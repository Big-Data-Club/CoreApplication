"""Logging access/provisioning contracts and opt-in real Loki/Alloy ingestion.

BDC_LOGGING_SMOKE=1 enables isolated local Docker integration checks.
"""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
LOGGING = ROOT / "k3s/logging"
spec = importlib.util.spec_from_file_location("enable_service_logs", ROOT / "scripts/enable-service-logs.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def dashboard():
    manifest = yaml.safe_load((LOGGING / "dashboards/bdc-service-logs.yaml").read_text())
    return json.loads(manifest["data"]["bdc-service-logs.json"])


class ProvisioningTests(unittest.TestCase):
    def test_existing_datasources_and_sidecar_settings_survive(self):
        existing = {"grafana": {"additionalDataSources": [{"uid": "traces", "type": "tempo"}],
                    "sidecar": {"dashboards": {"folderAnnotation": "folder", "searchNamespace": "ALL"}}}}
        before = copy.deepcopy(existing)
        patch = installer.provisioning_values(existing)
        self.assertEqual(existing, before)
        self.assertEqual(patch["grafana"]["additionalDataSources"][0], {"uid": "traces", "type": "tempo"})
        self.assertEqual(patch["grafana"]["sidecar"]["dashboards"]["folderAnnotation"], "folder")
        self.assertEqual(patch["grafana"]["sidecar"]["dashboards"]["searchNamespace"], "ALL")

    def test_provisioning_is_idempotent_and_never_changes_default_source(self):
        patch = installer.provisioning_values({})
        self.assertEqual(installer.provisioning_values(patch), patch)
        sources = patch["grafana"]["additionalDataSources"]
        self.assertEqual(len(sources), 1)
        self.assertFalse(sources[0]["isDefault"])

    def test_datasource_identity_collisions_abort(self):
        for source in ({"name": "BDC Logs", "uid": "foreign"}, {"uid": "bdc-loki", "type": "prometheus"}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                installer.provisioning_values({"grafana": {"additionalDataSources": [source]}})

    def test_incompatible_dashboard_discovery_aborts(self):
        for setting in ({"label": "other"}, {"labelValue": "true"}, {"searchNamespace": "other"}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                installer.provisioning_values({"grafana": {"sidecar": {"dashboards": setting}}})

    def test_installed_chart_version_is_preserved_and_release_must_be_deployed(self):
        release = {"chart": "kube-prometheus-stack-81.1.0", "status": "deployed"}
        self.assertEqual(installer.chart_version([release]), "81.1.0")
        for releases in ([], [release, release], [{**release, "status": "failed"}], [{**release, "chart": "other-1.0"}]):
            with self.subTest(releases=releases), self.assertRaises(ValueError):
                installer.chart_version(releases)

    def test_checked_in_helm_values_match_installer(self):
        values = yaml.safe_load((ROOT / "k3s/kube-prometheus-stack/values.yaml").read_text())
        self.assertIn(installer.DATASOURCE, values["grafana"]["additionalDataSources"])

    def test_default_plan_does_not_need_cluster_or_helm(self):
        result = subprocess.run([os.sys.executable, str(ROOT / "scripts/enable-service-logs.py")],
                                env={**os.environ, "PATH": ""}, text=True, capture_output=True, check=True)
        self.assertIn("no cluster access", result.stdout)

    def test_render_preserves_namespace_scoped_rbac_and_config_references(self):
        rendered = subprocess.run(["kubectl", "kustomize", str(LOGGING)], capture_output=True, text=True, check=True)
        resources = list(yaml.safe_load_all(rendered.stdout))
        identities = [(r["kind"], r["metadata"]["namespace"], r["metadata"]["name"]) for r in resources]
        self.assertEqual(len(identities), len(set(identities)))
        roles = {(r["metadata"]["namespace"], r["metadata"]["name"]): r for r in resources if r["kind"] == "Role"}
        self.assertIn(("default", "bdc-alloy-pod-discovery"), roles)
        self.assertIn(("default", "bdc-alloy-events"), roles)
        self.assertIn(("monitoring", "bdc-alloy-events"), roles)
        for role in roles.values():
            for rule in role["rules"]:
                self.assertLessEqual(set(rule["resources"]), {"pods", "events"})
                self.assertLessEqual(set(rule["verbs"]), {"get", "list", "watch"})
        configmaps = {r["metadata"]["name"] for r in resources if r["kind"] == "ConfigMap"}
        for resource in resources:
            if resource["kind"] not in ("Deployment", "DaemonSet"):
                continue
            self.assertEqual(resource["metadata"]["namespace"], "monitoring")
            for volume in resource["spec"]["template"]["spec"]["volumes"]:
                if "configMap" in volume:
                    self.assertIn(volume["configMap"]["name"], configmaps)
        self.assertFalse(any(r["kind"] == "Ingress" for r in resources))
        for resource in resources:
            if resource["kind"] == "Service":
                self.assertEqual(resource["spec"].get("type", "ClusterIP"), "ClusterIP")

    def test_dashboard_covers_worker_errors_and_infrastructure_failures(self):
        board = dashboard()
        self.assertEqual(board["uid"], "bdc-service-logs")
        panels = board["panels"]
        self.assertEqual(len({p["id"] for p in panels}), len(panels))
        queries = "\n".join(t["expr"] for p in panels for t in p["targets"])
        for signal in ('level="error"', "service_name", "kube_pod_status_phase", "OOMKilled", "bdc/kubernetes-events", "loki_write_dropped_entries_total"):
            self.assertIn(signal, queries)


@unittest.skipUnless(os.environ.get("BDC_LOGGING_SMOKE") == "1", "Set BDC_LOGGING_SMOKE=1 for local Docker integration")
class IngestionSmokeTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args, check=True):
        return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)

    @classmethod
    def setUpClass(cls):
        cls.prefix = "bdc-log-test-" + uuid.uuid4().hex[:10]
        cls.temp = tempfile.TemporaryDirectory(prefix=cls.prefix)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        cls.network = cls.prefix + "-net"
        cls.containers = []
        cls.docker("network", "create", cls.network)
        cls.addClassCleanup(cls.cleanup_docker)
        loki = cls.prefix + "-loki"
        cls.containers.append(loki)
        cls.docker("run", "-d", "--name", loki, "--network", cls.network, "--network-alias", "loki",
                   "-p", "127.0.0.1::3100", "--read-only", "--tmpfs", "/loki:uid=10001,gid=10001", "--tmpfs", "/tmp",
                   "-v", f"{LOGGING / 'config/loki.yaml'}:/config.yaml:ro", "grafana/loki:3.7.9", "-config.file=/config.yaml")
        port = cls.docker("inspect", "--format", '{{(index (index .NetworkSettings.Ports "3100/tcp") 0).HostPort}}', loki).stdout.strip()
        cls.url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 90
        while True:
            try:
                with urllib.request.urlopen(cls.url + "/ready", timeout=2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise AssertionError("Loki did not become ready: " + cls.docker("logs", loki).stdout)
                time.sleep(0.2)
        cls.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        def cri(text, stream="stdout", flag="F"):
            return f"{cls.now} {stream} {flag} {text}\n"
        records = [
            cri(json.dumps({"level": "ERROR", "service": "ai-service", "message": "Speech generation failed job=test-job", "exc_info": 'Traceback\nValueError: voice unavailable'})),
            cri(json.dumps({"level": "INFO", "message": "the word ERROR is harmless here"})),
            cri("[ERROR] 2026/10/22 12:00:00 go-error"),
            cri("ERROR: worker: python-error"),
            cri("Traceback (most recent call last):"),
            cri('  File "worker.py", line 1, in run'),
            cri("ValueError: traceback-tail"),
            cri("2026-10-22 12:00:01.000 ERROR 1 --- [main] java-error"),
            cri("\tat example.Service.run(Service.java:1)"),
            cri("2026-10-22T12:00:00 [app.worker] ERROR - python-fallback-error"),
            cri("[WARN] 2026/10/22 12:00:00 go-warning"),
            cri(json.dumps({"severity": "WARNING", "message": "json-warning"})),
            cri("INFO: stderr-info", stream="stderr"),
            cri('{"level":"ERROR","message":"partial-', flag="P"),
            cri('cri-error"}'),
        ]
        (cls.work / "worker.log").write_text("".join(records))
        (cls.work / "http.log").write_text(cri(json.dumps({"level": "INFO", "message": "http-ready"})))
        targets = [
            {"__path__": f"/fixtures/{filename}", "job": "bdc/containers", "namespace": "default",
             "service_name": service, "container": service, "pod": service + "-fixture"}
            for filename, service in (("worker.log", "ai-worker"), ("http.log", "ai-service"))
        ]
        source = (LOGGING / "config/logs.alloy").read_text()
        pipeline = source[source.index('loki.process "containers"'):].replace(
            "http://bdc-loki.monitoring.svc.cluster.local:3100", "http://loki:3100")
        event_source = (LOGGING / "config/events.alloy").read_text()
        event_pipeline = event_source[event_source.index('loki.process "events"'):event_source.index('loki.write "local"')]
        (cls.work / "events.log").write_text(json.dumps({"type": "Warning", "reason": "FailedScheduling", "message": "Insufficient memory"}) + "\n")
        config = 'logging { level = "warn" }\n' + "\n".join([
            'loki.source.file "fixtures" {',
            "targets = " + json.dumps(targets),
            "forward_to = [loki.process.containers.receiver]", "}",
            'loki.source.file "events_fixture" {',
            'targets = [{__path__ = "/fixtures/events.log", job = "bdc/kubernetes-events", namespace = "default"}]',
            "forward_to = [loki.process.events.receiver]", "}",
            pipeline, event_pipeline,
        ])
        # Alloy map attributes use '=' rather than JSON ':'. Build targets using
        # quoted strings but Alloy syntax (paths/labels stay literal test data).
        config = config.replace("targets = " + json.dumps(targets), "targets = [" + ",".join(
            "{" + ",".join(f"{k} = {json.dumps(v)}" for k, v in target.items()) + "}" for target in targets) + "]")
        (cls.work / "config.alloy").write_text(config)
        alloy = cls.prefix + "-alloy"
        cls.containers.append(alloy)
        cls.docker("run", "-d", "--name", alloy, "--network", cls.network,
                   "-v", f"{cls.work}:/fixtures:ro", "grafana/alloy:v1.21.1", "run", "/fixtures/config.alloy",
                   "--storage.path=/tmp/alloy", "--disable-reporting")
        deadline = time.monotonic() + 35
        while True:
            cls.records = cls.query('{job=~"bdc/.+"}')
            if len(cls.records) >= 12:
                break
            if time.monotonic() > deadline:
                raise AssertionError(f"Missing records ({len(cls.records)}): " + cls.docker("logs", alloy).stderr)
            time.sleep(0.2)

    @classmethod
    def cleanup_docker(cls):
        for container in reversed(cls.containers):
            cls.docker("rm", "-f", container, check=False)
        cls.docker("network", "rm", cls.network, check=False)

    @classmethod
    def query(cls, expression):
        params = urllib.parse.urlencode({"query": expression, "start": str(time.time_ns() - 600_000_000_000),
                                        "end": str(time.time_ns()), "limit": 1000})
        with urllib.request.urlopen(cls.url + "/loki/api/v1/query_range?" + params, timeout=15) as response:
            result = json.load(response)
        if result["data"]["resultType"] != "streams":
            return result["data"]["result"]
        return [(stream["stream"], value[1]) for stream in result["data"]["result"] for value in stream["values"]]

    def test_real_severity_and_cri_parsing(self):
        errors = self.query('{job="bdc/containers",level="error"}')
        self.assertEqual(len(errors), 6, errors)
        self.assertTrue(all(labels["service_name"] == "ai-worker" for labels, _ in errors))
        self.assertFalse(any("harmless" in line or "stderr-info" in line for _, line in errors))
        self.assertTrue(any("partial-cri-error" in line for _, line in errors))
        self.assertEqual(len(self.query('{job="bdc/containers",level="warn"}')), 2)

    def test_python_java_and_json_tracebacks_are_preserved(self):
        errors = self.query('{job="bdc/containers",level="error"}')
        python = next(line for _, line in errors if "python-error" in line)
        self.assertIn("traceback-tail", python)
        self.assertIn('File "worker.py"', python)
        java = next(line for _, line in errors if "java-error" in line)
        self.assertIn("Service.java:1", java)
        neural = next(line for _, line in errors if "test-job" in line)
        self.assertIn("voice unavailable", json.loads(neural)["exc_info"])

    def test_worker_identity_is_not_overwritten_by_json_service(self):
        self.assertTrue(self.query('{service_name="ai-worker"} |= "test-job"'))
        self.assertFalse(self.query('{service_name="ai-service"} |= "test-job"'))
        self.assertTrue(self.query('{service_name="ai-service"} |= "http-ready"'))

    def test_event_warnings_are_searchable(self):
        records = self.query('{job="bdc/kubernetes-events",level="warn"} |= "FailedScheduling"')
        self.assertEqual(len(records), 1)

    def test_every_dashboard_logql_query_parses_in_real_loki(self):
        substitutions = {"$__range": "1h", "$namespace": ".*", "$service": ".*", "$pod": ".*", "$level": ".*", "${search:raw}": ""}
        for panel in dashboard()["panels"]:
            if panel["datasource"]["type"] != "loki":
                continue
            expression = panel["targets"][0]["expr"]
            for key, value in substitutions.items():
                expression = expression.replace(key, value)
            with self.subTest(panel=panel["title"]):
                self.query(expression)


if __name__ == "__main__":
    unittest.main()
