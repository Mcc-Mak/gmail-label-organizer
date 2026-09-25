# Changelog

All notable changes to this project are documented in this file.
Versions follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

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
