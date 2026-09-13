# Dependencies

This file owns the dependency inventory, required capabilities, and the observed local
versions below. Required minimums come from the code that enforces them. The Textual
root pin and optional learning-validator pin belong to `launch/provision-venv.sh`.
`gates/build-ui-runtime.py` derives the exact shipped wheel inventory in
`compose/ui_runtime/manifest.json` from `TEXTUAL_PIN`; setup reads that inventory and
the optional validator pin. Guide `Environment Binding` sections own
role-slot/model choices and feature-specific host observations; `Evidence Base`
sections own measured behavior and numeric defaults.

Korean: [`ko/DEPENDENCIES.md`](ko/DEPENDENCIES.md). A version report or successful
package installation does not renew a native protocol, model-turn, or UI observation.
The verification column states the scope of each check.

## Runtime tools

The supported operating systems are macOS and Linux (`package.json` `os`). Private
transactions, instruction capture and app registration use POSIX file locks, file
descriptors and symlinks. The JSON setup protocol, machine-mode corpus operations,
import and app context use Python standard libraries. Interactive installation,
package/current-checkout Corpus Studio and the private/current-checkout launcher's
rich entrypoint load the shipped
offline UI dependencies. Optional learning validation and retained compatibility clients
have separate runtime requirements below.

| Tool | Required by | Required capability | Verified |
| --- | --- | --- | --- |
| `python3` | `compose/corpus*.py`, app bridge helper, `session-cost.py`, `launch/agent-launch.py` | Python 3.11+ (`tomllib`) for the private store, offline installer UI loader, import evidence, app receipts and native session adapter | 3.14.5 · version report · 2026-09-12 |
| `bash` | `install.sh`, shell adapters, provisioner and app helper command dispatch | Bash arrays and argument-preserving execution; macOS system Bash is supported | 3.2.57 · version report · 2026-09-12 |
| `git` | conversation source acquisition, clone updates and version-control workflows | clone and detached checkout for a fixed source commit; worktrees and modern revision operations for development. No Git checkout is required to use an installed npm package | 2.50.1 · version report · 2026-09-12 |
| `zsh` | `launch/agent-launch.zsh`, optional `launch/shell_integration.py` connection | shell functions, TTY checks and argument-preserving dispatch. Used by the explicit private shell connection as well as compatibility installation; it is not required for ordinary private storage or app context use | 5.9 · version report · 2026-09-12 |
| `mktemp`, `cp` | wrapper temporary homes and shell utilities | BSD or GNU command interfaces | local inventory checks command availability; no package-version claim |
| `ioreg`, `ps` | conversation setup machine/process identity on macOS | local OS identity probes. Linux uses machine-id and `/proc`; machine identity has a host/filesystem fallback, while missing process evidence leaves a running attempt unconfirmed | source-defined probes; no separate tool version pin |
| Node.js | npm delivery, optional npm host installation and selected slide jobs | `package.json` requires Node >=18 for npm package delivery. The optional Claude npm recipe requires Node >=22; Codex npm installation and slide runtimes retain their own requirements. The Python corpus runtime does not require Node | 26.0.0 · version report · 2026-09-12 |
| `npm` | package delivery and optional host installation recipes | normal global package installation using the user's configured prefix/registry | 12.0.2 · version report · 2026-09-12 |
| Homebrew (`brew`) | optional setup installation recipes | available formula/cask installation commands selected in the reviewed setup plan; setup does not install Homebrew itself | local `--version` probe; no installation version pin |
| Python `venv`, `ensurepip` and pip | explicitly selected managed-environment installation | create an isolated environment using `AGENT_LAUNCH_PYTHON` (default `python3`); not prerequisites for loading the bundled installation UI. Some Linux Python distributions provide these components separately | clean venv creation and `pip check` · Python 3.14.5 · 2026-09-12 |
| Bundled Textual UI runtime | interactive `install`/`onboard`, package/current-checkout Corpus Studio TTY entrypoint, private/current-checkout launcher rich entrypoint | pure-Python wheels shipped under `compose/ui_runtime/`; the loader verifies and extracts them temporarily before UI imports. No system/managed Textual, pip installation or runtime network access is needed | manifest versions/hashes/licenses; offline clean-interpreter, TTY and backend-handoff checks · 2026-09-12 |
| Managed `textual` | standalone compatibility launcher copies, retained in-process APIs and author tests | optional environment at `${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}`. Its installation target is `TEXTUAL_PIN`; current package CLI UI paths use the shipped bundle | 8.2.8 · clean-venv installation/import, `pip check` and UI tests · 2026-09-12 |
| `rich` | Textual clients | included with the installer UI bundle and otherwise provided transitively by Textual; not a separate setup choice. Plain editing needs no optional syntax-highlighting packages | managed Textual environment and UI tests · 2026-09-12; bundled version belongs to the manifest |
| `jsonschema` | `learn/collect-learning.py`, `learn/check-learning.py` | Draft 2020-12 validation for user learning capture and author verification. `learn` uses a usable system validator, otherwise the configured managed interpreter. Installation target is `JSONSCHEMA_PIN` in the provisioner; `--learning-only` installs it without adding Textual | 4.26.0 · clean-venv installation/import and `pip check` · 2026-09-12 |

`agent-bios install` and `onboard` are interactive unless `--non-interactive` is explicit.
Selection flags seed the UI, and a non-TTY default call fails before writes. Python
3.11+ is still required. `compose/corpus_ui_runtime.py` validates the shipped bundle
before UI imports and uses one process-owned temporary extraction, cleaned on normal
exit and released by the launcher before backend `execve`. It creates no persistent UI
package installation. Missing, damaged or conflicting bundle state produces repair
guidance on the package UI entrypoints; the installer does not fall back to numbered UI.
Standalone compatibility launcher copies retain managed/numbered behavior. Imported
in-process APIs retain their existing dependency contract; CLI bundle activation is
explicit at the real entrypoints.

The terminal installer language chooser and its English/Korean/Japanese messages are
owned by `compose/corpus_setup_i18n.py`. This is a per-run UI choice before dependency
probes, not another corpus language or persisted host setting. Locale variables suggest
a starting choice; the user still sees the chooser. The JSON setup protocol accepts an
explicit review language while retaining its stable field names and exact values.

`agent-bios setup` needs Python 3.11+ and Bash, with no TTY, Textual, model SDK or new
server. It reuses `SetupController` for inspection, reviewed plans and fixed dependency
actions. Only explicit Apply runs selected actions; its durable receipts use private
state. `status` and `resume` inspect or prepare further review without executing
installation actions. The conversation client needs the host's normal local file and
command tools. `INSTALL.md` resolves the repository-link request to an explicitly
selected local source or one downloaded commit before reading `compose/setup/START.md`.
Source acquisition uses the host's download or Git tools and creates caller-owned
files before the installation plan; it is separate from setup Apply. No preinstalled
bridge, Codex CLI, Node.js or npm is required for this source-based conversation route.

Setup probes installed commands without installing or signing in. Available dependency
actions have fixed argv and run only after explicit selection and Apply. The app bridge
retains the configured managed-environment path for later learning calls. Host sign-in,
user MCP credentials, browser/job bindings and personal skills remain separate setup
steps; absence of an optional route does not make the local corpus store unavailable.
Manager recipes are offered only after their version probe succeeds. Creating a new
managed environment requires the selected Python venv/ensurepip bootstrap; an existing
managed interpreter does not need to bootstrap again. The provisioner checks Python
3.11+ before modifying the environment.

## Host agent CLIs

| CLI | Required by | Required capability | Verification |
| --- | --- | --- | --- |
| Claude Code | native Claude sessions and Claude worker/review routes | `--model`, `--effort`, `--agents`, per-call `--append-system-prompt`, `--session-id`, `--resume`, `--mcp-config`, `--plugin-dir`, and the selected permission mode; native global/project loading remains native | 2.1.268 · 2026-09-12 |
| Codex CLI | `compose/corpus_session.py`, launcher and Codex worker/review adapters | per-call `-c`; cwd-aware `app-server --stdio` `config/read`; durable `thread/start`, `thread/inject_items`, `thread/read`; `codex resume`; `codex exec` and agent-config projection | local 0.153.4; isolated compatibility 0.154.0 · 2026-09-12 |

The Claude row reports the installed command version. The Codex row distinguishes the
installed runtime from the newer isolated compatibility check. Native protocol and
execution evidence have narrower scope:

- Optional global-instruction exclusion requires Claude Code **2.1.263+**, enforced by
  `compose/corpus_session.py`. The adapter supplies `claudeMdExcludes` through one
  `--settings` argument and refuses a conflicting existing argument. Include/exclude/
  resume startup preserving project sources was observed on 2026-09-08. The current
  Codex adapter has no supported global-only exclusion in the verified 0.154.0 protocol;
  it refuses that choice instead of changing its sandbox or config home.
- The isolated Codex compatibility check covers cwd-aware configuration and prompt
  preservation, durable thread creation/injection/read and pin recovery, bridge skill
  discovery/removal, and user/project/session hook discovery. It does not claim hook
  execution or a model turn on that runtime.
- The Claude SWEEP projection requires `--restricted`, `--tools`, `--strict-mcp-config`
  and `--mcp-config`; parser/projection verification used 2.1.263. Its allowed tools and
  effort choices come from the launch bindings. A parser check is not a model-generation
  receipt.
- Native corpus hooks use the common installed Python carrier and typed event/matcher.
  Claude plugin delivery was exercised with 2.1.268; Codex inline hook discovery and
  local-transport execution controls used 0.153.4. Existing host hooks, enablement and
  native trust remain in force. Discovery alone does not prove execution.
- Codex deep-review flag checks used 0.146.0. The Claude `ultracode` keyword trigger was
  read from the 2.1.220 installed bundle. These feature observations are not refreshed
  by the current `--version` reports. Authenticated corpus-agent execution and post-fix
  authenticated resume remain unverified.

## Codex app and instruction import

The Codex desktop app is a separate host from the Codex CLI. Its optional bridge needs
native skill discovery for `~/.agents/skills/agent-bios`, the explicit-invocation policy in
`compose/app_bridge/agents/openai.yaml`, and Python plus `/bin/bash` for its helper.
`CODEX_THREAD_ID` supplies the current task identity; an explicit real `--session` id
can substitute when absent. The bridge resolves the confirmed private installation
and saved roots on each call. Local app registration and receipt tests do not establish
a minimum desktop-app version or prove native discovery/model reading.

An explicit installation request can use the bridge's `setup` forwarding, including
`setup start` to locate the installation guide. This route does not need a task identity
or run `session use`; native task identity is required for task-context receipts only.
Review/apply context instead binds the machine, user, paths, package, working directory
and effect-relevant environment. Status receipts describe recorded attempts; `handoff`
separates package/runtime verification from helper registration, integrity and usability.
Read-only `try_transaction_lock` in `compose/corpus_transaction.py` permits current
checks without waiting for another writer or creating synchronization state. If it
cannot acquire safe synchronization, handoff reports `verification: "deferred"` and
unobserved readiness fields as `null`, while status still returns recorded progress.
`verification: "checked"` reports that the checks ran; their individual results remain
separate.
A caller uses `helper_argv` only with `helper_usable`, or `setup_argv` with
`package_verified`, and supplies the returned environment. Neither flag proves native
skill discovery. The engine does not install or configure the host's file/command tools.

`app session preview/use/off/status` manages **returned task context**, not a new Codex
CLI session. This route uses no separate Codex CLI subprocess, no Textual runtime and
no direct model SDK. Corpus Studio needs a terminal; rich UI remains optional. App use
requires explicit selection, enables no native hooks or agents, and Off cannot retract
previously returned text. Registration is off by default and owns only its discovery
link, preserving global instruction files and foreign entries.

Local instruction import also needs no model SDK or parser framework. Standard-library
code discovers fixed instruction filenames at known global and explicit project roots,
captures redacted evidence through `learn/redact.py`, and validates source digests,
coverage, project/host scope and the store transaction. The host agent authors content,
consumption placement and trigger descriptions; it is not a deterministic classifier.
Planning/applying requires an installed baseline. Original native files remain intact
and may still be loaded independently by the host.

## Private corpus assets

- **Native corpus hooks and agents** require explicit `--corpus-native` and a supported
  installed carrier. Claude agents retain their authored frontmatter in per-item
  plugins; names are plugin-qualified. Codex agent-semantic translation remains separate
  work. Neither route registers global hooks by default.
- **Codex role templates** (`codex/agents/*.toml`) are carried in the immutable private
  release. Private installation does not require copies under the native host home.
- **Management bootstrap** (`compose/bootstrap/SKILL.md`) and selected requested
  procedures are private snapshot resources. **No-corpus mode omits the bootstrap and
  corpus instruction text.** The optional app discovery bridge is a separate entry;
  registration alone does not select task context.

## Models and optional integrations

Concrete role-slot/model bindings belong to each guide's `Environment Binding` and the
launch profile. Providers are Anthropic and OpenAI; host login supplies authentication.
Agent-bios does not install credentials or infer a model account from dependency probes.

- **Slide-writing static HTML/PDF companion** — its primary guide requires no renderer.
  The selected static path needs Python standard libraries for preparation and acceptance;
  rendering additionally needs a job-bound Node executable, Playwright module, `pdf-lib`
  beside that module, and a Chromium-family browser executable. These are not installed
  by corpus delivery. The 2026-09-09 job verification used Node 24.19.0, Playwright 1.62.1,
  pdf-lib 1.17.1 and browser 152.0.7977.83; it is separate from the current host Node report.
- **Deep review** — uses the configured host CLI rather than another core tool. Codex
  runs its own read-only exec route with a self-contained packet; the frontier model
  and effort come from the launch binding. Claude runs headless with the
  keyword `ultracode` in the prompt to activate its workflow. Native configuration
  remains inherited unless a hermetic adapter is selected. Personal reviewers register
  in `review-methods.local.toml`.
- **Cross-family review adapters** — private routes resolve `wrappers/codex-run.sh`,
  `codex-helm.sh` and `claude-run.sh` from the selected package. Their command paths,
  binding, reach and fallback are declared in the launch contract. An unavailable or
  unauthenticated opposite-family route is reported, not credited as a completed review.
- **MCP servers** — user-specific; only a selected capability declaring `mcp-stdio-v1`
  is registered by the launcher. No shipped review method requires MCP. App corpus
  context delivery does not add an MCP server.
- **spreadsheet-processing** — an optional skill referenced by the spreadsheet rule
  when that corpus is selected. If unavailable, its inline plain-tools/code and real
  spreadsheet-engine validation fallback applies.

Host `config.toml`, `settings.json`, `hooks.json` and credentials are untracked,
user-owned state. `launch/agent-launch.toml` carries launch bindings without secrets.

## Re-verify

Read the current local inventory without installing packages or starting model turns:

```bash
python3 -B - <<'PY'
import json, os, pathlib, sys
repo = pathlib.Path.cwd()
sys.path.insert(0, str(repo / 'compose'))
from corpus_setup import dependency_inventory
for row in dependency_inventory(repo, {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}):
    print(json.dumps({key: row[key] for key in ('id', 'status', 'version', 'path', 'manual_reason')}, ensure_ascii=False))
PY
```

Inspect the installed private state using this checkout's runtime:

```bash
bash install.sh verify
bash install.sh corpus status --json
bash install.sh app status --json
```

Provision packages only when explicitly requested for learning validation, compatibility
clients or author tests. These commands are not needed by the package CLI UI; they may access
the configured package index and modify the managed environment:

```bash
bash launch/provision-venv.sh
bash launch/provision-venv.sh --learning-only
```

The author-side bundle checks are offline. They verify the root pin, exact wheel
metadata and licenses, isolated imports/rendering, cleanup and negative controls:

```bash
python3 gates/build-ui-runtime.py --check
python3 gates/build-ui-runtime.py --self-test
```

Only the builder's explicit `--build` path fetches packages; do not hand-edit wheel
archives or their manifest. The full author umbrella also exercises compatibility
clients and can provision its managed test environment, so it is not a read-only
machine inventory:

```bash
python3 -B - <<'PY'
import pathlib
paths = list(pathlib.Path('compose').glob('corpus*.py')) + [pathlib.Path('launch/agent-launch.py')]
for path in paths:
    compile(path.read_text(), str(path), 'exec')
PY
bash -n install.sh launch/provision-venv.sh wrappers/codex-run.sh wrappers/codex-helm.sh wrappers/claude-run.sh
zsh -n launch/agent-launch.zsh
./gates/check-parity.sh
```

## Ownership

| Owner | Owns |
| --- | --- |
| `DEPENDENCIES.md` | required capability inventory and scoped local version observations |
| `launch/provision-venv.sh` | Textual root pin, `JSONSCHEMA_PIN` and explicit managed package installation |
| `gates/build-ui-runtime.py` | author-side bundle generation and offline check/self-test |
| `compose/ui_runtime/manifest.json` | generated exact UI wheel inventory, versions, hashes and licenses |
| `compose/corpus_ui_runtime.py` | offline verification, process-lifetime extraction and release |
| `compose/corpus_setup.py` | shared SetupController, local inventory and reviewed dependency recipes |
| `package.json` and runtime validators | supported platforms and required runtime minimums |
| guide `Environment Binding` and launch profile | role/model bindings and feature-specific host evidence |
| guide `Evidence Base` | measured behavior and numeric defaults |
