# agent-bios

**A personal instruction layer for Claude Code and Codex.**

Build an instruction library you can inspect, edit, and reuse. Choose what each
CLI session or Codex app task uses, while preserving your existing global instruction files.

[Quick start](#quick-start) · [Corpus Studio](#your-instruction-library) · [How it works](#how-sessions-work) · [Understand!](#understand-the-reasoning) · [Documentation](#documentation) · [한국어](ko/README.md)

![Corpus Studio showing a guide-linked rule and an unapplied on/off choice](docs/assets/corpus-studio.svg)

*Actual 0.18.0 Studio UI, captured with Textual enabled and the bundled corpus
in an isolated test environment.*

## Make your instructions your own

agent-bios ships a starting library of rules, guides, and procedures, called a
**corpus**. You decide which parts belong in your working environment.

| What you want to do | What agent-bios provides |
| --- | --- |
| See what your instructions say | Browse and search documents in Corpus Studio; follow a rule's links to its guides. |
| Adapt them to your work | Edit supplied items, create personal ones, and choose their delivery method. |
| Choose what a session uses | Switch individual items on or off without deleting their content or edits. |
| Recover the starting point | Restore supplied content, recover personal items, or preview a full reset. |

This is an instruction and launch layer, not a replacement for either host CLI.
It does not train the model or guarantee that the model follows every instruction.

## Quick start

Use the terminal installer or set up through a Codex app conversation. Both offer
language, dependency, corpus and optional app/import choices.
See [setup and prerequisites](docs/setup.md).

### In a terminal

You need **macOS or Linux**, **Bash**, **Python 3.11+**, and **Node.js 18+ with npm**
for package installation. Run:

```bash
npm install -g agent-bios@0.19.0
agent-bios install
```

The installer opens a guided terminal UI with English, Korean and Japanese. Its
verified Textual bundle is included; a separate UI installation is unnecessary.
Choose only the dependencies and corpus you want. [Full setup options →](docs/setup.md)

To launch a CLI session, install and authenticate that host CLI, then run this from
your project:

```bash
"$HOME/.local/bin/agent-launch" claude
```

Use `codex` instead of `claude` for a Codex CLI session.

1. Choose a Builder preset or **Custom**.
2. Review the model, review setup, and permissions. **Some presets request
   permission bypass**; select settings appropriate for your project.
3. Start the session. Choose **Software Engineer / Vanilla** to use the host's
   native setup without an agent-bios corpus snapshot.

Open **Corpus Studio** from the launcher or run `agent-bios corpus` to inspect the
library. `agent-bios status` shows the installed private release and its location.

<details>
<summary>Install from source instead</summary>

Use this repository's **Code** menu to copy its clone command or download its
source. From the obtained repository folder, run:

```bash
bash install.sh install
```

This route needs Bash and Python 3.11+; Node/npm are not acquisition prerequisites.
Keep using `bash install.sh <command>` from that source for management. A global
`agent-bios` command can belong to a different npm version.

</details>

Ordinary `claude` and `codex` commands do not automatically receive agent-bios
content. An optional zsh [shell connection](docs/advanced-launch.md#optional-shell-connection)
can route bare interactive commands through the launcher. If you have an older
global installation, read [migration](docs/recovery.md#ownership-and-legacy-migration)
before changing it.

### In the Codex app

Open a local task on the machine you want to configure and send:

```text
Install https://github.com/kangminlee-maker/agent-bios
```

The agent follows [INSTALL.md](INSTALL.md), obtains a fixed source revision, and
asks for English, 한국어 or 日本語. Choose dependencies, no active corpus or specific
corpus, and optional app connection or instruction-file capture. Review the effects
before Apply. You do not need to supply a local path or install Codex CLI.

Once the registered command appears in the app, use `$agent-bios` for setup or management.
To add corpus to a task, explicitly ask it to use your chosen corpus there.
Installation and opening Corpus Studio do not activate task context.
[App use, off, and personal instruction import →](docs/setup.md#use-corpus-in-a-codex-app-task)

## Your instruction library

Open **Corpus Studio** in the launcher, or run `agent-bios corpus`.
In the app, `$agent-bios` can manage the same library through conversation.

- **Read as you navigate.** Arrow keys move between reading controls and update
  the document as the library cursor moves; Enter is not required to read an item.
- **Recognize guide pointers.** Rules with explicit guide references show
  **→ GUIDE** and link to the guide, its delivery method, and its current state.
- **Switch items on or off.** Press **Space** in the library. `[x]` is on,
  `[ ]` is off, and `*` means the choice is not yet applied.
- **Apply deliberately.** Stage several choices, then use
  **Preview on/off → Apply**. Ordinary edits also use a revision-checked preview.

An item's **use** and its **delivery method** are separate. A selected rule may
be `always`, a guide `relevant`, or a procedure `requested`. Native hooks and
agents use separate opt-in adapters. Putting a guide next to its trigger does
not change either one's delivery.

Individual on/off choices take precedence over default domain/core selections.
Off is not deletion: content and edits remain available, including for learning.
Updates retain those choices; a full reset returns to installed defaults.

[Corpus controls, keyboard navigation, delivery methods, and included guides →](docs/corpus.md)

## How sessions work

**Library → your selection and edits → fixed snapshot → configured session**

Installation stores a release and its baseline in agent-bios-owned locations.
A configured launch compiles the selected content for its host. Later edits
affect future snapshots; managed CLI resume resolves the session's recorded snapshot.
App tasks use a separately selected snapshot returned through their tool/context path.
Turning app delivery off cannot erase text already present in the conversation.

Your own global instructions are **also loaded by default** in activated
sessions. Not overwriting them is different from excluding them. Supported Claude
versions offer selective global-document exclusion; the current Codex adapter
does not. Project instructions and prior conversation content are separate.

[Storage, session pins, and verification limits →](docs/session-model.md)

## Understand the reasoning

Choose **Understand!** in the launcher to explore why the corpus is written the
way it is. Select a coherent learning bundle rather than memorizing separate files.

The tutor explains purposes, background, tradeoffs, and limits. Each active
learning turn ends with a relevant question, then waits for your answer. It
distinguishes documented reasons from inference and respects pause or stop requests.

For example, a discussion of clarification might ask:
*“What would change in your next action if this ambiguity were resolved?”*

The aim is understanding when a rule helps—and where it stops helping.
This is learning for the person, not model training. Saving a personal discovery
requires your confirmation.

[Learning sessions and personal discoveries →](docs/understand.md)

## Stay in control

- **No default global rewrite.** Private installation leaves native instruction
  files, discovery directories, and hook settings alone. Explicit legacy
  migration is a separate operation.
- **Separate selection from permission.** Turning an item on does not bypass
  native hook/agent opt-in, host trust, or execution permissions.
- **Know what is verified.** `agent-bios verify` checks stored content and owned
  projections. `activation: unverified` is deliberate; it does not certify model
  consumption. Authenticated resume and some native integrations remain
  [incompletely verified](docs/session-model.md#verification-and-limits).
- **Inspect recovery before applying it.** Migration and reset have previews.
  Conflicting user-owned paths are reported, not permission to delete them.

## Documentation

| When you need more detail | Read |
| --- | --- |
| Install, connect the app, or import existing instructions | [Setup](docs/setup.md) |
| Author, enable, restore, or inspect corpus items | [Corpus](docs/corpus.md) |
| Understand snapshots, storage, and session evidence | [Session model](docs/session-model.md) |
| Migrate, reset, or resolve installation conflicts | [Recovery](docs/recovery.md) |
| Configure presets, globals, shell connection, native hooks, or review | [Advanced launch](docs/advanced-launch.md) |
| Learn the corpus and preserve a discovery | [Understand!](docs/understand.md) |
| Check prerequisites and optional tools | [Dependencies](DEPENDENCIES.md) |
| Develop this repository | [Contributing](CONTRIBUTING.md) — requires a checkout |

Use `agent-bios help` and `agent-bios corpus --help` for command discovery.
Source references: [delivery surfaces](SURFACES.md), [network contract](ENDPOINTS.md),
and [terminology](LEXICON.md).

## Adopting elsewhere

Review the `(private)` bindings and environment-specific dependencies before
adopting the defaults. Keep personal adjustments in Corpus Studio, or follow
[the source-authoring workflow](CONTRIBUTING.md#adopting-elsewhere) when changing
what the package ships.

## Scope

The package contains instruction sources and runtime machinery, not your
personal corpus state, learning events, session pins, credentials, or native settings.

## License

[MIT](LICENSE).
