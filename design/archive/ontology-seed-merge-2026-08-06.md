# Merging `ontology-seed` into the trunk — work design

**Archived 2026-08-06 — the merge landed as `e28f66d`.** Nothing here is updated after this date;
read it as what was true on the way in, not as current state. The decisions it left open were
recorded as D-0039, D-0040 and D-0041 in `decisions/decisions.jsonl`, which is where they stay
current.

It was a living document until the merge landed. Every number below was measured on
2026-08-05 against `ontology-seed` = `b583945` and `origin/main` = `52d2a95`; each carries the
command that reproduces it, so a stale figure is detectable rather than believed.

## Goal

Land 47 commits of `ontology-seed` on the trunk without re-litigating what either branch already
decided, and without letting the merge silently answer questions a merge cannot answer.

Done when: the merged tree passes both branches' full gate suites, the four recorded decisions
(D-0035…D-0038) are either honoured or superseded by a dated correction, and no conflict was
resolved by preference where a decision existed.

## Why the two branches are one piece of work

Both attack the same failure from opposite ends, and each states it in its own words.

`ontology/domain_scope.md`:

> Capture this repository's **dependencies in full**, so that a change made in brownfield
> conditions cannot silently miss a surface it was obliged to touch. […] The failure this exists
> to remove is not "I did not know what this repo does". It is "I knew what I was changing, and
> I did not know the other four places that had to change with it".

The trunk, in a commit subject and a section heading:

> The repo could not tell its product from its workshop
> *Where authority lives — Re-derived from code. Prefer these over any summary.*

One made the **boundary** explicit and enforced; the other made the **obligation** computable.
Neither is a competing account of what this repo is for.

The strongest evidence is structural rather than rhetorical: `ontology-seed`'s purpose layer is
**extracted, never authored** — 17 `stated` clauses, 0 `inferred`, quoted verbatim from
`README.md`, `package.json`, `install.sh` and `AGENTS.md`, with `check_purpose_extraction`
failing when a quote leaves its source. PU-15 is the trunk's own first invariant. The branch did
not bring a rival purpose; it read the shared one and made it checkable.

```bash
python3 -c "import json;p=json.load(open('ontology/instances/graph.json'))['purpose'];print(len(p['stated']),len(p.get('inferred',[])))"
```

## The decision rule

Not "which file wins", and not "which side already built a gate" — the second ranks the
implementation as truth, which is the thing `AGENTS.md` "Ontology rounds" forbids:

> **Support is site agreement, not source extraction.** Ranking the implementation strongest
> treats it as truth.

The rule is: **what must the merged repo be able to do that neither half can do alone.** Where
that does not decide, the first invariant does — one owner, every other surface generated, a
restatement surviving only as a semantic transformation at a different altitude.

## The decisions

| | Disposition | Change from the ledger |
| --- | --- | --- |
| D-0035 `AGENTS.md` | hold | **execution prerequisite added** (measured, below) |
| D-0036 `LEXICON.md` | hold | **rationale replaced** — the recorded one is falsified |
| D-0037 `FINDINGS.md` / `decisions/` | hold | scope extended from two surfaces to three |
| D-0038 dated records | hold | none |
| **New — authority table** | open | not in the ledger or the assessment |

### D-0035 — rules and map are different consumption modes

The trunk's `AGENTS.md` is rules loaded every session; `ontology-seed`'s is a map looked up when
you already know you need it. PU-9 (the always-loaded layer is a token budget) and PU-10 (a rule
earns global placement only if it works without situation recognition) make that split a purpose
consequence rather than a preference. The map merges into `README.md` `## Layout`, which is
already the same table at the same altitude.

Only two of `ontology-seed`'s seven sections are map: `## Map` and `## Commands`. `## Invariants`,
`## Deploy gotchas` and `## Commits` are rules and merge into the trunk's numbered sections.
`## Ontology rounds` (68 lines) is method for running a round — needed when you run one, not every
session — so it belongs in a scoped document, not in the always-loaded file. That collides with
`design/archive/README.md` ("Durable *method* does not live here… it belongs in the repo's
`AGENTS.md`"), written before the method reached this size. Resolve it when the section moves.

**Prerequisite, measured not inferred.** Two purpose clauses quote `AGENTS.md`, and both quotes
exist only in `ontology-seed`'s version. Replacing the file breaks them, and the gate says so by
name:

```
실험군  AGENTS.md = trunk    → check-ontology FAIL
          PU-4:  quote is no longer in AGENTS.md — the purpose clause has lost its source
          PU-15: quote is no longer in AGENTS.md — the purpose clause has lost its source
대조군  AGENTS.md = seed     → check-ontology OK (38 entities, 49 edges, 9 kinds)
```

Run in a scratch worktree with the other seven conflicts pinned to `ontology-seed`, so
`AGENTS.md` was the single variable. Either relocate the quoted sentences into the file that
keeps them, or update `source`/`quote` in the graph — in the same change, or the merge lands red.

### D-0036 — hold, on a different reason

The ledger defers the LEXICON→projection conversion because the ontology is "a subsystem that has
never run in this tree" and the conversion is something `domain_scope` "proposes". Both are
false. It is built and gated:

```bash
python3 ontology/emit-lexicon.py --check    # OK (LEXICON.md matches graph.json)
python3 ontology/check-ontology.py --self-test   # 55/55
```

The conclusion survives on a reason the record does not give. `domain_scope.md` says, in one
document:

> So the load-bearing content of this ontology is its **edges**, not its nodes. […] `LEXICON.md`
> already owns the former (and is absorbed here, see "Relation to LEXICON"). This ontology exists
> for the latter.

> The ontology's entity layer becomes canonical and `LEXICON.md` becomes its projection, so a
> concept is defined once

Absorbing the node layer is not demanded by the ontology's stated purpose; it is an extra move
that arrives with the same merge. Defer it to its own change, where it gets its own control.

The `lexicon` block is also authored rather than extracted — a fact worth carrying into that
later decision, because it puts terminology *policy* inside the instance layer:

```bash
rg -c -i lexicon ontology/extract.py        # 0
rg -c -i lexicon ontology/emit-lexicon.py   # 19   ← positive control: the search works
```

### D-0037 — three surfaces, not two

| Surface | Question | Lifecycle | Gate |
| --- | --- | --- | --- |
| `FINDINGS.md` | which product defects are open | deleted when closed | `check-lexicon` refuses resolution markers |
| `decisions/decisions.jsonl` | what closed an alternative | appended, never edited | `record-decision.py --check`, `--self-test` |
| `graph.json` `decisions.rows` | which ontology claims are unsettled | open until decided | `check-ontology.py` |

The ledger reconciled the first two. The third exists and `FINDINGS.md` already points at it.
Ids collide in shape: the graph uses `D-1`, `D-2`; the ledger uses `D-0001`…`D-0038`. State the
boundary once, in one place, and separate the namespaces.

### D-0038 — no change

Both branches independently found the same rotten artifact (`session-distill/HANDOFF.md` claiming
current state with moved counts). The directory rule (never edited, no runtime pointer, both
enforced) and the timestamped filename are complementary halves. The trunk's "What goes where"
row still routes history to `design/<initiative>/` and must be updated to match.

### New — the authority table is a hand-maintained projection

`AGENTS.md` `## Where authority lives` says *"Prefer these over any summary"* while being one.
Seven of its nine rows name a path that a graph entity already anchors:

| row | entity |
| --- | --- |
| Deployed instruction text | `corpus-rule` |
| Terminology and concept homes | `terminology-authority` |
| npm payload boundary | `payload-entry` |
| Corpus classification | `packaging-tier`, `domain`, `package-identity`, `schema-version` |
| Launch bindings | `backend`, `host`, `tier-binding`, `capability`, `review-method` |
| Runtime-projection checks | `negative-control` |
| Cost accounting | `measurement-instrument` |
| External tools and versions | **none** |
| Codex + ko/codex projection | **none** |

The two uncovered rows are G1 coverage gaps in the ontology's own taxonomy: nothing anchors
`gates/emit-mirrors.py` or `DEPENDENCIES.md`. So the table is not redundant today — it carries
two claims the graph does not.

This is the point where the two branches were actually building the same thing, and it appears in
neither the assessment nor the ledger. It is what the merge **opens**, not a precondition of it:
the table cannot become a projection until the graph covers those two, and the graph can express
what the table cannot — which obligations nothing enforces (`impact.py`'s `!!`).

## Execution

"Record before merging" binds only where a record changes a resolution, and none of the three
pending ones does: D-0036's correction leaves its conclusion intact, `FINDINGS.md` and
`decisions/` are create-only on opposite sides and appear in no conflict, and the authority-table
item is post-merge by construction. The tool that writes records arrives *with* the merge, so
recording after is both possible and better — the entries then state what happened rather than
what was planned.

1. **Commit this document.** It is what survives a context reset, and it holds the reasoning the
   ledger entries will later compress.
2. **Merge, not rebase** — `git merge origin/main` from `ontology-seed`, so 47 commits are not
   replayed. Resolutions: `AGENTS.md` and `CLAUDE.md` per D-0035; `LEXICON.md` stays
   `ontology-seed`'s generated file (D-0036); `install.sh` is the one real semantic merge (trunk
   +128/−6 vs seed +165/−69 from the base); `launch/agent-launch.toml` and `gates/test-assemble.sh`
   are additive.

   The purpose prerequisite resolves inside this step rather than before it. PU-15's quote —
   `every other surface is generated from it` — survives by construction if `## Invariants` is
   carried into the merged rules, and the trunk states that invariant nowhere, so a red PU-15 is
   the gate reporting a real loss rather than a bookkeeping mismatch. PU-4's quote is the repo
   one-liner in the seed header; it belongs in `README.md` by the trunk's own routing table, so it
   moves there and the graph's `source` for PU-4 changes in the same commit.
3. **Regenerate, do not merge** — `gates/goldens/review-matrix.json` via
   `gates/capture-review-goldens.py`, and `IMPLEMENTATION_MAP.html` from the merged state.
4. **Verify** (below).
5. **Record** the three ledger entries, now that `decisions/record-decision.py` exists.
6. **Deploy and publish** — repo-tree deploy, then pin-exact npm install and verify the *deployed*
   `version.json`. The payload gains `compose/prune-backups.py` and `wrappers/claude-run.sh`, so
   this is a real release and needs a version bump, not a republish.

## Verification

Both suites, because each covers what the other does not. The last line is only runnable after
the merge — `decisions/` does not exist on this branch, which is itself a reason to run the full
set rather than the half this checkout can reach:

```bash
./gates/check-parity.sh            # includes check-surfaces, check-receipt-chain, review goldens
python3 ontology/check-ontology.py && python3 ontology/check-ontology.py --self-test
python3 gates/check-lexicon.py && bash gates/check-package.sh
python3 decisions/record-decision.py --check && python3 decisions/record-decision.py --self-test
bash gates/test-assemble.sh && bash launch/check-prompting-targets.sh
```

Controls, because a green suite over a merged tree proves less than it looks:

- **Purpose anchoring** — after resolving `AGENTS.md`, restore the trunk's version alone and
  confirm `check-ontology` fails naming PU-4 and PU-15. A pass there means the prerequisite was
  not actually satisfied, only masked.
- **Regeneration really ran** — the regenerated `review-matrix.json` must differ from *both*
  parents. Byte-identical to either means the capture did not execute.
- **`install.sh` merge** — the merged file must fail a planted revert of a line each side
  contributed, one per side. A merge that keeps only one side's behaviour passes every existing
  test.
- **Non-vacuity** — print the counts (entities, edges, files scanned, cells) rather than trusting
  `OK`; an empty subject set passes vacuously.

## Where this stopped, and how it resumed

**Corrected 2026-08-06.** This section previously reported `gates/test-install-guides.sh` as
"I1–I5 pass, I6–I8 do not". That was false against the merged tree — the suite stood at 8 PASS /
19 FAIL, with I1, I2, I3 and I5 failing too. The claim is corrected rather than deleted because
the discrimination this section prescribed is what found the defect, and the prescription was
right even though the figure was not.

The merge was **in progress and uncommitted** — `MERGE_HEAD` live, no conflicts remaining, every
resolution staged. `git merge --abort` discards it; continuing needs no re-resolution.

Everything below the last line is green on the merged tree: ontology (38/49/9) and its 55/55
self-test, lexicon (207 files, 9 concept homes — up from 8, so the gate grew rather than passing
over the same set), package (32 runtime paths, 27 author-side), `record-decision --check` and
`--self-test`, the assembler scenarios, and the regenerated review golden at 254 cells that
differs from **both** parents.

**`gates/test-install-guides.sh` failed.** That suite is the trunk's, and it was written against
an install with two paths — packaged and full. `ontology-seed` collapsed them into one
(`assemble_corpus`, which expresses "full" as a selection of every domain), so several of its
assertions describe a branch that no longer exists.

That explained the shape of the failure but not the first one. `I6 the domain-selected install
exits 0` asserts only that `install --domains builder-base` returns 0, which is a claim about the
product rather than about the two-path structure — so the suite's failure was **not attributable**
until the install was run alone, with nothing from the harness:

```bash
bash install.sh install --domains builder-base --dry-run ; echo "rc=$?"
```

**It exits 1**, on `install.sh: line 564: author_only_guides: command not found`. The first branch
held: the merged `install.sh` carried a real regression, and the test was doing its job.

The cause is a brace the merge misplaced. Both sides added different content immediately before
the same anchor line (`# ---- corpus deploy ---`): `ontology-seed` added `prune_backups`, closed
(`80b5c97:112-117`); the trunk added `author_only_guides` and `prune_withheld`. The union kept
both bodies but carried `prune_backups`'s closing `}` past them, so the two trunk functions became
**nested definitions** inside it — created only when `prune_backups` runs, which `cmd_install`
does at its final line, long after `author_only_guides` is needed at 564. Every install path died,
not only the domain-selected one.

Nothing static caught it because a nested function definition is legal bash: `bash -n` returns 0
and the file's braces balance. What catches it is counting definitions against declarations — 29
functions written at column 0, 27 reaching top level.

The `grep: …/backups: No such file or directory` line was the same root cause, as suspected here:
the install died before creating the backup directory. Fixing the brace alone turned both I5
assertions green.

**Both hypotheses were true, and they were never exclusive.** Moving the one brace took the suite
from 8 PASS / 19 FAIL to 24 PASS / 3 FAIL, and `I6 the domain-selected install exits 0` flipped to
PASS — which is what proves that assertion was not stale. The three that remained do encode the
deleted two-path structure, and were rewritten against the single shape:

| stale assertion | current behaviour |
| --- | --- |
| full mode means no `selection.json` | full mode is every domain selected |
| an ordinary guide sits at `$CLAUDE_DIR/guides` | it lands under `central/guides`; the old path is only swept |
| both hosts log `removed stale copy` | `assemble.py` logs `remove withheld` for the destinations it writes; `install.sh` logs `removed stale copy` for the pre-unification path it alone sweeps |

The third is the one worth reading twice: lowering the count from 2 to 1 would have passed while
dropping the codex removal from coverage entirely. The two removals have different owners, so each
is now asserted through its own message.

Each rewrite carries a negative control — the full-mode predicate rejects a single-domain **and an
empty** selection, the codex pattern does not fire on the claude line, and the old guide path is
confirmed absent so the previous assertion would now fail. The suite is 27/27, `check-parity.sh` is
green with **no leg skipped**, and the whole gate set re-run: ontology 38/49/9 and 55/55, lexicon
207 files / 9 homes, package 32 runtime paths / 27 author-side, decisions 38 records / 131 controls.

## Discovered while merging, worth keeping

- **The README Layout table is gated.** `check-parity.sh` fails when a tracked top-level tree is
  missing from it, in `README.md` *and* `ko/README.md` — which is why `.githooks/`, `decisions/`
  and `packages/` had to be added. This is the mechanism that makes the README a real map rather
  than a document someone maintains, and it is independent evidence for D-0035.
- **`design/session-distill/HANDOFF.md` does not exist in the merged tree.** `ontology-seed` moved
  it into `design/archive/` while the trunk edited it in place, so the trunk's distill mission
  string would have pointed at a path that is gone. The resolved `launch/agent-launch.toml` takes
  the trunk's *location* (the checkout, since the guide is withheld from installs) and the
  branch's *target* (`ledger.json`, since the handoff is now a dated record).
- **`compose/assemble.py` prunes only the destinations it writes** — `central/guides` and the
  Codex guides. `$CLAUDE_DIR/guides` is the pre-unification full-mode destination, so the
  installer keeps sweeping it for machines that installed before the single shape.
- **`## Ontology rounds` stayed in `AGENTS.md`.** `design/archive/README.md` assigns durable
  method there in as many words, so moving it is a decision of its own rather than a merge
  resolution.

## Out of scope

- Converting `LEXICON.md` to a projection of the entity layer (D-0036) — its own change.
- Making the authority table a projection — blocked on two coverage gaps, and after the merge.
- Stage 7 of `design/reviewer-registry/DESIGN.md` (the receipt producer) — unrelated to the merge
  and blocked on its own schema question.

## Reproducing the state claims

```bash
git merge-base origin/main ontology-seed                      # a279e26
git diff --shortstat $(git merge-base origin/main ontology-seed) ontology-seed
git merge-tree --write-tree --name-only origin/main ontology-seed
```

47 commits, 81 files, +15,886 / −255. Eight conflicts: `AGENTS.md`, `CLAUDE.md`,
`IMPLEMENTATION_MAP.html`, `LEXICON.md`, `gates/goldens/review-matrix.json`,
`gates/test-assemble.sh`, `install.sh`, `launch/agent-launch.toml` — reproduced by a real trial
merge, not only by `merge-tree`.

Both sides were green before the merge: `ontology-seed` (parity; ontology 38/49/9 and 55/55
self-test; lexicon 193 files, 14 tokens, 8 homes; package 26 runtime paths, 4 exempt, 9
author-side) and the trunk at `52d2a95` (parity, package, lexicon, `record-decision --check` and
`--self-test`).
