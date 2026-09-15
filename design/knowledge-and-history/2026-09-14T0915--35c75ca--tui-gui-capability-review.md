---
created_at: 2026-09-14T09:15:49+09:00
head: 35c75ca
kind: review
status: surface-capability-assessment-not-implementation
requirements: 2026-09-14T0217--35c75ca--requirements-coverage-review.md
disposition: 2026-09-14T0758--35c75ca--zero-base-review-disposition.md
---

# TUI and GUI: capability, audience, and complete operating paths

The decision is not whether a graphical window is more capable than a terminal
in the abstract. It is which surface lets a particular worker select, understand,
maintain and continue a Team environment with fewer mistakes and less effort.
Neither a new UI nor the existing TUI changes source ownership, approval,
replication, or actual-use semantics.

The [07:58 disposition](2026-09-14T0758--35c75ca--zero-base-review-disposition.md)
already separates two useful jobs: a work-context brief for starting/continuing
work, and an environment notebook for authoring/maintenance. A brief can appear
in a host, terminal or graphical window; a notebook need not require creating a
task. Both jobs remain available. This review does not choose a frontend library,
desktop framework, hosting service, or a measured winner between surfaces.

## What is actually implemented now

The inspected implementation is `compose/instructions_ui.py`, its CLI entry and
current entry documentation. Dated browser prototypes are mockups, not a GUI
client of the shipped InstructionsStore, and are not evidence of implemented
Team, Domain knowledge, Decision memory or P2P/GitHub capabilities.

| Current capability | Source evidence | Limit relevant to the new design |
| --- | --- | --- |
| Instructions library, editor, Preview → Apply | [App and bindings](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:210); [store calls](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:901) | The UI delegates reads/plans/apply to its supplied store. It is not a Team governance or memory authority. |
| Searchable tree and document reading | [Library/search](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:490); [matching](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:531) | Case-insensitive substring search covers named item fields/domains. It is not semantic retrieval or a qualified current-memory reducer. |
| Automatic document display, guide links, member selection | [Cursor handling](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:644); [guide/qualification rendering](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:594); [member changes](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:679) | Library position follows a stable item ref. These links are display references, not proof of inclusion or delivery. |
| Editable text and consumption placement | [Editor controls](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:301); [payload formation](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:849) | New UI-created items are personal rules. Existing member files and supported hook bindings can be edited; this is not an arbitrary domain/form/graph editor. |
| Unified content/member diff and metadata preview | [Diff creation](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:885); [plan preview](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:901) | Preview renders text plus structured plan details. No side-by-side merge editor, graph comparison, or specialized semantic difference display is implemented here. |
| Effective/installed/change/diff/history reading | [View enumeration](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:44); [non-effective renderer](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:641) | Non-effective views expose JSON-formatted store results. Store recovery history is not the proposed multi-workstream decision memory. |
| On/off staging, remove/restore/recover/reset | [Library contract](/Users/kangmin/Documents/agent-bios-personal/docs/instructions.md:61); [actions](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:943) | Effects concern future activated snapshots. This screen explicitly does not activate a host session. |
| Protected edit target and unsaved-change prompts | [Mode isolation](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:400); [cancel/quit](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:812) | Cursor movement cannot retarget an editor/plan. Draft fields are app-instance state; these paths do not establish crash-restored editor drafts or cross-surface draft continuation. |
| Keyboard navigation and native text widgets | [Bindings](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:215); [documented arrows](/Users/kangmin/Documents/agent-bios-personal/docs/instructions.md:47) | This establishes explicit key routes, not complete keyboard/IME/screen-reader certification. No product-specific copy/export/clipboard action is declared in the inspected module. |
| Terminal and machine entrypoints | [TTY dispatch](/Users/kangmin/Documents/agent-bios-personal/compose/instructions.py:381); [documented machine operations](/Users/kangmin/Documents/agent-bios-personal/docs/instructions.md:25) | A TTY opens the UI; non-TTY defaults to a list and supports explicit JSON operations. A numbered fallback exists on its own route, but normal bundled-UI startup fails explicitly if the bundle cannot load. |
| Locally bundled UI assets | [Bundled entry](/Users/kangmin/Documents/agent-bios-personal/compose/instructions.py:369); [setup contract](/Users/kangmin/Documents/agent-bios-personal/docs/setup.md:70) | The UI dependency bundle needs no runtime download. This does not make host models or future external sources available offline. |

The fixed horizontal library/detail layout, column widths and toolbar minimums
are visible in the [current CSS](/Users/kangmin/Documents/agent-bios-personal/compose/instructions_ui.py:228).
No responsive stacking rule is declared there. That is a layout limitation to
measure at selected terminal widths, not evidence that all narrow terminals
already fail. This review read source; it did not execute a new current-TUI
usability or accessibility test.

The current CLI offers more explicit machine operations than one editor form.
Conversely, the existence of JSON does not make a user-friendly equivalent of a
Team/knowledge operation available before its provider and interaction exist.

## Candidate surface arrangements

These are product delivery options. Costs below are engineering/UX judgments
to validate, not comparative performance measurements.

| Surface | Best-fit jobs to test | Principal cost or limit | Offline/authority condition |
| --- | --- | --- | --- |
| Terminal TUI with CLI companion | Existing terminal workers; compact work brief; scoped inspection; text changes; exact review; peer-package and recovery operations | Dense spatial editing and long comparison need alternate list/form/text modes. Discoverability, terminal selection behavior, Korean input and screen-reader behavior need actual target testing. | Local providers and required assets/bodies must be present. Terminal location is not proof of identity, custody or permission. |
| Local-browser GUI | Ordinary workers receiving invitations/context; environment notebook; documents, tables, differences and discoverable Team administration | Requires a supported local backend/bridge and a reliable lifecycle for launch, reconnect and browser closure. “Browser” must not silently mean hosted-only or browser cache as the sole durable store. | All required application assets and local services are installed locally. A local port or opened page grants no source/Team authority. |
| Native desktop GUI | Repeated maintenance, file/clipboard interactions, OS-integrated launch and established accessibility conventions | Platform-specific packaging, update, window/input and accessibility behavior still need design and tests; native controls do not guarantee usability. | Uses the same local providers and protected host identity stores. Closing a window cannot erase durable pending work or fabricate cancellation. |
| Packaged desktop GUI using an embedded web renderer, including an Electron-style shell | The graphical workflows above with a controlled application window and a potentially shared web presentation | Another packaging/update and privileged-bridge boundary; resource footprint and platform behavior need measurement. A wrapper is not itself a capability or authority model. | Bundle required assets; constrain renderer-to-provider operations; network/GitHub remains optional. Do not create a second embedded business store. |

A hosted web-only client does not satisfy the complete disconnected/P2P baseline
by itself. It can be an optional surface if the same local operating/recovery
paths remain available. An existing host app can also expose the work brief and
the shared machine operations; ordinary users must still have a graphical route
without learning a CLI.

## Capability equivalence does not mean pixel equivalence

The complete requirements remain available across the product. Core setup,
authoring, approved Team changes, use, peer/package exchange and recovery must
have a supported terminal/local-machine route as well as graphical workflows.
They must not require a browser canvas, desktop login, GitHub account or GUI-only
approval record to complete. This is a target contract, not current coverage.

| Capability | TUI / command representation | GUI representation | Same effect to verify |
| --- | --- | --- | --- |
| Read and search | Scoped list, filters, bounded detail and exact expansion; readable text export | Search/list/notebook, linked sections and accessible detail | Same authorized scope, edition/frontier and required qualifications; search failure is not empty history |
| Text/source authoring | Text/member editor or supported local editor round-trip; typed metadata forms | Text/table/member editor with visible field errors | Same canonical draft/source, base/version, validation and proposed effect; no implicit publication or adoption |
| Copy/paste and import | Explicit copy/export of a named body/ref; safe multiline input/file import | Select/copy actions, paste/import preview and file picker | User knows whether they copied a body, reference, manifest or audit excerpt; source permissions apply; pasted text cannot execute as a command or auto-submit a change |
| Diffs and conflicts | Unified diff plus structured before/after fields; explicit conflict resolution form | Optional side-by-side diff/table/graph overlays with a text equivalent | Same exact request and changes; no clipping away a permission, condition, removed rule or targeted correction |
| Knowledge ontology/questions | Entity/relation tables, stable IDs, required fields and question/result lists; supported file import/export | Graph/map/form mode and question/evidence pane | Graph layout is a view. Adding/removing a relation has an equivalent typed operation; no graph-only source authority or required mouse gesture |
| Decision/workstreams | Current-state list, expandable why/history, related-workstream references and event forms | Timeline/lanes plus state cards and linked evidence | Same state-changing closure and unresolved results. Spatial adjacency cannot invent causality; missing rationale stays missing |
| Team creation/join/CRUD | Guided forms and named lifecycle actions with reviewable result | Wizard/sheet/management panel with the same actions | Stable Team ID; bounded founding; actual membership/device/grants; distinct archive/leave/local-forget/close; no GitHub-default auto-upload |
| Approval and administration | Exact request list, permitted diff, approve/reject and execute/recover through shared handlers | Contextual review and management panels | Same requester/author independence, applicable policy and authority checks across routes, including direct CLI/MCP calls |
| Bulk, retention and recovery | Per-item plan/status, explicit package path, continuation/retry by operation | Batch table, consequence review and operation detail | Same atomicity boundaries and individual outcomes; an unknown result is reconciled rather than repeated |
| Offline/P2P and optional GitHub | Local status, configured peer/package exchange, verified acknowledgments, outbox and recovery | Status and synchronization panels with actionable conditions | Local usability separate from connection/copy target; no live-folder mirroring or replication of private keys/native sessions |
| Current/new/child use | Host/recipient selector or exact context reference, bounded body and qualified delivery result | Work brief, use action and recipient-specific inspection | Preparation can share one user intent with use where authorized; actual recipient evidence remains separate from parent/context-cache evidence |

Clipboard/export is an intentional disclosure operation. It should respect the
source's permitted use and explain the scope being copied; a generic “copy all
debug state” must not include credentials or unrelated private context. Neither
surface can promise to recall plaintext after the user has copied it outside
the controlled application. No clipboard implementation is selected here.

## Shared services and state across surfaces

Extend the current pattern of UI clients over owned operations: shared scoped
read/prepare, propose/review, and execute/recover contracts with role-specific
payloads. There is one authority for each source/head and one canonical meaning
for each operation. Do not duplicate a knowledge interpreter, memory reducer,
permission evaluator or mutation engine inside the GUI.

Each client may own selection, focus, expansion and unsent field state. Durable
drafts and pending operations have explicit owners/references so reopening a
window or switching surface can recover them. Moving from TUI to GUI reopens the
same draft or sealed request; it does not copy its approval onto changed input.

For equivalent inputs, every surface must preserve these invariants:

1. Read results retain the same authorized sources, required meaning and
   qualification, although layout and optional excerpt expansion may differ.
2. The proposed effect, target/base and applicable review are the same. A GUI
   disabled button is not the enforcement boundary for CLI/MCP calls.
3. Sealed request and outcome identity survives retries, process exit and
   surface changes. Unknown result does not become a second operation.
4. P2P-only operation is complete. Eligible setup recommends GitHub but does not
   connect, create a repository or upload on selection; a prohibited external
   scope has a usable permitted alternative.
5. A fresh or child context receives necessary bodies and qualifications through
   its actual supported route; no surface substitutes a locator or a parent's
   receipt for that delivery.

Internal protocol stages need not be individual screens. The next wireframes
should show the user's meaningful intent, any required choice/review, progress
and outcome, with technical evidence available on demand.

## Accessibility, input and offline acceptance

Test keyboard-only operation on the target terminals and operating systems,
including discoverable shortcuts, text-field arrow/space behavior, modal focus,
return position and no destructive action triggered by ordinary editing. For
graph and timeline views, supply structured table/list equivalents reachable
without dragging. Test Korean composition, multiline paste and long mixed-script
content; a screenshot cannot establish correct input behavior.

For graphical candidates, test semantic control names, focus, zoom/narrow-window
reflow, error association, selection/copy and an actual supported screen reader.
For TUI candidates, test the actual terminal/screen-reader combination and a
linear machine/text alternative where the full-screen representation is not
usable. Do not label either surface inherently accessible because it uses
native widgets or supports Tab.

Run the same operation with the network unavailable after installation, with
GitHub never configured, and after a week with no peer contact. Verify installed
assets and required bodies, preserved drafts/outboxes, explicit stale/unknown
conditions and recovery after contact returns. GUI asset availability, source
availability, permission validity and model/host availability are different
preconditions; each failure must identify the affected action.

## Recommendation and decision gate

Preserve the existing TUI/CLI as a supported operational route. Prototype the
graphical environment notebook for source maintenance and Team administration,
and the compact work brief in both terminal/host and graphical surfaces. This
tests the two audience/job hypotheses from the latest review rather than forcing
every visit into either a task dashboard or a storage tree.

The graphical packaging choice remains open until the required local launch,
file/input, accessibility, offline and maintenance behavior is exercised. A
local-browser implementation can test the graphical interaction without claiming
it decides native versus embedded-renderer desktop packaging. Do not require
maintaining several production GUI stacks merely to compare wireframes.

Evaluate equivalent journeys: first Team/environment/use, returning after a
change, editing and reviewing a source, inspecting a cross-workstream decision,
recovering missing material without GitHub, and distinguishing Team closure from
local removal. Add an expert table/graph/bulk task so GUI is not judged solely on
short reading, and an ordinary nondeveloper task so TUI familiarity is not assumed.

Observe comprehension, completion, wrong-object actions, input/review errors,
assistance and recovery. Measure actual time and effort rather than choosing by
screen count. A simpler-looking candidate cannot win by losing required actions,
hiding qualifications, granting extra rights or requiring the other surface for
every difficult core operation.

This review makes no runtime change and no final claim that TUI-only, browser,
native desktop or embedded-renderer desktop is optimal. Its conclusion is that
the common operating contract should remain complete while interaction and
packaging are tested against the real worker and maintainer jobs.
