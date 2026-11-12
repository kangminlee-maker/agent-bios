---
created_at: 2026-11-13T04:45:00+09:00
head: 247e100
kind: design
---

# What an operation does, and where release 1's S11 writes

Lead decision, 2026-11-13, made while implementing S11 (`session-distill/runlib/stage_apply.py`).
The owner's decision it stands under is `D-20261113-f22b7d`: release 1's S11 writes approved
changes into files of the declared checkout and nothing else.

## The gap this closes

§7.3 names five operation types and the packet lists their fields — `create(path, content)`,
`edit(path, anchor, diff)`, `delete(path, anchor)`, `merge(units, into, text)`, `route(entry)` — and
`sequencing.apply_to` models their effect on a tree of names. Nothing said what an operation does to
a file's BYTES. S11 cannot be written without that, and a rule invented inside the stage would be a
contract nobody could read. The module's docstring is the contract's home; this record is why it
reads as it does.

## The contract

A target is `path` or `path#heading`. A heading names one ATX heading of the file, by its title with
or without its `#` marks, occurring exactly once outside fenced code; its section runs to the next
heading of the same or a higher level.

- **create** — the file is absent and becomes `content`.
- **edit** — with `anchor`, that exact text occurs once in the section (or the file) and is replaced
  by `content`; with a heading and no anchor the section is replaced; with neither the file becomes
  `content`.
- **delete** — the anchor's text, the section, or with neither the file.
- **merge** — each unit removed (its section, or its file), except the unit that is the target;
  then the target takes `content`.
- **route** — `entry` appended as one line to the section or the file; an entry already there is
  refused.

Every refusal has its own name (`HEADING_ABSENT`, `HEADING_AMBIGUOUS`, `ANCHOR_ABSENT`,
`ANCHOR_AMBIGUOUS`, `CREATE_TARGET_PRESENT`, `APPLY_BEFORE_MISMATCH`, …), and any refusal in the plan
means no file is written.

## What was closed

1. **Applying a model-written diff.** The packet's `edit(path, anchor, diff)` reads as a patch. A
   patch needs a patch engine: fuzzy context matching, or a subprocess. The first writes text where
   the model did not say; the second is a process, which `D-20261113-f22b7d` rules out. So an edit
   places `content`, located by a heading or an exact anchor that must occur once. An edit carrying
   only a `diff` is refused by name (`OPERATION_NOT_APPLICABLE`), not approximated. The packet's
   wording is to be brought in line with this.
2. **The journal under the owner's state root.** `journal.Confined` was written with
   `destinations.runtime_state` in mind. Release 1 writes no state root, so the journal and the plan
   live in the run directory, which is the run's own. The confinement is the same code with another
   root.
3. **Running an unfinished write again.** A write the journal holds as planned with no done record
   is not retried. The stage says whether the file is at its before-state, its after-state or
   neither, and stops (`APPLY_UNRECONCILED`). The checkout is a git repository the owner controls;
   inspecting and restoring it is theirs, and a new run applies again. Automatic recovery is release
   2's, with the commit.
4. **Layer-level drift as the gate.** `drift.operation_problems` refuses a target whose layer the
   declaration's `config_manifest_B` does not carry, and nothing computes that manifest yet, so it
   would refuse every operation. Release 1's drift check is per file: each operation carries the
   state S7 read when the proposal was written, and the file must be at that state at the plan and
   again, through its own descriptor, at the write. A file that moved is refused, not patched.
   Layer-level drift returns when the manifest is computed.

## What S11 does not do, stated so it is not assumed

No git, no installer, no hook, no personal layer, no state root, no nudge. `apply.json` carries
`not_done_by_this_stage` and the two commands the owner runs. Approved items that change the ledger
alone are counted and left to S12.

## Revisit

Release 2 decides whether S11 commits (the five deferred findings of
`2026-11-13T0130--0ab9fca--release-1-s11-writes-files-and-the-owner-commits.md`), and with it
automatic recovery and a personal-layer destination.
