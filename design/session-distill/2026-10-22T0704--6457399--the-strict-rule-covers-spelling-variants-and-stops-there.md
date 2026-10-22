---
created_at: 2026-10-22T07:04:00+09:00
head: 6457399
kind: design
supersedes: 2026-10-22T0335--4e06f15--the-skeleton-drops-what-renders-nothing.md
---

# The strict rule covers spelling variants and stops there

`projection.CURRENT` is `r20`, landed in `6457399` with the AB#0 and AB#1 fixes. `r1`..`r19` are
asserted unregistered. This record carries the owner's scope decision, which the superseded record
left as an open question.

## Scope of the strict quote rule — owner decision, 2026-10-22

The strict rule covers **spelling variants** of a secret name:

* every encoding and escape the JSON escape table defines — `\" \\ \/ \b \f \n \r \t` and `\uXXXX`
  with a surrogate pair joined into its one scalar, at any decode depth, with anything else refused
  as undecodable;
* Unicode normalisation — NFKC, casefold, and the orders that settle `APİ_KEY`;
* every character that renders nothing of its own or only modifies the character beside it — the
  AB#0 set: the three mark categories, the format characters, the unassigned points, and the four
  fillers Unicode calls ordinary letters.

It stops there. **Cross-script lookalikes — Cyrillic, Greek or other letters shaped like Latin ones,
the UTS #39 confusables — are out of scope**, recorded as a tracked residual rather than a gap.

The reasons, as the owner gave them:

* the transcripts are the owner's own work sessions, so a real secret name appears in plain ASCII;
* a lookalike name exists only if someone crafts it on purpose;
* the value itself is still masked by the floor's own value patterns, so the credential does not
  survive even when its name is spelled oddly;
* a confusables table would be a versioned data dependency carried for an adversarial-only case.

Closed alternatives:

* **map UTS #39 confusables** — closed, for the reasons above;
* **refuse every quote mixing Latin with another script inside one word** — closed, because it would
  refuse ordinary Korean text, such as an English word carrying a Korean particle.

`vf_invisible`'s docstring and the AB#0 control block both state this boundary where a reader meets
it, so the scope is in the code and not only in this record. The control asserts the current
behaviour directly: a Cyrillic `а`, an ordinary letter, a Hangul syllable and an emoji are read as
visible characters.

## Residuals

| Shape | Found | Status |
| --- | --- | --- |
| a comma-prefixed remainder carrying a separator but not a validated member (X#6) | round 12 | open by instruction |
| an unreadable structure class, 63 cases | round 15 | pending the owner |
| a secret name written with cross-script lookalike letters | round 19 (anticipated) | **out of scope by owner decision, 2026-10-22** |

The third row is not a defect queue entry: it records a boundary that was decided, so a later round
finds the decision rather than rediscovering the shape.
