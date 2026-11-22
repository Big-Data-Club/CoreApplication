ALTER TABLE legacy_note_imports ADD COLUMN space_id uuid REFERENCES spaces(id);
UPDATE legacy_note_imports i SET space_id=p.space_id FROM pages p WHERE p.id=i.page_id;
ALTER TABLE legacy_note_imports ALTER COLUMN space_id SET NOT NULL;
ALTER TABLE legacy_note_imports DROP CONSTRAINT legacy_note_imports_pkey;
ALTER TABLE legacy_note_imports ADD PRIMARY KEY(user_id,note_id,space_id);
