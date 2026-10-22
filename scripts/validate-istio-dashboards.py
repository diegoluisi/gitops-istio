#!/usr/bin/env python3
"""Read-only query smoke check. Requires port-forwards documented in docs/istio-dashboards.md.

Uses broad variable selections and a one-hour lookback. Empty results are reported,
not silently converted to zero; they can mean no matching traffic or absent metrics.
"""
import json,pathlib,re,urllib.request,urllib.parse,time,concurrent.futures
root=pathlib.Path(__file__).resolve().parents[1]/'addons/grafana/grafana/overlays/ops/dashboards'
def expand(q):
 q=q.replace('$__rate_interval','5m').replace('$__interval','5m').replace('$__range','1h')
 q=q.replace('$label_name','namespace').replace('${search:doublequote}','""').replace('${minDuration:raw}','100ms').replace('${service:raw}','.*')
 q=re.sub(r'\$\{[^}]+\}', '.+',q); q=re.sub(r'\$(namespace|scrape_namespace|workload|service)\b','.+',q)
 return q
def run(item):
 file,title,typ,q=item; q=expand(q)
 base={'prometheus':'http://127.0.0.1:19009/prometheus/api/v1/query','loki':'http://127.0.0.1:13100/loki/api/v1/query','tempo':'http://127.0.0.1:13200/api/search'}[typ]
 params={'q':q,'limit':5,'start':int(time.time()-3600),'end':int(time.time())} if typ=='tempo' else {'query':q}
 if typ=='loki' and not re.match(r'\s*(topk|sum|count|bytes_over_time|quantile_over_time|max|max_over_time|count_over_time)',q):
  base+='_range'; params.update({'start':int((time.time()-3600)*1e9),'end':int(time.time()*1e9),'limit':5})
 try:
  d=json.load(urllib.request.urlopen(base+'?'+urllib.parse.urlencode(params),timeout=25))
  values=d.get('traces',[]) if typ=='tempo' else d.get('data',{}).get('result',[])
  return {'file':file,'panel':title,'type':typ,'status':'ok','series':len(values),'query':q,'sample':values[:1]}
 except Exception as e:
  detail=e.read().decode() if isinstance(e,urllib.error.HTTPError) else str(e)
  return {'file':file,'panel':title,'type':typ,'status':'error','error':detail,'query':q}
items=[]
for p in root.glob('*.json'):
 d=json.loads(p.read_text())
 for panel in d['panels']:
  for t in panel.get('targets',[]):
   if t.get('hide'):continue
   typ=t.get('datasource',panel.get('datasource',{})).get('type','prometheus')
   q=t.get('expr',t.get('query',''))
   if typ not in ('prometheus','loki','tempo') or not q or t.get('queryType')=='traceId':continue
   items.append((p.name,panel['title'],typ,q))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,items))

for r in results:print(r['status'],r.get('series',''),r['file'],r['panel'],r.get('error',''))

raise SystemExit(1 if any(r["status"] != "ok" for r in results) else 0)
