-- V007__add_organization_to_users.sql
-- Add organization column to users table in LMS DB
ALTER TABLE users ADD COLUMN IF NOT EXISTS organization VARCHAR(255);
