"""Run explicitly with RUN_SUPABASE_TESTS=1; all writes use temporary tables."""
from contextlib import contextmanager
import os
import unittest
import test_pipeline
from server import env_file
from database import Database, PostgresConnection


class TemporaryPostgres:
    remote = True

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def connect(self):
        with self.connection.transaction():
            yield PostgresConnection(self.connection)


@unittest.skipUnless(os.environ.get('RUN_SUPABASE_TESTS') == '1', 'Supabase integration opt-in')
class SupabaseTest(test_pipeline.PipelineTest):
    def setUp(self):
        super().setUp()
        self.remote = Database(self.app.db, env_file())
        self.conn = self.remote.pool.getconn()
        self.conn.execute('SET search_path TO pg_temp, ad_pipeline, pg_catalog')
        self.conn.execute('CREATE TEMP TABLE ads (LIKE ad_pipeline.ads INCLUDING ALL)')
        self.conn.execute('CREATE TEMP TABLE imports (LIKE ad_pipeline.imports INCLUDING ALL)')
        self.app.storage = TemporaryPostgres(self.conn)

    def tearDown(self):
        self.conn.rollback()
        self.remote.pool.putconn(self.conn)
        self.remote.close()
        super().tearDown()

    def test_batch_dedup_and_board_filters(self):
        source = str(self.run/'annonces.jsonl')
        rows = [{'texte_annonce':'Lampe 100% sûre','couverture':'10M'}]*2
        self.assertEqual(self.app.ingest_many(rows,source),1)
        self.assertEqual(self.app.ingest_many(rows,source),0)
        self.assertEqual(self.app.board({'q':['100%']})['counts']['inbox'],1)
        self.assertEqual(self.app.board({'q':['100_']})['counts']['inbox'],0)
        self.assertEqual(self.app.board({'potential':['oui']})['counts']['inbox'],0)

    def test_timestamp_precision_survives_remote_round_trip(self):
        value = 1791234567.1234567
        with self.remote.connect() as db:
            result = db.execute('SELECT ?::float8 AS value', (value,)).fetchone()
        self.assertEqual(result['value'], value)
