"""Persistent settings, content-free usage ledger, and atomic quota reservations."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pka.llm.config import Routing, digest


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS ai_settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_permissions (repo TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_confirmations (provider TEXT PRIMARY KEY, key_hash TEXT NOT NULL, checked REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_attempts (id TEXT PRIMARY KEY, workspace TEXT, project TEXT, feature TEXT,
                provider TEXT, model TEXT, started REAL, elapsed REAL DEFAULT 0, status TEXT,
                error TEXT DEFAULT '', http_status INTEGER, reserved INTEGER,
                input_tokens INTEGER, output_tokens INTEGER, reported TEXT DEFAULT '{}');
            CREATE INDEX IF NOT EXISTS ai_attempts_time ON ai_attempts(started);
            CREATE TABLE IF NOT EXISTS ai_cooldowns (provider TEXT PRIMARY KEY, until_time REAL NOT NULL, reason TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def config(self):
        with self.db() as db:
            row = db.execute('SELECT value FROM ai_settings WHERE id=1').fetchone()
        return Routing.model_validate_json(row[0]) if row else Routing()

    def save_config(self, value):
        config = Routing.model_validate(value)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO ai_settings VALUES(1,?)', (config.model_dump_json(),))
        return config

    def permission(self, repo):
        with self.db() as db:
            row = db.execute('SELECT value FROM ai_permissions WHERE repo=?', (repo,)).fetchone()
        value = json.loads(row[0]) if row else {'providers':[], 'classification':'private', 'approved_at':None}
        # Existing approvals cover GitHub only; never silently expand their scope.
        value.setdefault('source_types', ['github'] if value['providers'] else [])
        return value

    def permit(self, repo, providers, *, classification='public', source_types=('github',)):
        if classification not in {'public','github'}:
            raise ValueError('Unsupported cloud source approval.')
        if set(source_types) - {'github','jira','slack'} or 'github' not in source_types:
            raise ValueError('Choose GitHub and explicitly approved connected source types.')
        value = {'providers':sorted(set(providers)), 'classification':classification if providers else 'private',
                 'source_types':sorted(set(source_types)) if providers else [],
                 'approved_at':time.time() if providers else None}
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO ai_permissions VALUES(?,?)', (repo,json.dumps(value)))
        return value

    def confirm(self, provider, key, confirmed):
        with self.db() as db:
            db.execute('DELETE FROM ai_confirmations WHERE provider=?',(provider,))
            if confirmed and key:
                db.execute('INSERT INTO ai_confirmations VALUES(?,?,?)', (provider,digest(key),time.time()))

    def confirmed(self, provider, key, at=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM ai_confirmations WHERE provider=?',(provider,)).fetchone()
        return bool(row and key and row['key_hash']==digest(key) and 0 <= (at or time.time())-row['checked'] < 7*86400)

    def signature(self, repo):
        with self.db() as db:
            confirmations = [dict(row) for row in db.execute('SELECT * FROM ai_confirmations ORDER BY provider')]
        return digest({'config':self.config().model_dump(), 'permission':self.permission(repo), 'confirmations':confirmations})

    def reserve(self, workspace, project, feature, target, estimated, provider_limits, project_limits, *, at=None):
        at = time.time() if at is None else at
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM ai_cooldowns WHERE provider=?',(target.provider,)).fetchone()
            if target.provider != 'ollama' and row and row['until_time'] > at:
                return None, 'cooldown'
            if target.provider != 'ollama':
                for clause, args, limits, label in [
                    ('provider=?',[target.provider],provider_limits,'provider_limit'),
                    ("project=? AND provider!='ollama'",[project],project_limits,'project_limit')]:
                    for window, count_cap, token_cap in [(60,limits.rpm,limits.tpm),(86400,limits.rpd,limits.tpd)]:
                        row = db.execute(f'''SELECT COUNT(*) AS requests,
                            COALESCE(SUM(CASE WHEN input_tokens IS NOT NULL AND output_tokens IS NOT NULL
                                THEN input_tokens+output_tokens ELSE reserved END),0) AS tokens
                            FROM ai_attempts WHERE {clause} AND started>?''', (*args,at-window)).fetchone()
                        if row['requests']+1 > count_cap or row['tokens']+estimated > token_cap:
                            return None,label
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO ai_attempts(id,workspace,project,feature,provider,model,started,status,reserved) VALUES(?,?,?,?,?,?,?,?,?)',
                       (identifier,workspace,project,feature,target.provider,target.model,at,'in_flight',estimated))
            # Only expired metrics are pruned; rolling quota windows remain intact.
            db.execute('DELETE FROM ai_attempts WHERE started<?',(at-30*86400,))
            return identifier,''

    def finish(self, identifier, elapsed, *, reply=None, error=None, status='succeeded'):
        with self.db() as db:
            db.execute('UPDATE ai_attempts SET elapsed=?,status=?,error=?,http_status=?,input_tokens=?,output_tokens=?,reported=? WHERE id=?',
                (elapsed,status,error.code if error else '',error.status if error else 200 if reply else None,
                 reply.input_tokens if reply else None,reply.output_tokens if reply else None,
                 json.dumps(reply.reported if reply else error.reported if error else {}),identifier))
            if error and error.retry_after:
                provider = db.execute('SELECT provider FROM ai_attempts WHERE id=?',(identifier,)).fetchone()[0]
                db.execute('INSERT INTO ai_cooldowns VALUES(?,?,?) ON CONFLICT(provider) DO UPDATE SET '
                           'until_time=MAX(until_time,excluded.until_time),reason=excluded.reason',
                           (provider,time.time()+error.retry_after,error.code))
            reported = reply.reported if reply else error.reported if error else {}
            reset = max(reported.get('reset-requests-seconds',86400) if reported.get('remaining-requests')==0 else 0,
                        reported.get('reset-tokens-seconds',60) if reported.get('remaining-tokens')==0 else 0)
            if reset:
                provider = db.execute('SELECT provider FROM ai_attempts WHERE id=?',(identifier,)).fetchone()[0]
                db.execute('INSERT INTO ai_cooldowns VALUES(?,?,?) ON CONFLICT(provider) DO UPDATE SET '
                           'until_time=MAX(until_time,excluded.until_time),reason=excluded.reason',
                           (provider,time.time()+reset,'reported_quota_exhausted'))

    def dashboard(self, workspace, config=None):
        with self.db() as db:
            rows = db.execute('SELECT * FROM ai_attempts WHERE workspace=? ORDER BY started DESC LIMIT 100',(workspace,)).fetchall()
            aggregate = db.execute('''SELECT provider,model,feature,COUNT(*) requests,
                SUM(status='succeeded') successes,AVG(elapsed) average_seconds,
                SUM(COALESCE(input_tokens,0)) input_tokens,SUM(COALESCE(output_tokens,0)) output_tokens,
                SUM(input_tokens IS NOT NULL AND output_tokens IS NOT NULL) usage_reported_requests,
                SUM(CASE WHEN input_tokens IS NULL OR output_tokens IS NULL THEN reserved ELSE 0 END) estimated_unreported_tokens
                FROM ai_attempts WHERE workspace=? AND started>? GROUP BY provider,model,feature''',
                (workspace,time.time()-86400)).fetchall()
            cooldowns = db.execute('SELECT provider,until_time,reason FROM ai_cooldowns WHERE until_time>?',(time.time(),)).fetchall()
            shared = []
            if config:
                for provider, settings in config.providers.items():
                    for seconds,request_cap,token_cap in ((60,settings.limits.rpm,settings.limits.tpm),(86400,settings.limits.rpd,settings.limits.tpd)):
                        usage = db.execute('''SELECT COUNT(*),COALESCE(SUM(CASE WHEN input_tokens IS NOT NULL AND output_tokens IS NOT NULL
                            THEN input_tokens+output_tokens ELSE reserved END),0) FROM ai_attempts WHERE provider=? AND started>?''',
                            (provider,time.time()-seconds)).fetchone()
                        shared.append({'provider':provider,'window_seconds':seconds,'requests':usage[0],'tokens':usage[1],
                                       'request_cap':request_cap,'token_cap':token_cap,
                                       'warning':usage[0]>=request_cap*.8 or usage[1]>=token_cap*.8})
        attempts = [{k:row[k] for k in ('id','feature','provider','model','started','elapsed','status','error','http_status',
                                        'reserved','input_tokens','output_tokens')} | {'reported':json.loads(row['reported'])} for row in rows]
        return {'recent':attempts, 'last_24_hours':[dict(r) for r in aggregate], 'cooldowns':[dict(r) for r in cooldowns],
                'shared_local_estimates':shared,
                'quota_scope':'Provider limits are shared by all models and accounts on this installation. Project caps are additional.',
                'usage_note':'Token reservations are local estimates. Actual usage and remaining quota are labelled only when reported by a provider. Other applications using the same provider account are not measured.'}
