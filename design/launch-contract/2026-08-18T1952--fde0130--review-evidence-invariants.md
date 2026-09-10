---
created_at: 2026-08-18T19:52:00+09:00
head: fde0130
kind: design
supersedes: 2026-08-18T0235--3328cb8--review-evidence-invariants.md
---

# Invariants — the launcher's review-evidence subsystem

**Subject:** `launch/agent-launch.py` after spec rounds 1–7 (final closure `fde0130` on
`spec-round-7-closure`; closures `270738f`, `debe2a0`, `fb157f0`, `16238c5`, `3328cb8`,
`0008590`, `fde0130`). **The review loop concluded with round 7's closure
(D-20260818-76bea7)**; this revision is the spec's resting state — the instrument for any
future round, none scheduled: the review plan a launch
contract carries (`ReviewPlan/v1`), the receipts dispatched review processes emit
(`ReviewReceipt/v1`), the fold of per-pass receipts into a bundle (`ReviewReceipts/v1`),
adjudication PROPOSED vs ACHIEVED, and the save of review-carrying presets.

**Why this document exists:** rounds 20–24 reviewed this code against its own stated
intentions and returned 8/9/10/5/12 closed findings, the Highs in this subsystem every round
(`D-20260817-2284a1` changed the instrument). A reviewer now holds the code against THIS
document: **done = every invariant holds or names its violation.** The recurring shapes it is
built to close: a guard defeated by an *absence*; folding many into one discarding the part
that would have been refused; absences comparing equal; a rendered label as identity; a
"snapshot" recomputed at verification; an unresolved host read as a wildcard.

**Provenance:** synthesized from two independent frontier drafts off one blind packet —
Claude (fable-5) and GPT (gpt-5.6-sol, ultra) — per the dual-provider design rule; revised
after spec rounds 1–7 (findings and closures under this directory): each round's
specification defects are amended exactly as its closure record proposed, and the
enforcement markers reflect the tree after the closures. Section notes name which draft
contributed what.

## 0. Terms and trust boundary *(GPT draft, condensed)*

- A **selected row** is the base plus every optional row whose status is not `DROPPED`.
- A **pass** is one raw `ReviewReceipt/v1` before folding. The **review packet** is the exact
  byte sequence supplied to every dispatched pass (the existing "declared packet").
- A **canonical SHA-256** is 64 lowercase hex characters; a **result digest** is a canonical
  SHA-256 that is not the SHA-256 of empty bytes (`is_result_digest`).
- A **verbatim arm** preserves the parsed TOML tree — types, values, array order, key
  identity — not comments, whitespace, or lexical spelling.
- **`ACHIEVED` means only** that deterministic checks accepted a cooperating adapter's
  bounded report against the plan. It does not independently prove provider honesty, the seat
  actually reached, isolation, review quality, or semantic aggregation. The trust boundary:
  the local operator, launcher, canonical adapters and their environment are trusted
  producers; receipts prove internal consistency, not authenticated provenance (Q7).

## 1. Object model *(Claude draft; packet row from GPT)*

| Artifact | Created by | What its existence ASSERTS | Identity pinned by |
|---|---|---|---|
| **Plan** (`ReviewPlan/v1`) | `review_plan_v1` over the resolved `ReviewReport`; spliced exactly once by `run_contract` behind `ReviewPlan/v1: ` | At launch this review was projected: these methods, on these seats, under these controls and this evidence bar, summarized by `best_grade`. The *complete* statement of every bar receipts will later be held to | `schema`, header, base row, method rows — content, not position |
| **Plan row** (`ReviewMethodReport`) | `_resolve_one` / `resolve_composable_review`; `_row_v1`/`_row_from_v1` | Selectable (`OK`/`DEGRADED`/`ADVISORY`): selected on exactly `provider:model/effort` via `mechanism`, under the `controls`+`evidence` snapshots. `DROPPED`: named but ran nothing — no seat, `controls=None`, `evidence=[]` | `method_id` + `status`; the seat triple pins what a receipt must match |
| **Controls** | descriptor (`[review_methods.*]`) at launch | The mechanical bar declared at launch: `trials` (int ≥1, not bool), `order` ∈ {fixed, randomized}, `swap_augmentation` (bool), `aggregation` ∈ {union, majority}. One shape, three consumers: `controls_clause`, the row, the receipt bar | the four values |
| **Mechanism / required evidence** (`ReviewMechanism.evidence`) | `derive_review_mechanism` — first offer in declared order serving (operation, binding's host); no branch reads the method's identity | The chosen offer declares these evidence fields will be reported. Carried into the row's snapshot; never looked up a second time | the (capability, operation, host) triple |
| **Review packet** | dispatch orchestration | The exact bytes supplied to each pass, containing the canonical plan being executed | its runtime-computed digest + the embedded plan |
| **Receipt** (`ReviewReceipt/v1`) | `emit_receipt_command` — launcher owns `dispatch_id` (uuid4), hashes, field names, path | One *fresh child dispatch* consumed the packet (`packet_sha256`), produced a non-empty result (`result_sha256`), on the named seat, with this `exit_status` and these observed `evidence` values | `dispatch_id` — never the adapter's to choose |
| **Pass** | one receipt in a fold group; after folding, one `passes` entry | One distinct process produced one distinct non-empty result. `passes` holds result digests, never dispatch ids | the result digest |
| **Bundle** (`ReviewReceipts/v1`) | `fold_receipts_command` | These folded receipts were collected against *this* packet (hashed from the packet artifact, never off receipts) and outside *this* main session | its two anchors: `packet_sha256` + `main_dispatch_id` |
| **Verdict** (`ReceiptVerdict`) | `verify_review_receipts` | Per *selected* method: ACHIEVED or PROPOSED with a named reason. `selected=False` rows are diagnoses about the bundle, not units of coverage | `method_id` for selected; arrival order for foreign — a rendered label is not identity |
| **Saved preset** | `preset_from_plan` → `render_preset_block` → `save_preset` | Reloading rebuilds the saved plan: active host from the plan, every inactive host/arm as authored, nothing silently dropped. Asserts authoring intent only — no runtime status, receipt, or verdict | preset name (via `_toml_key`) |

`achieved_grade` starts `UNKNOWN_UNTIL_RECEIPTS`; `achievement` ∈ none/partial/complete over
selected rows; `availability` is the launch-time projection, never written by verification.

## 2. Invariants

Each is falsifiable: the violation decidable from the artifacts, plus — for the clauses
that are about an INTERLEAVING rather than a state — a bounded runtime probe that injects a
failure at a named step. D8's "a concurrent reader observes no file or one parseable
receipt" and S5's "readers observe the old or the complete new file, and a lost concurrent
save" are temporal properties: a final receipt or preset cannot say what another reader saw.
Their artifact-decidable residue is the POST-FAILURE state — no partial file, and no
leftover temporary that a later run or reader would mistake for live state; when the
cleanup itself fails, the residue is a disclosed temporary path, never a silent one — and
that is what a control asserts. Enforcement is structural unless marked
**[unenforced]**. *(Skeleton: Claude draft; the formerly-[unenforced] clauses were the GPT
draft's independent finds, adjudicated in spec round 1.)*

### Launch-time — what the plan must snapshot

- **L1 — One canonical record.** The rendered contract carries `ReviewPlan/v1: ` exactly once
  (composable path), one decodable record; every authored value reaching prose refuses the
  marker — evidence field NAMES included (`refuse_evidence_marker` at offer parsing and row
  parse), a refusal never reproduces the token it forbids, and `run_contract` asserts the
  record span's own marker count (spec round 3); legacy and composable review never coexist in one preset; a no-review route
  advertises neither route nor plan. *Violation:* `extract_review_plan_v1` recovers ≠1 record,
  or any prose span carrying the marker.
- **L2 — Snapshot completeness, closed grammar.** Every bar the verifier holds a receipt to
  is a field of the plan row (seat, `controls`, `evidence`); adjudication reads the snapshot,
  never post-launch config. The plan and row grammars are **closed**: exactly the declared
  fields, declared types, closed value domains; unknown fields, wrong containers, missing
  fields refused by name (`REVIEW_PLAN_KEYS`/`REVIEW_ROW_KEYS`; spec round 1) — the nested
  `controls` grammar included (`controls_value_reason`/`CONTROLS_KEYS`, one validator for
  descriptor parsing and `_row_from_v1`; spec round 2).
  Adding a new adjudication input is a schema evolution, not silent widening (Q2).
  *Violation:* an adjudication input read from post-launch config, or an unknown-keyed record
  parsed clean.
- **L3 — Row shape closed by status.** Selectable: non-empty string `method_id`, `provider`,
  `model`, `effort`, `mechanism`; `grade` ∈ `GRADE_ORDER`; `controls` a table; `evidence` a
  list of non-empty names. `DROPPED`: `controls=None`, `evidence=[]`, no seat, and
  `grade` ∈ {`None`, `GRADE_NOT_REVIEW`} — every `GRADE_ORDER` value refused, because an
  I1 grade is independence bought and a method that ran nothing bought none, while
  `NOT_REVIEW` is the documented exclusion marker for a mechanism core does not attest
  rather than a rung on the ladder, and the deployed corpus guide names it in as many
  words (D-20260817-c54fa5; spec round 1). Only an *optional* row may be `DROPPED`; a
  DROPPED row carrying seat fields, a `GRADE_ORDER` grade, controls, or evidence is
  refused, and its attempted seat lives as prose in `detail`; an invented grade string
  outside {`None`, `NOT_REVIEW`, `GRADE_ORDER`} is refused on every row, and `detail`/
  `instruction` must be strings (spec round 3). *Violation:* a row outside its status shape
  parsed rather than refused — including null seat fields on a selectable row, or a DROPPED
  row graded on the ladder.
- **L4 — The base is never DROPPED.** `resolve_composable_review` refuses to build it and
  `review_plan_from_v1` refuses to parse it, so it can never shrink the denominator.
- **L5 — Header validated by name; grades are derived.** `availability` ∈ {projected},
  `achieved_grade` ∈ {UNKNOWN_UNTIL_RECEIPTS}, `best_grade` ∈ `GRADE_ORDER` **and** equal to
  `best_review_grade(rows)`. Row grades and independence claims must be *recomputable* from
  facts the record (or a structurally bound launch artifact) pins — main seat included
  **[unenforced: the main seat is not serialized; the verdict rendering now DISCLOSES
  `grade_derivation=claimed` (D-20260817-47c998), and the schema evolution is Q2]**.
  *Violation:* a forged header surviving, or a claimed grade rendered as derived.
- **L6 — One id, one row, one verdict.** `panel` is the base's reserved id: the base row
  wears it and no other row may, refused in the optional map, among a serialized plan's
  methods, and on the base itself — a base under another name was resolved from no panel
  descriptor, so the floor's own controls (two distinct perspectives, two trials) were
  never the bar it was credited under. A plan selecting any id twice is refused. One
  validator answers all of it, at parse and at adjudication, because a plan record arrives
  from anywhere and a report is also built in process (spec round 1; spec round 2).
- **L7 — Contract/argv fidelity.** Every plan value that changes projected argv is rendered
  in the contract (`execution_clause`, both hosts, from the field `project_args` reads);
  forwarded-key collision identity is TOML segment *tuples* (`canonical_config_key`) —
  whitespace, quoting, literal dots change nothing in either direction; the MCP
  registration projection — the `(name, command, args)` a selected capability registers —
  is computed once (`review_mcp_servers`) and consumed by BOTH the contract clause and
  every backend argv builder, so a capability rename cannot change argv under a
  byte-identical contract (D-20260818-7ad546; spec round 5) — and both the MCP and the
  child-agent projections are CALLED once per launch, at the top of `project_args`, with
  the same values handed to `run_contract`, the materializer, and the argv builders (spec
  round 7). *Violation:* two
  plans with different argv and byte-identical contracts, or a spelling-dependent collision.
- **L8 — Advertised tiers are the active set.** Contract and both summaries enumerate
  `active_tiers` = main ∪ (`SPAWNABLE_TIERS` if delegation), complement labeled "inactive
  tiers" with its reason; child projection reads `SPAWNABLE_TIERS` alone (D-20260817-4aec19).

### Dispatch-time — what a receipt must prove

- **D1 — Receipt structure closed.** `schema == ReviewReceipt/v1`; keys ⊆ `RECEIPT_KEYS`;
  `type(exit_status) is int`; one shared validator (`_receipt_structure_reason`) at both
  readers. A **raw** receipt additionally carries no fold-owned `passes` — one raw receipt is
  one pass, and the raw/folded distinction is a phase-specific type door
  (`_raw_receipt_reason` at fold input, before the singleton return; spec round 1).
- **D2 — Fresh dispatch identity.** `dispatch_id` non-empty, ≠ `main_dispatch_id`, and
  never reused across the credited receipts visible at the phase. That an id was
  launcher-generated rather than adapter-chosen is a PRODUCER OBLIGATION
  (`emit_receipt_command` owns uuid4, and an adapter binds to the contract by calling it)
  and not a property of the artifact: two otherwise identical receipts cannot be told apart
  on it, which is the same limit §0's trust boundary draws. Verified uniqueness is therefore
  per phase — across methods within one bundle, and across the raw inputs of one fold
  (fold-wide raw-id scan before grouping; spec round 2) — and the folded record does not
  preserve per-pass ids, so cross-method uniqueness has no post-fold subject (Q5).
- **D3 — A result hash is a digest of a non-empty result.** `is_result_digest` at every site
  a result hash is read: primary `result_sha256`, every raw pass at fold, every `passes`
  entry at adjudication. (Known condition: `passes` on a `trials=1` receipt is never read —
  Q4.)
- **D4 — Packet consumption.** The receipt's `packet_sha256` is canonical hex and equals
  the bundle's anchor; absence is refused before equality. Whether that anchor is bound to
  real BYTES is a disclosed property rather than a condition of achievement: fold hashes
  the packet *file*, so a bundle is written bound. Verification is offered the packet
  independently (`--verify-receipts --packet`), and when it is supplied it must recompute
  the digest and check the embedded plan is the plan being adjudicated. When it is not,
  the packet-less path is the norm and not a violation — achievement and exit status are
  unaffected — and the verdict must render `packet_binding=none`, naming the digest as
  bound to no bytes (spec round 1, `D-20260817-c3a9f0`; spec round 5). "Must receive the
  packet" binds only a verification that CLAIMS byte binding. Packet retention is Q3.
- **D5 — Seat equality.** Receipt `provider`/`model`/`effort` equal the row's snapshot —
  which L3 has proven non-null, so omission can never match.
- **D6 — Evidence and control markers.** `evidence` a table when present; every
  snapshot-required field carries a truthy value; `ordering_seed` REQUIRED WHEN the declared
  order is randomized, `swap_group` when swap is declared — each bar applied only where the
  descriptor declared it, and **only as a requirement**: a marker present where nothing
  declared it is ignored, exactly as an evidence field reported beyond the declared set is,
  because a bar on an extra is a bar no descriptor wrote and the fold's own rule is presence
  AGREEMENT across passes rather than absence (D-20260816-c0067f, -0ed011,
  D-20260817-3d6a6e; spec round 3). A missing offer and a real empty-evidence offer are
  distinct states; absence is not an empty declaration (`select_capability_offer` +
  `registered_capability`, one selector for launch and verification, the per-row
  `required_evidence` recorded even when empty, no-match refused; spec round 2).
- **D7 — Multi-pass counting.** For `trials > 1`: `passes` is a list, every entry passes D3,
  distinct entries ≥ trials, primary result ∈ passes (enforced in full, spec round 1).
- **D8 — Atomic, runtime-owned emission.** Only the canonical emitter assigns schema, id,
  hashes, serialization, path; it publishes complete bytes atomically so a concurrent reader
  observes no file or one parseable receipt, and failure leaves no final receipt (dotted same-directory temp + `os.replace`; cleanup of the temporary on failure is
  best-effort — it may not mask the initiating failure, and a temporary the cleanup could
  not remove is disclosed by path rather than guaranteed absent; spec round 1; spec
  round 7 — the disclosure half is an ADOPTED OBLIGATION not yet enforced: today's
  `publish_atomically` preserves the initiating failure but discloses nothing, and an
  interrupt raised during cleanup can mask it; priced in the round-7 closure, open).

### Fold-time — what folding may and may not infer

- **F1 — Every raw pass judged before anything folds, singleton included.** Structure (D1),
  identity (D2), digest (D3), readable evidence — asked of *each* receipt before the
  singleton return or any merge. Anything a later pass is not held to here is never held to
  at all.
- **F2 — Folding never manufactures agreement, and is order-invariant.** Across a group:
  seat and `packet_sha256` agree by value; the set of evidence fields *reported with a value*
  agrees; `ordering_seed`/`swap_group` agree on *presence* (values may differ — a swap group
  names which arm ran). Descriptor-owned *value* bars stay at adjudication — applying them in
  the fold would reopen D-20260816-c0067f/-0ed011/D-20260817-3d6a6e. Folding the same
  receipts in any order yields the same outcome and content (`_fold_order_key`; spec
  round 1).
- **F3 — The folded record is faithful.** `passes` = the set of per-pass result digests,
  nothing filtered; a failed pass propagates its nonzero exit; a control field every pass
  omitted stays omitted — silence for the descriptor-aware adjudicator, never a default.
- **F4 — Bundle write-side anchors.** `fold_receipts_command` refuses an empty directory, a
  missing `main_dispatch_id`, a method-less receipt; `packet_sha256` hashed from the packet
  file; bundle keys closed (`RECEIPT_BUNDLE_KEYS`) and an empty `method_id` refused at the
  public fold boundary (spec round 1).

### Verify-time — adjudication

- **V1 — Read-side anchors required.** Non-empty `main_dispatch_id`, canonical
  `packet_sha256`, `receipts` an array — required, never defaulted: `--verify-receipts`
  adjudicates a file from anywhere and the fold's write-side refusals prove nothing about it.
- **V2 — Drift refused symmetrically; the snapshot adjudicates.** Plan `controls` must equal
  the current descriptor, plan `evidence` the current offer — disagreement refused by name,
  never resolved toward either side; comparison unconditional. Adjudication reads the
  snapshot, so post-launch config edits neither lower nor raise the bar; the drift
  comparisons are UNCONDITIONAL — a `None` evidence snapshot or a non-map is refused, never
  skipped, and both the row's and the descriptor's controls pass the closed grammar
  (`controls_snapshot_reason`) before comparison, after which `trials`/`order`/`swap` are
  indexed with no default (spec round 3).
- **V3 — No bar is defaulted.** A registry that fails to load is a config-attributed
  failure; a selected method with no descriptor is refused, never defaulted to one pass.
- **V4 — An unresolved host is a refusal, never a wildcard.** The evidence-bar offer is
  selected exactly as `derive_review_mechanism` seats a method; a provider mapping to no
  host (or several) is refused by name, never "first offer wins".
- **V5 — Canonical cardinality.** At most one folded receipt per selected `method_id`; a
  bundle carrying duplicates for one method is refused rather than adjudicated first-wins —
  the canonical fold emits one per method, so a duplicate evidences concatenation or
  tampering (enforced, spec round 1; supersedes the Claude draft's description of the old
  first-wins behavior as intent).
- **V6 — Coverage counts selected rows only; foreign receipts disclosed, uncounted.**
  Fraction and `achievement` over selected rows; a receipt naming no selected method yields
  an ordered `selected=False` diagnosis — never keyed by display label, never refusing the
  bundle (D-20260816-bf3d08). A selected method with no receipt is PROPOSED "no receipt was
  supplied"; `achieved_grade` stays UNKNOWN rather than becoming failure-by-silence; the
  output report copies every launch-time field verbatim — verification writes only what it
  learned.
- **V7 — The verify command is a gate.** Exit 0 iff `achievement == complete`; every refusal
  above exits nonzero with a named reason; a traceback in place of a named refusal is itself
  a violation.

### Save-time — carried verbatim, normalized, or refused

- **S1 — Verbatim carry has no depth limit and no type list.** Everything outside the active
  host's rebuild is written back as authored: inactive arms (an empty arm as an explicit
  parent table), unseated bindings, unknown fields at any depth (recursive
  `_emit_arm_table`), every dynamic key through `_toml_key`, every `tomllib`-producible type
  through the shared serializer — and semantic identity is recursive and type-aware (array
  order significant, table order not; infinities and datetimes compare as parsed values;
  **all NaNs are one value — sign ignored, and a NaN equal to itself** — which is what
  `_toml_scalar`'s `repr` spelling writes and what the round-trip comparator's `repr` test
  asks, since a value comparison would call the one spelling this clause is about unequal
  to itself; a `-nan` saved as `nan` is compliant; spec round 3 — GPT). Any TOML the launcher writes elsewhere (child agent templates) uses the same
  spellings. A saved preset carries *intent only* — no runtime status, grade, receipt, or
  verdict.
- **S2 — The source is the plan, never the destination name.** Carried inactive material
  (`tier_overrides`, `frontier_effort_authored`, arms) comes from the plan built from the
  source preset; Save As and save-over-source behave identically on every inactive host.
- **S3 — One value, one home.** FRONTIER effort normalized into
  `tier_overrides.<host>.frontier.effort`; two homes, or a contradiction, refused by name at
  read and at write, for EVERY launchable host — the comparison runs before default-value
  elision, so an inactive host's contradiction cannot be normalized away
  (D-20260817-76ecd1; spec round 2).
- **S4 — Refuse by name; never drop, never default.** An authored value the save cannot
  faithfully write is refused naming the entry; the complement holds — except for S6's routed-content refusals, every non-routed profile
  the launcher accepts remains saveable; any other refusal names the genuinely unwritable
  entry (D-20260817-105da4, -53c588, -25a972, -89fc58; spec round 5) — nested inactive
  tier-override values go through the recursive emitter, and a genuine refusal names the
  exact entry path (spec round 3).
- **S5 — What is saved reloads, crash-safe.** The candidate parses before it replaces
  anything; the write is lock-serialized; readers observe the old file or the complete new
  one, and a failure at or before the atomic replace leaves the old file intact and, when
  cleanup succeeds, no temporary behind — cleanup is best-effort, may not mask the
  initiating failure, and discloses a temporary it could not remove — one
  `publish_atomically`, shared with receipt emission, so D8 and S5 cannot come to mean
  different things by "published" (spec round 2; spec round 7). On the ACTIVE host a
  saved preset projects what is being saved: a behavioral comparator and not just a parse,
  with the candidate rebuilt through `build_plan` and its projection compared before
  `os.replace`. Every other launchable host **on which the source preset builds** is owed
  that the saved preset still BUILDS there, plus S1's verbatim carry and S2's
  source-not-destination rule for the material written for it — a host arm the source
  never built is owed the carry alone, since a refusal the source already earns there is
  not the save's to repair; there is no second projection to hold any inactive host to,
  because a host-independent customization is supposed to move every host's projection
  (D-20260817-57c57c; spec round 1; spec round 7).
- **S6 — Routed content cannot wear a preset's shape.** A plan carrying a mission/trigger or
  a routed preset name is refused at save.

### Explicitly outside the falsifiable set *(Claude draft; GPT concurs via trust boundary)*

- Adapter honesty (a receipt proves the seat it *names*), semantic aggregation adherence
  (union/majority as *meaning*, not count — making it achievement-bearing is Q6), review
  quality. Stated so nobody mistakes ACHIEVED for more than it is.

## 3. Coverage and enforcement

The Claude draft's per-invariant enforcement table (code + gate control + findings) was
verified against the round records and holds; it is not repeated here — the compressed form:
every one of the fourteen High findings maps to an enforced invariant: R20#1→D4/V1/F4 ·
R20#2→F1 · R20#3→L2/V2 · R20#4→L7 · R21#1→L6 · R21#2→D1/F1 · R21#3→F2 · R22#1→L3/D5 ·
R22#2→F2 · R22#3→D1 · R24#1→L2/D6/V2 · R24#2→V4 · R24#3→L4 · R24#4→D3. Enforcement lives in
the functions each invariant names; the controls in `gates/check_parity.py`
(`launcher_receipts`, `launcher_receipt_fold`, `launcher_review_contract`,
`launcher_review_schema`, `launcher_review_save`, `preset_save`, `preset_save_round_trips`,
`backend_dispatch`, `agent_materialization`, `launcher_delegation_clause`).

**Spec round 1 disposition of the eight pre-registered violations** (findings record
`…T1517--9d1d668--spec-round-findings.md`, closures `270738f`, closure record
`…T1639--270738f--spec-round-closure.md`): seven confirmed with mutation/control evidence
and closed at the authority — L2 (closed grammars), D1 (raw `passes` refused), D4 (packet
binding + unbound disclosure), D8 (atomic emission), F4 (closed bundle keys, and the empty
`method_id` twin), V5 (duplicates refused), S5 (behavioral comparison) — plus five more the
round found beyond the list (D7 primary ∈ passes, L3 DROPPED-with-live-seat, L6 serialized
`panel`, F2 order-dependent content, F4's fold-boundary door). One REFUTED: visible
cross-method dispatch-id reuse was already refused. L5 remains unenforced by decision
(D-20260817-47c998) with the `grade_derivation=claimed` disclosure; its schema evolution is
Q2.

## 4. Open questions — neutral, none concluded here

- **Q1 — The drift refusal's second remedy has no mechanism** ("verify against the registry
  of the time"): (a) reword to re-launch-only; (b) snapshot the whole descriptor into the
  plan; (c) a flag taking an asserted launch-time config path. *(Claude)*
- **Q2 — Field-by-field snapshotting recurs the R24#1 shape.** Options: whole-descriptor
  snapshot; keep per-field with L2's completeness rule; status quo. Any main-seat/grade
  serialization (L5) is the same schema evolution. *(both drafts)*
- **Q3 — Packet persistence** for V1/D4: retain the dispatched packet beside the bundle; a
  runtime-owned immutable reference + digest; or verification accepts the packet explicitly
  with no retention story. *(GPT)*
- **Q4 — `passes` on a one-trial receipt is never read:** validate unconditionally under D3;
  refuse `passes` on a one-trial method; or leave inert. *(Claude)*
- **Q5 — Raw vs folded shape:** one schema with phase doors (today, plus D1's raw-passes
  refusal); a versioned folded form preserving per-pass ids (would give V5 global
  uniqueness real subjects); or bundles accepted only from an authenticated fold. *(both)*
- **Q6 — Aggregation evidence:** leave non-achievement-bearing (today; outside the
  falsifiable set); a separate deterministic adjudication step over structured pass results;
  or bounded adapter-reported aggregation evidence. Teaching the registry-free fold
  descriptor semantics would reopen D-20260816-c0067f/-0ed011. *(GPT, held against the
  Claude draft's outside-set placement — adopted as a question, not an invariant)*
- **Q7 — Producer provenance:** keep the trusted-local-operator boundary; authenticate
  receipts/folds with a launcher-owned secret; or verify against host execution logs. *(GPT)*
- **Q8 — Pre-migration records** (before `controls`/`evidence` existed) have refusal as
  their only path: keep; one-time migration; or a schema version distinguishing "old" from
  "tampered". *(Claude)*
- **Q9 — Should the file-based fold optionally hold the plan?** Earlier refusal vs the
  fold's deliberate registry-blindness — an optional auditor-side plan input changes the
  premise of three standing decisions and reopens them if pursued. *(Claude)*

## 5. Review checklist — the violation to look for

**Launch** — L1 a second decodable record, or an authored value in prose with the marker ·
L2 an adjudication bar read from current config; an unknown-keyed record parsing clean ·
L3 a selectable row with a null/empty seat field; a DROPPED base or a live-looking DROPPED
row · L4 `base.status=DROPPED` accepted anywhere · L5 a header outside its enum;
`best_grade` ≠ derived; an underivable row grade · L6 `panel` in the optional map; one id on
two rows · L7 different argv, identical contracts; a spelling-dependent collision ·
L8 a tier advertised that argv does not bind.

**Dispatch** — D1 wrong schema/unknown keys/bool exit credited; a raw receipt carrying
`passes` · D2 a main-context, id-less, or id-reusing receipt credited · D3 a non-digest or
empty-digest result credited at any position · D4 packet check passing on absence or non-hex equality; a supplied packet whose digest or
embedded plan is not re-derived; a packet-less verify that claims `packet_binding=bytes`,
or renders no binding line at all · D5 an omitted seat matching a row · D6 a required
evidence field absent/empty on a credited receipt; a control marker demanded where never
declared · D7 trials satisfied by duplicates or non-digests · D8 a partial receipt visible
to a concurrent reader.

**Fold** — F1 a singleton skipping validation; a defect visible only on a later pass ·
F2 outcome changing with group order; mixed presence folding clean; a descriptor value bar
inside the fold (decision violation) · F3 a pass missing from `passes`; a crash folded
behind a sibling's exit 0; an invented control field · F4 a bundle with missing anchors,
unknown keys, or a packet hash not taken from the file.

**Verify** — V1 an anchor-less bundle adjudicated · V2 a bar taken from current config;
drift silently accepted · V3 a defaulted bar · V4 `row_host=None` skipping the host
predicate · V5 duplicate selected receipts adjudicated first-wins · V6 a foreign receipt in
the denominator, keyed by label, or silently dropped; verification mutating a launch field ·
V7 exit 0 without complete; a traceback where a refusal is contracted.

**Save** — S1 any authored value reloading different, renamed, or absent; runtime evidence
saved as configuration · S2 Save As reading the destination name · S3 two effort homes; a
contradiction resolved · S4 a drop or default without a named refusal; a non-routed launchable profile refused · S5 a save reported OK that reparses different, loses a concurrent save, or shows a
partial file · S6 a mission/trigger surviving into (or silently shed from) a saved preset.
