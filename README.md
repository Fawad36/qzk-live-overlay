# QZK Live Overlay — Next Level

A legitimate, self-hosted remote text/overlay system for machines you own or are authorized to manage.

## What is included

- Central FastAPI server with persistent SQLite state.
- Admin dashboard for licenses, device HWID registration, and session creation.
- Browser control page with live text push.
- Browser display/overlay page.
- Windows agent with automatic machine fingerprint/HWID and a native desktop overlay.
- Laptop A + Laptop B can be bound to the same license/session while keeping distinct HWIDs.
- WebSocket live updates, reconnect/backoff, presence count, state persistence, input length limit.
- Automated HTTP + WebSocket integration tests.
- GitHub-ready PowerShell launcher.
- Railway/Render deployment templates.

## Important HWID behavior

A hardware ID is machine-specific. Laptop A and Laptop B should **not** have the same HWID. Register both HWIDs under the same license. The session token is what joins them to the same live state.

## Local server test

Windows PowerShell:

```powershell
$env:QZK_ADMIN_PASSWORD='use-a-long-password'
$env:QZK_TOKEN_SECRET='use-a-long-random-secret'
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/admin`.

1. Create a license.
2. Register Laptop A HWID and Laptop B HWID.
3. Generate a session.
4. Copy the **PRIMARY CONTROL LINK** into a browser.
5. Type text. Every connected agent in that session receives it.

The browser control page and the native agent communicate through the central server using WebSockets.

## Agent

Install Python 3 on each Windows laptop, then:

```powershell
py -m pip install -r requirements-agent.txt
py agent.py --server https://YOUR-SERVER --token YOUR_SESSION_TOKEN --label "Laptop A"
```

The agent automatically calculates a stable SHA-256 fingerprint from Windows machine identifiers when available. You can override it for testing with `QZK_HWID`.

## GitHub one-command launcher

Upload this repository to your own GitHub repository. GitHub serves raw repository files through `raw.githubusercontent.com`; keep the launcher and agent files in the expected path. GitHub documents raw file access and repository contents APIs. 

In `launcher.ps1`, or through environment variables, configure:

- `QZK_RAW_BASE` = raw GitHub folder containing `agent.py` and `requirements-agent.txt`.
- `QZK_SERVER` = your deployed FastAPI server URL.
- `QZK_TOKEN` = session token (or let the launcher prompt).

Then the same command can be used on each authorized laptop:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/launcher.ps1 | iex"
```

The command downloads the agent and requirements from your repository, installs the small agent dependency, and connects it to your central server.

## Production deployment

Do not use the default admin password. Set `QZK_ADMIN_PASSWORD` and `QZK_TOKEN_SECRET` as platform secrets.

SQLite needs persistent storage in production. If your hosting platform uses an ephemeral filesystem, attach a persistent volume or replace SQLite with a managed database before relying on it for long-term license state.

Use HTTPS in production so browser WebSockets become secure `wss://` connections.

## Security boundary

This project is for authorized remote display/control on systems you own or administer. It intentionally does not contain anti-capture, security-bypass, credential-stealing, stealth, DLL injection, or exam-protection bypass functionality.


## Laptop A/B connection
If the server runs on Laptop B and agent runs on Laptop A, do NOT use 127.0.0.1 on Laptop A. Use Laptop B's LAN IPv4, e.g. `http://192.168.1.10:9000`. On B run `ipconfig`; on A run `Test-NetConnection 192.168.1.10 -Port 9000`. Allow TCP 9000 in Windows Firewall if needed.
