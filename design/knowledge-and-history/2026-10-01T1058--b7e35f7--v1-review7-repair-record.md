---
created_at: 2026-10-01T10:58:06+09:00
head: b7e35f7
kind: review
plan: 2026-09-30T0604--b702da9--development-plan.json
node: V1
supersedes: null
decisions: D-20261001-0fd591, D-20260930-c06461
---

# V1's seventh bound review found four places the start did not hold to its contract, and all four do now

This follows the [21:35 repair record](2026-09-30T2135--8c27731--v1-review6-repair-record.md)
and the [21:43 direct-use record](2026-09-30T2143--8bda008--v1-acceptance-after-review6-direct-use-record.md).

- **The record.** V1 was recorded into `run-16` at `b7e35f7`, and all 21 cases passed. `run-16`
  is `run-15` without V1's sixth, unpublished attempt (`v1-accept/make_run16.py`).
- **The review.** One bound review ran on `gpt-6-astra` at max effort, hermetic and read-only,
  from 21:48:53 to 22:16:06 on 2026-09-30 (`review-v1-20260930-r7/`).
- **The result.** `defects_found`: one high and three medium findings, and 23 stated checks. The
  recorded hashes and case outcomes agree. P00 and P01 would remain accepted.
- **The owner's answer** came on 2026-10-01.

V1's attempt in `run-16` is not published. V1 is recorded again, in a new run, after this repair.

## What the review found, re-derived here

### 1. High: a required winning unit with no body still started

This goes against done-when [10].

- **The reviewer's case.** A personal collection selects `README.md` with `concern: review` and
  `startup: required`, and its body is not held. Composition stated `role_body_unavailable` at
  the unit, and activation committed without a body.
- **The contract.** C07's `unit_binding`: "`startup: required` means the unit must resolve before
  a session starts when it wins", and a unit it `needs` "stays required". The SSOT says the same:
  "A required winning startup unit must resolve, or the user explicitly changes the selection."
- **In the code.** `roles.activating` never read the preparation's unit gaps.

### 2. Medium: a shadowed document blocked an independent winner

This goes against done-when [6] and `shadowed_team_content_blocks_start=false`.

- **The reviewer's case.** A personal unit wins over a repository-authored Team document for the
  same concern, and neither needs the other. With the Team document absent from its checkout,
  activation was refused `working_bytes_moved`.
- **In the code.** `roles.moved` read every unit that names a body, shadowed ones included.

### 3. Medium: two identical requests under different ids could both be admitted

This goes against done-when [10].

- **The reviewer's case.** Request B passed the unknown-outcome rule; before B entered its unit of
  work, request A, the same operation, target and payload under another id, was held unknown. B
  was then admitted too.
- **In the code.** `journal.layer_journal` asked `ruled` outside `store.unit` only. The second
  review's repair asked `repeated` again inside it, for the same id, and not this rule.

### 4. Medium: the entry showed the branch the repository was bound on

This goes against done-when [9].

- **The reviewer's case.** Bound on `main`, then switched to `feature/retry`, the entry still read
  `work · local repository · main`.
- **In the code.** `tui.location_of` read the binding's observation alone.

## What the owner chose

All four are fixed within the frozen contract (`D-20261001-0fd591`). The closed alternatives are
deferring each as a known limitation.

## What changed

- **`workenv/roles.py`.**
  - `unmet(prepared)` names the first gap at an Instructions unit that wins with `startup:
    required`, or at a unit such a unit needs. Knowledge is read for a task, not at the start, so
    a knowledge unit's gap gates nothing.
  - `activating` refuses with that gap, so the activation and its dispatch both refuse it, and a
    start launches nothing.
  - `moved` reads only units a delivery carries (`winning`, `layered`) or a winner needs.
  - The module's description says so.
- **`workenv/tui.py`.**
  - A start refused with `role_body_unavailable` or `object_digest_mismatch` is drawn as
    `시작하지 못함 · 필수 지침 본문을 쓸 수 없음 · 선택을 바꾸거나 본문 받기` (en `a required body
    is unusable · change the selection or fetch it`, ja likewise). Its result label is one
    method, `result_label`.
  - `location_of` reads the branch the bound checkout is on now (`checkouts.branch_now`): none on
    a detached HEAD, and the bound branch where git does not read the checkout. The entry reads it
    once, as it opens.
- **`workenv/sources/checkouts.py`.** `branch_now` is the one reading of the branch, and
  `observed_in` asks it.
- **`workenv/journal.py`.** Inside the unit of work, `ruled` is asked again, so a request held
  unknown in between refuses this one `resubmitted_while_unknown`.
- **Tests:**
  - `test_roles`: a required winner with no body is refused, on activation and on dispatch; one
    `not_required` starts with the gap carried; a unit a required winner needs, with no body, is
    refused.
  - `test_roles`: a shadowed repository-authored document that changed blocks nothing, and one
    the winner needs refuses `working_bytes_moved`.
  - `test_start`: such a start launches nothing and states `role_body_unavailable`.
  - `test_tui`: the refusal's wording; the branch the checkout is on as the entry opens, on a
    detached HEAD, and with the checkout gone.
  - `test_journal`: a request held unknown while this one waited refuses it.

## How it was checked

- **The mutation sweep** (`v1-accept/mutate_v1ze.py`).
  - Its first run (`mutate_v1ze.txt`) caught 9 of 11. Two tests did not take the path they
    named:
    - the needed unit was a required winner of its own concern, so it was refused on that
      ground, and is now `not_required`;
    - the other request was held unknown before this one's rules were first asked, not after,
      and is now held in between.
  - Run again (`mutate_v1ze-2.txt`), it caught 11 of 11: activation ignoring a unit that must
    resolve; `unmet` ignoring startup, a winner's needs or the role; the entry drawing the
    reason; `moved` reading a shadowed unit or ignoring a needed one; the rule not asked inside
    the unit; the location reading the binding alone, with no fallback, or reading a detached
    HEAD as unreadable.
- **The earlier sweeps, re-run on this tree** (`mutate_*-rerun-v1ze.txt`):
  - `mutate_v1r.py` caught 8 of 8, `mutate_v1v.py` 5 of 5, `mutate_v1za.py` 6 of 6,
    `mutate_v1zc.py` 6 of 6, `mutate_v1ux-reanchored.py` 6 of 6, `mutate_v1xz-reanchored.py` 4 of
    4 and `mutate_v1z-reanchored.py` 1 of 1.
  - `mutate_v1u.py`, `mutate_v1u-reanchored.py` and `mutate_v1x.py` caught all they could apply,
    with the anchors the [20:31 record](2026-09-30T2031--8897a53--v1-review5-repair-record.md)
    names. `mutate_v1z.py` caught all it could apply, with those anchors and the one the
    [21:35 record](2026-09-30T2135--8c27731--v1-review6-repair-record.md) names.
  - Three more anchors moved, because this repair gathered the result label into
    `result_label` and narrowed `moved`: one each of `mutate_v1z.py` (the code drawn, not the
    next steps), `mutate_v1zb.py` (admitting alone never named) and `mutate_v1zd.py` (`moved`
    reading a unit that names no body). Re-anchored on the code as it is now, undoing the same
    things (`mutate_v1zbd-reanchored.py`), all three are caught. The rest of `mutate_v1zb.py` and
    `mutate_v1zd.py` were caught.
- **The workenv gate:** `WORKENV OK`.
- **Every profile's cases** (`all_outcomes.py`, 837 outcomes) are identical before (an archive
  of `b7e35f7`) and after: 61 passed, 764 blocked, 12 failed. V1's 21 pass.
- **Bindings.** `cases.py --bindings` equals the 13 frozen bindings `run-17` holds, so P01 is not
  reopened.

## Next

1. A short real use on both hosts with the committed code.
2. V1 recorded into `run-17`, which is `run-16` without V1's attempt (`v1-accept/make_run17.py`).
3. One bound review, whose result goes to the owner.
