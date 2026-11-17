---
created_at: 2026-11-04T06:50:00+09:00
head: 487dd16
kind: design
supersedes: null
---

# Every self-test reads the pinned Claude host and S3 seat, so a re-pin edits four places

WP-08 step 6 re-pins the Claude host (A-1, `session-distill/REPIN.md`) from 2.1.304, whose binary is gone, to the
installed version, and moves the S3 seat to `/high` (D-20261103-4b967e). This commit comes before that re-pin's model
calls and makes none. The lead approved it on 2026-11-04 as its own commit.

## The problem

Self-tests wrote `2.1.304` and `claude:claude-sonnet-5-5/xhigh` as literals and joined them to the checkout's
`seats.json`: its pinned flag-set hash, its seat capacity rows, its host allowance. Move the pin and they fail, though
nothing they test has changed. So a re-pin had to edit test code in five modules besides the pin itself.

## What reads the pin now

Each of these takes the version from `seats.json` `hosts.claude.version` and the S3 seat from `stage_seats.S3`, both
through `gate.seats()`:

- `declare.fixture()`: its S3 seat, `hosts.claude`, and the host version of its allowance. The dispatch, views,
  census and stage_read suites all build on this declaration. `declare.py` now imports `gate`, and the self-test's
  local `gate`, the prompting-targets script path, is renamed `targets_gate`.
- `dispatch.py` self-test:
  - the view-window seat and its allowance's host version;
  - the planted pinned-binary path (`_pinned` judges a start of the path `seats.json` pins);
  - the checkout's S3 capacity row. This control now asks that a host-reported capacity exists, not that it equals
    1,000,000. That number was a copy of `seats.json`, and a measured value.
- `views.py`: `fx_seats`' default seat and version, and the BA#1/BB#5 controls.
- `gate.py`:
  - the replayed Claude captures' `call.json` host version. With the old literal, every replay case fails
    PROFILE_INHERITED once the pin moves.
  - the measured-auxiliary control.
- `wrappers/claude_hermetic_evidence.py`: the three needles name the measured versions as `RECORD_KINDS` lists them.
- `gates/check_parity.py` `claude_run_hermetic`: its fake host answers as the pinned version, and so do the calls
  and `call.json` the leg builds. The version is now written in one line only: the pin check itself.
- Prose: the `wrappers/claude-run.sh` header no longer names a version, and REPIN.md step 6 lists the parity line.

## What a re-pin edits

1. `session-distill/seats.json`: version, path, allowance, capacity rows.
2. `RECORD_KINDS` in the evidence helper.
3. The pin line in `gates/check_parity.py`.
4. `DEPENDENCIES.md`.

The S3 seat moving to `/high` is a one-off design change, not part of a re-pin. It also edits `design_4` in
`dispatch.py`: the control that holds `stage_seats` to design §4 keeps its own copy of that table on purpose.

## Evidence

The pretrial `c6pre-pretrial-1` (development tool, not committed) ran each suite in a disposable committed copy:

- the suites: declare, views, dispatch, gate, census, stage_read, the evidence helper, and
  `check_parity.py --only claude_run`;
- fake env, own TMPDIR under `/tmp`, no model call.

The three sets:

- **This tree:** all 8 pass.
- **This tree with a simulated re-pin to 2.1.317:** the four places above plus the S3 move. All 8 pass.
- **The same simulated re-pin over HEAD (this change reverted):** 5 of 6 fail.
  - views: CAPACITY_UNDECLARED for the fixture's `/xhigh` seat, raised before any control.
  - dispatch: DECLARATION_INVALID, because the allowance's flag-set hash comes back None.
  - gate: 30 FAIL lines (the replay cases, PROFILE_INHERITED).
  - evidence helper: 3 needles.
  - parity `claude_run`: 2 PROFILE_INHERITED.
  - The sixth, declare's own suite, passes on HEAD. It joins nothing to the pin. Its fixture is what the others
    failed on.

## Found, not changed

`wrappers/claude_hermetic_evidence.py --self-test` is not run by the umbrella. `gates/check-parity.sh`,
`gates/check_parity.py` and `gates/run-legs.py` hold no call of it. `check_parity.py`'s `claude_run` exercises the
helper through the adapter. REPIN.md step 7 says the parity gate runs the helper's self-test. Reported to the lead.

## Supplement to the 5b record

This adds to `2026-11-04T0700--3da448e--s3-reads-units-side-by-side-and-leaves-the-bytes-one-at-a-time-leaves.md`,
which is not edited.

The thirteen-party barrier in `jobs: twelve at a time runs twelve independent items at once and never a thirteenth`
fails safe in one direction only:

- A false failure of the gate cannot happen. Twelve workers can never pass a thirteen-party barrier.
- A broken worker cap can pass. If 13 workers really exist, but heavy load keeps the thirteenth from arriving within
  the 2 s wait, the barrier breaks as if only twelve existed, and a revert of the cap survives that run.
