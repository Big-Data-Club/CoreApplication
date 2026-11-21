import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { createPool, migrate, requireSchema } from "../src/db.mjs";

const only = process.env.TEST_DATABASE_URL ? test : test.skip;
const directory = new URL("../migrations/", import.meta.url);
const names = (await readdir(directory))
  .filter((name) => name.endsWith(".sql"))
  .sort();

async function isolated(run) {
  const admin = createPool({ connectionString: process.env.TEST_DATABASE_URL });
  const schema = `baseline_test_${randomUUID().replaceAll("-", "")}`;
  let pool;
  try {
    assert.equal(
      (await admin.query("SELECT current_database() AS name")).rows[0].name,
      "workspace_test",
    );
    await admin.query(`CREATE SCHEMA ${schema}`);
    pool = createPool({
      connectionString: process.env.TEST_DATABASE_URL,
      options: `-c search_path=${schema}`,
    });
    await run(pool, schema);
  } finally {
    await pool?.end();
    await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
    await admin.end();
  }
}

async function manual(pool, count) {
  for (const name of names.slice(0, count))
    await pool.query(await readFile(new URL(name, directory), "utf8"));
  await pool.query(
    "INSERT INTO workspace_users(id,email,name) VALUES('baseline','baseline@example.test','Existing user')",
  );
}

for (const count of [1, 8, 10]) {
  only(
    `adopts ${count} manually applied migrations, preserves data and safely retries`,
    async () => {
      await isolated(async (pool) => {
        await manual(pool, count);
        await migrate(pool);
        await migrate(pool);
        await requireSchema(pool);
        assert.equal(
          (
            await pool.query(
              "SELECT count(*)::int AS count FROM workspace_migrations",
            )
          ).rows[0].count,
          names.length,
        );
        assert.equal(
          (
            await pool.query(
              "SELECT name FROM workspace_users WHERE id='baseline'",
            )
          ).rows[0].name,
          "Existing user",
        );
        assert.equal(
          (
            await pool.query(
              "SELECT count(*)::int AS count FROM pg_namespace WHERE nspname LIKE 'workspace_baseline_%'",
            )
          ).rows[0].count,
          0,
        );
      });
    },
  );
}

only(
  "rejects incomplete manual schema without recording migrations or changing data",
  async () => {
    await isolated(async (pool) => {
      await manual(pool, 1);
      await pool.query("ALTER TABLE pages DROP CONSTRAINT pages_kind_check");
      await assert.rejects(
        migrate(pool),
        /do not match a known migration prefix/,
      );
      assert.equal(
        (
          await pool.query(
            "SELECT to_regclass('workspace_migrations') AS ledger",
          )
        ).rows[0].ledger,
        null,
      );
      assert.equal(
        (await pool.query("SELECT count(*)::int AS count FROM workspace_users"))
          .rows[0].count,
        1,
      );
    });
  },
);

only(
  "restores the four-version policy when adopting a manually applied schema",
  async () => {
    await isolated(async (pool) => {
      await manual(pool, 10);
      const space = randomUUID(),
        page = randomUUID();
      await pool.query(
        "INSERT INTO spaces(id,title,kind,owner_id) VALUES($1,'Test','personal','baseline')",
        [space],
      );
      await pool.query(
        "INSERT INTO pages(id,space_id,created_by,updated_by) VALUES($1,$2,'baseline','baseline')",
        [page, space],
      );
      for (let index = 0; index < 6; index++)
        await pool.query(
          "INSERT INTO page_versions(id,page_id,author_id,title,label,state,properties) VALUES($1,$2,'baseline','Test','Snapshot',''::bytea,'{}')",
          [randomUUID(), page],
        );
      await migrate(pool);
      assert.equal(
        (await pool.query("SELECT count(*)::int AS count FROM page_versions"))
          .rows[0].count,
        4,
      );
    });
  },
);
