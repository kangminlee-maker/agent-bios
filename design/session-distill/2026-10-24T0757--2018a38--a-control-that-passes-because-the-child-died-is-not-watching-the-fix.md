---
created_at: 2026-10-24T07:57:00+09:00
head: 2018a38
kind: review
supersedes: 2026-10-24T0308--2018a38--a-guarantee-is-the-weakest-mechanism-under-it.md
---

# A control that passes because the child died is not watching the fix

Round 2 of the hermetic review returned eight findings; implementing them was straightforward. What
was not straightforward is what the implementation exposed: a self-test that runs itself, a bound
nobody had put on a child process, two diagnostic layers that say the same sentence, and a control
that had been green for a year because the thing it watched kept crashing.

This record carries that round's work forward. It amends two statements of the 0308 record and one
claim I made during the round itself; everything else in 0308 stands, including §1's account of the
observer, §2's misattribution correction, and §4's limits.

## 1. A suite that runs itself needs a depth bound of its own

Two controls in each entry point run that entry point's whole suite as a real process, because the
failure they observe — a scratch parent that cannot be written in, a `TMPDIR` inside a host home —
has to happen where the suite creates its fixtures. Nothing stopped the child from doing the same.
What had been stopping it was the very wiring those controls revert: with `dir=` gone, `tempfile`
resolved `TMPDIR` on its own, the child survived the failure it was supposed to die on, reached the
same two controls, and spawned its own child.

One revert case recursed 594 deep. Each level left a 67MB fixture tree, 591 of them survived the
kill because `SIGKILL` runs no cleanup, and the disk reached 100% with 819MB free. No verdict was
reached about anything, and the mutation was still on disk when the run was ended from outside.

The depth is now bound by a mark on the child's environment (`AGENT_BIOS_SELF_TEST_NESTED`,
`entry.nest`), and a marked run skips the sections that would run it again. The bound holds whatever
any protection does, which is the point: a protection under test cannot be what limits the blast
radius of testing it.

**The guard has no revert case, deliberately.** Reverting it IS the incident. What stands in place of
one is a structural control: every call in `session-distill/` that runs its own file as a
`--self-test` child is enumerated from the AST, the set must be exactly the four that exist, each
must stand inside the guard, and each must mark the child's environment. Its negative controls plant
three violations — a site outside the guard, a child whose environment is not marked, a site in a
file that had none — into a throwaway copy of the SOURCE TEXT, never on disk.

**Named residual:** outside the harness, in-run recursion is bounded only by the per-child time limit
of §2. A run started by hand with the guard removed would recurse until that limit on each level.

## 2. What the depth bound then exposed

With the recursion gone, the revert that caused it passed. The control it was supposed to fail read
"nothing was created in the location the judgement refused" — and `tempfile` REMOVES what it made on
the way out. The location was empty either way. What had been failing that control was the wreckage
of a child that died before it could clean up.

So emptiness is not evidence. A marked run now SAYS where it put its fixtures, through the floor
(`SELF_TEST_SCRATCH`, which reads as `<HOME>/.claude/tmp/...` when it is somewhere it should not
be), and the parent's control reads that. With the wiring in place the child never gets that far,
because the judged parent refuses first; without it, the control fails by its own name in 12
seconds.

The same wiring at the other entry point needed a different revert: `chosen_parent =
scratch_parent()` is its own statement there, so removing the `dir=` leaves the refusal standing and
reverts nothing. What has to go is the judgement.

## 3. A child process without a bound is a control that cannot fail

Every `subprocess.run` in both self-tests was unbounded. A child that hangs, or spawns a suite of
its own, never lets the run reach a verdict — and a run killed from outside leaves the mutation on
disk and produces no result at all, which is the opposite of what a self-test is for.

`entry.bounded(spawn, timeout, what)` takes a function that STARTS the process, rather than making
the call itself: the closure gate judges a dispatch where it is written, so moving the call into the
shared module would move every self-test's dispatch there and strip it of the admission its own site
carries. The child starts in a session of its own, and a timeout ends that GROUP — `subprocess`'s
own timeout ends one process and leaves its descendants running, which is what kept filling the
disk. Only a child that leads its own group is ever signalled; that check is what keeps the call from
signalling this process's group.

A timeout is the reading control's own named failure, not a missing result.

## 4. Two layers that say the same sentence need two controls

`main`'s own handler and the `entry.guarded` around `__main__` both print a `COMMAND_FAILED` line.
A control that reads a real process cannot tell which layer caught the failure, so moving the
self-test back outside `main`'s `try` left every control green.

The inner layer is now asked in this process: the suite is replaced by one that raises a file error
carrying a path, `main` is called directly, and the failure must be caught, named with the command
(which only the inner layer does), projected, and must not leave `main` at all. The outer layer is
asked in two parts — what it does with a `SystemExit` carrying a message, which `main` never sees,
and that `__main__` is wired to it, read from the AST. Nothing through the CLI can tell them apart,
so a behavioural control alone would have been a control of the inner layer wearing the outer one's
name.

## 5. A parent is not this file

0308 §3 said "a site that runs its own `__file__` is admitted structurally, because the identity is
the expression; a sibling named the same way is not." The sentence was right and the code was not:
the peel followed `.parent`, so `[sys.executable, str(pathlib.Path(__file__).parent)]` was admitted
as "its own file" while python runs a DIRECTORY — that directory's `__main__.py`, a different
program. `.resolve()`, `.absolute()`, `str`, `os.fspath`, `os.path.realpath` and `os.path.abspath`
name the same file; a parent does not, and no site in this closure runs one. The peel no longer
follows it, and three planted controls stand on the rule: a parent, a grandparent, and a bare name
are each refused.

The bare name was the other half. `__file__` is the only name that is this file, and nothing had
been standing on that half of the test — the planted programs were all subscripts or binary
operations, so removing `and node.id == "__file__"` changed no control's answer.

## 6. Where extents are not the defence

During this round I reported that the whole-carrier withholding was a second layer behind
`mask_extents` for the suite's carrier fixtures, and that proving its propagation to spans would
need a seam in the floor. That was reasoning from the shape of the code without measuring, and it
was wrong. For both fixtures the real extent finder returns **nothing**: these carriers are withheld
because the text is undecodable, which is a decision extents cannot express. Withholding is the only
defence they have.

A seam was built and it disproved its own premise — with the real extents already empty, replacing
the extent finder removes nothing — so it was removed. Reverting `carrier_decision`'s withheld
branch leaks `shortpass` out of a natural fixture, through `units_of`, `shed` and the real writer,
and three controls say so: every span of a withheld carrier is blanked, the published file carries
no byte of it, and the differential over every carrier fixture. The property is established
end to end by real carriers, with no seam and no residual.

## 7. What this record does not claim

It says nothing about an entry point outside package A's two files; the other runlib suites still
print directly and still run their children unbounded, and that is stated rather than implied. The
structural control judges the shape of the self-running calls, not what they do: it establishes that
each stands inside the guard and marks its child, not that the guard is correct. The time bound
makes a runaway finite; it does not make it harmless.
