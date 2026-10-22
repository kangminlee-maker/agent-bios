---
created_at: 2026-10-21T23:16:00+09:00
head: 0794bd3
kind: design
supersedes: 2026-10-21T2247--b776d6b--floor-asked-not-rederived.md
---

# A surrogate pair is one character, and an encoding nobody can finish refuses the quote

`projection.CURRENT` is `r18`. Every earlier projection (`r1`..`r17`) is asserted unregistered, so a
stale artifact cannot be remade by asking for the version that produced it.

## The defect this closes

The verifier's traversal read `\uXXXX` escapes one at a time. A character outside the BMP is written
as two of them, so the traversal produced two lone surrogates instead of the one character they
spell. No normalisation maps a lone surrogate: a compatibility spelling of a secret name — the
mathematical sans-serif letters, `𝗉𝖺...` — arrived as unmappable halves, NFKC
folded nothing, and the floor was never asked about the name `password` those letters spell. The
quote was admissible.

## The principle, not the case

Written as a rule about the traversal rather than about mathematical letters, because the same shape
exists for every non-BMP block and new ones are added to Unicode:

> In the traversal the strict rule uses, a valid surrogate pair decodes to its one scalar. A lone
> surrogate, an invalid escape, or any decoding the traversal cannot complete **refuses the quote**,
> with the reason `undecodable`.

The refusal is the half that matters. A pair that decodes is asked of the floor like any other
spelling; a run that does not decode is a run whose content nobody here can rule out, and the strict
side does not store what it could not read. `vf_pair` is the single place that resolves one escape,
shared by the clean reader (`vf_unescape`), the relaxed reader (`vf_relax`, for text that is not one
clean layer throughout) and the unfinished-run detector (`vf_unfinished`) — so a lone surrogate is
reported as an unfinished run, `Reach.exhausted` is set, and `evidence_quote_admissible` refuses.

A lone surrogate inside a transcript block is therefore blanked by the projection before any quote is
taken from it, which is the stronger outcome: there is no sensitive text left to refuse. The
predicate is still asked about the raw text in the controls, because the projection's blanking and the
strict rule's refusal are two different guarantees and only one of them is about sharing.

An ordinary non-ASCII word — Korean, or an emoji written as a pair — reads cleanly and is admitted.
The rule refuses unreadable encodings, not unfamiliar characters.

## Where the rule is proven

Controls live where the thing they test lives, and the evidence-side ones go through the real
writers rather than the predicate:

| Claim | Control |
| --- | --- |
| a pair decodes to its character; the relaxed reader joins one inside ordinary text | `projection.py` Y#0 block |
| the floor is asked about the name those letters spell | same block, via `vf_secret_name` |
| a lone high / lone low surrogate, a half-pair, a short second half: unreadable, unfinished, refused as `undecodable` | same block |
| an escaped Korean word and an escaped pair emoji are read and admitted | same block |
| the names stand in SOURCE fixtures, the projected quote still carries them | `evidence.py` strict-rows block |
| `make` refuses, and an independently built record is refused at `append` into a new file and into a populated one | same block, both paths |
| a refusal creates no file and leaves every stored byte unchanged | same block |
| the lone-surrogate rows are blanked by the projection, and the raw text is still refused as `undecodable` | same block |

## Y#2: a dirty text is a copy of the row, not the row with a mask substituted

The downstream detector pairs used to build their dirty input by replacing the first mask in the
clean text. For two rows that produced a different shape from the one the fixture persists, so the
control exercised a rule the fixture does not run. Each pair is now written out as a literal copy of
the persisted row's own text with exactly the target value changed, and the control asserts it: clean
and dirty differ in exactly one span, and that span is the target value, plus only the punctuation
the row is about — the comma for the mask-plus-comma row, the run for the escape-run row. The clean
case is asserted first, then the exact detector.

## Residuals

Unchanged from the superseded record, except that the undecodable class is now closed on the strict
side. X#6 (a comma-prefixed remainder carrying a separator but not a validated member) stays open by
instruction, and the 63-case unreadable-structure class stays as it is, pending the owner.
