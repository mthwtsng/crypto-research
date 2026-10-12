"""Small cached, rate-limited Solana JSON-RPC client for this wallet study.

The endpoint defaults are loaded from the project AGENTS.md file, so API keys
do not need to be copied into this source file or into the raw-data manifests.
"""

from __future__ import annotations

import fcntl
import gzip
import hashlib
import itertools
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_CACHE_DIR = HERE / "raw_rpc"
MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 35
MAX_GLOBAL_REQUESTS_PER_SECOND = 6.0
ENHANCED_METHODS = {"getTransactionsForAddress"}
DYNAMIC_METHODS = {"getSlot", "getBalance"}
_request_ids = itertools.count(1)
_fallback_lock = threading.Lock()


class RPCError(RuntimeError):
    """An RPC call failed without exposing the configured endpoint URL."""

    def __init__(self, provider: str, method: str, message: str, *, transient: bool = False):
        super().__init__(f"{provider} {method}: {message}")
        self.provider = provider
        self.method = method
        self.transient = transient


def _read_endpoints() -> dict[str, str]:
    env = {
        "shyft": os.environ.get("WALLET_EDGE_SHYFT_RPC_URL") or os.environ.get("SHYFT_RPC_URL"),
        "alchemy": os.environ.get("WALLET_EDGE_ALCHEMY_RPC_URL") or os.environ.get("ALCHEMY_RPC_URL"),
    }
    agents = REPO_ROOT / "AGENTS.md"
    text = agents.read_text(encoding="utf-8") if agents.exists() else ""
    urls = re.findall(r"https://[^\s`<>\"']+", text)
    for raw in urls:
        url = raw.rstrip(".,);]")
        if "rpc.shyft.to" in url and not env["shyft"]:
            env["shyft"] = url
        elif "solana-mainnet.g.alchemy.com" in url and not env["alchemy"]:
            env["alchemy"] = url
    missing = [name for name, url in env.items() if not url]
    if missing:
        raise RuntimeError(
            "RPC endpoint configuration missing for " + ", ".join(missing)
            + "; set WALLET_EDGE_*_RPC_URL or restore project AGENTS.md defaults"
        )
    return {name: str(url) for name, url in env.items()}


def _cache_dir() -> Path:
    raw = os.environ.get("WALLET_EDGE_RPC_CACHE_DIR")
    path = Path(raw).expanduser() if raw else DEFAULT_CACHE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _cache_path(cache_dir: Path, method: str, params: Any) -> Path:
    key = hashlib.sha256(_canonical_bytes({"method": method, "params": params})).hexdigest()
    return cache_dir / f"{key}.json.gz"


def _read_gzip_json(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _atomic_gzip_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
                zipped.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _rate_gate(cache_dir: Path) -> None:
    """Cross-process start-rate gate; default 4 req/s and never over 6 req/s."""
    requested = float(os.environ.get("WALLET_EDGE_RPC_RATE", "4"))
    rate = min(MAX_GLOBAL_REQUESTS_PER_SECOND, max(0.1, requested))
    interval = 1.0 / rate
    lock_path = cache_dir / ".rpc_rate_limit.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="ascii") as lock_file:
        file_lock_acquired = False
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            file_lock_acquired = True
        except (AttributeError, OSError):
            _fallback_lock.acquire()
        try:
            lock_file.seek(0)
            raw_previous = lock_file.read().strip()
            try:
                previous = float(raw_previous) if raw_previous else 0.0
            except ValueError:
                previous = 0.0
            delay = previous + interval - time.time()
            if delay > 0:
                time.sleep(delay)
            started = time.time()
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(f"{started:.9f}")
            lock_file.flush()
        finally:
            if file_lock_acquired:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            else:
                _fallback_lock.release()


def _safe_error_message(error: Any) -> str:
    if isinstance(error, dict):
        code = error.get("code")
        message = str(error.get("message", "JSON-RPC error"))
        message = re.sub(r"https?://\S+", "[endpoint redacted]", message)
        return f"code {code}: {message}" if code is not None else message
    message = str(error)
    return re.sub(r"https?://\S+", "[endpoint redacted]", message)


def _transient_rpc_error(error: Any) -> bool:
    if not isinstance(error, dict):
        return False
    code = error.get("code")
    message = str(error.get("message", "")).lower()
    return code in {429, -32005, -32004} or "rate limit" in message or "too many requests" in message


def _post_once(endpoint: str, provider: str, method: str, params: Any) -> Any:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": next(_request_ids), "method": method, "params": params},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        transient = status == 429 or 500 <= status < 600
        raise RPCError(provider, method, f"HTTP {status}", transient=transient) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise RPCError(provider, method, f"transport error: {reason.__class__.__name__}", transient=True) from None

    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RPCError(provider, method, "response was not valid JSON") from None
    if not isinstance(document, dict):
        raise RPCError(provider, method, "response was not a JSON-RPC object")
    if "error" in document:
        err = document["error"]
        raise RPCError(provider, method, _safe_error_message(err), transient=_transient_rpc_error(err))
    if "result" not in document:
        raise RPCError(provider, method, "response has neither result nor error")
    return document["result"]


def rpc_with_meta(method: str, params: Any, *, cache: bool | None = None) -> dict[str, Any]:
    """Call RPC and return `{result, provider, cache_hit}` for provenance.

    Enhanced history uses Alchemy. Standard JSON-RPC reads use Shyft first and
    fall back to Alchemy on failure. Successful responses are gzip-cached under
    this report's `raw_rpc/`; dynamic slot/balance reads bypass cache by default.
    """
    if cache is None:
        cache = method not in DYNAMIC_METHODS
    cache_dir = _cache_dir()
    cached_file = _cache_path(cache_dir, method, params) if cache else None
    if cached_file and cached_file.exists():
        document = _read_gzip_json(cached_file)
        return {"result": document["result"], "provider": document["provider"], "cache_hit": True}

    endpoints = _read_endpoints()
    providers = ["alchemy"] if method in ENHANCED_METHODS else ["shyft", "alchemy"]
    failures: list[str] = []
    for provider in providers:
        endpoint = endpoints.get(provider)
        if not endpoint:
            failures.append(f"{provider}: endpoint unavailable")
            continue
        last_error: RPCError | None = None
        for attempt in range(MAX_RETRIES + 1):
            _rate_gate(cache_dir)
            try:
                result = _post_once(endpoint, provider, method, params)
                document = {"schema_version": 1, "provider": provider, "method": method, "params": params, "result": result}
                if cached_file:
                    _atomic_gzip_json(cached_file, document)
                return {"result": result, "provider": provider, "cache_hit": False}
            except RPCError as error:
                last_error = error
                if not error.transient or attempt >= MAX_RETRIES:
                    break
                time.sleep(min(8.0, 0.35 * (2**attempt)))
        if last_error:
            failures.append(str(last_error))
    raise RuntimeError("; ".join(failures) or f"No RPC route available for {method}")


def rpc(method: str, params: Any, *, cache: bool | None = None) -> Any:
    """Convenience helper that returns the JSON-RPC result value."""
    return rpc_with_meta(method, params, cache=cache)["result"]


__all__ = ["RPCError", "rpc", "rpc_with_meta"]
