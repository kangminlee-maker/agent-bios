---
created_at: 2026-08-17T05:03:48+09:00
head: d60bbc7          # the fix commit this record closes
kind: review
---

# Round 23 — closure

Five findings, all five real. Every one was reproduced with the reviewer's own
mutation AND its control before anything was changed, fixed at the authority,
given a named assertion in the check the reviewer named as missing, and then
proven by reverting the fix alone and watching that assertion fail by name. The
revert restored a pristine copy of the FIXED tree afterwards, never an inverse
patch, and each revert refused loudly unless its text matched exactly once.

Twelve reverts for five findings — three, one, five, two and one — plus one
planted profile mutation for the denominator. Where a fix had more than one door,
each door was reverted on its own, and only the case it owns failed. All thirteen
fired.

| # | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- |
| 1 | yes | `active_tiers` / `inactive_tiers` / `inactive_tier_reason`, used by `run_contract`, `print_summary`, `setup_summary_lines` | `backend_dispatch` — every advertised tier reconciled against argv over every shipped host/preset cell, per surface, two-sided, plus a non-HELM-main denominator | yes, each of three surfaces separately |
| 2 | yes | `review_plan_from_v1` (header by field name) | `launcher_receipts` — forged availability, non-string availability, unknown `best_grade`, a launch-time `achieved_grade` forged to a real grade | yes |
| 3 | yes | `is_sha256_hex`, used by `verify_review_receipts` (bundle anchor), `_receipt_reason` (result, packet, pass entries) and `_merge_method_passes` (per pass) | `launcher_receipts` — bundle packet, receipt packet, result, uppercase hex, non-hash pass entries; `launcher_receipt_fold` — a non-hash pass in both orders and alone | yes, each of five doors separately |
| 4 | yes | `build_plan` (every launchable host's map entry), `preset_from_plan` (the save's own door) | `preset_save` — four malformed shapes at each door, plus a carried-string assertion and a valid-entry positive control | yes, each door separately |
| 5 | yes | `_toml_scalar` + `_toml_array_value` | `launcher_review_save` — integer, float, array, date/time and array-of-inline-table fields in an untouched inactive arm, each round-tripped through the RELOADED profile | yes |

## Where the fix departs from the reviewer's proposal, and why

- **#1.** The proposal asks for the one active-tier set to be used in "child
  projection" as well. It is not. The active set is `main_tier ∪
  SPAWNABLE_TIERS`; child projection is `SPAWNABLE_TIERS` alone, and the two
  differ whenever the main is itself spawnable — feeding the union into
  `codex_agent_configs` / `claude_agents` would register HELM as a child agent on
  every HELM-main preset, which is the exact misuse the constant was introduced
  to prevent. Single ownership is preserved the other way round: `active_tiers()`
  is COMPUTED from `SPAWNABLE_TIERS`, so a tier that becomes spawnable is
  advertised by the contract and both summaries with nobody editing them, and no
  second list of children exists to drift. Recorded as `D-20260817-4aec19`.
- **#4** takes both offered remedies rather than the "at minimum" one, because
  each catches a case the other cannot: the profile is refused where it is READ,
  and a plan assembled some other way is refused where it is WRITTEN. Their
  scopes are then deliberately different. `build_plan` holds the host's model and
  the effort table, so it owns what an effort IS and asks that of every launchable
  host's entry — the precedent `validate_host_tiers` already sets by checking the
  review host's table beside the launching host's. The save owns only what it can
  serialize, so it refuses a non-string, an empty string or a table by name and
  writes a STRING back as authored even when the reader would refuse it. Asking
  the value question in both places would give one rule two owners. Recorded as
  `D-20260817-25a972`.
- **#1, beyond the proposal.** The trailing row in both summaries is labelled
  `Inactive` rather than `Children` / `Child tiers`. Under delegation-off the
  inactive set really is the children; under delegation-on it is HELM, which is
  precisely not a child, and a label that is right in one branch and wrong in the
  other is the same defect one altitude up. The phrase the existing
  `launcher_delegation_clause` assertions pin — "inactive, not projected because
  delegation is off" — is byte-identical.
- **#3, kept rather than tightened.** The empty-result refusal is left exactly as
  it was and the hash-form refusal added AFTER it, so `result_sha256=""` still
  reads "records an empty result, so nothing was actually reviewed". That is the
  reviewer's own instruction, and it is also the difference between a claim about
  what the reviewer PRODUCED and a claim about the field being a digest.

## What the reverts taught

- **A fix in a shared helper is not one door.** #1 changes one function that
  three surfaces call, and the naive control — "the contract no longer says
  `helm=`" — would have passed with two of the three surfaces still advertising
  HELM. Reconciling each surface against argv SEPARATELY, and naming the surface
  in the failure, is what makes three reverts distinguishable. Each revert fired
  its own surface's two assertions on both hosts — four lines, all naming that
  surface — and left the other two surfaces silent.
- **A tightened predicate breaks its own fixture, and that is the finding.**
  Both receipt checks went red the moment `is_sha256_hex` landed — `"packet"`,
  `"one"`, `"p1"` — and that redness IS the reviewer's point restated by the
  gate: a fixture built from readable placeholders cannot ask whether a purported
  hash is one, whatever else it asserts. Moving them to real digests is not
  incidental cleanup; it is the only way the new cases mean anything, because a
  check whose every subject is a non-hash has no positive control.
- **The denominator assertion is the control for a control.** `backend_dispatch`
  can only see this defect through a cell whose main is not HELM, and exactly one
  shipped preset supplies one. Flipping `fast-batch`'s `main_tier` to `helm` in
  the profile turned every reconciliation green and fired only the denominator
  line — which is the shape of the trap AGENTS.md names: a control that indexes a
  live list stops testing when that list empties, in silence.
- **Two doors for one finding must be reachable independently, or one of them is
  decoration.** #4's save-path door is unreachable from any profile once
  `build_plan` validates the map, so its case had to be a plan whose
  `frontier_effort_authored` was set directly. Written the other way — both cases
  driven from a profile — reverting the save door alone would have changed
  nothing observable, which is round 20's "a guard whose only proof is another
  guard" arriving a fourth time.
- **Scoping a control to the implementation is how a decision gets made by
  accident.** #4's save-door case initially included a non-effort STRING and
  failed, because the save writes such a value back rather than refusing it. The
  fix was not to tighten the save until the case passed: it was to decide who
  owns "is this a real effort", record it, and assert the carrying behaviour
  explicitly. A control written to match whatever the code does would have
  silently given that rule two owners.

## The golden

`gates/goldens/review-matrix.json` moved by exactly two cells — `shipped/fast-batch/claude`
and `shipped/fast-batch/codex` — in one field path, `/projection/contract`. The
recapture was PROVED rather than trusted: applying the intended transformation to
the OLD golden (drop the `helm=` chunk from the tiers list, append the inactive
clause) reproduces the new golden byte for byte across all 91 contract-carrying
cells of the 121; no cell gained the clause twice; no unchanged cell carries it;
and every helm-main cell still lists `helm=`. The 30 cells without a contract
string are error records and were untouched.

## Gates

- `python3 gates/check_parity.py` (venv interpreter) — all 62 checks green, run
  after the fixes and again after every assertion was added.
- `gates/capture-review-goldens.py --check` — 121 cells, 0 control failures,
  after the recapture proved above.
- `python3 gates/check-lexicon.py` — OK, 317 files.
- `python3 decisions/record-decision.py --check` — OK, ids content-bound.
- `python3 ontology/check-ontology.py` — OK, 38 entities, 49 edges.
- `python3 ontology/impact.py --diff` — no open obligation; `Golden`,
  `NegativeControl` and `PresetMode` all moved with their counterparts.
- `python3 gates/control-audit.py` — disclosure only, exit 0. It still reports
  `gates/check_parity.py` as "not audited (python with no --self-test to
  consult)", which is why every control here was proven by manual revert.
- The commit itself ran `check-package.sh` and `check-parity.sh` against the index
  through `.githooks/pre-commit`. That run is the authoritative one, and it was
  started detached: this hook outlasts a foreground tool call, as round 22
  recorded.

## One environmental note

`pgrep -f control-audit.py` in a wait loop matches the wait loop's OWN command
line, so the loop reported the audit as still running after it had exited 0 —
twice, until `ps` showed the only matches were the two waiters. That is the
broad-substring trap AGENTS.md names for destructive scoping, arriving in a
read-only use where it costs time rather than data. The waiters were stopped by
PID.

## Not reached

The reviewer's own exclusions stand and nothing here touched them:
`compose/corpus-state.py`, the wizard trial path, host CLI execution, access
control, writable on-disk `save_preset` beyond what `preset_save` /
`preset_save_round_trips` drive, filesystem-backed receipt emission and folding,
the file-based `--verify-receipts` command beyond the subprocess runs
`launcher_receipts` already makes, and unscripted TUI interaction. The three void
readings were left alone — the reviewer withdrew each against its own control,
and the seed/swap one is behaviour `D-20260816-c0067f`, `D-20260816-0ed011` and
`D-20260817-3d6a6e` deliberately keep.

One consequence of #5 worth stating because nothing gates it: an inactive host's
`tier_overrides.<host>.<tier>.effort` holding a non-string was previously refused
at save by the serializer's inability to write it, and now round-trips. That
refusal was accidental rather than designed — it is the same accident #5 is about
— and the value is refused where it is read, when that host launches. The rule
stays "carried, not re-derived; refused where it is read".
