---
created_at: 2026-11-10T13:50:00+09:00
head: ebf98ab
kind: design
supersedes: null
---

# A refused call in inventory's self-test fails by name, and its block runs to its end

Package pre10, before WP-10. Two decisions asked for it. D-20261102-f5cf48 left nine of WP-07's revert rows (c71af0e)
cutting a self-test block: each row's named control still failed, but the rest of the block did not run, so that
block's other controls were lost under that revert. D-20261110-7f976d asked for a control that a member of a
`nothing_new` unit arrives bound from the census. Only `session-distill/runlib/inventory.py`'s `self_test` changes; no
product line does.

## What lands

- `judged(name, call, shape=None, record=None)`, defined beside `section`. It runs `call`. When the call raises an
  Exception, that is one failed check, `<name> completes`, with the exception's type and first 300 characters. The
  answer then reads as `Absent`, or as a tuple of `shape` Absents when the caller unpacks it, so the controls after it
  still run and fail by name. When the call answers, that is one passing check and the answer. `judged_run` is now
  `judged` over a full `run`; its check names and details are unchanged.
- The calls where the nine rows' blocks stopped are judged (D-20261102-f5cf48 named the rows, the pretrial below found
  the calls):
  - P2.1: the records run's store document, release index and sessions document (T3, T8, W22, 13a-r);
  - GA#0 (security review): the headed guide's and the absolute-path package's shed (P1R1);
  - GA#6-8: the pinned session's frozen inputs and its release inventories (V8);
  - #16: the clean copy's statuses, a pair the block unpacks (V8, W12, 13a-r, P1R1); the block's matrix cases already
    caught their own;
  - GC#4: the five shed calls (P1R1);
  - the R1#0/R2#0 differential's helpers `emitted_strings` (its shed) and `document_strings` (its emitted document),
    which r5 F0 and r4 R0 also call; r3 S1's `context_strings` (its shed) and the masked-mention write's shed (P1R1);
  - P2.6: `p26_reference` and `p26_shared` (P1R1), and the A1 context sets of the unplanted universes (Y73, Y78).
    `p26b_sets` itself is not judged: A1's planted cases call it under `_raised` and need its refusal.
- Names later blocks read are bound before anything in their block can raise:
  - R1#0/R2#0's helpers (`strings_in`, `emitted_strings`, `document_strings`, `withheld_lines`) now stand first in
    their block. Under P1R1 the block stopped before them, and r5 F0 and r4 R0 then stopped on an unbound name.
  - P2.6's A3 originals (`p26_a3_kept`) and their stand-in (`p26_no_read`) now stand at the top of the closures block.
    The context-set block restores the file readers with them in a `finally`. A restore that cannot name the
    originals leaves every way of reading a file raising for the rest of the suite.
  - GC#4's carriers are bound in place. With its calls judged, the block runs to its end under every row.
- A presence term where an Absent answer would pass a check on an empty subject (the contract `Absent`'s docstring
  states): the headed guide's masking, GC#4's far, multi-line, escaped and heading checks, and r3 S1's "no string of
  that published document carries the credential". Each is unchanged on a passing run; the pretrial's `none` row
  shows it.
- `29cc92: a member of a nothing_new unit arrives bound from the census and is read`, after the 85f3e8 control. A Codex
  root and its spawned child, every record of both on 2026-09-20, before the census fixture's window. The census reads
  the child in full before it decides the root `nothing_new`, so the child's row carries its hash and
  `transcript_records` reads it as `bound`. The check also requires the root to be `nothing_new` and the child
  `child_of`, so it cannot pass on another case.

## Evidence

Work tool `pt10-pretrial.py` (not committed): each row in a fresh copy of the tree without `.git`, the inventory suite
run in full, under a fake HOME and `TMPDIR=/tmp/p10`; no model call and no network.

| Row | Before (ebf98ab) | After |
| --- | --- | --- |
| none | pass | pass |
| T3, T8, W12, W22, Y73, Y78 | caught, 1 block cut each | caught, 0 cut |
| V8, 13a-r | caught, 2 cut each | caught, 0 cut |
| P1R1 | caught, 9 cut | caught, 0 cut |
| census reads no member of a root owning no record of the window | missed, no failure at all | caught by the 29cc92 control alone |
| `judged` lets the refusal out | (new) | caught |
| `judged` answers None for a refusal | (new) | caught |

No row prints a traceback. In every row, every failure the row had before is still among its failures. The new ones
are the `<name> completes` failures, which name each refusal, and the controls of the blocks that now run to their end.

## Not done

- Other production calls the self-test makes directly, outside `judged`, `judged_run` and `_raised`, are left as they
  are: about 13 `shed`, 9 `store_document`, 5 `release_index`, 8 `freeze_inputs`, 7 `emitted_document`, 15
  `write_document` and others (counted on ebf98ab, with `units_of` and `carrier` fixture builders on top). A revert
  that makes one of them raise still cuts its block. The cut is a failed check named
  `<block> did not run to its end: <type>`, so no verdict is lost. Only that block's later controls are lost, as
  before this package.
- Downstream of a refused shed, a control that asks for an absence (the differential's `leaks={}`) passes on what was
  emitted, which is nothing. The refusal itself fails by name, so the suite does not pass.
