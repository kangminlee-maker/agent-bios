---
created_at: 2026-08-17T00:35:56+09:00
head: f2513a8          # the fix commit this record closes
kind: review
---

# Round 21 — closure

Nine findings, all nine real. Every one was reproduced with the reviewer's own
mutation AND its control before anything was changed, fixed at the authority,
given a named assertion in the check the reviewer named as missing, and then
proven by reverting the fix alone and watching that assertion fail by name. The
revert restored a pristine copy of the FIXED tree afterwards, and each revert
refused loudly unless its text matched exactly once — a silent no-op revert makes
every control look green.

| # | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- |
| 1 | yes | `parse_review_block` (authoring), `verify_review_receipts` (adjudicating) | `launcher_review_schema` — `panel` in the optional method map; `launcher_receipts` — a plan file whose `methods` repeats the base row | yes, each door separately |
| 2 | yes | `_receipt_structure_reason`, shared by `_receipt_reason` and `_merge_method_passes` | `launcher_receipt_fold` — bogus schema in both orders, an unknown key, a non-table pass | yes |
| 3 | yes | `_merge_method_passes` (evidence agreement) | `launcher_receipt_fold` — an empty required value in both orders, plus a positive control that two passes reporting different VALUES still fold | yes |
| 4 | yes | `execution_clause`, used by `run_contract` | `backend_dispatch` — four policy values per host, each read back out of the rendered contract, argv agreement, and pairwise-distinct contracts | yes |
| 5 | yes | `build_plan` (`tier_overrides` in the plan), `preset_from_plan` | `preset_save` — a real `save_preset` + `load_config` round trip, asserted on what the INACTIVE host projects, both directions, with a positive control on the active host's rebuilt block | yes |
| 6 | yes | `_row_from_v1` (row type), `review_plan_from_v1` (`methods` array) | `launcher_receipts` — string base row, string method row, non-array `methods`, null base row, each through the CLI | yes, each door separately |
| 7 | yes | `ReceiptVerdict.selected`, `verify_review_receipts`, `render_receipt_verdicts` | `launcher_receipts` — a foreign receipt ADDED to a complete bundle, asserting the fraction and the disclosure on one run | yes, plus a planted alternative |
| 8 | yes | `no_review_route`, used by `run_contract` and `print_summary` | `launcher_delegation_clause` — the summary's review line for `solo` on both hosts, with a routed positive control and a both-subjects-seen assertion | yes |
| 9 | yes | `canonical_config_key` (segment tuples), `config_key_text`, `overlaps` | `agent_materialization` — the literal quoted dotted key forwards; every-segment-quoted still refused | yes, as one fix |

## Where the fix departs from the reviewer's proposal, and why

- **#2, #3.** The proposal asks for the capability's required-evidence bar on
  every raw pass. Folding is adapter-side and holds no registry, so the only
  place it could learn that bar is the receipts it is folding — the audited party
  declaring its own. That is the objection already recorded for round 20 #2
  (`D-20260816-c0067f`), and it stands. What the fold CAN judge from the group
  alone it now judges on every pass: whether each is a `ReviewReceipt/v1` record
  at all and carries no key the schema has no meaning for, and agreement on which
  evidence fields were reported WITH A VALUE. #3 is the proposal's own "at
  minimum" branch. Recorded as `D-20260816-0ed011`.
- **#7.** Of the two offered remedies, coverage is scoped to selected rows rather
  than the bundle refused: refusing the whole bundle lets one stray file destroy
  the evidence for every method that did verify, and the commonest way to acquire
  one is benign. Recorded as `D-20260816-bf3d08`.
- **#4** is widened rather than narrowed. The proposal names the Claude mode;
  Codex's `codex_execution_policy` had the identical gap, verified before the fix
  (`contract_equal=True` across `bypass` and `read-only`). A twin left standing is
  the same finding with a different key.

## What the reverts taught

- **Reverting a comparison is not reverting the fix when the fix was a TYPE.**
  #9's first revert restored `overlaps` to its string form alone and the control
  PASSED — because `canonical_config_key` still returned tuples, and a tuple `==`
  already separates the literal key from the nested one. The load-bearing half is
  the return type; the prefix comparison is what keeps ancestor and descendant
  collisions firing. Reverted as one fix (three hunks), the control fails by name
  on both new forwards. A control graded against a partial revert would have been
  a control for a fix nobody made.
- **A control whose subject crashes the gate is not failing by name.** With #2
  reverted, the fold's non-table pass raised `AttributeError` out of
  `_merge_method_passes` and aborted `launcher_receipt_fold` mid-run: three
  assertions had reported, and every later one was skipped in silence. The case
  now catches non-`LaunchError` explicitly and says so, matching the shape
  `launcher_review_schema`'s tier rejects already use.
- **Two doors for one finding must each fail on their own case.** #6's row-type
  door and `methods`-array door were reverted separately: the first leaves the
  array case passing (the array door covers it), the second makes the array case
  fail with the ROW door's message. Neither is proved by the other, which is the
  trap round 20 recorded and this is the first case since.
- **The same-name save is the positive control, and it must keep passing.** #5's
  revert fails only the `saveas-<host>` destination; saving back under the SOURCE
  name still round-trips on the reverted code, because that is the one case where
  looking the source up under the destination name finds the right preset. Both
  destinations run in the check for that reason — one fails on revert, the other
  must not, and together they say the fix is scoped to Save As rather than to
  saving.
- **A denominator and a disclosure are different properties, and only a planted
  alternative shows the second is real.** Reverting `render_receipt_verdicts`
  proved the fraction; it says nothing about whether the foreign row still
  prints. Planting the other implementation — foreign verdicts dropped from the
  tuple, which is where the "reject foreign receipts" proposal tends — fired the
  disclosure assertion AND broke two pre-existing scenarios (`unknown-method`,
  `receipt-not-a-table`), which is how the repo's existing dependence on that
  disclosure became visible.

## The golden

#4 adds one sentence to every contract, so `gates/goldens/review-matrix.json`
moved: 182 changed lines over all 91 contract strings the golden holds — the 121
cells include error records that carry no contract, and every string that has one
gained the clause, none was left behind. The recapture was PROVED rather than
trusted: removing exactly one execution clause from each new string reproduces the
previous golden byte for byte, no other field changed, no string gained two
clauses, and `contract` is the only field carrying it. The two clause forms
observed are the two the golden's presets can produce (`bypass` on each host); the
other policy values are covered by `backend_dispatch`, not here, which is why the
golden alone could never have caught this.


## Gates

- `python3 gates/check_parity.py` (venv interpreter) — all 62 checks green, run
  twice: once after the fixes and once after `preset_save`'s control was rewritten
  to go through the real `save_preset` + `load_config` path.
- `gates/capture-review-goldens.py --check` — 121 cells, 0 control failures, after
  the recapture proved above.
- `python3 gates/check-lexicon.py` — OK, 313 files.
- `python3 decisions/record-decision.py --check` — OK, ids content-bound.
- The commit itself ran `check-package.sh` and `check-parity.sh` against the index
  through `.githooks/pre-commit`: `check-package: OK` and `PARITY OK`, exit 0, in
  about sixteen minutes. That run is the authoritative one — a standalone umbrella
  run in this worktree is a different environment, as the incident below records.

## One environmental incident, recorded because it changed how this was verified

A standalone `./gates/check-parity.sh` run in this worktree came back with every
git-reading leg failing on `fatal: not a git repository`: the linked worktree's
`.git` POINTER FILE had been deleted mid-run. Nothing else was lost — the branch,
HEAD, the index and the staged findings file were all intact under
`.git/worktrees/fix-tree` in the primary repository — and the repair is the one
line git would have written:

```
printf 'gitdir: <primary>/.git/worktrees/fix-tree\n' > <worktree>/.git
```

It was NOT reproduced, and it was not conclusively tested either: two standalone
runs of the leg that failed first (`gates/test-install-guides.sh`) were started
and stopped at I7 and I5, both far short of I13 where the original failure
surfaced, with the pointer intact throughout. What is established here is the
repair and the blast radius, not the cause. No gate in this repository was found
that removes `$REPO/.git`, and the two that build repositories at all
(`compose/corpus-state.py`'s fixture, `check-publish.sh`'s self-test) each scrub
the repo-relocating environment first and say why.

Two things about that leg are worth knowing regardless.
`gates/test-install-guides.sh` plants `gate-i13-probe.md` into the REAL source
tree it is run from (`$REPO/claude/skills/<skill>/`) and removes it from an EXIT
trap, so two standalone runs in one tree race on that file and an interrupted one
can leave it behind — check `git status` before staging after any standalone
umbrella run. And a standalone run is not the hook's environment: the hook
materialises the index into a temp directory, so `$REPO` there is that copy and
the plant, the git legs and any `.git` of its own belong to it rather than to the
worktree you are sitting in.

## Not reached

The reviewer's own exclusions stand and nothing here touched them: host CLI
execution, access-control posture, `compose/corpus-state.py`, the wizard trial
load, writable on-disk save/receipt flows, and full TUI operation. The two void
readings (the `--custom` twin and marker recovery) were left alone — the reviewer
withdrew both against their own controls.
