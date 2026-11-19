"""Exercise disk gates, release application and rollback without a real cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DeploymentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "bin").mkdir()
        (self.root / "scripts").mkdir()
        self.calls = self.root / "calls"
        self.calls.touch()
        self.disk = self.root / "disk"
        self.disk.write_text("50")
        self.env = {**os.environ, "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
                    "CALLS": str(self.calls), "DISK": str(self.disk),
                    "REGISTRY_NAMESPACE": "test", "IMAGE_TAG": "new-sha",
                    "BDC_OPERATION_OWNER": "offline-test", "SERVICES": "ai-service,ai-worker"}

    def executable(self, path, content):
        path = self.root / path
        path.write_text(content)
        path.chmod(0o755)

    def commands(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def run_script(self, name, *args, **env):
        return subprocess.run(["bash", str(ROOT / "scripts" / name), *args], cwd=self.root,
                              env={**self.env, **env}, text=True, capture_output=True, timeout=10)

    def setup_maintenance(self):
        self.executable("bin/kubectl", '#!/bin/sh\nexit 0\n')
        self.executable("bin/k3s", '#!/bin/sh\nexit 0\n')
        self.executable("bin/df", '#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/test 100 90 10 $(cat "$DISK")% /"\n')
        self.executable("bin/sudo", '#!/bin/sh\necho prune >> "$CALLS"\nif [ "${PRUNE_FAIL:-0}" = 1 ]; then exit 1; fi\necho "${AFTER_PRUNE:-50}" > "$DISK"\n')

    def test_prune_failure_stops_preflight(self):
        self.setup_maintenance()
        self.disk.write_text("94")
        result = self.run_script("k3s-maintenance.sh", "--phase", "pre", PRUNE_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Stopping before rollout", result.stderr)

    def test_successful_prune_must_actually_free_space(self):
        self.setup_maintenance()
        self.disk.write_text("94")
        result = self.run_script("k3s-maintenance.sh", "--phase", "pre", AFTER_PRUNE="94")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_script("k3s-maintenance.sh", "--phase", "pre", AFTER_PRUNE="70")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failure_cleanup_keeps_images_for_rollback(self):
        self.setup_maintenance()
        self.disk.write_text("94")
        result = self.run_script("k3s-maintenance.sh", "--phase", "post", K3S_PRUNE_IMAGES="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), "")
        self.assertEqual(self.disk.read_text(), "94")

    def setup_deployment(self):
        for name in ("render-deployment.py",):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        (self.root / "scripts/db-operation-lock.py").write_text("")
        (self.root / "scripts/apply-runtime-config.py").write_text("")
        self.executable("scripts/k3s-maintenance.sh", '#!/bin/sh\nexit "${FAIL_MAINTENANCE:-0}"\n')
        shutil.copytree(ROOT / "k3s", self.root / "k3s")
        self.executable("bin/kubectl", f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
import yaml
a = sys.argv[1:]
payload = sys.stdin.read() if a[:3] == ['apply', '-f', '-'] else None
with open(os.environ['CALLS'], 'a') as out:
    out.write(json.dumps({'args': a, 'payload': json.loads(payload) if payload else None}) + '\\n')
if a[:1] == ['create'] and '--dry-run=client' in a:
    docs = list(yaml.safe_load_all(Path(a[a.index('-f') + 1]).read_text()))
    renders = sum(json.loads(line)['args'][:1] == ['create'] for line in Path(os.environ['CALLS']).read_text().splitlines())
    if str(renders) == os.environ.get('FAIL_RENDER_AT'):
        print('{}\\ninvalid JSON')
    elif os.environ.get('RENDER_LIST') == '1':
        print(json.dumps({'kind': 'List', 'items': docs}))
    else:
        for doc in docs:
            print(json.dumps(doc, indent=2))
elif a[:1] == ['get']:
    target = a[1]
    if target == 'deployment': pass  # suspended gateways do not exist
    elif target.startswith('deployment/'):
        if target != os.environ.get('NEW_DEPLOYMENT'):
            print('test/bdc-ai:old-sha' if any('jsonpath=' in x for x in a) else target)
    elif target == 'pods' and any('jsonpath=' in x for x in a): print('old-running-pod')
    elif target == 'pod' and os.environ.get('HAS_PREVIOUS') == '1': print('ai-service')
elif a[:2] == ['rollout', 'status'] and a[2] == os.environ.get('FAIL_ROLLOUT'):
    sys.exit(1)
''')

    def test_shared_manifest_applies_only_selected_workload_with_final_image(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", SERVICES="ai-service")
        self.assertEqual(result.returncode, 0, result.stderr)
        applied = [c['payload'] for c in self.commands() if c['payload']]
        self.assertEqual(len(applied), 1)
        deployments = [d for d in applied[0]['items'] if d['kind'] == 'Deployment']
        self.assertEqual([d['metadata']['name'] for d in deployments], ['ai-service'])
        self.assertEqual(deployments[0]['spec']['template']['spec']['containers'][0]['image'], 'test/bdc-ai:new-sha')

    def test_waits_for_each_rollout_before_applying_next_workload(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.commands()
        apply_indices = [i for i, c in enumerate(calls) if c['payload']]
        first_wait = next(i for i, c in enumerate(calls) if c['args'][:3] == ['rollout', 'status', 'deployment/ai-service'])
        self.assertLess(apply_indices[0], first_wait)
        self.assertLess(first_wait, apply_indices[1])

    def test_kubectl_list_output_is_also_supported(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", SERVICES="ai-service", RENDER_LIST="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        applied = [c['payload'] for c in self.commands() if c['payload']]
        self.assertEqual(len(applied), 1)
        self.assertEqual([d['metadata']['name'] for d in applied[0]['items'] if d['kind'] == 'Deployment'], ['ai-service'])

    def test_failed_render_rolls_back_once_and_never_applies_partial_output(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", FAIL_RENDER_AT="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.count('Deployment failed; rolling back'), 1)
        self.assertEqual(sum(bool(c['payload']) for c in self.commands()), 1)
        restored = [c for c in self.commands() if c['args'][:3] == ['set', 'image', 'deployment/ai-service']]
        self.assertEqual(len(restored), 1)
        self.assertIn('ai-service=test/bdc-ai:old-sha', restored[0]['args'])

    def test_failed_rollout_restores_image_and_does_not_start_next_workload(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", FAIL_ROLLOUT="deployment/ai-service")
        self.assertNotEqual(result.returncode, 0)
        calls = self.commands()
        self.assertEqual(sum(bool(c['payload']) for c in calls), 1)
        self.assertTrue(any(c['args'][:3] == ['set', 'image', 'deployment/ai-service']
                            and 'ai-service=test/bdc-ai:old-sha' in c['args'] for c in calls))
        self.assertFalse(any('--previous' in c['args'] or '--force' in c['args'] for c in calls))

    def test_disk_gate_prevents_deployment_changes(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", FAIL_MAINTENANCE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['args'][0] in ('apply', 'set', 'scale') for c in self.commands()))

    def test_previous_logs_are_requested_only_for_a_terminated_prior_container(self):
        self.setup_deployment()
        self.run_script("deploy-production.sh", SERVICES="ai-service",
                        FAIL_ROLLOUT="deployment/ai-service", HAS_PREVIOUS="1")
        previous = [c['args'] for c in self.commands() if '--previous' in c['args']]
        self.assertEqual(len(previous), 1)
        self.assertIn('ai-service', previous[0])
        self.assertIn('-c', previous[0])

    def test_failure_removes_only_newly_created_deployment(self):
        self.setup_deployment()
        result = self.run_script("deploy-production.sh", SERVICES="ai-service",
            FAIL_ROLLOUT="deployment/ai-service", NEW_DEPLOYMENT="deployment/ai-service")
        self.assertNotEqual(result.returncode, 0)
        calls = [c['args'] for c in self.commands()]
        self.assertTrue(any(c[:3] == ['delete', 'deployment', 'ai-service'] for c in calls))
        self.assertFalse(any(c[:2] == ['set', 'image'] for c in calls))

    def test_legacy_restart_failure_stops_remaining_restarts(self):
        import yaml
        self.setup_deployment()
        workflow = yaml.load((ROOT / '.github/workflows/cd-production.yml').read_text(), Loader=yaml.BaseLoader)
        script = next(step['run'] for step in workflow['jobs']['deploy']['steps']
                      if step['name'] == 'Selective Kubernetes Rollout')
        result = subprocess.run(['bash', '-c', script], cwd=self.root, text=True,
            capture_output=True, timeout=10, env={**self.env, 'SELECTED_SERVICES': 'ai-service,ai-worker',
                                                'FAIL_ROLLOUT': 'deployment/ai-service'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['args'][:3] == ['rollout', 'restart', 'deployment/ai-worker']
                             for c in self.commands()))


if __name__ == "__main__":
    unittest.main()
