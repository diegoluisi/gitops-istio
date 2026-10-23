# Bookinfo circuit breaker lab

`apps/bookinfo/overlays/dev/circuit-breaker.yaml` defines a DestinationRule for
`details.bookinfo.svc.cluster.local`. The dev overlay owns these deliberately low
lab limits. Other Bookinfo services and external egress policies are unchanged.

The caller's Envoy enforces the policy when it sends traffic to Details. The
resource is configuration, not an extra network hop. Productpage's sidecar and
the ingress gateway can each enforce their own independent limits.

- `maxConnections: 1`: at most one upstream TCP connection per proxy cluster.
- `http1MaxPendingRequests: 1`: at most one pending request waiting for a connection.
- `http2MaxRequests: 1`: at most one active upstream request (also applies to HTTP/1).
- `maxRequestsPerConnection: 1`: close a connection after one request, making
  connection-pool overflow easier to reproduce.
- `consecutive5xxErrors: 5`: repeated upstream server errors can eject an endpoint;
  evaluated with a 5-second detection interval and a 30-second base ejection time.
- `maxEjectionPercent: 100`, `minHealthPercent: 0`: allow even the single Details
  endpoint to be ejected, without disabling outlier detection at low health.
  During ejection a single-replica service can return `503 UH` (no healthy upstream).

These are per-proxy limits, not a global requests-per-second rate limit. Capacity
must be tuned before using this configuration outside the lab.

## Verify and generate traffic

After Argo CD syncs `bookinfo-dev`, inspect the caller's outbound cluster:

```sh
istioctl proxy-config clusters deployment/productpage-v1 -n bookinfo \
  --fqdn details.bookinfo.svc.cluster.local -o json
```

Look for `circuitBreakers.thresholds` and `outlierDetection`. Normal traffic:

```sh
kubectl -n bookinfo exec deployment/productpage-v1 -c productpage -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://details:9080/details/0").status)'
```

To exercise overflow, send concurrent requests from the same sidecar:

```sh
kubectl -n bookinfo exec -i deployment/productpage-v1 -c productpage -- python - <<'PY'
import collections
import concurrent.futures
import urllib.error
import urllib.request

def request(_):
    try:
        with urllib.request.urlopen('http://details:9080/details/0', timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__

with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
    print(dict(collections.Counter(pool.map(request, range(200)))))
PY
```

Expect successful responses mixed with 503s. Exact counts depend on timing and
retries. Confirm the breaker with counters and access logs, rather than assuming
any 503 proves circuit breaking:

```sh
kubectl -n bookinfo exec deployment/productpage-v1 -c istio-proxy -- \
  pilot-agent request GET 'stats?filter=outbound.*9080.*details.*(overflow|ejections)'
kubectl -n bookinfo logs deployment/productpage-v1 -c istio-proxy --since=2m
```

Some Envoy counters may be absent when the mesh proxy statistics matcher does
not include them; use the `UO` access-log evidence in that case.

Pool overflow increments `upstream_rq_pending_overflow` and/or
`upstream_cx_overflow`; rejected requests normally carry `UO` in the access-log
response flags. `UH` instead indicates no healthy upstream. The concurrency test
exercises pool limits; it does not deliberately make Details emit upstream 5xx
errors to test outlier ejection. When load stops, normal requests should work
again immediately if no endpoint was ejected.

To disable the lab, remove `circuit-breaker.yaml` from the dev kustomization and
commit the change; Argo CD prunes the DestinationRule.

Reference: https://istio.io/latest/docs/tasks/traffic-management/circuit-breaking/

## Verified lab result

A 200-request run with 32 workers returned 42 HTTP 200 and 158 HTTP 503
responses. Productpage Envoy logs showed `503 UO` and
`upstream_reset_before_response_started{overflow}`. A subsequent sequential
request returned HTTP 200. The loaded Envoy cluster confirmed all three pool
thresholds were 1 and outlier detection was configured. Outlier ejection itself
was not fault-tested.
