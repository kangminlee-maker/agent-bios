---
created_at: 2026-10-01T23:25:44+09:00
head: e8b281b
kind: design
supersedes: null
plan: 2026-09-30T0604--b702da9--development-plan.json
decisions: D-20261001-4c38cf
---

# V1 acceptance: each host's routes probed again, and one session on each through a change and a compaction, after the restructure (record)

This is a dated direct-use record for V1's done-when [0] and [6]. It records real use run by the
agent on 2026-10-01 between 23:13 and 23:25 KST, on this machine, through the code at
`e8b281b`. That commit is the restructure in the
[23:09 record](2026-10-01T2309--3551ccb--v1-restructure-record.md). The commit that carries this
record changes one docstring in `workenv/hosts/start.py` and nothing else under `workenv/`.

The setup is that of the
[16:39 record](2026-10-01T1639--19c383e--v1-acceptance-after-review8-direct-use-record.md):
Claude Code 2.1.286, Codex CLI 0.159.2 (`gpt-6.1-sol`), tmux, the main checkout and the state
base `v1-accept/use/base`. Evidence is in the workbench's `v1-accept/use/`, files `150` …
`175`, with the scripts `readmit.py`, `probe.py`, `midsession.py` and `check_last.py`.

V1 is not accepted by this record. It stands beside the cases, never in place of one.

## What was run and what was seen

1. **`AGENTS.md` admitted again** (`150`). The checkout's document read `d16c076c…`, other
   than the body admitted, so a start would have been refused `working_bytes_moved`. It was
   admitted as revision `a1e1bc15…`.
2. **Every route a session uses, probed again on both hosts** (`151` … `156`).
   - The probes before this were made by code that counted an unconfirmed turn or compaction.
   - With `e8b281b`, `rehydrated`, `new` and `current` each `worked` on Claude Code and on Codex.
   - Claude Code's `/compact` was followed by `compact_boundary`. Codex reported the compaction
     and completed its turn.
3. **Claude Code, in the main checkout** (`157` … `165`).
   - **The entry.** It showed the Codex start of 16:38 as the previous note, and both
     Instructions.
   - **The new session.** It gave `AGENTS.md` `d16c076c…`, then `korean-writing.md`
     `74d227ef…`, and named `src_832de866…` as not usable.
   - **The owner's record.** The activation and the `new` delivery were recorded at 14:18:27Z.
     The digest and render checks hold, and the text holds no `unt_`.
   - **A change during the session** (`160`). `midsession.py` committed a personal revision
     `24d7d6af…`, pinned it in the person's collection, and composed the start's request for
     the session's link.
   - **The next prompt** (`161`). The hook handed the one-line notice that the change is larger
     than the hook carries and a new session receives it, and recorded nothing. The latest
     preparation carries `AGENTS.md` (43,202 bytes) and the personal body, and the hook carries
     10,000 characters.
   - **`/compact`, then the same question** (`162`, `163`). The session gave the two bodies it
     started with. A `rehydrated` delivery of the activated preparation was recorded (`164`,
     `175`).
   - `/exit` ended the session, and `start` exited 0.
4. **Codex, in the main checkout** (`166` … `174`).
   - **The entry.** It showed the Claude start's note as the previous note.
   - **The new session.** On `GPT-6.1-Sol low`, it gave `AGENTS.md` `d16c076c…`, then
     `korean-writing.md` `24d7d6af…`, the body changed during the Claude session, and named the
     same unusable source. The activation and the `new` delivery were recorded at 14:23:40Z, and
     the checks hold.
   - **A change during the session.** `midsession.py` committed `231ac7c5…`. The next prompt
     received the same notice; Codex's hook carries 2,500 bytes, and nothing was recorded.
   - **`/compact`.** Codex reported "Context compacted". The same question gave the two bodies
     it started with, and a `rehydrated` delivery was recorded (`173`, `175`).
   - `/exit` ended it, and `start` exited 0.

## What this shows against V1's done-when

At `e8b281b`:

- **[0]:** on each host, a session in this repository with repository then personal
  Instructions, and a record of what it received.
- **[6]:** a `new` delivery and a `rehydrated` one on each host. Each names the preparation
  whose text the session holds, and each route was probed by code that counts only what its
  host confirmed.
  - A `current` delivery reached each session as a notice and was recorded as nothing, as the
    hook states for bodies larger than it carries.

## What this run did not exercise

- **A `current` delivery that prints its bodies.** The hook hands all of a preparation's
  bodies, and this repository's `AGENTS.md` alone is more than either host's hook carries.
  `test_start` holds the printed path, and the `current` probes show each host's hook reaches
  the session.
- **The cases the path tests hold.** A needed unit switched off, omitted or shadowed, a needed
  member of another role, and two carried units of equal bytes are not in either base.
  `test_paths` holds them.
- **No change to V1's contracts or cases.** The personal revisions committed here change the
  real-use base only.
