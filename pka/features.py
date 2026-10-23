"""Group what is already known separately into features.

The chart's sixth phase, and most of its seventh, eighth and ninth, hang off one missing idea.
A route is known. The files that route reaches are known, because an import is a line in a file.
The tables those files touch are known. The ticket that asked for the work is known, because its
key is written in the code. Nothing put them under one name.

This does that, and only that. Nothing here is written by a model. A feature is a cluster of
evidence, and every member of the cluster carries the file and line it came from, exactly as the
facts and diagrams already do. Where the only link is that two things look similar, the member is
marked `possible` and kept, rather than promoted to a fact or quietly dropped.

What this cannot do is name a feature the way a person would. The name comes from the route
address and, where a ticket is attached, from the ticket's own words. A feature nobody routes to
is not found at all, which is stated in the payload rather than left to be noticed.
"""
import re
from collections import defaultdict

from pka import diagram
from pka.facts import TEST_PATH, source_url

# A route under /api/v1/orders is about orders, not about api or v1.
SKIP_SEGMENTS = {'api', 'v1', 'v2', 'v3', 'rest', 'www', 'public', 'internal', 'static',
                 'index', 'default', 'home', 'root', ''}
# How far an import chain is followed out from a route's own file. Two hops reaches the service
# a handler calls and the store that service uses, which is the depth the request journey in
# pka/diagram.py already found worth drawing. Beyond that a feature swallows the whole project.
REACH_DEPTH = 2
MAX_FEATURES = 24
MAX_FILES_PER_FEATURE = 20
ISSUE_KEY = re.compile(r'\b([A-Z][A-Z0-9_]{1,20})-(\d{1,6})\b')
SEGMENT = re.compile(r'[A-Za-z][A-Za-z0-9_-]*')
WORD = re.compile(r'[a-z0-9]+')


ACRONYMS = {'qa', 'api', 'ui', 'db', 'id', 'url', 'http', 'io', 'sql', 'csv', 'pdf', 'ai',
            'ml', 'kt', 'crm', 'sso', 'otp', 'jwt'}


def _word(word: str, first: bool) -> str:
    if word.lower() in ACRONYMS:
        return word.upper()
    return word.capitalize() if first else word.lower()


def _title(segment: str) -> str:
    """orders -> Orders, order-items -> Order items, qa -> QA, orderItems -> Order items."""
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', segment).replace('-', ' ').replace('_', ' ')
    words = [w for w in spaced.split() if w]
    if not words:
        return segment
    return ' '.join(_word(w, i == 0) for i, w in enumerate(words))


def _subject(address: str) -> str:
    """The segment a route is about, skipping prefixes that say nothing about the project."""
    for raw in address.strip('/').split('/'):
        found = SEGMENT.match(raw)        # skips {id}, :id and <int:id>
        if not found:
            continue
        word = found.group(0)
        if word.lower() in SKIP_SEGMENTS:
            continue
        return word
    return ''


def _split(label: str) -> tuple[str, str]:
    """'POST /orders' -> ('POST', '/orders'). A table route has no method."""
    parts = label.split(' ', 1)
    if len(parts) == 2 and parts[0].isupper():
        return parts[0], parts[1]
    return '', label


def _group_of(facts, key) -> list:
    for group in facts:
        if group['key'] == key:
            return group['items']
    return []


PY_DEF = re.compile(r'^(\s*)(?:async\s+)?def\s+\w+')
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _handler_span(lines: dict, route_line: int) -> tuple[int, int]:
    """The body of the function one route declaration belongs to.

    A route is declared on a line; the work it does is in the function underneath it. Reading
    only that function is what separates two features declared in the same file.

    Python is found by indentation: the first def after the decorator, then every line indented
    further than it. Anything else falls back to the braces opened on the route line. A span
    that cannot be found returns empty, and the caller treats the whole file as the handler,
    which is the old behaviour and never worse than it.
    """
    numbers = sorted(lines)
    after = [n for n in numbers if n >= route_line]
    for i, number in enumerate(after):
        found = PY_DEF.match(lines[number])
        if not found:
            # Only a decorator or a blank line may sit between the route and its function.
            text = lines[number].strip()
            if number != route_line and text and not text.startswith(('@', '#')):
                break
            continue
        indent = len(found.group(1))
        end = number
        for later in after[i + 1:]:
            text = lines[later]
            if not text.strip():
                end = later
                continue
            if len(text) - len(text.lstrip()) <= indent:
                break
            end = later
        return number, end

    # Brace matching, for a route registered as a call with a callback.
    depth, started, end = 0, False, route_line
    for number in after:
        depth += lines[number].count('{') - lines[number].count('}')
        started = started or '{' in lines[number]
        end = number
        if started and depth <= 0:
            return route_line, end
    return 0, 0


def _names_used(lines: dict, start: int, end: int) -> set:
    """Every identifier written inside that span."""
    used = set()
    for number in range(start, end + 1):
        text = lines.get(number)
        if text:
            used |= set(IDENTIFIER.findall(text))
    return used


def _local_defs(lines: dict) -> dict:
    """Every function defined in this file, with the lines it occupies."""
    found, numbers = {}, sorted(lines)
    for i, number in enumerate(numbers):
        match = PY_DEF.match(lines[number])
        if not match:
            continue
        name = lines[number].split('def ', 1)[1].split('(')[0].strip()
        indent, end = len(match.group(1)), number
        for later in numbers[i + 1:]:
            text = lines[later]
            if not text.strip():
                end = later
                continue
            if len(text) - len(text.lstrip()) <= indent:
                break
            end = later
        found.setdefault(name, (number, end))
    return found


def _names_reached(lines: dict, start: int, end: int, local: dict, depth: int = 2) -> set:
    """The names a handler uses, including through the helpers in its own file it calls.

    A handler that calls a helper beside it, and the helper being the thing that imports, is
    an ordinary way to write a route. Stopping at the handler's own lines missed it entirely.
    """
    used, seen = _names_used(lines, start, end), set()
    for _ in range(depth):
        following = {n for n in used if n in local and n not in seen}
        if not following:
            break
        seen |= following
        for name in following:
            where = local[name]
            used |= _names_used(lines, where[0], where[1])
    return used


def _reach(start: set, edges: dict, depth: int) -> dict:
    """Files reachable from these by following import lines, with the hop each was found at."""
    seen = {path: 0 for path in start}
    frontier = set(start)
    for hop in range(1, depth + 1):
        following = set()
        for path in frontier:
            for target, _line in edges.get(path, []):
                if target not in seen:
                    seen[target] = hop
                    following.add(target)
        frontier = following
        if not frontier:
            break
    return seen


# TEST_PATH treats any path under a folder called `testing` as a test, which is right for most
# projects and wrong for one whose product is about testing: it called
# src/mcp_project/testing/qa_task_store.py a test covering the chat feature. Here a file has to
# be named like a test, or sit under a folder named exactly tests, before it counts as one.
TEST_FILE = re.compile(r'(^|/)tests?/|(^|/)__tests__/|(^|/)test_[^/]+$|_test\.[A-Za-z]+$'
                       r'|\.(test|spec)\.[A-Za-z]+$', re.I)


def _tests_for(members: set, edges: dict) -> list:
    """A test file that imports a member. An import line, so this is confirmed, not guessed."""
    found = []
    for path, imports in edges.items():
        if not TEST_FILE.search(path):
            continue
        for target, line in imports:
            if target in members:
                found.append({'name': path.rsplit('/', 1)[-1], 'path': path, 'line': line,
                              'covers': 'Imports ' + target, 'confidence': 'confirmed'})
                break
    return found


def _issues_for(members: set, files: dict, issues: dict, words: set) -> list:
    """Tickets attached to a feature, separating a key written in the code from a word match."""
    found, taken = [], set()
    # A ticket key written inside a member file is a link somebody typed on purpose.
    for path in members:
        for number, line in files.get(path, []):
            for match in ISSUE_KEY.finditer(line):
                key = match.group(0)
                if key in issues and key not in taken:
                    taken.add(key)
                    found.append({'key': key, 'summary': issues[key]['summary'],
                                  'confidence': 'confirmed',
                                  'path': path, 'line': number})
    # Anything left is only a word overlap with the feature's own name, so it says so.
    for key, issue in issues.items():
        if key in taken:
            continue
        if words & issue['words']:
            found.append({'key': key, 'summary': issue['summary'], 'confidence': 'possible',
                          'path': 'jira/' + key, 'line': 1})
    return found


def _issue_index(index, scan) -> dict:
    """Every Jira issue read in this scan, by key, with the words of its summary."""
    issues = {}
    for path in index.indexed_paths(scan['id']):
        if not path.startswith('jira/'):
            continue
        key = path.split('/', 1)[1]
        lines = index.file_lines(scan['id'], path)
        summary = ''
        for _number, text in lines:
            stripped = text.strip()
            if stripped:
                summary = stripped[:160]
                break
        issues[key] = {'summary': summary, 'words': set(WORD.findall(summary.lower()))}
    return issues


def derive(index, scan: dict, facts: list) -> dict:
    """Cluster this scan's routes, files, tables, services and tickets into features.

    Returns the list payload described in docs/FEATURE_CONTRACT.md. Nothing here calls a model
    and nothing here reaches the network: every input is already in the index.
    """
    code = index.code_paths(scan['id'])
    files = {p: index.file_lines(scan['id'], p) for p in code}
    edges = diagram.import_edges(files)
    table = diagram._lookup(files)
    bindings = {path: diagram.import_bindings(path, lines, table)
                for path, lines in files.items()}
    issues = _issue_index(index, scan)

    routes = _group_of(facts, 'routes')
    stores = _group_of(facts, 'stores')
    services = _group_of(facts, 'services')

    def link(path, line):
        if scan.get('demo'):
            return ''
        return source_url(scan.get('repo', ''), scan.get('commit', ''), path, line)

    # One cluster per route subject. Two routes on /orders and /orders/{id} are one feature.
    clusters: dict[str, list] = defaultdict(list)
    unrouted = 0
    for item in routes:
        method, address = _split(item['text'])
        subject = _subject(address)
        if not subject:
            unrouted += 1
            continue
        clusters[subject.lower()].append({
            'method': method, 'path': address, 'declared_at': {
                'path': item['path'], 'line': item['line'], 'url': item['url']},
            'confidence': 'confirmed'})

    built = []
    for subject, members in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        seed = {r['declared_at']['path'] for r in members if r['declared_at']['path']}
        # Follow only what each route's own handler names. Seeding from the declaring file
        # instead gave every feature in a single-module application the same files, which was
        # the first thing visible on the first real project this was pointed at.
        handled = set()
        for route in members:
            at = route['declared_at']
            numbered = dict(files.get(at['path'], []))
            if not numbered:
                continue
            start, end = _handler_span(numbered, at['line'])
            used = (_names_reached(numbered, start, end, _local_defs(numbered))
                    if start else None)
            for name, target, _line in bindings.get(at['path'], []):
                if used is None or name in used:
                    handled.add(target)
        # Expand only from what the handlers named. The declaring file joins as a member at
        # hop zero without being followed, because following it is the whole-file reach again.
        reached = {path: hop + 1 for path, hop in
                   _reach(handled, edges, REACH_DEPTH - 1).items()}
        for path in seed:
            reached[path] = 0
        member_paths = set(sorted(reached, key=lambda p: (reached[p], p))[:MAX_FILES_PER_FEATURE])
        words = set(WORD.findall(subject))

        tables = [{'name': s['text'], 'plain': s['detail'],
                   'declared_at': {'path': s['path'], 'line': s['line'], 'url': s['url']},
                   'confidence': 'confirmed'}
                  for s in stores if s['path'] in member_paths]
        outside = [{'name': s['text'], 'plain': s['detail'],
                    'called_at': {'path': s['path'], 'line': s['line'], 'url': s['url']},
                    'confidence': 'confirmed'}
                   for s in services if s['path'] in member_paths]
        tests = _tests_for(member_paths, edges)
        attached = _issues_for(member_paths, files, issues, words)
        for evidence in tests + attached:
            evidence['url'] = ('' if evidence['path'].startswith('jira/') else
                               link(evidence['path'], evidence['line']))

        # A ticket somebody linked by key names the feature better than a URL segment does.
        named = next((i['summary'] for i in attached if i['confidence'] == 'confirmed' and i['summary']), '')
        name = _title(subject)

        gaps = []
        if not tables:
            gaps.append({'what': 'Where this feature stores anything',
                         'checked': 'Table and model declarations in the files this route reaches',
                         'why_missing': 'No store is declared in them.'})
        if not tests:
            gaps.append({'what': 'Tests covering this feature',
                         'checked': 'Test files importing any file this route reaches',
                         'why_missing': 'No test imports them.'})
        if not attached:
            gaps.append({'what': 'The request that asked for this feature',
                         'checked': 'Jira issue keys written in these files, and issue summaries',
                         'why_missing': 'No ticket is linked and none matches by name.'})

        built.append({
            'id': subject,
            'name': name,
            'plain': '',
            'ticket_name': named,
            'confidence': 'confirmed',
            'route_count': len(members),
            'file_count': len(member_paths),
            'issue_count': len(attached),
            'has_tests': bool(tests),
            'gap_count': len(gaps),
            # Kept for the detail endpoint rather than recomputed, so one read builds both.
            '_detail': {
                'routes': members, 'files': sorted(member_paths), 'reached': reached,
                'tables': tables, 'services': outside, 'tests': tests,
                'issues': attached, 'gaps': gaps,
                'components': {p: _component(p, files[p][0][0] if files[p] else 1,
                    link(p, files[p][0][0] if files[p] else 1)) for p in member_paths},
            },
        })

    built = built[:MAX_FEATURES]
    clustered = {p for f in built for p in f['_detail']['files']}
    for feature in built:
        for step in feature['_detail']['routes']:
            at = step['declared_at']
            at['url'] = at['url'] or link(at['path'], at['line'])

    return {
        'scan_id': scan['id'],
        'commit': scan.get('commit'),
        'features': built,
        'unclustered': {
            'routes': unrouted + sum(len(group) for _, group in
                                    sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))[MAX_FEATURES:]),
            'files': max(0, len(code) - len(clustered)),
            'note': 'A feature starts at a route. Files no route reaches are not assigned to one, '
                    'and a project that declares no routes produces no features at all.',
        },
    }


def listing(payload: dict) -> dict:
    """The list payload with the per-feature working detail stripped out."""
    return {**payload,
            'features': [{k: v for k, v in f.items() if not k.startswith('_')}
                         for f in payload['features']]}


def _component(path: str, line: int, url: str, kind: str = 'file') -> dict:
    return {'kind': kind, 'name': path.rsplit('/', 1)[-1], 'sub': path.rsplit('/', 1)[0],
            'path': path, 'line': line, 'url': url}


def detail(feature: dict) -> dict:
    """One feature in the shape docs/FEATURE_CONTRACT.md describes.

    The flow groups route declarations, files by import distance, and data declarations.
    It is a static map, not an observed execution trace. Generated prose is not implemented;
    `overview` comes back empty and the UI explains the available evidence instead.
    """
    d = feature['_detail']
    reached = d['reached']

    steps, n = [], 0
    for route in sorted(d['routes'], key=lambda r: r['path']):
        n += 1
        at = route['declared_at']
        steps.append({'n': n,
                      'label': (route['method'] + ' ' + route['path']).strip(),
                      'plain': 'The address this feature answers on.',
                      'component': _component(at['path'], at['line'], at['url'], 'route'),
                      'confidence': 'confirmed'})
    # Static import distance is not runtime execution order.
    for path in sorted((p for p in d['files'] if reached.get(p, 0) > 0),
                       key=lambda p: (reached[p], p)):
        n += 1
        steps.append({'n': n, 'label': path.rsplit('/', 1)[-1],
                      'plain': f'Reached by an import, {reached[path]} step'
                               f'{"s" if reached[path] > 1 else ""} from the route.',
                      'component': d['components'][path],
                      'confidence': 'confirmed'})
    for table in d['tables']:
        n += 1
        at = table['declared_at']
        steps.append({'n': n, 'label': table['name'],
                      'plain': 'A data declaration in a related file; runtime use is not verified.',
                      'component': _component(at['path'], at['line'], at['url'], 'table'),
                      'confidence': 'confirmed'})

    # Declarations do not establish successful requests or writes to a store.
    outcomes = []

    return {
        'id': feature['id'],
        'name': feature['name'],
        'plain': feature['plain'],
        'ticket_name': feature['ticket_name'],
        'confidence': feature['confidence'],
        'overview': {'purpose': None, 'statements': [], 'sources': [],
                     'note': 'Prose for a feature is written separately and is not built yet.'},
        'flow': {'title': f'Static code map for {feature["name"]}.', 'derived': True,
                 'steps': steps, 'outcomes': outcomes},
        'apis_and_data': {'routes': d['routes'], 'tables': d['tables'], 'services': d['services']},
        'tests': {'existing': d['tests'], 'suggested': []},
        'known_problems': {'items': [], 'note':
            'Nothing here observes the feature running. No application logs, no monitoring and '
            'no pull request history are connected, so known problems cannot be derived.'},
        'related': [d['components'][p] for p in d['files']],
        'issues': d['issues'],
        'gaps': d['gaps'],
    }
