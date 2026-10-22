import httpx
import pytest

from scripts.smoke_demo import wait_for_scan


def test_smoke_waits_for_background_job_after_scan_becomes_complete(monkeypatch):
    from scripts import smoke_demo
    monkeypatch.setattr(smoke_demo.time, 'sleep', lambda _: None)
    states = iter([
        {'scan':None,'ready':False,'busy':True},
        {'scan':{'status':'complete'},'ready':True,'busy':True},
        {'scan':{'status':'complete'},'ready':True,'busy':False},
    ])
    with httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(
            lambda r:httpx.Response(200,json=next(states)))) as client:
        assert not wait_for_scan(client)['busy']


def test_smoke_does_not_accept_failed_scan():
    with httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(
            lambda r:httpx.Response(200,json={'scan':{'status':'failed'},'busy':False,'ready':False}))) as client:
        with pytest.raises(RuntimeError, match='did not complete'):
            wait_for_scan(client)
