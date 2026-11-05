import pg from "pg";
import { readFile, readdir } from "node:fs/promises";

export function createPool(config = {}) {
  return new pg.Pool({
    connectionString: process.env.DATABASE_URL,
    max: 12,
    statement_timeout: 10000,
    connectionTimeoutMillis: 5000,
    ...config,
  });
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
  await transaction(pool, async (client) => {
    await client.query(
      "SELECT pg_advisory_xact_lock(hashtext('bdc_workspace_migrations'))",
    );
    await client.query(
      "CREATE TABLE IF NOT EXISTS workspace_migrations(name text PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())",
    );
    const names = (await readdir(new URL("../migrations/", import.meta.url)))
      .filter((n) => n.endsWith(".sql"))
      .sort();
    for (const name of names) {
      const done = await client.query(
        "SELECT 1 FROM workspace_migrations WHERE name=$1",
        [name],
      );
      if (!done.rowCount) {
        await client.query(
          await readFile(
            new URL(`../migrations/${name}`, import.meta.url),
            "utf8",
          ),
        );
        await client.query(
          "INSERT INTO workspace_migrations(name) VALUES($1)",
          [name],
        );
      }
    }
  });
}
