# Changelog

All notable changes to this project are documented in this file.
Versions follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## [0.1.0] - 2026-09-25
### Added
- `AGENTS.md` — instruction file for OpenCode sessions: per-change workflow
  (plan → implement → changelog → commit → push to `dev-001`), branch flow
  (`dev-001` only; CI auto-cascades to `dev` → `main`), hard technical
  constraints (IMAP-only, no Google APIs, non-destructive, idempotent), and
  the user's recursive sender-domain grouping intent.
