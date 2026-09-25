# Gmail Label Organizer

A self-contained Python application that connects to an email account over
**IMAP**, scans the inbox, and organizes messages into folders (IMAP folders
serve as "labels"). Ships as a Docker project. **IMAP-only and
provider-agnostic** — works with any IMAP mailbox (Gmail via app password,
Fastmail, Proton Bridge, Dovecot, etc.). Non-destructive by default: it copies
or moves, never deletes, marks-as-read, or expunges.

> The original build prompt is preserved verbatim and frozen in
> [`SPEC.md`](./SPEC.md). This file is the **living project documentation** —
> it grows as the project is built out. Do not edit `SPEC.md`; update this
> README instead.

---

## Status

Not yet implemented. This README will be expanded with the sections required
by `SPEC.md` (What it does, Infra requirements, Quick start, Config reference,
Rule syntax, Cron example, Safety notes, Troubleshooting) as the code is
written. See `SPEC.md` for the authoritative requirements and acceptance
checklist, and `AGENTS.md` for the contribution workflow.
