# BDC Hub — Read-Only Cluster Access (For New Contributors)

You've been given a personal kubeconfig file (`kubeconfig-<your-name>.yaml`)
that lets you inspect the BDC Hub cluster — pod status, logs, events,
service config — without being able to change anything. That's intentional:
this access is scoped to read-only so you can debug and learn safely.

## What you need

- A VPN connection to the BDC network (ask an admin if you're not set up yet)
- `kubectl` installed on your machine
- Your `kubeconfig-<your-name>.yaml` file, received privately

> Keep that file private. Don't post it in group chats, tickets, or commit
> it to Git — treat it like a password. It expires after 90 days; ask an
> admin for a new one when it does.

## Quick start

```bash
export KUBECONFIG=~/path/to/kubeconfig-<your-name>.yaml
kubectl get pods -n default
```

Or pass it explicitly each time instead of exporting it:

```bash
kubectl --kubeconfig=~/path/to/kubeconfig-<your-name>.yaml get pods -n default
```

## What you can do

| Action | Example |
|---|---|
| List/inspect pods, services, deployments, events | `kubectl get pods -n default` |
| Read logs | `kubectl logs <pod-name> -n default` |
| Read logs from a crashed container | `kubectl logs <pod-name> -n default --previous` |
| Describe an object (events, config, why it's failing) | `kubectl describe pod <pod-name> -n default` |
| Check rollout status | `kubectl rollout status deployment/lms-service -n default` |
| List monitoring pods | `kubectl get pods -n monitoring` |

## What you can't do (by design)

| Blocked | Why |
|---|---|
| `kubectl exec` into a pod | Prevents accidental changes or exposure of in-memory data |
| `kubectl delete` / `edit` / `apply` | Read-only means read-only |
| `kubectl get secrets` | Secrets hold DB passwords, JWT keys, API keys — not needed to debug logs |
| Anything in `kube-system` | Out of scope for app debugging |

If a command returns `Forbidden`, that's expected — it means the
permission model is working, not that something's broken on your end. If
you think you genuinely need a permission you don't have, ask an admin
rather than requesting broader access "just in case."

## Handy commands for chasing down an error

```bash
# Which pods are unhealthy right now
kubectl get pods -n default

# Recent events, oldest first — good for "why won't this pod start"
kubectl get events -n default --sort-by=.metadata.creationTimestamp

# Tail logs live
kubectl logs -f <pod-name> -n default

# Logs from the previous (crashed) instance of a container
kubectl logs <pod-name> -n default --previous

# Full detail on a pod: image, env, resource limits, recent events
kubectl describe pod <pod-name> -n default
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Unable to connect to the server` | VPN isn't connected — check that first |
| `Forbidden` on a specific verb/resource | Outside your read-only scope — expected |
| `Unauthorized` / token errors | Your 90-day token likely expired — ask an admin for a refresh |

## Requesting changes

Contact an admin (owner of `bdc_web@10.1.8.133`) if you need:
- Access to another namespace
- A refreshed kubeconfig after expiry
- To report a lost or possibly leaked kubeconfig — get it revoked immediately