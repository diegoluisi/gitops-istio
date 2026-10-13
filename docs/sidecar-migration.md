# Ambient to sidecar migration

Bookinfo and Bookstore enable `istio-injection: enabled`. Istiod enables
CNI integration; Istio CNI keeps configuring pod traffic but disables ambient.
Bookinfo and Bookstore enforce STRICT mutual TLS. Their deployment templates
have a migration annotation to trigger recreation with an injected `istio-proxy`.
The mesh-wide Telemetry still sends traces to Alloy and Tempo. Alloy discovers
sidecar metrics through Istio's Prometheus annotations; Mimir and Grafana remain.
The metrics dashboard keeps its existing UID/URL, with title Istio Sidecar Metrics.

Bookinfo's ServiceEntry exports httpbin.org to Bookinfo and istio-gateways. Its
VirtualService routes sidecar HTTP requests to the shared egress gateway using
ISTIO_MUTUAL from the DestinationRule. The gateway's HTTPS listener terminates
mesh mutual TLS, then the VirtualService forwards HTTP to httpbin.org:80.
The egress AuthorizationPolicy allows only Bookinfo service-account identities,
HTTP host httpbin.org, and the gateway's workload port 8080. NetworkPolicy allows
Bookinfo pods to reach that gateway port, their namespace on 9080, DNS, Istiod,
and Alloy; direct internet access remains blocked. The shared egress gateway's
NetworkPolicy permits external TCP 80 plus DNS, Istiod, and Alloy.

## Deployment order

ApplicationSets reconcile independently, so a Git commit is not a cross-application
ordering guarantee. During deployment, wait for the sidecar-ready Istiod and CNI
before rolling applications. Explicitly remove old ambient/waypoint labels from
bookinfo and bookstore if they remain live (for example from manual
labeling). Injection applies only to newly created pods. Verify every application
pod has istio-proxy; restart deployments if necessary.

The ApplicationSet preserves resources on Application deletion. Removing the
ztunnel and default waypoint folders does not automatically delete their live
resources. Keep ztunnel until no ambient workloads remain, then remove its captured
Argo-managed resources and the default waypoint Gateway. App-owned waypoints are
pruned by their existing Applications. Gateway API CRDs were subsequently removed after verifying that no Gateway API
Gateways, routes, or ReferenceGrants remained. The active gateways use Istio CRDs.
Injection is disabled in the unused default namespace.

## Validation

```bash
kubectl -n bookinfo get pods
kubectl -n bookstore get pods
istioctl proxy-status
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
curl -f http://localhost:8080/productpage
curl -f http://localhost:8080/details/1
curl --resolve bookstore.local:8080:127.0.0.1 http://bookstore.local:8080/productpage
kubectl -n bookinfo exec deployment/productpage-v1 -c productpage -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://httpbin.org/get", timeout=15).status)'
# Must fail: no permitted direct HTTPS egress.
kubectl -n bookinfo exec deployment/productpage-v1 -c productpage -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("https://github.com", timeout=15).status)'
```

Check new `istio_requests_total` samples in Mimir and new spans in the Istio Traces
dashboard. Historical ambient samples remain until storage retention expires.
