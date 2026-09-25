# AGENTS.md

## Project status
No implementation exists yet. Source-of-truth split:
- **`SPEC.md`** — the original build prompt, **frozen**. Never edit; if requirements change, raise a new spec revision. This is the immutable reference (incl. the ACCEPTANCE CHECKLIST).
- **`README.md`** — the **living** project doc. All project details go here as the project is built. This is where implementation notes, recursive domain-grouping behavior, config tables, etc. are recorded.
- Spec target: a Python 3.12 / Docker, IMAP-only email organizer.

## Per-change workflow (mandatory, user-defined)
Every change to this project MUST follow this exact order:
1. **Plan** — propose the plan; wait for explicit user approval before implementing.
2. **Implement.**
3. **Verify (segregation of duties)** — the implementer must NOT self-attest the SPEC.md ACCEPTANCE CHECKLIST. Verification must be an independent duty: re-run it as a separate step (fresh OpenCode session/agent, or at minimum re-asserted independently against the checklist — not "I wrote it so it passes"). Plan→approval is the human segregation point; implement↔verify is the agent segregation point.
4. **Update `CHANGELOG.md`** with a `X.X.X` semantic-version entry.
5. **Commit** with a good subject + body (do NOT repeat the vague existing history like "commit"/"doc").
6. **Push to `dev-001`**, referencing the `X.X.X` version.

Do not skip/reorder steps unless the user explicitly says so.

## Git / branch flow
- Work on `dev-001` only. **Never push directly to `dev` or `main`.**
- `.github/workflows/auto-merge.yml` auto-cascades on push: `dev-001` → `dev` → `main`. Pushing to `dev-001` is how changes propagate to release branches.
- That auto-merge relies on the repo secret `GIT_PUSH_TOKEN` (fine-grained PAT, Contents read+write) + main-branch protection bypass — already configured upstream; don't disable.
- `.github/workflows/deploy_reactjs_page.yml` is **legacy/unrelated** (deploys a Vite/Node holding page to GitHub Pages). Not part of this Python project; don't wire the app to it.

## Hard technical constraints (from SPEC.md — do not violate)
- **IMAP over SSL only** (`imaplib` + `email` stdlib). Despite the repo name "gmail-label-organizer": NO Gmail API, NO Google OAuth, NO Google SDK, NO Google Cloud, NO Apps Script. Must stay provider-agnostic.
- **Only `python-dotenv`** beyond stdlib. No Django/SQLAlchemy/heavy frameworks.
- **Non-destructive**: never delete, mark-as-read, or expunge. Only `COPY`, or `STORE \Deleted` after a confirmed copy (when `ACTION=move`); never call `EXPUNGE`.
- **Idempotent**: a second run must not duplicate folders or re-file messages — skip messages already in the target folder (verify via `SEARCH` by `Message-ID`).
- **Single-file entrypoint** `organizer.py`. Exact deliverable set: `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `organizer.py`.
- **Config via `.env` env vars only** — no hardcoded credentials/hosts/rules. `.env` MUST be in `.gitignore`.
- Base image `python:3.12-slim`.

## User's feature intent (augments the README spec)
The user's actual goal is to **log in to the mailbox and group emails by sender's domain, recursively**. The SPEC's flat `LABEL_RULES` scheme is the baseline; satisfy the recursive domain-grouping intent. Record implementation details in `README.md`, not here.

## Verification
No test suite, lint, or typecheck is configured yet. Use the SPEC's ACCEPTANCE CHECKLIST as the done-definition:
- `docker compose build` succeeds.
- `docker compose run --rm organizer --test-connection` exits 0.
- `--dry-run` issues no `COPY`/`STORE`.
- Malformed `LABEL_RULES` JSON → clear error, not a traceback.
- Second run does not duplicate work.
- No Google API/OAuth references anywhere in the repo.
- `.env` is gitignored.
