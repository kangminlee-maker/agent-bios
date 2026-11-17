---
created_at: 2026-11-11T19:25:00+09:00
head: 731325f
kind: design
supersedes: 2026-11-11T1810--364ff10--the-delivery-evidence-is-assembled-from-the-records-and-the-compiled-text-stays-the-owners.md
---

# WP-11b — the two unreachable states, and what made them reachable

The record this supersedes stated, truly of the tree at `364ff10`, that two of §6.3's states could
not be produced from run artifacts and were declared unreachable in the fixture library with their
reasons. Both are reachable at `731325f`. Everything else in that record still holds; this file
replaces only its "two state paths cannot be reached" section and the fixture count.

## What was missing was a fact, not a mechanism

`exposed_not_read` exists only on the guide surfaces, whose `pointer exposed` level asks whether the
compiled instruction text holds the item's own pointer. The catalogue route to `not_delivered` needs
the ladder of an item the session was NOT given, and a unit's surface was published only for the
items it was. Both are predicates over something the run does not hold — the compiled text, and the
installed baseline — so both are answered where that something is readable, at S2, and published as
facts in the shape `4ab59b6` established. No text enters the run (D-20261111-f2b23b).

A selection inventory publishes:

- per selected item, whether the compiled text held **its** pointer, with the basis named
  (`router_line` for a relevant item, `emitted_path` for a requested one). A surface with no pointer
  in the text is published as **having none**, never as a pointer that is missing; the judge's reader
  keeps the two apart. The emitted path's spelling comes from the catalog's own `_safe_ref_path`
  through the shipped loader, and the test is on the relative path, which the absolute one in the
  text ends with.
- the **router path the text itself names**, read out of that text, because what the judge asks is
  whether the text names it.
- per unit the selection holds, the **catalogue surface** of its item and where it was read: the
  snapshot for the items the session was given, the installed baseline for the rest, null for a unit
  neither names.

Absent rather than empty when this run cannot compute them: the pointer predicate needs the text and
the shipped loader, and an empty list beside a selection that holds items would read as "no item has
a pointer anywhere".

## The classifier is asked before a surface is attached

S5b attaches a published surface per pair, but only where `delivery_evidence.surface_row` cannot
place the unit already. The native layers are matched **by layer**, and attaching a surface to one
moved it onto the always-rule ladder, where its recorded-injection absence read as `not_in_release`
instead of `not_in_recorded_injection`. The frozen native fixture caught it; nothing else would
have, because every always-surface fixture still passed.

## The library is eight paths with none declared unreachable

`exposed_not_read` from a requested guide whose pointer the text held and whose file nothing read;
`not_delivered/selection_lacks_item` from a selection that was read, holds another item, and a
release that holds this one at a complete reference point. The native `not_delivered` path stays
beside it, because the two are different routes to one state and the code treats them differently.

## Still open

The installer surface stays `unknown: unbound` with its producer named absent — an exclusion with its
revisit condition recorded (D-20261111-a5dd11): **when S2 publishes the installation receipt's
facts**. The binding is a verdict over the owner's state root, and the acquisition boundary is S2's.

**Done-when 3 is still not run.** S5b refuses on the C2 clone by name
(`DELIVERY_EDGES_ABSENT`, the clone's inventory predates lane E's `edges` export), and the
measurement needs S2 re-run there. That re-run opens the owner's live session files, because S2's
census holds absolute paths into `~/.claude/projects` and `~/.codex/{sessions,archived_sessions}` and
a fixture HOME does not change it; D-20261103-c2f013 makes each such read the owner's own approval.
The exact sequence is prepared as a script outside the repo
(`work/impl/donewhen3-wp11b.py`), which refuses to act without `--approved` and without a checkout
carrying these facts; the lead runs it once when the approval arrives.

## Numbers at this head

| suite | controls |
| --- | --- |
| `inventory.py --self-test` | 1405 |
| `stage_delivery.py --self-test` | 99 |
| `delivery_evidence.py --self-test` | 63, over 9 frozen judge fixtures |
| `distill.py --self-test` | 145 |
| records-level §6.3 fixtures | 8 state paths |

`pretrial-wp11b-c10` 12/12. Two of its rows were re-anchored after the first run, and both are
findings of the discipline rather than of the code: a check that accepted an empty list as "a list"
passed over a reverted producer, and a row the frozen fixtures catch first now names both texts.
