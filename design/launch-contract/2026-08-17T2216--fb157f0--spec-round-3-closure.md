---
created_at: 2026-08-17T22:16:00+09:00
head: fb157f0          # the fix commit this record closes
kind: review
supersedes: 2026-08-17T2101--a2f061f--spec-round-3-findings.md
---

# Spec round 3 — closure

The third round under the invariants instrument (`D-20260817-2284a1`), against the
second revision `…T2012--9c1dad6--review-evidence-invariants.md`. Six code findings,
and **all six were real** — every one reproduced with the reviewer's own mutation
AND its control before anything was changed, fixed where the invariant is owned,
given an assertion in the check the reviewer named as missing, and then proven by
reverting that fix alone and watching the assertion fail by name.

**One shape, five times, and it is not round 2's.** Round 2's shape was a rule
implemented twice where the copy nobody re-read was the lenient one. This round's is
a door that **enumerated what a launch writes and admitted everything it does not**.
A DROPPED row's grade was closed against the four ladder values and open to every
other string. A row's `detail` and `instruction` were closed by NAME in
`REVIEW_ROW_KEYS` and never by type. Two empty control tables satisfied an equality
and then defaulted to one requested pass. The evidence comparison was skipped
entirely when the caller supplied no map. And `run_contract`'s structural marker
assertion — written precisely to "assert the property instead of the list" — asserts
the text before and after the canonical record and excludes the record's own span,
which is where an offer's evidence name landed.

The sixth is a different miss and worth naming separately: S4's tier-override
emitter was a flat loop where the review arms had already been given a recursive
one, so "verbatim carry has no depth limit" was true of one half of the save and
false of the other.

**A refusal that becomes the violation.** L1's fix exposed a second defect nobody
raised. `refuse_plan_marker` quoted the marker to be helpful, and a malformed
capability block does not refuse a launch — it DROPS its method, and the drop's
reason is rendered as that row's `detail`. So the refusal put a second marker in the
contract and the prose door then refused the launch naming a door that had nothing
to do with the cause. A message about a forbidden token may not carry it
(`D-20260817-6e5b0f`).

| # | Invariant | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- | --- |
| 1 | V2 | yes | `verify_review_receipts` — `required_evidence` loses its default and a non-map is refused by name; the `if required_evidence is not None:` wrapper gone | `launcher_receipts` — an adjudication supplied no declarations at all, needled on `the drift comparison is unconditional`, with the same receipt + agreeing map as its positive control | yes |
| 2 | V3 | yes | `controls_snapshot_reason` (+ `CONTROLS_KEYS`, `controls_value_reason`), called by `_row_from_v1` and by `verify_review_receipts` for BOTH the row's snapshot and the descriptor's declaration; `_receipt_reason` indexes `controls["trials"]`/`["order"]`/`["swap_augmentation"]` | `launcher_receipts` — four in-process cases on one helper: a None snapshot, an empty snapshot against an empty declaration, an empty registry declaration, and a drifted registry with both sides legal; matching controls verify | yes, each door separately; the no-default reads are behaviour-preserving and have no control |
| 3 | L1 | yes | `refuse_evidence_marker`, called by `parse_capability_offers` and `_row_from_v1`; `refuse_plan_marker` no longer reproduces the marker; `run_contract` asserts the record span's own marker count | `launcher_review_contract` — the offer's door asserted on the PLAN (dropped, entry named, refusal marker-free) so the backstop cannot grade it; a separate in-process case for the record span; `launcher_receipts` — a plan row whose evidence name carries the marker | yes, all four halves separately |
| 4 | L2 | yes | `_row_from_v1` — `detail` and `instruction` required to be strings | `launcher_receipts` — one plan-row case each, because a door asking only about `detail` leaves its twin open | yes, both cases fire on one revert |
| 5 | L3 | yes | `_row_from_v1` — a second door refusing every DROPPED grade outside `{None, GRADE_NOT_REVIEW}` | `launcher_receipts` — `dropped row carrying an invented grade`, needled apart from the ladder door's `bought no independence`, with round 24's `NOT_REVIEW` positive control unchanged | yes |
| 6 | S4 | yes | `render_preset_block` — inactive tier overrides go through `_emit_arm_table`, the same recursive emitter the review arms use | `preset_save` — a nested override round-tripped through `tomllib`, and an unwritable one refused naming `tier_overrides.claude.workhorse.future.deep` | yes, both halves fire on one revert |

## Where the fix departs from the reviewer's proposal, and why

- **#1 (V2).** The reviewer asked that `None` be treated as an absent declaration
  and refused. Taking it literally means the parameter's DEFAULT is the hazard, so
  it is gone: omission is now a `TypeError` at every call site and an explicit
  `None` gets its own named refusal, distinct from the per-row door's. That reverses
  half of `D-20260817-aefcea`, which had decided `None` means "no second view was
  recomputed, so the row's snapshot stands". The cost is stated rather than hidden:
  round 24's control "which bar adjudicates, reached where no second view exists"
  **loses its subject**, because the snapshot and the declaration are now proven
  equal before either is read. It is re-aimed at what stays observable — that a
  declared evidence field is demanded of the receipt — and the whole-map refusal is
  asserted on its own beside it. Recorded as `D-20260817-cf7ade`.
- **#2 (V3).** The reviewer proposed validating both sides against `CONTROLS_KEYS`
  and `controls_value_reason` at the adjudicator. Doing that literally would have
  written the key-set rule a third time, which is the defect one round earlier, so
  `controls_snapshot_reason` owns the whole grammar and the parser calls it too. It
  returns a FRAGMENT: `_row_from_v1`'s four messages are byte-identical to before,
  so round 2's six plan-row controls keep their needles, and the parser's
  `— re-launch` tail — which the adjudicator never appends — is what keeps the two
  doors' needles apart. Recorded as `D-20260817-8ce2c3`.
- **#3 (L1).** The reviewer asked for "one shared evidence-name validator (incl.
  `refuse_plan_marker`)". The shared function owns the MARKER only. The SHAPE means
  different things at the two sites — an offer's is an authoring error carrying its
  own hint, a row's is a record no launch wrote — and unifying it would have
  rewritten a message the gate asserts and collapsed two needles into one. Same
  decision, `D-20260817-8ce2c3`. Two additions the finding did not ask for: the
  refusal message stops reproducing the marker (`D-20260817-6e5b0f`, above), and
  `run_contract` asserts the record span's own marker count
  (`D-20260817-aa0d86`) — the pair of doors beside it already claims to assert the
  property rather than the list, and the record's span was the hole in that claim.
- **#5 (L3).** The reviewer proposed one door refusing every grade outside the two
  permitted values. Kept as two: the ladder refusal is round 24's, with a case
  needled on `bought no independence`, and collapsing them would have left that case
  grading a message nothing emits. Recorded as `D-20260817-a0738e`.
- **#6 (S4).** Both halves in one edit rather than a refusal path beside the
  emitter: `_emit_arm_table` already gives every leaf `_toml_key` and every leaf
  value `_arm_scalar`, so the nested value becomes saveable and the genuinely
  unwritable one is refused by its path in the same change.

## What the reverts taught

- **A backstop grades the door it backs up.** The offer-door case first rendered the
  contract, and with that door reverted the record-span assertion refused the launch
  — so the case failed on the backstop's message while asserting the offer door's
  needle was absent. The case now asserts on the PLAN (`build_plan` only) and leaves
  rendering to the control, which is the only arrangement where each of the two
  doors can be reverted alone.
- **A refusal whose message reaches the artifact needs a control of its own.** The
  same case gained a third assertion — that the refusal text does not itself carry
  the marker — and reverting the message rewording alone fires it. Without that
  assertion the rewording was a change nothing tested.
- **A fix can delete a control's subject, and that has to be said out loud.** V2
  made round 24's "no second view exists" case unreachable: the parameter it was
  built on is no longer legal. Silently leaving it would have left a control that
  passes because its premise is impossible.
- **A behaviour-preserving half has no revert.** Restoring `controls.get("trials", 1)`
  and its two siblings leaves every check green, correctly: with both grammar doors
  ahead of them the four keys are always present, so the indexing is a statement of
  the rule at the point of use and not an additional bar. Recorded rather than
  claimed as proven.
- **An over-broad revert names the wrong door.** The record-span revert had to be cut
  to the exact block; taken to the next `return` it removed the contract's assembly
  and every case in the check failed at once.

## Spec amendments proposed

The reviewer raised two specification defects. They are **not** applied here — the
spec is a dated record and the main session owns its revision. Exact replacement
sentences:

**1. D6's "present iff declared" contradicts its own checklist.** Probed both ways
before choosing. Current behaviour, in process on the fixed tree:

```text
undeclared ordering_seed AND swap_group present, order=fixed  -> ('complete', True, 'verified')
no markers at all,                               order=fixed  -> ('complete', True, 'verified')
declared and present,                       order=randomized  -> ('complete', True, 'verified')
declared and ABSENT,                        order=randomized  -> ('none', False, 'omits the ordering seed its randomized order requires…')
```

Only the declared-and-absent case refuses: the code implements **required when
declared, extras ignored**. That is the reading the decided posture supports.
`D-20260816-c0067f` and `D-20260816-0ed011` put descriptor-owned bars at
adjudication because the fold holds no registry, and `D-20260817-3d6a6e` fixed the
fold's bar at *presence agreement across passes* — never at a value, and never at
absence. A bar on an EXTRA marker would be a bar the descriptor never declared:
core would be asserting something about an adapter's reporting habits (an adapter
that always emits a seed would become unusable with every fixed-order method) rather
than about the review. It is also how `evidence` is already treated one clause
earlier — required fields demanded, extra reported fields ignored — so requiring
absence here would make one sentence say two things. In §2, Dispatch-time, D6
currently reads:

> - **D6 — Evidence and control markers.** `evidence` a table when present; every
>   snapshot-required field carries a truthy value; `ordering_seed` present iff the declared
>   order is randomized, `swap_group` iff swap declared — each bar applied only where the
>   descriptor declared it. A missing offer and a real empty-evidence offer are distinct
>   states; absence is not an empty declaration (`select_capability_offer` +
>   `registered_capability`, one selector for launch and verification, the per-row
>   `required_evidence` recorded even when empty, no-match refused; spec round 2).

Replace with:

> - **D6 — Evidence and control markers.** `evidence` a table when present; every
>   snapshot-required field carries a truthy value; `ordering_seed` REQUIRED WHEN the declared
>   order is randomized, `swap_group` when swap is declared — each bar applied only where the
>   descriptor declared it, and **only as a requirement**: a marker present where nothing
>   declared it is ignored, exactly as an evidence field reported beyond the declared set is,
>   because a bar on an extra is a bar no descriptor wrote and the fold's own rule is presence
>   AGREEMENT across passes rather than absence (D-20260816-c0067f, -0ed011,
>   D-20260817-3d6a6e; spec round 3). A missing offer and a real empty-evidence offer are
>   distinct states; absence is not an empty declaration (`select_capability_offer` +
>   `registered_capability`, one selector for launch and verification, the per-row
>   `required_evidence` recorded even when empty, no-match refused; spec round 2).

…and the checklist line for D6 (§5, Dispatch) stays as written — "a control marker
demanded where never declared" is now the whole of D6's marker rule, so the
checklist and the invariant agree.

**2. S1 does not define NaN semantic identity.** Probed against the code rather than
decided in the abstract:

```text
parsed  -nan: sign=-1 self_equal=False repr=nan
parsed   nan: sign=+1 self_equal=False repr=nan
_toml_scalar(-nan) = nan          _toml_scalar(nan) = nan
re-read sign after save: +1
the comparator's test, repr(-nan) == repr(nan): True
```

The serializer spells every NaN `nan` (`_toml_scalar` uses `repr`, and CPython's
`repr` carries no sign for NaN), and the comparator that guards the round trip
compares `repr` for exactly the reason the sign question raises — `nan != nan`, so a
value comparison would call the one spelling this is about unequal to itself. Both
sides therefore implement **sign-ignoring, all-NaNs-equal** identity, and the
observed `-nan` → `nan` save is COMPLIANT under it. In §2, Save-time, S1's
parenthetical currently reads:

> …and semantic identity is recursive and type-aware (array order significant, table order
> not; NaN/infinities/datetimes compare as parsed values — GPT).

Replace with:

> …and semantic identity is recursive and type-aware (array order significant, table order
> not; infinities and datetimes compare as parsed values; **all NaNs are one value —
> sign ignored, and a NaN equal to itself** — which is what `_toml_scalar`'s `repr`
> spelling writes and what the round-trip comparator's `repr` test asks, since a value
> comparison would call the one spelling this clause is about unequal to itself. A
> `-nan` saved as `nan` is compliant; spec round 3).

## Void, and unchanged

- The reviewer's three void readings stay void and nothing here touches them: D6's
  undeclared control markers (now answered by the amendment above rather than by
  code), F2's falsey `ordering_seed` on one pass, S3's active-host raw effort
  conflict.
- Q1–Q9 are unchanged. D4's retention half (Q3), L5's main-seat serialization (Q2),
  and Q4/Q5 are untouched.

## Verification

- `gates/check_parity.py` (the runtime-projection module, 62 checks): green.
- `gates/capture-review-goldens.py --check`: green with **no re-capture** — 121
  cells, 0 control failures; none of the six fixes changes rendered contract text on
  any shipped route. `--self-test`: 10 controls each proven to fire.
- `ontology/check-ontology.py`: OK (38 entities, 49 edges, 9 kinds).
- `decisions/record-decision.py --check`: OK.
- `gates/check-lexicon.py`: OK (329 files scanned).
- `--dry-run` on both hosts with `--config launch/agent-launch.toml`: exit 0.
- Eleven reverts, each cut from a pristine copy of the FIXED tree, never an inverse
  patch, each refusing unless its text matched exactly once. Ten failed by name; the
  eleventh is recorded above as having no control.
- The full umbrella (`.githooks/pre-commit`) ran on the index for both commits.

## Left open

- Nothing from the six findings.
- **A contract for in-process callers, extended.** Round 2 left "a `ReviewReport`
  handed to `verify_review_receipts` must name its base `panel`". It now must also
  carry a complete controls snapshot on every selectable row, and its caller must
  supply an evidence declaration per selected row. True of every caller in the tree;
  a new obligation on anyone building a report by hand.
- **The record-span backstop's subjects are not enumerated.** Its control reaches it
  in process, past every authored-value door, because that is what the next such
  field will look like. Which of the record's other string fields — `provider`,
  `model`, `effort`, `mechanism` — can carry the marker without some prose door
  catching it first was NOT determined; the backstop is written as a property
  precisely so that question does not have to be answered again each time the record
  gains a field. Its silence is not evidence that no other field can reach it.
