import http.client
import json
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from cloud import CloudApp
from server import App, make_handler
import test_pipeline


class VercelTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=App(Path(self.tmp.name),{'MISTRAL_API_KEY':'test-key'})
        self.app.__class__=CloudApp  # SQLite fixture; no external data changed.
        self.config={'SUPABASE_DB_URL':'postgresql://fixture-secret'}
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app,cloud=True,config=self.config))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path='/',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers or {})
        response=connection.getresponse();result=response.status,response.read();connection.close();return result

    def test_site_opens_without_credentials_and_keeps_csrf(self):
        status,html=self.request()
        self.assertEqual(status,200)
        token=re.search(b'name="pipeline-token" content="([^"]+)"',html).group(1).decode()
        self.assertNotIn(b'fixture-secret',html)
        self.assertEqual(self.request('/app.js')[0],200)
        self.assertEqual(self.request('/api/board')[0],200)
        self.assertEqual(self.request('/api/sync',{})[0],403)
        self.assertEqual(self.request('/api/sync',{}, {'X-Pipeline-Token':token})[0],200)
        self.assertEqual(self.request('/.env')[0],404)

    def test_legacy_password_configuration_does_not_prompt(self):
        handler=make_handler(self.app,cloud=True,config={'PIPELINE_PASSWORD':'legacy'})
        with patch.object(self.server,'RequestHandlerClass',handler):
            self.assertEqual(self.request()[0],200)

    def test_no_file_settings_or_missing_database_fallback(self):
        with self.assertRaises(ValueError):self.app.save_settings({'key':'should-not-write'})
        with self.assertRaises(ValueError):CloudApp(config={})

    def test_sync_analysis_is_idempotent(self):
        self.app.ingest({'texte_annonce':'Lampe','couverture':'1M'},'fixture')
        row=self.app.candidates({'limit':1})['rows'][0]
        with patch('server.ask_mistral',return_value=test_pipeline.analysis()) as call:
            self.assertEqual(self.app.analyze_one(row),{'done':1})
            self.assertEqual(self.app.analyze_one(row),{'done':0})
            self.assertEqual(call.call_count,1)
        self.assertEqual(self.app.board({})['totals']['review'],1)

    def test_cloud_images_only_use_trusted_https_origin(self):
        self.app.ingest({'texte_annonce':'Lampe','couverture':'1M','image_url':'https://evil.test/image.png'},'fixture')
        row=self.app.board({})['columns']['inbox'][0]
        self.assertFalse(row['has_image'])
        self.assertEqual(row['display_image'],'')

    def test_export_and_board_pagination(self):
        self.app.ingest_many([{'texte_annonce':'Produit '+str(i),'couverture':'1M'} for i in range(105)],'fixture')
        first=self.app.board({});second=self.app.board({'offset_inbox':['25']})
        self.assertEqual(len(first['columns']['inbox']),25)
        self.assertNotEqual(first['columns']['inbox'][0]['id'],second['columns']['inbox'][0]['id'])
        first=self.app.export_page({})
        second=self.app.export_page({k:[str(v)] for k,v in first['next'].items()})
        self.assertEqual(len(first['csv'].splitlines()),101)
        self.assertEqual(len(second['csv'].splitlines()),5)
        self.assertIsNone(second['next'])

    def test_blank_ocr_does_not_starve_candidates(self):
        blanks=['', ' ', '\n\t', '\u00a0', '\u2003']*25
        self.app.ingest_many([{'texte_annonce':text,'couverture':'1M'} for text in blanks]+[{'texte_annonce':'Lampe rechargeable','couverture':'1M'}], 'fixture')
        rows=self.app.candidates({'limit':100})['rows']
        self.assertEqual(len(rows),1)
        with patch('server.ask_mistral',return_value=test_pipeline.analysis()) as call:
            self.assertEqual(self.app.analyze_one(rows[0]),{'done':1})
            self.assertEqual(call.call_count,1)

    def test_direct_empty_ocr_is_skipped_without_mistral(self):
        self.app.ingest({'texte_annonce':'\n\t','couverture':'1M'},'fixture')
        with self.app.connect() as db:
            row=db.execute('SELECT id,revision FROM ads').fetchone()
        with patch('server.ask_mistral') as call:
            self.assertEqual(self.app.analyze_one(dict(row)),{'done':0})
            call.assert_not_called()
        self.assertEqual(self.app.candidates({'limit':100})['rows'],[])
