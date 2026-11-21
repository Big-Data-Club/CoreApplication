CREATE TABLE workspace_users (
  id text PRIMARY KEY,
  email text NOT NULL UNIQUE,
  name text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE spaces (
  id uuid PRIMARY KEY,
  title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
  kind text NOT NULL CHECK (kind IN ('personal','team')),
  owner_id text NOT NULL REFERENCES workspace_users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX spaces_one_personal ON spaces(owner_id) WHERE kind='personal';
CREATE TABLE space_members (
  space_id uuid NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES workspace_users(id),
  role text NOT NULL CHECK (role IN ('viewer','commenter','editor','manager','owner')),
  PRIMARY KEY(space_id,user_id)
);
CREATE TABLE pages (
  id uuid PRIMARY KEY,
  space_id uuid NOT NULL REFERENCES spaces(id),
  parent_id uuid,
  title text NOT NULL DEFAULT 'Trang không tiêu đề' CHECK (length(title) BETWEEN 1 AND 300),
  icon text NOT NULL DEFAULT '',
  cover text NOT NULL DEFAULT '',
  full_width boolean NOT NULL DEFAULT false,
  kind text NOT NULL DEFAULT 'page' CHECK (kind IN ('page','database','record')),
  properties jsonb NOT NULL DEFAULT '{}',
  sources jsonb NOT NULL DEFAULT '[]',
  initial_markdown text NOT NULL DEFAULT '',
  version integer NOT NULL DEFAULT 1,
  sort_order double precision NOT NULL DEFAULT 0,
  archived_batch uuid,
  archived_at timestamptz,
  created_by text NOT NULL REFERENCES workspace_users(id),
  updated_by text NOT NULL REFERENCES workspace_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,space_id),
  FOREIGN KEY(parent_id,space_id) REFERENCES pages(id,space_id),
  CHECK(parent_id IS NULL OR parent_id<>id)
);
CREATE INDEX pages_tree ON pages(space_id,parent_id,sort_order) WHERE archived_at IS NULL;
CREATE INDEX pages_records ON pages(parent_id,updated_at DESC) WHERE kind='record' AND archived_at IS NULL;
CREATE TABLE page_grants (
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES workspace_users(id),
  role text NOT NULL CHECK (role IN ('viewer','commenter','editor','manager')),
  PRIMARY KEY(page_id,user_id)
);
CREATE TABLE page_documents (
  page_id uuid PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
  state bytea NOT NULL DEFAULT ''::bytea,
  revision bigint NOT NULL DEFAULT 0,
  generation integer NOT NULL DEFAULT 1,
  search_text text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_search ON page_documents USING gin(to_tsvector('simple',search_text));
CREATE TABLE document_operations (
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  operation_id uuid NOT NULL,
  generation integer NOT NULL,
  revision bigint NOT NULL,
  author_id text NOT NULL REFERENCES workspace_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(page_id,operation_id)
);
CREATE TABLE page_preferences (
  page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  user_id text NOT NULL REFERENCES workspace_users(id),
  favorite boolean NOT NULL DEFAULT false,
  opened_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(page_id,user_id)
);
CREATE TABLE invitations (
  id uuid PRIMARY KEY,
  space_id uuid REFERENCES spaces(id) ON DELETE CASCADE,
  page_id uuid REFERENCES pages(id) ON DELETE CASCADE,
  email text NOT NULL,
  role text NOT NULL CHECK (role IN ('viewer','commenter','editor','manager')),
  created_by text NOT NULL REFERENCES workspace_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now()+interval '7 days',
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','declined','cancelled')),
  CHECK ((space_id IS NULL)<>(page_id IS NULL))
);
CREATE UNIQUE INDEX invites_pending_space ON invitations(space_id,email) WHERE status='pending';
CREATE UNIQUE INDEX invites_pending_page ON invitations(page_id,email) WHERE status='pending';
CREATE TABLE comments (
  id uuid PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES pages(id),
  block_id text,
  parent_id uuid REFERENCES comments(id),
  author_id text NOT NULL REFERENCES workspace_users(id),
  body text NOT NULL CHECK(length(body) BETWEEN 1 AND 10000),
  resolved boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX comments_page ON comments(page_id,created_at);
CREATE TABLE page_versions (
  id uuid PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES pages(id),
  author_id text NOT NULL REFERENCES workspace_users(id),
  title text NOT NULL,
  label text NOT NULL,
  state bytea NOT NULL,
  properties jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX versions_page ON page_versions(page_id,created_at DESC);
CREATE TABLE database_schemas (
  page_id uuid PRIMARY KEY REFERENCES pages(id),
  fields jsonb NOT NULL DEFAULT '[]',
  version integer NOT NULL DEFAULT 1
);
CREATE TABLE database_views (
  id uuid PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES pages(id),
  owner_id text REFERENCES workspace_users(id),
  name text NOT NULL,
  type text NOT NULL CHECK(type IN ('table','board','calendar','list','gallery','timeline')),
  config jsonb NOT NULL DEFAULT '{}',
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE attachments (
  id uuid PRIMARY KEY,
  uploaded_by text NOT NULL REFERENCES workspace_users(id),
  filename text NOT NULL,
  mime text NOT NULL,
  content bytea NOT NULL,
  size integer NOT NULL CHECK(size>0 AND size<=10485760),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE attachment_bindings (
  attachment_id uuid NOT NULL REFERENCES attachments(id),
  page_id uuid NOT NULL REFERENCES pages(id),
  PRIMARY KEY(attachment_id,page_id)
);
CREATE TABLE workspace_activity (
  id uuid PRIMARY KEY,
  space_id uuid NOT NULL REFERENCES spaces(id),
  page_id uuid REFERENCES pages(id),
  actor_id text NOT NULL REFERENCES workspace_users(id),
  action text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE workspace_notifications (
  id uuid PRIMARY KEY,
  user_id text NOT NULL REFERENCES workspace_users(id),
  page_id uuid REFERENCES pages(id),
  kind text NOT NULL,
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE websocket_tickets (
  digest text PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES pages(id),
  user_id text NOT NULL REFERENCES workspace_users(id),
  expires_at timestamptz NOT NULL
);
CREATE TABLE legacy_note_imports (
  user_id text NOT NULL REFERENCES workspace_users(id),
  note_id text NOT NULL,
  page_id uuid NOT NULL REFERENCES pages(id),
  PRIMARY KEY(user_id,note_id)
);
