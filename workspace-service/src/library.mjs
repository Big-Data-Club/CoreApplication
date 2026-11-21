// Apply the same space, direct-page and database-record grants as Store.page.
// Hidden ancestors/fields are removed before sorting, filtering and pagination.
const scope = `WITH RECURSIVE hidden(id) AS (
  SELECT p.id FROM pages p LEFT JOIN workspace_fields f ON f.id=p.field_id
  WHERE p.archived_at IS NOT NULL OR f.archived_at IS NOT NULL
  UNION SELECT p.id FROM pages p JOIN hidden h ON p.parent_id=h.id
), visible AS (
  SELECT p.*,s.title space_title,s.kind space_kind,s.owner_id,sm.role space_role,
    GREATEST(CASE sm.role WHEN 'owner' THEN 5 WHEN 'manager' THEN 4 WHEN 'editor' THEN 3 WHEN 'commenter' THEN 2 WHEN 'viewer' THEN 1 ELSE 0 END,
      CASE g.role WHEN 'manager' THEN 4 WHEN 'editor' THEN 3 WHEN 'commenter' THEN 2 WHEN 'viewer' THEN 1 ELSE 0 END,
      CASE b.role WHEN 'manager' THEN 4 WHEN 'editor' THEN 3 WHEN 'commenter' THEN 2 WHEN 'viewer' THEN 1 ELSE 0 END) access,
    (s.kind='team' OR EXISTS(SELECT 1 FROM space_members other WHERE other.space_id=s.id AND other.user_id<>s.owner_id)
      OR EXISTS(SELECT 1 FROM page_grants shared WHERE shared.page_id=p.id OR (p.kind='record' AND shared.page_id=p.parent_id))) shared
  FROM pages p JOIN spaces s ON s.id=p.space_id
  LEFT JOIN space_members sm ON sm.space_id=p.space_id AND sm.user_id=$1
  LEFT JOIN page_grants g ON g.page_id=p.id AND g.user_id=$1
  LEFT JOIN page_grants b ON p.kind='record' AND b.page_id=p.parent_id AND b.user_id=$1
  WHERE (sm.role IS NOT NULL OR g.role IS NOT NULL OR b.role IS NOT NULL)
    AND NOT EXISTS(SELECT 1 FROM hidden h WHERE h.id=p.id)
), catalog AS (
  SELECT p.id,p.title,p.icon,p.kind,p.created_at,p.updated_at,p.created_by,p.updated_by,
    p.access,p.space_role,COALESCE(pref.favorite,false) favorite,pref.opened_at,
    creator.name creator_name,editor.name last_editor,p.shared,
    (p.space_kind='personal' AND p.owner_id=$1 AND NOT p.shared) private,
    CASE WHEN p.space_role IS NOT NULL THEN p.space_id END space_id,
    CASE WHEN p.space_role IS NOT NULL THEN p.field_id END field_id,
    parent.id parent_id,EXISTS(SELECT 1 FROM visible c WHERE c.parent_id=p.id) has_children,
    CASE WHEN parent.id IS NOT NULL THEN jsonb_build_object('kind','page','id',parent.id,'title',parent.title,'icon',parent.icon)
      WHEN p.space_role IS NOT NULL AND f.id IS NOT NULL THEN jsonb_build_object('kind','field','id',f.id,'space_id',p.space_id,'title',f.title,'icon',f.icon)
      WHEN p.space_role IS NOT NULL AND p.space_kind='personal' AND NOT p.shared THEN jsonb_build_object('kind','private','title','Riêng tư')
      WHEN p.space_role IS NOT NULL THEN jsonb_build_object('kind','space','id',p.space_id,'title',p.space_title)
      ELSE jsonb_build_object('kind','shared','title','Được chia sẻ') END source
  FROM visible p LEFT JOIN visible parent ON parent.id=p.parent_id
  LEFT JOIN workspace_fields f ON f.id=p.field_id
  LEFT JOIN page_preferences pref ON pref.page_id=p.id AND pref.user_id=$1
  JOIN workspace_users creator ON creator.id=p.created_by
  JOIN workspace_users editor ON editor.id=p.updated_by
)`;
const columns = {
  title: "lower(title)",
  creator: "lower(creator_name)",
  source: "lower(source->>'title')",
  created: "created_at",
  editor: "lower(last_editor)",
  edited: "updated_at",
  visited: "opened_at",
};
const escaped = (value) => value.replace(/[\\%_]/g, "\\$&");

export class Library {
  constructor(store) {
    this.store = store;
  }
  async list(user, input) {
    if (input.parent)
      await this.store.page(this.store.pool, input.parent, user);
    const values = [user.id],
      clauses = [];
    const bind = (value) => {
      values.push(value);
      return `$${values.length}`;
    };
    if (input.tab === "recent") clauses.push("opened_at IS NOT NULL");
    if (input.tab === "favorites") clauses.push("favorite");
    if (input.tab === "shared") clauses.push("shared");
    if (input.tab === "private") clauses.push("private");
    if (input.parent) clauses.push(`parent_id=${bind(input.parent)}::uuid`);
    if (input.q) clauses.push(`title ILIKE ${bind(`%${escaped(input.q)}%`)}`);
    const rules = input.filters.map((rule) => {
      const field = {
        title: "title",
        creator: "created_by",
        editor: "updated_by",
        created: "created_at",
        edited: "updated_at",
        visited: "opened_at",
      }[rule.field];
      if (rule.op === "empty") return `${field} IS NULL`;
      if (rule.op === "not_empty") return `${field} IS NOT NULL`;
      if (["created", "edited", "visited"].includes(rule.field)) {
        if (rule.op === "past_week") return `${field}>=now()-interval '7 days'`;
        if (rule.op === "past_month")
          return `${field}>=now()-interval '30 days'`;
        const operator = {
          on: "=",
          before: "<",
          after: ">",
          on_or_before: "<=",
          on_or_after: ">=",
        }[rule.op];
        return `(${field} AT TIME ZONE ${bind(input.timezone)})::date ${operator} ${bind(rule.value)}::date`;
      }
      if (rule.field === "creator" || rule.field === "editor")
        return `${field}${rule.op === "eq" ? "=" : "<>"}${bind(rule.value)}`;
      if (rule.op === "eq" || rule.op === "not_eq")
        return `lower(title)${rule.op === "eq" ? "=" : "<>"}lower(${bind(rule.value)})`;
      const pattern =
        rule.op === "starts_with"
          ? `${escaped(rule.value)}%`
          : rule.op === "ends_with"
            ? `%${escaped(rule.value)}`
            : `%${escaped(rule.value)}%`;
      return `title ${rule.op === "not_contains" ? "NOT ILIKE" : "ILIKE"} ${bind(pattern)}`;
    });
    if (rules.length)
      clauses.push(`(${rules.join(input.match === "any" ? " OR " : " AND ")})`);
    const order = `${columns[input.sort]} ${input.direction === "asc" ? "ASC" : "DESC"} NULLS LAST,id ASC`;
    const limit = bind(input.limit),
      offset = bind(input.offset);
    const { rows } = await this.store.pool.query(
      `${scope}, filtered AS (
      SELECT * FROM catalog ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""}
    ), selected AS (SELECT * FROM filtered ORDER BY ${order} LIMIT ${limit} OFFSET ${offset})
    SELECT (SELECT count(*)::int FROM filtered) total,COALESCE((SELECT json_agg(selected ORDER BY ${order}) FROM selected),'[]'::json) items`,
      values,
    );
    const result = rows[0];
    return {
      ...result,
      next_offset:
        input.offset + result.items.length < result.total
          ? input.offset + result.items.length
          : null,
    };
  }
  async options(user) {
    const { rows } = await this.store.pool.query(
      `${scope}
      SELECT COALESCE((SELECT json_agg(person ORDER BY lower(name),id) FROM (SELECT DISTINCT created_by id,creator_name name FROM catalog) person),'[]'::json) creators,
      COALESCE((SELECT json_agg(person ORDER BY lower(name),id) FROM (SELECT DISTINCT updated_by id,last_editor name FROM catalog) person),'[]'::json) editors`,
      [user.id],
    );
    return rows[0];
  }
}
