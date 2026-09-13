# SURFACES.md — where knowledge and tools reach a model, and what each place admits

These surfaces serve the product purpose stated in `AGENTS.md`: workers select,
share, and inherit team work environments. They determine what selected material
reaches a model, when it reaches it, and under which delivery contract.

Efficient consumption preserves the information needed for the current judgment
while limiting context and retrieval cost. Content, timing, and delivery surface
must be considered together; a shorter response that hides a required condition
or decision conflict does not satisfy that purpose.

This file is the catalog of those places. For each: what it admits, what it refuses,
how it fails when misused, and the code that realizes it.

Every entry describes the current delivery route. Re-derive its scope and evidence
from the named authority before treating a stored artifact as consumed context.

## The one boundary

**A prose surface can never control.** Compliance is the model's choice, so text can
inform and it can steer, but it cannot make an outcome impossible. Only surfaces that
change what is *possible*, what is *reachable*, or what is *accepted* can control.

Every routing mistake in this repo has been a version of ignoring that line — writing a
prohibition where a denial was available, or gating a judgment that was never decidable.

Control comes in exactly four kinds here, and they are not interchangeable:

| Kind | Mechanism | Answers |
| --- | --- | --- |
| Make it impossible | sandbox, tool denial, an unregistered capability | "it must not happen" |
| Make the right way the default | wrappers, launch-time projection | "it should happen without being asked" |
| Make it not land | gates | "it must not be committed" |
| Make it not count | receipt adjudication | "it must not be claimed as done" |

The fourth is the one people forget. A claim about work already performed — *the review
ran, on that seat, over that packet* — cannot be prevented, defaulted, or blocked. It can
only be refused credit.

## The catalog

Ordered by when the cost is paid, because that is the axis that decides placement.

| Surface | Loaded | Cost paid by | Reaches | Can do |
| --- | --- | --- | --- | --- |
| Enforcement defaults | never | nobody | every consumer, incl. scripts and people | control, behavior |
| Verification gates | never | nobody | every consumer, after the fact | control |
| Receipt adjudication | never | nobody | whoever audits the claim | control |
| Capability withholding | never | nobody | the dispatched process | control |
| Activated startup instructions | one explicitly activated session, selection-dependent | that session | its main context; children only through a verified projection | behavior, some knowledge |
| App discovery metadata | when the host discovers an explicitly registered bridge | tasks in that discovery scope | the host's skill selector | routing only |
| App task context | after explicit use in one task | that task | its returned tool/context stream | knowledge, behavior |
| Instruction import evidence | when explicitly supplied for import review | the reviewing task | the reviewing model as source data | knowledge |
| Legacy global projection | every native session until explicitly migrated; compatibility only | every session on that old installation | both hosts | behavior, some knowledge |
| Personal learnings | one host's selected activated snapshot | that session | that user and host | knowledge |
| Agent description | only when a verified session adapter registers or compiles it | the dispatcher | the selected session | behavior (routing) |
| Launch contract | one configured session | that session | that session | behavior |
| MCP tool surface | one session, selection-dependent | every turn of it | that session | knowledge, behavior, control |
| Hook injection | one `--instructions-native` Claude or Codex session when a supported event carrier is selected | that matching call | Claude per-item plugin or Codex session config, subject to host enablement/trust | knowledge |
| Guides | when an activated session follows its private router/path | only the reader | the selected session | knowledge, behavior |
| Agent body | one `--instructions-native` Claude session when an installed delegated carrier is selected | that native child | generated namespaced plugin agent | knowledge, behavior |
| Requested procedure | selected startup entry or explicit installation request; body when its exact path is read | the reader | the requesting task | knowledge, behavior |
| Private management bootstrap | compact entry in a snapshot unless no-instructions mode is selected; body on `$agent-bios` | the selected session, then the caller | the selected session | knowledge, behavior |
| Incubator ledger | never | nobody | whoever searches it | none until promoted |

The immutable release, baseline tuples, personal source tree, setup clients, Instructions
Studio, and transaction journals are authorities or clients. Storing or
rendering an item there does not activate it. Native adapters and the explicit app
context route supply snapshots and report their distinct delivery evidence.

`understand!` uses a selected instructions bundle as learning data, not as a new instruction
or capability surface. `compose/instructions_understand.py` pins the effective source bytes;
the launcher passes a compact learning prompt into an ordinary scoped interactive
session. CLI show, start and session responses expose metadata and compact entry
guidance. `understand read` pages a manifest or one requested pinned body/member;
native turns use the same bounded-output paging contract. Byte offsets, resource
digests and an explicit end marker distinguish partial reads from completed reads.
The requested `understand` skill plans finite core coverage, uses supporting guides
as references, and can explain or summarize without another question. It owns tutoring
and semantic discovery review; its question budget is a tutoring instruction, not a
runtime claim that the model complied. Native
transcript evidence, user confirmation, and a successful personal-note save precede
the persistent trophy; the trophy is UI state, never model authority. Learning neither
installs global instructions nor enables native instructions hooks or agents.

## What each surface admits

### Enforcement defaults

- **Admits** — a right way that can be *expressed as a default*: decidable, the same
  every time, with rare exceptions. Tools whose existence makes the right path the
  path of least resistance.
- **Refuses** — anything with frequent exceptions (make it a flag), anything needing
  judgment (guide).
- **Fails as** — a default that is wrong often enough teaches users to route around
  the wrapper, and then it controls nothing. `docs/advanced-launch.md` deliberately refuses to call
  `codex-run` a policy boundary for exactly this reason.
- **Authority** — the private default dispatcher in `install.sh`, installation and
  ownership checks in `compose/instructions_install.py`, session projection in
  `compose/instructions_session.py`, and launch-plan projection in
  `launch/agent-launch.py`. The accepted install plan writes its own `agent-launch`
  entrypoint but does not replace `codex` or `claude` by default. The optional
  `launch/shell_integration.py` owner restores/removes the shell connection from
  the CLI and root TUI, reusing `launch/agent-launch.zsh` with native argument
  passthrough and no added permission flags. It owns only its `.zshrc` block and
  managed script; global instruction files are outside its write set. Host-home
  instructions deploy calls in `install.sh` remain reachable only when
  `AGENT_BIOS_LEGACY_INSTALL=1` selects compatibility/regression behavior.
  `SetupController` in `compose/instructions_setup.py` owns the reviewed setup plan and
  `compose/instructions_setup_ui.py` renders it; neither classifies imported content or
  activates a model session.
  `compose/instructions_install.py` `setup_local_instructions` reports stored, nonremoved personal
  and host-learning item counts separately from source-catalog choices. Setup inspect
  exposes these as `retained_corpus` and localized display rows, retaining those
  serialized names for compatibility; the UI shows a checked,
  read-only list rather than adding targets or activating content. The read refuses
  malformed, symlinked or pending private state without recovery writes. Available
  dependencies are likewise checked readiness observations; only selected missing
  dependencies with current recipes enter requested install actions. The independent
  **Connect to the Codex app** choice registers the explicit management entrypoint,
  while task instructions use requires a separate request.
  `compose/instructions_setup_i18n.py` supplies English/Korean/Japanese presentation.
  The terminal UI's explicit language chooser precedes dependency probes; locale
  variables suggest its initial value without selecting it. Returning to that chooser
  preserves the setup plan. The UI choice is not persisted. The JSON setup protocol
  records a review language while preserving field names, paths, identifiers and vendor
  diagnostics. Neither route translates instructions bodies or changes host settings.
  `compose/instructions_setup_cli.py` exposes local JSON start, inspect, discover, plan,
  apply, status and resume operations over the same controller without requiring a
  terminal or UI runtime. Its complete review envelope binds context, source bytes,
  state and recipes before Apply. Durable receipts separate completed and uncertain
  effects; status reports the recorded attempt while handoff reports current package,
  runtime and helper evidence separately. `try_transaction_lock` in
  `compose/instructions_transaction.py` checks the existing lock without blocking or creating
  state. If synchronization is unavailable, status returns recorded progress and
  `handoff.verification` is `deferred`, with readiness fields `null` rather than false.
  `checked` means the checks ran, not that all passed. Resume follows recorded
  continuations or issues a nested review for safe remaining work. Neither status nor resume performs
  remaining installation actions. Review identity proves consistency, not user consent.
  `install` and `onboard` open interactive setup unless `--non-interactive` is explicit;
  selection flags seed that UI. A non-TTY default call refuses before writes.
  `compose/instructions_ui_runtime.py` verifies the shipped `compose/ui_runtime/` wheels and
  extracts them temporarily for the process. Installation, package/current-checkout
  Instructions Studio, and private/current-checkout launcher rich CLI paths activate that
  runtime before UI imports. Python 3.11+ is required; preinstalled Textual, pip and
  runtime downloads are not. A broken bundle requires repair rather than silent fallback.
  Standalone compatibility copies and in-process APIs retain their named managed paths.
  Normal exit cleans the runtime; `launch/agent-launch.py` also releases it before
  backend `execve`. UI libraries and their widgets are human-facing clients, not new
  model-consumption surfaces.

### Verification gates

- **Admits** — deterministically decidable structural or security violations, over a
  subject set the gate can prove non-empty, with a negative control that fires by name.
- **Refuses** — semantic, quality, coverage or preservation concerns. Those go to a
  non-blocking disclosure and a person decides.
- **Fails as** — gate a judgment call and people learn to route around the gate. A gate
  with no negative control is not a gate; a gate over an empty subject passes vacuously.
- **Authority** — `gates/`, umbrella at `gates/check-parity.sh`.

### Receipt adjudication

- **Admits** — claims about work already performed, where the evidence is
  argv-independent and observable by a process *other than the claimant*: exit status,
  a hash of what went in, a hash of what came back, the seat actually sent.
- **Refuses** — anything only the claimant can assert. Set-level declarations
  (ordering seed, swap group) are carried but never authenticated, and the difference
  is stated rather than blurred.
- **Fails as** — a receipt field nobody can produce independently is decoration: it
  makes the bundle longer and the audit no stronger. This buys drift, not honesty.
- **Authority** — `RECEIPT_KEYS` and `verify_review_receipts` in
  `launch/agent-launch.py`; the producers are the adapters in `wrappers/`. The chain is
  exercised end to end by `gates/check-receipt-chain.py`, over a space derived from the
  config rather than a list of scenarios.

### Capability withholding

- **Admits** — verifications whose validity depends on the reviewer *not* holding our
  answer, and the user's explicit plain CLI / Software Engineer / Vanilla boundary.
- **Refuses** — silently suppressing native user/project instructions, authentication,
  settings, or policy. Vanilla withholds agent-bios additions only.
- **Fails as** — a reviewer that inherited the instructions agrees with it; a Vanilla path
  that still sees a legacy marker is not instructions-free merely because the launch argv is
  empty.
- **Authority** — `--profile hermetic` in `wrappers/codex-run.sh`; the structural
  Software Engineer short-circuit in `launch/agent-launch.py`; private-at-rest default
  and explicit legacy cleanup in `compose/instructions_install.py`.

### Activated startup instructions

- **Admits** — cross-domain rules needed before the selected session can recognize a
  situation, compressed to a bullet. “Always” means every explicitly activated session
  whose selection contains the item; it never means plain CLI or Vanilla.
- **Refuses** — procedures, tables, measured numbers, worked examples, permissions, and
  claims that a host loaded or invoked the text. Procedures remain behind private paths;
  runtime authority remains in tools and host policy.
- **Fails as** — adding every stored item makes an activated snapshot pay the same
  dilution cost as the old global bundle. Parent injection also does not prove a child
  received it.
- **Authority** — source items in `claude/CLAUDE.md` and `compose/domains.json`, inventory
  and compilation in `compose/instructions_catalog.py`, selection/snapshot ownership in
  `compose/instructions_store.py`, and per-call delivery/pinning in
  `compose/instructions_session.py` as invoked by `launch/agent-launch.py`.

### App discovery metadata

- **Admits** — a compact explicit-use bridge description, helper path and invocation
  policy after the user selects app registration. The bridge itself contains no instructions
  body and does not select a task's instructions.
- **Refuses** — implicit instructions activation, native global instruction edits, replacement
  of foreign discovery entries, and a claim that an on-disk registration was discovered
  or loaded by the app.
- **Fails as** — treating installation or `$agent-bios` discovery as consent to inject all
  stored instructions. Even metadata has a discovery-scope context cost.
- **Authority** — `compose/instructions_app.py` `AppBridge`, `compose/app_bridge/SKILL.md`,
  `compose/app_bridge/agents/openai.yaml`, and `compose/app_bridge/scripts/bridge.py`.
  Explicit register/unregister owns only the `~/.agents/skills/agent-bios` symlink to a
  verified immutable private generation; implicit invocation is disabled. This is the
  named exception to default native discovery preservation. Global `AGENTS.md` and
  `CLAUDE.md` remain outside the write set.

### App task context

- **Admits** — the selected immutable snapshot text returned after explicit use in the
  current app task. Preview names the expected ContentRef; management and status return
  no instructions body. Each task starts with delivery off.
- **Refuses** — native developer-role injection claims, native session pin claims,
  automatic native hook/agent activation, permission changes, and erasure claims after
  text has reached conversation context.
- **Fails as** — interpreting `returned-as-context` as proof of model reading, or saying
  Off removed earlier instructions. Clean exclusion after delivery requires a new task.
- **Authority** — `compose/instructions_app.py` `AppSessions`, snapshot selection in
  `compose/instructions_store.py`, and the explicit procedure/helper in `compose/app_bridge/`.
  App receipts live separately from native CLI pins. The helper resolves the confirmed
  private package and saved roots for each call instead of inheriting prior shell exports.
  Its separate `setup` forwarding uses the same confirmed package and roots but never
  calls session use. Setup requires execution context, not a native task receipt.

### Instruction import evidence

- **Admits** — redacted snapshots of explicitly selected local instruction files,
  original-source digests, recorded scope, and line evidence for model-authored import
  candidates. The model chooses wording and always/relevant/requested placement with
  rationale; relevant/requested bodies carry an authored description for their router
  trigger. Code checks identities, coverage and revision preconditions.
- **Refuses** — executing source instructions during discovery, following arbitrary file
  references, heuristic semantic classification, forged provenance, or converting prose
  into hooks, permissions, agents or executable assets.
- **Fails as** — copying project rules into every task, silently replacing personal edits,
  or assuming preserved native originals stopped loading after import.
- **Authority** — `compose/instructions_import.py`, `learn/redact.py`, and the import plan/apply
  operation in `compose/instructions_store.py`. Discovery is bounded to known global files and
  fixed filenames at explicitly selected project roots. Runtime-owned project/host scope
  is checked before selection and enablement; original files and native settings remain
  unchanged. Imported items become instructions only through a later selected snapshot.

### Legacy global projection

- **Admits** — no new content. It exists only so an older installation can remain
  inspectable until the user accepts a migration preview, and so regression fixtures can
  exercise cleanup.
- **Refuses** — default installation and new activation behavior. A private operation
  never falls through to this writer.
- **Fails as** — an old marker, imported central bundle, discovery file, hook, or shell
  function continues affecting plain CLI and Vanilla after the private package is stored.
  Installation alone cannot claim that legacy exposure is gone.
- **Authority** — exact marker/import/config/hook inventory and previewed removal in
  `compose/instructions_install.py`; the old writer remains in `compose/assemble.py`,
  `launch/agent-launch.zsh`, and `install.sh` behind `AGENT_BIOS_LEGACY_INSTALL=1`.

### Personal learnings

- **Admits** — immutable, host-qualified capture events plus local overlays that change
  how a later selected snapshot presents them.
- **Refuses** — reuse of one `learning_id` for edited bytes, silent remote deletion, or
  semantic merging of a shared target. Promotion suppresses a source only in a snapshot
  that proves the exact captured digest has a safe replacement.
- **Fails as** — treating Claude and Codex event stores as one authority loses host and
  upload identity; treating local edit/reset as remote deletion overclaims an operation
  no protocol performed.
- **Authority** — immutable event ingestion, overlay resolution, promotion checks, and
  per-host snapshot selection in `compose/instructions_store.py`; legacy source collection and
  explicit migration in `learn/collect-learning.py`, `learn/migrate-learnings.py`, and
  `compose/instructions_install.py` until every old writer is retired.

### Agent description

- **Admits** — **when to call this agent**, in one sentence, for a selected
  `--instructions-native` Claude plugin whose installed carrier can be registered for that
  session.
- **Refuses** — how the agent works. That is the body.
- **Fails as** — a description that says what the agent *does* rather than when to
  *spawn* it produces both over- and under-delegation. Plugin namespace plus native
  frontmatter name are the route, not a bare launcher tier name; authenticated native
  instructions-agent execution remains a pending observation.
- **Authority** — authored frontmatter in `claude/agents/*.md`, generated templates in
  `codex/agents/*.toml`, item classification in `compose/domains.json`, namespaced native
  plugin compilation in `compose/instructions_catalog.py`, and Claude plugin validation in
  `compose/instructions_session.py`. Legacy Codex registration remains in
  `codex/config-additions.toml` only for the compatibility path.

### Launch contract

- **Admits** — what is true of **this launch only**: the resolved seat, delegation
  state, review plan, workflow trigger, and selected private `ContentRef` context.
- **Refuses** — anything constant across launches. An always-identical injection is a
  selected always item paying a worse price and escaping instructions review, because it
  lives in argv.
- **Fails as** — invisible growth. Nothing about it is in a file a reader opens, which
  is why its rendering is pinned byte-for-byte by a golden.
- **Authority** — the projection and contract renderer in `launch/agent-launch.py`,
  preset/profile source in `launch/agent-launch.toml`, selection/snapshot source in
  `compose/instructions_store.py`, and host/session binding in `compose/instructions_session.py`;
  review-only portions remain pinned by the routing golden in `gates/check_parity.py`.

### MCP tool surface

- **Admits** — a tool that exists, whose description is needed at call time, for a
  capability this launch actually selected.
- **Refuses** — policy about *whether* to reach for the tool. The tool list is not a
  place for rules; that belongs in a guide.
- **Fails as** — a registered server the plan never selected costs tool-list tokens in
  every turn of the session, and nothing ever calls it.
- **Authority** — `review_mcp_servers` and the `mcp_servers.*` projection in
  `launch/agent-launch.py`.

### Hook injection

- **Admits** — a **machine-detectable trigger** (tool name plus command pattern) with
  one to three lines useful at exactly that moment. Both native adapters default off
  and require `--instructions-native`, an installed canonical hook carrier, and a typed
  `event`/`matcher` supported by the selected host. The command body and binding are
  shared; Claude plugin roots and Codex inline config are session-scoped carriers.
- **Refuses** — triggers that need judgment (guide), arbitrary prose promoted into
  code by a surface edit, unsupported events and extra discovery/config members.
  Event names do not imply identical decision or blocking semantics. The shipped
  tooling reminder is advisory; it neither blocks nor rewrites a call.
- **Fails as** — a broad trigger fires on every call; a carrier lacks its binding;
  the selected host does not discover it; or native enablement/trust suppresses it.
  Both guide trees remain fallbacks, including tools outside a host's hook coverage.
  Codex discovery and exact-trust context injection have a real-host local-transport
  positive/negative control. Neither discovery nor a dry preview proves execution.
- **Authority** — `claude/hooks/tooling-gotchas-hook.py`, binding extraction from
  `claude/settings.template.json`, shared validation/compilation in
  `compose/instructions_catalog.py`, immutable assets in `compose/instructions_store.py`, and
  Claude plugin/Codex session-config delivery in `compose/instructions_session.py`.
  Legacy settings merge/removal remains compatibility-only.

### Guides

- **Admits** — procedure, tables, measured numbers and worked examples: enough bulk
  that an always item cannot carry it, behind a selected private router line that names
  the situation in the reader's own terms. A top-level guide may own a same-stem
  companion tree. The primary is the default readable/editable body; companions are
  separately readable/editable members of the same selectable, restorable item.
  `claude/guides/slide-writing.md` supplies the slide criteria, with its optional
  HTML/PDF runbook and scripts below `claude/guides/slide-writing/`. Job preparation
  derives its oracle from the selected criterion bytes without changing the bundle.
- **Refuses** — anything needed *before* the situation is recognized. That belongs in
  the selected activated startup instructions.
- **Fails as** — a router line that does not name the situation the reader is actually
  in makes the guide unreachable. The knowledge is dead while looking present, and
  nothing reports it.
- **Authority** — `claude/guides/`, classification in `compose/domains.json`, generated
  host mirrors from `gates/emit-mirrors.py`, and private member/router compilation in
  `compose/instructions_catalog.py`. `compose/instructions_store.py` binds the emitted guide bytes to
  the immutable snapshot.

### Agent body

- **Admits** — the packet shape that tier receives and the contract it returns. Only
  what the spawned context needs.
- **Refuses** — anything the dispatcher needs in order to decide. That is the
  description.
- **Fails as** — instructions the dispatcher needed sit where only the dispatched can
  read them, instructions available only to a parent are assumed to reach a child without an inheritance
  receipt, or a plugin agent is mistaken for the launcher's bare tier agent. Original
  frontmatter is preserved and the snapshot context is appended only to a namespaced
  installed carrier.
- **Authority** — bodies in `claude/agents/*.md`, generated `developer_instructions` in
  `codex/agents/*.toml`, native plugin compilation in `compose/instructions_catalog.py`, and
  `--plugin-dir` validation in `compose/instructions_session.py`.

### Requested procedure

- **Admits** — a selected procedure whose compact authored description tells an
  activated session when to read its exact private snapshot path. Skills use this
  surface by default; a guide can use it through an explicit consumption override.
  An explicit repository-link installation request reads `INSTALL.md` for source
  acquisition, then the package's setup guide through the exact path returned by
  `setup start`, before any private installation exists.
  Native skill-menu
  discovery is optional evidence, not part of the baseline claim.
- **Refuses** — session-wide settings, permissions, implicit execution of companion
  scripts, or a claim that a copied directory is registered. A selection that does not
  cover an instructions procedure receives neither its compact entry nor its body path.
- **Fails as** — a missing resource rewrite leaves the procedure pointing back to a
  mutable/native host home; calling private path access a native skill overstates what
  the host consumed.
- **Authority** — prose trees in `claude/skills/`, explicitly requested guide bundles
  in `claude/guides/`, stable item metadata in `compose/domains.json`, private
  tree/path compilation in `compose/instructions_catalog.py`,
  and snapshot retention in `compose/instructions_store.py`. The default installer does not
  copy them into native global discovery paths; `deploy_tree` in `install.sh` remains a
  legacy compatibility writer. `INSTALL.md` owns the public installation entry and
  source-acquisition procedure. `compose/setup/START.md` is a separate installation
  procedure resolved by `compose/instructions_setup_cli.py`; it is not a discovered skill or
  selected instructions body. The conversation collects choices and displays the reviewed
  effects; the shared setup engine owns validation and execution.

### Private management bootstrap

- **Admits** — the one lifecycle-wide procedure for inspecting current authoring and
  creating a revision-checked plan through `agent-bios instructions`; snapshots carry it
  unless no-instructions mode is selected. The app bridge retrieves it on an explicit
  management request.
- **Refuses** — instructions CRUD over itself, free-form ids/paths, direct canonical writes,
  or the claim that its mutation changed the running session. Apply changes future
  activated snapshots only.
- **Fails as** — retaining the file without naming its exact path makes it unreachable;
  putting its body into global instruction files would impose it on unselected sessions.
  The snapshot supplies its private path. The separate app discovery entry carries only
  its explicit-use bridge procedure.
- **Authority** — procedure contract in `compose/bootstrap/SKILL.md`, machine and rich
  clients in `compose/instructions.py` and `compose/instructions_ui.py`, plan/apply authority in
  `compose/instructions_store.py`, and selected-session injection in
  `launch/agent-launch.py` through `compose/instructions_session.py`.

### Incubator ledger

- **Admits** — candidates whose evidence is below the promotion bar, with the evidence
  kept.
- **Refuses** — anything promotable (promote it) and anything disproven (retire it).
- **Fails as** — it never ships. A rule parked here reaches nobody, and parking reads
  like placement in a status report.
- **Authority** — `design/session-distill/ledger.json`. It is *absent* from
  `package.json` `files[]`; the author-side distribution boundary is enforced by
  `gates/check-package.sh`.

## Tools are a second axis

A tool is where knowledge goes when it stops being prose. The leftward rule — mechanize
a gotcha into structure rather than restating it — points here, and a promoted tool is
usually worth more than the guide paragraph it replaces.

A tool admitted to the product must satisfy four things the prose surfaces never face:

- **Reachable** — in `package.json` `files[]`, copied into the immutable release by
  `compose/instructions_install.py`, and named where the selected consumer actually looks
  (the `agent-launch` entrypoint, snapshot text/path, or a verified registration).
  `gates/check-package.sh` derives runtime paths from real references and fails on any
  missing from `files[]` — an unshipped runtime path is invisible from a clone and fatal
  on npm. Stored-but-unselected and copied-but-unregistered both remain inactive.
- **Self-evidencing** — success must be checkable from outside: an exit status, an
  artifact, a hash. A tool whose success is only reported in prose cannot be gated and
  cannot produce a receipt.
- **Degrading** — absence must degrade the route that needs it, never crash the caller.
  Every payload exemption is justified individually and guarded at its call site.
- **Owning its deterministic values** — ids, paths, timestamps, hashes and
  serialization belong to the tool, never to the model. The model supplies bounded
  semantic payloads; the tool creates the canonical artifact.

## Choosing a surface

Ask in this order and stop at the first yes. The order is cheapness, and cheapness here
means *who pays context for it*.

1. Can it be a **default or a tool**? → enforcement. Reaches everyone, costs nothing.
2. Is the violation **decidable**? → gate. Add its negative control in the same change.
3. Is it a claim about **work already done**? → receipt evidence.
4. Is there a **machine-detectable trigger** whose session adapter is verified? → hook;
   otherwise a selected guide and an explicit unavailable disclosure.
5. Does it vary **per launch**? → launch contract.
6. Is it needed only **after** the situation is recognized? → guide behind a router line.
7. Must it work **without** recognition? → activated startup instructions — and name the
   selected bullet it displaces.
8. Is it **user- or machine-specific**? → host-qualified personal learning source.
9. Below the bar? → ledger, with the evidence.

Two rules complete it:

- **Reformulate leftward first.** The type is not fixed. Prefer turning a fact into a
  principle, and a principle into a mechanism, whenever the target surface's bar passes.
  Cheaper and more reliable than prose.
- **Check who executes.** After picking, ask who the executor is when this is needed. If
  it includes a hermetic dispatch or a script, the prose surfaces never reach them —
  escalate to enforcement, a gate, or packet injection.

## Posture: authority at the root, restriction at the leaves

Native agent-bios startup delivery requires explicit `agent-launch` activation;
app task delivery requires explicit use. Plain CLI and Vanilla receive no agent-bios
startup projection. Presets may select a
permission-bypass execution policy independently of instructions activation. Dispatched
reviewers remain deliberately closed — read-only sandboxes, denied mutation tools, and
hermetic profiles.

This asymmetry is the design, not an oversight. A proposal to "tighten control" that
lands on the main session is working against it; the same proposal applied to the
dispatch path is working with it.

## What is checked, and what is not

Checked by repository gates or deterministic runtime validators:

- every runtime path against `package.json` `files[]` (`gates/check-package.sh`)
- the Codex and Korean mirrors against their generator, including the agent
  descriptions projected into `codex/config-additions.toml`
- the rendered review contract, byte-for-byte across every setup/host/family — a
  one-word change to an adapter's shape string fails `gates/goldens/review-matrix.json`
- concept homes and deprecated terminology, with the file set asserted non-empty
- private release, catalog, store, CLI/TUI, migration, session-pin and packaged-flow
  behavior through the real-store `compose/test_instructions*.py` suite reached from
  `gates/check-parity.sh`; `compose/instructions_install.py:verify` re-reads stored release and
  baseline state
- import evidence integrity, source-change refusal, project/host scope, setup preview
  boundaries, and explicit app registration/context receipts through
  `compose/test_instructions_import.py`, `compose/test_instructions_setup.py`, and
  `compose/test_instructions_app.py`; a returned-context receipt does not prove model reading
- UI bundle root-pin agreement, wheel metadata/hashes/licenses, offline isolated
  imports/rendering and cleanup through `gates/build-ui-runtime.py` `--check` and
  `--self-test`; the root pin is `TEXTUAL_PIN` in `launch/provision-venv.sh`
- the receipt chain end to end for every preset and host the config declares, on the
  seat each plan projects (`gates/check-receipt-chain.py`) — and it reports, every run,
  which hosts' panel dispatch is not yet adapter-backed
- **this catalog against the code** (`gates/check-surfaces.py`), in two directions: an
  authority path below that matches no file is a stale declaration, and a deploy target
  no surface claims is a delivery route the catalog does not know about. Its deploy
  extractor currently sees the legacy `deploy_*` call sites, not files copied indirectly
  through the private package manifest; package coverage for the latter belongs to
  `gates/check-package.sh` and the packaged-flow test.

Structural claims above are re-derived from code. **The admission bars are not.** What a
surface *should* accept, and how it fails when misused, is design judgment carried
here so it stops being re-litigated — some of it traceable to a decision or a comment in
the code, some of it argued rather than measured. Read those as the current position,
not as findings.

Not checked, and therefore a judgment every time:

- **a surface reached through indirect private-release copy or per-call injection.** The
  surfaces gate sees literal legacy deploy targets; it cannot infer that a new snapshot
  field reached a host. Loader, invocation, child, and resume claims need their own
  real-path evidence.
- whether an item admitted to a surface actually met that surface's bar
- whether a router line names the situation well enough to be found
- the relative cost claims — no surface's context cost has been measured with
  `session-cost.py`; the ordering is architectural reasoning about who pays and how
  often, which is weaker evidence than it looks

The residual is deliberate. What is left is judgment, and gating a judgment call teaches
people to route around the gate — which is itself one of the admission bars above.
