# Namespace sidecar injection with Kyverno

`kyverno-ops` installs the pinned Kyverno Helm chart. `istio-injection-ops`
installs `enable-istio-injection`. Both are discovered by the existing ops
ApplicationSet from `addons/kyverno/*/overlays/ops`.

The admission rule sets `istio-injection=enabled` on Namespace CREATE/UPDATE.
The background rule backfills existing namespaces on policy installation/update,
and subsequently reconciles them. Its target preconditions repeat the exclusion
list deliberately: admission exclusions do not constrain background targets.
Background RBAC grants only the namespace read/update/patch permissions needed.

Excluded namespaces:

- Kubernetes infrastructure: kube-system, kube-public, kube-node-lease.
- Istio control plane: istio-system (also excluded by the CNI setup).
- Kyverno: kyverno, explicitly injection-disabled to avoid a webhook dependency.
- Lab bootstrap infrastructure: argocd and local-path-storage.
- istio-gateways: keeps its revision-based gateway proxy injection; a gateway
  proxy is not an application sidecar. Do not disable injection in that namespace.

The last three categories are operational choices for this repository, not a
universal Istio exclusion list. Other namespaces, including the observability
namespaces and kiali-system, receive enabled labels. Existing explicit namespace
`istio-injection=disabled` values outside the exclusions are overwritten. Keep
GitOps namespace declarations consistent with this cluster policy.

This policy enables namespace injection, not forced pod mutation. Host-network
pods and pods explicitly opting out remain governed by Istio's injection rules.
Existing pods do not change until recreated. Roll out workloads in a controlled
order after the labels are present; do not restart all system workloads.
Kiali currently runs in excluded istio-system and must be migrated out before it
can receive a sidecar with the current CNI setup.

Deploy the updated addons project and Kyverno first, then the policy. The policy
Application retries while the CRD/webhook/RBAC become available. Check:

```sh
kubectl -n kyverno get deployments
kubectl get clusterpolicy enable-istio-injection
kubectl get namespaces -L istio-injection,istio.io/rev
kubectl create namespace injection-check --dry-run=server -o yaml
```

The dry-run namespace should have the enabled label without persisting anything.
For existing namespace convergence inspect Kyverno background-controller logs and
UpdateRequests if labels do not appear. Namespace labeling alone does not prove
that a workload has an injected proxy; inspect its newly created pods.

References:
- https://kyverno.io/docs/policy-types/cluster-policy/mutate/
- https://istio.io/latest/docs/setup/additional-setup/sidecar-injection/

The Helm values use the official `ghcr.io/kyverno` image mirror because initial
pulls from `reg.kyverno.io` failed in this Docker Desktop environment. Policy
admission defaults are explicit to avoid GitOps drift. Kustomize explicitly renders `conversion.strategy=None` on the pinned chart's CEL
policy CRDs to match Kubernetes defaulting without ignoring conversion settings.

Live validation completed: all four controllers became available; a dry-run
namespace received the enabled label; existing eligible namespaces were backfilled;
and a dry-run Pod in grafana received istio-proxy. Excluded namespace labels were
unchanged. Existing workloads still need their normal controlled rollout to inject
sidecars. ClusterPolicy is supported by the pinned release but deprecated upstream;
a future Kyverno upgrade should include migration to the CEL policy types.
