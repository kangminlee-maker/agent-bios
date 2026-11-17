---
created_at: 2026-11-02T16:19:00+09:00
head: 40d10ac
kind: design
supersedes: 2026-11-02T1516--9dadb8f--the-umbrella-runs-six-legs-at-a-time-and-four-suites-can-stop-at-their-first-failure.md
---

# Review round 1: every leg starts with its shell's environment, and the schema parse is kept by the file's text

The hermetic Codex review of the verify-speed package at `40d10ac` (round 1 of at most 2) returned
`fix_then_accept` with two major findings, both confirmed by the lead. The commit this record lands in answers
both; it changes `gates/run-legs.py`, `gates/check-parity.sh` and `session-distill/runlib/inventory.py`. What the
superseded record says about S1-S3 stands except where this one corrects it.

## #0: the runner handed its own environment to the legs

`gates/run-legs.py` started every leg with `subprocess.Popen` inheriting the runner's own environment. Python
changes its environment as it starts: under a C locale with no `LC_CTYPE` it sets `LC_CTYPE=C.UTF-8` (PEP 538),
and a macOS framework build adds its launcher variable. A leg started through the runner could therefore run
under a variable the umbrella's shell never exported, and the digest the runner compared (`export -p | cksum`,
taken in the shell) could not see it. Measured here under `LANG=C`: a `/bin/sh` leg that dumps its environment
received `LC_CTYPE=C.UTF-8` through the runner and not when run in place.

The superseded record said a recorded leg runs "under the exported environment of that moment", and so did
`run-legs.py`'s docstring and the umbrella's comment. That claim was as broad as this finding: it held for what
the shell exported and missed what the runner added.

- `legs_run` now writes the exported environment with `env -0`, which is not Python, to a file in the umbrella's
  temporary directory just before it starts the runner. The runner reads that file and starts every leg with
  exactly that environment, with `_` set as bash sets it for a command it runs; it reads `AGENT_BIOS_PARITY_JOBS`
  from it too. Each leg records a digest of `env -0` (sorted, below), and the runner compares that with the file's
  cksum, so a leg recorded under another environment is still refused by name.
- Four new controls in `run-legs.py --self-test` (23 -> 27; a fifth below): a variable only the runner carries
  does not reach a leg; a variable only the shell exported does; a cut snapshot is refused; and, through the
  umbrella's own leg block under `LANG=C` with no `LC_*`, a non-Python leg's environment through the runner equals
  the same dump taken in place, compared whole. With `env=` removed from the `Popen` call, the first two and the
  last fail by name, the last showing `LC_CTYPE=C.UTF-8` on the runner's side only.

### The first commit attempt: a reorder read as a change

The commit's first hook (16:19-16:24) refused the umbrella's first eight legs, "the exported environment changed
after this leg was recorded", and ran the other 82. Run directly in a clean clone (`bash .githooks/pre-commit`)
it did the same, and a dump of `env -0` at each leg's record showed why: the names and values were the same at
every leg and at the run; the ORDER was not. The first eight legs saw `PWD SHLVL OLDPWD _`, the ninth and the
run `OLDPWD PWD SHLVL _`. Between the eighth and the ninth leg stands the anchor loop, `while IFS='|' read -r
anchor fa fb`, and bash 3.2 rebuilds the environment it exports after a temporary assignment like that one,
moving OLDPWD to the front (reproduced alone in two lines). `export -p` lists the exported variables sorted by
name, so S1-S3's digest never saw the reorder, and nothing a leg received had changed.

- Both digests are now taken over the sorted entries: `env -0 | LC_ALL=C sort -z | cksum` at each leg's record,
  `LC_ALL=C sort -z <environ | cksum` at the run. A leg still starts with the snapshot as `env -0` wrote it; the
  order of an environment means nothing to the process that receives it.
- A fifth control, `a-leg-recorded-before-the-shell-reordered-its-exports-still-runs` (28 controls): in the
  umbrella's leg block, `cd .` gives the shell an OLDPWD, a leg is recorded, and `IFS='|' read` runs before the
  legs do; a presence term requires the exported order to have really changed. With both digests unsorted again
  it is the one control that fails.
- Why development did not see it: `run-legs.py --self-test` runs the umbrella's leg block with bodies of its own,
  and none put a temporary assignment between recording a leg and running it; the real umbrella's inline checks,
  where the anchor loop is, ran only in the hook. The umbrella measurement in real conditions that was left out
  after S2 was the run that would have shown it, and this round's commit was preceded by one, in a clean clone.
- The C-locale control printed the environment entries it found different, values included, in its failure
  detail. It prints their names only now.

## #1: the schema parse was kept by the file's stat

S2 kept inventory's schema parse while the file's inode, size, mtime and ctime were unchanged. A rewrite of the
same size within one tick of a coarse clock (HFS+ keeps whole seconds; ext4's timestamps follow a kernel tick)
leaves all four as they were, and the old vocabulary would have been answered. The key was the lead's proposal in
the S2 ruling, and the S2 control covered only a rewrite whose ctime moved.

- Two answers were measured over 243,000 calls in one process: reading the file and comparing its text with the
  text parsed, 6.0 s; a stat, 0.2 s; parsing each time, as before S2, 36.5 s. Reading and comparing was chosen:
  it is decidable without knowing the clock's resolution, which a racy-clean rule (re-read while the mtime is
  within one tick of the read) would have to assume. It gives back about 6 s of S2's gain.
- `schema_text(path)` holds what `inventory_schema` always did (the `SCHEMA_MISSING` refusal for a path that is
  not a file, then `read_text`); `inventory_schema` parses it, and `kept_schema_enum` reads it on every call and
  keeps the parse only while the text read is the text parsed. `schema_file_state` is gone.
- The control "a rewrite of the same size whose mtime is put back is read again, because its ctime moved" is
  replaced by "a rewrite of the same length whose every stat value is the one read is read again: the parse is
  kept by the file's text, never by its stat": every `os.stat` of the fixture file returns the result taken when
  it was read, so no clock is involved. Inventory's control count stays 1145.

## A control name held `[FAIL]`

One of S3's six controls in distill's suite was named "... with a non-zero exit, that failure's [FAIL] line and
no later one". Distill lists every passing control by name ("  control <name>"), so a harness that reads
`[FAIL]` lines read a passing run as holding a failure: the lead's audit at `40d10ac` recorded
`failing=['line and no later one']` for each rc=0 distill baseline, and `p2-revert.py` would count the line among
a distill row's other failures. The control is renamed "... with a non-zero exit, that failure's line and no
later one"; what it judges is unchanged, and distill still has 137 controls. A control name does not contain
`[FAIL]`.

The audit's verdicts did not change: the lead's parallel audit (`audit-parallel.py`, outside the repository)
judges a line by the suite's exit code alone (0 survived, otherwise killed), and its baseline by rc. The names are read in two places only, the
solo re-run when only load-sensitive controls failed (distill has none) and the "killed with no named failure"
report, which for distill's lines therefore always read empty.

## The package's closing audit, stop-first

The lead ran the parallel control audit at `40d10ac` with the stop mode on, six workers, over the four suites
(`lead/apar-vs-stop.log`, outside the repository): projection 11 of 11 checks have a control (15:23:06-15:23:13),
distill 8 of 8 (to 15:23:52), dispatch 78 of 78 (15:23:54-15:40:34), inventory 170 of 171 (15:40:35-16:14:07,
33.5 minutes; the same audit with the mode off at `c71af0e` took 2 hours 15 minutes). Inventory's one surviving
line is :3389, `confined`'s second `DESTINATION_ESCAPES` layer, which package A left without a control by
decision. Dispatch's report names four lines killed with no named failure, :907, :1143, :1471 and :1661: the
raises of `BUDGET_UNDECLARED`, `RESERVATION_MISSING`, `CAPACITY_UNDECLARED` and `RECEIPT_MISSING`. Without one of
those refusals the suite ends with a non-zero code by another path before it prints a `[FAIL]` line, and the
audit, like `gates/control-audit.py`, counts a non-zero exit as killed whatever the mode; whether a named control catches each of the four is a
separate question, outside this package. The state root: three lines changed, all under `sessions/` (snapshots
or app-context), written by a host session running at the time, not by the audit; nothing outside the host
session changed, and no temporary file was left.

## Pretrial and hook

The pretrial (`r1-revert.py`, outside the repository; disposable copies, six at a time, fake HOME, 16:15:11 to
16:18:16): `run-legs.py --self-test` (27 controls, 3.9 s) and `inventory.py --self-test` (1145 controls, 179.3 s)
pass unmutated, and each of seven faults planted in this round's code fails its named controls: `env=` removed
from the runner's `Popen` (three controls); a cut snapshot accepted; `env -0` replaced by an empty file (the
C-locale control among three); the per-leg digest put back to `export -p | cksum` (every umbrella leg refused);
S2's stat key restored (the pinned-stat control); the text comparison dropped (two controls); a missing file
answered from the kept text (one). No temporary file was left. After the rename, distill's suite passes with 137
controls and prints no `[FAIL]` line. After the sorted digest, a second pass over the runner alone
(`r1b-revert.py`): `run-legs.py --self-test` passes with 28 controls, and five faults each fail their named
controls (the digests unsorted again, the per-leg digest back to `export -p`, `env=` removed, a cut snapshot
accepted, an empty dump). Then the hook's own run, in a clean clone with these files staged (`bash
.githooks/pre-commit`, real HOME and venv, 16:33:15-16:37:39): 264 s, 90 legs declared, 90 run, 0 failed, the
longest the inventory self-test (183 s). The hook's figures are added to the claims after the commit.
