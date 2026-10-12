#!/usr/bin/env python3
"""Frozen creation-hash sample. Read-only RPC; never use outcomes for sampling."""
import concurrent.futures, datetime, gzip, hashlib, json, pathlib, pickle, re, sys, threading, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research/day_general_20261004/helpers'))
sys.path.insert(0, str(ROOT / 'research/day_general_20261004'))
import prepare as P

AUTH = 'TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
SOL = {None, '11111111111111111111111111111111', 'So11111111111111111111111111111111111111112'}
text = (ROOT / 'AGENTS.md').read_text()
URL = 'https://solana-mainnet.g.alchemy.com/v2/' + re.search(r'alchemy.com/v2/([^`]+)', text).group(1)
LOCK = threading.Lock()
LAST = 0.

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.partial')
    if path.suffix == '.gz':
        with gzip.open(temp, 'wt', compresslevel=1) as f: json.dump(value, f)
    else: temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)

def rpc(method, params):
    global LAST
    key = hashlib.sha256(json.dumps([method, params], sort_keys=True).encode()).hexdigest()
    path = OUT / 'rpc' / (key + '.json.gz')
    if path.exists(): return json.load(gzip.open(path, 'rt'))['result']
    for attempt in range(4):
        try:
            with LOCK:
                time.sleep(max(0., .4 - (time.monotonic() - LAST)))
                LAST = time.monotonic()
            request = urllib.request.Request(URL, json.dumps(dict(jsonrpc='2.0', id=1, method=method, params=params)).encode(), {'Content-Type': 'application/json'})
            response = json.load(urllib.request.urlopen(request, timeout=35))
            if 'error' in response: raise RuntimeError(str(response['error']))
            save(path, response)
            return response['result']
        except Exception:
            if attempt == 3: raise
            time.sleep(1 + attempt)

def history(address, start, end):
    token = None
    rows = []
    for page in range(120):
        bounds = {'lt': end}
        if start is not None: bounds['gte'] = start
        cfg = dict(transactionDetails='full', encoding='jsonParsed', maxSupportedTransactionVersion=1, sortOrder='asc', limit=1000, commitment='finalized', filters=dict(status='succeeded', blockTime=bounds))
        if token: cfg['paginationToken'] = token
        result = rpc('getTransactionsForAddress', [address, cfg])
        rows.extend(result['data'])
        next_token = result.get('paginationToken')
        if not next_token:
            rows = list({x['transaction']['signatures'][0]: x for x in rows}.values())
            if any(x.get('transactionIndex') is None for x in rows): raise ValueError('missing_history_index')
            return sorted(rows, key=lambda x: (x['slot'], x['transactionIndex'])), page + 1
        if next_token == token: raise ValueError('pagination_cycle')
        token = next_token
    raise ValueError('history_cap')

def census(hour):
    path = OUT / 'census' / (str(hour) + '.json.gz')
    if path.exists(): return json.load(gzip.open(path, 'rt'))
    rows, pages = history(AUTH, hour, hour + 3600)
    creations = {}
    for tx in rows:
        for c in P.decoder.creations(tx):
            if hour <= tx['blockTime'] < hour + 3600:
                creations[c['mint']] = dict(mint=c['mint'], creation=c, creation_time=tx['blockTime'], creation_slot=tx['slot'], signature=tx['transaction']['signatures'][0])
    result = dict(start=hour, end=hour+3600, complete=True, receipts=len(rows), pages=pages, creations=list(creations.values()))
    save(path, result)
    print('CENSUS', datetime.datetime.fromtimestamp(hour, datetime.timezone.utc).isoformat(), len(creations), 'pages', pages, flush=True)
    return result

def tape(item):
    path = OUT / 'raw_curves' / (item['mint'] + '.json.gz')
    end = min(item['creation_time'] + 1800, FREEZE['capture_end'])
    if path.exists(): data = json.load(gzip.open(path, 'rt'))
    else:
        rows, pages = history(item['creation']['bonding_curve'], None, end+1)
        data = dict(mint=item['mint'], requested_end_time=end, transactions=rows, pages=pages)
        save(path, data)
    value, audit = P.make(data)
    if value:
        value.update(creation_metadata=item['creation'], source='20261011_frozen_creation_hash_sample', decision_end_time=end)
    return value, audit

FREEZE = json.loads((OUT / 'FREEZE.json').read_text())
if __name__ == '__main__':
    census_rows = []
    with concurrent.futures.ThreadPoolExecutor(2) as executor:
        futures = {executor.submit(census, hour): hour for hour in range(FREEZE['start'], FREEZE['end'], 3600)}
        for future in concurrent.futures.as_completed(futures):
            try: census_rows.append(future.result())
            except Exception as e: census_rows.append(dict(start=futures[future], complete=False, error=repr(e), creations=[]))
            save(OUT / 'CENSUS_PROGRESS.json', census_rows)
    if not all(x['complete'] for x in census_rows): raise RuntimeError('incomplete_24h_census')
    chosen = []
    for hour in sorted(census_rows, key=lambda x: x['start']):
        eligible = [c for c in hour['creations'] if c['creation'].get('quote_mint') in SOL and not c['creation'].get('is_mayhem_mode', False)]
        chosen.extend(sorted(eligible, key=lambda x: hashlib.sha256((FREEZE['seed']+x['mint']).encode()).hexdigest())[:FREEZE['per_hour']])
    save(OUT / 'CREATION_SAMPLE.json', dict(chosen=chosen, census_creations=sum(len(x['creations']) for x in census_rows), selection='fixed hash per complete creation hour; no outcome or survival filter'))
    tapes, audits = [], []
    with concurrent.futures.ThreadPoolExecutor(2) as executor:
        futures = {executor.submit(tape, item): item for item in chosen}
        for future in concurrent.futures.as_completed(futures):
            try: value, audit = future.result()
            except Exception as e: value, audit = None, dict(mint=futures[future]['mint'], error=repr(e))
            if value: tapes.append(value)
            audits.append(audit)
            save(OUT / 'PREPARE_AUDIT.json', audits)
            if len(audits) % 10 == 0: print('TAPES', len(audits), '/', len(chosen), 'prepared', len(tapes), flush=True)
    with gzip.open(OUT / 'TAPES.pkl.gz', 'wb') as f: pickle.dump(tapes, f)
    save(OUT / 'COLLECTION_COMPLETE.json', dict(selected=len(chosen), prepared=len(tapes), errors=[a for a in audits if a.get('error')], custody_gaps=[a for a in audits if a.get('custody_gap')]))
    print('COLLECTION_COMPLETE', len(chosen), len(tapes), flush=True)
