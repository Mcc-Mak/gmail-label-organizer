# Gmail Label Organizer

A self-contained Python application that connects to an email account over
**IMAP**, scans the inbox, and organizes messages into IMAP folders (which act
as "labels"). Ships as a Docker project. **IMAP-only and provider-agnostic** —
works with any IMAP mailbox (Gmail via app password, Fastmail, Proton Bridge,
Dovecot, etc.). **Non-destructive by default**: it copies or moves, never
deletes, marks-as-read, or expunges.

The headline behavior is **recursive sender-domain grouping**: a message from
`user@hko.gov.hk` is filed into `Auto/hk/gov/hko` — `hko` nested inside `gov`
nested inside `hk`. Optional `LABEL_RULES` augment (or replace) the domain
tree with explicit pattern matches.

> The original build prompt is preserved verbatim and frozen in
> [`SPEC.md`](./SPEC.md). This file is the **living project documentation** —
> it grows as the project is built out. Do not edit `SPEC.md`; update this
> README instead. See [`AGENTS.md`](./AGENTS.md) for the contribution workflow.

---

## What it does

On each run the organizer:

1. Connects to an IMAP server over SSL (`imaplib.IMAP4_SSL`).
2. Selects the configured mailbox (default `INBOX`).
3. Searches for messages (optionally limited by `SINCE_DAYS` and `MAX_MESSAGES`).
4. For each message, derives one or more target folders:
   - **Domain tree (primary, when `DOMAIN_GROUPING=all`):** the sender's domain
     is split on `.` and reversed into a TLD-first nested folder path under
     `FOLDER_PREFIX`. Example: `ccmak@hko.gov.hk` → `Auto/hk/gov/hko`
     (3 levels: `hko` in `gov` in `hk`).
   - **LABEL_RULES (optional):** explicit `field:pattern` rules, filed in
     addition to the domain tree (or instead of, per `DOMAIN_GROUPING`).
5. Ensures each target folder exists (creating parent levels as needed).
6. **Idempotency check:** skips messages already present in the target folder
   (by `Message-ID` header) — a second run does not duplicate work.
7. Copies (or moves, when `ACTION=move`) the message. Move = copy + flag
   `\Deleted` only after a confirmed copy; **never** `EXPUNGE`.
8. Logs a per-run summary.

## Infra requirements

- **Docker** 20.10+
- **Docker Compose** v2
- An **IMAP-enabled** mailbox reachable over SSL (port 993).
  - **Gmail specifically:** enable 2FA and create an App Password at
    <https://myaccount.google.com/apppasswords> — regular passwords are
    rejected.
  - **Self-hosted (Dovecot, Proton Bridge, etc.):** confirm IMAP is enabled
    and that your network can reach the IMAP port.

## Quick start

```bash
cp .env.example .env
# edit .env  (IMAP_HOST, IMAP_USER, IMAP_PASSWORD at minimum)
docker compose build
docker compose run --rm organizer --test-connection   # sanity check
docker compose run --rm organizer --dry-run            # preview, no changes
docker compose run --rm organizer                      # actually run
```

## Config reference

All configuration is via environment variables loaded from `.env`. No
credentials or rules are hardcoded.

| Variable           | Default     | Meaning |
| ------------------ | ----------- | ------- |
| `IMAP_HOST`        | —           | IMAP server hostname (e.g. `imap.gmail.com`). **Required.** |
| `IMAP_PORT`        | `993`       | IMAP-over-SSL port. |
| `IMAP_USER`        | —           | Login username. **Required.** |
| `IMAP_PASSWORD`    | —           | Login password / app password. **Required.** |
| `IMAP_MAILBOX`     | `INBOX`     | Mailbox to scan. |
| `ACTION`           | `copy`      | `copy` leaves the message in the source; `move` flags it `\Deleted` after a confirmed copy. Never expunges. |
| `MAX_MESSAGES`     | `500`       | Max messages to scan per run. `0` = unlimited. |
| `SINCE_DAYS`       | `30`        | Only scan messages newer than N days. `0` = no limit. |
| `DRY_RUN`          | `false`     | If true, log intended actions only — no `COPY`/`STORE`. |
| `FOLDER_PREFIX`    | `Auto`      | Root for all managed folders (e.g. `Auto/newsletter`). |
| `DOMAIN_GROUPING`  | `all`       | `all` = file every message by sender domain tree (+ rules); `fallback` = by domain only when no rule matched; `off` = rules only (flat folders). |
| `LABEL_RULES`      | `{}`        | JSON object: `{folder: [rules]}`. See *Rule syntax* below. |
| `STOP_ON_FIRST`    | `false`     | If true, stop after the first matching rule per message (affects only the rules portion, not domain grouping). |
| `LOG_LEVEL`        | `INFO`      | Logging level (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |

### CLI flags (override env per run)

| Flag                | Effect |
| ------------------- | ------ |
| `--dry-run`         | Force dry run for this run. |
| `--list-folders`    | Print IMAP folders and exit. |
| `--test-connection` | Connect + authenticate + select, then exit 0/1. |
| `--rule <name>`     | Run only one `LABEL_RULES` entry by name. |

## Rule syntax

`LABEL_RULES` is a JSON object mapping a folder name to a list of rule
strings. A rule has the form `field:pattern`, or `field:pattern:i` for
case-insensitive matching. Default (no `:i`) is **case-sensitive substring**.

Supported fields: `from`, `to`, `subject`, `body`, `list-id`.

```json
{
  "newsletter": ["from:newsletter@", "subject:digest", "list-id:newsletter"],
  "billing":    ["subject:invoice", "subject:receipt", "from:billing@"],
  "social":     ["from:linkedin.com", "from:twitter.com:i"]
}
```

- A message may match multiple rule folders; it is copied to each unless
  `STOP_ON_FIRST=true`.
- Folders are created (under `FOLDER_PREFIX`) if missing.
- `body` matching is best-effort: the run fetches headers only (cheap,
  non-destructive), so `body:` rules only match when payload is present in
  the parsed header object. Prefer `from`/`subject`/`list-id` where possible.

## Recursive sender-domain grouping

This is the project's headline feature (per `AGENTS.md` user intent). When
`DOMAIN_GROUPING` is `all` or `fallback`, each message's sender domain is
turned into a **TLD-first nested IMAP folder tree** under `FOLDER_PREFIX`.

### How it works

The sender's email domain is split on `.` and the labels are reversed, so the
top-level domain becomes the first nesting level and the host label becomes
the leaf.

| Sender                | Domain tree folder       |
| --------------------- | ------------------------ |
| `ccmak@hko.gov.hk`    | `Auto/hk/gov/hko`        |
| `me@corp.example.com` | `Auto/com/example/corp`  |
| `news@github.com`     | `Auto/com/github`        |
| `bot@svc.io`          | `Auto/io/svc`            |

The example from the project intent: `ccmak@hko.gov.hk` → `Auto/hk/gov/hko`
(3 in 2 in 1) — shared parents auto-merge, so `user1@hko.gov.hk` and
`user2@hko.gov.hk` both land under the same `Auto/hk/gov/hko` folder, and a
sender from `gov.hk` itself would land at `Auto/hk/gov`.

This is **PSL-free** (no public-suffix-list dependency — only `python-dotenv`
beyond stdlib is allowed): it reverses the *full* domain, so the tree is
deterministic and never mis-splits `co.uk`-style suffixes.

### Interaction with `LABEL_RULES`

| `DOMAIN_GROUPING` | Domain tree folder? | Rule folders? |
| ----------------- | ------------------- | ------------- |
| `all` (default)   | Yes, for every message with a domain | Yes, in addition (duplicates de-duped) |
| `fallback`        | Only if no rule matched | Yes |
| `off`             | No                  | Yes (flat folders — original spec baseline) |

## Cron example

The tool is a single-run batch job. Schedule it with the host crontab, e.g.
every hour at :05:

```cron
# m h  dom mon dow  command
5  *  *  *  *  cd /path/to/gmail-label-organizer && docker compose run --rm organizer >> /var/log/mail-organizer.log 2>&1
```

Alternatively, add a `scheduler` service to `docker-compose.yml` that sleeps
and re-invokes `organizer` (left to the operator; not required by the spec).

## Safety notes

- **Dry-run first.** Always run `--dry-run` against a new config to preview
  actions; it issues no `COPY`/`STORE`.
- **Copy vs move.** `ACTION=copy` (default) leaves messages in the source
  mailbox. `ACTION=move` flags the copied message `\Deleted` *only after a
  confirmed copy* — and the tool **never calls `EXPUNGE`**, so the original
  remains recoverable until your client/server expunges.
- **Idempotent.** A second run skips messages already present in each target
  folder (matched by `Message-ID`). Re-running is safe and produces no
  duplicates.
- **No deletes / no mark-as-read / no expunge.** Ever.
- **Messages without a `Message-ID` header** are skipped (warned) rather than
  risk duplicate filing.

## Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| `Authentication failed` with Gmail | Gmail requires 2FA + an App Password. Generate one at <https://myaccount.google.com/apppasswords>. |
| `Application-specific password required` | Same as above — you're using your account password instead of an App Password. |
| `folder-not-found` / create fails | Some providers disallow creating certain top-level folders. Ensure `FOLDER_PREFIX` doesn't collide with a reserved name; check `--list-folders` output. |
| Duplicate folders / wrong separator | The tool auto-detects the server's hierarchy separator (`/`, `.`, etc.). If detection fails, confirm the mailbox supports `LIST`. |
| Domain tree not created | Set `DOMAIN_GROUPING=all` (or `fallback`). With `off`, only flat `LABEL_RULES` folders are used. |
| `body:` rules never match | The run fetches headers only; prefer `from`/`subject`/`list-id`. See *Rule syntax*. |
| Second run re-files messages | Ensure messages carry a `Message-ID` header; messages without one are skipped to avoid duplicates. |

---

See [`SPEC.md`](./SPEC.md) for the frozen original requirements and acceptance
checklist, and [`AGENTS.md`](./AGENTS.md) for the per-change workflow.
