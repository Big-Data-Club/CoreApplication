import { assert } from "./errors.mjs";

// Explicitly remove Workspace-owned dependents; shared files survive while bound
// to another page. A future unhandled FK causes a rollback, never partial deletion.
export class Trash {
  constructor(store) {
    this.store = store;
  }
  async removePages(client, ids) {
    if (!ids.length) return;
    const files = (
      await client.query(
        "SELECT DISTINCT attachment_id id FROM attachment_bindings WHERE page_id=ANY($1::uuid[])",
        [ids],
      )
    ).rows.map((row) => row.id);
    for (const table of [
      "comments",
      "page_versions",
      "database_views",
      "database_schemas",
      "attachment_bindings",
      "workspace_activity",
      "workspace_notifications",
      "websocket_tickets",
      "legacy_note_imports",
    ])
      await client.query(`DELETE FROM ${table} WHERE page_id=ANY($1::uuid[])`, [
        ids,
      ]);
    await client.query("DELETE FROM pages WHERE id=ANY($1::uuid[])", [ids]);
    if (files.length)
      await client.query(
        "DELETE FROM attachments a WHERE a.id=ANY($1::uuid[]) AND NOT EXISTS(SELECT 1 FROM attachment_bindings b WHERE b.attachment_id=a.id)",
        [files],
      );
  }
  async page(user, id) {
    return this.store.tx(async (client) => {
      const initial = await this.store.page(client, id, user, 4, true);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        initial.space_id,
      ]);
      await this.store.space(client, initial.space_id, user, 4);
      const page = await this.store.page(client, id, user, 4, true);
      assert(
        page.archived_at,
        409,
        "Chuyển trang vào thùng rác trước khi xóa vĩnh viễn.",
      );
      const rows = (
        await client.query(
          "WITH RECURSIVE branch AS(SELECT id FROM pages WHERE id=$1 UNION ALL SELECT p.id FROM pages p JOIN branch b ON p.parent_id=b.id) SELECT p.id,p.archived_at FROM pages p JOIN branch b USING(id) FOR UPDATE OF p",
          [id],
        )
      ).rows;
      assert(
        rows.every((row) => row.archived_at),
        409,
        "Nhánh vẫn có trang đang hoạt động.",
      );
      await this.removePages(
        client,
        rows.map((row) => row.id),
      );
      await this.store.event(
        client,
        user,
        page.space_id,
        null,
        "page.deleted",
        { count: rows.length },
      );
      return { id };
    });
  }
  async field(user, id) {
    return this.store.tx(async (client) => {
      const initial = await this.store.field(client, id, user, 4, true);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        initial.space_id,
      ]);
      const field = await this.store.field(client, id, user, 4, true);
      assert(
        field.archived_at,
        409,
        "Chuyển lĩnh vực vào thùng rác trước khi xóa vĩnh viễn.",
      );
      const rows = (
        await client.query(
          "SELECT id,archived_at FROM pages WHERE field_id=$1 FOR UPDATE",
          [id],
        )
      ).rows;
      assert(
        rows.every((row) => row.archived_at),
        409,
        "Lĩnh vực vẫn có trang đang hoạt động.",
      );
      await this.removePages(
        client,
        rows.map((row) => row.id),
      );
      await client.query("DELETE FROM workspace_fields WHERE id=$1", [id]);
      await this.store.event(
        client,
        user,
        field.space_id,
        null,
        "field.deleted",
        { count: rows.length },
      );
      return { id };
    });
  }
}
