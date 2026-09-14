# Instructions compatibility

[← Instructions](instructions.md) · [Storage and sessions](session-model.md) · [Recovery](recovery.md)

**Instructions** is the current name for the rules, guides, and procedures
component. Compatibility names below identify older interfaces and stored data;
they are not a second component. New documentation and callers use Instructions.

## Commands and environment

| Canonical interface | Accepted older alias | Owner |
| --- | --- | --- |
| `agent-bios instructions` | `agent-bios corpus` | `install.sh` |
| `--instructions` | `--corpus` | installer selection and launcher Studio entry |
| `--instructions-domains` | `--corpus-domains` | `launch/agent-launch.py` |
| `--instructions-native` | `--corpus-native` | `launch/agent-launch.py` |
| `--no-instructions` | `--no-corpus` | app session preview/use |
| `AGENT_BIOS_INSTRUCTIONS_DIR` | `AGENT_BIOS_CORPUS_DIR` | private store and installer |
| `AGENT_BIOS_INSTRUCTIONS_STATUS` | `AGENT_BIOS_CORPUS_STATUS` | status projection and launcher |
| `AGENT_BIOS_PRIVATE_INSTRUCTIONS` | `AGENT_BIOS_PRIVATE_CORPUS` | private runtime selection |

An older environment variable is a fallback when its canonical counterpart is
absent. If both are present with different raw values, the affected operation
refuses and names both variables. It does not choose a value by precedence,
normalize differing values into a guessed match, or select a different store.
Set one name, or give both the same value.

Registered helpers and returned runtime environments bind the already selected
absolute roots under both spellings. This replaces ambient aliases consistently;
it does not reinterpret conflicting settings supplied when selecting the store.

The canonical module owners are `compose/instructions*.py`. The corresponding
16 `compose/corpus*.py` modules remain thin import/CLI shims: `corpus.py`,
`corpus-state.py`, and the `corpus_app`, `corpus_catalog`, `corpus_import`,
`corpus_install`, `corpus_session`, `corpus_setup`, `corpus_setup_cli`,
`corpus_setup_i18n`, `corpus_setup_ui`, `corpus_store`, `corpus_transaction`,
`corpus_ui`, `corpus_ui_runtime`, and `corpus_understand` Python modules. They
forward to the canonical owners rather than maintaining separate implementations.

## Storage and identity

| Retained literal | Reason and owner |
| --- | --- |
| `~/.config/agent-bios/corpus/` | The private store and installer keep the existing default user root. `AGENT_BIOS_INSTRUCTIONS_DIR` can select a custom root. |
| `~/.local/share/agent-bios/corpus-status.json` | The status projection and launcher share the existing status location. |
| `.corpus-store.lock` | `compose/instructions_transaction.py` retains the shared lock name so older and newer writers do not acquire independent locks. |
| `corpus-rollback-*` | The status/recovery machinery retains its recovery-artifact naming contract. |
| `deployed_corpus`, `corpus_storage`, `retained_corpus` | Existing schema-v1 serialized fields retain their spelling for consumers of deployment, setup, and retained-library records. This includes `display.retained_corpus`. |
| `corpus_hash`, `corpus_drift` | Benchmark records retain their existing serialized fields. |
| `corpus-not-loaded` | The compatibility learning migration keeps its recorded skip-result enum. |

The naming change performs no automatic root relocation and creates no second
store or independent writer. Retaining the lock preserves a common exclusion
boundary; it does not establish that every older release understands newer data.

Existing immutable snapshots, exact item references, and session pins retain
their contents and identities. Newly compiled snapshots may have new hashes
because compiler and store implementation bytes participate in their identity.
A historical reference must resolve to its original content or report that it
is unavailable; it must not silently resolve to a newer snapshot.

## Historical and unrelated uses

Dated design records, decisions, source quotations, and captured release images
keep the names used at the time. The image `assets/instructions-studio.svg`
is an actual 0.18.0 capture and retains its earlier Corpus Studio title.

The review-request guides use *corpus* for their research dataset of review
findings. Contributor documentation also uses it for the AGENTS.md/CLAUDE.md
research collection. Those datasets are distinct from the Instructions component.

The reserved operation names are `publish-instructions` and `fetch-instructions`.
Neither has a network implementation, so there is no deployed endpoint to
migrate. The rename introduces no new network traffic.

## Removal condition

The compatibility layer is retained in 0.19.2 and scheduled for future removal;
no removal release is assigned. New integrations use the canonical interfaces.
Removal work covers older command and option aliases, environment aliases, Python
import shims, and old-release adapters. Stored paths, locks, serialized fields and
immutable references require a separate preservation or migration plan before any
related support is removed. Compatibility interfaces can be removed only in
a separately announced breaking release after consumer migration and preservation
or explicit migration of the affected data and references have been demonstrated.
An occurrence count reaching zero is not evidence that those conditions hold.
