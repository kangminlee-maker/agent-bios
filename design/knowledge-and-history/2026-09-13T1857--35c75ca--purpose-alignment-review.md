---
created_at: 2026-09-13T18:57:02+09:00
head: 35c75ca
kind: review
status: design-review
reviews: 2026-09-13T1642--35c75ca--minimal-architecture.md
---

# Purpose alignment: from selected material to shared work environments

## Verdict

The minimal architecture is a sound foundation for separating Instructions, Domain knowledge, and Decision memory, but it is **not yet a complete design for sharing and inheriting an organizational work environment**. Its principal unit is a task's selected references. The clarified purpose requires an owned, reusable environment and a reliable way for another worker to obtain and materialize it.

This is a review of proposed contracts against the user's purpose, not a runtime test. The current working tree also contains concurrent setup/understanding changes; those changes were observed but not assessed as completed features here.

## Decision criterion

The canonical purpose now lives in root AGENTS.md and is projected into README.md. Root CLAUDE.md imports AGENTS.md. The structural purpose gate checks those routes; whether a design serves the purpose is a review judgment.

The decisive user scenario is: a replacement worker selects the same organization's environment for the same role and authorized work scope, obtains its standards and relevant decision context, and continues without depending on the predecessor's private session state. A worker using another company's environment must retain that company's distinct standards and access boundaries.

## Findings and minimum changes

| Existing contract | Assessment against the purpose | Minimum correction |
| --- | --- | --- |
| Three separately owned content capabilities | Fits: behavior, domain meaning, and history must not silently confer authority on one another | Retain |
| Stable references and exact historical versions | Fits: enables attributable continuity | Retain, but share source editions rather than host-local compiled snapshots |
| Task context manifest | Necessary but insufficient: a list of refs does not identify the organizational environment being inherited | Every materialization names an owned environment and edition |
| Selection of knowledge/history | Incomplete: the successor may not know the predecessor's record IDs or sessions | Environment identifies discoverable shared memory scopes and required knowledge sources |
| Explicit adoption and local receipts | Fits, but provider acceptance and adoption of a composed environment are separate choices | Add environment-level ownership, approval, and adoption references |
| Refresh at operation boundaries | Incomplete: a worker could refresh away from the approved environment while keeping its name | Pin static components; permit evolving feeds only through the edition's declared selectors |
| Namespace/access language | Directionally correct, insufficient for sharing | Check recipient access and required dependencies; inherited refs do not confer access |
| Deferral of all synchronization | No longer adequate: local consistency alone does not enable worker transfer | Specify portable content, authority, conflict, receipt, and offline semantics now; defer transport sophistication |

## Six purpose scenarios

1. **Worker replacement:** a workstream belongs to the organization/project namespace, not its creator's session. The successor discovers relevant decisions and unresolved states from the environment's declared scope.
2. **Different hosts/models:** both materializations name the same approved edition; differences in adapters, actual source frontiers, and additional native instructions remain visible. Common context does not promise identical model responses.
3. **Same role, different company:** shared professional material can be reused while company Instructions, knowledge, decisions, and authorization remain separate.
4. **Personal variation:** a changed composition identifies its base and changes as a distinct derivative. It cannot retain the claim that its effective composition is the unchanged company-approved edition.
5. **Team update:** publication, organizational adoption, local receipt, local readiness, and host activation are distinct. An existing host pin does not become the new edition by changing a team pointer.
6. **Incomplete access:** a worker lacking a required company decision source cannot be reported as fully ready for the declared environment. Optional omissions are reported; required gaps restrict the affected use.

These scenarios require a small environment composition contract. They do not require a universal knowledge schema, an organization hierarchy engine, a graph database, or a task-management product.

## Revised architectural center

The design should begin with:

**Owned environment → immutable edition and composition → approved selection → worker materialization → operation context → attributable shared decisions.**

Instructions, knowledge, and memory providers remain underneath that chain. Role, industry, company, and project are applicability dimensions, not an automatic override hierarchy. Reuse references exact editions; changing an upstream source produces an explicit candidate update.

A context manifest records one operation's concrete result. An environment edition specifies the reusable selection and permitted evolution. Their identities must remain different, especially when a live memory feed advances between two operations.

## What remains deliberately small

Keep coherent documents/tables before atomic claims, explicit premises before inferred graphs, whole-decision replacement before scope algebra, and existing onto lenses before new review machinery. Continue to defer collaborative text editing, automatic semantic merge, federation, rollout scheduling, and a general permissions engine.

What can no longer be deferred is the meaning of portability, namespace authority, mutable-head concurrency, interruption recovery, offline use, and complete materialization. Those are core sharing contracts even if the first transport is a manually exchanged bundle.

The first proof should use two workers, two organization scopes, one shared professional base, and one ongoing workstream. Demonstrate transfer, inheritance, a concurrent/offline contribution, explicit adoption of an update, and an inaccessible required dependency. This is a more direct acceptance test than merely compiling material from three local stores.

## Validation outcome

Recorded 2026-09-13 10:24:15 UTC. The product-purpose checker passed its positive control, 15 planted negative cases, projection emission, and idempotence check. Package and full parity checks passed against a fixed snapshot of the current tracked work plus this task's new files, without changing the live index; the parity run included successful 509-test and 24-test suites. Concurrent setup/understanding changes were included in that captured tree, not attributed to this task.

After the snapshot was captured, two written storage-contract clarifications and the new gate's ontology anchors/projections were completed. The final ontology check passed against those updated sources. These checks validate the repository change and its structural integration; they do not constitute implementation tests for the proposed shared storage or synchronization protocol.


## Review provenance

Independent delegated passes assessed purpose alignment and storage/synchronization against the existing implementation. Both identified the missing environment-level composition and portability contracts. Their recommendations are incorporated into the companion environment/storage design. These are same-family design reviews; no cross-family semantic validation or new runtime behavior is claimed.
