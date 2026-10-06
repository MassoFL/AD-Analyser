import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import App, validate_analysis, ask_mistral

def analysis(**kwargs):
    a={'texte_nettoye':'Lampe rechargeable','micro_niche':'Lampes rechargeables',
       'consommable':'non','service':'non','niche_claire':True,'a_verifier':False,'commentaire':''}
    a.update(kwargs)
    return validate_analysis(a)

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.exports=self.root/'exports'
        self.run=self.exports/'run'; self.run.mkdir(parents=True)
        self.app=App(self.root/'data',{'SCRAPER_EXPORT_DIR':str(self.exports),'MISTRAL_API_KEY':'fake-test-key'})
    def tearDown(self): self.tmp.cleanup()
    def rows(self):
        with self.app.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM ads ORDER BY created')]
    def insert(self,text='Lampe rechargeable',**kwargs):
        return self.app.ingest({'texte_annonce':text,'couverture':'10M',**kwargs},str(self.run/'annonces.jsonl'))
    def test_import_dedup_and_preserve_decision(self):
        self.assertEqual(self.insert(),1)
        row=self.rows()[0]
        self.app.update(row['id'],{'revision':0,'stage':'kept','analysis':analysis()})
        self.assertEqual(self.insert(),0)
        updated=self.rows()[0]
        self.assertEqual(updated['stage'],'kept')
        self.assertEqual(json.loads(updated['analysis'])['micro_niche'],'Lampes rechargeables')
        with self.assertRaises(ValueError): self.app.update(row['id'],{'revision':0,'stage':'rejected'})
    def test_image_upgrade_keeps_record_then_distinct_images(self):
        self.insert()
        original=self.rows()[0]['id']
        (self.run/'images').mkdir(); (self.run/'images'/'one.png').write_bytes(b'test')
        self.assertEqual(self.insert(image_url='https://medias.trendtrack.io/google/one.png',image_path='images/one.png'),0)
        self.assertEqual(self.rows()[0]['id'],original)
        self.assertTrue(self.rows()[0]['image_path'])
        self.assertEqual(self.insert(image_url='https://medias.trendtrack.io/google/one.png'),0)
        self.assertEqual(self.insert(image_url='https://medias.trendtrack.io/google/two.png'),1)
        self.assertEqual(len(self.rows()),2)
    def test_jsonl_partial_line_and_csv_not_double_imported(self):
        record={'texte_annonce':'Un bracelet','couverture':'10M','image_url':'https://medias.trendtrack.io/google/one.png'}
        path=self.run/'annonces.jsonl'
        path.write_text(json.dumps(record)+'\n'+json.dumps({'texte_annonce':'Une montre','couverture':'2M'}))
        (self.run/'annonces.csv').write_text('texte_annonce;couverture\nAutre;10M\n')
        self.app.import_all();self.assertEqual(len(self.rows()),1)
        with path.open('a') as f:f.write('\n')
        self.app.import_all();self.assertEqual(len(self.rows()),2)
    def test_reject_image_outside_exports(self):
        outside=self.root/'secret.txt';outside.write_text('not an image')
        self.insert(image_path=str(outside))
        self.assertEqual(self.rows()[0]['image_path'],'')
    def test_potential_conditions_and_validation(self):
        self.assertEqual(analysis()['potentiel_ecommerce'],'oui')
        for changes in ({'consommable':'oui'},{'consommable':'indéterminé'},{'service':'oui'},{'service':'indéterminé'},{'niche_claire':False},{'micro_niche':'indéterminée'}):
            self.assertEqual(analysis(**changes)['potentiel_ecommerce'],'non')
        with self.assertRaises(ValueError): analysis(service='maybe')
        with self.assertRaises(ValueError): analysis(niche_claire='true')
    def test_mistral_contract_text_only_and_job_transition(self):
        class FakeResponse(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        result={'choices':[{'message':{'content':json.dumps(analysis())}}]}
        with patch('server.urlopen',return_value=FakeResponse(json.dumps(result).encode())) as request:
            answer=ask_mistral('Lampe rechargeable',self.app.config())
            payload=json.loads(request.call_args[0][0].data)
            self.assertEqual(payload['response_format'],{'type':'json_object'})
            self.assertNotIn('image_url',str(payload))
            self.assertEqual(answer['potentiel_ecommerce'],'oui')
        self.insert()
        self.app.job={'running':True,'total':1,'done':0,'failed':0,'error':''}
        with patch('server.ask_mistral',return_value=analysis()):self.app.run_job(self.rows(),self.app.config())
        self.assertEqual(self.rows()[0]['stage'],'review')
        self.assertEqual(self.app.job['done'],1)
    def test_api_failure_keeps_ad_and_stops_batch(self):
        self.insert();self.insert('Autre annonce')
        self.app.job={'running':True,'total':2,'done':0,'failed':0,'error':''}
        with patch('server.ask_mistral',side_effect=RuntimeError('Clé Mistral refusée.')) as call:
            self.app.run_job(self.rows(),self.app.config())
        self.assertEqual(call.call_count,1)
        self.assertTrue(all(r['stage']=='inbox' for r in self.rows()))
        self.assertFalse(self.app.job['running'])
    def test_manual_change_wins_over_inflight_analysis(self):
        self.insert(); row=self.rows()[0]
        self.app.job={'running':True,'total':1,'done':0,'failed':0,'error':''}
        def manual_during_request(*args):
            self.app.update(row['id'],{'revision':0,'stage':'rejected'})
            return analysis()
        with patch('server.ask_mistral',side_effect=manual_during_request):self.app.run_job([row],self.app.config())
        self.assertEqual(self.rows()[0]['stage'],'rejected')
        self.assertIsNone(self.rows()[0]['analysis'])
    def test_recent_decisions_appear_first_in_destination(self):
        self.insert('Ancienne annonce'); self.insert('Annonce récente')
        old,new=self.rows()
        self.app.update(new['id'],{'revision':0,'stage':'kept'})
        self.app.update(old['id'],{'revision':0,'stage':'kept'})
        self.assertEqual(self.app.board({})['columns']['kept'][0]['id'],old['id'])

    def test_potential_filter_only_applies_to_review(self):
        for text in ('Pending','Review yes','Review no','Kept','Rejected'):
            self.insert(text)
        rows={row['raw']:row for row in self.rows()}
        for text,stage,consumable in [('Review yes','review','non'),('Review no','review','oui'),('Kept','kept','oui'),('Rejected','rejected','non')]:
            self.app.update(rows[text]['id'],{'revision':0,'stage':stage,'analysis':analysis(consommable=consumable)})
        for potential,expected in [('oui','Review yes'),('non','Review no')]:
            board=self.app.board({'potential':[potential]})
            self.assertEqual(board['counts'],{'inbox':1,'review':1,'kept':1,'rejected':1})
            self.assertEqual(board['columns']['review'][0]['raw'],expected)
            self.assertEqual(board['columns']['inbox'][0]['raw'],'Pending')
            self.assertEqual(len(board['columns']['kept']),1)
            self.assertEqual(len(board['columns']['rejected']),1)
            self.assertEqual(board['totals']['review'],2)

    def test_board_never_exposes_api_key(self):
        self.assertNotIn('fake-test-key',json.dumps(self.app.board({})))

if __name__=='__main__': unittest.main()
