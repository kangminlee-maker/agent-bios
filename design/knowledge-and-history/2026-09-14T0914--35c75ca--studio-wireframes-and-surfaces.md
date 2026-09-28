---
created_at: 2026-09-14T09:14:35+09:00
head: 35c75ca
kind: design
status: wireframe-and-surface-hypothesis
requirements: 2026-09-14T0217--35c75ca--requirements-coverage-review.md
amends: 2026-09-14T0758--35c75ca--zero-base-review-disposition.md
---

# Studio wireframes and the TUI/GUI boundary

## Recommendation

Keep the current Instructions TUI and its machine interface. Design a graphical
Studio for the complete environment-authoring, knowledge, decision and Team
management scope, with compact work-context access also available in the
terminal and existing hosts. One shared operating core serves those surfaces;
do not build separate sources, reducers, permission rules or mutation engines.

This is a proposed direction to validate, not a measured claim that GUI always
outperforms TUI. The current implementation addresses Instructions management;
neither the current TUI nor the previous HTML mockups implement the full future
product. The [source-based capability review](2026-09-14T0915--35c75ca--tui-gui-capability-review.md)
identifies those implemented boundaries and evidence paths.

For the requested complete Studio, a TUI-only presentation is not a sufficient
default assumption. Several important tasks require comparing documents,
conditions, affected environments, relations and concurrent decisions while
retaining context. A graphical composition is a stronger candidate for these
tasks. A compact terminal route remains valuable for known-item edits, quick
selection, remote administration and reliable scripted recovery.

The purpose is shared Team environments that workers can select, understand
and continue across people, devices and hosts. Supporting that purpose does
not require every worker to enter Studio or every operator to open a browser.

## Ten wireframes, twenty surface representations

The wireframe atlas is deliberately monochrome. It tests information hierarchy,
actions and paths rather than color, branding, animation or a frontend framework.
It begins with one overview of ten tasks; each opens a graphical wireframe and
its corresponding terminal-oriented representation. Each screen explains the
surface-specific hypothesis. The atlas selector is a design-review harness,
not ten mandated production navigation destinations.

| ID | User question / main layout | Main next path | Requirement groups |
| --- | --- | --- | --- |
| W01 · Work-context brief | Which Team standards apply to this work? Show useful method, support, current decisions, material limitations and target environment. | Source/evidence W03, decision why W04, missing-body recovery W08, actual recipient W09 | U01–U04, U09, U11 |
| W02 · Environment composition | What does our Team share? Environment list with exact source composition; distinguish source editing from environment references. | Source W03/W04, search W10, changed composition review W05 | U01–U03, U10 |
| W03 · Knowledge authoring | Where does this knowledge apply and what supports it? Topic/section selection, body/conditions, evidence. Relations and questions are selectable views. | Exact revision proposal or scoped validation → W05 | U05–U06, U09, U14 |
| W04 · Decision/workstream understanding | How did the current choice arise? Current state and open questions above aligned workstreams; selected record opens its actual rationale and correction. | Targeted correction/new choice → W05; return to work W01 | U07–U09 |
| W05 · Change review | What exactly changes, and what does my approval do? Before/after plus reason, source/Team impact and remaining execution responsibility. | Appropriate source/environment result, preserving separate publication/adoption/use outcomes | U10, U12, U14 |
| W06 · Team creation | With whom and how will we work? Reviewable identity, P2P/GitHub choice and founding responsibilities; advanced connectivity conditions remain accessible. | Created Team and pending founding W07, then first environment W02 | U02, U12–U13, U15–U17 |
| W07 · Team management | What is affected by this operation? Overview, members/permissions, settings and lifecycle scope; rare destructive actions are distinct. | Governed change W05, custody/recovery W08, environment W02 | U12–U14, U18 |
| W08 · Exchange and recovery | What is local, unshared, missing or uncertain? Local usability separate from inbox/outbox and dated custody; identify actionable missing bodies and operation receipts. | Verify/recover, then return to W01; not automatic activation | U14–U18 |
| W09 · Recipient and handoff | Who actually receives which context? Prior versus target recipient, required bodies/routes, permissions and delivery evidence. | Actual recipient result or specific missing-condition recovery | U01, U08–U09, U11 |
| W10 · Search and bulk work | Can I find and move the correct material? Scope/query, per-item owner/version/access, plan and partial results. | Per-item source or governed transfer/review W05 | U06, U10, U14–U17 |

These are screen families, not a claim that every nested advanced operation is
fully rendered. They retain the complete source/governance/CRUD contracts from
the prior designs. Instructions editing uses the source text/member pattern;
knowledge adds its specialized conditions, relation and question views. Memory
uses typed events rather than a generic body overwrite. A source graph is a
view with an equivalent entity/relation list, not a new source of truth.

The low-fidelity buttons open the action's expected effect or navigate to a
related wireframe. They do not execute simulated approval/creation/deletion
state machines. The previous end-to-end prototypes supply those finite process
examples; this atlas concentrates on layout and the TUI/GUI comparison.

## Equivalent meaning, appropriate representation

| Task property | Terminal representation | Graphical representation |
| --- | --- | --- |
| Brief, already-known work | Short ordered body, visible current scope, keyboard-accessible actions | Same brief with visible source sections and target/ready action |
| Exact small text change | Unified diff and explicit before/after metadata | Unified or side-by-side diff with affected context |
| Several long sources at once | Section switching, search, referenced local editor/reader where supported | Evidence and editable material in adjacent panes, preserving return position |
| Scoped domain relation | Searchable entity/relation records and path text | Selected neighborhood graph/table and inspector, not an unbounded whole-graph canvas |
| Parallel decisions | Qualified current-state list, related-event links and named workstream paths | Current-state summary, aligned lanes and connected record detail |
| Team governance/lifecycle | Guided typed forms, exact effect review and named commands | Discoverable forms and consequence review with all affected objects named |
| Batch and remote recovery | Machine-readable plan/result, terminal detail and request-bound resume | Per-item selection, evidence and partial-result table over the same operation |

The terminal design must remain capable without the GUI: core Team setup,
authoring, authorized changes, source/context inspection, exchange and recovery
have equivalent operations. It need not imitate graphical spatial gestures.
A browser-only relation editor or GUI-only approval record must not make a
closed/remote environment unable to complete a necessary operation.

Conversely, nondevelopers must not be sent to JSON, a command line or a second
technical tool merely because the initial implementation was a TUI. A usable
graphical route must exist for ordinary creation/joining, work preparation,
source management and recovery. Surface parity means qualified outcome and
operation equivalence, not identical pixels or a copy of every command button.

## Packaging: local GUI first as a validation vehicle

The next graphical prototype can run in a local browser with installed assets
and a local operation bridge. That demonstrates interaction without committing
to a dedicated desktop wrapper. A browser is a presentation host, not a demand
for an Internet-hosted service. GitHub remains the recommended optional sync
choice; core work remains local/P2P under its actual conditions.

| Form | Decision for now |
| --- | --- |
| TUI plus CLI/machine interface | Retain and extend the appropriate compact and operational routes. |
| Locally served graphical Studio | Leading implementation experiment for GUI interaction because the same design can be evaluated before platform-specific packaging. |
| Packaged GUI with an embedded renderer | Consider when controlled window lifecycle, file integration, distribution or isolation needs justify it; measure actual cost/behavior. |
| Native platform GUI | Consider when native accessibility/input, device integration or browser restrictions decide the deployment; avoid assuming it is automatically better. |
| Hosted-only web application | Cannot be the only route for the required disconnected/P2P product. Optional remote access is a separate deployment. |

No production frontend library, wrapper or platform is selected by these
wireframes. Do not maintain several GUI stacks simply to evaluate alternatives.
Do not deploy a network listener or upload Team content as a side effect of
creating/opening a wireframe.

The production local bridge must bind to the intended local surface and current
authorized principal, enforce the shared operation policy, and preserve exact
request identity. A page's origin, a loopback address or a button state alone
does not grant Team permissions. Window/terminal exit and reopening must recover
durable drafts/outboxes and uncertain operations without replacing them with
new requests. Moving between TUI and GUI must reopen the same candidate/request.

## What remains visible and what may collapse

Always show the Team/environment relevant to the action and any material
limitation. Show ownership, current/draft/adopted/use differences when they
affect the decision. Body conditions, exceptions and targeted corrections must
remain with the claim they qualify. Raw hashes, full checkpoint histories and
protocol evidence can be expanded when needed.

The GUI must provide keyboard equivalents for non-freehand interactions;
graph relationships and workflow paths also have structured text/list views.
The W3C keyboard guidance supports this criterion, rather than a presumption
that either GUI or TUI is inherently accessible.
[W3C keyboard guidance](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html)

Test actual terminal cell width, Korean composition/paste, terminal resizing,
focus and the supported screen-reader combination. The HTML terminal wireframe
does not emulate any of these. Graphical testing additionally covers zoom,
semantic reading order, errors, copy/paste, keyboard-only operation and narrow
windows. Neither an attractive screenshot nor a native widget proves these.

## Validation plan and decision criteria

Use the same rights, data, task and failure state in TUI and GUI prototypes.
Include routine terminal users and nondeveloper/occasional users; retain
separate first-exposure evidence rather than assuming everyone knows shortcuts.
Include long documents, multiple conditions, intertwined workstreams and bulk
operations, not only short examples that favor a terminal summary.

Observe whether participants identify the correct scope/effect, preserve
important conditions, locate an unfamiliar operation and recover from an error.
Measure actual task time/effort after correctness. Compare input friction and
switching between source, evidence and result; do not award a surface victory
merely for fewer screens or a wider diagram.

Acceptance also needs supported operation through SSH or constrained machines,
no GitHub configuration, a week between exchanges, missing local evidence,
an unknown commit result and a cross-surface resumed draft. An offline GUI whose
assets load but whose required model/reader does not work is not ready.

Wireframes are appropriate for exploring structure before committing to code;
later realistic prototypes and user observation must decide behavior and
packaging. Prototype code is not production security or performance evidence.
[GOV.UK prototyping guidance](https://www.gov.uk/service-manual/design/making-prototypes)

## Artifacts and review

- [GUI/TUI wireframe atlas source](2026-09-14T0914--35c75ca--studio-wireframe-atlas.html)
- [Current TUI and candidate GUI capability review](2026-09-14T0915--35c75ca--tui-gui-capability-review.md)
- [Atlas QA and explicit limits](2026-09-14T0930--35c75ca--wireframe-atlas-qa.md)

An independent final review found no critical contradiction with the complete
scope, zero-base interaction direction, P2P foundation or optional GitHub. It
confirmed that the local-browser choice is a validation vehicle and that the
wireframes do not establish actual terminal behavior, complete advanced-editor
implementation or human usability. No surface is declared inherently superior.

## Scope and evidence

The current work produces a screen atlas, its GUI/TUI surface assessment and
mechanical atlas QA. No runtime files, actual Team, provider or credentials are
changed. Full operational details remain in the consolidated requirement and
Team/source/governance designs. Actual user usability and a deployed local GUI
are not claimed.
