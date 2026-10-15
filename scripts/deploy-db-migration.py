#!/usr/bin/env python3
"""Install/update the migration console without starting a migration."""
import importlib.util
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


RUNTIME_OBJECTS = {
    ("ConfigMap", "bdc-db-operation"),
    ("ConfigMap", "bdc-db-migration"),
    ("ConfigMap", "bdc-db-migration-settings"),
    ("Secret", "bdc-db-migration-recovery"),
    ("Secret", "bdc-db-source"),
    ("Secret", "bdc-db-target"),
}


def split_manifests(manifests):
    """Keep mutable state out of kubectl apply, including the live lock."""
    static, runtime = [], {}
    for document in re.split(r"(?m)^---\s*$", manifests):
        if not document.strip():
            continue
        kind = re.search(r"(?m)^kind: ([A-Za-z]+)\s*$", document)
        metadata = re.search(r"(?m)^metadata:\s*\n((?:[ \t].*\n?)*)", document)
        name = re.search(r"(?m)^  name: ([a-z0-9-]+)\s*$", metadata.group(1)) if metadata else None
        if not kind or not name:
            raise RuntimeError("Rendered manifest has no kind or metadata.name")
        identity = (kind.group(1), name.group(1))
        if identity in RUNTIME_OBJECTS:
            if identity in runtime:
                raise RuntimeError("Duplicate runtime resource in rendered manifests")
            runtime[identity] = document.strip() + "\n"
        else:
            static.append(document.strip())
    if set(runtime) != RUNTIME_OBJECTS:
        raise RuntimeError("Rendered manifests are missing runtime resources")
    return "\n---\n".join(static) + "\n", runtime


def ensure_runtime(kind, name, document):
    resource = kind.lower()
    existing = kubectl("-n", "default", "get", resource, name, "--ignore-not-found", "-o", "name")
    if not existing.strip():
        kubectl("create", "-f", "-", input_text=document)


def main():
    manifests, runtime = split_manifests(render(os.environ["MIGRATION_IMAGE"]))
    # Bootstrap only the lock before claiming it. Do not bootstrap by applying
    # the whole stack: an existing migration may own it already.
    ensure_runtime("ConfigMap", "bdc-db-operation", runtime[("ConfigMap", "bdc-db-operation")])
    spec = importlib.util.spec_from_file_location("db_operation_lock", Path(__file__).with_name("db-operation-lock.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = "deploy-migration-console:" + str(uuid.uuid4())
    # These manifests intentionally target the established default namespace.
    os.environ["DEPLOY_NAMESPACE"] = "default"
    module.lock("claim", owner)
    try:
        for kind, name in sorted(RUNTIME_OBJECTS - {("ConfigMap", "bdc-db-operation")}):
            ensure_runtime(kind, name, runtime[(kind, name)])
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
