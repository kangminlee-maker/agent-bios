---
created_at: 2026-11-16T11:28:00+09:00
head: 79477c2          # the commit reviewed; the answers are the next commit
kind: review
supersedes: none (it follows 2026-11-16T1059--7467742--the-closing-after-its-confirmation-review.md, which stays as written)
---

# The closing after its second review

Codex's second and last round on the closing (79477c24) returned rework: three major findings and one minor. Of
round 1's five, the earlier version's applied run and the guide were met, the other three partly. A set that
changes no file behaves as before under both scopes, and S11's saved plans and journals cannot bypass an empty final
set. Review file: the lead's `work/lead/release1-x2-review.json`. There is no third round for this change; the
answers below are verified by revert trials.

## What each became

- **A declared checkout inside a skill** (major). `destination_problems` judged the destination's relative spelling
  only, so `design/session-distill/ledger.json` under a checkout declared at `claude/skills/understand` was an
  instruction member. `drift.library_place` reads an absolute path, symlinks followed, from every ancestor that holds
  both `claude/` and `codex/` (an agent-bios checkout or package) and inside a host's installed home (`.claude`,
  `.codex`), and S12 asks it of each destination where it lands in the declared checkout.
- **A run directory inside a skill** (major). An explicit `--out` was judged per command, and S11 opened its lock
  before any check. The driver's `run_dir_of` refuses a run directory `library_place` names, for every command,
  before any lock or directory (`RUN_DIR_IN_INSTRUCTIONS`). A stage function called directly, outside the driver,
  does not ask this.
- **An adopted keep** (major). An S7b keep alternative names no units, so S12 could not record its keep record.
  `adopted_gap` sends an adopted keep back to S7 like an incubate; only `none` and a `drop` with its reason close as
  adopted. An item sent back stays out of this confirmation; once the set is confirmed, the run builds no other, so
  it is decided again in a new proposal cycle before confirming, or in a later run.
- **The scope control** (minor). The AST walk also refuses `_SCOPE`, placement's `__dict__`, `vars(placement)` and
  `import_module` of it outside a suite. What it does not hold is written in `scoped`'s docstring: Python run in the
  same process at will (`exec`, a thread started under a suite's name, a module defining its own `self_test` to call
  it) can change any module state. The property is release 1's commands, not an interpreter boundary.

## Verification

Ten revert trials (`work/lead/pretrial-release1-r3.py`, `pt-release1-r3.log`), each failing a named control.

## What is not claimed

- `library_place` recognises a checkout by its `claude/` and `codex/` directories. An installed library that has
  neither, other than a host's home, is not recognised.
- No real run has met these refusals.
