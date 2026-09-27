---
created_at: 2026-09-27T20:02:02+09:00
head: 28d1102
kind: backlog
supersedes: null
---

# Backlog — setting a repository's AGENTS.md while keeping every existing statement

Owner's request, 2026-09-27: a skill that sets up a repository's `AGENTS.md`. Where an
`AGENTS.md` or `CLAUDE.md` already exists, its existing content is rearranged into our structure
with nothing lost. Nothing here is designed or decided; this records the request and what the
current skill does.

## What exists

`claude/skills/repo-charter/SKILL.md` (design `2026-08-13T1422--8e7c44e--design.md`, dogfood
`2026-08-16T2114--20845ff--dogfood.md`) writes or overhauls a repository's `AGENTS.md`, with
`CLAUDE.md` as a one-line shim. It works like this:

- It drafts **from the code first**: invariants, gates and traps. It opens the existing
  instruction file only at its last step, deliberately, so the old file's structure does not
  anchor the draft.
- At that last step it checks each existing claim against the code and shows the person the
  draft beside the existing file, naming the divergences.

Nothing in the skill requires that every existing statement survive. An overhaul can drop
content, and nothing would notice. That is the gap this request names.

## What "without loss" asks for

- **An inventory** of every statement in the existing files: root and nested `AGENTS.md` and
  `CLAUDE.md`, and what they import (`@` imports, rule directories).
- **One disposition per statement.** Each is:
  - kept in its place in the new structure;
  - moved behind a pointer into a guide or document;
  - merged with a duplicate; or
  - marked stale against the code that contradicts it, and moved to a dated record rather than
    deleted.
- **A closing check** that the dispositions cover the whole original text. Map each original
  sentence or line to exactly one disposition, so a dropped statement fails by name.
- **The originals kept** (git history or a dated copy), and the person shown the mapping before
  anything is written.
- **Claude-only content in `CLAUDE.md` stays reachable** when `CLAUDE.md` becomes a shim that
  imports `AGENTS.md`.

## Questions to settle before building

- **Extend `repo-charter` or add a second skill.** Default by concept economy: extend it with a
  reconcile step, keeping "draft from the code first". The losslessness is enforced at
  reconciliation, and a second skill writing the same file would be two owners of one file.
- **What "our structure" means.** The skill's category vocabulary (orientation, invariants,
  gates, traps, …), and this repository's own `AGENTS.md` conventions: every rule names what
  enforces it, and the file states current behaviour only.
- **Step 0's "decide whether a file is warranted".** How does it read when a file already
  exists? The person already has one, so the choice is between restructuring it and leaving it.
- **How this meets the Team work-environment design.** That design treats a repository's
  authored Instructions as a source (SSOT S05, the `repository_authored` home mode in
  `workenv/sources/`). The structure the skill writes should be one V1 can read as
  repository-authored units.

**Start condition:** none blocking. It is independent of V1's remaining slices.
