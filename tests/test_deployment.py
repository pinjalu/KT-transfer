"""Private hosting keeps the local host, session, origin and workspace boundaries."""
from datetime import datetime, timedelta, timezone
import ipaddress

from fastapi.testclient import TestClient
import pytest

from pka.deployment import Hosting, configure
from pka.web import create_app


@pytest.fixture
def certificate(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'kt.example.test')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('kt.example.test'),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    public, private = tmp_path / 'certificate.pem', tmp_path / 'key.pem'
    public.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    return str(public), str(private)


@pytest.mark.parametrize('host', ['0.0.0.0', '::', '8.8.8.8', '169.254.1.2', 'kt.example.test'])
def test_wildcard_public_and_implicit_binds_are_refused(host):
    with pytest.raises(ValueError): configure(host)


def test_private_address_requires_explicit_tls_origin_and_certificates(certificate):
    with pytest.raises(ValueError, match='requires'):
        configure('192.168.1.20')
    public, private = certificate
    config = configure('192.168.1.20', 8443, 'https://kt.example.test:8443', public, private)
    assert config.url == 'https://kt.example.test:8443'
    assert config.allows(config.url + '/')
    assert not config.allows('http://kt.example.test:8443')
    assert not config.allows('https://kt.example.test:8444')
    assert not config.allows('https://evil.example:8443')


@pytest.mark.parametrize('origin', ['http://kt.example.test:8443', 'https://kt.example.test:8443/path',
    'https://user:secret@kt.example.test:8443', 'https://kt.example.test:8443?token=x',
    'https://kt.example.test:8443#x', 'https://kt.example.test:8000'])
def test_invalid_team_origin_never_starts(origin, certificate):
    with pytest.raises(ValueError): configure('192.168.1.20', 8443, origin, *certificate)


def test_default_remains_loopback_and_invalid_certificates_are_refused(tmp_path):
    assert configure().url == 'http://127.0.0.1:8000'
    assert not Hosting().allows('https://kt.example.test:8443')
    file = tmp_path / 'not-a-certificate.pem'
    file.write_text('not a certificate')
    with pytest.raises(ValueError, match='could not be loaded'):
        configure('192.168.1.20', 8443, 'https://kt.example.test:8443', str(file), str(file))


def test_team_host_still_requires_authentication_and_same_origin(tmp_path):
    config = Hosting('192.168.1.20', 8443, 'https://kt.example.test:8443')
    app = create_app(True, tmp_path / 'demo.sqlite3', hosting=config)
    with TestClient(app, base_url=config.url, headers={'X-PKA-Request': '1'}) as client:
        assert client.get('/healthz').json() == {'status': 'ok'}
        assert client.get('/api/status').status_code == 401
        assert client.get('/api/auth/status').status_code == 200
        assert client.get('/api/auth/status', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.get('/api/auth/status', headers={'Host': 'evil.example'}).status_code == 403
        assert client.get('/api/auth/status', headers={'X-PKA-Request': ''}).status_code == 403
        response = client.post('/api/auth/setup', json={'code': app.state.auth.setup_path.read_text(),
            'username': 'team-owner', 'password': 'Private deployment fixture password!'})
        assert response.status_code == 200
        assert 'secure' in response.headers['set-cookie'].lower()
        assert client.get('/api/status').status_code == 200
        assert client.get('/healthz').headers['strict-transport-security'] == 'max-age=86400'
        assert client.post('/api/admin/accounts', json={'username': 'member',
            'password': 'Private member fixture password!'}).status_code == 200
        with TestClient(app, base_url=config.url, headers={'X-PKA-Request': '1'}) as member:
            assert member.post('/api/auth/login', json={'username': 'member',
                'password': 'Private member fixture password!'}).status_code == 200
            assert member.get('/api/status').status_code == 200
            assert member.get('/api/admin/accounts').status_code == 403
            assert member.get('/api/status', headers={'Host': 'evil.example'}).status_code == 403
    with TestClient(app, base_url='http://kt.example.test:8443', headers={'X-PKA-Request': '1'}) as plain:
        assert plain.get('/api/auth/status', headers={'X-Forwarded-Proto': 'https'}).status_code == 403


def test_health_reports_storage_failure_without_exposing_details(tmp_path, monkeypatch):
    app = create_app(True, tmp_path / 'demo.sqlite3')
    def unavailable(): raise OSError('PRIVATE DATABASE LOCATION')
    monkeypatch.setattr(app.state.service.index, 'db', unavailable)
    with TestClient(app, base_url='http://localhost:8000') as client:
        response = client.get('/healthz')
        assert response.status_code == 503 and response.json() == {'status': 'unavailable'}
        assert 'PRIVATE' not in response.text
