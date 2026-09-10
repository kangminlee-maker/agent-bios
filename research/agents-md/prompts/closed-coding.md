# Closed coding — apply a fixed codebook to instruction blocks

You are labelling, not designing. The codebook below is **fixed**: do not rename, merge,
split, or invent categories. If a block does not fit, that is a finding — return `OTHER` with
a reason. A wrong forced fit is worse than an honest `OTHER`.

## Codebook

`CODEBOOK`

## Task

`UNITS_PATH` is a JSON Lines file. Each line is one instruction block:

```
{"unit_id": "...", "full_name": "...", "path": "...", "heading": "...", "text": "..."}
```

For every line, assign exactly one `category` from the codebook, using the category's
`discriminators` when two are close. Assign `secondary` only when a block genuinely does two
jobs and dropping either would misrepresent it; leave it `null` otherwise.

Rules:

- Judge the block on **what job it does for the agent**, not on its heading. Headings lie:
  a section titled "Testing" may be a command recipe, a policy gate, or background context.
- Use `confidence: "low"` when the block is short, ambiguous, or sits exactly between two
  categories. Low-confidence labels are audited later, so marking them honestly is useful.
- `OTHER` requires a one-line `reason` describing the purpose you saw that the codebook has
  no home for.
- Label every unit in the file. Do not sample, summarize, or stop early. If the file has 60
  units, return 60 objects.

## Return format

Return **only** JSON Lines — one object per input line, same order, no prose, no code fence:

```
{"unit_id": "...", "category": "...", "secondary": null, "confidence": "high", "reason": null}
```
