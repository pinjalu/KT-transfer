"""Explicit private HTTPS hosting; localhost remains the default."""
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Hosting:
    host: str = '127.0.0.1'
    port: int = 8000
    team_origin: str = ''
    certfile: str | None = None
    keyfile: str | None = None

    @property
    def url(self):
        scheme = 'https' if self.certfile else 'http'
        return self.team_origin or f'{scheme}://{self.host}:{self.port}'

    def allows(self, base_url):
        try:
            parsed = urlsplit(base_url)
            if parsed.username or parsed.password or parsed.path not in {'', '/'}:
                return False
            if parsed.hostname in {'127.0.0.1', 'localhost'}:
                return parsed.scheme in {'http', 'https'}
            return bool(self.team_origin) and base_url.rstrip('/') == self.team_origin
        except ValueError:
            return False


def configure(host='127.0.0.1', port=8000, team_origin='', certfile=None, keyfile=None):
    if not 1024 <= port <= 65535:
        raise ValueError('Choose a port between 1024 and 65535.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError('Bind to 127.0.0.1 or a specific private IPv4 address on this computer.') from None
    allowed = any(address in network for network in (
        ipaddress.ip_network('10.0.0.0/8'), ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16'))) if address.version == 4 else False
    if host != '127.0.0.1' and not allowed:
        raise ValueError('Use 127.0.0.1 or a specific private IPv4 address; wildcard and public binds are refused.')
    if bool(certfile) != bool(keyfile):
        raise ValueError('Provide both the TLS certificate and private key.')
    if team_origin:
        try:
            parsed = urlsplit(team_origin)
            valid = (parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
                     and not parsed.password and parsed.path in {'', '/'} and not parsed.query
                     and not parsed.fragment and (parsed.port or 443) == port
                     and bool(re.fullmatch(r'[A-Za-z0-9.-]+', parsed.hostname)))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Team origin must be one HTTPS hostname/address with the listening port and no path.')
        team_origin = team_origin.rstrip('/')
    if host != '127.0.0.1' and not (team_origin and certfile and keyfile):
        raise ValueError('Private team hosting requires an HTTPS origin, TLS certificate and private key.')
    if team_origin and not certfile:
        raise ValueError('Team HTTPS hosting requires a certificate and private key; forwarded headers are not trusted.')
    if certfile:
        for value in (certfile, keyfile):
            if not Path(value).is_file():
                raise ValueError('The configured TLS certificate or key file does not exist.')
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certfile, keyfile)
        except (OSError, ssl.SSLError):
            raise ValueError('The TLS certificate and key could not be loaded. Use a matching PEM pair.') from None
    return Hosting(host, port, team_origin, str(certfile) if certfile else None, str(keyfile) if keyfile else None)
