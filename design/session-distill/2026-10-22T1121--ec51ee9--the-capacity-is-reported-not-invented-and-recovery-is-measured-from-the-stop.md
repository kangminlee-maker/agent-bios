---
created_at: 2026-10-22T11:21:00+09:00
head: ec51ee9
kind: design
supersedes: 2026-10-22T1018--acdec41--the-bound-has-one-owner-and-the-dispatcher-is-its-boundary.md
---

# The capacity is reported, not invented, and recovery is measured from the stop

The seam's first hermetic review (BA#0–BA#6). The consolidation held; three of its pieces were wrong
in ways that matter, and four controls were weaker than they read.

## BA#0 — recovery is measured from where the stop was committed

The excess record carried the sequence the **call** was reserved under. So a `host_allowance`
amendment recorded *while the call was still running* — before anybody could know the host had
changed — lifted the stop that call then caused. An amendment cannot be a re-measurement of something
that has not happened yet.

The sequence is now read where the stop is **committed**, under the same lock, as the latest the
declaration has reached at that moment (`bound.committed`, stamped inside `_stop_run`). Recovery
needs a `host_allowance` amendment strictly after it. `bound.excess` no longer carries a sequence at
all, and an unstamped record lifts for nothing — a control asserts both.

## BA#1 — no invented capacity, and the invented one was also wrong

Check (d) substituted `CONTEXT_CAPACITY = 200_000` when the seat declared none. The reviewer found
that number has no source. It is also **false**: every live Claude result in WP-03v reports
`modelUsage["claude-sonnet-5-5"].contextWindow = 1000000` (with `maxOutputTokens` 128000) on host
2.1.304 — read back from `/Users/Shared/agent-bios-probe-cells/wp03v/dw5/fix-judge.json`'s
`call_dir/result.json` before being written here.

So the seat's context window is **declared evidence**, in `seats.json`'s new `seat_capacity` block:
per seat, with its host version and the basis it came from. `gate.seat_capacity` is its only reader
and refuses an entry with no basis, a non-positive number, or another host version.

* a view-window call on a seat with no declared capacity is refused **`CAPACITY_UNDECLARED`**;
* cutting a window reads the **same** declaration — `views.limits_of` has no capacity default either,
  and refuses by the same name;
* the gate compares the declared capacity against the host's own `contextWindow` in a Claude result
  and fails **`CAPACITY_DRIFT`** per call, so a stale declaration is caught on the next call rather
  than at the next review.

Codex seats carry **no** entry: no capture reports one. That means a Codex view-window call is
refused today, which is correct and is itself controlled against the real file. The self-test's seat
copies declare their own capacity and say in the basis that it is not a measurement.

**The output reservation had the same defect, and the lead ruled on it in the same round.** There is
no constant: the reservation in (d) is **this call's own declared output cap** (`max_output_tokens`),
what the call reserved for its answer — not the host's reported `maxOutputTokens` of 128000, which is
what the host would allow. So `OUTPUT_RESERVATION` and `CONTEXT_CAPACITY` are **deleted** from
`bound.py`, and `bound.limits` takes both as keyword-only arguments with no defaults, so neither
reader can fall back on a number nobody chose. A view-window call that declares no positive cap is
refused `CAP_UNDECLARED` before admission **on any host** (it was Claude-only before). Window cutting
uses the same number: `views.limits_of` and `views.run` have no reservation default and refuse by the
same name, and `distill.py views` takes `--output-cap` as a required flag — there is no slot in the
declaration for a stage's output cap today, so the caller that makes the call states it, exactly as
the dispatcher's caller does. When WP-08 gives it a declared home, both read that declaration.

Two controls carry the shape, and the only thing that moves between them is the cap: the same window
under a declared narrow capacity is admitted with a cap that leaves room for the answer and refused
`WINDOW_CAPACITY_EXCEEDED (d)` with one that does not. A third refuses a view-window call that
declares no cap, and `bound.py` fails if `limits` grows a default for either argument or if a
module-level constant for either comes back.

With a 1,000,000-token capacity, (d) cannot bind on the S3 seat at a 120k bound. That is a real rule
whose seat makes it non-binding, not a dead one: the control plants a narrow capacity through the
same declaration to exercise it.

## BA#2 — one representation for a declared driver part

No non-empty appended prompt could satisfy both the payload counter (which needed content) and
`CALL_SCHEMA` (which allowed only a name and a hash). A part is now declared by its **content** —
`text`, or a `path` to read — counted from those bytes, and **recorded** as its `sha256` and `bytes`
(`bound.part_evidence`, `bound.declared_evidence`, written into the call's manifest by the
dispatcher). The schema accepts that shape for instructions and appended prompts alike. A part that
only asserts a number is not evidence of anything and is refused.

## BA#3–BA#6 — the controls that read stronger than they were

* **BA#3**: the ownership check scanned the module's text, which its own controls satisfied. It now
  reads `bound.<name>` call sites out of the **Supervisor class's AST**, and one control per delegated
  function proves the check fails when that delegation is inlined (eight of them).
* **BA#4**: recovery only proved a reservation was granted. The recovered call is now **dispatched**
  through the fake runner — as the non-window call design §8.6 says an R-authoring call is — with its
  launch counted and `gate.accept` passing.
* **BA#5**: the producer's guarantee is asserted on calls just made: a window call and a non-window
  call must each record the complete `bound` block, with the byte count the boundary counted and the
  declared capacity; omitting a field fails the control, and a legacy record without the block stays
  schema-valid.
* **BA#6**: `module-docstring-lists-the-same-refusals` was dropped when the inventory block was
  rewritten. Restored beside the updated scan.

Two places needed the same care as last round: a concurrency bug I introduced and then removed —
admission facts briefly travelled on `self`, which twelve concurrent calls would have clobbered, and
they now travel as a return value — and the gate-acceptance half of BA#2, which belongs in `gate.py`
because the golden fake host appends nothing, so the dispatch-side control asserts every leg **but**
the unobserved-context one, by name, and `gate.py` holds the matching pair.

## Where it is proven

| Finding | Controls | Where |
| --- | --- | --- |
| BA#0 | `BA#0-the-stop-is-stamped-with-the-sequence-the-commit-read-not-the-call-s`, `BA#0-an-amendment-between-the-reservation-and-the-stop-does-not-lift-it`, `control, BA#0: an uncommitted excess record carries no sequence…`, `control, BA#0: the sequence a stop is stamped with…` | `dispatch.py`, `bound.py` |
| BA#1 | `a-view-window-call-on-a-seat-with-no-declared-capacity-is-refused`, `a-non-window-call-on-the-same-seat-needs-no-capacity`, four `a-seat-capacity-…-is-no-capacity` rows, `the-checkout-declares-the-S3-seat-s-host-reported-capacity`, `the-checkout-leaves-every-codex-seat-undeclared`, `control, BA#1: a seat seats.json declares no context capacity for cuts no window`, `BA#1: the S3 seat's capacity is the host-reported one…`, `a-call-admitted-against-the-capacity-the-host-reports-is-accepted`, `a-call-admitted-against-a-capacity-the-host-contradicts-fails-the-gate`, `a-host-that-reports-no-context-window-is-no-drift` | `dispatch.py`, `views.py`, `gate.py` |
| BA#2 | `an-appended-prompt-is-recorded-as-its-hash-and-the-length-counted`, `the-recorded-length-is-inside-the-counted-driver-payload`, `a-call-carrying-an-appended-prompt-passes-every-gate-leg-but-the-unobserved-context`, `an-oversized-appended-prompt-is-refused-before-dispatch`, `appended-prompt-declared-with-its-counted-length`, and five `BA#2:` rows in `bound.py` | `dispatch.py`, `gate.py`, `bound.py` |
| BA#3 | `the-bound-helpers-have-a-caller-in-the-supervisor`, `removing-the-delegation-of-<name>-is-detected` × 8 | `dispatch.py` |
| BA#4 | `BA#4-the-recovered-call-is-launched-and-accepted`, `BA#4-the-recovered-call-records-the-bound-block-with-the-stop-no-longer-standing` | `dispatch.py` |
| BA#5 | `a-new-window-call-records-the-complete-bound-block`, `a-new-non-window-call-records-the-complete-bound-block`, `a-call-record-with-the-bound-block-omitted-fails-the-producer-control`, `a-legacy-call-record-without-a-bound-block-is-still-schema-valid` | `dispatch.py` |
| BA#6 | `module-docstring-lists-the-same-refusals` | `dispatch.py` |

Counts after both rounds: `bound` (new), `views` 530, `dispatch` 258, `gate` 192, `distill` 57.

## Two notes about this commit

**The rounds are mixed, deliberately.** The BA#0–BA#6 commit was refused by the hook (the gate failure
below) and never landed, and the output-cap ruling arrived while its files were still being edited. The
two rounds now share hunks in `bound.py`, `dispatch.py`, `gate.py` and `views.py`, and separating them
would mean splitting hunks by hand — so this is one commit, as the lead allowed.

**The gate failure that refused the first attempt, and its fix.** Making `bytes` a *required* property
of an appended-prompt item broke a scenario outside this lane: `FAIL: claude-run through the gate,
declared appended prompt … 'bytes' is a required property`. The field is now **optional**, for the same
reason the `bound` block is: a call record captured before this seam carries none, and requiring it
would re-judge evidence already frozen. That every record the dispatcher writes today carries it is
held where it is produced, not in the shape.

The near miss is worth keeping: the first attempt's failure detail was lost because only the last lines
of the hook's output were captured. Hook and umbrella output goes to a file now, and its FAIL lines are
read before anything is reported.

## Still open

X#6, the 63-case unreadable-structure class, and cross-script lookalikes (out of scope by the owner's
decision of 2026-10-22). The output cap has no declared home yet — its caller states it until WP-08
gives it one, which is a known interface edge rather than an open defect.
