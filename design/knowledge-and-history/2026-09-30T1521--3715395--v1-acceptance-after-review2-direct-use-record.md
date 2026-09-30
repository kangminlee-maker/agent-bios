---
created_at: 2026-09-30T15:21:02+09:00
head: 3715395
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20260930-5d1abb
---

# V1 acceptance: one start on each host after the second review's repair (record)

This is a dated direct-use record for V1's done-when [0]. It records a short real use run by the
agent on 2026-09-30 between 15:16 and 15:20 KST, on this machine, through the code at `3715395`.
That code is the repair described in the
[15:13 record](2026-09-30T1513--3851a9a--v1-review2-repair-record.md), and it is the last commit that
changes `workenv/`.

It repeats, on that code, what the
[12:52 record](2026-09-30T1252--6676966--v1-acceptance-both-hosts-direct-use-record.md) showed at
length. The setup is the same, and so is the state base. The base still holds the person's
Instructions collection with one source that does not resolve.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

Evidence is in the workbench's `v1-accept/use/`, `40` … `48`, with `check_last.py`.

1. **The Claude Code entry** (`41`):
   - the location;
   - both Instructions suggested and included, the person's line reading
     `개인 지침 · korean-writing.md · 쓸 수 없는 원본 src_832de866`;
   - the note, the tool, the permissions and the start.

   A note was typed, and Tab moved to the permissions and then the start.
2. **A Claude Code 2.1.285 session from the entry** (`42`).
   - Asked with no tool for every body sha256 its environment names, in order, it gave
     `242afd12…` then `74d227ef…`. It left out `memory-use.md`'s digest as not a body.
   - It said the environment names the personal collection's `src_832de866…` at revision
     `666666666666` as `selection_unresolved`.
   - `/exit` ended the session, and `start` exited 0.
3. **What reached it** (`43`, `44`).
   - The host session `3665a378f95a` was activated at 06:18:09Z with the two units, and its
     projection carries the gap.
   - The job's environment digest is the sha256 of the handed text.
   - The recorded preparation renders the handed text byte for byte, and the text holds no `unt_`.
4. **The Codex entry** (`45`). It is the same, with the tool `Codex CLI`. Tab moved from the note
   to the tool, the permissions and the start, since both hosts are qualified.
5. **A Codex CLI 0.159.2 session from the entry** (`46`).
   - It ran on `GPT-6.1-Sol low`.
   - It gave the same two digests in the same order.
   - It said the personal collection is `selection_unresolved`.
   - `/exit` ended it, and `start` exited 0.
6. **What reached it** (`47`, `48`).
   - The host session `8ed7b286d4d1` was activated at 06:19:54Z with the two units and the gap.
   - The job's environment digest matches the handed text.
   - The recorded preparation renders the handed text byte for byte, and the text holds no `unt_`.

## What this shows against V1's done-when

At `3715395`, on each host, as at `6676966`:

- **[0]:** a session started in this repository, with repository then personal Instructions in
  that order, and a record of what it received.
- **[6]:** a `new` delivery whose recorded preparation renders the text the session holds.
- **[10]:** the unresolved selection is visible on the entry and to the session.

## What this run did not exercise

- **An identical request overlapping another.** That needs two submissions of one request
  scheduled inside each other; it is shown by the unit test the repair added.
- **The entry's check asked a second time.** That needs a start whose outcome stays unknown, and
  none arose here; it is shown by the unit test the repair added.
