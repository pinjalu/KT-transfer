"""Link function names in overview prose to definitions in the saved source snapshot."""
import re

from pka.config import source_url
from pka.index import TEST_PATH


DEFINITIONS = (
    re.compile(r'^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\('),
    re.compile(r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\('),
    re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>'),
    re.compile(r'^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\('),
)


def definitions(index, scan, paths):
    """Only declarations in this system; duplicate names keep their separate locations."""
    found = []
    for path in paths:
        if TEST_PATH.search(path) or not path.endswith(('.py', '.js', '.jsx', '.mjs', '.ts', '.tsx', '.go')):
            continue
        for line, text in index.file_lines(scan['id'], path):
            match = next((m for pattern in DEFINITIONS if (m := pattern.match(text))), None)
            if match:
                found.append({'name':match.group(1), 'path':path, 'line':line,
                              'url':'' if scan.get('demo') else source_url(scan['repo'], scan['commit'], path, line)})
    return found


def references(statement, sources, symbols):
    """Attach only names expressly written as code or named as a function in the claim."""
    cited = {source['path'] for source in sources if source['source_id'] in statement.get('source_ids', [])}
    found = []
    for name in sorted({symbol['name'] for symbol in symbols}, key=lambda value: (-len(value), value)):
        if not re.search(r'`' + re.escape(name) + r'`|\b' + re.escape(name) + r'\s*\(|\bfunction\s+' + re.escape(name) + r'\b',
                         statement['text']):
            continue
        candidates = [symbol for symbol in symbols if symbol['name'] == name]
        within = [symbol for symbol in candidates if symbol['path'] in cited]
        chosen = within if len(within) == 1 else candidates if len(candidates) == 1 else []
        if chosen and chosen[0]['url']:
            found.append(chosen[0])
        if len(found) >= 5:
            break
    return found
