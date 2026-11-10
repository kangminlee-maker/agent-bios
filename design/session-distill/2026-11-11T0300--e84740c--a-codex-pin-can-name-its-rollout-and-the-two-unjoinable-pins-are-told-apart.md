---
created_at: 2026-11-11T03:00:00+09:00
head: e84740c          # the commit the content was true at
kind: design
supersedes: none
---

# F-22, everything but the realization: a Codex pin can name its rollout, and the two unjoinable pins are told apart

F-22 (`FINDINGS.md`): a Codex activation pins the app-server's thread id, and on 2026-10-23 none of
the owner's 15 pins joined any of 2,631 rollouts, so Codex selection and delivery could only ever be
reported unknown. Option 1 (record the rollout the host actually writes) is the owner's default,
unobjected. This lands what every source of the rollout id shares; the resolution itself ships as a
named seam.

## What a pin carries now

A Codex activation records `rollout_path`, `rollout_id` and `rollout_method` — **always**, null when
it resolved none, because the ABSENCE of the keys is the only signal that a pin predates this
binding. The evidence `method` ends with how they were obtained (`...+index`, `...+thread.path`) or
with `rollout_unresolved`. The recovery path records them too, or its pin would read as one written
before the binding existed.

A reader joins on the rollout: `sources.read_pins` keys a Codex pin by its rollout id as well as its
thread id, and `inventory.codex_pin_for_rollout` finds the pin that NAMES a row's rollout, so a
joined Codex row is read like a Claude row under that pin's own id. The two pins that cannot be
joined are told apart by name (D-20261111-1cf373): `pin_predates_rollout_binding` and
`rollout_unresolved`. A Codex pin that names its rollout now carries its snapshot as `current`'s
session_injection carrier, exactly as a Claude pin does (D-20261111-61cc2d); `id_space` stays for a
rollout no pin names and for a Codex session's overlays.

## What the host offers, measured 2026-11-11

Under a **temporary** `CODEX_HOME`, inside the real `thread/start` that
`RealCodexTests.test_real_host_session_id_is_persisted_and_readable` already runs on every umbrella
pass — no owner data, no extra cost:

| Question | Answer |
| --- | --- |
| Is `thread.path` set, and does the file exist? | yes, and it IS the rollout (`rollout-<date>T<time>-<uuid>.jsonl`) once resolved through the `/private` symlink |
| Does a rollout under that home carry the thread id? | yes — in its file name, and as its first record's `session_meta.id` |
| Does the host's thread index hold a row for the id with an existing `rollout_path`? | yes, naming that same file |

All three work for a **new** activation, and the second means the two id spaces coincide today: the
id `census.entry_of` takes from a rollout is the id the pin is named by. F-22's zero joins are about
the owner's existing pins, written by an earlier host version or route, and that is the one fact a
count over the owner's own index would settle. Until it does, `resolve_codex_rollout` returns None
(D-20261111-22d10b) and every pin it writes says `rollout_unresolved` rather than guessing.

## Not here

The realization, the F-22 entry's deletion, and the retroactive count over the owner's index. A
time-window or cwd match stays ruled out: a wrong join attributes one session's delivered bytes to
another, which is worse than unknown.
