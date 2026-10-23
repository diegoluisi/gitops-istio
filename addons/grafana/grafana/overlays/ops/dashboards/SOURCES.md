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
