"""Only completed, validated topics are resumed; never cache failures as successes."""
import json
from pka import monitoring
from pka.config import now
from pka.llm.config import digest, PROMPT_VERSION
from pka.connectors.base import SourceError


def key(scan, revision, topic, sources, configuration, generator='default'):
    return digest({'repo':scan['repo'],'commit':scan['commit'],'scan_id':scan['id'],
                   'revision':revision,'topic':topic,'sources':sources,'configuration':configuration,
                   'prompt_version':PROMPT_VERSION,'generator':generator})


def read(index, cache_key):
    with index.db() as db:
        row = db.execute('SELECT payload FROM ai_topic_cache WHERE cache_key=? ORDER BY created DESC LIMIT 1',(cache_key,)).fetchone()
    if not row:
        monitoring.event('overview.cache', index_path=index.path, cache_hit=False)
        return None
    section = json.loads(row[0])
    monitoring.event('overview.cache', index_path=index.path, cache_hit=True)
    return {**section,'cache_hit':True}


def save(index, cache_key, revision, section):
    if section.get('error'): return
    metadata = section.get('generation') or {}
    with index.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT revision FROM knowledge_state WHERE id=1').fetchone()[0] != revision:
            raise SourceError('stale','Sources changed before the overview topic could be saved.')
        db.execute('INSERT OR REPLACE INTO ai_topic_cache VALUES(?,?,?,?,?)',
                   (cache_key,metadata.get('provider','unreported'),metadata.get('model','unreported'),json.dumps(section),now()))
        db.execute('DELETE FROM ai_topic_cache WHERE rowid NOT IN (SELECT rowid FROM ai_topic_cache ORDER BY created DESC LIMIT 200)')
    monitoring.event('overview.topic_saved', index_path=index.path, provider=metadata.get('provider'), model=metadata.get('model'))
