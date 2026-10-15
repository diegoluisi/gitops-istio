# Direct access through ingressgateway-pub

The Istio Gateway ingressgateway-pub in namespace istio-gateways selects the
existing istio-ingressgateway deployment. The Helm release and Service keep their
names. Its LoadBalancer Service publishes HTTP port 8080 to Envoy port 8080;
the Istio Gateway listener uses the same port. Docker Desktop exposes this outside
the cluster on the local host. No kubectl port-forward or separate tunnel is needed.

Ports 80 and 443 on this machine belong to the separate k8s-demo cluster, so this
cluster uses port 8080. On another Kubernetes environment, the LoadBalancer Service
requires that environment's load-balancer implementation and assigned address.

| Application | Direct URL |
|---|---|
| Bookinfo | http://localhost:8080/productpage |
| Bookinfo details | http://localhost:8080/details/1 |
| Grafana | http://localhost:8080/grafana/ |
| Kiali | http://localhost:8080/kiali/ |
| Bookstore | http://bookstore.local:8080/productpage |
| Preserved AWX instance | http://awx.localhost:8080/ |

Bookstore requires bookstore.local to resolve to 127.0.0.1 on the local machine.
Browsers normally resolve awx.localhost locally; a hosts entry can be used if needed.
AWX is currently archived under .old/ and not rediscovered as a GitOps application;
its preserved live VirtualService is updated to the new Gateway as part of this
migration. The archived route reference is updated without restoring the addon.
Use HTTP: no TLS certificate or HTTPS listener is configured by this change.

```bash
kubectl -n istio-gateways get svc istio-ingressgateway
curl http://localhost:8080/productpage
curl --resolve bookstore.local:8080:127.0.0.1 http://bookstore.local:8080/productpage
curl --resolve awx.localhost:8080:127.0.0.1 http://awx.localhost:8080/api/v2/ping/
```

If a manually started port-forward already occupies local port 8080, stop it before
using the LoadBalancer. Keep Docker Desktop and its Kubernetes cluster running.
