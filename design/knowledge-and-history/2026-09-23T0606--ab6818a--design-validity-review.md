---
created_at: 2026-09-23T06:06:01+09:00
head: ab6818a
kind: review
supersedes: 2026-09-23T0550--18b0b9b--design-validity-review.md
---

# Is the design still valid? — the complete review

The 05:50 record was written while the last of four section reads was still running and
said so. This one carries all four. It supersedes it; nothing in it was withdrawn.

The design SSOT is dated 2026-09-15. The plan and catalog were trimmed on 2026-09-22,
removing ten features, and P01 has since frozen twelve contracts. The question is whether
the design still describes what is being built.

**The plan is coherent. The documents describing it are stale. Nothing is unguarded.**

## Method, and why the classification matters more than the count

Four blind reads of the SSOT against the plan, the catalog, `gates/workenv/case-index.json`
and the frozen contracts, one per section group, each asked to check a kept case before
calling anything a gap. Every finding was re-derived here before being accepted, and three
of the four gap claims did not survive that.

Classes: **TEXT-STALE** (the feature and its guard went together, so the fix is
documentary), **GUARD-GAP** (the situation still occurs and nothing guards it),
**CONTRADICTION**, **CONFIRMED**.

The line between the first two is the whole review. A reader who searches the kept cases
for the words a clause uses will find nothing and call it a gap. The question that decides
it is not whether a case mentions the subject but **whether the path still exists**. Both
surviving gap claims failed on exactly that.

## No guard gap survived

**Claimed: SSOT line 742 — compaction and child use restore the necessary checks**, whose
case `DH-REACH` the trim removed. The three things that sentence protects are each guarded:
`N08-INSPECT-NEG` refuses material offered as a use no admission created (`use_not_admitted`,
nothing written); `DC-ASK` asks on each new use; `N15-C11-POS` delivers to a child session
under its own use and to a conversation rehydrated after compaction whole. What remains is
the model reasoning silently over text in its own context, which the same paragraph calls a
coverage limit because it cannot be observed.

**Claimed: SSOT line 1823 — forged, stale, wrong-scope or wrong-audience proof must fail
without reviving an old decision** (the repair S12 calls G03). No operation takes or
returns a proof, and `state_proof` and `memory.state.prove` have no occurrence in the
contracts, so there is nothing to forge. The surviving `proof_digests` field is a different
thing — C03's access handles, whose misuse `N03-ENTRANCES-NEG` refuses. And removing the
proof route made the system stricter rather than looser: without event closure a restricted
correction can no longer be resolved at all, which `N07-C05-NEG` tests ("leave the affected
entries unresolved with their gap; no ranking selects a winner") and `N07-STATE-GAP-NEG`
completes ("an entry a gap names is never current") — that last one is the
no-revival guarantee the clause asks for, under another name. Where evidence of control
really is carried, the adversarial half is tested too: `N13-C09-NEG` stops an import on
truncation, a missing baseline, altered bytes, **the wrong audience**, a traversal or
executable member, or a superseded control, each at the stage its record names.

**Claimed: `N19-C08-NEG`'s and `N03-PROVIDER-OUTAGE-POS`'s deferrals.** Covered by `CAP-11`,
`N19-BOOTSTRAP-NEG`, `N16-C12-NEG`, and by `N03-C02-POS` with `N18-C01-NEG`.

## What holds

| Claim | Checked by | Result |
| --- | --- | --- |
| The design's own criterion is current | the SSOT's quoted purpose against `AGENTS.md` | byte-identical, 873 characters |
| The plan bundle is sound | `gates/check-development-plan.py` | valid; 28 positive and 412 negative controls |
| The trimmed plan is internally coherent | P04, P05, P07, P10, P14 to P17 `done_when` | the rewordings agree with the removals |
| A hook reply is never a person's answer | S06 lines 721-738 against `c11_answer_evidence` | `hook_generated` carries no choice and needs no separation evidence, so it cannot qualify; `N04-ROUTER-NEG` blocks it as `answer_not_from_a_person` |
| Operation continues with hooks absent | S12 line 1819 | `N04-ROUTER-POS` |
| The local access barrier and generation | S07 lines 1049-1051 against `c02.py` | agree |
| Independent review excludes requester and authors | S07 lines 1099-1102 against `c08.py` | agree |
| Three copies is a target, not a quorum | S08 lines 1191-1194 against `c10.py` | agree |
| Causal relations, fork and clone identity, peer recovery | S04 against `c05` schemas, `SRC-10`, `SRC-11`, `N14-C10-POS` | agree |

**A revisit condition fired and was honoured.** S13 line 1872 defers the proof wire format
and cryptographic suite until interoperable proof import is implemented, and says
verification is mandatory. B01 freezes detached SSHSIG through the operating system's
`ssh-keygen` with `algorithm` pinned, carrying `observed_on` across five OpenSSH versions,
two operating systems and two architectures, and explicit `limits` — built alongside
`N13-C09`, the package-import case the condition names. The decision was taken where the
condition says it should be. The S13 row's own wording is what is stale.

## What has to change, and where

Everything below is documentary. The first two rows were live files stating something
untrue and were fixed; the rest waits for the successor SSOT.

| Where | What it says | Class |
| --- | --- | --- |
| `CURRENT.md` (fixed) | first-exposure comprehension remains required evidence | CONTRADICTION in a live file |
| `c08_team_state` description (fixed) | evidence recovery does not revive a closed Team — an operation C08 no longer has | CONTRADICTION in a frozen contract |
| SSOT 216 | the extension-of-supplied-knowledge route | TEXT-STALE |
| SSOT 268-278 | a restricted correction resolvable by a qualified-state proof | TEXT-STALE |
| SSOT 709-711 | prefer a native form elicitation | TEXT-STALE |
| SSOT 740-744 | compaction and child use restore the checks | TEXT-STALE |
| SSOT 1074-1097 | grants are held by people **and groups** | TEXT-STALE |
| SSOT 1370 | Team copy/derive | TEXT-STALE |
| SSOT 1431 | evidence recovery after closure | TEXT-STALE |
| SSOT 1766 | group expansion cannot pass via a role label | vacuous, not wrong |
| SSOT 1776 | dashboard counts are not complete inventory | vacuous, not wrong |
| SSOT 1814 | supplied and **added** knowledge share the contract | TEXT-STALE in part |
| SSOT 1819, 1821, 1823, 1825, 1832 | acceptance rows naming removed features | TEXT-STALE |
| SSOT 1906 | the retired comprehension family as pending evidence | TEXT-STALE, and it reads as open rather than gone |
| development spec 321, 515, 550, 573, 654 | the native form route and that same family | TEXT-STALE |

Two of these are worth separating from the rest. A clause that **prohibits** something the
product no longer has — group expansion through a role label, a dashboard count mistaken
for an inventory — is not wrong, it is empty. When the successor is written, those lines are
deleted rather than corrected, and the distinction decides which.

**S13's exclusion table is stale in both directions.** None of the ten removals is in it,
and the proof-wire-format row above has been decided.

## The process finding, which is the one to read first

S14 states the maintenance rule, and `CURRENT.md` restates it: "produce a dated successor of
this complete SSOT, update the single CURRENT.md pointer, and record material
decisions/exclusions… Do not maintain competing latest rules in supplements."

The scope trim did the second half and not the first. The decisions and the trim record
exist; no successor SSOT does, and the pointer still names the 2026-09-15 document. The
sharper half of the finding is that `CURRENT.md`'s own prose about what the trim removed is
functioning as the supplement the rule forbids — **and the correction made today enlarges
it**, because stopping the file from asserting a retired requirement meant saying in that
file that it is retired. The alternative was to leave a false requirement standing.

So this is a knowingly held debt, not an oversight: the entry point carries a temporary
correction until the successor absorbs it. Whoever opens that work reads this section first.

## What was done

1. `CURRENT.md` no longer states a retired family as current evidence.
2. `c08_team_state`'s description no longer names an operation C08 does not have; it now
   states what `N19-BOOTSTRAP-NEG` actually tests.
3. The ten removals carry the condition that would bring each back (`D-20260923-3fad2c`),
   which S13 requires of the ledger and which neither trim record had.
4. C01's source request drops the `extend_supplied` route (`D-20260923-40b9f0`): three of
   its four routes are sent by 16, 3 and 2 scenarios and that one by none. Removing it opens
   no hole — `c01_source_home`'s `published_home` states it has no field for a local edit of
   publisher-owned bytes — and what is given up is recording which supplied base revision an
   addition extends. A knowledge-role import example replaces the one the removal took,
   which also gives the import route its first accepted example.
5. Two instruments, so neither class is found by reading again (`D-20260923-804f9b`): the
   entry point's family identifiers are gated, and contract-branch coverage discloses.

## What is still open

The successor SSOT and development spec, and the S13 exclusion rows they carry.
