"""Bounded synthetic journeys and steady Bookinfo traffic; stdlib only."""
import argparse
import collections
import concurrent.futures
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGETS = {
    'ingress_productpage': ('http://istio-ingressgateway.istio-gateways.svc.cluster.local:8080/productpage', ['The Comedy of Errors', 'ISBN-10']),
    'ingress_details': ('http://istio-ingressgateway.istio-gateways.svc.cluster.local:8080/details', ['Shakespeare']),
    'internal_details': ('http://details.bookinfo.svc.cluster.local:9080/details/0', ['Shakespeare']),
}
BUCKETS = [.05, .1, .25, .5, 1, 2, 5, 10]
LOCK = threading.Lock()
STATE = {name: {'success': 0, 'failure': 0, 'fast': 0, 'duration': 0.,
                'buckets': [0]*len(BUCKETS), 'last_success': 0, 'last_run': 0,
                'healthy': 0, 'last_duration': 0.} for name in TARGETS}


def fetch(url, required):
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read(256000).decode(errors='replace')
            status = response.status
            success = status == 200 and all(token in body for token in required)
    except urllib.error.HTTPError as error:
        status, success = error.code, False
    except Exception as error:
        status, success = type(error).__name__, False
    return success, time.monotonic()-start, status


def loop():
    while True:
        start = time.monotonic()
        for name, (url, required) in TARGETS.items():
            good, duration, status = fetch(url, required)
            with LOCK:
                row = STATE[name]
                row['success' if good else 'failure'] += 1
                row['fast'] += int(good and duration <= 1)
                row['duration'] += duration
                for i, bound in enumerate(BUCKETS):
                    row['buckets'][i] += int(duration <= bound)
                row.update(last_run=time.time(), healthy=int(good), last_duration=duration)
                if good:
                    row['last_success'] = time.time()
            if not good:
                print(json.dumps({'probe': name, 'status': status, 'success': False,
                                  'duration_seconds': duration}), flush=True)
        time.sleep(max(0, 5-(time.monotonic()-start)))


def metrics():
    lines = []
    with LOCK:
        for name, row in STATE.items():
            labels = f'probe="{name}"'
            count = row['success']+row['failure']
            for outcome in ['success', 'failure']:
                lines.append(f'bookinfo_probe_requests_total{{{labels},outcome="{outcome}"}} {row[outcome]}')
            lines.append(f'bookinfo_probe_good_latency_total{{{labels}}} {row["fast"]}')
            for field, key in [('success','healthy'), ('last_run_timestamp_seconds','last_run'),
                               ('last_success_timestamp_seconds','last_success'), ('duration_seconds','last_duration')]:
                lines.append(f'bookinfo_probe_{field}{{{labels}}} {row[key]}')
            for bound, value in zip(BUCKETS, row['buckets']):
                lines.append(f'bookinfo_probe_duration_seconds_bucket{{{labels},le="{bound}"}} {value}')
            lines += [f'bookinfo_probe_duration_seconds_bucket{{{labels},le="+Inf"}} {count}',
                      f'bookinfo_probe_duration_seconds_count{{{labels}}} {count}',
                      f'bookinfo_probe_duration_seconds_sum{{{labels}}} {row["duration"]}']
    return '\n'.join(lines)+'\n'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ['/metrics', '/healthz']:
            self.send_error(404)
            return
        body = (metrics() if self.path == '/metrics' else 'ok\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--burst', action='store_true')
    args = parser.parse_args()
    if args.burst:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(lambda _: fetch(*TARGETS['internal_details'])[2], range(200)))
        print(json.dumps({'requests': 200, 'concurrency': 32, 'results': dict(collections.Counter(results))}))
    else:
        threading.Thread(target=loop, daemon=True).start()
        ThreadingHTTPServer(('0.0.0.0', 9090), Handler).serve_forever()
