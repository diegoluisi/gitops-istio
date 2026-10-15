# Observability for the sidecar lab

Alloy collects Istio proxy/control-plane metrics, Kubernetes object state from
kube-state-metrics, and kubelet/cAdvisor metrics through the authenticated Kubernetes
API node proxy. The additional RBAC grants Alloy GET on nodes/proxy. Scrapes use
30-second intervals for Kubernetes and 15 seconds for Istio and monitoring backends.
All metric streams are written to Mimir. No second Prometheus server is installed.

Grafana provisions these dashboards in the Istio folder:

- Istio Sidecar Metrics: HTTP application namespace selection is based on HTTP
  metrics; scrape health has its own namespace selector.
- Istio Control Plane and Gateways: configuration delivery, proxy connections,
  certificate errors, gateway traffic, CPU/memory, and mutual TLS traffic.
- Kubernetes Workload Health: replicas, readiness, restarts, CPU/memory, PVC usage,
  node readiness and scrape health. PVC panels require kubelet volume statistics;
  local storage provisioners may not report all of them.
- Istio Traces: searches and span waterfalls from Tempo.
- Istio Logs: namespace selection and literal-text searching in Loki.

Loki is single-replica monolithic with filesystem storage on a 5Gi PVC and 72-hour
retention. Alloy tails application, mesh and observability container logs through
Kubernetes API access, using cluster, namespace, pod and container labels. Trace IDs
are not indexed as labels. Log collection is limited to the explicitly listed lab
namespaces in discovery.relabel.pod_logs; add new application namespaces there.
Retention is time-based and does not guarantee the disk cannot fill.

Alloy generates service graph and span metrics from the same Istio spans sent to
Tempo. Grafana's Tempo service map uses Mimir, and the trace-to-metrics link opens a
mesh-wide HTTP rate query. Kiali links to Grafana dashboards and Tempo in Grafana
through the existing localhost:8080/grafana/ ingressgateway-pub URL. Trace graphs depend
on propagated context and matching client/server spans; proxy telemetry does not
provide application-internal spans. Application code instrumentation remains a
separate change to the sample applications.

This is a local study setup with one Alloy instance. Scaling service graph processing
requires routing all spans of a trace to the same processor. Grafana-managed Istio alert rules are now provisioned as described below. Existing Mimir/Tempo retention remains 7 days / 24 hours.

## Grafana Istio integration alignment

Reference: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/integration-reference/integration-istio/

This installation implements the guide's collection conventions with self-hosted
Alloy, Mimir, Loki and Grafana rather than installing a Grafana Cloud integration.
Istio metrics use job=integrations/istio and instance=<namespace>-<pod>, with cluster,
namespace and pod retained. Discovery honors the actual Prometheus path/port
annotations and handles IPv4/IPv6. It limits targets to the monitoring ports,
avoiding duplicate scrapes of each proxy's other declared ports. Access logs are
already enabled through Istiod meshConfig.accessLogFile=/dev/stdout.

Proxy logs across namespaces use the same integration job/instance conventions.
The pipeline distinguishes access/system logs, extracts HTTP method, protocol,
response code and system severity, and joins multiline system messages. Other
application/observability logs remain available without proxy parsing.

The local dashboards provide system/control-plane, service, workload and log
views equivalent in purpose to the guide; they are custom GitOps dashboards, not
Grafana Cloud's bundled dashboard exports. No allowlist drops Istio metrics.

Seven Grafana-managed rules are file-provisioned under Istio/istio-integration:
latency, configuration validation, listener conflicts, xDS rejections, HTTP errors,
gRPC errors and missing/down scrape targets. The documentation names these alerts
but does not publish their expressions/thresholds. Local thresholds are p95>500ms,
HTTP/gRPC error ratio>5%, configuration errors/conflicts>0, and scrape failure;
conditions must persist for 5 minutes. The gRPC rule counts server-side status
codes 2,4,8,13,14,15. Classic conditions aggregate alert instances per rule.
Error counters may not exist until an error occurs or may vary by Istio version;
no-data is OK for these rules, while the scrape rule explicitly detects total
absence. Legacy galley_validation_failed is collected if Istiod exposes it.
Notifications are not configured: add a real Grafana contact point before expecting
email/chat delivery. The rules are visible in Grafana Alerting.
