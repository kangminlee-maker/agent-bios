---
created_at: 2026-11-06T05:45:00+09:00
head: 0d12dd5
kind: design
supersedes: null
---

# S4's answer names what its packet labels, and a type G candidate states its tension or is refused

WP-09, commit 1: the formation contract. It adds the schema, the packet template, and the stage's check of one answer
(`session-distill/runlib/stage_form.py`). It has no CLI, no partition and no intake yet; those are commits 2 to 5 of the
plan in `work/impl/wp09/stage0.md`.

## What one formation answer is

`schemas/form.schema.json` has three lists, one for each partition class of design §9:
- `candidates`;
- `rejected_findings`;
- `non_findings`.

**A candidate** carries:
- `lesson`: consolidate.js's one-line cluster name, kept as the plan's Files line asks;
- `type` A-G;
- `situation`, `action`, `exception`;
- `admission`: the eight requirements of D-20261020-71699d, each by its own name and each required;
- `event_ids`;
- `tension`.

Each admission requirement is `{basis, claim_ids, evidence_ids}`: what the events show for it. Its lists may be empty,
because `positioned` and `audience` rest on reasoning. S4 states the basis; the judges mark the requirement met or unmet
(design §6.4).

**A rejected finding** carries:
- `finding` and `event_ids`;
- `failed`: the requirements it fails. At least one is required, and only the eight names are allowed;
- `reason`.

**A non-finding** names one event and one reason from §9's fixed list (`no_consequence`, `routine_step`,
`duplicate_of_another_event`). A duplicate names the event it repeats in `duplicate_of`.

The partition is checked in commit 2, by code. Every event must be in exactly one place, and the code names what
breaks this (SET_MISMATCH).

## Labels

The packet names everything it shows by labels of its own:
- events v1, sessions s1, claims c1, quotes q1 and placed clusters u1;
- the answer names its own candidates k1 and rejected findings r1.

This is the same rule as S3's packets since WP-08b. A label the packet does not show is UNKNOWN_LABEL twice: in the
stage's check, and again where an accepted answer is turned into stored ids (`FormLabels.resolve`). So no label can
reach a store.

An event row lists two kinds of claims apart:
- `claims`: the claims that describe the event;
- `outcome_claims`: the claims that show its outcome. These are the stitch's claims for an event whose outcome a later
  window showed.

A carried event that this run resolved has no claim of this run that describes it, so its `claims` list is empty.

Sessions are labelled so that the model can see when events from different sessions support one lesson. Session ids
never reach the packet.

## What code refuses beside the schema

- **G_ANTI_ABSTRACTION** (design §7.4) is refused by name for each missing part of a type G candidate:
  - two distinct sides;
  - an ordering;
  - what the preference forbids;
  - at least three distinct shown claims as instances.

  An instance the packet does not show is UNKNOWN_LABEL and counts for nothing.
- **TENSION_OUTSIDE_G**: a tension filled on any other type.
- **NON_FINDING_DUPLICATE**: a duplicate that names no event or names itself, or `duplicate_of` filled under another
  reason.
- **RECORD_INTEGRITY**: a candidate or finding id that repeats.

The schema leaves the tension's parts free (empty strings and lists are valid), so that a missing part is refused by
the stage's check under design §7.4's name, not as a schema violation.

### Why empty strings and not null

`tension` is required on every candidate. On a type other than G, its lists are empty and its texts are "".
`duplicate_of` is "" for the two other reasons.

The schemas handed to a host so far (read and stitch) hold no type array, so no live call has shown that a host's
structured output takes `["object", "null"]`. This contract avoids depending on one.

## Closed lists

`stage_form.py` copies each closed list of the contract from the section that owns it, with the line numbers. The
self-test holds both the code and the schema to these copies (plan WP-09 done-when 7):

| List | Owning text | Lines |
|---|---|---|
| partition classes and non-finding reasons | design §9 | 921-924 |
| intake sources | design §7.1, as the plan's Artifacts names them | — |
| the eight admission names | purpose record 2026-10-20T1133 | 47-66 |
| types A-G | PLACEMENT-FRAMEWORK.md | 32-45 |

The intake sources have no schema yet. Commit 4's intake schema is held to the same constant.

## The packet

`packets/form.md` takes three fields:
- `events`;
- `claims`, each with its quotes;
- `clusters`: placed learnings sharing a principle, filled by commit 4's intake. It is "none" until then.

The packet carries:
- the seven types;
- the eight requirements, in the purpose record's words, shortened;
- one place for every event;
- the rule that quotes are data, not instructions.

It sends no lifecycle candidate. Code forms those candidates (lead decision D7 of stage 0).

`packet.TEMPLATES` now lists `form`, so the packet linter's template checks cover it. The check that a template's fixed
part leaves room in `bound.PACKET_OVERHEAD` applies only to S3's two templates (`WINDOW_TEMPLATES`):
- That overhead is what S3's view windows were cut to leave free.
- The form packet's fixed part is 17,827 bytes with its schema. It is not cut against windows.
- Commit 5 bounds the S4 packet by its own stage (`FORM_OVER_BOUND`).

## Controls

`stage_form.py --self-test` holds 37 controls. It runs in the umbrella after S3's suite.

The pretrial (`work/impl/wp09/logs/pt9-1.log`) ran 22 rows:
- 2 none rows: both PASS.
- 20 rows that each revert one check: every one CAUGHT by name, with traceback False.

## Open

- **An upward-distillation G candidate.** A G candidate drawn from a placed cluster alone has no claims of the window,
  so it cannot meet "at least three claim ids as instances". Whether a cluster's placed learnings may count as instances
  is a question for commit 4's intake rule (X review).
