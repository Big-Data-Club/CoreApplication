import { createServer } from "node:http";
import { createPool, migrate } from "./db.mjs";
import { createApplication } from "./app.mjs";
import { attachRealtime } from "./realtime.mjs";

const pool = createPool();
await migrate(pool);
const origins = (
  process.env.WORKSPACE_ALLOWED_ORIGINS ||
  "http://localhost:3000,http://127.0.0.1:3000"
)
  .split(",")
  .map((v) => v.trim())
  .filter(Boolean);
const services = createApplication({ pool, origins }),
  server = createServer(services.app);
const closeRealtime = attachRealtime({ server, pool, ...services, origins });
const port = Number(process.env.PORT || 8088);
server.listen(port, "0.0.0.0", () =>
  console.info(`Workspace ready on port ${port}`),
);
let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  await closeRealtime();
  server.close();
  await pool.end();
}
process.on("SIGTERM", () => void stop());
process.on("SIGINT", () => void stop());
