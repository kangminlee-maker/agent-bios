---
created_at: 2026-11-06T05:58:00+09:00
head: 01eaddf
kind: design
supersedes: null
---

# A decision names the incubate it resolves

WP-09, commit 3, lead decision D3 of WP-09 stage 0. It adds the field `resolves` to the schema 2 decision element, and
this record is that field's contract. `ledger.FIELD_RECORDS` names this record, and `ledger.field_record_problems` fails
by name if the record is missing or does not name the field.

## The gap

Design §7.1 says: "A later decision on the same learning or intervention names the incubate decision it resolves
(`resolves: <decision id>`), so the pending item leaves the intake only when resolved or expired-and-dropped."

WP-13's schema 2 had no such field. Ordering alone, through `standing_decision`, cannot say which of two pending
interventions on one placed entry a later decision settles. The plan's `candidates.json` already carries
`lifecycle.resolves`.

## The contract of `resolves`

- **Where.** An optional property of a decisions[] element: `"resolves": "<entry id>@<run>"`. The id is the one S3
  already uses for an expected observation (`stage_read.due_observations`).
- **Writer.** The decision that settles a pending incubate. That is S10 parsing and S11 application (WP-20, WP-21),
  writing what a lifecycle candidate's `lifecycle.resolves` named.
- **Reader.** `ledger.unresolved_incubates(ledger)`. It lists every incubate a run decided that no later decision of its
  entry resolves, with its expiry and its entry's status. WP-09's lifecycle intake (commit 4) takes from it the
  decisions due by the window's end. An incubate on a placed entry is a pending intervention (design §12.3): its status
  does not move, and it is listed like an incubating entry's.
- **Rules.** `ledger.resolves_problems` holds these, and `validate_ledger` runs it. Each rule fails by name:

| Code | What it refuses |
|---|---|
| RESOLVES_OTHER_ENTRY | a decision resolves an incubate of another entry; a decision resolves only an incubate of its own entry |
| RESOLVES_DANGLING | the named run made no decision on this entry |
| RESOLVES_NOT_EARLIER | the named decision is not earlier in decisions[] |
| RESOLVES_NOT_INCUBATE | the named decision is not an incubate |
| RESOLVES_TWICE | one incubate is resolved twice |
| RESOLVES_ON_LEGACY | a migrated element carries the field; the migration resolved nothing |

  The schema's pattern refuses a value that is not of the form `<entry id>@<run>`.
- **Migration.** None. The owner's ledger is schema 1 until WP-22's cutover, and the migration writes no `resolves`,
  because a migrated element is no run's decision.

## A field after ADDENDUM

`ADDENDUM` (2026-10-21T0820) contracts what schema 2 carried beyond design §12.1 when WP-13 landed.
`addendum_problems` fails when ADDENDUM does not name every optional property.

A dated record is written once, so `resolves` is not added to ADDENDUM's text. Instead:
- `FIELD_RECORDS` maps each later property to the record that contracts it;
- `addendum_problems` no longer asks ADDENDUM for those properties;
- `field_record_problems` asks each one's own record. It fails with:
  - FIELD_RECORD_MISSING when the record is not there;
  - FIELD_RECORD_SILENT when the record does not name the property;
  - FIELD_RECORD_STALE when the property is no optional property of a decision.

## Limits

- **Within one entry only.** A merge that would settle another entry's incubate is outside this field. It is refused
  (RESOLVES_OTHER_ENTRY), not modelled.
- **Expiry.** An incubate whose expiry passed stays unresolved until a decision resolves it, normally a drop. This is
  design §7.1's "expired-and-dropped". Nothing here ends it by date.

## Controls

These were added to `ledger.py --self-test`:
- **Positive cases:**
  - a drop that resolves an earlier incubate;
  - a pending intervention on a placed entry, listed by `unresolved_incubates` as `P-1@r1`;
  - an incubate that a later decision resolves is not listed;
  - an incubate that nothing resolves is listed.
- **One case for each refusal** above, each failing by its own name.
- **The contract check:** the record of `resolves` is present and names it; a record that names nothing, a missing
  record and a stale property each fail by name; ADDENDUM is not asked for `resolves`.
