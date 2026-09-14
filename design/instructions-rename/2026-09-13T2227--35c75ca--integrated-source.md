---
created_at: 2026-09-13T22:27:17+09:00
head: 35c75ca
kind: review
status: integrated-source
completes: 2026-09-13T1846--35c75ca--handoff.md
---

# Instructions migration integrated

The delegated migration has been integrated into the main working tree. This is source implementation, not a commit, publication, or installation into the user's active environment.

## Scope

Canonical runtime modules/classes, CLI/options, UI and EN/KO/JA labels, active documentation/payload, ontology owners/projections, packaging, and test discovery now use Instructions.

Compatibility remains explicit: the corpus command and older options/environment names, sixteen module shims, existing physical roots/status/lock names, and schema-v1 serialized fields continue to identify their existing interfaces. Historical snapshots, exact references, session pins, bridge generations, dated records, and actual dataset uses preserve their original meaning. The 0.18.0 screenshot retains its original bytes and historical caption.

The current compatibility contract is docs/instructions-compatibility.md. A breaking removal or data relocation needs its own supported migration; no removal release is invented here.

## Isolation and integration evidence

The subagent worked on feat/instructions-rename at /Users/kangmin/.local/share/agent-bios-workbench/instructions-rename-ipz366lz/source, starting from a captured working-tree baseline at 2026-09-13T21:30:51+09:00. That baseline included preexisting setup/understanding and purpose work.

The migration-only manifest contained 207 changed/added/deleted paths and 43 explicit rename mappings. Applying its patch to a separate baseline copy reproduced every target hash. The source worker preserved 286 captured historical/decision/output files.

Main integration compared current files against that baseline rather than replacing the checkout. Only the main-side SURFACES.md purpose introduction needed a three-way merge, which completed cleanly. The integration receipt and before-files are retained at:

- /Users/kangmin/.local/share/agent-bios-workbench/instructions-rename-ipz366lz/main-integration-20260913T221513/
- /Users/kangmin/.local/share/agent-bios-workbench/instructions-rename-ipz366lz/migration-delta-manifest.json
- /Users/kangmin/.local/share/agent-bios-workbench/instructions-rename-ipz366lz/migration-rename-map.json
- /Users/kangmin/.local/share/agent-bios-workbench/instructions-rename-ipz366lz/remaining-corpus.json

Comparing all 679 intended source paths after integration found only the explicitly retained main-side documentation and decision-ledger differences. No migration runtime differences were present at that check. Main index writes were not used.

## Explicit post-integration adjustments

- Preserved the main SURFACES introduction tying efficient consumption to the canonical team purpose.
- Added installed-version guidance to README, its Korean reference, and docs/instructions.md: source-level canonical names do not imply an already installed older CLI recognizes them; the supported corpus alias remains usable.
- Updated this turn's new consumption design to point to the verified canonical instruction-module owners.
- Clarified the slide-writing RUNBOOK's job-owned output path to include its job placeholder in EN/KO sources, then regenerated mirrors. Main has an ignored output directory, which caused the package gate to classify a bare output/deck.html example as a repository path. The isolated tree lacked that directory. The clarification preserves the actual output layout; no user output or gate rule was removed.
- Normalized trailing blank lines in three uncommitted dated notes, including the team-scope amendment, without changing their wording.

The frozen subagent manifests remain evidence for its original tree. These later prose changes are named here instead of being attributed to that earlier validation.

## Validation

The subagent's final parity umbrella exited successfully: 523 runtime tests and 24 slide-writing tests, plus the generator/package/ontology/endpoint/negative-control legs. Additional evidence covered 12 compatibility cases, 32 migration cases, 23 app cases, 72 benchmark artifact controls, and an isolated 146-entry packed install.

The actual captured-baseline upgrade preserved a personal reference, 111 original snapshot files, the old session pin, and the old bridge generation while refreshing registration.

After integration, the 12 compatibility cases passed in main. Purpose, surface, ontology/projection, lexicon, package, endpoint, mirror, and whitespace checks passed within their recorded scopes; the package check was rerun after the RUNBOOK clarification. The endpoint check retained the no-default-transport contract. The full parity umbrella was not redundantly repeated for the merged purpose/availability prose; validated code identity and targeted integration checks were used.

The complete author benchmark self-test was not completed because its author's legacy deployed-manifest fixture was absent. The affected benchmark import and persisted artifact controls passed separately. No credentials or live model dispatch were used to satisfy that prerequisite.

Domain knowledge and Decision memory consumption remain proposed design work, documented separately. The rename does not implement those readers.
