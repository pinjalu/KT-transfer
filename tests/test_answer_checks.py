import asyncio
from contextlib import asynccontextmanager

import pytest

from pka.answer_checks import checked_answer, generation_sources, numeric_answer, runtime_answer
from pka.config import LIMITS, now
from pka.connectors.fixture import FixtureSource
from pka.index import Index, chunk_file
from pka.service import Service


def source(text, path='rules.py', sid='S1'):
    return {'source_id': sid, 'path': path, 'text': text, 'start': 1, 'end': len(text.splitlines())}


@pytest.mark.parametrize('symbol,value,expected', [
    ('<', '0.44', True), ('<', '0.45', False), ('<', '0.46', False),
    ('<=', '0.45', True), ('>', '0.45', False), ('>=', '0.45', True),
    ('==', '0.45', True), ('!=', '0.45', False),
])
def test_exact_boundary_uses_code_operator(symbol, value, expected):
    evidence = [source(f'LIMIT = float(os.environ.get("LIMIT", "0.45"))\nlow = score {symbol} LIMIT')]
    answer = numeric_answer(f'A response scores exactly {value}. Will it trigger?', evidence)
    text = answer['statements'][0]['text']
    assert f'`{value} {symbol} 0.45`: {str(expected).lower()}' in text
    assert 'environment has not overridden' in text
    assert answer['statements'][0]['source_ids'] == ['S1']


def test_numeric_check_generalizes_to_other_names_values_and_paths():
    evidence = [source('MAX_AGE = 21\nallowed = age >= MAX_AGE', 'eligibility.py')]
    text = numeric_answer('With age 21, is this allowed?', evidence)['statements'][0]['text']
    assert '`21 >= 21`: true' in text
    assert '0.45' not in text


@pytest.mark.parametrize('evidence', [
    [source('low = score < LIMIT')],
    [source('LIMIT = 0.45\nLIMIT = 0.60\nlow = score < LIMIT')],
    [source('LIMIT = 0.45\nLIMIT = runtime_value()\nlow = score < LIMIT')],
    [source('LIMIT = int("0.45")\nlow = score < LIMIT')],
    [source('LIMIT = "0.45"\nlow = score < LIMIT')],
    [source('LIMIT = 0.45', 'other.py'), source('low = score < LIMIT')],
    [source('LIMIT = 0.45\nlow = score < LIMIT', 'jira/TEST-1')],
    [source('LIMIT = __import__("os").system("never execute")\nlow = score < LIMIT')],
    [source('LIMIT = 0.45\nlow = score < LIMIT'), source('LIMIT = 0.60\nlow = score < LIMIT', 'other.py', 'S2')],
])
def test_ambiguous_missing_or_non_code_values_are_not_computed(evidence):
    assert numeric_answer('A response scores 0.45. Will it trigger?', evidence) is None


def test_multiple_inputs_are_left_for_a_full_explanation():
    assert numeric_answer('Compare scores 0.45 and 0.60', [source('LIMIT = 0.45\nlow = score < LIMIT')]) is None


def test_final_boolean_guard_is_preserved_without_assuming_other_inputs():
    evidence = [source('LIMIT = 0.45\nlow = score < LIMIT\n"suggest": (low or missing_answer) and not already_open,')]
    text = numeric_answer('A response scores 0.45. Will it trigger?', evidence)['statements'][0]['text']
    assert '`missing_answer` can also trigger' in text
    assert '`already_open` must be false' in text


@pytest.mark.parametrize('text,path', [
    ('CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))', 'main.py'),
    ('Production handoff threshold default: 0.45', 'README.md'),
    ('Synthetic demo: verified production handoff threshold is 0.45.', 'jira/TEST-1'),
    ('We have not inspected production. Its handoff threshold is unknown.', 'slack/team'),
    ('Proposed production handoff threshold 0.60; confirmation pending.', 'slack/team'),
    ('Verified production login timeout = 30.', 'slack/team'),
])
def test_production_value_requires_relevant_observed_evidence(text, path):
    answer = runtime_answer('What handoff threshold is currently configured in production?', [source(text, path)])
    assert answer['statements'] == []
    assert 'cannot be confirmed' in answer['missing_information']


def test_explicit_runtime_record_is_attributed_without_claiming_live_verification():
    text = '2026-10-26: production configuration readback confirmed CONFIDENCE_THRESHOLD=0.63.'
    answer = runtime_answer('What confidence threshold is configured in production?', [source(text, 'slack/ops')])
    assert text in answer['statements'][0]['text']
    assert answer['statements'][0]['source_ids'] == ['S1']
    assert 'not been independently checked' in answer['missing_information']


def test_conflicting_runtime_records_are_not_silently_resolved():
    answer = runtime_answer('What threshold is configured in production?', [
        source('Production readback confirmed threshold=0.63.', 'slack/ops'),
        source('Production readback confirmed threshold=0.71.', 'jira/OPS-2', 'S2')])
    assert len(answer['statements']) == 2
    assert answer['missing_information']


@pytest.mark.parametrize('question', ['How do I configure production?',
    'What is the repository default threshold?', 'Why does production use this threshold?',
    'What is the final decision: 0.45 or 0.60?',
    'Can a public image prove that private S3 signing works?'])
def test_other_questions_still_use_the_normal_answer_path(question):
    assert checked_answer(question, [source('LIMIT = 0.45\nlow = score < LIMIT')]) is None


def test_decision_citations_use_the_record_and_keep_conflicting_proposals():
    evidence = [source('Threshold default: 0.45', 'README.md'),
                source('Proposal: handoff threshold 0.60.', 'slack/team', 'S2'),
                source('Final decision: retain handoff threshold 0.45; replaces the 0.60 proposal.', 'jira/TEST-1', 'S3')]
    selected = generation_sources('What is the final decision on the handoff threshold?', evidence)
    assert [s['source_id'] for s in selected] == ['S2', 'S3']
    assert generation_sources('What is the threshold default?', evidence) == evidence


def test_retrieval_adds_comparison_and_its_same_file_definition(tmp_path):
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo': 'acme/test', 'branch': 'main'})
    scan = {'id': 1, 'repo': 'acme/test', 'commit': 'a' * 40, 'status': 'complete', 'finished': now()}
    code = ('LIMIT = float(os.getenv("LIMIT", "0.45"))\n\n' +
            ''.join(f'def unrelated_{i}():\n    return {i}\n\n' for i in range(80)) +
            'def suggest(score):\n    low = score < LIMIT\n    return low\n')
    chunks = chunk_file('rules.py', code)
    chunks += chunk_file('jira/TEST-1', 'A response score suggests handoff when score < LIMIT. Test the boundary.')
    index.activate(1, chunks, scan)
    question = 'A response scores exactly 0.45. Will it suggest handoff?'
    found = index.search(question, scan)
    answer = numeric_answer(question, found)
    assert answer and '`0.45 < 0.45`: false' in answer['statements'][0]['text']
    assert sum(len(s['text']) for s in found) <= LIMITS.context_chars
    assert len(found) <= LIMITS.max_sources
    assert len({s['source_id'] for s in found}) == len(found)


@pytest.mark.parametrize('question,evidence,expected', [
    ('A response scores exactly 0.45. Will it suggest handoff?',
     [source('LIMIT = 0.45\nlow = score < LIMIT')], '`0.45 < 0.45`: false'),
    ('What threshold is currently configured in production?',
     [source('LIMIT = 0.45')], 'cannot be confirmed'),
])
def test_service_does_not_publish_a_models_wrong_boundary_or_production_claim(tmp_path, monkeypatch, question, evidence, expected):
    @asynccontextmanager
    async def connector(settings, demo=False):
        yield FixtureSource()
    async def wrong_model(question, sources):
        pytest.fail('These evidence checks should resolve the question without a model call.')
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo': 'acme/shop', 'branch': 'main'})
    service = Service(index, connector_factory=connector, generator=wrong_model)
    asyncio.run(service.scan())
    monkeypatch.setattr(index, 'search', lambda *a, **kw: evidence)
    answer = asyncio.run(service.ask(question))
    assert answer['error'] is None
    assert expected in ' '.join(s['text'] for s in answer['statements']) + answer['missing_information']
    assert answer['answer_id'] > 0
