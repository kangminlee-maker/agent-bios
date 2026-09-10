#!/usr/bin/env python3
"""The live path (named for its realization, and so it never shadows benchmarks/run.py
on a sys.path usage.py also extends): Stage-0 seat probes, and one delegated run per arm through the same
driver the golden path uses (protocol.drive), with a solver that dispatches real hosts.

    python3 live.py probe --host claude|codex         # standing prefix per seat, spreads
    python3 live.py run --host H --arm ARM [--m 3]    # one live run, ledger + level + verdict
    python3 live.py plants --record DIR               # control-0 plants on the run's artifacts

Realization: `live` only. Every number here is read from the host's own artifact by
usage.py after the process exits; nothing is taken from what this runner requested.
What this runner supplies is recorded as intent (`launch`), and the receipt is what
the artifact says. A run record is written under benchmarks/out/tier/runs/, with the
artifacts COPIED beside it so the plants mutate copies, never the host's files.

Passes and participants (control 0): a pass is one host process — the parent, spawned
fresh for `solve` and resumed for later phases — and the participants it produces are
declared by role BEFORE it runs: solve and self_verify produce the parent's own new
requests plus exactly one new child; parent_repair produces the parent's requests and
no child. A pass that produced a different set fails the ledger by name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import corpus      # noqa: E402  (benchmarks/corpus.py: auth channel)
import dispatch    # noqa: E402  (benchmarks/dispatch.py: real_bin, parsers)
import fixture_gen  # noqa: E402
import level       # noqa: E402
import pin as pinmod  # noqa: E402
import probes      # noqa: E402
import protocol    # noqa: E402
import usage       # noqa: E402
import budget      # noqa: E402  (benchmarks/tier/budget.py: the design's ceilings, re-derived from records)
import registry    # noqa: E402  (benchmarks/tier/registry.py: the registered topology, one owner)

REPO = HERE.parent.parent
# The run tree lives OUTSIDE the repository (`D-20260904-4ccdf9`): Stage 1's seats reached
# the generator by `../../../../../../../tier/fixture_gen.py` and by `git show HEAD:…`
# because every run directory sat under the checkout. TIER_OUT overrides.
OUT = pathlib.Path(os.environ.get("TIER_OUT") or (pathlib.Path.home() / ".agent-bios" / "tier"))
TIMEOUT = 1500               # seconds per host process


class RunError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- arms
# The treatment matrix (design). `mechanism`: none (the parent works itself), isolated
# (a fresh child on a registered agent, fork_turns none / a non-fork subagent), fork
# (fork_turns all — the child inherits the parent's context AND seat: a model override
# in a Codex fork is silently dropped, measured 2026-09-04, which is why there is no
# fork-sweep). `protocol` is the brief template the child receives; a fork gets the
# fixed FORK_TASK line instead, since it already holds the parent's context.
ARMS = {
    "inline":              {"mechanism": "none",     "child_tier": None,        "protocol": "standard"},
    "delegated-same":      {"mechanism": "isolated", "child_tier": "helm",      "protocol": "standard"},
    "delegated-workhorse": {"mechanism": "isolated", "child_tier": "workhorse", "protocol": "standard"},
    "delegated-sweep":     {"mechanism": "isolated", "child_tier": "sweep",     "protocol": "cheap-seat"},
    # fork-same is Codex-only: `claude -p --agents …` answers a subagent_type "fork" spawn
    # with "Agent type 'fork' not found" (measured 2026-09-04, claude 2.1.260) — the
    # fork subagent is not reachable from the print-mode parent this instrument runs.
    "fork-same":           {"mechanism": "fork",     "child_tier": "helm",      "protocol": "none",
                            "hosts": ("codex",)},
}
STAGE1_ARMS = ["inline", "delegated-same", "delegated-workhorse", "delegated-sweep", "fork-same"]
# One registered child agent per child tier, all present in every run's home so the
# arm is chosen by the parent's spawn call and receipted from the child's artifact.
CHILD_NAMES = {"helm": "tier-same", "workhorse": "tier-workhorse", "sweep": "tier-sweep"}
EXPECTED_ROLES = {"solve": ("parent", "child"), "self_verify": ("parent", "child"),
                  "parent_repair": ("parent",)}
INLINE_ROLES = {"solve": ("parent",), "self_verify": ("parent",), "parent_repair": ("parent",)}
TIMEOUT_BY_M = {1: 1800, 3: 1800, 5: 1800, 7: 1800, 10: 1800, 40: 3600, 160: 7200}


# The spawn-trigger experiment's registered volumes (design §Design, *Variables* and the
# treatment matrix): one host, M = 1 / 5 / 10 at R 10 for the primary contrast, the sweep
# at 1 and 5 (report-only, R 10), the same-seat control at 1 (R 5); a conditional cell at
# 3 or 7 (R 10); confirmation at R 5. Not options — a volume typed at the prompt is a
# declaration nobody registered (build review round 1, F2).
TRIGGER_HOST = registry.HOST
TRIGGER_PLAN = registry.STAGE_PLANS["trigger-b"]
# groups whose ceiling stops only their own remaining runs (report-only and control arms);
# every other group's ceiling, and the total, stops the stage (round 2, F5)
NON_PRIMARY_GROUPS = ("B-sweep", "B-same")


def trigger_c_plan(path: pathlib.Path, cand: dict, root_id: str, root: pathlib.Path) -> tuple[dict, dict]:
    """The confirmation stage's plan from the reader's candidates manifest, refused unless
    the claims are the two ends the registry names for the form (round 1 F13, round 2
    F13): the text is named by id and must resolve to the sealed sha; host, R, and the
    root identity are the registered ones."""
    form, n = cand.get("form"), cand.get("n")
    claims = [int(c["m"]) for c in (cand.get("claims") or [])]
    k = int(cand.get("k") or 0)
    if cand.get("host") != TRIGGER_HOST or int(cand.get("R") or 0) != registry.R_CONFIRM:
        raise RunError(f"{path}: host {cand.get('host')!r} R {cand.get('R')!r} — confirmation is {TRIGGER_HOST} at R {registry.R_CONFIRM}")
    if cand.get("root_id") != root_id:
        raise RunError(f"{path}: root_id {cand.get('root_id')!r} is not this root's {root_id!r}")
    try:
        want = registry.claims_for(form, n)
        tid = registry.make_id(form, n)
    except registry.RegistryError as exc:
        raise RunError(f"{path}: {exc}")
    if cand.get("text_id") != tid:
        raise RunError(f"{path}: text_id {cand.get('text_id')!r} is not {tid} (form {form!r}, N={n!r})")
    if sorted(claims) != want or k != len(want) or len(claims) != len(set(claims)):
        raise RunError(f"{path}: claims {claims} with k={k} — {tid} confirms exactly {want} (k={len(want)})")
    for key in ("text_sha256", "cards_sha256", "matrix_sha256", "cards_set", "tokens_unpadded"):
        if not cand.get(key):
            raise RunError(f"{path}: no {key} — the manifest does not name what it confirms")
    # the frozen text under THIS root is what the id names; a root without a frozen set
    # has nothing to confirm (round 2, F13 — and the self-test caught a lookup beside the
    # candidates file instead of under the root)
    texts_json = pathlib.Path(root) / registry.CARDS_DIR / "texts.json"
    if not texts_json.is_file():
        raise RunError(f"{texts_json} does not exist — no frozen text set under this root names {tid}")
    try:
        frozen = registry.text_sha(json.loads(texts_json.read_text()), tid)
    except registry.RegistryError as exc:
        raise RunError(f"{path}: {exc}")
    if frozen != cand["text_sha256"]:
        raise RunError(f"{path}: {tid} is frozen as {frozen[:12]}, the manifest carries {cand['text_sha256'][:12]}")
    plan = registry.confirm_plan(want)
    meta = {"root_id": root_id,
            "confirms": {"candidates": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "k": k, "form": form, "n": n, "text_id": tid, "text_sha256": cand["text_sha256"], "cards_sha256": cand["cards_sha256"],
                         "matrix_sha256": cand["matrix_sha256"], "cards_set": cand["cards_set"], "tokens_unpadded": cand["tokens_unpadded"]}}
    return plan, meta


def preflight_groups(root: pathlib.Path, name: str, plan: dict) -> dict:
    """Before a trigger stage starts: every primary group must be startable; a report-only
    or control group that has spent its ceiling is skipped by the loop rather than
    refusing the whole stage (round 5, F11). Returns the groups that will be skipped."""
    skipped = {}
    for group in sorted({budget.group_of_run(name, arm) for arm in plan}):
        allowed, why = budget.can_start(root, group)
        if allowed:
            continue
        if group in NON_PRIMARY_GROUPS and ("nothing left" in why or why.startswith("ceiling")):
            skipped[group] = why
            print(f"preflight: {group} is at its ceiling — its runs are skipped, the stage goes on ({why[:80]})")
            continue
        raise RunError(f"{name} does not start: {why}")
    return skipped


def require_pass_c(root: pathlib.Path, cand_sha: str) -> None:
    """C first draws its fresh cost sample (design §Staging): the confirmation blocks are
    dispatched only after pass C is complete, scored, valid, and bound to the sealed
    candidates file (round 3, F9)."""
    pdir = root / registry.CARDS_DIR / "passes" / "C"
    man_p, score_p = pdir / "manifest.json", pdir / "score.json"
    if not man_p.is_file() or not score_p.is_file():
        raise RunError(f"pass C under {pdir} is not declared and scored — C draws its fresh cost sample before any block runs")
    man, score = json.loads(man_p.read_text()), json.loads(score_p.read_text())
    bound = (man.get("confirms") or {}).get("candidates_sha256")
    if bound != cand_sha:
        raise RunError(f"pass C was declared against candidates {str(bound)[:12]}, the sealed file is {cand_sha[:12]}")
    if not score.get("complete"):
        raise RunError("pass C's score is not complete — every declared call must have a priced record")
    if score.get("invalid"):
        raise RunError(f"pass C is invalid: {score['invalid']} — its null is not a baseline, so nothing is confirmed")
    # a self-asserted score is not evidence: the pass is reconciled the way its scorer and
    # the reader reconcile it, and the selection it confirms is re-derived (round 4, F11)
    import cards as cardsmod
    import trigger as triggermod
    problems = list(cardsmod.verify_pass(root, "C", {"confirms.candidates_sha256": cand_sha}))
    problems += list(triggermod.reconcile_selection(root))
    if problems:
        raise RunError("pass C is not confirmable: " + "; ".join(str(p_) for p_ in problems[:6]))


def trigger_cell_plan(root: pathlib.Path, m: int, root_id: str, pin_head: str | None = None) -> tuple[dict, dict]:
    """The one conditional cell the sealed PENDING tree authorizes (round 2, F7): after
    Stage B the reader seals `trigger-tree.pending.json` when the row needs a cell — it has
    no N, so it authorizes nothing but that cell. It must exist, pass the registry's checks
    for this root, and name exactly this size; the other size's stage directory must not
    exist; a complete tree already on disk means no cell is pending."""
    pend_path = root / registry.PENDING_FILE
    if (root / registry.TREE_FILE).is_file() and not (root / f"trigger-cell{m}").exists():
        raise RunError(f"{root / registry.TREE_FILE} is sealed — the tree is complete and no conditional cell is pending")
    if not pend_path.is_file():
        raise RunError(f"{pend_path} does not exist — a conditional cell is authorized by the pending tree the reader seals after Stage B")
    pend = json.loads(pend_path.read_text())
    bad = registry.check_pending_tree(pend, root_id, root=root)
    if bad:
        raise RunError(f"{pend_path} is not a sealed pending tree for this root: " + "; ".join(bad))
    if pend.get("needs") != m:
        raise RunError(f"the pending tree authorizes conditional cell M={pend.get('needs')}, not M={m}")
    b_manifest = root / "trigger-b" / "manifest.json"
    if not b_manifest.is_file():
        raise RunError(f"{b_manifest} does not exist — no Stage B declaration under this root for the pending tree to derive from")
    b_sha = hashlib.sha256(b_manifest.read_bytes()).hexdigest()
    if pend.get("b_manifest_sha256") != b_sha:
        raise RunError(f"the pending tree was derived from Stage B manifest {str(pend.get('b_manifest_sha256'))[:12]}, on disk is {b_sha[:12]} — stale (round 3, F11)")
    if pin_head is not None and not registry.same_head(pend.get("pin_head"), pin_head, root):
        raise RunError(f"the pending tree was sealed at pin {pend.get('pin_head')}, the tree is at {pin_head} — "
                       "a head the experiment did not declare (registry.py extend-pin)")
    other = {3: 7, 7: 3}[m]
    if (root / f"trigger-cell{other}").exists():
        raise RunError(f"{root / f'trigger-cell{other}'} exists — at most one conditional cell follows the tree")
    plan = registry.STAGE_PLANS[f"trigger-cell{m}"]
    return plan, {"root_id": root_id, "pending_tree_sha256": hashlib.sha256(pend_path.read_bytes()).hexdigest()}


def rows_for(pin: dict, host: str, arm: str, parent_tier: str = "helm") -> dict:
    spec = ARMS[arm]
    if "hosts" in spec and host not in spec["hosts"]:
        raise RunError(f"{arm} is not an arm on {host}")
    child = pinmod.experiment_row(pin, host, spec["child_tier"]) if spec["child_tier"] else None
    return {"parent": pinmod.experiment_row(pin, host, parent_tier), "child": child}


def child_agents(pin: dict, host: str, body: str) -> dict:
    """Every child seat the host's arms can spawn: name -> {body, row}."""
    return {CHILD_NAMES[t]: {"body": body, "row": pinmod.experiment_row(pin, host, t)}
            for t in ("helm", "workhorse", "sweep")}


# ----------------------------------------------------------------------------- hosts
def binary(host: str) -> str:
    """The host binary. `codex` on this machine is a shell function plus a cmux shim,
    so the Homebrew symlink is resolved to the real Mach-O; claude goes through
    dispatch.real_bin like the instruction benchmark."""
    if host == "codex":
        brew = pathlib.Path("/opt/homebrew/bin/codex")
        if brew.exists():
            return os.path.realpath(brew)
    for d in os.environ.get("PATH", "").split(":"):
        if not d or "/.superset" in d or "cmux-cli-shims" in d:
            continue
        cand = pathlib.Path(d) / host
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return dispatch.real_bin(host)


def claude_project_dir(cwd: pathlib.Path) -> pathlib.Path:
    """Claude keys a project's transcripts by its cwd with every `/` AND every `.`
    replaced by `-` (measured 2026-09-04: `~/.agent-bios/tier/…` became
    `-Users-kangmin--agent-bios-tier-…`); the earlier run tree had no dot in its path,
    so the second replacement never showed."""
    return pathlib.Path.home() / ".claude" / "projects" / str(cwd).replace("/", "-").replace(".", "-")


def claude_agents_json(agents: dict) -> str:
    out = {}
    for name, a in agents.items():
        spec = {"description": f"the experiment's {name} seat", "prompt": a["body"],
                "model": a["row"]["model"]}
        if a["row"].get("effort"):
            spec["effort"] = a["row"]["effort"]
        out[name] = spec
    return json.dumps(out, separators=(",", ":"))


def codex_home(dest: pathlib.Path, agents: dict, source: pathlib.Path | None = None,
               reuse: bool = False) -> dict:
    """A CODEX_HOME carrying the deployed corpus and auth, every child seat registered,
    and nothing else the operator's home adds (MCP servers are stripped so the child's
    tool surface is the host's own — recorded as a disclosure). `reuse` keeps an
    existing home: a fresh one bootstraps ~28 MB of curated plugins on first start
    (measured 2026-09-04), which a stage pays once, not per run."""
    src = source or (pathlib.Path.home() / ".codex")
    if dest.exists() and reuse and (dest / "config.toml").is_file():
        return {"home": str(dest), "reused": True,
                "templates": {n: str(dest / "agents" / f"{n}.toml") for n in agents}}
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    dest.chmod(0o700)
    for rel in ("AGENTS.md", "guides", "auth.json"):
        s = src / rel
        if s.is_file():
            shutil.copy2(s, dest / rel)
        elif s.is_dir():
            shutil.copytree(s, dest / rel)
    if (dest / "auth.json").exists():
        (dest / "auth.json").chmod(0o600)
    cfg = (src / "config.toml").read_text(encoding="utf-8") if (src / "config.toml").is_file() else ""
    kept, dropped = [], []
    for block in re.split(r"(?m)^(?=\[)", cfg):
        head = block.split("\n", 1)[0].strip()
        if head.startswith("[agents.") or head.startswith("[mcp_servers"):
            dropped.append(head)
        else:
            kept.append(block)
    (dest / "agents").mkdir()
    text = "".join(kept).rstrip("\n") + "\n"
    if "multi_agent = true" not in text:
        text += "\n[features]\nmulti_agent = true\n"
    templates = {}
    for name, a in agents.items():
        tmpl = dest / "agents" / f"{name}.toml"
        lines = [f'name = "{name}"',
                 f'description = "the experiment\'s {name} seat"',
                 f'model = "{a["row"]["model"]}"']
        if a["row"].get("effort"):
            lines.append(f'model_reasoning_effort = "{a["row"]["effort"]}"')
        lines.append('developer_instructions = """\n' + a["body"] + '"""')
        tmpl.write_text("\n".join(lines) + "\n", encoding="utf-8")
        text += (f"\n[agents.{name}]\ndescription = \"the experiment's {name} seat\"\n"
                 f"config_file = \"{tmpl}\"\n")
        templates[name] = str(tmpl)
    (dest / "config.toml").write_text(text, encoding="utf-8")
    return {"home": str(dest), "templates": templates, "dropped_sections": dropped, "reused": False}


# What a run's own home takes from the stage template: the instruction surface, the child
# seat templates and config, auth, and the plugin/tool caches a fresh home would rebuild
# (~28 MB, network) — never a store (sessions, thread/state/memory databases, logs, shell
# snapshots, locks, tmp), so the home holds nothing another run wrote.
RUN_HOME_ENTRIES = ("AGENTS.md", "guides", "skills", "agents", "config.toml", "auth.json", "plugins",
                    "cache", "models_cache.json", "installation_id", ".sandbox_migration")


def run_home(template: pathlib.Path, dest: pathlib.Path) -> dict:
    """A run's own CODEX_HOME (`D-20260905-aec4cd`): the template's `RUN_HOME_ENTRIES`,
    trees hardlinked so a 600-run stage stores them once, config and auth copied and the
    child seat templates re-addressed into this home so nothing in it points at the
    template; what the template holds beyond that is listed as `without`, not copied. A
    seat here finds the surface and its own session, and the stage loop removes the home
    once the run's transcript is in `artifacts/`."""
    template = pathlib.Path(template)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    dest.chmod(0o700)
    copied, without = [], []
    for entry in sorted(os.listdir(template)):
        s = template / entry
        if entry not in RUN_HOME_ENTRIES:
            without.append(entry)
            continue
        if s.is_dir():
            shutil.copytree(s, dest / entry, symlinks=True, copy_function=os.link)
        elif entry in ("config.toml", "auth.json"):
            shutil.copy2(s, dest / entry)
        else:
            os.link(s, dest / entry)
        copied.append(entry)
    if (dest / "auth.json").exists():
        (dest / "auth.json").chmod(0o600)
    cfg = dest / "config.toml"
    if cfg.is_file():
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(str(template) + "/agents/", str(dest) + "/agents/"),
                       encoding="utf-8")
    return {"home": str(dest), "per_run": True, "template": str(template), "copied": copied, "without": without,
            "removed_after_run": True}


def parent_cmd(host: str, row: dict, prompt: str, cwd: pathlib.Path, agents_json: str = "",
               resume: str | None = None, max_budget_usd: float | None = None) -> list[str]:
    if host == "claude":
        cmd = [binary("claude"), "-p", "--output-format", "json",
               "--permission-mode", "acceptEdits",
               "--allowedTools", "Bash(pytest:*),Bash(python3:*),Bash(python:*),Edit,Write,"
                                 "Read,Glob,Grep,Agent",
               "--model", row["model"]]
        if row.get("effort"):
            cmd += ["--effort", row["effort"]]
        if max_budget_usd is not None:
            # the process stops itself at the cap: the budget reserve is a bound the host
            # enforces, not an estimate the ledger reads afterwards (round 3, F7)
            cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
        if agents_json:
            cmd += ["--agents", agents_json]
        if resume:
            cmd += ["--resume", resume]
        return cmd + [prompt]
    cmd = [binary("codex"), "exec"]
    if resume:
        # `exec resume` takes no --cd/-s: the thread keeps its cwd and sandbox. Model and
        # effort are NOT kept (measured 2026-09-04: a bare resume ran at xhigh after a
        # `low` thread), so both are re-pinned on every resume.
        cmd += ["resume"]
    cmd += ["--json", "--skip-git-repo-check", "-m", row["model"]]
    if row.get("effort"):
        cmd += ["-c", f'model_reasoning_effort="{row["effort"]}"']
    if resume:
        cmd += [resume, prompt]
    else:
        cmd += ["-s", "workspace-write", "--cd", str(cwd), prompt]
    return cmd


def spawn_process(host: str, cmd: list[str], cwd: pathlib.Path, home: str | None) -> dict:
    env = dict(os.environ)
    for spec in corpus.HOST_HOMES.values():
        env.pop(spec["env"], None)
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    if host == "codex":
        env["CODEX_HOME"] = home
    started = time.time()
    # The parent runs in the DEPLOYED home (no CLAUDE_CONFIG_DIR override), so it
    # authenticates itself the way an operator's own session does. The fd channel is
    # used when a token is available (a long-lived setup-token outlives a batch); when
    # the keychain refuses this process (ACL, rc=51) the run proceeds without it and
    # says so, because the process's own login is what the shell probes proved works.
    auth_note = None
    try:
        channel = corpus.auth_channel(host)
        auth_add, pass_fds = channel.__enter__()
    except corpus.CorpusError as exc:
        channel, auth_add, pass_fds = None, {}, ()
        auth_note = f"no token channel ({str(exc).splitlines()[0][:80]}); process self-authenticates"
    try:
        try:
            proc = subprocess.run(cmd, cwd=cwd, env={**env, **auth_add},
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=TIMEOUT, pass_fds=pass_fds)
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, rc = "", "timeout", None
    finally:
        if channel is not None:
            channel.__exit__(None, None, None)
    parsed = {}
    if stdout.strip():
        try:
            parsed = dispatch._parse_claude(stdout) if host == "claude" else dispatch._parse_codex(stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            parsed = {"parse_error": f"{type(exc).__name__}: {exc}"}
    rec = {"cmd": cmd, "returncode": rc, "elapsed_s": round(time.time() - started, 1),
           "session_id": parsed.get("session_id"), "result_text": parsed.get("result_text", ""),
           "stderr_tail": stderr[-600:], "parse_error": parsed.get("parse_error"),
           "auth_note": auth_note}
    if host == "claude" and stdout.strip() and not parsed.get("parse_error"):
        rec["wrapper"] = usage.claude_wrapper(stdout)
    if rc is None or rc != 0 or parsed.get("parse_error") or corpus.is_auth_failure(stdout + stderr):
        rec["status"] = ("defect:timeout" if rc is None else
                         "defect:auth" if corpus.is_auth_failure(stdout + stderr) else
                         f"defect:rc{rc}" if rc else "defect:parse")
    else:
        rec["status"] = "ok"
    return rec


# ----------------------------------------------------------------------------- packets
def spawn_how(host: str, arm: str) -> str:
    spec = ARMS[arm]
    if spec["mechanism"] == "fork":
        if host == "claude":
            return 'use the Agent tool with subagent_type "fork" (no model, no other agent)'
        return 'call spawn_agent with fork_turns "all" (no agent_type, no model)'
    name = CHILD_NAMES[spec["child_tier"]]
    if host == "claude":
        return f'use the Agent tool with subagent_type "{name}"'
    return f'call spawn_agent with agent_type "{name}" and fork_turns "none"'


# The parent holds a run-unique canary that is in no packet and on no disk (control 8):
# every child is asked to open its report with it; a fork must return it, an isolated
# child must return NONE. The line asking is part of the pinned brief templates.
CANARY_LINE = "CANARY: {canary}  (this token exists only in this conversation)\n"
PARENT_PREAMBLE = """Run {nonce}.
{canary_line}You are the parent seat of a delegated run. Do not edit any file yourself in this turn.
"""
SOLVE_PROMPT = PARENT_PREAMBLE + """1. Spawn exactly one child: {how}. Its working directory is this one.
   Give it the text between the BRIEF markers VERBATIM as its whole prompt — do not
   paraphrase, add, or omit a line.
---BRIEF---
{brief}
---END BRIEF---
2. Wait for the child to finish.
3. Report the child's final report verbatim. Do nothing else.
"""
INLINE_PROMPT = """Run {nonce}.
{canary_line}You are doing this work yourself. Do not spawn anything. The task, exactly:
---BRIEF---
{brief}
---END BRIEF---
Do it now in this working directory, run the verification yourself, and report.
"""
FORK_TASK = protocol.FORK_TASK
REPAIR_SUFFIX = protocol.REPAIR_SUFFIX
SELF_VERIFY_PROMPT = """Run {nonce}, repair pass {i}.
{canary_line}The verifier reports these items still failing: {items}. Do not edit any file yourself.
Spawn exactly one child again — {how} — with the text between the BRIEF markers VERBATIM
as its whole prompt, wait for it, and report its final report verbatim.
---BRIEF---
{brief}
---END BRIEF---
"""
INLINE_REPAIR_PROMPT = """Run {nonce}, repair pass {i}.
The verifier reports these items still failing their visible tests: {items}. Repair them
yourself: edit only pkg/mod.py, keep _normalize's contract, run
`python3 -m pytest tests_visible tests_regression -q`, and report. Do not spawn anything.
"""
PARENT_REPAIR_PROMPT = """Run {nonce}, parent repair.
The verifier reports these items failing their visible tests: {items}. Repair them
yourself now: edit only pkg/mod.py, keep the shared helper _normalize's contract, then
run `python3 -m pytest tests_visible tests_regression -q` and report the result. Do not
spawn anything.
"""


brief_text = protocol.brief_text


def canary_answer(host: str, path: pathlib.Path) -> str | None:
    """The CANARY= line of the child's final report, from its own artifact."""
    last = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if host == "claude":
                if d.get("type") == "assistant":
                    c = (d.get("message") or {}).get("content") or []
                    t = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if t.strip():
                        last = t
            else:
                p = d.get("payload") or {}
                if d.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "assistant":
                    last = "\n".join(b.get("text", "") for b in p.get("content") or [] if isinstance(b, dict))
    if not last:
        return None
    m = re.search(r"CANARY\s*=\s*([A-Za-z0-9_-]+)", last)
    return m.group(1) if m else None


# ----------------------------------------------------------------------------- artifacts
def read_participants(host: str, ident: str, project_dir: pathlib.Path | None,
                      home: str | None) -> list:
    if host == "claude":
        return usage.claude_participants(project_dir, ident)
    return usage.codex_participants(pathlib.Path(home), ident)


def child_received_text(host: str, path: pathlib.Path, parent_path: pathlib.Path | None = None,
                        spawn_index: int = 0) -> tuple[str, str]:
    """The packet the child received, and where it was read from.

    Claude: the subagent transcript's first user record IS the Agent prompt (artifact).
    Codex: the child's rollout stores the parent's message as `encrypted_content`
    (measured 2026-09-04), so the text is read from the PARENT rollout's spawn_agent
    call arguments — still a host artifact, not this runner's intent — and the
    provenance says so. `spawn_index` picks the k-th spawn call for the k-th child."""
    if host == "claude":
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "user":
                    continue
                c = (d.get("message") or {}).get("content")
                if isinstance(c, str):
                    return c, "child artifact"
                if isinstance(c, list):
                    return "\n".join(b.get("text", "") for b in c
                                     if isinstance(b, dict) and b.get("type") == "text"), "child artifact"
        return "", "child artifact (no user record)"
    # Codex encrypts inter-agent messages at rest in BOTH rollouts — the child's copy
    # is `encrypted_content` and the parent's spawn_agent `arguments.message` is the
    # same ciphertext (measured 2026-09-04, codex-cli 0.153.0); the exec --json stream
    # carries no spawn text either. So the brief a Codex child received has no host
    # artifact to read from; what exists is the spawn call's COUNT and its plaintext
    # agent_type/fork_turns, which is what this returns, and the brief half of
    # control 4 is disclosed as launch-only on Codex rather than receipted.
    calls = []
    with open(parent_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "spawn_agent" not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = d.get("payload") or {}
            if d.get("type") == "response_item" and p.get("name") == "spawn_agent" \
                    and p.get("type") in ("function_call", "custom_tool_call"):
                try:
                    args = json.loads(p.get("arguments") or p.get("input") or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append(args)
    if spawn_index < len(calls):
        a = calls[spawn_index]
        return "", (f"unreadable: encrypted at rest; spawn #{spawn_index + 1} was agent_type="
                    f"{a.get('agent_type')!r} fork_turns={a.get('fork_turns')!r}")
    return "", f"parent artifact has {len(calls)} spawn_agent call(s), wanted index {spawn_index}"


def claude_spawn_type(parent_path: pathlib.Path, spawn_index: int) -> str | None:
    """The k-th Agent tool call's `subagent_type` in a Claude parent transcript — the
    plaintext half of control 4 on Claude: an isolated arm must have spawned its named
    child, a fork arm must have spawned "fork"."""
    calls = []
    with open(parent_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"Agent"' not in line and "subagent_type" not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = ((d.get("message") or {}).get("content")) if d.get("type") == "assistant" else None
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Agent":
                    calls.append((b.get("input") or {}).get("subagent_type"))
    return calls[spawn_index] if spawn_index < len(calls) else None


def spawn_args(parent_path: pathlib.Path, spawn_index: int) -> dict:
    """The k-th spawn_agent call's plaintext arguments in a Codex parent rollout."""
    _, prov = child_received_text("codex", parent_path, parent_path, spawn_index)
    return {"provenance": prov}


def child_body_receipt(host: str, path: pathlib.Path, launch_body: str) -> dict:
    """Body provenance per host. Codex: the child's rollout carries the template's
    developer_instructions in turn_context (artifact). Claude: the subagent transcript
    carries no system prompt; the meta.json names the agent type, and the body is the
    one this runner registered under that name (launch argv)."""
    if host == "codex":
        # The template's developer_instructions arrive as the child's first
        # `role: developer` message — an artifact-level receipt. The host appends its
        # own blocks after the body in a writable sandbox (measured 2026-09-04:
        # <skills_instructions>, <permissions instructions>, <plugins_instructions>,
        # ~13K chars), so the receipt is a PREFIX equality on the pinned body and the
        # appended length is reported, never hashed into the body.
        # The body sits inside the child's first developer message, but not always at
        # its start: a child on a model other than its parent's gets the new model's
        # base instructions wrapped in `<model_switch>…</model_switch>` FIRST, and the
        # template body follows in the same message (measured 2026-09-04, sol -> terra:
        # body at char 17,885 of 32,522; another run of the same seats had it at 0). The
        # host then appends its own blocks (<skills_instructions>, permissions,
        # plugins) without the body's final newline. The receipt is therefore: the
        # rstripped body occurs in a developer message either at its start or
        # immediately after a closing </model_switch>; anything else before it is not
        # the host's preamble and refuses. Offsets and lengths are reported.
        core = launch_body.rstrip("\n")
        devs = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                p = d.get("payload") or {}
                if d.get("type") == "response_item" and p.get("type") == "message" \
                        and p.get("role") == "developer":
                    devs.append("".join(b.get("text", "") for b in p.get("content") or []
                                        if isinstance(b, dict)))
        for k, text in enumerate(devs):
            i = text.find(core)
            if i < 0:
                continue
            before = text[:i]
            if before == "" or before.rstrip().endswith("</model_switch>"):
                return {"provenance": "artifact", "sha256": pinmod._sha_text(launch_body),
                        "developer_index": k, "body_offset": i,
                        "preceded_by": "<model_switch> block" if before else None,
                        "host_appended_chars": len(text.rstrip("\n")) - i - len(core)}
            return {"provenance": "artifact", "sha256": pinmod._sha_text(text),
                    "why": f"developer message {k} carries the body at char {i} after text "
                           f"that is not the host's model-switch preamble: {before[:60]!r}"}
        if devs:
            return {"provenance": "artifact", "sha256": pinmod._sha_text(devs[0]),
                    "why": f"none of {len(devs)} developer message(s) carries the pinned body",
                    "openings": [t.split("\n", 1)[0][:40] for t in devs]}
        return {"provenance": "artifact", "sha256": None, "why": "no developer message"}
    meta = path.with_suffix(".meta.json")
    agent_type = json.loads(meta.read_text()).get("agentType") if meta.is_file() else None
    return {"provenance": "launch", "agent_type": agent_type,
            "sha256": pinmod._sha_text(launch_body) if agent_type in CHILD_NAMES.values() else None}


def delta_participant(before: dict, now, role: str):
    """The requests a participant added during one pass, as its own Participant."""
    n = before.get(now.id, 0)
    reqs = now.requests[n:]
    return usage.Participant(now.id, now.host, role, now.artifact, reqs, terminal=now.terminal,
                             completeness=None,
                             models=sorted({r.model for r in reqs if r.model}),
                             efforts=sorted({r.effort for r in reqs if r.effort}),
                             notes=list(now.notes))


# ----------------------------------------------------------------------------- probes
def probe(host: str, out: pathlib.Path, seats: list[dict]) -> dict:
    """Per seat: one uncounted priming request, then a measured fresh request whose
    first-request kinds are the seat's standing-prefix reference. Claude: both cost
    estimators and the known-opposite spread; Codex: the differential disclosure."""
    cwd = out / "probe-cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    home = None
    if host == "codex":
        home = codex_home(out / "probe-home", {}, reuse=True)["home"]   # a probe spawns no child
    project = claude_project_dir(cwd)
    result = {"host": host, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seats": {}}
    for row in seats:
        key = f"{row['model']}/{row.get('effort') or 'n/a'}"
        runs = []
        # Two primings, then the measurement: on Claude the read part grew ~3-4K between
        # the first and second fresh run in a directory (opus 11,815 -> 15,027; haiku
        # 14,952 -> 19,314 on 2026-09-04) and held on the third, so one priming measures
        # a prefix still settling. The three reads are all recorded, and a last step that
        # still moved past the band's own tolerance is disclosed as unstable.
        for phase in ("prime", "prime2", "measure"):
            cmd = parent_cmd(host, row, "Reply with exactly: pong", cwd)
            if host == "claude":
                cmd.insert(-1, "--max-turns"); cmd.insert(-1, "1")
            rec = spawn_process(host, cmd, cwd, home)
            if rec["status"] != "ok" or not rec["session_id"]:
                raise RunError(f"{key} {phase}: {rec['status']} {rec['stderr_tail'][-200:]}")
            parts = read_participants(host, rec["session_id"], project, home)
            parent = parts[0]
            entry = {"phase": phase, "session_id": rec["session_id"],
                     "first_request": parent.requests[0].kinds if parent.requests else None,
                     "models": parent.models, "efforts": parent.efforts,
                     "modelled_usd": usage.price_run(parts)["usd"], "notes": parent.notes}
            if host == "claude":
                entry["measured_usd"] = rec["wrapper"]["total_cost_usd"]
                entry["reconciliation"] = usage.reconcile(parts, entry["measured_usd"])
            runs.append(entry)
        m = runs[-1]
        prev = runs[-2]["first_request"]["cache_read"]
        unstable = probes.cache_band_flag(m["first_request"]["cache_read"], prev) if prev else None
        result["seats"][key] = {
            "row": row, "runs": runs,
            "standing_prefix": m["first_request"]["cache_read"],
            "reads": [r["first_request"]["cache_read"] for r in runs],
            "unstable": (f"the measured read still moved past the band vs the prior run: {unstable}"
                         if unstable else None),
            "seat_receipt": pinmod.check_seat(
                usage.Participant("probe", host, "parent", "", [], True, None,
                                  m["models"], m["efforts"]), row),
        }
    keys = list(result["seats"])
    if host == "claude" and len(keys) >= 2:
        dear, cheap = result["seats"][keys[0]]["runs"][-1], result["seats"][keys[-1]]["runs"][-1]
        result["known_opposite"] = {
            "pair": [keys[0], keys[-1]], "min_ratio": 5.0,
            "measured": probes.known_opposite_spread(cheap["measured_usd"], dear["measured_usd"], 5.0),
            "modelled": probes.known_opposite_spread(cheap["modelled_usd"], dear["modelled_usd"], 5.0),
            "ratio_measured": dear["measured_usd"] / cheap["measured_usd"],
            "ratio_modelled": dear["modelled_usd"] / cheap["modelled_usd"],
            "both_reconcile": all(r["reconciliation"]["ok"] for r in (dear, cheap)),
        }
    if host == "codex":
        result["differential"] = {k: v["runs"][-1]["notes"] for k, v in result["seats"].items()}
    return result


def load_prefixes(host: str) -> dict:
    p = OUT / f"stage0-probes-{host}.json"
    if not p.is_file():
        return {}
    d = json.loads(p.read_text())
    return {v["row"]["model"]: v["standing_prefix"] for v in d["seats"].values()}


# ----------------------------------------------------------------------------- one run
def prime(host: str, row: dict, cwd: pathlib.Path, home: str | None, n: int = 2,
          max_budget_usd: float | None = None) -> list:
    """Uncounted priming requests for a seat, in the run's own working directory with the
    run's own flags (design, "Cache order"; Stage 0: the read settles on the third
    byte-identical process in a directory). Their artifacts are not participants."""
    out = []
    for _ in range(n):
        cmd = parent_cmd(host, row, "Reply with exactly: pong", cwd, max_budget_usd=max_budget_usd)
        if host == "claude":
            cmd.insert(-1, "--max-turns"); cmd.insert(-1, "1")
        rec = spawn_process(host, cmd, cwd, home)
        out.append({"status": rec["status"], "session_id": rec["session_id"],
                    "cost_usd": (rec.get("wrapper") or {}).get("total_cost_usd")})
        if rec["status"] != "ok":
            raise RunError(f"priming: {rec['status']}: {rec['stderr_tail'][-200:]}")
    return out


def run(host: str, arm: str, m: int, seed: str, parent_tier: str, rundir: pathlib.Path,
        home: str | None = None, block: str | None = None, do_prime: bool = False,
        per_run_home: bool = False,
        timeout: int | None = None, fixture_src: pathlib.Path | None = None,
        budget_usd: float | None = None) -> dict:
    """One run of one arm. `fixture_src` is a block's pristine fixture to copy (a matched
    block shares its fixture across arms); without it a fixture is generated from
    `seed`. `home` is a prepared Codex home (shared by a stage); without it one is built
    for this run."""
    global TIMEOUT
    if timeout:
        TIMEOUT = timeout
    pin = pinmod.build_pin()
    spec = ARMS[arm]
    rows = rows_for(pin, host, arm, parent_tier)
    body = pinmod.child_body(REPO, host)
    agents = child_agents(pin, host, body)
    proto = spec["protocol"]
    nonce = secrets.token_hex(6)
    canary = "CN" + secrets.token_hex(5)
    rundir.mkdir(parents=True, exist_ok=True)
    fx = rundir / "fixture"
    # The fixture on disk is the WORKDIR only. The oracle is regenerated from the seed
    # into a scoring tree after the last participant has exited, and removed again once
    # scored, so no run — this one or a sibling of the same block — has an answer key on
    # disk while a seat runs (`D-20260904-4ccdf9`).
    if fixture_src:
        if fx.exists():
            shutil.rmtree(fx)
        shutil.copytree(fixture_src, fx)
        manifest = json.loads((fx / "manifest.json").read_text())
        fixture_seed = manifest["seed"]
    else:
        fixture_seed = f"{seed}:{nonce}"
        manifest = fixture_gen.generate(fx, m, fixture_seed, parts=("workdir",))
    workdir = fx / "workdir"
    if (fx / "oracle").exists():
        raise RunError(f"an oracle is on disk at {fx / 'oracle'} before the run — refused")
    scoring = rundir / "oracle-scoring"

    def oracle():
        # materialised by protocol.drive only when scoring begins
        if scoring.exists():
            shutil.rmtree(scoring)
        fixture_gen.generate(scoring, m, fixture_seed, parts=("oracle",))
        return scoring / "oracle"
    project = claude_project_dir(workdir)
    home_rec = None
    agents_json = ""
    if host == "codex":
        if home is None:
            home_rec = codex_home(rundir / "home", agents)
            home = home_rec["home"]
        elif per_run_home:
            # `home` is the stage template; the run gets its own (D-20260905-aec4cd)
            home_rec = run_home(pathlib.Path(home), rundir / "home")
            home = home_rec["home"]
        else:
            home_rec = {"home": home, "shared": True}
    else:
        agents_json = claude_agents_json(agents)
    prefixes = load_prefixes(host)
    record = {
        "host": host, "arm": arm, "mechanism": spec["mechanism"], "m": m, "block": block,
        "nonce": nonce, "rows": rows, "protocol": proto, "pin": pin,
        "child_body_sha256": pinmod._sha_text(body), "parent_tier": parent_tier,
        "evidence_run": parent_tier == "helm", "codex_home": home_rec, "manifest": manifest,
        "passes": [], "dispatches": [], "flags": {}, "problems": [], "priming": None,
    }
    record["budget_usd"] = budget_usd

    def remaining_cap() -> float | None:
        # the run's reserve less what its earlier processes reported (the host wrapper's
        # own total), so the run as a whole stays under the reserve (round 3, F7)
        if budget_usd is None:
            return None
        spent = 0.0
        for d in record["dispatches"]:
            w = _charge((d.get("wrapper") or {}).get("total_cost_usd"))
            if w is None:
                raise RunError("a dispatch of this run reported no usable charge — the run stops before another process (fix review 5 F5, fix review 6 F4)")
            spent += w
        for p_ in (record.get("priming") or []):
            c = _charge(p_.get("cost_usd")) if isinstance(p_, dict) else None
            if c is None:
                # an unknown, negative or non-finite priming charge is unknown, never zero:
                # no further process is started under a cap computed from a guess
                raise RunError("a priming process of this run reported no usable charge — the run stops before another process")
            spent += c
        left = round(budget_usd - spent, 4)
        if left <= 0:
            raise RunError(f"run reserve ${budget_usd:.2f} exhausted after ${spent:.4f} — the run stops before another process")
        return left
    if do_prime:
        # one priming process at a time, each under what the run still has (round 4, F1)
        record["priming"] = []
        for _ in range(2):
            record["priming"] += prime(host, rows["parent"], workdir, home, n=1, max_budget_usd=remaining_cap())
    roles = INLINE_ROLES if spec["mechanism"] == "none" else EXPECTED_ROLES
    child_name = CHILD_NAMES[spec["child_tier"]] if spec["child_tier"] and spec["mechanism"] == "isolated" else None
    canary_line = CANARY_LINE.format(canary=canary)
    state = {"session": None, "seen": {}, "children": set(), "pass_no": 0}
    flags = {"cache_band": None, "reconciliation": None, "codex_differential": None,
             "output_dominance": None, "brief_receipt": None, "inheritance": None}
    measured_total = 0.0

    def solver(phase: str, failing: list, wd: pathlib.Path):
        nonlocal measured_total
        state["pass_no"] += 1
        i = state["pass_no"]
        how = spawn_how(host, arm) if spec["mechanism"] != "none" else ""
        if phase == "solve":
            brief = brief_text(nonce, proto, manifest)
            if spec["mechanism"] == "none":
                prompt = INLINE_PROMPT.format(nonce=nonce, canary_line=canary_line, brief=brief)
            else:
                prompt = SOLVE_PROMPT.format(nonce=nonce, canary_line=canary_line, how=how, brief=brief)
            cmd = parent_cmd(host, rows["parent"], prompt, workdir, agents_json, max_budget_usd=remaining_cap())
        elif phase == "self_verify":
            brief = brief_text(nonce, proto, manifest, (i, failing))
            if spec["mechanism"] == "none":
                prompt = INLINE_REPAIR_PROMPT.format(nonce=nonce, i=i, items=", ".join(failing))
            else:
                prompt = SELF_VERIFY_PROMPT.format(nonce=nonce, i=i, canary_line=canary_line,
                                                   items=", ".join(failing), how=how, brief=brief)
            cmd = parent_cmd(host, rows["parent"], prompt, workdir, agents_json, resume=state["session"], max_budget_usd=remaining_cap())
        else:
            brief = None
            prompt = PARENT_REPAIR_PROMPT.format(nonce=nonce, items=", ".join(failing))
            cmd = parent_cmd(host, rows["parent"], prompt, workdir, agents_json, resume=state["session"], max_budget_usd=remaining_cap())
        rec = spawn_process(host, cmd, workdir, home)
        rec["phase"] = phase
        record["dispatches"].append({k: v for k, v in rec.items() if k != "cmd"} | {"cmd": cmd[:-1]})
        if rec["status"] != "ok":
            raise RunError(f"pass {i} ({phase}): {rec['status']}: {rec['stderr_tail'][-300:]}")
        if phase == "solve":
            state["session"] = rec["session_id"]
        elif host == "claude" and rec["session_id"] != state["session"]:
            raise RunError(f"pass {i}: resume changed the session id "
                           f"{state['session']} -> {rec['session_id']}")
        if host == "claude":
            measured_total += rec["wrapper"]["total_cost_usd"] or 0.0
        parts = read_participants(host, state["session"], project, home)
        parent_now = [p for p in parts if p.role == "parent"][0]
        new_children = [p for p in parts if p.role == "child" and p.id not in state["children"]]
        passes = []
        problems = []
        pd = delta_participant(state["seen"], parent_now, "parent")
        if not pd.requests:
            problems.append(f"pass {i} ({phase}): the parent made no request")
        passes.append(protocol.PassRecord(pd.id, host, "parent", rows["parent"]["model"],
                                          rows["parent"].get("effort") or "", phase, pd))
        problems += [f"pass {i} parent: {x}" for x in pinmod.check_seat(pd, rows["parent"])]
        want_child = "child" in roles[phase]
        if want_child and len(new_children) != 1:
            problems.append(f"pass {i} ({phase}): expected exactly one new child, found "
                            f"{len(new_children)} — declared participant child-{i} produced no pass"
                            if not new_children else
                            f"pass {i} ({phase}): expected one new child, found {len(new_children)}")
        if not want_child and new_children:
            problems.append(f"pass {i} ({phase}): {len(new_children)} undeclared child(ren) acted"
                            + (" — the inline arm spawned" if spec["mechanism"] == "none" else ""))
        for c in new_children:
            state["children"].add(c.id)
            passes.append(protocol.PassRecord(c.id, host, "child", rows["child"]["model"],
                                              rows["child"].get("effort") or "", phase, c))
            problems += [f"pass {i} child: {x}" for x in pinmod.check_seat(c, rows["child"])]
            received, prov = child_received_text(host, pathlib.Path(c.artifact),
                                                 pathlib.Path(parent_now.artifact),
                                                 len(state["children"]) - 1)
            entry = {"pass": i, "phase": phase, "child": c.id,
                     "child_received_sha256": pinmod._sha_text(received), "child_received_from": prov}
            if host == "claude":
                stype = claude_spawn_type(pathlib.Path(parent_now.artifact), len(state["children"]) - 1)
                want_type = "fork" if spec["mechanism"] == "fork" else child_name
                if stype != want_type:
                    problems.append(f"pass {i} child {c.id}: the Agent call's subagent_type was "
                                    f"{stype!r}, the arm requires {want_type!r}")
                entry["subagent_type"] = stype
            if spec["mechanism"] == "isolated":
                # the Agent tool hands the prompt over without its trailing newline
                # (measured 2026-09-04: 1261 vs 1262 bytes), so equality is on stripped text
                if brief and host == "claude":
                    how = protocol.brief_match(brief, received)
                    entry["brief_match"] = how
                    if how is None:
                        problems.append(f"pass {i} child {c.id}: received brief is not the pinned "
                                        f"{proto!r} rendering (control 4; read from {prov})")
                    elif how == "escaped":
                        # the helm seat transcribes a brief it relays (entities, backslashes);
                        # equal up to that escaping is the pinned brief (D-20260905-fd9177)
                        flags["brief_escaped"] = (f"pass {i} child {c.id}: the parent's Agent call transcribed "
                                                  f"the brief; equal up to escaping (read from {prov})")
                if brief and host == "codex":
                    if f"agent_type={child_name!r}" not in prov or "fork_turns='none'" not in prov:
                        problems.append(f"pass {i} child {c.id}: spawn was not an isolated "
                                        f"{child_name} spawn — {prov}")
                    flags["brief_receipt"] = f"codex: brief text is launch-only provenance ({prov})"
                bodyr = child_body_receipt(host, pathlib.Path(c.artifact), body)
                if bodyr.get("sha256") != record["child_body_sha256"]:
                    problems.append(f"pass {i} child {c.id}: body receipt {bodyr} != pinned "
                                    f"{record['child_body_sha256'][:12]}")
                entry["body_receipt"] = bodyr
            else:
                # a fork inherits the body; the spawn's plaintext half must say fork_turns all
                if host == "codex" and "fork_turns='all'" not in prov:
                    problems.append(f"pass {i} child {c.id}: spawn was not a fork — {prov}")
                entry["body_receipt"] = {"provenance": "inherited"}
            # control 8, disclosing: the canary discriminates fork from isolated
            got = canary_answer(host, pathlib.Path(c.artifact))
            want = canary if spec["mechanism"] == "fork" else "NONE"
            entry["inheritance"] = {"expected": want, "got": got, "ok": got == want}
            if got != want:
                flags["inheritance"] = (f"pass {i} child: expected {want!r}, got {got!r} — "
                                        f"{'a fork that did not inherit' if want != 'NONE' else 'an isolated child that saw the parent context'}")
            ref = prefixes.get(rows["child"]["model"])
            if not ref:
                flags["cache_band"] = (f"not checked: no standing-prefix reference for "
                                       f"{rows['child']['model']} (run `live.py probe` first)")
            elif c.requests:
                fl = probes.cache_band_flag(c.requests[0].kinds["cache_read"], ref)
                if fl:
                    flags["cache_band"] = f"pass {i} child: {fl}"
            record["passes"].append(entry)
        if phase == "solve" and pd.requests:
            ref = prefixes.get(rows["parent"]["model"])
            if not ref:
                flags["cache_band"] = (f"not checked: no standing-prefix reference for "
                                       f"{rows['parent']['model']} (run `live.py probe` first)")
            else:
                fl = probes.cache_band_flag(pd.requests[0].kinds["cache_read"], ref)
                if fl:
                    flags["cache_band"] = f"pass {i} parent: {fl}"
        state["seen"] = {p.id: len(p.requests) for p in parts}
        record["problems"] += problems
        if want_child and not new_children:
            record.setdefault("declared_extra", []).append(f"{host}:child-{i}")
        return passes

    def declared_after(passes):
        return sorted({p.participant_id for p in passes}) + record.get("declared_extra", [])

    res = protocol.drive(workdir, oracle, manifest, solver, declared_after)
    if scoring.exists():
        shutil.rmtree(scoring)   # scored; the key does not stay on disk for the next run
    parts_all = [p.as_participant() for p in res.passes]
    if host == "claude":
        rec = usage.reconcile(parts_all, measured_total)
        record["reconciliation"] = rec
        if not rec["ok"]:
            flags["reconciliation"] = (f"modelled {rec['modelled']:.4f} vs measured "
                                       f"{rec['measured']:.4f} (rel {rec['rel_err']})")
    else:
        notes = [n for p in parts_all for n in p.notes]
        if notes:
            flags["codex_differential"] = "; ".join(notes[:3])
    share = usage.output_priced_share(parts_all) if parts_all else None
    flags["output_dominance"] = probes.output_dominance_flag(share)
    record["output_priced_share"] = share
    record["flags"] = flags
    record["result"] = {"reached": res.reached, "reached_at": res.reached_at,
                        "cost_to_parity": res.cost_to_parity, "ledger": res.ledger,
                        "score": res.score, "problems": res.problems + record["problems"]}
    record["measured_total_usd"] = measured_total if host == "claude" else None
    art = rundir / "artifacts"
    if art.exists():
        shutil.rmtree(art)
    art.mkdir()
    for p in read_participants(host, state["session"], project, home):
        shutil.copy2(p.artifact, art / pathlib.Path(p.artifact).name)
        meta = pathlib.Path(p.artifact).with_suffix(".meta.json")
        if meta.is_file():
            shutil.copy2(meta, art / meta.name)
    record["artifacts"] = {"dir": str(art), "session": state["session"],
                           "project_dir": str(project), "home": home,
                           "declared": declared_after(res.passes)}
    # Control 10, second half: what the participants READ, from their own artifacts.
    apply_access_scan(record, level.access_scan(art, workdir, (home,) if home else ()))
    (rundir / "record.json").write_text(json.dumps(record, indent=1, default=str))
    (rundir / "verdict.txt").write_text("\n".join(verdict_lines(record)) + "\n")
    (OUT / "last-run.txt").write_text(str(rundir))
    return record


def _charge(x) -> float | None:
    """A live charge as a process reported it: a finite, non-negative number, or None —
    a negative or NaN figure would widen the next process's cap (fix review 6, F4)."""
    if x is None or isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(float(x)) and float(x) >= 0 else None


def apply_access_scan(record: dict, scan: dict) -> None:
    """Write the access receipt onto the record. The hits void the run (they join its
    problems); the measured level STAYS on the record. Voiding is a judgement on the
    receipt under one scan rule, and the aggregator re-scans under the current rule at
    load — a level discarded here could only be restored by scoring again with the key
    back on disk (round 4 found the live scan discarding it)."""
    access = scan.pop("problems")
    record["access_scan"] = scan
    if scan["notes"]:
        record["flags"]["access_notes"] = f"{scan['notes']} disclosed access(es) (git, scratch), e.g. {scan['note_lines'][0][:90]}"
    if access:
        record["result"]["problems"] = record["result"]["problems"] + access


def verdict_lines(record: dict) -> list[str]:
    r = record["result"]
    lines = probes.verdict_header(record["flags"])
    lines.append(f"run {record['host']}/{record['arm']} m={record['m']} nonce={record['nonce']} "
                 f"evidence_run={record['evidence_run']}")
    if r["problems"]:
        lines.append(f"BLOCKED ({len(r['problems'])} problem(s)):")
        lines += [f"  x {p}" for p in r["problems"]]
    lines.append(f"done-when reached={r['reached']} at={r['reached_at']} "
                 f"cost_to_parity={r['cost_to_parity']}")
    if r["score"].get("scored"):
        lines.append(f"level defects={r['score']['level_defects']} "
                     f"(held-out {r['score']['level']['heldout_failures']}/"
                     f"{r['score']['level']['heldout_total']}, regression "
                     f"{r['score']['level']['regression_failures']}, static "
                     f"{r['score']['level']['static_errors']})")
    else:
        lines.append(f"level: not scored — {r['score'].get('why')}")
    for row in r["ledger"].get("participants", []):
        lines.append(f"  {row['role']:6} {row['id'][:34]:34} {row['models']} {row['efforts']} "
                     f"req={row['requests']} kinds={row['kinds']}")
    if record.get("reconciliation"):
        lines.append(f"reconciliation: {record['reconciliation']}")
    return lines


# ----------------------------------------------------------------------------- plants
def plants(rundir: pathlib.Path) -> int:
    """Control 0's two planted cases on COPIES of a real run's artifacts: the child
    artifact missing, and the child artifact cut before its terminal record. Each must
    fail the ledger by name."""
    record = json.loads((rundir / "record.json").read_text())
    host = record["host"]
    art = pathlib.Path(record["artifacts"]["dir"])
    declared = record["artifacts"]["declared"]
    child_files = [f for f in sorted(art.iterdir())
                   if f.suffix == ".jsonl" and _is_child(host, f)]
    if not child_files:
        print("plants: no child artifact in the record — nothing to plant on")
        return 2
    ok = 0

    def ledger_of(folder: pathlib.Path) -> dict:
        parts = _participants_from_copy(host, folder, record)
        passes = [protocol.PassRecord(p.id, host, p.role, "", "", "solve", p) for p in parts]
        return protocol.run_ledger(passes, declared)

    import tempfile
    base = pathlib.Path(tempfile.mkdtemp(prefix="tier-plants-"))
    try:
        # positive control: the untouched copy ledgers clean
        clean = base / "clean"; shutil.copytree(art, clean)
        lg = ledger_of(clean)
        if lg["problems"]:
            print(f"positive control FAILED: the untouched artifacts ledger unclean: {lg['problems']}")
            return 1
        print("positive control: untouched artifacts ledger clean")
        # plant A: child artifact missing
        a = base / "missing"; shutil.copytree(art, a)
        for f in child_files:
            (a / f.name).unlink()
        lg = ledger_of(a)
        hit = [p for p in lg["problems"] if "no pass" in p or "produced no pass" in p]
        print(("PLANT missing-child: refused by name — " + hit[0]) if hit else
              f"PLANT missing-child: NOT refused: {lg['problems']}")
        ok += bool(hit)
        # plant B: child artifact cut before its terminal record
        b = base / "cut"; shutil.copytree(art, b)
        for f in child_files:
            _cut_before_terminal(host, b / f.name)
        lg = ledger_of(b)
        hit = [p for p in lg["problems"] if "no terminal record" in p]
        print(("PLANT cut-child: refused by name — " + hit[0]) if hit else
              f"PLANT cut-child: NOT refused: {lg['problems']}")
        ok += bool(hit)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok == 2 else 1


def _is_child(host: str, f: pathlib.Path) -> bool:
    if host == "claude":
        return f.name.startswith("agent-")
    head = f.open(encoding="utf-8", errors="replace").readline()
    return '"parent_thread_id":"' in head.replace(" ", "") and \
        '"parent_thread_id":null' not in head.replace(" ", "")


def _participants_from_copy(host: str, folder: pathlib.Path, record: dict) -> list:
    parts = []
    for f in sorted(folder.iterdir()):
        if f.suffix != ".jsonl":
            continue
        if host == "claude":
            role = "child" if f.name.startswith("agent-") else "parent"
            pid = f"claude:{f.stem}" if role == "child" else f"claude:{record['artifacts']['session']}"
            parts.append(usage._claude_participant(f, role, pid))
        else:
            parts.append(usage._codex_participant(f, "child" if _is_child(host, f) else "parent"))
    return parts


def _cut_before_terminal(host: str, path: pathlib.Path) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    keep = []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            keep.append(line); continue
        if host == "claude" and d.get("type") == "assistant" and \
                (d.get("message") or {}).get("stop_reason"):
            continue   # drop every stop-bearing record: the artifact is now open-ended
        if host == "codex" and d.get("type") == "event_msg" and \
                (d.get("payload") or {}).get("type") == "task_complete":
            continue
        keep.append(line)
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- stage 1
def counterbalanced(arms: list[str], rep: int) -> list[str]:
    """Arms rotate within each matched block so no arm always runs first (design, "Cache
    order"); rep r starts at position r, so over R reps each arm takes R positions."""
    k = rep % len(arms)
    return arms[k:] + arms[:k]


class Vault:
    """Seals a finished run's solved workdir and artifacts while later seats of the same
    stage run, and unseals them when the stage ends. A one-time pad from `secrets`, held
    in this process only — never on disk — so a seat that finds the sealed file has
    ciphertext; the scan cannot name a read whose path is built from variables, so the
    solutions are not there to read (round 7). A stage that dies keeps its pads with it:
    what it had sealed stays sealed, and state.json names it."""

    def __init__(self):
        self.pads: dict[str, bytes] = {}

    @staticmethod
    def _pack(d: pathlib.Path) -> bytes:
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.add(d, arcname=d.name)
        return buf.getvalue()

    @staticmethod
    def _xor(a: bytes, b: bytes) -> bytes:
        return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")

    def seal(self, d: pathlib.Path) -> pathlib.Path:
        data = self._pack(d)
        pad = secrets.token_bytes(len(data))
        sealed = d.parent / (d.name + ".sealed")
        sealed.write_bytes(self._xor(data, pad))
        shutil.rmtree(d)
        self.pads[str(sealed)] = pad
        return sealed

    def unseal(self, sealed: pathlib.Path) -> pathlib.Path:
        import io, tarfile
        pad = self.pads.pop(str(sealed))
        data = self._xor(sealed.read_bytes(), pad)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
            tar.extractall(sealed.parent, filter="data")
        sealed.unlink()
        return sealed.parent / sealed.name[:-len(".sealed")]

    def unseal_all(self) -> list[str]:
        out = []
        for s in list(self.pads):
            if pathlib.Path(s).is_file():
                self.unseal(pathlib.Path(s))
                out.append(s)
        return out


SEALED = ("fixture/workdir", "artifacts")   # what a finished run holds that solves its block


def seal_run(vault: Vault, rundir: pathlib.Path) -> list[str]:
    return [str(vault.seal(rundir / rel)) for rel in SEALED if (rundir / rel).is_dir()]


def sealed_without_pad(out: pathlib.Path, vault: Vault) -> list[str]:
    """Sealed files no pad in this process opens — a stage that died holding them."""
    return sorted(str(p) for p in (out / "runs").glob("*/**/*.sealed") if str(p) not in vault.pads) if (out / "runs").is_dir() else []


def unpriced(rec: dict) -> str | None:
    """Why a finished run has no ledger cost through no fault of its own: it reached, its
    access scan hit nothing, and its ledger could not be closed because a participant's
    transcript carried no terminal record when the run was read. Such a run is neither
    sound nor failed; a resume re-dispatches it like a failed dispatch and keeps the
    record beside the stage (D-20260908: M1-b6 delegated-workhorse)."""
    r = rec.get("result") or {}
    if not r.get("reached") or r.get("cost_to_parity") is not None:
        return None
    scan = rec.get("access_scan") or {}
    # a complete, current, clean scan — not a missing one (fix review 3, F6), not one
    # under an older rule or over zero calls (fix review 4, F10): those are rescanned by
    # `stage.load_records` before anything is concluded from them, and a park would
    # hide the run from that rescan
    if not scan or scan.get("hits") or scan.get("malformed") or not scan.get("checked"):
        return None
    if scan.get("rule") != level.RULE or int(scan.get("calls") or 0) < 1:
        return None
    if rec.get("problems") or r.get("problems"):
        return None
    problems = ((r.get("ledger") or {}).get("problems") if isinstance(r.get("ledger"), dict) else None) or []
    cut = [p_ for p_ in problems if "no terminal record" in str(p_)]
    if not cut or len(cut) != len(problems):
        return None
    return "; ".join(str(p_) for p_ in cut)


def park_unpriced(out: pathlib.Path, rundir: pathlib.Path) -> pathlib.Path | None:
    """Move an unpriced run's directory out of `runs/` (to `<out>/unpriced/<dir>-<n>`),
    where no reader or ledger scan finds it and nothing of it is lost; None when the
    record is priced or voided (it stays)."""
    rec = json.loads((rundir / "record.json").read_text())
    why = unpriced(rec)
    if why is None:
        return None
    dest_root = out / "unpriced"
    dest_root.mkdir(parents=True, exist_ok=True)
    n = 1
    while (dest_root / f"{rundir.name}-{n}").exists():
        n += 1
    dest = dest_root / f"{rundir.name}-{n}"
    shutil.move(str(rundir), str(dest))
    (dest / "unpriced.txt").write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} parked before re-dispatch: {why}\n")
    return dest


def stale_out(out: pathlib.Path) -> list[pathlib.Path]:
    """What a fresh declaration would silently inherit under `out`: records (skipped as
    done) and block fixtures (reused as this stage's) from another declaration (round 7)."""
    old = list((out / "runs").glob("*/record.json")) if (out / "runs").is_dir() else []
    old += list((out / "blocks").glob("*/manifest.json")) if (out / "blocks").is_dir() else []
    return sorted(old)


def generate_block(block_dir: pathlib.Path, host: str, block: str, m: int, name: str = "stage1") -> dict:
    """A block's pristine fixture (workdir only), its manifest stamped with the digest of
    the generator that wrote it — the receipt a rescore and a resumed stage read. The
    seed carries the stage's name: a later stage draws fresh blocks (design, *Staging*)."""
    man = fixture_gen.generate(block_dir, m, f"{name}:{host}:{block}", parts=("workdir",))
    man["generator_sha256"] = level.generator_sha256()
    (block_dir / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


BLOCK_DRAW_SLACK = 5   # draws past R a size may spend on voided blocks before it is NOT RUN


def block_validity(block_dir: pathlib.Path, m: int) -> list[str]:
    """The spawn-trigger design's block assertions (§Design, *Task and build surface*), on
    the pristine workdir before any seat runs: exactly M items; every visible test failing;
    a non-empty held-out set; the helper chain (item 0 calls the helper, item k > 0 calls
    item k − 1); at M = 1 one item and no chain. Deterministic — generation is seeded — so a
    failing block is voided at declaration and costs nothing. Returns the reasons (empty =
    valid)."""
    import ast
    why = []
    man = json.loads((block_dir / "manifest.json").read_text())
    if man.get("m") != m or len(man.get("items", [])) != m:
        why.append(f"manifest carries m={man.get('m')} with {len(man.get('items', []))} items, declared {m}")
    if not man.get("heldout_test_ids") or int(man.get("heldout_in_count") or 0) < 1:
        why.append("held-out set empty")
    work = block_dir / "workdir"
    try:
        tree = ast.parse((work / "pkg" / "mod.py").read_text())
    except (OSError, SyntaxError) as exc:
        return why + [f"stub unreadable: {exc}"]
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    items = [f"f{k}" for k in range(m)]
    extra = sorted(n for n in funcs if n.startswith("f") and n[1:].isdigit() and n not in items)
    if any(n not in funcs for n in items) or extra:
        why.append(f"stub defines {sorted(n for n in funcs if n.startswith('f'))}, declared {items}")
    if "_normalize" not in funcs:
        why.append("shared helper _normalize absent")
    for k, name in enumerate(items):
        fn = funcs.get(name)
        if fn is None:
            continue
        want = "_normalize" if k == 0 else f"f{k - 1}"
        calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        if want not in calls:
            why.append(f"{name} does not call {want}")
    if m == 1 and ("f1" in funcs or any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id.startswith("f")
                                       for c in ast.walk(funcs.get("f0", ast.Pass())))):
        why.append("M=1 block carries a chain")
    try:
        res = level._pytest(work, ["tests_visible"])
        passing = [t for t, o in res["outcomes"].items() if o == "pass"]
        if res["total"] != m or passing:
            why.append(f"visible tests before work: {res['total']} collected, {len(passing)} passing (want {m} collected, 0 passing)")
    except level.CheckerError as exc:
        why.append(f"visible tests could not run: {exc}")
    finally:
        for junk in ("__pycache__", ".pytest_cache"):
            shutil.rmtree(work / junk, ignore_errors=True)
            shutil.rmtree(work / "pkg" / junk, ignore_errors=True)
            shutil.rmtree(work / "tests_visible" / junk, ignore_errors=True)
    return why


def fixture_digest(block_dir: pathlib.Path) -> str:
    """One digest over a block's pristine fixture (manifest and every workdir file), taken
    when the block was validated and compared before the block is first used — a fixture
    edited after its declaration is refused (round 4, F16)."""
    h = hashlib.sha256()
    block_dir = pathlib.Path(block_dir)
    files = [block_dir / "manifest.json"] + sorted(p for p in (block_dir / "workdir").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for p in files:
        h.update(str(p.relative_to(block_dir)).encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def draw_valid_blocks(out: pathlib.Path, host: str, name: str, m: int, R: int) -> tuple[list[str], list[dict]]:
    """R valid block fixtures for size m, generated now under out/blocks with their
    validity asserted; a voided draw keeps its index (the seed sequence is the record) and
    the next index is drawn, at most R + BLOCK_DRAW_SLACK draws. Fewer than R valid blocks
    is a declaration failure: the cell would be NOT RUN before it cost anything."""
    blocks, voided = [], []
    for r in range(R + BLOCK_DRAW_SLACK):
        if len(blocks) == R:
            break
        block = f"M{m}-b{r + 1}"
        block_dir = out / "blocks" / block
        if not (block_dir / "manifest.json").is_file():
            generate_block(block_dir, host, block, m, name)
        check_block_fixture(block_dir, host, block, m, name)
        why = block_validity(block_dir, m)
        if why:
            voided.append({"block": block, "why": why})
            continue
        blocks.append(block)
    state = {"m": m, "R": R, "valid": blocks, "voided": voided, "draws": min(R + BLOCK_DRAW_SLACK, len(blocks) + len(voided)),
             "not_run": len(blocks) < R, "digests": {b: fixture_digest(out / "blocks" / b) for b in blocks}}
    (out / "blocks").mkdir(parents=True, exist_ok=True)
    (out / "blocks" / f"M{m}-draws.json").write_text(json.dumps(state, indent=1))   # the evidence outlives the stop (round 1, F20)
    if len(blocks) < R:
        raise RunError(f"M={m}: {len(blocks)} valid block(s) in {R + BLOCK_DRAW_SLACK} draws, {R} needed — the cell is NOT RUN; "
                       f"voided: {[v['block'] for v in voided]} (recorded in {out / 'blocks' / f'M{m}-draws.json'})")
    return blocks, voided


def check_block_fixture(block_dir: pathlib.Path, host: str, block: str, m: int, name: str = "stage1") -> None:
    """A block fixture found under a stage's `--out` must be the one this stage would
    generate: same host-carrying seed, same m, same generator. A stale one (an earlier
    stage's, a host-less seed) is refused by name — never reused as if fresh (round 7)."""
    man = json.loads((block_dir / "manifest.json").read_text())
    want = f"{name}:{host}:{block}"
    if man.get("seed") != want:
        raise RunError(f"block fixture {block_dir} was generated from seed {man.get('seed')!r}, not {want!r} — "
                       "another stage's blocks; use a new --out")
    if man.get("m") != m:
        raise RunError(f"block fixture {block_dir} has m={man.get('m')}, this stage declares {m} — use a new --out")
    if man.get("generator_sha256") != level.generator_sha256():
        raise RunError(f"block fixture {block_dir} was written by another generator — use a new --out")


def stage_arms(host: str, arms: list[str]) -> list[str]:
    """The arms a stage runs on `host`: an arm declared for other hosts only (fork-same is
    Codex-only, `D-20260904-fd86f1`) is left out of the manifest rather than failing at
    dispatch once per block — the Claude re-run of 2026-09-04 logged nine such failures."""
    return [a for a in arms if "hosts" not in ARMS[a] or host in ARMS[a]["hosts"]]


def stage1(host: str, sizes: list[int], R: int, arms: list[str], out: pathlib.Path,
           max_consecutive_failures: int = 2, resume: bool = True) -> dict:
    return stage("stage1", host, sizes, R, arms, out, max_consecutive_failures, resume)


def same_seats(a: dict, b: dict) -> list[str]:
    """The pin fields on which two declarations differ, `head` aside: an extension or a
    confirmation at a later HEAD measures the seats it continues only if every hash the
    pin freezes is the same (design, *The experiment pin*)."""
    return sorted(k for k in set(a) | set(b) if k != "head" and a.get(k) != b.get(k))


def plan_runs(out: pathlib.Path, host: str, name: str, arm_plan: dict) -> tuple[list[dict], dict, list[dict]]:
    """Runs from a per-arm size plan `{arm: {m: R}}`: block r of size m carries arm a iff
    r < R_a(m); the blocks are drawn valid at declaration (`draw_valid_blocks`), one
    fixture per block shared by the arms it carries, counterbalanced over those arms. A
    size's block count is the largest R any arm declares there."""
    sizes = sorted({int(m) for plan in arm_plan.values() for m in plan})
    for m in sizes:
        if m not in TIMEOUT_BY_M:
            raise RunError(f"M={m} has no timeout entry — a trigger size is declared, never defaulted")
    arms = list(arm_plan)
    runs, blocks_by_size, voided, not_run = [], {}, [], {}
    for m in sizes:
        R_m = max(int(arm_plan[a].get(m, arm_plan[a].get(str(m), 0))) for a in arms)
        try:
            blocks, void = draw_valid_blocks(out, host, name, m, R_m)
        except RunError as exc:
            # the size could not draw R valid blocks: NOT RUN, carried in the manifest the
            # caller writes so the reader can say so (round 4, F15); no run of that size
            not_run[str(m)] = str(exc)
            continue
        blocks_by_size[str(m)] = blocks
        voided += void
        for r, block in enumerate(blocks):
            here = [a for a in arms if r < int(arm_plan[a].get(m, arm_plan[a].get(str(m), 0)))]
            for k, arm in enumerate(counterbalanced(here, r)):
                runs.append({"block": block, "m": m, "rep": r + 1, "arm": arm, "order": k, "dir": f"{block}-{arm}"})
    return runs, blocks_by_size, voided, not_run


def stage(name: str, host: str, sizes: list[int], R, arms: list[str], out: pathlib.Path,
          max_consecutive_failures: int = 2, resume: bool = True,
          extends: pathlib.Path | None = None, extend_by: dict | None = None,
          candidates: pathlib.Path | None = None,
          arm_plan: dict | None = None, meta_extra: dict | None = None) -> dict:
    """A stage: every arm × every size × R matched blocks (R one number, or one per
    size — Stage 2 takes each size's R from the Stage-1 rule), one fixture per
    block shared by its arms, runs counterbalanced, the parent seat primed twice in each
    run's own directory. Declared before dispatch as `manifest.json`; each run's record
    is its completion mark, so a stopped stage resumes at the first run without one.
    Two consecutive failed dispatches stop the stage (a rate limit or a dead host is not
    something to retry-storm); the reason is written to `state.json`."""
    out.mkdir(parents=True, exist_ok=True)
    arms = stage_arms(host, arms)
    pin = pinmod.build_pin()
    body = pinmod.child_body(REPO, host)
    agents = child_agents(pin, host, body)
    home = codex_home(out / "home", agents, reuse=True)["home"] if host == "codex" else None
    manifest_path = out / "manifest.json"
    if manifest_path.is_file() and resume:
        manifest = json.loads(manifest_path.read_text())
        # one experiment, the heads it declared (`registry.extend_pin`): an owner's
        # extension continues a trigger stage at a later head on the same seats, and the
        # seats are held equal just below; a tier stage has no experiment root and its
        # head is held equal outright
        continued = (registry.same_head(manifest["pin"]["head"], pin["head"], out.parent)
                     if manifest.get("stage") in budget.STAGE_GROUPS
                     else registry.short_head(manifest["pin"]["head"]) == registry.short_head(pin["head"]))
        if not continued:
            raise RunError(f"stage manifest was declared at HEAD {manifest['pin']['head'][:12]}, "
                           f"tree is at {pin['head'][:12]} — a stage does not span two pins unless the experiment declared both")
        if manifest.get("not_run"):
            # the declaration itself says a size could not draw R valid blocks: the stage
            # stopped there, and a resume would dispatch the other sizes past a registered
            # stop (round 5, F4)
            raise RunError(f"{out} was declared NOT RUN at M={sorted(manifest['not_run'])} — a stage declared NOT RUN does not resume; "
                           "the owner decides, and a new declaration needs a new root")
        moved = same_seats(manifest["pin"], pin)
        if moved:
            # the head alone is not the pin: an uncommitted change to a binding, an agent
            # body, or a brief template moves a frozen hash under the same HEAD (round 3, F5)
            raise RunError(f"the pin moved under HEAD {pin['head'][:12]} in {moved} — a resumed stage runs on the seats it declared")
        # the whole declaration, not the head alone: a resumed stage runs what was declared,
        # so a different plan, host, name, or candidates file under the same --out is refused
        # by the field that differs (round 1, F12)
        want = {"stage": name, "host": host, "arms": arms,
                "arm_plan": ({a: {str(m): int(r_) for m, r_ in pl.items()} for a, pl in arm_plan.items()} if arm_plan is not None else None),
                "confirms_sha256": ((meta_extra or {}).get("confirms") or {}).get("sha256"),
                "root_id": (meta_extra or {}).get("root_id"), "frozen_sha256": (meta_extra or {}).get("frozen_sha256")}
        have = {"stage": manifest.get("stage"), "host": manifest.get("host"), "arms": manifest.get("arms"),
                "arm_plan": manifest.get("arm_plan"), "confirms_sha256": (manifest.get("confirms") or {}).get("sha256"),
                "root_id": manifest.get("root_id"), "frozen_sha256": manifest.get("frozen_sha256")}
        diff = [k for k in want if want[k] != have[k]]
        if diff:
            raise RunError(f"{out} holds a declaration that differs in {diff} from this command — resume runs what was "
                           f"declared; use a new --out or --fresh")
    else:
        old = stale_out(out)
        if old:
            raise RunError(f"{out} already holds {len(old)} record(s)/block fixture(s) from another declaration — "
                           "resume without --fresh, or use a new --out")
        R_by_size = {m: (R[m] if isinstance(R, dict) else R) for m in sizes}
        meta = {}
        start = {m: 0 for m in sizes}
        count = dict(R_by_size)
        if extends is not None:
            # a completion draw: fresh blocks numbered after the earlier declaration's, in
            # its stage namespace (so the seeds continue it and never collide), for the same
            # seats — refused when any pinned hash differs, or the declaration differs
            src = json.loads((pathlib.Path(extends) / "manifest.json").read_text())
            diff = same_seats(src["pin"], pin)
            if diff:
                raise RunError(f"cannot extend {extends}: the pin differs in {diff} — different seats, not a completion")
            if src["host"] != host or src["arms"] != arms:
                raise RunError(f"cannot extend {extends}: host/arms differ ({src['host']} {src['arms']} vs {host} {arms})")
            for m in sizes:
                if str(m) not in src["R"] or int(src["R"][str(m)]) != R_by_size[m]:
                    raise RunError(f"cannot extend {extends}: M={m} declared R {src['R'].get(str(m))} there, {R_by_size[m]} here")
                start[m] = int(src["R"][str(m)]); count[m] = int((extend_by or {}).get(m, 0))
                if count[m] < 1:
                    raise RunError(f"--extend needs at least one block at M={m}")
            name = src["stage"]
            meta = {"extends": {"out": str(extends), "head": src["pin"]["head"], "R": src["R"], "blocks_added": {str(m): count[m] for m in sizes}}}
        if candidates is not None:
            man = json.loads(pathlib.Path(candidates).read_text())
            cells = {int(c["m"]) for c in man["candidates"]}
            for m in sizes:
                if m not in cells:
                    raise RunError(f"M={m} is not a candidate cell in {candidates} (cells {sorted(cells)})")
                if int(man["R"][str(m)]) != R_by_size[m]:
                    raise RunError(f"M={m}: the candidate manifest declares R={man['R'][str(m)]}, this stage {R_by_size[m]} — confirmation runs the cell's own R")
            if man["host"] != host:
                raise RunError(f"the candidate manifest is for host {man['host']}, this stage for {host}")
            meta = {"confirms": {"candidates": str(candidates), "sha256": hashlib.sha256(pathlib.Path(candidates).read_bytes()).hexdigest(), "k": man["k"]}}
        runs = []
        if arm_plan is not None:
            if extends is not None or candidates is not None:
                raise RunError("a per-arm plan declares its own blocks; it does not extend or confirm through --extends/--candidates")
            runs, blocks_by_size, voided, not_run = plan_runs(out, host, name, arm_plan)
            meta = {"arm_plan": {a: {str(m): int(r_) for m, r_ in plan.items()} for a, plan in arm_plan.items()},
                    "blocks": blocks_by_size, "voided_blocks": voided, "not_run": not_run}
        else:
            for m in sizes:
                for r in range(start[m], start[m] + count[m]):
                    block = f"M{m}-b{r + 1}"
                    for k, arm in enumerate(counterbalanced(arms, r)):
                        runs.append({"block": block, "m": m, "rep": r + 1, "arm": arm, "order": k,
                                     "dir": f"{block}-{arm}"})
        manifest = {"stage": name, "host": host, "sizes": sizes, "R": {str(m): r for m, r in R_by_size.items()},
                    "arms": arms, "pin": pin, "declared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": runs,
                    **meta, **(meta_extra or {})}
        manifest_path.write_text(json.dumps(manifest, indent=1))
        if meta.get("not_run"):
            raise RunError(f"{name}: NOT RUN at M={sorted(meta['not_run'])} — declared as such in {manifest_path}; nothing of those sizes is dispatched: "
                           + "; ".join(meta["not_run"].values())[:400])
    state_path = out / "state.json"
    log = out / f"{name}.log"
    failures = 0
    done = skipped = 0
    vault = Vault()
    lost = sealed_without_pad(out, vault)   # a stage that died before this one held the pads
    try:
        return _stage_loop(host, manifest, out, home, vault, state_path, log, max_consecutive_failures, lost)
    finally:
        # the stage's end — normal, breaker, or exception — is when no seat of this stage
        # runs, so the solved workdirs and artifacts come back for the aggregator
        vault.unseal_all()


def _stage_loop(host, manifest, out, home, vault, state_path, log, max_consecutive_failures, lost):
    done = skipped = 0
    skipped_groups = {}
    name = manifest.get("stage", "stage1")
    # the breaker's streak survives a resume: rebuilt from the ledger, never reset by a
    # restart (round 3, F8)
    failures = budget.trailing_failures(out.parent, f"{name}/") if name in budget.STAGE_GROUPS else 0
    if failures >= max_consecutive_failures:
        state = {"stopped": True, "why": f"{failures} consecutive failed dispatches on the ledger — a person closes the streak with its reason (`budget.py ack <root> {name}/ <why>`) once the cause is gone, then resumes",
                 "at": "resume", "sealed_without_pad": lost, "failures": failures}
        state_path.write_text(json.dumps(state, indent=1))
        print(f"STOPPED: {state['why']}")
        return {"done": 0, "skipped": 0, "stopped": state}
    for spec in manifest["runs"]:
        rundir = out / "runs" / spec["dir"]
        if (rundir / "record.json").is_file():
            parked = park_unpriced(out, rundir)
            if parked is None:
                skipped += 1
                continue
            with open(log, "a") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {spec['dir']}: UNPRICED record parked at {parked} — re-dispatched\n")
        block_dir = out / "blocks" / spec["block"]
        if not (block_dir / "manifest.json").is_file():
            # the seed carries the host: the two hosts' stages run concurrently, and a
            # block fixture solved on one host must be no answer key for the other
            # (round 6; the 2026-09-04 re-run shared `stage1:<block>` across hosts)
            generate_block(block_dir, host, spec["block"], spec["m"], name)
        check_block_fixture(block_dir, host, spec["block"], spec["m"], name)
        attempt = None
        if name in budget.STAGE_GROUPS:
            # the design's ceilings, asked before EVERY dispatch from the records on disk
            # (round 1 F1; round 2 F1, F2, F5): a report-only or control group at its
            # ceiling skips its own remaining runs; any other group's, or the total, stops
            # the stage; an open or uncosted attempt stops everything
            group = budget.group_of_run(name, spec["arm"])
            if group in skipped_groups:
                skipped += 1
                continue
            if spec["m"] not in TIMEOUT_BY_M:
                raise RunError(f"M={spec['m']} has no timeout entry — a declared size is never defaulted")
            # a validated fixture is used only as validated (round 4, F16)
            draws_p = out / "blocks" / f"M{spec['m']}-draws.json"
            want_digest = (json.loads(draws_p.read_text()).get("digests") or {}).get(spec["block"]) if draws_p.is_file() else None
            if want_digest is None:
                raise RunError(f"{spec['block']} has no validation digest in {draws_p} — a trigger block is dispatched only as validated")
            if fixture_digest(block_dir) != want_digest:
                raise RunError(f"{spec['block']}'s fixture changed since it was validated — refused")
            # check, cap, and reservation under one lock (round 4, F2)
            attempt, cap, why = budget.reserve(out.parent, group, "run", f"{name}/{spec['dir']}",
                                               prefix=f"{name}/", max_failures=max_consecutive_failures)
            if attempt is None and group in NON_PRIMARY_GROUPS and why.startswith(f"ceiling: group {group}"):
                skipped_groups[group] = why
                with open(log, "a") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} {spec['dir']}: SKIPPED {why} — the group's remaining runs are skipped, the stage goes on\n")
                print(f"SKIPPED {group}: {why}")
                skipped += 1
                continue
            if attempt is None:
                state = {"stopped": True, "why": why, "at": spec["dir"], "sealed_without_pad": lost, "skipped_groups": skipped_groups}
                state_path.write_text(json.dumps(state, indent=1))
                with open(log, "a") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} {spec['dir']}: STOPPED {why}\n")
                print(f"STOPPED: {why} — the owner decides any extension")
                return {"done": done, "skipped": skipped, "stopped": state}
        else:
            attempt, cap = None, None
        if spec["m"] not in TIMEOUT_BY_M:
            if attempt:
                budget.close_attempt(out.parent, attempt, 0.0, "refused-before-dispatch")
            raise RunError(f"M={spec['m']} has no timeout entry — a declared size is never defaulted")
        started = time.time()
        try:
            rec = run(host, spec["arm"], spec["m"], f"{name}:{host}:{spec['block']}", "helm", rundir,
                      home=home, block=spec["block"], do_prime=True, per_run_home=True,
                      timeout=TIMEOUT_BY_M[spec["m"]], fixture_src=block_dir, budget_usd=cap)
            if attempt:
                # the record names its attempt, so the ledger credits it against that one
                # and no other (round 3, F6)
                rec["attempt"] = attempt
                rp = rundir / "record.json"
                if rp.is_file():
                    stored = json.loads(rp.read_text()); stored["attempt"] = attempt
                    rp.write_text(json.dumps(stored, indent=1))
            seal_run(vault, rundir)   # the solved workdir and the transcript leave the disk until the stage ends
            # the run's own home held its session; the transcript is in artifacts/ now, and
            # nothing of this run stays readable for the next (D-20260905-aec4cd)
            shutil.rmtree(rundir / "home", ignore_errors=True)
            if attempt:
                # the one terminal row, after everything that can raise has run: a seal
                # that fails closes the attempt as failed below, never twice (fix review 2, F3)
                budget.close_run(out.parent, attempt, rec, "ok")
            failures = 0
            done += 1
            r = rec["result"]
            line = (f"{time.strftime('%H:%M:%S')} {spec['dir']}: reached={r['reached']} at={r['reached_at']} "
                    f"cost={r['cost_to_parity']} level={r['score'].get('level_defects')} "
                    f"problems={len(r['problems'])} flags={[k for k, v in rec['flags'].items() if v]} "
                    f"({round(time.time() - started)}s)")
        except (RunError, usage.UsageError, pinmod.PinError, OSError) as exc:
            if attempt:
                # the failed attempt's cost is unknown: charged at the reserve, on the ledger
                budget.close_attempt(out.parent, attempt, None, f"failed: {type(exc).__name__}")
            failures += 1
            line = f"{time.strftime('%H:%M:%S')} {spec['dir']}: FAILED {type(exc).__name__}: {str(exc)[:300]}"
            (rundir / "failed.txt").write_text(line + "\n") if rundir.exists() else None
            shutil.rmtree(rundir / "home", ignore_errors=True)
            # what the seat wrote before the failure is sealed like a finished run's, so no
            # later sibling of the block can read it (Stage 2, M160-b10: the sweep seat read
            # the failed same-arm run's tree); the stage's end unseals it with the rest
            if rundir.exists():
                seal_run(vault, rundir)
        with open(log, "a") as fh:
            fh.write(line + "\n")
        print(line, flush=True)
        if failures >= max_consecutive_failures:
            state = {"stopped": True, "why": f"{failures} consecutive failed dispatches", "at": line,
                     "sealed_without_pad": lost, "failures": failures}
            state_path.write_text(json.dumps(state, indent=1))
            print(f"STOPPED: {state['why']} — resume with the same command after the cause is fixed")
            return {"done": done, "skipped": skipped, "stopped": state}
    state_path.write_text(json.dumps({"stopped": False, "done": done, "skipped": skipped,
                                      "sealed_without_pad": lost, "skipped_groups": skipped_groups, "failures": failures}, indent=1))
    return {"done": done, "skipped": skipped, "stopped": None, "skipped_groups": skipped_groups}


# ----------------------------------------------------------------------------- cli
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe"); p.add_argument("--host", required=True, choices=["claude", "codex"])
    p.add_argument("--tiers", default="helm,workhorse,sweep")
    r = sub.add_parser("run"); r.add_argument("--host", required=True, choices=["claude", "codex"])
    r.add_argument("--arm", required=True, choices=sorted(ARMS)); r.add_argument("--m", type=int, default=3)
    r.add_argument("--seed", default="stage0")
    r.add_argument("--prime", action="store_true", help="two priming requests in the run's directory first")
    r.add_argument("--parent-tier", default="helm", choices=["helm", "workhorse", "sweep"],
                   help="debugging only: a run whose parent is not the HELM row is not evidence")
    q = sub.add_parser("plants"); q.add_argument("--record", help="run dir (default: the last run)")
    s1 = sub.add_parser("stage1"); s1.add_argument("--host", default="codex", choices=["claude", "codex"])
    s1.add_argument("--sizes", default="10,40,160"); s1.add_argument("--R", type=int, default=3)
    s1.add_argument("--arms", default=",".join(STAGE1_ARMS))
    s1.add_argument("--out", default=str(OUT / "stage1"))
    s1.add_argument("--fresh", action="store_true", help="ignore an existing manifest and records")
    s2 = sub.add_parser("stage2", help="every cell on fresh blocks, R per size from the Stage-1 rule")
    s2.add_argument("--host", default="codex", choices=["claude", "codex"])
    s2.add_argument("--sizes", default="10,40,160"); s2.add_argument("--R", required=True, help="one R per size, e.g. 12,15,13")
    s2.add_argument("--arms", default=",".join(STAGE1_ARMS))
    s2.add_argument("--out", default=str(OUT / "stage2"))
    s2.add_argument("--fresh", action="store_true", help="ignore an existing manifest and records")
    s2.add_argument("--extends", help="a completion draw: the earlier stage2 --out whose cells this extends (same seats, same R)")
    s2.add_argument("--extend", help="blocks to add per size, e.g. 2,4 (with --extends)")
    # The spawn-trigger commands carry NO volume options: sizes, R, and arms are the
    # design's registered values (TRIGGER_PLAN), and the output directories are fixed
    # under --root so the budget ledger finds every record (round 1, F1 and F2).
    tb = sub.add_parser("trigger-b", help="spawn-trigger Stage B: inline + workhorse at M=1,5,10 (R 10), sweep at 1,5 (R 10), same at 1 (R 5)")
    tb.add_argument("--root", default=str(OUT), help="the tier run root (stage dir = <root>/trigger-b)")
    tb.add_argument("--fresh", action="store_true")
    tb.add_argument("--dry", action="store_true", help="declare the manifest and draw the blocks; dispatch nothing")
    tc = sub.add_parser("trigger-cell", help="spawn-trigger conditional cell: inline + workhorse at the size the tree named, R 10")
    tc.add_argument("--m", type=int, required=True, choices=[3, 7])
    tc.add_argument("--root", default=str(OUT)); tc.add_argument("--fresh", action="store_true")
    tc.add_argument("--dry", action="store_true")
    tk = sub.add_parser("trigger-c", help="spawn-trigger confirmation: the claim cells of <root>/trigger-candidates.json on fresh blocks, R 5, after pass C")
    tk.add_argument("--root", default=str(OUT)); tk.add_argument("--fresh", action="store_true")
    tk.add_argument("--dry", action="store_true")
    cf = sub.add_parser("confirm", help="confirmation: the candidate cells on fresh blocks at their own R")
    cf.add_argument("--host", default="codex", choices=["claude", "codex"])
    cf.add_argument("--sizes", required=True); cf.add_argument("--R", required=True, help="one R per size — must equal the manifest's")
    cf.add_argument("--arms", default=",".join(STAGE1_ARMS))
    cf.add_argument("--candidates", required=True, help="the candidate manifest discovery wrote (bounds.py --write-candidates)")
    cf.add_argument("--out", default=str(OUT / "confirm"))
    cf.add_argument("--fresh", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "probe":
        pin = pinmod.build_pin()
        seats, seen = [], set()
        for t in a.tiers.split(","):
            row = pinmod.experiment_row(pin, a.host, t)
            if row["model"] in seen:
                continue
            seen.add(row["model"]); seats.append(row)
        res = probe(a.host, OUT, seats)
        (OUT / f"stage0-probes-{a.host}.json").write_text(json.dumps(res, indent=1))
        for k, v in res["seats"].items():
            print(f"{k}: standing prefix {v['standing_prefix']} reads={v['reads']} "
                  f"first={v['runs'][-1]['first_request']} seat_receipt={v['seat_receipt'] or 'ok'}"
                  + (f" UNSTABLE: {v['unstable']}" if v.get('unstable') else ""))
        if "known_opposite" in res:
            print("known-opposite:", json.dumps(res["known_opposite"]))
        if "differential" in res:
            print("differential:", json.dumps(res["differential"]))
        return 0
    if a.cmd == "run":
        nonce_dir = OUT / "runs" / f"{time.strftime('%Y%m%dT%H%M%S')}-{a.host}-{a.arm}-{secrets.token_hex(3)}"
        rec = run(a.host, a.arm, a.m, a.seed, a.parent_tier, nonce_dir, do_prime=a.prime)
        print("\n".join(verdict_lines(rec)))
        print(f"record: {OUT / 'last-run.txt'} -> {(OUT / 'last-run.txt').read_text().strip()}")
        return 0 if not rec["result"]["problems"] else 1
    if a.cmd == "plants":
        rd = pathlib.Path(a.record) if a.record else pathlib.Path((OUT / "last-run.txt").read_text().strip())
        return plants(rd)
    if a.cmd in ("trigger-b", "trigger-cell", "trigger-c"):
        root = pathlib.Path(a.root)
        host = TRIGGER_HOST
        pin = pinmod.build_pin()
        if a.cmd == "trigger-b":
            # the first Stage B declaration creates the experiment's identity; every later
            # manifest under this root carries it (round 2, F4). An EXISTING root admits a
            # Stage B call only at a head it declared (fix review 4, F11): a retry after the
            # checkout moved is a fresh declaration at an undeclared head otherwise
            if (root / registry.ROOT_FILE).is_file():
                try:
                    ident = registry.root_identity(root)
                except registry.RegistryError as exc:
                    raise RunError(str(exc))
                if not registry.head_declared(pin["head"], root):
                    raise RunError(f"this tree is at {registry.short_head(pin['head'])}, a head the experiment did not declare "
                                   f"({sorted(registry.declared_heads(root))}) — registry.py extend-pin, with the owner's decision")
            else:
                ident = registry.root_identity(root, pin_head=pin["head"], create=True)
            plan = {arm: dict(sizes) for arm, sizes in TRIGGER_PLAN.items()}
            name = "trigger-b"
            try:
                frozen = registry.frozen_digest(root / registry.CARDS_DIR)   # texts and cards frozen BEFORE any run (round 4, F3)
            except registry.RegistryError as exc:
                raise RunError(f"Stage B does not start: {exc}")
            meta_extra = {"root_id": ident["root_id"], "frozen_sha256": frozen}
        elif a.cmd == "trigger-cell":
            try:
                ident = registry.root_identity(root)
            except registry.RegistryError as exc:
                raise RunError(str(exc))
            if not registry.head_declared(pin["head"], root):
                raise RunError(f"this tree is at {registry.short_head(pin['head'])}, a head the experiment did not declare "
                               f"({sorted(registry.declared_heads(root))}) — registry.py extend-pin, with the owner's decision")
            plan, meta_extra = trigger_cell_plan(root, a.m, ident["root_id"], pin["head"])
            name = f"trigger-cell{a.m}"
        else:
            try:
                ident = registry.root_identity(root)
            except registry.RegistryError as exc:
                raise RunError(str(exc))
            if not registry.head_declared(pin["head"], root):
                raise RunError(f"this tree is at {registry.short_head(pin['head'])}, a head the experiment did not declare "
                               f"({sorted(registry.declared_heads(root))}) — registry.py extend-pin, with the owner's decision")
            cand_path = root / registry.CANDIDATES_FILE
            if not cand_path.is_file():
                raise RunError(f"{cand_path} does not exist — confirmation runs on the selection the reader sealed there, nowhere else")
            cand = json.loads(cand_path.read_text())
            plan, meta_extra = trigger_c_plan(cand_path, cand, ident["root_id"], root)
            require_pass_c(root, meta_extra["confirms"]["sha256"])
            name = "trigger-c"
        out = root / name
        sizes = sorted({m for p_ in plan.values() for m in p_})
        preflight_groups(root, name, plan)
        if a.dry:
            # declare only: the manifest and the valid blocks, no dispatch — the same
            # declaration path, stopped before the loop
            out.mkdir(parents=True, exist_ok=True)
            if (out / "manifest.json").is_file() and not a.fresh:
                raise RunError(f"{out} already holds a manifest — a dry declaration wants a fresh directory")
            if stale_out(out):
                # --fresh never redeclares over records or fixtures: the old ones would be
                # skipped as done under the new declaration (round 2, F9)
                raise RunError(f"{out} holds {len(stale_out(out))} record(s)/fixture(s) from another declaration — a dry declaration wants an empty directory")
            runs, blocks, voided, not_run = plan_runs(out, host, name, plan)
            manifest = {"stage": name, "host": host, "sizes": sizes, "R": {str(m): max(int(p_.get(m, 0)) for p_ in plan.values()) for m in sizes},
                        "arms": list(plan), "pin": pin, "declared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": runs,
                        "arm_plan": {k: {str(m): v for m, v in p_.items()} for k, p_ in plan.items()}, "blocks": blocks,
                        "voided_blocks": voided, "not_run": not_run, "dry": True, **(meta_extra or {})}
            (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
            if not_run:
                raise RunError(f"{name}: NOT RUN at M={sorted(not_run)} — declared as such in {out / 'manifest.json'}: "
                               + "; ".join(not_run.values())[:400])
            print(json.dumps({"runs": len(runs), "by_arm": {k: sum(1 for r in runs if r["arm"] == k) for k in plan},
                              "blocks": {m: len(b) for m, b in blocks.items()}, "voided": voided}, indent=1))
            return 0
        res = stage(name, host, sizes, {m: max(int(p_.get(m, 0)) for p_ in plan.values()) for m in sizes}, list(plan), out,
                    resume=not a.fresh, arm_plan=plan, meta_extra=meta_extra)
        print(json.dumps(res, indent=1))
        return 0 if not res["stopped"] else 3
    if a.cmd in ("stage1", "stage2", "confirm"):
        sizes = [int(x) for x in a.sizes.split(",")]
        if a.cmd in ("stage2", "confirm"):
            rs = [int(x) for x in str(a.R).split(",")]
            if len(rs) != len(sizes):
                raise SystemExit(f"--R needs one value per size ({len(sizes)}), got {len(rs)}")
            R = dict(zip(sizes, rs))
        else:
            R = int(a.R)
        extends = extend_by = None
        if a.cmd == "stage2" and (getattr(a, "extends", None) or getattr(a, "extend", None)):
            if not (a.extends and a.extend):
                raise SystemExit("--extends and --extend go together")
            ex = [int(x) for x in a.extend.split(",")]
            if len(ex) != len(sizes):
                raise SystemExit(f"--extend needs one value per size ({len(sizes)}), got {len(ex)}")
            extends, extend_by = pathlib.Path(a.extends), dict(zip(sizes, ex))
        res = stage(a.cmd, a.host, sizes, R, a.arms.split(","),
                     pathlib.Path(a.out), resume=not a.fresh, extends=extends, extend_by=extend_by,
                     candidates=pathlib.Path(a.candidates) if a.cmd == "confirm" else None)
        print(json.dumps(res, indent=1))
        return 3 if res["stopped"] else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
