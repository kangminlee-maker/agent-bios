---
created_at: 2026-11-04T19:45:00+09:00
head: 559d484
kind: design
supersedes: null
---

# An overlap omission keeps the role of the record it omits

WP-08, a small commit before merge. After ⑧ the lead asked who reads an overlap row's `context` role. The answer was
that only `views.expand` reads a row's `window_role`. While checking that, one defect showed up:
- `overlap_side` gave the entries the side's budget omits no `window_role`;
- `overlap_manifest` therefore defaulted their rows to `context`, even when the record is in a window.

S3 cannot reach this today, because it expands only a window's own rows (`SET_MISMATCH`). A later expansion of an
overlap row would still have carried `context` into evidence for an in-window record. The lead decided to fix it now
rather than backlog it. No model call and no decision record.

## Reproduction

`work/impl/wp08/c7/role-repro.py` ran on 559d484 over a transcript whose records are all in the window (31 records,
4 windows):
- every window's neighbour overlap omitted 5 or 6 records for its budget;
- each of their rows carried `context`, while each record's own role was `in_window`;
- `views.expand` on such a row, by its omission id, gave the expanded record `context`.

After the fix, the same run gives `in_window` both for the rows and for the expanded record.

## The change

An entry the budget omits now carries `"window_role": entry["window_role"]`, as a shown entry already does
(`overlap_of`). The `.get(..., "context")` defaults in `overlap_manifest` and `views.expand` remain in place. Every row
the stage writes now carries a role, so only a hand-built row can reach them.

**The controls** (views, 569 to 573):
- At the unit: the same seven entries, once as `context` and once as `in_window`, differ only in their role. The
  entries the side's budget omits must keep each case's role.
- A run of the control's own fixture, `fx_role_records`: every record is in a window, so no row is borrowed from
  another run.
  - Its guard: there is more than one window, and the budget omits records whose own role is `in_window`.
  - Each such row's role must equal the record's own role.
  - The record expanded from the first such row must carry that role too. A refusal is reported by name.

**The pretrial** (`c7/pt6-pretrial.py`):
- Unmutated, all six suites passed: views, stage_read, packet, evidence, claims, measures.
- With the fix's one line removed, the three role controls failed by name. There were no other failures and no
  traceback, and the guard did not fail.

## What moved

Nothing that a control pins:
- For the default golden and the dw2, apart and twin live-leg fixtures, every file S2 writes was compared with 559d484
  (86 files), and so was every rendered window (10). None differed (`c7/role-snap.py`). The comparison left out
  `at`, `started` and `ended`, which differ between any two builds.
- None of these four fixtures holds a budget-omitted overlap entry.
- The long-turn run's 12 overlap rows are `context` before and after, and none of them is owned by a window.

A window document's `overlap.omitted` entries gain one key wherever the budget omits an entry. That key reaches no
rendered packet, for two reasons:
- `render_window` renders only the shown overlap;
- a packet lists only the window's own omission rows (`stage_read.own_rows`).
