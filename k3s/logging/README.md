# BDC service logs and errors

Application stdout/stderr → Grafana Alloy on each node → Loki → the existing
Grafana at `/monitor/`. A separate, single Alloy reader persists Kubernetes
Events from `default` and `monitoring`, including scheduling and eviction errors
that have no application logs. This extends `kps`; it does not install another
Grafana or modify application Deployments.

## Install once

Use an authorised workstation with `kubectl`, Helm, this checkout and the correct
production context. SSH is not required. The helper prints its plan by default:

```bash
python3 scripts/enable-service-logs.py
python3 scripts/enable-service-logs.py --apply
```

The helper validates the manifests against the API before making changes,
preserves existing additional datasources, and upgrades `kps` using its **already
installed chart version** and existing values. It enables dashboard discovery,
adds the `BDC Logs` datasource, installs the collectors and waits for readiness.
It can restart Grafana as part of provisioning; it does not roll application pods.
Do not apply `k3s/monitoring/`, which contains legacy standalone Grafana manifests.
Production CI currently does not deploy `k3s/logging/`; a Git push alone does not
install this stack.

If interrupted with Ctrl+C during `helm upgrade`, the Kubernetes changes are
not automatically undone. `Update Complete. Happy Helming!` from `helm repo
update` only reports a refreshed chart index. Check `helm -n monitoring history
kps` and `helm -n monitoring status kps`. Once no Helm deployment is still
running, roll back a failed/pending release to the latest successful revision
shown in history, for example `helm -n monitoring rollback kps 12 --wait
--timeout 10m` when revision 12 succeeded and 13 failed. Wait for rollback to
finish, then rerun the installer. Do not uninstall the release or delete its
Helm Secrets to unlock it. The installer now lists all release states and prints
the recovery command instead of a generic traceback; it never rolls back
automatically. During Helm's readiness wait (up to 10 minutes), inspect
`kubectl -n monitoring get pods` in another terminal instead of cancelling.

Prerequisites: the `monitoring` namespace and `kps` release, Prometheus Operator
CRDs, the `local-path` storage class, Linux K3s nodes with `/var/log/pods`, and an
enabled network-policy controller. Account for about **175m CPU / 368Mi RAM
requests on one node**, plus existing monitoring workloads. Per-node file agents
read root-owned pod logs through a read-only mount, without privileged mode,
host networking or access to Kubernetes Secrets. RBAC permits only pod metadata
in `default` and Events in the two configured namespaces. Add Role/RoleBinding
and discovery namespaces together when collecting another namespace.

To update only the versioned manifests after installation:

```bash
kubectl kustomize k3s/logging > /tmp/bdc-logging.yaml
kubectl apply --dry-run=server -k k3s/logging
kubectl apply -k k3s/logging
```

Generated config names change with their content, triggering collector rollouts.
Pod-log file offsets persist at `/var/lib/bdc-alloy` on each node. The Events
reader has one replica with Recreate strategy to avoid duplicate readers.

## Use Grafana

Open `/monitor/d/bdc-service-logs/` → **BDC Service Logs & Errors**. Select:

- **Namespace**, **Service**, **Pod**, **Level** and the time range.
- **Search**: a case-insensitive RE2 expression, job UUID, request UUID or text
  such as `Speech generation failed` / `studio generate failed`.
- **Error records and tracebacks** to expand a complete JSON `exc_info` or
  grouped Python/Java stack trace. Log panels keep the original message.
- **Kubernetes warnings** for `FailedScheduling`, `Evicted`, `FailedMount`,
  image-pull and probe failures. This panel uses namespace/search filters,
  independently of service/pod filters. Select All namespaces to inspect Loki.

The dashboard graphs error records per minute and totals by service, warnings,
restarts, Pending/Failed pods, waiting reasons, last OOM termination of current
pods, collector scrape health, dropped records and node disk capacity. Metrics
use the existing Prometheus datasource; choose it in **Metrics source** if more
than one exists. An empty error panel with no log volume is not proof of health.

In **Explore**, choose **BDC Logs**, then use LogQL:

```logql
{job="bdc/containers", service_name="ai-worker"} |= "Speech generation failed"
```

```logql
{job="bdc/containers", service_name="ai-service", level="error"}
```

```logql
sum by (service_name) (rate({job="bdc/containers",level="error"}[5m])) * 60
```

```logql
{job="bdc/kubernetes-events",level="warn"} | json
```

Service identity comes from Kubernetes labels, falling back to the container
name. This keeps `ai-worker` separate from `ai-service` even when their JSON
`service` fields are identical. Only bounded level labels are indexed; job IDs,
request IDs, logger names and message contents are searchable text. JSON,
Go `[ERROR]` / `ERROR:` and timestamped Java levels are normalized; unrecognized
levels stay `unknown`, and stderr alone is not assumed to be an error. Error
counts represent log records, not unique incidents or HTTP error percentages.
An HTTP 500 access log without a severity field can remain `unknown`; inspect
service HTTP metrics and raw logs as well.

## Retention and access

The initial small-VM profile uses a single Loki instance, TSDB v13, filesystem
storage, a 5Gi local-path PVC and **72h** compactor retention. It survives a pod
restart, but it is not highly available and does not survive loss of that node's
disk. Local-path PVC size is a request, **not an enforced filesystem quota**.
Retention is asynchronous and can exceed 72h by compaction/deletion delay; it
does not delete early when disk space is low. The `BDCLoggingDiskLow` alert and
dashboard monitor the node filesystem. Before keeping more history or ingesting
large volumes, use an approved dedicated object-store bucket (R2/S3) and size
retention against measured volume; do not mix logs with course/media buckets.

Loki and Alloy expose no Ingress or external Service. Loki has tenant auth off
for this single-tenant internal stack; its NetworkPolicy permits Grafana, Alloy
and Prometheus pods in `monitoring`. Keep the existing Grafana login/access
restrictions; a Grafana viewer allowed to query this datasource can read logs.
Do not log API keys, passwords, tokens, narration/document bodies or learner
personal data. This collector does not make unsafe application logging safe.

Log records are capped at 256KB and grouped stack traces at 200 lines. Lines
older than 72h are rejected; existing rotated/deleted node logs and expired
Kubernetes Events cannot be recovered retroactively. Event updates may repeat;
their log count is not the count of distinct infrastructure incidents. Collection
starts from files still present on installation and continues across rollouts;
it is best effort, not an exactly-once audit archive. Loki outage plus node-log
rotation or eviction can lose records despite persisted file offsets.

Prometheus rules report unavailable collectors, unreachable logging targets,
dropped records and low disk through the existing Alertmanager. External email
or chat notifications depend on its existing receiver configuration.

## Verify and troubleshoot

```bash
ai-service/.venv/bin/python -m unittest discover -s scripts/tests -p test_service_logging.py -v
kubectl kustomize k3s/logging > /tmp/bdc-logging.yaml
docker run --rm -v "$PWD/k3s/logging/config:/config:ro" grafana/loki:3.7.9 -config.file=/config/loki.yaml -verify-config=true
docker run --rm -v "$PWD/k3s/logging/config:/config:ro" grafana/alloy:v1.21.1 validate /config/logs.alloy
docker run --rm -v "$PWD/k3s/logging/config:/config:ro" grafana/alloy:v1.21.1 validate /config/events.alloy
BDC_LOGGING_SMOKE=1 ai-service/.venv/bin/python -m unittest discover -s scripts/tests -p test_service_logging.py -v
```

The opt-in smoke uses local Docker and synthetic records, starts isolated
Loki/Alloy containers, verifies real ingestion, severity, traceback preservation,
and dashboard LogQL, and removes its own containers/network afterwards.

After production installation, confirm both app/worker logs and warning Events
in Grafana. If no data arrives, inspect the logging workloads once via kubectl:

```bash
kubectl -n monitoring get pods,pvc -l app=bdc-loki
kubectl -n monitoring get daemonset bdc-alloy-logs
kubectl -n monitoring logs deployment/bdc-loki --tail=100
kubectl -n monitoring logs daemonset/bdc-alloy-logs --tail=100
kubectl -n monitoring logs deployment/bdc-alloy-events --tail=100
```

For a Pending collector, use `kubectl describe pod` and check resources/PVC
binding. For missing dashboards, check Grafana's dashboard sidecar, label
`grafana_dashboard=1` and namespace discovery. For a datasource error, check Loki
readiness and NetworkPolicy labels. No remote access or live deployment has
been performed by adding these files.

Rollback: remove the `bdc-loki` datasource from the preserved Helm values and
delete the `bdc-*` logging Deployments, DaemonSet, ServiceMonitor, PrometheusRule,
dashboard ConfigMap and access rules as needed. **Keep the `bdc-loki` PVC** until
log disposal is explicitly intended; `kubectl delete -k k3s/logging` also deletes
that PVC. Application Deployments are unaffected.

Primary references: [Alloy file source](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/),
[Kubernetes Events source](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.kubernetes_events/),
[Loki retention](https://grafana.com/docs/loki/latest/operations/storage/retention/)
and [filesystem storage](https://grafana.com/docs/loki/latest/operations/storage/filesystem/).
