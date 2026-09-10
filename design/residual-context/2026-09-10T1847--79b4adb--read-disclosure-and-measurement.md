---
created_at: 2026-09-10T18:47:20+09:00
head: 79b4adb
kind: design
supersedes: none
---

# A large read discloses its cost before it happens, and what would have to be measured before it may block

Spotify's engineering blog published *Portal by Spotify cut my Claude Code token usage by 90%*
on 2026-09. Its mechanism is a PreToolUse hook that **blocks** any `Read` over 350 lines and
redirects the agent to a cheaper model that reads the file and returns a summary. This record
takes the mechanism, declines the block, and states what would have to be true before the block
becomes the right shape here.

## What is built

`claude/hooks/residual-context-hook.py`, registered on `PreToolUse` / `Read`
(`compose/domains.json`, `claude/settings.template.json`). When an unbounded `Read` would pull
more than a threshold of bytes into the main context, the hook injects one sentence naming the
size, the *Residual context* gate of `guides/cli-multi-model-workflow.md`, and the fact that an
edit still needs the bytes. It never blocks, never rewrites, and never judges whether this
particular read should be delegated.

That is the hook charter of `design/session-distill/PLACEMENT-FRAMEWORK.md`, quoted whole
because it decided the shape before the article was read: *"Only sanctioned pattern: PreToolUse
pattern match → inject relevant bullets as read-only context. No blocking, no rewriting, no
semantic judging."*

## Why disclosure rather than the block the article ships

Two reasons, and only the second is about this repo's charter.

**The first is decidability.** `AGENTS.md` §3: blocking is for deterministically decidable
violations only, because gating a judgement call teaches people to route around the gate. A
file's size is decidable. Whether *this* read should be delegated is not: the article's own
author reports that the worker's summaries carry no reliable line numbers, so an edit has to
read the bytes anyway, and that the worker missed a thread-safety bug the main model caught in
seconds. A block that fires on size alone therefore fires on a population that includes every
edit-shaped read, and the first time it costs someone an edit they will set the threshold to
infinity. A disclosure that is wrong costs one sentence.

**The second is that the knowledge, not the prohibition, is what was missing.** The standing
spawn policy already carries the Residual context gate, and the measured count rule shipped on
2026-09-08 already delegates bounded implementation work at five items. Both are instructions
that require the agent to recognise the situation. `AGENTS.md` §8 names that failure mode
exactly: a rule whose failure mode is recognition belongs behind something structural. The hook
makes the size of the read visible *before* the read, which is the one thing a sentence in a
guide cannot do. It changes what is known, not what is permitted.

## The trigger is bytes, and the threshold is provisional

The article's trigger is 350 lines. Lines are the wrong unit here, and this repo carries the
counterexample: `research/agents-md/derived/sample_closed.jsonl` is **181 lines and 1.3 MB**. A
line threshold never fires on it; a byte threshold does. The hook measures the bytes of the
first 2000 lines, because that is what an unbounded `Read` actually pulls.

Measured over the 590 tracked text files of this repo at `79b4adb` (bytes of the first 2000
lines):

| percentile | size |
| --- | --- |
| p50 | 10.5 KB |
| p75 | 23.3 KB |
| p90 | 46.2 KB |
| p95 | 85.4 KB |
| p99 | 182.3 KB |

The default is **60 KB**, which fires on 46 of 590 files (7.8%). That number is a calibration,
not a result: it was chosen to sit near the top decile so the disclosure stays rare, and it is
the value the measurement below exists to replace. `AGENT_BIOS_READ_DISCLOSE_KB` moves it, and
an unusable value falls back to the default rather than silencing the hook.

## Why the article's 90% cannot be carried over

Its headline is *"Mean bulk-read savings were around a whopping 90%."* That is the share of
tokens that never entered the main context on one read operation. The tier-economics
confirmation of 2026-09-06 measured something else: **+45.5% [40.4, 50.5]**, the dollars to
reach parity on a whole work unit, with the child's own spend and the carriage of its report
counted against it. Different numerator, different denominator, different population
(read-dominated versus write-dominated). Neither number predicts the other, and quoting the 90%
in support of a binding here would be the basis error the global rules name.

What the two do share is the shape of the finding: below some size, the overhead of delegation
exceeds what it saves. The article puts that boundary at 350 lines by its own tuning; the
spawn-trigger experiment put its own boundary at five items with a confirmed lower bound. The
read boundary is unmeasured here.

## The measurement that would license a block

**Question.** For an unbounded read of size S, does routing it to a cheaper seat reach the same
answer for fewer dollars, and above which S?

**Arms**, one question per block, same question to each: (a) the main seat reads inline
(`claude-opus-5` / xhigh); (b) a SWEEP child reads and answers (`claude-haiku-4-5`); (c) a
WORKHORSE child reads and answers (`claude-sonnet-5` / xhigh). Arm (c) is the seat the
2026-09-06 confirmation already priced on write-dominated work, so a read-dominated result
composes with it rather than restating it.

**Quality has to be checkable, or this repeats Stage 2**, where every arm came back at level 0
and the task separated no seat. The task family is therefore questions whose ground truth a
deterministic script derives from the file itself — every symbol that writes to disk, every
call site of a named function, the exact set of exported names — so an answer is scored against
a computed key rather than judged. An arm that misses the key is not cheaper; it is wrong, and
the block would be shipping wrongness.

**Cost basis**: dollars to a correct answer, including the child's dispatch, the child's own
tokens, and the carriage of its report into the main. Same basis as the confirmed retention
contrast, so the two results sit on one axis. `session-cost.py` is the measure;
`benchmarks/tier/` already owns seat pinning, the ledger, group ceilings, and exact-R.

**Bands**: S swept across roughly 20 / 60 / 150 KB, because the deliverable is not "delegation
wins" but the S at which it starts winning. That S is the hook's default.

**Excluded by construction**, and to be stated in the record rather than discovered: reads whose
purpose is an edit (the summary carries no line numbers), and any question whose answer needs
the reasoning of the main seat rather than the contents of the file. Both are the article's own
reported failure modes, and neither is a cost question.

**Also to be counted**: the hook's own cost. It injects roughly sixty words on every fire, on
every session that installs the orchestration domain. At 7.8% of reads that is small, but it is
not zero, and a disclosure that costs more than it saves is the same defect one level up.

**Done when**: the three arms have their declared blocks at each band, every answer is scored
against the computed key, and the lowest band whose confirmed lower bound clears the dispatch
overhead is named. Until that exists, the threshold stays a calibration and the hook stays
advisory.

## What was verified here

The hook's `--self-test` drives the real entry point over real stdin: it fires on a 94 KB file,
stays silent on a small one, on a bounded read (`limit=`), on a binary file, on a missing path,
on a directory, on an image extension, on another tool, and on five malformed payload shapes;
it fires on an offset-only read, because an offset moves the window without shrinking it; and it
proves the threshold knob in both directions. Seven behaviours were then reverted one at a time
and each control was watched failing by name — including the outer crash guard, whose first
version survived its own removal until a payload was added that actually reaches it (a
`file_path` carrying an embedded NUL, which raises `ValueError` past the `OSError` guard).

The umbrella's hook leg no longer names one file: it runs `--self-test` for every `claude/hooks/*.py`
and fails when the directory holds none, so the next hook is covered by existing rather than by
someone remembering to add a line.
