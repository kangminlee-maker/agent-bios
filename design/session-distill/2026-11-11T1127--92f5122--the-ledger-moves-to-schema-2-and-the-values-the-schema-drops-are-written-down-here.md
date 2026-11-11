---
created_at: 2026-11-11T11:27:00+09:00
head: 92f5122          # the commit the content was true at
kind: design
supersedes: none
---

# The ledger moves to schema 2, and the values the schema drops are written down here

`design/session-distill/ledger.json` moved from schema 1 to schema 2 in the WP-22a cutover commit,
by `session-distill/migrate-ledger.py --apply --removed <file>`. The migration is deterministic and
this record is the other half of it: the schema removes four kinds of value, this module is their
only source, and after the write they exist nowhere else. `--apply` refuses to run without a place
to put them for exactly that reason.

## What the file is now

| | |
| --- | --- |
| entries before / after | 267 / 267 |
| entry ids | identical, in the same order |
| windows | 4, from the schema 1 chain string |
| removed-value rows | 268 (one per entry, plus `_ledger` for the chain), holding 782 values |
| status renames | one: `G-7` `incubating-G` → `incubating` |
| classification types | identical: A 3, B 36, C 28, D 49, F 7, G 13, unclassified 131 |

The one status rename is not a loss. `G-7` carries a `decisions[]` element of kind
`legacy_migration` with `legacy_text: "incubating-G"` and `legacy_status: "incubating"`, and its
`classification.type` is `"G"`, so the schema 1 status is recoverable from the schema 2 record.

## What today's readers make of it

The ledger's two reader layers were run over the schema 1 file and over its migration by the
shipped reader, `runlib/inventory.py::ledger_carriers`:

| layer | schema 1 | schema 2 | outcome |
| --- | --- | --- | --- |
| `ledger_incubating` | 142 carriers | 142 carriers | same refs, same text; one carrier's provenance differs |
| `ledger_keep` | 0 carriers | 0 carriers | same, and vacuous |

The one provenance difference is `G-7`'s `status`, which is the rename above, read straight off the
entry. No carrier appeared, disappeared or changed its text.

**The real ledger has no `keep` record today**, under either schema. A census over this file
therefore cannot witness that the migration preserves the keep layer: both answers are empty, and
they agree because there is nothing to agree about. That layer is judged instead on a fixture pair
in `migrate-ledger.py --self-test` — a schema 1 ledger carrying one standing keep record and two
held back for different reasons, migrated, and read by the same shipped reader, where the carriers,
their text, their provenance and the held-back list must match row for row. A control whose subject
is an empty list is not a control, and this is the shape that says so out loud.

Building that pair found two real defects, both invisible while the layer was empty:

- **`keep` was named by no row of the §12.2 field table**, so the migration stopped with
  `FIELD_UNMAPPED` on any entry carrying one — while schema 2 *requires* `keep` on every entry
  (`schemas/ledger.schema.json`, `keep_record`, nullable) and a schema 1 keep record already has
  that exact shape. It is a pass-through now, in `KEPT_FIELDS` and in the assembled record, with the
  fixture pair as its control. Nothing in the committed ledger changed as a result: every entry's
  `keep` was and is null.
- **`reason`, the rationale a schema 1 keep row carries, had no home in schema 2** — an entry
  forbids additional properties, so a pass-through would have built a record the validator rejects,
  and `runlib/inventory.py` was reading `entry.get("reason")` into a keep carrier's provenance for
  both schemas, which is null for every schema 2 ledger. Its home is the keep record
  (`keep_record.reason`, optional; lead decision D-20261111-148ee5): the reader takes it from
  `entry["keep"]["reason"]` and never from the entry, and the migration maps the schema 1 field
  into the record. An entry carrying the rationale with **no** keep record to hold it is still
  refused by name, because there is then nothing to carry it.

  That choice makes one asymmetry, and it is deliberate: under schema 1 the rationale sits on the
  entry, which the reader no longer looks at, so a schema 1 ledger's keep carrier has no rationale
  until the migration moves it. The alternative — reading the entry for schema 1 only — is the
  shape that produced the defect. The fixture pair therefore carries no rationale, so "the same
  outcome on both schemas" keeps its meaning, and the rationale's move has a control of its own:
  null under schema 1, the sentence under schema 2.

## The four window rows, exactly as derived

`windows[]` is the schema 1 chain string parsed oldest first, and nothing more:

```json
[{"start": "2026-06-27", "end": "2026-07-18", "run_id": "legacy-2026-07-18", "kind": "legacy", "commit": null, "accounted": null, "fully_read": null},
 {"start": null, "end": "2026-08-25", "run_id": "legacy-2026-08-25", "kind": "legacy", "commit": null, "accounted": null, "fully_read": null},
 {"start": null, "end": "2026-09-09", "run_id": "legacy-2026-09-09", "kind": "legacy", "commit": null, "accounted": null, "fully_read": null},
 {"start": null, "end": "2026-09-22", "run_id": "legacy-2026-09-22", "kind": "legacy", "commit": null, "accounted": null, "fully_read": null}]
```

They stay `kind: legacy` with a null commit, and no hand-written row joins them. The redesign's runs
are not windows of the v1 process, and the new driver writes its own window rows when its runs
actually apply (S11). Only the first has a `start`, because only the first chain link states a day
count (`census 21d ending 2026-07-18`).

## The values the schema removes

`verdict`, `strength` and `criteria` are gone from the entry. `criteria` also became
`consequence.kinds`, so it is the one value with a home in the new record as well; `verdict` and
`strength` have none. The chain string is under `_ledger`. 267 entry rows, verbatim as the migration
returned them:

```json
{
 "S4-01": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "quality_lever", "rare_high_cost"]},
 "S4-02": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S4-03": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S4-04": {"verdict": "partial", "strength": 4, "criteria": ["rare_high_cost", "recurrent_error", "quality_lever"]},
 "S4-05": {"verdict": "partial", "strength": 4, "criteria": ["recurrent_error", "quality_lever", "re_exploration"]},
 "S4-06": {"verdict": "novel", "strength": 4, "criteria": ["rollback", "quality_lever", "recurrent_error"]},
 "S4-07": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "rare_high_cost", "quality_lever"]},
 "S3-01": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-02": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "recurrent_error"]},
 "S3-03": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-04": {"verdict": "novel", "strength": 4, "criteria": ["rollback", "re_exploration"]},
 "S3-05": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "recurrent_error"]},
 "S3-06": {"verdict": "novel", "strength": 4, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-07": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-08": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-09": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-10": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-11": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-12": {"verdict": "novel", "strength": 3, "criteria": ["quality_lever", "re_exploration"]},
 "S3-13": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "quality_lever"]},
 "S3-14": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-15": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-16": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-17": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-18": {"verdict": "novel", "strength": 3, "criteria": ["quality_lever", "re_exploration"]},
 "S3-19": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-20": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-21": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "quality_lever"]},
 "S3-22": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "quality_lever"]},
 "S3-23": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "high_token"]},
 "S3-24": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-25": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-26": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "high_token"]},
 "S3-27": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-28": {"verdict": "novel", "strength": 3, "criteria": ["high_token", "rare_high_cost"]},
 "S3-29": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-30": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-31": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "recurrent_error"]},
 "S3-32": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-33": {"verdict": "novel", "strength": 3, "criteria": ["quality_lever", "rare_high_cost"]},
 "S3-34": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-35": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "re_exploration", "quality_lever"]},
 "S3-36": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-37": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost", "quality_lever"]},
 "S3-38": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-39": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "recurrent_error", "rare_high_cost", "quality_lever"]},
 "S3-40": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "recurrent_error", "quality_lever"]},
 "S3-41": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S2-01": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S2-02": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-03": {"verdict": "novel", "strength": 2, "criteria": ["quality_lever"]},
 "S2-04": {"verdict": "partial", "strength": 4, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-05": {"verdict": "novel", "strength": 2, "criteria": ["rare_high_cost", "quality_lever"]},
 "S2-06": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "recurrent_error"]},
 "S2-07": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error"]},
 "S2-08": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-09": {"verdict": "novel", "strength": 2, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S2-10": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-11": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-12": {"verdict": "novel", "strength": 2, "criteria": ["rollback", "recurrent_error", "high_token"]},
 "S2-13": {"verdict": "novel", "strength": 2, "criteria": ["quality_lever", "re_exploration"]},
 "S2-14": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-15": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-16": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S2-17": {"verdict": "novel", "strength": 2, "criteria": ["rollback"]},
 "S2-18": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-19": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S2-20": {"verdict": "novel", "strength": 2, "criteria": ["quality_lever"]},
 "S2-21": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-22": {"verdict": "novel", "strength": 2, "criteria": ["quality_lever"]},
 "S2-23": {"verdict": "novel", "strength": 2, "criteria": ["recurrent_error", "quality_lever", "rare_high_cost"]},
 "S2-24": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error", "re_exploration"]},
 "S2-25": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-26": {"verdict": "novel", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "G-1": {"verdict": "principle", "strength": null, "criteria": []},
 "G-2": {"verdict": "principle", "strength": null, "criteria": []},
 "G-3": {"verdict": "principle", "strength": null, "criteria": []},
 "G-4": {"verdict": "principle", "strength": null, "criteria": []},
 "G-5": {"verdict": "principle", "strength": null, "criteria": ["rollback"]},
 "G-6": {"verdict": "principle", "strength": null, "criteria": ["rollback"]},
 "G-7": {"verdict": "principle", "strength": null, "criteria": ["rollback"]},
 "G-8": {"verdict": "principle", "strength": null, "criteria": ["rollback"]},
 "L-01": {"verdict": "novel", "strength": 1, "criteria": ["rare_high_cost", "quality_lever"]},
 "S4-08": {"verdict": "partial", "strength": 4, "criteria": ["recurrent_error", "rollback", "rare_high_cost", "quality_lever"]},
 "S4-09": {"verdict": "partial", "strength": 4, "criteria": ["recurrent_error", "quality_lever"]},
 "S4-10": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "rollback", "rare_high_cost", "re_exploration"]},
 "S4-11": {"verdict": "partial", "strength": 4, "criteria": ["rare_high_cost", "quality_lever"]},
 "S4-12": {"verdict": "partial", "strength": 4, "criteria": ["rare_high_cost"]},
 "S4-13": {"verdict": "partial", "strength": 4, "criteria": ["recurrent_error", "re_exploration", "rare_high_cost", "quality_lever"]},
 "S4-14": {"verdict": "partial", "strength": 4, "criteria": ["rare_high_cost", "rollback"]},
 "S4-15": {"verdict": "partial", "strength": 4, "criteria": ["rollback", "high_token", "rare_high_cost", "recurrent_error"]},
 "S4-16": {"verdict": "partial", "strength": 4, "criteria": ["high_token", "rollback", "recurrent_error"]},
 "S4-17": {"verdict": "partial", "strength": 4, "criteria": ["rollback", "recurrent_error", "quality_lever"]},
 "S4-18": {"verdict": "partial", "strength": 4, "criteria": ["rollback", "quality_lever", "rare_high_cost", "recurrent_error"]},
 "S4-19": {"verdict": "partial", "strength": 4, "criteria": ["quality_lever", "high_token", "re_exploration", "rollback"]},
 "S4-20": {"verdict": "partial", "strength": 4, "criteria": ["rare_high_cost", "re_exploration", "quality_lever"]},
 "S4-21": {"verdict": "partial", "strength": 4, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-42": {"verdict": "novel", "strength": 3, "criteria": ["quality_lever", "rollback"]},
 "S3-43": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback", "quality_lever"]},
 "S3-44": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "quality_lever", "rollback"]},
 "S3-45": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rare_high_cost", "recurrent_error"]},
 "S3-46": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "recurrent_error"]},
 "S3-47": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rollback", "recurrent_error"]},
 "S3-48": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rare_high_cost", "quality_lever"]},
 "S3-49": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost", "quality_lever"]},
 "S3-50": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "recurrent_error", "quality_lever"]},
 "S3-51": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "quality_lever", "rollback"]},
 "S3-52": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-53": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "re_exploration"]},
 "S3-54": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "high_token"]},
 "S3-55": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever"]},
 "S3-56": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-57": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-58": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-59": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-60": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "quality_lever"]},
 "S3-61": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "rollback"]},
 "S3-62": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "re_exploration"]},
 "S3-63": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-64": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-65": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback"]},
 "S3-66": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rare_high_cost"]},
 "S3-67": {"verdict": "novel", "strength": 3, "criteria": ["re_exploration", "recurrent_error"]},
 "S3-68": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-69": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "quality_lever"]},
 "S3-70": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-71": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-72": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rollback"]},
 "S3-73": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "high_token"]},
 "S3-74": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rare_high_cost", "quality_lever"]},
 "S3-75": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback"]},
 "S3-76": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-77": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "recurrent_error"]},
 "S3-78": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-79": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-80": {"verdict": "partial", "strength": 3, "criteria": ["re_exploration", "quality_lever"]},
 "S3-81": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "rollback"]},
 "S3-82": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "quality_lever"]},
 "S3-83": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "quality_lever"]},
 "S3-84": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever", "recurrent_error"]},
 "S3-85": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-86": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "recurrent_error"]},
 "S3-87": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-88": {"verdict": "novel", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-89": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-90": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "rollback"]},
 "S3-91": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-92": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-93": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "high_token"]},
 "S3-94": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rollback"]},
 "S3-95": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-96": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-97": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-98": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-99": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback", "rare_high_cost"]},
 "S3-100": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-101": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-102": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rare_high_cost"]},
 "S3-103": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error"]},
 "S3-104": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-105": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-106": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever", "high_token"]},
 "S2-27": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-28": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error"]},
 "S2-29": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "quality_lever"]},
 "S2-30": {"verdict": "partial", "strength": 2, "criteria": ["high_token", "rollback"]},
 "S2-31": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "re_exploration"]},
 "S2-32": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-33": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-34": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost"]},
 "S2-35": {"verdict": "partial", "strength": 2, "criteria": ["high_token", "re_exploration"]},
 "S2-36": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-37": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "recurrent_error"]},
 "S2-38": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "high_token"]},
 "S2-39": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-40": {"verdict": "novel", "strength": 2, "criteria": ["rare_high_cost", "rollback"]},
 "S2-41": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-42": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-43": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-44": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost"]},
 "S2-45": {"verdict": "partial", "strength": 2, "criteria": ["high_token", "quality_lever"]},
 "S2-46": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-47": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-48": {"verdict": "partial", "strength": 2, "criteria": ["re_exploration", "rare_high_cost"]},
 "S2-49": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-50": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "re_exploration"]},
 "S2-51": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error", "quality_lever"]},
 "S2-52": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-53": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "rollback"]},
 "S2-54": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-55": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-56": {"verdict": "partial", "strength": 2, "criteria": ["re_exploration"]},
 "S2-57": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-58": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-59": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-60": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "high_token"]},
 "S2-61": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "rollback"]},
 "S2-62": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-63": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "rare_high_cost"]},
 "S2-64": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost"]},
 "S2-65": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-66": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-67": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-68": {"verdict": "novel", "strength": 2, "criteria": ["rollback", "recurrent_error"]},
 "S2-69": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "re_exploration"]},
 "S2-70": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-71": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-72": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "recurrent_error"]},
 "S2-73": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-74": {"verdict": "partial", "strength": 3, "criteria": ["rollback"]},
 "S2-75": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rare_high_cost"]},
 "S2-76": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-77": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-78": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-79": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-80": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-81": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-82": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-83": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error"]},
 "S2-84": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-85": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost"]},
 "S2-86": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-87": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "G-9": {"verdict": "principle", "strength": null, "criteria": []},
 "G-10": {"verdict": "principle", "strength": null, "criteria": []},
 "G-11": {"verdict": "principle", "strength": null, "criteria": []},
 "G-12": {"verdict": "principle", "strength": null, "criteria": []},
 "S4-22": {"verdict": "novel", "strength": 4, "criteria": ["recurrent_error", "re_exploration", "quality_lever", "high_token"]},
 "S4-23": {"verdict": "partial", "strength": 4, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S4-24": {"verdict": "partial", "strength": 4, "criteria": ["quality_lever", "rollback", "high_token"]},
 "S4-25": {"verdict": "partial", "strength": 4, "criteria": ["rollback", "re_exploration", "rare_high_cost"]},
 "S3-107": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback", "recurrent_error", "re_exploration"]},
 "S3-108": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rare_high_cost"]},
 "S3-109": {"verdict": "novel", "strength": 3, "criteria": ["rollback", "rare_high_cost"]},
 "S3-110": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "recurrent_error"]},
 "S3-111": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rollback"]},
 "S3-112": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S3-113": {"verdict": "partial", "strength": 3, "criteria": ["high_token", "rollback", "quality_lever"]},
 "S3-114": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "rare_high_cost"]},
 "S3-115": {"verdict": "novel", "strength": 3, "criteria": ["rare_high_cost"]},
 "S3-116": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever"]},
 "S3-117": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-118": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "rare_high_cost", "quality_lever", "high_token"]},
 "S3-119": {"verdict": "partial", "strength": 3, "criteria": ["rare_high_cost", "quality_lever"]},
 "S3-120": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "recurrent_error", "rare_high_cost"]},
 "S3-121": {"verdict": "partial", "strength": 3, "criteria": ["quality_lever", "rare_high_cost", "rollback"]},
 "S2-88": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "rollback", "quality_lever"]},
 "S2-89": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error", "quality_lever"]},
 "S2-90": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-91": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "re_exploration"]},
 "S2-92": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "quality_lever"]},
 "S2-93": {"verdict": "partial", "strength": 2, "criteria": ["re_exploration", "quality_lever"]},
 "S2-94": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost"]},
 "S3-122": {"verdict": "partial", "strength": 3, "criteria": ["recurrent_error", "re_exploration", "quality_lever"]},
 "S3-123": {"verdict": "partial", "strength": 3, "criteria": ["rollback", "quality_lever"]},
 "S2-95": {"verdict": "partial", "strength": 2, "criteria": ["rare_high_cost", "rollback"]},
 "S2-96": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever"]},
 "S2-97": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-98": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-99": {"verdict": "partial", "strength": 2, "criteria": ["recurrent_error"]},
 "S2-100": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "quality_lever"]},
 "S2-101": {"verdict": "partial", "strength": 2, "criteria": ["rollback", "rare_high_cost"]},
 "S2-102": {"verdict": "partial", "strength": 2, "criteria": ["rollback"]},
 "S2-103": {"verdict": "novel", "strength": 2, "criteria": ["quality_lever", "re_exploration"]},
 "S2-104": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "recurrent_error"]},
 "S2-105": {"verdict": "partial", "strength": 2, "criteria": ["quality_lever", "rollback"]},
 "S2-106": {"verdict": "partial", "strength": 2, "criteria": ["high_token", "rollback", "re_exploration"]}
}
```

And the ledger's own removed value:

```json
{"_ledger": {"window": "census ending 2026-09-22 (previous: census ending 2026-09-09 (previous: census ending 2026-08-25 (previous: census 21d ending 2026-07-18)))"}}
```

## How to read it back

```bash
python3 session-distill/migrate-ledger.py --check        # a schema 2 ledger must be its own migration
python3 gates/check-ledger.py --check                    # the gate suite's leg, against the index
python3 session-distill/migrate-ledger.py --self-test    # the mapping rules, the apply path, the keep pair
```

`--apply` is idempotent: run against this file again it reports `already schema 2` and writes
nothing, so the migration cannot be performed twice.
