---
created_at: 2026-10-02T08:34:37+09:00
head: f40ef98
kind: design
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V2
supersedes: null
decisions: D-20261002-c65b60, D-20261002-8abec4, D-20261002-9257c1
---

# V2 in five slices: decision records and their state, a use that waits for a question, the person's answer from their own prompt, both hosts, and the entry

V2 is the plan's second implementation stage, "Decision memory: decisions carry forward, and a
conflict is asked in the working CLI". It depends on V1, accepted at `f40ef98`
([acceptance record](2026-10-02T0805--6b4e67a--v1-acceptance-record.md)). This record is the
plan for building it, written before any of it exists. It states no implemented behaviour.

## What V2 must show

The plan's V2 node has thirteen `done_when` clauses. In short:

- **[0]** On this machine: record two conflicting decisions, start a new session, be asked in
  the CLI, answer, restart, and see the choice hold. Written down in a dated direct-use record.
- **[1] … [6]** Decision records and their events, reduced to a current state before anything
  is ranked; conflicts and broken lifecycles left unresolved rather than resolved by scope or
  recency; repository ADRs, Team ADRs and personal records keeping their source authority; at an
  actual conflicting use, the person's application in keep or ask mode, invalidated when a
  participant changes, and one logical use asked once.
- **[7] … [10]** Inspect, prepare a use, answer and resume through one local owner; the
  question asked in the working conversation, with the person's reply told apart from the
  agent's own arguments; a headless or unqualified route keeps the use pending.
- **[11], [12]** The entry shows nine scope and role positions, a separate effective view, and
  whether a decision use is pending or resolved. It does not ask the question itself.

Its profile is 47 cases: V1's 21, run again, and 26 of its own.

## What exists at `f40ef98`

Read from the tree, not run.

- **Contracts and serving rows exist; no code serves them.**
  - The operations V2 serves have contract rows: C05 (`workstream.open`,
    `memory.record.publish`, `memory.lifecycle.apply`, `memory.state.resolve`,
    `memory.preference.record`), C06 (`memory.use.prepare`, `reader.body.read`,
    `reader.question.answer`, `reader.use.resume`), C11 (`recipient.answer.record`), C04
    (`role.project`) and C07 (`preparation.assess`).
  - `gates/workenv/conformance/serving.json` routes each to an entry. None of the entries
    exists.
- **Modules missing.** `workenv/memory.py`, `workenv/memory_use.py`, `workenv/reading.py`,
  `workenv/admission.py` and `gates/workenv/units/v2/`.
- **V1 entries that refuse what V2 needs.**
  - `recipient.delivery.attempt` serves bodies only (`workenv/delivery.py`).
  - `capability.probe` serves the four delivery capabilities only (`workenv/hosts/probes.py`).
- **Nothing to build on.**
  - The store has no tables for uses, questions, answers or preferences.
  - The hook reads no prompt text.
  - The shipped guide `workenv/guides/memory-use.md` says reading decision records for a use,
    and recording an answer, are not available in this version.
- **Missing driver features.** Two V2 cases (DC-RACE, CMP-LOCAL) use the world features
  `processes` and `partitions`, and `gates/workenv/conformance/features/` has neither.

## What the owner decided before building

- **The person's answer is their next prompt in the same conversation** (`D-20261002-c65b60`).
  - The host's prompt hook (`UserPromptSubmit`) observes it, apart from the agent's arguments.
  - This is one route for Claude Code and Codex alike.
  - It counts only in an interactive session. A headless or unqualified session keeps the use
    pending.
  - Closed: Claude Code's native choice tool, with a separate route on Codex.
- **A conflict is recognized deterministically** (`D-20261002-8abec4`).
  - Records conflict when they answer the same question, their stated applicability overlaps,
    and their choices differ, after lifecycle and applicability are reduced.
  - No semantic matching, and no new contract field.
  - Closed: a concern-key field on `choice_record`, which would change a frozen contract and
    reopen P01.
- **An existing Markdown ADR is exact source bytes** (`D-20261002-9257c1`).
  - A typed choice record is published beside the observed ADR bytes.
  - No parser derives a record from Markdown.
  - Closed: a parser for common ADR formats.

## The slices

Each slice ends with its cases passing, the V1 cases still passing, its own tests and mutation
sweep, and a dated record.

1. **Decision records and their current state.**
   - Builds `workenv/memory.py`: `workstream.open`, `memory.record.publish`,
     `memory.lifecycle.apply` and `memory.state.resolve`.
   - Reduces lifecycle events to a current state. Leaves conflicts, missing targets, cycles,
     competing successors and contradicting events unresolved, by name.
   - Repository ADRs are read as exact bytes.
   - Cases: DC-SET, N07-C05-POS, N07-C05-NEG, N07-STATE-GAP-NEG, N07-STATE-SOURCE-NEG,
     N27-ADR-POS, SRC-10, SRC-11.
2. **Reading, and a use that waits for a question.**
   - Builds `workenv/reading.py` (`reader.body.read`) and `workenv/memory_use.py`
     (`memory.use.prepare`).
   - Adds a durable pending use and question, minted by the owner and found again on retry,
     replay or restart.
   - Releases every lock before the use waits on a person.
   - Covers the router `role_projection` at activation.
   - Cases: N08-C06-POS, N08-INSPECT-NEG, N21-HISTORY-POS, N05-WAIT-POS, N04-ROUTER-POS,
     N04-ROUTER-NEG, and DC-ASK's preparation steps.
3. **The question, the answer and the resumed use.**
   - Question delivery through `recipient.delivery.attempt`.
   - `reader.question.answer`, `recipient.answer.record`, `reader.use.resume` and
     `memory.preference.record`.
   - Keep and ask mode. A kept application is invalidated by a participant change and not
     revived by a revert.
   - Cases: DC-CHOICE, DC-CHANGE, DC-HOST, DC-ASK, DC-RACE, N08-PENDING-NEG, N15-ANSWER-NEG.
4. **Both hosts.**
   - `capability.probe` for the `user_event`, `question` and `read` capabilities.
   - The prompt hook reads the person's reply and records it as a host reply with the host's
     configuration as measured then.
   - Question delivery in the working conversation.
   - `memory-use.md` rewritten for what now exists.
   - The `host-conversation-evidence` artifact.
   - The direct use that [0] asks for, on Claude Code and on Codex.
   - Cases: DH-CONVERSATION, DH-PENDING.
5. **The entry and the rest.**
   - The entry's nine positions, a separate effective view, and decision-use status.
   - `preparation.assess` and `role.project`.
   - Cases: CMP-UI, CMP-LOCAL, N09-C07-NEG.

After the fifth slice V2 is recorded, reviewed and brought to the owner as V1 was, under the
review rule of `D-20261002-fceb6a`.

## The test driver, and what it moves

`gates/workenv/conformance/` and `gates/workenv/fixtures/` are shared integrator paths ("patch
proposals; never concurrent writes"). V2 needs the driver to grow, at least:

- **World features.** `processes` and `partitions`, for DC-RACE and CMP-LOCAL.
- **Rule contexts.** Contexts for the C06 and C11 rules the runner cannot read yet, for
  N21-HISTORY-POS and N15-ANSWER-NEG.
- **Probe answers.** A way to answer `user_event`, `question` and `read` probe steps.

These may move V1's frozen case binding as well as V2's. `cases.py --bindings` is compared with
`run-21`'s 13 frozen bindings after each driver change. Where V1's moves, P01 is frozen again
before V2's record. V1 then reads stale until V2's acceptance re-establishes it, by the stage
chain the evaluator admits (`CURRENT.md`, the implementation task graph).

## To settle where it is met

These are differences between frozen scenarios. They are not yet known to be defects.

- **`memory.use.prepare` on a conflicting use.**
  - N04-ROUTER-POS and N04-ROUTER-NEG expect `previewed` with no gap.
  - Twenty-six other steps expect `blocked` with `choice_conflict_unresolved`.
  - Slice 2 reads why before it implements either.
- **The same delivery gap at different stages.** `answer_origin_unverified` is `refused` in
  DC-HOST and `blocked` in N08-PENDING-NEG. Slice 3 reads why.
- **Where the documents are silent.**
  - Changing keep or ask mode without answering a question.
  - Which operation is the "inspect" entrance.
  - The plan's V2 node does not list C12, though its probes are C12.
  - Each is settled in the slice that meets it, as a decision where it closes an alternative.
- **Restart and keep.** DC-KEEP and DC-DURABLE are not V2-required cases, though [0] asks
  that a choice hold across a restart. The direct use in slice 4 shows it.

## Not decided here

- How a question is worded in the conversation.
- How the person's prompt is matched to the alternatives offered.
- What an interactive session is, measured per host.

Slice 4 brings these to the owner with what it measured.
