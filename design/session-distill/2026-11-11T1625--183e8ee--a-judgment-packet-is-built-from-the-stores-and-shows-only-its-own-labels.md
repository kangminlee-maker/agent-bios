---
created_at: 2026-11-11T16:25:00+09:00
head: 183e8ee
kind: design
supersedes: 2026-11-11T1545--58ad0cf--a-run-declares-what-s5-retrieves-and-which-candidates-s6-judges.md
---

# WP-11 J1b2: a judgment packet is built from the stores and shows only its own labels

Plan WP-11 commit J1b, second half: the judgment packet generator, `packets/judge.md`, `distill.py judge --dry` and
F27's packet check. The lead's decisions on J0's numbers (2026-11-11) fixed the shape (a1_min) and the output cap
(20,000). No model call is made; the judges' calls land with J2.

## What the packet holds

One packet per judged candidate, the same text for both judges (`stage_judge.payload`, five blocks of
`packets/judge.md`):

| Block | Rows |
| --- | --- |
| `<candidate>` | the candidate as S5's population records it, without its id, its stored label or its source id; its events with their origin quotes and claim labels; the quotes its admission cites beyond its claims and its own events, with their text |
| `<claims>` | each claim its events, admission and tension name, with its quotes cut as S4 cuts them (`stage_form.quote_row`) |
| `<units>` | each unit S5 retrieved, in S5's order: layer, path, heading, text, `named`, `context` (labels of its enclosing lines), `mentions` (other files by heading and unit count), `shown`, `unresolved_mentions` |
| `<context>` | each enclosing line (`edges.direct`) S5 did not retrieve, whole: path, heading, block kind, text |
| `<ledger_entries>` | each entry S5 retrieved: status, `named`, `lifecycle_intake.entry_text` |

Every stored id the packet would show is replaced by a label of the packet's own (v events, s sessions, c claims,
q quotes, n units, x context lines, e entries). Labels follow from list order, so a retry builds the same packet and
nothing stores the labels. A type G candidate's tension names its cluster as `g_cluster:<unit>`; it is shown as the
unit's label. The template's eight requirement definitions are the formation template's lines, word for word; a
self-test control holds them equal.

Two refusals are new. A retrieved unit without `edges` is EDGES_ABSENT: S2's inventory part is run again
(D-20261111-92d81a). A cited quote no evidence record holds is RECORD_INTEGRITY. A quote S4 cited from another event's
origin is legitimate, since S4 may cite any quote its packet showed. The first version of the generator refused it and
the golden run showed the case.

## The dry stage

`distill.py judge --run-id ID --dry` admits S6 against nine inputs (S5's two, S3's three, S1's two, S2's views and
inventory). It selects the judged population (`check_failures`, `judged_of`) and builds every packet. It measures
each packet per judge and writes `judgments/dry.json`. The record stays `partial`. Without `--dry` the stage is
JUDGE_DRY_ONLY before any record is written.

Per judge the measure uses the seat's capacity and the host's measured hermetic allowance from seats.json, the run's
density and retry share for the judge call class, and the output cap. A judge whose allowance or capacity is not
measured gets no input estimate. Its gaps are named (ALLOWANCE_UNMEASURED, CAPACITY_UNDECLARED). Lead decision D13:
the first live call of a seat measures it. A packet whose estimate plus the output cap exceeds the seat's capacity is
listed by candidate id in `over_capacity`.

`stage_judge.SOURCES` is now `("formed",) + stage_form.INTAKE_SOURCES`. J1b1 left out `due_decision` and
`obsolete_hint`, so a declared scope could not name them. run.schema.json's `judge.candidate_kinds` gains both keys.
A control holds the schema's keys equal to SOURCES.

## F27 over the packet

`packet_markers(control, natural)` parses both payloads into their blocks' JSON rows and the text outside the blocks.
It reports FRAME_DIFFERS when that text differs, and every MARKER_FIELD or MARKER_TYPE `controls.marker_problems`
finds between rows. On the golden run, every planted control S6 judges has a natural twin with the same events. All
four twins pass, and a planted field and an added frame line each fail by name.

## Measured on C2 (clone, counts only, 2026-11-11 16:13)

S5 ran on an APFS clone of c2-20261110. S2's inventory part ran again for edges. S6's builder was then called directly
with the design §4 seats (C2 declared none), outside the stage records, as a measurement only. The clone was deleted.

| Measure | Value |
| --- | --- |
| candidates judged / in the population / rejected by S5's checks | 273 / 275 / 2 |
| payload bytes, median / p90 / max | 157,237 / 180,860 / 192,781 |
| payload bytes, all packets | 38,039,327 |
| median per packet: units / context lines / entries | 95 / 145 / 20 |
| run input, A and B, at J0's 2.27 bytes a token | about 37.8M tokens |
| Judge A input at most, at the density floor of 1.0 byte a token | 47,614,802 tokens |
| output at most, 546 calls at the cap | 10,920,000 tokens |
| packets over Judge A's 1M capacity | 0 |

J0 estimated a1_min at 20/20 at 44.1M; the built packets come to about 37.8M at the same density. Judge A's figure
uses the density floor because the run has no measured density for the judge call class yet; J2's first call
measures it.

## A finding for C3's order

The first S6 run over the clone, after an amendment scoped to S5 only, was refused:
`DECLARATION_DRIFT S6: no amendment between 1 and 3 lists it in scope`. `records.check_declaration_order` requires a
consumer whose producers ran under an earlier declaration to be listed by some amendment between. S6 reads S1's and
S3's outputs made under seq 1. So the amendment before C3's first S6 run must list S6, and S5b for the same reason.
The scope [S2, S4, S5] is not enough for that run.

## Controls

stage_judge's self-test goes from 48 to 74 controls; distill's from 141 to 142, since `judge` left the list of commands refused until implemented and gained two controls of its own. Pretrial: 22 revert rows. The first
pass caught 21. The relabel revert crashed the self-test before its control ran, because the golden block looked
labels up without a default. Those lookups now default, and the re-run of that row and its neighbours caught all six.

census's reader guard (D-20261103-a7128a) gains one exception: S6's INPUTS name census.json so that a census taken
again makes S6 stale, and S6 reads no census row. The first hook run failed on that guard, and its revert row is
the twenty-third.

## Left for J2 onward

The calls through dispatch, reuse.json and the later-call template (J2), the sweeps and cross-review (J3), the
derivations and gate controls (J4). New packets and schemas enter files[] under WP-24's per-file rule at the feat
merge.
