---
created_at: 2026-11-04T08:21:00+09:00
head: 90b3c90
kind: review
supersedes: null
---

# A stop is concluded only from a complete listing, and a runner starts under a mark the resume reads

Review W round 2 (on `90b3c90`, range `487dd16..90b3c90`) returned rework: two major findings and one minor. It
found seven of round 1's eight findings fixed. The W set closed at its cap of two rounds. The lead verifies this fix
with the review's own reproductions (D-20261104-0ce364). This record states what each finding changed and which control
holds it.

## stop.py:380 (major): an incomplete listing certified a stop

**The finding.**
- `ps_table` counts the lines it cannot read in `Listing.unreadable`, but `stop_recorded` never read that count.
- The review mocked a live member of the runner's group hidden behind one unreadable line:
  - With the leader listed, only the leader was stopped and killed, and the stop read `stopped`.
  - With the leader gone, nothing was signalled and the stop read `gone`.
- `Supervisor.interrupted` resumes on both outcomes. `stop_tree` already treats unreadable lines as incomplete
  evidence.

**The change.** None of the three conclusions is drawn from a listing with an unreadable line: the group gone, the
freeze stable, the kill done. This is D-20261104-0b4fda.
- First listing: when the leader is not in it and a line could not be read, the listing is taken again until one is
  complete, within `freeze_wait_s`. If none is complete in time, the stop is `unverified` and nothing is signalled.
- Freeze: it is stable only when a complete listing shows every member stopped and none new. Otherwise it goes on
  listing until its deadline, and then the members found are killed, as before.
- Kill: only a complete listing verifies it. With none before `settle_s`, the stop is `unverified` and the detail
  counts the incomplete listings.

**The controls.** Four, over the mocked process table. Its `hidden` pids appear only as unreadable lines, and its
mocked `os.kill` sends no real signal.
- `W r2: a leader unlisted beside an unreadable line is unverified, never gone, and nothing is signalled`.
- `W r2: a first listing hiding the leader is taken again, and the complete one decides`.
- `W r2: a member an unreadable line hid from the first listings is frozen and killed once a complete listing shows
  it`.
- `W r2: a kill no complete listing verifies is unverified, not stopped`.

## dispatch.py:1916 (major): a driver dying between Popen and the identity write was read as no runner started

**The finding.**
- `Supervisor.call` starts the runner with `Popen` before it computes and writes `runner_identity`.
- A driver dying in that interval leaves `dispatched_at` set and no `runner` field.
- `interrupted` read that state as "died before its runner started", charged the reservation, and allowed the resume.
  In the review's fixture, the runner was still alive at that point.

**The change.** The lead's default startup protocol. This is D-20261104-88d36e.
- `call` writes `spawning` (the instant) into the reservation and the ledger just before the `Popen`, and the identity
  just after, as before.
- A `Popen` that raises `OSError` started nothing, so the mark is taken off again.
- `interrupted` reads a dispatched reservation with the mark and no identity as `unverified`. The resume is refused
  (RESUME_HOST_UNVERIFIED) before anything is closed.
  - The detail tells the owner to look for a process using the cell named in the call's `call.json` and end it.
- A dispatched reservation without the mark still closes as before: it died before its runner could start, and it is
  charged as before.

**The controls.** The driver's death is a planted exception that nothing in the dispatcher catches. It leaves the
ledger as a dead driver would. Each runner is the suite's own fixture child, held from its `Popen` and ended by closing
its stdin.
- `W r2: a driver dead right after it started its runner leaves the reservation spawning, and the resume refuses
  beside it`.
- `W r2: a driver dead with its runner's identity known and not yet written is refused the same way`.
- `W r2: among several open reservations the resume refuses on the spawning ones alone and closes none`. Beside the
  two spawning reservations there are three others:
  - one never dispatched;
  - one dispatched without the mark;
  - the one an earlier control left open.

  Two of these, the never-dispatched one and the one dispatched without the mark, close on their own as before. The
  existing S9 controls `interrupted-closes-a-reservation-never-dispatched-unspent` and
  `interrupted-charges-a-dispatched-call-its-reserved-amount-when-nothing-was-measured` hold that.
- `the crash controls' runners, this suite's own children, have all ended`.

**Left as it is.** A run directory whose resume is refused RESUME_HOST_UNVERIFIED stays refused: no command closes the
reservation. This holds for every `unverified` cause. This fix adds a cause and does not change that behaviour.

## records.py:635 (minor): the reason still claimed a supervisor lock

`declaration_state`'s reason in DECLARATION_READERS now names the lock each caller holds:
- run_stage's stage admission and dispatch's stop stamp (`_stop_run`) hold the declaration lock.
- `reserve` holds the supervisor's lock alone. So does the standing-stop check (`_blocked`) where `reserve` and a
  call's launch make it.
- These hold neither lock:
  - that check as a call first makes it, before the call takes the supervisor's lock;
  - the seat admission (`_admit_seat`), also before that lock;
  - the read-only budget query (`remaining`).
- A read without the declaration lock that lands mid-amendment is refused by name (DECLARATION_DRIFT).

## Evidence

`work/impl/wp08/w2fix/repro.py` (development tool, not committed) runs the review's two reproductions against the real
functions of a checkout's `session-distill`.
- On this tree before the fix:
  - stop read `stopped` (leader listed) and `gone` (leader absent), and the hidden member was left running.
  - After a crash right after `Popen` and after a crash before the identity write, `interrupted` returned with the
    runner alive.
- After the fix: both stops are `unverified`, and both resumes are refused with RESUME_HOST_UNVERIFIED. No runner is
  left.

The pretrial `w2fix-pretrial` (development tool, not committed) ran in disposable committed copies, in a fake env, with
TMPDIR under `/tmp`. Each of its six rows puts back one rule and fails by its control's name:
- the four stop rules;
- the missing spawning mark;
- the mark read as no runner started.

The unmutated stop (55 controls), dispatch (565), stage_read (147) and records suites pass. No fixture process was left.
