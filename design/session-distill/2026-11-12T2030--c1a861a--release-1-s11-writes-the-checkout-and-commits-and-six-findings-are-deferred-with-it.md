---
created_at: 2026-11-12T20:30:00+09:00
head: c1a861a          # the commit the content was true at
kind: design
supersedes: 2026-11-12T1607--7535e80--wp21-containment-review-round-2-direct-fixes-and-target-identity.md
---

# Release 1's apply writes the checkout and commits, and six findings are deferred with that scope

The owner decided on 2026-11-12, answering the WP-21 containment unit's third review
(`D-20261112-2cf1c4`, kind direction):

> In release 1, S11 `apply` writes the approved changes into files of the DECLARED CHECKOUT and
> makes the git commit, and nothing else. It does not run the installer, does not write personal
> layers, install roots or the owner's state; it ends by naming the install command for the owner to
> run. Installing as part of apply moves to release 2.

What that closed: *S11 runs the installer and writes personal layers and state in release 1*.

Why it was closed, and not deferred quietly: three review rounds each found NEW blocking defects in
certifying what the existing installer, `update-state.py` and their recovery paths write — compiler
output under the system temp with no TMPDIR given, atomic-write siblings outside a file-valued
override's class root, recovery replaying persisted paths with no destination-root bound. Each round
closed the previous ones and found more, which is the shape of an unbounded surface rather than a
list. The owner had already ruled that an apply against real install roots is the owner's own
command after their review, so release 1 ends by NAMING that command instead of running it.

## The scope is a fact the code holds, not a sentence in this file

A scope that lives only in prose is a scope the code can drift out of. Each destination row carries
whether release-1 S11 may invoke its writer; the installer, the launcher, `update-state.py` and the
personal layers are `not_invoked_in_release_1`, their certification is withheld BY THAT NAME, and a
control holds that no row outside the checkout-and-git set can come back certified. A reader asking
"what may this release write" reads the manifest, not this record.

`environment.home` stays in the declaration, with a narrower job: git is handed HOME as the run
declares it (so no inherited `HOME` can reach a hook or a config include), and the checkout's own
tree is the only destination. It is no longer the base from which other writers' fixed roots are
computed, because release 1 runs none of those writers.

## The six findings deferred with it, with their revisit condition

Each is recorded with the round-3 text that found it. The revisit condition for all six is the same:
**release 2's decision to run the installer as part of apply.** None may be treated as closed by
this record; they are open findings whose subject this release does not reach.

1. `destinations.py:743` — "reachable: normal non-interactive installation writes temporary compiler
   output outside the declared roots." (`compose/instructions_store.py`'s `TemporaryDirectory` with
   no TMPDIR given.)
2. `destinations.py:754` — "reachable: assigning a class root directly to a file-valued override
   places atomic-write temporaries outside that root." (`update-state.py`'s `write_state` mkstemp
   siblings.)
3. `destinations.py:965` — "reachable: persisted installer transaction paths bypass the certified
   destination roots during ordinary install recovery." (`compose/instructions_install.py:899`.)
4. `destinations.py:833` — "reachable: fixed-root computation guesses containment for expressions it
   cannot establish."
5. `destinations.py:1138` — "reachable: root_from='argument' grants certification without proving
   that the writer accepts or uses such an argument."
6. `destinations.py:935` — "reachable: the password-database guard checker approves the opposite of
   the licensed condition."

Items 4, 5 and 6 are about certifying writers release 1 does not invoke. They are listed here rather
than fixed because a fix would have to be re-derived against release 2's scope anyway, and a check
that nobody's release exercises is a check that rots.

## What S12 `close` writes, and its release-1 form

By design S12 writes the ledger rows and the version registry into the CHECKOUT, the coverage state
into the checkout, and the nudge baseline through `session-distill/update-state.py`, which writes the
owner's own state root (the `nudge` destination class). Under the same rule the first three stay and
the fourth does not: release 1's close writes the checkout only and NAMES the nudge command for the
owner to run, exactly as apply names the install command. That keeps the stage's own record complete
— the ledger says what was applied — while nothing personal is written by a stage the owner has not
run against their own machine.

## A named exclusion: no Codex seat can take S7

`schemas/propose.schema.json` does not project into the provider's strict dialect. Fifteen optional
properties across four sites, and the ones that matter are per-operation-type:
`anchor`, `content`, `diff`, `entry`, `names`, `units` on an operation, where ABSENCE carries which
kind of operation it is. Making them required-and-nullable would drop that discrimination, and the
strict subset refuses the `anyOf`-per-type shape that would carry it properly.

So: a Codex seat cannot take S7 until the per-operation fields are decided. Today none does, so
nothing is blocked; the exclusion is named here with its revisit condition — **a seat assignment
that puts a Codex host on S7** — rather than left to be rediscovered by a provider's 400.

## A control two mechanisms guarantee, and what the trial does about it

`destinations`' control that a `self_test` a runtime function calls outright is IN the effect audit's
scope is held twice over: by the root rule (a `self_test` with a non-test caller is not test-only)
and by the walk's propagation (a real root reaching it pulls it in). Reverting either leaves the
control green, correctly — so no single-line revert row can show it firing, and a row that tries
reads as CONTROL-SILENT, which is indistinguishable from a rule nobody enforces.

Both mechanisms stay: each is the right answer for a different shape of module. The evidence is a
DOUBLE revert row in the trial, which removes both and watches the control fail by name. That row is
the only honest form the evidence can take, and it is written down because the next reader of a
single-line trial will otherwise find the gap and reach for the wrong conclusion.

## The instrument that judged all of this, and what was wrong with it

The revert trials counted a catch as "the wanted text appears on any line containing `[FAIL]`". The
dying-control wrapper prints `[FAIL] the suite died after '<control name>'`, so a row whose wanted
text was that control's name counted a DEATH as a catch; a traceback line carrying the text counted;
and so did the text landing in another control's detail. One judge now answers
(`work/impl/trialkit.py`): a catch is an anchored failure line whose CONTROL NAME starts with the
wanted text, and `died`, `incomplete`, `unanchored` and `silent` are verdicts of their own.

All 29 rows of the round-2 trial were re-judged on a clone with it: 27 of 29, unchanged. No catch
counted so far rested on a death or a traceback. The two that do not fire are the double-guaranteed
control above and one row whose anchor text the A rewrite removed, which was re-derived and fires.

One log was lost and re-made rather than claimed: `pt-21r2a.log` and a file written as
`pt-21r2A.log` are the same file on a case-folding filesystem, so the A trial's log overwrote the
earlier one. The 29-row trial was re-run on a clone of the committed tree to replace it.
