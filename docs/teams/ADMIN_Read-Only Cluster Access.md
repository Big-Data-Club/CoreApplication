# BDC Hub - Read-Only Cluster Access (Admin Guide)

Audience: whoever already has cluster-admin `kubectl` access on
`bdc_web@10.1.8.133` and is onboarding a new contributor who only needs to
read pod status, logs, and events - not modify anything.

## Why not just add another SSH user

`DEPLOYMENT.md` sets up `bdc_web` with a copy of
`/etc/rancher/k3s/k3s.yaml`, which is a **cluster-admin** kubeconfig -
unrestricted access to the whole cluster. Sharing that file, or `sudo k3s
kubectl`, with a new member gives them full control, not read-only.

The VM also holds `k8s/base/secrets.yaml` (base64-encoded, not encrypted)
and the `.env` file `prepare-runtime.sh` reads. A shell user on the box -
even without `sudo` - can often read these if directory permissions aren't
locked down carefully. The safest approach is to **not give new members a
shell on the VM at all**. Everything they need - `get`, `describe`, `logs`
- is available straight from the Kubernetes API (port 6443) over VPN, from
their own laptop.

## The model

1. One dedicated `ServiceAccount` per person - never a shared token.
2. A `RoleBinding` to the built-in `view` ClusterRole, scoped per namespace
   (`default`, `monitoring`, ...) rather than a cluster-wide binding, so
   `kube-system` stays out of reach. `view` grants `get/list/watch` on most
   resources plus pod logs, and explicitly excludes Secrets, `exec`,
   `delete`, `patch`, and `create`.
3. A short-lived token (90 days) packaged into a standalone kubeconfig -
   never a copy of the admin `~/.kube/config`.
4. The API server (6443) firewalled to the VPN subnet only, same as SSH
   (22) already is.

## Files

| File | Purpose |
|---|---|
| `create-readonly-user.sh` | Creates the ServiceAccount + RoleBinding(s), issues a token, writes `kubeconfig-<name>.yaml` |
| `revoke-readonly-user.sh` | Deletes the ServiceAccount + RoleBinding(s), invalidating the token immediately |

Both run on the VM, under the account that currently has cluster-admin
access.

## 1 - Restrict the API server to VPN only (one-time)

```bash
# Adjust the subnet to match your actual VPN range
sudo ufw allow from 10.8.0.0/24 to any port 6443 proto tcp
sudo ufw deny 6443
```

## 2 - Grant a new member read-only access

```bash
chmod +x create-readonly-user.sh revoke-readonly-user.sh

./create-readonly-user.sh minh                  # defaults to: default,monitoring
./create-readonly-user.sh lan lab,default        # custom namespace scope
```

This produces `kubeconfig-minh.yaml`. Hand it to them over a private
channel (personal Signal/Zalo DM) - never post it in a group chat, ticket,
or commit it to Git.

## 3 - Verify before handing off

```bash
kubectl --kubeconfig=kubeconfig-minh.yaml auth can-i get pods -n default         # yes
kubectl --kubeconfig=kubeconfig-minh.yaml auth can-i get secrets -n default      # no
kubectl --kubeconfig=kubeconfig-minh.yaml auth can-i delete pods -n default      # no
kubectl --kubeconfig=kubeconfig-minh.yaml auth can-i create pods/exec -n default # no
kubectl --kubeconfig=kubeconfig-minh.yaml auth can-i get pods -n kube-system     # no
```

## 4 - Revoke access (offboarding, or a leaked token)

```bash
./revoke-readonly-user.sh minh
```

Deleting the `ServiceAccount` invalidates the token immediately - no need
to wait out the 90-day expiry.

## What `view` grants vs. denies

| Allowed | Denied |
|---|---|
| `get`, `list`, `watch` on pods, deployments, services, configmaps, events | `get`/`list` on Secrets |
| `pods/log` (i.e. `kubectl logs`) | `exec` / `attach` / `port-forward` |
| `describe` on most objects | `create`, `update`, `patch`, `delete` |
| | Any access outside the namespaces it's bound to |

## If host-level (not pod-level) access is ever truly needed

Some things - `journalctl -u k3s`, `docker ps` - live on the host, not in a
pod. If a contributor genuinely needs that:

- Create a dedicated Unix user, **no `sudo`**, SSH key-only login.
- Never let them read `bdc_web`'s `~/.kube/config` (that's the admin one).
- Restrict what they can run via a forced command in `authorized_keys`
  (e.g. only `journalctl --no-pager -u k3s`) instead of a full shell.
- Never expose `k8s/base/secrets.yaml`, `.env`, or `prepare-runtime.sh` to
  that user.

This is harder to audit than the kubeconfig-over-VPN model above, so treat
it as a fallback, not the default.