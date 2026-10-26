"""Describe evidence provenance without turning text overlap into verification."""
import re
from pathlib import PurePosixPath


CODE_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.rb', '.php',
                 '.cs', '.c', '.h', '.cpp', '.hpp', '.swift', '.kt', '.scala', '.sh', '.ps1', '.sql'}
TEST_PATH = re.compile(r'(^|/)(tests?|specs?|__tests__|fixtures?|__mocks__)/|(^|/)test_[^/]*$|'
                       r'(_test|_spec|\.test|\.spec)\.[^/]+$', re.I)
SUGGESTION = re.compile(
    r'^\s*(?:suggested|recommended|proposed)(?:\s+[\w -]{1,40})?\s*:|'
    r'^\s*(?:consider|add|write|create|introduce|implement|try|test|verify|check)\b|'
    r'\b(?:we|you|the team)\s+(?:should|could)\b|\bshould\b|'
    r'\bI\s+(?:recommend|suggest|propose)\b|'
    r'\b(?:recommended|suggested)\s+(?:to|that)\b', re.I)
UNCERTAIN = re.compile(r'\b(?:might|may|probably|likely|appears? to|possibly|assuming|hypothetical)\b', re.I)
REASONS = {
    'verified_code': 'Computed from parsed repository code for the stated input and assumptions. The running application was not tested.',
    'suggestion': 'A proposed action or expected behaviour, not proof of an implemented or tested outcome.',
    'code': 'An explanation citing source code. Citation and word matching do not verify the explanation or its runtime outcome.',
    'test': 'Cites a test definition or fixture. Its presence does not establish that the test ran or passed.',
    'documentation': 'Cites documentation or configuration. It does not establish the currently deployed behaviour.',
    'discussion': 'Cites a recorded requirement or discussion. A plan, agreement or reported result does not independently verify implementation.',
    'mixed': 'Combines different kinds of evidence. Check each claim against its sources before treating it as implemented behaviour.',
    'unverified': 'The available evidence does not independently verify this behaviour. Inspect the cited sources and stated assumptions.',
    'example': 'Example data; no live project behaviour was verified.',
}


def source_kind(source):
    path = source['path'].lower().replace('\\', '/')
    if path.startswith(('jira/', 'slack/')):
        return 'discussion'
    if path.startswith('local://'):
        path = path.split('/', 3)[-1]
    if TEST_PATH.search(path):
        return 'test'
    return 'code' if PurePosixPath(path).suffix in CODE_SUFFIXES else 'documentation'


def describe(statement, sources, *, example=False, verified_code=False):
    """The caller can mark a deterministic code calculation, never a model response.

    Classification is conservative and English-only. Missing/uncertain evidence is not
    promoted to verified, even when a source or generated sentence says 'verified'.
    """
    known = {s['source_id']: s for s in sources}
    ids = statement.get('source_ids', [])
    cited = [known[sid] for sid in ids if sid in known]
    kinds = {source_kind(s) for s in cited}
    text = statement['text']
    if example:
        kind = 'example'
    elif not cited or any(sid not in known for sid in ids):
        kind = 'unverified'
    elif verified_code and kinds == {'code'}:
        kind = 'verified_code'
    elif SUGGESTION.search(text):
        kind = 'suggestion'
    elif statement.get('files_not_read') or statement.get('support') in {'check this', 'not measured'}:
        kind = 'unverified'
    elif UNCERTAIN.search(text):
        kind = 'unverified'
    elif len(kinds) != 1:
        kind = 'mixed'
    else:
        kind = next(iter(kinds))
    return {'kind': kind, 'reason': REASONS[kind]}
