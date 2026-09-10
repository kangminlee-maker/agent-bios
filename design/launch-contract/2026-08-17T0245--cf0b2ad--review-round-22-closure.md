---
created_at: 2026-08-17T02:45:00+09:00
head: cf0b2ad          # the fix commit this record closes
kind: review
---

# Round 22 — closure

Ten findings, all ten real. Every one was reproduced with the reviewer's own
mutation AND its control before anything was changed, fixed at the authority,
given a named assertion in the check the reviewer named as missing, and then
proven by reverting the fix alone and watching that assertion fail by name. The
revert restored a pristine copy of the FIXED tree afterwards, never an inverse
patch, and each revert refused loudly unless its text matched exactly once.

Twenty reverts for ten findings: where a fix had more than one door, each door
was reverted on its own, and the case it owns is the one that failed. All twenty
fired.

| # | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- |
| 1 | yes | `_row_from_v1` — status set, method id, seat fields, grade | `launcher_receipts` — eight identity mutations on one selected row, each a single field, plus a DROPPED row with null seat fields that must still verify | yes, each of four doors separately |
| 2 | yes | `_merge_method_passes` (control-field presence) | `launcher_receipt_fold` — seed and swap omitted by the later pass and by the earlier one, an empty seed, outcome equality over the reversed pair, and two positive controls | yes |
| 3 | yes | `_receipt_structure_reason`, shared by `_receipt_reason` and `_merge_method_passes` | `launcher_receipts` — `false`, `true` and `"0"` as exit statuses; `launcher_receipt_fold` — a boolean pass | yes, proven in both checks |
| 4 | yes | `select_plan` (`custom_requested or picked_custom`) | `launcher_module_api` — the flag with the picker choosing an ORDINARY preset, and the same run without the flag | yes |
| 5 | yes | `pick_mode_and_preset` (baseline fallback + its refusal) | `launcher_module_api` — a routed-only profile refused by name, a non-routed-only profile still reaching the hub | yes, each half separately |
| 6 | yes | `build_plan` (raw authoring in the plan), `preset_from_plan` (normalization) | `preset_save_round_trips` — the projection on the host the save was NOT made from, over every shipped preset on both hosts, with a non-empty-subject assertion | yes, each half separately |
| 7 | yes | `verify_review_receipts` (identity map + ordered foreign list), return tuple | `launcher_receipts` — a plan row named `<unnamed>` beside an unusable receipt, and the same bundle against an ordinary id | yes, each half separately |
| 8 | yes | `setup_summary_lines` | `launcher_delegation_clause` — the setup panel's child rows and its inactive line, both delegation states, on both hosts | yes, each half separately |
| 9 | yes | `preset_from_plan` (stop filtering), `render_preset_block` (`_table` hoisted over the tier overrides) | `preset_save` — a scalar host block and a scalar tier block, each naming its own entry | yes, each half separately |
| 10 | yes | `render_preset_block` (arm extras), `_emit_arm_table`, `_arm_scalar` | `launcher_review_save` — one arm carrying a scalar field, one carrying a sub-table, each asserted on the RELOADED profile | yes, each half separately |

## Where the fix departs from the reviewer's proposal, and why

- **#2.** The proposal asks for `ordering_seed` and `swap_group` compared by
  "presence/value". Only presence is compared. A swap group names WHICH arm a pass
  ran, so passes differing there is the augmentation working rather than a
  disagreement — and the same function already draws exactly that line for
  `evidence`, where a trace id differs per pass by construction. Presence alone
  buys the property the finding is about: the mixed pair is refused in both
  orders, an agreeing pair folds in both, and a pair where nobody reports leaves
  the folded record silent so the descriptor-aware adjudicator decides, which is
  what `D-20260816-c0067f` and `D-20260816-0ed011` deliberately keep. Recorded as
  `D-20260817-3d6a6e`.
- **#6.** Of the two offered remedies the authoring is normalized into
  `tier_overrides.<host>.frontier.effort` rather than re-emitted. `build_plan`
  refuses a preset that authors both homes to different values, and the save
  already rebuilds the active host's overrides from the plan, so re-emitting would
  let the writer's two outputs contradict each other. Only what differs from that
  host's default is written — the rule the override loop already follows — so no
  shipped preset gains a line. Recorded as `D-20260817-76ecd1`.
- **#6, widened.** The finding names the host MAP. A scalar `frontier_effort`
  loses the same way, on every inactive host at once, and was verified before the
  fix (`source_codex=low saved_codex=max`). One normalization covers both: a twin
  left standing is the same finding with a different key, which is the reason
  round 21 #4 was widened too. Where a source authored both homes for one inactive
  host to different values, the save now refuses by name instead of silently
  keeping one — that value pair is the contradiction `build_plan` itself refuses.
- **#10.** Of the two offered remedies, untouched arms are serialized generically
  and recursively rather than unsupported keys refused. The launcher ACCEPTS such
  a profile and launches it, so refusing at save would make an accepted profile
  unsaveable and the user would meet the refusal only after the launch had
  happened — the objection already recorded as `D-20260816-77afa8`. A named
  refusal is kept for the one case genuinely unwritable, a value with no scalar or
  table form, because the alternative there is dropping it in silence. Recorded as
  `D-20260817-105da4`.
- **#7, beyond the proposal.** Foreign verdicts moved from a label-keyed map into
  an ordered list, so two foreign receipts sharing a label are now two disclosed
  rows rather than one. That follows from the same sentence the fix is made of —
  a receipt silently dropped is a receipt nobody can chase — and it is why the
  rendered order changed: selected rows sorted by method id, then the bundle's own
  diagnoses in arrival order.

## What the reverts taught

- **A check whose failures are named by CASE cannot be graded by the door's
  message.** Two of the twenty reverts were first graded against the text
  `_merge_method_passes` raises, and both came back "fails, but not by name" —
  because `launcher_receipt_fold`'s loop reports a missed refusal as `fold accepted
  a <label>`. The door's message is asserted on the other branch, when the refusal
  DOES fire and has to be the right one. Re-graded against the labels each case
  owns, all six of #2's cases and #3's fold case fired. The grading rule is per
  check, not per repo: a control's needle has to be the text that check emits when
  the door is gone, and reading it off the fix is how a control ends up testing a
  mechanism other than its own.
- **A door reverted alone can be caught by the door beside it, and only ordering
  says which.** #1 is four doors inside one function. The seat door and the grade
  door both sit under `status != STATUS_DROPPED`, and the status door runs first —
  so a row with an unreadable status never reaches either. Reverting them one at a
  time, with a case per field rather than a case per row, is what shows each
  refuses something no other refuses. A single "malformed row" case would have
  passed with three of the four doors deleted.
- **The positive control for a type door is the shape the type door must NOT
  refuse.** #1's seat door binds selectable rows only, and a door that refused
  every null would have satisfied all eight identity cases while making an ordinary
  plan — any preset with one unavailable method — unverifiable. The dropped row
  with null everywhere is added to the same plan, and it must still verify.
- **Two halves of one fix can fail the same assertion and still need separate
  cases.** #10's scalar emission and its recursive sub-table emission both end at
  "the arm came back different". Written as one subject carrying both shapes, either
  revert failed it and neither was distinguishable. Split into two subjects — an arm
  with only a scalar, an arm with only a sub-table — each half fails its own.

## The golden

`gates/goldens/review-matrix.json` did not move, and that is the expected result
rather than a lucky one: no finding touched contract text. Every fix is in a
reader, an adjudicator, a serializer, or a summary renderer. The golden was
re-checked after the fixes and after the new assertions — 121 cells, 0 control
failures — precisely because "the golden is unchanged" is only worth stating when
it was actually run.

## Gates

- `python3 gates/check_parity.py` (venv interpreter) — all 62 checks green, run
  after the fixes and again after every assertion was added.
- `gates/capture-review-goldens.py --check` — 121 cells, 0 control failures.
- `python3 gates/check-lexicon.py` — OK, 315 files.
- `python3 decisions/record-decision.py --check` — OK, 78 records, ids content-bound.
- `python3 ontology/check-ontology.py` — OK, 38 entities, 49 edges.
- `python3 ontology/impact.py --diff` — no open obligation; `NegativeControl` and
  `PresetMode` both moved with their counterparts.
- `python3 gates/control-audit.py` — disclosure only, exit 0. It still reports
  `gates/check_parity.py` as "not audited (python with no --self-test to consult)",
  which is why all twenty controls here were proven by manual revert instead.
- The commit itself ran `check-package.sh` and `check-parity.sh` against the index
  through `.githooks/pre-commit`. That run is the authoritative one.

## One environmental note

The first commit attempt was killed by the harness's own ten-minute command
timeout, not by anything in the repository: `git commit` had reached
`check-parity.sh` when the tool sent SIGTERM. Nothing was left behind — no commit,
the index intact, no gate process surviving, and no `gate-i13-probe.md` in the
source tree, because the hook materialises the index into a temp directory and the
probe belongs to that copy. The commit was re-run detached and took about thirteen
minutes of process time, which is the shape any future run should take: this hook
outlasts a foreground tool call, so it needs a detached run and a wait on its pid.

Two things seen while waiting are worth writing down, because both look like a
collision and neither is one. A second `check-parity.sh` appeared partway through,
running out of the SAME `agent-bios-precommit.*` temp directory as the first: that
is `gates/test-install-guides.sh` driving `install.sh install`, and `install.sh
verify` re-running the parity umbrella inside the tree it just installed
(`install.sh:630-648`). One hook run, nested. And the probe-file race that AGENTS.md
warns about does not apply between two hook runs at all — each materialises the
index into its own temp directory, so `$REPO` and the plant belong to that copy
rather than to the worktree. The `.git` pointer file that vanished during round 21
stayed intact throughout.

## Not reached

The reviewer's own exclusions stand and nothing here touched them:
`compose/corpus-state.py`, the wizard trial-load path, real Textual screen
rendering beyond its pure setup-summary producer, on-disk `save_preset` replacement
and locking beyond what `preset_save`/`preset_save_round_trips` already drive,
filesystem-backed `--emit-receipt`/`--fold-receipts`, host CLI interpretation or
execution, credentials, and any access-control conclusion. The reviewer's three
void readings (execution-clause drift, the repaired `no_review_route` twin, and
all-pass seed/swap omission at fold time) were left alone — the first two were
withdrawn against their own controls, and the third is behaviour two recorded
decisions keep.
