---
created_at: 2026-11-11T03:45:00+09:00
head: 0390fb3          # the commit the content was true at
kind: design
supersedes: 2026-11-11T0300--e84740c--a-codex-pin-can-name-its-rollout-and-the-two-unjoinable-pins-are-told-apart.md
---

# A Codex activation names the rollout the host wrote, and F-22 closes for the pins written from here on

F-22's entry is deleted with this change. What is established, and what is not, is below; nothing
here is a claim about the owner's existing pins.

## Established, measured 2026-11-11 with the installed Codex

Under a **temporary** `CODEX_HOME`, inside the real `thread/start` that
`RealCodexTests.test_real_host_session_id_is_persisted_and_readable` runs on every umbrella pass:

- `thread.path` is set, the file exists, and it **is** the rollout
  (`rollout-<date>T<time>-<uuid>.jsonl`) once compared by realpath — an unresolved string compares
  unequal through the `/private` symlink, which is what made the first reading say otherwise.
- The rollout's file name carries the thread id, and so does its first record's `session_meta.id`.
  **A new activation's thread id is the rollout's own id**, so the two id spaces coincide today.
- The host's thread index (`state_<n>.sqlite`, table `threads`) holds a row for that id whose
  `rollout_path` names the same file.

So a pin written from here on joins by the fields it now carries, and the end-to-end assertion that
it does runs with the suite rather than being remembered.

## How the activation resolves it (D-20261111-034508)

1. `thread.path` when it matches the rollout name shape and exists, compared by realpath:
   `rollout_path` is that path and `rollout_id` the last uuid in its **name**. No file is read — an
   activation that read the rollout would be reading the host's transcript to write its own pin.
2. Else the host's index row for the thread id with an existing `rollout_path`, read from a **copy**:
   a read-only sqlite open of a live WAL database moves the host's `-shm`, and this module writes
   nothing outside its own activation records and pins.
3. Else `rollout_unresolved`, naming both attempts on stderr.

The census keeps its own rule for a rollout's id (the first record's `session_meta.id`, else the
name), so a census id that differs from the pinned one — a fork, a rename — is a named reason in the
reader, never a silent miss here.

## Not established

The owner's 15 pins of 2026-10-23 carry no rollout fields and therefore read
`pin_predates_rollout_binding`. Whether the host's index maps them to rollouts is a count over the
owner's own index that needs the owner's approval; if it does, a one-time fill of those pins' rollout
fields from the index is a **follow-up**, not this change. A time-window or cwd match stays ruled
out at every step: a wrong join attributes one session's delivered bytes to another, which is worse
than unknown.
