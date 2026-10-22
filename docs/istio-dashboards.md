# Istio dashboards

The dashboards are provisioned by GitOps in Grafana's Istio folder. The collection
covers the mesh, services, workloads, control plane/gateways, egress, Kubernetes
health, access logs, and traces. Dashboard navigation preserves the time range.

| Dashboard | Use |
| --- | --- |
| Istio Sidecar Metrics | Overview using Mimir workload recording rules; fixed five-minute rates |
| Istio Services Overview | Per-service traffic, HTTP error percentage, p50/p95/p99 latency, callers, response codes and gRPC errors |
| Istio Workloads Overview | Per-workload inbound/outbound traffic, errors, latency and namespace sidecar resources |
| Istio Control Plane and Gateways | Scrape availability, connected proxies, pushes, gateway traffic/resources and mTLS |
| Istio Egress | Egress gateway requests/latency and sidecar `block_all` responses |
| Kubernetes Workload Health | Readiness, restarts, CPU, memory, scrape health and available volume statistics |
| Grafana Loki Dashboard for Istio Service Mesh | Detailed Envoy access-log analysis, counts, response codes, durations and client addresses |
| Istio Logs | Application and mesh logs, with Loki-to-Tempo links |
| Istio Traces | Recent/slow/error searches and selected trace waterfall |

## Reading the panels

- Metrics retain cluster and reporter where applicable. Source and destination
  reports describe different observations of a request; do not add them together
  to count unique requests. Service/workload views also retain destination namespace.
- HTTP 5xx percentages return zero when there is traffic but no 5xx series. A
  zero request rate leaves the ratio undefined rather than implying successful traffic.
- Log statistics count proxy observations, not unique visits. Choose an ingress
  proxy to approximate visitor traffic. Forwarded addresses may contain proxy
  chains; fallback downstream addresses may be internal peers.
- Log stat/ranking panels use the panel time range; the visitors panel explicitly
  overrides it to 15 minutes, and active client addresses to five minutes.
- Access-log durations are milliseconds. Ranking by maximum latency is distinct
  from p95 latency. Top-ten rankings now actually limit results to ten.
- No gRPC errors is expected without gRPC traffic. Configuration rejects and
  certificate errors can be absent until an event occurs. Absence does not prove
  zero failures; check scrape health and Istiod logs.
- Docker Desktop local-path storage may not export `kubelet_volume_stats_*`.
  An empty PVC panel means volume capacity telemetry is unavailable.
- A new recording-rule deployment has no historical backfill. Deploy Mimir before
  dashboards that use the recordings and generate traffic before evaluating rates.
- The trace waterfall requires selecting a trace or pasting an ID. Slow/error
  searches can legitimately have no matches. Log links accept unpadded hexadecimal
  IDs as well as full-width IDs and do not truncate them to 16 characters.

## Read-only validation

In separate terminals, start temporary forwards:

```sh
kubectl -n mimir port-forward svc/mimir 19009:9009
kubectl -n loki port-forward svc/loki 13100:3100
kubectl -n tempo port-forward svc/tempo 13200:3200
```

Run:

```sh
python3 scripts/validate-istio-dashboards.py
```

The script exercises PromQL, LogQL and TraceQL with broad dashboard selections
and a one-hour lookback. It returns nonzero for query errors and reports empty
results separately. It does not deploy dashboards or test Grafana's browser rendering.
Stop the forwards afterward. Custom textbox expressions remain user input; testing
broad defaults does not validate every possible expression.

During the 2026-10-22 review, all 71 queries succeeded against live backends, 47
PromQL range queries succeeded, all three datasource UIDs were verified in Grafana,
and a real Tempo trace returned HTTP 200. Known empty panels were PVC statistics,
gRPC errors, configuration rejects, certificate errors, and blocked egress in the
selected time window. JSON validity, datasource references and Kustomize rendering
were also checked. Updated dashboards still require Git push and Argo CD sync;
these checks do not claim browser validation of an undeployed dashboard.

References:
- https://istio.io/latest/docs/ops/integrations/grafana/
- https://istio.io/latest/docs/ops/best-practices/observability/
