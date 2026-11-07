import { randomUUID } from "node:crypto";
import * as Y from "yjs";
import { assert } from "./errors.mjs";
import { defaultFields } from "./validation.mjs";
import { templates } from "./templates.mjs";
import { indexPageLinks } from "./links.mjs";
import { Databases } from "./databases.mjs";

export class Pages {
  constructor(store) {
    this.store = store;
  }
  async create(user, spaceId, input) {
    return this.store.tx(async (client) => {
      await this.store.space(client, spaceId, user, 3);
      if (input.parent_id) {
        const parent = await this.store.page(client, input.parent_id, user, 3);
        assert(
          parent.space_id === spaceId &&
            parent.kind !== "record" &&
            parent.kind !== "database",
          400,
          "Trang cha không hợp lệ.",
        );
      }
      const page = await this.store.insertPage(client, user, spaceId, input);
      if (input.template && templates[input.template]) {
        page.initial_markdown = templates[input.template];
        await client.query("UPDATE pages SET initial_markdown=$2 WHERE id=$1", [
          page.id,
          page.initial_markdown,
        ]);
      }
      if (input.markdown) {
        page.initial_markdown = input.markdown;
        await client.query("UPDATE pages SET initial_markdown=$2 WHERE id=$1", [
          page.id,
          input.markdown,
        ]);
      }
      if (page.kind === "database") {
        await client.query(
          "INSERT INTO database_schemas(page_id,fields) VALUES($1,$2)",
          [page.id, JSON.stringify(defaultFields)],
        );
        for (const [name, type] of [
          ["Bảng", "table"],
          ["Kanban", "board"],
          ["Lịch", "calendar"],
        ])
          await client.query(
            "INSERT INTO database_views(id,page_id,name,type,config) VALUES($1,$2,$3,$4,$5)",
            [
              randomUUID(),
              page.id,
              name,
              type,
              { group_by: "status", date_field: "date" },
            ],
          );
      }
      await this.store.event(client, user, spaceId, page.id, "page.created");
      return page;
    });
  }
  async patch(user, id, input) {
    return this.store.tx(async (client) => {
      const initial = await this.store.page(client, id, user, 3);
      if ("parent_id" in input || "field_id" in input)
        await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
          initial.space_id,
        ]);
      await client.query("SELECT id FROM pages WHERE id=$1 FOR UPDATE", [id]);
      const page = await this.store.page(client, id, user, 3);
      assert(
        page.version === input.version,
        409,
        "Trang vừa thay đổi. Tải lại trước khi lưu.",
        "version_conflict",
      );
      if ("parent_id" in input || "field_id" in input) {
        await this.store.space(client, page.space_id, user, 4);
        const fieldId = "field_id" in input ? input.field_id : page.field_id;
        if (fieldId) {
          const field = await this.store.field(client, fieldId, user, 4);
          assert(
            field.space_id === page.space_id,
            400,
            "Lĩnh vực không cùng không gian.",
          );
        }
        const parentId =
          "parent_id" in input ? input.parent_id : page.parent_id;
        if (parentId) {
          const parent = await this.store.page(client, parentId, user, 4);
          assert(
            parent.space_id === page.space_id &&
              parent.kind === "page" &&
              parent.field_id === fieldId,
            400,
            "Trang cha không hợp lệ.",
          );
          const cycle = await client.query(
            "WITH RECURSIVE children AS(SELECT id FROM pages WHERE id=$1 UNION ALL SELECT p.id FROM pages p JOIN children c ON p.parent_id=c.id) SELECT 1 FROM children WHERE id=$2",
            [id, parentId],
          );
          assert(
            !cycle.rowCount,
            400,
            "Không thể di chuyển vào trang con của chính trang này.",
          );
        }
        assert(
          page.kind !== "record",
          400,
          "Di chuyển mục qua bảng bằng thao tác quản lý bảng.",
        );
        if ("field_id" in input && input.field_id !== page.field_id)
          await client.query(
            "WITH RECURSIVE branch AS(SELECT id FROM pages WHERE id=$1 UNION ALL SELECT p.id FROM pages p JOIN branch b ON p.parent_id=b.id) UPDATE pages SET field_id=$2,version=version+1,updated_by=$3 WHERE id IN(SELECT id FROM branch) AND id<>$1",
            [id, input.field_id, user.id],
          );
      }
      if (input.cover_image_id) {
        const binding = await client.query(
          "SELECT 1 FROM attachments a JOIN attachment_bindings b ON b.attachment_id=a.id WHERE a.id=$1 AND b.page_id=$2 AND a.mime IN ('image/png','image/jpeg','image/webp')",
          [input.cover_image_id, id],
        );
        assert(binding.rowCount, 400, "Ảnh bìa phải là ảnh đã tải lên trang này.");
      }
      const allowed = [
        "title",
        "icon",
        "cover",
        "cover_image_id",
        "full_width",
        "parent_id",
        "field_id",
        "sort_order",
        "sources",
      ];
      const keys = allowed.filter((key) => key in input);
      if (!keys.length) return page;
      const values = keys.map((key) =>
        key === "sources" ? JSON.stringify(input[key]) : input[key],
      );
      const { rows } = await client.query(
        `UPDATE pages SET ${keys.map((key, i) => `${key}=$${i + 2}`).join(",")},version=version+1,updated_at=now(),updated_by=$${keys.length + 2} WHERE id=$1 RETURNING *`,
        [id, ...values, user.id],
      );
      await this.store.event(client, user, page.space_id, id, "page.updated", {
        fields: keys,
      });
      return rows[0];
    });
  }
  async archive(user, id) {
    return this.store.tx(async (client) => {
      const page = await this.store.page(client, id, user, 4);
      await this.store.space(client, page.space_id, user, 4);
      await client.query("SELECT id FROM spaces WHERE id=$1 FOR UPDATE", [
        page.space_id,
      ]);
      const batch = randomUUID();
      await client.query(
        `WITH RECURSIVE branch AS(SELECT id FROM pages WHERE id=$1 UNION ALL SELECT p.id FROM pages p JOIN branch b ON p.parent_id=b.id) UPDATE pages SET archived_at=now(),archived_batch=$2,updated_by=$3,version=version+1 WHERE id IN(SELECT id FROM branch) AND archived_at IS NULL`,
        [id, batch, user.id],
      );
      await this.store.event(client, user, page.space_id, id, "page.archived");
      return { batch };
    });
  }
  async restore(user, id) {
    return this.store.tx(async (client) => {
      const page = await this.store.page(client, id, user, 4, true);
      await this.store.space(client, page.space_id, user, 4);
      assert(page.archived_batch, 409, "Trang đang hoạt động.");
      if (page.field_id) await this.store.field(client, page.field_id, user);
      if (page.parent_id) await this.store.page(client, page.parent_id, user);
      await client.query(
        "UPDATE pages SET archived_at=NULL,archived_batch=NULL,updated_by=$2,version=version+1 WHERE archived_batch=$1",
        [page.archived_batch, user.id],
      );
      await this.store.event(client, user, page.space_id, id, "page.restored");
      return { id };
    });
  }
  async duplicate(user, id) {
    return this.store.tx(async (client) => {
      const original = await this.store.page(client, id, user);
      await this.store.space(client, original.space_id, user, 3);
      const page = await this.store.insertPage(
        client,
        user,
        original.space_id,
        {
          title: `${original.title.slice(0, 285)} (bản sao)`,
          kind: original.kind === "record" ? "page" : original.kind,
          parent_id: original.kind === "record" ? null : original.parent_id,
          sources: original.sources,
          field_id: original.field_id,
        },
      );
      const saved = await client.query(
        "SELECT state,search_text,revision FROM page_documents WHERE page_id=$1",
        [id],
      );
      await client.query(
        "UPDATE page_documents SET state=$2,search_text=$3,revision=$4 WHERE page_id=$1",
        [
          page.id,
          saved.rows[0].state,
          saved.rows[0].search_text,
          Number(saved.rows[0].revision) ? 1 : 0,
        ],
      );
      await client.query(
        "UPDATE pages SET icon=$2,cover=$3,properties=$4,initial_markdown=$5,cover_image_id=$6 WHERE id=$1",
        [
          page.id,
          original.icon,
          original.cover,
          original.properties,
          original.initial_markdown,
          original.cover_image_id,
        ],
      );
      await client.query(
        "INSERT INTO page_links(source_id,target_id) SELECT $2,target_id FROM page_links WHERE source_id=$1 ON CONFLICT DO NOTHING",
        [id, page.id],
      );
      await client.query(
        "INSERT INTO attachment_bindings(attachment_id,page_id) SELECT attachment_id,$2 FROM attachment_bindings WHERE page_id=$1 ON CONFLICT DO NOTHING",
        [id, page.id],
      );
      if (original.kind === "database") {
        await client.query(
          "INSERT INTO database_schemas(page_id,fields) SELECT $2,fields FROM database_schemas WHERE page_id=$1",
          [id, page.id],
        );
        await client.query(
          "INSERT INTO database_views(id,page_id,name,type,config) VALUES($1,$2,'Bảng','table','{}')",
          [randomUUID(), page.id],
        );
      }
      await this.store.event(
        client,
        user,
        page.space_id,
        page.id,
        "page.duplicated",
        { source_page: id },
      );
      return page;
    });
  }
  async favorite(user, id, value) {
    await this.store.page(this.store.pool, id, user);
    await this.store.pool.query(
      "INSERT INTO page_preferences(page_id,user_id,favorite,opened_at) VALUES($1,$2,$3,NULL) ON CONFLICT(page_id,user_id) DO UPDATE SET favorite=EXCLUDED.favorite",
      [id, user.id, value],
    );
    return { favorite: value };
  }
  async snapshot(client, user, page, label) {
    const document = await client.query(
      "SELECT state FROM page_documents WHERE page_id=$1 FOR UPDATE",
      [page.id],
    );
    const id = randomUUID();
    await client.query(
      "INSERT INTO page_versions(id,page_id,author_id,title,label,state,properties) VALUES($1,$2,$3,$4,$5,$6,$7)",
      [
        id,
        page.id,
        user.id,
        page.title,
        label,
        document.rows[0].state,
        page.properties,
      ],
    );
    return { id };
  }
  async versions(user, id) {
    await this.store.page(this.store.pool, id, user);
    return (
      await this.store.pool.query(
        "SELECT v.id,v.label,v.title,v.created_at,u.name author FROM page_versions v JOIN workspace_users u ON u.id=v.author_id WHERE page_id=$1 ORDER BY created_at DESC LIMIT 100",
        [id],
      )
    ).rows;
  }
  async createVersion(user, id, label) {
    return this.store.tx(async (client) => {
      const page = await this.store.page(client, id, user, 3);
      return this.snapshot(client, user, page, label);
    });
  }
  async restoreVersion(user, id, versionId) {
    return this.store.tx(async (client) => {
      const page = await this.store.page(client, id, user, 4);
      const version = (
        await client.query(
          "SELECT * FROM page_versions WHERE id=$1 AND page_id=$2",
          [versionId, id],
        )
      ).rows[0];
      assert(version, 404, "Không tìm thấy phiên bản.");
      if (page.kind === "record") {
        const databases = new Databases(this.store),
          schema = await databases.schema(
            client,
            user,
            page.parent_id,
            1,
            true,
          );
        try {
          await databases.validateValues(
            client,
            user,
            schema.fields,
            version.properties,
            page.parent_id,
          );
        } catch (error) {
          if (error.status >= 400 && error.status < 500)
            assert(
              false,
              409,
              "Thuộc tính phiên bản cũ không còn phù hợp với cấu trúc hoặc quyền hiện tại. Nội dung hiện tại vẫn được giữ.",
            );
          throw error;
        }
      }
      await this.snapshot(client, user, page, "Trước khi khôi phục");
      const doc = new Y.Doc();
      if (version.state.length) Y.applyUpdate(doc, version.state);
      const xml = doc.getXmlFragment("document-store").toString();
      const text = xml.replace(/<[^>]*>/g, " ").slice(0, 200000);
      doc.destroy();
      await indexPageLinks(client, id, xml);
      await client.query(
        "UPDATE page_documents SET state=$2,generation=generation+1,revision=revision+1,search_text=$3,updated_at=now() WHERE page_id=$1",
        [id, version.state, text],
      );
      await client.query(
        "UPDATE pages SET title=$2,properties=$3,version=version+1,updated_by=$4,updated_at=now() WHERE id=$1",
        [id, version.title, version.properties, user.id],
      );
      await this.store.event(
        client,
        user,
        page.space_id,
        id,
        "document.restored",
      );
      return { id };
    });
  }
}
