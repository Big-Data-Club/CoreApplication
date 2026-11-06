import { before, after, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { randomUUID, randomBytes } from "node:crypto";
import { SignJWT } from "jose";
import * as Y from "yjs";
import { WebSocket } from "ws";
import { createPool, migrate } from "../src/db.mjs";
import { createApplication } from "../src/app.mjs";
import { attachRealtime } from "../src/realtime.mjs";
import { HttpError } from "../src/errors.mjs";
import { jwtIdentity } from "../src/auth.mjs";

const enabled = Boolean(process.env.TEST_DATABASE_URL);
let pool, server, services, base, closeRealtime;
const users = {
  alice: { id: "901", email: "alice@workspace.test", name: "Alice" },
  bob: { id: "902", email: "bob@workspace.test", name: "Bob" },
  eve: { id: "903", email: "eve@workspace.test", name: "Eve" },
};
before(async () => {
  if (!enabled) return;
  pool = createPool({
    connectionString: process.env.TEST_DATABASE_URL,
    max: 12,
  });
  const database = (await pool.query("SELECT current_database() name")).rows[0]
    .name;
  assert.equal(
    database,
    "workspace_test",
    "Tests only run against the isolated workspace_test database.",
  );
  await migrate(pool);
  services = createApplication({
    pool,
    origins: ["http://workspace.test"],
    identity: async (req) => {
      const user = users[req.headers.authorization?.replace("Bearer ", "")];
      if (!user) throw new HttpError(401, "Unauthorized");
      return user;
    },
  });
  server = createServer(services.app);
  closeRealtime = attachRealtime({
    server,
    pool,
    ...services,
    origins: ["http://workspace.test"],
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}/api/v1/workspace`;
});
after(async () => {
  if (!enabled) return;
  await closeRealtime();
  await new Promise((resolve) => server.close(resolve));
  await pool.end();
});
beforeEach(async () => {
  if (enabled) {
    await pool.query("TRUNCATE workspace_users CASCADE");
    for (const user of Object.values(users))
      await services.store.register(user);
  }
});
async function request(actor, path, method = "GET", body) {
  const response = await fetch(base + path, {
    method,
    headers: {
      ...(actor ? { Authorization: `Bearer ${actor}` } : {}),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: response.status, data: await response.json() };
}
async function home(actor = "alice") {
  return (await request(actor, "/bootstrap")).data;
}
async function create(actor = "alice", options = {}) {
  const initial = await home(actor);
  const space = initial.spaces.find((s) => s.kind === "personal");
  return (
    await request(actor, `/spaces/${space.id}/pages`, "POST", {
      title: "A page",
      ...options,
    })
  ).data;
}
async function invite(page, role = "viewer", target = "bob") {
  const invitation = await request("alice", "/invitations", "POST", {
    page_id: page.id,
    email: users[target].email,
    role,
  });
  assert.equal(invitation.status, 201);
  const result = await request(
    target,
    `/invitations/${invitation.data.id}/respond`,
    "POST",
    { action: "accept" },
  );
  assert.equal(result.status, 200);
  return invitation.data;
}
function change(text) {
  const doc = new Y.Doc(),
    node = new Y.XmlElement("paragraph"),
    value = new Y.XmlText();
  value.insert(0, text);
  node.insert(0, [value]);
  doc.getXmlFragment("document-store").insert(0, [node]);
  const update = Buffer.from(Y.encodeStateAsUpdate(doc)).toString("base64");
  doc.destroy();
  return update;
}
const only = enabled ? test : test.skip;

only(
  "authentication and private personal workspace creation are isolated and idempotent",
  async () => {
    assert.equal((await request(null, "/bootstrap")).status, 401);
    const [a, b] = await Promise.all([home(), home()]);
    assert.equal(a.spaces[0].id, b.spaces[0].id);
    const other = await home("bob");
    assert.notEqual(a.spaces[0].id, other.spaces[0].id);
    const page = await create();
    assert.equal((await request("bob", `/pages/${page.id}`)).status, 404);
    assert.equal(
      (await request("bob", `/spaces/${page.space_id}/pages`)).status,
      404,
    );
  },
);
only(
  "a direct page invitation does not disclose the parent space or child pages",
  async () => {
    const parent = await create(),
      child = await create("alice", {
        parent_id: parent.id,
        title: "Secret child",
      });
    await invite(parent);
    assert.equal((await request("bob", `/pages/${parent.id}`)).status, 200);
    assert.equal((await request("bob", `/pages/${child.id}`)).status, 404);
    assert.equal(
      (await request("bob", `/spaces/${parent.space_id}/pages`)).status,
      404,
    );
    assert.deepEqual((await request("bob", "/search?q=Secret")).data, []);
    assert.equal(
      (
        await request("bob", `/pages/${parent.id}`, "PATCH", {
          version: 1,
          title: "No",
        })
      ).status,
      403,
    );
  },
);
only(
  "commenter can discuss a page but cannot change document content",
  async () => {
    const page = await create();
    await invite(page, "commenter");
    assert.equal(
      (
        await request("bob", `/pages/${page.id}/comments`, "POST", {
          body: "Question",
        })
      ).status,
      201,
    );
    await assert.rejects(
      services.documents.write(users.bob, page.id, {
        operation_id: randomUUID(),
        generation: 1,
        update: change("No"),
      }),
      (error) => error.status === 403,
    );
    const comment = (await request("bob", `/pages/${page.id}/comments`))
      .data[0];
    assert.equal(
      (
        await request("eve", `/comments/${comment.id}`, "PATCH", {
          body: "Hijack",
        })
      ).status,
      404,
    );
  },
);
only(
  "revocation applies to open-page reads, search, comments and documents",
  async () => {
    const page = await create("alice", { title: "Visible secret" });
    await invite(page, "editor");
    await request("alice", "/grants", "PATCH", {
      page_id: page.id,
      member_id: users.bob.id,
      role: null,
    });
    for (const path of [
      `/pages/${page.id}`,
      `/pages/${page.id}/document`,
      `/pages/${page.id}/comments`,
    ])
      assert.equal((await request("bob", path)).status, 404);
    assert.deepEqual((await request("bob", "/search?q=Visible")).data, []);
  },
);
only(
  "pending invitations are recipient-bound and recheck the sender authority",
  async () => {
    const page = await create();
    const pending = await request("alice", "/invitations", "POST", {
      page_id: page.id,
      email: users.bob.email,
      role: "editor",
    });
    assert.equal(
      (
        await request(
          "eve",
          `/invitations/${pending.data.id}/respond`,
          "POST",
          { action: "accept" },
        )
      ).status,
      404,
    );
    await request("alice", `/invitations/${pending.data.id}`, "DELETE");
    assert.equal(
      (
        await request(
          "bob",
          `/invitations/${pending.data.id}/respond`,
          "POST",
          { action: "accept" },
        )
      ).status,
      404,
    );
  },
);
only(
  "hierarchy prevents cycles, foreign parents and stale metadata overwrites",
  async () => {
    const a = await create(),
      b = await create("alice", { parent_id: a.id });
    assert.equal(
      (
        await request("alice", `/pages/${a.id}`, "PATCH", {
          version: 1,
          parent_id: b.id,
        })
      ).status,
      400,
    );
    assert.equal(
      (
        await request("alice", `/pages/${a.id}`, "PATCH", {
          version: 1,
          title: "Changed",
        })
      ).status,
      200,
    );
    assert.equal(
      (
        await request("alice", `/pages/${a.id}`, "PATCH", {
          version: 1,
          title: "Stale",
        })
      ).status,
      409,
    );
    const foreign = await create("bob");
    assert.equal(
      (
        await request("alice", `/pages/${b.id}`, "PATCH", {
          version: 1,
          parent_id: foreign.id,
        })
      ).status,
      404,
    );
  },
);
only(
  "branch restore does not resurrect children archived before that branch operation",
  async () => {
    const parent = await create(),
      child = await create("alice", { parent_id: parent.id }),
      earlier = await create("alice", { parent_id: parent.id });
    await request("alice", `/pages/${earlier.id}/archive`, "POST", {});
    await request("alice", `/pages/${parent.id}/archive`, "POST", {});
    assert.equal((await request("alice", `/pages/${child.id}`)).status, 404);
    await request("alice", `/pages/${parent.id}/restore`, "POST", {});
    assert.equal((await request("alice", `/pages/${child.id}`)).status, 200);
    assert.equal((await request("alice", `/pages/${earlier.id}`)).status, 404);
  },
);
only(
  "concurrent document edits merge durably and duplicate delivery is idempotent",
  async () => {
    const page = await create();
    await invite(page, "editor");
    const operation = randomUUID();
    await Promise.all([
      services.documents.write(users.alice, page.id, {
        operation_id: operation,
        generation: 1,
        update: change("Alice"),
      }),
      services.documents.write(users.bob, page.id, {
        operation_id: randomUUID(),
        generation: 1,
        update: change("Bob"),
      }),
    ]);
    const result = await services.documents.read(users.alice, page.id),
      doc = new Y.Doc();
    Y.applyUpdate(doc, Buffer.from(result.state, "base64"));
    const text = doc.getXmlFragment("document-store").toString();
    doc.destroy();
    assert.match(text, /Alice/);
    assert.match(text, /Bob/);
    await services.documents.write(users.alice, page.id, {
      operation_id: operation,
      generation: 1,
      update: change("Must not appear"),
    });
    assert.equal(
      (await services.documents.read(users.alice, page.id)).revision,
      result.revision,
    );
  },
);
only(
  "invalid document changes roll back without marking an operation persisted",
  async () => {
    const page = await create();
    await assert.rejects(
      services.documents.write(users.alice, page.id, {
        operation_id: randomUUID(),
        generation: 1,
        update: "aW52YWxpZA==",
      }),
      (error) => error.status === 400,
    );
    assert.equal(
      Number((await services.documents.read(users.alice, page.id)).revision),
      0,
    );
  },
);
only(
  "restoring a version advances generation and rejects stale clients",
  async () => {
    const page = await create();
    await services.documents.write(users.alice, page.id, {
      operation_id: randomUUID(),
      generation: 1,
      update: change("Before"),
    });
    const version = await services.pages.createVersion(
      users.alice,
      page.id,
      "Milestone",
    );
    await services.documents.write(users.alice, page.id, {
      operation_id: randomUUID(),
      generation: 1,
      update: change("Later"),
    });
    await services.pages.restoreVersion(users.alice, page.id, version.id);
    await assert.rejects(
      services.documents.write(users.alice, page.id, {
        operation_id: randomUUID(),
        generation: 1,
        update: change("Stale"),
      }),
      (error) => error.code === "generation_changed",
    );
    assert.equal(
      (await services.documents.read(users.alice, page.id)).generation,
      2,
    );
  },
);
only(
  "database records share identity across views and inherit collection access",
  async () => {
    const db = await create("alice", { kind: "database" });
    const record = await request(
      "alice",
      `/databases/${db.id}/records`,
      "POST",
      {
        title: "Read paper",
        values: { status: "todo", date: { start: "2026-11-05" } },
      },
    );
    assert.equal(record.status, 201);
    await invite(db, "editor");
    const data = (await request("bob", `/databases/${db.id}`)).data;
    assert.deepEqual(
      data.views.map((v) => v.type),
      ["table", "board", "calendar"],
    );
    assert.equal(
      (await request("bob", `/pages/${record.data.id}`)).status,
      200,
    );
    assert.equal(
      (
        await request("bob", `/records/${record.data.id}`, "PATCH", {
          version: 1,
          values: { status: "done" },
        })
      ).status,
      200,
    );
    const updated = (await request("alice", `/databases/${db.id}`)).data
      .records[0];
    assert.equal(updated.id, record.data.id);
    assert.equal(updated.properties.status, "done");
    assert.equal(
      (
        await request("alice", `/records/${record.data.id}`, "PATCH", {
          version: 1,
          values: { status: "todo" },
        })
      ).status,
      409,
    );
  },
);
only(
  "database values and structure reject invalid dates, unknown options and destructive type changes",
  async () => {
    const db = await create("alice", { kind: "database" });
    for (const values of [
      { status: "unknown" },
      { date: { start: "2026-99-99" } },
      { assignee: ["903"] },
    ])
      assert.ok(
        (
          await request("alice", `/databases/${db.id}/records`, "POST", {
            title: "Bad",
            values,
          })
        ).status >= 400,
      );
    await request("alice", `/databases/${db.id}/records`, "POST", {
      title: "Valid",
      values: { status: "todo" },
    });
    const schema = (await request("alice", `/databases/${db.id}`)).data;
    assert.equal(
      (
        await request("alice", `/databases/${db.id}/schema`, "PUT", {
          version: 1,
          fields: schema.fields.map((f) =>
            f.id === "status"
              ? { id: "status", name: "Status", type: "text" }
              : f,
          ),
        })
      ).status,
      409,
    );
    await invite(db, "editor");
    assert.equal(
      (
        await request("bob", `/databases/${db.id}/schema`, "PUT", {
          version: 1,
          fields: schema.fields,
        })
      ).status,
      403,
    );
  },
);
only(
  "computed fields detect dependency cycles and evaluate without code execution",
  async () => {
    const db = await create("alice", { kind: "database" });
    const fields = [
      { id: "hours", name: "Hours", type: "number" },
      { id: "total", name: "Total", type: "formula", formula: "[hours]*12" },
      { id: "loop", name: "Loop", type: "formula", formula: "[loop]+1" },
    ];
    assert.equal(
      (
        await request("alice", `/databases/${db.id}/schema`, "PUT", {
          version: 1,
          fields,
        })
      ).status,
      200,
    );
    await request("alice", `/databases/${db.id}/records`, "POST", {
      title: "Work",
      values: { hours: 3 },
    });
    const record = (await request("alice", `/databases/${db.id}`)).data
      .records[0];
    assert.equal(record.computed.total, 36);
    assert.ok(record.computed.loop.error);
  },
);
only(
  "personal views are private, shared view edits require structure permission",
  async () => {
    const db = await create("alice", { kind: "database" });
    await invite(db, "editor");
    assert.equal(
      (
        await request("bob", `/databases/${db.id}/views`, "POST", {
          name: "Mine",
          type: "table",
          personal: true,
        })
      ).status,
      201,
    );
    assert.equal(
      (await request("alice", `/databases/${db.id}`)).data.views.length,
      3,
    );
    assert.equal(
      (await request("bob", `/databases/${db.id}`)).data.views.length,
      4,
    );
    assert.equal(
      (
        await request("bob", `/databases/${db.id}/views`, "POST", {
          name: "Everyone",
          type: "board",
        })
      ).status,
      403,
    );
  },
);
only(
  "legacy note conversion is idempotent and stays in the personal space",
  async () => {
    await home();
    const input = {
      note_id: "old-note",
      title: "Existing note",
      content: "# Notes",
      course_id: 12,
    };
    const a = await request("alice", "/legacy-notes", "POST", input),
      b = await request("alice", "/legacy-notes", "POST", input);
    assert.equal(a.status, 201);
    assert.equal(a.data.id, b.data.id);
    const page = (await request("alice", `/pages/${a.data.id}`)).data;
    assert.equal(page.initial_markdown, "# Notes");
    assert.equal(page.sources[0].type, "notebook");
    assert.equal((await request("bob", `/pages/${page.id}`)).status, 404);
  },
);
only("image and file reads recheck page rights after revocation", async () => {
  const page = await create();
  const bytes = Buffer.from(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489",
    "hex",
  );
  const file = await services.files.upload(
    users.alice,
    page.id,
    bytes,
    "tiny.png",
  );
  await invite(page);
  assert.equal(
    (await services.files.get(users.bob, file.id)).mime,
    "image/png",
  );
  await request("alice", "/grants", "PATCH", {
    page_id: page.id,
    member_id: users.bob.id,
    role: null,
  });
  await assert.rejects(
    services.files.get(users.bob, file.id),
    (error) => error.status === 404,
  );
  await assert.rejects(
    services.files.upload(
      users.alice,
      page.id,
      Buffer.from("<svg/>"),
      "bad.svg",
    ),
    (error) => error.status === 400,
  );
});
only("page covers require an image bound to that page and retain private access across duplicates", async () => {
  const page = await create(), other = await create();
  const bytes = Buffer.from("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489", "hex");
  const image = await services.files.upload(users.alice, page.id, bytes, "cover.png");
  assert.equal((await request("alice", `/pages/${other.id}`, "PATCH", { version: other.version, cover_image_id: image.id })).status, 400);
  const pdf = await services.files.upload(users.alice, page.id, Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"), "cover.pdf");
  assert.equal((await request("alice", `/pages/${page.id}`, "PATCH", { version: page.version, cover_image_id: pdf.id })).status, 400);
  const saved = await request("alice", `/pages/${page.id}`, "PATCH", { version: page.version, cover_image_id: image.id });
  assert.equal(saved.status, 200); assert.equal(saved.data.cover_image_id, image.id);
  assert.equal((await request("eve", `/pages/${page.id}`)).status, 404);
  await assert.rejects(services.files.get(users.eve, image.id), error => error.status === 404);
  const duplicate = await request("alice", `/pages/${page.id}/duplicate`, "POST", {});
  assert.equal(duplicate.status, 201);
  assert.equal((await request("alice", `/pages/${duplicate.data.id}`)).data.cover_image_id, image.id);
  const cleared = await request("alice", `/pages/${page.id}`, "PATCH", { version: saved.data.version, cover_image_id: null, cover: "green" });
  assert.equal(cleared.status, 200); assert.equal(cleared.data.cover_image_id, null);
  assert.equal((await request("alice", `/pages/${page.id}`, "PATCH", { version: page.version, cover_image_id: image.id })).status, 409);
});
only("foreign origins and unsafe links are rejected", async () => {
  const response = await fetch(base + "/bootstrap", {
    headers: { Authorization: "Bearer alice", Origin: "https://evil.test" },
  });
  assert.equal(response.status, 403);
  assert.equal(
    (
      await request(
        "alice",
        `/spaces/${(await home()).spaces[0].id}/pages`,
        "POST",
        {
          title: "Bad",
          sources: [{ type: "url", label: "Bad", url: "javascript:alert(1)" }],
        },
      )
    ).status,
    400,
  );
});
only(
  "websocket tickets are single use and only acknowledge committed edits",
  async () => {
    const page = await create(),
      ticket = await services.documents.ticket(users.alice, page.id);
    const socket = new WebSocket(
      base
        .replace("http:", "ws:")
        .replace("/api/v1/workspace", "/workspace-ws"),
      { origin: "http://workspace.test" },
    );
    const messages = [];
    socket.on("message", (bytes) =>
      messages.push(JSON.parse(bytes.toString())),
    );
    await new Promise((resolve, reject) => {
      socket.once("open", resolve);
      socket.once("error", reject);
    });
    socket.send(
      JSON.stringify({ type: "auth", ticket: ticket.ticket, client_id: 12345 }),
    );
    async function until(type) {
      for (let i = 0; i < 100; i++) {
        const result = messages.find((m) => m.type === type);
        if (result) return result;
        await new Promise((r) => setTimeout(r, 20));
      }
      throw Error(`Missing ${type}`);
    }
    await until("ready");
    await assert.rejects(
      services.documents.consumeTicket(ticket.ticket),
      (error) => error.status === 401,
    );
    const id = randomUUID();
    socket.send(
      JSON.stringify({
        type: "update",
        operation_id: id,
        generation: 1,
        update: change("Persisted"),
      }),
    );
    const ack = await until("ack");
    assert.equal(ack.operation_id, id);
    assert.equal(
      Number((await services.documents.read(users.alice, page.id)).revision),
      Number(ack.revision),
    );
    socket.close();
    await new Promise((resolve) => socket.once("close", resolve));
  },
);
test("JWT verification rejects refresh tokens and accepts signed BDC access identities", async () => {
  const secret = randomBytes(48),
    identity = jwtIdentity(secret.toString("hex")),
    key = new TextEncoder().encode(secret.toString("hex"));
  const access = await new SignJWT({
    user_id: 901,
    email: "alice@workspace.test",
    roles: ["ROLE_USER"],
  })
    .setProtectedHeader({ alg: "HS384" })
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(key);
  assert.equal(
    (await identity({ headers: { authorization: `Bearer ${access}` } })).id,
    "901",
  );
  const refresh = await new SignJWT({ user_id: 901 })
    .setProtectedHeader({ alg: "HS384" })
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(key);
  await assert.rejects(
    identity({ headers: { authorization: `Bearer ${refresh}` } }),
  );
});
only(
  "ten simultaneous document editors converge and persist every operation",
  async () => {
    const page = await create(),
      seed = new Y.Doc();
    const root = new Y.XmlElement("paragraph");
    root.insert(0, [new Y.XmlText()]);
    seed.getXmlFragment("document-store").insert(0, [root]);
    await services.documents.write(users.alice, page.id, {
      operation_id: randomUUID(),
      generation: 1,
      update: Buffer.from(Y.encodeStateAsUpdate(seed)).toString("base64"),
    });
    const clients = Array.from({ length: 10 }, (_, index) => {
      const doc = new Y.Doc();
      Y.applyUpdate(doc, Y.encodeStateAsUpdate(seed));
      const vector = Y.encodeStateVector(doc);
      doc
        .getXmlFragment("document-store")
        .get(0)
        .get(0)
        .insert(0, `[editor-${index}]`);
      return {
        doc,
        update: Buffer.from(Y.encodeStateAsUpdate(doc, vector)).toString(
          "base64",
        ),
      };
    });
    const results = await Promise.all(
      clients.map(({ update }) =>
        services.documents.write(users.alice, page.id, {
          operation_id: randomUUID(),
          generation: 1,
          update,
        }),
      ),
    );
    assert.equal(
      new Set(results.map((item) => Number(item.revision))).size,
      10,
    );
    const saved = await services.documents.read(users.alice, page.id),
      merged = new Y.Doc();
    Y.applyUpdate(merged, Buffer.from(saved.state, "base64"));
    const text = merged.getXmlFragment("document-store").toString();
    for (let index = 0; index < 10; index++)
      assert.ok(text.includes(`[editor-${index}]`));
    for (const { doc } of clients) {
      Y.applyUpdate(doc, Y.encodeStateAsUpdate(merged));
      assert.equal(doc.getXmlFragment("document-store").toString(), text);
      doc.destroy();
    }
    seed.destroy();
    merged.destroy();
  },
);
only(
  "page managers cannot archive undisclosed branches or manage unrelated pending invitations",
  async () => {
    const parent = await create(),
      child = await create("alice", { parent_id: parent.id });
    await invite(parent, "manager");
    const other = await create();
    await request("alice", "/invitations", "POST", {
      page_id: other.id,
      email: users.eve.email,
      role: "editor",
    });
    assert.equal(
      (await request("bob", `/pages/${parent.id}/archive`, "POST", {})).status,
      404,
    );
    assert.equal((await request("alice", `/pages/${child.id}`)).status, 200);
    assert.equal(
      (await request("bob", `/pages/${parent.id}/sharing`)).data.pending.length,
      0,
    );
  },
);
only("tickets cannot outlive the authenticated BDC session", async () => {
  const page = await create();
  const ticket = await services.documents.ticket(
    { ...users.alice, expiresAt: Date.now() - 1000 },
    page.id,
  );
  await assert.rejects(
    services.documents.consumeTicket(ticket.ticket),
    (error) => error.status === 401,
  );
});
only(
  "used status choices cannot be removed and private attachments cannot be rebound by guessing IDs",
  async () => {
    const database = await create("alice", { kind: "database" });
    await request("alice", `/databases/${database.id}/records`, "POST", {
      title: "Keep",
      values: { status: "todo" },
    });
    const schema = (await request("alice", `/databases/${database.id}`)).data;
    schema.fields[0].options = schema.fields[0].options.filter(
      (option) => option.id !== "todo",
    );
    assert.equal(
      (
        await request("alice", `/databases/${database.id}/schema`, "PUT", {
          version: schema.version,
          fields: schema.fields,
        })
      ).status,
      409,
    );
    const secret = await create(),
      destination = await create("bob");
    const bytes = Buffer.from(
      "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489",
      "hex",
    );
    const file = await services.files.upload(
      users.alice,
      secret.id,
      bytes,
      "private.png",
    );
    await assert.rejects(
      services.documents.write(users.bob, destination.id, {
        operation_id: randomUUID(),
        generation: 1,
        update: change(`/api/workspace/files/${file.id}`),
      }),
      (error) => error.status === 403,
    );
  },
);
only(
  "rollups never reveal records whose relation database the reader cannot access",
  async () => {
    const target = await create("alice", { kind: "database" }),
      db = await create("alice", { kind: "database" });
    await request("alice", `/databases/${target.id}/schema`, "PUT", {
      version: 1,
      fields: [{ id: "amount", name: "Amount", type: "number" }],
    });
    const row = (
      await request("alice", `/databases/${target.id}/records`, "POST", {
        title: "Private",
        values: { amount: 4321 },
      })
    ).data;
    await request("alice", `/databases/${db.id}/schema`, "PUT", {
      version: 1,
      fields: [
        {
          id: "related",
          name: "Related",
          type: "relation",
          relation_page_id: target.id,
        },
        {
          id: "sum",
          name: "Sum",
          type: "rollup",
          relation_field_id: "related",
          target_field_id: "amount",
          aggregate: "sum",
        },
      ],
    });
    await request("alice", `/databases/${db.id}/records`, "POST", {
      title: "Public",
      values: { related: [row.id] },
    });
    await invite(db, "viewer");
    const visible = (await request("bob", `/databases/${db.id}`)).data
      .records[0];
    assert.ok(visible.computed.sum.error);
    assert.equal(JSON.stringify(visible).includes("4321"), false);
  },
);
only(
  "backlinks retain page-reference attributes while filtering private referring pages",
  async () => {
    const target = await create(),
      source = await create(),
      doc = new Y.Doc(),
      node = new Y.XmlElement("pageLink");
    node.setAttribute("pageId", target.id);
    doc.getXmlFragment("document-store").insert(0, [node]);
    await services.documents.write(users.alice, source.id, {
      operation_id: randomUUID(),
      generation: 1,
      update: Buffer.from(Y.encodeStateAsUpdate(doc)).toString("base64"),
    });
    doc.destroy();
    assert.deepEqual(
      (
        await request("alice", `/pages/${target.id}/references`)
      ).data.backlinks.map((item) => item.id),
      [source.id],
    );
    await invite(target);
    assert.deepEqual(
      (await request("bob", `/pages/${target.id}/references`)).data.backlinks,
      [],
    );
  },
);
only(
  "duplicating an unopened Markdown page preserves its initial content",
  async () => {
    const page = await create("alice", { markdown: "# Keep this content" }),
      copy = (await request("alice", `/pages/${page.id}/duplicate`, "POST", {}))
        .data;
    const saved = (await request("alice", `/pages/${copy.id}`)).data;
    assert.equal(saved.initial_markdown, "# Keep this content");
    assert.equal(Number(saved.revision), 0);
  },
);
only("schema removal cannot hide used properties", async () => {
  const db = await create("alice", { kind: "database" });
  await request("alice", `/databases/${db.id}/records`, "POST", {
    title: "Keep status",
    values: { status: "todo" },
  });
  const schema = (await request("alice", `/databases/${db.id}`)).data;
  assert.equal(
    (
      await request("alice", `/databases/${db.id}/schema`, "PUT", {
        version: schema.version,
        fields: schema.fields.filter((field) => field.id !== "status"),
      })
    ).status,
    409,
  );
});
only(
  "record restore rejects properties invalidated by a newer schema without changing the document generation",
  async () => {
    const db = await create("alice", { kind: "database" }),
      record = (
        await request("alice", `/databases/${db.id}/records`, "POST", {
          title: "Track",
          values: { status: "todo" },
        })
      ).data;
    const version = (
      await request("alice", `/pages/${record.id}/versions`, "POST", {
        label: "Old status",
      })
    ).data;
    await request("alice", `/records/${record.id}`, "PATCH", {
      version: record.version,
      values: { status: "done" },
    });
    const schema = (await request("alice", `/databases/${db.id}`)).data;
    schema.fields[0].options = schema.fields[0].options.filter(
      (option) => option.id !== "todo",
    );
    assert.equal(
      (
        await request("alice", `/databases/${db.id}/schema`, "PUT", {
          version: schema.version,
          fields: schema.fields,
        })
      ).status,
      200,
    );
    assert.equal(
      (
        await request(
          "alice",
          `/pages/${record.id}/versions/${version.id}/restore`,
          "POST",
          {},
        )
      ).status,
      409,
    );
    const saved = (await request("alice", `/pages/${record.id}`)).data;
    assert.equal(saved.properties.status, "done");
    assert.equal(saved.generation, 1);
  },
);

async function createField(
  spaceId,
  title = "Hệ thống phân tán",
  actor = "alice",
) {
  const result = await request(actor, `/spaces/${spaceId}/fields`, "POST", {
    title,
    icon: "code",
    color: "green",
    description: "Ghi chép nghiên cứu",
    tags: ["Systems"],
  });
  assert.equal(result.status, 201);
  return result.data;
}
only(
  "fields are user-created, private and independently scoped, with optimistic metadata updates",
  async () => {
    const initial = await home(),
      spaceId = initial.spaces[0].id;
    assert.deepEqual(initial.fields, []);
    assert.deepEqual(
      (await request("alice", `/spaces/${spaceId}/pages`)).data,
      [],
    );
    const f = await createField(spaceId);
    assert.equal(f.page_count, 1);
    const root = (await request("alice", `/pages/${f.page_id}`)).data;
    assert.equal(root.field_id, f.id);
    assert.equal(root.title, f.title);
    assert.equal(root.cover, "green");
    assert.equal((await request("bob", `/fields/${f.id}`)).status, 404);
    assert.equal(
      (
        await request("alice", `/fields/${f.id}`, "PATCH", {
          version: f.version,
          title: "Lĩnh vực đổi tên",
        })
      ).status,
      200,
    );
    assert.equal(
      (
        await request("alice", `/fields/${f.id}`, "PATCH", {
          version: f.version,
          title: "Ghi đè cũ",
        })
      ).status,
      409,
    );
    assert.equal((await home("bob")).fields.length, 0);
    await invite(root);
    assert.equal((await request("bob", `/pages/${root.id}`)).status, 200);
    assert.equal(
      (await request("bob", `/spaces/${spaceId}/fields`)).status,
      404,
    );
    assert.equal((await home("bob")).fields.length, 0);
  },
);
only(
  "page branches inherit fields and move atomically, including archived children and database records",
  async () => {
    const spaceId = (await home()).spaces[0].id,
      f = await createField(spaceId),
      g = await createField(spaceId, "Đồ thị");
    const createAt = async (input) =>
      (await request("alice", `/spaces/${spaceId}/pages`, "POST", input)).data;
    const child = await createAt({ title: "Con", parent_id: f.page_id }),
      nested = await createAt({ title: "Cháu", parent_id: child.id });
    assert.equal(child.field_id, f.id);
    assert.equal(nested.field_id, f.id);
    assert.equal(
      (
        await request("alice", `/spaces/${spaceId}/pages`, "POST", {
          title: "Sai nhánh",
          parent_id: child.id,
          field_id: g.id,
        })
      ).status,
      400,
    );
    const collection = await createAt({
      title: "Kế hoạch",
      parent_id: child.id,
      kind: "database",
    });
    const record = (
      await request("alice", `/databases/${collection.id}/records`, "POST", {
        title: "Việc cần làm",
        values: {},
      })
    ).data;
    assert.ok(record.id);
    const archived = await createAt({ title: "Đã cất", parent_id: child.id });
    await request("alice", `/pages/${archived.id}/archive`, "POST", {});
    assert.equal(
      (
        await request("alice", `/pages/${child.id}`, "PATCH", {
          version: child.version,
          field_id: g.id,
          parent_id: g.page_id,
        })
      ).status,
      200,
    );
    const branch = (
      await pool.query("SELECT field_id FROM pages WHERE id=ANY($1::uuid[])", [
        [child.id, nested.id, collection.id, record.id, archived.id],
      ])
    ).rows;
    assert.equal(branch.length, 5);
    assert.ok(branch.every((p) => p.field_id === g.id));
    const current = (await request("alice", `/pages/${child.id}`)).data;
    assert.equal(
      (
        await request("alice", `/pages/${child.id}`, "PATCH", {
          version: current.version,
          parent_id: nested.id,
        })
      ).status,
      400,
    );
    assert.equal(
      (
        await request("alice", `/pages/${child.id}`, "PATCH", {
          version: current.version,
          field_id: f.id,
        })
      ).status,
      400,
    );
    assert.equal(
      (await request("alice", `/pages/${archived.id}/restore`, "POST", {}))
        .status,
      200,
    );
  },
);
only(
  "field archive restores its batch only, retains legacy pages and rejects cross-space field assignment",
  async () => {
    const spaceId = (await home()).spaces[0].id,
      f = await createField(spaceId);
    const old = await create();
    assert.equal(old.field_id, null);
    const trashed = (
      await request("alice", `/spaces/${spaceId}/pages`, "POST", {
        title: "Đã xóa trước",
        field_id: f.id,
      })
    ).data;
    await request("alice", `/pages/${trashed.id}/archive`, "POST", {});
    assert.equal(
      (await request("alice", `/fields/${f.id}/archive`, "POST", {})).status,
      200,
    );
    assert.equal((await request("alice", `/pages/${f.page_id}`)).status, 404);
    assert.equal(
      (await request("alice", `/pages/${trashed.id}/restore`, "POST", {}))
        .status,
      404,
    );
    assert.equal((await home()).fields.length, 0);
    assert.equal((await request("alice", `/pages/${old.id}`)).status, 200);
    assert.equal(
      (await request("alice", `/fields/${f.id}/restore`, "POST", {})).status,
      200,
    );
    assert.equal((await request("alice", `/pages/${f.page_id}`)).status, 200);
    assert.equal((await request("alice", `/pages/${trashed.id}`)).status, 404);
    const other = (await home("bob")).spaces[0].id;
    assert.equal(
      (
        await request("bob", `/spaces/${other}/pages`, "POST", {
          title: "Foreign",
          field_id: f.id,
        })
      ).status,
      404,
    );
  },
);
only(
  "block activity records the committed author of changed blocks and rechecks page visibility",
  async () => {
    const page = await create(),
      doc = new Y.Doc(),
      block = new Y.XmlElement("blockContainer"),
      text = new Y.XmlText();
    block.setAttribute("id", "test-block");
    text.insert(0, "Nội dung");
    block.insert(0, [text]);
    doc.getXmlFragment("document-store").insert(0, [block]);
    await services.documents.write(users.alice, page.id, {
      operation_id: randomUUID(),
      generation: 1,
      update: Buffer.from(Y.encodeStateAsUpdate(doc)).toString("base64"),
    });
    const activity = await request(
      "alice",
      `/pages/${page.id}/blocks/test-block/activity`,
    );
    assert.equal(activity.status, 200);
    assert.equal(activity.data.author, "Alice");
    assert.equal(
      (await request("bob", `/pages/${page.id}/blocks/test-block/activity`))
        .status,
      404,
    );
    assert.equal(
      (await request("alice", `/pages/${page.id}/blocks/unknown/activity`))
        .data,
      null,
    );
    doc.destroy();
  },
);

only(
  "page analytics count explicit opens only and serialize repeated foreground visits",
  async () => {
    const page = await create();
    assert.equal(
      (await request("alice", `/pages/${page.id}/analytics`)).data.views,
      0,
    );
    for (let i = 0; i < 3; i++) await request("alice", `/pages/${page.id}`);
    assert.equal(
      (await request("alice", `/pages/${page.id}/analytics`)).data.views,
      0,
    );
    const visits = await Promise.all(
      Array.from({ length: 10 }, () =>
        request("alice", `/pages/${page.id}/view`, "POST", {}),
      ),
    );
    assert.equal(visits.filter((item) => item.data.counted).length, 1);
    let summary = (
      await request("alice", `/pages/${page.id}/analytics?days=28`)
    ).data;
    assert.equal(summary.views, 1);
    assert.equal(summary.unique_viewers, 1);
    assert.equal(summary.daily.length, 28);
    assert.equal(
      summary.daily.reduce((n, day) => n + day.views, 0),
      1,
    );
    assert.deepEqual(
      summary.viewers.map((item) => item.name),
      ["Alice"],
    );
    await pool.query(
      "UPDATE page_visits SET viewed_at=now()-interval '6 minutes' WHERE page_id=$1",
      [page.id],
    );
    assert.equal(
      (await request("alice", `/pages/${page.id}/view`, "POST", {})).data
        .counted,
      true,
    );
    summary = (await request("alice", `/pages/${page.id}/analytics?days=7`))
      .data;
    assert.equal(summary.views, 2);
    assert.equal(summary.daily.length, 7);
    assert.equal(
      (await request("alice", `/pages/${page.id}/analytics?days=1000`)).status,
      400,
    );
    const metadata = (await request("alice", `/pages/${page.id}`)).data;
    assert.equal(metadata.creator_name, "Alice");
    assert.equal(metadata.last_editor, "Alice");
  },
);
only(
  "viewer names are always visible to authorized page readers and denied after revocation",
  async () => {
    const page = await create();
    await invite(page, "viewer");
    await request("alice", "/pages/" + page.id + "/view", "POST", {});
    await request("bob", "/pages/" + page.id + "/view", "POST", {});
    // Obsolete hidden-name choices no longer affect the requested named history.
    await pool.query(
      "INSERT INTO page_view_preferences(page_id,user_id,show_name) VALUES($1,$2,false)",
      [page.id, users.bob.id],
    );
    const summary = (await request("bob", "/pages/" + page.id + "/analytics"))
      .data;
    assert.equal(summary.views, 2);
    assert.equal(summary.unique_viewers, 2);
    assert.deepEqual(summary.viewers.map((x) => x.name).sort(), [
      "Alice",
      "Bob",
    ]);
    assert.ok(summary.viewers.every((x) => !("user_id" in x)));
    assert.ok(!("show_name" in summary));
    assert.equal(
      (await request("eve", "/pages/" + page.id + "/analytics")).status,
      404,
    );
    assert.equal(
      (await request("eve", "/pages/" + page.id + "/view", "POST", {})).status,
      404,
    );
    await pool.query(
      "DELETE FROM page_grants WHERE page_id=$1 AND user_id=$2",
      [page.id, users.bob.id],
    );
    assert.equal(
      (await request("bob", "/pages/" + page.id + "/analytics")).status,
      404,
    );
    assert.equal(
      (
        await fetch(base + "/pages/" + page.id + "/view-preference", {
          method: "PATCH",
          headers: {
            Authorization: "Bearer alice",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ show_name: false }),
        })
      ).status,
      404,
    );
  },
);
only(
  "tab picker searches accessible pages across fields without revealing private children or recording views",
  async () => {
    const initial = await home(),
      space = initial.spaces[0].id,
      f = await createField(space, "Lĩnh vực A"),
      g = await createField(space, "Lĩnh vực B");
    const child = (
      await request("alice", `/spaces/${space}/pages`, "POST", {
        title: "Private child",
        parent_id: f.page_id,
      })
    ).data;
    const root = (await request("alice", `/pages/${f.page_id}`)).data;
    await invite(root);
    const all = (await request("alice", "/tab-pages")).data;
    assert.ok(all.some((page) => page.id === f.page_id));
    assert.ok(all.some((page) => page.id === g.page_id));
    assert.ok(
      (await request("alice", `/tab-pages?field=${g.id}`)).data.every(
        (page) => page.field_id === g.id,
      ),
    );
    const shared = (await request("bob", "/tab-pages")).data;
    assert.ok(shared.some((page) => page.id === root.id));
    assert.ok(!shared.some((page) => page.id === child.id));
    assert.equal(
      (await request("bob", `/tab-pages?field=${f.id}`)).status,
      404,
    );
    assert.equal(
      (await request("alice", `/pages/${root.id}/analytics`)).data.views,
      0,
    );
    await request("alice", `/fields/${f.id}/archive`, "POST", {});
    assert.ok(
      !(await request("alice", "/tab-pages")).data.some(
        (page) => page.id === child.id,
      ),
    );
  },
);

only(
  "permanent page deletion requires trash and space authority, removes a whole branch and preserves shared attachments",
  async () => {
    const root = await create(),
      child = await create("alice", { parent_id: root.id }),
      grand = await create("alice", { parent_id: child.id }),
      other = await create();
    assert.equal(
      (await request("alice", "/pages/" + root.id, "DELETE")).status,
      409,
    );
    await invite(root, "manager");
    const bytes = Buffer.from(
      "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489",
      "hex",
    );
    const shared = await services.files.upload(
        users.alice,
        child.id,
        bytes,
        "shared.png",
      ),
      exclusive = await services.files.upload(
        users.alice,
        grand.id,
        bytes,
        "exclusive.png",
      );
    await pool.query(
      "INSERT INTO attachment_bindings(attachment_id,page_id) VALUES($1,$2)",
      [shared.id, other.id],
    );
    await services.pages.createVersion(users.alice, child.id, "Snapshot");
    await pool.query(
      "INSERT INTO comments(id,page_id,author_id,body) VALUES($1,$2,$3,'Comment')",
      [randomUUID(), child.id, users.alice.id],
    );
    await request("alice", "/pages/" + child.id + "/view", "POST", {});
    await services.documents.ticket(users.alice, child.id);
    await request("alice", "/pages/" + grand.id + "/archive", "POST", {});
    await request("alice", "/pages/" + root.id + "/archive", "POST", {});
    assert.equal(
      (await request("eve", "/pages/" + root.id, "DELETE")).status,
      404,
    );
    assert.equal(
      (await request("bob", "/pages/" + root.id, "DELETE")).status,
      404,
    );
    assert.equal(
      (await request("alice", "/pages/" + root.id, "DELETE")).status,
      200,
    );
    for (const page of [root, child, grand])
      assert.equal(
        (await request("alice", "/pages/" + page.id + "/restore", "POST", {}))
          .status,
        404,
      );
    for (const table of [
      "pages",
      "page_documents",
      "page_versions",
      "comments",
      "page_visits",
      "websocket_tickets",
    ]) {
      const key = table === "pages" ? "id" : "page_id";
      assert.equal(
        (
          await pool.query(
            "SELECT count(*)::int n FROM " +
              table +
              " WHERE " +
              key +
              "=ANY($1::uuid[])",
            [[root.id, child.id, grand.id]],
          )
        ).rows[0].n,
        0,
      );
    }
    assert.equal((await request("alice", "/pages/" + other.id)).status, 200);
    assert.equal(
      (
        await pool.query(
          "SELECT count(*)::int n FROM attachments WHERE id=$1",
          [shared.id],
        )
      ).rows[0].n,
      1,
    );
    assert.equal(
      (
        await pool.query(
          "SELECT count(*)::int n FROM attachments WHERE id=$1",
          [exclusive.id],
        )
      ).rows[0].n,
      0,
    );
  },
);
only(
  "permanent field deletion includes previously trashed pages and database records, while active and foreign fields stay protected",
  async () => {
    const space = (await home()).spaces[0].id,
      field = await createField(space),
      other = await createField(space, "Keep");
    const earlier = await create("alice", { field_id: field.id });
    await request("alice", "/pages/" + earlier.id + "/archive", "POST", {});
    const database = await create("alice", {
      field_id: field.id,
      kind: "database",
    });
    const record = (
      await request("alice", "/databases/" + database.id + "/records", "POST", {
        title: "Record",
        values: {},
      })
    ).data;
    assert.equal(
      (await request("alice", "/fields/" + field.id, "DELETE")).status,
      409,
    );
    await request("alice", "/fields/" + field.id + "/archive", "POST", {});
    assert.equal(
      (await request("bob", "/fields/" + field.id, "DELETE")).status,
      404,
    );
    assert.equal(
      (await request("alice", "/fields/" + field.id, "DELETE")).status,
      200,
    );
    assert.equal(
      (await request("alice", "/fields/" + field.id + "/restore", "POST", {}))
        .status,
      404,
    );
    for (const id of [field.page_id, earlier.id, database.id, record.id])
      assert.equal(
        (await request("alice", "/pages/" + id + "/restore", "POST", {}))
          .status,
        404,
      );
    assert.equal(
      (
        await pool.query(
          "SELECT count(*)::int n FROM pages WHERE field_id=$1",
          [field.id],
        )
      ).rows[0].n,
      0,
    );
    assert.equal(
      (await request("alice", "/pages/" + other.page_id)).status,
      200,
    );
  },
);
