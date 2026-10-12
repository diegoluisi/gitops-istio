# gitops-istio
GitOps for Istio ICA Tests

## Istio addons

The Autopilot `root` Application reads `projects/addons.yaml`, which defines the
`addons` AppProject and an ApplicationSet using the Git **file** generator.
It matches `addons/*/*/overlays/ops/config.yaml` and generates one Application
per addon targeting the `ops` cluster (currently Docker Desktop / in-cluster).
The existing Application names are preserved for migration.

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
    gateway/                 # same base/ and overlays/ops/ layout
```

Each overlay's `config.yaml` supplies the Application name, namespace, cluster
label, and Kubernetes API server. The generator derives the source path from the
configuration file's directory. These files are generator inputs, not Kubernetes
resources, and are not included in the overlay's Kustomization.

Shared bases render the official Istio Helm charts, pinned to `1.30.3`, with
`values.yaml`. The `ops` overlays reference their bases and hold cluster-specific
patches. The gateway overlay changes the service to NodePort for the local lab.
The installation uses sidecar mode: base CRDs, istiod, and an ingress gateway.
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
kubectl kustomize addons/istio-system/gateway/overlays/ops --enable-helm
```

Commit and push these changes to the branch watched by Argo CD. Let `argo-cd`
sync the Kustomize build option before the generated Applications switch sources.
Then `root` discovers the AppProject and ApplicationSet, and the file generator
creates or adopts the three existing Applications. The generator reads Git,
so applying the ApplicationSet locally before pushing these files will not
migrate the running Applications.

```bash
kubectl -n argocd get applicationsets,applications
kubectl -n istio-system get pods,svc
kubectl -n istio-system port-forward svc/istio-ingressgateway 8080:80
```

To inject sidecars into lab workloads, label their namespace before creating pods:

```bash
kubectl label namespace <lab-namespace> istio-injection=enabled --overwrite
```

Restart existing pods to receive a sidecar. The Istio system namespace itself is
not labeled for injection. Change or remove the gateway's overlay patch to use a
LoadBalancer on clusters that provide one.

To add another addon, create its base, an `overlays/ops/kustomization.yaml`, and a
matching `overlays/ops/config.yaml`; no individual Application manifest is needed.
