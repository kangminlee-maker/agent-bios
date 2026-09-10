#!/usr/bin/env python3
"""One benchmark response: dispatch it, and report what actually happened.

The unit is a *response*, not a run. Everything a receipt needs about a response
is derived here from the host's own structured output rather than from what was
requested — because the two differ. Measured 2026-08-26: `claude -p` with no
`--model` reported `claude-fable-5` in its own usage record, so a batch that
recorded the requested seat would have recorded a seat that never ran.

Statuses are a closed set, and only `ok` is data:

  ok            reached the seat, produced a result
  defect:auth   never reached a seat (see corpus.AUTH_FAILURE_MARKERS) — scoring
                this as a MISS would read as the strongest possible ablation effect
  defect:seat   reached a seat outside the accepted set
  defect:empty  produced nothing
  defect:timeout / defect:dispatch
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

import corpus

# Reasoning effort reaches each host differently; the level names are the host's.
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODEX_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")

CANARY_GLOBAL_RE = re.compile(r"CANARY_GLOBAL:\s*(\S+)")
CANARY_GUIDE_RE = re.compile(r"CANARY_GUIDE:\s*([A-Za-z0-9_.-]+)\s*=\s*(\S+)")
CANARY_HOOK_RE = re.compile(r"CANARY_HOOK:\s*(\S+)")


def real_bin(name: str) -> str:
    """The host binary itself, never an agent wrapper.

    `shutil.which` returns the Superset shim on this machine; it re-execs the real
    binary but injects env of its own, and a benchmark seat has to be pinned."""
    for d in os.environ.get("PATH", "").split(":"):
        if not d or "/.superset" in d:
            continue
        p = pathlib.Path(d) / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    raise RuntimeError(f"{name}: not found on PATH outside agent wrappers")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def host_version(binary: str) -> str:
    """The version of the binary that will actually run.

    Not the one `codex --version` prints from an interactive shell: that name
    resolves through a shell function to a different install (0.146.0 there,
    0.149.1 for the binary this runner dispatches). A receipt that named the
    shell's answer would name a version that did not run."""
    try:
        p = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
        return p.stdout.strip().splitlines()[0] if p.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unknown"


def command_for(host: str, prompt: str, model: str, effort: str, cwd: str,
                writable: bool = False) -> list[str]:
    """`writable` lets the agent actually edit the fixture, so a postcondition has a
    trace to read. It is scoped to the snapshot directory the run owns, and only
    scenarios that declare a postcondition ask for it — a scenario judged on prose
    is dispatched read-only, where the cheapest wrong action is impossible."""
    if host == "codex":
        cmd = [real_bin("codex"), "exec", "--json", "--skip-git-repo-check",
               "--sandbox", "workspace-write" if writable else "read-only", "--cd", cwd]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        return cmd + [prompt]
    cmd = [real_bin("claude"), "-p", "--output-format", "json",
           "--permission-mode", "acceptEdits" if writable else "plan"]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    return cmd + [prompt]


def _parse_claude(stdout: str) -> dict:
    """claude --output-format json emits EITHER a bare result object or an array of
    events ending in one — measured both shapes from the same binary on 2026-08-26
    (the array appeared when a rate_limit_event accompanied the result). A parser
    that knew only one shape would have turned an ordinary run into a defect."""
    payload = json.loads(stdout)
    events = payload if isinstance(payload, list) else [payload]
    if not events:
        raise ValueError("claude JSON output is empty")
    final = events[-1]
    models = sorted((final.get("modelUsage") or {}).keys())
    return {
        "session_id": final.get("session_id") or events[0].get("session_id"),
        "models_reported": models,
        "result_text": final.get("result") or "",
        "cost_usd": final.get("total_cost_usd"),
        "host_error": bool(final.get("is_error")),
    }


def codex_seat_from_rollout(home: str, thread_id: str) -> list[str]:
    """The model codex actually ran, read from its own session file.

    `codex exec --json` reports no model anywhere in its event stream, so verifying
    the seat against the request would be a check that cannot fire. The rollout
    file codex writes under the variant home names the thread in its filename and
    carries `"model":"…"`, so the evidence is the host's, not the runner's."""
    if not thread_id:
        return []
    root = pathlib.Path(home) / "sessions"
    hits = sorted(root.rglob(f"rollout-*{thread_id}*.jsonl")) if root.is_dir() else []
    models = set()
    for f in hits:
        models.update(re.findall(r'"model"\s*:\s*"([^"]+)"', f.read_text(encoding="utf-8",
                                                                          errors="replace")))
    return sorted(models)


def _parse_codex(stdout: str) -> dict:
    """codex exec --json emits JSONL events; thread.started carries the thread id."""
    session_id, models, text = None, set(), []
    malformed = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if ev.get("thread_id") and not session_id:
            session_id = ev["thread_id"]
        for blob in (ev, ev.get("msg") if isinstance(ev.get("msg"), dict) else {}):
            if isinstance(blob, dict):
                if isinstance(blob.get("model"), str):
                    models.add(blob["model"])
                usage = blob.get("usage")
                if isinstance(usage, dict) and isinstance(usage.get("model"), str):
                    models.add(usage["model"])
        item = ev.get("item") if isinstance(ev.get("item"), dict) else None
        if item and item.get("type") in ("agent_message", "assistant_message"):
            if isinstance(item.get("text"), str):
                text.append(item["text"])
    return {
        "session_id": session_id,
        "models_reported": sorted(models),
        "result_text": "\n".join(text),
        "cost_usd": None,
        "host_error": False,
        "malformed_lines": malformed,
    }


GUIDE_PATH_RE = re.compile(r"(/[^\s,;'\"()]*/guides/[^\s,;'\"()]+\.md)")


def _alias_free(path: str) -> str:
    """macOS's /private/var and /var name one directory; pick one spelling."""
    return path.replace("/private/var/", "/var/")


def _is_deployed(path: str, host: str) -> bool:
    """True only when the path is unmistakably the deployed corpus.

    BOTH operands are alias-normalised. Normalising only the reported path let a
    /var-form report miss a /private/var-form home on both prefix tests, so a
    response that had plainly read the deployed guide came back with an empty
    `guide_paths_deployed` and validated. An abbreviated path still cannot be decided
    either way and is deliberately not flagged."""
    home = _alias_free(str(corpus.HOST_HOMES[host]["home"].resolve()))
    return _alias_free(path).startswith(home + "/")


def canary_verdicts(text: str, variant: dict) -> dict:
    """Which carriers this response evidences it loaded, from THIS arm.

    EVERY global canary occurrence is collected, not the first one that matches.
    A response quoting this arm's token and then another arm's is contradictory
    evidence, and reading only the first match reports the favourable half — the
    exact shape of a signal that looks true. A guide canary bearing another arm's
    token is likewise reported apart from a missing one: different failures, and
    the first is the one that resembles success."""
    expected = f"{variant['token']}-GLOBAL"
    globals_found = CANARY_GLOBAL_RE.findall(text)
    guides = CANARY_GUIDE_RE.findall(text)
    mine = [g for g in globals_found if g == expected]
    foreign = [g for g in globals_found if g != expected]
    return {
        "global": len(mine) == 1 and not foreign,
        "global_seen": globals_found,
        "global_foreign": foreign,
        # Exact (slug, nonce) pairs this build injected. A slug reported with any
        # other value is not evidence of a read — it is a guess or another arm's.
        "guides_this_arm": sorted({sl for sl, v in guides
                                   if variant["guide_canaries"].get(sl) == v}),
        "guides_other_arm": sorted({sl for sl, v in guides
                                    if variant["guide_canaries"].get(sl) != v}),
        # WHETHER a guide was read is the measurement, so reading none is data and
        # never a defect. Reading one from the DEPLOYED home is an integrity failure.
        #
        # The test is "is this path the deployed corpus", not "is this path inside the
        # variant". The negative form produced 25 false positives in the first baseline:
        # macOS reports the temp home as /private/var/... while the runner stored
        # /var/..., and agents abbreviate long paths with an ellipsis, so a path INSIDE
        # the arm fails a startswith() test against it. The nonce carries the positive
        # proof — it cannot be abbreviated or symlinked — and the path only has to catch
        # the one case the nonce cannot: a guide read from the deployed tree, which
        # reports no canary at all and would otherwise look like "read no guide".
        "guide_paths_deployed": sorted({
            m for m in GUIDE_PATH_RE.findall(text) if _is_deployed(m, variant["host"])}),
        # The hook nonce was generated, injected and asked for, and then read by
        # nobody: a receipt was valid with no evidence that the corpus's own hook
        # delivery surface ran at all — the same shape as the guide canary defect this
        # instrument already fixed once. `expected` is None on an arm that registers no
        # hooks (the codex spec declares no settings file, so nothing is registered there
        # — Codex's own hook surface is simply not wired), and then there is nothing to prove.
        "hook_expected": variant.get("hook_canary"),
        "hook_seen": CANARY_HOOK_RE.findall(text),
        "hook": (variant.get("hook_canary") in CANARY_HOOK_RE.findall(text)
                 if variant.get("hook_canary") else None),
    }


# Models a host runs for its own housekeeping alongside the pinned seat. Claude
# reports claude-haiku-4-5 for internal side-tasks on every run, so an accepted set
# of exactly one id would fail every Claude response; an unlisted extra model is a
# seat defect, which is what catches a second full-strength model in the set.
AUXILIARY_MODELS = {"claude": ("claude-haiku-4-5",), "codex": ()}


def model_matches(want: str, got: str) -> bool:
    """Exact host-reported id, or the same id with a version suffix.

    Substring containment accepted `claude-opus-50` for `claude-opus-5`, which is a
    seat check that cannot tell a different model from the declared one."""
    return got == want or got.startswith(f"{want}-") or got.startswith(f"{want}@")


def seat_problem(host: str, want: str, reported: list) -> str | None:
    """None when every reported model is the pinned seat or a declared auxiliary."""
    if not want or not reported:
        return None
    allowed = (want,) + AUXILIARY_MODELS.get(host, ())
    if not any(model_matches(want, m) for m in reported):
        return f"pinned seat {want} appears in no reported model {reported}"
    stray = [m for m in reported if not any(model_matches(a, m) for a in allowed)]
    if stray:
        return f"models outside the accepted set participated: {stray}"
    return None


def dispatch(host: str, prompt: str, variant: dict, model: str, effort: str,
             cwd: pathlib.Path, fixture_hash: str, timeout: int = 600,
             writable: bool = False) -> dict:
    """Run one response and return everything a receipt needs about it."""
    env = dict(os.environ)
    for spec in corpus.HOST_HOMES.values():
        env.pop(spec["env"], None)
    # The operator's own seat must not be inherited by the agent under test's tool
    # subprocesses, so it never enters this environment; it travels on an fd.
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    env[corpus.HOST_HOMES[host]["env"]] = variant["home"]

    cmd = command_for(host, prompt, model, effort, str(cwd), writable)
    started = time.time()
    binary = cmd[0]
    try:
        with corpus.auth_channel(host) as (auth_add, pass_fds):
            proc = subprocess.run(cmd, cwd=cwd, env={**env, **auth_add},
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=timeout, pass_fds=pass_fds)
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, rc = "", "timeout", None
    elapsed = round(time.time() - started, 2)

    record = {
        "host": host, "requested_model": model, "requested_effort": effort,
        "binary": binary, "binary_version": host_version(binary),
        "returncode": rc, "elapsed_s": elapsed,
        "request_sha256": sha256_text(prompt + "\0" + fixture_hash),
        "experiment_hash": variant["experiment_hash"],
        "realized_hash": variant["realized_hash"],
        "fixture_hash": fixture_hash, "corpus_drift": None, "writable": writable,
        "session_id": None, "models_reported": [], "result_text": "",
        "cost_usd": None, "status": "ok", "host_error": False, "malformed_lines": 0,
        "raw_stdout": "", "raw_stderr": "",
        "raw_sha256": sha256_text(stdout),
    }

    record["raw_stdout"], record["raw_stderr"] = stdout, stderr
    if rc is None:
        record["status"] = "defect:timeout"
        return record
    # Auth failure is decided BEFORE parsing only when nothing parseable came back.
    # Scanning a successful response's own text for the phrase rejected responses that
    # merely discussed logging in — visible, so a detected miss rather than a false
    # pass, but a defect all the same.
    try:
        parsed = _parse_claude(stdout) if host == "claude" else _parse_codex(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        record["status"] = ("defect:auth" if corpus.is_auth_failure(stdout + stderr)
                            else f"defect:dispatch:{type(exc).__name__}")
        return record
    record.update(parsed)
    if host == "codex" and not record["models_reported"]:
        record["models_reported"] = codex_seat_from_rollout(variant["home"],
                                                            record["session_id"])
    record["result_sha256"] = sha256_text(record["result_text"])
    record["canaries"] = canary_verdicts(record["result_text"], variant)
    # The build-time hash describes bytes that may have moved since. Ask again.
    record["corpus_drift"] = corpus.verify_unchanged(variant)

    # The host's own failure signals gate the status. Both were recorded and
    # neither was read, so a nonzero exit with a well-formed payload became data.
    if rc != 0:
        record["status"] = ("defect:auth" if corpus.is_auth_failure(stdout + stderr)
                            else f"defect:dispatch:returncode-{rc}")
    elif record.get("host_error"):
        record["status"] = "defect:dispatch:host-error"
    elif record.get("malformed_lines"):
        record["status"] = f"defect:dispatch:malformed-{record['malformed_lines']}"
    elif not record["result_text"].strip():
        record["status"] = "defect:empty"
    elif not record["session_id"]:
        # No host-returned id means nothing evidences this was its own session.
        record["status"] = "defect:dispatch:no-session-id"
    elif seat_problem(host, model, record["models_reported"]):
        record["status"] = "defect:seat"
        record["seat_problem"] = seat_problem(host, model, record["models_reported"])
    return record
