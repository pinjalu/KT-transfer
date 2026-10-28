"""Overview diagrams and function links come only from declarations in this scan."""

from pka.er_diagram import build as er_diagram
from pka.overview_references import definitions, references


class Files:
    def __init__(self, files):
        self.files = {path: list(enumerate(text.splitlines(), 1)) for path, text in files.items()}

    def code_paths(self, scan_id):
        return list(self.files)

    def file_lines(self, scan_id, path):
        return self.files.get(path, [])


SCAN = {'id': 1, 'repo': 'example/project', 'commit': 'a' * 40}


def test_er_diagram_shows_only_explicit_foreign_keys_and_source_lines():
    index = Files({'schema.sql': 'CREATE TABLE users (\n id INTEGER PRIMARY KEY,\n name TEXT\n);\n'
                                 'CREATE TABLE orders (\n id INTEGER PRIMARY KEY,\n'
                                 ' user_id INTEGER REFERENCES users(id)\n);\n'})
    graph = er_diagram(index, SCAN)
    assert {node['label'] for node in graph['nodes']} == {'users', 'orders'}
    assert len(graph['edges']) == 1
    edge = graph['edges'][0]
    assert (edge['from'], edge['to'], edge['line']) == ('er:orders', 'er:users', 7)
    assert 'user_id references users' == edge['reason']
    order = next(node for node in graph['nodes'] if node['label'] == 'orders')
    assert order['fields'] == ['id', 'user_id']
    assert order['url'].endswith('/schema.sql#L5')


def test_er_diagram_keeps_systems_separate_and_does_not_invent_relations():
    index = Files({'local://snapshot/schema.py': 'class Match(models.Model):\n    person = models.ForeignKey("User", on_delete=CASCADE)\n',
                   'users.py': 'class User(models.Model):\n    name = models.CharField(max_length=40)\n'})
    local = er_diagram(index, SCAN, ['local://snapshot/schema.py'])
    assert [node['label'] for node in local['nodes']] == ['Match']
    assert local['edges'] == []
    primary = er_diagram(index, SCAN, ['users.py'])
    assert [node['label'] for node in primary['nodes']] == ['User']
    assert primary['edges'] == []


def test_single_line_table_does_not_absorb_following_code():
    index = Files({'schema.sql': 'CREATE TABLE users (id INTEGER);\nnot_a_column INTEGER\n'})
    graph = er_diagram(index, SCAN)
    assert graph['nodes'][0]['fields'] == []


def test_function_reference_opens_the_definition_in_a_cited_file():
    index = Files({'app.py': 'def match(request):\n    return request\n',
                   'other.py': 'def match(item):\n    return item\n'})
    symbols = definitions(index, SCAN, index.code_paths(1))
    sources = [{'source_id': 'S1', 'path': 'app.py'}, {'source_id': 'S2', 'path': 'other.py'}]
    claim = {'text': 'The `match` function receives the request.', 'source_ids': ['S1']}
    refs = references(claim, sources, symbols)
    assert [(ref['name'], ref['path'], ref['line']) for ref in refs] == [('match', 'app.py', 1)]
    assert refs[0]['url'].endswith('/app.py#L1')
    assert references({'text': 'The matching feature receives a request.', 'source_ids': ['S1']}, sources, symbols) == []
