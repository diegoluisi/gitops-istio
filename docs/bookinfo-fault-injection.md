# Bookinfo fault injection

The dev overlay includes `reviews-fault-injection`, a mesh VirtualService that
returns HTTP 503 for every request to `reviews` with the header `end-user: jason`.
Requests without that header follow the normal route to all available reviews versions.

After committing, pushing, and syncing Bookinfo in Argo CD, open
`http://localhost:8080/productpage` and log in as `jason`. The product page should
show that reviews are unavailable. Log out to restore normal behavior.

To test the reviews endpoint directly from a pod with an Istio sidecar and curl:

```sh
curl -i -H 'end-user: jason' http://reviews.bookinfo.svc.cluster.local:9080/reviews/0
curl -i http://reviews.bookinfo.svc.cluster.local:9080/reviews/0
```

The first request should return 503; the second should return 200 when reviews
is healthy. Generate requests as `jason` and inspect the productpage-to-reviews
edge in Kiali for errors.

To remove the fault, remove `fault-injection.yaml` from the dev overlay's
resources and sync with pruning enabled.
