---
created_at: 2026-09-30T09:42:02+09:00
head: 6265ff4
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-76d550, D-20260930-1dfd67, D-20260930-6c708c
---

# V1 acceptance: direct use of the repaired start, and three things the person is not shown (record)

This is a dated direct-use record for V1's done-when [0]. It records the real use run by the agent
on 2026-09-30 between 09:29 and 09:41 KST, on this machine, through the code at `6265ff4`: the
repair the [09:23 record](2026-09-30T0923--c39e727--v1-review-repair-record.md) describes.

It checks the repair's two claims in real use:

- the delivery recorded is of the text the session holds (F-20, `D-20260930-6c708c`);
- a start whose selected source does not resolve still starts, and the session is told
  (`D-20260930-76d550`).

Both hold. The run also found three places where the **person** is not shown what the session or
the host knows. They are listed under "What was found" and are not yet dispositioned.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## Where and with what

- **Hosts:** Claude Code 2.1.285 and Codex CLI 0.158.0 (`/opt/homebrew/bin/codex`), with the
  person's own settings and accounts.
- **The repository:** the main checkout `~/Documents/agent-bios-personal`. Nothing was written
  there.
- **The state:** a new base, `…/agent-bios-workbench/team-env-20260920/v1-accept/use/base`, named
  by `AGENT_BIOS_STATE_DIR`. The person's `~/.local/share/agent-bios` was not touched.
- **The program:** `workenv/commands.py` from the worktree at `6265ff4`, run by
  `/opt/homebrew/opt/python@3.14/bin/python3.14`.
- **The terminal:** each `start` ran inside tmux (a private socket, `LANG=ko_KR.UTF-8`), driven by
  keys sent to it and read back from the rendered screen.
- **Evidence:** the workbench's `v1-accept/use/`, numbered `00-source.txt` …
  `15-codex-default-model.txt`, with `prep.py`, `gap.py` and `run-start.sh`.

## What was run and what was seen

1. **The profile at first use** (`01`): profile `prf_49f9…f2f3`, principal `prn_a044…b1b1`,
   access `active (first_use)`, generation 1. No signup and no Team.
2. **The binding and sources** (`prep.py`, `02`), as the actor first use made, through the
   journal. Each was `committed`, and no collection was written.
   - `repository.bind` of the main checkout;
   - the checkout's `AGENTS.md` as the repository's Instructions, body `242afd12…`;
   - `claude/guides/korean-writing.md` as the person's own Instructions, body `74d227ef…`.
3. **The sources and their order** (`03`): repository Instructions `installed` (`AGENTS.md`), then
   personal Instructions `installed` (`korean-writing.md`); knowledge and memory none.
4. **Preparing on Claude Code** (`04`): the probe reported `worked`. The preparation composed in
   the order `repository, personal` with two layered units.
5. **Preparing on Codex** (`05`, `05b`), twice: `no_response`, "The host gave no reply to the
   probe …". Nothing was started with Codex. See finding 3.
6. **A Claude Code session from the entry** (`06`).
   - Asked, with no tool, for every heading of its agent-bios work environment and the line under
     each, it gave the environment heading, `## Repository instructions: AGENTS.md` and
     `## Personal instructions: korean-writing.md`.
     - Under each body heading: `Source src_…, body sha256 ….`, with the two digests.
   - Asked whether any `unt_` id appears, it answered no.
7. **What reached it** (`07`): the host session `de014fb4aa31`, activated at 00:31:21Z, with the
   two units, the repository's first.
8. **The F-20 repair against the state** (`08`).
   - The job's environment digest is the sha256 of the handed `environment.md`.
   - The delivery recorded names preparation `prp_9fed…`, whose unit ids differ from the start's
     own preparation `prp_1ead…`. Rendered by `start.environment`, it is the handed text byte for
     byte.
   - The handed text holds no `unt_`.
   - The link's destination is this session's id.
9. **A selection that does not resolve** (`gap.py`, `09`). `collection.change` (committed) wrote
   the person's Instructions collection `col_d550…7b85` with two entries switched on:
   - `korean-writing.md`'s source at its accepted revision;
   - source `src_832d…7574` at revision `666…6`, which this installation does not hold.
10. **The sources after it** (`10`): `personal instructions (collection col_d550…): installed`,
    listing `src_108d… revision 7561de27ed4d: korean-writing.md` and
    `src_832d… revision 666666666666`, with no name and no state. See finding 1.
11. **Preparing with it** (`11`): the two units as before, and
    `gap selection_unresolved at /collections/0`.
12. **A Claude Code session from the entry, with it** (`12`).
    - **The entry** showed `[x] 개인 지침 · korean-writing.md`. Nothing on it named the source that
      does not resolve. See finding 1.
    - **The session**, asked with no tool whether its environment says anything is missing, quoted
      the section exactly:

      ```
      ## Missing from this environment

      This environment was asked to hold something it does not:

      - The personal instructions collection: `selection_unresolved`, a selected source that is
        unknown, denied or damaged; this is not absence, and no lower layer silently satisfies it.
      ```

    - It named the bodies it received, `AGENTS.md` (`242afd12…`) and `korean-writing.md`
      (`74d227ef…`).
    - It added two remarks:
      - `memory-use.md` is named by path and sha256, with no body;
      - it could not tell from its environment how the personal collection is unresolved while
        `korean-writing.md`'s body arrived. See finding 2.
    - `/exit` ended the session, and `start` exited 0.
13. **What reached it** (`13`): the host session `ae74fe32c666`, activated at 00:34:08Z, with the
    two units.
14. **The gap against the state** (`14`).
    - The activation's one projection carries the two units and
      `[{"code": "selection_unresolved", "pointer": "/collections/0"}]`.
    - The recorded preparation renders the handed environment byte for byte.
15. **Codex under the person's own settings** (`15`).
    - `codex exec "Reply OK."` ran the session hooks and then failed with exit 1:
      `{"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The
      'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account."}}`.
    - The person's `~/.codex/config.toml` sets `model = "gpt-6.1-sol"`. It was changed at 06:19
      today, not by this run, and this run did not change it.

## What this shows against V1's done-when

**Shown here, on this machine:**

- **[0]:** a Claude Code session in this repository with the profile made at first use,
  repository then personal Instructions in that order, and a record of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders exactly the text the session holds.
  The F-20 repair holds in real use.
- **[10], for the session:** a selected source that does not resolve still starts, the activation
  carries the gap, and the session is told.

**Not shown here:**

- **Codex, on this machine now.** The person's own Codex setting is refused by Codex itself, so no
  Codex session was started. Done-when [0] asks for a Claude or Codex session; Codex was shown on
  2026-09-29 at `9f7b58c` ([09:36 record](2026-09-29T0936--9f7b58c--v1-slice5-direct-use-record.md)).
- **[10], for the person.** See findings 1 and 2.

## What was found

None of these is dispositioned by this record.

1. **The entry and `sources` hide a selected source that does not resolve.**
   - **Seen.** The entry shows `[x] 개인 지침 · korean-writing.md`, and `sources` states the
     collection `installed` and lists the missing source's id and revision with no name and no
     state (steps 10 and 12). The person learns of it only if the session mentions it.
   - **Why.** `tui.position_of` names only entries whose pinned revision the store holds, and
     states `installed` for any Instructions collection with an entry switched on. `sources` prints
     the same state.
   - **Against.** SSOT 0553: "Show owner/edition or unresolved status at the depth needed to
     choose", and "Empty, denied, unavailable, unsupported, unresolved and truncated remain
     distinguishable". Done-when [8] and [10].
2. **The missing section names the collection, not the source.**
   - **Seen.** The session could not reconcile "the personal instructions collection:
     `selection_unresolved`" with a body from that collection arriving (step 12).
   - **Why.** The composition's gap points at `/collections/0`, and `start.gaps_text` renders
     where the pointer is, not which entry of it does not resolve.
   - **Against.** SSOT 0553: "Keep winning, shadowed, disabled and unresolved references
     attributable."
3. **Preparing on Codex hides why Codex gave no reply.**
   - **Seen.** `prepare codex` reports `no_response` (step 5). Codex's own reason is a 400 refusing
     the model the person configured (step 15), and nothing agent-bios shows says so.
   - **Why.** `codex.Server.turn` keeps the agent's messages only. A turn that ends in an error
     ends with none, so `probes.probed` reports `no_response` with no note.
   - **Against.** Done-when [0]: the person cannot tell what to change to start Codex.

## Seen, and not a finding

- **`memory-use.md` has no body in the environment.** By design: done-when [5] asks for a compact
  usage contract and a reachable guide, and the guide is named by path and digest.
- **Tab after a Korean note.** During step 12 the first two Tab presses after typing the note
  did not appear to move the focus. It was not reproduced:
  - on a copy of the state, focus moved at every Tab after a Korean note, from the note through
    the permissions and the start and back;
  - the key decoder returns one `tab` per Tab after multi-byte text, split or whole.

  The cause of the first observation is not established.
