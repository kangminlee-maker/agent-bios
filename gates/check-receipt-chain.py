#!/usr/bin/env python3
"""Gate: the receipt chain, over a space DERIVED from the config rather than listed.

The chain — dispatch, emit, fold, adjudicate — was first proven by hand: someone picked
a preset, read the seat off a dry-run, ran three passes, folded them and read the
verdict. Everything in that sentence that a person chose is a place coverage can rot,
and a hand-listed scenario stays green while the config grows past it.

So nothing here is chosen. The presets and hosts come from the config, the plan comes
from the real launcher, and the SEAT each adapter is pinned to comes from the plan the
launcher just projected. Add a preset and this widens by itself.

What is asserted is a property, not a value: for every selected method a receipt CAN be
produced for, the chain must end in that method being credited. The refusal paths — wrong
seat, short passes, reused id, empty result — are negative-controlled next door in
`gates/check_parity.py::launcher_receipts` and `::launcher_receipt_adapters`; duplicating
them here would buy nothing. What this adds is the space.

Two modes:

  (default)  fixture native backends and a stub adapter pinned to the plan's seat.
             No network, no spend; reported adapter coverage describes the fixture.
  --real     the command the plan actually names. Costs a live dispatch per cell, so it
             is never run by the umbrella. Cells whose dispatch command is not a
             receipt-emitting adapter are REPORTED as unchainable, not failed — that gap
             is the routing decision, not a defect.

  --self-test   plant a wrong seat and a short pass count and prove each is refused,
                prove the cell set is non-empty, and force each failure-reporting path
                (launcher exit, unparsable projection, lost ReviewPlan, uncredited
                cell) to prove the gate says so; exits 0 only if all hold.
"""
import argparse
import contextlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import tomllib

from launcher_fixture_env import launcher_environment

REPO = pathlib.Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "launch" / "agent-launch.py"
# The repo's own profile, pinned: a deployed profiles.toml would make this gate's space
# depend on what the machine happens to have installed.
PROFILE = REPO / "launch" / "agent-launch.toml"
PACKET = "the review packet this cell fed its reviewer\n"
# A value no emitted receipt can hold, so the "produced in the main session's own
# context" refusal is present in every cell rather than inert.
MAIN_DISPATCH = "not-a-dispatch-main-session"

STUB = """#!/usr/bin/env bash
set -euo pipefail
seat="$1"; shift
packet=$(mktemp); result=$(mktemp)
cat > "$packet"
# Distinct per invocation, because `passes` counts DISTINCT result hashes: a stub that
# answered identically would collapse three passes into one and fail for a reason that
# has nothing to do with the space under test.
printf 'REVIEW from pass %s: no findings\\n' "$$" | tee "$result"
"{python}" "{launcher}" --emit-receipt "${{REVIEW_METHOD_ID:-}}" "$seat" 0 "$packet" "$result" >/dev/null
"""


def launcher_module():
    spec = importlib.util.spec_from_file_location("agent_launch", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_launch"] = module
    spec.loader.exec_module(module)
    return module


def _contract_plan(al, argv):
    """The ReviewPlan the launcher just rendered, out of the argv it would have exec'd.

    Two carriers, because the hosts differ: Claude passes the contract as a plain
    argument, Codex embeds it in a TOML assignment where the JSON is escaped. A real
    TOML parser undoes the second — hand-unescaping it is how the first attempt at this
    silently produced no plan for half the matrix."""
    for element in argv:
        if "ReviewPlan/v1" not in element:
            continue
        report = al.extract_review_plan_v1(element)
        if report:
            return report
        try:
            value = next(iter(tomllib.loads(element).values()))
        except (tomllib.TOMLDecodeError, StopIteration, AttributeError):
            continue
        report = al.extract_review_plan_v1(value)
        if report:
            return report
    return None


def rendered_plans(al, config):
    """{(preset, host): ReviewReport} — every combination the config declares.

    A preset carrying no `review` block is on the legacy route and renders no plan; that
    is a configuration, not a defect, so it contributes no cells and is reported. Which
    presets those are is read from the config rather than named here — listing them
    would be the same hand-authored space this gate exists to remove, and a composable
    preset that silently stopped rendering would have been absorbed by the list."""
    plans, failures, planless = {}, [], []
    hosts = sorted(config.get("backends", {}))
    presets = sorted(config.get("presets", {}))
    for preset in presets:
        composable = isinstance(config["presets"][preset].get("review"), dict)
        for host in hosts:
            done = subprocess.run(
                [sys.executable, str(LAUNCHER), "--config", str(PROFILE),
                 "--preset", preset, "--dry-run", host],
                capture_output=True, text=True, cwd=str(REPO),
            )
            if done.returncode != 0:
                failures.append(f"{preset}/{host}: launcher exited {done.returncode}")
                continue
            try:
                argv = json.loads(done.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                failures.append(f"{preset}/{host}: no projection on stdout")
                continue
            report = _contract_plan(al, argv)
            if report is None:
                if composable:
                    failures.append(
                        f"{preset}/{host} declares a review block and rendered no "
                        f"ReviewPlan — the composable route stopped emitting its record"
                    )
                else:
                    planless.append(f"{preset}/{host}")
                continue
            plans[(preset, host)] = report
    return plans, failures, planless, len(presets), len(hosts)


def chain_cells(al, plans, methods):
    """The cells a receipt can actually be produced for, plus what was left out and why.

    Deduped on (method, seat, passes): two presets projecting the same seat run the same
    chain, and running it twice proves nothing the first run did not. The collapse is
    reported rather than silent — a coverage number that hides its own truncation reads
    as more than it is."""
    cells, skipped, seen = {}, [], 0
    for (preset, host), report in sorted(plans.items()):
        for row in (report.base, *report.methods):
            if row.status == al.STATUS_DROPPED:
                continue
            seen += 1
            if row.mechanism != al.PANEL_ADAPTER:
                skipped.append((preset, host, row.method_id, row.mechanism))
                continue
            descriptor = methods.get(row.method_id)
            if descriptor is None:
                skipped.append((preset, host, row.method_id, "no descriptor"))
                continue
            key = (row.method_id, row.provider, row.model, row.effort, descriptor.trials)
            cells.setdefault(key, []).append((preset, host))
    return cells, skipped, seen


def _write_stub(directory):
    stub = directory / "stub-adapter.sh"
    stub.write_text(STUB.format(python=sys.executable, launcher=LAUNCHER))
    stub.chmod(0o755)
    return stub


def run_cell(al, key, plan_report, workdir, command=None, seat_override=None, passes=None):
    """Dispatch, emit, fold, adjudicate — through the real CLI at every step.

    Returns (credited, detail)."""
    method_id, provider, model, effort, trials = key
    seat = seat_override or f"{provider}:{model}/{effort}"
    runs = trials if passes is None else passes
    receipts = workdir / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    packet = workdir / "packet.txt"
    packet.write_text(PACKET)
    adapter = command or _write_stub(workdir)
    env = {
        **_base_env(),
        al.RECEIPT_DIR_ENV: str(receipts),
        al.RECEIPT_METHOD_ENV: method_id,
        al.RECEIPT_SEED_ENV: f"seed-for-{method_id}",
        al.RECEIPT_SWAP_ENV: f"swap-for-{method_id}",
    }
    for _ in range(runs):
        with packet.open("rb") as handle:
            done = subprocess.run(
                [str(adapter), seat], stdin=handle, capture_output=True, text=True,
                env=env, cwd=str(REPO),
            )
        if done.returncode != 0:
            return False, f"adapter exited {done.returncode}: {done.stderr.strip()[:160]}"

    folded = subprocess.run(
        [sys.executable, str(LAUNCHER), "--fold-receipts", str(receipts),
         str(packet), MAIN_DISPATCH],
        capture_output=True, text=True, cwd=str(REPO),
    )
    if folded.returncode != 0:
        return False, f"fold failed: {folded.stderr.strip()[:160]}"
    bundle = workdir / "bundle.json"
    bundle.write_text(folded.stdout)
    plan_file = workdir / "plan.json"
    plan_file.write_text(json.dumps(al.review_plan_v1(plan_report)))

    verdict = subprocess.run(
        [sys.executable, str(LAUNCHER), "--config", str(PROFILE),
         "--verify-receipts", str(plan_file), str(bundle)],
        capture_output=True, text=True, cwd=str(REPO),
    )
    output = verdict.stdout + verdict.stderr
    if verdict.returncode not in (0, 1):
        return False, f"adjudicator crashed ({verdict.returncode}): {output.strip()[:160]}"
    # Per METHOD, not per bundle: a plan carries reviewers this chain cannot produce a
    # receipt for, so the bundle is legitimately partial and its exit status says so.
    credited = f"{method_id}: ACHIEVED" in output
    reason = next((line.strip() for line in output.splitlines()
                   if line.strip().startswith(f"{method_id}:")), output.strip()[:160])
    return credited, reason


def _base_env():
    import os
    return {k: v for k, v in os.environ.items()}


@contextlib.contextmanager
def _offline_environment(real=False):
    if real:
        yield
        return
    with tempfile.TemporaryDirectory(prefix="receipt-chain-native-inputs-") as directory:
        with launcher_environment(pathlib.Path(directory), REPO):
            yield


def check(real=False):
    with _offline_environment(real):
        return _check(real)


def _check(real=False):
    al = launcher_module()
    config = al.load_config(PROFILE)
    methods = al.load_review_methods(config)
    plans, failures, planless, preset_count, host_count = rendered_plans(al, config)
    if failures:
        return failures, {}
    if not plans:
        return ["no preset/host combination rendered a plan — the check ran over an "
                "empty subject"], {}

    cells, skipped, rows_seen = chain_cells(al, plans, methods)
    if not rows_seen:
        return ["no selected review method in any plan — vacuous"], {}
    if not cells:
        return ["no plan carries a method a receipt can be produced for, so the chain "
                "was never exercised"], {}

    problems, unchainable = [], []
    for key, covering in sorted(cells.items()):
        command = None
        if real:
            host = covering[0][1]
            command = al.host_dispatch_command(host, config)
            if command is None or pathlib.Path(command).name not in ADAPTERS:
                unchainable.append((key[0], covering[0][1], command))
                continue
        with tempfile.TemporaryDirectory(prefix="receipt-chain-") as work:
            credited, reason = run_cell(al, key, plans[covering[0]], pathlib.Path(work),
                                        command=command)
        if not credited:
            problems.append(
                f"{key[0]} on {key[1]}:{key[2]}/{key[3]} "
                f"(covering {', '.join(f'{p}/{h}' for p, h in covering)}) "
                f"was not credited — {reason}"
            )
    summary = {
        "presets": preset_count, "hosts": host_count, "plans": len(plans),
        "rows": rows_seen, "cells": len(cells),
        "collapsed": sum(len(v) for v in cells.values()) - len(cells),
        "skipped": skipped, "unchainable": unchainable, "planless": planless,
        "adapter_backed": _adapter_coverage(al, config),
        "adapter_coverage_source": "deployed" if real else "fixture",
    }
    return problems, summary


ADAPTERS = {"codex-run", "claude-run"}


def _adapter_coverage(al, config):
    """Which hosts' current dispatch resolves to a receipt-emitting adapter.

    Derived, and reported even when everything passes: the stub proves the chain works,
    and the summary labels whether these are fixture or deployed bindings. Fixture
    availability cannot establish that an adapter is deployed on the operator's host."""
    out = {}
    for host in sorted(config.get("backends", {})):
        command = al.host_dispatch_command(host, config)
        name = pathlib.Path(command).name if command else None
        out[host] = (name, bool(name in ADAPTERS))
    return out


def self_test():
    with _offline_environment():
        return _self_test()


def _self_test():
    al = launcher_module()
    config = al.load_config(PROFILE)
    methods = al.load_review_methods(config)
    plans, failures, _, _, _ = rendered_plans(al, config)
    problems = []
    if failures:
        return _report_self_test([f"live tree does not render: {failures[0]}"])
    cells, _, _ = chain_cells(al, plans, methods)
    if not cells:
        return _report_self_test(["no cell derived, so no control means anything"])

    # A multi-pass cell when one exists (the panel always is), else the first: the
    # short-pass control below needs passes > 1 to have anything to withhold, and the
    # blind first cell became a one-pass method when the deep reviewers were renamed.
    key = next((k for k in sorted(cells) if k[4] > 1), sorted(cells)[0])
    covering = cells[key][0]

    with tempfile.TemporaryDirectory(prefix="receipt-chain-st-") as work:
        credited, reason = run_cell(al, key, plans[covering], pathlib.Path(work))
    if not credited:
        problems.append(f"the positive control was not credited: {reason}")

    with tempfile.TemporaryDirectory(prefix="receipt-chain-st-") as work:
        credited, reason = run_cell(al, key, plans[covering], pathlib.Path(work),
                                    seat_override="openai:not-the-projected-model/low")
    if credited:
        problems.append("a receipt naming a seat the plan never projected was credited")

    if key[4] > 1:
        with tempfile.TemporaryDirectory(prefix="receipt-chain-st-") as work:
            credited, _ = run_cell(al, key, plans[covering], pathlib.Path(work),
                                   passes=key[4] - 1)
        if credited:
            problems.append("a method evidencing fewer passes than requested was credited")
    else:
        problems.append("the first cell asks for one pass, so the short-pass control "
                        "cannot fire — pick a multi-pass method")

    # -- reporting-path controls. The three controls above prove the CHAIN can refuse;
    # none of them proves the gate SAYS so. Every append below was measured as a
    # control-audit survivor: delete it and the self-test stayed green while the gate
    # went silent on exactly the failure it exists to surface. Each control forces one
    # path with a stub and asserts the specific message, so neutering that one append
    # is what the control notices.
    import types

    probe_cfg = {"backends": {"codex": {}}, "presets": {"probe": {"review": {}}}}

    def forced(stdout, returncode=0):
        def fake_run(*_a, **_k):
            return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
        return fake_run

    real_subprocess_run = subprocess.run
    for stub, expect, label in (
        (forced("", returncode=7), "launcher exited",
         "a launcher failure is reported, not swallowed"),
        (forced("this is not a projection"), "no projection",
         "a projection that does not parse is reported"),
        (forced('["codex", "exec"]'), "rendered no",
         "a composable preset that lost its ReviewPlan is reported"),
    ):
        subprocess.run = stub
        try:
            _, fails, _, _, _ = rendered_plans(al, probe_cfg)
        finally:
            subprocess.run = real_subprocess_run
        if not any(expect in f for f in fails):
            problems.append(f"{label} — forced the path, gate stayed silent "
                            f"(wanted {expect!r} in {fails!r})")

    # The main verdict itself: an uncredited cell must reach the report. run_cell is
    # forced to refuse, so check() judging the real tree must name every cell.
    globals_ref = globals()
    real_run_cell = globals_ref["run_cell"]
    globals_ref["run_cell"] = lambda *a, **k: (False, "forced by control")
    try:
        chain_problems, _ = check()
    finally:
        globals_ref["run_cell"] = real_run_cell
    # Every derived cell, not any: a regression that reports only the first refused
    # cell — or drops one cell's diagnostic — kept this green under `any`. The cell set
    # here is the same derivation check() performs, so identity comparison is exact.
    unreported = [key for key in cells
                  if not any(f"{key[0]} on {key[1]}:{key[2]}/{key[3]}" in p
                             and "was not credited" in p for p in chain_problems)]
    if unreported:
        problems.append(f"forced every cell to refuse and {len(unreported)} of "
                        f"{len(cells)} never reached the gate's report: "
                        f"{sorted(unreported)[:2]}")

    return _report_self_test(problems)


def _report_self_test(problems):
    if problems:
        print("check-receipt-chain --self-test: FAIL")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("check-receipt-chain --self-test: OK (chain credited on the projected seat; "
          "wrong seat and short passes both refused; cell set non-empty; all four "
          "reporting paths speak when forced)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true",
                        help="dispatch the command the plan names; costs a live run per cell")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    problems, summary = check(real=args.real)
    if problems:
        print("check-receipt-chain: FAILED")
        for item in problems:
            print(f"  - {item}")
        return 1
    backed = summary["adapter_backed"]
    print(
        f"check-receipt-chain: OK ({summary['plans']} plans over {summary['presets']} "
        f"presets x {summary['hosts']} hosts; {summary['rows']} selected rows; "
        f"{summary['cells']} chains run, {summary['collapsed']} collapsed as duplicates)"
    )
    if summary["skipped"]:
        kinds = sorted({mech for _, _, _, mech in summary["skipped"]})
        print(f"  not chainable from this side ({len(summary['skipped'])} rows): "
              f"{', '.join(kinds)} — a receipt cannot be produced for them here")
    for host, (name, is_adapter) in sorted(backed.items()):
        if summary["adapter_coverage_source"] == "fixture":
            state = "adapter fixture" if is_adapter else "raw backend fixture"
            print(f"  fixture {host} panel dispatches {name}: {state}")
            continue
        # Routing now PREFERS the adapter, so a raw binary here means the adapter is not
        # deployed on this machine rather than that the launcher does not know about it.
        # Saying which one keeps the line actionable instead of alarming.
        state = ("adapter" if is_adapter
                 else "RAW BINARY — the adapter is not deployed here, so no receipt")
        print(f"  {host} panel dispatches {name}: {state}")
    if summary["unchainable"]:
        print(f"  --real skipped {len(summary['unchainable'])} cell(s) whose dispatch "
              f"command is not a receipt-emitting adapter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
