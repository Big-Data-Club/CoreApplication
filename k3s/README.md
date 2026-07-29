# BDC Hub Kubernetes Configuration

`k3s/` contains the Kubernetes source used for BDC Hub production operations.
It is configuration, not a local development shortcut: inspect changes with the
service owner and follow the [DevOps runbook](../docs/DEVOPS_RUNBOOK.md) before
applying anything to a cluster.

## Layout

| Path | Purpose |
|---|---|
| `base/` | Application deployments, services, ingress, Kafka/Redis and shared configuration |
| `base/kustomization.yaml` | Kustomize entry point for the base workload set |
| `observability/` | Application ServiceMonitors and Grafana dashboard assets |
| `kube-prometheus-stack/` | Helm values required by the monitoring stack |
| `monitoring/` | Legacy/auxiliary monitoring material; review against the active Helm deployment before applying |

## Safe validation

```bash
kubectl kustomize k3s/base
kubectl diff -k k3s/base
```

`kubectl diff` requires approved cluster access and is read-only with respect to
cluster objects. Do not apply a full base casually during an image deployment:
the production deploy script deliberately changes selected immutable images and
rolls them back on failure. See the runbook for the current CI/CD matrix,
rollout diagnostics, monitoring, and performance-test guardrails.

## Change rules

- Keep Secrets out of Git; reference approved secret names only.
- Set named container ports where monitoring/service discovery needs them.
- Add resource, probe, ingress, ServiceMonitor, and rollout implications to a
  pull request that changes a workload.
- Verify the resulting deployment image SHA, pod readiness, events, and service
  smoke behaviour after an approved production release.
