#!/usr/bin/env python3
"""Provision Neon endpoint Secrets interactively; never print or persist URLs."""
import getpass
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/db-migration"))
from endpoints import neon_urls


class SetupError(RuntimeError):
    """Safe, credential-free operator message."""


def read_endpoint(label):
    try:
        entered = getpass.getpass(label + " runtime URL (hidden): ").strip()
    except EOFError:
        entered = ""
    if not entered:
        raise SetupError(f"No {label.lower()} URL was entered. Wait for this prompt, then paste the URL and press Enter.")
    try:
        return neon_urls(entered)
    except (ValueError, TypeError):
        raise SetupError(f"Invalid {label.lower()} Neon URL. Check scheme, host, database and sslmode=require.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="Enable the production profile after saving endpoint Secrets")
    parser.add_argument("--source-only", action="store_true", help="Enter the destination URL in /monitor/migrations/ for each run")
    args = parser.parse_args()
    source = read_endpoint("Source")
    target = {} if args.source_only else read_endpoint("Destination")
    if target and source["direct_url"] == target["direct_url"]:
        raise ValueError("Source and destination must differ")
    spec = importlib.util.spec_from_file_location("db_operation_lock", Path(__file__).with_name("db-operation-lock.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = "configure-endpoints:" + str(uuid.uuid4())
    module.lock("claim", owner)
    try:
        # Require the installed controller; avoid a successful-looking setup
        # against a different cluster or before first automatic deployment.
        module.kubectl("get", "configmap", "bdc-db-migration-settings", "-o", "name")
        for name, data in (("bdc-db-source", source), ("bdc-db-target", target)):
            obj = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": {
                "name": name, "namespace": os.environ.get("DEPLOY_NAMESPACE", "default")}, "stringData": data}
            result = subprocess.run(["kubectl", "apply", "--server-side", "--field-manager=bdc-db-endpoint-setup", "-f", "-"],
                                    input=json.dumps(obj), text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError("Could not provision endpoint Secret; no credentials were logged")
        if args.enable:
            patch = {"data": {"enabled_profiles": json.dumps(["production-cloud-cutover"])}}
            module.kubectl("patch", "configmap", "bdc-db-migration-settings", "--type=merge", "--patch-file=/dev/stdin", input_text=json.dumps(patch))
    finally:
        module.lock("release", owner)
    print("Endpoint Secrets configured. No migration has started.")
    if args.enable:
        print("Profile enabled. Allow up to two minutes for the mounted settings to refresh, then reload /monitor/migrations/.")


if __name__ == "__main__":
    try:
        main()
    except SetupError as exc:
        raise SystemExit(str(exc))
    except (Exception, KeyboardInterrupt):
        raise SystemExit("Endpoint configuration did not complete after URL entry. Check the database operation lock and Kubernetes access; no credentials were logged.")
