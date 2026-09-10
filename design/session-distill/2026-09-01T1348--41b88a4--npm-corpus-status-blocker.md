---
created_at: 2026-09-01T13:48:59+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1337--41b88a4--desktop-selection-hook-boundary.md
---

# Npm corpus-status blocker before desktop selection

## Live result that changed the design

Running `agent-bios onboard` from the published npm 0.14.0 package applied all five domains,
updated `selection.json`, rewrote the deployed corpus, updated `version.json`, passed deployment
verification, and returned zero. It also printed:

```text
note: corpus-status projection unavailable (versions.json/ledger missing?)
```

The note guesses at a secondary dependency. The direct failure is earlier: the npm package does
not contain `compose/corpus-state.py`. `install.sh` suppresses that command's stderr and exit status,
then prints the same generic note for every failure. After the Claude activation canary succeeds,
the `record-apply` call to the same missing script is also suppressed.

The resulting state is split by freshness:

| Artifact | Result of the npm onboarding run |
| --- | --- |
| `selection.json` | updated |
| `~/.codex/AGENTS.md` managed region | updated |
| `version.json` | updated |
| `corpus-status.json` | stale from the prior checkout deployment |
| `last_apply` inside corpus status | not recorded |

The selected set happened to be identical to the prior all-domain selection, so the stale
`domains.applied` value still looked correct. Its timestamp and empty `last_apply` expose the
failure. On a fresh npm-only machine the status file can be absent instead.

## Root cause

`gates/check-package.sh` explicitly exempts `compose/corpus-state.py` as an optional projection.
That premise stopped being true when the launcher's corpus panel became a consumer of
`corpus-status.json`; the proposed desktop onboarding skill would become another required
consumer. The installer treats a now-required state projection as optional, and the package gate
preserves that mismatch deliberately.

Adding only the script to `package.json` is insufficient. Its `project` subcommand currently
requires author-only `design/session-distill/versions.json` and `ledger.json`, neither of which
belongs in the npm payload. Its `record-apply` subcommand does not require those registries, but it
requires an existing status file.

## Revised order

Do not implement the desktop onboarding skill against `corpus-status.json` yet. Repair the
existing runtime status path first, then build the skill on the repaired contract.

### Recommended cause fix — preserve the existing concept

1. Remove the package-gate exemption and ship `compose/corpus-state.py`.
2. Make `project` always derive `domains.available` from the shipped `compose/domains.json` and
   `domains.applied` from installer-owned `selection.json`.
3. In an npm layout without the author registries, produce a valid status with the domain and
   apply fields while representing corpus-version/ledger fields as unavailable. Preserve a prior
   `last_apply` during projection.
4. Keep the full version/ledger projection in a checkout, where the registries and Git history
   exist. Do not ship the author ledger merely to fill optional dashboard fields; npm rollback
   still lacks the repository history it would need.
5. Make the launcher render absent version/ledger fields as unavailable rather than as zero or
   empty facts.
6. Add an npm-package-layout installation test that begins without `corpus-status.json`, applies
   a non-default selection, and asserts a fresh domain projection plus `last_apply: applied`.
   Reverting the packaging or degrade fix must make this test fail by name.

This preserves the existing `corpus-status` concept and its writer. Splitting a second domain
status artifact would add ownership, migration, and synchronization surface without solving a
different lifecycle.

## Alternatives rejected for the default

- Shipping the author `versions.json` and `ledger.json` with the script widens the package boundary
  and exposes curation history, while rollback would still lack Git history.
- Adding a new domain-status artifact duplicates the existing status concept and creates a second
  writer/reader migration.
- Letting the desktop skill read stale `corpus-status.json` makes the UI confidently report a
  selection the latest successful installer run did not record.

## Canary boundary remains unchanged

The final `CANARY PASS` in this run came from `compose/canary.sh`, which probes `claude -p` against
the Claude central bundle. It does not prove that Codex CLI or a ChatGPT desktop Codex task loaded
the managed `AGENTS.md` region. The desktop plan must keep that live-surface verification separate.

## Done when

The blocker is closed when a materialized npm package, not the checkout, can start with no corpus
status, run `agent-bios onboard --domains <non-default-set>`, and leave all of these true:

1. the installed managed corpus matches the requested selection;
2. `selection.json` contains the requested closed set;
3. `corpus-status.json` is newly generated and reports the same available/applied sets;
4. `last_apply` records `applied` for the same requested set;
5. unavailable author-only version/ledger data is labelled unavailable; and
6. the installer exits non-zero if a required domain/apply status write cannot be completed.

Only after that contract is real should the desktop onboarding skill consume it.
