"""Opt-in zsh entrypoints, independent of native instruction files and corpus content."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import time


START = b"# >>> agent-bios shell connection >>>\n"
END = b"# <<< agent-bios shell connection <<<\n"
SCRIPT_HEADER = b"# agent-bios optional shell connection; managed by agent-bios shell\n"


class ShellIntegrationError(RuntimeError):
    pass


class ShellIntegration:
    def __init__(self, environ=None, source_root=None):
        self.env = dict(os.environ if environ is None else environ)
        self.home = Path(self.env.get("HOME", str(Path.home()))).expanduser().absolute()
        self.zdotdir = Path(self.env.get("ZDOTDIR") or str(self.home)).expanduser().absolute()
        self.state = Path(self.env.get("AGENT_BIOS_STATE_DIR", str(self.home / ".local/share/agent-bios"))).expanduser().absolute()
        self.startup = self.zdotdir / ".zshrc"
        self.script = self.home / ".config/agent-launch/shell.zsh"
        self.receipt = self.state / "runtime/shell-connection.json"
        self.source = Path(source_root) if source_root else Path(__file__).resolve().parent.parent

    @staticmethod
    def _safe_ancestors(path):
        import sys
        compose = str(Path(__file__).resolve().parent.parent / "compose")
        if compose not in sys.path:
            sys.path.insert(0, compose)
        from corpus_transaction import reject_symlink_ancestors, TransactionError
        try:
            reject_symlink_ancestors(path)
        except TransactionError as exc:
            raise ShellIntegrationError(str(exc)) from exc

    @staticmethod
    def _safe(path):
        ShellIntegration._safe_ancestors(path)
        if path.exists() and not path.is_file():
            raise ShellIntegrationError(f"shell connection target is not a regular file: {path}")

    def _read(self, path):
        self._safe(path)
        return path.read_bytes() if path.exists() else None

    def _record(self, raw):
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ShellIntegrationError(f"invalid shell connection record: {self.receipt}") from exc
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("startup") != str(self.startup)
                or value.get("script") != str(self.script)
                or not isinstance(value.get("startup_existed"), bool)
                or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", "")))):
            raise ShellIntegrationError(f"shell connection record does not match HOME/ZDOTDIR: {self.receipt}")
        return value

    def _block(self):
        path = shlex.quote(str(self.script))
        return START + f"[ -r {path} ] && source {path}\n".encode() + END

    def _strip(self, raw):
        body = raw or b""
        starts, ends = body.count(START.rstrip(b"\n")), body.count(END.rstrip(b"\n"))
        if not starts and not ends:
            return body, False
        block = self._block()
        if starts != 1 or ends != 1 or body.count(block) != 1:
            raise ShellIntegrationError(f"shell connection block was edited; preserve and reconcile it: {self.startup}")
        return body.replace(block, b"", 1), True

    def _script_body(self):
        source = self.source / "launch/agent-launch.zsh"
        body = self._read(source)
        if body is None:
            raise ShellIntegrationError(f"shell connection source missing: {source}")
        return SCRIPT_HEADER + (
            f"typeset -g _agent_launch_private_connection={shlex.quote(str(self.script))}\n").encode() + body

    def has_connection(self):
        """Discover interrupted opt-ins without inspecting an ordinary user's rc.

        A header is only a reason to inspect: plan still requires exact managed
        bytes or a valid receipt hash before modifying any discovered script.
        """
        if self.receipt.exists() or self.receipt.is_symlink():
            return True
        if not self.script.is_file():
            return False
        try:
            self._safe(self.script)
        except ShellIntegrationError:
            # Without a receipt this is not evidence of our ownership. Leave a
            # foreign symlink/directory alone; explicit shell actions still refuse it.
            return False
        current = self._read(self.script)
        return current is not None and current.startswith(SCRIPT_HEADER)

    def plan(self, action, *, installing=False):
        if action not in {"restore", "remove", "status"}:
            raise ShellIntegrationError(f"unknown shell connection action: {action}")
        before = {path: self._read(path) for path in (self.startup, self.script, self.receipt)}
        record = self._record(before[self.receipt])
        remaining, connected = self._strip(before[self.startup])
        expected = self._script_body()
        current = before[self.script]
        if current is not None and current != expected and (
                record is None or hashlib.sha256(current).hexdigest() != record["sha256"]):
            raise ShellIntegrationError(f"shell connection will not replace an unowned or edited file: {self.script}")
        launcher = self.home / ".local/bin/agent-launch"
        try:
            self._safe(launcher)
            launcher_ready = launcher.is_file() and os.access(launcher, os.X_OK)
        except ShellIntegrationError:
            launcher_ready = False
        active = connected and current is not None and record is not None and launcher_ready
        needs_action = []
        if not active and (connected or current is not None or record is not None):
            needs_action.append("shell connection is incomplete; run agent-bios shell restore or remove")
        if action == "restore":
            installed = self._read(self.state / "runtime/private-install.json")
            try:
                private = json.loads(installed) if installed is not None else {}
            except (ValueError, UnicodeError) as exc:
                raise ShellIntegrationError("private installation record is invalid; run agent-bios verify") from exc
            if not installing and (not launcher_ready
                    or not isinstance(private, dict) or private.get("mode") != "private-session-scoped"
                    or not isinstance(private.get("launcher"), dict)
                    or private["launcher"].get("path") != str(launcher)):
                raise ShellIntegrationError("restore needs a private installation; run agent-bios install or migrate first")
            receipt = {"schema_version": 1, "startup": str(self.startup), "script": str(self.script),
                       "sha256": hashlib.sha256(expected).hexdigest(),
                       "startup_existed": record["startup_existed"] if record else before[self.startup] is not None}
            receipt_body = (json.dumps(receipt, sort_keys=True) + "\n").encode()
            # Persist first-opt-in ownership before publishing the script/hook.
            # On updates, retain the old hash until the new script is published:
            # either old recorded bytes or current source bytes remain recoverable.
            after = {self.receipt: receipt_body} if record is None else {}
            after.update({self.script: expected,
                          self.startup: before[self.startup] if connected else self._block() + remaining,
                          self.receipt: receipt_body})
        elif action == "remove":
            after = {self.startup: remaining if before[self.startup] is not None else None,
                     self.script: None, self.receipt: None}
            if record and not record["startup_existed"] and not remaining:
                after[self.startup] = None
        else:
            after = {}
        changes = [{"path": path, "before": before[path], "after": body,
                    "mode": path.stat().st_mode & 0o777 if before[path] is not None else 0o600}
                   for path, body in after.items() if before[path] != body]
        return {"enabled": active, "startup_path": str(self.startup), "shell_path": str(self.script),
                "needs_action": needs_action, "changes": changes}

    def status(self):
        try:
            result = self.plan("status")
            result.pop("changes")
            return result
        except (ShellIntegrationError, OSError) as exc:
            return {"enabled": False, "startup_path": str(self.startup), "shell_path": str(self.script),
                    "needs_action": [str(exc)]}

    @staticmethod
    def _write(path, body, mode):
        if body is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(name, mode)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def apply(self, action, dry_run=False):
        # One writer lock is shared with install/reset/migrate. Imports stay lazy so
        # status and help do not create state or require an installed corpus.
        import sys
        compose = str(Path(__file__).resolve().parent.parent / "compose")
        if compose not in sys.path:
            sys.path.insert(0, compose)
        from corpus_transaction import transaction_lock, guard_pending
        lock = contextlib.nullcontext() if dry_run else transaction_lock(self.state)
        with lock:
            guard_pending(self.state)
            plan = self.plan(action)
            changes = plan.pop("changes")
            result = {**plan, "preview": dry_run, "action": action,
                      "changed_paths": [str(row["path"]) for row in changes]}
            if dry_run or not changes:
                return result
            for row in changes:
                if self._read(row["path"]) != row["before"]:
                    raise ShellIntegrationError(f"shell file changed during planning: {row['path']}")
            backups = self.state / "runtime/shell-backups"
            self._safe_ancestors(backups)
            backups.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = Path(tempfile.mkdtemp(prefix=f"{int(time.time())}-", dir=backups))
            metadata = []
            for index, row in enumerate(changes):
                saved = backup / str(index)
                if row["before"] is not None:
                    self._write(saved, row["before"], 0o600)
                    if saved.read_bytes() != row["before"]:
                        raise ShellIntegrationError(f"shell backup did not verify: {saved}")
                metadata.append({"path": str(row["path"]), "existed": row["before"] is not None,
                                 "file": str(index), "mode": row["mode"]})
            self._write(backup / "paths.json", (json.dumps(metadata) + "\n").encode(), 0o600)
            completed = []
            try:
                for row in changes:
                    if self._read(row["path"]) != row["before"]:
                        raise ShellIntegrationError(f"shell file changed during apply: {row['path']}")
                    completed.append(row)
                    self._write(row["path"], row["after"], row["mode"])
                for row in changes:
                    if self._read(row["path"]) != row["after"]:
                        raise ShellIntegrationError(f"shell change did not verify: {row['path']}")
            except BaseException:
                # Roll back only our exact writes; retain concurrent user edits and
                # the durable originals for recovery rather than overwriting them.
                for row in reversed(completed):
                    with contextlib.suppress(OSError, ShellIntegrationError):
                        if self._read(row["path"]) == row["after"]:
                            self._write(row["path"], row["before"], row["mode"])
                raise ShellIntegrationError(f"shell connection apply interrupted; originals saved at {backup}")
            return {**result, **self.status(), "backup_root": str(backup)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "restore", "remove"), nargs="?", default="status")
    parser.add_argument("--dry-run", action="store_true", help="preview without editing shell files")
    args = parser.parse_args(argv)
    manager = ShellIntegration()
    try:
        result = manager.status() if args.action == "status" else manager.apply(args.action, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("needs_action") else 0
    except (ShellIntegrationError, OSError, RuntimeError) as exc:
        print(f"shell connection: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
