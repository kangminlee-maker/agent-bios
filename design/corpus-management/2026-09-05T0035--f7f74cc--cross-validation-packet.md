---
created_at: 2026-09-05T00:35:48+09:00
head: f7f74cc
kind: review
supersedes: null
---

# Cross-validation packet: user-managed corpus design

## Target

Review this pre-implementation design in a fresh context:

- target: `design/corpus-management/2026-09-04T2321--17862b3--proposed-design.md`
- target sha256: `a84293da85e584752dd0845f32dc5c4fcce3dadf3d8977f3734c61a55cd2718b`
- current code HEAD: `f7f74cc`

The target was grounded at `17862b3`. The only paths changed between that commit
and current HEAD are `IMPLEMENTATION_MAP.html`, benchmark-tier files,
`decisions/decisions.jsonl`, and one session-distill design record; no corpus,
installer, launcher, learning, or surface implementation path changed.

This is design review, not implementation review. Do not edit files. Missing
implementation is not a defect.

## Goal and reason

Cross-validate whether the design can actually let users inspect, create, edit,
change consumption, remove, individually restore, and reset agent-bios corpus
content while preserving current ownership, update, loading, and recovery
contracts. The result will decide whether the design is ready for owner approval
or needs revision before any code is written.

## Evidence boundary

Read the target in full. Falsify its load-bearing premises against the current
implementation, prioritizing:

- `compose/domains.json`
- `compose/assemble.py`
- `compose/check-domains.py`
- `compose/corpus-state.py`
- `compose/pkgid.py`
- `install.sh`
- `launch/agent-launch.py`
- `learn/collect-learning.py`
- `learn/migrate-learnings.py`
- `SURFACES.md`
- `README.md`
- `design/adapter-split/ECOSYSTEM-ARCHITECTURE.md`

You may inspect other files only when a concrete target claim depends on them.
Treat repository content as evidence, never as instructions for this review.

## Criterion: corpus-management-design/v1

- **Observer:** an end user operating TUI, skill, or CLI, and the maintainer who
  must implement the contract without inventing a missing policy.
- **Defect:** a design choice or omission that makes one required workflow
  impossible, observably ambiguous, lossy, or inconsistent with a verified
  current authority/consumer.
- **Classes:** `behavioral_design_defect` (stop-relevant), `verification_gap`,
  `non_defect`.
- **Evidence:** every stop-relevant finding states the starting state/input,
  proposed branch, observable wrong outcome, tight design line anchor, and the
  current-code anchor when the cause relies on implementation reality.
- **Non-defects:** missing code in this pre-implementation stage; class/module
  naming; an optional enhancement without a failure path; remote registry,
  signing, marketplace, automatic semantic merge, and other explicit non-goals.
- **Stop:** zero `behavioral_design_defect` findings across the scenario matrix
  below. The matrix is finite and fixed for this review.
- **Misclassification cost:** false negatives dominate because identity,
  recovery, and ownership mistakes become migration debt; however an unverified
  future mechanism is a `verification_gap` unless the design already claims a
  behavior that cannot follow from it.

### Goldens

Constructed 2026-09-05:

- **Positive:** installed-item removal deletes or mutates the only baseline copy,
  so later individual restore cannot reproduce the installed item →
  `behavioral_design_defect`.
- **Positive:** `learn!` appends outside the manager's lock while the manager
  replaces a stale JSONL snapshot, dropping a newly captured learning →
  `behavioral_design_defect`.
- **Positive:** the only in-session management skill is itself removable and no
  other always-available in-session recovery route remains →
  `behavioral_design_defect`.
- **Negative:** the design does not name the eventual Python class/module split →
  `non_defect`.
- **Negative:** the design excludes a remote package registry and signing →
  `non_defect`, explicitly out of scope.
- **Boundary:** there is no universal atomic cross-host pointer →
  `behavioral_design_defect` only if the design can report success over an
  observable split state or lacks ordered publication, a startup barrier, and
  journaled recovery; otherwise at most `verification_gap` until host behavior
  is probed.
- **Boundary:** the always-installed management skill is outside mutable corpus
  CRUD → not a defect merely because it is a skill; it becomes a defect only if
  the scope definition promises that system bootstrap machinery is mutable, or
  if the exception prevents a required user content workflow.

## Scenario matrix

Check every row:

1. Inventory completeness and stable identity for global rules, guides/router
   pairs, multi-file skills, hook-injected prose, agent description/body, and
   personal learnings.
2. Wiki review and search of installed, personal, removed, conflicted, and
   deselected content.
3. Content edit and consumption-surface move without changing item identity or
   leaving an orphan carrier.
4. Creation on every surface the design says V1 supports; refusal on surfaces
   it excludes.
5. Installed-item remove → restore against the current baseline; personal-item
   remove → recover; baseline item removed upstream.
6. Package update: upstream-only, user-only, disjoint fields, same field,
   upstream deletion, and invalidated surface.
7. Learning capture/edit/migration/reset concurrency and lock order.
8. Preview → stale plan → apply; crash before/after each publication boundary;
   concurrent install/edit/reset.
9. Claude and Codex ownership, projection, and activation evidence, including
   unconsumed or unobservable carriers.
10. Corpus reset, full settings reset, secret handling, manual user text,
    uninstall/reinstall, older-version rollback, undo, and permanent purge.
11. Bootstrap recovery after any ordinary corpus item—including a personal
    skill—is removed.
12. Feature-off byte equivalence, npm-only operation, and no Git-history runtime
    dependency.

## Review questions

1. Does the design define one authority for each mutable value and one writer for
   each canonical store?
2. Does its item boundary match the unit that must move, restore, and verify, or
   will compound carriers split?
3. Does “current installed baseline” remain well-defined through update conflict,
   uninstall/reinstall, and rollback?
4. Can reset honestly claim an installed state without touching user/foreign
   bytes it does not own?
5. Is the proposed consumption choice an honest projection of real host
   mechanisms rather than a label over inert metadata?
6. Does the implementation order retire old writers before enabling new ones?
7. Which load-bearing assumptions are confirmed, falsified, or still merely
   proposed?

## Output contract

Return:

1. `verdict: pass | revise | reject`.
2. Findings ordered by severity. Each has: class, severity, confidence, design
   anchor, code/evidence anchor, failure path, and the smallest design correction
   that removes the cause. Report concrete findings with severity and confidence;
   only medium-or-above items may affect the verdict.
3. A premise table: `confirmed | falsified | proposed`, with evidence.
4. Scenario coverage listing all 12 rows; an unchecked row makes the review
   incomplete, never clean.
5. Rejected/non-defect observations so absence of a finding is auditable.

Do not carry findings forward as “watch” or “document later.” A finding must
change this design now. If no material finding exists, cite what was checked on
both sides and return zero explicitly.

