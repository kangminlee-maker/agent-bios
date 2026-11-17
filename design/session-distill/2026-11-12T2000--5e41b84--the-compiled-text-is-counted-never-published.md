---
created_at: 2026-11-12T20:00:00+09:00
head: 5e41b84
kind: review
supersedes: null
---

# The compiled instruction text is counted, never published: WP-11b review X round 1, finding (i)

The lead decided both questions (가): units with no match are published as counts with their reason and do not make
the layer incomplete, and the transcript-recorded copies of the same text follow the same rule (D-20261112-db6840). This record states
what S2 now publishes for the `session_injection` layer, what the unmatched units are on the checkout's catalogue,
and which readers the change reaches. It describes the tree at the commit that carries it, on `wp/11b-inventory`.

## What S2 publishes

- **A layer row.** A `session_injection` row publishes `units: 0`, `empty: false`, and a `withheld` block: the reason
  `owner_text_never_enters_a_run`, the would-be units, how many match a unit the same document publishes by text
  sha, how many match none, the unmatched by class, and the same counts per carrier version. The counts are taken
  while the text is in hand, before it is dropped. The text itself reaches no artifact.
- **The store.** A store version of that layer is listed by its identity, layer, path and length, with `split:
  withheld`, no unit references, and the same three counts against the units the store publishes. The text is
  never stored, whether it came from the snapshot or from a transcript occurrence. An occurrence keeps its place
  (pointer, ordinal, span), its manner (method) and its sha, as before. One rule applies to one text, whichever
  road it came by.
- **The fidelity check.** `withheld_problems` runs over every reference document and every shared inventory before
  anything is written. A withheld row must name the declared reason, publish no unit, be non-empty, and have counts
  that add up in total and over its carriers (`WITHHELD_INCONSISTENT`). A complete row with no unit, not empty and
  no withheld block is refused as complete-and-empty (`WITHHELD_UNNAMED`).
- **Context sets.** A segment's universe still lists the injected version by identity, but contributes none of its
  units, as the store holds none. Before this change, the injected body's own units were in its context set, and
  their mentions reached native carriers (R1#0). Now the mentions resolve only through the catalogue units that the
  matched units duplicate, which the pointed inventories hold. The unmatched units' mentions resolve nowhere.
- **The release index.** It accepts a withheld version as split: it was read and counted, so a complete row naming
  it stays complete.

## The unmatched units on the checkout's catalogue

The checkout catalogue at this tree has 2,007 units. The probe compiles its items with the shipped compiler into a
temporary directory, splits the text as S2 splits a `session_injection` carrier, and compares each unit's sha with
the catalogue's. It reads no owner data and makes no network call. The probe stays out of the tree:

```
python3 -B -I work/impl/wp11/probe-injection-match-2.py <tree>     # under the fake environment, env.sh
```

| Selection | Items | Would-be units | Matched | Unmatched |
| --- | ---: | ---: | ---: | ---: |
| always only | 77 | 79 | 77 | 2 |
| always, relevant and requested | 100 | 82 | 64 | 18 |

- **The 2:** the compiler's two headings, `# Activated private instructions` and `## Always in this environment`
  (class `reference`).
- **The 18:**
  - the same 2 headings;
  - 1 block that starts `Relevant procedures:`, the router line;
  - 15 catalogue rules whose text holds the state-root path, because the compiler rewrote their resource paths
    once the guides they name were selected.

  By class: 16 operative, 2 reference.
- **What is measured and what is assigned.** The counts are measured. The reason for each unmatched unit is
  assigned by a text criterion, not by tracing the compiler: a heading block; a block starting `Relevant
  procedures:`; a block holding the reference root. In that sense the split is partly an estimate. No unmatched
  unit differs from a catalogue unit by trailing whitespace alone; the probe checks this.
- **A correction.** An earlier reading of the 18 counted 13 path-rewritten rules, 1 router line and 2 requested
  lines. It was an estimate, and this classification replaces it.

## Where the total reaches a person

- S5 sums the current point's withheld counts into `checks.json`'s `absence` block (`withheld`), beside the
  completeness it already reports, and its report prints them.
- S6 carries the block into its sweeps section and prints a line beside the absence claims.
- The total is disclosed only; no threshold reads it. S5b's summary and S9's measurement section were the two
  places named, and neither reports reference-point completeness at this tree; S5 and S6 do.

## Readers of the text the store held

- **S5b `version_universe`.** It read a store unit's `text` for every version. An injection version's path is
  `snapshot:<ref>/output.json#instruction_text` or `<host>:session_injection:<pointer>`, which no read matches, so
  no binding changes.
- **S5b `native_events_of`.** It reads an injection event by its kind, not by its units.
- **S5's index and retrieval.** The `session_injection` layer now indexes nothing. A matched unit is retrieved
  through its catalogue twin. An unmatched unit cannot be retrieved, and that is the meaning of "cannot be judged
  at this reference point".
- **S6's packets and sweeps.** They follow S5.
- **S7 and S9.** They name the layer as a destination only.

No reader needs the bytes back from the views, and no file of lane L's changes.

## The controls

- **A planted fixture of its own.** It holds two catalogue rules and a compiled text with the compiler's two
  headings, the two rules and one compiled-only rule. Expected: 5 would-be units, 2 matched, 3 unmatched (1
  operative, 2 reference), with the same counts in the store. Each fidelity code is planted on its own copy.
- **The sentinel.** The planted run's compiled text, in its snapshot and in its transcript, carries a string no
  floor masks. It may appear in no S2 output: the store, `current.json`, `selection.json`, `sessions.json` and the
  selection inventories by name, then every other file the run wrote. The views are excluded by name, as the
  session's own record where the text lives. The control asserts the sentinel IS in the planted transcript, which
  is the record the views are made from, so the exclusion hides no empty subject.
- **Retargeted controls.** Those that asserted published injection units now assert the withheld rows, versions
  and counts: GA#0, M1, the recorded injection, R1#0, R1#1 and the run's injection carrier.
- **Revert trials.** The trial rows file is `rows-11c-i`; its results are in the commit message.
