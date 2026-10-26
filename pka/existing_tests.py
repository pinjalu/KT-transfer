"""Explain stored Python test definitions without importing or executing project code."""
import ast
from pathlib import PurePosixPath

from pka.config import source_url
from pka.features import TEST_FILE

MAX_FILES, MAX_TESTS, MAX_CHECKS = 100, 300, 20


def spelling(node):
    return ast.unparse(node)[:400]


def body_nodes(node):
    """Walk control flow, but do not attribute nested helper bodies to the test."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from body_nodes(child)


def qualified(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, 'self' if node.id == 'self' else '')
    if isinstance(node, ast.Attribute):
        return qualified(node.value, aliases) + '.' + node.attr
    return ''


def assertion_reason(node):
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        names = {ast.Eq: 'equality', ast.NotEq: 'a difference', ast.Lt: 'a strict upper bound',
                 ast.LtE: 'an inclusive upper bound', ast.Gt: 'a strict lower bound',
                 ast.GtE: 'an inclusive lower bound', ast.In: 'membership', ast.NotIn: 'absence',
                 ast.Is: 'object identity', ast.IsNot: 'different object identities'}
        return f'Checks {names[type(node.ops[0])]} between {spelling(node.left)} and {spelling(node.comparators[0])}.'
    if isinstance(node, ast.BoolOp):
        return 'Requires ' + ('all' if isinstance(node.op, ast.And) else 'at least one') + ' of the written conditions to be truthy.'
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f'Requires {spelling(node.operand)} to be falsy.'
    return f'Requires {spelling(node)} to be truthy.'


def parse_file(path, numbered, repo, commit):
    result = {'path': path, 'url': source_url(repo, commit, path, 1), 'tests': [], 'gaps': []}
    if PurePosixPath(path).suffix.lower() != '.py':
        result['gaps'].append('This file matches a test naming pattern. Assertion explanations currently support Python only.')
        return result
    if not numbered or numbered[-1][0] > 20000 or sum(len(line) for _, line in numbered) > 250000:
        result['gaps'].append('The stored file is empty or exceeds the analysis size limit.')
        return result
    lines = [''] * numbered[-1][0]
    for number, text in numbered:
        lines[number - 1] = text
    if len(numbered) != len(lines):
        result['gaps'].append('Some line positions are absent from the saved excerpts. Definitions may be incomplete.')
    text = '\n'.join(lines)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        result['gaps'].append('The saved Python text could not be parsed. It may be incomplete or use unsupported syntax.')
        return result
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            aliases.update({item.asname or item.name: item.name for item in node.names})
        elif isinstance(node, ast.ImportFrom) and node.module in {'pytest', 'unittest'}:
            aliases.update({item.asname or item.name: node.module + '.' + item.name for item in node.names})

    def evidence(node, explanation):
        start, end = node.lineno, node.end_lineno
        return {'line': start, 'end': end, 'code': '\n'.join(lines[start-1:end])[:1600],
                'explanation': explanation, 'url': source_url(repo, commit, path, start, end)}

    definitions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
            definitions.append(('', node, False, []))
        elif isinstance(node, ast.ClassDef):
            unit = any(qualified(base, aliases) == 'unittest.TestCase' for base in node.bases)
            if unit or node.name.startswith('Test'):
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith('test' if unit else 'test_'):
                        definitions.append((node.name, method, unit, node.decorator_list))
    unit_checks = {'assertEqual': 'Checks that the two values are equal.', 'assertNotEqual': 'Checks that the values differ.',
                   'assertTrue': 'Requires a truthy value.', 'assertFalse': 'Requires a falsy value.',
                   'assertIsNone': 'Requires None.', 'assertIsNotNone': 'Rejects None.',
                   'assertIn': 'Checks membership.', 'assertNotIn': 'Checks absence.',
                   'assertLess': 'Checks a strict upper bound.', 'assertLessEqual': 'Checks an inclusive upper bound.',
                   'assertGreater': 'Checks a strict lower bound.', 'assertGreaterEqual': 'Checks an inclusive lower bound.'}
    for owner, node, unit, class_decorators in definitions[:MAX_TESTS]:
        checks, markers = [], []
        for decorator in [*class_decorators, *node.decorator_list]:
            name = qualified(decorator.func if isinstance(decorator, ast.Call) else decorator, aliases)
            if name in {'pytest.mark.skip', 'pytest.mark.skipif', 'pytest.mark.xfail', 'pytest.mark.parametrize',
                        'unittest.skip', 'unittest.skipIf', 'unittest.skipUnless', 'unittest.expectedFailure'}:
                markers.append(evidence(decorator, f'Declares {name}; collection and conditions have not been evaluated.'))
        for child in body_nodes(node):
            if isinstance(child, ast.Assert):
                checks.append(evidence(child, assertion_reason(child.test)))
            elif isinstance(child, ast.Call):
                name = qualified(child.func, aliases)
                if name == 'pytest.raises' or unit and name in {'self.assertRaises', 'self.assertRaisesRegex'}:
                    if child.args:
                        checks.append(evidence(child, f'Expects {spelling(child.args[0])} to be raised by the guarded operation.'))
                elif unit and name.startswith('self.') and name[5:] in unit_checks:
                    checks.append(evidence(child, unit_checks[name[5:]]))
                elif name in {'pytest.skip', 'pytest.xfail'}:
                    markers.append(evidence(child, f'Contains {name}; this call may be conditional.'))
        gaps = []
        if not checks:
            gaps.append('No supported inline assertions were found. Helpers, fixtures or other frameworks may contain checks.')
        if len(checks) > MAX_CHECKS:
            gaps.append(f'Only the first {MAX_CHECKS} of {len(checks)} recognized checks are shown.')
        if any(isinstance(child, (ast.If, ast.For, ast.While, ast.Try)) for child in body_nodes(node)):
            gaps.append('Checks inside branches, loops or exception handlers may not execute on every path.')
        result['tests'].append({'name': f'{owner}.{node.name}' if owner else node.name,
            'line': node.lineno, 'end': node.end_lineno, 'url': source_url(repo, commit, path, node.lineno, node.end_lineno),
            'framework': 'unittest' if unit else 'Python test convention', 'status': 'definition_not_run',
            'description': (ast.get_docstring(node) or '')[:1200],
            'why': 'These checks document expectations and can detect changes that violate them when the test is collected and run.' if checks else 'The definition names a scenario, but its purpose cannot be established from supported inline checks.',
            'checks': checks[:MAX_CHECKS], 'markers': markers[:20], 'gaps': gaps})
    if len(definitions) > MAX_TESTS:
        result['gaps'].append(f'Only the first {MAX_TESTS} definitions in this file are shown.')
    if not definitions:
        result['gaps'].append('No supported test functions or test-class methods were found in this saved file.')
    return result


def derive(index, scan):
    paths = [path for path in index.code_paths(scan['id']) if TEST_FILE.search(path)]
    files, remaining = [], MAX_TESTS
    for path in paths[:MAX_FILES]:
        file = parse_file(path, index.file_lines(scan['id'], path), scan['repo'], scan['commit'])
        if len(file['tests']) > remaining:
            file['gaps'].append('Some definitions were omitted because the page limit was reached.')
        file['tests'] = file['tests'][:remaining]
        remaining -= len(file['tests'])
        files.append(file)
    return {'available': True, 'commit': scan['commit'], 'knowledge_revision': index.revision,
            'partial_scan': scan.get('status') == 'partial', 'files': files,
            'candidate_files': len(paths), 'definitions': MAX_TESTS - remaining,
            'limits': {'files': MAX_FILES, 'definitions': MAX_TESTS, 'checks_per_test': MAX_CHECKS},
            'omitted_files': max(0, len(paths) - MAX_FILES),
            'note': 'Static Python test definitions from saved files. No project code was imported, collected or executed. This is not a test report or a coverage measure.'}
