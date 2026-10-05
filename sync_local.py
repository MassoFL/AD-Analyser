"""Keep this collector running on the Mac while scraping for the Vercel dashboard."""
import time
from server import App

if __name__ == '__main__':
    app = App()
    if not app.storage.remote:
        raise SystemExit('Configure SUPABASE_DB_URL dans .env.')
    print('Collecteur connecté à Supabase. Ctrl+C pour arrêter.',flush=True)
    try:
        while True:
            app.import_all()
            if app.import_info['error']: print(app.import_info['error'],flush=True)
            elif app.import_info['added']: print(str(app.import_info['added'])+' nouvelles annonces envoyées.',flush=True)
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        app.storage.close()
