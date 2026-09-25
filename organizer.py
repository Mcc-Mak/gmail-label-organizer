#!/usr/bin/env python3
"""Gmail Label Organizer — IMAP-only, provider-agnostic email organizer.

Groups messages into IMAP folders that act as labels. Primary behavior is
recursive sender-domain grouping (TLD-first tree, e.g. hko.gov.hk -> Auto/hk/gov/hko).
LABEL_RULES optionally augment. Non-destructive: copy/move only, never
delete/mark-read/expunge. Idempotent: skips messages already in the target.
"""

from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Iterable

from dotenv import load_dotenv

log = logging.getLogger("organizer")

REQUIRED_VARS = ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD")
SUPPORTED_FIELDS = ("from", "to", "subject", "body", "list-id")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class Config:
    """Resolved configuration loaded from .env (CLI flags override env)."""

    def __init__(self, args: argparse.Namespace) -> None:
        load_dotenv()

        self.imap_host = os.environ.get("IMAP_HOST", "").strip()
        self.imap_port = int(os.environ.get("IMAP_PORT", "993") or 993)
        self.imap_user = os.environ.get("IMAP_USER", "").strip()
        self.imap_password = os.environ.get("IMAP_PASSWORD", "").strip()
        self.imap_mailbox = os.environ.get("IMAP_MAILBOX", "INBOX").strip() or "INBOX"

        self.action = os.environ.get("ACTION", "copy").strip().lower() or "copy"
        if self.action not in ("copy", "move"):
            raise ConfigError(f"ACTION must be 'copy' or 'move', got: {self.action!r}")

        self.max_messages = int(os.environ.get("MAX_MESSAGES", "500") or 500)
        self.since_days = int(os.environ.get("SINCE_DAYS", "30") or 30)
        self.dry_run = _env_bool("DRY_RUN", default=False)
        self.folder_prefix = os.environ.get("FOLDER_PREFIX", "Auto").strip() or "Auto"
        self.stop_on_first = _env_bool("STOP_ON_FIRST", default=False)
        self.domain_grouping = os.environ.get("DOMAIN_GROUPING", "all").strip().lower() or "all"
        if self.domain_grouping not in ("all", "fallback", "off"):
            raise ConfigError(
                f"DOMAIN_GROUPING must be 'all', 'fallback', or 'off', got: {self.domain_grouping!r}"
            )

        self.label_rules = self._parse_label_rules(os.environ.get("LABEL_RULES", "{}") or "{}")

        self.log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"

        # CLI overrides
        if args.dry_run:
            self.dry_run = True
        if args.rule:
            if args.rule not in self.label_rules:
                raise ConfigError(f"--rule {args.rule!r} not found in LABEL_RULES")
            self.label_rules = {args.rule: self.label_rules[args.rule]}

        missing = [v for v in REQUIRED_VARS if not getattr(self, v.lower())]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in values."
            )

    @staticmethod
    def _parse_label_rules(raw: str) -> dict[str, list[str]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"LABEL_RULES is not valid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ConfigError("LABEL_RULES must be a JSON object: {folder: [rules]}")
        rules: dict[str, list[str]] = {}
        for folder, rlist in data.items():
            if not isinstance(folder, str) or not folder.strip():
                raise ConfigError("LABEL_RULES: every folder name must be a non-empty string")
            if not isinstance(rlist, list):
                raise ConfigError(f"LABEL_RULES[{folder!r}] must be a list of rule strings")
            parsed: list[str] = []
            for rule in rlist:
                if not isinstance(rule, str):
                    raise ConfigError(f"LABEL_RULES[{folder!r}] contains a non-string rule: {rule!r}")
                field = rule.split(":", 1)[0].lower()
                if field not in SUPPORTED_FIELDS:
                    raise ConfigError(
                        f"LABEL_RULES[{folder!r}]: unknown field {field!r} in rule {rule!r}. "
                        f"Supported fields: {', '.join(SUPPORTED_FIELDS)}"
                    )
                if len(rule.split(":", 1)) < 2 or not rule.split(":", 1)[1].rstrip(":i"):
                    raise ConfigError(
                        f"LABEL_RULES[{folder!r}]: rule {rule!r} has no pattern"
                    )
                parsed.append(rule)
            rules[folder.strip()] = parsed
        return rules


class ConfigError(Exception):
    """Raised for user-facing configuration problems (clean exit, no traceback)."""


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# IMAP connection
# --------------------------------------------------------------------------- #
class ImapSession:
    """Thin wrapper around imaplib.IMAP4_SSL with safe teardown."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.conn: imaplib.IMAP4_SSL | None = None
        self._separator = "/"
        self._created: set[str] = set()
        self._mid_cache: dict[str, set[str]] = {}

    def __enter__(self) -> "ImapSession":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def connect(self) -> None:
        cfg = self.cfg
        try:
            self.conn = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
            self.conn.login(cfg.imap_user, cfg.imap_password)
        except imaplib.IMAP4.error as exc:
            raise ConfigError(
                f"IMAP authentication/connection failed: {exc}. "
                "If using Gmail, generate an App Password: "
                "https://myaccount.google.com/apppasswords"
            ) from exc
        self.conn.select(cfg.imap_mailbox, readonly=False)
        self._detect_separator()

    def close(self) -> None:
        if self.conn is None:
            return
        try:
            typ, _ = self.conn.state  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if getattr(self.conn, "state", None) in ("SELECTED",):
                self.conn.close()
        except imaplib.IMAP4.error:
            pass
        try:
            self.conn.logout()
        except imaplib.IMAP4.error:
            pass
        self.conn = None

    def _detect_separator(self) -> None:
        assert self.conn is not None
        try:
            typ, data = self.conn.list()
            if typ == "OK":
                for item in data:
                    if not item:
                        continue
                    raw = item.decode() if isinstance(item, bytes) else str(item)
                    # LIST response: (\\HasNoChildren) "/" "INBOX"
                    if '"' in raw:
                        parts = raw.split('"')
                        for sep in ('"',):
                            for part in parts:
                                if part in ("/", ".", "\\", "-"):
                                    self._separator = part
                                    return
                    for sep in ("/", ".", "\\", "-"):
                        if f'"{sep}"' in raw:
                            self._separator = sep
                            return
        except imaplib.IMAP4.error:
            pass

    @property
    def separator(self) -> str:
        return self._separator

    # -- folder management -------------------------------------------------- #
    def folder_path(self, *parts: str) -> str:
        clean = [p.strip().strip("/") for p in parts if p and p.strip().strip("/")]
        return self._separator.join(clean)

    def ensure_folder(self, path: str) -> None:
        if not path or path in self._created:
            return
        assert self.conn is not None
        # Create level by level so nested trees (Auto/hk/gov/hko) work.
        levels = path.split(self._separator)
        built = ""
        for level in levels:
            built = level if not built else f"{built}{self._separator}{level}"
            if built in self._created:
                continue
            try:
                typ, _ = self.conn.create(built)
                if typ == "OK":
                    log.debug("created folder %s", built)
            except imaplib.IMAP4.error as exc:
                # "already exists" is expected and fine.
                log.debug("create(%s) -> %s (likely exists)", built, exc)
            self._created.add(built)

    # -- message id sets for idempotency ------------------------------------ #
    def message_ids_in(self, folder: str) -> set[str]:
        if folder in self._mid_cache:
            return self._mid_cache[folder]
        assert self.conn is not None
        result: set[str] = set()
        try:
            typ, _ = self.conn.select(folder, readonly=True)
            if typ != "OK":
                return result
            typ, data = self.conn.search(None, "ALL")
            if typ != "OK":
                return result
            uids = data[0].split() if data and data[0] else []
            for uid in uids:
                typ, fdata = self.conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
                if typ != "OK":
                    continue
                mid = _extract_message_id(fdata)
                if mid:
                    result.add(mid)
        except imaplib.IMAP4.error as exc:
            log.warning("could not enumerate %s for idempotency: %s", folder, exc)
        finally:
            try:
                self.conn.select(self.cfg.imap_mailbox, readonly=False)
            except imaplib.IMAP4.error:
                pass
        self._mid_cache[folder] = result
        return result

    # -- main scan ---------------------------------------------------------- #
    def search_uids(self) -> list[bytes]:
        assert self.conn is not None
        if self.cfg.since_days > 0:
            since = (date.today() - timedelta(days=self.cfg.since_days)).strftime("%d-%b-%Y")
            typ, data = self.conn.search(None, "SINCE", since)
        else:
            typ, data = self.conn.search(None, "ALL")
        if typ != "OK":
            raise ConfigError(f"IMAP SEARCH failed: {data}")
        uids = data[0].split() if data and data[0] else []
        if self.cfg.max_messages > 0:
            uids = uids[: self.cfg.max_messages]
        return uids

    def fetch_headers(self, uid: bytes) -> email.message.Message | None:
        assert self.conn is not None
        try:
            typ, data = self.conn.fetch(uid, "(RFC822.HEADER)")
        except imaplib.IMAP4.error as exc:
            log.warning("fetch failed for uid=%s: %s", uid.decode(errors="replace"), exc)
            return None
        if typ != "OK":
            return None
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                raw = part[1]
                if isinstance(raw, (bytes, bytearray)):
                    return email.message_from_bytes(raw)
        return None

    def copy_to(self, uid: bytes, folder: str) -> bool:
        assert self.conn is not None
        typ, _ = self.conn.uid("COPY", uid, folder)
        return typ == "OK"

    def mark_deleted(self, uid: bytes) -> bool:
        assert self.conn is not None
        typ, _ = self.conn.uid("STORE", uid, "+FLAGS", "\\Deleted")
        return typ == "OK"

    def list_folders(self) -> list[str]:
        assert self.conn is not None
        typ, data = self.conn.list()
        out: list[str] = []
        if typ != "OK":
            return out
        for item in data:
            if not item:
                continue
            raw = item.decode() if isinstance(item, bytes) else str(item)
            out.append(raw)
        return out


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def sender_domain(msg: email.message.Message) -> str | None:
    """Extract the registered sender domain (TLD-first tree root) from From."""
    from_raw = msg.get("From", "")
    if not from_raw:
        return None
    _, addr = email.utils.parseaddr(from_raw)
    if "@" not in addr:
        return None
    domain = addr.rsplit("@", 1)[-1].strip().lower()
    if not domain or domain.startswith("["):
        return None
    # strip any trailing bracketed IP / angle brackets
    domain = domain.strip("[]")
    if not domain or "." not in domain:
        return None
    return domain


def domain_tree_path(domain: str, prefix: str, sep: str) -> str:
    """Reverse the domain into a TLD-first nested folder path.

    hko.gov.hk -> Auto/hk/gov/hko (with '/'); prefix joined by sep.
    """
    labels = [lbl for lbl in domain.split(".") if lbl]
    reversed_labels = list(reversed(labels))
    parts = [prefix] + reversed_labels
    return sep.join(parts)


def classify_rules(msg: email.message.Message, rules: dict[str, list[str]], stop_on_first: bool) -> list[str]:
    matched: list[str] = []
    for folder, rlist in rules.items():
        for rule in rlist:
            if _rule_matches(msg, rule):
                matched.append(folder)
                if stop_on_first:
                    return matched
                break  # one match per folder is enough
    return matched


def _rule_matches(msg: email.message.Message, rule: str) -> bool:
    # rule forms: "field:pattern" or "field:pattern:i"
    force_ci = rule.endswith(":i")
    if force_ci:
        rule = rule[:-2]
    field, _, pattern = rule.partition(":")
    field = field.strip().lower()
    pattern = pattern
    if not pattern:
        return False
    if force_ci:
        pattern = pattern.lower()

    def norm(s: str) -> str:
        return s.lower() if force_ci else s

    if field == "from":
        return norm(pattern) in norm(msg.get("From", ""))
    if field == "to":
        return norm(pattern) in norm(msg.get("To", ""))
    if field == "subject":
        return norm(pattern) in norm(msg.get("Subject", ""))
    if field == "list-id":
        return norm(pattern) in norm(msg.get("List-Id", ""))
    if field == "body":
        # Only headers are fetched by design; body matching is best-effort off
        # the header payload (List-Id etc.). We do not fetch full body to keep
        # the run cheap and non-destructive; treat body rule as never matching
        # unless a body is already present in the parsed object.
        body = _safe_body(msg)
        return bool(body) and norm(pattern) in norm(body)
    return False


def _safe_body(msg: email.message.Message) -> str:
    try:
        payload = msg.get_payload(decode=True)
    except Exception:
        return ""
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


def _extract_message_id(fetch_data: object) -> str | None:
    """Pull Message-ID out of a fetch response (list of tuples/bytes)."""
    if not fetch_data:
        return None
    for part in fetch_data:
        if isinstance(part, tuple) and len(part) >= 2:
            raw = part[1]
        elif isinstance(part, (bytes, bytearray)):
            raw = bytes(part)
        else:
            continue
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        for line in text.splitlines():
            if line.lower().startswith("message-id:"):
                return line.split(":", 1)[1].strip().strip("<>").lower()
    return None


def message_id_of(msg: email.message.Message) -> str | None:
    raw = msg.get("Message-ID", "")
    if not raw:
        return None
    return raw.strip().strip("<>").lower() or None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(args: argparse.Namespace) -> int:
    try:
        cfg = Config(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.test_connection:
        return _cmd_test_connection(cfg)
    if args.list_folders:
        return _cmd_list_folders(cfg)

    return _cmd_organize(cfg)


def _cmd_test_connection(cfg: Config) -> int:
    log.info("Testing connection to %s:%s as %s", cfg.imap_host, cfg.imap_port, cfg.imap_user)
    try:
        with ImapSession(cfg) as sess:
            log.info("OK: connected, authenticated, and selected %s", cfg.imap_mailbox)
            return 0
    except ConfigError as exc:
        log.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - surface any connection failure cleanly
        log.error("Connection test failed: %s", exc)
        return 1


def _cmd_list_folders(cfg: Config) -> int:
    try:
        with ImapSession(cfg) as sess:
            for line in sess.list_folders():
                print(line)
            return 0
    except ConfigError as exc:
        log.error("%s", exc)
        return 1


def _cmd_organize(cfg: Config) -> int:
    stats = {"scanned": 0, "filed": 0, "skipped": 0, "errors": 0}
    per_folder: dict[str, int] = {}

    try:
        with ImapSession(cfg) as sess:
            uids = sess.search_uids()
            log.info("scanning %d message(s) in %s", len(uids), cfg.imap_mailbox)

            # Pre-create rule folders so the tree exists (skip in dry-run:
            # a dry run must not touch the server).
            if not cfg.dry_run:
                for folder in cfg.label_rules:
                    sess.ensure_folder(sess.folder_path(cfg.folder_prefix, folder))

            for uid in uids:
                stats["scanned"] += 1
                try:
                    msg = sess.fetch_headers(uid)
                    if msg is None:
                        stats["errors"] += 1
                        continue

                    mid = message_id_of(msg)
                    if not mid:
                        log.warning(
                            "uid=%s has no Message-ID header; skipping to avoid duplicates",
                            uid.decode(errors="replace"),
                        )
                        stats["skipped"] += 1
                        continue

                    targets = _resolve_targets(sess, cfg, msg)
                    if not targets:
                        stats["skipped"] += 1
                        continue

                    for target in targets:
                        if cfg.dry_run:
                            # Dry run must not touch the server: no CREATE,
                            # no SELECT/SEARCH. Just preview the would-be path.
                            log.info("WOULD COPY uid=%s -> %s", uid.decode(errors="replace"), target)
                            stats["filed"] += 1
                            per_folder[target] = per_folder.get(target, 0) + 1
                            continue

                        sess.ensure_folder(target)
                        if _already_filed(sess, target, mid):
                            log.debug("uid=%s already in %s; skip", uid.decode(errors="replace"), target)
                            stats["skipped"] += 1
                            continue

                        if sess.copy_to(uid, target):
                            log.info("COPY uid=%s -> %s", uid.decode(errors="replace"), target)
                            if cfg.action == "move":
                                if sess.mark_deleted(uid):
                                    log.info(
                                        "STORE uid=%s +FLAGS \\Deleted (move confirmed)",
                                        uid.decode(errors="replace"),
                                    )
                                else:
                                    log.warning(
                                        "uid=%s copied but STORE \\Deleted failed; "
                                        "message left in source",
                                        uid.decode(errors="replace"),
                                    )
                            stats["filed"] += 1
                            per_folder[target] = per_folder.get(target, 0) + 1
                        else:
                            log.error("COPY failed uid=%s -> %s", uid.decode(errors="replace"), target)
                            stats["errors"] += 1
                            continue
                except imaplib.IMAP4.error as exc:
                    log.warning("uid=%s: %s", uid.decode(errors="replace"), exc)
                    stats["errors"] += 1
                except Exception as exc:  # noqa: BLE001 - never abort the run
                    log.warning("uid=%s: unexpected error: %s", uid.decode(errors="replace"), exc)
                    stats["errors"] += 1
    except ConfigError as exc:
        log.error("%s", exc)
        return 1

    _report(stats, per_folder)
    return 0 if stats["errors"] == 0 else 1


def _resolve_targets(sess: ImapSession, cfg: Config, msg: email.message.Message) -> list[str]:
    """Decide which folders a message should be filed into (order matters)."""
    rule_folders = classify_rules(msg, cfg.label_rules, cfg.stop_on_first)
    rule_paths = [sess.folder_path(cfg.folder_prefix, f) for f in rule_folders]

    domain = sender_domain(msg)
    domain_path = domain_tree_path(domain, cfg.folder_prefix, sess.separator) if domain else None

    mode = cfg.domain_grouping
    if mode == "off":
        return rule_paths
    if mode == "fallback":
        if rule_paths:
            return rule_paths
        return [domain_path] if domain_path else []
    # mode == "all": domain is primary, rules augment.
    targets: list[str] = []
    if domain_path:
        targets.append(domain_path)
    targets.extend(p for p in rule_paths if p != domain_path)
    return targets


def _already_filed(sess: ImapSession, folder: str, mid: str) -> bool:
    return mid in sess.message_ids_in(folder)


def _report(stats: dict[str, int], per_folder: dict[str, int]) -> None:
    log.info("--- summary ---")
    log.info("scanned: %d", stats["scanned"])
    log.info("filed:   %d", stats["filed"])
    log.info("skipped: %d", stats["skipped"])
    log.info("errors:  %d", stats["errors"])
    if per_folder:
        log.info("per-folder:")
        for folder, count in sorted(per_folder.items()):
            log.info("  %-40s %d", folder, count)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="organizer",
        description="IMAP-only email organizer with recursive sender-domain grouping.",
    )
    p.add_argument("--dry-run", action="store_true", help="print actions only; no COPY/STORE")
    p.add_argument("--list-folders", action="store_true", help="print IMAP folders and exit")
    p.add_argument("--test-connection", action="store_true", help="connect+disconnect, exit 0/1")
    p.add_argument("--rule", metavar="NAME", help="run only one LABEL_RULES entry by name")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
