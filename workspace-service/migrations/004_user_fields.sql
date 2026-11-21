CREATE TABLE workspace_fields (
  id uuid PRIMARY KEY,
  space_id uuid NOT NULL REFERENCES spaces(id),
  title text NOT NULL CHECK(length(title) BETWEEN 1 AND 120),
  description text NOT NULL DEFAULT '' CHECK(length(description)<=280),
  icon text NOT NULL DEFAULT 'book',
  color text NOT NULL DEFAULT 'violet',
  tags jsonb NOT NULL DEFAULT '[]',
  version integer NOT NULL DEFAULT 1,
  archived_at timestamptz,
  archived_batch uuid,
  created_by text NOT NULL REFERENCES workspace_users(id),
  updated_by text NOT NULL REFERENCES workspace_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,space_id)
);
CREATE INDEX workspace_fields_space ON workspace_fields(space_id,created_at);
ALTER TABLE pages ADD COLUMN field_id uuid;
ALTER TABLE pages ADD CONSTRAINT pages_field_space_fk FOREIGN KEY(field_id,space_id) REFERENCES workspace_fields(id,space_id);
ALTER TABLE pages ADD CONSTRAINT pages_field_parent_unique UNIQUE(id,space_id,field_id);
ALTER TABLE pages ADD CONSTRAINT pages_field_parent_fk FOREIGN KEY(parent_id,space_id,field_id) REFERENCES pages(id,space_id,field_id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX pages_field_tree ON pages(field_id,parent_id,sort_order) WHERE archived_at IS NULL;
-- Existing pages intentionally remain unfiled. No fields are seeded or auto-assigned.
