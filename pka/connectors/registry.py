"""One place that describes every platform this application can read from.

Adding a platform means adding an entry here and a connector module beside it. The browser,
the setup guidance and the connection checks all read this list, so a new platform appears in
the interface without any of them being edited.

Selecting a platform records only that a project uses it. It never grants access. Access needs
a credential the user places in their own .env file and a scope the user names explicitly: one
repository, one Jira project, a listed set of Slack channels. That separation is deliberate,
so a tick in a box can never widen what the application may read.
"""
import os

AVAILABLE = 'available'
PLANNED = 'planned'

PLATFORMS = [
    {
        'key': 'github',
        'label': 'GitHub',
        'status': AVAILABLE,
        'reads': 'Source files and documentation from one branch, pinned to one commit.',
        'scope_label': 'Repository',
        'scope_hint': 'owner/repository',
        'credentials': ['GITHUB_TOKEN'],
        'credential_optional': True,
        'permission': 'Fine-grained token, single repository, Repository permissions, Contents: Read-only.',
        'setup': [
            'On github.com open Settings, Developer settings, Personal access tokens, Fine-grained tokens.',
            'Generate a new token and select only the repository you want to read.',
            'Under Repository permissions set Contents to Read-only. Grant nothing else.',
            'Put the token on the GITHUB_TOKEN line of your local .env file, then restart.',
            'A public repository works without a token, but only about 55 files per hour.',
        ],
    },
    {
        'key': 'jira',
        'label': 'Jira',
        'status': AVAILABLE,
        'reads': 'Issues, descriptions, acceptance criteria and comments from one selected project.',
        'scope_label': 'Project key',
        'scope_hint': 'ABC',
        'credentials': ['JIRA_SITE', 'JIRA_EMAIL', 'JIRA_API_TOKEN'],
        'credential_hints': {
            'JIRA_SITE': 'https://yourcompany.atlassian.net',
            'JIRA_EMAIL': 'the Atlassian account that created the token',
            'JIRA_API_TOKEN': 'from id.atlassian.com, Security, API tokens',
        },
        'credential_optional': False,
        'permission': 'API token with read scopes, limited to the one project you name.',
        'setup': [
            'Note your site address, for example https://yourcompany.atlassian.net.',
            'Create an API token at id.atlassian.com under Security, API tokens.',
            'Decide the single project key you want read, for example ABC.',
            'Paste the site address, your account email and the token into the boxes below.',
            'The token must be created by the same Atlassian account as the email, or Jira refuses it.',
            'Only the project key you name is read. No other project enters the index.',
        ],
    },
    {
        'key': 'slack',
        'label': 'Slack',
        'status': PLANNED,
        'reads': 'Messages and thread replies from channels you list, with timestamps and links.',
        'scope_label': 'Channels',
        'scope_hint': '#engineering, #releases',
        'credentials': ['SLACK_BOT_TOKEN'],
        'credential_optional': False,
        'permission': 'Bot token with channels:history and channels:read, for listed channels only.',
        'setup': [
            'Create a Slack app for your workspace and add a bot user.',
            'Give it channels:history and channels:read. Grant nothing that can post or edit.',
            'Invite the bot to each channel you want read. It cannot see a channel it is not in.',
            'Put the token on the SLACK_BOT_TOKEN line of your local .env file, then restart.',
            'List the channels explicitly. Nothing is added for you, and direct messages are never read.',
        ],
    },
    {
        'key': 'slack_user',
        'label': 'Slack',
        'status': AVAILABLE,
        'reads': 'Messages and thread replies from the channels you list, public or private, '
                 'using your own account. Reading only: nothing is posted, edited or deleted.',
        'scope_label': 'Channels',
        'scope_hint': '#engineering, #releases',
        'credentials': ['SLACK_CLIENT_ID', 'SLACK_CLIENT_SECRET'],
        'credential_hints': {
            'SLACK_CLIENT_ID': 'digits, a dot, then digits',
            'SLACK_CLIENT_SECRET': '32 letters and numbers, from Show next to Client Secret',
        },
        'credential_optional': False,
        'oauth': {
            'authorize': 'https://slack.com/oauth/v2/authorize',
            'exchange': 'https://slack.com/api/oauth.v2.access',
            'user_scopes': ['channels:history', 'channels:read', 'groups:history', 'groups:read'],
            'token_name': 'SLACK_USER_TOKEN',
            'redirect_path': '/api/slack/callback',
            'pkce': True,
        },
        'permission': 'User token with channels:history, channels:read, groups:history and groups:read. '
                      'Do not grant im:history or mpim:history, and nothing that can write.',
        'setup': [
            'Create a Slack app for your workspace at api.slack.com/apps.',
            'Under OAuth and Permissions add these User Token Scopes and nothing else: '
            'channels:history, channels:read, groups:history, groups:read.',
            'Do not add im:history or mpim:history. Those open your direct messages, which this never needs.',
            'Under OAuth and Permissions, add the four scopes under User Token Scopes, not Bot Token Scopes.',
            'On the same page add exactly this Redirect URL: http://localhost:8000/api/slack/callback '
            'Slack accepts localhost and refuses 127.0.0.1, so this is always the localhost form.',
            'On that page also press Opt In under Proof Key for Code Exchange. Slack requires it for '
            'a localhost address, and this application already sends the proof.',
            'From Basic Information copy the Client ID and Client Secret into the boxes below.',
            'Then press Connect Slack. Slack asks you to approve, and the token is stored for you.',
            'This reads only the channels you list, and only channels you are already a member of. '
            'A private channel you are not in cannot be read by any token.',
            'Access follows your account: if you leave a channel or revoke the token, that content '
            'stops refreshing and is excluded from answers.',
        ],
    },
]

BY_KEY = {p['key']: p for p in PLATFORMS}


def keys() -> list[str]:
    return [p['key'] for p in PLATFORMS]


def credentials_present(platform: dict) -> bool:
    """True when every credential this platform needs is set. Values are never read out."""
    return all(os.getenv(name, '') for name in platform['credentials'])


def describe(selected=None) -> list[dict]:
    """Every platform, with whether this project uses it and whether it could connect.

    'selected' is what the project declared it uses. A platform that is selected but not yet
    implemented is reported as such rather than hidden, so the interface can say plainly that
    the work is not done instead of appearing to offer something that does not exist.
    """
    chosen = set(selected or [])
    rows = []
    for p in PLATFORMS:
        present = credentials_present(p)
        if p['status'] != AVAILABLE:
            # Report the credentials even though reading is not built, otherwise saving them
            # appears to do nothing at all and looks like the save failed.
            connection = ('credentials saved, reading not built yet' if present
                          else 'not implemented yet')
        elif present:
            connection = 'credentials found'
        elif p['credential_optional']:
            connection = 'no credentials, limited access'
        else:
            connection = 'credentials needed'
        oauth = p.get('oauth')
        connected = bool(oauth and os.getenv(oauth['token_name'], ''))
        if oauth:
            if connected:
                connection = 'connected'
            elif present:
                connection = 'ready to connect'
            else:
                connection = 'client id and secret needed'
        rows.append({**{k: v for k, v in p.items()},
                     'selected': p['key'] in chosen,
                     'credentials_present': present,
                     'oauth': bool(oauth),
                     'connected': connected,
                     'connection': connection})
    return rows


def validate(selected) -> list[str]:
    """Keep only platform names this application knows, preserving the listed order."""
    if not isinstance(selected, (list, tuple)):
        raise ValueError('Choose the platforms this project uses.')
    unknown = [str(x) for x in selected if x not in BY_KEY]
    if unknown:
        raise ValueError('Unknown platform: ' + ', '.join(unknown) + '.')
    return [k for k in keys() if k in set(selected)]
