-- Run in the Supabase SQL Editor as postgres. No password is stored here.
-- The private schema is not exposed through the Data API.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ad_pipeline_app') THEN
    CREATE ROLE ad_pipeline_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS ad_pipeline;
REVOKE ALL ON SCHEMA ad_pipeline FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA ad_pipeline TO ad_pipeline_app;

CREATE TABLE IF NOT EXISTS ad_pipeline.ads (
  id TEXT PRIMARY KEY,
  text_hash TEXT NOT NULL,
  raw TEXT NOT NULL,
  reach TEXT NOT NULL,
  image_url TEXT NOT NULL DEFAULT '',
  image_path TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'inbox' CHECK (stage IN ('inbox','review','kept','rejected')),
  analysis TEXT CHECK (analysis IS NULL OR jsonb_typeof(analysis::jsonb)='object'),
  analyst TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 0 CHECK (revision>=0),
  created DOUBLE PRECISION NOT NULL,
  updated DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ads_stage_created ON ad_pipeline.ads(stage, created, id);
CREATE INDEX IF NOT EXISTS idx_ads_text_hash ON ad_pipeline.ads(text_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ads_image_url ON ad_pipeline.ads(image_url) WHERE image_url!='';
CREATE TABLE IF NOT EXISTS ad_pipeline.imports (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS ad_pipeline.schema_migrations (version INTEGER PRIMARY KEY);
INSERT INTO ad_pipeline.schema_migrations VALUES(1) ON CONFLICT DO NOTHING;

ALTER TABLE ad_pipeline.ads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_pipeline.imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_pipeline.schema_migrations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA ad_pipeline FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON ad_pipeline.ads TO ad_pipeline_app;
GRANT SELECT, INSERT ON ad_pipeline.imports TO ad_pipeline_app;
GRANT SELECT ON ad_pipeline.schema_migrations TO ad_pipeline_app;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='ad_pipeline' AND tablename='ads' AND policyname='pipeline_server') THEN
    CREATE POLICY pipeline_server ON ad_pipeline.ads TO ad_pipeline_app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='ad_pipeline' AND tablename='imports' AND policyname='pipeline_server') THEN
    CREATE POLICY pipeline_server ON ad_pipeline.imports TO ad_pipeline_app USING (true) WITH CHECK (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='ad_pipeline' AND tablename='schema_migrations' AND policyname='pipeline_server') THEN
    CREATE POLICY pipeline_server ON ad_pipeline.schema_migrations FOR SELECT TO ad_pipeline_app USING (true);
  END IF;
END $$;
COMMIT;
