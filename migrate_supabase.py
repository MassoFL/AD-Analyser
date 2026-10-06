#!/usr/bin/env python3
"""Copy a consistent SQLite snapshot into Supabase, without replacing remote edits."""
import argparse
from datetime import datetime
from pathlib import Path
import sqlite3
from database import Database, DatabaseError
from server import ROOT, env_file

COLUMNS = ('id','text_hash','raw','reach','image_url','image_path','source','stage',
           'analysis','analyst','error','revision','created','updated','search_keywords','competitor_links')


def migrate(source, config):
    if not config.get('SUPABASE_DB_URL'):
        raise ValueError('Renseigne SUPABASE_DB_URL dans .env avant de migrer.')
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('Base SQLite source introuvable.')
    storage = Database(source, config)
    backup_dir = ROOT / 'data' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / ('before-supabase-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    try:
        with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as original:
            with sqlite3.connect(backup) as snapshot:
                original.backup(snapshot)
        backup.chmod(0o600)
        local = sqlite3.connect(backup)
        try:
            available = {r[1] for r in local.execute('PRAGMA table_info(ads)')}
            selection = ','.join(c if c in available else "'[]' AS "+c for c in COLUMNS)
            rows = local.execute('SELECT '+selection+' FROM ads ORDER BY created,id').fetchall()
            imports = local.execute('SELECT name FROM imports').fetchall()
        finally:
            local.close()
        with storage.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext('ad-pipeline-ingest'))")
            before = {r['id'] for r in db.execute('SELECT id FROM ads')}
            sql = 'INSERT INTO ads('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+') ON CONFLICT DO NOTHING'
            db.executemany(sql, rows)
            # Verify inserted content before committing the migration.
            remote = {r['id']:dict(r) for r in db.execute('SELECT '+','.join(COLUMNS)+' FROM ads')}
            for row in rows:
                if row[0] not in remote:
                    raise ValueError('Conflit de visuel : migration annulée, aucune donnée distante remplacée.')
                if row[0] not in before and tuple(remote[row[0]][c] for c in COLUMNS) != row:
                    fields = [c for i,c in enumerate(COLUMNS) if remote[row[0]][c] != row[i]]
                    raise ValueError('Vérification de migration échouée : transaction annulée. Champs : '+','.join(fields))
            if imports:
                db.executemany('INSERT INTO imports(name) VALUES(?) ON CONFLICT DO NOTHING', imports)
        return {'source_rows':len(rows), 'inserted':sum(row[0] not in before for row in rows),
                'preserved_remote':sum(row[0] in before for row in rows), 'backup':str(backup)}
    finally:
        storage.close()


if __name__ == '__main__':
    import json
    import os
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(ROOT/'data'/'pipeline.sqlite3'))
    args = parser.parse_args()
    try:
        print(json.dumps(migrate(args.source, env_file()), ensure_ascii=False))
    except (ValueError, DatabaseError, sqlite3.Error, OSError) as exc:
        raise SystemExit(str(exc)) from None
