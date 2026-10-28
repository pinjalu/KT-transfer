"""Project overview follows the selected source, including older mixed workspaces."""
from pathlib import PurePosixPath

from pka.config import selected_source


def selected_local(index, scan):
    settings = index.settings() or {}
    local = settings.get('local') or {}
    if selected_source(settings) != 'local' or scan['repo'].startswith(('local:', 'zip:')):
        return None
    repo = local.get('repo', '')
    if not repo.startswith('local:'):
        return None
    saved = index.source_import('local') or {}
    snapshot = saved.get('snapshot', '')
    prefix = 'local://' + snapshot + '/' if snapshot else ''
    paths = [p for p in index.code_paths(scan['id']) if prefix and p.startswith(prefix)]
    return {'id':prefix or 'local-selection:' + repo, 'name':PurePosixPath(repo[6:].replace('\\', '/').rstrip('/')).name,
            'repo':repo, 'commit':snapshot, 'paths':paths, 'source_kind':'local',
            'read_at':(saved.get('report') or {}).get('read_at') or local.get('read_at'),
            'skipped':(saved.get('report') or {}).get('skipped', 0)}


def apply_metadata(payload, selection, revision):
    """Keep the underlying snapshot IDs for citations but present the selected local project."""
    return {**payload, 'overview_scope':selection['id'], 'project_name':selection['name'],
            'source_kind':'local', 'repo':selection['repo'], 'branch':'', 'commit':selection['commit'],
            'knowledge_revision':revision, 'files_indexed':len(selection['paths']),
            'files_skipped':selection['skipped'] if isinstance(selection['skipped'], int) else 0,
            'scanned_at':selection['read_at'], 'systems':[{'id':selection['id'], 'name':selection['name']}],
            'scope_note':'This overview uses only the selected local folder’s imported files.'}


def current_local_payload(index, scan, selection, cached=None):
    from pka.architecture import SystemIndex
    from pka import facts, roles, features
    from pka.overview import topics_for, section_from, reading_order
    view = SystemIndex(index, scan['id'], selection['paths'])
    found = facts.derive(view, scan)
    derived = features.derive(view, scan, found)
    feature_list = {'available':True, **features.listing(derived),
                    'repo':selection['repo'], 'branch':'', 'commit':selection['commit'],
                    'scan_id':scan['id'], 'knowledge_revision':index.revision}
    if cached is None:
        topics = topics_for(set())
        cached = {'scan_id':scan['id'], 'demo':bool(scan.get('demo')), 'complete':False,
                  'topics_done':0, 'topics_total':len(topics), 'successful_topics':0, 'failed_topics':0,
                  'facts':found, 'roles':roles.describe(view, scan, found), 'diagrams':[], 'steps':[],
                  'sections':[section_from(topic, [], {'statements':[], 'missing_information':
                      'Build the overview to explain this local project from its own files.'}) for topic in topics],
                  'scope_update_available':True, 'plain_language_update_available':True}
    return apply_metadata({**cached, 'overview_features':feature_list,
        'system_feature_flows':{selection['id']:features.overview_flows(derived)},
        'reading_order':reading_order(selection['paths'], repo=scan['repo'], commit=scan['commit'])}, selection, index.revision)
