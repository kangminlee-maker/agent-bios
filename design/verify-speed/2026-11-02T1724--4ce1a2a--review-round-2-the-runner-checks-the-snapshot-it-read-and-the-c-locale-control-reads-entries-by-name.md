---
created_at: 2026-11-02T17:24:00+09:00
head: 4ce1a2a
kind: design
supersedes: 2026-11-02T1619--40d10ac--review-round-1-legs-start-with-the-shells-environment-and-the-schema-parse-is-kept-by-its-text.md
---

# Review round 2: the runner checks the snapshot it read, and the C-locale control reads entries by name

The hermetic Codex review of the verify-speed package at `4ce1a2a` (round 2, 17:01-17:15) returned
`fix_then_accept`. Both round-1 findings are closed: the review judged round 1's fixes and their controls met,
each control failing when its fix alone was reverted, and the schema memo met. Two findings remain, both in
`gates/run-legs.py`, both confirmed by the lead. This was the last round the owner's cap of two allows: there
is no round 3, and the lead checks this commit against the implementer's claims before the merge. What the
superseded records say about S1-S3 and round 1 stands except where this one corrects it.

## #0 (major): the snapshot's bytes were not held to the shell's digest

`legs_run` writes the exported environment with `env -0`, takes `LC_ALL=C sort -z <environ | cksum`, and
passes that digest with the file to the runner. The runner compared the digest only with each leg's recorded
digest, never with the bytes it read from the file. A file cut at an entry boundary after the shell's digest (a
full disk, another writer) still parses, so every leg would start without the variables it lost while the
digests agreed. The review's probe kept the whole file's digest and dropped trailing entries holding
`MUST_FAIL=1`: the whole snapshot gave exit 1, the cut one exit 0 with "1 declared, 1 run, 0 failed". The cut-
snapshot control covered only a file whose last entry had lost its NUL.

- The runner takes the digest of the bytes it read, by the shell's own commands (`/bin/sh -c "LC_ALL=C sort -z
  | cksum"`, those bytes on its input), and compares it with the shell's before it parses the snapshot and before
  any leg starts. A snapshot whose digest is not the shell's is refused with exit 2: "FAIL: leg runner: the
  environment snapshot read is not the one the shell took its digest of (digest ..., the shell's ...), so no leg
  ran". The leg's own comparison stays as it was.
- Two controls (30 in all). Both keep the shell's digest of a whole snapshot that ends in
  `PLANTED_MUST_FAIL=1`, under a leg that fails while that variable is exported: the snapshot cut at the entry
  boundary before it is refused and the leg does not run, and a positive term requires the whole snapshot to fail
  the leg, so what the cut removed is shown to matter; an empty file is refused the same way.
- The self-test's runs passed a placeholder digest ("E") to the runner and to each leg they recorded. They now
  pass the digest of the snapshot they write, taken as `legs_run` takes it, so every control goes through the
  new check.

## #1 (minor): the C-locale control split a multi-line value into variables

Round 1's control compared a non-Python leg's environment through the runner with the same dump taken in place,
from `env` output split on newlines, and required no line to start with `LC_CTYPE=`. A variable whose value holds
such a line (`first\nLC_CTYPE=fixture`) made that line look like a variable: with both environments equal, the
control failed, and the umbrella would have failed with it under an owner's shell holding such a value.

- Both dumps are taken with `env -0`, split on NUL, compared as entries, and `LC_CTYPE` is judged by variable
  name. The control's environment carries `PLANTED_MULTILINE=first\nLC_CTYPE=fixture`, and a term requires that
  entry, whole, among those the leg received through the runner. Its failure detail still prints names only.

## Pretrial

`r2-revert.py` (outside the repository; disposable copies, three at a time, fake HOME, 17:22:06-17:22:27):
`run-legs.py --self-test` passes unmutated with 30 controls, and each of eight planted faults fails its named
controls, leaving no temporary file. The three new rows: the digest check made a no-op (both new controls); the
runner's digest taken unsorted (28 controls, every run refused); the C-locale control judging lines again (that
control). The five rows of round 1's second pass, run again because every control now passes the snapshot's real
digest: `env=` removed from the runner's `Popen` (four controls, the cut-snapshot control's positive term among
them); a cut snapshot accepted; an empty dump from the shell; the per-leg digest back to `export -p`; both
digests unsorted.

Then the hook's own run, in a clean clone at `4ce1a2a` with this commit's code and this record (without this
paragraph) staged (`bash .githooks/pre-commit`, real HOME and venv, 17:23:45-17:28:55): 310 s, 90 legs
declared, 90 run, 0 failed, the longest the inventory self-test (212 s). The hook's figures are added to the
claims after the commit.
