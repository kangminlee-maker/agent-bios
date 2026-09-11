---
name: corpus
description: Inspect or change the private agent-bios corpus used by activated sessions, including item creation, edits, consumption placement, removal, restore, recovery, selection, reset, rollback, history, and current-vs-pinned explanation. Use for requests about the user's agent-bios instructions or personal learnings; it does not alter the running session or native global files.
---

# Corpus management

For a guided conversation about why a corpus bundle exists and how its rules work,
use the `understand!` / `$understand` skill. `agent-bios understand list` lists
learning bundles; `agent-launch --understand BUNDLE claude` (or `codex`) opens a
dedicated learning session. Understanding is not a corpus mutation or `learn!`
capture request; use the management operations below for ordinary edits.

Use the deterministic `agent-bios corpus` client. In an activated launch, invoke
it as `bash "$AGENT_BIOS_PACKAGE_ROOT/install.sh" corpus` (the examples below use
the shorter command name). The launcher supplies that package path, so a checkout
installation does not accidentally call an older global npm CLI. If the variable
is absent, resolve the installed `agent-bios` command before using the examples.
It reads and writes private
agent-bios state; it never edits native global `AGENTS.md` / `CLAUDE.md`, host
discovery directories, or the current conversation.

## Establish the view

Start with:

```bash
agent-bios corpus status --json
agent-bios corpus list --json
agent-bios corpus show '<CorpusRef>' --view effective --json
```

The running session is pinned to the `ContentRef` stated by its launch contract.
`status`, `list`, and `show` describe current authoring unless a command explicitly
says otherwise. A mutation changes future activated launches only; it does not
rewrite this session's pin. `snapshot --host codex|claude` composes current
authoring and returns stored snapshot evidence—it does not prove a host loaded it.
Use `snapshot --content-ref '<ContentRef>' --json` to inspect the exact immutable
items and instruction text of the running or resumed session, independently of
current authoring.

Use `show --view installed|change|diff|history` to compare the selected installed
baseline, the personal layer, and effective authoring. Use `history [CorpusRef]
--json` for recoverable revisions.

## Plan, preview, then apply

Send exactly one semantic operation as JSON. The runtime owns ids, paths, digests,
timestamps, serialization, revision calculation, and publication. Never invent or
edit those values. For writes, preserve the `digest` returned by `list` as
`item_digest`; preserve the plan's `expected_revision` when applying it.

```bash
agent-bios corpus plan --input request.json --json
agent-bios corpus apply '<plan_id>' --expected-revision '<expected_revision>' --json
```

Supported payloads:

```json
{"operation":"create","item":{"title":"Review releases","body":"...","surface":"requested","tier":"env-personal","domains":["personal"],"kind":"rule"}}
{"operation":"update","ref":"@scope/name:item-id","item_digest":"<digest>","patch":{"body":"...","surface":"relevant"}}
{"operation":"remove","ref":"@scope/name:item-id","item_digest":"<digest>"}
{"operation":"restore","ref":"@scope/name:item-id"}
{"operation":"recover","ref":"@local/personal:item-id"}
{"operation":"select","selection":["@scope/name/domain"]}
{"operation":"reset"}
{"operation":"rollback","baseline_ref":"<baseline_ref>"}
{"operation":"rollback","history_id":"<history_id>"}
```

For a body edit, submit `body`; the manager updates the item's `primary_member`
and derives every content view from that file. For a multi-file edit, submit
`members` retaining unchanged files. A conflicting simultaneous body/member edit
is refused. If `content_conflict` is shown, compare the preserved body and members
with the user; submit an explicit primary-member/content choice rather than
silently choosing a version. Personal IDs are issued once by the plan and remain
stable on retry; create payloads do not supply `item_id` or `ref`.
Do not turn a prose edit into an executable asset, hook,
permission, tool, or capability change. `always`, `relevant`, and `requested`
mean always in an activated selection, trigger-routed, and explicitly requested.
For existing hook items, `hook: {"event":"PreToolUse","matcher":"Bash"}`
edits the binding through the same plan/apply path. Preserve the installed source
carrier and native agent frontmatter, including tool restrictions. Changing an
ordinary prose item's kind/surface does not turn it into executable hook code.

Native hook execution and corpus-agent registration are off by default. The user
opts in per launch with `agent-launch --corpus-native`; `snapshot --host claude
--native --json` or `snapshot --host codex --native --json` previews/composes that
selection without activating a host. Hook bodies and typed bindings are shared;
compilation reports events the selected host does not support. Codex uses session
config flags and its native `/hooks` review; Claude uses per-item plugins. Native
corpus-agent registration currently projects Claude agent frontmatter only.
The snapshot supplies session-only local plugins; it does not install them into
global discovery. Check `unavailable` for unsupported carriers or hosts. Native
corpus agent names are qualified by their item plugin, distinct from the launcher's
bare tier names. Removing/restoring one item changes only future snapshots.

Show the plan and its consequences before Apply when the user has not already
approved that exact mutation. A stale revision or digest requires a fresh read and
new plan; never retry by dropping the revision check. Report after Apply that the
current session is unchanged and a new activated launch is needed.

## Restore, recover, and reset

- `restore` removes an installed item's personal override/tombstone and reveals
  the version in the selected baseline for future snapshots.
- `recover` reactivates a personal item or host learning from private history. It is not installed
  restore.
- `reset` returns future authoring and selection to the last successful installed
  tuple while preserving sources, history, and existing session pins.
- For all product settings as well, `agent-bios reset` previews the effect;
  `agent-bios reset --apply --yes --expected-revision '<preview revision>'` also
  resets launcher overrides and disables configured ingestion. It does not reset
  the native host's settings. Retry the accepted revision to finish an interrupted
  reset; if state has changed, show a fresh preview and obtain approval for its
  revision. Token bytes are never archived or restored.
- `rollback` selects a validated baseline or replays one history record for future
  snapshots; it never rewrites a running or resumable session.

## Personal learnings

Claude and Codex learning sources are separate, host-qualified local authorities.
Captured events and their `learning_id` identify immutable captured bytes. Editing
their corpus presentation creates a local overlay for future snapshots; it does
not change an already uploaded record. Uploading revised wording is a new explicit
capture with a new id and provenance link. Never claim that local remove, reset,
promotion, or purge deleted an uploaded learning unless a real remote delete
protocol reports that outcome.
