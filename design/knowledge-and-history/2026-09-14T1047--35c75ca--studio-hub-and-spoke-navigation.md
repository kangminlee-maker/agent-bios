---
created_at: 2026-09-14T10:47:58+09:00
head: 35c75ca
kind: design
status: proposed-entry-and-navigation-map
amends: 2026-09-14T0914--35c75ca--studio-wireframes-and-surfaces.md
---

# Studio entry and hub-and-spoke navigation

## Intent

Use a conditional entry and a Team/environment context hub to make the existing
wireframes understandable as one product. The hub helps users find the next
meaningful action; it does not require every action to begin or end there.
This serves the product purpose by retaining the chosen Team, shared standards
and work context while moving between reading, authoring, review and recovery.

The hub is an interaction concept, not a centralized source store or server.
The P2P foundation, optional recommended GitHub and separate authority/approval
contracts remain unchanged. The graph's edges mean navigation, not dataflow,
permission grants or compulsory ordering.

## Conditional entry

| Arrival | Initial destination | Boundary |
| --- | --- | --- |
| No known Team and no invitation | Create a Team or open a received invitation | Creation W06 differs from enrollment W07; no hidden pre-created environment |
| Known authorized Team/environment | Studio home in that context | Name the selected environment; allow choosing another without changing an active task |
| Exact source/work/review link | Requested authorized target, with a scoped explanation if unavailable | Do not require a home visit; do not infer access from the link |
| Invitation | Permitted invitation detail and enrollment process | Consent and registered membership are distinct; no private Team-management detail before authorization |
| Existing host work | W01 work brief or W09 actual recipient/handoff | Preserve actual host/work identity; do not require new task registration |

When several Teams/environments exist, expose the selected one and a clear
switching route. When a known Team has no environment, its home directs the
user to W02's first-environment setup. Incomplete founding, unavailable source
rights or expired offline conditions name the affected operation rather than
turn every action into a generic global failure.

## Home and five spokes

The home presents two prominent ordinary intents—work with the selected
environment, or explore/maintain it—and direct routes to review, Team management
and exchange/recovery. Relative prominence is a testable presentation choice;
the user's real permissions and pending work determine available actions.

| Spoke | Existing wireframes | Intent |
| --- | --- | --- |
| Start, continue and hand off work | W01, W09 | Read useful current context and deliver to the actual recipient |
| Compose and maintain environments/material | W02, W03, W04, W10 | Browse composition, instructions, knowledge, decisions and search/bulk operations |
| Review proposed changes | W05 | Inspect the exact proposal/effect and record a permitted approval or outcome |
| Create and manage Teams | W06, W07 | Found/join/manage/transfer/archive/restore/close the identified Team |
| Exchange data and recover | W08 | Inspect local and unshared work, missing bodies, retained copies and uncertain operations |

All ten screen families are reachable. Instructions source editing is a direct
owned-source route from W02; it is not lost because its source editor shares a
family with other material management. Removing an environment reference still
does not edit/delete that original source.

## Spoke-to-spoke paths and returns

| From | Direct path | Return behavior |
| --- | --- | --- |
| W01 current work | W03 support/evidence or W04 recorded reasons | Return to the same task, Team, selected edition and reading position |
| W02/W03/W04/W10 authoring or transfer | W05 exact change review | Return to the same candidate/request and actual outcome; preserve unsaved input |
| W01/W09 work/recipient preparation | W08 missing-material or operation recovery | Re-evaluate that original preparation; receipt or recovery alone does not start use |
| W06 first Team | W07 governance/enrollment, then W02 first environment, then W01/W09 | Preserve the new Team ID and actual state; no fixture or identity substitution |
| W07 Team governance/lifecycle | W05 review or W08 custody/recovery | Return to that Team and named operation, not an unrelated default Team |

Navigation state retains origin, selected object, draft reference, exact sealed
request where applicable, scope and return location. Do not silently rebase an
approved request when returning to it. Recheck relevant access and qualification
changes before presenting an old answer as currently usable.

`Back to where I came from` and `Studio home` are different routes. Returning
home should not clear a draft, widen authorization, complete an invitation, or
change the current worker context. A denied/revoked target can return to an
authorized origin without exposing its restricted body or metadata.

## Map and entry wireframe

The interactive companion has a map view and an entry-screen view. Selecting
an arrival type changes the entry example; choosing a spoke expands its
wireframe IDs, direct paths and return behavior. A small navigation trace
demonstrates nested movement and return. It deliberately executes no source,
Team, approval, transfer or host-delivery operation.

- [Interactive navigation source](2026-09-14T1047--35c75ca--studio-hub-and-spoke-prototype.html)
- [Navigation QA and limits](2026-09-14T1058--35c75ca--hub-navigation-qa.md)

The map uses hub-to-spoke connectors on wide screens. Narrow screens place the
hub above its labeled spokes without misleading crossing lines; the selected
route and return text remain explicit. This adaptation is presentation only.

The five-spoke diagram is a proposed information architecture, not a permanent
requirement for five cards or five first-level menus. Actual entry frequency,
findability and comprehension still need user observation, as in the zero-base
review. A knowledgeable user can bookmark/directly open their authorized target.

## Acceptance

- Each W01–W10 family is reachable from the map and has a meaningful origin.
- First-time and invited users remain in their corresponding entry state when
  returning home; navigation does not manufacture membership.
- Work → evidence → back preserves the work destination.
- Authoring → review → back preserves the target candidate/request.
- Recipient → recovery → back preserves the actual recipient and does not
  imply activation.
- The new-Team path does not assume an environment exists after creation.
- The map never presents its center as the storage/consensus authority.

An independent IA review confirmed coverage of the ten wireframes and required
the direct links, invitation distinction, Instructions editing path and origin
preservation recorded above. It did not establish human usability or runtime
enforcement. No shipped runtime code, actual Team or network deployment changes
are made by this navigation design.
