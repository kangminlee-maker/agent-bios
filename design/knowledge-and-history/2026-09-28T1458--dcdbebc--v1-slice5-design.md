---
created_at: 2026-09-28T14:58:13+09:00
head: dcdbebc
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260928-09cd4b, D-20260928-d6ff3a, D-20260926-8ee6bb, D-20260926-421d82, D-20260928-30d875
---

# V1, fifth slice: the entrances

The [14:37 survey](2026-09-28T1437--dcdbebc--v1-slice5-survey.md) holds what was read before
this design. The owner decided two things on 2026-09-28:

- **The start route's evidence.** The start route is qualified by the host's `new_delivery` probe,
  not by `read` over MCP. The seven entrance cases' probe steps are restated to match
  (`D-20260928-09cd4b`).
- **One re-freeze.** P01 is re-frozen once, at the end of this slice (`D-20260928-d6ff3a`). Until
  then the case specs this slice restates are drafts, and the slice is measured against them.

## One grammar, three layers

S11 asks for one information grammar across the host launcher, setup and the Studio hub. It
must not create "another store or business-rule engine". So the slice has three layers, and only
the first writes kept state:

1. **Owner operations**, which know no screen:
   - `route.offer` and `route.select` (`workenv/cli.py`, which `serving.json` names);
   - `operation.history.read` (`workenv/journal.py`).
2. **The entry model** (`workenv/tui.py`).
   - It is a function from what the owner holds, an offer and one input, to the next frame of a
     `surface_trace`. Each element carries its role, label, marks, focus, selection and state.
     The frame also records the view, what the input called and what it dispatched.
   - It reads the owner only through the owner's read operations, and records each call.
   - It never submits a write itself. A start hands the request it built to a dispatcher it was
     given.
   - `surface.drive` runs a whole `surface_script` through the model with a dispatcher that only
     records. That is why it is a pure preview.
3. **The terminal.** `agent-bios start <host>` draws the model's current frame in the terminal and
   reads keys. On the start action it submits the dispatched request through the journal, records
   the selection, and launches the host through `workenv.hosts.start`.

   The same entry is reached from:
   - `bash install.sh start <host>`;
   - the host launcher (`launch/agent-launch.py`), whose `Launch? [Y/n/q]` question is removed for
     this route (`D-20260926-8ee6bb`).

   What the conformance driver checks is the second layer. What a person uses is the third, which
   draws exactly the frames the second computes.

## Owner operations

- **`route.offer`** stores the routes an entrance offers, with `offered_at`. A route whose support
  says `qualified: yes` must name a `capability_probe` held here. That probe must qualify the
  capability the route's action needs, on the probe's host and version: the latest real probe
  worked, through the route's current wire (`workenv.hosts.qualified`). Otherwise the offer is
  refused `capability_not_qualified`. A route whose support says `no` is stored as stated: it
  widens nothing.
- **What an action needs.**
  - `use` (starting work in an environment) needs `new_delivery`.
  - `decide` needs `question`, which V1 does not serve.
  - The table lives in `workenv/cli.py`. Later stages extend it with the capabilities they
    qualify.
- **`route.select`** records one selection against a held offer:
  - The offer must be held (`ref_unavailable`), and the selected route must be one it offered
    (`request_mismatch`).
  - An unqualified route is refused `capability_not_qualified`. It returns a `route_outcome` of
    `got: unsupported`, `because: capability_absent`, for the capability the action needs. It is
    never run.
  - A qualified route answers for the request the selection names, which the journal must hold.
    The outcome carries the probe's capability and client, and a result derived from that
    request's held answer: `result` with its first output's digest, `unknown`, and so on.
- **`operation.history.read`** answers one scope's recent requests and dated checkpoints, as C03
  states. It needs the journal to keep what it drops today: a request's `rationale`, which is a
  checkpoint's note. It also needs a rule for which requests belong to a scope, which C03 does not
  state. The rule is settled in increment 1 against the two cases that read history (REPO-NO-ENV
  and UNKNOWN), written down with its reason, and cased.

## The entry model

The model computes these views:

- **W01**: the observed context, then the nine positions, then the execution choices, then the
  start action.
  - The observed context is location, branch and commit, and the last checkpoint with its note.
  - The nine positions are repository, personal and Team × Instructions, knowledge and memory.
    Each shows what the owner holds: selected, installed, checked empty, or not checked.
  - The execution choices are the tool and the new session. They are separate from the
    environment choice, and changing one never changes the other.
  - The start action carries its effects.
- **W02**: the detail of one position, with Esc returning to W01.
- **The hub**: the Studio entrance's job list.

S11's rules, each a check in the entry's unit tests:

- There is no goal or task field.
- Focus, a suggested default and a selection are three facts.
- Enter follows the focused control's verb, and there is no hidden global start key.
- One Enter on the start action dispatches exactly one owner request, with no preview or
  confirmation in between.
- A blocker says why and how to fix it.
- An unknown result offers "check this request".
- 80×24 clips an over-wide line rather than shrinking Korean.
- `ko`, `en` and `ja` come from one catalog. Labels never carry authoring criteria.

**Labels come only from records the owner holds.** Where a frozen case states a label no record
holds (see the survey), the case is restated. The model is not taught the label.

## The unconfirmed start (`event_reply_lost`)

In V1's start, the link's activation is made by the hook when the host reports its session. A
host that never reports (it failed to start, or Codex was not trusted to run the hook) leaves a
start with no answer. The journal already holds an `unknown` request as pending, and settles it
when the same request is asked again under its id.

This slice designs who asks first and who asks again. The entry then shows the pending start as
unknown, with "check this request", as TUI-ENTRY-UNKNOWN states. It is designed in increment 4,
when the terminal launches a host, against what that code has to live with
(`D-20260926-421d82`).

## Increments

Each increment ends with a mutation sweep and a commit through the hook. The case drafts it needs
are written in the same increment.

1. **Owner operations.**
   - `route.offer`, `route.select`, the action table, `operation.history.read`, and the journal
     keeping `rationale`.
   - Drafts of the probe steps (`new_delivery` in place of `read`) in the seven entrance cases,
     and TUI-ENTRY-UNKNOWN's frontier.
2. **The entry model and `surface.drive`.**
   - W01, W02, the hub, the key grammar and the catalog.
   - Drafts of the trace values no record holds.
3. **The terminal.**
   - `agent-bios start <host>` and the other commands of `D-20260926-8ee6bb` (`profile`,
     `sources`, `prepare <host>`, `received`), with first use making the local profile.
   - The `install.sh` arm, the launcher route, entrance rows and `package.json`.
4. **The unconfirmed start**, and `event_reply_lost` in the driver.

The slice then ends with:

- a real use of the entrance on both hosts, and its dated direct-use record;
- the P01 re-freeze carrying every draft;
- V1's acceptance.

## Not in this slice

- MCP and `read` (V2).
- The deferred presentation cases TUI-ENTRY-80X24 and TUI-ENTRY-STATE (trim of 2026-09-22).
- Questions, resumes and decision use (V2).
- Team routes beyond what N16-ENTRANCES-POS offers (V5).
