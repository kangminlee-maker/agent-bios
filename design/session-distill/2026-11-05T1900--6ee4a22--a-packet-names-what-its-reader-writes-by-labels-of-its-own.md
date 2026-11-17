---
created_at: 2026-11-05T19:00:00+09:00
head: 6ee4a22
kind: design
supersedes: null
---

# A packet names what its reader writes by labels of its own

WP-08b, commit 1. This record amends the mechanism design's §5.4
(`2026-10-20T1942--9684f05--mechanism-design.md`) and gives WP-08b's scope and done-when. WP-08b is a short package
placed before WP-09.

The decisions behind it:
- D-20261105-04f55b put the labels next.
- D-20261105-40184d placed DW5's follow-up half after them.
- D-20261105-7dbc98 settled the design and the live budget.

## Why

The live readers copied values from their packets, and code then refused the near copies of those values:
- apart-live1 wrote an entry without its last part: `7/message/content/0` for `7/message/content/0/text`.
- dw2-live2 wrote its call id with the label in front: `CALL-ID: <id>`.

Since WP-08 commit 7, every entry has stood alone on its own `entry: ` line. C1 still near-copied:
- one window call of the ten made since then;
- six of 82 quotes;
- six of the 22 quotes on tool-result entries.

The refused answer cost a retry, and the retry ran out of budget (0708d). The trouble was the copying task itself, not
the reader's care.

## §5.4, amended

After "Code supplies each expansion as additional windows under the same token bound and span mapping.":

> A packet names each value its answer writes by a label of its own: every entry its window shows, every omission it
> lists and every expected observation due (e1, o1, x1, ...), and, in a stitch packet, every event, claim and quote
> (v1, c1, q1, ...). Code turns the labels of an accepted answer back into what they label where it reads the answer;
> the stores hold entries and stored ids, never labels.

§3.3 does not change. The claim object, `call_id` included, is the same, so done-when 8 of WP-08 holds. §5.5 does not
change either: a quote is still located by its entry, its text and its occurrence.

## What a label is

**Read packets** (windows and expansion windows):
- `e1`, `e2`, ...: every entry the window shows, in the order it renders them. That order is the overlap before, then
  the records the window owns, then the overlap after (`views.entry_labels`).
- `o1`, `o2`, ...: the omissions the packet lists, in their order.
- `x1`, `x2`, ...: the expected observations due, in id order.

**Stitch packets:**
- `v1`, ...: the events, in the order the packet lists them.
- `c1`, ...: the claims, in theirs.
- `q1`, ...: their quotes, in the order they first appear. A quote that two claims cite has one label.

**Scope.** A packet's labels are its own. Every window, every expansion window and every stitch shard numbers from 1.
A record that one window owns and another shows as overlap has a label in each, and its entry is the identity across
them. A heading still holds its value alone on its line: `entry: e12`. Then comes the kind line:
`<kind>[:<tool>] <time> <role>`. Since the label no longer says which part of a record a span is, the kind line now
ends with `part k of n` for a span, in an overlap too.

**Determinism.** Labels follow from the packet's own inputs: the window, its rows and the due list, or the stitch's
events and claims. As a result:
- A retry's packet is its first packet plus the correction, so it shows the same labels.
- A resumed run reuses an attempt only for an equal payload, so it shows the same labels.
- Nothing stores the labels. The map is computed again from the same inputs wherever an answer is read.

**The omission line.** Each omission line reads:

```
- o1: in e7, 14300 of 15000 characters omitted, must expand (pending_event)
```

- Only the window's own records' omissions get an `o` label. They are the only ones its answer decides
  (D-20261103-8bfd69).
- An overlap row of the omission manifest is never listed and never labelled. The window that owns its record decides
  it.
- So `in eN` always names an owned, clipped entry of this window: the entry that carries the record's clip. For a split
  record, that is its first span. It never names an overlap entry.

**Stitch events.** An event's own claims are shown by their facts alone (`facts`). An event cannot join its own
claims, so they need no label, and showing their stored ids would leave an id to copy.

## Where labels become entries

- `Labels` (read) and `StitchLabels` (stitch) hold one packet's labels.
- The stage's check (`answer_problems`, `stitch_problems`) reads an answer in labels. Every line it writes names what
  the reader wrote, so a retry's correction never shows an entry.
- `resolve` turns an accepted answer into entries, omission ids, expected ids and stored ids. It is called once, where
  the stage reads that answer: `Reader.window` and `Reader.stitch`. Everything after it - `keep`, the decisions, the
  stitch's outcomes - works in entries as before.
- A label `resolve` does not know is refused by name (UNKNOWN_LABEL). An answer that bypassed the check therefore
  still cannot store a label.

What this leaves unchanged:
- `result.json` keeps the reader's labels, as written.
- The stores hold no label, so their bytes for a given answer are what they were.
- The reuse condition is unchanged: payload, seat, schema and output cap.
- The resume equality and the `jobs` equality are unchanged.

The schemas changed, so their sha changed once. An attempt made before this commit is not reused (REUSE_SCHEMA_CHANGED).

## Holding the reader to labels

The schemas take a fixed pattern at every field that names a label:
- read: `^e[1-9][0-9]*$` for the entry, `at_record` and `occasion_locator`; `^o…` for `omission_id`; `^x…` for
  `expected_id`;
- stitch: `^v…`, `^c…` and `^q…`.

The host refuses any other value: an entry, a near copy of one, a stored id, a label with its field name, or a padded
label. The schema stays one per stage.

A per-call enum of the packet's own labels was weighed and closed (D-20261105-7dbc98). It would cost:
- about 11 KB a call on a full window, since the host form copies each `$ref`;
- a schema sha that changes with every call;
- a new fit for the packet overhead and for every window cut.

A label that is well formed but not shown in the packet is refused by code: `UNKNOWN_LABEL <label> at <path>: this
packet shows no <entry|omission|expected observation|event|claim|quote> so labelled`. This takes the stage's one
retry. It replaces the read check's "is no entry this window shows" and the stitch's "is no event this packet lists".
In a stitch, a claim or quote the packet shows but the event may not rest on stays RECORD_INTEGRITY. So do the checks
read after mapping:
- an event on a context record or off the window's own records;
- an occasion off them;
- a quote's text located at store (QUOTE_MISMATCH).

**Disclosed, not new:** a label that is wrong but shown passes, exactly as a wrong but shown entry did. A quote is still
held to its text. Nothing judges which record an `at_record` or an occasion should be.

## What moved

**Window cuts.** S2 measures each window as rendered, labels included. An `e9` that becomes `e10` costs its byte in
the measured bytes, so nothing about label width is estimated. The cut's first guess per entry now uses the widest
label any window renders (`LABEL_BOUND`, `e99999`) instead of the entry. Windows of short records therefore hold more
of them:
- On the live apart session, a window holds 133 to 139 turns.
- Its fifth window now begins at the 538th turn; it began at the 450th.
- `FX_APART_LIVE_TURNS` and `FX_TWIN_LIVE_TURNS` are now 548 and 537. Their controls hold the same placements as
  before: the outcome is eleven turns into the fifth window, past the fourth window's overlap, and the twin is the
  first four windows.

**C1.** C1's windows will not compare byte for byte with the 0708c and 0708d runs.

**The shard rule's fixture.** Stitch rows got shorter, so the fixture's room beside the stitch packet's fixed part is
now 3,000 bytes, down from 4,000. The same shards came out anywhere from 2,600 to 3,500 bytes.

**The read packet's fixed part.** It grew with the new wording and the patterns. It now leaves 785 bytes under
`bound.PACKET_OVERHEAD`, down from 1,278; `packet`'s self-test holds this.

## Controls

These are in the `stage_read` self-test unless named otherwise.

**Labels in the read packets:**
- Every window packet of the live legs shows `entry: e1` to `eN` in render order, and those labels are exactly the
  entries the check takes as shown.
- No heading of a window or expansion packet holds an entry.
- An apart window of more than a hundred labels is measured with them.
- An expansion window numbers its labels from e1.
- A window's retry shows its first packet's labels. So does a stitch's.
- The omission lines are the own rows alone, `o1`... in order, each `in` the label of the owned, clipped entry. The
  overlap rows are present in the windows and absent from the lines.

**The stage's check and `resolve`:**
- UNKNOWN_LABEL is named at each read field: a quote's entry, an event's `at_record`, an occasion, an expected id and a
  decision's omission.
- It is named at each stitch field: event, claim and quote.
- In a stitch, a shown claim that no event may join stays RECORD_INTEGRITY.
- Every window of the golden view round-trips: an answer written in entries, put in labels, passes the check and reads
  back exactly.
- `Labels.resolve` refuses an unknown label at each field.
- `StitchLabels` numbers events, claims and quotes, with one label for a shared quote, and reads an answer back as
  stored ids.

**Packet text and schemas:**
- The read and stitch schemas, as written and in the host form, take the answers in labels and refuse 11 shapes at
  each of the 5 read fields and 3 stitch fields.
- Every read packet tells its reader to name entries, omissions and expected observations by its labels, and no longer
  to copy an entry to the end of its line. Every stitch packet tells it to name events, claims and quotes by theirs.
- Every stitch packet names events, claims and quotes `v1`/`c1`/`q1` in order, its joins among them, no own claim ids,
  and no stored id anywhere.

**In `views`:** a split entry's kind line ends `part k of n`, owned and in an overlap, and the fixture has both.

**Existing controls kept.** These hold unchanged:
- kill-and-resume;
- the `jobs` 1 and 12 byte equality;
- store immutability;
- the overlap accounting.

**Existing controls rewritten.** Controls that named an entry or a stored id where a packet now shows a label find what
they look for by what it is. An event is found by its description, or by where it stands for a carried one. A stitch's
stand-in for an unknown join is `c99`/`q99`.

**The pretrial** (`wp08b/pt8b-pretrial.py`, on a copy of the tracked tree), 22 rows:
- Unmutated, seven suites passed: stage_read, views, packet, claims, records, evidence and measures.
- Each of the 21 other rows reverts one new check alone, and each failed its control by name, with no traceback. They
  cover: UNKNOWN_LABEL at each read field and at each stitch field; each `resolve` refusal; `resolve` dropping one
  mapping; entries rendered in place of labels; the label order; the span part; the omission line's `in`; each
  schema's pattern; stored ids in the stitch packet; an event's own claim ids; and the old packet sentence.
- The first run missed three rows, for the tool's own reasons:
  - Two reverts emptied a loop's body and the copy did not compile. They now revert to `pass`, and the tool counts a
    copy that does not compile.
  - One run stopped on an existing control (W r1's carried-only view) that called `startswith` on a missing value. That
    control now reads it as empty and fails by name.
  - Rerun on the fixed tree, all 22 rows held.

## WP-08b: scope and done-when

**Scope:**
1. Commit 1, this record: the labels in read and stitch packets, their check, their mapping, the schemas, the packet
   text and the fixtures they moved.
2. Commit 2: DW5's follow-up half on a seeded schema-2 fixture ledger: one session, two windows, and one expansion
   that a retrieval term forces. Its expected observations are observed, not observed, pre-application,
   `exposure_unknown` and search-forced.
3. Review X (the packets and schemas) after commit 1, and W (the code) after commit 2, each at most two rounds.
4. The live legs, run by the owner (D-20261105-7dbc98): the dw2 fixture with labels, then DW5's follow-up half. They
   use at most 9 Claude calls, 80k input and 20k output tokens. The apart leg is not run.

**Done when:**
1. Every value a read or stitch answer names is a label its packet shows once, on its own line or field, and the
   schemas take nothing else.
2. An accepted answer's labels become entries, omission ids, expected ids and stored ids in one place per packet kind.
   The stores, the reuse condition and the resume equality are what they were.
3. A label the packet does not show is refused by name at every field, and a retry shows the same labels.
4. The dw2 leg's answers pass with labels and store what its golden run stores.
5. DW5's follow-up half derives and stores resolutions from answers written in labels. The verdicts are reported
   against the fixture's intent; a disagreement is recorded, not gated.

**Out of scope:**
- The C1 judge tools (`work/impl/wp08/c7/judge`) match rendered windows. They are on the lead's list for the
  pre-production recall measurement.
- `call_id` stays as §3.3 has it.
