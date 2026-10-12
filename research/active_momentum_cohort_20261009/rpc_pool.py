"""Read-only, cross-process-safe Solana RPC pool for the active cohort collector.

The public ``rpc(method, params)``, ``request(provider, method, params)``,
``save(path, value)``, ``ROOT`` and ``OUT`` interfaces are kept compatible with
the existing collector. The durable receipt cache key and layout are unchanged.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import math
import os
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent
RPC_CACHE = OUT / "rpc"
CONTROL = OUT / ".rpc_control"
EVENTS = OUT / "RPC_EVENTS.jsonl"
CAPABILITIES = OUT / "RPC_CAPABILITIES.json"
PROVIDER_CONFIG = OUT / "RPC_PROVIDER_CONFIG.json"

_instructions = (ROOT / "AGENTS.md").read_text()
_BASE_PROVIDERS = {
    "alchemy": re.search(
        r"https://solana-mainnet\.g\.alchemy\.com/v2/[A-Za-z0-9_-]+",
        _instructions,
    ).group(),
    "shyft": re.search(
        r"https://rpc\.shyft\.to\?api_key=[A-Za-z0-9_-]+", _instructions
    ).group(),
    "solami": "https://rpc.solami.dev/sol?api_key="
    + re.search(r"\bsk_[A-Za-z0-9_-]+", _instructions).group(),
}


def _load_helius_endpoint(path=PROVIDER_CONFIG, key="helius"):
    """Load an optional Helius endpoint without exposing it in diagnostics."""
    try:
        config = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return None
    endpoint = config.get(key) if isinstance(config, dict) else None
    if not isinstance(endpoint, str):
        return None
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != "mainnet.helius-rpc.com":
        return None
    return endpoint


def _provider_endpoints(base, config_path=PROVIDER_CONFIG):
    """Return configured providers while keeping absent Helius keys optional."""
    providers = dict(base)
    h1 = _load_helius_endpoint(config_path, "helius")
    if h1:
        providers["helius"] = h1
    h2 = _load_helius_endpoint(config_path, "helius_2")
    if h2:
        providers["helius_2"] = h2
    return providers


PROVIDERS = _provider_endpoints(_BASE_PROVIDERS)

# Target ceilings, not guarantees. Shared file pacing adapts down after 429s.
TARGET_RPS = {"alchemy": 10.0, "shyft": 5.0, "solami": 5.0, "helius": 8.0, "helius_2": 8.0}
MAX_IN_FLIGHT = {"alchemy": 8, "shyft": 4, "solami": 4, "helius": 4, "helius_2": 4}
PROVIDER_ORDER = tuple(
    name for name in ("alchemy", "shyft", "solami", "helius", "helius_2") if name in PROVIDERS
)
ALCHEMY_METHOD_CU = {"getBlock": 40, "getTransactionsForAddress": 100}
ALCHEMY_DEFAULT_METHOD_CU = 100
ALCHEMY_BLOCK_MAX_RPS = 10.0
THROTTLE_RETRY_FLOOR_SECONDS = 1.0
PACE_ALGORITHM_VERSION = "weighted_jit_v2"
_NULL_UNAVAILABLE_METHODS = {"getBlock", "getTransaction"}
_HISTORY_METHOD = "getTransactionsForAddress"

# Existing receipts provide representative finalized slots near the middle of
# each requested month. Only signatures are requested from providers here.
_HISTORY_PROBES = {
    "2026-08": {"slot": 441666345, "block_time": 1787674059},
    "2026-09": {"slot": 447527916, "block_time": 1789563371},
}
_BOUNDARY_PROBES = {
    "2026-09-01": {"slot_before": 443281993, "block_time_before": 1788220766},
    "2026-10-01": {"slot_before": 452119280, "block_time_before": 1790812740},
}

_thread_lock = threading.Lock()
_thread_counts = {}


class RpcFailure(RuntimeError):
    """Sanitized provider failure; never includes a request URL or API key."""

    def __init__(
        self,
        kind,
        *,
        http_status=None,
        rpc_code=None,
        rate_limited=False,
        unsupported=False,
        retry_after=None,
    ):
        super().__init__(kind)
        self.kind = kind
        self.http_status = http_status
        self.rpc_code = rpc_code
        self.rate_limited = rate_limited
        self.unsupported = unsupported
        self.retry_after = retry_after


def _control_path(name):
    CONTROL.mkdir(parents=True, exist_ok=True)
    return CONTROL / name


@contextlib.contextmanager
def _locked_file(path, *, nonblocking=False):
    """Hold a process-shared advisory lock for the lifetime of this context."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        operation = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        fcntl.flock(fd, operation)
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextlib.contextmanager
def _provider_slot(provider):
    """A crash-safe process-shared semaphore implemented with slot file locks."""
    slots = int(os.environ.get(f"COHORT_{provider.upper()}_MAX_IN_FLIGHT", str(MAX_IN_FLIGHT[provider])))
    while True:
        for number in range(slots):
            path = _control_path(f"{provider}.inflight.{number}.lock")
            lock = _locked_file(path, nonblocking=True)
            try:
                fd = lock.__enter__()
            except BlockingIOError:
                continue
            try:
                yield fd
            finally:
                lock.__exit__(None, None, None)
            return
        time.sleep(0.025)


def _read_locked_json(fd, fallback):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return fallback


def _write_locked_json(fd, value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        view = view[written:]
    os.fsync(fd)


def _wall_time():
    """Clock used by the cross-process pacing state; kept injectable in tests."""
    return time.time()


def _sleep(seconds):
    """Sleep hook kept separate so pacing retries can be tested without waits."""
    time.sleep(seconds)


def _provider_interval(provider, method, scale):
    """Return spacing for one actual request, including method-weighted Alchemy CU."""
    if provider == "alchemy":
        try:
            rate = float(os.environ.get("COHORT_ALCHEMY_CU_PER_SECOND", "400"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_COHORT_ALCHEMY_CU_PER_SECOND") from exc
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("invalid_COHORT_ALCHEMY_CU_PER_SECOND")
        cost = ALCHEMY_METHOD_CU.get(method, ALCHEMY_DEFAULT_METHOD_CU)
        interval = cost / (rate * scale)
        if method == "getBlock":
            try:
                block_max_rps = float(os.environ.get("COHORT_ALCHEMY_BLOCK_MAX_RPS", str(ALCHEMY_BLOCK_MAX_RPS)))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_COHORT_ALCHEMY_BLOCK_MAX_RPS") from exc
            if not math.isfinite(block_max_rps) or block_max_rps <= 0:
                raise ValueError("invalid_COHORT_ALCHEMY_BLOCK_MAX_RPS")
            interval = max(interval, 1.0 / block_max_rps)
        return interval
    if provider == "helius":
        try:
            helius_rps = float(os.environ.get("COHORT_HELIUS_TARGET_RPS", str(TARGET_RPS["helius"])))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_COHORT_HELIUS_TARGET_RPS") from exc
        if not math.isfinite(helius_rps) or helius_rps <= 0:
            raise ValueError("invalid_COHORT_HELIUS_TARGET_RPS")
        return 1.0 / (helius_rps * scale)
    return 1.0 / (TARGET_RPS[provider] * scale)


def _reserve_provider_start(provider, method):
    """Acquire the next shared start only when due; never reserve future time."""
    path = _control_path(f"{provider}.pace.json")
    with _locked_file(path) as fd:
        state = _read_locked_json(
            fd,
            {
                "next_start": 0.0,
                "backoff_until": 0.0,
                "scale": 1.0,
                "rate_limit_streak": 0,
                "successes_since_limit": 0,
            },
        )
        now = _wall_time()
        scale = min(1.0, max(0.125, float(state.get("scale", 1.0))))
        due = max(now, float(state.get("next_start", 0.0)), float(state.get("backoff_until", 0.0)))
        delay = max(0.0, due - now)
        if delay > 0:
            return delay
        state["next_start"] = now + _provider_interval(provider, method, scale)
        _write_locked_json(fd, state)
        return 0.0


def _note_provider_success(provider):
    path = _control_path(f"{provider}.pace.json")
    with _locked_file(path) as fd:
        state = _read_locked_json(fd, {"scale": 1.0, "successes_since_limit": 0})
        successes = int(state.get("successes_since_limit", 0)) + 1
        state["successes_since_limit"] = successes
        if successes >= 30:
            state["scale"] = min(1.0, float(state.get("scale", 1.0)) + 0.1)
            state["successes_since_limit"] = 0
            state["rate_limit_streak"] = 0
        _write_locked_json(fd, state)


def _note_provider_throttle(provider, retry_after=None):
    path = _control_path(f"{provider}.pace.json")
    with _locked_file(path) as fd:
        state = _read_locked_json(
            fd,
            {"scale": 1.0, "rate_limit_streak": 0, "successes_since_limit": 0},
        )
        now = _wall_time()
        current_backoff = float(state.get("backoff_until", 0.0))
        new_burst = current_backoff <= now
        streak = int(state.get("rate_limit_streak", 0))
        if new_burst:
            streak += 1
            state["rate_limit_streak"] = streak
            state["scale"] = max(0.125, float(state.get("scale", 1.0)) * 0.5)
        state["successes_since_limit"] = 0
        fallback_delay = min(30.0, 1.0 * (2 ** min(streak - 1, 5)))
        supplied_delay = max(0.0, float(retry_after)) if retry_after is not None else fallback_delay
        delay = max(THROTTLE_RETRY_FLOOR_SECONDS, supplied_delay)
        state["backoff_until"] = max(
            current_backoff, now + delay
        )
        _write_locked_json(fd, state)


def _append_event(event):
    """Append one telemetry row while holding an inter-process file lock."""
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(EVENTS, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _method_marker(provider, method):
    suffix = hashlib.sha256(method.encode()).hexdigest()[:12]
    return _control_path(f"unsupported.{provider}.{suffix}")


def _provider_marker(provider):
    return _control_path(f"disabled-provider.{provider}")


def _is_disabled(provider, method):
    return _provider_marker(provider).exists() or _method_marker(provider, method).exists()


def _mark_unsupported(provider, method):
    marker = _method_marker(provider, method)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        pass


def _mark_provider_disabled(provider):
    marker = _provider_marker(provider)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        pass


def _http_status(exc):
    try:
        return int(exc.code)
    except Exception:
        return None


def _parse_retry_after(value):
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            parsed = dt.datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT")
            return max(0.0, parsed.replace(tzinfo=dt.timezone.utc).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def _request_once(provider, method, params):
    request = urllib.request.Request(
        PROVIDERS[provider],
        json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode(),
        {"Content-Type": "application/json", "User-Agent": "active-cohort-rpc/1"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=35)
    except urllib.error.HTTPError as exc:
        status = _http_status(exc)
        retry = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
        exc.close()
        raise RpcFailure(
            "http_error",
            http_status=status,
            rate_limited=status == 429,
            retry_after=retry,
        ) from None
    except urllib.error.URLError:
        raise RpcFailure("network_error") from None
    except TimeoutError:
        raise RpcFailure("timeout") from None

    try:
        body = json.load(response)
    except Exception:
        raise RpcFailure("invalid_json") from None
    finally:
        response.close()

    if not isinstance(body, dict):
        raise RpcFailure("invalid_response")
    if "error" in body:
        error = body.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else None
        message = str(error.get("message", "")).lower() if isinstance(error, dict) else ""
        throttled = code == 429 or any(
            phrase in message
            for phrase in ("rate limit", "too many requests", "request limit", "throttled")
        )
        unsupported = code == -32601 or "method not found" in message or "unsupported method" in message
        raise RpcFailure(
            "rpc_error",
            rpc_code=code,
            rate_limited=throttled,
            unsupported=unsupported,
        )
    if "result" not in body:
        raise RpcFailure("missing_result")
    result = body["result"]
    if result is None and method in _NULL_UNAVAILABLE_METHODS:
        raise RpcFailure("null_unavailable")
    return result


def request(provider, method, params):
    """Make one provider request with shared pacing, concurrency and telemetry."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown_rpc_provider:{provider}")
    if _is_disabled(provider, method):
        raise RpcFailure("provider_method_disabled", unsupported=True)

    started = time.monotonic()
    status = "error"
    failure = None
    try:
        while True:
            with _provider_slot(provider):
                # Acquire an in-flight slot before claiming a start. If pacing
                # says to wait, release the slot and recheck shared state after
                # sleeping; this prevents stale sleepers from crossing a 429
                # backoff and avoids reserving starts that will later bunch up.
                delay = _reserve_provider_start(provider, method)
                if delay <= 0:
                    try:
                        result = _request_once(provider, method, params)
                    except RpcFailure as exc:
                        # Publish throttling before releasing this provider
                        # slot, so peers observe the backoff as they enter.
                        if exc.rate_limited:
                            _note_provider_throttle(provider, exc.retry_after)
                        if exc.unsupported:
                            _mark_unsupported(provider, method)
                        if exc.http_status in (401, 403):
                            _mark_provider_disabled(provider)
                        raise
                    _note_provider_success(provider)
                    status = "ok"
                    return result
            _sleep(delay)
    except RpcFailure as exc:
        failure = exc
        status = "unavailable" if exc.kind == "null_unavailable" else "error"
        raise
    finally:
        event = {
            "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "provider": provider,
            "method": method,
            "pace_algorithm_version": PACE_ALGORITHM_VERSION,
            "status": status,
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }
        if failure is not None:
            event["error_kind"] = failure.kind
            if failure.http_status is not None:
                event["http_status"] = failure.http_status
            if failure.rpc_code is not None:
                event["rpc_code"] = failure.rpc_code
        _append_event(event)
        with _thread_lock:
            key = (provider, method, status)
            _thread_counts[key] = _thread_counts.get(key, 0) + 1


def _cache_key(method, params):
    # Keep byte-for-byte compatible with the original cohort cache derivation.
    return hashlib.sha256(json.dumps([method, params], sort_keys=True).encode()).hexdigest()


def _cache_path(method, params):
    return RPC_CACHE / (_cache_key(method, params) + ".json.gz")


@contextlib.contextmanager
def _cache_key_lock(path):
    lock = pathlib.Path(path).with_name(pathlib.Path(path).name + ".lock")
    with _locked_file(lock):
        yield


def _cache_provider_allowed(method, params, provider):
    if method == _HISTORY_METHOD:
        return provider == "alchemy"
    if method == "getBlock":
        options = params[1] if isinstance(params, list) and len(params) > 1 and isinstance(params[1], dict) else {}
        if options.get("transactionDetails") != "signatures":
            return provider == "alchemy"
        if provider == "alchemy":
            return True
        if provider not in PROVIDERS:
            return False
        report = _valid_capabilities()
        month = _slot_period(params[0], report) if report else None
        if month is None:
            return False
        period = report.get("periods", {}).get(month, {})
        capability = period.get("providers", {}).get(provider, {})
        if provider == "helius":
            return _helius_block_probe_is_exact(period)
        alchemy_ok = period.get("providers", {}).get("alchemy", {}).get("status") == "ok"
        exact_match = capability.get("exact_signature_order_match") is True
        if not alchemy_ok or capability.get("status") != "ok" or not exact_match:
            return False
        return True
    return True


def _read_cache(path, method, params=None):
    try:
        with gzip.open(path, "rt") as stream:
            record = json.load(stream)
    except (OSError, EOFError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or "result" not in record:
        return None
    if params is not None and not _cache_provider_allowed(method, params, record.get("provider")):
        # Unproven alternate enhanced-history pages and signature arrays are
        # not authoritative. Leave them for inspection, but never consume them
        # as source-complete cache hits.
        return None
    if method in _NULL_UNAVAILABLE_METHODS and record.get("result") is None:
        # Old null receipts were not usable source coverage; do not let them
        # short-circuit provider fallback on the next run.
        try:
            pathlib.Path(path).unlink()
        except FileNotFoundError:
            pass
        return None
    return record


def _valid_capabilities():
    try:
        report = json.loads(CAPABILITIES.read_text())
    except (OSError, ValueError):
        return None
    if report.get("probe_version") != 1 or not report.get("periods"):
        return None
    return report


def _slot_period(slot, report):
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return None
    ranges = report.get("slot_ranges", {})
    for month in ("2026-08", "2026-09"):
        bounds = ranges.get(month) or {}
        lower = bounds.get("start_slot")
        upper = bounds.get("end_slot_exclusive")
        if (lower is None or slot >= int(lower)) and (upper is None or slot < int(upper)):
            return month
    return None


def _preferred_provider():
    value = os.environ.get("COHORT_RPC_PREFERRED_PROVIDER", "").strip().lower()
    return value if value in PROVIDERS else None


def _helius_block_probe_is_exact(period):
    """Require every Helius proof recorded for a month before routing/caching."""
    providers = period.get("providers", {})
    alchemy = providers.get("alchemy", {})
    helius = providers.get("helius", {})
    return (
        period.get("alchemy_first_attempt") is True
        and alchemy.get("status") == "ok"
        and helius.get("status") == "ok"
        and helius.get("exact_signature_order_match") is True
        and helius.get("routing_eligible") is True
        and helius.get("same_blockhash") is True
        and helius.get("same_block_time") is True
    )


def _stable_order(providers, cache_key, preferred=None):
    providers = [name for name in providers if name in PROVIDERS]
    if not providers:
        return []
    if preferred in providers:
        return [preferred] + [name for name in providers if name != preferred]
    start = int(cache_key[:12], 16) % len(providers)
    return providers[start:] + providers[:start]


def _route(method, params, cache_key):
    preferred = _preferred_provider()
    if method == _HISTORY_METHOD:
        # Pagination-token continuity and complete historical coverage are
        # provider-specific. The repository has not proven an alternate's
        # compatibility, so failures surface for retry instead of switching.
        return ["alchemy"] if not _is_disabled("alchemy", method) else []

    if method == "getBlock":
        options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
        # Only signatures-only blocks were capability-probed. Full-block
        # requests stay on Alchemy; no secondary has been tested for full bodies.
        if options.get("transactionDetails") != "signatures":
            return ["alchemy"] if not _is_disabled("alchemy", method) else []

        report = _valid_capabilities()
        if report is None:
            return ["alchemy"] if not _is_disabled("alchemy", method) else []
        month = _slot_period(params[0], report)
        if month is None:
            return ["alchemy"] if not _is_disabled("alchemy", method) else []
        period = report["periods"].get(month, {})
        primary_probe = period.get("providers", {}).get("alchemy", {}).get("status")
        if not period.get("alchemy_first_attempt"):
            return ["alchemy"] if not _is_disabled("alchemy", method) else []

        capable_secondaries = []
        for name in PROVIDER_ORDER:
            if name == "alchemy":
                continue
            capability = period.get("providers", {}).get(name, {})
            proven = (
                capability.get("status") == "ok"
                and capability.get("exact_signature_order_match") is True
                and capability.get("routing_eligible") is True
            )
            if name.startswith("helius"):
                proven = _helius_block_probe_is_exact(period)
            if proven and not _is_disabled(name, method):
                capable_secondaries.append(name)
        # Only exact signature-list parity establishes a safe secondary route:
        # the collector validates transactionIndex against absolute list offset.
        # The recorded Alchemy probe must also have succeeded for that month.
        available = capable_secondaries[:]
        if not _is_disabled("alchemy", method):
            available.append("alchemy")
        if not capable_secondaries:
            return ["alchemy"] if not _is_disabled("alchemy", method) else []
        if primary_probe == "ok":
            return _stable_order(available, cache_key, preferred if preferred in capable_secondaries else None)
        return _stable_order(available, cache_key, preferred)

    # Other methods are spread by stable cache-key hashing. Failures that prove
    # an endpoint or method unavailable are remembered across worker processes.
    capable = [name for name in PROVIDER_ORDER if not _is_disabled(name, method)]
    return _stable_order(capable, cache_key, preferred)


def save(path, value):
    """Atomically save JSON or gzip JSON, retaining the collector's API."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        path.name + f".{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.partial"
    )
    if path.suffix == ".gz":
        with gzip.open(temporary, "wt", compresslevel=1) as stream:
            json.dump(value, stream)
    else:
        temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def rpc(method, params):
    """Return a durable receipt, serializing duplicate cross-process cache work."""
    cache = _cache_path(method, params)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with _cache_key_lock(cache):
        record = _read_cache(cache, method, params) if cache.exists() else None
        if record is not None:
            return record["result"]

        failures = []
        providers = _route(method, params, _cache_key(method, params))
        for attempt in range(3):
            if attempt:
                time.sleep(min(0.5 * attempt, 2.0))
            for provider in providers:
                if _is_disabled(provider, method):
                    continue
                try:
                    result = request(provider, method, params)
                    # Never replace a valid receipt if one appeared via a
                    # different compatible writer or a prior cache repair.
                    existing = _read_cache(cache, method, params) if cache.exists() else None
                    if existing is None:
                        save(
                            cache,
                            {
                                "provider": provider,
                                "method": method,
                                "params": params,
                                "result": result,
                            },
                        )
                    return result if existing is None else existing["result"]
                except RpcFailure as exc:
                    failure = {"provider": provider, "error": exc.kind}
                    if exc.http_status is not None:
                        failure["http_status"] = exc.http_status
                    if exc.rpc_code is not None:
                        failure["rpc_code"] = exc.rpc_code
                    failures.append(failure)
                except Exception as exc:
                    failures.append({"provider": provider, "error": type(exc).__name__})
        raise RuntimeError({"method": method, "failures": failures})


def _block_summary(result):
    if not isinstance(result, dict):
        return {"status": "invalid_response"}
    signatures = result.get("signatures")
    if signatures is None:
        return {"status": "unsupported_response_shape"}
    return {"status": "ok", "signature_count": len(signatures)}


def _probe_block(provider, slot):
    params = [
        slot,
        {
            "transactionDetails": "signatures",
            "rewards": False,
            "maxSupportedTransactionVersion": 1,
            "commitment": "finalized",
        },
    ]
    started = time.monotonic()
    try:
        value = request(provider, "getBlock", params)
        summary = _block_summary(value)
        summary["elapsed_seconds"] = round(time.monotonic() - started, 6)
        return summary, value
    except RpcFailure as exc:
        summary = {"status": "unavailable" if exc.kind == "null_unavailable" else "error"}
        summary["error_kind"] = exc.kind
        if exc.http_status is not None:
            summary["http_status"] = exc.http_status
        if exc.rpc_code is not None:
            summary["rpc_code"] = exc.rpc_code
        summary["elapsed_seconds"] = round(time.monotonic() - started, 6)
        return summary, None
    except Exception as exc:
        return {
            "status": "error",
            "error_kind": type(exc).__name__,
            "elapsed_seconds": round(time.monotonic() - started, 6),
        }, None


def _compare_signature_order(reference, candidate):
    """Compare secondary signatures with Alchemy without persisting the lists."""
    if not isinstance(reference, dict) or not isinstance(candidate, dict):
        return {"exact_signature_order_match": False, "comparison": "unavailable"}
    left = reference.get("signatures")
    right = candidate.get("signatures")
    if not isinstance(left, list) or not isinstance(right, list):
        return {"exact_signature_order_match": False, "comparison": "missing_signature_list"}
    left_set, right_set = set(left), set(right)
    left_positions = {signature: i for i, signature in enumerate(left)}
    right_is_subsequence = all(
        left_positions.get(signature, -1) < left_positions.get(next_signature, -1)
        for signature, next_signature in zip(right, right[1:])
    ) if len(right) > 1 else True
    return {
        "exact_signature_order_match": left == right,
        "same_signature_set": left_set == right_set,
        "shared_signature_count": len(left_set & right_set),
        "alchemy_only_signature_count": len(left_set - right_set),
        "secondary_only_signature_count": len(right_set - left_set),
        "secondary_order_is_alchemy_subsequence": right_is_subsequence,
    }


def _get_block_time(slot):
    try:
        value = request("alchemy", "getBlockTime", [slot])
        return int(value) if value is not None else None
    except Exception:
        return None


def _find_first_slot_at_or_after(target_time, known_before_slot, known_before_time):
    """Find a produced slot at the UTC date boundary using Alchemy block times."""
    if known_before_time >= target_time:
        return None
    low_slot = int(known_before_slot)
    low_time = int(known_before_time)
    high_slot = low_slot + 512
    high_time = _get_block_time(high_slot)
    expansions = 0
    while (high_time is None or high_time < target_time) and expansions < 10:
        high_slot += 512 * (2 ** expansions)
        high_time = _get_block_time(high_slot)
        expansions += 1
    if high_time is None or high_time < target_time:
        return None

    skipped = 0
    while high_slot - low_slot > 1 and skipped < 128:
        middle = (low_slot + high_slot) // 2
        value = _get_block_time(middle)
        if value is None:
            # Skipped slots have no block to route. Move to the next produced
            # slot so the resulting boundary is a real finalized block.
            candidate = middle + 1
            for _ in range(16):
                value = _get_block_time(candidate)
                if value is not None:
                    break
                candidate += 1
            if value is None or candidate >= high_slot:
                low_slot = middle
                skipped += 1
                continue
            middle = candidate
        if value >= target_time:
            high_slot, high_time = middle, value
        else:
            low_slot, low_time = middle, value
        skipped = 0
    if high_slot - low_slot != 1:
        return None
    return {"slot": high_slot, "block_time": high_time, "method": "Alchemy getBlockTime binary search"}


def probe_historical_block_capabilities():
    """Record Alchemy-first August/September signatures-only provider probes.

    This is an explicit one-time operator step before parallel collection:
    ``python3 rpc_pool.py --probe-history``. Secondary routes stay disabled for
    historical blocks until this durable report exists.
    """
    report = {
        "probe_version": 1,
        "probed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_utc": {"start": "2026-08-18T00:00:00Z", "end_exclusive": "2026-10-01T00:00:00Z"},
        "probe_method": "getBlock transactionDetails=signatures; finalized; no transaction bodies",
        "periods": {},
        "slot_ranges": {},
        "boundary_probes": {},
        "routing_policy": "Alchemy attempted first for each month; a secondary is eligible only if its signatures-only response exactly matches Alchemy's ordered list for that month; Alchemy remains fallback.",
    }

    for month, probe in _HISTORY_PROBES.items():
        providers = {}
        alchemy_result = None
        # Explicitly contact Alchemy first for every date stratum.
        primary, alchemy_result = _probe_block("alchemy", probe["slot"])
        providers["alchemy"] = primary
        period = {
            "sample_slot": probe["slot"],
            "sample_block_time": probe["block_time"],
            "transaction_details": "signatures",
            "alchemy_first_attempt": True,
            "probe_order": ["alchemy"],
            "providers": providers,
        }
        if alchemy_result is not None:
            params = [
                probe["slot"],
                {
                    "transactionDetails": "signatures",
                    "rewards": False,
                    "maxSupportedTransactionVersion": 1,
                    "commitment": "finalized",
                },
            ]
            cache = _cache_path("getBlock", params)
            with _cache_key_lock(cache):
                existing = _read_cache(cache, "getBlock", params) if cache.exists() else None
                if existing is None:
                    save(cache, {"provider": "alchemy", "method": "getBlock", "params": params, "result": alchemy_result})

        for provider in ("shyft", "solami"):
            # One explicit August test per secondary establishes range support;
            # failures keep that provider off the full August route.
            outcome, secondary_result = _probe_block(provider, probe["slot"])
            if secondary_result is not None:
                outcome.update(_compare_signature_order(alchemy_result, secondary_result))
            else:
                outcome["exact_signature_order_match"] = False
                outcome["comparison"] = "secondary_unavailable"
            outcome["routing_eligible"] = (
                outcome.get("status") == "ok"
                and outcome.get("exact_signature_order_match") is True
                and providers["alchemy"].get("status") == "ok"
            )
            providers[provider] = outcome
            period["probe_order"].append(provider)
        period["secondary_route_enabled"] = any(
            providers[name].get("routing_eligible") is True for name in ("shyft", "solami")
        )
        report["periods"][month] = period

    for boundary, probe in _BOUNDARY_PROBES.items():
        target = int(dt.datetime.fromisoformat(boundary + "T00:00:00+00:00").timestamp())
        found = _find_first_slot_at_or_after(
            target, probe["slot_before"], probe["block_time_before"]
        )
        report["boundary_probes"][boundary] = {
            "known_slot_before": probe["slot_before"],
            "known_block_time_before": probe["block_time_before"],
            "target_block_time": target,
            "result": found,
            "status": "ok" if found else "unavailable",
        }

    sept_start = report["boundary_probes"].get("2026-09-01", {}).get("result")
    oct_start = report["boundary_probes"].get("2026-10-01", {}).get("result")
    if sept_start and oct_start:
        report["slot_ranges"] = {
            "2026-08": {"start_slot": None, "end_slot_exclusive": sept_start["slot"]},
            "2026-09": {"start_slot": sept_start["slot"], "end_slot_exclusive": oct_start["slot"]},
        }
    else:
        report["slot_range_status"] = "month boundaries unavailable; secondaries remain disabled for historical getBlock"
    save(CAPABILITIES, report)
    return report


def health():
    """Retain a small endpoint health diagnostic without mixing cursor state."""
    jobs = [(name, "getSlot", []) for name in PROVIDERS]

    def test(job):
        provider, method, params = job
        try:
            value = request(provider, method, params)
            return {"provider": provider, "method": method, "ok": True, "value": value}
        except Exception as exc:
            return {"provider": provider, "method": method, "ok": False, "error_kind": getattr(exc, "kind", type(exc).__name__)}

    with concurrent.futures.ThreadPoolExecutor(len(jobs)) as executor:
        results = list(executor.map(test, jobs))
    save(OUT / "RPC_HEALTH.json", results)
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-history", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.probe_history:
        print(json.dumps(probe_historical_block_capabilities(), indent=2), flush=True)
    elif args.health:
        health()
    else:
        parser.error("choose --probe-history or --health")
