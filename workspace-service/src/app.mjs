import express from "express";
import { randomUUID } from "node:crypto";
import { z, ZodError } from "zod";
import { HttpError, assert } from "./errors.mjs";
import { jwtIdentity } from "./auth.mjs";
import * as v from "./validation.mjs";
import { Store } from "./store.mjs";
import { Pages } from "./pages.mjs";
import { Documents } from "./documents.mjs";
import { Databases } from "./databases.mjs";
import { Sharing } from "./sharing.mjs";
import { Files } from "./files.mjs";
import { Fields } from "./fields.mjs";
import { Analytics } from "./analytics.mjs";
import { Trash } from "./trash.mjs";
import { Library } from "./library.mjs";

export function createApplication({
  pool,
  identity = jwtIdentity(process.env.JWT_SECRET),
  origins = [],
}) {
  const app = express(),
    store = new Store(pool),
    pages = new Pages(store),
    documents = new Documents(store, pages),
    databases = new Databases(store),
    sharing = new Sharing(store),
    files = new Files(store),
    fields = new Fields(store),
    analytics = new Analytics(store),
    trash = new Trash(store),
    library = new Library(store);
  app.disable("x-powered-by");
  app.set("trust proxy", false);
  app.use((req, res, next) => {
    res.set({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    const origin = req.headers.origin;
    if (origin && !origins.includes(origin))
      return res.status(403).json({ error: "Nguồn yêu cầu không hợp lệ." });
    next();
  });
  app.get("/health", (req, res) =>
    res.json({ status: "ok", service: "workspace" }),
  );
  app.get("/ready", async (req, res) => {
    try {
      await pool.query("SELECT 1");
      res.json({ status: "ready" });
    } catch {
      res.status(503).json({ status: "unavailable" });
    }
  });
  const api = express.Router();
  app.use("/api/v1/workspace", api);
  const limits = new Map();
  api.use(async (req, res, next) => {
    req.actor = await identity(req);
    const now = Date.now();
    let entry = limits.get(req.actor.id);
    if (!entry || now - entry.start > 60000) {
      entry = { start: now, count: 0 };
      limits.set(req.actor.id, entry);
    }
    assert(
      ++entry.count <= 600,
      429,
      "Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
    );
    if (limits.size > 5000)
      for (const [key, value] of limits)
        if (now - value.start > 60000) limits.delete(key);
    await store.register(req.actor);
    next();
  });
  api.use(express.json({ limit: "2mb" }));
  api.param("id", (req, res, next, id) => {
    v.uuid.parse(id);
    next();
  });
  api.param("spaceId", (req, res, next, id) => {
    v.uuid.parse(id);
    next();
  });
  api.get("/bootstrap", async (req, res) =>
    res.json(await store.bootstrap(req.actor)),
  );
  api.get("/library", async (req, res) => res.json(await library.list(req.actor, v.libraryQuery.parse(req.query))));
  api.get("/library/options", async (req, res) => res.json(await library.options(req.actor)));
  api.patch("/me", async (req, res) => {
    const { name } = z
      .object({ name: z.string().trim().min(1).max(100) })
      .strict()
      .parse(req.body);
    await pool.query("UPDATE workspace_users SET name=$2 WHERE id=$1", [
      req.actor.id,
      name,
    ]);
    res.json({ name });
  });
  api.post("/spaces", async (req, res) =>
    res.status(201).json(
      await store.createSpace(
        req.actor,
        z
          .object({ title: z.string().trim().min(1).max(120) })
          .strict()
          .parse(req.body).title,
      ),
    ),
  );
  api.get("/spaces/:spaceId/pages", async (req, res) =>
    res.json(
      await store.listPages(
        req.actor,
        req.params.spaceId,
        req.query.archived === "true",
      ),
    ),
  );
  api.get("/spaces/:spaceId/members", async (req, res) => {
    await store.space(pool, req.params.spaceId, req.actor);
    res.json(
      (
        await pool.query(
          "SELECT u.id,u.name,u.email,m.role FROM space_members m JOIN workspace_users u ON u.id=m.user_id WHERE m.space_id=$1 ORDER BY u.name",
          [req.params.spaceId],
        )
      ).rows,
    );
  });
  api.post("/spaces/:spaceId/pages", async (req, res) =>
    res
      .status(201)
      .json(
        await pages.create(
          req.actor,
          req.params.spaceId,
          v.createPage.parse(req.body),
        ),
      ),
  );
  api.get("/spaces/:spaceId/fields", async (req, res) =>
    res.json(
      await fields.list(
        req.actor,
        req.params.spaceId,
        req.query.archived === "true",
      ),
    ),
  );
  api.post("/spaces/:spaceId/fields", async (req, res) =>
    res
      .status(201)
      .json(
        await fields.create(
          req.actor,
          req.params.spaceId,
          v.createField.parse(req.body),
        ),
      ),
  );
  api.get("/fields/:id", async (req, res) =>
    res.json(await store.field(pool, req.params.id, req.actor)),
  );
  api.patch("/fields/:id", async (req, res) =>
    res.json(
      await fields.patch(
        req.actor,
        req.params.id,
        v.patchField.parse(req.body),
      ),
    ),
  );
  api.post("/fields/:id/archive", async (req, res) =>
    res.json(await fields.archive(req.actor, req.params.id)),
  );
  api.post("/fields/:id/restore", async (req, res) =>
    res.json(await fields.restore(req.actor, req.params.id)),
  );
  api.delete("/fields/:id", async (req, res) =>
    res.json(await trash.field(req.actor, req.params.id)),
  );
  api.get("/pages/:id/blocks/:blockId/activity", async (req, res) => {
    await store.page(pool, req.params.id, req.actor);
    const blockId = z
      .string()
      .regex(/^[a-zA-Z0-9_-]{1,100}$/)
      .parse(req.params.blockId);
    const row = (
      await pool.query(
        "SELECT b.updated_at,u.name author FROM block_activity b JOIN workspace_users u ON u.id=b.actor_id WHERE b.page_id=$1 AND b.block_id=$2",
        [req.params.id, blockId],
      )
    ).rows[0];
    res.json(row || null);
  });
  api.get("/search", async (req, res) =>
    res.json(
      await store.search(
        req.actor,
        z
          .string()
          .max(200)
          .parse(req.query.q || ""),
      ),
    ),
  );
  api.get("/pages/:id", async (req, res) =>
    res.json(await store.getPage(req.actor, req.params.id)),
  );
  api.delete("/pages/:id", async (req, res) =>
    res.json(await trash.page(req.actor, req.params.id)),
  );
  api.patch("/pages/:id", async (req, res) =>
    res.json(
      await pages.patch(req.actor, req.params.id, v.patchPage.parse(req.body)),
    ),
  );
  api.post("/pages/:id/archive", async (req, res) =>
    res.json(await pages.archive(req.actor, req.params.id)),
  );
  api.post("/pages/:id/restore", async (req, res) =>
    res.json(await pages.restore(req.actor, req.params.id)),
  );
  api.post("/pages/:id/duplicate", async (req, res) =>
    res.status(201).json(await pages.duplicate(req.actor, req.params.id)),
  );
  api.put("/pages/:id/favorite", async (req, res) =>
    res.json(
      await pages.favorite(
        req.actor,
        req.params.id,
        z.object({ favorite: z.boolean() }).strict().parse(req.body).favorite,
      ),
    ),
  );
  api.get("/pages/:id/document", async (req, res) =>
    res.json(await documents.read(req.actor, req.params.id)),
  );
  api.post("/pages/:id/ticket", async (req, res) =>
    res.json(await documents.ticket(req.actor, req.params.id)),
  );
  api.post("/pages/:id/initialize", async (req, res) =>
    res.json(
      await documents.write(req.actor, req.params.id, {
        ...z
          .object({
            update: z.string().max(6000000),
            operation_id: v.uuid,
            generation: z.number().int().positive(),
          })
          .strict()
          .parse(req.body),
        initialize: true,
      }),
    ),
  );
  api.get("/pages/:id/versions", async (req, res) =>
    res.json(await pages.versions(req.actor, req.params.id)),
  );
  api.post("/pages/:id/versions", async (req, res) =>
    res.status(201).json(
      await pages.createVersion(
        req.actor,
        req.params.id,
        z
          .object({ label: z.string().trim().min(1).max(120) })
          .strict()
          .parse(req.body).label,
      ),
    ),
  );
  api.post("/pages/:id/versions/:versionId/restore", async (req, res) =>
    res.json(
      await pages.restoreVersion(
        req.actor,
        req.params.id,
        v.uuid.parse(req.params.versionId),
      ),
    ),
  );
  api.get("/pages/:id/sharing", async (req, res) =>
    res.json(await sharing.members(req.actor, req.params.id)),
  );
  api.post("/invitations", async (req, res) => {
    const input = z
      .object({
        page_id: v.uuid.optional(),
        space_id: v.uuid.optional(),
        email: z.string().email().max(200),
        role: v.role,
      })
      .strict()
      .refine((value) => Boolean(value.page_id) !== Boolean(value.space_id))
      .parse(req.body);
    res.status(201).json(await sharing.invite(req.actor, input));
  });
  api.post("/invitations/:id/respond", async (req, res) =>
    res.json(
      await sharing.respond(
        req.actor,
        req.params.id,
        z
          .object({ action: z.enum(["accept", "decline"]) })
          .strict()
          .parse(req.body).action,
      ),
    ),
  );
  api.delete("/invitations/:id", async (req, res) =>
    res.json(await sharing.cancel(req.actor, req.params.id)),
  );
  api.patch("/grants", async (req, res) =>
    res.json(
      await sharing.grant(
        req.actor,
        z
          .object({
            page_id: v.uuid.optional(),
            space_id: v.uuid.optional(),
            member_id: z.string().regex(/^[1-9][0-9]{0,18}$/),
            role: v.role.nullable(),
          })
          .strict()
          .refine((value) => Boolean(value.page_id) !== Boolean(value.space_id))
          .parse(req.body),
      ),
    ),
  );
  api.get("/pages/:id/comments", async (req, res) =>
    res.json(await sharing.comments(req.actor, req.params.id)),
  );
  api.post("/pages/:id/comments", async (req, res) =>
    res
      .status(201)
      .json(
        await sharing.comment(
          req.actor,
          req.params.id,
          v.comment.parse(req.body),
        ),
      ),
  );
  api.patch("/comments/:id", async (req, res) =>
    res.json(
      await sharing.changeComment(
        req.actor,
        req.params.id,
        z
          .object({
            body: z.string().trim().min(1).max(10000).optional(),
            resolved: z.boolean().optional(),
            delete: z.boolean().optional(),
          })
          .strict()
          .parse(req.body),
      ),
    ),
  );
  api.get("/databases/:id", async (req, res) =>
    res.json(await databases.get(req.actor, req.params.id, req.query.cursor)),
  );
  api.put("/databases/:id/schema", async (req, res) => {
    const input = z
      .object({ fields: v.fields, version: z.number().int().positive() })
      .strict()
      .parse(req.body);
    res.json(
      await databases.setSchema(
        req.actor,
        req.params.id,
        input.fields,
        input.version,
      ),
    );
  });
  api.post("/databases/:id/records", async (req, res) => {
    const input = z
      .object({ title: v.title, values: z.record(z.unknown()).default({}) })
      .strict()
      .parse(req.body);
    res
      .status(201)
      .json(
        await databases.createRecord(
          req.actor,
          req.params.id,
          input.title,
          input.values,
        ),
      );
  });
  api.patch("/records/:id", async (req, res) =>
    res.json(
      await databases.patchRecord(
        req.actor,
        req.params.id,
        v.propertyPatch.parse(req.body),
      ),
    ),
  );
  api.post("/databases/:id/views", async (req, res) =>
    res
      .status(201)
      .json(
        await databases.saveView(
          req.actor,
          req.params.id,
          v.view.parse(req.body),
        ),
      ),
  );
  api.put("/databases/:id/views/:viewId", async (req, res) => {
    const input = z
      .object({ view: v.view, version: z.number().int().positive() })
      .strict()
      .parse(req.body);
    res.json(
      await databases.saveView(
        req.actor,
        req.params.id,
        input.view,
        v.uuid.parse(req.params.viewId),
        input.version,
      ),
    );
  });
  api.post(
    "/pages/:id/files",
    express.raw({ type: "application/octet-stream", limit: "10mb" }),
    async (req, res) =>
      res
        .status(201)
        .json(
          await files.upload(
            req.actor,
            req.params.id,
            req.body,
            req.headers["x-file-name"],
          ),
        ),
  );
  api.get("/files/:id", async (req, res) => {
    const file = await files.get(req.actor, req.params.id);
    res.set({
      "Content-Type": file.mime,
      "Content-Disposition": `${file.mime === "application/pdf" ? "attachment" : "inline"}; filename*=UTF-8''${encodeURIComponent(file.filename)}`,
      "Content-Security-Policy": "default-src 'none'; sandbox",
    });
    res.send(file.content);
  });
  api.get("/tab-pages", async (req, res) =>
    res.json(
      await store.tabPages(
        req.actor,
        z.string().trim().max(200).default("").parse(req.query.q),
        v.uuid.optional().parse(req.query.field),
      ),
    ),
  );
  api.get("/pages/:id/activity", async (req, res) => {
    await store.page(pool, req.params.id, req.actor);
    const events = await pool.query(
      "SELECT a.id,a.actor_id,a.action,a.detail,a.created_at,u.name actor FROM workspace_activity a JOIN workspace_users u ON u.id=a.actor_id WHERE a.page_id=$1 ORDER BY a.created_at DESC LIMIT 100",
      [req.params.id],
    );
    const edits = await pool.query(
      "SELECT min(o.operation_id::text) id,u.id actor_id,'document.edited' action,max(o.created_at) created_at,u.name actor FROM document_operations o JOIN workspace_users u ON u.id=o.author_id WHERE o.page_id=$1 GROUP BY u.id,u.name,date_trunc('minute',o.created_at) ORDER BY created_at DESC LIMIT 100",
      [req.params.id],
    );
    res.json(
      [...events.rows, ...edits.rows]
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 100),
    );
  });
  api.post("/pages/:id/view", async (req, res) =>
    res.json(await analytics.visit(req.actor, req.params.id)),
  );
  api.get("/pages/:id/analytics", async (req, res) =>
    res.json(
      await analytics.read(
        req.actor,
        req.params.id,
        Number(z.enum(["7", "28", "90"]).default("28").parse(req.query.days)),
      ),
    ),
  );
  api.get("/pages/:id/references", async (req, res) => {
    const page = await store.page(pool, req.params.id, req.actor);
    const candidates = await pool.query(
      "SELECT p.id,p.title,p.icon FROM pages p JOIN page_links l ON l.source_id=p.id WHERE p.id<>$1 AND p.archived_at IS NULL AND l.target_id=$1 LIMIT 100",
      [page.id],
    );
    const backlinks = [];
    for (const candidate of candidates.rows) {
      try {
        await store.page(pool, candidate.id, req.actor);
        backlinks.push(candidate);
      } catch {}
    }
    res.json({ sources: page.sources, backlinks });
  });
  api.get("/notifications", async (req, res) => {
    const notifications = await pool.query(
      "SELECT n.*,p.title FROM workspace_notifications n JOIN pages p ON p.id=n.page_id WHERE n.user_id=$1 AND n.read_at IS NULL ORDER BY n.created_at DESC LIMIT 100",
      [req.actor.id],
    );
    const visible = [];
    for (const notification of notifications.rows) {
      try {
        await store.page(pool, notification.page_id, req.actor);
        visible.push(notification);
      } catch {}
    }
    res.json(visible);
  });
  api.post("/notifications/:id/read", async (req, res) => {
    await pool.query(
      "UPDATE workspace_notifications SET read_at=now() WHERE id=$1 AND user_id=$2",
      [req.params.id, req.actor.id],
    );
    res.json({ id: req.params.id });
  });
  api.post("/legacy-notes", async (req, res) => {
    const input = z
      .object({
        note_id: z.string().min(1).max(100),
        title: v.title,
        content: z.string().max(100000),
        course_id: z.number().int().positive().nullable().optional(),
      })
      .strict()
      .parse(req.body);
    const result = await store.tx(async (client) => {
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
        `legacy:${req.actor.id}:${input.note_id}`,
      ]);
      const previous = (
        await client.query(
          "SELECT page_id FROM legacy_note_imports WHERE user_id=$1 AND note_id=$2",
          [req.actor.id, input.note_id],
        )
      ).rows[0];
      if (previous) return { id: previous.page_id };
      const space = (
        await client.query(
          "SELECT id FROM spaces WHERE owner_id=$1 AND kind='personal'",
          [req.actor.id],
        )
      ).rows[0];
      assert(space, 409, "Mở Workspace trước khi đưa ghi chú vào.");
      const page = await store.insertPage(client, req.actor, space.id, {
        title: input.title,
        sources: [
          { type: "notebook", id: input.note_id, label: "Vở ghi cá nhân" },
          ...(input.course_id
            ? [
                {
                  type: "course",
                  id: String(input.course_id),
                  label: "Khóa học",
                  url: `/lms/student/courses/${input.course_id}`,
                },
              ]
            : []),
        ],
      });
      await client.query("UPDATE pages SET initial_markdown=$2 WHERE id=$1", [
        page.id,
        input.content,
      ]);
      await client.query(
        "INSERT INTO legacy_note_imports(user_id,note_id,page_id) VALUES($1,$2,$3)",
        [req.actor.id, input.note_id, page.id],
      );
      return page;
    });
    res.status(201).json(result);
  });
  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    if (error instanceof ZodError)
      return res.status(400).json({
        error: "Dữ liệu không hợp lệ.",
        code: "validation_error",
        issues: error.issues
          .map((issue) => ({ path: issue.path, message: issue.message }))
          .slice(0, 8),
      });
    if (error instanceof HttpError)
      return res
        .status(error.status)
        .json({ error: error.message, code: error.code });
    if (error.type === "entity.too.large")
      return res
        .status(413)
        .json({ error: "Yêu cầu vượt giới hạn dung lượng." });
    if (error.type === "entity.parse.failed")
      return res.status(400).json({ error: "JSON không hợp lệ." });
    if (error.code === "23505")
      return res
        .status(409)
        .json({ error: "Thông tin hoặc lời mời đã tồn tại." });
    if (error.code === "22P02" || error.code === "23503")
      return res
        .status(400)
        .json({ error: "Tham chiếu dữ liệu không hợp lệ." });
    console.error("Workspace request failed", {
      code: error.code || "internal_error",
    });
    res.status(500).json({
      error: "Chưa thể hoàn thành thao tác. Bạn có thể thử lại.",
      code: "internal_error",
    });
  });
  return { app, store, pages, fields, documents, databases, sharing, files };
}
