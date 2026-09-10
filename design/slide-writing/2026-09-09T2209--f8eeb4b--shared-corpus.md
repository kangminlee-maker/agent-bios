---
created_at: 2026-09-09T22:09:54+09:00
head: f8eeb4b
kind: design
---

# One shared slide-writing procedure carries its criteria and runtime

The user selected the entire slide writing/judging system for the shared repository corpus, rather than a personal learning or a cross-domain summary alone. Reuse the existing office-work and visualization-docs selections. The item is `@agent-bios/core:skill-slide-writing`; no new global instruction or domain is added.

The source implementation came from a working slide authoring/review exercise. Its twelve criterion blocks (introduction and eleven sections) are translated into English for the model-consumed shared skill. Conditions, exceptions, and relationship distinctions were independently checked against the Korean source. The original source is historical input to this import, not a second translation to edit alongside this package.

`claude/skills/slide-writing/PRINCIPLES.md` owns semantic text; its generated ORACLE and role packets preserve identical criterion blocks. SKILL and RUNBOOK provide discovery and execution procedure, not a second rubric. The six runtime members contain no example deck, font binary, organization-specific source, or user environment snapshot. Tests belong in gates because the private installer rejects test payloads.

The built projection is shipped so consumers can run check/prepare without modifying the installed release or compiled snapshot. Python runs with bytecode disabled; all jobs live outside the corpus. Corpus-native skill menu registration remains outside this claim: the current compiler exposes the requested procedure by its private path.

The author-side gate exercises the original sixteen protocol controls and five integration checks: catalog/source projection, existing-domain membership, compiled relocation with unchanged files, default bundle cleanliness, and real temporary-home private installation. The npm archive also contains exactly the six runtime members and no author-side test.

An independent writer used the compiled English skill to prepare and author one neutral slide; the actual renderer produced one matching PDF page. A different context observed the screen before seeing the source, then submitted twelve criterion judgments. All role criteria were byte-identical and the snapshot stayed unchanged. The reviewer identified a direction arrow that contradicted the parallel relationship. This is evidence of real consumption and one detected quality defect, not universal visual-detection accuracy.

The first full gate used the ambient Python3.13 because the supplied PATH prefix named a directory without python3; the existing transport self-test raised PermissionError. Rechecking that seam with Python3.14 passed. The initial gate invocation also used -B in a form not recognized by the existing reachability scanner. The test file itself disables bytecode, so its umbrella invocation can use the scanner-supported form without modifying snapshot behavior. The final index-snapshot gate is the completion check for these integration fixes.

Publication and installation into the user's current environment are separate operations. This change adds shared repository content for future distribution.
