# Handoff — 2026-07-29

Resume point for the reviewer-registry work. Read this first, then
`design/reviewer-registry/DESIGN.md` Corrections **C31–C44** (the newest entries, written this
session). Everything below was verified against real code or a real run at the time of
writing; re-derive anything load-bearing before building on it.

## Where you are

**Everything is MERGED and DEPLOYED** (2026-07-29). No PR is open. `bash install.sh verify`
exits **0**, and the deployed launcher was checked by BEHAVIOUR, not by version string:
enter-through the real editor yields `OK` on both mains, a malformed offer block reads
`NO SEAT — capabilities.<cap>.offers[0].hosts must be a non-empty list…`, and a stored
unrunnable seat lists as `— WILL DROP` with the resolver's own reason.

| PR | What it was | Landed as |
| --- | --- | --- |
| **#14** | Registers a second dynamic-workflow reviewer so a **codex main** stops silently going without one. Six adversarial rounds, one workflow review, and the C41 seat fix. | `5ef8c09` |
| **#15** | The launch contract now states that delegation is the user's request, so Claude Code's own Opus-5 prompt bundle stops reading as a flat prohibition. | `f91be5f` |
| **#17** | Five review rounds against C41 (C42–C44): the gate's blindness to its own wiring, a refusal that lost the draft, advice for an impossible binding, two authorities disagreeing, and an audit that found two false claims in this document. | `22a8eb3` |
| **#16** | Resume-point refresh. | `c239213` |

**#14 and #15 conflicted with each other** in the generated `gates/goldens/review-matrix.json`,
while both reported `CLEAN` against `main` — that flag is computed against the base, never
against a sibling. Resolved by **regenerating** the golden from the merged code rather than
hand-merging it, then re-checking that the legacy drift is exactly what #15 declares: 96 cells,
all `deleg-on`, zero `deleg-off`, counted against a subject set asserted to be 192 first.
(#16 and #17 shared no file and needed none of that.)

**Twenty-six negative controls** now guard the review-seat surface, each verified to exit
nonzero with a named `FAIL:`. If you touch `review_provider_options`, `method_availability`,
`method_servable_hosts`, `no_seat_cause`, `seatable_hosts`, `review_landing_provider`, or the
`seat()` closure in `review_editor`, re-run them — the sweeps live in
`gates/check_parity.py::launcher_review_editor`.

## The naming that matters

`ultracode` runs **ON CLAUDE** — it is the Claude Code CLI's own dynamic workflow, opened by
putting the keyword in a prompt. `ultracode-for-codex` runs **ON CODEX**. Getting these the
wrong way round was a real defect this session (C32); the parity gate now pins both directions.

Together they give workflow-orchestration review **cross-family from either main**, which is
what PR #14 exists to fix.

## ANSWERED — codex `effort: ultra` IS orchestration, but it does not replace the tool

**The mechanism question is settled: orchestration, high confidence, verified locally.** The
effort value alone flips the model-visible delegation block. Re-run it yourself, free and
offline:

```
codex debug prompt-input -c model="gpt-5.6-sol" -c model_reasoning_effort="max"   "probe"
codex debug prompt-input -c model="gpt-5.6-sol" -c model_reasoning_effort="ultra" "probe"
```

```
max   -> <multi_agent_mode>Any earlier instruction enabling proactive multi-agent delegation
         no longer applies. Do not spawn sub-agents unless the user ... explicitly ask...
ultra -> <multi_agent_mode>Proactive multi-agent delegation is active. ... Use sub-agents when
         parallel work would materially improve speed or quality.
```

Corroborating, same build (`codex-cli 0.145.0`):
- `codex debug models` — `max` = *"Maximum reasoning depth for the hardest problems"*, `ultra`
  = *"Maximum reasoning with **automatic task delegation**"*. So ultra's differentiator is
  delegation, not depth: `max` already claims maximum depth.
- `ultra` exists **only** on `multi_agent_version: v2` models (`gpt-5.6-sol`, `gpt-5.6-terra`).
  `gpt-5.6-luna` is v1 and stops at `max`. Availability of ultra correlates exactly with
  multi-agent capability.
- `codex features list` → `multi_agent stable true`. The binary carries real spawn machinery
  (`spawn_agent`, `wait_agent`, `resume_agent`, `close_agent`, `subagent_start`/`subagent_stop`
  hooks, a `[subagents]` config block) and a retired toggle whose doc-comment says
  *"Ignored. Use Ultra reasoning effort for proactive multi-agent behavior."*

**But the replacement question is NOT settled, and the answer is currently no.** Three reasons,
in order of how much they matter:

1. **Ultra is a disposition, not a pipeline.** It permits proactive delegation; nothing
   guarantees a given turn spawns anyone. `ultracode-for-codex` (installed **0.7.1**, not 0.7.0)
   self-describes as *"durable, schema-enforced, resumable multi-agent workflows"* — deterministic
   scripts, per-agent schemas and tiers. Ultra gives fan-out; it does not give a contract.
2. **No adversarial-verification step.** The reviewer this repo registered is described as
   verifying each candidate finding by its own agent. Ultra's prompt block says only *"review
   the subagent's output"*. That is a different guarantee.
3. **Delivery is unverified here and reportedly flaky.** Third-party reports say the CLI/backend
   can map `ultra -> max` before the client sees it, that ultra is account-gated, and that
   `model_reasoning_effort` can reset. **None of that was checked on this machine** — asserting
   a config value is not evidence a sub-agent spawned.

**What would have to be true to drop the dependency.** A live falsifiable check that a spawn
actually occurred under this repo's own dispatch — assert a `multi_agent_call` turn item or a
`subagent_start` hook fires — plus an answer for the schema/verification contract that
`ultracode-for-codex` provides and ultra does not. Until then the dependency stays.

**Cheap intermediate win, if you want one:** this repo already emits
`-c model_reasoning_effort="ultra"` for `deep-review` on codex, so the *main* already runs in
proactive-delegation mode. That is orthogonal to the reviewer and needs no change.

## NEXT — the queue, in order

1. **Q2 onboarding — the head of the queue, and the only item left.** The customer-facing
   minimum and the ranked launch gate. Decided in the design (a trigger word backed by a
   deterministic submit subcommand, the `learn!` shape) and unbuilt. The registration principle
   established earlier: capture only what the tool does **not** self-describe, and the severity
   mapping is a decision the user supplies.

2. **Optional, and judged rather than skipped:** the concept audit proposed intersecting
   `seatable_hosts` INSIDE `method_servable_hosts`, since both runtime consumers re-intersect
   it themselves. Gate-green either way, so it is compaction, not a defect — worth doing on the
   next edit to that file, not on its own. The same audit proposed reducing
   `review_landing_provider` to "first enabled option"; that was **refused**, because it leaves
   the independence rule resting entirely on a sort key. Both encodings are asserted now, so
   the gate catches them drifting apart.

The three items the earlier queue held are done: the editor seat default (C41), the merge and
redeploy, and the five review rounds that followed (C42–C44).

## Recorded, not fixed — reproduced by the workflow review, none introduced by PR #14

Filed in DESIGN.md C39. Do not re-derive from scratch; each was reproduced by running code.

- A `capability offers no operation for host` drop is decorated with the capability's install
  hint, telling the user to install a tool that is already installed (`_resolve_one`). Still
  open, but no longer reachable from the editor — C41 made that seat unselectable rather than
  droppable, so this now needs a hand-written config to hit.
- A capability id containing a dot registers correctly on claude and **mis-registers on codex**
  (`-c mcp_servers.onto.v2.enabled=true` parses as a nested path), after the row reported OK.
- `order`, `swap_augmentation`, `aggregation` are parsed, validated, advertised on the
  registration screen, and read by nothing — no instruction slot, no consumer.
- `REVIEW_SETUPS[*]["requirements"]` is inert data; this branch rewrote it in three places and
  nothing reads it.
- The legacy `LEGACY_ROUTE_CAPABILITY` map is keyed by route only, so a same-family **claude**
  main is told to run `ultracode-for-codex`. Pre-existing; the new fact is that the claude main
  now has a workflow tool the legacy route cannot reach.
- `bash install.sh help` prints the derived `--with names:` line inside the `Env:` block.

## Contested — do not treat as settled

The workflow review filed a **BLOCKER** claiming the keyword cannot open the workflow in a
headless `-p` process, because `isHumanTypedPrompt` gates the system-reminder. Its own synthesis
then contradicted it: an A/B against the real CLI showed the first tool call **was** `Workflow`,
so the model reading the literal token opens it even though the reminder never fires.

The residual claim — that the descriptor attributes activation to `workflowKeywordTriggerEnabled`,
which is not the operative path headless — is plausible and **was not independently verified**.
It came from an agent cluster in which one member triggered a security warning for probing
whether spoofing the CLI's human-origin marker suppresses safety reminders, and for launching
nested sessions with permissions bypassed. That agent's output was discarded rather than
adjudicated. **Re-derive this yourself before acting on it**, and do not continue probing that
mechanism.

## How to verify anything here

```
cd /Users/kangmin/Documents/agent-bios
~/.local/share/agent-launch/venv/bin/python gates/check_parity.py            # exit 0 == green
~/.local/share/agent-launch/venv/bin/python gates/capture-review-goldens.py --check
~/.local/share/agent-launch/venv/bin/python gates/check-lexicon.py
bash gates/test-assemble.sh ; gates/check-package.sh
bash install.sh verify        # exits 1 only from deploy drift, see above
```

**Use that interpreter.** The system python produces ~45 spurious failures.

**A crashed check prints no `FAIL:` line and exits 1** — grepping for `FAIL` reports nothing,
which reads exactly like green. That happened here. Always look for a traceback before
concluding a check found nothing.

Legacy invariant: the **192 legacy cells** of `gates/goldens/review-matrix.json`. #14 left them
byte-identical; #15 deliberately moved 96 of them (all `deleg-on`) because the contract sentence
it changes is shared with the legacy path, which is why the two were separate branches. Both are
in `main` now, so the baseline for the next change is `main`, not the old pre-#15 matrix.

**Identify those 192 by CONSTRUCTING their keys** — `itertools.product` over `SETUPS`, `HOSTS`,
`FAMILIES`, `CAPABILITIES`, `DELEGATIONS` in `gates/capture-review-goldens.py`, which is what
its own control 1 does. A hand-written filter guessed at a `schema: "legacy"` field that does
not exist, matched nothing, and reported *zero drift over zero cells* — a clean bill of health
from an empty subject set. Assert the count is 192 before believing any answer about them.

## The through-line worth carrying forward

Seven over-restrictions were found across this effort, and the last four arrived **through the
door of a fix** — each correct about the case that prompted it and wrong about a neighbouring
one. Widening what a value may be without widening the key that identifies it; taking a
two-valued answer where the honest one has three; asserting a transformation against itself.

And the filter *"did this branch introduce it?"* is a fine reason to defer a fix into its own
change, but **not** a reason to file a hole in one's own gate as an observation about someone
else's code (C40).
