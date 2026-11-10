---
created_at: 2026-11-11T06:19:00+09:00
head: f168c5f          # the commit the content was true at
kind: review
supersedes: 2026-11-11T0345--0390fb3--a-codex-activation-names-the-rollout-the-host-wrote-and-f22-closes-for-new-pins.md
---

# Two review rounds taught the receipt reader and the pin readers that a reason may not outrun its evidence

Review X ran twice over this branch (round 1 on `d7889ef`, round 2 on `6bdb4db`, both
`fix_then_accept`) and its findings are closed in `abac3d9`, `6bdb4db`, `33d4174`, `acc301c`,
`49477a0`. This record states what is established at `f168c5f` and what is not. The earlier records
of this branch describe the trees they name and are not revised.

## What the rounds changed

**The receipt is evidence only where the reader asks what the writer promised.** A body that hashes
to its own file name was accepted while carrying the id that must live outside it, two different
installer digests, no installer root, files or build, an unreadable installer file, or a beginning
digest equal to the finishing one — which the writer normalises to null. The reader now holds the
installer block to the writer's exact shape, re-derives the installer digest from its own file rows,
and turns every violation into the `unbound` verdict with its own reason. An artifact `role` is
checked for being a string before set membership, where an unhashable role had raised.

**A recovery commits unbound rather than inheriting a refused claim.** The journal of a transaction
interrupted after its receipt was written carries that receipt id; an installer that refuses to write
one of its own now drops it first.

**A path is not an association.** A Codex activation accepts the thread's own path, and the host's
index row, only through one test: inside the resolved configured home's sessions tree, reached
through a sessions root that resolves to that home's own; exactly one link, since a hard link makes
one file two threads'; and a name carrying exactly one id, that id being this thread's, compared
without case. The highest readable thread database is the authority whether or not it holds the
thread, so an older store's row is no longer resurrected.

**A reason belongs to the pin it is about.** The pin-specific names
(`pin_predates_rollout_binding`, `rollout_unresolved`) reach a reader only on the identified-pin
path. A rollout no pin names takes an answer about the state: `unpinned`, or `rollout_unmatched` with
the count of pins carrying no rollout fields. Two or more pins naming one rollout are
`rollout_claimed_twice`, never a choice by file order, and the census keys such a rollout to none of
them. `id_space` is retired: its ground was the absence of the binding (D-20261111-b61c98).

**A reason may not be stronger than the scan behind it.** `unpinned` is said only by a scan that read
every pin file; an unreadable pin leaves the scan incomplete (`input_failed` with the count) and a
state that cannot be read says `input_unread` (D-20261111-fa0b3d). The two readers of one state share
one identity rule for what a pin is, so a record the census ignores is neither a claim on a rollout
nor a pin written before the binding.

## The fork-name limit, and what would close it

Because the index row is held to the same test as the thread's own path, **a row naming a fork-shaped
rollout — two ids in one file name — joins through neither step.** A forked thread's activation
therefore pins no transcript: it records `rollout_method: "rollout_unresolved"` naming both attempts,
and reads `rollout_unresolved` on its own `--pin` evidence path. This follows
D-20261111-18c350, which closed "the fork name's last id is this thread's", and refusing is the safe
direction, because a wrong join attributes one session's delivered bytes to another. It is a limit on
a class of sessions, not an edge case.

**Revisit condition:** measure on the installed host what it names a fork's rollout, whether that
file's `session_meta.id` is the fork's own thread id or the parent's, and which file a forked
thread's index row points at; until then a fork-named file joins through neither step. `FINDINGS.md`
F-33 carries the limit, that measurement, and the four ways to act on its answer.

## What remains unestablished

The 2026-11-11 measurement under a temporary `CODEX_HOME` covered one new, unforked thread: for it,
`thread.path` is the rollout, its name carries the thread id, and the index holds the row. Nothing
here measures a fork, a renamed rollout, or the owner's 15 pre-binding pins, which carry no rollout
fields and read `pin_predates_rollout_binding` until the one-time fill the owner has not approved.
Delivery and installer-exposure predicates remain WP-21's and WP-10's; this branch establishes the
binding and the join, not what a reader may conclude from them.
