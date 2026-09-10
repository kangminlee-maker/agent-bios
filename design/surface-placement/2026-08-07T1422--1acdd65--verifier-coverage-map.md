---
created_at: 2026-08-07T14:22:00+09:00
head: 1acdd65
kind: design
supersedes: none — first verifier-coverage map
---

# What can go wrong in the product, and where the verifier stops being able to see it

The question this map exists to answer is not "what does the system do" but **"is there a product
error the verifier cannot catch, and why not."** So the rows are product-defect classes and the
finding for each is a *reason* the verifier misses it, expressed as one of a small set of failure
modes. The failure modes are the improvement lever: closing one closes it for every row it touches.

Every mode below was **observed in this repository**, not imagined. Where a mode is proven by a
planted experiment, the experiment is stated so it can be re-run.

## The verifier's failure modes

| id | mode | proven how | detected today by |
| --- | --- | --- | --- |
| **V1** | **silent skip** — a leg guarded by `if [ -f subject ]` disappears when the subject does, and the umbrella still reports OK | deleting `SURFACES.md` in a clone **and staging it**: umbrella prints `PARITY OK`, exit 0, zero mentions of surfaces. Staged is the condition that counts — the hook judges the index | **nothing** |
| **V2** | vacuous pass — the check ran over an empty subject set | — | non-vacuity assertions, present in `check-domains` (9), `test-assemble` (1), `check-prompting-targets` (1); absent in `check-package`, `check-lexicon` |
| **V3** | tautological oracle — the expectation imports the predicate it is asserting | planting "core is no longer universal" in `assemble.audience()`: output drops 44→19 bullets, suite exits 0 | nothing mechanical; found by external diff review |
| **V4** | neighbour catch — a negative control passes because a *different* check fires on the same mutation | two controls this session; both survived a faithful revert of the check they named | **the revert test — prose only** (2 mentions in the working rules) |
| **V5** | proxy assertion — asserts a stand-in that holds while the real property breaks | `tooling-gotchas-hook.py` is asserted by "file copied" + "registration string present"; nothing invokes it with an input | nothing |
| **V6** | unreachable check — the check exists, has a subject, and does not run before the defect ships | `launch/check-prompting-targets.sh` is in neither the pre-commit hook nor the umbrella; 12 of 13 checks are reachable, it is the one that is not | nothing |
| **V7** | one-direction closure — a relation is checked one way and declared closed | bullet→guide was gated while guide→guide was not, in the same file, the same week | nothing |
| **V8** | stale typed expectation — a hand-written count that rots | six assertions broke across two changes this session | partially: derived expectations, where they exist |
| **V9** | wrong subject set — the check scans a tree that is not the one that ships | `check-lexicon` builds from `git ls-files`, so an untracked file is unscanned | prose (`git add -N` advice) |
| **V10** | no check at all | see the uncovered rows below | — |

## Product-defect classes, and what stops the verifier seeing each

`S` = structurally checked · `M` = semantically checked (is it *right*) · the last column names the
failure mode that explains the gap.

### On the forward path

| product defect | S | M | why the verifier misses what it misses |
| --- | --- | --- | --- |
| a rule is wrong, stale, or unsafe | lexicon, surfaces, ontology, doc phrases | **none** | **V10 by design.** The payload *is* the product, and every S-check propagates a wrong rule faithfully. This is the largest hole and the repo declares it deliberately |
| a rule sits on the wrong surface (global vs guide vs gate vs hook) | catalog↔code drift only | **none** | **V10.** `SURFACES.md` + `check-surfaces.py` gate whether the catalog matches the code, never whether a given rule chose right. Fired at 35 rules this session |
| a bullet is classified into the wrong tier/domain | bijection, legality, both router directions, self-tested | none — a legal but wrong domain passes | strongest coverage in the repo; the residual is **V10 on M** |
| a mirror or translation diverges | `emit-mirrors --check` + self-test | translation *meaning* unchecked | **V10 on M** |
| a selection receives the wrong set | scenario suite, contrast pairs, derived oracle | — | was **V3** until this session; the oracle now restates the contract |
| a runtime path is not packaged | three directions, planted-violation self-test | — | covered |
| **the published artifact is not the checked tree** | **none** | none | **V10.** Already bitten: a release was published from an uncommitted tree |
| migrate damages user-owned content | unit self-test only | — | **V5-adjacent.** The install scenarios stand up a real installer against a real temp HOME and assert nothing about migrate, which is the destructive step |
| the launch contract binds wrong | ~26 fixtures | — | **V4 risk**: the fixture harness itself has no `--self-test` |
| a model is bound with no prompting guide | the check exists | — | **V6.** It runs only at install time, so the commit lands clean |
| review routing or receipts are wrong | receipt chain over a derived preset×host space, self-tested | reviewer judgment unverifiable | covered structurally |
| **the always-firing hook is broken** | file copy + registration string | **none** | **V5.** A hook that crashed on every invocation passes every gate in this repo |
| a rule ships but never fires | orphan-guide check proves *something points at it* | none | **V10.** "pointed at" is not "followed" |

### On the return path — the loop edge a pipeline cannot hold

| product defect | S | M | why |
| --- | --- | --- | --- |
| a learning leaks a secret | redaction floor, schema, intake, each self-tested | — | covered |
| promotion deletes the wrong personal content | `migrate-learnings --self-test` | — | **V1 exposure**: the leg is `if [ -f learn/migrate-learnings.py ]` |

### Meta

| product defect | S | M | why |
| --- | --- | --- | --- |
| the repo's own rules are wrong, so every future change inherits it | anchor phrases, layout, lexicon, ontology | partial and **drifting now** | two live contradictions, below |
| a host CLI, model, or fact changes underneath | prompting-targets (install-time only), environment bindings | none | **V6 + V10** |

## Live contradictions in the repo's self-description

Found while checking the rows, each verified against the tree:

- **`ko/`**: the working rules call all of it payload "deployed to other machines"; the umbrella's
  own header says "KO reference (never installed)"; `files[]` omits it; `install.sh` mentions
  `$REPO/ko` exactly once, as a gate guard. The working rules are the wrong one, and they are what
  a new reader reads first.
- A working-rules citation for where verify re-runs the gates is ~125 lines stale.

## What to change, in order

Ranked by *how many product-defect rows a fix uncovers*, not by how alarming it sounds.

1. **V1 — assert every declared leg actually ran.** Proven live: deleting one subject removes its
   leg and the umbrella still says OK. The umbrella asserts ten required subjects up front
   (`gates/check-parity.sh:19-26`) — four directories and six files — and **none of them is the
   subject of any of the fourteen legs written as `if [ -f subject ]`**. The repo already states
   the reasoning at `:116-118`, and applied it to exactly one leg, `test-install-guides.sh`, which
   is why that one sits in the required list instead. Extending the list to every leg's subject is
   the whole fix. This mode silently removes coverage from *any* row above, so it outranks every
   individual gap.

   The unstaged deletion *is* caught, but for an unrelated reason: the lexicon gate builds its file
   set from `git ls-files` and trips on a tracked file that is missing from the worktree. That is
   V9 masking V1, and it stops masking the moment the deletion is staged — which is exactly the
   state the pre-commit hook evaluates, since it runs the gates against the index.
2. **V6 — make reach a checked property.** One check is unreachable at commit time today. The
   reach table is computable from script references; a gate can require every check to be
   reachable or explicitly declared install-time-only.
3. **V4 — make the revert test a recorded step, not prose.** It is the only thing that caught the
   fake controls, it caught both, and it lives in two sentences of a document. At minimum a
   self-test should record that each control was shown MISSED under revert.
4. **V5 — one invocation test for the hook.** The single mechanism that provably fires every
   session, and the cheapest row here: one file, one input, one assertion.
5. **Publication provenance.** Bind the published artifact to a commit; the repo has already
   shipped a release traceable to nothing.

**Deliberately left open:** `M` on the payload and on surface choice. Proving a rule is *right*
needs a judge nobody has built, and proving a deployed rule *changes behaviour* needs live
sessions. Both are out of proportion for a single-user tool. Recorded as a decision so the next
reader knows it is a choice.

## Re-run rather than believe

```bash
# V1, the headline: delete a guarded subject in a CLONE and watch the umbrella stay green
git clone --no-hardlinks . /tmp/v1 && cd /tmp/v1 && rm -f SURFACES.md && git add -A \
  && ./gates/check-parity.sh; echo $?    # staged — the state the hook evaluates

# V6: which checks are reachable from the pre-commit hook, and which only from install.sh
grep -o '[a-z]*/[a-z_-]*\.\(py\|sh\)' .githooks/pre-commit gates/check-parity.sh gates/check-package.sh | sort -u

# V5: what actually references the hook
git ls-files | grep -E '\.(py|sh|json)$' | xargs grep -l tooling-gotchas-hook
```

Four of this document's own probes were wrong before they were right — a grep that spanned a line
break, a plant that missed a second source, a path filter that let an untracked worktree in, and a
clone without `.git`. Each looked like a finding until it was re-run. Re-run these.
