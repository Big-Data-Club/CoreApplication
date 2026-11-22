#!/usr/bin/env python3
"""Consolidate repository SQL using a disposable PostgreSQL container, never Neon."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "lms-service", "ai-service", "lab-service", "chat-service", "farm-service",
    "dutylog/backend", "workspace-service", "auth-and-management-service",
)
LEDGERS = {
    "lab-service": ("lab_schema_migrations", "version", "TEXT"),
    "chat-service": ("schema_migrations", "version", "VARCHAR(255)"),
    "workspace-service": ("workspace_migrations", "name", "TEXT"),
}
AUTH_PREREQUISITE = "CREATE TABLE organizations(id BIGINT PRIMARY KEY);"
HEADER = """-- Consolidated schema reconstructed from repository SQL, not a Neon dump.
-- NEW databases only. Existing deployments continue using migration history.
-- Tables contain their final columns; indexes, constraints and seed defaults follow.
-- See README.md for scope and regeneration.

"""


def command(arguments, text=None):
    result = subprocess.run(arguments, input=text, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def compact_dump(raw):
    """Remove dump boilerplate, preserving comments/text inside SQL literals."""
    lines, mode, escaped = [], None, False
    for line in raw.splitlines():
        if mode is None and line.startswith(("--", "\\restrict", "\\unrestrict", "SET transaction_timeout")):
            continue
        lines.append(line)
        index = 0
        while index < len(line):
            if mode and mode.startswith("$"):
                end = line.find(mode, index)
                if end < 0:
                    break
                index, mode = end + len(mode), None
                continue
            char = line[index]
            if mode in ("'", '"'):
                if escaped and char == "\\":
                    index += 2
                    continue
                if char == mode:
                    if index + 1 < len(line) and line[index + 1] == mode:
                        index += 2
                        continue
                    mode = None
            elif line.startswith("--", index):
                break
            elif char in ("'", '"'):
                mode = char
                escaped = char == "'" and index > 0 and line[index - 1] in "Ee"
            elif char == "$":
                match = re.match(r"\$[A-Za-z_0-9]*\$", line[index:])
                if match:
                    mode = match.group()
                    index += len(mode)
                    continue
            index += 1
    return "\n".join(lines).strip() + "\n"


def inputs(service):
    directory = ROOT / service / "migrations"
    migrations = sorted(directory.rglob("*.sql"), key=lambda file: file.name)
    if not migrations or len({file.name for file in migrations}) != len(migrations):
        raise ValueError(f"Missing or duplicate migration inputs: {service}")
    # Historical 004 GraphRAG SQL was an operator script, after the base schema.
    if service == "ai-service":
        migrations = [file for file in migrations if file.name.startswith("V")] + [
            file for file in migrations if not file.name.startswith("V")]
    sources = list(migrations)
    if service == "farm-service":
        sources = [ROOT / service / "internal/farm/schema.sql",
                   ROOT / service / "internal/game/schema.sql"] + sources
    return migrations, sources


def input_sql(service, path):
    text = path.read_text()
    if service == "ai-service" and path.name == "V002__performance_indexes.sql":
        # CURRENT_DATE is STABLE, not IMMUTABLE; invalid in an index predicate.
        # Keep the historical bytes untouched; make the fresh-schema index valid.
        text = text.replace("WHERE next_review_date <= CURRENT_DATE;",
                            "WHERE next_review_date IS NOT NULL;")
    return text


def ledger_sql(service, migrations):
    if service not in LEDGERS:
        return ""
    table, column, kind = LEDGERS[service]
    values = ",\n".join("('" + file.name.replace("'", "''") + "')" for file in migrations)
    return (f"\n-- Record the historical identities covered by this fresh baseline.\n"
            f"CREATE TABLE public.{table} ({column} {kind} PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now());\n"
            f"INSERT INTO public.{table} ({column}) VALUES\n{values};\n")


class TemporaryPostgres:
    def __init__(self):
        self.name = "bdc-schema-" + uuid.uuid4().hex[:12]

    def __enter__(self):
        command(["docker", "run", "--detach", "--rm", "--name", self.name,
                 "--memory=768m", "--cpus=2", "-e", "POSTGRES_USER=bdc_schema",
                 "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:17-alpine"])
        try:
            for _ in range(90):
                ready = subprocess.run(["docker", "exec", self.name, "pg_isready",
                                        "-h", "127.0.0.1", "-U", "bdc_schema"],
                                       capture_output=True)
                if ready.returncode == 0:
                    return self
                time.sleep(0.5)
            raise RuntimeError("Temporary PostgreSQL did not become ready")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        command(["docker", "stop", self.name])

    def create(self, database, service):
        command(["docker", "exec", self.name, "createdb", "-U", "bdc_schema", database])
        if service == "auth-and-management-service":
            # A placeholder resolves the FK only. It is NEVER included in output.
            self.execute(database, AUTH_PREREQUISITE)

    def execute(self, database, sql):
        return command(["docker", "exec", "-i", self.name, "psql", "-X",
                        "-v", "ON_ERROR_STOP=1", "-U", "bdc_schema", "-d", database], sql)

    def dump(self, database, service, data=False):
        flags = ["--data-only", "--inserts"] if data else ["--schema-only"]
        if service == "auth-and-management-service":
            flags.append("--exclude-table=public.organizations")
        if service in LEDGERS:
            flags.append("--exclude-table=public." + LEDGERS[service][0])
        return compact_dump(command(["docker", "exec", self.name, "pg_dump",
                                     "-U", "bdc_schema", "--no-owner", "--no-acl",
                                     *flags, database]))


def build(postgres, service, index, check=False):
    migrations, sources = inputs(service)
    original, normalized, restored = (f"schema_{index}", f"normalized_{index}", f"restored_{index}")
    postgres.create(original, service)
    for file in sources:
        try:
            postgres.execute(original, input_sql(service, file))
        except RuntimeError as error:
            raise RuntimeError(f"{service}/{file.name}: {error}") from error
    ddl, seed = postgres.dump(original, service), postgres.dump(original, service, data=True)
    postgres.create(normalized, service)
    postgres.execute(normalized, ddl + "\n" + seed)
    # PostgreSQL normalizes varchar-array CHECK casts on the first restoration.
    ddl = postgres.dump(normalized, service)
    snapshot = HEADER + ddl + "\n-- Default rows from repository SQL only.\n" + seed + ledger_sql(service, migrations)
    postgres.create(restored, service)
    postgres.execute(restored, snapshot)
    if postgres.dump(restored, service) != ddl:
        raise RuntimeError(f"{service}: consolidated schema differs after restoration")
    if postgres.dump(restored, service, data=True) != seed:
        raise RuntimeError(f"{service}: repository seed data differs after restoration")
    if service in LEDGERS:
        table, column, _ = LEDGERS[service]
        recorded = postgres.execute(restored,
            f"COPY (SELECT {column} FROM public.{table} ORDER BY {column}) TO STDOUT;")
        if recorded.splitlines() != sorted(file.name for file in migrations):
            raise RuntimeError(f"{service}: baseline ledger lost original identities")
    directory = ROOT / service / "schema"
    metadata = {
        "engine": "PostgreSQL 17", "source": "repository SQL, not production",
        "inputs": [{"path": str(file.relative_to(ROOT / service)),
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest()} for file in sources],
        "current_sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
        "requires_jpa_organizations": service == "auth-and-management-service",
        "adjustments": (["idx_sr_student_due_today: replace volatile CURRENT_DATE predicate with IS NOT NULL"]
                        if service == "ai-service" else []),
    }
    if check:
        # Dumps containing repository DEFAULT now() seeds have fresh timestamps;
        # validate checked-in DDL/seed semantics, rather than comparing build times.
        postgres.create(f"checked_{index}", service)
        postgres.execute(f"checked_{index}", (directory / "current.sql").read_text())
        if postgres.dump(f"checked_{index}", service) != ddl:
            raise RuntimeError(f"{service}: checked-in snapshot is out of date")
    else:
        directory.mkdir(exist_ok=True)
        (directory / "current.sql").write_text(snapshot)
        (directory / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"{service}: consolidated and restored {len(migrations)} migrations", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", choices=SERVICES)
    parser.add_argument("--check", action="store_true", help="Validate checked-in snapshots without rewriting")
    args = parser.parse_args()
    with TemporaryPostgres() as postgres:
        for index, service in enumerate(args.service or SERVICES):
            build(postgres, service, index, args.check)


if __name__ == "__main__":
    main()
