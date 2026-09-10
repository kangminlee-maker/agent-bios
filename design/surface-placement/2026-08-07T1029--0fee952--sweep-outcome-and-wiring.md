---
created_at: 2026-08-07T10:29:00+09:00
head: 0fee952
kind: design
supersedes: 2026-08-06T2136--0fa0ce3--coverage-audit.md
---

# The sweep is done for four sections, and the wiring holds — but one check nothing enforces is what found the last gap

The coverage audit this supersedes answered "can each rule move without losing content". It was
right about that and wrong about something more basic: its **target guide** column named the
nearest *legal* guide rather than the concept's *owner*, so eighteen rules from two different
global sections were all headed for `coding-staged-workflow`. That column is void. What replaced
it is the step the initiative had skipped — deciding the guide inventory first, recorded as
**D-0043**.

**Two corrections to that record, held here rather than written into it.** Its summary reads
`partial 6 / author 19`; its own tables hold `7 / 18`. The total is right, so nothing downstream
moved, and the seven are: smallest viable path · define success criteria · narrowest reliable
test · case space from the artifact · falsifiable completion criteria · adversarial review and
convergence · git fetch, range and sibling PRs. The correction was first made by editing that
file, which is what the write-once rule forbids and what this paragraph exists to undo — a dated
record whose contents move is no longer a claim about the date on its label.

## Where the corpus landed

| | at the design record | now |
| --- | --- | --- |
| always-loaded bullets | 113 | **77** |
| guides | 14 | 17 |
| `builder-base` reader receives | — | 44 bullets, 8 guides |
| `core+infra` reader receives | — | 25 bullets, 1 guide |

Per section, `builder-base`:

| section | before | now | what happened |
| --- | --- | --- | --- |
| Concept Economy | 16 | 2 | new guide; the survivor fires while you believe you are fixing a finding |
| Coding Guidelines | 14 | 4 | one section authored into the existing guide; two rules deleted against an existing authority |
| Verification Discipline | 13 | 5 | new guide, which also took back the 54% of `coding-staged-workflow` that was already verification |
| Tooling and Operational Safety | 7 | 6 | only the git-range rule moved, into the guide that already held its neighbouring trap |
| Documentation Hygiene | 6 | 2 | new guide |
| **builder-base total** | **56** | **19** | |

Both columns are `git show`n from `origin/main` and `HEAD` and counted, not tallied by hand —
the first draft of this table said Coding 5 and Tooling unchanged at 7, and both were wrong.

**Tooling barely moved, and the design record's reason for that was wrong.** It said an unknown
trap is exactly what you cannot look up. True, but not why these stayed: reading
`tooling-gotchas.md` against them, the guide does not hold their content. Two cross-family
reviewers voted to move two of the six on the assumption that it did. The rules survive on
coverage, not on the argument originally given for them.

## What the guides gained that no bullet said

Authoring is not relocation, and the difference shows up as content that did not exist before:

- The procedure for finding the nearest existing concept — search for the behavior the concept
  would produce, because searching for the name you already invented returns nothing and reads
  as permission.
- That a comment describing a superseded contract is not stale documentation but a **second,
  false authority** — the answer, to whoever reads it first.
- That a continuously overwritten "current state" document claims to be now and is no particular
  time; where the facts are derivable, hand over the command that re-derives them.
- The five shapes that produce a green with nothing behind it, and the one discipline that covers
  all five: revert the fix and watch the check fail.

## Wiring: every guide has a consumer, and every reference resolves

Audited at `0fee952` across all five single-domain selections, the full selection, and the
`core+infra`-only path, on both the claude and codex sides.

- **17 of 17 guides have a named consumer.** Thirteen from a global bullet, three from a parent
  guide as a legitimate depth chain (`llm-capability-boundary`'s two children,
  `svg-visualization-guide`), one from a launch preset (`session-distill-workflow`, which is
  `audience: author` and withheld from installs by design). `verification-discipline` has two —
  a global router and a pointer from `coding-staged-workflow`.
- **14 pointer→guide pairs, every reader guaranteed the file.**
- **Every selection resolves every reference**, prose handles included, with no guide delivered
  to one host and not the other.
- **One bullet never assembles** — the `env-personal` Korean-response preference, which is
  declared as never-assembled and is the tier's whole purpose.
- **The hook is registered** in `settings.json` and its `source_guide` is claimed.

### The check that found this class, and which nothing enforces

The gates ask bullet → guide (does the reader have what the pointer names) and file → manifest
(is every file claimed). Neither asks the reverse: **does anything point at this guide at all.**
That is the question that leaves a guide inert, and this session created exactly that state twice
before wiring it — a guide written, packaged, shipped, and read by nobody.

Both directions were shown to fail on planted violations. Stripping a router makes the audit name
the inert guide; pointing a `builder-base` bullet at a `visualization-docs` guide is caught, but
by the existing domain gate as much as by the audit, so that leg is a restatement rather than new
coverage. **The inert-guide check is the one worth promoting into a gate**, and it is
deterministically decidable, which is the repo's bar for blocking. It is not gated today.

## What remains

| | count | why it is where it is |
| --- | --- | --- |
| Tooling rules, global | 5 inline + 1 router | the guide does not hold them; verified by reading, not by probe |
| Rules kept global elsewhere | 7 inline + 6 routers | each survivor fires in a moment the agent categorises as something else |
| Inert-guide check | — | proven, unenforced; promoting it is a decision, not a cleanup |

Documentation Hygiene's remaining question is not placement. `Phrase guidelines as desired
behavior` governs writing rules rather than writing software, and a reviewer's suggestion that it
does not belong in a builder domain package at all was recorded and not acted on.

## How to check this rather than believe it

```bash
python3 compose/check-domains.py            # bijection, file coverage, router co-package
./gates/check-parity.sh                     # mirrors, guide sets, frontmatter, anchor pairs
python3 compose/assemble.py --claude-dir /tmp/x/claude --codex-dir /tmp/x/codex \
        --state-dir /tmp/x/state --domains builder-base
```

The last one is the only one that answers "what does a reader actually receive", which is the
question every claim in this record is about. The bullet and guide counts above are its output,
not a tally kept by hand.
