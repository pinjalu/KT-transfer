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

def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='pka-demo-') as data:
        env={**os.environ,'PKA_DATA_DIR':data,'PYTHONPATH':str(ROOT)}
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
                for _ in range(100):
                    state=client.get('/api/status').json()
                    if state['scan'] and state['scan']['status']!='running':break
                    time.sleep(.1)
                assert state['scan']['status']=='complete',state
                answer=client.post('/api/ask',json={'question':'How does login work?'}).json()
                assert answer['sources'] and answer['statements'],answer
                assert client.post('/api/feedback',json={'answer_id':answer['answer_id'],'rating':'partially correct','sufficiency':'sufficient'}).status_code==200
                print(json.dumps({'mode':'SIMULATED GitHub data and answer; real HTTP and MCP subprocess',
                    'scan_status':state['scan']['status'],'files_read':state['scan']['read'],
                    'files_skipped':state['scan']['skipped'],'sources':len(answer['sources']),'feedback_saved':True},indent=2))
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
