---
created_at: 2026-10-21T22:47:00+09:00
head: b776d6b
kind: design
supersedes: 2026-10-21T2223--1bfd4c7--strict-rule-uses-the-floors-own-matching.md
---

# The floor is asked, not re-derived, and asked about whole tokens

Round-16 findings against the owner's split. The split stands as the superseded records state it. What
changes is the FORM of the strict rule's name recognition, which had been giving up one property to
keep the other.

## The two properties, and why one rule had to hold both

- **It may not be narrower than the floor.** The previous form casefolded each spelling and searched a
  scraped alternation. Casefolding `APİ_KEY` (U+0130) inserts a combining dot, after which the floor's
  own `api[_-]?key` no longer matches - so a quote naming `APİ_KEY` was admitted into a stored record.
- **It must be about whole tokens.** The scraped alternation was unanchored, so `input_tokens` and
  `tokenizer` were refused for containing `token`, although the floor itself claims neither name.

A scraped pattern cannot hold both: recompiled, it loses the floor's recognition; unanchored, it loses
the token boundary.

## The rule

**The floor is asked.** Every name token of every spelling is put to `secret_key`, which probes the
floor with `name=<value>` and reads whether the floor changed it - the floor's own pattern, its own
end-of-name context, its own flags, unchanged. Nothing is re-derived.

**It is asked about a union of spellings**, because no single normalisation preserves every name the
floor recognises: the text as it stands, NFKC, casefold, NFKC of the casefold of NFKC, and a skeleton
(NFKD, combining marks dropped, casefolded, NFKC). A name recognised in any of them is a finding.
Over-refusal is acceptable on this side - a refused quote is simply not stored, and the caller quotes a
span that names nothing - while under-refusal is a credential in a shared record.

**The token is Unicode-aware**: `\w` in Python 3 is Unicode, and the ASCII class this carried before
split `paſſword` into `pa` and `word`, so the floor was never asked about the name at all.

**The projection is `r17`**, so evidence made under `r16` is refused by name.

## Tracked residuals

| Shape | Round found | Status |
| --- | --- | --- |
| A readable structured value in a fragment keeps its key association, every leaf checked | 14 (V#0) | fixed, controlled - and a persisted transcript row since round 16 |
| What follows a quoted scalar is not the scalar's; nothing stripped from inside one | 14 (V#1) | fixed, controlled - and a persisted transcript row since round 16 |
| A quoted key whose separator stands after a newline | 14 (V#2) | fixed, controlled - and a persisted transcript row since round 16 |
| A structure whose extent genuinely cannot be read, under a secret-named key | 9 onward | open - the owner-pending structural class, unchanged by design |
| A value region whose remainder begins a further member of the same object | 14 | deferred to the member rule, which reads those members as members |
| The strict rule's token scanner narrower than the floor's own matching | 15 (W#0), again 16 (X#0) | fixed, controlled - the floor asked directly over a union of spellings |
| A complete multiline structured value truncated by the line region | 15 (W#5) | fixed, controlled |
| Arbitrary suffix text accepted as packaging after a comma | 15 (W#6) | fixed, controlled |
| A comma-prefixed remainder that carries a separator but is not a validated member - `,suffix_canary:` passes | 16 (X#6) | **open** - view-level residual, not fixed. The strict rule refuses such a quote, so nothing persisted for sharing carries it |
| Any further keyed-fragment spelling | - | residual: tracked here, not blocking |

## What it costs

The projection, re-measured on the same local sample of 60 session files and 142,551 projected blocks:
**114 blanked blocks, 0.080%** - 112 keyed fragment, 2 floor. Unchanged from r15 and r16. The strict
rule's reach grew; the projection's did not, because the strict rule governs quotes and not windows.
Re-measure before quoting this.
