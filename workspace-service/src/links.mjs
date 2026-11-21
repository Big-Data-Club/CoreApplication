export async function indexPageLinks(client, pageId, xml) {
  const pattern =
    /(?:pageId="|\/workspace\?page=)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi;
  const targets = [
    ...new Set(
      [...xml.matchAll(pattern)].map((match) => match[1].toLowerCase()),
    ),
  ].slice(0, 1000);
  await client.query("DELETE FROM page_links WHERE source_id=$1", [pageId]);
  if (targets.length)
    await client.query(
      "INSERT INTO page_links(source_id,target_id) SELECT $1,unnest($2::uuid[]) ON CONFLICT DO NOTHING",
      [pageId, targets],
    );
}
