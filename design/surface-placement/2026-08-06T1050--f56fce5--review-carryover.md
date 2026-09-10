---
created_at: 2026-08-06T10:50:00+09:00
head: f56fce5
kind: backlog
---

# Two findings from the #20 review, deliberately not fixed there

The Codex review of #20 ran four rounds. Six findings were fixed in the PR; these two were
held back because neither is something the merge introduced, and the PR had already grown
past the merge it exists to land. Recorded rather than dropped: an unfixed finding with no
trace is indistinguishable from one nobody found.

## 1. The uninstall archive can overwrite itself — P2

`install.sh` builds the archive path from `date +%Y%m%d-%H%M%S`, so two uninstalls that land
in the same second resolve to the same file and `tar czf` truncates the first. The realistic
shape is not concurrency but a second run: the first archive holds everything, the second
finds almost nothing left and replaces it with an effectively empty file — losing the only
recovery copy at the moment it matters.

Fix direction: generate the destination so it cannot collide, or refuse when the path exists.
Refusing is the cheaper half and fits the surrounding posture, which already prefers leaving
the machine untouched over completing a destructive step.

Not in the PR because the archive path came in with the branch and the failure needs two runs
inside one second — real, but not something the merge changed.

## 2. Folded review receipts inherit controls they did not verify — P1

`launch/agent-launch.py` folds a multi-pass review panel into one receipt, and the agreement
check omits `ordering_seed` and `swap_group`. The merged receipt takes both from the first
pass, so a later pass that omits or contradicts them still reads as achieved: `_receipt_reason`
sees the first pass's non-empty values and credits the whole panel.

This is the receipt surface asserting a control it did not confirm, which is worse than not
asserting it — the whole point of the receipt is that a clean verdict is evidenced rather than
claimed. It belongs with the reviewer-registry work (`design/reviewer-registry/DESIGN.md`),
whose Stage 7 receipt producer is the thing that would consume the fold.

Not in the PR because it is untouched by this merge and sits in a subsystem with its own open
design question.

## 3. `claude-run` says REQUIRED in its header and warns in its body — doc only

`wrappers/claude-run.sh` opens by stating that `--model` and `--effort` are "required rather
than optional, which is the one place this diverges from codex-run", and its dispatch check
then warns and proceeds, saying in as many words that it matches codex-run. The body is the
decision that stands — refusing turns "the review ran unpinned" into "the review did not run",
and the honest signal lives downstream, where an unpinned dispatch names no seat, emits no
receipt, and adjudicates UNKNOWN. `README.md` said the same wrong thing and was corrected with
that reasoning; the file's own header was left because the file is untouched by this merge.

No behaviour change, and no gate can decide it: this is a comment disagreeing with the code
beneath it, which is the class the repo routes to review rather than to enforcement.

## Entry conditions

None is blocked. (1) is a contained change to one function plus a control that runs two
uninstalls in the same second. (2) wants the reviewer-registry context loaded, and its
control has to make a later pass contradict the first — a fold that agrees proves nothing.
