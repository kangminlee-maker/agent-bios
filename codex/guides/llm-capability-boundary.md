---
guide_id: llm-capability-boundary
language: en
status: active
use_when:
  - designing structured outputs
  - changing runtime-owned artifacts
  - defining submit tools or accepted output channels
  - separating LLM semantic judgment from deterministic execution
  - designing validators, grounding checks, or capability-surface constraints
  - designing tool use, retrieval, side effects, or artifact persistence
core_rules:
  - instructions describe intended work, semantic criteria, and completion criteria
  - capability surface enforces constraints through context, tools, permissions, routes, paths, output channels, validators, gates, and approvals
  - assign each field or operation one primary authority, then add layered checks where needed
  - LLM handles semantic judgment, rationale, tradeoffs, and evidence reduction
  - runtime/tools handle deterministic execution, artifact creation, merge, serialization, validation, persistence, and tests
  - machine-consumed artifacts are created through submit tools or equivalent constrained channels
  - provider strict schema is an execution aid, not the source of artifact truth
  - tool inputs, tool results, retrieved content, and rendered views are untrusted until validated or sanitized
field_assignment:
  short_closed_values: provider_closed_selection_plus_runtime_enum_validation
  runtime_known_ids: runtime_owned_unless_selection_is_semantic
  long_refs_and_source_snippets: runtime_allowed_set_validation
  evidence_anchors: grounding_blocked_when_source_truth_is_decidable
  source_provenance: runtime_owned_snapshot_hash_scope_and_trust_tier
  open_rationale: free_generation_with_shape_checks
  side_effects: capability_surface_plus_policy_gate
  artifact_envelope_and_serialization: runtime_only
verification_focus:
  - accepted output channel is explicit
  - LLM cannot create canonical machine artifacts through free prose
  - runtime-owned fields and unknown fields fail loudly
  - provider schema limits are known and probed before relying on them
  - long refs are validated by runtime allowed sets instead of provider enums
  - grounding gates are used only for decidable truths
  - source trust, permission, staleness, and poisoning risk are checked separately from quote grounding
  - side-effect tools are classified by risk and gated by permission or approval
  - artifact writes are atomic, idempotent where possible, and auditable
  - schema, validator, allowed-set, prompt, and tests share one authority or have drift-catching tests
---

# LLM And Capability Boundary Guide

Use this guide when an LLM produces, selects, validates, summarizes, or routes
machine-consumed artifacts, code, ontology, pipeline outputs, review findings,
structured documents, or runtime decisions.

The core lesson is simple: instructions describe the intended work; the
capability surface makes the valid execution path available, bounded, accepted,
and observable.

Scoped extensions:

- For enforcement mechanics — submit tools, runtime-owned fields, output
  channel locks, provider schema use, allowed-set validation, grounding and
  provenance, deterministic projection, security and side effects,
  persistence and retry, and schema evolution — read and use
  `${CODEX_HOME:-$HOME/.codex}/guides/llm-capability-boundary-patterns.md`.
- For worked case studies applying this boundary, read and use
  `${CODEX_HOME:-$HOME/.codex}/guides/llm-capability-boundary-examples.md`.

## Core Model

- Instructions describe intended work, semantic criteria, tradeoffs, and
  completion criteria.
- The LLM performs semantic work: intent clarification, meaning assignment,
  materiality and causality judgment, rationale writing, option comparison,
  and evidence reduction.
- Runtime/tools perform authoritative mechanical work: parsing, counting,
  calculation, API calls, deterministic merge, serialization, validation,
  persistence, tests, and diff comparison.
- The capability surface provides structural constraints: accessible context,
  available tools, permissions, execution routes, artifact paths, accepted output
  channels, validators, retry policy, approval gates, and failure behavior.
- Canonical artifacts are created by runtime/tools, not by raw LLM prose, when
  downstream systems consume them.

Prefer this framing:

> The LLM may propose semantic content. The runtime decides what becomes
> artifact truth.

Use stronger prompts to clarify meaning. Use capability design to constrain
behavior that affects correctness, reproducibility, artifact truth, privacy,
security, or side effects.

## Capability Surface

The capability surface is the set of actions the LLM can actually take and the
outputs the runtime will actually accept. Shape it before relying on the LLM to
follow a rule.

Important levers:

- Accessible context: files, refs, rows, artifacts, source snippets, projections,
  and retrieved evidence the unit may inspect.
- Available tools: read tools, submit tools, validation tools, search tools, API
  tools, renderers, and their input schemas.
- Permissions: read-only, workspace-write, denied paths, network access,
  sandbox mode, route-specific side effects, and user approval.
- Execution routes: tool-capable executor, text-only executor, structured output
  route, direct-call route, deterministic runtime route, or human-review route.
- Artifact paths: exact output paths, canonical truth locations, temp paths,
  and denied write locations.
- Accepted output channels: submit tool call, structured JSON payload, runtime
  projection, generated YAML, markdown view, or final prose.
- Validators and gates: schema validation, unknown-field rejection,
  runtime-owned-field rejection, enum validation, allowed-set validation,
  grounding checks, provenance checks, citation checks, static checks, E2E
  checks, and semantic quality gates.
- Retry/fail policy: retry transient generation failures; fail clearly when the
  available route cannot enforce the required contract.
- Observability: prompt packet snapshot, model/provider version, schema hash,
  source snapshot, validator decision, retry reason, and artifact lineage.

## Boundary Decision Table

| Need | Primary authority | Preferred mechanism |
|---|---|---|
| Clarify user intent or product meaning | LLM | Prose reasoning and decision framing |
| Choose tradeoffs or materiality | LLM | Bounded semantic judgment with evidence |
| Produce open rationale or explanation | LLM | Free generation with shape constraints when needed |
| Inspect files or fresh facts | Tools/runtime | Search, parse, read, API call, source snapshot |
| Create canonical machine artifact | Runtime | Submit payload plus runtime serialization |
| Assign ids, paths, metadata, timestamps | Runtime | Runtime-owned fields |
| Merge artifacts by explicit rule | Runtime | Deterministic projection or merge |
| Validate syntax, schema, refs, counts | Runtime | Parser, schema, allowed-set, tests |
| Check source-span truth | Runtime | Grounding gate when decidable |
| Judge source trust or completeness | Runtime plus policy | Provenance, permission, staleness, trust tier |
| Prevent forbidden action | Capability surface | Make it unavailable, invalid, or unaccepted |
| Perform side effect | Capability surface plus policy | Risk class, permission, approval, audit log |
| Structured output required | Capability surface plus runtime | Submit tool or equivalent constrained channel |

## Structured Output Field Assignment

For each artifact field, assign one primary authority. Add layered checks for
cross-field invariants, security policy, privacy policy, and artifact-level
consistency.

| Field kind | Primary mechanism |
|---|---|
| Short closed values | Provider closed selection plus runtime enum validation |
| Runtime-known ids | Runtime-owned; provider enum only when LLM must select |
| Long refs and source snippets | Runtime closed validation; provider enum excluded |
| Evidence anchors | Grounding-blocked when source truth is decidable |
| Source provenance | Runtime-owned snapshot, hash, scope, trust tier, staleness |
| Open materiality or causal rationale | Free generation with structured shape checks |
| Side-effect decision | Capability surface plus policy and approval gate |
| Artifact envelope and serialization | Runtime only |

The goal is not to force every field into provider strict schema. The goal is
to use the weakest mechanism that is strong enough for that field.

## Generate-And-Validate

Generate-and-validate means the LLM generates a payload through one accepted
output channel, and runtime validates after generation.

It is useful when:

- fields are open and expressive
- iteration speed matters
- shape correctness is enough for the current step
- validator failures can be retried safely

It guarantees:

- expected top-level shape
- absence of unknown fields
- absence of runtime-owned fields
- parseable structured payload
- canonical artifact written by runtime

It does not guarantee meaning by itself. A well-formed payload can still contain
an unsupported claim, wrong ref, stale source, unauthorized source, unsafe link,
or semantically wrong category unless a validator or review gate catches it.

## Construct-And-Verify

Construct-and-verify means the runtime owns artifact construction, provides
closed choices where possible, and verifies grounded claims.

It is useful when:

- options can be enumerated before the LLM call
- refs or anchors can be checked against source truth
- invalid values must be impossible or fail-loud
- artifact authority or downstream impact is high
- side effects require permission, preview, or approval

It costs more:

- runtime must enumerate option space
- validators become product-critical code
- false constraints can exclude the right answer
- nuanced judgments can be discretized into the nearest bucket
- dependencies become more sequential

Use it per field or operation, not as a blanket replacement for LLM judgment.

## Design Procedure

Use this procedure when designing a new LLM-assisted artifact or revising an
existing one.

1. Identify the canonical artifact and downstream consumers. When the consumer already
   exists, read its **acceptance predicate**, not only its schema: the schema says which
   fields may appear, and the predicate says which combinations are credited. A producer
   designed against the schema alone can emit records that are valid and never
   accepted — one record per event where the consumer judges one record per subject is
   the common shape of this, and it survives every field-level check.
2. Split fields into semantic fields, deterministic fields, provenance fields,
   and side-effect operations.
3. Assign each field or operation one primary authority.
4. Decide the accepted output channel.
5. Shape accessible context and available tools around the task.
6. Make deterministic fields runtime-owned.
7. Decide which provider schema constraints are actually supported for the
   selected model and route.
8. Derive schemas and validators from one canonical source.
9. Add fail-loud checks for unknown fields, runtime-owned fields, unsupported
   refs, and denied actions.
10. Add grounding checks only where truth is decidable.
11. Add provenance checks for source trust, permission, freshness, and integrity.
12. Decide retry/fail policy by failure kind and side-effect class.
13. Make artifact persistence atomic and auditable.
14. Add focused tests for invalid values, unsupported refs, route rejection,
   grounding failure, policy failure, schema drift, and artifact persistence.
15. Report which checks prove shape, which prove wiring, which prove source
   grounding, and which only estimate semantic quality.

## Verification Checklist

- The LLM cannot create the canonical machine artifact through free prose.
- The accepted output channel is explicit.
- Structured output uses a submit tool or equivalent constrained channel.
- Runtime-owned fields are rejected if submitted by the LLM.
- Unknown fields fail loudly.
- Short closed values are provider enums where supported and runtime enums
  everywhere.
- Provider schema limits and refusal/incomplete behavior are tested for the
  selected route.
- Long refs are not provider enums when they are quote-heavy, private,
  tenant-scoped, or source-derived.
- Runtime allowed-set checks reject unsupported refs.
- Grounding gates are used only for decidable truths.
- Source trust, permission, freshness, and integrity are checked separately from
  source-span grounding.
- Tool inputs, tool results, retrieved content, LLM output, and rendered views
  are treated as untrusted at each boundary.
- Side-effect tools have risk classes, permissions, and approval gates.
- Human views are derived from machine artifacts when possible and sanitized
  before rendering.
- Artifact writes are atomic or have a clear recovery path.
- Retries are safe, idempotent, or explicitly blocked for the failure class.
- Schema, validator, allowed-set, prompt, and tests share one authority or have
  drift-catching tests.
- Observability captures prompt packet, model/provider version, schema hash,
  source snapshot, validator decision, retry reason, and artifact lineage.
