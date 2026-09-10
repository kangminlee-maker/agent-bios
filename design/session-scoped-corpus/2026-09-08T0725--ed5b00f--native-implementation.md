---
created_at: 2026-09-08T07:25:00+09:00
head: ed5b00f
kind: handoff
---

# Native corpus adapters and exact session environment

Implementation is in the dirty working tree. No commit, release, live product
installation, credential copy, or native instruction/settings edit was performed.
The new native route remains **default-off**. Authenticated live acceptance is
blocked by the current Claude CLI reporting no login, including in its original
unset-config-home environment. No model-success claim follows from that failure.

## Current contract

- `agent-launch --corpus-native` opts one configured Claude launch into selected
  native corpus hooks and agents. Plain/Vanilla emits no additional plugin flags.
  `agent-bios corpus snapshot --host claude --native` composes without launching.
- Each supported installed item becomes a session-only local plugin in its own
  immutable item directory. `--plugin-dir` consumes the generated roots. No
  shared host settings merge or global plugin registration is performed.
- Namespace derives from the entire CorpusRef. Authored agent Markdown, including
  tool restrictions, remains intact; the generated child body additionally carries
  the selected base corpus and private management-bootstrap pointer. Corpus
  subtypes are qualified names, separate from bare launcher tier definitions.
- Hook binding is the optional `hook: {event, matcher}` property. Its installed
  value is extracted from the actual shipped settings template into the baseline.
  The executable member and quoted Python command are runtime-derived. TUI and
  numbered/JSON CLI editing use the same revision-checked plan/apply path.
- Ordinary prose/kind changes do not create executable native carriers. Carrier
  provenance, retained entrypoint, native-discovery member boundaries, Python
  syntax, and routing-name shape are checked before generating native metadata.
  Unsupported hosts/carriers remain explicitly unavailable. Codex native adapters
  and named-profile support are not added by this change.
- Snapshot inputs include opt-in and the Python runner; assets and every generated
  file are persisted and digest-verified. Remove/restore changes future plugins
  independently; resume reads retained snapshot bytes and recorded arguments.

## Environment repair

F-18's forcing of a resolved directory into `CLAUDE_CONFIG_DIR` was removed.
New records capture exact set/unset/empty representation in the existing pin's
environment provenance. HOME is captured where default-home resolution needs it;
credentials are not captured. Working directory is resolved before recording.

All resume/recovery consumers validate that provenance and absolute working
directory before host access. Older ambiguous prepared/observed records remain
pending and do not block unrelated fresh work; explicit resume of an ambiguous
old pin fails rather than inferring an authentication context. Journal identity
must match its owned directory before recovery can write anywhere.

F-18 is removed from the live defect queue because its code cause and the
set/unset/caller-drift regression are repaired. **An authenticated Claude resume
after the repair remains unverified**; this is not presented as live acceptance.

## Evidence and corrections

The source/hash-bound native startup record is in
`2026-09-08T0725--ed5b00f--native-implementation-evidence/evidence.json`:

- Installed Claude 2.1.263 advertised **four generated plugins** and **three
  qualified corpus agents**.
- An installed hook item edited through the real store to a bounded SessionStart
  probe executed once through the generated plugin. No manual `--settings` hook
  registration was supplied. Native instruction/settings hashes were unchanged.
- The subsequent model stage returned `Not logged in`, with zero model tokens.
  Registration and hook execution therefore count; model instruction receipt,
  authenticated replay, and corpus-agent execution do not.
- Correction, 2026-09-08: native agent routing follows frontmatter `name`, not the
  Markdown filename. A source edit to `verification-sweep` exposed this in the
  real native advertised names. The compiler now reads that bounded slug while
  leaving other YAML semantics with Claude; regenerated routes match the observed
  names, and the renamed-agent regression passes.
- The native plugin validator reports manifests but returns `contents: []` on
  these trees. Validation is credited only as manifest checking; component
  populations are separately asserted. It is not a proxy for invocation or tool
  restriction enforcement.

## Review and verification boundary

`/root/native_adapter_design` ran on the FRONTIER Astra seat with a blind packet.
It selected per-item plugins over reconstructing native YAML as `--agents` JSON
or merging hook settings, principally to preserve policy fields and separate
name ownership. Decision `D-20260908-0cd1da` records the alternatives closed.

An independent fresh REVIEWER seat, `/root/native_runtime_review`, reviewed the
new runtime boundaries. Its relative-CWD finding led to canonical capture and
consumer-side rejection of ambiguous legacy records, including recovery before
host calls. Targeted regression controls cover both hosts and prepared/observed
journals. Additional controls prove an altered journal identity cannot redirect
recovery writes, and an off-native caller cannot supply unverified assets.

SpawnGate: Independence FRONTIER spawn — bounded native-adapter choice closed the
translation/collision alternatives; per-item plugins reduced host reimplementation.

SpawnGate: Parallelism WORKHORSE spawn — environment replay, catalog/plugin
emission, and editor integration had separated ownership.

SpawnGate: Independence REVIEWER spawn — fresh runtime review alongside actual
compiler/store/CLI and native bootstrap checks; no provider verdict is inferred.

Focused tests cover opt-in/off/Vanilla, source/binding edits and restore, retained
old snapshots, asset/file-digest boundaries, malformed carriers, preserved native
frontmatter, exact environment replay, and 80-column TUI binding editing. No fresh
full-umbrella green is claimed: the prior unrelated launcher/binding failures and
older untracked design whitespace remain separate.

Final verification: **78 corpus tests passed** with the installed Textual
interpreter and no skips. Package boundary, surfaces/self-test, ontology,
terminology, content hygiene, decision ledger, and skill validation passed. The
full launcher projection check reproduced the prior twelve binding/preset
assertions plus the previously diagnosed sandbox-only wrapper audit-log stderr
failure. An initial repeat with an empty temporary native home stopped early for
a missing review-route dependency; it is not credited as a complete run.

During final checks, another workstream advanced HEAD to `cca9949` (prompting and
frontier bindings). This work did not commit. Native compiler/store/CLI tests and
ontology checks were repeated after that movement; the native implementation
remains in the working tree. The header names the starting/probed base, not a
claim that this implementation was committed there.

## First next step

The user was asked to confirm Claude login interactively without sending tokens.
After that confirmation, create a fresh temporary live-probe root and run the
actual active→authoring-edit→resume flow, then invoke a **qualified corpus
plugin agent**, verify its child transcript and tool restriction, and repeat the
native on/off/removal contrast. Do not reuse a pre-provenance pin or silently
substitute current defaults for its unknown environment.
