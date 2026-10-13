#!/usr/bin/env python3
"""Share a Kubernetes CAS lock with DB migration Jobs; no automatic expiry.

Legacy clusters without the optional migration control plane remain supported.
Only NotFound is ignored; auth/network/API failures fail closed.
"""
import json
import os
import subprocess
import sys

NAME = "bdc-db-operation"


def kubectl(*args, input_text=None):
    result = subprocess.run(["kubectl", "-n", os.environ.get("DEPLOY_NAMESPACE", "default"), *args],
                            input=input_text, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Database operation lock request failed")
    return result.stdout


def lock(action, owner):
    raw = kubectl("get", "configmap", NAME, "--ignore-not-found", "-o", "json")
    if not raw.strip():
        return
    obj = json.loads(raw)
    held = obj.setdefault("data", {}).get("owner", "")
    if action == "claim":
        if held:
            raise RuntimeError("Deployment blocked by an active database operation")
        obj["data"]["owner"] = owner
    elif action == "check":
        if held != owner:
            raise RuntimeError("Database operation lock is not owned by this deployment")
        return
    elif action == "release":
        if held != owner:
            raise RuntimeError("Refusing to release another operation's lock")
        obj["data"]["owner"] = ""
    else:
        raise ValueError("Expected claim, check or release")
    kubectl("replace", "-f", "-", input_text=json.dumps(obj))


if __name__ == "__main__":
    try:
        lock(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
