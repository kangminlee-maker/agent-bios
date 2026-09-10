# AGENTS.md — working rules for developing this repo

**This repo's product is agent instructions. Do not confuse the product with your
instructions.** `claude/CLAUDE.md`, `codex/AGENTS.md`, `claude/guides/`,
`codex/guides/`, and all of `ko/` are **payload** — content deployed to other
machines (`install.sh` `assemble_corpus`, `deploy_glob`, `deploy_tree`; the set is
`package.json` `files[]`). Editing them changes what ships, not how you work here.
How you work here is this file.

English, matching `README.md` and `LEXICON.md`. Every rule names the code that
enforces it: **ENFORCED** = a gate fails on violation, **CONVENTION** = no gate
exists, only review catches it. Re-derive any rule from the named file before
treating it as authority.

## What goes where

| Kind | Home |
| --- | --- |
| How to work in this repo | **`AGENTS.md`** (this file), imported by root `CLAUDE.md` |
| What the system is and how it is shaped | **`README.md`** — user-facing, and gate-bound |
| Terminology, concept homes | **`ontology/instances/graph.json`** §lexicon — `LEXICON.md` is **generated** from it by `ontology/emit-lexicon.py` (`--check` fails a hand edit) and read by `gates/check-lexicon.py` |
| Where knowledge and tools reach a model, and what each place admits | **`SURFACES.md`** — held against the code by `gates/check-surfaces.py` |
| The network operations agent-bios speaks, and the zero-egress default | **`ENDPOINTS.md`** — held against the code by `gates/check-endpoints.py` |
| Open product-defect queue between review rounds | **`FINDINGS.md`** — closing an entry means deleting it (a resolution marker fails `gates/check-lexicon.py`) |
| External tools, host CLIs, verified versions | **`DEPENDENCIES.md`** |
| Current structure dashboard | **`IMPLEMENTATION_MAP.html`** |
| What was decided here, and what it closed | **`decisions/decisions.jsonl`** via `decisions/record-decision.py` |
| Dated records — handoffs, round records, superseded designs | **`design/archive/`** — never edited after the day they describe, and no runtime file may point into it |
| Work in flight — a design that must stay current until it lands | **`design/<initiative>/`** (isolated) |
| Regenerable pipeline snapshots | **`session-distill/out/`** |
| Deployed instruction text | **`claude/`**, **`codex/`**, **`ko/`** — payload, not docs; `claude/skills/` is one tree for both hosts, not mirrored |
| Shipped machinery outside the corpus | **`learn/`** (capture flow, five files ship), **`wrappers/`**, **`compose/`** (four scripts ship), **`launch/`**, `session-cost.py` |
| Author-side only, never shipped | **`gates/`**, **`ontology/`**, **`decisions/`**, **`design/`**, **`research/`**, **`benchmarks/`**, **`packages/`**, **`session-distill/`** — `gates/check-package.sh` holds the boundary |

## 1. Active files describe the present — CONVENTION, partly enforced

Code, `README.md`, `LEXICON.md`, and this file state current behavior, current
contracts, current failure handling. Change narratives, rejected alternatives,
migration rationale, and handoff logs live in `design/`.

This is already half-mechanical: `gates/check-lexicon.py` carries an archive
allowlist (`ARCHIVE`) precisely because a dated snapshot keeps the words
as written at the time. Read it before assuming coverage — it names **individual
paths**, not `design/` wholesale, so a new file under `design/` is scanned like
any live file and a deprecated token in it fails. Live files get no exemption at
all.

The reason is misreading, not tidiness — a past-tense sentence sitting next to
current code reads as a present fact to both people and models.

## 2. Dated records are written once, not edited — CONVENTION (new)

`design/session-distill/HANDOFF.md` announced itself as the single source of
truth while reporting the ledger as 74 entries in one place and 78 in another;
the artifact held 83. It was stale, self-inconsistent, and still told you to read
it first. That is fixed — the figures now carry their dates and the header gives
the command that re-derives current state — so treat this as the reason for the
rule, not as a live defect.

That is what a continuously overwritten "current state" file decays into: it
claims to be now, and is no particular time. A file whose name carries its
timestamp cannot rot, because its age is on the label.

For new records under `design/`, write a new file rather than editing a prior
one, and carry the point in time in the file:

```
design/<initiative>/<YYYY-MM-DD>T<HHMM>--<short-sha>--<slug>.md
```

```yaml
---
created_at: 2026-08-04T14:20:00+09:00
head: 6541703          # the commit the content was true at
kind: handoff | design | review | backlog
supersedes: <previous snapshot filename>
---
```

Existing `HANDOFF.md` / `DESIGN.md` files are not retroactively split — they are
themselves history. Numbers in them are claims about a past tree; re-derive from
the artifact (`ledger.json`, the code) before acting on any of them.

## 3. The gates run before every commit — ENFORCED once per clone, CONVENTION until then

Once per clone:

```bash
git config core.hooksPath .githooks
```

`.githooks/pre-commit` runs `gates/check-package.sh` and `gates/check-parity.sh`
and aborts the commit on failure. Budget **minutes, not seconds** — on the author's
machine the umbrella runs ~4.5 minutes (2026-08-31) — 267s, of which the install
scenarios in `gates/test-install-guides.sh` are 42s and the umbrella's own other legs
are the remaining ~217s; measure with `time`, and never
`pkill -f check-parity` while a commit runs, because that kills your own commit.

That figure was **50m26s** until 2026-08-31, and the cause was not the scenarios.
Each of the suite's twelve `install`/`verify` runs ends in `install.sh`'s `cmd_verify`,
which re-ran this umbrella on the tree the umbrella was already judging — the suite sets
`REPO="$PWD"` and writes only into a sandbox HOME, so all twelve re-derived one unchanged
answer, 3m37s each, 86% of a commit, and no assertion in the suite read the result.
`cmd_verify` now skips the parity gate under `AGENT_BIOS_IN_INSTALL_TEST`, announcing the
skip; the payload and prompting-target gates keep running there because at 0.16s together
they buy back nothing and their running is what proves verify still wires its gates up.
Re-measure before quoting either number — this one has been wrong by 4× before.

The scenarios themselves are a deliberate trade: they are the only check that
exercises the branch a default `agent-bios install` actually takes, and the defect
they now guard was invisible to every other gate in this repo. The hook lives in
the repo rather than
`.git/hooks` so the rule travels with the code instead of with one laptop — the
`git config` line above is the only part each clone must do by hand, and until it
is run, nothing is enforced.

**The gates run against a snapshot of the index, not your working tree and not the
live index.** Git commits the index, so a gate that reads the checkout judges
something else entirely: staging a bad file and restoring it on disk used to commit
clean. The hook copies the index once, up front, and derives everything from that
copy — the tree it materialises into a temp directory, the staged-file count, and the
`GIT_INDEX_FILE` the git-reading legs inherit — with `GIT_DIR`/`GIT_WORK_TREE`
pointing them at the same state. The copy is what makes a second session in the same
checkout survivable: the live index is shared, and a `git add` landing mid-run used to
give the legs a path list with no bytes behind it. Nothing is stashed, so an
interrupted hook cannot leave the repo mid-surgery. If gate output disagrees with what
you see on disk, the difference is unstaged.

**A commit whose index moved while the gates ran is refused.** The snapshot keeps each
gate self-consistent but cannot change what git commits — git re-reads the live index
to build the commit — so the hook compares the tree afterwards and fails by name when
it differs. A tree hash is decidable, which is why this one blocks. Coordinate index
writes with any parallel session rather than racing them.

There is no CI (`.github/` absent) and no npm test script, so this hook is the
only automatic enforcement in the repo. Run the umbrella directly any time with
`./gates/check-parity.sh`.

It is an umbrella — the mirror generator's `--check`, the domain manifest gate,
the assembler scenario suite, the payload gate's self-test, the learning-record
and redaction gates, the promotion-manifest staleness check, the decision-record
self-test, the lexicon gate, the content-hygiene gate (the shipped distribution
carries no org or personal binding outside `(private)`-marked lines or per-reason
exemptions), the endpoint-contract gate (`ENDPOINTS.md`'s wire literals against the
code, and the zero-egress default against the real transport resolver), and the
review-routing golden (which pins the
rendered review contract byte-for-byte across every setup/host/family
combination), each with its own `--self-test` negative control. Line numbers are
omitted deliberately: they were wrong within a day of being written.

| Check | Character |
| --- | --- |
| Codex/ko-codex trees diverge from their projection | blocking — a generator diff is decidable |
| Deprecated terminology token as a live identifier | blocking — token presence is decidable |
| Machinery file outside its declared concept home | blocking — a path prefix is decidable |
| Runtime path missing from the npm payload | blocking — derived from real references |
| Launch config binds a model no prompting guide covers | blocking — a set comparison |
| A decision record that closes no alternative | blocking — an empty list is decidable |
| Whether a rule earns its place in the deployed global | not gated — a person decides |
| Whether a number in a guide is still true | not gated — re-measure |

Blocking is for deterministically decidable violations only. Gate a judgment
call and people learn to route around the gate.

After deploying, `./install.sh verify` re-runs `check-package.sh`,
`check-parity.sh`, and `check-prompting-targets.sh` (`install.sh` `cmd_verify`).
Publishing is gated separately: `npm prepack` runs `gates/check-publish.sh --stamp`
and `prepublishOnly` runs `--guard` (`package.json` `scripts`), refusing a dirty or
unreachable HEAD and stamping `provenance.json` with the commit the tarball carries.

## 4. Never hand-edit `codex/` or `ko/codex/` — ENFORCED

They are generated projections of `claude/` and `ko/claude/`
(`gates/emit-mirrors.py` `TREES`), differing only in config-home variable and title,
plus one pinned Codex-only authorization bullet. `claude/skills/` is not projected —
one tree serves both hosts (`install.sh` `deploy_tree`). Edit order:

1. Edit `claude/` — and `ko/claude/` when the change is user-facing.
2. `python3 gates/emit-mirrors.py`
3. `./gates/check-parity.sh`

`check-parity.sh` compares against what the generator would emit (`emit-mirrors.py
--check`), so any hand edit to the Codex side fails.

## 5. Terminology comes from the ontology's lexicon block — ENFORCED

`LEXICON.md` is itself a projection: its four tables come from
`ontology/instances/graph.json` `lexicon` via `ontology/emit-lexicon.py`, and
`emit-lexicon.py --check` (in the ontology gate) fails any hand edit — so editing
`LEXICON.md` directly is the same class of error as editing `codex/`. Edit the
graph, re-emit, then run `gates/check-lexicon.py`, which reads the emitted file:
it scans every tracked text file outside its archive allowlist for deprecated
tokens (`DENY`). Every enforced token must be documented in LEXICON.md, and both
the file set and the denylist are asserted non-empty, so a green run cannot pass
over nothing.

It also enforces **concept homes**: a machinery file whose path carries a
concept's slug must live under that concept's declared home. The trees named in
`NOT_A_HOME` (the corpus trees, `design/`, `benchmarks/`, `research/`, `packages/`)
are exempt — a slug there is a mention, not a home. A home matching no file fails
as a stale declaration.

Adding a concept: find the nearest existing term in LEXICON.md first, then
reuse / extend / rename / split explicitly, in the same change — in the graph.

## 6. Anything the installer reads at runtime must be in `files[]` — ENFORCED

`gates/check-package.sh` greps the real `$REPO/...` references out of
`install.sh` and `compose/assemble.py` and fails on any path missing from
`package.json` `files[]`. Derived, not a hardcoded list, so a path added later is
covered automatically.

Three directions in all. The second: everything under `gates/` is author-side and
must **not** appear in `files[]`, as must the author-side files declared by name
inside shipped directories. The question is asked of the author-side **files**,
not of the `files[]` entries — npm expands a directory entry to its whole
subtree, so an entry can pack a file no entry names. Exemptions are individually
justified in the gate (`EXEMPT`), and an author-side path the installer really
does reach at runtime must be declared in `RUNTIME_GUARDED` with the literal
guard that protects it, which the gate then requires to still be present in the
referring file.

The third: **shipped prose may not name a path the user will not have.** It covers
the corpus markdown and shipped config alike, because a launch preset's mission
instructs an agent exactly as a guide does. A file may name author-side paths only
by declaring `audience: author` and stating `Requires an agent-bios checkout` in
its own text — and `compose/assemble.py` withholds such a file from delivery, so
the declaration now decides what a packaged user receives instead of only
excusing a reference. A nonexistent path fails regardless of the declaration:
`audience: author` excuses naming a path the reader will not have, never one
nobody has.

The declaration has one reader: `check-package.sh` imports `author_only` from
`compose/assemble.py` rather than parsing the frontmatter again, because the gate
only tolerates what that withholding makes safe. The direction is fixed —
author-side imports shipped, never the reverse, since the payload cannot depend
on `gates/`. A self-test case breaks the assembler's reader and requires the
gate's exemption to vanish with it, so the single-sourcing is proven, not stated.

This gate exists because an unshipped runtime path is invisible from a clone and
fatal on npm — every check you run from the clone passes.

`--self-test` plants each of these violations into a throwaway copy of the tracked
tree and requires the gate to fail **by name** on it, positive control first so a
failure is attributable to the mutation. It runs in the parity umbrella.

## 7. Rule bodies use role slots and tiers, not model names — CONVENTION, with a gated exception

Concrete bindings live in each guide's `Environment Binding`. A new model updates
that row; the rules stay untouched.

The real exception is the prompting guides: `claude-prompting.md` and
`gpt-prompting.md` are model-version-bound — their advice inverts between model
generations — so they list concrete ids in `targets:` frontmatter.
`launch/check-prompting-targets.sh` ENFORCES this, failing when
`launch/agent-launch.toml` binds a model no prompting guide covers, which is
exactly when the guidance needs re-deriving.

`README.md` (Principles, first bullet) declares only tool-surface sections and `DEPENDENCIES.md`
capability names as exceptions; the prompting-guide exception is real, gated, and
missing from that list. Trust the gate.

**But the gate checks NAMING, not re-derivation.** `check-prompting-targets.sh` computes
`configured - declared`: it fails when the launch config binds a model no guide lists, and
one line added to `targets:` satisfies it forever. That is correct as far as it goes —
"was this guide re-derived for this model" is not decidable, and this repo blocks only on
what is. What IS decidable is whether the source moved:

```bash
python3 gates/check-prompting-sources.py             # offline, BLOCKS — runs in the umbrella
python3 gates/check-prompting-sources.py --online    # + fetch and compare, discloses only
python3 gates/check-prompting-sources.py --self-test  # offline, 8 controls
```

Each prompting guide's frontmatter carries `derived_at` and `source_pins` (document name +
sha256 + `pinned_at`); `gates/prompting-sources.json` maps the document names to URLs. The
URL lives author-side on purpose — `gates/check-endpoints.py` forbids a shipped file from
carrying an endpoint URL, and buying an exemption for documentation metadata would weaken a
real product property for nothing.

**A pin is a baseline, not provenance.** When `pinned_at` is later than `derived_at`, the
guide predates its own pin and has never been checked against it; the tool says so on every
run. Both guides are in that state as of 2026-09-01 — `gpt-prompting.md` has not been
re-derived since the commit that created it (`dd12494`, 2026-07-16), and `claude-prompting.md`
not since `d30d41a` (2026-07-25). Recording today's hash as the derivation would have
manufactured provenance nobody could later tell from the real thing.

The two halves have different exit codes on purpose. **Structure blocks**: every pin must
name a document `prompting-sources.json` maps, every mapped document must be pinned by some
guide, and a run judging zero pins fails — all offline, all decidable, so it sits in the
umbrella like any other gate. **Drift only discloses, and only under `--online`**, because
fetching in the umbrella would fail in a tunnel and teach people to route around the suite.

That split was not the first design. The first put the whole tool outside the umbrella, and
`check-parity.sh`'s own reachability leg refused the commit — *"check(s) never reached from
the pre-commit hook, so they gate nothing at commit time"*. It was right: a check in
`gates/` that gates nothing is the thing this repo does not keep. Run `--online` when a
model binding changes and before trusting either guide.

## 8. The deployed global is a per-session token budget — CONVENTION

`claude/CLAUDE.md` is re-sent every session and to every subagent, so each added
bullet dilutes every other rule. A new global bullet must name the bullet it
displaces, or why none does. Procedures, tables, numbers, and worked examples
belong in a guide.

A rule earns global placement only if it must work **even when the agent fails to
recognize the situation**. A rule whose failure mode is recognition failure
belongs behind a pointer.

Numbers live in the owning guide's `Evidence Base`; measure with
`session-cost.py`. Do not scatter measured values into rule bodies.

**The global is frozen to reductions (2026-09-03).** Edits that delete, merge, or move a
rule out are open; additions are not. A rule that would have been added goes to a guide, a
skill, or session-level injection instead, and if none of those can hold it, that is the
case to bring — not a bullet.

The freeze is not a conclusion about where the corpus should live. It stops the one thing
that is irreversible in practice — growth — while that question gets a proper design pass.
The evidence behind it, and the delivery surfaces available on each host, are in the
2026-09-03 records under `design/session-distill/`.

## 9. Deploying the working tree is not `agent-bios install`

`install.sh` resolves `REPO` to its own resolved location,
so the globally installed `agent-bios install` deploys **the published npm
package**, not this tree. To deploy what you are editing:

```bash
bash install.sh install     # from the clone
```

Three more, each of which cost a real failed attempt:

- `npm i -g agent-bios@latest` right after publish installs the **previous** version (stale
  packument, exit 0). Pin exact — `npm i -g agent-bios@X.Y.Z` — then verify the *deployed*
  `version.json`, never the registry.
- `install.sh` runs `exec </dev/null` at the top, so a stdin-payload subcommand needs the
  caller's fd parked on 3.
- Never publish a corpus that calls a new CLI subcommand before the CLI carrying it ships.

## 10. Record a decision when it closes an alternative — CONVENTION

```bash
python3 decisions/record-decision.py --kind design|direction|stop|steering \
  --summary "..." --closed "the alternative this ruled out" --why "..."
python3 decisions/record-decision.py --render        # read it back
python3 decisions/record-decision.py --timeline      # active/idle per decision
python3 decisions/record-decision.py --graph         # sessions as lanes
python3 decisions/record-decision.py --check         # validate the ledger itself
```

`--check` runs in the parity umbrella. It exists because this is provenance for a
cooperating tool, not a security boundary: `session` comes from the environment
and the ledger is an append-only text file anyone can edit, so the artifact needs
a gate of its own rather than trust. An id is `D-<date>-<hex>`, derived from
every field of the record but the id — content, not position — so ledgers
written on two branches merge by concatenation, and `--check` fails any row
whose id is not what its content derives to (any hand edit moves it). Ids were positional (`D-0062`)
until 2026-08-16 and could not merge; `--migrate` rewrites an older ledger once
and is idempotent after. Appends take an exclusive lock, and a record identical
field for field to one already there is refused rather than written twice.

The bar is structural, not a matter of taste: the tool refuses a record that
closes nothing. Routine implementation choices are not decisions; a rejection, a
deferral, a stop, or a redirect is. Abandoned directions matter most — they are
the ones with no other trace, and the first thing you want when asking where
something went wrong.

The tool owns id, timestamp, branch, HEAD, dirty state, and the session. You
supply meaning only. The session comes from whichever host is running —
`CLAUDE_CODE_SESSION_ID`, or `CODEX_THREAD_ID` under Codex — and on both hosts
that id is part of the transcript's filename, so a decision points at the exact
action stream it belongs to instead of being matched to one by guesswork.
Reading only the first gave every Codex-recorded row a null session, which shares
the `unattributed` lane and resolves no transcript at all.

**Work volume is time, and time is derived rather than recorded.** Tokens are
not usable — billed output is mostly thinking that never reaches the transcript,
so any figure written here would be a guess. Time needs no measuring either:
every action in a session transcript already carries its instant, so duration is
a projection over the action stream. `--timeline` computes it; nothing is stored,
because a stored interval is a derived value frozen outside its source.

Only the transcripts of sessions that actually recorded decisions are read, and
an interval never crosses a session boundary — the wall-clock between one
session's last decision and the next session's first is time away, not work.
Scoping is not cosmetic: the same interval measured 445 actions across all
projects and 92 within its own session.

Consecutive actions less than 15 minutes apart count as active — a main context
waiting on a background task is working, and its results keep landing. A longer
silence is reported as idle, never counted and never dropped, because only a
person can tell a long wait from an absence. `--backfill` marks a decision whose
instant is when it was typed, so every interval touching it reads as unreliable.

The line against session distill is shipping, not subject matter. Distill is a
feature of the deployed package that its users run against their own sessions;
this log never leaves the checkout. `gates/check-package.sh` holds that boundary
in both directions — `decisions/` is declared author-side there, so adding it to
`package.json` files[] fails the gate. Merging it into distill later, or letting
it replace part of distill, is open; until then they are separate because one
ships and one does not.

## 11. Ontology claims come from the implementation, never from authoring — ENFORCED

`ontology/extract.py` derives them and `ontology/check-ontology.py` fails on disagreement —
including the counts stated in `ontology/` prose, which drifted from the data once already. A
dependency map that is confidently wrong is worse than no map, so it is gated like code, not
maintained like docs.

```bash
python3 ontology/impact.py <entity|path>   # what must change with it, and what enforces that
python3 ontology/impact.py --diff          # obligations where one side moved and the other did not
python3 ontology/extract.py                # re-derive the ontology's facts from source
python3 ontology/check-ontology.py         # hold ontology/ against the code (+ --self-test)
```

`impact.py` traversal follows each edge kind's obligation direction, not simply edges out of the
node — `!!` marks an obligation nothing enforces, which is the list worth reading. `--diff`
discloses rather than blocks; only `check-ontology.py` is wired into the gate suite.

## Ontology rounds

The ontology exists to reach correct decisions through complete understanding. A question that
only verifies or reproduces meaning has no utility and can multiply without bound, so it is
inadmissible — every bar below descends from that sentence.

**Two loops, never merged.** The synchronous one runs on every change (`impact.py --diff` plus
the gate suite) and only discloses. The deepening one runs deliberately, bears judgement, and is
expensive. A commit must never wait on a round of semantic judgement.

**Three kinds of gap, three owners.** G1 coverage (implemented, unnamed by the ontology) is
ontology work. G2 fidelity (named, but false or stale) is the gates' work, automatically. G3
enforcement (a true obligation nothing enforces) is **code** work. Mixing them in one round makes
"refining the ontology" and "building a gate" indistinguishable.

**A round is three stages and the order is a gate.** A settle (admit unanimous facts, decide
nothing) → B classify (surface every contradiction and unlinked pair, settle nothing) → C decide
(human, one at a time, with alternatives and a date). A must be exhausted before C: a fact
surfacing later invalidates a decision already made, and deciding requires the blast radius A
produces. Stopping at B is a normal outcome — moving an item from "unknown" to "known
unresolved" is progress. **The reverse direction is the one that gets missed**: when C lands,
re-read the questions and findings whose dependencies it changed, because each was written in an
earlier round's frame and nothing re-examines it on its own.

**A claim is in one of five states.** *admitted* — every site that speaks gives the same answer.
*licensed asymmetry* — sites differ and a declaration exists **as data** naming the differing
site. *contradiction* — sites differ with nothing naming them; this is a decision, and neither
side may be admitted. *unlinked* — the sites were never making the same claim, so the link is
wrong and the fix is in the ontology, not the code. *transitional* — the shape exists because
work is in flight, and the answer is finishing it. "A general rule covers it" does not qualify:
a declaration naming no site excuses every site, and an enumeration that happens to exclude
something has not named it. That last rule binds gate scopes and exemption lists too, not only
licences — every entry carries its own reason.

**Question admission.** Name the decision that changes when the answer changes, and that decision
must descend from a stated purpose clause; be answerable by evidence rather than opinion; and
change something either way. A new entity is admitted only when a supported question demanded it,
so the loop cannot invent its own work. A clause describing a future state licenses **foreclosure
questions only** — "does current work make this impossible or expensive later?" — never questions
about an implementation that does not exist.

**Support is site agreement, not source extraction.** Ranking the implementation strongest treats
it as truth. An answer is strong when every site gives the same answer, which is why extractors
return a **site set**: one that folds its sites into a single answer is structurally unable to see
a contradiction. Admissible support is source extraction, runtime probe, or user decision;
inference is not support, and an unsupported answer is not admitted.

**The ratchet.** unguarded down → undecided down. `unguarded-accepted` — decided *not* to enforce,
with the reason recorded — counts as closed. Driving every unguarded edge to zero is the Goodhart
failure: for some obligations enforcement costs more than the risk, and a check people learn to
ignore is worse than none. Convergence is two consecutive dry rounds plus a budget ceiling, and
every round records why it stopped, or "a round was run" is unfalsifiable.

**A round's output unit is a check, not a note.** Closing a G3 item means a new gate assertion
**and its negative control**; "recorded it" closes nothing. Decision records carry claim / sites /
options / consequence / decided (date, choice, rationale) / prevents — the last field is what
stops the same contradiction returning, and an open decision with one option is a conclusion
wearing a decision's shape. Two traps this repo has paid for: a negative control that indexes a
live list stops testing when that list empties, silently, so new controls build their own rows and
resolving an item means re-reading the controls for ones that went quiet; and after editing
`install.sh`, expect `check-ontology.py` to fail on drifted evidence literals before any test
does — fix those by re-measuring, never by editing the number to match.

**The judge.** Admission is judged inline; each round ends with one cross-family pass, and that
pass is the only independence the loop has. Re-measuring from inside the same context has been
wrong repeatedly. Same-provider agreement is high-confidence but blind-spot-sharing: a shared
"clean" from one reviewer kind is an absence of objection, not verification.

## Before you believe a green gate

A green gate means "it ran", not "it checked your change".

- **A gate that never scanned your file is green about nothing.**
  `gates/check-lexicon.py` builds its file set from `git ls-files`, so a new
  untracked file is not scanned and the gate passes without seeing it. Run
  `git add -N <file>` before trusting a lexicon or concept-home result.
- **Assert the subject set is non-empty before any "no bad X" claim.** An empty
  set satisfies everything. The gates model this themselves — `check-parity.sh`
  guards required dirs and files up front, and `check-lexicon.py`
  fails a concept home that matches no file.
- **Know which legs silently skip.** `install.sh` `cmd_verify` runs the parity gate only
  under `[ -d "$REPO/ko" ]`, and `ko/` is excluded from the npm package, so
  `agent-bios verify` from an npm install never checks mirrors. Only a clone
  does.
- **A gate you have not seen fail is not a gate.** Most gates here ship a
  `--self-test`; `check-parity.sh`'s own runtime-projection module
  (`gates/check_parity.py`) and `launch/check-prompting-targets.sh` do not, so do
  not read the umbrella's green as every leg having a negative control.
  `check-package.sh` gained one on this branch, and its four newest legs were each
  shown to pass a planted violation first — the flag had been rejected rather than
  implemented, which is honest and proves nothing. When you add a check, add its
  negative control, and prove a new rule fires by planting a violation and
  watching it fail by name. Then revert the fix and watch the control fail: a
  control written against a bug it does not actually test will survive a faithful
  revert, and two on this branch did. `gates/control-audit.py` runs that test for you
  across the Python gates: it removes one failure statement at a time and asks whether
  that gate's own `--self-test` notices. It discloses and exits 0, because which
  uncovered check deserves a control is a judgement, and a gate on a judgement call is
  one people route around. Shell gates, and any gate whose failure statements live only
  inside `self_test`, are named in its output as ungraded rather than counted clean.
  Every re-measure so far has found well under half the checks covered, and the denominator itself has moved three times as review taught the finder new emission shapes — re-run it for the current figure; a number copied here would be stale within rounds. Sinks are classified in the tool (FAIL_SINKS/DATA_SINKS) and an f-string append to a name in neither is reported loudly, so the next uncatalogued sink is a printed line, not a silent hole.
- **A check that cannot fire is not a check.** `check-package.sh` registers every
  leg's subject set through `leg(name, subjects)` and refuses to report clean when
  any leg judged nothing, so this is structural rather than remembered. It reports
  per leg and never aggregates — an aggregate count is how a zero hides, which is
  exactly how a scan here passed while its only subject had been deleted in the
  same commit that added it.
- **Ask what it operated on, and who reads the result.** A positive control proves
  the mechanism can fire on the input you chose; it says nothing about the inputs
  that exist, nor about anything downstream changing. Two questions catch what
  that misses: enumerate the real subjects and look at them, and `grep` for the
  consumers of any new field or label — if the only reader is the thing that
  produced it, it does nothing yet. `audience: author` was such a label: obliging
  a stated prerequisite still left the gate as its only reader, and the guide
  went on being installed by every selection until `compose/assemble.py` began
  withholding it. A label that changes only what a gate tolerates changes nothing
  a user receives.
- **Verify against the artifact, not a document about it.** Design records,
  handoffs, and dashboards are dated claims — count the ledger, read the code.

## Where authority lives

One value has one owner, and every other surface is generated from it. Generating makes a
one-sided edit impossible instead of merely detectable. A restatement survives only where the
second surface is a semantic transformation of the first — a translation, or a compression to a
different altitude — and then it is anchored and the reason is declared. A gate holding its own
copy of the value is a third restatement, not a guard. The rules above are this one's cases;
where a case still gates a restatement that could be generated, that is a debt, not a design.

Re-derived from code. Prefer these over any summary — and this table is itself one, held by hand
while `ontology/` covers seven of its nine rows.

| Concept | Authority |
| --- | --- |
| Deployed instruction text | `claude/CLAUDE.md` — Codex is projected from it |
| Codex + ko/codex trees | `gates/emit-mirrors.py` — owns the projection rule |
| Terminology and concept homes | `ontology/instances/graph.json` §lexicon → `LEXICON.md` (generated), operated by `gates/check-lexicon.py` |
| Delivery surfaces and their admission bars | `SURFACES.md`, held against `install.sh` by `gates/check-surfaces.py` |
| npm payload boundary | `package.json` `files[]`, enforced both ways by `gates/check-package.sh` |
| Corpus classification | `compose/domains.json`, gated by `compose/check-domains.py` |
| Launch bindings and projection | `launch/agent-launch.toml`, `launch/agent-launch.py` |
| Runtime-projection checks | `gates/check_parity.py` (`--list`, `--only`) |
| Cost accounting | `session-cost.py` |
| External tools and versions | `DEPENDENCIES.md` |

`README.md` is gate-bound: the anchor-phrase list in `gates/check-parity.sh`
pins shared phrases across files, and one pair names `README.md`, so rewording
there can fail parity.

`IMPLEMENTATION_MAP.html` is a current-state dashboard. Treat its claims as
dated and re-derive from code before relying on them.

## What this file deliberately leaves out

General engineering discipline — tool traps, verification menus, spawn policy,
review contracts — is not repeated here. It is already loaded from the deployed
global corpus in every session, and this repo's own rule is that restating a rule
dilutes it. Only what is specific to developing *this* repo belongs in this file.

## Traps that cost a real attempt here

- **A gate that runs `git init` under the hook's exported `GIT_DIR` rewrites the real
  `.git/config`** (`core.worktree`) and breaks `git status`. Scrub `GIT_DIR`/`GIT_WORK_TREE`
  before creating a scratch repo inside a gate (`compose/corpus-state.py` `own_repo_env`); the
  hook now detects and restores the value, but only after the damage.
- **`git add -A` sweeps files that other sessions left untracked in the tree** — it once
  widened a PR with somebody else's work in flight (`1acdd65`). Add by name.
- **A launcher run without `--config launch/agent-launch.toml` reads the DEPLOYED profile**,
  not the tree's; a probe that "passes" may be probing the last release. Options go before
  the positional host.
- **The Bash tool is zsh**: `$var` does not word-split, `$ref:path` is a history modifier — a
  probe loop that reports uniform results is a reason to check the instrument first.
- **`cost` follows `learn`'s fd-3 rule** (§9): a stdin payload for either subcommand must be
  parked on fd 3 by the caller.
- **An intent-to-add entry (`git add -N`) breaks the commit hook**: the index snapshot the
  hook materialises has no content for it, while `check-package.sh --self-test` copies every
  `git ls-files` path and dies on the missing file, reported as "self-test missed a planted
  violation". `-N` is for running the lexicon gate by hand; `git add` fully (or `git reset`
  the path) before committing.
- **Editing `install.sh` makes `ontology/ONTOLOGY_MAP.html` stale**: the map embeds, by live
  extraction, the line numbers of the `verify_match`/`verify_present` call sites, so any edit that
  shifts lines fails `check-ontology.py`'s projection-freshness leg — inside `install.sh verify`
  and inside the commit hook — with a message that names the map, not your edit. Run
  `python3 ontology/emit-map.py` after the last `install.sh` edit and stage the map with it
  (2026-08-26: two checkout deploys failed on this before the cause was attributed).
- **`bash gates/test-install-guides.sh` reads itself incrementally**: editing the file while a
  run is in flight shifts bash's offset into the middle of a line and the run dies with a
  syntax error that is not in the file. Copying it elsewhere does not help — it `cd`s to its
  own parent for `REPO`.

## Commits

Declarative-sentence titles stating the insight, not the mechanics — "Review independence is
the axis; the enum was the blocker". Releases: `Release vX.Y.Z`.
