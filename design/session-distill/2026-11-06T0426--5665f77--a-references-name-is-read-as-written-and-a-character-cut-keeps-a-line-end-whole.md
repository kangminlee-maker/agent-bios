---
created_at: 2026-11-06T04:26:00+09:00
head: 5665f77
kind: design
supersedes: null
---

# A reference's name is read as written, and a character cut keeps a line end whole

WP-08c, commit E: the fixes of review round 2, the last round. X returned accept with one minor finding, and W returned
fix_then_accept with one major finding and two controls missing. The lead checks the fixes by re-running the
reviewers' reproductions in a pinned clone. This record corrects what commit D's record
(`2026-11-06T0357--0abf228--...`) said of `"\r\n"` and of its manifest control, without editing that record.

## 1. A `$defs` name, and a reference's name, is letters, digits, `_` and `-` (W r2, major)

**Before.** The policy's lint and `packet.host_schema` read the name in `#/$defs/<name>` as written. jsonschema reads
the same reference as a JSON Pointer, where `~1` is "/" and `~0` is "~", in a URI fragment, where `%2F` is "/".

W's case:
- `$defs` holds `"a/b"` (an integer) and `"a~1b"` (a string), and `x` is `{"$ref": "#/$defs/a~1b"}`. The lint
  passed it.
- jsonschema resolves the reference to `"a/b"`, so the schema as written refuses `{"x": "unexpected"}`.
- `host_schema` took `"a~1b"`, so the handed schema accepted that answer, and `gate.schema` with it. `{"x": 5}` was
  judged the other way round.

**Now.** A `$defs` name is letters, digits, `_` and `-` only (`validate.LOCAL_NAME`). With these characters a name
reads the same as written, as a JSON Pointer and as a URI fragment, so nothing is decoded anywhere.
- **One function holds the rule.** `validate.local_ref_name(ref)` returns the name of a `#/$defs/<name>` reference
  whose name keeps the rule, or None.
- **The lint uses it.** It refuses as `SCHEMA_POLICY` a reference that is not such a name, and any `$defs` key outside
  the rule, whether or not a reference reads it. `schema_bytes` compiles a schema through the lint first, so a host is
  never handed such a schema.
- **`host_schema` uses it too.** Called alone, it refuses such a reference as `HOST_SCHEMA`.

All 114 `$defs` names in the repository's schemas keep the rule, as the lead counted and this commit's search found
again. The read, stitch and judge's verdict schemas still compile, and the schema-equivalence control of commit D
still passes.

**The decision.** The lead chose to restrict the names rather than decode them (D-20261106-3f7d6e). No schema here uses
an escaped name, and decoding would add code that must decode alike in two places.

## 2. A cut by characters keeps a `"\r\n"` whole (X r2, minor)

**Before.** Commit D's docstring said a bound never falls between the `"\r"` and the `"\n"` of one line end, and its
record allowed a character cut to fall there. X's case: `"a" * 1199 + "\r\n" + "b" * 5000` was cut at
`(1200, 5401)`, so the head ended between the `"\r"` and the `"\n"`.

**Now.** Either cut keeps a `"\r\n"` whole:
- a head end between its `"\r"` and `"\n"` moves back before the `"\r"`. X's case is cut at `(1199, 5401)`;
- a tail start there moves on past the `"\n"`.

**The tail never reaches that move.** For the tail to fall back to a character cut, the nearest line boundary at or
after `n - 800` must keep less than 400 characters. If `n - 800` falls between a `"\r"` and its `"\n"`, the boundary
right after that `"\r\n"` keeps 799 characters. So the line rule already starts the tail past the `"\n"`.
- The control's tail case, `"b" * 5000 + "\r\n" + "c" * 799`, is cut at `(1200, 5002)` by that rule.
- The tail line stays so that the two ends hold one rule if HEAD_CHARS or TAIL_CHARS change. No pretrial row bends it,
  since no text reaches it.

## 3. The parts across windows, complete (W r2, Q1)

Commit D's seven controls covered one expansion window for every case. Across windows, they covered only the readings
of one side that differ. Three controls now run on the longer log, where the parts lie in three expansion windows:
- every reading the same, window and parts: one instance, `observed`;
- the window against its parts, another verdict: the expansion's verdict, the window's judgement superseded;
- the window against its parts, another exposure: `exposure_unknown`, pending, the window's judgement superseded.

## 4. The line-end control calls `manifest_of` (W r2, Q4)

Commit D's control compared the clip's metadata (`clip_parts`) where its name said "the manifest". It now calls
`manifest_of` on the entry the view builds. On the result whose lines end in `"\r"`, the manifest's row must give:
- the same omitted span as the clip;
- one error line;
- the omission id of that span;
- the sha256 of the span's characters.

## 5. Controls

Each control was shown to fail by name when its fix is reverted. The pretrial tool (`pt8c-pretrial.py`, rowset `e`)
is a work tool outside the repository.

**pt8c-e, 9 rows:** 4 `none` rows passed (validate, packet, views, stage_read; the new controls of §3 and §4 pass
there). 5 reverting rows were caught by every named control expected, each with no traceback.

| Row | What it reverts | Controls that caught it |
| --- | --- | --- |
| `lint_reads_ref_raw` | the lint reading a reference's name as written, with no name rule | `validate`: "an escaped $defs or $ref name, both spellings defined (the reference)"; "... an escaped reference to a plain name" (and the ~1, ~0 and %2F cases) |
| `lint_defs_names_unchecked` | the lint's rule on `$defs` names removed | `validate`: "an escaped $defs or $ref name, both spellings defined (the names)"; "... a name no reference reads" |
| `lint_reads_ref_raw_packet` | both of the above, judged by packet | `packet`: `schema-builder-refuses-an-escaped-reference-name` |
| `host_schema_reads_ref_raw` | `host_schema` reading a reference's name as written | `packet`: `host-schema-refuses-an-escaped-reference-name` |
| `crlf_fallback_split` | the head's move before a `"\r\n"` removed | `views`: "WP-08c: a clipped tool result's cut by characters never falls between ..." |

## 6. Decisions

- D-20261106-3f7d6e: a `$defs` name and a reference's name are letters, digits, `_` and `-`, read by one function in
  the lint and in `host_schema`. It closes decoding JSON Pointer and URI escapes.
