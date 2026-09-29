---
created_at: 2026-09-29T11:51:29+09:00
head: e2ae51c
kind: design
supersedes: null
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260929-6ac3d9, D-20260929-b2b72a
---

# V1, fifth slice, fourth increment (d): each body in a session's environment names its layer, role and member

This follows the [10:38 record](2026-09-29T1038--95ff465--v1-slice5-unavailable-positions-record.md).
The owner resumed the run by hand and checked what reached the session. V1 is not complete, and no
node is accepted by this work.

## What the owner's run showed

On 2026-09-29 at 11:43, in the owner's own terminal and state
(`…/team-env-20260920/v1-slice5-owner/base`), Claude Code 2.1.284 was started from the entry with
the repository's `AGENTS.md` and the person's `korean-writing.md`. Three checks all agreed:

1. **`received`.** The host session `6b1cfab9e5f2` was activated at 02:43:56Z with two units:
   bodies `242afd12bf63` and `74d227ef9051`.
2. **The digests.** Asked without tools for every body sha256 its agent-bios environment names,
   the session gave the two digests in full, in that order.
3. **The content.** Asked without tools for the `guide_id` and `description` of the personal
   Instructions, the session quoted them exactly. The host does not load that guide natively, so
   only the environment could have carried it.

The session added two things, and both were checked against the owner's state, read only:

- **The session's unit ids are not the recorded ones.** The session named `unt_9c739daa…`; the
  record names `unt_89c79d24…`. Both are for source `src_a592bb31…` and body `74d227ef…`.
  - The journal shows the start composing at 02:43:54 and handing that text at launch.
  - The hook then composed the same request again for the session's link, at 02:43:56, and
    recorded the delivery of that second preparation (`prp_b588…`).
  - The owner chose to queue this as FINDINGS F-20, to be fixed with the two activations per start
    (`D-20260929-b2b72a`).
- **The environment named neither the file nor that the guide was personal.** Each body was
  headed by its unit id, then a line naming its source and digest. The preparation carries the
  layer, the role and the member, but the text did not.
  - The model could not tell a repository standard from a personal preference.
  - The owner chose to name them (`D-20260929-6ac3d9`).

## What changed

- **`workenv/hosts/start.py` `bodies_text`.**
  - **The heading.** Each body is now headed by its layer, its role and the member it is (for
    example `## Repository instructions: AGENTS.md`, `## Personal instructions:
    korean-writing.md`). A unit that names no member is headed by its layer and role.
  - **The line below** names the unit, the source and the body sha256 (`Unit unt_…, source src_…,
    body sha256 ….`), then the body follows as before.
  - **Where it is used.** The same text is used at launch and by the hook's `current` notice.
- **`FINDINGS.md` F-20,** with three alternatives.
- **Tests (`test_start.py`, 34).**
  - A new test holds the exact text for two units: one with a member and one without.
  - The launch test now looks for the `Personal instructions` heading and the unit line.

## What did not change

- **The bodies and their order.**
- **The usage contract at the head of the text.**
- **What the hook compares** before it records a delivery: the body digests, not the text.
- **The probe:** it hands its own code, not this text.
- **Unit ids** still name a unit in one preparation only (C07).

## How it was checked

- **The workenv gate** (`gates/workenv/check-workenv.py`, every unit leg and ruff): OK.
- **The V1 cases (`runv1-inc4d.txt`):** 19 passed and 3 failed, the same three as before. No
  case states the launch text.
- **Mutation sweep (`mutate5h.py`):** 4 of 4 caught.
  - a body headed by its unit id again;
  - the layer not named;
  - the member not named;
  - the unit line dropped.
- **The real text (`show5h.py`, `show5h.txt`),** rendered by the checkout's code from a copy of
  the real-use state, started through Enter on a detail with the host not run. The two headings
  read `## Repository instructions: AGENTS.md` and `## Personal instructions:
  korean-writing.md`, each followed by its unit line.

## Open

- **F-20,** as above.
- **Headings at the same level.** The unit headings are `##`, the same level as headings inside
  a body such as `AGENTS.md`. In both real runs, the model told the units apart. Whether a
  delimiter a body cannot contain is needed is left to the P01 re-freeze's review of the launch
  text.
- **The earlier open items remain,** as listed in the 10:38 record.
