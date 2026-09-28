---
created_at: 2026-09-14T18:15:39+09:00
head: 35c75ca
kind: review
status: storage-scope-intake-design-integrated-not-implemented
---

# Storage, repository/Team scope and intake integration review

The [complete SSOT](2026-09-14T1752--35c75ca--consolidated-design-ssot.md) incorporates U20/U21:
concrete source bundles and local state, repository versus Team ADR home scopes,
provided/added knowledge and typed learning/distillation intake. The
[development specification](2026-09-14T1752--35c75ca--development-spec.md), [task graph](2026-09-14T1752--35c75ca--development-plan.json)
and [test catalog](2026-09-14T1752--35c75ca--test-catalog.json) carry the implementation implications.
Backward compatibility remains explicitly unnecessary.

## Decisions integrated

- One source/acceptance authority per collection, with package, repository-authored
  or managed source home. Versioned JSON manifests bind Markdown/table/attachment
  members. SQLite stores scoped durable operation/reference/control/outbox state
  plus named derived indexes; it is not wholly disposable or the peer sync payload.
- Source ownership, repo/Team/personal home, applicability, provenance, acceptance
  and physical copies remain distinct. Clone/fork/branch observations and same-number
  ADRs preserve verified source identity. Combined reading has no automatic scope,
  supplied-source or timestamp winner.
- A candidate from authored/imported/learned/distilled input retains exact evidence,
  actual actor qualifications, selected source frontier, intended recipient/scope
  and request identity. Destination commit and any Team adoption are separate.
- Current light learning projects selected future personal Instructions; heavy
  distillation produces author-side Instructions candidates. The new typed pipeline
  cannot reuse their destination, filtering or packaging assumptions unchanged.

These were recorded as D-20260914-b9074f and D-20260914-1b0aaf. SQLite's official
transaction and backup documentation informed its bounded local use; it does not
supply cross-filesystem or distributed atomicity. The source inventory records URLs.

## Review and checks

Three read-only delegated perspectives inspected source/storage, capture/promotion,
and workflow/test integration. The added source and intake clauses had no required
repair in those bounded reviews. Workflow review found CAP-14's installed-package
case incorrectly selected at P17 even though it requires P18. It is now assigned
to P18; the checker enforces atomic case prerequisites and its negative control
reintroduces that error deliberately. No reviewer output is a runtime proof.

The current plan has 20 tasks and 33 test families.
N27/N28 add 26 proposed positive/negative case pairs. P19 depends on P06 only;
P15 consumes P19's candidate workflow; M1 remains independent of Team, SSO, GitHub
and P19. All product tasks/cases remain planned and not implemented. P01 freezes
actual executable cases/adapters; empty unresolved bindings are not passing suites.

The plan checker passed 19 negative controls plus positive/ownership controls,
acyclic and implementation-owner coverage checks for U01-U21/W01-W10/C01-C12,
phase scope and downstream-case checks, and selected input-hash verification.
Only P00 is initially ready. The checker never runs product tasks.

The selected brownfield evidence grew to 86 files after reading collector,
promotion and heavy-distill sources. The previous baseline comparison detected
three changed files (ontology graph, Instructions domain catalog and staged-workflow
guide). Their current UI-guide-related content was reread and retained; the new
manifest records old/new hashes and disposition. No concurrent changes were
reverted. This evidence still is not the complete P00 execution baseline.

Purpose projection, local links/anchors, JSON/Python syntax, explicit untracked-file
terminology and decision-ledger validation are checked in this turn. Previous
38 current-runtime tests are retained only as prior 17:20 evidence; they were
not re-executed or used to certify the changed catalog/new target. No new runtime,
SQLite store, extractor, repository binding, identity provider or live model call
was executed. No user data, repository source or package was published/migrated.

## Bound target documents

| Artifact | SHA-256 |
| --- | --- |
| consolidated-design-ssot.md | `38a45dca852d99a0db24ffa7e149d3e4e3edbaf79d194123edfea485be5c9dea` |
| development-spec.md | `12ea65dcd2b155e8fe424d78fbee6ae5fb2eea7c886871286753bf6b7a7e8106` |
| development-plan.json | `22da36d3320de05d9bfb4bcdec0dc2e5fa5696d494efe3571a51fee4b54c0889` |
| test-catalog.json | `6be44eb4c15d6729e7f8747f7ae11665188bb8761ad73562f743d62b8c9c947a` |
| brownfield-evidence.json | `a225d97b6afaedeb406804bacedaa012fa6cd28947e113cb154a0ec448d0df77` |
| check-development-plan.py | `ce017762e2649f86e8128dff5c810d76c2bf956444b06ad81335be35fd5f21ba` |

The earlier 15:04 visualization remains explicitly historical. No new visual or runtime qualification is claimed by updating the design documents.
