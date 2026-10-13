#!/usr/bin/env python3
"""Apply repo config while preserving migration-managed DB connection fields.

kubectl replaces the ConfigMap with resourceVersion so credentials are neither
logged nor placed in a last-applied annotation. Caller must own the operation lock.
"""
import json
import os
import subprocess

PREFIXES = ("POSTGRES", "LMS_POSTGRES", "LAB_POSTGRES", "CHAT_POSTGRES", "AI_POSTGRES", "DUTYLOG_POSTGRES")


def merge(desired, live):
    if live.get("metadata", {}).get("annotations", {}).get("bdc.io/db-managed"):
        for key in [p + "_HOST" for p in PREFIXES] + ["AI_DB_SSL"]:
            desired["data"][key] = live["data"][key]
        desired.setdefault("metadata", {}).setdefault("annotations", {})["bdc.io/db-managed"] = live["metadata"]["annotations"]["bdc.io/db-managed"]
    return desired


def run(*args, input_text=None):
    return subprocess.run(["kubectl", "-n", os.environ.get("DEPLOY_NAMESPACE", "default"), *args],
                          input=input_text, text=True, capture_output=True, check=True).stdout


if __name__ == "__main__":
    try:
        desired = json.loads(run("create", "--dry-run=client", "-f", "k3s/base/configmap.yaml", "-o", "json"))
        raw = run("get", "configmap", "bdc-config", "--ignore-not-found", "-o", "json")
        if raw.strip():
            live = json.loads(raw)
            desired = merge(desired, live)
            desired["metadata"]["resourceVersion"] = live["metadata"]["resourceVersion"]
            run("replace", "-f", "-", input_text=json.dumps(desired))
        else:
            run("create", "-f", "-", input_text=json.dumps(desired))
    except Exception:
        raise SystemExit("Runtime ConfigMap update failed; no configuration was logged")
