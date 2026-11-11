---
created_at: 2026-11-11T03:30:00+09:00
head: 180e352
kind: design
supersedes: null
---

# The middles a window's reading skipped are read by one gather, or named where they are not

WP-08e, commit 2 of 2. Lead decision D-20261111-360c9b, WP-08e's stage 0 answer Q3 (the first of its three options,
the gather). This record amends
WP-08c's omission record (`2026-11-06T0426--5665f77--a-references-name-is-read-as-written-and-a-character-cut-keeps-a-line-end-whole.md`)
and the skip policy before it, by a new record only.

## What C2 shows

The Codex child's first window (window 8) owned five clipped tool results, none forced (no pending event, no search
match): 5,938, 4,121, 4,102, 7,117 and 4,167 characters, of which 3,938, 2,121, 2,102, 5,117 and 2,167 - 15,445 in
all - were the omitted middles. The reading skipped all five. The recall judge found four of the window's seven
important items not covered and said the skipped record mattered, which is the rule A3 states. Of the four, only one
(A3) lies on a skipped record; three (A4 to A6) lie on records the window showed whole, and the item on the largest
skipped record (A8) was covered. A gather addresses the class of item that lies in a skipped middle; it does not
address how well a window reads what it is shown.

## The rule

- **One gather a window.** When an accepted window's answer skips omissions of its own records - forced_by `none`,
  since a forced one cannot be skipped - S3 makes one gather of that window (`Reader.file`): the skipped middles,
  each re-read from the projection and checked against its hash as an expansion's middle is (`views.omitted_middle`,
  now shared with `expansion_windows`), in the order the window lists them, with no record's neighbours, cut into
  windows of their own under the view's bound (`views.gather_windows`; a gather too large for one window is cut into
  several) and written beside the view (`views.gather`, `gather-<call>-<n>.json`). Each is read with the window
  template as an expansion is, its claims and events kept and stitched as an expansion's; an occasion it reads is of
  the expansion side when readings of a record are settled.
- **Its own class.** A gather is the class `gather` (`dispatch.class_key(S3, seat, "gather")`), never the window's,
  so a sample of one says nothing of the other. Like any class it is provisional until five are measured, and a
  provisional class dispatches only in a calibration tranche; in a broad tranche S3 does not reserve it and names the
  gather `gather_deferred: calibration` instead of refusing the unit.
- **Named where it does not read.** A gather that did not read its middles leaves its reason: `gather_deferred:
  budget` when the stage's remaining budget cannot hold its reservation (the dispatcher records it not done),
  `gather_deferred: provider` when the provider deferred it (the unit is deferred, as for any deferred call),
  `gather_failed` when it failed. The reason stands on the window's row (`gather`: omissions, windows, gathered,
  reason), on the file (`not_gathered`), and on the coverage basis: `observation_scope` names each session read view
  complete and not source complete with why, and `observations/resolutions.json` carries it as `not_source`. The skip
  itself stays in `expansions.jsonl` as the reading decided it.
- **Completeness.** An omission a gather read is no longer skipped for the source (`views.completeness`'s
  `gathered`): a file whose every skipped middle was gathered is source complete, and its basis can be `source`. One
  not gathered keeps the file at `view`.
- **The dry.** Each window with omissions not forced carries `gather_if_skipped`, the gather it would make were every
  one of them skipped, its windows measured as the window's are, at the density of the host's gather calls (the floor
  where none is measured); `estimate.gathers` sums them. It is the most the windows can ask for: an omission a reading
  expands is not gathered.

## Cost

On C2's numbers a gather of window 8 is about 29k driver bytes, about 15k input tokens at that window's measured
density, one call. Forcing the five expansions instead would have been five calls and 60-70k input; cutting a smaller
window for dense text about 11k more input and no reading of the middles. C2's other windows skipped fewer and shorter
middles.

## What follows from "provisional until measured"

The gather class has its own calibration, and calibration samples are the run's own. A broad S3 in a run that has not
measured five gathers defers every gather by name, so the middles stay skipped and named, and the basis stays `view`.
A run that should read them runs S3 in a calibration tranche, as C2 did, or measures five gathers first.

## Controls

Each fails by name when its fix alone is reverted (pretrial rows `c2-*`, 11 rows, all caught; with the provisional
check reverted, 34 other controls fail too, since every broad fixture that skips would be refused):

- every middle a window's reading skipped is read by that window's gather - calls of the gather class, accepted,
  claims kept - and the file is source complete, nothing skipped or named, the basis `source`;
- a gather the budget cannot hold is recorded not done, its middles stay skipped and named `gather_deferred: budget`
  on the window, the file and the coverage basis, which is `view`;
- a gather of a class not yet measured is not dispatched in a broad tranche, named `gather_deferred: calibration`,
  and the unit is still read;
- the dry estimates the gather of each window with omissions not forced, at the gather class's density, its basis
  named.

## What this does not establish

- That a gather reads a middle as well as an expansion does: it shows the middles without their records' heads,
  tails or neighbours, which the window that skipped them showed.
- A gather's live cost or density: no gather has run live; its class reads at the floor until one does.
- Whether window 8's A3 would be covered: that is C3's to measure.
