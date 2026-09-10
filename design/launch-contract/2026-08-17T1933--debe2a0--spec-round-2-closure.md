---
created_at: 2026-08-17T19:33:52+09:00
head: debe2a0          # the fix commit this record closes
kind: review
supersedes: 2026-08-17T1802--e42c905--spec-round-2-findings.md
---

# Spec round 2 — closure

The second round under the invariants instrument (`D-20260817-2284a1`), against the
revision `…T1720--4e59154--review-evidence-invariants.md`. Six code findings, and
**all six were real** — every one reproduced with the reviewer's own mutation AND
its control before anything was changed, fixed where the invariant is owned, given
an assertion in the check the reviewer named as missing, and then proven by
reverting that fix alone and watching the assertion fail by name.

**One shape, six times.** Every finding is a rule this system states once and
implements twice, where the copy nobody re-read admitted what the other refused:
launch refused a method no offer served and verification defaulted its bar; the
descriptor validated its control values and the plan row accepted any table; the
fold checked dispatch ids inside a method and not across the directory; the profile
reader compared FRONTIER's two effort homes for the host it was building and no
other; the receipt emitter removed its temporary on a failed publish and the preset
save did not. So every fix is one function with two callers rather than a second
check beside the first: a rule with two implementations is two rules, and the one
nobody re-read is the one that decides.

L6 is the same shape with the second reader missing entirely: `panel` was refused
among the optional rows and every id was refused twice, and neither the parser nor
the adjudicator ever asked what the BASE was called — so a row resolved from no
panel descriptor, never held to the floor's two perspectives or two trials, was
credited as the review floor and reached `achievement=complete`.

| # | Invariant | Reproduced | Fixed at | Control | Revert-proven |
| --- | --- | --- | --- | --- | --- |
| 1 | L6 | yes | `_review_identity_reason`, called by `review_plan_from_v1` and by `verify_review_receipts`; `check_adapter_command`'s probe base is now `panel` | `launcher_receipts` — a plan record whose base wears another name, needled on the PARSE door's own tail; and the same report in process, where only the adjudicator can fire, with a `panel`-named positive control | yes, the clause and each of the two doors separately |
| 2 | D6 / V2 / V3 / V4 | yes | `select_capability_offer` + `registered_capability`, used by `derive_review_mechanism` and by `verify_receipts_command`; `required_evidence` keyed per selected row; the `.get(method_id, ())` default removed | `launcher_receipts` — an offer moved off the row's host, asserted against the selector's own sentence rather than any refusal; an absent declaration in process against an empty one; and a new `receipt-bare` row whose offer really declares nothing | yes, the selector, the default, and the empty-declaration recording separately |
| 3 | D2 / F1 | yes | `fold_receipts_command` — one fold-wide raw-id scan before grouping, the per-group check untouched | `launcher_receipt_adapters` — two hand-written receipts naming different methods and sharing one id, with a distinct-id positive control | yes |
| 4 | S3 | yes | `build_plan` — the two effort homes compared for every launchable host; `preset_from_plan` — the comparison moved ahead of the default-value elision | `preset_save` — an inactive-host contradiction refused at READ from the other host, and at WRITE on a plan the reader never saw, with an agreeing-homes positive control | yes, each door separately |
| 5 | L2 | yes | `controls_value_reason` (+ `CONTROLS_KEYS`, derived from `METHOD_DEFAULTS`), called by `parse_review_method` and by `_row_from_v1`, which also closes the snapshot's key set | `launcher_receipts` — six plan-row cases (unknown key, missing key, boolean and zero trials, order, aggregation, swap); `launcher_review_methods` — six descriptor cases, which had no control at all before | yes, each door separately |
| 6 | S5 | yes | `publish_atomically`, shared by `emit_receipt_command` and `save_preset` | `preset_save_round_trips` — the publish step made to fail in a subprocess, then the old file asserted byte-identical and the directory asserted to hold no temporary; positive control on an ordinary save | yes, and the receipt side of the same primitive separately |

## Where the fix departs from the reviewer's proposal, and why

- **#1 (L6).** The reviewer asked for one identity validator shared by parse and
  adjudication, and taking it literally meant `--check-adapter` — the only caller
  in the system whose base row was not the panel — had to change. Its probe named
  the row `adapter-conformance-probe`, told the adapter that name through
  `REVIEW_METHOD_ID`, and then adjudicated it as a base. An exemption inside the
  validator would be a licensed asymmetry naming one caller, and an alias whose
  value equals `PANEL_METHOD` is a second name for one concept, so
  `ADAPTER_PROBE_METHOD` is gone and the probe says what it is: a one-row plan
  whose row is the base panel. Recorded as `D-20260817-97e839`.
- **#2 (D6).** The reviewer proposed removing `.get(method_id, ())`; the question
  that leaves open is what a caller who supplies NO map at all is owed. `None`
  still means "no second view was recomputed" — the row's own snapshot remains the
  bar, which is what `launcher_receipts`' snapshot control exists to hold — but a
  caller who supplies the map owes an entry per selected row, and a missing key is
  refused rather than read as an empty declaration. `check_adapter_command` now
  states the panel's empty bar rather than passing `{}`. Recorded as
  `D-20260817-aefcea`.
- **#5 (L2).** The shared validator owns the four control VALUES and not the key
  set. A descriptor supplies defaults for every control it omits and `METHOD_KEYS`
  already closes its unknown keys, so a completeness rule there would refuse
  nothing or refuse the defaults themselves; the plan row has neither guarantee.
  Each site keeps its own sentence — the descriptor's `{context}.trials must be an
  integer >= 1` authoring error, the row reader's `records controls whose …`
  refusal — around one shared fragment. Recorded as `D-20260817-c7df5e`.
- **#4 (S3).** The active-host check was replaced by the loop rather than joined by
  a second inactive-only one: the active host is a launchable host, and its message
  is the same sentence with its own name in it. `profile_errors`' existing
  conflict control passes unchanged, which is the evidence that the active host's
  behaviour did not move.

## What the reverts taught

- **Unifying two doors creates a shared needle — the fix makes the trap.** Round 24
  learned that one needle grading two doors stops testing; here the needle became
  shared *because* both doors now raise the same validator's sentence. R1 proved
  it: with the parser's call reverted, the record parsed and the adjudicator
  refused with identical text, so a case needled on the shared middle would have
  stayed green. The three plan-record identity cases now carry the parser's own
  tail (` — re-launch`), which the adjudicator never appends.
- **A refusal that moves earlier can be the wrong door's.** Under R3 the
  unserved-host case still exited non-zero — refused by the absent-declaration door
  instead of the selector's — so a control asserting only "it failed" would have
  survived the revert while the two loops still disagreed about which offer serves
  a host. The case names the selector's own sentence, with the round-24 `elif`
  beside it.
- **A fixture with no empty declaration cannot see one.** "Record a matched offer
  even when its evidence list is empty" had no subject in `launcher_receipts` at
  all: every offer there declares fields. The `receipt-bare` method and its
  evidence-less offer had to be added before R5 could fire — round 1's "a fixture
  can be the thing that hides a finding", one round later.
- **An over-broad revert proves the wrong thing.** The first R9 cut ran to the next
  comment and took the neighbouring DROPPED-controls door with it, so its failure
  list named a door this round never touched. Cutting to the next `if` and
  asserting the extracted text does not contain the neighbour's needle made it
  faithful — and the honest version still fired all six cases.
- **A behaviour-preserving refactor has no revert, and that is a finding.** R10 —
  the descriptor's four inline checks restored — survived the gate, correctly: the
  messages are identical. What it exposed is that those four rules had no control
  anywhere in the suite, which is why six descriptor cases were added and R10′
  (deleting the descriptor's call to the shared validator) fires them.
- **A leftover temporary poisons the next reader, and the test shows it.** Under
  R11 the positive control failed too, on the stray the mutation left behind — the
  finding's own claim arriving as a second test failure rather than as an argument.

## Spec amendments proposed

The reviewer raised two specification defects. They are **not** applied here — the
spec is a dated record and the main session owns its revision. Exact replacement
sentences:

**1. L3 refuses a grade the code deliberately keeps.** In §2, Launch-time, L3
currently reads:

> - **L3 — Row shape closed by status.** Selectable: non-empty string `method_id`, `provider`,
>   `model`, `effort`, `mechanism`; `grade` ∈ `GRADE_ORDER`; `controls` a table; `evidence` a
>   list of non-empty names. `DROPPED`: `controls=None`, `evidence=[]`, no seat, no grade —
>   and only an *optional* row may be `DROPPED` — a DROPPED row carrying seat fields, a
>   grade, controls, or evidence is refused; its seat prose lives in `detail`
>   (D-20260817-c54fa5; spec round 1). *Violation:* a row outside its status shape
>   parsed rather than refused — including null seat fields on a selectable row.

Replace with:

> - **L3 — Row shape closed by status.** Selectable: non-empty string `method_id`, `provider`,
>   `model`, `effort`, `mechanism`; `grade` ∈ `GRADE_ORDER`; `controls` a table; `evidence` a
>   list of non-empty names. `DROPPED`: `controls=None`, `evidence=[]`, no seat, and
>   `grade` ∈ {`None`, `GRADE_NOT_REVIEW`} — every `GRADE_ORDER` value refused, because an
>   I1 grade is independence bought and a method that ran nothing bought none, while
>   `NOT_REVIEW` is the documented exclusion marker for a mechanism core does not attest
>   rather than a rung on the ladder, and the deployed corpus guide names it in as many
>   words (D-20260817-c54fa5; spec round 1). Only an *optional* row may be `DROPPED`; a
>   DROPPED row carrying seat fields, a `GRADE_ORDER` grade, controls, or evidence is
>   refused, and its attempted seat lives as prose in `detail`. *Violation:* a row outside
>   its status shape parsed rather than refused — including null seat fields on a selectable
>   row, or a DROPPED row graded on the ladder.

**2. S5's inactive-host requirement contradicts its own comparator.** In §2,
Save-time, S5 currently reads:

> - **S5 — What is saved reloads, identically on every host, crash-safe.** The candidate
>   parses before it replaces anything; the write is lock-serialized; readers observe the old
>   or the complete new file, and failure before the atomic replace leaves the old file
>   intact; a saved preset rebuilt on *any* launchable host projects what the source projected
>   there (`effective_tier_model`, one rule both sides) — a behavioral comparator, not just a
>   parse: the candidate is rebuilt through `build_plan` and the ACTIVE host's projection
>   compared before `os.replace`; inactive hosts are held to still building
>   (D-20260817-57c57c; spec round 1).

Replace with:

> - **S5 — What is saved reloads, crash-safe.** The candidate parses before it replaces
>   anything; the write is lock-serialized; readers observe the old file or the complete new
>   one, and a failure at or before the atomic replace leaves the old file intact and no
>   temporary behind — one `publish_atomically`, shared with receipt emission, so D8 and S5
>   cannot come to mean different things by "published" (spec round 2). On the ACTIVE host a
>   saved preset projects what is being saved: a behavioral comparator and not just a parse,
>   with the candidate rebuilt through `build_plan` and its projection compared before
>   `os.replace`. Every other launchable host is owed that the preset still BUILDS there,
>   plus S1's verbatim carry and S2's source-not-destination rule for the material written
>   for it — there is no second projection to hold it to, because a host-independent
>   customization is supposed to move every host's projection (D-20260817-57c57c; spec
>   round 1).

**3. Beyond the two raised — L6 now says less than the code enforces.** Offered
because this round changed the code, not because the reviewer flagged it. L6
currently reads:

> - **L6 — One id, one row, one verdict.** `panel` is the base's reserved id, refused in the
>   optional map AND among a serialized plan's methods at parse; a plan selecting any id twice
>   is refused at parse and at adjudication (spec round 1).

Replace with:

> - **L6 — One id, one row, one verdict.** `panel` is the base's reserved id: the base row
>   wears it and no other row may, refused in the optional map, among a serialized plan's
>   methods, and on the base itself — a base under another name was resolved from no panel
>   descriptor, so the floor's own controls (two distinct perspectives, two trials) were
>   never the bar it was credited under. A plan selecting any id twice is refused. One
>   validator answers all of it, at parse and at adjudication, because a plan record arrives
>   from anywhere and a report is also built in process (spec round 1; spec round 2).

## The round-1 refutation, and its producer-side twin

Round 1 refuted pre-registration #4 and was right to: a bundle carrying one dispatch
id across two methods IS refused at adjudication, with `reuses a dispatch id already
credited to another method`. Finding 3 is the other end of that same id — the FOLD
that writes the bundle emits the duplicate and calls the result canonical, because
`_merge_method_passes` takes a fresh `seen_ids` per method and never sees across
them. The two findings do not disagree: one is about what an auditor refuses, the
other about what this launcher's own producer is willing to sign.

The reviewer's hidden-reuse subcase — ids colliding among raw passes the fold then
discards — stays void. Whether the new scan reaches it is NOT claimed here: the
findings record gives that probe's output and not its command, so it was not re-run.
What is claimed is only what the scan does: every raw `dispatch_id` in the directory
is compared before grouping, so a collision among raw inputs is refused rather than
grouped, and the per-group check that follows is untouched.

## Void, and unchanged

- The reviewer's three void readings (hidden non-representative id reuse at D2,
  `passes` on a one-trial receipt at D3/Q4, extra control markers at D6) stay void;
  nothing here touches them. Q4 and Q5 are unchanged.
- The reviewer's S5 probe reports `temporary_present=True` against the FIXED code,
  because its in-memory `Path` stub has no `unlink` and the cleanup's own
  `except Exception: pass` swallows the AttributeError. The behaviour was verified
  on the real filesystem instead, which is also where the gate control asserts it.

## Verification

- `gates/check_parity.py` (the runtime-projection module, 62 checks): green.
- `gates/capture-review-goldens.py --check`: green with **no re-capture** — none of
  the six fixes changes rendered contract text; `--self-test`: 10 controls each
  proven to fire.
- `ontology/check-ontology.py`: OK (38 entities, 49 edges, 9 kinds).
- `decisions/record-decision.py --check`: OK.
- Twelve reverts, each cut from a pristine copy of the FIXED tree, never an inverse
  patch, each refusing unless its text matched exactly once.
- The full umbrella (`.githooks/pre-commit`) ran on the index for both commits.

## Left open

- Nothing from the six findings.
- **A contract for in-process callers.** A `ReviewReport` handed to
  `verify_review_receipts` must now name its base `panel`. That is true of every
  caller in the tree and of every launch, and it is the reason four gate fixtures
  moved their probe rows — but it is a new obligation on anyone constructing a
  report by hand.
- D4's retention half (Q3), L5's main-seat serialization (Q2), and Q4/Q5 are
  untouched.
