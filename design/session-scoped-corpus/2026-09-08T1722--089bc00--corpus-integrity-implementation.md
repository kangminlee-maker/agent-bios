---
created_at: 2026-09-08T17:22:40+09:00
head: 089bc004c3095809ed7bfe716bf885f4e6d8e716
kind: handoff
---

# Private corpus integrity implementation

The owner approved all five remedies. They are implemented in the working tree;
the header names the starting commit, not a commit containing these changes.
No live installation, publishing, commit, push, or native global settings change
was performed. The six pre-existing binding/golden edits were preserved.

## Current contracts

- A personal identity is a runtime-generated UUID assigned once in a plan.
  Apply reuses it; repeated Apply returns the recorded result. Allocation checks
  retained source histories and plans, so reset and rollback cannot reissue an ID.
  Public create input cannot assign `item_id` or `ref`.
- `members[primary_member]` owns content. Body editing is a manager-owned alias,
  not client-side synchronization. CLI, skill, Textual editor, requested links
  and relevant routing share this authority. Ambiguous legacy content is shown
  without discarding either version; the editor requires an explicit member
  choice. Generated rule trailing-newline differences are normalized losslessly.
- Install and rollback use three-way field/member comparisons. No-op overlays
  are removed, learning overlays retain their captured-event authority, and
  selected conflicts prevent publication instead of silently removing items.
- Source preparation is separate from successful installation publication.
  Store and installer share a reentrant cross-process lock; installer journals
  retain the complete nonsecret projection association. Pending publication
  guards configuration readers. A launcher rechecks its installation generation
  before composing a snapshot; pinned/bare paths can read a prior confirmed
  immutable release. Direct source-only installation cannot replace the success
  tuple of an already managed installation.
- Full reset previews return `expected_revision`. Apply requires that value and
  `--yes`; it archives nonsecret settings, replays exact prior/candidate states,
  and deletes the original token late. Replacements and intervening source or
  settings changes refuse old intent. A freshly accepted preview can supersede
  an obsolete reset while keeping a pending guard until its replacement intent
  is durable. Unknown legacy journal state remains a disclosed recovery need.
- Dry-run snapshot reads synchronize with writers and refuse interrupted source
  state without modifying it. Existing snapshot bytes and native pins are retained.

Concept direction: identity and transaction concepts are extended in place;
duplicate content authority and divergent switch paths are reduced. No new
database, global host profile, automatic semantic merge, or native activation
default is introduced.

## Verification

The real catalog/store/compiler regressions were added before the changes. They
reproduced ID reuse, stale requested-file content, rollback omission and missing
installation preparation. Additional controls cover forced random collisions,
plan replay, overlapping changes, no-op edits and split source writes.

- Corpus discovery suite: 123 tests passed using the installed Textual Python;
  no skips. Includes real npm-layout install/CLI/snapshot/reset/uninstall and
  native loader configuration checks, not model-generation acceptance.
- Transaction tests discover the phases emitted by real journal writes, inject
  an interruption after each, and replay the accepted operation. A separate
  test interrupts the inner source publication of a full reset.
- Real Textual tests include legacy conflict/member selection. The bootstrap
  skill validator passes; its authoring examples now submit body-only edits.
- Package, surface, terminology, content hygiene, ontology and whitespace checks
  passed. The payload count was re-derived as 47 and the ontology map regenerated.
- Endpoint, seam-coverage and publication self-tests initially met sandbox
  restrictions; their isolated reruns passed with 75, 5 and 22 named controls
  respectively. Publication tests use throwaway repositories, not a real release.
- The full parity umbrella is not green. Model binding, profile fixture and
  preset-round-trip failures also reproduce in the starting commit plus only
  the six pre-existing user edits. Sandbox wrapper logging failures are separate.
  A new global-instruction fixture dependency failure was corrected and its
  focused check passed; no whole-tree clean verdict is claimed.

Re-run the current subjects rather than relying on this dated count:

```sh
PYTHONPATH=compose:. /Users/kangmin/.local/share/agent-launch/venv/bin/python -m unittest discover -s compose -p 'test_corpus*.py'
bash gates/check-package.sh
python3 gates/check-surfaces.py
python3 ontology/check-ontology.py
bash gates/check-parity.sh
```

An Astra advisory code pass identified learning-overlay, preview, empty-overlay
and members-only-input cases; they were resolved and tested. This was a reused
review context, not a fresh-context review receipt. An additional independent
agent dispatch hit the task limit. Claude external review was not dispatched;
no cross-provider clean verdict is claimed. Native corpus-agent model execution
and post-upgrade model-generation replay remain separate acceptance work.
