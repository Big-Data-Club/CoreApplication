import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ops/db-migration"))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeploymentTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("kubectl"), "Kustomize is validated separately on the CI host")
    def test_renderer_pins_both_images_without_credentials_or_migration_jobs(self):
        deploy = load_script("deploy-db-migration")
        image = "registry.invalid/team/migration@sha256:" + "a" * 64
        # Render real Kustomize manifests, without contacting a Kubernetes API.
        result = deploy.render(image)
        self.assertEqual(result.count(image), 2)
        self.assertNotIn("configure-immutable-tag", result)
        self.assertNotIn("kind: Job", result)
        self.assertNotIn("postgresql://", result)
        self.assertIn("name: bdc-db-migration-settings", result)
        self.assertNotIn("enabled_profiles:", result)

    def test_renderer_rejects_mutable_tags_before_kubectl(self):
        deploy = load_script("deploy-db-migration")
        with patch.object(deploy, "kubectl") as kubectl:
            with self.assertRaises(ValueError):
                deploy.render("registry.invalid/migration:latest")
            kubectl.assert_not_called()

    def test_runtime_enablement_survives_disabled_repository_default(self):
        from server import profiles
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profiles.json"
            setting = Path(directory) / "enabled_profiles"
            profile.write_text(json.dumps([{"id": "production", "enabled": False}]))
            with patch.dict(os.environ, {"PROFILES_FILE": str(profile), "ENABLED_PROFILES_FILE": str(setting)}):
                self.assertFalse(profiles()[0]["enabled"])
                setting.write_text('["production"]')
                self.assertTrue(profiles()[0]["enabled"])
                profile.write_text(json.dumps([{"id": "production", "enabled": False, "label": "Updated on push"}]))
                self.assertTrue(profiles()[0]["enabled"])
                self.assertEqual(profiles()[0]["label"], "Updated on push")
                setting.write_text('[]')
                self.assertFalse(profiles()[0]["enabled"])

    def test_dashboard_setup_reuses_installed_chart_version(self):
        from subprocess import CompletedProcess
        setup = load_script("enable-db-migration-dashboard")
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return CompletedProcess(command, 0, json.dumps([{"status": "deployed", "chart": "kube-prometheus-stack-70.4.2"}]))
        with patch.object(setup.subprocess, "run", side_effect=run):
            setup.main()
        upgrade = calls[-1]
        self.assertEqual(upgrade[upgrade.index("--version") + 1], "70.4.2")
        self.assertIn("--reuse-values", upgrade)
        self.assertNotIn("--install", upgrade)
