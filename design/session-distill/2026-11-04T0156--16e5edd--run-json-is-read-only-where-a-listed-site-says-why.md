---
created_at: 2026-11-04T01:56:00+09:00
head: 16e5edd
kind: design
supersedes: null
---

# run.json is read only where a listed site says why

Three reviews found the same defect, one stage at a time: a stage read run.json on its own and then built from that
read, so an amendment landing between the read and the stage's admission produced output under a record of the newer
declaration. S2's views and S3 were moved onto `StageRun.declaration` after the X review's first round, and S1 after its
second (`2026-11-03T2347--19f06a9--…`). Each fix closed a site the review had found. None closed the shape. This commit
adds a structural guard, so a site the next change adds fails by name. The lead asked for it as commit 2c, after the
stitch (commit 3).

## What lands

| Piece | Where |
| --- | --- |
| The allowlist: each site that may read run.json, with its reason | `records.DECLARATION_READERS` |
| The sources it judges: every Python module of session-distill (`*.py`, `runlib/*.py`) | `records.declaration_texts` |
| The scan, by AST | `records.declaration_reads` |
| Its controls | `records.self_test`, run by the umbrella's records leg and so by the commit hook |

A site is a place where code names `run_json_path` or `declaration_state` (also under an alias it imported them as) or
holds the literal `"run.json"`. A site is keyed by module and top-level function. A class's method is keyed as
`Class.method`, and anything at module level as `<module>`. The guard has three failures, each by name:

- DECLARATION_READ_UNLISTED: a site no entry lists;
- DECLARATION_READ_STALE: an entry whose site no longer reads the declaration;
- DECLARATION_READ_UNSCANNED: a scan that found no module or no site.

On 16e5edd plus this change it scans 40 modules and finds 23 sites, every one listed. The groups are:

- records, the owner: five sites, one of them the guard's own `DECLARATION_FILE`;
- declare's three writers;
- S1's pre-admission read;
- dispatch's five call-time reads;
- the inventory's run marker;
- eight self-test and fixture sites.

The reasons live in the allowlist and are not restated here.

## Choices made here

1. **A self-test control, not a new umbrella leg.** The records leg already runs in the umbrella and the commit hook.
   The census's READER_BYPASS guard has the same shape, a scan of the real tree plus planted controls in its module's
   self-test, so the two read alike.
2. **The owner is `records`.** It owns `run_json_path`, `declaration_state` and `run_stage`, so the list of who may
   bypass `run_stage` sits beside them.
3. **Every Python module of session-distill is scanned, not only the new pipeline.** The pipeline beside `distill.py`
   has no site today. Scanning it costs nothing, and a read added there is judged like any other.
4. **A call's admission is not a stage's build.** Dispatch reads the declaration current when a call is reserved,
   admitted, stopped or asked for its remaining budget. Those reads are listed. They decide whether a call may be
   spent, and no stage builds output from them.

## What the guard does not see

- A read spelled some other way: `getattr` with a built name, or a path joined from pieces.
- What a listed site hands to its caller. Of the listed sites:
  - `declaration_state` returns the declaration, and each of its callers is a site by name;
  - `run_stage` yields it as `StageRun.declaration`, which is the route stages are meant to use;
  - `declare.set_fields` returns what it wrote, to `distill.py`'s command handler;
  - `Supervisor.remaining` returns a number.

  So no listed site hands the declaration to a stage's build. A new listed site that does would need its reason to say
  so.

## Controls (records self-test)

- Positive, on the real tree:
  - no violation;
  - the sites equal the allowlist;
  - the modules include `distill.py`, `census.py` and `runlib/records.py`, one from each pattern.
- A pre-admission read planted three ways at the start of a stage's `run` is named:
  - `records.run_json_path` in S2;
  - the literal path in S3;
  - `declaration_state` under an imported alias in S2.
- S1's entry removed: its read is named UNLISTED.
- An entry for a site that does not read: named STALE.
- No modules (an empty root), and modules with no site: each named UNSCANNED.

The pretrial (`work/impl/wp08/c2c/c2c-revert.py`, author-side) reverts each piece of the scan and its three failures in
turn. It also plants a read in the real S2 and S3, removes an entry in the real allowlist, and narrows the scope to drop
the pipeline modules. Each row must fail its control by name, and the unmutated records suite must pass.
