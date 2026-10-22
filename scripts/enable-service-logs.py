#!/usr/bin/env python3
"""Provision Loki/Alloy and the existing kps Grafana. No SSH or app rollout.

Without --apply, print the installation plan without accessing a cluster.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOGGING = ROOT / "k3s/logging"
DATASOURCE = {
    "name": "BDC Logs",
    "uid": "bdc-loki",
    "type": "loki",
    "access": "proxy",
    "url": "http://bdc-loki.monitoring.svc.cluster.local:3100",
    "isDefault": False,
    "editable": False,
    "jsonData": {"maxLines": 1000, "timeout": 60},
}


def provisioning_values(existing: dict) -> dict:
    """Preserve additional datasources and the current sidecar configuration."""
    grafana = existing.get("grafana") or {}
    sources = copy.deepcopy(grafana.get("additionalDataSources") or [])
    if not isinstance(sources, list) or any(not isinstance(s, dict) for s in sources):
        raise ValueError("grafana.additionalDataSources must be a list of objects")
    for source in sources:
        if source.get("name") == DATASOURCE["name"] and source.get("uid") != DATASOURCE["uid"]:
            raise ValueError("A different datasource already uses the name BDC Logs")
        if source.get("uid") == DATASOURCE["uid"] and source.get("type") != "loki":
            raise ValueError("Datasource uid bdc-loki is already used by another type")
    sources = [s for s in sources if s.get("uid") != DATASOURCE["uid"]]
    sources.append(copy.deepcopy(DATASOURCE))
    dashboards = copy.deepcopy((grafana.get("sidecar") or {}).get("dashboards") or {})
    # The existing performance and migration dashboards use this same label.
    if dashboards.get("label", "grafana_dashboard") != "grafana_dashboard":
        raise ValueError("Review the existing nonstandard Grafana dashboard label before installation")
    if dashboards.get("labelValue") not in (None, "", "1"):
        raise ValueError("Grafana dashboard labelValue must accept grafana_dashboard=1")
    if dashboards.get("searchNamespace") not in (None, "monitoring", "ALL"):
        raise ValueError("Grafana dashboard discovery must include monitoring")
    dashboards.update(enabled=True, label="grafana_dashboard", SCProvider=True)
    dashboards.setdefault("searchNamespace", "monitoring")
    return {"grafana": {"additionalDataSources": sources, "sidecar": {"dashboards": dashboards}}}


def chart_version(releases: list) -> str:
    if len(releases) != 1 or releases[0].get("status") != "deployed":
        raise ValueError("Expected one deployed Helm release kps in monitoring")
    match = re.fullmatch(r"kube-prometheus-stack-([0-9][0-9A-Za-z.+-]*)", releases[0].get("chart", ""))
    if not match:
        raise ValueError("Release kps must use kube-prometheus-stack")
    return match.group(1)


def run(*args: str, capture: bool = False):
    return subprocess.run(list(args), text=True, check=True, capture_output=capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply to the current kubectl/Helm context")
    args = parser.parse_args()
    if not args.apply:
        print("Plan (no cluster access):")
        print("1. Validate k3s/logging against the current cluster.")
        print("2. Keep kps on its installed chart version and preserve its configured datasources.")
        print("3. Enable BDC Logs and dashboard discovery on the existing Grafana.")
        print("4. Install single-instance Loki (72h retention), node log collectors and an events reader.")
        print("5. Wait for all three workloads. Application pods are not restarted.")
        print("Run with --apply on an authorised kubectl/Helm workstation to install.")
        return
    for executable in ("kubectl", "helm"):
        if shutil.which(executable) is None:
            parser.error(f"{executable} is required")
    context = run("kubectl", "config", "current-context", capture=True).stdout.strip()
    print(f"Installing in context {context}, namespace monitoring", flush=True)
    releases = json.loads(run("helm", "list", "--kube-context", context, "-n", "monitoring", "--filter", "^kps$", "-o", "json", capture=True).stdout)
    version = chart_version(releases)
    existing = json.loads(run("helm", "get", "values", "kps", "--kube-context", context, "-n", "monitoring", "-o", "json", capture=True).stdout) or {}
    patch = provisioning_values(existing)
    # Validate CRDs, RBAC and admission before changing the Helm release.
    run("kubectl", "--context", context, "apply", "--dry-run=server", "-k", str(LOGGING))
    run("helm", "repo", "add", "prometheus-community", "https://prometheus-community.github.io/helm-charts", "--force-update")
    run("helm", "repo", "update", "prometheus-community")
    # Additional datasource settings can contain credentials in existing values.
    # TemporaryDirectory and NamedTemporaryFile keep them outside Git and 0600.
    with tempfile.TemporaryDirectory(prefix="bdc-grafana-") as temp:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=temp) as handle:
            json.dump(patch, handle)
            handle.flush()
            run("helm", "upgrade", "kps", "prometheus-community/kube-prometheus-stack", "-n", "monitoring",
                "--kube-context", context,
                "--version", version, "--reuse-values", "--values", handle.name,
                "--wait", "--timeout", "10m")
    run("kubectl", "--context", context, "apply", "-k", str(LOGGING))
    for workload in ("deployment/bdc-loki", "daemonset/bdc-alloy-logs", "deployment/bdc-alloy-events"):
        run("kubectl", "--context", context, "-n", "monitoring", "rollout", "status", workload, "--timeout=5m")
    print("Workloads ready. Open /monitor/d/bdc-service-logs/ and confirm recent logs and Kubernetes events.")
    print("Historical logs already deleted from the node cannot be recovered.")


if __name__ == "__main__":
    main()
