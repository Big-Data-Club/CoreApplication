#!/usr/bin/env python3
"""Provision Neon endpoint Secrets interactively; never print or persist URLs."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid
from urllib.parse import urlsplit, parse_qs


def neon_urls(url):
    parts = urlsplit(url)
    if (parts.scheme not in ("postgres", "postgresql") or not parts.hostname or
            not parts.hostname.endswith(".neon.tech") or not parts.username or not parts.password or
            parts.port not in (None, 5432) or not parts.path.strip("/")):
        raise ValueError("Use a complete Neon PostgreSQL URL on port 5432")
    options = parse_qs(parts.query)
    if options.get("sslmode", [""])[0] not in ("require", "verify-full", "verify-ca"):
        raise ValueError("Neon URLs must require TLS")
    if set(options) - {"sslmode", "channel_binding"}:
        raise ValueError("Only sslmode and channel_binding URL options are supported")
    direct_host = parts.hostname.replace("-pooler.", ".", 1)
    # Preserve percent-encoded user/password and all non-host URL components.
    direct_netloc = parts.netloc.replace("@" + parts.hostname, "@" + direct_host, 1)
    return {"runtime_url": url, "direct_url": parts._replace(netloc=direct_netloc).geturl()}


def main():
    source = neon_urls(getpass.getpass("Source runtime URL (hidden): "))
    target = neon_urls(getpass.getpass("Destination runtime URL (hidden): "))
    if source["direct_url"] == target["direct_url"]:
        raise ValueError("Source and destination must differ")
    spec = importlib.util.spec_from_file_location("db_operation_lock", Path(__file__).with_name("db-operation-lock.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = "configure-endpoints:" + str(uuid.uuid4())
    module.lock("claim", owner)
    try:
        for name, data in (("bdc-db-source", source), ("bdc-db-target", target)):
            obj = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": {
                "name": name, "namespace": os.environ.get("DEPLOY_NAMESPACE", "default")}, "stringData": data}
            result = subprocess.run(["kubectl", "apply", "--server-side", "--field-manager=bdc-db-endpoint-setup", "-f", "-"],
                                    input=json.dumps(obj), text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError("Could not provision endpoint Secret; no credentials were logged")
    finally:
        module.lock("release", owner)
    print("Source and destination Secrets configured. No migration has started.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        raise SystemExit("Endpoint configuration did not complete. Check Neon URL format, TLS and Kubernetes access.")
