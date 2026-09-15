---
created_at: 2026-09-14T16:59:46+09:00
head: 35c75ca
kind: review
status: identity-design-integrated-not-runtime-tested
ssot: 2026-09-14T1654--35c75ca--consolidated-design-ssot.md
---

# Identity and optional authentication integration

The complete [16:54 SSOT](2026-09-14T1654--35c75ca--consolidated-design-ssot.md#s07-identity) adds U19 without changing the
three content roles, Team authority, P2P foundation or source constraints.
[CURRENT.md](CURRENT.md) now resolves this full successor. The former design and
its visualization are preserved and explicitly labeled prior-revision; no new
browser/visual certification is claimed for this extension.

## Integration and source checks

The design distinguishes automatic opaque person/Team IDs, replaceable device
credentials, verified external identity bindings, Team membership and scoped
grants. Personal first use requires neither product signup nor synthetic Team
creation. Team enrollment supports a complete manual/device route and optional
Google/Slack/OIDC connections. Connecting/authenticating does not confer rights.

Official provider documentation was checked on 2026-09-14 with Context7 and
primary-source web reads. The [source inventory](2026-09-14T1654--35c75ca--ssot-sources.json)
records those URLs and retains prior source hashes. The cited facts cover stable
Google subject and hosted-domain checks, Slack identity/workspace claims,
separate sign-in scopes, and native versus confidential code exchange. The auth
bridge and offline Team credentials are product design choices inferred from
those constraints, not provider features claimed to be implemented here.

A delegated authority/identity review found the retained first-entry row still
required Team creation or invitation. The successor now explicitly permits
personal work with no Team in S10/S11 and its first-work acceptance in S12. The
review found no other required repair in its limited added-contract scope.

Explicit checks cover all nineteen requirement rows, fourteen main anchors plus
the identity subsection, purpose projection, local links, terminology and unchanged
input identities. Product-purpose and decision-ledger validation are run in this
turn. These checks do not test OIDC endpoints, callback deployment, cryptographic
credentials, actual enrollment, directory synchronization or runtime authorization.

SSOT SHA-256: `6965edbfd429605c25f57152e11ed939aa86b4bcb3706003c0883baca73e9085`.

## Remaining implementation proof

Before shipping: prove account-free first work; manual shared enrollment; configured
Google/Slack claims/callback handling; same-email conflict and guarded linking;
wrong issuer/audience/workspace, replay and missing fresh authentication; identity
continuity across devices/provider replacement; scoped revocation and offline
expiry; and unchanged reviewer independence. Provider registration/consent and
protected callback/secret hosting are real operator steps, not zero-configuration
promises. Automatic directory/SCIM management and a managed central identity broker
remain explicitly outside this initial mechanism.

No live provider connection, OAuth consent, Team/member/grant change, message,
publication, runtime edit or deployment was performed. The old visual map still
omits personal-first-entry and optional auth details and is labeled accordingly.
