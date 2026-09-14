---
created_at: 2026-09-13T20:27:28+09:00
head: 35c75ca
kind: design
status: accepted-scope-amendment
amends: 2026-09-13T1857--35c75ca--environment-storage-design.md
---

# Team is the basic work-environment unit

The user selected **Team / 팀** as the basic unit for choosing, adopting, and sharing a work environment. Company is no longer the generic name for that unit. A team may belong to a company or organization, but a company is not a prerequisite for a team environment.

This is a scope and terminology decision for the proposed architecture, not a claim that team storage or membership management is implemented.

## Meaning

A team is the group on whose behalf a work environment is selected and shared. Instructions, Domain knowledge, and Decision memory are composed for that team's roles and work. Industry, company, organization, and project remain applicability or ownership context where relevant.

Team identity, environment identity, and environment edition are distinct. A team can use several environments for different roles or projects; several teams can adopt the same published edition. Each adoption identifies the team and exact selected edition. No one-to-one relationship or mandatory company/organization/team hierarchy is introduced.

## Authority and isolation

Team adoption does not grant access or publication rights to referenced material. An organization, company, individual, or other provider may still own a source and its access, export, retention, or offline requirements. The team may further restrict those requirements but cannot relax them.

Changing teams requires reevaluating the target environment's permissions and compatibility with existing context. Compatible, authorized context can be reused. Incompatible previous Instructions, retained conversation, or unmet isolation requirements require an appropriate fresh or isolated work context. A team-name change alone is not evidence of completed activation.

## Reading earlier designs

| Earlier generic wording | Current meaning |
| --- | --- |
| Our company's work environment | Our team's work environment |
| Company selects/adopts an edition | Authorized team representative selects/adopts an edition |
| Company-approved composition | Composition approved for the team |
| Company A versus Company B example | Different teams, possibly in the same or different organizations |
| Company/source ownership or legal/access boundary | Retain the actual owner and boundary; do not reduce it to a team label |

The earlier versioning, publication, synchronization, operation receipts, memory frontiers, conflict handling, and completeness contracts remain. Team is the basic adopter/sharing unit; it does not merge the source providers or change their authority.

The canonical purpose in AGENTS.md, its README projection, the Korean reference, ontology purpose PU-19, and the current explanatory visualization use the team-based terminology. Root CLAUDE.md receives the purpose through its existing AGENTS import. Dated design/research records preserve their wording; this amendment supplies the updated interpretation.
