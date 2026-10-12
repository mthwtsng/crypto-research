"""Archive and revoke only the superseded mandatory-terminal exclusions."""
import sys
sys.dont_write_bytecode = True
import datetime
import hashlib
import json
import pathlib
import parallel_collect as Q

P = pathlib.Path(__file__).resolve().parent


def superseded(row):
    return 'local_source_not_eligible:incomplete_local_curve_history' in str(row.get('reason', ''))


def main():
    archive = P / 'archive' / 'mandatory_terminal_exclusions'
    archive.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in ('REJECTED_CANDIDATES.json', 'PARALLEL_OUTCOMES.jsonl'):
        path = P / name
        data = path.read_bytes()
        archived = archive / (name + '.' + hashlib.sha256(data).hexdigest())
        if not archived.exists():
            archived.write_bytes(data)
        lines = name.endswith('.jsonl')
        rows = [json.loads(x) for x in data.decode().splitlines() if x.strip()] if lines else json.loads(data)
        retained = [row for row in rows if not superseded(row)]
        counts[name] = len(rows) - len(retained)
        if lines:
            temp = path.with_name(path.name + '.revision.partial')
            temp.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in retained))
            temp.replace(path)
        else:
            Q._atomic_json(path, retained)
    report = dict(revoked_exclusion_counts=counts, archive=str(archive.relative_to(P)),
                  reason='User authorizes complete fixed first-hour observations without mandatory graduation',
                  updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    Q._atomic_json(P / 'FIRST_HOUR_REQUEUE.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
