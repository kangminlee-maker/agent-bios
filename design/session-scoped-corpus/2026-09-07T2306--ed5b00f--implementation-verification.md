---
created_at: 2026-09-07T23:06:00+09:00
head: ed5b00f
kind: handoff
---

# Private corpus management: implementation evidence

This records the dirty working tree on the stated date, not a release or a claim
about a live installation. Existing model-binding, prompting-guide, launcher UI,
and preset work was preserved. No commit, publication, or live-home deployment
was performed.

## Implemented surface

| User action | Implementation and effect |
| --- | --- |
| Review | Corpus Studio renders Markdown with a library tree, search, and effective/installed/change/history views. The machine CLI and private management bootstrap read the same store. |
| Create/edit | A Markdown editor and consumption enum submit a deterministic plan. Apply checks the source revision and optional item digest before publication. |
| Remove/restore | Tombstones and personal overlays leave immutable installed baselines intact. Individual installed items can be restored; personal items and host learnings can be recovered. |
| Reset | `agent-bios reset` previews. `--apply --yes` resets future authoring/selection, restores product defaults, archives local launcher overrides, and disables configured ingestion. Tokens are removed without being copied into archives or journals. |
| Configure a session | Explicit configured launch compiles an immutable snapshot and records an observed native session id. Plain CLI and Vanilla receive no automatic private corpus. |
| Resume | Read the exact pin, verify snapshot files, use the recorded native config home and argv. Recovery reconciles a prepared intent against exact host evidence. |
| Delete everything | A deliberately empty selection is valid. The snapshot retains the management bootstrap and can restore/create items; installed catalog validation still requires real source inventory. |

The source/compiler/store, CLI/TUI, installer, and session adapter live under
`compose/`. `install.sh`, `launch/agent-launch.py`, and the learning collector
route their live paths into these components. Installation stores content in
private owned directories; it does not inject native globals, register host
hooks/skills/agents, or intercept the user's shell. Legacy migration is explicit,
ownership-checked, backed up, and preserves the original learning event bytes.

Learning capture uses the existing collector-v1 record, including `lesson`,
`learning_id`, and `created`. Edits affect overlays, not captured/uploaded bytes.
Promotion suppression requires exact source and selected replacement evidence.
Local deletion/reset makes no claim about remote deletion.

## Verification observed

- `/Users/kangmin/.local/share/agent-launch/venv/bin/python -m unittest discover -s compose -p 'test_corpus*.py'`: **53 passed**. Textual was installed, and real Codex checks ran rather than skipping.
- Real npm-layout lifecycle: package extraction, private install/verify, public CLI CRUD, actual `learn --host codex --no-upload`, snapshot composition, Vanilla/configured dry-run, reset, and uninstall. Native canary files remained byte-identical; prior snapshot bytes were retained.
- Real Codex 0.153.4: effective native developer instructions plus project/global canaries survived prompt rendering; a thread was persisted with `thread/start` + `thread/inject_items`, read from a new app-server, and recovered after a simulated pre-pin process loss. No model turn or inference request was used.
- Real mounted Textual widgets at **80×24** and **100×30**: action reachability, keyboard/mouse navigation, document editing, dirty cancellation, learning removal/recovery, and immutable snapshot inspection.
- Negative controls: stale revision/digest, incomplete or forged ownership records, symlink paths, corrupted snapshot bytes, nested `inventory.json` members, compiler output overwrites, wrong native session evidence, migration record conflicts, and promotion without replacement proof.
- Package boundary, surface contract/self-test, ontology agreement, generated mirror agreement, lexicon, content hygiene, bootstrap skill validation, Python compilation, and `git diff --check` passed. New untracked files were made visible to git-enumerating checks through a **temporary index**, not the user's real index.
- Endpoint contract passed with **48 loopback assertions**. Transport seam coverage passed for **106 statements in five functions**, plus its five negative controls. Private-dispatch endpoint controls were retargeted to exactly one live site; dry-run and ambient-endpoint mutations were observed failing by name.
- The final full endpoint self-test exited **0**: positive control plus **75 planted violations** failed by name, including the corrected private-dispatch controls and the mis-declared-control rejection. Its owned subprocess completed; no background self-test remains.
- Publication-provenance self-test passed with an owned temporary npm cache. This exercised scratch repositories; it did not publish this tree.

## Independent review and corrections

The independent reviewer seat `/root/private_runtime_review` (REVIEWER) found
four initial material defects: collector record mismatch, successful install not
advancing the selected baseline, unproven promotion suppression, and silently
unqualified selection. All four were fixed and re-reviewed as closed. A later
review found prepared session intents were not reconciled against real host
evidence; that was fixed and its actual Codex recovery test passed. Narrow final
reviews accepted exclusive compiler outputs and empty-corpus recovery.

SpawnGate: Independence REVIEWER spawn — existing isolated reviewer seat reviewed runtime boundaries alongside useful implementation work.

SpawnGate: Parallelism WORKHORSE spawn — store/catalog, UI/CLI, and private installer ownership were separated; follow-up work reused those seats.

The earlier design's Astra cross-validation is recorded separately in
`2026-09-07T2126--ed5b00f--astra-cross-validation.md`; this implementation review
is not presented as an additional Astra or cross-provider run.

## Remaining verification and capability limits

- The complete repository gate is **not green**. The final launcher/binding run
  retains the twelve existing binding/projection/preset-save assertions described
  by the earlier launcher UI audit. One additional stderr-channel failure was
  traced to the sandbox denying the legacy wrapper's audit-log append; it passed
  with a writable temporary native home and outside the sandbox. No wrapper fix
  was made for that environmental result.
- The umbrella's task-related README contract failures were repaired and the
  documentation check rerun. The private collector's environment selector and
  legacy-targeted endpoint mutations were corrected rather than exempting actual
  endpoint configuration or dropping controls.
- Named native Codex profiles are explicitly unsupported by the verified private
  adapter. The installed CLI accepts `--profile` on runtime commands, but not
  `app-server`; reconstructing native semantics from rendered prompt text was not
  adopted. Private activation fails before session creation instead of silently
  selecting base settings. Plain CLI/Vanilla remains available.
- Native Claude first-turn loading remains unverified. Its adapter and trace
  reconciliation are implemented; Claude recovery tests use explicit trace-format
  fixtures, not a claim of real native activation.
- Native hook/delegated-agent adapters and native skill-menu registration remain
  unavailable/unverified. Private skill procedures are reachable through injected
  immutable file paths. Terminal widths below 80 columns are unverified.
- No live installation, authenticated model-generation canary, release, or commit
  is claimed. These need their own scoped verification and user authorization.
