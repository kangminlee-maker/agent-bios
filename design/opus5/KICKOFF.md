# Opus 5 rebind + prompting update — OUTCOME RECORD

Status: **COMPLETE and LIVE 2026-07-25** — released as v0.9.3, published, installed,
and verified on the real dispatch path. A follow-on experiment (v0.9.4) then moved
WORKHORSE to Opus 5 at `medium`; measured 2026-07-26, its verdict is **cannot judge —
the protocol cannot reach its own sample** — see §Backlog. Prepared as a kickoff on 2026-07-25 and executed the same day.

## What Opus 5 actually is (verified empirically, not from docs alone)

Probed against the installed Claude Code CLI **2.1.220**, with a negative control
so the check could actually fail:

| probe | result |
|---|---|
| `claude --model claude-opus-5 --effort low -p …` | exit 0, `OK` |
| `claude --model claude-opus-99 …` (negative control) | exit 1, "may not exist" |

- **Model id `claude-opus-5`** — no date suffix.
- **Effort `low`/`medium`/`high`/`xhigh`/`max`** — all five, already matching the
  launcher's `HOST_EFFORTS["claude"]`, so no schema change was needed.
- **$5 / $25 per MTok — identical to Opus 4.8**, half of Fable 5. 1M context
  (default *and* maximum), 128K output.
- Separate rate-limit bucket from the Opus 4.x pool. Prompt-cache minimum drops
  to 512 tokens (Opus 4.8: 1024). Thinking is on by default; disabling it is
  accepted only at `high` effort or below (400 above).

## Decisions

| tier | outcome | why |
|---|---|---|
| **HELM** | `claude-opus-4-8` → **`claude-opus-5`** @ `xhigh` | Same price as Opus 4.8 and documented as a step-change over it — a free upgrade. |
| **WORKHORSE** | **unchanged** (`claude-sonnet-5` @ `high`) | User goal is lower output cost. The claim that a stronger tier pays for itself via fewer retries was **unverified and withdrawn** — see §Cost evidence. |
| **FRONTIER** | **unchanged** (`claude-fable-5` @ `max`) | User confirmed the monthly spend cap that had forced an Opus detour is lifted. |
| **SWEEP** | unchanged (`claude-haiku-4-5` @ `low`) | Out of scope. |

### Cost evidence (why WORKHORSE did not move)

Measured over 60 days of real transcripts — 11,628 files, 163,933 unique API
requests. The measurement **did not support** moving workhorse to Opus 5:

- Opus 5 subagent sample was **n=6 tasks / 144 turns** — too small to conclude anything.
- No sign of "stronger tier → fewer round-trips": `claude-opus-4-8` subagent tasks
  had a **median of 8 turns**, `claude-sonnet-5` also **8**.
- Per-turn subagent output came out ~34× smaller than main-loop (47 vs 1,601
  tokens), which is not plausible — the record unit was wrong, so those numbers
  were discarded rather than reported.
- Per-task cost across models is **routing-confounded**: harder work is routed to
  stronger tiers by design.

Meanwhile the vendor's own Opus 5 guidance documents forces pushing output cost
**up**: longer responses (and `effort` is explicitly *not* the lever that shortens
them), longer written deliverables, more inter-tool narration, and **more eager
subagent delegation** — the reverse of Opus 4.8. The strong lever for output cost
is prompt-side, not the model binding.

## The lockstep parity contract (what had to change together)

`scripts/check-parity.sh` enforces this; a partial change fails the gate.

1. **`config/agent-launch.toml`** — `[hosts.claude.tiers.helm]` **and** the
   `[hosts.claude] models` catalog.
2. **`scripts/check-parity.sh`** — `expected_claude_tiers` **and** the Claude guide
   binding tuple. ⚠️ The same file carries a **separate GPT ladder** (HELM=GPT-5.6
   Sol, WORKHORSE=GPT-5.6 Terra) — Opus 5 touches only the Claude tuples.
3. **`cli-multi-model-workflow.md`** — Environment Binding HELM row + the HELM
   effort row + the binding date, **×4 mirrors** (`claude/`, `codex/`,
   `ko/claude/`, `ko/codex/`).
4. **`claude-prompting.md`** — the `targets:` list, ×4 mirrors.
5. **`scripts/session-cost.py`** — the price table.

**There is no HELM agent file.** `claude/agents/` holds only frontier / workhorse /
sweep, because HELM is the main and never a subagent.

**Incidental fix:** `session-cost.py` had no `claude-opus-5` row, so it was already
silently mis-costing real Opus 5 traffic present in the transcripts.

## Prompting rules re-derived (step 2)

`claude-prompting.md` (×4 mirrors) had **two rules that invert on Opus 5** and were
actively steering the wrong way, plus three gaps:

- *"add a self-check cadence; a fresh-context verifier subagent beats self-critique"*
  → **deleted.** Opus 5 verifies unasked; instructing it to verify buys
  over-verification. This inverts the usual self-check advice.
- *"this tier under-reaches for subagents"* → **reversed.** It over-reaches; the
  rule now says cap the spawn count. (Memory and custom tools still need triggers.)
- Added: length is a prompting lever, not an effort lever; scope self-correction;
  the thinking-on-by-default / effort-cap constraint; start-high-then-sweep-*down*.

## Verification

| check | result |
|---|---|
| `bash scripts/check-parity.sh` | **PASS** |
| Negative control — reverted the HELM row in 1 of 4 mirrors | **FAILED as required** ("HELM must bind exact Claude Opus 5"), then PASS on restore. The green is real, not vacuous. |
| `bash scripts/check-prompting-targets.sh` | **PASS** — "covers all 4 configured claude model(s)" |
| Launcher live projection, repo config | `HELM · claude-opus-5 · xhigh` |

## §Deploy — the change is inert until installed

`default_config_path()` in `scripts/agent-launch.py` resolves
`$AGENT_LAUNCH_CONFIG` → **`~/.config/agent-launch/profiles.toml`** → the repo copy.
The deployed profile still binds `claude-opus-4-8`, so real launches keep using it.
Confirmed both ways: `--config config/agent-launch.toml` projects `claude-opus-5`;
the default path projects `claude-opus-4-8`.

**Deploying also flushes a stale backlog.** npm has `agent-bios@0.9.2`, but
`agent-bios install` has not run since **2026-07-20** (no `version.json` marker,
which v0.9.2's installer writes). The deployed set therefore still has:

- `mode = "general"` — pre-SWE-rename launcher mode
- the pre-rename heavy-mining preset, which at that point was still triggered by
  `learn!` rather than today's `distill!`
- older guides (incl. `tooling-gotchas.md`, which lacks the collection-loop finale's
  Cloud Run traffic-pin learning)

Running `agent-bios install` lands all of it at once — and also runs the
learnings migrate/prune step, which is expected and previously demonstrated safe.

## §Backlog — WORKHORSE on Opus 5 at medium (2026-07-26: the treatment has not reached running processes)

Released as v0.9.4 (`68886df` / `b38fb05`), but the deployed **agent definition** only
flipped at 2026-07-25 21:54 — see the measurement note below; the v0.9.4 verification
covered `profiles.toml`, not the agent file. Binding only — `claude/agents/workhorse.md`'s
instruction body is unchanged, so exactly one variable moved.

**Decide it with this, declared before the run:**

| | |
|---|---|
| Win condition | median **< ~7,250 output tokens per subagent invocation** |
| Why that number | Opus 5 output is $25/MTok vs Sonnet 5's $15, so it must emit under **60%** of Sonnet's tokens. Baseline: `claude-sonnet-5` median **12,089**. |
| Reference point | `claude-opus-4-8` measured **7,665** (63.4%) — just above break-even, which is why this needed running rather than assuming |
| Cost instrument | `scripts/session-cost.py` (correct since `87a9ef6`) |
| Quality instrument | the workhorse report contract — `files_or_items_touched` against the enumerated scope catches partial completion, `verification or gap` catches skipped checks |
| Sample needed | ~20–30 invocations before the median is worth reading (an earlier attempt at n=6 could conclude nothing) |
| Rollback | restore the tier to `claude-sonnet-5`/`high` across config, `check-parity` (`expected_claude_tiers` + guide tuple), the guide row ×4 mirrors, and the agent frontmatter. The GPT ladder is untouched either way. |

### Measurement attempt 2026-07-26 — VERDICT: cannot judge, and the protocol is the problem

Two findings, both from real transcripts and installer backups rather than from the
recorded narrative.

**1. The experiment started later than this file says.** The clock here reads "live since
2026-07-25 (`68886df`, released `b38fb05` / tag `v0.9.4`, deployed and verified)". The
deployed **agent definition** — the surface that decides what a spawned workhorse actually
runs as — was still `claude-sonnet-5` / `high` until **2026-07-25 21:54**. Evidence: the
installer backup `~/.local/share/agent-bios/backups/20260725-215429/` holds the
`workhorse.md` it replaced, and that copy reads `model: claude-sonnet-5`, `effort: high`;
the deployed file's mtime is that same install. The v0.9.4 verification covered
`profiles.toml`, which agreed, while the agent file lagged — the deploy-chain drift this
repo lists as its main risk, landing on the experiment itself. **Any workhorse invocation
before 2026-07-25 21:54 ran on the old binding and is not experiment data.**

**2. At the observed spawn mix the sample will never arrive.** Counting main-side `Agent`
tool_use records after that cutoff: **14 spawns, of which workhorse is 1** (frontier 12,
Explore 1). The declared sample is 20–30, and this file already records that n=6 concluded
nothing. Per-invocation subagent output for `claude-opus-5` after the cutoff is n=3 with a
median of ~75.5k, which is not a workhorse profile at all — those are long-running agents,
and nothing in a subagent transcript identifies its tier, so even that number cannot be
attributed.

**3. Both of those readings were wrong, and the real blocker is neither.** Corrected the
same day:

- *Attribution is possible.* A subagent's `agentId` is `"a" + <the spawn's `name`> + "-" +
  hash`, and the main-side `Agent` tool_use carries `subagent_type` alongside that `name`,
  within the same `sessionId`. That joins 406 subagent transcripts to a typed spawn —
  **77 of them workhorse**. The earlier "no tier marker, cannot attribute" claim is
  withdrawn, as is the memory note saying subagents cannot be joined to main.
- *The rate estimate was drawn from a weekend.* It is not a valid basis for "n=20 is three
  weeks out", and that projection is withdrawn too.

**What actually blocks it: the experiment's unit is the CLI process launch, not the
session or the invocation.** The launcher injects the tier ladder as an inline `--agents`
JSON at process start. A process launched before 2026-07-25 21:54 keeps injecting
`workhorse: claude-sonnet-5 at high` for its whole life — **including across `/clear`,
which mints a new session id but does not re-launch the process or re-read the config.**
The evidence: of 77 joined workhorse invocations, **76 ran on `claude-sonnet-5` and 1 on
`claude-opus-5`**; even restricting to invocations timestamped after the flip it is 17
sonnet to 1 opus. Meanwhile `agent-launch --dry-run` against the deployed config projects
`WORKHORSE  claude-opus-5 · medium` correctly right now.

So the treatment is real and correctly configured, and it simply has not reached the
running processes. Waiting collects Sonnet data until the long-lived CLI processes are
relaunched.

**What that means for the decision.** Waiting is viable — the earlier "waiting is ruled
out" was based on the two withdrawn readings. To make it count: relaunch the long-running
CLI processes, and measure only invocations whose spawning **process** started after the
flip. The rollback option is unchanged and still cheap if the premium is not wanted.

**Expect no visible change in chattiness.** On Opus 5 `effort` moves thinking volume,
not visible output length — the vendor guidance is explicit that lowering effort does
not reliably shorten the response. Cost should fall without the output reading terser;
if the narration itself is too long, that is a prompt fix, not an effort fix.

## Related

Memory `[[opus5-rebind]]`, `[[opus5-workhorse-cost-evidence]]`, `[[frontier-tier-model]]`,
`[[claude-transcript-cost-measurement]]`.
Guides: `claude/guides/claude-prompting.md`, `claude/guides/cli-multi-model-workflow.md`.
