import pytest
from fastapi.testclient import TestClient as AnonymousClient
from auth_helpers import OwnerClient
from pka import existing_tests
from pka.connectors.base import SourceError
from pka.index import Index, chunk_file
from pka.web import create_app

COMMIT = 'a' * 40
SAMPLE = '''import pytest as pt
from unittest import TestCase as Case

@pt.mark.parametrize("score", [0.44, 0.45])
def test_threshold(score):
    """Equality stays on the answer path."""
    assert (score < 0.45) == (score == 0.44)
    assert 0.45 >= score
    def unused_helper():
        assert False

@pt.mark.skipif(True, reason="needs fixture")
async def test_failure():
    with pt.raises(ValueError):
        fail()

class LoginChecks(Case):
    def testInvalid(self):
        self.assertEqual(response.status_code, 401)
        with self.assertRaises(ValueError):
            login()

def helper():
    assert False
'''


def parsed(text=SAMPLE, path='tests/test_login.py'):
    return existing_tests.parse_file(path, list(enumerate(text.splitlines(), 1)), 'acme/app', COMMIT)


def test_real_assertions_exceptions_aliases_and_markers_have_original_lines():
    result = parsed()
    tests = result['tests']
    assert [test['name'] for test in tests] == ['test_threshold', 'test_failure', 'LoginChecks.testInvalid']
    assert [len(test['checks']) for test in tests] == [2, 1, 2]
    assert tests[0]['description'] == 'Equality stays on the answer path.'
    assert tests[0]['checks'][0]['code'] == '    assert (score < 0.45) == (score == 0.44)'
    assert 'inclusive lower bound' in tests[0]['checks'][1]['explanation']
    assert tests[0]['checks'][0]['url'].endswith('#L7')
    assert COMMIT in tests[0]['url']
    assert 'parametrize' in tests[0]['markers'][0]['explanation']
    assert 'skipif' in tests[1]['markers'][0]['explanation']
    assert 'ValueError' in tests[1]['checks'][0]['explanation']
    assert all(test['status'] == 'definition_not_run' for test in tests)


@pytest.mark.parametrize('expression,words', [('value < 3','strict upper'), ('value <= 3','inclusive upper'),
    ('value > 3','strict lower'), ('value != 3','difference'), ('value is None','object identity'),
    ('value not in items','absence'), ('a and b','all'), ('a or b','at least one'), ('not value','falsy')])
def test_comparison_and_boolean_semantics_are_preserved(expression, words):
    check = parsed('def test_boundary():\n    assert ' + expression)['tests'][0]['checks'][0]
    assert words in check['explanation']


def test_no_execution_no_inferred_coverage_and_nested_helpers_are_not_counted(tmp_path):
    sentinel = tmp_path/'never-created'
    result = parsed(f'open({str(sentinel)!r}, "w").write("bad")\ndef test_helpers():\n    helper()\n    def nested():\n        assert False')
    assert not sentinel.exists()
    assert not result['tests'][0]['checks']
    assert 'Helpers' in result['tests'][0]['gaps'][0]


def test_unknown_framework_calls_and_non_test_methods_are_not_assertions():
    result = parsed('class TestHelper:\n    def testing_tool(self):\n        assert False\n    def test_real(self):\n        self.assertEqual(1, 2)\n        pytest.raises(ValueError)')
    assert [test['name'] for test in result['tests']] == ['TestHelper.test_real']
    assert not result['tests'][0]['checks']


def test_class_markers_branch_conditions_and_gaps_are_visible():
    result = parsed('import pytest\n@pytest.mark.xfail\nclass TestBranch:\n    def test_branch(self):\n        if ready:\n            assert value\n        pytest.skip("not ready")')
    test = result['tests'][0]
    assert len(test['markers']) == 2
    assert any('branches' in gap for gap in test['gaps'])


def test_unsupported_missing_and_invalid_sources_do_not_claim_no_project_tests():
    assert 'Python only' in parsed('test("works")', 'tests/app.test.ts')['gaps'][0]
    assert 'could not be parsed' in parsed('def test_broken(')['gaps'][0]
    result = existing_tests.parse_file('test_a.py', [(1,'def test_a():'), (3,'    assert True')], 'acme/app', COMMIT)
    assert 'absent' in result['gaps'][0]
    assert result['tests'][0]['checks'][0]['line'] == 3
    assert 'size limit' in existing_tests.parse_file('test_a.py', [(20001,'pass')], 'acme/app', COMMIT)['gaps'][0]


def seed(index):
    scan = {'repo': 'demo/example-shop', 'branch': 'main', 'commit': COMMIT, 'status': 'partial'}
    ident = index.new_scan(scan)
    chunks = chunk_file('tests/test_login.py', SAMPLE) + chunk_file('tests/app.test.ts', 'test("hello")')
    index.activate(ident, chunks, scan)
    return index.active_scan()


def test_inventory_source_isolation_limits_and_local_snapshot_links(tmp_path, monkeypatch):
    index = Index(tmp_path/'index.sqlite3')
    scan = seed(index)
    body = existing_tests.derive(index, scan)
    assert body['partial_scan'] and body['definitions'] == 3
    assert body['candidate_files'] == 2
    monkeypatch.setattr(existing_tests, 'MAX_TESTS', 1)
    assert existing_tests.derive(index, scan)['definitions'] == 1
    monkeypatch.setattr(existing_tests, 'MAX_FILES', 1)
    assert existing_tests.derive(index, scan)['omitted_files'] == 1
    path = 'local://' + 'b'*64 + '/tests/test_login.py'
    assert parsed(path=path)['tests'][0]['url'].startswith('/source?snapshot=')


def test_api_requires_session_rechecks_access_and_withholds_changed_revisions(tmp_path, monkeypatch):
    app = create_app(True, tmp_path/'web.sqlite3')
    with AnonymousClient(app, base_url='http://localhost:8000', headers={'x-pka-request': '1'}) as client:
        assert client.get('/api/existing-tests').status_code == 401
    with OwnerClient(app, base_url='http://localhost:8000', headers={'x-pka-request': '1'}) as client:
        initial = client.get('/api/existing-tests')
        assert initial.status_code == 200, initial.text
        assert not initial.json()['available']
        service = app.state.service
        seed(service.index)
        response = client.get('/api/existing-tests')
        assert response.status_code == 200 and response.json()['definitions'] == 3
        original = existing_tests.derive
        def change(index, scan):
            result = original(index, scan)
            index.invalidate()
            return result
        monkeypatch.setattr(existing_tests, 'derive', change)
        assert client.get('/api/existing-tests').status_code == 409
        seed(service.index)
        async def denied(scan): raise SourceError('access_denied', 'Source access revoked')
        monkeypatch.setattr(service, 'check_external_access', denied)
        response = client.get('/api/existing-tests')
        assert response.status_code == 409
        assert 'test_threshold' not in response.text
