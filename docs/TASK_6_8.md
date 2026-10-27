# Task 6.8: credentials and audit records

Verified on 27 October 2026 for the existing private Windows account scope.
The implementation was introduced with task 6.7; this task closes its separate
credential/audit verification rather than adding a second credential store.

Source tokens are stored in separate Windows current-user DPAPI vaults. The API
returns configured/not-configured flags, never stored values. Source requests use
the authenticated account's vault. A member cannot inherit the owner's tokens or
select another account's saved project by request parameters. Failure to unlock
an existing vault fails closed. Migration verifies encrypted storage before
removing complete credential entries from the legacy `.env` file.

Only the owner can inspect audit records. Records contain action names, actor and
target account IDs, HTTP outcomes and timestamps. They exclude passwords, source
tokens, session cookies, questions, source excerpts and request bodies. Member
disablement revokes sessions and cancels that member's active jobs.

## Executed verification

`tests/test_auth.py`, `tests/test_vault.py` and `tests/test_workspaces.py`: **46
passed** on Windows with Python 3.12.14. These tests use disposable accounts and
source fixtures, real password hashing, real Windows DPAPI, HTTP endpoints, and
adversarial owner/member requests. They cover encrypted persistence, tampering,
failed migration, multiline credential cleanup, isolated writes and concurrent
credential contexts, private cached content, disabled sessions and audit redaction.
`pip check` passed. The existing Starlette/httpx deprecation warning remains.

Task 6.8 is **Done for this Windows scope**. The host Windows account remains
trusted and can unlock its vaults; source indexes and logs are not encrypted by
this task. Audit storage is local and is not an external tamper-proof service.
Credential recovery requires the original Windows account and its DPAPI keys.
Shared-network hosting and backup/recovery are assessed separately under 6.9.
