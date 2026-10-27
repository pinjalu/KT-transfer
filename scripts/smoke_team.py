"""Real HTTPS and recovery smoke using a disposable owner, certificate and data directory."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pka.backup import create_backup, restore_backup


def certificate(folder):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    public, private = folder / 'fixture.pem', folder / 'fixture-key.pem'
    public.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    return public, private


def main(certdir=None):
    import ssl
    from smoke_demo import stop_server
    output = ROOT.parent / 'outputs' / 'team-release-2026-10-27'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='https-fixture-', dir=output) as temporary:
        folder = Path(temporary)
        public, private = ((certdir / 'server.pem', certdir / 'server-key.pem')
                           if certdir else certificate(folder))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        data = folder / 'data'
        env = {**os.environ, 'PKA_DATA_DIR': str(data), 'PKA_LOG_DIR': str(folder / 'logs'), 'PKA_EMBED_MODEL': ''}
        args = [sys.executable, '-m', 'pka', '--demo', '--port', str(port),
                '--ssl-certfile', str(public), '--ssl-keyfile', str(private)]
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        with (folder / 'server.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
            try:
                context = ssl.create_default_context(cafile=str(public))
                with httpx.Client(base_url=f'https://127.0.0.1:{port}', verify=context, trust_env=False,
                                  timeout=10, headers={'X-PKA-Request': '1'}) as client:
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError('The HTTPS fixture server exited before startup.')
                        try:
                            if client.get('/healthz').status_code == 200:
                                break
                        except httpx.TransportError:
                            time.sleep(0.1)
                    else:
                        raise RuntimeError('The HTTPS fixture server did not become ready.')
                    assert client.get('/api/status').status_code == 401
                    password = secrets.token_urlsafe(28)
                    response = client.post('/api/auth/setup', json={
                        'code': (data / 'demo.auth.setup-code').read_text(),
                        'username': 'fixture-owner', 'password': password})
                    assert response.status_code == 200
                    assert 'secure' in response.headers['set-cookie'].lower()
                    assert client.get('/api/status').status_code == 200
                    assert client.get('/api/status', headers={'Origin': 'https://untrusted.example'}).status_code == 403
                    assert client.get('/healthz', headers={'Host': 'untrusted.example'}).status_code == 403
                    assert client.get('/healthz').json() == {'status': 'ok'}
                    # A second supported process cannot share the active data directory.
                    other = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, timeout=20, creationflags=flags)
                    assert other.returncode != 0 and b'directory is in use' in other.stderr
            finally:
                stop_server(process)
        # Backup operates on the production naming contract in disposable data.
        recovery = folder / 'recovery-source'
        recovery.mkdir()
        for source, target in [('demo.sqlite3', 'index.sqlite3'), ('demo.auth.sqlite3', 'index.auth.sqlite3')]:
            with closing(sqlite3.connect(data / source)) as incoming, closing(sqlite3.connect(recovery / target)) as outgoing:
                incoming.backup(outgoing)
        archive = folder / 'fixture-backup.zip'
        manifest = create_backup(recovery, archive)
        restored = restore_backup(archive, folder / 'restored')
        with closing(sqlite3.connect(folder / 'restored' / 'index.auth.sqlite3')) as db:
            assert db.execute('SELECT count(*) FROM owner').fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0
        result = {'https_certificate_verified': True, 'authentication_required': True, 'secure_cookie': True,
                  'host_and_origin_checks': True, 'single_process_lock': True, 'backup_files': len(manifest['files']),
                  'restored_owner_retained': True, 'restored_sessions_revoked': restored['sessions_revoked'],
                  'scope': 'Disposable loopback HTTPS fixture; office-network deployment is not tested.'}
        name = 'https-team-certificate-smoke.json' if certdir else 'https-recovery-smoke.json'
        (output / name).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--certificate-directory', type=Path)
    args = parser.parse_args()
    main(args.certificate_directory.resolve() if args.certificate_directory else None)
