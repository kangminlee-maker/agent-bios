---
created_at: 2026-09-14T20:33:47+09:00
head: 35c75ca
kind: review
status: scoped-design-and-browser-model-verified-runtime-and-human-evidence-pending
subject_revision: 2026-09-14T2033--35c75ca
evidence: 2026-09-14T2033--35c75ca--tui-entry-evidence.json
---

# TUI first-screen redesign and evidence

The successor SSOT, specification, graph and test catalog include the first-screen
redesign. The [wireframes](2026-09-14T2033--35c75ca--tui-entry-wireframes.md) and
[interactive projection](2026-09-14T2033--35c75ca--tui-entry-prototype.html) describe
the selected direction; they do not replace the current runtime TUI.

## Root cause and selected direction

The [source audit](2026-09-14T2033--35c75ca--tui-entry-source-audit.md) found different
entrances with different effects: host configuration, installation and Instructions
authoring. The launcher mixes mode/preset decisions with management/settings, and
its current-setup wording can refer to a highlighted proposal. Adding another
status panel would preserve that ambiguity.

The target first screen separates observable context, explicitly selected work
environment, execution configuration and the next named effect. Environment
selection supplies professional/team context; a model/preset is an execution choice.
The generic hub exposes product functions; a known host can enter environment
preparation directly. Direct links and evidenced recipients preserve their routes.
Settings are discoverable without becoming alternative professional roles.

The user corrected a consequential assumption in the first mock: agent-bios does
not know the current business task or target. The final mock has **no goal/target
form or prefilled intent**. It shows observed location and a scoped recent record,
including what that record cannot establish. A previous commit, review note or
delivery receipt is not current intent, whole-task completion or authority to resume.
The tool may be known; a proposed new session is only a start-mode choice.

Environment/startup preparation can succeed without a concrete task request.
It checks selected sources, access, essential initial material and the intended
start path. Task support remains unassessed. Task-specific knowledge/decision
queries follow an actual request in the host; they do not run simply because the
first screen or a selected source exists. S05/S06/S10/S11 and the development
specification carry this boundary together, including its negative oracles.

## First-screen space and interaction

The first browser projection was too tall: source details pushed the execution
configuration below the first wide viewport. The final initial view uses three
compact source summaries; body reading occupies a separate view and returns to the
same selection. It retains the consequential execution choices and next effect.
This changes the information hierarchy rather than hiding content with smaller text.

The fictional projection supports environment/configuration changes, startup
checking, explicitly simulated results, source detail, required initial-material
recovery, offline qualifications, same-request unknown recovery and a protected
locked view. Selected environment changes affect the displayed source summary.
Focus does not change the selection; changed selection invalidates its preview.
The full Team editor, onboarding wizard and every host adapter are outside this
mock's coverage, while remaining inside the product design/implementation scope.

## Verification performed

- Dated graph validation and selected brownfield identity checks pass. The existing
  25-node DAG and seven acceptance obligations remain; P11 still depends only on
  P06/P10 and M1 remains independent of Team/external providers.
- The evidence evaluator's **9 positive and 72 negative controls** pass. Four new
  controls reject omission of the two real entry-observation cases or replacement
  with deterministic fixtures. This tests the acceptance model, not the product UI.
- Browser checks pass **25 named assertions** and **256 scenario/width/layout/theme
  combinations** for horizontal containment. They exercise eight fictional cases,
  two entrance modes, two layouts, four widths and two appearances.
- Named checks cover selection versus focus, changed-source preview invalidation,
  taskless startup with unassessed task support, absent goal/target form, scoped
  checkpoint limits, missing/denied refusal, offline qualification, explicit mock
  effects, locked metadata, and the same unknown request after a draft change.
- The final wide first viewport contains both execution configuration and the next
  action. The two text wireframes have 21/19 lines and at most 65/63 counted cells,
  under the explicit wide/fullwidth=2 and combining=0 convention.
- Fresh delegated review checked the contract and execution dependencies. These
  reviews are evidence-based design judgments, not first-exposure user observation.

The browser projection reflows at narrow pixel widths; this is not a real 80×24
terminal emulator. Text cell counting, screenshots and injected strings do not
prove real IME, SSH, screen-reader or terminal behavior. The renderer's standalone
iframe was expanded for full-content QA captures; the fragment remains the editable
projection and the preview document is generated from it.

The [evidence record](2026-09-14T2033--35c75ca--tui-entry-evidence.json) stores source
hashes, exact scope and named check results. No product runtime, installed user state,
account, connection or real session was changed. No real participant was contacted
or observed. This turn does not certify the full repository parity suite; the prior
repair record retains its actual dirty-index failure and existing test results.

## Implementation and acceptance

P01 freezes the state/operation examples, actual terminal support and observation
protocol. P11 implements the personal shell and first-screen semantics; an independent
test packet can exercise different focused/selected/installed/delivered references.
Launcher/setup/locale changes integrate through the shared-path owner.

M1 verifies real personal entry, M2 actual Team/offline scope, and M3 shared unknown
operation/lifecycle links. P17 requires actual first-exposure comprehension and
Korean terminal observations of the integrated candidate. The existing terminal
obligations consume those cases; missing observations remain pending. Verification
nodes return defects to their implementation owner rather than modifying the source
they are certifying.

Fixed menu counts, extra permanent dashboards, profession-like execution modes,
a universal mandatory home and a first-screen goal registry are excluded. Actual
comprehension or operating evidence can overturn a layout choice. Source authority,
taskless start, exact recipient/effect boundaries and continuity remain required.
