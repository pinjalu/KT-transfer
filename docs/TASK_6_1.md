# Task 6.1: Jira requirements and comments

Completed 22 October 2026 for the selected project's visible text, within the documented
import limits. Jira reads retain descriptions and custom text fields under their actual
Jira labels, including acceptance criteria without a hardcoded field ID. Search requests
available fields and expanded names. Non-text custom values are not indexed.

Incomplete embedded comment lists are completed through Jira's GET comment endpoint, ordered
by creation time. A confirmed complete embedded page avoids extra requests. Missing totals,
limits and pagination gaps remain visible in coverage. Repeated comment IDs, inconsistent
offsets or totals, denied access and failed requests prevent publishing the new import;
the previous saved import remains until a successful read replaces it.

Long issue text becomes bounded searchable excerpts instead of cutting everything after
3,600 characters. Every excerpt cites its Jira issue. Word boundaries are retained where
possible; line positions refer to the flattened local text. Custom criteria and later comments
participate in the same content/access recheck as the description. Changed or newly hidden
saved text invalidates the old source before it can answer a question.

The import remains bounded: 300 issues, ten issue pages, 1,000 comments and twenty comment
pages per issue, and 200,000 text characters per issue. Coverage distinguishes issue counts
from excerpt counts and reports text/comments omitted by these limits. Rich-text links and
table boundaries are retained as text. Attachments, images and non-text custom fields are
outside this task. The separate Jira task-explanation screen remains task 6.2.

## Verification

- Full suite: **487 passed**. After the final excerpt line-position adjustment, all **38
  affected Jira and acceptance tests passed**. One existing Starlette/httpx warning.
- Cases cover comments after the first twenty, custom criteria, long descriptions,
  complete/unknown/partial pages, malformed pagination, endpoint/project boundaries,
  MCP excerpt pagination, and permission checks on later comments and description tails.
- Five Chrome checks passed with fixture Jira HTTP and the real app: coverage counts,
  reload persistence, custom-criteria retrieval, comment-26 retrieval and 900-pixel layout.
  Example-mode answers are deterministic; these checks do not measure model accuracy.
- Live real-MCP read: four issues, four excerpts and six custom text fields, complete within
  scope. All four content/access checks passed. The new comment endpoint accepted a read;
  the live project has zero comments, so multi-page coverage is fixture evidence.
- The isolated live check preserved the original 1,099 chunks and two imports. The idle app
  was then restarted on the same project and its selected Jira data refreshed, retaining
  GitHub/Slack content and those counts. The app is ready with knowledge revision 4.

Local evidence: `../../outputs/task-6-1-2026-10-22/`, including `tests.txt`, `tests-final.txt`,
`live-check.json`, `browser.json` and `app-active.json`. Private source text and databases are
not committed. No remote Jira content was changed.

API behavior was checked against Atlassian's official
[issue search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
and [comment pagination](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/)
references. Completeness means content visible to the connected account in the selected
scope at read time, within the limits above.
