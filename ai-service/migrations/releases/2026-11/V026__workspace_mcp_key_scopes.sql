ALTER TABLE mcp_api_keys
    DROP CONSTRAINT mcp_api_keys_scopes_valid,
    ADD CONSTRAINT mcp_api_keys_scopes_valid CHECK (
        scopes <@ ARRAY['read', 'write']::TEXT[]
        OR (scopes <@ ARRAY['workspace:read', 'workspace:create']::TEXT[]
            AND 'workspace:read' = ANY(scopes))
    );
