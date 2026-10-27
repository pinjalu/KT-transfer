"""Diagrams drawn from the scanned files, with no model involved.

A new developer handed eight paragraphs of prose reads none of them. The same person shown a
box diagram of six files with arrows between them understands the shape of the project in
about ten seconds, and then reads the prose because they now have somewhere to put it.

Everything here is derived, not described. An arrow between two boxes exists because one file
contains an import statement naming the other, and the line number of that import travels with
the arrow. A box sits in the band it sits in because of what its path and its contents are, not
because a model decided. So a diagram can be wrong in only one way: the import resolution can
fail to match a path, in which case an arrow is missing rather than invented. Nothing is drawn
that was not read.

Positions are decided here and pixels are decided in the browser. This file assigns each box a
column and a row, which is the part worth testing and the part that has to be stable; the
script turns those into coordinates against whatever width it actually has. The browser builds
the shapes element by element, so no markup is ever handed to it as text.
"""
import re
from pathlib import PurePosixPath

from pka.config import source_url

# Everything after the module name is ignored. Resolution is by path, so "from game import X"
# and "from game import Y" are the same edge, and which names were imported does not change it.
PY_FROM = re.compile(r'^\s*from\s+(\.*)([\w.]*)\s+import\b')
PY_IMPORT = re.compile(r'^\s*import\s+([\w.]+)')
JS_FROM = re.compile(r'''\bfrom\s+['"]([^'"]+)['"]''')
JS_REQUIRE = re.compile(r'''\brequire\(\s*['"]([^'"]+)['"]''')
JS_BARE = re.compile(r'''^\s*import\s+['"]([^'"]+)['"]''')

CODE_SUFFIXES = ('.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte')
# What each language's import is allowed to land on. Python's "import pytest" naming the
# project's own pytest.ini was a real arrow drawn between two files with no relationship, and
# the only guard against that is refusing a target an import could not have meant.
PY_TARGETS = ('.py',)
JS_TARGETS = ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte',
              '.css', '.scss', '.json')
TRY_SUFFIXES = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.py', '.vue', '.svelte',
                '.css', '.scss', '.json')
# An import written @/lib/utils or ~/lib/utils or src/lib/utils all mean the same file. The
# prefix is a build tool's setting that is not worth reading a config file to discover, because
# matching the tail of an indexed path finds the file either way.
ALIAS_HEADS = ('@', '~', 'src', 'app', '#')

INTERFACE_SUFFIXES = ('.html', '.css', '.scss', '.tsx', '.jsx', '.vue', '.svelte')
INTERFACE_DIRS = ('static', 'public', 'templates', 'assets', 'frontend', 'frontend-src',
                  'client', 'ui', 'web', 'views')
ENTRY_NAMES = ('main', '__main__', 'app', 'server', 'index', 'cli', 'run', 'manage', 'wsgi',
               'asgi', 'start')
DATA_HINTS = ('storage', 'store', 'db', 'database', 'models', 'model', 'schema', 'repository',
              'dao', 'migrations', 'entities')
CONFIG_SUFFIXES = ('.toml', '.ini', '.cfg', '.yml', '.yaml', '.json', '.env', '.lock')
CONFIG_NAMES = ('requirements', 'package', 'pyproject', 'setup', 'dockerfile', 'makefile',
                'go', 'cargo', 'gemfile', 'composer', 'pytest', 'tsconfig', 'vite', 'webpack',
                'rollup', 'babel', 'eslint', 'tailwind', 'postcss', 'jest', 'procfile')
TEST_PATH = re.compile(r'(^|/)(tests?|spec|__tests__|testing)/|(^|/)test_[^/]*$|_test\.[A-Za-z]+$'
                       r'|\.(test|spec)\.[A-Za-z]+$', re.I)

BANDS = (
    ('interface', 'What a person or a browser touches',
     'Pages, styles and components. Change these and the screen changes.'),
    ('api', 'Where a request arrives',
     'The file that is started and the addresses it answers on. Follow a bug in from here.'),
    ('logic', 'Where the work happens',
     'The rules of the project. This is usually where a change you are asked to make belongs.'),
    ('data', 'Where information is kept',
     'Tables, saving and loading. Anything that has to survive a restart passes through here.'),
    ('support', 'Settings and checks',
     'Dependency lists, settings files and tests. Read these to run it, not to understand it.'),
)

MAX_NODES = 26
MAX_PER_COLUMN = 7
MAX_ROUTES_SHOWN = 5
MAX_CHAIN_BRANCH = 4


def _without_suffix(path: str) -> str:
    found = PurePosixPath(path)
    return str(found.with_suffix('')) if found.suffix else path


def _lookup(paths) -> dict:
    """Every way an indexed file might be named by an import that reaches it."""
    table = {}
    for path in paths:
        table.setdefault(_without_suffix(path), path)
        found = PurePosixPath(path)
        # A folder import lands on its index or __init__ file.
        if found.stem in ('index', '__init__'):
            table.setdefault(str(found.parent), path)
    return table


def _resolve(target: str, importer: str, table: dict, allow: tuple) -> str:
    """The indexed file an import names, or an empty string when it names something external.

    External is the common answer and the right one: react and fastapi are dependencies, which
    are already listed with their versions elsewhere. Only an import that lands inside the
    scanned files becomes an arrow, because only those say anything about this project's shape.
    """
    if not target:
        return ''
    target = target.replace('\\', '/').rstrip('/')
    here = str(PurePosixPath(importer).parent)
    candidates = []
    if target.startswith('.'):
        relative = PurePosixPath(here) / target.lstrip('./') if here != '.' else PurePosixPath(target.lstrip('./'))
        # A '..' in the path is resolved by PurePosixPath only textually, which is what is
        # wanted here: these are repository paths, not paths on this disk.
        parts = []
        for piece in str(relative).replace('\\', '/').split('/'):
            if piece == '..':
                if parts:
                    parts.pop()
            elif piece not in ('', '.'):
                parts.append(piece)
        candidates.append('/'.join(parts))
    else:
        candidates.append(target)
        head = target.split('/')[0]
        if head in ALIAS_HEADS or head.startswith('@'):
            tail = '/'.join(target.split('/')[1:])
            if tail:
                candidates.append(tail)
        if here != '.':
            candidates.append(here + '/' + target)
    def allowed(path):
        return path.endswith(allow)

    for candidate in candidates:
        if candidate in table and allowed(table[candidate]):
            return table[candidate]
    # Nothing matched outright, so match the tail of an indexed path. "@/lib/utils" becomes
    # frontend-src/lib/utils.ts this way without anybody reading the build configuration.
    for candidate in candidates:
        if '/' not in candidate:
            continue
        for key, path in sorted(table.items()):
            if key.endswith('/' + candidate) and allowed(path):
                return path
    known = set(table.values())
    for candidate in candidates:
        for suffix in TRY_SUFFIXES:
            if suffix in allow and candidate + suffix in known:
                return candidate + suffix
    return ''


def imports_in(path: str, lines, table: dict) -> list[tuple[str, int]]:
    """The indexed files this file imports, each with the line that imports it."""
    if path.startswith('local://'):
        parts = path.split('/', 3)
        prefix, relative = '/'.join(parts[:3]) + '/', parts[3]
        local_paths = [p[len(prefix):] for p in set(table.values()) if p.startswith(prefix)]
        return [(prefix + target, line) for target, line in imports_in(relative, lines, _lookup(local_paths))]
    # An identical module name in another code source is not an import relationship.
    table = {key:value for key,value in table.items() if not value.startswith('local://')}
    if not path.endswith(CODE_SUFFIXES):
        return []
    found, seen = [], set()
    python = path.endswith('.py')
    allow = PY_TARGETS if python else JS_TARGETS
    for number, line in lines:
        targets = []
        if python:
            relative = PY_FROM.match(line)
            if relative:
                dots, module = relative.group(1), relative.group(2)
                targets.append(('.' * len(dots) if dots else '') + module.replace('.', '/'))
            plain = PY_IMPORT.match(line)
            if plain:
                targets.append(plain.group(1).replace('.', '/'))
        else:
            for pattern in (JS_FROM, JS_REQUIRE, JS_BARE):
                targets += pattern.findall(line)
        for target in targets:
            landed = _resolve(target, path, table, allow)
            if landed and landed != path and landed not in seen:
                seen.add(landed)
                found.append((landed, number))
    return found


def import_edges(files: dict) -> dict:
    """Every import edge in the scan, as {importer: [(imported, line), ...]}.

    The whole graph, with no node cap and no layout. `module_graph` draws a bounded picture of
    this for a reader; `pka/features.py` walks all of it to find what a route reaches. Both use
    the same resolution, so an arrow on the diagram and a file inside a feature mean the same
    thing: a real import line, at a known line number.
    """
    table = _lookup(files)
    return {path: imports_in(path, lines, table) for path, lines in files.items()}


def import_bindings(path: str, lines, table: dict) -> list[tuple[str, str, int]]:
    """The names this file binds by importing, as (name, file it lands on, import line).

    `imports_in` answers which files this file reaches. This answers which local name reaches
    which file, which is what lets a feature follow one route handler instead of the whole file
    it was declared in. A project that declares every route in one module gave every feature the
    same files without it.

    `from a.b import c` is tried as the submodule `a/b/c` first and falls back to `a/b`, because
    both are written identically and only the scan can say which one exists.
    """
    if path.startswith('local://'):
        parts = path.split('/', 3)
        prefix, relative = '/'.join(parts[:3]) + '/', parts[3]
        local_paths = [p[len(prefix):] for p in set(table.values()) if p.startswith(prefix)]
        return [(name, prefix + target, line) for name, target, line in
                import_bindings(relative, lines, _lookup(local_paths))]
    table = {key: value for key, value in table.items() if not value.startswith('local://')}
    if not path.endswith(CODE_SUFFIXES):
        return []
    python = path.endswith('.py')
    allow = PY_TARGETS if python else JS_TARGETS
    found, seen = [], set()

    def bind(name, target):
        landed = _resolve(target, path, table, allow)
        if landed and landed != path and (name, landed) not in seen:
            seen.add((name, landed))
            return landed
        return ''

    for number, line in lines:
        if python:
            relative = PY_FROM.match(line)
            if relative:
                dots, module = relative.group(1), relative.group(2)
                base = ('.' * len(dots) if dots else '') + module.replace('.', '/')
                tail = line.split(' import ', 1)[1] if ' import ' in line else ''
                for piece in tail.split('#')[0].split(','):
                    imported, _, alias = piece.strip().strip('()').partition(' as ')
                    name = (alias or imported).strip()
                    imported = imported.strip()
                    if not name.isidentifier() or not imported.isidentifier():
                        continue
                    # The submodule if the scan has one, otherwise the package itself.
                    landed = bind(name, base.rstrip('/') + '/' + imported) or bind(name, base)
                    if landed:
                        found.append((name, landed, number))
                continue
            plain = PY_IMPORT.match(line)
            if plain:
                dotted = plain.group(1)
                tail = line[plain.end():].split('#')[0].strip()
                alias = re.fullmatch(r'as\s+([A-Za-z_]\w*)', tail)
                name = alias.group(1) if alias else dotted.split('.')[0]
                landed = bind(name, dotted.replace('.', '/'))
                if landed:
                    found.append((name, landed, number))
                continue
        else:
            for pattern in (JS_FROM, JS_REQUIRE):
                for target in pattern.findall(line):
                    # import Thing, { a, b } from 'x'  /  const { a } = require('x')
                    head = line.split('from' if pattern is JS_FROM else '=', 1)[0]
                    for raw in re.findall(r'[A-Za-z_$][\w$]*', head):
                        if raw in ('import', 'const', 'let', 'var', 'require', 'as', 'from'):
                            continue
                        landed = bind(raw, target)
                        if landed:
                            found.append((raw, landed, number))
    return found


def _band(path: str, lines, route_paths: set) -> str:
    """Which layer of the stack this file belongs to. One file, one band."""
    found = PurePosixPath(path)
    name, stem, suffix = found.name.lower(), found.stem.lower(), found.suffix.lower()
    parts = [p.lower() for p in found.parts]
    if TEST_PATH.search(path):
        return 'support'
    # tsconfig.json and vite.config.ts both have a dotted stem, so the first segment is what
    # has to be compared against the known names of settings files.
    head = stem.split('.')[0]
    if suffix in CONFIG_SUFFIXES or stem in CONFIG_NAMES or head in CONFIG_NAMES:
        return 'support'
    if name.startswith(('.env', 'dockerfile', 'makefile')) or '.config' in stem:
        return 'support'
    if suffix in ('.bat', '.cmd', '.sh', '.ps1'):
        return 'support'
    if suffix in ('.md', '.rst', '.txt', '.adoc'):
        return 'support'
    if path in route_paths:
        return 'api'
    if suffix in INTERFACE_SUFFIXES or any(p in INTERFACE_DIRS for p in parts[:-1]):
        return 'interface'
    if any(h in stem for h in DATA_HINTS) or any(h in parts for h in DATA_HINTS):
        return 'data'
    if stem in ENTRY_NAMES and len(parts) <= 2:
        return 'api'
    for _, text in lines:
        if 'CREATE TABLE' in text.upper():
            return 'data'
    return 'logic'


def _node(ident, label, path='', line=0, url='', sublabel='', kind='file'):
    return {'id': ident, 'label': label, 'sublabel': sublabel, 'path': path,
            'line': line, 'url': url, 'kind': kind, 'column': 0, 'row': 0}


def _place(nodes, per_column=MAX_PER_COLUMN):
    """Assign a row inside each column, keeping a column from growing without limit."""
    counts = {}
    for item in nodes:
        column = item['column']
        item['row'] = counts.get(column, 0)
        counts[column] = item['row'] + 1
    return nodes


def stack_bands(files: dict, route_paths: set, link) -> dict:
    """The project as a stack of layers, read top to bottom.

    This is the diagram to look at first and the only one that is useful on a project with no
    internal imports at all, which is most small projects and every single-file one.
    """
    grouped = {}
    for path, lines in files.items():
        grouped.setdefault(_band(path, lines, route_paths), []).append(path)
    nodes = []
    bands = []
    for position, (key, title, plain) in enumerate(BANDS):
        held = sorted(grouped.get(key, []), key=lambda p: (len(PurePosixPath(p).parts), p))
        if not held:
            continue
        bands.append({'key': key, 'title': title, 'plain': plain, 'column': position,
                      'count': len(held)})
        for path in held[:MAX_PER_COLUMN]:
            nodes.append(_node('b:' + path, PurePosixPath(path).name, path, 1, link(path, 1),
                               str(PurePosixPath(path).parent) if '/' in path else '',
                               'file'))
            nodes[-1]['column'] = position
        if len(held) > MAX_PER_COLUMN:
            nodes.append(_node('b:more:' + key,
                               f'and {len(held) - MAX_PER_COLUMN} more', kind='more'))
            nodes[-1]['column'] = position
    if not bands:
        return {}
    return {'key': 'stack', 'kind': 'bands', 'title': 'The project as a stack',
            'plain': 'Every file that was read, put in the layer it belongs to. Read it from the '
                     'top down: that is the order a request travels.',
            'bands': bands, 'nodes': _place(nodes), 'edges': [],
            'note': 'A file is placed by its path and its contents, not by a model. Each box '
                    'opens the file at the scanned commit.'}


def module_graph(files: dict, link) -> dict:
    """Which file imports which, as boxes and arrows.

    Files are collapsed into folders when there are too many boxes to read, because a diagram
    nobody can take in at a glance has failed at the one thing it was for.
    """
    table = _lookup(files)
    edges, importers = [], {}
    for path, lines in files.items():
        for target, line in imports_in(path, lines, table):
            edges.append({'from': path, 'to': target, 'line': line})
            importers.setdefault(target, set()).add(path)
    if not edges:
        return {}
    involved = sorted({e['from'] for e in edges} | {e['to'] for e in edges})
    collapsed = len(involved) > MAX_NODES
    if collapsed:
        def group(path):
            parts = PurePosixPath(path).parts
            return parts[0] + '/' if len(parts) > 1 else path
        counted = {}
        for edge in edges:
            left, right = group(edge['from']), group(edge['to'])
            if left != right:
                counted[(left, right)] = counted.get((left, right), 0) + 1
        if not counted:
            return {}
        names = sorted({n for pair in counted for n in pair})
        edges = [{'from': a, 'to': b, 'line': 0, 'count': n} for (a, b), n in counted.items()]
        members = {}
        for path in involved:
            members.setdefault(group(path), []).append(path)
        nodes = {n: _node('m:' + n, n, '', 0, '',
                          f'{len(members.get(n, []))} files', 'group') for n in names}
    else:
        nodes = {p: _node('m:' + p, PurePosixPath(p).name, p, 1, link(p, 1),
                          str(PurePosixPath(p).parent) if '/' in p else '', 'file')
                 for p in involved}

    # Depth is the longest chain of imports leading into a file, so a file nothing imports
    # starts at the left and a file deep in the stack sits to the right of everything that
    # reaches it. A cycle cannot push depth forever because each file is settled once.
    incoming = {name: set() for name in nodes}
    outgoing = {name: set() for name in nodes}
    for edge in edges:
        if edge['from'] in nodes and edge['to'] in nodes:
            incoming[edge['to']].add(edge['from'])
            outgoing[edge['from']].add(edge['to'])
    depth = {name: 0 for name in nodes}
    frontier = [n for n in nodes if not incoming[n]] or sorted(nodes)
    settled = set(frontier)
    while frontier:
        following = []
        for name in frontier:
            for target in sorted(outgoing[name]):
                if depth[target] < depth[name] + 1:
                    depth[target] = depth[name] + 1
                if target not in settled:
                    settled.add(target)
                    following.append(target)
        frontier = following
    widest = max(depth.values()) if depth else 0
    for name, item in nodes.items():
        item['column'] = min(depth[name], widest)
    # A column with twenty boxes in it is a wall, not a diagram. Where one overflows, the files
    # with the most arrows touching them are kept, because those are the ones worth knowing
    # about, and the remainder is replaced by a single box that says how many were left out.
    degree = {name: len(incoming[name]) + len(outgoing[name]) for name in nodes}
    ordered, dropped = [], {}
    for column in sorted({n['column'] for n in nodes.values()}):
        here = [n for n in nodes.values() if n['column'] == column]
        here.sort(key=lambda n: (-degree[n['path'] or n['label']], n['path'] or n['label']))
        ordered.extend(here[:MAX_PER_COLUMN])
        if len(here) > MAX_PER_COLUMN:
            dropped[column] = len(here) - MAX_PER_COLUMN
    ordered.sort(key=lambda n: (n['column'], n['path'] or n['label']))
    for column, count in dropped.items():
        spare = _node(f'm:more:{column}', f'and {count} more', kind='more')
        spare['column'] = column
        ordered.append(spare)
    ordered.sort(key=lambda n: (n['column'], n['kind'] == 'more', n['path'] or n['label']))
    kept = {n['id'] for n in ordered}
    # Two files that import each other cannot both be to the left of the other, so one arrow
    # in a cycle must run backwards. It is a real import and gets drawn, marked so the browser
    # routes it under the boxes instead of through them, and counted, because files depending
    # on each other is a thing about the project worth telling a new reader.
    column_of = {n['id']: n['column'] for n in ordered}
    drawn = []
    for e in edges:
        start, finish = 'm:' + e['from'], 'm:' + e['to']
        if start not in kept or finish not in kept:
            continue
        drawn.append({'from': start, 'to': finish, 'line': e.get('line', 0),
                      'count': e.get('count', 1),
                      'back': column_of[finish] <= column_of[start]})
    circular = sum(1 for e in drawn if e['back'])
    note = ('Arrows come from import lines only. An import of something outside this '
            'project is a dependency, not an arrow, and is listed with the versions '
            'instead.')
    if circular:
        note += (f" {circular} dashed arrow{'s' if circular > 1 else ''} loop back underneath: "
                 'those files import each other, so there is no order in which one comes first.')
    return {'key': 'modules', 'kind': 'graph',
            'title': 'What uses what' if not collapsed else 'Which folders use which',
            'plain': ('An arrow means the file it starts at contains an import naming the file '
                      'it points to. Files nothing imports are on the left, so follow the '
                      'arrows rightwards to go deeper into the project.' if not collapsed else
                      'Too many files to draw one by one, so each box is a folder. The number '
                      'on an arrow is how many imports cross between them.'),
            'nodes': _place(ordered), 'edges': drawn, 'circular': circular, 'note': note}


def request_journey(files: dict, routes: list, link) -> dict:
    """One worked example: a request arriving, and where it goes.

    Only the steps that can be proved are drawn. The file is known to serve the address because
    the address is declared in it; the modules are known because it imports them; the table is
    known because the module creates it. What is not drawn is which route reaches which table,
    because no import line says that and guessing it would be the one dishonest arrow here.
    """
    if not routes:
        return {}
    busiest = {}
    for route in routes:
        busiest[route['path']] = busiest.get(route['path'], 0) + 1
    entry = max(busiest, key=lambda p: (busiest[p], -len(p)))
    table = _lookup(files)
    reached = [t for t, _ in imports_in(entry, files.get(entry, []), table)]

    nodes = [_node('j:client', 'A browser or a client', kind='outside')]
    nodes[-1]['sublabel'] = 'sends a request'
    nodes.append(_node('j:entry', PurePosixPath(entry).name, entry, 1, link(entry, 1),
                       'receives it and decides what handles it', 'file'))
    nodes[-1]['column'] = 1
    edges = [{'from': 'j:client', 'to': 'j:entry', 'line': 0, 'count': 1}]

    for route in routes[:MAX_ROUTES_SHOWN]:
        if route['path'] != entry:
            continue
        ident = 'j:route:' + route['text']
        nodes.append(_node(ident, route['text'], route['path'], route['line'],
                           route['url'], 'declared at line ' + str(route['line']), 'route'))
        nodes[-1]['column'] = 2
        edges.append({'from': 'j:entry', 'to': ident, 'line': route['line'], 'count': 1})

    for path in reached[:MAX_CHAIN_BRANCH]:
        ident = 'j:uses:' + path
        nodes.append(_node(ident, PurePosixPath(path).name, path, 1, link(path, 1),
                           'imported by ' + PurePosixPath(entry).name, 'file'))
        nodes[-1]['column'] = 3
        edges.append({'from': 'j:entry', 'to': ident, 'line': 0, 'count': 1})
        for number, line in files.get(path, []):
            if 'CREATE TABLE' in line.upper():
                store = 'j:store:' + path
                if store not in {n['id'] for n in nodes}:
                    nodes.append(_node(store, 'saved to a table', path, number,
                                       link(path, number),
                                       'the table is created at line ' + str(number), 'store'))
                    nodes[-1]['column'] = 4
                    edges.append({'from': ident, 'to': store, 'line': number, 'count': 1})
                break
    if len(nodes) < 3:
        return {}
    return {'key': 'journey', 'kind': 'graph', 'title': 'One request, start to finish',
            'plain': 'A worked example of the path a single request takes through the files '
                     'that were read.',
            'nodes': _place(nodes), 'edges': [{**e, 'back': False} for e in edges],
            'circular': 0,
            'note': 'Which address ends up touching which table is not drawn, because no line '
                    'in the files states it and the rest of this diagram does not guess.'}


def build(index, scan: dict, facts: list) -> list[dict]:
    """Every diagram that this scan supports. A diagram with nothing behind it is not drawn."""
    paths = index.code_paths(scan['id'])
    files = {p: index.file_lines(scan['id'], p) for p in paths}
    groups = {g['key']: g for g in facts}
    routes = groups.get('routes', {}).get('items', [])
    route_paths = {r['path'] for r in routes}

    def link(path, line):
        if scan.get('demo'):
            return ''
        return source_url(scan.get('repo', ''), scan.get('commit', ''), path, line)

    made = [stack_bands(files, route_paths, link),
            module_graph(files, link),
            request_journey(files, routes, link)]
    return [d for d in made if d]
