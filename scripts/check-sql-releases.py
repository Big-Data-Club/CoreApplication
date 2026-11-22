#!/usr/bin/env python3
"""Validate immutable SQL releases without connecting to any database."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "ai-service", "auth-and-management-service", "chat-service",
    "farm-service", "lab-service", "lms-service", "personalize-service", "workspace-service",
)
OPTIONAL_SERVICES = ("dutylog/backend",)


def validate_service(directory):
    manifests = sorted(directory.glob("releases/*/manifest.json"))
    if not manifests:
        raise ValueError(f"No release manifest: {directory}")
    recorded = set()
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        if data["release"] != manifest.parent.name:
            raise ValueError(f"Release name mismatch: {manifest}")
        for entry in data["files"]:
            name = entry["name"]
            if Path(name).name != name or not name.endswith(".sql"):
                raise ValueError(f"Invalid SQL filename: {name}")
            sql = manifest.parent / name
            if sql in recorded:
                raise ValueError(f"Duplicate manifest entry: {sql}")
            recorded.add(sql)
            if hashlib.sha256(sql.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Released SQL changed: {sql}")
    names = set()
    for sql in directory.rglob("*.sql"):
        if sql.name in names:
            raise ValueError(f"Duplicate migration name: {sql.name}")
        names.add(sql.name)
        if sql not in recorded:
            raise ValueError(f"SQL missing from release manifest: {sql}")
    snapshot = directory.parent / "schema"
    metadata_file = snapshot / "manifest.json"
    if metadata_file.exists() or (snapshot / "current.sql").exists():
        metadata = json.loads(metadata_file.read_text())
        if hashlib.sha256((snapshot / "current.sql").read_bytes()).hexdigest() != metadata["current_sha256"]:
            raise ValueError(f"Consolidated SQL changed without regeneration: {snapshot}")
        for entry in metadata["inputs"]:
            source = directory.parent / entry["path"]
            if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Consolidated SQL has stale input: {source}")
        covered = {entry["path"] for entry in metadata["inputs"] if entry["path"].startswith("migrations/")}
        expected = {str(sql.relative_to(directory.parent)) for sql in directory.rglob("*.sql")}
        if covered != expected:
            raise ValueError(f"Regenerate consolidated SQL after adding migrations: {snapshot}")
    return len(recorded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", choices=SERVICES + OPTIONAL_SERVICES)
    args = parser.parse_args()
    services = args.service or list(SERVICES)
    if not args.service:
        for service in OPTIONAL_SERVICES:
            # Root checkout intentionally excludes submodules. Check their release
            # when present; a pinned older submodule may still use the flat layout.
            if list((ROOT / service / "migrations").glob("releases/*/manifest.json")):
                services.append(service)
    total = sum(validate_service(ROOT / service / "migrations") for service in services)
    print(f"SQL releases verified: {total} unchanged files across {len(services)} services.")


if __name__ == "__main__":
    main()
