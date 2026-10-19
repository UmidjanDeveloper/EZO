-- Owner-reviewed setup for a NEW, dedicated EZO Supabase project.
-- Run as the project administrator in SQL Editor. No password belongs in this file.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ezo_app') THEN
    CREATE ROLE ezo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20;
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO ezo_app', current_database());
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'extensions') THEN
    GRANT USAGE ON SCHEMA extensions TO ezo_app;
  END IF;
END $$;
GRANT USAGE, CREATE ON SCHEMA public TO ezo_app;
ALTER ROLE ezo_app SET search_path TO public, extensions;
-- Set a strong password in the protected database-role UI.
-- The app needs DDL on its own objects because startup applies migrations.
-- This does not transfer existing objects owned by postgres; never run on a shared DB.
