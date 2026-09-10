---
created_at: 2026-09-07T18:18:00+09:00
head: ed5b00f
kind: design
supersedes: null
---

# Install privately; activate per session

Status: **PROPOSED architecture, with limited real-loader probes.** No installer,
live global file, or runtime activation behavior was changed for this proposal.
The user's direction is recorded as `D-20260907-fe9379`.

The user requires Software Engineer / Vanilla to carry no agent-bios corpus,
installation to leave global AGENTS.md and CLAUDE.md alone, and agent-bios settings
to apply only in sessions that explicitly use it. The product serves people who
can use a CLI but do not build advanced CLI environments themselves. Its entry
points and TUI must make the difference visible.

## Recommended behavior

| Entry | Native user/project configuration | agent-bios |
| --- | --- | --- |
| Plain `codex` / `claude` | Normal native loading | No automatic additions from a clean new installation |
| Software Engineer / Vanilla | Normal native loading, fresh session | No corpus, including core/infra, skill descriptions, or agent-bios hooks |
| Explicit `agent-launch` with an active preset | Normal loading plus the selected session overrides | Selected corpus and verified session registrations |
| Resume an activated session | Resume that session's recorded context and content | Retain its pinned corpus; resuming is not a switch to Vanilla |

"No corpus" means no automatic agent-bios additions. A user-authored instruction
that deliberately imports agent-bios, or an old transcript already containing it,
cannot simultaneously be preserved and treated as corpus-free. Detect known
legacy remnants and explain the required cleanup; do not silently edit user text.

Installation becomes storage, not activation. Reuse the existing `agent-launch`
entrypoint rather than inventing another public command. Shell replacement of
`codex` and `claude` is not a default installation step under the new contract.
Any convenience interception is a separate explicit opt-in. In particular, the
direct Claude wrapper's permission-bypass flag is not part of an ordinary native
CLI invocation.

## Why both installation and other writers must change

Current code contradicts this target in several independently observable places:

- `install.sh:cmd_install` assembles global instructions, deploys skills into host
  discovery directories, merges Codex agent settings, and calls `add_zsh_hook`.
- `compose/assemble.py` seeds Claude imports, replaces the marked Codex central
  span, and merges hooks into the user's settings. `install.sh:cmd_verify`
  currently requires those global registrations.
- `launch/agent-launch.zsh` replaces and reasserts shell functions. Its direct
  Claude path adds `--dangerously-skip-permissions`.
- `learn/collect-learning.py` adds a personal-learning import to global CLAUDE.md
  or a learning region to global AGENTS.md. Changing installation alone would let
  a later capture reintroduce global content.
- `learn/migrate-learnings.py` prunes those global projections, and
  `compose/corpus-state.py:_locked_rollback` republishes global corpus content.
- `launch/agent-launch.py:project_args` returns an empty argv for Vanilla. That
  suppresses launcher additions, not the host's normal global instruction loader.

The migration must cover these consumers and writers together. A new package
selection, learning capture, rollback, or uninstall must not revive global
activation after conversion.

## Mechanisms compared

| Mechanism | Result | Cost and limitation | Disposition |
| --- | --- | --- | --- |
| Startup corpus plus private procedure paths | Selected sessions receive the rules and can read their procedures/assets | Smallest portable route; does not promise native skill menus or event hooks | Baseline delivery mechanism |
| Same mechanism plus session-only native registrations | Adds native agents, skills, and reminders where the host supports them | Two bounded host adapters; actual discovery and merge behavior need probes | Recommended implementation |
| Redirect the host's configuration home | Filters files by changing what home the host sees | Couples corpus to auth, history, databases, preferences, and config writes | Not the default |

Temporary editing and restoration of shared global files is outside the contract:
parallel sessions and process failure must never depend on restoring user files.

Reuse **corpus**, **package**, **domain**, **consumption surface**, **preset**, and
**launch plan**. An immutable assembled snapshot is a projection of those existing
sources, not another authored corpus or a new public concept. Presets retain
launch settings; they do not copy instruction bodies. The launch plan records the
resolved content reference. Vanilla has no such content; an active session with
no optional domains still includes its core/infra content.

## Storage and lifetime

Store installed/assembled content under the existing agent-bios-owned data root,
outside native discovery directories; for example,
`~/.local/share/agent-bios/corpus/<content-reference>/`. Keep user-authored settings
and personal learning sources separately owned and outside overwrite-managed
files. The existing user-owned launcher local files remain user-owned.

The launcher resolves a selected version to concrete immutable files before it
starts the host. Rules, referenced guides, compiled agent definitions, and hook
resources must all belong to that resolved content. An update changes the default
for future sessions without replacing a running session's files.

Retain content for active and resumable sessions. Resume must recover its recorded
content rather than silently select the latest version. Missing content requires
a visible recovery path. Switching between activated work and Vanilla starts a
new session; it does not attempt to erase prior conversation context.

Keep real host homes, credentials, and native history in place. Do not copy auth
into temporary homes. Rewrite only corpus resource references during assembly;
do not globally replace CODEX_HOME or CLAUDE_CONFIG_DIR in prose, since those
variables also name legitimate user configuration in operational examples.

## Per-session configuration and instructions

Three contracts need separate treatment:

1. **Settings:** override only the settings the selected launch actually owns,
   through native per-call options. Preserve unrelated values and managed policy.
   Corpus activation alone does not grant execution permissions.
2. **Instruction text:** preserve existing instructions when composing the added
   corpus. The host's instruction hierarchy is not the same as TOML/JSON setting
   precedence, and an appended rule is not a runtime permission gate.
3. **Registrations:** merge agents, skills, hooks, and tools by their actual native
   contract. Do not assume array replacement is additive or that a supplied path
   automatically becomes a discoverable skill.

Keep the dynamic launch contract separate from the selected corpus at their
sources, then compose them at the outgoing host boundary. No model should merge
settings, choose artifact paths, or manufacture activation evidence: code performs
those deterministic operations, while the model judges task meaning and tradeoffs.

### Codex

The existing launcher already projects `-c developer_instructions=...` and
per-agent configuration paths. These can point to private assembled content while
leaving CODEX_HOME unchanged.

`developer_instructions` is a replacement scalar. Preserve its existing effective
value before adding the corpus and launch contract; do not parse just one user
config file and assume it represents the native effective configuration. The
installed app-server's `config/read` supports a cwd-aware effective read and
returned the expected developer instruction in a controlled probe. Coverage of
selected profiles and project overrides remains an implementation gate. Preserve
the text verbatim, and specify how project-specific instructions are intended to
relate to the added corpus without claiming an invented native priority level.

A configured external `skills.config` path did **not** register a private skill in
the tested loader. The same file placed in the temporary host's discovery directory
was visible, so the negative result was not an empty instrument. Until a supported
session-only native registration is proven, deliver those procedures through the
selected corpus's explicit private paths, with scripts and assets available there.
Describe this as procedure access, not as native `/skills` registration.

Normal delegated agents must receive the intended corpus through their compiled
definitions or another verified inheritance route. Parent injection alone is not
evidence of child delivery. Explicitly isolated reviewers retain their declared
review context rather than accidentally inheriting ambient corpus.

### Claude

Use `--append-system-prompt` for the selected corpus and dynamic launch contract,
and the existing `--agents` route for resolved agent definitions. Keep native user,
project, and local settings sources enabled.

`--plugin-dir` is a supported per-call candidate for private skills and advisory
hooks. Its actual loading, name collisions, inheritance, and coexistence with the
user's plugins need a real-host probe. A hook supplied through `--settings` is an
alternative only after its merge behavior is confirmed. Do not replace the user's
hook arrays on the assumption that a supplied settings file is additive.

Do not use `--safe-mode`, `--bare`, or excluding the user settings source as a
general corpus switch: their documented scope includes unrelated customization
and, for bare mode, authentication behavior. Prompt transport size and any
file-based transport must be checked against the installed CLI before selection.

## One-time migration is distinct from ordinary installation

New installs do not touch native global instructions/configuration. Existing
installs continue to expose old corpus until their known remnants are removed.
Ordinary launch must not secretly perform this cleanup.

Prepare a scoped migration diff from live ownership evidence: Codex central and
personal-learning spans, Claude's active corpus/learning imports, managed Codex
config additions, hook registrations, agent/skill files in discovery paths, and
shell interception. Back up exact prior bytes privately and preserve unrelated
content. Mixed, modified, or unprovable content gets a specific user decision;
never infer that a whole file belongs to agent-bios from its filename.

Applying that diff is a separate explicit action. Repeated migration must be safe;
an interruption must leave recoverable state and an honest report of what remains.
Do not delete resources still needed by retained sessions. Native backend
registration state and existing shell function state also need readback after
cleanup; removing one line on disk does not update an already-running shell.

## Implementation sequence and completion criteria

1. Resolve remaining native merge, profile, hook, skill, child, and resume probes.
   A flag existing in help is not evidence of its consumer executing correctly.
2. Add private immutable assembly and launch-plan projection behind a temporary
   explicit development opt-in. Keep current release behavior intact while the
   replacement is incomplete; this is not a permanent second content authority.
3. Wire active sessions and every content writer to the private path. Update
   learning capture, migration/pruning, selection, rollback, and verification.
4. Implement previewed legacy cleanup, recovery, and revised installer behavior.
   Retire global-writing installation and default shell interception when the new
   contract is promoted. Remove the temporary rollout mechanism with that change.
5. Update TUI wording and current-state docs. Distinguish **installed content** from
   **content applied to this session**. Vanilla says none, including core/infra;
   package selection says which future agent-bios sessions use the selection.

Completion requires real-path evidence for fresh and migrated installations:
unchanged user global files; no automatic agent-bios markers in fresh Vanilla;
selected markers and readable resources in active sessions; preserved user/project
instructions and unrelated configuration; intended child inheritance; simultaneous
active/Vanilla sessions; crash, update, and resume behavior; and capture/rollback
that cannot recreate global activation. Add negative controls for each structural
contract. Do not substitute dry-run argv, filenames, or an LLM's self-report for
the actual loader, registration, and execution evidence.

## Evidence and design synthesis

Installed versions probed: Codex 0.153.4 and Claude Code 2.1.263. Codex
`debug prompt-input` produced three real input assemblies against the same
controlled global/project files: off -> on -> off. The user-global and project
canaries remained in all three; the session corpus canary appeared only in the
middle developer message. File digests captured before and after matched. No model
generation was invoked. A separate app-server `config/read` probe preserved and
returned a pre-existing developer-instruction canary. Private skill registration
was tested with an actual-discovery positive control, as described above.

Two independent frontier drafts used one blind packet. The GPT draft supplied the
stronger treatment of developer-instruction replacement, old writers, user
ownership, child inheritance, and resume. The Claude draft supported private
assembly and concrete native activation candidates. The synthesis keeps the GPT
skeleton, adds the useful native adapter details, and does not add the suggested
extra public command or a second named snapshot concept. Claude used the existing
OAuth session. Its receipt `634ac2c0ae5b498aab5e6742bfd06600` records
Claude Fable 5/max; provider output confirms that model and successful completion
in session `d567bf4f-525f-4261-8144-e2db17acfa3e`. This is design work, not a clean
verdict on an implemented migration.

The earlier
`design/corpus-management/2026-09-04T2321--17862b3--proposed-design.md` remains a
dated proposal. This direction supersedes its always-installed management skill
and global-realization assumptions, not its entire baseline/personal-overlay
model. No broader Corpus Manager implementation is included here.

Official reference: [Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
Per-call Claude flags were checked in the installed CLI; local plugin usage is
also documented in the upstream `anthropics/claude-code` plugin-development skill.
