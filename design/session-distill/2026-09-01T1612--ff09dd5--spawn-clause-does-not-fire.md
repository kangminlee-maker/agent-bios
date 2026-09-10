---
created_at: 2026-09-01T16:12:00+09:00
head: ff09dd5
kind: review
supersedes: 2026-09-01T1429--7cdd750--npm-corpus-status-closed.md
---

# The always-spawn clause does not produce spawns

F-16 filed a contradiction between the deployed global's spawn policy and the
prompting guide it points to. Measuring it changed the finding: the contradiction is
textual, and the behaviour it describes does not occur on either side.

Four dispatches, $2.10 total, `claude -p --output-format json --permission-mode plan
--model claude-opus-5 --effort medium`, against the corpus deployed on this machine
(`agent-bios-bundle-rev: 481cbf6f`).

## Result

| Probe | Situation | Gate the corpus names | Agent spawns | Defect found |
| --- | --- | --- | --- | --- |
| 1 | A release gate reporting a false PASS | Independence | 0 | complete |
| 2 | A/B result whose arms have different denominators | Independence | 0 | complete, sign reversed |
| 3 | Two design alternatives open two weeks, conclusion shared with a team | Escalation | 0 | — |
| 4 | A subagent requested outright | none | **1** | — |

Probe 4 is the positive control and it is what makes the other three readable: the
mechanism works in this dispatch mode, so `0` means declined, not blocked. All four
transcripts were asserted non-empty before counting.

## What the rule actually says

The clauses live in one bullet:

> **Independence:** verifying or reviewing your own work always spawns …
> **Specifiability/de-minimis:** work needing your live context, or whose verification
> would repeat the reasoning, or whose packet outweighs the work, stays inline.

Probe 2 recorded its own decision:

> `SpawnGate: independence SWEEP inline` — conclusion rests on deterministic joins over
> 1,881 rows and 238 log lines, re-derivable in one command; a reviewer would repeat the
> same reasoning at higher cost.

That is the bullet's own escape, applied correctly. The gate was checked, as the rule's
first sentence requires; the outcome was inline, as its last sentence permits. Nothing
was violated in any of the three.

Probe 3 is the heavier datum. It was built to match the Escalation trigger verbatim, and
the response's own `TRIGGER_REASON` names the trigger — two alternatives, load-bearing,
shared onward — and still resolves inline.

## What caught the defects instead

Both defect probes were solved by other rules in the same corpus, cited by name in the
responses: `personal/learnings.md` `f8c7dfdf` (an empty interpolated variable makes a
shell check vacuous) in probe 1, and `d4c5b187` (a measurement agreeing with expectation
is when to test the instrument) plus Verification Discipline's common-basis rule in
probe 2.

This is also why the originally designed experiment cannot run. Two arms differing only
in the always-spawn clause would both score HIT, because the clause is not what produces
the behaviour. The measurement is degenerate before it is dispatched — which is the
answer, obtained for 3% of its projected cost.

## Fixture design note

Probe 1's fixture reproduced a failure shape that `personal/learnings.md` names
explicitly, and the response cited that learning's id while solving it. A fixture drawn
from this repo's own recorded learnings sits at the ceiling: the corpus carries the
answer key. Probe 2 was built deliberately outside that shape and hit the ceiling anyway.
Any future attempt to measure a corpus rule against defects the corpus already documents
inherits this problem.

## Consequence for F-16

The filed alternatives assumed the two rules compete for one behaviour. They do not
compete, because one of them is not producing behaviour. That admits an option the
finding did not list: the clause occupies per-session global budget while describing
something that does not happen. Rewriting it to state what occurs, or changing it so it
fires, are both live; leaving the present text is the one option the measurement argues
against.

Nothing is decided here. F-16 stays open with this evidence attached.

## Limits

N=3 scenarios at one repetition, one model, one host, `medium` effort, headless `-p`.
The largest untested confound is headless single-shot against an interactive session.
All three declines produced correct answers, so no case was observed where not spawning
cost accuracy; "inline is safe" does not follow from this data.

Cross-host reproduction on codex and an interactive/headless comparison are the two
checks most likely to move this conclusion.

## Re-derive

Fixtures and raw dispatch output are session scratch, not committed. The counting error
worth repeating: the subagent tool is named `Agent` in the transcript, not `Task`. A
counter keyed on `Task` returns zero for every run, including runs that did spawn.

```bash
python3 - <<'PY'
import json, glob, pathlib, collections
sid = "<session_id from the dispatch>"
tp = glob.glob(str(pathlib.Path.home()/f".claude/projects/**/{sid}.jsonl"), recursive=True)
tools = collections.Counter()
for line in open(tp[0]):
    d = json.loads(line)
    for blk in ((d.get("message") or {}).get("content") or []):
        if isinstance(blk, dict) and blk.get("type") == "tool_use":
            tools[blk["name"]] += 1
assert tools, "empty tool record — denominator unasserted"
print(dict(tools))
PY
```
