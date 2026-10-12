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
`prometheus-ops`. Kiali Operator `2.26.0` manages the Kiali instance in
`istio-system`; Prometheus uses the official Istio `1.30.3` sample addon with
Istio telemetry scraping. This is a lab metrics backend with ephemeral storage.
Kiali is read-only, with anonymous authentication for local port-forward access.
Grafana and tracing integrations are disabled because those services are not
installed. The ops overlay routes `/kiali` and `/kiali/` through
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

Allow a few Prometheus scrape intervals for graph edges to appear. Ztunnel reports
ambient traffic as TCP. HTTP metrics for service-to-service requests require a
waypoint in the application's namespace; the waypoint in `default` does not
serve `bookinfo`. The shared ingress itself also emits HTTP metrics.
