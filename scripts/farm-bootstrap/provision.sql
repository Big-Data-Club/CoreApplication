\getenv farm_user FARM_DB_USER
\getenv farm_password FARM_DB_PASSWORD
-- Never rotate a role password during deployment: pending events and live pods
-- must continue to work. A conflicting existing role fails the connection check.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'farm_user', :'farm_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'farm_user') \gexec
SELECT format('GRANT %I TO %I', :'farm_user', current_user)
WHERE :'farm_user' <> current_user \gexec
SELECT format('CREATE DATABASE gamefarm OWNER %I', :'farm_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gamefarm') \gexec

SELECT datdba = (SELECT oid FROM pg_roles WHERE rolname = :'farm_user') AS correct_owner
FROM pg_database WHERE datname = 'gamefarm' \gset
\if :correct_owner
\else
DO $$ BEGIN RAISE EXCEPTION 'Existing gamefarm database has another owner; explicit migration required'; END $$;
\endif
