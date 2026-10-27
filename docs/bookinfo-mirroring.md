# Bookinfo traffic mirroring

`apps/bookinfo-v2/overlays/dev` deploys a separate copy of the pinned Bookinfo
sample in namespace `bookinfo-v2`, with Istio sidecars. This is a shadow
environment, not a new upstream image release: productpage, details and ratings
remain v1; reviews includes v1, v2 and v3, just like the original stack.
The services use namespace-local discovery, so shadow productpage calls shadow
details and reviews, and shadow reviews calls shadow ratings.

The original ingress mirrors 100% of GET requests for `/productpage`,
`/productpage/…` and `/api/v1/products…` to shadow productpage. Client responses
come from the original stack. Login, logout, static assets and direct details
requests keep their existing routes without mirroring. The original reviews
fault-injection policy remains confined to namespace `bookinfo`.

Istio sends mirrors asynchronously and discards their responses. Mirroring is
best effort and adds load to
the cluster. This sample uses read-only product data; for a real application,
isolate shadow databases, queues and other systems with side effects too.

## GitOps rollout

Commit and push the manifests, then sync the dev AppProject and allow the dev
ApplicationSet to discover `bookinfo-v2-dev`. Sync that application and wait for
its deployments to become ready before syncing `bookinfo-dev` to enable the
mirror route. Direct cluster changes may be reverted by Argo CD self-healing
until these changes are in Git.

## Verify

```sh
curl -fsS http://localhost:8080/productpage > /dev/null
kubectl -n bookinfo-v2 get pods
kubectl -n bookinfo-v2 logs deployment/productpage-v1 -c istio-proxy --since=2m
```

Look for inbound `/productpage` requests in the shadow pod and outbound calls to
`details.bookinfo-v2.svc.cluster.local` and `reviews.bookinfo-v2.svc.cluster.local`.
In Kiali, select
both `bookinfo` and `bookinfo-v2` and generate several requests to inspect both
stacks. A port-forward directly to primary productpage bypasses the ingress
mirror rule.

To stop mirroring, remove the `productpage-mirror` route and sync `bookinfo-dev`.
The following `productpage` route continues to serve the same paths. Remove the
shadow application only after disabling mirroring.
