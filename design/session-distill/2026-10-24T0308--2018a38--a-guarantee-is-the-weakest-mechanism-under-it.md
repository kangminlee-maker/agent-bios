---
created_at: 2026-10-24T03:08:00+09:00
head: 2018a38
kind: review
supersedes: 2026-10-23T2335--352d35f--an-observation-of-one-event-kind-is-not-an-observation-of-every-write.md
---

# A guarantee is the weakest mechanism under it

Round 2 of the hermetic review of WP-07 package A read the tree at `2018a38` and returned eight
findings — one blocking, six major, one minor. Round 1 had seven. The pattern is not that the fixes
were wrong but that each one exposed the shape beside it: a span was projected with its carrier and
a heading was not; the roots this run reads were separated from the roots it protects and the host
homes kept their defaults; one entry point got a boundary and the other did not.

This record replaces the statements of the 2335 record that are false, or broader than the code they
describe, and one misattribution. Everything else in it stands, including §1's account of what the
probe now observes, §2's account of the startup handler, §3's three findings and §4 and §5.

## 1. What the 2335 record claimed too broadly

Each line below was written as a property and held only for the mechanism that had been built.

* **"every attempted write whose real path is under the copy"** — the hook resolved each pathname
  against the working directory and ignored the `dir_fd` an audit event carries, so a
  descriptor-relative removal resolved to the wrong tree; an integer file descriptor from
  `os.chmod` or `os.truncate` was discarded; and an `open` carrying only `O_TRUNC` was not counted
  as writing. The claim now rests on a `(path arguments, dir_fd arguments)` layout per event, a
  descriptor resolved through `F_GETPATH` (or `/proc/self/fd`), `O_TRUNC` among the write flags, and
  — the part that makes it a guarantee rather than a hope — **fail closed**: a mutation event the
  observer cannot attribute to a tree is counted as `unverified`, and the control requires
  `writes_under_checkout=0` **and** `unverified=0`.
* **"the observation is of attempts"**, for the attempts that fail — observed, but not asserted. The
  control required six rows under the copy, and the successful events alone supply six. Each
  deliberately failed attempt is now asserted by its own `(event, path)` identity, at a path nothing
  else in the probe touches.
* **"the copy's whole tree — every relative path with its content digest"**, offered as the backstop
  for an event kind the observer might miss. A content comparison cannot see a `chmod`, a `utime`,
  or a truncation that restored the same bytes. It now carries mode, size and `mtime_ns` as well.
  It still cannot see an attempt that failed — nothing changes on disk — which is why the failed
  attempts are asserted from the events and never from here.
* **"every line the driver prints"** — the driver's `main` printed through the floor, and invoked
  the top-level self-test outside its own `try`, so an ordinary file failure in a fixture left an
  unprojected traceback. And `runlib/inventory.py` is an entry point too: its self-test printed its
  report with `print`, which carried a planted credential and a fixture path out verbatim. Both now
  run inside one boundary, `runlib/entry.py`, which also owns the fixed path-free line for the case
  where the floor itself cannot load. **Scope, stated rather than implied:** that boundary is
  package A's two files. The other runlib modules each have a standalone `--self-test` that still
  prints directly; they are not this package's subject, and the module's own docstring says so.
* **"a withheld carrier withholds every span of it"** — true of spans, and `heading` was not one.
  For `api\_key: "alpha\n\n## shortpass\n"` the floor withholds the carrier whole; `text` came back
  blanked on every row while `heading` carried `shortpass` on two of them, and the real writer
  accepted that document. Every carrier-derived field now leaves through one path
  (`_carrier_span`), and the differential enumerates **every string the emitted row carries**, held
  against the string fields the schema declares, rather than reading `text` alone.

## 2. The misattribution

The 2335 record said `carrier_decision` "asked the floor about the whole carrier, but
`carrier_extents` returned only `mask_extents`, so the floor's decision to decline a carrier
altogether reached no span". `carrier_decision` is introduced by `352d35f`; it cannot be the cause
of behaviour that preceded it. What the sentence should have said: before `352d35f` the span path
asked `mask_extents` for a carrier's extents and applied the undecodable decision only to the
detached span. `carrier_decision` is the fix's own shape, and in `352d35f` it carried the
whole-carrier decision to `text` and to nothing else.

## 3. What round 2 changed beside those statements

* **Configured host homes.** `NATIVE`'s `home` fields are defaults, and all three protected sets
  read only those — so a home moved by `CODEX_HOME` or `CLAUDE_CONFIG_DIR` was a writable
  destination and an admissible scratch parent. The rule has one owner and it ships:
  `host_homes` loads `compose/instructions_install.py` by path and reads its `claude_root` and
  `codex_root`. `protected_roots` resolves them when its caller names none, which is now what every
  production caller does. A control asserts that nothing this module executes names either
  variable, so the rule cannot be restated here by accident.
* **`configured_roots` reads the environment's `HOME`.** It read the process's own, so the installed
  defaults did not move with a fixture environment — which is how a control that reverted the
  protection it was testing wrote four inventory artifacts into the reviewer's real state root. The
  rule is the shipped installer's (`env.get("HOME", Path.home())`), the control's destinations are
  inside disposable scratch, and every control of both suites was re-read for the same shape.
* **A copy-run is admitted by the call, not by the file.** `COPY_RUNS`'s guard was a file-wide
  substring, so with the legitimate guard present an added
  `subprocess.run([sys.executable, os.environ['OTHER_SCRIPT']])` was admitted, and an inline
  `runpy.run_path(sys.argv[1])` handed an unrelated script was admitted and recorded as following
  the driver. Admission now requires that the program expression at that call IS a call of the
  entry's declared owner — `inventory.copied_member`, which returns a declared closure member
  inside a tree `checkout_copy` made **in this process** and refuses every other root and member.
  For a `python -c` program, the argv element the inline load reads is matched by index to the
  expression the site passed there. A site that runs its own `__file__` is admitted structurally,
  because the identity is the expression; a sibling named the same way is not.

## 4. What this record does not claim

The observer establishes that no mutation event under the copy was attributed to the copy and that
none was left unattributed, for the event kinds CPython audits. It is not a claim about a write that
CPython does not audit, nor about a child process this run did not start. The tree comparison
establishes that names, contents and the three metadata fields it reads are unchanged. Neither
establishes anything about attempts that failed; those are the events' own assertion.
