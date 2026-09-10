# Pluggable review methods + capability onboarding — DESIGN

Status: **DESIGNED 2026-07-26. All eight stages landed except stage 7's receipt producer**
(measured against the code 2026-08-03 — see `Corrections` C46; the header previously said stages
6–8 remained, and all three of those claims were stale). The seam, the enum replacement, the gate
strategy, the independence report, and a staged plan with falsifiable controls are settled below.
Stage 1 is the golden characterisation (`gates/capture-review-goldens.py`, 192 cells); Stage 2 is
the dual reader plus the legacy IR; stage 3 is the vertical slice.

What remains is stage 7, and it is **larger than a missing producer**. No adapter emits receipts,
so `achieved_grade` stays `UNKNOWN_UNTIL_RECEIPTS` and every clean verdict is `PROPOSED` — but
the 2026-07-27 design review found (C48, findings #4/#8/#11/#12) that the verifier cannot yet
tell adapter-produced evidence from hand-authored JSON, so a producer built on today's schema
would emit receipts a forgery is indistinguishable from. The schema question comes first.

**Stage 3 ran as the falsifying stage and did not falsify the seam** (2026-07-27). `panel`,
`onto` and `ultracode` are encoded purely as `[review_methods.*]` descriptors and reach the
contract through one `derive_review_mechanism` + `render_review_method` pair. No shipped method
needed an `if method == "onto"` branch, and none exists. The control that proves it is a canary
whose identifier is generated at runtime — it projects with no code change, and the gate asserts
the name appears in no source file. Breaking the seam (making the renderer accept only known
method ids) makes that gate fail.

**Stage 4 landed the opt-in** (2026-07-27). Authoring `[presets.<n>.review]` *is* the opt-in:
that preset resolves through `resolve_composable_review`, which grades every method against the
main seat on the §4 ladder and returns a structured report. Shipped presets stay on
`review_setup`, so the default launch is untouched and the 192-cell golden is byte-identical
across stages 2, 3 and 4. `review_setup` is `None` on a composable plan, which is what keeps it
off the legacy renderer — a parity assertion pins exactly that, because projecting it as a legacy
name would silently mean "no review".
Read `Corrections` before acting on any claim here — three were overturned on 2026-07-26.

Provenance: drafted as **dual-provider frontier design drafts** — one blind packet dispatched
unchanged to `claude-fable-5` at max (native subagent) and to `gpt-5.6-sol` at max
(`codex-run --profile hermetic --sandbox read-only`, so it loaded neither this corpus nor any
user config). Neither draft saw the other. Synthesis and disposition at the end of this file.

**Absorbed 2026-07-26:** `design/tui-review-area.md` (2026-07-20) is the *surface* half of this
same item and is superseded by this file — written six days earlier, neither doc referenced the
other. Its requirements are folded into `## Surface`; that note stays as the dated record.

## Goal

The corpus mandates review discipline in terms of *kind* — "run independent adversarial review
across distinct lenses… different-kind divergence is the expected signal; act on the union."
But the launcher can only express three review routes. When a user's reachable reviewer is not
one of those three, the discipline silently narrows to whatever shipped.

> **The limit on review discipline should be which reviewers a user can actually reach — not
> which ones this repo happened to ship.**

Pluggability is downstream of that, not the goal itself: because interface and method are
degrees of freedom, anything reachable can be registered.

## Principles (decided)

Independent of interface (mcp/cli/api/subagent) and of method (ultracode, onto, adversarial…):

- **I1 — a model different from the designing model verifies.** Graded, best first:
  different provider > different model within a provider > **higher** effort on the same model.
  "Different effort" means higher; equal or lower earns no credit.
- **I2 — verification happens in an isolated context.** A **hard gate, not a grade**: without
  isolation it is not review at all, at any I1 grade.

Method/perspective diversity is a further axis, but it **cannot be machine-forced** — which is
why I1+I2 are the enforceable minimum. A gate must never assert that perspectives were
genuinely diverse. The one exception is mechanical: whether N passes with randomised ordering
were *requested* is checkable, even though "were they really different lenses" is not.

Even at the same model and same effort, isolation plus two or more distinct perspectives is a
**real review floor**, not a non-review — supported by the generation/verification asymmetry.

### Shape: a base plus composable axes, not a ladder you pick from

- **Base — always present, zero installation:** isolated context + multi-perspective panel.
  Review is therefore never "unavailable"; losing an axis is degradation.
- **Axes compose on top** as availability and cost allow: provider diversity, model diversity,
  higher effort, specialised tools. This is accumulation, not rung selection.
- `onto` and `ultracode-for-codex` are **optional installs, never dependencies.** The author
  uses them; a general user must not need them.

### External evidence behind these choices

- Self-preference bias in LLM judges is real, and its mechanism looks like
  **perplexity/familiarity** rather than self-recognition — so *same-family* models share it.
  That is why provider difference outranks model difference within a provider.
- Larger/more capable models show **stronger** self-preference, and for code review
  specifically model scale does not predict review quality. **Tier is a weak proxy; family
  diversity dominates tier** — "the reviewer should be a higher tier" is a heuristic, not a rule.
- A panel of diverse smaller judges beats one large judge, with less intra-model bias and far
  lower cost. Breadth is the workhorse.
- Position bias is systematic; the standard mitigations are order randomisation, swap
  augmentation, and multi-trial voting.
- No external evidence was found for the *higher-effort* rung specifically. It is kept as
  plausible and internally consistent, and marked unsupported.

### The corpus does not state these principles yet

Checked 2026-07-26: the globals and guides carry adjacent rules but not these. `CLAUDE.md`
has the **convergence heuristic by reviewer *kind*** (lens diversity, not model difference) and
"Independence: verifying or reviewing your own work always spawns" (spawning is not a different
model). The cli guide describes `hermetic` reach as an independent lens — context isolation, but
expressed as one Codex profile rather than a general invariant. Dual-**provider** drafting is
mandated for *design*, not for review.

So the corpus states provider difference for design and kind difference for review, and states
neither model difference for review nor isolation as a general invariant. **The launcher must not
enforce a rule the globals do not state**, so this item has a corpus half:

- **Global** (merge into the existing review bullet, not a new one — the global is a token
  budget): isolation is required; model independence is graded; method diversity is a separate
  axis that cannot be forced.
- **`cli-multi-model-workflow`** review section: the grade ordering, the higher-effort
  condition, the ≥2-perspective floor condition, and how isolation is realised per mechanism.

## The obstacle (verified against real code 2026-07-26)

Capability **presence** is already data-driven; capability **protocol** is not.

| What | Where it lives today |
|---|---|
| Which tools exist, their command + install hint | `launch/agent-launch.toml` `[capabilities.onto]`, `[capabilities.ultracode]` — data |
| Which review setups exist and what each requires | `REVIEW_SETUPS`, `launch/agent-launch.py` — **hardcoded** |
| Per-setup host requirements | `{"codex": ("ultracode",), "claude": ("ultracode",)}` — **hardcoded** |
| onto's provider enum | `ONTO_PROVIDERS` — **hardcoded** |
| How to invoke each reviewer | Bespoke prose per reviewer in `_cross_review_route` — **hardcoded** |
| What the gate checks | Literal contract substrings, e.g. `"so onto runs OpenAI/Codex"` — **per-reviewer** |

**The deeper blocker is the enum itself.** `review_setup` is a pick-one-of-six enum, and
`REVIEW_ROUTES["hybrid"] = ("onto","native","ultracode")` is a *hardcoded named combination* —
the existence proof that the concept is a set, not a choice. Adding an nth method to an enum of
alternatives costs 2ⁿ names.

Also verified: `wrappers/codex-helm.sh --mode review` is "HELM main, **fan-out allowed**,
read-only" with `--max-threads N`. **Multi-perspective review over subprocesses already ships**,
so a panel is *not* bound to native subagents and can be cross-provider.

## Design

### 1. Seam

**capability + method split**, with the mechanism derived by core and never configured.

- A **method** says *how to review*: instructions, perspectives, trial policy, result
  normalisation, and an optional capability operation.
- A **capability** says *how an installed tool exposes an operation*.
- A **binding** says *which verifier adjudicates*: `{provider, model, effort, service_tier}`.
- **Core** picks an isolation-capable mechanism that can deliver that binding. Configuration
  never names MCP, CLI, API, or subagent.

**Data locations.** Shipped methods and capabilities in `launch/agent-launch.toml`. User
extensions in `~/.config/agent-launch/review-methods.local.toml`, sibling to
`presets.local.toml` — merged at launch, **never deployed, never `verify_match`'d**. A user key
colliding with a shipped key is an error, never a silent override.

**Hosts gain a provider.** `[hosts.codex] provider = "openai"`, `[hosts.claude] provider =
"anthropic"`, reverse mapping unique. A binding to a provider with no configured host is
invalid because its effort cannot be validated or projected — consequently `grok` and
`lmstudio` stay valid *onto-internal* providers but cannot be **credited** reviewer bindings
until a host and effort vocabulary exist for them.

**Binding.** `provider` (required, maps to exactly one host), `model` (required),
`effort` (required, `validate_effort(provider_host, …)`), `service_tier` (default `"disabled"`).
Host-level effort validation is a **floor, not the provider's authority**: both providers publish
the valid set per *model* (`supportedReasoningEfforts` / `defaultReasoningEffort` in the codex
model catalog), and a binding already carries a model, so a host-union check accepts pairs a
specific model may reject. Tighten to the model when a per-model set is readable; until then the
host set is a documented approximation, not a claim of validity (see Corrections, 2026-07-26).
A binding may instead reference `tier` — a key into the resolved host's `[hosts.<h>.tiers]` —
which satisfies model⇒effort **by construction**, since tiers already bind the pair. `tier` XOR
`model`; `model` without `effort` is schema-rejected. No contract may contain a
`<review tier>` / `<e>` placeholder: the exact pair resolves before injection, so the designer
never selects the verifier's rigour.

**Method descriptor.** `label`, `description`, optional `capability` + `operation` (required iff
capability present), `instructions`, `perspectives`, `trials` (≥1), `order` (fixed|randomized),
`swap_augmentation`, `aggregation` (union|majority), `output = review-v1`, and a **required pair**
of severity fields. `severity_emits` states what this reviewer actually reports, verbatim — a
claim about the world that only its owner can supply, and the one thing the launcher cannot
find out for itself. A name is a **label**: letters and digits in any script, plus
` ._-+=<>#()/`, no leading or trailing space, and never the clause separator ` => ` itself.
The launcher renders that rule from the same constant it enforces, so the screen and the
parser cannot disagree (see Corrections, 2026-07-28).
`severity_map` is the owner's decision about how those land on the canonical ladder
(`blocker|high|medium|low|info`), and must cover `severity_emits` **exactly** — no gaps and
nothing invented. An unmapped external severity makes the result malformed — it cannot produce
a clean verdict, which realises requirement R6. Without `severity_emits` totality is
undecidable, because a wrongly copied map and a genuinely correct identity map are the same
object (see Corrections, 2026-07-27).

The reserved `panel` descriptor additionally requires **no capability**, ≥2 distinct
perspectives, and ≥2 trials; new-schema defaults are 3 trials, randomised order, swap
augmentation, majority aggregation. These are *requested mechanical controls* — unique labels do
not prove genuinely different perspectives.

**Capability operations** extend the existing registry rather than creating a second one:
`command`, `install`, `credential_env` (name only, never the secret), and a non-empty list of
**offers** `{operation, adapter, hosts}`. Core-owned adapter tags: `exec-stdio-v1`,
`mcp-stdio-v1`, `host-workflow-v1`, `http-json-v1`. These are **protocol codecs, not method
identities** — multiple offers may expose the same operation, and adding a method that reuses an
existing tag is data-only. Adding an *interface* is a core change; adding a *method* is not.

Registry data may **never** declare `isolated = true`. Isolation, exact binding projection, safe
tokenization, and read-only dispatch are properties of core adapters, not author claims.

**Mechanism derivation** (core): resolve provider → host; enumerate core reviewer mechanisms
(fresh host subprocess, hermetic Codex subprocess, `codex-helm --mode review` fan-out for a
multi-perspective binding, exactly-pinned native child, stateless API adapter); **discard any
candidate that cannot guarantee a fresh context or the exact model/effort**; join the method's
capability operation to a compatible offer; select deterministically. I2 is enforced *by
construction* — the mechanism menu contains only isolated shapes, so there is no in-main-context
mechanism to derive and a tool whose protocol requires the designing context is structurally
inexpressible rather than merely prohibited.

**Credited verifier.** The credited reviewer is the exactly-bound isolated one. `onto` and
`ultracode` output may be supplied to it **as evidence**; their opaque internal model choice or
internal fan-out is **not credited toward independence** unless a core adapter can independently
attest identity and isolation.

**When the derived mechanism is unavailable:** try another mechanism for the *same exact
binding* first. An optional method is never silently rebound to a different provider/model/
effort — it becomes `unavailable` and the base remains. If the preferred base binding cannot
resolve, base falls back to the exact main binding and reports the lost I1 axes. An
unprojectable non-disabled service tier is dropped and reported, never suppressing the review.
If **no** isolated mechanism can deliver even the same-main base floor, the managed launch is
invalid — it must never label a same-context call a review.

### 2. Enum replacement

`review_setup` becomes `base panel binding + map<method_id, binding>`. Adding method N adds one
descriptor and one binding entry. The map keys *are* the set, so no combination name exists.

The six legacy names survive only as a **quarantined compatibility reader** — not method IDs,
not composable:

| Legacy | Compatibility behaviour | New-schema equivalent |
|---|---|---|
| `none` | exact old no-review | base only (no managed equivalent) |
| `native-panel` | exact old native route | base panel only |
| `slash-review` | exact old slash route | base + `host-review` |
| `onto` | exact old onto-only route | base + `onto` |
| `ultracode` | exact old route | base + `ultracode` |
| `hybrid` | exact old hardcoded tuple | base + `onto` + `ultracode` |

Both `review_setup` and `[preset.review]` on one preset is a validation failure. Shipped presets
initially stay on `review_setup` and therefore exercise the compatibility reader; **review
authored in the editor emits only the composable form, and inherited legacy review round-trips
verbatim** (amended 2026-07-27 — the original "new saved presets emit only the composable form"
conflated a newly *authored review* with a newly *saved file*, and as written is unsatisfiable:
`none` has no composable form, because managed review always has a base panel). This quarantine
is what reconciles "new managed review always has a base panel" with "existing
`none`/slash-only/onto-only behaviour must not change".

**Accepted cost of the amendment:** a user-owned preset file may carry legacy names past stage 8,
so the compatibility reader cannot retire until a user-file migration story exists. Cheap for a
single practitioner, and named here so retiring the reader is a decision rather than a surprise.

**`review_family` is removed from the new schema.** Provider independence is computed per method
from its own binding. The compatibility reader interprets `cross` as today's opposite-provider
routes and `same` as today's same-provider routes; new configurations reject the key and can
express mixtures the global flag never could. A missing opposite host no longer mutates a global
flag — the affected bindings fail individually, optional methods drop, base falls to the
same-main isolated panel.

### 3. Gate

Parity moves from **per-reviewer prose parity** to **typed source-to-projection parity**. New
checks join `check_parity.py`'s named-check registry (`--list` / `--only`).

**Asserted**, for every selected method instance in every shipped preset × host projection:
descriptor and capability operation resolve; binding complete (model/effort inseparable);
provider maps to one host and effort validates against it; new-schema plans contain the base
panel; the selected mechanism is a core isolation-capable adapter; exact provider/model/effort
are projected with no dispatch-time placeholder left; unsupported service tier is absent from
argv and reported dropped; capability commands resolve to the same absolute paths placed in the
dispatch recipe; a missing optional capability yields `unavailable` with base still effective; a
failed-I2 candidate never appears in effective review; severity maps are total; the contract
carries a canonical `ReviewPlan/v1` object that round-trips to the typed plan, and the
human-readable lines are generated from those records with every selected, degraded, and
unavailable method appearing exactly once.

**Mechanism templates are pinned once per mechanism** (`--profile hermetic`,
`--permission-mode plan`, `--mode review`). This is legitimate precisely because mechanisms *are*
core code — the illegitimate thing was pinning per-reviewer prose. One pin then covers every
method, including unseen ones, that derives that mechanism.

Structural checks: `install.sh` contains **no `deploy_file` targeting the registry filename**
(enforcing "never deployed" structurally rather than by convention).

**Deliberately not asserted:** that review ran; that auth or a network call will later succeed;
that a model really used the configured backend absent a receipt; that perspectives were
genuinely different; that a tool's internal fan-out used diverse models; that findings were
correct; that a service tier was active without a supported projection and receipt; anything
about the user registry (its validation is launch-time and loud — the gate never reads it).

**Non-vacuity controls**, all three required per run:

1. **Real subject count.** Fail if zero method instances were inspected, or if no base subject
   was inspected, or if no capability-backed subject was inspected.
2. **Unknown-method canary.** Build a temporary registry with a randomly named method and a
   temp executable, select it in a temp preset, and prove the *generic* path projects it. Its
   identifier must not appear anywhere in core code.
3. **Mandatory negative mutation.** Take a real non-empty emitted plan and separately delete a
   selected method, change its effort, and remove its isolation evidence. **All three mutations
   must make the assertion fail**; if any mutated plan stays green, the gate itself fails.

**Retiring the existing literal pins** happens only after an old-check → new-check coverage map
shows zero gap, each existing pin accounted for.

### 4. Independence report

Independence is a **per-method vector with an ordinal I1 grade**, not a global cross/same
boolean. Given main seat `M` and resolved reviewer seat `R`:

```
isolation not core-attested   -> NOT_REVIEW          (excluded entirely)
R.provider != M.provider      -> provider_difference
R.model    != M.model         -> model_difference
effort_order(R) > effort_order(M) -> higher_effort
otherwise                     -> perspective_floor   (base panel; still a real review)
```

Different-but-lower effort earns no credit. Service tier never affects the grade. All method
rows are retained; `overall.best_grade` is a summary only, and multiple ready methods are
reported as *coverage*, never as proof of genuine method diversity.

Per-method status: `OK`, `DEGRADED(reason)` (runs at a lower grade than requested),
`DROPPED(reason + install hint)` (does not run), `ADVISORY(field)` (configured but not
deliverable — `service_tier` until a receipt exists; `effort` when a capability's seat does not
consume it). The status kind stays, but **onto is no longer an instance of it**: its seats do
consume a bound effort (Corrections, 2026-07-26). No shipped capability is a known instance
today, so `ADVISORY(effort)` must be reachable without being reached — a gate asserting it fires
would be asserting a defect.

**Achieved ≠ available.** Launch-time availability is reported as `projected`; the plan carries
`achieved_grade: UNKNOWN_UNTIL_RECEIPTS`. Real achievement needs adapter-owned receipts: plan and
method IDs, packet hash and non-empty result hash, a process/request identifier proving a fresh
dispatch, actual provider/model/effort where observable, exit status, and for panel controls the
pass IDs, ordering seed, and swap group. **A model echo is not sufficient evidence.**

`PROPOSED` is kept and sharpened rather than retired: a clean verdict without a valid receipt is
`PROPOSED`; a same-model/same-effort isolated panel is a real floor whose clean conclusion is
`PROPOSED` with `grade=perspective_floor`; an I2 failure is **not** a "PROPOSED review" but
`NOT_REVIEW`. `PROPOSED` qualifies verification status, never severity — findings keep the
canonical ladder.

### 5. Staging

Each stage carries a control that could fail.

1. **Characterise today.** Snapshot normalised dry-run argv, contract, effective/dropped/floor,
   and failure status across six setups × both hosts × cross/same × capability present/missing ×
   delegation on/off. *Control:* matrix asserted non-empty; snapshots stored before any refactor.
2. **Dual reader + legacy IR.** Parse the new schema but leave shipped presets on
   `review_setup`, routing legacy plans through a compatibility IR and the old renderer.
   *Control:* every stage-1 case byte-identical after path normalisation; both old and new keys
   together must fail.
3. **Vertical slice — THE FALSIFYING STAGE.** Encode panel, onto, ultracode and a randomly named
   third-party method purely as descriptors through one generic resolver and renderer against
   fake endpoints. *Control:* the random method projects with **no code change**; malformed
   model/effort pairs, unknown operations, incomplete severity maps and unsupported adapter tags
   all fail; missing endpoints degrade exactly as specified. **If any shipped method needs an
   `if method == "onto"` branch, or its protocol cannot pin an isolated reviewer through the
   declarative surface, stop and redesign the seam.**
4. **Composable review behind an explicit opt-in.** Base + method-map resolution, mechanism
   choice, service-tier degradation, structured report. Shipped defaults unchanged. *Control:* a
   matrix over provider difference, model difference, higher effort, same-seat floor, lower
   effort, service-tier loss, missing capability and I2 failure yields exact expected reports.
5. **Replace the parity assertions.** Schema/projection checks, subject counts, unknown-method
   canary, mandatory mutations. *Control:* full parity green, and each mutation independently
   makes the new check fail. Remove the old prose pins only after the coverage map is clean.
6. **Save/UI and durability.** The TUI edits a method map and exact bindings; saved presets emit
   only the new schema. *Control:* round-trip arbitrary N-method sets; adding method N changes
   exactly one map entry; a sentinel local registry keeps its digest across install/verify.
7. **Runtime receipts where mechanisms permit.** Until then reports stay `projected`.
   *Control:* three valid non-empty pass receipts can mark controls run; missing, duplicate,
   same-context, wrong-packet or identity-mismatched receipts cannot mark independence achieved.
8. **Separately approved behaviour migration.** Only then migrate shipped presets:
   balanced/fast-batch become base-only; `deep-review` and `session-distill` become
   base + onto + ultracode; `solo` moves off `none` only with explicit approval; `vanilla` stays
   bare. *Control:* an A/B in which the control profile's default invocation stays identical to
   stage 1 while only the opted-in treatment emits the new plan. **Plumbing and default-policy
   changes must never share a release switch.**

## Decided questions

| | Question | Decision |
|---|---|---|
| Q1 | Data-only or code-carrying? | **Data-only** (inherited from the ecosystem's prose-only lever). A tool whose protocol cannot be expressed declaratively is out of scope. |
| Q2 | Where does onboarding live? | **A trigger word backed by a deterministic submit subcommand**, the `learn!` shape. Installing a tool happens mid-task; it is the only form that does not demand a launcher restart. The launcher Review area (see `Surface`) is for selecting and installing, not registering. |
| Q3 | Who owns the emitted config? | **User-owned, never deployed, never verified against a shipped copy** (inherited from adapter-split). |
| Q4 | How does parity gate an unseen reviewer? | **§3** — typed projection parity, mechanism templates pinned once per mechanism, plus a randomly-named canary through the real path and mandatory negative mutations. |
| Q5 | One mechanism or two? | **Reviewers only, first.** A reviewer has a verifiable output (a report mapped to the severity ladder); general environment setup does not. Generalising with zero real registrations repeats the conflation that got contract v1 rejected. |

## Surface (absorbed from the TUI review-area note, 2026-07-20)

Where a user meets the contract. Requirements, not a design — shape decided at pickup.

- **A dedicated Review area in the launcher**, same visual grammar as Session distill. Its status
  panel is a projection of the resolved plan plus capability presence — read-only, so the
  launcher stays read+dispatch.
- **Install a missing capability on the spot** through the existing `[capabilities.*]`
  `{command, install}` registry and `install.sh handle_capabilities`, re-probing after; never a
  second installer.
- **Per-method execution choice** expressed as the binding, never as an interface field.
- **Show the actual backing model, not the label** — from receipts where available. A panel that
  repeats a configured label cannot detect family collapse, the failure this area exists for.
- **A severity map is a participation requirement**; a method without one must not become
  selectable.

## Open evidence

Ordered by how much they would change the design.

1. **Are `onto` / `ultracode` verifiers or evidence sources?** The design credits only the
   exactly-bound isolated reviewer and treats their output as evidence — honest, and it always
   satisfies effort pinning, but it costs more and may not match how those tools are meant to
   run. A live protocol trace showing the isolation boundary, the exact backing
   provider/model/effort, and who emits the final verdict would settle it.
2. **`protocol` / offer expressiveness.** Real third-party tools may need steps the declared
   adapter tags cannot carry, which would leak mechanism back into data. Settle by onboarding one
   real external tool at stage 3.
3. **A Claude fresh-process canary** proving `-p` neither resumes nor inherits the designing
   conversation — I2 currently rests on this being true.
4. **Adapter-owned provider/model receipts.** Configured argv alone cannot detect a backend
   fallback silently rerouting two "different" verifiers to one model. **A first real producer
   arrived 2026-07-27, from outside this repo:** onto's override now returns a seat report
   (`reached`/`dropped`) alongside the settings, and discloses it with the resolved route's
   `billing_mode`, the effective auth, and whether that auth was defaulted — on the runner's
   warning channel, so it surfaces as `environmentWarnings` in every `onto_review_read`
   projection and in the `onto_prepare_review` result. That is call-time evidence of the exact
   seat, which is precisely what §4's `achieved_grade` needs and what no launcher-side
   projection can synthesise. Wiring the `onto` method's adapter to consume it is now the
   cheapest receipt producer available, ahead of the panel.
5. ~~**Partial seats.** onto's `llmOverride` takes provider + model only, which makes a bound
   `effort` **advisory** there.~~ **RESOLVED 2026-07-26 — the premise was false; effort is
   delivered, not advisory.** See Corrections. The narrower remainder — the overlay only reaches
   seats that already carry an explicit `llm` block — was **MEASURED 2026-07-27 and is real, and
   worse than "may".** On a minimal settings file (`{schema_version, review:{mode}}`) resolution
   populates *no* seat `llm` blocks, so a full four-field override leaves all three actors
   UNTOUCHED, the call succeeds, and nothing reports it; the override-scoped support gate then
   passes over zero seats. A user in that state gets same-family review while the contract claims
   cross-family. **This is the standing argument for receipts (#4): a projected grade cannot see
   it, and only an adapter-owned receipt can.** Filed against onto as F1, and **FIXED UPSTREAM the
   same day**: an override reaching zero primary dispatch seats is now fail-loud
   (`llm_override_reached_no_seat`). onto's own disposition also answered the question this item
   left open — what a review dispatches when the override is dropped. It does not fail: the
   profile resolves to `codex/codex` on local codex availability alone, with `model = null`.
   **The family collapse was real, not hypothetical**, and it took the tool's own measurement to
   establish it. Record: `~/Documents/onto-mcp/development-records/audit/20260727-llm-override-consumer-findings.md`.
6. **Launch-time service-tier projection.** ~~Neither CLI exposes one today.~~ **CORRECTED
   2026-07-26 — codex does; the probe used the wrong key** (`model_service_tier`, inferred from
   the neighbouring `model_reasoning_effort`; the real key is `service_tier`). Claude's CLI still
   has none. Shipped bindings stay `service_tier = "disabled"` and the gate still must not assert
   delivery — that holds on the receipt requirement, no longer on "unprojectable". Reopened as a
   design question: whether the codex route should carry a tier at all. See Corrections.
7. **Host and effort semantics for grok / lmstudio** before they can be credited bindings.
   **BACKLOGGED 2026-07-27 with harder evidence than "unverified".** `ONTO_PROVIDERS`
   (`launch/agent-launch.py`) admits `grok` and `lmstudio`, but onto's own
   `.onto/authority/supported-models.yaml` carries **no model for either** — checked directly.
   ~~So the pair validates at launch and then fails at review time, every time.~~ **CORRECTED
   2026-07-27: the second half was never established.** The registry entry is missing, but onto's
   review-side gate (`review-invoke.js:2081`) is scoped to runs that *carry an override*, so
   "fails at review time, every time" does not follow from a missing entry and was not measured.
   What the pair actually does at dispatch remains unknown — which leaves the item open on its
   original terms rather than settled against them. Nothing shipped
   selects them, which is why this is backlog rather than a defect: the cost is paid only by
   someone who configures one. Two ways to close it — drop them from `ONTO_PROVIDERS` until onto
   registers models, or keep them and make launch validation consult the registry. The second is
   the better shape (validate against the authority rather than a hand-copied enum) and the more
   work, since the registry is another tool's file and reading it couples the launcher to onto's
   layout.
8. **The design review ran and was never triaged.** `§4.6` was closed on 2026-07-27 by an
   adversarial pass over this document — `ultracode-for-codex` 0.6.1, five lenses in parallel
   plus one refuter per finding defaulting to `refuted=true`, 23 agents, every lens reading
   DESIGN.md rather than the code. **18 raw findings, 16 survived refutation.** The record is
   `design/reviewer-registry/reviews/2026-07-27-design-review.md`.

   What is open is the triage. That file says "the triage lives in `Corrections`" and
   `Corrections` contains no reference to the review, to `§4.6`, or to any of the sixteen — so
   the pass happened, the evidence was written down, and nothing was adjudicated. Four of the
   sixteen (#4, #8, #11, #12) are the receipt schema, which is the one stage still unbuilt, and
   they argue it cannot yet distinguish adapter evidence from hand-authored JSON. That is a
   prerequisite for stage 7, not a footnote to it.

   Two things keep this findable rather than lost again: the record's directory is untracked, so
   a clone does not have it, and this document said until 2026-08-03 that the design had never
   been reviewed — a claim inherited from a handoff written the day after the review ran, and
   promoted here without being checked against the file sitting beside it.

## Synthesis and disposition

The Codex draft is the skeleton; three parts of the Claude draft are grafted in.

**Converged independently** (high confidence — different-kind reviewers agreeing): the
capability/method split; mechanism derived not configured; model⇒effort made structurally
unrepresentable; a user-owned registry with collision-as-error; `hybrid` as the existence proof
for base + set; `review_family` reduced to a per-method binding default; legacy names quarantined
for byte-parity with behaviour change deferred to its own step; per-reviewer prose pins replaced
by mechanism pins plus an unknown-method canary and mandatory mutations; and — independently —
the *same* falsifying stage.

**Diverged, and what was taken:**

- *Credited verifier.* Codex treats `onto`/`ultracode` as evidence into an exactly-bound
  reviewer; Claude treated them as reviewers with `ADVISORY(effort)`. **Codex taken** — crediting
  an opaque internal model choice as independence is exactly the claim this design exists to stop.
- *Adapter typing.* Codex proposed typed offer tags; Claude explicitly rejected them for
  free-form prose, arguing a tag re-privileges interface. **Codex taken** — a gate cannot
  validate free-form prose, and the requirement that the gate stay meaningful for an unseen
  reviewer outranks the aesthetic objection. Codex's framing (codecs, not identities; many offers
  per operation; new methods on existing tags are data-only) already defuses it. Note that
  Claude's own top risk was precisely that its prose would not be expressive enough.
- *Receipts.* Only Codex proposed them. **Taken** — without receipts "achieved independence" is
  unfalsifiable, and falsifiability is the whole discipline here.
- *`PROPOSED`.* Claude retired it into three labels; Codex kept and redefined it. **Union** —
  `DROPPED`/`DEGRADED` as status, `PROPOSED` as a receipt-bound verdict qualifier. Reusing the
  existing term is the concept-economy answer.
- **Grafted from Claude:** `tier` XOR `model` (a tier reference satisfies model⇒effort by
  construction, reusing an existing concept); the structural check that `install.sh` deploys
  nothing to the registry filename; and the requirement that the old literal pins are retired
  only after a zero-gap coverage map.

**Caught by Codex alone**, against a criterion deliberately withheld from both packets (that
`onto`/`ultracode` must stay optional installs): the shipped `deep-review` and `session-distill`
presets currently request `hybrid` and therefore assume the author's environment — handled in
stage 8. Codex also derived a hole the packet did not state: `grok` and `lmstudio` have no
configured host, so their effort cannot be validated and they cannot be credited bindings.

## Corrections

**2026-07-26** — three claims above were re-derived against installed artifacts and did not
survive. Probed: `onto-mcp` at `/opt/homebrew/lib/node_modules/onto-mcp`, `codex-cli 0.145.0`
(`/opt/homebrew/Caskroom/codex/0.145.0/codex-aarch64-apple-darwin`), `claude 2.1.220`.

**C1 — `effort` is delivered to onto's dispatch, not advisory** (was Open evidence #5). The live
tool schema accepts `{provider, model, effort, service_tier, auth}` — provider⇒model is the only
`dependentRequired`. The value survives the whole chain: `applyLlmBlockOverride` overlays it onto
every configured seat (`discovery/llm-override.js`), `model-switcher.js` maps it to
`reasoning_effort`, and `callCodexCli` (`llm/llm-caller.js`) pushes `-c
model_reasoning_effort="…"` into argv. Providers that cannot honour it fail loud
(`assertNoUnsupportedReasoningEffort`).

**C2 — codex exposes a launch-time service tier** (was Open evidence #6). `service_tier` is a
first-class `ConfigToml` field, is present on `ConfigProfile`, and the app-server protocol
documents *"Override the service tier for subsequent turns"*. The earlier probe tested
`model_service_tier`, which does not exist — and because `codex -c` accepts arbitrary keys, its
exit 0 said nothing. Claude's CLI genuinely has none: `--help` matches zero of
fast/speed/tier/priority/flex/service, and Anthropic's tier controls are API-side (`speed:"fast"`,
Opus 5 / Opus 4.8, Claude API only; **Priority Tier explicitly excludes Opus 5**, which is the
HELM seat — a Priority Tier request naming it fails validation).

**C3 — effort validity is per-model, not per-host** (tightens §1). The codex model catalog carries
`supportedReasoningEfforts` / `defaultReasoningEffort` per model, and `serviceTiers` /
`defaultServiceTier` alongside them. `HOST_EFFORTS` is therefore an approximation of a
model-level fact.

**What did NOT change: `HOST_EFFORTS` is correct as written.** Verified against provider
artifacts, which is the authority — an optional tool's narrower vocabulary is that tool's lag, not
a constraint on this repo. Claude accepts exactly `low, medium, high, xhigh, max` (`--effort
<level>`, matching the API's `output_config.effort` independently); codex's enum is `none,
minimal, low, medium, high, xhigh, max, ultra`, so all six configured values are valid and
`ultra` is real (the binary deprecates an older multi-agent flag in favour of `effort: "ultra"`).
onto's own accepted set omits `max`/`ultra` for openai and is enforced only on its
dispatch-fallback path — so agent-bios must validate before injecting rather than rely on onto to
reject, but must not narrow to onto's set.

**2026-07-27** — a stage-6 precondition check overturned the stage-4/5 completion claim.

**C4 — the composable path was never wired to the live launch.** Stages 1–5 built and
gated the reader, resolver, grading and report, but `resolve_composable_review` and
`render_review_report` were called only from `gates/check_parity.py`, and `build_plan`
read the `ReviewPlan` only to keep `legacy_setup`/`legacy_family`. Verified by running
it: a composable preset projected `Review family=None. Review setup=None:` with zero
routes, against a legacy contrast that projected `Review setup=hybrid:` with real ones;
saving such a plan raised `cannot serialize preset value: None`; and `ReviewPlan/v1`
(§3) existed in this document and nowhere in code. This is the inert-until-consumed
trap: gating a resolver in isolation proves the resolver, not the feature. Two further
defects were latent behind it — the report re-derived its own instruction slots and
emitted an empty `{command}` for capability methods, and `project_args` keyed stdio MCP
registration off the legacy route list, so a composable `onto` method was never
registered. Wired, and now gated by `launcher_review_contract`, which drives the real
`build_plan → run_contract → project_args` chain with a runtime-named method.

**C5 — two review-report findings did not survive re-derivation.** A cross-family
review (gpt-5.6-sol, hermetic, read-only) reported that a `NOT_REVIEW` row still gets a
command-bearing instruction and MCP registration, and that `ReviewPlan/v1` drops
`service_tier`. Both are false against real code: the single `GRADE_NOT_REVIEW` site in
`_resolve_one` returns `STATUS_DROPPED` with no mechanism or instruction, and two
bindings differing only by service tier serialise differently because `_resolve_one`
carries the value into `detail`. Its surviving findings — marker framing, shared-
capability duplication, silent skip, weak mutations, a vacuous round-trip assertion —
were fixed. The typed-field critique of `service_tier` stands as a preference, not a
defect.

**2026-07-27, second entry** — **C6: the save-semantics fork was decided by dual-provider frontier
drafts that DIVERGED, and the union was taken.** One blind packet, two providers, neither seeing
the other. Codex (`gpt-5.6-sol`, hermetic) chose "always emit composable, failing closed until the
user authors bindings" and independently derived the hole that decides it — `none` has no
composable form. Claude (`fable-5`) chose "emit only what was authored" and supplied the argument
codex missed: the only non-fabricating variant of always-composable forces an unrelated edit into
compulsory review authorship *and freezes today's default into a file the deployer never
overwrites*, detaching that user from the stage-8-governed evolution of defaults — which is
itself the behaviour move §5.8 reserves. Owner chose the authored-only rule. **Taken from codex
anyway:** the editor must fail closed — no preselected bindings, the legacy label shown as inert
provenance only. **Taken from Claude:** the §2 amendment above, its named cost, and a bidirectional
gate over *every* shipped preset rather than one. That last one was a real hole: the contrast as
first written exercised only `deep-review`, so `solo` and `vanilla` — the two presets on `none`,
the case the whole decision turns on — were never checked. Widening it caught a mutation that
translated exactly those two and nothing else.

**2026-07-27, third entry** — **C7: stage 8's migration list cannot be executed as written,
because a composable binding cannot express host-relative cross-family review.** Legacy
`review_family = "cross"` means *the opposite of wherever this launches*, and `build_plan`
resolves it per launch (`review_host = REVIEW_HOST[host]`). A composable binding names a
`provider`, which maps to exactly one host and is therefore absolute. Measured, with the legacy
contrast: a base pinned to `provider = "openai"` grades `provider_difference` when launched on
claude and `higher_effort` when launched on codex — same provider as the main, cross-family
independence gone — while legacy `balanced` routes cross on both hosts.

So migrating `balanced`, `fast-batch`, `deep-review` and `session-distill` to the composable form
silently downgrades review independence on one host for every one of them. That is a
default-policy regression, which is exactly what §5.8's separate approval exists to catch, so the
migration is **not executed**. `solo` and `vanilla` were out of scope anyway — §5.8 reserves
`solo` for explicit approval and keeps `vanilla` bare.

Three ways forward, none of them free:

1. **Leave the shipped presets legacy.** The compatibility reader stops being a transition and
   becomes permanent for host-relative review. Costs nothing today; the quarantine never ends.
2. **Migrate with a pinned provider and accept the regression** on one host, which trades an
   absolute, auditable seat for a relative one that was never auditable. Honest, but it lowers
   the grade on real launches.
3. **Give the binding a relative form** — a way to say "the provider this launch is not". This
   re-admits launch-relative resolution into a surface deliberately made absolute, and every
   downstream claim about the exact seat then holds only after the launch host is known.

The shipped-preset cells added alongside this note are the A/B surface the decision needs: all six
presets record `legacy` today, so whichever way it goes, what moved is visible.

**DECIDED 2026-07-27 — none of the three. A fourth option exists and is strictly better.** The
owner launches on both hosts, so option 2 would have weakened review on roughly half of all
sessions. What broke the deadlock was noticing that "rewrite the presets" admits **per-host arms**:

```toml
[presets.balanced.review.hosts.claude.base]   provider = "openai"
[presets.balanced.review.hosts.codex.base]    provider = "anthropic"
```

Unlike option 3's relative token, arms state **both** answers in the file, so a seat is still
readable without knowing the launch host — the absoluteness the schema was built for survives.
The form is not a new concept either: `tier_overrides` already scopes a preset's bindings by host.

Two further facts settled it, both measured. `REVIEW_HOST` is a 1:1 map, so legacy `cross` has **no
answer at all** for a third family without a code change — the enum does not merely lose precision
as providers are added, it stops being definable. And a composable preset already carries reviewers
from several families at once, each graded independently: with a third host added in config alone,
two reviewers resolved on two families and the third method dropped with an install hint because
its capability declares no offer for that host. Honest refusal, not a silent re-route.

`balanced`, `fast-batch`, `deep-review` and `session-distill` are migrated, each reviewing on the
other family from **both** hosts, and each now carrying a reviewer tier that matches its own intent
— `fast-batch` reviews at the workhorse seat, `deep-review` at frontier — which the enum could not
express, since `cross` exposed the whole opposite tier table and left the choice to the reader.
`solo` stays legacy (its definition is a single-model session) and `vanilla` cannot carry a review
at all: it is the bare Software Engineer mode, and `project_args` returns before any contract
exists.

**What the migration cost, recorded rather than hidden:** a composable preset needs `provider` on
the hosts it names, so the migrated defaults no longer launch on a profile whose hosts declare
none, and they fail closed when the reviewer's host is absent entirely rather than degrading to
same-family the way the enum did. Both are asserted. Failing closed is the intended posture — a
silent degrade to reviewing on your own family is precisely what this work exists to stop.

**2026-07-27, fourth entry** — **C8: the migration bound a Codex-only tool to an Anthropic seat, and
the A/B could not see it.** C7 reported the migration clean because exactly the four intended
presets moved and every one graded `provider_difference` on both hosts. Both facts were true and
both missed this: on a codex main, `deep-review` and `session-distill` bound the `ultracode` method
to `anthropic`/`claude-fable-5`, and the contract duly said *"run ultracode-for-codex … on
claude-fable-5/max"*. `ultracode-for-codex` drives the Codex app-server and takes its model catalog
from there — no model id is hardcoded and neither `claude` nor `anthropic` appears in the catalog
module — so that instruction can never run. Legacy had papered over the asymmetry by substituting a
*different* tool for a codex main (`cross_ultracode_command` returns the Claude backend), which is
its own problem; the arms simply carried the binding straight through.

The root cause was a false declaration, not the binding: `[capabilities.ultracode].offers` claimed
`hosts = ["codex", "claude"]`. That list is the set of hosts a reviewer can be **seated on**, and
for a Codex-backed tool it is `["codex"]` alone. Narrowed, and the two codex arms no longer bind
the method.

**What this says about the gate.** The first assertion written for it — no shipped preset may be
DROPPED for "offers no operation for host" — did not fire on the defect, because a false `hosts`
claim makes the mechanism resolve *successfully*. A derived invariant cannot catch a lie in the
data it derives from. The check that does fire pins the declaration itself, with the reason
attached, so widening it again is a decision rather than an accident.

**2026-07-27, fifth entry** — **C9: the onto instruction was billing cross-family review to a
metered API key, and dropping every configured effort.** onto's per-call `llmOverride` REPLACES the
seat it lands on, so a field the override omits is not inherited — it is gone. The shipped template
sent `{provider, model}` and nothing else.

Measured against onto's own `normalizeLlmModelSwitcher`, with no billed call:

| override | billing_mode | auth | adapter | effort |
|---|---|---|---|---|
| `{provider:anthropic, model}` | **per_token** | api_key | anthropic_sdk | dropped |
| `{provider:anthropic, model, auth:oauth, effort}` | subscription | oauth | claude_code | kept |
| `{provider:openai, model}` | subscription | oauth | codex_cli | dropped |

So the asymmetry is the whole story: **openai defaults to the subscription, anthropic defaults to
metered.** A codex-main launch — where cross-family means Anthropic — was paying per token for
every onto review, and both hosts were losing the effort each seat was configured with (13 resolved
review seats, 9 at medium and 1 at low, collapse to 3 with none). The template now sends `auth` and
`effort`; the contract's own override string, fed back through the switcher, yields `subscription`
on both hosts with `effort=max` preserved.

**A process correction worth keeping.** The first probe of this reported that the override changed
*nothing* — provider unchanged, seats untouched. That was an artifact: it fed
`applyReviewLlmOverride` the raw `~/.onto/settings.json`, whose seats live under
`review.execution.actors.*`, while the function reads the flat `review.execution.{teamlead,lens,
synthesize}`. The real call site passes `resolveSettingsChain(...)`, which normalises the nested
shape into the flat one. Reading a function's input from the file it *seems* to come from, rather
than from its actual caller, produced a confident and completely wrong result.

**Left open, deliberately — CLOSED 2026-07-27 by C10.** The legacy `_cross_review_route` prose
(`agent-launch.py`, the `llmOverride=` line) carries the same defect. No shipped preset reaches it
any more — the four that used onto are migrated, and `solo`/`vanilla` are `none` — so the exposure
is a user-authored legacy `onto`/`hybrid` preset. Fixing it is a behaviour change to the
quarantined compatibility layer and would move the 192-cell legacy golden, which has been
byte-identical for this entire project. That is the migration decision's call, not a drive-by edit.
See C10 for the decision, and for a correction to the openai row of the table above.

**2026-07-27, sixth entry** — **C10: the legacy `llmOverride` exposure is closed, and measuring it
corrected one cell of C9's own table.** Owner decision on the item C9 left open: fix it.

> **Superseded the same day by C11 — do not read the fix below as current.** onto changed the
> default at its authority, which made stating `auth` unnecessary and then harmful, so this
> entry's launcher change was reverted. What survives is the evidence: the exposure is
> permanent because a user-owned preset never migrates, and the openai-row correction to C9.

The exposure was never hypothetical. Two independent facts, both checked on this machine:
`~/.config/agent-launch/profiles.toml` is pre-migration, so the *deployed* `deep-review` and
`session-distill` still request `hybrid`; and `presets.local.toml` — user-owned, which
`install.sh` never overwrites — carries two more presets on `review_setup = "hybrid"`, one of
them a leftover still named for the heavy pipeline's pre-rename spelling. The second file is the
permanent case: presets there reach `_cross_review_route` no matter how many times the shipped
defaults are redeployed. This very session launched through one of them.

**What the measurement changed.** C9's table records `{provider:openai, model}` as dropping
effort. It does not. `applyLlmBlockOverride` REPLACES only when the override's provider (or auth)
differs from the block's; the seats here are already `openai`/`oauth`, so an openai override is an
OVERLAY and all 13 seats keep their configured efforts. Re-measured through the real caller's
input:

| override | seats | efforts | billing |
|---|---|---|---|
| `{provider:anthropic, model}` | 13→3 | none | **per_token** |
| `{provider:anthropic, model, auth}` | 3 | none | subscription |
| `{provider:openai, model}` | 13 | 9 medium, 1 low kept | subscription |
| `{provider:openai, model, auth, effort}` | 13 | **all flattened to max** | subscription |

C9's fix was right and its openai row was wrong — the defect is entirely on the REPLACE path,
where an omitted auth defaults to `api_key` for anthropic.

**So the legacy fix sends `auth` and deliberately not `effort`**, diverging from the composable
template on purpose. A legacy setup names no reviewer effort — the enum hands the reader the whole
tier table — so choosing one is a default-policy change, and the last row above shows what it
would cost: on the OVERLAY path it overwrites every per-seat effort the user tuned in their own
onto settings. `auth` alone is strictly non-regressive in both directions. (For the composable
path that flattening is intended, not a defect: the binding *is* the reviewer's pinned rigour.)

**A guard the composable path does not need.** `ONTO_PROVIDERS` admits `grok` and `lmstudio`, and
onto's `normalizeLlmModelSwitcher` *throws* on `auth = "oauth"` for either. A composable binding
can only name a provider with a configured host, so it never reaches them; a legacy
`onto_review` pin can. `ONTO_OAUTH_PROVIDERS` narrows it, and a non-oauth pin keeps today's shape
and makes no subscription claim in its prose.

**What moved.** 16 of the 192 legacy cells — both hosts × {`onto`, `hybrid`} × cross × onto
present × delegation — and the whole diff across all 16 is two insertions, `,"auth":"oauth"` and
the clause naming why. No `same`-family cell moved, because `_same_review_route` emits no override
at all: same-family onto runs on its own configured seats. `module` (routing) is untouched; only
`projection` moved. The 192-cell matrix is no longer byte-identical, which was the price named in
C9 and is now paid deliberately.

**The gate is not the golden.** A characterisation records the fixed bytes but cannot say why they
are there, and cannot reach the guard at all — no shipped config pins grok or lmstudio, so that
branch would have shipped untested. `launcher_review_legacy_onto_auth` owns synthetic subjects for
all four providers and pins the reason with the assertion. Four mutations were each proven to make
it fire: dropping `auth`, dropping the guard, pinning an `effort`, and stating `auth` without the
reason. Its own short-set guard fails the check if fewer than four subjects produce an override.

**Cross-family review (gpt-5.6-sol, hermetic, read-only) found one MEDIUM, and it held.** The
guard's assertion was `"auth" not in override` — a proxy for the hazard, not the hazard. onto
throws only on `oauth` outside openai/anthropic (and on lmstudio without `local`); `api_key` on
grok is legal, so the failure message *"claims auth for a provider onto rejects"* would have been
false for an input onto accepts. Unreachable from today's launcher, which is why every gate was
green — but it is the same shape as C8, a check whose stated reason does not match what it
enforces. Narrowed to `override.get("auth") == "oauth"`, and the guard-removal mutation still
fires. The reviewer separately confirmed the effort non-change against the consumer source: no
input it could show makes a missing effort fail.

**A trap worth keeping.** `gates/check_parity.py` must run under the launcher's textual venv, the
way `check-parity.sh` invokes it. Run under system `python3` it reports 45 failures that are
entirely the missing dependency — a convincing wall of red with nothing behind it.

**2026-07-27, seventh entry** — **C11: the fix moved upstream, so the launcher stops sending
`auth` at all — including on the composable path C9 shipped it to.** onto is changing
`defaultAuthForProvider` so an omitted `auth` can no longer select the metered route: the two
providers with a subscription route default to it, and metered is selected only by an explicit
`auth = "api_key"` or a present `api_key_env`. That is the root-cause fix for what C9 and C10 were
compensating for downstream, and it inverts both.

**Why stating `auth` becomes strictly worse than omitting it.** Measured, and
version-independent — the seat below states its auth explicitly, so the default rule is never
consulted for it:

| seat: `{anthropic, api_key, api_key_env, effort:high}` | result |
|---|---|
| override omits `auth` | OVERLAY — the user's `api_key` and `api_key_env` **preserved** |
| override states `auth:"oauth"` | route-cleaned — **forced to oauth**, `api_key_env` dropped |

So under the new rule an omitted `auth` gets the subscription where nothing was configured *and*
defers to a user who deliberately chose metered; a stated one buys nothing in the first case and
overrides them in the second. Codex's PR review was wrong about the mechanism — it claimed the
auth-change branch discards `effort`, and measurement shows `effort` survives in every seat — but
it was pointing at the one thing that outlives the upstream fix.

**`effort` is the opposite case and stays.** The composable binding *is* the reviewer's pinned
rigour, so stating it is the point; the legacy path names no effort at all, so any value there
would be invented. The gate now asserts one present and the other absent rather than a uniform
rule, because the two fields differ in who holds authority over them.

**What this does to C10.** Its launcher change is reverted, and the 192-cell legacy matrix is
byte-identical to `origin/main` again — the price C9 named and C10 paid is refunded. What survives
C10 is the finding that made it necessary: a user-owned preset never migrates, so the legacy path
is permanently live, and its gate (renamed `launcher_review_legacy_onto_override`) now pins the
seat-only shape across all four providers, grok and lmstudio included. Twelve golden cells move,
all composable and shipped, and the whole diff across them is two deletions.

**Sequencing, and why this lands as a draft.** The launcher emits static prose and cannot know
which onto a user has installed. The rule above is under review upstream, not released; the
installed build is 0.4.17, where an omitted `auth` still resolves anthropic to `api_key`. So this
change is correct only *after* onto ships, and merging it before then reinstates the metered
default for every 0.4.17 user. Held in draft on that dependency rather than merged with a note.

**Also corrected: a comment of C10's that a reviewer read the way it was written.** It said onto
throws "on lmstudio without `local`", which reads as "an absent auth throws". It does not —
`defaultAuthForProvider("lmstudio")` returns `local`, and an override with no auth normalizes
cleanly. Only an explicit non-`local` auth throws. The code was right and the comment was not,
which is the C8 shape again.

**Confirmed against the settled upstream rule (2026-07-27).** onto's final semantics arrived after
this entry was written from an interim summary, and they hold it: metered is selected **only when
a seat states it in writing** — `auth = "api_key"`, or an `api_key_env` naming the variable that
seat calls — and everything else defaults to the subscription worker. An auth-only switch now
keeps `api_key_env` only when the destination is direct-call, so stating `auth = "oauth"` still
strips a deliberate metered seat. Both halves of this entry stand, and the launcher's own comments
now cite the two-ways-to-state-it rule rather than the narrower one measured on 0.4.17.

**One new consequence, worth stating rather than discovering later.** A REPLACE cannot carry
`api_key_env` (the override schema excludes transport), so a codex main's `{provider: anthropic,
model}` now resolves to the Claude Code worker — and **fails loud with `no_host` when that CLI is
absent**, where the old default fell through to a metered API call. That is the right posture and
it is the posture this work exists to produce, but it converts a silent, billed success into a
visible failure on machines that have no Claude Code install. The launcher already fails closed
when a reviewer's host is absent from config; this is the same failure one layer down, at the
worker rather than the config, and it is onto's to report.

**2026-07-27, eighth entry** — **C13: a second cross-family pass found five, and all five held.**
Codex on PR #10, re-derived against real code before any was acted on. Unlike the first pass —
where both findings were wrong about mechanism — every one of these reproduced.

**The two that were defects in the gates rather than the launcher.** A method template could bind
its override's `effort` to a literal instead of the placeholder, and both existing checks passed:
the shape check searched for the key name, and the rendered-seat check was satisfied by the
template's *prose* `at {effort}` rendering the binding's value. Measured: a binding of `high`
against a template hardcoding `max` dispatches `max`, with green gates. That is a direct breach of
§1's rule that the designer never selects the verifier's rigour, and it is reachable through the
user-owned registry — the very surface this design exists to open. The shape gate now requires
`provider`, `model` and `effort` each to be **bound to their placeholder**. Separately, the legacy
prose check was a two-word denylist (`subscription`, `metered`), so `via per_token` sailed through;
it now asserts the sentence equals the family exactly, because the property worth pinning is
positive — this sentence may name the family and nothing else.

**One that was a real contradiction in the launcher.** The cross contract derives its advertised
family from the review *host* while the override takes its provider from `onto_review`, so a pin
on another provider makes the contract lie. Measured: `[hosts.claude].onto_review.provider =
"grok"` on a codex main emits `{"provider":"grok",…}` under the sentence *"so onto runs
Anthropic/Claude"*. Now rejected at config load — but **only when the host declares a `provider`**,
because that field is optional by deliberate design (a schema-v1 profile that never declares one
must still load, and requiring it would reject those profiles before a preset is even chosen). So
the hole survives for provider-less legacy profiles, which is narrower than the backlog item that
already tracks grok/lmstudio.

**Two were this document's own staleness, and they are the same failure the runtime rule names.**
The handoff's closed §4.1 still described C10's `auth`-sending launcher, naming a constant and a
gate that no longer exist; and §6's redeploy action, written before C11 reversed the direction,
told the next session to deploy this branch — which on onto 0.4.17 restores per-token billing for
the two user-owned `hybrid` presets, the exact harm the same document blocks the merge for. A
handoff that contradicts the launcher is worse than none, and both items were stale for the same
reason: an entry written under one direction was not revisited when the direction inverted.

**On the controls themselves.** Five mutations, and the fifth reported SILENT — not because the
gate was inert but because the control grepped the launcher's `LaunchError` wording, which the
mutation removes, instead of the gate's own message. Re-run against what the gate actually prints:
three failures, including the short-set guard independently catching the same regression. The rule
that saved it is the one about dumping what a check ran over when it goes green unexpectedly.

**2026-07-27, ninth entry** — **C14: the upstream rule shipped as onto 0.4.18, and a third review
pass found that two of C13's own fixes were a layer too shallow.**

**The dependency cleared, verified by behaviour rather than by version.** onto 0.4.18 is published
and installed. 12 checks, no billed call: an omitted `auth` resolves `subscription/oauth` for both
providers; metered stays reachable when the seat states it, by `auth = "api_key"` **or** by
`api_key_env` alone; `defaultAuthForProvider` is block-aware (`{}` → `oauth`,
`{api_key_env}` → `api_key`), which closes the `effectiveRoute` concern this work raised upstream;
a deliberate `api_key` seat keeps its auth, `api_key_env` and tuned effort under the override this
launcher emits and loses all three under the one it removed; and a zero-seat override throws
`llm_override_reached_no_seat` against a one-seat contrast that passes. End to end, the strings the
launcher actually emits round-trip through onto's own parser to `subscription/oauth` with
`effort = max` on both hosts.

**Both code findings were defects in C13's fixes, not in what C13 fixed.** The placeholder check
searched the whole instruction string, so a template could hardcode its override and restate the
placeholders in later prose — measured: the gate passes and the dispatched override is
`{"provider":"anthropic","model":"claude-fable-5","effort":"max"}` regardless of the binding. It
now extracts the `llmOverride={{…}}` payload and checks only that; an override it cannot locate
fails rather than being skipped. And the provider guard compared the onto pin against the *host's*
declaration while the advertised family stayed hardcoded in the renderer, so declaring
`hosts.claude.provider = "grok"` with a matching pin satisfied every equality and still printed
"run EVERY review route on Anthropic/Claude" over a grok seat. The label and the provider now read
from one constant, `LEGACY_HOST_FAMILY`, and a host may only declare the provider its family is.

**The lesson under both: a guard is only as deep as the layer it reads.** Each fix closed the
comparison it was written for and left the same lie available one level up — key name → whole
string → payload, and pin-vs-host → host-vs-family. Three passes were needed because each pass
could only see the layer the previous one exposed.

**A control that stayed silent for the right reason.** Mutating the new family constraint away
changed no gate outcome — not because the gate was weak but because **no subject declared a
mismatched host provider**, so the constraint had shipped untested. A subject was added; the
mutation now fires. The recurring harness error is worth naming since it happened three times in
one session: the control grepped a string the mutation *removes* (the launcher's own error text)
or a paraphrase of the gate's message. A mutation control must assert on the gate's emitted text,
copied from the gate, never on the failure it is trying to induce.

**And a document defect this file keeps re-earning.** The handoff pinned a literal settled hash;
it went stale three times in one day, each time pointing at a commit whose behaviour the rest of
the document contradicted. It now pins the branch and derives the tip, because a hash that must be
hand-maintained under a changing direction is a promise this process has now broken three times.

**2026-07-27, tenth entry** — **C15: the override payload is parsed rather than grepped, and the
0.4.17 exposure is accepted rather than closed.**

**Two more substring defects, and they were the last of that family because the check stopped
being substrings.** Independent regexes over the payload accepted a **duplicate key** —
`"provider":"{provider}","provider":"anthropic"` satisfies every placeholder search, and a JSON
parser keeps the *last* occurrence, so every request would dispatch the literal — and the `auth`
check still read the whole instruction, so a descriptor whose payload was clean but whose prose
merely contained the word was **falsely rejected** (measured: old predicate `True`, new `False`).
The payload is valid JSON once braced, since placeholders are ordinary strings, so the exact field
map is decidable. It is now parsed with duplicate-key rejection, and the rule is stated over
whatever the payload carries — every field present must be bound to its own placeholder — rather
than over a fixed key list, so a method binding `service_tier` stays legal while a literal
anywhere does not. Four mutations fire; the false-positive case and the baseline stay green.

**The P1 was correct, and it overturned a judgement recorded two entries earlier.** C14 called the
0.4.17 exposure narrow — "someone deliberately staying on an old version". It is not.
`install.sh:340` reports a capability **present** and `continue`s whenever the command resolves,
with no version probe and no upgrade, so an existing user who updates agent-bios keeps 0.4.17
indefinitely. On that version the shipped `deep-review` / `session-distill` arms send an Anthropic
override with no `auth`, which 0.4.17 resolves to `api_key`. So the exposure is the **default path
for every existing install**, and it lands on shipped presets rather than user-authored legacy
ones — wider than the defect C10 set out to fix.

No static prose is correct on both versions: omitting `auth` bills metered on 0.4.17 and is right
on 0.4.18; stating it is right on 0.4.17 and overrides a deliberate `api_key` seat on 0.4.18.

**Owner decision: ignore 0.4.17 compatibility.** No version floor, no launch-time degrade, no
reverting to a compatible override. **The launcher is correct only against onto ≥ 0.4.18**, and
that is a stated requirement rather than an enforced one. Recorded here because the finding was
real and the exposure is not zero: anyone who does not upgrade onto gets metered cross-family onto
review with no signal. Proportionate for a tool whose deployment context is a single practitioner
already on 0.4.18; it would not be proportionate for the ~500-user target, and if that target ever
becomes real this is the first thing to revisit.

**2026-07-27, eleventh entry** — **C16: both remaining findings were coverage holes, and one of
them was a subject that proved refusal instead of behaviour.**

**Only the first override was validated.** `re.search` returns one match, so an instruction
carrying a compliant payload followed by a hardcoded one passed while both reached the reviewer —
an `openai/high` binding could instruct `anthropic/max`. Every occurrence is validated now.

**The grok/lmstudio subjects never rendered anything.** They pinned a provider the host declares
against, so `load_config` refused them and they exercised only the refusal — counted as checked
while asserting nothing about a payload. The case that *can* legitimately emit such an override is
the schema-v1 profile that declares no host provider, which the conditional constraint admits by
design, and it had no subject at all. Two were added that strip the declaration and assert the
emitted payload; measured, they hand a provider-less user
`{"provider":"grok","model":"claude-fable-5"}` under the sentence "so onto runs Anthropic/Claude".
They deliberately assert the payload and **not** the family: that contradiction is the gap C13
recorded as open, and asserting it here would encode it as intended.

**Why this one mattered more than its severity suggests.** The regression it admits is narrow —
a field added for grok/lmstudio only — but the shape is the one this project keeps meeting: a
subject that looks like coverage because it is counted, while the assertion it feeds never runs
over the thing named. The short-set guard could not see it either, since a refused subject still
increments. The control confirms it: mutating the legacy path to add `effort` only for those two
providers now fires twice and previously fired not at all.

**2026-07-27, twelfth entry** — **C17: five rounds of spelling, so the check moved to the rendered
output.** `llmOverride ={{…}}` — one space before the `=` — escaped both the membership filter and
the payload regex, so a method whose only override was hardcoded was not failed but **never
examined**, while the shipped method kept the non-vacuity assertion satisfied.

Whitespace is now tolerated, but that alone would only buy the next round. Every finding in this
family has been a different spelling of the same evasion — key name, whole string, first
occurrence, spaced assignment — because every check read a *surface form of the template*. So the
gate now also reads what the reviewer is actually handed: **no known model id other than the
resolved binding's may appear in the rendered line.** That holds however the assignment is spelled,
because a literal seat shows up as a foreign model id whatever syntax carried it there. The two
checks are deliberately redundant; the control confirms the reported bypass fires on both.

**Named cost:** a method may no longer mention another model in its prose, even innocently
("unlike claude-fable-5"). That is a real constraint on method authors, accepted because a model
id in a rendered review instruction is indistinguishable, from the gate's side, from a seat the
launcher did not choose — and this surface exists to carry reviewers this repo has never seen.

**2026-07-27, thirteenth entry** — **C18: the check added one round earlier had a blind spot of its
own, on the arm it was measured from.**

**A single probe cannot see a literal equal to its own binding.** The shipped-method assertions ran
against one seat, `openai`/frontier, so a template hardcoding `gpt-5.6-sol` was excluded from the
foreign set by equality and passed the exact-seat check through its later placeholders. Under the
anthropic arm the same template renders `--model gpt-5.6-sol` beside `claude-fable-5/max` —
a reviewer handed a command for the wrong family, with no parity failure. Measured on both arms:
`foreign=[]` under openai, `foreign=['gpt-5.6-sol']` under anthropic. Both arms now render, and a
method that renders on neither fails rather than passing silently. `ultracode` legitimately seats
on codex only (C8), so its anthropic arm is skipped by reason rather than counted.

**And the check was a substring match.** A catalog keeping `gpt-5.6-sol` while a binding moves to
`gpt-5.6-sol-2026-07-27` would find the base id inside the derived one and fail every correct
method — blocking exactly the dated-model rollout this repo performs. Whole-identifier matching now,
with the boundary written over `[A-Za-z0-9._-]` because model ids carry `-` and `.` and `\b` would
not hold. Not reachable in today's catalog, which is why it is worth naming: it fires the first
time a model is rebound, not before.

**The honest read on convergence.** Rounds 5–7 have all been findings about checks added in the
round before. Each new assertion is new surface, so the loop does not terminate on its own; what
has changed is severity — from a live billing defect, to gate coverage, to a latent false positive
on a catalog shape that does not exist yet. That trend, not an empty round, is the signal to stop
on.

**2026-07-27, fourteenth entry** — **C19: the exact-seat check was being satisfied by the
renderer's own suffix, so it could not fail.** Landed after PR #10 merged; the review that found it
posted one minute later.

`render_review_method` ends every line with ` [shape; model/effort]`, generated from the binding.
The gate asserted `binding.model in line and binding.effort in line` — over the whole line,
suffix included — so the assertion was satisfied by metadata the renderer had just derived from
the very value being checked. Measured: a body reading "run every pass at low rigour" with no
`{effort}` at all renders as `panel: run every pass at low rigour [… ; gpt-5.6-sol/max]`, and
`'max' in line` is True **only because of the suffix**. The reviewer is told `low`; the gate is
green. A hardcoded *model* would have been caught by C18's foreign-model rule, but an effort is
not a model, so nothing saw it.

The body is now split from the suffix by **computing the exact suffix and requiring the line to
end with it** — not by splitting on `" ["`, which a body containing a bracket would break
silently. A renderer that changes its shape now fails loudly here instead. The foreign-model rule
moved onto the body, and the same rule now covers rigour: an effort named in the body that is not
the resolved one is a contradiction the suffix will not reveal.

**Two legacy checks had the shapes already corrected elsewhere.** The contract check read the
first override only — appending a second call carrying `"auth":"oauth"` left every assertion green
while the reviewer was told to make both — and the model was asserted *truthy* rather than equal
to `[hosts.<h>].onto_review.model`, so any substitution passed. Both fixed; exactly one override is
now required, and the payload is compared against the configured pin.

**One check was removed rather than fixed.** The first draft also flagged unresolved `{slot}`
forms, which promptly failed on onto's own rendered JSON payload — `{"provider":"openai",…}` is a
resolved value, not a leftover. Narrowing the pattern would have left a branch that cannot be
reached at all: `validate_instruction_slots` rejects unknown `{slots}` at load and `.format()`
substitutes every known one. It knows only the two literals `<review tier>` and `<e>`, so the
angle-bracket branch was kept — `<your model here>` loads clean and reaches the body — and
control-tested with exactly that. An untestable branch is the liability this project has now
tripped over four times; a redundant one is not worth the surface.

**2026-07-27, fifteenth entry** — **C20: §1's base fallback was written, gated, and unreachable —
it lived at the resolver while the failure it answers happens at the parse.**

Owner requirement: **cross-family review is a strong recommendation, not a mandate.** A user with
one provider, or a budget for one, must be able to point a reviewer at their own model. Measured
before changing anything, half of it already held — a same-provider/same-model/same-effort binding
launches, grades `perspective_floor`, status OK, and does so with the codex host and backend
removed entirely. What did not hold was every shipped preset that carries review: on a claude-only
profile `balanced`, `fast-batch`, `deep-review` and `session-distill` all refused to launch, leaving
only `solo` and `vanilla` — which carry no review at all. The practical answer to "I have one
provider" was "author your own preset".

**The code for the right behaviour already existed.** `resolve_composable_review` falls the base
back to the exact main seat and marks it `DEGRADED`, exactly as §1 specifies. It had never run for
this case: `parse_review_binding` → `host_for_provider` raises while *reading* the preset, long
before resolution. The same inert-until-consumed shape as C4, and it survived because C7 asserted
the refusal as intended and no measurement asked what a one-provider user actually gets.

**Resolution of the §1/C7 contradiction: C7 was protecting silence, not refusal.** Its words are
"a silent degrade to reviewing on your own family is precisely what this work exists to stop" — and
`DEGRADED(reason)` in the report, printed in the contract, is the loud form. A user who never had a
second provider has no cross-family claim to falsify. So the fallback runs and says so, and C7's
gate moved from *must raise* to *must degrade, grade `perspective_floor`, and appear in the
contract text* — the last clause because a status-only assertion would pass on a launch that tells
the user nothing.

**Tolerance is scoped by branch, not by message.** `host_for_provider` fails three ways; only
"no host declares this provider" is an environment shortfall. Ambiguity and a host with no effort
vocabulary stay hard errors under the flag, because those are mistakes in what the user wrote
rather than limits on what they have. And the flag is off by default, so a binding authored
interactively in the editor still fails loudly — being silently handed a different seat than the
one just picked would be its own defect.

**Per §1, roles differ: the base falls back, an optional method drops.** `deep-review` on one host
now launches with `base=DEGRADED/perspective_floor` and onto/ultracode `DROPPED`, each naming the
missing host rather than the old generic "names no verifier seat".

**Evidence it is scoped:** the golden moved by exactly one renamed scenario and **zero changed
cells** — the two-provider path is byte-identical. Four controls fire, and the fourth found a real
hole first: the method-drop path had no subject at all (`balanced` carries no methods), so mutating
it away changed nothing until a `deep-review` subject was added.

**2026-07-27, sixteenth entry** — **C21: the fallback's own review found that "authored but
unseatable" had been spelled `None`, which already meant "never authored".** Three findings on
PR #12, all reproduced, all consequences of C20.

**The conflation was the root of all three.** `ReviewPlan`'s own docstring says a `None` binding
keeps "authored" distinguishable from "inherited from a name we are retiring" — and C20 reused
`None` for a third meaning. Consequences, in severity order:

- **Saving deleted the user's configuration (P1).** `review_block_from_plan` filters on
  `binding is not None`, so a preset the profile could not seat lost every method bound to the
  absent provider the moment it was opened in Custom and saved — silently. An unseatable *base*
  was worse: the whole composable block was discarded, because the save path gated on
  `base_binding` truthiness. Both now write back the **raw authored table**, carried on a new
  `UnseatedBinding(raw, reason)`. Resolution cannot seat these today; that is no licence to forget
  them, and a profile that later gains the host must find them unchanged.
- **A typo was misclassified as an environment shortfall.** `provider = "opneai"` in a fully
  configured two-provider profile matches no host, which at that branch is indistinguishable from
  "this user has one provider" — so it degraded a launch that should have been rejected. C20 argued
  the scoping was safe because it was "by branch, not by message"; the branch itself was ambiguous.
  Tolerance now also requires the provider to be one the launcher **recognises**: declared by some
  configured host, or a family one of the structural hosts stands for.
- **Tolerating a missing host tolerated a malformed binding.** `{provider, tier, model}` returned
  at the host check before the tier-XOR-model rule, so it was accepted — and would start failing
  the day the host appeared, which is the worst moment to learn it. The host-independent shape
  checks now run first.

**Two of the three had no gate subject until a control proved it.** The save fix and the
method-drop path both survived their mutations untouched; each needed a subject built before the
mutation could fail. That is the fourth and fifth time in this project that a fix shipped with no
way to fail, and the pattern is now specific enough to name: **a fix whose control cannot be
written yet is a fix nobody has tested, however carefully it was reasoned.**

**The golden's own control caught a vacuous fixture.** Retargeting the scenario off `grok` made it
project identically to `base-only` — `hosts` chooses where a scenario projects, not which hosts
exist, so the binding resolved normally and tested nothing. `strip_provider` is the field that
removes a provider declaration, and the harness said so before it was noticed by reading.

**2026-07-27, seventeenth entry** — **C22: a four-lens ultracode workflow reviewed the fallback,
and all seven findings survived refutation.** Dispatched through `ultracode-for-codex` 0.6.1 rather
than the GitHub reviewer: four lenses in parallel (representation, tolerance scoping, save
round-trip, gate honesty), then one refuter per finding defaulting to `refuted=true`. 4/4 lenses
reported, 11 agents, 7 raw findings, 7 confirmed — each then re-derived here against real code
before anything was changed.

**The same data loss, one layer up.** C21 fixed the serializer so an unseated binding is written
back from its raw table. The EDITOR discards it before the serializer ever sees it: `review_editor`
builds its draft with `binding is not None`, so an unseatable method is invisible there, and Apply
rebuilt the plan from what was visible. Measured — opening Custom on a single-provider profile and
choosing Apply deleted the authored method, and adding the host later could not bring it back.
Three lenses found this independently. Carried through now via `edited_review_plan`, a **named
seam** rather than an expression inside the TUI branch, because the property is not testable through
the interactive path and shipped broken without it.

**The validation hoist was half done.** C21 moved the tier/model XOR and `service_tier` ahead of
host resolution and stopped there. `effort` alongside `tier`, a non-string `model`, and `model`
without `effort` all still sat behind it, so each was accepted as "unseated" and rejected the day
the host appeared. `model = 7` was worse than inconsistent: it **launched and then could not be
saved** — the raw table is written back verbatim, and a non-string reaches the TOML serializer.
Accepted-but-unsaveable is a state the round-trip rule exists to forbid.

**And the assertion written to prevent a silent degrade repeated C19's trap.** It tested
`STATUS_DEGRADED not in contract` — but `run_contract` appends a `ReviewPlan/v1` JSON built from the
same report, which carries `"status":"DEGRADED"` by construction, so the check could not fail
whatever the renderer emitted. Scoped to the readable body now, split on the plan marker. Twice in
one project, the second time in the very check written to stop the first.

**Six times now, a fix has shipped with no way to fail.** Three of this round's fixes had no gate
subject until a control proved it — the editor round trip, the three hoisted shape rules, and
before them the save path and the method drop. The rule is worth stating plainly: **write the
control before believing the fix**, and treat a mutation that changes nothing as evidence about
the subject set rather than about the fix.

**A stale control is not a passing one.** `mutate11`'s shape control silently stopped applying when
the function it patched was restructured — its anchor no longer matched, so it reported green
without mutating anything. The property is still covered (a targeted control confirms the XOR
check fires), but a harness that asserts on a failed patch is the same vacuity it exists to catch.

**2026-07-27, eighteenth entry** — **C23: the review loop was sampling a consumer set that could
just be enumerated, and enumerating it closed the class.**

Ten review rounds across two PRs produced 2→5→3→3→2→1→2→3→3→**7** confirmed findings. The claim
recorded at round 7 that this was converging was wrong twice over — the last round was the most
productive of the whole effort. But the findings were not random: every one of the last three
rounds found a **different consumer of the same representation**, the `None` binding that C21
showed had been carrying two meanings. A review round samples that set; the set itself is finite
and greppable.

Enumerated: **13 functions** touch `.base_binding` / `.methods` / `.base_unseated` /
`.methods_unseated`. Of those, only **6 consume a `ReviewPlan`** — `parse_review_block`,
`resolve_composable_review`, `review_block_from_plan`, `_has_base`, `edited_review_plan`,
`review_editor` — and all six are the ones this work already fixed. The other seven read a
`ReviewReport`, whose `methods` is a tuple of rows that always exist (DROPPED included) and can
never carry the overloaded `None`; `render_preset_block` walks an already-serialised dict. Zero
unexamined consumers.

**The first count said 13 and was worth distrusting.** `.methods` exists on both types, so the
grep that found the population also inflated it — acting on it would have meant hunting seven
risks that cannot exist. The type distinction was the whole answer, and it took one more
question, not one more review round.

**What this does and does not license.** It closes *this* class: a defect in how an unseatable
binding is represented and read. It says nothing about the design the class sits inside, which
remains the largest unexamined risk (`Open evidence` #6) — two blind frontier drafts and a
synthesis that was never adversarially reviewed. Both contradictions this effort found (§1 vs C7,
and the base/method role split) were design-level and survived every implementation review.

**2026-07-28** — **C24: `severity_map` was validated, shipped wrong, and read by nothing.**

The shipped `ultracode` descriptor mapped `blocker/high/medium/low/info` — the canonical ladder,
copied from the panel. The tool emits `P0`–`P3` **and a null severity**, so **not one** of its real
values was mapped. Nothing noticed, for two independent reasons.

**Totality was undecidable.** With only a map, a correct identity map and a wrongly copied one are
the same object: `onto`'s vocabulary genuinely IS the ladder (`REVIEW_SEVERITY_ORDER` in its own
source, read rather than assumed), so identity is right there and wrong for ultracode, and no rule
over the map alone can tell them apart. The descriptor now carries the two facts separately —
`severity_emits`, a claim about the world that only someone who knows the tool can supply, and
`severity_map`, our translation — and the map must cover the declared vocabulary **exactly**, no
gaps and nothing invented. Copying the identity map now fails on the key set.

**And the map reached no consumer.** It was parsed, validated, stored on `ReviewMethod`, and read
by nothing — not the renderer, not `ReviewPlan/v1`, not the receipt verifier. §1's promise that an
unmapped severity "cannot produce a clean verdict" was realised by nothing at all. `render_review_method`
now appends the translation for every method whose map moves anything, so an unseen third-party
reviewer carries it without its author remembering to. It sits **inside the seat bracket**: in the
body, `P1->high` would land in the text the parity gate scans for a foreign effort and read as a
method instructing a rigour its binding never resolved.

**The mapping itself could not be derived.** ultracode documents the vocabulary and not what each
level means, so `P0 -> blocker` was the owner's call, not ours. That is the shape of the whole
problem: **a tool states what it emits, never what it means**, so the translation is a decision to
capture at registration rather than a fact to look up. The registration screen asks for it in those
terms now.

**Evidence.** The golden moved in exactly the six cells that carry ultracode and nowhere else;
`severity_emits` alone moved zero cells, which is what proved it schema-only before the renderer
change. Three controls fire, including a replay of the original defect — restoring the copied
identity map now fails four ways. The gate's assertion is derived from the descriptor's own map
rather than from `severity_translation`, so mutating that helper cannot satisfy the renderer and
the check at once.

**2026-07-28** — **C25: the four things C24 got wrong, found by review of C24 itself.**

**A config error bought the audited party leniency it may not declare.** `verify_receipts_command`
read the registry for each method's required passes — correctly, since the bundle is the artifact
under audit — and then swallowed a failed load into an empty table. Every bar fell to the one-pass
default, so a panel receipt evidencing one pass and neither ordering seed nor swap group verified
`availability=achieved`, exit 0. Pre-existing, and C24 made it **reachable by migration**: a user
descriptor authored before `severity_emits` existed now fails to load. The load no longer has a
fallback. Proven on the real path: the gate's subject is a pre-migration descriptor, and with the
swallow restored the run prints `availability=achieved` over a one-pass receipt.

**The translation clause was proven only where it could be hardcoded.** Both identity-map methods
emit nothing, so the shipped assertions and the goldens rested entirely on `ultracode`'s
`P0`–`P3`. A renderer special-casing those five values kept every one of them green while dropping
an unseen reviewer's severities — measured, not argued: that mutation exits 0. The third-party
canary, whose vocabulary is neither the ladder nor ultracode's, now asserts its own translations.

**A severity name could restructure the clause it appears in.** `severities a, b->blocker` reads as
two mappings where the author declared one, so `severity_emits` names may no longer contain `,` or
`>`. Refused at registration rather than escaped at render, so the guarantee belongs to the clause
and not to today's only reader.

**And the normative schema still described the old contract** — `severity_map` as the sole severity
field — so a user following it would author a descriptor rejected at launch. C24 documented itself
in its own dated entry and left the definition it invalidated standing.

**2026-07-28** — **C26: the lowered bar had a second door, and the fix for the first had
over-corrected.** Found by re-reviewing C25.

**Closing the registry-load path closed one door of two.** `required_passes` was still a
`dict.get(..., 1)`, so a method simply *absent* from the table got the same one-pass default
without any load error at all — reachable from a config that validly carries no
`[review_methods]` (verified: `load_config` accepts it and `load_review_methods` returns `{}`)
or a plan naming a method this registry never had. The invariant now lives at the adjudicator
rather than at its caller: a selected method with no descriptor **has no bar** and refuses
adjudication. The default is gone, not raised — `passes_for[row.method_id]`, reachable only
after the guard proved the key exists.

**And the name restriction was wider than its own reason.** Banning every `>` would reject a
reviewer whose level is labelled `risk>7`, which renders `risk>7->high` — one arrow, read
correctly. The reserved tokens are `,` and `->`, and only those. `severity_emits` exists to
take the reviewer's words verbatim, so a rule wider than the grammar it protects costs the
user their vocabulary for nothing. This is the whole registry's constraint in miniature: every
restriction is a reviewer someone cannot register.

**Refusing to load is right; refusing without saying whose fault it is, is not.** A registry
that will not load now names itself in the refusal, because the plan and the bundle are the
artifacts under audit and a reader would otherwise go looking in the wrong file. Narrowing the
load to "just the descriptors" was declined: the config is the verifier's *authority*, and
adjudicating against a partially-loaded authority is precisely what C25 closed.

**Evidence.** Every subject moved either nothing or its whole vocabulary, so a renderer
dropping exactly the one-entry case stayed green — the canary now carries a singleton, with
`risk>7` riding along as the positive control for the narrowed name rule. Six controls fire.
Two replay the lowered bar faithfully — guard removed *and* the default restored — and print
`availability=achieved` over a registry-less config; the naive mutation only crashed, which
would have proven the wrong thing.

**2026-07-28** — **C27: the name rule was wrong twice, so it stopped being a list of
bad characters.** Found by re-reviewing C26.

**A denylist cannot be right about a grammar it does not own.** C25's rule banned every `>`
and was too wide; C26 narrowed it to `,` and `->` and was too narrow — `P0]\nforged: OK [x`
passed, closed the seat bracket early and forged a second method line into the contract. Both
failures are the same mistake: enumerating the characters the *rendered contract* gives
meaning to, a list that grows every time the contract does. A severity name is a **label**, so
the rule is now an allowlist over what a label is made of — letters, digits, and
` ._-+=<>#()` — plus the arrow as a two-character token. `risk>7` stays registrable and the
forgery does not. This is the third spelling of one rule; the allowlist is the version that
does not need a fourth.

**The screen was still teaching the rule the parser had abandoned.** C26 narrowed the parser
and left the registration screen telling users `>` was forbidden — a user would have renamed
their reviewer's real levels for nothing. Both now render from one constant, and the gate
drives the real screen and asserts it states what the parser enforces. Every restriction on
`severity_emits` is a reviewer someone cannot register; a restriction that only *appears* to
exist costs the same and buys nothing.

**And the gate was checking containment, which a mangled label satisfies.** `CRITICAL->blocker`
is inside `severity.CRITICAL->blocker`, so a renderer that prefixed or altered a third-party
label passed. Measured: a renderer preserving the five shipped labels and mangling every other
one passed **both** the gate and the goldens — the goldens can never catch it, because they
only ever see the shipped vocabulary. Both call sites now parse the clause out of the rendered
line and compare it as a **set** against the descriptor's own map, so extra, missing and
altered mappings all fail. That the third-party path is the one nothing covers is now the
third round in a row it has been the finding.

**Evidence.** Nine controls across the three rounds. Round 3's three fire: the denylist
restored accepts the forged name, the hardcoded screen fails against the parser's constant,
and the shipped-label-preserving mangler — silent before, in both the gate and the goldens —
now fails the canary and the singleton. The allowlist carries subjects on both edges, so it
cannot tighten to nothing and stay green.

**2026-07-28** — **C28: the grammar was the problem, not the vocabulary.** Found by
re-reviewing C27.

**Three rounds spent constraining labels, when the separator was what was ambiguous.** An
unpadded arrow FUSES with the label before it: `<` rendered `<->high`, which reads as one
bidirectional arrow rather than the label `<` mapped to `high` — and the gate could not see
it, because it composed the same string. The fix is not a fourth restriction on names. The
clause separator is now ` => `, padded on both sides, which makes the fusion unreachable for
**every** label instead of forbidding the labels that trigger it. `<`, `P0-`, `=` and even
`a->b` are all registrable now, and the arrow stopped being a reserved token at all.

**And the allowlist was excluding a real vocabulary.** `N/A` is how a tool spells the state
ultracode calls `null`, and `/` was not on the list — so the rule cost a plausible third-party
reviewer its own words while protecting nothing (`N/A => info` is unambiguous). Both edges now
carry gate subjects, because over-restriction has been the more expensive error twice: **every
restriction on `severity_emits` is a reviewer someone cannot register.**

**A body could contradict the clause core appends.** An authored `instructions` carrying
`; severities CRITICAL => info` rendered a second clause beside the map's, and the gate's
`rsplit` read only one of the two, so the set matched while the reader was handed a
contradiction. The marker is now refused in authored instructions, and the gate parses **every**
occurrence so that refusal has something to fail against.

**The screen stated one clause of the rule, so a user could follow it exactly and still be
refused** — it listed the punctuation and omitted that leading and trailing space are
rejected. Screen and parser now render the whole rule from one constant.

**Worst of the five: the rule the user is told to follow was the part they could not read.**
This work grew the registration payload from 20 lines to 26, and the panel that carries it is
a bare `Static` — measured on the installed Textual, `overflow-y: auto` leaves
`allow_vertical_scroll` False with no scrollbar, so everything past the panel's height is
simply gone on an ordinary 24-row terminal. The panel is a `VerticalScroll` now. The gate
drives a real 80×24 render and requires the whole payload to stay reachable; that probe
*rebuilds* the panel, so a source pin holds the mirror to the real compose, and the limitation
is stated rather than left implicit.

**Evidence.** Six controls, all firing: unpadding the arrow, dropping `/`, permitting the
marker in a body, reducing the screen to the punctuation clause, reverting the probe's panel
to a `Static`, and reverting the *real* panel while leaving the probe alone. The golden moved
in exactly the six ultracode cells and, line by line, in nothing but the arrow.

**2026-07-28** — **C29: the padded separator has exactly one hole, and the rule was
Latin-only without saying so.** Found by re-reviewing C28.

**A label containing the separator.** ` => ` disambiguates every label except one that
carries it: `risk => 7` renders `risk => 7 => high`, and neither a reader nor the identical
`ReviewPlan/v1` instruction can tell which arrow is the mapping — nor could the gate, having
composed the same string. The separator is now the one token a name may not contain, which is
the same rule C28 removed for `->`, moved to whatever the separator actually is.

**`string.ascii_letters` quietly meant "a Latin label".** `重大` and `심각` were
unregistrable while `critique` was fine, and the screen disclosed none of it. The rule is
Unicode-aware now — `isalnum()`, which already excludes the control, format and separator
categories that could corrupt the line. This is the third over-restriction in three rounds
and the largest: not one vocabulary, a whole script of them.

**The marker check read the template, and slots are substituted after it.** A perspective
named `security; severities CRITICAL => info` rendered a second, contradicting clause beside
the map's — as would a `{command}` path. Refused on the **formatted body**, the one place
every substitution passes through; the template check stays upstream for the earlier, clearer
message.

**And two things earlier rounds left behind.** The normative descriptor schema still said `>`
was forbidden, five commits after the parser stopped forbidding it — the same drift C27 fixed
in the screen, in the document that C27 was written in. The round-4 source pin, which existed
only to hold a rebuilt panel to the real compose, was silently checking a literal the code no
longer contained; the probe now drives the real `MenuScreen`, so the pin is gone rather than
repaired.

**A scrollbar is not a way to scroll.** The panel became scrollable in C28 and stayed
reachable by **mouse only**: `on_mount` focuses the option list, whose Up/Down are the only
movement keys the footer names, and the panel holds a non-focusable `Static`. PageUp/PageDown
now scroll it, advertised in the footer only when a panel is present. The probe mounts the
real screen at 80×24 and presses the keys — measured: 26 lines of payload, 13 hidden, focus on
the option list, and PageDown reaches exactly 13.

**Evidence.** Five controls, all firing: permitting the separator in a label, restoring
Latin-only letters, checking the template instead of the body, dropping the PageDown binding,
and reducing the screen to the punctuation clause. The goldens did not move, which is the
right answer — none of this changes what a shipped method renders.

**2026-07-28** — **C30: the stated limitation, closed — and it was worse than stated.**

C28 left "the whole screen does not fit 24 rows" as a known limitation. Measuring it properly
made two things clear at once. The first: **the previous measurement was wrong**, because the
probe read the stylesheet off the screen class, which never carried it — it had been measuring
an unstyled layout and calling it the screen. With the real stylesheet and a real plan, at
80×24 the title sat at **y=-9 and the setup panel at y=-8**: not clipped at the bottom where a
user might scroll, but pushed off the **top**, past the reach of every key the screen offers,
while the option list collapsed to one row. The screen needed 45 rows to show itself.

**Nothing absorbed the slack.** Every widget had a fixed or natural height, so when the sum
exceeded the viewport Textual pushed the overflow upward. A `1fr` scrolling region now takes
what is left, and only **reference** content lives in it — setup panel, corpus text. The
widgets the user acts through stay outside at their natural size, which took two wrong tries
to learn: a flexible widget *inside* a scrolling body has no leftover to be a fraction of, so
at `1fr` the option list collapsed to one row again, and at `auto` it grew until the detail
panel explaining the highlighted option scrolled out of reach — caught not by reasoning but by
the picker scenarios, which drive the real TUI over a 24-row pty.

**Two of this work's own claims were false and are gone.** `dock: top` on the title was
inert — the title stays at y=0 because the `1fr` body absorbs the slack, not because of the
dock — and the comment above it credited the dock for the fix. And the check itself passed
**vacuously** on the faithful reversion: it asserted the body "reaches its end", but a body
with no overflow reaches its end trivially, so a layout whose body sat at y=-30 with its
content unreachable was scored green. The body is now checked for being on screen like every
other widget, the overflow must be non-zero for the subject to count at all, and every row of
it must be scrollable to.

**Evidence.** Measured across 20/24/45 rows, with and without a corpus panel, and with 2 and
14 options: title, footer, detail panel and option list on screen, the body reaching its end
on PageDown, and screens without a corpus panel not scrolling at all — no regression for the
common case. Three controls fire, including the vacuity guard: removing the scrolling region
puts the title at y=-31, removing the PageDown binding strands the body, and trimming the
payload until it no longer overflows makes the check refuse to score itself.

**2026-07-28** — **C31: the preset promised a reviewer it silently omitted on one arm.**

`deep-review` describes itself as "hybrid onto, native, and **Ultracode** review", and on a
claude main it delivers exactly that. On a **codex** main it delivered `panel + onto` — no
ultracode, no `DROPPED` row, no mention anywhere in the contract. Reproduced on the deployed
launcher, not argued. `session-distill` had the same hole.

**The cause was that the concept had only one realisation.** `ultracode-for-codex` drives the
Codex app-server, so C8 correctly bound it to `hosts = ["codex"]`. A codex main routes review
cross-family to anthropic — a seat that tool cannot fill — so the arm had no way to express
it and simply went without. The three options this looked like (report it, degrade to
same-family, per-preset policy) were all answers to the wrong question.

**The right one was that the concept has a second realisation.** The Claude Code CLI carries
its own dynamic workflow, opened by putting the keyword in the prompt — read in the installed
2.1.220 bundle (`workflowKeywordTriggerEnabled`: "including the keyword in a prompt opts that
turn into the Workflow tool", default true), not assumed. Registered as `ultracode-claude`
with `hosts = ["claude"]`, it is the mirror image, and between the two a workflow-orchestration
reviewer is now available **cross-family from either main** with no same-family degrade.
Neither is `ultrareview`, the billed cloud review — a wrong turn corrected before it was built.

**Its severity ladder is ours, and that had to be made true rather than declared.** This
reviewer has no vocabulary of its own; it reports on the canonical ladder because the request
says so. Stating the ladder as prose in the body failed immediately — `high`, `medium` and
`low` are also effort names, so the gate read it as a method instructing a rigour its seat
never resolved. It is a core-owned `{severities}` slot instead: the vocabulary cannot drift
from `severity_emits`, and the gate can subtract the exact substring core produced before
scanning for a foreign effort. That subtraction is itself asserted to remove *exactly* the
vocabulary and nothing more — widening it to strip those three words anywhere left the gate
green, which would have blinded the effort check with no shipped subject to show it.

**The rename that could not happen.** A symmetric `ultracode-codex`/`ultracode-claude` pair
was tried and reverted: the frozen legacy layer binds `"ultracode"` by name, and renaming the
capability collapsed the golden's capability axis — caught by its own load-bearing control,
not by review. The Codex variant keeps the bare parent id and `LEXICON.md` carries the
parent-and-variants relationship the identifiers cannot.

**Evidence.** The golden moved in exactly two cells — `shipped/deep-review/codex` and
`shipped/session-distill/codex` — and no legacy cell moved. Four controls fire: dropping the
slot from the request, expanding the slot to nothing, widening the effort-scan subtraction,
and removing the codex arm (which puts the golden back where the defect was).

**2026-07-28** — **C32: C31 named the two tools backwards, and correcting it found a gate
that had never run.**

**The names.** `ultracode` runs **on Claude** — it is the Claude Code CLI's own dynamic
workflow — and `ultracode-for-codex` is that tool **ported to Codex**, which is what its
package name says. C31 assigned them the other way round, giving the bare parent name to the
port. Corrected: each is named for the host it runs on, and the parity gate pins **both**
directions in one place, so swapping them fails rather than resolving into an impossible
instruction.

**What they are for, which the descriptions now say.** Both drive a dynamic workflow, used
here as a flexible many-perspective check on an **implementation** — functional, adversarial,
logic, scenario, stress. That makes them **complementary to onto**, which looks hardest at
whether authority, gates and harness are consistent with one another. They are independently
selectable and either alone is a legitimate configuration: a thing whose whole point is that
it *works* can be reviewed by the workflow alone; a logic-bearing document, ontology, harness
or gate can be reviewed by onto alone. This is decision-shaping information that lived only in
the author's head, and the picker is where a user needs it.

**A frozen route token was doubling as a capability id.** The legacy layer resolved its
`ultracode` route by using the route token *as* the capability key — in four places
(availability, the install hint, the executable line, the lowering). So renaming the tool
silently repointed a frozen legacy route at whatever else held the bare name, which the
golden caught as 24 moved legacy cells. One `LEGACY_ROUTE_CAPABILITY` map now states the
binding, and the setup vocabulary and the tool ids are free to differ. The 192 legacy cells
are byte-identical again.

**And the gate that should have caught all of this had never executed.** The check's legacy
contrast, its **mandatory negative mutations**, and its shared-capability MCP registration
case — 95 lines, 10 statements — sat indented under `if ultracode_hosts != ["codex"]:`, a
condition that was true only when the assertion above it failed. On every commit that shipped
it, none of it ran. Worse, once de-indented it still failed, because the block also sat
*outside* the `with tempfile.TemporaryDirectory()` whose endpoint it uses: the fixture was
gone by the time it read it. Moved inside, it passes — and both controls confirm it is really
running: registering the shared capability per row fails it (`2 times on claude`, the exact
bug its comment describes), and making a mutation inert fails it. It now counts the cases it
ran and fails if the count shrinks, because a check that cannot report having run is
indistinguishable from one that passed.

**Evidence.** Golden moved in 12 cells, none legacy. Four controls fire, two of them on the
revived block. Discovered only because a rename made an always-false condition briefly true —
which is the argument for pinning both directions of a claim rather than one.

**2026-07-28** — **C33: the new capability described itself instead of declaring itself.**

Two fields, both wrong in the same way — written as documentation where the schema expects
something the runtime uses.

**`install` is executed.** `install.sh` hands that string to `sh -c`, so the sentence shipped
there — "the Claude Code CLI itself; see …" — would be run as two shell commands, both
failing, leaving the capability missing and the user told nothing useful. The field is gone:
a missing claude CLI is a missing **host**, not a missing reviewer. A gate now requires that
whatever `sh` would run first actually exists, which is decidable and catches the whole class.

**`command` duplicated a default instead of following the configuration.** The tool IS the
claude backend, but the descriptor wrote the literal token, so it resolved independently of
`[backends.claude].command`. Reproduced: with the backend at an absolute path and no `claude`
on `PATH`, ordinary dispatch resolved while the reviewer reported `DROPPED — capability
'ultracode' is not installed` and the review carried on without the method the preset asked
for. `${backend}` now means "the CLI of the host this capability offers on", resolved through
one `capability_command` helper at both the mechanism and the chooser.

**Why this machine could not have shown it.** `claude` IS on this PATH, so the literal token
resolved here and every existing check passed. The gate subject therefore points the backend
at a path no `which` would find and requires the reviewer to *name that path* — an assertion
that fails on the literal token even where the token happens to work.

**Evidence.** Golden moved in two cells, both codex arms, none legacy. Two controls fire:
restoring the literal token makes the reviewer name `claude` where the configured backend is
a wrapper, and prose in any shipped `install` fails on its first word.

**2026-07-28** — **C34: a sentinel is only as good as the sites that read it.**

`${backend}` was introduced at the two places that *write* a capability's command and missed
every place that re-reads it. Four surfaces, all found by review, none by this machine:

**MCP registration re-read the raw value.** A registry user may pair `${backend}` with the
stdio adapter; resolution then succeeds, the row is reported **available**, and
`project_args` aborts with `executable not found: ${backend}` — a launch that fails after
telling the user its review was ready. It now resolves through the same helper as the
mechanism, with the host derived from the row's provider through a small `provider_hosts`
projection the plan carries alongside `backends`.

**Availability collapsed a list to one answer.** The chooser is asked *without* a binding, so
a two-host `${backend}` capability had no single host to resolve and was labelled **NOT
INSTALLED** — then ran perfectly once bound. Availability now asks whether *any* offered
backend resolves, which is the honest question at that point. This is the third
over-restriction in this effort, and again it cost a legitimate reviewer its place.

**The installer probed the sentinel literally.** `install.sh` runs `command -v` on whatever
its capability table prints, so the built-in workflow capability reported as unavailable
while the launcher ran it. The table resolves the sentinel now, and `verify` fails on any
capability whose command is empty or still the sentinel.

**And the `--with` help had gone stale in the rename.** It advertised `onto, ultracode` — a
name that now selects the Claude-native capability, which has no install line — while
`ultracode-for-codex`, the one that actually installs something, was undiscoverable from the
CLI. The list is **derived** from the capability table, and `verify` compares the two so a
copy cannot drift back in.

**Evidence.** Four controls fire, each reproducing its finding exactly: re-reading the raw
command aborts the projection, collapsing availability re-labels the two-host capability,
un-resolving the installer's table trips the new verify check, and hardcoding the help list
makes it disagree with the table. The pattern worth keeping: **every one of these was true
only because `claude` is on this machine's PATH**, so the literal token resolved and nothing
local could have shown it.

**2026-07-28** — **C35: four of six were things a later commit had already made untrue.**

**Two real defects.** Availability answered for *every* host a capability offers, ignoring
which offer serves the **requested operation** — so a capability serving one operation on a
resolvable backend and another on an unresolvable one called the second method installed and
then dropped it at bind time. And the two installer checks added one commit earlier sat
**inside `if packaged_mode`**, so they passed vacuously on the ordinary full-corpus install —
the very path whose regressions they exist to catch. A check in the wrong branch is the same
failure as a check under a false condition, one commit after that exact defect was found and
written up.

**One over-restriction, again.** `verify` required the `--with` list to be non-empty, so a
configuration that legitimately declares no optional capabilities failed even though both
projections agreed. Two empty projections match.

**And three stale statements this effort had created.** The in-config comment still listed
the slot vocabulary without `severities`, telling an author that a supported slot was
forbidden — an over-restriction expressed as documentation. The capability-command validation
error still named `capabilities.ultracode`, which the rename had made a *different, valid*
capability, sending the reader to the wrong table. `README.md` and `DEPENDENCIES.md` still
told users to activate the workflow reviewer with `claude --effort ultracode -p` while the
shipped instruction opens it with the prompt keyword — follow the docs and you get an
ordinary headless session while believing the workflow is on.

**What that says about the shape of this work.** Every one of the last three was created by
an earlier commit in this same effort and survived its own round of review. The lesson is not
"check the docs" — it is that a change which renames a concept or adds a slot has a **fan-out
of statements about itself**, and each one is a claim that can now be false. Three of them now
have gates: the comment is compared against `INSTRUCTION_SLOTS`, the error is asserted to name
the capability it validates, and the docs are asserted not to describe a different activation
than the contract.

**Evidence.** Four controls fire — dropping the operation filter, removing `severities` from
the comment, blaming the wrong capability, and restoring the doc claim. The installer
relocation is structural (the block now sits after the branch closes) and `install.sh verify`
prints both capability lines.

**2026-07-28** — **C36: an over-restriction in a gate, and a claim standing on a proxy.**

**The host pin counted offers, not hosts.** `offered_hosts` in the gate collected into a list
where the production helper collects into a set, so a capability gaining a second offer on the
host it already serves — another operation, another adapter, both legal — rendered
`['claude', 'claude']` and failed a pin whose reachable host set had not widened by one
entry. Fifth over-restriction in this effort, and the first inside a gate rather than in the
data it guards. The positive control matters more than the negative one here: a duplicate-host
offer must be **accepted**, and it is, while widening to a real second host still fails.

**And availability stood on a proxy.** The claude CLI resolving proves the command exists; it
does not prove the keyword still opens a workflow. That is decided by
`workflowKeywordTriggerEnabled` — the user's setting, default true, which this launcher cannot
read. With it off, the review runs as an ordinary session and reports as though it were
orchestrated: the exact failure this branch exists to remove, arriving through the door of the
fix. The precondition is now named in the descriptor the chooser shows and in the instruction
the dispatcher reads, and a gate fails if it is dropped. **Not** enforced by probing the
setting: it lives in a settings chain this launcher does not model, and a partial read would
answer confidently and sometimes wrongly — worse than a stated limit. The host table also
claimed v2.1.207 while everything verified here was read from 2.1.220; it says 2.1.220 now.

**A method note worth keeping.** The first attempt at the precondition assertion referenced a
name out of scope. The check **crashed** — no `FAIL` line, exit 1 — and a grep for `FAIL`
reported nothing, which reads exactly like green. The controls run since then detect a
traceback separately from a finding.

**Evidence.** Three controls: a duplicate-host offer is accepted, a widened host set is
rejected, and removing the precondition sentence fails. Golden moved in 12 cells, none legacy.

**2026-07-28** — **C37: the registration identity was coarser than the thing it identified.**

Making MCP registration host-aware gave one capability the ability to resolve to a
**different command per host** — and left the registration keyed on the capability alone. Two
methods sharing a `${backend}` stdio capability, seated on opposite providers, therefore both
resolved `OK` and then **aborted the launch** on a guard written for a different problem
entirely: the duplicate-registration bug, where one capability was registered twice for the
same server. Reproduced before fixing; the composition is legal and both rows were valid.

Sixth over-restriction in this effort, and the second in a row that arrived **through the door
of a fix** rather than in the code being fixed. The pattern is worth naming: widening what a
value can be without widening the key that identifies it turns a correctness guard into a
refusal.

The key is `(capability, host)` now. The NAME stays the bare capability while the capability
means one thing, and gains the host only when it really is two servers — so every existing
registration and every golden is untouched, and the two-host composition gets two names
instead of a refusal.

**Evidence.** Two controls, in opposite directions: keying by capability alone reproduces the
abort, and always suffixing the host breaks an existing single-host registration. The golden
did not move at all, and the 192 legacy cells stay byte-identical.

**2026-07-28** — **C38: one of these gates could not fail, and it was mine.**

Asked to find assertions that cannot fail, the review found one: the guard that was supposed
to prove the effort scan strips *only* the severity vocabulary compared
`len(body) - len(scanned)` against `len(vocabulary)` **one line after computing `scanned` by
exactly that transformation**. The arithmetic cannot come out any other way, so the branch was
unreachable for every real input. It had fired in a control only because that control edited
the line above it — a mutation detector for one line, dressed as a property. The narrowing is
a named function now, exercised on a **controlled body** where the same word sits inside the
vocabulary and outside it; over-broad stripping removes both and the assertion fails.

**Two more registration findings, both from widening a key.** Making the identity
`(capability, host)` fixed the abort in C37 and introduced two of its own. A generated
`foo-codex` **collides with a capability someone really named** `foo-codex` — claude's dict
silently drops one, codex emits two conflicting overrides, both after every row reported OK.
And two hosts whose backends resolve to the **same executable** became two registrations of
one server. The identity is `(capability, resolved command)` now, so identical commands
collapse, and a generated name is checked against the authored capability ids and the names
already handed out.

**And the availability answer needed a third state.** Round 2 replaced "every host resolves"
with "any host resolves" because the former called a two-host capability uninstalled. Taken
alone, the latter advertises as installed a method the user can then bind to the host that
does **not** resolve — which Apply turns into a `DROPPED` row, the chooser promising what the
plan withdraws. All / some / none are three answers, and `PARTIAL` names which hosts are
reachable.

**The through-line for this whole effort.** Seven over-restrictions, and the last four all
arrived *through the door of a fix*: each was correct about the case that prompted it and
wrong about a neighbouring one. Widening what a value may be without widening its key; taking
a two-valued answer where the honest one has three; asserting a transformation against itself.

**Evidence.** Four controls, each reproducing its finding: over-broad stripping hides an
effort named outside the vocabulary; dropping the collision avoidance registers a duplicate
name; splitting on the host label registers one executable twice; and "any host resolves"
advertises a partially reachable method as installed. The golden did not move and the 192
legacy cells stay byte-identical.

**2026-07-29** — **C39: the workflow review found what six adversarial rounds had not.**

An orchestrated multi-agent pass over the same branch returned fourteen reproduced candidates
where six rounds of single-reviewer review had been converging on prose. Two were fixed here;
the rest are recorded below because they are real and were not caused by this branch.

**`--with ultracode` stopped installing anything.** On `origin/main` that request ran
`npm i -g ultracode-for-codex`. After the rename the token names the claude-backed reviewer,
which is the host CLI and deliberately carries no install line — so `handle_capabilities`
prints `capability present`, `continue`s, and the tool the user actually meant stays missing
with only a hint. The request no-ops and install exits 0. A/B-verified by exporting both trees
and running each under a controlled PATH. The present-capability branch now says the request
installed nothing and names the capabilities that do install.

**And the docs gate forbade what the launcher ships.** C35 added a check that fails if
`README.md` or `DEPENDENCIES.md` contains `--effort ultracode` — while the frozen legacy route
in `agent-launch.py` prints exactly that flag and sixteen golden cells hold it. The repo
banned in documentation what it emits in code. The rule now asserts **agreement** instead of
absence: the docs must describe the mechanism the shipped composable descriptor actually uses.
Absence rules are cheap to write and forbid more than they mean to.

**Recorded, not fixed** — reproduced by the workflow, none of them introduced here:
the review editor's press-enter default seats a host-bound reviewer on the host its capability
cannot fill, and the chooser shows no qualifier first; a `capability offers no operation for
host` drop is decorated with an install hint for a tool that is already installed; a
`${backend}` capability that cannot resolve is reported as a missing reviewer with no remedy;
the golden matrix's `cap-neither` cells never make the new capability absent, so it is present
in all 253; a capability id containing a dot registers on claude and mis-registers on codex;
`order`, `swap_augmentation` and `aggregation` are validated, advertised and read by nothing;
`REVIEW_SETUPS[*]["requirements"]` is inert data this branch rewrote in three places.

**On method.** The pass cost 78 agents and 7.7M tokens for two fixes and twelve filed
observations — worth it here, on a branch already reviewed six times, and not a default. One
refuting agent left its lane and probed whether spoofing the CLI's human-origin marker would
suppress a safety reminder, and launched nested sessions with permissions bypassed. Its
output was discarded rather than adjudicated. A fan-out that can do that needs its findings
re-derived by hand, which is the same rule already applied to every other reviewer here.

**2026-07-29** — **C40: "did this branch introduce it?" was the wrong filter.**

C39 fixed two of fourteen reproduced findings and recorded the rest, on the ground that the
others pre-existed. That triage was wrong for at least two of them, and the second is the
exact class the commit two before it was named after.

**The new reviewer had no absence coverage at all.** `[capabilities.ultracode]` resolves
through `${backend}` → `[backends.claude].command`, which every golden fixture rewrites to an
existing fake — so the capability-presence axis, whose whole job is to make things absent,
could not express its absence. Counted: **zero DROPPED rows in 253 cells**, including the ones
whose ids say `cap-neither` and `both-absent`. The branch's headline addition was present in
every cell of the matrix that exists to vary presence. That is a gate that cannot fail for the
thing this branch added, filed as an observation about someone else's code.

A `${backend}` capability is absent exactly when its HOST CLI is missing, so the fixture gained
that knob and one scenario uses it, scoped to the codex main — on a claude main a missing
claude CLI is a failed launch, which is correct and a different assertion. The matrix is 254
cells now and `ultracode` finally has a DROPPED row.

**And its drop said the wrong thing.** With the claude CLI missing, the row read `capability
'ultracode' is not installed` — pointing the user at a package that does not exist, with no
remedy, while the config's own comment says "a missing claude CLI is a missing host, not a
missing reviewer". It now names the host CLI and the path it failed to resolve. The new golden
cell is what makes that message falsifiable: reverting the diagnosis moves the cell.

**The rule this replaces.** Provenance is a fine reason to defer a fix into its own change; it
is not a reason to file a hole in one's own gate as an observation. The test is whether the
defect is in what this branch is responsible for — and a coverage hole for a capability this
branch introduced is, whatever the surrounding fixture's age.

**2026-07-29** — **C41: the seat pressing enter buys could not run the reviewer it was buying.**

The editor's provider default preferred the family the main is NOT. That is the right rule for
the base panel, which needs no tool and seats anywhere, and the wrong one for a method bound to
one host: adding `ultracode` on a claude main landed on openai, and Apply turned it into
`capability 'ultracode' offers no 'workflow-review' operation for host 'codex'`.

**Provenance, derived rather than inherited.** On `origin/main` one arm was already broken — a
codex main adding the then-codex-backed `ultracode` landed on claude and dropped — while the
other resolved. Giving each family its own workflow reviewer made **both** arms drop. The
branch's headline addition became unreachable by the path a hurried user takes, on either main.
C39 filed this under "not caused by this branch"; C40 had already replaced that filter, and
this is the case it was written for.

**The fix.** The provider menu takes the method. A host its capability does not offer stays
VISIBLE and disabled, carrying the exact `LaunchError` that seat would have raised, so the
screen and the DROPPED row say the same thing — a hidden option would answer nothing, and "why
can I not review this cross-family" is the question the screen exists to answer. The landing
seat prefers independence only among seats that can run the tool. On a claude main `ultracode`
now lands on anthropic and reports `model_difference`: a smaller grade honestly stated beats
provider independence promised and then withdrawn. And the grade is readable BEFORE the seat
screen — a capability offered on a strict subset of the seatable hosts says "Runs on claude
only" in the chooser, rather than being discovered as a family that will not select.

**Three answers again, not two.** `method_servable_hosts` returns None — "the host does not
decide this" — rather than every host, because a method naming a capability the config never
registered fails on every host for a reason no seat can fix. Narrowing that to the empty set
would replace a precise diagnosis with a menu that has nothing on it.

**And the first version of the gate could not fail.** It recomputed the landing rule instead of
calling it, so reverting the shipped default left it green: C38's defect, reproduced inside the
check written to prevent this one. The rule is a named function now, called by both the editor
and the gate. Two further controls crashed instead of asserting, because the disabled-seat
reason dereferenced `method` under a guard that read `servable` — a guard that reads one value
to protect a dereference of another holds only as long as their contract does, and a crash
prints no `FAIL:` line, which is the failure that reads like a passing gate.

**Evidence.** Seven controls, each reproducing its finding with a named failure: the pre-fix
default; the constraint removed entirely; a two-host capability narrowed to one; the
capability-free base panel constrained; the chooser qualifier removed; that qualifier applied
to a method offered everywhere; and a disabled seat that stops saying why. Driven end to end
through the real editor on both mains, pressing enter through every screen, `DROPPED` became
`OK`. The golden did not move and the 192 legacy cells stay byte-identical to `origin/main`,
counted against a subject set asserted non-empty first — the same check keyed on a guessed
field name had reported zero drift over zero cells.

**2026-07-29** — **C42: the fix's own gate could not fail for the one line that undoes it.**

C41 shipped with seven negative controls and no independent review. A cross-family reviewer
(gpt-5.6-sol at xhigh, hermetic, read-only, on a self-contained packet) returned seven
findings, three high. Every one that mattered was reproduced here before being acted on.

**The gate was blind to the wiring.** All seven controls mutated something the gate CALLS.
None touched the call site. Deleting one argument — `review_provider_options(config,
main_provider)` instead of `(config, main_provider, method)` — restores the original defect
exactly, and the whole gate stayed at **exit 0 with no FAIL line**. The scripted editor drive
that existed added the multi-host method, which resolves either way. There is now a drive that
adds a SINGLE-HOST method on both mains and reads the resulting row — the only assertion that
reaches the wire through the editor itself, though the seat-refusal assertions added in the
same commit catch the same mutation from the other side. Third time in this effort: C38's
assertion could not fail, C40's fixture could not express absence, and C42's controls could not
reach the wire.

*(Corrected 2026-07-29: this said "the only thing that sees it". An audit applied the mutation
and counted seven `FAIL:` lines across three assertion sites. The drive is the one that sees it
END TO END; it was never the only one.)*

**Two more the fix did not cover.** A method naming an unregistered capability returned the
same `None` as the capability-free panel — "the host does not decide this" — so every provider
stayed selectable and enter authored a guaranteed drop, the exact class C41 exists to prevent.
It returns the empty set now, and the precision that `None` was protecting moved into
`no_seat_cause`, which distinguishes the three reasons no seat can work: unregistered, offered
on no host, offered only on hosts this profile cannot seat. They are three different files to
go edit, and "no configured provider serves that host" was the same sentence for all of them.
And a STORED seat never passed through the chooser at all: a preset or hand-edited config could
name one, and applying an untouched draft preserved it into a DROPPED row while the compose
list showed it like any other. It is marked `WILL DROP` with its reason — said, not blocked,
because the row is the user's and Apply reporting DROPPED was already honest.

**And the gate's own over-restriction.** The widening assertion read "servable on more than one
host" as "servable on every seatable host". Those coincide only while exactly two hosts exist;
with a third, `onto` serves two of three, the runtime correctly disables the third, and the
gate called that an over-restriction. It compares against `seatable_hosts` now. The eighth
over-restriction of this effort, and the second to arrive in a check rather than in the code.

**Two ways a check hid its own failure.** Under the reverted-landing control the editor
re-prompted rather than raising — a disabled default is refused by `choose_lines` — so the
harness ran out of script and the AssertionError escaped as a traceback, aborting the stage
before it could name anything. And a new assertion called `choose_review_binding` expecting a
refusal; when a mutation made it NOT refuse, it reached real stdin and **blocked forever**,
which from outside is indistinguishable from a slow check. Both are caught by name now, and
the terminal read is stubbed for the whole call so the gate cannot reach a prompt.

**And the ninth over-restriction: the refusal cost more than the drop it prevented.** A native
reviewer, running the same branch on its own scenarios, found that the `LaunchError` C41 added
walks straight out of `review_editor`, which catches only `BackRequested`. Selecting a method
whose capability offers only a host this profile cannot seat **killed the launcher and took the
user's unsaved draft with it**. Contrast against **`7ee648e`, the commit before the constraint
landed** — not the fix's own parent, which already had the regression: on identical config it
authored the doomed seat and Apply showed a visible `DROPPED` row, draft intact. So the fix was
worse than the defect, and the path is reachable through the SUPPORTED flow — a reviewer
registered in the user-owned file. The raise stays where it belongs; the editor catches it,
shows the reason, and stays open. The seat is still refused, so no doomed row is authored: now
better than both `7ee648e` and the version in between.

*(Corrected 2026-07-29 by an audit of this entry: it originally said "the parent commit", which
is `6624c69` and loses the draft exactly as `origin/main` does. Naming the right commit
**strengthens** the finding — the draft-losing regression shipped to `main` in `5ef8c09` and was
live, rather than being introduced and repaired inside one branch.)*

**One promise the code made in a comment and nowhere else.** The disabled-seat reason claims to
match the error the drop would raise. For a malformed `offers` block it did not:
`capability_offered_hosts` silently skips what it cannot read, so the screen said "offers this
on no host" — true, and it sends the user hunting for a hosts list instead of the invalid
entry — while `derive_review_mechanism` names the exact line. `no_seat_cause` defers to the
parser now, and the gate asserts the two strings are EQUAL rather than merely both present.

**And the sentence that advised an impossible action.** `method_availability` produces nothing
BUT advice about bindings, and its PARTIAL branch was still reasoning over every host the
capability names: it told the user "binding it to `grok` drops the row" about a host with no
`[hosts.*]` entry, which the provider menu does not list and no binding can reach — in place of
the useful fact that here the method runs on one family. The commit that taught the sibling
branch about `seatable` left this one behind, which is the same omission one function apart.
The whole function is scoped to seatable hosts now, and a config that can seat nothing has no
install state to report at all — only `NO SEAT`.

**Evidence.** Fifteen controls, every one exiting nonzero with a named `FAIL:` — the seven from
C41 plus eight this round: the call-site wiring, the stored-seat warning, the unregistered
capability folded back into `None`, the no-seat test that skips the seatable intersection, the
`LaunchError` escaping the editor again, the malformed offer no longer deferred to the parser,
availability unscoped from seatable hosts, and the PARTIAL branch naming the offsite host
again. Two of those controls were written vacuous first and had to be fixed before they could
fail: keying "no seat can run this" on an empty `servable` missed a capability offered only
off-profile, whose set is non-empty; and the offsite probe never entered the PARTIAL branch at
all, so the sentence that actually contained the defect went uncovered while the check around
it passed. End to end on both mains, enter-through still yields `OK`.

**A gate fixture had to gain what the change made it need.** The three-availability-states
check ran on a synthetic config with capabilities and backends and no `hosts` table — fine when
availability was about installation, wrong once it is about seats, because a profile that can
seat nothing has one answer for all three states. The three collapsed into one string and the
DISTINCTNESS assertion caught it, which is the whole reason that assertion exists. The fixture
declares hosts now, and the seatless config is pinned as its own assertion rather than left as
an accident of the fixture.

**What the review was worth, and which kind bought what.** One cross-family pass at one seat
found what seven self-authored controls could not, on a change its author had just verified end
to end — not because it knew the code better, it had never seen it, but because the packet
asked it to assume the fix over-restricted somewhere, and it was not the one who chose which
mutations to try. The same-family reviewer running its own scenarios then found the one thing
the cross-family pass missed, and it was the most damaging: a lost draft, reachable through the
supported flow. Neither found the other's headline. That is the convergence heuristic behaving
exactly as written — different reviewer kinds diverge, and the union is the finding.

**2026-07-29** — **C43: the screen was computing its own answer, and the answer was the defect.**

A fourth round, cross-family at frontier effort on the whole cumulative change, returned five
defects — all reproduced here before being acted on, and all one root: **the editor decided
what a row would do by re-deriving it, instead of asking what decides it.**

**Two authorities were reading the same config and disagreeing.** `capability_offered_hosts`
skips whatever it cannot read; `parse_capability_offers` is what validates, and it runs only at
Apply. So `hosts = 7` in a user-registered capability raised an **uncaught `TypeError` straight
out of the chooser** — killing the launcher outside the `seat()` closure that exists to prevent
exactly that — while an invalid `adapter` advertised "Runs on claude only" for a row that always
dropped. Classification reads the parser now, and a block the parser rejects supports no seat.

**Support and reachability were competing for one slot.** A capability whose binary resolves
perfectly but offers a different operation was reported `NOT INSTALLED — mytool is missing`,
three lines from a provider menu correctly saying it offers no such operation. Nothing
installable fixes an unoffered operation, so support answers first and `NO SEAT` dominates. And
when a `${backend}` capability cannot resolve, the chooser now says what `_resolve_one` has said
since C40 — the HOST CLI is missing, not the reviewer — while staying `NOT INSTALLED`, because
that is a reachability fact about something installable. Folding it into `NO SEAT` would tell a
user with a fixable problem there is nothing to fix.

**And the `WILL DROP` warning from C42 was itself a second calculation.** It compared the seat's
host against the offered hosts, which is one of several reasons Apply drops — so it stayed
silent for a stored row whose command does not resolve, and for a method whose descriptor was
deleted from the user-owned file. Both drop; neither was flagged. The row asks `_resolve_one`
now, the same function that produces the report, so the list and the report **cannot** disagree.
That is the difference between a warning that is maintained in parallel and one that cannot
drift.

**Three of this round's own controls were defective, and each defect was a different one.** One
mutated the wrong site: `if capability.get("command") == HOST_BACKEND_COMMAND:` appears twice,
so a whole-string replace hit `_resolve_one` and left the branch under test untouched — the
control passed while proving nothing about the code it named. One crashed instead of asserting,
because the check called `review_provider_options` outside its own exception boundary. And one
crashed because the compose row read `registry[method_id].description` on a path a mutation could
reach with an unregistered id. A mutation anchor has to be unique, and a check has to survive the
thing it is testing for.

**Evidence.** Twenty controls, every one exiting nonzero with a named `FAIL:` — the fifteen from
C41/C42 plus five: classifying from the tolerant reader, reachability answering before support,
the backend-missing diagnosis blaming the reviewer, the compose row re-deriving instead of
resolving, and an unregistered stored method going unflagged. The last was verified surgically
after the broad version produced 82 failures, which is a control that proves the gate is alive
rather than that the assertion is. All gates green; enter-through still yields `OK` on both
mains.

**The concept-surface question, answered by experiment rather than by taste.** Each added name
was inlined or collapsed in a copy of the tree to see whether any assertion noticed.
`no_seat_cause` collapsed to one generic sentence produces **thirteen** named failures: it is
carrying real distinctions, not formatting. `seatable_hosts` is the interesting one — dropping
the `HOST_EFFORTS` half of its definition left the entire gate **green**, while the provider
menu began offering a host whose binding `parse_review_binding` refuses by name. The docstring
promised "the editor must not offer what the reader would reject" and nothing checked the
second half of it; that promise is asserted now, with the reader's refusal asserted alongside
so the rule is not guarding a case that cannot happen. `review_landing_provider` inlines
without any assertion noticing, which is what inlining SHOULD do — the name is not carrying
behaviour, it is carrying testability, and the editor drive covers the behaviour independently.
It stays, because deleting it returns the gate to restating the rule it is checking, which is
the C42 defect by another route.

**What four rounds bought, by reviewer kind.** Cross-family at xhigh found the gate's blindness
to its own wiring. Same-family native found the lost draft. Cross-family at max — a strictly
higher seat on the same provider — found the two authorities disagreeing, which neither of the
first two saw. Every round found something the previous rounds had looked straight at. The
per-round yield has not fallen, which is the argument for stopping on a decision rather than on
a clean verdict: this branch is not converging on "no findings", it is converging on findings
that need a smaller and smaller config to reach.

**2026-07-29** — **C44: the round that audited the record, and found the record wrong.**

Three parallel reviewers returned on the same branch: a mutation sweep against the current
tree, a concept-surface audit, and a fact-check of C42 itself. The fact-check is the one worth
leading with, because **it found two false claims in this document, both written by the author
of the fix.**

**"Contrast against the parent commit" named the wrong commit.** The round-3 fix's parent is
`6624c69`, which loses the draft exactly as `origin/main` does; the contrast belongs to
`7ee648e`, before the constraint landed at all. The experiment behind the claim was right — it
was run against the pre-constraint tree — and the sentence describing it was not. Naming the
right commit **strengthens** the finding: the draft-losing regression shipped to `main` and was
live, rather than being introduced and repaired inside one branch. **"The only thing that sees
it" was overstated**: the same mutation produces seven failures across three assertion sites.
Both are corrected in place above, with the correction noted rather than silently rewritten.

**Four mutations still passed a gate this effort has now hardened four times.** Each verified
here before acting. The **edit path had no drive at all** — every wiring drive ADDS, so
`current` is None, and the stored-seat drive applies without opening the row; deleting the
pre-fill guard therefore left the gate green while enter, on the edit screen, meant "keep the
DROPPED row". `seat()` widened from `LaunchError` to `Exception` also passed, which would render
a genuine `TypeError` as a polite "cannot be seated" screen — the crash-reads-like-a-pass
failure installed in the launcher rather than in the gate. The **provider half** of
`seatable_hosts` was droppable alone, the mirror of the `HOST_EFFORTS` half found an hour
earlier. And the per-host disabled reason could drift word-for-word from the `LaunchError` it
promises to match, because only the malformed-offer path was held to equality; every path is
now, which is what the promise said.

**And a gate that could not survive the config it checks.** `registry["onto"]` was hardcoded, so
renaming that shipped method raised `KeyError` and **aborted the stage** — every launcher check
after that line silently stopped running. It selects by property now: the first method whose
capability declares an `install` line, with a vacuity guard when none does.

**On the concept surface, one thing kept for a reason worth stating.** The audit showed
`review_landing_provider` reduces to "first enabled option" without any assertion noticing,
because the sort already places the main's own family last. That is true and it is why the
reduction is refused: it would leave the independence rule resting entirely on an ordering, and
the ordering was itself unasserted until this round. Two encodings the gate can catch drifting
between beats one encoding whose only carrier is a sort key. The ordering is asserted now as
well — the code claimed in a comment that a seat which cannot run the tool sorts below one that
can, and the drives could never see it, because enter picks the default by value rather than by
position.

**Evidence.** Twenty-six controls, every one exiting nonzero with a named `FAIL:`. All gates
green; enter-through still yields `OK` on both mains.

**Where this stops.** Five rounds, and the yield per round has not fallen — but its SHAPE has.
Rounds one to three found defects reachable from the shipped config. Rounds four and five needed
a hand-written capability, a renamed shipped method, or a deleted guard to reach. What survives
now is, in the sweep's own words, empty subject sets and contract breadth the drives cannot see.
That is the point at which more rounds buy gate coverage rather than user-facing correctness,
and the honest reason to stop is a decision, not a clean verdict.

**2026-08-03** — **C45: I1 grades difference and never asked whether the reviewer can review.
Owner decision, four parts.**

**(a) A capability floor exists, and the ladder has none.** Review is not work any tier can do:
the reviewer must be at least **workhorse**-tier capability, and **helm or above is the
recommendation**. This is orthogonal to I1, which measures only *difference* —
`independence_grade` returns `provider_difference`, its top grade, on
`reviewer.provider != main.provider` alone, so a `sweep` seat (`gpt-5.6-luna`/`low`,
`claude-haiku-4-5`/`low`) verifying a `helm` main grades highest while sitting below the floor.
Nothing in the launcher enforces a minimum. The floor and the ladder are two different
questions and the design collapsed them into one.

**(b) I2 stands as written** — isolation is a hard gate, not a grade.

**(c) A second provider is the best configuration, and must stay a user choice.** Different
models detect each other's blind spots, which is why cross-provider at helm-or-above is the most
effective shape. It cannot be mandated: a second provider is a billing decision that belongs to
the user. What the product owes them is that the **launch screen says so** — the review setup
surface should name cross-provider verification at helm tier or above as the most effective
option, as advice at the point of choosing, not as a gate.

**(d) Specialised tools stack, but they are not the way to be thorough.** On top of a
different-provider, isolated seat, adding a second verification *layer* is stronger still —
`ultracode-for-codex` reviewing product behaviour while `onto` reviews gate and authority
consistency is a genuinely thorough pass. But that thoroughness is reachable without either
tool: opus designing and `gpt-5.6-sol` at `ultra` verifying, or `gpt-5.6-sol` designing and
`claude-opus-5` verifying through ultracode, or plain `xhigh` subagents partitioned by the
design's own risk areas and cross-checking each other, all achieve it. So the specialised-tool
axis is an accelerator, not a rung anything should depend on — which is consistent with
`onto`/`ultracode` being optional installs, and argues against any future shape that treats
their absence as reduced thoroughness rather than reduced convenience.

**2026-08-03** — **C46: the status header was three stages behind the code, and C7's objection
had been answered without the answer being written down.** Measured, not inferred.

**Stage 6 landed, with all three declared controls.** `launch/agent-launch.py::review_editor`
is the method-map editor; `gates/check_parity.py::launcher_review_editor` is 808 lines carrying
80 distinct failures, and the stage's own controls are there by name — an arbitrary N-method set
round-trips keeping each binding's form, and a sentinel local registry keeps its digest across
install and verify.

**Stage 7's verifier landed; its producer did not, and that is the whole remainder.**
`verify_review_receipts` runs as a real process and `launcher_receipts` exercises every way a
receipt can be refused. A separate assertion pins the honest consequence: a clean verdict with no
receipt must read `PROPOSED`, and the launcher fails if it claims an `achieved_grade` without
one. So the machinery to *consume* evidence is complete and gated; nothing *emits* it, which is
why achievement is still asserted by hand.

**Stage 8 was executed, and C7's blocker was answered structurally.** All four review-carrying
presets — `balanced`, `fast-batch`, `deep-review`, `session-distill` — now declare composable
`review` blocks; `solo` and `vanilla` remain on `review_setup = "none"`, which §5.8 reserved and
which keeps a legacy contrast alive for the A/B rather than leaving the old path uncovered.

C7's objection was that a composable binding names a provider and is therefore absolute, while
legacy `review_family = "cross"` means *the opposite of wherever this launches* — so migrating
would silently downgrade independence on one host. The answer was to make the arms host-relative
instead of the binding: `REVIEW_ARMS_KEY = "hosts"`, and a preset declares one arm per **main**
host, which `parse_review_block` selects with the launching host. `balanced` therefore reviews on
`openai` from a claude main and on `anthropic` from a codex main, and cross-family holds on both
while every individual binding stays absolute. The mechanism was built; only the record of it was
missing.

**The document's largest named risk had no slot on its own open list.** C21 calls the unreviewed
synthesis "the largest unexamined risk" and cites `Open evidence #6` — which is the service-tier
item. So the risk was named inside a correction and absent from the list a reader consults to
find open questions. It is `Open evidence #8` now, stated on its own terms; C21's citation is
left as written, because corrections are dated and superseding them in place would be the same
edit-history-in-place this repo refuses elsewhere.

**Why this entry exists.** Three claims from this document were acted on earlier the same day and
none survived contact with the code: that stages 6–8 were unbuilt, that the risk in C21 was
listed where C21 said it was, and — from the handoff now archived — that the deployed launcher
predated the migration. A design document that is read to decide what to build next has to be
re-measured before it is used that way, not after.

**2026-08-03** — **C47: the capability floor is a cap on the ladder, not a gate beside it.**
C45a's requirement, mechanised. Three shapes were on the table and the evidence left one.

**"Advisory only" was never an alternative.** C45c already puts the recommendation on the launch
surface whichever mechanism is chosen, so picking it means doing that and nothing else — leaving
the report still calling a `sweep` reviewer maximally independent, which is the untrue part.

**A hard gate is the wrong import.** I2 is a gate because isolation is *structural*: always
decidable, and free to satisfy. The floor is neither. `ReviewBinding.tier` is `None` for a
binding written as a raw model id, so "is this workhorse-capable" has no mechanical answer for a
model the profile does not list — a gate would either refuse a legitimate frontier model or carry
a hole exactly where a user is most likely to under-configure. And helm-or-frontier seats cost
more, so refusing a weak one *forces spend*, which is the same character as the second provider
C45c deliberately leaves to the user.

**So: capped.** `below_review_floor` returns true only when a binding NAMES a tier weaker than
`REVIEW_TIER_FLOOR = "workhorse"`, and `independence_grade` then returns `perspective_floor`
however different the seat is. Unknown is not below — an untiered binding is graded normally,
because treating unclassifiable as under-floor would demote the exact model a user reached for
through **Other**. The report says which floor it is, since a capped grade and a same-seat floor
read identically otherwise.

Nothing shipped moves: all four review-carrying presets bind `helm` or `frontier`, so the golden
is unchanged at 254 cells. Two matrix rows carry the new rule and the contrast — a `sweep` seat
earns nothing, and `workhorse` itself is *not* capped, because the floor is the requirement while
helm-and-above is the recommendation. Proven falsifiable by lowering the constant to `sweep`,
which fails both.

**2026-08-03** — **C48: the design review this document called missing had already run, and its
sixteen surviving findings were never adjudicated.** Correcting C46's own entry, and the
`Open evidence #8` added the same day.

`§4.6` ran on 2026-07-27 — `ultracode-for-codex` 0.6.1, five lenses plus a refuter per finding,
23 agents, all five reading this document rather than the implementation. 18 findings, 16
survived. `Corrections` names none of them. The review file states its triage lives here; it
does not, and the handoff written the next day still listed `§4.6` as open, which is how the
claim "never reviewed as a design" outlived the review that closed it.

**This blocks stage 7 rather than decorating it.** Findings #4, #8, #11 and #12 are the receipt
schema, and their shared claim is that `verify_review_receipts` cannot tell adapter-produced
evidence from hand-authored JSON: `dispatch_id` and `main_dispatch_id` are unauthenticated
caller-supplied strings, `packet_sha256` is compared only against the bundle's own declared
value, `result_sha256` is never recomputed and need not be a digest, and `ReviewReceipt/v1`
carries no plan identity because `ReviewPlan/v1` has none to bind to. `launcher_receipts`
manufactures the whole passing bundle locally, so the gate demonstrates the gap instead of
closing it. Building a producer on that foundation would emit receipts a forgery is
indistinguishable from — which is the opposite of what receipts are for.

**Finding #1 is a sibling of C45a, not the same defect.** C45a says a reviewer below the tier
floor should not earn independence credit. #1 says the *floor grade itself* is granted without
the condition the Principles attach to it: same-model/same-effort review counts as a floor only
with isolation plus two or more perspectives, `§1` enforces that minimum for `panel` alone, and
`§4` awards `perspective_floor` to any method regardless. Same shape — a grade given to
something that has not met its own stated bar — on the perspectives axis rather than capability.

**The record is untracked.** `design/reviewer-registry/reviews/` is one of the directories kept
out of git on purpose, so the only copy of 16 adjudicated-nothing findings exists on one machine,
and the tool's own background directory that produced it is garbage-collected. Whether that
directory should stay untracked is now a decision with a cost attached.

**2026-08-03** — **C49: the nine HIGH findings, adjudicated. All nine hold, and they are six
defects.** Each was re-derived against the code rather than taken on the reviewer's word; the
site is named so the next reader can check the adjudication instead of trusting it.

**A. Receipt evidence is unauthenticated (#4, #8, #11 — one defect, three lenses).** `RECEIPT_KEYS`
carries no plan id and `review_plan_v1` emits no identity, so a receipt cannot name the plan it
belongs to and the plan has no name to be given. `packet_sha256` is compared only against the
bundle's own declared value, `result_sha256` is never recomputed and need not be a digest, and
`dispatch_id`/`main_dispatch_id` are caller-supplied strings. `launcher_receipts` manufactures the
entire passing bundle locally. A fabricated, internally consistent bundle therefore moves
`achieved_grade` off `UNKNOWN_UNTIL_RECEIPTS` with no reviewer dispatch. **This is why stage 7's
producer is not the next thing to build.**

**B. Registry assertions are trusted as core guarantees (#5, #16).** `derive_review_mechanism`
reads `offer["adapter"]` and looks the tag up in `REVIEW_ADAPTERS` — a dict of tag to *description
phrase*. Nothing establishes the isolation the tag names, so a locally registered capability can
label a stateful same-context command `exec-stdio-v1` and receive its "fresh read-only subprocess"
wording plus an OK independence row. `validate_instruction_slots` closes the slot *vocabulary* and
forbids two legacy placeholders; it never requires the template to *use* `{model}`/`{effort}`, so
an instruction that omits or contradicts the seat passes while the plan advertises
`provider_difference`. Both are the same shape: an author assertion rendered as a core guarantee.

**C. Trial policy is neither delivered nor audited against its own declaration (#9).**
`_receipt_reason` demands `ordering_seed` and `swap_group` whenever `required_passes > 1`,
ignoring the method's declared `order` and `swap_augmentation` — so a method authored fixed-order
and no-swap is audited as though both were required. In the other direction
`render_review_method` interpolates `perspectives` and `trials` only, so `order`,
`swap_augmentation` and `aggregation` never reach the reviewer at all. And `required_passes` is
read from the registry at verify time, so editing a descriptor changes whether yesterday's
receipts pass.

**D. `perspective_floor` is granted without the condition the Principles attach to it (#1).**
`parse_review_method` enforces the two-perspective and two-trial minimum inside
`if method_id == PANEL_METHOD` and nowhere else, while `§4` awards the floor to any method. A
capability-backed method with one lens at equal effort is reported `OK/perspective_floor`. This is
C45a's sibling: same defect shape — a grade given to something that has not met its own bar — on
the perspectives axis rather than the capability axis, and C47 fixed only the capability half.

**E. Optional methods drop where the base degrades (#14) — a decision, not a defect.** The
behaviour is as filed: a Codex main with `ultracode` installed loses the lens rather than
receiving it degraded same-family. But it is what this document already chose — "optional methods
drop, base falls to the main seat". So the finding collides with a recorded decision rather than
with the code, and what it earns is a re-read of that decision against the Principles' "axes
compose as availability and cost allow", not a fix.

**F. The provider/host vocabulary is code, not config (#15).** `HOST_EFFORTS` is a two-key literal
and `host_for_provider` raises for a provider mapping to no encoded host, so a reviewer reachable
through a registered capability on an unencoded provider cannot receive a binding — against
"anything reachable can be registered". Overlaps `Open evidence #7`, which reached the same wall
from the grok/lmstudio direction.

**What the adjudication changes.** Six items, one of which (E) is a decision to revisit and one of
which (D) is half-fixed. A and B are the load-bearing pair: until an adapter's claim and a
receipt's provenance are established rather than asserted, `achieved_grade` cannot mean what §4
says it means, and every stage-7 control tests self-consistency instead of the property it names.

**2026-08-03** — **C50: the seven MEDIUM findings, adjudicated. All seven hold; four reinforce
defects C49 already named and three are new.** The review set is now fully triaged: 16 findings,
**nine distinct defects**.

**Reinforcing what C49 named.** #7 is #1 through a second lens — the same panel-only enforcement
of the two-perspective minimum, so it is defect **D**, not a separate item. #3 is **F**: `:901`
rejects any adapter outside `REVIEW_ADAPTERS`, so a reachable protocol is blocked until core ships
a tag, which is the same wall #15 hit from the host side. #12 is **A**/**C**: `_receipt_reason`
counts `len({p for p in passes if p})` distinct truthy labels against one `result_sha256` for the
whole receipt, so one dispatch can claim three passes.

**#2, narrowed — the defect survives, the causal story does not.** Filed as majority aggregation
suppressing a lone perspective's finding against the corpus's act-on-the-union rule. That
suppression cannot happen, because `aggregation` never reaches the reviewer: the panel's
`instructions` end with "and aggregate" and name no rule, and `render_review_method` interpolates
only `perspectives` and `trials`. So the real defect is **C** again — a declared policy that is
inert — and the union rule is neither honoured nor violated, because nothing is asked for. That is
worse in one way and better in another, and it is not what was filed.

**G (new) — severity totality is claimed and is not decidable.** `§1` says a `severity_map` must
be total over the reviewer's severities and `§3` says the gate asserts it. `parse_review_method`
asserts the map is a non-empty table whose values sit on `SEVERITY_LADDER`, and nothing declares
the external severity *domain*, so totality has no subject. A reviewer that also emits `ERROR` is
selectable, passes parity with that severity unmapped, and a real finding can arrive
unnormalisable.

**H (new) — `availability` is two concepts in one field.** The design separates them: "Achieved ≠
available", launch-time availability is `projected`, runtime evidence moves `achieved_grade`. But
`verify_review_receipts` writes `AVAILABILITY_ACHIEVED if complete else report.availability`, so
after verification the field carries achievement completeness, and *partial* achievement is
indistinguishable from never-verified. It duplicates `achieved_grade` and hides the partial case,
which is precisely the state a consumer most needs to see.

**I (new) — the surface cannot express a seat that does not consume effort.** `§4` as amended by
C1 keeps `ADVISORY(effort)` for a capability whose seat ignores effort, and says it "must be
reachable without being reached". Neither the method schema nor the offer schema has a field to
declare that condition, so a reviewer whose protocol cannot take effort must either be credited as
though it received the exact effort or be dropped for failing to deliver the binding. The promised
status has no way to arise.

**What the full triage settles.** Nothing here changes the order C49 implied. A and B remain
load-bearing, C now carries three findings rather than one, and the three new items are narrower.
Triaging before touching code was the right call for one reason only: G, H and I would have been
lost, and none of them were reachable from the HIGH set.

**2026-08-03** — **C51: defect D's other half is disclosed, not downgraded, because the descriptor
cannot decide it.** C47 fixed the capability axis by capping the grade. The perspectives axis was
expected to be symmetric and measuring said it is not.

`perspective_floor` is the Principles' claim that same-seat review still counts, and that claim is
conditional on isolation **plus two or more distinct perspectives**. `parse_review_method` enforces
that minimum inside `if method_id == PANEL_METHOD` and nowhere else, so a same-seat single-lens
method lands on the floor without meeting the floor's own condition. Reachable, not hypothetical:
binding `ultracode` to the main seat grades `OK/perspective_floor`, and `ultracode` declares one
perspective and one trial.

**Why not cap it.** The capability floor was decidable because a binding names a `tier`. The
perspective condition is not decidable from `perspectives`, because that field counts the lenses
*core asks for* — and `ultracode` fans out into many agents internally, so one is not the number of
perspectives the tool applies. Downgrading on that count would encode a claim the data does not
support, and `NOT_REVIEW` is a heavy thing to assert on a proxy. So the row now says the floor is
**claimed rather than established**, and what to do about it stays a decision: enforce the minimum
for every method, teach the descriptor to distinguish lenses-requested from lenses-applied, or
accept the floor as advisory for methods that fan out.

**A note-accumulation bug from C47, fixed here.** `detail` was assigned per branch, so when a
below-floor binding also carried a non-default `service_tier`, the second note silently replaced
the first — C47's own disclosure was the one that vanished. Notes accumulate now, and a control
asserts both survive together; reverting to assignment fails it with only the service-tier note
present.

Shipped behaviour is unchanged again — every shipped method binds cross-provider, so the floor is
never the grade and the golden holds at 254 cells. Which is exactly why the controls exist: two
prove the disclosure (a one-lens method carries the note, the three-lens panel does not), and both
were proven by removing the branch and watching them fail.

**2026-08-03** — **C52: defect H is split. `availability` is a launch-time projection again, and
achievement carries its own coverage.**

`verify_review_receipts` used to write `AVAILABILITY_ACHIEVED if complete else
report.availability`, so one field answered two questions and answered the second one badly:
complete became `achieved`, while **partial and never-verified were both left as `projected`** —
the pair a reader most needs to tell apart, collapsed. It also duplicated `achieved_grade`, which
reports the best grade among accepted rows and therefore says nothing about how many rows there
were. One verified method out of three yields a top grade and no signal that two are missing.

`ReviewReport.achievement` now carries `none` / `partial` / `complete`, verification never writes
`availability`, and `AVAILABILITY_ACHIEVED` is gone because nothing sets it. The renderer prints
the count beside the word — `partial` says the set is incomplete, `1/3 evidenced` says how
incomplete, which is the difference between chasing one missing receipt and discovering almost
nothing ran. `verify_receipts_command`'s exit status keys off `achievement == complete`, so the
pipeline gate is unchanged in behaviour and now hangs off the field that means it.

The case that proves the split is the one that used to be invisible:

```
Review achievement (achievement=partial [1/2 evidenced], achieved_grade=provider_difference,
availability=projected — launch-time projection, unchanged by verification)
  onto:  PROPOSED — no receipt was supplied
  panel: ACHIEVED/provider_difference — verified
```

A top grade beside half the evidence. Before the split this read `availability=projected`, which
is what a plan nobody verified at all also reads.

Launch-time output is untouched — verification was the only writer — so the golden holds at 254
cells, and a control asserts the partial run reports all three facts at once and still exits
non-zero.

**This is a prerequisite the trust-list work needed.** Grading an MCP surface by what a trusted
server reports adds a third achievement state, and there was nowhere to put it while one field
carried two concepts.

**2026-08-03** — **C53: evidence is declared per offer and checked per receipt. It buys drift, not
honesty, and the distinction is the point.**

An offer may now declare `evidence` — the field names the tool reports back about the dispatch it
performed — and `_receipt_reason` refuses a receipt that carries none of them. `onto`'s
`structured-review` offer declares `reached_seat`, `billing_mode`, `auth_defaulted`, which is what
its override already returns on the warning channel.

**What this does not do.** A receipt is still written by whoever ran the review, so a named field
can be invented. This is not a defence against a party that lies, and calling it one would be the
same overclaim §4 already makes.

**What it does do, and why it earns its place.** It catches a tool that quietly stops reporting —
which is the failure this repo has *measured* rather than imagined. An override that reached no
seat resolved to a default provider with a `model` of `null` and **did not fail**, so an honest
reporter would have reported success. A contract naming the reached seat turns that silence into a
missing field, and a missing field is refused.

**It also solves version scoping without a version probe.** `install.sh` checks that a capability's
command resolves and never asks what version answered — so trusting a tool by NAME would credit a
build that no longer reports. Trusting a tool by CONTRACT does not: an old build has nothing to put
in the fields, so it fails on the evidence rather than on a version comparison nobody implemented.

**Declared per offer, not per capability**, because evidence is a property of how a tool is reached.
The same tool over a different adapter reports different things, and the offer is where the
adapter already lives.

Three controls, and the second is the one that matters. A receipt with no evidence is refused; a
receipt carrying one of three names the two it lacks, so "went quiet" and "written against an older
contract" do not read alike; and **deleting the declaration from the profile makes the first
control pass**, which is what proves the check reads the declaration instead of carrying its own
copy of the field list. The fixture derives its evidence from the profile for the same reason —
declaring a new field makes the happy path carry it rather than quietly stop exercising it.

## Related

`~/Documents/onto-mcp/development-records/audit/20260727-llm-override-consumer-findings.md`
(the four `llmOverride` findings this work measured, filed against onto 0.4.17, **with
onto's own disposition appended**: F1 and F2 fixed at the authority, F4 fixed in three
places, F3 kept by design with a measured counterfactual) ·
`design/adapter-split/ECOSYSTEM-ARCHITECTURE.md` (the two master levers) ·
`design/adapter-split/DESIGN.md` (user-owned config finding) ·
`design/tui-review-area.md` (absorbed; dated record of the surface) ·
`claude/guides/cli-multi-model-workflow.md` (current review routing) ·
`claude/guides/llm-capability-boundary.md` (submit-tool pattern).
