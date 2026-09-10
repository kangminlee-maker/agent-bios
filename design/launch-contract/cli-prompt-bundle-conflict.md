# The CLI's own prompt bundle contradicted the launch contract

**2026-07-28.** A session reported that its system prompt carried two prohibitions —

```
Do not call the AgentTool unless the user requested it
Do not use workflows or deep-research unless the user requested it
```

— beside a `LaunchPlan:` line that said `Delegation=on`. It followed the stricter reading and
ran its cross-check on a single axis.

## Where the lines come from

Not this repo. They are absent from the deployed launcher, the deployed `profiles.toml`, and
every preset. They are a constant in the **Claude Code CLI binary** (2.1.220):

```js
ttp = ["Do not call the AgentTool unless the user requested it",
       "Do not use workflows or deep-research unless the user requested it"].join(" | ")
```

selected by:

```js
let r = Ke("tengu_heron_brook", "");
if (r.trim() !== "") return r.trim();   // a server flag may replace the text
if (tXn(e)) return ttp;                 // otherwise this constant
return null;

function tXn(e) {
  if (e === undefined) return false;
  if (LN(lo(e), "opus_5_prompt_bundle") !== true) return false;   // ← model is Opus 5
  return !Ke(nug, false);                                          // kill switch
}
```

So the trigger is **the model**: any session on Opus 5 gets it, gated on a flag this launcher
does not set and cannot see. The Superset wrapper is a pure passthrough (`SUPERSET_AGENT_ID`
only) and is not involved.

## Why it mattered here

Every claude-host preset resolves its main tier to `claude-opus-5`, and four of them delegate:

| preset | main tier | model | delegation |
| --- | --- | --- | --- |
| balanced, deep-review, session-distill | helm | claude-opus-5 | on |
| fast-batch | workhorse | claude-opus-5 | on |
| solo, vanilla | helm | claude-opus-5 | off |

Two authorities, neither aware of the other. The launcher turns delegation on; the CLI bundle
tells the reader not to delegate. A reader resolving that conflict conservatively silently
does less work than was configured — and nothing reports it, because from the launcher's side
delegation *is* on.

## The fix, and why this one

The CLI's line carries its own exception — *"unless the user requested it"*. Delegation **is**
the user's request: they chose a delegating preset, and the corpus's standing spawn policy is
their instruction about when to use it. So the contract states that fact in the words the
clause is looking for, rather than trying to override an instruction it cannot see:

```
Delegation=on — the user requested delegation by selecting this launch, and their standing
spawn policy governs when to use it.
```

Nothing is overridden and no prohibition is contradicted; a fact that was already true is
simply put where the reader can see it. `Delegation=off` is unchanged, byte for byte.

**Rejected alternative:** pinning the CLI's text in a gate. It is a constant in someone else's
binary behind a server flag — it can change or be replaced without notice, and a gate on it
would fail for reasons this repo cannot fix.

**Scope.** 130 golden cells move, every one of them `deleg-on`, none `deleg-off`. That
includes 96 legacy cells, so the "192 legacy cells byte-identical" property does not hold
across this change — deliberately, because a legacy preset on Opus 5 with delegation on has
exactly the same conflict. Kept off the reviewer-registry branch for that reason: it would
have destroyed that branch's own baseline for an unrelated reason.
