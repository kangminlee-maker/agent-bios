---
created_at: 2026-09-01T09:51:11+09:00
head: 23e3920
branch: main
kind: handoff
supersedes: 2026-08-31T1636--db5e745--release-and-model-currency.md
---

# Self-contained handoff — everything needed to continue, in one file

**Written to be read where this repo's corpus is NOT loaded** (the ChatGPT desktop app, a
fresh session, another machine). It assumes you know nothing about this project. Where a
claim can be re-derived, the command is given; prefer the command over the claim, because
this file is a snapshot of `23e3920` and stops being current the moment something lands.

It is dated in its filename on purpose. A standing `HANDOFF.md` in this repo once declared
itself the single source of truth while reporting one number two different ways and a third
in the artifact; a file whose name carries its timestamp cannot rot that way.

---

## 1. What this project is

`agent-bios` is an npm package that **deploys instruction files to a developer's machine**
so that Claude Code and Codex sessions load a shared set of working rules. The product is
the instructions themselves.

The one distinction that causes the most confusion:

| | |
| --- | --- |
| **Payload** — what ships to users | `claude/`, `codex/`, `ko/`, `claude/skills/` |
| **Author-side** — never ships | `gates/`, `ontology/`, `decisions/`, `design/`, `benchmarks/` |
| **How to work in the repo** | `AGENTS.md` (root) — imported by root `CLAUDE.md` |

`claude/CLAUDE.md` is the deployed global: ~20,350 characters (~5,100 tokens) re-sent every
session and to every subagent. `codex/` is a **generated projection** of `claude/` — never
hand-edit it; edit `claude/`, then run `python3 gates/emit-mirrors.py`.

## 2. State at `23e3920` (2026-09-01)

| | |
| --- | --- |
| HEAD, and `origin/main` | `23e3920` — in sync, tree clean |
| Released | **v0.14.0**, published to npm, deployed and verified on the author's machine |
| Deployed marker | `{"version":"0.14.0","source":"package","commit":"db5e745…"}` |
| Findings queue | **F-16 open** (see §5) — the only entry |
| Commit gate cost | ~4–6 min (was 50m26s until 2026-08-31) |

Eight commits landed on 2026-08-31 – 09-01: the gate speedup, the v0.14.0 release, the TUI
update badge, the prompting source pins, and the guide re-derivation.

## 3. Re-derive before trusting anything here

Only possible with repo access. If you do not have it, treat §2 as dated and say so rather
than asserting it.

```bash
git log -1 --format='%h %s'                          # expect 23e3920 or later
git status --short                                    # expect empty
agent-bios status                                      # expect deployed 0.14.0, no DRIFT
bash gates/test-install-guides.sh                      # expect 104 PASS / 0 FAIL, ~70s
python3 gates/check-prompting-sources.py --self-test    # expect 9/9
python3 gates/check-prompting-sources.py --online       # vendor docs vs their pins
./gates/check-parity.sh                                 # the umbrella, ~4 min
```

**The commit gate takes minutes, not seconds.** `.githooks/pre-commit` runs the whole
umbrella. Launch a commit detached (`subprocess.Popen(..., start_new_session=True)`) — a
foreground tool call is killed at its cap and the commit dies with it. Never
`pkill -f check-parity` while a commit runs; that kills your own commit.

## 4. The four open items

### Item 1 — ChatGPT desktop app cannot select a corpus  ← **you may be able to answer this one**

`agent-bios install` shows a terminal UI that lets the user pick which instruction domains
to deploy. A session started from the ChatGPT desktop app never sees that UI, so on that
path the user gets something they did not choose — or nothing.

**Nothing here has been investigated. There is no design.** Three questions, in order:

1. Does a ChatGPT desktop session load any agent-bios content at all? The deployed Codex
   entry point is `~/.codex/AGENTS.md`, which carries a region marked
   `agent-bios:central:start`.
2. If it loads, from which path?
3. What did the user actually miss — no corpus at all, or a corpus with no way to choose
   domains?

**If you are running inside the ChatGPT desktop app, you can answer 1 and 2 by observing
yourself**, which no other session can do: report what instructions you actually have, and
whether anything resembling the region marker above is among them. Say plainly if you
cannot tell — "I cannot see my own system prompt" is a real and useful answer here, and far
better than a guess. Question 3 is the user's to answer.

### Item 2 — re-derive the two prompting guides  ✅ DONE 2026-09-01

Kept here only so it is not re-opened. `claude/guides/claude-prompting.md` and
`gpt-prompting.md` were reconciled against their vendor sources at pinned hashes. **They
were not stale — they were incomplete**; the audit's inference from "never re-derived" to
"wrong" was not supported. What was missing: the whole "running with thinking disabled"
section on the Claude side, and the whole "programmatic tool calling" section on the GPT
side, plus deterministic subagent caps, prompt-contradiction review, and several others.

### Item 3 — Stage 2 scope: the owner's open decision

There is an experiment harness in `benchmarks/` that removes one rule from the corpus,
re-runs scenarios, and scores whether behaviour got worse. It answers two different
questions: does a rule still work (regression), and is a rule still needed (obsolescence).

An external survey on 2026-08-31 found **no existing tool supports the second question** —
promptfoo, DeepEval, Inspect, Braintrust, LangSmith, Langfuse and W&B all do regression and
model-variation only, and Braintrust calls instruction-trimming manual in its own docs. So
this harness is unusual and worth finishing.

The decision, unchanged and not taken:

| | Scope | Cost |
| --- | --- | --- |
| **A** | Stage 2 as designed | ≈1,760 responses, ≈35 h serial |
| **B** | reach only — 13 items, current vs restored | ≈832 responses |
| **C** | derivability only | — |
| **D** | stop; keep the guide split and the ledger correction | 0 |

An independent cross-family reading returned **B**. Its own cheapest suggestion was smaller
still: run the four T-class items among the 13 first (`S2-02`, `S2-14`, `S3-35`, `S3-36`) —
the registered prediction says they regress, and if they hold, the value of the larger run
collapses too. Full reasoning: `design/session-distill/2026-08-31T0613--16a5a93--stage2-revalidation.md`.

### Item 4 — commit-gate timing  ✅ RESOLVED 2026-09-01

Three measurements: 5m59s, 13m11s, 4m25s. The 13-minute run did not reproduce; the
improvement from 50m26s holds. The cause of the outlier was never proven and is not worth
chasing.

## 5. F-16 — the live finding, and the most important thing in this file

**The deployed global and the guide it tells the model to read give opposite instructions.**

- `claude/CLAUDE.md`: *"Independence: verifying or reviewing your own work **always spawns**"*
- `claude/guides/claude-prompting.md`: *"Do **not** add … a dedicated verifier subagent"*

The guide is faithful to its source. Anthropic's `prompting-claude-opus-5` names *"use a
subagent to verify"* as its own example of an instruction to delete, and says plainly: *"do
not use subagents to verify or double-check your own work."* The launch profile binds
`claude-opus-5` at the helm tier. Both hosts load the global; the Claude host also loads the
guide.

**Do not close this by editing one side to match the other.** The two rules answer different
questions. The vendor's concern is cost — over-verification burns tokens with no measured
quality gain. This repo's concern is a false PASS: its own recorded experience is that
self-verification produced readings that were wrong *and agreed with each other*, which is
exactly why they survived. Both can be true at once.

Four alternatives are written out in `FINDINGS.md`. One of them is to measure it, on the
harness from item 3, where this clause is a single arm.

## 6. Working rules that will NOT be loaded for you

The deployed corpus is not present in a ChatGPT desktop session. These are the few rules
that actually govern the open work; the rest is in `claude/CLAUDE.md` if you have the repo.

- **Re-derive load-bearing claims from real code or data.** Treat handoff claims (including
  this file), prior diagnoses, reviewer findings, and your own earlier conclusions as
  hypotheses. Record a dated correction when one is overturned.
- **A green check means "it ran", not "it checked your change."** Assert the subject set is
  non-empty before any "no bad X" claim; an empty set satisfies everything.
- **When a measurement agrees with your expectation, that is the moment to test the
  instrument** — not the moment to stop. Disagreement forces you to inspect the probe
  anyway, so instrument bugs producing false *passes* are the ones that survive.
- **Block only on what is deterministically decidable.** Route judgement calls to a
  non-blocking disclosure. A gate on a judgement call is one people learn to route around.
- **Never weaken a security or authority posture as a rote edit** — state the consequence
  and a safer path, and get explicit confirmation first.
- Explain choices in outcome terms — what changes, what it costs, what risk, and a
  recommended default — not in jargon.

## 7. Traps that each cost a real attempt

- **`npm i -g agent-bios@X.Y.Z` silently keeps an `npm link`.** If the global install is a
  symlink to a clone, npm sees the version already satisfied and does nothing, and every
  later version check reads the clone and agrees with itself. Prove it with
  `npm ls -g --link`, or by the presence of `gates/` under the install — `gates/` never
  ships.
- **`install.sh` runs under `set -euo pipefail`.** A tolerated command in a pipeline aborts
  the function unless you write `|| fallback` explicitly. This shipped a broken offline path
  that the success path hid completely.
- **Editing `install.sh` makes `ontology/ONTOLOGY_MAP.html` stale** — it embeds live line
  numbers. Run `python3 ontology/emit-map.py` after the last edit and stage the map with it.
- **A new untracked file breaks `check-package.sh --self-test`**, which copies every
  `git ls-files` path; the failure is reported as "self-test missed a planted violation" and
  names nothing useful. `git add` the file first.
- **A negative control that indexes live data dies when the data changes.** One here
  asserted a warning fired on the real guides; re-deriving them made it fail. Controls must
  build their own subject.
- **The Bash tool is zsh**: `$var` does not word-split. A loop that reports uniform results
  is a reason to check the instrument first.
- **Adding a path to `package.json` `files[]` moves a derived ontology count.** Re-measure
  with `python3 ontology/extract.py`; never edit the number to match the error.

## 8. If you can only do one thing

Answer item 1's questions 1 and 2 by observing your own session, and say clearly which parts
you could not determine. That is the only item on this list that a session in the ChatGPT
desktop app can settle and a session anywhere else cannot.
