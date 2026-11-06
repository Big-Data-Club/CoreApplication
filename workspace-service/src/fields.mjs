import { randomUUID } from "node:crypto";
import { assert } from "./errors.mjs";
export class Fields {
  constructor(store) {
    this.store = store;
  }
  async list(user, spaceId, archived = false) {
    await this.store.space(this.store.pool, spaceId, user);
    return (
      await this.store.pool.query(
        `SELECT f.*,count(p.id)::int page_count,GREATEST(f.updated_at,COALESCE(max(p.updated_at),f.updated_at)) last_activity FROM workspace_fields f LEFT JOIN pages p ON p.field_id=f.id AND p.archived_at IS NULL WHERE f.space_id=$1 AND (f.archived_at IS NOT NULL)=$2 GROUP BY f.id ORDER BY f.created_at`,
        [spaceId, archived],
      )
    ).rows;
  }
  async create(user, spaceId, input) {
    return this.store.tx(async (client) => {
      await this.store.space(client, spaceId, user, 3);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        spaceId,
      ]);
      const count = (
        await client.query(
          "SELECT count(*)::int n FROM workspace_fields WHERE space_id=$1 AND archived_at IS NULL",
          [spaceId],
        )
      ).rows[0].n;
      assert(
        count < 100,
        409,
        "Mỗi không gian hỗ trợ tối đa 100 lĩnh vực đang hoạt động.",
      );
      const id = randomUUID();
      const field = (
        await client.query(
          "INSERT INTO workspace_fields(id,space_id,title,description,icon,color,tags,created_by,updated_by) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8) RETURNING *",
          [
            id,
            spaceId,
            input.title,
            input.description,
            input.icon,
            input.color,
            JSON.stringify(input.tags),
            user.id,
          ],
        )
      ).rows[0];
      const page = await this.store.insertPage(client, user, spaceId, {
        title: input.title,
        field_id: id,
      });
      await client.query("UPDATE pages SET cover=$2 WHERE id=$1", [
        page.id,
        input.color,
      ]);
      await this.store.event(client, user, spaceId, null, "field.created");
      return { ...field, page_id: page.id, page_count: 1 };
    });
  }
  async patch(user, id, input) {
    return this.store.tx(async (client) => {
      await client.query(
        "SELECT id FROM workspace_fields WHERE id=$1 FOR UPDATE",
        [id],
      );
      const field = await this.store.field(client, id, user, 3);
      assert(
        field.version === input.version,
        409,
        "Lĩnh vực vừa thay đổi. Mở lại trước khi lưu.",
        "version_conflict",
      );
      const keys = ["title", "description", "icon", "color", "tags"].filter(
        (key) => key in input,
      );
      if (!keys.length) return field;
      const saved = (
        await client.query(
          `UPDATE workspace_fields SET ${keys.map((key, index) => `${key}=$${index + 2}`).join(",")},version=version+1,updated_at=now(),updated_by=$${keys.length + 2} WHERE id=$1 RETURNING *`,
          [
            id,
            ...keys.map((key) =>
              key === "tags" ? JSON.stringify(input[key]) : input[key],
            ),
            user.id,
          ],
        )
      ).rows[0];
      await this.store.event(
        client,
        user,
        field.space_id,
        null,
        "field.updated",
      );
      return saved;
    });
  }
  async archive(user, id) {
    return this.store.tx(async (client) => {
      const initial = await this.store.field(client, id, user, 4);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        initial.space_id,
      ]);
      const field = await this.store.field(client, id, user, 4),
        batch = randomUUID();
      await client.query(
        "UPDATE workspace_fields SET archived_at=now(),archived_batch=$2,version=version+1,updated_by=$3 WHERE id=$1",
        [id, batch, user.id],
      );
      await client.query(
        "UPDATE pages SET archived_at=now(),archived_batch=$2,version=version+1,updated_by=$3 WHERE field_id=$1 AND archived_at IS NULL",
        [id, batch, user.id],
      );
      await this.store.event(
        client,
        user,
        field.space_id,
        null,
        "field.archived",
      );
      return { id };
    });
  }
  async restore(user, id) {
    return this.store.tx(async (client) => {
      const initial = await this.store.field(client, id, user, 4, true);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        initial.space_id,
      ]);
      const field = await this.store.field(client, id, user, 4, true);
      assert(field.archived_batch, 409, "Lĩnh vực đang hoạt động.");
      const count = (
        await client.query(
          "SELECT count(*)::int n FROM workspace_fields WHERE space_id=$1 AND archived_at IS NULL",
          [field.space_id],
        )
      ).rows[0].n;
      assert(
        count < 100,
        409,
        "Chuyển bớt lĩnh vực vào thùng rác trước khi khôi phục (tối đa 100 lĩnh vực hoạt động).",
      );
      await client.query(
        "UPDATE pages SET archived_at=NULL,archived_batch=NULL,version=version+1,updated_by=$2 WHERE archived_batch=$1",
        [field.archived_batch, user.id],
      );
      await client.query(
        "UPDATE workspace_fields SET archived_at=NULL,archived_batch=NULL,version=version+1,updated_by=$2 WHERE id=$1",
        [id, user.id],
      );
      await this.store.event(
        client,
        user,
        field.space_id,
        null,
        "field.restored",
      );
      return { id };
    });
  }
}
