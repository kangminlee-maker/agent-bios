---
created_at: 2026-09-23T05:50:35+09:00
head: 18b0b9b
kind: review
supersedes:
---

# Is the design still valid? — a review against the trimmed plan

The design SSOT is dated 2026-09-15. The plan and catalog were trimmed on 2026-09-22,
removing ten features, and P01 has since frozen twelve contracts. This asks whether the
design still describes what is being built, and lists what has to change.

**The answer is that nothing is unguarded and several documents are stale.** The plan is
coherent; the documents describing it are not.

## Method

Four blind reads of the SSOT against the plan, the catalog, `gates/workenv/case-index.json`
and the frozen contracts, one per section group, each asked to classify every divergence
and to check a kept case before calling anything a gap. Their findings were re-derived here
before being accepted. Classes: **TEXT-STALE** (the feature and its guard went together, so
the fix is documentary), **GUARD-GAP** (the situation still occurs and nothing guards it),
**CONTRADICTION**, **CONFIRMED**.

S10 to S14 had not reported when this was written; its range is the acceptance table, the
exclusion table and the maintenance rule, so the list below is not complete for those.

## What holds

| Claim | Checked by | Result |
| --- | --- | --- |
| The design's own criterion is current | the SSOT's quoted purpose against `AGENTS.md` | byte-identical, 873 characters |
| The plan bundle is sound | `gates/check-development-plan.py` | valid; 28 positive and 412 negative controls |
| The trimmed plan is internally coherent | P04, P05, P07, P10, P14 to P17 `done_when` | the rewordings agree with the removals |
| A hook reply is never a person's answer | P01's host probe against S06 lines 721-738 | the design was right, and `c11.py` states it |
| The local access barrier and generation | S07 lines 1049-1051 against `c02.py` | agree, including the signing-key arrangement the spike settled |
| Independent review excludes requester and authors | S07 lines 1099-1102 against `c08.py` | agree |
| Three copies is a target, not a quorum | S08 lines 1191-1194 against `c10.py` | agree |

## No guard gap survived verification

One was reported: SSOT line 742, that compaction and child use restore the necessary
context and checks, whose case (`DH-REACH`) the trim removed. It does not survive, because
the three things that sentence protects are each still guarded:

- Offering material already in hand as an admitted use — `N08-INSPECT-NEG`: an inspection's
  result resumed as a use no admission created is refused `use_not_admitted`, nothing is
  written.
- Asking again for a new use — `DC-ASK`.
- The bodies after a compaction or in a child session — `N15-C11-POS`: a child session
  receives its own use, and a conversation rehydrated after compaction receives the body
  again, whole.

What is left is the model reasoning silently over text in its own context, which the same
SSOT paragraph calls a coverage limit because it cannot be observed. No case can close it
and the design says so.

Two other suspected gaps were also ruled out against kept cases: `N19-C08-NEG`'s deferral
(covered by `CAP-11`, `N19-BOOTSTRAP-NEG`, `N16-C12-NEG`) and `N03-PROVIDER-OUTAGE-POS`'s
(covered by `N03-C02-POS` and `N18-C01-NEG`).

## What has to change, and where

Everything below is documentary except the first row, which was fixed in this change.

| Where | What it says | Class |
| --- | --- | --- |
| `CURRENT.md` (fixed here) | first-exposure comprehension remains required evidence | CONTRADICTION in a live file |
| SSOT 216 | the extension-of-supplied-knowledge route | TEXT-STALE |
| SSOT 268-278 | a restricted correction resolvable by a qualified-state proof | TEXT-STALE |
| SSOT 709-711 | prefer a native form elicitation | TEXT-STALE |
| SSOT 740-744 | compaction and child use restore the checks | TEXT-STALE |
| SSOT 1074-1097 | grants are held by people **and groups** | TEXT-STALE |
| SSOT 1370 | Team copy/derive | TEXT-STALE |
| SSOT 1431 | evidence recovery after closure | TEXT-STALE |
| development spec 321 | P10 prefers native form elicitation | TEXT-STALE |
| development spec 515, 550, 573, 654 | the retired comprehension family as required evidence | TEXT-STALE |

Each names a feature the 2026-09-22 trim removed, and in each the guard left with the
feature. The clearest case is groups: no schema and no contract module carries a
person-group concept, `c08_grant_record`'s holder is a principal and nothing else, so the
repair the SSOT calls G01 — an unauthorized self-add creating group powers — has no path to
occur.

**S13's exclusion table is stale in both directions.** None of the ten removals is in it,
and the row deferring the final proof wire format and cryptographic suite has since been
decided: B01 freezes detached SSHSIG through the operating system's `ssh-keygen`, on spike
evidence across OpenSSH 8.2p1 to 10.3p1.

**S14 states how this is repaired**: a dated successor of the complete SSOT, with the
CURRENT.md pointer moved to it, and no competing rules kept in a supplement. So the cheap
fix is the one the design forbids. The owner chose to fix the harmful row now and to issue
the successor once, when P01 is recorded, rather than issue it twice around U18 and U12.

## What was done here

1. `CURRENT.md` no longer states a retired family as current evidence.
2. The ten removals now carry the condition that would bring each back
   (`D-20260923-3fad2c`), which S13 requires of the ledger and which neither trim record
   had.
3. C01's source request drops the `extend_supplied` route (`D-20260923-40b9f0`): of the
   four routes it carried, three are sent by 16, 3 and 2 scenarios and that one by none.
   Removing it opens no hole — `c01_source_home`'s `published_home` states it has no field
   for a local edit of publisher-owned bytes — and what is given up is recording which
   supplied base revision an addition extends. A knowledge-role import example replaces the
   one the removal took, which also gives the import route its first accepted example.
4. Two instruments, so neither class is re-found by reading (`D-20260923-804f9b`): the
   entry point's family identifiers are now gated, and contract-branch coverage discloses.

## What is still open

The successor SSOT and development spec, the S13 exclusion rows, and whatever S10 to S14's
read adds to the list above.
