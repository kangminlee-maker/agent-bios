#!/usr/bin/env python3
"""Runtime-projection half of the parity gate (check 6 in check-parity.sh).

Every check here compares a live runtime projection against its declared source:
the Codex role-slot templates and the config fragment that publishes them, the
guide Environment Binding rows, the two Codex wrappers' bypass and sandbox
defaults, and the launcher's plan/args/contract/TUI behavior against
launch/agent-launch.toml.

Checks are registered by name. `--list` prints them; `--only NAME` runs a subset.
A subset is a debugging aid, not a gate: the launcher checks share one temporary
fixture whose environment is mutated in declaration order (agent_materialization
sets AGENT_LAUNCH_DEBUG and leaves it set), so only a full run reproduces the
state each check was written against.

Run by gates/check-parity.sh under the managed Textual venv, from the repo
root; every path here is repo-relative.
"""
import argparse
import contextlib
import copy
import dataclasses
import datetime
import difflib
import fcntl
import hashlib
import importlib.util
import inspect
import io
import json
import os
import pathlib
import pty
import ast
import re
import string
import secrets
import select
import signal
import struct
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import unicodedata
import termios
import time
import tomllib
import types
from launcher_fixture_env import launcher_environment

sys.dont_write_bytecode = True

fail = 0


# Package front-ends an install line may legitimately start with even where this gate
# runs without them on PATH. Anything else has to actually exist.
INSTALLER_FRONT_ENDS = {"npm", "npx", "pnpm", "yarn", "pip", "pip3", "pipx", "brew",
                        "cargo", "go", "uv"}


def mark_fail(message):
    global fail
    print(f"FAIL: {message}")
    fail = 1


# Checks in declaration order. `needs_fixture` splits the ones that run against
# the shared temporary launcher harness from the ones that only read the repo.
CHECKS = {}


def check(fn):
    CHECKS[fn.__name__] = (fn, False)
    return fn


def launcher_check(fn):
    CHECKS[fn.__name__] = (fn, True)
    return fn

agent_dir = pathlib.Path("codex/agents")
launch_profile_path = pathlib.Path("launch/agent-launch.toml")
launcher = pathlib.Path("launch/agent-launch.py")
shell_init = pathlib.Path("launch/agent-launch.zsh")

def legacy_preset_toml(name, setup, family=None, delegation=True, mode="builder"):
    """A synthetic LEGACY preset appended to a profile under test.

    Compatibility checks used to make their scenario by string-replacing a shipped
    preset's `review_setup`. The moment the shipped defaults migrated, those
    replacements silently no-op'd and the checks asserted nothing — so they own their
    subject now instead of borrowing one that is free to move."""
    lines = [
        f"\n\n[presets.{name}]",
        f'label = "Gate {name}"',
        f'mode = "{mode}"',
        'main_tier = "helm"',
        'frontier_effort = "max"',
        f'review_setup = "{setup}"',
        f"delegation = {'true' if delegation else 'false'}",
        'codex_execution_policy = "bypass"',
        'claude_permission_mode = "bypassPermissions"',
    ]
    if family is not None:
        lines.insert(6, f'review_family = "{family}"')
    return "\n".join(lines) + "\n"


def table_row(path, slot):
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] == slot:
            return cells
    return None


def has_exact_model(text, model):
    return re.search(rf"(?<![\w.-]){re.escape(model)}(?![\w.-])", text) is not None

def invoke(argv, *, input_text=None, env=None):
    # stdin=DEVNULL when there is no payload: subprocess inherits the parent's stdin
    # otherwise, and a child that reads it blocks forever on an open-but-idle one —
    # exactly what a backgrounded or piped gate run provides. `codex-helm.sh
    # --dry-run` does read it, which is why this gate intermittently hung for ten
    # minutes with the child at 0% CPU. install.sh solved the same problem for the
    # same wrapper with `exec </dev/null`; this is that fix for the gate.
    return subprocess.run(
        argv,
        input=input_text,
        stdin=None if input_text is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
    )


def expect_text(result, label, present=(), absent=(), status=0):
    if result.returncode != status:
        mark_fail(f"{label} returned {result.returncode}, want {status}: {result.stderr.strip()}")
        return False
    for token in present:
        if token not in result.stdout:
            mark_fail(f"{label} missing {token!r}")
    for token in absent:
        if token in result.stdout:
            mark_fail(f"{label} unexpectedly contains {token!r}")
    return True

try:
    launch_profile = tomllib.loads(launch_profile_path.read_text())
except Exception as exc:
    mark_fail(f"launch profile does not parse: {launch_profile_path} ({exc})")
    launch_profile = {}

helm = pathlib.Path("wrappers/codex-helm.sh")

expected_launch_tiers = {
    "frontier": ("gpt-6-astra", "max"),
    "helm": ("gpt-5.6-sol", "xhigh"),
    "workhorse": ("gpt-5.6-terra", "xhigh"),
    "sweep": ("gpt-5.6-luna", "max"),
}
expected_claude_tiers = {
    "frontier": ("claude-fable-5-1", "max"),
    "helm": ("claude-opus-5", "xhigh"),
    "workhorse": ("claude-sonnet-5", "xhigh"),
    "sweep": ("claude-haiku-4-5", None),
}


@check
def required_assets():
    for required in (launch_profile_path, launcher, shell_init):
        if not required.is_file():
            mark_fail(f"required launch asset missing: {required}")


LAYOUT_DOCS = ("CONTRIBUTING.md", "ko/CONTRIBUTING.md")
LAUNCH_DOC_PHRASES = {
    "docs/advanced-launch.md": (
        "Every arrow-key TUI selection screen", "persistent settings hub",
        "Start with these settings", "Exit without launching", "`b` is the back command",
    ),
    "ko/docs/advanced-launch.md": (
        "화살표 키 TUI의 모든 선택 화면", "지속형 설정 허브",
        "Start with these settings", "Exit without launching", "`b`가 뒤로가기 명령",
    ),
}
README_REFERENCES = {
    "README.md": ("CONTRIBUTING.md", "docs/corpus.md", "docs/session-model.md",
                  "docs/recovery.md", "docs/advanced-launch.md", "docs/understand.md"),
    "ko/README.md": ("CONTRIBUTING.md", "../docs/corpus.md", "../docs/session-model.md",
                     "../docs/recovery.md", "docs/advanced-launch.md", "../docs/understand.md"),
}


def _layout_errors(trees, documents):
    if not trees or not documents:
        return ["layout contract has no trees or documents"]
    errors = []
    for doc, text in documents.items():
        table = text.split("## Layout", 1)[-1].split("\n## ", 1)[0] if "## Layout" in text else ""
        if not table:
            errors.append(f"{doc} has no Layout section to check trees against")
            continue
        for tree in trees:
            if f"`{tree}/" not in table and f"`{tree}`" not in table:
                errors.append(f"{doc} Layout table does not mention the tracked tree {tree!r}")
    return errors


def _phrase_errors(documents, required):
    if not required or any(not phrases for phrases in required.values()):
        return ["documentation phrase contract has no subjects"]
    return [f"agent-launch documentation contract missing from {doc}: {phrase!r}"
            for doc, phrases in required.items() for phrase in phrases
            if phrase not in documents.get(doc, "")]


def _reference_errors(documents, required):
    if not required or any(not links for links in required.values()):
        return ["README reference contract has no subjects"]
    errors = []
    for doc, links in required.items():
        for link in links:
            if f"]({link})" not in documents.get(doc, ""):
                errors.append(f"{doc} does not link to {link}")
            target = os.path.normpath(str(pathlib.Path(doc).parent / link))
            if not documents.get(target, "").strip():
                errors.append(f"{doc} reference target is missing or empty: {target}")
    return errors


def _documentation_texts(paths):
    return {path: pathlib.Path(path).read_text() if pathlib.Path(path).is_file() else ""
            for path in paths}


@check
def readme_layout_covers_every_tree():
    """README-linked contributor maps cover the real tracked top-level trees."""
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split()
    trees = sorted({rel.split("/", 1)[0] for rel in tracked if "/" in rel})
    for error in _layout_errors(trees, _documentation_texts(LAYOUT_DOCS)):
        mark_fail(error)


@check
def doc_phrases():
    for error in _phrase_errors(_documentation_texts(LAUNCH_DOC_PHRASES), LAUNCH_DOC_PHRASES):
        mark_fail(error)


@check
def readme_reference_navigation():
    paths = set(README_REFERENCES)
    paths.update(os.path.normpath(str(pathlib.Path(doc).parent / link))
                 for doc, links in README_REFERENCES.items() for link in links)
    for error in _reference_errors(_documentation_texts(paths), README_REFERENCES):
        mark_fail(error)


@check
def documentation_contract_controls():
    """Independent fixture data keeps controls alive when live docs are reorganized."""
    layout = {"contribution.md": "## Layout\n| `source/` | code |\n| `docs/` | docs |\n"}
    phrases = {"launch.md": ("launch contract",)}
    required = {"ko/README.md": ("../docs/runtime.md",)}
    linked = {"ko/README.md": "[Runtime](../docs/runtime.md)", "docs/runtime.md": "Runtime instructions"}
    probes = (
        (not _layout_errors(["source", "docs"], layout), "layout positive control"),
        (any("'docs'" in e for e in _layout_errors(["source", "docs"],
             {"contribution.md": "## Layout\n| `source/` | code |"})), "missing tree"),
        (bool(_layout_errors([], layout)), "empty tree set"),
        (bool(_layout_errors(["source"], {})), "empty layout set"),
        (bool(_layout_errors(["source"], {"contribution.md": "no heading"})), "missing Layout heading"),
        (not _phrase_errors({"launch.md": "launch contract"}, phrases), "phrase positive control"),
        (any("launch contract" in e for e in _phrase_errors({"launch.md": "wrong"}, phrases)), "missing launch phrase"),
        (bool(_phrase_errors({}, {})), "empty phrase contract"),
        (not _reference_errors(linked, required), "relative link positive control"),
        (any("does not link" in e for e in _reference_errors(
            dict(linked, **{"ko/README.md": "no link"}), required)), "missing README link"),
        (any("missing or empty" in e for e in _reference_errors(
            {"ko/README.md": linked["ko/README.md"]}, required)), "missing destination"),
        (bool(_reference_errors(linked, {})), "empty reference contract"),
    )
    for passed, name in probes:
        if not passed:
            mark_fail(f"documentation contract self-test: {name}")


@check
def launch_profile_tiers():
    codex_launch_tiers = launch_profile.get("hosts", {}).get("codex", {}).get("tiers", {})
    if set(codex_launch_tiers) != set(expected_launch_tiers):
        mark_fail("launch profile Codex tiers must be exactly frontier/helm/workhorse/sweep")
    for tier, (model, effort) in expected_launch_tiers.items():
        binding = codex_launch_tiers.get(tier, {})
        if (binding.get("model"), binding.get("effort")) != (model, effort):
            mark_fail(f"launch profile Codex {tier} is {binding!r}, want {model}/{effort}")
    def frontier_mismatches(presets):
        result = []
        for name, preset in presets.items():
            effort = preset.get("frontier_effort", codex_launch_tiers.get("frontier", {}).get("effort"))
            if isinstance(effort, dict):
                effort = effort.get("codex")
            if effort != "max":
                result.append(name)
        return result

    for name in frontier_mismatches(launch_profile.get("presets", {})):
        mark_fail(f"shipped preset {name} overrides Codex FRONTIER; want max")
    # Independent subjects keep both scalar and host-qualified shadowing covered.
    for value in ("xhigh", {"codex": "xhigh", "claude": "max"}, {"claude": "max"}):
        if frontier_mismatches({"control": {"frontier_effort": value}}) != ["control"]:
            mark_fail("Codex FRONTIER preset shadowing control did not reject the planted override")
    if frontier_mismatches({"control": {"frontier_effort": {"codex": "max", "claude": "low"}}}):
        mark_fail("Codex FRONTIER preset control incorrectly constrains the Claude arm")
    claude_launch_tiers = launch_profile.get("hosts", {}).get("claude", {}).get("tiers", {})
    if set(claude_launch_tiers) != set(expected_claude_tiers):
        mark_fail("launch profile Claude tiers must be exactly frontier/helm/workhorse/sweep")
    for tier, (model, effort) in expected_claude_tiers.items():
        binding = claude_launch_tiers.get(tier, {})
        if (binding.get("model"), binding.get("effort")) != (model, effort):
            mark_fail(f"launch profile Claude {tier} is {binding!r}, want {model}/{effort}")

    balanced = launch_profile.get("presets", {}).get("balanced", {})
    balanced_arms = balanced.get("review", {}).get("hosts", {})
    if balanced.get("main_tier") != "helm" or "review_setup" in balanced:
        mark_fail("balanced launch preset must start HELM and carry no legacy review name")
    # Both arms, each pointed at the OTHER family. One arm, or two naming the same
    # provider, is exactly the cross-family loss the per-host form exists to prevent.
    if sorted(balanced_arms) != ["claude", "codex"]:
        mark_fail(f"balanced must review per host; arms: {sorted(balanced_arms)}")
    elif (balanced_arms["claude"]["base"]["provider"]
          == balanced_arms["codex"]["base"]["provider"]):
        mark_fail("balanced reviews on the same provider from both hosts — not cross-family")
    deep_review = launch_profile.get("presets", {}).get("deep-review", {})
    deep_frontier = deep_review.get("frontier_effort", {
        host: launch_profile["hosts"][host]["tiers"]["frontier"]["effort"]
        for host in ("codex", "claude")
    })
    if isinstance(deep_frontier, str):
        deep_frontier = dict.fromkeys(("codex", "claude"), deep_frontier)
    if (
        deep_review.get("main_tier") != "helm"
        or deep_frontier.get("codex") != "max"
        or deep_frontier.get("claude") != "max"
    ):
        mark_fail("deep-review must keep HELM main, pin Codex FRONTIER at max, and cap Claude at max")


@check
def codex_agent_templates():
    expected_agents = {
        "frontier.toml": ("frontier", "gpt-6-astra", "max"),
        "workhorse.toml": ("workhorse", "gpt-5.6-terra", "xhigh"),
        "sweep.toml": ("sweep", "gpt-5.6-luna", "max"),
        "reviewer.toml": ("reviewer", "gpt-5.6-terra", "xhigh"),
    }

    missing_agents = sorted(set(expected_agents) - {path.name for path in agent_dir.glob("*.toml")}) if agent_dir.is_dir() else sorted(expected_agents)
    if missing_agents:
        mark_fail(f"required Codex agent files missing: {', '.join(missing_agents)}")

    for filename, (expected_name, expected_model, expected_effort) in expected_agents.items():
        path = agent_dir / filename
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text())
        except Exception as exc:
            mark_fail(f"agent TOML does not parse: {path} ({exc})")
            continue
        if data.get("name") != expected_name:
            mark_fail(f"{path} name is {data.get('name')!r}, want {expected_name!r}")
        for required_text_field in ("description", "developer_instructions"):
            value = data.get(required_text_field)
            if not isinstance(value, str) or not value.strip():
                mark_fail(f"{path} requires non-empty {required_text_field}")
        if data.get("model") != expected_model:
            mark_fail(f"{path} model is {data.get('model')!r}, want {expected_model!r}")
        if expected_effort is None and "model_reasoning_effort" in data:
            mark_fail(f"{path} must omit model_reasoning_effort so HELM can pin task-fit effort per dispatch")
        elif expected_effort is not None and data.get("model_reasoning_effort") != expected_effort:
            mark_fail(
                f"{path} effort is {data.get('model_reasoning_effort')!r}, "
                f"want {expected_effort!r}"
            )


@check
def config_fragment():
    # codex/config-additions.toml is the additive fragment install merges into the
    # live ~/.codex/config.toml; its agent entries are projections of the canonical
    # codex/agents/*.toml templates and must not drift from them.
    fragment_path = pathlib.Path("codex/config-additions.toml")
    if not fragment_path.is_file():
        mark_fail("required file missing: codex/config-additions.toml")
    else:
        fragment = tomllib.loads(fragment_path.read_text())
        if fragment.get("features", {}).get("multi_agent") is not True:
            mark_fail("config-additions must set features.multi_agent = true")
        fragment_agents = fragment.get("agents", {})
        if set(fragment_agents) != {"frontier", "workhorse", "sweep"}:
            mark_fail(
                "config-additions agents must be exactly the spawnable tiers "
                f"(no helm): {sorted(fragment_agents)}"
            )
        for tier, spec in fragment_agents.items():
            template_path = agent_dir / f"{tier}.toml"
            template = tomllib.loads(template_path.read_text()) if template_path.is_file() else {}
            if spec.get("description") != template.get("description"):
                mark_fail(f"config-additions {tier} description drifted from {template_path}")
            if spec.get("config_file") != f"${{CODEX_HOME}}/agents/{tier}.toml":
                mark_fail(
                    f"config-additions {tier} config_file must be "
                    f"${{CODEX_HOME}}/agents/{tier}.toml"
            )


@check
def environment_bindings():
    for guide_name in [
        "claude/guides/cli-multi-model-workflow.md",
        "codex/guides/cli-multi-model-workflow.md",
        "ko/claude/guides/cli-multi-model-workflow.md",
        "ko/codex/guides/cli-multi-model-workflow.md",
    ]:
        guide = pathlib.Path(guide_name)
        rows = {slot: table_row(guide, slot) for slot in ("FRONTIER", "HELM", "WORKHORSE", "SWEEP")}
        for slot, row in rows.items():
            if row is None or len(row) < 2:
                mark_fail(f"{guide} missing Environment Binding row for {slot}")
        # The model each slot binds comes from the launch profile through the declared display
        # map — the gate holds no copy of its own, so a rebind cannot leave the gate enforcing
        # yesterday's model. What stays as literals below is POLICY the profile does not carry
        # (when Ultra is allowed, that a main Ultra needs explicit selection): those are not
        # restatements of profile data, so asserting them here is not a second authorship.
        profile = tomllib.loads(launch_profile_path.read_text())
        display = profile.get("model_display", {})
        if not display:
            mark_fail("launch profile declares no [model_display] map — the binding tables would "
                      "have to be compared against names written inside this gate")
        for slot in ("FRONTIER", "HELM", "WORKHORSE", "SWEEP"):
            if not rows[slot]:
                continue
            for host in ("claude", "codex"):
                tier = (profile["hosts"][host]["tiers"].get(slot.lower()) or {})
                model_id = tier.get("model")
                want = display.get(model_id)
                if not want:
                    mark_fail(f"{model_id!r} has no [model_display] entry; {guide} {slot} cannot "
                              f"be checked against the profile")
                elif not has_exact_model(rows[slot][1], want):
                    mark_fail(f"{guide} {slot} must bind {want} for host {host} — the launch "
                              f"profile says {model_id!r}")
        if rows["FRONTIER"] and (
            "max" not in rows["FRONTIER"][1] or "Ultra" not in rows["FRONTIER"][1]
        ):
            mark_fail(f"{guide} FRONTIER must bind at max with Ultra allowed")
        if rows["HELM"] and (
            "xhigh" not in rows["HELM"][1]
            or "bounded FRONTIER Ultra" not in rows["HELM"][1]
            or not any(token in rows["HELM"][1] for token in ("explicit selection", "명시 선택"))
        ):
            mark_fail(f"{guide} HELM must keep the main at xhigh, require explicit main Ultra selection, and allow bounded FRONTIER Ultra dispatch")
        for slot in ("WORKHORSE", "SWEEP"):
            if not rows[slot]:
                continue
            for host in ("claude", "codex"):
                binding = profile["hosts"][host]["tiers"][slot.lower()]
                model = display[binding["model"]]
                expected = binding.get("effort")
                labels = ("effort omitted", "effort 생략") if expected is None else (expected,)
                if not any(f"{model} ({label})" in rows[slot][1] for label in labels):
                    mark_fail(f"{guide} {slot} must show {host} effort {expected!r} beside {model}")


@check
def codex_helm():
    def helm_dry(path, *args):
        return invoke(["bash", str(path), "--dry-run", "--reach", "hermetic", *args, "probe"])

    def binding(source, label):
        if not isinstance(source, dict):
            mark_fail(f"codex-helm contract source has no {label} binding")
            return None
        model, effort = source.get("model"), source.get("effort")
        if not isinstance(model, str) or not model or not isinstance(effort, str) or not effort:
            mark_fail(f"codex-helm contract source has invalid {label} binding: {source!r}")
            return None
        return model, effort

    codex_tiers = launch_profile.get("hosts", {}).get("codex", {}).get("tiers", {})
    frontier = binding(codex_tiers.get("frontier"), "Codex FRONTIER")
    workhorse = binding(codex_tiers.get("workhorse"), "Codex WORKHORSE")
    sweep = binding(codex_tiers.get("sweep"), "Codex SWEEP")
    reviewer_path = agent_dir / "reviewer.toml"
    try:
        reviewer = tomllib.loads(reviewer_path.read_text())
    except Exception as exc:
        mark_fail(f"codex-helm contract source cannot read {reviewer_path}: {exc}")
        reviewer = {}
    reviewer = binding(
        {"model": reviewer.get("model"), "effort": reviewer.get("model_reasoning_effort")},
        "REVIEWER template",
    )

    role_contracts = []
    for role, seat, sandbox in (
        ("WORKHORSE", workhorse, "read-only-or-workspace-write"),
        ("SWEEP", sweep, "read-only"),
        ("REVIEWER", reviewer, "read-only"),
    ):
        if seat is not None:
            role_contracts.append((role, f"{role}={seat[0]}/{seat[1]}/{sandbox}"))
    if len(role_contracts) != 3:
        mark_fail("codex-helm has fewer than three internal role contracts to check")

    frontier_description = None
    frontier_command = None
    if frontier is not None:
        frontier_model, frontier_effort = frontier
        frontier_description = (
            f"Use codex-run with {frontier_model}/read-only and task-fit effort: "
            f"{frontier_effort} default, Ultra for divisible work, lower when cost/latency dominates."
        )
        frontier_command = (
            f"--model {frontier_model} --effort <effort> --multi-agent auto --sandbox read-only"
        )

    def emitted_contract_errors(result):
        if result.returncode != 0:
            return [("wrapper", f"dry-run returned {result.returncode}: {result.stderr.strip()}")]
        errors = []
        # These patterns cover only the wrapper's emitted role and FRONTIER contract fields.
        role_pattern = re.compile(
            r"\b(?P<role>WORKHORSE|SWEEP|REVIEWER)="
            r"(?P<model>[A-Za-z0-9._-]+)/(?P<effort>[A-Za-z0-9._-]+)/"
            r"(?P<sandbox>[A-Za-z0-9_-]+)"
        )
        observed_roles = {}
        for match in role_pattern.finditer(result.stdout):
            observed_roles.setdefault(match.group("role"), set()).add(match.group(0))
        for role, expected in role_contracts:
            observed = observed_roles.get(role, set())
            if expected not in observed:
                errors.append((role, f"missing internal role binding {expected!r}"))
            unexpected = sorted(observed - {expected})
            if unexpected:
                errors.append((role, f"contradictory internal role binding(s) {unexpected!r}"))

        description_pattern = re.compile(
            r"Use codex-run with [A-Za-z0-9._-]+/read-only and task-fit effort: "
            r"[A-Za-z0-9._-]+ default, Ultra for divisible work, lower when cost/latency dominates\."
        )
        observed_descriptions = {match.group(0) for match in description_pattern.finditer(result.stdout)}
        if frontier_description is not None and frontier_description not in observed_descriptions:
            errors.append(("FRONTIER descriptive binding", f"missing {frontier_description!r}"))
        if frontier_description is not None:
            unexpected = sorted(observed_descriptions - {frontier_description})
            if unexpected:
                errors.append(("FRONTIER descriptive binding", f"contradictory binding(s) {unexpected!r}"))

        command_pattern = re.compile(
            r"--model [A-Za-z0-9._-]+ --effort <effort> --multi-agent auto --sandbox read-only"
        )
        observed_commands = {match.group(0) for match in command_pattern.finditer(result.stdout)}
        if frontier_command is not None and frontier_command not in observed_commands:
            errors.append(("FRONTIER executable command", f"missing {frontier_command!r}"))
        if frontier_command is not None:
            unexpected = sorted(observed_commands - {frontier_command})
            if unexpected:
                errors.append(("FRONTIER executable command", f"contradictory binding(s) {unexpected!r}"))
        return errors


    if not helm.is_file():
        mark_fail("required file missing: wrappers/codex-helm.sh")
    else:
        if "Expert Codex config override" not in helm.read_text():
            mark_fail("codex-helm must document -c as an expert override")
        frontier_tokens = (
            "Do not use native spawn_agent for FRONTIER",
            "adapter enables native multi-agent only for ultra",
            "agents.max_threads=4",
            "agents.max_depth=1",
        )
        for mode in ("auto", "implement", "review", "scout", "single"):
            result = helm_dry(helm, "--mode", mode)
            if not expect_text(
                result,
                f"codex-helm {mode} dry-run",
                ("--bypass-sandbox", "features.multi_agent=false"),
                ("explicitly selected Codex Ultra",),
            ):
                continue
            match = re.search(rf"^mode={mode} reach=hermetic model=(\S+) effort=(\S+) sandbox=(\S+) ", result.stdout, re.MULTILINE)
            if not match or match.groups() != ("gpt-5.6-sol", "xhigh", "dangerously-bypass-approvals-and-sandbox"):
                mark_fail(f"codex-helm {mode} defaults are missing or incorrect")
            has_adapter = "Internal FRONTIER command base" in result.stdout
            if has_adapter != (mode != "single"):
                mark_fail(f"codex-helm {mode} FRONTIER adapter exposure is incorrect")
            if mode != "single":
                for token in frontier_tokens:
                    if token not in result.stdout:
                        mark_fail(f"codex-helm {mode} missing FRONTIER contract token: {token}")
                for subject, failure in emitted_contract_errors(result):
                    mark_fail(f"codex-helm {mode} {subject}: {failure}")
            else:
                for subject, expected in role_contracts:
                    if expected in result.stdout:
                        mark_fail(f"codex-helm single unexpectedly exposes {subject}")
                for subject, expected in (
                    ("FRONTIER descriptive binding", frontier_description),
                    ("FRONTIER executable command", frontier_command),
                ):
                    if expected is not None and expected in result.stdout:
                        mark_fail(f"codex-helm single unexpectedly exposes {subject}")

        expect_text(
            helm_dry(helm, "--effort", "ultra"),
            "codex-helm Ultra dry-run",
            ("explicitly selected Codex Ultra", "features.multi_agent=true"),
        )
        single_ultra = helm_dry(helm, "--mode", "single", "--effort", "ultra")
        if single_ultra.returncode == 0 or "Ultra requires fan-out" not in single_ultra.stderr:
            mark_fail("codex-helm single + Ultra must fail with the fan-out explanation")
        expect_text(
            helm_dry(helm, "--no-fanout"),
            "codex-helm no-fanout dry-run",
            ("Do not spawn subagents",),
            ("Internal FRONTIER command base",),
        )
        limited = helm_dry(helm, "--max-threads", "2", "--max-depth", "2")
        expect_text(
            limited,
            "codex-helm FRONTIER limits",
            ("Internal FRONTIER command base",),
        )
        frontier_line = next((line for line in limited.stdout.splitlines() if line.startswith("- Internal FRONTIER command base:")), "")
        if "agents.max_threads=2" not in frontier_line or "agents.max_depth=2" not in frontier_line:
            mark_fail("codex-helm FRONTIER command does not carry the requested 2/2 limits")
        for args in (
            ("--sandbox", "read-only"),
            ("--sandbox", "read-only", "--allow-danger"),
            ("--allow-danger", "--sandbox", "read-only"),
        ):
            expect_text(
                helm_dry(helm, *args),
                f"codex-helm explicit sandbox order {' '.join(args)}",
                ("sandbox=read-only",),
                ("--bypass-sandbox",),
            )

        # Disposable wrappers run replacement and additive drift through the live assertion.
        replacements = []
        revert_roles = {
            "WORKHORSE": "WORKHORSE=gpt-5.6-terra/high/read-only-or-workspace-write",
            "SWEEP": "SWEEP=gpt-5.6-luna/low/read-only",
            "REVIEWER": "REVIEWER=gpt-5.6-terra/high/read-only",
        }
        for role, expected in role_contracts:
            replacements.append((role, expected, revert_roles[role]))
        if frontier_description is not None:
            replacements.append((
                "FRONTIER descriptive binding",
                frontier_description,
                frontier_description.replace("gpt-6-astra", "gpt-5.6-sol"),
            ))
        if frontier_command is not None:
            replacements.append((
                "FRONTIER executable command",
                frontier_command,
                frontier_command.replace("gpt-6-astra", "gpt-5.6-sol"),
            ))
        additions = [
            (subject, expected, f"{expected}\n- {subject}: {reverted}")
            for subject, expected, reverted in replacements
        ]
        controls = [
            ("replacement", subject, expected, reverted)
            for subject, expected, reverted in replacements
        ] + [
            ("additive", subject, expected, added)
            for subject, expected, added in additions
        ]
        if len(replacements) != 5 or len(additions) != 5:
            mark_fail("codex-helm role/FRONTIER controls have an incomplete subject set")
        else:
            with tempfile.TemporaryDirectory() as raw_tmp:
                tmp = pathlib.Path(raw_tmp)
                copied_helm = tmp / "codex-helm.sh"
                copied_run = tmp / "codex-run.sh"
                shutil.copy2(helm, copied_helm)
                shutil.copy2(helm.parent / "codex-run.sh", copied_run)
                source = copied_helm.read_text()
                for kind, subject, expected, mutated in controls:
                    if expected == mutated or source.count(expected) != 1:
                        mark_fail(
                            f"codex-helm {kind} {subject} control has no unique mutable wrapper binding"
                        )
                        continue
                    copied_helm.write_text(source.replace(expected, mutated, 1))
                    errors = emitted_contract_errors(helm_dry(copied_helm))
                    copied_helm.write_text(source)
                    if subject not in {name for name, _ in errors}:
                        mark_fail(
                            f"codex-helm {kind} {subject} control did not fail through its named "
                            "emitted-contract assertion"
                        )


@check
def purpose_obligations():
    """Three promoted purpose clauses that would otherwise be enforced by prose alone.

    Each would hold only because nobody had edited the line that makes it true. They are one
    check because they share that shape: a stated guarantee with no assertion behind it.
    """
    # PU-6 — "deployment is by copy and explicit; never a postinstall side effect". A postinstall
    # script exists. It prints today, and nothing said it had to keep printing.
    pkg = json.loads(pathlib.Path("package.json").read_text())
    post = pkg.get("scripts", {}).get("postinstall", "").strip()
    if post:
        # Parsed, not grepped: the printed MESSAGE names commands the user should run, so a
        # substring search for "agent-bios " or "&&" flags the text it is meant to allow. What
        # matters is whether anything executes outside the quoted argument, so the quoted part is
        # removed and the remainder must be nothing but the printf call itself.
        try:
            words = shlex.split(post)
        except ValueError:
            words = None
        if not words or words[0] != "printf" or len(words) > 2:
            mark_fail("package.json postinstall must be a single print-only `printf` — "
                      "deployment is an explicit command, never an install side effect "
                      f"(got: {post[:70]!r})")

    # PU-11 / PL-2 — English is installed, Korean is reference only. The installer deploys
    # English, but nothing forbade the Korean tree from entering the published payload: the
    # package gate exempts `ko` by NAME, which permits its absence rather than its presence.
    for pattern in pkg.get("files", []):
        if pattern.strip("/").split("/")[0] == "ko":
            mark_fail(f"package.json files[] ships {pattern!r} — the Korean tree is reference "
                      f"only and must never enter the payload")

    # PU-17 — the deployed state answers for itself. The version marker is what `status` reads
    # when the deploying command is long gone, so it has to be written AND manifested (or
    # uninstall would strand it) AND read back.
    installer = pathlib.Path("install.sh").read_text()
    if "$STATE_DIR/version.json" not in installer:
        mark_fail("install.sh writes no version marker — `status` would have nothing to read")
    if 'printf \'%s\\n\' "$STATE_DIR/version.json" >> "$MANIFEST"' not in installer:
        mark_fail("the version marker is not manifested, so uninstall would leave it behind "
                  "claiming a version that is no longer deployed")
    if "deployed_version()" not in installer or "drift_state()" not in installer:
        mark_fail("nothing reads the version marker back — a marker with no reader is inert")


@check
def uninstall_keeps_a_backup_it_could_not_stage():
    """A copy that never reached the stage must not be deleted from the original.

    Waiting for `tar` made the purge recoverable only for files the archive actually holds.
    Every staging failure here is silent — a full temp filesystem, an unreadable source, a
    destination that cannot be created — and the purge read the ORIGINAL list, so a file missing
    from the archive was removed anyway. Per file, not all-or-nothing: one unreadable copy must
    not keep the rest on disk.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        claude, archive = root / "claude", root / "archive"
        state = root / ".local" / "share" / "agent-bios"
        for d in (claude, archive, state):
            d.mkdir(parents=True)
        ok = claude / "settings.json.bak-20260101-000000"
        bad = claude / "settings.json.bak-20260102-000000"
        ok.write_text("this one stages fine")
        bad.write_text("this one cannot be read")
        bad.chmod(0o000)
        try:
            # If the setup did not actually make it unreadable — running as root does that —
            # the control would pass while testing nothing, so it says so instead.
            try:
                bad.read_text()
                mark_fail("could not make a source unreadable, so this control proved nothing "
                          "about the staging-failure path")
                return
            except PermissionError:
                pass
            env = {**os.environ, "HOME": str(root), "CLAUDE_CONFIG_DIR": str(claude),
                   "CODEX_HOME": str(root / "codex"), "AGENT_LAUNCH_VENV": str(root / "venv"),
                   "AGENT_BIOS_UNINSTALL_ARCHIVE": str(archive)}
            repo = pathlib.Path(__file__).resolve().parents[1]
            result = subprocess.run(["bash", str(repo / "install.sh"), "uninstall"], env=env,
                                    cwd=str(repo), capture_output=True, text=True,
                                    stdin=subprocess.DEVNULL)
            out = result.stdout + result.stderr
            # Positive control: the purge has to have run, or "the unreadable one survived" is
            # true for the wrong reason.
            if ok.exists():
                mark_fail("uninstall did not purge a backup it staged successfully, so this "
                          "control cannot distinguish a careful purge from no purge at all")
                return
            if not bad.exists():
                mark_fail("uninstall deleted a backup it could not stage — the archive does not "
                          "contain it, so nothing can restore it")
            if "could not stage" not in out:
                mark_fail("the staging failure was not reported; the operator is told everything "
                          "was archived while one file was left behind")
        finally:
            bad.chmod(0o644)


@check
def uninstall_without_a_manifest_spares_the_entry_files():
    """With no manifest, uninstall must not delete the files it does not own.

    That branch runs exactly when state is missing or agent-bios was never installed here, so
    nothing says we wrote anything. It used to remove `CLAUDE.md` and `AGENTS.md` whole — and
    since the modes converged those are the user's, the first seeded once and the second ours
    only between the central markers. There is no backup on this path either: BACKUP_DIR is set
    on the manifest branch alone, so the copy was gone with no way back.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        claude, codex = root / "claude", root / "codex"
        for d in (claude, codex):
            d.mkdir(parents=True)
        mine_claude = "instructions only this user wrote"
        mine_codex = "a codex rule only this user wrote"
        (claude / "CLAUDE.md").write_text(f"# CLAUDE.md\n\n- {mine_claude}\n")
        (codex / "AGENTS.md").write_text(f"# AGENTS.md\n\n- {mine_codex}\n")
        # No state dir at all, which is what puts uninstall on the fallback branch.
        env = {**os.environ, "HOME": str(root), "CLAUDE_CONFIG_DIR": str(claude),
               "CODEX_HOME": str(codex), "AGENT_LAUNCH_VENV": str(root / "venv"),
               "AGENT_BIOS_UNINSTALL_ARCHIVE": str(root)}
        repo = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(["bash", str(repo / "install.sh"), "uninstall"], env=env,
                                cwd=str(repo), capture_output=True, text=True,
                                stdin=subprocess.DEVNULL)
        if "no manifest" not in (result.stdout + result.stderr):
            mark_fail("uninstall did not take the no-manifest branch, so this control proved "
                      "nothing about it")
            return
        for label, path, secret in (("the claude entry", claude / "CLAUDE.md", mine_claude),
                                    ("the codex entry", codex / "AGENTS.md", mine_codex)):
            if not path.is_file() or secret not in path.read_text():
                mark_fail(f"uninstall destroyed {label} on the no-manifest path — without a "
                          "manifest nothing says we wrote it, and this branch has no backup")


@launcher_check
def dynamic_toml_keys_keep_their_identity(fx):
    """A name the user chose must come back as the name they chose.

    Bare TOML keys hold only letters, digits, `-` and `_`, so any dynamic segment written
    unquoted turns a dot into NESTING: a review arm authored `future.host` was written
    back as `future`, and a capability named `tool.v1` registered as `tool` while the
    method needing it still asked for `tool.v1` — registration then reported it live for
    something the config did not contain. Round-tripped through the real renderer and the
    real reader, with a hyphenated twin as the control: quoting everything into a
    different shape would move both, and only the dotted one is supposed to move."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    profile = pathlib.Path("launch/agent-launch.toml")
    base = tomllib.loads(profile.read_text(encoding="utf-8"))

    def arm_survives(arm_name):
        config = copy.deepcopy(base)
        preset = copy.deepcopy(config["presets"]["balanced"])
        preset.pop("review_setup", None)
        preset.pop("review_family", None)
        preset["review"] = {"hosts": {
            "codex": {"base": {"provider": "openai", "tier": "frontier"}},
            arm_name: {"base": {"provider": "anthropic", "tier": "frontier"}},
        }}
        config["presets"]["probe"] = preset
        plan = launcher_module.build_plan(config, "codex", "probe")
        fields, overrides, review = launcher_module.preset_from_plan(plan, config, "probe")
        rendered = launcher_module.render_preset_block("probe", fields, overrides, review)
        back = tomllib.loads(rendered)["presets"]["probe"]["review"]["hosts"]
        return arm_name in plan["review_arms"], arm_name in back

    for label, arm in (("a dotted", "future.host"), ("a hyphenated", "future-host")):
        present, survived = arm_survives(arm)
        if not present:
            mark_fail(f"the {label} review-arm probe never reached the plan — measuring nothing")
        elif not survived:
            mark_fail(f"saving a preset renamed {label} review arm {arm!r} out of existence")

    # The same question at the LEAF of an inactive host's tier override, which the two
    # probes above cannot reach: they move a table NAME, and this writer emitted its leaf
    # keys raw, so `future.field` reloaded as the table `future` holding `field` — the
    # value under a name nobody wrote (round 24, #10). An inactive host's block is written
    # back as authored, so its leaf names are the profile author's; the selected host's are
    # closed to model and effort and cannot express the case at all.
    def override_leaf_survives(leaf_name):
        config = copy.deepcopy(base)
        preset = copy.deepcopy(config["presets"]["balanced"])
        preset["tier_overrides"] = {"claude": {"sweep": {leaf_name: "keep-me"}}}
        config["presets"]["probe-leaf"] = preset
        plan = launcher_module.build_plan(config, "codex", "probe-leaf")
        fields, overrides, review = launcher_module.preset_from_plan(plan, config, "probe-leaf")
        rendered = launcher_module.render_preset_block("probe-leaf", fields, overrides, review)
        back = tomllib.loads(rendered)["presets"]["probe-leaf"]["tier_overrides"]["claude"]["sweep"]
        carried = plan.get("tier_overrides", {}).get("claude", {}).get("sweep", {})
        return carried.get(leaf_name) == "keep-me", back.get(leaf_name) == "keep-me"

    for label, leaf in (("a dotted", "future.field"), ("a hyphenated", "future-field")):
        present, survived = override_leaf_survives(leaf)
        if not present:
            mark_fail(
                f"the {label} tier-override leaf probe never reached the plan — measuring nothing"
            )
        elif not survived:
            mark_fail(
                f"saving a preset renamed {label} tier-override leaf {leaf!r} out of existence"
            )

    def capability_registers(capability_name):
        capability = {"name": capability_name, "command": "tool", "install": "",
                      "operation": "review", "adapter": "exec-stdio-v1", "hosts": ["codex"]}
        answers = {"id": "trial", "label": "Trial", "description": "Trial",
                   "capability": capability,
                   "instructions": "run {command} on {model}/{effort}",
                   "perspectives": ["correctness"], "trials": 1,
                   "severity_emits": ["high"], "severity_map": {"high": "high"}}
        texts = {
            "profiles.toml": profile.read_text(encoding="utf-8"),
            "review-methods.local.toml": (
                launcher_module.USER_METHODS_HEADER
                + launcher_module._render_registration(answers)),
        }

        class FakePath:
            def __init__(self, name): self.name = name
            def read_text(self, encoding="utf-8"): return texts[self.name]
            def with_name(self, name): return FakePath(name)
            def is_file(self): return self.name in texts
            def __str__(self): return self.name

        config = launcher_module.load_config(FakePath("profiles.toml"))
        methods = launcher_module.load_review_methods(config)
        if "trial" not in methods:
            return None
        return methods["trial"].capability in config["capabilities"]

    for label, name in (("a dotted", "tool.v1"), ("a hyphenated", "tool-v1")):
        registered = capability_registers(name)
        if registered is None:
            mark_fail(f"the {label} capability probe registered no method — measuring nothing")
        elif not registered:
            mark_fail(
                f"registering {label} capability {name!r} left the method pointing at a "
                f"capability the config does not define, while reporting it live"
            )


@launcher_check
def saving_a_preset_never_leaves_an_unreadable_file(fx):
    """Save rewrites a file the user owns, so the file it leaves must be readable.

    Which lines belong to the block being replaced is a question about TOML, and the
    line scanner answering it has been narrowed three times — a header inside a
    multiline string, a quoted header name, and now a triple quote inside a COMMENT,
    each of which made Save append a duplicate table and replace the file without
    reading it back. This asserts the outcome rather than the scanner: whatever the
    scanner decides, the file the user is left with parses, or nothing is written.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    config_path = pathlib.Path("launch/agent-launch.toml")
    config = launcher_module.load_config(config_path)
    plan = launcher_module.build_plan(config, "codex", "balanced")
    fields, overrides, review = launcher_module.preset_from_plan(plan, config, "gate-probe")
    block = launcher_module.render_preset_block("gate-probe", fields, overrides, review)
    triple_quote = chr(34) * 3

    def attempt(header):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            local_config = tmp / "profiles.toml"
            local_config.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
            target = launcher_module.user_presets_path(local_config)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(header + block, encoding="utf-8")
            try:
                tomllib.loads(target.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError:
                return "fixture-invalid", False, False
            before = target.read_text(encoding="utf-8")
            try:
                launcher_module.save_preset(plan, config, local_config, "gate-probe")
                outcome = "saved"
            except launcher_module.LaunchError:
                outcome = "refused"
            after = target.read_text(encoding="utf-8")
            try:
                tomllib.loads(after)
                readable = True
            except tomllib.TOMLDecodeError:
                readable = False
            return outcome, readable, after == before

    for label, header in (
        ("a comment containing a triple quote", "# note: token " + triple_quote + "\n"),
        ("a comment containing a header name", "# note: [presets.gate-probe] is mine\n"),
        ("an ordinary comment", "# note: nothing unusual\n"),
        ("no comment at all", ""),
    ):
        outcome, readable, unchanged = attempt(header)
        if outcome == "fixture-invalid":
            mark_fail(f"agent-launch save probe fixture for {label} is not valid TOML")
            continue
        if not readable:
            mark_fail(
                f"agent-launch save left the user presets file unreadable after {label}"
            )
        elif outcome == "refused" and not unchanged:
            mark_fail(
                f"agent-launch save refused after {label} but had already written to the file"
            )
    # The control: an ordinary file must actually be WRITTEN, or a save that refuses
    # everything satisfies every row above.
    outcome, readable, unchanged = attempt("# note: nothing unusual\n")
    if outcome != "saved" or unchanged:
        mark_fail(
            f"agent-launch save did not write an ordinary user presets file "
            f"(outcome={outcome} unchanged={unchanged})"
        )


@check
def uninstall_cleanup_does_not_depend_on_a_readable_manifest():
    """--remove-owned says removal does not need a well-formed manifest. Half of it does not.

    The parse sat above the branch, so a corpus mid-edit raised out of uninstall before the
    branch that needs nothing from it. The two halves need it differently: the AGENTS.md
    region is bounded by our own markers, while the settings registrations are owned BY NAME
    and cannot be found without the manifest. So the region must go either way, and the half
    that cannot run has to be said out loud rather than warned about and summarised over."""
    source = pathlib.Path("compose/assemble.py")
    if not source.is_file():
        mark_fail("required file missing: compose/assemble.py")
        return
    region = "<!-- agent-bios:central:start -->\nours\n<!-- agent-bios:central:end -->\n"
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)

        def drive(manifest_text):
            root = tmp / ("broken" if manifest_text is None else "clean")
            (root / "compose").mkdir(parents=True)
            (root / "claude").mkdir()
            shutil.copy2(source, root / "compose" / "assemble.py")
            (root / "compose" / "domains.json").write_text(
                "{not json" if manifest_text is None else manifest_text)
            codex = root / "codex-home"
            codex.mkdir()
            (codex / "AGENTS.md").write_text(f"{region}\nTHEIR-OWN-RULES\n")
            result = invoke([
                sys.executable, str(root / "compose" / "assemble.py"), "--remove-owned",
                "--claude-dir", str(root / "claude-home"), "--codex-dir", str(codex),
                "--state-dir", str(root / "state"),
            ])
            body = (codex / "AGENTS.md").read_text()
            return result, ("agent-bios:central:start" not in body), ("THEIR-OWN-RULES" in body)

        clean, clean_gone, clean_kept = drive('{"hooks": {}, "guides": {}, "agents": {}}')
        if clean.returncode != 0 or not clean_gone:
            mark_fail(
                "--remove-owned does not remove the central region on the happy path "
                f"(rc={clean.returncode} removed={clean_gone}) — the leg is measuring nothing"
            )
            return
        broken, broken_gone, broken_kept = drive(None)
        if not broken_gone:
            mark_fail(
                "an unreadable domains.json stops --remove-owned removing the AGENTS.md "
                "region, which is bounded by our own markers and needs no manifest"
            )
        if broken.returncode == 0:
            mark_fail(
                "--remove-owned reports success although it could not read the manifest "
                "naming the settings registrations it was asked to remove"
            )
        elif "settings.json" not in broken.stdout + broken.stderr:
            mark_fail("--remove-owned failed without naming what was left behind")
        for label, kept in (("happy path", clean_kept), ("unreadable manifest", broken_kept)):
            if not kept:
                mark_fail(f"--remove-owned took the user's own AGENTS.md text on the {label}")


@check
def a_failed_write_never_truncates_a_user_file():
    """The assembler edits files the user owns, and a plain write truncates before it fills.

    settings.json and AGENTS.md are theirs — they edit both — and the backup taken beside
    these writes is of the PREVIOUS content, which is exactly what a half-written file
    destroys the value of. A short write left AGENTS.md holding a fragment of our marker and
    none of their text. Driven by making the write fail rather than by reading the source,
    because the property is what survives, not which function was called."""
    driver = r'''
import importlib.util, pathlib, sys, tempfile
spec = importlib.util.spec_from_file_location("asm", "compose/assemble.py")
m = importlib.util.module_from_spec(spec); sys.modules["asm"] = m; spec.loader.exec_module(m)
tmp = pathlib.Path(tempfile.mkdtemp())
agents = tmp / "AGENTS.md"
agents.write_text(f"BEFORE-TEXT\n{m.MARK_START}\nold\n{m.MARK_END}\nAFTER-TEXT\n")
real = pathlib.Path.write_text
def flaky(self, data, **kw):
    if FAIL and self.name.startswith("AGENTS.md"):
        with open(self, "w", encoding="utf-8") as handle:
            handle.write(data[:20])
        raise OSError("simulated short write")
    return real(self, data, **kw)
pathlib.Path.write_text = flaky
raised = ""
try:
    m.merge_codex(tmp, "# NEW-REGION\n")
except Exception as exc:
    raised = type(exc).__name__
finally:
    pathlib.Path.write_text = real
body = agents.read_text()
leftovers = [p.name for p in tmp.iterdir() if p.name != "AGENTS.md"]
print("raised=%s before=%s after=%s applied=%s leftovers=%d" % (
    raised or "none", "BEFORE-TEXT" in body, "AFTER-TEXT" in body,
    "# NEW-REGION" in body, len(leftovers)))
'''
    def drive(fail):
        return invoke([sys.executable, "-c", f"FAIL={fail}\n" + driver])

    broken, clean = drive(True), drive(False)
    if "raised=OSError" not in broken.stdout:
        mark_fail(
            "the failed-write probe did not fail — it is proving nothing "
            f"({broken.stdout.strip()[:120]}{broken.stderr.strip()[:120]})"
        )
        return
    for label, needed in (("before=True", "text before the region"),
                          ("after=True", "text after the region")):
        if label not in broken.stdout:
            mark_fail(f"a failed assembler write destroyed the user's {needed}: {broken.stdout.strip()}")
    if "applied=True" in broken.stdout:
        mark_fail("a failed assembler write reported as applied anyway: " + broken.stdout.strip())
    if "leftovers=0" not in broken.stdout:
        mark_fail("a failed assembler write left its temp file behind: " + broken.stdout.strip())
    # Control: the same driver with the write allowed must actually apply the region, or
    # every assertion above is satisfied by an assembler that never writes at all.
    if "applied=True" not in clean.stdout or "after=True" not in clean.stdout:
        mark_fail("the successful-write control did not apply the region: " + clean.stdout.strip())


@check
def uninstall_will_not_delete_what_it_could_not_copy():
    """"Back up before deleting" is a claim about the copy LANDING, not being attempted.

    archive_and_purge below is scrupulous about this — nothing is deleted unless it
    verifiably reached the stage — while the manifest loop above it ran `mkdir && cp` and
    never read the result, so a deployed file was removed and reached neither the backup
    nor the archive built from it. The manifest that names it has to survive too, or the
    file is left on disk with nothing recording that it is ours."""
    repo = pathlib.Path(__file__).resolve().parents[1]

    def uninstall(block_backups):
        tmp = pathlib.Path(tempfile.mkdtemp())
        claude = tmp / "claude"
        state = tmp / ".local" / "share" / "agent-bios"
        archive = tmp / "archive"
        (claude / "central" / "guides").mkdir(parents=True)
        state.mkdir(parents=True)
        archive.mkdir()
        deployed = claude / "central" / "guides" / "a-guide.md"
        deployed.write_text("a deployed guide\n")
        (state / "manifest.txt").write_text(f"{deployed}\n")
        # A regular FILE where the backup directory must go, so mkdir cannot create it. Not an
        # unwritable directory: that stops blocking anything when the suite runs as root, and a
        # control that quietly cannot fire is not a control.
        if block_backups:
            (state / "backups").write_text("")
        env = {**os.environ, "HOME": str(tmp), "ZDOTDIR": str(tmp),
               "CLAUDE_CONFIG_DIR": str(claude), "CODEX_HOME": str(tmp / "codex"),
               "AGENT_LAUNCH_VENV": str(tmp / "venv"),
               "AGENT_BIOS_UNINSTALL_ARCHIVE": str(archive)}
        result = subprocess.run(["bash", str(repo / "install.sh"), "uninstall"], env=env,
                                cwd=str(repo), capture_output=True, text=True,
                                stdin=subprocess.DEVNULL)
        tarballs = sorted(archive.glob("*.tar.gz"))
        archived = False
        if tarballs:
            with tarfile.open(tarballs[0]) as handle:
                archived = any("a-guide.md" in name for name in handle.getnames())
        return {
            "output": result.stdout + result.stderr,
            "took_the_manifest_branch": "no manifest at" not in result.stdout,
            "file_survives": deployed.is_file(),
            "manifest_survives": (state / "manifest.txt").is_file(),
            "archived": archived,
        }

    # Positive control first: with a writable backup destination the file really is removed
    # AND really is in the archive, so "it survived" below is attributable to the block.
    clean = uninstall(block_backups=False)
    if not clean["took_the_manifest_branch"]:
        mark_fail("uninstall probe never found its manifest — the leg is measuring nothing")
        return
    if clean["file_survives"] or not clean["archived"]:
        mark_fail(
            "uninstall does not remove-and-archive a manifested file on the happy path "
            f"(survives={clean['file_survives']} archived={clean['archived']})"
        )
    blocked = uninstall(block_backups=True)
    if not blocked["took_the_manifest_branch"]:
        mark_fail("blocked uninstall probe never found its manifest — measuring nothing")
        return
    if blocked["archived"]:
        mark_fail("the blocked-backup probe archived the file anyway — the block did not fire")
    elif not blocked["file_survives"]:
        mark_fail(
            "uninstall deleted a deployed file whose backup copy failed, leaving nothing in "
            "the archive to restore it from"
        )
    elif not blocked["manifest_survives"]:
        mark_fail(
            "uninstall left a deployed file on disk but purged the manifest naming it, so "
            "nothing records that the file is ours"
        )
    elif "nothing of ours is left on this machine" in blocked["output"]:
        mark_fail("uninstall left a file behind and still reported a clean removal")


@check
def uninstall_keeps_backups_when_the_archive_fails():
    """A failed archive must leave the originals exactly where they were.

    Only the successful archive was ever exercised. On the failure path the loose copies had
    already been deleted before `tar` ran, so an unwritable destination took the backups with
    it — while the warning told the operator that "state, backups and the venv were left in
    place". The filesystem and the message disagreed, and only the message was visible.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        claude, state = root / "claude", root / ".local" / "share" / "agent-bios"
        for d in (claude / "central", state):
            d.mkdir(parents=True)
        (claude / "CLAUDE.md").write_text("# CLAUDE.md\n@central/bundle.md\n")
        (claude / "central" / "bundle.md").write_text("# assembled corpus\n")
        (state / "manifest.txt").write_text(f"{claude / 'central' / 'bundle.md'}\n")
        backup = claude / "settings.json.bak-20260101-000000"
        backup.write_text("the only copy of something the user may still want")
        # A regular FILE where a directory is expected, so the archive path cannot be created.
        # Chosen over an unwritable directory because that one stops blocking anything when the
        # suite happens to run as root, and a control that quietly cannot fire is not a control.
        blocked = root / "not-a-directory"
        blocked.write_text("")
        env = {**os.environ, "HOME": str(root), "CLAUDE_CONFIG_DIR": str(claude),
               "CODEX_HOME": str(root / "codex"), "AGENT_LAUNCH_VENV": str(root / "venv"),
               "AGENT_BIOS_UNINSTALL_ARCHIVE": str(blocked)}
        repo = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(["bash", str(repo / "install.sh"), "uninstall"], env=env,
                                cwd=str(repo), capture_output=True, text=True,
                                stdin=subprocess.DEVNULL)
        # Positive control first, so a surviving backup is attributable to the fix rather than
        # to an uninstall that never reached the archive at all.
        if "could not write" not in (result.stdout + result.stderr):
            mark_fail("the archive was supposed to fail and did not, so this control proved "
                      "nothing — it ran the success path again")
            return
        if not backup.is_file():
            mark_fail("a failed archive deleted the loose backup anyway — the warning claims "
                      "backups were left in place, and nothing is recoverable")


def owned_sibling_rule():
    """The shipped answer to "is this loose backup ours", imported rather than restated.

    Author-side may import shipped; the reverse is what the payload boundary forbids. Copying
    the pattern here would give the gate its own third statement of the rule, which is how a
    check goes on passing after the thing it checks has moved.
    """
    spec = importlib.util.spec_from_file_location(
        "prune_backups_under_test",
        pathlib.Path(__file__).resolve().parents[1] / "compose" / "prune-backups.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OWNED_SIBLING


@check
def uninstall_leaves_no_trace():
    """Uninstall must remove everything of ours AND lose nothing the user wrote.

    Those pull opposite ways because full mode writes the corpus into an entry file the user then
    edits, so the same bytes are both. One archive settles it: the removed content leaves as a
    single artifact outside every managed path, and the managed paths are then purged. This runs
    the real command against a throwaway HOME, because a destructive path asserted only in prose
    is the kind that works until the day it matters.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        claude, archive = root / "claude", root / "archive"
        state = root / ".local" / "share" / "agent-bios"   # derived from HOME by install.sh
        codex = root / "codex"
        for d in (claude, archive, state / "backups" / "old", root / "venv",
                  root / ".cache" / "agent-launch", claude / "guides", codex / "guides"):
            d.mkdir(parents=True, exist_ok=True)
        secret = "a line only this user wrote"
        # The entry file is the USER'S since the modes converged, so it is deliberately not in
        # the manifest: uninstall must take our central tree and leave their file standing.
        (claude / "CLAUDE.md").write_text(f"# CLAUDE.md\n@central/bundle.md\n\n- {secret}\n")
        (claude / "central").mkdir()
        (claude / "central" / "bundle.md").write_text("# assembled corpus\n")
        (claude / "settings.json.bak-20260101-000000").write_text("a loose backup copy")
        # The same basename under both host trees. Staging used to flatten every copy into one
        # directory, so the second silently overwrote the first — and both originals were deleted
        # regardless, leaving the archive with one of the two.
        (claude / "guides" / "learnings.md.bak-migrate-20260101-000000").write_text("claude copy")
        (codex / "guides" / "learnings.md.bak-migrate-20260101-000000").write_text("codex copy")
        # NOT ours: same shared directory, but no marker this repo writes. `*.bak-*` claimed it.
        (claude / "notes.bak-old").write_text("a file the user saved by hand")
        (state / "manifest.txt").write_text(f"{claude / 'central' / 'bundle.md'}\n")
        (state / "backups" / "old" / "f").write_text("an earlier backup")
        env = {**os.environ, "HOME": str(root), "CLAUDE_CONFIG_DIR": str(claude),
               "CODEX_HOME": str(root / "codex"), "AGENT_LAUNCH_VENV": str(root / "venv"),
               "AGENT_BIOS_UNINSTALL_ARCHIVE": str(archive)}
        # Resolved from this file, not the ambient cwd: the subprocess gets its own HOME, and
        # a gate that depends on where it was invoked from is one that passes for the wrong reason.
        repo = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(["bash", str(repo / "install.sh"), "uninstall"], env=env,
                                cwd=str(repo), capture_output=True, text=True,
                                stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            mark_fail(f"uninstall failed on a throwaway home: {result.stderr[-200:]}")
            return
        archives = list(archive.glob("*.tar.gz"))
        if len(archives) != 1:
            mark_fail(f"uninstall must leave exactly one archive, found {len(archives)}")
            return
        for label, path in (("state dir", state), ("venv", root / "venv"),
                            ("cache", root / ".cache" / "agent-launch"),
                            ("the central tree", claude / "central")):
            if path.exists():
                mark_fail(f"uninstall left {label} behind at {path} — it is a security operation")
        # The other half: what is theirs must still be there. A removal that satisfies the
        # security rule by deleting the user's own file has not passed, it has overshot.
        entry = claude / "CLAUDE.md"
        if not entry.is_file() or secret not in entry.read_text():
            mark_fail("uninstall removed the user-owned entry file or its contents — the entry "
                      "is seeded once and then theirs")
        owned = owned_sibling_rule()
        left = [p for p in claude.rglob("*") if p.is_file() and owned.search(p.name)]
        if left:
            mark_fail(f"uninstall left loose backup copies of ours behind: {left}")
        if not (claude / "notes.bak-old").is_file():
            mark_fail("uninstall deleted a backup it does not own — these config dirs are shared "
                      "with the user and with other tools, so the NAME carries ownership and the "
                      "directory never does")
        with tarfile.open(archives[0]) as tar:
            bodies = [tar.extractfile(m).read().decode("utf-8", "replace")
                      for m in tar.getmembers() if m.isfile()]
        if not any("a loose backup copy" in b for b in bodies):
            mark_fail("the archive does not carry what was removed — purging without a "
                      "recoverable copy is the data loss the archive exists to prevent")
        # BOTH, never either: these two share a basename, and flattened staging kept one.
        for marker in ("claude copy", "codex copy"):
            if not any(marker in b for b in bodies):
                mark_fail(f"the archive lost the {marker!r} backup — two same-named copies from "
                          "the two host trees must both survive staging")


def _package_json_at(ref):
    """package.json as of a git ref, or None when it cannot be read."""
    out = subprocess.run(["git", "show", f"{ref}:package.json"],
                         capture_output=True, text=True,
                         cwd=str(pathlib.Path(__file__).resolve().parents[1]))
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


@check
def release_date_moves_with_the_version():
    """A version bump must carry its release date with it.

    `install.sh` copies both fields into `$STATE_DIR/version.json` and the launcher renders them
    together, so a bump that leaves `releaseDate` behind ships a package that tells every user
    the wrong date. v0.9.9 did exactly that, and nothing noticed: the field is hand-maintained
    and no check held it to the version. It is a restatement of something the tag and the
    registry already know, which is why it drifts — the durable fix is to derive it, and this is
    the cheap guard until then.

    Decidable, so it blocks: the question is only whether two fields moved together. It compares
    the working tree against HEAD, so it fires exactly on the commit that bumps the version and
    is silent on every other one — including a fresh clone, where the two agree by construction.
    """
    here = json.loads(pathlib.Path("package.json").read_text(encoding="utf-8"))
    before = _package_json_at("HEAD")
    if before is None:
        mark_fail("could not read package.json at HEAD, so the version/date pairing went "
                  "unchecked rather than passing quietly")
        return
    if before.get("version") == here.get("version"):
        return  # no bump in flight; nothing to hold together
    if before.get("releaseDate") == here.get("releaseDate"):
        # An unmoved date is wrong only when it is not, in fact, today: a same-day
        # second release legitimately keeps the date, and demanding a change there
        # forces a lie. Local time, like the hand that maintains the field.
        if here.get("releaseDate") == datetime.date.today().isoformat():
            return
        mark_fail(f"version moved {before.get('version')} -> {here.get('version')} while "
                  f"releaseDate stayed {here.get('releaseDate')}, which is not today. "
                  "install.sh copies both into version.json and the launcher shows them "
                  "together, so this ships the wrong date to every user of the new version.")


@check
def ui_catalogs_hold_the_reference_key_set():
    """UI text i18n: `en` is the reference key-set and the other catalogs match it exactly.

    Five decidable claims, each loud on its own: every `t("...")` literal in the launcher
    exists in en.toml (a call with no string is invisible UI text); en.toml carries no key
    no call uses (an orphan is a string nobody renders); ko/ja equal en's key-set in both
    directions (an incomplete catalog must be unshippable, not silently hybrid); and each
    key's `{slot}` names match en's, because a composed string is formatted at render and
    a translation that drops or misspells a slot raises there — for ko/ja readers only,
    which no English-language test can reach. Keys are scanned as single-line `t("...")`
    literals — a COMPUTED key is invisible and fails as an orphan, while a call wrapped
    across lines is seen normally, because `\\s` matches newlines. This docstring claimed
    the opposite until a review tested it.
    """
    directory = pathlib.Path("launch/i18n")
    catalogs = {}
    for language in ("en", "ko", "ja"):
        path = directory / f"{language}.toml"
        if not path.is_file():
            mark_fail(f"UI text catalog missing: {path}")
            return
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            mark_fail(f"UI text catalog {path} does not parse: {exc}")
            return
        catalogs[language] = {k: v for k, v in raw.items() if isinstance(v, str)}
    pattern = r'\bt\(\s*"([^"]+)"\s*\)'
    launcher_source = launcher.read_text(encoding="utf-8")
    called = set(re.findall(pattern, launcher_source))
    # The scanner itself is the subtlest part, so it carries its own control: a literal
    # call it cannot see would let every claim below pass over nothing.
    if "gate.control.probe" not in set(re.findall(pattern, 't("gate.control.probe")')):
        mark_fail("UI text catalog scanner cannot see a literal t() call — vacuous")
        return
    if not called:
        mark_fail('no t("...") calls in the launcher — the catalog check is vacuous')
        return
    if not catalogs["en"]:
        mark_fail("the English UI text catalog is empty — the completeness check is vacuous")
        return
    unknown = sorted(called - set(catalogs["en"]))
    if unknown:
        mark_fail(f"launcher asks for UI text key(s) absent from en.toml: {', '.join(unknown)}")
    orphans = sorted(set(catalogs["en"]) - called)
    if orphans:
        mark_fail(f"en.toml carries key(s) no t() call renders: {', '.join(orphans)}")
    # A composed string's slots are part of its contract. `t(key).format(...)` raises
    # at render time when a translation misspells or drops one, and every claim above
    # passes over that: the key exists and the value is non-empty. Comparing slot NAMES
    # per key is decidable, so it is gated rather than reviewed. Both the extractor and
    # the comparison carry their own control — a slot-blind regex would let this pass
    # over every catalog.
    # Fields come from Python's own parser everywhere, never a regex. A regex
    # cannot tell `{latest}` from `{{latest}}`: the first is a field, the second is
    # an escaped brace that renders the text "{latest}" on screen, and a
    # translation changed that way used to pass every check here.
    def fields_of(value):
        """(parsed_ok, {root name: format_spec}) for one catalog value."""
        try:
            parsed = list(string.Formatter().parse(value))
        except ValueError:
            return False, {}
        found = {}
        for _, field, spec, conversion in parsed:
            if field is None:
                continue
            root = field.split(".")[0].split("[")[0]
            # The remainder is KEPT, not folded away. Reducing {tier.foo} to its
            # root made it validate and then raise AttributeError at render, and
            # {tier[0]} validated and silently drew "H". The launcher passes plain
            # strings, so any navigation past the root name is wrong by construction.
            trailer = field[len(root):]
            decoration = trailer + (spec or "") + ("!" + conversion if conversion else "")
            # ACCUMULATED, never assigned. `{outcome:d} … {outcome}` let the second,
            # bare occurrence overwrite the first one's spec, so the value validated
            # and then raised at render on the occurrence nobody had looked at.
            found[root] = found.get(root, "") + decoration
        return True, found

    def slots(value):
        return set(fields_of(value)[1])

    # Comparing translations against each other cannot see a value that is broken
    # in every language at once, and that is not hypothetical: a stray "}" raises
    # ValueError, and a slot misspelled consistently in all three raises KeyError
    # against the kwargs the CALL SITE passes. So each formatted value is also
    # checked against Python's own parser and against those kwargs, read from the
    # source. A key nothing formats is exempt by construction rather than by an
    # exemption list — `wizard.instructions.label` shows {command} to the user as
    # text and is never formatted, so no brace of it can raise.
    # Parsed, not pattern-matched. A regex for `.format(...)` stops at the first
    # ")", so a call whose arguments nest parens — v.get("closed", "?") — reports
    # kwargs the site really does pass as missing. That was a false failure on
    # distill.version.description before this became an AST walk.
    try:
        tree = ast.parse(launcher_source)
    except SyntaxError as exc:
        mark_fail(f"launcher does not parse, so format sites cannot be read: {exc}")
        return
    per_site = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"):
            continue
        inner = node.func.value
        if not (isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "t"
                and len(inner.args) == 1
                and isinstance(inner.args[0], ast.Constant)
                and isinstance(inner.args[0].value, str)):
            continue
        per_site.setdefault(inner.args[0].value, []).append(
            {keyword.arg for keyword in node.keywords if keyword.arg}
        )
    # Intersection, not union: a key formatted at two sites must be renderable at
    # both, so only the kwargs every site passes may appear in the value.
    formatted = {key: set.intersection(*sites) for key, sites in per_site.items()}
    # Every t("…") that is NOT the receiver of a .format() call. A key formatted at
    # one site and bare at another stayed in `formatted` and so escaped the
    # unformatted scan entirely — `model.title` has two sites, and deleting the
    # formatter from one of them drew a raw "{tier} model" on the Other-model prompt
    # while the gate stayed green.
    receivers = {
        id(node.func.value) for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    }
    bare_sites = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "t" and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and id(node) not in receivers):
            bare_sites[node.args[0].value] = bare_sites.get(node.args[0].value, 0) + 1

    def format_problems(key, language, value):
        """Every way this value can fail at render. Shared by the loop and its
        control, so a control cannot pass while the real logic is gone."""
        found = []
        kwargs = formatted.get(key)
        if kwargs is None:
            return found
        parsed_ok, field_specs = fields_of(value)
        if not parsed_ok:
            found.append(
                f"{language}.toml {key} is not a valid format string; "
                f"rendering that screen raises"
            )
            return found
        # A format spec on UI text buys nothing and raises on the wrong type:
        # `{outcome:d}` parses, validates by name, and dies at render because the
        # launcher passes a string. Catalog slots name a value; they do not format it.
        spec_bearing = sorted(f"{name} (as {{{name}{spec}}})" for name, spec in field_specs.items() if spec)
        if spec_bearing:
            found.append(
                f"{language}.toml {key} decorates slot(s) {', '.join(spec_bearing)}; "
                "UI text names a slot and nothing more — an attribute, an index, a "
                "format spec or a conversion either raises at render or silently "
                "renders part of the value"
            )
            return found
        fields = list(field_specs)
        # The call site passes a keyword the value never uses: the argument goes
        # missing from the screen with nothing raised. `{{pending}}` escaped in all
        # three catalogs reads as damage-free to a cross-catalog comparison, and the
        # count it was meant to show simply disappears.
        unused = sorted(kwargs - set(fields))
        if unused:
            found.append(
                f"{language}.toml {key} never uses "
                f"{', '.join('{' + u + '}' for u in unused)}, which the call site passes; "
                "the value it carries silently does not reach the screen"
            )
        # Fields come from Python's own parser, not from a second regex. A regex
        # over `{name}` cannot see `{}` or `{0}`: both parse cleanly and both raise
        # IndexError at render, because every call site passes keywords and no
        # positional arguments at all.
        positional = [f for f in fields if f == "" or f.split(".")[0].split("[")[0].isdigit()]
        if positional:
            found.append(
                f"{language}.toml {key} uses positional field(s) "
                f"{', '.join('{' + f + '}' for f in positional)}; every call site passes "
                f"keywords only — render raises IndexError"
            )
            return found
        named = {f.split(".")[0].split("[")[0] for f in fields}
        unknown = sorted(named - kwargs)
        if unknown:
            found.append(
                f"{language}.toml {key} formats slot(s) the call site never passes: "
                f"{', '.join('{' + s + '}' for s in unknown)}; it passes "
                f"{', '.join(sorted(kwargs)) or 'nothing'} — render raises KeyError"
            )
        return found

    def parity_problems(key, language, reference, translated):
        """Slot names a translation lost or invented against English. Dropping one
        loses information silently rather than raising, which is why this survives
        alongside the format check above."""
        found = []
        lost = sorted(slots(reference) - slots(translated))
        invented = sorted(slots(translated) - slots(reference))
        if lost:
            found.append(
                f"{language}.toml key {key} drops slot(s) en.toml formats: "
                f"{', '.join('{' + s + '}' for s in lost)} — the value goes missing on render"
            )
        if invented:
            found.append(
                f"{language}.toml key {key} invents slot(s) en.toml never passes: "
                f"{', '.join('{' + s + '}' for s in invented)} — format() raises on render"
            )
        return found

    if slots("Use {model} for {tier}.") != {"model", "tier"}:
        mark_fail("UI text slot extractor cannot see a {slot} — vacuous")
        return
    # Driven through parity_problems itself, so deleting its comparisons takes the
    # control with them rather than leaving a green check over absent logic.
    if len(parity_problems("k", "control", "{tier}", "{teir}")) != 2:
        mark_fail("UI text parity control: a swapped slot was not reported both ways — vacuous")
        return
    if parity_problems("k", "control", "{tier} x", "x {tier}"):
        mark_fail("UI text parity control: flagged a faithful reordering")
        return
    if not formatted:
        mark_fail("no t(...).format(...) call sites found — the render checks are vacuous")
        return
    # The controls drive format_problems itself, not a copy of its reasoning, so
    # deleting the production checks inside it takes these down with it.
    probe_key = next(iter(formatted))
    probe_kwargs = formatted[probe_key]
    if not format_problems(probe_key, "control", "{" + "".join(probe_kwargs) + "} }"):
        mark_fail("UI text format control: a stray brace was not reported — vacuous")
        return
    if not format_problems(probe_key, "control", "{definitely_not_a_real_slot}"):
        mark_fail("UI text format control: an unpassed slot was not reported — vacuous")
        return
    for shape in ("{}", "{0}"):
        if not format_problems(probe_key, "control", f"x {shape}"):
            mark_fail(
                f"UI text format control: positional field {shape} was not reported — "
                "vacuous (it parses cleanly and raises IndexError on render)"
            )
            return
    if format_problems("a.key.nothing.formats", "control", "{whatever} }"):
        mark_fail("UI text format control: flagged a key no call site formats")
        return
    # A slot-bearing key that NOTHING formats renders its template to the user.
    # Deleting a `.format(...)` from a call site used to make its key vanish from
    # `formatted` and become exempt by absence — the check disappeared with the
    # code it was checking. Exemption is now explicit, carries its reason, and is
    # itself asserted to still apply.
    EXEMPT_UNFORMATTED = {
        "wizard.instructions.label":
            "shows the slot NAMES to the user as documentation of what a reviewer "
            "instruction may interpolate; it is prose about slots, not a template",
        "wizard.cap.command.label":
            "names the shell-style ${backend} placeholder the user may type; the "
            "brace is part of the literal the reader must copy",
    }
    for key, reason in sorted(EXEMPT_UNFORMATTED.items()):
        if key not in catalogs["en"]:
            mark_fail(f"unformatted-slot exemption names a key en.toml no longer has: {key}")
        elif key in formatted:
            mark_fail(f"unformatted-slot exemption is stale — {key} IS formatted now: {reason}")
    unformatted = sorted(
        key for key, value in catalogs["en"].items()
        if slots(value) and key not in formatted and key not in EXEMPT_UNFORMATTED
    )
    if unformatted:
        mark_fail(
            "en.toml key(s) carry {slots} that no call site formats, so the template "
            f"renders to the user: {', '.join(unformatted)}"
        )
    partly = sorted(
        key for key, value in catalogs["en"].items()
        if slots(value) and key in formatted and bare_sites.get(key)
        and key not in EXEMPT_UNFORMATTED
    )
    if partly:
        mark_fail(
            "en.toml key(s) carry {slots} and are formatted at some call sites but "
            f"not all, so the bare ones render the template: {', '.join(partly)}"
        )
    def examine(language, values):
        """Every per-value format check over one catalog. The real catalogs and the
        control below both go through THIS function, so stubbing it — or replacing
        the call with an empty list — takes the control down with the checking. A
        counter cannot see that; a shared code path can."""
        problems = []
        for key, value in sorted(values.items()):
            problems.extend(format_problems(key, language, value))
        return problems

    # The control rides the production path: a planted violation must come back out
    # of the same function that examines the shipped catalogs.
    if not examine("control", {probe_key: "{" + "".join(probe_kwargs) + "} }"}):
        mark_fail("format examination reported nothing on a planted violation — vacuous")
        return
    # English included: a malformed value there raises for everyone.
    examined = 0
    for language in ("en", "ko", "ja"):
        examined += len(catalogs[language])
        for problem in examine(language, catalogs[language]):
            mark_fail(problem)
    # The controls above prove the helpers behave; this proves the helpers were
    # actually run over the shipped catalogs. Deleting the loop leaves them green.
    # The threshold is the SUM over all three catalogs, not en's key count.
    # len(catalogs["en"]) was satisfied by examining English alone, which left every
    # ko and ja value unchecked — precisely the readers these checks exist for.
    expected_examinations = sum(len(catalogs[lang]) for lang in ("en", "ko", "ja"))
    if examined < expected_examinations:
        mark_fail(
            f"format checks examined {examined} value(s), not the {expected_examinations} "
            "across en/ko/ja — the loop is not reaching every shipped value"
        )
    for language in ("ko", "ja"):
        gaps = sorted(set(catalogs["en"]) - set(catalogs[language]))
        extra = sorted(set(catalogs[language]) - set(catalogs["en"]))
        if gaps:
            mark_fail(f"{language}.toml is missing key(s): {', '.join(gaps)}")
        if extra:
            mark_fail(f"{language}.toml carries key(s) en.toml does not: {', '.join(extra)}")
        empty = sorted(k for k, v in catalogs[language].items() if not v.strip())
        if empty:
            mark_fail(f"{language}.toml has empty value(s) for: {', '.join(empty)}")
        # Decomposed Hangul renders identically and measures differently: NFD
        # "적용 버전" is 16 code points to the panel's width function and 9 cells on
        # screen, so a decomposed label misaligns the panel AND passes the alignment
        # leg, whose ruler counts the same way. macOS filesystems hand out NFD
        # readily, so this is a paste away rather than hypothetical.
        decomposed = sorted(
            key for key, value in catalogs[language].items()
            if value != unicodedata.normalize("NFC", value)
        )
        if decomposed:
            mark_fail(
                f"{language}.toml value(s) are not NFC-normalised: {', '.join(decomposed)} "
                "— they render the same and measure wider, which misaligns the corpus panel"
            )
        compared = 0
        for key, reference in sorted(catalogs["en"].items()):
            translated = catalogs[language].get(key)
            if translated is None:
                continue  # already reported as a gap
            problems = parity_problems(key, language, reference, translated)
            compared += 1
            for problem in problems:
                mark_fail(problem)
        shared = len(set(catalogs["en"]) & set(catalogs[language]))
        if compared < shared:
            mark_fail(
                f"slot parity compared {compared} of {shared} shared key(s) for "
                f"{language} — the loop is not reaching every translated value"
            )


@check
def capture_works_anywhere():
    """PU-12 — capture works from any directory, not only from a clone.

    `collect-learning.py` resolves its home from the environment and said so in a comment. A
    comment is not a check, and the failure it prevents is silent: run from elsewhere, write
    nowhere the agent reads.
    """
    script = pathlib.Path("learn/collect-learning.py").resolve()
    if not script.is_file():
        mark_fail("learn/collect-learning.py missing")
        return
    with tempfile.TemporaryDirectory() as foreign:
        home = pathlib.Path(foreign) / "claude-home"
        home.mkdir()
        # cwd is the subject here, so this runs directly rather than through invoke().
        # HOME too, not only the config home: the upload transport resolves its
        # slot from $HOME (ENDPOINTS.md), so redirecting the config home alone
        # would leave a harness pointed at the operator's real endpoint.
        result = subprocess.run([sys.executable, str(script), "--self-test"],
                                cwd=foreign, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL,
                                env={**os.environ, "CLAUDE_CONFIG_DIR": str(home),
                                     "HOME": foreign})
        if result.returncode != 0:
            mark_fail(f"collect-learning fails when run from a directory that is not a clone: "
                      f"{(result.stdout + result.stderr)[-200:]}")


@check
def codex_run():
    run = pathlib.Path("wrappers/codex-run.sh")
    if not run.is_file():
        mark_fail("required file missing: wrappers/codex-run.sh")
    else:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            fake, argv_log = tmp / "codex", tmp / "argv"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"$FAKE_CODEX_ARGV\"\n"
                "printf 'progress-err\\n' >&2\n"
                "printf 'final-out\\n'\n"
                "exit \"${FAKE_CODEX_STATUS:-0}\"\n"
            )
            fake.chmod(0o755)
            env = os.environ.copy()
            env.update(PATH=f"{tmp}{os.pathsep}{env.get('PATH', '')}", FAKE_CODEX_ARGV=str(argv_log))

            def fake_call(argv):
                result = invoke(argv, input_text="probe\n", env=env)
                return result, argv_log.read_text().splitlines()

            def expect_args(label, received, present=(), absent=(), pair=None):
                for token in present:
                    if token not in received:
                        mark_fail(f"{label} missing argument: {token}")
                for token in absent:
                    if token in received:
                        mark_fail(f"{label} unexpectedly passed argument: {token}")
                if pair and not any(received[i : i + 2] == list(pair) for i in range(len(received) - 1)):
                    mark_fail(f"{label} missing argument pair: {' '.join(pair)}")

            result, received = fake_call([
                "bash", str(run), "--profile", "inherit", "--bypass-sandbox",
                "--model", "gpt-5.6-sol", "--effort", "max", "-",
            ])
            if (result.returncode, result.stdout, result.stderr) != (0, "final-out\n", "progress-err\n"):
                mark_fail("codex-run does not preserve stdout/stderr/exit channels")
            expect_args(
                "codex-run bypass",
                received,
                ("--dangerously-bypass-approvals-and-sandbox", "gpt-5.6-sol", 'model_reasoning_effort="max"'),
                ("--sandbox",),
            )
            result, received = fake_call(["bash", str(run), "--profile", "inherit", "--sandbox", "read-only"])
            expect_args(
                "codex-run explicit sandbox",
                received,
                absent=("--dangerously-bypass-approvals-and-sandbox",),
                pair=("--sandbox", "read-only"),
            )
            if result.returncode != 0:
                mark_fail("codex-run explicit sandbox fake runtime failed")

            for effort, multi_agent in (("max", "false"), ("ultra", "true")):
                result, received = fake_call([
                    "bash", str(run), "--profile", "inherit", "--effort", effort, "--multi-agent", "auto",
                ])
                if result.returncode != 0:
                    mark_fail(f"codex-run multi-agent auto failed at {effort}")
                expect_args(
                    f"codex-run multi-agent auto {effort}",
                    received,
                    (f'model_reasoning_effort="{effort}"', f"features.multi_agent={multi_agent}"),
                )

            for effort, multi_agent in (("xhigh", "false"), ("ultra", "true")):
                result, received = fake_call(["bash", str(helm), "--reach", "inherit", "--effort", effort, "probe"])
                if result.returncode != 0:
                    mark_fail(f"codex-helm fake runtime failed at effort {effort}: {result.stderr.strip()}")
                expect_args(
                    f"codex-helm {effort}",
                    received,
                    ("--dangerously-bypass-approvals-and-sandbox", f'model_reasoning_effort="{effort}"', f"features.multi_agent={multi_agent}"),
                    ("--sandbox",),
                )

            # Advanced launch docs promise an explicit --sandbox disables the HELM default bypass
            # "regardless of flag order", and the flag that would re-enable it is parsed
            # in the same loop — so the reversed order is the case worth pinning, not
            # the one a reader would write first.
            for label, extra in (
                ("explicit sandbox", ["--sandbox", "read-only"]),
                ("explicit sandbox after --allow-danger", ["--allow-danger", "--sandbox", "read-only"]),
                ("explicit sandbox before --allow-danger", ["--sandbox", "read-only", "--allow-danger"]),
            ):
                result, received = fake_call(["bash", str(helm), "--reach", "inherit", *extra, "probe"])
                if result.returncode != 0:
                    mark_fail(f"codex-helm {label} fake runtime failed: {result.stderr.strip()}")
                expect_args(
                    f"codex-helm {label}",
                    received,
                    absent=("--dangerously-bypass-approvals-and-sandbox",),
                    pair=("--sandbox", "read-only"),
                )

            env["FAKE_CODEX_STATUS"] = "7"
            failed, _ = fake_call(["bash", str(run), "--profile", "inherit", "--bypass-sandbox"])
            if failed.returncode != 7:
                mark_fail(f"codex-run returns {failed.returncode} instead of Codex exit status 7")


@check
def dry_run_previews_the_run_it_replaces():
    """A dry run must describe the run it stands in for, not a different one.

    Separate from "a dry run changes nothing", which the install scenarios already hold:
    a preview can be perfectly clean and still report the opposite outcome. Migration
    named only `$STATE_DIR/selection.json` — a file a dry run deliberately does not write
    — so on a fresh state directory both hosts fell into "skipped" while the real run,
    which writes that file moments earlier, migrated for real. Driven by sourcing
    install.sh and calling the one function, because the assertion is about which
    arguments it builds; the full install scenarios cost ~45s each and buy nothing here."""
    installer = pathlib.Path("install.sh")
    if not installer.is_file():
        mark_fail("required file missing: install.sh")
        return
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)

        def drive(dry, state):
            script = (
                'set -- status\n'
                f'source ./{installer} >/dev/null 2>&1\n'
                f'DRY_RUN={dry}; DOMAINS_SET=0; DOMAINS_ARG=\n'
                f'STATE_DIR={tmp / state}\n'
                f'CLAUDE_DIR={tmp / state}-claude\n'
                f'CODEX_DIR={tmp / state}-codex\n'
                'MANIFEST="$STATE_DIR/manifest.txt"\n'
                'PRIOR_MANIFEST="$STATE_DIR/manifest.prev.txt"\n'
                'migrate_learnings 2>&1\n'
            )
            return invoke(["bash", "-c", script])

        preview = drive(1, "fresh-dry")
        real = drive(0, "fresh-real")
        if "selection file not found" in preview.stdout + preview.stderr:
            mark_fail(
                "install.sh dry-run migration asks for a selection file a dry run never "
                "writes, so the preview reports a failure the real run does not have"
            )
        # Compare the per-host verdicts rather than the text, which carries a `[dry]` tag
        # by design. An empty extraction would make them trivially equal, so it is asserted.
        def verdicts(result):
            return sorted(re.findall(r"host=(\w+)\s+([\w-]+)", result.stdout + result.stderr))
        preview_says, real_says = verdicts(preview), verdicts(real)
        if not preview_says:
            mark_fail("install.sh dry-run migration named no per-host outcome at all")
        elif preview_says != real_says:
            mark_fail(
                f"install.sh dry-run migration previews {preview_says} but the real run "
                f"does {real_says}"
            )


@check
def canary_separates_not_loading_from_not_probed():
    """The canary's own header: only a probe that really replied may return 1.

    The 1-vs-3 split is the whole value of this script — answering "the bundle is not
    loading" for a dispatch that never happened sends a reader to re-approve imports for
    a question nobody asked. Every case is driven with a fake CLI on PATH, so what is
    asserted is the script's arithmetic on a real reply, not a real model's answer."""
    canary = pathlib.Path("compose/canary.sh")
    if not canary.is_file():
        mark_fail("required file missing: compose/canary.sh")
        return
    marker = "agent-bios-bundle-rev: gatecanary"
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)
        for sub in ("cfg/central", "bin", "home"):
            (tmp / sub).mkdir(parents=True)
        (tmp / "cfg/central/bundle.md").write_text(f"# bundle\n\n{marker}\n")

        def drive(body):
            (tmp / "bin/claude").write_text(f"#!/usr/bin/env bash\n{body}\n")
            (tmp / "bin/claude").chmod(0o755)
            env = os.environ.copy()
            env.update(
                PATH=f"{tmp / 'bin'}{os.pathsep}{env.get('PATH', '')}",
                HOME=str(tmp / "home"),
                CLAUDE_CONFIG_DIR=str(tmp / "cfg"),
                AGENT_BIOS_STATE_DIR=str(tmp / "state"),
            )
            return invoke(["bash", str(canary)], env=env)

        # 0 = proven loading, 1 = proven NOT loading, 3 = could not be established.
        for label, body, want in (
            ("marker echoed", f'echo "{marker}"', 0),
            ("marker echoed but the CLI exits nonzero", f'echo "{marker}"; exit 2', 0),
            ("a real reply without the marker", "echo BUNDLE-NOT-LOADED", 1),
            ("a failed dispatch that printed something",
             'echo "Error: connection reset by peer"; exit 1', 3),
            ("a failed dispatch that printed nothing", "exit 1", 3),
            ("an unauthenticated CLI", 'echo "Invalid API key"; exit 1', 3),
        ):
            result = drive(body)
            if result.returncode != want:
                mark_fail(
                    f"compose/canary.sh on {label}: exit {result.returncode}, want {want} "
                    f"({result.stdout.strip().splitlines()[:1]})"
                )
        # The verdicts must not agree with each other, or asserting them proves nothing:
        # a script that always answered 3 satisfies half the rows above.
        proven = drive(f'echo "{marker}"').returncode
        refuted = drive("echo BUNDLE-NOT-LOADED").returncode
        unprobed = drive("exit 1").returncode
        if len({proven, refuted, unprobed}) != 3:
            mark_fail(
                "compose/canary.sh returns the same verdict for loading, not-loading and "
                f"not-probed ({proven}/{refuted}/{unprobed}) — the split is not being made"
            )


@check
def managed_venv_is_an_enhancement():
    """A venv that cannot be executed must degrade, not end the launch.

    provision-venv.sh states it plainly: missing or broken, the launcher falls back to
    numbered prompts. `os.execve` returns only by failing, and a file can be +x without
    being a program — a venv carried across architectures, or truncated mid-creation.
    Driven in a subprocess because the passing case really does replace the process."""
    driver = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('al', {str(launcher)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "sys.modules['al'] = m\n"
        "spec.loader.exec_module(m)\n"
        "m.maybe_reexec_into_venv()\n"
        "print('SURVIVED')\n"
    )
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)
        (tmp / "home").mkdir()
        broken = tmp / "broken"
        (broken / "bin").mkdir(parents=True)
        (broken / "bin" / "python").write_text("this is not a program\n")
        (broken / "bin" / "python").chmod(0o755)

        def drive(venv):
            env = os.environ.copy()
            env.update(HOME=str(tmp / "home"), AGENT_LAUNCH_VENV=str(venv))
            env.pop("AGENT_LAUNCH_REEXEC", None)
            return invoke([sys.executable, "-c", driver], env=env)

        result = drive(broken)
        if result.returncode != 0 or "SURVIVED" not in result.stdout:
            mark_fail(
                "agent-launch does not survive an unrunnable managed venv interpreter: "
                f"rc={result.returncode} {result.stderr.strip()[-160:]}"
            )
        elif "unusable" not in result.stderr:
            mark_fail("agent-launch swallowed an unrunnable managed venv without saying so")
        # Control: with no venv to find at all there is nothing to warn about, so a leg
        # that passed by never reaching the interpreter would show up here as the same
        # silence the real fallback produces.
        control = drive(tmp / "absent")
        if control.returncode != 0 or "SURVIVED" not in control.stdout:
            mark_fail("agent-launch does not survive an ABSENT managed venv")
        elif "unusable" in control.stderr:
            mark_fail("agent-launch reports an unusable venv interpreter where none exists")


@check
def claude_run():
    """The seat a receipt names must be the seat the tool ran on.

    That is the whole reason claude-run exists, and it is exactly the property a
    wrapper cannot hold by remembering its own arguments: claude takes the LAST
    --model/--effort on its command line, and this adapter forwards expert overrides
    verbatim by design, so a pin the wrapper was ASKED for and a pin the tool RAN on
    are two different values whenever a caller uses the override. Every case below
    carries the control that separates the two — an assertion that only ever sees the
    un-overridden dispatch cannot tell a fixed adapter from a broken one."""
    run = pathlib.Path("wrappers/claude-run.sh")
    if not run.is_file():
        mark_fail("required file missing: wrappers/claude-run.sh")
        return
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)
        bin_dir, root = tmp / "bin", tmp / "root"
        bin_dir.mkdir()
        root.mkdir()
        (bin_dir / "claude").write_text(
            "#!/usr/bin/env bash\n"
            "{ printf 'CWD\\t%s\\n' \"$PWD\"; printf 'ARG\\t%s\\n' \"$@\"; } > \"$FAKE_CLAUDE_ARGV\"\n"
            "cat >/dev/null\n"
            "printf 'progress-err\\n' >&2\n"
            "printf 'final-out\\n'\n"
            "exit \"${FAKE_CLAUDE_STATUS:-0}\"\n"
        )
        (bin_dir / "agent-launch").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$@\" > \"$FAKE_RECEIPT\"\n"
        )
        for name in ("claude", "agent-launch"):
            (bin_dir / name).chmod(0o755)

        argv_log, receipt_log = tmp / "argv", tmp / "receipt"
        env = os.environ.copy()
        env.update(
            PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            FAKE_CLAUDE_ARGV=str(argv_log),
            FAKE_RECEIPT=str(receipt_log),
            AGENT_LAUNCH_BIN=str(bin_dir / "agent-launch"),
            REVIEW_RECEIPT_DIR=str(tmp / "receipts"),
            REVIEW_METHOD_ID="parity-probe",
        )

        def dispatch(*extra):
            for stale in (argv_log, receipt_log):
                if stale.exists():
                    stale.unlink()
            result = invoke(["bash", str(run), *extra], input_text="packet\n", env=env)
            lines = argv_log.read_text().splitlines() if argv_log.exists() else []
            argv = [line.split("\t", 1)[1] for line in lines if line.startswith("ARG\t")]
            cwd = next((line.split("\t", 1)[1] for line in lines if line.startswith("CWD\t")), None)
            # `--emit-receipt METHOD SEAT STATUS PACKET RESULT`
            receipt = receipt_log.read_text().splitlines() if receipt_log.exists() else []
            seat = receipt[2] if len(receipt) > 2 else None
            return result, argv, cwd, seat

        def last_value(argv, flag):
            found = None
            for index, token in enumerate(argv):
                if token == flag and index + 1 < len(argv):
                    found = argv[index + 1]
                elif token.startswith(f"{flag}="):
                    found = token.split("=", 1)[1]
            return found

        pinned = ["--model", "seat-A", "--effort", "high"]
        for label, extra in (
            ("no override", []),
            ("model override after --", ["--", "--model", "seat-B"]),
            ("effort override after --", ["--", "--effort", "max"]),
            ("both overridden after --", ["--", "--model", "seat-B", "--effort", "max"]),
            ("model override forwarded without --", ["--model", "seat-B"]),
        ):
            result, argv, _, seat = dispatch(*pinned, *extra)
            ran_model, ran_effort = last_value(argv, "--model"), last_value(argv, "--effort")
            if not ran_model or not ran_effort:
                mark_fail(f"claude-run {label}: the fake tool saw no --model/--effort at all")
                continue
            want = f"anthropic:{ran_model}/{ran_effort}"
            if seat != want:
                mark_fail(
                    f"claude-run {label}: receipt names seat {seat!r} but the tool ran on "
                    f"{want!r}"
                )
            if result.returncode != 0:
                mark_fail(f"claude-run {label} fake runtime failed: {result.stderr.strip()}")
        # The controls above are only discriminating if the overrides actually moved the
        # seat; if claude's own last-wins parsing ever changed, every case would agree
        # with the pin and the leg would pass while asserting nothing.
        _, argv, _, _ = dispatch(*pinned, "--", "--model", "seat-B")
        if last_value(argv, "--model") != "seat-B":
            mark_fail("claude-run: the override probe no longer moves the dispatched model")

        # --cd names the working root, exactly as codex-run's does. --add-dir alone
        # widens reach and moves the root nowhere, so the control is the cwd itself.
        _, argv, cwd, _ = dispatch(*pinned, "--cd", str(root))
        if cwd != str(root):
            mark_fail(f"claude-run --cd: the tool ran in {cwd!r}, not the named root {str(root)!r}")
        if "--add-dir" not in argv:
            mark_fail("claude-run --cd no longer names the reach it grants in argv")
        _, _, unset_cwd, _ = dispatch(*pinned)
        if unset_cwd == str(root):
            mark_fail("claude-run: the --cd control is vacuous — cwd matches with no --cd given")
        missing = invoke(
            ["bash", str(run), *pinned, "--cd", str(tmp / "absent")], input_text="packet\n", env=env
        )
        if missing.returncode == 0:
            mark_fail("claude-run accepted a --cd working root that does not exist")

        env["FAKE_CLAUDE_STATUS"] = "7"
        failed, _, _, _ = dispatch(*pinned)
        if failed.returncode != 7:
            mark_fail(f"claude-run returns {failed.returncode} instead of Claude exit status 7")


def import_launcher():
    """Import agent-launch as a module so its API can be driven directly."""
    try:
        spec = importlib.util.spec_from_file_location("agent_launch_under_test", launcher)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not create import specification")
        launcher_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = launcher_module
        spec.loader.exec_module(launcher_module)
    except Exception as exc:
        mark_fail(f"agent-launch test import failed: {exc}")
        launcher_module = None
    return launcher_module


@launcher_check
def launcher_syntax(fx):
    syntax = invoke([sys.executable, "-c", f"compile(open({str(launcher)!r}).read(), {str(launcher)!r}, 'exec')"])
    if syntax.returncode != 0:
        mark_fail(f"agent-launch Python syntax failed: {syntax.stderr.strip()}")
    zsh_syntax = invoke(["zsh", "-n", str(shell_init)])
    if zsh_syntax.returncode != 0:
        mark_fail(f"agent-launch zsh syntax failed: {zsh_syntax.stderr.strip()}")


@launcher_check
def launcher_shell_reassert(fx):
    """A tool that redefines `claude` or `codex` after the rc files ran must not win.

    cmux's zsh integration reinstalls its own `claude` function on its first precmd —
    deliberately, after every rc file — so whatever the launcher defined at rc time is
    replaced and bare `claude` skips the preflight in silence. The interception in
    launch/agent-launch.zsh answers at preexec: if the function about to run is not
    byte-identical to ours (or an alias has appeared), redefine it. Every case below runs
    in a temp HOME + ZDOTDIR, never the author's rc files, feeds an interactive shell on
    stdin (`zsh -ilc` runs no precmd and produced a false PASS during the diagnosis), and
    asserts BOTH that our dispatch ran with a per-run nonce AND that the shadower did not
    — a marker alone is satisfied by a mutant that prints it from the hook. The negative
    control removes the preexec hook and must see the shadower win; the evidence writer
    is driven, not assumed: with a state dir the log must carry the shadower's first line
    and `install.sh status` must read it back; without one no log may appear."""
    if shutil.which("zsh") is None:
        mark_fail("zsh not found — the shell reassert check cannot run")
        return
    script = shell_init.resolve()
    repo = pathlib.Path(__file__).resolve().parents[1]
    nonce = uuid.uuid4().hex[:8]
    direct = '_agent_launch_direct() { print "AGENT_LAUNCH_DIRECT host=$1 args=${*:2}" }'

    def shadower(host="claude", body="print SHADOW-RAN \\$*", every=False):
        drop = "" if every else f"add-zsh-hook -d precmd _shadow_{host};"
        return (
            f'autoload -Uz add-zsh-hook; _shadow_{host}() {{ eval "{host}() {{ {body}; }}"; '
            f"{drop} }}; add-zsh-hook precmd _shadow_{host}"
        )

    def run(zshenv_after, zshrc_extra="", commands=None, state=False, env_extra=None,
            zshenv_before="", state_mode=None, real_direct=False):
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / "home"
        zdot = tmp / "zdot"
        home.mkdir()
        zdot.mkdir()
        state_dir = home / ".local" / "share" / "agent-bios"
        if state:
            state_dir.mkdir(parents=True)
            if state_mode is not None:
                state_dir.chmod(state_mode)
        (zdot / ".zshenv").write_text(f'{zshenv_before}\nsource "{script}"\n{zshenv_after}\n')
        (zdot / ".zshrc").write_text(f"{'' if real_direct else direct}\n{zshrc_extra}\n")
        env = {**os.environ, "HOME": str(home), "ZDOTDIR": str(zdot)}
        if real_direct:
            # The true direct path, with a fake `claude` binary first in PATH so the
            # `builtin command claude …` line is exercised without launching anything.
            fake = tmp / "bin"
            fake.mkdir()
            (fake / "claude").write_text('#!/bin/sh\nprintf "REAL-CLAUDE %s\\n" "$*"\n')
            (fake / "claude").chmod(0o755)
            env["PATH"] = f"{fake}:{env.get('PATH', '')}"
        env.update(env_extra or {})
        cmds = list(commands) if commands else [f"claude probe-{nonce}"]
        result = invoke(["zsh", "-il"], input_text="\n".join(cmds) + "\n", env=env)
        log = state_dir / "shell-shadow.log"
        text = log.read_text() if log.exists() else None
        if state and state_mode is not None:
            state_dir.chmod(0o700)
        return result.stdout, text, home

    ours = f"AGENT_LAUNCH_DIRECT host=claude args=probe-{nonce}"

    def expect_ours(label, out, marker=ours, foreign="SHADOW-RAN"):
        ok = True
        if marker not in out:
            mark_fail(f"shell reassert [{label}]: our dispatch did not run: {out.strip()[:160]!r}")
            ok = False
        if foreign in out:
            mark_fail(f"shell reassert [{label}]: the shadower ran: {out.strip()[:160]!r}")
            ok = False
        return ok

    # 1. A precmd shadower (cmux's shape): ours runs, the shadower does not, and no log
    #    appears because there is no state dir.
    out, log, _ = run(shadower())
    expect_ours("precmd shadower", out)
    if log is not None:
        mark_fail("shell reassert: shell-shadow.log appeared without a state dir")
    # 2. Bare `claude` — the live defect's exact shape (no argument to hide behind).
    out, _, _ = run(shadower(), commands=["claude"])
    if not re.search(r"^AGENT_LAUNCH_DIRECT host=claude args=$", out, re.M) or "SHADOW-RAN" in out:
        mark_fail(f"shell reassert [bare claude]: {out.strip()[:160]!r}")
    # 3. The other entrypoint is covered too.
    out, _, _ = run(shadower(host="codex"), commands=[f"codex probe-{nonce}"])
    expect_ours("codex shadower", out, marker=f"AGENT_LAUNCH_DIRECT host=codex args=probe-{nonce}")
    # 4. A foreign body that quotes the ownership marker must still be replaced.
    out, _, _ = run(shadower(body=': "_agent_launch_dispatch claude "; print SHADOW-RAN \\$*'))
    expect_ours("decoy marker body", out)
    # 5. An alias shadow expands at parse time, so the command already parsed is lost;
    #    the next command must be ours and the alias gone.
    alias_sh = (
        'autoload -Uz add-zsh-hook; _shadow_alias() { alias claude="print ALIAS-RAN"; '
        "add-zsh-hook -d precmd _shadow_alias; }; add-zsh-hook precmd _shadow_alias"
    )
    out, _, _ = run(alias_sh, commands=["claude first", f"claude probe-{nonce}"])
    expect_ours("alias shadower, second command", out, foreign=f"ALIAS-RAN probe-{nonce}")
    #    …and a GLOBAL alias (lives in $galiases, not $aliases), and an EMPTY alias, which
    #    erases the command word: both must be detected by existence, not by content.
    galias_sh = (
        'autoload -Uz add-zsh-hook; _shadow_galias() { alias -g claude="print GLOBAL-RAN"; '
        "add-zsh-hook -d precmd _shadow_galias; }; add-zsh-hook precmd _shadow_galias"
    )
    out, _, _ = run(galias_sh, commands=["claude first", f"claude probe-{nonce}"])
    expect_ours("global alias shadower, second command", out, foreign=f"GLOBAL-RAN probe-{nonce}")
    ealias_sh = (
        "autoload -Uz add-zsh-hook; _shadow_ealias() { alias claude=''; "
        "add-zsh-hook -d precmd _shadow_ealias; }; add-zsh-hook precmd _shadow_ealias"
    )
    out, _, _ = run(ealias_sh, commands=["claude first", f"claude probe-{nonce}"])
    expect_ours("empty alias shadower, second command", out, foreign=f"command not found: probe-{nonce}")
    # 6. Aliases that already exist when the file is sourced (a parse-time trap for a
    #    function that defines `claude() {` inside its body), plus ERR_RETURN at
    #    reassert time (an absent alias makes `unalias` return 1).
    out, _, _ = run(shadower(), zshenv_before="alias codex='print PRE-ALIAS'; alias claude='print PRE-ALIAS'",
                    zshrc_extra="setopt ERR_RETURN")
    expect_ours("pre-existing alias + ERR_RETURN", out)
    if "PRE-ALIAS" in out:
        mark_fail(f"shell reassert [pre-existing alias]: the alias survived sourcing: {out.strip()[:160]!r}")
    #    (A round-2 reviewer claimed ERR_RETURN set before the source aborts initialization at
    #    the top-level `unalias`; measured on zsh 5.9 it does not — the source merely returns 1 —
    #    so no case is kept for it: it could not be made to fail.)
    # 7. The evidence writer, driven: with a state dir the log carries one line naming the
    #    shadower's first line, and install.sh status reads it back. A hostile
    #    TERM_PROGRAM with a newline and tabs must not forge a second row.
    hostile = "cmux\n2099-01-01T00:00:00Z\tcodex\tx\tFORGED"
    out, log, home = run(shadower(), state=True, env_extra={"TERM_PROGRAM": hostile})
    expect_ours("state dir present", out)
    lines = (log or "").splitlines()
    if len(lines) != 1 or lines[0].count("\t") != 3 or lines[0].split("\t")[1] != "claude" \
            or not lines[0].split("\t")[3].startswith("print SHADOW-RAN"):
        mark_fail(f"shell reassert: shadow log is not one four-field claude line naming the shadower: {lines!r}")
    status = invoke(["bash", str(repo / "install.sh"), "status"], env={**os.environ, "HOME": str(home)})
    if "shadowing observed 1 time(s)" not in status.stdout or "shadowed by: print SHADOW-RAN" not in status.stdout \
            or "FORGED" in status.stdout.split("shadowed by:")[0]:
        mark_fail(f"shell reassert: install.sh status did not read the shadow log back: {status.stdout.strip()[-300:]!r}")
    #    A shell function named `date` must not write the timestamp field.
    out, log, _ = run(shadower(), state=True,
                      zshrc_extra="date() { print -r -- $'2000-01-01T00:00:00Z\\tcodex\\tx\\tFORGED\\n2001-01-01T00:00:00Z'; }")
    expect_ours("date function present", out)
    lines = (log or "").splitlines()
    if len(lines) != 1 or "FORGED" in (log or "") or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\t", lines[0] if lines else ""):
        mark_fail(f"shell reassert [date function]: the timestamp field was forged or malformed: {lines!r}")
    # 8. Every-prompt shadower: repaired on every command, logged once (the line is a
    #    first observation, not a repair count — what status says it is).
    out, log, _ = run(shadower(every=True), state=True, commands=[f"claude a-{nonce}", f"claude probe-{nonce}"])
    if f"AGENT_LAUNCH_DIRECT host=claude args=a-{nonce}" not in out or ours not in out or "SHADOW-RAN" in out:
        mark_fail(f"shell reassert [every-prompt shadower]: {out.strip()[:160]!r}")
    if len((log or "").splitlines()) != 1:
        mark_fail(f"shell reassert [every-prompt shadower]: expected exactly one log line, got {(log or '').splitlines()!r}")
    # 8b. An alias named `builtin` that exists when the file is sourced must not be baked
    #     into `_agent_launch_direct` — the real direct path, with a fake `claude` in PATH.
    out, _, _ = run(shadower(), zshenv_before="alias builtin='print BUILTIN-ALIAS'", real_direct=True)
    if f"REAL-CLAUDE --dangerously-skip-permissions probe-{nonce}" not in out or "BUILTIN-ALIAS" in out or "SHADOW-RAN" in out:
        mark_fail(f"shell reassert [alias builtin before source]: the direct path did not reach the binary: {out.strip()[:200]!r}")
    # 8c. A hook registered AFTER ours in preexec wins for its command (documented, not
    #     fought) — but the shadow is still in place at the next prompt, so it must be
    #     recorded there. ONE command, then EOF: with a second command the next preexec
    #     would record it too, and the case would not distinguish a precmd observer.
    late = ('autoload -Uz add-zsh-hook; _late() { eval "claude() { print LATE-RAN \\$*; }"; }; '
            'add-zsh-hook preexec _late')
    out, log, _ = run("", zshrc_extra=late, state=True, commands=["claude first"])
    lines = (log or "").splitlines()
    if not lines or "LATE-RAN" not in lines[0].split("\t")[3]:
        mark_fail(f"shell reassert [later preexec shadower]: not recorded at the next prompt: {lines!r} / {out.strip()[:120]!r}")
    # 8d. A shell function named `printf` must not be able to report a write that did not happen.
    out, log, _ = run(shadower(), state=True, zshrc_extra="printf() { return 0; }")
    expect_ours("printf function present", out)
    if len((log or "").splitlines()) != 1:
        mark_fail(f"shell reassert [printf function]: the evidence line was not written: {(log or '')!r}")
    # 8e. Terminal-control bytes in a foreign body must not reach the log or the status line.
    #     The body carries a RAW escape byte (a quoted $'\\e' would stay literal text in
    #     `$functions` and never test anything).
    out, log, home = run(shadower(body="print \x1b[2JSHADOW-RAN \\$*"), state=True)
    expect_ours("ESC in foreign body", out)
    status = invoke(["bash", str(repo / "install.sh"), "status"], env={**os.environ, "HOME": str(home)})
    if "\x1b" in (log or "") or "\x1b" in status.stdout:
        mark_fail("shell reassert [ESC in foreign body]: a control byte reached the log or the status line")
    # 8f. The TTY branch — the only path the live defect is about — needs a PTY: bare
    #     `claude` on a terminal must reach the launcher, not the direct path, under the
    #     precmd shadower. AGENT_LAUNCH_BIN points at a stub that prints and exits.
    tmp = pathlib.Path(tempfile.mkdtemp())
    home = tmp / "home"; zdot = tmp / "zdot"; home.mkdir(); zdot.mkdir()
    stub = tmp / "agent-launch"
    stub.write_text('#!/bin/sh\nprintf "LAUNCHER-RAN %s\\n" "$1"\n')
    stub.chmod(0o755)
    (zdot / ".zshenv").write_text(f'source "{script}"\n{shadower()}\n')
    (zdot / ".zshrc").write_text("PS1='%% '\n")
    env = {**os.environ, "HOME": str(home), "ZDOTDIR": str(zdot), "AGENT_LAUNCH_BIN": str(stub), "TERM": "dumb"}
    master, slave = os.openpty()
    proc = subprocess.Popen(["zsh", "-il"], stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)
    os.write(master, b"claude\rexit\r")
    collected = b""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            collected += chunk
        elif proc.poll() is not None:
            break
    if proc.poll() is None:
        proc.kill()
    os.close(master)
    text = collected.decode("utf-8", "replace")
    if "LAUNCHER-RAN claude" not in text or "SHADOW-RAN" in text:
        mark_fail(f"shell reassert [PTY bare claude]: the launcher was not reached on a terminal: {text.strip()[-200:]!r}")
    # 9. An unwritable state dir must not block the repair, and status must say the
    #    evidence cannot be recorded rather than "no shadowing observed". Root ignores
    #    mode bits, so the assertion is skipped there rather than passed vacuously.
    if os.geteuid() == 0:
        print("NOTE: launcher_shell_reassert skipped the unwritable-state-dir case (root ignores mode bits) — "
              "that assertion is UNVERIFIED in this run, not passed")
    else:
        out, log, home = run(shadower(), state=True, state_mode=0o500)
        expect_ours("unwritable state dir", out)
        if log is not None:
            mark_fail("shell reassert [unwritable state dir]: a log line was written anyway")
        (home / ".local" / "share" / "agent-bios").chmod(0o500)
        status = invoke(["bash", str(repo / "install.sh"), "status"], env={**os.environ, "HOME": str(home)})
        (home / ".local" / "share" / "agent-bios").chmod(0o700)
        if "evidence log not writable" not in status.stdout:
            mark_fail("shell reassert [unwritable state dir]: status did not disclose the unwritable evidence dir")
        if "no shadowing observed" in status.stdout:
            mark_fail("shell reassert [unwritable state dir]: status printed 'no shadowing observed' beside the unwritable warning — a contradictory clean signal")
        # …and a writable dir holding a read-only (empty) log: the append fails just as
        # silently, and status must say so rather than "no shadowing observed".
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / "home"; zdot = tmp / "zdot"; home.mkdir(); zdot.mkdir()
        state_dir = home / ".local" / "share" / "agent-bios"; state_dir.mkdir(parents=True)
        (state_dir / "shell-shadow.log").write_text(""); (state_dir / "shell-shadow.log").chmod(0o400)
        (zdot / ".zshenv").write_text(f'source "{script}"\n{shadower()}\n')
        (zdot / ".zshrc").write_text(f"{direct}\n")
        env = {**os.environ, "HOME": str(home), "ZDOTDIR": str(zdot)}
        out = invoke(["zsh", "-il"], input_text=f"claude probe-{nonce}\n", env=env).stdout
        expect_ours("read-only log file", out)
        status = invoke(["bash", str(repo / "install.sh"), "status"], env={**os.environ, "HOME": str(home)})
        (state_dir / "shell-shadow.log").chmod(0o600)
        if "evidence log not writable" not in status.stdout or "no shadowing observed" in status.stdout:
            mark_fail("shell reassert [read-only log file]: status did not disclose the unwritable log")
    # 9b. The log symlinked to /dev/null (an attacker-controlled HOME): the append "succeeds"
    #     and keeps nothing. The writer must refuse a non-regular file and status must say so.
    tmp = pathlib.Path(tempfile.mkdtemp())
    home = tmp / "home"; zdot = tmp / "zdot"; home.mkdir(); zdot.mkdir()
    state_dir = home / ".local" / "share" / "agent-bios"; state_dir.mkdir(parents=True)
    (state_dir / "shell-shadow.log").symlink_to("/dev/null")
    (zdot / ".zshenv").write_text(f'source "{script}"\n{shadower()}\n')
    (zdot / ".zshrc").write_text(f"{direct}\n")
    env = {**os.environ, "HOME": str(home), "ZDOTDIR": str(zdot)}
    out = invoke(["zsh", "-il"], input_text=f"claude probe-{nonce}\n", env=env).stdout
    expect_ours("log symlinked to /dev/null", out)
    status = invoke(["bash", str(repo / "install.sh"), "status"], env={**os.environ, "HOME": str(home)})
    if "not a regular file" not in status.stdout or "no shadowing observed" in status.stdout:
        mark_fail("shell reassert [log symlinked to /dev/null]: status did not disclose the non-regular evidence file")
    # 10. NEGATIVE CONTROL — with the preexec hook removed the shadower must win, or this
    #     gate cannot distinguish (the earlier diagnosis's `zsh -ilc` false PASS is the precedent).
    control, _, _ = run(shadower(), zshrc_extra="add-zsh-hook -d preexec _agent_launch_reassert")
    if f"SHADOW-RAN probe-{nonce}" not in control:
        mark_fail(f"reassert gate cannot distinguish: with the preexec hook removed the shadower still lost ({control.strip()[:160]!r})")


@launcher_check
def launcher_contract_language_invariance(fx):
    """UI language must never reach a rendered launch contract.

    Headless runs load no catalogs at all, so the goldens hold this by
    construction — what they cannot catch is a `t()` call added to a contract
    renderer, which would ship raw keys the moment the construction changed.
    Decidable at the source level: none of the contract-rendering functions may
    source text from the catalog. The scanner carries its own probe control."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    pattern = r'\bt\(\s*"'
    if not re.search(pattern, 'x = t("probe")'):
        mark_fail("contract-invariance scanner cannot see a t() call — vacuous")
        return
    subjects = (
        "run_contract", "render_review_report", "render_review_method",
        "_same_review_route", "_cross_review_route", "review_plan_v1",
    )
    scanned = 0
    for name in subjects:
        fn = getattr(launcher_module, name, None)
        if fn is None:
            mark_fail(f"contract-invariance subject vanished: {name}")
            continue
        scanned += 1
        if re.search(pattern, inspect.getsource(fn)):
            mark_fail(
                f"{name} sources UI text from the catalog; contracts must be "
                "language-invariant"
            )
    if scanned == 0:
        mark_fail("contract-invariance scanned nothing — vacuous")


@launcher_check
def launcher_registration_wizard(fx):
    """F3 round-trip: the guided registration lands an entry the REAL reader loads,
    and every refusal leaves the user's file byte-identical.

    Driven through the numbered path in a sandbox config dir (the wizard derives
    both its trial and its write target from config_path, so nothing here can
    touch the developer's real file). The duplicate-id second run is the negative
    control: the reader's own refusal, file unchanged."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix="gate-wizard-"))
    profile = sandbox / "profiles.toml"
    shutil.copy(launch_profile_path, profile)
    real_input = launcher_module.read_input
    # Every run below drives _trial_registration, and every trial owns a scratch
    # directory. Snapshot the temp area FIRST: the set comparison at the end is
    # what catches a trial that stops cleaning up after itself.
    temp_area = pathlib.Path(tempfile.gettempdir())
    trial_dirs_before = set(temp_area.glob("agent-launch-register-*"))

    def scripted(script):
        fed = list(script)

        def fake_input(prompt):
            if not fed:
                raise AssertionError(f"wizard asked for unscripted input: {prompt!r}")
            return fed.pop(0)
        return fed, fake_input

    happy = [
        "gate-wiz-lens",  # id
        "",               # label (default)
        "",               # description (default)
        "1",              # drives: an installed tool
        "",               # capability name (default id-kit)
        "/gate/wiz-tool", # command
        "",               # install (default '-': none)
        "",               # operation (default vendor-review)
        "",               # adapter (default exec-stdio-v1)
        "",               # hosts (default both)
        "",               # instructions (default)
        "",               # severity_emits (default ladder -> identity map, no asks)
        "",               # confirm: write
        "",               # done info screen: back
    ]
    try:
        config = launcher_module.load_config(profile)
        registry = launcher_module.load_review_methods(config)
        fed, launcher_module.read_input = scripted(happy)
        with contextlib.redirect_stdout(io.StringIO()):
            landed = launcher_module.register_reviewer_wizard(None, profile, config, registry)
        if not landed:
            mark_fail("registration wizard did not land a valid candidate")
            return
        if fed:
            mark_fail(f"registration wizard left {len(fed)} scripted input(s) unused")
        target = launcher_module.user_methods_path(profile)
        if not target.is_file() or "[review_methods.gate-wiz-lens]" not in target.read_text():
            mark_fail("the wizard reported success but the entry is not in the user file")
            return
        fresh = launcher_module.load_config(profile)
        fresh_registry = launcher_module.load_review_methods(fresh)
        if "gate-wiz-lens" not in fresh_registry:
            mark_fail("a wizard-landed entry does not load through the real reader")
            return
        if "gate-wiz-lens" not in registry:
            mark_fail("the wizard did not refresh the live registry in place")
        binding = launcher_module.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, fresh, "gate.wizard"
        )
        mechanism = launcher_module.derive_review_mechanism(
            fresh_registry["gate-wiz-lens"], binding, fresh
        )
        if mechanism.command != "/gate/wiz-tool":
            mark_fail(
                f"a wizard-landed method resolves to {mechanism.command!r}, not its "
                "own registered command"
            )
        # Negative control: the same id again. Within one user file that is a
        # duplicate TOML table — the reader's own refusal — and the file must
        # come out byte-identical. The scripted tail backs out of the refusal.
        before = target.read_bytes()
        duplicate = [*happy[:13]]
        fed, launcher_module.read_input = scripted(duplicate)
        duplicate_screen = io.StringIO()
        try:
            with contextlib.redirect_stdout(duplicate_screen):
                landed_again = launcher_module.register_reviewer_wizard(
                    None, profile, config, registry
                )
        except (AssertionError, launcher_module.BackRequested,
                launcher_module.LaunchError):
            landed_again = False
        if landed_again:
            mark_fail("the wizard landed a DUPLICATE method id; the reader should refuse")
        if target.read_bytes() != before:
            mark_fail("a refused registration modified the user's methods file")
        # The refusal must come from the TRIAL ORACLE, before any write. The
        # post-write restore also keeps the file byte-identical, so the byte
        # check alone cannot tell a running oracle from a bypassed one — the
        # refusal screen's header can: only the pre-write refusal renders it.
        if launcher_module.t("wizard.refused.header") not in duplicate_screen.getvalue():
            mark_fail(
                "the duplicate never reached the reader's refusal screen — the "
                "trial oracle did not run before the write"
            )
        # SECOND-reader control (writable-scratch round, #5): a candidate that
        # parses clean through load_config and is refused only by
        # load_review_methods. The duplicate above is rejected by TOML parsing,
        # so deleting the `load_review_methods(trial_config)` call left this
        # gate green while the trial stopped running the reader that decides.
        before = target.read_bytes()
        badslot = [
            "gate-wiz-badslot",       # id
            "",                       # label (default)
            "",                       # description (default)
            "2",                      # drives: a review panel
            "",                       # perspectives (default)
            "",                       # trials (default)
            "review {not_a_slot}",    # instructions: load_config-clean, reader-refused
            "",                       # severity_emits (default ladder)
            "b",                      # refusal screen: back out, answers retained
        ]
        fed, launcher_module.read_input = scripted(badslot)
        badslot_screen = io.StringIO()
        try:
            with contextlib.redirect_stdout(badslot_screen):
                landed_badslot = launcher_module.register_reviewer_wizard(
                    None, profile, config, registry
                )
        except (AssertionError, launcher_module.BackRequested,
                launcher_module.LaunchError):
            landed_badslot = False
        if landed_badslot:
            mark_fail("the wizard landed an instructions slot the runtime reader refuses")
        if fed:
            mark_fail(f"the bad-slot run left {len(fed)} scripted input(s) unused")
        if "unknown slot {not_a_slot}" not in badslot_screen.getvalue():
            mark_fail(
                "the reader-specific refusal (unknown slot) never rendered — the "
                "trial ran only the first reader, not load_review_methods"
            )
        if target.read_bytes() != before:
            mark_fail("a reader-refused registration modified the user's methods file")
        # Publication-failure control (writable-scratch round, #6): a directory at
        # the target makes the atomic replace fail AFTER the trial passed. The
        # wizard must refuse like any other refusal — no raw OSError, no
        # completed temporary left beside the target.
        pubfail_sandbox = pathlib.Path(tempfile.mkdtemp(prefix="gate-wizard-pubfail-"))
        pubfail_profile = pubfail_sandbox / "profiles.toml"
        shutil.copy(launch_profile_path, pubfail_profile)
        pubfail_target = launcher_module.user_methods_path(pubfail_profile)
        pubfail_target.mkdir()
        pubfail = [
            "gate-wiz-pubfail", "", "",  # id, label, description
            "1",                          # drives: an installed tool
            "", "/gate/wiz-fail-tool",    # capability name, command
            "", "", "", "",               # install, operation, adapter, hosts
            "", "",                       # instructions, severity_emits
            "",                           # confirm: write (the publish then fails)
            "b",                          # refusal screen: back out
        ]
        pubfail_config = launcher_module.load_config(pubfail_profile)
        pubfail_registry = launcher_module.load_review_methods(pubfail_config)
        fed, launcher_module.read_input = scripted(pubfail)
        pubfail_screen = io.StringIO()
        landed_pubfail = False
        try:
            with contextlib.redirect_stdout(pubfail_screen):
                landed_pubfail = launcher_module.register_reviewer_wizard(
                    None, pubfail_profile, pubfail_config, pubfail_registry
                )
        except (AssertionError, launcher_module.BackRequested,
                launcher_module.LaunchError):
            landed_pubfail = False
        except OSError as exc:
            mark_fail(
                f"a publication failure escaped the wizard as a raw {type(exc).__name__} "
                "instead of a refusal"
            )
        if landed_pubfail:
            mark_fail("the wizard reported success over a publication that failed")
        if "cannot write" not in pubfail_screen.getvalue():
            mark_fail(
                "a failed publication did not render the refusal screen with the "
                "writer's own message"
            )
        leftovers = sorted(
            path.name for path in pubfail_sandbox.glob(".review-methods.local.toml.*")
        )
        if leftovers:
            mark_fail(
                f"a failed publication left its temporary behind: {leftovers}"
            )
        if not pubfail_target.is_dir():
            mark_fail("the publication-failure fixture lost its directory target")
        # Trial-workspace lifecycle (writable-scratch round, #7): every wizard run
        # above ran at least one real trial, and each trial's scratch directory
        # must be gone by the time it answers.
        leaked = sorted(
            path.name for path in
            set(temp_area.glob("agent-launch-register-*")) - trial_dirs_before
        )
        if leaked:
            mark_fail(
                f"registration trials leaked their scratch director(ies): {leaked}"
            )
    finally:
        launcher_module.read_input = real_input


@launcher_check
def launcher_chrome_speaks_the_selected_language(fx):
    """The launcher's own words — panel titles, key line, input prompts — render in the
    selected language, and the key line keeps the two properties other checks rest on.

    The chrome used to be English literals inside the screen while every option and panel
    around it was translated, so a Korean session read its own interface in two
    languages. Held here rather than by eye because the strings are now spread across
    three catalogs.

    Three properties, each with a control:
      * TRANSLATED — a language whose chrome equals English is not translated, and the
        assertion is per string, because one forgotten entry is exactly what this leg is
        for.
      * DISCRIMINATING — the with-back and without-back forms must not be substrings of
        each other in ANY language; `tui_picker` uses them to tell which screen is drawn.
      * FITS — every form must fit the 100-column terminal the picker scenarios run in
        (less the footer's own padding), because a wrapped footer puts a newline through
        the middle of a marker and the scenario waits out its deadline instead.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    # The picker's terminal is 100 columns and the footer carries `padding: 0 1`.
    WIDTH = 98
    forms = ((False, False), (True, False), (True, True))
    languages = launcher_module.I18N_LANGUAGES
    if not languages or "en" not in languages:
        mark_fail("no language set to judge — this leg would assert nothing")
        return
    # A plan with an inactive tier, so the panel renders BOTH column forms: the ASCII
    # tier rows and the translated Inactive label beside them.
    setup_plan = {
        "host": "codex", "label": "Balanced", "main_tier": "workhorse",
        "review_setup": "none", "delegation": False,
        "codex_execution_policy": "bypass", "claude_permission_mode": "auto",
        "frontier_effort": "ultra",
        "tiers": {tier: {"model": f"m-{tier}", "effort": "high"}
                  for tier in ("frontier", "helm", "workhorse", "sweep")},
    }
    real_catalog = launcher_module._CATALOG
    rendered = {}
    try:
        for language in languages:
            catalog = launcher_module._module_catalog(language)
            if not catalog:
                mark_fail(f"no UI catalog for {language} beside the launcher")
                continue
            launcher_module._CATALOG = catalog
            rendered[language] = {
                "footers": [launcher_module.menu_footer(*form) for form in forms],
                "chrome": {key: launcher_module.t(key) for key in (
                    "tui.setup.title", "tui.corpus.title", "tui.detail.title",
                    "tui.input.new", "tui.input.placeholder", "tui.input.footer",
                    "setup.none", "setup.main", "setup.delegation",
                    "setup.inactive.label",
                )},
                "setup": launcher_module.setup_summary_lines(setup_plan),
            }
    finally:
        launcher_module._CATALOG = real_catalog
    if set(rendered) != set(languages):
        mark_fail(f"chrome rendered for {sorted(rendered)}, not {sorted(languages)}")
        return

    english = rendered["en"]
    for language, shown in rendered.items():
        for index, footer in enumerate(shown["footers"]):
            width = launcher_module.display_width(footer)
            if width > WIDTH:
                mark_fail(
                    f"the {language} key line for form {forms[index]} is {width} cells "
                    f"and the terminal is {WIDTH}; it wraps, and a wrapped footer breaks "
                    "the markers the picker scenarios wait on"
                )
        without_back, with_back = shown["footers"][0], shown["footers"][1]
        if without_back in with_back or with_back in without_back:
            mark_fail(
                f"the {language} key lines are not mutually exclusive: "
                f"{without_back!r} vs {with_back!r}"
            )
        if language == "en":
            continue
        # A key NAME is not translated — you press Enter, not 입력 — so equality with
        # English is judged on the whole string, which carries the verb.
        same = [key for key, value in shown["chrome"].items()
                if value == english["chrome"][key]]
        if same:
            mark_fail(
                f"{language} renders the launcher's own chrome in English: {sorted(same)}"
            )
        if shown["footers"] == english["footers"]:
            mark_fail(f"the {language} key line is English text")

    # The setup panel's label column is padded in CELLS, not characters: a CJK label
    # padded as characters is drawn twice as wide and moves the value column for its row
    # alone. Asserted by rendering, because the padding lives in the renderer.
    for language, shown in rendered.items():
        starts = set()
        for line in shown["setup"]:
            head, _, tail = line.partition(" ")
            if not tail.startswith(" "):
                continue  # a prose row, not a two-column one
            starts.add(launcher_module.display_width(line) - launcher_module.display_width(tail.lstrip()))
        if len(starts) > 1:
            mark_fail(
                f"the {language} setup panel does not align its value column "
                f"(starts at {sorted(starts)}): {shown['setup']!r}"
            )
        # And a value must survive untranslated — the words a user has to find again in
        # a config file or a CLI flag. Checked on the ROW that carries the value, never
        # against the whole panel: the first version of this searched the joined body and
        # passed a planted translation of `off`, because `inactive_tier_reason` renders
        # "delegation is off" two rows below and satisfied the search on its own.
        rows = shown["setup"]
        if len(rows) != len(english["setup"]):
            mark_fail(f"the {language} setup panel has {len(rows)} rows against English's "
                      f"{len(english['setup'])}; the row-scoped checks below would drift")
            continue
        for index, value in ((0, "codex"), (1, "WORKHORSE"), (2, " off"),
                             (3, "m-workhorse")):
            if value not in rows[index]:
                mark_fail(
                    f"the {language} setup panel lost the value {value!r} from its row: "
                    f"{rows[index]!r}"
                )

    # Control: the leg must notice a chrome string left untranslated. Planted in the
    # catalog the renderer reads, so a leg that quietly used English throughout — the
    # exact bug it is checking for — cannot pass this.
    planted = launcher_module._module_catalog("ko")
    planted["tui.detail.title"] = english["chrome"]["tui.detail.title"]
    launcher_module._CATALOG = planted
    try:
        untranslated = launcher_module.t("tui.detail.title") == english["chrome"]["tui.detail.title"]
    finally:
        launcher_module._CATALOG = real_catalog
    if not untranslated:
        mark_fail(
            "the untranslated-chrome control could not plant its case, so a clean "
            "verdict above is about nothing"
        )


@launcher_check
def launcher_corpus_sizes(fx):
    """Every package row says what that package is and what it costs, and the panel of
    an install with no author-side registry reports the corpus instead of saying
    "unavailable" three times.

    Driven against a fixture PACKAGE — its own manifest, monolith and guides — because
    the figures are derived by running that package's assembler, and a fixture that only
    supplied numbers would be checking arithmetic this module does not do.

    Four negative controls: a package without a manifest must degrade to bare names
    rather than raise; a manifest the assembler refuses must do the same; a projection
    naming a package the install does not carry must say so; and the per-row
    descriptions must DIFFER, which is the defect the sizing was added for — one shared
    sentence under five names is a list, not a choice.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    root = pathlib.Path(tempfile.mkdtemp())
    repo_root = pathlib.Path(__file__).resolve().parents[1]

    def build_package(name: str, manifest: dict, monolith: str) -> pathlib.Path:
        repo = root / name
        (repo / "compose").mkdir(parents=True)
        (repo / "claude" / "guides").mkdir(parents=True)
        (repo / "compose" / "domains.json").write_text(json.dumps(manifest))
        (repo / "claude" / "CLAUDE.md").write_text(monolith)
        shutil.copy(repo_root / "compose" / "assemble.py", repo / "compose" / "assemble.py")
        for guide, size in (("wide.md", 4096), ("narrow.md", 1024)):
            (repo / "claude" / "guides" / guide).write_text("g" * size)
        return repo

    manifest = {
        "domains": {"alpha": "Alpha: the wide one", "beta": "Beta: the narrow one"},
        "tiers": ["core", "domain", "env-personal", "infra"],
        "bullets": [
            {"anchor": "core rule", "tier": "core", "domains": []},
            {"anchor": "alpha rule one", "tier": "domain", "domains": ["alpha"]},
            {"anchor": "alpha rule two", "tier": "domain", "domains": ["alpha"]},
            {"anchor": "beta rule", "tier": "domain", "domains": ["beta"]},
        ],
        "guides": {
            "wide.md": {"tier": "domain", "domains": ["alpha"]},
            "narrow.md": {"tier": "domain", "domains": ["beta"]},
        },
        "hooks": {}, "agents": {}, "skills": {},
    }
    # Two sections, and the second holds a rule from BOTH packages. A one-section
    # monolith cannot tell the total apart from the sum of the parts, because the
    # header both deltas carry is the thing being double-counted.
    monolith = (
        "# CLAUDE.md\n\n## One\n\n- core rule\n- alpha rule one\n"
        "\n## Two\n\n- alpha rule two\n- beta rule\n"
    )
    repo = build_package("package", manifest, monolith)

    def facts_for(repo_path, applied):
        return launcher_module.corpus_facts({
            "repo": str(repo_path),
            "domains": {"available": ["alpha", "beta"], "applied": applied},
            "versions": None,
        })

    facts = facts_for(repo, ["alpha", "beta"])
    if facts is None:
        mark_fail("the launcher cannot size a well-formed package — every claim below "
                  "would then pass over a None")
        return
    alpha, beta = facts["domains"]["alpha"], facts["domains"]["beta"]
    if not (alpha["rules"] == 2 and beta["rules"] == 1):
        mark_fail(f"per-package rule counts wrong: alpha={alpha['rules']} beta={beta['rules']}; want 2 and 1")
    if not (alpha["guide_chars"] == 4096 and beta["guide_chars"] == 1024):
        mark_fail(f"per-package guide sizes wrong: {alpha['guide_chars']} / {beta['guide_chars']};"
                  " want 4096 and 1024")
    if alpha["chars"] <= beta["chars"]:
        mark_fail("the wider package does not measure wider — the sizes carry no information")
    # The selection total is assembled outright rather than summed: the sum double-counts
    # the section header both packages need.
    if facts["selected"]["chars"] >= alpha["chars"] + beta["chars"] + facts["base"]["chars"]:
        mark_fail("the applied total equals the sum of the parts, so shared lines are "
                  "counted twice")
    if facts["selected"]["rules"] != 4:
        mark_fail(f"the applied total holds {facts['selected']['rules']} rules; want 4")

    # Each row's description is its own, and carries the package's own words.
    described = [launcher_module._domain_description(facts["domains"][name])
                 for name in ("alpha", "beta")]
    if described[0] == described[1]:
        mark_fail("both packages describe themselves identically — the row says nothing "
                  "that would help choose between them")
    if "Alpha: the wide one" not in described[0] or "Beta: the narrow one" not in described[1]:
        mark_fail(f"a package description does not reach its row: {described!r}")

    # The panel of an install with no author-side registry.
    status = {
        "repo": str(repo), "versions": None, "summary": None,
        "domains": {"available": ["alpha", "beta"], "applied": ["alpha", "beta"]},
        "last_apply": None,
    }
    lines = launcher_module.corpus_summary_lines(status)
    body = "\n".join(lines)
    if launcher_module.t("panel.unavailable") in body:
        mark_fail(f"a packaged install still reports the corpus as unknowable: {lines!r}")
    if "4" not in body or "alpha" not in body:
        mark_fail(f"the packaged panel names neither the rule count nor the packages: {lines!r}")
    # A failed apply stays loud on the packaged panel too — it is a different branch.
    failed = {**status, "last_apply": {
        "requested": ["alpha"], "outcome": "canary_failed",
        "at": "2026-09-03T00:00:00", "error_tail": None,
    }}
    if not any("canary_failed" in line for line in launcher_module.corpus_summary_lines(failed)):
        mark_fail("the packaged panel drops a failed apply")

    # Control 0: the assembler that ran is the PACKAGE's own, not whichever module the
    # process already has under that name. Proven behaviourally — a second package whose
    # assembler emits an extra line per bundle must measure larger for the same manifest.
    loud = build_package("loud", manifest, monolith)
    loud_asm = loud / "compose" / "assemble.py"
    loud_asm.write_text(loud_asm.read_text().replace(
        '    text = "\\n".join(out) + "\\n"',
        '    text = "\\n".join(out) + "\\n" + "M" * 500 + "\\n"', 1))
    louder = facts_for(loud, ["alpha", "beta"])
    if louder is None or louder["selected"]["chars"] <= facts["selected"]["chars"]:
        mark_fail(
            "a package carrying a different assembler measured the same as the first — "
            "the launcher is not running the assembler it was pointed at"
        )

    # Control 1: no manifest at all.
    bare = root / "bare"
    bare.mkdir()
    if facts_for(bare, ["alpha"]) is not None:
        mark_fail("a package with no manifest still produced sizes")
    if launcher_module._domain_description(None) != launcher_module.t("corpus.toggle.description"):
        mark_fail("an unsized package does not fall back to the plain toggle description")

    # Control 2: a manifest the assembler refuses (a bullet no anchor matches). The
    # assembler exits rather than raising, which is not an Exception and would leave the
    # launcher through every absorber in the file.
    broken = build_package("broken", manifest, "# CLAUDE.md\n\n## Section\n\n- unmatched\n")
    if facts_for(broken, ["alpha"]) is not None:
        mark_fail("a monolith the assembler refuses still produced sizes")

    # Control 3: the projection names a package this install does not carry.
    stray = facts_for(repo, ["alpha", "ghost"])
    if stray is None or stray["selected"]["unknown"] != ["ghost"]:
        mark_fail(f"an applied package the install lacks is not surfaced: {stray!r}")
    stray_lines = launcher_module.corpus_summary_lines({
        **status, "domains": {"available": ["alpha"], "applied": ["alpha", "ghost"]},
    })
    if not any("ghost" in line for line in stray_lines):
        mark_fail(f"the panel hides an applied package the install lacks: {stray_lines!r}")

    # Control 4: an install that has never applied is not sized at all — what is
    # deployed is whatever the install put there, and the manifest cannot say which.
    unset = launcher_module.corpus_summary_lines({
        **status, "domains": {"available": ["alpha", "beta"], "applied": None},
    })
    if not any(launcher_module.t("panel.domains.unset") in line for line in unset):
        mark_fail(f"a never-applied projection is sized as if it were: {unset!r}")

    shutil.rmtree(root, ignore_errors=True)


@launcher_check
def launcher_corpus_checklist(fx):
    """The corpus checklist hands the installer EXACTLY the checked set, and only
    on a real change; the panel is loud about a failed apply and silent about a
    clean one.

    Driven through the numbered path (the shared controller both renderers call)
    with the status projection fixtured via AGENT_BIOS_CORPUS_STATUS, the
    installer resolution and dispatch monkeypatched to record argv. Negative
    controls: an unchanged set must dispatch nothing, and the applied-fixture
    panel must carry no failure marker."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    status = {
        "repo": str(tmp),
        "current_version": "v", "latest_version": "v", "rolled_back_to": None,
        "versions": [], "summary": {},
        "domains": {"available": ["alpha", "beta", "gamma"], "applied": ["alpha"]},
        "last_apply": None,
    }
    status_path = tmp / "status.json"
    status_path.write_text(json.dumps(status))
    recorded = []
    real_run, real_which = subprocess.run, shutil.which
    real_status_path = launcher_module.CORPUS_STATUS_PATH
    real_input = launcher_module.read_input
    real_legacy = os.environ.pop("AGENT_BIOS_LEGACY_INSTALL", None)

    def scripted(script):
        fed = list(script)

        def fake_input(prompt):
            if not fed:
                raise AssertionError(f"corpus checklist asked for unscripted input: {prompt!r}")
            return fed.pop(0)
        return fed, fake_input

    try:
        # The status path is resolved at import (env-pinned for subprocesses);
        # an in-process leg patches the resolved constant instead.
        launcher_module.CORPUS_STATUS_PATH = status_path
        subprocess.run = lambda argv, **kw: (
            recorded.append(list(argv)) or types.SimpleNamespace(returncode=0)
        )
        shutil.which = lambda name: (
            "/gate/agent-bios" if name == "agent-bios" else real_which(name)
        )
        # Toggle beta on (option 2), apply (option 4).
        fed, launcher_module.read_input = scripted(["2", "4"])
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.corpus_checklist(None)
        if fed:
            mark_fail(f"corpus checklist left {len(fed)} scripted input(s) unused")
        if recorded != [["/gate/agent-bios", "onboard", "--non-interactive", "--domains", "alpha,beta"]]:
            mark_fail(
                f"corpus checklist dispatched {recorded!r}; want exactly "
                "[['/gate/agent-bios', 'onboard', '--non-interactive', '--domains', 'alpha,beta']]"
            )
        # Negative control: toggling back to the applied set leaves Apply disabled
        # and dispatches nothing — the prompt loops, so back out instead.
        recorded.clear()
        fed, launcher_module.read_input = scripted(["2", "2", "b"])
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.corpus_checklist(None)
        if recorded:
            mark_fail(f"an unchanged corpus selection still dispatched: {recorded!r}")
        # Emptying the selection must say so explicitly, not send an empty argv.
        recorded.clear()
        fed, launcher_module.read_input = scripted(["1", "4"])
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.corpus_checklist(None)
        if recorded != [["/gate/agent-bios", "onboard", "--non-interactive", "--domains", "none"]]:
            mark_fail(
                f"emptying the selection dispatched {recorded!r}; want --domains none"
            )
        # applied:null is "never selected", not "core+infra verified": the very
        # first apply — even with nothing toggled — IS a change and must be
        # offered. Collapsing null into the empty set locked first-time users
        # out of a core+infra-only apply.
        status_path.write_text(json.dumps({**status, "domains": {
            "available": ["alpha", "beta", "gamma"], "applied": None,
        }}))
        recorded.clear()
        fed, launcher_module.read_input = scripted([""])
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.corpus_checklist(None)
        if recorded != [["/gate/agent-bios", "onboard", "--non-interactive", "--domains", "none"]]:
            mark_fail(
                f"a never-applied projection dispatched {recorded!r}; the first "
                "apply must be offered and say --domains none"
            )
        recorded.clear()
        (tmp / "install.sh").write_text("#!/bin/sh\n")
        shutil.which = lambda name: None if name == "agent-bios" else real_which(name)
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.run_corpus_apply(["beta"])
        if recorded != [["bash", str(tmp / "install.sh"), "onboard", "--non-interactive", "--domains", "beta"]]:
            mark_fail(f"checkout corpus apply omitted explicit machine mode: {recorded!r}")
        recorded.clear()
        shutil.which = lambda name: "/gate/agent-bios" if name == "agent-bios" else real_which(name)
        os.environ["AGENT_BIOS_LEGACY_INSTALL"] = "1"
        with contextlib.redirect_stdout(io.StringIO()):
            launcher_module.run_corpus_apply(["alpha"])
        if recorded != [["/gate/agent-bios", "onboard", "--domains", "alpha"]]:
            mark_fail(f"compatibility corpus apply received private interaction flags: {recorded!r}")
    finally:
        subprocess.run, shutil.which = real_run, real_which
        launcher_module.read_input = real_input
        launcher_module.CORPUS_STATUS_PATH = real_status_path
        if real_legacy is None:
            os.environ.pop("AGENT_BIOS_LEGACY_INSTALL", None)
        else:
            os.environ["AGENT_BIOS_LEGACY_INSTALL"] = real_legacy

    # The panel: a failed apply is loud, a clean one is silent — asserted on the
    # rendered lines, not on the JSON.
    failed = {**status, "last_apply": {
        "requested": ["alpha"], "outcome": "canary_failed",
        "at": "2026-08-10T00:00:00", "error_tail": None,
    }}
    lines = launcher_module.corpus_summary_lines(failed)
    if not any("LAST APPLY canary_failed" in line for line in lines):
        mark_fail(f"a failed corpus apply is invisible on the panel: {lines!r}")
    clean = {**status, "last_apply": {
        "requested": ["alpha"], "outcome": "applied",
        "at": "2026-08-10T00:00:00", "error_tail": None,
    }}
    lines = launcher_module.corpus_summary_lines(clean)
    if any("LAST APPLY" in line for line in lines):
        mark_fail(f"a clean corpus apply renders a failure marker: {lines!r}")
    missing = {**status, "domains": None}
    lines = launcher_module.corpus_summary_lines(missing)
    if any("Domains" in line for line in lines):
        mark_fail("a status with no domain projection invented a Domains line")


@launcher_check
def launcher_review_report(fx):
    """Stage 4's control: the independence matrix must yield exact reports.

    Grades are ordinal and only upward — a different-but-lower effort earns no
    credit — and isolation is a gate rather than a rung, so an unattested mechanism
    is excluded instead of graded low."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    try:
        config = launcher_module.load_config(launch_profile_path)
        methods = launcher_module.load_review_methods(
            tomllib.loads(launch_profile_path.read_text())
        )
        bind = lambda raw: launcher_module.parse_review_binding(raw, config, "gate")
        main = bind({"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh"})
    except Exception as exc:
        mark_fail(f"agent-launch review report: setup failed: {exc}")
        return

    def report_for(base_raw, method_bindings=None, cfg=None):
        plan = launcher_module.ReviewPlan(
            True,
            bind(base_raw),
            {name: bind(raw) for name, raw in (method_bindings or {}).items()},
            "composable",
        )
        return launcher_module.resolve_composable_review(plan, main, cfg or config, methods)

    # The matrix. Same main seat throughout; only the reviewer's seat moves.
    matrix = [
        ("provider difference", "OK", "provider_difference",
         {"provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh"}),
        ("model difference", "OK", "model_difference",
         {"provider": "anthropic", "model": "claude-fable-5", "effort": "xhigh"}),
        ("higher effort", "OK", "higher_effort",
         {"provider": "anthropic", "model": "claude-opus-5", "effort": "max"}),
        ("same seat floor", "OK", "perspective_floor",
         {"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh"}),
        # The one that is easy to get wrong: different is not the same as better.
        ("lower effort earns no credit", "OK", "perspective_floor",
         {"provider": "anthropic", "model": "claude-opus-5", "effort": "high"}),
        ("service tier not projectable", "ADVISORY", "perspective_floor",
         {"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh",
          "service_tier": "fast"}),
        # Difference is not capability. A sweep seat differs from the main in provider,
        # model AND effort, and still earns nothing: it cannot do the work. Its contrast
        # is the row below — the floor itself must NOT be capped, or the rule would read
        # as "only helm and above", which is the recommendation, not the requirement.
        ("below the review floor earns no credit", "OK", "perspective_floor",
         {"provider": "openai", "tier": "sweep"}),
        ("the floor itself is not capped", "OK", "provider_difference",
         {"provider": "openai", "tier": "workhorse"}),
    ]
    if not matrix:
        mark_fail("agent-launch review report: empty matrix — the check is vacuous")
    for name, want_status, want_grade, base_raw in matrix:
        try:
            row = report_for(base_raw).base
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch review report: {name} did not resolve: {exc}")
            continue
        if row.status != want_status or row.grade != want_grade:
            mark_fail(
                f"agent-launch graded {name} as {row.status}/{row.grade}, "
                f"want {want_status}/{want_grade}"
            )

    # The capped grade alone reads as a same-seat floor, which is a different fact, so
    # the report must say which one it is. Literals, not the module's constants: an
    # assertion built from the value it checks is true by construction.
    capped = report_for({"provider": "openai", "tier": "sweep"}).base
    if "workhorse" not in capped.detail or "floor" not in capped.detail:
        mark_fail(
            f"agent-launch capped a below-floor reviewer without saying why: {capped.detail!r}"
        )
    # And an unclassifiable seat is not treated as below-floor: a raw model id carries no
    # tier, and penalising it would demote a frontier model this profile happens not to list.
    unclassified = report_for(
        {"provider": "openai", "model": "a-model-no-tier-names", "effort": "high"}
    ).base
    if unclassified.grade != "provider_difference":
        mark_fail(
            f"agent-launch graded an untiered reviewer {unclassified.grade!r}; an unknown "
            f"capability must not be read as a low one"
        )

    # The floor grade carries a condition — isolation plus two or more perspectives — that
    # parse_review_method enforces for `panel` alone. A single-lens method landing on it has
    # claimed the floor without establishing it, and the row must say which one it is.
    same_seat = {"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh"}
    lens = report_for(same_seat, {"ultracode": same_seat})
    single = next((row for row in lens.methods if row.method_id == "ultracode"), None)
    if single is None:
        mark_fail("agent-launch dropped ultracode from a same-seat plan; the lens check is vacuous")
    elif single.grade != "perspective_floor":
        mark_fail(f"agent-launch graded a same-seat method {single.grade!r}, expected the floor")
    elif "perspective" not in single.detail:
        mark_fail(
            f"agent-launch put a one-lens method on the floor without saying the floor's "
            f"condition is unmet: {single.detail!r}"
        )
    # The contrast: the panel declares three, so it must carry no such note.
    if "perspective(s)" in lens.base.detail:
        mark_fail(f"agent-launch flagged the three-lens panel as single-lens: {lens.base.detail!r}")

    # Two notes can be true at once, and assignment used to let the last one win.
    both = report_for({"provider": "openai", "tier": "sweep", "service_tier": "fast"}).base
    if "floor" not in both.detail or "service_tier" not in both.detail:
        mark_fail(f"agent-launch reported only one of two simultaneous notes: {both.detail!r}")

    # A dropped service tier must not reach the reviewer as live prose. The report said
    # `service_tier='fast' is not projectable at launch; dropped` and the `{service_tier}`
    # slot rendered `fast` in the same row's instruction (round 18, #10) — one binding,
    # two values. Rendered through the real resolver with a template that USES the slot,
    # because the shipped templates do not, so the matrix row above cannot see it.
    tiered = launcher_module.parse_review_method(
        "gate-tiered",
        {"label": "Tiered", "description": "Gate fixture: a template that names the tier.",
         "capability": "gate-tier-kit", "operation": "tier-review",
         "instructions": "dispatch {command} with service_tier={service_tier}",
         "output": "review-v1", "perspectives": ["refutation"], "trials": 1,
         "order": "fixed", "swap_augmentation": False, "aggregation": "union",
         "severity_emits": ["high"], "severity_map": {"high": "high"}},
        "gate.tiered",
    )
    with tempfile.TemporaryDirectory() as raw_dir:
        endpoint = pathlib.Path(raw_dir) / "tier-kit"
        endpoint.write_text("#!/usr/bin/env bash\nexit 0\n")
        endpoint.chmod(0o755)
        tier_config = {
            **config,
            "capabilities": {**config.get("capabilities", {}), "gate-tier-kit": {
                "command": str(endpoint),
                "offers": [{"operation": "tier-review", "adapter": "exec-stdio-v1",
                            "hosts": ["claude"]}],
            }},
        }
        for tier, expected in (("fast", "service_tier=disabled"), ("disabled", "service_tier=disabled")):
            row = launcher_module._resolve_one(
                tiered,
                bind({"provider": "anthropic", "model": "claude-opus-5", "effort": "xhigh",
                      "service_tier": tier}),
                main, tier_config,
            )
            if expected not in row.instruction or f"service_tier={tier}" in row.instruction and tier != "disabled":
                mark_fail(
                    f"agent-launch rendered a requested service_tier={tier!r} into the "
                    f"instruction while the report drops it: {row.instruction!r}"
                )
            if tier == "fast" and (row.status != launcher_module.STATUS_ADVISORY
                                   or "dropped" not in row.detail):
                mark_fail(f"agent-launch service-tier subject is not the ADVISORY/dropped row: "
                          f"{row.status} {row.detail!r}")

    # A missing capability drops its own method and says how to install it; it must
    # never be rebound to a seat the author did not choose, and the base carries on.
    # A SYNTHETIC capability, because no shipped one names an install any more: both
    # shipped reviewers are `${backend}` host CLIs, whose absence is a missing host
    # rather than a missing tool.
    absent_toml = launch_profile_path.read_text() + '''
[capabilities.gate-kit]
command = "/nonexistent/gate-kit"
install = "gate fixture; never installed"
offers = [{ operation = "gate-review", adapter = "exec-stdio-v1", hosts = ["codex"] }]

[review_methods.gate-lens]
label = "Gate lens"
description = "Gate fixture: a method whose capability is deliberately absent."
capability = "gate-kit"
operation = "gate-review"
instructions = "run {command} on {model}/{effort}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = { blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }
'''
    absent_raw = tomllib.loads(absent_toml)
    absent_methods = launcher_module.load_review_methods(absent_raw)
    absent = {
        **config,
        "capabilities": {
            **config["capabilities"],
            "gate-kit": absent_raw["capabilities"]["gate-kit"],
        },
    }
    dropped = launcher_module.resolve_composable_review(
        launcher_module.ReviewPlan(
            True,
            bind({"provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh"}),
            {"gate-lens": bind({"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"})},
            "composable",
        ),
        main, absent, absent_methods,
    )
    lens_row = next((row for row in dropped.methods if row.method_id == "gate-lens"), None)
    if lens_row is None or lens_row.status != "DROPPED":
        mark_fail("agent-launch did not drop a method whose capability is absent")
    elif "install" not in lens_row.detail:
        mark_fail(f"agent-launch dropped gate-lens without an install hint: {lens_row.detail}")
    if lens_row is not None and lens_row.status == "DROPPED":
        # A dropped row carries NO SEAT. This is the branch that used to: the mechanism
        # derived, the command did not resolve, and the row went out wearing a live
        # provider, model, effort and mechanism while holding the one status that removes
        # it from the denominator — so a row that ran nothing still looked covered, and the
        # plan parser accepted it back (spec round, #9). Each field named, because a door
        # noticing only all four at once would pass on a row that kept one.
        seated = sorted(
            field for field in ("provider", "model", "effort", "mechanism")
            if getattr(lens_row, field) is not None
        )
        if seated:
            mark_fail(
                f"agent-launch emitted a DROPPED row still carrying {', '.join(seated)} — "
                f"a method that ran nothing sat on no seat, and the verifier matches a "
                f"receipt against exactly those fields"
            )
        # …and the operator does not lose what was attempted: it moves into the detail,
        # where nothing adjudicates it. Without this the fix above is a silent deletion.
        if "would have run on" not in lens_row.detail:
            mark_fail(
                f"agent-launch dropped gate-lens without saying which seat it would have "
                f"used: {lens_row.detail}"
            )
    if dropped.base.status == "DROPPED":
        mark_fail("agent-launch dropped the base panel because an optional method was absent")

    # I2 is a gate, not a rung. Reached only if something hands the resolver a
    # mechanism core does not attest — which the normal path cannot, and the second
    # assertion below is what keeps that true.
    real_derive = launcher_module.derive_review_mechanism
    try:
        launcher_module.derive_review_mechanism = lambda method, binding, cfg: (
            launcher_module.ReviewMechanism(
                method.method_id, "gate-in-main-context", "the designing context", None, binding
            )
        )
        unattested = launcher_module._resolve_one(
            methods["codex-exec"],
            bind({"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"}),
            main,
            config,
        )
    finally:
        launcher_module.derive_review_mechanism = real_derive
    if unattested.status != "DROPPED" or unattested.grade != launcher_module.GRADE_NOT_REVIEW:
        mark_fail(
            f"agent-launch graded an unattested mechanism {unattested.status}/{unattested.grade} "
            "instead of excluding it as NOT_REVIEW"
        )

    # Every adapter a real configuration can derive must be core-attested, which is
    # what makes the in-main-context shape structurally unreachable rather than
    # merely forbidden.
    derivable = {launcher_module.PANEL_ADAPTER}
    for name, capability in config["capabilities"].items():
        for offer in launcher_module.parse_capability_offers(name, capability):
            derivable.add(offer["adapter"])
    if not derivable:
        mark_fail("agent-launch review report: no derivable adapters — the check is vacuous")
    stray = sorted(a for a in derivable if a not in launcher_module.REVIEW_ADAPTERS)
    if stray:
        mark_fail(f"agent-launch can derive adapters core does not attest: {', '.join(stray)}")

    # Launch time reports what it projected and says so; achievement needs receipts.
    # Compared against literals, never against the module's own constants: asserting
    # a value equals the constant it was built from is true by construction and
    # survives redefining the constant. A negative control caught exactly that here.
    summary = report_for({"provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh"})
    if summary.availability != "projected":
        mark_fail(f"agent-launch review report availability is {summary.availability!r}")
    if summary.achieved_grade != "UNKNOWN_UNTIL_RECEIPTS":
        mark_fail(
            f"agent-launch claims achieved_grade={summary.achieved_grade!r} without receipts"
        )
    rendered = launcher_module.render_review_report(summary)
    if "PROPOSED" not in rendered:
        mark_fail("agent-launch review report does not say a receipt-less clean verdict is PROPOSED")


@launcher_check
def launcher_review_contract(fx):
    """The wiring control: a composable preset must reach the LIVE launch path.

    Resolution and the independence report were gated in isolation before this check
    existed, and that is exactly how a composable preset came to project
    `Review setup=None` with no review at all — every consumer still read the legacy
    enum. So this runs the real build_plan → run_contract → project_args chain, and
    its mutations must move what those projections SAY, not merely what the resolver
    returns. It also carries a second unknown-method canary: unlike the resolver-level
    one, this canary has to survive the whole live path.

    Machine-independent on purpose: the capability points at a temp executable, so a
    machine without onto/ultracode installed runs the identical subject."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    canary = "gate-live-" + secrets.token_hex(6)
    base_toml = launch_profile_path.read_text()

    def config_text(endpoint, effort_binding='tier = "frontier"', methods=(None,)):
        blocks = [base_toml, f'''
[capabilities.gate-mcpkit]
command = "{endpoint}"
install = "gate fixture; never installed"
offers = [{{ operation = "structured-review", adapter = "mcp-stdio-v1", hosts = ["codex", "claude"] }}]

[review_methods.{canary}]
label = "Live canary"
description = "A reviewer this repository has never seen, through the whole launch path."
capability = "gate-mcpkit"
operation = "structured-review"
instructions = "invoke {{command}} on {{model}}/{{effort}} over {{perspectives}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[review_methods.{canary}-b]
label = "Live canary, second lens"
description = "A second method on the SAME capability, to prove one server is registered."
capability = "gate-mcpkit"
operation = "structured-review"
instructions = "invoke {{command}} again on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["coverage"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[presets.gate-composable]
label = "gate-composable"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.gate-composable.review]
base = {{ provider = "openai", tier = "frontier" }}
''']
        for method in methods:
            if method is not None:
                blocks.append(
                    f"\n[presets.gate-composable.review.methods.{method}]\n"
                    f'provider = "openai"\n{effort_binding}\n'
                )
        return "".join(blocks)

    def project(text, host):
        directory = pathlib.Path(tempfile.mkdtemp())
        path = directory / "profiles.toml"
        path.write_text(text)
        config = launcher_module.load_config(path)
        plan = launcher_module.build_plan(config, host, "gate-composable")
        return plan, launcher_module.run_contract(plan), launcher_module.project_args(
            plan, materialize_agents=False
        )

    with tempfile.TemporaryDirectory() as raw:
        endpoint = pathlib.Path(raw) / "vendor-mcp"
        endpoint.write_text("#!/usr/bin/env bash\nexit 0\n")
        endpoint.chmod(0o755)
        text = config_text(endpoint, methods=(canary,))
        try:
            plan, contract, argv = project(text, "claude")
        except Exception as exc:
            mark_fail(f"agent-launch review contract: a composable preset did not launch: {exc}")
            return
        report = plan.get("review_report")
        if report is None:
            mark_fail("agent-launch review contract: the plan carries no composable report")
            return
        rows = (report.base, *report.methods)
        # Vacuity guard: an empty subject set would satisfy every assertion below.
        if len(rows) < 2:
            mark_fail(f"agent-launch review contract: only {len(rows)} subject row(s) — vacuous")

        # The regression this check exists for: the contract must not project the
        # legacy enum's absence as if it were a review setting.
        if "Review setup=None" in contract:
            mark_fail("agent-launch projects a composable preset as 'Review setup=None'")
        if "Composable review (availability=" not in contract:
            mark_fail("agent-launch omits the composable review report from the launch contract")
        if canary not in contract:
            mark_fail("agent-launch omits an authored review method from the launch contract")

        # The resolved command must reach the instruction. Rendering the report from
        # slots it could not resolve once emitted an empty {command} into the contract.
        if str(endpoint) not in contract:
            mark_fail("agent-launch rendered a capability method without its resolved command")

        # ReviewPlan/v1: present, parseable, and a real inverse — an untestable
        # round-trip claim would not be a control.
        restored = launcher_module.extract_review_plan_v1(contract)
        # Two decodable records is not a plan. First-wins let a forged record placed ahead
        # of the canonical one be the plan a receipt was verified against (round 19, #1);
        # exactly one is accepted and two are refused by name.
        try:
            launcher_module.extract_review_plan_v1(contract + " " + contract)
        except launcher_module.LaunchError as exc:
            if "records" not in str(exc):
                mark_fail(f"agent-launch refused a two-record contract for another reason: {exc}")
        else:
            mark_fail(
                "agent-launch took the first of two ReviewPlan/v1 records as the plan; a "
                "record placed ahead of the canonical one would be verified against"
            )
        if restored is None:
            mark_fail("agent-launch contract carries no recoverable ReviewPlan/v1 record")
        elif restored != report:
            mark_fail("agent-launch ReviewPlan/v1 round-trips to a different report")
        # Recovery must survive authored text containing the marker. Comparing the
        # re-render of a round-tripped object against its own source cannot fail — the
        # renderer is pure and every field participates in equality — so the control is
        # a decoy contract instead, where a position-based reader picks up prose.
        decoy = (
            f"Mission: emit ReviewPlan/v1: not-json here. {contract} "
            f"trailing ReviewPlan/v1: also-not-json"
        )
        if launcher_module.extract_review_plan_v1(decoy) != report:
            mark_fail(
                "agent-launch cannot recover ReviewPlan/v1 when authored text also "
                "carries the marker"
            )

        # The stdio MCP capability must be registered in the args the backend receives,
        # keyed off the core adapter tag rather than a method name.
        if str(endpoint) not in " ".join(argv):
            mark_fail("agent-launch does not register a composable stdio MCP capability (claude)")
        try:
            _, codex_contract, codex_argv = project(text, "codex")
        except Exception as exc:
            mark_fail(f"agent-launch review contract: codex host did not launch: {exc}")
            codex_contract, codex_argv = "", []
        if "mcp_servers.gate-mcpkit.command" not in " ".join(codex_argv):
            mark_fail("agent-launch does not register a composable stdio MCP capability (codex)")

        # No shipped preset may bind a method to a seat its capability cannot fill. That
        # Contrast: the legacy path in the same config must be untouched.
        legacy_config = launcher_module.load_config(launch_profile_path)
        # `solo` is the contrast because it is still legacy. deep-review moved to the
        # composable form, and a "legacy" contrast that is not legacy proves nothing.
        legacy_plan = launcher_module.build_plan(legacy_config, "claude", "solo")
        if legacy_plan.get("review_report") is not None:
            mark_fail("agent-launch built a composable report for a legacy preset")
        if "Review setup=none:" not in launcher_module.run_contract(legacy_plan):
            mark_fail("agent-launch stopped projecting the legacy review enum")

        # Counted, because this whole block was DEAD: it sat indented under an `if` whose
        # condition was always false, and 95 lines of mandatory mutation — including the
        # shared-capability registration case — never ran on any commit that shipped them.
        # A check that cannot report having run is indistinguishable from one that passed.
        contract_cases = 0
        # Mandatory negative mutations. Each must move the projection; a mutation that
        # leaves the contract identical means the assertions above prove nothing.
        # Each mutation asserts what the projection must SAY and what the backend must
        # RECEIVE. Comparing contracts for inequality alone would pass an implementation
        # that registered every declared capability regardless of selection.
        mutations = [
            ("dropping the method", config_text(endpoint, methods=()), False, None),
            (
                "changing the effort",
                config_text(
                    endpoint, effort_binding='model = "gpt-5.6-sol"\neffort = "low"',
                    methods=(canary,),
                ),
                True, "low",
            ),
            (
                "unresolvable capability command",
                config_text(pathlib.Path(raw) / "does-not-exist", methods=(canary,)),
                False, None,
            ),
        ]
        for name, mutated_text, want_server, want_effort in mutations:
            try:
                mutated_plan, mutated_contract, mutated_argv = project(mutated_text, "claude")
            except Exception as exc:
                mark_fail(f"agent-launch review contract: {name} raised instead of projecting: {exc}")
                continue
            if mutated_contract == contract:
                mark_fail(
                    f"agent-launch review contract: {name} left the contract identical — "
                    "the control cannot fail"
                )
            # The registration, not the contract text: the endpoint also appears inside
            # the instruction, so a substring search over argv would be satisfied by
            # prose and could never fail.
            registered = bool(
                json.loads(mutated_argv[mutated_argv.index("--mcp-config") + 1])["mcpServers"]
                if "--mcp-config" in mutated_argv else {}
            )
            contract_cases += 1
            if registered != want_server:
                mark_fail(
                    f"agent-launch review contract: after {name} the stdio capability was "
                    f"{'registered' if registered else 'absent'}, want the opposite"
                )
            if want_effort is not None:
                row = next(
                    (r for r in mutated_plan["review_report"].methods if r.method_id == canary),
                    None,
                )
                if row is None or row.effort != want_effort:
                    mark_fail(
                        f"agent-launch review contract: {name} did not reach the projected "
                        f"seat (effort={getattr(row, 'effort', None)!r}, want {want_effort!r})"
                    )

        # Two methods on one capability must project exactly one server on BOTH hosts.
        # Appending per row registered it twice, which only codex's argv revealed.
        shared_text = config_text(endpoint, methods=(canary, f"{canary}-b"))
        for host in ("claude", "codex"):
            try:
                shared_plan, _, shared_argv = project(shared_text, host)
            except Exception as exc:
                mark_fail(f"agent-launch review contract: shared capability on {host}: {exc}")
                continue
            if len(shared_plan["review_report"].methods) != 2:
                mark_fail("agent-launch review contract: the shared-capability case lost a method")
            # Counted over the REGISTRATION only. The endpoint also appears inside the
            # contract, which travels in argv as well, so counting it across all of argv
            # conflates instruction text with the server the backend is handed.
            if host == "codex":
                registered = " ".join(shared_argv).count("mcp_servers.gate-mcpkit.command=")
            elif "--mcp-config" in shared_argv:
                config_json = json.loads(shared_argv[shared_argv.index("--mcp-config") + 1])
                registered = len(config_json["mcpServers"])
            else:
                registered = 0
            contract_cases += 1
            if registered != 1:
                mark_fail(
                    f"agent-launch registered a shared stdio capability {registered} times "
                    f"on {host}, want exactly 1"
                )

        # ── the registration NAME, reconciled between the contract and argv ───────────
        # The mutations above vary method removal, effort and resolved command, and hold
        # the capability's IDENTITY fixed — so the one value that becomes the backend's
        # `mcp_servers.<name>` namespace was the one nothing varied. Renaming only the
        # capability produced different argv under a byte-identical contract, while the
        # contract's own tail promises that what is described there is what runs (spec
        # round 5, L7).
        #
        # Twins on BOTH hosts, because the two argv shapes are built separately — a dict
        # under `--mcp-config` on claude, repeated `-c mcp_servers.*` overrides on codex —
        # and a name that stopped reaching one of them is invisible from the other.
        def registered_servers(argv, host):
            """(name -> command) the backend is really handed, read off ARGV rather than
            off the plan. The contract has to reconcile with what was projected, and a
            reader that asked the plan again would agree with itself by construction."""
            if host == "codex":
                found = {}
                for token in argv:
                    if token.startswith("mcp_servers.") and ".command=" in token:
                        key, _, value = token.partition(".command=")
                        found[key.removeprefix("mcp_servers.")] = json.loads(value)
                return found
            if "--mcp-config" in argv:
                servers = json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]
                return {name: entry["command"] for name, entry in servers.items()}
            return {}

        same_text = config_text(endpoint, methods=(canary,))
        # ONLY the capability id moves: same command, same method, same seat. The method
        # block names the capability, so both sites rename together — a rename that broke
        # the reference would drop the row and prove nothing.
        renamed_text = same_text.replace("gate-mcpkit", "gate-renamedkit")
        rename_cases = 0
        for host in ("claude", "codex"):
            try:
                _, same_contract, same_argv = project(same_text, host)
                _, twin_contract, twin_argv = project(same_text, host)
                _, renamed_contract, renamed_argv = project(renamed_text, host)
            except Exception as exc:
                mark_fail(f"agent-launch review contract: rename twins on {host}: {exc}")
                continue
            same_servers = registered_servers(same_argv, host)
            renamed_servers = registered_servers(renamed_argv, host)
            # Vacuity: with no server registered on either side there is nothing for a
            # rename to move, and every assertion below would hold over an empty set.
            if not same_servers or not renamed_servers:
                mark_fail(
                    f"agent-launch review contract: the rename twins registered "
                    f"{len(same_servers)}/{len(renamed_servers)} server(s) on {host} — "
                    f"vacuous, the case cannot fail"
                )
                continue
            rename_cases += 1
            # The nearest control: the SAME text projected twice must render the same
            # contract. Without it, "the rename moved the contract" is satisfied by any
            # nondeterminism in the projection, and the case grades noise.
            if twin_contract != same_contract:
                mark_fail(
                    f"agent-launch review contract: two projections of one config differ "
                    f"on {host}; the rename case cannot attribute a difference"
                )
            if set(renamed_servers) == set(same_servers):
                mark_fail(
                    f"agent-launch review contract: renaming the capability left the "
                    f"registered server names unchanged on {host} — the mutation is inert"
                )
            elif renamed_contract == same_contract:
                mark_fail(
                    f"agent-launch review contract: renaming the capability moved the "
                    f"registered server names on {host} "
                    f"({sorted(same_servers)} -> {sorted(renamed_servers)}) and left the "
                    f"contract byte-identical; the name is the backend's server namespace, "
                    f"so the contract describes a launch other than the one that runs"
                )
            # Reconciliation proper, and the reason inequality alone is not enough: a
            # contract that moved for some unrelated reason would satisfy it. Every
            # registration argv carries must be findable in the contract, name and command
            # together, on both sides of the rename.
            for label, servers, contract_text in (
                ("baseline", same_servers, same_contract),
                ("renamed", renamed_servers, renamed_contract),
            ):
                for name, command in servers.items():
                    # Named apart, because they fail for different reasons and a control
                    # graded by its neighbour's message has stopped testing: the command
                    # already reached the contract through the method's instruction
                    # template, and the NAME is the half that reached nothing.
                    missing = [
                        part for part, value in (("name", name), ("command", command))
                        if value not in contract_text
                    ]
                    if missing:
                        mark_fail(
                            f"agent-launch review contract: the {label} projection on "
                            f"{host} registers {name!r} at {command!r}, and the contract "
                            f"does not state its {' or its '.join(missing)}"
                        )
        contract_cases += rename_cases
        if rename_cases != 2:
            mark_fail(
                f"agent-launch review contract: the capability-rename case ran on "
                f"{rename_cases} host(s), want 2; the two argv shapes are built "
                f"separately, so one host is half the surface"
            )

        # ── the child agent-template projection (spec round 6, L7) ───────────────────
        # The same defect as the capability rename above, one projection later. A tier's
        # template decides the description the backend receives AND, through the digest that
        # names the config directory, the path it reads the child's binding from — and the
        # contract stated neither, so repointing one tier at another tier's template
        # produced different argv under a byte-identical contract. This check ran the whole
        # live chain already and never varied a template; the adjacent `agent_materialization`
        # exercises the projection without ever comparing it to the contract.
        #
        # Synthetic templates in a directory of this check's own, so the two mutations are
        # exact. The first moves the DESCRIPTION; the second is a restatement carrying the
        # same description and a different body, so only the content digest moves. A fix
        # that stated descriptions and left the paths out passes the first and fails the
        # second, which is the entire reason the second exists.
        templates_dir = pathlib.Path(raw) / "agent-templates"
        templates_dir.mkdir()
        for tier in ("frontier", "workhorse", "sweep"):
            (templates_dir / f"{tier}.toml").write_text(f'description = "gate {tier} child"\n')
        (templates_dir / "sweep-restated.toml").write_text(
            'description = "gate sweep child"\ninstructions = "a body only the digest sees"\n'
        )

        def child_text(pointer):
            """The composable config with its agent templates pointed at the fixture, and
            optionally with `sweep` repointed at another file in it."""
            text = config_text(endpoint, methods=(canary,)).replace(
                '"${CODEX_HOME}/agents/', f'"{templates_dir}/'
            )
            if pointer is None:
                return text
            return text.replace(
                f'sweep = "{templates_dir}/sweep.toml"',
                f'sweep = "{templates_dir}/{pointer}"',
            )

        base_child = child_text(None)
        # The rewrite is the fixture: if it silently missed, every case below would run
        # against whatever templates this machine happens to have and both mutations would
        # be inert — the failure mode this whole block exists to catch, wearing green.
        if ('"${CODEX_HOME}/agents/' in base_child
                or f'sweep = "{templates_dir}/sweep.toml"' not in base_child
                or child_text("frontier.toml") == base_child):
            mark_fail(
                "agent-launch review contract: the child-template cases could not repoint "
                "[hosts.codex.agent_templates] at the fixture, so their mutations are inert "
                "and they cannot fail"
            )

        def registered_children(argv):
            """(tier -> {description, config_file}) the backend is really handed, read off
            ARGV for the reason the server reader above is: a reader that asked the plan
            again would agree with itself by construction."""
            found = {}
            for token in argv:
                if not token.startswith("agents."):
                    continue
                for field in ("description", "config_file"):
                    if f".{field}=" in token:
                        key, _, value = token.partition(f".{field}=")
                        found.setdefault(key.removeprefix("agents."), {})[field] = json.loads(value)
            return found

        child_cases = 0
        for label, pointer in (
            ("repointing a tier at another tier's template", "frontier.toml"),
            ("repointing a tier at a restatement of its own", "sweep-restated.toml"),
        ):
            try:
                _, base_contract, base_argv = project(base_child, "codex")
                _, twin_contract, _ = project(base_child, "codex")
                _, moved_contract, moved_argv = project(child_text(pointer), "codex")
            except Exception as exc:
                mark_fail(
                    f"agent-launch review contract: child-template twins for {label}: {exc}"
                )
                continue
            base_children = registered_children(base_argv)
            moved_children = registered_children(moved_argv)
            # Vacuity: with no child registered — or one registered by name only — every
            # assertion below holds over an empty or half-empty set.
            if (not base_children or not moved_children
                    or any(len(entry) != 2 for entry in base_children.values())):
                mark_fail(
                    f"agent-launch review contract: the child-template twins registered "
                    f"{base_children!r}/{len(moved_children)} child agent(s) — vacuous, "
                    f"{label} cannot fail"
                )
                continue
            child_cases += 1
            # The nearest control, for the reason the rename case carries one: without it,
            # "the mutation moved the contract" is satisfied by any nondeterminism.
            if twin_contract != base_contract:
                mark_fail(
                    f"agent-launch review contract: two projections of one config differ on "
                    f"codex; {label} cannot attribute a difference"
                )
            if moved_children == base_children:
                mark_fail(
                    f"agent-launch review contract: {label} left the registered children "
                    f"unchanged — the mutation is inert"
                )
            elif moved_contract == base_contract:
                mark_fail(
                    f"agent-launch review contract: {label} moved what the backend registers "
                    f"({base_children!r} -> {moved_children!r}) and left the contract "
                    f"byte-identical; a child's description is what the main session reads "
                    f"when it chooses a tier and its config file is where the binding comes "
                    f"from, so the contract describes a launch other than the one that runs"
                )
            # Reconciliation proper, for the reason the rename case needs it: a contract
            # that moved for an unrelated reason satisfies inequality alone. Halves named
            # apart, because they fail for different reasons — a fix stating descriptions
            # only leaves the config path reaching argv from nowhere the reader can see.
            for tag, children, contract_text in (
                ("baseline", base_children, base_contract),
                (label, moved_children, moved_contract),
            ):
                for tier, entry in sorted(children.items()):
                    missing = [
                        part for part in ("description", "config file")
                        if entry[part.replace(" ", "_")] not in contract_text
                    ]
                    if missing:
                        mark_fail(
                            f"agent-launch review contract: the {tag} projection registers "
                            f"child {tier!r} as {entry['description']!r} at "
                            f"{entry['config_file']!r}, and the contract does not state its "
                            f"{' or its '.join(missing)}"
                        )
        contract_cases += child_cases
        if child_cases != 2:
            mark_fail(
                f"agent-launch review contract: the child-template case ran {child_cases} "
                f"time(s), want 2; the description half and the content-digest half are "
                f"different halves of the registration and one proves nothing about the other"
            )
        # And why the clause is codex-only rather than an omission: `claude_agents` derives
        # its descriptions from the tier, model and effort the `tiers:` clause already
        # states, so nothing an author writes reaches claude's `--agents` except through
        # that clause. Asserted rather than assumed — the day claude starts reading these
        # templates, this fires and says the scope is now a hole.
        try:
            _, claude_base, claude_base_argv = project(base_child, "claude")
            _, claude_moved, claude_moved_argv = project(child_text("frontier.toml"), "claude")
        except Exception as exc:
            mark_fail(f"agent-launch review contract: child-template scope on claude: {exc}")
        else:
            if claude_base_argv != claude_moved_argv or claude_base != claude_moved:
                mark_fail(
                    "agent-launch review contract: repointing a Codex agent template moved "
                    "the claude projection, which reads no template today — the child clause "
                    "is rendered for codex only, so that scope is now a hole rather than a "
                    "fact about where the authored value goes"
                )

        # ── each projection is computed ONCE per launch projection (spec round 7, L7) ──
        # One producer was proven for both registrations above — and the producer was
        # still CALLED twice inside one `project_args`: the contract render computed the
        # value and the argv builders computed it again, and both producers reread their
        # sources (template files, PATH), so a change landing between the two calls put
        # one value in the contract and another in argv. Every static twin above holds
        # the sources fixed for the duration of a projection and cannot see it; these
        # make the source answer DIFFERENTLY on every call and require the contract to
        # still reconcile with the argv beside it. Each half first proves its needle is
        # armed — two direct producer calls under the patch must disagree — because a
        # patch that misses its seam leaves the case passing over nothing.
        temporal_cases = 0

        def argv_contract(argv, host):
            """The contract the SAME projection call injected, read off argv like the
            registrations are: a reader that called run_contract again would hand the
            recomputation a fresh chance to agree with itself."""
            if host == "codex":
                return json.loads(next(
                    token.split("=", 1)[1] for token in argv
                    if token.startswith("developer_instructions=")
                ))
            return argv[argv.index("--append-system-prompt") + 1]

        # Child half: the sweep template's bytes change on every read after the first.
        try:
            temporal_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
            temporal_path.write_text(base_child)
            temporal_plan = launcher_module.build_plan(
                launcher_module.load_config(temporal_path), "codex", "gate-composable"
            )
        except Exception as exc:
            mark_fail(f"agent-launch review contract: temporal child subject: {exc}")
            temporal_plan = None
        if temporal_plan is not None:
            source = launcher_module.expand_config_path(
                temporal_plan["agent_templates"]["sweep"]
            )
            real_read = pathlib.Path.read_text
            reads = {"n": 0}

            def shifting_read(self, *args, **kwargs):
                text = real_read(self, *args, **kwargs)
                if self == source:
                    reads["n"] += 1
                    if reads["n"] >= 2:
                        return text.replace(
                            "gate sweep child", f"gate sweep child SHIFT-{reads['n']}", 1
                        )
                return text

            pathlib.Path.read_text = shifting_read
            try:
                first = launcher_module.child_agent_registrations(temporal_plan)
                second = launcher_module.child_agent_registrations(temporal_plan)
                temporal_argv = launcher_module.project_args(
                    temporal_plan, materialize_agents=False
                )
            except Exception as exc:  # noqa: BLE001 — a raw escape fails the case
                mark_fail(f"agent-launch review contract: temporal child twin raised: {exc}")
                first = second = temporal_argv = None
            finally:
                pathlib.Path.read_text = real_read
            if temporal_argv is not None:
                children = registered_children(temporal_argv)
                if first == second or not children or any(
                    len(entry) != 2 for entry in children.values()
                ):
                    mark_fail(
                        "agent-launch review contract: the temporal child twin's needle is "
                        "not armed — successive projections agree or argv registers "
                        f"nothing ({children!r}), so the case cannot fail"
                    )
                else:
                    temporal_cases += 1
                    contract_text = argv_contract(temporal_argv, "codex")
                    for tier, entry in sorted(children.items()):
                        missing = [
                            part for part in ("description", "config file")
                            if entry[part.replace(" ", "_")] not in contract_text
                        ]
                        if missing:
                            mark_fail(
                                f"agent-launch review contract: with the sweep template "
                                f"changing between reads, ONE projection registered child "
                                f"{tier!r} as {entry['description']!r} at "
                                f"{entry['config_file']!r} while its own contract does not "
                                f"state its {' or its '.join(missing)} — the projection "
                                f"was computed once for the contract and again for argv"
                            )
        # MCP half: command resolution answers a different path on every call. Both
        # hosts, because the two argv shapes are built separately.
        for host in ("claude", "codex"):
            try:
                mcp_temporal_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
                mcp_temporal_path.write_text(same_text)
                mcp_temporal_plan = launcher_module.build_plan(
                    launcher_module.load_config(mcp_temporal_path), host, "gate-composable"
                )
            except Exception as exc:
                mark_fail(f"agent-launch review contract: temporal MCP subject on {host}: {exc}")
                continue
            real_resolve = launcher_module.resolve_command
            shifts = {"n": 0}

            def shifting_resolve(command):
                if command == str(endpoint):
                    shifts["n"] += 1
                    return f"{endpoint}-shift{shifts['n']}"
                return real_resolve(command)

            launcher_module.resolve_command = shifting_resolve
            try:
                first = launcher_module.review_mcp_servers(mcp_temporal_plan)
                second = launcher_module.review_mcp_servers(mcp_temporal_plan)
                mcp_argv = launcher_module.project_args(
                    mcp_temporal_plan, materialize_agents=False
                )
            except Exception as exc:  # noqa: BLE001 — a raw escape fails the case
                mark_fail(
                    f"agent-launch review contract: temporal MCP twin on {host} raised: {exc}"
                )
                continue
            finally:
                launcher_module.resolve_command = real_resolve
            servers = registered_servers(mcp_argv, host)
            if first == second or not servers:
                mark_fail(
                    f"agent-launch review contract: the temporal MCP twin's needle is not "
                    f"armed on {host} — successive projections agree or argv registers "
                    f"nothing, so the case cannot fail"
                )
                continue
            temporal_cases += 1
            contract_text = argv_contract(mcp_argv, host)
            for server_name, command in servers.items():
                missing = [
                    part for part, value in (("name", server_name), ("command", command))
                    if value not in contract_text
                ]
                if missing:
                    mark_fail(
                        f"agent-launch review contract: with command resolution changing "
                        f"between calls, ONE projection on {host} registered "
                        f"{server_name!r} at {command!r} while its own contract does not "
                        f"state its {' or its '.join(missing)} — the projection was "
                        f"computed once for the contract and again for argv"
                    )
        contract_cases += temporal_cases
        if temporal_cases != 3:
            mark_fail(
                f"agent-launch review contract: the once-per-projection case ran "
                f"{temporal_cases} time(s), want 3 (child on codex, MCP on both hosts); "
                f"the halves patch different seams and one proves nothing about the other"
            )

        # ── authored values that reach the contract as prose (round 20, #5) ───────────
        # Exactly one decodable record is the plan. The instruction-template and mission
        # doors were repaired in round 19 and still hold; what walked past them were the
        # values nobody had listed — the METHOD ID core prefixes to every rendered row, and
        # the TRIGGER substituted into an already-checked mission. Refusal has to happen
        # where the text is authored: "the contract carries 2 records" arrives at recovery,
        # names neither the field nor the file, and by then the session has launched.
        marker = launcher_module.REVIEW_PLAN_MARKER
        forged = marker + '{"schema":"ReviewPlan/v1","availability":"forged"}'
        marker_cases = 0

        def marker_contract(method_id):
            """A REGISTERED method whose id is author-chosen, like every method id is."""
            path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
            path.write_text(launch_profile_path.read_text() + f'''
[capabilities.gate-markerkit]
command = "{endpoint}"
offers = [{{ operation = "marker-review", adapter = "exec-stdio-v1", hosts = ["codex", "claude"] }}]

[review_methods.{json.dumps(method_id)}]
label = "Marker probe"
description = "Gate fixture: the author names the method, and the renderer prefixes that name."
capability = "gate-markerkit"
operation = "marker-review"
instructions = "invoke {{command}} on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[presets.gate-marker]
label = "gate-marker"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.gate-marker.review.base]
provider = "openai"
tier = "frontier"

[presets.gate-marker.review.methods.{json.dumps(method_id)}]
provider = "openai"
tier = "frontier"
''')
            marker_plan = launcher_module.build_plan(
                launcher_module.load_config(path), "claude", "gate-marker"
            )
            return launcher_module.run_contract(marker_plan)

        def evidence_contract(value):
            """A capability OFFER's declared evidence field name — author-chosen like every
            other name in that block, and serialized verbatim into the canonical record."""
            path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
            path.write_text(launch_profile_path.read_text() + f'''
[capabilities.gate-evidencekit]
command = "{endpoint}"
offers = [{{ operation = "marker-review", adapter = "exec-stdio-v1", hosts = ["codex", "claude"], evidence = [{json.dumps(value)}] }}]

[review_methods.gate-evidence-lens]
label = "Evidence probe"
description = "Gate fixture: the author names the fields the tool reports back."
capability = "gate-evidencekit"
operation = "marker-review"
instructions = "invoke {{command}} on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[presets.gate-evidence]
label = "gate-evidence"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.gate-evidence.review.base]
provider = "openai"
tier = "frontier"

[presets.gate-evidence.review.methods.gate-evidence-lens]
provider = "openai"
tier = "frontier"
''')
            plan = launcher_module.build_plan(
                launcher_module.load_config(path), "claude", "gate-evidence"
            )
            # The PLAN, not the contract. Rendering is the caller's, because the
            # record-span backstop below would refuse this launch outright once the offer
            # door is gone — and a case graded on that refusal is grading the backstop.
            return plan, next(
                r for r in plan["review_report"].methods
                if r.method_id == "gate-evidence-lens"
            )

        def trigger_contract(value):
            cfg = launcher_module.load_config(launch_profile_path)
            cfg["presets"]["balanced"]["mission"] = "run {trigger} first"
            cfg["presets"]["balanced"]["trigger"] = value
            return launcher_module.run_contract(
                launcher_module.build_plan(cfg, "claude", "balanced")
            )

        def structural_contract(value):
            """Past every authored-value door, by mutating the PLAN. This is what the next
            field nobody has listed looks like from run_contract's side."""
            probe = launcher_module.build_plan(
                launcher_module.load_config(launch_profile_path), "claude", "balanced"
            )
            probe["mission"] = value
            return launcher_module.run_contract(probe)

        # Each case names the door that must refuse it, not merely that SOME door did. The
        # structural door catches all three, so a shared needle would have graded the two
        # field doors on it and gone on passing with either of them deleted — a control that
        # tests a different mechanism than the one it is written against.
        for label, render, forged_value, plain_value, door in (
            ("a registered method id", marker_contract, forged, "gate-marker-lens",
             "the rendered row for review method"),
            ("a preset trigger", trigger_contract, forged, "distill!",
             "presets.balanced.trigger contains"),
            ("the rendered contract itself", structural_contract, forged, "get on with it",
             "the contract text rendered"),
        ):
            marker_cases += 2
            try:
                text = render(forged_value)
            except launcher_module.LaunchError as exc:
                if door not in str(exc):
                    mark_fail(
                        f"agent-launch review contract: {label} carrying the plan marker was "
                        f"refused by something other than its own door ({door!r} absent): {exc}"
                    )
            else:
                mark_fail(
                    f"agent-launch review contract: {label} carrying the plan marker rendered "
                    f"a contract with {text.count(marker)} markers — a second decodable record "
                    f"is chosen between by position, and nothing refused it at launch"
                )
            # The control, without which a renderer that refused every launch would pass.
            try:
                text = render(plain_value)
            except launcher_module.LaunchError as exc:
                mark_fail(f"agent-launch review contract: the {label} control was refused: {exc}")
            else:
                if text.count(marker) != 1:
                    mark_fail(
                        f"agent-launch review contract: the {label} control projects "
                        f"{text.count(marker)} records, want exactly 1"
                    )
                elif launcher_module.extract_review_plan_v1(text) is None:
                    mark_fail(
                        f"agent-launch review contract: the {label} control projects a record "
                        f"that does not decode"
                    )
        # An OFFER's declared evidence field name, which reaches the contract INSIDE the
        # canonical record rather than beside it: the three cases above all render into
        # prose, and the structural door deliberately excludes the record's own span, so
        # this one walked past every door and put a second marker in the contract (spec
        # round 3, #3). It does not raise — a capability block the parser rejects DROPS its
        # method, like every other malformed offer — so what is asserted is the outcome:
        # one marker, the row dropped, and the refusal naming the exact entry.
        marker_cases += 2
        _, marked_row = evidence_contract(forged)
        if marked_row.status != launcher_module.STATUS_DROPPED:
            mark_fail(
                f"agent-launch review contract: an offer declaring an evidence name that "
                f"carries the plan marker still seated its method ({marked_row.status}) — "
                f"the name is serialized verbatim into the record"
            )
        elif "offers[0].evidence[0]" not in marked_row.detail:
            mark_fail(
                f"agent-launch review contract: the offer's evidence-name refusal does not "
                f"name the entry: {marked_row.detail[:200]}"
            )
        elif marker in marked_row.detail:
            # The refusal is rendered as that dropped row's `detail`, so a message that
            # REPRODUCES the token it forbids puts a second marker in the contract itself —
            # the diagnostic becoming the violation (spec round 3, #3).
            mark_fail(
                "agent-launch review contract: the offer's evidence-name refusal reproduces "
                "the plan marker, and it is rendered into the contract as the dropped row's "
                f"detail: {marked_row.detail[:200]}"
            )
        # The control, without which a fixture that dropped every method would pass: the
        # same offer with an ordinary name seats the method, snapshots the declaration, and
        # renders one record.
        plain_plan, plain_row = evidence_contract("reached_seat")
        if plain_row.status == launcher_module.STATUS_DROPPED:
            mark_fail(
                f"agent-launch review contract: the evidence-name control DROPPED its "
                f"method ({plain_row.detail[:160]}) — the case above then proves nothing"
            )
        elif plain_row.evidence != ("reached_seat",):
            mark_fail(
                f"agent-launch review contract: the evidence-name control snapshotted "
                f"{plain_row.evidence!r}, not the offer's declaration"
            )
        elif launcher_module.run_contract(plain_plan).count(marker) != 1:
            mark_fail(
                "agent-launch review contract: the evidence-name control projects a "
                "contract that is not exactly one record"
            )
        # …and the RECORD's own span, asserted as a property rather than as a list. The
        # loop above checks the text before and after the record and skips the record
        # itself, which is exactly where the field nobody listed landed. Reached past every
        # authored-value door by putting the marker on a RESOLVED row, the way the next
        # such field will arrive.
        marker_cases += 2
        def record_span_contract(value):
            probe = launcher_module.build_plan(
                launcher_module.load_config(launch_profile_path), "claude", "balanced"
            )
            report = probe["review_report"]
            probe["review_report"] = launcher_module.ReviewReport(
                dataclasses.replace(report.base, evidence=(value,)),
                report.methods, report.best_grade, report.availability,
                report.achieved_grade, report.achievement,
            )
            return launcher_module.run_contract(probe)
        try:
            text = record_span_contract(forged)
        except launcher_module.LaunchError as exc:
            if "the canonical review record spans" not in str(exc):
                mark_fail(
                    f"agent-launch review contract: a marker serialized INTO the record was "
                    f"refused by something other than the record-span door: {exc}"
                )
        else:
            mark_fail(
                f"agent-launch review contract: a value carrying the plan marker serialized "
                f"into the canonical record rendered {text.count(marker)} markers with "
                f"nothing refusing it — the span whose position identifies the plan"
            )
        try:
            text = record_span_contract("reached_seat")
        except launcher_module.LaunchError as exc:
            mark_fail(
                f"agent-launch review contract: the record-span control was refused: {exc}"
            )
        else:
            if text.count(marker) != 1:
                mark_fail(
                    f"agent-launch review contract: the record-span control projects "
                    f"{text.count(marker)} records, want exactly 1"
                )
        if marker_cases < 10:
            mark_fail(
                f"agent-launch review contract: only {marker_cases} marker case(s) ran; the "
                f"list of authored values that reach prose has grown twice, and a shrinking "
                f"count is how the next one goes unwatched"
            )

        # The canary proves no code change was involved.
        for source in (launcher, pathlib.Path(__file__)):
            if canary in source.read_text(errors="ignore"):
                mark_fail(f"agent-launch review contract: canary name leaked into {source.name}")


        if contract_cases < 12:
            mark_fail(
                f"agent-launch review contract: only {contract_cases} projection case(s) "
                f"ran; this block was dead once already, so a shrinking count is the "
                f"symptom to catch"
            )
    # failure is a CONFIG error, not an environment one, and the two are worth telling
    # apart: "not installed" is the user's to fix, "offers no operation for host" is
    # ours. The migration bound ultracode — a Codex-backed tool whose model catalog
    # comes from the Codex app-server — to the anthropic seat on codex mains, so the
    # contract said "run ultracode-for-codex on claude-fable-5", which cannot work.
    shipped_config = launcher_module.load_config(launch_profile_path)
    checked = 0
    for preset_name in sorted(tomllib.loads(launch_profile_path.read_text())["presets"]):
        for host in ("claude", "codex"):
            try:
                shipped_plan = launcher_module.build_plan(shipped_config, host, preset_name)
            except Exception as exc:
                mark_fail(f"agent-launch review contract: shipped {preset_name}/{host}: {exc}")
                continue
            shipped_report = shipped_plan.get("review_report")
            if shipped_report is None:
                continue
            for row in (shipped_report.base, *shipped_report.methods):
                checked += 1
                if "offers no" in (row.detail or ""):
                    mark_fail(
                        f"agent-launch shipped preset {preset_name!r} on {host} binds "
                        f"{row.method_id!r} to a seat its capability cannot fill: {row.detail}"
                    )
    if checked == 0:
        mark_fail("agent-launch review contract: no shipped composable rows inspected — vacuous")

    # The guard above catches binding to a host a capability does not CLAIM. It cannot
    # catch a capability claiming a host it cannot actually serve — that resolves fine
    # and emits an impossible instruction instead. Nothing here can verify a tool's
    # reach, so the claim is pinned as data and widening it has to be deliberate.
    shipped_capabilities = tomllib.loads(launch_profile_path.read_text())["capabilities"]

    def offered_hosts(name):
        # A SET, like the production helper. The capability schema allows several offers,
        # so a second operation on the same host is legitimate — comparing offer
        # multiplicity would have rejected that profile for widening nothing.
        return sorted({
            host
            for offer in shipped_capabilities.get(name, {}).get("offers", [])
            for host in offer.get("hosts", [])
        })

    # Both halves of the deep review, pinned in the same place and in opposite
    # directions — which is also what keeps the two from being swapped. They are named for
    # the host they run ON: `ultracode` is the Claude Code CLI's own workflow and cannot run
    # on a codex seat; `codex-exec` is the Codex CLI's non-interactive exec mode, so it
    # cannot fill a claude one. Reversing them resolves fine and emits an impossible
    # instruction — 'run codex exec on claude-fable-5' — which is the failure this pin
    # exists for.
    for capability, want in (("ultracode", ["claude"]), ("codex-exec", ["codex"])):
        hosts = offered_hosts(capability)
        if hosts != want:
            mark_fail(
                f"agent-launch offers the {capability!r} capability on {hosts}, want {want}: "
                f"the two deep reviewers are named for the host they run on, and a "
                f"seat on the other one is a seat that tool cannot fill"
            )

    # A capability whose tool IS the host's CLI must follow the CONFIGURED backend, not a
    # literal token that happens to be on this machine's PATH. Asserted by pointing the
    # claude backend at a path no `which` would find and requiring the reviewer to name it:
    # with the token duplicated, dispatch worked while the reviewer reported NOT INSTALLED
    # and the review continued without it — and on a machine where `claude` IS on PATH, which
    # is this one, nothing else here would have shown it.
    backend_dir = pathlib.Path(tempfile.mkdtemp())
    wrapper = backend_dir / "claude-wrapper"
    wrapper.write_text("#!/usr/bin/env bash\nexit 0\n")
    wrapper.chmod(0o755)
    rewired = backend_dir / "profiles.toml"
    rewired.write_text(
        launch_profile_path.read_text().replace(
            '[backends.claude]\ncommand = "claude"',
            f'[backends.claude]\ncommand = "{wrapper}"', 1,
        )
    )
    try:
        rewired_plan = launcher_module.build_plan(
            launcher_module.load_config(rewired), "codex", "deep-review"
        )
        rows = {r.method_id: r for r in rewired_plan["review_report"].methods}
        row = rows.get("ultracode")
        if row is None or row.status != launcher_module.STATUS_OK:
            mark_fail(
                f"agent-launch dropped the claude-hosted workflow reviewer when the claude "
                f"backend is a wrapper: {getattr(row, 'status', 'absent')} "
                f"({getattr(row, 'detail', '')!r}) — dispatch resolves, the reviewer did not"
            )
        elif str(wrapper) not in row.instruction:
            mark_fail(
                f"agent-launch told the workflow reviewer to run something other than the "
                f"configured claude backend {str(wrapper)!r}: {row.instruction}"
            )
    except Exception as exc:  # noqa: BLE001 — a config that will not build is the finding
        mark_fail(f"agent-launch could not project a rewired claude backend: {exc}")

    # The sentinel has to hold everywhere a capability command is READ, not just where it is
    # written. Two sites re-read it independently: MCP registration, which resolves after the
    # row is already reported available and so aborted the launch instead of dropping the
    # row; and the chooser, which is asked WITHOUT a host and labelled a legitimate two-host
    # reviewer NOT INSTALLED. A registry user can pair `${backend}` with the stdio adapter,
    # so this subject is authored the way one of them would be.
    probe_dir = pathlib.Path(tempfile.mkdtemp())
    probe_wrapper = probe_dir / "claude-wrapper"
    probe_wrapper.write_text("#!/usr/bin/env bash\nexit 0\n")
    probe_wrapper.chmod(0o755)
    probe_profile = probe_dir / "profiles.toml"
    probe_profile.write_text(
        launch_profile_path.read_text().replace(
            '[backends.claude]\ncommand = "claude"',
            f'[backends.claude]\ncommand = "{probe_wrapper}"', 1,
        ) + '''
[capabilities.gate-backend-mcp]
command = "${backend}"
offers = [{ operation = "structured-review", adapter = "mcp-stdio-v1", hosts = ["codex", "claude"] }]

[review_methods.gate-backend-mcp]
label = "L"
description = "the host CLI, served over stdio MCP"
capability = "gate-backend-mcp"
operation = "structured-review"
instructions = "invoke {command} on {model}/{effort}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
severity_emits = ["blocker"]
severity_map = { blocker = "blocker" }

[presets.gate-backend-probe]
label = "p"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.gate-backend-probe.review]
base = { provider = "openai", tier = "frontier" }

[presets.gate-backend-probe.review.methods.gate-backend-mcp]
provider = "anthropic"
tier = "frontier"
'''
    )
    try:
        probe_config = launcher_module.load_config(probe_profile)
        probe_method = launcher_module.load_review_methods(probe_config)["gate-backend-mcp"]
        if "NOT INSTALLED" in launcher_module.method_availability(probe_method, probe_config):
            mark_fail(
                "agent-launch calls a two-host backend-provided capability NOT INSTALLED; "
                "the chooser has no binding yet, so either offered backend should count"
            )
        probe_plan = launcher_module.build_plan(probe_config, "codex", "gate-backend-probe")
        servers = {name: command for name, command, _ in launcher_module.review_mcp_servers(probe_plan)}
        if servers.get("gate-backend-mcp") != str(probe_wrapper):
            mark_fail(
                f"agent-launch registered {servers.get('gate-backend-mcp')!r} for a "
                f"backend-provided MCP capability, want {str(probe_wrapper)!r}: the raw "
                f"sentinel reaches resolve_command and aborts the launch after the row was "
                f"already reported available"
            )
        launcher_module.project_args(probe_plan, materialize_agents=False)
        # ONE server while the capability means one thing — the name stays bare, which is
        # what keeps every existing registration and golden where it is.
        if list(servers) != ["gate-backend-mcp"]:
            mark_fail(
                f"agent-launch renamed a single-host MCP registration to {list(servers)}; "
                f"the host belongs in the name only when the capability is really two servers"
            )
    except Exception as exc:  # noqa: BLE001 — an abort here IS the defect
        mark_fail(f"agent-launch could not project a backend-provided MCP capability: {exc}")

    # And TWO when it really is two. A `${backend}` capability resolves to a different
    # command per host, so two methods sharing one seated on opposite providers are a legal
    # composition — it aborted the launch on a guard written for the duplicate-registration
    # case, after both rows had already reported OK.
    two_host = probe_dir / "two-host.toml"
    two_host.write_text(probe_profile.read_text().replace(
        '[presets.gate-backend-probe.review.methods.gate-backend-mcp]\nprovider = "anthropic"',
        '[presets.gate-backend-probe.review.methods.gate-backend-mcp]\nprovider = "anthropic"'
        '\ntier = "frontier"\n\n[review_methods.gate-backend-mcp-b]\nlabel = "L"\n'
        'description = "the same capability on the other seat"\ncapability = "gate-backend-mcp"\n'
        'operation = "structured-review"\ninstructions = "invoke {command} on {model}/{effort}"\n'
        'output = "review-v1"\nperspectives = ["refutation"]\ntrials = 1\n'
        'severity_emits = ["blocker"]\nseverity_map = { blocker = "blocker" }\n\n'
        '[presets.gate-backend-probe.review.methods.gate-backend-mcp-b]\nprovider = "openai"',
        1,
    ))
    try:
        two_plan = launcher_module.build_plan(
            launcher_module.load_config(two_host), "codex", "gate-backend-probe"
        )
        two_servers = {
            name: command
            for name, command, _ in launcher_module.review_mcp_servers(two_plan)
        }
        launcher_module.project_args(two_plan, materialize_agents=False)
        if len(two_servers) != 2 or len(set(two_servers.values())) != 2:
            mark_fail(
                f"agent-launch registered {two_servers} for one capability seated on two "
                f"hosts; each host's backend is a different server and needs its own name"
            )
    except Exception as exc:  # noqa: BLE001 — the abort IS the finding
        mark_fail(
            f"agent-launch refused a capability seated on two hosts, which is a legal "
            f"composition both of whose rows resolved OK: {exc}"
        )

    # ...and ONE when both hosts resolve to the same executable. Splitting on the host label
    # rather than the resolved command would start the same server twice and leave tool
    # selection ambiguous between two names for one thing.
    same_cmd = probe_dir / "same-command.toml"
    same_cmd.write_text(two_host.read_text().replace(
        '[backends.codex]\ncommand = "codex"',
        f'[backends.codex]\ncommand = "{probe_wrapper}"', 1))
    try:
        same_plan = launcher_module.build_plan(
            launcher_module.load_config(same_cmd), "codex", "gate-backend-probe"
        )
        same_servers = launcher_module.review_mcp_servers(same_plan)
        if len(same_servers) != 1:
            mark_fail(
                f"agent-launch registered {same_servers} for one capability whose two hosts "
                f"resolve to the SAME executable; that is one server under two names"
            )
    except Exception as exc:  # noqa: BLE001
        mark_fail(f"agent-launch could not project the identical-command subject: {exc}")

    # Availability must answer for the operation the METHOD asks for. A capability may serve
    # one operation on a host whose backend resolves and another only on one that does not;
    # answering with every offered host called the second method installed and then dropped
    # it at bind time.
    split_capability = {
        "command": launcher_module.HOST_BACKEND_COMMAND,
        "offers": [
            {"operation": "here", "adapter": "host-workflow-v1", "hosts": ["claude"]},
            {"operation": "there", "adapter": "host-workflow-v1", "hosts": ["codex"]},
        ],
    }
    split_config = {"backends": {"claude": {"command": str(probe_wrapper)},
                                 "codex": {"command": "/nonexistent/gate-absent-backend"}}}
    reachable = launcher_module.capability_commands(split_capability, split_config, "here")
    unreachable = launcher_module.capability_commands(split_capability, split_config, "there")
    if reachable != [str(probe_wrapper)] or unreachable != ["/nonexistent/gate-absent-backend"]:
        mark_fail(
            f"agent-launch resolved capability commands without regard to the requested "
            f"operation: here={reachable}, there={unreachable}"
        )

    # The config comment is the in-file guidance for authoring a reviewer, and an unknown
    # slot is rejected at load — so a stale list is an over-restriction that costs a real
    # reviewer. Compared against the enum the parser actually enforces.
    # Read as a SENTENCE, not line by line: the list wraps, and a token-per-line parse lost
    # the one at the wrap and reported a false drift.
    profile_comment = " ".join(
        line.lstrip("# ").rstrip()
        for line in launch_profile_path.read_text().splitlines()
        if line.startswith("#")
    )
    marker = "core slot vocabulary:"
    tail = profile_comment.split(marker, 1)[1] if marker in profile_comment else ""
    documented = {token.strip(" `") for token in tail.split(".", 1)[0].split(",")}
    missing_slots = sorted(launcher_module.INSTRUCTION_SLOTS - documented)
    if missing_slots:
        mark_fail(
            f"agent-launch's config comment does not document the slot(s) "
            f"{', '.join(missing_slots)} that the parser accepts; an author reading it would "
            f"believe a supported slot is forbidden"
        )

    # A rename moved this capability's command, and the error still sent the reader to the
    # table that no longer holds it — now a different, valid capability. The anchor rides
    # the comment's unique tail because `command = "${backend}"` appears in two blocks.
    try:
        launcher_module.load_config(_write_probe_profile(
            probe_dir / "empty-command.toml",
            '# codex CLI is a missing host, not a missing reviewer.\ncommand = "${backend}"',
            '# codex CLI is a missing host, not a missing reviewer.\ncommand = ""',
        ))
    except launcher_module.LaunchError as exc:
        if "codex-exec.command" not in str(exc):
            mark_fail(f"agent-launch blamed the wrong capability for a bad command: {exc}")
    else:
        mark_fail("agent-launch accepted an empty capability command")

    # The public docs describe how a user invokes the reviewer, so they cannot name a
    # different activation than the contract does. They advertised a session-wide effort
    # flag while the shipped instruction opens the workflow with a prompt keyword — follow
    # the docs and you get an ordinary headless session believing the workflow is on.
    # Agreement with the SHIPPED descriptor, not absence of a string. The first spelling of
    # this rule banned `--effort ultracode` from the docs — while the launcher's own frozen
    # legacy route prints exactly that flag (agent-launch.py, and 16 golden cells hold it).
    # The repo forbade in documentation what it ships in code. What the docs owe the reader
    # is the mechanism the CURRENT composable descriptor uses; the legacy layer may keep
    # describing its own.
    keyword_mechanism = "keyword `ultracode` in the prompt"
    for doc in ("docs/advanced-launch.md", "DEPENDENCIES.md"):
        text = pathlib.Path(doc).read_text()
        if keyword_mechanism not in text:
            mark_fail(
                f"{doc} does not describe how the shipped workflow reviewer is actually "
                f"activated ({keyword_mechanism!r}); a reader following it would use some "
                f"other mechanism and believe the workflow is on"
            )

    # Availability for this one is established by a PROXY: the claude CLI resolving proves
    # the command exists, not that the keyword still opens a workflow. The setting that
    # decides it is the user's and this launcher cannot read it, so the descriptor has to
    # carry the precondition to the reader — otherwise an ordinary session reports as an
    # orchestrated review, which is the exact failure this whole branch is about.
    shipped_methods = tomllib.loads(launch_profile_path.read_text()).get("review_methods", {})
    workflow_description = shipped_methods.get("ultracode", {}).get("description")
    if workflow_description is not None:
        if "workflowKeywordTriggerEnabled" not in workflow_description:
            mark_fail(
                "agent-launch's claude workflow reviewer does not name the precondition its "
                "availability cannot establish; a resolvable CLI would then stand in as "
                "proof that the workflow opens"
            )

    # A GENERATED name can collide with an AUTHORED capability id: `foo` spanning two hosts
    # yields `foo-codex`, and someone may have a capability really called `foo-codex`.
    # Claude's dict silently drops one of them and codex emits two conflicting overrides —
    # after every row was reported OK. Uniqueness is the property; the exact names are not.
    collide = probe_dir / "collide.toml"
    collide.write_text(
        probe_profile.read_text().replace(
            '[capabilities.gate-backend-mcp]',
            '[capabilities."gate-backend-mcp-codex"]\ncommand = "'
            + str(probe_wrapper) + '"\noffers = [{ operation = "structured-review", '
            'adapter = "mcp-stdio-v1", hosts = ["codex", "claude"] }]\n\n'
            '[review_methods."gate-collide"]\nlabel = "L"\ndescription = "d"\n'
            'capability = "gate-backend-mcp-codex"\noperation = "structured-review"\n'
            'instructions = "invoke {command}"\noutput = "review-v1"\n'
            'perspectives = ["refutation"]\ntrials = 1\nseverity_emits = ["blocker"]\n'
            'severity_map = { blocker = "blocker" }\n\n[capabilities.gate-backend-mcp]', 1,
        ).replace(
            '[presets.gate-backend-probe.review.methods.gate-backend-mcp]\nprovider = "anthropic"',
            '[presets.gate-backend-probe.review.methods."gate-collide"]\nprovider = "openai"\n'
            'tier = "frontier"\n\n[review_methods.gate-backend-mcp-b]\nlabel = "L"\n'
            'description = "same capability, other seat"\ncapability = "gate-backend-mcp"\n'
            'operation = "structured-review"\ninstructions = "invoke {command}"\n'
            'output = "review-v1"\nperspectives = ["refutation"]\ntrials = 1\n'
            'severity_emits = ["blocker"]\nseverity_map = { blocker = "blocker" }\n\n'
            '[presets.gate-backend-probe.review.methods.gate-backend-mcp-b]\n'
            'provider = "openai"\ntier = "frontier"\n\n'
            '[presets.gate-backend-probe.review.methods.gate-backend-mcp]\nprovider = "anthropic"',
            1,
        )
    )
    try:
        collide_plan = launcher_module.build_plan(
            launcher_module.load_config(collide), "codex", "gate-backend-probe"
        )
        collide_names = [name for name, _, _ in launcher_module.review_mcp_servers(collide_plan)]
        if len(collide_names) != len(set(collide_names)):
            mark_fail(
                f"agent-launch generated a duplicate MCP server name {collide_names}; one "
                f"registration silently replaces another on claude and conflicts on codex"
            )
        if len(collide_names) < 3:
            mark_fail(
                f"agent-launch review methods: the name-collision subject registered "
                f"{len(collide_names)} server(s), so it cannot show a collision"
            )
    except Exception as exc:  # noqa: BLE001
        mark_fail(f"agent-launch could not project the name-collision subject: {exc}")

    # Three availability states, exercised as three. "Any host resolves" alone advertised a
    # method the user could then bind to the host that does NOT resolve, which Apply turns
    # into a DROPPED row — the chooser promising something the plan withdraws.
    two_host_cap = {
        "command": launcher_module.HOST_BACKEND_COMMAND,
        "offers": [{"operation": "structured-review", "adapter": "mcp-stdio-v1",
                    "hosts": ["codex", "claude"]}],
    }

    class _Probe:
        capability = "probe"
        operation = "structured-review"
        description = "D."

    states = {
        "both": {"claude": {"command": str(probe_wrapper)}, "codex": {"command": str(probe_wrapper)}},
        "one": {"claude": {"command": str(probe_wrapper)}, "codex": {"command": "/nonexistent/gate-absent"}},
        "none": {"claude": {"command": "/nonexistent/a"}, "codex": {"command": "/nonexistent/b"}},
    }
    # The fixture has to declare hosts, because availability is now scoped to seats the
    # user could actually take: a config that can seat nothing has no install state worth
    # reporting, only NO SEAT. Without this the three states collapsed into one identical
    # string — which the distinctness assertion below caught, and is why it is there.
    probe_hosts = {"claude": {"provider": "anthropic"}, "codex": {"provider": "openai"}}
    verdicts = {}
    for label, backends in states.items():
        verdicts[label] = launcher_module.method_availability(
            _Probe(),
            {"capabilities": {"probe": two_host_cap}, "backends": backends,
             "hosts": probe_hosts},
        )
    # And the seatless config is its own answer, pinned rather than assumed: every host the
    # capability offers is one this profile cannot bind, so no install state applies.
    seatless = launcher_module.method_availability(
        _Probe(), {"capabilities": {"probe": two_host_cap}, "backends": states["both"]}
    )
    if "NO SEAT" not in seatless:
        mark_fail(
            "agent-launch reports an install state for a profile that can seat nothing: "
            f"{seatless!r}"
        )
    # Every sentence this function produces advises a BINDING, so it must never name a host
    # the provider menu does not offer. PARTIAL did: it told the user "binding it to
    # gate-offsite drops the row" about a host with no `[hosts.*]` entry — an impossible
    # action, in place of the useful fact that here the method runs on one family.
    offsite = {
        "command": launcher_module.HOST_BACKEND_COMMAND,
        "offers": [{"operation": "structured-review", "adapter": "mcp-stdio-v1",
                    "hosts": ["claude", "gate-offsite"]}],
    }
    note = launcher_module.method_availability(
        _Probe(),
        {"capabilities": {"probe": offsite},
         "backends": {"claude": {"command": str(probe_wrapper)}},
         "hosts": probe_hosts},
    )
    if "gate-offsite" in note:
        mark_fail(
            "agent-launch advises binding a method to a host this profile cannot seat: "
            f"{note!r}"
        )
    if "Runs on claude only" not in note:
        mark_fail(
            "agent-launch does not tell the chooser which seatable host a partly-offsite "
            f"method actually runs on: {note!r}"
        )
    # And again THROUGH the PARTIAL branch, which is where the impossible advice was
    # written: one seatable host reachable, one seatable host not, plus an offsite one.
    # The all-reachable probe above never enters this branch, so on its own it left the
    # sentence that actually named the offsite host completely uncovered.
    partly = {
        "command": launcher_module.HOST_BACKEND_COMMAND,
        "offers": [{"operation": "structured-review", "adapter": "mcp-stdio-v1",
                    "hosts": ["claude", "codex", "gate-offsite"]}],
    }
    advice = launcher_module.method_availability(
        _Probe(),
        {"capabilities": {"probe": partly},
         "backends": {"claude": {"command": str(probe_wrapper)},
                      "codex": {"command": "/nonexistent/gate-absent"}},
         "hosts": probe_hosts},
    )
    if "PARTIAL" not in advice:
        mark_fail(f"agent-launch PARTIAL probe does not reach the PARTIAL branch: {advice!r}")
    elif "gate-offsite" in advice:
        mark_fail(
            "agent-launch PARTIAL advises binding to a host this profile cannot seat: "
            f"{advice!r}"
        )
    elif "codex" not in advice:
        mark_fail(
            f"agent-launch PARTIAL does not name the seatable host that drops: {advice!r}"
        )
    if "PARTIAL" in verdicts["both"] or "NOT INSTALLED" in verdicts["both"]:
        mark_fail(f"agent-launch qualified a fully reachable method: {verdicts['both']!r}")
    if "PARTIAL" not in verdicts["one"]:
        mark_fail(
            f"agent-launch advertises a method as installed when only one of its hosts "
            f"resolves; the user can bind the other and Apply drops it: {verdicts['one']!r}"
        )
    if "NOT INSTALLED" not in verdicts["none"]:
        mark_fail(f"agent-launch did not call an unreachable method uninstalled: {verdicts['none']!r}")
    if len({verdicts["both"], verdicts["one"], verdicts["none"]}) != 3:
        mark_fail("agent-launch review methods: the three availability states are not distinct")

    # `install` is EXECUTED — `install.sh` hands it to `sh -c` — so prose in that field is
    # run as a shell command. A sentence shipped there once, and both halves of it failed
    # silently while the capability stayed missing. Decidable rule: whatever `sh` would run
    # first has to be something that exists.
    for name, capability in shipped_capabilities.items():
        hint = capability.get("install")
        if not hint:
            continue
        try:
            first = shlex.split(hint)[0]
        except ValueError:
            first = ""
        if not first or not (shutil.which(first) or first in INSTALLER_FRONT_ENDS):
            mark_fail(
                f"agent-launch capabilities.{name}.install starts with {first!r}, which is "
                f"not a command — install.sh runs this string through `sh -c`, so prose here "
                f"is executed and fails: {hint!r}"
            )

@launcher_check
def launcher_delegation_clause(fx):
    """A delegating launch has to say WHOSE decision the delegation was.

    Claude Code's Opus-5 prompt bundle appends "Do not call the AgentTool unless the user
    requested it" — a constant in the 2.1.220 binary, gated on that bundle and on nothing
    this launcher sets. Beside a bare `Delegation=on` those are two authorities that do not
    know about each other, and the conservative reading of the stricter one wins: a session
    configured to fan out runs single-axis instead. Observed, not theorised.

    That clause carries its own exception, so the contract satisfies it rather than arguing
    with it. Asserted here because the sentence is the entire mechanism: drop it and the
    contradiction is back with nothing to show for it."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    config = launcher_module.load_config(launch_profile_path)
    seen_on = seen_off = False
    seen_no_route = seen_route = False

    def review_line(summary_text):
        return next(
            (line for line in summary_text.splitlines() if "Review setup" in line), ""
        )

    for preset in ("balanced", "solo"):
        for host in ("claude", "codex"):
            plan = launcher_module.build_plan(config, host, preset)
            contract = launcher_module.run_contract(plan)
            argv = launcher_module.project_args(plan, materialize_agents=False)
            child_in_argv = (
                "--agents" in argv if host == "claude"
                else any(a.startswith("agents.") for a in argv)
            )
            children = [t for t in plan["tiers"] if t != plan["main_tier"]]
            # The SUMMARY, from the same plan as the contract and the argv above. It did not
            # branch on delegation at all: it printed a binding row for every tier and called
            # the child bindings configured whichever state the plan was in, so the operator
            # read one answer and the launched session received the other (round 20, #8).
            # Compared by LINE PREFIX rather than by model name, because a child tier can
            # legitimately share the main's model and a substring search would then pass on
            # the main's own row.
            summary_out = io.StringIO()
            launcher_module.print_summary(plan, host, argv, summary_out)
            summary = summary_out.getvalue()
            child_rows = [
                tier for tier in children
                if any(line.startswith(f"  {tier.upper():<14} ") for line in summary.splitlines())
            ]
            claims_children = "child bindings configured" in summary
            # The setup PANEL, the TUI's and the Custom hub's own "Current setup", read off
            # the same plan. The round-20 fix reached `print_summary` and left this twin
            # listing a binding row for every tier under delegation off (round 22, #8) —
            # the surface the user reads while choosing, above an argv carrying none of
            # them. Same prefix comparison, at this renderer's own column width.
            panel = launcher_module.setup_summary_lines(plan)
            panel_child_rows = [
                tier for tier in children
                if any(line.startswith(f"{tier.upper():<10} ") for line in panel)
            ]
            # The review line, read off the SAME summary. `solo` is review_setup="none":
            # the contract asks whether anything resolved BEFORE it branches on family and
            # correctly says no route exists, while the summary asked only the family and
            # appended "cross-family review on <host>" — so the operator was told about a
            # reviewer the launched session was never asked to run (round 21, #8).
            if "No additional review route requested" in contract:
                seen_no_route = True
                if "review on" in review_line(summary):
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: the contract says no review "
                        f"route was requested and the summary printed "
                        f"{review_line(summary).strip()!r} from the same plan"
                    )
            if plan["delegation"]:
                seen_on = True
                if "Delegation=on" not in contract:
                    mark_fail(f"agent-launch {preset!r} lost its delegation state")
                elif "the user requested delegation" not in contract:
                    mark_fail(
                        f"agent-launch {preset!r} says Delegation=on without saying the user "
                        f"asked for it, so the CLI's own 'unless the user requested it' clause "
                        f"reads as a flat prohibition and the fan-out silently does not happen"
                    )
                # Every child tier is projected and the contract lists every one.
                if not child_in_argv or any(f"{t}=" not in contract for t in children):
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is on but the child "
                        f"bindings are not both projected and listed"
                    )
                if "not projected because delegation is off" in contract:
                    mark_fail(f"agent-launch {preset!r} on {host} calls its projected children inactive")
                if sorted(child_rows) != sorted(children) or not claims_children:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is on but the summary "
                        f"lists {sorted(child_rows)} of {sorted(children)} child tiers "
                        f"(authority claimed: {claims_children}) — the projected bindings are "
                        f"what the operator is entitled to see"
                    )
                if sorted(panel_child_rows) != sorted(children):
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is on but the setup "
                        f"panel lists {sorted(panel_child_rows)} of {sorted(children)} child "
                        f"tiers — the projected bindings are what the panel exists to show"
                    )
            else:
                seen_off = True
                if "Delegation=off." not in contract or "requested delegation" in contract:
                    mark_fail(
                        f"agent-launch {preset!r} has delegation off but its contract does not "
                        f"say so plainly"
                    )
                # No child binding is projected, so none may be listed as one (round 18,
                # #9): the contract used to list all four tiers and say their defaults were
                # projected while both argv builders omitted every child.
                if child_in_argv:
                    mark_fail(f"agent-launch {preset!r} on {host}: delegation off yet a child "
                              "binding reached argv — the subject is wrong")
                if "not projected because delegation is off" not in contract:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off but the "
                        f"contract does not say the child tiers are inactive: {contract[:200]!r}"
                    )
                if any(f"{t}={plan['tiers'][t]['model']}" in contract for t in children):
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off yet a child "
                        f"tier is listed with a binding as though projected"
                    )
                if "child model/effort defaults are" in contract:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off yet the "
                        f"contract claims child defaults are projected"
                    )
                if child_rows:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off yet the summary "
                        f"prints a binding row for {sorted(child_rows)} — argv carries none of "
                        f"them, so the summary advertises seats the session never receives"
                    )
                if claims_children:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off yet the summary "
                        f"says child model/effort is configured, contradicting the contract "
                        f"printed from the same plan"
                    )
                if "inactive, not projected because delegation is off" not in summary:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off and the summary "
                        f"does not say the child tiers are inactive, so their absence reads as "
                        f"an omission rather than the state"
                    )
                if panel_child_rows:
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: delegation is off yet the setup "
                        f"panel prints a binding row for {sorted(panel_child_rows)} — argv "
                        f"carries none of them, so the panel the user reads while choosing "
                        f"advertises seats the session never receives"
                    )
                if not any(
                    "inactive, not projected because delegation is off" in line
                    for line in panel
                ):
                    mark_fail(
                        f"agent-launch {preset!r} on {host}: the setup panel drops the child "
                        f"tiers without saying they are inactive, so their absence reads as "
                        f"an omission rather than the state: {panel!r}"
                    )
    # The delegation-off tiers clause NAMES the set it lists, and the name has to be true
    # of it. It said "child tiers", which is right whenever the main is HELM — and every
    # delegation-off cell this gate and the 121-cell golden hold has a HELM main, so the
    # one shape where it is false was never rendered. With a non-HELM main the inactive set
    # CONTAINS HELM, which `SPAWNABLE_TIERS` says is never a child, and the contract told
    # the reader the launch had a child tier it structurally cannot have (round 24, #12).
    # The subject is built here rather than borrowed: no shipped preset combines the two,
    # which is exactly why nothing saw it.
    labelled_cells = 0
    for main_tier in ("helm", "workhorse"):
        clause_cfg = copy.deepcopy(config)
        clause_preset = copy.deepcopy(clause_cfg["presets"]["solo"])
        clause_preset.update({"main_tier": main_tier, "delegation": False})
        clause_cfg["presets"]["gate-inactive-label"] = clause_preset
        for host in ("claude", "codex"):
            plan = launcher_module.build_plan(clause_cfg, host, "gate-inactive-label")
            inactive = set(launcher_module.inactive_tiers(plan))
            sentence = launcher_module.run_contract(plan)
            sentence = sentence[sentence.index("LaunchPlan:"):].split(". ", 1)[0]
            if "; tiers: " not in sentence:
                mark_fail(
                    f"agent-launch inactive label ({main_tier} main on {host}): the contract "
                    f"carries no tiers clause: {sentence!r}"
                )
                continue
            clause = sentence.split("; tiers: ", 1)[1]
            listed = {tier for tier in launcher_module.TIER_ORDER
                      if tier in clause.split(" are inactive", 1)[0].split("only; ", 1)[-1]
                      .replace("(", " ").replace(")", " ").replace(",", " ").split()}
            if listed != inactive:
                mark_fail(
                    f"agent-launch inactive label ({main_tier} main on {host}): the clause "
                    f"lists {sorted(listed)} where the plan's inactive set is "
                    f"{sorted(inactive)} — the two must be the same set: {clause!r}"
                )
            # The NOUN, asserted against the set it introduces. A tier outside
            # SPAWNABLE_TIERS called a child is a false claim about the launch's shape, and
            # this is the only cell that can carry one.
            if "child tiers (" in clause and inactive - set(launcher_module.SPAWNABLE_TIERS):
                mark_fail(
                    f"agent-launch inactive label ({main_tier} main on {host}): the contract "
                    f"calls {sorted(inactive)} 'child tiers' while "
                    f"{sorted(inactive - set(launcher_module.SPAWNABLE_TIERS))} is the main "
                    f"role and never a child: {clause!r}"
                )
            if "inactive tiers (" not in clause:
                mark_fail(
                    f"agent-launch inactive label ({main_tier} main on {host}): the "
                    f"delegation-off clause does not name its set as inactive tiers, so it "
                    f"either dropped the disclosure or renamed it: {clause!r}"
                )
            if inactive - set(launcher_module.SPAWNABLE_TIERS):
                labelled_cells += 1
    if not labelled_cells:
        mark_fail(
            "agent-launch inactive label: no delegation-off cell had a non-spawnable tier "
            "in its inactive set — the shape the label can be false of is absent, so the "
            "assertions above are about the case that was never wrong"
        )

    # The route prose too, not only the tiers clause: with delegation off the cross and
    # same renderers still told the session to "fall back to native same-model subagent
    # review via the configured child agents" (round 19, #5). Mutation/control differ only
    # in delegation, on a setup whose route text carries the fallback sentence.
    for family in ("cross", "same"):
        for delegation, expect_child in ((False, False), (True, True)):
            cfg = copy.deepcopy(config)
            preset = copy.deepcopy(cfg["presets"]["solo"])
            preset.pop("review", None)
            preset.update({"delegation": delegation, "review_setup": "ultracode",
                           "review_family": family})
            cfg["presets"]["gate-fallback"] = preset
            try:
                plan = launcher_module.build_plan(cfg, "claude", "gate-fallback")
                text = launcher_module.run_contract(plan)
            except Exception as exc:  # noqa: BLE001 — any failure here is the finding
                mark_fail(f"agent-launch delegation prose subject ({family}, {delegation}) "
                          f"did not build: {exc!r}")
                continue
            # The positive control the no-route assertion above needs: a summary that
            # simply stopped printing the cross-family clause would satisfy it and lose
            # the disclosure. This preset DOES route, so its summary must still say where.
            fallback_summary = io.StringIO()
            launcher_module.print_summary(
                plan, "claude",
                launcher_module.project_args(plan, materialize_agents=False),
                fallback_summary,
            )
            if family == "cross":
                seen_route = True
                if f"cross-family review on {plan['review_host']}" not in review_line(
                    fallback_summary.getvalue()
                ):
                    mark_fail(
                        f"agent-launch cross/ultracode with delegation={delegation}: the "
                        f"summary no longer names the cross-family reviewer it resolved "
                        f"({review_line(fallback_summary.getvalue()).strip()!r})"
                    )
            promises_child = "fall back to native same-model subagent review" in text
            if promises_child != expect_child:
                mark_fail(
                    f"agent-launch {family}/ultracode with delegation={delegation}: the "
                    f"contract {'promises' if promises_child else 'does not promise'} a "
                    f"child fallback; expected {'one' if expect_child else 'none'}"
                )
            if not delegation and "no child fallback is available" not in text:
                mark_fail(
                    f"agent-launch {family}/ultracode with delegation off does not say no "
                    f"child fallback is available: {text[:200]!r}"
                )
    if not (seen_on and seen_off):
        mark_fail(
            f"agent-launch delegation clause: subjects covered on={seen_on} off={seen_off} "
            f"— both states must be exercised or the check proves nothing"
        )
    if not (seen_no_route and seen_route):
        mark_fail(
            f"agent-launch delegation clause: review-line subjects covered "
            f"no_route={seen_no_route} routed={seen_route} — the summary/contract agreement "
            f"needs both, or one of the two assertions was never reached"
        )


@launcher_check
def launcher_receipts(fx):
    """Stage 7 end to end: `--verify-receipts` run as a real process, over every way a
    receipt can be refused.

    The point of receipts is that achievement is UNFALSIFIABLE without them, so the
    controls here are mostly negative: each rejection path must name its own defect and
    exit non-zero. A verifier that accepted everything would pass a happy-path-only
    check and prove nothing."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    # A synthetic evidence-declaring capability, because no shipped one declares
    # `evidence` any more — both shipped reviewers are host CLIs whose receipts carry
    # no tool-reported fields. The crediting rules under test are method-agnostic.
    receipt_tool = tmp / "receipt-tool"
    receipt_tool.write_text("#!/usr/bin/env bash\nexit 0\n")
    receipt_tool.chmod(0o755)
    profile = tmp / "profiles.toml"
    profile.write_text(launch_profile_path.read_text() + f'''
[capabilities.receipt-kit]
command = "{receipt_tool}"
# The claude offer is listed FIRST on purpose, with evidence the codex seat never reports:
# the evidence bar used to be the first offer for the operation whatever host the row was
# seated on (round 19, #7), so a codex-seated lens was held to claude_trace.
# The third offer declares NO evidence — a real empty declaration, which is a different
# state from no offer at all (D6). Verification recorded an entry only when the list was
# non-empty and only when an offer matched, so both states arrived at the adjudicator as
# the same absence and `.get(method_id, ())` read it as "declares nothing" (spec round 2,
# #2). With one selector for launch and verification, this row is the case that proves an
# empty declaration is WRITTEN DOWN rather than left out.
offers = [
  {{ operation = "receipt-review", adapter = "exec-stdio-v1", hosts = ["claude"], evidence = ["claude_trace"] }},
  {{ operation = "receipt-review", adapter = "exec-stdio-v1", hosts = ["codex"], evidence = ["reached_seat", "billing_mode"] }},
  {{ operation = "receipt-bare", adapter = "exec-stdio-v1", hosts = ["codex", "claude"] }},
]

[review_methods.receipt-solo]
label = "Receipt solo"
description = "Gate fixture: one trial, randomized order and swap augmentation declared."
capability = "receipt-kit"
operation = "receipt-review"
instructions = "run {{command}} on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "randomized"
swap_augmentation = true
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[review_methods.receipt-lens]
label = "Receipt lens"
description = "Gate fixture: a reviewer whose offer declares evidence fields."
capability = "receipt-kit"
operation = "receipt-review"
instructions = "run {{command}} on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 2
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[review_methods.receipt-bare]
label = "Receipt bare"
description = "Gate fixture: a reviewer whose offer declares no evidence at all."
capability = "receipt-kit"
operation = "receipt-bare"
instructions = "run {{command}} on {{model}}/{{effort}}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = {{ blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }}

[presets.receipt-probe]
label = "receipt-probe"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.receipt-probe.review.base]
provider = "openai"
tier = "frontier"

[presets.receipt-probe.review.methods."receipt-lens"]
provider = "openai"
tier = "frontier"

[presets.receipt-probe.review.methods."receipt-solo"]
provider = "openai"
tier = "frontier"

[presets.receipt-probe.review.methods."receipt-bare"]
provider = "openai"
tier = "frontier"
''')
    try:
        config = launcher_module.load_config(profile)
        plan = launcher_module.build_plan(config, "claude", "receipt-probe")
        contract = launcher_module.run_contract(plan)
        report = plan["review_report"]
    except Exception as exc:
        mark_fail(f"agent-launch receipts: could not build a subject plan: {exc}")
        return
    rows = {row.method_id: row for row in (report.base, *report.methods)}
    if len(rows) < 4:
        mark_fail("agent-launch receipts: subject plan has fewer than four rows — vacuous")
        return
    # The empty-declaration row has to be SELECTED, or the state it exists to exercise is
    # not in the subject at all: a dropped `receipt-bare` would leave every assertion below
    # green while nothing carried a real empty evidence declaration.
    if rows["receipt-bare"].status == launcher_module.STATUS_DROPPED:
        mark_fail(
            "agent-launch receipts: the empty-evidence row dropped, so no selected row "
            f"declares an offer with no evidence — vacuous: {rows['receipt-bare'].detail}"
        )
    registry = launcher_module.load_review_methods(config)

    # A real digest, not a readable placeholder: `packet_sha256` is compared for
    # EQUALITY, and two equal non-hashes satisfied that comparison — the fixture said
    # "packet" on both sides and never asked whether either was a hash (round 23, #3).
    packet = hashlib.sha256(("packet-" + secrets.token_hex(8)).encode()).hexdigest()
    main_dispatch = "main-" + secrets.token_hex(8)

    def _result_hash(method_id):
        return hashlib.sha256(f"result-{method_id}".encode()).hexdigest()

    def _pass_hashes(method_id, count):
        """Distinct RESULT HASHES, one per pass. The pass count is `len(set(passes))`,
        which counts distinct strings — so `["p1", "p2"]` evidenced two passes exactly as
        well as two digests did, and the fixture could not tell the difference.

        The FIRST entry is the receipt's own `result_sha256`. The canonical fold keeps one
        pass's result as the folded record's primary and folds every pass's into `passes`,
        so a record whose primary is absent from its own pass list was never produced by
        folding — and this fixture's passes were all disjoint from their primary, which is
        why nothing here could see that the two were never tied together (spec round, #5).
        """
        return [_result_hash(method_id)] + [
            hashlib.sha256(f"pass-{method_id}-{index}".encode()).hexdigest()
            for index in range(1, count)
        ]

    def receipt(method_id, **overrides):
        row = rows[method_id]
        def evidence_for(mid):
            # By operation AND the row's host, the way the verifier now selects it: the
            # first-operation lookup this helper used to share with the verifier is the
            # defect, and a helper that agreed with it would have hidden the fix.
            method = registry.get(mid)
            capability = config.get("capabilities", {}).get(
                getattr(method, "capability", None) or ""
            )
            if not isinstance(capability, dict):
                return ()
            host = launcher_module.host_for_provider(config, rows[mid].provider, mid, missing_ok=True)
            for offer in launcher_module.parse_capability_offers(method.capability, capability):
                if offer["operation"] == method.operation and host in offer["hosts"]:
                    return offer["evidence"]
            return ()

        base = {
            "schema": "ReviewReceipt/v1",
            "method_id": method_id,
            "dispatch_id": f"dispatch-{method_id}-" + secrets.token_hex(4),
            "packet_sha256": packet,
            "result_sha256": _result_hash(method_id),
            "provider": row.provider, "model": row.model, "effort": row.effort,
            "exit_status": 0,
        }
        # The panel's descriptor asks for three trials, randomized and swapped, so a base
        # receipt must evidence three distinct passes plus the ordering seed and swap group.
        if method_id == launcher_module.PANEL_METHOD:
            base |= {
                "passes": _pass_hashes(method_id, 3),
                "ordering_seed": "seed-1",
                "swap_group": "group-a",
            }
        # The lens declares TWO passes, fixed order and no swap augmentation, and its
        # receipt carries neither seed nor group on purpose: the bar used to demand both
        # of every multi-pass method whatever it declared, so this receipt was refused for
        # lacking controls the method never ran. all-valid passing IS that assertion.
        elif method_id == "receipt-lens":
            base |= {"passes": _pass_hashes(method_id, 2)}
        # One trial, randomized and swapped: the controls are audited whatever the pass
        # count (round 19, #6), so this receipt carries a seed and a group and no passes.
        elif method_id == "receipt-solo":
            base |= {"ordering_seed": "seed-solo", "swap_group": "group-solo"}
        # Whatever this method's offer declares it reports back. Derived from the profile
        # rather than typed here, so declaring a new evidence field makes the fixture carry
        # it instead of quietly leaving the happy path un-exercised.
        declared = evidence_for(method_id)
        if declared:
            base |= {"evidence": {field: f"{field}-value" for field in declared}}
        return base | overrides

    def bundle(receipts, **overrides):
        # A bundle short of a filler row gets a valid one, so every scenario written
        # against two rows still isolates its own defect after the third and fourth rows
        # were added.
        for filler in ("receipt-solo", "receipt-bare"):
            if not any(isinstance(r, dict) and r.get("method_id") == filler for r in receipts):
                receipts = [*receipts, receipt(filler)]
        return {
            "schema": "ReviewReceipts/v1",
            "packet_sha256": packet,
            "main_dispatch_id": main_dispatch,
            "receipts": receipts,
        } | overrides

    good = [receipt("panel"), receipt("receipt-lens"), receipt("receipt-solo"),
            receipt("receipt-bare")]
    duplicate = receipt("receipt-lens", dispatch_id=good[0]["dispatch_id"])
    scenarios = [
        ("all-valid", bundle(good), 0, "achievement=complete"),
        # The tool stopped reporting: a receipt that carries no evidence is not evidence,
        # and this is the case a version probe would otherwise have to catch.
        ("no-evidence", bundle([receipt("panel"), receipt("receipt-lens", evidence={})]),
         1, "declares it returns"),
        # Partial reporting names the fields individually, so "it went quiet" and "it was
        # written against an older contract" do not read the same.
        ("half-evidence",
         bundle([receipt("panel"), receipt("receipt-lens", evidence={"reached_seat": "x"})]),
         1, "billing_mode"),
        ("missing-receipt", bundle([receipt("panel")]), 1, "no receipt was supplied"),
        ("duplicate-dispatch", bundle([good[0], duplicate]), 1, "reuses a dispatch id"),
        ("same-context", bundle([receipt("panel", dispatch_id=main_dispatch), receipt("receipt-lens")]),
         1, "main session's own context"),
        ("wrong-packet",
         bundle([receipt("panel", packet_sha256=hashlib.sha256(b"other-packet").hexdigest()),
                 receipt("receipt-lens")]),
         1, "different packet"),
        # A `*_sha256` field that is a NON-EMPTY STRING and not a hash. The absences above
        # are refused and the mismatch above is refused, but the checks between them are an
        # equality and a non-emptiness — both satisfied by any string — so a bundle and its
        # receipts all saying "packet" agreed with each other and earned `complete`, as did
        # a result hash reading "not-a-sha256" (round 23, #3). Each field separately: the
        # bundle anchor raises, the receipt fields are per-receipt verdicts, and a door that
        # noticed only one of them would leave the other two crediting non-hashes.
        ("bundle-packet-not-a-hash", bundle(good, packet_sha256="not-a-sha256"),
         1, "records packet_sha256='not-a-sha256', which is not a SHA-256 hash"),
        ("receipt-packet-not-a-hash",
         bundle([receipt("panel", packet_sha256="not-a-sha256"), receipt("receipt-lens")]),
         1, "records packet_sha256='not-a-sha256', which is not a SHA-256 hash"),
        ("result-not-a-hash",
         bundle([receipt("panel", result_sha256="not-a-sha256"), receipt("receipt-lens")]),
         1, "records result_sha256='not-a-sha256', which is not a SHA-256 hash"),
        # Uppercase hex of the right length: `hexdigest()` never writes it, so a value in
        # that spelling was not produced by hashing here either — and it is the one shape a
        # length-only or charset-only check would let through.
        ("result-uppercase-hex",
         bundle([receipt("panel", result_sha256=hashlib.sha256(b"x").hexdigest().upper()),
                 receipt("receipt-lens")]),
         1, "which is not a SHA-256 hash"),
        ("identity-mismatch", bundle([receipt("panel", model="something-else"), receipt("receipt-lens")]),
         1, "where the plan projected"),
        ("failed-dispatch", bundle([receipt("panel", exit_status=3), receipt("receipt-lens")]),
         1, "failed dispatch"),
        # JSON booleans, which `!= 0` cannot tell from an exit status: `False == 0` in
        # Python, so `"exit_status": false` was credited as a clean dispatch and earned
        # `complete` (round 22, #3). Both values, because only one of them was ever
        # refused, and it was refused as a FAILED dispatch — a diagnosis that sends the
        # reader to the reviewer instead of to the receipt's type.
        ("false-exit-status",
         bundle([receipt("panel", exit_status=False), receipt("receipt-lens")]),
         1, "records exit_status as bool"),
        ("true-exit-status",
         bundle([receipt("panel", exit_status=True), receipt("receipt-lens")]),
         1, "records exit_status as bool"),
        ("string-exit-status",
         bundle([receipt("panel", exit_status="0"), receipt("receipt-lens")]),
         1, "records exit_status as str"),
        ("empty-result",
         bundle([receipt("panel", result_sha256=launcher_module.EMPTY_SHA256), receipt("receipt-lens")]),
         1, "empty result"),
        ("unknown-method", bundle([receipt("panel"), {**receipt("receipt-lens"), "method_id": "ghost"}]),
         1, "names no selected method"),
        # The nested value the top-level shape checks did not reach. `--emit-receipt` can
        # only ever write a table here, but what this verifies is a bundle FILE — an
        # adapter's or a hand edit's — and `.get` on the raw value made the one function
        # whose job is to name a defect raise AttributeError instead of naming it.
        ("evidence-list",
         bundle([receipt("panel", evidence=["reached_seat"]), receipt("receipt-lens")]),
         1, "not a table"),
        ("evidence-string",
         bundle([receipt("panel", evidence="reached_seat"), receipt("receipt-lens")]),
         1, "not a table"),
        ("unknown-key", bundle([receipt("panel", extra="x"), receipt("receipt-lens")]),
         1, "unknown receipt key"),
        ("bad-receipt-schema", bundle([receipt("panel", schema="nope"), receipt("receipt-lens")]),
         1, "not a ReviewReceipt/v1"),
        ("receipt-not-a-table", bundle(["just a string", receipt("receipt-lens")]), 1, "not a table"),
        ("no-dispatch-id", bundle([receipt("panel", dispatch_id=""), receipt("receipt-lens")]),
         1, "carries no dispatch id"),
        ("too-few-passes",
         bundle([receipt("panel", passes=_pass_hashes("panel", 1)), receipt("receipt-lens")]),
         1, "fewer than the 3 requested passes"),
        ("no-ordering-seed", bundle([receipt("panel", ordering_seed=""), receipt("receipt-lens")]),
         1, "omits the ordering seed"),
        ("no-swap-group", bundle([receipt("panel", swap_group=""), receipt("receipt-lens")]),
         1, "omits the swap group"),
        # One trial does not exempt a declared control (round 19, #6).
        ("solo-no-seed", bundle([receipt("panel"), receipt("receipt-lens"),
                                 receipt("receipt-solo", ordering_seed="")]),
         1, "omits the ordering seed"),
        # The pass list's SHAPE is judged before its count: a nested array used to raise
        # TypeError out of the set comprehension and a number counted as a pass (#12).
        ("passes-nested",
         bundle([receipt("panel"),
                 receipt("receipt-lens", passes=[*_pass_hashes("receipt-lens", 1), ["n"]])]),
         1, "not a SHA-256 result hash"),
        ("passes-numeric",
         bundle([receipt("panel"),
                 receipt("receipt-lens", passes=[*_pass_hashes("receipt-lens", 1), 7])]),
         1, "not a SHA-256 result hash"),
        # The digest of an EMPTY result, sitting in `passes`. It IS a SHA-256 hash, so the
        # form check has nothing to say about it and `len(set(passes))` counted it as a
        # pass — while the identical value in `result_sha256` is refused two doors above
        # for reviewing nothing (round 24, #4). The bar is one predicate now, and the empty
        # digest is named for what it is rather than as a malformed hash.
        ("passes-empty-digest",
         bundle([receipt("panel"),
                 receipt("receipt-lens",
                         passes=[*_pass_hashes("receipt-lens", 1),
                                 launcher_module.EMPTY_SHA256])]),
         1, "pass entry that hashes an empty result"),
        # …and a pass entry that is a perfectly good NON-EMPTY STRING and no hash at all.
        # The count is `len(set(passes))` over distinct strings, so two arbitrary words
        # evidenced two passes exactly as well as two digests did, and every case above was
        # satisfied by a list of readable placeholders (round 23, #3).
        ("passes-not-hashes",
         bundle([receipt("panel"), receipt("receipt-lens", passes=["p1", "p2"])]),
         1, "2 pass entries that are not a SHA-256 result hash"),
        # The record's OWN result, absent from its own pass list. Every case above is
        # about the pass entries; nothing tied `result_sha256` to them, so a receipt could
        # evidence two passes and then name a primary result neither of them produced —
        # the answer the method is judged on coming from a dispatch outside the evidenced
        # set (spec round, #5). The count is satisfied here on purpose, so the refusal
        # cannot be the cardinality door: two foreign digests, both well-formed.
        ("primary-result-not-among-passes",
         bundle([receipt("panel"),
                 receipt("receipt-lens",
                         passes=[hashlib.sha256(b"foreign-pass-1").hexdigest(),
                                 hashlib.sha256(b"foreign-pass-2").hexdigest()])]),
         1, "records a primary result its own pass list does not contain"),
        # TWO receipts for one selected method. Adjudication was first-acceptance-wins,
        # which is right for choosing between verdicts and wrong for a duplicate: the
        # acceptable one hid the other entirely — uncounted, undisclosed, unrefused — so a
        # bundle carrying a receipt that fails every bar still read `complete` (spec round,
        # #3). The second receipt is deliberately VALID, because the defect is the
        # cardinality and not the second record's quality.
        ("duplicate-selected-receipt",
         bundle([receipt("panel"), receipt("panel"), receipt("receipt-lens")]),
         1, "carries more than one receipt for panel"),
        # A key the bundle grammar has no meaning for. The reader took its four anchors and
        # ignored the rest, so anything else rode along unjudged and unmentioned — in the
        # one artifact that IS under audit (spec round, #12).
        ("unknown-bundle-key", bundle(good, future_bundle_field="smuggled"),
         1, "unknown bundle key(s): future_bundle_field"),
        # The declared-controls half of the same bar: fixed order and no swap are not
        # audited for a seed or group, but the pass count still is.
        ("fixed-order-too-few-passes",
         bundle([receipt("panel"),
                 receipt("receipt-lens", passes=_pass_hashes("receipt-lens", 1))]),
         1, "fewer than the 2 requested passes"),
        ("bad-bundle-schema", bundle(good, schema="nope"), 1, "ReviewReceipts/v1 bundle"),
        ("receipts-not-array", {**bundle(good), "receipts": {}}, 1, "must be an array"),
        # The bundle's own anchors, DELETED rather than mismatched. Every scenario above
        # supplies both, which is exactly why neither absence had been judged: with no main
        # dispatch id the freshness equality matches no receipt, and with no packet hash on
        # either side the packet comparison is None == None and passes (round 20, #1).
        ("no-main-dispatch-id",
         {k: v for k, v in bundle(good).items() if k != "main_dispatch_id"},
         1, "carries no main_dispatch_id"),
        ("empty-main-dispatch-id", bundle(good, main_dispatch_id=""),
         1, "carries no main_dispatch_id"),
        ("no-bundle-packet",
         {k: v for k, v in bundle(good).items() if k != "packet_sha256"},
         1, "carries no packet_sha256"),
        # And the receipt's half of the same pair, named apart from a mismatch: "hashes a
        # different packet" would send the reader looking for the wrong packet.
        ("receipt-no-packet",
         bundle([{k: v for k, v in receipt("panel").items() if k != "packet_sha256"},
                 receipt("receipt-lens")]),
         1, "carries no packet hash"),
        # A foreign receipt ADDED to an otherwise complete bundle, not swapped in for a
        # selected one. Every verdict was the denominator, so one extra row rendered
        # `complete [n/n+1 evidenced]` — the word and the fraction disagreeing inside one
        # line (round 21, #7). It stays disclosed and stops being counted, so this expects
        # SUCCESS: the selected review really is complete and the exit status must say so.
        ("foreign-receipt-extra",
         bundle([*good, {**receipt("receipt-lens"), "method_id": "ghost",
                         "dispatch_id": "ghost-dispatch"}]),
         0, "4/4 evidenced"),
    ]
    if not scenarios:
        mark_fail("agent-launch receipts: no scenarios — vacuous")
    if not any(expected == 0 for _, _, expected, _ in scenarios):
        mark_fail("agent-launch receipts: no scenario expects success — the verifier could "
                  "reject everything and pass")

    plan_file = tmp / "plan.json"
    plan_file.write_text(json.dumps(launcher_module.review_plan_v1(report)))
    contract_file = tmp / "contract.txt"
    contract_file.write_text(contract)

    def run(plan_path, bundle_path):
        proc = subprocess.run(
            [sys.executable, str(launcher), "--config", str(profile),
             "--verify-receipts", str(plan_path), str(bundle_path)],
            capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
        )
        return proc.returncode, proc.stdout + proc.stderr

    for name, payload, expected_status, expected_text in scenarios:
        path = tmp / f"receipts-{name}.json"
        path.write_text(json.dumps(payload))
        status, output = run(plan_file, path)
        if (status == 0) != (expected_status == 0):
            mark_fail(
                f"agent-launch receipts: {name} exited {status}, expected "
                f"{'success' if expected_status == 0 else 'failure'} — {output.strip()[:160]}"
            )
        if expected_text not in output:
            mark_fail(
                f"agent-launch receipts: {name} did not name its defect "
                f"({expected_text!r} absent from {output.strip()[:160]!r})"
            )

    # The plan carries the controls the registry declared AT LAUNCH, and the verifier
    # holds the two together: a descriptor edited since is refused by name rather than
    # silently becoming the bar (round 19, #3). Mutation: the lens's trials edited in the
    # registry after the plan file was written. Control: the untouched registry verifies.
    drifted_profile = tmp / "drifted-profiles.toml"
    drifted_profile.write_text(profile.read_text().replace(
        'trials = 2\norder = "fixed"', 'trials = 1\norder = "fixed"', 1
    ))
    if drifted_profile.read_text() == profile.read_text():
        mark_fail("agent-launch receipts: the registry-drift mutation did not apply — vacuous")
    good_path = tmp / "receipts-good.json"
    good_path.write_text(json.dumps(bundle(good)))
    drift = subprocess.run(
        [sys.executable, str(launcher), "--config", str(drifted_profile),
         "--verify-receipts", str(plan_file), str(good_path)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    if drift.returncode == 0 or "changed since" not in drift.stdout + drift.stderr:
        mark_fail(
            "agent-launch receipts: a registry edited after launch was accepted as the bar "
            f"(rc={drift.returncode}) — the plan's recorded controls were not held against it"
        )
    # A row without the recorded controls is refused BY NAME, not by KeyError.
    stale = json.loads(plan_file.read_text())
    stale["base"].pop("controls", None)
    stale_path = tmp / "plan-no-controls.json"
    stale_path.write_text(json.dumps(stale))
    old = subprocess.run(
        [sys.executable, str(launcher), "--config", str(profile),
         "--verify-receipts", str(stale_path), str(good_path)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    if old.returncode == 0 or "carries no 'controls'" not in old.stdout + old.stderr:
        mark_fail(
            "agent-launch receipts: a plan row without controls was not refused by name "
            f"(rc={old.returncode}): {(old.stdout + old.stderr).strip()[:160]}"
        )
    # The key PRESENT and null is the same missing snapshot, and null is precisely the value
    # the drift comparison skipped — so a row could satisfy the check above and still be
    # adjudicated against today's registry (round 20, #3). Two assertions, because the
    # refusal alone would be satisfied by a verifier that refused every plan: the drifted
    # registry must reject the nulled row, and the intact one must still verify it once the
    # snapshot is real. The subject is the same plan file, mutated one field at a time.
    nulled = json.loads(plan_file.read_text())
    nulled["base"]["controls"] = None
    nulled_path = tmp / "plan-null-controls.json"
    nulled_path.write_text(json.dumps(nulled))
    if json.loads(plan_file.read_text())["base"]["controls"] is None:
        mark_fail("agent-launch receipts: the null-controls mutation changed nothing — vacuous")
    status, output = run(nulled_path, good_path)
    if status == 0 or "records controls as NoneType" not in output:
        mark_fail(
            "agent-launch receipts: a plan row recording controls as null was not refused by "
            f"name (rc={status}), so the launch-time snapshot the verifier audits against was "
            f"never required to exist: {output.strip()[:160]}"
        )
    # …and the drifted registry proves the nulled row was a BYPASS, not merely unusual: the
    # same registry edit that the intact plan refuses used to be accepted through it.
    nulled_drift = subprocess.run(
        [sys.executable, str(launcher), "--config", str(drifted_profile),
         "--verify-receipts", str(nulled_path), str(good_path)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    if nulled_drift.returncode == 0:
        mark_fail(
            "agent-launch receipts: a null-controls plan verified against a registry edited "
            "after launch — the recorded-controls check is bypassed by the one value a "
            "tampered or pre-migration record most easily holds"
        )

    # The EVIDENCE bar, drifted the way the registry above was: the requirement deleted
    # from the capability's offer AFTER the plan was written. Only `controls` was
    # snapshotted on the row, so this bar was recomputed from the config at verification
    # time and the same bundle went from `none [0/1]`, exit 1, to `complete [1/1]`, exit 0
    # — the one bar the audited party could lower by editing the file the auditor reads
    # (round 24, #1). The bundle is the one that OMITS the lens's evidence, so a verifier
    # still holding the launch-time bar has something to refuse.
    no_evidence_bundle = tmp / "receipts-no-evidence.json"
    dropped_evidence_profile = tmp / "dropped-evidence-profiles.toml"
    dropped_evidence_profile.write_text(profile.read_text().replace(
        ', evidence = ["reached_seat", "billing_mode"] }', " }", 1
    ))
    if dropped_evidence_profile.read_text() == profile.read_text():
        mark_fail("agent-launch receipts: the evidence-drift mutation did not apply — vacuous")
    drifted_evidence = subprocess.run(
        [sys.executable, str(launcher), "--config", str(dropped_evidence_profile),
         "--verify-receipts", str(plan_file), str(no_evidence_bundle)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    drifted_output = drifted_evidence.stdout + drifted_evidence.stderr
    if drifted_evidence.returncode == 0 or "the capability's offer changed since" not in drifted_output:
        mark_fail(
            "agent-launch receipts: an offer whose evidence was deleted after launch became "
            f"the bar (rc={drifted_evidence.returncode}) — the plan's recorded evidence was "
            f"not held against it: {drifted_output.strip()[:200]}"
        )
    # …and the same bundle against the UNTOUCHED profile must still be refused for the
    # reason it was always refused for. Without this the assertion above is satisfied by a
    # verifier that refuses every bundle, and the diagnosis would be free to become the
    # drift one everywhere.
    status, output = run(plan_file, no_evidence_bundle)
    if status == 0 or "declares it returns" not in output:
        mark_fail(
            "agent-launch receipts: the evidence-drift control does not discriminate — the "
            f"untouched profile reports {output.strip()[:160]!r} rather than the missing "
            f"evidence field"
        )

    # A selected row whose PROVIDER this config maps to no host. `missing_ok=True` yields
    # None, the host predicate was then skipped, and the first offer for the operation won
    # — so the claude offer's `claude_trace` became the bar for an openai-seated row, and a
    # receipt reporting it certified a codex row (round 24, #2). The subject is the shipped
    # two-offer capability, whose claude offer is listed FIRST for exactly this reason.
    hostless_profile = tmp / "hostless-provider-profiles.toml"
    # Anchored on the line the HOST table pairs its provider with, not on the bare
    # `provider = "openai"` — six review bindings in the shipped profile spell that
    # identically, and the first of them is not the one this is about.
    host_provider_line = 'provider = "openai"\nmodels = ['
    if profile.read_text().count(host_provider_line) != 1:
        mark_fail(
            "agent-launch receipts: the codex host's provider line is no longer uniquely "
            "identifiable, so the hostless-provider mutation would land somewhere else"
        )
    hostless_profile.write_text(profile.read_text().replace(host_provider_line, "models = [", 1))
    if hostless_profile.read_text() == profile.read_text():
        mark_fail("agent-launch receipts: the hostless-provider mutation did not apply — vacuous")
    if 'provider = "openai"' not in hostless_profile.read_text():
        mark_fail(
            "agent-launch receipts: the hostless-provider mutation removed every openai "
            "binding, not just the host's — the plan under test would then name no provider"
        )
    hostless = subprocess.run(
        [sys.executable, str(launcher), "--config", str(hostless_profile),
         "--verify-receipts", str(plan_file), str(good_path)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    hostless_output = hostless.stdout + hostless.stderr
    if hostless.returncode == 0:
        mark_fail(
            "agent-launch receipts: a row whose provider resolves to no host was adjudicated "
            f"anyway — an unresolved host is not a wildcard that matches every offer: "
            f"{hostless_output.strip()[:200]}"
        )
    elif "maps it to no host" not in hostless_output:
        # Refused, but for something else. Without the door of its own, the wrong offer is
        # SELECTED and the evidence-drift comparison then refuses the disagreement it
        # produced — a true verdict reached through a false step, and the operator is sent
        # to the registry instead of to the provider their plan names. Named separately
        # because "it failed" and "it failed for this reason" are different properties, and
        # a guard whose only proof is another guard is untested (round 20).
        mark_fail(
            "agent-launch receipts: an unresolvable provider was refused by some other door "
            f"than its own — the offer was still chosen by guesswork first: "
            f"{hostless_output.strip()[:200]}"
        )
    if "Traceback" in hostless_output:
        mark_fail("agent-launch receipts: the unresolvable-provider refusal reached the "
                  "operator as a traceback")

    # NO OFFER SERVES THE ROW'S HOST. The launch selector refuses a method it cannot seat
    # by name; verification ran a second loop over the same offers, and when none matched
    # it simply wrote no entry — which `required_evidence.get(method_id, ())` then read as
    # "this method declares nothing", so a method the launcher would never have seated was
    # adjudicated against a bar of nothing and reported complete (spec round 2, #2). The
    # mutation moves the codex offer onto claude, leaving the codex-seated rows with no
    # offer at all; the shipped fixture's rows are openai/codex-seated, so this is the same
    # capability both loops read.
    unserved_profile = tmp / "unserved-host-profiles.toml"
    unserved_profile.write_text(profile.read_text().replace(
        'hosts = ["codex"], evidence = ["reached_seat", "billing_mode"]',
        'hosts = ["claude"], evidence = ["reached_seat", "billing_mode"]', 1
    ))
    if unserved_profile.read_text() == profile.read_text():
        mark_fail("agent-launch receipts: the unserved-host mutation did not apply — vacuous")
    unserved = subprocess.run(
        [sys.executable, str(launcher), "--config", str(unserved_profile),
         "--verify-receipts", str(plan_file), str(good_path)],
        capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
    )
    unserved_output = unserved.stdout + unserved.stderr
    if unserved.returncode == 0:
        mark_fail(
            "agent-launch receipts: a selected row no offer serves was adjudicated anyway — "
            f"an unmatched offer is not an empty evidence declaration: "
            f"{unserved_output.strip()[:200]}"
        )
    elif "offers no 'receipt-review' operation for host 'codex'" not in unserved_output:
        # Refused, but by another door. Without the selector's own refusal the row falls
        # through to a bar of nothing, and whether anything then objects depends on whether
        # the row's snapshot happened to be non-empty — a true verdict reached by accident,
        # and the operator sent to the registry instead of to the offer that does not serve
        # their host. Named separately, as the unresolvable-provider case beside it is.
        mark_fail(
            "agent-launch receipts: a row no offer serves was refused by some other door "
            f"than the selector's — the two loops still disagree about which offer serves a "
            f"host: {unserved_output.strip()[:200]}"
        )
    if "Traceback" in unserved_output:
        mark_fail("agent-launch receipts: the unserved-host refusal reached the operator as "
                  "a traceback")
    # The positive control: the untouched profile, whose codex offer does serve those rows,
    # still verifies the same bundle. Without it the case above is satisfied by a verifier
    # that refuses every profile.
    status, output = run(plan_file, good_path)
    if status != 0 or "achievement=complete" not in output:
        mark_fail(
            f"agent-launch receipts: the unserved-host control does not discriminate — the "
            f"untouched profile reports {output.strip()[:200]!r}"
        )

    # A row that is not a TABLE at all. `_row_from_v1` assumed a dictionary and reached
    # `.get` while FORMATTING the refusal it meant to raise, so the reader whose contract
    # is that a wrong shape is named left the CLI as an AttributeError traceback instead
    # (round 21, #6). Both positions the shape can arrive in, plus `methods` itself held as
    # a string — iterable, so it was silently read as one row per character.
    # A grade this subject plan does NOT reach, chosen from the enum rather than typed:
    # asserting a fixed value would go quiet the day the fixture's seats change, which is
    # the "control that indexes a live list" trap in its other form.
    reached = launcher_module.best_review_grade((report.base, *report.methods))
    other_grade = next(g for g in launcher_module.GRADE_ORDER if g != reached)
    for label, mutate, needle in (
        ("string base row", lambda rec: rec.update(base="not-a-row"), "a row is str"),
        ("string method row", lambda rec: rec.update(methods=["not-a-row"]), "a row is str"),
        ("methods not an array", lambda rec: rec.update(methods="panel"),
         "methods is str, not an array of rows"),
        ("null base row", lambda rec: rec.update(base=None), "a row is NoneType"),
        # The row's own IDENTITY FIELDS, one at a time. Every case above mutates a whole
        # row container or `controls`, so the fields the verifier actually COMPARES were
        # never asked for: a selectable row holding None for provider, model and effort was
        # matched by a receipt that omitted all three — three absences comparing equal, and
        # `complete` (round 22, #1). Each field separately, because a door that only
        # noticed all three at once would pass on the receipt that omits one.
        ("null provider on a selected row",
         lambda rec: rec["base"].update(provider=None), "records provider=None on a OK row"),
        ("null model on a selected row",
         lambda rec: rec["base"].update(model=None), "records model=None on a OK row"),
        ("null effort on a selected row",
         lambda rec: rec["base"].update(effort=None), "records effort=None on a OK row"),
        ("null mechanism on a selected row",
         lambda rec: rec["base"].update(mechanism=None), "records mechanism=None on a OK row"),
        ("empty seat field on a selected row",
         lambda rec: rec["base"].update(provider=""), "records provider='' on a OK row"),
        ("nameless row", lambda rec: rec["base"].update(method_id=""),
         "records method_id '', not a name"),
        ("unreadable status", lambda rec: rec["base"].update(status="MAYBE"),
         "records status 'MAYBE'"),
        ("null grade on a selected row", lambda rec: rec["base"].update(grade=None),
         "records grade None on a OK row"),
        # The plan HEADER, which every case above leaves alone. Rows were hardened twice
        # while `availability`, `best_grade` and `achieved_grade` were copied through
        # untouched, so a forged availability survived verification and was rendered as
        # "launch-time projection, unchanged by verification" — the sentence that vouches
        # for the value made out of the value (round 23, #2). One field per case, because a
        # door noticing only a wholly wrong header would pass on each single forgery, and a
        # non-string case too: the field is compared, never parsed.
        ("forged availability", lambda rec: rec.update(availability="forged-reachable"),
         "availability='forged-reachable' is none of projected"),
        ("non-string availability", lambda rec: rec.update(availability=7),
         "availability=7 is none of projected"),
        ("unknown best_grade", lambda rec: rec.update(best_grade="forged_grade"),
         "best_grade='forged_grade' is none of perspective_floor"),
        ("achieved_grade forged into a launch-time record",
         lambda rec: rec.update(achieved_grade="provider_difference"),
         "achieved_grade='provider_difference' is none of UNKNOWN_UNTIL_RECEIPTS"),
        # `best_grade` is the one header field that states a RELATIONSHIP to the rows, and
        # the enum case above is satisfied by any member of the enum: a record could claim
        # `provider_difference` over rows that reach the floor, and the contract rendered
        # the launch's central claim about how independent its review was (round 24, #5).
        # Derived through the same helper the launch side computes it with, so the two
        # cannot drift; the value here is picked to differ from whatever this subject plan
        # actually reaches, so the case cannot go quiet if the fixture's grades move.
        ("best_grade contradicting its own rows",
         lambda rec: rec.update(best_grade=other_grade),
         "the header is a summary OF the rows"),
        # The BASE, whose status the generic row parser accepted all four values of. A
        # dropped base is the state resolve_composable_review refuses to launch in, and
        # verification removes dropped rows from the selected set — so one optional receipt
        # became complete coverage of a plan whose review floor ran nothing (round 24, #3).
        ("dropped base row", lambda rec: rec["base"].update(status="DROPPED"),
         "records the base row"),
        # The complement of the controls door, on an OPTIONAL row: DROPPED means the method
        # ran nothing, so a live controls snapshot on it is a selected row wearing the one
        # status that leaves the denominator. The seat and the grade are nulled in the SAME
        # mutation, because the two doors added beside this one (below) fire first
        # otherwise and this case would go quiet while reporting a neighbour's message.
        ("dropped row carrying a controls snapshot",
         lambda rec: rec["methods"][0].update(
             status="DROPPED", provider=None, model=None, effort=None, mechanism=None,
             grade=None),
         "declared nothing"),
        # The SEAT half of the same closure, and the emit side's twin: `_resolve_one`
        # returned a dropped row carrying a live provider, model, effort and mechanism, and
        # the parser accepted one — a row that ran nothing and left the denominator, still
        # wearing everything that makes a row look covered (spec round, #9). Each of the
        # other fields nulled, so the refusal can only be the seat.
        ("dropped row carrying a live seat",
         lambda rec: rec["methods"][0].update(
             status="DROPPED", grade=None, controls=None, evidence=[]),
         "sat on no seat"),
        # …and the GRADE half. An I1 grade is a claim about independence bought, and a
        # method that ran nothing bought none. `NOT_REVIEW` is deliberately still admitted
        # here — it is the documented exclusion marker for an unattested mechanism, not a
        # rung — which the positive control below holds.
        ("dropped row carrying an independence grade",
         lambda rec: rec["methods"][0].update(
             status="DROPPED", provider=None, model=None, effort=None, mechanism=None,
             controls=None, evidence=[]),
         "bought no independence"),
        # …and every grade OUTSIDE both sets, which the ladder door one line up cannot see:
        # it asked whether the value was one of the four I1 grades, so a dropped row could
        # wear any string at all — the shape closed against the grades a launch writes and
        # open to every grade it does not (spec round 3, #5). Its own needle, because a
        # case graded on `bought no independence` would go quiet the day this door is what
        # fires. The `NOT_REVIEW` positive control below is what keeps both honest.
        ("dropped row carrying an invented grade",
         lambda rec: rec["methods"][0].update(
             status="DROPPED", grade="invented-grade", provider=None, model=None,
             effort=None, mechanism=None, controls=None, evidence=[]),
         "neither absent nor NOT_REVIEW"),
        # The row's PROSE. `detail` and `instruction` are the two fields the grammar closed
        # by NAME and never by TYPE, so a container was copied through and reaches the
        # contract as its repr rather than as a sentence (spec round 3, #4). One case each,
        # because a door asking only about `detail` would leave its twin open — which is
        # how the pair got here.
        ("row detail in a container",
         lambda rec: rec["base"].update(detail=["not", "text"]),
         "records detail as list"),
        ("row instruction in a container",
         lambda rec: rec["base"].update(instruction={"run": "it"}),
         "records instruction as dict"),
        # The plan grammar, CLOSED. Both readers took the fields they knew and dropped the
        # rest, so a record carrying a key they do not know parsed clean and re-emitted
        # without it — a later schema's bar erased in silence (spec round, #8). The plan
        # and the row are separate doors with separate messages, so each is asserted where
        # the other cannot fire.
        ("unknown plan key", lambda rec: rec.update(future_plan_bar="smuggled"),
         "unknown plan key(s): future_plan_bar"),
        ("unknown row key",
         lambda rec: rec["base"].update(future_row_bar="smuggled"),
         "unknown row key(s): future_row_bar"),
        # The BASE's own id, which neither the parser nor the adjudicator ever asked for.
        # `panel` was refused among the optional rows and any id was refused twice, and a
        # base wearing any other name passed both: every launch builds the base from
        # `methods[PANEL_METHOD]`, so a renamed base was resolved from no panel descriptor
        # at all and its two-perspective, two-trial floor was never the bar — while the row
        # still counted as the review floor and reached `achievement=complete` (spec round
        # 2, #1). Its own sentence, because the DROPPED-base door one line away already
        # owns "records the base row".
        ("base row under another name",
         lambda rec: rec["base"].update(method_id="renamed-base"),
         "the floor's own controls were never its bar — re-launch"),
        # The CONTROLS snapshot's contents, which the row reader never looked inside. It
        # asked only whether the value was a table, so a row could carry `trials=True` —
        # read by `controls.get("trials", 1)` as a single pass — an `order` and an
        # `aggregation` outside their closed domains, and a key nobody has a meaning for,
        # and be adjudicated against a bar no descriptor could have declared (spec round 2,
        # #5). One case per rule, because a door noticing only the unknown key would let
        # every value through, and the values are what lower the bar.
        ("controls carrying an unknown key",
         lambda rec: rec["base"]["controls"].update(future_control_bar="smuggled"),
         "records controls carrying unknown key(s): future_control_bar"),
        ("controls missing a declared key",
         lambda rec: rec["base"]["controls"].pop("aggregation"),
         "records controls omitting aggregation"),
        # A BOOLEAN trial count: `True` is an int in Python and `True >= 1`, so it survived
        # every numeric test and then demanded one pass.
        ("controls recording a boolean trial count",
         lambda rec: rec["base"]["controls"].update(trials=True),
         "records controls whose trials must be an integer >= 1"),
        ("controls recording a zero trial count",
         lambda rec: rec["base"]["controls"].update(trials=0),
         "records controls whose trials must be an integer >= 1"),
        ("controls recording an order outside its domain",
         lambda rec: rec["base"]["controls"].update(order="sideways"),
         "records controls whose order must be one of"),
        ("controls recording an aggregation outside its domain",
         lambda rec: rec["base"]["controls"].update(aggregation="plurality"),
         "records controls whose aggregation must be one of"),
        ("controls recording a non-boolean swap",
         lambda rec: rec["base"]["controls"].update(swap_augmentation=0),
         "records controls whose swap_augmentation must be boolean"),
        # `panel` among the optional methods, and any id on two rows. The authored side
        # refuses `review.methods.panel` at parse, and the adjudicator refuses two selected
        # rows sharing an id — but a plan RECORD reaches neither door, and a rendered
        # contract or a saved projection reaches only this one (spec round, #10).
        # All three identity cases carry the PARSE door's own tail. One validator answers
        # this for the reader and for the adjudicator now, and both raise the same
        # sentence — so a needle taken from the shared middle is satisfied by whichever
        # door happens to fire, and reverting the reader's call would leave these cases
        # green on the adjudicator's message. `— re-launch` is appended by the reader
        # alone; the adjudicator's in-process cases below assert its wording instead.
        ("panel among the optional methods",
         lambda rec: rec["methods"].append(json.loads(json.dumps(rec["base"]))),
         "is not the plan this adjudicates — re-launch"),
        ("one id on two optional rows",
         lambda rec: rec["methods"].append(json.loads(json.dumps(rec["methods"][0]))),
         "certified by a single receipt — re-launch"),
        # The EVIDENCE snapshot, the field that made the bar audit-able at all. It was
        # recomputed from the config at verification time while `controls` was snapshotted,
        # so the audited party could lower its own bar by editing the file the auditor reads
        # (round 24, #1). Absent and malformed, each named: a record written before the
        # field existed cannot be held to the offer it launched under.
        ("plan row with no evidence snapshot",
         lambda rec: rec["base"].pop("evidence"), "carries no 'evidence'"),
        ("plan row whose evidence is not a list of fields",
         lambda rec: rec["base"].update(evidence="reached_seat"),
         "not the list of field names its offer declared at launch"),
        # …and an evidence NAME carrying the plan marker, at the reader's own door. The
        # offer that authors such a name is refused where it is written, but a record
        # arrives from anywhere and is re-serialized by anything that re-renders it, so
        # the same rule is asked here (spec round 3, #3). Needled on the row's context,
        # which the offer's door never emits.
        ("plan row whose evidence name carries the plan marker",
         lambda rec: rec["base"].update(
             evidence=[launcher_module.REVIEW_PLAN_MARKER + "shadow"]),
         "evidence[0] contains the ReviewPlan/v1 record marker"),
    ):
        malformed = json.loads(plan_file.read_text())
        mutate(malformed)
        if malformed == json.loads(plan_file.read_text()):
            mark_fail(f"agent-launch receipts: the {label} mutation changed nothing — vacuous")
        malformed_path = tmp / f"plan-{label.replace(' ', '-')}.json"
        malformed_path.write_text(json.dumps(malformed))
        status, output = run(malformed_path, good_path)
        if status == 0 or needle not in output:
            mark_fail(
                f"agent-launch receipts: a plan holding a {label} was not refused by name "
                f"(rc={status}, want {needle!r}): {output.strip()[:200]}"
            )
        if "Traceback" in output:
            mark_fail(
                f"agent-launch receipts: a plan holding a {label} reached the operator as a "
                f"traceback — the reader's whole contract is that a wrong shape is named"
            )

    # The positive control the eight identity cases need: the seat fields are nullable on a
    # DROPPED row, and a door that refused every null would satisfy all of them while making
    # an ordinary plan — any preset with one unavailable method — unverifiable. A dropped
    # row holding null everywhere is ADDED to the same plan, which must still verify.
    with_dropped = json.loads(plan_file.read_text())
    with_dropped["methods"] = [*with_dropped["methods"], {
        "method_id": "gate-dropped", "status": launcher_module.STATUS_DROPPED, "grade": None,
        "detail": "no such review method is registered", "model": None, "effort": None,
        "provider": None, "mechanism": None, "instruction": "", "controls": None,
        # A dropped row declares no evidence, exactly as a launch emits it: the offer's
        # declared fields are snapshotted on the row now (round 24, #1), and a row that ran
        # nothing reports nothing.
        "evidence": [],
    }]
    dropped_path = tmp / "plan-dropped-row.json"
    dropped_path.write_text(json.dumps(with_dropped))
    status, output = run(dropped_path, good_path)
    if status != 0 or "achievement=complete" not in output:
        mark_fail(
            "agent-launch receipts: a plan carrying a DROPPED row with null seat fields no "
            f"longer verifies (rc={status}) — the seat door is supposed to bind selectable "
            f"rows only, and the null-field cases above prove nothing if it binds all: "
            f"{output.strip()[:200]}"
        )
    # …and the one grade a DROPPED row may still carry. `NOT_REVIEW` is the documented
    # exclusion marker for a mechanism core does not attest — a gate, not a rung — and the
    # deployed guidance names it in as many words, so a door refusing every grade on a
    # dropped row would satisfy the case above while making an ordinary unattested-mechanism
    # plan unverifiable. Taken from the module rather than typed, because what is asserted
    # is that THIS value stays admissible.
    unattested = json.loads(json.dumps(with_dropped))
    unattested["methods"][-1]["grade"] = launcher_module.GRADE_NOT_REVIEW
    unattested_path = tmp / "plan-dropped-not-review.json"
    unattested_path.write_text(json.dumps(unattested))
    status, output = run(unattested_path, good_path)
    if status != 0 or "achievement=complete" not in output:
        mark_fail(
            f"agent-launch receipts: a DROPPED row graded {launcher_module.GRADE_NOT_REVIEW} "
            f"no longer verifies (rc={status}) — the exclusion marker is not an independence "
            f"grade, and refusing it makes every unattested-mechanism plan unadjudicable: "
            f"{output.strip()[:200]}"
        )

    # ── the PACKET. Every equality the adjudicator makes of `packet_sha256` is between the
    # bundle and its own receipts, which are the artifacts under audit: they agree with each
    # other by construction, and nothing bound the anchor to any bytes (spec round, #1).
    # Supplied, the packet is rehashed here and the plan it CARRIES has to be the plan being
    # adjudicated. Four cases, because each half is satisfiable by the wrong thing.
    packet_dir = tmp / "packets"
    packet_dir.mkdir()
    real_packet = packet_dir / "packet.txt"
    real_packet.write_text(
        "review packet\n"
        + launcher_module.REVIEW_PLAN_MARKER
        + json.dumps(launcher_module.review_plan_v1(report))
        + "\n",
        encoding="utf-8",
    )
    other_packet = packet_dir / "other.txt"
    other_packet.write_text("a packet nobody reviewed\n", encoding="utf-8")
    plainer_packet = packet_dir / "no-record.txt"
    plainer_packet.write_text("review packet\n", encoding="utf-8")
    foreign_plan = json.loads(plan_file.read_text())
    foreign_plan["base"]["detail"] = "a different launch entirely"
    foreign_packet = packet_dir / "foreign-plan.txt"
    foreign_packet.write_text(
        "review packet\n"
        + launcher_module.REVIEW_PLAN_MARKER + json.dumps(foreign_plan) + "\n",
        encoding="utf-8",
    )

    def bundle_anchored_to(packet_path, label):
        """A bundle whose anchor is that packet's digest — the receipts' too.

        Each door has to be REACHED, and the digest comparison sits ahead of the plan
        comparison: a bundle anchored elsewhere makes every case fail as a digest mismatch
        and the plan doors would never fire."""
        digest = hashlib.sha256(pathlib.Path(packet_path).read_bytes()).hexdigest()
        path = tmp / f"receipts-anchored-{label}.json"
        path.write_text(json.dumps({
            **bundle([receipt("panel", packet_sha256=digest),
                      receipt("receipt-lens", packet_sha256=digest),
                      receipt("receipt-solo", packet_sha256=digest),
                      receipt("receipt-bare", packet_sha256=digest)]),
            "packet_sha256": digest,
        }))
        return path

    bound_bundle = bundle_anchored_to(real_packet, "real")
    bound_packet_hash = hashlib.sha256(real_packet.read_bytes()).hexdigest()

    def run_with_packet(plan_path, bundle_path, packet_path):
        proc = subprocess.run(
            [sys.executable, str(launcher), "--config", str(profile),
             "--verify-receipts", str(plan_path), str(bundle_path),
             "--packet", str(packet_path)],
            capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
        )
        return proc.returncode, proc.stdout + proc.stderr

    for label, packet_path, bundle_path, expected_status, needle in (
        # The positive control FIRST and load-bearing: a verifier refusing every packet
        # would satisfy the three refusals below.
        ("the real packet", real_packet, bound_bundle, 0, "packet_binding=bytes"),
        ("bytes that hash to something else", other_packet, bound_bundle, 1,
         "these receipts were not collected against these bytes"),
        ("a packet carrying no plan record", plainer_packet,
         bundle_anchored_to(plainer_packet, "plain"), 1,
         f"carries no {launcher_module.REVIEW_PLAN_SCHEMA} record"),
        ("a packet carrying another plan", foreign_packet,
         bundle_anchored_to(foreign_packet, "foreign"), 1,
         f"carries a different {launcher_module.REVIEW_PLAN_SCHEMA} record"),
    ):
        status, output = run_with_packet(plan_file, bundle_path, packet_path)
        if (status == 0) != (expected_status == 0):
            mark_fail(
                f"agent-launch receipts: --packet with {label} exited {status}, expected "
                f"{'success' if expected_status == 0 else 'failure'}: {output.strip()[:200]}"
            )
        if needle not in output:
            mark_fail(
                f"agent-launch receipts: --packet with {label} did not name its outcome "
                f"({needle!r} absent from {output.strip()[:200]!r})"
            )
    # …and the two plan-door cases must not be satisfiable by the DIGEST door: each is run
    # against a bundle anchored to its OWN packet, so the digest agrees and only the plan
    # comparison can refuse. Asserted rather than assumed, because a helper that quietly
    # anchored every bundle to the same packet would make both cases read as digest
    # mismatches while still failing by the expected name.
    for label, path in (("no-record", plainer_packet), ("foreign-plan", foreign_packet)):
        anchored = json.loads(bundle_anchored_to(path, "assert-" + label).read_text())
        if anchored["packet_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            mark_fail(
                f"agent-launch receipts: the {label} bundle is not anchored to its own "
                f"packet, so its refusal cannot be attributed to the plan comparison"
            )
        if anchored["packet_sha256"] == bound_packet_hash:
            mark_fail(
                f"agent-launch receipts: the {label} packet hashes to the real packet's "
                f"digest — the two cases are not distinguishable"
            )
    # …and without `--packet` the verdict has to SAY the anchor is bound to nothing, rather
    # than reading as though it were. A disclosure nobody renders is a disclosure nobody
    # reads, and this is the whole remedy for the half of D4 that stays open (Q3).
    status, output = run(plan_file, tmp / "receipts-all-valid.json")
    if "packet_binding=none" not in output:
        mark_fail(
            "agent-launch receipts: a verdict reached with no packet artifact does not "
            f"disclose that packet_sha256 was bound to no bytes: {output.strip()[:200]}"
        )
    # The main seat is not serialized, so a row's independence grade cannot be recomputed
    # from the record and an enum-valid forged one survives parse (spec round, #4). Left
    # unenforced deliberately — the schema evolution that would close it is Q2 — so the
    # rendering states it every time instead of letting silence read as derivation.
    if "grade_derivation=claimed" not in output:
        mark_fail(
            "agent-launch receipts: a verdict does not disclose that its row grades are the "
            f"launch's own claim rather than a recomputation: {output.strip()[:200]}"
        )
    # …asserted on a plan whose base grade really has been forged, so the disclosure is
    # shown to survive the case it exists for rather than only the happy path. The TOP
    # grade, which `best_review_grade` then derives as the header — the one door that IS
    # enforced — so the record parses and the forgery is invisible, which is the finding.
    forged = json.loads(plan_file.read_text())
    forged_grade = next(
        g for g in launcher_module.GRADE_ORDER if g != forged["base"]["grade"]
    )
    forged["base"]["grade"] = forged_grade
    # The header IS enforced — `best_grade` must equal what its rows reach — so the forgery
    # has to carry the header with it or the record is refused for the wrong reason.
    # Derived through the module's own helper over the mutated rows, never restated here.
    class _Row:
        def __init__(self, raw):
            self.status, self.grade = raw.get("status"), raw.get("grade")
    forged["best_grade"] = launcher_module.best_review_grade(
        [_Row(raw) for raw in (forged["base"], *forged["methods"])]
    )
    forged_path = tmp / "plan-forged-grade.json"
    forged_path.write_text(json.dumps(forged))
    status, output = run(forged_path, good_path)
    if "grade_derivation=claimed" not in output:
        mark_fail(
            "agent-launch receipts: a plan carrying a row grade no launch could have "
            f"produced was adjudicated with no disclosure that grades are unrecomputed: "
            f"{output.strip()[:200]}"
        )

    # Two SELECTED rows under one id, reached IN PROCESS. The parse-time doors above now
    # refuse this shape in a plan file, so the adjudicator's own guard has no reachable
    # subject there any more — and a guard whose only proof is another guard is untested
    # (round 20). Reports are also built in process (check_adapter builds one), and those
    # carry whatever their constructor was given, so the guard is asserted where it can
    # still fire: the rows collapse into one dictionary entry and one receipt certified
    # every row sharing the id (round 21, #1).
    twin_controls = {
        "trials": 1, "order": "fixed", "swap_augmentation": False, "aggregation": "union",
    }
    twin_packet = hashlib.sha256(b"twin-packet").hexdigest()
    def twin_row(method_id):
        return launcher_module.ReviewMethodReport(
            method_id, launcher_module.STATUS_OK, "perspective_floor", "", "model-x",
            "high", "openai", "exec-stdio-v1", "", twin_controls, (),
        )
    # The duplicate rows are OPTIONAL ones beside a real panel base. They used to be the
    # base and one method, and the base-identity door added below (spec round 2, #1) fires
    # first on a base named anything else — so this case would report a neighbour's message
    # while asserting its own needle was absent, which is round 1's "a new door can silence
    # an old control" arriving one door later.
    def adjudicate_twins(second_id):
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(
                twin_row(launcher_module.PANEL_METHOD),
                (twin_row("twin"), twin_row(second_id)), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": twin_packet, "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": "twin", "dispatch_id": "child-twin",
                           "packet_sha256": twin_packet,
                           "result_sha256": hashlib.sha256(b"twin-result").hexdigest(),
                           "provider": "openai", "model": "model-x", "effort": "high",
                           "exit_status": 0}]},
            {launcher_module.PANEL_METHOD: twin_controls, "twin": twin_controls,
             second_id: twin_controls},
            # An evidence declaration per selected row, required of every caller since the
            # drift comparison stopped being the caller's to opt into (spec round 3, #1).
            {launcher_module.PANEL_METHOD: (), "twin": (), second_id: ()},
        )
    try:
        adjudicate_twins("twin")
    except launcher_module.LaunchError as exc:
        # The identity validator's own sentence, which the parser raises too: one function
        # answers this for both readers now, so a needle taken from the old
        # adjudication-only wording would be asserting a message nothing emits.
        if "names more than one row" not in str(exc):
            mark_fail(
                f"agent-launch receipts: a report selecting one method id twice was refused "
                f"for another reason: {exc}"
            )
    else:
        mark_fail(
            "agent-launch receipts: a report selecting one method id twice was adjudicated "
            "anyway — one receipt then certifies every row sharing that id"
        )
    # The positive control it needs: two DISTINCT ids, one receipt each missing, must
    # adjudicate rather than refuse. Without this the case above is satisfied by a verifier
    # that refuses every two-row report.
    try:
        adjudicate_twins("other")
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch receipts: a report selecting two DISTINCT ids was refused as a "
            f"duplicate: {exc} — the case above then proves nothing"
        )

    # The BASE's id, at the door where a plan file cannot reach: the parser refuses a
    # renamed base now, so the adjudicator's own half of that validator would be proved
    # only by the parser's — and a guard whose only proof is another guard is untested
    # (round 20). Reports are built in process too (`check_adapter_command` builds one),
    # and those carry whatever their constructor was given: a base under another name was
    # resolved from no panel descriptor, so the floor's two-perspective, two-trial
    # controls were never its bar, and it still reached `achievement=complete` (spec
    # round 2, #1).
    def adjudicate_base_named(method_id):
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(
                twin_row(method_id), (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": twin_packet, "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": method_id, "dispatch_id": "child-base",
                           "packet_sha256": twin_packet,
                           "result_sha256": hashlib.sha256(b"base-result").hexdigest(),
                           "provider": "openai", "model": "model-x", "effort": "high",
                           "exit_status": 0}]},
            {method_id: twin_controls}, {method_id: ()},
        )
    try:
        adjudicate_base_named("renamed-base")
    except launcher_module.LaunchError as exc:
        if "the base is the one row that must wear it" not in str(exc):
            mark_fail(
                f"agent-launch receipts: a report whose base wears another name was refused "
                f"for another reason: {exc}"
            )
    else:
        mark_fail(
            "agent-launch receipts: a report whose base is not the panel was adjudicated "
            "anyway — the row credited as the review floor was built from no panel "
            "descriptor, so the floor's own controls were never its bar"
        )
    # The positive control it needs: the SAME report with the base named `panel` verifies.
    # Without it a verifier that refused every one-row report would satisfy the case above.
    try:
        verified_base, _ = adjudicate_base_named(launcher_module.PANEL_METHOD)
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch receipts: a report whose base IS the panel was refused too "
            f"({exc}) — the renamed-base case above then proves nothing"
        )
    else:
        if verified_base.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
            mark_fail(
                f"agent-launch receipts: a one-row report named {launcher_module.PANEL_METHOD} "
                f"did not verify ({verified_base.achievement})"
            )

    # The extra foreign receipt is DISCLOSED as well as uncounted. Correcting the
    # denominator by dropping the row would satisfy the scenario's fraction and leave a
    # receipt nobody can chase, so both halves are asserted on the same run.
    status, output = run(plan_file, tmp / "receipts-foreign-receipt-extra.json")
    if status != 0:
        mark_fail(
            f"agent-launch receipts: an extra foreign receipt made a complete review fail "
            f"(rc={status}): {output.strip()[:200]}"
        )
    if "ghost" not in output or "names no selected method" not in output:
        mark_fail(
            "agent-launch receipts: an extra foreign receipt was not disclosed at all — "
            f"uncounted must not mean invisible: {output.strip()[:200]}"
        )

    # The COMPARISON itself, reached directly. The door above now refuses a null snapshot,
    # so no plan file can deliver one to the comparison any more — and a guard whose only
    # proof is another guard is untested. Reports are also built in process (check_adapter
    # builds one), and those carry whatever their constructor was given, so the comparison
    # is asserted where it can still fire. Mutation and control differ only in the row's
    # controls: None against the registry's table, then the registry's table itself.
    direct_controls = {
        "trials": 1, "order": "fixed", "swap_augmentation": False, "aggregation": "union",
    }
    direct_packet = hashlib.sha256(b"direct-packet").hexdigest()
    direct_result = hashlib.sha256(b"direct-result").hexdigest()
    # Named `panel`, because it is this report's BASE and the base wears the reserved id
    # (spec round 2, #1). What the case is about is the row's controls snapshot, so the
    # identity is set to the one value that leaves the identity door silent.
    def adjudicate_direct(row_controls, registry_controls=None):
        row = launcher_module.ReviewMethodReport(
            launcher_module.PANEL_METHOD, launcher_module.STATUS_OK, "perspective_floor",
            "", "model-x", "high", "openai", "exec-stdio-v1", "", row_controls,
        )
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(row, (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet,
             "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": launcher_module.PANEL_METHOD,
                           "dispatch_id": "child-1",
                           "packet_sha256": direct_packet,
                           "result_sha256": direct_result, "provider": "openai",
                           "model": "model-x", "effort": "high", "exit_status": 0}]},
            {launcher_module.PANEL_METHOD:
                direct_controls if registry_controls is None else registry_controls},
            {launcher_module.PANEL_METHOD: ()},
        )
    # Each case names the door that must refuse it. The adjudicator's two snapshot doors
    # are one validator away from the PARSER's, which appends `— re-launch` and these do
    # not: a needle taken from the shared middle would be satisfied by whichever door fired
    # first, and the parser's runs earlier on every plan FILE (spec round 2's R1 trap, one
    # validator later). The drift case keeps its own sentence, because a grammar door that
    # fired for both would hide the comparison going quiet.
    for label, mutate, door, why in (
        # The snapshot skipped ENTIRELY by the comparison: None is equal to nothing the
        # registry can declare, so the drift refusal used to fire and the grammar was never
        # asked. Now the grammar refuses it first, and by its own name.
        ("a None controls snapshot", lambda: adjudicate_direct(None),
         "the plan's snapshot holds controls as NoneType",
         "the drift comparison skips exactly the value a tampered or in-process report "
         "most easily holds"),
        # BOTH sides empty. Two empty tables are EQUAL, so the drift refusal passed them,
        # and `controls.get("trials", 1)` then read the emptiness as one requested pass —
        # a bar of one bought by declaring nothing on either side (spec round 3, #2).
        ("an empty snapshot against an empty declaration",
         lambda: adjudicate_direct({}, {}),
         "the plan's snapshot holds controls omitting",
         "an absence on both sides compares equal, and the pass count is then defaulted "
         "to the lowest bar this verifier can apply"),
        # The REGISTRY's side of the same grammar, which no door asked either. The row is
        # complete here, so only the descriptor map can be what is refused.
        ("an empty registry declaration",
         lambda: adjudicate_direct(dict(direct_controls), {}),
         "the registry now declares controls omitting",
         "the bar is the descriptor's, and a descriptor map that declares nothing is not "
         "a bar the launch could have been audited under"),
        # …and the COMPARISON itself, still reachable now that both sides are validated
        # first: two complete, legal, DIFFERENT tables.
        ("a drifted registry, both sides legal",
         lambda: adjudicate_direct(dict(direct_controls),
                                   {**direct_controls, "trials": 2}),
         "the descriptor changed since",
         "a descriptor edited after the launch is neither side's to resolve"),
    ):
        try:
            mutate()
        except launcher_module.LaunchError as exc:
            if door not in str(exc):
                mark_fail(
                    f"agent-launch receipts: {label} was refused by something other than "
                    f"its own door ({door!r} absent): {exc}"
                )
        else:
            mark_fail(f"agent-launch receipts: {label} was adjudicated anyway — {why}")
    try:
        verified, _ = adjudicate_direct(dict(direct_controls))
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch receipts: the direct-comparison control does not verify: {exc}")
    else:
        if verified.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
            mark_fail(
                "agent-launch receipts: a row whose recorded controls MATCH the registry did "
                f"not verify ({verified.achievement}) — the mutation above proves nothing"
            )
    # The descriptor map itself, NOT a map. The per-method grammar door the four cases
    # above assert never receives one, because `set(required_controls)` raises first: the
    # adjudication left through a TypeError, which is a traceback where `--verify-receipts`
    # is contracted to exit with a named reason, and the shared validator was never reached
    # (spec round 4, #3). Its own needle, distinct from the evidence map's below — a caller
    # holding no view of the descriptors and one holding no view of the offers are
    # different failures. The direct-comparison control just above is its positive half: a
    # real map verifies.
    for registry_label, bad_registry in (
        ("null", None), ("list-of-pairs", [("panel", direct_controls)]),
    ):
        try:
            launcher_module.verify_review_receipts(
                launcher_module.ReviewReport(
                    launcher_module.ReviewMethodReport(
                        launcher_module.PANEL_METHOD, launcher_module.STATUS_OK,
                        "perspective_floor", "", "model-x", "high", "openai",
                        "exec-stdio-v1", "", direct_controls,
                    ), (), "perspective_floor"),
                {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
                 "packet_sha256": direct_packet, "main_dispatch_id": "m",
                 "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                               "method_id": launcher_module.PANEL_METHOD,
                               "dispatch_id": "child-registry",
                               "packet_sha256": direct_packet,
                               "result_sha256": direct_result, "provider": "openai",
                               "model": "model-x", "effort": "high", "exit_status": 0}]},
                bad_registry,
                {launcher_module.PANEL_METHOD: ()},
            )
        except launcher_module.LaunchError as exc:
            if "the controls declarations were supplied as" not in str(exc):
                mark_fail(
                    f"agent-launch receipts: a {registry_label} controls registry was refused by "
                    f"another door: {exc}"
                )
        except Exception as exc:  # noqa: BLE001 — the traceback IS the finding
            mark_fail(
                f"agent-launch receipts: a {registry_label} controls registry raised "
                f"{type(exc).__name__} instead of a named refusal: {exc} — the verify "
                f"command is a gate, and a traceback names no defect and no fix"
            )
        else:
            mark_fail(
                f"agent-launch receipts: a {registry_label} controls registry was adjudicated — the "
                f"bar is the descriptor's, and a caller supplying no map supplied no bar"
            )

    # THAT the evidence bar is applied, on a row that declares one. Round 24 wrote this
    # case as "the row's OWN snapshot is the bar, called with no recomputation at all", and
    # that subject is gone: the drift comparison is unconditional now, so a caller supplying
    # no map is refused rather than adjudicated against the snapshot alone (spec round 3,
    # #1). Which side is read is no longer observable BECAUSE the two are proven equal
    # first — so what stays assertable is that the declared field is demanded of the
    # receipt, and the whole-map refusal is asserted on its own below.
    snapshot_row = launcher_module.ReviewMethodReport(
        launcher_module.PANEL_METHOD, launcher_module.STATUS_OK, "perspective_floor", "",
        "model-x", "high", "openai", "exec-stdio-v1", "", direct_controls,
        ("reached_seat",),
    )
    def adjudicate_snapshot(evidence_field):
        receipt_body = {
            "schema": launcher_module.RECEIPT_SCHEMA,
            "method_id": launcher_module.PANEL_METHOD,
            "dispatch_id": "child-snapshot", "packet_sha256": direct_packet,
            "result_sha256": direct_result, "provider": "openai", "model": "model-x",
            "effort": "high", "exit_status": 0,
        }
        if evidence_field is not None:
            receipt_body["evidence"] = evidence_field
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(snapshot_row, (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet, "main_dispatch_id": "m",
             "receipts": [receipt_body]},
            {launcher_module.PANEL_METHOD: direct_controls},
            {launcher_module.PANEL_METHOD: ("reached_seat",)},
        )
    silent, _ = adjudicate_snapshot(None)
    if silent.achievement == launcher_module.ACHIEVEMENT_COMPLETE:
        mark_fail(
            "agent-launch receipts: a row whose snapshot declares reached_seat was verified "
            "by a receipt reporting nothing — a declared evidence field is demanded of the "
            "receipt, and a dispatch that reported none of it is not evidenced"
        )
    reporting, _ = adjudicate_snapshot({"reached_seat": "yes"})
    if reporting.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
        mark_fail(
            f"agent-launch receipts: a receipt reporting exactly what the row's snapshot "
            f"declares did not verify ({reporting.achievement}) — the case above then only "
            f"proves the verifier refuses everything"
        )
    # The map itself, ABSENT. `required_evidence=None` was the parameter's own default and
    # it skipped the whole comparison, so the bar every selected row recorded at launch was
    # held against nothing at all — the optional half of a rule V2 calls unconditional
    # (spec round 3, #1). Its own sentence, distinct from the per-row door two cases down:
    # a caller that could not say which offer served ONE row and a caller holding no view
    # of the registry are different failures, and only the first names a method.
    try:
        launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(snapshot_row, (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet, "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": launcher_module.PANEL_METHOD,
                           "dispatch_id": "child-nomap", "packet_sha256": direct_packet,
                           "result_sha256": direct_result, "provider": "openai",
                           "model": "model-x", "effort": "high", "exit_status": 0,
                           "evidence": {"reached_seat": "yes"}}]},
            {launcher_module.PANEL_METHOD: direct_controls},
            None,
        )
    except launcher_module.LaunchError as exc:
        if "the drift comparison is unconditional" not in str(exc):
            mark_fail(
                f"agent-launch receipts: an adjudication supplied no evidence declarations "
                f"at all was refused for another reason: {exc}"
            )
    else:
        mark_fail(
            "agent-launch receipts: an adjudication with no evidence declarations supplied "
            "was accepted — the drift comparison the plan's recorded bar exists for is then "
            "the caller's to opt into, and the caller that opts out is the one under audit"
        )
    # Its positive control: the SAME receipt with the declarations supplied and agreeing
    # verifies. Without it a verifier that refused every adjudication would satisfy the
    # case above.
    mapped, _ = adjudicate_snapshot({"reached_seat": "yes"})
    if mapped.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
        mark_fail(
            f"agent-launch receipts: the same adjudication WITH declarations supplied did "
            f"not verify ({mapped.achievement}) — the absent-map case above proves nothing"
        )

    # An ABSENT evidence declaration against an EMPTY one, which `.get(method_id, ())`
    # made the same state. A caller that supplies the map at all owes an entry per selected
    # method; the default turned "I could not say which offer served this row" into "this
    # method declares nothing", and the drift comparison then passed for every row whose
    # own snapshot was empty too (spec round 2, #2). Reached in process because the map is
    # the caller's, and the two cases differ in exactly one key.
    empty_row = launcher_module.ReviewMethodReport(
        launcher_module.PANEL_METHOD, launcher_module.STATUS_OK, "perspective_floor", "",
        "model-x", "high", "openai", "exec-stdio-v1", "", direct_controls, (),
    )
    def adjudicate_declared(declarations):
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(empty_row, (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet, "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": launcher_module.PANEL_METHOD,
                           "dispatch_id": "child-declared",
                           "packet_sha256": direct_packet,
                           "result_sha256": direct_result, "provider": "openai",
                           "model": "model-x", "effort": "high", "exit_status": 0}]},
            {launcher_module.PANEL_METHOD: direct_controls},
            declarations,
        )
    try:
        adjudicate_declared({})
    except launcher_module.LaunchError as exc:
        if "an absent declaration is not an empty one" not in str(exc):
            mark_fail(
                f"agent-launch receipts: a selected method with no evidence declaration was "
                f"refused for another reason: {exc}"
            )
    else:
        mark_fail(
            "agent-launch receipts: a selected method the caller supplied no evidence "
            "declaration for was adjudicated against an empty bar — an absence and a real "
            "empty-evidence offer are different states, and only one of them was declared"
        )
    # The positive control: the same call with the entry PRESENT and empty verifies. A
    # real offer may declare no evidence, and a door refusing every empty declaration would
    # satisfy the case above while making every panel-only plan unadjudicable.
    try:
        declared, _ = adjudicate_declared({launcher_module.PANEL_METHOD: ()})
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch receipts: an evidence declaration that is present and empty was "
            f"refused ({exc}) — the absent-declaration case above then proves nothing"
        )
    else:
        if declared.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
            mark_fail(
                f"agent-launch receipts: a row declaring no evidence, against an offer that "
                f"declares none, did not verify ({declared.achievement})"
            )

    # The evidence snapshot's GRAMMAR, on BOTH sides — the twin of the controls pair
    # above, one round later. `_row_from_v1` holds a serialized row to a list of non-empty
    # names, and the adjudicator held neither the in-process row nor the caller's
    # declaration to anything: `("",)` on both sides compared EQUAL, and the empty name was
    # then looked up in the receipt's evidence table and found — a bar met by naming
    # nothing — while `None` on either side left as `tuple(None)`, a traceback out of the
    # function whose every other failure is a named refusal (spec round 4, #1). Reached in
    # process because that is the only caller able to deliver either shape: every plan FILE
    # passes the parser's door first, and the direct cases above are how that door's
    # absence here was invisible.
    def adjudicate_evidence(row_evidence, declared_evidence):
        row = launcher_module.ReviewMethodReport(
            launcher_module.PANEL_METHOD, launcher_module.STATUS_OK, "perspective_floor",
            "", "model-x", "high", "openai", "exec-stdio-v1", "", direct_controls,
            row_evidence,
        )
        return launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(row, (), "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet, "main_dispatch_id": "m",
             "receipts": [{"schema": launcher_module.RECEIPT_SCHEMA,
                           "method_id": launcher_module.PANEL_METHOD,
                           "dispatch_id": "child-evidence",
                           "packet_sha256": direct_packet,
                           "result_sha256": direct_result, "provider": "openai",
                           "model": "model-x", "effort": "high", "exit_status": 0,
                           # Reports BOTH names, so every case below is one the adjudicator
                           # would otherwise credit: the mutation is the declaration, never
                           # a silent reviewer.
                           "evidence": {"": "yes", "reached_seat": "yes"}}]},
            {launcher_module.PANEL_METHOD: direct_controls},
            declared_evidence,
        )
    for label, row_evidence, declared_evidence, door, why in (
        # The finding's own arrangement: an empty field NAME, repeated by the declaration
        # and reported by the receipt, so nothing else in the adjudication objects.
        ("an empty evidence field name on both sides", ("",),
         {launcher_module.PANEL_METHOD: ("",)},
         "the plan's snapshot holds evidence",
         "an empty name is looked up in the receipt's evidence table like any other, so a "
         "bar that names nothing is met by reporting anything"),
        # The `None` twin of the row's side, which reached no message at all.
        ("a null evidence snapshot", None, {launcher_module.PANEL_METHOD: ()},
         "the plan's snapshot holds evidence",
         "`tuple(None)` is a traceback from the reader contracted to name what it refuses"),
        # …and of the declaration's side, which is the caller's half of the same absence.
        ("a null evidence declaration", (), {launcher_module.PANEL_METHOD: None},
         "the registry now declares evidence",
         "a declaration that is not a sequence of names is not a bar the launch could "
         "have been audited under"),
        # The registry's side of the NAME rule, with the row's side legal — so only the
        # declaration can be what is refused, and the drift comparison below it is not
        # what fires.
        ("an empty field name in the registry's declaration", ("reached_seat",),
         {launcher_module.PANEL_METHOD: ("",)},
         "the registry now declares evidence",
         "the empty name would otherwise be compared against the row's, and drift is a "
         "different finding from a declaration that is not one"),
    ):
        try:
            adjudicate_evidence(row_evidence, declared_evidence)
        except launcher_module.LaunchError as exc:
            if door not in str(exc):
                mark_fail(
                    f"agent-launch receipts: {label} was refused by something other than "
                    f"its own door ({door!r} absent): {exc}"
                )
        except Exception as exc:  # noqa: BLE001 — a raw TypeError names no door at all
            mark_fail(
                f"agent-launch receipts: {label} raised {type(exc).__name__} instead of a "
                f"named refusal: {exc}"
            )
        else:
            mark_fail(f"agent-launch receipts: {label} was adjudicated anyway — {why}")
    # The positive control all four need: a real name on both sides, reported by the
    # receipt, still verifies. A validator refusing every evidence snapshot would satisfy
    # every case above and make every evidence-declaring method unadjudicable.
    try:
        named, _ = adjudicate_evidence(
            ("reached_seat",), {launcher_module.PANEL_METHOD: ("reached_seat",)})
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch receipts: a legal evidence snapshot was refused ({exc}) — the "
            f"grammar cases above then prove nothing"
        )
    else:
        if named.achievement != launcher_module.ACHIEVEMENT_COMPLETE:
            mark_fail(
                f"agent-launch receipts: a row and a declaration naming the same reported "
                f"field did not verify ({named.achievement})"
            )

    # A foreign receipt whose DISPLAY LABEL collides with a selected method id. `<unnamed>`
    # is what a malformed receipt renders as and is also a legal method id, and the verdict
    # map was keyed by that label: the selected row was overwritten by the foreign
    # diagnosis and left the denominator entirely, 0/1 becoming 0/0 (round 22, #7). In
    # process, because the collision needs a plan row named exactly that. Control: the same
    # bundle against an ordinarily-named row, which has always produced both verdicts.
    collide_controls = {
        "trials": 1, "order": "fixed", "swap_augmentation": False, "aggregation": "union",
    }
    # The colliding id is an OPTIONAL row beside a real panel base: the base wears the
    # reserved id (spec round 2, #1), so the denominator here is two selected rows and
    # both must survive the foreign diagnosis.
    def collide_row(method_id):
        return launcher_module.ReviewMethodReport(
            method_id, launcher_module.STATUS_OK, "perspective_floor", "", "model-x",
            "high", "openai", "exec-stdio-v1", "", collide_controls,
        )
    for method_id, why in (("<unnamed>", "colliding"), ("probe", "ordinary")):
        verified, verdicts = launcher_module.verify_review_receipts(
            launcher_module.ReviewReport(
                collide_row(launcher_module.PANEL_METHOD), (collide_row(method_id),),
                "perspective_floor"),
            {"schema": launcher_module.RECEIPT_BUNDLE_SCHEMA,
             "packet_sha256": direct_packet,
             "main_dispatch_id": "m", "receipts": ["not-a-table"]},
            {launcher_module.PANEL_METHOD: collide_controls,
             method_id: collide_controls},
            {launcher_module.PANEL_METHOD: (), method_id: ()},
        )
        rendered = launcher_module.render_receipt_verdicts(verified, verdicts)
        if "0/2 evidenced" not in rendered:
            mark_fail(
                f"agent-launch receipts: a {why} method id with one unusable receipt reports "
                f"{rendered.splitlines()[0]!r} — a selected method that received no valid "
                f"receipt is uncovered, never absent from the denominator"
            )
        if sum(1 for verdict in verdicts if verdict.selected) != 2:
            mark_fail(
                f"agent-launch receipts: a {why} method id yielded "
                f"{sum(1 for v in verdicts if v.selected)} selected verdict(s) for two "
                f"selected rows — a rendered label was used as identity"
            )
        if not any(not verdict.selected for verdict in verdicts):
            mark_fail(
                f"agent-launch receipts: the malformed receipt beside a {why} method id was "
                f"not disclosed at all — uncounted must not mean invisible"
            )

    # A whole launch contract is where a session actually finds its plan, so the record
    # must be recoverable from it and not only from a bare JSON file.
    status, output = run(contract_file, tmp / "receipts-all-valid.json")
    if status != 0 or "achievement=complete" not in output:
        mark_fail(f"agent-launch receipts: a full contract was not accepted as the plan: {output[:160]}")

    # The split's whole point: partial evidence must not read as never-verified. Two of
    # three methods verified (the missing-receipt bundle omits the lens) leaves
    # availability at its launch projection, reports `partial`, and still exits non-zero
    # — three facts the single field could not carry at once.
    status, output = run(contract_file, tmp / "receipts-missing-receipt.json")
    if status == 0:
        mark_fail("agent-launch receipts: partial evidence exited 0")
    for want in ("achievement=partial", "3/4 evidenced", "availability=projected"):
        if want not in output:
            mark_fail(
                f"agent-launch receipts: partial run does not report {want!r}, so partial "
                f"and never-verified stay indistinguishable: {output[:200]}"
            )

    empty = tmp / "no-record.txt"
    empty.write_text("this text carries no plan record at all")
    status, output = run(empty, tmp / "receipts-all-valid.json")
    if status == 0 or "no ReviewPlan/v1 record" not in output:
        mark_fail("agent-launch receipts: a file with no plan record was not refused")

    # How many passes a method must evidence comes from the REGISTRY. A registry that
    # cannot be loaded therefore leaves the verifier with no bar at all, and defaulting
    # to one pass would silently drop the panel's three plus its ordering and swap
    # controls — the audited party gaining, from a config error, exactly the leniency it
    # is not allowed to declare for itself. The subject is a real migration: a descriptor
    # authored before `severity_emits` existed, otherwise valid.
    stale = launcher_module.user_methods_path(profile)
    stale.write_text(
        '[review_methods.gate-premigration]\n'
        'label = "L"\ndescription = "D"\ninstructions = "x"\noutput = "review-v1"\n'
        'severity_map = { high = "high" }\n'
    )
    lowered = tmp / "receipts-lowered-bar.json"
    lowered.write_text(json.dumps(bundle([
        receipt("panel", passes=["p1"], ordering_seed="", swap_group=""), receipt("receipt-lens"),
    ])))
    try:
        status, output = run(plan_file, lowered)
        if status == 0 or "severity_emits is required" not in output:
            mark_fail(
                "agent-launch receipts: an unloadable registry did not fail verification "
                f"— a one-pass panel receipt was adjudicated anyway: {output.strip()[:160]}"
            )
        if "does not load" not in output:
            mark_fail(
                "agent-launch receipts: the refusal did not attribute itself to the config, "
                "so a broken registry reads as a defective receipt"
            )
    finally:
        stale.unlink()

    # Same lowered bar, reached without any load error at all: a config may validly carry
    # no [review_methods], and a plan may name a method this registry never had. Either
    # way the descriptor — and with it the bar — is simply absent, which must refuse
    # adjudication rather than default to one pass.
    bare = tmp / "bare"
    bare.mkdir()
    bare_profile = bare / "profiles.toml"
    kept, dropping = [], False
    for line in profile.read_text().splitlines(keepends=True):
        if line.startswith("["):
            dropping = line.startswith("[review_methods.")
        if not dropping:
            kept.append(line)
    bare_profile.write_text("".join(kept))
    if "[review_methods." in bare_profile.read_text():
        mark_fail("agent-launch receipts: the registry-less subject still declares methods — vacuous")

    def run_bare(bundle_path):
        proc = subprocess.run(
            [sys.executable, str(launcher), "--config", str(bare_profile),
             "--verify-receipts", str(plan_file), str(bundle_path)],
            capture_output=True, text=True, env=fx.env, cwd=str(pathlib.Path.cwd()),
        )
        return proc.returncode, proc.stdout + proc.stderr

    status, output = run_bare(lowered)
    if status == 0 or "no descriptor for selected method" not in output:
        mark_fail(
            "agent-launch receipts: a config carrying no review registry adjudicated anyway "
            f"— every descriptor-owned bar defaulted away: {output.strip()[:160]}"
        )
    # And the same config must still refuse a receipt bundle that would otherwise pass, so
    # the refusal is the missing descriptor and not something the weak bundle triggered.
    status, output = run_bare(tmp / "receipts-all-valid.json")
    if status == 0 or "no descriptor for selected method" not in output:
        mark_fail(
            "agent-launch receipts: a registry-less config accepted an otherwise-valid "
            f"bundle: {output.strip()[:160]}"
        )


@launcher_check
def launcher_receipt_fold(fx):
    """Folding keeps one dispatch id per method, so every pass's id is judged before it
    disappears: a main-context pass listed after a child pass used to vanish into `passes`
    with its result credited (round 19, #2). Empty, repeated and main-context ids are each
    refused by name; a clean group folds."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    fold_packet = hashlib.sha256(b"fold-packet").hexdigest()

    def result_hash(label):
        """A REAL digest per readable label. Every `result_sha256` and every `passes` entry
        is a SHA-256 hash, and the pass count is `len(set(passes))` over distinct STRINGS —
        so this fixture's `"one"`/`"two"` evidenced two passes exactly as well as two digests
        did, and nothing here ever asked whether a purported hash was one (round 23, #3).
        A value that is already a digest is returned as itself, because the empty-result
        sentinel's cases are about what it MEANS, not about its form."""
        if launcher_module.is_sha256_hex(label):
            return label
        return hashlib.sha256(label.encode()).hexdigest()

    def receipt(dispatch, result, **extra):
        return {"schema": launcher_module.RECEIPT_SCHEMA, "method_id": "panel",
                "dispatch_id": dispatch, "packet_sha256": fold_packet,
                "result_sha256": result_hash(result),
                "provider": "openai", "model": "model-x", "effort": "high", "exit_status": 0,
                **extra}
    empty = launcher_module.EMPTY_SHA256
    for label, group, needle in (
        ("main-context pass", [receipt("child-1", "one"), receipt("main-1", "two")], "main session"),
        ("repeated dispatch id", [receipt("child-1", "one"), receipt("child-1", "two")], "repeat"),
        ("empty dispatch id", [receipt("child-1", "one"), receipt("", "two")], "no dispatch id"),
        # A group of ONE returned before any of the three above, so the lone receipt every
        # single-pass method produces was folded unexamined (round 20, #2). It is the one
        # shape carrying no `passes` for the adjudicator to re-read, so nothing else looked.
        ("singleton main-context pass", [receipt("main-1", "one")], "main session"),
        ("singleton empty result", [receipt("child-1", empty)], "empty result"),
        # Folding keeps the FIRST receipt's payload, so a later empty pass landed in
        # `passes` behind a good hash and verified. The same two receipts REVERSED were
        # refused — file order in a directory decided whether a review was achieved — so
        # both orders are asserted and neither may fold.
        ("later empty pass", [receipt("child-1", "one"), receipt("child-2", empty)], "empty result"),
        ("earlier empty pass", [receipt("child-2", empty), receipt("child-1", "one")], "empty result"),
        # A pass whose result hash is a non-empty string and no hash at all — refused apart
        # from the empty-result cases above, which are a claim about what the reviewer
        # PRODUCED rather than about the field being a digest. Both orders, because folding
        # keeps the first receipt's payload and the second pass is the one that used to
        # disappear into `passes`.
        ("later non-hash pass",
         [receipt("child-1", "one"), {**receipt("child-2", "two"), "result_sha256": "not-a-sha256"}],
         "which is not a SHA-256 hash"),
        ("earlier non-hash pass",
         [{**receipt("child-2", "two"), "result_sha256": "not-a-sha256"}, receipt("child-1", "one")],
         "which is not a SHA-256 hash"),
        ("singleton non-hash pass",
         [{**receipt("child-1", "one"), "result_sha256": "not-a-sha256"}],
         "which is not a SHA-256 hash"),
        # Same asymmetry, one field over: only the first receipt's `evidence` survives the
        # fold, so a later pass that reported nothing was invisible to the bar the offer
        # declares. The FIELDS are compared, never the values — a trace id differs per pass.
        ("later pass reporting less",
         [receipt("child-1", "one", evidence={"reached_seat": "a", "billing_mode": "b"}),
          receipt("child-2", "two", evidence={"reached_seat": "c"})],
         "different evidence fields"),
        ("earlier pass reporting less",
         [receipt("child-1", "one", evidence={"reached_seat": "c"}),
          receipt("child-2", "two", evidence={"reached_seat": "a", "billing_mode": "b"})],
         "different evidence fields"),
        # The twin the field-set comparison could not see: the key is PRESENT and empty, so
        # the sets agree and the first pass's value survived the fold — while the same
        # receipt judged alone is refused for reporting nothing (round 21, #3). Both orders,
        # for the reason the empty-result pair is in both orders.
        ("later pass reporting an empty required value",
         [receipt("child-1", "one", evidence={"reached_seat": "a"}),
          receipt("child-2", "two", evidence={"reached_seat": ""})],
         "present with an empty value"),
        ("earlier pass reporting an empty required value",
         [receipt("child-1", "one", evidence={"reached_seat": ""}),
          receipt("child-2", "two", evidence={"reached_seat": "a"})],
         "present with an empty value"),
        # Whether each pass is a ReviewReceipt/v1 record AT ALL. Per-pass validation
        # omitted the schema and the key set, and the fold keeps the FIRST receipt's, so a
        # later bogus pass contributed a credited result hash and then disappeared from the
        # record the method is judged on (round 21, #2). Both orders again: reversed, the
        # same pair was already refused, which is the asymmetry that made it invisible.
        ("later pass with a bogus schema",
         [receipt("child-1", "one"), receipt("child-2", "two", schema="NotAReceipt/v1")],
         "not a ReviewReceipt/v1 record"),
        ("earlier pass with a bogus schema",
         [receipt("child-1", "one", schema="NotAReceipt/v1"), receipt("child-2", "two")],
         "not a ReviewReceipt/v1 record"),
        ("later pass carrying an unknown key",
         [receipt("child-1", "one"), receipt("child-2", "two", smuggled="x")],
         "unknown receipt key(s): smuggled"),
        ("pass that is not a table", [receipt("child-1", "one"), "not-a-receipt"],
         "not a table"),
        # The PANEL CONTROLS, which the fold copied from the first receipt alone. A pair
        # where one pass carries the ordering seed and the other does not folded to
        # whichever was read first, so the identical two receipts verified in one order and
        # were refused in the other (round 22, #2). Both orders, for the reason the empty
        # pass is in both orders — the asymmetry is the defect.
        ("later pass omitting the ordering seed",
         [receipt("child-1", "one", ordering_seed="seed"), receipt("child-2", "two")],
         "disagree on whether ordering_seed was reported"),
        ("earlier pass omitting the ordering seed",
         [receipt("child-1", "one"), receipt("child-2", "two", ordering_seed="seed")],
         "disagree on whether ordering_seed was reported"),
        ("later pass omitting the swap group",
         [receipt("child-1", "one", swap_group="swap"), receipt("child-2", "two")],
         "disagree on whether swap_group was reported"),
        ("earlier pass omitting the swap group",
         [receipt("child-1", "one"), receipt("child-2", "two", swap_group="swap")],
         "disagree on whether swap_group was reported"),
        # The same absence wearing the key: an empty value is not a report, measured the
        # way `_receipt_reason` measures it, or the fold and the adjudicator would disagree
        # about what carrying a seed means.
        ("later pass carrying an empty ordering seed",
         [receipt("child-1", "one", ordering_seed="seed"),
          receipt("child-2", "two", ordering_seed="")],
         "disagree on whether ordering_seed was reported"),
        # …and the pair the door above CANNOT tell apart, because an empty value and an
        # absent key are one state to it. The fold does not only judge — it emits, keeping
        # the representative's key set verbatim — so a pass carrying the key empty and one
        # omitting it folded clean to a record whose key set was decided by which pass
        # sorted first (spec round 4, #2). Its own needle: a case reading the reportedness
        # door's message would stop testing the moment that door is what fires. Both
        # orders, and the swap twin, for the reason every pair here is in both orders.
        ("later pass omitting a key an earlier pass carries empty",
         [receipt("child-1", "one", ordering_seed=""), receipt("child-2", "two")],
         "disagree on whether ordering_seed is present at all"),
        ("earlier pass omitting a key a later pass carries empty",
         [receipt("child-1", "one"), receipt("child-2", "two", ordering_seed="")],
         "disagree on whether ordering_seed is present at all"),
        ("swap group carried empty by one pass and omitted by the other",
         [receipt("child-1", "one", swap_group=""), receipt("child-2", "two")],
         "disagree on whether swap_group is present at all"),
        # A boolean exit status, which `!= 0` credits as success — asked of every PASS as
        # well as of the adjudicated record, because the fold keeps the first receipt's
        # (round 22, #3). The fixtures here all used integer 0, so the type was never asked.
        ("later pass with a boolean exit status",
         [receipt("child-1", "one"), receipt("child-2", "two", exit_status=False)],
         "records exit_status as bool"),
        # A RAW receipt carrying `passes`. That field is written BY the fold — it is where
        # "three processes ran" becomes "three passes are evidenced" — and a lone receipt
        # holding one went through the singleton return unchanged, so a single dispatch
        # declared the pass count it would then be judged by (spec round, #2). The singleton
        # first, because that is the shape the defect needed; and in both positions of a
        # pair, because the fold keeps one receipt's payload and the other is the one that
        # used to disappear.
        ("singleton carrying a pass list",
         [receipt("child-1", "one", passes=[result_hash("one"), result_hash("two")])],
         "carries a pass list before anything was folded"),
        ("later pass carrying a pass list",
         [receipt("child-1", "one"),
          receipt("child-2", "two", passes=[result_hash("two"), result_hash("three")])],
         "carries a pass list before anything was folded"),
        ("earlier pass carrying a pass list",
         [receipt("child-1", "one", passes=[result_hash("one"), result_hash("three")]),
          receipt("child-2", "two")],
         "carries a pass list before anything was folded"),
        # A raw receipt naming no method. The public fold refuses this while GROUPING, so
        # the merge seam never sees it from there — but the seam is called directly too
        # (check_adapter, and any future orchestration), and a pass belonging to no method
        # is nobody's pass wherever it arrives (spec round, #13). Its own message, so the
        # two doors are told apart.
        ("pass naming no method",
         [receipt("child-1", "one"), {**receipt("child-2", "two"), "method_id": ""}],
         "names no method"),
    ):
        try:
            launcher_module._merge_method_passes("panel", group, "main-1")
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(f"agent-launch fold refused a {label} for another reason: {exc}")
        except Exception as exc:  # a raw AttributeError here aborts the run and names nothing
            mark_fail(
                f"agent-launch fold raised {type(exc).__name__} on a {label} instead of "
                f"naming it: {exc}"
            )
        else:
            mark_fail(
                f"agent-launch fold accepted a {label}; a pass no check saw went into the "
                f"single record the method is judged on"
            )
    try:
        merged = launcher_module._merge_method_passes(
            "panel", [receipt("child-1", "one"), receipt("child-2", "two")], "main-1")
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch fold refused a clean two-pass group: {exc}")
    else:
        if merged.get("passes") != sorted({result_hash("one"), result_hash("two")}):
            mark_fail(f"agent-launch fold of a clean group lost a pass: {merged.get('passes')}")
    # The positive control the empty-value cases need: a fold that refused every group
    # carrying evidence at all would satisfy both of them and pass. Two passes reporting
    # the SAME field with DIFFERENT values still fold — the values were never the subject,
    # since a trace id differs per pass by construction.
    try:
        evidenced = launcher_module._merge_method_passes(
            "panel",
            [receipt("child-1", "one", evidence={"reached_seat": "a"}),
             receipt("child-2", "two", evidence={"reached_seat": "b"})],
            "main-1",
        )
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch fold refused two passes that each reported the declared field "
            f"with a value: {exc} — the empty-value cases above then prove nothing"
        )
    else:
        if evidenced.get("passes") != sorted({result_hash("one"), result_hash("two")}):
            mark_fail(f"agent-launch fold of an evidenced group lost a pass: {evidenced.get('passes')}")
    # The positive control the singleton cases need: a fold that refused every lone receipt
    # would satisfy all of them and pass. One clean child receipt still folds, and folding
    # it EVIDENCES it: `passes` is the fold's whole output — where "one process ran" becomes
    # "one pass is evidenced" — and the lone receipt was returned as it arrived, so the one
    # record the method is judged on carried no pass set at all (spec round 6, F3). This
    # control accepted that: it asked only for the dispatch id and the primary digest, both
    # of which an untouched receipt has by construction, so it could not tell a folded
    # record from an unfolded one. The pass set is asserted by VALUE — `passes` merely
    # being present is satisfied by any list, and the one thing a one-pass fold means is
    # that the set is exactly the receipt's own result.
    lone_result = result_hash("one")
    try:
        alone = launcher_module._merge_method_passes("panel", [receipt("child-9", "one")], "main-1")
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch fold refused a clean single-pass receipt: {exc}")
    else:
        if alone.get("dispatch_id") != "child-9" or alone.get("result_sha256") != lone_result:
            mark_fail(f"agent-launch fold altered a clean single-pass receipt: {alone!r}")
        elif alone.get("passes") != [lone_result]:
            mark_fail(
                f"agent-launch fold of a lone pass omits its pass set: passes="
                f"{alone.get('passes')!r}, want {[lone_result]!r} — the folded record is "
                f"what the adjudicator reads passes off, and a singleton that skips the "
                f"merge evidences no pass at all"
            )
    # And the property the empty-pass pair is really about: the same receipts in either
    # order reach the same verdict. Asserted as an equality over outcomes rather than as two
    # separate expectations, because the defect was precisely that the two disagreed.
    def fold_outcome(group):
        try:
            return ("folded", launcher_module._merge_method_passes("panel", group, "main-1")["result_sha256"])
        except launcher_module.LaunchError as exc:
            return ("refused", str(exc))
    pair = [receipt("child-1", "one"), receipt("child-2", empty)]
    if fold_outcome(pair) != fold_outcome(list(reversed(pair))):
        mark_fail(
            "agent-launch fold: the same two receipts in the other order reach a different "
            "verdict — which pass is judged depends on which file was read first"
        )
    # The same property over the CONTROL fields, which is where the order-invariance
    # assertion above was empty: it covered the empty-result pair only, and `ordering_seed`
    # and `swap_group` were copied from `group[0]` with nothing comparing them, so the
    # reversed pair folded to a record carrying no seed and lost the review (round 22, #2).
    marked = [receipt("child-1", "one", ordering_seed="seed", swap_group="swap"),
              receipt("child-2", "two")]
    if fold_outcome(marked) != fold_outcome(list(reversed(marked))):
        mark_fail(
            "agent-launch fold: a pass carrying the panel controls and one without them "
            "reach a different verdict when the pair is reversed — the folded record's "
            "controls are whichever receipt happened to be first"
        )
    # And the positive control both need: passes that AGREE on carrying the controls still
    # fold, keeping them. A fold that refused every group mentioning a seed would satisfy
    # every case above, and the values are deliberately different — a swap group names
    # WHICH arm a pass ran, so equal values were never the bar.
    try:
        controlled = launcher_module._merge_method_passes(
            "panel",
            [receipt("child-1", "one", ordering_seed="seed", swap_group="a"),
             receipt("child-2", "two", ordering_seed="seed", swap_group="b")],
            "main-1",
        )
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch fold refused two passes that each reported the panel controls: "
            f"{exc} — the omission cases above then prove nothing"
        )
    else:
        if (controlled.get("ordering_seed") != "seed"
                or controlled.get("passes") != sorted({result_hash("one"), result_hash("two")})):
            mark_fail(
                f"agent-launch fold dropped the controls of an agreeing group: {controlled!r}"
            )
    # The order-invariance assertions above compare a REFUSAL against a refusal, or one
    # field of a folded record. What they never asked is whether a group that folds CLEANLY
    # folds to the same record: the merged record keeps one receipt's identity and payload,
    # that receipt was `group[0]`, and reversing two valid passes produced a different
    # dispatch id, a different primary result and different evidence values — the record a
    # method is judged on decided by the order a directory was read in (spec round, #11).
    # Whole-content equality, which is the finding's own measure, over a pair that differs
    # in every field folding copies.
    clean_pair = [
        receipt("child-a", "one", evidence={"reached_seat": "a"},
                ordering_seed="seed-a", swap_group="arm-a"),
        receipt("child-b", "two", evidence={"reached_seat": "b"},
                ordering_seed="seed-b", swap_group="arm-b"),
    ]
    forward = launcher_module._merge_method_passes("panel", clean_pair, "main-1")
    reverse = launcher_module._merge_method_passes(
        "panel", list(reversed(clean_pair)), "main-1")
    if forward != reverse:
        mark_fail(
            "agent-launch fold: two clean passes fold to different records when the pair is "
            f"reversed — the folded identity is whichever receipt was read first "
            f"({forward.get('dispatch_id')!r}/{forward.get('result_sha256', '')[:8]} vs "
            f"{reverse.get('dispatch_id')!r}/{reverse.get('result_sha256', '')[:8]})"
        )
    if forward.get("dispatch_id") not in {"child-a", "child-b"}:
        mark_fail(
            f"agent-launch fold: the folded record's identity is not one of the passes' "
            f"({forward.get('dispatch_id')!r}) — the representative must be a receipt, not "
            f"something invented"
        )
    # …and the property that makes the equality above non-vacuous: the pair really does
    # differ in the fields folding copies, so a fold returning either one is a real choice.
    if clean_pair[0] == clean_pair[1]:
        mark_fail("agent-launch fold: the order-invariance pair is identical — vacuous")
    # The same property where a FAILED pass decides the merged exit status, which is the
    # other value folding takes from one receipt.
    failing_pair = [
        receipt("child-a", "one", exit_status=3),
        receipt("child-b", "two", exit_status=4),
    ]
    if (launcher_module._merge_method_passes("panel", failing_pair, "main-1")
            != launcher_module._merge_method_passes(
                "panel", list(reversed(failing_pair)), "main-1")):
        mark_fail(
            "agent-launch fold: two failed passes propagate a different exit status when "
            "the pair is reversed — which failure the record reports depends on file order"
        )
    # …and the other half of that control: when NO pass reports one, the fold stays silent
    # and the descriptor-aware adjudicator decides, which is the behaviour D-20260816-c0067f
    # and D-20260816-0ed011 deliberately keep.
    try:
        silent = launcher_module._merge_method_passes(
            "panel", [receipt("child-1", "one"), receipt("child-2", "two")], "main-1")
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch fold refused a group in which no pass reports controls: {exc}")
    else:
        if "ordering_seed" in silent or "swap_group" in silent:
            mark_fail(
                f"agent-launch fold invented panel controls no pass reported: {silent!r}"
            )
    # The positive control the key-presence cases need: a UNIFORM falsey extra still folds,
    # and the merged record still wears the key. Every pass agrees about the key, and a bar
    # on an extra marker is a bar no descriptor wrote — the reading D6 was amended to state
    # (spec round 3). Without this, a fold refusing every empty marker would satisfy all
    # three key-presence cases above and pass.
    try:
        uniform = launcher_module._merge_method_passes(
            "panel",
            [receipt("child-1", "one", ordering_seed=""),
             receipt("child-2", "two", ordering_seed="")],
            "main-1",
        )
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"agent-launch fold refused two passes that AGREE on carrying an empty ordering "
            f"seed: {exc} — the key-presence cases above then only prove the fold refuses "
            f"every empty marker"
        )
    else:
        if "ordering_seed" not in uniform or uniform.get("ordering_seed") != "":
            mark_fail(
                f"agent-launch fold rewrote a key every pass agreed on: {uniform!r} — the "
                f"merged record carries what the passes carried, and dropping a uniform "
                f"field is the fold deciding a bar the descriptor owns"
            )


@launcher_check
def launcher_receipt_adapters(fx):
    """The PRODUCER side: `--emit-receipt`, `--fold-receipts`, `--check-adapter`.

    Everything `launcher_receipts` covers is adjudication, and adjudication had no
    counterpart — the only party able to write a receipt was whoever ran the review, so
    the audited party wrote its own audit record. These checks cover the other end.

    A stub adapter, not a real one: what is under test is the calling convention and the
    folding rule, and a live dispatch would put a model's availability inside a gate.
    The stub is the one a third-party author would write, so passing it is the claim
    being made — that binding to the contract needs nothing but calling the emitter."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    tmp = pathlib.Path(tempfile.mkdtemp())
    seat = "openai:gpt-5.6-sol/xhigh"

    def stub(name, *, seat_reported=seat, receipts=1, blank_result=False):
        """An adapter that reads a packet on stdin, answers on stdout, and reports."""
        path = tmp / f"adapter-{name}.sh"
        path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'packet=$(mktemp); result=$(mktemp)\n'
            "cat > \"$packet\"\n"
            + ("printf '' | tee \"$result\"\n" if blank_result
               else "printf 'REVIEW %s: no findings\\n' \"$$\" | tee \"$result\"\n")
            + "".join(
                f'"{sys.executable}" "{launcher.resolve()}" --emit-receipt '
                f'"${{REVIEW_METHOD_ID:-}}" "{seat_reported}" 0 "$packet" "$result" '
                f'>/dev/null\n'
                for _ in range(receipts)
            )
        )
        path.chmod(0o755)
        return path

    def run(*args, env=None):
        proc = subprocess.run(
            [sys.executable, str(launcher), *args],
            capture_output=True, text=True, cwd=str(pathlib.Path.cwd()),
            env={**fx.env, **(env or {})},
        )
        return proc.returncode, proc.stdout + proc.stderr

    # ── --check-adapter. The positive control comes first and is load-bearing: a
    # checker that rejected every adapter would satisfy all the negatives below.
    conformance = [
        ("conforming", stub("good"), 0, "ACHIEVED"),
        ("writes-nothing", stub("silent", receipts=0), 1, "wrote no receipt"),
        ("two-receipts", stub("double", receipts=2), 1, "one dispatch is one receipt"),
        ("wrong-seat", stub("liar", seat_reported="openai:other-model/xhigh"), 1,
         "where the plan projected"),
        ("empty-result", stub("mute", blank_result=True), 1, "empty result"),
    ]
    if not any(expected == 0 for _, _, expected, _ in conformance):
        mark_fail("agent-launch adapters: no conformance scenario expects success — the "
                  "checker could reject every adapter and pass")
    for name, adapter, expected_status, expected_text in conformance:
        status, output = run("--check-adapter", seat, str(adapter))
        if (status == 0) != (expected_status == 0):
            mark_fail(
                f"agent-launch adapters: --check-adapter {name} exited {status}, expected "
                f"{'0' if expected_status == 0 else 'non-zero'}: {output.strip()[:200]}"
            )
        elif expected_text not in output:
            mark_fail(
                f"agent-launch adapters: --check-adapter {name} did not name its outcome "
                f"({expected_text!r}): {output.strip()[:200]}"
            )

    # The separator anyone reaches for when the adapter command carries its own flags.
    # argparse eats a bare `--` before the REMAINDER sees it, so without normalisation the
    # command landed on the host positional and the error talked about hosts.
    status, output = run("--check-adapter", seat, "--", str(stub("separated")))
    if status != 0 or "ACHIEVED" not in output:
        mark_fail(
            "agent-launch adapters: --check-adapter SEAT -- CMD did not reach the adapter: "
            f"{output.strip()[:160]}"
        )

    # ── --emit-receipt refuses to write where nothing asked it to. Absent destination is
    # how every caller behaves today, so this is the branch that keeps the mechanism inert.
    status, output = run("--emit-receipt", "panel", seat, "0", str(launcher), str(launcher))
    if status == 0 or "nowhere to write a receipt" not in output:
        mark_fail(
            "agent-launch adapters: --emit-receipt wrote a receipt with no "
            f"{launcher_module.RECEIPT_DIR_ENV}: {output.strip()[:160]}"
        )

    # ── --fold-receipts. N per-dispatch receipts become one method record carrying
    # `passes`, and that is what makes a multi-pass method adjudicable at all.
    packet = tmp / "packet.txt"
    packet.write_text("the review packet\n")

    def dispatch(directory, adapter, method_id="panel", **env):
        directory.mkdir(parents=True, exist_ok=True)
        with packet.open("rb") as handle:
            subprocess.run(
                [str(adapter)], stdin=handle, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, cwd=str(pathlib.Path.cwd()),
                env={**fx.env, launcher_module.RECEIPT_DIR_ENV: str(directory),
                     launcher_module.RECEIPT_METHOD_ENV: method_id, **env},
            )

    def fold(directory):
        return run("--fold-receipts", str(directory), str(packet), "a-main-dispatch-id")

    passes_dir = tmp / "passes"
    for _ in range(3):
        dispatch(passes_dir, stub("pass"))
    status, output = fold(passes_dir)
    if status != 0:
        mark_fail(f"agent-launch adapters: folding three passes failed: {output.strip()[:160]}")
    else:
        folded = json.loads(output)
        merged = folded["receipts"]
        if len(merged) != 1:
            mark_fail(
                f"agent-launch adapters: three passes of one method folded to "
                f"{len(merged)} records, not one — the method is judged on a single receipt"
            )
        elif len({p for p in merged[0].get("passes", []) if p}) != 3:
            mark_fail(
                "agent-launch adapters: the folded receipt does not evidence three distinct "
                f"passes: {merged[0].get('passes')!r}"
            )

    # Identical output across passes billed as isolated collapses the distinct set — the
    # reason `passes` carries result hashes and not the ids, which are distinct for free.
    same_dir = tmp / "identical"
    identical = tmp / "adapter-identical.sh"
    identical.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'packet=$(mktemp); result=$(mktemp)\n'
        'cat > "$packet"\n'
        "printf 'the same answer every time\\n' | tee \"$result\"\n"
        f'"{sys.executable}" "{launcher.resolve()}" --emit-receipt "${{REVIEW_METHOD_ID:-}}" '
        f'"{seat}" 0 "$packet" "$result" >/dev/null\n'
    )
    identical.chmod(0o755)
    for _ in range(3):
        dispatch(same_dir, identical)
    status, output = fold(same_dir)
    if status != 0:
        mark_fail(f"agent-launch adapters: folding identical passes failed: {output.strip()[:160]}")
    else:
        distinct = json.loads(output)["receipts"][0].get("passes", [])
        if len({p for p in distinct if p}) != 1:
            mark_fail(
                "agent-launch adapters: three byte-identical passes did not collapse to one "
                f"distinct pass, so the isolation control is not looking at output: {distinct!r}"
            )

    # Receipts that disagree on the seat are not one method's passes, and merging them
    # would invent a set that never ran.
    mixed_dir = tmp / "mixed"
    dispatch(mixed_dir, stub("seat-a"))
    dispatch(mixed_dir, stub("seat-b", seat_reported="openai:another-model/xhigh"))
    status, output = fold(mixed_dir)
    if status == 0 or "disagree on model" not in output:
        mark_fail(
            "agent-launch adapters: receipts disagreeing on the seat folded into one "
            f"method's passes: {output.strip()[:160]}"
        )

    # An empty directory folds to a bundle that satisfies everything vacuously.
    empty_dir = tmp / "empty"
    empty_dir.mkdir()
    status, output = fold(empty_dir)
    if status == 0 or "evidences nothing" not in output:
        mark_fail(
            f"agent-launch adapters: an empty receipt directory folded anyway: "
            f"{output.strip()[:160]}"
        )

    # A receipt naming no method, at the PUBLIC fold boundary. The grouping asked only
    # whether `method_id` was a string, so `""` became a group key and a bundle was emitted
    # for a method no plan can ever select (spec round, #13). Written by hand rather than
    # emitted, because the emitter is handed the name by the orchestrator and the artifact
    # this reads is a directory anyone can write into.
    nameless_dir = tmp / "nameless"
    nameless_dir.mkdir(parents=True, exist_ok=True)
    nameless_receipt = {
        "schema": launcher_module.RECEIPT_SCHEMA, "method_id": "",
        "dispatch_id": "child-nameless",
        "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "result_sha256": hashlib.sha256(b"nameless-result").hexdigest(),
        "provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh", "exit_status": 0,
    }
    (nameless_dir / "one.json").write_text(json.dumps(nameless_receipt))
    status, output = fold(nameless_dir)
    if status == 0 or "names no method" not in output:
        mark_fail(
            f"agent-launch adapters: a receipt whose method_id is empty folded into a "
            f"bundle anyway (rc={status}): {output.strip()[:200]}"
        )
    # The positive control: the same receipt with a name folds. Without it the case above
    # is satisfied by a fold that refuses every hand-written receipt.
    named_dir = tmp / "named"
    named_dir.mkdir(parents=True, exist_ok=True)
    (named_dir / "one.json").write_text(json.dumps({**nameless_receipt, "method_id": "panel"}))
    status, output = fold(named_dir)
    if status != 0 or '"method_id": "panel"' not in output:
        mark_fail(
            f"agent-launch adapters: the same receipt WITH a method name did not fold "
            f"(rc={status}), so the empty-name case proves nothing: {output.strip()[:200]}"
        )

    # TWO METHODS, ONE DISPATCH ID. `_merge_method_passes` takes a fresh `seen_ids` per
    # method, so uniqueness was only ever asked inside one method's passes: a directory
    # holding two receipts that name different methods and share an id folded clean, and
    # the emitted bundle carried the same dispatch id twice (spec round 2, #3). The
    # adjudicator does refuse that reuse — but only after this command has declared the
    # bundle canonical, and the fold is the phase where every raw id is still visible.
    # Written by hand, because the emitter owns the id and cannot produce this.
    shared_dir = tmp / "shared-dispatch"
    shared_dir.mkdir(parents=True, exist_ok=True)
    def raw_receipt(method_id, dispatch_id, result):
        return {
            "schema": launcher_module.RECEIPT_SCHEMA, "method_id": method_id,
            "dispatch_id": dispatch_id,
            "packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
            "result_sha256": hashlib.sha256(result).hexdigest(),
            "provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh",
            "exit_status": 0,
        }
    (shared_dir / "alpha.json").write_text(
        json.dumps(raw_receipt("alpha", "one-dispatch", b"alpha-result")))
    (shared_dir / "beta.json").write_text(
        json.dumps(raw_receipt("beta", "one-dispatch", b"beta-result")))
    status, output = fold(shared_dir)
    if status == 0 or "share the dispatch id" not in output:
        mark_fail(
            f"agent-launch adapters: two receipts naming different methods and sharing one "
            f"dispatch id folded into a bundle anyway (rc={status}) — one process is one "
            f"dispatch and one receipt, and the fold is where every raw id is still "
            f"visible: {output.strip()[:200]}"
        )
    # The positive control: the same two receipts with DISTINCT ids fold, and the bundle
    # carries both methods. Without it the case above is satisfied by a fold that refuses
    # every two-method directory.
    distinct_dir = tmp / "distinct-dispatch"
    distinct_dir.mkdir(parents=True, exist_ok=True)
    (distinct_dir / "alpha.json").write_text(
        json.dumps(raw_receipt("alpha", "alpha-dispatch", b"alpha-result")))
    (distinct_dir / "beta.json").write_text(
        json.dumps(raw_receipt("beta", "beta-dispatch", b"beta-result")))
    status, output = fold(distinct_dir)
    if status != 0:
        mark_fail(
            f"agent-launch adapters: two methods with distinct dispatch ids did not fold "
            f"(rc={status}), so the shared-id case proves nothing: {output.strip()[:200]}"
        )
    else:
        ids = [r.get("dispatch_id") for r in json.loads(output)["receipts"]]
        if sorted(ids) != ["alpha-dispatch", "beta-dispatch"]:
            mark_fail(
                f"agent-launch adapters: the two-method fold emitted {ids!r} rather than one "
                f"record per method"
            )

    # ── --emit-receipt publishes complete bytes or none. `write_text` creates the final
    # name and then fills it, so a reader — and the fold globs exactly this directory —
    # could observe a truncated record, and a failed write left that truncation behind as
    # the receipt for the dispatch (spec round, #6). Proved from the OUTSIDE, on the real
    # filesystem: the emitter is asked to write into a path it cannot create the final file
    # at, and the directory afterwards must hold no `*.json` at all.
    #
    # The mechanism is a same-directory temporary plus an atomic rename, so the observable
    # is what a concurrent reader could glob. A partial `.json` and a leftover temporary are
    # different failures and both are asserted.
    blocked_dir = tmp / "atomic"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    # A directory sitting where the receipt file must go: os.replace onto a directory
    # fails after the temporary is complete, which is exactly the window the fix owns.
    emitted = subprocess.run(
        [sys.executable, str(launcher), "--emit-receipt", "panel", seat, "0",
         str(packet), str(packet)],
        capture_output=True, text=True, cwd=str(pathlib.Path.cwd()),
        env={**fx.env, launcher_module.RECEIPT_DIR_ENV: str(blocked_dir)},
    )
    if emitted.returncode != 0:
        mark_fail(
            f"agent-launch adapters: --emit-receipt failed on a writable directory: "
            f"{(emitted.stdout + emitted.stderr).strip()[:200]}"
        )
    else:
        written_paths = sorted(blocked_dir.iterdir())
        leftovers = [p for p in written_paths if p.name.endswith(".tmp")]
        if leftovers:
            mark_fail(
                f"agent-launch adapters: --emit-receipt left a temporary behind: "
                f"{[p.name for p in leftovers]!r}"
            )
        if len(written_paths) != 1 or not written_paths[0].name.endswith(".json"):
            mark_fail(
                f"agent-launch adapters: --emit-receipt wrote {[p.name for p in written_paths]!r}, "
                f"not one receipt"
            )
        else:
            # The published file is COMPLETE — parseable and carrying the dispatch id its
            # own name is made of, which is what a concurrent glob would have to see.
            try:
                published = json.loads(written_paths[0].read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                mark_fail(f"agent-launch adapters: the published receipt is not JSON: {exc}")
            else:
                if published.get("dispatch_id") != written_paths[0].stem:
                    mark_fail(
                        f"agent-launch adapters: the published receipt names "
                        f"{published.get('dispatch_id')!r} and the file is "
                        f"{written_paths[0].name!r} — the atomic publish moved the wrong file"
                    )
    # The failure path, injected at the PUBLISH step — the only place the two designs
    # differ. A blocked destination is no discriminator: writing straight to the final name
    # and writing a temporary both fail at open, leaving nothing either way. `os.replace`
    # made to raise is the discriminator, because an emitter that publishes by writing the
    # final name directly never calls it and simply SUCCEEDS. Afterwards the directory must
    # hold no receipt at all and no temporary: those are the bytes a reader globbing this
    # directory would otherwise find and take for a dispatch that never published.
    failing_dir = tmp / "atomic-blocked"
    failing_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        [sys.executable, "-c",
         "import runpy, os, sys\n"
         f"m = runpy.run_path({str(launcher.resolve())!r})\n"
         "def _no_publish(*args, **kwargs):\n"
         "    raise OSError('injected publish failure')\n"
         "m['os'].replace = _no_publish\n"
         f"os.environ[m['RECEIPT_DIR_ENV']] = {str(failing_dir)!r}\n"
         "try:\n"
         f"    m['emit_receipt_command']('panel', {seat!r}, '0', {str(packet)!r}, {str(packet)!r})\n"
         "except m['LaunchError'] as exc:\n"
         "    print('refused: ' + str(exc))\n"
         "    sys.exit(1)\n"
         "print('emitted anyway')\n"],
        capture_output=True, text=True, cwd=str(pathlib.Path.cwd()), env=fx.env,
    )
    probe_output = probe.stdout + probe.stderr
    if probe.returncode == 0 or "refused:" not in probe_output:
        mark_fail(
            f"agent-launch adapters: an emission whose publish step fails did not refuse "
            f"(rc={probe.returncode}) — the bytes reached their final name without being "
            f"published: {probe_output.strip()[:200]}"
        )
    published_anyway = sorted(p.name for p in failing_dir.glob("*.json"))
    if published_anyway:
        mark_fail(
            f"agent-launch adapters: an emission whose publish step failed still left a "
            f"receipt behind: {published_anyway!r}"
        )
    strays = sorted(p.name for p in failing_dir.iterdir() if p.name.endswith(".tmp"))
    if strays:
        mark_fail(
            f"agent-launch adapters: a failed emission left its temporary behind: {strays!r} "
            "— a reader globbing this directory finds bytes no dispatch published"
        )

    # The panel controls reach the receipt from the ORCHESTRATOR's environment, so an
    # adapter that never heard of them still produces an adjudicable record.
    controlled = tmp / "controlled"
    dispatch(controlled, stub("controlled"),
             REVIEW_ORDERING_SEED="seed-9", REVIEW_SWAP_GROUP="group-z")
    status, output = fold(controlled)
    if status != 0:
        mark_fail(f"agent-launch adapters: folding controls failed: {output.strip()[:160]}")
    else:
        record = json.loads(output)["receipts"][0]
        if record.get("ordering_seed") != "seed-9" or record.get("swap_group") != "group-z":
            mark_fail(
                "agent-launch adapters: the orchestrator's panel controls did not reach the "
                f"receipt: {record.get('ordering_seed')!r}/{record.get('swap_group')!r}"
            )


@launcher_check
def launcher_review_editor(fx):
    """Stage 6's editor: authoring is the opt-in, and nothing else is.

    Driven through the real menu path with only the terminal read stubbed, because the
    properties worth asserting are what the user is SHOWN and what backing out leaves
    behind — neither of which a direct call to the mutator would exercise."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    def drive(plan, config, script):
        fed, seen = list(script), io.StringIO()

        def fake_input(prompt):
            seen.write(prompt)
            if not fed:
                raise AssertionError(f"editor asked for unscripted input: {prompt!r}")
            value = fed.pop(0)
            seen.write(value + "\n")
            return value

        original = launcher_module.read_input
        launcher_module.read_input = fake_input
        try:
            with contextlib.redirect_stdout(seen):
                try:
                    launcher_module.review_editor(plan, config, None, launch_profile_path)
                except launcher_module.BackRequested:
                    pass  # the cancel path; it must leave the plan untouched
        finally:
            launcher_module.read_input = original
        return seen.getvalue(), fed

    try:
        config = launcher_module.load_config(launch_profile_path)
    except Exception as exc:
        mark_fail(f"agent-launch review editor: setup failed: {exc}")
        return

    # The landing seat must also be a seat that can RUN the method. Independence is what
    # the provider screen sells, and preferring it into a host the capability does not
    # offer is how pressing enter authored a DROPPED row for the very reviewer being
    # added — on BOTH mains once each family had its own host-bound workflow tool.
    registry = launcher_module.load_review_methods(config)
    host_bound = {
        mid: method for mid, method in registry.items()
        if launcher_module.method_servable_hosts(method, config) is not None
    }
    if not host_bound:
        mark_fail("agent-launch has no capability-backed review method — the seat check is vacuous")
    dropped_without_the_constraint = 0
    for host in ("claude", "codex"):
        main_provider = config["hosts"][host]["provider"]
        for mid, method in host_bound.items():
            options = launcher_module.review_provider_options(config, main_provider, method)
            enabled = [option for option in options if option.enabled]
            if not enabled:
                mark_fail(f"agent-launch offers no seat for {mid!r} on a {host} main")
                continue
            landing = launcher_module.review_landing_provider(options, main_provider)
            binding = launcher_module.parse_review_binding(
                {"provider": landing, "tier": "helm"}, config, f"gate.{mid}"
            )
            try:
                launcher_module.derive_review_mechanism(method, binding, config)
            except launcher_module.LaunchError as exc:
                mark_fail(
                    f"agent-launch lands the {mid!r} seat on {landing!r} for a {host} main, "
                    f"which cannot run it: {exc}"
                )
            # The control, in the same loop over the same inputs: the OLD default ignored
            # what the method can run, so it has to drop somewhere. If it never does, the
            # assertion above passed for a reason other than the constraint.
            old = next(
                (option.value for option in options if option.value != main_provider),
                options[0].value,
            )
            old_binding = launcher_module.parse_review_binding(
                {"provider": old, "tier": "helm"}, config, f"gate.{mid}.control"
            )
            try:
                launcher_module.derive_review_mechanism(method, old_binding, config)
            except launcher_module.LaunchError:
                dropped_without_the_constraint += 1
    if not dropped_without_the_constraint:
        mark_fail(
            "agent-launch seat control is vacuous: the unconstrained default drops nothing, "
            "so nothing proves the constraint is what makes the landing seat resolve"
        )

    # And the opposite over-restriction, which is the way every fix in this effort went
    # wrong: a method the host does NOT decide must keep every family selectable. The
    # base panel needs no tool, and a capability offering both hosts is a real
    # cross-family choice the editor must not take away.
    for main_provider in ("anthropic", "openai"):
        base_options = launcher_module.review_provider_options(config, main_provider)
        if not all(option.enabled for option in base_options):
            mark_fail(
                f"agent-launch disabled a provider for the base panel on {main_provider}, "
                "which needs no capability and seats anywhere"
            )
        # "Offered on more than one host" is NOT "offered on every host this profile can
        # seat" — the two coincide only while exactly two hosts exist. Taking the first
        # for the second made this assertion FAIL the moment a third host appeared, on a
        # runtime that was behaving correctly: `onto` serves two of three, the third is
        # rightly disabled, and the gate called that an over-restriction.
        seatable = launcher_module.seatable_hosts(config)
        # A SYNTHETIC every-host method, because both shipped reviewers are host-bound
        # now — the rule under test is core's, not any shipped descriptor's.
        wide_config = copy.deepcopy(config)
        wide_config["capabilities"]["gate-widekit"] = {
            "command": "gate-widekit",
            "offers": [{
                "operation": "wide-review", "adapter": "exec-stdio-v1",
                "hosts": sorted(seatable),
            }],
        }
        wide_method = launcher_module.parse_review_method(
            "gate-wide-lens",
            {
                "label": "L", "description": "D", "capability": "gate-widekit",
                "operation": "wide-review", "instructions": "run {command}",
                "output": "review-v1", "perspectives": ["refutation"], "trials": 1,
                "severity_emits": ["blocker", "high", "medium", "low", "info"],
                "severity_map": {
                    "blocker": "blocker", "high": "high", "medium": "medium",
                    "low": "low", "info": "info",
                },
            },
            "gate",
        )
        unrestricted = [
            method for method in (*host_bound.values(), wide_method)
            if seatable <= (
                launcher_module.method_servable_hosts(method, wide_config) or set()
            )
        ]
        if not unrestricted:
            mark_fail("agent-launch has no fully-offered review method — the widening check is vacuous")
        for method in unrestricted:
            wide_options = launcher_module.review_provider_options(
                wide_config, main_provider, method
            )
            # `all([])` is vacuously true, so an empty option list must fail on its
            # own before enabled-ness means anything.
            if not wide_options:
                mark_fail(
                    f"agent-launch offered no provider options for fully-offered "
                    f"{method.method_id!r} on {main_provider} — the widening check is vacuous"
                )
            if not all(option.enabled for option in wide_options):
                mark_fail(
                    f"agent-launch disabled a provider for {method.method_id!r}, which its "
                    "capability offers on every configured host"
                )

    # The editor must not offer what the READER would reject. A configured host with a
    # provider but no effort vocabulary cannot have a binding validated, so it is not a
    # seat — and nothing asserted that: deleting the `HOST_EFFORTS` half of
    # `seatable_hosts` left this whole gate green while the menu started offering a
    # provider whose binding `parse_review_binding` refuses by name.
    effortless = copy.deepcopy(config)
    effortless["hosts"]["gate-effortless"] = {
        **copy.deepcopy(config["hosts"]["claude"]), "provider": "gate-effortless-vendor",
    }
    if "gate-effortless" in launcher_module.HOST_EFFORTS:
        mark_fail("agent-launch effort-vocabulary probe collides with a real host — vacuous")
    else:
        if "gate-effortless" in launcher_module.seatable_hosts(effortless):
            mark_fail(
                "agent-launch calls a host with no effort vocabulary seatable; a binding "
                "there cannot be validated"
            )
        # The other half of the same rule, droppable on its own and equally unasserted: a
        # host with no provider has no family to grade independence against, and losing
        # that clause turned exclusion into a `KeyError: 'provider'` inside the menu.
        providerless = copy.deepcopy(config)
        providerless["hosts"]["gate-providerless"] = {
            key: value for key, value in copy.deepcopy(config["hosts"]["claude"]).items()
            if key != "provider"
        }
        launcher_module.HOST_EFFORTS["gate-providerless"] = launcher_module.HOST_EFFORTS["claude"]
        try:
            if "gate-providerless" in launcher_module.seatable_hosts(providerless):
                mark_fail(
                    "agent-launch calls a host with no provider seatable; there is no family "
                    "to grade a reviewer seat against"
                )
            launcher_module.review_provider_options(providerless, "anthropic")
        except Exception as exc:  # noqa: BLE001 — a crash here names nothing
            mark_fail(
                f"agent-launch crashed building the provider menu for a host with no "
                f"provider: {type(exc).__name__}: {exc}"
            )
        finally:
            launcher_module.HOST_EFFORTS.pop("gate-providerless", None)
        offered = [
            option.value
            for option in launcher_module.review_provider_options(effortless, "anthropic")
        ]
        if "gate-effortless-vendor" in offered:
            mark_fail(
                "agent-launch offers a provider whose host has no effort vocabulary: "
                f"{offered}"
            )
        # And the reader really does refuse it, or the rule above is protecting nothing.
        try:
            launcher_module.parse_review_binding(
                {"provider": "gate-effortless-vendor", "tier": "helm"}, effortless, "gate.eff"
            )
            mark_fail(
                "agent-launch review binding reader ACCEPTS a host with no effort "
                "vocabulary — the seat rule is guarding a case that does not exist"
            )
        except launcher_module.LaunchError:
            pass

    # A disabled seat that does not say why is a dead end: the user came to this screen
    # to buy independence and has to learn why this method cannot sell it.
    single = next(
        (method for method in host_bound.values()
         if len(launcher_module.method_servable_hosts(method, config)) == 1),
        None,
    )
    if single is None:
        mark_fail("agent-launch has no single-host review method — the reason check is vacuous")
    else:
        blocked = [
            option
            for option in launcher_module.review_provider_options(config, "anthropic", single)
            if not option.enabled
        ]
        if not blocked:
            mark_fail(
                f"agent-launch left every provider selectable for {single.method_id!r}, which "
                "runs on one host"
            )
        # The ordering claim the code states in a comment: a seat that cannot run the tool
        # sorts BELOW the same-family seat that at least reviews something. The drives cannot
        # see this — enter picks the default by value, not by position — so dropping the
        # enabled-first key listed a dead option first and nothing noticed.
        listed = launcher_module.review_provider_options(config, "anthropic", single)
        if listed and not listed[0].enabled:
            mark_fail(
                f"agent-launch lists a seat that cannot run {single.method_id!r} first: "
                f"{[(o.value, o.enabled) for o in listed]}"
            )
        for option in blocked:
            # The promise is that this text and the LaunchError the seat would have raised
            # say the SAME thing. Checking that the capability, operation and host names
            # merely APPEAR let the wording drift: inserting "(and never will)" into the
            # sentence kept every part present and the gate green, while the screen and the
            # DROPPED row stopped matching. Equality is the promise, so equality is the
            # check — the malformed-offer path was already held to it and this one was not.
            binding = launcher_module.parse_review_binding(
                {"provider": option.value, "tier": "helm"}, config, "gate.reason"
            )
            try:
                launcher_module.derive_review_mechanism(single, binding, config)
                mark_fail(
                    f"agent-launch resolved {single.method_id!r} on {option.value!r}, which "
                    "the menu says it cannot run — the disabled seat is guarding nothing"
                )
            except launcher_module.LaunchError as exc:
                if option.unavailable_reason != str(exc):
                    mark_fail(
                        f"agent-launch disables {option.value!r} for {single.method_id!r} with "
                        f"wording the drop does not use — screen "
                        f"{option.unavailable_reason!r}, drop {str(exc)!r}"
                    )
        # And the grade has to be readable BEFORE the seat screen, or the first the user
        # hears of it is a family that will not select.
        note = launcher_module.method_availability(single, config)
        served = ", ".join(sorted(launcher_module.method_servable_hosts(single, config)))
        if f"Runs on {served} only." not in note:
            mark_fail(
                f"agent-launch does not tell the chooser that {single.method_id!r} runs on "
                f"{served} only: {note!r}"
            )
        for method in unrestricted:
            if "Runs on" in launcher_module.method_availability(method, config):
                mark_fail(
                    f"agent-launch narrows {method.method_id!r} in the chooser, but its "
                    "capability is offered on every seatable host"
                )

    # Refusing a seat must not cost more than the drop it prevents. `choose_review_binding`
    # raises for an unseatable method — right authority, and for one commit that exception
    # walked out of `review_editor` (which catches only BackRequested), killed the launcher
    # and took the user's unsaved draft with it. The parent commit authored the doomed seat
    # and showed a DROPPED row with the draft intact, so the fix was worse than the defect.
    # Reachable through the SUPPORTED path: a reviewer registered in the user-owned file,
    # naming a capability that offers only a host this profile cannot seat.
    unseatable = copy.deepcopy(config)
    unseatable["capabilities"]["gate-usertool"] = {
        "command": "/bin/sh",
        "offers": [{"operation": "gate-user-review", "hosts": ["gate-nowhere"],
                    "adapter": "host-workflow-v1"}],
    }
    unseatable["review_methods"]["gate-usermethod"] = {
        **copy.deepcopy(config["review_methods"][sorted(host_bound)[0]]),
        "label": "Gate user reviewer",
        "description": "Registered by the user, seatable nowhere here.",
        "capability": "gate-usertool",
        "operation": "gate-user-review",
    }
    user_addable = sorted(set(launcher_module.load_review_methods(unseatable))
                          - {launcher_module.PANEL_METHOD})
    survivor = launcher_module.build_plan(unseatable, "claude", "solo")
    # base, then try to add the unseatable method, back out of the reason screen, Apply.
    script = ["1", "", "", "2", str(user_addable.index("gate-usermethod") + 1), "b", "3"]
    try:
        shown, leftover = drive(survivor, unseatable, script)
    except AssertionError as exc:
        mark_fail(f"agent-launch editor did not stay open after refusing an unseatable seat: {exc}")
        shown, leftover = "", []
    except launcher_module.LaunchError as exc:
        mark_fail(
            "agent-launch editor died refusing an unseatable seat, losing the draft — a "
            f"refusal must not cost more than the DROPPED row it prevents: {exc}"
        )
        shown, leftover = "", []
    if shown:
        if leftover:
            mark_fail(f"agent-launch unseatable-refusal drive left {len(leftover)} input(s) unused")
        if "cannot be seated" not in shown:
            mark_fail("agent-launch refused an unseatable seat without showing the reason")
        report = survivor.get("review_report")
        if report is None:
            mark_fail("agent-launch lost the draft after refusing an unseatable seat")
        elif any(row.method_id == "gate-usermethod" for row in report.methods):
            mark_fail("agent-launch authored a row for a method it said could not be seated")

    # When NO seat can run a method, the screen has to say WHICH of the three reasons it
    # is — they live in different files. Folding them together, or back into "the host
    # does not decide this", leaves every provider selectable so enter-through authors a
    # guaranteed drop, which is the defect this whole constraint exists to prevent.
    if single_probe := next(iter(host_bound.values()), None):
        causes = {}
        gone = copy.deepcopy(config)
        gone["capabilities"].pop(single_probe.capability, None)
        causes["unregistered"] = (gone, "is not registered")
        nowhere = copy.deepcopy(config)
        nowhere["capabilities"][single_probe.capability]["offers"] = [
            {"operation": "gate-absent-operation", "hosts": ["claude"], "adapter": "host-workflow-v1"}
        ]
        causes["operation offered nowhere"] = (nowhere, "on any host")
        unseatable = copy.deepcopy(config)
        unseatable["capabilities"][single_probe.capability]["offers"] = [
            {"operation": single_probe.operation, "hosts": ["gate-ghost"],
             "adapter": "host-workflow-v1"}
        ]
        causes["offered only off-profile"] = (unseatable, "can seat none of those")
        malformed = copy.deepcopy(config)
        malformed["capabilities"][single_probe.capability]["offers"] = [
            {"operation": single_probe.operation, "adapter": "host-workflow-v1"}  # no `hosts`
        ]
        causes["offer block malformed"] = (malformed, "must be a non-empty list")
        # The tolerant reader skipped what it could not iterate and raised TypeError out of
        # the chooser, killing the launcher; and an invalid adapter advertised the method as
        # runnable on a host where every Apply drops. Classification reads the PARSER now.
        wrong_type = copy.deepcopy(config)
        wrong_type["capabilities"][single_probe.capability]["offers"] = [
            {"operation": single_probe.operation, "hosts": 7, "adapter": "host-workflow-v1"}
        ]
        causes["offer hosts not a list"] = (wrong_type, "must be a non-empty list")
        bad_adapter = copy.deepcopy(config)
        bad_adapter["capabilities"][single_probe.capability]["offers"] = [
            {"operation": single_probe.operation, "hosts": ["claude"], "adapter": "gate-nope"}
        ]
        causes["offer adapter unknown"] = (bad_adapter, "is not a core adapter")
        for label, (broken, phrase) in causes.items():
            try:
                options = launcher_module.review_provider_options(
                    broken, "anthropic", single_probe
                )
            except Exception as exc:  # noqa: BLE001 — a crash here names nothing and aborts
                mark_fail(
                    f"agent-launch crashed building the provider menu when its capability "
                    f"{label}: {type(exc).__name__}: {exc}"
                )
                continue
            if not options or any(option.enabled for option in options):
                mark_fail(
                    f"agent-launch leaves a provider selectable for {single_probe.method_id!r} "
                    f"when its capability {label} — enter would author a guaranteed drop"
                )
            if not all(phrase in option.unavailable_reason for option in options):
                mark_fail(
                    f"agent-launch does not name the cause ({label}) on the disabled seats for "
                    f"{single_probe.method_id!r}: {[o.unavailable_reason for o in options][:1]}"
                )
            # Stub the terminal read for the whole call. If the constraint regresses, this
            # does not raise — it PROMPTS, and a gate that reaches real stdin blocks
            # forever instead of failing. That happened: the sweep hung on an unanswered
            # menu, which from the outside is indistinguishable from a slow check.
            prompted = []
            original_read = launcher_module.read_input
            launcher_module.read_input = lambda prompt: (
                prompted.append(prompt) or (_ for _ in ()).throw(
                    AssertionError(f"editor prompted instead of refusing: {prompt!r}")
                )
            )
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    launcher_module.choose_review_binding(
                        broken, single_probe.method_id, None, None, "anthropic", single_probe
                    )
                mark_fail(
                    f"agent-launch authored a seat for {single_probe.method_id!r} when its "
                    f"capability {label}"
                )
            except launcher_module.LaunchError as exc:
                if phrase not in str(exc):
                    mark_fail(
                        f"agent-launch refuses the {single_probe.method_id!r} seat without naming "
                        f"the cause ({label}): {exc}"
                    )
            except AssertionError:
                mark_fail(
                    f"agent-launch offered a menu for {single_probe.method_id!r} when its "
                    f"capability {label}, instead of refusing with the reason: {prompted[:1]}"
                )
            except Exception as exc:  # a crash here prints no FAIL and reads like green
                mark_fail(
                    f"agent-launch crashed instead of refusing the {single_probe.method_id!r} "
                    f"seat when its capability {label}: {type(exc).__name__}: {exc}"
                )
            finally:
                launcher_module.read_input = original_read
            # Support answers before reachability. A capability whose binary resolves perfectly
        # but offers a different operation was reported "NOT INSTALLED — missing" while the
        # provider menu, three lines away, correctly said it offers no such operation.
        # Nothing installable fixes an unoffered operation.
        wrong_op = copy.deepcopy(config)
        wrong_op["capabilities"][single_probe.capability] = {
            "command": "/bin/sh",
            "offers": [{"operation": "gate-other-operation", "hosts": ["claude"],
                        "adapter": "host-workflow-v1"}],
        }
        note = launcher_module.method_availability(single_probe, wrong_op)
        if "NOT INSTALLED" in note:
            mark_fail(
                f"agent-launch calls {single_probe.method_id!r} uninstalled when its command "
                f"resolves and the real defect is an unoffered operation: {note[-80:]!r}"
            )
        if "NO SEAT" not in note:
            mark_fail(f"agent-launch does not report an unoffered operation as NO SEAT: {note[-80:]!r}")

        # A `${backend}` capability that cannot resolve is a missing HOST, not a missing
        # reviewer — the same distinction `_resolve_one` makes at Apply, and the config
        # omits `install` because no package exists. The two screens disagreed.
        backend_gone = copy.deepcopy(config)
        backend_gone["capabilities"][single_probe.capability] = {
            "command": launcher_module.HOST_BACKEND_COMMAND,
            "offers": [{"operation": single_probe.operation, "hosts": ["claude"],
                        "adapter": "host-workflow-v1"}],
        }
        backend_gone["backends"] = {
            **copy.deepcopy(config.get("backends", {})),
            "claude": {"command": "/nonexistent/gate-absent-cli"},
        }
        note = launcher_module.method_availability(single_probe, backend_gone)
        if "missing host, not a missing reviewer" not in note:
            mark_fail(
                "agent-launch blames the reviewer when the host CLI is what does not "
                f"resolve: {note[-90:]!r}"
            )

    # And for a malformed block the screen must say EXACTLY what the drop would, which
        # is the promise the code makes in a comment — the kind this effort keeps finding
        # unasserted. `capability_offered_hosts` silently skips what it cannot read, so
        # without deferring to the parser the screen blamed the host list for an invalid
        # entry and sent the user to the wrong line.
        broken_offer = causes["offer block malformed"][0]
        screen = launcher_module.review_provider_options(
            broken_offer, "anthropic", single_probe
        )[0].unavailable_reason
        try:
            launcher_module.derive_review_mechanism(
                single_probe,
                launcher_module.parse_review_binding(
                    {"provider": "anthropic", "tier": "helm"}, broken_offer, "gate.offer"),
                broken_offer,
            )
            mark_fail("agent-launch resolved a mechanism from a malformed offer block")
        except launcher_module.LaunchError as exc:
            if screen != str(exc):
                mark_fail(
                    "agent-launch disagrees with itself on a malformed offer — screen says "
                    f"{screen!r}, the drop says {str(exc)!r}"
                )

        # The chooser must carry it too, or the first the user hears is a screen that
        # refuses. Taken from the off-profile case, the one that looked fully installed.
        note = launcher_module.method_availability(single_probe, causes["offered only off-profile"][0])
        if "NO SEAT" not in note:
            mark_fail(
                f"agent-launch describes {single_probe.method_id!r} as available when no host it "
                f"offers on can be seated: {note[-90:]!r}"
            )

    # ...and the WIRING, through the real editor. Every assertion above calls the seat
    # helpers DIRECTLY, so all of them stay green when `choose_review_binding` simply
    # stops passing the method down — one line, and the original defect is back. Verified:
    # that mutation left this whole gate at exit 0 with no FAIL line. Only a drive that
    # ADDS A SINGLE-HOST METHOD and reads the resulting row can see it, because the
    # editor's own scripted drive below adds the multi-host method, which resolves either
    # way.
    single_host = sorted(
        mid for mid, method in host_bound.items()
        if len(launcher_module.method_servable_hosts(method, config)) == 1
    )
    if not single_host:
        mark_fail("agent-launch has no single-host review method — the wiring drive is vacuous")
    for host in ("claude", "codex"):
        for mid in single_host:
            addable = sorted(set(registry) - {launcher_module.PANEL_METHOD})
            if mid not in addable:
                mark_fail(f"agent-launch cannot add {mid!r} in the editor — the drive is vacuous")
                continue
            wired = launcher_module.build_plan(config, host, "solo")
            # Base panel, then add `mid`, pressing ENTER through every seat screen — the
            # hurried path this constraint exists for. Apply is option 4 because the added
            # method now holds a row of its own.
            script = ["1", "", "", "2", str(addable.index(mid) + 1), "", "", "4"]
            try:
                _, leftover = drive(wired, config, script)
            except AssertionError as exc:
                # `drive` raises when the editor asks for input the script does not have.
                # Landing on a DISABLED option does exactly that — `choose_lines` refuses
                # the empty answer and re-prompts — so this is the defect, not a harness
                # problem, and it has to be reported by name. Letting it escape aborts the
                # whole stage, and an aborted stage prints no FAIL line at all.
                mark_fail(
                    f"agent-launch editor re-prompted while adding {mid!r} on a {host} main: "
                    f"pressing enter did not answer a screen, which is what a landing seat "
                    f"that cannot be selected does ({exc})"
                )
                continue
            if leftover:
                mark_fail(
                    f"agent-launch editor drive for {mid!r} on a {host} main left "
                    f"{len(leftover)} scripted input(s) unused — the script no longer "
                    "matches the menus, so this proved nothing"
                )
                continue
            report = wired.get("review_report")
            if report is None:
                mark_fail(f"agent-launch editor drive for {mid!r} on a {host} main applied nothing")
                continue
            dropped = [
                row.method_id for row in report.methods
                if row.status == launcher_module.STATUS_DROPPED
            ]
            if dropped:
                mark_fail(
                    f"agent-launch: pressing enter through the editor to add {mid!r} on a "
                    f"{host} main authored a DROPPED row: {dropped}"
                )

    # A seat the editor never authored can still be unrunnable — a preset or a hand-edited
    # config names one, and constraining the CHOOSER does nothing for a row nobody opens.
    # Applying an untouched draft preserved it into a DROPPED row while the compose list
    # showed it like any other, so the user learned it only from the report.
    if single_host:
        mid = single_host[0]
        wrong = next(
            (option.value
             for option in launcher_module.review_provider_options(config, None, registry[mid])
             if not option.enabled),
            None,
        )
        if wrong is None:
            mark_fail(f"agent-launch: no unservable provider for {mid!r} — the stored-seat check is vacuous")
        else:
            stored = launcher_module.build_plan(config, "claude", "solo")
            stored["review_plan"] = launcher_module.ReviewPlan(
                base_present=True,
                base_binding=launcher_module.parse_review_binding(
                    {"provider": "openai", "tier": "frontier"}, config, "gate.stored"),
                methods={mid: launcher_module.parse_review_binding(
                    {"provider": wrong, "tier": "helm"}, config, "gate.stored")},
                source="composable",
            )
            try:
                transcript, _ = drive(stored, config, ["4"])
            except AssertionError as exc:
                mark_fail(f"agent-launch editor could not apply a stored {mid!r} seat: {exc}")
                transcript = ""
            if transcript and "WILL DROP" not in transcript:
                mark_fail(
                    f"agent-launch lists a stored {mid!r} seat on {wrong!r} without warning it "
                    "cannot run there; applying the untouched draft drops the row"
                )
            report = stored.get("review_report")
            if report is None or not any(
                row.method_id == mid and row.status == launcher_module.STATUS_DROPPED
                for row in report.methods
            ):
                mark_fail(
                    f"agent-launch stored-seat check is vacuous: the {mid!r} seat on {wrong!r} "
                    "did not actually drop, so the warning had nothing to warn about"
                )

            # Two more rows Apply drops that the list stayed silent about, because the
            # warning re-derived the answer instead of asking the resolver: a method whose
            # DESCRIPTOR is gone, and an OFFERED seat whose command does not resolve.
            # Neither is about which host was chosen, which is all the old check looked at.
            served = sorted(launcher_module.method_servable_hosts(registry[mid], config))
            right = config["hosts"][served[0]]["provider"]
            unresolvable = copy.deepcopy(config)
            unresolvable["capabilities"][registry[mid].capability]["command"] = (
                "/nonexistent/gate-absent-tool"
            )
            for label, cfg, plan_methods in (
                ("a method whose descriptor is gone", config,
                 {"gate-ghost-method": launcher_module.parse_review_binding(
                     {"provider": right, "tier": "helm"}, config, "gate.ghost")}),
                ("an offered seat whose command does not resolve", unresolvable,
                 {mid: launcher_module.parse_review_binding(
                     {"provider": right, "tier": "helm"}, unresolvable, "gate.unres")}),
            ):
                probe_plan = launcher_module.build_plan(cfg, "claude", "solo")
                probe_plan["review_plan"] = launcher_module.ReviewPlan(
                    base_present=True,
                    base_binding=launcher_module.parse_review_binding(
                        {"provider": "openai", "tier": "frontier"}, cfg, "gate.stored"),
                    methods=plan_methods, source="composable",
                )
                try:
                    seen_text, _ = drive(probe_plan, cfg, ["4"])
                except (AssertionError, launcher_module.LaunchError) as exc:
                    mark_fail(f"agent-launch editor died listing {label}: {exc}")
                    continue
                probe_report = probe_plan.get("review_report")
                if probe_report is None or not any(
                    row.status == launcher_module.STATUS_DROPPED
                    for row in probe_report.methods
                ):
                    mark_fail(
                        f"agent-launch check for {label} is vacuous: the row did not drop, so "
                        "there was nothing for the list to warn about"
                    )
                elif "WILL DROP" not in seen_text:
                    mark_fail(
                        f"agent-launch lists {label} without warning it drops — the warning "
                        "is re-derived instead of asked of the resolver Apply uses"
                    )

    # The EDIT path, which no drive reached. Every wiring drive ADDS (so `current` is None),
    # and the stored-seat drive applies without opening the row — so the pre-fill guard that
    # refuses to land on a seat the method cannot run was asserted nowhere. Deleting it left
    # the gate green while enter, on the edit screen, meant "keep the DROPPED row".
    if single_host:
        mid = single_host[0]
        served = sorted(launcher_module.method_servable_hosts(registry[mid], config))
        right = config["hosts"][served[0]]["provider"]
        wrong = next(
            (option.value
             for option in launcher_module.review_provider_options(config, None, registry[mid])
             if not option.enabled),
            None,
        )
        if wrong is None or wrong == right:
            mark_fail(f"agent-launch edit-path probe has no unservable seat for {mid!r} — vacuous")
        else:
            edited = launcher_module.build_plan(config, "claude", "solo")
            edited["review_plan"] = launcher_module.ReviewPlan(
                base_present=True,
                base_binding=launcher_module.parse_review_binding(
                    {"provider": "openai", "tier": "frontier"}, config, "gate.edit"),
                methods={mid: launcher_module.parse_review_binding(
                    {"provider": wrong, "tier": "helm"}, config, "gate.edit")},
                source="composable",
            )
            # open the stored row, take the default action (edit), enter through both seat
            # screens, then Apply — the hurried path, on a seat that starts out wrong.
            try:
                _, leftover = drive(edited, config, ["2", "", "", "", "4"])
            except (AssertionError, launcher_module.LaunchError) as exc:
                mark_fail(f"agent-launch editor died editing a stored unservable {mid!r} seat: {exc}")
                leftover = None
            if leftover:
                mark_fail(f"agent-launch edit drive left {len(leftover)} scripted input(s) unused")
            elif leftover is not None:
                report = edited.get("review_report")
                dropped = [
                    row.method_id for row in (report.methods if report else [])
                    if row.status == launcher_module.STATUS_DROPPED
                ]
                if report is None:
                    mark_fail(f"agent-launch edit drive for {mid!r} applied nothing")
                elif dropped:
                    mark_fail(
                        f"agent-launch: opening a stored {mid!r} seat on {wrong!r} and pressing "
                        f"enter through KEPT the unrunnable seat: {dropped}"
                    )

    # A real bug inside the seat path must not be rendered as a polite refusal. The editor
    # swallows `LaunchError` so a refusal does not cost the draft — widen that to `Exception`
    # and a TypeError becomes a "cannot be seated" screen the user is invited to work around,
    # which is the crash-reads-like-a-pass failure installed in the launcher itself.
    exploded = launcher_module.build_plan(config, "claude", "solo")
    original_binding = launcher_module.choose_review_binding

    def _boom(*_args, **_kwargs):
        raise TypeError("gate: a real bug, not a seat refusal")

    launcher_module.choose_review_binding = _boom
    try:
        drive(exploded, config, ["1"])
        mark_fail(
            "agent-launch review editor swallowed a TypeError from the seat path and carried "
            "on; only a refusal may be caught there, or every bug becomes a refusal"
        )
    except TypeError:
        pass
    except Exception as exc:  # noqa: BLE001
        mark_fail(f"agent-launch turned a seat-path TypeError into {type(exc).__name__}: {exc}")
    finally:
        launcher_module.choose_review_binding = original_binding

    # Cancelling. An inherited name is provenance and nothing more: the lowering table
    # carries no bindings, so a pre-filled seat here would be invented.
    # Still-legacy subject: the migrated presets no longer exercise the inherited-name
    # path at all, so a contrast taken from one would be vacuous.
    cancelled = launcher_module.build_plan(config, "claude", "solo")
    setup_before = cancelled["review_setup"]
    if setup_before is None:
        mark_fail("agent-launch review editor: the contrast preset is not legacy — vacuous")
        return
    transcript, _ = drive(cancelled, config, ["b"])
    if f"Inherited: {setup_before}" not in transcript:
        mark_fail("agent-launch review editor does not show the inherited name as provenance")
    if "Base panel: not set" not in transcript:
        mark_fail("agent-launch review editor pre-filled a base binding from a legacy name")
    if "managed review always has a base panel" not in transcript:
        mark_fail("agent-launch review editor offered Apply before a base binding existed")
    if (cancelled["review_setup"] != setup_before
            or cancelled["review_plan"].source != "legacy"
            or cancelled["review_report"] is not None):
        mark_fail("agent-launch review editor mutated the plan on the cancel path")

    # The landing seat must be a family the main is NOT. Pressing enter through the
    # binding screens is how a hurried user configures review, so the default decides
    # what most reviews actually are.
    for host in ("claude", "codex"):
        main_provider = config["hosts"][host]["provider"]
        options = launcher_module.review_provider_options(config, main_provider)
        if not options:
            mark_fail(f"agent-launch offers no reviewer provider on {host} — vacuous")
            continue
        landing = launcher_module.review_landing_provider(options, main_provider)
        if landing == main_provider:
            mark_fail(
                f"agent-launch lands the {host} provider menu on {landing!r}, the main's "
                "own family — enter-through would configure self-review"
            )
        if options[0].value == main_provider:
            mark_fail(
                f"agent-launch lists the main's own family first on {host}; the "
                "independent choice must come first"
            )
        # Each option has to say what choosing it buys, or the ordering is the only
        # signal and an ordering nobody reads is not a signal.
        same = next((o for o in options if o.value == main_provider), None)
        if same is not None and "Same family" not in same.description:
            mark_fail(f"agent-launch does not mark the same-family provider on {host}")

    # Preference among EQUALLY independent providers, which only a third family reveals.
    three = copy.deepcopy(config)
    three["hosts"]["gate-third"] = {
        **copy.deepcopy(config["hosts"]["claude"]), "provider": "gate-vendor",
    }
    launcher_module.HOST_EFFORTS["gate-third"] = launcher_module.HOST_EFFORTS["claude"]
    try:
        ordered = [o.value for o in launcher_module.review_provider_options(three, "anthropic")]
        if ordered[:1] != ["openai"]:
            mark_fail(
                f"agent-launch does not prefer the codex family among independent "
                f"providers: {ordered}"
            )
        if ordered[-1] != "anthropic":
            mark_fail(f"agent-launch does not rank the main's own family last: {ordered}")
    finally:
        launcher_module.HOST_EFFORTS.pop("gate-third", None)

    # An uninstalled method must not look like an installed one in the chooser.
    # Chosen by PROPERTY, not by name: hardcoding `registry["onto"]` meant renaming that
    # shipped method raised `KeyError` here and aborted the stage, so every launcher check
    # after this line silently stopped running. A gate that depends on one method's name
    # cannot survive the config it exists to check.
    # A SYNTHETIC install-bearing capability: no shipped method carries one any more
    # (both shipped reviewers are host CLIs), and the chooser-marking rule is core's.
    install_config = copy.deepcopy(config)
    install_config["capabilities"]["gate-installkit"] = {
        "command": str(pathlib.Path(tempfile.mkdtemp()) / "gate-install-tool"),
        "install": "npm i -g gate-install-tool",
        "offers": [{
            "operation": "install-review", "adapter": "exec-stdio-v1",
            "hosts": ["codex", "claude"],
        }],
    }
    tool = pathlib.Path(install_config["capabilities"]["gate-installkit"]["command"])
    tool.write_text("#!/usr/bin/env bash\nexit 0\n")
    tool.chmod(0o755)
    install_method = launcher_module.parse_review_method(
        "gate-install-lens",
        {
            "label": "L", "description": "D", "capability": "gate-installkit",
            "operation": "install-review", "instructions": "run {command}",
            "output": "review-v1", "perspectives": ["refutation"], "trials": 1,
            "severity_emits": ["blocker", "high", "medium", "low", "info"],
            "severity_map": {
                "blocker": "blocker", "high": "high", "medium": "medium",
                "low": "low", "info": "info",
            },
        },
        "gate",
    )
    absent = copy.deepcopy(install_config)
    absent["capabilities"]["gate-installkit"]["command"] = "gate-definitely-not-installed"
    marked = launcher_module.method_availability(install_method, absent)
    present = launcher_module.method_availability(install_method, install_config)
    if "NOT INSTALLED" not in marked or "install:" not in marked:
        mark_fail(
            f"agent-launch does not mark an uninstalled method in the chooser: {marked!r}"
        )
    if marked == present:
        mark_fail("agent-launch describes an uninstalled method exactly like an installed one")

    # Authoring. One assignment, one schema — the plan leaves composable or unchanged.
    authored = launcher_module.build_plan(config, "claude", "solo")
    _, leftover = drive(authored, config, ["1", "2", "1", "2", "1", "1", "1", "4"])
    if leftover:
        mark_fail(f"agent-launch review editor left {len(leftover)} scripted input(s) unused")
    review = authored["review_plan"]
    if review.source != "composable" or review.base_binding is None or len(review.methods) != 1:
        mark_fail(
            f"agent-launch review editor did not author a composable review "
            f"({review.source}, {len(review.methods)} method(s))"
        )
    if authored["review_setup"] is not None or authored["review_family"] is not None:
        mark_fail(
            "agent-launch review editor left a legacy name beside an authored block: "
            f"{authored['review_setup']!r}/{authored['review_family']!r}"
        )
    if authored["review_report"] is None:
        mark_fail("agent-launch review editor did not re-derive the report it displays")
    if "Composable review (availability=" not in launcher_module.run_contract(authored):
        mark_fail("agent-launch review editor's result does not reach the launch contract")
    # The base IS the panel; listing it in the map too would report it twice.
    if any(row.method_id == launcher_module.PANEL_METHOD for row in authored["review_report"].methods):
        mark_fail("agent-launch review editor put the panel in the method map as well as the base")

    # The owner's recommendation has to reach the seat screen or it is a constant nobody
    # reads. Asserted on what the user is SHOWN, and against the phrases rather than the
    # module's own string: comparing a surface to the constant it was built from passes
    # however empty that constant becomes.
    advised = launcher_module.build_plan(config, "claude", "solo")
    advised["review_plan"] = launcher_module.ReviewPlan(
        base_present=True,
        base_binding=launcher_module.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, config, "gate.advice"),
        methods={}, source="composable",
    )
    try:
        advice_shown, _ = drive(advised, config, ["b"])
    except (AssertionError, launcher_module.LaunchError) as exc:
        mark_fail(f"agent-launch editor died before showing the seat screen: {exc}")
    else:
        for phrase in ("different provider", "helm", "workhorse"):
            if phrase not in advice_shown:
                mark_fail(
                    f"agent-launch review editor never shows the user {phrase!r} — the "
                    f"most-effective shape is advice only, so an unshown constant is nothing"
                )


@launcher_check
def launcher_review_save(fx):
    """Stage 6's controls: an authored review survives save, and the user-owned
    registry is the deployer's business never.

    A preset emits the composable schema only when its review was AUTHORED in it. An
    inherited legacy name is carried through unchanged — legacy `none` has no
    composable form at all, since managed review always has a base panel, and two
    shipped presets are on it, so translating on save would perform the separately
    approved behaviour migration."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    base_toml = launch_profile_path.read_text()

    def composable(methods):
        body = (
            '\n[presets.src]\nlabel = "src"\nmain_tier = "helm"\ndelegation = true\n'
            'codex_execution_policy = "bypass"\nclaude_permission_mode = "standard"\n'
            '\n[presets.src.review.base]\nprovider = "openai"\ntier = "frontier"\n'
        )
        for method_id, extra in methods:
            body += f'\n[presets.src.review.methods."{method_id}"]\nprovider = "openai"\n{extra}\n'
        return body

    def fresh(methods):
        path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
        path.write_text(base_toml + composable(methods))
        return path

    # Control 1 — an arbitrary N-method set round-trips, keeping the form each binding
    # was AUTHORED in. Comparing the resolved report instead would pass even if `tier`
    # had been rewritten as a bare model/effort pair.
    sets = [
        [("onto", 'tier = "frontier"')],
        [("onto", 'tier = "frontier"'), ("ultracode", 'model = "gpt-5.6-terra"\neffort = "high"')],
        [("onto", 'tier = "helm"'),
         ("ultracode", 'model = "gpt-5.6-sol"\neffort = "max"\nservice_tier = "fast"')],
    ]
    if not sets:
        mark_fail("agent-launch review save: no method sets — the control is vacuous")
    for methods in sets:
        path = fresh(methods)
        try:
            config = launcher_module.load_config(path)
            plan = launcher_module.build_plan(config, "claude", "src")
            launcher_module.save_preset(plan, config, path, "saved")
            reloaded = launcher_module.load_config(path)
            back = launcher_module.build_plan(reloaded, "claude", "saved")
        except Exception as exc:
            mark_fail(f"agent-launch review save: {len(methods)}-method set did not save: {exc}")
            continue
        before, after = plan["review_plan"], back["review_plan"]
        if (after.source != "composable" or after.base_binding != before.base_binding
                or after.methods != before.methods):
            mark_fail(
                f"agent-launch review save: a {len(methods)}-method set did not round-trip "
                f"({sorted(after.methods)})"
            )
        if "review_setup" in reloaded["presets"]["saved"]:
            mark_fail("agent-launch wrote a legacy review name beside an authored [review] block")

    # Control 1b — an untouched arm's NESTED shapes are named, not tracebacked. The outer
    # arm check caught a scalar arm; a scalar `methods` inside a table arm reached
    # `.items()` as AttributeError past the save boundary (round 19, #11).
    try:
        cfg = launcher_module.load_config(launch_profile_path)
        cfg["presets"]["gate-arm"] = copy.deepcopy(cfg["presets"]["balanced"])
        cfg["presets"]["gate-arm"]["review"]["hosts"]["codex"]["methods"] = "not-a-table"
        plan = launcher_module.build_plan(cfg, "claude", "gate-arm")
        fields, overrides, review_block = launcher_module.preset_from_plan(plan, cfg, "saved")
        launcher_module.render_preset_block("saved", fields, overrides, review_block)
    except launcher_module.LaunchError as exc:
        if "not a table" not in str(exc) or "codex.methods" not in str(exc):
            mark_fail(f"agent-launch review save refused a malformed inactive arm without naming it: {exc}")
    except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
        mark_fail(f"agent-launch review save let a malformed inactive arm escape as {type(exc).__name__}: {exc}")
    else:
        mark_fail("agent-launch review save serialised a scalar `methods` in an inactive arm")

    # Control 1b2 — an untouched inactive arm goes back VERBATIM, which includes the fields
    # this serializer has no meaning for. It emitted `base` and `methods` and nothing else,
    # so any other top-level key the profile authored was dropped without a word: the
    # promise was verbatim and the behaviour was a projection of two known keys (round 22,
    # #10). Asserted on the RELOADED profile, and at both depths a raw field can arrive in.
    # A scalar field and a sub-table are separate cases: a serializer emitting the arm's own
    # keys and one recursing into its sub-tables are two doors, and either alone leaves the
    # other's shape silently dropped.
    # …and every TYPE the arm's fields can hold, not only strings. `_toml_scalar` covered
    # strings and booleans alone, so a plain TOML integer in an inactive arm was refused as
    # having "no form this writes back" — a value `tomllib` had just read, and TOML spells
    # (round 23, #5). One case per type family: the equality below is a full round trip, so
    # a type that came back as a different value fails as loudly as one that vanished.
    for shape, extra_toml in (
        ("scalar field", '\n[presets.src.review.hosts.codex]\nfuture_metadata = "keep-me"\n'),
        ("sub-table", '\n[presets.src.review.hosts.codex.future_table]\nnested = "keep-me"\n'),
        ("integer field", '\n[presets.src.review.hosts.codex]\nlimit = 7\nfloor = -3\n'),
        ("float field", '\n[presets.src.review.hosts.codex]\nthreshold = 1.5\nscale = 1e30\n'),
        ("array field",
         '\n[presets.src.review.hosts.codex]\nlenses = ["refutation", "coverage"]\n'
         'mixed = [1, "two", true, 3.5]\nnothing = []\n'),
        ("date and time fields",
         '\n[presets.src.review.hosts.codex]\nrecorded_at = 2026-08-17T03:39:00+09:00\n'
         'recorded_on = 2026-08-17\nrecorded_time = 03:39:00\n'),
        # The shape this profile authors `[capabilities.*].offers` in, so an arm carrying
        # one is ordinary rather than exotic — and inside an array an inline table is the
        # only spelling a table has.
        ("array of inline tables",
         '\n[presets.src.review.hosts.codex]\n'
         'offers = [{ operation = "review", hosts = ["claude", "codex"] }]\n'),
    ):
        verbatim_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
        verbatim_path.write_text(base_toml + (
            '\n[presets.src]\nlabel = "src"\nmain_tier = "helm"\ndelegation = true\n'
            'codex_execution_policy = "bypass"\nclaude_permission_mode = "standard"\n'
            '\n[presets.src.review.hosts.claude.base]\nprovider = "openai"\ntier = "frontier"\n'
            + extra_toml +
            '\n[presets.src.review.hosts.codex.base]\nprovider = "anthropic"\ntier = "frontier"\n'
        ))
        try:
            verbatim_config = launcher_module.load_config(verbatim_path)
            authored_arm = copy.deepcopy(
                verbatim_config["presets"]["src"]["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
            launcher_module.save_preset(
                launcher_module.build_plan(verbatim_config, "claude", "src"),
                verbatim_config, verbatim_path, "verbatim-saved",
            )
            saved_arm = (
                launcher_module.load_config(verbatim_path)["presets"]["verbatim-saved"]
                ["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
        except Exception as exc:  # noqa: BLE001 — a failure to save the subject is the finding
            mark_fail(
                f"agent-launch review save: the verbatim-arm {shape} subject did not save: {exc!r}"
            )
            continue
        if set(authored_arm) <= {"base", "methods"}:
            mark_fail(
                f"agent-launch review save: the verbatim-arm {shape} subject carries only "
                f"{sorted(authored_arm)} — it has no unrecognised field to lose, so the case "
                f"is vacuous"
            )
        elif saved_arm != authored_arm:
            mark_fail(
                f"agent-launch review save: an untouched arm authored a {shape} "
                f"{authored_arm!r} and came back as {saved_arm!r} — an arm promised back "
                f"verbatim lost {sorted(set(authored_arm) - set(saved_arm))}"
            )

    # Control 1b3 — a WHOLE inactive arm authored as a TOML value. The cases above all
    # author table-shaped arms and vary what is inside them; `hosts.codex = [1, 2]` is a
    # profile the launcher accepts — only the launching arm is parsed — and TOML writes it
    # back as a value in the parent hosts table, so refusing it at Save made an accepted
    # profile unsaveable (spec round 7, #2). Through the REAL save and reader, asserted on
    # the reloaded profile; two value shapes, because an array and a scalar take different
    # serializer branches.
    for arm_shape, arm_toml, arm_want in (
        ("array arm", "codex = [1, 2]", [1, 2]),
        ("scalar arm", 'codex = "disabled"', "disabled"),
    ):
        whole_arm_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
        whole_arm_path.write_text(base_toml + (
            '\n[presets.src]\nlabel = "src"\nmain_tier = "helm"\ndelegation = true\n'
            'codex_execution_policy = "bypass"\nclaude_permission_mode = "standard"\n'
            f'\n[presets.src.review.hosts]\n{arm_toml}\n'
            '\n[presets.src.review.hosts.claude.base]\nprovider = "openai"\ntier = "frontier"\n'
        ))
        try:
            whole_arm_config = launcher_module.load_config(whole_arm_path)
            authored_arm = copy.deepcopy(
                whole_arm_config["presets"]["src"]["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
            launcher_module.save_preset(
                launcher_module.build_plan(whole_arm_config, "claude", "src"),
                whole_arm_config, whole_arm_path, "whole-arm-saved",
            )
            saved_arm = (
                launcher_module.load_config(whole_arm_path)["presets"]["whole-arm-saved"]
                ["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
        except Exception as exc:  # noqa: BLE001 — refusing a writable arm is the finding
            mark_fail(
                f"agent-launch review save: an inactive {arm_shape} authored as a TOML "
                f"value did not save: {exc!r} — the launcher accepts this profile, so "
                f"refusing it at Save makes an accepted profile unsaveable"
            )
            continue
        if authored_arm != arm_want:
            mark_fail(
                f"agent-launch review save: the whole-{arm_shape} subject authored "
                f"{authored_arm!r}, not the {arm_want!r} the case reads — vacuous"
            )
        elif saved_arm != authored_arm:
            mark_fail(
                f"agent-launch review save: an inactive {arm_shape} authored as "
                f"{authored_arm!r} came back as {saved_arm!r} — an arm promised back "
                f"verbatim"
            )
    # …and the complement: a whole arm with no TOML spelling at all — reachable only by
    # assembling the config in memory, since `tomllib` cannot author one — is refused
    # naming `review.hosts.<host>`, never written and never dropped.
    unwritable_arm_cfg = launcher_module.load_config(launch_profile_path)
    unwritable_arm_cfg["presets"]["gate-unwritable-arm"] = copy.deepcopy(
        unwritable_arm_cfg["presets"]["balanced"]
    )
    unwritable_arm_cfg["presets"]["gate-unwritable-arm"]["review"]["hosts"]["codex"] = {
        "unserializable",
    }
    try:
        unwritable_arm_plan = launcher_module.build_plan(
            unwritable_arm_cfg, "claude", "gate-unwritable-arm"
        )
        fields, overrides, review_block = launcher_module.preset_from_plan(
            unwritable_arm_plan, unwritable_arm_cfg, "saved"
        )
        launcher_module.render_preset_block("saved", fields, overrides, review_block)
    except launcher_module.LaunchError as exc:
        if "review.hosts.codex" not in str(exc) or "no form this writes back" not in str(exc):
            mark_fail(
                f"agent-launch review save refused an unserializable whole arm without "
                f"naming the entry: {exc}"
            )
    except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
        mark_fail(
            f"agent-launch review save let an unserializable whole arm escape as "
            f"{type(exc).__name__}: {exc}"
        )
    else:
        mark_fail(
            "agent-launch review save serialised a whole arm that has no TOML spelling — "
            "writing means dropping it, and a drop needs a named refusal"
        )

    # …and the same promise one level DEEPER, inside `base` and inside a method binding.
    # Those two had a flat emitter of their own: a sub-table under either reached
    # `_toml_scalar`, which gives a bare table no spelling, so an arm the launcher ACCEPTS
    # died at Save with "cannot serialize preset value" — verbatim carry-through has no
    # depth limit, and this was the depth it stopped at (round 24, #7). The same loop
    # carried raw leaf keys, so a key needing quotes was written bare and TOML reloaded
    # `future.field` as the table `future` holding `field` — the value under a name nobody
    # wrote (round 24, #10). One case per site and per defect, so a fix reaching only one
    # of the two loops, or only one of the two spellings, fails the case it missed.
    for shape, base_extra, method_extra, tail, probe in (
        ("sub-table under base", "", "",
         '\n[presets.src.review.hosts.codex.base.metadata]\nnote = "keep-me"\n',
         lambda arm: arm["base"].get("metadata", {}).get("note")),
        ("sub-table under a method binding", "", "",
         '\n[presets.src.review.hosts.codex.methods."onto".metadata]\nnote = "keep-me"\n',
         lambda arm: arm["methods"]["onto"].get("metadata", {}).get("note")),
        ("dotted leaf key under base", '"future.field" = "keep-me"\n', "", "",
         lambda arm: arm["base"].get("future.field")),
        ("dotted leaf key under a method binding", "", '"future.field" = "keep-me"\n', "",
         lambda arm: arm["methods"]["onto"].get("future.field")),
    ):
        deep_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
        deep_path.write_text(base_toml + (
            '\n[presets.src]\nlabel = "src"\nmain_tier = "helm"\ndelegation = true\n'
            'codex_execution_policy = "bypass"\nclaude_permission_mode = "standard"\n'
            '\n[presets.src.review.hosts.claude.base]\nprovider = "openai"\ntier = "frontier"\n'
            '\n[presets.src.review.hosts.codex.base]\nprovider = "anthropic"\n'
            'tier = "frontier"\n' + base_extra +
            '\n[presets.src.review.hosts.codex.methods."onto"]\nprovider = "anthropic"\n'
            'tier = "frontier"\n' + method_extra + tail
        ))
        try:
            deep_config = launcher_module.load_config(deep_path)
            authored_arm = copy.deepcopy(
                deep_config["presets"]["src"]["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
            launcher_module.save_preset(
                launcher_module.build_plan(deep_config, "claude", "src"),
                deep_config, deep_path, "deep-saved",
            )
            saved_arm = (
                launcher_module.load_config(deep_path)["presets"]["deep-saved"]
                ["review"][launcher_module.REVIEW_ARMS_KEY]["codex"]
            )
        except Exception as exc:  # noqa: BLE001 — a failure to save the subject is the finding
            mark_fail(
                f"agent-launch review save: an untouched arm carrying a {shape} did not save: "
                f"{exc!r} — the launcher accepts this profile, so refusing it at Save reaches "
                f"the user only after the launch has already happened"
            )
            continue
        if probe(authored_arm) != "keep-me":
            mark_fail(
                f"agent-launch review save: the {shape} subject did not land where the case "
                f"reads it ({probe(authored_arm)!r}) — vacuous"
            )
        elif saved_arm != authored_arm:
            mark_fail(
                f"agent-launch review save: an untouched arm authored a {shape} and came back "
                f"as {saved_arm!r} rather than {authored_arm!r} — a value carried under a "
                f"name nobody wrote is lost exactly as completely as one dropped"
            )

    # Control 1c — an EMPTY inactive arm survives the save. `preset_from_plan` carried the
    # arm through and the renderer emitted no table for one holding neither a base nor a
    # method, so saving on claude deleted codex's arm and nothing failed (round 20, #6).
    # Asserted on the RELOADED profile rather than the rendered text: what the arm must
    # survive is the round trip, because the next launch reads the file, not the renderer.
    arm_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
    arm_path.write_text(base_toml + (
        '\n[presets.src]\nlabel = "src"\nmain_tier = "helm"\ndelegation = true\n'
        'codex_execution_policy = "bypass"\nclaude_permission_mode = "standard"\n'
        '\n[presets.src.review.hosts.claude.base]\nprovider = "openai"\ntier = "frontier"\n'
        '\n[presets.src.review.hosts.codex]\n'
    ))
    authored, saved_arms = [], []
    try:
        arm_config = launcher_module.load_config(arm_path)
        authored = sorted(arm_config["presets"]["src"]["review"][launcher_module.REVIEW_ARMS_KEY])
        launcher_module.save_preset(
            launcher_module.build_plan(arm_config, "claude", "src"), arm_config, arm_path, "saved"
        )
        saved_arms = sorted(
            launcher_module.load_config(arm_path)["presets"]["saved"]["review"][
                launcher_module.REVIEW_ARMS_KEY]
        )
    except Exception as exc:  # noqa: BLE001 — any failure here is the finding
        mark_fail(f"agent-launch review save: the empty-arm subject did not round-trip: {exc!r}")
    if authored != ["claude", "codex"]:
        mark_fail(
            f"agent-launch review save: the empty-arm subject authored arms {authored}, so the "
            f"case has no inactive arm to lose — vacuous"
        )
    elif saved_arms != authored:
        mark_fail(
            f"agent-launch review save: saving on claude wrote back arms {saved_arms} and "
            f"dropped {sorted(set(authored) - set(saved_arms))} — an arm holding nothing is "
            f"still an arm, and saving on one host silently un-launched the other"
        )

    # Control 2 — adding method N adds exactly one table and touches nothing else.
    def saved_text(methods):
        path = fresh(methods)
        config = launcher_module.load_config(path)
        launcher_module.save_preset(
            launcher_module.build_plan(config, "claude", "src"), config, path, "saved"
        )
        return launcher_module.user_presets_path(path).read_text().splitlines()

    one = saved_text([("onto", 'tier = "frontier"')])
    two = saved_text([("onto", 'tier = "frontier"'), ("ultracode", 'tier = "frontier"')])
    delta = list(difflib.unified_diff(one, two, lineterm="", n=0))
    added_tables = [line for line in delta if line.startswith("+[")]
    removed = [line for line in delta if line.startswith("-") and not line.startswith("---")]
    if len(added_tables) != 1:
        mark_fail(f"agent-launch review save: adding method N added {len(added_tables)} tables, want 1")
    if removed:
        mark_fail(f"agent-launch review save: adding method N removed lines: {removed[:3]}")

    # Control 3 — a user-registered method reaches the contract, a shipped-name
    # collision is refused, and the file the deployer must never touch is unchanged.
    path = fresh([("local-lens", 'tier = "frontier"')])
    registry = launcher_module.user_methods_path(path)
    registry.write_text(
        '[capabilities.local-kit]\ncommand = "/bin/echo"\n'
        'offers = [{ operation = "vendor-review", adapter = "exec-stdio-v1", '
        'hosts = ["codex", "claude"] }]\n\n'
        '[review_methods.local-lens]\nlabel = "A locally registered reviewer"\n'
        'description = "Registered by the user, never shipped."\ncapability = "local-kit"\n'
        'operation = "vendor-review"\ninstructions = "run {command} on {model}/{effort}"\n'
        'output = "review-v1"\nperspectives = ["refutation"]\ntrials = 1\norder = "fixed"\n'
        'swap_augmentation = false\naggregation = "union"\n'
        'severity_emits = ["blocker", "high", "medium", "low", "info"]\n'
        'severity_map = { blocker = "blocker", high = "high", medium = "medium", '
        'low = "low", info = "info" }\n'
    )
    digest = hashlib.sha256(registry.read_bytes()).hexdigest()
    try:
        config = launcher_module.load_config(path)
        contract = launcher_module.run_contract(
            launcher_module.build_plan(config, "claude", "src")
        )
    except Exception as exc:
        mark_fail(f"agent-launch review save: a locally registered method did not launch: {exc}")
        contract = ""
    if "local-lens" not in contract or "/bin/echo" not in contract:
        mark_fail("agent-launch did not project a locally registered review method")
    if hashlib.sha256(registry.read_bytes()).hexdigest() != digest:
        mark_fail("agent-launch modified the user-owned review method registry")

    collide = fresh([("onto", 'tier = "frontier"')])
    launcher_module.user_methods_path(collide).write_text(
        '[review_methods.panel]\nlabel = "hijack"\n'
    )
    try:
        launcher_module.load_config(collide)
        mark_fail("agent-launch let a local review method shadow a shipped one")
    except launcher_module.LaunchError as exc:
        if "already shipped" not in str(exc):
            mark_fail(f"agent-launch refused a collision for the wrong reason: {exc}")

    # Structural: the deployer neither writes nor verifies that filename. Asserted over
    # a non-empty target set that demonstrably contains the sibling it DOES deploy, so
    # an absence claim cannot pass by finding nothing at all.
    install = pathlib.Path("install.sh").read_text()
    targets = re.findall(
        r'(?:deploy_file|verify_match)\s+("[^"]*"|\S+)\s+("[^"]*"|\S+)', install
    )
    flat = [item for pair in targets for item in pair]
    if not flat:
        mark_fail("agent-launch review save: install.sh exposed no deploy/verify targets — vacuous")
    elif not any("profiles.toml" in item for item in flat):
        mark_fail("agent-launch review save: the deploy-target scan missed profiles.toml")
    if any(launcher_module.USER_METHODS_NAME in item for item in flat):
        mark_fail("install.sh deploys or verifies the user-owned review method registry")

    # Contrast — EVERY shipped preset's inherited legacy name is carried through, not
    # translated. Enumerated from the shipped profile rather than listed here, so a new
    # shipped preset is covered the day it lands. This is the control that fails the
    # moment anyone "finishes" the design sentence by adding a default lowering: the
    # two presets on `none` have no composable form at all, and they are exactly the
    # ones a one-preset spot check would miss.
    shipped_presets = sorted(tomllib.loads(base_toml)["presets"])
    if len(shipped_presets) < 2:
        mark_fail("agent-launch review save: fewer than two shipped presets — vacuous contrast")
    covered_setups = set()
    for preset_name in shipped_presets:
        legacy_path = fresh([("onto", 'tier = "frontier"')])
        try:
            legacy_config = launcher_module.load_config(legacy_path)
            legacy_plan = launcher_module.build_plan(legacy_config, "claude", preset_name)
        except Exception as exc:
            mark_fail(f"agent-launch review save: shipped preset {preset_name!r}: {exc}")
            continue
        if legacy_plan["review_setup"] is None:
            continue  # already composable; the round-trip controls above own it
        covered_setups.add(legacy_plan["review_setup"])
        # Mutate one NON-review field, which is the realistic way a user reaches save.
        legacy_plan["tiers"]["workhorse"]["model"] = "probe-workhorse"
        launcher_module.save_preset(legacy_plan, legacy_config, legacy_path, "legacy-saved")
        reloaded = launcher_module.load_config(legacy_path)
        saved_preset = reloaded["presets"]["legacy-saved"]
        if "review" in saved_preset:
            mark_fail(
                f"agent-launch wrote a [review] block when saving {preset_name!r}, whose "
                "review was never authored"
            )
        if (saved_preset.get("review_setup") != legacy_plan["review_setup"]
                or saved_preset.get("review_family") != legacy_plan["review_family"]):
            mark_fail(
                f"agent-launch translated {preset_name!r} on save: "
                f"{saved_preset.get('review_setup')!r}/{saved_preset.get('review_family')!r} "
                f"from {legacy_plan['review_setup']!r}/{legacy_plan['review_family']!r}"
            )
        if saved_preset.get("tier_overrides", {}).get("claude", {}).get("workhorse", {}).get(
            "model"
        ) != "probe-workhorse":
            mark_fail(f"agent-launch dropped the non-review edit when saving {preset_name!r}")
    # The `none` presets are the reason this decision went the way it did; a contrast
    # that never sees one would not have caught the failure it exists to catch.
    if "none" not in covered_setups:
        mark_fail(
            "agent-launch review save: no shipped preset on review_setup='none' was "
            f"exercised (saw {sorted(covered_setups)}) — the contrast misses the case "
            "that has no composable form"
        )

    # Host-scoped arms: saving a preset resolved on ONE host must keep the others. This
    # is the most dangerous failure in the form — losing an arm silently un-launches the
    # preset on that host, and nothing on the saving host would show it.
    arms_path = pathlib.Path(tempfile.mkdtemp()) / "profiles.toml"
    arms_path.write_text(base_toml + '''
[presets.arms]
label = "arms"
main_tier = "helm"
delegation = true
codex_execution_policy = "bypass"
claude_permission_mode = "standard"

[presets.arms.review.hosts.claude.base]
provider = "openai"
tier = "frontier"

[presets.arms.review.hosts.claude.methods."onto"]
provider = "openai"
tier = "frontier"

[presets.arms.review.hosts.codex.base]
provider = "anthropic"
tier = "frontier"
''')
    try:
        arms_config = launcher_module.load_config(arms_path)
        on_claude = launcher_module.build_plan(arms_config, "claude", "arms")
        on_codex = launcher_module.build_plan(arms_config, "codex", "arms")
    except Exception as exc:
        mark_fail(f"agent-launch review save: host-scoped arms did not resolve: {exc}")
        return
    # Each host must review on the OTHER family; one arm serving both is the regression
    # the form exists to prevent.
    if on_claude["review_report"].base.provider == on_codex["review_report"].base.provider:
        mark_fail(
            "agent-launch resolved the same reviewer provider on both hosts from "
            "host-scoped arms — the arm was not selected per host"
        )
    for plan, want in ((on_claude, "provider_difference"), (on_codex, "provider_difference")):
        if plan["review_report"].base.grade != want:
            mark_fail(
                f"agent-launch graded the {plan['host']} arm "
                f"{plan['review_report'].base.grade!r}, want {want!r}"
            )
    launcher_module.save_preset(on_claude, arms_config, arms_path, "arms-saved")
    reloaded_arms = launcher_module.load_config(arms_path)
    saved_arms = reloaded_arms["presets"]["arms-saved"].get("review", {}).get("hosts", {})
    if set(saved_arms) != {"claude", "codex"}:
        mark_fail(
            f"agent-launch saved only {sorted(saved_arms)} of the host arms — the preset "
            "can no longer launch everywhere it could before the save"
        )
    else:
        survived = launcher_module.build_plan(reloaded_arms, "codex", "arms-saved")
        binding = survived["review_plan"].base_binding
        if binding is None or binding.provider != "anthropic":
            mark_fail(
                "agent-launch did not round-trip the arm it never resolved "
                f"({binding})"
            )

    # Converse — an authored review is idempotent under load -> save -> load -> save.
    idem_path = fresh([("onto", 'tier = "frontier"')])
    idem_config = launcher_module.load_config(idem_path)
    launcher_module.save_preset(
        launcher_module.build_plan(idem_config, "claude", "src"), idem_config, idem_path, "idem"
    )
    first = launcher_module.user_presets_path(idem_path).read_text()
    second_config = launcher_module.load_config(idem_path)
    launcher_module.save_preset(
        launcher_module.build_plan(second_config, "claude", "idem"),
        second_config, idem_path, "idem",
    )
    if launcher_module.user_presets_path(idem_path).read_text() != first:
        mark_fail("agent-launch review save: an authored review is not idempotent under re-save")


def _write_probe_profile(path, old, new):
    """The shipped profile with one substitution, written where a check can load it."""
    text = launch_profile_path.read_text()
    assert text.count(old) == 1, f"probe anchor is not unique: {old!r}"
    path.write_text(text.replace(old, new))
    return path


def effort_scan_text(body, vocabulary):
    """The body as the foreign-effort scan should see it: one occurrence of the severity
    vocabulary core produced, removed, and nothing else.

    A FUNCTION so it can be exercised with a controlled input. The previous guard compared
    `len(body) - len(scanned)` against `len(vocabulary)` one line after computing `scanned`
    by exactly that transformation — arithmetic that cannot come out any other way, so the
    branch was unreachable for every real input and only fired if someone edited the line
    above it."""
    return body.replace(vocabulary, "", 1) if vocabulary in body else body


def translation_clause(rendered, launcher_module):
    """Every mapping a rendered method STATES, parsed out of the line.

    Containment is not enough: `severity.CRITICAL => blocker` contains `CRITICAL => blocker`,
    so a renderer that prefixes or mangles a third-party label satisfies an `in` check while
    telling the reader a name the reviewer never emits. Measured, not assumed — a renderer
    preserving the five shipped labels and mangling every other one passed both this gate and
    the goldens, because the goldens only ever see the shipped vocabulary.

    EVERY occurrence, not the last: a body that carried the marker itself would render a
    second clause, and taking one of the two would compare a set that matches while the
    reader is handed a contradiction. Core now refuses that body, and reading both here means
    the refusal has something to fail against."""
    marker = launcher_module.SEVERITY_CLAUSE_MARKER
    return {
        piece
        for chunk in rendered.split(marker)[1:]
        for piece in chunk.removesuffix("]").split(", ")
        if piece
    }


def conditions_that_held(**conditions) -> list:
    """The names of the conditions that are true, for a message that says which fired.

    One message over several `or`ed conditions names a symptom and not a defect. F-15 was
    exactly that: a launcher assertion failed once, never reproduced in three consecutive
    runs, and could not say which of its four conditions had been true — so the evidence the
    next occurrence needs was destroyed by the reporting, and the leading hypothesis (a race
    on a file a spawned process writes) stayed a hypothesis. Naming them costs one list.
    """
    return [name for name, held in conditions.items() if held]


def screen_survives_short_terminal(lines, plan, launcher_module):
    """Why the real screen at 80x24 is usable, or None when it cannot be judged.

    Drives the real MenuScreen with the real stylesheet — an earlier version of this check
    read the CSS off the screen class, which never carried it, so it was measuring an
    unstyled layout and calling it the screen. With the styles applied the fixed heights
    overflowed and Textual pushed the title and the setup panel off the TOP of the viewport
    (y=-9), where no key reaches them, while the option list collapsed to one row; the screen
    needed 45 rows to show itself.

    Three properties, all pressed rather than computed: the title and footer are always on
    screen, the option list the user must act through is on screen, and the whole body is
    reachable with the keys the footer advertises. A real `plan` matters — with None the
    panels collapse and the layout under test never happens."""
    try:
        import asyncio
        from textual.app import App
        from textual.widgets import OptionList
    except ImportError:
        return None
    app_class = launcher_module._build_app_class()
    screen_class = getattr(app_class, "MenuScreen", None)
    if screen_class is None or not getattr(app_class, "CSS", ""):
        return None
    options = [
        launcher_module.MenuOption("back", "Back", "Return."),
        launcher_module.MenuOption("go", "Go", "Do it."),
    ]

    class Probe(App):
        CSS = app_class.CSS

    async def drive():
        app = Probe()
        async with app.run_test(size=(80, 24)) as pilot:
            await app.push_screen(
                screen_class("Register another reviewer", options, "go", True, plan, None, lines)
            )
            await pilot.pause()
            screen = app.screen

            def on_screen(widget):
                region = widget.region
                return region.height > 0 and region.y >= 0 and region.y + region.height <= 24

            body = screen.query_one(f"#{launcher_module.BODY_PANEL_ID}")
            # The body is checked like the rest, and that is the whole point: the defect was
            # never a clipped bottom, it was widgets pushed off the TOP. Without this the
            # check passed on a layout whose body sat at y=-30 — its overflow was zero, so
            # "reaches its end" held vacuously while the setup panel and the corpus text were
            # unreachable by any key.
            for name, widget in (
                ("title", screen.query_one("#al-title")),
                ("scrolling body", body),
                ("detail panel", screen.query_one("#al-detail")),
                ("option list", screen.query_one(OptionList)),
                ("footer", screen.query_one("#al-footer")),
            ):
                if not on_screen(widget):
                    return f"the {name} is off the 80x24 viewport ({widget.region})"
            overflow = body.virtual_size.height - body.size.height
            if overflow <= 0:
                return "the body holds no overflow at 80x24 — the subject proves nothing"
            if body.max_scroll_y < overflow:
                return f"{overflow - body.max_scroll_y} rows of the body can never be scrolled to"
            for _ in range(body.max_scroll_y + 2):
                await pilot.press("pagedown")
            await pilot.pause()
            if body.scroll_offset.y < body.max_scroll_y:
                return "the body does not reach its end on PageDown"
            if not on_screen(screen.query_one("#al-title")):
                return "scrolling the body takes the title with it"
            return ""

    try:
        return asyncio.run(drive())
    except Exception as exc:  # noqa: BLE001 — an undrivable screen is not a pass
        return f"the screen could not be driven: {exc}"


def stated_translations(method, launcher_module):
    """What the descriptor's own map says the clause must contain — built here rather than
    read from `severity_translation`, so the renderer cannot satisfy the check by agreeing
    with itself."""
    return {
        f"{external}{launcher_module.SEVERITY_ARROW}{canonical}"
        for external, canonical in method.severity_map.items()
        if external != canonical
    }


@launcher_check
def launcher_review_methods(fx):
    """Stage 3's falsifying control: a method this repo has never seen must project
    through the generic resolver and renderer with NO code change.

    The canary's identifier is generated at runtime, so it cannot appear in any
    source file — and the check asserts exactly that. If a shipped method ever needs
    an `if method == "onto"` branch, the seam is wrong and this is where it shows."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    try:
        config = launcher_module.load_config(launch_profile_path)
        data = tomllib.loads(launch_profile_path.read_text())
        methods = launcher_module.load_review_methods(data)
        # BOTH shipped provider arms. A single arm cannot see a literal that happens to
        # equal its own model: a template hardcoding `gpt-5.6-sol` is invisible under an
        # openai binding, and only shows up under the anthropic one — where it renders
        # beside claude-fable-5 and hands the reviewer a command for the wrong family.
        arms = [
            (provider, launcher_module.parse_review_binding(
                {"provider": provider, "tier": "frontier"}, config, "gate"
            ))
            for provider in ("openai", "anthropic")
        ]
    except Exception as exc:
        mark_fail(f"agent-launch review methods: setup failed: {exc}")
        return

    # Every shipped method reaches the contract through the one renderer.
    shipped = ("panel", "codex-exec", "ultracode")
    # A reviewer with no vocabulary of its own reports on OUR ladder only because the
    # request says so, which makes its identity map true for a third reason — not "our own
    # subagents" (panel) and not "its ladder happens to be ours" (a tool with its own
    # matching vocabulary).
    # That third reason lives entirely in the instruction text, so it is asserted there:
    # strip the ladder out of the request and the descriptor is claiming a vocabulary
    # nothing establishes. Targeted rather than general because which of the three reasons
    # applies is not derivable from a descriptor, and inventing a field to say so would buy
    # one check at the cost of a concept every future reviewer has to understand.
    # Asserted on the RENDERED body rather than the template, because the template names a
    # slot and the reviewer receives the expansion; checking the template would pass on a
    # slot that expanded to nothing.
    DICTATED = ("ultracode", "codex-exec")
    missing = [name for name in shipped if name not in methods]
    if missing:
        mark_fail(f"agent-launch is missing shipped review method(s): {', '.join(missing)}")
    known_models = sorted(
        {
            model
            for host in (config.get("hosts") or {}).values()
            for model in (host.get("models") or [])
        }
    )

    known_efforts = sorted(
        {
            tier["effort"]
            for host in (config.get("hosts") or {}).values()
            for tier in (host.get("tiers") or {}).values()
            if isinstance(tier, dict) and tier.get("effort")
        }
    )

    def names_model(token, text):
        """Whole identifier, not substring. A catalog that keeps `gpt-5.6-sol` while a
        binding moves to `gpt-5.6-sol-2026-07-27` would otherwise find the base id inside
        the derived one and fail every correct method, blocking the rollout."""
        return re.search(
            r"(?<![A-Za-z0-9._-])" + re.escape(token) + r"(?![A-Za-z0-9._-])", text
        )

    for name in shipped:
        if name not in methods:
            continue
        rendered_arms = 0
        for provider, binding in arms:
            try:
                mechanism = launcher_module.derive_review_mechanism(
                    methods[name], binding, config
                )
                line = launcher_module.render_review_method(methods[name], mechanism)
            except launcher_module.LaunchError as exc:
                # A capability that offers no operation on this binding's host cannot be
                # seated there at all — that is the narrowing C8 introduced, not a defect.
                if "offers no" not in str(exc):
                    mark_fail(
                        f"agent-launch could not project shipped method {name!r} on "
                        f"{provider}: {exc}"
                    )
                continue
            rendered_arms += 1
            # SPLIT the authored body from the suffix the renderer appends. The renderer
            # ends every line with ` [shape; model/effort]`, so an assertion over the whole
            # line is satisfied by metadata the renderer generated from the binding — it
            # could not fail, whatever the body said. Computing the exact suffix rather
            # than splitting on " [" means a renderer that changes its shape fails here
            # loudly instead of being mis-split silently.
            suffix = (
                f" [{mechanism.shape}; {binding.model}/{binding.effort}"
                f"{launcher_module.controls_clause(methods[name])}"
                f"{launcher_module.severity_translation(methods[name])}]"
            )
            if not line.endswith(suffix):
                mark_fail(
                    f"agent-launch method {name!r} on {provider} did not render the exact "
                    f"seat suffix {suffix!r}; the body/suffix split below cannot be "
                    f"trusted: {line}"
                )
                body = line
            else:
                body = line[: -len(suffix)]
            # No angle-bracket slot may reach the reviewer. `validate_instruction_slots`
            # already rejects unknown `{slots}` at load, so a brace form cannot survive to
            # here and asserting one would be an untestable branch — but it knows only the
            # two literals `<review tier>` and `<e>`, so `<your model here>` loads clean
            # and arrives in the body. §1: the seat resolves before injection.
            leftover = re.search(r"<[a-z][a-z /-]*>", body)
            if leftover:
                mark_fail(
                    f"agent-launch method {name!r} on {provider} left {leftover.group(0)!r} "
                    f"unresolved in its body, handing the reviewer's seat back to the "
                    f"designer at dispatch time: {body}"
                )
            # …and no OTHER known model may appear in what the reviewer is handed. Every
            # check below reads a surface form — `llmOverride=`, then its payload, then
            # each occurrence — and each spelling that escaped one produced another
            # finding. This reads the RENDERED output instead, so it holds however the
            # template spells the assignment: a literal seat is a foreign model id in the
            # line, whatever syntax carried it there.
            # Every severity this reviewer moves must be stated in what the reader gets.
            # Derived from the descriptor's own map rather than from severity_translation,
            # so mutating that helper cannot satisfy the renderer and this check at once —
            # they would otherwise agree by construction and prove nothing.
            expected_moves = stated_translations(methods[name], launcher_module)
            if translation_clause(line, launcher_module) != expected_moves:
                mark_fail(
                    f"agent-launch method {name!r} on {provider} states "
                    f"{sorted(translation_clause(line, launcher_module))} where its map says "
                    f"{sorted(expected_moves)}; the reader is told a translation the "
                    f"reviewer never emits, or none at all"
                )
            # The mechanical controls the reviewer is handed must be the descriptor's own,
            # stated exactly. Built from the fields here rather than read back through
            # `controls_clause`, so the renderer cannot satisfy the check by agreeing with
            # itself — the same reason the severity clause is checked against the map.
            # Before this clause existed, `order`, `swap_augmentation` and `aggregation`
            # were parsed and read by nothing: contrary policies rendered identical lines.
            declared = methods[name]
            expected_controls = (
                f"trials={declared.trials}, order={declared.order}, "
                f"swap_augmentation={'true' if declared.swap_augmentation else 'false'}, "
                f"aggregation={declared.aggregation}"
            )
            if f"{launcher_module.CONTROLS_CLAUSE_MARKER}{expected_controls}" not in line:
                mark_fail(
                    f"agent-launch method {name!r} on {provider} does not state its declared "
                    f"controls ({expected_controls}) to the reader; a policy the reviewer "
                    f"is never told is a policy nothing runs: {line}"
                )
            foreign = sorted(
                model
                for model in known_models
                if model != binding.model and names_model(model, body)
            )
            if foreign:
                mark_fail(
                    f"agent-launch method {name!r} renders model(s) {', '.join(foreign)} "
                    f"that are not the resolved binding {binding.model!r} on {provider}; "
                    f"the reviewer would be handed a seat the launcher did not choose: "
                    f"{body}"
                )
            # Same rule for rigour. A body naming an effort the binding did not resolve
            # instructs the reviewer to run at it — and unlike a model id, nothing else in
            # the line would betray it, because the suffix keeps stating the real seat.
            #
            # Scanned with the `{severities}` expansion SUBTRACTED, and only that: `high`,
            # `medium` and `low` are rigours here and severity names there, and the text
            # alone cannot tell them apart. The subtraction is exact — core produced the
            # substring, the gate asks core for it — so this narrows the scan to what it
            # was always about rather than loosening it. Removing one literal occurrence,
            # because a body that names an effort somewhere ELSE must still fail.
            vocabulary = launcher_module.severity_vocabulary(methods[name])
            if name in DICTATED:
                unstated = [
                    value for value in methods[name].severity_emits if value not in body
                ]
                if unstated or vocabulary not in body:
                    mark_fail(
                        f"agent-launch method {name!r} on {provider} claims to emit "
                        f"{', '.join(unstated) or vocabulary} but its request never asks "
                        f"for it; this reviewer has no ladder of its own, so an unstated "
                        f"one is a claim about nothing: {body}"
                    )
            # Exercised on a CONTROLLED body where the same word sits both inside the
            # vocabulary and outside it. Over-broad stripping removes both, and the scan
            # then cannot see a rigour the seat never resolved — the failure the narrowing
            # was supposed to make impossible. Independent of how `scanned` is produced.
            probe_body = f"run it at low effort; severities {vocabulary}"
            if "low" not in effort_scan_text(probe_body, vocabulary):
                mark_fail(
                    "agent-launch review methods: narrowing the effort scan also hides an "
                    "effort named OUTSIDE the severity vocabulary, so a body instructing a "
                    "rigour the seat never resolved would pass unseen"
                )
            if vocabulary and vocabulary in effort_scan_text(probe_body, vocabulary):
                mark_fail(
                    "agent-launch review methods: the effort scan still sees the severity "
                    "vocabulary, so severity names read as rigours"
                )
            scanned = effort_scan_text(body, vocabulary)
            wrong_effort = sorted(
                effort
                for effort in known_efforts
                if effort != binding.effort and names_model(effort, scanned)
            )
            if wrong_effort:
                mark_fail(
                    f"agent-launch method {name!r} names effort(s) "
                    f"{', '.join(wrong_effort)} in its body while the resolved binding is "
                    f"{binding.effort!r} on {provider}; the reviewer is told one rigour and "
                    f"the seat carries another: {body}"
                )
        if rendered_arms == 0:
            mark_fail(
                f"agent-launch shipped method {name!r} rendered on neither provider arm, "
                "so every assertion above passed over nothing"
            )

    # The canary. Its name exists only inside this run.
    canary = "gate-canary-" + secrets.token_hex(6)
    with tempfile.TemporaryDirectory() as raw_canary:
        endpoint = pathlib.Path(raw_canary) / "vendor-reviewer"
        endpoint.write_text("#!/usr/bin/env bash\nexit 0\n")
        endpoint.chmod(0o755)
        canary_config = {
            **config,
            "capabilities": {
                **config["capabilities"],
                "gate-vendorkit": {
                    "command": str(endpoint),
                    "offers": [
                        {
                            "operation": "adversarial-pass",
                            "adapter": "exec-stdio-v1",
                            "hosts": ["codex", "claude"],
                        }
                    ],
                },
            },
        }
        descriptor = None
        try:
            descriptor = launcher_module.parse_review_method(
                canary,
                {
                    "label": "Canary",
                    "description": "A reviewer this repository has never seen.",
                    "capability": "gate-vendorkit",
                    "operation": "adversarial-pass",
                    "instructions": "run {command} on {model}/{effort} over {perspectives}",
                    "output": "review-v1",
                    "perspectives": ["refutation"],
                    "trials": 2,
                    "severity_emits": ["CRITICAL", "WARN"],
                    "severity_map": {"CRITICAL": "blocker", "WARN": "medium"},
                },
                f"review_methods.{canary}",
            )
            mechanism = launcher_module.derive_review_mechanism(descriptor, binding, canary_config)
            rendered = launcher_module.render_review_method(descriptor, mechanism)
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch could not project an unseen third-party method: {exc}")
            rendered = ""
        if str(endpoint) not in rendered or binding.model not in rendered:
            mark_fail("agent-launch projected the canary without its endpoint or its seat")
        # This canary's vocabulary is neither the ladder nor the one shipped tool's, which
        # is the only reason it can prove the translation clause is general. A renderer
        # that special-cased the shipped P0..P3 values would leave every shipped assertion
        # and every golden green while dropping an unseen reviewer's severities entirely.
        # Read from the descriptor's own map so the two cannot be satisfied by one edit.
        canary_moves = stated_translations(descriptor, launcher_module) if descriptor else set()
        if translation_clause(rendered, launcher_module) != canary_moves:
            mark_fail(
                f"agent-launch projected the canary stating "
                f"{sorted(translation_clause(rendered, launcher_module))} where its map says "
                f"{sorted(canary_moves)}; an unseen reviewer's severities reach no reader "
                f"intact"
            )
        # Every other subject moves either nothing or its whole vocabulary, so a renderer
        # that dropped exactly the one-entry case would keep all of them green. A reviewer
        # reporting on the ladder but for a single renamed level is an ordinary shape, not
        # a corner. `risk>7` rides along as the positive control for the name rule: `>` is
        # legal, only the arrow and the comma are reserved.
        singleton = {
            "label": "Canary", "description": "One renamed level.",
            "capability": "gate-vendorkit", "operation": "adversarial-pass",
            "instructions": "run {command} on {model}/{effort} over {perspectives}",
            "output": "review-v1", "perspectives": ["refutation"], "trials": 2,
            "severity_emits": ["risk>7", "medium"],
            "severity_map": {"risk>7": "high", "medium": "medium"},
        }
        try:
            one = launcher_module.render_review_method(
                launcher_module.parse_review_method(canary, singleton, f"review_methods.{canary}"),
                mechanism,
            )
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch refused a legal one-entry severity map: {exc}")
            one = ""
        if translation_clause(one, launcher_module) != {"risk>7 => high"}:
            mark_fail(
                "agent-launch did not state exactly the one translation a singleton map "
                f"moves — a reviewer that renames one level carries none of it, or carries "
                f"an identity that moves nothing: {one!r}"
            )
        # Contrary mechanical policies must reach the reader as different lines and
        # different records. Two descriptors differing ONLY in order, swap augmentation
        # and aggregation rendered byte-identical contracts (round 18, #6): the values
        # were parsed, defaulted, validated and read by nothing. `trials` is the control
        # — it always differed, because the author's `{trials}` slot carried it.
        policies = {}
        for label, order, swap, aggregation in (
            ("fixed-union", "fixed", False, "union"),
            ("randomized-majority", "randomized", True, "majority"),
        ):
            try:
                method = launcher_module.parse_review_method(
                    canary, {**singleton, "order": order, "swap_augmentation": swap,
                             "aggregation": aggregation},
                    f"review_methods.{canary}",
                )
                policies[label] = (
                    launcher_module.render_review_method(method, mechanism),
                    launcher_module.method_controls(method),
                )
            except launcher_module.LaunchError as exc:
                mark_fail(f"agent-launch refused a legal control policy {label}: {exc}")
        if len(policies) == 2:
            (line_a, controls_a), (line_b, controls_b) = policies.values()
            if line_a == line_b:
                mark_fail(
                    "agent-launch renders contrary review controls (order, swap "
                    "augmentation, aggregation) as the identical contract line; the reader "
                    f"cannot tell one policy from the other: {line_a!r}"
                )
            if controls_a == controls_b:
                mark_fail(
                    "agent-launch records contrary review controls as the identical "
                    "controls record; the ReviewPlan/v1 row cannot carry the declaration"
                )
            for expected in ("order=fixed", "swap_augmentation=false", "aggregation=union"):
                if expected not in line_a or expected in line_b:
                    mark_fail(
                        f"agent-launch controls clause does not state {expected!r} exactly "
                        f"where declared and only there: {line_a!r} / {line_b!r}"
                    )
        # The rule is an allowlist now, so its edges need subjects on BOTH sides: a name the
        # contract's own grammar would break must be refused, and a name that merely looks
        # unusual must not be. Without the second, the rule could tighten to nothing and
        # every other check here would still pass.
        def registers(name):
            return launcher_module.parse_review_method(
                canary, {**singleton, "severity_emits": [name, "medium"],
                         "severity_map": {name: "high", "medium": "medium"}},
                f"review_methods.{canary}",
            )

        # ` => ` is the one token padding cannot save: `risk => 7` renders
        # `risk => 7 => high`, where no reader can tell which arrow is the mapping — and the
        # gate could not tell either, having composed the identical string.
        for illegal in ("P0]\nforged: OK [x", "a, b", "P0;xhigh", " P0", "risk => 7"):
            try:
                registers(illegal)
            except launcher_module.LaunchError:
                continue
            mark_fail(
                f"agent-launch accepted the severity name {illegal!r}, which the rendered "
                f"contract gives its own meaning"
            )
        # The other edge, and it is the one that keeps being got wrong: over-restriction is
        # a reviewer someone cannot register, which the rule has already cost twice. `N/A` is
        # how a real tool spells the state ultracode calls `null`; `<` and `P0-` are the
        # labels an UNPADDED arrow used to fuse with, kept registrable by padding the
        # separator instead of forbidding them; `a->b` is legal for the same reason.
        # `重大` and `심각` are here because the rule was written with `string.ascii_letters`
        # and so quietly meant "a Latin label" — an over-restriction the screen did not even
        # disclose, and the most expensive kind here: a whole script of reviewers no one
        # could register.
        for legal in ("N/A", "<", "P0-", "a->b", "risk>7", "重大", "심각", "critique"):
            try:
                rendered_legal = launcher_module.render_review_method(
                    registers(legal), mechanism
                )
            except launcher_module.LaunchError as exc:
                mark_fail(f"agent-launch refused the plausible severity name {legal!r}: {exc}")
                continue
            if translation_clause(rendered_legal, launcher_module) != {
                f"{legal}{launcher_module.SEVERITY_ARROW}high"
            }:
                mark_fail(
                    f"agent-launch rendered the severity name {legal!r} into a clause that "
                    f"does not read back as itself: {rendered_legal!r}"
                )

        # A slot value can carry the clause marker that the TEMPLATE check never sees: this
        # perspective renders a second, contradicting translation beside the map's, and the
        # `{command}` path is the same door. Refused on the formatted body, which is the one
        # place every substitution has to pass through.
        # `{command}` present, because a capability-backed method without it is refused
        # at parse for THAT reason — and this control had gone vacuous behind it: the
        # refusal it counted on was the wrong one. The reason is asserted, not the raise.
        # Every core-owned marker takes the same door: a perspective carrying the controls
        # marker rendered a second controls clause beside core's (round 19, #9).
        for label, marker_value in (
            ("severities", f"security{launcher_module.SEVERITY_CLAUSE_MARKER}CRITICAL "
                           f"{launcher_module.SEVERITY_ARROW.strip()} info"),
            ("controls", f"correctness{launcher_module.CONTROLS_CLAUSE_MARKER}trials=1"),
            ("plan record", f"coverage {launcher_module.REVIEW_PLAN_MARKER}{{}}"),
        ):
            smuggled = {
                **singleton,
                "instructions": "run {command} over {perspectives}",
                "perspectives": [marker_value],
                "trials": 1,
            }
            reason = ""
            try:
                leaked = launcher_module.render_review_method(
                    launcher_module.parse_review_method(
                        canary, smuggled, f"review_methods.{canary}"
                    ),
                    mechanism,
                )
            except launcher_module.LaunchError as exc:
                leaked, reason = None, str(exc)
            if leaked is not None:
                mark_fail(
                    f"agent-launch rendered a second {label} clause smuggled in through a "
                    f"slot, so the reader is handed two and no way to choose: {leaked!r}"
                )
            elif "renders" not in reason or "slot value" not in reason:
                mark_fail(
                    f"agent-launch refused the smuggled {label} marker for a reason other "
                    f"than the formatted-body guard, so that guard is untested: {reason!r}"
                )

    # The registration screen is where a user learns the name rule, so a screen stating a
    # rule the parser does not enforce is worse than none: this one shipped once telling
    # users `>` was forbidden after the parser had stopped forbidding it, and a user would
    # have renamed their reviewer's real levels for nothing. Driven through the real
    # function, so this is about the lines the screen is GIVEN — not about a string in the
    # source, and not about what fits on the terminal, which is asserted separately below.
    shown: list[str] = []
    real_info = launcher_module._corpus_info
    launcher_module._corpus_info = lambda ui, title, lines, *a, **k: shown.extend(lines)
    try:
        launcher_module.register_reviewer_info(None, pathlib.Path("/nonexistent/profiles.toml"))
    except Exception as exc:  # noqa: BLE001 — any failure here is the finding
        mark_fail(f"agent-launch could not show the reviewer registration screen: {exc}")
    finally:
        launcher_module._corpus_info = real_info
    screen = "\n".join(shown)
    if not shown:
        mark_fail("agent-launch review methods: the registration screen showed nothing — vacuous")
    if launcher_module.SEVERITY_NAME_RULE not in screen:
        mark_fail(
            "agent-launch's registration screen does not state the severity-name rule the "
            f"parser enforces, so a user cannot author a valid descriptor from it: {screen!r}"
        )
    # Being GIVEN the lines is not being shown them, and having a scrollbar is not being able
    # to USE one. This payload is 26 lines on a terminal that is commonly 24, so the screen
    # carrying it has to survive being too small — with the title, the footer and the option
    # list still on it, and nothing pushed past a key's reach.
    try:
        subject_plan = launcher_module.build_plan(config, "claude", "deep-review")
    except Exception:  # noqa: BLE001 — no plan means no layout to judge
        subject_plan = None
    if subject_plan is None:
        mark_fail("agent-launch review methods: no plan for the screen subject — vacuous")
    else:
        verdict = screen_survives_short_terminal(shown, subject_plan, launcher_module)
        if verdict is None:
            mark_fail("agent-launch review methods: could not drive the real screen — vacuous")
        elif verdict:
            mark_fail(f"agent-launch's registration screen at 80x24: {verdict}")

    # Proof that no code change was involved: the identifier appears nowhere in core.
    scanned = 0
    for source in (launcher, pathlib.Path(__file__)):
        scanned += 1
        if canary in source.read_text(errors="ignore"):
            mark_fail(f"agent-launch review methods: canary name leaked into {source.name}")
    if scanned == 0:
        mark_fail("agent-launch review methods: scanned no source files — the proof is vacuous")

    # Each malformed descriptor must be rejected for its own stated reason. Without
    # these the declarative surface would accept anything and prove nothing.
    base = {
        "label": "L",
        "description": "D",
        "instructions": "x",
        "output": "review-v1",
        "severity_emits": ["a"],
        "severity_map": {"a": "high"},
    }
    rejects = [
        ("severity off the ladder", "severity ladder", {**base, "severity_map": {"a": "nope"}}),
        ("empty severity map", "non-empty table", {**base, "severity_map": {}}),
        # The declaration that makes totality decidable, and the two ways the map can
        # fail against it. Without these the shipped ultracode descriptor mapped the
        # canonical ladder while the tool emits P0..P3, and nothing could tell that
        # from onto's identity map, whose vocabulary genuinely IS the ladder.
        ("no severity_emits", "severity_emits is required",
         {k: v for k, v in base.items() if k != "severity_emits"}),
        ("severity_emits not a list", "severity_emits is required",
         {**base, "severity_emits": "a"}),
        ("severity_emits repeats", "repeats a value",
         {**base, "severity_emits": ["a", "a"]}),
        ("map misses an emitted severity", "unmapped: b",
         {**base, "severity_emits": ["a", "b"]}),
        ("map invents a severity", "maps values it never emits: z",
         {**base, "severity_map": {"a": "high", "z": "low"}}),
        # The clause separates its entries with a comma, so a name carrying one would render
        # as two mappings and misstate what the reviewer reports. Refused at registration
        # rather than escaped downstream.
        ("severity name carrying the clause separator", "may not contain",
         {**base, "severity_emits": ["a, b"], "severity_map": {"a, b": "high"}}),
        # Core appends the clause AFTER the authored body, so a body carrying the marker
        # renders two of them — the author's and the map's — and nothing reconciles a reader
        # handed both.
        ("instructions carrying the clause marker", "core appends",
         {**base, "instructions": "review; severities CRITICAL => info"}),
        ("wrong output contract", "output must be", {**base, "output": "freeform"}),
        ("unknown instruction slot", "unknown slot", {**base, "instructions": "{secret_key}"}),
        # The slot NAME was checked and its decoration was not: `{model:>10}` loaded clean
        # and raised a bare ValueError at render time, outside the LaunchError boundary.
        ("format spec on a slot", "format spec or conversion",
         {**base, "instructions": "run {model:>10}"}),
        ("conversion on a slot", "format spec or conversion",
         {**base, "instructions": "run {model!r}"}),
        # Core appends the controls clause too, for the same reason as the severity one.
        ("instructions carrying the controls marker", "core appends",
         {**base, "instructions": "review; controls trials=1"}),
        # The contract's canonical record has a marker too; authored text carrying it
        # could put a second, decodable record ahead of the real one.
        ("instructions carrying the plan-record marker", "canonical review record",
         {**base, "instructions": "review ReviewPlan/v1: x"}),
        # A capability resolves to a command the session must invoke; without `{command}`
        # the method reported OK and the launched session received no route to it.
        ("capability-backed method naming no {command}", "must name {command}",
         {**base, "capability": "onto", "operation": "o", "instructions": "review {perspectives}"}),
        # The legacy contract still carries these; the new surface must not.
        ("<review tier> placeholder", "resolve", {**base, "instructions": "a <review tier> b"}),
        ("declared isolation", "unknown method key", {**base, "isolated": True}),
        ("capability without operation", "required together", {**base, "capability": "onto"}),
        ("panel with a capability", "takes no capability",
         {**base, "capability": "onto", "operation": "o", "perspectives": ["a", "b"], "trials": 2}),
        ("panel with one perspective", "at least 2 distinct",
         {**base, "perspectives": ["a"], "trials": 2}),
        ("panel with one trial", "at least 2",
         {**base, "perspectives": ["a", "b"], "trials": 1}),
        # The four CONTROL values, which the descriptor and the plan row's snapshot are now
        # judged on by one function (`controls_value_reason`, spec round 2, #5). The row
        # reader's cases in `launcher_receipts` exercise that function's body; these
        # exercise the descriptor's use of it, so neither side is proved only by the other.
        # A BOOLEAN trial count first: `True` is an int in Python and `True >= 1`, so it
        # passes every numeric test written without `isinstance(..., bool)`.
        ("boolean trial count", "trials must be an integer >= 1",
         {**base, "trials": True}),
        ("zero trial count", "trials must be an integer >= 1", {**base, "trials": 0}),
        ("order outside its domain", "order must be one of",
         {**base, "order": "sideways"}),
        # A LIST where a closed-domain string belongs: `[] in <a set>` raises TypeError
        # rather than answering False, so the isinstance half is what keeps a hand-edited
        # profile from exiting on a traceback instead of this sentence.
        ("order that is not a string", "order must be one of", {**base, "order": []}),
        ("aggregation outside its domain", "aggregation must be one of",
         {**base, "aggregation": "plurality"}),
        ("non-boolean swap augmentation", "swap_augmentation must be boolean",
         {**base, "swap_augmentation": 0}),
    ]
    for name, needle, raw in rejects:
        method_id = "panel" if name.startswith("panel") else "gate-probe"
        try:
            launcher_module.parse_review_method(method_id, raw, "gate")
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(f"agent-launch rejected {name} for the wrong reason: {exc}")
        else:
            mark_fail(f"agent-launch accepted {name}, which must be rejected")

    offer_rejects = [
        ("unsupported adapter tag", "not a core adapter",
         {"offers": [{"operation": "o", "adapter": "grpc-v9", "hosts": ["codex"]}]}),
        ("offer without hosts", "non-empty list",
         {"offers": [{"operation": "o", "adapter": "exec-stdio-v1", "hosts": []}]}),
    ]
    for name, needle, raw in offer_rejects:
        try:
            launcher_module.parse_capability_offers("gate", raw)
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(f"agent-launch rejected {name} for the wrong reason: {exc}")
        else:
            mark_fail(f"agent-launch accepted {name}, which must be rejected")

    # A method whose capability offers nothing for this host must not silently
    # resolve to some other mechanism.
    try:
        launcher_module.derive_review_mechanism(
            launcher_module.parse_review_method(
                # `{command}` present, so the only defect this subject carries is the
                # unserved operation — a capability-backed method without it is refused
                # earlier, for that.
                "gate-probe",
                {**base, "capability": "codex-exec", "operation": "no-such-operation",
                 "instructions": "run {command}"},
                "gate",
            ),
            binding,
            config,
        )
    except launcher_module.LaunchError as exc:
        if "offers no" not in str(exc):
            mark_fail(f"agent-launch rejected an unserved operation for the wrong reason: {exc}")
    else:
        mark_fail("agent-launch resolved a mechanism for an operation no capability offers")


@launcher_check
def launcher_review_criterion(fx):
    """The criterion stage's falsifying controls.

    The discipline clause is plan-conditional, core-owned and method-blind; the
    compile → check → emit chain refuses by name with no salvage path; and
    verification binds a receipt's schema digest to the packet's OWN declared
    criterion — recompiled, never read off the receipts, which are the artifacts
    under audit. Every branch plants its violation through the real CLI or the real
    module call and refuses when the machinery accepts it."""
    m = fx.launcher_module
    if m is None:
        return
    tmp = pathlib.Path(tempfile.mkdtemp())

    def run(*args, env=None):
        proc = subprocess.run(
            [sys.executable, str(launcher), *args],
            capture_output=True, text=True, env={**fx.env, **(env or {})},
        )
        return proc.returncode, proc.stdout + proc.stderr

    # ── render: the toggle adds EXACTLY the core constant, and nothing else.
    try:
        config = m.load_config(launch_profile_path)
        methods = m.load_review_methods(config)
        binding = m.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, config, "gate"
        )
        mech = m.derive_review_mechanism(methods["codex-exec"], binding, config)
        off = m.render_review_method(methods["codex-exec"], mech, False)
        on = m.render_review_method(methods["codex-exec"], mech, True)
    except Exception as exc:
        mark_fail(f"agent-launch criterion: setup failed: {exc}")
        return
    if m.CRITERION_CLAUSE_MARKER in off:
        mark_fail("agent-launch criterion: the clause renders with the toggle off")
    if m.CRITERION_CLAUSE not in on or on.replace(m.CRITERION_CLAUSE, "", 1) != off:
        mark_fail(
            "agent-launch criterion: toggling on does not add exactly the core clause — "
            "subtracting the constant does not recover the untoggled row"
        )
    # A method this code has never seen carries the clause with NO code change, and a
    # non-identity severity map proves the ordering: the criterion clause must sit
    # BEFORE the severity clause, whose parser consumes everything after its marker.
    canary_raw = dict(
        tomllib.loads(launch_profile_path.read_text())["review_methods"]["codex-exec"]
    )
    canary_raw["severity_emits"] = ["P0", "P1"]
    canary_raw["severity_map"] = {"P0": "blocker", "P1": "medium"}
    canary_id = f"canary-{secrets.token_hex(4)}"
    try:
        canary = m.parse_review_method(canary_id, canary_raw, "gate canary")
        canary_row = m.render_review_method(canary, mech, True)
    except m.LaunchError as exc:
        mark_fail(f"agent-launch criterion: the canary method did not render: {exc}")
        canary_row = ""
    if canary_row:
        if m.CRITERION_CLAUSE not in canary_row:
            mark_fail(
                "agent-launch criterion: a never-seen method rendered without the "
                "clause — the append is not method-blind"
            )
        if m.SEVERITY_CLAUSE_MARKER not in canary_row:
            mark_fail("agent-launch criterion: the canary lost its severity clause")
        elif m.CRITERION_CLAUSE_MARKER in canary_row and canary_row.index(
            m.CRITERION_CLAUSE_MARKER
        ) > canary_row.index(m.SEVERITY_CLAUSE_MARKER):
            mark_fail(
                "agent-launch criterion: the clause rendered after the severity "
                "clause, which is parsed as everything after its marker"
            )
    # A slot value carrying the marker is refused at the formatted-body choke point —
    # the panel is the shipped method whose template renders {perspectives}.
    panel = methods[m.PANEL_METHOD]
    panel_mech = m.derive_review_mechanism(panel, binding, config)
    spoofed = dataclasses.replace(
        panel, perspectives=(f"security{m.CRITERION_CLAUSE_MARKER}forged", "safety")
    )
    try:
        m.render_review_method(spoofed, panel_mech, True)
    except m.LaunchError as exc:
        if "criterion" not in str(exc):
            mark_fail(f"agent-launch criterion: spoof refused for the wrong reason: {exc}")
    else:
        mark_fail(
            "agent-launch criterion: a perspective carrying the clause marker rendered "
            "a second decodable clause"
        )
    # …and the author's own template literal is refused at parse.
    try:
        m.validate_instruction_slots(
            f"do X{m.CRITERION_CLAUSE_MARKER}fake", "gate.instructions"
        )
    except m.LaunchError as exc:
        if "criterion" not in str(exc):
            mark_fail(f"agent-launch criterion: template literal refused for the wrong reason: {exc}")
    else:
        mark_fail("agent-launch criterion: an authored clause-marker literal parsed")

    # ── plan: the preset boolean threads to every live row, and only a boolean does.
    # Fake backends, the way the golden harness fakes them: the rows must resolve OK on
    # a machine with neither host CLI installed, and nothing here ever dispatches one.
    profile_text = launch_profile_path.read_text()
    for host in ("codex", "claude"):
        fake = tmp / f"fake-{host}"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        profile_text = profile_text.replace(
            f'command = "{host}"', f'command = {json.dumps(str(fake))}', 1
        )
    toggled_profile = tmp / "toggled-profiles.toml"
    toggled_profile.write_text(profile_text.replace(
        "[presets.deep-review]\n", "[presets.deep-review]\ncriterion = true\n", 1
    ))
    try:
        config_on = m.load_config(toggled_profile)
        plan_on = m.build_plan(config_on, "claude", "deep-review")
    except m.LaunchError as exc:
        mark_fail(f"agent-launch criterion: a toggled shipped preset did not build: {exc}")
        return
    live = [
        row for row in (plan_on["review_report"].base, *plan_on["review_report"].methods)
        if row.status != m.STATUS_DROPPED
    ]
    unmarked = [r.method_id for r in live if m.CRITERION_CLAUSE_MARKER not in r.instruction]
    if not live or unmarked:
        mark_fail(
            f"agent-launch criterion: toggled plan rows missing the clause: "
            f"{unmarked or 'no live rows at all'}"
        )
    if "deep-review" not in m.routed_preset_names(config_on["presets"]):
        mark_fail(
            "agent-launch criterion: a criterion-toggled preset is not routed, so a "
            "saved user preset could shadow it and silently drop the discipline"
        )
    bad_profile = tmp / "bad-profiles.toml"
    bad_profile.write_text(profile_text.replace(
        "[presets.deep-review]\n", '[presets.deep-review]\ncriterion = "yes"\n', 1
    ))
    try:
        m.build_plan(m.load_config(bad_profile), "claude", "deep-review")
    except m.LaunchError as exc:
        if "boolean" not in str(exc):
            mark_fail(f"agent-launch criterion: non-boolean toggle refused for the wrong reason: {exc}")
    else:
        mark_fail("agent-launch criterion: a string toggle built a plan")

    # ── the CLI chain: compile → check-findings → emit, every refusal by name.
    document = {
        "name": "AI harness", "observer": "the operator",
        "defect": "a false signal that looks true",
        "classes": ["false_signal", "detected_miss"], "stop_class": "false_signal",
        "evidence": "the input plus the known correct answer",
        "non_defects": ["style"],
        "stop_condition": "every PASS survives a known-opposite check",
        "misclassification_cost": "false passes dominate",
        "goldens": [
            {"kind": "positive", "case": "g1", "why": "w", "date": "2026-08-14",
             "provenance": "measured"},
            {"kind": "positive", "case": "g2", "why": "w", "date": "2026-08-19",
             "provenance": "constructed"},
            {"kind": "negative", "case": "g3", "why": "w", "date": "2026-08-14",
             "provenance": "measured"},
            {"kind": "negative", "case": "g4", "why": "w", "date": "2026-08-17",
             "provenance": "measured"},
            {"kind": "boundary", "case": "g5", "why": "w", "date": "2026-08-14",
             "provenance": "measured"},
        ],
    }
    doc_file = tmp / "criterion.json"
    doc_file.write_text(json.dumps(document))
    schema_file = tmp / "schema.json"
    status, output = run("--compile-criterion", str(doc_file), str(schema_file))
    if status != 0 or m.CRITERION_RECORD_MARKER not in output \
            or "criterion_schema_sha256=" not in output:
        mark_fail(f"agent-launch criterion: compile did not publish: {output.strip()[:200]}")
    schema_file2 = tmp / "schema2.json"
    run("--compile-criterion", str(doc_file), str(schema_file2))
    if schema_file.read_bytes() != schema_file2.read_bytes():
        mark_fail(
            "agent-launch criterion: double-compile is not byte-identical, so the "
            "verify-side recompilation can never match a receipt digest"
        )
    broken = dict(document, stop_class="not_a_class")
    broken_file = tmp / "broken.json"
    broken_file.write_text(json.dumps(broken))
    status, output = run("--compile-criterion", str(broken_file), str(tmp / "x.json"))
    if status == 0 or "stop_class" not in output:
        mark_fail(f"agent-launch criterion: a stop class off the enum compiled: {output.strip()[:160]}")
    good_result = tmp / "result-good.json"
    good_result.write_text('{"findings":[{"class":"false_signal","finding":"a wrong PASS"}]}')
    bad_result = tmp / "result-bad.json"
    bad_result.write_text('{"findings":[{"finding":"no class"}]}')
    status, _ = run("--check-findings", str(good_result), str(schema_file))
    if status != 0:
        mark_fail("agent-launch criterion: a conforming result was refused")
    status, output = run("--check-findings", str(bad_result), str(schema_file))
    if status == 0 or "carries no class" not in output:
        mark_fail(f"agent-launch criterion: a class-less finding passed: {output.strip()[:160]}")
    edited = json.loads(schema_file.read_text())
    edited["additionalProperties"] = True
    edited_file = tmp / "edited-schema.json"
    edited_file.write_text(json.dumps(edited))
    status, output = run("--check-findings", str(good_result), str(edited_file))
    if status == 0 or "recompile" not in output:
        mark_fail(f"agent-launch criterion: a hand-edited schema was accepted: {output.strip()[:160]}")

    # ── emission IS the accepting channel: env set, an invalid result earns NO receipt.
    codex_row = next(
        (r for r in live if r.method_id == "codex-exec" and r.status == m.STATUS_OK), None
    )
    if codex_row is None:
        mark_fail("agent-launch criterion: deep-review projected no OK codex-exec row to receipt")
        return
    seat = f"{codex_row.provider}:{codex_row.model}/{codex_row.effort}"
    contract = m.run_contract(plan_on)
    packet = tmp / "packet.txt"
    packet.write_text(f"{contract}\n{m.criterion_record_line(document)}\npacket prose\n")
    plan_file = tmp / "plan.txt"
    plan_file.write_text(contract)
    rdir = tmp / "receipts-good"
    env_good = {
        m.RECEIPT_DIR_ENV: str(rdir), m.RECEIPT_CRITERION_ENV: str(schema_file),
    }
    status, output = run(
        "--emit-receipt", "codex-exec", seat, "0", str(packet), str(good_result),
        env=env_good,
    )
    if status != 0:
        mark_fail(f"agent-launch criterion: a conforming emit failed: {output.strip()[:160]}")
    else:
        written = json.loads(next(rdir.glob("*.json")).read_text())
        expected = hashlib.sha256(schema_file.read_bytes()).hexdigest()
        if written.get("criterion_schema_sha256") != expected:
            mark_fail(
                "agent-launch criterion: the receipt's schema digest is not the hash of "
                "the schema the emission validated against"
            )
    rdir_bad = tmp / "receipts-bad"
    status, output = run(
        "--emit-receipt", "codex-exec", seat, "0", str(packet), str(bad_result),
        env={m.RECEIPT_DIR_ENV: str(rdir_bad), m.RECEIPT_CRITERION_ENV: str(schema_file)},
    )
    if status == 0 or "no receipt" not in output or (
        rdir_bad.exists() and any(rdir_bad.iterdir())
    ):
        mark_fail(
            f"agent-launch criterion: an unclassified finding earned a receipt: "
            f"{output.strip()[:160]}"
        )
    status, _ = run(
        "--emit-receipt", "codex-exec", seat, "0", str(packet), str(bad_result),
        env={m.RECEIPT_DIR_ENV: str(tmp / 'receipts-prose')},
    )
    if status != 0:
        mark_fail(
            "agent-launch criterion: with no schema env a prose-route emit changed "
            "behavior — the default-off path is not preserved"
        )

    # ── verification binds the digest to the PACKET's criterion, both directions.
    def fold_and_verify(receipt_dir, packet_file, *, with_packet=True):
        status, bundle_out = run(
            "--fold-receipts", str(receipt_dir), str(packet_file), "main-gate"
        )
        if status != 0:
            return None, f"fold failed: {bundle_out.strip()[:160]}"
        bundle_file = tmp / f"bundle-{receipt_dir.name}.json"
        bundle_file.write_text(bundle_out)
        args = ["--verify-receipts", str(plan_file), str(bundle_file),
                "--config", str(toggled_profile)]
        if with_packet:
            args += ["--packet", str(packet_file)]
        return run(*args), None
    result, failure = fold_and_verify(rdir, packet)
    if failure:
        mark_fail(f"agent-launch criterion: {failure}")
    else:
        status, output = result
        if "codex-exec: ACHIEVED" not in output:
            mark_fail(
                f"agent-launch criterion: a stamped conforming receipt was not achieved: "
                f"{output.strip()[:300]}"
            )
        if "criterion=declared and bound" not in output:
            mark_fail("agent-launch criterion: the bound adjudication did not disclose itself")
    result, failure = fold_and_verify(rdir, packet, with_packet=False)
    if failure:
        mark_fail(f"agent-launch criterion: {failure}")
    elif "criterion=declared but UNBOUND" not in result[1]:
        mark_fail(
            "agent-launch criterion: a packet-less adjudication of a criterion plan did "
            "not disclose that the digest was bound to no bytes"
        )
    # A receipt validated against SOME OTHER criterion's schema is refused by name.
    other = dict(document, classes=["surface_defect", "note"], stop_class="surface_defect")
    other_file = tmp / "other.json"
    other_file.write_text(json.dumps(other))
    other_schema = tmp / "other-schema.json"
    run("--compile-criterion", str(other_file), str(other_schema))
    other_result = tmp / "result-other.json"
    other_result.write_text('{"findings":[{"class":"surface_defect","finding":"x"}]}')
    rdir_other = tmp / "receipts-other"
    run(
        "--emit-receipt", "codex-exec", seat, "0", str(packet), str(other_result),
        env={m.RECEIPT_DIR_ENV: str(rdir_other), m.RECEIPT_CRITERION_ENV: str(other_schema)},
    )
    result, failure = fold_and_verify(rdir_other, packet)
    if failure:
        mark_fail(f"agent-launch criterion: {failure}")
    elif "not compiled from the criterion this packet declares" not in result[1]:
        mark_fail(
            "agent-launch criterion: a receipt stamped with a foreign schema digest was "
            f"not refused: {result[1].strip()[:300]}"
        )
    # A plan that declared the discipline cannot verify against a packet with no record.
    bare_packet = tmp / "bare-packet.txt"
    bare_packet.write_text(contract)
    rdir_bare = tmp / "receipts-bare"
    run(
        "--emit-receipt", "codex-exec", seat, "0", str(bare_packet), str(good_result),
        env={m.RECEIPT_DIR_ENV: str(rdir_bare), m.RECEIPT_CRITERION_ENV: str(schema_file)},
    )
    result, failure = fold_and_verify(rdir_bare, bare_packet)
    if failure:
        mark_fail(f"agent-launch criterion: {failure}")
    else:
        status, output = result
        if status == 0 or f"carries no {m.CRITERION_RECORD_SCHEMA} record" not in output:
            mark_fail(
                f"agent-launch criterion: a criterion plan verified against a packet "
                f"that never declared one: {output.strip()[:200]}"
            )

    # ── the doors the first criterion-declared review closed (criterion round, #0-#8).
    # A legacy plan accepts the toggle and renders nothing — refused by name, never inert.
    # The needle is the guard's OWN diagnostic and the fixture name avoids it: with the
    # preset named gate-crit-legacy, any unrelated LaunchError echoing the preset name
    # satisfied a "legacy" needle (criterion round 2, #4).
    legacy_profile = tmp / "legacy-criterion.toml"
    legacy_profile.write_text(
        profile_text + legacy_preset_toml("gate-crit-old", "native-panel")
        + "criterion = true\n"
    )
    try:
        m.build_plan(m.load_config(legacy_profile), "claude", "gate-crit-old")
    except m.LaunchError as exc:
        if "silently inert" not in str(exc):
            mark_fail(f"agent-launch criterion: legacy toggle refused for the wrong reason: {exc}")
    else:
        mark_fail(
            "agent-launch criterion: a legacy preset accepted criterion = true and "
            "built a plan the clause never reaches — an inert toggle reads as "
            "discipline in force"
        )
    # A method ID carrying ANY of the three clause markers forges a clause core never
    # appended — all three, because a guard retaining only one stays green over the
    # other two (criterion round 2, #3).
    for marker in (
        m.SEVERITY_CLAUSE_MARKER, m.CONTROLS_CLAUSE_MARKER, m.CRITERION_CLAUSE_MARKER,
    ):
        try:
            m.parse_review_method(f"evil{marker}forged", canary_raw, "gate id")
        except m.LaunchError as exc:
            if "method id" not in str(exc):
                mark_fail(f"agent-launch criterion: marker-in-id ({marker!r}) refused for the wrong reason: {exc}")
        else:
            mark_fail(
                f"agent-launch criterion: a method id carrying {marker!r} parsed — "
                f"it would forge a clause in every row it prefixes"
            )
    # Schemas self-consistent over enums the compiler can never produce — every arm of
    # the admissibility rule, not one (criterion round 2, #3).
    for label, enum in (
        ("one-class", ["attacker_class"]),
        ("duplicate", ["attacker_class", "attacker_class"]),
        ("padded", ["attacker_class ", "other"]),
    ):
        attacker = tmp / f"attacker-{label}.json"
        attacker.write_text(json.dumps(m.criterion_schema(enum)))
        status, output = run("--check-findings", str(good_result), str(attacker))
        if status == 0 or "never produce" not in output:
            mark_fail(
                f"agent-launch criterion: a {label} schema supplied its own authority: "
                f"{output.strip()[:160]}"
            )
    # Present-but-empty env is a named refusal, not a silent prose downgrade — the
    # empty string AND whitespace, because `if env and not env.strip()` refuses only
    # the second while silently downgrading the first (criterion round 2, #3).
    for label, value in (("empty", ""), ("whitespace", "  ")):
        rdir_empty = tmp / f"receipts-{label}-env"
        status, output = run(
            "--emit-receipt", "codex-exec", seat, "0", str(packet), str(bad_result),
            env={m.RECEIPT_DIR_ENV: str(rdir_empty), m.RECEIPT_CRITERION_ENV: value},
        )
        if status == 0 or "set but empty" not in output or (
            rdir_empty.exists() and any(rdir_empty.iterdir())
        ):
            mark_fail(
                f"agent-launch criterion: a {label} {m.RECEIPT_CRITERION_ENV} was "
                f"treated as unset: {output.strip()[:160]}"
            )
    # A lone surrogate rides a JSON escape through json.loads and crashes every later
    # encode; both readers refuse it as non-compiler-producible (criterion round 2, #0).
    surrogate_doc = dict(document, classes=["\ud800bad", "ok"], stop_class="ok")
    surrogate_file = tmp / "surrogate.json"
    surrogate_file.write_text(json.dumps(surrogate_doc), encoding="utf-8")
    status, output = run("--compile-criterion", str(surrogate_file), str(tmp / "s.json"))
    if status == 0 or "UTF-8" not in output or "Traceback" in output:
        mark_fail(
            f"agent-launch criterion: a lone-surrogate document was not refused by "
            f"name: {output.strip()[:160]}"
        )
    surrogate_schema = tmp / "surrogate-schema.json"
    surrogate_schema.write_text(
        json.dumps(m.criterion_schema(["\ud800bad", "ok"])), encoding="utf-8"
    )
    status, output = run("--check-findings", str(good_result), str(surrogate_schema))
    if status == 0 or "never produce" not in output:
        mark_fail(
            f"agent-launch criterion: a lone-surrogate schema supplied its own "
            f"authority: {output.strip()[:160]}"
        )
    # The stamped digests are of the bytes VALIDATION saw: swap both files at the seam
    # between validation and hashing — a hook on findings_violations, which the fixed
    # and the reverted implementation both call there — and require pre-swap digests
    # (criterion round 2, #1: the stable-file oracle was satisfied by the old
    # validate-then-reopen implementation too).
    swap_schema = tmp / "swap-schema.json"
    swap_schema.write_bytes(schema_file.read_bytes())
    swap_result = tmp / "swap-result.json"
    swap_result.write_bytes(good_result.read_bytes())
    expected_schema_digest = hashlib.sha256(swap_schema.read_bytes()).hexdigest()
    expected_result_digest = hashlib.sha256(swap_result.read_bytes()).hexdigest()
    attack_bytes = json.dumps(m.criterion_schema(["swapped_a", "swapped_b"])).encode()
    real_violations = m.findings_violations

    def swapping_violations(result, classes):
        verdict = real_violations(result, classes)
        swap_schema.write_bytes(attack_bytes)
        swap_result.write_bytes(b'{"findings":[]}')
        return verdict

    rdir_swap = tmp / "receipts-swap"
    env_backup = {
        key: os.environ.get(key)
        for key in (m.RECEIPT_DIR_ENV, m.RECEIPT_CRITERION_ENV)
    }
    m.findings_violations = swapping_violations
    os.environ[m.RECEIPT_DIR_ENV] = str(rdir_swap)
    os.environ[m.RECEIPT_CRITERION_ENV] = str(swap_schema)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m.emit_receipt_command(
                "codex-exec", seat, "0", str(packet), str(swap_result)
            )
    except m.LaunchError as exc:
        mark_fail(f"agent-launch criterion: the snapshot control's emission failed: {exc}")
    finally:
        m.findings_violations = real_violations
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    swapped = sorted(rdir_swap.glob("*.json")) if rdir_swap.exists() else []
    if not swapped:
        mark_fail("agent-launch criterion: the snapshot emission wrote no receipt")
    else:
        record = json.loads(swapped[0].read_text())
        if (
            record.get("criterion_schema_sha256") != expected_schema_digest
            or record.get("result_sha256") != expected_result_digest
        ):
            mark_fail(
                "agent-launch criterion: the receipt stamped digests of bytes the "
                "validation never saw — emission is not a single byte snapshot"
            )
    # A prose mention mid-line is not the declared record; a record line with trailing
    # content is a different claim than the compiler printed.
    # The mid-line case deliberately carries NOTHING after the JSON: with trailing text
    # it was refused by the trailing-content door even with anchoring reverted, and the
    # expected substring "record line" appears in that door's message too — a control
    # satisfied by the wrong producer, caught by its own faithful-revert run.
    for text_case, expected, label in (
        (f"prose {m.CRITERION_RECORD_MARKER}{json.dumps(document)}\n",
         "carries no", "a mid-line prose mention"),
        (f"{m.criterion_record_line(document)} trailing junk\n",
         "trailing content", "a record line with trailing content"),
    ):
        try:
            m.extract_criterion(text_case, "gate packet")
        except m.LaunchError as exc:
            if expected not in str(exc):
                mark_fail(
                    f"agent-launch criterion: {label} refused for the wrong reason: {exc}"
                )
        else:
            mark_fail(f"agent-launch criterion: {label} was accepted as the declared record")
    # The schema-flag probe: present, absent, and the known-opposite error producer
    # whose STDERR carries the very token being searched for.
    probe_cases = []
    for name, script, expect in (
        ("present", "#!/bin/sh\necho '--output-schema <FILE>'\nexit 0\n", "present"),
        ("absent", "#!/bin/sh\necho 'no such flag here'\nexit 0\n", "absent"),
        ("error", "#!/bin/sh\necho 'error: unknown option --output-schema' >&2\nexit 2\n",
         "cannot probe"),
    ):
        stub = tmp / f"probe-{name}"
        stub.write_text(script)
        stub.chmod(0o755)
        probe_profile = tmp / f"probe-{name}.toml"
        probe_profile.write_text(launch_profile_path.read_text().replace(
            'command = "codex"', f'command = {json.dumps(str(stub))}', 1
        ))
        status, output = run(
            "--config", str(probe_profile), "--check-schema-flag", "codex"
        )
        probe_cases.append((name, expect, status, output))
    for name, expect, status, output in probe_cases:
        if expect == "present" and (status != 0 or "present" not in output):
            mark_fail(f"agent-launch criterion: probe {name} did not report present: {output.strip()[:120]}")
        elif expect == "absent" and (status != m.SCHEMA_FLAG_ABSENT_EXIT or "absent" not in output):
            mark_fail(f"agent-launch criterion: probe {name} did not report absent: {output.strip()[:120]}")
        elif expect == "cannot probe" and (
            status == 0 or "cannot probe" not in output or ": present" in output
        ):
            mark_fail(
                f"agent-launch criterion: a failed help run whose error text carries "
                f"the token was read as a capability: {output.strip()[:160]}"
            )
    # Save As carries the toggle; an untoggled plan's projection stays byte-identical.
    saved_fields = m.preset_from_plan(plan_on, config_on, "gate-save")[0]
    if saved_fields.get("criterion") is not True:
        mark_fail(
            "agent-launch criterion: Save As from a criterion plan serialized no "
            "criterion field — reload would silently drop the discipline"
        )
    untoggled_profile = tmp / "untoggled-profiles.toml"
    untoggled_profile.write_text(profile_text)
    config_off = m.load_config(untoggled_profile)
    plan_off = m.build_plan(config_off, "claude", "deep-review")
    if "criterion" in m.preset_from_plan(plan_off, config_off, "gate-save")[0]:
        mark_fail(
            "agent-launch criterion: an untoggled plan's saved preset gained a "
            "criterion field — existing saves are no longer byte-identical"
        )


@launcher_check
def launcher_review_schema(fx):
    """The composable review schema parses, and every way of writing it wrong fails.

    Stage 2 of design/reviewer-registry/DESIGN.md: the reader ships before the
    resolver, so the only thing that can be asserted here is that reading is real —
    a valid block resolves its bindings, and each guard rejects for its own stated
    reason. Byte-identity of the resolved routes is the goldens' job, not this one."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    try:
        config = launcher_module.load_config(launch_profile_path)
    except Exception as exc:
        mark_fail(f"agent-launch review schema: real profile did not load: {exc}")
        return

    def read(preset):
        return launcher_module.read_review(preset, "gate", config, "claude")

    # Rejections go through build_plan, not read_review, because build_plan is where
    # the reader is actually invoked for a selected preset. Calling read_review
    # directly would keep passing even if that wiring were deleted.
    skeleton = {
        "label": "Gate",
        "main_tier": "helm",
        "codex_execution_policy": "standard",
        "claude_permission_mode": "standard",
    }

    def read_via_build_plan(preset):
        probe_config = {
            **config,
            "presets": {**config["presets"], "gate-probe": {**skeleton, **preset}},
        }
        return launcher_module.build_plan(probe_config, "claude", "gate-probe")

    # A tier reference must satisfy model⇒effort by construction — that is the whole
    # reason it exists, so resolve it against the real profile rather than a literal.
    frontier = config["hosts"]["claude"]["tiers"]["frontier"]
    try:
        composable = read(
            {
                "review": {
                    "base": {"provider": "anthropic", "tier": "frontier"},
                    "methods": {
                        "codex-exec": {"provider": "openai", "model": "gpt-5.6-sol", "effort": "high"}
                    },
                }
            }
        )
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch rejected a valid composable review block: {exc}")
        return
    if (
        composable.source != "composable"
        or composable.base_binding.model != frontier["model"]
        or composable.base_binding.effort != frontier["effort"]
        or composable.base_binding.service_tier != launcher_module.DEFAULT_SERVICE_TIER
        or composable.methods["codex-exec"].effort != "high"
    ):
        mark_fail("agent-launch composable review binding did not resolve to the tier's seat")

    # A legacy preset must lower with UNBOUND methods: a fabricated default here
    # would be indistinguishable from an authored binding once the resolver lands.
    legacy = read({"review_setup": "ultracode", "review_family": "cross"})
    if (
        legacy.source != "legacy"
        # Method IDS, so they follow the tool: legacy lowers its `ultracode` ROUTE into the
        # Codex-hosted method, which is a different namespace from the route token.
        or list(legacy.methods) != ["codex-exec"]
        or any(binding is not None for binding in legacy.methods.values())
        or not legacy.base_present
    ):
        mark_fail("agent-launch legacy review lowering did not produce unbound methods")
    if read({"review_setup": "none"}).base_present:
        mark_fail("agent-launch lowered legacy 'none' with a base panel it never had")

    rejects = [
        # The Stage 2 control: the two schemas are alternatives, never a merge.
        ("review_setup with [review]", "cannot be combined",
         {"review_setup": "ultracode", "review": {"base": {"provider": "openai", "tier": "frontier"}}}),
        # Both legacy names must conflict with [review]; testing only review_setup let
        # a reader that silently drops a top-level review_family still pass the gate.
        ("review_family with [review]", "cannot be combined",
         {"review_family": "same", "review": {"base": {"provider": "openai", "tier": "frontier"}}}),
        ("review_family inside [review]", "not part of the composable schema",
         {"review": {"base": {"provider": "openai", "tier": "frontier"}, "review_family": "cross"}}),
        ("tier and model together", "exactly one of tier or model",
         {"review": {"base": {"provider": "openai", "tier": "frontier", "model": "gpt-5.6-sol"}}}),
        ("model without effort", "effort is required",
         {"review": {"base": {"provider": "openai", "model": "gpt-5.6-sol"}}}),
        ("effort invalid for the resolved host", "unsupported effort",
         {"review": {"base": {"provider": "anthropic", "model": "claude-opus-5", "effort": "ultra"}}}),
        # NOT here any more: a provider with no configured host. A preset naming one now
        # degrades to the main seat instead of failing the parse, because cross-family is
        # a recommendation and a user with one provider must still be able to launch. It
        # is still rejected where tolerance does not apply — asserted below, since moving
        # a subject out of a rejection list without re-asserting it elsewhere is how a
        # property quietly stops being checked.
        ("unknown binding key", "unknown binding key",
         {"review": {"base": {"provider": "openai", "tier": "frontier", "interface": "mcp"}}}),
        ("missing base panel", "base is required", {"review": {"methods": {}}}),
        # The base panel's own id, authored as an OPTIONAL method. The editor says panel is
        # the mandatory base and never belongs in the map, and the schema accepted it: the
        # report then carried two selected rows under one id, which the verifier collapses
        # into a single entry, so one receipt certified both (round 21, #1). Asserted here
        # rather than only in `launcher_review_editor`, which proves the UI does not author
        # it — a rule only the UI keeps is no rule at all for a hand-edited profile.
        ("panel as an optional method", "mandatory base panel",
         {"review": {"base": {"provider": "openai", "tier": "frontier"},
                     "methods": {"panel": {"provider": "anthropic", "tier": "helm"}}}}),
    ]
    if not rejects:
        mark_fail("agent-launch review schema: no rejection subjects — the check is vacuous")

    # The four corners of `missing_host_ok`. Tolerance means one thing only: a provider
    # this launcher RECOGNISES, for which this profile happens to configure no host.
    # Every neighbouring case must still fail, and each failed differently before it was
    # asserted here.
    one_host = copy.deepcopy(config)
    one_host["hosts"].pop("codex", None)
    # (a) recognised but absent -> tolerated, which is the whole single-provider case.
    if launcher_module.parse_review_binding(
        {"provider": "openai", "tier": "frontier"}, one_host, "gate", missing_host_ok=True
    ) is not None:
        mark_fail(
            "agent-launch seated a binding whose provider this profile has no host for; "
            "the caller can no longer tell a satisfiable binding from an unsatisfiable one"
        )
    # (b) a TYPO is not a shortfall. Without the recognition test both look identical at
    # the point where no host matches, and a misspelling degraded a launch it should have
    # rejected — an authoring error wearing the costume of an environment limit.
    try:
        launcher_module.parse_review_binding(
            {"provider": "opneai", "tier": "frontier"}, config, "gate",
            missing_host_ok=True,
        )
    except launcher_module.LaunchError as exc:
        if "no configured host" not in str(exc):
            mark_fail(f"agent-launch rejected a misspelled provider unclearly: {exc}")
    else:
        mark_fail(
            "agent-launch tolerated a provider no host declares and this launcher does "
            "not recognise; a typo must fail, not silently degrade to the main seat"
        )
    # (c) tolerance is opt-in: the interactive editor must still refuse.
    try:
        launcher_module.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, one_host, "gate"
        )
    except launcher_module.LaunchError as exc:
        if "no configured host" not in str(exc):
            mark_fail(f"agent-launch rejected an unreachable provider unclearly: {exc}")
    else:
        mark_fail(
            "agent-launch accepted a provider with no configured host without being asked "
            "to tolerate it; an interactively authored binding must fail, not degrade"
        )
    # (d) tolerating a missing host is not tolerating a malformed binding. Checked after
    # host resolution, a tier+model pair returned early and was accepted — then started
    # failing the day the host appeared.
    # Every host-INDEPENDENT shape rule, not just the first one. Each of these was
    # accepted as "unseated" while its host was absent and rejected the day the host
    # appeared; `model = 7` was worse than inconsistent — it launched and then could not
    # be SAVED, because the raw table is written back verbatim and a non-string reaches
    # the TOML serializer.
    malformed = [
        ("tier and model together", "exactly one of tier or model",
         {"provider": "openai", "tier": "frontier", "model": "x"}),
        ("effort alongside tier", "effort is fixed by tier",
         {"provider": "openai", "tier": "frontier", "effort": "high"}),
        ("non-string model", "model must be a non-empty string",
         {"provider": "openai", "model": 7, "effort": "high"}),
        ("model without effort", "effort is required with model",
         {"provider": "openai", "model": "gpt-5.6-sol"}),
    ]
    for label, expected, raw_binding in malformed:
        try:
            launcher_module.parse_review_binding(
                raw_binding, one_host, "gate", missing_host_ok=True
            )
        except launcher_module.LaunchError as exc:
            if expected not in str(exc):
                mark_fail(
                    f"agent-launch rejected {label} unclearly: {exc} (want {expected!r})"
                )
        else:
            mark_fail(
                f"agent-launch accepted {label} on a binding it could not seat; a missing "
                f"host must not excuse a shape the same binding is refused for once the "
                f"host exists"
            )
    ambiguous = copy.deepcopy(config)
    for host in ambiguous.get("hosts", {}).values():
        if isinstance(host, dict):
            host["provider"] = "openai"
    try:
        launcher_module.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, ambiguous, "gate",
            missing_host_ok=True,
        )
    except launcher_module.LaunchError as exc:
        if "more than one host" not in str(exc):
            mark_fail(f"agent-launch rejected an ambiguous provider unclearly: {exc}")
    else:
        mark_fail(
            "agent-launch tolerated an AMBIGUOUS provider under missing_host_ok; that flag "
            "covers a user's missing host, never a profile that maps one provider twice"
        )
    # A tier reference must not be a hole in validation — the same malformed pairs are
    # rejected for the explicit-model spelling. These are asserted directly against
    # parse_review_binding rather than through build_plan, because build_plan validates
    # every tier of the selected host before the reader runs, so a malformed tier is
    # unreachable from that edge. Stage 3's resolver will call the binding parser on
    # its own, which is what these guard.
    def doctored(tier_binding):
        host = {**config["hosts"]["claude"]}
        host["tiers"] = {**host["tiers"], "frontier": tier_binding}
        return {**config, "hosts": {**config["hosts"], "claude": host}}

    tier_rejects = [
        ("tier whose effort the host rejects", "unsupported effort",
         {"model": "claude-opus-5", "effort": "ultra"}),
        ("tier with a non-string effort", "unsupported effort",
         {"model": "claude-fable-5", "effort": 7}),
        ("tier with no usable model", "no usable model", {"model": "", "effort": "high"}),
        ("tier missing effort entirely", "unsupported effort", {"model": "claude-opus-5"}),
    ]
    for name, needle, tier_binding in tier_rejects:
        try:
            launcher_module.parse_review_binding(
                {"provider": "anthropic", "tier": "frontier"}, doctored(tier_binding), "gate"
            )
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(f"agent-launch rejected {name} for the wrong reason: {exc}")
        except Exception as exc:  # a raw KeyError here reaches the CLI as a traceback
            mark_fail(f"agent-launch raised {type(exc).__name__} instead of LaunchError for {name}")
        else:
            mark_fail(f"agent-launch accepted {name}, which must be rejected")

    for name, needle, preset in rejects:
        try:
            read_via_build_plan(preset)
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(f"agent-launch rejected {name} for the wrong reason: {exc}")
        else:
            mark_fail(f"agent-launch accepted {name}, which must be rejected")

    # The next two both go through load_config on a real file, because that is where
    # host validation and preset merging happen. Asserting them against an
    # already-loaded config dict never executes either path and passes vacuously —
    # which is exactly what both of these rows did before this was negative-controlled.
    profile_text = launch_profile_path.read_text()
    with tempfile.TemporaryDirectory() as raw_probe:
        probe_dir = pathlib.Path(raw_probe)

        # A legacy profile that predates [hosts.<h>].provider must still load. Making
        # the key mandatory stopped every such install before a preset was selected.
        legacy_profile = probe_dir / "legacy.toml"
        legacy_text = "\n".join(
            line for line in profile_text.splitlines() if not line.startswith("provider = ")
        )
        if legacy_text == profile_text:
            mark_fail("agent-launch review schema: legacy-profile probe removed nothing")
        legacy_profile.write_text(legacy_text)
        try:
            legacy_config = launcher_module.load_config(legacy_profile)
            # A LEGACY preset must still launch with no host declaring a provider; that
            # is why the field is optional.
            launcher_module.build_plan(legacy_config, "claude", "solo")
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch rejected a provider-less legacy profile: {exc}")
        # A COMPOSABLE preset cannot, because its seats are named by provider. That is a
        # real new requirement of the migrated defaults, so it must fail LOUDLY and name
        # the reason rather than launching a review that silently is not one.
        try:
            launcher_module.build_plan(legacy_config, "claude", "balanced")
            mark_fail("agent-launch launched a composable preset on a provider-less profile")
        except launcher_module.LaunchError as exc:
            if "provider" not in str(exc):
                mark_fail(f"agent-launch refused it for an unclear reason: {exc}")

        # One malformed preset in the user-owned file must not disable the others. It
        # used to fail only when selected; load-time reading made it a total outage.
        dormant_profile = probe_dir / "dormant.toml"
        dormant_profile.write_text(profile_text)
        (probe_dir / launcher_module.USER_PRESETS_NAME).write_text(
            '[presets.gate-dormant]\nlabel = "Dormant"\nmain_tier = "helm"\n'
            'codex_execution_policy = "standard"\nclaude_permission_mode = "standard"\n'
            'review_setup = "not-a-real-setup"\n'
        )
        try:
            dormant_config = launcher_module.load_config(dormant_profile)
            launcher_module.build_plan(dormant_config, "claude", "balanced")
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch let a dormant malformed preset block a valid one: {exc}")

    # A non-table `tiers` on the resolved host must be a LaunchError, not a TypeError:
    # build_plan only validates the launch host's tiers, never the opposite host's.
    list_tiers_config = {
        **config,
        "hosts": {**config["hosts"], "codex": {**config["hosts"]["codex"], "tiers": ["frontier"]}},
    }
    try:
        launcher_module.parse_review_binding(
            {"provider": "openai", "tier": "frontier"}, list_tiers_config, "gate"
        )
    except launcher_module.LaunchError:
        pass
    except Exception as exc:
        mark_fail(
            f"agent-launch raised {type(exc).__name__} for a non-table tiers value; "
            "a raw exception here reaches the CLI as a traceback"
        )
    else:
        mark_fail("agent-launch accepted a binding against a non-table tiers value")

    # A host the launcher has no effort vocabulary for cannot validate a binding.
    # Resolving the provider is not enough: this used to reach validate_effort and
    # escape as a raw KeyError, which reaches the CLI as a traceback.
    custom_host_config = {
        **config,
        "hosts": {**config["hosts"], "gate-custom": {**config["hosts"]["claude"], "provider": "gate-corp"}},
    }
    try:
        launcher_module.parse_review_binding(
            {"provider": "gate-corp", "tier": "frontier"}, custom_host_config, "gate"
        )
    except launcher_module.LaunchError as exc:
        if "no effort vocabulary" not in str(exc):
            mark_fail(f"agent-launch rejected an unvalidatable host for the wrong reason: {exc}")
    except Exception as exc:
        mark_fail(
            f"agent-launch raised {type(exc).__name__} for a host with no effort vocabulary; "
            "a raw exception here reaches the CLI as a traceback"
        )
    else:
        mark_fail("agent-launch credited a binding on a host it cannot validate efforts for")

    # The reader ships before the resolver, so a composable preset must fail loudly
    # rather than render through the legacy path as whichever name is absent (none).
    composable_config = {
        **config,
        "presets": {
            **config["presets"],
            "gate-composable": {
                "label": "Gate",
                "main_tier": "helm",
                "codex_execution_policy": "standard",
                "claude_permission_mode": "standard",
                "review": {"base": {"provider": "anthropic", "tier": "frontier"}},
            },
        },
    }
    # Stage 4 made authoring [review] the opt-in, so a composable preset now resolves
    # — but it must never travel the LEGACY path, which would project it as whichever
    # legacy name happened to be absent, i.e. silently as no review. The tell is that
    # `review_setup` stays None and the legacy route resolver returns nothing.
    try:
        composable_plan = launcher_module.build_plan(composable_config, "claude", "gate-composable")
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch rejected an opted-in composable preset: {exc}")
    else:
        if composable_plan["review_setup"] is not None:
            mark_fail(
                "agent-launch gave a composable preset a legacy review_setup of "
                f"{composable_plan['review_setup']!r}, so it would render through the legacy path"
            )
        if launcher_module.effective_review(composable_plan) != ([], [], None):
            mark_fail("agent-launch routed a composable preset through the legacy review enum")


@launcher_check
def launcher_module_api(fx):
    launcher_module = fx.launcher_module
    class ScriptedUI:
        def __init__(self):
            self.plan = None
            self.checked = False
            self.hub_visits = 0

        def set_plan(self, plan):
            self.plan = plan

        def choose(self, title, options, default, allow_back, preview=None,
                   corpus_lines=None, confirm=None):
            if title == "Mode":
                return "builder"
            if title == "Preset":
                if preview is not None:
                    balanced = launcher_module.setup_summary_lines(preview("balanced"))
                    deep = launcher_module.setup_summary_lines(preview("deep-review"))
                    if balanced == deep:
                        mark_fail(
                            "agent-launch Preset menu does not live-preview the "
                            "highlighted preset in the setup panel"
                        )
                return launcher_module.CUSTOM_PRESET
            if title == "Custom settings":
                self.hub_visits += 1
                if self.hub_visits == 1:
                    return "main"
                summary = launcher_module.setup_summary_lines(self.plan)
                option_by_value = {option.value: option for option in options}
                if "Main WORKHORSE | Review composable" not in " ".join(summary):
                    mark_fail(
                        "agent-launch did not project the selected main tier back "
                        "into the Custom hub"
                    )
                if not {"tier:frontier", "tier:workhorse", "start", "exit"} <= set(option_by_value):
                    mark_fail("agent-launch Custom hub is missing tier or final actions")
                if (
                    option_by_value["start"].label != "Start with these settings"
                    or option_by_value["start"].description
                    != "Confirm the complete setup shown above and continue to launch."
                    or option_by_value["exit"].label != "Exit without launching"
                    or option_by_value["exit"].description
                    != "Discard this launch and return to the shell."
                ):
                    mark_fail("agent-launch Custom final actions have mismatched semantics")
                self.checked = True
                return "start"
            if title == "Main tier":
                if preview is not None:
                    summary = launcher_module.setup_summary_lines(preview("sweep"))
                    # Substring, not list membership: the composable label carries the
                    # selected methods after the schema name, so the line is no longer a
                    # fixed string.
                    if "Main SWEEP | Review composable" not in " ".join(summary):
                        mark_fail(
                            "agent-launch Main tier menu does not live-preview the "
                            "highlighted tier in the setup panel"
                        )
                return "workhorse"
            raise AssertionError(f"unexpected scripted menu: {title}")

    scripted_ui = ScriptedUI()
    scripted_plan = launcher_module.select_plan(
        launch_profile,
        "codex",
        None,
        False,
        scripted_ui,
    )
    if not scripted_ui.checked or not scripted_plan.get("_launch_confirmed"):
        mark_fail("agent-launch scripted Custom hub did not reach final confirmation")

    # Software Engineer mode: its submenu is exactly Vanilla + Custom; Vanilla
    # stays the bare backend (no launch contract), while Custom re-bases to the
    # applied builder baseline rather than inheriting Vanilla's bare
    # short-circuit. Driven directly through pick_mode_and_preset — the root
    # mode picker is TTY-only, so a piped/non-TTY run defaults past it.
    class SEModeUI:
        def __init__(self, pick):
            self._pick = pick
            self.submenu_labels = None

        def set_plan(self, plan):
            pass

        def choose(self, title, options, default, allow_back, preview=None,
                   corpus_lines=None, confirm=None):
            if title == "Mode":
                if launcher_module.SWE_MODE not in {option.value for option in options}:
                    mark_fail("agent-launch root menu is missing the Software Engineer mode")
                return launcher_module.SWE_MODE
            if title == "Preset":
                self.submenu_labels = [option.label for option in options]
                return self._pick
            raise AssertionError(f"unexpected scripted menu: {title}")

    se_vanilla_ui = SEModeUI("vanilla")
    se_v_name, se_v_custom, _ = launcher_module.pick_mode_and_preset(
        launch_profile, "codex", se_vanilla_ui, None
    )
    if se_vanilla_ui.submenu_labels != ["Vanilla", "Custom"]:
        mark_fail(
            "agent-launch Software Engineer submenu must be exactly Vanilla + "
            f"Custom, got {se_vanilla_ui.submenu_labels}"
        )
    if se_v_custom or se_v_name != "vanilla":
        mark_fail("agent-launch SE -> Vanilla must select the vanilla preset directly")
    elif launcher_module.project_args(
        launcher_module.build_plan(launch_profile, "codex", se_v_name),
        materialize_agents=False,
    ):
        mark_fail("agent-launch SE -> Vanilla must project the bare backend (no launch contract)")

    se_custom_ui = SEModeUI(launcher_module.CUSTOM_PRESET)
    se_c_name, se_c_custom, _ = launcher_module.pick_mode_and_preset(
        launch_profile, "codex", se_custom_ui, None
    )
    if not se_c_custom:
        mark_fail("agent-launch SE -> Custom must request the settings hub")
    elif not launcher_module.project_args(
        launcher_module.build_plan(launch_profile, "codex", se_c_name),
        materialize_agents=False,
    ):
        mark_fail("agent-launch SE -> Custom must project an applied setup, not the bare backend")

    # Under a config with no builder presets, custom_base falls back to the SE
    # default (vanilla), so SE -> Custom builds a plan in SWE_MODE; select_plan
    # must force a customized plan out of that bare short-circuit so the user's
    # settings are not silently discarded. Driven through the real select_plan.
    class SECustomHubUI:
        def set_plan(self, plan):
            pass

        def choose(self, title, options, default, allow_back, preview=None,
                   corpus_lines=None, confirm=None):
            if title == "Mode":
                return launcher_module.SWE_MODE
            if title == "Preset":
                return launcher_module.CUSTOM_PRESET
            if title == "Custom settings":
                return "start"
            raise AssertionError(f"unexpected scripted menu: {title}")

        def prompt_text(self, label, default):
            return default

    stripped_profile = dict(launch_profile)
    stripped_profile["presets"] = {
        name: data
        for name, data in launch_profile["presets"].items()
        if name in ("vanilla", "session-distill")
    }
    stripped_custom_plan = launcher_module.select_plan(
        stripped_profile, "codex", None, False, SECustomHubUI()
    )
    if not launcher_module.project_args(stripped_custom_plan, materialize_agents=False):
        mark_fail(
            "agent-launch SE -> Custom under a no-builder-preset config must still "
            "project an applied setup (customization must not be silently discarded)"
        )

    # `--custom` with NO preset named. The flag and the picker are two sources for one
    # intent and the picker's boolean simply overwrote the flag, so choosing an ordinary
    # preset from the menu skipped customization entirely and launched the preset as
    # authored (round 22, #4). Driven through the real select_plan, with the picker
    # answering an ORDINARY preset — the combination neither existing case covers.
    class FlagCustomUI:
        def __init__(self):
            self.hub_visits = 0

        def set_plan(self, plan):
            pass

        def choose(self, title, options, default, allow_back, preview=None,
                   corpus_lines=None, confirm=None):
            if title == "Mode":
                return launcher_module.DEFAULT_PRESET_MODE
            if title == "Preset":
                return "balanced"
            if title == "Custom settings":
                self.hub_visits += 1
                return "start"
            raise AssertionError(f"unexpected scripted menu: {title}")

        def prompt_text(self, label, default):
            return default

    for requested, want_hub in ((True, True), (False, False)):
        flag_ui = FlagCustomUI()
        flag_plan = launcher_module.select_plan(
            launch_profile, "codex", None, requested, flag_ui
        )
        opened = flag_ui.hub_visits > 0
        if opened != want_hub or flag_plan["label"].startswith("Custom (") != want_hub:
            mark_fail(
                f"agent-launch --custom={requested} with the picker choosing an ordinary "
                f"preset opened the settings hub {opened} and labelled the plan "
                f"{flag_plan['label']!r}; the flag means 'customize after selection' and is "
                f"not a default the picker replaces"
            )

    # Custom's arbitrary baseline is never a ROUTED preset. `distill` is a mode that opens
    # a hub, and with `session-distill` the only preset left it became the Custom baseline:
    # the launch carried that preset's mission, its `distill!` trigger and mode=distill
    # under the label "Custom" (round 22, #5). Refused by name instead. Control: the same
    # stripped shape with one NON-routed preset still reaches the hub.
    class RoutedFallbackUI:
        def set_plan(self, plan):
            pass

        def choose(self, title, options, default, allow_back, preview=None,
                   corpus_lines=None, confirm=None):
            if title == "Mode":
                return launcher_module.DEFAULT_PRESET_MODE
            if title == "Preset":
                return launcher_module.CUSTOM_PRESET
            if title == "Custom settings":
                return "start"
            raise AssertionError(f"unexpected scripted menu: {title}")

        def prompt_text(self, label, default):
            return default

    for only, expect_refusal in (("session-distill", True), ("vanilla", False)):
        routed_profile = dict(launch_profile)
        routed_profile["presets"] = {only: launch_profile["presets"][only]}
        if len(routed_profile["presets"]) != 1:
            mark_fail(f"agent-launch routed-baseline subject is not a single preset ({only})")
        try:
            routed_plan = launcher_module.select_plan(
                routed_profile, "codex", None, False, RoutedFallbackUI()
            )
        except launcher_module.LaunchError as exc:
            if not expect_refusal:
                mark_fail(
                    f"agent-launch Custom under a {only}-only profile was refused: {exc}"
                )
            elif "no launchable baseline" not in str(exc):
                mark_fail(
                    f"agent-launch Custom under a routed-only profile was refused for "
                    f"another reason: {exc}"
                )
        else:
            if expect_refusal:
                mark_fail(
                    f"agent-launch Custom took the routed preset {routed_plan['preset']!r} as "
                    f"its baseline (mode={routed_plan['mode']!r}, "
                    f"trigger={routed_plan.get('trigger')!r}) — a mode that opens a hub is "
                    f"not a setup to start from"
                )
            elif routed_plan.get("mode") == launcher_module.DISTILL_MODE:
                mark_fail("agent-launch Custom inherited the distill mode from its baseline")

    # Version line: version_label reads the deployed version marker
    # ($STATE_DIR/version.json) that install writes from package.json. A
    # present marker yields "agent-bios v<version> · <releaseDate>"; an absent
    # one yields None (uninstalled / dev checkout, so the panel shows no line).
    saved_version_path = launcher_module.VERSION_INFO_PATH
    try:
        version_marker = pathlib.Path(tempfile.mkdtemp()) / "version.json"
        version_marker.write_text('{"version": "9.9.9", "releaseDate": "2026-01-02"}')
        launcher_module.VERSION_INFO_PATH = version_marker
        if launcher_module.version_label() != "agent-bios v9.9.9 · 2026-01-02":
            mark_fail(
                "agent-launch version_label wrong with a marker present: "
                f"{launcher_module.version_label()!r}"
            )
        launcher_module.VERSION_INFO_PATH = version_marker.parent / "absent.json"
        if launcher_module.version_label() is not None:
            mark_fail("agent-launch version_label must be None when the marker is absent")
    finally:
        launcher_module.VERSION_INFO_PATH = saved_version_path


@launcher_check
def launcher_global_instruction_option(fx):
    """Global-instruction exclusion is one plan value from CLI through Custom/save/argv.

    The fixture replaces only the private snapshot and host composition boundaries; the
    subject is the real launcher's `main -> select_plan -> customize -> save_preset`
    path. A live Claude session would add model and account authority without testing
    this deterministic hand-off, so it is deliberately outside this gate's realization.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    original_private = launcher_module.private_corpus_enabled
    original_store = launcher_module.corpus_store
    original_choose = launcher_module.choose
    original_prompt = launcher_module.prompt_text
    original_catalog = launcher_module._CATALOG
    original_catalog_en = launcher_module._CATALOG_EN
    absent = object()
    original_session = sys.modules.get("corpus_session", absent)
    original_package_root = os.environ.get("AGENT_BIOS_PACKAGE_ROOT")
    composed = []
    snapshots = []
    shared_presets = launcher_module.user_presets_path(fx.fake_profile)
    shared_before = shared_presets.read_bytes() if shared_presets.is_file() else None
    # Save As is deliberately real below, but it must not change the profile subsequent
    # checks share. A sibling config gets the same deployed catalog and its own local
    # presets home. The unchanged assertion in `finally` is the regression control: the
    # previous subject wrote `global-exclude-saved` beside fx.fake_profile and fails it.
    option_root = fx.tmp / "global-instruction-option"
    option_root.mkdir()
    option_profile = option_root / fx.fake_profile.name
    shutil.copy2(fx.fake_profile, option_profile)
    shutil.copytree(fx.fake_profile.with_name("i18n"), option_root / "i18n")

    class FixtureStore:
        state_root = fx.tmp / "private-state"

        def snapshot(self, host, selected, dry_run, native):
            snapshots.append((host, selected, dry_run, native))
            return {
                "instruction_text": "PRIVATE_CORPUS_FIXTURE",
                "content_ref": "fixture-snapshot",
                "assets": {},
                "unavailable": [],
            }

    def compose(command, argv, host, snapshot, **kwargs):
        composed.append(kwargs.get("include_global_instructions"))
        return list(argv)

    def run_main(arguments):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return launcher_module.main(arguments)

    try:
        # The un-authored default must stay absent from a saved preset, while False is
        # serialized and re-read as False. `save_preset` below exercises the latter on
        # its real writer/reader path.
        base_config = launcher_module.load_config(option_profile)
        base_plan = launcher_module.build_plan(base_config, "claude", "balanced")
        default_fields, _, _ = launcher_module.preset_from_plan(
            base_plan, base_config, "global-default"
        )
        if "include_global_instructions" in default_fields:
            mark_fail(
                "agent-launch serializes the default global-instruction inclusion instead "
                "of preserving the absent=True schema default"
            )

        launcher_module.private_corpus_enabled = lambda: True
        launcher_module.corpus_store = lambda: FixtureStore()
        sys.modules["corpus_session"] = types.SimpleNamespace(compose_argv=compose)

        def custom_choices(final_action, setting, saved_name=None):
            actions = iter(("global-instructions", final_action))

            def choose(title, options, default, ui=None, allow_back=False,
                       preview=None, corpus_lines=None, confirm=None):
                option_by_value = {option.value: option for option in options}
                if title == launcher_module.t("custom.title"):
                    if "global-instructions" not in option_by_value:
                        mark_fail("agent-launch Custom hub has no global-instruction row")
                        return "exit"
                    return next(actions)
                if title == launcher_module.t("global-instructions.title"):
                    if default != "exclude" or not option_by_value["include"].enabled:
                        mark_fail(
                            "agent-launch --exclude-global-instructions did not seed "
                            "Custom with the selectable Exclude choice"
                        )
                    return setting
                raise AssertionError(f"unexpected global-instruction fixture menu: {title}")

            launcher_module.choose = choose
            launcher_module.prompt_text = lambda label, default, ui=None: saved_name or default

        # First save the visible Exclude choice. This proves the CLI seeds Custom before
        # Save As runs, and drives the real serializer and profile reader.
        custom_choices("save", "exclude", "global-exclude-saved")
        if run_main([
            "--config", str(option_profile), "--no-tui", "--dry-run", "--preset",
            "balanced", "--custom", "--exclude-global-instructions", "claude",
        ]) != 0:
            mark_fail("agent-launch could not save a CLI-seeded global Exclude Custom preset")
        try:
            saved = launcher_module.load_config(option_profile)
            if launcher_module.build_plan(
                saved, "claude", "global-exclude-saved"
            )["include_global_instructions"] is not False:
                mark_fail("agent-launch saved global Exclude did not reload as False")
        except Exception as exc:
            mark_fail(f"agent-launch could not read its saved global Exclude preset: {exc}")

        # A final visible Include choice wins over the CLI's initial False. If main
        # reapplies the flag after Custom, compose receives False and this fails.
        custom_choices("start", "include")
        if run_main([
            "--config", str(option_profile), "--no-tui", "--dry-run", "--preset",
            "balanced", "--custom", "--exclude-global-instructions", "claude",
        ]) != 0:
            mark_fail("agent-launch could not start Custom after selecting global Include")
        if composed != [False, True]:
            mark_fail(
                "agent-launch global-instruction choice did not reach compose_argv in "
                f"Custom/save order (got {composed!r}, want [False, True])"
            )
        if len(snapshots) != 2 or any(host != "claude" for host, *_ in snapshots):
            mark_fail(
                "agent-launch global-instruction Custom launches did not take the expected "
                f"private Claude snapshot path: {snapshots!r}"
            )

        # These fail before either the snapshot or backend boundary. Resume's recorded
        # choice is immutable, while bare/Vanilla/Codex cannot accept this override.
        before_refusals = (len(snapshots), len(composed))
        for label, arguments, expected in (
            (
                "bare",
                ["--config", str(option_profile), "--no-tui", "--exclude-global-instructions", "claude"],
                "corpus launch options require",
            ),
            (
                "Vanilla",
                ["--config", str(option_profile), "--no-tui", "--preset", "vanilla", "--exclude-global-instructions", "claude"],
                "unavailable for Vanilla",
            ),
            (
                "Codex",
                ["--config", str(option_profile), "--no-tui", "--preset", "balanced", "--exclude-global-instructions", "codex"],
                "does not support a safe way",
            ),
            (
                "resume",
                ["--config", str(option_profile), "--no-tui", "--resume-session", "fixture-session", "--exclude-global-instructions", "claude"],
                "resume uses its pinned",
            ),
        ):
            try:
                run_main(arguments)
            except launcher_module.LaunchError as exc:
                if expected not in str(exc):
                    mark_fail(
                        f"agent-launch {label} global-instruction refusal was {exc!r}, "
                        f"want wording containing {expected!r}"
                    )
            else:
                mark_fail(f"agent-launch accepted --exclude-global-instructions for {label}")
        if (len(snapshots), len(composed)) != before_refusals:
            mark_fail(
                "agent-launch reached private snapshot or composition for a refused "
                "global-instruction override"
            )
    except Exception as exc:
        mark_fail(f"agent-launch global-instruction fixture crashed: {type(exc).__name__}: {exc}")
    finally:
        shared_after = shared_presets.read_bytes() if shared_presets.is_file() else None
        if shared_after != shared_before:
            mark_fail(
                "agent-launch global-instruction option check changed the shared fixture "
                "presets.local.toml; subsequent launcher scenarios are no longer isolated"
            )
        launcher_module.private_corpus_enabled = original_private
        launcher_module.corpus_store = original_store
        launcher_module.choose = original_choose
        launcher_module.prompt_text = original_prompt
        launcher_module._CATALOG = original_catalog
        launcher_module._CATALOG_EN = original_catalog_en
        if original_package_root is None:
            os.environ.pop("AGENT_BIOS_PACKAGE_ROOT", None)
        else:
            os.environ["AGENT_BIOS_PACKAGE_ROOT"] = original_package_root
        if original_session is absent:
            sys.modules.pop("corpus_session", None)
        else:
            sys.modules["corpus_session"] = original_session


@contextlib.contextmanager
def launcher_fixture(launcher_module):
    """The shared harness: a fake backend, a rewritten profile, and a pty driver."""
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)
        backend = tmp / "backend"
        argv_log = tmp / "backend.argv"
        backend.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$@\" > \"$FAKE_LAUNCH_ARGV\"\n"
            "printf 'backend-output\\n'\n"
            "exit \"${FAKE_LAUNCH_STATUS:-0}\"\n"
        )
        backend.chmod(0o755)
        fake_profile = tmp / "profiles.toml"
        # UI text catalogs are config siblings; the interactive pty legs render the
        # mode screen through them, so the fixture deploys them the way install
        # does. Copied, not symlinked: the fixture mirrors a real deployment.
        shutil.copytree(pathlib.Path("launch/i18n"), tmp / "i18n")
        profile_text = launch_profile_path.read_text()
        profile_text = profile_text.replace('command = "codex"', f"command = {json.dumps(str(backend))}", 1)
        profile_text = profile_text.replace('command = "claude"', f"command = {json.dumps(str(backend))}", 1)
        portable_profile_text = profile_text
        for tier in ("frontier", "workhorse", "sweep"):
            profile_text = profile_text.replace(
                f'${{CODEX_HOME}}/agents/{tier}.toml', str((agent_dir / f"{tier}.toml").resolve()), 1
            )
        fake_profile.write_text(profile_text)
        fake_data = tomllib.loads(profile_text)
        fake_commands = {
            host: binding.get("command") for host, binding in fake_data.get("backends", {}).items()
        }
        if set(fake_commands) != {"codex", "claude"} or any(
            command != str(backend) for command in fake_commands.values()
        ):
            mark_fail(f"fake launch profile did not replace every backend: {fake_commands!r}")
            fake_profile = pathlib.Path("/nonexistent/unsafe-fixture")
        env = os.environ.copy()
        version_fixture = tmp / "version.json"
        version_fixture.write_text('{"version": "9.9.9", "releaseDate": "2026-01-02"}')
        # Operator state is pinned into the fixture, not merely hoped absent. The
        # session-distill nudge and the corpus-status panel both resolve through
        # Path.home(), so on a machine whose history has crossed the nudge threshold
        # they add a line to every pty transcript this fixture captures — the exact
        # shape that made the review-routing golden report drift with no routing
        # change (2026-08-27). Both accept an override and treat a missing file as
        # nothing to say, so a path inside tmp makes these legs independent of how
        # many sessions whoever runs the gate has accumulated.
        env.update(
            FAKE_LAUNCH_ARGV=str(argv_log),
            AGENT_LAUNCH_LANG="en",
            AGENT_LAUNCH_CONFIG=str(fake_profile),
            XDG_CACHE_HOME=str(tmp / "cache"),
            AGENT_LAUNCH_VERSION_FILE=str(version_fixture),
            AGENT_BIOS_SESSION_DISTILL_STATE=str(tmp / "no-distill-state.json"),
            AGENT_BIOS_CORPUS_STATUS=str(tmp / "no-corpus-status.json"),
        # Pinned for BOTH reasons, and the second is the one that bites: an operator's
        # real cache would print "update vX available" into every transcript and drift
        # the golden, and an unpinned launcher would SPAWN `agent-bios update --check`
        # — a gate that reaches the network is not a gate. The =0 is the belt to the
        # path's braces: even pointed at a missing file the check must not fire.
        AGENT_BIOS_UPDATE_CHECK_STATE=str(tmp / "no-update-check.json"),
        AGENT_BIOS_UPDATE_CHECK="0",
        )

        pty_env = env.copy()

        def run_picker_scenario(
            name,
            steps,
            # Measured idle, every scenario in this fixture finishes in 0.03-0.35 s, so 3 s was
            # already a 9-100x margin — and it was not enough. The install scenarios run a
            # NESTED umbrella, which runs this fixture again while the outer one is running, and
            # under that load a picker missed the deadline and was killed. F-15 was that kill,
            # reported for two years as a launcher verdict. The deadline only costs time when
            # something genuinely hangs, so it buys headroom at no cost to a passing run.
            timeout=15,
            term="xterm-256color",
            host="codex",
            config_path=fake_profile,
            dry_run=True,
            env_overrides=None,
        ):
            scenario_env = pty_env.copy()
            scenario_env["TERM"] = term
            # The fixture pins AGENT_LAUNCH_LANG=en so no scenario depends on
            # ambient user state; a per-language leg overrides it here rather than
            # reaching for the user preference file, which a gate must never read.
            if env_overrides:
                scenario_env.update(env_overrides)
            picker_pid, master = pty.fork()
            if picker_pid == 0:
                try:
                    child_argv = [
                        sys.executable,
                        str(launcher),
                        "--config",
                        str(config_path),
                    ]
                    if dry_run:
                        child_argv.append("--dry-run")
                    child_argv.append(host)
                    os.execve(
                        sys.executable,
                        child_argv,
                        scenario_env,
                    )
                except Exception:
                    os._exit(127)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))
            transcript = bytearray()
            picker_status = None
            search_offset = 0

            def read_until(token):
                nonlocal search_offset
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    found = transcript.find(token, search_offset)
                    if found >= 0:
                        search_offset = found + len(token)
                        return True
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if not ready:
                        continue
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    transcript.extend(chunk)
                found = transcript.find(token, search_offset)
                if found >= 0:
                    search_offset = found + len(token)
                    return True
                return False

            try:
                for expected, key in steps:
                    if not read_until(expected):
                        mark_fail(f"agent-launch {name} missing {expected.decode()!r}")
                        break
                    if isinstance(key, tuple):
                        rows, columns = key[:2]
                        if len(key) == 3:
                            os.write(master, key[2])
                            time.sleep(0.1)
                        fcntl.ioctl(
                            master,
                            termios.TIOCSWINSZ,
                            struct.pack("HHHH", rows, columns, 0, 0),
                        )
                        try:
                            os.kill(picker_pid, signal.SIGWINCH)
                        except ProcessLookupError:
                            pass
                    else:
                        os.write(master, key)
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.05)
                    if ready:
                        try:
                            chunk = os.read(master, 4096)
                        except OSError:
                            chunk = b""
                        if chunk:
                            transcript.extend(chunk)
                    waited_pid, raw_status = os.waitpid(picker_pid, os.WNOHANG)
                    if waited_pid:
                        picker_status = os.waitstatus_to_exitcode(raw_status)
                        break
                if picker_status is not None:
                    while select.select([master], [], [], 0)[0]:
                        try:
                            chunk = os.read(master, 4096)
                        except OSError:
                            break
                        if not chunk:
                            break
                        transcript.extend(chunk)
            finally:
                if picker_status is None:
                    try:
                        os.kill(picker_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, raw_status = os.waitpid(picker_pid, 0)
                    picker_status = os.waitstatus_to_exitcode(raw_status)
                    # Say who killed it. Without this the -9 flows into the semantic
                    # assertions below and the suite reports "Custom Start was not the final
                    # launch confirmation" — the launcher blamed for the harness's own
                    # deadline, which is a false signal by this repo's defect criterion and is
                    # what made F-15 unreadable for as long as it was.
                    mark_fail(
                        f"agent-launch picker scenario {name!r} did not exit within "
                        f"{timeout}s and was killed by this harness — every assertion about "
                        f"this scenario below is about a killed process, not a launcher "
                        f"verdict")
                os.close(master)
            return bytes(transcript), picker_status
        with launcher_environment(tmp / "native-inputs", pathlib.Path.cwd()) as native:
            env.update(native)
            pty_env.update(native)
            yield types.SimpleNamespace(
                argv_log=argv_log,
                backend=backend,
                env=env,
                fake_commands=fake_commands,
                fake_data=fake_data,
                fake_profile=fake_profile,
                launcher_module=launcher_module,
                portable_profile_text=portable_profile_text,
                profile_text=profile_text,
                pty_env=pty_env,
                run_picker_scenario=run_picker_scenario,
                tmp=tmp,
            )


@launcher_check
def tui_picker(fx):
    argv_log, env, fake_profile, profile_text, run_picker_scenario, tmp = fx.argv_log, fx.env, fx.fake_profile, fx.profile_text, fx.run_picker_scenario, fx.tmp
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    # Root menu is now a Mode picker (Software Engineer / Builder / Session
    # distill); Builder is the default highlight and lists Custom. Reaching
    # Custom means: Enter the root to open Builder's preset submenu, then
    # step down through its fixed presets (Balanced default-highlighted).
    # The footer is how a step tells which screen is drawn, so the markers are ASKED FOR
    # rather than restated: a copy here would be a second authority that drifts silently
    # the next time the key line is reworded, and the symptom is a scenario that waits
    # fifteen seconds for text nothing prints.
    #
    # Read against the English catalog on disk, not the module's active one — the
    # launcher fixture is order-dependent, and a leg that left Korean loaded would build
    # Korean markers for a subprocess rendering English.
    english = launcher_module._module_catalog("en")
    if not english:
        mark_fail("no English UI catalog beside the launcher — every marker below would "
                  "be a key name and every scenario would time out")
        return
    real_catalog = launcher_module._CATALOG
    launcher_module._CATALOG = english
    try:
        ROOT = launcher_module.menu_footer(False, False).encode()
        INTERIOR = launcher_module.menu_footer(True, False).encode()
        chrome = tuple(launcher_module.t(key).encode() for key in
                       ("tui.setup.title", "tui.detail.title"))
        options_header = launcher_module.t("tui.options.header").split("{")[0].encode()
    finally:
        launcher_module._CATALOG = real_catalog
    # Whole lines, so neither can match the other's screen. Asserted rather than assumed
    # — the exclusivity is a property of the wording, and the wording now lives in a
    # catalog that a translator edits.
    # An empty or near-empty marker is the vacuous case that matters most here:
    # `transcript.find(b"")` returns 0, so every step would match instantly and the whole
    # suite below would pass without driving anything.
    if min(len(ROOT), len(INTERIOR)) < 20 or not options_header or not all(chrome):
        mark_fail(f"a screen marker came back empty or too short to identify a screen "
                  f"(root={ROOT!r} interior={INTERIOR!r} header={options_header!r} "
                  f"chrome={chrome!r}); every scenario below would match on nothing")
        return
    if ROOT in INTERIOR or INTERIOR in ROOT:
        mark_fail(f"the two menu footers are not mutually exclusive ({ROOT!r} vs "
                  f"{INTERIOR!r}); a marker matching both screens desynchronises every "
                  "scenario below")
        return
    left, down = b"\x1b[D", b"\x1b[B"
    baseline = launcher_module.build_plan(launcher_module.load_config(fake_profile), "codex", "balanced")
    models = baseline["available_models"]
    frontier_model = baseline["tiers"]["frontier"]["model"]
    workhorse_model = baseline["tiers"]["workhorse"]["model"]
    frontier_effort = baseline["frontier_effort"]
    workhorse_effort = baseline["tiers"]["workhorse"]["effort"]

    def move_to(choices, source, target):
        distance = choices.index(target) - choices.index(source)
        return (down if distance >= 0 else b"\x1b[A") * abs(distance)

    other_from_frontier = move_to([*models, "__other__"], frontier_model, "__other__")
    frontier_input = english["tui.input.current"].format(value=frontier_model).encode()

    def description_marker(key):
        # A short prefix from the live catalog survives terminal wrapping without
        # freezing a translator's prose into this navigation script.
        return " ".join(english[key].split()[:5]).encode()

    open_custom_steps = (
        (ROOT, b"\r"),
        (description_marker("preset.balanced.description"), b""),
        (INTERIOR, b"\x1b[B"),
        (description_marker("preset.deep-review.description"), b"\x1b[B"),
        (description_marker("preset.fast-batch.description"), b"\x1b[B"),
        (description_marker("preset.solo.description"), b"\x1b[B"),
        (description_marker("preset.custom.description"), b"\r"),
    )

    def hub_choice(offset):
        return (b"Custom settings", down * offset + b"\r")

    transcript, picker_status = run_picker_scenario(
        "fixed layout",
        ((ROOT, b"\x1b[6~"), (b"agent-bios v9.9.9", b"q")),
    )
    if picker_status != 130:
        mark_fail(f"agent-launch fixed layout returned {picker_status}, want 130")
    layout_tokens = (
        chrome[0],
        b"FRONTIER",
        b"HELM",
        b"WORKHORSE",
        b"SWEEP",
        chrome[1],
        description_marker("mode.builder.description"),
        options_header,
    )
    positions = {token: transcript.find(token) for token in layout_tokens}
    if any(position < 0 for position in positions.values()):
        missing = [token.decode() for token, position in positions.items() if position < 0]
        mark_fail(f"agent-launch fixed layout missing sections: {missing!r}")
    elif not (
        positions[chrome[0]]
        < min(positions[token] for token in (b"FRONTIER", b"HELM", b"WORKHORSE", b"SWEEP"))
        < positions[chrome[1]]
        < positions[description_marker("mode.builder.description")]
        < positions[options_header]
    ):
        mark_fail("agent-launch layout is not setup then description then options")
    if b"agent-bios v9.9.9" not in transcript:
        mark_fail("agent-launch does not show the deployed version line in the setup panel")

    _, picker_status = run_picker_scenario(
        "root escape cancellation",
        ((ROOT, b"\x1b"),),
    )
    if picker_status != 130:
        mark_fail(f"agent-launch root Esc returned {picker_status}, want 130")

    # Root Mode picker navigation: Left from the Builder preset submenu returns to a
    # freshly re-rendered Mode picker (Builder's own description reappears) rather than
    # cancelling the launcher outright.
    _, picker_status = run_picker_scenario(
        "mode picker navigation",
        (
            (ROOT, b"\r"),
            (description_marker("preset.balanced.description"), left),
            (description_marker("mode.builder.description"), b"q"),
        ),
    )
    if picker_status != 130:
        mark_fail(f"agent-launch mode picker Left-back returned {picker_status}, want 130")

    # And the key that used to mean back now means abort, everywhere. Without this the
    # suite would prove only that Left goes back — it would not notice Escape quietly
    # keeping its old meaning, which is the half of the change a user feels.
    _, picker_status = run_picker_scenario(
        "interior escape aborts",
        (
            (ROOT, b"\r"),
            (description_marker("preset.balanced.description"), b"\x1b"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch Esc from an interior screen returned {picker_status}, want "
            "130 — Escape aborts the session rather than stepping up a level"
        )

    if argv_log.exists():
        argv_log.unlink()
    _, picker_status = run_picker_scenario(
        "launch confirmation q cancellation",
        (
            (ROOT, b"\r"),
            (description_marker("preset.balanced.description"), b"\r"),
            (b"Launch? [Y/n/q]:", b"q\r"),
        ),
        dry_run=False,
    )
    fired = conditions_that_held(
        picker_exit_not_130=picker_status != 130,
        argv_log_written=argv_log.exists(),
    )
    if fired:
        mark_fail(f"agent-launch final confirmation q executed the backend: {fired} "
                  f"(picker exit {picker_status})")

    if argv_log.exists():
        argv_log.unlink()
    transcript, picker_status = run_picker_scenario(
        "Custom final start",
        (
            *open_custom_steps,
            (b"Custom settings", down * 9),
            (b"Confirm the complete setup shown above", b"\r"),
        ),
        dry_run=False,
    )
    fired = conditions_that_held(
        picker_exited_nonzero=picker_status != 0,
        argv_log_absent=not argv_log.exists(),
        numbered_prompt_present=b"Launch? [Y/n/q]:" in transcript,
        confirmation_line_absent=b"Start with these settings" not in transcript,
    )
    if fired:
        mark_fail(f"agent-launch Custom Start was not the final launch confirmation: "
                  f"{fired} (picker exit {picker_status})")

    if argv_log.exists():
        argv_log.unlink()
    transcript, picker_status = run_picker_scenario(
        "Custom explicit exit",
        (
            *open_custom_steps,
            (b"Custom settings", down * 10),
            (b"Discard this launch and return to the shell", b"\r"),
        ),
        dry_run=False,
    )
    fired = conditions_that_held(
        picker_exit_not_130=picker_status != 130,
        argv_log_written=argv_log.exists(),
        exit_line_absent=b"Exit without launching" not in transcript,
    )
    if fired:
        mark_fail(f"agent-launch Custom Exit executed the backend: {fired} "
                  f"(picker exit {picker_status})")

    transcript, picker_status = run_picker_scenario(
        "Custom escape back",
        (
            *open_custom_steps,
            (b"Custom settings", left),
            (description_marker("preset.balanced.description"), b"\r"),
        ),
    )
    if picker_status != 0 or b"Preset         Balanced" not in transcript:
        mark_fail("agent-launch Custom Left did not return to the preset picker")

    _, picker_status = run_picker_scenario(
        "Custom interior left back",
        (
            *open_custom_steps,
            (b"Custom settings", b"\r"),
            (b"Primary orchestrator for planning, delegation", left),
            (b"Choose the primary orchestrator used for this session", b"q"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch interior Left back returned {picker_status}, want 130"
        )

    _, picker_status = run_picker_scenario(
        "current setup update",
        (
            *open_custom_steps,
            (b"Custom settings", b"\r"),
            (b"Primary orchestrator for planning, delegation", b"\x1b[B"),
            (b"high-volume implementation", b"\r"),
            (b"Main tier: WORKHORSE", b"q"),
        ),
    )
    if picker_status != 130:
        mark_fail("agent-launch main-tier selection flow did not reach Review setup")

    transcript, picker_status = run_picker_scenario(
        "Custom tier hub return",
        (
            *open_custom_steps,
            hub_choice(4),
            (b"Other (enter a model id)", move_to(models, frontier_model, workhorse_model) + b"\r"),
            (description_marker(f"effort.{frontier_effort}.description"),
             move_to([o.value for o in launcher_module.effort_options("codex", workhorse_model) if o.enabled],
                     frontier_effort, "ultra") + b"\r"),
            (f"FRONTIER: {workhorse_model} / ultra".encode(), down * 2 + b"\r"),
            (b"Other (enter a model id)", move_to([*models, "__other__"], workhorse_model, "__other__") + b"\r"),
            (english["tui.input.current"].format(value=workhorse_model).encode(), b"workhorse-local\r"),
            (description_marker(f"effort.{workhorse_effort}.description"),
             move_to([o.value for o in launcher_module.effort_options("codex", "workhorse-local") if o.enabled],
                     workhorse_effort, "xhigh") + b"\r"),
            (b"WORKHORSE: workhorse-local / xhigh", down * 3 + b"\r"),
        ),
    )
    if picker_status != 0:
        mark_fail(
            f"agent-launch tier-to-hub flow returned {picker_status}, want 0"
        )
    for expected in (
        f"FRONTIER       {workhorse_model} · ultra".encode(),
        "WORKHORSE      workhorse-local · xhigh".encode(),
    ):
        if expected not in transcript:
            mark_fail(
                "agent-launch tier-to-hub flow did not visit "
                f"{expected.decode()!r}"
            )

    numbered_interior_back = invoke(
        [
            sys.executable,
            str(launcher),
            "--config",
            str(fake_profile),
            "--preset",
            "balanced",
            "--custom",
            "--dry-run",
            "codex",
        ],
        input_text="1\nb\n10\n",
        env=env,
    )
    if (
        numbered_interior_back.returncode != 0
        or "b back | q cancel" not in numbered_interior_back.stdout
        or numbered_interior_back.stdout.count("\nCustom settings\n") < 2
        or "Preset         Custom (Balanced)" not in numbered_interior_back.stdout
    ):
        mark_fail("agent-launch numbered interior back did not return to Custom hub")

    _, picker_status = run_picker_scenario(
        "Custom model q cancellation",
        (
            *open_custom_steps,
            hub_choice(4),
            (b"Other (enter a model id)", other_from_frontier + b"\r"),
            (frontier_input, b"q\r"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch curses model q returned {picker_status}, want 130"
        )

    _, picker_status = run_picker_scenario(
        "Custom model Esc cancellation",
        (
            *open_custom_steps,
            hub_choice(4),
            (b"Other (enter a model id)", other_from_frontier + b"\r"),
            (frontier_input, b"\x1b"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch curses model Esc returned {picker_status}, want 130"
        )

    _, picker_status = run_picker_scenario(
        "Custom q-prefixed model preservation",
        (
            *open_custom_steps,
            hub_choice(4),
            (b"Other (enter a model id)", other_from_frontier + b"\r"),
            (frontier_input, b"qwen\r"),
            (b"Options (", left),
            (b"Other (enter a model id)", b"\r"),
            (b"Current value: qwen", b"\x1b"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch q-prefixed model returned {picker_status}, want 130"
        )

    _, picker_status = run_picker_scenario(
        "Custom model Ctrl-C cancellation",
        (
            *open_custom_steps,
            hub_choice(4),
            (b"Other (enter a model id)", other_from_frontier + b"\r"),
            (frontier_input, b"\x03"),
        ),
    )
    if picker_status != 130:
        mark_fail(
            f"agent-launch curses model Ctrl-C returned {picker_status}, want 130"
        )

    numbered_model_q = invoke(
        [
            sys.executable,
            str(launcher),
            "--config",
            str(fake_profile),
            "--preset",
            "balanced",
            "--custom",
            "--dry-run",
            "codex",
        ],
        input_text="5\nq\n",
        env=env,
    )
    if numbered_model_q.returncode != 130 or "Traceback" in numbered_model_q.stderr:
        mark_fail("agent-launch numbered model q did not cancel cleanly")

    _, picker_status = run_picker_scenario(
        "arrow picker cancellation",
        (*open_custom_steps, (b"Custom settings", b"\x03")),
    )
    if picker_status != 130:
        mark_fail(f"agent-launch arrow picker returned {picker_status}, want 130")

    transcript, picker_status = run_picker_scenario(
        "Custom completion",
        (*open_custom_steps, hub_choice(9)),
    )
    if picker_status != 0:
        mark_fail(f"agent-launch Custom completion returned {picker_status}, want 0")
    for expected in (
        b"Preset         Custom (Balanced)",
        b"Main           HELM",
        b"Review setup   composable",
        b"Execution      Codex bypass",
    ):
        if expected not in transcript:
            mark_fail(f"agent-launch Custom projection missing {expected.decode()!r}")

    claude_auto_profile = tmp / "claude-auto.toml"
    claude_auto_profile.write_text(
        profile_text.replace(
            'claude_permission_mode = "bypassPermissions"',
            'claude_permission_mode = "auto"',
            1,
        )
    )
    transcript, picker_status = run_picker_scenario(
        "Claude Custom auto preservation",
        (*open_custom_steps, hub_choice(9)),
        host="claude",
        config_path=claude_auto_profile,
    )
    if picker_status != 0:
        mark_fail(
            f"agent-launch Claude Custom auto returned {picker_status}, want 0"
        )
    for expected in (
        b"Preset         Custom (Balanced)",
        b"Execution      Claude auto",
        b'"--permission-mode", "auto"',
    ):
        if expected not in transcript:
            mark_fail(
                "agent-launch Claude Custom auto projection missing "
                f"{expected.decode()!r}"
            )
    if b'"--dangerously-skip-permissions"' in transcript:
        mark_fail("agent-launch Claude Custom auto escalated to permission bypass")

    claude_dont_ask_profile = tmp / "claude-dont-ask.toml"
    claude_dont_ask_profile.write_text(
        profile_text.replace(
            'claude_permission_mode = "bypassPermissions"',
            'claude_permission_mode = "dontAsk"',
            1,
        )
    )
    dont_ask = invoke(
        [
            sys.executable,
            str(launcher),
            "--config",
            str(claude_dont_ask_profile),
            "--preset",
            "balanced",
            "--custom",
            "--dry-run",
            "claude",
        ],
        input_text="10\n",
        env=env,
    )
    if dont_ask.returncode != 0:
        mark_fail(
            "agent-launch numbered Claude Custom dontAsk failed: "
            f"{dont_ask.stderr.strip()}"
        )
    else:
        dont_ask_argv = json.loads(dont_ask.stdout.splitlines()[-1])
        if dont_ask_argv[-2:] != ["--permission-mode", "dontAsk"]:
            mark_fail(
                "agent-launch numbered Claude Custom did not preserve dontAsk"
            )


@launcher_check
def launcher_renders_each_language(fx):
    """ko/ja reach a terminal, not merely a catalog.

    The key-set gate proves the three catalogs agree and that every slot survives
    translation. Neither claim needs a byte of Korean to have been drawn: a launcher
    that ignored the selected language outright would satisfy both. This drives the
    real root screen under a pty once per language and requires that language's OWN
    strings in the transcript. Expectations are read from the catalog the fixture
    deployed, at gate runtime, so a retranslation updates this gate by updating the
    catalog — no expected bytes are maintained here to drift.

    Two things this leg had to be taught, both measured rather than assumed:

    * Wrapping breaks a match, not glyph width. At the harness's 100 columns every
      language renders its short strings contiguously, while a long description wraps
      in whichever language is wordiest — which measured as English, not CJK, since
      Korean and Japanese say the same thing in fewer characters. Evidence keys are
      therefore titles and labels, never descriptions.
    * A key whose translation equals its English is not evidence. `mode.swe.label` is
      "Software Engineer" in all three catalogs because it names a product. The leg
      fails when an evidence key stops differing from English, so it cannot decay into
      asserting English and calling that a Korean render.

    The control plants a sentinel into the deployed catalog and requires the
    transcript to follow it — sentinel present AND the real string gone. A screen that
    had stopped rendering, or an assertion matching bytes from anywhere but this run,
    fails it.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    # Resolved the way the launcher resolves it, rather than by repeating the path.
    directory = launcher_module.i18n_dir(fx.fake_profile)

    def catalog(language):
        raw = tomllib.loads((directory / f"{language}.toml").read_text(encoding="utf-8"))
        return {key: value for key, value in raw.items() if isinstance(value, str)}

    english = catalog("en")
    evidence_keys = ("mode.title", "corpus.label", "language.label")

    def drive(language):
        return fx.run_picker_scenario(
            f"{language} root render",
            ((catalog(language)["prompt.cancel"].encode(), b"\x1b"),),
            env_overrides={"AGENT_LAUNCH_LANG": language},
        )

    # Which languages this run actually put on a screen. Asserted against the
    # expected set at the end, because the sentinel control below drives only
    # Korean: without this, deleting the loop would leave Japanese never launched
    # and the leg still green.
    rendered = set()
    expected = {"ko", "ja"}
    for language in sorted(expected):
        strings = catalog(language)
        tokens = []
        for key in evidence_keys:
            value = strings.get(key, "")
            if not value:
                mark_fail(f"{language}.toml lacks evidence key {key}")
            elif value == english.get(key):
                mark_fail(
                    f"{language}.toml {key} now equals its English text, so rendering it "
                    "is no evidence this language displays — choose another evidence key"
                )
            else:
                tokens.append(value.encode())
        if not tokens:
            mark_fail(f"{language}: no evidence token left; this leg would assert nothing")
            continue
        transcript, status = drive(language)
        if status != 130:
            mark_fail(f"agent-launch {language} root Esc returned {status}, want 130")
        missing = [tok for tok in tokens[1:] if tok not in transcript]
        for token in missing:
            mark_fail(
                f"agent-launch rendered no {token.decode()!r} in {language}; the "
                "catalog carries it but the screen never showed it"
            )
        if not missing and tokens[0] in transcript:
            rendered.add(language)

    if rendered != expected:
        mark_fail(
            f"language render leg covered {sorted(rendered) or 'nothing'}, not "
            f"{sorted(expected)} — a language nothing drove cannot be reported clean"
        )

    target = directory / "ko.toml"
    original_text = target.read_text(encoding="utf-8")
    real_title = catalog("ko")["mode.title"]
    sentinel = "가짜제목ZZ"
    try:
        target.write_text(
            original_text.replace(
                f'"mode.title" = "{real_title}"', f'"mode.title" = "{sentinel}"', 1
            ),
            encoding="utf-8",
        )
        if catalog("ko")["mode.title"] != sentinel:
            mark_fail("language-render control could not plant its sentinel — vacuous")
        else:
            planted, _ = drive("ko")
            if sentinel.encode() not in planted:
                mark_fail(
                    "language-render control: the planted title never rendered, so this "
                    "leg is not reading the catalog it believes it is"
                )
            title_rows = re.findall(rb"\x1b\[1;1H([^\r\n]*)", planted)
            if not title_rows:
                mark_fail("language-render control: no terminal title row was captured")
            if any(real_title.encode() in row for row in title_rows):
                mark_fail(
                    f"language-render control: {real_title!r} rendered from a catalog that "
                    "no longer carries it — the assertion is matching stale bytes"
                )
    finally:
        target.write_text(original_text, encoding="utf-8")


@launcher_check
def corpus_status_shapes_degrade_rather_than_lie(fx):
    """A wrong type in the corpus projection renders as absence, never as a plausible value.

    `config_typos_reach_the_user_as_messages` does this for `agent-launch.toml`; nothing
    did it for `corpus-status.json`, and that is where three defects lived. The readers
    promise to DEGRADE on a shape they cannot use, and the failure was not a crash — a
    string passed `value or []` and every consumer iterated its characters, so
    `applied = "office-work"` became eleven domain names on their way to the installer,
    `versions = "v1"` counted as two, and a failed apply reported requesting `a, l, p, h,
    a`. Nothing raised, so the absorber that keeps the promise never saw anything.

    The assertion is CONTENT-INDEPENDENCE: two different wrong values of the same type
    must render the same. A reader that degrades cannot tell them apart, and a reader that
    iterates a string produces different text for "office-work" than for "zz". Stated this
    way it needs no list of forbidden outputs and no knowledge of which degradation message
    applies — an earlier version demanded the wrong type render exactly like an EMPTY
    field, and that was too strong: the launcher distinguishes "read it, nothing in it"
    from "cannot read it", which is better behaviour than collapsing the two.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    workspace = fx.tmp / "corpus-shapes"
    workspace.mkdir(exist_ok=True)
    status_path = workspace / "corpus-status.json"

    # The shape the installer actually writes, reduced to what the readers consume.
    well_formed = {
        "repo": "/repo", "current_version": "v2", "latest_version": "v2",
        "rolled_back_to": None,
        "versions": [{"version": "v2", "closed": "2026-01-01", "commit": "abc",
                      "summary": "a release"}],
        "summary": {"entries": 1, "by_status": {"placed": 1, "incubating": 0},
                    "placed_by_layer": {"guide": 1}},
        "domains": {"available": ["office-work"], "applied": ["office-work"]},
        "last_apply": {"outcome": "failed", "requested": ["office-work"]},
        "generated": "2026-01-01",
    }
    # Which leaves are list-typed, derived from the document rather than listed.
    list_paths = []

    def walk(node, prefix=()):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, prefix + (key,))
        elif isinstance(node, list):
            list_paths.append(prefix)

    walk(well_formed)
    if not list_paths:
        mark_fail("corpus status shape sweep: the fixture holds no list-typed field, so "
                  "the substitution this leg makes has nothing to act on")
        return

    def place(tree, path, value):
        node = tree
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    def render(document):
        status_path.write_text(json.dumps(document), encoding="utf-8")
        saved = os.environ.get(launcher_module.CORPUS_STATUS_ENV) if hasattr(
            launcher_module, "CORPUS_STATUS_ENV") else os.environ.get("AGENT_BIOS_CORPUS_STATUS")
        os.environ["AGENT_BIOS_CORPUS_STATUS"] = str(status_path)
        try:
            importlib.reload(launcher_module) if False else None
            launcher_module.CORPUS_STATUS_PATH = status_path
            # Panel AND checklist: `domains.available` never reaches the panel, so a
            # panel-only probe would have to skip it, and a skipped field is exactly the
            # kind of silent hole this leg exists to close. The checklist is driven with
            # its input exhausted immediately, which draws the screen once and leaves.
            errors, drawn = io.StringIO(), io.StringIO()
            real_input = launcher_module.read_input

            def exhausted(_prompt):
                raise launcher_module.BackRequested

            launcher_module.read_input = exhausted
            try:
                with contextlib.redirect_stderr(errors):
                    lines = launcher_module.corpus_summary_lines(
                        launcher_module.load_corpus_status()
                    )
                    with contextlib.redirect_stdout(drawn):
                        try:
                            launcher_module.corpus_checklist(None)
                        except (launcher_module.BackRequested, launcher_module.LaunchError):
                            pass
            finally:
                launcher_module.read_input = real_input
            return "\n".join(lines) + "\n--\n" + drawn.getvalue()
        finally:
            if saved is None:
                os.environ.pop("AGENT_BIOS_CORPUS_STATUS", None)
            else:
                os.environ["AGENT_BIOS_CORPUS_STATUS"] = saved

    original_path = launcher_module.CORPUS_STATUS_PATH
    try:
        baseline = render(copy.deepcopy(well_formed))
        if not baseline.strip():
            mark_fail("corpus status shape sweep: the well-formed fixture renders nothing, "
                      "so every comparison below would pass against an empty string")
            return
        for path in list_paths:
            dotted = ".".join(path)
            emptied = copy.deepcopy(well_formed)
            place(emptied, path, [])
            if render(emptied) == baseline:
                mark_fail(f"corpus status shape sweep: emptying {dotted} changed no rendered "
                          "surface, so nothing here can observe this field at all")
                continue
            # Two values of the same wrong type, differing only in content.
            for label, first, second in (
                ("a string", "office-work", "zz"),
                ("a number", 7, 999),
                ("a table", {"a": 1}, {"bbbb": 2, "cccc": 3}),
            ):
                one, two = copy.deepcopy(well_formed), copy.deepcopy(well_formed)
                place(one, path, first)
                place(two, path, second)
                if render(one) != render(two):
                    mark_fail(
                        f"corpus status: {dotted} given {label} renders differently for "
                        f"{first!r} than for {second!r} — the reader is deriving a value "
                        "from a shape it cannot use instead of degrading"
                    )
    finally:
        launcher_module.CORPUS_STATUS_PATH = original_path


@launcher_check
def corpus_panel_columns_align_in_every_language(fx):
    """The status panel's values start at one column, in every language.

    The panel pads labels into a column, and padding computed with len() lines up
    only in English: `적용 버전` is five characters and nine display cells, so a
    naive pad leaves Korean four cells short and the panel ragged. Nothing else
    here can see that — the catalog gate checks keys and slots, and the render legs
    assert a string appeared, not where. This drives the REAL corpus_summary_lines
    over one fixture status per language and requires every labelled row to begin
    its value at the same cell.

    The control swaps the width function for len() and requires this to fail, so
    the assertion cannot pass over an implementation that stopped measuring.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    directory = launcher_module.i18n_dir(fx.fake_profile)
    status = {
        "current_version": "v3", "latest_version": "v4",
        "summary": {"placed_by_layer": {"global": 2, "guide": 5},
                    "by_status": {"placed": 53, "incubating": 24}},
        "versions": [{"version": "v3"}, {"version": "v4"}],
        "domains": {"available": ["office"], "applied": []},
    }
    label_keys = ("panel.version.label", "panel.mechanisms.label",
                  "panel.ledger.label", "panel.domains.label")
    saved = launcher_module._CATALOG

    # The gate's own ruler, deliberately a second implementation. Measuring with the
    # launcher's display_width would make this agree with the very bug it exists to
    # catch: pad with len() and measure with len() and a ragged panel reads level.
    # A checker that borrows its subject's ruler can only check for typos.
    def measure(text):
        normalised = unicodedata.normalize("NFC", text)
        return sum(
            0 if unicodedata.category(ch) in ("Mn", "Me")
            else 2 if unicodedata.east_asian_width(ch) in ("W", "F")
            else 1
            for ch in normalised
        )

    # The ruler answers for the three ways a count diverges from a render: wide
    # glyphs, decomposed ones, and marks that take no cell. A ruler wrong about any
    # of them agrees with a product wrong the same way, and the panel reads level.
    # The mark case uses q+U+0301 deliberately: there is no precomposed q-acute, so
    # it survives the NFC pass and actually reaches the Mn/Me branch. A+U+0301
    # composes to Á first and left that branch untested — removing it kept this
    # green.
    if (measure("적용 버전") != 9 or measure("Applied version") != 15
            or measure(unicodedata.normalize("NFD", "적용 버전")) != 9
            or measure("q\u0301") != 1):
        mark_fail("corpus panel: the gate's own width ruler is wrong — vacuous")
        return

    def value_columns(language):
        """The display cell each labelled row's value starts at."""
        raw = tomllib.loads((directory / f"{language}.toml").read_text(encoding="utf-8"))
        launcher_module._CATALOG = {k: v for k, v in raw.items() if isinstance(v, str)}
        lines = launcher_module.corpus_summary_lines(status)
        columns = {}
        for key in label_keys:
            label = launcher_module.t(key)
            row = next((r for r in lines if r.startswith(label)), None)
            if row is None:
                mark_fail(f"corpus panel ({language}) has no row for {key}")
                continue
            rest = row[len(label):]
            pad = len(rest) - len(rest.lstrip(" "))
            columns[key] = measure(label) + pad
        return columns

    try:
        for language in ("en", "ko", "ja"):
            columns = value_columns(language)
            if len(set(columns.values())) > 1:
                mark_fail(
                    f"corpus panel ({language}) values start at different columns: "
                    f"{columns} — the label pad is not measuring display cells"
                )
        # Control: the naive width function must break exactly the CJK panels, or
        # this leg is asserting something that was never at risk.
        real_width = launcher_module.display_width
        launcher_module.display_width = len
        try:
            ragged = [lang for lang in ("ko", "ja")
                      if len(set(value_columns(lang).values())) > 1]
        finally:
            launcher_module.display_width = real_width
        if not ragged:
            mark_fail(
                "corpus panel control: len()-based padding kept ko and ja aligned, "
                "so this leg would pass whether or not the widths are measured"
            )
    finally:
        launcher_module._CATALOG = saved


@launcher_check
def numbered_fallback(fx):
    fake_data, run_picker_scenario = fx.fake_data, fx.run_picker_scenario
    english = fx.launcher_module._module_catalog("en")
    # TERM=dumb routes to numbered prompts (textual renders on any usable
    # terminal, so the numbered fallback is gated on TERM/non-TTY/textual
    # availability, not a terminfo probe). 'b' is the numbered back command.
    # The root Mode menu is fixed (Software Engineer=1, Builder=2, Session distill=3)
    # regardless of preset count; only Custom's position within Builder's
    # own preset submenu depends on how many builder-mode presets exist.
    builder_preset_count = sum(
        1
        for data in fake_data["presets"].values()
        if data.get("mode", "builder") == "builder"
    )
    custom_number = str(builder_preset_count + 1).encode()
    transcript, picker_status = run_picker_scenario(
        "numbered fallback (TERM=dumb)",
        (
            (english["mode.builder.description"].encode(), b"2\n"),
            (english["preset.custom.description"].encode(), custom_number + b"\n"),
            (b"Custom settings", b"b\n"),
            (english["preset.balanced.description"].encode(), b"1\n"),
        ),
        term="dumb",
    )
    if (
        picker_status != 0
        or b"Traceback" in transcript
        or b"Preset         Balanced" not in transcript
    ):
        mark_fail("agent-launch numbered fallback (TERM=dumb) did not preserve numbered back")


@launcher_check
def distill_hub(fx):
    run_picker_scenario = fx.run_picker_scenario
    english = fx.launcher_module._module_catalog("en")
    # Session Distill hub: enter, render status, back out, launch balanced.
    transcript, picker_status = run_picker_scenario(
        "numbered distill hub (TERM=dumb)",
        (
            (b"Session distill", b"3\n"),
            (b"Versions & rollback", b"4\n"),
            (english["mode.builder.description"].encode(), b"2\n"),
            (english["preset.balanced.description"].encode(), b"1\n"),
        ),
        term="dumb",
    )
    corpus_panel_rendered = (
        b"Applied version" in transcript or b"not projected yet" in transcript
    )
    if (
        picker_status != 0
        or b"Traceback" in transcript
        or not corpus_panel_rendered
        or b"Preset         Balanced" not in transcript
    ):
        mark_fail("agent-launch numbered distill hub did not render or return")


@launcher_check
def backend_dispatch(fx):
    argv_log, backend, env, profile_text, tmp = fx.argv_log, fx.backend, fx.env, fx.profile_text, fx.tmp
    passed = invoke([
        sys.executable, str(launcher), "--no-tui", "codex", "--", "exec", "--json", "probe"
    ], env=env)
    if passed.returncode != 0 or argv_log.read_text().splitlines() != ["exec", "--json", "probe"]:
        mark_fail("agent-launch Codex argument-bearing bypass changed forwarded argv")

    passed = invoke([
        sys.executable, str(launcher), "--no-tui", "claude", "--", "-p", "probe"
    ], env=env)
    if passed.returncode != 0 or argv_log.read_text().splitlines() != [
        "--dangerously-skip-permissions", "-p", "probe"
    ]:
        mark_fail("agent-launch Claude bypass did not preserve the existing backend default")

    # The bare-launch arguments are BARE-launch arguments: a configured launch projects
    # the preset's own policy and must not carry them. A `standard` preset that inherited
    # `--dangerously-skip-permissions` from `[backends.claude]` would launch with the
    # posture its author declined (round 18, #3 — the key was renamed for this).
    standard_profile = tmp / "standard-policy.toml"
    standard_profile.write_text(
        profile_text + legacy_preset_toml("gate-standard", "none", family="same").replace(
            'claude_permission_mode = "bypassPermissions"', 'claude_permission_mode = "standard"', 1
        )
    )
    standard = invoke([
        sys.executable, str(launcher), "--config", str(standard_profile),
        "--preset", "gate-standard", "--yes", "--dry-run", "claude",
    ], env=env)
    if standard.returncode != 0:
        mark_fail(f"agent-launch standard-policy subject did not launch: {standard.stderr.strip()[:160]}")
    else:
        standard_argv = json.loads(standard.stdout.splitlines()[-1])
        if "--dangerously-skip-permissions" in standard_argv:
            mark_fail(
                "agent-launch configured launch carried the backend's bare-launch argument "
                "over a preset that chose the standard permission mode"
            )
        if "--permission-mode" in standard_argv:
            mark_fail("agent-launch projected a --permission-mode flag for the standard mode, which is the CLI's default")

    # The projected policy and the INJECTED CONTRACT, compared against each other. Both
    # were pinned independently — the argv above, the contract in the review-matrix golden
    # — and neither asked whether they agree, so `claude_permission_mode` changed argv
    # while the contract stayed byte-identical: two launches, one carrying
    # `--dangerously-skip-permissions` and one carrying no policy flag at all, described
    # themselves the same way under a tail promising that what is described is what runs
    # (round 21, #4). Every value is exercised on both hosts, and the contracts are
    # required to be pairwise distinct: a clause that named the host but not the value
    # would satisfy "the contract mentions a policy" and change nothing.
    launcher_module = fx.launcher_module
    if launcher_module is not None:
        policy_matrix = {
            "codex": ("codex_execution_policy",
                      ("bypass", "workspace-write", "read-only", "standard")),
            "claude": ("claude_permission_mode",
                       ("bypassPermissions", "acceptEdits", "plan", "standard")),
        }
        for policy_host, (field, values) in policy_matrix.items():
            contracts: dict[str, str] = {}
            for value in values:
                config = launcher_module.load_config(launch_profile_path)
                config["presets"]["balanced"][field] = value
                try:
                    plan = launcher_module.build_plan(config, policy_host, "balanced")
                except launcher_module.LaunchError as exc:
                    mark_fail(f"agent-launch {policy_host}/{field}={value} did not build: {exc}")
                    continue
                contract = launcher_module.run_contract(plan)
                argv = launcher_module.project_args(plan, materialize_agents=False)
                contracts[value] = contract
                # Read back OUT of the rendered contract, not asked of the renderer: a
                # clause asserted through the function that wrote it proves only that the
                # function is itself.
                execution = next(
                    (part for part in contract.split(". ") if part.startswith("Execution=")),
                    "",
                )
                if value not in execution:
                    mark_fail(
                        f"agent-launch {policy_host}: {field}={value!r} is projected into argv "
                        f"and the contract injected beside it says {execution!r}, while its "
                        f"tail promises that what it describes is what runs"
                    )
                # …and the contract's claim is the argv's behaviour, not a second opinion
                # about it: `standard` projects no policy flag, everything else projects one.
                flags = [
                    token for token in argv
                    if token in ("--permission-mode", "--sandbox",
                                 "--dangerously-skip-permissions",
                                 "--dangerously-bypass-approvals-and-sandbox")
                ]
                says_default = "no sandbox flag is projected" in contract or (
                    "no permission-mode flag is projected" in contract
                )
                if bool(flags) == says_default:
                    mark_fail(
                        f"agent-launch {policy_host}/{field}={value!r}: argv carries {flags!r} "
                        f"while the contract says the backend's own default applies"
                        if says_default else
                        f"agent-launch {policy_host}/{field}={value!r}: argv carries no policy "
                        f"flag while the contract describes a projected posture"
                    )
            if len(set(contracts.values())) != len(contracts):
                mark_fail(
                    f"agent-launch {policy_host}: two {field} values inject the same contract "
                    f"— the value is projected into argv and the description cannot tell them "
                    f"apart"
                )

    # EVERY advertised tier reconciled against argv, not only the main binding. `SPAWNABLE_TIERS`
    # says HELM is the main role and never a child, so under the shipped `fast-batch` (main
    # WORKHORSE) nothing binds HELM — no child agent config names it and the main binding is
    # somebody else's — while the contract, the launch summary and the setup panel all listed it
    # as projected (round 23, #1). Each surface is read back OUT of its own rendered text and
    # judged on its own, so reverting one leaves the other two green. The property is two-sided:
    # nothing advertised may be missing from argv, and every tier argv does not carry must be
    # NAMED inactive rather than silently dropped — the second half is what the delegation-off
    # fixes of rounds 20 and 22 bought, and it is asserted here for both causes at once.
    launcher_module = fx.launcher_module
    if launcher_module is not None:
        tier_config = launcher_module.load_config(launch_profile_path)
        tier_order = launcher_module.TIER_ORDER

        # The inactive tiers a surface NAMES, read off its own rendered text. Cut at the word
        # "inactive" and keep what precedes it: every surface states its REASON after that
        # word, and the reason names the spawnable tiers, so a token scan over the whole line
        # would read the projected children as unprojected.
        def named_inactive(text: str) -> set[str]:
            # Anchored on the REASON clause, which the tier list always immediately
            # precedes, rather than on the first "inactive" in the line. The contract's
            # delegation-off branch now opens with "inactive tiers (…)" — the set can
            # contain HELM, which is not a child (round 24, #12) — and splitting on the
            # first occurrence took the lead to the end of the bindings and reported an
            # empty set. An unrecognised wording returns nothing and fails the caller's
            # comparison loudly, which is what a control should do when the surface it
            # reads has moved.
            for anchor in ("are inactive and not projected",
                           "is inactive and not projected",
                           "— inactive, not projected"):
                if anchor in text:
                    lead = text.split(anchor, 1)[0]
                    break
            else:
                return set()
            if "; " in lead:
                lead = lead.split("; ", 1)[1]
            for punctuation in "(),—":
                lead = lead.replace(punctuation, " ")
            words = lead.split()
            return {tier for tier in tier_order if tier in words}

        reconciled: list[str] = []
        non_helm_mains: list[str] = []
        for tier_host in ("claude", "codex"):
            for preset in tier_config["presets"]:
                plan = launcher_module.build_plan(tier_config, tier_host, preset)
                if launcher_module.plan_projects_nothing(plan):
                    continue
                cell = f"{preset!r} on {tier_host}"
                reconciled.append(cell)
                if plan["main_tier"] != "helm":
                    non_helm_mains.append(cell)
                argv = launcher_module.project_args(plan, materialize_agents=False)
                # What the launched session really receives: the main binding, plus whichever
                # child agent configs argv registers.
                if tier_host == "codex":
                    carried = {
                        token.split(".", 2)[1] for token in argv if token.startswith("agents.")
                    }
                elif "--agents" in argv:
                    carried = set(json.loads(argv[argv.index("--agents") + 1]))
                else:
                    carried = set()
                carried.add(plan["main_tier"])

                contract = launcher_module.run_contract(plan)
                sentence = contract[contract.index("LaunchPlan:"):].split(". ", 1)[0]
                if "; tiers: " not in sentence:
                    mark_fail(
                        f"agent-launch {cell}: the contract carries no tiers clause to "
                        f"reconcile against argv: {sentence!r}"
                    )
                    continue
                clause = sentence.split("; tiers: ", 1)[1]
                advertised = {
                    chunk.split("=", 1)[0].strip()
                    for chunk in clause.split(";", 1)[0].split(", ")
                    if "=" in chunk
                }

                summary_out = io.StringIO()
                launcher_module.print_summary(plan, tier_host, argv, summary_out)
                summary_lines = summary_out.getvalue().splitlines()
                summary_rows = {
                    tier for tier in tier_order
                    if any(line.startswith(f"  {tier.upper():<14} ") for line in summary_lines)
                }
                panel = launcher_module.setup_summary_lines(plan)
                panel_rows = {
                    tier for tier in tier_order
                    if any(line.startswith(f"{tier.upper():<10} ") for line in panel)
                }

                contract_inactive = named_inactive(clause)
                summary_inactive = named_inactive(
                    next((line for line in summary_lines if "inactive, not projected" in line), "")
                )
                panel_inactive = named_inactive(
                    next((line for line in panel if "inactive, not projected" in line), "")
                )

                for surface, shown, called_inactive in (
                    ("contract", advertised, contract_inactive),
                    ("launch summary", summary_rows, summary_inactive),
                    ("setup panel", panel_rows, panel_inactive),
                ):
                    if shown - carried:
                        mark_fail(
                            f"agent-launch {cell}: the {surface} advertises "
                            f"{sorted(shown - carried)} as an active binding while argv carries "
                            f"{sorted(carried)} — a seat the launched session never receives"
                        )
                    if called_inactive != set(tier_order) - carried:
                        mark_fail(
                            f"agent-launch {cell}: the {surface} names {sorted(called_inactive)} "
                            f"as inactive while argv carries {sorted(carried)} of "
                            f"{sorted(tier_order)} — an unprojected tier is dropped in silence "
                            f"rather than named"
                        )
        if not reconciled:
            mark_fail("agent-launch tier reconciliation judged no preset at all")
        if not non_helm_mains:
            mark_fail(
                "agent-launch tier reconciliation saw only HELM mains, where every tier is "
                "either the main or a child — the cell this check exists for is absent"
            )

    env["FAKE_LAUNCH_STATUS"] = "9"
    failed = invoke([sys.executable, str(launcher), "--no-tui", "codex", "--", "probe"], env=env)
    if failed.returncode != 9:
        mark_fail(f"agent-launch returns {failed.returncode} instead of backend exit status 9")
    env.pop("FAKE_LAUNCH_STATUS")

    # A command validated by its slash-containing spelling is answered ABSOLUTE. It was
    # returned as written, so `./bin/x` entered the contract as the reviewer's route while
    # `host_dispatch_command` promised an absolute one (round 18, #14). Asserted on the
    # resolver both callers pass through, from a cwd where the relative spelling is valid.
    launcher_module = fx.launcher_module
    if launcher_module is not None:
        rel_dir = tmp / "relative-command"
        rel_dir.mkdir(exist_ok=True)
        (rel_dir / "tool").write_text("#!/usr/bin/env bash\nexit 0\n")
        (rel_dir / "tool").chmod(0o755)
        previous = os.getcwd()
        try:
            os.chdir(tmp)
            resolved = launcher_module.resolve_command("./relative-command/tool")
        except launcher_module.LaunchError as exc:
            mark_fail(f"agent-launch refused a valid relative command spelling: {exc}")
            resolved = ""
        finally:
            os.chdir(previous)
        if resolved and not os.path.isabs(resolved):
            mark_fail(
                f"agent-launch resolve_command answered the relative spelling {resolved!r}; "
                "the contract's dispatch route must be absolute"
            )
        if resolved and not os.path.samefile(resolved, rel_dir / "tool"):
            mark_fail(f"agent-launch resolve_command answered {resolved!r} for a different file")

    sleeper = tmp / "sleeper"
    sleeper.write_text("#!/usr/bin/env bash\nexec sleep 30\n")
    sleeper.chmod(0o755)
    signal_profile = tmp / "signal.toml"
    signal_profile.write_text(profile_text.replace(str(backend), str(sleeper)))
    signal_process = subprocess.Popen([
        sys.executable, str(launcher), "--config", str(signal_profile),
        "--no-tui", "codex",
    ], env=env)
    time.sleep(0.2)
    signal_process.terminate()
    try:
        signal_status = signal_process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        signal_process.kill()
        signal_process.wait()
        mark_fail("agent-launch did not forward process lifetime through exec")
    else:
        if signal_status != -15:
            mark_fail(f"agent-launch SIGTERM status is {signal_status}, want -15")


@launcher_check
def profile_validation(fx):
    env, profile_text, tmp = fx.env, fx.profile_text, fx.tmp
    invalid_args_profile = tmp / "invalid-args.toml"
    invalid_args_profile.write_text(
        profile_text.replace("bare_launch_args = []", 'bare_launch_args = "--bad"', 1)
    )
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_args_profile),
        "--no-tui", "codex",
    ], env=env)
    if invalid.returncode != 2 or "bare_launch_args" not in invalid.stderr:
        mark_fail("agent-launch accepted string bare_launch_args instead of failing closed")
    # The old key is refused by name rather than read as nothing: a profile still saying
    # `passthrough_args` would otherwise launch bare with no policy flag at all, silently.
    renamed_profile = tmp / "renamed-key.toml"
    renamed_profile.write_text(
        profile_text.replace("bare_launch_args = []", 'passthrough_args = []', 1)
    )
    stale = invoke([
        sys.executable, str(launcher), "--config", str(renamed_profile), "--no-tui", "codex",
    ], env=env)
    if stale.returncode != 2 or "bare_launch_args" not in stale.stderr:
        mark_fail("agent-launch read a stale passthrough_args key as no bare arguments instead of refusing")

    invalid_delegation_profile = tmp / "invalid-delegation.toml"
    invalid_delegation_profile.write_text(
        profile_text.replace("delegation = true", 'delegation = "false"', 1)
    )
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_delegation_profile),
        "--preset", "balanced", "--dry-run", "codex",
    ], env=env)
    if invalid.returncode != 2 or "delegation must be boolean" not in invalid.stderr:
        mark_fail("agent-launch accepted non-boolean delegation instead of failing closed")

    no_delegation_profile = tmp / "no-delegation.toml"
    no_delegation_profile.write_text(
        profile_text + legacy_preset_toml("gate-nodeleg", "none", delegation=False)
    )
    no_delegation = invoke([
        sys.executable, str(launcher), "--config", str(no_delegation_profile),
        "--preset", "gate-nodeleg", "--dry-run", "claude",
    ], env=env)
    if no_delegation.returncode != 0:
        mark_fail(f"agent-launch rejected valid delegation=false: {no_delegation.stderr.strip()}")
    else:
        no_delegation_argv = json.loads(no_delegation.stdout.splitlines()[-1])
        if "--agents" in no_delegation_argv or "Delegation=off" not in " ".join(no_delegation_argv):
            mark_fail("agent-launch Claude delegation=false still projected child agents")


@launcher_check
def review_matrix(fx):
    env, profile_text, tmp = fx.env, fx.profile_text, fx.tmp
    # The native-requires-delegation contradiction is a same-family concept
    # (cross native does not gate on delegation); test it under review_family=same.
    for review_setup in ("native-panel",):
        incompatible_review_profile = tmp / f"no-delegation-{review_setup}.toml"
        incompatible_review_profile.write_text(
            profile_text
            + legacy_preset_toml(
                "gate-contradiction", review_setup, family="same", delegation=False
            )
        )
        incompatible_review = invoke([
            sys.executable,
            str(launcher),
            "--config",
            str(incompatible_review_profile),
            "--preset",
            "gate-contradiction",
            "--dry-run",
            "claude",
        ], env=env)
        if (
            incompatible_review.returncode != 2
            or "requires delegation" not in incompatible_review.stderr
        ):
            mark_fail(
                "agent-launch accepted delegation=false with review setup "
                f"{review_setup}"
            )

    for field in ("codex_execution_policy", "claude_permission_mode"):
        missing_policy_profile = tmp / f"missing-{field}.toml"
        missing_policy_profile.write_text(
            profile_text.replace(f'{field} = "bypass"\n', "", 1)
            if field == "codex_execution_policy"
            else profile_text.replace(f'{field} = "bypassPermissions"\n', "", 1)
        )
        missing_policy = invoke([
            sys.executable, str(launcher), "--config", str(missing_policy_profile),
            "--preset", "balanced", "--dry-run", "codex",
        ], env=env)
        if missing_policy.returncode != 2 or field not in missing_policy.stderr:
            mark_fail(f"agent-launch accepted missing security policy: {field}")

    for field, valid_value in (
        ("codex_execution_policy", "bypass"),
        ("claude_permission_mode", "bypassPermissions"),
    ):
        invalid_policy_profile = tmp / f"invalid-{field}.toml"
        invalid_policy_profile.write_text(
            profile_text.replace(
                f'{field} = "{valid_value}"',
                f'{field} = "unsupported-policy"',
                1,
            )
        )
        invalid_policy = invoke([
            sys.executable,
            str(launcher),
            "--config",
            str(invalid_policy_profile),
            "--preset",
            "balanced",
            "--dry-run",
            "codex",
        ], env=env)
        if invalid_policy.returncode != 2 or field not in invalid_policy.stderr:
            mark_fail(f"agent-launch accepted invalid security policy: {field}")


@launcher_check
def profile_errors(fx):
    env, profile_text, tmp = fx.env, fx.profile_text, fx.tmp
    invalid_schema_profile = tmp / "invalid-schema.toml"
    invalid_schema_profile.write_text(profile_text.replace("schema_version = 1", "schema_version = true", 1))
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_schema_profile),
        "--no-tui", "codex",
    ], env=env)
    if invalid.returncode != 2 or "unsupported schema_version" not in invalid.stderr:
        mark_fail("agent-launch accepted boolean schema_version instead of failing closed")

    invalid_review_profile = tmp / "invalid-review.toml"
    # Its own legacy subject: the shipped presets no longer carry review_setup, so the
    # replacement silently stopped matching and the probe asserted nothing.
    invalid_review_profile.write_text(
        profile_text
        + legacy_preset_toml("gate-malformed", "native-panel").replace(
            'review_setup = "native-panel"', 'review_setup = ["native-panel"]', 1
        )
    )
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_review_profile),
        "--preset", "gate-malformed", "--dry-run", "codex",
    ], env=env)
    if invalid.returncode != 2 or "unknown review setup" not in invalid.stderr:
        mark_fail("agent-launch raised outside LaunchError for malformed review_setup")

    invalid_models_profile = tmp / "invalid-models.toml"
    codex_section = re.search(r"(?ms)^\[hosts\.codex\]\n.*?(?=^\[|\Z)", profile_text).group()
    invalid_codex_section = re.sub(r"(?m)^models\s*=.*$", "models = []", codex_section, count=1)
    assert invalid_codex_section != codex_section, "models control did not alter the real host table"
    invalid_models_profile.write_text(
        profile_text.replace(codex_section, invalid_codex_section, 1)
    )
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_models_profile),
        "--preset", "balanced", "--dry-run", "codex",
    ], env=env)
    if invalid.returncode != 2 or "must be a non-empty list of strings" not in invalid.stderr:
        mark_fail("agent-launch accepted an empty models catalog instead of failing closed")

    invalid_claude_effort_profile = tmp / "invalid-claude-effort.toml"
    invalid_claude_effort_profile.write_text(
        profile_text.replace('[presets.deep-review]\n',
                             '[presets.deep-review]\nfrontier_effort = { codex = "max", claude = "ultra" }\n', 1)
    )
    invalid = invoke([
        sys.executable, str(launcher), "--config", str(invalid_claude_effort_profile),
        "--preset", "deep-review", "--dry-run", "claude",
    ], env=env)
    if invalid.returncode != 2 or "unsupported effort" not in invalid.stderr:
        mark_fail("agent-launch accepted Claude Ultra instead of failing closed")

    # A tier override's keys are closed. `modle = "x"` used to load as no override at
    # all, so the preset launched advertising the default model while its author
    # believed otherwise (round 18, #11). Control: the same value under the right key
    # is applied. Both through the CLI, so the refusal is a sentence and exit 2.
    for key, expect_refusal in (("modle", True), ("model", False)):
        override_profile = tmp / f"override-{key}.toml"
        override_profile.write_text(
            profile_text + legacy_preset_toml("gate-override", "none", family="same")
            + f'\n[presets.gate-override.tier_overrides.codex.workhorse]\n{key} = "gpt-5.6-luna"\n'
        )
        run = invoke([
            sys.executable, str(launcher), "--config", str(override_profile),
            "--preset", "gate-override", "--yes", "--dry-run", "codex",
        ], env=env)
        if expect_refusal:
            if run.returncode != 2 or "unknown key(s) in" not in run.stderr:
                mark_fail(
                    "agent-launch accepted a misspelt tier-override key instead of failing "
                    f"closed: rc={run.returncode} {run.stderr.strip()[:160]}"
                )
        elif run.returncode != 0 or "workhorse=gpt-5.6-luna" not in run.stdout:
            mark_fail(
                "agent-launch override control: a correctly keyed override was not applied "
                f"(rc={run.returncode})"
            )

    # The override table's host keys are closed as well: `codxe` can never be the active
    # host, so an override under it used to be no override at all (round 19, #10).
    host_profile = tmp / "override-host.toml"
    host_profile.write_text(
        profile_text + legacy_preset_toml("gate-override-host", "none", family="same")
        + '\n[presets.gate-override-host.tier_overrides.codxe.workhorse]\nmodel = "gpt-5.6-luna"\n'
    )
    run = invoke([
        sys.executable, str(launcher), "--config", str(host_profile),
        "--preset", "gate-override-host", "--yes", "--dry-run", "codex",
    ], env=env)
    if run.returncode != 2 or "unknown host(s) in" not in run.stderr:
        mark_fail(
            "agent-launch accepted a misspelt tier-override host instead of failing closed: "
            f"rc={run.returncode} {run.stderr.strip()[:160]}"
        )

    # …and the closed set is the LAUNCHABLE one, not whatever `[hosts]` happens to declare.
    # Adding a complete host table under the typo made the misspelt override VALID and
    # permanently inert, since no argv can ever select `codxe` (round 20, #7) — the typo's
    # own table widened the set that exists to catch it. The case above is the control: the
    # same override without the fake host, refused the same way.
    typo_host = "".join(
        f'\n[hosts.codxe.tiers.{tier}]\nmodel = "{model}"\neffort = "{effort}"\n'
        for tier, model, effort in (
            ("frontier", "gpt-5.6-sol", "max"), ("helm", "gpt-5.6-sol", "xhigh"),
            ("workhorse", "gpt-5.6-terra", "high"), ("sweep", "gpt-5.6-luna", "low"),
        )
    )
    configured_typo = tmp / "override-host-configured.toml"
    configured_typo.write_text(
        profile_text + legacy_preset_toml("gate-typo-host", "none", family="same")
        + '\n[presets.gate-typo-host.tier_overrides.codxe.workhorse]\nmodel = "gpt-5.6-luna"\n'
        + '\n[hosts.codxe]\nprovider = "typo-provider"\n'
          'models = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]\n' + typo_host
    )
    run = invoke([
        sys.executable, str(launcher), "--config", str(configured_typo),
        "--preset", "gate-typo-host", "--yes", "--dry-run", "codex",
    ], env=env)
    if run.returncode != 2 or "unknown host(s) in" not in run.stderr:
        mark_fail(
            "agent-launch accepted a tier-override keyed on a host no argv can select, because "
            f"the typo's own [hosts] table widened the set meant to catch it: "
            f"rc={run.returncode} {run.stderr.strip()[:160]}"
        )
    # The positive control: the same profile, the override keyed on the host that CAN be
    # selected. Without it a refusal triggered by the extra host table — rather than by the
    # key — would satisfy the mutation above.
    configured_ok = tmp / "override-host-configured-ok.toml"
    configured_ok.write_text(
        profile_text + legacy_preset_toml("gate-typo-ok", "none", family="same")
        + '\n[presets.gate-typo-ok.tier_overrides.codex.workhorse]\nmodel = "gpt-5.6-luna"\n'
        + '\n[hosts.codxe]\nprovider = "typo-provider"\n'
          'models = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]\n' + typo_host
    )
    run = invoke([
        sys.executable, str(launcher), "--config", str(configured_ok),
        "--preset", "gate-typo-ok", "--yes", "--dry-run", "codex",
    ], env=env)
    if run.returncode != 0 or "workhorse=gpt-5.6-luna" not in run.stdout:
        mark_fail(
            "agent-launch launchable-host control: an override keyed on a real host was not "
            f"applied beside an unlaunchable host table (rc={run.returncode})"
        )

    # FRONTIER's effort authored twice, to different values, is a contradiction and is
    # refused; authored once through the override alone it is applied and the plan holds
    # ONE value (round 18, #13). Two runs, because the refusal must be specific to the
    # conflict and not to the override.
    for top_level, expect_refusal in (('frontier_effort = "max"', True), ("", False)):
        conflict_profile = tmp / f"frontier-{'conflict' if top_level else 'override'}.toml"
        conflict_profile.write_text(
            profile_text
            + legacy_preset_toml("gate-frontier", "none", family="same").replace(
                'frontier_effort = "max"', top_level, 1
            ).replace('main_tier = "helm"', 'main_tier = "frontier"', 1)
            + '\n[presets.gate-frontier.tier_overrides.claude.frontier]\neffort = "high"\n'
        )
        run = invoke([
            sys.executable, str(launcher), "--config", str(conflict_profile),
            "--preset", "gate-frontier", "--yes", "--dry-run", "claude",
        ], env=env)
        if expect_refusal:
            if run.returncode != 2 or "FRONTIER's effort has one value" not in run.stderr:
                mark_fail(
                    "agent-launch accepted two disagreeing FRONTIER efforts instead of failing "
                    f"closed: rc={run.returncode} {run.stderr.strip()[:160]}"
                )
        else:
            if run.returncode != 0:
                mark_fail(
                    "agent-launch frontier control: an override-only FRONTIER effort was "
                    f"refused: {run.stderr.strip()[:160]}"
                )
            elif "main=frontier (claude-fable-5-1/high)" not in run.stdout:
                mark_fail(
                    "agent-launch frontier control: the override-only effort did not reach "
                    f"the contract as the one FRONTIER value: {run.stdout[-300:]!r}"
                )
            else:
                argv = json.loads(run.stdout.splitlines()[-1])
                if argv[argv.index("--effort") + 1] != "high":
                    mark_fail("agent-launch frontier control: argv effort disagrees with the contract")

    bare_dry_run = invoke([
        sys.executable, str(launcher), "--dry-run", "codex",
    ], env=env)
    if bare_dry_run.returncode != 0 or "Preset         Balanced" not in bare_dry_run.stdout:
        mark_fail("agent-launch non-TTY bare --dry-run did not select Balanced")

    no_balanced_profile = tmp / "no-balanced.toml"
    # Prefix, not the exact header: the preset's review arms live in
    # [presets.balanced.review.hosts.*] sub-tables, and renaming only the header left
    # those behind — which re-created `balanced` implicitly and made the probe inert.
    no_balanced_profile.write_text(
        profile_text.replace("[presets.balanced", "[presets.daily")
    )
    no_balanced = invoke([
        sys.executable,
        str(launcher),
        "--config",
        str(no_balanced_profile),
        "--dry-run",
        "codex",
    ], env=env)
    if (
        no_balanced.returncode != 2
        or "requires a 'balanced' preset" not in no_balanced.stderr
    ):
        mark_fail(
            "agent-launch bare non-TTY dry-run selected an arbitrary custom preset"
        )


@launcher_check
def codex_materialization_refuses_cleanly(fx):
    """An unwritable cache root ends the Codex launch with a message, not a traceback.

    `--dry-run` and a real launch differ by exactly one argument — `materialize_agents` —
    and everything that argument turns on is filesystem work. So the projection came back
    clean while the launch it was previewing raised PermissionError, which is the one
    disagreement between the two that no other check here can see: every other gate reads
    `--dry-run`, and `--dry-run` is the half that cannot fail this way.

    Narrow by nature — Codex, delegation on, and a directory that refuses writes — so the
    conditions are pinned as a matrix rather than a single case, and the three neighbours
    that must NOT refuse are asserted beside the one that must.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    workspace = fx.tmp / "codex-materialize"
    workspace.mkdir(exist_ok=True)
    profile = workspace / "agent-launch.toml"
    profile.write_text(fx.profile_text, encoding="utf-8")
    config = launcher_module.load_config(profile)

    unwritable = workspace / "readonly"
    unwritable.mkdir(exist_ok=True)
    writable = workspace / "writable"
    writable.mkdir(exist_ok=True)

    def materialize(preset, host, cache):
        """Real plan, real function, only the cache root varies."""
        saved = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = str(cache)
        try:
            plan = launcher_module.build_plan(config, host, preset)
            launcher_module.codex_agent_configs(plan, True)
            return None
        except launcher_module.LaunchError as exc:
            return ("refused", str(exc))
        except Exception as exc:  # noqa: BLE001 — that is the finding
            return ("raw", f"{type(exc).__name__}: {exc}")
        finally:
            if saved is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = saved

    delegating = sorted(
        name for name, preset in config["presets"].items()
        if isinstance(preset, dict) and preset.get("delegation") and "codex" not in str(
            preset.get("mode", "")
        )
    )
    if not delegating:
        mark_fail("codex materialization check: no shipped preset delegates, so the write "
                  "path it guards is never entered and a clean result means nothing")
        return

    # A cache location that is not an absolute path must be ignored, per the XDG spec, and
    # the reason is not pedantry: the relative path was resolved against the working
    # directory, so launching from a repo wrote an `agent-launch/` tree into it as
    # untracked files. `.get(name, default)` hid the empty case entirely — an empty
    # variable is present, so the default never applied.
    outside = workspace / "cwd-probe"
    outside.mkdir(exist_ok=True)
    saved_cwd = os.getcwd()
    for label, value in (("empty", ""), ("relative", "relative-cache")):
        before = {entry.name for entry in outside.iterdir()}
        saved_cache = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = value
        os.chdir(outside)
        try:
            plan = launcher_module.build_plan(config, "codex", delegating[0])
            launcher_module.codex_agent_configs(plan, True)
        except launcher_module.LaunchError:
            pass
        finally:
            os.chdir(saved_cwd)
            if saved_cache is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = saved_cache
        created = sorted({entry.name for entry in outside.iterdir()} - before)
        if created:
            mark_fail(
                f"codex materialization wrote {created} into the working directory with "
                f"an {label} XDG_CACHE_HOME — a non-absolute value must be ignored"
            )

    os.chmod(unwritable, 0o555)
    try:
        # The case that must refuse — cleanly, through LaunchError.
        for preset in delegating:
            outcome = materialize(preset, "codex", unwritable)
            if outcome is None:
                mark_fail(f"codex materialization: {preset} wrote into an unwritable cache "
                          "root, so this check's subject does not exist")
            elif outcome[0] == "raw":
                mark_fail(f"codex materialization: {preset} escaped as a raw exception "
                          f"instead of LaunchError — {outcome[1]}")

        # The neighbours that must NOT refuse, or "refuses" is not about writability.
        for preset in delegating[:1]:
            if materialize(preset, "codex", writable) is not None:
                mark_fail(f"codex materialization: {preset} refused a WRITABLE cache root — "
                          "the check is reporting on something other than writability")
    finally:
        os.chmod(unwritable, 0o755)


@launcher_check
def launcher_routed_presets(fx):
    """Saving a preset name and launching with it must refuse exactly the same names.

    The two refusals are separate on purpose — the save-side one arrives while the user
    still has the name in front of them, the load-side one on the next launch — and they
    were separate rules too until `routed_preset_names` became the single owner. Only one
    direction of drift is survivable: a save that accepts a name the next load refuses
    leaves the user launching nothing, out of a file the launcher offers no way to edit.

    So this asks both sides about every shipped preset rather than trusting the shared
    call: the guarantee is about behaviour, and a future edit could reintroduce a local
    rule at either site without touching the function.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    # Every probe below gets its OWN directory, because save_preset writes a
    # presets.local.toml BESIDE the profile it is given. Pointed at the shared fixture
    # root, this leg saved a copy of every shipped preset there and the legs that run
    # after it loaded a config where `vanilla` was shadowed — they failed reporting that
    # the bare preset carried --agents and --dangerously-skip-permissions. The fixture is
    # order-dependent by design; a check that writes into it is not read-only in practice.
    workspace = fx.tmp / "routed-presets"
    workspace.mkdir(exist_ok=True)
    profile = workspace / "agent-launch.toml"
    profile.write_text(fx.profile_text, encoding="utf-8")
    config = launcher_module.load_config(profile)
    shipped = config["presets"]
    routed = launcher_module.routed_preset_names(shipped)

    # Both classes must be present or the comparison below proves nothing: all-routed and
    # all-ordinary each make one of the two verdicts unobservable.
    if not routed:
        mark_fail("routed-preset check: no shipped preset carries a mission or trigger, "
                  "so the refusal it guards can never be observed")
        return
    if not set(shipped) - routed:
        mark_fail("routed-preset check: every shipped preset is routed, so the ALLOWED "
                  "case is untested and the check cannot tell a rule from a blanket refusal")
        return

    def save_refuses(name):
        scratch = workspace / f"save-{name}"
        scratch.mkdir(exist_ok=True)
        copy = scratch / "agent-launch.toml"
        copy.write_text(fx.profile_text, encoding="utf-8")
        plan = launcher_module.build_plan(config, "claude", "balanced")
        try:
            launcher_module.save_preset(plan, config, copy, name)
        except launcher_module.LaunchError:
            return True
        return False

    def load_refuses(name):
        # A real user file defining that name, read back through the real loader.
        scratch = workspace / f"load-{name}"
        scratch.mkdir(exist_ok=True)
        copy = scratch / "agent-launch.toml"
        copy.write_text(fx.profile_text, encoding="utf-8")
        launcher_module.user_presets_path(copy).write_text(
            f'[presets."{name}"]\nlabel = "Probe"\nmode = "builder"\n'
            'main_tier = "helm"\nfrontier_effort = "max"\ndelegation = true\n'
            'codex_execution_policy = "bypass"\nclaude_permission_mode = "bypassPermissions"\n',
            encoding="utf-8",
        )
        try:
            launcher_module.load_config(copy)
        except launcher_module.LaunchError as exc:
            return "redefines routed preset" in str(exc)
        return False

    disagreed = []
    for name in sorted(shipped):
        saving, loading = save_refuses(name), load_refuses(name)
        if saving != loading:
            disagreed.append(f"{name}: save {'refuses' if saving else 'allows'}, "
                             f"load {'refuses' if loading else 'allows'}")
        elif saving and name not in routed:
            disagreed.append(f"{name}: both refuse it but it carries no mission or trigger")
        elif not saving and name in routed:
            disagreed.append(f"{name}: routed, yet neither side refuses it")
    if disagreed:
        mark_fail("the save-time and launch-time routed-preset rules disagree: "
                  + "; ".join(disagreed))

    # The control rides the same two functions: a name the launcher must accept has to
    # come back ALLOWED from both, or the loop above is reporting agreement on refusal
    # for every input and would pass a rule that refuses everything.
    ordinary = sorted(set(shipped) - routed)[0]
    if save_refuses(ordinary) or load_refuses(ordinary):
        mark_fail(f"routed-preset check: {ordinary!r} carries no mission or trigger yet "
                  "was refused — the probes refuse regardless of input")


@launcher_check
def config_typos_reach_the_user_as_messages(fx):
    """Every leaf of the shipped config, given a TOML type it must not have, still exits
    through LaunchError.

    `profile_errors` above pins named malformations one at a time and reads the exact
    sentence each produces. This one asks the whole-file question that a named case
    cannot: is there ANY key where a hand-edit produces a traceback instead? Four did.
    `order`, `aggregation` and `adapter` were compared against a set with no type guard,
    and `x in <a set>` RAISES for a list or table rather than answering False; the fourth
    reached os.path.expanduser through a caller that only caught LaunchError. All four
    exited 1 with a traceback where the launcher's own contract is 2 with a sentence —
    and for `--verify-receipts`, which its docstring offers as a pipeline gate, exit 1
    is already spoken for by "the review did not verify".

    The sweep runs in-process because it is exhaustive: 172 keys x 2 types x 5 entry
    points is ~1.6s here and about eleven minutes as subprocesses. What that trades away
    is argv parsing and the exit-code mapping, which `profile_errors` covers.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return

    def toml_scalar(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        if isinstance(value, list):
            return "[" + ", ".join(toml_scalar(item) for item in value) + "]"
        if isinstance(value, dict):
            return "{" + ", ".join(f"{k} = {toml_scalar(v)}" for k, v in value.items()) + "}"
        raise TypeError(f"no TOML form for {type(value).__name__}")

    def to_toml(data):
        # tomllib reads and does not write, and the sweep needs to put a mutated tree back
        # on disk because load_config takes a path. Only the shapes this config actually
        # uses are handled; toml_scalar raises on anything else rather than emitting
        # something that would parse back differently.
        out = []

        def walk(table, prefix):
            scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
            tables = {k: v for k, v in table.items() if isinstance(v, dict)}
            if prefix:
                out.append(f"[{'.'.join(prefix)}]")
            for key, value in scalars.items():
                out.append(f"{key} = {toml_scalar(value)}")
            if scalars or prefix:
                out.append("")
            for key, value in tables.items():
                walk(value, prefix + [key])

        walk(data, [])
        return "\n".join(out) + "\n"

    def leaves(node, prefix=()):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from leaves(value, prefix + (key,))
        elif isinstance(node, list) and any(isinstance(item, dict) for item in node):
            # `[capabilities.*].offers` is a list of inline tables, and an earlier version
            # of this walk stopped at the list. The adapter defect lived inside one.
            for index, value in enumerate(node):
                yield from leaves(value, prefix + (index,))
        else:
            yield prefix

    def place(tree, path, value):
        node = tree
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    shipped = tomllib.loads(launch_profile_path.read_text(encoding="utf-8"))
    keys = list(leaves(shipped))
    if not keys:
        mark_fail("config type sweep found no keys to mutate — the sweep is vacuous")
        return

    # A sweep over the shipped file only covers the shape that file happens to have, and
    # a user's own presets.local.toml may carry keys the shipped presets do not. That is
    # not hypothetical: `review_family` is read by two sites and written by no shipped
    # preset, so the first version of this leg swept 172 keys and could not see either.
    # The extra keys are DERIVED from the launcher's own `preset.get("...")` calls rather
    # than listed here, so a key added to the code is covered without editing this gate.
    launcher_source = launcher.read_text(encoding="utf-8")
    preset_keys = {
        node.args[0].value
        for node in ast.walk(ast.parse(launcher_source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get" and getattr(node.func.value, "id", None) == "preset"
        and node.args and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    if not preset_keys:
        mark_fail("config type sweep: found no preset.get(...) keys in the launcher, so the "
                  "user-written-key half of this check reads an empty schema")
        return
    absent = sorted(preset_keys - {k for p in shipped["presets"].values()
                                   if isinstance(p, dict) for k in p})
    probe_preset = sorted(shipped["presets"])[0]
    extra_keys = [("presets", probe_preset, key) for key in absent]

    # Named, so a rename fails here loudly instead of quietly dropping an entry point.
    # The split is about what each one DOES with a bad config, and it decides how this
    # leg proves it looked at anything. The refusers raise LaunchError, so a count of
    # zero means they judged nothing. `host_dispatch_command` catches LaunchError and
    # answers None on purpose — availability, not validation — so it can never raise and
    # a refusal count would assert nothing about it. Its proof is the control instead:
    # with the resolve_command guard removed, the escape has to come back out of it.
    REFUSERS = ["load_config", "load_review_methods", "resolve_backend",
                "parse_capability_offers"]
    ANSWERERS = ["host_dispatch_command"]
    entry_names = REFUSERS + ANSWERERS

    def sweep(module):
        def entries(path):
            config = module.load_config(path)
            yield "load_config", lambda: config
            yield "load_review_methods", lambda: module.load_review_methods(config)
            yield "resolve_backend", lambda: [
                module.resolve_backend(config, host) for host in ("codex", "claude")
            ]
            yield "host_dispatch_command", lambda: [
                module.host_dispatch_command(host, config) for host in ("codex", "claude")
            ]
            yield "parse_capability_offers", lambda: [
                module.parse_capability_offers(name, raw)
                for name, raw in config.get("capabilities", {}).items()
            ]

        escapes, refusals = [], {name: 0 for name in entry_names}
        target = sweep_dir / "agent-launch.toml"
        # `keys` replaces a value that is there; `extra_keys` adds one that is not, which
        # is what a user's own presets.local.toml does. Same mutation, same verdict.
        for path in keys + extra_keys:
            for wrong in ([], {"probe": 1}):
                mutated = copy.deepcopy(shipped)
                place(mutated, path, wrong)
                target.write_text(to_toml(mutated), encoding="utf-8")
                dotted = ".".join(str(part) for part in path)
                try:
                    steps = list(entries(target))
                except module.LaunchError:
                    refusals["load_config"] += 1
                    continue
                except Exception as exc:  # noqa: BLE001 — that is the finding
                    escapes.append(f"{dotted} [load_config] {type(exc).__name__}")
                    continue
                for name, call in steps:
                    try:
                        call()
                    except module.LaunchError:
                        refusals[name] += 1
                    except Exception as exc:  # noqa: BLE001 — that is the finding
                        escapes.append(f"{dotted} [{name}] {type(exc).__name__}: {exc}")
        return escapes, refusals

    sweep_dir = pathlib.Path(tempfile.mkdtemp(prefix="config-sweep-"))
    # host_dispatch_command returns early when it finds a deployed `claude-run`, and on a
    # developer's own machine it does — which skipped the very line the fourth defect was
    # on and let a reverted guard read clean. The sweep gets a home with nothing in it.
    empty_home = sweep_dir / "home"
    (empty_home / ".claude").mkdir(parents=True)
    saved = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME")}
    os.environ.update(HOME=str(empty_home), CLAUDE_CONFIG_DIR=str(empty_home / ".claude"),
                      CODEX_HOME=str(empty_home / ".codex"))
    try:
        missing = [name for name in entry_names if not hasattr(launcher_module, name)]
        if missing:
            mark_fail(f"config type sweep names entry points that no longer exist: {missing}")
            return

        escapes, refusals = sweep(launcher_module)
        for name in REFUSERS:
            if refusals[name] == 0:
                mark_fail(
                    f"config type sweep: {name} refused nothing across {len(keys)} keys, so "
                    "its clean result is about no input at all"
                )
        if escapes:
            mark_fail(
                "a config typo escapes as a raw exception instead of LaunchError: "
                + "; ".join(sorted(set(escapes))[:6])
            )

        # One control per guard, each naming its own literal. Asserting the literal is
        # present before reverting it is the point: a reworded guard fails the gate here
        # rather than silently leaving the control testing nothing.
        source = launcher.read_text(encoding="utf-8")
        controls = [
            ("order", "if not isinstance(order, str) or order not in REVIEW_ORDERS:",
             "if order not in REVIEW_ORDERS:"),
            ("aggregation",
             "if not isinstance(aggregation, str) or aggregation not in REVIEW_AGGREGATIONS:",
             "if aggregation not in REVIEW_AGGREGATIONS:"),
            ("adapter", "if not isinstance(adapter, str) or adapter not in REVIEW_ADAPTERS:",
             "if adapter not in REVIEW_ADAPTERS:"),
            ("resolve_command",
             '    if not isinstance(value, str) or not value:\n'
             '        raise LaunchError(f"command must be a non-empty string, '
             'not {type(value).__name__}")\n',
             ""),
        ]
        blamed = set()
        for index, (label, guard, reverted) in enumerate(controls):
            if guard not in source:
                mark_fail(f"config type sweep control for {label} no longer matches the source")
                continue
            probe_path = sweep_dir / f"control-{index}.py"
            probe_path.write_text(source.replace(guard, reverted, 1), encoding="utf-8")
            spec = importlib.util.spec_from_file_location(f"sweep_control_{index}", probe_path)
            probe = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = probe
            try:
                spec.loader.exec_module(probe)
                caught, _ = sweep(probe)
            finally:
                sys.modules.pop(spec.name, None)
            if not caught:
                mark_fail(
                    f"config type sweep reported nothing with the {label} guard removed — "
                    "it does not test that guard"
                )
            blamed.update(re.search(r"\[([a-z_]+)\]", line).group(1) for line in caught)
        for name in ANSWERERS:
            if name not in blamed:
                mark_fail(
                    f"config type sweep: no control produced a finding through {name}, so "
                    "nothing shows this leg reaches it at all"
                )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(sweep_dir, ignore_errors=True)


@launcher_check
def agent_materialization(fx):
    env, portable_profile_text, tmp = fx.env, fx.portable_profile_text, fx.tmp
    materialization_env = {**env, "XDG_CACHE_HOME": str(tmp / "materialization-cache")}
    configured_runtime = invoke([
        sys.executable, str(launcher), "--preset", "balanced", "--yes", "codex", "--", "probe"
    ], env=materialization_env)
    if configured_runtime.stdout != "backend-output\n":
        mark_fail("configured non-TTY launch polluted backend stdout with its summary")
    if "Launch summary" not in configured_runtime.stderr:
        mark_fail("configured non-TTY launch did not disclose its summary on stderr")
    projected_agent_files = sorted((pathlib.Path(materialization_env["XDG_CACHE_HOME"])
                                    / "agent-launch/codex-agents").glob("*/*.toml"))
    if len(projected_agent_files) != 3:
        mark_fail("configured Codex launch did not materialize three pinned child agents")
    for path in projected_agent_files:
        data = tomllib.loads(path.read_text())
        tier = path.stem
        expected_model, expected_effort = expected_launch_tiers[tier]
        if (data.get("model"), data.get("model_reasoning_effort")) != (
            expected_model, expected_effort
        ):
            mark_fail(f"materialized Codex {tier} binding drifted: {path}")

    custom_codex_home = tmp / "custom-codex-home"
    (custom_codex_home / "agents").mkdir(parents=True)
    for tier in ("frontier", "workhorse", "sweep"):
        (custom_codex_home / "agents" / f"{tier}.toml").write_text(
            (agent_dir / f"{tier}.toml").read_text()
        )
    portable_profile = tmp / "portable.toml"
    portable_profile.write_text(portable_profile_text)
    portable_env = env.copy()
    portable_env.update(
        CODEX_HOME=str(custom_codex_home),
        XDG_CACHE_HOME=str(tmp / "portable-cache"),
    )
    portable = invoke([
        sys.executable, str(launcher), "--config", str(portable_profile),
        "--preset", "balanced", "--yes", "codex", "--", "probe",
    ], env=portable_env)
    if portable.returncode != 0 or len(
        list((tmp / "portable-cache/agent-launch/codex-agents").glob("*/*.toml"))
    ) != 3:
        mark_fail("configured Codex launch did not honor non-default CODEX_HOME")

    env["AGENT_LAUNCH_DEBUG"] = "1"
    configured = invoke([
        sys.executable, str(launcher), "--preset", "balanced", "--yes", "--dry-run",
        "codex", "--", "exec", "probe",
    ], env=env)
    expect_text(
        configured,
        "agent-launch Codex configured projection",
        (
            "configured/requested · completed: not enforced",
            'model_reasoning_effort=\\"xhigh\\"',
            "features.multi_agent=true",
            "--dangerously-bypass-approvals-and-sandbox",
            "forwarded backend args appended last; a projected option cannot be overridden",
            '"exec", "probe"',
        ),
    )
    if configured.returncode == 0:
        codex_argv = json.loads(configured.stdout.splitlines()[-1])
        if codex_argv[-2:] != ["exec", "probe"]:
            mark_fail("agent-launch Codex expert overrides were not appended last")
    # A forward that restates an option the launch projected is refused, on both hosts
    # and in both spellings the CLI accepts (round 18, #2): appended after the projection
    # it won on the command line while the contract went on naming the configured seat.
    # Control: the harmless forwards above pass. Derived from the projection, so the
    # `-c` key form on codex is covered too.
    for host, forward in (
        ("codex", ["--model", "gpt-5.6-luna"]),
        ("codex", ["-m", "gpt-5.6-luna"]),
        ("codex", ["-c", 'model_reasoning_effort="low"']),
        # The attached and short spellings Codex accepts, which slipped past the
        # separated-form parser as ordinary options (round 19, #4).
        ("codex", ['--config=model_reasoning_effort="low"']),
        ("codex", ['-cmodel_reasoning_effort="low"']),
        # The SAME four spellings with whitespace TOML discards. Compared as raw text the
        # spaced form was a different key, so it collided with nothing and was appended
        # last — one space bought the override the un-spaced form is refused for (round 20,
        # #4). All four, because they share one key reader and a fix in three of them is a
        # fix in none.
        ("codex", ['--config=model_reasoning_effort = "low"']),
        ("codex", ["-c", 'model_reasoning_effort = "low"']),
        ("codex", ["--config", 'model_reasoning_effort = "low"']),
        ("codex", ['-cmodel_reasoning_effort = "low"']),
        # And the two other spellings of the same key the parser accepts: a quoted segment,
        # and spacing around the dots of a dotted key.
        ("codex", ["-c", '"model_reasoning_effort" = "low"']),
        ("codex", ["-c", 'agents . sweep . description = "x"']),
        # Every segment quoted is the SAME nested key and must still be refused. The rule
        # is that a dot INSIDE a segment is data while a dot BETWEEN them is structure —
        # not that quoting exempts a key, which is what a fix keyed on the quote character
        # would have amounted to.
        ("codex", ["-c", '"agents"."sweep"."description" = "x"']),
        ("codex", ["--disable", "multi_agent"]),
        ("codex", ["-c", "agents.sweep.description=x"]),
        # An ancestor table of a projected key overrides it wholesale.
        ("codex", ["-c", "agents=x"]),
        ("claude", ["--model", "claude-haiku-4-5"]),
        ("claude", ["--effort", "low"]),
        ("claude", ["--append-system-prompt", "other"]),
    ):
        refused = invoke([
            sys.executable, str(launcher), "--preset", "balanced", "--yes", "--dry-run",
            host, "--", *forward,
        ], env=env)
        if refused.returncode != 2 or "would override what this launch projects" not in refused.stderr:
            mark_fail(
                f"agent-launch {host} accepted forwarded {forward} on a configured launch: "
                f"rc={refused.returncode} — the contract would describe a different run"
            )
    # Keys that merely share a first segment with a projected one are NOT overrides — a
    # second, separate agent beside the projected ones registers fine on the CLI, and the
    # refusal used to fire on it (round 19, #4). These forward.
    # The whitespace spelling of a NON-colliding key is in the list on purpose: canonical
    # keys must make more things compare equal, not make everything collide, and without
    # this a fix that refused every spaced assignment would pass the mutations above.
    # A quoted segment CONTAINING DOTS is a different key from the nested path that spells
    # the same characters: TOML reads `"agents.sweep.description"` as one segment and
    # `agents.sweep.description` as three, and only the second is what the launcher
    # projects. Canonicalising to a dotted STRING made them equal, so a valid forward was
    # refused as an override of something it cannot touch (round 21, #9). Both the literal
    # key and a genuinely nested sibling of it forward.
    for forward in (["-c", 'agents.reviewer.config_file="/x"'],
                    ["-c", 'agents.reviewer.config_file = "/x"'],
                    ["-c", '"agents.sweep.description"="forwarded"'],
                    ["-c", '"features.multi_agent"=true'],
                    ["-c", "notice.hide_full_access_warning=true"]):
        allowed = invoke([
            sys.executable, str(launcher), "--preset", "balanced", "--yes", "--dry-run",
            "codex", "--", *forward,
        ], env=env)
        if allowed.returncode != 0:
            mark_fail(
                f"agent-launch refused forwarded {forward}, which overrides nothing the "
                f"launch projects: {allowed.stderr.strip()[:160]}"
            )
    # The bare path projects nothing and must keep forwarding the same tokens.
    bare = invoke([sys.executable, str(launcher), "--no-tui", "claude", "--", "--model", "x"], env=env)
    if bare.returncode != 0 or fx.argv_log.read_text().splitlines()[-2:] != ["--model", "x"]:
        mark_fail("agent-launch bare launch no longer forwards a --model the configured path refuses")
    configured = invoke([
        sys.executable, str(launcher), "--preset", "balanced", "--yes", "--dry-run",
        "claude", "--", "-p", "probe",
    ], env=env)
    expect_text(
        configured,
        "agent-launch Claude configured projection",
        (
            "configured/requested · completed: not enforced",
            "--append-system-prompt",
            "--agents",
            "--dangerously-skip-permissions",
            '"-p", "probe"',
        ),
    )
    if configured.returncode == 0:
        try:
            projected_argv = json.loads(configured.stdout.splitlines()[-1])
            agents_arg = json.loads(projected_argv[projected_argv.index("--agents") + 1])
        except (ValueError, IndexError, json.JSONDecodeError) as exc:
            mark_fail(f"agent-launch Claude --agents projection is not valid JSON: {exc}")
        else:
            expected_spawnable = {
                tier: expected_claude_tiers[tier]
                for tier in ("frontier", "workhorse", "sweep")
            }
            if set(agents_arg) != set(expected_spawnable):
                mark_fail(
                    "Claude --agents must project exactly the spawnable tiers "
                    f"(HELM is the main, never a subagent): {sorted(agents_arg)}"
                )
            for tier, (model, effort) in expected_spawnable.items():
                role = agents_arg.get(tier, {})
                if role.get("model") != model or role.get("effort") != effort:
                    mark_fail(f"agent-launch Claude {tier} role projection drifted: {role!r}")
                if effort is None and "effort" in role:
                    mark_fail(f"agent-launch Claude {tier} must omit effort rather than emit null")
                if tier == "sweep" and role.get("tools") != ["Read", "Glob", "Grep"]:
                    mark_fail("agent-launch Claude SWEEP must retain its read-only tool surface")
            if projected_argv[-2:] != ["-p", "probe"]:
                mark_fail(
                    "agent-launch Claude expert overrides were not appended last"
                )

    # A Codex agent template is READ as TOML and was WRITTEN as JSON, and the two are not
    # the same language. Every value in a template round-trips by construction — tomllib
    # had just read it — except where the spellings differ: JSON writes a non-finite float
    # as `NaN`/`Infinity` and TOML spells them `nan`/`inf`, so a template carrying one
    # produced a child agent config Codex cannot parse at all (round 24, #11); and a key
    # needing quotes was written bare and became a different key. The subject is a template
    # holding one value of every type this writer accepts, asserted by RE-READING the file
    # the launcher actually wrote — the shipped templates carry plain strings, which is why
    # nothing here could see it.
    launcher_module = fx.launcher_module
    if launcher_module is not None:
        spelling_root = tmp / "agent-template-spelling"
        spelling_root.mkdir(exist_ok=True)
        spelling_template = spelling_root / "probe.toml"
        spelling_template.write_text(
            'description = "probe"\n'
            'limit = nan\nceiling = inf\nfloor = -inf\n'
            'ratio = 1.5\nrounds = 7\nverbose = true\nname = "quoted \\"value\\""\n'
            '"future.field" = "keep-me"\n',
            encoding="utf-8",
        )
        authored = tomllib.loads(spelling_template.read_text(encoding="utf-8"))
        if not any(isinstance(v, float) and repr(v) in ("nan", "inf", "-inf")
                   for v in authored.values()):
            mark_fail(
                "agent-launch agent template spelling: the subject carries no value whose "
                "JSON and TOML spellings differ — vacuous"
            )
        spelling_config = launcher_module.load_config(launch_profile_path)
        spelling_plan = launcher_module.build_plan(spelling_config, "codex", "balanced")
        spelling_plan["agent_templates"] = {
            tier: str(spelling_template) for tier in launcher_module.SPAWNABLE_TIERS
        }
        previous_cache = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = str(spelling_root / "cache")
        try:
            written = launcher_module.codex_agent_configs(spelling_plan, True)
        except Exception as exc:  # noqa: BLE001 — a refusal to write it is a finding too
            mark_fail(
                f"agent-launch agent template spelling: the launcher could not write a "
                f"template value tomllib had just read: {type(exc).__name__}: {exc}"
            )
            written = {}
        finally:
            if previous_cache is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = previous_cache
        for tier, (written_path, _description) in sorted(written.items()):
            try:
                reloaded = tomllib.loads(written_path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                mark_fail(
                    f"agent-launch agent template spelling: the {tier} child agent config "
                    f"this launcher wrote is not TOML, so Codex cannot read the seat it was "
                    f"handed: {exc}"
                )
                continue
            for key, value in authored.items():
                # The two the launcher OWNS and overwrites; everything else is the
                # template author's and must come back as authored.
                if key in ("model", "model_reasoning_effort"):
                    continue
                # `repr`, because `nan != nan`: a value comparison would call the one
                # spelling this is about equal to nothing, including itself.
                if repr(reloaded.get(key)) != repr(value):
                    mark_fail(
                        f"agent-launch agent template spelling: the {tier} config wrote "
                        f"{key!r} as {reloaded.get(key)!r} where the template authored "
                        f"{value!r} — a template value is carried, never respelled"
                    )


@launcher_check
def vanilla_mode(fx):
    backend, env = fx.backend, fx.env
    # Vanilla (mode=software-engineer): the raw backend with nothing applied — no
    # launch contract, no agents, no permission-bypass flag.
    vanilla_configured = invoke([
        sys.executable, str(launcher), "--preset", "vanilla", "--yes", "--dry-run",
        "claude",
    ], env=env)
    if vanilla_configured.returncode != 0:
        mark_fail(
            f"agent-launch vanilla dry-run failed: {vanilla_configured.stderr.strip()}"
        )
    else:
        vanilla_argv = json.loads(vanilla_configured.stdout.splitlines()[-1])
        for forbidden in (
            "--append-system-prompt", "--agents", "--dangerously-skip-permissions",
        ):
            if forbidden in vanilla_argv:
                mark_fail(f"agent-launch vanilla preset unexpectedly carried {forbidden}")
        if vanilla_argv != [str(backend)]:
            mark_fail(
                "agent-launch vanilla preset must project the bare backend with "
                f"nothing applied: {vanilla_argv!r}"
            )


@launcher_check
def cross_family(fx):
    env, launcher_module, profile_text, tmp = fx.env, fx.launcher_module, fx.profile_text, fx.tmp
    # Cross-family default: each main routes every review route to the OPPOSITE
    # model family, with concrete tools/paths/bindings named in the contract.
    # The cross CODEX_HOME needs the reviewer wrappers (bin) and the same-family
    # agent templates (agents) that the codex fallback floor still materializes.
    cross_home = tmp / "cross-codex-home"
    (cross_home / "bin").mkdir(parents=True)
    (cross_home / "agents").mkdir(parents=True)
    for wrapper in ("codex-run", "codex-helm"):
        wrapper_path = cross_home / "bin" / wrapper
        wrapper_path.write_text("#!/usr/bin/env bash\nexit 0\n")
        wrapper_path.chmod(0o755)
    for tier in ("frontier", "workhorse", "sweep"):
        (cross_home / "agents" / f"{tier}.toml").write_text(
            (agent_dir / f"{tier}.toml").read_text()
        )
    cross_env = env.copy()
    cross_env["CODEX_HOME"] = str(cross_home)

    # Per-reviewer prose is deliberately NOT asserted here any more. The 192-cell
    # golden pins the entire rendered contract byte-for-byte — a strictly stronger
    # check that also covers reviewers this repo has never seen, which a substring
    # list structurally cannot. What stays below is per-MECHANISM and per-BINDING:
    # those are core code, so pinning them once covers every method that derives them.
    # These pin the legacy cross-family MECHANISM prose, so the subject has to stay
    # legacy. deep-review migrated; borrowing it again would make the pin follow the
    # defaults instead of guarding the compatibility path it exists for.
    cross_profile = tmp / "cross-legacy.toml"
    # Two presets: native-panel pins the cross NATIVE mechanism prose, ultracode pins
    # the cross DEEP mechanism prose — no remaining legacy setup carries both routes.
    cross_profile.write_text(
        profile_text
        + legacy_preset_toml("gate-cross", "native-panel", family="cross")
        + legacy_preset_toml("gate-cross-deep", "ultracode", family="cross")
    )
    claude_cross = invoke([
        sys.executable, str(launcher), "--config", str(cross_profile),
        "--preset", "gate-cross", "--yes", "--dry-run", "claude",
    ], env=cross_env)
    expect_text(
        claude_cross,
        "agent-launch Claude cross-family (gpt/codex) review projection",
        (
            "Review family=cross",
            "run EVERY review route on OpenAI/Codex",
            "codex-run --profile hermetic",
            f"frontier={expected_launch_tiers['frontier'][0]}/{expected_launch_tiers['frontier'][1]}",
        ),
    )
    codex_cross = invoke([
        sys.executable, str(launcher), "--config", str(cross_profile),
        "--preset", "gate-cross", "--yes", "--dry-run", "codex",
    ], env=cross_env)
    expect_text(
        codex_cross,
        "agent-launch Codex cross-family (anthropic/claude) review projection",
        (
            "Review family=cross",
            "run EVERY review route on Anthropic/Claude",
            "-p --model <review tier>",
            "--permission-mode plan",
            "frontier=claude-fable-5-1/max",
        ),
    )
    claude_deep = invoke([
        sys.executable, str(launcher), "--config", str(cross_profile),
        "--preset", "gate-cross-deep", "--yes", "--dry-run", "claude",
    ], env=cross_env)
    expect_text(
        claude_deep,
        "agent-launch Claude cross-family deep exec projection",
        (
            "Review family=cross",
            "deep exec: run",
            # Quote-free needles: the dry-run's last line is JSON argv, so quotes in
            # the contract reach stdout escaped.
            f"exec -s read-only -m {expected_launch_tiers['frontier'][0]} -c model_reasoning_effort=",
            "only when a faster, shallower pass is explicitly wanted",
        ),
    )
    codex_deep = invoke([
        sys.executable, str(launcher), "--config", str(cross_profile),
        "--preset", "gate-cross-deep", "--yes", "--dry-run", "codex",
    ], env=cross_env)
    expect_text(
        codex_deep,
        "agent-launch Codex cross-family deep workflow projection",
        (
            "Review family=cross",
            "--effort ultracode -p <self-contained review packet>",
            "workflow-orchestration review",
        ),
    )

    # Module-level: the composable deep-review preset pins the deep reviewers' rendered
    # dispatch. On a claude main the reviewer is codex-exec at the authored seat — the
    # exec flags are the mechanism and the fast tier stays an explicit opt-in; on a
    # codex main it is the Claude workflow, opened by the keyword.
    cross_cfg = tomllib.loads(profile_text)
    for main_host, needle in (
        ("claude", 'exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort="ultra"'),
        ("codex", "prompt carries the keyword ultracode"),
    ):
        cross_plan = launcher_module.build_plan(cross_cfg, main_host, "deep-review")
        contract = launcher_module.run_contract(cross_plan)
        if needle not in contract:
            mark_fail(f"agent-launch {main_host} deep-review dispatch missing: {needle!r}")

    # A config with only one host degrades cross review to same-family instead of
    # crashing on the absent opposite host.
    single_host_cfg = tomllib.loads(profile_text)
    single_host_cfg["hosts"].pop("claude", None)
    single_host_cfg["backends"].pop("claude", None)
    try:
        # A LEGACY preset still degrades cross review to same-family rather than crashing.
        single_plan = launcher_module.build_plan(single_host_cfg, "codex", "solo")
        if single_plan["review_family"] != "same":
            mark_fail("agent-launch single-host config did not coerce cross review to same")
        single_contract = launcher_module.run_contract(single_plan)
        # Coercion must be TOLD, not only done. The plan used to keep the coerced value
        # alone, so the session read "Review family=same" as though the preset had chosen
        # it (round 18, #8). The requested family survives on the plan and the header
        # names both. `solo` is a shipped cross-family preset — the guard below keeps
        # this from passing vacuously if it ever migrates.
        if single_plan.get("review_family_requested") != "cross":
            mark_fail(
                "agent-launch single-host coercion lost the requested family: plan carries "
                f"review_family_requested={single_plan.get('review_family_requested')!r}, "
                "expected 'cross' (or the subject preset is no longer cross-family)"
            )
        if "Review family=same (configured cross;" not in single_contract:
            mark_fail(
                "agent-launch single-host coercion is silent in the contract: the session "
                "is told same-family was the configured choice — "
                f"{single_contract[:200]!r}"
            )
        # The edited-plan path coerces through the same function, or the two paths drift.
        edited = copy.deepcopy(single_plan)
        launcher_module.apply_review_plan(edited, single_host_cfg, edited["review_plan"])
        if (edited["review_family"], edited.get("review_family_requested")) != ("same", "cross"):
            mark_fail(
                "agent-launch apply_review_plan does not coerce the family the way "
                f"build_plan does: {edited['review_family']!r}/"
                f"{edited.get('review_family_requested')!r}"
            )
        # The Customize path lowered the EFFECTIVE family into the legacy IR, so merely
        # reselecting the current setup on a single-host machine turned the fallback into
        # the request, and the save path then saved it (round 19, #8). Driven through the
        # real customize loop with its chooser answered; the plan must keep the request
        # and the projected preset must save `cross`.
        customized = copy.deepcopy(single_plan)
        answers = iter(["review", "none", "start"])
        globals_ = launcher_module.customize.__globals__
        real_choose = globals_["choose"]
        globals_["choose"] = lambda *a, **k: next(answers)
        try:
            launcher_module.customize(customized, single_host_cfg, launch_profile_path)
        except Exception as exc:  # noqa: BLE001 — a crash here is the finding
            mark_fail(f"agent-launch customize did not run on the single-host plan: {exc!r}")
        finally:
            globals_["choose"] = real_choose
        saved_family = launcher_module.preset_from_plan(customized, single_host_cfg, "saved")[0].get("review_family")
        if (customized["review_family"], customized.get("review_family_requested"), saved_family) != ("same", "cross", "cross"):
            mark_fail(
                "agent-launch customize made the single-host family fallback permanent: "
                f"plan={customized['review_family']!r}/"
                f"{customized.get('review_family_requested')!r} saved={saved_family!r}"
            )
    except launcher_module.LaunchError as exc:
        mark_fail(f"agent-launch single-host config raised instead of degrading: {exc}")
    except Exception as exc:
        mark_fail(f"agent-launch single-host config crashed (not a clean degrade): {exc!r}")
    # A migrated preset names the other family explicitly. On a single-host config it used
    # to fail closed; it now LAUNCHES and degrades to the main seat, because cross-family
    # is a strong recommendation and not a requirement — a user with one provider must
    # still get review. What C7 was protecting was never the refusal itself but the
    # silence: a degrade that nobody is told about is the thing this work exists to stop.
    # So the assertion moved from "must raise" to "must say so", and the contract text is
    # part of it — a report that records DEGRADED where the launch prints nothing would
    # satisfy a status-only check while telling the user nothing.
    try:
        degraded_plan = launcher_module.build_plan(single_host_cfg, "codex", "balanced")
        contract = launcher_module.run_contract(degraded_plan)
    except Exception as exc:
        mark_fail(
            f"agent-launch refused a cross-family preset on a single-host config instead "
            f"of degrading to the main seat: {exc!r}"
        )
    else:
        report = degraded_plan.get("review_report")
        if report is None:
            mark_fail("agent-launch degraded a composable preset without a review report")
        elif report.base.status != launcher_module.STATUS_DEGRADED:
            mark_fail(
                f"agent-launch fell back to the main seat with status "
                f"{report.base.status!r}, not DEGRADED; the user is not told an axis was "
                f"lost"
            )
        elif report.base.grade != "perspective_floor":
            mark_fail(
                f"agent-launch graded a same-main fallback {report.base.grade!r}, not "
                "perspective_floor; it claims independence it did not buy"
            )
        # The READABLE body, not the whole contract. run_contract appends a ReviewPlan/v1
        # JSON generated from the same report, and it carries "status":"DEGRADED" by
        # construction — so a whole-contract membership test cannot fail on this branch
        # whatever the renderer emits. Same trap as C19, dug again in the very assertion
        # written to prevent a silent degrade.
        elif launcher_module.STATUS_DEGRADED not in contract.partition(
            launcher_module.REVIEW_PLAN_MARKER
        )[0]:
            mark_fail(
                "agent-launch degraded the base but the human-readable contract never says "
                "so; the machine record alone is not telling the user, and a silent degrade "
                "to the main's own family is exactly what must not happen"
            )
    # `balanced` above carries no methods, so it says nothing about the OTHER half of §1:
    # the base falls back, an optional method DROPS. `deep-review` binds onto and
    # ultracode, both unreachable on a single-host config, and without a subject that
    # actually has them the drop path shipped untested — mutating it away changed nothing.
    try:
        methods_plan = launcher_module.build_plan(single_host_cfg, "codex", "deep-review")
    except Exception as exc:
        mark_fail(f"agent-launch refused a method-bearing preset on one host: {exc!r}")
    else:
        method_report = methods_plan.get("review_report")
        dropped = [
            row for row in (method_report.methods if method_report else ())
            if row.status == launcher_module.STATUS_DROPPED
        ]
        if not dropped:
            mark_fail(
                "agent-launch dropped no method on a single-host config; an optional "
                "method whose provider has no host must become unavailable, never be "
                "rebound to the seat the base fell back to"
            )
        elif not any("has no configured host" in (row.detail or "") for row in dropped):
            mark_fail(
                f"agent-launch dropped a method without naming the missing host as the "
                f"reason: {[row.detail for row in dropped]}"
            )
        # DROPPED at launch must not mean DELETED on save. The plan cannot seat these
        # bindings, which is no licence to forget them: a serializer that reads "no
        # binding" as "never authored" destroys the user's own configuration the moment
        # they open the preset in Custom and save it, and they are never told.
        authored = set(methods_plan["review_plan"].methods)
        try:
            block = launcher_module.review_block_from_plan(methods_plan)
        except Exception as exc:
            mark_fail(f"agent-launch could not save a degraded composable plan: {exc!r}")
        else:
            if block is None:
                mark_fail(
                    "agent-launch saved a degraded composable preset as no review block "
                    "at all; an unseatable base is not an unauthored one"
                )
            else:
                arm = block.get(launcher_module.REVIEW_ARMS_KEY, {}).get(
                    methods_plan["host"], block
                )
                saved = set((arm or {}).get("methods") or {})
                if not authored:
                    mark_fail("agent-launch review save: no authored methods — vacuous")
                elif saved != authored:
                    mark_fail(
                        f"agent-launch saved {sorted(saved)} of the authored methods "
                        f"{sorted(authored)}; a binding this profile cannot seat must be "
                        f"written back as authored, not silently deleted"
                    )
                elif (arm or {}).get("base") is None:
                    mark_fail(
                        "agent-launch saved a degraded preset without its base binding"
                    )
        # …and the same must survive an EDITOR round trip. The editor lists only bindings
        # this profile can seat, so an unseatable one never appears in its draft; rebuilding
        # the plan from what is visible deleted a method the user was never shown. Asserted
        # through `edited_review_plan`, the seam the TUI branch calls, so this checks the
        # real construction rather than a copy of it.
        draft_methods = {
            method_id: binding
            for method_id, binding in methods_plan["review_plan"].methods.items()
            if binding is not None
        }
        edited = launcher_module.edited_review_plan(
            methods_plan["review_plan"],
            methods_plan["review_plan"].base_binding,
            draft_methods,
        )
        if set(edited.methods) != authored:
            mark_fail(
                f"agent-launch review editor: applying a draft kept {sorted(edited.methods)} "
                f"of the authored methods {sorted(authored)}; a binding the editor cannot "
                f"show is still the user's, and dropping it deletes a choice never made"
            )
        elif set(edited.methods_unseated) != {
            m for m, b in methods_plan["review_plan"].methods.items() if b is None
        }:
            mark_fail(
                f"agent-launch review editor: applying a draft lost the raw tables for "
                f"{sorted(authored - set(edited.methods_unseated))}, so the next save "
                f"cannot write them back"
            )

    # An all-disabled option list raises a clean LaunchError, not a hang.
    try:
        launcher_module.choose(
            "empty", [launcher_module.MenuOption("a", "A", "d", enabled=False)], "a"
        )
        mark_fail("agent-launch choose accepted an all-disabled option list")
    except launcher_module.LaunchError:
        pass


@launcher_check
def same_family(fx):
    backend, env, profile_text, tmp = fx.backend, fx.env, fx.profile_text, fx.tmp
    # review_family=same lands review on the LAUNCH host, and the deep route follows it
    # (round 18, #4): on a Codex main it is codex exec, and the executable line must name
    # the RESOLVED codex CLI — the capability's command is `${backend}`, so a literal
    # token here would mean the resolution never ran. On a Claude main it is the host's
    # own workflow, user-triggered, and no Codex executable may be named beside it. This
    # check used to assert the Claude-to-Codex combination as correct.
    same_family_profile = tmp / "same-family.toml"
    same_family_profile.write_text(
        profile_text + legacy_preset_toml("gate-degrade", "ultracode", family="same")
    )
    same_family_codex = invoke([
        sys.executable, str(launcher), "--config", str(same_family_profile),
        "--preset", "gate-degrade", "--yes", "--dry-run", "codex",
    ], env=env)
    expect_text(
        same_family_codex,
        "agent-launch review_family=same on a codex main names the codex deep route",
        (
            "Review family=same",
            "Codex-backed deep review route",
            f"Deep-exec executable: {backend}",
        ),
        ("cross-family review", "/code-review ultra"),
    )
    same_family_claude = invoke([
        sys.executable, str(launcher), "--config", str(same_family_profile),
        "--preset", "gate-degrade", "--yes", "--dry-run", "claude",
    ], env=env)
    expect_text(
        same_family_claude,
        "agent-launch review_family=same on a claude main names the claude deep route",
        (
            "Review family=same",
            "The deep route on a Claude seat is /code-review ultra",
        ),
        ("cross-family review", "Codex-backed", "Deep-exec executable:"),
    )

    frontier_profile = tmp / "frontier.toml"
    frontier_profile.write_text(
        profile_text + legacy_preset_toml("gate-frontier-main", "none")
        .replace('main_tier = "helm"', 'main_tier = "frontier"', 1)
        .replace('frontier_effort = "max"', 'frontier_effort = "ultra"', 1)
    )
    configured = invoke([
        sys.executable, str(launcher), "--config", str(frontier_profile),
        "--preset", "gate-frontier-main", "--yes", "--dry-run", "codex",
    ], env=env)
    expect_text(
        configured,
        "agent-launch FRONTIER main effort projection",
        ('Main           FRONTIER · gpt-6-astra · ultra', 'main=frontier (gpt-6-astra/ultra)'),
    )

    # A Claude main's same-family deep route is the host's own workflow, so it must NOT
    # depend on the codex CLI: with the codex backend missing it stays effective. This
    # scenario used to assert the opposite — that a claude main degrades to native when
    # codex is absent — which was the Claude-to-Codex hardwiring seen from the other
    # side. The first fixture-backend occurrence is [backends.codex].
    unavailable_profile = tmp / "unavailable.toml"
    unavailable_profile.write_text(
        profile_text.replace(
            f"command = {json.dumps(str(backend))}",
            f"command = {json.dumps(str(tmp / 'missing-codex'))}",
            1,
        ) + legacy_preset_toml("gate-degrade", "ultracode", family="same")
    )
    unavailable_claude = invoke([
        sys.executable, str(launcher), "--config", str(unavailable_profile),
        "--preset", "gate-degrade", "--yes", "--dry-run", "claude",
    ], env=env)
    expect_text(
        unavailable_claude,
        "agent-launch claude same-family deep route with codex absent",
        ("The deep route on a Claude seat is /code-review ultra",),
        ("ultracode unavailable", "Deep-exec executable:", "--mcp-config"),
    )
    # The degrade-to-native path still needs a subject, and the one place a same-family
    # deep route can go missing is a Codex main whose codex-exec capability does not
    # resolve. Overridden on the capability, not the backend: the backend is the CLI being
    # launched. The block's own `command` line is rewritten, so the first `${backend}`
    # occurrence in the file — a different capability's — is left alone.
    head, _, tail = profile_text.partition("[capabilities.codex-exec]")
    if not tail:
        mark_fail("agent-launch degrade scenario: the profile has no [capabilities.codex-exec]")
    else:
        tail = tail.replace(
            'command = "${backend}"', f"command = {json.dumps(str(tmp / 'missing-codex-exec'))}", 1
        )
        degrade_profile = tmp / "degrade.toml"
        degrade_profile.write_text(
            head + "[capabilities.codex-exec]" + tail
            + legacy_preset_toml("gate-degrade", "ultracode", family="same")
        )
        unavailable_codex = invoke([
            sys.executable, str(launcher), "--config", str(degrade_profile),
            "--preset", "gate-degrade", "--yes", "--dry-run", "codex",
        ], env=env)
        if expect_text(
            unavailable_codex,
            "agent-launch codex degrade-to-native review",
            (
                "Review setup   ultracode → effective native (ultracode unavailable)",
                "fall back to native same-model subagent review",
            ),
            ("Deep-exec executable:",),
        ):
            codex_degraded_argv = json.loads(unavailable_codex.stdout.splitlines()[-1])
            if "features.multi_agent=true" not in codex_degraded_argv:
                mark_fail("agent-launch codex degrade dropped native multi-agent review")


@launcher_check
def cross_floor_contract(fx):
    """A cross-family request that resolves to a same-family floor is rendered from what
    RESOLVED. The cross renderer opened with "run EVERY review route on <other family>"
    unconditionally and then, when only the slash floor remained, told the same reader
    that this route cannot be dispatched cross-family (round 18, #5) — and the golden
    pinned both sentences. Mutation: family=cross with a same-family-only setup. Control:
    the same setup at family=same, which is simply effective and says neither."""
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    try:
        config = launcher_module.load_config(launch_profile_path)
    except launcher_module.LaunchError as exc:
        mark_fail(f"cross floor contract: could not load the shipped profile: {exc}")
        return
    if not set(launcher_module.REVIEW_ROUTES.get("slash-review", ())) & \
            set(launcher_module.SAME_FAMILY_ROUTES):
        mark_fail("cross floor contract: slash-review no longer routes to a same-family "
                  "route, so this check has no floor subject")
        return
    seen = {}
    for family in ("cross", "same"):
        cfg = copy.deepcopy(config)
        preset = copy.deepcopy(cfg["presets"]["solo"])
        preset.pop("review", None)
        preset["review_setup"] = "slash-review"
        preset["review_family"] = family
        cfg["presets"]["gate-floor"] = preset
        try:
            plan = launcher_module.build_plan(cfg, "claude", "gate-floor")
            contract = launcher_module.run_contract(plan)
            effective, _, floor = launcher_module.effective_review(plan)
        except Exception as exc:  # noqa: BLE001 — any failure here is the finding
            mark_fail(f"cross floor contract: {family} subject did not build: {exc!r}")
            return
        seen[family] = (contract, effective, floor)
    contract, effective, floor = seen["cross"]
    if effective or floor != "slash":
        mark_fail(f"cross floor contract: mutation is not a floor-only plan "
                  f"(effective={effective}, floor={floor!r}) — the assertion below is vacuous")
    if "run EVERY review route" in contract:
        mark_fail("cross floor contract: nothing runs cross-family, yet the contract commands "
                  f"every route to run cross-family: {contract[:240]!r}")
    if "Cross-family review was requested" not in contract:
        mark_fail("cross floor contract: the reader is not told cross-family was requested and "
                  f"did not resolve: {contract[:240]!r}")
    if "cannot be dispatched cross-family" not in contract:
        mark_fail("cross floor contract: the floor is not named as PROPOSED same-family: "
                  f"{contract[:240]!r}")
    control, effective, floor = seen["same"]
    if effective != ["slash"] or floor is not None:
        mark_fail(f"cross floor contract: control is not a plain same-family plan "
                  f"(effective={effective}, floor={floor!r})")
    for absent in ("run EVERY review route", "Cross-family review was requested",
                   "cannot be dispatched cross-family"):
        if absent in control:
            mark_fail(f"cross floor contract: the same-family control carries {absent!r}, so "
                      "the mutation's reading is not specific to the floor case")


@launcher_check
def preset_save_round_trips(fx):
    """Saving a setup and reloading it must project the same launch.

    "Save these settings globally" is the only path that persists a user's work, and the
    only thing worth asserting about it is that what comes back is what went in. Field-by
    -field comparison would miss the failure that was here: `mode` was never written, so
    every saved preset reloaded as `builder`, and saving Vanilla — zero arguments, no
    contract, no permission flag, the whole point of it — returned a preset projecting
    eight. Comparing the PROJECTION catches that without needing to know which field was
    dropped, which is the property that survives the next field being added.

    Presets carrying a mission are refused rather than round-tripped, and that is asserted
    here too: a saved preset cannot reproduce one, and writing it anyway is how a menu
    entry comes to start something other than its name.
    """
    launcher_module = fx.launcher_module
    if launcher_module is None:
        return
    workspace = fx.tmp / "preset-round-trip"
    workspace.mkdir(exist_ok=True)
    profile = workspace / "agent-launch.toml"
    profile.write_text(fx.profile_text, encoding="utf-8")

    shipped = sorted(tomllib.loads(fx.profile_text)["presets"])
    if not shipped:
        mark_fail("preset round-trip: no shipped presets to save, so the check is vacuous")
        return

    saved = refused = cross_host = 0
    for host in ("codex", "claude"):
        other = "claude" if host == "codex" else "codex"
        for preset in shipped:
            config = launcher_module.load_config(profile)
            try:
                plan = launcher_module.build_plan(config, host, preset)
            except launcher_module.LaunchError:
                continue
            before = launcher_module.project_args(plan, materialize_agents=False)
            # What the SOURCE preset projects on the host it is not being saved from. Every
            # comparison here was same-host, so a value the save read off the active host's
            # resolution and wrote back for that host alone was invisible: saving shipped
            # `deep-review` from Claude moved Codex's frontier effort from `ultra` to the
            # host default, and both hosts' round trips passed (round 22, #6).
            try:
                before_other = launcher_module.project_args(
                    launcher_module.build_plan(config, other, preset),
                    materialize_agents=False,
                )
            except launcher_module.LaunchError:
                before_other = None
            name = f"roundtrip-{host}-{preset}"
            try:
                launcher_module.save_preset(plan, config, profile, name)
            except launcher_module.LaunchError:
                # Refusal is a valid outcome, but only for a setup that really cannot be
                # reproduced — anything else refusing would be a silent loss of coverage.
                if not (plan.get("mission") or plan.get("trigger")):
                    mark_fail(f"preset round-trip: {host}/{preset} was refused despite "
                              "carrying no mission or trigger")
                else:
                    refused += 1
                continue
            reloaded = launcher_module.load_config(profile)
            if name not in reloaded["presets"]:
                mark_fail(f"preset round-trip: {host}/{preset} saved but did not reload")
                continue
            after = launcher_module.project_args(
                launcher_module.build_plan(reloaded, host, name), materialize_agents=False
            )
            saved += 1
            if before != after:
                mark_fail(
                    f"preset round-trip: {host}/{preset} projects {len(before)} argument(s) "
                    f"before saving and {len(after)} after reloading it"
                )
            if before_other is not None:
                cross_host += 1
                after_other = launcher_module.project_args(
                    launcher_module.build_plan(reloaded, other, name),
                    materialize_agents=False,
                )
                if before_other != after_other:
                    mark_fail(
                        f"preset round-trip: saving {host}/{preset} changed what the preset "
                        f"projects on {other} — "
                        f"{sorted(set(before_other) ^ set(after_other))!r} differs, so a save "
                        f"on one host rebound the other"
                    )
    if cross_host == 0:
        mark_fail("preset round-trip: no preset built on the inactive host, so the "
                  "cross-host comparison judged nothing")
    if saved == 0:
        mark_fail("preset round-trip: nothing was saved, so no comparison happened")
    if refused == 0:
        mark_fail("preset round-trip: no setup was refused, so the mission rule this leg "
                  "also asserts was never exercised")

    # A candidate that PARSES and BEHAVES differently. Everything above compares what the
    # renderer produced today against what reloading it projects, so the two agree by
    # construction and the comparison never had a disagreeing subject: `save_preset`
    # reparsed the candidate for syntax, wrote it, replaced the file and reported success
    # while the reloaded preset bound a different model (spec round, #7). The renderer is
    # mutated to emit a parseable block that projects a different launch, and the save must
    # refuse by name AND leave the file on disk untouched — reporting a refusal after
    # replacing the file is the same failure wearing an error message.
    config = launcher_module.load_config(profile)
    behaviour_plan = launcher_module.build_plan(config, "codex", "balanced")
    presets_file = launcher_module.user_presets_path(profile)
    launcher_module.save_preset(behaviour_plan, config, profile, "behaviour-control")
    before_bytes = presets_file.read_bytes()
    real_render = launcher_module.render_preset_block
    mutated = None
    try:
        def drifting_render(*args, **kwargs):
            nonlocal mutated
            text = real_render(*args, **kwargs)
            mutated = text.replace('main_tier = "helm"', 'main_tier = "workhorse"', 1)
            return mutated
        launcher_module.render_preset_block = drifting_render
        try:
            launcher_module.save_preset(behaviour_plan, config, profile, "behaviour-probe")
        except launcher_module.LaunchError as exc:
            if "projects a different launch" not in str(exc):
                mark_fail(
                    f"preset save: a candidate that parses and projects differently was "
                    f"refused for another reason: {exc}"
                )
        else:
            mark_fail(
                "preset save: a candidate that parses cleanly and projects a different "
                "launch was written and reported as saved — parsing proves the next launch "
                "can READ the file, never what it then runs"
            )
    finally:
        launcher_module.render_preset_block = real_render
    if mutated is None or 'main_tier = "workhorse"' not in (mutated or ""):
        mark_fail(
            "preset save: the behavioural mutation did not apply to the rendered block — "
            "the refusal above was about something else, so the case is vacuous"
        )
    if presets_file.read_bytes() != before_bytes:
        mark_fail(
            "preset save: the refused candidate still changed the presets file on disk — "
            "'nothing was written' has to be true of the file, not only of the message"
        )
    # The positive control the case above needs: with the renderer untouched, the SAME plan
    # under the SAME name saves. Otherwise a save_preset that refused everything would pass.
    try:
        launcher_module.save_preset(behaviour_plan, config, profile, "behaviour-probe")
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"preset save: the unmutated candidate was refused too ({exc}) — the "
            f"behavioural case above then only proves the save refuses everything"
        )
    else:
        if "behaviour-probe" not in tomllib.loads(
            presets_file.read_text(encoding="utf-8")
        ).get("presets", {}):
            mark_fail("preset save: the unmutated candidate reported success and wrote nothing")

    # A PUBLISH that fails leaves no temporary behind. The candidate was written under a
    # dotted temporary and published with `os.replace`, with no cleanup on the way out: an
    # `os.replace` that fails leaves the complete candidate sitting beside the preset file
    # it did not replace, for the next reader — or the next save's glob — to find (spec
    # round 2, #6). The old file staying intact was already true and is asserted here too,
    # because a fix that published straight to the final name would satisfy the leftover
    # assertion by destroying that one.
    #
    # Injected at the PUBLISH step and in a subprocess, for the reason `launcher_receipt_
    # adapters` gives about the emitter: a blocked destination is no discriminator, because
    # a save that writes the final name directly never calls `os.replace` and simply
    # succeeds.
    presets_file = launcher_module.user_presets_path(profile)
    launcher_module.save_preset(behaviour_plan, config, profile, "publish-control")
    intact_bytes = presets_file.read_bytes()
    publish_probe = subprocess.run(
        [sys.executable, "-c",
         "import runpy, sys\n"
         f"m = runpy.run_path({str(launcher.resolve())!r})\n"
         "def _no_publish(*args, **kwargs):\n"
         "    raise OSError('injected publish failure')\n"
         "m['os'].replace = _no_publish\n"
         f"cfg = m['load_config'](m['pathlib'].Path({str(profile)!r}))\n"
         "plan = m['build_plan'](cfg, 'codex', 'balanced')\n"
         "try:\n"
         f"    m['save_preset'](plan, cfg, m['pathlib'].Path({str(profile)!r}), 'publish-probe')\n"
         "except m['LaunchError'] as exc:\n"
         "    print('refused: ' + str(exc))\n"
         "    sys.exit(1)\n"
         "print('saved anyway')\n"],
        capture_output=True, text=True, cwd=str(pathlib.Path.cwd()), env=fx.env,
    )
    publish_output = publish_probe.stdout + publish_probe.stderr
    if publish_probe.returncode == 0 or "refused:" not in publish_output:
        mark_fail(
            f"preset save: a save whose publish step fails did not refuse "
            f"(rc={publish_probe.returncode}) — the candidate reached its final name "
            f"without being published: {publish_output.strip()[:200]}"
        )
    strays = sorted(
        path.name for path in presets_file.parent.iterdir() if path.name.endswith(".tmp")
    )
    if strays:
        mark_fail(
            f"preset save: a save whose publish step failed left its temporary behind: "
            f"{strays!r} — the complete candidate is sitting beside the file it did not "
            f"replace"
        )
    if presets_file.read_bytes() != intact_bytes:
        mark_fail(
            "preset save: a save whose publish step failed still changed the presets file — "
            "the old file has to survive a failure before the replace"
        )
    # The positive control: with nothing injected, the same save succeeds and leaves no
    # temporary either. Without it the leftover assertion is satisfied by a save that never
    # writes anything at all.
    launcher_module.save_preset(behaviour_plan, config, profile, "publish-probe")
    strays = sorted(
        path.name for path in presets_file.parent.iterdir() if path.name.endswith(".tmp")
    )
    if strays or "publish-probe" not in tomllib.loads(
        presets_file.read_text(encoding="utf-8")
    ).get("presets", {}):
        mark_fail(
            f"preset save: an ordinary save did not write the preset or left a temporary "
            f"behind ({strays!r}) — the injected-failure case above then proves nothing"
        )

    # Concurrent saves must not lose one another. `os.replace` makes each write atomic and
    # leaves the read-modify-write SEQUENCE unguarded: two launchers each read the file,
    # each append their own block to the copy they read, and the second replace erases the
    # first. Three saves reported success and left two presets behind — the failure mode
    # is a save the user was told worked. Real processes, because a lock is exactly the
    # thing an in-process loop cannot test.
    # Every spelling TOML accepts for the same table name must be recognised as that name.
    # This class has now arrived twice: bare-header matching missed `[presets."name"]` and
    # a trailing comment, and stripping quote bytes then missed `[presets."name"]`,
    # which tomllib reads as `name`. Each time the old table survived, the new one was
    # appended, and the next launch died on a duplicate key before drawing a screen. The
    # assertion is agreement with tomllib rather than a list of spellings, so the next
    # spelling nobody thought of is covered by the same line.
    spellings = [
        "[presets.spellcheck]",
        '[presets."spellcheck"]',
        "[presets.'spellcheck']",
        "[presets.spellcheck]  # a comment",
        '[presets."spell\\u0063heck"]',
        '[presets."dotted.name"]',
        "[presets.spellcheck.sub]",
    ]
    for header in spellings:
        try:
            document = tomllib.loads(header + "\n")
        except tomllib.TOMLDecodeError:
            mark_fail(f"preset header spelling probe is not valid TOML: {header!r}")
            continue
        expected: list[str] = []
        node = document
        while isinstance(node, dict) and len(node) == 1:
            key, value = next(iter(node.items()))
            expected.append(key)
            node = value
        seen = launcher_module._preset_header_name(header)
        if seen != tuple(expected):
            mark_fail(
                f"the preset writer reads {header!r} as {seen!r} while tomllib reads it as "
                f"{tuple(expected)!r} — a save against that name leaves both tables and the "
                "next launch cannot parse the file"
            )

    # Asserted by HOLDING the lock, not by racing for it. Two savers colliding is what the
    # defect looked like — three reported success and two survived — but a timing collision
    # is not guaranteed to happen, so a race-shaped assertion passes whenever the schedule
    # is kind and the control that removes the lock passes with it. Taking the lock here
    # and requiring the saver to wait tests the same property with an answer that does not
    # depend on the scheduler.
    saver = workspace / "saver.py"
    saver.write_text(
        "import sys, pathlib, importlib.util\n"
        "cfg = pathlib.Path(sys.argv[1])\n"
        f"spec = importlib.util.spec_from_file_location('agl', {str(launcher.resolve())!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['agl'] = mod; spec.loader.exec_module(mod)\n"
        "config = mod.load_config(cfg)\n"
        "plan = mod.build_plan(config, 'codex', 'balanced')\n"
        "mod.save_preset(plan, config, cfg, sys.argv[2])\n",
        encoding="utf-8",
    )
    presets_file = launcher_module.user_presets_path(profile)
    presets_file.unlink(missing_ok=True)
    lock_path = presets_file.with_name(presets_file.name + ".lock")
    held = os.open(lock_path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    blocked = None
    try:
        with os.fdopen(held, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            worker = subprocess.Popen(
                [sys.executable, str(saver), str(profile), "lock-probe"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            try:
                worker.communicate(timeout=4)
                blocked = False          # it finished while another holder had the lock
            except subprocess.TimeoutExpired:
                blocked = True
        # Lock released here; the saver should now be able to finish.
        if blocked:
            worker.communicate(timeout=30)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.communicate()
    if blocked is False:
        mark_fail("preset save took no exclusive lock — a second launcher saving at the "
                  "same moment reads the file this one is about to replace, and the later "
                  "write erases the earlier preset while both report success")
    elif not presets_file.is_file() or "lock-probe" not in tomllib.loads(
        presets_file.read_text(encoding="utf-8")
    ).get("presets", {}):
        mark_fail("preset save waited for the lock and then did not write once it was "
                  "released, so the wait is not the thing being tested here")


@launcher_check
def preset_save(fx):
    argv_log, env, launcher_module, profile_text, tmp = fx.argv_log, fx.env, fx.launcher_module, fx.profile_text, fx.tmp
    # Stage C: a named preset save round-trips and stays host-scoped.
    save_target = tmp / "save-target.toml"
    save_target.write_text(profile_text)
    save_cfg = tomllib.loads(save_target.read_text())
    save_plan = launcher_module.build_plan(save_cfg, "codex", "balanced")
    save_plan["main_tier"] = "workhorse"
    save_plan["tiers"]["workhorse"]["model"] = "custom-wh"
    save_plan["tiers"]["workhorse"]["effort"] = "xhigh"
    save_plan["frontier_effort"] = "ultra"
    launcher_module.save_preset(save_plan, save_cfg, save_target, "mysetup")
    reloaded = launcher_module.load_config(save_target)
    if "mysetup" not in reloaded["presets"] or "balanced" not in reloaded["presets"]:
        mark_fail("save_preset did not persist the preset or clobbered existing ones")
    else:
        round_trip = launcher_module.build_plan(reloaded, "codex", "mysetup")
        if (
            round_trip["main_tier"] != "workhorse"
            or round_trip["tiers"]["workhorse"] != {"model": "custom-wh", "effort": "xhigh"}
            or launcher_module.tier_effort(round_trip, "frontier") != "ultra"
        ):
            mark_fail(f"saved preset did not round-trip: {round_trip['tiers']}")
        claude_view = launcher_module.build_plan(reloaded, "claude", "mysetup")
        if (
            claude_view["tiers"]["workhorse"]["model"]
            != save_cfg["hosts"]["claude"]["tiers"]["workhorse"]["model"]
        ):
            mark_fail("saved codex tier override leaked into the claude host")
        launcher_module.save_preset(round_trip, reloaded, save_target, "mysetup")
        saved_file = launcher_module.user_presets_path(save_target)
        if saved_file.read_text().count("[presets.mysetup]") != 1:
            mark_fail("re-saving a preset duplicated its block")
        if "[presets.mysetup]" in save_target.read_text():
            mark_fail("save_preset wrote a user preset into the installer-owned config")

    # Save As under a NEW name keeps the inactive hosts' bindings. Only the active host's
    # block is rebuilt and every other host is written back as authored — but "as authored"
    # was looked up under the DESTINATION name, so saving `balanced` as `balanced-copy`
    # found a preset that does not exist yet and wrote a copy carrying only the host it was
    # saved from (round 21, #5). The shipped presets author no cross-host overrides, which
    # is why `preset_save_round_trips` could not see this: the subject has to have
    # something to lose. Both directions, because a fix that hardcoded one host would pass
    # a single-direction test.
    # Through the REAL writer and reader, and asserted on the PROJECTION the other host
    # gets — not on the table this composed. A saved preset that still parses but launches
    # a different seat is the failure worth catching, and only building from the reloaded
    # profile can see it.
    for active, inactive in (("codex", "claude"), ("claude", "codex")):
        crosshost_dir = tmp / f"crosshost-{active}"
        crosshost_dir.mkdir(exist_ok=True)
        crosshost_target = crosshost_dir / "agent-launch.toml"
        crosshost_target.write_text(profile_text)
        crosshost_cfg = launcher_module.load_config(crosshost_target)
        crosshost_cfg["presets"]["balanced"]["tier_overrides"] = {
            active: {"workhorse": {"effort": "low"}},
            inactive: {"workhorse": {"effort": "medium"}},
        }
        # What the source preset projects on the host that is NOT being saved from.
        wanted = launcher_module.project_args(
            launcher_module.build_plan(crosshost_cfg, inactive, "balanced"),
            materialize_agents=False,
        )
        source_plan = launcher_module.build_plan(crosshost_cfg, active, "balanced")
        for destination in (f"saveas-{active}", "balanced"):
            launcher_module.save_preset(
                source_plan, crosshost_cfg, crosshost_target, destination
            )
            reloaded = launcher_module.load_config(crosshost_target)
            got = launcher_module.project_args(
                launcher_module.build_plan(reloaded, inactive, destination),
                materialize_agents=False,
            )
            if got != wanted:
                mark_fail(
                    f"preset save: saving {active}'s plan as {destination!r} changed what the "
                    f"preset projects on {inactive} — the source preset's bindings for the "
                    f"inactive host did not survive the save"
                )
            # The positive control: the ACTIVE host's own block is still REBUILT from the
            # plan, or a save that simply copied the source preset whole would satisfy the
            # assertion above while doing none of the work the save exists for.
            saved_active = (
                reloaded["presets"][destination].get("tier_overrides", {})
                .get(active, {}).get("workhorse", {})
            )
            if saved_active.get("effort") != "low":
                mark_fail(
                    f"preset save: {destination!r} came back without the active host's own "
                    f"rebuilt override ({saved_active!r})"
                )

    # A NON-TABLE inactive override node is TOML the launcher accepts —
    # `tier_overrides.claude` or `…claude.workhorse` authored as a value in its parent
    # table — so the save writes it back VERBATIM rather than refusing it: the refusal
    # this loop used to assert made an accepted profile unsaveable, the over-refusal S4's
    # complement forbids (spec round 7, #3). Round 22 #9's two halves — a silent drop and
    # a raw escape — stay closed, by round-trip now instead of by refusal. Both depths,
    # plus the authored-empty host table, which used to vanish without a word.
    for label, overrides, probe, want in (
        ("scalar host block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": "not-a-table"},
         lambda p: p.get("tier_overrides", {}).get("claude"), "not-a-table"),
        ("array tier block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": {"workhorse": [1, 2]}},
         lambda p: p.get("tier_overrides", {}).get("claude", {}).get("workhorse"), [1, 2]),
        ("empty host block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": {}},
         lambda p: p.get("tier_overrides", {}).get("claude"), {}),
    ):
        writable_cfg = launcher_module.load_config(save_target)
        writable_cfg["presets"]["solo"]["tier_overrides"] = copy.deepcopy(overrides)
        try:
            writable_plan = launcher_module.build_plan(writable_cfg, "codex", "solo")
            fields, scoped, review = launcher_module.preset_from_plan(
                writable_plan, writable_cfg, "writable-save"
            )
            writable_text = launcher_module.render_preset_block(
                "writable-save", fields, scoped, review
            )
        except Exception as exc:  # noqa: BLE001 — refusing a writable value is the finding
            mark_fail(
                f"preset save refused a {label} in an inactive host's overrides "
                f"({type(exc).__name__}: {exc}) — TOML spells it as a value in its parent "
                f"table, and a profile the launcher accepts must remain saveable"
            )
            continue
        writable_saved = tomllib.loads(writable_text)["presets"]["writable-save"]
        carried = probe(writable_saved)
        if carried != want:
            mark_fail(
                f"preset save wrote a {label} in an inactive host's overrides back as "
                f"{carried!r}, not the {want!r} that was authored"
            )
        # The active host's block is still rebuilt and validated, or a save that copied
        # the source whole would satisfy the verbatim assertion above.
        active = (
            writable_saved.get("tier_overrides", {}).get("codex", {}).get("workhorse", {})
        )
        if active.get("effort") != "low":
            mark_fail(
                f"preset save: the {label} case lost the active host's own rebuilt "
                f"override ({active!r})"
            )
    # …and the complement at the SAME depths: a value with no TOML spelling at all is
    # still refused naming the entry, exactly as the deeper `future.deep` case below is.
    for label, overrides, needle in (
        ("host block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": object()},
         "tier_overrides.claude holds object"),
        ("tier block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": {"workhorse": object()}},
         "tier_overrides.claude.workhorse holds object"),
    ):
        unwritable_node_cfg = launcher_module.load_config(save_target)
        unwritable_node_cfg["presets"]["solo"]["tier_overrides"] = overrides
        try:
            unwritable_node_plan = launcher_module.build_plan(
                unwritable_node_cfg, "codex", "solo"
            )
            fields, scoped, review = launcher_module.preset_from_plan(
                unwritable_node_plan, unwritable_node_cfg, "unwritable-node"
            )
            launcher_module.render_preset_block("unwritable-node", fields, scoped, review)
        except launcher_module.LaunchError as exc:
            if needle not in str(exc):
                mark_fail(
                    f"preset save refused an unwritable {label} without naming the entry: {exc}"
                )
        except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
            mark_fail(
                f"preset save let an unwritable {label} escape as {type(exc).__name__}: {exc}"
            )
        else:
            mark_fail(
                f"preset save accepted an unwritable {label} — it has no TOML spelling, so "
                f"writing means dropping it, and a drop needs a named refusal"
            )

    # A NESTED value in an inactive override. The tier loop was flat — one level of keys
    # under `[…tier_overrides.<host>.<tier>]` — so a sub-table reached `_toml_scalar`,
    # which gives a bare table no spelling: a profile the launcher accepts died at Save
    # with `cannot serialize preset value: {'nested': 1}`, naming neither the host, the
    # tier, nor the key (spec round 3, #6). Both halves, because S4 is two rules: what CAN
    # be written round-trips, and what genuinely cannot is refused NAMING the entry.
    nested_cfg = launcher_module.load_config(save_target)
    nested_cfg["presets"]["solo"]["tier_overrides"] = {
        "codex": {"workhorse": {"effort": "low"}},
        "claude": {"workhorse": {"future": {"nested": 1}}},
    }
    try:
        nested_plan = launcher_module.build_plan(nested_cfg, "codex", "solo")
        fields, scoped, review = launcher_module.preset_from_plan(
            nested_plan, nested_cfg, "nested-save"
        )
        nested_text = launcher_module.render_preset_block(
            "nested-save", fields, scoped, review
        )
    except Exception as exc:  # noqa: BLE001 — refusing a saveable value is the finding
        mark_fail(
            f"preset save refused a nested inactive tier override TOML spells perfectly "
            f"well ({type(exc).__name__}: {exc}) — verbatim carry has no depth limit, and "
            f"a profile the launcher accepts must remain saveable"
        )
    else:
        reloaded_nested = tomllib.loads(nested_text)["presets"]["nested-save"]
        carried = (
            reloaded_nested.get("tier_overrides", {}).get("claude", {})
            .get("workhorse", {}).get("future")
        )
        if carried != {"nested": 1}:
            mark_fail(
                f"preset save wrote a nested inactive tier override back as {carried!r}, "
                f"not the table that was authored"
            )
    # …and the complement, on the same entry: a value with no TOML spelling at all is
    # refused by the PATH it sits at. `_toml_scalar`'s own message quotes the repr and
    # names nothing, which is what sent the reader looking through the whole profile.
    unwritable_cfg = launcher_module.load_config(save_target)
    unwritable_cfg["presets"]["solo"]["tier_overrides"] = {
        "codex": {"workhorse": {"effort": "low"}},
        "claude": {"workhorse": {"future": {"deep": object()}}},
    }
    try:
        unwritable_plan = launcher_module.build_plan(unwritable_cfg, "codex", "solo")
        fields, scoped, review = launcher_module.preset_from_plan(
            unwritable_plan, unwritable_cfg, "unwritable-save"
        )
        launcher_module.render_preset_block("unwritable-save", fields, scoped, review)
    except launcher_module.LaunchError as exc:
        if "tier_overrides.claude.workhorse.future.deep" not in str(exc):
            mark_fail(
                f"preset save refused an unwritable nested inactive override without "
                f"naming the entry: {exc}"
            )
    except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
        mark_fail(
            f"preset save let an unwritable nested inactive override escape as "
            f"{type(exc).__name__}: {exc}"
        )
    else:
        mark_fail(
            "preset save accepted a value with no TOML spelling inside an inactive tier "
            "override — it is written back as authored or the save says which entry, never "
            "dropped in silence"
        )

    # FRONTIER's two effort homes, CONTRADICTING each other on the host that is not
    # launching. `build_plan` compared the pair only for the host it was building, so a
    # profile Claude refuses by name built cleanly from Codex — and the save then wrote a
    # preset carrying whichever value survived normalization, resolving the contradiction
    # instead of naming it (spec round 2, #4). Two doors, and each has a case only it can
    # catch: the profile is refused where it is READ, from the host the contradiction is
    # not on, and a plan assembled some other way is refused where it is WRITTEN.
    #
    # The authored top-level value is that host's OWN DEFAULT on purpose. The normalizer
    # elides an authoring equal to the default — there is no line to write — and the
    # elision used to run BEFORE the two homes were compared, so exactly these
    # contradictions passed through it unread.
    conflict_cfg = launcher_module.load_config(save_target)
    claude_default = conflict_cfg["hosts"]["claude"]["tiers"]["frontier"]["effort"]
    conflict_other = next(
        effort for effort in launcher_module.HOST_EFFORTS["claude"] if effort != claude_default
    )
    conflict_cfg["presets"]["solo"]["frontier_effort"] = claude_default
    conflict_cfg["presets"]["solo"]["tier_overrides"] = {
        "claude": {"frontier": {"effort": conflict_other}},
    }
    try:
        launcher_module.build_plan(conflict_cfg, "codex", "solo")
    except launcher_module.LaunchError as exc:
        if "FRONTIER's effort has one value" not in str(exc):
            mark_fail(
                f"preset save: a profile whose INACTIVE host authors two disagreeing FRONTIER "
                f"efforts was refused for another reason: {exc}"
            )
        elif "claude" not in str(exc):
            mark_fail(
                f"preset save: the inactive-host FRONTIER contradiction was refused without "
                f"naming the host it is on: {exc}"
            )
    else:
        mark_fail(
            "preset save: a profile authoring frontier_effort and "
            "tier_overrides.claude.frontier.effort to different values built cleanly from "
            "codex — the host the contradiction is on refuses it by name, so one profile "
            "has two answers and the save normalizes one of them away"
        )
    # …and the SAVE's own door, on a plan the profile reader never saw. Reverting either
    # door alone leaves the other's cases passing, so neither is proved by the other.
    conflict_plan = launcher_module.build_plan(
        launcher_module.load_config(save_target), "codex", "solo"
    )
    conflict_plan["frontier_effort_authored"] = claude_default
    conflict_plan["tier_overrides"] = {"claude": {"frontier": {"effort": conflict_other}}}
    try:
        launcher_module.preset_from_plan(
            conflict_plan, launcher_module.load_config(save_target), "frontier-conflict"
        )
    except launcher_module.LaunchError as exc:
        if "FRONTIER's effort has one value" not in str(exc):
            mark_fail(
                f"preset save: a plan whose inactive host holds two disagreeing FRONTIER "
                f"efforts was refused for another reason: {exc}"
            )
    except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
        mark_fail(
            f"preset save: an inactive-host FRONTIER contradiction escaped as "
            f"{type(exc).__name__}: {exc}"
        )
    else:
        mark_fail(
            "preset save: a plan authoring claude's frontier effort in both homes, to "
            "different values, was written — the authored value equals that host's default "
            "so nothing is emitted for it, and the override alone became the saved answer"
        )
    # The positive control both doors need: the SAME two homes AGREEING still builds and
    # still saves, so neither case above is satisfied by refusing every profile that
    # authors both.
    agree_cfg = launcher_module.load_config(save_target)
    agree_cfg["presets"]["solo"]["frontier_effort"] = claude_default
    agree_cfg["presets"]["solo"]["tier_overrides"] = {
        "claude": {"frontier": {"effort": claude_default}},
    }
    try:
        agree_plan = launcher_module.build_plan(agree_cfg, "codex", "solo")
        launcher_module.preset_from_plan(agree_plan, agree_cfg, "frontier-agree")
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"preset save: two AGREEING FRONTIER effort homes on an inactive host were "
            f"refused ({exc}) — the contradiction cases above then prove nothing"
        )

    # The same class one key over, in the RAW `frontier_effort` host map. The map is a
    # second authored home for FRONTIER's effort and its inactive entries are carried
    # through the plan into the save, which read them with `isinstance(str)` and skipped
    # anything else — so `codex = false` was dropped at Save As and that host reloaded at
    # its default: a value the user authored, replaced by one they did not, in silence
    # (round 23, #4). Two doors, and a case that only each can catch: the profile is
    # refused where it is READ, and a plan assembled some other way is refused where it is
    # written. The positive control below is what a refuse-everything implementation fails.
    for label, bad in (("a boolean", False), ("a non-effort string", "warp-speed"),
                       ("an empty string", ""), ("a nested table", {"effort": "max"})):
        effort_cfg = launcher_module.load_config(save_target)
        effort_cfg["presets"]["solo"]["frontier_effort"] = {"codex": "max", "claude": bad}
        try:
            launcher_module.build_plan(effort_cfg, "codex", "solo")
        except launcher_module.LaunchError as exc:
            if "solo.frontier[claude]" not in str(exc):
                mark_fail(
                    f"preset save: a profile whose inactive frontier_effort entry holds "
                    f"{label} was refused without naming the entry: {exc}"
                )
        except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
            mark_fail(
                f"preset save: an inactive frontier_effort entry holding {label} escaped as "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            mark_fail(
                f"preset save: a profile whose inactive frontier_effort entry holds {label} "
                f"built a plan — the value is carried into the save, where it is dropped and "
                f"the host reloads at its default"
            )
    # …and the save's own door, on a plan the profile reader never saw. Reverting either door
    # alone leaves the other's cases passing, so neither is proved by the other. Scoped to
    # what the save can decide: a value with no writable form. Whether a STRING names a real
    # effort is the profile reader's question — it has the host's model and the effort table
    # — and asking it in two places would give one rule two owners, so a string the reader
    # would refuse is written back rather than dropped, and refused where it is read.
    for label, bad in (("a boolean", False), ("an empty string", ""),
                       ("a nested table", {"effort": "max"})):
        save_plan = launcher_module.build_plan(
            launcher_module.load_config(save_target), "codex", "solo"
        )
        save_plan["frontier_effort_authored"] = {"codex": "max", "claude": bad}
        try:
            launcher_module.preset_from_plan(
                save_plan, launcher_module.load_config(save_target), "effort-save"
            )
        except launcher_module.LaunchError as exc:
            if "frontier_effort for claude holds" not in str(exc):
                mark_fail(
                    f"preset save refused a plan whose inactive frontier_effort holds {label} "
                    f"without naming the host and the value: {exc}"
                )
        except Exception as exc:  # noqa: BLE001
            mark_fail(
                f"preset save let an inactive frontier_effort holding {label} escape as "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            mark_fail(
                f"preset save accepted a plan whose inactive frontier_effort holds {label} — "
                f"the entry is written back or the save says why, never dropped in silence"
            )
    # The other half of that line, asserted rather than assumed: a STRING the reader would
    # refuse is carried into the saved preset, not replaced by the host default. Dropping it
    # is the defect; refusing it here would move the effort table's ownership.
    carried_plan = launcher_module.build_plan(
        launcher_module.load_config(save_target), "codex", "solo"
    )
    carried_plan["frontier_effort_authored"] = {"codex": "max", "claude": "warp-speed"}
    _, carried_scoped, _ = launcher_module.preset_from_plan(
        carried_plan, launcher_module.load_config(save_target), "effort-carried"
    )
    carried_value = carried_scoped.get("claude", {}).get("frontier", {}).get("effort")
    if carried_value != "warp-speed":
        mark_fail(
            f"preset save wrote the inactive host's frontier effort as {carried_value!r} "
            f"instead of the authored 'warp-speed' — an authored value the save cannot "
            f"judge is carried, never swapped for a default"
        )
    # The positive control both doors need: a VALID inactive entry differing from that
    # host's default still builds, still saves, and still arrives in the reloaded preset.
    valid_cfg = launcher_module.load_config(save_target)
    claude_default = valid_cfg["hosts"]["claude"]["tiers"]["frontier"]["effort"]
    claude_other = next(
        e for e in launcher_module.EFFORT_ORDER
        if e != claude_default and e in launcher_module.HOST_EFFORTS["claude"]
    )
    valid_cfg["presets"]["solo"]["frontier_effort"] = {"codex": "max", "claude": claude_other}
    valid_target = tmp / "frontier-effort-valid.toml"
    valid_target.write_text(save_target.read_text())
    try:
        launcher_module.save_preset(
            launcher_module.build_plan(valid_cfg, "codex", "solo"),
            valid_cfg, valid_target, "effort-valid",
        )
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"preset save refused a VALID inactive frontier_effort entry: {exc} — the "
            f"malformed cases above then prove nothing"
        )
    else:
        back = launcher_module.load_config(valid_target)["presets"]["effort-valid"]
        got = back.get("tier_overrides", {}).get("claude", {}).get("frontier", {}).get("effort")
        if got != claude_other:
            mark_fail(
                f"preset save: a valid inactive frontier_effort entry came back as {got!r}, "
                f"not {claude_other!r} — the door refuses malformed values and loses good ones"
            )

    # An inactive host's frontier effort, validated against the model that host will
    # ACTUALLY bind. The selected host applies `tier_overrides.<host>.frontier.model`
    # before validating its effort and the inactive branch used the host's BASE model, so
    # one profile got two answers and which one you saw depended on where you launched
    # from (round 24, #6). Asserted as AGREEMENT between the two hosts rather than as a
    # fixed verdict per profile: the property is that the answer does not depend on the
    # seat, and a fixed expectation would have to be re-derived every time the effort
    # table moves. `gpt-5.6-luna/ultra` is the one model-dependent effort rule this
    # launcher has, so it is the only shape that can express the case at all.
    agreement_seen = {"accepted": 0, "refused": 0}
    for label, mutate in (
        # The override makes the effort INVALID. The inactive branch was reading the base
        # model, which accepts it, so this profile launched from claude and died from
        # codex — a preset that saves clean and cannot be launched by the host it is for.
        ("an inactive override to the restricted model",
         lambda c: (
             c["presets"]["solo"].update(frontier_effort={"codex": "ultra", "claude": "max"}),
             c["presets"]["solo"].update(
                 tier_overrides={"codex": {"frontier": {"model": "gpt-5.6-luna"}}}),
         )),
        # …and the mirror, where the override makes the effort VALID: the base model bars
        # it and the override lifts the bar. Refusing this is the same defect with the
        # sign flipped, and a fix that simply refused more would pass the case above.
        ("an inactive override away from the restricted model",
         lambda c: (
             c["hosts"]["codex"]["tiers"]["frontier"].update(model="gpt-5.6-luna"),
             c["presets"]["solo"].update(frontier_effort={"codex": "ultra", "claude": "max"}),
             c["presets"]["solo"].update(
                 tier_overrides={"codex": {"frontier": {"model": "gpt-5.6-sol"}}}),
         )),
        # The control: no override at all, so both branches read the same model anyway.
        ("no override at all",
         lambda c: c["presets"]["solo"].update(
             frontier_effort={"codex": "ultra", "claude": "max"})),
    ):
        verdicts = {}
        for seat in ("claude", "codex"):
            seat_cfg = launcher_module.load_config(save_target)
            mutate(seat_cfg)
            try:
                launcher_module.build_plan(seat_cfg, seat, "solo")
            except launcher_module.LaunchError as exc:
                verdicts[seat] = f"refused: {exc}"
            else:
                verdicts[seat] = "accepted"
        outcomes = {seat: value.split(":", 1)[0] for seat, value in verdicts.items()}
        if len(set(outcomes.values())) != 1:
            mark_fail(
                f"preset save: with {label}, solo is {outcomes['claude']} from claude and "
                f"{outcomes['codex']} from codex — one profile, two answers, and the "
                f"inactive host's effort is being validated against a model it will not "
                f"bind: {verdicts}"
            )
        agreement_seen[next(iter(outcomes.values()))] += 1
    if not agreement_seen["accepted"] or not agreement_seen["refused"]:
        mark_fail(
            f"preset save: the inactive frontier-model cases produced {agreement_seen} — "
            f"agreement is satisfied by an implementation that answers the same way to "
            f"everything, so both outcomes have to occur"
        )

    # A non-table where FRONTIER's normalized home would go, beside a NON-DEFAULT authored
    # `frontier_effort` for the same host. The save carries a non-table override node
    # verbatim now (spec round 7, #3), so the normalizer can neither write the effort into
    # the occupied home — `setdefault("frontier", {})` on a string was round 24 #8's raw
    # TypeError — nor skip past it, which would drop the authored effort in silence: two
    # authored values, one home, and the save refuses naming both. Each occupied spelling,
    # because the door names the host block and its frontier entry from different branches.
    frontier_shape_cfg = launcher_module.load_config(save_target)
    # The inactive effort must DIFFER from that host's default, or nothing is owed a line
    # and the home is not contested. Derived, not typed: written as a literal it goes
    # quiet the day the shipped default moves to that value.
    shape_default = frontier_shape_cfg["hosts"]["claude"]["tiers"]["frontier"]["effort"]
    shape_effort = next(
        e for e in launcher_module.EFFORT_ORDER
        if e != shape_default and e in launcher_module.HOST_EFFORTS["claude"]
    )
    for occupied_label, occupied_overrides, occupied_needle in (
        ("frontier entry",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": {"frontier": "not-a-table"}},
         "tier_overrides.claude.frontier holds a non-table value"),
        ("host block",
         {"codex": {"workhorse": {"effort": "low"}}, "claude": "not-a-table"},
         "tier_overrides.claude holds a non-table value"),
    ):
        occupied_cfg = launcher_module.load_config(save_target)
        occupied_cfg["presets"]["solo"]["frontier_effort"] = {
            "codex": "max", "claude": shape_effort,
        }
        occupied_cfg["presets"]["solo"]["tier_overrides"] = copy.deepcopy(occupied_overrides)
        try:
            occupied_plan = launcher_module.build_plan(occupied_cfg, "codex", "solo")
            fields, scoped, review = launcher_module.preset_from_plan(
                occupied_plan, occupied_cfg, "frontier-shape"
            )
            launcher_module.render_preset_block("frontier-shape", fields, scoped, review)
        except launcher_module.LaunchError as exc:
            if occupied_needle not in str(exc) or "cannot write both" not in str(exc):
                mark_fail(
                    f"preset save refused an occupied FRONTIER home ({occupied_label}) "
                    f"without naming both values: {exc}"
                )
        except Exception as exc:  # noqa: BLE001 — the raw escape is the finding
            mark_fail(
                f"preset save let an occupied FRONTIER home ({occupied_label}) escape as "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            mark_fail(
                f"preset save wrote a preset whose {occupied_label} holds a non-table value "
                f"while claude also authors a non-default frontier_effort — one of the two "
                f"was dropped in silence, and the save owes a refusal naming both"
            )
    # …and the door's two edges, which must stay OPEN: with the authored effort EQUAL to
    # that host's default nothing is owed a line, and with no authored frontier_effort at
    # all nothing contests the home — both save, carrying the non-table value verbatim.
    for edge_label, edge_frontier in (
        ("default-valued frontier_effort", {"codex": "max", "claude": shape_default}),
        ("no authored frontier_effort", None),
    ):
        edge_cfg = launcher_module.load_config(save_target)
        if edge_frontier is not None:
            edge_cfg["presets"]["solo"]["frontier_effort"] = edge_frontier
        else:
            edge_cfg["presets"]["solo"].pop("frontier_effort", None)
        edge_cfg["presets"]["solo"]["tier_overrides"] = {
            "codex": {"workhorse": {"effort": "low"}},
            "claude": {"frontier": "not-a-table"},
        }
        try:
            edge_plan = launcher_module.build_plan(edge_cfg, "codex", "solo")
            fields, scoped, review = launcher_module.preset_from_plan(
                edge_plan, edge_cfg, "frontier-edge"
            )
            edge_text = launcher_module.render_preset_block(
                "frontier-edge", fields, scoped, review
            )
        except Exception as exc:  # noqa: BLE001 — refusing a writable profile is the finding
            mark_fail(
                f"preset save refused the {edge_label} edge ({type(exc).__name__}: {exc}) — "
                f"the home is not contested there, so the profile stays saveable"
            )
            continue
        edge_carried = (
            tomllib.loads(edge_text)["presets"]["frontier-edge"]
            .get("tier_overrides", {}).get("claude", {}).get("frontier")
        )
        if edge_carried != "not-a-table":
            mark_fail(
                f"preset save: the {edge_label} edge wrote claude's frontier node back as "
                f"{edge_carried!r}, not the authored value"
            )

    # A `frontier_effort` key naming no LAUNCHABLE host. `build_plan` deliberately leaves
    # such a key alone, so the profile launches; the save's normalization walks the
    # launchable hosts, never visited the key, and wrote a preset the entry had vanished
    # from with nothing said (round 24, #9). Refused by name, because the normalized schema
    # genuinely cannot hold it: `tier_overrides` host keys are closed to the launchable set,
    # and a partial `frontier_effort` map makes the preset unloadable on the host it omits.
    future_cfg = launcher_module.load_config(save_target)
    future_cfg["presets"]["solo"]["frontier_effort"] = {
        "codex": "max", "claude": "max", "gate-future-host": "high",
    }
    try:
        future_plan = launcher_module.build_plan(future_cfg, "codex", "solo")
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"preset save: a frontier_effort key naming an unlaunchable host stopped the "
            f"LAUNCH ({exc}) — the save-side case below then tests nothing, and the profile "
            f"reader's tolerance of such a key is a decided boundary"
        )
    else:
        try:
            launcher_module.preset_from_plan(future_plan, future_cfg, "future-host")
        except launcher_module.LaunchError as exc:
            if "gate-future-host" not in str(exc) or "not a launchable host" not in str(exc):
                mark_fail(
                    f"preset save refused an unlaunchable frontier_effort key without naming "
                    f"it: {exc}"
                )
        except Exception as exc:  # noqa: BLE001
            mark_fail(
                f"preset save let an unlaunchable frontier_effort key escape as "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            mark_fail(
                "preset save accepted a frontier_effort key naming an unlaunchable host — it "
                "cannot be written to either home, so accepting means dropping a value the "
                "user authored in silence"
            )
    # The positive control that refusal needs: the SAME map without the unlaunchable key
    # still saves, and the launchable entries still arrive in the reloaded preset.
    future_control_cfg = launcher_module.load_config(save_target)
    future_control_cfg["presets"]["solo"]["frontier_effort"] = {"codex": "max", "claude": "max"}
    future_control_target = tmp / "future-host-control.toml"
    future_control_target.write_text(save_target.read_text())
    try:
        launcher_module.save_preset(
            launcher_module.build_plan(future_control_cfg, "codex", "solo"),
            future_control_cfg, future_control_target, "future-control",
        )
    except launcher_module.LaunchError as exc:
        mark_fail(
            f"preset save refused a frontier_effort map naming only launchable hosts: {exc} "
            f"— the unlaunchable-key case above then proves nothing"
        )

    # The Custom hub 'save' action persists the named preset then launches.
    ui_save_target = tmp / "ui-save.toml"
    ui_save_target.write_text(profile_text)
    if argv_log.exists():
        argv_log.unlink()
    ui_save = invoke([
        sys.executable, str(launcher), "--config", str(ui_save_target),
        "--preset", "balanced", "--custom", "codex",
    ], input_text="9\ndaily-driver\n", env=env)
    if ui_save.returncode != 0 or not argv_log.exists():
        mark_fail(f"agent-launch custom save-and-start did not launch: {ui_save.stderr.strip()}")
    elif "daily-driver" not in launcher_module.load_config(ui_save_target)["presets"]:
        mark_fail("agent-launch custom hub save did not persist the named preset")


@launcher_check
def shell_wrapper(fx):
    env, tmp = fx.env, fx.tmp
    shell_bin = tmp / "shell-bin"
    shell_bin.mkdir()
    dispatch_log = tmp / "dispatch.argv"
    shell_backend = shell_bin / "backend"
    shell_backend.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$(basename \"$0\")\" \"$@\" > \"$FAKE_DISPATCH_ARGV\"\n"
    )
    shell_backend.chmod(0o755)
    (shell_bin / "codex").symlink_to(shell_backend)
    (shell_bin / "claude").symlink_to(shell_backend)
    shell_env = env.copy()
    shell_env.update(
        PATH=f"{shell_bin}{os.pathsep}{shell_env.get('PATH', '')}",
        FAKE_DISPATCH_ARGV=str(dispatch_log),
    )
    for command, expected in (
        ("codex exec probe", ["codex", "exec", "probe"]),
        ("claude --no-tui -p probe", ["claude", "--dangerously-skip-permissions", "-p", "probe"]),
        ("codex", ["codex"]),
    ):
        shell_result = invoke([
            "zsh", "-f", "-c", f"source {shell_init}; {command}"
        ], env=shell_env)
        received = dispatch_log.read_text().splitlines() if dispatch_log.is_file() else []
        if shell_result.returncode != 0 or received != expected:
            mark_fail(f"shell dispatch for {command!r} is {received!r}, want {expected!r}")
    alias_result = invoke([
        "zsh", "-f", "-c",
        f"alias codex='false'; alias claude='false'; source {shell_init}; codex exec alias-probe",
    ], env=shell_env)
    received = dispatch_log.read_text().splitlines() if dispatch_log.is_file() else []
    if alias_result.returncode != 0 or received != [
        "codex", "exec", "alias-probe"
    ]:
        mark_fail("shell init did not replace pre-existing codex/claude aliases")


def main(argv):
    from fixture_support import legacy_host_environment
    with legacy_host_environment(pathlib.Path(__file__).resolve().parents[1]):
        return run_checks(argv)


def run_checks(argv):
    ap = argparse.ArgumentParser(description="Runtime-projection parity checks.")
    ap.add_argument("--only", action="append", metavar="NAME",
                    help="run only these checks (repeatable); a subset is a debugging aid, not a gate")
    ap.add_argument("--list", action="store_true", help="print the check names and exit")
    args = ap.parse_args(argv)

    if args.list:
        for name, (_, needs_fixture) in CHECKS.items():
            print(f"{name}{'  (launcher fixture)' if needs_fixture else ''}")
        return 0

    selected = list(CHECKS)
    if args.only:
        unknown = [n for n in args.only if n not in CHECKS]
        if unknown:
            print(f"FAIL: unknown check name(s): {', '.join(unknown)}")
            return 2
        selected = [n for n in CHECKS if n in args.only]
        print(f"NOTE: partial run ({len(selected)}/{len(CHECKS)} checks) — the launcher fixture "
              "is order-dependent, so this does not stand in for a full gate run")

    for name in selected:
        fn, needs_fixture = CHECKS[name]
        if not needs_fixture:
            fn()

    if launcher.is_file() and launch_profile and any(CHECKS[n][1] for n in selected):
        launcher_module = import_launcher()
        with launcher_fixture(launcher_module) as fx:
            for name in selected:
                fn, needs_fixture = CHECKS[name]
                if needs_fixture:
                    if name == "launcher_module_api" and launcher_module is None:
                        continue
                    fn(fx)

    if fail == 0:
        print("LAUNCH/BINDINGS OK: profile projections, bypass paths, role slots, and wrappers aligned")
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
