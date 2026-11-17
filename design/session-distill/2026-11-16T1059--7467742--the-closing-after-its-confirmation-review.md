---
created_at: 2026-11-16T10:59:00+09:00
head: 7467742          # the commit reviewed; the answers are the next commit
kind: review
supersedes: none (it follows 2026-11-16T0944--b6770be--release-1-changes-no-library-file.md, which stays as written)
---

# The closing after its confirmation review

Codex reviewed the closing of the write path (74677426, D-20261116-7853bc) and returned rework: three major
findings and two minor. It confirmed that S7's three accepting paths, S7b, S10b and S11 refuse a change, that a saved
plan or journal cannot bypass an empty final set, that no environment variable, declaration field, flag or import
changes the scope, and that every one of 80 ordinary and 84 legacy combinations keeps an accepted answer with its
conditions. Review file: the lead's `work/lead/release1-x-review.json`.

## What each became

- **S12 could write a library member through its own destinations** (major). `--checkout-ledger` and
  `--checkout-coverage` were checked for path safety only, so a ledger or coverage state named inside a skill would
  be written there and shipped as part of it. `stage_close.destination_problems` refuses a destination in any layer
  of `tables/drift_layers.json` but `ledger`, or under `claude/`, `codex/` or `ko/`, read case-folded, before either
  write (`CLOSE_DESTINATION_IN_LIBRARY`). This holds under both scopes.
- **An adopted S7b alternative could confirm a set S12 cannot close** (major). An alternative carries a reason and
  no observation; S10b put an adopted incubate in the ledger-only set, where S12 refused it for its missing
  observation after confirmation, and an adopted drop lost its reason on the way. `stage_confirm.adopted_gap` sends
  an incubate, or a keep or drop without a reason, back to S7 (`needs_proposal`, with the reason named on the page),
  and the reason the owner read travels to the close (`alternative_reason`). S7b's packet says so.
- **S12 closed a run an earlier version had applied** (major), so the lost keep release (round 4's C4) could still
  reach the ledger. S12 refuses, in release 1, a run whose confirmed set held a change or whose S11 record holds an
  effect, before the allocation and every write, and says how to recover. F-45's reach paragraph says this now; its
  earlier "none of these runs" was false for this path.
- **The scope control missed a call through another name** (minor). The AST walk now refuses any reference to
  placement's `scoped` - an attribute through an alias of the module, an import from it, a `getattr` with the name -
  outside a function named `self_test`, `_self_test_all` or `_self_test_body`, and `scoped` itself refuses to run
  unless one of them is on the calling thread's stack (`RELEASE_SCOPE_OUTSIDE_SELF_TEST`), proved from a thread.
- **The guide still directed library edits** (minor). Its outcome list and a paragraph before Stage 2 say, in English
  and Korean, that Stages 2 to 5 are an author's own work by hand and that the driver changes no library file.

The suite of S12 now runs the run release 1 can make, from S10's parse through S12 at the shipped scope: an adopted
drop and an approved legacy group, S11 writing nothing, and S12 recording the drop with the owner's reason.

## Verification

Ten revert trials (`work/lead/pretrial-release1-r2.py`, `pt-release1-r2.log`), each failing a named control.

## What is not claimed

- No real run has met the refusals.
- A recovery from a run an earlier version applied is described in the refusal, not exercised.
