# Task 6.7: limit search to each user's permissions

The local Windows app now supports an owner and up to 25 member accounts. The owner creates
or disables members from **Account settings**. Each member signs in with their own password,
adds their own source credentials, and chooses their own repository, Jira project and Slack
channels. Existing owner data and sessions are retained by the account database migration.

## Permission boundary

The server chooses the workspace from the authenticated account ID. Query parameters,
request headers, repository names and guessed object IDs cannot select another workspace.
Each account has a separate index, source settings, imported content, embeddings, answers,
feedback, overview, feature explanations, jobs and scan reports. The owner's index remains
at its existing path. Member indexes live under `data/index.users/<account-id>/`.

Each account's source credentials are carried in a request context and passed explicitly to
the fixed MCP subprocess. Members do not inherit the owner's process environment, token,
cached source listing or repository selection. Background jobs inherit the initiating context.
Shared account and audit routes require authentication; only the owner can manage members or
read the audit records. Disabling a member revokes their sessions and cancels their active job.
Re-enabling the account does not revive previous sessions.

GitHub access and the branch commit are checked before serving cached code views and before
search. Source access is checked again after answer generation, before saving or returning the
result. Existing issue-level Jira and message-snapshot Slack checks remain in place. Confirmed
denial invalidates the affected saved content. A transient verification failure withholds the
response without treating an outage as proof that permission was revoked.

## Credentials and action records

**Account settings → Your source credentials** accepts masked values without returning them.
The GitHub link opens token creation; select the intended repository and Contents read-only.
Connections now says **Credential saved**, since a saved token alone does not verify access.

Windows current-user DPAPI encrypts separate credential files. On first production startup,
the owner credentials in the existing `.env` are encrypted, read back for verification, then
removed from `.env` and the process environment. Other settings remain in `.env`. An encryption
failure leaves the original configuration in place and prevents startup. Quoted multiline
credential values are removed completely. Member saves never modify the owner's environment.

Audit records contain account IDs, action names, times and HTTP outcomes. Passwords, session
tokens, source content, questions and credential values are excluded. The owner can paginate
through records in Account settings. These controls also provide the credential and audit
foundation requested by task 6.8.

## Verification

`tests/test_workspaces.py` uses real account sessions and controlled upstream permissions to
check separate retrieval and cached views, guessed IDs, host credential isolation, scan logs,
revocation before and during generation, member disable/re-enable, password/session isolation,
audit redaction and concurrent credential contexts. `tests/test_vault.py` exercises actual
Windows DPAPI persistence, tampering, complete migration and encryption failure.

Six Chrome checks use disposable owner/member accounts and fixture sources: masked credential
save, owner membership controls, empty member workspaces, persistence across reload, disabled
session replay and audit display. No browser page errors occurred. Desktop account layouts were
checked at 1440 and 1280 pixels. The existing narrow-screen app shell remains a separate layout
limitation; this task does not add mobile navigation.

## Limits

This is local hosting on Windows, bound to `127.0.0.1`. It does not introduce LAN hosting,
organization SSO, shared indexes or administrator impersonation. Browser accounts are isolated
from each other, but the Windows account running the app remains trusted: it can read the local
databases and unlock the vaults. Indexes and debug logs are not encrypted by this change.
DPAPI restoration requires the appropriate Windows account and its keys. Audit records are
local records, not an externally secured or tamper-proof audit service. Deployment scheduling,
backup retention and recovery validation remain task 6.9.
