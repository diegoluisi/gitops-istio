# Kubernetes metrics collectors and metric hygiene

## Collectors

| Component | Purpose | Historical Grafana data |
|---|---|---|
| metrics-server | Kubernetes resource metrics API for `kubectl top` and HPA | Not a historical monitoring backend; cAdvisor supplies CPU/memory history |
| kube-state-metrics (existing) | Kubernetes object state, requests/limits, readiness | `job="kube-state-metrics"` |
| kubelet (existing) | Kubelet/runtime/volume operations | `job="kubernetes-kubelet"` |
| cAdvisor (existing, embedded in kubelet) | Per-container CPU, memory, throttling, network | `job="kubernetes-cadvisor"` |
| prometheus-node-exporter | Node CPU, memory, filesystems, disk and networking | `job="kubernetes-node-exporter"` |
| API server | API request rates, errors, latency, in-flight requests | `job="kubernetes-apiserver"` |
| CoreDNS | DNS requests, response codes and latency per replica | `job="kubernetes-coredns"` |

There is no second cAdvisor DaemonSet: the kubelet endpoint already provides it.
Metrics-server does not replace Prometheus-compatible historical collection.
Scheduler, controller-manager and etcd scraping is not enabled because their
secured endpoints are not configured for this monitoring client.

New Helm addons follow `addons/kube-system/<chart>/overlays/ops` and are discovered
by the existing ApplicationSet. Metrics-server chart 3.14.0 runs v0.9.0;
node-exporter chart 4.60.1 runs v1.12.1. Node-exporter is a DaemonSet and uses the
chart's host mounts/network/PID defaults to inspect the node. On Docker Desktop
this means the Linux Kubernetes VM, **not the macOS host**.

The ops metrics-server Helm values include `--kubelet-insecure-tls` for the local
Docker Desktop kubelet certificate. The reusable base omits that exception. For
production, use properly trusted serving certificates and remove the local flag.
The ops values are self-contained because Kustomize Helm values cannot read
outside their root with Argo CD's default load restrictions.

## Scraping and permissions

Alloy uses its service-account token and cluster CA to scrape API server metrics.
Node-exporter and CoreDNS targets are discovered per pod and scraped through
`/api/v1/namespaces/kube-system/pods/http:<pod>:<port>/proxy/metrics`. This preserves
per-node/per-replica identity without sending HTTP to unregistered pod IPs under
Istio `REGISTRY_ONLY`. It adds API-server proxy load; the 30-second interval is
appropriate for this small lab. A larger cluster should use dedicated collectors
with an explicit network/authentication design rather than routing all telemetry
through the API server.

RBAC adds `GET /metrics` plus a kube-system Role granting `get pods/proxy` to
`alloy/alloy`. Pod proxy access can reach pod HTTP endpoints beyond metrics, so it
is a privileged monitoring capability; it is scoped to kube-system. Existing
`nodes/proxy` permissions support the kubelet/cAdvisor scrapes.

## Dashboards

Grafana's **Kubernetes** folder now includes:

- Kubernetes Cluster Overview: resource requests, readiness, pod phases, restarts
  and collector availability.
- Kubernetes Nodes: CPU, memory, load, filesystem usage, disk I/O and network.
- Kubernetes Containers & Workloads: CPU, working set, throttling, requests and
  waiting/termination reasons.
- Kubernetes API & DNS: API rates/errors/latency, DNS rates/errors/latency and
  collector scrape durations.
- Existing Kubernetes Health dashboard remains available.

Some runtime-dependent metrics (for example PVC volume stats) can be absent on
Docker Desktop. Missing data is not zero. All new queries use the existing Mimir
UID; no extra Prometheus instance or datasource is installed.

## Shared metrics filter

Every metric producer forwards to `prometheus.relabel.metrics_hygiene` before
`prometheus.remote_write.mimir`. Logs and traces are unaffected.

The explicit drop rule removes unused `gc_*`, selected detailed `go_gc_*` families,
and GC-specific `go_memstats_*` series. It deliberately **retains**:

- `go_gc_duration_seconds` quantiles used by the Argo CD dashboard.
- `go_gc_duration_seconds_count` used by Alloy's Resources dashboard.
- Process CPU, memory, container/node metrics, telemetry health and Istio counters.

GC data is not intrinsically garbage; it helps diagnose application/runtime
pressure. This denylist is a lab dependency-based selection, not a universal
recommendation. User ad-hoc queries and dashboards outside Git must be considered
before broadening it. Historical discarded series stay in Mimir until retention
expires; filtering only stops new samples.

Run before changing the filter or adding dashboards:

```sh
python3 scripts/check-metric-filter.py
```

The test checks referenced metric tokens across checked-in dashboards, recording
rules and Grafana alerts, protects known required metrics, and verifies that only
the filter forwards directly to Mimir. It cannot detect dynamically constructed
metric names or requirements of future external consumers.

## Verification

```sh
kubectl get apiservice v1beta1.metrics.k8s.io
kubectl top nodes
kubectl top pods -n bookinfo
kubectl -n kube-system rollout status daemonset/node-exporter
```

In Grafana Explore / Mimir:

```promql
up{job=~"kube-state-metrics|kubernetes-cadvisor|kubernetes-kubelet|kubernetes-node-exporter|kubernetes-apiserver|kubernetes-coredns"}
```

Confirm node-exporter, container CPU, API request and DNS request series have data.
Alloy's `prometheus_relabel_metrics_processed` and
`prometheus_relabel_metrics_written` self-metrics show samples passing through the
filter; the difference indicates drops (when exposed by the installed version).
Check exporter `/metrics` versus new timestamps in Mimir to verify a specific
filtered family. Existing samples can remain visible during lookback/retention.

References:
- https://github.com/kubernetes-sigs/metrics-server
- https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.relabel/
- https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/
