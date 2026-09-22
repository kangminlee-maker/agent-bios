---
created_at: 2026-09-22T11:06:00+09:00
head: c1915b2
kind: design
status: successor-bundle-selected-p00-stale-until-rerun
plan: 2026-09-22T0900--c1915b2--development-plan.json
supersedes: 2026-09-20T0809--d76af32--successor-bundle-record.md
decisions: D-20260922-d8021b, D-20260922-b2a009
---

# Scope-trim successor of 2026-09-22 09:00: what the plan requires now and what it no longer builds

`CURRENT.md` now selects `2026-09-22T0900--c1915b2--development-plan.json`. Five files carry the
same stamp: the plan, the test catalog, the evaluator, the regression helper and the mutation
sweep. The 25 nodes, the design SSOT and the development spec are unchanged. Nothing about the
product is implemented by this bundle. It changes which cases a node must pass and which planned
features a node must build.

Evidence named here is outside the repository, under
`~/.local/share/agent-bios-workbench/team-env-20260920/p01-u11/phase6/`. It holds:

- `classes.py`: the class of every case, with a one-line reason
- `xcheck/`: the blind cross-provider classification: packet, schema, result and receipt
- `successor.py`: builds this bundle from the 07:51 one
- `trim_registry.py`
- the sweep outputs

## Why

The owner, on 2026-09-22, while U11 was reviewing 205 required cases:

> happy path를 실행하는데에 문제가 없음을 보장하고, 정말 일어나면 안되는 상황(crash를 만들거나,
> 복구가 불가한 영구적 구조손상 혹은 data contamination을 일으키는 케이스들)에 대한 안전판만 있으면 돼.
> 나머지는 QA 및 실사용 통해서 발견하고 해결하면 돼. 너무 많은 시나리오를 쓰면, 처음부터 너무 과한 코드를
> 쓰게 돼. YAGNI를 기억해야 해.

In English: guarantee that the happy path runs, and keep a safety net only for what must never
happen: a crash, unrecoverable permanent structural damage, or data contamination. Everything
else is found and fixed through QA and real use. Writing too many scenarios forces too much code
from the start.

The owner then placed data exposure and authority widening inside the safety net, because a
disclosure cannot be undone and the product purpose requires a simplification to preserve
authority boundaries. Deferred cases are deleted, not kept as optional files.

## How each case was classified

| Class | Meaning | Count |
| --- | --- | --- |
| H | The node's normal flow; without it a worker cannot use the feature the node delivers | 74 |
| S | Prevents a crash or hang, lost unique work, split or orphaned authority, a half-written store, or a record, answer, decision, instruction or original that becomes wrong and persists | 57 |
| L | Prevents data reaching someone who must not have it, or authority a principal was not given | 31 |
| D | Deferred: presentation detail, report precision, a quality property that can be corrected later without lasting damage, or a case another kept case already guarantees | 43 |

The coordinator classified all 205 cases first. One `gpt-6-astra/max` pass through the read-only
wrapper then classified the same 205 without seeing that classification (receipt
`40bb055745fd4e24b7e0a49cc9f588c7`). The two agreed on 130 cases and split keep against defer on
56. The disagreements were settled by three rules, applied in order:

1. A case that stops a wrong record, answer or duplicate effect from persisting is S, even when
   its trigger looks like a detail. Examples: an invented rationale written as decision history
   (CAP-05); an operation run against an item the worker did not select (TUI-ENTRY-FOCUS); an
   unknown operation replayed from a recovery screen (TUI-ENTRY-UNKNOWN, -SHARED-UNKNOWN).
2. A feature that a node's `done_when` names keeps its happy-path case. Deferring that case would
   leave the feature built but unchecked. The owner then removed seven such features (below).
3. A case that only repeats what a kept case guarantees is D. Examples: N19-C08-NEG repeats
   N19-TRANSFER-NEG; N28-C01-NEG repeats CAP-03 and CAP-07; SRC-09 repeats N27-C01-POS and -NEG.

## Features the plan no longer builds

The SSOT still describes these as target design. The plan defers them; each decision record
names what would bring one back.

| Feature | Plan change | Catalog change |
| --- | --- | --- |
| Real validator adapter | P15 `done_when[1]` removed | N23 leaves P15 |
| Dashboard signals | P16 `done_when[1]` removed | — |
| Actual first-exposure and Korean terminal observation | P17 `done_when[2]` removed; P17 scope reworded | family N26 removed; TUI-OBS-ENTRY-COMPREHENSION, TUI-OBS-KOREAN-TERMINAL removed |
| Native form questions | P10 `done_when[2]` and scope reworded to the native-question or conversation route; `host-form-evidence` leaves every node's outputs | DH-FORM removed |
| Decision reach through cached, compacted and child routes | P10 `done_when[3]` and P17 `done_when[3]` reworded | DH-REACH removed |
| Restricted-state proofs | P05 `done_when[1]` reworded | N22 oracle 0 drops "proofs" |
| Authorized knowledge extensions | P04 `done_when[2]`: add/import paths | SRC-05 removed |
| Group grants | P07 `done_when[0]` reworded | N11 oracle 0 drops group delegation |
| Team copy | P14 `done_when[0]` reworded | — |
| Closed-Team evidence recovery | P14 `done_when[0]` reworded | N19 oracle 0 drops evidence recovery |

The first three were decided with the scope rule (D-20260922-d8021b). The other seven were
decided after the cross-check showed that each was named in a `done_when` while all of its cases
were deferred (D-20260922-b2a009). The optional GitHub carrier (P12) and external login (P13)
stay.

## Deferred cases (43)

They are deleted from the tree. Their text remains in the 10:26 catalog, and their scenarios
remain at `c1915b2`.

- **Catalog atomic (10):**
  - DH-FORM, DH-REACH: features removed.
  - DH-REVALIDATE: N05-WAIT-POS keeps the store from blocking; DC-RACE keeps a stale answer out.
  - SRC-05: feature removed.
  - SRC-09 and SRC-12: repeat N27-C01 and CMP-ORDER with DC-CHOICE.
  - TUI-ENTRY-80X24, TUI-ENTRY-STATE: presentation.
  - TUI-OBS-ENTRY-COMPREHENSION, TUI-OBS-KOREAN-TERMINAL: feature removed.
- **Removed features (12):**
  - N07-PROOF-POS/-NEG
  - N11-GROUP-POS/-NEG
  - N19-COPY-POS/-NEG
  - N19-EVIDENCE-POS/-NEG
  - N23-VALIDATOR-POS/-NEG
  - N26-INSTALLED-POS/-NEG
- **Presentation, report precision or temporary availability (10):**
  - N06-C04-NEG, N16-CAPABILITY-NEG, N16-DASHBOARD-POS, N16-HOME-POS, N16-PENDING-VIEW-NEG
  - N20-GRAPH-TABLE-POS, N21-C10-NEG
  - N23-PROVIDER-NEG, N23-SECRET-NEG, N03-PROVIDER-OUTAGE-POS
- **Record rules whose failure is recoverable (6):**
  - N07-PREFERENCE-NEG, N09-UNIT-GAP-NEG, N09-UNITS-NEG
  - N15-ATTEMPT-NEG, N20-VALIDATION-NEG, N23-PROBE-NEG
- **Repeats of a kept case (5):**
  - N12-READINESS-NEG repeats CMP-PINS and N12-C07-NEG.
  - N13-RESUME-POS: a repeated accept is already idempotent (N13-C09-POS).
  - N19-C08-NEG, N22-E2E-NEG, N28-C01-NEG.

## What changed in each file

- **Catalog:**
  - The ten atomic cases above are removed from their families and from every profile and
    obligation.
  - Family N26 is removed.
  - Families leave the profiles that keep no case in them: N23 from P15 and M2, N26 from P17 and
    M4.
  - The P10 and P17 scopes are reworded. Three family oracles are reworded (N11, N19, N22).
- **Plan:**
  - It names the new catalog, evaluator and helper, and binds their digests.
  - Each node's `test_ids` equal its profile's families.
  - Every `done_when` change is listed above.
  - `required_evidence` reads "for the conversation case" where it read "for the selected
    form/fallback cases".
- **Evaluator:** two places change. `HOST_ANSWER_ARTIFACTS` holds only DH-CONVERSATION, and the
  allowed carriers no longer branch on DH-FORM. The default plan path is the new one.
- **Regression helper:**
  - The named constants follow the trimmed sets. `HOST_QUALIFICATION_CASES` is DH-CONVERSATION
    and DH-PENDING. `ENTRY_OBSERVATIONS` is gone.
  - The two tests on which reply route permits the other became one negative: an unavailable
    conversation route cannot certify interactive host support.
  - Every control that drove the native form drives the conversation route.
  - The controls that pinned BKP-COVERAGE and DC-CHANGE stay, because both cases stay as S.
- **Mutation sweep:** only its default plan path changes.
- **Case registry (P01's own, `gates/workenv/`):**
  - The 43 cases and their scenarios are gone, and the `covers` rows follow the removed
    `done_when` items.
  - `cases.py` no longer requires a positive and a negative in every profile's family. A family
    may hold only its happy path or only its safety net; the evaluator's own rule, one bound case
    per family, remains.
- **Contracts:** the spellings that only removed features or deferred cases used are removed:
  - C11's `surface.observe` and `surface.protocol.record` with the kinds `surface_observation`,
    `exposure_trial` and `study_protocol`
  - C05's `memory.state.prove` with `state_proof` and its three gap codes
  - C08's group holder (`approved_set`, `provider_delegation`, `group_membership_escalation`), the
    founding proposal's `derived_from`, and the `recover_evidence` lifecycle action
  - the `native_form` reply route in five schemas
  - C01's `extension_of_supplied` provenance
  - eight runtime rules no kept case checks, with their oracles and fixtures: C04
    `view_names_declared_companions`; C05 `selected_participant_applicable` and
    `proof_answers_its_request`; C07 `gap_names_no_losing_unit` and
    `unit_reference_names_a_winning_unit`; C11 `attempt_outcome_fits_its_request`; C12
    `qualified_only_by_a_real_probe` and `validation_covers_its_request`
  - Four kept scenarios were rewritten without a removed spelling: CAP-13 resolves its state on
    an individual read grant instead of a proof; N11-C08-POS and -NEG use individual review
    grants; N04-ROUTER-NEG and the decision scenarios ask through the native-question or
    conversation route.
  - Totals now: 91 operations (94), 22 runtime rules (30), 176 error codes (180), 162 scenarios.

## Measured

| Check | Result |
| --- | --- |
| Evaluator on the new plan | `plan-valid-not-runtime-qualified`, 25 nodes, 7 obligations |
| Regression helper | passed: 28 positive and 412 negative controls (07:51: 30 and 425) |
| Live gate `gates/check-development-plan.py` | `current-plan-valid-and-regressions-passed` on the new bundle |
| Refusal sweep | 130 refusals: 130 detected, 0 undetected, 0 crashed, 0 harness errors |
| Named reverts (`--reverts`) | 78 of 78 caught by every control they name |
| `gates/workenv/cases.py` | `CASES OK`; every profile's case map is accepted by the new evaluator |
| `scenarios.py --check`, `project-names.py --check`, `errors --check` | 162 specs, 0 problems; names current; 176 codes |

Re-run them rather than trusting these figures.

## What it costs

- **P00 is stale:** the plan digest moved, so P00's 08:42 record reads `stale plan/node`. P00
  is run again in a new run before P01 can be recorded.
- **Not reviewed as a bundle:** the evaluator's two changed places and the helper's changed
  controls have been exercised by the helper and the sweep, not read by a second provider. The
  cross-provider pass read the classification, not the bundle's bytes.
- **U11 walks again:** the walk-through verdicts of 2026-09-22 were given over the 205 cases, so
  U11 walks the 162 kept cases again.

## Not verified

- that the SSOT's descriptions of the ten deferred features leave no requirement a kept case
  depends on
- any runtime behaviour of the product; none exists
