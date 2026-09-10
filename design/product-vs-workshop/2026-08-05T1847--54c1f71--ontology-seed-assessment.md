---
created_at: 2026-08-05T18:47:48+09:00
head: 54c1f71
branch: spurious-captain
kind: design
supersedes: none — first assessment of ontology-seed against this branch
---

# Can we take `ontology-seed` on our terms?

Read from artifacts and diffs at `ontology-seed` = `b583945`, against this branch at
`54c1f71`. **Not verified by running their suite** — no gate of theirs was executed,
so every claim here is about what the files say, not about what passes.

47 commits, 81 files, +15,886 / −255 since the shared base `a279e26`.

## It is three workstreams, not one

| Stream | Size | What it is |
| --- | --- | --- |
| `ontology/` | ~10k lines | An instance-bearing dependency graph of this repo, extracted from real code. `impact.py <entity>` answers "what else must move with this", `--diff` finds obligations where one side moved and the other did not. |
| Receipt / reviewer adapters | ~1.5k | Continues the reviewer-registry: a receipt contract, `wrappers/claude-run.sh`, `gates/check-receipt-chain.py`. Evidence declared per offer, checked per receipt. |
| Repo hygiene | ~1.5k | `SURFACES.md`, `FINDINGS.md`, `design/archive/` with an enforced convention, backup pruning, uninstall treated as a security operation. |

They can be judged and absorbed separately. Nothing forces them to arrive together.

## Are the principles ours?

Yes, to a degree that reads as the same lineage rather than agreement. Their commit
subjects are this repo's own discipline stated from another angle:

- *"The extractor read one author and reported that author's world as the world."*
- *"A value nobody reads is a defect only if a gate was supposed to read it."*
- *"An enumeration that happens to excludes something has not named it."*
- *"The audit's biggest hit was the auditor holding its own copy of the vocabulary."*
- *"Position decays and content does not — anchors are addressed by what they name."*
- *"Twenty-nine of thirty dead functions were the sweep's error, so the sweep does not become a gate."*

That last one is our own "hard-block only decidable violations", derived independently
from a false-positive sweep. And `ontology/domain_scope.md` states the facts are
"extracted from real code, never authored", with anchors "verified, never assumed" —
the same rule this branch spent the day enforcing on itself.

**Strongest evidence of convergence:** their `design/archive/README.md` names the
*same defect this branch fixed today* — `design/session-distill/HANDOFF.md` claiming
current state while its counts had moved. Two branches, independently, found the same
rotten artifact. Their fix generalises: a directory where nothing is ever edited to
stay current, a lexicon exemption so historical prose keeps its words, and a gate that
forbids any runtime file pointing into it. Ours was narrower: restore the July text,
move the re-derivation to a dated file.

### Where they genuinely differ from us

1. **What `AGENTS.md` is.** Theirs is a **map** — subsystem inventory, commands,
   where things live. Ours is **working rules** — what is ENFORCED versus CONVENTION,
   and how to not fool yourself. Our own "What goes where" table assigns the map to
   `README.md`. Both cannot own the file. This is the only disagreement at the level
   of concept ownership, and it is a decision, not a merge.
2. **`FINDINGS.md`** — a live queue of open defects where closing an entry means
   deleting it. We record decisions instead: append-only, each closing an alternative.
   Different concepts (open defects vs closed choices), but both answer "where is
   outstanding work written down", so leaving both unreconciled would give two
   answers.
3. **Dated records.** Their `design/archive/` prefix + gate versus our
   `design/<initiative>/<ts>--<sha>--<slug>.md` filename convention. Same intent,
   two mechanisms. Keeping both would be the near-duplicate concept both branches
   otherwise refuse.

None of these is a contradiction of principle. All three are one concept with two
homes, which is exactly the thing to resolve before merging rather than after.

## Do we need it?

**The ontology: yes, and today is the argument.** Its stated failure mode —

> "I knew what I was changing, and I did not know the other four places that had to
> change with it"

is what this branch cost itself four times in one day:

| What was missed | What would have named it |
| --- | --- |
| `packaged_mode()` is about a domain selection, so the assembler filter missed the default install | an edge from the filter to *both* deploy paths |
| `verify` demanded presence of a guide the deploy had begun withholding | an obligation between deployer and verifier |
| the packaged path prunes `central/guides`; the full-mode copy lives elsewhere | the two destinations as separate anchors |
| a preset declares `audience = "author"` and no launcher code reads it | `impact.py --diff` — one side moved, the other did not |

Each was found by an external reviewer, one at a time, at review cost. A dependency
graph is the mechanism that finds that class without paying per instance.

**The receipt work: probably, but check first.** It continues something already
shipped, and this branch just deferred a neighbouring item (D-0034, the launcher's
missing reader for a preset's audience). Whether their receipt work already crosses
that deferral is unknown and worth reading before absorbing.

**The hygiene stream: yes, but it is the overlap.** This is where the duplicate
concepts are, so it is absorbed by deciding, not by merging.

## Conflict versus creation

Re-derived with `git merge-tree HEAD ontology-seed` at `54c1f71`. Eight files, up from
the four the earlier handoff recorded — this branch's `install.sh` and
`test-assemble.sh` work added two, and the `agent-launch.toml` mission edit a third.

**Resolve as conflicts** — both sides changed the same thing:

| File | Nature | Resolution |
| --- | --- | --- |
| `CLAUDE.md` | add/add, both `@AGENTS.md` | not a real conflict; keep ours, it says why the bridge exists |
| `gates/goldens/review-matrix.json` | both regenerated it | do not merge — regenerate with `gates/capture-review-goldens.py` after the rest lands |
| `launch/agent-launch.toml` | our mission edit vs their +21 | textual, small |
| `install.sh` | ours +76 (withholding, prune, stderr) vs theirs +165/−69 | the real merge; both restructured deploy and uninstall |
| `gates/test-assemble.sh` | both added scenarios | additive, order only |
| `IMPLEMENTATION_MAP.html` | both refreshed the dashboard | regenerate from the merged state rather than merging claims |
| `LEXICON.md` | ours +6/−2 vs theirs +7/−3 | small textually, but see the layering decision below |
| `AGENTS.md` | add/add, 168 vs 375 lines, different purposes | **a decision, not a merge** |

**Create instead** — no counterpart on the other side, so nothing to reconcile:

- theirs only: `ontology/`, `SURFACES.md`, `FINDINGS.md`, `wrappers/claude-run.sh`,
  `gates/check-surfaces.py`, `gates/check-receipt-chain.py`, `compose/prune-backups.py`
- ours only: `decisions/`, `gates/test-install-guides.sh`, the package gate's
  `--self-test`, the `audience: author` withholding across both install paths

**Decide before merging, because a merge cannot answer them:**

1. Where the repo map lives — their `AGENTS.md` content into `README.md`, or our
   working rules move out. Our own table already answers this; theirs was written
   without it.
2. Whether `LEXICON.md` becomes a projection of the ontology's entity layer. They
   state it should and that `check-lexicon.py` would change input, not behaviour.
   That is coherent, but it makes the ontology load-bearing for a gate we currently
   own outright.
3. Whether `FINDINGS.md` and `decisions/` are one concept or two. They are two —
   open defects and closed alternatives — but that needs saying once, in one place.
4. Whether dated records use their directory prefix or our filename convention.

## Order

The agreed order still holds and is now better justified: **this branch merges first**,
then `ontology-seed` absorbs main with `git merge` rather than a rebase, so its 47
commits are not replayed. Their ontology would otherwise be extracted against an
`install.sh` that is about to change underneath it — and the install path is exactly
what its first useful answer is about.
