---
created_at: 2026-10-26T14:02:00+09:00
head: b65371c
kind: review
supersedes: 2026-10-24T0757--2018a38--a-control-that-passes-because-the-child-died-is-not-watching-the-fix.md
---

# An instrument that answers for a guarantee is part of the guarantee

Round 3 of the hermetic review of WP-07 package A returned ten findings. The owner chose to fix them
at their causes rather than one at a time, and the causes turned out to be one shape repeated: a
judge that enumerates the forms it knows admits the form it does not. `shed` copied every field of a
unit record and overwrote the ones it knew; the dispatch judge peeled whatever wrapper it
recognised; the self-test's bytecode claim rested on an observer that had itself been wrong twice.

This record replaces the named statements of the 0757 record and of 0308 behind it. What is
withdrawn here is withdrawn by the owner's narrowing of 2026-10-25 (decision draft 12 in the
round's working notes), not fixed: the claims were sound sentences about an instrument that no
longer exists.

## 1. What the 0308 and 0757 records claimed, and what is claimed now

0308 §1 rebuilt the audit-hook observer after round 2 found it blind to every event that was not an
`open`, and stated the rebuilt claim: **every attempted write whose real path is under the copy**,
with a per-event layout of path and `dir_fd` arguments, descriptors resolved through `F_GETPATH`,
`O_TRUNC` among the write flags, and a fail-closed `unverified` accounting. 0757 §1 carried that
forward. Round 3 then found two more holes in the same instrument (r3 #3, the `dir_fd` observation;
r3 #9, a failed-`mkdir` control that six successful events already satisfied).

**That claim is withdrawn.** The observer is removed — its `MUTATIONS` table of 37 events, its
`fd_path`/`resolve`/`record`/`hook` functions, its `sys.addaudithook` call, its `unverified`
accounting, and the two probe branches that existed to make it fire. What stands in its place is
three separate statements, each decidable on its own, none of which asks a reader to trust an
instrument this suite built:

* **The cause, in the entry files' own source.** `sys.dont_write_bytecode = True` must be a literal
  module-level statement of `session-distill/distill.py` and `session-distill/runlib/inventory.py`,
  and before it a module-level statement may only be the docstring, a `__future__` import, or an
  import of the standard library — judged against `sys.stdlib_module_names`, which the interpreter
  publishes, so the contract behind "this import is not ours" is Python's rather than a list of this
  repository's directory names. A guard nested in `if`, `try` or `with` is not the guard.
* **The cause, for loads by path.** Every `exec_module` in `runlib/inventory.py` is lexically inside
  a `with no_bytecode():` block. Unchanged from 0308 §1; it was always the second of two facts.
* **The effect.** A real invocation — the driver run as `__main__` through `runpy.run_path`, from an
  uncached copy of the checkout — leaves that copy exactly as it was: entry names, content hashes,
  mode, size and mtime in nanoseconds, with directories as entries of their own and links read
  rather than followed.
* **That the effect can fail.** The same run from a second copy, with the one line
  `sys.dont_write_bytecode = True` removed from its driver, leaves a `__pycache__` the same
  comparison reports. It runs first, on its own copy, which is then discarded.

## 2. What is no longer claimed, in plain terms

* **A write that was attempted and refused.** Nothing on disk records one. An audit hook fires
  before the operation, which is what made "attempted" askable at all; without the hook the question
  cannot be asked by comparing a tree, and it is not asked.
* **That every audited mutation kind is recognised and attributed.** `unverified=0` was a statement
  about the observer's coverage of CPython's audit events. There is no observer and no such
  statement.
* **That the instrument can see a write.** 0308's positive leg loaded `learn/redact.py` by path with
  the guard off, to show both the hook and the disk scan noticing. The disk comparison keeps a
  positive control of its own; the hook's half is gone, and `learn/redact.py` is no longer a
  copy-run member of that site.

## 3. Why narrowing is the correct direction here

The observer was wrong in rounds 1, 2 and 3 — four separate holes — and in every case it reported a
clean run. When an instrument is the evidence for a guarantee, a defect in the instrument appears as
a green result, which is the one failure mode that cannot be noticed by reading the result. The
three statements above are each decidable from a source file or from two directory listings, and the
fourth shows the listing comparison failing on demand.

The cost is recorded rather than argued away: the ability to see a refused attempt is lost, and
regaining it means building an observer again. **Revive condition:** a defect in which the command
attempts a write under a tree it must not touch, the attempt fails for an unrelated reason (a
permission, a missing parent, a read-only mount), and the tree therefore looks untouched. If such a
defect is found by any route, the observer is the instrument for it, and this record is the one to
supersede.

## 4. Scope of the cause and effect claims

Both claims cover **the distill driver (`session-distill/distill.py`) and the inventory's own entry
point (`session-distill/runlib/inventory.py`)**, because those are the two programs a user or a
control actually invokes, and the two files `ENTRY_FILES` names.

Every other script under `session-distill/` is **outside** these claims, with the reason: the other
`runlib/` modules are imported by those two and are therefore covered by the driver's own guard,
which is set before any of them is imported; `session-distill/screen-codex.py` is declared
out-of-scope for the dispatch closure and is not part of a distill run; and `session-cost.py` lives
outside `session-distill/` and is its own entry point, judged by nothing here. A new entry point is
covered by adding it to `ENTRY_FILES`, and until it is there, the judge says nothing about it —
which is why the judge refuses an empty set rather than passing over one.

## 5. What else in 0757 and 0308 is superseded, and by what

0757 §1's depth bound and the structural checker it described are superseded by this round's S4
(`1cd7705`): no self-test child runs a suite any more, so the recursion that needed a bound cannot
occur, and 0757's residuals about that checker and about unbounded production `git` calls moved with
it. 0308 §2's account of the startup handler is superseded by S2 (`9d234fc`): each entry file now
bootstraps its own fixed, path-free failure line around the import of the boundary module itself,
which is not the handler 0308 described.

The rest of 0308 and 0757 is **not** restated here, and this record does not claim it holds. Those
two records describe the tree at `2018a38`; this one describes `b65371c` and the commit it belongs
to. The record that restates, for this tree, whatever of them is still true is written after S7, at
the end of the round. Until that record exists, read any statement of 0308 or 0757 that is not named
above as a claim about `2018a38`, and re-derive it from the code before relying on it.
