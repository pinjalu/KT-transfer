"""Windows current-user DPAPI vaults. No application-readable encryption key file."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading


def protect(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Encrypted credential storage requires Windows DPAPI on this deployment.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, result = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError('Windows could not unlock the credential vault. Use the original Windows account.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Vault:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            if not self.path.exists():
                return {}
            data = self.path.read_bytes()
            if len(data) > 131072:
                raise RuntimeError('Credential vault is invalid.')
            try:
                result = json.loads(protect(data, decrypt=True))
                if not isinstance(result, dict) or any(not isinstance(v, str) for v in result.values()):
                    raise ValueError()
                return result
            except (ValueError, UnicodeError):
                raise RuntimeError('Credential vault is invalid.') from None

    def save(self, values):
        with self.lock:
            current = self.read()
            current.update(values)
            atomic_write(self.path, protect(json.dumps(current).encode()))
            # Verify before allowing migration to remove the old plaintext copy.
            if self.read() != current:
                raise RuntimeError('Credential vault verification failed.')

    def migrate(self, env_path, names):
        from dotenv import dotenv_values
        from dotenv.parser import parse_stream
        from io import StringIO
        env_path = Path(env_path)
        original = env_path.read_bytes() if env_path.exists() else b''
        values = dotenv_values(env_path) if env_path.exists() else {}
        values = {name: str(values.get(name) or os.getenv(name, '')) for name in names
                  if values.get(name) or os.getenv(name)}
        if values:
            self.save(values)
        elif not self.path.exists():
            self.save({})
        # Bindings preserve complete quoted/multiline values and comments. Removing only
        # the first line of a multiline secret would leave its remaining plaintext behind.
        kept = ''.join(binding.original.string for binding in parse_stream(StringIO(original.decode('utf-8')))
                       if binding.key not in names).encode()
        if kept != original:
            if env_path.read_bytes() != original:
                raise RuntimeError('Credential file changed during migration. Retry startup.')
            atomic_write(env_path, kept)
        for name in names:
            os.environ.pop(name, None)
