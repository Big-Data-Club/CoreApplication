"""PostgreSQL initial COPY + WAL streaming, with a committed marker at cutover.

Only ordinary permanent tables are supported. Unsupported data is rejected, never
silently omitted. Connections use a dedicated application_name for diagnostics.
"""
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import parse_dsn, make_dsn

APP = "bdc-migration"
SCHEMA = "bdc_migration_control"
TABLES = """
SELECT n.nspname,c.relname,c.relkind,c.relpersistence,c.relreplident,
       EXISTS(SELECT 1 FROM pg_index i WHERE i.indrelid=c.oid AND i.indisprimary),
       EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
              AND d.objid=c.oid AND d.deptype='e'), c.relrowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema', 'bdc_migration_control')
  AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%'
  AND c.relkind IN ('r','p','f','m') ORDER BY 1,2
"""


class MigrationError(RuntimeError):
    """Safe, authored explanation that can be shown in the operations UI."""


def connect(url, database):
    conn = psycopg2.connect(make_dsn(url, dbname=database, application_name=APP,
                                   connect_timeout=15), options="-c statement_timeout=60000 -c lock_timeout=15000")
    conn.autocommit = True
    return conn


def query(conn, query_text, args=None):
    with conn.cursor() as cur:
        cur.execute(query_text, args)
        return cur.fetchall() if cur.description else []


def identifier(schema, name):
    return sql.Identifier(schema, name)


def schema_dump(url, database):
    # No credentials in argv, exceptions or child output. libpq reads a private
    # service file; subprocess output is never forwarded to the dashboard/logs.
    params = parse_dsn(url)
    params.update(dbname=database, application_name=APP, connect_timeout="15")
    with tempfile.TemporaryDirectory() as directory:
        service = Path(directory) / "pg_service.conf"
        if any("\n" in value or "\r" in value for value in params.values()):
            raise MigrationError("Multiline PostgreSQL connection parameters are unsupported")
        service.write_text("[migration]\n" + "\n".join(f"{key}={value}" for key, value in params.items()))
        service.chmod(0o600)
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        env.update(PGSERVICEFILE=str(service), PGSERVICE="migration")
        result = subprocess.run(["pg_dump", "--schema-only", "--no-owner", "--no-acl",
                                 "--no-publications", "--no-subscriptions", "--exclude-schema=" + SCHEMA],
                                env=env, capture_output=True, timeout=120, check=False)
        if result.returncode:
            raise MigrationError("Schema dump failed; inspect database permissions and client version")
    # Plain dumps include psql metacommands (including random restriction keys).
    # Execute only SQL via libpq, and normalize comments for schema comparison.
    return "\n".join(line for line in result.stdout.decode().splitlines()
                     if not line.startswith("\\") and not line.startswith("--"))


def fingerprint(dump):
    return hashlib.sha256(dump.encode()).hexdigest()


class Replica:
    def __init__(self, source_url, target_url, database, run_id, index):
        self.source_url, self.target_url, self.database = source_url, target_url, database
        self.name = "bdcm_" + run_id[:20] + "_" + str(index)
        self.token = run_id
        self.source = connect(source_url, database)
        try:
            admin = connect(target_url, parse_dsn(target_url)["dbname"])
            try:
                if not query(admin, "SELECT 1 FROM pg_database WHERE datname=%s", (database,)):
                    query(admin, sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            finally:
                admin.close()
            self.target = connect(target_url, database)
        except Exception:
            self.source.close()
            raise
        self.guard = None
        self.tables = []
        self.started = False

    def preflight(self):
        source_major = self.source.server_version // 10000
        target_major = self.target.server_version // 10000
        version = subprocess.run(["pg_dump", "--version"], capture_output=True, check=True).stdout.decode()
        client_major = int(re.search(r"(\d+)\.", version).group(1))
        if source_major < 16 or source_major != target_major or source_major != client_major:
            raise MigrationError("Use matching PostgreSQL 16+ source, target and client major versions")
        if query(self.source, "SHOW wal_level")[0][0] != "logical":
            raise MigrationError("Source must enable logical replication before migration")
        if query(self.source, "SELECT count(*) FROM pg_largeobject_metadata")[0][0]:
            raise MigrationError("Large objects require a separate migration strategy")
        subscriptions = "SELECT count(*) FROM pg_subscription WHERE subdbid=(SELECT oid FROM pg_database WHERE datname=current_database())"
        if query(self.source, subscriptions)[0][0]:
            raise MigrationError("A source that is itself a subscriber is unsupported")
        if query(self.target, TABLES) or query(self.target, subscriptions)[0][0]:
            raise MigrationError("Destination database must be empty; automatic overwrite is disabled")
        if query(self.source, "SELECT 1 FROM pg_namespace WHERE nspname=%s", (SCHEMA,)) or query(
                self.target, "SELECT 1 FROM pg_namespace WHERE nspname=%s", (SCHEMA,)):
            raise MigrationError("Previous migration artifacts need operator cleanup")
        self.tables = query(self.source, TABLES)
        if not self.tables:
            raise MigrationError("Source database has no supported tables")
        for _, _, kind, persistence, identity, primary, extension, rls in self.tables:
            if kind != "r" or persistence != "p" or extension or rls:
                raise MigrationError("Partitioned, unlogged, foreign, materialized, extension-owned or RLS tables require a custom plan")
            if identity not in ("f", "i") and not (identity == "d" and primary):
                raise MigrationError("All source tables need a primary key or explicit replica identity")

    def prepare(self):
        # Prevent ALTER/DROP on existing tables while allowing normal DML.
        self.guard = connect(self.source_url, self.database)
        self.guard.autocommit = False
        names = sql.SQL(", ").join(identifier(t[0], t[1]) for t in self.tables)
        query(self.guard, sql.SQL("LOCK TABLE {} IN ACCESS SHARE MODE").format(names))
        self.dump = schema_dump(self.source_url, self.database)
        query(self.target, self.dump)
        query(self.target, 'SET statement_timeout=60000; SET lock_timeout=15000; SET search_path TO "$user", public')
        self.started = True  # cleanup checks object existence after partial failure
        for conn in (self.source, self.target):
            query(conn, sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMA)))
            query(conn, sql.SQL("CREATE TABLE {} (id integer PRIMARY KEY, token text NOT NULL)").format(identifier(SCHEMA, "barrier")))
        query(self.source, sql.SQL("INSERT INTO {} VALUES (1, %s)").format(identifier(SCHEMA, "barrier")), (self.token,))
        published = sql.SQL(", ").join([identifier(t[0], t[1]) for t in self.tables] + [identifier(SCHEMA, "barrier")])
        query(self.source, sql.SQL("CREATE PUBLICATION {} FOR TABLE {}").format(sql.Identifier(self.name), published))
        dsn = make_dsn(self.source_url, dbname=self.database, application_name=APP)
        query(self.target, sql.SQL("CREATE SUBSCRIPTION {} CONNECTION {} PUBLICATION {} WITH (copy_data = true)").format(
            sql.Identifier(self.name), sql.Literal(dsn), sql.Identifier(self.name)))

    def progress(self):
        ready, total = query(self.target, """SELECT count(*) FILTER (WHERE srsubstate='r'),count(*)
            FROM pg_subscription_rel WHERE srsubid=(SELECT oid FROM pg_subscription WHERE subname=%s)""", (self.name,))[0]
        rows = query(self.source, """SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),confirmed_flush_lsn)::bigint,
            active FROM pg_replication_slots WHERE slot_name=%s""", (self.name,))
        lag, active = rows[0] if rows else (None, False)
        return {"ready": ready, "total": total, "lag_bytes": lag, "streaming": active}

    def caught_up(self):
        p = self.progress()
        return p["total"] == len(self.tables) + 1 and p["ready"] == p["total"] and p["streaming"] and p["lag_bytes"] is not None and p["lag_bytes"] < 1024 * 1024

    def fence(self):
        # Acquire after managed writers stop. This also drains in-flight writes
        # and prevents outside DML on existing tables until handover finishes.
        names = sql.SQL(", ").join(identifier(t[0], t[1]) for t in self.tables)
        query(self.guard, sql.SQL("LOCK TABLE {} IN SHARE MODE").format(names))
        if fingerprint(schema_dump(self.source_url, self.database)) != fingerprint(self.dump):
            raise MigrationError("Source schema changed while copying; cutover aborted")
        # A WAL marker is database-specific: cluster-wide LSN polling alone can
        # hang on writes from unrelated databases or acknowledge the wrong DB.
        query(self.source, sql.SQL("UPDATE {} SET token=%s WHERE id=1").format(identifier(SCHEMA, "barrier")), (self.token + ":final",))

    def barrier_applied(self):
        return query(self.target, sql.SQL("SELECT token FROM {} WHERE id=1").format(identifier(SCHEMA, "barrier"))) == [(self.token + ":final",)]

    def verify_runtime(self, url, expected):
        conn = connect(url, self.database)
        try:
            actual = query(conn, sql.SQL("SELECT token FROM {} WHERE id=1").format(identifier(SCHEMA, "barrier")))
            if actual != [(expected,)]:
                raise MigrationError("Runtime endpoint does not reach the intended database")
            if query(conn, "SELECT current_schema()")[0][0] != "public":
                raise MigrationError("Runtime endpoint search_path must resolve to public")
        finally:
            conn.close()

    def finalize(self):
        if not self.barrier_applied():
            raise MigrationError("Destination has not applied the final committed marker")
        # Sequence state is not part of logical replication. Copy both last_value
        # and is_called while source writers remain fenced.
        sequences = query(self.source, """SELECT schemaname,sequencename FROM pg_sequences
            WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2""")
        for schema, name in sequences:
            last, called = query(self.source, sql.SQL("SELECT last_value,is_called FROM {}").format(identifier(schema, name)))[0]
            qualified = identifier(schema, name).as_string(self.target)
            query(self.target, "SELECT setval(%s::regclass,%s,%s)", (qualified, last, called))
        # The ordered marker + all tables in 'r' verifies replication delivery;
        # avoid full COUNT(*) scans during the short write pause.
        p = self.progress()
        if p["ready"] != len(self.tables) + 1:
            raise MigrationError("Not every table has completed initial synchronization")

    def cleanup(self):
        if not self.started:
            return
        if query(self.target, "SELECT 1 FROM pg_subscription WHERE subname=%s", (self.name,)):
            query(self.target, sql.SQL("DROP SUBSCRIPTION {}").format(sql.Identifier(self.name)))
        # A failed CREATE SUBSCRIPTION can leave its source slot behind.
        if query(self.source, "SELECT 1 FROM pg_replication_slots WHERE slot_name=%s", (self.name,)):
            query(self.source, "SELECT pg_drop_replication_slot(%s)", (self.name,))
        query(self.source, sql.SQL("DROP PUBLICATION IF EXISTS {}").format(sql.Identifier(self.name)))
        for conn in (self.source, self.target):
            query(conn, sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(SCHEMA)))

    def close(self):
        if self.guard:
            self.guard.close()
        self.source.close()
        self.target.close()
