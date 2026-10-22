---
created_at: 2026-10-21T19:37:00+09:00
head: b8c83d2
kind: design
supersedes: 2026-10-21T1815--e32b83b--projection-verified-single-pass.md
---

# The backstop's own rules are invariants, and the projection is r10

Lead decision of 2026-10-21, after the sixth review round. The single pass and the independent
verifier stand as the superseded record states them. What changes is that the verifier's own
coverage is no longer a matter of cases: four rules now hold everywhere, and the projection carries
a new version because its output can differ.

## The rules

1. **An unfinished verification is a finding.** The traversal reports `verifier-limit` when it stops
   with something still to decode - its depth limit, its budget, or a layer it cannot read - and the
   block is blanked. A backstop that gives up quietly reports clean on exactly the inputs it failed
   to read. It also reads leniently: a backslash before anything at all is dropped, because six
   layers of `\` decode down to `sk\-abcdefghijklmnopqrst`, which the floor does not match and
   any careless reader recovers.
2. **Every block leaves through one exit.** `emit` is the only `return` in the block-producing
   functions, and that is checked against the source rather than remembered. The structured path used
   to serialise its walk and return it unverified, so two leaves that were each clean emitted a floor
   match across the member boundary between them - and a second projection masked it, which is how
   idempotence broke too. What a reader, an index and a quote all see is the final emitted text, and
   that is the text the verifier reads.
3. **Valid JSON in, valid JSON out.** A number, a boolean or a null under a secret-named key is
   replaced by a quoted mask, since it had no quotes of its own; a blanked JSON block becomes a valid
   JSON string. Any block whose projection stops parsing while the input parsed is blanked by the
   same rule, named `broken syntax`.
4. **The projection is `r10`.** `r9` is unregistered and refused by name wherever an artifact names
   it - windows, indexes, evidence records - because r9 masked less than r10 does.

Blank counts by detector are recorded in the run's view statistics, so how often the mapping could
not cover a block is a figure a reader of the run can see.

## The closed alternative

**Keeping the backstop's coverage as a set of cases.** Each of the four was found as a case in one
round and would have been fixed as a case; each is in fact a rule, and a rule is what a later shape
cannot slip past.

## What it costs

Re-measured on the same local sample of 60 session files and 142,551 projected blocks: **2 blanked
blocks, 0.0014%**, both for the floor detector - unchanged from r9's measurement, so the lenient
reading and the limit rules cost nothing on real transcripts. 3,299 blocks (2.31%) were masked in
place. Re-measure before quoting this.
