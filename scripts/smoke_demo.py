"""Real local HTTP + MCP test. GitHub data and the answer are SIMULATED."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parent.parent


def wait_for_scan(client, timeout=120):
    """A saved scan can be complete before its background worker releases the job slot."""
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        response = client.get('/api/status')
        response.raise_for_status()
        state = response.json()
        if state.get('scan') and state['scan']['status'] != 'running' and not state.get('busy'):
            if state['scan']['status'] != 'complete' or not state.get('ready'):
                raise RuntimeError('Demo scan did not complete successfully.')
            return state
        time.sleep(.1)
    raise RuntimeError('Demo scan did not become idle before the timeout.')


def stop_server(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Windows venv Python is a launcher. Terminating only it leaves the server child
        # holding the temporary database/log open. Stop only the tree this check created.
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='pka-demo-') as data:
        env={**os.environ,'PKA_DATA_DIR':data,'PYTHONPATH':str(ROOT),'PKA_EMBED_MODEL':''}
        process=subprocess.Popen([sys.executable,'-m','pka','--demo','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'X-PKA-Request':'1'},timeout=30,trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get('/').status_code==200:break
                    except httpx.ConnectError:pass
                    if process.poll() is not None:raise RuntimeError('Application exited before startup.')
                    time.sleep(.1)
                else:raise RuntimeError('Application startup timed out.')
                assert client.post('/api/scan',json={}).status_code==200
                state=wait_for_scan(client)
                response=client.post('/api/ask',json={'question':'How does login work?'})
                response.raise_for_status()
                answer=response.json()
                assert answer['sources'] and answer['statements'],answer
                assert client.post('/api/feedback',json={'answer_id':answer['answer_id'],'rating':'partially correct','sufficiency':'sufficient'}).status_code==200
                print(json.dumps({'mode':'SIMULATED GitHub data and answer; real HTTP and MCP subprocess',
                    'scan_status':state['scan']['status'],'files_read':state['scan']['read'],
                    'files_skipped':state['scan']['skipped'],'sources':len(answer['sources']),'feedback_saved':True},indent=2))
        finally:
            stop_server(process)

if __name__=='__main__':main()
