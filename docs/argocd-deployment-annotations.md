# Dev deployment markers

The dev ApplicationSet subscribes generated applications to `on-dev-deployed`.
Argo CD Notifications posts an organization annotation to Grafana after a dev
application finishes syncing successfully and is both Synced and Healthy.
`operationState.finishedAt` deduplicates notifications per completed operation,
including a later deployment of the same Git revision.

The ArgoCD dashboard's **Dev deployments** annotation query selects all three
required tags: `argocd`, `deployment`, and `dev`. Markers contain the application,
destination namespace, and deployed revision. Toggle this query in the dashboard
to show or hide deployment lines. Initial subscription can mark the application's
most recent successful operation.

This lab uses Grafana's existing anonymous Editor role to POST annotations;
there is no token in Git. If anonymous editing is removed, configure a Grafana
service-account token in `argocd-notifications-secret` and an Authorization
header in `service.webhook.grafana` before relying on notifications.

Alloy's UI is exposed through the shared Istio ingress at `/alloy/`, using the
chart's `alloy.uiPathPrefix` setting. OTLP receivers remain internal; this route
only forwards the UI and its HTTP endpoints on port 12345.

References:
- https://argo-cd.readthedocs.io/en/stable/operator-manual/notifications/services/webhook/
- https://grafana.com/docs/alloy/latest/reference/cli/run/
