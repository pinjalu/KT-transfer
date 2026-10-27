"""Create a private, single-host HTTPS certificate without changing machine trust."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def prepare(address, destination):
    ip = ipaddress.ip_address(address)
    if ip.version != 4 or not any(ip in ipaddress.ip_network(net) for net in
                                  ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Choose a private IPv4 address assigned to this Windows computer.')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('The certificate destination must be new; existing keys are never replaced.')
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'KT Assistant {ip}')])
    issued = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(issued - timedelta(minutes=5)).not_valid_after(issued + timedelta(days=90))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1')), x509.DNSName('localhost')]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None), critical=True)
            .sign(key, hashes.SHA256()))
    destination.mkdir(parents=True, mode=0o700)
    (destination / 'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (destination / 'team-public.cer').write_bytes(cert.public_bytes(serialization.Encoding.DER))
    private = destination / 'server-key.pem'
    with private.open('xb') as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    private.chmod(0o600)
    details = {'origin':f'https://{ip}:8443', 'expires':cert.not_valid_after_utc.isoformat(),
               'sha256':cert.fingerprint(hashes.SHA256()).hex().upper(),
               'is_certificate_authority':False, 'trust_installed':False}
    (destination / 'certificate-info.json').write_text(json.dumps(details, indent=2), encoding='utf-8')
    return details


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.ip, args.output), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
