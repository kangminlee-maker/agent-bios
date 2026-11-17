---
created_at: 2026-11-11T19:35:00+09:00
head: a1070cc
kind: design
supersedes: 2026-11-11T1925--731325f--two-unreachable-states-became-reachable-when-the-pointer-and-the-surface-became-facts.md
---

# WP-11b — done-when 3 is deferred to C3, and the C2 clone is deleted

The two records before this one left done-when 3 open and the C2 clone in place. The owner has
decided; this file replaces only that part of them. Everything else in both still holds.

## The decision (D-20261111-2b5f08)

**No S2 re-run on the C2 clone.** Done-when 3 is measured at **C3's own S2 run**: S5b runs there
after S5 and before S6, so the state distribution and the candidate bound are read before any paid
judging.

The reason is the read, not the cost. Every S2 run opens the owner's live session files — the census
holds absolute paths into `~/.claude/projects` and `~/.codex/{sessions,archived_sessions}`, and a
fixture HOME does not change that. D-20261103-c2f013 makes each such read the owner's own approval.
C3 needs that read anyway, so measuring there spends no approval that the work does not already
need.

**A correction to this lane's premise, from the lead.** The prepared script runs S2's `inventory`
part only, and this lane described that as the smaller read. It is not a lesser read: the inventory
part itself opens the owner's bound session files through the same absolute paths. "Inventory only"
means one artifact fewer, not one corpus read fewer. The script's own comment still carries the
weaker wording; it is left as it stands because the script is now C3's counting part and is not to be
changed until then.

## What was measured on the clone before it went, and what was not

The clone is deleted: `/tmp/l11b/c2/run`, 3.0 GB, gone. The original run was never amended and was
read only; the real-home canary (`~/.local/state/agent-bios`) was absent before and after every run
this lane made.

S5b never produced a document there. It refused by name —
`DELIVERY_EDGES_ABSENT 26855 current unit(s) carry no edges` — because the clone's inventory predates
lane E's `edges` export. These are the counts the clone did yield, read from its artifacts with no
S1 or S2 run:

| what | count |
| --- | --- |
| sessions in the inventory | 67,893 |
| sessions with a read pin | 39 |
| of those, with a selection inventory | 0 |
| pairs S5b owes | 24,962 |
| of those, with a decision ordinal | 436 |
| distinct sessions in those pairs | 3 |
| distinct units in those pairs | 1,897 |
| current units | 26,855 |
| current units whose own text this run could not see (redacted) | 14,116 |
| current units carrying `edges` | 0 |

The 39 pinned sessions all recorded `selection.status = unknown / input_failed`. That remains a **C2
OBSERVATION** and not a finding; C3's own S2 run is now what would confirm or clear it, and the
redaction share stays a **C3 fact** the owner should see beside the budget.

## What C3 runs

`work/impl/donewhen3-wp11b.py`, unchanged, as C3's counting part: it prints its plan and changes
nothing without `--approved`, refuses a checkout that does not carry S2's pointer and surface facts,
and collects the state distribution, the per-surface distribution, the reason histogram, the
unresolved-reference counts, the installer row, and the upper bound on candidates no longer pinned to
the `unknown` kind by the delivery column alone. The kind itself stays S6's: `derive.unit_outcome`
reads the judges' marks, which exist only after S6's calls.
