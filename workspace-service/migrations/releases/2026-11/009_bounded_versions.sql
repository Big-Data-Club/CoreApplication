CREATE INDEX page_versions_retention ON page_versions(page_id,created_at DESC,id DESC);
-- Product policy: retain only the four newest snapshots of each page.
WITH ranked AS (
  SELECT id,row_number() OVER(PARTITION BY page_id ORDER BY created_at DESC,id DESC) position
  FROM page_versions
)
DELETE FROM page_versions WHERE id IN(SELECT id FROM ranked WHERE position>4);
