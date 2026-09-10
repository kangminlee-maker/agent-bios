---
created_at: 2026-08-16T22:20:06+09:00
head: 68bb011          # the fix commit this record closes
kind: review
---

# Round 20 — closure

Every finding was reproduced with the reviewer's own mutation and control before
anything was changed, fixed at the authority, given a named assertion in the
check the reviewer named as missing, and then proven by reverting the fix alone
and watching that assertion fail by name. The revert used a pristine snapshot of
the fixed tree and restored by copy, never by inverse patch: an inverse patch
that fails to match leaves a half-reverted tree, and the control is then graded
against a state nobody inspected.

| # | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- |
| 1 | yes | `verify_review_receipts` (bundle anchors), `_receipt_reason` (receipt packet hash) | `launcher_receipts` — `no-main-dispatch-id`, `empty-main-dispatch-id`, `no-bundle-packet`, `receipt-no-packet` | yes, each hunk separately |
| 2 | yes | `_merge_method_passes` | `launcher_receipt_fold` — singleton cases, both orders of the empty pair, evidence-field agreement, outcome equality over the reversed pair | yes, each of three hunks separately |
| 3 | yes | `_row_from_v1`, `verify_review_receipts` (comparison) | `launcher_receipts` — nulled plan through the CLI, plus the comparison reached directly | yes, each hunk separately |
| 4 | yes | `canonical_config_key`, used by `config_pairs` | `agent_materialization` — four spellings with whitespace, a quoted key, a spaced dotted key, and a non-colliding key in the whitespace spelling that must still forward | yes |
| 5 | yes | `run_contract` (structural), `render_review_method` (rendered row), `build_plan` (trigger), all through `refuse_plan_marker` | `launcher_review_contract` — three cases, each asserting its OWN door's message | yes, each door separately |
| 6 | yes | `render_preset_block` | `launcher_review_save` — a real save/reload round trip asserted on the reloaded profile | yes |
| 7 | yes | `LAUNCH_HOSTS` + `launchable_hosts`, used by `build_plan` and argparse | `profile_errors` — the override with the fake host table, plus a positive control keyed on the real host beside the same table | yes |
| 8 | yes | `print_summary` | `launcher_delegation_clause` — the summary compared by line prefix, not by model name | yes, each hunk separately |

## Where the fix departs from the reviewer's proposal, and why

- **#2.** The proposal asks for the seed, swap and evidence *requirements* per
  pass. Those come from the descriptor, and folding is adapter-side with no
  registry — the only place it could learn a method's required controls is the
  receipts it is folding, which is the audited party declaring its own bar. The
  fold now judges everything observable from the group itself (identity, a
  non-empty result, a readable evidence table, and agreement on which evidence
  FIELDS were reported); the descriptor's bars stay on the adjudicated record,
  where the registry is in hand. Recorded as `D-20260816-c0067f`.
- **#6.** Of the two offered remedies, the parent table is emitted rather than a
  base-less arm refused: the launcher accepts such a profile, so refusing at save
  would make an accepted profile unsaveable — and the user would meet that
  refusal only after the launch had already happened. Recorded as
  `D-20260816-77afa8`.
- **#7.** The proposal says "all host-keyed preset maps". `parse_review_arms` was
  changed the same way and then reverted: its single caller always passes the
  selected host, which argparse has already constrained, so the tightening was
  code nothing could reach. Making it fire would mean validating every arm key
  rather than the selected one, which reverses a deliberate design (an arm naming
  a host this config lacks is that host's problem) — a decision, not a fix.
  Recorded as `D-20260816-0f72a5`.
- **#5.** Both halves of the proposal are taken, and the structural half is the
  mechanism: `run_contract` asserts that the canonical record is the only marker
  in the contract, so the next authored field is covered without anyone listing
  it. The field doors are kept for their diagnoses. Recorded as `D-20260816-a49423`.

## Two things the controls taught, which are worth more than the fixes

- **A shared needle grades every door on whichever one fires first.** The three
  #5 cases initially asserted only that *some* refusal mentioned the canonical
  record. All three passed with the method-id door deleted and with the trigger
  door deleted, because the structural door caught them — the control tested a
  mechanism other than the one it was written against. Each case now asserts the
  message of its own door, and each door fails its own case on revert.
- **A guard whose only proof is another guard is untested.** Reverting the
  unconditional controls comparison (#3) changed nothing observable: the row door
  added in the same fix refuses a null before the comparison is reached. The
  comparison is now asserted directly, on a report built in process — the shape
  `check_adapter_command` actually produces — so both halves fail on their own.

## Deliberately not changed

- The formatted-body marker check was briefly folded into the rendered-row check
  and put back: `review_method_registry`'s smuggled-marker control asserts that a
  marker arriving through a *slot value* is refused by the body guard and says
  "one of its slot values carries the marker". That is a different diagnosis from
  the method id's, and the repo had already decided it is worth having. The two
  doors now sit one after the other, each with its own control.
- Per-pass evidence *requirements* at fold time (see #2 above).
- Validating every review-arm host key rather than the selected one (see #7).

## Gates

- `gates/capture-review-goldens.py --check` — 121 cells, 0 control failures. This
  is what proves the `run_contract` restructure moved no contract text: the
  record is now spliced between two separately-asserted spans, and the bytes are
  identical.
- `python3 gates/check_parity.py` (venv interpreter) — all 62 checks green.
- `./gates/check-parity.sh` — PARITY OK, exit 0, 20m32s.
- `python3 gates/check-lexicon.py` — OK, 311 files.
- `python3 decisions/record-decision.py --check` — OK, 73 records, ids content-bound.
- `python3 gates/control-audit.py` — disclosure only, exit 0. It does not audit
  `check_parity.py` (no `--self-test` to consult), which is why every control
  here was proven by manual revert instead.
- The commit itself ran `check-package.sh` and `check-parity.sh` against the
  index through `.githooks/pre-commit`.

## Not reached

The reviewer's own exclusions stand: `compose/corpus-state.py`, the wizard trial
path, persistent on-disk save/reload beyond the deterministic renderer, full TUI
operation, real backend dispatch, and the permission/credential surfaces. Nothing
here touched them.
