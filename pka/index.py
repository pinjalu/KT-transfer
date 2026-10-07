"""A small replaceable lexical retrieval layer: SQLite FTS5 + paths + symbols."""
import ast
import difflib
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


TEST_PATH = re.compile(r'(^|/)(tests?|spec|__tests__|testing)/|(^|/)test_[^/]*$|_test\.[A-Za-z]+$|\.(test|spec)\.[A-Za-z]+$', re.I)
MIN_CHUNK_CHARS = 80
PATH_MATCH_BONUS = 1.5
MAX_TEST_SOURCES = 2


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
            CREATE TABLE IF NOT EXISTS overviews (commit_sha TEXT PRIMARY KEY, scan_id INTEGER,
                payload TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, question TEXT,
                response TEXT, elapsed REAL, created TEXT, rating TEXT DEFAULT 'not assessed',
                sufficiency TEXT DEFAULT 'not assessed');
            ''')
            self._migrate(db)
    def _migrate(self, db):
        # Added after the first release, so an existing database is upgraded in place.
        columns = {r[1] for r in db.execute('PRAGMA table_info(chunks)').fetchall()}
        if 'url' not in columns:
            db.execute('ALTER TABLE chunks ADD COLUMN url TEXT')

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
        """Update the selection, keeping anything this call does not mention.

        Only the repository or branch changing invalidates what was collected. Ticking a
        platform used to clear the whole index and both connector choices along with it, which
        made a connection impossible to keep.
        """
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            current = json.loads(row[0]) if row else {}
            merged = {**current, **settings}
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(merged),))
            if (current.get('repo'), current.get('branch')) == (merged.get('repo'), merged.get('branch')):
                return
            # The snapshot belonged to the old repository, so it cannot answer for the new one.
            for table in ('chunks','search','answers','overviews','scans'):
                db.execute('DELETE FROM '+table)
            db.execute('UPDATE active SET scan_id=NULL')
    def configure_source(self, name, value):
        """Save one connector's choice without clearing the code index, which it does not affect."""
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            settings = json.loads(row[0]) if row else {}
            settings[name] = value
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(settings),))
    def configure_slack(self, slack):
        """Save the Slack choice without clearing the code index, which it does not affect."""
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            settings = json.loads(row[0]) if row else {}
            settings['slack'] = slack
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(settings),))
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
            db.execute('DELETE FROM overviews WHERE commit_sha<>?',(detail.get('commit',''),))
    def replace_source(self, scan_id, prefix, blocks):
        """Swap in this scan's Slack content, leaving the code snapshot alone.

        Reading again replaces what was read before rather than adding to it, so a message that
        was deleted or a channel that was removed from the list cannot linger in answers.
        """
        with self.db() as db:
            stale = [r[0] for r in db.execute(
                'SELECT id FROM chunks WHERE scan_id=? AND path LIKE ?',(scan_id,prefix+'%')).fetchall()]
            for chunk_id in stale:
                db.execute('DELETE FROM search WHERE rowid=?',(chunk_id,))
            db.execute('DELETE FROM chunks WHERE scan_id=? AND path LIKE ?',(scan_id,prefix+'%'))
            for block in blocks:
                cur = db.execute(
                    'INSERT INTO chunks(scan_id,path,start,end,text,symbols,split,url) VALUES(?,?,?,?,?,?,?,?)',
                    (scan_id,block['path'],block['start'],block['end'],block['text'],
                     block['symbols'],int(block['split']),block.get('url') or None))
                db.execute('INSERT INTO search(rowid,path,symbols,text) VALUES(?,?,?,?)',
                    (cur.lastrowid,' '.join(words(block['path'])),block['symbols'],' '.join(words(block['text']))))
            return len(blocks)
    def replace_slack(self, scan_id, blocks):
        return self.replace_source(scan_id, 'slack/', blocks)
    def source_blocks(self, scan_id, prefix):
        with self.db() as db:
            return db.execute('SELECT COUNT(*) FROM chunks WHERE scan_id=? AND path LIKE ?',
                              (scan_id,prefix+'%')).fetchone()[0]
    def slack_blocks(self, scan_id):
        return self.source_blocks(scan_id, 'slack/')
    def invalidate(self):
        with self.db() as db:
            db.execute('UPDATE active SET scan_id=NULL')
            for table in ('chunks','search','answers','overviews'):
                db.execute('DELETE FROM '+table)
    def recover(self):
        with self.db() as db:
            for row in db.execute("SELECT id,detail FROM scans WHERE status='running'").fetchall():
                detail = json.loads(row['detail'])
                detail.update(status='interrupted',finished=now(),error='Previous scan was interrupted. Start a new scan.')
                db.execute('UPDATE scans SET status=?,detail=? WHERE id=?',('interrupted',json.dumps(detail),row['id']))
                db.execute('UPDATE active SET scan_id=NULL')
    def vocabulary(self, scan_id: int) -> set:
        """Every word that actually appears in this snapshot, used to understand the question.

        A generic synonym list cannot know that this project calls it authenticate rather than
        login, so the words the project itself uses are the better dictionary. Cached per scan
        because it is read once and asked many times.
        """
        cached = getattr(self, '_vocab', None)
        if cached and cached[0] == scan_id:
            return cached[1]
        with self.db() as db:
            rows = db.execute('SELECT path,symbols,text FROM chunks WHERE scan_id=?',(scan_id,)).fetchall()
        vocab = set()
        for r in rows:
            vocab.update(words(r['path']))
            vocab.update(words(r['symbols'] or ''))
            vocab.update(words(r['text']))
        vocab = {w for w in vocab if len(w) > 2}
        self._vocab = (scan_id, vocab)
        return vocab

    def resolve(self, tokens: list[str], vocab: set) -> tuple[list[str], list[str], dict]:
        """Map what the user typed onto words this project really contains.

        Exact words pass through. A word that is not in the project is tried as a prefix, which
        catches a wrong ending, then by closeness, which catches a misspelling. A word that
        matches nothing is dropped and reported rather than left to dilute the ranking.
        """
        used, unknown, corrections = [], [], {}
        for t in tokens:
            if t in vocab:
                used.append(t)
                used.extend(x for x in SYNONYMS.get(t, []) if x in vocab)
                continue
            # The project may simply call it something else: the user says login, the code says
            # authenticate. Try the known aliases before guessing at spelling.
            alias = [x for x in SYNONYMS.get(t, []) if x in vocab][:3]
            if alias:
                corrections[t] = alias
                used.extend(alias)
                continue
            # Only guess at a word long enough for a guess to be meaningful. Correcting a short
            # word turns "rom" into "from" and makes the search worse than leaving it out.
            near = []
            if len(t) >= 5:
                stem = t[:max(4, len(t) - 3)]
                near = sorted(w for w in vocab if w.startswith(stem))[:2]
                if not near:
                    # A typist rarely gets the first letter wrong, and without that guard
                    # "winner" is read as "inner", which is a different word entirely.
                    near = [w for w in difflib.get_close_matches(t, vocab, n=4, cutoff=0.84)
                            if w[:1] == t[:1]][:2]
            if near:
                corrections[t] = near
                used.extend(near)
            else:
                unknown.append(t)
        return list(dict.fromkeys(used)), unknown, corrections

    def search(self, question: str, scan: dict, info: dict | None = None) -> list[dict]:
        asked = list(dict.fromkeys(t for t in words(question) if t not in STOP))[:16]
        # resolve already folds in aliases and spelling, so tokens are the final search terms
        tokens, unknown, corrections = self.resolve(asked, self.vocabulary(scan['id']))
        expanded = tokens
        if info is not None:
            info.update(asked=asked, terms=tokens, unknown=unknown, corrections=corrections)
        if not expanded:
            return []
        expression = ' OR '.join('"'+t+'"' for t in expanded)
        with self.db() as db:
            rows = db.execute('''SELECT c.*, bm25(search,5,4,1) AS rank FROM search
                JOIN chunks c ON c.id=search.rowid WHERE search MATCH ? AND c.scan_id=?
                ORDER BY rank LIMIT 60''',(expression,scan['id'])).fetchall()
        # BM25 divides by document length, so a long chunk that repeats a word can outrank a file
        # whose folder is named after it. Someone asking about bug investigation wants
        # bug_investigation/, so reward a path that carries the words that were asked for.
        wanted = set(expanded)
        rows = sorted(rows, key=lambda r: r['rank'] - PATH_MATCH_BONUS * len(wanted & set(words(r['path']))))
        # Keep multiple relevant files and a bounded prompt. No model-selected tools.
        def choose(min_chars: int, test_cap: int) -> list[dict]:
            selected, counts, budget, tests = [], {}, 0, 0
            for row in rows:
                d = dict(row)
                # BM25 favours short documents, so a one line chunk such as "class Store:" can
                # outrank the implementation while carrying nothing a reader can use.
                if len(d['text'].strip()) < min_chars:
                    continue
                # A test is real evidence and sometimes the clearest specification, but a question
                # about how something works should be answered mostly from the code that does it.
                is_test = bool(TEST_PATH.search(d['path']))
                if is_test and tests >= test_cap:
                    continue
                if counts.get(d['path'],0) >= 2 or budget+len(d['text']) > LIMITS.context_chars:
                    continue
                counts[d['path']] = counts.get(d['path'],0)+1
                budget += len(d['text'])
                tests += is_test
                d['source_id'] = 'S'+str(len(selected)+1)
                d['url'] = d.get('url') or (None if scan.get('demo') else (
                    'https://github.com/'+scan['repo']+'/blob/'+scan['commit']+'/'+quote(d['path'],safe='/')+
                    f"#L{d['start']}-L{d['end']}"))
                selected.append(d)
                if len(selected) >= LIMITS.max_sources:
                    break
            return selected
        # Prefer substantial, non-test evidence; fall back rather than return nothing at all.
        return choose(MIN_CHUNK_CHARS, MAX_TEST_SOURCES) or choose(0, LIMITS.max_sources)
    def record_answer(self, scan_id, question, response, elapsed):
        with self.db() as db:
            return db.execute('INSERT INTO answers(scan_id,question,response,elapsed,created) VALUES(?,?,?,?,?)',
                (scan_id,question,json.dumps(response),elapsed,now())).lastrowid
    def save_overview(self, scan_id, commit_sha, payload):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO overviews VALUES(?,?,?,?)',
                       (commit_sha,scan_id,json.dumps(payload),now()))
    def overview(self, commit_sha):
        """The cached overview for this commit, or None. Keyed by commit so a refresh that
        lands on the same commit keeps it and a new commit rebuilds it."""
        with self.db() as db:
            row = db.execute('SELECT payload,created FROM overviews WHERE commit_sha=?',(commit_sha,)).fetchone()
            if not row:
                return None
            return {**json.loads(row['payload']), 'built_at':row['created']}
    def indexed_paths(self, scan_id):
        with self.db() as db:
            return [r[0] for r in db.execute(
                'SELECT DISTINCT path FROM chunks WHERE scan_id=? ORDER BY path',(scan_id,)).fetchall()]
    def feedback(self, answer_id, rating, sufficiency):
        with self.db() as db:
            cur = db.execute('UPDATE answers SET rating=?,sufficiency=? WHERE id=?',(rating,sufficiency,answer_id))
            return cur.rowcount == 1
