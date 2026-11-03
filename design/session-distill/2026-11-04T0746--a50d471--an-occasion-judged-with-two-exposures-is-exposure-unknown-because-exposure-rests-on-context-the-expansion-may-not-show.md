---
created_at: 2026-11-04T07:46:00+09:00
head: a50d471
kind: review
supersedes: null
---

# An occasion judged with two exposures is exposure_unknown, because exposure rests on context the expansion may not show

Commit B2 of review W round 1. It follows commit B (`a50d471`), whose record is
`2026-11-04T0735--fc999c9--a-carried-event-is-the-unit-s-a-late-occasion-its-own-window-s-and-a-store-line-ends-only-at-a-newline.md`.
This record replaces the exposure part of that record's `stage_read.py:781` section. The rest of that record still
holds.

## stage_read.py:781: the exposure of an occasion judged twice

**The decision.** The lead answered the second design question after commit B had entered its hook.
- When a window and an expansion of one of its records judge one occasion with different verdicts, the verdict is the
  expansion's. This is unchanged: the verdict is about the entry, which the expansion read whole.
- When their exposures differ, the instance keeps `exposure_unknown`, and the resolution stays pending. Exposure rests
  on the context before the entry. The window saw its overlap, and an expansion may show less of it, so neither
  reading wins.
- This replaces the exposure part of D-20261104-d4dead, which took the expansion's exposure. It is recorded as
  D-20261104-a9e2d2.

**The change.** `settle_occasions` now works like this:
- The verdict is the expansion's.
- The exposure is the shared one, or `exposure_unknown` when the two differ. The model's exposure values are only
  `eligible` and `exposure_unknown`, so the outcome differs from the old rule only when the window judged
  `exposure_unknown` and the expansion `eligible`.
- The evidence is that of the readings that gave the verdict kept. When the verdicts agree and only the exposures
  differ, that is both readings.
- The file's read record names each superseded occasion under `occasions.superseded`, with what differed (`differs`),
  the window's judgement and the one kept. It counts the two kinds of difference apart: `verdict_differs` and
  `exposure_differs`.
- Expansions that judge an occasion otherwise among themselves still keep none of it. That occasion is named
  `conflicting`, and the unit is `read_partial`.

**The controls.** Four stage runs on the clipped record `late_clip`, each one condition apart. Each requires that both
readings judged the occasion.
- `W r1: an occasion its window and its expansion judge the same is one instance`.
- `W r1 B2: an occasion its expansion judges with another verdict keeps the expansion's verdict, the window's named
  superseded`.
- `W r1 B2: an occasion its window and its expansion judge with another exposure is exposure_unknown, named
  superseded`. Here the window judged `exposure_unknown` and the expansion `eligible`, so the old rule would keep
  `eligible`.
- `W r1 B2: an occasion judged with another verdict and another exposure keeps the expansion's verdict, is
  exposure_unknown, and names both`.

## The late evidence's basis, for its reader

An occasion on a backlog record is stored as late evidence of its own window, with basis `incomplete`
(D-20261104-6e324e). WP-21, not yet built, is to read that evidence. Every late instance it will find carries basis
`incomplete`, because the run that read it could not say whether that window's scope was complete. S3 sets no other
basis on late evidence.

## stop.py: what the owner does when the kill listing fails

`stop_recorded` has one path that leaves processes stopped and not killed. In that path the group was frozen, but the
listing taken just before the kill failed. With no start time to check against, it sends no signal. The stop is
`unverified`, and the resume is refused (RESUME_HOST_UNVERIFIED) with the pids named. The lead accepted this path for
commit A.

Its detail now ends with what the owner does: "they stay stopped until the owner checks each pid against the run's
host and ends it". No control compares this text.

## Evidence

The pretrial `wB2-pretrial` (development tool, not committed) ran in disposable committed copies, in a fake env, with
TMPDIR under `/tmp`. Each of its five rows puts back one rule and fails by its control's name:
- the occasions left unsettled (all four controls);
- the window's verdict kept over the expansion's (the verdict control and the both control);
- the expansion's exposure taken, which is D-20261104-d4dead's rule (the exposure control and the both control);
- the two kinds of difference counted together (the verdict control and the exposure control);
- the instances written before the resolutions are derived.

The unmutated stage_read suite (147 controls) and stop suite (51 controls) pass. Every TMPDIR ended empty.
