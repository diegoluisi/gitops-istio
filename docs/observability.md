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
through the existing localhost:8080/grafana/ shared-ingress URL. Trace graphs depend
on propagated context and matching client/server spans; proxy telemetry does not
provide application-internal spans. Application code instrumentation remains a
separate change to the sample applications.

This is a local study setup with one Alloy instance. Scaling service graph processing
requires routing all spans of a trace to the same processor. No alerting is installed
by this change. Existing Mimir/Tempo retention remains 7 days / 24 hours.
