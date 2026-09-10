# Handoff — reviewer-registry, 2026-08-04

Dated record. True as of 2026-08-04 and never revised; read it as history, not as state.

**State is not here on purpose.** What is decided lives in `design/reviewer-registry/DESIGN.md`
(`Corrections`, `Open evidence`); what is open in the product lives in the repo-root `FINDINGS.md`;
what the ontology holds lives in `ontology/instances/graph.json`. This file says only where the
work stopped, what the next step is, and what it cost to learn.

## Where you are

- Repo `~/Documents/agent-bios`, branch **`ontology-seed`**, HEAD **`870fbd4`**, 39 commits ahead
  of `main`, working tree clean apart from four intentionally-untracked directories
  (`.claude/`, `research/`, `design/review-process-learnings/`, `design/reviewer-registry/reviews/`).
  **Never `git add -A` here.**
- **Nothing is deployed.** The machine runs the previously installed corpus.

Verify before trusting any of it:

```bash
cd ~/Documents/agent-bios
./gates/check-parity.sh                          # includes check_parity.py and the review goldens
python3 ontology/check-ontology.py && python3 ontology/check-ontology.py --self-test
python3 gates/check-lexicon.py && bash gates/check-package.sh
```

All green at the time of writing; the ontology self-test held 55/55 and the review golden 254 cells.

## The next step, and its shape

**Shim observation.** `exec_backend` hands an env dict to the host CLI before `os.execve` replaces
the launcher (`launch/agent-launch.py`, the `env["AGENT_LAUNCH_ACTIVE"] = "1"` site). Prepending a
recorder directory to `PATH` there makes every reviewer the session dispatches *by name* pass
through a recorder that execs the real binary and records argv, exit status and an output hash.

The owner approved building it **behind a default-off switch**, on the grounds that it changes the
execution environment: a mistake breaks the session itself, and after a deploy the revert is not
immediate.

Two things to keep straight while building it:

- **Observation is not dispatch.** The reviewer's isolation is from the *designing* context; a
  passive recorder puts nothing into the reviewer's context and does not break I2. This was the
  reframing that unblocked the whole line — do not re-derive it as "the launcher must dispatch".
- **The existing zsh interception does not cover this.** `launch/agent-launch.zsh` defines shell
  *functions* `codex()`/`claude()`, and functions are not inherited by subprocesses, so today's
  hook catches what a user types and not what an agent dispatches. `PATH` is inherited, which is
  why the shim goes there.

Coverage, measured: `codex-run` (ours already), `claude -p`, and command-invoked workflow tools are
observable. **MCP is not** — its dispatch is a JSON-RPC message inside a stdio pipe opened once at
session start, so a `PATH` shim sees the server start and never a review. That gap is what C53's
evidence contract addresses from the other side.

## What was decided this session, so it is not re-litigated

`DESIGN.md` `Corrections` C45–C53 carry the reasoning. In one line each:

- **C45** — owner decision in four parts: a capability floor exists (workhorse minimum, helm
  recommended); I2 stands; a second provider stays the user's choice and the launch screen must say
  it is most effective; specialised tools are accelerators, not rungs.
- **C46** — the status header was three stages behind the code; stages 6 and 8 are built and 8 was
  executed, and C7's blocker was answered by host-relative *arms* (`REVIEW_ARMS_KEY`).
- **C47 / C51** — the floor is a grade cap, not a gate, because it is a cost decision and is
  undecidable for an untiered binding. The perspectives half is **disclosed, not capped**, because
  `perspectives` counts lenses *requested* and a fan-out tool is not described by that number.
- **C48** — the design review had already run (2026-07-27, 23 agents, 16 surviving findings) and
  was never triaged; the claim that it never ran was inherited from a handoff written the day after.
- **C49 / C50** — all 16 findings adjudicated against real code: **nine distinct defects**, of which
  D is half-fixed and E is a recorded decision rather than a defect.
- **C52** — `availability` is a launch-time projection again; achievement carries its own
  none/partial/complete coverage, because partial and never-verified were the same value.
- **C53** — evidence is declared per offer and checked per receipt. It buys **drift, not honesty**,
  and gets version scoping without a version probe.

Still open from the nine: **A** (receipt evidence unauthenticated) and **B** (registry assertions
trusted as core guarantees) are load-bearing; **C**, **F**, **G**, **I** are narrower; **D**'s
perspectives half and **E**'s decision-to-re-read remain.

## Traps this session paid for

- **`git checkout <file>` reverts the whole file, not your experiment.** Undoing a falsification
  probe this way destroyed three uncommitted edits in the same file. Back up to the scratchpad and
  restore from there; file-level revert does not aim at what you planted.
- **A green suite over shipped config proves nothing about a new branch.** Three changes in a row
  left the review golden byte-identical because shipped presets never reach the new code — which
  means the branch never ran. Every one needed a planted control, and each was proven by deleting
  the branch and watching the control fail.
- **Prove the *declaration* is read, not just the check.** For the evidence contract, deleting the
  field list from the profile had to make the control pass; otherwise the check could have carried
  its own copy and looked identical.
- **The document was wrong three times, in the same direction.** Stages 6–8 "remaining", a redeploy
  already done, and a cross-reference pointing at the wrong list entry. Measure before acting on
  any claim in a design doc, including one written hours earlier by you.
- **Dates: I wrote 2026-08-01 into five corrections on 2026-08-03.** Check the real date before
  stamping a record.
- **`gates/check_parity.py:4821` flakes** — failed once, never reproduced, and its assertion ORs
  four conditions behind one message so the failing run could not say which fired. Filed as F-15.
