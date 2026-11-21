-- Favoriting an unopened page must not create a fictitious visit.
ALTER TABLE page_preferences ALTER COLUMN opened_at DROP NOT NULL;
CREATE INDEX page_preferences_user_recent ON page_preferences(user_id,opened_at DESC,page_id) WHERE opened_at IS NOT NULL;
CREATE INDEX pages_library_updated ON pages(updated_at DESC,id) WHERE archived_at IS NULL;
