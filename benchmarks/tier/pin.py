#!/usr/bin/env python3
"""The experiment pin, and the seat receipt read against it.

One HEAD and one set of hashes are frozen at Stage 0 and every run resolves its
bindings from them (design, "The experiment pin"). A run whose resolved model,
effort, agent body, or brief protocol differs from its pinned row is a control
failure, never pooled. This is control 4, blocking.

The seat is read from the participant's OWN artifact, never from what the runner
requested — usage.Participant already carries `.models` and `.efforts` extracted from
the Claude transcript's per-record `model`/`effort` and the Codex rollout's
`turn_context`. The old receipt.py marked effort "unverified" because it read the
`-p` JSON wrapper, which omits effort; the transcript carries it, so effort is part
of the receipt here and an effort-only swap is refused.

Body and brief-protocol hashes are pinned now and verified against the packet the
child actually received in S4, where a live child carries them; this module fixes
the pin and the model/effort receipt, which are decidable from existing artifacts.

The tested efforts are fixed by D-20260904-29fbdd (workhorse xhigh, sweep max), and
a seat whose model has no effort parameter pins effort None: measured 2026-09-04,
`claude -p --effort max` on haiku records no `effort` field while opus-5 records
"xhigh", and the vendor reference lists no effort levels for Haiku 4.5. For such a
row an artifact that DOES report an effort is the contradiction.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

sys.path.insert(0, str(HERE))
import level  # noqa: E402
import usage  # noqa: E402


class PinError(RuntimeError):
    """The pin cannot be resolved, so nothing can be judged against it."""


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def child_body(repo: pathlib.Path, host: str) -> str:
    """The body text a child is injected with, from the pinned definition file: the
    markdown below the frontmatter on Claude, `developer_instructions` on Codex."""
    text = (repo / CHILD_BODY[host]).read_text(encoding="utf-8")
    if host == "claude":
        m = re.match(r"---\n.*?\n---\n", text, re.S)
        if not m:
            raise PinError(f"{CHILD_BODY[host]}: no frontmatter")
        return text[m.end():].strip() + "\n"
    m = re.search(r'developer_instructions\s*=\s*"""\n(.*?)"""', text, re.S)
    if not m:
        raise PinError(f"{CHILD_BODY[host]}: no developer_instructions")
    return m.group(1)


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


AGENT_DEFS = {
    "claude": {"workhorse": "claude/agents/workhorse.md", "sweep": "claude/agents/sweep.md",
               "frontier": "claude/agents/frontier.md"},
    "codex": {"workhorse": "codex/agents/workhorse.toml", "sweep": "codex/agents/sweep.toml",
              "frontier": "codex/agents/frontier.toml"},
}
LAUNCH_TOML = "launch/agent-launch.toml"

# The child body every isolated delegated arm runs (design, "Agent body"): the
# workhorse definition's text on Claude, its Codex projection's developer_instructions
# on Codex. Model and effort vary by row; the body does not.
CHILD_BODY = {"claude": "claude/agents/workhorse.md", "codex": "codex/agents/workhorse.toml"}

# Models with no effort parameter: the CLI accepts --effort and drops it, and the
# artifact records none. Prefix-matched like dispatch.model_matches.
NO_EFFORT_MODELS = ("claude-haiku-4-5",)

# The efforts the experiment tests, per tier (D-20260904-29fbdd). P is the helm row.
ARM_EFFORT = {"helm": "xhigh", "workhorse": "xhigh", "sweep": "max"}

# Experimental model substitutions are frozen into each pin. A row records
# `tested_over` only when that pin's tested and shipped models differ; existing
# pins keep their original seats and provenance when shipped defaults change.
TESTED_MODELS = {"claude/workhorse": "claude-sonnet-5"}


def _head(repo: pathlib.Path) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise PinError(f"cannot read HEAD: {out.stderr.strip()}")
    return out.stdout.strip()


# The shipped tier bindings, parsed from launch/agent-launch.toml. The design freezes
# these as literals at Stage 0 rather than resolving per run, so a binding that moves
# mid-experiment does not silently re-label a cell.
def _tier_bindings(repo: pathlib.Path) -> dict:
    text = (repo / LAUNCH_TOML).read_text(encoding="utf-8")
    out: dict = {}
    host = tier = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[hosts.") and ".tiers." in s:
            parts = s.strip("[]").split(".")
            host, tier = parts[1], parts[3]
            out.setdefault(host, {}).setdefault(tier, {})
        elif host and tier and s.startswith("model"):
            out[host][tier]["model"] = s.split("=", 1)[1].strip().strip('"')
        elif host and tier and s.startswith("effort"):
            out[host][tier]["effort"] = s.split("=", 1)[1].strip().strip('"')
        elif s.startswith("[") and not s.startswith("[hosts.") :
            host = tier = None
    return out


def build_pin(repo: pathlib.Path | None = None, briefs: dict | None = None) -> dict:
    """Freeze HEAD, the launch config, and every agent definition. `briefs` maps a
    protocol name to a file whose hash is pinned when the templates exist (S3/S4)."""
    repo = pathlib.Path(repo) if repo else REPO
    defs = {}
    for host, files in AGENT_DEFS.items():
        for name, rel in files.items():
            p = repo / rel
            if p.is_file():
                defs[f"{host}/{name}"] = _sha(p)
    brief_hashes = {}
    for name, rel in (briefs or {}).items():
        p = repo / rel
        if not p.is_file():
            raise PinError(f"brief template {rel} does not exist")
        brief_hashes[name] = _sha(p)
    return {
        "head": _head(repo),
        # the fixture generator as it RUNS — an uncommitted edit is not the commit at HEAD
        # (round 7), and the held-out tests it draws have no other receipt
        "generator_sha256": level.generator_sha256(),
        "launch_toml_sha256": _sha(repo / LAUNCH_TOML),
        "tier_bindings": _tier_bindings(repo),
        "agent_def_sha256": defs,
        "child_body_sha256": {h: _sha_text(child_body(repo, h)) for h in CHILD_BODY
                              if (repo / CHILD_BODY[h]).is_file()},
        "brief_sha256": brief_hashes,
        "tested_models": dict(TESTED_MODELS),
    }


def pinned_row(pin: dict, host: str, tier: str) -> dict:
    """The literal model/effort a cell is bound to — read from the frozen pin, not
    from the live config, so a mid-experiment rebind cannot move it."""
    row = (pin.get("tier_bindings", {}).get(host, {}) or {}).get(tier)
    if not row or "model" not in row:
        raise PinError(f"pin has no binding for {host}/{tier}")
    return row


def no_effort_model(model: str) -> bool:
    return any(model == m or model.startswith(m + "-") for m in NO_EFFORT_MODELS)


def experiment_row(pin: dict, host: str, tier: str) -> dict:
    """The literal seat an arm runs: the tier's pinned MODEL at the experiment's fixed
    effort. A model with no effort parameter pins `effort: None` and says why, so the
    receipt demands an absent effort rather than an unprovable one."""
    shipped = pinned_row(pin, host, tier)["model"]
    tested = (pin.get("tested_models") or {}).get(f"{host}/{tier}")
    model = tested or shipped
    if tier not in ARM_EFFORT:
        raise PinError(f"no experiment effort for tier {tier!r}")
    if no_effort_model(model):
        row = {"model": model, "effort": None, "no_effort": True}
    else:
        row = {"model": model, "effort": ARM_EFFORT[tier]}
    if tested and tested != shipped:
        row["tested_over"] = shipped
    return row


def check_seat(participant, expected: dict) -> list[str]:
    """Problems that make this participant's seat differ from its pinned row.

    Model AND effort both, from the artifact. The effort check is the one the old
    receipt could not make: on Claude the effort is a per-record field, on Codex a
    turn_context field, so an effort-only swap that leaves the model correct is caught
    here where a model-only receipt would have reported the contrast as run."""
    problems = []
    want_model = expected.get("model")
    want_effort = expected.get("effort")
    got_models = participant.models
    got_efforts = participant.efforts
    if want_model:
        if not got_models:
            problems.append(f"{participant.id}: no model in the artifact — seat unproven")
        elif not all(usage.dispatch.model_matches(want_model, m) for m in got_models):
            problems.append(f"{participant.id}: ran model {got_models}, pinned {want_model!r}")
    if want_effort:
        if not got_efforts:
            problems.append(f"{participant.id}: no effort in the artifact — effort unproven")
        elif got_efforts != [want_effort]:
            problems.append(f"{participant.id}: ran effort {got_efforts}, pinned {want_effort!r}")
    elif expected.get("no_effort") and got_efforts:
        problems.append(f"{participant.id}: reports effort {got_efforts} but the pinned seat "
                        f"{want_model!r} has no effort parameter")
    return problems


def check_body(reported_sha: str, pin: dict, key: str) -> list[str]:
    """The child body the participant actually ran, against the pinned definition.

    `reported_sha` is the sha256 of the agent body carried in the child's own artifact
    (its injected system prompt); S4 reads it from a live child. Here the check is the
    decidable half: a reported hash that is not the pinned one is refused."""
    want = pin.get("agent_def_sha256", {}).get(key)
    if not want:
        return [f"pin has no agent definition for {key}"]
    if reported_sha != want:
        return [f"ran body {reported_sha[:12]}, pinned {key} is {want[:12]}"]
    return []


def check_brief(reported_sha: str, pin: dict, protocol: str) -> list[str]:
    """The brief protocol the child received (standard | cheap-seat), against the pin.
    A cheap arm that got the standard brief, or a retention arm the cheap-seat one, is a
    row mismatch (design, "Briefing is part of the treatment")."""
    want = pin.get("brief_sha256", {}).get(protocol)
    if not want:
        return [f"pin has no brief template for {protocol!r}"]
    if reported_sha != want:
        return [f"received brief {reported_sha[:12]}, pinned {protocol!r} is {want[:12]}"]
    return []


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="freeze or read the experiment pin")
    ap.add_argument("--repo", help="repo root (default: this checkout)")
    ap.add_argument("--out", help="write the pin JSON here")
    a = ap.parse_args(argv)
    pin = build_pin(pathlib.Path(a.repo) if a.repo else None)
    text = json.dumps(pin, indent=1)
    if a.out:
        pathlib.Path(a.out).write_text(text)
        print(f"pin written to {a.out} (head {pin['head'][:12]})")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
