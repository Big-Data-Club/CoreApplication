ALTER TABLE websocket_tickets ADD COLUMN identity_expires_at timestamptz NOT NULL DEFAULT (now()+interval '1 hour');
