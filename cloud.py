"""Request-scoped operations for Vercel. Durable state lives in Supabase."""
import csv
import io
import json
from urllib.parse import urlparse
from server import App, LABELS

class CloudApp(App):
    def __init__(self, **kwargs):
        config = kwargs.get('config') or {}
        if not config.get('SUPABASE_DB_URL'):
            raise ValueError('Configurer SUPABASE_DB_URL dans Vercel.')
        super().__init__(**kwargs)

    @staticmethod
    def serialize(row):
        result = App.serialize(row)
        url = urlparse(result.get('image_url',''))
        valid = url.scheme=='https' and url.hostname=='medias.trendtrack.io' and not url.username and url.port in (None,443)
        result['display_image'] = result['image_url'] if valid else ''
        result['has_image'] = bool(result['display_image'])
        return result

    def board(self, query):
        result = super().board(dict(query,limit=['25']))
        result['settings'].update(cloud=True, page_size=25)
        for rows in result['columns'].values():
            for row in rows:
                row['raw'] = row['raw'][:1500]
                if row['analysis']:
                    for key,value in row['analysis'].items():
                        if isinstance(value,str): row['analysis'][key]=value[:1500]
        return result

    def import_all(self):
        # The Mac's collector writes to Supabase. Vercel never scans local files.
        return None

    def save_settings(self, body):
        raise ValueError('Sur Vercel, configure MISTRAL_API_KEY et MISTRAL_MODEL dans Settings → Environment Variables, puis redéploie.')

    def candidates(self, body):
        limit = int(body.get('limit',1))
        if limit not in (1,10,25,100): raise ValueError('Taille de lot invalide.')
        return {'rows':[{'id':r['id'],'revision':r['revision']} for r in self.pending_ads(limit)]}

    def analyze_one(self, body):
        if not self.config().get('MISTRAL_API_KEY'): raise ValueError('Configure MISTRAL_API_KEY dans Vercel.')
        ident, revision = body.get('id'), body.get('revision')
        if not isinstance(ident,str) or len(ident)>100 or type(revision) is not int:
            raise ValueError('Annonce invalide.')
        try:
            done = self.analyze_row({'id':ident,'revision':revision},self.config())
            return {'done':done}
        except (ValueError,RuntimeError) as exc:
            # No automatic retry of a possibly billed request.
            message = str(exc)
            with self.connect() as db:
                db.execute('UPDATE ads SET error=? WHERE id=? AND revision=?',(message,ident,revision))
            raise

    def export_page(self, query):
        # Keyset pagination stays stable while the local scraper appends ads.
        after_time = float(query.get('after_time',['-1'])[0])
        after_id = query.get('after_id',[''])[0]
        with self.connect() as db:
            rows = db.execute('SELECT * FROM ads WHERE created>? OR (created=? AND id>?) ORDER BY created,id LIMIT 100',
                              (after_time,after_time,after_id)).fetchall()
        out = io.StringIO(); writer = csv.writer(out,delimiter=';')
        if after_time == -1:
            writer.writerow(['id','texte_annonce','couverture','texte_nettoye','micro_niche','consommable','service','potentiel E-Commerce','statut','commentaire','mot_cle_1','mot_cle_2','mot_cle_3','liens_concurrents'])
        for row in rows:
            a=json.loads(row['analysis'] or '{}')
            values=[row['id'],row['raw'],row['reach'],a.get('texte_nettoye',''),a.get('micro_niche',''),a.get('consommable',''),a.get('service',''),a.get('potentiel_ecommerce',''),LABELS[row['stage']],a.get('commentaire','')]
            keywords=json.loads(dict(row).get('search_keywords') or '[]'); values+=(keywords+['','',''])[:3]
            values.append('\n'.join(json.loads(dict(row).get('competitor_links') or '[]')))
            writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in values])
        cursor = {'after_time':rows[-1]['created'],'after_id':rows[-1]['id']} if len(rows)==100 else None
        return {'csv':out.getvalue(),'next':cursor}
