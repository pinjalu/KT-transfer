"""Facts read straight out of the scanned files, with no model involved.

The overview used to ask a 1.7B model to tell a reader what the project is built with, which
files start it and where its settings live. Those are not opinions, they are written down in
requirements.txt, in the route decorators and in the calls to getenv, so reading them is both
cheaper and correct. The model is left to do the part only it can do, which is explaining in
prose what the code is for.

Everything produced here carries the path and the line it came from, so every line in the
overview can be opened at the exact lines on GitHub. A pattern that finds nothing reports
nothing; no group is ever filled with a guess to look complete.
"""
import re
from pathlib import PurePosixPath

from pka.config import source_url
from pka.index import is_source_path

LANGUAGES = {
    '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript (React)', '.mjs': 'JavaScript',
    '.cjs': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript (React)', '.java': 'Java',
    '.go': 'Go', '.rb': 'Ruby', '.php': 'PHP', '.cs': 'C#', '.rs': 'Rust', '.kt': 'Kotlin',
    '.swift': 'Swift', '.c': 'C', '.h': 'C or C++ header', '.cpp': 'C++', '.cc': 'C++',
    '.scala': 'Scala', '.sh': 'Shell script', '.bat': 'Windows batch file', '.ps1': 'PowerShell',
    '.sql': 'SQL', '.html': 'HTML page', '.css': 'Stylesheet', '.scss': 'Stylesheet',
    '.md': 'Documentation (Markdown)', '.rst': 'Documentation', '.txt': 'Plain text',
    '.json': 'Settings or data (JSON)', '.yml': 'Settings (YAML)', '.yaml': 'Settings (YAML)',
    '.toml': 'Settings (TOML)', '.ini': 'Settings (INI)', '.cfg': 'Settings', '.env': 'Settings',
    '.vue': 'Vue component', '.svelte': 'Svelte component', '.dart': 'Dart', '.ex': 'Elixir',
}

DOC_NAMES = ('readme', 'contributing', 'changelog', 'license', 'licence', 'authors', 'security',
             'code_of_conduct', 'architecture', 'install', 'setup', 'usage', 'faq', 'notice',
             'start_here', 'start-here', 'getting_started', 'getting-started', 'roadmap', 'status')
DOC_SUFFIXES = ('.md', '.rst', '.adoc', '.txt')
DOC_DIRS = ('docs', 'doc', 'documentation', 'wiki')

DEPENDENCY_FILES = {
    'requirements.txt': 'Python', 'requirements-dev.txt': 'Python, development only',
    'requirements_dev.txt': 'Python, development only',
    'dev-requirements.txt': 'Python, development only',
    'pyproject.toml': 'Python', 'pipfile': 'Python', 'environment.yml': 'Python with conda',
    'package.json': 'JavaScript or TypeScript', 'go.mod': 'Go', 'cargo.toml': 'Rust',
    'gemfile': 'Ruby', 'composer.json': 'PHP', 'pubspec.yaml': 'Dart',
}

TEST_PATH = re.compile(r'(^|/)(tests?|spec|__tests__|testing)/|(^|/)test_[^/]*$|_test\.[A-Za-z]+$'
                       r'|\.(test|spec)\.[A-Za-z]+$', re.I)

# One route per line is the normal shape in every framework below, so the line a pattern
# matches on is the line a reader should be sent to.
ROUTE_DECORATOR = re.compile(
    r'@[\w.]*\.(get|post|put|patch|delete|head|options|websocket|route)\(\s*["\'`]([^"\'`]+)', re.I)
ROUTE_CALL = re.compile(
    r'\b(?:app|router|api|server)\.(get|post|put|patch|delete|head|options|ws|all|use)'
    r'\(\s*["\'`](/[^"\'`]*)', re.I)
ROUTE_TABLE = re.compile(r'\b(?:path|re_path|url)\(\s*["\']([^"\']*)["\']')

ENV_PATTERNS = (
    re.compile(r'os\.getenv\(\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
    re.compile(r'os\.environ\.get\(\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
    re.compile(r'os\.environ\[\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
    re.compile(r'process\.env\.([A-Za-z_][A-Za-z0-9_]{1,60})'),
    re.compile(r'process\.env\[\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
    re.compile(r'import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]{1,60})'),
    re.compile(r'\bgetenv\(\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
    re.compile(r'\bENV\[\s*["\']([A-Za-z_][A-Za-z0-9_]{1,60})["\']'),
)
SETTING_LINE = re.compile(r'^\s*([A-Z][A-Z0-9_]{2,60})\s*=')

STORE_PATTERNS = (
    (re.compile(r'CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\'`\[]?(\w+)', re.I),
     'database table'),
    (re.compile(r'^\s*class\s+(\w+)\s*\(\s*[\w.]*(?:Base|db\.Model|models\.Model|SQLModel)\b'),
     'database model class'),
    (re.compile(r'^\s*class\s+(\w+)\s*\(\s*[\w.]*BaseModel\b'), 'data shape, a pydantic model'),
    (re.compile(r'^\s*model\s+(\w+)\s*\{'), 'database model in Prisma'),
    (re.compile(r'mongoose\.model\(\s*["\'](\w+)'), 'database collection in Mongoose'),
    (re.compile(r'^\s*(?:export\s+)?(?:interface|type)\s+(\w+)\s*[={]'), 'data shape in TypeScript'),
)
ENGINES = {'sqlite': 'SQLite', 'postgres': 'PostgreSQL', 'psycopg': 'PostgreSQL', 'mysql': 'MySQL',
           'mariadb': 'MariaDB', 'mongodb': 'MongoDB', 'mongoose': 'MongoDB', 'redis': 'Redis',
           'elasticsearch': 'Elasticsearch', 'dynamodb': 'DynamoDB', 'firestore': 'Firestore',
           'supabase': 'Supabase', 'sqlalchemy': 'SQLAlchemy, which works with several databases',
           'prisma': 'Prisma, which works with several databases'}

# Outside services a project talks to, recognised by the dependency that talks to them or by
# the import that pulls that dependency in. The point is never "Stripe is integrated"; it is
# which file calls it and what it is called for, so each entry carries both.
SERVICES = {
    'stripe': ('Stripe', 'takes card payments'),
    'razorpay': ('Razorpay', 'takes payments'),
    'paypal': ('PayPal', 'takes payments'),
    'braintree': ('Braintree', 'takes payments'),
    'sendgrid': ('SendGrid', 'sends email'),
    'mailgun': ('Mailgun', 'sends email'),
    'nodemailer': ('An SMTP mail server', 'sends email'),
    'smtplib': ('An SMTP mail server', 'sends email'),
    'twilio': ('Twilio', 'sends text messages or makes calls'),
    'firebase': ('Firebase', 'sign-in, storage or notifications from Google'),
    'auth0': ('Auth0', 'signs users in'),
    'okta': ('Okta', 'signs users in'),
    'clerk': ('Clerk', 'signs users in'),
    'passport': ('Passport', 'signs users in'),
    'jwt': ('JSON Web Tokens', 'proves who a signed-in user is on each request'),
    'jose': ('JSON Web Tokens', 'proves who a signed-in user is on each request'),
    'boto3': ('Amazon Web Services', 'storage, queues or email on AWS'),
    'aws-sdk': ('Amazon Web Services', 'storage, queues or email on AWS'),
    'azure': ('Microsoft Azure', 'cloud services'),
    'google-cloud': ('Google Cloud', 'cloud services'),
    'cloudinary': ('Cloudinary', 'stores and resizes images'),
    'sentry': ('Sentry', 'records errors that happen in production'),
    'datadog': ('Datadog', 'watches the running system'),
    'newrelic': ('New Relic', 'watches the running system'),
    'opentelemetry': ('OpenTelemetry', 'records timings and traces'),
    'prometheus': ('Prometheus', 'records numbers about the running system'),
    'redis': ('Redis', 'keeps frequently used answers in memory so they are not fetched twice'),
    'memcached': ('Memcached', 'keeps frequently used answers in memory'),
    'celery': ('Celery', 'runs slow work in the background'),
    'rabbitmq': ('RabbitMQ', 'passes jobs between parts of the system'),
    'kafka': ('Kafka', 'passes streams of events between systems'),
    'elasticsearch': ('Elasticsearch', 'searches large amounts of text'),
    'algolia': ('Algolia', 'searches large amounts of text'),
    'openai': ('OpenAI', 'calls a language model'),
    'anthropic': ('Anthropic', 'calls a language model'),
    'ollama': ('Ollama', 'calls a language model running on this machine'),
    'slack_sdk': ('Slack', 'reads or posts Slack messages'),
    'atlassian': ('Atlassian', 'reads Jira or Confluence'),
    'github': ('GitHub', 'reads repositories'),
    'pusher': ('Pusher', 'pushes live updates to browsers'),
    'socket.io': ('Socket.IO', 'keeps a live connection open to the browser'),
    'websockets': ('WebSockets', 'keeps a live connection open to the browser'),
    'graphql': ('GraphQL', 'serves a query-shaped API'),
    'docusign': ('DocuSign', 'collects signatures'),
    'shopify': ('Shopify', 'reads shop data'),
    'salesforce': ('Salesforce', 'reads customer records'),
}
# A file that merely names a service in prose is weaker evidence than one that imports it, so
# the two are reported differently and the import always wins.
CALLING_SUFFIXES = ('.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.svelte',
                    '.java', '.go', '.rb', '.php', '.cs', '.rs', '.kt', '.swift')
SERVICE_CALL = re.compile(r'https?://([a-z0-9.\-]+\.[a-z]{2,})/', re.I)
INTERNAL_HOSTS = ('localhost', '127.0.0.1', '0.0.0.0', 'example.com', 'example.org',
                  'schemas.', 'www.w3.org', 'json-schema.org')

# Files that say how the project is built, shipped and watched. These are read as files, which
# is not the same as watching a pipeline run, and the wording everywhere says so.
DELIVERY_FILES = {
    'dockerfile': ('Dockerfile', 'builds a container image of this project'),
    'docker-compose.yml': ('Docker Compose', 'runs this project and its services together locally'),
    'docker-compose.yaml': ('Docker Compose', 'runs this project and its services together locally'),
    'compose.yml': ('Docker Compose', 'runs this project and its services together locally'),
    'procfile': ('Procfile', 'tells a hosting platform which command to run'),
    'vercel.json': ('Vercel', 'settings for hosting on Vercel'),
    'netlify.toml': ('Netlify', 'settings for hosting on Netlify'),
    'fly.toml': ('Fly.io', 'settings for hosting on Fly.io'),
    'railway.json': ('Railway', 'settings for hosting on Railway'),
    'render.yaml': ('Render', 'settings for hosting on Render'),
    'app.yaml': ('Google App Engine', 'settings for hosting on App Engine'),
    'serverless.yml': ('Serverless Framework', 'deploys functions to a cloud provider'),
    'kubernetes.yml': ('Kubernetes', 'describes how this runs in a cluster'),
    'jenkinsfile': ('Jenkins', 'the build and release pipeline'),
    '.gitlab-ci.yml': ('GitLab CI', 'the build and release pipeline'),
    'azure-pipelines.yml': ('Azure Pipelines', 'the build and release pipeline'),
    'cloudbuild.yaml': ('Google Cloud Build', 'the build and release pipeline'),
    'makefile': ('Makefile', 'the commands the project builds and runs itself with'),
}
CI_DIRS = ('.github/workflows', '.circleci', '.gitlab')

MAX_ITEMS = 40


def _item(text, path='', line=0, url='', detail=''):
    return {'text': text, 'path': path, 'line': line, 'url': url, 'detail': detail}


def _group(key, title, plain, items, note=''):
    return {'key': key, 'title': title, 'plain': plain, 'items': items[:MAX_ITEMS],
            'truncated': max(0, len(items) - MAX_ITEMS), 'note': note}


def _requirements(lines, path, link):
    """Pinned names out of a pip requirements file, ignoring comments and pip's own options."""
    found = []
    for number, line in lines:
        text = line.split('#')[0].strip()
        if not text or text.startswith('-'):
            continue
        name = re.split(r'[\s<>=!~;\[]', text, 1)[0].strip()
        if not name:
            continue
        # The pinned version reads better as "version 2.13.5" than as the raw "==2.13.5".
        version = text[len(name):].strip().lstrip('=<>!~ ').strip()
        found.append(_item(name, path, number, link(number),
                           'version ' + version if version else ''))
    return found


def _json_dependencies(lines, path, link):
    """Dependency names from package.json or composer.json.

    The file is walked as text rather than parsed, because the line number is what makes an
    entry openable and json.loads throws it away. A malformed file simply yields nothing.
    """
    found, section = [], ''
    for number, line in lines:
        header = re.search(r'"(dependencies|devDependencies|peerDependencies|require|require-dev)"\s*:', line)
        if header:
            section = header.group(1)
            continue
        if section and re.match(r'^\s*[}\]]', line):
            section = ''
            continue
        entry = re.match(r'^\s*"([^"]+)"\s*:\s*"([^"]*)"', line)
        if section and entry:
            note = 'development only' if 'dev' in section.lower() else ''
            detail = ' '.join(x for x in (entry.group(2), note and '(' + note + ')') if x)
            found.append(_item(entry.group(1), path, number, link(number), detail))
    return found


def _toml_or_mod(lines, path, link):
    """Dependency names from pyproject.toml, Cargo.toml, go.mod, a Gemfile or environment.yml."""
    found, inside = [], False
    for number, line in lines:
        stripped = line.strip()
        if stripped.startswith('['):
            inside = bool(re.search(r'\[(?:project|tool\.poetry)?\.?dependencies|\[dependencies',
                                    stripped, re.I))
            continue
        if re.match(r'^\s*(?:dependencies|install_requires|require|requires)\s*[=(:]', line, re.I):
            inside = True
            continue
        if inside and re.match(r'^\s*[)\]]', line):
            inside = False
            continue
        gem = re.match(r'^\s*gem\s+["\']([^"\']+)["\']', line)
        if gem:
            found.append(_item(gem.group(1), path, number, link(number)))
            continue
        if path.endswith('go.mod'):
            mod = re.match(r'^([a-z0-9][\w.\-]*(?:/[\w.\-]+)+)\s+v?([\w.\-+]+)$', stripped)
            if mod:
                found.append(_item(mod.group(1), path, number, link(number), mod.group(2)))
                continue
        if not inside:
            continue
        quoted = re.findall(r'["\']([A-Za-z0-9_.\-/@]{2,})["\']', line)
        if quoted:
            for name in quoted:
                found.append(_item(re.split(r'[<>=!~\s\[]', name, 1)[0], path, number, link(number)))
            continue
        entry = re.match(r'^-?\s*([A-Za-z0-9_.\-/]{2,})\s*[=><]', stripped)
        if entry:
            found.append(_item(entry.group(1), path, number, link(number)))
    return found


def _dependencies(files, link_for):
    """Every declared dependency, each one carrying the file and line that declares it."""
    items = []
    for path, lines in files.items():
        name = PurePosixPath(path).name.lower()
        kind = DEPENDENCY_FILES.get(name)
        if not kind and name.startswith('requirements') and name.endswith('.txt'):
            kind = 'Python'
        if not kind:
            continue

        def link(number, where=path):
            return link_for(where, number)

        if name.startswith('requirements') or name == 'pipfile':
            found = _requirements(lines, path, link)
        elif name.endswith('.json'):
            found = _json_dependencies(lines, path, link)
        else:
            found = _toml_or_mod(lines, path, link)
        seen = set()
        for entry in found:
            if entry['text'].lower() in seen or not (1 < len(entry['text']) <= 60):
                continue
            seen.add(entry['text'].lower())
            entry['detail'] = ' '.join(x for x in (entry['detail'], 'declared in ' + path) if x)
            items.append(entry)
    return items


def _routes(files, link_for):
    """Addresses this project answers on, read from the route declarations themselves."""
    items, seen = [], set()
    for path, lines in files.items():
        if TEST_PATH.search(path):
            continue
        for number, line in lines:
            decorator = ROUTE_DECORATOR.search(line)
            call = ROUTE_CALL.search(line)
            table = ROUTE_TABLE.search(line)
            if decorator:
                method, address = decorator.group(1).upper(), decorator.group(2)
            elif call:
                method, address = call.group(1).upper(), call.group(2)
            elif table:
                method, address = '', table.group(1)
            else:
                continue
            if not address or len(address) > 120 or ' ' in address:
                continue
            label = (method + ' ' + address).strip()
            if label.lower() in seen:
                continue
            seen.add(label.lower())
            items.append(_item(label, path, number, link_for(path, number), 'handled in ' + path))
    return items


def _environment(files, link_for):
    """Settings the code reads from the environment, plus the keys any example file lists."""
    items, seen = [], set()
    for path, lines in files.items():
        example = PurePosixPath(path).name.lower().startswith(('.env', 'env.'))
        for number, line in lines:
            names = []
            for pattern in ENV_PATTERNS:
                names += pattern.findall(line)
            if example:
                bare = line.lstrip('#').strip() if line.lstrip().startswith('#') else line
                found = SETTING_LINE.match(bare)
                if found:
                    names.append(found.group(1))
            for name in names:
                if name in seen or name in {'NODE_ENV', 'PATH'}:
                    continue
                seen.add(name)
                items.append(_item(name, path, number, link_for(path, number),
                                   ('listed as an example in ' if example else 'read by ') + path))
    return sorted(items, key=lambda x: x['text'])


def _stores(files, link_for):
    """Tables, model classes and data shapes, plus which database engines are referred to."""
    items, seen, engines = [], set(), {}
    for path, lines in files.items():
        if TEST_PATH.search(path):
            continue
        for number, line in lines:
            for pattern, kind in STORE_PATTERNS:
                found = pattern.search(line)
                if not found:
                    continue
                name = found.group(1)
                if name.lower() in seen or len(name) > 60:
                    continue
                seen.add(name.lower())
                items.append(_item(name, path, number, link_for(path, number), kind + ' in ' + path))
            lowered = line.lower()
            for needle, pretty in ENGINES.items():
                if needle in lowered and pretty not in engines:
                    engines[pretty] = (path, number)
    for pretty, (path, number) in sorted(engines.items()):
        items.append(_item(pretty, path, number, link_for(path, number),
                           'referred to in ' + path))
    return items


def _commands(files, link_for):
    """Commands the project defines for itself: npm scripts, make targets, container entry points."""
    items = []
    for path, lines in files.items():
        name = PurePosixPath(path).name.lower()
        if name == 'package.json':
            inside = False
            for number, line in lines:
                if re.search(r'"scripts"\s*:', line):
                    inside = True
                    continue
                if inside and re.match(r'^\s*[}\]]', line):
                    inside = False
                    continue
                entry = re.match(r'^\s*"([^"]+)"\s*:\s*"(.*)"', line)
                if inside and entry:
                    items.append(_item('npm run ' + entry.group(1), path, number,
                                       link_for(path, number), entry.group(2)[:200]))
        elif name in {'makefile', 'justfile'}:
            for number, line in lines:
                entry = re.match(r'^([A-Za-z_][\w.-]*)\s*:(?!=)', line)
                if entry:
                    items.append(_item('make ' + entry.group(1), path, number, link_for(path, number)))
        elif name.startswith('dockerfile') or name == 'procfile':
            for number, line in lines:
                if name == 'procfile' or re.match(r'^\s*(CMD|ENTRYPOINT|EXPOSE)\b', line):
                    if line.strip():
                        items.append(_item(line.strip()[:160], path, number,
                                           link_for(path, number), 'from ' + path))
        elif name.endswith(('.bat', '.sh', '.ps1', '.cmd')) and len(PurePosixPath(path).parts) == 1:
            items.append(_item(path, path, 1, link_for(path, 1),
                               'a start-up script in the project root'))
    return items


def _documents(paths, link_for):
    """Documentation that was indexed, so a reader can open it rather than be told about it."""
    items = []
    for path in paths:
        name = PurePosixPath(path).name.lower()
        stem = PurePosixPath(path).stem.lower()
        head = PurePosixPath(path).parts[0].lower()
        if not (name.endswith(DOC_SUFFIXES) or '.' not in name):
            continue
        if not (stem.startswith(DOC_NAMES) or head in DOC_DIRS):
            continue
        why = ('The project introduces itself here.' if stem.startswith('readme')
               else 'Terms of use.' if stem.startswith(('license', 'licence'))
               else 'How to contribute changes.' if stem.startswith('contributing')
               else 'What changed between versions.' if stem.startswith('changelog')
               else 'A written guide kept with the project.')
        items.append(_item(path, path, 1, link_for(path, 1), why))
    return sorted(items, key=lambda x: (len(PurePosixPath(x['path']).parts), x['path']))


def _shape(paths, counts, link_for):
    """How much was read and what kind of files it is, counted rather than estimated."""
    items, languages, folders = [], {}, {}
    code = [p for p in paths if not is_source_path(p)]
    for path in code:
        suffix = PurePosixPath(path).suffix.lower()
        pretty = LANGUAGES.get(suffix) or ((suffix.lstrip('.') or 'no extension') + ' files')
        languages[pretty] = languages.get(pretty, 0) + 1
        parts = PurePosixPath(path).parts
        head = parts[0] if len(parts) > 1 else 'the project root'
        folders[head] = folders.get(head, 0) + 1
    for pretty, number in sorted(languages.items(), key=lambda x: (-x[1], x[0])):
        items.append(_item(f'{pretty}: {number} ' + ('file' if number == 1 else 'files')))
    for head, number in sorted(folders.items(), key=lambda x: (-x[1], x[0])):
        label = head if head == 'the project root' else head + '/'
        items.append(_item(label, detail=f'{number} ' +
                           ('file was read here' if number == 1 else 'files were read here')))
    tests = [p for p in code if TEST_PATH.search(p)]
    if tests:
        items.append(_item(f'{len(tests)} test ' + ('file' if len(tests) == 1 else 'files'),
                           tests[0], 1, link_for(tests[0], 1),
                           'tests describe what the project expects of itself'))
    for prefix, label in (('slack/', 'Slack message blocks'), ('jira/', 'Jira issue blocks')):
        number = counts.get(prefix, 0)
        if number:
            items.append(_item(f'{number} {label}',
                               detail='read in beside the code and searched with it'))
    return items


def _services(files, dependencies, link_for):
    """Outside services this project talks to, and the line that talks to them.

    "Stripe is integrated" tells a new developer nothing they can act on. What they need is
    which file calls it and what it is called for, so a service is only reported when
    something in the project actually reaches for it, and the entry carries that line.
    """
    items, seen = [], {}

    def note(key, where, line, how):
        pretty, purpose = SERVICES[key]
        if pretty in seen:
            return
        seen[pretty] = True
        items.append(_item(pretty, where, line, link_for(where, line),
                           purpose + ', ' + how))

    declared = {d['text'].lower(): d for d in dependencies}
    for name, entry in sorted(declared.items()):
        for key in SERVICES:
            bare = name.split('/')[-1].replace('@', '')
            if key == bare or key in bare.split('-') or bare.startswith(key):
                note(key, entry['path'], entry['line'],
                     'brought in by the dependency ' + entry['text'])
                break
    for path, lines in sorted(files.items()):
        if TEST_PATH.search(path):
            continue
        for number, line in lines:
            lowered = line.lower()
            if not re.match(r'^\s*(?:from|import|const|let|var|require|use)\b', lowered) \
                    and 'import' not in lowered:
                continue
            for key in SERVICES:
                if re.search(r'\b' + re.escape(key) + r'\b', lowered):
                    note(key, path, number, 'imported by ' + path)
                    break
    # An address written into the code is a service too, and often the only sign of one that
    # arrived without a package: a webhook posted to, an API called with plain HTTP.
    hosts = {}
    for path, lines in sorted(files.items()):
        # An address in a readme is a link for a human to click and one in an install script is
        # usually a download, neither of which this project calls. Only source code counts, or
        # every documentation link becomes an integration.
        if PurePosixPath(path).suffix.lower() not in CALLING_SUFFIXES or TEST_PATH.search(path):
            continue
        for number, line in lines:
            for host in SERVICE_CALL.findall(line):
                lowered = host.lower()
                if any(x in lowered for x in INTERNAL_HOSTS) or lowered in hosts:
                    continue
                hosts[lowered] = (path, number)
    for host, (path, number) in sorted(hosts.items())[:12]:
        if any(host.startswith(s.lower().replace(' ', '')) for s in seen):
            continue
        items.append(_item(host, path, number, link_for(path, number),
                           'an address this project calls, written into ' + path))
    return items


def _delivery(files, paths, dependencies, link_for):
    """How the project says it is built, shipped and watched.

    Every entry is a file in the repository. A pipeline file is not a pipeline run and a
    monitoring dependency is not a dashboard, so each entry says it was read, never observed.
    """
    items = []
    for path in paths:
        name = PurePosixPath(path).name.lower()
        known = DELIVERY_FILES.get(name)
        if not known and name.startswith('dockerfile'):
            known = DELIVERY_FILES['dockerfile']
        if known:
            items.append(_item(known[0], path, 1, link_for(path, 1), known[1] + ', read from ' + path))
            continue
        folder = '/'.join(PurePosixPath(path).parts[:2]).lower()
        if folder in CI_DIRS or PurePosixPath(path).parts[0].lower() in CI_DIRS:
            items.append(_item(PurePosixPath(path).name, path, 1, link_for(path, 1),
                               'a build or release pipeline definition, read from ' + path))
    watching = [d for d in dependencies
                if any(k in d['text'].lower() for k in ('sentry', 'datadog', 'newrelic',
                                                        'opentelemetry', 'prometheus'))]
    for entry in watching:
        items.append(_item(entry['text'], entry['path'], entry['line'],
                           link_for(entry['path'], entry['line']),
                           'watches the running system, declared in ' + entry['path']))
    return items


# What a reader will reasonably want that this scan has no way of answering. Saying so, and
# saying what was looked at, is worth more than silence: silence reads as "there is nothing
# here", and the two are very different.
UNREACHABLE = [
    ('Pull requests and code review',
     'why a change was made and who questioned it',
     'the scan reads one branch at one commit, so no pull request, review comment or merge '
     'is visible to it'),
    ('Commit history',
     'when something changed and what it looked like before',
     'only the files as they stand at the scanned commit were read, with no history behind them'),
    ('Actual pipeline runs',
     'whether the build and the tests are passing right now',
     'pipeline definition files are read as text where they exist, but no run, result or '
     'duration is fetched from any CI system'),
    ('Running deployments',
     'what version is live, and where',
     'deployment settings are read as files where they exist; nothing is queried from a '
     'hosting platform, cluster or registry'),
    ('Logs and monitoring',
     'what is failing in production and how often',
     'no log store or monitoring service is connected, so only the code that writes logs is '
     'visible, never a log line'),
    ('The live database',
     'what the data actually looks like and how much of it there is',
     'tables and models are read from the code that declares them; no database is connected '
     'and no row is ever read'),
    ('Third-party behaviour',
     'what an outside service returns in practice, including when it fails',
     'the call sites are read from the code; no request is made to any outside service'),
]


def gaps(groups, counts) -> dict:
    """The honest edge of what was read, with what was checked for each thing that is missing.

    This is not an apology. A new developer who knows that pull requests were never read will
    go and read them; one who is not told assumes the overview covered everything and does not.
    """
    present = {g['key']: g for g in groups}
    # Built through _item like every other group, so one shape of entry reaches the browser
    # and a gap cannot quietly lack the fields the rest are read for. A gap has no file behind
    # it, which is the whole point, so its path and its link are empty.
    missing = [_item(title, detail='for ' + wanted + '. Not available because ' + why)
               for title, wanted, why in UNREACHABLE]
    checked = []
    for key, label in (('documents', 'documentation files in the repository'),
                       ('dependencies', 'the files that declare dependencies'),
                       ('routes', 'route declarations in the code'),
                       ('stores', 'table and model declarations'),
                       ('environment', 'settings read from the environment'),
                       ('services', 'outside services reached from the code'),
                       ('delivery', 'build, container and pipeline files')):
        group = present.get(key)
        found = len(group['items']) if group else 0
        checked.append(f'{label}: {found} found' if found else f'{label}: none found')
    for prefix, label in (('slack/', 'Slack messages'), ('jira/', 'Jira issues')):
        number = counts.get(prefix, 0)
        checked.append(f'{label}: {number} blocks read' if number
                       else f'{label}: not connected for this scan')
    return {'key': 'gaps', 'title': 'What this cannot tell you',
            'plain': 'Each of these is something a new developer will want and this scan has no '
                     'way of answering. The reason is given so you know where to go instead.',
            'items': missing, 'truncated': 0,
            'note': 'Checked for this scan: ' + '; '.join(checked) + '.'}


def derive(index, scan: dict) -> list[dict]:
    """Read every group of facts out of one scan's indexed text.

    Takes the index rather than a list of paths because the stored chunks already hold the
    text, so nothing here fetches anything or reads GitHub again.
    """
    paths = index.indexed_paths(scan['id'])
    code = index.code_paths(scan['id'])
    files = {p: index.file_lines(scan['id'], p) for p in code}
    counts = {prefix: index.source_blocks(scan['id'], prefix) for prefix in ('slack/', 'jira/')}

    def link_for(path, line):
        if scan.get('demo'):
            return ''
        return source_url(scan.get('repo', ''), scan.get('commit', ''), path, line)

    dependencies = _dependencies(files, link_for)
    groups = [
        _group('shape', 'What was read',
               'The size and shape of what the scan actually covered.',
               _shape(paths, counts, link_for)),
        _group('documents', 'Documentation in the project',
               'The written guides that were indexed. Open these first.',
               _documents(paths, link_for)),
        _group('dependencies', 'Other software this project needs',
               'Taken from the files that declare dependencies, not guessed from import lines.',
               dependencies),
        _group('services', 'Outside services it talks to',
               'Each one carries the line that reaches for it and what it is reached for.',
               _services(files, dependencies, link_for)),
        _group('commands', 'Commands the project defines',
               'Scripts and targets the project set up for itself. These are listed, never run.',
               _commands(files, link_for)),
        _group('routes', 'Addresses it answers on',
               'Each entry is one route declaration, at the line that declares it.',
               _routes(files, link_for)),
        _group('stores', 'Where information is kept',
               'Tables, model classes, data shapes and the database engines the code mentions.',
               _stores(files, link_for)),
        _group('environment', 'Settings it reads from the environment',
               'Names only. No value is read, shown or stored by this list.',
               _environment(files, link_for)),
        _group('delivery', 'How it is built and shipped',
               'Read from the files that describe it. A pipeline file is not a pipeline run, '
               'and nothing here was observed actually happening.',
               _delivery(files, paths, dependencies, link_for)),
    ]
    found = [g for g in groups if g['items']]
    # Always last, and always present: what was not reachable is as much a fact of the scan as
    # what was.
    found.append(gaps(found, counts))
    return found
