---
created_at: 2026-10-23T23:35:00+09:00
head: 352d35f
kind: review
supersedes: 2026-10-23T2038--c23dd2d--the-bytecode-control-asks-a-copy-and-a-location-names-a-declared-member.md
---

# An observation of one event kind is not an observation of every write

Round 1 of the hermetic review of WP-07 package A read the tree at `352d35f` and returned seven
findings, five of them boundary defects the suites were green over. This record replaces two
statements of the 2038 record and nothing else; the rest of it — §1's other bullets, §2, §4, and
§3's rule about declared member names — stands as written.

Both replaced statements have the same shape: a claim stated in the language of a property
(*every* attempted write, *every* line the driver prints) resting on a mechanism that covered one
case of it. The suite was green because the control exercised the covered case.

## 1. §1: "the audit hook reports every attempted write whose real path is under the copy"

**That was not true of the tree it was written against.** `BYTECODE_PROBE`'s hook returned
immediately for every audit event except `open`, so a directory created, a file renamed and a file
deleted under the copy were all unobserved, and the disk check afterwards scanned only for `.pyc`
files. The guarded run's `writes_under_checkout=0` was therefore a statement about write-mode opens,
not about writes — and the sentence that made the wider read-only claim and the bytecode claim "one
observation" was the part that did not hold.

What now holds, measured on this tree:

* The hook resolves a path at event time for the filesystem-mutating audit events as well as
  `open` — `os.mkdir`, `os.rmdir`, `os.remove`, `os.rename`, `os.replace`, `os.link`,
  `os.symlink`, `os.truncate`, `os.chmod`, `os.chown`, `os.utime`, the `shutil` operations and
  `tempfile.mkstemp`/`mkdtemp` — through a table that maps each event name to the index of its path
  argument.
* The positive controls run on the same copy before the guarded run: a directory created, a file
  written, a file renamed, a file deleted, a directory removed, and **two attempts that fail**. An
  audit hook fires before the operation, so a refused attempt has still been attempted, and the
  observation is of attempts.
* The after-run check is a comparison of the copy's **whole tree** — every relative path with its
  content digest — against the same tree before the run, rather than a scan for one suffix. A missed
  event kind shows up there as a difference.

## 2. §3: "every line the driver prints"

`projection.diagnostic` covers the lines `distill.py` prints *within* its exception boundary. Two
exits were outside it. The `runlib` imports run before the boundary exists, and
`runlib/validate.py` exits during import when its JSON Schema pin is unreadable, interpolating the
absolute pin path; and `main` invoked the top-level self-test outside the `try`, where the suite
printed its own failure strings — which carry fixture paths, and a failure line is exactly where a
disclosure would be.

What now holds:

* The `runlib` imports sit inside `try/except BaseException`, and the handler prints through the
  same projection. If the floor itself is what failed to import, the driver prints one fixed,
  path-free line (`STARTUP_WITHHELD`) and exits 2 — it does not describe a failure it cannot
  project.
* The self-test's diagnostics are printed through the driver's own printer, to stderr.
* Both exits have controls: a fixture pin made unreadable in a disposable checkout copy produces a
  projected diagnostic with `<HOME>` in it and the absolute path absent, and a copy whose
  `learn/redact.py` cannot be imported produces exactly the fixed line.

## 3. The three remaining findings, and what each one's control now asks

These were not claimed by the 2038 record; they are recorded here because each is a boundary that
looked closed from inside the suite.

* **Span projection could publish what the intact carrier withholds.** `carrier_decision` asked the
  floor about the whole carrier, but `carrier_extents` returned only `mask_extents`, so the floor's
  decision to decline a carrier **altogether** — undecodable escaped text, an output that still
  discloses — reached no span. For `api\_key: "alpha\nbravo\n\nshortpass"` the floor withholds the
  carrier and the span path published a later block of it with the value intact. The decision is now
  `(extents, withheld)` and a withheld carrier withholds every span of it. Two controls: the escaped
  fixture through `units_of` → `shed` → the real `write_document`, read back from disk; and a
  differential over every carrier fixture in the suite — no line the intact carrier does not keep
  appears in any emitted span — with a positive control that projects each span detached, which is
  the shape the fix replaced.
* **`--no-state` made the owner's roots writable.** The flag that says "read no state root" set both
  roots to `None` before the protected set was built, so `--state-root S --to S/out --no-state`
  exited 0 and wrote four artifacts under `S`. Protection and reading are now two questions:
  `configured_roots` resolves the roots from the flag, the environment, then the installed default,
  whether or not this run opens them, and `inventory.run` takes the declared pair beside the read
  pair. Controls at both layers, each asserting the attempted write did not happen.
* **`source_selection` was a claim about where reads pass, not the gate.** `hash_tree` and `freeze`
  read their selected paths directly; denying the selection outright still hashed eight files and
  copied one. Both now admit through it and report a denial as an omission rather than a silence,
  and the control denies it and reads the omissions back.

## 4. A self-test's own scratch parent is a protected-root question

Both suites asked `tempfile` for a scratch parent. `tempfile` resolves `TMPDIR` by **probing** it,
so an ordinary `TMPDIR` inside a checkout's `.tmp` or inside the owner's state root put every
fixture, the checkout copy and the cleanup inside a protected root before production's preflight
could refuse anything. `inventory.scratch_parent` now judges the parent by `temp_home`'s path-only
rule over the same protected set, and the control calls it with a fixture environment rather than
running the suite recursively.

One adjacent correction: the control for a protected `TMPDIR` used to install its fixture value in
`os.environ` and then **pop** `TMPDIR`, so every later `tempfile` call in that process resolved
somewhere other than the parent the suite had been given. The environment under test is now passed
as an argument.

## 5. A test's cleanup is a write like any other

The checkout-protection control wrote its destination inside the review checkout — which is the
root the rule is about — and removed it afterwards unconditionally. A failing control appends its
failure and execution continues, so a leftover from an interrupted revert, or anything else at that
path, was deleted inside the reviewer's tree. No adversarial condition was needed.

The control now runs against a **disposable copy** of the checkout, and the driver under test is
that copy's own, so the copy is the checkout the rule protects. Nothing is deleted: the copy lives
under the judged scratch parent and goes with it. A second control states the shape the old cleanup
would have destroyed — a pre-existing destination holding a sentinel this test does not own is
refused, and the sentinel is still there afterwards.
