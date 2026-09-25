# Changelog

All notable changes to this project are documented in this file.
Versions follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## [0.3.0] - 2026-09-25
### Added
- **Initial implementation** of the IMAP email organizer (all SPEC deliverables):
  `organizer.py`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`,
  `.env.example`, `.gitignore`.
- **Recursive sender-domain grouping** (user's primary feature intent): a
  message from `ccmak@hko.gov.hk` is filed into `Auto/hk/gov/hko` (TLD-first
  nested tree, PSL-free — full domain reversed, no registered-domain
  heuristic). Controlled by new `DOMAIN_GROUPING` env var:
  `all` (default, file every message by domain + rules), `fallback`
  (domain only when no rule matches), `off` (rules-only flat folders).
- `LABEL_RULES` classification: `field:pattern` / `field:pattern:i`
  (case-insensitive). Fields: `from`, `to`, `subject`, `body`, `list-id`.
- CLI flags: `--dry-run`, `--list-folders`, `--test-connection`, `--rule`.
- Idempotency: skips messages already in the target folder (by `Message-ID`);
  messages without `Message-ID` are skipped to avoid duplicates.
- Non-destructive: `COPY`, or `STORE \Deleted` after confirmed copy when
  `ACTION=move`; never `EXPUNGE`, never mark-as-read.
- Expanded `README.md` with all SPEC-required sections (What it does, Infra,
  Quick start, Config reference, Rule syntax, Recursive domain grouping,
  Cron, Safety, Troubleshooting).

### Fixed (during verification)
- `--dry-run` no longer touches the server: previously it still issued
  `CREATE` (folder creation) and read-only `SELECT`/`SEARCH` for idempotency
  checks; now a dry run only logs `WOULD COPY` and issues no `CREATE`,
  `COPY`, or `STORE`. Caught by independent verification (segregation of
  duties) against the SPEC intent ("Print what would happen without touching
  the server").

## [0.2.0] - 2026-09-25
### Changed
- **Segregation of duties in the per-change workflow**: "verify" is now a
  distinct duty from "implement". The implementer must not self-attest the
  SPEC.md ACCEPTANCE CHECKLIST; verification must be re-run as a separate
  step/session/agent against the checklist. Plan→approval remains the human
  segregation point; implement↔verify is the agent segregation point.
- **Separate the frozen prompt from the living doc**: the verbatim build
  prompt has been extracted from `README.md` into `SPEC.md` (frozen, never
  edit). `README.md` is now a clean living project doc that points to
  `SPEC.md` and grows as the project is built — the original prompt can no
  longer be accidentally destroyed by future README edits.
- Updated `AGENTS.md` to reference `SPEC.md` as the source of truth (hard
  constraints, feature intent, acceptance checklist).

## [0.1.0] - 2026-09-25
### Added
- `AGENTS.md` — instruction file for OpenCode sessions: per-change workflow
  (plan → implement → changelog → commit → push to `dev-001`), branch flow
  (`dev-001` only; CI auto-cascades to `dev` → `main`), hard technical
  constraints (IMAP-only, no Google APIs, non-destructive, idempotent), and
  the user's recursive sender-domain grouping intent.
