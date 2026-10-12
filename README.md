# gitops-istio
GitOps for Istio ICA Tests

## Istio addons

The Autopilot `root` Application reads `projects/addons.yaml`, which defines the
`addons` AppProject and an ApplicationSet using the Git **file** generator.
It matches `addons/*/*/overlays/ops/config.yaml` and generates one Application
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
          config.yaml
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
        config.yaml
        kustomization.yaml
```

Each overlay's `config.yaml` supplies the Application name, cluster label, and
Kubernetes API server. The generator derives the destination namespace from the
first folder under `addons/` (`{{ index .path.segments 1 }}`), and the source path
from the configuration file's directory. These files are generator inputs, not Kubernetes
resources, and are not included in the overlay's Kustomization.

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
Then `root` discovers the AppProject and ApplicationSet, and the file generator
creates five Applications (`istio-base`, `istiod`, `istio-cni`, `ztunnel`, and
`istio-gateways`). The generator reads Git,
so applying the ApplicationSet locally before pushing these files will not
migrate the running Applications. The initial live `istio-gateways` Application
uses the same two Helm releases in the `default` project until this Git update is
pushed; the ApplicationSet then adopts it and switches it to the Kustomize source
and `addons` project.

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

To add another addon, create its base, an `overlays/ops/kustomization.yaml`, and a
matching `overlays/ops/config.yaml`; no individual Application manifest is needed.

When migrating the old `istio-ingressgateway` Application in `istio-system`, wait
until both new gateways are healthy before removing the old Application and its
workloads. The ApplicationSet preserves resources when an Application disappears
from the generator, so migration cleanup is explicit.
