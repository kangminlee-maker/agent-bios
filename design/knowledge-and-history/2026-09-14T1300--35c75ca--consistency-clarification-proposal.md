---
created_at: 2026-09-14T13:00:57+09:00
head: 35c75ca
kind: design
status: proposed-clarifications-not-applied-to-runtime
review: 2026-09-14T1300--35c75ca--whole-design-consistency-review.md
---

# Proposed minimum clarifications for G01–G04

These are concrete resolutions to the underspecified boundaries in the
[consistency review](2026-09-14T1300--35c75ca--whole-design-consistency-review.md).
They preserve the user's scope and the existing authority/source contracts.
This record does not claim the proposals were independently adopted as Team
policy or that the prototype/runtime gaps have been repaired.

## G01: effective group authority

Treat a membership change that increases effective permissions as an
authorization change, even if the grant row itself does not change. A group
grant must identify its stable group/provider, action and resource ceiling,
governing policy, and one explicit membership-authority mode:

| Mode | Meaning |
| --- | --- |
| Approved membership | Privileges apply only to the approved members who also satisfy the currently required membership evidence. New members need the existing grant-expansion process. |
| Explicit delegated membership | The grant deliberately authorizes a named group's controller/provider to manage eligibility within a stated ceiling and conditions. The delegation itself is governed as privilege expansion. |

Recommend approved membership as the conservative default. An external group
name, service administrator or imported membership list must not implicitly
receive grant authority. The delegated mode is a deliberate alternative for
Teams that already trust a membership authority; it is not a client bypass.

In both modes, evaluate expiry/revocation and the connectivity policy. A known
membership removal cannot be ignored because an earlier approved list contains
the person. Offline clients can use only the evidence their policy permits;
they do not promise instantaneous discovery of an unseen removal.

Approval counts resolve distinct accountable eligible people, not group count,
number of credentials or agent runs. A delegated membership authority still
cannot bypass requester/author independence or grant powers outside its ceiling.

Required tests: an unauthorized group manager cannot self-add into publication;
an explicit bounded delegation admits a permitted member; membership removal
invalidates future dependent use as required; multiple accounts for one reviewer
do not increase approval count. Implementers must select a declared group mode
instead of inferring it from incidental identity-provider behavior.

## G02: preparation basis separate from adopted status

Extend the existing preparation envelope with a semantic selection basis. Names
below are illustrative, not finalized public API fields:

```text
selection_basis
  kind: adopted_environment | exact_candidate | scoped_sources
  exact environment/candidate/source references
  adoption reference and evidence, only if applicable

intended_operation
  discovery/drafting or the requested substantive work
  permitted scope and required conditions
```

An adopted preparation uses the actual edition/adoption evidence. An exact
candidate or derivative retains its identity and unadopted status. A scoped
source preparation names the exact permitted material and bounded project/user
evidence; it need not invent an environment ID just to conduct research.

All modes enforce source rights, Team constraints when applicable, required
meaning, current control evidence and the relevant action permission. Calling
an operation discovery does not grant wider access, bypass Team closure, remove
mandatory requirements or turn substantive execution into harmless inspection.
Only matching adopted evidence supports a Team-adopted readiness claim.

Changing the basis or operation scope creates a new preparation boundary.
Required-subject selection and memory closure still apply to their actual
scope. A legitimate empty lookup remains empty; a denied query remains denied.

Required tests: a new Team can prepare an authorized research draft with no
adopted environment; its result remains unadopted. It cannot mutate adoption or
perform a separately unauthorized action. Required source denial cannot be
escaped by switching mode. Later adopted use resolves the correct exact edition
and conditions instead of relabeling the earlier packet.

## G03: two forms of sufficient memory-state evidence

Distinguish raw-history availability from authorized-state availability. A
reader may establish the qualified state through:

1. The required local event bodies and their state-changing closure, verified
   under the selected frontier and source/recipient policy; or
2. A qualified state artifact issued/attested by the responsible trusted provider,
   when that provider's policy permits the result and its offline use.

The second form must bind at least:

- issuing authority identity and verifiable trust/authorization evidence;
- permitted subject/query, source scope and recipient/audience restrictions;
- exact frontier and bounded coverage of the stated result;
- interpretation/reducer semantics version or declared equivalent contract;
- returned state body, material unknowns/conflicts and required qualifications;
- applicable control/retention evidence and offline validity conditions.

This is a serialized authorized reader result, not a new accepted domain claim
or arbitrary summary store. Its body may communicate a correction's permitted
effect while withholding the confidential event. It must never claim that all
private events were delivered or that the client independently reconstructed
them. Hidden record identities/counts remain protected where required.

The receiver verifies the artifact and supported semantics. Unknown, stale,
wrong-scope or insufficient evidence returns an unresolved/unsupported result.
A cached model explanation, a hash with no body, or a copied provider label
cannot stand in for the attestation. Known new controls/qualifications are
re-evaluated before reuse; the artifact does not certify global latestness.

Required tests: a valid qualified artifact carries the corrected state without
private event text; a forged/stale/wrong-audience one fails; a client unable to
interpret its semantics reports unsupported; no fallback revives the old
visible decision. If the provider cannot supply this alternative, the dependent
offline case remains explicitly incomplete rather than weakening confidentiality.

## G04: logical continuation separate from host creation

Archive continuation policy must name the existing work it covers, the allowed
scope and whether recipient rehydration/replacement is permitted. A stable
work reference may come from an existing host/workstream or prior operation
evidence; this does not introduce mandatory task-tracker registration.

The preparation records `continuation_of` when supported and separately names
the actual planned/created host recipient. Creating a new host context is not
automatically new Team work, but an unsupported assertion of continuation is
not permission to start a new task either.

Rehydration/replacement requires valid continuation authority, recipient/source
access and compatible context. Broader task scope, new Team decisions or a
changed environment require their own allowed operation. When policy or work
identity cannot be established, report the specific unmet condition. Keep
permitted historical reading and bounded local observations available where
their policies allow them; do not invent an emergency approval.

This clarification applies to archived Teams. Permanently closed Teams still
prohibit future Team work. Evidence-only recovery after closure is a separate
read/retention operation and cannot reactivate the Team.

Required tests: an authorized same-work replacement succeeds; unrelated new
work fails; a changed scope or revoked source right fails; absent continuation
evidence does not silently default to either ready or adopted. If a concrete
Team wants broader continuation, change its policy through existing governance.

## Closure plan

These changes belong in shared reader/authorization/lifecycle contracts, then
all clients and their fixtures. They do not require four new services or a
universal record schema. Keep exact scenario fixtures with both permitted and
rejected cases. A scope-specific state/result must flow through navigation;
independent screenshots cannot masquerade as one continuous operation.

Prototype P01 needs one declared capability model, P02 needs preserved incoming
preparation/custody state, and P03 needs evidence recovery separate from revival.
Correct successor artifacts and demonstrate the original failure no longer
occurs. The underlying runtime must later enforce the same rules outside the UI.
Until then the consistency review's findings remain open with concrete remedies.
