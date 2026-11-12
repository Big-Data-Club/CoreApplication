#!/usr/bin/env python3
"""Initialize only pinned submodules needed by one service build context."""
from __future__ import annotations

import os
from pathlib import PurePosixPath
import subprocess
import sys


def required_submodules(context: str, git_index: bytes) -> list[str]:
    path = PurePosixPath(context)
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise ValueError("Build context must be a relative service directory")
    context = str(path)
    required = []
    for record in git_index.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        if metadata.split()[0] != b"160000":
            continue
        name = name.decode("utf-8")
        if name == context or name.startswith(context + "/") or context.startswith(name + "/"):
            required.append(name)
    return sorted(set(required))


def submodule_environment() -> dict[str, str]:
    # checkout(submodules=false) stores auth in the root's local config; child
    # clone processes do not inherit it. Pass it ephemerally, never in argv/logs
    # or a global Git config on the reused runner. Also support SSH gitlinks.
    environment = os.environ.copy()
    entries = [
        ("url.https://github.com/.insteadOf", "git@github.com:"),
        ("url.https://github.com/.insteadOf", "ssh://git@github.com/"),
    ]
    try:
        header = subprocess.check_output(
            ["git", "config", "--local", "--get", "http.https://github.com/.extraheader"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        header = ""
    if header:
        entries.extend([("http.https://github.com/.extraheader", ""),
                        ("http.https://github.com/.extraheader", header)])
    count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    for key, value in entries:
        environment[f"GIT_CONFIG_KEY_{count}"] = key
        environment[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: checkout-service-submodules.py SERVICE_CONTEXT", file=sys.stderr)
        return 2
    try:
        index = subprocess.check_output(["git", "ls-files", "--stage", "-z"])
        paths = required_submodules(argv[0], index)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cannot select service submodules: {exc}", file=sys.stderr)
        return 1
    if not paths:
        print("This service build does not require any submodule checkout.")
        return 0
    if "ai-gateway" in paths and os.environ.get("SUBMODULE_PAT_CONFIGURED", "").lower() != "true":
        print("::error::Building private ai-gateway requires the CoreApplication Actions secret SUBMODULE_PAT. "
              "Grant its token Contents: read on CoreApplication and BDCHub---AIGateway; "
              "a default GITHUB_TOKEN cannot read another private repository.", file=sys.stderr)
        return 1
    print("Checking out pinned service submodules: " + ", ".join(paths), flush=True)
    try:
        environment = submodule_environment()
        subprocess.run(["git", "submodule", "sync", "--recursive", "--", *paths], check=True, env=environment)
        subprocess.run(["git", "submodule", "update", "--init", "--depth=1", "--recursive", "--", *paths], check=True, env=environment)
    except subprocess.CalledProcessError:
        print("::error::Required submodule checkout failed. Check SUBMODULE_PAT repository access, "
              "organization approval/SSO, token expiry, and the pinned commit's availability.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
