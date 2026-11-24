import { createHash, timingSafeEqual } from "node:crypto";
import { Router, json } from "express";
import { z } from "zod";
import { assert } from "./errors.mjs";
import { createPage, safeUrl, title, uuid } from "./validation.mjs";

const saveInput = z.object({
  destination_id: uuid,
  request_id: uuid,
  title,
  markdown: z.string().min(1).max(100000).refine((value) => value.trim().length > 0),
  source_url: safeUrl.refine((value) => /^https?:\/\//i.test(value)).nullish(),
}).strict();

export function workspaceMcpRouter(store, pages, secret) {
  const router = Router();
  const expected = Buffer.from(secret || "");
  router.use((req, _res, next) => {
    assert(expected.length >= 32, 404, "Workspace MCP is disabled.");
    const presented = Buffer.from(req.headers.authorization?.match(/^Bearer (\S+)$/)?.[1] || "");
    assert(presented.length === expected.length && timingSafeEqual(presented, expected),
      401, "Service authentication required.");
    const id = req.headers["x-workspace-actor"];
    assert(typeof id === "string" && /^[1-9][0-9]{0,18}$/.test(id), 401, "Invalid Workspace identity.");
    req.actor = { id };
    next();
  });

  router.get("/destinations", async (req, res) => {
    assert(req.headers["x-workspace-scope"] === "workspace:read", 403, "Workspace read scope required.");
    const { rows } = await store.pool.query(
      `SELECT s.id,s.title,s.kind FROM spaces s
       JOIN space_members m ON m.space_id=s.id AND m.user_id=$1 AND m.role='owner'
       WHERE s.owner_id=$1 AND s.kind='personal'`, [req.actor.id],
    );
    assert(rows.length, 404, "Open Workspace to create your personal space.", "workspace_not_initialized");
    res.json({ destinations: rows });
  });

  router.post("/pages", (req, _res, next) => {
    assert(req.headers["x-workspace-scope"] === "workspace:create", 403, "Workspace create scope required.");
    next();
  }, json({ limit: "1mb" }), async (req, res) => {
    const { destination_id, request_id, title, markdown, source_url } = saveInput.parse(req.body);
    const input = createPage.parse({
      title,
      markdown,
      sources: source_url ? [{ type: "url", label: "Nguồn bài viết", url: source_url }] : [],
    });
    const user = req.actor;
    const hash = createHash("sha256").update(JSON.stringify([destination_id, input])).digest("hex");
    const result = await store.tx(async (client) => {
      await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [
        `workspace-mcp:${user.id}:${request_id}`,
      ]);
      const space = await store.space(client, destination_id, user, 3);
      assert(space.kind === "personal" && space.owner_id === user.id,
        404, "Personal destination not found.");
      const { rows: [previous] } = await client.query(
        "SELECT page_id,payload_hash FROM workspace_mcp_page_requests WHERE user_id=$1 AND request_id=$2",
        [user.id, request_id],
      );
      if (previous) {
        assert(previous.payload_hash === hash, 409, "Request ID already used with different content.");
        assert(previous.page_id, 404, "The original page was deleted.");
        await store.page(client, previous.page_id, user);
        return { page_id: previous.page_id, created: false };
      }
      const page = await pages.createInTransaction(client, user, destination_id, input);
      await client.query(
        "INSERT INTO workspace_mcp_page_requests(user_id,request_id,payload_hash,page_id) VALUES($1,$2,$3,$4)",
        [user.id, request_id, hash, page.id],
      );
      return { page_id: page.id, created: true };
    });
    res.status(result.created ? 201 : 200).json(result);
  });

  return router;
}
