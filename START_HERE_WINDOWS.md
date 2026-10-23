# Run KT Assistant on Windows

This guide describes the current local prototype and React interface. The original interface
remains available at /legacy. Current verification and remaining acceptance gates are recorded
in [task 5.8](docs/TASK_5_8.md).

## Install and start

Open the inner project-knowledge-assistant folder in VS Code. It contains requirements.txt,
frontend/ and pka/. Run these commands in its PowerShell terminal:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Python 3.10 or newer is required. Reuse an existing working .venv. Activation is optional;
the commands call its Python directly. Do not install or run the analyzed project's dependencies.

The built interface is included under pka/static/ui/. Node is needed only to rebuild after
frontend changes: run npm ci and npm run build inside frontend/, then return to the project root.

## Try the example

```powershell
.\.venv\Scripts\python.exe -m pka --demo
```

Open <http://127.0.0.1:8000/connections>. On first use, open the setup-code file shown in the
startup terminal, paste its one-time code into the form, and choose an owner username and
15–128-character password. The code file disappears after account creation. Live mode and
example mode have separate accounts. Then click **Refresh repository**. Expect three files
read and one policy exclusion. Open **Ask assistant** and ask "How does login work?".
Choose **Developer** to see excerpts. Answer correctness and source sufficiency have separate
feedback controls. Build **Project overview**, then inspect **Architecture**.

Example mode labels its data and simulates answers. It exercises HTTP, MCP and storage,
not live accounts or model quality. Its database is separate. Stop it with Ctrl+C before
starting live mode on the same port.

## Configure live sources

Create .env only if it does not already exist:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

Edit this local file in VS Code. Keep credentials out of chat, source control and screenshots.

| Source | Credentials | Selection in Connections |
|---|---|---|
| GitHub | GITHUB_TOKEN, restricted to the intended repository with Contents read-only | Repository and branch |
| Jira | **Update Jira credentials**: site URL, Atlassian email and API token; or JIRA_SITE, JIRA_EMAIL and JIRA_API_TOKEN in .env | One project, then **Read issues** |
| Slack | SLACK_USER_TOKEN; alternatively OAuth with SLACK_CLIENT_ID and SLACK_CLIENT_SECRET through **Connect Slack** | Choose channels, **Save channels**, then **Read messages** |

The Slack user-token reader supports selected public/private channels. The bot-token reader
is not implemented; direct messages are not imported. OAuth needs the exact redirect URL
configured in the Slack app. Message permalinks require a saved workspace name; when absent,
messages can still be read but no link is fabricated.

Use the providers' official token instructions:
[GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
and [Atlassian](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/).
Choose only the reading permissions needed by the selected sources.

## Run the live app

Run ollama list and confirm the model named in OLLAMA_MODEL exists (default qwen3:1.7b).
Open Ollama or run ollama serve if it is not already listening on 127.0.0.1:11434.
Do not start another instance when the existing one is healthy.

```powershell
.\.venv\Scripts\python.exe -m pka
```

Create the live owner account when prompted, or sign in to the existing account. The username
in the top bar opens password and session controls. Password recovery is local:
`.\.venv\Scripts\python.exe -m pka --reset-password` prompts for a new password without echoing it
and signs out all sessions. Use an interactive terminal; do not put passwords in command arguments.

On Connections, enter owner/repository or a GitHub URL and the branch, then click
**Save and read files**. On subsequent starts, **Use it again** fills the previous selection;
**Save and read files** reconnects to its usable snapshot without rereading it.
The app requires a project selection in each run.

Wait for the repository scan before importing Jira and Slack. Check **Import coverage** for
each source. Expand **Coverage details and limits** for skipped files, missing comments,
failed channels or missing replies. Credentials being present does not prove an import worked.
Older imports can show **Coverage unknown** until another read records coverage.

## Refresh and background work

**Refresh repository** rereads code and clears saved Jira/Slack content and derived answers.
Then use **Read issues**, **Read messages**, and **Build overview**. Reading an external source
also clears prior answers and the overview.

Scans, imports and overview builds continue during page navigation and reloads. Their shared
banner offers **Cancel job**, which waits for the current connector/model request to reach a
safe checkpoint. **Retry job** starts a fresh attempt after failure, cancellation, partial
completion or interruption; it does not resume halfway through or bypass import limits.
After app restart, unfinished jobs are Interrupted and wait for explicit retry.

## Current screens and limits

Home, Connections, Project overview, Ask assistant and Architecture have working views.
Feature explorer, Jira tasks, Team decisions, Troubleshooting and Settings are marked as not
built. Importing Jira/Slack does not implement those dedicated analysis screens. Model settings
currently live in .env. Multi-user access control is not implemented.

Inspect citations before accepting claims. Valid links and passing phrase checks do not
establish accuracy. See [task 5.2](docs/TASK_5_2.md) for the separate human review workflow.

## Verify and troubleshoot

```powershell
.\.venv\Scripts\python.exe -m pka.doctor
.\.venv\Scripts\python.exe -m pka.acceptance --output data/acceptance/connections.json
.\.venv\Scripts\python.exe -m pka.access_check --output data/acceptance/access.json
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke_demo.py
```

Connection acceptance makes scoped live reads without replacing the saved index. Access
verification uses a disposable copy. The smoke check uses temporary fixture data and cleans
up its own server process tree. None of these commands supplies human answer ratings.

| Symptom | Next action |
|---|---|
| Repository/branch unavailable | Check spelling, token access, expiry and organization approval. A private repository may return 404 when access is denied. |
| Rate limit | Wait for the reported interval and review credentials before retrying. |
| Branch/source changed | Read that source again, inspect coverage and rebuild the overview. |
| Empty or partial import | Expand coverage details; inspect Import history for repository file reasons. |
| Ollama unavailable/timed out | Check service and model. A model request can wait up to 180 seconds. |
| Another task running | Wait or use Cancel job. |
| Port occupied | Use --port 8001, or stop the existing app you own. |
| MCP failure | Inspect data/logs/pka.log, restart and run the smoke check. |

Use python -m pka.logs --last-ask for the latest diagnostic trace. Tokens and excerpt/answer
text are omitted; question text is off unless explicitly enabled. A corporate proxy is not
configured. Do not disable TLS verification.

## Stop and resume

Press Ctrl+C in the app terminal. Settings and knowledge remain in data/index.sqlite3.
Start with the same command and reconnect to the saved project. Keep this single-user service
on localhost; do not publish it or share its unencrypted database and credentials.
