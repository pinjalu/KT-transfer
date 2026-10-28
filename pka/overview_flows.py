"""Select a real action and its input/output evidence before explaining a workflow."""
import re
from pathlib import PurePosixPath

from pka.diagram import _lookup, import_bindings
from pka.facts import _routes
from pka.features import _handler_span, _local_defs, _names_used

NOISE = re.compile(r'(?:^|[/_])(?:debug|logs?|logging|logger)(?:[/_.]|$)', re.I)
SUPPORT_ROUTE = re.compile(r'(?:^|/)(?:health|healthz|ready|metrics|static|assets|favicon)(?:/|\.|$)', re.I)
ACTION = re.compile(r'chat|ask|search|match|track|order|upload|submit|process|generate|convert', re.I)
CLIENT = re.compile(r'\b(?:fetch|axios|ajax)\b|<form\b', re.I)


def flow_anchors(index, scan, paths, readmes):
    files = {p: index.file_lines(scan['id'], p) for p in paths
             if PurePosixPath(p).suffix.lower() in {'.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.vue', '.go', '.java', '.cs'}}
    # Derive routes within this system. The overall facts list is capped and can otherwise
    # contain only the first imported system's routes.
    routes = [r for r in _routes(files, lambda *args: '')
              if not NOISE.search(r['path']) and not SUPPORT_ROUTE.search(r['text'].split()[-1])
              and not re.search(r'\binclude\s*\(|admin\.site', dict(files[r['path']]).get(r['line'], ''))]
    intro = ' '.join(text for path in readmes[:1] for _, text in index.file_lines(scan['id'], path)[:12]).lower()
    settings = index.settings() or {}
    local_name = ((settings.get('local') or {}).get('repo', '') if paths and all(p.startswith('local://') for p in paths)
                  else scan['repo'])
    project_words = set(re.findall(r'[a-z]{4,}', local_name.replace('\\', '/').rsplit('/', 1)[-1].lower()))

    def rank(route):
        words = set(re.findall(r'[a-zA-Z]{3,}', route['text'].lower())) - {'get', 'post', 'put', 'delete', 'api', 'admin'}
        return (sum(word in intro for word in words) * 10 + bool(ACTION.search(route['text'])) * 100
                + sum(word in route['path'].lower() for word in project_words) * 20
                + route['text'].startswith('POST ') * 2)

    routes.sort(key=lambda r: (-rank(r), r['path'].count('/'), r['path'], r['line']))
    anchors = []

    def add(path, line=0):
        if path in paths and (path, line) not in anchors:
            anchors.append((path, line))

    for path in readmes[:1]:
        add(path)
    if not routes:
        for path in files:
            if PurePosixPath(path).stem.lower() in {'main', '__main__', 'app', 'cli', 'server'}:
                lines = files[path]
                at = next((n for n, text in lines if '__name__' in text or 'def main(' in text), 1)
                add(path, at)
                break
        return anchors

    route = routes[0]
    path, line = route['path'], route['line']
    add(path, line)
    numbered = dict(files[path])
    start, end = _handler_span(numbered, line)
    start, end = (start, end) if start else (line, line)
    body = '\n'.join(text for n, text in files[path] if start <= n <= end)
    names = _names_used(numbered, start, end)

    # Include a client that actually names the selected route, rather than any UI file.
    address = route['text'].split()[-1]
    if address.startswith('/') and address != '/':
        for client_path, lines in files.items():
            if client_path == path or not CLIENT.search('\n'.join(text for _, text in lines)):
                continue
            hit = next((n for n, text in lines if address in text), None)
            if hit:
                add(client_path, hit)
                break

    # An explicit request to another route can supply the next backend step. Matching
    # route names alone never establish a connection between two services.
    for other in routes:
        target = other['text'].split()[-1]
        if other['path'] != path and target.startswith('/') and target != '/' and re.search(re.escape(target) + r'''["'`]''', body):
            add(other['path'], other['line'])
            break

    table = _lookup(paths)
    for name, target, _ in import_bindings(path, files[path], table):
        if name not in names or NOISE.search(target):
            continue
        definitions = _local_defs(dict(files.get(target, [])))
        at = next((span[0] for symbol, span in definitions.items() if symbol in names), 1)
        add(target, at)
        if len(anchors) >= 5:
            break
    if len(anchors) < 5:
        for name, (at, _) in _local_defs(numbered).items():
            if name in names and not start <= at <= end and not NOISE.search(name):
                add(path, at)
                if len(anchors) >= 5:
                    break

    # Long handlers often describe the input near their beginning and return the result
    # hundreds of lines later. Keep the latter visible within the same bounded budget.
    returns = [n for n, text in files[path] if start <= n <= end and re.match(r'\s*(?:return|yield)\b', text)]
    if returns and returns[-1] > line + 35:
        add(path, returns[-1])
    return anchors[:6]
