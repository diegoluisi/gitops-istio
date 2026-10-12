# Bookstore dev lab

`apps/bookstore/overlays/dev` is discovered by the dev directory generator and
creates Argo CD Application `bookstore-dev`, targeting namespace `bookstore`.

The base reuses the pinned Bookinfo workload template from `apps/bookinfo/base`.
It creates separate Deployments, Services, and ServiceAccounts in `bookstore`;
it does not send traffic to the running Bookinfo application.

The dev overlay owns its Namespace, ambient labels, waypoint Gateway, and ingress
VirtualService. Namespace enrollment is declared per application rather than
forced globally by the dev ApplicationSet.

Bookstore uses hostname `bookstore.local` on the existing shared ingress. This
keeps its `/productpage`, `/details`, `/static`, and API paths from colliding with
Bookinfo's routes and avoids rewriting the sample application's absolute URLs.

After Git sync:

```bash
kubectl -n argocd get application bookstore-dev
kubectl -n bookstore get pods,svc,gateway
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
| Per application namespace | Workloads, Services, ServiceAccounts, Namespace labels, waypoint, ingress routes |
| Per destination cluster | Istiod, CNI, ztunnel, Gateway API CRDs, shared ingress, shared egress definitions, tracing and metrics backends |
| Per environment | Overlay, hostname, enrollment and app policies, AppProject destination |

The HTTP trace path is the shared ingress → bookstore waypoint → bookstore
service. Ztunnel secures ambient workload connections; the waypoint processes L7
traffic. The mesh-wide tracing policy sends proxy spans to the existing Alloy
and Tempo. No second Alloy, Tempo, Grafana, or egress proxy is needed for this app.

The existing external ServiceEntry for httpbin in `default` is shared mesh
configuration, and can be used by bookstore's ambient pods. This is separate from
its namespace waypoint; creating a waypoint does not automatically route all
internet traffic through it.

Dev currently simulates a cluster using the same Kubernetes API server as ops.
On a real separate dev cluster, install the shared infrastructure there and set
the dev AppProject and ApplicationSet destination to that cluster's API server.
