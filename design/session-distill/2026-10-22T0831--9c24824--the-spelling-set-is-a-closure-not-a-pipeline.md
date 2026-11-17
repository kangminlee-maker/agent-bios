---
created_at: 2026-10-22T08:31:00+09:00
head: 9c24824
kind: design
supersedes: 2026-10-22T0725--2b5e3a1--one-spelling-set-feeds-all-three-triggers.md
---

# The spelling set is a closure, not a pipeline

`projection.CURRENT` is `r22`. `r1`..`r21` are asserted unregistered.

## The defect this closes

`r21` gave the three triggers one set, and the set was still a pipeline: each decode layer, expanded
by a fixed list of normalised forms. A pipeline privileges an order, and two orders were missing.

* **AD#0** — the invisible characters were stripped only inside the casefolded skeleton. The owner's
  home path and the floor's value patterns are case-sensitive, so they never saw a spelling that was
  stripped **and** case-preserved: `/Us<ZWSP>ers/<owner>` and `sk-abcdefghij<ZWSP>klmnopqrst` were
  admissible.
* **AD#1** — an escape that normalisation *reveals* was never decoded. A fullwidth backslash is an
  ordinary character until NFKC turns it into `\`, and decoding had already run before normalising
  and never ran again, so `＼u0070assword` never spelled `password`.

## The fix: a closure under single-step transforms

`vf_all_spellings(quote)` is now the **closure** of the quote under `vf_transforms`, a fixed set of
single steps:

* one layer undone by the JSON escape table — strict (`vf_unescape`) and relaxed (`vf_relax`);
* NFKC;
* NFKD;
* casefold;
* the invisible characters stripped (the AB#0 property).

Each step is applied to every string in the set until no new string appears. Any composition, in any
order, is therefore in the set — the r20 skeleton is now one path through these rather than a form of
its own, and `casefold then decode` is reachable exactly as `decode then casefold` is. Structures are
decoded as before, their member objects collected for the keyed-member rule and their leaf strings
fed back into the closure.

## The bound refuses; it never truncates

`VF_CLOSURE_LIMIT` is 256 strings and `VF_CLOSURE_ROUNDS` is 12. Passing either, or meeting a
sequence the escape table does not define anywhere in the set, sets `reach.exhausted` with a reason
of its own and **refuses the quote** as undecodable. A truncated set would be a clean answer about a
quote nobody finished reading, which is the failure this whole rule exists to prevent. `Reach.reason`
carries the closure's own words, so the refusal says which bound it was:

```
undecodable: it spells more than 2 strings
undecodable: its spellings were still growing after 1 round
undecodable: one of its spellings holds '\U', which the JSON escape table does not define
```

## Where the rule is proven

| Claim | Control |
| --- | --- |
| the set is CLOSED: every transform of every member is a member, over four subjects, with the set asserted non-empty first | `projection.py` AD block |
| an invisible character inside a case-sensitive owner path, and inside a case-sensitive credential: refused by the home and floor detectors | same block |
| an escape revealed by NFKC: refused naming `password` | same block |
| an escape revealed by casefolding: refused as undecodable — `\U` is outside the table and that refusal fires first, which is still a refusal | same block |
| Korean text, an ordinary escaped `é`, an emoji ZWJ sequence: admitted | same block |
| both bounds refuse by name, tested by lowering the bound around an ordinary quote, and the bounds are asserted restored afterwards | same block |
| the same shapes in SOURCE fixtures, refused at `make` and at an independently built `append` into a new and a populated file, storage unchanged | `evidence.py` strict-rows block |

The casefold-reveals-an-escape row is recorded as refused-for-another-reason rather than smoothed
over: AA#0 refuses `\U` before any casefolding can turn it into `\u`, so the order is unreachable in
practice. Both outcomes are refusals, and the boundary owes a refusal, not a particular one.

## Scope, unchanged

Spelling variants — the escape table, Unicode normalisation, and every character that renders nothing
or only modifies a neighbour. Cross-script lookalikes are out of scope by the owner's decision of
2026-10-22.

## Residuals

| Shape | Found | Status |
| --- | --- | --- |
| a comma-prefixed remainder carrying a separator but not a validated member (X#6) | round 12 | open by instruction |
| an unreadable structure class, 63 cases | round 15 | pending the owner |
| a secret name written with cross-script lookalike letters | round 19 (anticipated) | out of scope by owner decision, 2026-10-22 |
