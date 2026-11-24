CREATE TABLE workspace_mcp_page_requests (
  user_id text NOT NULL REFERENCES workspace_users(id) ON DELETE CASCADE,
  request_id uuid NOT NULL,
  payload_hash text NOT NULL,
  page_id uuid REFERENCES pages(id) ON DELETE SET NULL,
  PRIMARY KEY (user_id, request_id)
);

CREATE INDEX workspace_mcp_page_requests_page_idx ON workspace_mcp_page_requests(page_id);
