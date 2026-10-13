import base64
import copy
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kube import APIError, LOCK, MANAGED, STATE, claim, state
from runner import Migration, PREFIXES, endpoint, uses_database
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
