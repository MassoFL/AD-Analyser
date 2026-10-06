BEGIN;
ALTER TABLE ad_pipeline.ads ADD COLUMN IF NOT EXISTS search_keywords TEXT NOT NULL DEFAULT '[]'
  CHECK (jsonb_typeof(search_keywords::jsonb)='array' AND jsonb_array_length(search_keywords::jsonb)<=3);
INSERT INTO ad_pipeline.schema_migrations VALUES(2) ON CONFLICT DO NOTHING;
COMMIT;
