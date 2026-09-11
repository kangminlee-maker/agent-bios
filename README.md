# agent-bios

Single source of truth for the instructions and scoped guides that an explicit
agent-bios launch supplies to Claude Code or Codex. Edit once; the private corpus
compiler projects the selected content for each activated session.

A deployable instruction corpus for coding agents, plus the CLI that
installs, verifies, and evolves it. The npm package ships the corpus; `install.sh` is both the
`agent-bios` CLI entry and the deployer.

Korean reference: [`ko/`](ko/) mirrors every doc below — reference only, never installed or loaded.

## Model

Two authored layers:

- **Always-in-an-activated-session instructions** — `claude/CLAUDE.md` is the English canonical and `codex/AGENTS.md` its generated host projection. They hold compact invariants, decision principles, and guide pointers. A clean private install does not copy either file into a host's global discovery path; `compose/corpus_catalog.py` inventories their registered items and compiles the selected rules into an immutable session snapshot.
- **Scoped guides** — `claude/guides/`, with generated Codex mirrors. The snapshot compiler copies selected guides to private generation-qualified paths and emits their router. Procedures, tables, numbers, and environment-specific content live here.

## Principles

The `slide-writing` guide is selected through `office-work` and
`visualization-docs`. Its primary guide supplies the semantic criteria for every
slide or presentation task. Its companion runbook and scripts are used only for
an explicitly applicable static HTML/PDF job: preparation derives a job-local
criteria copy and `ORACLE.json`, then freezes them with the job inputs and runtime
version. Jobs stay outside immutable corpus snapshots; preparation and result
acceptance need Python, while rendering uses the optional dependencies listed in
`DEPENDENCIES.md`. Native presentation formats remain the user's choice; the
supplied renderer's mechanical checks apply only to its static HTML/PDF path.

- **Rule bodies never name concrete models or tools** — only role slots and tiers. Bindings live in each guide's `Environment Binding` (dated; expire ~8 weeks or on a newer model). New model → update that row + date; leave rules alone. Declared exceptions: sections whose subject is a concrete tool surface (the cli guide's Codex direct-drive section) and optional-capability names inventoried in `DEPENDENCIES.md` (e.g. the `spreadsheet-processing` skill) — the Adopting checklist below covers swapping both.
- **The Codex tree is generated, not mirrored by hand** — `gates/emit-mirrors.py` projects `claude/` → `codex/` and `ko/claude/` → `ko/codex/`, differing only in title and config-home variable (`$CLAUDE_CONFIG_DIR` ↔ `$CODEX_HOME`), plus one declared Codex-only standing-dispatch authorization required by Codex's trigger contract, inserted at a pinned position. It owns the projection rule; `gates/check-parity.sh` runs its `--check` and adds pointer resolvability, frontmatter, shared anchor phrases on the global↔guide restatement pairs that remain, and Codex role-binding / wrapper-default projections. Parity enforces content synchronization only; it does not guarantee both harnesses respond to the same wording with the same strength.
- **The always surface is a per-activated-session token budget** — every selected rule is supplied to that session and can be inherited by its children, so each added bullet dilutes the rest. A new always rule must name the bullet it displaces (or why none does); procedures, tables, numbers, and worked examples belong in guides.
- **Installation is storage, not activation** — `install` and `onboard` copy a validated immutable release into agent-bios-owned state and record a baseline plus selection. `verify` proves those stored bytes, the catalog, the baseline, and the owned launcher projection; it deliberately reports activation as unverified. Only a configured `agent-launch` resolves a snapshot and calls a host adapter.
- **The default installer leaves native host state alone** — it does not seed global `AGENTS.md`/`CLAUDE.md`, host skill/agent directories, hook settings, or shell interception. Existing installations keep their old global projection until `agent-bios migrate` previews and, with explicit apply confirmation, removes only proven legacy-owned material. `AGENT_BIOS_LEGACY_INSTALL=1` exists only for compatibility and migration regression coverage.
- **Source, snapshot, and session have separate lifetimes** — `CorpusStore` revision-checks private authoring, compiles content-addressed snapshots, and preserves prior snapshots. `corpus_session.py` records a host-observed session id before a pin counts as resumable; reset and later edits affect future snapshots, not an existing pin.
- **Learning evidence stays immutable** — capture events are host-qualified private JSONL records. A local edit is an overlay for later snapshots; promotion suppresses only an exact source revision when its replacement is proven in that snapshot. Local reset, removal, or migration makes no claim that an uploaded record was deleted.
- **`Evidence Base` (per guide) is the single owner of numbers.** Measure with `session-cost.py` (`agent-bios cost` on an installed package).
- **English is canonical and shipped; Korean (`ko/`) is reference only.** The private catalog and snapshot compiler consume the fixed-name English sources.

## Layout

| Path | Role |
| --- | --- |
| `claude/CLAUDE.md`, `codex/AGENTS.md` | canonical and generated always-surface sources (en); shipped privately and selected into activated snapshots, never installed into native global files by default |
| `claude/guides/*.md`, `codex/guides/*.md` | scoped-guide sources copied to immutable private snapshots when selected |
| `codex/agents/*.toml` | Codex role-template sources retained in the private release; agent-item activation remains separately evidenced |
| `ko/**` | Korean mirror of every doc above + this README + DEPENDENCIES (reference only) |
| `launch/` | launch profile and preflight TUI; `agent-launch.py` resolves a private snapshot for configured sessions, keeps Software Engineer / Vanilla bare, and routes resume through the recorded pin. The old shell interception remains only on the legacy compatibility path |
| `compose/` | corpus authority and clients: `corpus_catalog.py` inventory/compiler, `corpus_store.py` baseline/overlay/plan/snapshot store, `corpus.py` + `corpus_ui.py` machine/numbered/rich clients, `corpus_install.py` private install and migration, `corpus_session.py` host delivery and pins, and the immutable private management bootstrap |
| `learn/` | the collection loop — capture, record schema and its validator, curation intake, promotion manifest, redistribution, and the secret-redaction floor |
| `session-distill/` | the heavy curator pipeline that mines many sessions into corpus-grade items |
| `wrappers/` | internal host/review adapters carried by the private release; the default install does not populate native host bin directories |
| `gates/` | author-side verification (mirror generation, parity, lexicon, payload, assembler scenarios) — reachable only from a repo checkout, and `check-package.sh` fails if any of it enters the npm payload |
| `ontology/` | what a change obliges elsewhere — entities, obligation edges, and the service's routes, held against real source by `check-ontology.py`. `instances/graph.json` is canonical; `LEXICON.md`, the RDF views, the HTML map, and the competency/extension docs are generated from it |
| `install.sh`, `session-cost.py` | the `agent-bios` command dispatcher/private installer entry and the cost meter |
| `decisions/` | the decision record for developing this repo — what was decided and which alternative it closed; author-side, never shipped |
| `packages/` | authored corpus packages, organized by package identity rather than by concept home |
| `.githooks/` | the pre-commit hook that runs the gates against the index, enabled per clone with `core.hooksPath` |
| `SURFACES.md` | where knowledge and tools reach a model, and what each place admits — every entry names the code that realizes it |
| `FINDINGS.md` | open implementation defects, live; closing one deletes its entry |
| `design/`, `benchmarks/` | design records and the instruction-behavior benchmark |
| `research/` | corpus research (the 12,749-file AGENTS.md/CLAUDE.md classification): reports, scripts, labeling record; bulk data stays local by `.gitignore` rule |
| `DEPENDENCIES.md` | external tools / host CLIs / model providers + verified versions |

`config.toml`, `settings.json`, and `hooks.json` are machine-specific (trust lists, hook paths, secrets) and intentionally untracked.

## Guides

| Guide | Scope |
| --- | --- |
| `cli-multi-model-workflow` | multi-model CLI workflow: Default Frame, role slots/tiers, delegation mechanics, driving Codex CLI directly, cache economy, unattended-batch safety, halt/resume, handoff contract, Environment Binding |
| `coding-staged-workflow` | staged development: design → process → implement, lightweight path, review loop, severity contract, stop conditions |
| `verification-discipline` | verification depth and per-domain mix (owns the Verification Menus), case space, what a green result is worth |
| `concept-economy` | concept-surface economy: reuse / extend / rename / split, split triggers, migration compatibility |
| `documentation-hygiene` | where comments, history, and handoffs belong; how to phrase rules others follow |
| `llm-capability-boundary` (+ `-patterns`, `-examples`) | LLM/tool/code authority boundary: field authority, accepted output channels, structural enforcement, worked examples |
| `mock-realization-boundary` | mock/fixture realization vs product semantic path |
| `svg-visualization-guide` | SVG diagram / service-blueprint spec |
| `implementation-map` | IMPLEMENTATION_MAP.html current-state dashboard |

The table names the load-bearing guides; the full inventory and its per-domain
classification live in `compose/domains.json`, which the domains gate holds against the
tree.

## Edit workflow

1. Edit the English canonical (`claude/`), and the Korean canonical (`ko/claude/`) when the change is user-facing.
2. `python3 gates/emit-mirrors.py` — regenerates `codex/` and `ko/codex/` from those two canonicals. Never hand-edit the Codex side: it is a generated projection, and `--check` (which the parity gate runs) fails on any file that is not exactly what the generator emits.
3. `./gates/check-parity.sh` must pass.
4. Commit, then deploy: `agent-bios install` (or `agent-bios update` from a clone).

## Install and activate

The npm package and command are both named `agent-bios`. Installation is always
explicit—never a package-manager postinstall side effect—and the default path stores
an immutable release and baseline under agent-bios-owned state. It installs the
`agent-launch` entrypoint and its own profile/catalog files, but does not change native
Claude/Codex globals, discovery directories, settings, hooks, or shell command
resolution unless the user explicitly restores the optional shell connection.

```bash
npm install -g agent-bios
agent-bios install     # store an immutable private release and baseline
agent-bios onboard --domains builder-base,multi-agent-orchestration
agent-bios verify      # verify stored bytes/catalog/baseline; not host activation
agent-bios status      # show the private release, baseline, conflicts, and evidence state
agent-bios corpus      # rich Corpus Studio in a TTY; list in a non-TTY
agent-launch claude    # open the launch TUI for Claude
agent-launch codex     # open the launch TUI for Codex
agent-bios shell restore # opt in: bare claude/codex opens the TUI
agent-bios shell remove  # remove only that optional shell connection
agent-bios reset       # preview reset; keep sources, snapshots, and pins
agent-bios reset --apply --yes --expected-revision REV # use the revision returned by preview
agent-bios migrate     # preview legacy global cleanup; --apply --yes performs it
agent-bios update      # git pull + reinstall (clone), or print the npm update line
agent-bios uninstall   # remove owned runtime entries; retain user corpus and pinned sessions
```

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

`install`, `onboard`, `reset`, `migrate`, and `uninstall` expose dry-run or preview
paths appropriate to their mutations. A pre-existing owned launcher/profile path whose
bytes no longer match the recorded copy is reported as an owned-path conflict rather than
overwritten. `migrate` is the separate recovery-backed operation for a legacy global
installation: preview is the default, applying requires `--apply --yes`, ambiguous
ownership refuses the apply, and later private operations do not fall through to a
global writer. Setting `AGENT_BIOS_LEGACY_INSTALL=1` selects the old deployer only for
compatibility and migration regression work; it is not the user default.

The legacy compatibility deployer preserves guide paths named only by a previous
manifest when the current source no longer establishes their ownership. It names
these remnants for manual inspection and leaves them out of the new ownership
manifest, so later uninstall does not claim them. Current source-owned members
retain normal backup and selection cleanup; private snapshot installation uses its
own authoritative inventory.

After updating a legacy global installation, run `agent-bios migrate` before the
first private `install`. Its preview identifies exact managed regions, legacy
manifest paths and learning sources. `agent-bios migrate --apply --yes` backs up
the originals, transfers and verifies learning records, retires the legacy paths,
then installs the private release. A central-only Codex file and the unmodified
empty Claude learning seed do not require a learning JSONL file; actual learning
content without its source still requires attention.

An interrupted migration is visible in `status` and blocks configuration readers
and unrelated writes. Re-run `agent-bios migrate --apply --yes` to resume its
pinned release and recorded path versions. A completed private installation is
not repeated, and later cleanup cannot delete its replacement launcher/profile.
Intervening edits are preserved and reported instead of overwritten. Older
incomplete journals without replay evidence require reconciliation from their
backups rather than a guessed replay. Existing private-session replay retains the
previous confirmed release until migration completes.

Before applying or resuming, stop the old global collectors that can still append a native
learning JSONL or rewrite its native prose/entry file. The migration checks the
recorded native state immediately before commit, but no filesystem check can make
a noncooperating writer atomic after that final observation. If it reports a
changed native target, preserve only the affected paths and restore only those
paths to the journal's recorded `after` state before resuming the old migration.
Do not replace a whole native directory or edit the journal.

For a validated late-input recovery, set `JOURNAL` to the one `NEEDS_RECOVERY`
migration journal and pass only the specific changed JSONL, prose, or entry paths
that its error named. This makes a new durable copy under that journal's existing
`backup_root`, verifies the copy, and then restores a changed target from its
recorded `after` bytes/existence/mode or an input-only path to its recorded
unchanged existence. It rejects a path absent from the journal, symlinks, and
non-regular files before writing any backup. New private journals retain exact
bytes for input-only native files, so the command can restore an originally
present input while preserving its current mode (or using `0600` if it is
absent). Historic digest-only journals still need an external byte-identical
backup; the command refuses to invent their missing bytes.

```sh
JOURNAL="${AGENT_BIOS_STATE_DIR:-$HOME/.local/share/agent-bios}/runtime/migrations/<migration-id>/journal.json"
python3 - "$JOURNAL" \
  "$HOME/.codex/personal/learnings.jsonl" <<'PY'
import base64, hashlib, json, os, sys, tempfile
from pathlib import Path

journal = Path(sys.argv[1])
data = json.loads(journal.read_text(encoding="utf-8"))
backup_root = Path(data.get("backup_root", ""))
if data.get("kind") != "migrate" or data.get("state") != "NEEDS_RECOVERY" or backup_root != journal.parent / "backup":
    raise SystemExit("expected one validated NEEDS_RECOVERY migration journal")
targets = {Path(entry["path"]): entry for entry in data["paths"]}
inputs = {Path(path): version for path, version in data["inputs"].items()}
selected = [Path(value).expanduser() for value in sys.argv[2:]]
unknown = [str(path) for path in selected if path not in targets and path not in inputs]
if not selected or unknown:
    raise SystemExit("name one or more exact journal paths; unknown: " + ", ".join(unknown))

planned = []
for path in selected:
    entry = targets.get(path)
    version = entry["after"] if entry is not None else inputs[path]
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SystemExit(f"refusing unsafe native path: {path}")
    root = next((parent for parent in (path.parent, *path.parents)
                 if parent.name in {".claude", ".codex"}), None)
    if root is None or root.is_symlink():
        raise SystemExit(f"recovery supports an exact Claude/Codex native path, not: {path}")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise SystemExit(f"refusing symlink ancestor: {current}")
    planned.append((path, entry, version))

if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
    raise SystemExit(f"refusing unsafe recovery root: {backup_root}")
backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
recovery = Path(tempfile.mkdtemp(prefix="recovery-before-resume-", dir=backup_root)) / "files"
for path, entry, version in planned:
    if path.exists():
        saved = recovery / str(path).lstrip("/")
        saved.parent.mkdir(parents=True, exist_ok=True)
        before = path.read_bytes()
        saved.write_bytes(before)
        saved.chmod(path.stat().st_mode & 0o777)
        if saved.read_bytes() != before:
            raise SystemExit(f"backup did not verify: {saved}")
    if not version["exists"]:
        path.unlink(missing_ok=True)
        continue
    encoded = version.get("bytes_b64")
    if not isinstance(encoded, str):
        raise SystemExit(f"journal records only a digest for existing input; restore it from an exact external backup: {path}")
    body = base64.b64decode(encoded.encode("ascii"), validate=True)
    if hashlib.sha256(body).hexdigest() != version["sha256"]:
        raise SystemExit(f"journal after bytes are invalid: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        mode = entry["mode"] if entry is not None else (path.stat().st_mode & 0o777 if path.exists() else 0o600)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
print(recovery)
PY
```

Resume the old journal with `agent-bios migrate --apply --yes`. After it commits,
restore only the preserved late record (`B`) from the printed recovery directory
to its original native path, then run a fresh `agent-bios migrate` preview and
`agent-bios migrate --apply --yes`. The new migration imports `B` through the
normal learning-id deduplication path. Leave every other recovery copy in place
as evidence; it is not an instruction to restore all saved native files.

```sh
RECOVERY_BACKUP='<the directory printed above>'
B="$HOME/.codex/personal/learnings.jsonl"  # the one path you deliberately preserved
cp "$RECOVERY_BACKUP/${B#/}" "$B"
agent-bios migrate
agent-bios migrate --apply --yes
```

Corpus Studio and the machine CLI are views over the same `CorpusStore`. The CLI
provides `list`, `search`, `show`, `history`, `status`, and `snapshot`; mutations are
semantic JSON passed to `plan`, followed by `apply PLAN --expected-revision REV`.
Implemented operations are create, update (including consumption surface), remove,
installed-item restore, personal-item recover, selection, reset, and rollback. Stable
`CorpusRef` identities survive those changes. The current `ContentRef` hashes the
baseline, resolved selection, authoring/item/learning/promotion digests, catalog and
store implementation digests, and management bootstrap. There is not yet a standalone undo command,
arbitrary package authoring/import, automatic semantic conflict resolution, or verified
native skill-menu registration; those design stages must not be inferred from the
library UI.

New personal identities are allocated once in the creation plan and remain stable
on retry; reset and history rollback do not make retired identities reusable.
Member files are the content authority: `primary_member` identifies the main file,
and `body` is its view or edit alias. The manager applies a body edit to that file
for all clients. Divergent older body/member values stay visible until an explicit
content choice reconciles them; old immutable snapshots are not rewritten.

Installation and rollback validate the target baseline and personal field/member
changes together. Conflicts preserve the current selection rather than dropping
items from a successful snapshot. Installation publishes a complete corpus/config
association under the same lock used by readers. Pending publication is disclosed
by status and prevents a new configured launch from reading mixed state; bare and
pinned replay can use the last confirmed immutable release.

Full reset returns an `expected_revision` in its preview. Pass that value with
`--apply --yes`; a changed preview is refused. Retry the accepted revision to finish
an interrupted reset, or review and accept a fresh revision to replace a stale
reset intent. Later user changes and replacement credentials are not overwritten
by the old intent. Nonsecret settings are archived; token bytes never are.

Native corpus consumption is default-off. `agent-bios corpus snapshot --host codex
--native --json` (or `--host claude`) composes a preview; `agent-launch --corpus-native`
opts one configured session into selected corpus hooks. Both hosts use the same
installed Python carrier and typed `event`/`matcher` binding. Authoring accepts the
combined event vocabulary; compilation reports an event unsupported by the selected
host without changing its name or executing it through another event.

Claude receives a namespaced plugin per CorpusRef through `--plugin-dir`. Codex
receives inline `hooks.<Event>` config through per-session `-c` arguments. Existing
user, project and session hooks remain present, and resume retains the pin's exact
registrations. Neither adapter installs global hooks. Codex hook enablement and native
trust still apply: new or changed definitions need review in `/hooks`. Discovery is
checked before launch, but discovery alone does not establish execution. Hooks use the
host's command permissions; opting in permits the selected carrier to run. Editing an
event binding does not rewrite the Python carrier's input/output contract.

Native corpus agents currently use Claude plugins and retain authored frontmatter and
plugin-qualified names, distinct from launcher's bare tier agents. A Codex agent
projection still needs to translate agent-specific model and tool restrictions; this
does not limit shared hook delivery. Arbitrary prose promoted to `event` or `delegated`
cannot become executable, and hidden discovery/config members are refused.

Tier defaults come from the launch profile and the guides' Environment Binding
tables. Claude Haiku 4.5 has no effort parameter: its tier entry, native agent
definition and projected call omit it. SWEEP is one-rule-per-item read-only work.
As a main seat it disables child delegation and requires review off (for example,
Solo); a requested review needs a HELM or WORKHORSE main instead. Codex SWEEP mains
use a read-only sandbox; Claude SWEEP mains use restricted Read/Glob/Grep tools
and an empty, strict MCP configuration. Other main roles retain their selected
policies, and explicit personal model/effort overrides remain available.

The private install does not replace the `codex` or `claude` shell commands by default. Run
`agent-launch claude` or `agent-launch codex` explicitly to open the preflight, or pass `--preset NAME HOST` for a
configured non-interactive launch. Software Engineer / Vanilla structurally projects
no agent-bios snapshot, launch contract, tier binding, or permission flag. After a
fresh private install—or after an explicit legacy migration—the native CLI therefore
receives no automatic agent-bios content; the user's own native global and project
instructions still follow the host's normal loading rules. `--resume-session ID`
loads the recorded host/session pin rather than resolving current defaults.

**Shell connection** in the root TUI offers **Restore connection** and **Remove
connection**, with confirmation before writing. The same owner is available as
`agent-bios shell` (status), `agent-bios shell restore`, and `agent-bios shell remove`;
`--dry-run` previews either action. Restore backs up existing files and adds one
managed block to `${ZDOTDIR:-$HOME}/.zshrc`, plus a managed `shell.zsh`. Open a new
terminal or source that `.zshrc` to load it. Interactive, argument-free `claude` and
`codex` then open the TUI; argument-bearing and non-TTY calls go to the original CLI
without added permission flags. Removal preserves other shell text and withdraws
loaded managed wrappers on the next shell command. An edited managed file or block
is preserved and reported for reconciliation, not overwritten. Backups remain private
under `runtime/shell-backups/`; `ZDOTDIR` must match the connection's recorded path.
Updates preserve an opted-in connection; reset and uninstall remove it. This setting
never edits global `AGENTS.md`/`CLAUDE.md`, project files, or corpus content. Ordinary
private installation also leaves those globals alone; explicit `migrate` can remove
the old agent-bios-managed regions and imports while preserving user-authored text.
First opt-in records ownership before publishing shell wiring, so interrupted restores
remain recoverable. Reset and uninstall also detect receipt-less managed scripts from
older interrupted restores. Install repairs a missing or non-executable owned launcher;
an unavailable launcher falls back to the native CLI. Recovery rechecks path ancestors
before writing and refuses redirected symlink targets.

### Understand a corpus bundle

Choose **Understand!** in the root TUI, or run:

```bash
agent-bios understand list
agent-bios understand show core-purpose
agent-launch --understand core-purpose claude   # or codex
```

The selection is a coherent bundle, not an individual file: core groups cover goals
and scope, decision support, adaptation, evidence/safety, and retained learning;
domain and personal bundles come from the effective corpus. A session freezes its
selected source references and edited content. The tutor explains the purpose,
background, mechanisms, tradeoffs, and limits, distinguishing documented rationale
from inference. Each active learning turn ends with one goal-relevant question and
waits for the user. Incidental ambiguity does not force a detour; pause and stop
requests end the questioning. `understand!` also works through the shared skill in
an activated session. Learning excerpts are data, not permission to run their commands.

A meaningful flaw or alternative first introduced by the user can unlock a persistent
pixel trophy. Tutor-originated ideas, leading hints, and echoes do not qualify. The
discovery flow binds the native human session, checks recorded turn provenance and
ordering, and asks for a later exact save confirmation. Unsupported provenance leaves
the award pending, without blocking learning. Significance and semantic originality
remain explicit tutor/user judgments; transcript validation does not prove them or
authenticate against an owner who can edit local files. Only a successfully saved
requested-only personal corpus note can unlock the trophy. The CLI prints it, and the
TUI shows it when there is room. Retries do not duplicate the note; updates and note
deletion retain the trophy. Full reset archives the active unlock generation and clears
the display; older discovery records cannot reactivate it. Native global files and
corpus source rules are not rewritten by learning.

Activated sessions include the user's global instruction documents by default.
**Custom → My global instruction files** can exclude them, or use
`agent-launch --preset balanced --exclude-global-instructions claude`. The CLI flag
sets Custom's initial choice; the final visible choice is what gets saved and run.
The choice is retained by managed resume, which cannot change it through a new flag.

Exclusion currently supports Claude Code 2.1.263 and newer: a per-call
`claudeMdExcludes` setting omits the global `CLAUDE.md`, its imports, and user
`rules/`. Project instructions and project memory remain, as do native settings,
authentication, tool registrations, and permissions. No global file is rewritten.
An existing CLI `--settings` argument, ambiguous relative/empty configuration home,
symlinks, glob characters in the configuration path, or a project/global file alias
is refused rather than replaced or silently included. Current Codex exclusion is
unavailable; its native loader has no selective global-document switch. Vanilla
and ordinary CLI launches retain their native loading behavior.
This controls automatic instruction loading, not file access or memory erasure:
tools can still open files, and project memory or prior conversation content can
contain instructions independently of the excluded documents.

The preflight keeps the current setup above each choice, supports the configured model
catalog and **Other**, and offers Builder presets, Software Engineer / Vanilla,
Session distill, Custom, Language, and **Corpus Studio**. Studio is the same backend as
`agent-bios corpus`: it searches and renders the library, edits Markdown and
consumption surface, and requires Preview then revision-bound Apply. In environments
without Textual, the corpus client and launcher retain numbered fallbacks; the corpus
editor uses `$VISUAL`/`$EDITOR` when available. Interface catalogs change only human
UI text; model-consumed corpus remains English.

Every arrow-key TUI selection screen keeps the complete current setup in a fixed top
panel, followed by the highlighted option's description and the option list. Custom
opens a persistent settings hub for the main tier, review setup, host policy, global instruction files, and tier
bindings. Every edit returns to that hub; **Start with these settings** is the final
launch confirmation, while **Exit without launching** cancels it. In the numbered
launcher fallback, `b` is the back command. These controls configure an explicit
agent-bios launch; they do not restore global instruction installation. Optional
shell wiring is controlled separately from the root **Shell connection** menu.

Review runs cross-family by default (`review_family`, default `cross`; `same` restores today's same-family projection): because the main's tiers are one model family, every dispatchable review route — native and the deep route — runs on the opposite family. The exception is `slash-review`, the host's own built-in review command (`/code-review` on Claude, with `ultra` for its deep multi-agent pass; `/review` on Codex): it needs no dependency and always resolves, but being the main's own command it cannot be dispatched cross-family, so under `cross` it runs as the same-family floor and its verdicts are labeled PROPOSED. A Claude main dispatches gpt/codex review (native via the `codex-run` reviewer wrapper resolved under `$CODEX_HOME/bin`, deep via plain `codex exec -m <frontier model> -c model_reasoning_effort="ultra"` with a self-contained packet on stdin — `-c service_tier="fast"` is the explicit faster, shallower opt-in); a Codex main dispatches Anthropic/Claude review (native via `claude -p --permission-mode plan`, deep via the `claude` CLI headless with the keyword `ultracode` in the prompt, which is what opens Claude Code's dynamic workflow for that turn). The concrete reviewer command, resolved absolute path, and opposite-family tier bindings are named in the injected session-start contract; cross-family reviewers are dispatched as read-only subprocesses, not CLI-native subagents, since neither CLI hosts the other family as a native subagent. When a cross-family route is unavailable at launch or unauthenticated at use time it degrades to same-family native subagent review labeled PROPOSED (family collapse) rather than blocking; a requested non-none review with no cross-family route and no same-family fallback (delegation off) stays fail-closed. A reviewer this launcher has never seen is yours to add: **Register another reviewer…** in the review editor asks for the descriptor a method needs, proves the candidate by running it through the real config reader before a byte is written, and appends it to `review-methods.local.toml` beside your config — a file the installer never deploys, verifies, or overwrites, whose entries face exactly the validation a shipped one does and whose name may not shadow a shipped method. A refusal shows the reader's own message and leaves that file byte-identical. Review setup means configured/requested; this launcher does not claim that review completed, and unavailable runtimes such as Ultrawork are not offered until integrated.

Both the legacy shell adapter and the optional private shell connection preserve
argument-bearing and non-TTY calls as direct backend invocations. The private
connection adds no permission flags on that path. Without opting in, the private
default installs no shell functions; an explicit `agent-launch` call projects a
launch profile or corpus snapshot.

Direct `agent-launch` calls still require a valid profile to resolve the backend command and its default arguments. `--preset`, `--custom`, or `--dry-run` select the configured-launch path even when non-TTY or combined with `--no-tui`; a non-TTY bare `--dry-run` deterministically uses Balanced, and a custom profile without that preset must pass `--preset NAME`. Forwarded backend arguments are appended verbatim after the projected defaults; one that would override a projected option (the seat, the contract, delegation, policy) is refused at launch so the contract keeps describing the run, and the summary discloses forwarded arguments when present. For scripted configured launches, call `$HOME/.local/bin/agent-launch --preset NAME --yes HOST -- ...` or add `$HOME/.local/bin` to `PATH`. The summary goes to stderr so backend stdout stays machine-consumable.

When the internal Codex wrappers are available to a configured route, `codex-helm` follows the local CLI default and launches the HELM main with `--dangerously-bypass-approvals-and-sandbox`; an explicit `--sandbox MODE` disables bypass for that run regardless of flag order. `AGENTS.md` gives root/main local Codex sessions standing ordinary-subagent authorization when the delegation gates fire. A non-Ultra HELM main sets native multi-agent off by default and instructs HELM to send tiered dispatch through the internal `codex-run` adapter, where the selected model, effort, and sandbox are pinned; native multi-agent defaults on only when the HELM main itself is explicitly Ultra. FRONTIER is instructed to run as a separate `gpt-6-astra` root that is always read-only, at max by default, Ultra for genuinely divisible complex work, or a lower supported effort when cost or latency dominates. Because the HELM main has bypass authority and arbitrary expert `-c` by design, this dispatch route is an instruction-backed, live-E2E-verified default rather than a security boundary. Keep `codex-run` as the low-level internal adapter, not as a user-facing policy boundary. Both wrappers accept `-c key=value` as an expert override, and that override may intentionally change wrapper defaults for a single run. The private installer keeps wrapper files in its immutable release rather than populating `$CODEX_HOME/bin`; a route that still names a native-home wrapper is unavailable until its adapter path is resolved.

`claude-run` is the Claude-side review adapter carried by the release, and it takes `--model` and `--effort` to pin the seat. Omitting either warns and dispatches anyway, matching `codex-run`: refusing outright turned "the review ran unpinned" into "the review did not run", which is the worse of the two. The honest signal is downstream instead — an unpinned dispatch can name no seat, so it emits no receipt and the method adjudicates to UNKNOWN rather than to a clean pass. Its default denies the mutating tools, which is not the OS-level sandbox its Codex twin gets — do not read the two defaults as equivalent guarantees.

**Review receipts.** A launch reports what it *projected*, because at launch no review has run — so a clean verdict without a receipt is PROPOSED, never ACHIEVED. Given `REVIEW_RECEIPT_DIR`, both adapters record what they observed of the dispatch they just performed: exit status, a hash of the packet fed in, a hash of the bytes returned, and the seat actually sent. Unset, they behave exactly as they would otherwise and write nothing. `agent-launch --fold-receipts DIR PACKET MAIN_DISPATCH_ID` folds a run into a `ReviewReceipts/v1` bundle — several passes of one method become the one record it is judged on — and `agent-launch --verify-receipts PLAN BUNDLE` adjudicates it, exiting non-zero unless every selected method verified. Adapting another tool needs no change here: call `agent-launch --emit-receipt` from your adapter and prove it conforms with `agent-launch --check-adapter SEAT -- CMD`, which is adjudicated by the same code that credits a real review. A receipt is still written by whoever ran the review, so this buys drift rather than honesty: what it stops is a reviewer that quietly never ran, returned nothing, or exited non-zero reading as a clean pass.

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

## Adopting elsewhere

Keep the rule layers. Swap checklist: every line carrying the `(private)` private-binding marker — today the global file's response-language preference; guides' `Environment Binding` author examples adopt the marker as they are touched — plus the "설계" design-trigger word in the global file and the skill/MCP names inventoried in `DEPENDENCIES.md` (the `spreadsheet-processing` skill, the review MCP). The other direction is enforced, not asked: `gates/check-hygiene.py` refuses org identifiers anywhere in the shipped distribution and author identifiers outside marked lines or per-reason exemptions. Then re-measure `Evidence Base` numbers in your environment before tuning.

## Scope

The repository and npm package contain corpus sources and private runtime machinery,
not a user's authoring state, learning events, snapshots, pins, activation journals,
credentials, native settings, or generated temporary files.
