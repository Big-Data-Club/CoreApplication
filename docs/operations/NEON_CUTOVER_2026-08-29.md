# Neon PostgreSQL Cutover and K3s Recovery - 2026-08-29

| Field | Value |
|---|---|
| Status | Completed incident trajectory and reusable recovery procedure |
| Date | 2026-08-29 (Asia/Ho_Chi_Minh) |
| Scope | Neon PostgreSQL migration, production K3s runtime configuration, node disk pressure |
| Result | Six databases migrated and verified; every production deployment ready |

> This document intentionally omits passwords, tokens, private addresses, and
> complete database connection strings. Obtain credentials from the approved
> secret store and expose them only for the duration of an authorized cutover.

## 1. Executive summary

Production application pods were unavailable during a Neon database cutover.
The recovery exposed four independent issues:

1. Production K3s still referenced the old Neon endpoint.
2. Only part of the database set had a previous recorded migration; the live
   source actually contained six user databases.
3. `bdc-secrets` contained `TODO_CHANGE_ME` placeholders for non-database
   runtime values, so services failed even after their database settings were
   corrected.
4. The single K3s node had `DiskPressure=True`. An orphaned Docker model-cache
   volume consumed approximately 6.4 GB even though production now used K3s.

A restore also carried an empty database-level `search_path` into four target
databases. Direct connections were corrected immediately, but Neon pooler
sessions continued to reuse the old setting until their backend sessions were
recycled.

## 2. Final verified state

The migration discovered and copied all user databases from the old Neon
project to the new project.

| Database | User-table count after source/target verification |
|---|---:|
| `ai` | 27 |
| `auth` | 20 |
| `chat` | 7 |
| `lab` | 22 |
| `lms` | 45 |
| `neondb` | 9 |

Fresh custom-format dumps from the cutover are stored outside this repository's
tracked source files under:

```text
Backup-and-Migration-DB/dumps/cutover-20260829/
```

The final production checks showed:

- all application deployments at their desired ready replica count;
- `DiskPressure=False` and no disk-pressure taint;
- approximately 8.3 GB free on the 39 GB root filesystem after application
  images had been pulled again; and
- Auth, LMS, Lab, Chat, AI, AI worker, course-blueprint workers, frontend,
  Personalize, and Recommender available.

## 3. Actual recovery trajectory

### Step 1 - Establish the production failure mode

After connecting through the approved VPN and SSH path, inspect the node, pods,
and scheduling events:

```bash
kubectl get nodes
kubectl get pods --no-headers
kubectl describe pod <pending-pod> | sed -n '/Events:/,$p'
```

Observed state:

- application pods were `Pending`, `Error`, `Evicted`, or
  `ContainerStatusUnknown`;
- the scheduler reported an untolerated taint; and
- the node carried `node.kubernetes.io/disk-pressure:NoSchedule`.

### Step 2 - Confirm the database migration scope

Do not infer the database set from the database name at the end of one
connection string. Query the source catalog:

```sql
SELECT datname
FROM pg_database
WHERE datistemplate = false
  AND datname NOT IN ('postgres')
ORDER BY datname;
```

The source returned `ai`, `auth`, `chat`, `lab`, `lms`, and `neondb`. A previous
migration state file listed only `ai`, `auth`, and `lms`, so it was not evidence
that the whole source had been copied.

### Step 3 - Create fresh dumps and restore every database

PostgreSQL 17 clients were used because both Neon endpoints reported PostgreSQL
17.11. For each discovered database:

1. create a new custom-format dump with `pg_dump`;
2. create the target database if it does not exist;
3. restore with `--clean --if-exists`, `--no-owner`, and `--no-acl`; and
4. compare source and target user-table counts.

Sanitized command pattern:

```bash
pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="<dump-dir>/<database>.dump" \
  "<source-url-for-database>"

pg_restore \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  --exit-on-error \
  --dbname="<target-url-for-database>" \
  "<dump-dir>/<database>.dump"
```

All six restores and table-count comparisons completed successfully.

### Step 4 - Cut K3s over to the new Neon project

The shared `bdc-config` ConfigMap was updated so all five service-specific host
keys referenced the new pooler endpoint:

```text
POSTGRES_HOST
LMS_POSTGRES_HOST
LAB_POSTGRES_HOST
CHAT_POSTGRES_HOST
AI_POSTGRES_HOST
```

The database name, user, and password keys in `bdc-secrets` were updated for
Auth, LMS, Lab, Chat, and AI. Logical database names remained service-specific;
they were not all changed to `ai` merely because the supplied administrative
URL ended in `/ai`.

The production `.env` on the server was updated as the persistent source for
the same endpoint and credential values. This prevents a later runtime-secret
refresh from reverting the live cluster.

### Step 5 - Recover the complete runtime Secret

New pods revealed a second fault unrelated to PostgreSQL. LMS first failed with
`JWT secret must be at least 32 characters`. Inspection showed that
`bdc-secrets` contained sample `TODO_CHANGE_ME` values.

The production `.env` contains duplicate keys: local defaults appear earlier
and production values appear later. Passing it directly to
`kubectl --from-env-file` fails on duplicates. A temporary canonical env file
was therefore generated with "last value wins" semantics before applying the
Secret:

```bash
runtime_env="$(mktemp)"
chmod 600 "$runtime_env"

awk -F= '
  /^[A-Za-z_][A-Za-z0-9_]*=/ {
    key=$1
    if (!(key in seen)) {
      order[++count]=key
      seen[key]=1
    }
    line[key]=$0
  }
  END {
    for (i=1; i<=count; i++) print line[order[i]]
  }
' <production-env-file> >"$runtime_env"

kubectl create secret generic bdc-secrets \
  --from-env-file="$runtime_env" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

rm -f "$runtime_env"
```

Never apply `k3s/base/secrets.yaml` to production with its sample values. Do not
print or commit the generated Secret manifest.

### Step 6 - Remove the disk-pressure cause

The node initially had only about 5.3 GB free and K3s was evicting application
pods. Host inspection found:

```text
/var/lib/docker/volumes/core_ai_model_cache   approximately 6.4 GB
/var/lib/rancher/k3s                         approximately 15 GB
```

The Docker binary was no longer installed and production used the K3s
containerd runtime. The exact Docker model-cache volume was therefore an
orphaned, derived cache rather than a live K3s PVC. It was removed, and archived
journals were reduced to a bounded size. No K3s storage directory or application
PVC was deleted.

After cleanup, root filesystem usage fell from approximately 87% to 70%. It
later settled near 79% after K3s pulled required application images again.

Validate both bytes and inodes:

```bash
df -h /
df -i /
kubectl get node <node> -o jsonpath='{.spec.taints}{"\n"}'
kubectl get node <node> \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}:{.reason}{"\n"}{end}'
```

Kubelet retains pressure conditions for a transition period. Manually removing
the taint while `DiskPressure=True` is not sufficient because the node
controller adds it again. In this incident, K3s was restarted after capacity
was demonstrably healthy so the eviction manager re-evaluated immediately.
The result was `DiskPressure=False` with no taint.

### Step 7 - Roll out workloads with restored runtime configuration

The database consumers were restarted so environment variables sourced from
the ConfigMap and Secret were rebuilt:

```bash
kubectl rollout restart \
  deployment/auth-service \
  deployment/lms-service \
  deployment/lab-service \
  deployment/chat-service \
  deployment/ai-service \
  deployment/ai-worker \
  deployment/course-blueprint-worker
```

Redis was also restarted after restoring `bdc-secrets`. Before that restart,
new LMS pods used the restored password while the existing Redis process still
used the old value, producing `WRONGPASS`:

```bash
kubectl rollout restart statefulset/redis
```

Redis used its existing PVC; this restart did not delete Redis data.

### Step 8 - Repair restored `search_path` and recycle Neon pooler sessions

Chat connected to the new database but failed its startup migration with:

```text
ERROR: no schema has been selected to create in (SQLSTATE 3F000)
```

`SHOW search_path` was normal for `ai` and `auth`, but empty for `chat`, `lab`,
`lms`, and `neondb`. The database-level setting was reset and the owner role was
given the standard default:

```sql
ALTER ROLE <database-owner> SET search_path TO "$user", public;

ALTER DATABASE ai RESET search_path;
ALTER DATABASE auth RESET search_path;
ALTER DATABASE chat RESET search_path;
ALTER DATABASE lab RESET search_path;
ALTER DATABASE lms RESET search_path;
ALTER DATABASE neondb RESET search_path;
```

The direct Neon endpoint then returned:

```text
"$user", public
public
```

The pooler still returned an empty value because it retained backend sessions
created before the repair. Authorized connections belonging to the database
owner were terminated through the direct endpoint so that the pooler recreated
them with the corrected setting:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = current_user
  AND pid <> pg_backend_pid();
```

This is a brief connection interruption. Use it only in an approved cutover and
expect application pools to reconnect. After recycling, both the pooler and
direct endpoint returned the standard search path, and Chat became ready.

### Step 9 - Perform final readiness checks

```bash
kubectl get deploy
kubectl get pods -A
kubectl get node <node> \
  -o jsonpath='{range .status.conditions[?(@.type=="DiskPressure")]}DiskPressure={.status}{"\n"}{end}'
df -h /
```

Do not declare recovery while a deployment remains unavailable, even if a
replacement pod is `Running`; wait for readiness probes and the deployment's
`AVAILABLE` count.

## 4. Required ordering for the next cutover

The safe sequence is:

1. Inventory every source database from `pg_database`.
2. Stop or quiesce writes, or explicitly accept and document the consistency
   window.
3. Take fresh dumps using a PostgreSQL client at least as new as the server.
4. Restore all databases to the target.
5. Verify table counts and application-critical row counts.
6. Check `search_path`, schema ownership, and privileges through both the direct
   endpoint and pooler.
7. Confirm the complete production Secret is valid and contains no placeholders.
8. Confirm the K3s node has disk, inode, memory, and PID headroom.
9. Update the persistent production env file and live ConfigMap/Secret.
10. Restart stateful dependencies whose startup configuration changed.
11. Roll out database consumers in a controlled order.
12. Verify every deployment, logs, ingress smoke tests, and node conditions.
13. Retain dumps until the rollback window closes.

Do not point production at the target before the full database inventory is
migrated and verified. During this incident the endpoint was initially changed
before the incomplete historical migration record was recognized; the complete
fresh migration corrected that ordering mistake.

## 5. Preventive actions

- Alert before root filesystem free space crosses the K3s eviction threshold.
- Remove or archive Docker-era volumes after confirming the K3s replacement is
  stable.
- Add a CI check that rejects `TODO_CHANGE_ME` in any rendered production
  Secret input.
- Make the runtime preparation path independent of an unavailable Docker CLI,
  or install and document its required dependency.
- Make database discovery mandatory in the migration job; never rely only on a
  manually maintained include list or old state file.
- Add post-restore checks for `SHOW search_path`, `current_schema()`, schema
  privileges, and pooler/direct endpoint parity.
- Add smoke tests for PostgreSQL and Redis authentication before declaring a
  rollout healthy.
- Keep at least one immutable, timestamped dump set for the active rollback
  window and document its retention owner.
