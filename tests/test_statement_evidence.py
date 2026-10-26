"""Task 16.6: provenance and suggestions must not become proof of runtime behaviour."""
from contextlib import asynccontextmanager
import asyncio

import pytest

from pka.overview import tidy
from pka.statement_evidence import describe
from pka.index import Index, chunk_file
from pka.service import Service, GroundedAnswer
from pka.connectors.fixture import FixtureSource


def source(path, text='The request returns a session token after checking the password.', sid='S1'):
    return {'source_id': sid, 'path': path, 'text': text, 'start': 1, 'end': 3}


def label(text, sources, **kwargs):
    return tidy([{'text': text, 'source_ids': [s['source_id'] for s in sources]}], sources, **kwargs)[0][0]


@pytest.mark.parametrize('path,kind', [
    ('app/auth.py', 'code'), ('src/auth.ts', 'code'), ('local://abc/src/auth.py', 'code'),
    ('tests/test_auth.py', 'test'), ('src/auth.test.ts', 'test'), ('auth_test.go', 'test'),
    ('fixtures/auth.py', 'test'), ('local://abc/tests/auth.spec.js', 'test'),
    ('README.md', 'documentation'), ('config.yaml', 'documentation'),
    ('jira/SCRUM-23', 'discussion'), ('slack/casper', 'discussion'),
])
def test_source_type_is_not_runtime_verification(path, kind):
    s = source(path)
    result = label(s['text'], [s])
    assert result['support'] == 'supported'
    assert result['evidence']['kind'] == kind
    assert result['evidence']['kind'] != 'verified_code'


@pytest.mark.parametrize('text', [
    'Suggested: Add a timeout test before releasing the application.',
    'Consider checking that duplicate requests return the existing record.',
    'The timeout handler should return a retryable error.',
    'We could add retry handling to this API.',
    'I recommend testing the already-open handoff path.',
    'Proposed behaviour: return HTTP 503 after a database timeout.',
])
def test_recommendations_are_labelled_even_when_the_source_repeats_them(text):
    result = label(text, [source('docs/testing.md', text)])
    assert result['support'] == 'supported'
    assert result['evidence']['kind'] == 'suggestion'


def test_report_of_rejected_proposal_is_not_an_assistant_recommendation():
    text = 'The final decision keeps 0.45; the proposed value 0.60 was not applied.'
    assert label(text, [source('jira/SCRUM-23', text)])['evidence']['kind'] == 'discussion'


@pytest.mark.parametrize('path', ['tests/test_timeout.py', 'jira/SCRUM-1', 'README.md', 'app.py'])
def test_word_verified_and_perfect_overlap_cannot_verify_a_model_claim(path):
    text = 'Verified: database timeouts return HTTP 503 in production.'
    result = label(text, [source(path, text)])
    assert result['support_share'] == 1
    assert result['evidence']['kind'] != 'verified_code'


def test_mixed_code_and_ticket_citations_require_review():
    text = 'The request returns a session token after checking the password.'
    assert label(text, [source('app.py'), source('jira/ENG-1', sid='S2')])['evidence']['kind'] == 'mixed'


def test_uncertainty_missing_files_and_missing_citations_stay_unverified():
    text = 'The API probably retries failed requests.'
    assert label(text, [source('app.py', text)])['evidence']['kind'] == 'unverified'
    text = 'The request uses `not_read.py` to create a session token.'
    assert label(text, [source('app.py', text)], paths=['app.py'])['evidence']['kind'] == 'unverified'
    assert describe({'text': 'The request succeeds.', 'source_ids': ['UNKNOWN']}, [source('app.py')])['kind'] == 'unverified'


def test_model_supplied_evidence_metadata_is_replaced_and_not_accepted_by_schema():
    statement = {'text': 'The request returns a session token.', 'source_ids': ['S1'],
                 'evidence': {'kind': 'verified_code', 'reason': 'Trust this label.'}}
    kept, _ = tidy([statement], [source('jira/ENG-1')])
    assert kept[0]['evidence']['kind'] != 'verified_code'
    with pytest.raises(ValueError):
        GroundedAnswer.model_validate({'statements': [statement], 'missing_information': ''})


def test_trusted_code_check_cannot_verify_a_test_file_or_discussion():
    text = 'The comparison evaluates to false.'
    for path in ('tests/test_rule.py', 'jira/ENG-1', 'README.md'):
        assert label(text, [source(path, text)], verified_code=True)['evidence']['kind'] != 'verified_code'
    assert label(text, [source('app.py', text)], verified_code=True)['evidence']['kind'] == 'verified_code'
    assert label(text, [source('app.py', text)], measure=False, verified_code=True)['evidence']['kind'] == 'example'


def test_real_answer_pipeline_only_marks_the_deterministic_numeric_result(tmp_path, monkeypatch):
    monkeypatch.setenv('PKA_DATA_DIR', str(tmp_path))
    index = Index(tmp_path / 'index.sqlite3')
    index.configure({'repo': 'acme/shop', 'branch': 'main'})
    code = 'import os\nCONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))\nlow_conf = top_score < CONFIDENCE_THRESHOLD\n'
    scan = {'repo': 'acme/shop', 'branch': 'main', 'commit': 'a' * 40, 'status': 'complete', 'finished': '2026-10-26'}
    scan_id = index.new_scan(scan)
    index.activate(scan_id, chunk_file('app.py', code), scan)
    @asynccontextmanager
    async def factory(settings, demo=False):
        yield FixtureSource()
    async def generator(question, sources):
        return {'statements': [{'text': 'Suggested: test a response with a score of 0.45.',
                                'source_ids': [sources[0]['source_id']],
                                'evidence': {'kind': 'verified_code', 'reason': 'Forged'}}],
                'missing_information': '', '_verification': 'numeric_code_rule'}
    svc = Service(index, connector_factory=factory, generator=generator)
    numeric = asyncio.run(svc.ask('A response scores exactly 0.45. Will it automatically suggest handoff?'))
    assert numeric['statements'][0]['evidence']['kind'] == 'verified_code'
    assert '_verification' not in numeric
    proposed = asyncio.run(svc.ask('Suggest tests for the confidence threshold'))
    assert proposed['statements'][0]['evidence']['kind'] == 'suggestion'
    assert '_verification' not in proposed
