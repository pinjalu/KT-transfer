"""Stage 2: a beginner-friendly project overview built from retrieved evidence.

Each topic is retrieved separately and explained separately, so a weak section stays weak
instead of borrowing confidence from a strong one. Every section carries its own sources and
its own statement of what is missing. Nothing here claims the whole project was examined; the
overview is built from the same bounded excerpts the question flow uses.

Two kinds of content sit side by side. Groups in facts.py are read out of the files and are
correct by construction: the dependency list is the dependency file, the route list is the
route declarations. The topics below are prose, which only a model can write, and prose is
where a small model goes wrong, so what it returns is checked here before anyone reads it:
near-repeats are dropped, a citation of everything at once is narrowed to the excerpts that
actually carry the words, and each statement records how much of itself can be found in the
excerpt it points at.

The reading list is derived from the indexed file paths rather than written by the model,
because "which files exist" is a fact of the scan and does not need to be inferred.
"""
import re
from pathlib import PurePosixPath

from pka.config import source_url
from pka.index import is_source_path
from pka.statement_evidence import describe as describe_evidence

TOPICS = [
    {
        'key': 'purpose',
        'title': 'What this project is for',
        'queries': [
            'readme introduction overview purpose project description what this does',
            'application product users feature goal problem solves',
            'title heading about summary intro',
        ],
        'test_cap': 0,
        'ask': 'Say what this project is for, what problem it solves and who uses it. Open with one plain sentence a non-developer would follow. Then say what it actually does, naming the real parts. If the excerpts never state the business purpose, say that in missing_information and describe what the code does instead of guessing at why.',
    },
    {
        'key': 'technologies',
        'title': 'What it is built with',
        'queries': [
            'requirements dependencies install package version',
            'import framework library module from',
            'language runtime build tool compiler bundler',
        ],
        'test_cap': 0,
        'ask': 'Explain what the important technologies here are used FOR in this project. The reader already has the exact dependency list with versions, so never just recite names and numbers. For each important technology, explain its role, which part uses it and how it fits with the other components. Include a simple example of a supported use where helpful.',
    },
    {
        'key': 'architecture',
        'title': 'How the code is organised',
        'queries': [
            'module package folder structure layer component organisation',
            'class function responsibility interface service helper utility',
            'import from internal dependency between files',
        ],
        'test_cap': 0,
        'ask': 'Explain how this project is split up and what each part is responsible for. Name the real files and folders. For each, say what a developer would go there to change. Say which part calls which only where an excerpt shows it.',
    },
    {
        'key': 'setup',
        'title': 'How to set it up and start it',
        'queries': [
            'install dependencies requirements pip npm packages virtual environment',
            'run start server command launch script usage',
            'environment variable configuration token credential example file',
            'readme prerequisites version required before you begin',
        ],
        'test_cap': 0,
        'ask': 'Give the setup and start-up steps as a numbered walk a person can follow after cloning this repository. Commands exactly as the excerpts show them, in the order they are run. Never invent a step, a port or a path. Anything the excerpts leave out goes in missing_information, because a reader will try to run what you write.',
    },
    {
        'key': 'flows',
        'title': 'What happens when it runs',
        'queries': [
            'main entry point startup initialise bootstrap lifespan',
            'request response handler route controller middleware',
            'workflow process pipeline step job queue task loop',
        ],
        'test_cap': 0,
        'ask': 'Walk through what happens from the moment this project starts. The entry point, then step by step what happens when a request or a command arrives, then what goes back out. Finish with one concrete example: somebody does a particular thing, these files run in this order, this is what they get.',
    },
    {
        'key': 'interfaces',
        'title': 'What it exposes to the outside',
        'queries': [
            'route endpoint api get post put delete path url',
            'websocket socket event message channel subscribe',
            'command line argument parser option flag input output',
        ],
        'test_cap': 1,
        'ask': 'Explain what this project offers to anything outside it: its addresses, its command line options, its events. For each important one say what action causes it, what has to be sent, what comes back, and what changes as a result.',
    },
    {
        'key': 'data',
        'title': 'Where it keeps information and settings',
        'queries': [
            'database table schema migration query insert select',
            'model record field column entity document',
            'config settings environment file store save read write path',
        ],
        'test_cap': 0,
        'ask': 'Explain what this project stores and what each stored thing means in the real world, not just its type. For each table or model, say what one row of it represents and when a new one appears. Then say where settings live, separately from stored data.',
    },
    {
        'key': 'testing',
        'title': 'How it is checked',
        'queries': [
            'test assert expect fixture mock pytest jest spec',
            'continuous integration workflow pipeline lint check coverage',
        ],
        'test_cap': 5,
        'ask': 'Explain how this project checks itself and what each group of tests is protecting against. Name the test files. Say how they are run. If the excerpts show no tests, say exactly that and stop.',
    },
    {
        'key': 'decisions',
        'title': 'What the team recorded about it',
        'queries': [
            'decision agreed decided proposal discussion thread message',
            'issue ticket story requirement acceptance criteria status assignee',
            'bug defect blocker priority comment update',
        ],
        'test_cap': 0,
        'needs': ('slack/', 'jira/'),
        'ask': 'Explain what the tickets and conversations say about this project: what is being worked on, what was decided and what is still open. Keep a proposal and an agreed decision apart, and name who said something only where an excerpt records it. Say where a recorded decision no longer matches what the code does, if an excerpt shows that.',
    },
]

# A handover is an order, not a pile. An experienced developer walking somebody through a
# project does not open with the dependency list; they say what it is, draw the shape of it,
# get it running, then follow one request through. Each step below is one sitting, and it names
# which written sections, which groups of facts and which diagram belong to it. A step with
# nothing behind it on this particular project is dropped rather than shown empty.
STEPS = [
    {
        'key': 'orientation',
        'title': 'What this project is',
        'kt': 'Start here. This is what a colleague would tell you before opening any file.',
        'topics': ['purpose'],
        'facts': ['shape', 'documents'],
        'diagrams': [],
    },
    {
        'key': 'shape',
        'title': 'The shape of it',
        'kt': 'Look at the picture before the prose. Every file that was read is in one of '
              'these layers, and a request travels down them in order.',
        'topics': ['architecture'],
        'facts': [],
        'diagrams': ['stack'],
    },
    {
        'key': 'wiring',
        'title': 'What uses what',
        'kt': 'Now the connections between those files, and what each of the important ones is '
              'for. This is the map you come back to when you are asked to change something '
              'and need to know what else it touches.',
        'topics': [],
        'facts': [],
        'diagrams': ['modules'],
        'roles': True,
    },
    {
        'key': 'running',
        'title': 'Get it running',
        'kt': 'Do this before reading any further. Nothing about a project makes sense until '
              'you have watched it start.',
        'topics': ['setup', 'technologies'],
        'facts': ['commands', 'dependencies', 'environment'],
        'diagrams': [],
    },
    {
        'key': 'request',
        'title': 'Follow one request through',
        'kt': 'The most useful half hour you can spend on a new project. One request, from '
              'arriving to being answered, through the real files.',
        'topics': ['flows', 'interfaces'],
        'facts': ['routes', 'services'],
        'diagrams': ['journey'],
    },
    {
        'key': 'information',
        'title': 'Where information is kept',
        'kt': 'What survives a restart, and which file writes it.',
        'topics': ['data'],
        'facts': ['stores'],
        'diagrams': [],
    },
    {
        'key': 'checks',
        'title': 'How to know you have not broken it, and how it ships',
        'kt': 'What the project checks about itself, how to run those checks, and what it says '
              'about being built and deployed.',
        'topics': ['testing'],
        'facts': ['delivery'],
        'diagrams': [],
    },
    {
        'key': 'team',
        'title': 'What the team has said about it',
        'kt': 'The tickets and conversations that were read in. Decisions and open questions '
              'that the code itself does not record.',
        'topics': ['decisions'],
        'facts': [],
        'diagrams': [],
    },
    {
        'key': 'reading',
        'title': 'Read these, in this order',
        'kt': 'You have the shape of it now. This is the order to read the files in.',
        'topics': [],
        'facts': ['gaps'],
        'diagrams': [],
        'reading_order': True,
    },
]


def walkthrough(planned_keys, written_keys, fact_keys, diagram_keys,
                has_roles: bool = False) -> list[dict]:
    """The steps this scan will have, in handover order, whether or not they are written yet.

    The list is settled against the topics the build intends to attempt, not against the ones
    finished so far, so step five is step five from the first second of the build. The earlier
    version grew the list as sections arrived, which renumbered every step after the new one
    and moved a reader onto a different step while they were reading it.

    A step the build will never be able to fill is still dropped. A step that is merely waiting
    for its prose is kept and marked, because a reader is better served by a greyed out step
    seven that says what is coming than by step seven appearing from nowhere later.

    Only keys are carried, not content. The sections, the groups of facts and the diagrams are
    each stored once in the payload and a step points at them, so a change to a section cannot
    leave a stale copy of it inside a step.
    """
    planned, written = set(planned_keys), set(written_keys)
    groups, drawings = set(fact_keys), set(diagram_keys)
    built = []
    for step in STEPS:
        intended = [k for k in step['topics'] if k in planned]
        topics = [k for k in intended if k in written]
        waiting = [k for k in intended if k not in written]
        facts = [k for k in step['facts'] if k in groups]
        diagrams = [k for k in step['diagrams'] if k in drawings]
        roles = bool(step.get('roles') and has_roles)
        if not (intended or facts or diagrams or roles or step.get('reading_order')):
            continue
        built.append({'key': step['key'], 'title': step['title'], 'kt': step['kt'],
                      'topics': topics, 'waiting_for': waiting, 'facts': facts,
                      'diagrams': diagrams, 'roles': roles,
                      'reading_order': bool(step.get('reading_order')),
                      'ready': bool(topics or facts or diagrams or roles
                                    or step.get('reading_order'))})
    for position, step in enumerate(built):
        step['number'] = position
        step['of'] = len(built)
    return built


ENTRY_NAMES = ('main', '__main__', 'app', 'server', 'index', 'cli', 'run', 'manage', 'wsgi', 'asgi')
CONFIG_NAMES = ('requirements.txt', 'pyproject.toml', 'package.json', 'setup.py', 'setup.cfg',
                'dockerfile', 'makefile', 'go.mod', 'cargo.toml', 'pom.xml', 'build.gradle')

# Words that appear in any sentence about any codebase. Counting them towards whether a
# statement is supported by its excerpt would make every statement look supported.
FILLER = set('''that this with from into have has had will would could should been being does
doing used uses using also than then them they their there these those which while when what
where because about after before each other some more most such only just able need needs
project code file files function functions method class classes value values data user users
developer developers thing things part parts work works line lines name names type types
provide provides include includes contain contains allow allows handle handles make makes
based between across through within without over under here same both very much many well
without run runs runnable new first main important specific several various different'''.split())

DUPLICATE_AT = 0.68
SUPPORTED_AT = 0.55
PARTLY_AT = 0.28

# A name belonging to this project and to no other: a file, a route, a table, a dependency, a
# setting, a function. A sentence carrying at least one of these is about this project. A
# sentence carrying none of them is the kind of statement that would be equally true of any
# codebase, which is exactly what a new developer cannot use.
NAME_IN_TEXT = re.compile(r'[A-Za-z_][A-Za-z0-9_.\-]*\.[A-Za-z]{1,5}\b'   # a file name
                          r'|/[A-Za-z0-9_{}:\-/]+'                          # a route
                          r'|\b[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b'      # snake_case
                          r'|\b[a-z]+[A-Z][A-Za-z0-9]*\b'                   # camelCase
                          r'|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b'           # PascalCase
                          # An underscore is required. Bare capitals are ordinary English in
                          # this domain, and API, HTTP, JSON and SQL were being read as names
                          # belonging to the project, which is the opposite of what this is for.
                          r'|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b')              # SHOUTING_CASE


# A sentence telling a reader to install from requirements.txt, in a project that has no such
# file, is wrong in a way the support check cannot see: the words do appear in the excerpt it
# cites, because the excerpt talks about installing. Only the scan knows which files exist.
FILE_IN_TEXT = re.compile(r'\b[A-Za-z_][A-Za-z0-9_.\-]*\.'
                          r'(?:py|js|jsx|ts|tsx|mjs|cjs|vue|svelte|go|rb|rs|java|kt|php|cs'
                          r'|toml|txt|md|rst|json|ya?ml|cfg|ini|lock|env|sh|ps1|bat|sql|html|css)\b',
                          re.I)


def file_names(paths) -> set:
    """Every name a file in this scan can be referred to by."""
    known = set()
    for path in paths:
        known.add(path.lower())
        known.add(PurePosixPath(path).name.lower())
    return known


def unknown_files(text: str, known: set) -> list:
    """File names a sentence uses that were never read in this scan.

    Reported as not read rather than not existing, because a file the scan skipped is also
    absent from `known` and saying it does not exist would be a claim this cannot make.
    """
    if not known:
        return []
    return sorted({found for found in FILE_IN_TEXT.findall(text)
                   if found.lower() not in known})


def project_names(sources, facts=()) -> set:
    """The words that belong to this project rather than to software in general.

    Built from the paths of the excerpts in hand and from the groups of facts, which already
    hold every dependency, route, table and setting by name. These are what a sentence has to
    touch to be about this project.
    """
    found = set()
    for source in sources:
        for piece in re.split(r'[/\.]', source.get('path', '')):
            if len(piece) > 2:
                found.add(piece.lower())
        found.add(PurePosixPath(source.get('path', '')).name.lower())
    for group in facts or ():
        for item in group.get('items', ()):
            text = item.get('text', '')
            found.add(text.lower())
            for piece in re.split(r'[\s/.:\-]', text):
                if len(piece) > 2:
                    found.add(piece.lower())
    return {f for f in found if f}


def _names_this_project(text: str, known: set) -> bool:
    """Whether this sentence actually points at something in this project.

    Two ways to qualify. Naming something the scan knows about is the strong one. Carrying a
    word shaped like code, meaning a path, a route or an identifier, is the weaker one, and it
    is allowed because a statement can correctly name a function that no group of facts
    happens to list.
    """
    lowered = text.lower()
    if any(name in lowered for name in known if len(name) > 3):
        return True
    return bool(NAME_IN_TEXT.search(text))


def reading_order(paths, limit: int = 12, repo: str = '', commit: str = '') -> list[dict]:
    """Suggest a reading order from the indexed paths. Derived from the scan, not from the model.

    Each entry carries the address of the file at the scanned commit, so the list is a set of
    links a reader can follow rather than a set of names to go hunting for.

    Only repository files. Slack messages and Jira issues sit in the same index under their own
    prefix, and once a real project's issues had been read the list offered `jira/SCRUM-17` as
    "one of the project files that was read", with a link to that path inside the repository,
    where no such file has ever existed.
    """
    paths = [p for p in paths if not is_source_path(p)]
    picked, seen = [], set()

    def take(path, why):
        if path in seen or len(picked) >= limit:
            return
        seen.add(path)
        picked.append({'path': path, 'why': why, 'url': source_url(repo, commit, path)})

    for p in paths:
        if PurePosixPath(p).name.lower().startswith('readme'):
            take(p, 'The project introduces itself here. Usually the quickest way in.')
    for p in paths:
        if PurePosixPath(p).name.lower() in CONFIG_NAMES:
            take(p, 'Lists the other software this project needs in order to work.')
    for p in paths:
        if PurePosixPath(p).stem.lower() in ENTRY_NAMES:
            take(p, 'Named like a starting point, so the program probably begins here.')
    for p in paths:
        if PurePosixPath(p).parts[0].lower() in ('docs', 'doc', 'documentation'):
            take(p, 'Written notes and guides for this project.')
    for p in sorted(paths, key=lambda x: (len(PurePosixPath(x).parts), x)):
        take(p, 'One of the project files that was read.')
    return picked


def topics_for(prefixes: set) -> list[dict]:
    """The topics worth spending a model call on for this scan.

    A topic that declares what it needs is skipped when the scan holds none of it. Asking a
    model about recorded decisions when no Slack or Jira content was ever read costs a minute
    and produces a paragraph about nothing.
    """
    return [t for t in TOPICS if not t.get('needs') or any(p in prefixes for p in t['needs'])]


def _meaningful(text: str) -> set:
    """The words in a piece of text that are worth matching on, reduced to short stems.

    Three things were getting in the way of comparing a statement with its excerpt. A number
    was thrown away, so "binds to port 8000" could not be matched against bind(8000), which is
    exactly the kind of detail worth checking. start_server and server looked like different
    words. And binds, starts and started all looked different from bind and start. Splitting
    on case and underscores and then cutting each word to four characters fixes all three. It
    is blunt, and it is meant to be: this measures whether a sentence is anywhere near its
    excerpt, not whether it is written correctly.
    """
    spaced = re.sub(r'([a-z0-9])([A-Z])', r' ', text)
    found = {w for w in re.findall(r'[A-Za-z0-9]+', spaced.lower())
             if w not in FILLER and (len(w) > 2 or w.isdigit())}
    return {w[:4] if len(w) > 4 else w for w in found}


def _overlap(left: set, right: set) -> float:
    if not left:
        return 0.0
    return len(left & right) / len(left)


def _repeats(words: set, earlier: list[set]) -> bool:
    """Whether this statement says what an earlier one already said.

    Judged both ways round, because a short restatement of a long statement shares nearly all
    of its own words while sharing only some of the longer one's.
    """
    for seen in earlier:
        if not seen:
            continue
        if min(_overlap(words, seen), _overlap(seen, words)) >= DUPLICATE_AT:
            return True
    return False


def tidy(statements: list[dict], sources: list[dict],
         measure: bool = True, facts=(), paths=(), *, verified_code=False) -> tuple[list[dict], dict]:
    """Check and clean up what the model returned, before anybody reads it.

    Three things go wrong with a small model asked for between one and eight statements, and
    all three were visible in real runs on this project. It restates a point in different words
    to fill the list, which wastes a reader's time. It cites every excerpt it was given on
    every statement, which makes a citation worthless as a pointer. And it occasionally writes
    a sentence whose content is not in any excerpt it names.

    Repeats are dropped. A citation of everything is narrowed to the excerpts whose text
    actually carries the statement's words. The third cannot be fixed from here, so it is
    measured instead and reported, and the reader is told which statements to check first.
    """
    supplied = {s['source_id']: _meaningful(s['text'] + ' ' + s['path']) for s in sources}
    known = project_names(sources, facts)
    scanned = file_names(paths) if measure else set()
    kept, earlier, dropped, narrowed, generic, invented = [], [], 0, 0, 0, 0
    for statement in statements:
        words = _meaningful(statement['text'])
        if _repeats(words, earlier):
            dropped += 1
            continue
        earlier.append(words)
        cited = [x for x in statement['source_ids'] if x in supplied]
        # Citing every excerpt at once says nothing about where a claim came from. Rank them by
        # how much of the statement each one actually contains and keep the ones that carry it.
        if len(cited) >= 4 and len(cited) >= len(supplied):
            ranked = sorted(cited, key=lambda sid: -_overlap(words, supplied[sid]))
            cited, narrowed = ranked[:3], narrowed + 1
        covered = set()
        for sid in cited:
            covered |= supplied.get(sid, set())
        share = _overlap(words, covered)
        # Example mode's text is a notice about example mode, not a claim about any code, so
        # measuring it against an excerpt would flag a fixed string as if a model had drifted.
        level = ('not measured' if not measure
                 else 'supported' if share >= SUPPORTED_AT
                 else 'partly supported' if share >= PARTLY_AT else 'check this')
        # "An API is an endpoint used to talk to the backend" is true of every project ever
        # written and therefore useless here. A statement that names nothing belonging to this
        # project is marked so, and the reader can see at a glance which sentences were worth
        # their time.
        about_this = not measure or _names_this_project(statement['text'], known)
        generic += 0 if about_this else 1
        missing = unknown_files(statement['text'], scanned)
        invented += 1 if missing else 0
        kept.append({
            'text': statement['text'],
            'source_ids': cited or statement['source_ids'],
            'support': level,
            'support_share': round(share, 2) if measure else None,
            'about_this_project': about_this,
            'files_not_read': missing,
        })
        kept[-1]['evidence'] = describe_evidence(kept[-1], sources, example=not measure,
                                                verified_code=verified_code)
    return kept, {'dropped_repeats': dropped, 'narrowed_citations': narrowed,
                  'unsupported': sum(1 for k in kept if k['support'] == 'check this'),
                  'generic': generic, 'names_unread_files': invented}


def section_from(topic: dict, sources: list[dict], answer: dict | None, error: str = '',
                 measure: bool = True, facts=(), paths=()) -> dict:
    """Package one section, keeping its own sources and its own gaps attached to it."""
    statements, checks = tidy((answer or {}).get('statements', []), sources, measure, facts, paths)
    return {
        'key': topic['key'],
        'title': topic['title'],
        'statements': statements,
        'checks': checks,
        'missing_information': (answer or {}).get('missing_information', ''),
        'error': error,
        'sources': [{'source_id': s['source_id'], 'path': s['path'], 'start': s['start'],
                     'end': s['end'], 'url': s.get('url'), 'text': s['text'], 'split': s.get('split')}
                    for s in sources],
    }
