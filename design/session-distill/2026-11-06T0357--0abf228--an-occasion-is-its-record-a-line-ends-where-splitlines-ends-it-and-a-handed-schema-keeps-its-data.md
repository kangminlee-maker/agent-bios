---
created_at: 2026-11-06T03:57:00+09:00
head: 0abf228
kind: design
supersedes: null
---

# An occasion is its record, a line ends where splitlines ends it, and a handed schema keeps its data

WP-08c, commit D: the fixes of review round 1, where X and W both returned fix_then_accept, and the lead's condition
that a product refusal fail a control by name. It corrects the line-boundary rule of commit A
(`2026-11-05T2202--01ab16a--...`) without editing that record, and amends §11 (what an instance is) of the mechanism
design (`2026-10-20T1942--9684f05--mechanism-design.md`).

## 1. A clip's bounds end where str.splitlines ends a line (X r1, major)

**Before.** `clip_bounds` moved the head and the tail only to `"\n"` boundaries. The clipper and the view check read
error lines with `str.splitlines`, which also ends a line at `"\r"`, U+2028, `"\x0c"` and other separators.
- X's case: 300 lines of 41 characters, each ending in `"\r"`, were cut at 1,200 and at n-800, inside lines, although
  line boundaries at 1,189 and 11,521 kept more than half of the head and of the tail. `check_tiling` saw nothing wrong.
- U+2028 line ends gave the same result.

**Now.** A line ends where `str.splitlines(keepends=True)` ends it:
- `"\n"`, `"\r"`, U+2028, `"\x0c"` and the other separators it knows each end a line;
- `"\r\n"` is one line end, so no bound falls between its `"\r"` and `"\n"`.

The head ends at the last line boundary at or before 1,200, and the tail starts at the first at or after n-800.

**A correction to commit A's description.** A's record and C's docstring said the cut falls back to characters "as in
a block that is one long line". The fallback is wider than that. The cut is by characters, at 1,200 or at n-800
itself, whenever the nearest line boundary would keep less than half of the head (600) or of the tail (400). That
happens in a one-line block, and also in a block whose line around the cut is that long.

A character cut is not moved off a `"\r\n"`, so a fallback can fall between its two characters. Such a cut is a
character cut, the same as one inside a long line.

**Measured.** The comparison script is a work tool outside the repository.
- 20,000 random blocks whose lines end in `"\n"` only: the new bounds equal the old in all 20,000.
- 20,000 blocks with mixed line ends: every bound is the nearest line boundary, or the documented character cut. The
  new bounds differ from the old in 10,191 of them.

**Commit B's control on error lines changes.** Commit B added a control for an error line between the head's `"\n"`
end and the 1,200th character. That case existed only because the bounds and the error lines read different line ends.
With one rule for both, the error lines read between the clip's bounds equal those read between 1,200 and n-800, so no
row can tell the two apart. The control now holds what must stay true on a result whose lines end in `"\r"`:
- the clip's bounds, the view check's error lines and the manifest's omitted span name the same bounds and the same
  error line;
- the error line is kept, and hiding it is named `ERROR_LINE_DROPPED`.

## 2. An occasion is its record (W r1, major; §11)

**Before.** `keep` named an occasion by its view and the entry the reading named. A record too long for one entry is
shown in parts, and a part's entry carries `#k/n`. W r1 found three consequences:
- the window that clipped a record and an expansion of its middle split into parts named two occasions;
- `settle_occasions` never put them together, so equal judgements were counted twice;
- the window's `not_observed` decided over the expansion's `observed`, and an exposure difference gave `not_observed`
  where it should give pending.

W r1 also found the case is not rare: under a real packet's overhead, a result of 100,450 characters was one entry
in its expansion before commit B, and two once expansions carried overlap.

**Now.** `keep` names an occasion by its view and its `record_id`, without the part. Every part of one record is one
occasion: in one expansion window or across several, and in the windows (a long record shown across windows) as in
an expansion.

The readings of one side (the windows, or the expansions) are judged together first:
- the same judgement is kept once, with the evidence of every reading;
- **a difference in the exposure alone** gives `exposure_unknown`, so the resolution is pending and the unit stays
  `read_complete`. Each part's window shows other context: a later part's overlap is the earlier part, not the records
  before the record. Reading again would not settle such a difference. This is the rule D-20261104-a9e2d2 gives a
  window and its expansion, so one rule holds (D-20261106-e42658, the lead's choice);
- **a difference in the verdict** keeps none of it, named conflicting, and the unit is `read_partial`, as before.

Between the two sides, D-20261104-a9e2d2 holds unchanged. A different verdict is the expansion's, a different exposure
gives `exposure_unknown`, and the window's judgement is named superseded.

**Where the name is read.** All of these now carry the record-level name, and none of them parses a part from it (the
search was by `occasion_locator` and `span_of`):
- `measures.derive_resolution` and its input check, which refuses a repeated occasion;
- the late rows of a backlog record;
- the superseded and conflicting entries;
- the stored instances (`observations/<window>.jsonl`);
- each window's observations in the read record.

The answer check still judges entries, because a reader names entries: the repeated-occasion check, the ownership
check and `EXPOSURE_ORDER` all read the labels the packet shows.

**The limit.** A verdict difference within one side can be structural too: only a later part may show the outcome the
verdict rests on. Such a unit can stay `read_partial` when it is read again. It is not fixed here. If a live run or C2
shows it, it is looked at again.

## 3. A handed schema keeps its data (X r1 minor, W r1 major)

**Before.** `host_schema` replaced every dict holding `$ref` with the `$defs` entry it named, wherever the dict stood.
- A property named `$ref` raised `KeyError`.
- A literal `{"$ref": ...}` in an `enum` or a `const` was replaced. In W's case, the original schema refuses
  `{"payload": {"type": "string"}}` while the handed schema, and `gate.schema` with it, accept it. The allowlist ran
  after the change and saw nothing wrong.

**Now.** `host_schema` walks the schema by its structure, with the same constants `host_keywords` uses. It enters the
schemas under `properties` and `patternProperties` by name, and the schema `items` or `additionalProperties` holds:
- a property named `$ref` is a name;
- an `enum`, `const`, `default` or `examples` value is data, kept as written;
- any other keyword's value is kept as written too, and `host_keywords` then refuses that keyword by name;
- a `$ref` that names no `$defs` entry is refused by name (`HOST_SCHEMA ...: the reference names no entry of $defs`),
  where it raised `KeyError` before.

**The control.** The schema as written and its handed form must accept and refuse the same answers for five schemas:
a literal `$ref` in an `enum` and a `const`, a property named `$ref`, the read schema, the stitch schema, and the
judge's verdict schema as dispatch hands it. Each schema has at least one answer accepted and one refused.

## 4. A product refusal fails a control by name (the lead's condition)

**Before.** When a bend made the product refuse, the refusal ended the suite as a traceback before the named control
reported. Earlier pretrials could only judge such rows as product refusals (`refused:`, `raised:`).

**Now.**
- **views.** The five expansions the self-test makes directly go through `try_expand`. A refusal fails each control
  that reads the expansion, with "not run (<the refusal's first line>)" as its value. The expansions' log is read only
  when it exists. The split-middle control was already guarded (commit B).
- **packet.** The first schema the self-test builds is a positive control of its own,
  `schema-builder-takes-a-conforming-schema`. When it is refused, the envelope controls run on the schema's bytes as
  written. A template or schema that fails to load fails its three controls as "not run (...)".

The rows earlier pretrials judged as product refusals are now caught by named controls, with no traceback (§5):
`expansion_overlap_disabled` and `expansion_own_record_included` (pt8c-b2), and `host_keywords_reads_names` (pt8c-c).

**Left out.** stage_read's fixture builder, `fx_plan`, expands through the product before a run starts. So a views bend
that refuses every expansion still ends stage_read's suite as a traceback; pt8c-b's `expansion_overlap_dropped_sr` is
such a row. That suite was outside the lead's scope for this commit.

## 5. Controls

Each control was shown to fail by name when its fix alone is reverted, or its subject bent. The pretrial tool
(`pt8c-pretrial.py`, rowset `d`) is a work tool outside the repository.

**pt8c-d, 10 rows:** 3 `none` rows passed, and 7 bending rows were caught by every named control expected, each with no
traceback. A row's other failures are the controls that read the same bent subject.

| Row | What it bends | Controls that caught it |
| --- | --- | --- |
| `expansion_overlap_disabled` | expansions cut with no overlap (pt8c-b2: a product refusal) | `views`: "WP-08c: a middle too long for one window ..."; "done-when 5: an expansion is additional windows ..." |
| `expansion_own_record_included` | the clipped record among its own neighbours (pt8c-b2: a product refusal) | `views`: "WP-08c: a middle too long for one window ..."; "R#1: the omitted interval ..." |
| `host_keywords_reads_names` | a `properties` map walked as a schema (pt8c-c: a product refusal) | `packet`: `host-schema-takes-properties-named-like-keywords`; `schema-builder-takes-a-conforming-schema` |
| `clip_bounds_newline_only` | `clip_bounds` back on `"\n"` alone | `views`: "WP-08c: a clipped tool result's bounds are line boundaries as str.splitlines ends lines ..."; "WP-08c: on a result whose lines end in carriage returns ..." |
| `occasion_keyed_by_entry` | an occasion named by the entry again | `stage_read`: "WP-08c, an occasion is its record: one window, every reading the same ..." |
| `exposure_split_conflicting` | an exposure-only difference within one side conflicting again (the closed alternative) | `stage_read`: "... one window, its two parts differing in the exposure alone ..."; "... across windows, its parts differing in the exposure alone ..." |
| `host_schema_inlines_data` | `host_schema` back on replacing every dict holding `$ref` | `packet`: `host-schema-keeps-data-and-names-as-written`; `host-schema-judges-every-answer-as-the-schema-does` |

The other new `stage_read` controls of §2 hold the readings of one side that differ in the verdict (in one window and
across windows), and the window side against the expansion side (another verdict, another exposure). No row bent their
branches alone, since commit D keeps them. Under `occasion_keyed_by_entry`, six controls failed besides the expected
one; the log names three of them, all §2 controls.

stage_read's self-test took 58.42 s, with 203 controls.

## 6. Decisions

- D-20261106-e42658: an occasion is keyed by its record, and readings of one side that differ in the exposure alone
  give `exposure_unknown`. It closes keying by the entry id a reading names, and treating an exposure-only difference
  as conflicting.
