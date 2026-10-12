"""User-directed local-first queue revision; source folders remain read-only."""
import sys
sys.dont_write_bytecode = True
import datetime
import json
import pathlib
import parallel_collect as Q
import local_active_seed as L

P = pathlib.Path(__file__).resolve().parent
LOCAL_ONLY_END = int(datetime.datetime(2026, 9, 8, tzinfo=datetime.timezone.utc).timestamp())


def build_revision(existing, local):
    candidates, exclusions, seen = [], [], set()
    for row in list(local) + list(existing):
        mint = row['mint']
        if mint in seen:
            exclusions.append(dict(mint=mint, reason='duplicate_local_first_candidate_retained'))
            continue
        # Migration census dates are migration times, not creation times. We
        # exclude the early census interval unless represented by a local row;
        # later candidates get a separate genuine-creation guard in verify().
        timestamp = row.get('creation_time', row.get('time'))
        if not row.get('local_raw_path') and timestamp is not None and timestamp < LOCAL_ONLY_END:
            exclusions.append(dict(mint=mint, reason='local_only_early_window_no_local_source'))
            continue
        seen.add(mint)
        candidates.append(dict(row))
    return candidates, exclusions


def main():
    old = Q.C.read(Q.QUEUE_PATH)
    if old.get('selection_revision') == 'local_first_240s_v2':
        print(json.dumps({'state': 'already_revised', 'candidate_count': old['candidate_count']}))
        return
    local = L.load_local_candidates()
    candidates, exclusions = build_revision(old['candidates'], local)
    archive = P / 'archive' / 'queue_before_local_first'
    archive.mkdir(parents=True, exist_ok=True)
    for source in (Q.QUEUE_PATH, Q.QUEUE_EXCLUSIONS_PATH):
        if source.exists():
            target = archive / (source.stem + '.' + old['queue_sha256'] + source.suffix)
            if not target.exists():
                target.write_bytes(source.read_bytes())
    data = dict(old, candidates=candidates, candidate_count=len(candidates),
                queue_sha256=Q._queue_digest(candidates),
                selection_revision='local_first_240s_v2',
                previous_queue_sha256=old['queue_sha256'],
                revised_utc=Q.utc_now(), local_seed_count=len(local),
                ordering='local active manifest day-interleaved first; existing later-window queue follows; first mint occurrence retained',
                local_only_creation_end_exclusive=LOCAL_ONLY_END,
                required_post_migration_seconds=240,
                revision_exclusion_count=len(exclusions))
    Q._atomic_json(Q.QUEUE_PATH, data)
    Q._atomic_json(Q.QUEUE_EXCLUSIONS_PATH, dict(queue_sha256=data['queue_sha256'],
                   count=len(exclusions), exclusions=exclusions, original_archive=str(archive.relative_to(P))))
    print(json.dumps({key: data[key] for key in ('candidate_count', 'local_seed_count', 'revision_exclusion_count', 'queue_sha256')}))


if __name__ == '__main__':
    main()
