---
guide_id: llm-capability-boundary-examples
parent: llm-capability-boundary
language: en
status: active
use_when:
  - looking for worked precedents of boundary and field-authority design
  - designing cases similar to sidecar submit, structured-output hybrid, MCP schema projection, or projection enrichment
---

# LLM And Capability Boundary: Worked Examples

This guide is a scoped extension of
`${CODEX_HOME:-$HOME/.codex}/guides/llm-capability-boundary.md`.
Each example records a problem, the structural path taken, and the learning.

## Lens Sidecar To Finding Ledger

Problem:

- Lens markdown was heterogeneous.
- Finding-ledger LLM had to reread and normalize noisy markdown.
- Runtime could not strongly guarantee ids, refs, artifact paths, or validation
  scaffolds.

Structural path:

- Add `submit_lens_findings` as a batched submit tool.
- LLM submits semantic finding fields once.
- Runtime writes `round1/{lens}.findings.yaml`.
- Runtime owns `session_id`, `lens_id`, `candidate_id`, `source_ref`,
  `human_output_ref`, validation, and YAML serialization.
- Optional markdown is rendered from the sidecar.
- When every lens output is a sidecar, runtime writes `finding-ledger.yaml`
  deterministically.

Learning:

- Machine artifacts should not depend on LLM prose formatting.
- Batched submit reduces partial-output and per-call overhead.
- Prompt packets can become audit packets when runtime owns the artifact.
- A tool-capable route is required; text-only fallback should fail clearly for
  this contract.

## Structured Output Hybrid

Problem:

- Provider strict schema can enforce short enums.
- Long evidence refs can contain quotes or source text that make provider enum
  schemas brittle.
- Pure post-hoc validation catches shape but not meaning.

Structural path:

- Use provider strict schema for short closed fields.
- Keep `evidence_refs` as string arrays in provider schema.
- Compute runtime allowed refs from prompt packet projections.
- Reject unsupported refs at submit time.
- Use a route where artifacts are created only by runtime submit handling.

Learning:

- Strict schema is real enforcement only where provider support and schema shape
  are suitable.
- Long refs need runtime allowed-set validation.
- Each field needs one primary authority plus enough layered checks.

## MCP-Projectable Schema Boundary

Problem:

- MCP/Claude tool surfaces need simple, directly valid object schemas.
- Internal artifact schemas may benefit from richer JSON Schema composition.
- Treating every repository schema as a tool schema can over-constrain internal
  design, while exposing composed schemas can break tool hosts.

Structural path:

- Expose pattern-valid canonical tool names: use `namespace_verb` snake_case
  such as `sheets_read`, matching `^[a-zA-Z0-9_-]{1,64}$`; reuse the catalog
  name for dispatch, audit, and allowed-tool config, and enforce it in catalog
  or seed validation.
- Treat MCP tool `input_schema` values and schemas intended for MCP/Claude tool
  projection as MCP-projectable schemas.
- For MCP-projectable schemas, prefer direct object schemas with explicit
  fields and avoid `oneOf`, `anyOf`, and `allOf`.
- Put variant behavior behind operation enums, deterministic dispatch, runtime
  validation, or explicit projection adapters.
- Internal-only schemas may use composition when it materially reduces
  complexity, but project them into compatible direct object schemas before
  they reach an MCP/Claude tool surface.

Learning:

- The compatibility rule belongs at the tool projection boundary, not as a
  universal ban on every internal schema.
- Tools/code should own projection and validation so the LLM cannot accidentally
  expose an incompatible schema shape.

## Issue Stance Matrix Projection

Problem:

- A compact projection lacked action and dependency context needed by later LLM
  units.
- Asking later units to reread raw artifacts would increase latency and drift.

Structural path:

- Enrich the runtime projection with action, dependency, threshold, singleton,
  shared-cause, and bounded-source-ref fields from authoritative upstream
  artifacts.
- Keep matrix merge deterministic.
- Validate refs against allowed source variants.
- Track projection coverage and fallback when omitted context may matter.

Learning:

- Projection-first enrichment is often better than expanding LLM context.
- Add semantic context to deterministic projections when later judgment depends
  on it.
- Projection quality needs coverage checks, not only schema checks.
