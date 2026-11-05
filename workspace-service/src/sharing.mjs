import { randomUUID } from "node:crypto";
import { assert } from "./errors.mjs";
export class Sharing {
  constructor(store) {
    this.store = store;
  }
  async members(user, pageId) {
    const page = await this.store.page(this.store.pool, pageId, user);
    const members = await this.store.pool.query(
      `SELECT u.id,u.name,u.email,m.role,'space' source FROM space_members m JOIN workspace_users u ON u.id=m.user_id WHERE m.space_id=$1 UNION ALL SELECT u.id,u.name,u.email,g.role,'page' source FROM page_grants g JOIN workspace_users u ON u.id=g.user_id WHERE g.page_id=$2`,
      [page.space_id, pageId],
    );
    const pending =
      page.access >= 4
        ? (
            await this.store.pool.query(
              `SELECT id,email,role,expires_at FROM invitations WHERE status='pending' AND expires_at>now() AND (page_id=$1 OR (space_id=$2 AND $3)) ORDER BY created_at DESC`,
              [
                pageId,
                page.space_id,
                ["owner", "manager"].includes(page.space_role),
              ],
            )
          ).rows
        : [];
    return { members: members.rows, pending, access: page.access };
  }
  async invite(user, { page_id, space_id, email, role }) {
    return this.store.tx(async (client) => {
      const target = page_id
        ? await this.store.page(client, page_id, user, 4)
        : await this.store.space(client, space_id, user, 4);
      assert(
        !space_id || target.kind === "team",
        400,
        "Không gian cá nhân chỉ chia sẻ từng trang.",
      );
      const normalized = email.trim().toLowerCase();
      assert(normalized !== user.email, 400, "Bạn đã có quyền truy cập.");
      const id = randomUUID();
      await client.query(
        `INSERT INTO invitations(id,page_id,space_id,email,role,created_by) VALUES($1,$2,$3,$4,$5,$6)`,
        [id, page_id || null, space_id || null, normalized, role, user.id],
      );
      await this.store.event(
        client,
        user,
        page_id ? target.space_id : target.id,
        page_id || null,
        "invitation.created",
      );
      return { id };
    });
  }
  async respond(user, id, action) {
    return this.store.tx(async (client) => {
      const invite = (
        await client.query(
          "SELECT * FROM invitations WHERE id=$1 AND email=$2 FOR UPDATE",
          [id, user.email],
        )
      ).rows[0];
      assert(
        invite &&
          invite.status === "pending" &&
          new Date(invite.expires_at).getTime() > Date.now(),
        404,
        "Lời mời không còn hiệu lực.",
      );
      if (action === "accept") {
        const sender = (
          await client.query(
            "SELECT id,email,name FROM workspace_users WHERE id=$1",
            [invite.created_by],
          )
        ).rows[0];
        if (invite.page_id)
          await this.store.page(client, invite.page_id, sender, 4);
        else await this.store.space(client, invite.space_id, sender, 4);
        if (invite.page_id)
          await client.query(
            "INSERT INTO page_grants(page_id,user_id,role) VALUES($1,$2,$3) ON CONFLICT(page_id,user_id) DO UPDATE SET role=EXCLUDED.role",
            [invite.page_id, user.id, invite.role],
          );
        else
          await client.query(
            "INSERT INTO space_members(space_id,user_id,role) VALUES($1,$2,$3) ON CONFLICT(space_id,user_id) DO UPDATE SET role=EXCLUDED.role",
            [invite.space_id, user.id, invite.role],
          );
      }
      await client.query("UPDATE invitations SET status=$2 WHERE id=$1", [
        id,
        action === "accept" ? "accepted" : "declined",
      ]);
      return { status: action };
    });
  }
  async cancel(user, id) {
    return this.store.tx(async (client) => {
      const invite = (
        await client.query("SELECT * FROM invitations WHERE id=$1", [id])
      ).rows[0];
      assert(invite, 404, "Không tìm thấy lời mời.");
      if (invite.page_id)
        await this.store.page(client, invite.page_id, user, 4);
      else await this.store.space(client, invite.space_id, user, 4);
      await client.query(
        "UPDATE invitations SET status='cancelled' WHERE id=$1 AND status='pending'",
        [id],
      );
      return { id };
    });
  }
  async grant(user, { page_id, space_id, member_id, role }) {
    return this.store.tx(async (client) => {
      const target = page_id
        ? await this.store.page(client, page_id, user, 4)
        : await this.store.space(client, space_id, user, 4);
      const space = (
        await client.query("SELECT owner_id,kind FROM spaces WHERE id=$1", [
          page_id ? target.space_id : space_id,
        ])
      ).rows[0];
      assert(
        member_id !== space.owner_id,
        400,
        "Không thể thay đổi quyền chủ sở hữu bằng thao tác này.",
      );
      if (space_id) {
        assert(
          space.kind === "team",
          400,
          "Không gian cá nhân không có thành viên nhóm.",
        );
        assert(
          target.access >= 5,
          403,
          "Chỉ chủ sở hữu quản lý quyền thành viên nhóm.",
        );
      }
      const table = page_id ? "page_grants" : "space_members",
        column = page_id ? "page_id" : "space_id",
        id = page_id || space_id;
      if (role)
        await client.query(
          `UPDATE ${table} SET role=$3 WHERE ${column}=$1 AND user_id=$2`,
          [id, member_id, role],
        );
      else
        await client.query(
          `DELETE FROM ${table} WHERE ${column}=$1 AND user_id=$2`,
          [id, member_id],
        );
      if (space_id && !role) {
        await client.query(
          "DELETE FROM page_grants WHERE user_id=$1 AND page_id IN(SELECT id FROM pages WHERE space_id=$2)",
          [member_id, space_id],
        );
        const email = (
          await client.query("SELECT email FROM workspace_users WHERE id=$1", [
            member_id,
          ])
        ).rows[0]?.email;
        if (email)
          await client.query(
            "UPDATE invitations SET status='cancelled' WHERE email=$1 AND status='pending' AND (space_id=$2 OR page_id IN(SELECT id FROM pages WHERE space_id=$2))",
            [email, space_id],
          );
      }
      await this.store.event(
        client,
        user,
        page_id ? target.space_id : space_id,
        page_id || null,
        "access.changed",
      );
      return { id: member_id };
    });
  }
  async comments(user, id) {
    await this.store.page(this.store.pool, id, user);
    return (
      await this.store.pool.query(
        "SELECT c.*,u.name author_name FROM comments c JOIN workspace_users u ON u.id=c.author_id WHERE c.page_id=$1 ORDER BY c.created_at LIMIT 500",
        [id],
      )
    ).rows;
  }
  async comment(user, id, input) {
    return this.store.tx(async (client) => {
      const page = await this.store.page(client, id, user, 2);
      if (input.parent_id) {
        const parent = (
          await client.query("SELECT page_id FROM comments WHERE id=$1", [
            input.parent_id,
          ])
        ).rows[0];
        assert(
          parent?.page_id === id,
          400,
          "Bình luận gốc không thuộc trang này.",
        );
      }
      const commentId = randomUUID();
      await client.query(
        "INSERT INTO comments(id,page_id,block_id,parent_id,author_id,body) VALUES($1,$2,$3,$4,$5,$6)",
        [commentId, id, input.block_id, input.parent_id, user.id, input.body],
      );
      for (const memberId of new Set(input.mentions)) {
        try {
          await this.store.page(client, id, { id: memberId });
          await client.query(
            "INSERT INTO workspace_notifications(id,user_id,page_id,kind) VALUES($1,$2,$3,'mention')",
            [randomUUID(), memberId, id],
          );
        } catch {}
      }
      await this.store.event(
        client,
        user,
        page.space_id,
        id,
        "comment.created",
      );
      return { id: commentId };
    });
  }
  async changeComment(user, id, input) {
    return this.store.tx(async (client) => {
      const comment = (
        await client.query("SELECT * FROM comments WHERE id=$1", [id])
      ).rows[0];
      assert(comment, 404, "Không tìm thấy bình luận.");
      const page = await this.store.page(client, comment.page_id, user, 2);
      assert(
        comment.author_id === user.id || page.access >= 4,
        403,
        "Chỉ tác giả hoặc người quản lý được đổi bình luận.",
      );
      if (input.delete) {
        await client.query(
          "UPDATE comments SET body=$2,updated_at=now() WHERE id=$1",
          [id, "[Bình luận đã được gỡ]"],
        );
      } else
        await client.query(
          "UPDATE comments SET body=COALESCE($2,body),resolved=COALESCE($3,resolved),updated_at=now() WHERE id=$1",
          [id, input.body || null, input.resolved ?? null],
        );
      await this.store.event(
        client,
        user,
        page.space_id,
        page.id,
        "comment.updated",
      );
      return { id };
    });
  }
}
