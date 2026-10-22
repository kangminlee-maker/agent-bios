---
created_at: 2026-10-22T07:25:00+09:00
head: 2b5e3a1
kind: design
supersedes: 2026-10-22T0704--6457399--the-strict-rule-covers-spelling-variants-and-stops-there.md
---

# One spelling set feeds all three triggers

`projection.CURRENT` is `r21`. `r1`..`r20` are asserted unregistered, so evidence stored while the
triggers disagreed cannot be remade by asking for the version that stored it.

## The defect this closes

The strict rule has three triggers: a secret-named token, a match for the floor's own value patterns,
and the owner's home path. Only the first received the normalised spellings — `vf_secret_name`
expanded `vf_skeletons` inside itself, while the floor's value patterns and the owner-path detector
were handed the decoded string alone. So an owner path written with a fullwidth letter, and a floor
value broken by a zero-width space, were judged by a narrower set than a name was, and could be
stored.

The previous record's scope decision made this visible: the owner's scope is *spelling variants*, and
one of the three triggers was reading them while two were not.

## The fix is structural, so the three cannot diverge again

`vf_all_spellings(quote)` returns `(spellings, members, reach)` and is the only place the set is
built: the decode layers from `every_spelling`, each expanded by `vf_skeletons` into raw, NFKC,
casefold, NFKC(casefold(NFKC)) and the skeleton — every decode depth times every normalisation.
Admission then runs one loop over that one set, asking three detectors per spelling.

`vf_secret_name` was split for this: `vf_name_in(text)` asks the floor about the tokens of **one**
string, and `vf_secret_name` is that asked about each of `vf_skeletons`. Admission uses
`vf_name_in`, so all three detectors receive exactly the same strings rather than one of them
re-expanding privately.

## The structural claim is asserted, not trusted

`SPELLING_PROBE` is a module-level dict that admission fills through `vf_probe` when a control sets
it, recording which strings each detector was asked about. The control asserts all three names are
present and the three recorded sequences are **identical**, and names the narrowest detector when
they are not:

```
the three strict detectors were handed different spelling sets - 'floor' saw the narrowest,
{'floor': 1, 'home': 5, 'name': 5}
```

It is asked of an **admitted** quote on purpose: a refusal returns early, which would leave the three
lists different lengths for a reason that is not divergence. The probe is `None` outside the control,
so nothing is recorded in a real run.

## Where the rule is proven

| Claim | Control |
| --- | --- |
| an owner path with a fullwidth letter, a zero-width space, a combining mark: refused, and by the home detector | `projection.py` AC#0 block |
| a floor value in fullwidth and with a zero-width space: refused, and by the floor detector | same block |
| an ordinary non-owner path with Unicode letters, Korean text, a plain sentence: admitted | same block |
| all three detectors ran, over identical sets, and the probe recorded something | same block |
| the shared set reaches a name behind a layer of escaping, keeps the text as it stands, and normalises a fullwidth spelling | same block |
| the same variants in SOURCE fixtures, refused at `make` and at an independently built `append` into a new and a populated file, storage unchanged | `evidence.py` strict-rows block |

Two of the five path rows are masked in the view already — the projection's own home rule reaches a
zero-width space and a combining mark — so those rows assert the masking and then the raw text's
refusal, and the three the view still carries assert the boundary refusing them. That split is
recorded rather than smoothed over: it is the difference between the best-effort view and the strict
boundary, which is the owner's split of 2026-10-21 working as intended.

## Scope, unchanged from the superseded record

The strict rule covers spelling variants — the escape table, Unicode normalisation, and every
character that renders nothing or only modifies a neighbour — and stops there. Cross-script
lookalikes are out of scope by the owner's decision of 2026-10-22.

## Residuals

| Shape | Found | Status |
| --- | --- | --- |
| a comma-prefixed remainder carrying a separator but not a validated member (X#6) | round 12 | open by instruction |
| an unreadable structure class, 63 cases | round 15 | pending the owner |
| a secret name written with cross-script lookalike letters | round 19 (anticipated) | out of scope by owner decision, 2026-10-22 |
