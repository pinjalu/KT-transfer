"""A small replaceable lexical retrieval layer: SQLite FTS5 + paths + symbols."""
import ast
import difflib
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import PurePosixPath
import re
import sqlite3
from pka import embed
from pka.answer_checks import comparison_references
from pka.config import LIMITS, now, source_url

STOP = set('how does do did the a an is are was were it in on of to for and or can i we my this that work works please explain what where when why with from'.split())
# Words that carry no search intent but do appear in ordinary code and comments. Left in, a
# greeting retrieves whichever file happens to contain the word "hello" and the model is then
# asked to explain it, which is how "hello" came back as an explanation of a chat module.
SOCIAL = set('hello hi hy hii hiii hey heya hiya helo hllo yo greetings howdy namaste salam '
             'thanks thank thankyou thx ty cheers bye goodbye cya ok okay k '
             'yes no yeah yep nope sure cool nice great good morning afternoon evening night '
             # "help" is deliberately absent. It is a greeting word in some mouths and a real
             # file name in plenty of projects, and losing a search for help.py costs more
             # than answering "help" as though it were a question.
             'you your yours u who there here me us am im sorry please welcome'.split())
STOP |= SOCIAL
# Conversational scaffolding should not outrank the subject of a question. Keep
# these out of search only, so greetings and the small-talk contract are unchanged.
QUERY_FILLER = set('which project codebase want wants ask asking about tell give name named '
                   'use uses used using currently actual exact specifically'.split())


def question_words(question):
    asked = list(dict.fromkeys(t for t in words(question) if t not in STOP))
    focused = [t for t in asked if t not in QUERY_FILLER]
    return (focused or asked)[:16]


def model_role_query(question):
    """Disambiguate a conversational AI model from business-domain model names."""
    terms = set(words(question))
    if not terms & {'model', 'models'}:
        return question
    # Preserve explicitly requested roles and non-AI meanings of 'model'.
    if terms & {'embed', 'embedding', 'embeddings', 'vector', 'vectors', 'classifier',
                'classification', 'rerank', 'reranking', 'vision', 'rewrite'}:
        return question
    business = terms & {'vehicle', 'motorcycle', 'bike', 'car', 'product', 'database', 'schema', 'orm'}
    if business and not terms & {'ai', 'llm'}:
        return question
    if terms & {'bot', 'chatbot', 'chat', 'answer', 'answers', 'answering', 'respond', 'response', 'completion'}:
        return 'chat model'
    return question


def word_stem(token):
    """A small inflection family, also matching identifier parts such as EMBED_MODEL."""
    if token.endswith('s') and len(token) > 4 and not token.endswith('ss'):
        token = token[:-1]
    if token.endswith('ing') and len(token) > 6:
        token = token[:-3]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
    return token


ASSIGNMENT = re.compile(r'^\s*(?:(?:export|const|let|var)\s+)*[\"\']?([A-Za-z_][\w]*)[\"\']?'
                        r'\s*(?::\s*[A-Za-z_][\w.\[\], |]*)?\s*(?:=(?!=)|:)\s*(.+)')


def definition_coverage(text, groups, path=''):
    """Prefer named values and documentation headings over incidental mentions."""
    best = 0
    for line in text.splitlines():
        if path.lower().endswith(('.md', '.markdown')) and re.match(r'^(?:#{2,6}\s+|\*\*[^*]+\*\*\s*$)', line):
            best = max(best, sum(bool(set(words(line)) & group) for group in groups))
        match = ASSIGNMENT.match(line)
        if match and re.search(r'[\"\'\d\[{]', match[2]):
            names = set(words(match[1]))
            best = max(best, sum(bool(names & group) for group in groups))
    return best
SYNONYMS = {
    'login': ['auth','authentication','signin','session','password'],
    'signin': ['login','auth','session'], 'logout':['signout','session','revoke'],
    'signup':['register','registration','account'], 'payment':['checkout','billing','invoice'],
    'payments':['payment','checkout','billing'], 'database':['db','sql','model','schema'],
    'setup':['install','requirements','startup','readme'], 'start':['startup','run','readme'],
    'permission':['authorisation','authorization','role','access'],
    'error':['exception','raise','catch','error'], 'test':['pytest','spec','test'],
    # Jira and Slack content sits in the same index as the code, and people ask about it in
    # their own words: ticket for what Jira calls an issue, decision for what Slack recorded.
    'ticket':['issue','story','bug','task','jira'], 'issue':['ticket','bug','story','task'],
    'bug':['defect','issue','error','fix'], 'requirement':['acceptance','criteria','story','spec'],
    'decision':['agreed','decided','proposal','discussion'],
    'discussion':['thread','message','channel','slack'],
}


TEST_PATH = re.compile(r'(^|/)(tests?|spec|__tests__|testing)/|(^|/)test_[^/]*$|_test\.[A-Za-z]+$|\.(test|spec)\.[A-Za-z]+$', re.I)
# Copied-in component libraries and generated bundles are in the repository but nobody wrote
# them here, so they are evidence about a dependency rather than about this project.
VENDOR_PATH = re.compile(r'(^|/)(components/ui|ui/components|third_?party|external|generated)/|'
                         r'\.(min|bundle|generated)\.[A-Za-z]+$', re.I)
ISSUE_KEY = re.compile(r'\b([A-Za-z][A-Za-z0-9_]{0,20})-(\d{1,6})\b')
# Slack and Jira content shares the chunk table with the repository's files, told apart only by
# the prefix its path carries. Written once, here, so a caller that needs to tell them apart
# cannot drift from the ones that stored them.
SOURCE_PREFIXES = ('slack/', 'jira/')
MIN_CHUNK_CHARS = 80
PATH_MATCH_BONUS = 1.5
MAX_TEST_SOURCES = 2
MAX_VENDOR_SOURCES = 1
# A match of sixty characters is not something a reader can judge, so a short chunk is grown
# from its neighbours in the same file until it carries enough to read.
WIDEN_TO_CHARS = 1400
WIDEN_MAX_LINES = 60
# Reciprocal rank fusion's damping constant. Sixty is the usual choice and keeps a single
# first place from dominating a chunk that several queries agree on further down.
RRF_K = 60
# Two floors decide which near neighbours count as evidence at all. The absolute one throws
# out a chunk pointing the other way. The relative one is what actually does the work, because
# how close "unrelated" sits to zero depends entirely on the embedding model: real models put
# two unrelated paragraphs around 0.4, not around 0. Keeping only what scores most of what the
# best match scored is a judgement the model's own scale makes for us.
SEMANTIC_FLOOR = 0.15
SEMANTIC_MARGIN = 0.6
# How much a semantic ranking counts against a lexical one when the two are fused. Swept over
# the labelled set rather than guessed at: python -m pka.evaluate --sweep.
#
# The guess going in was that this belonged below one, so that an approximate match could
# never overrule an exact one. The measurement said otherwise. Between weight 0 and weight 3
# every band improves, lexical included, going from mrr 0.73 to 0.85 on the questions that
# share words with their answer. Word matching was not being protected by a low weight, it
# was being left to fail alone on the many questions where the asker's words and the code's
# words are different.
#
# Three is the top of a flat region that starts around two; five is past it and falls away.
# The set is twenty questions, so treat anything between two and three as the same answer and
# re-run the sweep when the set grows.
SEMANTIC_WEIGHT = float(os.getenv('PKA_SEMANTIC_WEIGHT', '3.0'))
# How much of a question has to be made of words this project never uses before a search that
# meaning-based retrieval already rejected is treated as not being about the project at all.
# Zero means that rejection is enough on its own.
#
# Swept on both labelled sets. The score on answerable questions does not move at all between
# zero and one, on either repository, while the score on questions that should be refused goes
# from 0.25 to 1.0 as it drops to zero. Requiring unknown words on top of the semantic
# rejection bought nothing and cost every off-topic question phrased in ordinary English:
# "who won the world cup in 1998" is four common words that any large repository contains
# somewhere in its documentation, so it slipped through a rule built on unknown words while
# meaning-based retrieval had already correctly found nothing.
OFF_TOPIC_UNKNOWN_RATIO = float(os.getenv('PKA_OFF_TOPIC_RATIO', '0.0'))


def is_source_path(path: str) -> bool:
    """True for a Slack message or a Jira issue, false for a file in the repository."""
    return path.startswith(SOURCE_PREFIXES)


def words(text: str) -> list[str]:
    # SCRUM-17 split into scrum and 17 matches any chunk that happens to contain either, so the
    # key is kept whole as well. Asking about one named ticket is otherwise impossible.
    keys = [a.lower() + b for a, b in ISSUE_KEY.findall(text)]
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return re.findall(r'[A-Za-z0-9]+', text.lower()) + keys


def small_talk(text: str) -> bool:
    """True when nothing typed is a word worth searching this project for.

    A greeting, a thank-you or an empty pleasantry leaves no term behind once the stop list
    has done its work. Answering one by retrieving whatever file contains the word is worse
    than saying plainly that it was not a question about the project.
    """
    return not [t for t in words(text) if t not in STOP]


def widen(row: dict, siblings) -> tuple[str, int, int]:
    """Grow a short match outwards into the lines around it, inside the documented excerpt size.

    Boundary splitting produces many small pieces: a heading, a one line helper, a decorator.
    Five of those filled a prompt with a few hundred characters out of a budget of several
    thousand, so the model was answering from almost nothing. Ranking still happens on the
    small piece, which is the precise part; only what gets read is widened. The piece that
    matched stays inside the result and the line numbers follow what is actually returned,
    so a citation still points at the lines the reader is shown.
    """
    text, start, end = row['text'], row['start'], row['end']
    if len(text) >= WIDEN_TO_CHARS or not siblings:
        return text, start, end
    ordered = sorted(siblings, key=lambda s: s['start'])
    here = next((i for i, s in enumerate(ordered)
                 if s['start'] == start and s['end'] == end), None)
    if here is None:
        return text, start, end
    low = high = here
    growing = True
    while growing and len(text) < WIDEN_TO_CHARS:
        growing = False
        if high + 1 < len(ordered):
            following = ordered[high + 1]
            if (len(text) + len(following['text']) + 1 <= LIMITS.chunk_chars
                    and following['end'] - start + 1 <= WIDEN_MAX_LINES):
                # Neighbours are not always touching: a run of blank lines belongs to no chunk
                # because an empty one is never stored. Those lines go back in, otherwise the
                # line numbers would stop describing the text and a citation would point astray.
                text += '\n' * (following['start'] - end) + following['text']
                end, high, growing = following['end'], high + 1, True
        if low and len(text) < WIDEN_TO_CHARS:
            preceding = ordered[low - 1]
            if (len(text) + len(preceding['text']) + 1 <= LIMITS.chunk_chars
                    and end - preceding['start'] + 1 <= WIDEN_MAX_LINES):
                text = preceding['text'] + '\n' * (start - preceding['end']) + text
                start, low, growing = preceding['start'], low - 1, True
    return text, start, end


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
            CREATE TABLE IF NOT EXISTS knowledge_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
            INSERT OR IGNORE INTO knowledge_state VALUES(1,0);
            CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, scan_id INTEGER, path TEXT,
                start INTEGER, end INTEGER, text TEXT, symbols TEXT, split INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(path, symbols, text, tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS vectors (chunk_id INTEGER PRIMARY KEY, scan_id INTEGER,
                vector BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS vector_models (scan_id INTEGER PRIMARY KEY, signature TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calibration (scan_id INTEGER, model TEXT, ceiling REAL,
                floor REAL, probes INTEGER, created TEXT, PRIMARY KEY (scan_id, model));
            CREATE TABLE IF NOT EXISTS overviews (commit_sha TEXT PRIMARY KEY, scan_id INTEGER,
                payload TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS source_imports (name TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS file_checkpoints (slot TEXT, scope TEXT, path TEXT, sha TEXT,
                payload TEXT NOT NULL, PRIMARY KEY(slot,path));
            CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluation_runs (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jira_explanations (issue_key TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decision_summaries (channel_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, question TEXT,
                response TEXT, elapsed REAL, created TEXT, rating TEXT DEFAULT 'not assessed',
                sufficiency TEXT DEFAULT 'not assessed');
            ''')
            self._migrate(db)
    @property
    def revision(self):
        # Committed alongside the snapshot: survives restart and cannot advance on rollback.
        with self.db() as db:
            return db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0]

    def _advance_revision(self, db):
        db.execute('UPDATE knowledge_state SET revision=revision+1 WHERE id=1')
        self._vocab = None

    def _migrate(self, db):
        # Added after the first release, so an existing database is upgraded in place.
        columns = {r[1] for r in db.execute('PRAGMA table_info(chunks)').fetchall()}
        if 'url' not in columns:
            db.execute('ALTER TABLE chunks ADD COLUMN url TEXT')
        if 'metadata' not in columns:
            db.execute("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")

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
            self._advance_revision(db)
            for name in ('jira', 'slack'):
                for key in ('read_at', 'import_report'):
                    (merged.get(name) or {}).pop(key, None)
            db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(merged),))
            for table in ('chunks','search','answers','overviews','scans','vectors','vector_models','source_imports','calibration','jira_explanations','decision_summaries','file_checkpoints','evaluation_runs'):
                db.execute('DELETE FROM '+table)
            db.execute('UPDATE active SET scan_id=NULL')
    @staticmethod
    def source_scope(name, value):
        if name == 'local':
            return {'repo':value.get('repo', '')}
        if name == 'jira':
            return {'project':str(value.get('project', '')).upper()}
        if name == 'slack':
            return {'workspace':value.get('workspace', ''),
                    'channels':sorted([c['id'], c['name']] for c in value.get('channels', []))}
        raise ValueError('Unknown source.')

    def _changed(self, db):
        """Derived content must never outlive the source snapshot it describes."""
        self._advance_revision(db)
        db.execute('DELETE FROM answers')
        db.execute('DELETE FROM evaluation_runs')
        db.execute('DELETE FROM overviews')
        db.execute('DELETE FROM calibration')
        db.execute('DELETE FROM jira_explanations')
        db.execute('DELETE FROM decision_summaries')

    def _drop_source(self, db, name):
        prefix = 'local://' if name == 'local' else name + '/'
        db.execute('DELETE FROM search WHERE rowid IN (SELECT id FROM chunks WHERE path LIKE ?)', (prefix+'%',))
        db.execute('DELETE FROM vectors WHERE chunk_id IN (SELECT id FROM chunks WHERE path LIKE ?)', (prefix+'%',))
        db.execute('DELETE FROM chunks WHERE path LIKE ?', (prefix+'%',))
        db.execute('DELETE FROM source_imports WHERE name=?', (name,))

    def configure_source(self, name, value):
        """A changed source selection removes its old content immediately."""
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            settings = json.loads(row[0]) if row else {}
            value = dict(value)
            if self.source_scope(name, settings.get(name) or {}) != self.source_scope(name, value):
                self._drop_source(db, name)
                if name == 'local':
                    db.execute("DELETE FROM file_checkpoints WHERE slot='local'")
                self._changed(db)
                value.pop('read_at', None)
                value.pop('import_report', None)
            settings[name] = value
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(settings),))
    def configure_slack(self, slack):
        self.configure_source('slack', slack)

    def source_import(self, name):
        with self.db() as db:
            row = db.execute('SELECT payload FROM source_imports WHERE name=?', (name,)).fetchone()
            return json.loads(row[0]) if row else None

    def discard_source(self, name, *, keep_checkpoints=False):
        """Remove inaccessible content and every answer/overview that could cite it."""
        with self.db() as db:
            self._drop_source(db, name)
            if name == 'local' and not keep_checkpoints:
                db.execute("DELETE FROM file_checkpoints WHERE slot='local'")
            self._changed(db)
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            settings = json.loads(row[0]) if row else {}
            source = settings.get(name) or {}
            source.pop('read_at', None)
            source.pop('import_report', None)
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(settings),))
    def new_scan(self, detail):
        with self.db() as db:
            self._changed(db)
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
            # Embedding input is exactly path + text. Preserve only exact inputs from
            # the same model/preprocessing; changed chunks are embedded after publication.
            signature = embed.signature() if embed.enabled() else ''
            reusable_vectors = {(r['path'], r['text']):r['vector'] for r in db.execute('''
                SELECT c.path,c.text,v.vector FROM chunks c JOIN vectors v ON c.id=v.chunk_id
                JOIN vector_models m ON v.scan_id=m.scan_id WHERE m.signature=?
                LIMIT ?''', (signature, embed.MAX_CHUNKS))} if signature else {}
            self._changed(db)
            db.execute('DELETE FROM source_imports')
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            if row:
                settings = json.loads(row[0])
                for name in ('jira', 'slack'):
                    for key in ('read_at', 'import_report'):
                        (settings.get(name) or {}).pop(key, None)
                db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(settings),))
            db.execute('DELETE FROM search')
            db.execute('DELETE FROM chunks')
            db.execute('DELETE FROM vectors')
            db.execute('DELETE FROM vector_models')
            reused_vectors = 0
            for c in chunks:
                cur = db.execute('INSERT INTO chunks(scan_id,path,start,end,text,symbols,split) VALUES(?,?,?,?,?,?,?)',
                    (scan_id,c['path'],c['start'],c['end'],c['text'],c['symbols'],int(c['split'])))
                db.execute('INSERT INTO search(rowid,path,symbols,text) VALUES(?,?,?,?)',
                    (cur.lastrowid,' '.join(words(c['path'])),c['symbols'],' '.join(words(c['text']))))
                vector = reusable_vectors.get((c['path'], c['text']))
                if vector is not None and reused_vectors < embed.MAX_CHUNKS:
                    db.execute('INSERT INTO vectors VALUES(?,?,?)', (cur.lastrowid, scan_id, vector))
                    reused_vectors += 1
            if reused_vectors:
                db.execute('INSERT INTO vector_models VALUES(?,?)', (scan_id, signature))
            detail['reused_vectors'] = reused_vectors
            db.execute('UPDATE active SET scan_id=?',(scan_id,))
            db.execute('UPDATE scans SET status=?,detail=? WHERE id=?',(detail['status'],json.dumps(detail),scan_id))
    def replace_source(self, scan_id, prefix, blocks, import_meta=None):
        """Replace one external source and its derived caches in one transaction.
    
        Reading again replaces what was read before rather than adding to it, so a message that
        was deleted or a channel that was removed from the list cannot linger in answers.
        """
        if prefix not in {'jira/', 'slack/', 'local://'}:
            raise ValueError('Unknown source prefix.')
        name = 'local' if prefix == 'local://' else prefix[:-1]
        with self.db() as db:
            stale = [r[0] for r in db.execute(
                'SELECT id FROM chunks WHERE scan_id=? AND path LIKE ?',(scan_id,prefix+'%')).fetchall()]
            for chunk_id in stale:
                db.execute('DELETE FROM search WHERE rowid=?',(chunk_id,))
            for chunk_id in stale:
                db.execute('DELETE FROM vectors WHERE chunk_id=?',(chunk_id,))
            db.execute('DELETE FROM chunks WHERE scan_id=? AND path LIKE ?',(scan_id,prefix+'%'))
            for block in blocks:
                cur = db.execute(
                    'INSERT INTO chunks(scan_id,path,start,end,text,symbols,split,url,metadata) VALUES(?,?,?,?,?,?,?,?,?)',
                    (scan_id,block['path'],block['start'],block['end'],block['text'],
                     block['symbols'],int(block['split']),block.get('url') or None,json.dumps(block.get('metadata') or {})))
                db.execute('INSERT INTO search(rowid,path,symbols,text) VALUES(?,?,?,?)',
                    (cur.lastrowid,' '.join(words(block['path'])),block['symbols'],' '.join(words(block['text']))))
            self._changed(db)
            db.execute('DELETE FROM source_imports WHERE name=?', (name,))
            if import_meta is not None:
                db.execute('INSERT INTO source_imports VALUES(?,?)', (name, json.dumps(import_meta)))
                row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
                settings = json.loads(row[0]) if row else {}
                settings.setdefault(name, {}).update(read_at=import_meta['report']['read_at'],
                                                     import_report=import_meta['report'])
                db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(settings),))
            return len(blocks)
    def replace_slack(self, scan_id, blocks):
        return self.replace_source(scan_id, 'slack/', blocks)
    def source_blocks(self, scan_id, prefix):
        with self.db() as db:
            return db.execute('SELECT COUNT(*) FROM chunks WHERE scan_id=? AND path LIKE ?',
                              (scan_id,prefix+'%')).fetchone()[0]
    def source_digests(self, scan_id, prefix):
        """Hashes of saved source text for permission-sensitive snapshot checks."""
        if prefix not in {'jira/', 'slack/'}:
            raise ValueError('Unknown source prefix.')
        grouped = {}
        with self.db() as db:
            for row in db.execute('SELECT path,text FROM chunks WHERE scan_id=? AND path LIKE ? ORDER BY path,start,id',
                                  (scan_id, prefix+'%')):
                grouped.setdefault(row['path'][len(prefix):], []).append(row['text'])
        return {key: hashlib.sha256('\n'.join(parts).encode()).hexdigest() for key, parts in grouped.items()}

    def jira_issues(self, scan_id):
        with self.db() as db:
            rows = db.execute('SELECT path,text,url FROM chunks WHERE scan_id=? AND path LIKE ? ORDER BY path,start,id',
                              (scan_id, 'jira/%')).fetchall()
        found = {}
        for row in rows:
            key = row['path'][5:]
            if key not in found:
                headline = row['text'].splitlines()[0] if row['text'] else key
                found[key] = {'key':key, 'title':headline.removeprefix(key+':').strip() or key,
                              'url':row['url'], 'excerpts':0}
            found[key]['excerpts'] += 1
        return list(found.values())

    def jira_excerpts(self, scan_id, key):
        with self.db() as db:
            rows = db.execute('SELECT path,start,end,text,url FROM chunks WHERE scan_id=? AND path=? ORDER BY start,id',
                              (scan_id, 'jira/'+key)).fetchall()
        return [{'source_id':f'J{i+1}', **dict(row)} for i,row in enumerate(rows)]

    def relationship_rows(self, scan_id, kind):
        condition = ("path LIKE 'slack/%'" if kind == 'discussions' else
                     "path NOT LIKE 'jira/%' AND path NOT LIKE 'slack/%'")
        with self.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,path,start,end,text,url FROM chunks WHERE scan_id=? AND '+condition+' ORDER BY path,start,id',
                (scan_id,))]

    def jira_explanation(self, key):
        with self.db() as db:
            row = db.execute('SELECT payload FROM jira_explanations WHERE issue_key=? AND revision=?',
                             (key, self.revision)).fetchone()
        return json.loads(row[0]) if row else None

    def save_jira_explanation(self, key, revision, payload):
        with self.db() as db:
            current = db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0]
            if current != revision:
                raise ValueError('The source revision changed before the explanation was saved.')
            db.execute('INSERT OR REPLACE INTO jira_explanations VALUES(?,?,?)',
                       (key, revision, json.dumps(payload)))
    def slack_blocks(self, scan_id):
        return self.source_blocks(scan_id, 'slack/')

    def slack_excerpts(self, scan_id, name):
        with self.db() as db:
            return [{**dict(row), 'metadata':json.loads(row['metadata'])} for row in db.execute(
                'SELECT id,path,start,end,text,url,metadata FROM chunks WHERE scan_id=? AND path=? ORDER BY start,id',
                (scan_id, 'slack/'+name))]

    def decision_summary(self, channel_id):
        with self.db() as db:
            row = db.execute('SELECT payload FROM decision_summaries WHERE channel_id=? AND revision=?',
                             (channel_id, self.revision)).fetchone()
        return json.loads(row[0]) if row else None

    def save_decision_summary(self, channel_id, revision, payload):
        with self.db() as db:
            if db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0] != revision:
                raise ValueError('Source information changed before the decision summary was saved.')
            db.execute('INSERT OR REPLACE INTO decision_summaries VALUES(?,?,?)',
                       (channel_id, revision, json.dumps(payload)))

    def invalidate(self, *, keep_checkpoints=False):
        with self.db() as db:
            if not keep_checkpoints:
                db.execute('DELETE FROM file_checkpoints')
            self._advance_revision(db)
            db.execute('UPDATE active SET scan_id=NULL')
            for table in ('chunks','search','answers','overviews','vectors','vector_models','source_imports','calibration','jira_explanations','decision_summaries','evaluation_runs'):
                db.execute('DELETE FROM '+table)
            row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
            if row:
                settings = json.loads(row[0])
                for name in ('jira', 'slack'):
                    for key in ('read_at', 'import_report'):
                        (settings.get(name) or {}).pop(key, None)
                db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(settings),))
    def recover(self):
        with self.db() as db:
            for row in db.execute('SELECT id,detail FROM jobs').fetchall():
                detail = json.loads(row['detail'])
                if detail['state'] in {'queued', 'running', 'cancelling'}:
                    detail.update(state='interrupted', finished_at=now(), code='interrupted',
                                  error='The app stopped before this job finished. Retry when ready.')
                    db.execute('UPDATE jobs SET detail=? WHERE id=?', (json.dumps(detail), row['id']))
            for row in db.execute("SELECT id,detail FROM scans WHERE status='running'").fetchall():
                detail = json.loads(row['detail'])
                detail.update(status='interrupted',finished=now(),error='Previous scan was interrupted. Start a new scan.')
                db.execute('UPDATE scans SET status=?,detail=? WHERE id=?',('interrupted',json.dumps(detail),row['id']))
                db.execute('UPDATE active SET scan_id=NULL')
    def create_job(self, detail):
        with self.db() as db:
            job_id = db.execute('INSERT INTO jobs(detail) VALUES(?)', (json.dumps(detail),)).lastrowid
            db.execute('DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 30)')
            return {**detail, 'id':job_id}

    def save_job(self, job):
        with self.db() as db:
            db.execute('UPDATE jobs SET detail=? WHERE id=?', (json.dumps(job), job['id']))

    def latest_job(self):
        with self.db() as db:
            row = db.execute('SELECT id,detail FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
            return {**json.loads(row['detail']), 'id':row['id']} if row else None

    def vocabulary(self, scan_id: int) -> set:
        """Every word that actually appears in this snapshot, used to understand the question.

        A generic synonym list cannot know that this project calls it authenticate rather than
        login, so the words the project itself uses are the better dictionary. Cached per scan
        because it is read once and asked many times.
        """
        cached = getattr(self, '_vocab', None)
        revision = self.revision
        if cached and cached[0] == (scan_id, revision):
            return cached[1]
        with self.db() as db:
            rows = db.execute('SELECT path,symbols,text FROM chunks WHERE scan_id=?',(scan_id,)).fetchall()
        vocab = set()
        for r in rows:
            vocab.update(words(r['path']))
            vocab.update(words(r['symbols'] or ''))
            vocab.update(words(r['text']))
        # A number carries meaning however short it is: issue 17, version 3, port 80. Dropping
        # everything under three characters made every ticket number an unknown word.
        vocab = {w for w in vocab if len(w) > 2 or w.isdigit()}
        self._vocab = ((scan_id, revision), vocab)
        return vocab

    def resolve(self, tokens: list[str], vocab: set) -> tuple[list[str], list[str], dict]:
        """Map what the user typed onto words this project really contains.

        Exact words pass through. A word that is not in the project is tried as a prefix, which
        catches a wrong ending, then by closeness, which catches a misspelling. A word that
        matches nothing is dropped and reported rather than left to dilute the ranking.
        """
        used, unknown, corrections = [], [], {}
        for t in tokens:
            family = sorted(w for w in vocab if word_stem(w) == word_stem(t))[:8]
            if t in vocab:
                used.append(t)
                used.extend(x for x in SYNONYMS.get(t, []) if x in vocab)
                continue
            # The project may simply call it something else: the user says login, the code says
            # authenticate. Try the known aliases before guessing at spelling.
            alias = family or [x for x in SYNONYMS.get(t, []) if x in vocab][:3]
            if alias:
                corrections[t] = alias
                used.extend(alias)
                continue
            # Only guess at a word long enough for a guess to be meaningful. Correcting a short
            # word turns "rom" into "from" and makes the search worse than leaving it out.
            near = []
            if len(t) >= 5:
                # Five, not four. A four-character stem let "thanks" match the word "than" that
                # happened to sit in a comment, so a thank-you was answered with three unrelated
                # files. Five still catches a wrong ending, because "connecting" stems to
                # "connect", and a genuine misspelling falls through to the closeness test below.
                stem = t[:max(5, len(t) - 3)]
                # Alphabetical order turned tickt into ticks. Closest in length is a better
                # guess at what was meant than whichever candidate happens to sort first.
                near = sorted((w for w in vocab if w.startswith(stem)),
                              key=lambda w: (abs(len(w) - len(t)), w))[:2]
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

    def _terms(self, question: str, scan: dict, info: dict | None = None):
        """Turn what was typed into the words this snapshot actually contains."""
        asked = question_words(question)
        # resolve already folds in aliases and spelling, so tokens are the final search terms
        tokens, unknown, corrections = self.resolve(asked, self.vocabulary(scan['id']))
        if info is not None:
            info.setdefault('asked', []).extend(x for x in asked if x not in info['asked'])
            info.setdefault('terms', []).extend(x for x in tokens if x not in info['terms'])
            info.setdefault('unknown', []).extend(x for x in unknown if x not in info['unknown'])
            info.setdefault('corrections', {}).update(corrections)
        return tokens

    def _ranked(self, db, tokens: list[str], scan: dict, groups=None) -> list[dict]:
        """One query's candidate chunks, best first, before anything is widened or capped."""
        if not tokens:
            return []
        expression = ' OR '.join('"'+t+'"' for t in tokens)
        rows = db.execute('''SELECT c.*, bm25(search,5,4,1) AS rank FROM search
            JOIN chunks c ON c.id=search.rowid WHERE search MATCH ? AND c.scan_id=?
            ORDER BY rank LIMIT 60''',(expression,scan['id'])).fetchall()
        groups = [g for g in (groups or []) if g]
        # OR alone lets a common word fill the candidate budget. Include chunks
        # matching all query concepts before ranking, with alternatives inside each.
        if len(groups) > 1:
            joint = ' AND '.join('(' + ' OR '.join('"' + t + '"' for t in sorted(g)) + ')' for g in groups)
            exact = db.execute('''SELECT c.*, bm25(search,5,4,1) AS rank FROM search
                JOIN chunks c ON c.id=search.rowid WHERE search MATCH ? AND c.scan_id=?
                ORDER BY rank LIMIT 20''', (joint, scan['id'])).fetchall()
            # Keep the original query's BM25 score for existing candidates.
            # Scores from differently expanded queries are not interchangeable.
            combined = {r['id']: r for r in rows}
            for row in exact:
                combined.setdefault(row['id'], row)
            rows = list(combined.values())
        # BM25 divides by document length, so a long chunk that repeats a word can outrank a file
        # whose folder is named after it. Someone asking about bug investigation wants
        # bug_investigation/, so reward a path that carries the words that were asked for.
        wanted = set(tokens)
        def rank(row):
            definition = definition_coverage(row['text'], groups, row['path'])
            # Only a definition matching the requested concept gets priority.
            # Counting all prose matches ahead of BM25 overvalues long comments
            # which mention several subsystems (e.g. a proxy mentioning an API).
            definition = definition if definition >= min(2, len(groups)) else 0
            return (-definition,
                    row['rank'] - PATH_MATCH_BONUS * len(wanted & set(words(row['path']))))
        return [dict(row, _direct_value=definition_coverage(row['text'], groups, row['path']) >= min(2, len(groups)))
                for row in sorted(rows, key=rank)]

    def prepare_vectors(self, scan_id: int, signature: str):
        """Retain source text; rebuild only derived vectors when model/preprocessing changes."""
        with self.db() as db:
            row = db.execute('SELECT signature FROM vector_models WHERE scan_id=?', (scan_id,)).fetchone()
            if not row or row[0] != signature:
                db.execute('DELETE FROM vectors WHERE scan_id=?', (scan_id,))
                db.execute('DELETE FROM calibration WHERE scan_id=?', (scan_id,))
                db.execute('INSERT OR REPLACE INTO vector_models VALUES(?,?)', (scan_id, signature))

    def unembedded(self, scan_id: int) -> list[dict]:
        """Chunks in this scan that have no vector yet, so a scan can be embedded in batches."""
        with self.db() as db:
            return [dict(r) for r in db.execute(
                'SELECT c.id, c.path, c.text FROM chunks c '
                'LEFT JOIN vectors v ON v.chunk_id=c.id '
                'WHERE c.scan_id=? AND v.chunk_id IS NULL ORDER BY c.id '
                'LIMIT MAX(0, ? - (SELECT COUNT(*) FROM vectors WHERE scan_id=?))',
                (scan_id, embed.MAX_CHUNKS, scan_id)).fetchall()]

    def save_vectors(self, scan_id: int, pairs: list[tuple[int, object]]) -> int:
        with self.db() as db:
            for chunk_id, vector in pairs:
                db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',
                           (chunk_id, scan_id, embed.pack(vector)))
            return len(pairs)

    def embedded(self, scan_id: int) -> int:
        with self.db() as db:
            return db.execute('SELECT COUNT(*) FROM vectors WHERE scan_id=?',(scan_id,)).fetchone()[0]

    def _nearest(self, db, vector, scan: dict, limit: int = 60) -> list[dict]:
        """The chunks closest in meaning to this vector, as one more ranking to fuse.

        Every vector is compared in Python rather than in SQL. A scan is a few hundred to a few
        thousand chunks of a few hundred floats, which is milliseconds, and an index built for
        vector search would be a dependency and a file format to maintain for no gain at this
        size. If a scan ever gets big enough for this to show, the honest fix is a real vector
        index behind this same method, not a cleverer loop.
        """
        rows = db.execute('SELECT c.*, v.vector FROM vectors v JOIN chunks c ON c.id=v.chunk_id '
                          'WHERE v.scan_id=?',(scan['id'],)).fetchall()
        if not rows:
            return []
        scored = []
        for row in rows:
            scored.append((embed.similarity(vector, embed.unpack(row['vector'])), row))
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        # Measured for this snapshot and this embedding model where one has been measured,
        # which is what lets the same code be right on a repository it has never seen.
        floor = self.floor_for(scan['id'])
        if best < floor:
            # Nothing in the snapshot is about this. Returning the least unrelated chunk would
            # be worse than returning none, because it would look like an answer.
            return []
        cut = max(floor, best * SEMANTIC_MARGIN)
        # The vector column is dropped here. It was selected to score the row and is raw bytes;
        # left in, it rides along into the chosen excerpts and the answer stops being JSON.
        # Nothing caught that until embeddings were switched on and measured.
        return [{k: v for k, v in dict(row, rank=-score).items() if k != 'vector'}
                for score, row in scored[:limit] if score >= cut]

    def semantic_ceiling(self, scan_id: int, probe_vectors: list) -> float:
        """The best similarity any deliberately irrelevant probe reaches in this snapshot.

        This is the number that makes the cut-off portable. An absolute similarity means
        something only against a particular embedding model and a particular body of text, so
        rather than carrying one repository's figure around in the source, each snapshot is
        asked where its own floor of meaninglessness sits.
        """
        with self.db() as db:
            rows = db.execute('SELECT vector FROM vectors WHERE scan_id=?', (scan_id,)).fetchall()
        if not rows or not probe_vectors:
            return 0.0
        stored = [embed.unpack(r['vector']) for r in rows]
        return max(embed.similarity(p, s) for p in probe_vectors for s in stored)

    def save_calibration(self, scan_id: int, model: str, ceiling: float, probes: int) -> float:
        """Store the cut-off for this snapshot and model, and return it."""
        floor = round(ceiling * embed.CALIBRATION_MARGIN, 4)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO calibration VALUES(?,?,?,?,?,?)',
                       (scan_id, model, round(ceiling, 4), floor, probes, now()))
        return floor

    def calibration(self, scan_id: int, model: str) -> dict | None:
        """What was measured for this snapshot and this model, or None if never measured.

        Keyed by model as well as by scan, because the scale of a similarity belongs to the
        model. Changing PKA_EMBED_MODEL must not inherit the previous model's cut-off.
        """
        with self.db() as db:
            row = db.execute('SELECT * FROM calibration WHERE scan_id=? AND model=?',
                             (scan_id, model)).fetchone()
        return dict(row) if row else None

    def floor_for(self, scan_id: int) -> float:
        """The cut-off to apply: the measured one when there is one, the fallback otherwise."""
        found = self.calibration(scan_id, embed.model()) if embed.enabled() else None
        return found['floor'] if found else SEMANTIC_FLOOR

    def nearest(self, scan: dict, vector) -> list[dict]:
        """The chunks nearest this vector in meaning, with nothing lexical mixed in.

        Separate from search_many so the semantic half can be inspected and measured on its
        own, which is what the plan's comparison between word matching and embeddings needs.
        """
        with self.db() as db:
            return self._nearest(db, vector, scan)

    def _fuse(self, rankings: list[list[dict]], weights: list[float] | None = None) -> list[dict]:
        """Combine several rankings into one by reciprocal rank fusion.

        A topic such as "how it is set up" is not one search. Asking separately about installing,
        about running and about environment variables, then merging by position rather than by
        score, pulls in the file that only the third query knew about. Positions are comparable
        across queries in a way BM25 scores are not, which is the whole reason for doing it this
        way: a chunk ranked third twice beats one ranked first once and nowhere else.

        A ranking may also count for less than another. The weights are how a semantic ranking
        contributes without being able to outvote an exact word match on its own.
        """
        if len(rankings) == 1:
            return rankings[0]
        weights = weights or [1.0] * len(rankings)
        scored, best = {}, {}
        for ranking, weight in zip(rankings, weights):
            for position, row in enumerate(ranking):
                key = (row['path'], row['start'], row['end'])
                scored[key] = scored.get(key, 0.0) + weight / (RRF_K + position + 1)
                best.setdefault(key, row)
        return [best[k] for k in sorted(scored, key=lambda k: -scored[k])]

    def _assemble(self, db, rows: list[dict], scan: dict, max_sources: int,
                  context_chars: int, test_cap: int, vendor_cap: int) -> list[dict]:
        """Widen, diversify and budget the candidates into the excerpts that get read."""
        # Ranking is sharper on small pieces, but reading needs more than the piece that
        # matched, so every candidate file's chunks are kept to grow the excerpt from.
        paths = sorted({r['path'] for r in rows})
        neighbours = {}
        if paths:
            placeholders = ','.join('?' * len(paths))
            for n in db.execute('SELECT path,start,end,text FROM chunks WHERE scan_id=? '
                                'AND path IN (' + placeholders + ') ORDER BY path,start',
                                (scan['id'], *paths)).fetchall():
                neighbours.setdefault(n['path'], []).append(n)

        # Keep multiple relevant files and a bounded prompt. No model-selected tools.
        def choose(min_chars: int, test_cap: int, vendor_cap: int, per_file: int) -> list[dict]:
            selected, counts, budget, tests, vendored = [], {}, 0, 0, 0
            seen = set()
            for row in rows:
                d = dict(row)
                direct_value = d.pop('_direct_value', False)
                required_context = d.pop('_required_context', False)
                # A test is real evidence and sometimes the clearest specification, but a question
                # about how something works should be answered mostly from the code that does it.
                is_test = bool(TEST_PATH.search(d['path']))
                if is_test and tests >= test_cap:
                    continue
                # A copied-in component library answers questions about itself very well and
                # crowds out the project, so at most one such excerpt is ever shown.
                is_vendor = bool(VENDOR_PATH.search(d['path']))
                if is_vendor and vendored >= vendor_cap:
                    continue
                if counts.get(d['path'],0) >= per_file and not required_context:
                    continue
                d['text'], d['start'], d['end'] = widen(d, neighbours.get(d['path'], ()))
                key = (d['path'], d['start'], d['end'])
                if key in seen:
                    continue
                # Checked after widening, because a short chunk that grew is now worth reading
                # and the budget has to account for what is actually sent.
                if len(d['text'].strip()) < min_chars and not direct_value:
                    continue
                if budget+len(d['text']) > context_chars:
                    continue
                counts[d['path']] = counts.get(d['path'],0)+1
                seen.add(key)
                budget += len(d['text'])
                tests += is_test
                vendored += is_vendor
                d['source_id'] = 'S'+str(len(selected)+1)
                d['url'] = d.get('url') or (None if scan.get('demo') else source_url(
                    scan['repo'], scan['commit'], d['path'], d['start'], d['end']))
                selected.append(d)
                if len(selected) >= max_sources:
                    break
            return selected
        # One excerpt per file first, so a reader is shown several files rather than one file
        # twice. Only if that leaves room unused does a second excerpt from a file come back.
        spread = choose(MIN_CHUNK_CHARS, test_cap, vendor_cap, 1)
        if len(spread) >= max_sources:
            return spread
        # Prefer substantial, non-test evidence; fall back rather than return nothing at all.
        return (choose(MIN_CHUNK_CHARS, test_cap, vendor_cap, 2) or spread
                or choose(0, max_sources, max_sources, 2))

    def search(self, question: str, scan: dict, info: dict | None = None,
               max_sources: int | None = None, context_chars: int | None = None,
               test_cap: int | None = None, vendor_cap: int | None = None,
               query_vectors: list | None = None, context_question: str | None = None) -> list[dict]:
        # A direct question naming a file must not borrow another file's values.
        # Relationship/explanation questions keep cross-file retrieval available.
        related = re.search(r'\b(?:how|why|explain|describe|depend\w*|call\w*|referenc\w*|'
                            r'across|between|impact|interact\w*|connect\w*|compar\w*|uses)\b|\bused by\b', question, re.I)
        named = [] if related else [path for path in self.code_paths(scan['id'])
            if re.search(r'(?<![\w./-])' + re.escape(path) + r'(?![\w./-])', question, re.I)]
        retrieval_question = model_role_query(question)
        if info is not None and retrieval_question != question:
            info['interpretation'] = 'chat model configuration'
        queries = [retrieval_question] + ([context_question] if context_question else [])
        found = self.search_many(queries, scan, info, max_sources, context_chars,
                                 test_cap, vendor_cap, query_vectors, path_filter=named)
        references = comparison_references(question, found)
        if not references:
            return found
        # A discussion can quote a condition without its definition. Retrieve both
        # from indexed code so boundary arithmetic uses the actual operator/value.
        with self.db() as db:
            related = []
            for left, right in references:
                rows = db.execute("SELECT * FROM chunks WHERE scan_id=? AND path LIKE '%.py' AND text LIKE ?",
                                  (scan['id'], '%' + right + '%')).fetchall()
                code = [dict(row) for row in rows if not is_source_path(row['path'])
                        and (not named or row['path'] in named)]
                conditions = [row for row in code if re.search(
                    r'\b' + re.escape(left) + r'\s*(?:<=|>=|==|!=|<|>)\s*' + re.escape(right) + r'\b', row['text'])]
                paths = {row['path'] for row in conditions}
                definitions = [row for row in code if row['path'] in paths and re.search(
                    r'^' + re.escape(right) + r'\s*=', row['text'], re.M)]
                related.extend([{**row, '_direct_value': True, '_required_context': True}
                                for row in definitions + conditions])
            if related:
                found = self._assemble(db, related + found, scan, max_sources or LIMITS.max_sources,
                                       context_chars or LIMITS.context_chars,
                                       MAX_TEST_SOURCES if test_cap is None else test_cap,
                                       MAX_VENDOR_SOURCES if vendor_cap is None else vendor_cap)
        return found

    def search_many(self, questions: list[str], scan: dict, info: dict | None = None,
                    max_sources: int | None = None, context_chars: int | None = None,
                    test_cap: int | None = None, vendor_cap: int | None = None,
                    query_vectors: list | None = None, path_filter=None) -> list[dict]:
        """Retrieve for several phrasings of the same need and fuse them into one set.

        One question is the ordinary case and behaves exactly as a single search did. An
        overview topic passes several, because "what it is built with" is asked differently by
        a requirements file, an import line and a readme.
        """
        max_sources = max_sources or LIMITS.max_sources
        context_chars = context_chars or LIMITS.context_chars
        # A topic about how the project is set up is badly served by two test files; a topic
        # about how it is tested is served by nothing else. The caller knows which it is.
        test_cap = MAX_TEST_SOURCES if test_cap is None else test_cap
        # Copied-in component libraries describe themselves well and answer nothing about this
        # project, so a topic explaining how this project is built asks for none of them.
        vendor_cap = MAX_VENDOR_SOURCES if vendor_cap is None else vendor_cap
        # Kept whatever the caller passed, because the off-topic test below reads it.
        info = {} if info is None else info
        if info is not None:
            info.setdefault('asked', [])
            info.setdefault('terms', [])
            info.setdefault('unknown', [])
            info.setdefault('corrections', {})
        with self.db() as db:
            rankings, weights, anchors = [], [], []
            for question in questions:
                tokens = self._terms(question, scan, info)
                vocab = self.vocabulary(scan['id'])
                groups = [set(self.resolve([word], vocab)[0]) |
                          {v for v in vocab if word_stem(v) == word_stem(word)}
                          for word in question_words(question)]
                ranked = self._ranked(db, tokens, scan, groups)
                if ranked:
                    rankings.append(ranked)
                    weights.append(1.0)
                    if ranked[0].get('_direct_value'):
                        anchors.append((ranked[0]['path'], ranked[0]['start'], ranked[0]['end']))
            # Semantic candidates are one more ranking, not a replacement. A question whose
            # words are all in the project still gets its exact matches; a question phrased in
            # words the project never uses now has something to find.
            for vector in (query_vectors or []):
                nearest = self._nearest(db, vector, scan)
                if nearest:
                    rankings.append(nearest)
                    weights.append(SEMANTIC_WEIGHT)
                    if info is not None:
                        info['semantic'] = info.get('semantic', 0) + 1
            if not rankings:
                return []
            # Two weak signals together mean the question is not about this project at all.
            # "How do I train a puppy" matched the word train in a machine learning file, and
            # "the capital of France" matched capitalize, each on one word out of two while
            # meaning-based retrieval found nothing above the measured floor. Either signal
            # alone is normal: a question can use words the code never uses and still be
            # answerable, and a well worded question can land below the floor. Both at once
            # has not once been a real question.
            #
            # This only applies where meaning-based retrieval actually ran. Without it there
            # is no second opinion, and refusing on unknown words alone would throw away the
            # ordinary case of someone naming a thing differently from the code.
            asked, unmatched = info.get('asked') or [], info.get('unknown') or []
            if query_vectors and self.embedded(scan['id']) and not info.get('semantic') and not anchors:
                if asked and len(unmatched) >= OFF_TOPIC_UNKNOWN_RATIO * len(asked):
                    info['off_topic'] = True
                    return []
            rows = self._fuse(rankings, weights)
            # Semantic matches can crowd a literal configuration definition out of
            # the bounded prompt. Preserve each query's strongest direct value;
            # use fused relevance for the remaining evidence.
            rows.sort(key=lambda row: (row['path'], row['start'], row['end']) not in anchors)
            if path_filter:
                rows = [row for row in rows if row['path'] in path_filter]
                info['focused_paths'] = path_filter
            found = self._assemble(db, rows, scan, max_sources, context_chars,
                                   test_cap, vendor_cap)
        if info is not None:
            info['candidates'] = len(rows)
            info['queries'] = len(questions)
        return found
    def record_answer(self, scan_id, question, response, elapsed):
        with self.db() as db:
            return db.execute('INSERT INTO answers(scan_id,question,response,elapsed,created) VALUES(?,?,?,?,?)',
                (scan_id,question,json.dumps(response),elapsed,now())).lastrowid
    def save_overview(self, scan_id, commit_sha, payload):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO overviews VALUES(?,?,?,?)',
                       (commit_sha,scan_id,json.dumps(payload),now()))
    def overview(self, commit_sha):
        """Cached overview for the current snapshot; every source refresh invalidates it.

        A commit alone cannot identify scan coverage, imported issues or messages.
        """
        with self.db() as db:
            row = db.execute('SELECT payload,created FROM overviews WHERE commit_sha=?',(commit_sha,)).fetchone()
            if not row:
                return None
            return {**json.loads(row['payload']), 'built_at':row['created']}
    def indexed_paths(self, scan_id):
        """Every path in this scan, repository files and other sources together.

        Slack messages and Jira issues live in the same table under their own prefix, so what
        comes back is not all files. Use `code_paths` unless both are genuinely wanted: the
        suggested reading order asked this one, and offered `jira/SCRUM-17` as a file to read
        with a link to that path inside the repository, where it has never existed.
        """
        with self.db() as db:
            return [r[0] for r in db.execute(
                'SELECT DISTINCT path FROM chunks WHERE scan_id=? ORDER BY path',(scan_id,)).fetchall()]

    def code_paths(self, scan_id):
        """Only the repository files, which is what nearly every caller means."""
        return [p for p in self.indexed_paths(scan_id) if not is_source_path(p)]
    def file_lines(self, scan_id, path) -> list[tuple[int, str]]:
        """Rebuild one file as numbered lines from the chunks that were stored for it.

        The deterministic facts need to say which line a dependency or a route is declared on,
        and a chunk already records the line its text begins at. Blank lines are never stored,
        so they are simply absent here rather than renumbering everything after them, which is
        what would break a citation.
        """
        with self.db() as db:
            rows = db.execute('SELECT start,text FROM chunks WHERE scan_id=? AND path=? ORDER BY start',
                              (scan_id,path)).fetchall()
        numbered = {}
        for r in rows:
            for offset,line in enumerate(r['text'].splitlines()):
                numbered.setdefault(r['start']+offset, line)
        return [(n,numbered[n]) for n in sorted(numbered)]
    def feedback(self, answer_id, rating, sufficiency):
        with self.db() as db:
            cur = db.execute('UPDATE answers SET rating=?,sufficiency=? WHERE id=?',(rating,sufficiency,answer_id))
            return cur.rowcount == 1
