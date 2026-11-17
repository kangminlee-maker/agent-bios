---
created_at: 2026-10-21T22:23:00+09:00
head: 1bfd4c7
kind: design
supersedes: 2026-10-21T2156--4f74584--strict-quotes-best-effort-views.md
---

# A rule that protects the floor may not be narrower than the floor

Round-15 findings against the owner's split of 2026-10-21. The split itself stands exactly as the
superseded record states it: strict and blocking for evidence quotes, best effort for model-bound
views and the local index, new view shapes tracked as residuals. What changes is one blocking defect
in the strict rule and two residuals that turned out to be local.

## The strict rule

**It recognises secret names with the floor's OWN matching.** The alternation is read out of the
floor's first pattern and compiled with the floor's own flags, and every spelling the verifier reaches
is NFKC-normalised and casefolded before it is searched. There is no second scanner: the previous one
was an ASCII name token, which is narrower than the thing it protects - the floor's `(?i)` matching
recognises `paſſword` (U+017F), and a quote holding that name was admitted into a stored record.
A fullwidth `ｓｅｃｒｅｔ` is the same class of miss, and NFKC is what closes it.

`evidence.make` and `evidence.append` both ask the rule, a refusal is `EVIDENCE_QUOTE_SENSITIVE`, and
a refusal writes nothing: no store file is created and every existing one stays byte-identical. A
record built independently of `make` - as another tool or an older file would hand one in - is refused
at `append` all the same.

**The projection is `r16`**, so evidence made under `r15` is refused by name: the strict rule changed
what may be stored.

## The two residuals that were local

- A complete multiline structured value was cut by the line region, so only `[` remained, which then
  read as a structure this verifier cannot parse - and so as the owner-pending class. A quoted scalar
  and a structure are now read from the whole text rather than from the line: their extent is a
  scanner's question, and a line is not a scanner.
- Any remainder beginning with a comma passed as packaging, so `"<REDACTED>",v15suffix` was exempt
  with a suffix that belonged to nobody. What follows a comma must itself carry a separator - a member
  rather than any text at all.

## Tracked residuals

| Shape | Round found | Status |
| --- | --- | --- |
| A readable structured value in a fragment keeps its key association, every leaf checked | 14 (V#0) | fixed, controlled |
| What follows a quoted scalar is not the scalar's; nothing stripped from inside one | 14 (V#1) | fixed, controlled |
| A quoted key whose separator stands after a newline | 14 (V#2) | fixed, controlled |
| A structure whose extent genuinely cannot be read, under a secret-named key | 9 onward | open - the owner-pending structural class, unchanged by design |
| A value region whose remainder begins a further member of the same object | 14 | deferred to the member rule, which reads those members as members |
| The strict rule's token scanner narrower than the floor's own matching | 15 (W#0) | fixed, controlled |
| A complete multiline structured value truncated by the line region | 15 (W#5) | fixed, controlled |
| Arbitrary suffix text accepted as packaging after a comma | 15 (W#6) | fixed, controlled |
| Any further keyed-fragment spelling | - | residual: tracked here, not blocking |

## What it costs

The projection, re-measured on the same local sample of 60 session files and 142,551 projected
blocks: **114 blanked blocks, 0.080%** - 112 keyed fragment, 2 floor. Unchanged from r15, so none of
this round's three fixes costs anything on real transcripts. Re-measure before quoting this.
