"""Vercel entry point: no background thread, local import or writable database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud import CloudApp
from server import env_file, make_handler

config = env_file()
config['VERCEL'] = '1'
if not config.get('SUPABASE_SSLROOTCERT'):
    config['SUPABASE_SSLROOTCERT'] = 'certs/supabase-ca.crt'

class RequestApp:
    """Connect only after HTTP authentication, then release all DB resources."""
    def __init__(self): self.instance = None
    def __getattr__(self, name):
        if self.instance is None: self.instance = CloudApp(config=config)
        return getattr(self.instance, name)
    def close(self):
        if self.instance is not None: self.instance.storage.close()

class handler(make_handler(None, cloud=True, config=config)):
    def __init__(self, *args, **kwargs):
        self.application = RequestApp()
        try:
            super().__init__(*args, **kwargs)
        finally:
            self.application.close()
