import { randomUUID } from "node:crypto";
import { fileTypeFromBuffer } from "file-type";
import { assert } from "./errors.mjs";
export class Files {
  constructor(store) {
    this.store = store;
  }
  async upload(user, pageId, bytes, filename) {
    assert(
      Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= 10485760,
      413,
      "Tệp phải nhỏ hơn 10 MB.",
    );
    let type;
    try {
      type = await fileTypeFromBuffer(bytes);
    } catch {
      assert(false, 400, "Tệp không hợp lệ hoặc chưa đầy đủ.");
    }
    const allowed = [
      "image/png",
      "image/jpeg",
      "image/webp",
      "application/pdf",
    ];
    assert(
      type && allowed.includes(type.mime),
      400,
      "Chỉ hỗ trợ PNG, JPEG, WebP và PDF.",
    );
    return this.store.tx(async (client) => {
      await this.store.page(client, pageId, user, 3);
      await client.query(
        "SELECT id FROM workspace_users WHERE id=$1 FOR UPDATE",
        [user.id],
      );
      const usage = (
        await client.query(
          "SELECT COALESCE(sum(size),0)::bigint bytes,count(*) FILTER(WHERE created_at>now()-interval '1 hour') recent FROM attachments WHERE uploaded_by=$1",
          [user.id],
        )
      ).rows[0];
      assert(
        Number(usage.bytes) + bytes.length <= 104857600 &&
          Number(usage.recent) < 40,
        429,
        "Đã đạt giới hạn lưu trữ hoặc tải tệp trong giờ.",
      );
      let decodedName = String(filename || `attachment.${type.ext}`);
      try {
        decodedName = decodeURIComponent(decodedName);
      } catch {}
      const id = randomUUID(),
        name = decodedName.replace(/[\x00-\x1f\x7f/\\]/g, "_").slice(0, 180);
      await client.query(
        "INSERT INTO attachments(id,uploaded_by,filename,mime,content,size) VALUES($1,$2,$3,$4,$5,$6)",
        [id, user.id, name, type.mime, bytes, bytes.length],
      );
      await client.query(
        "INSERT INTO attachment_bindings(attachment_id,page_id) VALUES($1,$2)",
        [id, pageId],
      );
      return { id, name, mime: type.mime, url: `/api/workspace/files/${id}` };
    });
  }
  async get(user, id) {
    const bindings = await this.store.pool.query(
      "SELECT page_id FROM attachment_bindings WHERE attachment_id=$1",
      [id],
    );
    let authorized = false;
    for (const binding of bindings.rows) {
      try {
        await this.store.page(this.store.pool, binding.page_id, user);
        authorized = true;
        break;
      } catch {}
    }
    assert(authorized, 404, "Tệp không tồn tại hoặc bạn không có quyền xem.");
    return (
      await this.store.pool.query(
        "SELECT filename,mime,content FROM attachments WHERE id=$1",
        [id],
      )
    ).rows[0];
  }
}
