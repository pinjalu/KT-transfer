"""Project-specific overview context stays bounded, citable and scoped to saved sources."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from pka.config import now
from pka.connectors.fixture import FixtureSource, COMMIT
from pka.facts import derive
from pka.index import Index, chunk_file
from pka.llm import topics as topic_cache
from pka.overview import TOPICS
from pka.overview_context import CONTEXT_CHARS, MAX_SOURCES, select_sources
from pka.roles import describe
from pka.service import Service


FILES = {
    'README.md': '# Parcel desk\nCustomers look up delivery status by entering a parcel number.\n'
        'The browser sends the number to /track and displays the saved delivery status.\n'
        + '\n'.join(f'Background note {i}.' for i in range(140))
        + '\n## Getting started\nInstall Node 22. From the web folder, run npm ci, then npm run desk.\n'
        'Open http://localhost:4317. Set PARCEL_DB to the parcel database path.\n',
    'web/package.json': '{\n  "engines": {"node": "22"},\n  "scripts": {\n'
        '    "desk": "node server.js --port 4317"\n  }\n}\n',
    'app.py': '"""Receive parcel numbers and return their delivery status."""\n'
        'from tracking import track\n@app.get("/track")\ndef find(number):\n    return track(number)\n',
    'tracking.py': '"""Look up the saved delivery status for a parcel."""\n'
        'from store import lookup\ndef track(number):\n    return lookup(number)\n',
    'store.py': '"""Read the parcel database."""\nimport os\nDB = os.getenv("PARCEL_DB")\n'
        'SCHEMA = "CREATE TABLE parcels (number TEXT, status TEXT)"\n'
        'def lookup(number):\n    return {"number": number}\n',
    'utils/format.py': 'def format_value(value):\n    return str(value)\n',
    'tests/test_setup.py': '# npm start, port 9999: test-only instructions\n',
    'third_party/README.md': '# Another product\nRun npm start on port 7777.\n',
}


def prepared(tmp_path, repo='acme/parcels', prefix=''):
    index = Index(tmp_path/'index.sqlite3')
    index.configure({'repo': repo, 'branch': 'main'})
    scan = {'id': 1, 'repo': repo, 'branch': 'main', 'commit': COMMIT,
            'status': 'complete', 'finished': now()}
    scan['id'] = index.new_scan(scan)
    files = {prefix + path: text for path, text in FILES.items()}
    index.activate(1, [chunk for path, text in files.items() for chunk in chunk_file(path, text)], scan)
    facts = derive(index, scan)
    return index, scan, files, facts, describe(index, scan, facts)


@pytest.mark.parametrize('repo,prefix', [
    ('acme/parcels', ''), ('local:D:/Projects/parcels', ''),
    ('zip:D:/managed/parcels', ''), ('acme/parcels', 'local/abc123/parcels/'),
])
@pytest.mark.parametrize('topic', ['purpose', 'architecture', 'setup', 'flows'])
def test_main_project_context_survives_irrelevant_search_hits(tmp_path, repo, prefix, topic):
    index, scan, files, facts, roles = prepared(tmp_path, repo, prefix)
    irrelevant = [{'path': prefix + 'utils/format.py', 'text': FILES['utils/format.py'],
                   'start': 1, 'end': 2, 'source_id': 'S99'}]
    sources = select_sources(index, scan, topic, irrelevant, facts, roles)
    paths = [s['path'] for s in sources]
    assert prefix + 'README.md' in paths
    if topic == 'setup':
        assert prefix + 'web/package.json' in paths
        assert prefix + 'store.py' in paths
        assert 'npm ci' in '\n'.join(s['text'] for s in sources)
        assert 'http://localhost:4317' in '\n'.join(s['text'] for s in sources)
    else:
        assert prefix + 'app.py' in paths and prefix + 'tracking.py' in paths
        if topic == 'flows':
            assert prefix + 'utils/format.py' not in paths
        else:
            assert paths.index(prefix + 'app.py') < paths.index(prefix + 'utils/format.py')
        assert 'return track(number)' in '\n'.join(s['text'] for s in sources)
    assert not any('third_party/' in p or 'tests/' in p for p in paths)
    assert len(sources) <= MAX_SOURCES
    assert sum(len(s['text']) for s in sources) <= CONTEXT_CHARS
    assert [s['source_id'] for s in sources] == [f'S{i + 1}' for i in range(len(sources))]
    for source in sources:
        assert source['text'].splitlines() == files[source['path']].splitlines()[source['start'] - 1:source['end']]


def test_missing_setup_is_not_replaced_by_another_snapshot_or_test_fixture(tmp_path):
    index, scan, _, facts, roles = prepared(tmp_path)
    new_scan = {**scan, 'id': 2, 'commit': 'b' * 40}
    index.activate(2, chunk_file('calculator.py', 'def add(a, b):\n    return a + b\n'), new_scan)
    sources = select_sources(index, new_scan, 'setup', [], derive(index, new_scan), {})
    assert sources == []


@pytest.mark.parametrize('prefix', ['', 'local://snapshot/'])
def test_purpose_prefers_django_request_handler_over_stylesheets(tmp_path, prefix):
    index, scan, _, _, _ = prepared(tmp_path)
    files = {
        prefix + 'apps/shop/urls.py': 'from django.urls import path\nfrom .views import SearchView\nurlpatterns = [\n    path("search", SearchView.as_view(), name="search"),\n]\n',
        prefix + 'apps/shop/views.py': 'class SearchView(View):\n    def post(self, request):\n        company = request.POST["company"]\n        return render(request, "results.html", {"company": company})\n',
        prefix + 'static/css/main.css': 'body { color: blue; }\n',
        prefix + 'manage.py': 'from django.core.management import execute_from_command_line\n',
    }
    index.activate(scan['id'], [chunk for path, content in files.items()
                                for chunk in chunk_file(path, content)], scan)
    found = derive(index, scan)
    noisy = [{'path':prefix + 'static/css/main.css', 'start':1, 'end':1,
              'text':files[prefix + 'static/css/main.css'], 'source_id':'S99'}]
    sources = select_sources(index, scan, 'purpose', noisy, found,
                             describe(index, scan, found), paths=list(files))
    selected = {item['path']:item['text'] for item in sources}
    assert prefix + 'apps/shop/urls.py' in selected
    assert 'class SearchView' in selected[prefix + 'apps/shop/views.py']
    assert prefix + 'static/css/main.css' not in selected
    assert prefix + 'manage.py' not in selected


def test_context_does_not_bridge_missing_lines(tmp_path):
    index = Index(tmp_path/'index.sqlite3')
    scan = {'id': 1, 'repo': 'acme/parcels', 'commit': COMMIT, 'status': 'complete'}
    chunks = chunk_file('README.md', '# Parcel desk\nTracks parcels.\n')
    chunks += [{**chunk_file('README.md', '## Startup\npython hidden.py\n')[0], 'start': 50, 'end': 51}]
    index.activate(1, chunks, scan)
    sources = select_sources(index, scan, 'purpose', [], [], {})
    assert len(sources) == 1
    assert sources[0]['end'] == 2 and 'hidden.py' not in sources[0]['text']


def test_build_supplies_main_files_and_does_not_reuse_old_topic_prompts(tmp_path, monkeypatch):
    from pka import service as module
    index, scan, _, _, _ = prepared(tmp_path)
    selected_topics = [t for t in TOPICS if t['key'] in {'purpose', 'architecture', 'setup', 'flows'}]
    monkeypatch.setattr(module, 'topics_for', lambda present: selected_topics)
    monkeypatch.setattr(index, 'search_many', lambda *args, **kwargs: [])
    seen = {}

    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()

    async def generator(question, sources):
        topic = next(t for t in selected_topics if t['ask'] == question)
        seen[topic['key']] = sources
        return {'statements': [], 'missing_information': 'Fixture: no model was called.'}

    svc = Service(index, connector_factory=factory, generator=generator)
    result = asyncio.run(svc.build_overview())
    assert result['complete'] and set(seen) == {'purpose', 'architecture', 'setup', 'flows'}
    assert 'app.py' in {s['path'] for s in seen['purpose']}
    assert 'tracking.py' in {s['path'] for s in seen['architecture']}
    assert 'web/package.json' in {s['path'] for s in seen['setup']}
    for topic in selected_topics:
        current = topic_cache.key(scan, index.revision, topic, seen[topic['key']], 'routing')
        old = topic_cache.key(scan, index.revision, {**topic, 'ask': 'Old generic instructions'}, seen[topic['key']], 'routing')
        assert current != old
    seen.clear()
    cached = asyncio.run(svc.build_overview())
    assert not seen and all(s.get('cache_hit') for s in cached['sections'])


def test_overview_retries_a_prompt_echo_with_project_specific_evidence(tmp_path, monkeypatch):
    from pka import service as module
    index, _, _, _, _ = prepared(tmp_path)
    monkeypatch.setattr(module, 'topics_for', lambda present: [TOPICS[0]])
    calls = []

    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()

    async def generator(question, sources):
        calls.append(question)
        if len(calls) == 1:
            return {'statements':[{'text':'**Problem:** Who has a need, and what difficulty are they trying to solve?',
                                   'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
        return {'statements':[
            {'text':'**Problem:** Customers need to look up delivery status by entering a parcel number.',
             'source_ids':[sources[0]['source_id']]},
            {'text':'**Solution:** Parcel desk lets customers enter a parcel number and see its saved delivery status.',
             'source_ids':[sources[0]['source_id']]},
        ], 'missing_information':''}

    result = asyncio.run(Service(index, connector_factory=factory, generator=generator).build_overview())
    assert len(calls) == 2
    assert 'previous response' in calls[1]
    assert result['sections'][0]['story'] == {'problem':0, 'solution':1}
    assert not result['sections'][0]['error']


def test_repeated_prompt_echo_is_neither_displayed_nor_cached(tmp_path, monkeypatch):
    from pka import service as module
    index, _, _, _, _ = prepared(tmp_path)
    monkeypatch.setattr(module, 'topics_for', lambda present: [TOPICS[0]])
    calls = []

    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()

    async def generator(question, sources):
        calls.append(question)
        return {'statements':[{'text':'**Solution:** What does THIS project let that person do to address the problem? Describe the main product, not a list of technologies.',
                               'source_ids':[sources[0]['source_id']]}], 'missing_information':''}

    result = asyncio.run(Service(index, connector_factory=factory, generator=generator).build_overview())
    section = result['sections'][0]
    assert len(calls) == 2
    assert section['statements'] == []
    assert 'repeated instructions' in section['error']
    with index.db() as db:
        assert db.execute('SELECT COUNT(*) FROM ai_topic_cache').fetchone()[0] == 0


def test_flow_reads_the_real_request_and_output_instead_of_logging(tmp_path):
    index, scan, files, facts, roles = prepared(tmp_path)
    files['app.py'] = ('from tracking import track\n@app.post("/track")\n'
                       'def find(number):\n' + '    value = number\n' * 180 + '    return track(value)\n')
    files['web/client.js'] = 'async function submit(number) {\n  const reply = await fetch("/track", {body: number});\n  show(await reply.json());\n}\n'
    files['pipeline_debug.py'] = 'def log_pipeline_start(job_id):\n    print(job_id)\n'
    index.activate(scan['id'], [c for path, text in files.items() for c in chunk_file(path, text)], scan)
    logger = {'path':'pipeline_debug.py', 'start':1, 'end':2, 'text':files['pipeline_debug.py'], 'source_id':'S1'}
    sources = select_sources(index, scan, 'flows', [logger], derive(index, scan), {})
    text = '\n'.join(s['text'] for s in sources)
    assert '@app.post("/track")' in text and 'return track(value)' in text
    assert 'show(await reply.json())' in text
    assert 'log_pipeline_start' not in text
    assert sum(len(s['text']) for s in sources) <= CONTEXT_CHARS


def test_separate_systems_never_share_a_generation_request_or_citation_ids(tmp_path, monkeypatch):
    from pka import service as module
    from pka.connectors.base import SourceError
    index, scan, files, _, _ = prepared(tmp_path)
    prefix = 'local://' + 'c' * 64 + '/'
    local = {'README.md':'# Investor matching\nFind investors by a requested industry.\n',
             'app.py':'@app.post("/match")\ndef match(industry):\n    return {"industry":industry}\n'}
    files.update({prefix + path:text for path, text in local.items()})
    index.configure_source('local', {'repo':'local:D:/Projects/investor-matching'})
    index.activate(scan['id'], [c for path, text in files.items() for c in chunk_file(path, text)], scan)
    flow = next(t for t in TOPICS if t['key'] == 'flows')
    monkeypatch.setattr(module, 'topics_for', lambda present:[flow])
    seen = []
    fail_local = True
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()
    async def generator(question, sources):
        seen.append(sources)
        scopes = {s['path'].startswith('local://') for s in sources}
        assert len(scopes) == 1, 'Unrelated systems must never reach a model together'
        if fail_local and True in scopes:
            raise SourceError('model', 'Fixture local model is unavailable')
        return {'statements':[{'text':'Example input is processed by app.py.', 'source_ids':[sources[0]['source_id']]}], 'missing_information':''}
    svc = Service(index, connector_factory=factory, generator=generator)
    first = asyncio.run(svc.build_overview())
    sections = first['sections'][0]['system_sections']
    assert [s['system_name'] for s in sections] == ['parcels', 'investor-matching']
    assert not sections[0]['error'] and sections[1]['error']
    assert 'system_sections' in first['sections'][0]
    ids = [s['source_id'] for part in sections for s in part['sources']]
    assert len(ids) == len(set(ids))
    assert all(s.get('system_name') for part in sections for s in part['sources'])
    assert set(first['system_diagrams']) == {'primary', prefix}
    assert not any(node['path'].startswith(prefix) for diagram in first['system_diagrams']['primary']
                   for node in diagram['nodes'])
    assert set(first['system_feature_flows']) == {'primary', prefix}
    seen.clear()
    fail_local = False
    second = asyncio.run(svc.build_overview())
    assert len(seen) == 1 and all(s['path'].startswith(prefix) for s in seen[0])
    assert not second['sections'][0]['error']
