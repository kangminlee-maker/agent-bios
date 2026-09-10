---
guide_id: implementation-map
language: en
status: active
use_when:
  - creating or updating IMPLEMENTATION_MAP.html in a repo with implementation code
  - building the single SVG service blueprint inside it
  - deciding what belongs in the current-state dashboard vs isolated history notes
---

# Implementation Map Guide

Scoped extension of the **Implementation Map** section of the global instructions. Use this when creating or updating `IMPLEMENTATION_MAP.html` for a repo with implementation code.

## Purpose

`IMPLEMENTATION_MAP.html` is a **current-state dashboard** — it answers "where is this work now, what decides next, and what is at risk," not "what happened." It is not a changelog, handoff log, or accumulated project diary.

## Build / rebuild rules

- Rebuild it around the current task, current architecture, current risks, current decisions, and current verification status.
- Compress completed history into the smallest useful summary; keep detailed past progress, abandoned alternatives, and long completed-task lists in isolated notes (`docs/`, `design/`, `archive/`).
- The first viewport must show current goal, phase, health, next decision, and main risk.
- Make it a self-contained HTML view with compact visual sections for status, architecture, roadmap, decisions, risks, verification, and change impact.
- Update it before committing, when writing a handoff, or after meaningful architecture, roadmap, risk, decision, or verification changes.

## The SVG service blueprint

Include exactly **one** self-contained SVG service blueprint that visualizes the whole service or implemented system at the right level of abstraction. Build it using `${CODEX_HOME:-$HOME/.codex}/guides/svg-visualization-guide.md`.

- Keep the blueprint focused on a single judgment question; use compact nodes rather than exhaustive file or task lists.
- Use stable lanes, a legend, fixed role colors, short labels, and explicit arrows to separate: inputs, runtime/tools, LLM work, canonical artifacts, views, gates, quality checks, postponed work, and downstream/future work.
- Distinguish time flow from authority flow, and distinguish canonical artifacts from JSON/YAML/Markdown/HTML projections.
- Validate SVG syntax and layout hygiene when practical; ensure text does not overlap, and keep hot-path work visually separate from postponed or excluded work.
