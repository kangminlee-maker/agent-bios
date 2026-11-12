---
created_at: 2026-11-12T16:07:00+09:00
head: 7535e80
kind: review
supersedes: 2026-11-12T0310--5f74b1e--s7-proposes-and-s7b-reviews-what-only-code-can-hold-lives-in-tables.md
---

# WP-21 containment: review X round 2, the direct fixes and the target-identity contract

Lane L's answer to review X round 2 of the WP-21 containment unit (pinned at `cf9187c`; rework, 4
blocking, 14 major, 1 minor), as committed at `7535e80`. This record states the judgement calls;
the commit message states what changed. Every figure is re-derivable from the artifact it names.

## Two departures carried from round 1

1. N#4 is read as a **(writer, override) pair**. The design sentence could be read per writer; one
   variable belonging to two classes is refused (`OVERRIDE_CLASS_SPLIT`). Read per writer,
   `install.sh` alone would carry every class and certify nothing.
2. `DESTINATION_BOTH_WAYS` is retired. Reporting both directions under one name put "the table
   holds too much" and "the tree holds too much" on one line, and the two need different fixes; they
   are `INVENTORY_INCOMPLETE`, `INVENTORY_UNWRITTEN` and `INVENTORY_FIXED_ROOT`. The token is
   no longer in the repository.

## One departure in round 2

The review offered two ways to make `exposure.py`'s table decide: make the predicates executable in
a constrained declarative form, or bind the declarations to named implementations by exact fidelity
checks. The first was taken. With a narrow grammar (names, constants, `and`/`or`/`not`, identity
and membership comparisons) the table is the authority; the second keeps two copies and adds a check
between them. The cost is explicit: a predicate outside the grammar is refused
(`EXPOSURE_PREDICATE_UNREADABLE`). The day a rule needs such a predicate it is a code branch again
and the table stops being the authority; that day is this choice's revisit condition.

## Lead decisions recorded here

- This unit is not closed under the two-round review cap. It is the layer every irreversible effect
  stands on and both rounds returned four blocking findings; it receives a third review after the
  structural fixes.
- Target identity has one owner, `runlib/targets.py`; `drift` and `journal` ask it. The case
  question is answered by reading the filesystem, never by writing a probe into the checkout, and an
  unanswered question refuses.
- The approved order is validated directly and returned when it holds; `ORDER_REARRANGED` means the
  approved order fails and another passes.

## Open at this commit

The destination derivation's inversion to a scrubbed per-writer environment, and the journal's single
confined handle and lock, are not in this commit. Three of round 2's blocking findings sit there. The
lead approved both designs with conditions on 2026-11-12; they follow in that order: journal, then
destinations.
