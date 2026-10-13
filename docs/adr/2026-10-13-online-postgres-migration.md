# ADR: Operate PostgreSQL cutovers from /monitor with logical replication

- Date: 2026-10-13
- Status: Implemented in the repository; the console and dashboard have been deployed, but no production data cutover has been confirmed
- Scope: Grafana/K3s operations, production deployment, Neon PostgreSQL

## Context

The sibling `Backup-and-Migration-DB` repository contains `start_migrate` and
scripts for dump, restore, writer shutdown, and Secret cutover over Docker/SSH.
That flow stops writers before copying all data. The new requirement is to
initiate a cutover from `/monitor`, run it in K3s, and shorten the interruption.
Neon is the chosen PostgreSQL provider.

## Decision

Run an independent operations control plane in `ops/db-migration`. It remains
available while Auth, LMS, and AI services are stopped. A Grafana dashboard
links to a same-origin console. The console checks the Grafana server Admin
session through `/api/user`, validates Origin and JSON on mutations, and starts
only approved Job profiles. The browser never receives Kubernetes credentials.
It sends each destination URL to the console, which stores it in a Kubernetes
Secret rather than a Job specification or status ConfigMap.

The Job uses `pg_dump --schema-only` and native logical replication for initial
COPY and ongoing WAL changes. Once every database has caught up, it stops all
writers, verifies committed markers per database, copies sequence values,
patches the DB fields in the runtime Secret and ConfigMap, and restores the
previous replica counts. It preserves the existing runtime contract, including
the host in `bdc-config`, so application manifests do not all need to change.
It does not change Redis credentials or restart Redis.

A ConfigMap `resourceVersion` compare-and-swap lock is shared with repository
deployments. A separate compare-and-swap transition lets a Job start only once.
Ambiguous requests, killed Pods, and failures after the destination may have
accepted writes retain the lock. Before destination writes begin, the runner
may restore the source. Afterwards, operators must repair forward on the
destination or follow an approved reconciliation plan. A readiness failure
must not trigger an automatic rollback to the source.

CI respects the `bdc.io/db-managed` annotation and preserves migrated DB
settings in later deployments. Endpoint credentials and recovery snapshots
remain in Secrets; the status ConfigMap contains progress only. A dedicated
workflow builds and deploys the console and dashboard on relevant pushes to
`main`, using an image digest and the shared production lock. The migration
profile starts disabled. Operators configure the source and enable the profile
once, then enter a new destination URL for each run. After a successful cutover
and rollout, the Job promotes the destination Secret to the next source, so
A→B→C works without reconfiguring the source on the server. If promotion fails
after destination writers start, the Job retains the lock for manual recovery.
Deployments preserve the enabled profile and endpoint Secrets.

## Consequences

The cutover no longer depends on a laptop's SSH/Docker session or an Airflow
HTTP server outside Grafana authentication. The older repository remains, but
its scripts must not run concurrently because they do not use the shared lock.

This implementation requires PostgreSQL 16+ on the same major version, empty
destination databases with matching names, six bindings on one source, and all
writers following the current Deployment convention. The [runbook](../operations/POSTGRES_ONLINE_MIGRATION.md)
documents schema restrictions, replication capacity, DDL freeze, and Neon
setup. It does not provide zero downtime, multi-role ACL migration, automatic
resume, or rollback after destination writes begin.

References: [PostgreSQL logical replication](https://www.postgresql.org/docs/17/logical-replication.html),
[Neon publisher/subscriber](https://neon.com/docs/guides/logical-replication-neon),
[Grafana data links and actions](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/configure-data-links/).
