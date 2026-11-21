import { createPool, migrate } from "./db.mjs";

if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL is required");
const pool = createPool();
try {
  await migrate(pool);
  console.info("Workspace migrations are up to date");
} finally {
  await pool.end();
}
