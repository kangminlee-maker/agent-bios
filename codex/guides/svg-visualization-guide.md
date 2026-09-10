---
guide_id: svg-visualization-guide
language: en
status: active
use_when:
  - creating SVG diagrams for architecture, pipelines, artifacts, runtime/LLM boundaries, or service blueprints
  - adding a blueprint SVG to IMPLEMENTATION_MAP.html
  - visualizing before/after structure, hot paths, postponed work, gates, quality checks, or artifact authority
  - replacing prose-heavy implementation status with a compact visual decision aid
core_rules:
  - make each SVG answer one judgment question
  - separate time flow from authority flow when they differ
  - use stable role colors for input, runtime/tools, LLM, artifact, view/UI, gate, quality, postponed work, and downstream work
  - label format and authority separately so canonical artifacts and projections are not confused
  - keep hot-path work visually separate from postponed or excluded work
  - prefer lanes, legends, short labels, explicit arrows, and compact nodes over dense prose
  - validate SVG syntax and visual layout when practical
verification_focus:
  - the SVG has one clear question
  - input and output are obvious
  - runtime/tools and LLM responsibilities are visually distinct
  - canonical artifacts and projections are labeled separately
  - hot path and postponed work are separated
  - gates and quality checks have different meanings
  - text does not overlap and arrows remain readable
---

# SVG Visualization Guide

Use this guide when a diagram needs more precision than a Markdown table or
Mermaid diagram can provide. The goal is not decoration. The goal is to help a
reader quickly decide what the system does, where authority lives, what is on
the hot path, what is postponed, and what must be verified.

For `IMPLEMENTATION_MAP.html`, include one self-contained SVG service blueprint
that shows the whole service or implemented system at the right level of
abstraction.

## Slide And Presentation Work

When creating, revising, or reviewing slides or presentation materials, read the
normal guide at `${CODEX_HOME:-$HOME/.codex}/guides/slide-writing.md` for
the semantic criteria before choosing a visual expression. Read its companion
runbook only for an explicitly applicable static HTML/PDF job path. This guide
helps make logical relationships visually readable; it does not replace the
that guide's source-fidelity, hierarchy, spacing, or review criteria.

## When To Use SVG

Prefer SVG when the visual needs any of these:

- before/after structure
- sequential pipeline flow
- multiple lanes or layers
- artifact relationships
- runtime/tools and LLM responsibility boundaries
- canonical artifact versus projection distinction
- gate, quality review, and UI projection in the same view
- postponed or excluded work beside the hot path
- a self-contained browser-readable visual artifact

Prefer a Markdown table or Mermaid diagram when the structure is shallow, has
five or fewer items, or the exact text diff matters more than layout.

## Core Principles

### One Judgment Question

Each SVG should answer one clear question.

Good questions:

- How does source authority become a canonical artifact consumers trust?
- Why does this pipeline need both a chunk pass and a bridge pass?
- How did input authority change before and after this redesign?
- What is the current service blueprint and where are the gates?

The SVG may cover many nodes, but all nodes should support the same question.
Detailed history, exhaustive task lists, and long explanations belong outside
the SVG.

### Time Flow And Authority Flow

Separate time flow from authority flow when they differ.

Time flow example:

```text
input -> stage 1 -> stage 2 -> stage N
```

Authority flow example:

```text
source/chat/decision/config
  -> canonical JSON artifact
  -> runtime projection
  -> confirmed handoff
```

Use separate lanes or distinct arrow styles when the reader needs to see both.

### Stable Role Colors

Use the same role colors across diagrams so the reader does not relearn the
legend.

| Role | Color | Meaning |
|---|---|---|
| Input | Blue | User source, chat, decision, config snapshot |
| Runtime/tools | Green | Deterministic parse, merge, projection, id/ref/digest creation |
| LLM | Amber | Semantic interpretation, drafting, relation judgment |
| Artifact | Slate/gray | Canonical or generated file |
| View/UI | Purple | HTML review, confirmation UI, user-facing projection |
| Gate | Red | Deterministic blocking check |
| Quality | Cyan | Non-blocking quality report or competency question |
| Postponed/excluded | Orange | Later decision, later collection, outside hot path |
| Future/downstream | Dashed gray | Later phase, downstream system, future redesign |

Color is not enough by itself. Use labels and legends too.

### Format And Authority

Each important node should show at least two of these:

- human-readable name
- artifact or concept id
- format
- owner
- authority status

Example:

```text
Confirmed Planning Input
JSON canonical + YAML projection
Runtime owns schema/ref/digest
```

YAML, Markdown, and HTML may be projections rather than canonical artifacts.
Label that distinction directly.

### Hot Path And Postponed Work

Complexity reduction often depends on what the system leaves out. Show hot-path
work and postponed or excluded work in the same SVG, but in separate lanes or
side boxes.

Examples:

```text
post_decision: fields resolved by a later decision
post_collection: assets gathered in a later step
placeholder_need: reserve context for later collection
```

Postponed items should not sit inside the main flow.

## Recommended SVG Structure

### Title And Subtitle

Use a title that names the target and purpose. Use a subtitle for the single
judgment question.

```xml
<text class="title" x="70" y="72">Input Authority Rebuild Plan</text>
<text class="subtitle" x="72" y="108">How confirmed source authority becomes a canonical artifact</text>
```

### Legend

Place a compact legend near the top. The legend should explain:

- role colors
- artifact formats
- arrow meanings
- hot path versus postponed work when relevant

### Lanes

Use lanes to make complex diagrams readable. Keep the lane count small.

Recommended lanes:

```text
Inputs
Runtime/tools
LLM semantic work
Canonical artifacts
Views, gates, and quality
Postponed or downstream work
```

For before/after comparisons, use two columns instead of many lanes.

### Nodes

Keep each node to three to five short lines.

Recommended node shape:

```text
Node title
Plain behavior
Important constraint
artifact_id or format
```

Use monospace-like styling for artifact ids when useful. Keep long prose in the
surrounding document.

### Arrows

Use arrow meaning consistently.

- Slate arrow: normal data flow
- Green arrow: runtime-owned deterministic flow
- Amber or blue arrow: LLM semantic submit/candidate flow
- Red arrow: gate or blocking condition
- Dashed gray arrow: optional, future, downstream, or projection-only flow

When arrows cross too much, add a lane, hub node, or intermediate artifact.

## Implementation Map Blueprint

The `IMPLEMENTATION_MAP.html` blueprint SVG should explain the current service
or implemented system, not every file and task.

It should answer:

- What enters the service?
- What leaves the service?
- Which steps are runtime/tools work?
- Which steps are LLM semantic work?
- Which artifacts are canonical?
- Which views are generated projections?
- Which gates block progress?
- Which quality checks disclose risk without blocking?
- Which items are postponed, excluded, downstream, or future work?

Use the blueprint to support decisions. A reader should be able to understand
the current architecture, hot path, authority boundaries, and main risks without
reading a long progress log.

## Layout Rules

Recommended default:

```xml
<svg width="1900" height="1640" viewBox="0 0 1900 1640">
```

Use these layout defaults:

- Width around 1800-1900px for complex blueprints
- Lane gaps of at least 30-40px
- Node gaps of at least 60-80px
- Node width of at least 240px
- Fixed font sizes
- Letter spacing of 0 except tiny badge cases
- Manual line breaks for long labels
- Larger boxes when text could overflow
- Hub nodes when arrows would cross heavily

## Accessibility And Visual Hygiene

Include `role`, `title`, and `desc`:

```xml
<svg role="img" aria-labelledby="title desc">
  <title id="title">...</title>
  <desc id="desc">...</desc>
</svg>
```

Keep visuals plain and readable:

- simple fill and stroke
- wide margins
- clear lanes
- fixed color system
- short labels
- no text overflow
- no decorative gradients, orbs, blobs, excessive shadows, or nested cards
- no unnecessary icons

## Procedure

1. Write the judgment question in one sentence.
2. Split concepts into up to five or six lanes.
3. List three to five nodes per lane.
4. Mark each node owner: input, runtime/tools, LLM, artifact, view, gate,
   quality, postponed, downstream.
5. Label machine-consumed outputs by format and authority.
6. Put postponed or excluded work in a separate lane or side box.
7. Draw arrows with consistent meanings.
8. Validate syntax and inspect layout.

## Verification

Run syntax and diff checks when practical:

```bash
xmllint --noout path/to/file.svg
git diff --check -- path/to/file.svg
```

If the SVG is embedded in HTML, inspect it in a browser or screenshot when
layout matters. Check that:

- text does not overlap
- arrows do not obscure meaning
- lane titles and node titles are easy to scan
- hot path and postponed work are visually separate
- runtime/tools, LLM, gate, quality, artifact, and view colors match the legend

## Completion Criteria

The SVG is complete when:

- it answers one judgment question
- input and output are clear
- runtime/tools and LLM responsibilities are separated by label and color
- canonical artifacts and projections are distinct
- needed JSON/YAML/Markdown/HTML formats are labeled
- hot path and postponed or downstream work are separate
- gates and quality review have different visual meanings
- text does not overlap
- syntax and diff checks pass when available
