import { randomUUID } from "node:crypto";
import { assert } from "./errors.mjs";
import { evaluateFormula } from "./formula.mjs";
import { safeUrl } from "./validation.mjs";
const isDate = (value) =>
  typeof value === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) &&
  new Date(value).toISOString().slice(0, 10) === value;
export class Databases {
  constructor(store) {
    this.store = store;
  }
  async schema(client, user, id, min = 1, lock = false) {
    const page = await this.store.page(client, id, user, min);
    assert(page.kind === "database", 400, "Trang này không phải bảng quản lý.");
    const schema = (
      await client.query(
        `SELECT * FROM database_schemas WHERE page_id=$1 ${lock ? "FOR SHARE" : ""}`,
        [id],
      )
    ).rows[0];
    return { ...schema, page };
  }
  async get(user, id, cursor) {
    const schema = await this.schema(this.store.pool, user, id);
    const offset = Math.max(0, Math.min(50000, Number(cursor) || 0));
    const records = await this.store.pool.query(
      "SELECT * FROM pages WHERE parent_id=$1 AND kind='record' AND archived_at IS NULL ORDER BY sort_order,created_at LIMIT 201 OFFSET $2",
      [id, offset],
    );
    const views = await this.store.pool.query(
      "SELECT * FROM database_views WHERE page_id=$1 AND (owner_id IS NULL OR owner_id=$2) ORDER BY created_at",
      [id, user.id],
    );
    const rows = records.rows.slice(0, 200);
    for (const record of rows)
      record.computed = await this.computed(user, schema.fields, record);
    return {
      fields: schema.fields,
      version: schema.version,
      views: views.rows,
      records: rows,
      next_cursor: records.rows.length > 200 ? String(offset + 200) : null,
      access: schema.page.access,
    };
  }
  async computed(user, fields, record) {
    const values = {},
      visiting = new Set();
    const resolve = (fieldId) => {
      const field = fields.find((f) => f.id === fieldId || f.name === fieldId);
      if (!field) throw Error("Thuộc tính không tồn tại.");
      if (Object.hasOwn(values, field.id)) return values[field.id];
      if (visiting.has(field.id)) throw Error("Công thức tham chiếu vòng.");
      visiting.add(field.id);
      try {
        const value =
          field.type === "formula"
            ? evaluateFormula(field.formula || "", resolve)
            : (record.properties[field.id] ?? null);
        values[field.id] = value;
        return value;
      } finally {
        visiting.delete(field.id);
      }
    };
    // Rollups are prepared through access-checked records before formula evaluation.
    for (const field of fields.filter((f) => f.type === "rollup")) {
      try {
        const relation = fields.find(
          (f) => f.id === field.relation_field_id && f.type === "relation",
        );
        assert(relation?.relation_page_id, 400, "Chọn thuộc tính liên kết.");
        await this.schema(this.store.pool, user, relation.relation_page_id);
        const ids = record.properties[relation.id] || [];
        const numbers = [];
        for (const id of ids) {
          const target = await this.store.page(this.store.pool, id, user);
          assert(
            target.parent_id === relation.relation_page_id,
            400,
            "Mục liên kết không hợp lệ.",
          );
          const value = target.properties[field.target_field_id];
          if (typeof value === "number") numbers.push(value);
        }
        values[field.id] =
          field.aggregate === "count"
            ? ids.length
            : field.aggregate === "avg"
              ? numbers.length
                ? numbers.reduce((a, b) => a + b, 0) / numbers.length
                : 0
              : field.aggregate === "min"
                ? numbers.length
                  ? Math.min(...numbers)
                  : 0
                : field.aggregate === "max"
                  ? numbers.length
                    ? Math.max(...numbers)
                    : 0
                  : numbers.reduce((a, b) => a + b, 0);
      } catch {
        values[field.id] = {
          error: "Không tính được từ nguồn liên kết hiện tại.",
        };
      }
    }
    for (const field of fields.filter((f) => f.type === "formula")) {
      try {
        resolve(field.id);
      } catch (error) {
        values[field.id] = { error: error.message };
      }
    }
    return Object.fromEntries(
      fields
        .filter((f) => ["formula", "rollup"].includes(f.type))
        .map((f) => [f.id, values[f.id]]),
    );
  }
  async setSchema(user, id, fields, version) {
    return this.store.tx(async (client) => {
      const current = await this.schema(client, user, id, 4);
      for (const removed of current.fields.filter(
        (before) => !fields.some((after) => after.id === before.id),
      )) {
        const used = await client.query(
          "SELECT 1 FROM pages WHERE parent_id=$1 AND properties ? $2 LIMIT 1",
          [id, removed.id],
        );
        assert(
          !used.rowCount,
          409,
          "Thuộc tính đang có dữ liệu. Chuyển dữ liệu trước khi xóa thuộc tính.",
        );
      }
      await client.query(
        "SELECT page_id FROM database_schemas WHERE page_id=$1 FOR UPDATE",
        [id],
      );
      assert(
        current.version === version,
        409,
        "Cấu trúc bảng vừa thay đổi.",
        "version_conflict",
      );
      for (const field of fields) {
        if (["select", "status", "multi_select"].includes(field.type))
          assert(
            field.options?.length &&
              new Set(field.options.map((o) => o.id)).size ===
                field.options.length,
            400,
            "Các lựa chọn phải có ID riêng.",
          );
        if (field.type === "relation") {
          const target = await this.schema(
            client,
            user,
            field.relation_page_id,
          );
          assert(
            target.page.space_id === current.page.space_id,
            400,
            "Bảng liên kết phải trong cùng không gian.",
          );
        }
        if (field.type === "formula")
          assert(field.formula?.trim(), 400, "Nhập công thức.");
        if (field.type === "rollup")
          assert(
            field.relation_field_id && field.target_field_id && field.aggregate,
            400,
            "Chọn nguồn tổng hợp.",
          );
        if (field.type === "rollup") {
          const relation = fields.find(
            (item) =>
              item.id === field.relation_field_id && item.type === "relation",
          );
          assert(
            relation?.relation_page_id,
            400,
            "Chọn liên kết đến bảng nguồn.",
          );
          const target = await this.schema(
            client,
            user,
            relation.relation_page_id,
          );
          const targetField = target.fields.find(
            (item) => item.id === field.target_field_id,
          );
          assert(
            targetField &&
              (field.aggregate === "count" || targetField.type === "number"),
            400,
            "Tổng, trung bình, nhỏ nhất và lớn nhất cần thuộc tính Số từ bảng nguồn.",
          );
        }
        const before = current.fields.find((f) => f.id === field.id);
        if (before?.options && field.options) {
          const removed = before.options
            .filter(
              (option) => !field.options.some((next) => next.id === option.id),
            )
            .map((option) => option.id);
          if (removed.length) {
            const used = await client.query(
              "SELECT 1 FROM pages WHERE parent_id=$1 AND (properties->>$2=ANY($3::text[]) OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(CASE WHEN jsonb_typeof(properties->$2)='array' THEN properties->$2 ELSE '[]'::jsonb END) value WHERE value=ANY($3::text[]))) LIMIT 1",
              [id, field.id, removed],
            );
            assert(
              !used.rowCount,
              409,
              "Lựa chọn đang được dùng. Đổi dữ liệu trước khi xóa lựa chọn.",
            );
          }
        }
        if (before && before.type !== field.type) {
          const used = await client.query(
            "SELECT 1 FROM pages WHERE parent_id=$1 AND properties ? $2 LIMIT 1",
            [id, field.id],
          );
          assert(
            !used.rowCount,
            409,
            "Cột đã có dữ liệu. Tạo cột mới để chuyển kiểu an toàn.",
          );
        }
      }
      const updated = (
        await client.query(
          "UPDATE database_schemas SET fields=$2,version=version+1 WHERE page_id=$1 AND version=$3 RETURNING *",
          [id, JSON.stringify(fields), version],
        )
      ).rows[0];
      assert(updated, 409, "Cấu trúc bảng vừa thay đổi.", "version_conflict");
      await this.store.event(
        client,
        user,
        current.page.space_id,
        id,
        "database.schema_updated",
      );
      return updated;
    });
  }
  async validateValues(client, user, fields, values, pageId) {
    const result = {};
    assert(Object.keys(values).length <= 40, 400, "Quá nhiều thuộc tính.");
    for (const [key, value] of Object.entries(values)) {
      const field = fields.find((f) => f.id === key);
      assert(
        field && !["formula", "rollup"].includes(field.type),
        400,
        "Thuộc tính không hợp lệ hoặc chỉ đọc.",
      );
      if (value === null) {
        result[key] = null;
        continue;
      }
      switch (field.type) {
        case "number":
          assert(
            typeof value === "number" && Number.isFinite(value),
            400,
            "Cần nhập số hợp lệ.",
          );
          break;
        case "checkbox":
          assert(
            typeof value === "boolean",
            400,
            "Giá trị checkbox không hợp lệ.",
          );
          break;
        case "date":
          assert(
            value &&
              isDate(value.start) &&
              (!value.end || (isDate(value.end) && value.end >= value.start)),
            400,
            "Ngày hoặc khoảng ngày không hợp lệ.",
          );
          break;
        case "select":
        case "status":
          assert(
            typeof value === "string" &&
              field.options?.some((option) => option.id === value),
            400,
            "Lựa chọn không hợp lệ.",
          );
          break;
        case "multi_select":
          assert(
            Array.isArray(value) &&
              value.length <= 30 &&
              value.every((item) =>
                field.options?.some((option) => option.id === item),
              ),
            400,
            "Nhãn không hợp lệ.",
          );
          break;
        case "person": {
          assert(
            Array.isArray(value) &&
              value.length <= 30 &&
              value.every(
                (v) => typeof v === "string" && /^[1-9][0-9]{0,18}$/.test(v),
              ),
            400,
            "Người phụ trách không hợp lệ.",
          );
          for (const id of value) await this.store.page(client, pageId, { id });
          break;
        }
        case "relation": {
          assert(
            Array.isArray(value) &&
              value.length <= 50 &&
              value.every((v) => /^[0-9a-f-]{36}$/.test(v)),
            400,
            "Liên kết mục không hợp lệ.",
          );
          for (const id of value) {
            const target = await this.store.page(client, id, user);
            assert(
              target.parent_id === field.relation_page_id &&
                target.kind === "record",
              400,
              "Mục không thuộc bảng được liên kết.",
            );
          }
          break;
        }
        case "url":
          assert(
            safeUrl.safeParse(value).success,
            400,
            "Liên kết không hợp lệ.",
          );
          break;
        default:
          assert(
            typeof value === "string" && value.length <= 5000,
            400,
            "Văn bản quá dài.",
          );
      }
      result[key] = value;
    }
    return result;
  }
  async createRecord(user, id, title, values = {}) {
    return this.store.tx(async (client) => {
      const schema = await this.schema(client, user, id, 3, true);
      const parsed = await this.validateValues(
        client,
        user,
        schema.fields,
        values,
        id,
      );
      const page = await this.store.insertPage(
        client,
        user,
        schema.page.space_id,
        { title, parent_id: id, kind: "record" },
      );
      const record = (
        await client.query(
          "UPDATE pages SET properties=$2 WHERE id=$1 RETURNING *",
          [page.id, parsed],
        )
      ).rows[0];
      await this.store.event(client, user, page.space_id, id, "record.created");
      return record;
    });
  }
  async patchRecord(user, id, input) {
    return this.store.tx(async (client) => {
      await client.query("SELECT id FROM pages WHERE id=$1 FOR UPDATE", [id]);
      const record = await this.store.page(client, id, user, 3);
      assert(record.kind === "record", 400, "Đây không phải mục trong bảng.");
      assert(
        record.version === input.version,
        409,
        "Mục vừa được người khác sửa. Nội dung của bạn vẫn được giữ để thử lại.",
        "version_conflict",
      );
      const schema = await this.schema(client, user, record.parent_id, 3, true);
      const values = await this.validateValues(
        client,
        user,
        schema.fields,
        input.values,
        record.parent_id,
      );
      const updated = (
        await client.query(
          "UPDATE pages SET properties=properties||$2::jsonb,title=COALESCE($3,title),version=version+1,updated_at=now(),updated_by=$4 WHERE id=$1 RETURNING *",
          [id, JSON.stringify(values), input.title || null, user.id],
        )
      ).rows[0];
      await this.store.event(
        client,
        user,
        record.space_id,
        record.parent_id,
        "record.updated",
      );
      return updated;
    });
  }
  async saveView(user, id, input, viewId = null, version = null) {
    return this.store.tx(async (client) => {
      const schema = await this.schema(
        client,
        user,
        id,
        input.personal ? 3 : 4,
      );
      if (viewId) {
        const previous = (
          await client.query(
            "SELECT * FROM database_views WHERE id=$1 AND page_id=$2 FOR UPDATE",
            [viewId, id],
          )
        ).rows[0];
        assert(
          previous &&
            (previous.owner_id === null || previous.owner_id === user.id),
          404,
          "Không tìm thấy cách xem.",
        );
        assert(
          previous.version === version,
          409,
          "Cách xem đã thay đổi.",
          "version_conflict",
        );
        assert(
          (previous.owner_id !== null) === input.personal,
          400,
          "Không thay đổi phạm vi của cách xem hiện có.",
        );
        const row = (
          await client.query(
            "UPDATE database_views SET name=$2,type=$3,config=$4,version=version+1 WHERE id=$1 RETURNING *",
            [viewId, input.name, input.type, input.config],
          )
        ).rows[0];
        await this.store.event(
          client,
          user,
          schema.page.space_id,
          id,
          "database.view_updated",
        );
        return row;
      }
      const row = (
        await client.query(
          "INSERT INTO database_views(id,page_id,owner_id,name,type,config) VALUES($1,$2,$3,$4,$5,$6) RETURNING *",
          [
            randomUUID(),
            id,
            input.personal ? user.id : null,
            input.name,
            input.type,
            input.config,
          ],
        )
      ).rows[0];
      await this.store.event(
        client,
        user,
        schema.page.space_id,
        id,
        "database.view_created",
      );
      return row;
    });
  }
}
