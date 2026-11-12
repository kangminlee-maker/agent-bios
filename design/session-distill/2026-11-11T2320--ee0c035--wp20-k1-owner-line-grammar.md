---
created_at: 2026-11-11T23:20:00+09:00
head: ee0c035
kind: design
supersedes: null
---

# WP-20 K1: the owner's lines are read where the render marks them, and refused by line everywhere else

The first commit of WP-20 (plan `2026-10-20T2119--cc0498f--implementation-plan.md`, WP-20; release-1 amendment
`2026-11-11T0040--062b76d--…`), on `wp/20-review` from `wp/12-propose` at `ee0c035` (lead decision E10). It depends
on nothing: the renderer (K2), the decision parser that writes `approvals.jsonl` and `adjudications.jsonl` (K3) and
the confirmation (K6) call it.

## What landed

`session-distill/grammar/owner_lines.py`, one parser with `--self-test` (96 controls), in the parity umbrella and in
`gates/control-audit.py` `SUBJECTS`.

- **The copy.** `copy_of(render, name)` is one header line (`<!-- owner-copy of=<name> sha256=<render sha256> -->`)
  over the render's bytes. `review_block(item, item_sha, labels)` and `confirm_block(set_sha)` are the only writers
  of an owner block; `render_problems` refuses a render whose blocks are anything else, prefilled included.
- **Editable by position** (D-20261111-eaeb76). Only the lines between a block's markers may change; every byte
  outside, markers included, must equal the render's. The first departure is named by the copy's line number
  (`EDIT_OUTSIDE_EDITABLE`), with CRLF, a byte-order mark and an NFD re-normalization named by their own codes so the
  owner learns what the editor did.
- **The lines.** Review blocks: `결정: <verb>` (§10.1's five verbs, held to the copied sentence), `수정 대안 <id>`,
  `메모:`, `판정 <label>: A | B | <own value>`, `keep 해제: <record> <grounds>`. Confirmation blocks (lead decision
  E1): `확인: 확정 | 반려`, `메모:`. A line of no kind, a second decision line, words after a verb, a filled judgment
  under another verb, a release under anything but 승인, a lower-case `a` read as judge A: each refused by line,
  never guessed.
- **Held to the current rows** when the caller passes them: `DECISION_STALE` (the anchor's sha is not the item's
  now; the item is decided again in a new version, and nothing else of it is judged), `KEEP_GUARDED`,
  `DISPUTE_UNRESOLVED`, `DECISION_NOT_ALLOWED`, `ADJUDICATION_INCOMPLETE`, `JUDGMENT_UNKNOWN`,
  `JUDGMENT_VALUE_INVALID`, `ALTERNATIVE_UNKNOWN`, `KEEP_UNKNOWN`, `ITEM_UNKNOWN`, `ITEM_NOT_RENDERED`;
  `CONFIRM_STALE` for a confirmation of a set that is no longer the final one.

## Choices made here, open to the lead

- The file is `grammar/owner_lines.py`, not the plan's `grammar/decisions.py`: `LEXICON.md` declares the concept
  slug `decision` with home `decisions/` (this repo's own decision record), and `gates/check-lexicon.py` fails any
  path outside that home that carries the slug. K3's stage file follows (`stage_approvals.py`, not
  `stage_decisions.py`).
- A note is required for `판정` (it is `adjudications.jsonl`'s rationale), for `수정` without a named alternative
  (S7 receives it), and for `반려`. 승인, 보류 and 기각 take an optional note.
- The decision values written downstream are `approve`, `revise`, `defer`, `reject`, `adjudicate`, and the
  confirmation's `confirm`, `return`; the Korean verbs stay the owner's interface.
- A judgment label is letters, digits, `_`, `.` or `-` (the render numbers them per row); the label's judgment
  reference and its allowed own values come from the caller's rows, never from the copy.

## Evidence

Revert trials (`work/impl/wp11/rows-k1.py`, 70 rows, `logs/pt-k1-1.log`, `pt-k1-2.log`): every row's named control
failed. One row first missed because the suite died on an uncaught refusal in its last control; that control now
fails by name, and the row is caught.

## Not here

The renderer and the rows' `judgments`, `alternatives` and `guarded_keeps` (K2, K3: they wait for WP-12's 4b
proposal schema); writing `approvals.jsonl` / `adjudications.jsonl` and their bindings (K3); the review page's mark
for a row admitted by adjudication and applied untested (D-20261111-6d8152, K2/K5).
