"""Evidence-bound checks for numeric comparisons and live configuration claims.

Source code is parsed, never executed. Ambiguous comparisons stay with the normal
answer path; repository defaults never establish a production runtime value.
"""
import ast
from decimal import Decimal, InvalidOperation
import html
import operator
import re

NUMBER = r'-?\d+(?:\.\d+)?'
COMPARISON = re.compile(r'\b([A-Za-z_]\w*)\s*(<=|>=|==|!=|<|>)\s*([A-Z][A-Z0-9_]+)\b')
OPS = {ast.Lt: ('<', operator.lt), ast.LtE: ('<=', operator.le),
       ast.Gt: ('>', operator.gt), ast.GtE: ('>=', operator.ge),
       ast.Eq: ('==', operator.eq), ast.NotEq: ('!=', operator.ne)}


def terms(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return {w.removesuffix('s') for w in re.findall(r'[a-z]+', text.lower())}


def scenario(question):
    """One numeric input, rather than a version, ticket ID or two choices."""
    values = re.findall(r'(?<![\w.])' + NUMBER + r'(?!\w|\.\d)', question)
    if len(values) != 1 or not re.search(
            r'\b(?:score[sd]?|value|count|amount|latency|temperature|size|age|retries)\b', question, re.I):
        return None
    return Decimal(values[0])


def comparison_references(question, sources):
    if scenario(question) is None:
        return []
    wanted = terms(question)
    refs = []
    for source in sources:
        for left, _, right in COMPARISON.findall(html.unescape(source['text'])):
            if terms(left) & wanted and (left, right) not in refs:
                refs.append((left, right))
    return refs[:4]


def _number(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, str):
        try:
            number = Decimal(str(node.value))
            return number if number.is_finite() else None
        except InvalidOperation:
            return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _number(node.operand)
        return (-value if isinstance(node.op, ast.USub) else value) if value is not None else None
    return None


def _default(node):
    # Recognize syntax, never call a function from an excerpt.
    integer_cast = False
    numeric_cast = False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'float', 'int'} and len(node.args) == 1:
        numeric_cast = True
        integer_cast = node.func.id == 'int'
        node = node.args[0]
    if isinstance(node, ast.Call) and ast.unparse(node.func) in {'os.getenv', 'os.environ.get'} and len(node.args) == 2:
        node, env = node.args[1], True
    else:
        env = False
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and not numeric_cast:
        return None, env
    number = _number(node)
    if integer_cast and number is not None and number != number.to_integral_value():
        return None, env
    return number, env


def _line_node(line):
    text = line.strip()
    try:
        if text.startswith(('if ', 'elif ')) and text.endswith(':'):
            return ast.parse(text.split(' ', 1)[1][:-1], mode='eval').body
        return ast.parse(text).body[0]
    except (SyntaxError, IndexError, ValueError):
        return None


def numeric_answer(question, sources):
    value = scenario(question)
    if value is None:
        return None
    wanted = terms(question)
    definitions, comparisons, unknown_assignments = {}, [], set()
    for source in sources:
        if not source['path'].endswith('.py') or source['path'].startswith(('jira/', 'slack/')):
            continue
        for line in source['text'].splitlines():
            node = _line_node(line)
            if node is None:
                continue
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                number, env = _default(node.value)
                key = (source['path'], node.targets[0].id)
                if number is not None and line == line.lstrip():
                    definitions.setdefault(key, []).append((number, env, source['source_id']))
                else:
                    unknown_assignments.add(key)
            for comparison in ast.walk(node):
                if (isinstance(comparison, ast.Compare) and len(comparison.ops) == 1
                        and isinstance(comparison.left, ast.Name) and isinstance(comparison.comparators[0], ast.Name)
                        and type(comparison.ops[0]) in OPS and terms(comparison.left.id) & wanted):
                    comparisons.append((comparison, source))
    matched = {}
    for comparison, source in comparisons:
        name = comparison.comparators[0].id
        definitions_here = definitions.get((source['path'], name), [])
        # Missing or conflicting definitions and cross-file name collisions are
        # not grounds to choose a convenient value.
        if (source['path'], name) in unknown_assignments or len({(n, env) for n, env, _ in definitions_here}) != 1:
            continue
        threshold, env, definition_id = definitions_here[0]
        symbol, compare = OPS[type(comparison.ops[0])]
        expression = ast.unparse(comparison)
        matched[(source['path'], expression, threshold)] = (comparison.left.id, name, symbol,
            compare(value, threshold), threshold, env, source, definition_id)
    if len(matched) != 1:
        return None
    left, right, symbol, result, threshold, env, comparison_source, definition_id = next(iter(matched.values()))
    text = (f'With `{left} = {value}` and the repository {"default" if env else "value"} '
            f'`{right} = {threshold}`, `{left} {symbol} {right}` evaluates to '
            f'`{value} {symbol} {threshold}`: {str(result).lower()}. ')
    text += ('The comparison is true; this alone does not establish the final action.' if result else
             'This input does not trigger the action through that comparison alone; other conditions may still trigger it.')
    if env:
        text += ' This assumes the environment has not overridden the default.'
    # Preserve a visible OR branch and AND-NOT guard without pretending the input
    # supplied values for either. This pattern works for any flag/output names.
    binding = None
    for line in comparison_source['text'].splitlines():
        node = _line_node(line)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if ast.unparse(node.value) == f'{left} {symbol} {right}':
                binding = node.targets[0].id
    if binding:
        for line in comparison_source['text'].splitlines():
            try:
                record = ast.parse('{' + line.strip().rstrip(',') + '}', mode='eval').body
            except SyntaxError:
                continue
            if not isinstance(record, ast.Dict) or len(record.values) != 1:
                continue
            expression = record.values[0]
            if not (isinstance(expression, ast.BoolOp) and isinstance(expression.op, ast.And) and len(expression.values) == 2):
                continue
            branches, guard = expression.values
            if not (isinstance(branches, ast.BoolOp) and isinstance(branches.op, ast.Or)
                    and len(branches.values) == 2 and all(isinstance(n, ast.Name) for n in branches.values)
                    and isinstance(guard, ast.UnaryOp) and isinstance(guard.op, ast.Not) and isinstance(guard.operand, ast.Name)
                    and isinstance(record.keys[0], ast.Constant) and isinstance(record.keys[0].value, str)):
                continue
            other = [n.id for n in branches.values if n.id != binding]
            if len(other) == 1:
                text += (f' For `{record.keys[0].value}`, `{other[0]}` can also trigger the result; '
                         f'`{guard.operand.id}` must be false in either case.')
                break
    return {'statements': [{'text': text, 'source_ids': list(dict.fromkeys([comparison_source['source_id'], definition_id]))}],
            'missing_information': '', '_verification': 'numeric_code_rule'}


def runtime_lookup(question):
    if not re.search(r'\b(?:production|prod|live environment|deployed environment)\b', question, re.I):
        return False
    if re.search(r'\b(?:how|why|should|could|would|default|example|propos\w*)\b', question, re.I):
        return False
    return bool(re.search(r'\b(?:what|which|is|are|confirm)\b', question, re.I))


def runtime_answer(question, sources):
    """Report explicit runtime observations in their own words, or disclose the gap.

This conservative check does not independently inspect the live environment.
"""
    if not runtime_lookup(question):
        return None
    subject = terms(question) - set('what which is are confirm the a an in on of for currently actual configured configuration production prod live environment deployed using running value setting'.split())
    observations = []
    for source in sources:
        path = source['path'].lower()
        if not (path.startswith(('jira/', 'slack/')) or path.endswith(('.md', '.txt', '.log'))):
            continue
        if re.search(r'\b(?:synthetic|demo|example|fixture)\b', source['text'], re.I):
            continue
        for line in source['text'].splitlines():
            if not re.search(r'\b(?:production|prod|live environment)\b', line, re.I):
                continue
            if not re.search(r'\b(?:verified|observed|confirmed|readback|effective|inspected)\b', line, re.I):
                continue
            if re.search(r'\b(?:not|never|unknown|unverified|unconfirmed|pending|proposal|plan|should|could|may|might|default)\b|\?', line, re.I):
                continue
            if not subject or not (subject & terms(line)):
                continue
            quote = line.strip()
            if len(quote) > 700:
                continue
            if quote not in [x['quote'] for x in observations]:
                observations.append({'quote': quote, 'source_id': source['source_id']})
    if observations:
        return {'statements': [{'text': 'The retrieved deployment record reports: ' + item['quote'],
                                'source_ids': [item['source_id']]} for item in observations[:3]],
                'missing_information': 'These are recorded observations; the current live environment has not been independently checked.'}
    return {'statements': [], 'missing_information':
            'The current production setting cannot be confirmed from the retrieved evidence. '
            'Repository defaults, example configuration and demo decisions do not establish a deployed value. '
            'A production configuration readback or a verified deployment record for this setting is needed.'}


def checked_answer(question, sources):
    return runtime_answer(question, sources) or numeric_answer(question, sources)


def generation_sources(question, sources):
    """A decision must cite its discussion/record, not just a matching code default."""
    if not re.search(r'\b(?:decision|decided|approved|agreed)\b', question, re.I):
        return sources
    subject = terms(question) - set('what which is are the a an final latest decision decided approved agreed on for or and to we'.split())
    records = [(len(subject & terms(s['text'])), s) for s in sources
               if re.search(r'\b(?:decision|decided|approved|agreed|proposal|correction|supersed\w*)\b', s['text'], re.I)]
    best = max((score for score, _ in records), default=0)
    # Keep relevant conflicting proposals together; only an explicit correction
    # can resolve them. The prompt still requires disclosing unresolved conflict.
    return [s for score, s in records if score >= max(1, best / 2)] if best else sources
