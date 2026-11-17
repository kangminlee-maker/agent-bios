---
created_at: 2026-10-21T18:15:00+09:00
head: e32b83b
kind: design
supersedes: 2026-10-21T1740--5efadbf--projection-single-pass.md
---

# The single pass stands, and an independent verifier stands behind it

Lead decision of 2026-10-21, after the fifth review round. This record keeps everything the
superseded record said - the single monotone pass in the original text's coordinates, and the closed
alternative of decode-first-accept-or-fall-back - and adds the backstop that makes a mapping mistake
safe rather than fatal.

## What the fifth round found

The pass was the right shape; every remaining leak was in one step of it, mapping a decoded finding
back to a raw extent:

- An encoded member was read as already covered because the key's name stood in an unrelated value
  of the same structure (E#0).
- A decoded level's findings replaced the other findings of that level instead of joining them, so a
  plain home path beside a twice-encoded token was left for a second projection (E#1).
- A decodable escaped body with no escaped quote in it was examined by nothing at all (E#2).
- A floor extent was replaced with its delimiters inside it, so the document stopped parsing and a
  second projection read the orphaned quote differently (E#3).

## The rule

1. **The single pass stands** as the superseded record states it, with four corrections: a decoded
   key counts as covered only when the raw rules can SEE that key; every extent of every decoded
   level is mapped back, not the deepest set alone; a body is read as escaped whenever it decodes,
   with or without an escaped quote; and a floor extent is normalised to what encloses it - one
   literal gives its inner range, two or more give the smallest enclosing structure, neither gives
   the extent as it stands.
2. **An independent verifier runs over the output of every block.** It decodes every string at every
   depth and escape layer with its OWN decoder - not the projection's walk - and runs the same three
   detectors over every spelling it reaches. If it finds anything, the whole block is replaced by the
   mask and the detector is recorded in the run's stats as `blanked:<detector>`. Nothing partial, and
   no second mapping to get wrong.
3. **Idempotence by construction.** A verified block holds no finding, so projecting it again changes
   nothing; a blanked block is the mask, and the mask is not a secret. Both are asserted, and so is
   the stronger property the fourth round asked for: a projected document still parses as JSON.

E#0 and E#2 were both local, and both are fixed in the mapping rather than carried by the verifier.
Controls assert that precision directly: each of the four shapes must be masked IN PLACE with the
block surviving, so reverting any one mapping fix fails by name instead of falling through to the
backstop. The verifier carries what remains - an escaped region whose character-to-raw-span map
cannot be built - and one control proves it fires on such a region.

## The closed alternative

**Relying on raw-extent mapping alone.** Five rounds asked the same question - which raw characters
produced this decoded byte - and it has a different answer for every spelling, every depth and every
escape layer. Each round's answer was correct for the shapes it was written against and wrong for
the next one. A backstop that does no mapping at all cannot be wrong in that way: it either finds a
credential in the output or it does not.

## What it costs

Measured over a local sample of 60 session files, 142,551 projected blocks: **2 blanked blocks,
0.001%**, both for the floor detector, in one file. 3,299 blocks (2.31%) were masked in place and
139,250 were unchanged. The backstop is therefore not a general blanket - it is the exception, and
its cost on real transcripts is close to nothing. Re-measure before quoting this: it is one sample
of one machine's sessions.

## How it is held

`projection.py --self-test` carries the four E-shapes as fixed cases and again as precision cases;
the syntax cases (valid JSON and exact first/second-projection equality); 280 seeded cases over
fourteen classes, including opaque values under an encoded key and floor credentials that exist only
after a decoding; and one shared oracle, built on the verifier's decoder, proven to reject a
deliberately unredacted output, a half-masked one, and a doubly encoded one before it judges any
generated case. `views.py --self-test` parses each `.json` artifact whole and each `.jsonl` artifact
per record, sweeps every decoded string for the owner's path in three spellings case-insensitively,
and proves both checks reject deliberate contamination planted in the index alone and in a window
alone.
