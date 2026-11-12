---
created_at: 2026-11-12T12:10:00+09:00
head: 5a18ebd
kind: review
supersedes: 2026-11-12T0310--5f74b1e--s7-proposes-and-s7b-reviews-what-only-code-can-hold-lives-in-tables.md
---

# WP-11's review is closed; WP-10's first-round findings, as answered so far

Lane E, branch `wp/20-review`, from `65fe927` (WP-11 at its second Codex review) to `5a18ebd`, plus
the commit that carries this record. What follows states what each finding was, what the code at
that head does about it, and which control holds it. Commit messages carry the detail; this record
is the one place the two review units are read side by side.

## WP-11, round 2 (Codex X), all four fixed

| # | Finding | Commit | What the code does now |
| --- | --- | --- | --- |
| 1 | A corrective retry's due hash was given for any text in the correction's frame | `18ead2c` | `due_correction` rebuilds the correction from the failed predecessor's own records (its stage check, else the gate's verdict); `corrected_sha256` compares the whole expected payload byte for byte |
| 2 | S10's reader admitted any file whose call id matched | `d7cc4ec` | the live derivation reads what it accepted; the disk reader reads S6's files only as S6's stage record registered them and holds each to the accepted call's own records |
| 3 | A due decision's `resolves` reached every packet kind | `3f297b7` | `LIFECYCLE_INTERNAL` leaves it out of the judge, reconsideration, sweep and cross-review projections |
| 4 | K5's fixture crashed before its control when B was dropped; its revert rows matched nothing | `d7cc4ec` | the fixture copies the whole run; the artifact control asserts the exact set |

The lead re-ran every row of the round's four row files in a clean clone at `3f297b7`: zero
substitutions failed to match, every row was caught by name with no traceback, the no-edit rows
passed, and the three superseded rows of round 1 were refused as matching nothing. WP-11 is closed.

**One single revert is not caught, and that is accepted as equivalent (lead decision, 2026-11-12).**
Removing only `due_correction`'s "no predecessor" guard does not let a first attempt's correction
through: two other checks each still refuse it. The predecessor must have been sent the payload
alone, and the attempt's bytes must equal the payload plus the correction rebuilt from that
predecessor. So no single revert reopens the hole, and the row was dropped from the trial rather
than kept as a miss. If either of the other two checks is ever removed, this guard is the only one
left, and its own control row has to come back.

The revert tool refuses a row whose substitution matches zero times (NO-MATCH), as it already
refused one that matches twice. The older J-stage rows whose anchors later J-steps moved stay as
they were, valid at the commits they were written for.

## WP-10, round 1 (Codex X): what is in

| # | Finding | Commit | Answer |
| --- | --- | --- | --- |
| 1 | S5's cited set missed admission, tension and event claims | `2abae35` | fixed |
| 2, 3 | A requirement's coverage was read one read at a time, and the unparsed check asked only the unit's carrier | `46031b1` | fixed |
| 4 | Planted candidates are told from natural ones by id form and label order | `4300ea9` | refuted for what a judge is sent; see below |
| 5 | Runtime decisions restated table values | `cb00abf`, `f94dd76` | fixed: delivery evidence reads the licensed level and the native layer's level; S5's and S6's verdicts on a control apply the rule its table row states; eligibility is the row's; the paraphrase count is the table's |

**#4.** On disk the two kinds differ by design: S4's own `candidates.json` lists the natural ones. The
requirement is that no judge can tell them apart, so the control runs over every S6 packet the
complete golden sends, all four kinds. No candidate id appears in any packet. No judge or
reconsideration packet holds its candidate's stored label. Each CALL-ID names a candidate only by
`item_of`, one digest for every member. Where candidates share a packet (a sweep shard), they are
grouped and labelled k1, ... in candidate-id order. Every formed id, planted or natural, is `k-` and
sixteen hex digits of a sha256, so that order is a digest's, not creation order or label number;
this record's commit adds that control.

One observation, not a finding: a planted `temporal_order_cause` control changes only its admission's
stated reason. Its sweep view (lesson, type, situation, action, exception) is therefore its borrowed
base's. If both are absence claims in one sweep group, a sweep packet shows two identical views. That
says a control exists, not which candidate it is, and a sweep judges coverage, which that control is
not checked on.

The rest of WP-10's findings (#6 to #10) follow in their own commits.

## Also in this range

`5a18ebd`: delivery evidence orders a carrier's lines by the inventory's published `n` (lead
decision 2026-11-12: the inventory emits no `start`). The suite's unit helper and the frozen fixtures
had invented a `start`, and both drop it. A second invented field was found and is open:
`surface_row` reads `unit.get("surface")`, which producer units do not carry. Whatever calls
delivery evidence (lane L's S5b) has to supply it.
