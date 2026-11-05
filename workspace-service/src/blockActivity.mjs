import * as Y from "yjs";
export function blockSignatures(fragment) {
  const result = new Map();
  function walk(node) {
    if (!(node instanceof Y.XmlElement) && !(node instanceof Y.XmlFragment))
      return;
    const id = node instanceof Y.XmlElement ? node.getAttribute("id") : null;
    if (
      typeof id === "string" &&
      /^[a-zA-Z0-9_-]{1,100}$/.test(id) &&
      result.size < 10000
    )
      result.set(id, node.toString());
    for (const child of node.toArray()) walk(child);
  }
  walk(fragment);
  return result;
}
export async function recordBlockActivity(client, pageId, user, before, after) {
  const changed = [...after]
    .filter(([id, signature]) => before.get(id) !== signature)
    .map(([id]) => id);
  if (changed.length)
    await client.query(
      "INSERT INTO block_activity(page_id,block_id,actor_id) SELECT $1,unnest($2::text[]),$3 ON CONFLICT(page_id,block_id) DO UPDATE SET actor_id=EXCLUDED.actor_id,updated_at=now()",
      [pageId, changed, user.id],
    );
}
