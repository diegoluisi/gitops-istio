#!/usr/bin/env python3
"""Read-only query smoke check. Requires port-forwards documented in docs/istio-dashboards.md.

Uses broad variable selections and a one-hour lookback. Empty results are reported,
not silently converted to zero; they can mean no matching traffic or absent metrics.
"""
import json,pathlib,re,urllib.request,urllib.parse,time,concurrent.futures
root=pathlib.Path(__file__).resolve().parents[1]/'addons/grafana/grafana/overlays/ops/dashboards'
def expand(q, file):
 service=file.split('/')[0]
 values={'__rate_interval':'5m','__interval':'5m','__range':'1h','__range_s':'3600','__interval_ms':'300000','__auto':'5m',
         'namespace':service if service in ('argocd','mimir','loki','alloy','kyverno') else '.+',
         'cluster':'https://kubernetes.default.svc' if service=='argocd' else 'ops',
         'job':'.+','instance':'.+','kyvernoNS':'kyverno','groupby':'instance','grouping':'namespace,name,project',
         'latency_metrics':'1','interval':'5m','label_name':'namespace','label_value':'.+','search':'',
         'minDuration':'100ms','service':'.*','filters':''}
 def brace(m):
  name,fmt=m.group(1),m.group(2)
  value=values.get(name,'.+')
  return json.dumps(value) if fmt=='doublequote' else value
 q=re.sub(r'\$\{([A-Za-z_][A-Za-z_0-9]*)(?::([^}]+))?\}',brace,q)
 q=re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)',lambda m:values.get(m.group(1),'.+'),q)
 return q
def fetch_json(url):
 for attempt in range(4):
  try:
   with urllib.request.urlopen(url,timeout=25) as response:
    return json.load(response)
  except urllib.error.HTTPError as error:
   if error.code not in (429,503) or attempt==3:
    raise
   time.sleep(0.5 * 2**attempt)
def run(item):
 file,title,typ,q=item; q=expand(q,file)
 base={'prometheus':'http://127.0.0.1:19009/prometheus/api/v1/query','loki':'http://127.0.0.1:13100/loki/api/v1/query','tempo':'http://127.0.0.1:13200/api/search'}[typ]
 params={'q':q,'limit':5,'start':int(time.time()-3600),'end':int(time.time())} if typ=='tempo' else {'query':q}
 if typ=='loki' and not re.match(r'\s*(topk|sum|count|bytes_over_time|quantile_over_time|max|max_over_time|count_over_time)',q):
  base+='_range'; params.update({'start':int((time.time()-3600)*1e9),'end':int(time.time()*1e9),'limit':5})
 try:
  d=fetch_json(base+'?'+urllib.parse.urlencode(params))
  values=d.get('traces',[]) if typ=='tempo' else d.get('data',{}).get('result',[])
  return {'file':file,'panel':title,'type':typ,'status':'ok','series':len(values),'query':q,'sample':values[:1]}
 except Exception as e:
  detail=e.read().decode() if isinstance(e,urllib.error.HTTPError) else str(e)
  return {'file':file,'panel':title,'type':typ,'status':'error','error':detail,'query':q}
def panels_in(items):
 for panel in items:
  yield panel
  yield from panels_in(panel.get('panels',[]))
items=[]
for p in root.rglob('*.json'):
 d=json.loads(p.read_text())
 for panel in panels_in(d.get('panels',[])):
  for t in panel.get('targets',[]):
   if t.get('hide'):continue
   ds=t.get('datasource') or panel.get('datasource') or {}
   typ=ds.get('type','prometheus') if isinstance(ds,dict) else ('loki' if 'loki' in ds.lower() else 'prometheus')
   q=t.get('expr',t.get('query',''))
   if typ not in ('prometheus','loki','tempo') or not q or t.get('queryType')=='traceId':continue
   items.append((str(p.relative_to(root)),panel['title'],typ,q))
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,items))

for r in results:print(r['status'],r.get('series',''),r['file'],r['panel'],r.get('error',''))

raise SystemExit(1 if any(r["status"] != "ok" for r in results) else 0)
