# Bookstore dev lab

`apps/bookstore/overlays/dev` is discovered by the dev directory generator and
creates Argo CD Application `bookstore-dev`, targeting namespace `bookstore`.

The base reuses the pinned Bookinfo workload template from `apps/bookinfo/base`.
It creates separate Deployments, Services, and ServiceAccounts in `bookstore`;
it does not send traffic to the running Bookinfo application.

The dev overlay owns its Namespace, sidecar-injection labels, strict mTLS policy, and ingress
VirtualService. Namespace enrollment is declared per application rather than
forced globally by the dev ApplicationSet.

Bookstore uses hostname `bookstore.local` on the existing shared ingress. This
keeps its `/productpage`, `/details`, `/static`, and API paths from colliding with
Bookinfo's routes and avoids rewriting the sample application's absolute URLs.

After Git sync:

```bash
kubectl -n argocd get application bookstore-dev
kubectl -n bookstore get pods,svc
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
# In another terminal:
curl --resolve bookstore.local:8080:127.0.0.1 http://bookstore.local:8080/productpage
curl --resolve bookstore.local:8080:127.0.0.1 http://bookstore.local:8080/details/0
```

For browser access, resolve `bookstore.local` to `127.0.0.1` on your machine and
open `http://bookstore.local:8080/productpage`.

| Ownership | Resources |
|---|---|
| Shared source template | Pinned Bookinfo base; each app gets its own workload instances |
| Per application namespace | Workloads, Services, ServiceAccounts, Namespace labels, sidecars, ingress routes |
| Per destination cluster | Istiod, CNI, Gateway API CRDs, shared ingress, shared egress definitions, tracing and metrics backends |
| Per environment | Overlay, hostname, enrollment and app policies, AppProject destination |

The HTTP trace path is the shared ingress → bookstore sidecars → bookstore
services. Sidecars secure service connections with mTLS and process L7 traffic. The mesh-wide tracing policy sends proxy spans to the existing Alloy
and Tempo. No second Alloy, Tempo, Grafana, or egress proxy is needed for this app.

The httpbin egress lab is now owned by Bookinfo, with routing through the shared egress gateway
and namespace network policies. Bookstore does not inherit Bookinfo's
egress restriction; it needs its own external-service and policy decisions.

Dev currently simulates a cluster using the same Kubernetes API server as ops.
On a real separate dev cluster, install the shared infrastructure there and set
the dev AppProject and ApplicationSet destination to that cluster's API server.
