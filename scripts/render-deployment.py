#!/usr/bin/env python3
"""Render one selected workload with its release image before applying it."""
import argparse
import json
import subprocess


def parse_documents(raw):
    """kubectl create may emit consecutive JSON objects for a YAML stream."""
    decoder = json.JSONDecoder()
    documents = []
    offset = 0
    while offset < len(raw):
        if raw[offset].isspace():
            offset += 1
            continue
        document, offset = decoder.raw_decode(raw, offset)
        if not isinstance(document, dict):
            raise ValueError("Expected a Kubernetes JSON object")
        items = document.get("items") if document.get("kind") == "List" else [document]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("Expected Kubernetes List items to be objects")
        documents.extend(items)
    if not documents:
        raise ValueError("kubectl returned no manifest objects")
    return documents


def render(documents, deployment, container, image, config_revision=None):
    selected = [doc for doc in documents if doc and doc.get("kind") == "Deployment"
                and doc.get("metadata", {}).get("name") == deployment]
    if len(selected) != 1:
        raise ValueError(f"Expected one Deployment named {deployment}")
    workload = selected[0]
    containers = workload["spec"]["template"]["spec"]["containers"]
    matches = [item for item in containers if item["name"] == container]
    if len(matches) != 1:
        raise ValueError(f"Expected one container named {container}")
    matches[0]["image"] = image
    if config_revision:
        metadata = workload["spec"]["template"].setdefault("metadata", {})
        metadata.setdefault("annotations", {})["bdc.io/farm-config-revision"] = config_revision
    selected.extend(doc for doc in documents if doc and doc.get("kind") == "Service"
                    and doc.get("metadata", {}).get("name") == deployment)
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": selected})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "deployment", "container", "image"):
        parser.add_argument(name)
    parser.add_argument("--config-revision")
    parser.add_argument("--namespace", default="default")
    args = parser.parse_args()
    raw = subprocess.check_output(["kubectl", "create", "--dry-run=client", "--validate=false",
                                   "--namespace", args.namespace, "-f", args.manifest, "-o", "json"], text=True)
    documents = parse_documents(raw)
    print(render(documents, args.deployment, args.container, args.image, args.config_revision))
