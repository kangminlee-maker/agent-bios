#!/usr/bin/env python3
"""Stage 1 of the pluggable-review-methods plan: characterise today's review routing.

Captures, for every cell of the review matrix, what the launcher actually does. Two
observation routes, because either alone can agree with a wrong answer:

  projection route  normalised dry-run argv + the injected contract
  module route      effective_review() -> (effective, dropped, floor), or the failure

The output is a golden the later stages are checked against byte-for-byte, so the
normalisation applied here is part of the control, not an implementation detail.
Every rule is listed in gates/goldens/NORMALISATION.md.

Run:  python3 gates/capture-review-goldens.py [--check]
      --check re-captures and diffs against the stored golden instead of writing.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import itertools
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "launch" / "agent-launch.py"
PROFILE = REPO / "launch" / "agent-launch.toml"
GOLDEN_DIR = REPO / "gates" / "goldens"
GOLDEN = GOLDEN_DIR / "review-matrix.json"

# The matrix axes. Order is fixed: it determines cell ids, which are the golden's keys.
SETUPS = ("none", "native-panel", "slash-review", "ultracode")
HOSTS = ("codex", "claude")
FAMILIES = ("cross", "same")
# Both shipped review capabilities are `${backend}`, so a reviewer is absent exactly
# when a host CLI is. The absence this axis can express without making the MAIN
# unlaunchable — which would break the two-route agreement control — is the OPPOSITE
# host's CLI: from a claude main that CLI is both the cross-family dispatcher and the
# deep-exec reviewer, and from a codex main it is the cross-family claude seat. A main
# missing its OWN CLI is a different assertion, pinned by the composable
# `backend-absent`/`codex-exec-absent` scenarios.
OPPOSITE_CLIS = ("present", "absent")
DELEGATIONS = ("on", "off")
AXES = ("setup", "host", "family", "opposite_cli", "delegation")

PRESET = "golden"
COMPOSABLE_PRESET = "golden-composable"

# Composable cells are ENUMERATED, not a product: the failure branches are not axes,
# and a cartesian product over them would mostly be unreachable combinations. Each
# scenario names one path through the schema. `outcome` is asserted by a control, so a
# branch that silently stops failing is caught rather than re-baselined.
#
# Grade scenarios pin host=claude, whose main seat here is helm = claude-opus-5/xhigh;
# stating the grade only makes sense against a known main.
COMPOSABLE_SCENARIOS = (
    # -- shapes, both hosts -------------------------------------------------
    {"id": "base-only", "outcome": "ok", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "base-plus-codex-exec", "outcome": "ok", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"
"""},
    {"id": "base-plus-ultracode", "outcome": "ok", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."ultracode"]
provider = "anthropic"
tier = "frontier"
"""},
    {"id": "base-plus-both", "outcome": "ok", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."ultracode"]
provider = "anthropic"
tier = "frontier"
"""},
    # A `${backend}` reviewer is absent exactly when its host CLI is. claude main only:
    # with no codex CLI a CODEX main cannot launch at all, which is correct and a
    # different assertion. The base sits on the anthropic seat so only the reviewer —
    # not the panel it degrades to — depends on the CLI this scenario removes.
    {"id": "codex-exec-absent", "outcome": "ok", "hosts": ("claude",),
     "absent_backend": "codex", "review": """
[presets.PRESET.review.base]
provider = "anthropic"
tier = "frontier"

[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"
"""},
    # The claude-hosted workflow reviewer is absent only when the claude CLI is missing.
    # Nothing else in this matrix can drop it, which is why it had zero DROPPED rows.
    # codex main only: with no claude CLI a CLAUDE main cannot launch at all, which is
    # correct and a different assertion. Here the question is what a codex main projects
    # when the reviewer it routes to cannot run.
    {"id": "backend-absent", "outcome": "ok", "hosts": ("codex",),
     "absent_backend": "claude", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."ultracode"]
provider = "anthropic"
tier = "frontier"
"""},
    {"id": "unregistered-method", "outcome": "ok", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."no-such-lens"]
provider = "openai"
tier = "frontier"
"""},
    {"id": "delegation-off", "outcome": "ok", "delegation": False, "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"
"""},
    # -- criterion discipline: additive cells only. The toggle off is every OTHER cell
    # in this file, so the byte-identity of the untoggled render is pinned by all of
    # them at once; these pin the toggled render — the clause exactly once per live
    # row, appended by core, method-blind.
    {"id": "criterion-base-only", "outcome": "ok", "fields": {"criterion": True},
     "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "criterion-base-plus-both", "outcome": "ok", "fields": {"criterion": True},
     "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."ultracode"]
provider = "anthropic"
tier = "frontier"
"""},
    # The toggle is a boolean and nothing else: the criterion's CONTENT rides the
    # packet, and a preset smuggling it as a string is refused at plan build.
    {"id": "err-criterion-non-boolean", "outcome": "error", "hosts": ("claude",),
     "fields": {"criterion": "yes"}, "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    # A method the repository has never seen, registered by the user. This is the
    # registry's only end-to-end proof: merged at launch, projected, never deployed.
    {"id": "local-registry", "outcome": "ok", "registry": """
[capabilities.local-kit]
command = "CAPABILITY_CMD"
offers = [{ operation = "vendor-review", adapter = "mcp-stdio-v1", hosts = ["codex", "claude"] }]

[review_methods.local-lens]
label = "Locally registered"
description = "Registered by the user, never shipped."
capability = "local-kit"
operation = "vendor-review"
instructions = "run {command} on {model}/{effort}"
output = "review-v1"
perspectives = ["refutation"]
trials = 1
order = "fixed"
swap_augmentation = false
aggregation = "union"
severity_emits = ["blocker", "high", "medium", "low", "info"]
severity_map = { blocker = "blocker", high = "high", medium = "medium", low = "low", info = "info" }
""", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.methods."local-lens"]
provider = "openai"
tier = "frontier"
"""},
    # -- host-scoped arms: the only form that keeps cross-family on BOTH hosts --
    {"id": "arms-both-hosts", "outcome": "ok", "review": """
[presets.PRESET.review.hosts.claude.base]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.hosts.claude.methods."codex-exec"]
provider = "openai"
tier = "frontier"

[presets.PRESET.review.hosts.codex.base]
provider = "anthropic"
tier = "frontier"

[presets.PRESET.review.hosts.codex.methods."ultracode"]
provider = "anthropic"
tier = "frontier"
"""},
    {"id": "err-arms-missing-host", "outcome": "error", "hosts": ("codex",), "review": """
[presets.PRESET.review.hosts.claude.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-arms-with-flat", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review]
base = { provider = "openai", tier = "frontier" }

[presets.PRESET.review.hosts.claude.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-arms-unknown-host", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.hosts.mystery.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-arms-empty", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review]
hosts = {}
"""},
    # -- grades, claude only (main seat = helm = claude-opus-5/xhigh) --------
    {"id": "grade-same-seat", "outcome": "ok", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "anthropic"
model = "claude-opus-5"
effort = "xhigh"
"""},
    {"id": "grade-model-difference", "outcome": "ok", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "anthropic"
model = "claude-fable-5"
effort = "xhigh"
"""},
    {"id": "grade-higher-effort", "outcome": "ok", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "anthropic"
model = "claude-opus-5"
effort = "max"
"""},
    # Different is not better: a lower effort must earn no credit and land on the floor.
    {"id": "grade-lower-effort", "outcome": "ok", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "anthropic"
model = "claude-opus-5"
effort = "high"
"""},
    {"id": "advisory-service-tier", "outcome": "ok", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "anthropic"
model = "claude-opus-5"
effort = "xhigh"
service_tier = "fast"
"""},
    # -- failure branches, claude only (host-independent unless stated) ------
    {"id": "err-both-schemas", "outcome": "error", "hosts": ("claude",),
     "fields": {"review_setup": "ultracode"}, "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-no-base", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.methods."codex-exec"]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-family-in-block", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review]
review_family = "cross"

[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-unknown-block-key", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review]
panel = "yes"

[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-unknown-binding-key", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
seat = "extra"
"""},
    {"id": "err-no-provider", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
tier = "frontier"
"""},
    # NOT an error scenario any more: a base bound to a provider this profile has no host
    # for degrades to the main seat rather than refusing to launch (design §1). The
    # scenario is kept, renamed, and flipped to "ok" so the fixture records what a
    # single-provider user is actually handed — the case the whole fallback exists for.
    # `openai` rather than `grok`: the fallback is for a provider the launcher RECOGNISES
    # and this profile lacks. An unrecognised name is a typo and still fails, which is a
    # different assertion and lives in the parity gate. `strip_provider` on the OTHER host
    # is what makes openai absent — naming one host in `hosts` only chooses where the
    # scenario projects, so without the strip this bound normally and the harness's own
    # control caught it projecting identically to `base-only`.
    {"id": "base-provider-without-host", "outcome": "ok", "hosts": ("claude",),
     "strip_provider": "codex", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-tier-and-model", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
model = "gpt-5.6-sol"
"""},
    {"id": "err-neither-tier-nor-model", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
"""},
    {"id": "err-model-without-effort", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
model = "gpt-5.6-sol"
"""},
    {"id": "err-tier-with-effort", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
effort = "max"
"""},
    {"id": "err-unknown-tier", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "no-such-tier"
"""},
    {"id": "err-invalid-effort", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
model = "gpt-5.6-sol"
effort = "turbo"
"""},
    {"id": "err-empty-service-tier", "outcome": "error", "hosts": ("claude",), "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
service_tier = ""
"""},
    # The launch host itself declares no provider, so its main seat cannot be graded.
    {"id": "err-host-without-provider", "outcome": "error", "hosts": ("claude",),
     "strip_provider": "claude", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-registry-collision", "outcome": "error", "hosts": ("claude",), "registry": """
[review_methods.panel]
label = "hijack"
""", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-registry-unknown-section", "outcome": "error", "hosts": ("claude",), "registry": """
[presets.sneaky]
label = "not allowed here"
""", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
    {"id": "err-registry-unparseable", "outcome": "error", "hosts": ("claude",),
     "registry": "this is not = valid toml [[[\n", "review": """
[presets.PRESET.review.base]
provider = "openai"
tier = "frontier"
"""},
)


def cell_id(setup: str, host: str, family: str, opposite_cli: str, delegation: str) -> str:
    return f"{host}/{setup}/{family}/cli-{opposite_cli}/deleg-{delegation}"


def composable_cell_id(scenario_id: str, host: str) -> str:
    return f"composable/{scenario_id}/{host}"


def shipped_cell_id(preset: str, host: str) -> str:
    return f"shipped/{preset}/{host}"


# ── normalisation ───────────────────────────────────────────────────────────
# Machine-varying strings are replaced by stable tokens. Longest-first so that a
# path nested inside another (the venv under HOME) is not half-substituted.

def normaliser(tmp: pathlib.Path) -> list[tuple[str, str]]:
    home = str(pathlib.Path.home())
    venv = os.environ.get("AGENT_LAUNCH_VENV") or f"{home}/.local/share/agent-launch/venv"
    rules = [
        (str(tmp.resolve()), "<TMP>"),
        (str(tmp), "<TMP>"),
        (str(REPO), "<REPO>"),
        (venv, "<VENV>"),
        (home, "<HOME>"),
    ]
    # Longest literal first; ties broken by the literal itself for determinism.
    return sorted(set(rules), key=lambda rule: (-len(rule[0]), rule[0]))


def normalise(text: str, rules: list[tuple[str, str]]) -> str:
    for literal, token in rules:
        text = text.replace(literal, token)
    return text


# ── fixture ─────────────────────────────────────────────────────────────────

def toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported preset scalar: {value!r}")


def write_profile(
    tmp: pathlib.Path,
    backend: pathlib.Path,
    cell_host: str,
    opposite_cli: str,
    setup: str,
    family: str,
    delegation: str,
) -> pathlib.Path:
    """A profile whose backends are the fake, with the OPPOSITE host's CLI present or
    deliberately unresolvable, and which carries one synthetic preset per cell.

    Absence is produced by pointing the command at a name that cannot resolve —
    never by uninstalling anything (this machine has everything installed and
    is therefore not representative; see HANDOFF.md §2)."""
    text = PROFILE.read_text()
    for host in HOSTS:
        # One fake per host, never a shared one: aliasing them made "dispatched the
        # opposite family" and "dispatched my own family again" the same recorded argv,
        # so a cross-family regression stayed byte-identical across all 192 cells.
        target = str(backend) + "-" + host
        if host != cell_host and opposite_cli == "absent":
            target = str(tmp / f"nonexistent-{host}")
        text = text.replace(
            f'command = "{host}"', f"command = {json.dumps(target)}", 1
        )

    base = tomllib.loads(PROFILE.read_text())["presets"]["balanced"]
    fields = {
        "label": "Golden",
        "mode": base.get("mode", "builder"),
        "main_tier": base["main_tier"],
        "codex_execution_policy": base["codex_execution_policy"],
        "claude_permission_mode": base["claude_permission_mode"],
        "review_setup": setup,
        "review_family": family,
        "delegation": delegation == "on",
    }
    block = "\n".join(f"{key} = {toml_scalar(value)}" for key, value in fields.items())
    text += f"\n\n[presets.{PRESET}]\n{block}\n"

    path = tmp / f"profile-{cell_host}-{opposite_cli}-{setup}-{family}-{delegation}.toml"
    path.write_text(text)
    return path


def write_composable_profile(tmp: pathlib.Path, backend: pathlib.Path, scenario: dict):
    """Profile + optional user registry for one composable scenario.

    Returns (profile path, registry path or None). The registry is written as the
    profile's sibling because that is exactly how the launcher finds it — writing it
    anywhere else would test a path the product does not have."""
    text = PROFILE.read_text()
    for host in HOSTS:
        text = text.replace(
            f'command = "{host}"', f"command = {json.dumps(str(backend) + '-' + host)}", 1
        )
    strip = scenario.get("strip_provider")
    if strip:
        provider = tomllib.loads(PROFILE.read_text())["hosts"][strip]["provider"]
        text = text.replace(f'provider = "{provider}"', "# provider removed by fixture", 1)
    # A `${backend}` capability is absent exactly when its HOST CLI does not resolve — never
    # when a tool is uninstalled, because there is no tool. The capability-presence axis
    # rewrites named executables and so could not express this state at all: the reviewer
    # this branch added was PRESENT in all 253 cells, including the ones whose ids assert
    # that nothing is installed.
    absent_backend = scenario.get("absent_backend")
    if absent_backend:
        text = text.replace(
            f'command = {json.dumps(str(backend) + "-" + absent_backend)}',
            json.dumps("command = " + json.dumps(str(tmp / f"nonexistent-{absent_backend}")))[1:-1]
            .replace('\\"', '"'), 1,
        )

    base = tomllib.loads(PROFILE.read_text())["presets"]["balanced"]
    fields = {
        "label": "Golden composable",
        "mode": base.get("mode", "builder"),
        "main_tier": base["main_tier"],
        "codex_execution_policy": base["codex_execution_policy"],
        "claude_permission_mode": base["claude_permission_mode"],
        "delegation": scenario.get("delegation", True),
        **scenario.get("fields", {}),
    }
    block = "\n".join(f"{key} = {toml_scalar(value)}" for key, value in fields.items())
    review = scenario["review"].replace("PRESET", COMPOSABLE_PRESET)
    text += f"\n\n[presets.{COMPOSABLE_PRESET}]\n{block}\n{review}"

    directory = tmp / f"composable-{scenario['id']}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "profiles.toml"
    path.write_text(text)
    registry_path = None
    if "registry" in scenario:
        registry_path = directory / "review-methods.local.toml"
        registry_path.write_text(
            scenario["registry"].replace("CAPABILITY_CMD", str(tmp / "local-kit-tool"))
        )
    return path, registry_path


def write_shipped_profile(tmp: pathlib.Path, backend: pathlib.Path) -> pathlib.Path:
    """The SHIPPED presets, unmodified, against the fake backend.

    Every other cell in this golden invents its own preset, which means nothing here
    pinned what the presets a user actually launches project. That gap is why a
    default-policy migration had no A/B to run against."""
    text = PROFILE.read_text()
    for host in HOSTS:
        text = text.replace(
            f'command = "{host}"', f"command = {json.dumps(str(backend) + '-' + host)}", 1
        )
    path = tmp / "shipped-profiles.toml"
    path.write_text(text)
    return path


def shipped_cell(launcher, profile: pathlib.Path, host: str, preset: str, rules=()) -> dict:
    """What a shipped preset resolves to: its schema, its review, and the seats."""
    try:
        config = launcher.load_config(profile)
        plan = launcher.build_plan(config, host, preset)
    except launcher.LaunchError as exc:
        return {"error": normalise(str(exc), rules)}
    report = plan["review_report"]
    return {
        "schema": "composable" if report is not None else "legacy",
        "review_setup": plan["review_setup"],
        "review_family": plan["review_family"],
        "effective": list(launcher.effective_review(plan)[0]),
        "rows": None if report is None else [
            {"method_id": row.method_id, "status": row.status, "grade": row.grade,
             "provider": row.provider, "model": row.model, "effort": row.effort}
            for row in (report.base, *report.methods)
        ],
    }


def composable_module_cell(launcher, profile: pathlib.Path, host: str, rules=()) -> dict:
    """The resolver's own verdict: per-method status, grade and mechanism.

    effective_review() is meaningless here — a composable plan does not route through
    the legacy enum — so recording it would pin ([], [], None) for every cell and prove
    nothing about the schema under test."""
    try:
        config = launcher.load_config(profile)
        plan = launcher.build_plan(config, host, COMPOSABLE_PRESET)
    except launcher.LaunchError as exc:
        return {"error": normalise(str(exc), rules)}
    report = plan["review_report"]
    if report is None:
        return {"error": "no composable report was built for a composable preset"}
    return {
        "best_grade": report.best_grade,
        "availability": report.availability,
        "achieved_grade": report.achieved_grade,
        "rows": [
            {
                "method_id": row.method_id, "status": row.status, "grade": row.grade,
                "mechanism": row.mechanism, "effort": row.effort, "provider": row.provider,
            }
            for row in (report.base, *report.methods)
        ],
        "mcp_servers": [name for name, _, _ in launcher.review_mcp_servers(plan)],
    }


# ── observation routes ──────────────────────────────────────────────────────

def module_cell(launcher, profile: pathlib.Path, host: str, rules=()) -> dict:
    """effective_review() straight from the resolver — no subprocess, no argv."""
    try:
        config = launcher.load_config(profile)
        plan = launcher.build_plan(config, host, PRESET)
        effective, dropped, floor = launcher.effective_review(plan)
    except launcher.LaunchError as exc:
        # Normalised like the projection route: a LaunchError may quote the profile or
        # registry path, and an un-normalised temp path makes the golden differ from
        # itself on every run. Only the projection route normalised until a composable
        # error message first carried a path.
        return {"error": normalise(str(exc), rules)}
    return {
        "effective": list(effective),
        "dropped": list(dropped),
        "floor": floor,
        # build_plan can force review_family=same when the opposite host is absent.
        # Recording the resolved value keeps a silent downgrade visible in the golden.
        "resolved_family": plan["review_family"],
    }


def projection_cell(
    profile: pathlib.Path, host: str, env: dict, rules: list[tuple[str, str]], python: str,
    preset: str = PRESET,
) -> dict:
    """The real dispatch path, stopped at --dry-run: argv as the backend would see it."""
    proc = subprocess.run(
        [python, str(LAUNCHER), "--preset", preset, "--yes", "--dry-run", host, "--", "probe"],
        capture_output=True,
        text=True,
        env={**env, "AGENT_LAUNCH_DEBUG": "1", "AGENT_LAUNCH_CONFIG": str(profile)},
        cwd=str(REPO),
    )
    if proc.returncode != 0:
        return {"status": proc.returncode, "stderr": normalise(proc.stderr.strip(), rules)}
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    try:
        argv = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"status": proc.returncode, "argv_parse_failed": normalise(proc.stdout[-400:], rules)}
    argv = [normalise(item, rules) for item in argv]
    # The contract's argv index differs by host (codex takes it inside a -c
    # assignment, claude as the value after --append-system-prompt), so locate it
    # by its own prefix rather than a fixed position — the index is not stable.
    # Mark the contract IN PLACE rather than removing it: dropping it discarded both
    # its argv position and its multiplicity, so relocating or duplicating it left the
    # golden byte-identical while the backend invocation had materially changed.
    contract = next((item for item in argv if "LaunchPlan:" in item), None)
    return {
        "status": proc.returncode,
        "argv": [
            item[: item.index("LaunchPlan:")] + "<CONTRACT>" if "LaunchPlan:" in item else item
            for item in argv
        ],
        "contract": contract,
    }


# ── controls ────────────────────────────────────────────────────────────────

def run_controls(cells: dict) -> list[str]:
    """Falsifiable checks on the matrix itself. A golden that cannot fail these
    would prove nothing, so they run on every capture."""
    failures = []
    expected = len(SETUPS) * len(HOSTS) * len(FAMILIES) * len(OPPOSITE_CLIS) * len(DELEGATIONS)
    # Scoped to the legacy product, and identified by CONSTRUCTING its keys rather than
    # excluding the prefixes known today: an exclusion list silently absorbs every new
    # cell family into this count, which is exactly what happened when the shipped-preset
    # cells landed and turned a real cardinality guard into a moving number.
    legacy_keys = {
        cell_id(*combo)
        for combo in itertools.product(SETUPS, HOSTS, FAMILIES, OPPOSITE_CLIS, DELEGATIONS)
    }
    legacy = {key: cell for key, cell in cells.items() if key in legacy_keys}
    if not legacy:
        failures.append("control 1: matrix is empty — a vacuous golden proves nothing")
    elif len(legacy) != expected:
        failures.append(f"control 1: expected {expected} legacy cells, captured {len(legacy)}")

    # Control 4: the contract's invocation envelope must survive normalisation. The
    # token once replaced the whole argv element, which erased codex's
    # `developer_instructions="…"` wrapper — so changing that config key left every
    # cell byte-identical. At least one cell must retain a prefix before the token.
    enveloped = [
        key
        for key, cell in cells.items()
        for item in cell.get("projection", {}).get("argv", [])
        if item.endswith("<CONTRACT>") and item != "<CONTRACT>"
    ]
    if not enveloped:
        failures.append(
            "control 4: no cell kept an invocation envelope around the contract — "
            "normalisation is discarding how the backend receives it"
        )

    # Control 3: the two routes must agree per cell on whether the plan resolves.
    # They agreed on all 96 cells before the fixture was introduced; a broken fixture
    # made 48 cells fail in the dispatch while the resolver still said they were fine,
    # and controls 1-2 stayed green because both only look at shape, never at health.
    disagree = [
        key
        for key, cell in cells.items()
        if ("error" in cell.get("module", {})) != ("argv" not in cell.get("projection", {}))
    ]
    if disagree:
        failures.append(
            f"control 3: {len(disagree)} cell(s) where the resolver and the dispatch "
            f"disagree on success, e.g. {disagree[0]} — the harness is broken, not the launcher"
        )

    # Control 2: every axis must be load-bearing. If flipping one axis never changes
    # any cell, either the axis is inert or the matrix is built wrong — both are bugs
    # in this harness, not evidence that the launcher is consistent.
    index = {}
    for combo in itertools.product(SETUPS, HOSTS, FAMILIES, OPPOSITE_CLIS, DELEGATIONS):
        index[combo] = cells.get(cell_id(*combo))
    for axis_pos, axis in enumerate(AXES):
        values = (SETUPS, HOSTS, FAMILIES, OPPOSITE_CLIS, DELEGATIONS)[axis_pos]
        # EVERY value must be load-bearing, not just one of them. Requiring only that
        # some sibling differs once let a four-state axis collapse to two — an absence
        # state that behaves exactly like present is indistinguishable from a
        # resolver that ignores the absence, which is the regression the state exists for.
        for other in values[1:]:
            distinguished = any(
                index.get(combo)
                != index.get(combo[:axis_pos] + (other,) + combo[axis_pos + 1 :])
                for combo in index
                if combo[axis_pos] == values[0]
            )
            if not distinguished:
                failures.append(
                    f"control 2: axis {axis!r} value {other!r} behaves exactly like "
                    f"{values[0]!r} in every cell — that value tests nothing"
                )
    failures += composable_controls(cells)
    failures += shipped_controls(cells)
    failures += hermeticity_controls(cells)
    return failures


NUDGE_MARK = "session-distill due:"


def hermeticity_controls(cells: dict) -> list[str]:
    """Control 11: no cell carries an environment-state notice. The launcher's
    session-distill nudge depends on how many sessions the OPERATOR has accumulated —
    a fact about the machine, not about routing — and a golden that captures it
    drifts whenever that count crosses the threshold, which reads as a routing
    regression. Any stderr, on either route, containing the nudge is a capture that
    was not hermetic."""
    leaked = sorted(
        key for key, cell in cells.items()
        if any(NUDGE_MARK in str((cell.get(route) or {}).get("stderr", ""))
               for route in ("projection", "module"))
    )
    if leaked:
        return [f"control 11: {len(leaked)} cell(s) carry the session-distill nudge in "
                f"stderr — the capture read the operator's state, not the fixture's "
                f"(first: {leaked[0]})"]
    return []


def shipped_controls(cells: dict) -> list[str]:
    """Control 9: every shipped preset is projected on both hosts, and each one's
    schema is recorded. This is the A/B surface for a default-policy migration — the
    only place the golden can show which shipped presets moved and which did not."""
    failures = []
    shipped = {key: cell for key, cell in cells.items() if key.startswith("shipped/")}
    presets = sorted(tomllib.loads(PROFILE.read_text())["presets"])
    expected = len(presets) * len(HOSTS)
    if not shipped:
        failures.append("control 9: no shipped-preset cells — a default migration has no A/B")
        return failures
    if len(shipped) != expected:
        failures.append(f"control 9: expected {expected} shipped cells, got {len(shipped)}")
    for preset in presets:
        for host in HOSTS:
            cell = shipped.get(shipped_cell_id(preset, host))
            if cell is None:
                failures.append(f"control 9: shipped preset {preset!r} unprojected on {host}")
                continue
            schema = cell.get("module", {}).get("schema")
            if schema not in ("legacy", "composable"):
                failures.append(
                    f"control 9: shipped preset {preset!r} on {host} recorded no schema "
                    f"({cell.get('module', {}).get('error', 'unknown')!r})"
                )
    return failures


def composable_controls(cells: dict) -> list[str]:
    """The composable half. Its scenarios are enumerated rather than a product, so the
    product-shaped controls above do not apply; these are its equivalents."""
    failures = []
    composable = {key: cell for key, cell in cells.items() if key.startswith("composable/")}
    expected = sum(len(s.get("hosts", HOSTS)) for s in COMPOSABLE_SCENARIOS)
    if not composable:
        failures.append("control 5: no composable cells — the schema has no E2E coverage")
        return failures
    if len(composable) != expected:
        failures.append(f"control 5: expected {expected} composable cells, got {len(composable)}")

    # Control 6: every scenario's DECLARED outcome must be the observed one. Without
    # this a failure branch that quietly starts succeeding would just be re-baselined
    # into the golden as the new truth.
    for scenario in COMPOSABLE_SCENARIOS:
        for host in scenario.get("hosts", HOSTS):
            cell = composable.get(composable_cell_id(scenario["id"], host))
            if cell is None:
                failures.append(f"control 6: missing cell for {scenario['id']} on {host}")
                continue
            errored = "error" in cell.get("module", {}) or "argv" not in cell.get("projection", {})
            if errored != (scenario["outcome"] == "error"):
                failures.append(
                    f"control 6: {scenario['id']} on {host} declared outcome "
                    f"{scenario['outcome']!r} but "
                    f"{'failed' if errored else 'succeeded'}"
                )
    # Both outcomes must be represented, or control 6 is asserting one thing about a
    # uniform population.
    outcomes = {scenario["outcome"] for scenario in COMPOSABLE_SCENARIOS}
    if outcomes != {"ok", "error"}:
        failures.append(f"control 6: composable scenarios cover only {sorted(outcomes)}")

    # Control 7: no scenario may be indistinguishable from the plain base-only shape.
    # A scenario whose projection matches the baseline is testing nothing, which is how
    # a dropped axis hides.
    for host in HOSTS:
        baseline = composable.get(composable_cell_id("base-only", host))
        if baseline is None:
            continue
        twins = [
            scenario["id"]
            for scenario in COMPOSABLE_SCENARIOS
            if scenario["id"] != "base-only"
            and host in scenario.get("hosts", HOSTS)
            and composable.get(composable_cell_id(scenario["id"], host)) == baseline
        ]
        if twins:
            failures.append(
                f"control 7: on {host}, scenario(s) {twins} project exactly like base-only — "
                "they test nothing"
            )

    # Control 8: an absent capability must remove the stdio server from the ARGS, not
    # merely annotate the contract. This is the half that only the projection route can
    # see, and the reason these cells run a real process at all.
    for scenario_id, server_expected in (
        ("base-plus-codex-exec", False), ("codex-exec-absent", False),
        ("local-registry", True),
    ):
        for host in HOSTS:
            cell = composable.get(composable_cell_id(scenario_id, host))
            if cell is None:
                continue
            argv = " ".join(cell.get("projection", {}).get("argv", []))
            has_server = "mcp_servers." in argv or "mcpServers" in argv
            if has_server != server_expected:
                failures.append(
                    f"control 8: {scenario_id} on {host} "
                    f"{'registered' if has_server else 'did not register'} an MCP server; "
                    f"expected the opposite"
                )
    # Control 10: the host-scoped arm cells must differ BETWEEN hosts. Identical cells
    # would mean the arms were not selected per host at all — the exact defect the form
    # exists to prevent, and invisible to any single-host assertion.
    left = composable.get(composable_cell_id("arms-both-hosts", "claude"))
    right = composable.get(composable_cell_id("arms-both-hosts", "codex"))
    if left is None or right is None:
        failures.append("control 10: the host-scoped arms scenario is missing a host")
    else:
        providers = [
            tuple(row["provider"] for row in cell.get("module", {}).get("rows", []))
            for cell in (left, right)
        ]
        if providers[0] == providers[1]:
            failures.append(
                f"control 10: both hosts resolved the same reviewer providers {providers[0]} — "
                "the arms were not selected per host"
            )
        if not all(providers):
            failures.append("control 10: an arms cell resolved no reviewer rows at all")
    return failures


# ── driver ──────────────────────────────────────────────────────────────────

def capture(*, only: set[str] | None = None) -> dict:
    from fixture_support import legacy_host_environment
    with legacy_host_environment(REPO):
        return _capture(only=only)


def _capture(*, only: set[str] | None = None) -> dict:
    spec = importlib.util.spec_from_file_location("agent_launch_goldens", LAUNCHER)
    launcher = importlib.util.module_from_spec(spec)
    # Required: without it @dataclass raises AttributeError on None.__dict__.
    sys.modules[spec.name] = launcher
    spec.loader.exec_module(launcher)

    python = os.environ.get("AGENT_LAUNCH_VENV_PYTHON") or sys.executable
    cells = {}
    with tempfile.TemporaryDirectory() as raw:
        tmp = pathlib.Path(raw)
        backend = tmp / "backend"
        for host in HOSTS:
            per_host = tmp / f"backend-{host}"
            per_host.write_text("#!/usr/bin/env bash\nexit 0\n")
            per_host.chmod(0o755)
        # The user-registered capability's executable (composable local-registry
        # scenario). The shipped capabilities are `${backend}` and need no fake of
        # their own — the per-host backends above ARE their executables.
        local_kit = tmp / "local-kit-tool"
        local_kit.write_text("#!/usr/bin/env bash\nexit 0\n")
        local_kit.chmod(0o755)
        # Without a fixture the launcher reads the author's real ${CODEX_HOME} for
        # codex-run and the agent templates, so the golden encoded one machine's
        # install and drifted on a clean checkout even with repo behaviour unchanged.
        codex_home = tmp / "codex-home"
        (codex_home / "bin").mkdir(parents=True)
        (codex_home / "agents").mkdir(parents=True)
        # Mirror what install.sh deploys into CODEX_HOME. Both wrappers matter:
        # omitting codex-helm silently removed the cross-family fanout branch from
        # every contract, so that behaviour became unobservable in all 192 cells.
        for wrapper in ("codex-run", "codex-helm"):
            path = codex_home / "bin" / wrapper
            path.write_text("#!/usr/bin/env bash\nexit 0\n")
            path.chmod(0o755)
        # The templates come from the repository, not from thin air: the launcher
        # rejects a template without a description, and an invented empty one turned
        # 48 codex/delegation-on cells into error records that still passed the
        # controls. Sourcing them here also means a template edit moves the golden.
        for tier in ("frontier", "workhorse", "sweep"):
            source = REPO / "codex" / "agents" / f"{tier}.toml"
            if not source.is_file():
                raise SystemExit(f"missing agent template for the fixture: {source}")
            (codex_home / "agents" / f"{tier}.toml").write_text(source.read_text())
        # The claude side of the same fixture, and it exists for the reason the
        # codex-helm comment above records: the panel's claude dispatch now prefers the
        # deployed claude-run adapter, and a fixture without one leaves that branch
        # unexercised in every cell — the golden would stay green because the new route
        # never ran, not because it was correct.
        claude_home = tmp / "claude-home"
        (claude_home / "bin").mkdir(parents=True)
        claude_adapter = claude_home / "bin" / "claude-run"
        claude_adapter.write_text("#!/usr/bin/env bash\nexit 0\n")
        claude_adapter.chmod(0o755)
        rules = normaliser(tmp)
        # R2-2: the module route reads CODEX_HOME straight from os.environ, so passing
        # it only in the subprocess env left half the capture reading the author's real
        # install. Setting it on the process covers both routes. CLAUDE_CONFIG_DIR is
        # read the same way and needs the same treatment.
        os.environ["CODEX_HOME"] = str(codex_home)
        os.environ["CLAUDE_CONFIG_DIR"] = str(claude_home)
        # These are legacy projection goldens; an operator's private install
        # must not turn only the subprocess half into snapshot activation.
        os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"] = "0"
        # The session-distill nudge reads the OPERATOR's state file and history line
        # counts through Path.home(), not through the homes pinned above, so it leaked
        # into every cell's stderr the day the author's history crossed the threshold
        # (2026-08-27: a benchmark's few hundred `claude -p` dispatches did it). The
        # launcher offers this override and treats a missing file as "no nudge"; pointing
        # it into the fixture makes the capture independent of how many sessions whoever
        # runs it has accumulated. Both routes read os.environ, so set it on the process.
        os.environ["AGENT_BIOS_SESSION_DISTILL_STATE"] = str(tmp / "no-distill-state.json")
        env = {
            **os.environ,
            "XDG_CACHE_HOME": str(tmp / "cache"),
            "CODEX_HOME": str(codex_home),
            "CLAUDE_CONFIG_DIR": str(claude_home),
            "AGENT_BIOS_SESSION_DISTILL_STATE": str(tmp / "no-distill-state.json"),
        }
        version = tmp / "version.json"
        version.write_text('{"version": "9.9.9", "releaseDate": "2026-01-02"}')
        env["AGENT_LAUNCH_VERSION_FILE"] = str(version)

        for opposite_cli, setup, family, delegation in itertools.product(
            OPPOSITE_CLIS, SETUPS, FAMILIES, DELEGATIONS
        ):
            # The absent CLI is relative to the cell's host, so the profile is
            # per-host rather than shared across the host axis.
            for host in HOSTS:
                key = cell_id(setup, host, family, opposite_cli, delegation)
                if only is not None and key not in only:
                    continue
                profile = write_profile(
                    tmp, backend, host, opposite_cli, setup, family, delegation
                )
                cells[key] = {
                    "module": module_cell(launcher, profile, host, rules),
                    "projection": projection_cell(profile, host, env, rules, python),
                }

        shipped_profile = write_shipped_profile(tmp, backend)
        for preset in sorted(tomllib.loads(PROFILE.read_text())["presets"]):
            for host in HOSTS:
                key = shipped_cell_id(preset, host)
                if only is not None and key not in only:
                    continue
                cells[key] = {
                    "module": shipped_cell(launcher, shipped_profile, host, preset, rules),
                    "projection": projection_cell(
                        shipped_profile, host, env, rules, python, preset
                    ),
                }

        for scenario in COMPOSABLE_SCENARIOS:
            if only is not None and not any(composable_cell_id(scenario["id"], host) in only
                                            for host in scenario.get("hosts", HOSTS)):
                continue
            profile, _ = write_composable_profile(tmp, backend, scenario)
            for host in scenario.get("hosts", HOSTS):
                key = composable_cell_id(scenario["id"], host)
                if only is not None and key not in only:
                    continue
                cells[key] = {
                    "module": composable_module_cell(launcher, profile, host, rules),
                    "projection": projection_cell(
                        profile, host, env, rules, python, COMPOSABLE_PRESET
                    ),
                }
    return cells


def self_test() -> int:
    """Every control must still fail on the defect it exists for. Runs against the
    stored golden mutated in memory, plus one real projection per private-mode
    poisoning case. Each mutation below is one that actually shipped and was caught,
    not a hypothetical."""
    if not GOLDEN.exists():
        print(f"FAIL self-test: golden missing: {GOLDEN}", file=sys.stderr)
        return 1
    stored = json.loads(GOLDEN.read_text())
    if run_controls(stored):
        print("FAIL self-test: the stored golden does not pass its own controls", file=sys.stderr)
        return 1

    def collapse_axis(cells):
        # An axis value that no longer behaves differently — the singleton-collapse
        # regression the four-state capability axis exists to catch.
        mutated = dict(cells)
        for key in cells:
            if "/cli-absent/" in key:
                mutated[key] = cells[key.replace("/cli-absent/", "/cli-present/")]
        return mutated

    def disagree(cells):
        # The resolver says a plan resolves while the dispatch fails: a broken
        # fixture, not a launcher change.
        mutated = dict(cells)
        for key, cell in cells.items():
            if "error" not in cell["module"] and "argv" in cell["projection"]:
                mutated[key] = {**cell, "projection": {"status": 2, "stderr": "mutated"}}
                break
        return mutated

    def strip_envelopes(cells):
        # The contract token swallowing its invocation envelope.
        return {
            key: {
                **cell,
                "projection": {
                    **cell["projection"],
                    "argv": [
                        "<CONTRACT>" if item.endswith("<CONTRACT>") else item
                        for item in cell["projection"].get("argv", [])
                    ],
                }
                if "argv" in cell["projection"] else cell["projection"],
            }
            for key, cell in cells.items()
        }

    def drop_one(prefix_match):
        # Dropping "the last cell" stopped testing control 1 once composable cells were
        # appended: it removed one of those and fired control 5 instead. Each count
        # control must lose a cell from its OWN population.
        def mutate(cells):
            mutated = dict(cells)
            for key in cells:
                if key.startswith("composable/") == prefix_match:
                    del mutated[key]
                    return mutated
            return mutated
        return mutate

    def outcome_flipped(cells):
        # A declared failure branch that quietly starts succeeding. Without control 6
        # this would be re-baselined into the golden as the new truth.
        mutated = dict(cells)
        for scenario in COMPOSABLE_SCENARIOS:
            if scenario["outcome"] != "error":
                continue
            key = composable_cell_id(scenario["id"], scenario.get("hosts", HOSTS)[0])
            if key in mutated:
                mutated[key] = {"module": {"rows": []}, "projection": {"status": 0, "argv": []}}
                return mutated
        return mutated

    def twin_of_baseline(cells):
        # A scenario that projects exactly like base-only is testing nothing.
        mutated = dict(cells)
        for host in HOSTS:
            baseline = cells.get(composable_cell_id("base-only", host))
            twin = composable_cell_id("base-plus-codex-exec", host)
            if baseline is not None and twin in mutated:
                mutated[twin] = baseline
                return mutated
        return mutated

    def server_registered_anyway(cells):
        # An absent capability whose stdio server still reaches the args — the failure
        # only the projection route can see.
        mutated = dict(cells)
        key = composable_cell_id("base-plus-codex-exec", HOSTS[0])
        cell = cells.get(key)
        if cell is not None and "argv" in cell.get("projection", {}):
            mutated[key] = {
                **cell,
                "projection": {
                    **cell["projection"],
                    "argv": [*cell["projection"]["argv"], "mcp_servers.local-kit.enabled=true"],
                },
            }
        return mutated

    def unschema_shipped(cells):
        # A shipped preset that no longer records which schema it resolves through —
        # the A/B surface going blind exactly when a migration needs it.
        mutated = dict(cells)
        for key, cell in cells.items():
            if key.startswith("shipped/"):
                mutated[key] = {**cell, "module": {**cell["module"], "schema": "?"}}
                return mutated
        return mutated

    def arms_not_selected(cells):
        # Both hosts resolving the same reviewers: the arm was never selected per host,
        # which is the whole reason the form exists and is invisible on one host.
        mutated = dict(cells)
        left = composable_cell_id("arms-both-hosts", "claude")
        right = composable_cell_id("arms-both-hosts", "codex")
        if left in mutated and right in mutated:
            mutated[right] = mutated[left]
        return mutated

    def nudge_leaks(route):
        """The operator's nudge reaching ONE observation route's stderr.

        Planted in both routes at once, a single mutation cannot tell whether control 11
        reads both — one working branch masks a blind one. The live leak reached both,
        so each route gets its own mutation."""
        def mutate(cells):
            mutated = dict(cells)
            for key, cell in cells.items():
                side = dict(cell.get(route) or {})
                side["stderr"] = (NUDGE_MARK + " ~262 new session entries since 2026-08-25 "
                                  "(threshold 250)\n" + str(side.get("stderr", "")))
                mutated[key] = {**cell, route: side}
                return mutated
            return mutated
        return mutate

    mutations = [
        ("control 11 (nudge in the projection route)", nudge_leaks("projection")),
        ("control 11 (nudge in the module route)", nudge_leaks("module")),
        ("control 10 (arms selected per host)", arms_not_selected),
        ("control 9 (shipped presets projected)", unschema_shipped),
        ("control 1 (legacy cell count)", drop_one(False)),
        ("control 2 (axis is load-bearing)", collapse_axis),
        ("control 3 (routes agree)", disagree),
        ("control 4 (contract envelope)", strip_envelopes),
        ("control 5 (composable cell count)", drop_one(True)),
        ("control 6 (declared outcome observed)", outcome_flipped),
        ("control 7 (no scenario is a twin)", twin_of_baseline),
        ("control 8 (capability absence reaches argv)", server_registered_anyway),
    ]
    failures = []
    for name, mutate in mutations:
        if not run_controls(mutate(stored)):
            failures.append(f"{name} did not fire on its own defect")
    failures.extend(private_mode_controls(stored))
    for failure in failures:
        print(f"FAIL self-test: {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"review goldens self-test OK ({len(mutations)} mutation controls; "
          "2 real projections isolate private-mode poisoning)")
    return 0


def private_mode_controls(stored: dict) -> list[str]:
    """An operator's install or explicit opt-in cannot change a legacy projection."""
    from launcher_fixture_env import launcher_environment

    key = cell_id("none", "codex", "cross", "present", "on")
    if key not in stored or "argv" not in stored[key].get("projection", {}):
        return ["control 12: private-mode projection subject is absent or does not succeed"]
    failures = []
    previous = os.environ.copy()
    try:
        for flag in (None, "1"):
            with tempfile.TemporaryDirectory(prefix="review-private-mode-") as directory:
                root = pathlib.Path(directory).resolve()
                with launcher_environment(root, REPO):
                    # A deliberately incomplete private record is enough to poison
                    # auto-detection if the capture's mode pin disappears. All private
                    # paths stay in the fixture even in that failing control.
                    os.environ["AGENT_BIOS_INSTRUCTIONS_DIR"] = str(root / "instructions")
                    os.environ["AGENT_BIOS_PACKAGE_ROOT"] = str(REPO)
                    marker = root / "state/runtime/private-install.json"
                    marker.parent.mkdir(parents=True)
                    marker.write_text('{"mode":"private-session-scoped"}\n')
                    if flag is None:
                        os.environ.pop("AGENT_BIOS_PRIVATE_INSTRUCTIONS", None)
                    else:
                        os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"] = flag
                    observed = capture(only={key})
                    if observed != {key: stored[key]}:
                        label = "installed state" if flag is None else "inherited private flag"
                        failures.append(f"control 12: {label} changed the legacy projection")
    finally:
        os.environ.clear()
        os.environ.update(previous)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="diff against the stored golden")
    parser.add_argument(
        "--self-test", action="store_true",
        help="prove controls with golden mutations and isolated private-mode projections",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    cells = capture()
    failures = run_controls(cells)
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        return 1

    payload = json.dumps(cells, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not GOLDEN.exists():
            print(f"FAIL golden missing: {GOLDEN}", file=sys.stderr)
            return 1
        if GOLDEN.read_text() != payload:
            print(f"FAIL golden drift: {GOLDEN}", file=sys.stderr)
            return 1
        print(f"review goldens OK ({len(cells)} cells, {len(run_controls(cells))} control failures)")
        return 0

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(payload)
    print(f"wrote {GOLDEN.relative_to(REPO)} ({len(cells)} cells; controls passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
