import base64
import copy
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kube import APIError, LOCK, MANAGED, STATE, claim, state
from runner import Migration, PREFIXES, endpoint, uses_database
from replication import MigrationError, Replica, connect
from server import BASE, Handler, grafana_admin, make_job, start, validate_request

RUN_ID = "a" * 32
REQUEST_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROFILE = {"id": "test", "enabled": True, "label": "Test", "prefixes": sorted(PREFIXES), "writers": ["lms-service"]}
TARGET_URL = "postgresql://tester:test-only@ep-target.region.neon.tech/fixture?sslmode=require"


class FakeKube:
    def __init__(self):
        self.objects = {("configmaps", LOCK): {"metadata": {"resourceVersion": "1"}, "data": {}},
                        ("configmaps", STATE): {"metadata": {"resourceVersion": "1"}, "data": {}},
                        ("secrets", "bdc-db-migration-recovery"): {"data": {}},
                        ("configmaps", "bdc-config"): {"metadata": {}, "data": {**{p + "_HOST": "source.invalid" for p in PREFIXES}, "AI_DB_SSL": "require"}},
                        ("secrets", "bdc-secrets"): {"metadata": {}, "data": {}}
                        }
        for prefix in PREFIXES:
            for key, value in {"_USER": "tester", "_PASSWORD": "test-only", "_DB": "fixture"}.items():
                self.objects[("secrets", "bdc-secrets")]["data"][prefix + key] = base64.b64encode(value.encode()).decode()
        self.dep = {"metadata": {"name": "lms-service", "generation": 1}, "spec": {"replicas": 2,
                    "selector": {"matchLabels": {"app": "lms-service"}}, "template": {"spec": {"containers": [{"env": [
                        {"valueFrom": {"secretKeyRef": {"name": "bdc-secrets", "key": "LMS_POSTGRES_DB"}}}]}]}}}}
        self.calls = []
        self.endpoints = {name: {"runtime_url": f"postgresql://tester:test-only@{host}.invalid/fixture?sslmode=require",
                                 "direct_url": f"postgresql://tester:test-only@{host}.invalid/fixture?sslmode=require"}
                          for name, host in (("bdc-db-source", "source"), ("bdc-db-target", "target"))}
        self.create_error = False
        self.fail_patch = None
        self.fail_target_scale = False

    def get(self, resource, name=""):
        if (resource, name) in self.objects:
            return copy.deepcopy(self.objects[(resource, name)])
        if resource == "deployments":
            if not name:
                return {"items": [copy.deepcopy(self.dep)]}
            count = self.dep["spec"]["replicas"]
            return {**copy.deepcopy(self.dep), "status": {"observedGeneration": 1, "updatedReplicas": count,
                    "availableReplicas": count, "replicas": count}}
        return {"items": []}

    def secret(self, name):
        return copy.deepcopy(self.endpoints[name])

    def patch(self, resource, name, body):
        self.calls.append(("PATCH", resource, name, copy.deepcopy(body)))
        if self.fail_patch == (resource, name):
            self.fail_patch = None
            raise APIError(500)
        if name.endswith("/scale"):
            count = body["spec"]["replicas"]
            if self.fail_target_scale and count > 0:
                raise APIError(500)
            self.dep["spec"]["replicas"] = count
            return
        if resource == "secrets" and name in self.endpoints:
            self.endpoints[name].update(body["stringData"])
            return
        obj = self.objects.setdefault((resource, name), {})
        for key, value in body.items():
            if isinstance(value, dict):
                obj.setdefault(key, {}).update(copy.deepcopy(value))
            else:
                obj[key] = value

    def request(self, method, resource, name="", body=None):
        self.calls.append((method, resource, name, copy.deepcopy(body)))
        if method == "POST":
            if self.create_error:
                raise TimeoutError()
            return body
        if method == "PUT":
            current = self.objects[(resource, name)]
            if current["metadata"]["resourceVersion"] != body["metadata"]["resourceVersion"]:
                raise APIError(409)
            self.objects[(resource, name)] = copy.deepcopy(body)
            self.objects[(resource, name)]["metadata"]["resourceVersion"] = str(int(body["metadata"]["resourceVersion"]) + 1)


class FakeReplica:
    failure = None

    def __init__(self, *_args):
        self.calls = []
        self.source = SimpleNamespace(server_version=180000)
        self.target = SimpleNamespace(server_version=180000)

    def __getattr__(self, name):
        def call(*args):
            self.calls.append(name)
            if self.failure == name:
                raise RuntimeError("must never log postgresql://credentials")
            if name == "progress":
                return {"ready": 2, "total": 2, "lag_bytes": 0, "streaming": True}
            return True
        return call


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.kube = FakeKube()
        FakeReplica.failure = None
        self.env = patch.dict(os.environ, {"MIGRATION_IMAGE": "example/migration:fixture-sha", "PUBLIC_ORIGIN": "https://monitor.invalid"})
        self.env.start()
        self.addCleanup(self.env.stop)
        query_mock = patch("runner.query", side_effect=lambda conn, statement: [(20,)] if statement.startswith("SHOW ") else [(0,)])
        query_mock.start()
        self.addCleanup(query_mock.stop)

    def migrate(self):
        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, FakeReplica)
        with patch("sys.stdout", new=io.StringIO()) as output:
            ok = migration.run()
        self.output = output.getvalue()
        self.assertNotIn("credentials", output.getvalue())
        return ok, migration

    def test_success_switches_credentials_restores_replicas_and_releases_lock(self):
        ok, migration = self.migrate()
        self.assertTrue(ok)
        self.assertEqual(state(self.kube)["phase"], "succeeded")
        self.assertEqual(self.kube.get("configmaps", LOCK)["data"]["owner"], "")
        self.assertEqual(self.kube.dep["spec"]["replicas"], 2)
        self.assertEqual(self.kube.get("configmaps", "bdc-config")["data"]["POSTGRES_HOST"], "ep-target.region.neon.tech")
        self.assertEqual(self.kube.secret("bdc-db-source"), self.kube.secret("bdc-db-target"))
        self.assertEqual(migration.replicas[0].calls.index("fence") < migration.replicas[0].calls.index("finalize"), True)

    def test_successive_destinations_become_sources(self):
        self.assertTrue(self.migrate()[0])
        request_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        next_url = "postgresql://tester:test-only@ep-next.region.neon.tech/fixture?sslmode=require"
        start(self.kube, PROFILE, request_id, 42, next_url)
        migration = Migration(self.kube, PROFILE, request_id.replace("-", ""), FakeReplica)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertTrue(migration.run())
        self.assertEqual(migration.source["runtime_url"], TARGET_URL)
        self.assertEqual(self.kube.secret("bdc-db-source")["runtime_url"], next_url)
        self.assertEqual(self.kube.get("configmaps", "bdc-config")["data"]["POSTGRES_HOST"], "ep-next.region.neon.tech")

    def test_six_databases_rotate_three_active_subscriptions_through_final_barrier(self):
        for prefix in sorted(PREFIXES):
            self.kube.objects[("secrets", "bdc-secrets")]["data"][prefix + "_DB"] = base64.b64encode(prefix.lower().encode()).decode()

        class TrackedReplica(FakeReplica):
            instances = []
            maximum_active = 0

            def __init__(self, *_args):
                super().__init__(*_args)
                self.enabled = False
                self.seen_barrier = False
                self.__class__.instances.append(self)

            def mark_active(self):
                active = sum(r.enabled for r in self.instances)
                self.__class__.maximum_active = max(self.maximum_active, active)
                if active > 3:
                    raise AssertionError("More than three subscriptions active")

            def prepare(self):
                self.calls.append("prepare")
                self.enabled = True
                self.mark_active()

            def pause(self):
                self.calls.append("pause")
                self.enabled = False

            def no_workers(self):
                return not self.enabled

            def resume(self):
                self.calls.append("resume")
                self.enabled = True
                self.mark_active()

            def progress(self):
                return {"ready": 2, "total": 2, "lag_bytes": 0, "streaming": self.enabled}

            def caught_up(self):
                return self.enabled

            def barrier_applied(self):
                if self.enabled:
                    self.seen_barrier = True
                return self.enabled

            def finalize(self):
                self.calls.append("finalize")
                if not self.seen_barrier:
                    raise AssertionError("Finalized before the subscription replayed its marker")

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, TrackedReplica)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertTrue(migration.run())
        self.assertEqual(len(TrackedReplica.instances), 6)
        self.assertEqual(TrackedReplica.maximum_active, 3)
        self.assertTrue(all(r.seen_barrier for r in TrackedReplica.instances))
        self.assertTrue(any("pause" in r.calls and "resume" in r.calls for r in TrackedReplica.instances))
        self.assertEqual(state(self.kube)["phase"], "succeeded")

    def test_postgres_17_checks_origin_capacity_using_replication_slots(self):
        class PreviousMajor(FakeReplica):
            def __init__(self, *_args):
                super().__init__(*_args)
                self.target.server_version = 170000

        def checked_query(_conn, statement):
            if "max_active_replication_origins" in statement:
                raise AssertionError("PostgreSQL 17 has no separate origin capacity setting")
            return [(20,)] if statement.startswith("SHOW ") else [(0,)]

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, PreviousMajor)
        with patch("runner.query", side_effect=checked_query), patch("sys.stdout", new=io.StringIO()):
            self.assertTrue(migration.run())

    def test_source_promotion_failure_keeps_lock(self):
        self.kube.fail_patch = ("secrets", "bdc-db-source")
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertEqual(state(self.kube)["phase"], "recovery_required")
        self.assertEqual(self.kube.get("configmaps", LOCK)["data"]["owner"], "migration:" + RUN_ID)

    def test_preflight_failure_does_not_scale_or_patch_runtime(self):
        FakeReplica.failure = "preflight"
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertEqual(state(self.kube)["phase"], "failed_source_active")
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))
        diagnostic = json.loads(self.output.splitlines()[-1])
        self.assertEqual(diagnostic["failed_phase"], "preflight")
        self.assertTrue(diagnostic["failed_check"].startswith("database_prerequisites:"))
        self.assertIn("Operation failed", diagnostic["error"])
        self.assertNotIn("postgresql://", self.output + json.dumps(state(self.kube)))

    def test_runtime_connection_omits_startup_options_for_poolers(self):
        conn = MagicMock()
        with patch("replication.psycopg2.connect", return_value=conn) as open_connection:
            connect(TARGET_URL, "fixture", runtime=True)
            self.assertEqual(open_connection.call_args.kwargs, {})
            connect(TARGET_URL, "fixture")
            self.assertIn("options", open_connection.call_args.kwargs)

    def test_runtime_endpoint_failure_is_caught_before_preparing(self):
        class BrokenRuntime(FakeReplica):
            def check_runtime_endpoint(self, _url):
                raise psycopg2.OperationalError("postgresql://private-user:private-password@example.invalid/db")

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, BrokenRuntime)
        output = io.StringIO()
        with patch("sys.stdout", new=output):
            self.assertFalse(migration.run())
        diagnostic = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(diagnostic["failed_phase"], "preflight")
        self.assertEqual(diagnostic["failed_check"], "runtime_connectivity:source:" + ",".join(sorted(PREFIXES)))
        self.assertEqual(diagnostic["error_kind"], "postgres_connection")
        self.assertNotIn("private-password", output.getvalue() + json.dumps(state(self.kube)))
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))

    def test_prepare_failure_reports_safe_step_without_connection_details(self):
        class BrokenReplica(FakeReplica):
            def prepare(self):
                self.prepare_step = "subscription"
                raise psycopg2.OperationalError("postgresql://private-user:private-password@example.invalid/db")

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, BrokenReplica)
        output = io.StringIO()
        with patch("sys.stdout", new=output):
            self.assertFalse(migration.run())
        diagnostic = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(diagnostic["failed_phase"], "preparing")
        self.assertEqual(diagnostic["failed_check"], "prepare:" + ",".join(sorted(PREFIXES)) + ":subscription")
        self.assertEqual(diagnostic["error_kind"], "postgres_connection")
        self.assertNotIn("private-password", output.getvalue() + json.dumps(state(self.kube)))
        self.assertEqual(state(self.kube)["phase"], "failed_source_active")

    def test_lost_guard_is_detected_before_writers_stop(self):
        class LostGuard(FakeReplica):
            def guard_heartbeat(self):
                raise psycopg2.OperationalError("postgresql://private-user:private-password@example.invalid/db")

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, LostGuard)
        output = io.StringIO()
        with patch("sys.stdout", new=output):
            self.assertFalse(migration.run())
        diagnostic = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(diagnostic["failed_phase"], "preparing")
        self.assertEqual(diagnostic["failed_check"], "prepare:" + ",".join(sorted(PREFIXES)) + ":source_guard_heartbeat")
        self.assertEqual(diagnostic["error_kind"], "postgres_connection")
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))
        self.assertNotIn("private-password", output.getvalue() + json.dumps(state(self.kube)))

    def test_guard_failure_during_drain_reports_exact_safe_step_and_restores_source(self):
        class LostGuard(FakeReplica):
            def fence(self):
                self.drain_step = "source_guard_fence"
                raise psycopg2.OperationalError("postgresql://private-user:private-password@example.invalid/db")

        start(self.kube, PROFILE, REQUEST_ID, 42, TARGET_URL)
        migration = Migration(self.kube, PROFILE, RUN_ID, LostGuard)
        output = io.StringIO()
        with patch("sys.stdout", new=output):
            self.assertFalse(migration.run())
        diagnostic = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(diagnostic["failed_phase"], "draining")
        self.assertEqual(diagnostic["failed_check"], "drain:" + ",".join(sorted(PREFIXES)) + ":source_guard_fence")
        self.assertEqual(diagnostic["error_kind"], "postgres_connection")
        self.assertEqual(state(self.kube)["phase"], "failed_source_active")
        self.assertEqual(self.kube.dep["spec"]["replicas"], 2)
        self.assertNotIn("private-password", output.getvalue() + json.dumps(state(self.kube)))

    def test_binding_mismatch_reports_field_without_credential_values(self):
        secret = self.kube.objects[("secrets", "bdc-secrets")]["data"]
        secret["AI_POSTGRES_PASSWORD"] = base64.b64encode(b"private-password-fixture").decode()
        self.assertFalse(self.migrate()[0])
        diagnostic = json.loads(self.output.splitlines()[-1])
        self.assertEqual(diagnostic["failed_check"], "runtime_bindings")
        self.assertIn("AI_POSTGRES (password)", diagnostic["error"])
        self.assertNotIn("private-password-fixture", self.output + json.dumps(state(self.kube)))
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))

    def test_kubernetes_failure_reports_status_and_check(self):
        self.kube.fail_patch = ("secrets", "bdc-db-migration-recovery")
        self.assertFalse(self.migrate()[0])
        diagnostic = json.loads(self.output.splitlines()[-1])
        self.assertEqual(diagnostic["failed_check"], "recovery_snapshot")
        self.assertIn("HTTP 500", diagnostic["error"])

    def test_version_mismatch_reports_all_three_major_versions(self):
        replica = Replica.__new__(Replica)
        replica.source = MagicMock(server_version=180001)
        replica.target = MagicMock(server_version=180002)
        with patch("replication.subprocess.run", return_value=MagicMock(stdout=b"pg_dump (PostgreSQL) 17.6")), \
                patch("replication.query") as query_mock:
            with self.assertRaises(MigrationError) as raised:
                replica.preflight()
            query_mock.assert_not_called()
        self.assertIn("source=18, destination=18, pg_dump=17", str(raised.exception))
        self.assertIn("MIGRATION_PG_MAJOR", str(raised.exception))

    def test_matching_postgres_18_passes_prerequisites(self):
        replica = Replica.__new__(Replica)
        replica.source = MagicMock(server_version=180001)
        replica.target = MagicMock(server_version=180002)
        tables = [("public", "fixture", "r", "p", "d", True, False, False)]
        with patch("replication.subprocess.run", return_value=MagicMock(stdout=b"pg_dump (PostgreSQL) 18.1")), \
                patch("replication.query", side_effect=[[("logical",)], [(0,)], [(0,)], [], [(0,)], [], [], tables]):
            replica.preflight()
        self.assertEqual(replica.tables, tables)

    def test_partial_config_failure_restores_source_before_resuming(self):
        self.kube.fail_patch = ("secrets", "bdc-secrets")
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertEqual(state(self.kube)["phase"], "failed_source_active")
        self.assertEqual(self.kube.dep["spec"]["replicas"], 2)
        self.assertEqual(self.kube.get("configmaps", "bdc-config")["data"]["POSTGRES_HOST"], "source.invalid")

    def test_no_automatic_rollback_once_target_may_have_writes(self):
        self.kube.fail_target_scale = True
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertEqual(state(self.kube)["phase"], "recovery_required")
        self.assertEqual(self.kube.get("configmaps", LOCK)["data"]["owner"], "migration:" + RUN_ID)
        self.assertEqual(self.kube.get("configmaps", "bdc-config")["data"]["POSTGRES_HOST"], "ep-target.region.neon.tech")

    def test_failure_to_cleanup_keeps_lock(self):
        FakeReplica.failure = "cleanup"
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertEqual(state(self.kube)["phase"], "recovery_required")
        self.assertTrue(self.kube.get("configmaps", LOCK)["data"]["owner"])

    def test_duplicate_click_returns_same_job(self):
        first = start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL)
        second = start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL)
        self.assertEqual(first, second)
        self.assertEqual(sum(c[0] == "POST" for c in self.kube.calls), 1)
        self.assertEqual(sum(c[2] == "bdc-db-target" for c in self.kube.calls), 1)
        self.assertNotIn(TARGET_URL, json.dumps(first))

    def test_explicit_source_and_target_are_secret_only_and_retry_is_idempotent(self):
        source_url = "postgresql://tester:test-only@ep-source.region.neon.tech/ai?sslmode=require"
        first = start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL, source_url)
        call_count = len(self.kube.calls)
        self.assertEqual(start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL, source_url), first)
        self.assertEqual(len(self.kube.calls), call_count)
        self.assertEqual(self.kube.secret("bdc-db-source")["runtime_url"], source_url)
        self.assertNotIn(source_url, json.dumps(first))
        self.assertNotIn(source_url, json.dumps([c for c in self.kube.calls if c[1] != "secrets"]))
        migration = Migration(self.kube, PROFILE, RUN_ID, FakeReplica)
        with patch("sys.stdout", new=io.StringIO()):
            self.assertFalse(migration.run())  # source differs from live application bindings
        self.assertEqual(state(self.kube)["phase"], "failed_source_active")
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))

    def test_same_endpoint_with_different_database_paths_is_rejected_before_lock(self):
        with self.assertRaises(ValueError):
            start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL, TARGET_URL.replace("/fixture?", "/ai?"))
        self.assertFalse(self.kube.calls)

    def test_new_click_while_active_fails(self):
        start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL)
        with self.assertRaises(RuntimeError):
            start(self.kube, PROFILE, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", 1, TARGET_URL)

    def test_duplicate_job_execution_does_not_touch_completed_state(self):
        ok, _ = self.migrate()
        self.assertTrue(ok)
        calls = len(self.kube.calls)
        duplicate = Migration(self.kube, PROFILE, RUN_ID, FakeReplica)
        self.assertFalse(duplicate.run())
        self.assertEqual(state(self.kube)["phase"], "succeeded")
        self.assertEqual(len(self.kube.calls), calls)

    def test_ambiguous_job_creation_keeps_lock(self):
        self.kube.create_error = True
        with self.assertRaises(TimeoutError):
            start(self.kube, PROFILE, REQUEST_ID, 1, TARGET_URL)
        self.assertTrue(self.kube.get("configmaps", LOCK)["data"]["owner"])

    def test_job_has_no_retry_no_urls_and_bounded_runtime(self):
        job = make_job(PROFILE, RUN_ID, 42)
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["template"]["spec"]["restartPolicy"], "Never")
        self.assertNotIn("postgresql://", json.dumps(job))

    def test_csrf_origin_and_json_are_required(self):
        body = {"profile": "test", "request_id": REQUEST_ID, "target_url": "postgresql://u:p@ep-example-pooler.region.neon.tech/db?sslmode=require&channel_binding=require"}
        good = {"Origin": "https://monitor.invalid", "Content-Type": "application/json"}
        validate_request(good, body)
        for headers in ({}, {**good, "Origin": "https://attacker.invalid"}, {**good, "Content-Type": "text/plain"}):
            with self.assertRaises(ValueError):
                validate_request(headers, body)

    def test_http_mutation_requires_grafana_admin(self):
        handler = Handler.__new__(Handler)
        handler.headers = {}
        handler.path = BASE + "api/runs"
        response = []
        handler.send = lambda code, data: response.append(code)
        with patch("server.grafana_admin", return_value=None), patch("server.Kube") as kube:
            handler.do_POST()
            kube.assert_not_called()
        self.assertEqual(response, [403])

    def test_missing_cookie_does_not_contact_grafana(self):
        with patch("server.build_opener") as opener:
            self.assertIsNone(grafana_admin("unrelated=fixture"))
            opener.assert_not_called()

    def test_grafana_viewer_cannot_start_and_session_cookie_is_scoped(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"id": 7, "isGrafanaAdmin": False}).encode()
        with patch.dict(os.environ, {"GRAFANA_URL": "http://grafana.invalid/monitor"}), patch("server.build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertIsNone(grafana_admin("grafana_session=fixture; app_token=private"))
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.headers["Cookie"], "grafana_session=fixture")

    def test_endpoint_setup_preserves_encoded_password(self):
        path = Path(__file__).resolve().parents[3] / "scripts/configure-db-migration.py"
        spec = importlib.util.spec_from_file_location("endpoint_config", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.neon_urls("postgresql://fixture:p%40ss@ep-fixture-pooler.region.neon.tech/db?sslmode=require")
        self.assertEqual(result["direct_url"], "postgresql://fixture:p%40ss@ep-fixture.region.neon.tech/db?sslmode=require")
        pooled = module.neon_urls("postgresql://fixture:masked@ep-fixture-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
        self.assertEqual(pooled["direct_url"], "postgresql://fixture:masked@ep-fixture.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

    def test_unknown_profile_returns_404_without_kubernetes_write(self):
        handler = Handler.__new__(Handler)
        body = json.dumps({"profile": "missing", "request_id": REQUEST_ID, "target_url": "postgresql://u:p@ep-example-pooler.region.neon.tech/db?sslmode=require"}).encode()
        handler.headers = {"Origin": "https://monitor.invalid", "Content-Type": "application/json", "Content-Length": str(len(body))}
        handler.path, handler.rfile = BASE + "api/runs", io.BytesIO(body)
        response = []
        handler.send = lambda code, data: response.append(code)
        with patch("server.grafana_admin", return_value=42), patch("server.profiles", return_value=[PROFILE]), patch("server.Kube") as kube:
            handler.do_POST()
            kube.assert_not_called()
        self.assertEqual(response, [404])

    def test_runtime_endpoint_rejects_plaintext_and_unsupported_port(self):
        for url in ("postgresql://u:p@host/db", "postgresql://u:p@host:5433/db?sslmode=require"):
            with self.assertRaises(ValueError):
                endpoint(url, runtime=True)

    def test_new_worker_is_detected_and_blocks_incomplete_profile(self):
        self.kube.dep["metadata"]["name"] = "new-worker"
        ok, _ = self.migrate()
        self.assertFalse(ok)
        self.assertFalse(any(c[2].endswith("/scale") for c in self.kube.calls))

    def test_managed_config_survives_later_deploy(self):
        path = Path(__file__).resolve().parents[3] / "scripts/apply-runtime-config.py"
        spec = importlib.util.spec_from_file_location("runtime_config", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        desired = self.kube.get("configmaps", "bdc-config")
        live = copy.deepcopy(desired)
        live["metadata"]["annotations"] = {MANAGED: "migration:example"}
        live["data"]["POSTGRES_HOST"] = "target.invalid"
        desired["data"]["OTHER_SETTING"] = "new"
        merged = module.merge(desired, live)
        self.assertEqual(merged["data"]["POSTGRES_HOST"], "target.invalid")
        self.assertEqual(merged["data"]["OTHER_SETTING"], "new")


if __name__ == "__main__":
    unittest.main()
