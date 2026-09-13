---
created_at: 2026-09-14T01:27:08+09:00
head: 35c75ca
kind: direction
status: user-selected-setup-default
amends: 2026-09-14T0114--35c75ca--peer-default-with-github-sync.md
---

# GitHub connection is the recommended setup option

The user selects GitHub connection as the recommended default option in team
environment setup. P2P remains the complete operating foundation. This advances
the shared-environment purpose by making routine state retention and exchange
convenient without introducing a required external service.

## Setup contract

| Option | Presentation | Effect |
| --- | --- | --- |
| Connect GitHub | First and initially selected; Korean label `GitHub 연결 (추천)` | Configure the permitted repository and synchronization scope through the supported connection flow |
| Use P2P only | Visible alternative; Korean label `P2P만 사용` | Complete setup and operate without GitHub; connection can be added later |

The selected recommendation is a UI default, not an already established
connection. Repository binding, existing valid authorization and allowed scope
must be established before transfer. It does not authorize uploading every local
source, create a repository automatically, or change unconfigured runtime egress.
Reuse valid existing setup instead of requesting the same authorization again.

A failed, canceled or temporarily unavailable GitHub connection must leave a
clear route to continue with P2P and connect later. Do not repeatedly prompt an
environment that deliberately chose P2P only. When an explicitly configured
network/source policy forbids GitHub, default that scope to the permitted P2P
route and explain the restriction; do not invite an impossible connection.

## Acceptance and status

Verify the recommended option is initially selected in eligible new setup,
that selection alone makes no connection or upload, and that P2P-only completion
requires no GitHub account or repository. Also verify canceled/unavailable
connection, later connection, and the explicit restricted-scope exception.

Approval, finalization, adoption, peer retention and offline-use rules remain
those in the preceding design. This records the setup design and user decision;
it does not claim the new team setup or P2P/GitHub adapters are implemented.
