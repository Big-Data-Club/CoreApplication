export class Analytics {
  constructor(store) {
    this.store = store;
  }
  async visit(user, id) {
    return this.store.tx(async (client) => {
      await this.store.page(client, id, user);
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
        `workspace-visit:${id}:${user.id}`,
      ]);
      const last = (
        await client.query(
          "SELECT 1 FROM page_visits WHERE page_id=$1 AND user_id=$2 AND viewed_at>now()-interval '5 minutes' LIMIT 1",
          [id, user.id],
        )
      ).rowCount;
      if (!last)
        await client.query(
          "INSERT INTO page_visits(page_id,user_id) VALUES($1,$2)",
          [id, user.id],
        );
      return { counted: !last };
    });
  }
  async preference(user, id, showName) {
    await this.store.page(this.store.pool, id, user);
    await this.store.pool.query(
      "INSERT INTO page_view_preferences(page_id,user_id,show_name) VALUES($1,$2,$3) ON CONFLICT(page_id,user_id) DO UPDATE SET show_name=EXCLUDED.show_name",
      [id, user.id, showName],
    );
    return { show_name: showName };
  }
  async read(user, id, days) {
    await this.store.page(this.store.pool, id, user);
    const pool = this.store.pool;
    const [daily, totals, viewers, editors, preference, enabled] =
      await Promise.all([
        pool.query(
          `WITH dates AS(SELECT generate_series((now() AT TIME ZONE 'UTC')::date-($2::int-1),(now() AT TIME ZONE 'UTC')::date,interval '1 day')::date AS day), counts AS(SELECT (viewed_at AT TIME ZONE 'UTC')::date AS day,count(*)::int views,count(DISTINCT user_id)::int unique_viewers FROM page_visits WHERE page_id=$1 AND viewed_at>=((now() AT TIME ZONE 'UTC')::date-($2::int-1)) AT TIME ZONE 'UTC' GROUP BY 1) SELECT to_char(d.day,'YYYY-MM-DD') AS day,COALESCE(c.views,0) views,COALESCE(c.unique_viewers,0) unique_viewers FROM dates d LEFT JOIN counts c USING(day) ORDER BY d.day`,
          [id, days],
        ),
        pool.query(
          "SELECT count(*)::int views,count(DISTINCT user_id)::int unique_viewers FROM page_visits WHERE page_id=$1 AND viewed_at>=((now() AT TIME ZONE 'UTC')::date-($2::int-1)) AT TIME ZONE 'UTC'",
          [id, days],
        ),
        pool.query(
          "SELECT u.name,max(v.viewed_at) viewed_at,count(*)::int views FROM page_visits v JOIN page_view_preferences p ON p.page_id=v.page_id AND p.user_id=v.user_id AND p.show_name JOIN workspace_users u ON u.id=v.user_id WHERE v.page_id=$1 AND v.viewed_at>=((now() AT TIME ZONE 'UTC')::date-($2::int-1)) AT TIME ZONE 'UTC' GROUP BY u.id,u.name ORDER BY viewed_at DESC LIMIT 50",
          [id, days],
        ),
        pool.query(
          "WITH edits AS(SELECT author_id user_id,created_at FROM document_operations WHERE page_id=$1 UNION ALL SELECT actor_id,created_at FROM workspace_activity WHERE page_id=$1 AND action IN('page.created','page.updated','document.restored')) SELECT u.name,max(e.created_at) edited_at FROM edits e JOIN workspace_users u ON u.id=e.user_id GROUP BY u.id,u.name ORDER BY edited_at DESC LIMIT 20",
          [id],
        ),
        pool.query(
          "SELECT show_name FROM page_view_preferences WHERE page_id=$1 AND user_id=$2",
          [id, user.id],
        ),
        pool.query(
          "SELECT applied_at FROM workspace_migrations WHERE name='006_page_analytics.sql'",
        ),
      ]);
    return {
      days,
      ...totals.rows[0],
      daily: daily.rows,
      viewers: viewers.rows,
      editors: editors.rows,
      show_name: preference.rows[0]?.show_name || false,
      tracked_since: enabled.rows[0]?.applied_at,
    };
  }
}
