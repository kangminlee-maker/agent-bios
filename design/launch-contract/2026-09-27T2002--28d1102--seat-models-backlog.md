---
created_at: 2026-09-27T20:02:02+09:00
head: 28d1102
kind: backlog
supersedes: null
---

# Backlog — the four default seats follow each model family's newest version

Owner's request, 2026-09-27: when Claude or Codex models are updated, the default bindings of the
four seats (frontier, helm, workhorse, sweep) move with them. Each seat is fixed to a model
family, and a default binding always names that family's newest version:

| Seat | Claude family | Codex family |
| --- | --- | --- |
| frontier | fable | astra |
| helm | opus | sol |
| workhorse | sonnet | terra |
| sweep | haiku | luna |

Every TUI start checks, through each host's own CLI binary, the newest version per provider and
family. A seat the person set themselves (a custom setting) is not changed. Nothing here is
designed or decided.

## What exists

- **The defaults** are concrete model ids in `launch/agent-launch.toml`
  (`[hosts.<host>.tiers.<seat>] model`), with each host's known ids in `[hosts.<host>] models` and
  display names in `[model_display]`. On 2026-09-27 they read:
  - Claude: `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5`;
  - Codex: `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`.

  The Claude helm seat is already behind: this environment names `claude-opus-5-5` as the newest
  Opus.
- **Custom settings** are separate from the defaults: a preset's
  `tier_overrides.<host>.<seat>.model` (and `effort`), validated in `launch/agent-launch.py`
  (`TIER_ORDER`, the `tier_overrides` checks, `validate_effort`). So "change the default, leave
  the person's choice" has a place to hold: rewrite the default binding, never an override.

## What each CLI binary offers (read 2026-09-27; re-check on the versions in use)

- **Codex 0.157.1:** the app server has `model/list`, which runs no model. Its entries carry
  display name, hidden, default, supported reasoning efforts and upgrade information (see the
  generated protocol, `schema157/` in the workbench's `v1-slice4-use`).
- **Claude Code 2.1.283:** `--model` takes a family alias (`fable`, `opus`, `sonnet`) that the
  CLI resolves to the newest model. No listing command was found in `--help`. A `-p` run reports
  the resolved id in `modelUsage`, but that costs a model call.

## Questions to settle before building

- **Resolve or name.** Either resolve each alias to a concrete id at TUI start and bind that, or
  bind the alias and record the id it resolved to. Concrete ids keep the rest of the launcher
  (review floors, effort validation, displays) working on a known value.
- **How the Claude id is learned without a model call.** Also how the start stays fast and
  offline-safe: the CLI binary is the source, and agent-bios itself keeps its zero-egress default
  (`ENDPOINTS.md`).
- **What a new version does to the prompting guides.** `claude-prompting.md` and
  `gpt-prompting.md` are version-bound, and `launch/check-prompting-targets.sh` fails when the
  launch config binds a model no guide lists (AGENTS.md §7). A default that moves at run time
  binds such a model before anyone re-derives the guide. Decide whether the TUI says so, whether
  it holds the old version until the guide covers the new one, or neither.
- **Efforts.** A new version may support other reasoning efforts. Decide whether the seat's
  default effort is re-validated against what `model/list` reports.
- **Where the moved default is written,** so a later start compares against it: the deployed
  profile, not the shipped `launch/agent-launch.toml`. How is it shown to the person, and can it
  be undone?
- **What counts as custom.** A preset's `tier_overrides`, anything else the Custom hub saves,
  and a default the person pinned on purpose.

**Start condition:** none blocking. It is independent of the Team work-environment stages.
