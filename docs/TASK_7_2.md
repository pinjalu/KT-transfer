# Task 7.2: incremental and resumable file imports

GitHub repository scans and local folder reads now reuse unchanged files. Each successful
file read is checkpointed in the account's own SQLite database. A refresh or **Retry job**
resolves the currently selected source, enumerates its current files, and reuses a checkpoint
only when the path and content hash match. New and changed files are fetched again; deleted
and excluded files are removed. Failed files are retried. Cancellation, a temporary network
failure or an app restart can retain completed reads without publishing an incomplete scan.

On Connections, **Refresh repository** or **Read local folder again** uses this automatically.
After a failed, cancelled or interrupted job, choose **Retry job**. After restarting the app,
reselect the saved project first. Counts distinguish files reused from files fetched.
Older scans create their initial checkpoints on their first refresh after this update.

## Boundaries

- Checkpoints are private staging data, never searchable answers or source-viewer content.
  The existing atomic snapshot publication and source-revision invalidation still apply.
- Repository/folder, branch, credential identity, demo mode and import-policy version are part
  of the reuse scope. Changing the project or folder clears its old checkpoints. Confirmed
  access denial removes checkpoints as well as searchable content. Current source access is
  checked again before a repository scan is published. Concurrent invalidation prevents late
  reads from saving new checkpoints or publishing a scan.
- Each file-import slot retains at most the existing 500-file / 5 MiB scan allowance; individual
  files remain limited to 256 KiB. Current exclusions and scan limits also apply to reused files.
- GitHub's request-budget preflight subtracts matching cached files from estimated blob reads.
  Metadata and final access checks still make requests; the estimate is not a total HTTP count.
- Existing embeddings are reused for an identical path and text only when the model and input
  preprocessing signature match. Changed text is embedded again. Derived explanations are
  invalidated as before, and repository refresh still requires rereading supplemental imports.
- Local folders are still read to compute fresh content hashes and verify access. This avoids
  trusting file timestamps, but means local disk reads and snapshot verification still take time.

## Scope and verification

This implements the incremental/resumable file-import options in task 7.2. It does not add a
timer, watcher or scheduled unattended refresh. Jira and Slack retain their existing bounded
full reads, including edit/deletion and permission checks. Their pagination cursors and model
generation are not resumed. Checkpoints are local source text, protected by the existing
Windows/account trust boundary, not a new encrypted storage system.

`tests/test_incremental_imports.py` exercises unchanged refreshes, edits/additions/deletions,
restart/network/cancellation recovery, credential changes, denial before and after reads,
concurrent invalidation, account separation, exclusions and limits, GitHub request budgets,
real local-folder hashes, embedding compatibility and the real MCP process with demo data.
Existing scan, job, source-freshness, import-coverage and workspace-isolation tests remain
regression gates. Frontend checks verify reuse counts and source-specific guidance. No live
GitHub/Jira/Slack contents are modified by these tests.

Verified on 26 October 2026: the full backend suite passed **838 tests**, the frontend suite
passed **65 tests**, and the production build passed. The restarted local app serves the new
Connections interface. Its active scan, 1,134 chunks, two supplemental imports and source
revision were unchanged. Existing saved scans have no file checkpoints until their first
refresh with this version. No live browser interaction or external-source refresh was used
for this verification.
