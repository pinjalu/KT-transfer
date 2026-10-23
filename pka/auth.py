"""Local accounts and sessions. Each account owns an isolated source workspace.

Passwords use salted scrypt. Only hashes of random session/setup tokens are stored in SQLite.
The setup code is delivered through a local file, never an unauthenticated HTTP response.
"""
from contextlib import contextmanager
import hashlib
import hmac
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
ATTEMPTS = 5
RETRY_SECONDS = 5 * 60
MAX_SESSIONS = 10
_hash_slots = threading.BoundedSemaphore(2)


class AuthError(Exception):
    def __init__(self, message, status=401, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with _hash_slots:
        value = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                               n=131072, r=8, p=1, dklen=32, maxmem=256*1024*1024)
    return f'scrypt:131072:8:1:{salt}:{value.hex()}'


def password_matches(password, stored):
    try:
        algorithm, n, r, p, salt, value = stored.split(':')
        if (algorithm, n, r, p) != ('scrypt', '131072', '8', '1'):
            return False
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def validate_account(username, password):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,79}', username):
        raise AuthError('Use 3–80 letters, numbers, dots, underscores or hyphens for your username.', 422)
    if not 15 <= len(password) <= 128 or not password.strip():
        raise AuthError('Use a password or passphrase containing 15–128 characters.', 422)
    return username


class AuthStore:
    def __init__(self, index_path):
        self.path = Path(index_path).with_suffix('.auth.sqlite3')
        self.setup_path = self.path.with_suffix('.setup-code')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # POSIX mode; Windows inherits the local data directory's user ACL.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, origin TEXT NOT NULL,
                    created REAL NOT NULL, active REAL NOT NULL, version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS bootstrap (id INTEGER PRIMARY KEY CHECK(id=1), token_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS throttle (id INTEGER PRIMARY KEY CHECK(id=1), started REAL NOT NULL, attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS members (
                    id INTEGER PRIMARY KEY CHECK(id>1), username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1);
                CREATE VIEW IF NOT EXISTS accounts AS
                    SELECT id,username,password_hash,version,1 AS enabled,'owner' AS role FROM owner
                    UNION ALL SELECT id,username,password_hash,version,enabled,'member' AS role FROM members;
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, created REAL NOT NULL, actor INTEGER,
                    action TEXT NOT NULL, outcome INTEGER NOT NULL, target INTEGER);
            ''')
            if 'user_id' not in {row['name'] for row in db.execute('PRAGMA table_info(sessions)')}:
                db.execute('ALTER TABLE sessions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1')
        self.ensure_setup()

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ensure_setup(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM owner').fetchone():
                self.setup_path.unlink(missing_ok=True)
                return
            saved = db.execute('SELECT token_hash FROM bootstrap').fetchone()
            if saved and self.setup_path.exists():
                code = self.setup_path.read_text(encoding='utf-8').strip()
                if hmac.compare_digest(digest(code), saved['token_hash']):
                    return
            code = secrets.token_urlsafe(32)
            fd = os.open(self.setup_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(code)
            db.execute('INSERT OR REPLACE INTO bootstrap VALUES(1,?)', (digest(code),))

    def configured(self):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM owner').fetchone())

    def reserve_attempt(self):
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM throttle').fetchone()
            if not row or now >= row['started'] + RETRY_SECONDS:
                db.execute('INSERT OR REPLACE INTO throttle VALUES(1,?,1)', (now,))
            elif row['attempts'] >= ATTEMPTS:
                raise AuthError('Too many attempts. Try again in a few minutes.', 429,
                                max(1, math.ceil(row['started'] + RETRY_SECONDS - now)))
            else:
                db.execute('UPDATE throttle SET attempts=attempts+1 WHERE id=1')

    def _session(self, db, origin, version, old_token='', user_id=1):
        now, token = time.time(), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE token_hash=? OR created<=? OR active<=?',
                   (digest(old_token), now-ABSOLUTE_SECONDS, now-IDLE_SECONDS))
        db.execute('INSERT INTO sessions(token_hash,origin,created,active,version,user_id) VALUES(?,?,?,?,?,?)',
                   (digest(token), origin, now, now, version, user_id))
        db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN '
                   '(SELECT token_hash FROM sessions WHERE user_id=? ORDER BY created DESC LIMIT ?)',
                   (user_id, user_id, MAX_SESSIONS))
        db.execute('DELETE FROM throttle')
        return token

    def setup(self, code, username, password, origin):
        self.reserve_attempt()
        username = validate_account(username, password)
        # Verify the code before doing an expensive hash; recheck under the write lock.
        with self.db() as db:
            row = db.execute('SELECT token_hash FROM bootstrap').fetchone()
            if not row or not hmac.compare_digest(row['token_hash'], digest(code)):
                raise AuthError('Setup code is invalid or has already been used.')
        hashed = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM owner').fetchone():
                raise AuthError('The owner account already exists. Sign in instead.', 409)
            row = db.execute('SELECT token_hash FROM bootstrap').fetchone()
            if not row or not hmac.compare_digest(row['token_hash'], digest(code)):
                raise AuthError('Setup code is invalid or has already been used.')
            db.execute('INSERT INTO owner(id,username,password_hash) VALUES(1,?,?)', (username, hashed))
            db.execute('DELETE FROM bootstrap')
            token = self._session(db, origin, 1)
        self.setup_path.unlink(missing_ok=True)
        return token

    def login(self, username, password, origin, old_token=''):
        self.reserve_attempt()
        with self.db() as db:
            owner = db.execute('SELECT * FROM accounts WHERE username=?', (username.strip().lower(),)).fetchone()
        # Unknown users pay the same hash cost. Never report which field was wrong.
        stored = owner['password_hash'] if owner else 'scrypt:131072:8:1:' + '00'*16 + ':' + '00'*32
        valid = password_matches(password, stored)
        if not owner or not valid or not owner['enabled']:
            raise AuthError('Username or password is incorrect.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT version,enabled FROM accounts WHERE id=?', (owner['id'],)).fetchone()
            if not current['enabled'] or current['version'] != owner['version']:
                raise AuthError('Account changed. Sign in again.')
            return self._session(db, origin, current['version'], old_token, owner['id'])

    def session(self, token, origin, touch=False):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return None
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT s.*,o.username,o.role FROM sessions s JOIN accounts o '
                             'ON o.id=s.user_id AND o.version=s.version AND o.enabled=1 '
                             'WHERE s.token_hash=? AND s.origin=?', (digest(token), origin)).fetchone()
            if not row:
                return None
            if now >= row['created']+ABSOLUTE_SECONDS or now >= row['active']+IDLE_SECONDS:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(token),))
                return None
            if touch:
                db.execute('UPDATE sessions SET active=? WHERE token_hash=?', (now, digest(token)))
            return {'id':row['user_id'], 'role':row['role'], 'username':row['username'],
                    'expires_at':row['created']+ABSOLUTE_SECONDS,
                    'idle_expires_at':(now if touch else row['active'])+IDLE_SECONDS}

    def logout(self, token, everywhere=False):
        with self.db() as db:
            if everywhere:
                db.execute('DELETE FROM sessions WHERE user_id=(SELECT user_id FROM sessions WHERE token_hash=?)',
                           (digest(token),))
            else:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (digest(token),))

    def change_password(self, token, origin, current_password, new_password):
        self.reserve_attempt()
        session = self.session(token, origin)
        if not session:
            raise AuthError('Sign in again to change your password.')
        validate_account(session['username'], new_password)
        with self.db() as db:
            owner = db.execute('SELECT * FROM accounts WHERE id=?', (session['id'],)).fetchone()
        if not password_matches(current_password, owner['password_hash']):
            raise AuthError('Current password is incorrect.', 403)
        hashed = password_hash(new_password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute('SELECT * FROM sessions WHERE token_hash=?', (digest(token),)).fetchone()
            current = db.execute('SELECT version,enabled FROM accounts WHERE id=?', (session['id'],)).fetchone()
            now = time.time()
            if (not active or not current['enabled'] or current['version'] != owner['version'] or
                    now >= active['created']+ABSOLUTE_SECONDS or now >= active['active']+IDLE_SECONDS):
                raise AuthError('Session changed. Sign in again.')
            table = 'owner' if session['id'] == 1 else 'members'
            db.execute(f'UPDATE {table} SET password_hash=?,version=version+1 WHERE id=?', (hashed,session['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (session['id'],))
            return self._session(db, origin, owner['version']+1, user_id=session['id'])

    def reset_password(self, new_password):
        """Local terminal recovery only. OS account access is the trust boundary."""
        with self.db() as db:
            owner = db.execute('SELECT username FROM owner').fetchone()
        if not owner:
            raise AuthError('Create the owner account in the browser first.', 409)
        validate_account(owner['username'], new_password)
        hashed = password_hash(new_password)
        with self.db() as db:
            db.execute('UPDATE owner SET password_hash=?,version=version+1', (hashed,))
            db.execute('DELETE FROM sessions WHERE user_id=1')
            db.execute('DELETE FROM throttle')
        return owner['username']

    def create_member(self, username, password):
        username = validate_account(username, password)
        hashed = password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM owner').fetchone():
                raise AuthError('Create the owner account first.', 409)
            if db.execute('SELECT 1 FROM accounts WHERE username=?', (username,)).fetchone():
                raise AuthError('This username is already in use.', 409)
            if db.execute('SELECT count(*) FROM members').fetchone()[0] >= 25:
                raise AuthError('This local installation supports up to 25 members.', 409)
            user_id = db.execute('SELECT coalesce(max(id),1)+1 FROM members').fetchone()[0]
            db.execute('INSERT INTO members(id,username,password_hash) VALUES(?,?,?)', (user_id,username,hashed))
            return {'id':user_id, 'username':username, 'role':'member', 'enabled':True}

    def set_member_enabled(self, user_id, enabled):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('UPDATE members SET enabled=?,version=version+1 WHERE id=?',
                              (int(enabled),user_id)).rowcount:
                raise AuthError('Member not found.', 404)
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

    def members(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT id,username,role,enabled FROM accounts ORDER BY id')]

    def audit(self, action, actor=None, outcome=200, target=None):
        # Only application-defined action names and numeric identities, never request bodies,
        # source names, passwords, session identifiers, questions or credential values.
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', action):
            raise ValueError('Invalid audit action')
        with self.db() as db:
            db.execute('INSERT INTO audit(created,actor,action,outcome,target) VALUES(?,?,?,?,?)',
                       (time.time(),actor,action,outcome,target))

    def audit_records(self, before=0):
        with self.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM audit WHERE (?=0 OR id<?) ORDER BY id DESC LIMIT 100', (before,before))]
