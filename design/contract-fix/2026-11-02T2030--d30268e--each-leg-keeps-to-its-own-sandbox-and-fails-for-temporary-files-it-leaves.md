---
created_at: 2026-11-02T20:30:00+09:00
head: d30268e
kind: design
---

# Contract fix, commit 1: the umbrella's legs keep to their own sandboxes, and a leg that leaves temporary files fails by name

This record lands with the first commit of the contract-fix package (owner, 2026-11-02: the package goes before
WP-08; scope from D-20261026-7fce2a and D-20261102-2f0d43). The commit holds the umbrella-leg hygiene items G-1,
G-2, G-3, G-4, G-6, G-7 and G-8 that verify-speed's probes found. G-5 is closed without a change
(D-20261102-ddfc25): a local clone hardlinks the loose objects, which moves their link count and change time and
writes no object. Every change is author-side except two self-tests that live in shipped files
(`learn/collect-learning.py`, `learn/migrate-learnings.py`): their `--self-test` paths now remove their scratch
directories, and no user path changes. `head` is the base the figures below were measured on, with this commit's
changes laid on it.

The commit also carries the nine decisions the lead recorded for this package on 2026-11-02: the owner's
D-20261102-d8310f (F-30), -29ca35 (F-26), -49b466 (F-29) and -6b6676 (F-31), and the lead's -16af2f (F-23),
-fcbcd5 (F-25), -0048bd (F-27), -967506 (F-28) and -ddfc25 (G-5). Implementing them is later work in this package.

## G-1: the learn probes no longer inherit the caller's AGENT_BIOS_* or CODEX_HOME

`gates/check-endpoints.py`'s wire leg started the shipped `install.sh learn` at two sites with a copy of its own
environment whole, plus HOME and CLAUDE_CONFIG_DIR. An inherited `AGENT_BIOS_CORPUS_DIR` (or `_INSTRUCTIONS_DIR`,
`_STATE_DIR`) pointed `learn` at the caller's own queue, and an inherited `CODEX_HOME` sent the Codex run past the
decoy planted for it. Both sites now take `probe_environ(home, config_home)`: the process's environment minus every
`AGENT_BIOS_*` and `CODEX_HOME`, with HOME and both hosts' config homes in the probe's scratch tree.

Control (end of the self-test): four of those variables are planted in the process environment, pointing at
directories that do not exist; the wire leg runs through the real call sites with `subprocess.run` recording the
environment of each `learn` it starts. It requires three `learn` runs (the dispatch and the two zero-egress hosts),
none carrying a planted value, none of the planted directories created, and no wire problem. Revert rows: site 1
back to the whole environment, site 2 the same, `AGENT_BIOS_*` kept, `CODEX_HOME` kept; each fails this control
by name.

## G-2: check-publish's npm runs with its own home, cache and temp directory

`gates/check-publish.sh --self-test` ran `npm` (through the stamp and the guard) with the caller's HOME and TMPDIR,
so each run wrote `~/.npm` and a `node-compile-cache` into the caller's temp directory. `cleangit`, which every
command in the self-test's clone goes through, now also sets HOME, `npm_config_cache` and TMPDIR inside the
self-test's own temp directory, which its EXIT trap removes.

Control: with two empty directories planted as the caller's HOME and TMPDIR, a stamp leaves both empty and npm
writes its cache into the self-test's own home (22 -> 23 OK lines). Revert rows: HOME, cache and TMPDIR dropped,
and TMPDIR alone dropped; each fails the control by name, the second naming `planted-tmp/node-compile-cache`.

## G-3: `claude plugin validate` runs with a sandbox home

`compose/test_instructions_catalog.py`'s native-plugin test ran the real `claude plugin validate` under the
caller's HOME and config dir, which wrote `.claude.json` and its backups there. It now runs with HOME and
`CLAUDE_CONFIG_DIR` in the test's temporary directory, while the caller's HOME and config dir are planted as two
empty directories that must stay empty. Revert row: the validator's `env=` dropped; the test fails with "the
validator wrote into the caller's HOME or config dir".

## G-4: no leg writes into the source tree, so no leg runs alone

Two legs wrote into the source tree while other legs read it, and so ran alone before the rest (`-a`):

- `gates/test-install-guides.sh` scenario I13 planted `gate-i13-probe.md` in `claude/skills/<skill>/` for one
  install. It now copies the source tree (without `.git` and `__pycache__`) under its own temp directory, plants
  there, and runs both I13 installs from the copy (`run_install_from`). A new check, "I13 the plant is outside the
  source tree the umbrella's other legs read", fails when the plant path is under `$REPO`.
- `session-distill/runlib/bound.py --self-test` wrote `__bound_selftest_*.md` beside itself. Its two BB#1/BC#1
  controls now write into a scratch directory removed at the end (`shutil` and `tempfile` imported inside the
  self-test, since the module's purity check forbids reaching outside it), and a new expectation requires both
  paths to lie outside the module's directory.

Both `-a` marks are gone from `gates/check-parity.sh`; the install scenarios are marked `-e` (a long leg, started
first). `gates/run-legs.py` keeps the `-a` mechanism and its control. Revert rows: the plant back in `$REPO`, and
bound's files back beside the module; each fails its new check by name.

## G-6: each leg has a TMPDIR of its own, and leaving anything there fails it

An umbrella run left about 120 entries in the TMPDIR it started with, and nothing said whose. The structural
control (approved by the lead, blocking): `gates/run-legs.py` gives each leg a TMPDIR of its own, `mkdtemp(prefix=
"pt")` inside the TMPDIR the umbrella exported, set after the recorded digest is compared, so the digests remain
those of what the shell exported. When the leg ends the runner lists that directory, writes "leg runner: it left N
entries in its TMPDIR: <up to five names>" into the leg's output, removes the directory, and fails a leg that
exited 0 with "left N in its TMPDIR". The runner's captures and a logged leg's log stay in the umbrella's TMPDIR.
The short prefix keeps socket paths short: a leg's TMPDIR grows by 11 bytes.

Controls (`run-legs --self-test` 30 -> 32): two legs each see a distinct TMPDIR, a direct child of the umbrella's,
gone after the run; a leg that leaves a file and a directory fails naming both, its neighbour passes, and the
umbrella's TMPDIR ends empty. The C-locale control compares the environment through the runner with the one in
place minus TMPDIR, the one declared difference, and asserts that the leg's TMPDIR is a child of the shell's.
Revert rows: the leftover check removed, the per-leg TMPDIR removed, and the per-leg directory kept; each fails
by name.

Fixed at the legs that left entries (found by the stage-0 inventory and by the dev runs):

- `gates/test-install-guides.sh`: the egress probe's `egress-ctl-*` home is made under the suite's `$T`; every
  install runs with `TMPDIR=$T/tmp`, because `install.sh` keeps a failed step's log in TMPDIR for the operator
  and this suite plants failures.
- `session-distill/runlib/stop.py`: the fake `ps` directory `stop-ps-*` is removed after its last use.
- `session-distill/runlib/coverage.py`: the refused write goes into a `TemporaryDirectory`.
- `learn/migrate-learnings.py --self-test`: all scratch homes (sixteen per run) are made in one root, removed at
  exit; `learn/collect-learning.py --self-test` also removes its scratch at exit, so a run that raises (the
  seam-coverage gate runs it on mutated copies) leaves nothing.
- `gates/check_parity.py`: `main` points TMPDIR, for the process and every program it starts, at one root it
  removes at the end. About ninety bare `mkdtemp()` sites in its checks and drivers left their directories; one
  root covers them rather than ninety edits, so a new leak inside this leg is removed, not named.
- `gates/compose-tests.py`: `NODE_DISABLE_COMPILE_CACHE=1`, so the node-based CLIs the tests run leave no compile
  cache in TMPDIR.
- `gates/check-publish.sh`: TMPDIR inside its own temp directory (G-2).

What this control does not see: the umbrella's inline blocks and its venv provisioning run in the main shell with
the original TMPDIR, so they were checked once by counting that TMPDIR before and after a clean-clone run (below);
and a program that writes to `/tmp` or another fixed path rather than through TMPDIR is outside it. `install.sh`'s
own `mktemp -t` sites (F-23, D-20261102-16af2f) are shipped behaviour and stay for a later commit; this suite
only keeps what they leave inside its sandbox.

## G-7: REACH reads heredocs only in a line's code, and never `<<<`

`gates/check-parity.sh`'s REACH block opened a heredoc on any `<<WORD` in a line, comments and here-strings
included, and a heredoc swallowed every later line, so the legs after it read as never reached. Heredoc detection
now runs on `sans_comment(s)` and requires `<<` not adjacent to another `<`. Three probes: a `<<EOF` inside a
comment and a `<<< word` inside a comment open nothing, and a live `<<<"$v"` leaves the next command reached.
Revert rows: full revert, comment stripping only, here-string exclusion only; each fails the probe it covers.

## G-8: a refusal that stops refusing fails its own control

`dispatch.py`'s self-test helper `refusal` caught only `Refused` and `Deferred`. With any of four refusals
neutered (`BUDGET_UNDECLARED`, `RESERVATION_MISSING`, `CAPACITY_UNDECLARED`, `RECEIPT_MISSING`) the next line
raised a TypeError or IndexError, and the suite ended on a traceback with no line naming the control. `refusal`
now returns any other exception as `UNEXPECTED <type>: <text>`, which no expected refusal starts with, so that
control fails by its own name. A new control plants a KeyError; the BC#0 lock-timeout control, whose escape now
reads as UNEXPECTED, checks for it there (522 -> 523 controls). Revert rows: each of the four raises neutered, and
the new `except` removed; each fails the named control. After the CAPACITY_UNDECLARED control fails, the
suite's next `reserve`, outside any `refusal`, is refused (CALIBRATION_SERIAL) because the neutered call left
its calibration reservation open; the boundary prints the failures collected so far, the named one first, and
the suite ends there.

## Verification

- Development runs (fake HOME, a fresh short TMPDIR each, no `-B`): every touched suite passed and left its TMPDIR
  empty; the umbrella in the worktree, fake HOME with the real launcher venv, rc=0 in 191 s, 90 legs declared and
  run, 0 failed, its TMPDIR empty at the end.
- Pretrial (`work/impl/cfix/c1-revert.py`, each run in a disposable copy committed into a fresh repository, six at
  a time, fake HOME, a fresh TMPDIR per run): the 20 revert rows above each failed with their expected text, and
  18 unmutated suites passed with their TMPDIRs empty. Three rows are noted. The G-1 site-1 row first ran with the
  fake HOME's own `AGENT_BIOS_*` inherited, which reached the reverted probe before the planted ones, and the
  suite's own positive control failed first; the four G-1 rows were run again with no `AGENT_BIOS_*` inherited,
  the umbrella's usual condition, and each failed the new control by name. The two G-2 rows left a
  `node-compile-cache` in the harness's TMPDIR, the reverted fault's own trace.
- Real conditions (2026-11-02, a clean clone of the worktree, the real HOME and venv, a fresh TMPDIR, run one
  after the other): `d30268e` rc=0 in 260 s and left 113 entries in its TMPDIR; `d30268e` with this commit's
  changes rc=0 in 192 s and left none, the inline blocks included (the venv existed, so it was not provisioned).
  Both: 90 legs declared and run, 0 failed; `git status` of the clone the same before and after. The difference, 68 s,
  matches the install scenarios' time as a leg (70-81 s), no longer spent before the other legs start; the
  second run had the higher load (5.8-7.6 against 2.9-5.8).
