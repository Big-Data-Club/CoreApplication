CREATE TABLE page_links (
  source_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  target_id uuid NOT NULL,
  PRIMARY KEY(source_id,target_id)
);
CREATE INDEX page_links_target_idx ON page_links(target_id);
