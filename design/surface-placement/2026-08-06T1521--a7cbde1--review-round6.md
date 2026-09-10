---
created_at: 2026-08-06T15:21:00+09:00
head: a7cbde1
kind: backlog
---

# Six findings from the sixth Codex round, none of them verified

The review of #20 ran six rounds. This round produced seven findings; one was fixed in the PR
and these six were not, by a rule fixed **before** the findings were read: only
`compose/assemble.py` would be touched, because that file had shown a gap in its own previous
fix three rounds running. It produced zero findings this round, which was the signal the rule
was watching for.

**These are reviewer claims, not established defects.** Every finding acted on in this PR was
re-derived from the code first, and that mattered — one had a correct conclusion resting on a
wrong mechanism, and two were already fixed while still being reported. Nothing below has had
that treatment. Read each as a hypothesis with a place to start looking.

| where | | claim |
| --- | --- | --- |
| `learn/migrate-learnings.py:260` | P1 | Activation proof is compared by bundle revision only, so a proof from an earlier `onboard` — or from a different `CLAUDE_CONFIG_DIR` home carrying the same revision — authorizes deleting personal learnings without a fresh canary |
| `launch/agent-launch.py:1774` | P1 | A zero-byte pass with exit 0 has a truthy SHA-256, so it counts as a distinct fold and the panel reads as achieved although one pass returned nothing |
| `gates/check-receipt-chain.py:190` | P2 | The chain check does not invoke real adapters with their documented flags |
| `ontology/extract.py:143` | P2 | Removal performed through `assemble.py` is not recognized |
| `ontology/extract.py:43` | P2 | Assembler writes are missing from deploy coverage |
| `SURFACES.md:217` | P2 | Claims design files can enter the package, which the payload boundary does not allow |

The two P1s are the ones to look at first, and they are the same shape as each other and as
`launch/agent-launch.py:1774`'s sibling already recorded in the carryover note: **a truthy value
standing in for a verified one.** A revision that matches is treated as a canary that ran; a
non-empty hash is treated as a pass that produced something. Both credit a check that never
happened, which is the failure the receipt surface exists to prevent.

Neither is introduced by this merge.

## Why the round stopped here

Findings per round ran 4, 4, 4, 2, 2, 7 — the last number is not a regression but a widening:
this round reached into `learn/`, `ontology/` and `launch/`, subsystems the merge does not
touch. Meanwhile the files this session actually edited went quiet, and `compose/assemble.py`,
the one that had needed three consecutive corrections, produced nothing.

The PR exists to land a verified merge. Absorbing findings from every subsystem the reviewer
can reach has no natural end, and each round of fixes was itself generating the next round's
findings — five of the defects fixed in this PR were introduced by an earlier fix in the same
PR. Stopping while the edited surface is quiet is the point at which that loop closes.

## Entry conditions

None blocked. The two P1s want their subsystem's context loaded rather than a quick patch —
`learn/` has the promote→migrate lifecycle behind it, and the fold belongs with the
reviewer-registry receipt work in `design/reviewer-registry/DESIGN.md`, which is where the
first fold finding was already sent.
