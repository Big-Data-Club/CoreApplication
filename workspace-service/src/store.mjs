import { randomUUID } from "node:crypto";
import { transaction } from "./db.mjs";
import { assert } from "./errors.mjs";
export const ranks = {
  viewer: 1,
  commenter: 2,
  editor: 3,
  manager: 4,
  owner: 5,
};
export const roleSql = (alias) =>
  `CASE ${alias}.role WHEN 'owner' THEN 5 WHEN 'manager' THEN 4 WHEN 'editor' THEN 3 WHEN 'commenter' THEN 2 WHEN 'viewer' THEN 1 ELSE 0 END`;
export class Store {
  constructor(pool) {
    this.pool = pool;
  }
  tx(fn) {
    return transaction(this.pool, fn);
  }
  async register(user) {
    await this.pool.query(
      `INSERT INTO workspace_users(id,email,name) VALUES($1,$2,$3) ON CONFLICT(id) DO UPDATE SET email=EXCLUDED.email,updated_at=now()`,
      [user.id, user.email, user.name],
    );
  }
  async space(client, id, user, min = 1) {
    const { rows } = await client.query(
      `SELECT s.*,${roleSql("m")} access FROM spaces s JOIN space_members m ON m.space_id=s.id AND m.user_id=$2 WHERE s.id=$1`,
      [id, user.id],
    );
    const result = rows[0];
    assert(result, 404, "Không tìm thấy không gian.");
    assert(
      result.access >= min,
      403,
      "Bạn chưa có quyền thực hiện thao tác này.",
    );
    return result;
  }
  async page(client, id, user, min = 1, archived = false) {
    const { rows } = await client.query(
      `SELECT p.*,m.role space_role,GREATEST(COALESCE(${roleSql("m")},0),COALESCE(${roleSql("g")},0),COALESCE(${roleSql("b")},0)) access,
      EXISTS(WITH RECURSIVE ancestors AS(SELECT id,parent_id,archived_at FROM pages WHERE id=p.id UNION ALL SELECT a.id,a.parent_id,a.archived_at FROM pages a JOIN ancestors t ON a.id=t.parent_id) SELECT 1 FROM ancestors WHERE archived_at IS NOT NULL) OR EXISTS(SELECT 1 FROM workspace_fields f WHERE f.id=p.field_id AND f.archived_at IS NOT NULL) hidden
      FROM pages p LEFT JOIN space_members m ON m.space_id=p.space_id AND m.user_id=$2 LEFT JOIN page_grants g ON g.page_id=p.id AND g.user_id=$2 LEFT JOIN page_grants b ON p.kind='record' AND b.page_id=p.parent_id AND b.user_id=$2 WHERE p.id=$1`,
      [id, user.id],
    );
    const result = rows[0];
    assert(
      result && result.access > 0 && (archived || !result.hidden),
      404,
      "Trang không tồn tại hoặc bạn không có quyền xem.",
    );
    assert(
      result.access >= min,
      403,
      "Bạn chưa có quyền thực hiện thao tác này.",
    );
    return result;
  }
  async field(client, id, user, min = 1, archived = false) {
    const field = (
      await client.query("SELECT * FROM workspace_fields WHERE id=$1", [id])
    ).rows[0];
    assert(
      field && (archived || !field.archived_at),
      404,
      "Lĩnh vực không tồn tại hoặc đã lưu trữ.",
    );
    const space = await this.space(client, field.space_id, user, min);
    return { ...field, access: space.access };
  }
  async event(client, user, spaceId, pageId, action, detail = {}) {
    await client.query(
      "INSERT INTO workspace_activity(id,space_id,page_id,actor_id,action,detail) VALUES($1,$2,$3,$4,$5,$6)",
      [randomUUID(), spaceId, pageId, user.id, action, detail],
    );
    await client.query("SELECT pg_notify('workspace_changes',$1)", [
      JSON.stringify({ space_id: spaceId, page_id: pageId, action }),
    ]);
  }
  async insertPage(client, user, spaceId, input) {
    await client.query("SELECT id FROM spaces WHERE id=$1 FOR SHARE", [
      spaceId,
    ]);
    let fieldId = input.field_id ?? null;
    if (input.parent_id) {
      const parent = await this.page(client, input.parent_id, user, 3);
      assert(
        parent.space_id === spaceId,
        400,
        "Trang cha không cùng không gian.",
      );
      if (input.field_id !== undefined)
        assert(
          input.field_id === parent.field_id,
          400,
          "Trang con phải nằm trong cùng lĩnh vực với trang cha.",
        );
      fieldId = parent.field_id;
    }
    if (fieldId) {
      const field = await this.field(client, fieldId, user, 3);
      assert(
        field.space_id === spaceId,
        400,
        "Lĩnh vực không cùng không gian.",
      );
    }
    const id = randomUUID();
    const { rows } = await client.query(
      `INSERT INTO pages(id,space_id,parent_id,title,kind,created_by,updated_by,sources,field_id,sort_order) VALUES($1,$2,$3,$4,$5,$6,$6,$7,$8,COALESCE((SELECT max(sort_order)+1 FROM pages WHERE space_id=$2 AND parent_id IS NOT DISTINCT FROM $3 AND field_id IS NOT DISTINCT FROM $8),0)) RETURNING *`,
      [
        id,
        spaceId,
        input.parent_id || null,
        input.title,
        input.kind || "page",
        user.id,
        JSON.stringify(input.sources || []),
        fieldId,
      ],
    );
    await client.query("INSERT INTO page_documents(page_id) VALUES($1)", [id]);
    return rows[0];
  }
  async bootstrap(user) {
    await this.tx(async (client) => {
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
        `workspace-user:${user.id}`,
      ]);
      const existing = await client.query(
        "SELECT id FROM spaces WHERE owner_id=$1 AND kind='personal'",
        [user.id],
      );
      if (!existing.rowCount) {
        const id = randomUUID();
        await client.query(
          "INSERT INTO spaces(id,title,kind,owner_id) VALUES($1,'Không gian cá nhân','personal',$2)",
          [id, user.id],
        );
        await client.query(
          "INSERT INTO space_members(space_id,user_id,role) VALUES($1,$2,'owner')",
          [id, user.id],
        );
      }
    });
    const spaces = await this.pool.query(
      "SELECT s.*,m.role FROM spaces s JOIN space_members m ON m.space_id=s.id WHERE m.user_id=$1 ORDER BY s.kind,s.created_at",
      [user.id],
    );
    const shared = await this.pool.query(
      `SELECT p.id,p.title,p.icon,p.space_id,g.role FROM pages p JOIN page_grants g ON g.page_id=p.id WHERE g.user_id=$1 AND p.archived_at IS NULL AND NOT EXISTS(SELECT 1 FROM space_members m WHERE m.space_id=p.space_id AND m.user_id=$1)`,
      [user.id],
    );
    const invites = await this.pool.query(
      `SELECT i.id,i.role,i.page_id,i.space_id,COALESCE(p.title,s.title) title,u.name sender FROM invitations i LEFT JOIN pages p ON p.id=i.page_id LEFT JOIN spaces s ON s.id=i.space_id JOIN workspace_users u ON u.id=i.created_by WHERE i.email=$1 AND i.status='pending' AND i.expires_at>now() ORDER BY i.created_at DESC`,
      [user.email],
    );
    const profile = await this.pool.query(
      "SELECT id,name,email FROM workspace_users WHERE id=$1",
      [user.id],
    );
    const fields = await this.pool.query(
      `SELECT f.*,count(p.id)::int page_count,GREATEST(f.updated_at,COALESCE(max(p.updated_at),f.updated_at)) last_activity FROM workspace_fields f JOIN space_members m ON m.space_id=f.space_id AND m.user_id=$1 LEFT JOIN pages p ON p.field_id=f.id AND p.archived_at IS NULL WHERE f.archived_at IS NULL GROUP BY f.id ORDER BY f.created_at`,
      [user.id],
    );
    return {
      user: profile.rows[0],
      spaces: spaces.rows,
      shared_pages: shared.rows,
      invitations: invites.rows,
      fields: fields.rows,
    };
  }
  async createSpace(user, title) {
    return this.tx(async (client) => {
      const count = await client.query(
        "SELECT count(*)::int n FROM spaces WHERE owner_id=$1",
        [user.id],
      );
      assert(count.rows[0].n < 30, 409, "Bạn đã đạt giới hạn 30 không gian.");
      const id = randomUUID();
      const { rows } = await client.query(
        "INSERT INTO spaces(id,title,kind,owner_id) VALUES($1,$2,'team',$3) RETURNING *",
        [id, title, user.id],
      );
      await client.query(
        "INSERT INTO space_members(space_id,user_id,role) VALUES($1,$2,'owner')",
        [id, user.id],
      );
      return rows[0];
    });
  }
  async listPages(user, spaceId, archived = false) {
    await this.space(this.pool, spaceId, user);
    const { rows } = await this.pool.query(
      `SELECT p.*,COALESCE(f.favorite,false) favorite,f.opened_at FROM pages p LEFT JOIN page_preferences f ON f.page_id=p.id AND f.user_id=$2 WHERE p.space_id=$1 AND (p.archived_at IS NOT NULL)=$3 ORDER BY p.sort_order,p.created_at LIMIT 5000`,
      [spaceId, user.id, archived],
    );
    return rows;
  }
  async getPage(user, id) {
    const page = await this.page(this.pool, id, user);
    const document = await this.pool.query(
      "SELECT revision,generation,search_text FROM page_documents WHERE page_id=$1",
      [id],
    );
    await this.pool.query(
      `INSERT INTO page_preferences(page_id,user_id) VALUES($1,$2) ON CONFLICT(page_id,user_id) DO UPDATE SET opened_at=now()`,
      [id, user.id],
    );
    const preferences = await this.pool.query(
      "SELECT favorite FROM page_preferences WHERE page_id=$1 AND user_id=$2",
      [id, user.id],
    );
    const membership = await this.pool.query(
      "SELECT role FROM space_members WHERE space_id=$1 AND user_id=$2",
      [page.space_id, user.id],
    );
    const editor = (
      await this.pool.query("SELECT name FROM workspace_users WHERE id=$1", [
        page.updated_by,
      ])
    ).rows[0];
    return {
      ...page,
      ...document.rows[0],
      favorite: preferences.rows[0]?.favorite || false,
      space_role: membership.rows[0]?.role || null,
      last_editor: editor?.name,
    };
  }
  async search(user, query) {
    if (query.trim().length < 2) return [];
    const { rows } = await this.pool.query(
      `SELECT p.id,p.title,p.icon,p.space_id,left(d.search_text,180) snippet FROM pages p JOIN page_documents d ON d.page_id=p.id WHERE p.archived_at IS NULL AND (p.title ILIKE $2 OR d.search_text ILIKE $2) AND (EXISTS(SELECT 1 FROM space_members m WHERE m.space_id=p.space_id AND m.user_id=$1) OR EXISTS(SELECT 1 FROM page_grants g WHERE g.page_id=p.id AND g.user_id=$1)) ORDER BY p.updated_at DESC LIMIT 60`,
      [user.id, `%${query.replace(/[\\%_]/g, "\\$&")}%`],
    );
    const visible = [];
    for (const row of rows) {
      try {
        await this.page(this.pool, row.id, user);
        visible.push(row);
      } catch {}
    }
    return visible;
  }
}
