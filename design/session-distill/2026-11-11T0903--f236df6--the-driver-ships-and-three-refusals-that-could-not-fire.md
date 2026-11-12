---
created_at: 2026-11-11T09:03:00+09:00
head: f236df6          # the commit the content was true at
kind: design
supersedes: (none — WP-24 has no earlier record)
---

# WP-24, the driver ships: what it took, and three refusals that could not fire

The session-distill driver was author-side machinery. After this package it is runtime
payload: a private install stores it, and `python3 session-distill/distill.py --self-test`
runs from the installed location. Five commits on `wp/24-ship-driver`, from `3843795`.

| Commit | What it settled |
| --- | --- |
| `cf94778` | the gate reader moved into a shipped module (`runlib/gitread.py`); the fourth payload direction |
| `1ba49fb` | the ledger's path became a parameter; its checkout-only inputs are injected by an author-side caller |
| `b9b2576` | the default run root is the XDG state directory's |
| `0717b3c` | every runtime dependency declared with the version it was measured at |
| `f236df6` | `session-distill/` in `files[]`, file by file; three refusals repaired |

## The payload boundary gained a fourth direction

`gates/check-package.sh` asked three questions of `files[]`. The fourth: **a shipped `.py`
may not name an author-side `*.py` as a string constant.** The code works in every clone
and raises on the first packaged user, which is the same failure shape as an unshipped
runtime path, one layer out.

Scope includes `self_test` bodies, deliberately: a self-test that imports a path the user
lacks is a crash the user meets if they ever run it. Exemptions are keyed by
`(file, path)` with a reason each, and a stale one fails. Six now — the two the direction
started with (`dispatch.py` naming `benchmarks/tier/live.py` as a path its closure may NOT
load; `gate.py` reading `benchmarks/absence.py` as source rather than importing it) and
four for `dispatch.py`'s closure inventory, which names the v1 curator stages and the
ledger migrator as declaration DATA (`OUT_OF_SCOPE`, `SCRIPT_RUNS`, `PROGRAMS`). Naming
them is how those rules are stated; nothing loads them at runtime.

One trap, for the next person writing a planted-violation case in that gate: **a heredoc
that plants a literal contains that literal itself.** Three attempts failed because
`sub <file> <needle>` found its own argument text, and a forward `t.index("AUTHOR_IMPORT_EXEMPT = {")`
matched the heredoc's own line rather than the table. The working form searches backwards
(`t.rfind(...)`) and guards that the hit lies after the table's own opening.

## Three refusals that existed and could not fire

Each was found by a gate or a test that had never scanned these files, because `files[]`
had never named them. All three are repaired in `f236df6`, each with a control.

1. **`compose/instructions_install.py`: the author-side trees were never refused by their
   directory entry.** `_relative` strips a trailing slash, so `"gates/"` arrived as
   `"gates"` and `startswith("gates/")` was false. The refusal fired only for an entry
   naming a file INSIDE such a tree — never for the entry that packs the whole tree, which
   is the shape npm actually uses. Compared on the first path segment now.
2. **The author's compiled bytecode was payload.** A directory entry expands to every file
   under it and `.pyc` is a file, so a release carried whatever `__pycache__` the author's
   checkout held — and `runlib/` is run from the checkout constantly. Skipped when
   expanding, matching `.npmignore`. A stale `.pyc` shadowing its own source is a trap this
   repo has already paid for once.
3. **`gates/check-endpoints.py` counted local bytecode as shipped.** It derives subjects
   from the worktree rather than from git, so `runlib/__pycache__/*.pyc` were scanned as
   shipped prose and reported URLs read out of compiled constants. The second-order damage
   is the reason it matters: the `urls` leg then failed inside EVERY mutated copy, so
   fourteen of that gate's own planted violations stopped proving what they declare and
   said so only as "caught by anchors, urls but declares no reach".

## What shipped, and what did not

Named file by file, not as a directory. The whole tree carries 221 tracked files, of which
163 are author-side: 146 fixtures whose `PROVENANCE` rows hold the author's probe paths,
two regenerable v1 snapshots, twelve v1 curator stages, the ledger migrator and `REPIN.md`.
Measured with `files[]` naming the directory: 78 content-hygiene violations over 443 shipped
files. With the intended set: 11, all in two files, all fixed here.

`AUTHOR_SIDE_DIRS` declares `session-distill/fixtures/` and `session-distill/out/`;
`AUTHOR_SIDE_FILES` declares the fourteen author-side files by name.

The owner's home had been written into two shipped suites: `runlib/projection.py` passed it
as the `home` argument of the masking rule at ten sites, and `runlib/views.py`'s capture
sweep listed it as a literal. The masking rule is shape-based, so a declared fixture owner
exercises it identically; the sweep asks for `str(pathlib.Path.home())`, which also makes it
correct on a machine that is not this one.

## The default run root

`${XDG_STATE_HOME:-~/.local/state}/agent-bios/distill/runs/<run-id>`
(`distill.py::default_out`, decision D-20261111-b50a81). Not the package, which an install
replaces and a packaged user may not have; not the owner's state root, which
`inventory.protected_roots` refuses to write into; the XDG **state** directory rather than
the data directory, because a run is regenerable output while the data directory holds what
is the owner's — pins, receipts, the ledger.

The protection is unchanged. Carving the run directory out of it would turn "the owner's is
protected" into "some of it is not", and R1#1 — a run writing four artifacts under the
owner's state root — is why that sentence exists. The checkout keeps passing
`session-distill/out/<run-id>` explicitly.

## The installed self-test, and what a packaged user cannot run

`distill.py --self-test` is **already** fixture-free and author-side-free: OK (144 controls)
in a tree with `fixtures/` and `out/` deleted, in a shipped-shape tree with the author-side
trees deleted, and from the installed release directory after
`bash install.sh install --non-interactive`. There is nothing in it to skip, so no skip
registry was built (lead decision): a mechanism whose subject set is empty is a check that
cannot fire.

What a packaged user cannot run is the `runlib` module suites, which are the checkout's own
tooling rather than the driver's self-test. Measured in a shipped-shape tree: 20 of 29 pass,
9 fail in three classes.

- **Five crash on a missing `fixtures/` tree** with a raw `FileNotFoundError` rather than a
  named skip: `breaker.py`, `dispatch.py`, `gate.py`, `monitor.py`, `views.py`. There is no
  single fixture-root helper to make refuse by name — there are three roots:
  `gate.py:998 FIXTURES` (also read by `dispatch.py`'s suite), `views.py:147 CAPTURES`, and
  inline recomputations in `breaker.py:277` and `monitor.py:887`/`:1111`. Two of those files
  are in lane E's active set, so a shared helper refusing `FIXTURES_ABSENT <path>` is a
  one-line item for lane E after their branch integrates, not work for this package.
- **Two fail on a missing author-side `design/` record**, and both are SELF-TEST ONLY, which
  is why they are not a shipped defect: `declare.py`'s
  `posture-is-authorized-by-a-named-addendum-that-exists` sits inside `self_test`, and
  `ledger.py`'s `ADDENDUM_SILENT` comes from `addendum_problems`, whose only callers are its
  own `self_test`. Nothing at runtime asks whether the record a schema's `$comment` cites
  exists on disk.
- **Two depend on the shipping set itself** (`census.py`'s documented handoff to the v1
  `digest.py`; `records.py`'s site census over every module of `session-distill`).

## The ledger's path, and one transitional shape

`runlib/ledger.py` no longer knows a checkout path. `ledger_path(state_root, override)`
resolves the override, then the state root's own `distill/ledger.json`, then **None** — and
a comparison that needs the migration and was given none answers `MIGRATOR_UNAVAILABLE`
rather than migrating silently. The author-side `gates/check-ledger.py` owns the checkout's
`design/session-distill/ledger.json` and injects it.

`LEDGER_REL = STATE_LEDGER_REL` remains as an alias because `runlib/stage_read.py` still
reads it (lines 200, 204, 3798), and that file is lane E's. **This is a transitional shape:
the alias goes when lane E's branch integrates**, and the three references are routed to
them as a one-line item.

## Dependencies, derived rather than recalled

`DEPENDENCIES.md` now names the driver as a consumer of `python3` (3.14.7 measured today),
`git` (2.50.1, for `git show <rev>:<path>`), `jsonschema` (4.26.0, equal to `JSONSCHEMA_PIN`),
Claude Code and Codex CLI — and carries a **new row for `zstd`** (1.5.7), which had no row
anywhere although the driver reads compressed captures and refuses `ZSTD_UNAVAILABLE`
without it.

`gates/check-driver-dependencies.py` holds this against the code from now on: every
third-party import of `distill.py` and `runlib/*.py`, and every command name given as a
string literal to a `subprocess`/`shutil` runner, must be declared in a `DEPENDENCIES.md`
row. The import half is complete; the program half is deliberately not, because the host
CLIs arrive as resolved paths from configuration and no scan can see them — their
declarations stay with review, and the gate says so rather than claiming completeness.

## The guide, named as an exclusion

`claude/guides/session-distill-workflow.md` keeps `audience: author` and
`Requires an agent-bios checkout`, so `compose/assemble.py::author_only` goes on withholding
it (lead decision D-20261111-568aed). **The driver therefore ships in this package without a
user guide.** The condition on that exclusion: WP-22 delivers the S0–S12 user guide before
release 1's release commit. All 184 lines of the current file are the author-side v1 mining
runbook, so there was no user-facing half to split out.

## Rejected

**One rule instead of nineteen exemptions in the endpoint gate** — treating every RFC 2606 /
RFC 6761 reserved name as a fixture host (D-20261111-df9014). Implemented, measured, reverted:
it turned three of `check-endpoints.py`'s negative controls green immediately, and the
remaining six plants use the same `collector.example.com`, so the gate's self-test would have
stopped proving what it declares. A change that makes negative controls pass is the one shape
this repo refuses.

**Carving the run directory out of `protected_roots`**, and **shipping no default run root at
all** (both closed in D-20261111-b50a81).

## Numbers, and how to re-derive them

Every figure here was measured on the commit named beside it; re-measure rather than quote.

| Figure | Command |
| --- | --- |
| 59 driver files in a private release | `bash install.sh install --non-interactive` into a scratch HOME, then count `<state>/runtime/releases/<digest>/session-distill` |
| 144 controls, installed | `python3 session-distill/distill.py --self-test` from that release directory |
| 11 vs 78 hygiene violations | `files[]` with the intended set vs the directory, then `python3 gates/check-hygiene.py` |
| 20 of 29 module suites | each `python3 session-distill/runlib/<name>.py --self-test` in a tree without the author-side trees |
| the driver's dependencies | `python3 gates/check-driver-dependencies.py` |
