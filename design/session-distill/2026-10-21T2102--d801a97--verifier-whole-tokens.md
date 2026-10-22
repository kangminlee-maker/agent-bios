---
created_at: 2026-10-21T21:02:00+09:00
head: d801a97
kind: design
supersedes: 2026-10-21T2037--9422589--verifier-over-detects.md
---

# A cap, a prefix and a newline: three ways a generous rule stopped being generous

Lead direction of 2026-10-21, after the ninth review round. The verifier's four rules stand as the
superseded record states them. What changes is that each of them is now stated without a bound, and
the escape-run rule consumes what it claims to.

## What the round found

All three were in the keyed-fragment rule added the round before - the rule written to be generous:

- Its name token carried a 41-character cap, so a key behind 38 characters of padding split into two
  tokens and the floor claimed neither.
- Its value stopped at the first space, so a value that merely STARTED with the mask was read as
  masked and whatever followed stood in the output.
- Its escape-run test matched a terminal backslash and a short `\u`, but not a backslash before an
  actual newline - a run the lenient reading cannot cross, since that reading does not cross a
  newline.

## The rules

1. **A name token is matched whole.** No cap: a run of name characters, however long, asked of the
   floor as one token.
2. **The exemption is exact equality.** A keyed fragment's value is exempt only when it IS the mask -
   nothing before it, nothing after it, not a space and not a comma. A value that opens a structure
   matches empty and is left to the member rule, which keeps the residual structural class awaiting
   the owner's judgement exactly as it is.
3. **An escape run is consumed or it is `verifier-limit`, with nothing in between.** A run is
   consumed when it is a valid JSON escape or when the lenient reading can drop its backslash. Three
   runs are not: a backslash at the end of a string, a backslash before a real newline or carriage
   return, and a `\u` with fewer than four hex digits behind it.
4. **The independence guard follows the verifier's whole reachable closure**, computed from the call
   graph rather than from a list of entry points, and a dependency planted one call below an entry
   point must be rejected by it - otherwise the guard only checks the functions it was handed.
5. **Each generated class declares the decoding depth it is about**, and a deliberately shallower
   fixture - a container encoded but its credential plain - must be rejected by that assertion.
6. **The projection is `r13`**, and `r12` is refused by name.

## The closed alternative

**Bounding a generous rule for performance.** Every bound in it - a token length, a value
terminator, an escape form - is a place where the rule stops being the rule. The bounds that remain
are the verifier's depth and budget, and both of those are findings when reached rather than silent
stops.

## What it costs

Re-measured on the same local sample of 60 session files and 142,551 projected blocks: **2 blanked
blocks, 0.001%**, both for the floor detector - unchanged across r9 through r13. Re-measure before
quoting this.
