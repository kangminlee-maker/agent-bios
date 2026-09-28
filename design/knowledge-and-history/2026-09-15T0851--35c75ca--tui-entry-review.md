---
created_at: 2026-09-15T08:51:50+09:00
head: 35c75ca
kind: review
status: scoped-design-and-prototype-verified-runtime-and-human-evidence-pending
supersedes: 2026-09-15T0815--35c75ca--tui-entry-review.md
evidence: 2026-09-15T0851--35c75ca--tui-entry-evidence.json
---

# Decision-use choice and lifetime

The user made decision material an exception to automatic scope priority.
Instructions/knowledge retain repository → personal → Team application. An actual
use that encounters incompatible applicable decisions now requires the user's
application choice and a keep-until-change or ask-each-use policy.

The complete successor updates SSOT S04/S05/S06/S08/S11, the development specification,
P03/P05/P06/P11 work, the catalog and its consumed acceptance obligations. The new
state belongs to private operation/preferences, not a new shared ADR or a mutation
of source decisions. The source/permission and existing-session boundaries remain.

## Lifetime contract

Keep-mode is valid for the same principal, concern, context and unchanged relevant
decision set. Bind every participant, including unchosen alternatives, with exact
revision/lifecycle and relevant change continuity. Participant/set changes invalidate
choice and mode. Returning to old bytes does not revive invalidated consent.
Unrelated records, independent I/K choices, display aliases and new sessions do not
force requestions. Source frontiers establish coverage; raw whole-Team revision
equality is not the relevant-set key.

Ask-mode requests a choice for each new logical use, preserving the mode while the
basis is unchanged. A retry/page/reconnect of one use restores its same pending
question or answer. A changed basis creates a new question version; old answers
cannot be applied to it. A disappearing conflict returns normal qualified data
rather than creating a meaningless vote. Closing without an answer leaves only the
affected use pending. Actual source access is checked independently of preferences.

The [prototype](2026-09-15T0851--35c75ca--tui-entry-prototype.html) opens a fictional
explicit decision-use route by default so the question can be inspected. Its host
startup route remains separate and asks no future decision question. The source
table and startup snapshot retain unresolved decision references for later use.

## Verification and corrections

- Browser checks cover no default consent; I/K priority and absence of an automatic
  M winner; explicit choice/mode; keep reuse; ask on new use; same-use return;
  unrelated updates; unchosen/chosen participant changes; reversion; stale-answer
  rejection; bounded custom resolution; manual preference change; and immutable
  historical displays.
- The final browser run passes 29 named assertions and 32 dialog appearance/width/
  layout/custom-input combinations. Wide and narrow renders were visually inspected.
- The author evaluator adds four structural regression controls for the M exception,
  complete-input lifetime, session-independent lookup, and consumed change evidence.
  Its final result is recorded in the [evidence file](2026-09-15T0851--35c75ca--tui-entry-evidence.json).
- Cross-review found one P06 completion sentence still generalizing priority to all
  roles and a DC-CHOICE oracle that could require mode selection on every use. Both
  now distinguish initial/changed-basis questions from valid keep/ask reuse.
- Prototype review found the same repeated-mode issue in ask-mode. It now restores
  an unchanged saved ask policy while leaving the new application unselected.
  After relevant changes, both fields are reset. A manual change route also allows
  revisiting a retained preference without editing an original decision.
- Updated source snapshots and past applied selections are kept separately, so
  a later Team revision does not alter the source version/content shown for a past use.

The logical simulation uses fictional per-record revisions and change epochs.
It is not proof of real Git/source change continuity, database restart/backup,
cross-device transfer, trusted human-origin answers or host behavior. P01 binds
those concrete contracts; P03/P05/P06/P10/P11 and M1/M2/M3/P17 supply their actual
implementation/evidence. No real person was asked to approve a sample decision.

The [wireframes](2026-09-15T0851--35c75ca--tui-entry-wireframes.md) are a scoped
projection of the [arbitration SSOT](2026-09-15T0851--35c75ca--consolidated-design-ssot.md#s05-decision-arbitration).
No deployed runtime, end-user source collection, Team policy or installed state
was changed. Prior snapshots are preserved, and no full-runtime/whole-parity or
human-usability certification is claimed by this design turn.
