# Open coding — derive a purpose taxonomy for agent-instruction files

You are one of several analysts working **independently** on the same evidence. Another
analyst's taxonomy will be compared against yours; convergence is the signal we want, so do
not try to guess what anyone else would produce. Derive your categories from the evidence in
front of you and nothing else.

## Evidence

Read the entire packet at `PACKET_PATH`. Each file is delimited by a
`===== FILE <owner/repo>::<path> | stars=… followers=… lang=… bytes=… =====` header.
These are real `AGENTS.md` / `CLAUDE.md` files from repositories with ≥1,000 stars or owners
with ≥1,000 followers. Read every file. Do not skim; the packet is sized to be read in full.

## Unit of analysis

One **instruction block** = one heading section, or one coherent run of bullets under a
heading. Categorize blocks, not whole files — a single file routinely serves several purposes.

## What "purpose" means here

Group blocks by **the job the block does for the coding agent that reads it** — what changes
in the agent's behaviour because the block is present. Group by function, not by surface
form: two blocks written as a bullet list and a prose paragraph serve the same purpose if
they change the same thing. Conversely, "Commands" and "Testing" are the same *topic* but may
be different *purposes* (orientation vs. gate) — decide by what the agent is supposed to do
with the text.

## Constraints on the taxonomy

- **Bottom-up only.** Do not import a category set you already know from documentation
  conventions, README structure, or prior training. Every category must be traceable to
  blocks you actually read in this packet. If you catch yourself producing a familiar-looking
  list, re-derive it from the evidence.
- **6–12 top-level categories.** Fewer than 6 is under-fitted; more than 12 is not a
  categorization. Sub-categories are allowed but only where the packet genuinely supports them.
- **Mutually exclusive, collectively exhaustive.** For every pair of adjacent categories,
  state the discriminating question that assigns a block to one and not the other.
- **Residual is data, not failure.** Report what did not fit and roughly what share it was.
  Do not inflate a category to absorb it.

## Return format

Return **only** a JSON object, no prose around it:

```json
{
  "categories": [
    {
      "id": "kebab-case-stable-id",
      "name_en": "…",
      "name_ko": "…",
      "definition": "one sentence: the job this block does for the agent",
      "includes": ["concrete criterion", "…"],
      "excludes": ["what belongs to <other-id> instead and why", "…"],
      "discriminators": ["question that separates it from its nearest neighbour"],
      "examples": [
        {"file_id": "owner/repo::AGENTS.md", "quote": "verbatim ≤200 chars"}
      ],
      "est_share_of_blocks": 0.00,
      "est_share_of_files_containing": 0.00
    }
  ],
  "residual": {"est_share": 0.00, "description": "…", "examples": ["…"]},
  "observations": [
    "anything about the corpus that a frequency table would not show: contradictions between files, conventions that appear to be copied, purposes that appear only in high-star files, etc."
  ]
}
```

`est_share_of_blocks` must sum with `residual.est_share` to ≈1.0. Estimate from what you
read; approximate is fine, invented precision is not.
