# Envoy access logs and dashboard 14876

Source: https://grafana.com/grafana/dashboards/14876-grafana-loki-dashboard-for-istio-service-mesh/
Pinned upstream revision: 3. Local UID: istio-loki-14876.

The vendored dashboard JSON is provisioned through the Grafana dashboard ConfigMap
and uses the existing Loki datasource (UID loki). Import-time datasource placeholders
are removed. Default scope is namespace bookinfo, with proxy-instance selection.
Only streams with job=integrations/istio, container=istio-proxy and log_type=access
are selected, so proxy startup/system messages do not distort log-derived counts.

Local adaptations also remove an unused hidden NGINX JSON query, use the parsed
authority field in place of the original missing host field, and display Envoy's
millisecond durations as milliseconds. Selecting several proxies counts observations
at each selected hop; restrict the instance selector to an ingress proxy or one
workload when interpreting request counts. Top-page/user-agent panels retain the
upstream longer lookback periods; available history is bounded by Loki retention.

Istio reference: https://istio.io/latest/docs/tasks/observability/logs/access-log/
The mesh Telemetry resource enables the default envoy file-access-log provider.
Istiod keeps TEXT encoding and the default format required by the dashboard's Loki
pattern queries. Tracing remains configured on the same Telemetry resource.

Flow: Bookinfo Envoy stdout -> Kubernetes container logs -> Alloy
loki.source.kubernetes -> proxy classification/enrichment -> Loki -> Grafana.
Envoy does not push these file logs directly to Alloy's OTLP trace receiver.
The Alloy discovery rule already includes every istio-proxy container across
namespaces, including Bookinfo.

After Argo CD sync, open /grafana/d/istio-loki-14876/ through the shared ingress.
Generate traffic to /productpage and /details/1, then use a recent dashboard range.

```bash
kubectl -n istio-gateways port-forward svc/istio-ingressgateway 8080:80
curl http://localhost:8080/productpage
kubectl -n bookinfo logs deployment/productpage-v1 -c istio-proxy --tail=10
```

In Grafana Explore with Loki, check:

```logql
{job="integrations/istio",namespace="bookinfo",container="istio-proxy",log_type="access"}
```

If a recovered cluster's application pods were created before Istio injection was
ready, namespace labels alone do not add sidecars to existing pods. After Istiod is
ready, restart Bookinfo deployments and confirm istio-proxy exists in each pod.
