"""Keep introductory topics grounded in the project, not a few keyword-matched helpers."""
import re
from pathlib import PurePosixPath

from pka.config import source_url
from pka.index import TEST_PATH, VENDOR_PATH

MAX_SOURCES = 8
CONTEXT_CHARS = 16000
EXCERPT_CHARS = 2800
ENTRY_NAMES = {'app', 'main', '__main__', 'server', 'cli', 'manage', 'index', 'application'}
MANIFESTS = {'package.json', 'pyproject.toml', 'requirements.txt', 'pipfile', 'go.mod',
             'cargo.toml', 'pom.xml', 'build.gradle', 'makefile', 'dockerfile',
             'compose.yaml', 'compose.yml', 'docker-compose.yml', 'procfile'}
SETUP_DOC = re.compile(r'(?:readme|start.?here|getting.?started|quick.?start|install|setup|running)', re.I)
SETUP_HEADING = re.compile(r'^\s*#{1,6}\s+.*(?:install|setup|getting started|quick.?start|run|start|requirements|prerequisites)', re.I)
STRUCTURE_HEADING = re.compile(r'^\s*#{1,6}\s+.*(?:architecture|structure|components|overview)', re.I)
HELPER = re.compile(r'(^|/)(?:utils?|helpers?|logging|logger|constants)(?:/|\.)', re.I)
PURPOSE_CODE = {'.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.java', '.cs'}


def _excerpt(index, scan, path, topic, anchor=0):
    """A bounded, contiguous window of saved lines, with the original citation offsets."""
    lines = index.file_lines(scan['id'], path)
    if not lines:
        return None
    if not anchor:
        heading = SETUP_HEADING if topic == 'setup' else STRUCTURE_HEADING if topic == 'architecture' else None
        anchor = next((n for n, text in lines if heading and heading.search(text)), lines[0][0])
    position = next((i for i, (n, _) in enumerate(lines) if n >= anchor), 0)
    # Include context above a declaration, but never bridge unread gaps in the index.
    begin = position
    while begin > max(0, position - 6) and lines[begin - 1][0] + 1 == lines[begin][0]:
        begin -= 1
    selected, size = [], 0
    for number, text in lines[begin:]:
        if selected and number != selected[-1][0] + 1:
            break
        if size + len(text) + 1 > EXCERPT_CHARS or len(selected) >= 100:
            break
        selected.append((number, text))
        size += len(text) + 1
    if not selected:
        return None
    start, end = selected[0][0], selected[-1][0]
    return {'path': path, 'start': start, 'end': end,
            'text': '\n'.join(text for _, text in selected),
            'url': None if scan.get('demo') else source_url(scan['repo'], scan['commit'], path, start, end)}


def source_systems(index, scan, paths):
    """Keep an explicitly added local system apart from the repository's own files."""
    settings = index.settings() or {}
    grouped = {}
    for path in paths:
        scope = '/'.join(path.split('/')[:3]) + '/' if path.startswith('local://') else 'primary'
        grouped.setdefault(scope, []).append(path)
    systems = []
    for scope, members in grouped.items():
        if scope == 'primary':
            name = (settings.get('project_name') if scan['repo'].startswith(('local:', 'zip:'))
                    else scan['repo'].rsplit('/', 1)[-1])
            name = name or scan['repo'].replace('\\', '/').rsplit('/', 1)[-1]
        else:
            local = settings.get('local') or {}
            local_path = local.get('repo', '').replace('\\', '/').rstrip('/')
            name = local.get('project_name') or local_path.rsplit('/', 1)[-1] or 'Additional local system'
        systems.append({'id': scope, 'name': name, 'paths': members})
    return systems


def select_sources(index, scan, topic, retrieved, facts, roles, paths=None):
    """Reserve room for overview docs, main components and real setup definitions.

    All evidence comes from this scan's already imported files. This adds no file reads,
    model calls or embeddings. Normal search still supplies complementary excerpts.
    """
    if topic not in {'purpose', 'architecture', 'setup', 'flows'}:
        return retrieved
    paths = [p for p in (index.code_paths(scan['id']) if paths is None else paths)
             if not TEST_PATH.search(p) and not VENDOR_PATH.search(p)]
    known = set(paths)
    paths.sort(key=lambda p: (p.count('/'), p.lower()))
    groups = {g['key']: g.get('items', []) for g in facts}
    anchors = []

    def add(path, line=0):
        if path not in known:
            return
        for position, (existing, at) in enumerate(anchors):
            if existing == path:
                if line and not at:
                    anchors[position] = (path, line)
                return
        anchors.append((path, line))

    docs = [p for p in paths if PurePosixPath(p).suffix.lower() in {'.md', '.rst', '.txt'}
            and SETUP_DOC.search(PurePosixPath(p).name)]
    readmes = [p for p in docs if PurePosixPath(p).name.lower().startswith('readme')]
    if topic == 'flows':
        from pka.overview_flows import flow_anchors
        anchors = flow_anchors(index, scan, paths, readmes)
    elif topic == 'purpose':
        # A framework launcher and a stylesheet say little about the need this
        # application meets. Start with a real user action and the code handling it.
        from pka.overview_flows import flow_anchors
        for path, line in flow_anchors(index, scan, paths, readmes):
            if PurePosixPath(path).suffix.lower() not in PURPOSE_CODE and path not in readmes:
                continue
            add(path, line)
            if PurePosixPath(path).name.lower() == 'urls.py':
                route_line = dict(index.file_lines(scan['id'], path)).get(line, '')
                view_name = re.search(r'\b([A-Z]\w+)\.as_view\s*\(', route_line)
                # Preserve local:// snapshot prefixes; PurePosixPath collapses //.
                sibling = path.rsplit('/', 1)[0] + '/views.py'
                if sibling in known:
                    declaration = re.compile(r'^\s*(?:class|(?:async\s+)?def)\s+' + re.escape(view_name.group(1)) + r'\b') if view_name else None
                    at = next((number for number, text in index.file_lines(scan['id'], sibling)
                               if declaration and declaration.search(text)), 0)
                    add(sibling, at)
            if len(anchors) >= 5:
                break
        if len(anchors) < 5:
            for path in paths:
                if PurePosixPath(path).suffix.lower() in PURPOSE_CODE and PurePosixPath(path).stem.lower() in {'views', 'handlers', 'controller', 'app', 'server', 'main'}:
                    add(path)
                if len(anchors) >= 5:
                    break
    elif topic == 'setup':
        # At most two guides, leaving space for scripts and required settings.
        for path in (readmes[:1] + [p for p in docs if p not in readmes][:1]):
            add(path)
        for item in groups.get('commands', [])[:8]:
            add(item.get('path'), item.get('line', 0))
            if len(anchors) >= 4:
                break
        for path in paths:
            if PurePosixPath(path).name.lower() in MANIFESTS:
                add(path)
            if len(anchors) >= 5:
                break
        for item in groups.get('environment', []):
            add(item.get('path'), item.get('line', 0))
            if len(anchors) >= 6:
                break
    else:
        for path in readmes[:1]:
            add(path)
        # Real entry points and route declarations precede highly shared utility files.
        for path in paths:
            if PurePosixPath(path).stem.lower() in ENTRY_NAMES and not HELPER.search(path):
                add(path)
            if len(anchors) >= 3:
                break
        for item in groups.get('routes', []):
            add(item.get('path'), item.get('line', 0))
            if len(anchors) >= 4:
                break
        cards = roles.get('cards', [])
        for card in cards:
            if not HELPER.search(card['path']):
                add(card['path'])
            if len(anchors) >= 6:
                break
        for item in groups.get('stores', []):
            add(item.get('path'), item.get('line', 0))
            if len(anchors) >= 6:
                break

    candidates = [_excerpt(index, scan, path, topic, line) for path, line in anchors[:6]]
    if topic == 'purpose':
        # Search can still rank a CSS file or an instruction prompt above the handler.
        # Neither establishes the product's implemented problem or solution.
        retrieved = [source for source in retrieved
                     if PurePosixPath(source['path']).suffix.lower() not in {'.css', '.scss', '.less', '.map'}
                     and not re.search(r'(^|/)prompts?/', source['path'], re.I)
                     and PurePosixPath(source['path']).stem.lower() not in {'manage', 'wsgi', 'asgi'}]
    if topic == 'flows' and any(PurePosixPath(path).suffix.lower() not in {'.md', '.rst', '.txt'} for path, _ in anchors):
        related_paths = {path for path, _ in anchors}
        retrieved = [source for source in retrieved if source['path'] in related_paths]
    selected, size = [], 0
    for source in candidates + retrieved:
        if not source or source['path'] not in known:
            continue
        if topic == 'flows':
            from pka.overview_flows import NOISE
            if NOISE.search(source['path']):
                continue
        if any(s['path'] == source['path'] and s['start'] <= source['end']
               and source['start'] <= s['end'] for s in selected):
            continue
        if size + len(source['text']) > CONTEXT_CHARS:
            continue
        selected.append({**source, 'source_id': f'S{len(selected) + 1}'})
        size += len(source['text'])
        if len(selected) == MAX_SOURCES:
            break
    return selected
