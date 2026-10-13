#!/usr/bin/env python3
"""Enable discovery of migration dashboards on the existing kps Helm release."""
import json
import re
import subprocess


def main():
    result = subprocess.run(["helm", "list", "-n", "monitoring", "--filter", "^kps$", "-o", "json"],
                            text=True, capture_output=True, check=True)
    releases = json.loads(result.stdout)
    if len(releases) != 1 or releases[0]["status"] != "deployed":
        raise RuntimeError("Expected one deployed kps release in monitoring")
    match = re.fullmatch(r"kube-prometheus-stack-([0-9][0-9A-Za-z.+-]*)", releases[0]["chart"])
    if not match:
        raise RuntimeError("The kps release is not a kube-prometheus-stack chart")
    subprocess.run(["helm", "repo", "add", "prometheus-community", "https://prometheus-community.github.io/helm-charts", "--force-update"], check=True)
    subprocess.run(["helm", "repo", "update", "prometheus-community"], check=True)
    subprocess.run(["helm", "upgrade", "kps", "prometheus-community/kube-prometheus-stack",
                    "-n", "monitoring", "--version", match.group(1), "--reuse-values",
                    "--set", "grafana.sidecar.dashboards.enabled=true",
                    "--set", "grafana.sidecar.dashboards.searchNamespace=monitoring",
                    "--set", "grafana.sidecar.dashboards.label=grafana_dashboard",
                    "--set", "grafana.sidecar.dashboards.SCProvider=true",
                    "--wait", "--timeout", "10m"], check=True)
    print("Dashboard discovery enabled. Open /monitor/d/bdc-db-migration/.")


if __name__ == "__main__":
    main()
