# gitops-istio
GitOps for Istio ICA Tests

## Istio addons

The Autopilot `root` Application reads `projects/addons.yaml`, which defines the
`addons` AppProject and the cluster-specific `ops` ApplicationSet using the Git
**directory** generator.
It matches `addons/*/*/overlays/ops` and generates one Application
per addon targeting the `ops` cluster (currently Docker Desktop / in-cluster).
The gateway chart renders separate ingress and egress releases in `istio-gateways`.

```text
addons/
  istio-system/
    base/
      base/
        kustomization.yaml
        values.yaml
      overlays/
        ops/
          kustomization.yaml
    istiod/                  # same base/ and overlays/ops/ layout
    cni/                     # ambient CNI node agent
    ztunnel/                 # ambient node proxy
  istio-gateways/
    gateway/
      base/
        kustomization.yaml
        ingress/values.yaml
        egress/values.yaml
      overlays/ops/
        kustomization.yaml
```

The generator discovers overlay folders directly; no `config.yaml` is needed.
It derives the addon name from the chart folder (`{{ index .path.segments 2 }}`),
the cluster label and Application suffix from the overlay folder
(`{{ .path.basename }}`), and the destination namespace from the first folder
under `addons/` (`{{ index .path.segments 1 }}`). The source path is the matched
overlay directory (`{{ .path.path }}`). The `ops` ApplicationSet sets its
Kubernetes API server once in `spec.template.spec.destination.server`.

Shared bases render the official Istio Helm charts, pinned to `1.30.3`, with
`values.yaml`. The `ops` overlays reference their bases. All gateway configuration
is in Helm values, without Kustomize patches: ingress uses NodePort for the local
lab, and egress uses ClusterIP. Their `istio: ingressgateway` and
`istio: egressgateway` labels support selectors in Istio Gateway resources.
The installation uses ambient mode: base CRDs, istiod with `profile: ambient`,
Istio CNI with `profile: ambient`, and the ztunnel DaemonSet. All components use
version `1.30.3`. Workload traffic is redirected to ztunnel without an application
sidecar. Ingress and egress remain standalone Envoy gateway deployments.
Argo CD creates `istio-gateways` through `CreateNamespace=true`. Gateway pods opt
into gateway injection through the chart's pod annotations; the namespace does
not need a general sidecar-injection label.
The base chart leaves `defaultRevision` empty to avoid introducing a validator
that needs istiod before the control plane exists.

Argo CD renders these Helm charts through Kustomize, so `argocd-cm` must contain
`kustomize.buildOptions: --enable-helm`. This is configured declaratively in
`bootstrap/argo-cd/install.yaml`. The generated Applications preserve webhook
certificate and failure policy fields managed by Istio and retry initial syncs.
ApplicationSet Applications reconcile independently; they do not have an ordered
installation guarantee. On an empty cluster, the retry policy allows resources
to converge as CRDs and the control plane become available.

Validate each overlay locally (requires Helm and access to the chart repository):

```bash
kubectl kustomize addons/istio-system/base/overlays/ops --enable-helm
kubectl kustomize addons/istio-system/istiod/overlays/ops --enable-helm
kubectl kustomize addons/istio-system/cni/overlays/ops --enable-helm
kubectl kustomize addons/istio-system/ztunnel/overlays/ops --enable-helm
kubectl kustomize addons/istio-gateways/gateway/overlays/ops --enable-helm
```

Commit and push these changes to the branch watched by Argo CD. Let `argo-cd`
sync the Kustomize build option before the generated Applications switch sources.
Then `root` discovers the AppProject and `ops` ApplicationSet. The directory generator
creates `base-ops`, `istiod-ops`, `cni-ops`, `ztunnel-ops`,
`gateway-ops`, `gateway-api-ops`, and `waypoint-ops`. The generator reads Git, so local edits must be pushed before
they affect reconciliation.

For another cluster, create a separate ApplicationSet named after that cluster,
match its `overlays/<cluster>` folders. The folder name automatically
sets the cluster label and Application suffix. Set that ApplicationSet's destination server
and register/allow that server in Argo CD and the AppProject.

Renaming the existing `addons` ApplicationSet and its Applications is a migration,
not an in-place Kubernetes rename. Retire the old Applications while preserving
their workloads before allowing the new names to reconcile, to avoid concurrent
controllers managing the same resources. `preserveResourcesOnDeletion: true`
keeps workloads when the old ApplicationSet is removed.

```bash
kubectl -n argocd get applicationsets,applications
kubectl -n istio-system get pods,svc
kubectl -n istio-gateways get pods,svc
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
```

The `default` namespace is enrolled declaratively by
`bootstrap/cluster-resources/in-cluster/default-ns.yaml`, with
`istio.io/dataplane-mode: ambient` and `istio-injection: disabled`.
Infrastructure namespaces (`argocd`, `istio-system`, `istio-gateways`, and
`kube-system`) are not enrolled. For another application namespace:

```bash
kubectl label namespace <lab-namespace> istio-injection=disabled --overwrite
kubectl label namespace <lab-namespace> istio.io/rev-
kubectl label namespace <lab-namespace> istio.io/dataplane-mode=ambient --overwrite
```

Also remove workload-level injection labels/annotations and revision labels when
migrating existing workloads. Existing sidecar pods must be recreated after
removing injection settings; adding an ambient label alone does not remove their
sidecars. Pods already running without sidecars can enroll without a restart.
Do not disable the gateway chart's gateway-template injection: it constructs a
standalone gateway proxy, not a sidecar added to an application pod.

Verify the ambient components after Git sync:

```bash
kubectl -n istio-system rollout status deployment/istiod
kubectl -n istio-system rollout status daemonset/istio-cni-node
kubectl -n istio-system rollout status daemonset/ztunnel
kubectl get namespace default --show-labels
kubectl -n default get pods -o custom-columns='NAME:.metadata.name,CONTAINERS:.spec.containers[*].name'
```

Application pods should have only their application containers. For HTTP routing
and Layer 7 authorization inside the ambient mesh, add a shared waypoint and the
Gateway API CRDs when needed; neither is required for ztunnel's Layer 4 mesh.

Change `service.type` in `gateway/base/ingress/values.yaml` to use a LoadBalancer
on clusters that provide one. Installing an egress gateway does not route outbound
traffic through it automatically; configure Gateway, VirtualService, and
ServiceEntry resources for the corresponding lab.

To add another addon, create its base and an `overlays/ops/kustomization.yaml`.
The directory generator discovers it automatically; no config or individual
Application manifest is needed.

When migrating the old `istio-ingressgateway` Application in `istio-system`, wait
until both new gateways are healthy before removing the old Application and its
workloads. The ApplicationSet preserves resources when an Application disappears
from the generator, so migration cleanup is explicit.

## GitOps waypoint for Layer 7

`gateway-api-ops` manages the pinned Gateway API `v1.5.1` standard CRDs from
`addons/istio-system/gateway-api`. `waypoint-ops` manages a Gateway in `default`
from `addons/default/waypoint`. Both follow the base/overlays/ops structure and
are discovered by the `ops` ApplicationSet. The Gateway uses the
`istio-waypoint` class, HBONE listener on port 15008, and
`istio.io/waypoint-for: service`. Istiod creates its Deployment and Service.

The namespace manifest in `bootstrap/cluster-resources/in-cluster/default-ns.yaml`
enrolls `default` using `istio.io/use-waypoint: waypoint`. Ambient traffic addressed
to Services in this destination namespace passes through the shared waypoint,
without adding sidecars to application pods. Direct Pod-IP traffic is outside
this service-only waypoint's scope. Ingress-to-waypoint routing requires separate
Istiod configuration and service enrollment.

Push these manifests to enable reconciliation. The existing retry policy and
`SkipDryRunOnMissingResource=true` allow waypoint sync to converge when the
Gateway API CRDs arrive. Applications reconcile independently, so check the CRDs
and waypoint readiness after sync:

```bash
kubectl -n argocd get applications gateway-api-ops waypoint-ops
kubectl -n default wait gateway/waypoint --for=condition=Programmed --timeout=180s
kubectl -n default rollout status deployment/waypoint
kubectl get namespace default --show-labels
```

An optional GET-only L7 authorization example lives in
`examples/waypoint/allow-get.yaml`. To manage it through GitOps, add it to the
waypoint base directory and list it in that base's Kustomization. It is not enabled
by default because it restricts HTTP methods for every Service using the waypoint.
Waypoint authorization uses `targetRefs`, not workload selectors. For a specific
Service, attach the policy to that Service instead. Policies only enforce traffic
that reaches the waypoint; pair with Layer 4 authorization if bypass prevention
is required.

## Simulated dev cluster: Bookinfo

`projects/dev.yaml` defines the `dev` AppProject and ApplicationSet. Its Git
directory generator matches `apps/*/overlays/dev`. For
`apps/bookinfo/overlays/dev`, folder names generate:

- Application: `bookinfo-dev`
- Namespace: `bookinfo`
- Cluster label: `dev`

This simulates dev on the same Kubernetes API server as ops
(`https://kubernetes.default.svc`); it does not create a separate cluster. For a
real dev cluster, register it in Argo CD and update both the project destination
and the ApplicationSet destination server.

Bookinfo's base references the official sample pinned to Istio `1.30.3`. Its dev
overlay sets the namespace. Argo CD creates `bookinfo` and labels it for ambient
mode with sidecar injection disabled. This namespace does not inherit the
`default` namespace's waypoint: add a waypoint and enrollment in `bookinfo` when
you need Layer 7 processing there.

After pushing and Git reconciliation:

```bash
kubectl -n argocd get applicationset dev
kubectl -n argocd get application bookinfo-dev
kubectl -n bookinfo get pods,svc
kubectl -n bookinfo port-forward svc/productpage 9080:9080
```

Open `http://localhost:9080/productpage`. Bookinfo needs the ambient components
installed in the destination cluster; a real dev cluster needs its own Istio
installation.

## Shared ingress

`addons/istio-gateways/gateway/base/shared-gateway.yaml` defines one Istio
`networking.istio.io/v1` Gateway named `shared-ingress`. It selects the existing
`istio: ingressgateway` pods and accepts HTTP on port 80. It is independent of
the ambient waypoint Gateway.

Applications define their own VirtualServices in their namespaces and reference
`istio-gateways/shared-ingress`. Bookinfo's dev overlay exposes `/details`
(rewritten to `/details/0`), `/details/<id>`, and `/productpage` with its supporting
static, login, logout, and API paths. Adding another application requires its
VirtualService with non-overlapping paths or a separate hostname; no additional
ingress Deployment is needed.

After Git sync:

```bash
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
# In another terminal:
curl http://localhost:8080/details
curl http://localhost:8080/details/0
curl http://localhost:8080/productpage
```

This dev lab uses wildcard hosts and HTTP. Configure specific hosts and TLS when
exposing it outside the local lab. A real dev cluster needs its own shared ingress
Gateway and ingress pods; these cross-namespace references stay within one cluster.

## Kiali traffic visualization

The ops directory generator discovers `kiali-operator-ops`, `kiali-ops`, and
`mimir-ops`. Kiali Operator `2.26.0` runs in `kiali-system` and manages the Kiali instance in
`istio-system`; Alloy scrapes Istio telemetry and remote-writes to Mimir, the lab metrics
backend with persistent storage.
Kiali is read-only, with anonymous authentication for local port-forward access.
Kiali queries Tempo for traces. Grafana has provisioned Tempo and Mimir datasources. The ops overlay routes `/kiali` and `/kiali/` through
`istio-gateways/shared-ingress` to Kiali on port 20001, without rewriting the path.
Using the ingress port-forward on port 8080, open `http://localhost:8080/kiali/`.
Kiali retains anonymous, read-only access for this lab.

```bash
kubectl -n istio-system port-forward svc/kiali 20001:20001
```

Open `http://localhost:20001/kiali`, select `bookinfo` in Traffic Graph, enable TCP
traffic, and use a recent time window (for example, Last 5 minutes). Generate
requests through the ingress in another terminal:

```bash
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
# In another terminal:
for i in $(seq 1 60); do
  curl -fsS http://localhost:8080/productpage > /dev/null
  sleep 1
done
```

Allow a few Alloy scrape intervals for graph edges to appear. Ztunnel reports
ambient traffic as TCP. HTTP metrics for service-to-service requests require a
waypoint in the application's namespace; the waypoint in `default` does not
serve `bookinfo`. The shared ingress itself also emits HTTP metrics.

The gateway namespace is associated with the default Istio control-plane revision
by `bootstrap/cluster-resources/in-cluster/istio-gateways-ns.yaml`
(`istio.io/rev: default`). It stays outside ambient capture with
`istio.io/dataplane-mode: none`. This lets Kiali include shared Gateways when
validating cross-namespace VirtualService references. An unlabeled gateway
namespace can produce a false KIA1102 warning even while ingress routing works.

## Restricted Bookinfo egress

Bookinfo's dev overlay owns `httpbin-egress`, a ServiceEntry for `httpbin.org:80`,
and `egress-waypoint`, a dedicated waypoint in namespace `bookinfo`. The entry
is scoped with `exportTo: ["."]` and selects the egress waypoint explicitly.
The original `default` namespace entry is removed; its general waypoint remains.

The egress waypoint ALLOW policy accepts HTTP host `httpbin.org` (including its
explicit `:80` form). Bookinfo's egress NetworkPolicies allow workloads to reach
DNS, Istiod, Alloy tracing, and Bookinfo services/waypoints. Direct internet access
is blocked. Only the egress waypoint can open external TCP port 80 connections;
its HTTP authorization limits requests to httpbin. HTTPS to httpbin is not enabled
in this HTTP lab. These policies require NetworkPolicy enforcement; the installed
kindnetd supports it. Internal Bookinfo traffic and ingress remain available.

After Git sync:

```bash
kubectl -n bookinfo rollout status deployment/egress-waypoint
kubectl -n bookinfo exec deployment/productpage-v1 -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://httpbin.org/get", timeout=10).status)'
# Expected: timeout / denied direct outbound access
kubectl -n bookinfo exec deployment/productpage-v1 -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("https://github.com", timeout=5).status)'
kubectl -n bookinfo logs deployment/egress-waypoint --since=2m | grep httpbin
```

The policies preserve Bookinfo's current port 9080 internal dependencies. Add
specific internal destinations/ports when the app acquires new dependencies.
This restriction applies to Bookinfo workloads; it does not impose a global
internet allowlist on the other application or infrastructure namespaces.


## Tracing: Istio → Alloy → Tempo → Grafana

The ops ApplicationSet manages these namespace/chart folders:

- `addons/kiali-system/kiali-operator`: operator moved from `istio-system`;
  the Kiali server and CR remain in `istio-system`.
- `addons/tempo/tempo`: single-binary Tempo with a 5Gi PVC and 24-hour retention.
- `addons/grafana/grafana`: Grafana with a 2Gi PVC, provisioned Tempo datasource
  (`uid: tempo`), and the Mimir datasource.
- `addons/alloy/alloy`: one collector Deployment receiving OTLP gRPC on 4317 and
  HTTP on 4318, batching traces, then exporting to `tempo.tempo:4317`.

Istiod's Helm values enable tracing and register the `alloy` OpenTelemetry
extension provider. A root-namespace Telemetry resource enables 100% sampling
for this lab. Gateway and waypoint Envoy proxies export spans to Alloy; ztunnel
provides Layer 4 telemetry and does not generate HTTP spans.

Bookinfo's dev overlay creates its own waypoint. Its Namespace manifest
labels the application namespace with `istio.io/use-waypoint: waypoint` and
`istio.io/ingress-use-waypoint: true`. Istiod enables ingress waypoint routing,
so Bookinfo requests entering through the shared ingress also traverse the
Bookinfo waypoint. Internal calls get L7 tracing without application sidecars.
Applications must propagate trace headers to join calls into one distributed
trace; proxy instrumentation alone does not instrument application code.

Grafana uses anonymous Editor access (including Explore and dashboard editing) and disables creation of the initial admin
account for this local lab. No Grafana credentials are stored in Git. Access it
with a local port-forward:

```bash
kubectl -n grafana port-forward svc/grafana 3000:80
```

Open `http://localhost:3000/grafana/`, go to Explore, select Tempo, and search recent traces.
Generate requests through `http://localhost:8080/productpage` using the existing
shared ingress port-forward. Kiali's Traces view also queries the Tempo HTTP API.

```bash
kubectl -n kiali-system get pods
kubectl -n tempo get pods,pvc
kubectl -n grafana get pods,pvc
kubectl -n alloy get pods,svc
kubectl -n bookinfo get gateway waypoint
kubectl -n alloy logs deployment/alloy --since=5m
```

The Kiali operator migration keeps its Argo CD Application name
`kiali-operator-ops`. Once Git sync changes its destination to `kiali-system`,
Retire the former operator Deployment and ServiceAccount from `istio-system`
after the new operator is ready, preserving the Kiali CR and the cluster-scoped
CRD. Existing Bookinfo namespace enrollment is also enforced by an explicit
Namespace manifest. Waypoint tracing uses a root Telemetry policy targeting the
`istio-waypoint` GatewayClass. A default
StorageClass is required for the Tempo and Grafana PVCs.

Grafana is also exposed through `istio-gateways/shared-ingress` at
`http://localhost:8080/grafana/`. Its ops VirtualService preserves the subpath;
Helm values set `server.root_url` and `serve_from_sub_path` so assets, API calls,
and redirects use `/grafana/`. The public URL is configured for the local ingress
port-forward on 8080; update `root_url` when deploying to a real hostname.

## Second application: bookstore

`apps/bookstore/overlays/dev` demonstrates reuse of the Bookinfo base with
independent resources in namespace `bookstore`. Its Application is `bookstore-dev`
and its ingress hostname is `bookstore.local`. It has its own waypoint, while
reusing cluster ingress, egress, Istio, and observability infrastructure.
See `apps/bookstore/README.md` for the ownership table and test commands.
Both app namespaces own their ambient/waypoint labels explicitly; the dev
ApplicationSet no longer imposes waypoint enrollment on every discovered app.

## Mimir metrics and Istio dashboard

The Prometheus server is replaced by Mimir `3.2.1` in namespace `mimir`.
`addons/mimir/mimir` deploys a single-process lab instance using the classic
ingestion architecture, local filesystem storage on a 5Gi PVC, and 7-day
retention. Multi-tenancy is disabled for this local lab. This is not an HA
production deployment; a production installation should use distributed Mimir
and object storage.

Alloy retains the OTLP trace pipeline to Tempo and adds Kubernetes pod discovery
for annotated Istio metrics endpoints. It scrapes Istiod, ztunnel, gateway proxies,
and waypoints every 15 seconds and remote-writes to Mimir `/api/v1/push`.
Grafana's `Mimir` datasource and Kiali query Mimir's Prometheus-compatible API
at `/prometheus`. Kiali uses its proxy compatibility mode with explicit scrape
interval and retention because Mimir does not expose Prometheus server config.

The provisioned **Istio Ambient Metrics** dashboard lives in
`addons/grafana/grafana/overlays/ops/dashboards/istio-ambient.json`. A generated
ConfigMap and Grafana's dashboard sidecar provision it under the **Istio** folder.
Open `http://localhost:8080/grafana/d/istio-ambient-overview/` after Git sync.
Choose the application namespace to view HTTP request rates, 5xx percentages,
p95 latency, TCP bytes, connection rates, and scrape target health. HTTP panels
need waypoint/ingress traffic; TCP panels use ztunnel metrics. Reporter series
are displayed separately to distinguish multiple observation points.

The old Prometheus datasource is removed during Grafana provisioning. Existing
Prometheus history is not migrated. Retire the old `prometheus-ops` Application
and its server resources only after Mimir ingestion and Kiali/Grafana queries
are verified; the ops ApplicationSet preserves resources on deletion.

## Istio tracing dashboard

The provisioned **Istio Traces** dashboard is defined in
`addons/grafana/grafana/overlays/ops/dashboards/istio-traces.json` and appears
under Grafana's **Istio** folder. Open `/grafana/d/istio-traces/` through the
shared ingress. It queries the existing Tempo datasource for recent, slow,
and error traces. Filter with a service-name regex such as `.*bookinfo.*` and
change the slow-span threshold (default `100ms`). Select **View span waterfall**
on a table result, or paste its Trace ID into the variable, to inspect its spans.
The waterfall needs a selected Trace ID. Generate traffic to `/productpage` or
`/details/1`, then refresh if no traces appear in the selected time range.
Tempo retains traces for 24 hours. Slow/error tables match individual spans;
Istio gateways and waypoints emit these traces, while ztunnel supplies L4 metrics.
