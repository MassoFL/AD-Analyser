BEGIN;
ALTER TABLE ad_pipeline.ads ADD COLUMN IF NOT EXISTS competitor_links TEXT NOT NULL DEFAULT '[]'
  CHECK (jsonb_typeof(competitor_links::jsonb)='array');
INSERT INTO ad_pipeline.schema_migrations VALUES(3) ON CONFLICT DO NOTHING;
COMMIT;
