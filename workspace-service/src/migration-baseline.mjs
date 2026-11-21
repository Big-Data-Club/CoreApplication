import { randomUUID } from "node:crypto";

const identifier = (value) => `"${value.replaceAll('"', '""')}"`;

// Compare structure, not row counts: manually applied SQL may already contain data.
async function schemaSignature(client, schema, tables) {
  const { rows } = await client.query(
    `SELECT c.relname AS name,
       (SELECT jsonb_agg(jsonb_build_array(a.attname,
          format_type(a.atttypid,a.atttypmod),a.attnotnull,
          pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated)
          ORDER BY a.attnum)
        FROM pg_attribute a LEFT JOIN pg_attrdef d
          ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped) AS columns,
       (SELECT jsonb_agg(jsonb_build_array(k.conname,pg_get_constraintdef(k.oid))
          ORDER BY k.conname)
        FROM pg_constraint k WHERE k.conrelid=c.oid) AS constraints,
       (SELECT jsonb_agg(pg_get_indexdef(i.indexrelid) ORDER BY ic.relname)
        FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid
        WHERE i.indrelid=c.oid) AS indexes
     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname=$1 AND c.relkind='r' AND c.relname=ANY($2::text[])
     ORDER BY c.relname`,
    [schema, tables],
  );
  return JSON.stringify(rows)
    .replaceAll(`${identifier(schema)}.`, "")
    .replaceAll(`${schema}.`, "");
}

// Only adopt an exact, contiguous migration prefix when the ledger is empty.
// Build reference schemas inside the caller's transaction; never modify live tables.
export async function baselineManualSchema(client, migrations) {
  const { rows: ledger } = await client.query(
    "SELECT name FROM workspace_migrations LIMIT 1",
  );
  if (ledger.length) return;
  const { rows: context } = await client.query(
    "SELECT current_schema() AS schema, current_setting('search_path') AS path, to_regclass('workspace_users') AS users",
  );
  if (!context[0].users) return;
  const { schema, path } = context[0];
  const reference = `workspace_baseline_${randomUUID().replaceAll("-", "")}`;
  await client.query(`CREATE SCHEMA ${identifier(reference)}`);
  await client.query("SELECT set_config('search_path',$1,true)", [reference]);
  const signatures = [];
  for (const migration of migrations) {
    await client.query(migration.sql);
    const { rows } = await client.query(
      "SELECT tablename FROM pg_tables WHERE schemaname=$1 ORDER BY tablename",
      [reference],
    );
    const tables = rows.map((row) => row.tablename);
    signatures.push({
      tables,
      value: await schemaSignature(client, reference, tables),
    });
  }
  const tables = signatures.at(-1).tables;
  await client.query("SELECT set_config('search_path',$1,true)", [path]);
  const actual = await schemaSignature(client, schema, tables);
  const prefix = signatures.findIndex((entry) => entry.value === actual);
  await client.query(`DROP SCHEMA ${identifier(reference)} CASCADE`);
  if (prefix < 0)
    throw new Error(
      "Workspace tables exist without a migration ledger and do not match a known migration prefix. No changes were applied; inspect the schema before retrying.",
    );
  // Migration 009 has a data policy as well as an index. Reapply its bounded
  // cleanup so matching DDL alone cannot bypass the four-version policy.
  const adopted = migrations.slice(0, prefix + 1);
  const retention = adopted.find(
    (entry) => entry.name === "009_bounded_versions.sql",
  );
  if (retention)
    await client.query(
      retention.sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS "),
    );
  await client.query(
    "INSERT INTO workspace_migrations(name) SELECT unnest($1::text[])",
    [adopted.map((entry) => entry.name)],
  );
  console.info(
    `Workspace verified and recorded ${adopted.length} manually applied migrations`,
  );
}
