---
created_at: 2026-10-23T20:38:00+09:00
head: c23dd2d
kind: design
supersedes: 2026-10-23T1548--2a61d6b--plan-amendment-a-past-reference-point-is-what-the-transcript-records.md
---

# The bytecode control asks a copy of the checkout, and a location names a declared member

This supersedes four statements of the 1548 amendment and nothing else. Its §1–§8, §11, §12 and
§13 stand as written; so do the dispositions in the §9 table other than the GC#10 row. Each
statement below is replaced because WP-07 package A's implementation made it false, or because it
was already false on the tree it was written against.

## 1. §9.1: the control runs the driver as `__main__` against an uncached COPY

§9.1 said the control "now runs the driver the way production does — `runpy.run_path(...,
run_name="__main__")` inside a child, from a cleared cache". **That was not true of the tree it was
written against.** The committed probe put `session-distill/` on `sys.path`, imported `distill` as a
module and called `distill.main(...)`. That is the one shape production never takes, and the only
shape that caches the driver: the single `session-distill/__pycache__/distill.*.pyc` ever observed
here was the probe's own doing, which §9.1 itself records.

Two further things the sentence got wrong about its own control. "From a cleared cache" meant the
control deleted `__pycache__` directories **inside the review checkout** — a write into the tree the
run is supposed not to write to, and only under `learn/` and `compose/`, leaving `runlib/`'s caches
warm. And what it inspected afterwards was the scratch probe directory, not the tree it had asked
about.

What now holds, measured on this tree:

* The subject is an **uncached copy of the checkout**: its tracked files are copied into a scratch
  directory (1,162 files, 0.3s), so no `__pycache__` can come along, and the control asserts the
  copy holds none before it runs anything.
* The real invocation runs as `runpy.run_path(<copy>/session-distill/distill.py,
  run_name="__main__")` in a child process with no bytecode environment variable set, writing its
  output outside the copy.
* The audit hook reports **every attempted write whose real path is under the copy**, not only the
  bytecode ones. The guarded run reported `writes_under_checkout=0`, and the copy held no `.pyc`
  afterwards. The wider read-only claim and the bytecode claim are now one observation.
* The positive control runs first, on that same copy: a by-path load of `<copy>/learn/redact.py`
  with the guard off was observed writing
  `<copy>/learn/__pycache__/redact.cpython-314.pyc.<n>` and left
  `learn/__pycache__/redact.cpython-314.pyc` on the copy's disk. Both instruments — the hook and the
  disk scan — are therefore known to see such a write in the tree the question is about. The cache
  it made is then removed **from the copy**, and the copy is asserted uncached again before the
  guarded run.
* **No cache in the review checkout is ever cleared**, and the claim is no longer scoped to "the
  modules the command loads by path": it is every attempted write under the copy.

The reason the guarded run writes nothing is unchanged and is still in the code: `distill.py` sets
`sys.dont_write_bytecode = True` before the line that imports `runlib`, and the driver is
`__main__`, which is never cached.

## 2. §9's GC#10 row: it copies rather than clears

The row said the control "clears the caches it asks about so it cannot pass on a cache that was
already valid". It copies instead. The property that row was protecting — that a run finding a valid
cache writes nothing, so a pass can mean nothing — is kept by the copy being uncached by
construction and asserted so, which is also what makes clearing anything in the checkout
unnecessary.

## 3. §9.2: a location names a member the owning code DECLARES

§9.2 said `document_disclosures` "returns locations built from schema-safe names or ordinals".
Schema-*safe* was a syntax test: a key was named when it matched a name-shaped pattern and the floor
had nothing to say about it. Syntax is not authority. `document_disclosures({"api_key":
{"shortpass": {"token": "x"}}})` returned `$.api_key.shortpass.token` and repeated an ordinary short
secret, which is a perfectly ordinary word to find as a key.

The rule now: `document_disclosures` takes the set of member names the code that owns the document
declares, and names a key only when it is one of them. Every other key — including one a document
merely happens to carry — is reported by its ordinal, `[key #n]`. The floor infers no authority; it
is handed one. A name missing from the set costs a readable location and nothing else, so the
failure direction is toward saying less. `runlib/inventory.py` declares `DOCUMENT_KEYS` and
`runlib/records.py` declares `RECORD_KEYS`, and a control asks the floor about every entry of the
former, because a schema that declared a credential name would license naming one.

The rest of §9.2 stands: `projection.document_disclosures` is the one entry point, it takes either
representation and converts internally, and the inventory owns nothing but its refusal code. Two
publications were added to it rather than beside it — every stage-record write
(`records.publish_record`) and every line the driver prints (`projection.diagnostic`).

## 4. §10: dated-record dependence is removed from WP-07, and named where it remains

§10 ruled that no control depends on a dated design record by path. On the tree it was written
against, `runlib/inventory.py`'s `layer_problems` and `contract_problems` both read
`design/session-distill/2026-10-20T1942--9684f05--mechanism-design.md` by path and parsed §6.1 out
of its prose, and `self_test` read that file directly for a third control.

That contract now lives in `session-distill/schemas/inventory.schema.json`, a file the code owns:
it declares the layer set as an enum and the unit record's required fields, it is load-bearing
beyond the comparison (the real documents' units and layer rows are validated against it, and it
compiles under `runlib/validate.py`'s own schema policy), and the design section it was derived from
is cited in its `$comment` as provenance that nothing executable reads. The independence GA#11 asked
for is kept: the schema is a separate file from the tables the code walks, so a layer or a field
deleted from either still fails against something that is not itself. Every negative control now
plants an in-memory schema, so no control depends on a document existing at a path.

**Two executable dependencies of this kind remain outside WP-07's subject**, named here rather than
left to be rediscovered:

* `runlib/declare.py` (`self_test`, the `posture-is-authorized-by-a-named-addendum-that-exists`
  control) requires `design/session-distill/2026-10-21T0318--2d4fbd4--plan-addendum-wp01.md` to
  exist at that path.
* `runlib/ledger.py` (`self_test`) reads
  `design/session-distill/2026-10-21T1545--b324de5--writer-holds-the-transaction.md` and
  `design/session-distill/2026-10-21T0820--9b42df2--plan-addendum-wp13.md` and judges against their
  text.

They belong to WP-01 and WP-13 and were not changed here: editing them moves those packages'
acceptance criteria. §10's ruling applies to them, and closing it is their work.
