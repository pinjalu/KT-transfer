"""Traceable relationships within the selected snapshot; never follow links or use a model."""
import re
from urllib.parse import unquote, urlsplit

from pka.config import source_url
from pka.index import QUERY_FILLER, STOP, words
from pka.jira_tasks import metadata_text

URL = re.compile(r'https?://[^\s<>\[\]"\)|]+', re.I)
LINK_MARKUP = re.compile(r'\[[^\]]*\]\(https?://[^)]+\)|<https?://[^>]+>', re.I)
GENERIC = STOP | QUERY_FILLER | set('task tasks issue issues ticket tickets jira description '
    'acceptance criteria requirement requirements feature features type status priority assigned '
    'reporter reported nobody unknown none rank labels today work implementation implement add '
    'update create requested request should must shall need needs new existing '
    'above across after again against all already also although always among another any '
    'anyone anything around because been before being below beside between both but could '
    'during each either else enough even every everyone everything few first further had '
    'has have having however into its itself just last least less many may might more most '
    'much neither never next nor not now off often once one only other others our ours out over '
    'own per rather same several since some someone something still such than their theirs '
    'them themselves then these they those though through thus too toward under until upon '
    'very via well were whether while whose will within without would yet '
    'app apps application applications code source sources file files function functions '
    'change changes changed changing complete completed completing done ensure example '
    'following given include includes including make made provide provides real work works '
    'back current get gets set sets run runs running return returns pass def class self true false'.split())


def plain(text):
    """Keep offsets while excluding URLs and their labels from bare-key/path matching."""
    for pattern in (LINK_MARKUP, URL):
        text = pattern.sub(lambda match: ' ' * len(match.group()), text)
    return text


def token_match(value, text, ignore_case=True):
    return re.search(r'(?<![\w./-])(?:\./)?' + re.escape(value) + r'(?![\w/-]|\.[\w])', text,
                     re.I if ignore_case else 0)


def normalized_url(url):
    try:
        parsed = urlsplit(url.rstrip('.,;:'))
        return parsed.hostname, unquote(parsed.path).rstrip('/')
    except ValueError:
        return None, ''


def slack_url(url):
    return bool(url and url.startswith('https://') and
                (normalized_url(url)[0] or '').endswith('.slack.com'))


def issue_reference(key, issue_url, text):
    expected = normalized_url(issue_url)
    for match in URL.finditer(text):
        if expected[0] and normalized_url(match.group()) == expected:
            return match.start(), 'This excerpt links directly to the selected Jira issue.'
    match = token_match(key, plain(text))
    if match:
        return match.start(), f'This excerpt explicitly mentions {key}.'
    return None


def task_words(sources, key):
    text = ''.join(source['text'] for source in sources)
    for metadata in metadata_text(sources):
        # Metadata may span lines; matching whitespace consistently keeps admin terms out.
        pattern = r'\s+'.join(re.escape(part) for part in metadata.split())
        text = re.sub(pattern, ' ', text)
    text = text.replace(key, ' ')
    return {word for word in words(plain(text)) if len(word) >= 3 and not word.isdigit() and word not in GENERIC}


def excerpt(row, position=0, discussion=False):
    text = row['text']
    line = text[:position].count('\n')
    lines = text.splitlines(keepends=True)
    low = sum(len(part) for part in lines[:max(0, line-2)])
    high = sum(len(part) for part in lines[:line+5])
    # Very long code lines and Slack messages stay bounded, centered on the actual match.
    if high-low > 1400:
        low = max(low, position-350)
        high = min(high, low+1400)
    part = text[low:high].rstrip()
    start = row['start'] if discussion else row['start'] + text[:low].count('\n')
    end = row['end'] if discussion else start + part.count('\n')
    return {'path':row['path'], 'start':start, 'end':end, 'text':part,
            'shortened':low > 0 or high < len(text), 'url':row.get('url') or ''}


def named_file(path, sources, scan):
    """Exact indexed paths or current-repository URLs are recorded links, not guesses."""
    for source in sources:
        text = source['text']
        for match in URL.finditer(text):
            host, target = normalized_url(match.group())
            if host not in {'github.com', 'www.github.com'}:
                continue
            if any(target == f"/{scan['repo']}/blob/{ref}/{path}" for ref in {scan['commit'], scan['branch']}):
                return excerpt(source, match.start()), 'The Jira task links to this file in the selected repository.'
        match = token_match(path, plain(text), ignore_case=False)
        if match:
            return excerpt(source, match.start()), 'The Jira task explicitly names this indexed file.'
    return None


def named_discussion(url, sources):
    if not slack_url(url):
        return None
    for source in sources:
        for match in URL.finditer(source['text']):
            if normalized_url(match.group()) == normalized_url(url):
                return excerpt(source, match.start()), 'The Jira task links to the start of this imported Slack excerpt.'
    return None


def related(key, sources, rows, scan, kind, offset=0, limit=10):
    """Return a bounded page while counting all matching imported files or excerpts."""
    issue_url = sources[0].get('url') or ''
    wanted = task_words(sources, key)
    files = {row['path'] for row in rows} if kind == 'files' else set()
    named = {path:named_file(path, sources, scan) for path in files}
    candidates = {}
    for row in rows:
        discussion = kind == 'discussions'
        reference = issue_reference(key, issue_url, row['text'])
        forward = named_discussion(row.get('url'), sources) if discussion else named[row['path']]
        shared = sorted(wanted & set(words(plain(row['text']))))
        evidence, position = None, 0
        if reference:
            position, reason = reference
            confidence = 'confirmed'
        elif forward:
            evidence, reason = forward
            confidence = 'confirmed'
        elif len(shared) >= 2:
            confidence, reason = 'possible', 'Shared words only; no explicit task reference was found.'
            position = min((match.start() for term in shared
                            for match in [re.search(re.escape(term), row['text'], re.I)] if match), default=0)
        else:
            continue
        context = excerpt(row, position, discussion)
        if not discussion:
            context['url'] = source_url(scan['repo'], scan['commit'], row['path'], context['start'], context['end'])
        elif not slack_url(context['url']):
            context['url'] = ''
        identifier = str(row['id']) if discussion else row['path']
        rank = (confidence == 'confirmed', reference is not None, len(shared))
        item = {**context, 'id':identifier, 'confidence':confidence, 'reason':reason,
                'shared_words':shared[:12] if confidence == 'possible' else [],
                'evidence':evidence, 'kind':kind}
        # One file card, with its strongest actual matching excerpt. Discussions retain
        # their imported block identity so different channel excerpts are not collapsed.
        if identifier not in candidates or rank > candidates[identifier][0]:
            candidates[identifier] = (rank, item)
    ordered = [item for _, item in sorted(candidates.values(), key=lambda pair:
        (-pair[0][0], -pair[0][1], -pair[0][2], pair[1]['path'], pair[1]['start'], pair[1]['id']))]
    confirmed = sum(item['confidence'] == 'confirmed' for item in ordered)
    return {'items':ordered[offset:offset+limit], 'total':len(ordered), 'confirmed':confirmed,
            'possible':len(ordered)-confirmed, 'offset':offset, 'limit':limit,
            'next_offset':offset+limit if offset+limit < len(ordered) else None,
            'searched':len({row['path'] for row in rows}) if kind == 'files' else len(rows),
            'search_words':sorted(wanted)[:20], 'kind':kind}
