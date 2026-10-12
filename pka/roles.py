"""What each important file is for, and what it is wired to.

The question a new developer asks over and over in their first week is "what is this file and
who calls it". That question has an exact answer sitting in the code: the importers of a file
are the files that import it, and what it calls is what it imports. Neither needs a model and
neither should be guessed at, because a wrong answer sends somebody editing the wrong file.

The one-line purpose is taken from what the file says about itself, which is its module
docstring, its leading comment or its first heading. Where a file says nothing about itself,
nothing is claimed; a file with no docstring gets a blank purpose rather than an invented one.

The ranking is by how connected a file is, because the files worth describing first are the
ones the rest of the project leans on.
"""
import re
from pathlib import PurePosixPath

from pka.config import source_url
from pka.diagram import TEST_PATH, _lookup, imports_in

DOCSTRING = re.compile(r'^\s*(?:[rubf]{0,2})("""|\'\'\')(.*)$')
LINE_COMMENT = re.compile(r'^\s*(?://+|#+|\*|/\*+)\s?(.*)$')
HEADING = re.compile(r'^\s*#{1,6}\s+(.+)$')
SKIP_LINE = re.compile('^﻿?\\s*(?:#!|#\\s*-\\*-|#\\s*coding[:=]|//\\s*@ts-|/\\* eslint|'
                       'from __future__ import|\'use strict\'|"use strict")')
MAX_FILES = 14
MAX_LISTED = 6
PURPOSE_CHARS = 240


def _purpose(path: str, lines) -> tuple[str, int]:
    """The file's own one-line description of itself, and the line it is written on.

    Only the first few lines are looked at. A sentence found halfway down a file is a comment
    about one function, not a statement of what the file is for, and treating it as the latter
    produces confident nonsense.
    """
    head = [(n, text) for n, text in lines if n <= 12]
    if not head:
        return '', 0
    name = PurePosixPath(path).name.lower()
    if name.endswith(('.md', '.rst', '.txt')):
        for number, text in head:
            found = HEADING.match(text)
            if found:
                return found.group(1).strip()[:PURPOSE_CHARS], number
            if text.strip():
                return text.strip()[:PURPOSE_CHARS], number
        return '', 0
    collected, started_at = [], 0
    for number, text in head:
        if not collected:
            opened = DOCSTRING.match(text)
            if opened:
                started_at = number
                rest = opened.group(2)
                closed = rest.find(opened.group(1))
                if closed >= 0:
                    return rest[:closed].strip()[:PURPOSE_CHARS], number
                if rest.strip():
                    collected.append(rest.strip())
                continue
            # A shebang and an encoding line are instructions to the interpreter, not a
            # description, and skipping past them is not the same as giving up on the file.
            if SKIP_LINE.match(text) or not text.strip():
                continue
            comment = LINE_COMMENT.match(text)
            if comment and comment.group(1).strip():
                return comment.group(1).strip()[:PURPOSE_CHARS], number
            # Real code before any description means the file does not describe itself.
            return '', 0
        else:
            if '"""' in text or "'''" in text:
                break
            if not text.strip():
                break
            collected.append(text.strip())
    return (' '.join(collected)[:PURPOSE_CHARS], started_at) if collected else ('', 0)


def _what_it_holds(path: str, lines, routes, stores) -> list[str]:
    """The named things this file declares, in the reader's words rather than the language's."""
    held = []
    mine = [r for r in routes if r['path'] == path]
    if mine:
        held.append('answers ' + ', '.join(r['text'] for r in mine[:4])
                    + (f' and {len(mine) - 4} more' if len(mine) > 4 else ''))
    kept = [s for s in stores if s['path'] == path]
    if kept:
        held.append('declares ' + ', '.join(s['text'] for s in kept[:4])
                    + (f' and {len(kept) - 4} more' if len(kept) > 4 else ''))
    return held


def describe(index, scan: dict, facts: list) -> dict:
    """One card per important file: what it is for, who uses it, what it uses.

    Returns the group in the same shape as every other group of facts, so the browser needs no
    special case for it, with the cards carried separately because each one has more structure
    than a single line of text.
    """
    paths = index.code_paths(scan['id'])
    files = {p: index.file_lines(scan['id'], p) for p in paths}
    groups = {g['key']: g for g in facts}
    routes = groups.get('routes', {}).get('items', [])
    stores = groups.get('stores', {}).get('items', [])

    def link(path, line=1):
        if scan.get('demo'):
            return ''
        return source_url(scan.get('repo', ''), scan.get('commit', ''), path, line)

    table = _lookup(files)
    calls, used_by = {}, {}
    for path, lines in files.items():
        for target, number in imports_in(path, lines, table):
            calls.setdefault(path, []).append({'path': target, 'line': number})
            used_by.setdefault(target, []).append({'path': path, 'line': number})

    route_paths = {r['path'] for r in routes}
    store_paths = {s['path'] for s in stores}
    tested = set()
    for path in paths:
        if not TEST_PATH.search(path):
            continue
        for target in calls.get(path, []):
            tested.add(target['path'])

    def weight(path):
        # Most leaned on first: a file five others import matters more to a newcomer than one
        # nobody imports, and a file that answers a route or owns a table matters either way.
        return (len(used_by.get(path, [])) * 2 + len(calls.get(path, []))
                + (6 if path in route_paths else 0) + (4 if path in store_paths else 0)
                - (8 if TEST_PATH.search(path) else 0))

    ranked = sorted((p for p in paths if weight(p) > 0), key=lambda p: (-weight(p), p))
    cards = []
    for path in ranked[:MAX_FILES]:
        purpose, at = _purpose(path, files[path])
        cards.append({
            'path': path,
            'name': PurePosixPath(path).name,
            'url': link(path, at or 1),
            'purpose': purpose,
            'purpose_line': at,
            'holds': _what_it_holds(path, files[path], routes, stores),
            'used_by': [{'path': u['path'], 'name': PurePosixPath(u['path']).name,
                         'line': u['line'], 'url': link(u['path'], u['line'])}
                        for u in sorted(used_by.get(path, []), key=lambda x: x['path'])[:MAX_LISTED]],
            'calls': [{'path': c['path'], 'name': PurePosixPath(c['path']).name,
                       'line': c['line'], 'url': link(path, c['line'])}
                      for c in sorted(calls.get(path, []), key=lambda x: x['path'])[:MAX_LISTED]],
            'tested': path in tested,
        })
    if not cards:
        return {}
    return {'key': 'roles', 'title': 'What each important file is for',
            'plain': 'The files the rest of the project leans on most, first. Who uses a file '
                     'and what it uses are read from the import lines themselves, so they are '
                     'exact. The one-line description is whatever the file says about itself.',
            'cards': cards, 'items': [], 'truncated': max(0, len(ranked) - MAX_FILES),
            'note': 'A file that says nothing about itself is left without a description rather '
                    'than given an invented one.'}
