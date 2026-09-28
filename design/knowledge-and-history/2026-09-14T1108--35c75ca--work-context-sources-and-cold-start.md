---
created_at: 2026-09-14T11:08:45+09:00
head: 35c75ca
kind: design
status: proposed-source-and-cold-start-contract
amends:
  - 2026-09-14T0914--35c75ca--studio-wireframes-and-surfaces.md
  - 2026-09-14T1047--35c75ca--studio-hub-and-spoke-navigation.md
consumption: 2026-09-13T2138--35c75ca--knowledge-memory-consumption.md
---

# W01/W09: source provenance and starting without prior context

## Correction to the wireframes

The current W01/W09 wireframe examples contain hard-coded fictional task names,
knowledge, decisions and earlier delivery records. They are not read from a
working repository, a remote GitHub repository or a host session. In particular,
W09's unconditional prior-task panel and W01's default continuation language
omit legitimate first-use states. Those assumptions are amended here; the dated
wireframes remain evidence of the earlier proposal, not an implemented reader.

Use **W01: Work preparation (`작업 준비`)** and **W09: Use target and delivery
(`사용 대상과 전달`)** as the screen-family descriptions. Show `이어서` only
when an actual identified prior context supports that action. A project,
repository, task title, predecessor and existing Decision memory are not
universal prerequisites for preparing useful work.

The product purpose is continuity of Team standards and decision context, not
the invention of history where none was recorded. Source grounding and honest
cold-start behavior are necessary for that purpose.

## 1. W01 is a derived preparation, not a remote task database

W01 assembles a scoped reading/preparation result from separate inputs. It is
not a fourth knowledge store, a clone of an issue tracker, or a rule that all
work must be registered in Studio first. The existing proposed operation
manifest carries its input identities and qualifications; reusable source
material remains owned by its role-specific provider.

| Visible information | Input/owner | What that input can establish | What it cannot establish alone |
| --- | --- | --- | --- |
| Selected Team, role environment and static source editions | Explicit user selection or a previously verified binding, resolved through the authorized environment provider | Intended shared standards, selected Instructions/knowledge editions and permitted memory scope | Membership or privileges inferred from a project/repository name |
| Present goal and constraints | Current user request, explicit host task context, or a selected issue/brief supplied through a supported connection | What this worker is trying to do now | Every fact in private prior conversations, current implementation or actual completion |
| Existing project state | Selected local worktree/folder/documents or explicitly fetched remote artifacts | Observed structure, configuration, implementation and documented assertions at the inspected state | Historical reasons, approval, deployed behavior, or an automatic right to change the Team standard |
| What was decided and why | Authorized Decision memory plus explicitly connected/imported ADR, decision, meeting or PR evidence | Recorded choices, stated reasons and qualified lifecycle state in the inspected scope | A reason inferred merely from the code, a complete history, or current state without relevant correction closure |
| Useful task support | Selected Instructions and knowledge readers, scoped memory reader, bounded project evidence | A derived brief with required meaning, source links, missing conditions and limitations | New accepted knowledge or a Team decision simply because the summary was generated |
| Previous preparation/delivery, if any | Actual saved operation manifest and supported host/adapter receipts | Which scope and body were previously prepared or returned to an identified target | Bodies retained after compaction or a model's actual reading/obedience |

The current implementation already makes a narrower delivery distinction:
[AppSessions](../../compose/instructions_app.py:262) records returned Instructions
context separately from native pins; [its result](../../compose/instructions_app.py:367)
does not certify native startup loading or model reading. That mechanism does
not implement the proposed project-context, knowledge or memory readers.

### Working-project repository versus Team synchronization repository

These may both be hosted on GitHub, but their roles are different:

- The **working-project repository** supplies allowed project evidence and
  artifacts. It may be local, remote, offline, absent, or one of several
  relevant locations.
- The **agent-bios Team synchronization repository** carries permitted Team
  source revisions, checkpoints and shared records. It is one optional exchange
  path in the P2P architecture, not the automatic origin of all project history.

Neither location implies the other or grants its permissions. Do not initialize
an agent-bios directory inside the working project, upload the project to the
Team repository, or enroll another Team merely because a URL or folder was
selected. Those are separate explicitly scoped operations if later needed.

## 2. How the input becomes known

Resolve the Team/environment first from confirmed available context or an
explicit selection. Reuse host-supplied current task/location when supported,
with its actual observation scope. Do not ask the user to retype information
the host already supplies, and do not pretend a bare task ID supplies its body.

If the working location is unclear, offer `기존 작업 연결`, `폴더·자료 선택`,
and `자료 없이 준비`. A spreadsheet, policy document, local folder or user brief
can be a valid work object; no Git repository is required. If the user only wants
to browse environments, route to W02 instead of demanding a work goal.

When a question materially changes the relevant knowledge, allowed action or
interpretation, ask for that missing condition. Otherwise proceed with the
qualified known scope. No universal job-title/task-card form is introduced.

The location shown in W01 names what was actually inspected: a local checkout,
remote ref, document version, supplied artifact or no project yet. A remote URL
is a locator until its selected contents are obtained. Prefer the selected
actual working copy for a local edit task; do not overwrite its meaning with
the remote's HEAD or silently discard local changes.

Each evidence unit records source identity/location, inspected scope, exact
revision or selected-byte references, observation time and qualification.
HEAD alone does not identify dirty or untracked selected files. A bounded file
set can carry individual content references without snapshotting the entire
repository. Preserve the distinction between committed state and the inspected
working tree. Recheck materially changed evidence before dependent action.

## 3. Existing project with no agent-bios history

An existing project does not imply existing agent-bios metadata. It also does
not imply that no decisions were ever made. W01 offers **bounded current-state
discovery**, not mandatory exhaustive archaeology.

1. Establish the intended Team/environment, present request and selected
   project/artifact scope. State which local or remote location will be read.
2. Inspect the relevant entry documents, configuration, artifacts and code as
   appropriate to that task. Look for existing decision evidence only within
   the authorized scope; additional remote history is optional and explicit.
3. Separate observed current facts, documented constraints/decisions, and
   uncertain interpretations. Include source anchors and what was not checked.
4. Ask only for gaps that change a consequential next decision. Support
   inspection, comparison, reproduction or a draft while other questions remain
   open; do not call the dependent implementation/claim ready without its
   required evidence or authority.
5. If a new choice is made, record it now with its actual reasons and premises.
   A person explaining an old choice today provides a present attestation with
   the asserted historical context, not an invented earlier approval timestamp.

For example, inspected code that retries twice supports "this implementation
retries twice at the inspected revision." It does not support "the Team chose
two retries to reduce cost" unless actual decision evidence states that reason.
A document, commit or PR can contain such evidence, but its author, scope,
status, later corrections and current applicability still need interpretation.

Reading a test establishes what that test asserts, not that it passed. Reading
code/configuration establishes the inspected implementation, not necessarily
deployed runtime behavior. Executed observations require their own permitted
run and attributable evidence; W01 must preserve that distinction.

Existing local/native project instructions retain their host-governed role.
Reading project documentation as evidence does not silently raise it to a new
system/developer instruction, and selecting a Team environment does not erase
incompatible native constraints. Resolve material conflict according to the
existing authority/context contract rather than guessing precedence from file
location or recency.

The discovery result is a derived project baseline with visible gaps. Local
inspection does not automatically publish that baseline into shared knowledge
or Decision memory, index all transcripts, or upload private project material.
Creating a reusable Team source or accepted decision follows the relevant
contribution/approval contract.

## 4. Empty, missing, unknown and unavailable are different

| Situation | Accurate UI wording | Effect |
| --- | --- | --- |
| Project not selected | `아직 작업 자료를 연결하지 않았습니다` | Select a source or prepare without one; ask only if the task needs it |
| Source has not been inspected | `이 범위는 아직 확인하지 않았습니다` | Offer bounded inspection; do not assert that records are absent |
| Authorized decision lookup succeeded and found none | `선택한 범위에서 연결된 결정 기록을 찾지 못했습니다` | A legitimate empty result; may continue where no prior decision is required |
| A decision exists without its reason | `선택은 기록되어 있고, 이유는 기록되어 있지 않습니다` | Preserve the choice's status; do not fill the reason with inference |
| Source/record is denied or unreachable | `필요한 기록을 확인할 수 없습니다` with an authorized remedy | Not an empty result; required dependent preparation remains incomplete |
| Sources disagree or their current state is unresolved | `현재 기준을 확정할 근거가 부족합니다` | Preserve the conflict and identify the affected action |
| There is genuinely no prior project/recipient | `새 작업` / no predecessor comparison | Do not create a fictional history panel |
| Offline with permitted complete local sources | `마지막으로 확인한 기준으로 준비합니다` | Follow offline policy and disclose freshness; offline is not absence |

Do not reveal restricted record identities or counts to explain a denied lookup.
"No records found" is scoped negative evidence, not a claim that no decision
ever existed. A required-subject query or state-changing correction that cannot
be resolved must not vanish when the system switches to a cold-start layout.

## 5. New work with no project yet

W01 starts from the selected Team environment and the current request. It can
provide the working method, applicable domain map/support, known Team-level
constraints, and the few missing conditions needed to begin. Creating a local
repository, task card or project registration is not mandatory preparation.

New work does **not** mean all Team memory is empty. Relevant Team/industry
decisions may already apply even when this project has no history. Query them
under their actual scope and qualify their relevance; do not copy another
project's decisions as this project's past. A genuinely empty new workstream
is a valid result, not a reason to manufacture seed decisions.

If a suitable adopted environment exists, use it within its source conditions.
If none exists, offer an explicit candidate/default selection or environment
draft through W02. A public/general source is not automatically the Team's
approved standard. Researching and drafting can proceed in an explicitly
unadopted scope when permitted, without claiming Team-standard readiness.

Start recording actual new choices from this work forward when they close
alternatives. Capture intent, rationale and outcomes at their real occurrence
rather than attempting to reconstruct all missing history before useful work.

## 6. W09 describes a recipient plan and observed results

W09 receives the exact prepared context from W01 (or an identified earlier
preparation/handoff) and the target descriptor from the supported host adapter
or explicit user selection. It does not discover recipients from a remote
repository, infer them from peers holding copies, or invent a session ID.

| Origin | Display | Required check |
| --- | --- | --- |
| New recipient | Planned host/recipient type and context to deliver; omit predecessor panel | Confirm/create the actual target through its supported operation before claiming delivery |
| Identified previous work | Exact prior task/manifest and its known delivery status | Revalidate current permission, compatibility and retained bodies; earlier delivery does not prove current context retention |
| Handoff/delegation | Source work and actual destination, with permitted scope | The new recipient's rights, required body/reader access and actual delivery evidence |
| No supported delivery adapter | Prepared material and allowed manual/export route, if any | Show prepared/exported only; user attestation and host-observed delivery have different evidence labels |

The screen progresses through meaningful evidence states:

`target planned → required material prepared → delivery requested → observed result`

Prepared is not delivered. A result may be returned-as-context, native activation
confirmed, unsupported or unknown depending on the adapter; preserve those exact
meanings. An observation of actual use is separate from transmission, and model
understanding/obedience remains unproven. A delivery receipt from one host does
not automatically have the evidential strength of another host's observation.

An unknown result uses the same request-bound recovery path. New/current/child
targets retain the existing isolation and access rules. A receiver with no
reader needs the permitted necessary bodies delivered directly or an explicit
unmet requirement; a locator or parent's receipt is insufficient.

## 7. Revised screen states and hub paths

| Entry condition | W01 state and action | W09 state |
| --- | --- | --- |
| Known work with usable records | `작업 준비` with prior-context summary; `이 범위로 이어서 준비` | Identified prior context plus actual/planned recipient |
| Brownfield, no connected context | `현재 상태부터 파악` with inspected/not-checked sources; `현재 자료 살펴보기` / `기록 연결` | Newly prepared baseline and target; no fictional prior delivery |
| Greenfield | Team environment plus current goal; `이 환경으로 시작 준비` | New target; no predecessor panel |
| Work location/goal not known | `기존 작업 연결` / `폴더·자료 선택` / `자료 없이 준비` | Not yet prepared; no delivery claim |
| Environment browsing only | Route to W02 without a work-registration requirement | W09 need not open |

The hub's Work spoke remains, but it no longer assumes every arrival means
resuming a previous task. Evidence/record recovery links to W03/W04/W08; return
preserves the original preparation and distinguishes inspection, contribution,
Team acceptance and actual delivery.

### Conceptual flow

```text
Selected Team environment ───┐
Current request/host context ├─> scoped preparation (W01)
Inspected work artifacts ────┤      │
Recorded decisions ──────────┘      ├─ current facts / recorded choices / unknowns
                                   └─ exact prepared body + qualifications
                                               │
Actual or planned recipient ──────────────> use target and delivery (W09)
                                               │
Supported host/adapter evidence ──────────> qualified observed result
```

Remote project content is one optional work-artifact source. The Team sync
repository is one optional source-transport route. Neither replaces the other
inputs or the actual recipient evidence.

## 8. Acceptance and status

- Brownfield code with no ADR reports observed implementation and unknown
  reasons; generated explanations are not accepted historical decisions.
- Local dirty/untracked evidence differs from remote HEAD and remains precisely
  attributed; a changed inspected file invalidates the dependent stale claim.
- Remote unavailability permits authorized local discovery where sufficient;
  an inaccessible required record is not relabeled empty.
- New project preparation has no invented predecessor, past decision or receipt,
  while applicable Team-level decisions can still be retrieved.
- A prior host task with lost bodies rehydrates from available sources and
  discloses unrecoverable context rather than claiming retained memory.
- User rationale supplied now is a present attestation/new decision, with its
  real scope and date, not a backdated adoption record.
- Projectless/noncoding work can prepare without creating a Git repository or
  an additional task-tracking object.
- W09 before delivery has a planned target, not a fabricated real target ID.
  Manual export and unknown delivery do not become verified activation.

Two delegated reviews confirmed the missing cold-start branch and recommended
source-specific provenance, bounded brownfield discovery, legitimate empty
history and recipient-specific evidence. This record adds the contract and
screen-state design; no actual project was scanned, imported, uploaded or
modified. No repository, task or receiver was created. The current production
Instructions mechanisms are evidence for their narrow implemented behavior,
not proof that the proposed W01/W09 pipeline exists.
