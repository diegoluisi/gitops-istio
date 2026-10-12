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
The installation uses sidecar mode: base CRDs, istiod, ingress and egress gateways.
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
kubectl kustomize addons/istio-gateways/gateway/overlays/ops --enable-helm
```

Commit and push these changes to the branch watched by Argo CD. Let `argo-cd`
sync the Kustomize build option before the generated Applications switch sources.
Then `root` discovers the AppProject and ApplicationSet, and the file generator
creates the three Applications (`istio-base`, `istiod`, and `istio-gateways`). The generator reads Git,
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

To inject sidecars into lab workloads, label their namespace before creating pods:

```bash
kubectl label namespace <lab-namespace> istio-injection=enabled --overwrite
```

Restart existing pods to receive a sidecar. The Istio system namespace itself is
not labeled for injection. Change `service.type` in `gateway/base/ingress/values.yaml` to use a LoadBalancer
on clusters that provide one. Installing an egress gateway does not route outbound
traffic through it automatically; configure Gateway, VirtualService, and
ServiceEntry resources for the corresponding lab.

To add another addon, create its base, an `overlays/ops/kustomization.yaml`, and a
matching `overlays/ops/config.yaml`; no individual Application manifest is needed.

When migrating the old `istio-ingressgateway` Application in `istio-system`, wait
until both new gateways are healthy before removing the old Application and its
workloads. The ApplicationSet preserves resources when an Application disappears
from the generator, so migration cleanup is explicit.
