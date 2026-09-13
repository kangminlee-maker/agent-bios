#!/usr/bin/env python3
"""Executable coverage for tier effort projection, including Haiku omission.

Runs only local config/serialization paths in a temporary config root. It never
starts either provider CLI: the one launcher invocation uses --dry-run.
"""

from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib


ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "launch" / "agent-launch.toml"
MODULE = ROOT / "launch" / "agent-launch.py"
sys.path.insert(0, str(ROOT / "gates"))
from fixture_support import legacy_host_environment


def load_launcher():
    spec = importlib.util.spec_from_file_location("agent_launch_test", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launch = None


def expect_error(call, fragment: str) -> None:
    try:
        call()
    except launch.LaunchError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected LaunchError containing {fragment!r}")


def saved_preset(source: dict, name: str, main_tier: str, *, workhorse_haiku: bool) -> dict:
    preset = copy.deepcopy(source["presets"]["balanced"])
    preset.update({
        "label": name,
        "description": "tier-effort serialization test",
        "mode": "builder",
        "main_tier": main_tier,
        "review_setup": "none",
    })
    preset.pop("review", None)
    if workhorse_haiku:
        preset["tier_overrides"] = {
            "claude": {"workhorse": {"model": "claude-haiku-4-5"}}
        }
    source["presets"][name] = preset
    return launch.build_plan(source, "claude", name)


def find_option(args: list[str], option: str) -> str:
    index = args.index(option)
    return args[index + 1]


def sweep_main_plan(source: dict, host: str) -> dict:
    """A selectable SWEEP main, with delegation requested to prove it is narrowed."""
    preset = copy.deepcopy(source["presets"]["solo"])
    preset.update({
        "label": f"sweep-main-{host}",
        "description": "SWEEP main projection test",
        "main_tier": "sweep",
        "delegation": True,
    })
    source["presets"][f"sweep-main-{host}"] = preset
    return launch.build_plan(source, host, f"sweep-main-{host}")


def sweep_review_preset(source: dict, host: str) -> str:
    name = f"sweep-review-{host}"
    preset = copy.deepcopy(source["presets"]["solo"])
    preset.update({
        "label": name,
        "description": "Must refuse review on a SWEEP main.",
        "main_tier": "sweep",
        "review_setup": "native-panel",
    })
    source["presets"][name] = preset
    return name


def run_checks() -> int:
    global launch
    launch = load_launcher()
    config = launch.load_config(CONFIG)
    for separator in ("/", " / ", " · "):
        assert launch.format_model_effort("model", "xhigh", separator) == f"model{separator}xhigh"
        assert launch.format_model_effort("model", None, separator) == "model"
    expected = {
        "claude": {
            "frontier": ("claude-fable-5-1", "max"),
            "helm": ("claude-opus-5", "xhigh"),
            "workhorse": ("claude-sonnet-5", "xhigh"),
            "sweep": ("claude-haiku-4-5", None),
        },
        "codex": {
            "frontier": ("gpt-6-astra", "max"),
            "helm": ("gpt-5.6-sol", "xhigh"),
            "workhorse": ("gpt-5.6-terra", "xhigh"),
            "sweep": ("gpt-5.6-luna", "max"),
        },
    }
    for host, matrix in expected.items():
        plan = launch.build_plan(config, host, "balanced")
        actual = {
            tier: (plan["tiers"][tier]["model"], launch.tier_effort(plan, tier))
            for tier in launch.TIER_ORDER
        }
        assert actual == matrix, (host, actual)

    for host in ("claude", "codex"):
        sweep_config = copy.deepcopy(config)
        plan = sweep_main_plan(sweep_config, host)
        original_review_mcp_servers = launch.review_mcp_servers
        launch.review_mcp_servers = lambda _plan: (_ for _ in ()).throw(
            AssertionError("SWEEP must not select an MCP registration")
        )
        try:
            args = launch.project_args(plan, materialize_agents=False)
            contract = launch.run_contract(plan)
        finally:
            launch.review_mcp_servers = original_review_mcp_servers
        summary = io.StringIO()
        launch.print_summary(plan, host, args, stream=summary)
        assert plan["delegation"] is False
        assert plan["delegation_requested"] is True
        assert launch.active_tiers(plan) == ("sweep",)
        assert "SWEEP main: apply one explicit read-only rule per item" in contract
        assert "SWEEP main disables delegation" in contract
        assert "SWEEP restricted" in summary.getvalue()
        assert "restricted" in "\n".join(launch.setup_summary_lines(plan))
        if host == "claude":
            assert "--effort" not in args
            assert "--agents" not in args
            assert "--restricted" in args
            assert find_option(args, "--tools") == "Read,Glob,Grep"
            assert "--strict-mcp-config" in args
            assert json.loads(find_option(args, "--mcp-config")) == {"mcpServers": {}}
            assert "--dangerously-skip-permissions" not in args
            assert "Claude runs with --restricted" in contract
            assert "inherited MCP servers are unavailable" in contract
            assert "strict empty MCP" in summary.getvalue()
        else:
            assert "--dangerously-bypass-approvals-and-sandbox" not in args
            assert args[args.index("--sandbox") + 1] == "read-only"
            assert 'features.multi_agent=false' in args
            assert not any("agents." in item for item in args)
            assert "Codex runs with --sandbox read-only" in contract
        assert "Review MCP registrations" not in contract

    for host in ("claude", "codex"):
        sweep_review_config = copy.deepcopy(config)
        name = sweep_review_preset(sweep_review_config, host)
        expect_error(
            lambda host=host, name=name, sweep_review_config=sweep_review_config: launch.build_plan(
                sweep_review_config, host, name
            ),
            "Turn review off (the Solo setup) or choose HELM or WORKHORSE as main",
        )

    review_menu_config = copy.deepcopy(config)
    review_menu = copy.deepcopy(review_menu_config["presets"]["solo"])
    review_menu.update({"label": "review-menu", "review_setup": "native-panel"})
    review_menu_config["presets"]["review-menu"] = review_menu
    review_menu_plan = launch.build_plan(review_menu_config, "claude", "review-menu")
    review_menu_answers = iter(["1", "4", "q"])
    review_menu_output = io.StringIO()
    original_read_input = launch.read_input

    def review_menu_read_input(_prompt: str) -> str:
        return next(review_menu_answers)

    launch.read_input = review_menu_read_input
    try:
        with contextlib.redirect_stdout(review_menu_output):
            try:
                launch.customize(review_menu_plan, review_menu_config, CONFIG, ui=None)
            except KeyboardInterrupt:
                pass
    finally:
        launch.read_input = original_read_input
    assert review_menu_plan["main_tier"] == "helm"
    assert "cannot dispatch review" in review_menu_output.getvalue()

    claude_plan = launch.build_plan(config, "claude", "balanced")
    claude_args = launch.project_args(claude_plan, materialize_agents=False)
    assert "--dangerously-skip-permissions" in claude_args
    assert "--restricted" not in claude_args
    agents = json.loads(find_option(claude_args, "--agents"))
    sweep = agents["sweep"]
    assert sweep["model"] == "claude-haiku-4-5"
    assert "effort" not in sweep
    assert sweep["tools"] == ["Read", "Glob", "Grep"]
    assert "one explicit read-only rule per item" in sweep["prompt"]
    assert "semantic judgments" in sweep["prompt"]
    assert "None" not in sweep["description"] + sweep["prompt"]
    assert launch.effort_options("claude", "claude-haiku-4-5") == []
    assert launch.binding_for_selected_model(
        "claude", {"model": "claude-sonnet-5", "effort": "xhigh"}, "claude-haiku-4-5"
    ) == {"model": "claude-haiku-4-5"}
    assert launch.binding_for_selected_model(
        "claude",
        {"model": "claude-haiku-4-5"},
        "claude-sonnet-5",
        default_effort="xhigh",
    ) == {"model": "claude-sonnet-5", "effort": "xhigh"}

    codex_default_args = launch.project_args(
        launch.build_plan(config, "codex", "balanced"), materialize_agents=False
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in codex_default_args

    # Exercise the numbered fallback rather than only its helper: this is the
    # Astra reproduction (FRONTIER → Haiku → Fable 5.1 → Enter). The final
    # `5`, `10` reopen the model menu; the synthetic `q` merely ends the probe.
    picker_plan = launch.build_plan(config, "claude", "solo")
    picker_answers = iter(["5", "5", "5", "2", "", "5", "10"])
    picker_prompts: list[str] = []
    original_read_input = launch.read_input
    original_private = os.environ.get("AGENT_BIOS_PRIVATE_INSTRUCTIONS")

    def picker_read_input(prompt: str) -> str:
        picker_prompts.append(prompt)
        return next(picker_answers, "q")

    launch.read_input = picker_read_input
    os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"] = "0"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                launch.customize(picker_plan, config, CONFIG, ui=None)
            except KeyboardInterrupt:
                pass
    finally:
        launch.read_input = original_read_input
        if original_private is None:
            os.environ.pop("AGENT_BIOS_PRIVATE_INSTRUCTIONS", None)
        else:
            os.environ["AGENT_BIOS_PRIVATE_INSTRUCTIONS"] = original_private
    assert any("[max]" in prompt for prompt in picker_prompts), picker_prompts
    assert picker_plan["tiers"]["frontier"] == {
        "model": "claude-fable-5-1", "effort": "max"
    }
    assert picker_plan["frontier_effort"] == "max"

    haiku_main_config = copy.deepcopy(config)
    haiku_main = saved_preset(
        haiku_main_config, "haiku-main-source", "sweep", workhorse_haiku=False
    )
    haiku_main_args = launch.project_args(haiku_main, materialize_agents=False)
    assert "--effort" not in haiku_main_args
    assert "None" not in launch.run_contract(haiku_main)
    assert "None" not in "\n".join(launch.setup_summary_lines(haiku_main))
    summary = io.StringIO()
    launch.print_summary(haiku_main, "claude", haiku_main_args, stream=summary)
    assert "None" not in summary.getvalue()

    override_config = copy.deepcopy(config)
    override_plan = saved_preset(
        override_config, "haiku-workhorse-source", "workhorse", workhorse_haiku=True
    )
    assert override_plan["tiers"]["workhorse"] == {"model": "claude-haiku-4-5"}
    assert launch.tier_effort(override_plan, "workhorse") is None
    assert "--effort" not in launch.project_args(override_plan, materialize_agents=False)

    reviewed_workhorse_config = copy.deepcopy(config)
    reviewed_workhorse = copy.deepcopy(reviewed_workhorse_config["presets"]["balanced"])
    reviewed_workhorse.update({
        "label": "haiku-workhorse-reviewed",
        "description": "Haiku main with an independent effort-capable reviewer.",
        "main_tier": "workhorse",
        "delegation": True,
        "tier_overrides": {
            "claude": {"workhorse": {"model": "claude-haiku-4-5"}}
        },
        "review": {
            "base": {"provider": "openai", "model": "gpt-5.6-sol", "effort": "xhigh"},
            "methods": {},
        },
    })
    reviewed_workhorse.pop("review_setup", None)
    reviewed_workhorse_config["presets"]["haiku-workhorse-reviewed"] = reviewed_workhorse
    reviewed_workhorse_plan = launch.build_plan(
        reviewed_workhorse_config, "claude", "haiku-workhorse-reviewed"
    )
    assert reviewed_workhorse_plan["delegation"] is True
    assert reviewed_workhorse_plan["review_report"].base.effort == "xhigh"
    assert "--effort" not in launch.project_args(
        reviewed_workhorse_plan, materialize_agents=False
    )

    malformed = copy.deepcopy(config)
    malformed["hosts"]["claude"]["tiers"]["sweep"]["effort"] = "low"
    expect_error(
        lambda: launch.validate_host_tiers("claude", malformed["hosts"]["claude"]["tiers"]),
        "does not accept an effort",
    )
    malformed = copy.deepcopy(config)
    malformed["presets"]["invalid-haiku-override"] = {
        "label": "invalid-haiku-override",
        "description": "must reject an effort on Haiku",
        "mode": "builder",
        "main_tier": "workhorse",
        "review_setup": "none",
        "delegation": True,
        "codex_execution_policy": "bypass",
        "claude_permission_mode": "bypassPermissions",
        "tier_overrides": {
            "claude": {"workhorse": {"model": "claude-haiku-4-5", "effort": "low"}}
        },
    }
    expect_error(
        lambda: launch.build_plan(malformed, "claude", "invalid-haiku-override"),
        "does not accept an effort",
    )
    expect_error(
        lambda: launch.parse_review_binding(
            {"provider": "anthropic", "model": "claude-sonnet-5"}, config, "test.review"
        ),
        "effort is required",
    )
    for host, tier in (("claude", "workhorse"), ("codex", "workhorse")):
        malformed = copy.deepcopy(config)
        malformed["hosts"][host]["tiers"][tier].pop("effort")
        expect_error(
            lambda host=host, malformed=malformed: launch.validate_host_tiers(
                host, malformed["hosts"][host]["tiers"]
            ),
            "unsupported effort",
        )

    haiku_binding = launch.parse_review_binding(
        {"provider": "anthropic", "tier": "sweep"}, config, "test.review"
    )
    assert haiku_binding is not None and haiku_binding.effort is None
    review_methods = launch.load_review_methods(config)
    sol_binding = launch.ReviewBinding(
        "openai", "codex", "gpt-5.6-sol", "xhigh"
    )
    main_haiku_review = launch.resolve_composable_review(
        launch.ReviewPlan(True, sol_binding, {}, "composable"),
        haiku_binding,
        config,
        review_methods,
    )
    assert main_haiku_review.base.model == "gpt-5.6-sol"
    assert main_haiku_review.base.effort == "xhigh"
    assert launch.review_plan_from_v1(launch.review_plan_v1(main_haiku_review)).base.effort == "xhigh"
    expect_error(
        lambda: launch.resolve_composable_review(
            launch.ReviewPlan(True, haiku_binding, {}, "composable"),
            sol_binding,
            config,
            review_methods,
        ),
        "ReviewPlan/v1 seat require an explicit effort",
    )

    with tempfile.TemporaryDirectory(prefix="agent-launch-tier-effort-") as directory:
        temporary = pathlib.Path(directory)
        config_path = temporary / CONFIG.name
        shutil.copy2(CONFIG, config_path)
        temporary_config = launch.load_config(config_path)

        main_plan = saved_preset(
            temporary_config, "haiku-main-source", "sweep", workhorse_haiku=False
        )
        launch.save_preset(main_plan, temporary_config, config_path, "haiku-main")

        workhorse_plan = saved_preset(
            temporary_config, "haiku-workhorse-source", "workhorse", workhorse_haiku=True
        )
        launch.save_preset(workhorse_plan, temporary_config, config_path, "haiku-workhorse")
        saved = tomllib.loads((temporary / launch.USER_PRESETS_NAME).read_text(encoding="utf-8"))
        assert saved["presets"]["haiku-main"]["delegation"] is True
        workhorse = saved["presets"]["haiku-workhorse"]
        assert workhorse["tier_overrides"]["claude"]["workhorse"] == {
            "model": "claude-haiku-4-5"
        }
        assert "frontier_effort" not in workhorse

        reloaded = launch.load_config(config_path)
        reloaded_sweep_plan = launch.build_plan(reloaded, "claude", "haiku-main")
        assert reloaded_sweep_plan["delegation_requested"] is True
        assert reloaded_sweep_plan["delegation"] is False
        reloaded_plan = launch.build_plan(reloaded, "claude", "haiku-workhorse")
        assert launch.tier_effort(reloaded_plan, "workhorse") is None
        assert "--effort" not in launch.project_args(reloaded_plan, materialize_agents=False)

        run = subprocess.run(
            [
                sys.executable,
                str(MODULE),
                "--config",
                str(config_path),
                "--dry-run",
                "--preset",
                "haiku-main",
                "claude",
            ],
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "AGENT_BIOS_PRIVATE_INSTRUCTIONS": "0",
                "AGENT_BIOS_SESSION_DISTILL_STATE": str(temporary / "session-distill-state.json"),
                "HOME": str(temporary / "home"),
                "XDG_CACHE_HOME": str(temporary / "cache"),
                "XDG_CONFIG_HOME": str(temporary / "config"),
            },
        )
        assert run.returncode == 0, run.stderr + run.stdout
        argv = json.loads(run.stdout.splitlines()[-1])
        assert "--effort" not in argv
        assert "--agents" not in argv
        assert "--restricted" in argv
        assert "--strict-mcp-config" in argv
        assert json.loads(find_option(argv, "--mcp-config")) == {"mcpServers": {}}
        assert "--dangerously-skip-permissions" not in argv
        assert "None" not in run.stdout

    print("OK: tier effort projection, omission, validation, and save/reload paths")
    return 0


def main() -> int:
    with legacy_host_environment(ROOT):
        return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
