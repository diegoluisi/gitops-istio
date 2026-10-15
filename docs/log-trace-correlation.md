# Debug Bookinfo with Istio, Loki and Tempo

Adapted from https://grafana.com/blog/how-istio-tempo-and-loki-speed-up-debugging-for-microservices/
The article uses Istio 1.10, Zipkin and Fluent Bit. This repo uses the existing
Istio Helm charts, OTLP Alloy receiver, Loki, Tempo and provisioned Grafana instead.

Envoy writes traceID=%TRACE_ID% in its text access log. Unlike a B3-header-only
formatter, this uses the active span ID for requests where tracing generates a new
trace context. Alloy tails the proxy stdout and delivers logs to Loki; proxy spans
are exported via OTLP/gRPC to Alloy on 4317 and then to Tempo. Sampling is 100%.
Trace IDs are not indexed Loki labels.

1. Open http://localhost:8080/productpage to generate requests.
2. Open http://localhost:8080/grafana/explore and select Loki.
3. Query `{job="integrations/istio",namespace="bookinfo",log_type="access"}`.
4. Expand a log containing traceID followed by a hexadecimal ID. The derived
   TraceID field has a View trace in Tempo internal link.
5. Inspect the span waterfall in Tempo. Use Logs for this span to return to matching
   Envoy logs, with a one-minute time margin on both sides of the selected span.

For a known trace ID, query Loki with:

```logql
{job="integrations/istio",container="istio-proxy",log_type="access"} |= "traceID=YOUR_TRACE_ID"
```

The Tempo datasource trace-to-logs query performs this lookup automatically.
Grafana's provisioning macros use escaped dollars in Helm values so Grafana keeps
the variables for query-time interpolation. The dashboard 14876 recent-request
panel preserves traceID in its formatted log messages for the same derived link.

The traces describe Envoy network hops. Complete cross-service traces depend on the
application propagating context; internal function/database spans require application
instrumentation. A log link can only open traces that exist within Tempo retention
(24h), which is shorter than Loki log retention (72h). Historical logs with no traceID
are not retroactively correlated.
