# Dashboard sources and lab adaptations

Dashboards are vendored in Git, not downloaded by Grafana at startup. Their
ConfigMaps carry `grafana_folder` annotations and the sidecar provisions folders
from the resulting filesystem directories. Existing custom dashboard UIDs are
preserved. Each service has its own ConfigMap to avoid the 1 MiB resource limit.

| Folder | Dashboard | Source |
| --- | --- | --- |
| Argo CD | ArgoCD | https://github.com/argoproj/argo-cd/blob/v3.2.0/examples/dashboard.json |
| Kyverno | Kyverno (15987, revision 2) | https://grafana.com/grafana/dashboards/15987-kyverno/ |
| Kyverno | Kyverno Overview | Repository dashboard for the installed CEL policy metrics |
| Mimir | Mimir / Overview | https://github.com/grafana/mimir/blob/mimir-3.2.1/operations/mimir-mixin-compiled/dashboards/mimir-overview.json |
| Loki | Loki / Operational | https://github.com/grafana/loki/blob/v3.7.8/production/loki-mixin-compiled/dashboards/loki-operational.json |
| Alloy | Resources, Controller, Prometheus Components, OpenTelemetry | https://github.com/grafana/alloy/tree/v1.20.1/operations/alloy-mixin/rendered/dashboards |
| Istio | Existing mesh, control plane, services, workloads, egress, logs and traces | Repository dashboards; Loki 14876 adapted earlier |
| Kubernetes | Workload Health | Repository dashboard |

Adaptations:

- Prometheus datasource references point to provisioned Mimir UID `mimir`;
  Loki references use `loki`. Import-only datasource variables are fixed constants.
- Legacy row layouts are flattened for modern provisioning and validation, and
  legacy graph/singlestat panels use timeseries/stat types. Existing query content
  is otherwise retained except for the explicit adaptations below.
- Alloy self-metrics carry cluster/namespace labels. Mimir uses job `mimir/mimir`,
  compatible with its upstream monolithic selectors. Loki's distributed job
  selectors target `loki/loki` in this monolithic deployment.
- Ten upstream recording rules required by Mimir/Loki overviews are provisioned
  through Mimir's ruler in `rules/service-dashboards.yaml`.
- Dashboard 15987 predates CEL policies. Evaluation counters and durations use
  the CEL metric equivalents. CPU queries use raw cAdvisor counters; memory
  selectors use this repository's kubelet scrape job. Legacy rule inventory,
  policy-type and quota panels can remain empty: they have no honest one-to-one
  equivalent for CEL-only policies. Use Kyverno Overview for current policy health.
- Loki's dashboard includes optional Promtail, distributed-component and storage
  features. Those panels can be empty because this lab uses Alloy, a single Loki
  process and filesystem storage. No synthetic zero metrics are added to hide
  absent components. Mimir alert-notification and object-storage panels likewise
  depend on those features actually being used.
- Alloy clustering-specific dashboards are omitted because clustering is disabled.
  The four included dashboards cover the installed collector's actual pipelines.

All dashboards are editable through Git. Grafana UI edits remain disabled.
Query smoke checks: `python3 scripts/validate-istio-dashboards.py` with the
Mimir/Loki/Tempo port-forwards documented in `docs/istio-dashboards.md`. Empty
results are reported separately from execution errors; a successful query is not
proof that an optional component exists or every browser visualization is correct.

Three existing manually imported Istio dashboards (Mesh, Service and Workload)
were exported from the running Grafana instance without changing their queries or
UIDs. They are now provisioned in the Istio folder as default-*.json; the Workload
dashboard previously lived in General. Their exported dashboard metadata retains
upstream descriptions and version information.

## Additional Grafana.com imports

Pinned copies with stable upstream UIDs, Mimir datasource binding and local cluster defaults:

| ID | Dashboard | Revision |
|---|---|---|
| 15757 | Kubernetes / Views / Global | 43 |
| 15758 | Kubernetes / Views / Namespaces | 46 |
| 15759 | Kubernetes / Views / Nodes | 40 |
| 15760 | Kubernetes / Views / Pods | 41 |
| 13407 | Loki2.0 Global Metrics | 1 |

Source: `https://grafana.com/api/dashboards/<ID>/revisions/<REV>/download`.
Kubernetes dashboards are by dotdc: https://github.com/dotdc/grafana-dashboards-kubernetes.
The Pods view's container CPU query uses our cAdvisor job rather than the
kube-state-metrics job used for object state. Linux-only/hardware-dependent
metrics may be absent. Loki queries are scoped to `job="loki/loki"` so Cortex
prefixes cannot accidentally display Mimir data. The legacy log counter is mapped
to `loki_internal_log_messages_total`; typoed tenant aggregation labels are fixed.
Legacy graph panels and the external pie-chart plugin are converted to Grafana
built-in timeseries/piechart panels. Optional ruler/cache/Cassandra/S3 and legacy storage panels can remain empty on
Loki 3.x with filesystem storage. The modern Loki operational dashboard remains
the primary operational view.

`dashboard-egress.yaml` registers `grafana.com:443` only in Grafana's namespace.
This permits backend dashboard downloads/import-by-ID under `REGISTRY_ONLY`.
Provisioned copies remain pinned in Git; manual import-by-ID changes are separate
from these files and can conflict with the same upstream UID. No mesh-wide
ALLOW_ANY, plugin CDN access or unrelated external hosts are enabled.

## OpenTelemetry & Tempo (23242)

Source: https://grafana.com/api/dashboards/23242/revisions/1/download
Upstream UID: `fe6ry0t5qk0zkb`, revision 1. Folder: Tempo. Datasource: Mimir.

This is an adapted lab edition, not a byte-for-byte upstream import. The original
assumes an older standalone OTel collector plus distributed Tempo, metrics-generator,
Memcached, tail sampling and a load-balancing exporter. This environment uses Alloy
and single-binary Tempo 3.1. Changes are explicit:

- Use current `otelcol_*_total` counters, Alloy process resource metrics, and job
  selectors rather than absent Kubernetes `service` labels.
- Replace Tempo ingester metrics with current live-store/block-builder metrics.
- Use the existing Alloy spanmetrics/servicegraph output (including `service_name`
  labels) rather than enabling duplicate generation inside Tempo.
- Replace unsupported cache/tail-sampler/load-balancer sections with real batch,
  queue, resource, service-graph, span-latency and query-frontend signals.
- Scope backend metrics to Tempo so remote-write panels cannot mix other backends.
- Failure/discard counters may not exist before their first event. Their panels
  derive zero only when the corresponding sent/received counter is present; if
  that telemetry disappears, no-data remains visible.

No Memcached, tail sampler, extra collector or Tempo metrics-generator was installed
just to fill panels. The existing Alloy and Tempo scrapes already collect the
necessary metrics. Span counts represent spans, not unique user requests. This
custom edition should be reviewed when upgrading Alloy/Tempo or upstream dashboard
revisions; do not overwrite it by importing the same UID manually.
