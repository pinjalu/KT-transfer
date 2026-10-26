"""Private file checkpoints, separate from searchable/published project content."""
import hashlib
import json
from dataclasses import asdict

from pka.config import LIMITS


class FileCheckpoints:
    def __init__(self, index, slot, repo, branch, identity, demo=False):
        self.index, self.slot = index, slot
        self.revision = index.revision
        # A policy change must re-read files, even if their content hashes match.
        self.scope = hashlib.sha256(json.dumps(
            [1, repo, branch, identity, demo, asdict(LIMITS)], sort_keys=True).encode()).hexdigest()
        with index.db() as db:
            db.execute('DELETE FROM file_checkpoints WHERE slot=? AND scope<>?', (slot, self.scope))
            self.files = {r['path']: {'sha':r['sha'], 'result':json.loads(r['payload'])}
                          for r in db.execute('SELECT path,sha,payload FROM file_checkpoints WHERE slot=? AND scope=?',
                                              (slot, self.scope))}

    def hashes(self):
        return {path:entry['sha'] for path,entry in self.files.items()}

    def get(self, item):
        saved = self.files.get(item['path'])
        if not item.get('skip') and item.get('sha') and saved and saved['sha'] == item['sha']:
            return {**saved['result'], 'reused':True}
        return None

    def prune(self, entries):
        """Drop deleted, changed and excluded files against the newly authorized manifest."""
        keep = {e['path'] for e in entries if self.get(e) is not None}
        with self.index.db() as db:
            for path in self.files.keys() - keep:
                db.execute('DELETE FROM file_checkpoints WHERE slot=? AND path=?', (self.slot, path))
        self.files = {path:value for path,value in self.files.items() if path in keep}

    def save(self, item, result):
        if (not isinstance(result, dict) or result.get('skip') or not item.get('sha')
                or result.get('sha') != item['sha'] or not isinstance(result.get('text'), str)):
            return
        payload = {k:result[k] for k in ('text', 'bytes', 'sha')}
        others = [value for path,value in self.files.items() if path != item['path']]
        if (len(others) >= LIMITS.max_files or result['bytes'] > LIMITS.max_file_bytes
                or sum(v['result']['bytes'] for v in others) + result['bytes'] > LIMITS.max_total_bytes):
            return
        with self.index.db() as db:
            if db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0] != self.revision:
                return
            db.execute('INSERT OR REPLACE INTO file_checkpoints VALUES(?,?,?,?,?)',
                       (self.slot, self.scope, item['path'], item['sha'], json.dumps(payload)))
        self.files[item['path']] = {'sha':item['sha'], 'result':payload}
