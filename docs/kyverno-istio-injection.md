# Namespace sidecar injection with Kyverno

`kyverno-ops` installs the pinned chart and the CEL `MutatingPolicy`
`istio-injection`, stored at
`addons/kyverno/kyverno/base/policies/istio/istio-injection.yaml` and listed in the
base Kustomization. The deprecated ClusterPolicy and separate policy Application
have been retired.

The policy sets `istio-injection=enabled` on Namespace CREATE/UPDATE and enables
background mutation of existing namespaces. Admission and target resource rules
repeat the same exclusions, so background mutation cannot label infrastructure
namespaces accidentally. The background controller has namespace get/list/watch/
update/patch permissions. The policy syncs after controller resources (wave 10).

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

Deploy kyverno-ops; the policy is included in the same Application. Check:

```sh
kubectl -n kyverno get deployments
kubectl get mutatingpolicy istio-injection
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
admission defaults are explicit to avoid GitOps drift. Kustomize removes empty `metadata.labels` maps emitted on the pinned chart's CEL
policy CRDs. Kubernetes drops those empty maps, which otherwise causes persistent
Argo CD drift. No CRD schema or conversion settings are ignored.

Live validation completed: all four controllers became available; a dry-run
namespace received the enabled label; existing eligible namespaces were backfilled;
and a dry-run Pod in grafana received istio-proxy. Excluded namespace labels were
unchanged. Existing workloads still need their normal controlled rollout to inject
sidecars. The CEL policy uses policies.kyverno.io/v1, avoiding the deprecated ClusterPolicy API.

## Monitoring

Alloy scrapes all four Kyverno metrics Services on port 8000 every 15 seconds,
using registered Service DNS addresses compatible with REGISTRY_ONLY. Metrics use
job `integrations/kyverno`, controller, cluster and namespace labels. The Grafana
Kyverno Overview dashboard uses Mimir and covers scrape health, admission requests
and p95 latency, policy outcomes and latency, active rules, API deprecations,
controller reconciliations, CPU, memory, goroutines and API client traffic.

Event counters may be absent until a matching event occurs. Historical deprecated
API requests remain visible within the selected range after migration. Static
Service scraping matches this lab's single-replica controllers; switch to
per-endpoint discovery when scaling controllers to multiple replicas.
