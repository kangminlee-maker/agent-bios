---
created_at: 2026-10-22T03:13:00+09:00
head: 898be61
kind: design
supersedes: 2026-10-21T2316--0794bd3--a-surrogate-pair-is-one-character.md
---

# The strict side reads the JSON escape table and nothing else

`projection.CURRENT` is `r19`. `r1`..`r18` are asserted unregistered, so evidence stored under a
projection that admitted an unsupported escape cannot be remade by asking for that version.

## The defect this closes

`r18` stated the principle — an encoding the traversal cannot complete refuses the quote — but the
strict side still inherited the *lenient* reading's treatment of an unsupported escape. That reading
drops a backslash before anything at all, so `\x41` read as `x41`: a sequence with no definition was
quietly treated as text, nothing reported a layer left undone, and the quote was admissible.

The principle was right and its scope was wrong. Stated exactly:

> The strict traversal decodes the JSON escape table and nothing else — `\" \\ \/ \b \f \n \r \t`,
> and `\uXXXX` with a surrogate pair joined into its one scalar. **Any** other backslash sequence, at
> **any** decode depth, is undecodable and refuses the quote. The strict traversal tracks this itself;
> the lenient reader is never asked.

Two functions carry it, and neither consults the lenient reading:

* `vf_outside_table(text)` — the first sequence the table does not define, or None. One string, no
  recursion.
* `vf_undecodable(value)` — the same question at any depth, decoding down through `vf_unescape`,
  `vf_relax`, `vf_load` and `vf_structures` only.

`evidence_quote_admissible` asks `vf_undecodable` before anything else, and names the offending
sequence in the refusal.

## What this deliberately refuses

A Windows path (`C:\Users\...`) holds `\U` and so is refused on the strict side. That is the
conservative direction for text persisted for sharing, and it is a consequence of the rule rather
than an oversight: a reader that cannot say what a sequence spells cannot rule out what it hides.
The view side is unchanged — by the owner's split of 2026-10-21, views and the local index stay
best-effort, so these sequences are still visible there and only the shareable boundary refuses them.

## Where the rule is proven

| Claim | Control |
| --- | --- |
| `\x41`, `\q`, `\u12`, `\U0001D5C9`, `\8`: outside the table, reached by the traversal, refused as undecodable | `projection.py` AA#0 block |
| a trailing lone backslash: outside the table, refused | same block |
| behind one layer of escaping, and inside a JSON structure the text spells — with the top layer asserted clean first, so the depth case proves something | same block |
| the table's own escapes, with characters needing none (`é`, a paired emoji): read and admitted | same block |
| the same rows in SOURCE fixtures, refused at `make` and at an independently built `append` into a new and a populated file, storage unchanged | `evidence.py` strict-rows block |

## AA#1: a row's source spelling is asserted, not assumed

`"AP\\u0130_KEY"` in this file is the **escape**, not the character, and reading it as the character
is how the plain U+0130 case went missing twice. Every strict row now declares the spelling its
source text actually has (`plain` — no backslash; `escaped` — at least one), and the control asserts
that spelling before any boundary is asked of the row. The plain row is built as
`"AP" + chr(0x0130) + "_KEY"`, the escaped row separately.

## Residuals

Unchanged. X#6 stays open by instruction; the 63-case unreadable-structure class stays as it is,
pending the owner.
