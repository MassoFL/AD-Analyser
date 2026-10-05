import subprocess
import sys
import time
import webbrowser
from urllib.request import urlopen
from pathlib import Path
from server import env_file

root=Path(__file__).resolve().parent
port=int(env_file().get('PORT',8765))
url=f'http://127.0.0.1:{port}'
def ready():
    try:
        with urlopen(url+'/api/board',timeout=1) as r:
            return b'"columns"' in r.read()
    except Exception:
        return False
if ready():
    webbrowser.open(url)
else:
    process=subprocess.Popen([sys.executable,str(root/'server.py'),'--port',str(port)],cwd=root)
    try:
        for _ in range(60):
            if ready():
                webbrowser.open(url);break
            if process.poll() is not None: raise RuntimeError('Le pipeline n’a pas pu démarrer.')
            time.sleep(0.5)
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
