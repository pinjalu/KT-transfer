"""A small replaceable lexical retrieval layer: SQLite FTS5 + paths + symbols."""
import ast
from contextlib import contextmanager
import json
from pathlib import PurePosixPath
import re
import sqlite3
from urllib.parse import quote
from pka.config import LIMITS, now

STOP = set('how does do did the a an is are was were it in on of to for and or can i we my this that work works please explain what where when why with from'.split())
SYNONYMS = {
    'login': ['auth','authentication','signin','session','password'],
    'signin': ['login','auth','session'], 'logout':['signout','session','revoke'],
    'signup':['register','registration','account'], 'payment':['checkout','billing','invoice'],
    'payments':['payment','checkout','billing'], 'database':['db','sql','model','schema'],
    'setup':['install','requirements','startup','readme'], 'start':['startup','run','readme'],
    'permission':['authorisation','authorization','role','access'],
    'error':['exception','raise','catch','error'], 'test':['pytest','spec','test'],
}


def words(text: str) -> list[str]:
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return re.findall(r'[A-Za-z0-9]+', text.lower())


def chunk_file(path: str, content: str) -> list[dict]:
    lines = content.splitlines()
    if not lines:
        return []
    boundaries = {0,len(lines)}
    symbols = {}
    if path.endswith('.py'):
        try:
            tree = ast.parse(content)
            for n in ast.walk(tree):
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    start = min([n.lineno]+[d.lineno for d in getattr(n,'decorator_list',[])])-1
                    boundaries.update([start,n.end_lineno])
                    symbols[start] = n.name
        except (SyntaxError, ValueError, RecursionError):
            pass
    else:
        pattern = re.compile(r'^\s*(?:#{1,6}\s+|(?:export\s+)?(?:async\s+)?(?:def|class|function|func|interface)\s+|(?:public|private|protected)\s+)')
        for i,line in enumerate(lines):
            if pattern.match(line):
                boundaries.add(i)
                symbols[i] = line.strip()[:180]
    points = sorted(boundaries)
    chunks = []
    for start,end in zip(points,points[1:]):
        pos = start
        while pos < end:
            stop, size = pos, 0
            while stop < end and stop-pos < 60 and size+len(lines[stop])+1 <= LIMITS.chunk_chars:
                size += len(lines[stop])+1
                stop += 1
            if stop == pos:
                stop += 1
            text = '\n'.join(lines[pos:stop])
            if text.strip():
                symbol = symbols.get(start, '')
                chunks.append({'path':path,'start':pos+1,'end':stop,'text':text,
                               'symbols':' '.join(words(symbol)), 'split':stop<end or pos>start})
            pos = stop
    return chunks


class Index:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS active (id INTEGER PRIMARY KEY CHECK(id=1), scan_id INTEGER);
            INSERT OR IGNORE INTO active VALUES(1,NULL);
            CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, scan_id INTEGER, path TEXT,
                start INTEGER, end INTEGER, text TEXT, symbols TEXT, split INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(path, symbols, text, tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, question TEXT,
                response TEXT, elapsed REAL, created TEXT, rating TEXT DEFAULT 'not assessed',
                sufficiency TEXT DEFAULT 'not assessed');
            ''')
    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path,timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    def settings(self):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            return json.loads(row[0]) if row else None
    def configure(self, settings):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(settings),))
            # Configuration changes invalidate and remove old source content and answers.
            for table in ('chunks','search','answers','scans'):
                db.execute('DELETE FROM '+table)
            db.execute('UPDATE active SET scan_id=NULL')
    def new_scan(self, detail):
        with self.db() as db:
            db.execute('UPDATE active SET scan_id=NULL')
            cur = db.execute('INSERT INTO scans(status,detail) VALUES(?,?)',('running',json.dumps(detail)))
            return cur.lastrowid
    def save_scan(self, scan_id, detail):
        with self.db() as db:
            db.execute('UPDATE scans SET status=?, detail=? WHERE id=?',
                       (detail['status'],json.dumps(detail),scan_id))
    def latest(self):
        with self.db() as db:
            row = db.execute('SELECT id,detail FROM scans ORDER BY id DESC LIMIT 1').fetchone()
            return {'id':row['id'], **json.loads(row['detail'])} if row else None
    def active_scan(self):
        with self.db() as db:
            row = db.execute('SELECT scans.id,detail FROM scans JOIN active ON scans.id=active.scan_id').fetchone()
            return {'id':row['id'],**json.loads(row['detail'])} if row else None
    def last_successful(self):
        with self.db() as db:
            row = db.execute("SELECT detail FROM scans WHERE status='complete' ORDER BY id DESC LIMIT 1").fetchone()
            return json.loads(row[0]).get('finished') if row else None
    def activate(self, scan_id, chunks, detail):
        # Replace the whole snapshot in one transaction; deleted files cannot linger in retrieval.
        with self.db() as db:
            db.execute('DELETE FROM search')
            db.execute('DELETE FROM chunks')
            for c in chunks:
                cur = db.execute('INSERT INTO chunks(scan_id,path,start,end,text,symbols,split) VALUES(?,?,?,?,?,?,?)',
                    (scan_id,c['path'],c['start'],c['end'],c['text'],c['symbols'],int(c['split'])))
                db.execute('INSERT INTO search(rowid,path,symbols,text) VALUES(?,?,?,?)',
                    (cur.lastrowid,' '.join(words(c['path'])),c['symbols'],' '.join(words(c['text']))))
            db.execute('UPDATE active SET scan_id=?',(scan_id,))
            db.execute('UPDATE scans SET status=?,detail=? WHERE id=?',(detail['status'],json.dumps(detail),scan_id))
            db.execute('DELETE FROM answers')
    def invalidate(self):
        with self.db() as db:
            db.execute('UPDATE active SET scan_id=NULL')
            for table in ('chunks','search','answers'):
                db.execute('DELETE FROM '+table)
    def recover(self):
        with self.db() as db:
            for row in db.execute("SELECT id,detail FROM scans WHERE status='running'").fetchall():
                detail = json.loads(row['detail'])
                detail.update(status='interrupted',finished=now(),error='Previous scan was interrupted. Start a new scan.')
                db.execute('UPDATE scans SET status=?,detail=? WHERE id=?',('interrupted',json.dumps(detail),row['id']))
                db.execute('UPDATE active SET scan_id=NULL')
    def search(self, question: str, scan: dict) -> list[dict]:
        tokens = list(dict.fromkeys(t for t in words(question) if t not in STOP))[:16]
        expanded = list(dict.fromkeys(tokens + [x for t in tokens for x in SYNONYMS.get(t,[])]))
        if not expanded:
            return []
        expression = ' OR '.join('"'+t+'"' for t in expanded)
        with self.db() as db:
            rows = db.execute('''SELECT c.*, bm25(search,5,4,1) AS rank FROM search
                JOIN chunks c ON c.id=search.rowid WHERE search MATCH ? AND c.scan_id=?
                ORDER BY rank LIMIT 30''',(expression,scan['id'])).fetchall()
        # Keep multiple relevant files and a bounded prompt. No model-selected tools.
        selected, counts, budget = [], {}, 0
        for row in rows:
            d = dict(row)
            if counts.get(d['path'],0) >= 2 or budget+len(d['text']) > LIMITS.context_chars:
                continue
            counts[d['path']] = counts.get(d['path'],0)+1
            budget += len(d['text'])
            d['source_id'] = 'S'+str(len(selected)+1)
            d['url'] = None if scan.get('demo') else (
                'https://github.com/'+scan['repo']+'/blob/'+scan['commit']+'/'+quote(d['path'],safe='/')+
                f"#L{d['start']}-L{d['end']}")
            selected.append(d)
            if len(selected) >= LIMITS.max_sources:
                break
        return selected
    def record_answer(self, scan_id, question, response, elapsed):
        with self.db() as db:
            return db.execute('INSERT INTO answers(scan_id,question,response,elapsed,created) VALUES(?,?,?,?,?)',
                (scan_id,question,json.dumps(response),elapsed,now())).lastrowid
    def feedback(self, answer_id, rating, sufficiency):
        with self.db() as db:
            cur = db.execute('UPDATE answers SET rating=?,sufficiency=? WHERE id=?',(rating,sufficiency,answer_id))
            return cur.rowcount == 1
