# SURFACES.md — where knowledge and tools reach a model, and what each place admits

agent-bios exists to cut the time and cost of reaching a goal, by putting the right
prior knowledge and the right tool in front of a model for the work it is actually
doing. The binding constraint is the execution environment — above all the context
window — so *what* is delivered matters less than *where it is delivered from*. The
same sentence is cheap in one place and ruinous in another.

This file is the catalog of those places. For each: what it admits, what it refuses,
how it fails when misused, and the code that realizes it.

**This is not a routing history.** `design/session-distill/PLACEMENT-FRAMEWORK.md`
is a dated record of the 2026-07-18 layer ordering; it ranks placement by cheapness
and covers the layers session-distill items are routed into. This file is the
current *full* set of delivery surfaces, including several that record does not name.
Re-derive both from the authorities below before trusting either.

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
| Activated startup corpus | one explicitly activated session, selection-dependent | that session | its main context; children only through a verified projection | behavior, some knowledge |
| Legacy global projection | every native session until explicitly migrated; compatibility only | every session on that old installation | both hosts | behavior, some knowledge |
| Personal learnings | one host's selected activated snapshot | that session | that user and host | knowledge |
| Agent description | only when a verified session adapter registers or compiles it | the dispatcher | the selected session | behavior (routing) |
| Launch contract | one configured session | that session | that session | behavior |
| MCP tool surface | one session, selection-dependent | every turn of it | that session | knowledge, behavior, control |
| Hook injection | one `--corpus-native` Claude session when an installed event carrier is selected | that matching call | generated per-item plugin only | knowledge |
| Guides | when an activated session follows its private router/path | only the reader | the selected session | knowledge, behavior |
| Agent body | one `--corpus-native` Claude session when an installed delegated carrier is selected | that native child | generated namespaced plugin agent | knowledge, behavior |
| Requested procedure | compact entry in selected startup text; body when its private path is read | the activated session, then the caller | the selected session | knowledge, behavior |
| Private management bootstrap | compact entry in every activated snapshot; body on `$corpus` | every activated session, then the caller | the selected session | knowledge, behavior |
| Incubator ledger | never | nobody | whoever searches it | none until promoted |

The immutable release, baseline tuples, personal source tree, Corpus Studio, and
transaction journals are authorities or human-facing clients, not model-consumption
surfaces. Storing or rendering an item there does not activate it. A snapshot is likewise
only composed state until a host adapter supplies it and records the evidence level it
actually observed.

`understand!` uses a selected corpus bundle as learning data, not as a new instruction
or capability surface. `compose/corpus_understand.py` pins the effective source bytes;
the launcher passes its learning prompt into an ordinary scoped interactive session.
The requested `understand` skill owns tutoring and semantic discovery review. Native
transcript evidence, user confirmation, and a successful personal-note save precede
the persistent trophy; the trophy is UI state, never model authority. Learning neither
installs global instructions nor enables native corpus hooks or agents.

## What each surface admits

### Enforcement defaults

- **Admits** — a right way that can be *expressed as a default*: decidable, the same
  every time, with rare exceptions. Tools whose existence makes the right path the
  path of least resistance.
- **Refuses** — anything with frequent exceptions (make it a flag), anything needing
  judgment (guide).
- **Fails as** — a default that is wrong often enough teaches users to route around
  the wrapper, and then it controls nothing. `README.md` deliberately refuses to call
  `codex-run` a policy boundary for exactly this reason.
- **Authority** — the private default dispatcher in `install.sh`, installation and
  ownership checks in `compose/corpus_install.py`, session projection in
  `compose/corpus_session.py`, and launch-plan projection in
  `launch/agent-launch.py`. The default install writes its own `agent-launch`
  entrypoint but does not replace `codex` or `claude` by default. The optional
  `launch/shell_integration.py` owner restores/removes the shell connection from
  the CLI and root TUI, reusing `launch/agent-launch.zsh` with native argument
  passthrough and no added permission flags. It owns only its `.zshrc` block and
  managed script; global instruction files are outside its write set. Host-home
  corpus deploy calls in `install.sh` remain reachable only when
  `AGENT_BIOS_LEGACY_INSTALL=1` selects compatibility/regression behavior.

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
- **Fails as** — a reviewer that inherited the corpus agrees with it; a Vanilla path
  that still sees a legacy marker is not corpus-free merely because the launch argv is
  empty.
- **Authority** — `--profile hermetic` in `wrappers/codex-run.sh`; the structural
  Software Engineer short-circuit in `launch/agent-launch.py`; private-at-rest default
  and explicit legacy cleanup in `compose/corpus_install.py`.

### Activated startup corpus

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
  and compilation in `compose/corpus_catalog.py`, selection/snapshot ownership in
  `compose/corpus_store.py`, and per-call delivery/pinning in
  `compose/corpus_session.py` as invoked by `launch/agent-launch.py`.

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
  `compose/corpus_install.py`; the old writer remains in `compose/assemble.py`,
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
  per-host snapshot selection in `compose/corpus_store.py`; legacy source collection and
  explicit migration in `learn/collect-learning.py`, `learn/migrate-learnings.py`, and
  `compose/corpus_install.py` until every old writer is retired.

### Agent description

- **Admits** — **when to call this agent**, in one sentence, for a selected
  `--corpus-native` Claude plugin whose installed carrier can be registered for that
  session.
- **Refuses** — how the agent works. That is the body.
- **Fails as** — a description that says what the agent *does* rather than when to
  *spawn* it produces both over- and under-delegation. Plugin namespace plus native
  frontmatter name are the route, not a bare launcher tier name; authenticated native
  corpus-agent execution remains a pending observation.
- **Authority** — authored frontmatter in `claude/agents/*.md`, generated templates in
  `codex/agents/*.toml`, item classification in `compose/domains.json`, namespaced native
  plugin compilation in `compose/corpus_catalog.py`, and Claude plugin validation in
  `compose/corpus_session.py`. Legacy Codex registration remains in
  `codex/config-additions.toml` only for the compatibility path.

### Launch contract

- **Admits** — what is true of **this launch only**: the resolved seat, delegation
  state, review plan, workflow trigger, and selected private `ContentRef` context.
- **Refuses** — anything constant across launches. An always-identical injection is a
  selected always item paying a worse price and escaping corpus review, because it
  lives in argv.
- **Fails as** — invisible growth. Nothing about it is in a file a reader opens, which
  is why its rendering is pinned byte-for-byte by a golden.
- **Authority** — the projection and contract renderer in `launch/agent-launch.py`,
  preset/profile source in `launch/agent-launch.toml`, selection/snapshot source in
  `compose/corpus_store.py`, and host/session binding in `compose/corpus_session.py`;
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
  one to three lines useful at exactly that moment. Default-off Claude native consumption
  requires `--corpus-native`, an installed hook carrier, and typed `event`/`matcher`
  binding; the generated plugin root is supplied only to that session.
- **Refuses** — anything whose trigger needs judgment (guide), arbitrary prose promoted
  into code by a surface edit, and extra plugin auto-discovery members. Anything both
  decidable and forbidden should be a *denial*, not a reminder.
- **Fails as** — a broad trigger fires on every call; a copied carrier lacks its typed
  binding; or the authenticated host state needed to observe later hook/agent behavior is
  unavailable. One generated `SessionStart` plugin hook ran automatically without manual
  settings; that does not prove authenticated corpus-agent execution.
- **Authority** — hook source in `claude/hooks/tooling-gotchas-hook.py`, exact binding
  extraction from `claude/settings.template.json`, carrier/plugin compilation in
  `compose/corpus_catalog.py`, and per-session `--plugin-dir` validation in
  `compose/corpus_session.py`. The legacy settings merge remains separate.

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
  the selected activated startup corpus.
- **Fails as** — a router line that does not name the situation the reader is actually
  in makes the guide unreachable. The knowledge is dead while looking present, and
  nothing reports it.
- **Authority** — `claude/guides/`, classification in `compose/domains.json`, generated
  host mirrors from `gates/emit-mirrors.py`, and private member/router compilation in
  `compose/corpus_catalog.py`. `compose/corpus_store.py` binds the emitted guide bytes to
  the immutable snapshot.

### Agent body

- **Admits** — the packet shape that tier receives and the contract it returns. Only
  what the spawned context needs.
- **Refuses** — anything the dispatcher needs in order to decide. That is the
  description.
- **Fails as** — instructions the dispatcher needed sit where only the dispatched can
  read them, a parent-only corpus is assumed to reach a child without an inheritance
  receipt, or a plugin agent is mistaken for the launcher's bare tier agent. Original
  frontmatter is preserved and the snapshot context is appended only to a namespaced
  installed carrier.
- **Authority** — bodies in `claude/agents/*.md`, generated `developer_instructions` in
  `codex/agents/*.toml`, native plugin compilation in `compose/corpus_catalog.py`, and
  `--plugin-dir` validation in `compose/corpus_session.py`.

### Requested procedure

- **Admits** — a selected procedure whose compact authored description tells an
  activated session when to read its exact private snapshot path. Skills use this
  surface by default; a guide can use it through an explicit consumption override.
  Native skill-menu
  discovery is optional evidence, not part of the baseline claim.
- **Refuses** — session-wide settings, permissions, implicit execution of companion
  scripts, or a claim that a copied directory is registered. A selection that does not cover a procedure
  receives neither its compact entry nor its body path.
- **Fails as** — a missing resource rewrite leaves the procedure pointing back to a
  mutable/native host home; calling private path access a native skill overstates what
  the host consumed.
- **Authority** — prose trees in `claude/skills/`, explicitly requested guide bundles
  in `claude/guides/`, stable item metadata in `compose/domains.json`, private
  tree/path compilation in `compose/corpus_catalog.py`,
  and snapshot retention in `compose/corpus_store.py`. The default installer does not
  copy them into native global discovery paths; `deploy_tree` in `install.sh` remains a
  legacy compatibility writer.

### Private management bootstrap

- **Admits** — the one lifecycle-wide procedure for inspecting current authoring and
  creating a revision-checked plan through `agent-bios corpus`; every activated
  snapshot carries it regardless of optional selection.
- **Refuses** — corpus CRUD over itself, free-form ids/paths, direct canonical writes,
  or the claim that its mutation changed the running session. Apply changes future
  activated snapshots only.
- **Fails as** — retaining the file without naming its exact path makes it unreachable;
  registering it globally would violate Vanilla. The snapshot therefore injects a
  compact `$corpus` invocation and calls the result private procedure access, not native
  skill registration.
- **Authority** — procedure contract in `compose/bootstrap/SKILL.md`, machine and rich
  clients in `compose/corpus.py` and `compose/corpus_ui.py`, plan/apply authority in
  `compose/corpus_store.py`, and selected-session injection in
  `launch/agent-launch.py` through `compose/corpus_session.py`.

### Incubator ledger

- **Admits** — candidates whose evidence is below the promotion bar, with the evidence
  kept.
- **Refuses** — anything promotable (promote it) and anything disproven (retire it).
- **Fails as** — it never ships. A rule parked here reaches nobody, and parking reads
  like placement in a status report.
- **Authority** — `design/session-distill/ledger.json`. It is *absent* from
  `package.json` `files[]`, not held out by a gate: adding it there passes
  `gates/check-package.sh`, whose reverse direction covers only `gates/`. Measured, not
  assumed.

## Tools are a second axis

A tool is where knowledge goes when it stops being prose. The leftward rule — mechanize
a gotcha into structure rather than restating it — points here, and a promoted tool is
usually worth more than the guide paragraph it replaces.

A tool admitted to the product must satisfy four things the prose surfaces never face:

- **Reachable** — in `package.json` `files[]`, copied into the immutable release by
  `compose/corpus_install.py`, and named where the selected consumer actually looks
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
7. Must it work **without** recognition? → activated startup corpus — and name the
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

An agent-bios main session is deliberately opened through explicit `agent-launch`
activation; plain CLI and Vanilla receive no agent-bios projection. Presets may select a
permission-bypass execution policy independently of corpus activation. Dispatched
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
  behavior through the real-store `compose/test_corpus*.py` suite reached from
  `gates/check-parity.sh`; `compose/corpus_install.py:verify` re-reads stored release and
  baseline state
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
