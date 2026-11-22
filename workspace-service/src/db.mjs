import pg from "pg";
import { readFile } from "node:fs/promises";
import { migrationFiles } from "./migration-files.mjs";
import { baselineManualSchema } from "./migration-baseline.mjs";

export function createPool(config = {}) {
  const max = Number(process.env.WORKSPACE_DB_POOL_MAX || 6);
  if (!Number.isInteger(max) || max < 2 || max > 50)
    throw new Error(
      "WORKSPACE_DB_POOL_MAX must be an integer between 2 and 50",
    );
  return new pg.Pool({
    connectionString: process.env.DATABASE_URL,
    max,
    statement_timeout: 10000,
    connectionTimeoutMillis: 5000,
    ...config,
  });
}
async function verifyDatabase(pool) {
  if (!process.env.WORKSPACE_DATABASE_NAME) return;
  const { rows } = await pool.query("SELECT current_database() AS name");
  if (rows[0].name !== process.env.WORKSPACE_DATABASE_NAME)
    throw new Error(
      "Workspace database does not match WORKSPACE_DATABASE_NAME",
    );
}
export async function requireSchema(pool) {
  await verifyDatabase(pool);
  const names = (await migrationFiles()).map(({ name }) => name);
  const { rows } = await pool.query("SELECT name FROM workspace_migrations");
  const applied = new Set(rows.map((row) => row.name));
  if (names.some((name) => !applied.has(name)))
    throw new Error(
      "Workspace schema is out of date; run npm run migrate first",
    );
}
export async function transaction(pool, fn) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const value = await fn(client);
    await client.query("COMMIT");
    return value;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}
export async function migrate(pool) {
  await verifyDatabase(pool);
  await transaction(pool, async (client) => {
    await client.query(
      "SELECT pg_advisory_xact_lock(hashtext('bdc_workspace_migrations'))",
    );
    await client.query(
      "CREATE TABLE IF NOT EXISTS workspace_migrations(name text PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())",
    );
    const migrations = await Promise.all(
      (await migrationFiles()).map(async ({ name, file }) => ({
        name,
        sql: await readFile(file, "utf8"),
      })),
    );
    await baselineManualSchema(client, migrations);
    for (const { name, sql } of migrations) {
      const done = await client.query(
        "SELECT 1 FROM workspace_migrations WHERE name=$1",
        [name],
      );
      if (!done.rowCount) {
        await client.query(sql);
        await client.query(
          "INSERT INTO workspace_migrations(name) VALUES($1)",
          [name],
        );
      }
    }
  });
}
