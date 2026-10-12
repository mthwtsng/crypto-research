"""Inspect collection leases instead of trusting a stale status-file label."""
import datetime
import fcntl
import json
import pathlib

P = pathlib.Path(__file__).resolve().parent


def held(name):
    path = P / name
    if not path.exists():
        return False
    with path.open('r') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def status():
    recorded = json.loads((P / 'PARALLEL_STATUS.json').read_text())
    coordinator = held('RUN.lock')
    supervisor = held('SUPERVISOR.lock')
    recorded_inflight = recorded.get('worker_inflight_count')
    return {
        'checked_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'coordinator_active': coordinator,
        'supervisor_active': supervisor,
        'live_state': 'running' if coordinator else ('starting_or_retrying' if supervisor else 'stopped'),
        'admitted': recorded.get('total_selected'),
        'ordered_admitted_coins': recorded.get('ordered_admitted_coins', recorded.get('total_selected')),
        'ordered_prefix_cursor': recorded.get('ordered_prefix_cursor'),
        'target': recorded.get('target'),
        'total_completed_by_workers': recorded.get('total_completed_by_workers'),
        'worker_progress_scope': recorded.get('worker_progress_scope'),
        'worker_completion_counts_this_run': recorded.get('worker_completion_counts_this_run'),
        'worker_completed_unique_candidates_this_run': recorded.get('worker_completed_unique_candidates_this_run'),
        'worker_inflight_count': recorded_inflight if coordinator else 0,
        'last_recorded_worker_inflight_count': recorded_inflight,
        'resumed_staged_valid_count': recorded.get('resumed_staged_valid_count'),
        'resumed_staged_valid_unadmitted_count': recorded.get('resumed_staged_valid_unadmitted_count'),
        'buffered_verified_count': recorded.get('buffered_verified_count'),
        'buffered_verified_by_current_run_workers': recorded.get('buffered_verified_by_current_run_workers'),
        'buffered_verified_from_resumed_stages': recorded.get('buffered_verified_from_resumed_stages'),
        'buffered_verified_from_other_cached_outcomes': recorded.get('buffered_verified_from_other_cached_outcomes'),
        'last_worker_status': recorded.get('last_worker_status'),
        'last_recorded_state': recorded.get('state'),
        'last_recorded_update_utc': recorded.get('updated_utc'),
        'last_recorded_workers': recorded.get('workers'),
        'worker_reported_staged_audits': len(list((P / 'parallel_stage/candidates').glob('*/audits/*.json'))),
        'note': 'Staged audits are worker-reported results pending independent ordered admission, not additional manifest admissions.',
    }


if __name__ == '__main__':
    print(json.dumps(status(), indent=2))
