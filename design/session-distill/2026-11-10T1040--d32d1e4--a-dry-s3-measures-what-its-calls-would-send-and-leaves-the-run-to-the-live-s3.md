---
created_at: 2026-11-10T10:40:00+09:00
head: d32d1e4
kind: design
supersedes: null
---

# A dry S3 measures what its calls would send and leaves the run to the live S3

WP-08d, commit 2 (brief `work/lead/wp08d-brief.md`, defect 2). Pre-production stage A4 found the problem while it
prepared C2. S3 had no dry mode, so the work tool ran S3 with a stand-in runner that printed the argv and exited, under
realization golden. That run went through the whole stage: every unit failed, and S3 wrote `read-results.json`, its
read records and a `complete` record. The run then read as one S3 had finished. The tool's own guard refused the live
S3 after it, and a later stage would have been admitted over a dry run's results. The tool worked around this with a
clone of the run. S4's `--dry` already stops before its call and leaves its record `partial`
(`stage_form.run(dry=True)`).

## What lands

`stage_read.run(run_dir, dry=True)`, with no supervisor (`dry_run`):

- it is admitted as the stage is, over the same inputs (S2's views, S1's census and coverage state) and the ledger
  the declaration pins;
- every unit's views are checked as the reading checks them (`Reader.window_docs`, now shared): WINDOWLESS_VIEW,
  WINDOW_CAP_MISMATCH, VIEW_DRIFT;
- every window's packet is built under its first attempt's call id, as the dispatcher builds it: the window, the
  omissions with the full-source search's forced ones, and the expected observations due. Its driver bytes are
  measured with the schema (`bound.driver_bytes`) and held to the bound the window was cut against
  (`views.limits_of`, `bound.check_bound`). A window over it is WINDOW_OVER_BOUND, as the dispatcher refuses it;
- it writes `read-dry.json` and nothing else. That file holds each window's driver bytes, omissions and forced
  omissions, the bound, and the count of window calls with their total and largest bytes;
- it leaves S3's record `partial`.

The dry run writes no read record, store, `read-results.json` or `read.json`, and makes no reservation. So a stage
that reads S3's output refuses the run (INPUT_PARTIAL S3), and the live S3 reads it as if the dry run had not
happened. S3 without a supervisor and not dry is READ_UNSUPERVISED.

Expansions and stitches are not measured. What they send follows from the answers.

## Controls

stage_read self-test, on one golden run (`fx_reader`, every omission expanded):

- S3 without a supervisor is refused before admission, and no S3 record is written;
- the dry run makes no call and leaves the record `partial` with `read-dry.json` as its only output. It leaves no read
  record, store, `read-results.json` or `read.json`;
- it measures every window `views.json` lists, each within the bound;
- S4's admission over the dry run is INPUT_PARTIAL S3;
- the live S3 after it completes. Its stores are byte for byte those of a run with no dry before it, and it reuses
  nothing;
- the dry run's bytes for each window equal what the dispatcher recorded for that window's first attempt
  (`call.json` `bound.driver_bytes`);
- a window over the bound is WINDOW_OVER_BOUND, and a drifted window is VIEW_DRIFT, with the record `failed`.

The pretrial (`work/impl/wp08d/pt8d-pretrial.py`, rowset 2) reverts one fix per row:

- the record left `complete`;
- `read-results.json` left behind;
- the dry run falling through to the reading. It then fails at its first supervisor call, so the record is `failed`:
  S4's admission is INPUT_INVALID rather than INPUT_PARTIAL, and the drifted run fails before VIEW_DRIFT;
- no supervisor check;
- no bound check;
- the schema left out of the measure;
- the views read unchecked.

Every row is caught by exactly the controls it names and by no other, with no traceback; the module suite passes
unchanged.

`run_stage` never refused a second run of S3 over one directory: the refusal was the work tool's guard. So no single
revert makes the live run after a dry run fail. Its control is the positive half of the contract: the run is left
readable, and the live run's stores are a run's without the dry.

## Closed

- A dry run on an APFS clone of the run (`c2-run.sh s3 --dry`, stage A4). It measured the clone's packets through the
  stand-in runner and left the clone behind to delete. The work tools switch to `stage_read.run(dry=True)` on the run
  itself.
- A `distill.py read` command carrying only `--dry`. S3 has no command yet, and a command that could run only dry
  would be a second entry with half a contract; the dry run is reached where the live one is.

Revisit when S3 gets its command: `read --dry` then calls `run(dry=True)`, as `form --dry` calls S4's.
