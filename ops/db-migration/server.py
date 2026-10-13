"""Grafana-session protected migration console; Kubernetes credentials stay server-side."""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

from kube import APIError, Kube, claim, release, save_state, state

BASE = "/monitor/migrations/"
ASSETS = Path(__file__).parent / "static"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def grafana_admin(cookie, renewed_cookies=None):
    cookies = SimpleCookie()
    cookies.load(cookie or "")
    session = cookies.get("grafana_session")
    if not session:
        return None
    request = Request(os.environ["GRAFANA_URL"].rstrip("/") + "/api/user",
                      headers={"Cookie": "grafana_session=" + session.coded_value})
    try:
        with build_opener(NoRedirect).open(request, timeout=5) as response:
            user = json.load(response)
            if renewed_cookies is not None:
                renewed_cookies.extend(response.headers.get_all("Set-Cookie", []))
        if user.get("isGrafanaAdmin") is True and isinstance(user.get("id"), int):
            return user["id"]
    except Exception:
        pass
    return None


def validate_request(headers, body):
    if headers.get("Origin") != os.environ["PUBLIC_ORIGIN"]:
        raise ValueError("Invalid request origin")
    if headers.get("Content-Type", "").split(";")[0] != "application/json":
        raise ValueError("JSON required")
    if set(body) != {"profile", "request_id"}:
        raise ValueError("Expected profile and request_id")
    if not isinstance(body["profile"], str) or not re.fullmatch(r"[a-z0-9-]{1,40}", body["profile"]):
        raise ValueError("Invalid profile")
    if str(uuid.UUID(body["request_id"])) != body["request_id"]:
        raise ValueError("Invalid request ID")


def make_job(profile, run_id, actor):
    image = os.environ["MIGRATION_IMAGE"]
    if image.endswith(":latest") or not ("@sha256:" in image or ":" in image):
        raise ValueError("Migration image must have an immutable release tag or digest")
    return {"apiVersion": "batch/v1", "kind": "Job", "metadata": {
        "name": "db-migrate-" + run_id, "labels": {"app": "bdc-db-migration"},
        "annotations": {"bdc.io/actor": str(actor), "bdc.io/profile": profile["id"]}},
        "spec": {"backoffLimit": 0, "activeDeadlineSeconds": profile.get("timeout_seconds", 7200) + 900,
                 "ttlSecondsAfterFinished": 604800, "template": {
                     "metadata": {"labels": {"app": "bdc-db-migration"}},
                     "spec": {"restartPolicy": "Never", "serviceAccountName": "bdc-db-migration-worker",
                              "terminationGracePeriodSeconds": 120,
                              "securityContext": {"runAsUser": 1000, "runAsGroup": 1000, "fsGroup": 1000},
                              "containers": [{"name": "migrate", "image": image,
                                  "command": ["python3", "/app/runner.py"],
                                  "env": [{"name": "RUN_ID", "value": run_id},
                                          {"name": "PROFILE", "value": json.dumps(profile)},
                                          {"name": "NAMESPACE", "value": os.environ.get("NAMESPACE", "default")}],
                                  "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                                                "limits": {"cpu": "1", "memory": "512Mi"}},
                                  "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                                      "capabilities": {"drop": ["ALL"]}},
                                  "volumeMounts": [{"name": "scratch", "mountPath": "/tmp"}]}],
                              "volumes": [{"name": "scratch", "emptyDir": {"sizeLimit": "512Mi"}}]}}}}


def start(kube, profile, request_id, actor):
    previous = state(kube)
    if previous.get("request_id") == request_id:
        if previous.get("profile") != profile["id"]:
            raise ValueError("Request ID already used for another profile")
        return previous
    run_id = request_id.replace("-", "")
    job = make_job(profile, run_id, actor)
    claim(kube, "migration:" + run_id)
    value = {"run_id": run_id, "request_id": request_id, "profile": profile["id"],
             "actor": actor, "phase": "queued", "updated_at": datetime.now(timezone.utc).isoformat(),
             "job": job["metadata"]["name"]}
    try:
        save_state(kube, value)
    except Exception:
        release(kube, "migration:" + run_id)
        raise
    # An ambiguous create/timeout MUST keep the lock: the Job may already exist.
    kube.request("POST", "jobs", body=job)
    return value


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No cookies, request bodies, or query strings in access logs.

    def send(self, code, data, content_type="application/json"):
        payload = json.dumps(data).encode() if content_type == "application/json" else data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'; base-uri 'none'")
        for cookie in getattr(self, "renewed_cookies", []):
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def authorize(self):
        self.renewed_cookies = []
        return grafana_admin(self.headers.get("Cookie"), self.renewed_cookies)

    def do_GET(self):
        if self.path == "/healthz":
            return self.send(200, {"ok": True})
        if self.authorize() is None:
            return self.send(403, {"error": "Log in at /monitor/login with a Grafana server Admin account"})
        try:
            if self.path == BASE + "api/status":
                kube = Kube()
                value = state(kube)
                if value.get("job"):
                    try:
                        job = kube.get("jobs", value["job"])
                    except APIError as exc:
                        if exc.status != 404:
                            raise
                        job = {}
                        value["job_expired"] = True
                    value["job_failed"] = any(c["type"] == "Failed" and c["status"] == "True"
                                              for c in job.get("status", {}).get("conditions", []))
                return self.send(200, value)
            if self.path == BASE + "api/profiles":
                return self.send(200, [{"id": p["id"], "label": p["label"]} for p in profiles() if p.get("enabled")])
            assets = {BASE: ("index.html", "text/html; charset=utf-8"),
                      BASE + "app.js": ("app.js", "text/javascript; charset=utf-8"),
                      BASE + "style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path in assets:
                name, mime = assets[self.path]
                return self.send(200, (ASSETS / name).read_bytes(), mime)
            self.send(404, {"error": "Not found"})
        except Exception:
            self.send(503, {"error": "Cannot read migration status. Inspect the operation lock and Job in K3s."})

    def do_POST(self):
        actor = self.authorize()
        if actor is None:
            return self.send(403, {"error": "Grafana server Admin required"})
        if self.path != BASE + "api/runs":
            return self.send(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("Invalid body size")
            body = json.loads(self.rfile.read(length))
            validate_request(self.headers, body)
            profile = next((p for p in profiles() if p["id"] == body["profile"] and p.get("enabled")), None)
            if profile is None:
                return self.send(404, {"error": "Enabled profile not found"})
            value = start(Kube(), profile, body["request_id"], actor)
            self.send(202, value)
        except (ValueError, TypeError, KeyError, AttributeError):
            self.send(400, {"error": "Invalid migration request"})
        except Exception:
            self.send(409, {"error": "Cannot start: an operation may hold the lock. Refresh status before retrying."})


def profiles():
    return json.loads(Path(os.environ.get("PROFILES_FILE", "/config/profiles.json")).read_text())


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
