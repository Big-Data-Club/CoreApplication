"""Small in-cluster client. Never include API response bodies in exceptions."""
import base64
import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class APIError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Kubernetes request failed ({status})")


class Kube:
    def __init__(self):
        self.namespace = os.environ.get("NAMESPACE", "default")
        self.root = "https://kubernetes.default.svc"
        self.sa = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.tls = ssl.create_default_context(cafile=str(self.sa / "ca.crt"))

    def path(self, resource, name=""):
        groups = {"deployments": "apps/v1", "statefulsets": "apps/v1",
                  "jobs": "batch/v1", "cronjobs": "batch/v1",
                  "horizontalpodautoscalers": "autoscaling/v2"}
        prefix = "/apis/" + groups[resource] if resource in groups else "/api/v1"
        return f"{prefix}/namespaces/{self.namespace}/{resource}" + (f"/{name}" if name else "")

    def request(self, method, resource, name="", body=None):
        headers = {"Authorization": "Bearer " + (self.sa / "token").read_text().strip(),
                   "Content-Type": "application/merge-patch+json" if method == "PATCH" else "application/json"}
        request = Request(self.root + self.path(resource, name), method=method, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, context=self.tls, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            raise APIError(exc.code) from None

    def get(self, resource, name=""):
        return self.request("GET", resource, name)

    def patch(self, resource, name, body):
        return self.request("PATCH", resource, name, body)

    def secret(self, name):
        return {key: base64.b64decode(value).decode() for key, value in self.get("secrets", name).get("data", {}).items()}


LOCK = "bdc-db-operation"
STATE = "bdc-db-migration"
MANAGED = "bdc.io/db-managed"


def claim(kube, owner):
    obj = kube.get("configmaps", LOCK)
    current = obj.get("data", {}).get("owner", "")
    if current:
        raise RuntimeError("Another operation holds the database lock")
    obj.setdefault("data", {})["owner"] = owner
    # PUT with resourceVersion: concurrent claims cannot both succeed.
    kube.request("PUT", "configmaps", LOCK, obj)


def release(kube, owner):
    obj = kube.get("configmaps", LOCK)
    if obj.get("data", {}).get("owner") != owner:
        raise RuntimeError("Database lock ownership changed")
    obj["data"]["owner"] = ""
    kube.request("PUT", "configmaps", LOCK, obj)


def state(kube):
    return json.loads(kube.get("configmaps", STATE).get("data", {}).get("state", "{}"))


def save_state(kube, value):
    kube.patch("configmaps", STATE, {"data": {"state": json.dumps(value)}})
