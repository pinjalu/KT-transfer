# GitHub and local folders together

In **Connections**, use the **Connection** dropdown to open the GitHub, Local folder,
Jira or Slack form. Changing this dropdown only changes the visible form. It does not
disconnect a source or change the saved project. Saved-source badges show which imports
are available. Forms retain their drafts while switching sources on the page.

To add local code to an existing GitHub project:

1. Sign in as the installation owner and open Connections.
2. Select **Local folder**.
3. Paste an absolute folder path such as `D:\Projects\shop`, or a link such as
   `file:///D:/Projects/shop`. Spaces in a file link may be encoded as `%20`.
4. Select **Save and read files**. The folder is added to the existing code index.
5. Build the Project overview or ask a question. Relevant evidence can come from
   GitHub, the local folder, Jira and Slack, with separate citations.

Adding or rereading an additional local folder retains the existing GitHub scan, Jira
issues and Slack messages. Derived answers and overviews are invalidated because their
evidence changed. A local folder can also be the initial code source without GitHub.
If GitHub is added later, its repository becomes the primary scan and the local folder
selection is retained; read that folder again to include it beside the GitHub snapshot.
One GitHub repository and one local folder are supported per workspace.

The folder must be on the computer running KT Assistant. It need not be a Git clone.
Current working files, including untracked and uncommitted files, are read without running
project code. No GitHub token is required for local files. Other app accounts cannot select
or read the owner's filesystem folders.

## Refresh and citations

Use **Read local folder again** after changing local files. There is no filesystem watcher
and a page refresh does not start an import or overview build. Before answers and saved
views are returned, the bounded local snapshot is checked again. Changes or denied access
remove the additional local content and its derived caches; the GitHub, Jira and Slack
imports remain. Read the folder again before relying on it. For a local-only project,
changed files invalidate its primary scan.

Local citations open an authenticated page inside KT Assistant with indexed line numbers.
They point to an exact content snapshot, not a Git commit or an unrestricted file URL.
Older citations are refused after the snapshot changes. Blank lines or content excluded
from indexing may be absent; retained line numbers stay tied to the original file.

Refreshing the primary repository replaces its scan and clears supplementary imports,
as before. Read the local folder, Jira issues and Slack messages again afterward, then
rebuild the overview. Switching the dropdown never performs that refresh.

## Read scope

The existing supported-text policy applies: at most 500 files, 256 KiB per file, 5 MiB
of content and 20,000 traversed entries per local snapshot. UTF-8 text is supported;
binary data and overlong lines are omitted. Coverage reports skipped files and limits.
Built-in exclusions cover common secret filenames, generated files, dependencies and
private tool directories. These rules are not a general secret detector. Custom
`.gitignore` patterns are not applied. Root-level `jira/` and `slack/` paths are reserved
by the index and are omitted from local reads.

Network paths, mapped network drives, drive roots, symbolic links and Windows junctions
are rejected or skipped. File reads stay inside the explicitly selected folder. Local
and GitHub files with the same relative filename remain distinct evidence; neither
silently overwrites the other. Conflicting evidence should be described with citations
to both sources. Retrieval chooses relevant excerpts within the existing context limit,
so connecting four sources does not mean every answer must cite all four.
