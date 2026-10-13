#!/usr/bin/env python3
"""Install/update the migration console without starting a migration."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


def kubectl(*args, input_text=None):
    result = subprocess.run(["kubectl", *args], input=input_text, text=True, capture_output=True)
    if result.returncode:
        # This script never requests Secret contents. Preserve useful kubectl
        # diagnostics (image pull, permissions, readiness) for the deploy log.
        raise RuntimeError(result.stderr.strip() or "kubectl failed")
    return result.stdout


def render(image):
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", image):
        raise ValueError("MIGRATION_IMAGE must be a registry image pinned by SHA256 digest")
    content = kubectl("kustomize", "k3s/db-migration")
    placeholder = "bdc-db-migration:configure-immutable-tag"
    if content.count(placeholder) != 2:
        raise RuntimeError("Expected exactly the console and worker image references")
    return content.replace(placeholder, image)


def main():
    manifests = render(os.environ["MIGRATION_IMAGE"])
    # Bootstrap only the lock before claiming it. Do not bootstrap by applying
    # the whole stack: an existing migration may own it already.
    raw = kubectl("-n", "default", "get", "configmap", "bdc-db-operation", "--ignore-not-found", "-o", "name")
    if not raw.strip():
        obj = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "bdc-db-operation", "namespace": "default"}}
        kubectl("create", "-f", "-", input_text=json.dumps(obj))
    spec = importlib.util.spec_from_file_location("db_operation_lock", Path(__file__).with_name("db-operation-lock.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = "deploy-migration-console:" + str(uuid.uuid4())
    # These manifests intentionally target the established default namespace.
    os.environ["DEPLOY_NAMESPACE"] = "default"
    module.lock("claim", owner)
    try:
        kubectl("-n", "default", "get", "secret", "dockerhub-registry", "-o", "name")
        print(kubectl("apply", "-f", "-", input_text=manifests), end="")
        print(kubectl("-n", "default", "rollout", "status", "deployment/bdc-db-migration-console", "--timeout=5m"), end="")
    finally:
        module.lock("release", owner)
    print("Migration console deployed at /monitor/migrations/. No database migration was started.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(str(exc))
