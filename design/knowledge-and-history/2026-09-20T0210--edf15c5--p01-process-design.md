---
created_at: 2026-09-20T02:10:00+09:00
head: edf15c5
kind: design
status: p01-in-progress-design-adjudicated-spikes-partly-run-nothing-frozen
plan: 2026-09-16T1747--494f996--development-plan.json
node: P01
run_id: team-env-20260920
depends_on: 2026-09-20T0146--edf15c5--p00-rerun-record.md
decisions: D-20260920-4597f7, D-20260920-80164c
---

# P01 process design — what the contract freeze binds, and what the first probes found

P01 is **not** accepted and nothing is frozen. No file exists under `workenv/` or
`gates/workenv/`. This record fixes how P01 will be carried out, which platform bindings it
proposes, what was measured on 2026-09-20, and which choices are the owner's. It does not
restate the design SSOT or the development spec; where it disagrees with either, they win.

All evidence named here is outside the repository, under
`~/.local/share/agent-bios-workbench/team-env-20260920/` (`p01-design/`, `p01-u1/`,
`p01-spikes/`, `p01-brownfield-facts/`), each directory with its own `SHA256SUMS` or receipts.
Re-run the probes rather than trusting the figures; every one names its script.

## How the design was produced

One blind packet (`p01-design/design-packet.md`, ten questions and a rubric) went to two
frontier designers: `gpt-6-astra/max` through the read-only wrapper, with a receipt matching
packet and result hashes, and a fresh `claude-fable-5-1` subagent whose transcript shows it
read only the packet. The coordinator wrote its own leanings and the conditions that would
change them (`coordinator-priors.md`) before reading either draft.

Only the OpenAI draft is provider-different. The second draft shares the coordinator's model
family, so its agreement with the priors is weighted as a shared blind spot, not as
confirmation. Every disagreement between the drafts was settled by a measurement or a primary
source, never by counting votes. `p01-design/adjudication.md` holds the per-question
disposition.

**The packet had a defect, and it was the coordinator's.** It omitted the plan's
`shared_integrator_paths`, which already name `gates/workenv/case-index.json`,
`gates/workenv/fixtures/`, `gates/workenv/conformance/`, `gates/workenv/test_contracts.py`,
one `gates/workenv/test_<area>.py` per later node, `workenv/__init__.py` and
`workenv/contracts/`. Both designers therefore invented registry and driver locations. The
plan's names are used. A designer's worry that P01 "must write outside `workenv/contracts/`"
is answered the same way: those are integrator paths, in coordinator mode the coordinator is
the integrator, and the evaluator constrains `product_changes` only for read-only and
candidate-build nodes.

## Evidence gathered on 2026-09-20

| # | Question | Result | Where |
| --- | --- | --- | --- |
| E1 | Is a registry for all 25 profiles satisfiable under the evaluator's own rules? | Yes. 25 profiles, 33 families, 72 atomic cases, 123 (profile, family) pairs, 205 required-atomic references, no atomic case whose canonical family its profile lacks. A skeleton binding is accepted for 25 of 25, and six known-bad bindings are each refused by name. `binding_errors` and `digest` are imported from the dated checker, not re-implemented. | `p01-u1/u1_feasibility.py` |
| E2 | Evidence-class words | `deterministic` and `observed`. Families N23, N25 and N26 require `observed`: 11 of the 123 pairs. | evaluator constant |
| E3 | Does stock macOS sign and verify SSHSIG offline? | `/usr/bin/ssh-keygen`, OpenSSH_10.2p1. Positive verify exits 0. Altered byte, wrong namespace, identity not allowed, key outside the allowed set and truncated signature each exit 255. Two Ed25519 signings of the same bytes are byte-identical. `-Y check-novalidate` exits 0. | `p01-spikes/sig/` |
| E4 | WAL or rollback journal? | SQLite 3.53.2 on APFS, `fullfsync=ON`: WAL+FULL 4.11 ms per commit, DELETE+EXTRA 11.76, DELETE+FULL 10.92. During a 60-commit burst a second connection made 96 reads at p50 0.01 ms under WAL, and one read that waited 766 ms under DELETE. Control: with `fullfsync=OFF` every profile falls below 0.6 ms, so the pragma reaches the engine. | `p01-spikes/sqlite/` |
| E5 | Can a Claude Code hook answer an elicitation? | The current hooks reference says yes: an `Elicitation` hook can "respond programmatically, skipping the dialog entirely", and an `ElicitationResult` hook can "observe, modify, or block the response". | `p01-spikes/host-docs/` |
| E6 | Does the installed host do that? | Yes. See the next section. | `p01-spikes/host/RESULTS.md` |

## An `accept` is not a person — the finding that changes the design

A stdlib stdio MCP stub was first checked against a scripted client with a known answer,
then run against the installed hosts, headless, in an empty directory.

| Host | Offered protocol | Declared | Headless outcome |
| --- | --- | --- | --- |
| Claude Code 2.1.278 | `2025-11-25` | `elicitation: {}` | `cancel` within 3 ms |
| Codex CLI 0.155.1 | `2025-06-18` | `elicitation: {form, url}` | `decline` within 2 ms, once the server's tools are pre-approved; otherwise `exec` refuses the MCP call before it reaches the server |

With one `Elicitation` hook in the settings passed to Claude Code, the server received
`{"action":"accept","content":{"choice":"alternative_a"}}` after 62 ms with nobody present.
The server cannot tell this from a person choosing. In that run neither `ElicitationResult`
nor the `elicitation_response` notification fired; without the forging hook, both fired on
the host's own `cancel`. That asymmetry was seen once per arm and is only as trustworthy as
the hook configuration, which is the same configuration that can forge.

Consequences, all adopted:

- The coordinator's prior — use the `ElicitationResult` hook as the independent observation
  of a human answer — is **withdrawn**. The host-capability fact file's sentence that a hook
  "cannot supply or alter the user's answer" is wrong for the current host and is corrected
  here, not there (it is a dated evidence file).
- No operation a model can call accepts an answer. Agents get `decision.inspect`,
  `decision.prepare_use` and `decision.resume`; an answer arrives only on a channel the
  host binding has qualified. This removes the tool-surface route. It does not remove the
  hook route, which is a host-configuration boundary.
- The evaluator already requires `automated: false` and
  `response_origin: verified-native-user-event` for `DH-FORM`. C11's answer-evidence record
  must therefore carry what makes `verified` checkable — at minimum the measured effective
  hook configuration for the asking server at the time of the question — and P10 must show,
  attended, that the measurement separates a person from a hook. Until then every host
  binding reads `pending qualification`, and a conflicting decision use stays `pending_user`.
- The supported MCP version set is a closed list probed per host; the two installed hosts
  already differ.

This is the item most likely to need an owner decision or a successor plan. If no installed
host can be shown to separate a person from its own automation, M1's conflict-use proof is
blocked on that host, and the alternatives are a controlled client that agent-bios owns or an
honest `pending_user`. Neither is chosen here.

## Proposed bindings

| Area | Binding | Decided by |
| --- | --- | --- |
| Contract representation | JSON Schema documents are the source. A stdlib validator implements a **closed** keyword set and fails contract load on any other keyword, so the subset cannot drift silently. Runtime-owned fields are marked in the same document and a submit mode rejects them by name: one authored schema, not two. Examples are raw byte files with an expectation sidecar, because duplicate keys and non-canonical bytes cannot be represented as parsed JSON. One error table, checked both ways: a code no negative example exercises fails, and an example naming an unknown code fails. | both drafts; closure answers the prior's change condition |
| Extension point | Not adopted. Compatibility is waived and a changed contract is a replan trigger, so an in-band `ext`/`requires` mechanism is surface every reader carries forever. A `schema` version field with `unsupported_schema_version` stands until a contract demands more. | coordinator, concept economy |
| Canonical bytes and digest | The repository's existing compact convention, with inputs restricted (ASCII snake_case keys, integers only, no duplicate keys, valid UTF-8) so the bytes coincide with RFC 8785. Stored bytes are the hash input; sha256. One owner under `workenv/contracts/`; the four `compose/` copies are not touched. The RFC 8785 coincidence is asserted by vectors and is not yet observed. | both drafts |
| Signature | Detached SSHSIG by the OS `ssh-keygen -Y`, Ed25519, one namespace per record kind, message on stdin, **exit status is the only verdict**. Because "not allowed" and "bad signature" share exit 255, two named codes take two calls (`check-novalidate`, then `verify`), never output parsing. Fixtures are recorded from a real run; no private key is committed. Tool absent: `not_runnable` for the case and `unsupported` for the operation, never `passed`. The account-free personal path signs nothing. | E3 |
| Secret and unlock | The device key is a dedicated passphrase-encrypted OpenSSH key, unlocked by the person at OpenSSH's own TTY prompt into a workenv-owned `ssh-agent`, never the login agent. agent-bios never holds the passphrase. `active` / `locked` / `signed_out` and the access generation live in the database; lock commits the new generation **before** the agent is purged, and a live agent never upgrades the state. No TTY: the access gap `locked`, not an error and not a pass. | both drafts |
| State database | WAL, `synchronous=FULL`, `fullfsync` and `checkpoint_fullfsync` on, explicit `BEGIN IMMEDIATE`, every setting read back on every connection with refusal on mismatch, SQLite version and compile options recorded. One declarative connection profile serves two databases — P02's profile access database and P03's namespace database — so P02 and P03 stay independent. WAL's price is accepted by name: a `during_checkpoint` fault point, backup only through the backup API, refusal when the returned journal mode is not `wal`. | E4, against the OpenAI recommendation |
| Publication order | Stage, sync members and manifest, read back and re-hash, rename into the digest directory (an existing directory is compared, never replaced), sync the directory, then one transaction moves head, receipt and outbox. An object without a receipt is unaccepted. Nine named fault points, each hit in a child process that records the hit before it exits. | both drafts |
| Decision-use entrances | One owner; typed CLI and a stdlib stdio MCP server exposing the three operations above. | both drafts; E6 |
| Studio bridge | Loopback HTTP for a browser only; TUI and CLI call the operations in-process. Per-launch token in the URL fragment, no cookie (cookies are not port-isolated), exact `Host` and `Origin` checks. The token identifies a client instance and grants nothing; the access generation is re-read before a body is written. | both drafts; not yet probed |
| Case registry | Catalog ids verbatim. New cases are defined once as `<FAMILY>-<SUBJECT>-<POS\|NEG>` and each profile's binding selects the cases in its own scope; this is the adopted reading of the catalog's "task-scoped ids, authored once". Cases bind to adapter-contract selectors and contract fixtures, never to implementations, host versions or unit tests. Qualification status is evidence, not registry content. P00's binding is carried **verbatim**, or P00's `binding_digest` goes stale. Every (profile, family) pair gets a positive and a negative. | E1 |
| Repository fit | A slug may have more than one declared home, each exact-file entry with its own reason, landing with the node that creates the file; P01's own files are named by contract id and collide with no claimed slug. `gates/workenv/` is wired into the umbrella through one driver that asserts a non-empty file set and tests-run above zero per file, with a self-test. `workenv/` stays out of `files[]` under one pending-package entry until P18. | both drafts; not yet probed |
| Existing entrances | One deciding property: can the entrance reach state the target keeps, through a root the caller chose, without the one admission owner? Guards sit at three library choke points, not at fifty commands. Compatibility-only routes retire by name at the single cutover, which is quiesced, verified and abortable until its one commit. Whether `instructions-state.py` is reachable with the legacy switch unset must be traced before it is listed for retirement. | Anthropic draft; not yet probed |

## Work units

| Unit | Work | Closes when | State |
| --- | --- | --- | --- |
| U1 | Registry feasibility against the evaluator | skeleton accepted 25/25, known-bad bindings refused by name | **done** (E1) |
| U2 | Host handshake and answer-origin probe | both logs show `initialize`; the scripted control shows `accept` | **done headless** (E6); attended behaviour is P10's |
| U3 | Signature probe | positive 0, negatives non-zero, fixtures recorded | **macOS done** (E3); Linux open; fixtures not yet recorded |
| U4 | Unlock probe — attended, a person types a passphrase | agent-backed sign succeeds, sign after lock fails, the no-TTY result is recorded | open |
| U5 | Storage probe and crash harness | every named fault point hit, invariants hold | settings measured (E4); harness open |
| U6 | Bridge probe | positive control 200, five refusals, late result refused | open |
| U7 | Canonical encoder, closed validator, error table, emitters | RFC 8785 vectors pass; an unsupported keyword fails by name | open |
| U8 | Schemas and byte examples for C01–C12 and the binding records | every error code exercised; every runtime-owned field has a submit negative | open |
| U9 | Lexicon, umbrella and package patches with their controls | each control fails on revert, by name; umbrella green on the staged index | open |
| U10 | Entrance dispositions and the cutover shape | construction-site count equals the guarded set | open |
| U11 | Case definitions for 123 pairs, selectors, fixtures; a blind consumer walk-through per profile on the other provider; dry composition of the P02, P03 and R0 packets | no reviewer reports an inexpressible required case; packets compose with no unfilled field | open |
| U12 | Emit `case-bindings`, measure the `contracts` subject, run the two bootstrap cases, control-revert audit, evaluator acceptance on the real run file | evaluator accepts P01; artifact inventory is exactly `case-bindings` and `result-evidence` | open |

P01's `inputs` must reference `digest(records[P00])` =
`9c510027f6db6567b3e4af08d4b7d689d0f1a89df0473eac6c3439eb0b68361e` from the 2026-09-20 run.
After U9 changes shared files, re-measure P00's `baseline` subject and decide whether P00
needs fresh evidence before P01 is recorded.

## Choices that are the owner's

Each has a default that is taken if the owner says nothing, because each default is the
reversible side.

| Choice | Default | The other side |
| --- | --- | --- |
| What counts as a person's answer on a host whose automation can answer for them | Treat no current host as qualified; keep conflicting uses `pending_user`; require attended P10 evidence plus a measured hook configuration | Accept `accept` as an answer — rejected, it contradicts the SSOT; or build a client agent-bios controls — a new user-visible surface and probably a successor plan |
| At-rest protection of protected bodies | Measure volume encryption and disclose `storage_not_encrypted` as a material gap; Team policy may tighten later | Refuse protected persistence on an unencrypted volume, as the OpenAI draft proposed; the SSOT does not require it |
| Unlock without a terminal | Unsupported; account-free work continues | Qualify an askpass or Keychain route in P11, which puts a secret on a path agent-bios owns |
| Two planned file names that collide with the concept-home gate | More than one home per slug, plan identity intact | Rename the files — a dated successor plan that invalidates every record, P00's included |
| First user-visible removals (legacy deployer, the old command word, thirteen shims, legacy env aliases) | Retire at the cutover, failing by name | Carry the `retired_entrance` message for one release before the code goes |

## Recorded as unavailable, each with the probe that would qualify it

Claude desktop, all question capability (registration untested) — P10. Codex
`tool/requestUserInput`, experimental — P10. Conversation-origin answers on Claude Code — P10,
`DH-CONVERSATION`. Elicitation answered by a person on either host — P10, `DH-FORM`, attended.
GUI or askpass unlock and a Keychain-remembered passphrase — P11. Bearer-secret storage — P12
and P13. Hardware-backed keys and any algorithm but Ed25519 — a versioned contract revision.
A Linux image without OpenSSH — `unsupported` for signed operations, by U3's Linux run.
Windows. Screen-reader and IME behaviour — N26 gets a protocol from P01, not an observation.

## Not verified

The RFC 8785 coincidence; SSHSIG and SQLite behaviour on Linux; agent-backed signing and
no-TTY unlock; the crash harness; the bridge refusals; whether the lexicon emitter can carry
a list of homes without a wider rewrite; whether the reach scan treats a `gates/workenv/`
driver as a subject; the legacy-reachability trace; whether hook configuration written in
mid-session takes effect without the host's review step; attended behaviour of any host.
