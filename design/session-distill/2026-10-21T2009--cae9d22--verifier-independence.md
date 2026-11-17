---
created_at: 2026-10-21T20:09:00+09:00
head: cae9d22
kind: design
supersedes: 2026-10-21T1937--b8c83d2--projection-verified-invariants.md
---

# A backstop that consults the mapping cannot catch the mapping

Lead decision of 2026-10-21, after the seventh review round. The single pass, the verifier and the
four invariants stand as the superseded record states them. What changes is that the verifier no
longer reads anything of the mapping, and that its rules are stated as local and total.

## What the round found

The verifier asked its secret-named-key question through the projection's own textual scanner, and
that scanner reads a key only where it can locate the value - while the mapping had already declared
the key "covered" by NAME. A duplicate `password` member standing behind a masked one, or one with a
newline before its colon, was therefore skipped by both. The backstop was blind in exactly the
places the mapping is blind, which is the one failure mode a backstop may not have.

## The rules

1. **The verifier is independent of the mapping, and that is a source-level fact.** Its functions may
   use the floor's patterns, the home patterns, `secret_key` and the mask test, and nothing of the
   mapping - no extents, no spans, no locator, no coverage. `self_test` parses this module and fails
   by name when a verifier function calls a mapping function, and it fails too when a name in either
   list no longer exists.
2. **Its three rules are local and total.** A floor match in any spelling it can reach is a finding.
   The owner's home path in any spelling is a finding. And for EVERY member of every decoded object -
   duplicates kept, in order, whatever whitespace stands around the colon - a secret-named key whose
   value is not exactly the mask is a finding; for a structure value, every leaf must be the mask. An
   absent value (null, empty text, an empty structure) discloses nothing and is not a secret. Objects
   are decoded with every member preserved, because `json.loads` keeps only the last value for a
   repeated key - and a masked duplicate standing last is exactly how one got through.
3. **An escape layer that starts and cannot be read is `verifier-limit`.** A text with a backslash
   that no reading gets past - a trailing one, a truncated sequence - is a layer the traversal did not
   finish. A Windows path is not this case: the lenient reading gets past it, so the detectors do see
   its characters.
4. **Blanking is counted at the content-block boundary.** `project` is that boundary. `BLOCKS` counts
   blanked content blocks and `BLANKED` counts blanking operations, since a structured block's leaves
   each pass the exit; both are recorded in the run's view statistics.
5. **The projection is `r11`**, because its output can change, and `r10` is refused by name wherever
   an artifact names it.

## The closed alternative

**Letting the backstop reuse the mapping's reading of a key/value association.** It is the cheapest
implementation and it cancels the backstop: the two agree precisely where the mapping is wrong.

## What it costs

Re-measured on the same local sample of 60 session files and 142,551 projected blocks: **2 blanked
blocks, 0.0014%**, both for the floor detector - unchanged from r9 and r10. The total member rule and
the unreadable-layer rule cost nothing on real transcripts. 3,299 blocks (2.31%) were masked in
place. Re-measure before quoting this.
