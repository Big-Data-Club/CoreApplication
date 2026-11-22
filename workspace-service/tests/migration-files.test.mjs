import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import { migrationFiles } from "../src/migration-files.mjs";

test("release directories keep ledger names and global order; duplicates are rejected", async () => {
  const root = await mkdtemp(join(tmpdir(), "workspace-migrations-"));
  try {
    await mkdir(join(root, "releases/older"), { recursive: true });
    await mkdir(join(root, "releases/newer"), { recursive: true });
    await writeFile(join(root, "releases/older/002.sql"), "SELECT 2;");
    await writeFile(join(root, "releases/newer/001.sql"), "SELECT 1;");
    await writeFile(join(root, "releases/older/manifest.json"), "{}");
    const directory = pathToFileURL(root + "/");
    assert.deepEqual(
      (await migrationFiles(directory)).map(({ name }) => name),
      ["001.sql", "002.sql"],
    );
    await writeFile(join(root, "001.sql"), "SELECT 3;");
    await assert.rejects(migrationFiles(directory), /Duplicate migration name/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
