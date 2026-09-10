---
created_at: 2026-08-31T16:36:41+09:00
head: db5e745
branch: main
kind: handoff
supersedes: 2026-08-31T0704--c9e36db--handoff.md
---

# v0.14.0 shipped; the gate got 11x cheaper; and the prompting guides turn out to be the least current thing in the corpus

Re-derive before acting:

```bash
git log -1 --format='%h %s'
agent-bios status                        # expect deployed 0.14.0, source "package", no DRIFT
bash gates/test-install-guides.sh        # expect 104 PASS / 0 FAIL, ~70s
python3 benchmarks/selftest.py           # expect 246/246
```

## What landed

`f448041` **Release v0.14.0**, published and deployed. The tarball was verified against the
artifact rather than the registry: shasum match, `provenance.json` bound to the commit,
`dirty:false`, no stray `.pyc`, no `gates/`.

`db5e745` **The commit gate went 50m26s -> ~4.5 min.** `test-install-guides.sh` sets
`REPO="$PWD"` and writes only to a sandbox HOME, so its twelve `cmd_verify` runs re-ran the
umbrella on the tree the umbrella was already judging: 3m37s each, 43m22s of a 50m26s commit,
86%, and no assertion in the suite read the result. `cmd_verify` now skips the parity gate
under `AGENT_BIOS_IN_INSTALL_TEST` and announces the skip. The payload and prompting-target
gates keep running there deliberately — at 0.16s together they buy back nothing, and their
running is what proves verify still wires its gates up.

This commit: the TUI update badge (below), and the audit that motivates the next round.

## Two traps this session paid for, both worth carrying

- **`npm link` masks `npm i -g`.** `/opt/homebrew/lib/node_modules/agent-bios` was a symlink
  to this clone. `npm i -g agent-bios@0.14.0` returned "changed 1 package in 192ms" and KEPT
  the link, because the linked tree's package.json already read 0.14.0. Every downstream
  check then read the clone and agreed: `agent-bios status` reported the right version and
  the right commit, and `version.json` recorded `"source": "clone"`. The npm delivery path
  had never once run on this machine. Prove it with `npm ls -g --link`, or by the presence
  of `gates/` under the install — `gates/` never ships.
- **`set -euo pipefail` kills a tolerated failure.** `latest="$(npm view ... | tr ...)"` with
  npm exiting non-zero makes the PIPELINE fail and `set -e` abort the function before it can
  record the attempt. The offline path was broken and the success path was green; a
  hand-run E2E agreed with expectation and missed it. I16's failing-registry stub caught it.

## The update badge (this commit)

The network operation belongs to `install.sh`; the launcher only reads a local cache.

| Piece | Role |
| --- | --- |
| `install.sh` `refresh_update_cache` | `npm view <name> version` -> cache. Names no registry, so a private registry, proxy and the user's auth keep working, and no shipped file carries a URL (`gates/check-endpoints.py` forbids it) |
| `compose/write-update-cache.py` | atomic `os.replace`; a half-written cache is a TUI crash |
| launcher `version_label()` | appends `· update vX.Y.Z available`; spawns the refresh DETACHED when >24h stale, never blocking a launch |

Declared in `ENDPOINTS.md` as `check-version` (four operations -> five). It does not weaken
the zero-egress claim, whose scope is **data egress**: it sends the package name and nothing
derived from the machine, like `provision-venv.sh`'s PyPI fetch and the `onboard` probe.
`AGENT_BIOS_UPDATE_CHECK=0` disables it, and the gates' launcher fixture sets exactly that —
a gate that reaches the network is not a gate. Controls: I16, 8 assertions, network stubbed
by a fake `npm` so it passes in a tunnel.

## The audit — prompting-guide currency

| Finding | Evidence |
| --- | --- |
| The gate enforces NAMING, not re-derivation | `check-prompting-targets.sh` is `configured - declared`. One line in `targets:` satisfies it forever |
| `gpt-prompting.md` has never been re-derived | last content change is its creation commit `dd12494` (2026-07-16); `claude-prompting.md` was re-derived at `d30d41a` (2026-07-25) |
| Neither guide records what it was derived from | no `Evidence Base`, no `Environment Binding`, and `Sources` says only "the vendor's published guidance" — no document, no date, no version |
| The corpus contains the pattern its own guide names as harmful | `claude-prompting.md` says de-prescribe step-by-step scaffolding; `## Problem Solving` is an 11-step sequential procedure inside a 5,087-token per-session budget |

The `gpt` core_rule about blanket ALWAYS/NEVER is **well kept**: 12 `never`, all condition-scoped,
zero ALL-CAPS prohibitions.

## What the external survey changes

Full report in the session transcript. The parts that move a decision:

1. **No surveyed tool supports obsolescence detection natively** — promptfoo, DeepEval, Inspect,
   Braintrust, LangSmith, Langfuse, W&B all do regression and model-variation only; Braintrust
   calls instruction-trimming manual in its own docs. `benchmarks/` is unusual.
2. **Pre-registering the expected direction** is the survey's second recommendation, and §5's
   falsifier already does it.
3. **The missing axis is one outer loop**: {rule present, absent} x {old model, new model}, where
   obsolescence is the cell in which absent-on-new matches present-on-new.
   `dispatch.command_for` already takes `model` and already verifies the seat that answered.
4. **Anthropic publishes a delete-list** naming instruction categories that are counterproductive
   on Opus 5 — verification instructions ("use a subagent to verify" is their own example),
   re-check instructions, don't-think rules, prior-model workarounds. Grepped against
   `claude/CLAUDE.md`: the first three are present, the fourth is not. These are the cheapest
   ablation candidates, not deletions to make on the vendor's word.
5. **A rule can invert across one generation with its text unchanged**: arXiv 2510.22251,
   GSM8K n=1317, rule-based prompting 97% vs CoT 93% on gpt-4o, and 94% vs 96.36% on gpt-5.
   The authors name it *Guardrail-to-Handcuff*. This is the risk profile of `## Problem Solving`.
6. **Vendor docs are served as raw `.md` with stable frontmatter** — verified live: HTTP 200,
   12,465 bytes, `title`/`url`/`description`, and the delete-list sentence present verbatim.
7. **Nobody has solved rule interaction** under leave-one-out. This repo has already paid for
   it: the C6 arm was declared VOID because deleting the trigger left an action still naming it.

## Next, in the order that closes the most with the least

1. **`derived_from` / `derived_hash` / `derived_at` in each prompting guide's frontmatter**, plus a
   NON-BLOCKING leg in `check-prompting-targets.sh`: "the vendor doc changed since derivation".
   "Was it re-derived correctly" is undecidable and must not be gated; "has the source moved"
   is a hash. Closes audit findings 1 and 3. Roughly an afternoon.
2. **ChatGPT desktop app corpus selection** — that host never shows the TUI, so selection has no
   surface there. Unstarted; no design yet.
3. **Stage 2 scope** remains the owner's open call (A/B/C/D in
   `2026-08-31T0613--16a5a93--stage2-revalidation.md`). The survey strengthens the reach half
   (2a) and gives the derivability half a published mechanism and a vendor-named candidate list.
4. `benchmarks/out` is still 25 MB of gitignored evidence on one machine with no backup.
