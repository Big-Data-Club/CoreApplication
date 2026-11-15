"""Exercise release selection without Docker Hub, production credentials or K3s."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(path):
    # BaseLoader preserves GitHub's `on` key instead of interpreting it as True.
    return yaml.load((ROOT / path).read_text(), Loader=yaml.BaseLoader)


class ReleaseRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = workflow(".github/workflows/production.yml")

    def select(self, **overrides):
        job = self.production["jobs"]["detect-changes"]
        step = next(step for step in job["steps"] if step.get("id") == "select")
        env = {**os.environ, **{name: "false" for name in step["env"] if name.endswith("_CHANGED")},
               "GITHUB_EVENT_NAME": "push", "MANUAL_IMAGE_TAG": "", "MANUAL_SERVICES": "", **overrides}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            run = subprocess.run(["bash", "-c", step["run"]], cwd=ROOT,
                                 env={**env, "GITHUB_OUTPUT": str(output)}, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_pointer_only_reuses_frontend_image_without_build(self):
        result = self.select(FRONTEND_CHANGED="true")
        self.assertEqual(result["should_build"], "false")
        self.assertEqual(json.loads(result["matrix"]), {"include": []})
        self.assertEqual(result["services"], "frontend")
        sha = subprocess.check_output(["git", "rev-parse", "HEAD:frontend"], cwd=ROOT, text=True).strip()
        self.assertEqual(result["frontend_image_tag"], sha)

    def test_mixed_commit_builds_only_backend_and_combines_rollout(self):
        result = self.select(FRONTEND_CHANGED="true", LMS_CHANGED="true")
        self.assertEqual(result["should_build"], "true")
        self.assertEqual(result["services"], "lms-service,frontend")
        self.assertEqual(json.loads(result["matrix"])["include"], [{"image": "bdc-lms", "context": "lms-service"}])

    def test_backend_only_does_not_wait_for_frontend(self):
        result = self.select(RECOMMENDER_CHANGED="true")
        self.assertEqual(result["services"], "recommender-service")
        self.assertNotIn("frontend_image_tag", result)

    def test_no_changes_produces_no_release(self):
        result = self.select()
        self.assertEqual(result["services"], "")
        self.assertEqual(result["should_build"], "false")

    def test_manual_frontend_rollback_uses_requested_tag(self):
        result = self.select(GITHUB_EVENT_NAME="workflow_dispatch", MANUAL_IMAGE_TAG="previous-sha",
                             MANUAL_SERVICES="frontend", FRONTEND_CHANGED="true", LMS_CHANGED="true")
        self.assertEqual(result["services"], "frontend")
        self.assertEqual(result["frontend_image_tag"], "previous-sha")
        self.assertEqual(result["should_build"], "false")

    def test_ci_and_restart_workflows_cannot_double_release_main(self):
        ci = workflow(".github/workflows/ci.yml")
        self.assertNotIn("main", ci["on"]["push"]["branches"])
        matrix = ci["jobs"]["build-and-test"]["strategy"]["matrix"]["include"]
        self.assertNotIn("frontend", [item["service"] for item in matrix])
        legacy = workflow(".github/workflows/cd-production.yml")
        self.assertEqual(set(legacy["on"]), {"workflow_dispatch"})
        self.assertEqual(legacy["concurrency"]["group"], self.production["concurrency"]["group"])
        self.assertFalse((ROOT / ".github/workflows/frontend-pointer-deploy.yml").exists())

    def test_workflow_only_edits_do_not_select_application_builds(self):
        changes = next(step for step in self.production["jobs"]["detect-changes"]["steps"] if step.get("id") == "changes")
        filters = yaml.safe_load(changes["with"]["filters"])
        for paths in filters.values():
            self.assertNotIn(".github/workflows/production.yml", paths)

    def test_missing_image_fails_before_deployment_and_published_image_passes(self):
        job = self.production["jobs"]["verify-frontend-image"]
        script = next(step["run"] for step in job["steps"] if "run" in step)
        deploy = self.production["jobs"]["deploy"]
        self.assertIn("verify-frontend-image", deploy["needs"])
        self.assertIn("needs.verify-frontend-image.result == 'success'", deploy["if"])
        with tempfile.TemporaryDirectory() as directory:
            bin_path = Path(directory)
            calls = bin_path / "calls"
            for name, code in {"docker": 'echo "$*" >> "$MOCK_CALLS"\nexit "$MOCK_STATUS"', "sleep": "exit 0"}.items():
                file = bin_path / name
                file.write_text("#!/bin/sh\n" + code + "\n")
                file.chmod(0o755)
            env = {**os.environ, "PATH": f"{directory}:{os.environ['PATH']}", "REGISTRY_NAMESPACE": "test",
                   "FRONTEND_IMAGE_TAG": "pinned-sha", "MOCK_CALLS": str(calls)}
            for status, expected_calls in [("0", 1), ("1", 30)]:
                calls.write_text("")
                run = subprocess.run(["bash", "-c", script], env={**env, "MOCK_STATUS": status},
                                     text=True, capture_output=True, timeout=10)
                self.assertEqual(run.returncode, int(status), run.stderr)
                self.assertEqual(calls.read_text().splitlines(),
                                 ["buildx imagetools inspect test/bdc-frontend:pinned-sha"] * expected_calls)


if __name__ == "__main__":
    unittest.main()
