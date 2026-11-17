#!/usr/bin/env python3
"""Record the session-distill nudge baseline at mining-window close.

Writes the state file the launcher's session_distill_nudge() reads:
{window_end, history_lines_total, transcript_files_total, updated}. Both totals must be counted
the same way the launcher counts them (`line_count` and `transcript_file_count` below mirror
launch/agent-launch.py `_line_count` and `_transcript_file_count`, and --self-test holds each pair
to one answer on a fixture tree), so the launcher's deltas start at ~0 after a window closes.
The file is replaced through a temporary file and a rename, so the launcher reads the old state or
the complete new one.

Usage: update-state.py [--window-end YYYY-MM-DD]  (default: today)
       update-state.py --self-test
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

STATE = pathlib.Path(
    os.environ.get(
        "AGENT_BIOS_SESSION_DISTILL_STATE",
        str(pathlib.Path.home() / ".local/share/agent-bios/session-distill-state.json"),
    )
)


def line_count(path: pathlib.Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 20), b""))
    except OSError:
        return 0


def transcript_file_count(home: pathlib.Path) -> int:
    """Transcript files under the hosts' roots (design §5.1, §12.4): Claude's one file per session
    directly in each project directory, Codex's rollouts, plain or compressed, anywhere below
    sessions/ and archived_sessions/. A directory listing; no file is opened."""
    total = 0
    try:
        with os.scandir(home / ".claude" / "projects") as projects:
            for project in projects:
                if project.is_dir(follow_symlinks=False):
                    with os.scandir(project.path) as files:
                        total += sum(1 for f in files if f.name.endswith(".jsonl") and f.is_file(follow_symlinks=False))
    except OSError:
        pass
    pending = [home / ".codex" / "sessions", home / ".codex" / "archived_sessions"]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(pathlib.Path(entry.path))
                    elif entry.name.endswith((".jsonl", ".jsonl.zst")) and entry.is_file(follow_symlinks=False):
                        total += 1
        except OSError:
            continue
    return total


def state_payload(home: pathlib.Path, window_end: str) -> dict:
    return {
        "window_end": window_end,
        "history_lines_total": line_count(home / ".claude/history.jsonl") + line_count(home / ".codex/history.jsonl"),
        "transcript_files_total": transcript_file_count(home),
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def write_state(path: pathlib.Path, payload: dict, before_rename=None) -> None:
    """Replace `path` with `payload`: a temporary file beside it, fsynced, then renamed over it.
    `before_rename` is the seam a crash is injected through."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=1) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if before_rename is not None:
            before_rename()
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--window-end", default=datetime.date.today().isoformat())
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    payload = state_payload(pathlib.Path.home(), args.window_end)
    write_state(STATE, payload)
    print(f"state written: {STATE} (window_end={args.window_end}, lines={payload['history_lines_total']}, "
          f"transcript files={payload['transcript_files_total']})")
    return 0


def self_test():
    """The writer and the launcher's reader agree: counts, field names, the nudge each state earns."""
    import subprocess
    import time
    failures = []
    repo = pathlib.Path(__file__).resolve().parents[1]
    launcher_path = repo / "launch" / "agent-launch.py"
    today = datetime.date.today()

    def day(offset):
        return (today - datetime.timedelta(days=offset)).isoformat()

    def load_launcher(path):
        spec = importlib.util.spec_from_file_location("agent_launch_probe", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["agent_launch_probe"] = module
        spec.loader.exec_module(module)
        return module

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        home = root / "home"
        for rel, text in {".claude/history.jsonl": "a\nb\nc\n", ".codex/history.jsonl": "d\ne\n",
                          ".claude/projects/p1/a.jsonl": "", ".claude/projects/p1/b.jsonl": "", ".claude/projects/p2/c.jsonl": "",
                          ".claude/projects/p1/sub/agent.jsonl": "", ".claude/projects/p1/notes.json": "", ".claude/projects/stray.jsonl": "",
                          ".codex/sessions/2026/10/21/rollout-x.jsonl": "", ".codex/sessions/2026/10/21/rollout-y.jsonl.zst": "",
                          ".codex/sessions/readme.txt": "", ".codex/archived_sessions/rollout-z.jsonl.zst": ""}.items():
            (home / rel).parent.mkdir(parents=True, exist_ok=True)
            (home / rel).write_text(text, encoding="utf-8")
        files_here = 6  # p1/a, p1/b, p2/c, rollout-x, rollout-y, rollout-z; nested, stray and non-transcript files are not
        launcher = load_launcher(launcher_path)
        if (transcript_file_count(home), launcher._transcript_file_count(home)) != (files_here, files_here):
            failures.append(f"the transcript count differs between writer and launcher: {transcript_file_count(home)} vs {launcher._transcript_file_count(home)}, expected {files_here}")
        if (line_count(home / ".claude/history.jsonl"), launcher._line_count(home / ".claude/history.jsonl")) != (3, 3):
            failures.append("the history line count differs between writer and launcher")
        if transcript_file_count(root / "nowhere") != 0 or launcher._transcript_file_count(root / "nowhere") != 0:
            failures.append("a home without transcript roots did not count as zero")

        # the writer: the documented invocation, run for real, then the fields the launcher reads
        state_file = root / "state" / "session-distill-state.json"
        env = {**os.environ, "HOME": str(home), "AGENT_BIOS_SESSION_DISTILL_STATE": str(state_file)}
        done = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--window-end", "2026-10-01"],
                              capture_output=True, text=True, env=env)
        written = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
        if done.returncode != 0 or set(written) != {"window_end", "history_lines_total", "transcript_files_total", "updated"} \
                or (written.get("window_end"), written.get("history_lines_total"), written.get("transcript_files_total")) != ("2026-10-01", 5, files_here):
            failures.append(f"update-state.py --window-end did not write the state the launcher reads (exit {done.returncode}): {written} {done.stderr[:200]}")
        before = state_file.read_bytes()

        class Crash(Exception):
            pass

        def crash():
            raise Crash("injected between the temporary write and the rename")
        try:
            write_state(state_file, {"window_end": "2030-01-01"}, before_rename=crash)
            failures.append("the injected crash did not surface")
        except Crash:
            pass
        if state_file.read_bytes() != before or sorted(p.name for p in state_file.parent.iterdir()) != [state_file.name]:
            failures.append("a crash before the rename changed the state file or left a temporary behind")

        # the reader, per state file: golden states from before and after this change, under a pinned home
        os.environ["HOME"] = str(home)
        launcher.SESSION_DISTILL_STATE = root / "golden-state.json"
        config = {"session_distill": {"nudge_after": 2, "cadence_days": 14, "transcript_growth": 3}}

        def nudge(state, cfg=config, module=None):
            launcher.SESSION_DISTILL_STATE.write_text(state if isinstance(state, str) else json.dumps(state), encoding="utf-8")
            return (module or launcher).session_distill_nudge(cfg)

        saved_home = os.environ.get("HOME")
        try:
            launcher.SESSION_DISTILL_STATE = root / "absent.json"
            if launcher.session_distill_nudge(config) is not None:
                failures.append("with no state file the launcher nudged")
            launcher.SESSION_DISTILL_STATE = root / "golden-state.json"
            old_fresh = {"window_end": day(1), "history_lines_total": 5, "updated": "x"}
            old_due = {"window_end": day(1), "history_lines_total": 0, "updated": "x"}
            if nudge(old_fresh) is not None:
                failures.append("a state from before this change, with no new history, nudged")
            legacy_text = nudge(old_due)
            want = f"session-distill due: ~5 new session entries since {day(1)} (threshold 2) — launch the Session distill preset to run the next mining window"
            if legacy_text != want:
                failures.append(f"a state from before this change no longer nudges as it did: {legacy_text!r}")
            if nudge({**old_fresh, "window_end": day(400)}) is not None:
                failures.append("a state without transcript_files_total nudged by cadence, which belongs to the new fields")
            current = {"window_end": day(1), "history_lines_total": 0, "transcript_files_total": files_here, "updated": "x"}
            if nudge(current) is not None:
                failures.append("a state written now, with nothing new and a young window, nudged (the new rule ignores history lines)")
            by_days = nudge({**current, "window_end": day(30)})
            if not by_days or "30 days since" not in by_days or "transcript files" in by_days:
                failures.append(f"a window older than the cadence did not nudge by days alone: {by_days!r}")
            by_growth = nudge({**current, "transcript_files_total": files_here - 3})
            if not by_growth or "~3 new transcript files" not in by_growth or "days since" in by_growth:
                failures.append(f"growth by the threshold did not nudge by files alone: {by_growth!r}")
            if nudge({**current, "transcript_files_total": files_here - 2}) is not None:
                failures.append("growth below the threshold nudged")
            both = nudge({**current, "window_end": day(30), "transcript_files_total": files_here - 3})
            if not both or "days since" not in both or "transcript files" not in both:
                failures.append(f"a window past both limits did not name both: {both!r}")
            if nudge({**current, "window_end": day(14)}) is None or nudge({**current, "window_end": day(13)}) is not None:
                failures.append("the cadence boundary is not 'reaches cadence_days'")
            if nudge({**current, "window_end": "not a date"}) is not None:
                failures.append("a window_end that is not a date nudged by days")
            if nudge({**old_due, "transcript_files_total": "many"}) != want:
                failures.append("a transcript_files_total that is not an integer did not fall back to the original rule")
            if nudge({**current, "transcript_files_total": True, "history_lines_total": 0}) != want:
                failures.append("a boolean transcript_files_total was taken for a count")
            if nudge("{ not json") is not None or nudge({"window_end": day(40), "transcript_files_total": 1}) is not None:
                failures.append("an unreadable state, or one without history_lines_total, nudged")
            for label, bad in (("a string", "14"), ("a bool", True), ("zero", 0), ("negative", -1)):
                cfg = {"session_distill": {"cadence_days": bad, "transcript_growth": bad}}
                if nudge({**current, "window_end": day(14)}, cfg) is None or nudge({**current, "window_end": day(13)}, cfg) is not None:
                    failures.append(f"{label} as cadence_days did not fall back to the default of 14 days")
                if nudge({**current, "transcript_files_total": files_here - 250}, cfg) is None or nudge({**current, "transcript_files_total": files_here - 249}, cfg) is not None:
                    failures.append(f"{label} as transcript_growth did not fall back to the default of 250")
            if nudge(current, {}) is not None or nudge({**current, "window_end": day(30)}, {"session_distill": "text"}) is None:
                failures.append("a missing or malformed [session_distill] table did not use the defaults")
            # the shipped table says what the launcher falls back to: 14 days and 250 transcript files (owner decision, 2026-10-21)
            import tomllib
            shipped = tomllib.loads((repo / "launch" / "agent-launch.toml").read_text(encoding="utf-8")).get("session_distill", {})
            if (shipped.get("cadence_days"), shipped.get("transcript_growth")) != (14, 250):
                failures.append(f"launch/agent-launch.toml [session_distill] says {shipped}, not cadence_days 14 and transcript_growth 250")
            table = {"session_distill": shipped}
            if nudge({**current, "window_end": day(14)}, table) is None or nudge({**current, "window_end": day(13)}, table) is not None \
                    or nudge({**current, "transcript_files_total": files_here - 250}, table) is None or nudge({**current, "transcript_files_total": files_here - 249}, table) is not None:
                failures.append("the shipped [session_distill] table does not nudge at 14 days or 250 new transcript files")

            # the launcher alone: copied away from the checkout and run by a fresh interpreter that cannot reach it
            away = root / "away"
            away.mkdir()
            copy = away / "agent-launch.py"
            copy.write_bytes(launcher_path.read_bytes())
            checkout = root / "checkout" / "launch"  # stands for the checkout: a helper only it holds
            checkout.mkdir(parents=True)
            (checkout / "checkout_only_helper.py").write_text("HELPER = 'reached'\n", encoding="utf-8")
            driver = ("import importlib.util, json, sys\n"
                      "spec = importlib.util.spec_from_file_location('agent_launch_alone', sys.argv[1])\n"
                      "module = importlib.util.module_from_spec(spec)\n"
                      "sys.modules['agent_launch_alone'] = module\n"
                      "spec.loader.exec_module(module)\n"
                      "print(json.dumps(module.session_distill_nudge(json.loads(sys.argv[2]))))\n")
            alone_state = {**current, "window_end": day(30), "transcript_files_total": files_here - 3}
            (root / "golden-state.json").write_text(json.dumps(alone_state), encoding="utf-8")
            alone_env = {"HOME": str(home), "AGENT_BIOS_SESSION_DISTILL_STATE": str(root / "golden-state.json"), "PATH": os.environ.get("PATH", "")}

            # Denying the checkout is the kernel's job, not the import path's: a helper read by absolute
            # path, or loaded from one, is reachable whatever PYTHONPATH says. `sandbox-exec` refuses
            # every read below the checkout; where the host has no such mechanism this control fails by
            # name rather than reporting an isolation it never applied.
            import shutil
            sandbox = shutil.which("sandbox-exec")
            denied = [checkout.resolve()] + ([repo.resolve()] if repo.resolve() not in pathlib.Path(sys.executable).resolve().parents else [])
            profile = "(version 1)(allow default)" + "".join(f'(deny file-read* (subpath "{d}"))' for d in denied)

            def run_alone(script, isolated=True, reach=None, deny=False):
                """The copy's nudge, from a fresh interpreter in the directory the copy sits in. `-I` drops PYTHONPATH,
                the script directory and the working directory from the import path; `reach` points PYTHONPATH at the
                stand-in checkout; `deny` puts the run under a sandbox profile that refuses every read below it."""
                command = [sys.executable, *(["-I"] if isolated else []), "-c", driver, str(script), json.dumps(config)]
                if deny:
                    command = [sandbox, "-p", profile, *command]
                return subprocess.run(command, cwd=away, capture_output=True, text=True,
                                      env={**alone_env, **({"PYTHONPATH": str(reach)} if reach else {})})

            expected = nudge(alone_state, module=launcher)
            alone = run_alone(copy)
            if expected is None or alone.returncode != 0 or json.loads(alone.stdout or "null") != expected:
                failures.append(f"the launcher copied out of the checkout did not nudge as the checkout's does from the state file and the home directory "
                                f"(exit {alone.returncode}): {alone.stdout[:120]!r} {alone.stderr[-200:]!r}")
            helper = checkout / "checkout_only_helper.py"
            plants = {  # each is the launcher plus one way of reaching a file only the checkout holds
                "an import by module name": "\nimport checkout_only_helper\n",
                "a read by absolute path": f"\nopen({str(helper)!r}, encoding='utf-8').read()\n",
                "an import by file path": ("\nimport importlib.util as _u\n"
                                           f"_s = _u.spec_from_file_location('checkout_only_helper', {str(helper)!r})\n"
                                           "_m = _u.module_from_spec(_s)\n_s.loader.exec_module(_m)\n"),
            }
            for label, tail in plants.items():
                planted = away / f"planted-{len(tail)}.py"
                planted.write_text(launcher_path.read_text(encoding="utf-8") + tail, encoding="utf-8")
                by_path = label != "an import by module name"
                reached = run_alone(planted, isolated=by_path, reach=None if by_path else checkout)
                if reached.returncode != 0 or json.loads(reached.stdout or "null") != expected:
                    failures.append(f"positive control: the plant reaching the checkout by {label} was not reachable with nothing denied "
                                    f"(exit {reached.returncode}): {reached.stderr[-200:]!r}")
                if sandbox is None:
                    failures.append(f"the plant reaching the checkout by {label} was never blocked: this host offers no sandbox-exec, "
                                    "so no run denied the checkout and the isolation is unproven")
                    continue
                blocked = run_alone(planted, isolated=by_path, reach=None if by_path else checkout, deny=True)
                named = str(helper) in blocked.stderr or "not permitted" in blocked.stderr or "checkout_only_helper" in blocked.stderr
                if blocked.returncode == 0 or not named:
                    failures.append(f"the plant reaching the checkout by {label} survived a denied checkout, so the isolation proves nothing "
                                    f"(exit {blocked.returncode}): {blocked.stderr[-300:]!r}")
            if sandbox is not None:
                confined = run_alone(copy, deny=True)
                if confined.returncode != 0 or json.loads(confined.stdout or "null") != expected:
                    failures.append(f"the launcher did not nudge with the checkout denied, so it reads one of its files "
                                    f"(exit {confined.returncode}): {confined.stderr[-300:]!r}")
            import ast
            source = ast.parse(launcher_path.read_text(encoding="utf-8"))
            body = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef) and n.name == "session_distill_nudge")
            names = {n.id for n in ast.walk(body) if isinstance(n, ast.Name)} | {c.value for c in ast.walk(body) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
            if "__file__" in names or any("coverage" in str(x) or "ledger" in str(x) for x in names):
                failures.append("session_distill_nudge names a checkout file or coverage.json")
        finally:
            if saved_home is not None:
                os.environ["HOME"] = saved_home
    for failure in failures:
        print(f"update-state --self-test [FAIL] {failure}")
    if failures:
        return 1
    print("update-state --self-test: OK (writer and launcher count alike, golden states from before and after, "
          "cadence and growth thresholds with their fallbacks, the launcher alone with every read below the checkout denied by the "
          "kernel, proven by three plants — an import by name, a read by absolute path, an import by file path — each reachable first "
          "and then blocked by the planted path, a crash before the rename)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
