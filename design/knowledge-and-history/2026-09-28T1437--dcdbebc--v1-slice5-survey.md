---
created_at: 2026-09-28T14:37:18+09:00
head: dcdbebc
kind: review
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
---

# V1, fifth slice: what the entrances need, and what the frozen cases ask that V1 cannot honestly do

The fifth slice is V1's entrances:

- `workenv/cli.py`, serving `route.offer` and `route.select`;
- `workenv/tui.py`, serving `surface.drive`;
- `operation.history.read`;
- `capability.probe` for `read`;
- the commands of `D-20260926-8ee6bb` (`profile`, `sources`, `prepare <host>`, `start <host>`, `received`), with the host launcher and setup routing into them.

This record is what was read before designing it, on 2026-09-28. Two read-only surveys read the
frozen cases, the driver, the contracts, the SSOT's S10–S11, the development specification's TUI
slice, and the entry code that exists today. Their claims were checked against the artifacts
where a decision rests on them. It decides nothing; the owner's decisions follow it.

## The seven V1 cases the slice serves

The cases are N16-ENTRANCES-POS, TUI-ENTRY-ACCOUNT-FREE, -FOCUS, -KO-STATE, -OPTIONS, -REPO-NO-ENV
and -UNKNOWN.

- Today five of them stop at their `capability.probe` of `read`, one at `operation.history.read`,
  and one at the driver's missing `event_reply_lost` feature.
- Right after each stop, every case needs `route.offer`, `route.select` and `surface.drive`, whose
  modules do not exist.
- In a look-ahead, the driver gave those steps their stated answers. The existing code then passed
  six of the seven. TUI-ENTRY-UNKNOWN failed on its composition (below).

## What the cases state that V1 cannot honestly produce

1. **`read` is probed over MCP, which V1 does not have.**
   - Every case qualifies its start route with a probe of `read` over `model_context_protocol`
     `2025-11-25`.
   - agent-bios has no MCP server. The development specification gives the stdio MCP entrances to
     V2: "V2 exposes inspect, prepare-use and answer/resume semantics through one local owner;
     typed CLI/API and selected stdio MCP entrances share the same durable questions".
   - V1 delivers through launch instructions, qualified today by real `new_delivery` probes on both
     hosts ([14:04 record](2026-09-28T1404--b04af19--v1-slice4-launch-delivery-record.md)).
   - The cases also probe clients this machine does not have: `claude-code 2.1.278`, where 2.1.283
     is installed, and `agent-bios 0.20.0`.
   - Their observed text differs by client. So does whether a `capability_profile` is returned:
     N16 returns one, the TUI cases do not. No rule is stated for either.
   - The frozen contracts already allow `new_delivery` as a route outcome's capability and as a
     probe's (`c12_route_outcome`, `c12_capability_probe`).
2. **Trace values no record holds.**
   - A dispatching frame names the digest and id of the next step's request. Those are fixed
     scenario ids that neither the key script nor the drive request carries.
   - Labels come from nowhere in the records:
     - "payments", where the binding's remote is `…/work.git`;
     - "alice", where no record holds a person's name;
     - a checkpoint's date "(2026-09-19)", in a case with no clock;
     - a commit "0123456", which the checkout feature replaces with the real HEAD everywhere but in
       labels;
     - KO-STATE's 156-character location string.
3. **TUI-ENTRY-UNKNOWN's composition.**
   - It states a frontier for an Instructions pin.
   - The composition rule records frontiers only for memory (C07), and FOCUS, KO-STATE and OPTIONS
     state none for the same shape.
4. **`operation.history.read` needs what the journal does not keep.**
   - History answers a scope's recent requests (last confirmed stage, when, coverage) and dated
     checkpoints carrying the note recorded then.
   - The journal keeps no request's `rationale`, which the checkpoints' notes are.
   - C03 does not say which requests belong to a scope.

## What the slice has to design, which no frozen artifact fixes

- **An unconfirmed start (`event_reply_lost`).** `D-20260926-421d82` deferred it until the code that
  launches a host existed; it exists now.
  - In V1's start, the link's activation is made by the hook when the host reports its session. A
    host that never reports leaves a start with no answer.
  - The journal already holds an `unknown` request as pending, and settles it when the same request
    is asked again under its id. The slice has to decide who asks first and who asks again.
- **The entry grammar.** S11 fixes the grammar:
  - one start action that validates and dispatches, with no mandatory preview;
  - work environment separate from the tool and execution choice;
  - focus separate from selection and from observed use;
  - no goal field;
  - 80×24 without shrinking Korean;
  - `ko` / `en` / `ja`.

  Today's host launcher asks `Launch? [Y/n/q]` before every start, which S11 and
  `D-20260926-8ee6bb` remove. The launcher and setup also choose the locale by different rules.
- **Where the entrances join.** `D-20260926-8ee6bb` fixes the command surface.
  - The integrator patches `install.sh`, `launch/agent-launch.py`, `launch/i18n/`, `package.json`
    and the entrance inventory.
  - Today's shell connection (`launch/agent-launch.zsh`) starts Claude Code with
    `--dangerously-skip-permissions` unless a private connection exists. That is existing launcher
    behaviour a V1 start would inherit if it reused that path.

## Evidence

The surveys' scratch scripts (a step lister and a look-ahead run of the driver in temporary
directories) are in the session's scratchpad. The findings above cite the artifacts they came
from:

- the case specs under `gates/workenv/fixtures/scenarios/`;
- `gates/workenv/conformance/serving.json`;
- `workenv/contracts/c03.py` and `c12.py`, and their schemas;
- `workenv/preparation.py`;
- `storage.py`'s `requests` table;
- the development specification (§ "Consumption route and host qualification", § "TUI entry
  implementation slice");
- the SSOT's S10–S11;
- `D-20260926-8ee6bb`, `D-20260926-421d82`, `D-20260928-30d875`.
