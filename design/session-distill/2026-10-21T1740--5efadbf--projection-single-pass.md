---
created_at: 2026-10-21T17:40:00+09:00
head: 5efadbf
kind: design
supersedes: null
---

# The redaction projection is one monotone pass in the original text's coordinates

Lead decision of 2026-10-21, taken after the fourth consecutive review round found a leak in the
same place. This record **amends the projection rule** that
`2026-10-20T1942--9684f05--mechanism-design.md` §8.6 and the WP-06 plan describe; everything else in
them stands, including the evidence store, the window and omission contracts, and the view's own
obligations. It does not supersede those records: they describe the same stage, with a different
rule inside one function.

## The rule

`session-distill/runlib/projection.py` projects a string in ONE pass, in the coordinates of the
original text:

1. **Collect mask extents over the original text**, from every source that can name one: every
   match the redaction floor claims; the whole value extent of every secret-named key, whether that
   value is a quoted scalar (including any structure written inside it), a readable structure, or a
   clipped one; every home path of the owner; and every finding that only decoding reveals, mapped
   back to the raw extent that produced it.
2. **Mapping is at literal or structure granularity, never inside an escape sequence.** A decoded
   finding at any depth up to `MAX_EMBEDDED` marks the entire outermost raw string literal it came
   from. A secret-named key written in escapes names a value with no locatable extent of its own, so
   the raw structure that holds it is the unit. An escaped region is read in its own coordinates
   through a character-to-raw-span map; where that map cannot be built and the decoded form holds a
   secret, the extent is the whole region.
3. **The output is the original text with the union of those extents replaced by the mask.**
   Content inside quotes is replaced and the quotes are kept, so the syntax a reader sees survives.
   Nothing is re-serialised, and there is no accept-or-fall-back step.
4. **Anything the walk cannot read** - an unprovable or undecodable claim, a structure with no
   readable extent - keeps the previous rule: the containing literal or block is masked whole. The
   residual structural class awaiting the owner's judgement is unchanged.
5. **Idempotence by construction.** A mask token is not a secret (the test is exact equality), masks
   only grow, and `project(project(x)) == project(x)` is asserted rather than hoped for.

## The closed alternative

**"Decode first, accept the decoded result by an oracle, else fall back to the raw span union."**
That was the rule from r5 through r8, and it is closed.

The reason is not that any single rule in it was wrong. It is that the architecture had two paths
that masked different things, and the gap between them was a leak that each round moved rather than
removed:

- r5 masked the decoded form and compared raw strings, so an obligation whose escaped spelling
  vanished read as masked while the credential stood there decoded.
- r6 judged the result by the original text's obligations in every spelling, and the fallback then
  restored what the decoded pass had masked inside structures.
- r7 made the fallback carry the structures the decoded pass reached into, and a readable quoted
  obligation containing a structure was masked only inside - two runs, two answers (A#0).
- r8 masked such a value whole on both paths, and the fallback restored an encoded credential that
  gap and tail projection had already masked (A#1).

Four rounds, four fixes, four new gaps, all at the seam. One set of coordinates has no seam: every
source answers the same question about the same text, and a union of extents cannot mask less than
one of its members.

## What this costs

An escaped region whose character-to-raw-span map cannot be built is masked whole, where the
previous rule could sometimes mask inside it. That is a deliberate trade: a mask that is too wide
is a readability cost, and a mask that is too narrow is a disclosure.

## How it is held

`projection.py --self-test` carries the seven shapes the four rounds were about as fixed cases, each
asserted for absence, for the original's obligations, and for idempotence; a seeded property control
of 240 cases over twelve classes, each asserting that the transformation it advertises really changed
the text and judging the output by decoding it independently at every depth; and the proof that the
leak oracle rejects a deliberately partial mask. `views.py --self-test` carries the same shapes
downstream, inspecting index posting keys directly rather than asking the index a question, and
sweeping every artifact's decoded strings for both spellings of the owner's path.
