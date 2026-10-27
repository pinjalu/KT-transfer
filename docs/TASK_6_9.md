# Task 6.9: private hosting and recovery

The implementation adds explicit private HTTPS hosting, a minimal health check,
a single-process data-directory lock, verified offline backups and restoration
into a new data directory. Local startup still defaults to `127.0.0.1:8000`.

The user selected this Windows computer on the office network. A private certificate
for `192.168.0.149` and setup instructions are prepared in [TEAM_OFFICE_SETUP.md](TEAM_OFFICE_SETUP.md).
Certificate trust and a test from a teammate's computer remain necessary before
this task can be marked deployed. The current live app
has not been switched to a network listener and no firewall or machine trust
settings have been changed.

## Private Windows host

Use the Windows account that owns the current encrypted credentials. Choose a
specific private IPv4 address assigned to the host, an internal hostname that
resolves to it, and a matching PEM certificate/key pair from a certificate
authority trusted by the team's browsers. Keep the private key on the host.
Wildcard/public binds and network HTTP are refused. Reverse-proxy forwarded
headers are not trusted in this release.

Example after substituting the actual address, hostname and certificate paths:

```powershell
.\.venv\Scripts\python.exe -m pka --host 192.168.1.20 --port 8443 --team-origin https://kt.example.internal:8443 --ssl-certfile D:\KT-Certificates\server.pem --ssl-keyfile D:\KT-Certificates\server-key.pem
```

Use the normal account-creation and member controls. Existing sessions are bound
to their original origin; users sign in again at the team HTTPS address. Source
credentials and workspaces remain separate. Secure cookies, exact host/origin
validation, request headers, source access checks and session invalidation still
apply. This mode does not configure network routing, open firewall ports, issue
certificates, add system certificate trust, or create an auto-start service.

The existing Slack OAuth callback is local-host scoped. For the initial team
release, members can enter their existing authorised user tokens in Account
settings. Organisation-hosted OAuth registration is a separate deployment step.
Local-folder connections refer to paths on the hosting computer, not a teammate's
browser computer.

## Monitoring

`GET /healthz` returns only `{"status":"ok"}` when the application can read its
local project and account databases. Storage failures return HTTP 503 with
`{"status":"unavailable"}`. Host restrictions and no-store headers still apply.
It does not expose account details, project names, credentials or source content.
Use this URL in the team's existing HTTPS monitor; never disable certificate
verification. This is application/storage readiness, not proof of source-provider
or Ollama availability. The existing signed-in connection checks cover those.

## Backup and recovery

Restart once with the updated launcher before relying on its runtime lock. Stop
the application and any maintenance commands before taking a backup. The CLI
refuses a data directory held by the supported launcher. Backups include the owner
and member project databases, shared accounts/audit database, and encrypted source
vaults. They exclude debug logs, `.env`, old setup codes, model files, certificates
and the source repositories themselves. Keep deployment configuration and the TLS
key separately under the host administrator's controls.

```powershell
.\.venv\Scripts\python.exe -m pka.backup create --output ..\outputs\team-backup-2026-10-27.zip
.\.venv\Scripts\python.exe -m pka.backup verify ..\outputs\team-backup-2026-10-27.zip
.\.venv\Scripts\python.exe -m pka.backup restore ..\outputs\team-backup-2026-10-27.zip --destination ..\restored-team-data
```

Create uses SQLite's backup API, including committed WAL content, checks database
integrity and verifies every archived file against a SHA-256 manifest. It refuses
existing output filenames. Restore rejects unexpected paths, duplicate files,
missing files, checksum failures and invalid databases. Encrypted vaults must
unlock successfully before publication. The destination must not already exist.
Restoring never replaces the live data directory, and old sessions/setup tokens
are removed from the restored account database.

After checking the restored copy, stop the old server and start against the new
directory from the original Windows account:

```powershell
$env:PKA_DATA_DIR = 'D:\Downloads\project-knowledge-assistant-stage1\restored-team-data'
.\.venv\Scripts\python.exe -m pka
```

For shared hosting, append the verified HTTPS arguments. The original directory
remains available for rollback. Re-select the saved project, confirm source access
and check one owner and one member workspace. External sources must still grant
the account access. Record a backup cadence, retention period, protected off-host
destination and a completed restore drill before operational sign-off. Backups
contain private project data; the archive itself is not password-encrypted.

## Verification

Initial focused suite: **27 passed**, covering hosting validation, origin/host
checks, authentication, Secure cookies, health failure, backup checksums and
restoration boundaries. Real HTTPS/server smoke and final regressions are recorded
in `TEAM_RELEASE.md`. The actual team certificate passed the real loopback HTTPS
smoke with certificate verification enabled. A separate recovery drill restored
the real project and accounts, verified matching row counts and revoked restored
sessions. No office-network deployment or unattended backup schedule has been
verified yet.

References: [Python SQLite backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup).
