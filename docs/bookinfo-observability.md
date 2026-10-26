# Bookinfo reliability and telemetry runbook

## What is deployed

`addons/alloy/bookinfo-probes/overlays/ops` is discovered by the ops ApplicationSet.
Its single lightweight Python process generates steady, sequential traffic every
five seconds across three probes:

- `ingress_productpage`: shared ingress `/productpage`, HTTP 200 and content
  containing both the book title and ISBN heading. This detects missing Details
  content even when Productpage returns HTTP 200.
- `ingress_details`: shared ingress `/details`, HTTP 200 and author content.
- `internal_details`: direct registered Details Service, same status/content check.

Alloy scrapes its metrics every 15 seconds into Mimir. No application image
changes, extra package installs at startup, or high-cardinality request labels
are required. Failed probes log their status and duration. Histograms include
failed requests too; the latency SLI only counts successful requests within 1s.
The worker makes sequential requests; failures/timeouts can reduce the probe rate.
Last-run freshness alerts detect a stuck worker even if `/healthz` remains up.

These in-cluster journeys do **not** measure external DNS, host/LB connectivity,
browser rendering, or the complete correctness of every Reviews version. A probe
on a host outside the cluster is needed for that coverage.

## SLOs and dashboards

Grafana folder **Bookinfo** contains:

1. **Bookinfo Overview & SLOs** (`bookinfo-overview`): probe health/freshness,
   synthetic p95, traffic/errors, error-budget remaining and deployment markers.
2. **Bookinfo Resilience** (`bookinfo-resilience`): caller response flags,
   connections, active/pending requests, overflow counters, active ejections,
   Details replica readiness and related Loki logs.
3. **Telemetry Pipeline Health** (`telemetry-health`): scrapes, export failures,
   queues, remote-write lag, rejected telemetry, PVC utilization and pod health.

Lab objectives are **99.5% availability** and **95% successful journeys within
1s**, evaluated independently for each probe over seven days. Latency failures
include failed requests. Mimir recording rules compute ratios from counters,
not averages of percentages. Seven-day panels show only the collected history
until seven days have elapsed; no data/zero requests means unknown, not 100%.
Mimir retention is seven days, leaving no long-term historical margin.

Grafana provisions fast (5m/1h, burn >6) and slow (30m/6h, burn >3) alert pairs,
plus a minimum 30 requests in five minutes, to avoid low-traffic noise. These
thresholds are **lab tuning**, not copied 30-day production thresholds. Prolonged
probe failure/freshness has independent alerts and is not hidden by the traffic
minimum. Existing alert rules remain in place.

Alerts evaluate in Grafana. No external contact point or messages were added;
configure your chosen receiver separately if notifications outside Grafana are
required. Metrics loss is detectable only while Grafana and its datasource are
functioning; monitor this stack from outside the cluster for independent coverage.

## Circuit breaker evidence

Bookinfo Deployment templates now include a targeted `proxyStatsMatcher`. Pods
roll on config changes; proxy statistics configuration is read at startup. Only
Details-related upstream pool/outlier counters are enabled in addition to Istio's
defaults. The shared ingress has separate limits/counters; this first iteration
shows the Bookinfo callers, not extra gateway statistics.

Use `UO` / overflow to identify pool-limit rejection, `UH` for no healthy upstream,
and `UF` for connection failure. Upstream application 5xx and proxy-generated
503s are distinct. Outlier ejection is per endpoint and caller; it is not a global
open/closed breaker state. Never interpret an absent counter as zero.

Generate an opt-in burst (200 requests, concurrency 32):

```sh
job=bookinfo-burst-$(date +%s)
kubectl -n alloy create job --from=cronjob/bookinfo-load-burst "$job"
kubectl -n alloy logs -f job/"$job" -c load
```

The CronJob is suspended by default. Kubernetes native sidecars allow the Job to
complete. Completed Jobs expire after ten minutes. With the intentionally small
circuit-breaker limits, 503s during this experiment are expected. Watch the
Resilience dashboard and recover normal sequential traffic after the burst.
This test exercises overflow, not deliberate repeated upstream-5xx ejection.

## Telemetry alerts and investigation

- Expected scrape failure/disappearance: Alloy, Mimir, Loki, Tempo and probe exporter.
- Stale probe updates and current synthetic journey failures.
- OTLP failed span exports and queue utilization >80%.
- Remote-write failures and lag >60s.
- Backend rejected telemetry, PVC utilization >85%, and unready backend pods.

Counter families for rejected telemetry may not exist until the first rejection.
No-data is OK for these event counters; expected-target and stale-data rules
handle coverage failures separately. Docker Desktop may not expose volume stats;
PVC panels will remain empty if the kubelet supplies none. Backend logs are then
needed to investigate disk failures. These are single-replica lab components,
with local storage rather than a high-availability production deployment.

For an incident: compare synthetic probes, caller flags, readiness and recent
GitOps deployment annotations. Check Alloy exporter logs and backend readiness
before concluding an empty application dashboard means no traffic. Use service
DNS for HTTP scrapes under `REGISTRY_ONLY`; arbitrary pod-IP requests may fail.

## Application instrumentation versus Istio

Istio provides network-boundary spans: service calls, durations and proxy errors.
Application OpenTelemetry instrumentation adds internal operations, exceptions,
database/cache calls, business outcomes, and time spent before/after outgoing
requests. It can reveal that a page returned 200 with incomplete content or that
latency was dominated by application processing rather than the network.

Propagate W3C trace context consistently and check the current Istio provider's
propagation behavior before expecting a single combined trace. Avoid duplicate
HTTP instrumentation and never place passwords, raw bodies or customer IDs in
span attributes. Start with Productpage entrypoint and dependency/business spans,
then verify parent-child relationships in Tempo. This work was not included in
the synthetic/SLO/dashboard implementation.

References:
- https://sre.google/workbook/alerting-on-slos/
- https://istio.io/latest/docs/ops/configuration/telemetry/envoy-stats/
- https://opentelemetry.io/docs/concepts/signals/traces/
