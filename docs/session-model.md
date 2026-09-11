# Sessions, storage, and verification

[← Overview](../README.md) · [Corpus](corpus.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

**Library → selection and edits → immutable snapshot → configured session**

## Corpus ownership

Single source of truth for the instructions and scoped guides that an explicit
agent-bios launch supplies to Claude Code or Codex. Edit once; the private corpus
compiler projects the selected content for each activated session.

A deployable instruction corpus for coding agents, plus the CLI that
installs, verifies, and evolves it. The npm package ships the corpus; `install.sh` is both the
`agent-bios` CLI entry and the deployer.

## Authored layers

Two authored layers:

- **Always-in-an-activated-session instructions** — `claude/CLAUDE.md` is the English canonical and `codex/AGENTS.md` its generated host projection. They hold compact invariants, decision principles, and guide pointers. A clean private install does not copy either file into a host's global discovery path; `compose/corpus_catalog.py` inventories their registered items and compiles the selected rules into an immutable session snapshot.
- **Scoped guides** — `claude/guides/`, with generated Codex mirrors. The snapshot compiler copies selected guides to private generation-qualified paths and emits their router. Procedures, tables, numbers, and environment-specific content live here.

## Activation and Vanilla

The private install does not replace the `codex` or `claude` shell commands by default. Run
`agent-launch claude` or `agent-launch codex` explicitly to open the preflight, or pass `--preset NAME HOST` for a
configured non-interactive launch. Software Engineer / Vanilla structurally projects
no agent-bios snapshot, launch contract, tier binding, or permission flag. After a
fresh private install—or after an explicit legacy migration—the native CLI therefore
receives no automatic agent-bios content; the user's own native global and project
instructions still follow the host's normal loading rules. `--resume-session ID`
loads the recorded host/session pin rather than resolving current defaults.

Per-item on/off overrides take precedence over launch-domain selection. See [corpus selection](corpus.md#manage-the-library). Existing host globals are loaded by default; [selective exclusion](advanced-launch.md#global-instruction-files) is a separate host-specific option.

## Storage layout

From a clone, `bash install.sh install` is the same default path. The release lives
under `~/.local/share/agent-bios/runtime/releases/`; baseline tuples and transaction
journals live under that runtime root, immutable snapshots and pins under
`~/.local/share/agent-bios/sessions/`, and user packages, overlays, tombstones,
learnings, history, and trash under `~/.config/agent-bios/corpus/`. The corresponding
`AGENT_BIOS_STATE_DIR` and `AGENT_BIOS_CORPUS_DIR` environment variables relocate
those private roots; `AGENT_LAUNCH_VENV` relocates the optional Textual runtime.
The owned `agent-launch` entrypoint exports `AGENT_BIOS_PRIVATE_CORPUS=1` and the
immutable `AGENT_BIOS_PACKAGE_ROOT`; the launcher also recognizes the private install
record when the explicit marker is absent. These select the private runtime and do not
claim that any host session has loaded a snapshot.

## Verification and limits

`agent-bios verify` checks the recorded immutable release file-by-file, reloads a
non-empty catalog from that release, matches the store's last successful baseline to
the install record, and verifies the owned launcher/profile/status projections. Its
result says `activation: unverified`: neither stored bytes nor a dry-run argv proves a
host loaded the snapshot.

Corpus selection seeds future activated sessions, not plain CLI/Vanilla. A one-off
`--corpus-domains` selection applies only to that launch. The store composes an
immutable `ContentRef`; Codex startup preserves the effective native developer
instructions, injects the private corpus and dynamic launch contract, creates and
reads back a durable host thread, then records its pin. Claude uses the per-call
append and requested session id and records a pin only after observing that id in the
native session log. Real-host probes cover Codex and Claude first-turn delivery,
including corpus propagation to a launcher-generated Claude workhorse. Claude
resume restores the pin's exact environment provenance rather than changing an unset
config-home variable into an explicit default. Post-fix authenticated resume remains
unverified. Snapshot pin integrity alone does
not establish that a resumed model request succeeded.

The native Claude plugin bootstrap has advertised selected plugin roots and
qualified corpus agents. An edited corpus `SessionStart` hook ran automatically
through its generated plugin. Codex 0.153.4 discovery retains user, project and session
hooks alongside the selected corpus. A real-host test with a local transport verifies
that a generated `SessionStart` hook runs and injects context after its exact definition
is trusted; the untrusted control does neither. This test uses no external model.
Authenticated corpus-agent execution and native skill-menu registration remain
unverified; they are separate from hook delivery and launcher-tier child evidence.

Pins preserve environment provenance rather than reconstructing it: the host's
config-home variable, and `HOME` when needed for default lookup, retain their
recorded unset, set, or explicitly empty state. A relative native home is resolved
from the recorded canonical cwd. Pins lacking that context fail explicitly at resume;
it is never inferred from the caller's environment.

Named native Codex profiles (`--profile` / `-p`) are not supported for private
activation by the verified 0.153.4 adapter: that host exposes profiles on runtime
commands but not its effective-config app-server surface. The launcher refuses
this combination before creating a session rather than substituting base settings.
Plain CLI/Vanilla profile use is unchanged.

Every activated snapshot retains the immutable private management bootstrap and puts
its exact path in the injected startup text, so `$corpus` has private procedure access
even without native skill discovery. Selected requested procedures are exposed the same
way. This is not a claim that either host registered them in its native skill menu;
native skill registration remains unverified.

## Scope

The repository and npm package contain corpus sources and private runtime machinery,
not a user's authoring state, learning events, snapshots, pins, activation journals,
credentials, native settings, or generated temporary files.
