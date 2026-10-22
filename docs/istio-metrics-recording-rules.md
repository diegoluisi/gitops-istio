# Istio metrics recording rules

Alloy scrapes Istio every 15 seconds and remote-writes raw metrics to Mimir.
Mimir evaluates `istio.workload-rates` every 30 seconds using a five-minute rate
window. Rate is calculated before aggregation to handle individual counter resets.
The rules remove scrape identity (`instance`, `pod`, `namespace`, and legacy
Kubernetes scrape labels), retaining workload namespaces, cluster, reporter,
response codes, and histogram bucket boundaries. Do not sum source and destination
reporters when counting requests: they observe the same traffic at different hops.

Rules are provisioned from `addons/mimir/mimir/base/rules/istio.yaml` through a
hashed ConfigMap. Mimir's local ruler backend reads them under tenant `anonymous`
(multitenancy is disabled); its writable working directory remains on the data PVC.
Kustomize updates the StatefulSet template when the rule contents change.

The Istio Sidecar Metrics dashboard uses the recorded rates. Its rate window is
fixed at five minutes, independent of dashboard resolution. Other dashboards and
Kiali continue using raw metrics. Retaining raw metrics preserves troubleshooting
and does not reduce ingestion/storage costs; recordings add a smaller derived set.

Deploy Mimir before Grafana to avoid a temporary empty overview. After deployment,
check `/prometheus/api/v1/rules` on Mimir for group health and query:

```promql
workload:istio_requests_total:rate5m
```

Generate application traffic if no request series exist. New recordings have no
historical backfill. Compare with the same aggregation of `rate(istio_requests_total[5m])`.
Check `up{job="integrations/istio"}` for scrape failures. The IstioMetricsDown
Grafana rule now alerts on missing data; optional legacy metric alerts still allow
no data. External notification receivers require a separate destination choice.

Full trace sampling and access logs remain enabled for the lab. For larger traffic
volumes, choose sampling/retention budgets and size storage before increasing load.
The Alloy `cluster="ops"` value must be unique in each future cluster deployment;
recording rules retain that label and the overview groups by cluster.

References:
- https://istio.io/latest/docs/ops/best-practices/observability/
- https://grafana.com/docs/mimir/latest/references/architecture/components/ruler/
