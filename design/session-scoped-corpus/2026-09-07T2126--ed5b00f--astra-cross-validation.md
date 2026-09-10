---
created_at: 2026-09-07T21:26:28+09:00
head: ed5b00f
kind: review
supersedes: null
---

# Astra cross-validation — managed corpus under session-scoped activation

Target bundle:

- `2026-09-07T1818--ed5b00f--proposed-design.md` — governing direction
- `../corpus-management/2026-09-04T2321--17862b3--proposed-design.md` —
  historical Corpus Manager design

Packet:
`../corpus-management/2026-09-07T2109--ed5b00f--astra-cross-validation-packet.md`.

Seat: isolated `gpt-6-astra` FRONTIER, xhigh, live repository read access, no
writes. The reviewer read both designs, the session-scoped blind packet and
loader probe, the owner decision, and the current writers/consumers. Earlier
review reports and model drafts were excluded.

## Verdict

**REVISE — four material design defects.** Private installation and explicit
per-session activation remain the governing architecture. Stable item identity,
immutable baselines, one personal overlay level, standalone Studio/CLI, and
plan-preview-apply survive after adaptation.

## Material findings

### 1. Mutable learning content reuses immutable upload/promotion identity

Current upload settlement and server dedup use `learning_id`; promotion pruning
also selects by that id without comparing the local content revision. Editing a
settled learning under the same id can leave the server on the old content and
later remove the edited local content as though the promoted revision matched.

Correction: captured JSONL rows remain immutable capture/upload evidence. Local
corpus edits, moves, and removals are overlays/tombstones. Uploading revised
content is a new explicit capture, not reuse of a settled id. Promotion may
suppress only the exact captured revision and must preserve any local overlay.

### 2. Promotion pruning is global but session corpus is selection-relative

Current migration deletes the personal source after finding a replacement in
one deployed selection. A later session pinned to an older baseline or another
domain selection may have neither the promoted copy nor the deleted personal
copy.

Correction: retain personal source records. Promotion creates per-immutable-
snapshot suppression only when that snapshot contains the effective replacement
and no local modification is lost. Rollback or deselection recomputes
suppression; it never reconstructs deleted source.

### 3. Activated sessions lack an explicit management bootstrap contract

The old always-discovered management skill is superseded by no-global-corpus
installation. Private `skills.config` registration failed the recorded Codex
probe. Without another contract, a core-only activated session can lose the
required in-session management route.

Correction: package an immutable private management bootstrap with the manager.
Every activated launch receives its invocation description and concrete
procedure path independently of optional package/domain/skill selection. It
calls the same manager API and is outside corpus CRUD. Vanilla receives no
description or registration. Native session-only skill registration is an
optional adapter improvement only after a real probe.

### 4. Reset defaults are not coupled to the baseline that produced them

One mutable install-default record can name a domain introduced by baseline N
while rollback activates N−1. Reset would then reject, silently filter, or invent
a translation.

Correction: every successful installation record binds exact baseline refs,
package/domain defaults, and packaged settings as one immutable tuple. Reset
restores the tuple for future activated sessions; rollback never rewrites it and
existing session pins remain unchanged.

## Compatibility disposition

| Historical Corpus Manager element | Result under session scoping |
| --- | --- |
| stable `CorpusRef` independent of path/surface | keep |
| immutable baseline + personal override/tombstone | keep; resolve into private snapshots |
| deterministic conflicts and staged update | keep |
| standalone Studio/CLI + one manager/validator | keep |
| compound item/dependency closure | keep; verify shared routers and multi-file skills |
| personal-learning adapter | revise for findings 1–2 and separate host sources |
| selection/status/transactions | revise to distinguish authoring default, future launch, and pinned session |
| restore/reset/rollback/uninstall | revise for baseline tuple and retained pins |
| always-discovered management skill | replace with activated private bootstrap |
| global files, discovery registration, shell interception | retire through explicit legacy migration |

## Management experience

One standalone manager has three clients: Corpus Studio, non-TTY CLI, and the
activated-session bootstrap. Studio works before any agent session. An activated
session can inspect its pinned view and current authoring view; mutation creates
a revision-checked plan against current source. Vanilla receives no automatic
management content. Installing an inert executable is compatible with the
no-corpus boundary.

## Review coverage

All twelve packet scenarios were checked. No additional material defect was
counted for absent implementation, native registration that remains disabled,
lack of a universal host pointer, explicit remote-registry/signing non-goals, or
already-running sessions retaining prior context. These remain verification
conditions:

- real absence across globals, skills, hooks, agents, config additions, and shell
  interception on fresh install/Vanilla;
- private management invocation from a core-only activated session;
- effective instruction preservation, child inheritance, and resume pinning;
- shared guide/skill closure and hook/agent consumers;
- crash recovery and pin retention through update/reset/rollback/uninstall.

## Disposition

`FRONTIER disposition: retain the current worktree's private-install,
session-activation direction; absorb the older manager's source/identity/overlay
and UI contracts; replace its global realization and always-installed-skill
assumptions; resolve the four findings in one superseding design before
implementation.`

## Superseding-design re-review

The findings were folded into
`2026-09-07T2128--ed5b00f--managed-corpus-design.md` and reviewed again by the
same Astra FRONTIER plus an isolated implementation-reality reviewer.

The first pass over that synthesis found four state-transition gaps:

- `ContentRef` omitted independently advancing learning/promotion/bootstrap
  inputs;
- host launch could succeed before the session id was durably pinned;
- a promoted learning plus local overlay could emit two versions;
- reset did not distinguish last successful install from a rollback-selected
  baseline.

After correction, Astra found one narrower regression: replacing a whole
promoted guide could discard sibling content. The final design now permits
automatic replacement only for a verified exclusive item or stable member;
shared/whole-container targets conflict rather than merge semantically.

Final targeted re-review results:

- Astra FRONTIER: **PASS, open material findings 0**.
- Independent reviewer: **APPROVE, open material findings 0**.

These verdicts validate the design contract and its stated verification plan;
they are not evidence that the unimplemented host adapters or migration already
work.
