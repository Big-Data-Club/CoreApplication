import { readdir } from "node:fs/promises";

// Paths may change between releases; the ledger identity remains the SQL basename.
export async function migrationFiles(
  directory = new URL("../migrations/", import.meta.url),
) {
  const files = new Map();
  async function visit(folder) {
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const file = new URL(
        entry.name + (entry.isDirectory() ? "/" : ""),
        folder,
      );
      if (entry.isDirectory()) await visit(file);
      else if (entry.isFile() && entry.name.endsWith(".sql")) {
        if (files.has(entry.name))
          throw new Error(`Duplicate migration name: ${entry.name}`);
        files.set(entry.name, file);
      }
    }
  }
  await visit(directory);
  return [...files]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([name, file]) => ({ name, file }));
}
