"""A small ER map from explicit data declarations in the imported files."""
import re

from pka.config import source_url


CREATE = re.compile(r'\bCREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?(\w+)', re.I)
MODEL = re.compile(r'^\s*(?:export\s+)?model\s+(\w+)\s*\{')
ORM = re.compile(r'^(\s*)class\s+(\w+)\s*\(\s*([^)]+)\)\s*:')
TABLE_NAME = re.compile(r'__tablename__\s*=\s*["\'](\w+)["\']')
REFERENCES = re.compile(r'\bREFERENCES\s+["`\[]?([\w.]+)', re.I)
FOREIGN_KEY = re.compile(r'\bForeignKey\s*\(\s*["\']([\w.]+)', re.I)
DJANGO_RELATION = re.compile(r'models\.(?:ForeignKey|OneToOneField|ManyToManyField)\s*\(\s*(?:["\']([\w.]+)["\']|([\w.]+))')
DJANGO_FIELD = re.compile(r'^\s*(\w+)\s*=\s*models\.(?:\w*Field|ForeignKey|OneToOneField|ManyToManyField)\s*\(')
SQLA_FIELD = re.compile(r'^\s*(\w+)\s*=\s*(?:Column|mapped_column)\s*\(')
SQL_FIELD = re.compile(r'^\s*["`\[]?(\w+)["`\]]?\s+[A-Za-z][\w()]*')
PRISMA_FIELD = re.compile(r'^\s*(\w+)\s+([\w?\[\]]+)\s*(?:@|$)')
MAX_ENTITIES = 16


def build(index, scan, paths=None):
    """Return an ER graph only for declarations actually present in this source scope."""
    paths = paths if paths is not None else index.code_paths(scan['id'])
    entities = []
    for path in paths:
        current = None
        kind = ''
        indent = 0
        for number, text in index.file_lines(scan['id'], path):
            found = CREATE.search(text)
            model = MODEL.match(text)
            orm = ORM.match(text)
            if found or model or (orm and any(x in orm.group(3) for x in ('Base', 'Model', 'SQLModel'))):
                kind = 'sql' if found else 'prisma' if model else 'orm'
                name = (found or model).group(1) if found or model else orm.group(2)
                current = {'name': name, 'path': path, 'line': number, 'fields': [], 'relations': []}
                entities.append(current)
                indent = len(orm.group(1)) if orm else 0
            elif current and (kind == 'prisma' and text.strip().startswith('}')
                              or kind == 'sql' and text.strip().startswith(');')
                              or kind == 'orm' and text.strip() and not text.lstrip().startswith('#')
                              and len(text) - len(text.lstrip()) <= indent):
                current = None
                continue
            if not current:
                continue
            if kind == 'orm':
                table = TABLE_NAME.search(text)
                if table:
                    current['name'] = table.group(1)
                field = DJANGO_FIELD.match(text) or SQLA_FIELD.match(text)
                relation = FOREIGN_KEY.search(text)
                django = DJANGO_RELATION.search(text)
                target = (relation.group(1).split('.')[0] if relation else
                          (django.group(1) or django.group(2)).split('.')[-1] if django else '')
            elif kind == 'prisma':
                field = PRISMA_FIELD.match(text)
                target = field.group(2).strip('?[]') if field and '@relation' in text else ''
            else:
                field = SQL_FIELD.match(text)
                if field and field.group(1).upper() in {'CREATE', 'FOREIGN', 'PRIMARY', 'UNIQUE', 'CONSTRAINT', 'CHECK'}:
                    field = None
                relation = REFERENCES.search(text)
                target = relation.group(1).split('.')[0] if relation else ''
            field_name = field.group(1) if field else ''
            if field_name and len(current['fields']) < 12 and field_name not in current['fields']:
                current['fields'].append(field_name)
            if target:
                current['relations'].append({'target': target, 'field': field_name, 'line': number})
            if kind == 'sql' and ');' in text:
                current = None

    # Names can repeat in migration files. Keep the first declaration and never join two
    # different systems: the caller supplies only paths for the selected system.
    unique = {}
    for entity in entities:
        unique.setdefault(entity['name'].lower(), entity)
    if not unique:
        return {}
    relations = []
    for entity in unique.values():
        for relation in entity['relations']:
            target = relation['target'].lower()
            if target in unique and target != entity['name'].lower():
                relations.append((entity['name'].lower(), target, relation))
    degree = {name: 0 for name in unique}
    for left, right, _ in relations:
        degree[left] += 1
        degree[right] += 1
    names = sorted(unique, key=lambda name: (-degree[name], name))[:MAX_ENTITIES]
    kept = set(names)
    related = [(left, right, relation) for left, right, relation in relations if left in kept and right in kept]
    columns = {name: 0 for name in names}
    if related:
        for _ in range(2):
            for left, right, _ in related:
                columns[right] = max(columns[right], min(2, columns[left] + 1))
    else:
        columns = {name: n % 3 for n, name in enumerate(names)}
    rows = {}
    nodes = []
    for name in sorted(names, key=lambda name: (columns[name], name)):
        entity = unique[name]
        column = columns[name]
        row = rows.get(column, 0)
        rows[column] = row + 1
        line = entity['line']
        nodes.append({'id': 'er:' + name, 'label': entity['name'],
                      'sublabel': ', '.join(entity['fields'][:3]), 'fields': entity['fields'],
                      'path': entity['path'], 'line': line,
                      'url': '' if scan.get('demo') else source_url(scan['repo'], scan['commit'], entity['path'], line),
                      'kind': 'entity', 'column': column, 'row': row})
    edges = [{'from': 'er:' + left, 'to': 'er:' + right, 'line': relation['line'], 'count': 1,
              'back': columns[right] <= columns[left],
              'reason': (relation['field'] + ' references ' if relation['field'] else 'References ') + unique[right]['name']}
             for left, right, relation in related]
    return {'key': 'er', 'kind': 'graph', 'title': 'How saved information connects',
            'plain': 'Each box is a table or database model declared in the imported files. '
                     'An arrow appears only when a field explicitly names another entity.',
            'nodes': nodes, 'edges': edges, 'circular': sum(edge['back'] for edge in edges),
            'note': (f'Showing {len(nodes)} of {len(unique)} entities. ' if len(unique) > len(nodes) else '')
                    + ('No explicit relationship was found among these entities. ' if not edges else '')
                    + 'This is a map of code declarations, not a live database inspection.'}
