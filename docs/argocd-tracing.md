# Argo CD traces through Alloy

The bootstrap manifests configure `argocd-cmd-params-cm` with:

```yaml
otlp.address: alloy.alloy.svc.cluster.local:4317
otlp.insecure: "true"
otlp.attrs: k8s.namespace.name:argocd,k8s.cluster.name:ops
```

Argo CD v3.2.0's API server, application controller and repo server already map
these keys to their supported OTLP environment variables. ApplicationSet,
notifications, Redis and Dex are not configured with unsupported tracing flags.
This is native Argo CD instrumentation and does not depend on injecting sidecars
into the excluded argocd namespace.

Alloy's existing OTLP gRPC receiver accepts the spans and exports them to Tempo
through its batch processor. The Alloy Service names port 4317 `grpc-otlp` so
Istio configures HTTP/2. The plaintext setting describes Argo CD's connection to
the receiver; no extra ZIPKIN receiver or endpoint is involved.

The three workload templates include a checksum of the OTLP ConfigMap data to
roll them when this configuration is introduced. ConfigMap environment variables
are read only on process startup. When editing the OTLP data in this raw bootstrap
manifest, update those checksums too (SHA256 of the sorted-key JSON data map).

Validation: trigger a hard refresh of a GitOps Application to exercise controller
and repo server instrumentation, and request `/api/version` from argocd-server.
In Grafana Explore, select Tempo and search:

```traceql
{ resource.service.name =~ "argocd.*" }
```

Look for native Argo CD spans rather than treating gateway/Envoy spans as proof
of application instrumentation. A collector accepting traffic alone is also not
proof that a particular application emitted traces.

References:
- https://argo-cd.readthedocs.io/en/release-3.2/operator-manual/argocd-cmd-params-cm-yaml/
