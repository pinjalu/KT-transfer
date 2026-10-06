# Run the first version in VS Code on Windows

You already have Python 3.10.9, Ollama and `qwen3:1.7b`. This guide starts from the downloaded ZIP. Keep the existing tester in its own folder; this project runs separately.

## 1. Extract and open the folder

Right-click the ZIP in File Explorer and select **Extract All**. In VS Code, use **File → Open Folder** and select the inner `project-knowledge-assistant` folder containing `README.md` and `requirements.txt`.

Open **Terminal → New Terminal**. Select PowerShell. Check that you are in the right folder:

```powershell
Get-Location
Get-ChildItem
python --version
```

You should see `requirements.txt`, the `pka` folder, and Python 3.10.9 or newer. These commands only show your location, files and Python version.

## 2. Create a private Python environment

```powershell
python -m venv .venv
```

This creates a `.venv` folder containing a separate Python environment for this application. The following commands use that environment's Python directly; you do not need to run an activation script or change PowerShell execution policy.

## 3. Install the libraries

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

The first command updates the installer. The second installs the pinned application libraries. The third checks for dependency conflicts. Internet access is needed for this step. Do not install the requirements of the repository you plan to scan: the assistant only reads its text.

## 4. Test the interface with built-in examples

```powershell
.\.venv\Scripts\python.exe -m pka --demo
```

Leave this terminal running. Open <http://127.0.0.1:8000> in your browser. Click **Start / refresh scan**. You should see **3 files read**, **1 skipped**, and **complete**. Ask **How does login work?**, expand a source and save feedback.

The yellow banner says **EXAMPLE MODE**. GitHub data and the answer are simulated. This checks installation, the browser interface, the actual local MCP connection and SQLite, but it does not measure the model's answers.

Return to the terminal and press **Ctrl+C** to stop example mode.

## 5. Create your local configuration

Run this only when you do not already have a `.env` file:

```powershell
Copy-Item .env.example .env
```

Open `.env` in VS Code. Keep `OLLAMA_MODEL=qwen3:1.7b`. You can enter your repository and branch here for the first launch, or save them in the browser. Once saved, the browser settings are authoritative.

For a **public repository**, leave `GITHUB_TOKEN=` empty. For a **private repository**, create a token in GitHub:

1. Open GitHub → your profile picture → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**.
2. Generate a new token and choose the appropriate resource owner.
3. Under **Repository access**, select **Only select repositories**, then select exactly the repository you want this assistant to read.
4. Under repository permissions, set **Contents → Read-only**. Keep the required metadata permission. Do not grant write permissions or additional repositories.
5. Choose an expiry and generate the token. An organisation may require administrator approval; wait for that approval if GitHub shows it as pending.
6. Paste the token only into your local `.env` file after `GITHUB_TOKEN=`. Save the file. Do not paste the token into a chat, a question, source code, a screenshot or a terminal command.

The token is loaded when the app starts, so restart the app after changing it. A token's name does not enforce permissions; make sure the actual permission selector says **Read-only**.

Official instructions: <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens>

## 6. Check Ollama

```powershell
ollama list
```

Confirm that `qwen3:1.7b` appears. You have already downloaded it; downloading it again is unnecessary. Open the Ollama desktop application if it is not running. Alternatively, in a separate terminal:

```powershell
ollama serve
```

If it says the address is already in use, Ollama may already be running. Keep the existing service. The assistant connects to `http://127.0.0.1:11434`. If the model is missing, use `ollama pull qwen3:1.7b`.

## 7. Start the real application

```powershell
.\.venv\Scripts\python.exe -m pka
```

Open <http://127.0.0.1:8000>. The example banner should be gone. Enter your repository. Pasting the address from your browser works, for example `https://github.com/my-team/my-project`, and so does typing `my-team/my-project`. Whatever you paste is shortened to `owner/repository` and the field shows that shortened form once saved. Then enter the exact branch name. These are examples, not repositories automatically authorised by the application.

Copy `.env.example` to `.env` before this step. If the scan stops saying the GitHub allowance cannot cover it, put a token on the `GITHUB_TOKEN=` line of `.env` and restart. On github.com go to Settings, Developer settings, Personal access tokens, Fine-grained tokens, Generate new token, select only the repository you want to scan, and set Repository permissions, Contents to Read-only. Grant nothing else. A public repository works without a token only while it has fewer than about 55 readable files, because the unauthenticated allowance is 60 requests per hour and each file costs one request.

Click **Save repository**, then **Start / refresh scan**. When anything misbehaves, open `data\logs\pka.log` first. It holds one line per event for the whole session, so you can follow a problem from startup to the failing step in order. Lines marked ERROR are the ones to read. If the scan ends as failed with every file skipped, open the newest file in `data\logs\` and read the "Counts by reason" block; that names the reason for each file. A repository that has committed its `.venv` or `node_modules` folder is the usual cause, and the cleanest cure is to stop tracking that folder in the repository itself. Wait for the scan to finish. Check the files read, skips, failures, commit and last successful scan time. Expand **Files read, skipped and failed** for details. A private repository returning 404 can mean the token lacks access; it does not necessarily mean the repository does not exist.

## 8. Ask one useful question

Try a feature that you know exists in your repository:

- How does login work?
- How do I set up and start the project?
- What happens when a customer places an order?
- Where are database models defined?

A filename is not required. Search uses project words, paths and symbols; it can still miss unfamiliar terminology. If the retrieved sources are poor, try a related word and record **insufficient** or **partly sufficient** for source sufficiency.

The first answer can be slow while Ollama loads the model. The app shows elapsed time. An i5 CPU and 16 GB RAM should be a reasonable starting point for the small model and bounded index, but performance on your machine has not been measured. Keep other memory-heavy applications closed if needed.

Expand each source to inspect the exact excerpt. GitHub links open the scanned commit, not whichever code happens to be on the branch now. Correct source IDs do not guarantee a correct explanation: compare the explanation with the code and your own knowledge.

## 9. Check your real connection if something fails

While the app runs, open another VS Code terminal:

```powershell
.\.venv\Scripts\python.exe -m pka.doctor
```

This reports Python, SQLite full-text search, whether the Ollama model is available, and whether GitHub permits reading the saved repository. It does not print your token.

| Message | What to do |
|---|---|
| Repository, branch or commit unavailable | Check spelling, branch, token expiry, selected repository and organisation approval. |
| GitHub rate limit reached | Wait for the reported interval and scan again. A restricted read-only token increases the usual public unauthenticated allowance. |
| Branch changed | Refresh the scan; the application will not use old excerpts for a new answer. |
| No searchable text | Inspect skipped files. The repository may contain unsupported formats or files beyond the configured limits. |
| Ollama unavailable / timed out | Start Ollama, confirm the model name and try a narrower question. Retrieved sources remain available. |
| Invalid answer / unknown source citation | The model's answer was withheld. Inspect the actual sources and ask a smaller question. |
| Another operation in progress | Wait for it to finish, or cancel the scan. Cancellation takes effect after the current network request. |
| Port 8000 already used | Start with `--port 8001` and open `http://127.0.0.1:8001`. |
| MCP failed | Restart the app; run the tests below. Confirm VS Code is using this project's `.venv`. |

A corporate proxy is not configured in this first version; the GitHub adapter deliberately ignores proxy environment variables. If your network requires a proxy, the connector needs an explicitly reviewed proxy setting before live use. Do not disable TLS verification.

## 10. Run the included checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_demo.py
```

Tests use fixtures and simulated network/model responses. The smoke check launches a real local web server and MCP subprocess using example data. Your own GitHub scan and an answer from your own Ollama service are separate live acceptance checks.

For your first live evaluation, ask five questions whose answers you can verify. Record answer quality and source sufficiency separately. Include one question about something the repository does not document; the assistant should expose that gap. No model-generated percentage is used as measured accuracy.

## 11. Stop and restart

Press **Ctrl+C** in the application terminal. Start again with:

```powershell
.\.venv\Scripts\python.exe -m pka
```

Your settings and usable scan remain in `data/index.sqlite3`. The next question still checks current GitHub access and branch freshness. Refresh manually after code changes. Do not publish this local service or share its database. Multi-user authentication and source permission isolation are planned prerequisites, not implemented features.
