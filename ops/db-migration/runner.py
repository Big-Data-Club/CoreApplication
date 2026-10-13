"""Single-attempt, fail-closed cutover Job. No retry after writers use the target."""
import base64
import json
import os
import signal
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs, unquote

from kube import Kube, LOCK, MANAGED, STATE, release, save_state, state
from replication import MigrationError, Replica, query

PREFIXES = {"POSTGRES", "LMS_POSTGRES", "LAB_POSTGRES", "CHAT_POSTGRES", "AI_POSTGRES", "DUTYLOG_POSTGRES"}
RECOVERY = "bdc-db-migration-recovery"


def endpoint(url, runtime=False):
    parsed = urlsplit(url)
    if parsed.scheme not in ("postgres", "postgresql") or not all((parsed.hostname, parsed.username, parsed.password)):
        raise ValueError("A complete PostgreSQL URL is required in the endpoint Secret")
    if not parsed.path.strip("/") or (runtime and parsed.port not in (None, 5432)):
        raise ValueError("Runtime manifests require port 5432 and URLs require a database")
    options = parse_qs(parsed.query)
    if set(options) - {"sslmode", "channel_binding"}:
        raise ValueError("Only sslmode and channel_binding URL options are supported")
    sslmode = options.get("sslmode", [""])[0]
    if sslmode not in ("require", "verify-ca", "verify-full"):
        raise ValueError("TLS is required for migration endpoints")
    return {"host": parsed.hostname, "user": unquote(parsed.username),
            "password": unquote(parsed.password), "sslmode": sslmode}


def uses_database(template):
    for c in template.get("spec", {}).get("containers", []) + template.get("spec", {}).get("initContainers", []):
        for item in c.get("env", []):
            ref = item.get("valueFrom", {}).get("secretKeyRef", {})
            if ref.get("name") == "bdc-secrets" and any(ref.get("key", "").startswith(p + "_") for p in PREFIXES):
                return True
        if any(item.get("secretRef", {}).get("name") == "bdc-secrets" for item in c.get("envFrom", [])):
            return True
    return False


class Migration:
    def __init__(self, kube, profile, run_id, replica_factory=Replica):
        self.kube, self.profile, self.run_id = kube, profile, run_id
        self.factory = replica_factory
        self.replicas = []
        self.workloads = {}
        self.quiesced = False
        self.config_changed = False
        self.target_writers_started = False
        self.snapshot = None
        self.status = state(kube)

    def update(self, phase, **fields):
        self.status.update(phase=phase, updated_at=datetime.now(timezone.utc).isoformat(), **fields)
        save_state(self.kube, self.status)
        print(json.dumps({"phase": phase, "run_id": self.run_id}), flush=True)

    def wait(self, predicate, seconds, label):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError(label)
            time.sleep(2)

    def preflight(self):
        if self.kube.get("configmaps", LOCK).get("data", {}).get("owner") != "migration:" + self.run_id:
            raise MigrationError("Migration does not own the operation lock")
        if set(self.profile["prefixes"]) != PREFIXES:
            raise MigrationError("Profile must cover all production PostgreSQL bindings")
        self.source = self.kube.secret("bdc-db-source")
        self.target = self.kube.secret("bdc-db-target")
        src = endpoint(self.source["runtime_url"], runtime=True)
        dst = endpoint(self.target["runtime_url"], runtime=True)
        source_direct = endpoint(self.source["direct_url"])
        target_direct = endpoint(self.target["direct_url"])
        if any("-pooler." in item["host"] for item in (source_direct, target_direct)):
            raise MigrationError("Use Neon direct endpoints, not pooler endpoints, for replication")
        if target_direct["user"] != dst["user"]:
            raise MigrationError("Target runtime role must own the restored schema")
        if self.source["direct_url"] == self.target["direct_url"]:
            raise MigrationError("Source and target must differ")
        live_config = self.kube.get("configmaps", "bdc-config")
        live_secret = self.kube.get("secrets", "bdc-secrets")
        decoded = {key: base64.b64decode(value).decode() for key, value in live_secret["data"].items()}
        databases = set()
        for prefix in sorted(PREFIXES):
            if (live_config["data"][prefix + "_HOST"] != src["host"] or
                    decoded[prefix + "_USER"] != src["user"] or decoded[prefix + "_PASSWORD"] != src["password"]):
                raise MigrationError("Source profile does not match every current application binding")
            databases.add(decoded[prefix + "_DB"])
        if live_config["data"].get("AI_DB_SSL") != src["sslmode"]:
            raise MigrationError("Source profile TLS setting does not match runtime configuration")
        for dep in self.kube.get("deployments")["items"]:
            if uses_database(dep["spec"]["template"]):
                self.workloads[dep["metadata"]["name"]] = dep
        if set(self.workloads) != set(self.profile["writers"]):
            raise MigrationError("Profile writer list does not match discovered database consumers")
        for resource in ("statefulsets", "cronjobs", "jobs"):
            for obj in self.kube.get(resource)["items"]:
                spec = obj["spec"]
                template = spec.get("jobTemplate", {}).get("spec", spec).get("template", {})
                if uses_database(template):
                    raise MigrationError("Database-consuming StatefulSets/Jobs/CronJobs require explicit maintenance support")
        for hpa in self.kube.get("horizontalpodautoscalers")["items"]:
            if hpa["spec"]["scaleTargetRef"]["name"] in self.workloads:
                raise MigrationError("Disable autoscaling of database writers before enabling the migration profile")
        if not self.workloads:
            raise MigrationError("No database writers discovered")
        for dep in self.workloads.values():
            if dep["spec"]["selector"].get("matchExpressions") or not dep["spec"]["selector"].get("matchLabels"):
                raise MigrationError("Writer selectors must use matchLabels")
        for pod in self.kube.get("pods")["items"]:
            if uses_database(pod) and not any(all(pod["metadata"].get("labels", {}).get(k) == v
                    for k, v in dep["spec"]["selector"]["matchLabels"].items()) for dep in self.workloads.values()):
                raise MigrationError("An unmanaged database writer Pod is running")
        self.snapshot = {
            "config": {k: v for k, v in live_config["data"].items() if k in {p + "_HOST" for p in PREFIXES} | {"AI_DB_SSL"}},
            "secret": {k: v for k, v in live_secret["data"].items() if k in {p + suffix for p in PREFIXES for suffix in ("_USER", "_PASSWORD")}},
            "managed_config": live_config["metadata"].get("annotations", {}).get(MANAGED),
            "managed_secret": live_secret["metadata"].get("annotations", {}).get(MANAGED),
            "replicas": {name: dep["spec"].get("replicas", 1) for name, dep in self.workloads.items()}}
        # Only the recovery Secret contains old credential values. Dashboard
        # state, logs, ConfigMaps and Pod specifications never contain URLs.
        self.kube.patch("secrets", RECOVERY, {"stringData": {"snapshot": json.dumps(self.snapshot), "run_id": self.run_id}})
        self.destination = dst
        for index, database in enumerate(sorted(databases)):
            replica = self.factory(self.source["direct_url"], self.target["direct_url"], database, self.run_id, index)
            self.replicas.append(replica)
            replica.preflight()
        # Reserve one table-sync worker/slot in addition to the persistent
        # per-database streams. Neon limits must be checked before any writes.
        count = len(self.replicas)
        source_conn, target_conn = self.replicas[0].source, self.replicas[0].target
        for conn, setting, used_sql in (
            (source_conn, "max_replication_slots", "SELECT count(*) FROM pg_replication_slots"),
            (source_conn, "max_wal_senders", "SELECT count(*) FROM pg_stat_activity WHERE backend_type='walsender'"),
            (target_conn, "max_logical_replication_workers", "SELECT count(*) FROM pg_stat_subscription WHERE pid IS NOT NULL"),
        ):
            capacity = int(query(conn, "SHOW " + setting)[0][0])
            used = query(conn, used_sql)[0][0]
            if capacity - used < count + 2:
                raise MigrationError("Insufficient replication capacity: " + setting + "; reserve database count + 2")

    def copy_ready(self, count=None):
        replicas = self.replicas[:count] if count else self.replicas
        progress = [r.progress() for r in replicas]
        lag = sum(p["lag_bytes"] or 0 for p in progress)
        if lag > self.profile.get("max_lag_bytes", 2147483648):
            raise MigrationError("Replication lag exceeded profile WAL budget")
        self.update("replicating", tables_ready=sum(p["ready"] for p in progress),
                    tables_total=sum(p["total"] for p in progress), lag_bytes=lag)
        return all(r.caught_up() for r in replicas)

    def scale(self, replicas):
        for name, count in replicas.items():
            self.kube.patch("deployments", name + "/scale", {"spec": {"replicas": count}})

    def no_writer_pods(self):
        pods = self.kube.get("pods")["items"]
        for dep in self.workloads.values():
            selector = dep["spec"]["selector"]["matchLabels"]
            if any(all(pod["metadata"].get("labels", {}).get(k) == v for k, v in selector.items())
                   and pod.get("status", {}).get("phase") not in ("Succeeded", "Failed") for pod in pods):
                return False
        return True

    def ready(self):
        for name, count in self.snapshot["replicas"].items():
            dep = self.kube.get("deployments", name)
            status = dep.get("status", {})
            if (status.get("observedGeneration", 0) < dep["metadata"]["generation"] or
                    status.get("updatedReplicas", 0) != count or status.get("availableReplicas", 0) != count or
                    status.get("replicas", 0) != count):
                return False
        return True

    def patch_destination(self):
        encode = lambda value: base64.b64encode(value.encode()).decode()
        self.config_changed = True  # set before either request: failure can be ambiguous
        annotations = {MANAGED: "migration:" + self.run_id}
        self.kube.patch("configmaps", "bdc-config", {"metadata": {"annotations": annotations}, "data": {
            **{p + "_HOST": self.destination["host"] for p in PREFIXES}, "AI_DB_SSL": self.destination["sslmode"]}})
        self.kube.patch("secrets", "bdc-secrets", {"metadata": {"annotations": annotations}, "data": {
            **{p + "_USER": encode(self.destination["user"]) for p in PREFIXES},
            **{p + "_PASSWORD": encode(self.destination["password"]) for p in PREFIXES}}})

    def restore_source(self):
        if self.config_changed:
            for resource, key, name in (("configmaps", "config", "bdc-config"), ("secrets", "secret", "bdc-secrets")):
                self.kube.patch(resource, name, {"data": self.snapshot[key], "metadata": {
                    "annotations": {MANAGED: self.snapshot["managed_" + key]}}})
        # Release table locks before allowing source writers to reconnect.
        for replica in self.replicas:
            replica.close()
        self.scale(self.snapshot["replicas"])
        self.wait(self.ready, 720, "Source rollout did not recover")

    def run(self):
        # Kubernetes can occasionally start a Job's program twice, even with
        # backoffLimit=0. Claim the queued state once with resourceVersion before
        # any database operation; a duplicate must NOT clean up or release locks.
        try:
            record = self.kube.get("configmaps", STATE)
            current = json.loads(record.get("data", {}).get("state", "{}"))
            if current.get("phase") != "queued" or current.get("run_id") != self.run_id:
                return False
            current["phase"] = "preflight"
            record["data"]["state"] = json.dumps(current)
            self.kube.request("PUT", "configmaps", STATE, record)
            self.status = current
        except Exception:
            return False
        try:
            self.update("preflight")
            self.preflight()
            self.update("preparing")
            copy_deadline = time.monotonic() + self.profile.get("timeout_seconds", 7200)
            for index, replica in enumerate(self.replicas):
                replica.prepare()
                replica.verify_runtime(self.source["runtime_url"], self.run_id)
                # Bootstrap one database at a time to avoid exhausting Neon's
                # temporary table-sync slots. Earlier streams remain active.
                self.wait(lambda: self.copy_ready(index + 1), max(1, copy_deadline - time.monotonic()), "Initial table copy timed out")
            self.wait(self.copy_ready, max(1, copy_deadline - time.monotonic()), "Initial replication timed out")
            for replica in self.replicas:
                replica.verify_runtime(self.target["runtime_url"], self.run_id)
            self.update("quiescing")
            self.quiesced = True
            self.scale({name: 0 for name in self.workloads})
            self.wait(self.no_writer_pods, 120, "Writers did not terminate")
            self.update("draining")
            for replica in self.replicas:
                replica.fence()
            self.wait(lambda: all(r.barrier_applied() for r in self.replicas), 60, "Final replication barrier timed out")
            for replica in self.replicas:
                replica.finalize()
                replica.verify_runtime(self.target["runtime_url"], self.run_id + ":final")
            # Drop replication before target writes; retain table locks until
            # application restart. Failure here still permits source recovery.
            for replica in self.replicas:
                replica.cleanup()
            self.update("cutover")
            self.patch_destination()
            self.update("rolling_out")
            self.target_writers_started = True  # never roll back past this point
            self.scale(self.snapshot["replicas"])
            self.wait(self.ready, 720, "Destination rollout requires operator recovery")
            # The new live database is the next run's source. Failure here
            # keeps the lock and requires operator recovery after target writes.
            self.kube.patch("secrets", "bdc-db-source", {"stringData": {
                "runtime_url": self.target["runtime_url"], "direct_url": self.target["direct_url"]}})
            self.update("succeeded")
            release(self.kube, "migration:" + self.run_id)
            return True
        except Exception as exc:
            # SQL errors can contain connection strings (CREATE SUBSCRIPTION).
            # Do not print exception text/tracebacks, even to Pod logs.
            failed_phase = self.status.get("phase", "unknown")
            recovered = not self.target_writers_started
            if recovered:
                try:
                    for replica in self.replicas:
                        replica.cleanup()
                    if self.quiesced:
                        self.restore_source()
                except Exception:
                    recovered = False
            reason = str(exc) if isinstance(exc, MigrationError) else "Operation failed; inspect prerequisites and database connectivity"
            self.update("failed_source_active" if recovered else "recovery_required", failed_phase=failed_phase,
                        error=reason, sqlstate=getattr(exc, "pgcode", None))
            if recovered:
                release(self.kube, "migration:" + self.run_id)
            return False
        finally:
            for replica in self.replicas:
                replica.close()


def interrupted(*_args):
    raise MigrationError("Migration interrupted")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        ok = Migration(Kube(), json.loads(os.environ["PROFILE"]), os.environ["RUN_ID"]).run()
    except Exception:
        print('{"phase":"recovery_required","reason":"Inspect durable operation state"}', flush=True)
        ok = False
    raise SystemExit(0 if ok else 1)
