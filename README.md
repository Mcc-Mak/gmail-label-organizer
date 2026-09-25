# Gmail Label Organizer
## Prompt: to build a self-contained Python application that connects to an email account over **IMAP**, scans the inbox, and organizes messages into folders (IMAP folders serve as "labels")
````
# OpenCode Instruction: Gmail Label Organizer (Python + Docker, IMAP-based)

## TASK

Build a self-contained Python application that connects to an email account over **IMAP**, scans the inbox, and organizes messages into folders (IMAP folders serve as "labels"). Ship it as a Docker project. **Do not use the Gmail API, Google OAuth, Google Cloud, or Google Apps Script.** Use only standard protocols (IMAP) so the tool works with any provider (Gmail via app password, Fastmail, Proton Bridge, Dovecot, etc.).

## DELIVERABLES (exact filenames)

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── organizer.py          # main entrypoint
```

## HARD CONSTRAINTS

- **Language/runtime**: Python 3.12 inside Docker (base image `python:3.12-slim`).
- **Email access**: IMAP over SSL only. Use `imaplib` + `email` from the standard library. Do **not** add `google-api-python-client`, `google-auth*`, or any Google SDK.
- **Dependencies**: only `python-dotenv` beyond stdlib. Do not add heavy frameworks (no Django, no SQLAlchemy).
- **Config**: everything configurable via environment variables loaded from `.env`. No hardcoded credentials, hosts, or rules.
- **Idempotency**: running twice must not duplicate work. Skip messages already in the target folder.
- **No destructive actions by default**: never delete, never mark-as-read, never expunge. Only copy/move to folders.

## .env.example

```env
# --- IMAP connection ---
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=you@example.com
IMAP_PASSWORD=app-password-here
IMAP_MAILBOX=INBOX

# --- Behavior ---
# "copy" leaves the message in INBOX; "move" removes it from INBOX.
ACTION=copy
# Max messages to scan per run (0 = unlimited).
MAX_MESSAGES=500
# Only scan messages newer than N days (0 = no limit).
SINCE_DAYS=30
# Print what would happen without touching the server.
DRY_RUN=false
# Folder name prefix for managed folders (e.g. "Auto/Newsletter").
FOLDER_PREFIX=Auto

# --- Classification rules ---
# JSON object: folder name -> list of match rules.
# A rule is a string "field:pattern" or "field:pattern:i" for case-insensitive.
# Supported fields: from, to, subject, body, list-id.
# Folder is created if missing. First matching folder wins; a message may
# match multiple folders and will be copied to each unless STOP_ON_FIRST=true.
LABEL_RULES={"newsletter":["from:newsletter@","subject:digest","list-id:newsletter"],"billing":["subject:invoice","subject:receipt","from:billing@"],"social":["from:linkedin.com","from:twitter.com"]}
STOP_ON_FIRST=false
```

## organizer.py — REQUIRED BEHAVIOR

Write a single-file script with these responsibilities, in this order:

1. **Load config** from `.env` via `python-dotenv`. Validate required vars (`IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`) and exit with a clear message if missing. Parse `LABEL_RULES` from JSON; fail loudly on malformed JSON.

2. **Connect** with `imaplib.IMAP4_SSL(host, port)`, `login(user, password)`, then `select(IMAP_MAILBOX, readonly=False)`. Wrap connection errors with a readable message (e.g. "Authentication failed — if using Gmail, generate an App Password: https://myaccount.google.com/apppasswords").

3. **Ensure folders exist** for every key in `LABEL_RULES`. Prepend `FOLDER_PREFIX` (e.g. `Auto/newsletter`). Use `IMAP4.list()` to check; `IMAP4.create()` if missing. Handle the "already exists" error gracefully.

4. **Fetch message metadata** using `IMAP4.search()`:
   - Build a criteria list: `['ALL']` or `['SINCE', <date>]` when `SINCE_DAYS > 0`.
   - `search(None, *criteria)` → UID list. Slice to `MAX_MESSAGES`.
   - For each UID, fetch headers with `fetch(uid, '(RFC822.HEADER)')` and parse via `email.message_from_bytes`.

5. **Classify**: for each parsed message, extract `From`, `To`, `Subject`, `List-Id` headers. For each rule, check `field:pattern` (case-insensitive substring by default; if the rule ends with `:i` force case-insensitive; otherwise case-sensitive). Record matched folders.

6. **Apply**:
   - If `DRY_RUN=true`: log `WOULD COPY uid=<n> → Auto/<folder>` and continue.
   - Otherwise use `IMAP4.uid('COPY', uid, folder)` to copy. If `ACTION=move`, follow with `IMAP4.uid('STORE', uid, '+FLAGS', '\\Deleted')` **only after confirming the copy succeeded**, and do **not** call `EXPUNGE` (let the server/user decide).
   - If `STOP_ON_FIRST=true`, break after the first match per message.

7. **Report**: at the end, log a summary table — total scanned, per-folder counts, errors.

8. **CLI flags** (via `argparse`, overriding env):
   - `--dry-run` — force dry run
   - `--list-folders` — print IMAP folders and exit
   - `--test-connection` — connect and disconnect, exit 0/1
   - `--rule <name>` — run only one rule by name

9. **Logging**: use `logging` with format `%(asctime)s [%(levelname)s] %(message)s`. Default level INFO; `LOG_LEVEL` env var overrides.

10. **Error handling**: any per-message failure must not abort the run — log a warning and continue. Always `logout()`/`close()` in a `finally` block.

## Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY organizer.py .
RUN useradd -m appuser
USER appuser
ENTRYPOINT ["python", "organizer.py"]
```

## docker-compose.yml

```yaml
services:
  organizer:
    build: .
    container_name: mail-organizer
    env_file: [.env]
    restart: "no"
```

## README.md — REQUIRED SECTIONS

1. **What it does** — one paragraph; emphasize IMAP-only, provider-agnostic, non-destructive.
2. **Infra requirements** — Docker 20.10+, Docker Compose v2, an IMAP-enabled mailbox. For Gmail specifically: enable 2FA and create an App Password (link). For self-hosted: note that the mailbox must allow IMAP.
3. **Quick start** — four commands:
   ```bash
   cp .env.example .env
   # edit .env
   docker compose build
   docker compose run --rm organizer --test-connection
   docker compose run --rm organizer --dry-run
   docker compose run --rm organizer
   ```
4. **Config reference** — a table of every env var with default and meaning.
5. **Rule syntax** — examples for `from:`, `subject:`, `list-id:`, case-sensitivity suffix `:i`.
6. **Cron example** — how to schedule it with host crontab or a `scheduler` service using `docker compose`.
7. **Safety notes** — dry-run first, copy vs move semantics, no deletes/expunge.
8. **Troubleshooting** — common IMAP login errors, Gmail App Password requirement, folder-not-found.

## ACCEPTANCE CHECKLIST

OpenCode must verify before declaring done:

- [ ] `docker compose build` succeeds with no warnings.
- [ ] `docker compose run --rm organizer --test-connection` returns exit code 0 against a real or mock IMAP server.
- [ ] `--dry-run` prints intended actions without issuing `COPY`/`STORE`.
- [ ] Malformed `LABEL_RULES` JSON produces a clear error, not a traceback.
- [ ] Running twice in a row does not duplicate folders or re-copy already-filed messages (skip if already in target — check via `SEARCH` in target folder by `Message-ID`).
- [ ] No reference to Google APIs, OAuth, or Apps Script anywhere in the repo.
- [ ] `.env` and any credentials are listed in `.gitignore`.

## OUT OF SCOPE

Do not implement: web UI, database, OAuth flows, SMTP sending, attachment processing, spam filtering, ML-based classification. Keep it a single-run batch tool.
````