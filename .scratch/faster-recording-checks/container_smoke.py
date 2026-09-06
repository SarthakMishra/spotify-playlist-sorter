"""Run inside the built image with Docker networking disabled and no mounted credentials."""
import os
import subprocess
import time
import urllib.request

import numpy as np

from api.audio_analysis import analyze_audio
from api.youtube import access_status

state = access_status(None)
assert state['node_available'] and state['scripts_available']
assert state['server_source'] == 'anonymous'
assert os.getuid() != 0
assert analyze_audio(np.zeros(22050, dtype=np.float32))['duration'] == 1
print('Node:', subprocess.check_output(['node', '--version'], text=True).strip())
print('Runtime UID:', os.getuid())
server = subprocess.Popen(
    ['uvicorn', 'api.app:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    for attempt in range(40):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1) as response:
                assert response.status == 200
            break
        except OSError:
            time.sleep(0.25)
    else:
        raise RuntimeError('Server did not start')
    with urllib.request.urlopen('http://127.0.0.1:8000/') as response:
        assert response.status == 200
    print('Anonymous configuration, EJS, Node, generated audio, API and SPA smoke checks passed')
finally:
    server.terminate()
    server.wait(timeout=5)
