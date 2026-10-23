# Task 6.6 — user login and secure sessions

This task adds one owner account for the existing local workspace. First-time setup requires
a random, one-use code from the local `data/index.auth.setup-code` file and a new username/password.
Example mode uses separate `demo.auth.*` files. There is no open registration or second-account
creation: per-user source permissions and team credential isolation remain tasks 6.7–6.8.
Existing project data is preserved and unavailable through the API until the owner signs in.

## Passwords and account controls

Passwords accept 15–128 characters, including spaces, and are hashed with random salts and
scrypt N=131072, r=8, p=1. Passwords, setup codes and raw session tokens are not stored in the
authentication database or included in request validation errors. The temporary local setup
file contains the code for delivery and is removed on successful setup. Authentication files
are excluded from Git. Preserve operating-system access controls on the data directory and backups.

Click the username in the top bar for **Account**. Changing a password requires the current
password, revokes all old sessions, and issues a replacement for the current browser. **Sign out**
revokes the current session; **Sign out all sessions** revokes every session. A local administrator
can recover the owner password with `python -m pka --reset-password` in an interactive terminal
(add `--demo` for example mode). Recovery uses hidden prompts and revokes all sessions.

Five authentication attempts within five minutes trigger a persistent cooldown shared across
usernames; successful authentication clears it. Wrong username/password responses are generic,
and unknown usernames still incur the password-hash cost. Hash concurrency is bounded.

## Sessions and request protection

Session identifiers contain 32 random bytes. SQLite stores only their SHA-256 digests,
the account version, origin and timestamps. Each successful login replaces the cookie's previous
session. At most ten sessions are retained. Sessions survive application restarts but expire
server-side after 30 minutes without interaction or eight hours after sign-in.

Polling does not renew idle time. Browser pointer/key interaction sends a bounded activity
request, and expired sessions cannot be revived by it. Logout and password changes clear other
open tabs through a notification containing no credentials. Visibility changes, page restoration
and subsequent API requests recheck authentication; protected React content is unmounted when
authentication is lost or cannot be verified. Background jobs continue independently of a session,
but reading results requires authentication. Slow responses are checked again before publication.

Cookies are HttpOnly, SameSite=Lax, host-only and scoped to `/`; no tokens are placed in browser
storage or URLs. HTTPS sets Secure. The supported runtime binds to loopback HTTP, so the Secure
flag is omitted for that local transport. LAN hosting, reverse proxies, TLS deployment and MFA
are outside this task. Forwarded proxy headers are disabled by the supported launcher.

Every project API defaults to authenticated access. Only setup, login and minimal authentication
status are public. Existing Host, Origin, Fetch Metadata and application-header checks also
protect authentication endpoints; security/no-store headers cover early rejections. Authentication
request bodies are bounded even without Content-Length and malformed inputs never echo secrets.
The Vite proxy preserves foreign origins and does not manufacture application headers.

Slack browser approval must be started while signed in on localhost (the callback host Slack
accepts). OAuth state is bound to the initiating session, checked on callback, and the session is
rechecked before storing the resulting credential. A 127.0.0.1 connect attempt gives instructions
to sign in on localhost. Manually saved Slack credentials continue to work as before.

## Verification

Dedicated tests cover default denial on every data endpoint, protected existing data, atomic
first setup, hashed storage, cookie flags, request forgery, generic failures, persistent throttling,
session tampering/fixation, origin binding, password changes/recovery, idle/absolute expiry,
restart persistence, bounded sessions, OAuth session binding and logout during a slow response.
Existing feature tests now use real owner sessions rather than bypassing authentication.
The HTTP/MCP demo smoke creates a disposable account; the live answer-evaluation runner accepts
`--username` and prompts for its password without putting it in command arguments or reports.

Chrome checks cover first setup and confirmation, HttpOnly cookies, navigation/reload/background
work, multiple tabs and replay after logout, wrong passwords, password changes, both expiry
types, mobile layout and sign-out-all. These use disposable local accounts and simulated project
data. Production activation preserves existing imported data and leaves owner setup for the user
to choose their own password. Test counts and activation results are recorded in STATUS.md.

Design references: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), and
[session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
This implementation does not claim full compliance with those guides or protection from another
process already running as the same operating-system user.
