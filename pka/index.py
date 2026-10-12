"""A small replaceable lexical retrieval layer: SQLite FTS5 + paths + symbols."""
import ast
import difflib
from contextlib import contextmanager
import json
from pathlib import PurePosixPath
import re
import sqlite3
from pka import embed
from pka.config import LIMITS, now, source_url

STOP = set('how does do did the a an is are was were it in on of to for and or can i we my this that work works please explain what where when why with from'.split())
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


def is_source_path(path: str) -> bool:
    """True for a Slack message or a Jira issue, false for a file in the repository."""
    return path.startswith(SOURCE_PREFIXES)


def words(text: str) -> list[str]:
    # SCRUM-17 split into scrum and 17 matches any chunk that happens to contain either, so the
    # key is kept whole as well. Asking about one named ticket is otherwise impossible.
    keys = [a.lower() + b for a, b in ISSUE_KEY.findall(text)]
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return re.findall(r'[A-Za-z0-9]+', text.lower()) + keys


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
            CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, scan_id INTEGER, path TEXT,
                start INTEGER, end INTEGER, text TEXT, symbols TEXT, split INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(path, symbols, text, tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS vectors (chunk_id INTEGER PRIMARY KEY, scan_id INTEGER,
                vector BLOB NOT NULL);
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
            for table in ('chunks','search','answers','overviews','scans','vectors'):
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
            db.execute('DELETE FROM vectors')
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
            for chunk_id in stale:
                db.execute('DELETE FROM vectors WHERE chunk_id=?',(chunk_id,))
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
            for table in ('chunks','search','answers','overviews','vectors'):
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
        # A number carries meaning however short it is: issue 17, version 3, port 80. Dropping
        # everything under three characters made every ticket number an unknown word.
        vocab = {w for w in vocab if len(w) > 2 or w.isdigit()}
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
        asked = list(dict.fromkeys(t for t in words(question) if t not in STOP))[:16]
        # resolve already folds in aliases and spelling, so tokens are the final search terms
        tokens, unknown, corrections = self.resolve(asked, self.vocabulary(scan['id']))
        if info is not None:
            info.setdefault('asked', []).extend(x for x in asked if x not in info['asked'])
            info.setdefault('terms', []).extend(x for x in tokens if x not in info['terms'])
            info.setdefault('unknown', []).extend(x for x in unknown if x not in info['unknown'])
            info.setdefault('corrections', {}).update(corrections)
        return tokens

    def _ranked(self, db, tokens: list[str], scan: dict) -> list[dict]:
        """One query's candidate chunks, best first, before anything is widened or capped."""
        if not tokens:
            return []
        expression = ' OR '.join('"'+t+'"' for t in tokens)
        rows = db.execute('''SELECT c.*, bm25(search,5,4,1) AS rank FROM search
            JOIN chunks c ON c.id=search.rowid WHERE search MATCH ? AND c.scan_id=?
            ORDER BY rank LIMIT 60''',(expression,scan['id'])).fetchall()
        # BM25 divides by document length, so a long chunk that repeats a word can outrank a file
        # whose folder is named after it. Someone asking about bug investigation wants
        # bug_investigation/, so reward a path that carries the words that were asked for.
        wanted = set(tokens)
        return sorted(rows, key=lambda r: r['rank'] - PATH_MATCH_BONUS * len(wanted & set(words(r['path']))))

    def unembedded(self, scan_id: int) -> list[dict]:
        """Chunks in this scan that have no vector yet, so a scan can be embedded in batches."""
        with self.db() as db:
            return [dict(r) for r in db.execute(
                'SELECT c.id, c.path, c.text FROM chunks c '
                'LEFT JOIN vectors v ON v.chunk_id=c.id '
                'WHERE c.scan_id=? AND v.chunk_id IS NULL ORDER BY c.id LIMIT ?',
                (scan_id, embed.MAX_CHUNKS)).fetchall()]

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
        if best < SEMANTIC_FLOOR:
            # Nothing in the snapshot is about this. Returning the least unrelated chunk would
            # be worse than returning none, because it would look like an answer.
            return []
        cut = max(SEMANTIC_FLOOR, best * SEMANTIC_MARGIN)
        return [dict(row, rank=-score) for score, row in scored[:limit] if score >= cut]

    def nearest(self, scan: dict, vector) -> list[dict]:
        """The chunks nearest this vector in meaning, with nothing lexical mixed in.

        Separate from search_many so the semantic half can be inspected and measured on its
        own, which is what the plan's comparison between word matching and embeddings needs.
        """
        with self.db() as db:
            return self._nearest(db, vector, scan)

    def _fuse(self, rankings: list[list[dict]]) -> list[dict]:
        """Combine several rankings into one by reciprocal rank fusion.

        A topic such as "how it is set up" is not one search. Asking separately about installing,
        about running and about environment variables, then merging by position rather than by
        score, pulls in the file that only the third query knew about. Positions are comparable
        across queries in a way BM25 scores are not, which is the whole reason for doing it this
        way: a chunk ranked third twice beats one ranked first once and nowhere else.
        """
        if len(rankings) == 1:
            return rankings[0]
        scored, best = {}, {}
        for ranking in rankings:
            for position, row in enumerate(ranking):
                key = (row['path'], row['start'], row['end'])
                scored[key] = scored.get(key, 0.0) + 1.0 / (RRF_K + position + 1)
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
            for row in rows:
                d = dict(row)
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
                if counts.get(d['path'],0) >= per_file:
                    continue
                d['text'], d['start'], d['end'] = widen(d, neighbours.get(d['path'], ()))
                # Checked after widening, because a short chunk that grew is now worth reading
                # and the budget has to account for what is actually sent.
                if len(d['text'].strip()) < min_chars:
                    continue
                if budget+len(d['text']) > context_chars:
                    continue
                counts[d['path']] = counts.get(d['path'],0)+1
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
               query_vectors: list | None = None) -> list[dict]:
        return self.search_many([question], scan, info, max_sources, context_chars,
                                test_cap, vendor_cap, query_vectors)

    def search_many(self, questions: list[str], scan: dict, info: dict | None = None,
                    max_sources: int | None = None, context_chars: int | None = None,
                    test_cap: int | None = None, vendor_cap: int | None = None,
                    query_vectors: list | None = None) -> list[dict]:
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
        if info is not None:
            info.setdefault('asked', [])
            info.setdefault('terms', [])
            info.setdefault('unknown', [])
            info.setdefault('corrections', {})
        with self.db() as db:
            rankings = []
            for question in questions:
                tokens = self._terms(question, scan, info)
                ranked = self._ranked(db, tokens, scan)
                if ranked:
                    rankings.append(ranked)
            # Semantic candidates are one more ranking, not a replacement. A question whose
            # words are all in the project still gets its exact matches; a question phrased in
            # words the project never uses now has something to find.
            for vector in (query_vectors or []):
                nearest = self._nearest(db, vector, scan)
                if nearest:
                    rankings.append(nearest)
                    if info is not None:
                        info['semantic'] = info.get('semantic', 0) + 1
            if not rankings:
                return []
            rows = self._fuse(rankings)
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
        """The cached overview for this commit, or None. Keyed by commit so a refresh that
        lands on the same commit keeps it and a new commit rebuilds it."""
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
