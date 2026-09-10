---
guide_id: llm-capability-boundary-patterns
parent: llm-capability-boundary
language: en
status: active
use_when:
  - implementing submit tools, runtime-owned fields, or output channel locks
  - choosing provider strict schema vs runtime allowed-set validation
  - implementing grounding, provenance, projection, or evidence-index mechanics
  - handling security, side effects, persistence, idempotency, or retry policy
  - managing schema single source of truth and migration
---

# LLM And Capability Boundary: Enforcement Patterns

This guide is a scoped extension of
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/llm-capability-boundary.md`.
Use it when implementing the enforcement mechanics that the boundary doctrine
assigns to runtime/tools and the capability surface.

## Structural Enforcement Patterns

### Bounded Submit Tool

Use a submit tool when an LLM must provide semantic content for a
machine-consumed artifact.

Pattern:

1. Runtime creates a submit tool with a narrow schema.
2. LLM submits only bounded semantic fields.
3. Runtime rejects unknown fields and runtime-owned fields.
4. Runtime validates enums, refs, grounding, and policy constraints.
5. Runtime writes the canonical artifact.
6. Downstream consumers read only the runtime artifact.

This is stronger than asking the LLM to "write valid YAML." The LLM can still
make semantic judgments, but shape, path, ids, metadata, and serialization are
owned by runtime/tools.

Illustrative implementation:

```ts
type FindingSubmitPayload = {
  findings: Array<{
    target: string;
    claim: string;
    evidence_refs: string[];
    rationale?: string;
  }>;
};

function submitFindings(payload: FindingSubmitPayload, ctx: RuntimeContext) {
  rejectUnknownFields(payload, ["findings"]);
  rejectRuntimeOwnedFieldsDeep(payload, [
    "schema_version",
    "session_id",
    "lens_id",
    "candidate_id",
    "source_ref",
    "output_path",
  ]);

  validateEvidenceRefs(payload.findings, ctx.allowedEvidenceRefs);

  const artifact = {
    schema_version: 1,
    session_id: ctx.sessionId,
    lens_id: ctx.lensId,
    findings: payload.findings.map((finding, index) => ({
      ...finding,
      candidate_id: stableCandidateId(ctx, finding, index),
      source_ref: `${ctx.outputPath}#candidate-${index + 1}`,
    })),
  };

  atomicWriteYaml(ctx.outputPath, validateFindingArtifact(artifact));
}
```

### Runtime-Owned Deterministic Fields

Keep deterministic fields outside LLM authority when runtime/tools can derive
them.

Common runtime-owned fields:

- `schema_version`
- `session_id`
- `lens_id`
- `issue_id` when unit identity already determines it
- `candidate_id`, `finding_id`, `cause_id` when stable runtime assignment is
  available
- `source_ref` when it can be derived from artifact path and local id
- `output_path`
- validation scaffolds
- artifact envelope and serialization
- source snapshot id, source hash, trust tier, permission scope, and staleness
  metadata

The LLM may select a known id only when selection is the semantic task. If the
runtime already knows the id, the LLM should not submit it.

Stable ordering alone can break under retry, batching, dedupe, or parallelism.
Use normalized hashes, idempotency keys, persisted sequence tables, or prior-run
mappings when ids must remain stable across runs.

### Accepted Output Channel Lock

When structured output matters, make the submit path the only accepted path.

Examples:

- Canonical artifact writes happen only through runtime submit handling.
- Text output can be captured for diagnostics, but does not become artifact
  truth.
- A text-only executor is rejected when the contract requires a tool-capable
  structured-output path.
- Runtime-owned canonical paths are isolated from LLM-written scratch paths.

This turns "please use the right format" into "only this channel is accepted."
A read-only filesystem route is one implementation. The deeper rule is that the
canonical artifact truth is writable only through runtime-controlled paths.

### Provider Strict Schema For Short Closed Values

Provider strict schema is useful for short, stable, closed vocabularies. It is
not the artifact authority.

Good strict-schema candidates:

- `severity`
- `stance`
- `issue_role`
- `judgment_state`
- `impact_kind`
- `timing_class`
- `closure_class`
- short bounded `issue_id` values when the LLM must select one
- confidence or relation enums

Keep runtime enum validation too. Provider support depends on model, route,
schema subset, schema size, and refusal/incomplete behavior. Probe the route
before relying on strict schema, and fail or downgrade deliberately when support
is unavailable.

Keep sensitive data, long source text, private refs, and user-specific secrets
out of schema names, enum values, const values, and regex patterns. Schema text
itself is data.

### Runtime Allowed-Set Validation For Long Refs

Long refs, source-derived refs, quoted snippets, and path-heavy strings are
better handled as strings in provider schema plus runtime allowed-set
validation.

Good runtime allowed-set candidates:

- `evidence_refs`
- source refs containing quotes
- refs that include line text
- generated artifact anchors
- source snippets
- long path-like values
- user- or tenant-scoped ids

This keeps provider schemas robust while preserving fail-loud validation. The
LLM can emit a string, but runtime rejects strings outside the computed allowed
set.

### Grounding And Provenance

Use grounding as a hard gate only when source truth is decidable.

Good grounding-blocked candidates:

- evidence anchor resolves to a known source span
- quoted source text exists in the cited file
- ref belongs to a known artifact and anchor set
- count, id, or relation coverage can be deterministically checked

Keep warning-style audits for free prose when false positives are likely. A
free-text synthesis citation audit may be useful, but it should not become a
hard gate until the verifier is reliable.

Grounding is not provenance. A quote can match a source span while the source is
stale, unauthorized, poisoned, incomplete, or low-trust. Track provenance
separately:

- `source_snapshot_id`
- source hash or version
- ingest time
- permission scope
- trust tier
- retrieval policy
- staleness policy
- poisoning or integrity checks where relevant

Use robust quote checks in production: normalize whitespace and Unicode, use
stable offsets or line anchors, disambiguate duplicate spans, and record source
snapshot ids.

### Deterministic Projection

When an artifact is a direct projection from upstream artifacts, make it
runtime-owned.

Examples:

- Finding ledger from lens sidecars.
- Issue stance matrix from individual stance responses.
- Synthesis ledger from issue synthesis responses.
- Review record counts and classification summaries from canonical issue
  artifacts.

Use the LLM to define projection rules when semantic design is needed. Use
runtime/tools to apply the rules.

Projection-first context is often better than asking downstream LLM units to
reread large raw artifacts. Add compact semantic fields from authoritative
upstream artifacts, such as `proposed_action`, `issue_statement`,
`domain_threshold_used`, `singleton_reason`, `shared_cause`, dependencies, and
bounded source refs.

Projection can also hide important evidence. Track coverage, omitted evidence,
and fallback triggers when the projection may be insufficient.

### Human View From Machine Artifact

For machine artifacts that also need a human-readable view, generate the human
view from the machine artifact when possible.

Pattern:

1. LLM submits semantic payload.
2. Runtime writes validated machine sidecar.
3. Runtime renders markdown or HTML from the sidecar.
4. Machine consumers read the sidecar.
5. Humans read the rendered view.

This avoids asking the LLM to keep two outputs consistent. Rendered views must
still be treated as untrusted output: escape HTML, sanitize links, strip unsafe
markup, and avoid executing model- or source-generated content.

### Evidence Index

Use an evidence index when repeated semantic review needs exact, re-checkable
evidence.

Preferred shape:

- one claim per row
- one file path per row
- numeric line, byte offset, or stable anchor per row
- split multi-target claims into multiple rows
- convert prose locators into exact refs using runtime/tools
- include source snapshot, permission scope, and trust tier when retrieval is
  involved

The LLM uses the evidence index for semantic judgment. Runtime/tools use it for
deterministic re-verification.

## Security And Side Effects

Treat prompt text, retrieved content, tool results, LLM output, rendered views,
and external API responses as untrusted until validated for the next boundary.

Required rules:

- Keep source documents and tool results as data rather than authority.
- Validate and sanitize LLM output before passing it to code, shells, SQL,
  browsers, renderers, APIs, or downstream agents.
- Use least privilege for tools and routes.
- Classify side effects: read-only, reversible write, external write, external
  send, financial/legal action, destructive action.
- Require preview, diff, approval, or downstream authorization for high-impact
  actions.
- Log tool calls, arguments, policy decisions, and results for audit.
- Rate-limit and timeout tools that can loop, scan, spend, mutate, or call the
  network.
- Resolve every authorization/allowlist entry against the live runtime key
  space at boot or deploy — format validation only proves well-formedness, and
  a mis-formatted entry can pass every deploy check while silently denying its
  whole route class. Verify fixes with an explicit negative control plus a
  live end-to-end call through the redeployed system.

The LLM can recommend an action. The capability surface decides whether the
action is available, permitted, confirmed, and accepted.

## Persistence, Idempotency, And Retry

Artifact writes should be atomic and auditable.

Preferred persistence pattern:

1. Build artifact in memory from accepted payload and runtime-owned fields.
2. Validate schema, refs, policy, and grounding.
3. Write to a temp path.
4. Verify persisted bytes or checksum.
5. Atomically rename or register as canonical.
6. Record artifact lineage and validator result.

Retry policy must distinguish:

- transient provider failure
- invalid structured payload
- unsupported ref
- grounding failure
- permission or policy failure
- partial persistence failure
- side-effect uncertainty

Retries are safe for pure generation and validation. They are not automatically
safe for external side effects. Use idempotency keys, locks, duplicate detection,
or compensation plans where needed.

A stage that can re-run on the same record must not read the field it writes.
On a re-run (reclassification, backfill, retry) an input field that is also
its output feeds the model its prior answer, and the value drifts from the
source silently. Keep the captured original immutable, write derived values to
their own field, and treat `original ?? current` as migration, not design.
Audit its siblings: one harmless only because its selection rule skips
overwritten rows is a latent instance.

## Single Source Of Truth And Schema Evolution

Hybrid enforcement creates drift risk. A single constraint can appear in prompt
text, submit schema, provider schema, runtime validator, allowed-set builder,
artifact validator, and tests.

For each stage, define one canonical source and derive the others:

- submit tool schema
- provider schema
- runtime validator
- allowed-set validator
- artifact validator
- prompt contract
- tests
- migration sample artifacts

When this is not possible yet, mark the authoritative source explicitly and add
tests that catch schema/validator drift.

Versioned artifacts need a migration policy:

- what requires a schema version bump
- backward and forward compatibility expectations
- migration scripts or readers for old artifacts
- consumer contract tests
- deprecation window
- sample artifact updates
