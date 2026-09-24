"""Run an honest, repeatable retrieval benchmark against a running Velocia API.
Standard library only. No database writes, model changes or expected-code injection.
"""
import argparse
import csv
import hashlib
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def code_key(value):
    text = str(value or '').upper().strip()
    # Remove the edition ONLY. Keep IS/IEC vs IS, part and section distinct.
    text = re.sub(r'\s*:\s*\d{4}\s*$', '', text)
    text = re.sub(r'\bSECTION\b', 'SEC', text)
    return re.sub(r'[^A-Z0-9]', '', text)


def hits(expected, returned):
    wanted = {code_key(x) for x in expected}
    return {str(k): int(any(code_key(x) in wanted for x in returned[:k])) for k in (1, 3, 5)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000/api/analyze')
    parser.add_argument('--dataset', type=Path, default=Path(__file__).with_name('evaluation_50.json'))
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('--run-label', default='local-current')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'evaluation_runs')
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    tests = json.loads(raw)['queries']
    if not tests or len({r['id'] for r in tests}) != len(tests):
        raise ValueError('Dataset is empty or contains duplicate IDs.')
    for row in tests:
        if not row.get('expected_codes') or not row.get('query'):
            raise ValueError('Missing query or expected codes.')
    started = datetime.now(timezone.utc)
    dest = args.output / started.strftime('%Y%m%dT%H%M%S%fZ')
    dest.mkdir(parents=True, exist_ok=False)
    output = []
    for n, row in enumerate(tests, 1):
        before = time.perf_counter()
        result = dict(row, returned_codes=[], hit_at={'1':0,'3':0,'5':0}, error=None)
        # Labels and source URLs are intentionally never sent to the engine.
        payload = json.dumps({'requirement':row['query'], 'category':row['category']}).encode()
        try:
            request = Request(args.url, data=payload, headers={'Content-Type':'application/json'}, method='POST')
            with urlopen(request, timeout=args.timeout) as response:
                data = json.load(response)
            standards = data.get('standards')
            if not isinstance(standards, list):
                raise ValueError('API response has no standards list')
            if any(not isinstance(r,dict) or not isinstance(r.get('is_number'),str) for r in standards):
                raise ValueError('Invalid standard record in API response')
            codes = [r['is_number'] for r in standards]
            result.update(returned_codes=codes, hit_at=hits(row['expected_codes'], codes), response=data)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            result['error'] = f'{type(error).__name__}: {error}'
        result['elapsed_seconds'] = round(time.perf_counter()-before, 3)
        output.append(result)
        print(f"[{n}/{len(tests)}] {row['id']} {row['category']} | " +
              ('ERROR' if result['error'] else f"Top1={result['hit_at']['1']} Top3={result['hit_at']['3']} Top5={result['hit_at']['5']}"), flush=True)
        # Checkpoint every response, even if a later request is interrupted.
        (dest/'raw_results.json').write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')

    def metrics(rows):
        return {'queries':len(rows), 'request_errors':sum(r['error'] is not None for r in rows),
                **{f'top_{k}':{'hits':sum(r['hit_at'][str(k)] for r in rows),
                   'total':len(rows),'percent':round(100*sum(r['hit_at'][str(k)] for r in rows)/len(rows),2)} for k in (1,3,5)}}
    summary = {'run_label':args.run_label,'started_utc':started.isoformat(),
               'dataset_sha256':hashlib.sha256(raw).hexdigest(), 'api_url':args.url,
               'evaluation_type':'Synthetic standard-family retrieval; not edition or technical applicability verification',
               'overall':metrics(output),
               'by_category':{cat:metrics([r for r in output if r['category']==cat]) for cat in sorted({r['category'] for r in output})},
               'median_request_seconds':round(statistics.median(r['elapsed_seconds'] for r in output),3)}
    (dest/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (dest/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['id','category','query','expected_codes','top_1','top_3','top_5','hit_1','hit_3','hit_5','seconds','error','source_url'])
        for r in output:
            codes=r['returned_codes']
            w.writerow([r['id'],r['category'],r['query'],' | '.join(r['expected_codes']),
                        ' | '.join(codes[:1]),' | '.join(codes[:3]),' | '.join(codes[:5]),
                        *[r['hit_at'][str(k)] for k in (1,3,5)],r['elapsed_seconds'],r['error'] or '',r['source_url']])
    print('\nSTANDARD-FAMILY RETRIEVAL RESULTS (edition ignored)')
    for k in (1,3,5):
        m=summary['overall'][f'top_{k}']; print(f"Top-{k}: {m['hits']}/{m['total']} = {m['percent']:.2f}%")
    errors=summary['overall']['request_errors']
    print(f'Request failures: {errors} (counted as misses, never removed from denominator)')
    if errors: print('Resolve request failures before treating this as a ranking-only benchmark.')
    print(f'Results saved in: {dest.resolve()}')

if __name__ == '__main__':
    main()
