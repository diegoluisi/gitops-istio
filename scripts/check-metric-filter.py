"""Fail if Alloy's GC drop rule intersects checked-in dashboard/rule dependencies."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
config = (root/'addons/alloy/alloy/base/values.yaml').read_text()
block = config.split('prometheus.relabel "metrics_hygiene" {',1)[1].split('prometheus.scrape "apiserver"',1)[0]
pattern = re.search(r'regex = "([^"]+)"',block).group(1)
drop = re.compile(pattern)
files = list((root/'addons/grafana/grafana/overlays/ops/dashboards').rglob('*.json'))
files += list((root/'addons/mimir/mimir/base/rules').glob('*.yaml'))
files += [root/'addons/grafana/grafana/base/values.yaml']
conflicts=[]
for path in files:
    for token in set(re.findall(r'[a-zA-Z_:][a-zA-Z0-9_:]*',path.read_text())):
        if drop.fullmatch(token):
            conflicts.append((str(path.relative_to(root)),token))
assert not conflicts, 'Filtered metrics are referenced: '+str(conflicts)
assert drop.fullmatch('go_gc_heap_live_bytes')
assert drop.fullmatch('gc_unused_total')
for required in ['go_gc_duration_seconds','go_gc_duration_seconds_count','process_cpu_seconds_total',
                 'node_cpu_seconds_total','container_cpu_usage_seconds_total','istio_requests_total']:
    assert not drop.fullmatch(required), required
assert config.count('forward_to = [prometheus.remote_write.mimir.receiver]') == 1
print(f'Metric filter dependency check passed ({len(files)} dashboard/rule files).')
