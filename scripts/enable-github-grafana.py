#!/usr/bin/env python3
"""Install GitHub datasource and optional management dashboards in an isolated organization.

Default: print a plan only. Run --apply on the VM; never pass a PAT to this script.
Standalone Python 3 script; requires kubectl and Helm only when applying.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = "grafana-github-datasource@2.9.4"
SOURCE_UID = "bdc-github"
SOURCE_FILE = "github-monitor.yaml"
SECRET_REF = {"secretKeyRef": {"name": "github-monitor", "key": "token"}}


def provisioning_values(existing: dict, org_id: int) -> dict:
    if isinstance(org_id, bool) or org_id <= 1:
        raise ValueError("Use a dedicated management organization ID greater than 1, not the default organization.")
    grafana = existing.get("grafana") or {}
    env = copy.deepcopy(grafana.get("env") or {})
    refs = copy.deepcopy(grafana.get("envValueFrom") or {})
    files = copy.deepcopy(grafana.get("datasources") or {})
    if not all(isinstance(value, dict) for value in (env, refs, files)):
        raise ValueError("Existing Grafana env/envValueFrom/datasources must be mappings; review Helm values locally.")
    if "GITHUB_MONITOR_TOKEN" in env:
        raise ValueError("GITHUB_MONITOR_TOKEN is already configured as a literal env value; migrate it to a Secret first.")
    if "GITHUB_MONITOR_TOKEN" in refs and refs["GITHUB_MONITOR_TOKEN"] != SECRET_REF:
        raise ValueError("GITHUB_MONITOR_TOKEN already references another source; review before replacing it.")
    sources = list(grafana.get("additionalDataSources") or [])
    for filename, config in files.items():
        if filename != SOURCE_FILE and isinstance(config, dict):
            sources.extend(config.get("datasources") or [])
    for source in sources:
        if isinstance(source, dict) and (source.get("uid") == SOURCE_UID or source.get("name") == "BDC GitHub"):
            raise ValueError("BDC GitHub is already managed by another provisioning source; review its organization before proceeding.")
    owned = files.get(SOURCE_FILE)
    if owned:
        old = owned.get("datasources", []) if isinstance(owned, dict) else []
        if len(old) != 1 or old[0].get("uid") != SOURCE_UID or old[0].get("orgId") != org_id:
            raise ValueError("github-monitor.yaml already has another datasource/org; refusing an implicit migration.")
    installed = env.get("GF_PLUGINS_PREINSTALL_SYNC", "")
    if not isinstance(installed, str):
        raise ValueError("Existing GF_PLUGINS_PREINSTALL_SYNC must be a string.")
    plugins = [p.strip() for p in installed.split(",") if p.strip() and p.strip().split("@")[0] != "grafana-github-datasource"]
    plugins.append(PLUGIN)
    env["GF_PLUGINS_PREINSTALL_SYNC"] = ",".join(plugins)
    refs["GITHUB_MONITOR_TOKEN"] = copy.deepcopy(SECRET_REF)
    files[SOURCE_FILE] = {
        "apiVersion": 1,
        "datasources": [{
            "name": "BDC GitHub", "uid": SOURCE_UID,
            "orgId": org_id, "type": "grafana-github-datasource",
            "access": "proxy", "isDefault": False, "editable": False,
            "jsonData": {"selectedAuthType": "personal-access-token"},
            "secureJsonData": {"accessToken": "$GITHUB_MONITOR_TOKEN"},
        }],
    }
    return {"grafana": {"env": env, "envValueFrom": refs, "datasources": files}}


DS = {"type": "grafana-github-datasource", "uid": SOURCE_UID}
PACK = "bdc-github-management"
VIEWS = [("overview", "Overview"), ("reviews", "Pull requests"),
         ("issues", "Issues"), ("actions", "CI & workflows"),
         ("security", "Security"), ("repositories", "Repositories"),
         ("coverage", "Coverage & access")]


def dashboard_pack(org_id: int) -> dict:
    """Native plugin 2.9.4 query schemas; no synthetic data or credentials."""
    result = {}
    for slug, title in VIEWS:
        panels = []

        def text_panel(content):
            panels.append({"type": "text", "title": "Scope & definitions", "options": {
                "mode": "markdown", "content": content}, "gridPos": {"x": 0, "y": 0, "w": 24, "h": 4}})

        def query(kind, options=None, repository=""):
            return {"refId": "A", "datasource": DS, "queryType": kind,
                    "owner": "Big-Data-Club", "repository": repository, "options": options or {}}

        def panel(title, target, fields, mode="table", group=None):
            index = len(panels) - 1
            transforms = []
            if group:
                if group in ("is_private", "is_fork", "is_draft"):
                    transforms.append({"id": "convertFieldType", "options": {"conversions": [{"targetField": group, "destinationType": "string"}], "fields": {}}})
                transforms.append({"id": "groupBy", "options": {"fields": {
                    group: {"operation": "groupby", "aggregations": []},
                    fields[0]: {"operation": "aggregate", "aggregations": ["count"]}}}})
            else:
                transforms.append({"id": "filterFieldsByName", "options": {"include": {"names": fields}}})
            defaults = {"color": {"mode": "palette-classic"}, "custom": {"align": "auto", "cellOptions": {"type": "auto"}}, "noValue": "No data"}
            overrides = [{"matcher": {"id": "byName", "options": field}, "properties": [
                {"id": "links", "value": [{"title": "Open GitHub", "url": "${__value.raw}", "targetBlank": True}]}]}
                for field in ("url", "html_url", "permalink", "pull_request_url", "review_url") if field in fields]
            options = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
            if mode == "barchart":
                options = {"orientation": "horizontal", "showValue": "always", "legend": {"displayMode": "hidden"}, "tooltip": {"mode": "single"}, "xField": group}
            panels.append({"type": mode, "title": title, "datasource": DS, "targets": [target],
                           "transformations": transforms, "fieldConfig": {"defaults": defaults, "overrides": overrides},
                           "options": options, "gridPos": {"x": (index % 2) * 12, "y": 4 + (index // 2) * 12, "w": 12, "h": 12}})

        repo = "$repository"
        pr = lambda search, time=4: query("Pull_Requests", {"query": search, "timeField": time})
        if slug == "overview":
            text_panel("## Big-Data-Club · Engineering pulse\nOrganization-wide, token-visible repositories. Open PRs include older backlog; merged PRs and updated issues follow the selected time window. Charts count returned records, not guaranteed complete organization totals. Refresh: 5 minutes.")
            panel("Open PRs by repository · current", pr("is:open"), ["number"], "barchart", "repository")
            panel("Merged PRs by repository · selected window", pr("is:merged", 2), ["number"], "barchart", "repository")
            panel("Open pull requests · current", pr("is:open sort:created-asc"), ["repository", "number", "title", "author_login", "is_draft", "created_at", "url"])
            panel("Issues updated · selected window", query("Issues", {"timeField": 2}), ["repo", "number", "title", "state", "updated_at"])
        elif slug == "reviews":
            text_panel("## Review queue\nOrganization-wide current backlog, independent of the five-day window. Review-required means GitHub search `review:required`; it does not measure first-review latency. No email addresses are displayed.")
            panel("Awaiting review by repository", pr("is:open draft:false review:required"), ["number"], "barchart", "repository")
            panel("Current PR states", pr("is:open"), ["number"], "barchart", "is_draft")
            panel("Review required · oldest first", pr("is:open draft:false review:required sort:created-asc"), ["repository", "number", "title", "author_login", "created_at", "url"])
            panel("Changes requested", pr("is:open review:changes_requested"), ["repository", "number", "title", "author_login", "updated_at", "url"])
        elif slug == "issues":
            text_panel("## Issue activity\nOrganization-wide issues updated in the selected window. This is activity, not the complete open backlog: untouched older issues are excluded by the plugin time filter. [Open the full backlog on GitHub](https://github.com/issues?q=org%3ABig-Data-Club+is%3Aissue+is%3Aopen).")
            target = query("Issues", {"timeField": 2})
            panel("Updated issues by repository", target, ["number"], "barchart", "repo")
            panel("Updated issues by state", target, ["number"], "barchart", "state")
            panel("Open issues updated in window", query("Issues", {"timeField": 2, "query": "is:open"}), ["repo", "number", "title", "author", "assignees", "milestone", "updated_at"])
            panel("Closed in window", query("Issues", {"timeField": 1, "query": "is:closed"}), ["repo", "number", "title", "closed_at"])
        elif slug == "actions":
            text_panel("## CI · $repository\nChoose a repository above. Runs follow the selected time window; distributions count returned run records. A successful workflow is not proof of a production deployment. Billing and attempt-level statistics are not inferred from these records.")
            target = query("Workflow_Runs", {"workflow": "", "branch": ""}, repo)
            panel("Run conclusions · selected repository", target, ["id"], "barchart", "conclusion")
            panel("Run status · selected repository", target, ["id"], "barchart", "status")
            panel("Workflow runs · open run for logs", target, ["name", "run_number", "head_branch", "status", "conclusion", "event", "created_at", "html_url"])
            panel("Workflow inventory · first 100", query("Workflows", {"timeField": 0}, repo), ["name", "path", "state", "updated_at", "html_url"])
        elif slug == "security":
            text_panel("## Security · $repository\nCurrent alerts for the selected repository. Code scanning and Dependabot require endpoint permissions and enabled repository features. An error or no data is not a clean security verdict. No secret values or source snippets are displayed.")
            target = query("Code_Scanning", {"state": "open"}, repo)
            panel("Open code alerts by severity", target, ["number"], "barchart", "rule_security_severity_level")
            panel("Dependency alerts by state", query("Vulnerabilities", {}, repo), ["value"], "barchart", "state")
            panel("Open code scanning alerts", target, ["number", "state", "rule_description", "rule_security_severity_level", "tool_name", "created_at", "url"])
            panel("Dependency vulnerabilities", query("Vulnerabilities", {}, repo), ["packageName", "severity", "state", "firstPatchedVersion", "vulnerableVersionRange", "permalink"])
        elif slug == "repositories":
            text_panel("## Repository inventory\nRepositories visible to this credential, including forks and mirrors. Inventory is a current snapshot, independent of the time picker. This plugin schema does not expose archive state; no active-repository total is claimed.")
            target = query("Repositories")
            panel("Repository visibility · true = private", target, ["name"], "barchart", "is_private")
            panel("Fork distribution", target, ["name"], "barchart", "is_fork")
            panel("Repository inventory", target, ["name_with_owner", "is_private", "is_fork", "is_mirror", "forks", "created_at", "url"])
        else:
            text_panel("## Coverage & access\nDatasource: `bdc-github` · private Grafana organization. These dashboards query GitHub directly; they do not create a historical metrics database or change Prometheus retention (5d). The time picker is a query filter, not deletion of GitHub history.")
            panels.append({"type": "text", "title": "Interpret results correctly", "gridPos": {"x": 0, "y": 4, "w": 24, "h": 12}, "options": {"mode": "markdown", "content": "### Scope and freshness\n- Only repositories visible to the PAT are included. Cross-check the inventory with a GitHub organization owner.\n- GitHub search can cap results at 1,000. Narrow the window or repository when approaching that limit. Workflow inventory is limited to 100.\n- Plugin cache can delay changes by about five minutes. Panels sharing a query use the same cached source response.\n- Red query errors, 403, disabled features and no data must be investigated individually. They are not zero alerts.\n\n### Management links\n[Organization](https://github.com/Big-Data-Club) · [Projects](https://github.com/orgs/Big-Data-Club/projects) · [People](https://github.com/orgs/Big-Data-Club/people) · [Security](https://github.com/organizations/Big-Data-Club/settings/security_analysis)\n\n### Not collected by this pack\nBilling, audit events, team membership, organization-wide CI history, API quota telemetry and historical backlog snapshots need additional authorized endpoints or a collector. There are no fabricated charts for those metrics."}})
        for i, item in enumerate(panels, 1):
            item["id"] = i
        variables = []
        if slug in ("actions", "security"):
            variables = [{"name": "repository", "label": "Repository", "type": "query", "datasource": DS,
                          "query": {"queryType": "Repositories", "owner": "Big-Data-Club", "repository": "", "field": "name"},
                          "refresh": 1, "sort": 1, "multi": False, "includeAll": False,
                          "current": {"text": "CoreApplication", "value": "CoreApplication"}, "options": []}]
        result[slug] = {"uid": "bdc-gh-" + slug, "title": "GitHub · " + title, "schemaVersion": 39,
                        "version": 1, "editable": False, "tags": ["bdc", "github", "management"],
                        "timezone": "browser", "refresh": "5m", "time": {"from": "now-5d", "to": "now"},
                        "timepicker": {"refresh_intervals": ["5m", "15m", "30m", "1h"]},
                        "templating": {"list": variables}, "panels": panels,
                        "links": [{"title": label, "type": "link", "url": f"/monitor/d/bdc-gh-{key}?orgId={org_id}", "targetBlank": False} for key, label in VIEWS]}
    return result


def dashboard_values(existing: dict, org_id: int) -> dict:
    patch = provisioning_values(existing, org_id)
    grafana = existing.get("grafana") or {}
    providers = copy.deepcopy(grafana.get("dashboardProviders") or {})
    dashboards = copy.deepcopy(grafana.get("dashboards") or {})
    if not isinstance(providers, dict) or not isinstance(dashboards, dict):
        raise ValueError("Existing dashboardProviders/dashboards must be mappings")
    provider = {"name": PACK, "orgId": org_id, "folder": "GitHub Management", "type": "file",
                "disableDeletion": True, "allowUiUpdates": False,
                "options": {"path": "/var/lib/grafana/dashboards/" + PACK}}
    filename = PACK + ".yaml"
    wanted = {"apiVersion": 1, "providers": [provider]}
    if filename in providers and providers[filename] != wanted:
        raise ValueError("Dashboard provider is already configured differently; refusing migration")
    for name, config in providers.items():
        if name != filename and isinstance(config, dict):
            for other in config.get("providers", []):
                if other.get("name") == PACK or other.get("options", {}).get("path") == provider["options"]["path"]:
                    raise ValueError("Another provider owns the GitHub dashboard path")
    generated = {slug: {"json": json.dumps(dashboard)} for slug, dashboard in dashboard_pack(org_id).items()}
    if PACK in dashboards and dashboards[PACK] != generated:
        # Only this pack's known dashboard keys may be updated on subsequent runs.
        if set(dashboards[PACK]) != set(generated):
            raise ValueError("GitHub dashboard directory contains unexpected keys")
    providers[filename] = wanted
    dashboards[PACK] = generated
    patch["grafana"].update({"dashboardProviders": providers, "dashboards": dashboards})
    return patch


def run(*args: str, capture: bool = False):
    return subprocess.run(list(args), text=True, check=True, capture_output=capture)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", type=int, help="Existing private management Grafana organization ID (not 1)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dashboards", action="store_true", help="Install seven management dashboards as well as the datasource")
    parser.add_argument("--export", type=Path, help="Export dashboard JSON locally, without cluster access")
    args = parser.parse_args()
    if args.export:
        if args.org_id is None or args.org_id <= 1:
            parser.error("--export requires --org-id greater than 1")
        args.export.mkdir(parents=True, exist_ok=True)
        for slug, dashboard in dashboard_pack(args.org_id).items():
            (args.export / (slug + ".json")).write_text(json.dumps(dashboard, indent=2) + "\n")
        print(f"Exported seven dashboards to {args.export}")
        return
    if not args.apply:
        print("Plan only; no VM/cluster access:")
        print("1. Verify deployed Helm release kps and Secret monitoring/github-monitor (key token).")
        print("2. Preserve the installed chart version and other Grafana settings/datasources.")
        print("3. Install pinned GitHub plugin, mount token through secretKeyRef, provision only in --org-id.")
        print("4. Wait for Grafana rollout. Then verify BDC GitHub via Save & test / Explore.")
        if args.dashboards:
            print("5. Provision seven linked dashboards in GitHub Management in the selected organization.")
        print("Prometheus retention is unchanged. No PAT value is read, printed or written by this script.")
        return
    if args.org_id is None or args.org_id <= 1:
        parser.error("Create/select a private management Grafana organization and provide --org-id greater than 1.")
    if not all(shutil.which(tool) for tool in ("helm", "kubectl")):
        parser.error("helm and kubectl are required on the VM")
    context = run("kubectl", "config", "current-context", capture=True).stdout.strip()
    if not context:
        raise ValueError("kubectl current context is empty")
    releases = json.loads(run("helm", "list", "--all", "--kube-context", context, "-n", "monitoring", "--filter", "^kps$", "-o", "json", capture=True).stdout)
    if len(releases) != 1 or releases[0].get("status") != "deployed":
        raise ValueError("Expected one deployed kps release. Inspect helm -n monitoring history/status kps before retrying.")
    match = re.fullmatch(r"kube-prometheus-stack-([0-9][0-9A-Za-z.+-]*)", releases[0].get("chart", ""))
    if not match:
        raise ValueError("kps is not a kube-prometheus-stack release")
    # Only the key's presence is printed; kubectl never emits Secret data.
    present = run("kubectl", "--context", context, "-n", "monitoring", "get", "secret", "github-monitor",
                  "-o", 'go-template={{if index .data "token"}}ready{{end}}', capture=True).stdout.strip()
    if present != "ready":
        raise ValueError("Secret github-monitor must contain a nonempty token key")
    existing = json.loads(run("helm", "get", "values", "kps", "--kube-context", context, "-n", "monitoring", "-o", "json", capture=True).stdout) or {}
    patch = dashboard_values(existing, args.org_id) if args.dashboards else provisioning_values(existing, args.org_id)
    run("helm", "repo", "add", "prometheus-community", "https://prometheus-community.github.io/helm-charts", "--force-update")
    run("helm", "repo", "update", "prometheus-community")
    # Existing values may contain other credentials; keep the merged file 0600
    # and ephemeral. The new PAT is only an environment reference, never decoded.
    with tempfile.TemporaryDirectory(prefix="bdc-github-grafana-") as temp:
        path = Path(temp) / "values.json"
        path.touch(mode=0o600)
        path.write_text(json.dumps(patch))
        print(f"Updating kps using its installed chart {match.group(1)}; target Grafana org ID {args.org_id}.", flush=True)
        run("helm", "upgrade", "kps", "prometheus-community/kube-prometheus-stack", "--kube-context", context,
            "-n", "monitoring", "--version", match.group(1), "--reuse-values", "--values", str(path), "--wait", "--timeout", "10m")
    run("kubectl", "--context", context, "-n", "monitoring", "rollout", "status", "deployment/kps-grafana", "--timeout=5m")
    print("Rollout ready. Switch to the management organization; open Connections > Data sources > BDC GitHub.")
    print("Run Save & test or Explore to verify GitHub API access. Rollout readiness alone does not verify PAT permissions.")
    if args.dashboards:
        print(f"Dashboards provisioned. Open https://bdc.hpcc.vn/monitor/d/bdc-gh-overview?orgId={args.org_id}")
        print("Folder: GitHub Management. Live query results depend on GitHub permissions; no observer was installed.")
    else:
        print("Datasource only. Add --dashboards --org-id ID --apply to install management dashboards.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError):
        print("Setup did not complete. Inspect Helm status/history and Grafana rollout events locally; do not paste Secret data or full Helm values.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted. Inspect Helm status/history before retrying; an in-flight rollout is not canceled automatically.", file=sys.stderr)
        sys.exit(130)
