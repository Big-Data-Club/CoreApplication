ALTER TABLE pages ADD COLUMN cover_image_id uuid REFERENCES attachments(id) ON DELETE SET NULL;
