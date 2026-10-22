---
created_at: 2026-10-21T21:27:00+09:00
head: 27f72ed
kind: design
supersedes: 2026-10-21T2102--d801a97--verifier-whole-tokens.md
---

# The keyed rule's unit is a line, because every smaller unit had a next bound

Lead direction of 2026-10-21, after the tenth review round. The verifier's four rules stand as the
superseded record states them. What changes is the FORM of the keyed-fragment rule: three rounds each
found the next bound inside it, so the bounds are gone rather than widened.

## What the rounds found, in order

- A 41-character cap on the name token (round nine).
- A value that stopped at the first space, so a value starting with the mask read as masked (round
  nine).
- An eight-character window for the separator, which nine spaces crossed (round ten).
- A value that stopped at a comma, so `"<REDACTED>,canary"` read as masked (round ten).

Each fix widened a number. The next round found the next number.

## The rule

**No numeric bound and no regex-delimited value anywhere in the keyed rule.**

1. Its unit is the whole logical line. A secret-named token, then a `:` or `=` anywhere later on that
   line - any distance - and the value region is everything after the separator to the end of the
   line, or the next non-empty line when the line ends at the separator.
2. A quoted scalar inside the region is read with a **real string scanner**: the opening quote and the
   escapes are tracked, so a comma, a brace or anything else inside the scalar belongs to the scalar.
   A scalar the scanner cannot read to its close is a finding, not a pass.
3. The region passes only if, after removing packaging - surrounding whitespace and quotes, a trailing
   comma or semicolon, the brackets that close the structure the value sat in - what remains is exactly
   the mask, or nothing at all.
4. A region that OPENS a structure is left to the member rule, which keeps the residual structural
   class awaiting the owner's judgement exactly as it is.

The independence check is now one callable returning named violations, run on this module and then on
an AST whose dependency sits one call below an entry point. Depth validation is one function, used by
the generated cases and by the planted ones, and proven on a case that needs no decoding while
declaring one and two.

**The projection is `r14`**, and `r13` is refused by name.

## The closed alternative

**Widening the bounds again.** Three rounds of that produced three bypasses. A line is not a number,
and a scanner is not a pattern.

## What it costs

This is the first change that moved the figure. Measured before committing, on the same local sample
of 60 session files and 142,551 projected blocks: **112 blanked blocks, 0.079%** - 110 for the keyed
fragment and 2 for the floor, against 2 in total at r13. The owner's threshold for this round was
0.5% (about 713 blocks), so the rule stands as written. 3,255 blocks (2.28%) were masked in place.
The blanked blocks are concentrated in lines naming `token` and `authorization`, where a value region
holds prose after the mask. Re-measure before quoting this.
