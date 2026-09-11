---
created_at: 2026-09-11T11:39:57.317356+09:00
head: 79b4adb
kind: backlog
supersedes: 2026-09-03T0120--69615f0--codex-hook-surface-verified.md
---

# Hook interoperability audit: initial backlog

The inventory covers 241 tracked text files with 2071 matching lines. `2026-09-11T1139--79b4adb--inventory.json` records every path and line, including historical records, research inputs, generated mirrors, Git/shell hooks, endpoint-header names, and runtime lifecycle hooks. The latter are the change subjects; the other meanings do not establish a host limitation. Historical records retain their original text.

## Verified inputs

- Codex CLI 0.153.4 and Claude Code 2.1.268 are installed. Resolved executable paths bypass shell interception.
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks): shared command input/output, session-level inline hook config, event differences, concurrent handlers, independent layers, enablement and hash-based trust.
- [Claude Hooks](https://code.claude.com/docs/en/hooks): command-hook input/output, per-event behavior and current vocabulary.
- Context7 resolved official Codex documentation and Claude documentation; direct official pages confirmed the contracts. Local Codex `hooks/list` positively discovers a session-flag hook and separately retains a same-event user-inline hook. Discovery is not execution.

## Backlog and acceptance

| ID | Evidence and consequence | Alternatives | Acceptance |
| --- | --- | --- | --- |
| HU-01 | `claude/CLAUDE.md` and Korean source list hook/skill as intrinsically host-specific examples. This discourages shared mechanisms before comparing their actual contracts. | Remove categorical examples; or replace them with a maintained host matrix in the global. | Remove the examples, reducing the global; explain differences in owning docs. |
| HU-02 | `compose/corpus_catalog.py` rejects every native event on Codex before checking the carrier. Shared Bash JSON/reminder output is already portable. | Shared compiler with host adapters; or duplicate a Codex hook tree. | One carrier/binding validates and emits on both hosts; no mirrored hook implementation. |
| HU-03 | Binding validation and both editors use `CLAUDE_HOOK_EVENTS`. Codex-only `Interrupt` is unrepresentable; several current Claude events are also absent. | Union for authoring with target-host checks; or independent per-host item schemas. | Shared authoring accepts known events, target compilation reports unsupported events by name without silently mapping them. |
| HU-04 | Snapshot assets and session launch understand only `claude_plugins`. Opt-in Codex hooks cannot survive preview, activation or resume. | Per-call inline Codex hooks; or install global hooks/plugins. | Hash native output, preserve user/project/session hooks, keep defaults and trust, retain exact pinned argv, and test removal and quoted paths. |
| HU-05 | Catalog/native/UI tests assert Codex has no native assets and use Claude-only event selection. | Positive/negative controls across both hosts; or only update expected strings. | Both carriers execute the same advisory contract; invalid carriers/events/settings and lost discovery fail tests. |
| HU-06 | README, SURFACES, DEPENDENCIES, bootstrap, implementation dashboard, hook comments and both guide languages describe Claude-only injection. | Align live contracts; or leave only a dated correction. | Current docs name both adapters and remaining runtime differences; regenerate Codex projections. |
| HU-07 | `benchmarks/corpus.py` sets Codex `settings=None`; receipts treat missing hook evidence as inapplicable. | Read/rebind Codex hooks with the shared harness; or explicitly refuse a hook-bearing input. | A Codex hook-bearing corpus cannot silently become hookless or inherit unrelated inline hook commands. |

## Boundaries audited separately

- `install.sh`, `compose/assemble.py`, `register-hooks.py`, `corpus_install.py`, `corpus-state.py`, and their gates retain Claude hook registration/removal for **legacy installations**. The default private installer writes neither host's global hooks. Adding new global Codex writes to a compatibility path would contradict the current product direction; session delivery is HU-04.
- `claude/settings.template.json` is the canonical hook binding source, and `claude/hooks/` is one shared authored tree. Its physical name does not require a second implementation. `domains.json`, endpoint gates and package files already inventory that source.
- Native corpus agents still require a Codex projection of authored Claude frontmatter, names, models and tool restrictions. This is an agent-adapter contract, not a hook limitation. The event adapter must not reject hooks merely because the delegated adapter differs.
- Reviewer wrappers deliberately withhold ambient hooks/config for isolated review. Global/main and reviewer capabilities need not match. Git pre-commit hooks, zsh prompt hooks, transport header `X-Hook-Token`, and third-party research fixtures do not describe either host's lifecycle API.
- Learning classification and promotion already use host-neutral `hook` placement; transcript and native-home differences remain real. No collection hook or new network operation is required.
- Ontology anchors name canonical source ownership and retained legacy registration. Extraction/gates, rather than copying claims from old design records, determine any required projection updates.

A later dated resolution record will state checks and remaining limitations. This file is the point-in-time admission of the backlog, not a live status board.
