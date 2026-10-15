# AWX study lab

The ops ApplicationSet discovers addons/awx/awx-operator/overlays/ops and
addons/awx/awx/overlays/ops. The operator is pinned to upstream release 2.19.1;
its supported AWX image is selected by the operator. Both run in namespace awx,
with sidecar injection disabled so controller-managed automation/job pods do not
require mesh-specific shutdown or connectivity configuration.

AWX uses its operator-managed ClusterIP Service and the existing shared Istio
ingress. Access it at http://awx.localhost:8080/ while forwarding the shared ingress:

```bash
# Ingress is exposed directly by LoadBalancer at http://localhost:8080
# In a second terminal:
curl --resolve awx.localhost:8080:127.0.0.1 http://awx.localhost:8080/api/v2/ping/
```

Browsers commonly resolve *.localhost locally. If yours does not, add
127.0.0.1 awx.localhost to your hosts file. Use HTTP; the shared ingress does not
terminate HTTPS. The dedicated hostname lets AWX use its original root/UI/API paths.

Log in as admin. Retrieve the generated password locally (it is not stored in Git):

```bash
kubectl -n awx get secret awx-admin-password -o jsonpath='{.data.password}' | base64 --decode
```

PostgreSQL has an 8Gi PVC and projects have a 2Gi ReadWriteOnce PVC, using the
cluster's default StorageClass. This is a single-node learning setup; preserve
the database and operator-generated encryption/password secrets when recovering.
Large or concurrent playbook jobs need more resources than this small lab profile.
Installation includes image downloads and database migrations and can take minutes.

Check progress:

```bash
kubectl -n awx get awx,pods,svc,pvc
kubectl -n awx logs deployment/awx-operator-controller-manager -c awx-manager --tail=50
kubectl -n argocd get applications awx-operator-ops awx-ops
```

Start learning with a localhost inventory, a Git project containing a simple
playbook, and a Job Template using the default execution environment. The operator
owns AWX's Deployments, Services and Secrets; Argo CD owns the operator installation,
AWX custom resource and ingress VirtualService. AWX namespace logs are included in
Alloy's existing Kubernetes log discovery.
