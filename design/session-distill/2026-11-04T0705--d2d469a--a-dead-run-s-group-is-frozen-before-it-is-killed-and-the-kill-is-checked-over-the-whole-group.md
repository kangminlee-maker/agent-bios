---
created_at: 2026-11-04T07:05:00+09:00
head: d2d469a
kind: review
supersedes: null
---

# A dead run's group is frozen before it is killed, and the kill is checked over the whole group

Review W round 1 (on `487dd16`, range `637a6a1..487dd16`) returned rework: six major findings and two minor. This is
commit A, the two findings in `runlib/stop.py`, which the lead put first because the self-test one is a safety defect
in a suite every hook has run since `3da448e`. It also adds a leg the lead asked for. Commit B takes the other six.

## W r1 major, stop.py:828: the self-test's cleanup could signal a group the suite did not start

**The finding.** The commit 5a block reaped `run_a` after stopping it, and its last line then called
`cleanup(group(run_a.pid))`. `group()` lists whatever now leads the group with that id, with its current start time.
If the pid was recycled by an unrelated group leader, cleanup would SIGKILL that group.

**The change.**
- While all three fixture runners are still unreaped children of this suite, their groups are listed once and kept as
  `owned`. Each group id is provably theirs then.
- Cleanup goes through `release(procs, members)`. It signals only those recorded identities, each only while a fresh
  listing shows it with its recorded start time, then reaps the runners.
- No group is looked up again by a pid the suite has reaped.

The other cleanups in the suite were checked as well. Each collects its members before the reap.

**The control.** `W r1: cleanup after the reap signals nothing of a group a recycled pid now leads`.
- A mocked listing shows the reaped `run_a` pid as the leader of an unrelated group with another member. `os.kill` is
  mocked too, so no real signal is sent.
- The control requires `release` to signal nothing.
- With the old body put back (`cleanup(group(proc.pid))` per runner), the mocked group is signalled and the control
  fails by name.

## W r1 major, stop.py:336: stop_recorded verified only its first snapshot

**The finding.**
- `stop_recorded` killed the group members its first listing showed, and verified only those.
- A child forked between that listing and the kill was never signalled or checked.
- A leader that was not listed returned `gone` at once, even when its group still held processes.
- In both cases `Supervisor.interrupted` would resume beside processes that may still be spending.

**The change.** The group is frozen first, as `stop_tree` freezes a tree:
- Every member a listing shows in the recorded group is SIGSTOPped.
- The group is listed again until one listing shows every member stopped and none new, and still shows the leader as
  recorded. A stopped process cannot fork, so a member forked after the first listing is found by the next one.
  - A member joins the set only from a listing that shows the leader. While the leader lives, its pid, and so the
    group id, cannot go to another program.
- Then every member is SIGKILLed, each only while its start time is the one listed.
- The kill is verified over the whole group a fresh listing shows, as well as over every member found. A process the
  group still holds is a survivor even if no listing found it before.
- When the leader is not listed but its group still holds processes, the group cannot be shown to be the runner's
  (the id is free once the leader is gone and the group empties). Nothing is signalled, and the outcome is
  `unverified`, which `Supervisor.interrupted` turns into RESUME_HOST_UNVERIFIED.
- A leader not listed with its group empty is still `gone`.
- The pid-reuse path (`identity_mismatch`: the pid listed with another start time, group or leader) is unchanged and
  still closes the reservation interrupted and lets the resume go on, as the lead decided for commit 5a.
- The leaderless group is a fourth case of RESUME_HOST_UNVERIFIED beside D-20261104-efa3ec's three; it is recorded
  as D-20261104-7b4028.

**The controls.** Four, each over a deterministic mocked process table: SIGSTOP stops a listed process, SIGKILL
removes it, and the mocked `os.kill` sends no real signal.
- `W r1: stop_recorded freezes the group and kills a member forked after its first listing`. The member appears in
  the second listing. Without the freeze it is never signalled.
- `W r1: stop_recorded verifies the whole group, so a process it holds after the kill is a survivor`. A process joins
  the group in the first listing after the kill. Verified over the members found only, the stop reads `stopped`.
- `W r1: a group still holding processes after its leader is gone is unverified and nothing is signalled`. It reads
  `gone` before this change.
- `W r1: a leader gone with its group empty is gone, and nothing is signalled`. This is the positive counterpart.

The real-process controls of commit 5a are unchanged and still pass: the stop of the recorded runner with its group,
the four identity mismatches, and the identity recorded in part.

## The evidence helper's self-test is a leg

`gates/check-parity.sh` now runs `wrappers/claude_hermetic_evidence.py --self-test`, beside the Codex capture helper's
leg. The helper ships, REPIN.md step 7 says the parity gate runs its self-test, and no leg did. It passed on the tree
before the leg was added (81 controls).

## Evidence

The pretrial `wA-pretrial` (development tool, not committed) ran in disposable committed copies, in a fake env, with
TMPDIR under `/tmp`.

Every row puts one rule back and fails its suite by that rule's control name:
- the cleanup that looks a group up again by a reaped pid;
- no freeze;
- the kill verified over the members found only;
- the leaderless group read as gone;
- the parent commit's `stop_recorded` whole. This is the reproduction; it fails the three new controls.

The unmutated stop, dispatch, stage_read and evidence-helper suites pass. Every TMPDIR ended empty.

The supplement to the 5b record that the lead asked for is in this branch's previous record,
`2026-11-04T0650--487dd16--every-self-test-reads-the-pinned-claude-host-and-s3-seat-so-a-re-pin-edits-four-places.md`.
