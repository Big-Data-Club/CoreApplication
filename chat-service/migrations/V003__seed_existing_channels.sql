-- Seed Read/Write roles for all existing public channels that might be missing them
INSERT INTO chat_channel_roles (channel_id, role_name, can_read, can_write)
SELECT c.id, r.role_name, true, true
FROM chat_channels c
CROSS JOIN (
    VALUES ('ADMIN'), ('TEACHER'), ('STUDENT')
) AS r(role_name)
WHERE c.is_private = false AND c.is_dm = false
ON CONFLICT (channel_id, role_name) DO NOTHING;
