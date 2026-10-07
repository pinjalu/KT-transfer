"""Stage 2: a beginner-friendly project overview built from retrieved evidence.

Each topic is retrieved separately and explained separately, so a weak section stays weak
instead of borrowing confidence from a strong one. Every section carries its own sources and
its own statement of what is missing. Nothing here claims the whole project was examined; the
overview is built from the same bounded excerpts the question flow uses.

The reading list is derived from the indexed file paths rather than written by the model,
because "which files exist" is a fact of the scan and does not need to be inferred.
"""
from pathlib import PurePosixPath

TOPICS = [
    {
        'key': 'purpose',
        'title': 'What this project is for',
        'query': 'readme introduction overview purpose project description what this does application',
        'ask': ('Explain clearly what this project is for, its main goal, and its core features for a new developer. '
                'Use only the supplied excerpts. Explain in plain, direct English with clear short sentences. '
                'If the evidence does not state the business purpose, explain what the code itself does and note what is missing in missing_information.'),
    },
    {
        'key': 'technologies',
        'title': 'What it is built with',
        'query': 'requirements dependencies install package import framework library module version config',
        'ask': ('List and explain the main technologies, frameworks, libraries, and core packages used in this project. '
                'For a new developer, explain clearly what each key component or dependency does. '
                'Use simple English and short sentences.'),
    },
    {
        'key': 'setup',
        'title': 'How to set it up and start it',
        'query': 'install setup getting started run start command usage pip npm docker environment variables',
        'ask': ('Describe the setup, installation, and startup steps documented in this project. '
                'Present them as a clear step-by-step guide for a new developer joining the project. '
                'If any setup step or environment setting is missing from the excerpts, state that in missing_information.'),
    },
    {
        'key': 'flows',
        'title': 'What happens when it runs',
        'query': 'main entry point route handler request response workflow process service controller api endpoint',
        'ask': ('Explain the main execution flows and data processing paths in this project. '
                'Describe the starting entry point, what happens step-by-step when a request or command runs, and what output is returned, in clear simple English.'),
    },
    {
        'key': 'data',
        'title': 'Where it keeps information and settings',
        'query': 'database schema table model migration config settings env store file save query',
        'ask': ('Explain where and how this project stores its data, models, schemas, and configurations. '
                'List database tables, data stores, or key configuration files shown in the excerpts in simple English.'),
    },
]

ENTRY_NAMES = ('main', '__main__', 'app', 'server', 'index', 'cli', 'run', 'manage', 'wsgi', 'asgi')
CONFIG_NAMES = ('requirements.txt', 'pyproject.toml', 'package.json', 'setup.py', 'setup.cfg',
                'dockerfile', 'makefile', 'go.mod', 'cargo.toml', 'pom.xml', 'build.gradle')


def reading_order(paths, limit: int = 12) -> list[dict]:
    """Suggest a reading order from the indexed paths. Derived from the scan, not from the model."""
    picked, seen = [], set()

    def take(path, why):
        if path in seen or len(picked) >= limit:
            return
        seen.add(path)
        picked.append({'path': path, 'why': why})

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


def section_from(topic: dict, sources: list[dict], answer: dict | None, error: str = '') -> dict:
    """Package one section, keeping its own sources and its own gaps attached to it."""
    return {
        'key': topic['key'],
        'title': topic['title'],
        'statements': (answer or {}).get('statements', []),
        'missing_information': (answer or {}).get('missing_information', ''),
        'error': error,
        'sources': [{'source_id': s['source_id'], 'path': s['path'], 'start': s['start'],
                     'end': s['end'], 'url': s.get('url'), 'text': s['text'], 'split': s.get('split')}
                    for s in sources],
    }
