---
created_at: 2026-10-22T03:35:00+09:00
head: 4e06f15
kind: design
supersedes: 2026-10-22T0313--898be61--the-strict-side-reads-the-table-and-nothing-else.md
---

# The skeleton drops what renders nothing, and that is a property rather than a list of attacks

`projection.CURRENT` is `r20`. `r1`..`r19` are asserted unregistered.

## The defect this closes

The strict skeleton dropped combining marks only — category `Mn`. Every other invisible character
stood: `pass<ZWSP>word` reads as the name to a person, tokenised as two ordinary names
(`VF_TOKEN` splits on the zero-width space), and the floor was asked about neither. A zero-width
joiner, a soft hyphen, a variation selector, a tag character and the Hangul fillers all did the same.

The test is now the property:

> A character the skeleton drops is one that renders nothing of its own, or only modifies the
> character beside it — the three mark categories (`Mn`, `Mc`, `Me`), the format characters (`Cf`),
> the unassigned points (`Cn`), which have no glyph at all, and the fillers that Unicode calls
> ordinary letters.

`vf_invisible(character)` answers it, `VF_INVISIBLE_CATEGORIES` holds the categories, and
`VF_IGNORABLE` holds only what no category names: U+115F, U+1160, U+3164 and U+FFA0, which are `Lo`
and render nothing.

## Why the explicit list is four code points and not five ranges

The round asked for the variation selectors, their supplement, the Mongolian U+180B..U+180F run and
the tag characters. They are all dropped — every one of them is `Mn`, `Cf` or `Cn`, so the category
test already names them, and listing them as well would be lines no revert could make fail. That is
the repo's own standard about checks that cannot fire, so instead of listing them a control asserts
that `VF_IGNORABLE` holds **nothing a category covers**. Adding such a line now fails the self-test
by name, which is what keeps the claim true as Unicode assigns new characters: if a listed filler is
ever given a mark or format category, the list is told to shrink.

Reaching the tag block's unassigned holes (U+E0000, U+E0002..U+E001F are `Cn`) is why `Cn` is in the
category set rather than the block being listed. It is also the conservative direction generally: an
unassigned code point has no glyph, so a reader sees the name without it.

## Open question, not fixed: cross-script confusables

Cyrillic `а` and Greek `ο` render characters of their own, so `vf_invisible` leaves them standing and
`pаssword` with a Cyrillic `а` is a different name to the floor. **Whether the strict rule should map
cross-script confusables is an open question with the owner as of 2026-10-22**, taken up by the lead
in this round. It is deliberately not implemented here, and a control asserts the current boundary —
a Cyrillic `а`, an ordinary letter, a Hangul syllable and an emoji are all read as visible — so the
open question has a place in the code to land on rather than a silent gap.

## Where the rule is proven

| Claim | Control |
| --- | --- |
| fifteen invisible characters, one per category and per listed filler: read as invisible, the floor still finds `password`, the quote refused naming the token | `projection.py` AB#0 block |
| `VF_IGNORABLE` holds nothing a category covers; an unassigned tag point is invisible | same block |
| a Cyrillic `а`, an ordinary letter, a Hangul syllable, an emoji: NOT invisible | same block |
| ordinary Korean text, an emoji ZWJ sequence, a variation selector in a non-secret word: admitted | same block |
| the same names in SOURCE fixtures — seven categories plain and three JSON-escaped — refused at `make` and at an independently built `append` into a new and a populated file, storage unchanged | `evidence.py` strict-rows block |

## AB#1: the clean case first in W#3's gap loop

Each separator gap now asserts its clean counterpart before the dirty one, so a detector that fires
on everything reads as a failure at the clean assertion instead of being confirmed by the dirty one.
A revert cannot demonstrate an ordering, so the proof that the assertion is live is the other
direction: making the clean text carry a credential fails `W#3: the clean counterpart at 0 space(s)
is found by nothing` by name.

## Residuals

X#6 stays open by instruction; the 63-case unreadable-structure class stays as it is, pending the
owner; cross-script confusables are the new open question above.
