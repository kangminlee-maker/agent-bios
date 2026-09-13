---
created_at: 2026-09-13T18:04:53+09:00
head: 35c75ca
kind: design
status: accepted-purpose-and-terminology
amends: 2026-09-13T1642--35c75ca--minimal-architecture.md
---

# Shared work environments and the Instructions name

## Purpose

The user clarified that agent-bios exists to let workers share an appropriate work environment. Selecting different instructions, domain knowledge, and decision history should let a worker operate within the role and context of a particular profession, industry, and company. A change of worker should not discard the accumulated standards and decision context.

The purpose is:

> agent-bios lets workers compose, share, and inherit work environments from instructions, domain knowledge, and decision memory, so they can carry out their roles within a common organizational context.

This is the direction for the expansion, not a claim that all three capabilities are implemented.

## Accepted terminology

The user explicitly selected **Instructions** as the replacement for the conceptual name corpus.

| Term | Meaning |
| --- | --- |
| Instructions / 작업 지침 | Rules, guidance, and procedures governing how a worker performs a task |
| Domain knowledge / 도메인 지식 | Concepts, commitments, scoped claims, and evaluation criteria needed to understand the domain and make judgments |
| Decision memory / 의사결정 기억 | The capability to retain and use decisions, their stated reasons, and meaningful events across workstreams |
| Work environment / 업무환경 | The selected composition and applicability scope through which workers share the standards and context of a role, industry, and organization |

Instructions names the behavioral component. Playbook is not introduced as a parallel official name. Corpus remains usable as the ordinary word for a collection of material and as a literal name in the existing implementation.

## Effect on the design

The three ownership boundaries, exact version references, and explicit evidence relationships of the minimal architecture remain applicable. Work environment supplies their product purpose and composition boundary.

A shareable environment definition identifies the selected material and its intended role/organizational scope. A task context manifest records a particular materialization for an operation. Sharing an environment does not require every worker to receive identical text or make identical decisions.

The next design pass should connect reusable environment selection to those manifests. It should not equate a work environment with a session, workstream, or host installation. Exact environment schema, composition conflict rules, and version rollout are not settled by this naming decision.

## Current implementation bindings

The operated lexicon changes the existing component's canonical term, with the same concept home. The dependent dialogue concept is called instruction understanding; its Understand! feature and identifiers retain their current bindings.

Current names such as `agent-bios corpus`, Corpus Studio, `compose/corpus_*.py`, `CorpusRef`, `ContentRef`, and stored state keys remain literal implementation bindings. There is no new `agent-bios instructions` command in this change. The retained `corpus` home slug continues to describe real machinery under `compose/`.

The lexicon does not ban the substring corpus: doing so would reject valid current commands, identifiers, ordinary collection terminology, and dated evidence. New conceptual prose uses Instructions; descriptions of current surfaces continue to use their real names.

A full CLI/UI/path migration remains a separate compatibility change. Revisit it when that user-facing migration is undertaken, preserving command compatibility and stored references explicitly. Earlier dated research and design records retain their original wording; this record amends their terminology and purpose.
