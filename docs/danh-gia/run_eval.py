"""Chạy bộ câu hỏi đánh giá RAG qua API đang chạy (http://localhost:5000/api).

Dùng:  python run_eval.py            # chạy các câu chưa có kết quả
       python run_eval.py Q01 G02    # chạy lại vài câu
Ghi kết quả vào rag-eval-results.json cùng thư mục. Cần tài khoản demo sv.nguyenducanh@.
"""
import json, re, sys, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = 'http://localhost:5000/api'
QS = json.load(open(HERE / 'rag-eval-questions.json', encoding='utf-8'))
OUT = HERE / 'rag-eval-results.json'
only = sys.argv[1:]  # tùy chọn: chạy lại vài mã câu hỏi


def call(method, path, body=None, tok=None, timeout=900):
    h = {'Content-Type': 'application/json'}
    if tok:
        h['Authorization'] = 'Bearer ' + tok
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


state = {'tok': None, 'at': 0}


def token():
    if not state['tok'] or time.time() - state['at'] > 600:
        r = call('POST', '/auth/login', {'email': 'sv.nguyenducanh@hvktcnan.edu.vn', 'password': 'Demo@2026'})
        state['tok'], state['at'] = r['accessToken'], time.time()
    return state['tok']


def kw_ok(answer, q):
    groups = q.get('must', [])
    hit = [bool(re.search(g, answer, re.I)) for g in groups]
    need = q.get('min', len(groups))
    return sum(hit) >= need, hit


results = {}
try:
    results = {r['id']: r for r in json.load(open(OUT, encoding='utf-8'))}
except Exception:
    pass

for q in QS:
    if only and q['id'] not in only:
        continue
    if not only and q['id'] in results and not results[q['id']].get('error'):
        continue
    rec = {'id': q['id'], 'mode': q['mode'], 'cat': q['cat'], 'q': q['q']}
    t0 = time.time()
    for attempt in range(3):
        try:
            res = call('POST', '/chat/ask', {'question': q['q'], 'mode': q['mode']}, token())
            break
        except urllib.error.HTTPError as e:
            rec['error'] = f'HTTP {e.code}: {e.read().decode()[:200]}'
            time.sleep(30 if e.code in (429, 500, 502, 503) else 5)
            if e.code == 401:
                state['tok'] = None
        except Exception as e:  # noqa
            rec['error'] = repr(e)[:200]
            time.sleep(10)
    else:
        results[q['id']] = rec
        json.dump(list(results.values()), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(q['id'], 'LỖI', rec['error'], flush=True)
        continue
    rec.pop('error', None)
    m = res['message']
    chunks = m.get('retrievedChunks') or []
    union = '\n'.join(c.get('text', '') for c in chunks)
    rec.update({
        'wall_s': round(time.time() - t0, 1),
        'answer': m['content'],
        'abstained': m['abstained'],
        'abstainReason': m.get('abstainReason'),
        'confidence': m.get('confidence'),
        'threshold': m.get('threshold'),
        'grounded': m.get('grounded'),
        'route': m.get('route'),
        'rounds': m.get('rounds'),
        'latencyMs': m.get('latencyMs'),
        'trace': m.get('trace'),
        'nCitations': len(m.get('citations') or []),
        'citations': [{k: v for k, v in c.items() if k != 'text'} for c in (m.get('citations') or [])],
        'retrievedSources': [c.get('source_file') for c in chunks],
    })
    if q.get('evidence'):
        rec['hit5'] = bool(re.search(q['evidence'], union, re.I))
    if q.get('must'):
        ok, per = kw_ok(m['content'], q)
        rec['kw_ok'], rec['kw_each'] = ok, per
    rec['fabricated_article'] = bool(re.search(r'Điều\s+\d+', m['content'])) if q.get('abstain') else None
    results[q['id']] = rec
    json.dump(list(results.values()), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(q['id'], 'abst' if m['abstained'] else 'ans ', 'conf', m.get('confidence'), 'ground', m.get('grounded'),
          'kw', rec.get('kw_ok'), 'hit5', rec.get('hit5'), f"{rec['wall_s']}s", flush=True)
    try:
        call('DELETE', '/chat/conversations/' + res['conversationId'], tok=token())
    except Exception:
        pass
    time.sleep(6)
print('XONG', flush=True)
