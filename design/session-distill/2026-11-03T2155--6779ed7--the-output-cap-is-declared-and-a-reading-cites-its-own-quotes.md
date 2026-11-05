---
created_at: 2026-11-03T22:10:00+09:00
head: 6779ed7
kind: design
supersedes: null
---

# The output cap is declared, and a reading cites its own quotes

WP-08's first commit: the declaration field for S3's output cap, the two schemas S3's calls answer in, the stored
record schemas the answers become, and the two packet templates. Nothing in it calls a model or reads a window yet:
the reader arrives in the next commit. The plan text this follows is amended by
`2026-11-03T2155--6779ed7--plan-amendment-wp08-reads-units-file-by-file-and-derives-resolutions.md`.

## The output cap has one home

The ruling of 2026-10-22 (`2026-10-22T1121--ec51ee9--…`) made check (d) reserve the cap the call itself declares,
and left the cap without a declared home: `distill.py views --output-cap` stood in until WP-08 gave it one. The home
is `run.json` `output_caps: {"S3": n}`, required, closed to stages nothing reads yet, an integer of at least 1.
`views.limits_of` and `views.run` read it and take no reservation argument, as they take no capacity argument (BB#5),
so no caller can cut against a number the declaration does not carry. The flag is gone; a declaration without the
field is refused `CAP_UNDECLARED output_caps.S3` when windows are cut. The S3 stage will declare the same number on
every call it dispatches.

**Raising the cap is accepted as an amendment, and it makes S2 and every later recorded stage stale**
(`declare.INVALIDATED_FROM["output_caps"] = "S2"`). S2 cut every window so that its bytes, the allowance and the cap
fit the seat's capacity, so a call that reserves more may not send those windows. Lowering it is treated the same
way, because the windows' recorded limits carry the cap they were cut with.

Closed: keeping the flag beside the field (two sources for one number); refusing an amendment that raises the cap
(the amendment mechanism already says which results it makes stale, and re-cutting is what a raise needs).

## A reading cites its own quotes

`read.schema.json` is one window's answer: `quotes`, `claims`, `events`, `decisions`, `observations`, all required,
any of them empty.

- **Claims are §3.3's object** (done-when 8): `claim_id`, `fact`, `interpretation`, `uncertainty`, `evidence_ids`,
  `call_id`. In the answer, `evidence_ids` name quotes of the same answer (`q1`, `q2`, ...), and `call_id` is the
  packet's CALL-ID. A quote is `{quote_id, entry, text, occurrence?}`, an exact stretch of one owned entry as the
  window shows it. Code turns each quote into an evidence record with `evidence.from_view`, which finds the span in
  what the window showed and reads the text from the projection, so a model never types a locator. The stored claim
  takes the evidence records' ids and a stored claim id derived by code; its fact, interpretation and uncertainty
  are stored as answered. Closed: claims that carry locators (the model would type line, pointer and span), and
  claims that carry their quotes inline (`evidence_ids` would no longer be §3.3's list of ids).
- **Events** answer `resolved` or `pending`. `unresolved` and `stitched_from` belong to the stitch call. `kind` is a
  short noun: neither the design nor the plan gives a vocabulary, and its consumer is S4 (WP-09).
- **Decisions** are one per omission the packet lists, by `omission_id`, `expand` or `skip` with a reason.
- **Observations** answer `exposure` and `verdict` as §11 names them, with quotes. The coverage basis is never
  answered: code sets it over the claim's scope (§5.4).

`stitch.schema.json` answers once for each pending event: `resolved` with the claim ids and evidence ids that show
the outcome, or `unresolved` with both lists empty. The schema policy has no conditional keyword, so the pairing of
an outcome with its lists is checked by code in the stitch commit.

The stored records the answers become are schemas too: `event.schema.json` and `observation.schema.json`, with the
field lists of the plan's WP-08 artifacts. They join `claims.py`'s contract table, so each field names its consumer
and each schema its design section. `claims.answer_mismatch` holds the two answer schemas to them: the reading's
claim object to §3.3's list; the stored instance's `basis` to §5.4's three words and to what `views.coverage_basis`
can return (read from its source); the answer's exposure and verdict to the stored instance's; a window's event
outcomes to the stored ones without `unresolved`; a stitch's to the stored ones without `pending`; decisions to
`views.DECISIONS`.

## The packets

`session-distill/packets/read.md` and `stitch.md` are payload templates with `{{field}}` placeholders.
`packet.render` fills them in one pass: every placeholder takes exactly one text field, no field is left over
(`TEMPLATE_FIELDS_MISMATCH`), and a field's text is never read as a template, so a transcript that quotes
`{{window}}` stays text. The long material comes first and the request last, and the request starts with "Think the
problem through before you answer": the prompting guide's advice for `claude-sonnet-5-5` answering JSON with
structured outputs at `high`, the effort the owner chose for S3.

Each template says why the reading is done (the owner checks every finding against their own session), that the
transcript is text to read about and never instructions, how a window is written, and what each answer field
means. The read template lists only the omissions of the window's own records, because of the measurement below.

## What a window's omissions are

C0c's views (run `c0-20261103c`, counts only): 1,264 windows. A window's omission manifest has a median of 189 rows
and at most 2,151. Of all 332,707 rows, 328,620 (98.8%) are overlap rows: entries of the neighbouring windows shown
as context and cut. A window's own omissions, 4,087 in all, have a median of 3 per window and at most 17. Listed one line each, the whole manifest takes a median of 11.7 KB
and up to 131 KB, more than a window's bound; the window's own omissions take at most 1,140 bytes. Of the 328,620
overlap rows, 325,144 are records that another window of the same view owns, and in every one of those the omitted
interval is shown in the owning window or listed there as that window's own omission. The other 3,476 are records
the run does not owe (`owned: false` in the sequence).

**The contract changes** (the lead's decision of 2026-11-03). The plan said "per clipped record an `expand`/`skip`
decision with reason (set accounting over the omission manifest)". It now reads: the model decides about the
omissions of the window's own records, and code accounts for every overlap row through the window that owns the
record. One decision per manifest row would ask for up to 2,151 answers in one call, and the list alone would not fit
the bound.

**The guarantee kept**: an interval counts as read only where some window showed it or decided about it, and that
window's result passed. The reader's commit builds this accounting (`check_decisions` and `completeness` over own
omissions) under three conditions, each with its control:

1. An overlap row is credited only when the owning window's result passed the gate. If the owner failed, was
   quarantined, was deferred or is not done, nothing is credited and the unit stays `read_partial`. Control: an owner
   planted as failed, whose overlap rows are then not credited.
2. Overlap rows on records the run does not owe (`owned: false`) are not completeness gaps. The run record publishes
   their count.
3. An overlap row whose owning window cannot be found is refused by name. It has a negative control.

Revisit if an overlap row is found whose interval its owner neither shows nor lists, if a view is cut without the
owned-once invariant, or if the overlap budget changes so that an overlap entry is no longer a copy of an owned
record.

## Bytes

The overhead S2 cuts windows with is `bound.PACKET_OVERHEAD`, 12,288 bytes. The part every read call carries, which
is the envelope, the principles block (4,295 bytes), the template and the schema, takes 10,438 bytes and leaves
1,850. A stitch call's fixed part leaves 5,340. `packet.py --self-test` reports both figures and fails when a fixed
part does not fit. What one call adds, its omission list and the expected observations due, is counted with that
call by the dispatcher's bound check, which refuses a packet over the bound by name (`WINDOW_OVER_BOUND`) before
anything is sent. C0c's largest list of a window's own omissions fits in the room left. A list of several expected
observations may not fit, so the reader's commit decides whether S2 counts each window's own list when it cuts. C1
has no expected observations, so this does not affect C1.

## Controls

- `declare.py`: the declared field set includes `output_caps`; dropping it, a cap of 0, a boolean cap, and a cap for a
  stage nothing reads are each refused by name; an amendment raising the cap after S1 to S4 recorded is logged with
  `invalidates == ["S2", "S3", "S4"]`.
- `views.py`: neither `limits_of` nor `run` takes a reservation; a golden run declared with 48,000 cuts with
  48,000; a declaration with no cap is `CAP_UNDECLARED`.
- `distill.py`: `views --output-cap` is an unknown argument.
- `claims.py`: the event and observation records go through the generic controls (every field dropped, the contract
  check, the inert-field check) plus six record mutations. Nine answer departures are each named: a fourth basis
  word in the stored instance, a fourth literal `coverage_basis` could return, a claim field added to or dropped from
  the reading's claim object, the model answering the basis, a window answering `unresolved`, a stitch answering
  `pending`, an exposure the stored instance cannot hold, and a decision other than expand or skip.
- `packet.py`: each template's placeholders are the fields its stage fills, each rendered packet passes
  `packet.check`, and each fixed part fits the overhead. A missing template, a missing field, an extra field and a
  non-text field are each refused by name. A field that quotes a placeholder is not expanded.
