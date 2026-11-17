---
created_at: 2026-11-06T00:55:00+09:00
head: 3809707
kind: design
supersedes: null
---

# A host is handed only the keywords both readings share, and a zero token cap starts nothing

WP-08c, commit C: items 6 to 9 of the package. Item 10, the live pair's report tool, is a work tool outside the
repository.
- Item 6 extends WP-08b's label-pattern fix (`2026-11-05T2003--303372d--...`) to the ids a reading makes up itself.
- Item 7 closes in the product what C1's first live leg showed (`2026-11-04T1922--bb9d199--...`, "c1-live1").
- Item 8 replaces a self-test list with a check on every schema a host is handed.
- Item 9 moves done-when 3's golden controls.

## 1. A reading's own ids end where their string ends (item 6)

**Before.** WP-08b ended every label pattern with `(?![\s\S])`: the labels a packet shows, which the answer copies.
The ids the reading makes up itself kept a pattern ending in `$`. There are five such fields: `quote_id`, `claim_id`,
`event_id`, and the `evidence_ids` and `claim_ids` lists that cite them. Python's `$` also matches before a final
line break, so the policy accepted `q1\n`. The host's check refuses it: in a JavaScript pattern, `$` is the end of the
string.

**Now.** The read schema's five id fields end with `(?![\s\S])`, as the stitch schema's already did. No pattern in
the read or stitch schema ends with `$`.

The control bends each of the five fields five ways (`1\n`, `12\n`, `1\r\n`, `01`, `1 `), 25 answers in all. Both the
schema as written and its handed form must refuse every one.

## 2. A zero per-episode token cap starts nothing (item 7)

**Before.** In c1-live1 every per-episode cap of the declaration was 0. The dispatcher admitted the call. The
supervisor stopped the host 0.089 s after it started, and whether its request was sent is unknown. Since then a work
tool (`live-leg.py`) refused zero caps before a leg ran; the product did not.

**Now.** `dispatch` refuses a per-episode token cap below 1 by name, `EPISODE_CAP_ZERO`:
- `item()` refuses first, before anything is reserved. The ledger and the calls directory stay as they were.
- `call()` refuses after `CAP_MISSING` and releases the reservation it holds. This covers a call made without `item()`.

**Only the token cap is refused.** The lead's rationale: of the per-episode caps, only tokens and compactions reach
the host's monitor, and max_turns and max_budget_usd are read only where the breaker reads a host's stop. A compactions
cap of 0 is a normal cap: it allows no compaction. The control checks that such a cap is not refused as
`EPISODE_CAP_ZERO`; the call goes on to the packet's own check.

## 3. One keyword allowlist for every schema a host is handed (item 8)

**Before.** The host checks a handed schema with Ajv's draft-07 class, while the policy reads the same schema as draft
2020-12. A self-test control in `stage_read` listed the keywords drafts 2019-09 and 2020-12 added, and looked for them
by key name anywhere in S3's schemas. That list had three gaps:
- it covered S3's schemas only;
- it took a property whose name is a keyword for that keyword;
- a keyword on neither draft's list passed.

**Now.** `packet.schema_bytes` makes the bytes of every schema a host is handed: the read, the stitch and the judge's
verdict. Dispatch's `call`, `item` and `reusable` all go through it. It now checks the handed form against
`HOST_KEYWORDS`, the 17 keywords both readings read alike:
- **The form checked** is the one the host receives. `host_schema` flattens it, so it holds no `$schema`, `$defs` or
  `$ref`; any of the three is refused.
- **The walk follows the schema's structure.** It enters the schemas under `properties` and `patternProperties` by
  name, and the schema that `items` or `additionalProperties` holds. A property named `items` or `required` is a name;
  an `enum` or `const` value is data.
- **`items` as a list** is refused. Draft-07 reads it as a tuple; draft 2020-12 refuses the schema.
- **A violation** raises `HOST_SCHEMA_KEYWORD`, a `SchemaPolicyError` that names each keyword and its place. `item()`
  makes the handed bytes before anything is reserved, so a refused schema reserves nothing.

The stage_read control now asks `packet.host_keywords` of every form S3 hands a host, instead of keeping its own list.

**The measurement.** The probe ran offline, with no model call:
- Ajv 8.20.0, with the options Claude Code 2.1.317 gives it: allErrors on, validateFormats off, multipleOfPrecision 6;
- node v26.0.0;
- 18 probe schemas. The probes and their scripts stay in the work directory.

| Probe | Ajv | The allowlist |
| --- | --- | --- |
| The 17 allowed keywords, in 11 probes | compiles | passes |
| `dependentRequired`, `dependentSchemas`, `prefixItems`, `unevaluatedProperties` | `strict mode: unknown keyword` | refused |
| `$schema` naming draft 2020-12 | `no schema with key or ref` | refused |
| `$defs` with a `$ref` into it | compiles | refused |
| `items` as a list | compiles, warning that it is a 1-tuple | refused |

Ajv also warns, without refusing, when `minimum`, `minLength` or `pattern` stands in a schema with no `type`.

Two of the refused rows are schemas Ajv compiles:
- **`$defs` and `$ref`:** a handed form is flattened, so they in it mean the flattening missed something.
- **`items` as a list:** the two readings take it to mean different things.

## 4. done-when 3's golden controls move onto the live apart fixture (item 9)

**Before.** `fx_apart_records` held two subjects: the shard rule's session, and done-when 3 (a cause and its outcome in
windows that cannot see each other). Its windows were apart only in what they own. The live apart leg had shown that
shape fail live: the outcome stood in the overlap of the earlier windows, so the reader quoted it from the first
window on.

**Now.** Three controls run on the golden runs of the live `apart` and `twin` fixtures, the ones a live leg spends
calls on:
- **The apart leg.** The cause in window 1 is resolved by the outcome's claim in window 5. Its evidence stands on
  window 5's outcome record, as `in_window`.
- **Event ids.** The same local event id, in the same window of the same view, read by two runs, is two events.
- **The twin.** It holds no outcome. It is stitched by a call, not by code, and left unresolved, and its event is
  handed on as a pending event of the unit's result.

Beside them stays the control that no window before the outcome's owns the outcome or shows it, overlap included,
and that no packet of theirs holds its text. `fx_apart_records`' description now names the shard rule alone.

**Time.** The lead's bound: if stage_read's self-test grew by more than 10%, rebuild the old fixture instead.

| | Run 1 | Run 2 |
| --- | --- | --- |
| Before | 61.86 s | 60.89 s |
| After | 57.49 s | 58.37 s |

It is about 5.7% faster, so the move stands.

## 5. Controls

Each control was shown to fail by name when its subject is bent. The pretrial tool (`pt8c-pretrial.py`) is a work
tool outside the repository.

**pt8c-c, 11 rows:**
- the 3 `none` rows passed;
- 7 bending rows were caught by name;
- 1 was missed: `host_keywords_reads_names`, which walked a `properties` map as if it were a schema.

**Why that row was missed.** The bend reads every property name as a keyword, so it refuses every real schema: the
first is `answer` at `#/properties`. The product's own `HOST_SCHEMA_KEYWORD` then ends the suite at its first schema,
before the named control reports.

**pt8c-c2, 3 rows.** It judged that row as a product refusal, and added the bend the control was written against: the
walk kept, and a property flagged when its name is a keyword the allowlist leaves out. Two forms of that bend were
tried, and the named control caught both.

| Control | Bent subject | Run |
| --- | --- | --- |
| `packet`: `host-schema-refuses-a-2019-keyword-by-name` | the allowlist check removed from `schema_bytes` | c |
| `packet`: `host-schema-takes-properties-named-like-keywords` | a property named `dependentRequired`, `prefixItems`, `$ref` and the like flagged by name; a property named `items` or `required` flagged by name | c2 |
| product: `HOST_SCHEMA_KEYWORD` in `schema_bytes` | a `properties` map walked as a schema | c2 |
| `packet`: `host-keywords-name-each-unread-keyword-where-it-stands` | `items` as a list allowed; the subschemas of `items` and `additionalProperties` not walked | c |
| `stage_read`: "WP-08c: the read schema, as written and as a host is handed it, refuses an id the answer makes up itself ..." | `claim_id` back on `$` | c |
| `stage_read`: "done-when 3 (golden): a cause in window 1 whose outcome is in window 5 is stitched ..." | the apart fixture's outcome claim not joined to its cause | c |
| `dispatch`: `episode-token-cap-zero-refused-before-anything-starts` | the refusal in `item()` removed; the refusal in `call()` removed | c |

**Not bent on its own.** The stage_read control that asks `packet.host_keywords` of S3's handed forms calls the
function the packet rows bend. It was not bent separately.

## 6. Decisions

- D-20261106-01255a: the allowlist on the handed form, and what it closes (vendoring Ajv, the name list).
- D-20261106-19b00f: done-when 3's golden controls on the live apart fixture.
- D-20261106-c1b659: `EPISODE_CAP_ZERO` on the token cap only, before anything is reserved.
