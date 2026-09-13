# Setup, app connection, and personal instructions

[← Overview](../README.md) · [Corpus](corpus.md) · [Sessions](session-model.md) · [Recovery](recovery.md)

Install `agent-bios@0.19.0` through the [README quick start](../README.md#quick-start)
to use the guided installer, conversation setup, app bridge and instruction import.
Commands below use the installed `agent-bios` CLI. From a source checkout, run
`bash install.sh <command>` at its root instead.

## Choose where to start

| Route | Requirements | Interface |
| --- | --- | --- |
| Codex app | A local task with command/file access on the intended machine, Bash, Python 3.11+ | Questions and effect review in the conversation; no extra Codex CLI or model login |
| Terminal | macOS or Linux, Bash, Python 3.11+, an input/output terminal; Node.js 18+/npm for package installation | Included Textual wizard |
| Automation | Bash, Python 3.11+, explicit machine commands | JSON inspection, review and results |

Host CLIs and their authentication are needed when you choose to launch them.
Node/npm are needed to obtain the npm package and for any selected capability that
uses them. Source acquisition through the app does not require npm. The app and
storage routes do not require every host CLI. Full versions,
purposes and provisioning boundaries are in [Dependencies](../DEPENDENCIES.md).

For first installation in the app, use the one-line request in the README. The
agent follows [INSTALL.md](../INSTALL.md), asks for English, 한국어 or 日本語, and
obtains one fixed source revision. It handles the local paths. Downloads and
retained acquisition artifacts are disclosed before setup Apply. If that revision
lacks the required setup files, the agent reports this instead of invoking an
older installation mode.

## Guided terminal installation

Install the exact package version, then start setup:

```bash
npm install -g agent-bios@0.19.0
agent-bios install
```

For the source alternative, obtain the repository through its Code menu and run
`bash install.sh install` at its root.

`install` and `onboard` open the wizard by default. After the language choice,
four stages collect the choices:

1. **Corpus:** no active corpus, all available corpus, selected packages/domains,
   or saved policy on an existing installation. App registration is optional.
2. **Personal instructions:** optionally add project folders and select detected
   global/project instruction files for capture. This is independent of corpus use.
3. **Dependencies:** inspect the full inventory and select supported installation
   recipes. Leaving them unselected installs none.
4. **Review:** inspect the effects and, when useful, expand exact commands and
   paths before Apply.

The fresh wizard starts with no active corpus. Reinstalling keeps saved choices
unless you change them. No active corpus retains the library privately but delivers
no corpus instruction text or management bootstrap. Explicit selected mode includes
only its targets within applicable host/project scope; it does not add unrelated
enabled items or implicit core content.

The installer, launcher and Corpus Studio use a verified UI bundle without downloading or installing
Textual. Its extraction is temporary and removed on exit. Missing or damaged
bundled UI fails explicitly. Language changes presentation, not corpus text,
identifiers or host settings.

Back preserves your choices. Cancelling before Apply performs no planned setup
effects. During Apply, cancellation requests a stop at an execution boundary;
completed package installations remain and are reported. A dependency, runtime,
app-registration or capture failure can leave completed effects. Review the result
before retrying rather than assuming everything rolled back.

Selection flags seed the wizard; they do not skip it:

```bash
agent-bios install --corpus none
agent-bios install --corpus selected --select '@agent-bios/core/builder-base'
agent-bios install --dry-run
```

`--dry-run` permits review but no Apply. A non-TTY caller must explicitly use a
machine route. Direct storage-only examples are:

```bash
agent-bios install --non-interactive --corpus none
agent-bios install --non-interactive --corpus all
agent-bios install --non-interactive --corpus selected --select '@agent-bios/core/builder-base'
```

Those direct commands do not collect dependency, app or import choices. Use the
shared conversation protocol below for a complete machine setup plan. The legacy
`--domains` flag requires `--non-interactive` and retains its implicit core/infra
meaning; `--domains none` is different from `--corpus none`.

## Setup through conversation or automation

The app asks questions and displays the review using its available controls. It
does not require a custom settings panel or a terminal UI. The same controller
validates and executes terminal and conversation choices.

```bash
agent-bios setup start
agent-bios setup inspect --language ko
agent-bios setup discover --project-root /absolute/project
agent-bios setup plan --language ko --input setup-choices.json > reviewed-setup.json
agent-bios setup apply --input reviewed-setup.json --review-id REVIEW_ID --yes
agent-bios setup status --review-id REVIEW_ID
agent-bios setup resume --review-id REVIEW_ID
```

`start` returns the supported languages, execution target and guide without
dependency probes or private setup writes. Choose the language before `inspect`.
The agent produces the six choice fields from your answers and saves the entire
engine-issued review. It shows the selected commands, destinations, corpus policy,
app change and capture sources before applying authorized effects. The engine
rejects a changed source, environment, plan or state; `--yes` alone is not evidence
that the effects were reviewed.

Status and resume are read-only. An old completed receipt describes that attempt;
current runtime/helper readiness is reported separately. A running operation can
defer readiness checks and return null fields while still showing recorded progress.
Resume returns a fresh nested review only when remaining effects can be determined;
it does not replay uncertain operations. The agent follows the full procedure in
[START.md](../compose/setup/START.md), including exact review preservation and verified
entrypoint handoff. Source and reviewed artifacts remain available for recovery.

## Use corpus in a Codex app task

Choose app registration during setup, or explicitly run:

```bash
agent-bios app register --dry-run
agent-bios app register
agent-bios app status --json
```

Registration creates the owned `~/.agents/skills/agent-bios` discovery link to a
private immutable helper. Implicit invocation is disabled. An unrelated or edited
entry is preserved. Registration on disk does not prove the app discovered it;
setup can return a usable helper path to continue before discovery refreshes.

Once discovered, use `$agent-bios` in the chosen task. Ask it to manage the library,
change setup, show task status, or explicitly use selected corpus in this task.
A setup or management request does not activate content. Each task starts with
managed delivery off and requires its own explicit use.

Use previews a `ContentRef` and then returns the exact snapshot's
`instruction_text` through the task's tool/context path. The receipt says
`returned-as-context`; it proves neither native startup injection nor model reading.
Session operations require the real task ID, normally `CODEX_THREAD_ID`. Setup and
management do not require that ID. App use enables no hooks, agents or permissions.

Ask `$agent-bios` to turn corpus delivery off to stop consulting it in subsequent
work. Text already returned cannot be erased; a fresh task is needed for clean
exclusion. A resumed or forked conversation can carry earlier content independently
of the new task's receipt. Native global/project instructions still follow host rules.

`agent-bios app unregister` removes only the owned discovery link. It does not erase
prior task context or personal corpus data. Corpus Studio can also run in the app's
integrated terminal; editing it changes future snapshots, not current task context.

## Import existing instructions

Setup can capture selected native global/project files for later model review.
You can also use the explicit import workflow:

```bash
agent-bios import discover --project /absolute/project --json
agent-bios import capture --project /absolute/project --path /absolute/project/AGENTS.md --json
agent-bios import prompt CAPTURE_ID
agent-bios import plan --input reviewed-import.json --json
agent-bios import apply PLAN_ID --expected-revision REV --json
```

Discovery checks known global locations and fixed filenames in chosen project
roots. It does not crawl the home directory or follow instruction references.
Capture preserves originals and stores redacted evidence with source digests
privately. It is pending review, not an automatically optimized personal corpus.

In an app task, ask `$agent-bios` to review the returned capture ID. The agent
proposes content, `always`/`relevant`/`requested` placement, rationale, and source-line
coverage or exclusions. The runtime checks the evidence and structure, and Apply
requires the reviewed revision. Changed originals or conflicting edits require
fresh review. Project-scoped imports remain limited to their recorded root and
applicable hosts, even when all corpus or an enable override is selected.

Native hosts may still read the untouched originals. Importing a procedure as
requested content does not suppress the same rule in a native file, and changing
placement is not a guarantee of optimal model behavior. Review duplication and
tradeoffs as part of the proposal. Installation, capture, import and task activation
have separate outcomes; the result tells you which actually completed.
