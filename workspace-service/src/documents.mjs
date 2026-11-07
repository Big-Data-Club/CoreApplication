import { createHash, randomBytes, randomUUID } from "node:crypto";
import * as Y from "yjs";
import { assert } from "./errors.mjs";
import { indexPageLinks } from "./links.mjs";
import { blockSignatures, recordBlockActivity } from "./blockActivity.mjs";
export const decode = (value) => Buffer.from(value, "base64");
export const encode = (value) => Buffer.from(value).toString("base64");
export class Documents {
  constructor(store, pages) {
    this.store = store;
    this.pages = pages;
  }
  async read(user, id) {
    await this.store.page(this.store.pool, id, user);
    const { rows } = await this.store.pool.query(
      "SELECT state,revision,generation FROM page_documents WHERE page_id=$1",
      [id],
    );
    return { ...rows[0], state: encode(rows[0].state) };
  }
  async ticket(user, id) {
    await this.store.page(this.store.pool, id, user);
    const ticket = randomBytes(32).toString("base64url");
    await this.store.pool.query(
      "DELETE FROM websocket_tickets WHERE expires_at<now()",
    );
    await this.store.pool.query(
      "INSERT INTO websocket_tickets(digest,page_id,user_id,expires_at,identity_expires_at) VALUES($1,$2,$3,now()+interval '60 seconds',$4)",
      [
        createHash("sha256").update(ticket).digest("hex"),
        id,
        user.id,
        new Date(user.expiresAt || Date.now() + 3600000),
      ],
    );
    return { ticket };
  }
  async consumeTicket(ticket) {
    assert(
      typeof ticket === "string" && ticket.length < 100,
      401,
      "Phiên kết nối không hợp lệ.",
    );
    const { rows } = await this.store.pool.query(
      "DELETE FROM websocket_tickets WHERE digest=$1 AND expires_at>now() AND identity_expires_at>now() RETURNING page_id,user_id,identity_expires_at",
      [createHash("sha256").update(ticket).digest("hex")],
    );
    assert(rows[0], 401, "Phiên kết nối đã hết hạn.");
    const profile = await this.store.pool.query(
      "SELECT id,email,name FROM workspace_users WHERE id=$1",
      [rows[0].user_id],
    );
    return {
      pageId: rows[0].page_id,
      user: {
        ...profile.rows[0],
        expiresAt: new Date(rows[0].identity_expires_at).getTime(),
      },
    };
  }
  async write(
    user,
    id,
    { operation_id, generation, update, initialize = false },
  ) {
    assert(
      typeof update === "string" &&
        update.length > 0 &&
        update.length < 6000000,
      413,
      "Thay đổi quá lớn.",
    );
    const bytes = decode(update);
    assert(
      bytes.length > 0 && bytes.length <= 4194304,
      413,
      "Thay đổi quá lớn.",
    );
    return this.store.tx(async (client) => {
      const saved = (
        await client.query(
          "SELECT * FROM page_documents WHERE page_id=$1 FOR UPDATE",
          [id],
        )
      ).rows[0];
      const page = await this.store.page(client, id, user, 3);
      assert(
        saved.generation === generation,
        409,
        "Trang đã được khôi phục phiên bản. Giữ bản nháp và tải lại.",
        "generation_changed",
      );
      const existing = (
        await client.query(
          "SELECT revision FROM document_operations WHERE page_id=$1 AND operation_id=$2",
          [id, operation_id],
        )
      ).rows[0];
      if (existing)
        return { revision: existing.revision, generation, operation_id };
      if (initialize)
        assert(
          Number(saved.revision) === 0,
          409,
          "Trang đã được khởi tạo.",
          "already_initialized",
        );
      const doc = new Y.Doc();
      try {
        if (saved.state.length) Y.applyUpdate(doc, saved.state);
        const beforeBlocks = blockSignatures(
          doc.getXmlFragment("document-store"),
        );
        try {
          Y.applyUpdate(doc, bytes);
        } catch {
          assert(false, 400, "Thay đổi tài liệu không hợp lệ.");
        }
        assert(
          [...doc.share.keys()].every((key) => key === "document-store"),
          400,
          "Cấu trúc tài liệu không hợp lệ.",
        );
        const state = Y.encodeStateAsUpdate(doc);
        assert(
          state.length <= 4194304,
          413,
          "Trang vượt giới hạn 4 MB. Hãy chia thành trang con.",
        );
        const xml = doc.getXmlFragment("document-store").toString();
        await recordBlockActivity(
          client,
          id,
          user,
          beforeBlocks,
          blockSignatures(doc.getXmlFragment("document-store")),
        );
        await indexPageLinks(client, id, xml);
        const fileIds = [
          ...new Set(
            [
              ...xml.matchAll(
                /\/api\/workspace\/files\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/g,
              ),
            ].map((match) => match[1]),
          ),
        ];
        for (const fileId of fileIds) {
          const bound = await client.query(
            "SELECT 1 FROM attachment_bindings WHERE attachment_id=$1 AND page_id=$2",
            [fileId, id],
          );
          if (!bound.rowCount) {
            const sources = await client.query(
              "SELECT page_id FROM attachment_bindings WHERE attachment_id=$1",
              [fileId],
            );
            let allowed = false;
            for (const source of sources.rows) {
              try {
                await this.store.page(client, source.page_id, user);
                allowed = true;
                break;
              } catch {}
            }
            assert(
              allowed,
              403,
              "Bạn không có quyền dùng tệp nguồn trong trang này.",
            );
            await client.query(
              "INSERT INTO attachment_bindings(attachment_id,page_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
              [fileId, id],
            );
          }
        }
        if (Number(saved.revision) > 0) {
          const latest = (
            await client.query(
              "SELECT created_at FROM page_versions WHERE page_id=$1 ORDER BY created_at DESC LIMIT 1",
              [id],
            )
          ).rows[0];
          if (
            !latest ||
            Date.now() - new Date(latest.created_at).getTime() > 600000
          )
            await this.pages.snapshot(client, user, page, "Tự động");
        }
        const revision = Number(saved.revision) + 1;
        await client.query(
          "UPDATE page_documents SET state=$2,revision=$3,search_text=$4,updated_at=now() WHERE page_id=$1",
          [
            id,
            Buffer.from(state),
            revision,
            xml.replace(/<[^>]*>/g, " ").slice(0, 200000),
          ],
        );
        await client.query(
          "UPDATE pages SET updated_at=now(),updated_by=$2 WHERE id=$1",
          [id, user.id],
        );
        await client.query(
          "INSERT INTO document_operations(page_id,operation_id,generation,revision,author_id) VALUES($1,$2,$3,$4,$5)",
          [id, operation_id, generation, revision, user.id],
        );
        await client.query("SELECT pg_notify('workspace_changes',$1)", [
          JSON.stringify({
            space_id: page.space_id,
            page_id: id,
            action: "document.updated",
          }),
        ]);
        return { revision, generation, operation_id };
      } finally {
        doc.destroy();
      }
    });
  }
}
