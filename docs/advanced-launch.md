# Launch configuration

[← Overview](../README.md) · [Setup](setup.md) · [Instructions](instructions.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

Inspect settings before launching. Some Builder and internal-wrapper defaults use permission bypass. A configured review or registered hook is not evidence that it ran.

## Preflight and settings

The preflight keeps the current setup above each choice, supports the configured model
catalog and **Other**, and offers Builder presets, Software Engineer / Vanilla,
Session distill, Custom, Language, and **Instructions Studio**. Studio is the same backend as
`agent-bios instructions`: it searches and renders the library, edits Markdown and
consumption surface, and requires Preview then revision-bound Apply. Packaged
entrypoints validate and temporarily extract their included UI bundle before loading
Rich/Textual. A missing or corrupt bundle fails explicitly; no preinstalled Textual
environment is required. Interface catalogs change only human UI text;
model-consumed instructions remain English.

Every arrow-key TUI selection screen keeps the complete current setup in a fixed top
panel, followed by the highlighted option's description and the option list. Custom
opens a persistent settings hub for the main tier, review setup, host policy, global instruction files, and tier
bindings. Every edit returns to that hub; **Start with these settings** is the final
launch confirmation, while **Exit without launching** cancels it. When the numbered
launcher flow is selected with `--no-tui`, `b` is the back command. These controls configure an explicit
agent-bios launch; they do not restore global instruction installation. Optional
shell wiring is controlled separately from the root **Shell connection** menu.

## Tiers and restricted seats

Tier defaults come from the launch profile and the guides' Environment Binding
tables. Claude Haiku 4.5 has no effort parameter: its tier entry, native agent
definition and projected call omit it. SWEEP is one-rule-per-item read-only work.
As a main seat it disables child delegation and requires review off (for example,
Solo); a requested review needs a HELM or WORKHORSE main instead. Codex SWEEP mains
use a read-only sandbox; Claude SWEEP mains use restricted Read/Glob/Grep tools
and an empty, strict MCP configuration. Other main roles retain their selected
policies, and explicit personal model/effort overrides remain available.

## Global instruction files

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

## Native hooks and agents

Native instructions consumption is default-off. `agent-bios instructions snapshot --host codex
--native --json` (or `--host claude`) composes a preview; `agent-launch --instructions-native`
opts one configured session into selected instructions hooks. Both hosts use the same
installed Python carrier and typed `event`/`matcher` binding. Authoring accepts the
combined event vocabulary; compilation reports an event unsupported by the selected
host without changing its name or executing it through another event.

Claude receives a namespaced plugin per InstructionsRef through `--plugin-dir`. Codex
receives inline `hooks.<Event>` config through per-session `-c` arguments. Existing
user, project and session hooks remain present, and resume retains the pin's exact
registrations. Neither adapter installs global hooks. Codex hook enablement and native
trust still apply: new or changed definitions need review in `/hooks`. Discovery is
checked before launch, but discovery alone does not establish execution. Hooks use the
host's command permissions; opting in permits the selected carrier to run. Editing an
event binding does not rewrite the Python carrier's input/output contract.

Native instructions agents currently use Claude plugins and retain authored frontmatter and
plugin-qualified names, distinct from launcher's bare tier agents. A Codex agent
projection still needs to translate agent-specific model and tool restrictions; this
does not limit shared hook delivery. Arbitrary prose promoted to `event` or `delegated`
cannot become executable, and hidden discovery/config members are refused.

## Optional shell connection

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
never edits global `AGENTS.md`/`CLAUDE.md`, project files, or instructions content. Ordinary
private installation also leaves those globals alone; explicit `migrate` can remove
the old agent-bios-managed regions and imports while preserving user-authored text.
First opt-in records ownership before publishing shell wiring, so interrupted restores
remain recoverable. Reset and uninstall also detect receipt-less managed scripts from
older interrupted restores. Install repairs a missing or non-executable owned launcher;
an unavailable launcher falls back to the native CLI. Recovery rechecks path ancestors
before writing and refuses redirected symlink targets.

## Scripted launches and forwarded arguments

Both the legacy shell adapter and the optional private shell connection preserve
argument-bearing and non-TTY calls as direct backend invocations. The private
connection adds no permission flags on that path. Without opting in, the private
default installs no shell functions; an explicit `agent-launch` call projects a
launch profile or instructions snapshot.

Direct `agent-launch` calls still require a valid profile to resolve the backend command and its default arguments. `--preset`, `--custom`, or `--dry-run` select the configured-launch path even when non-TTY or combined with `--no-tui`; a non-TTY bare `--dry-run` deterministically uses Balanced, and a custom profile without that preset must pass `--preset NAME`. Forwarded backend arguments are appended verbatim after the projected defaults; one that would override a projected option (the seat, the contract, delegation, policy) is refused at launch so the contract keeps describing the run, and the summary discloses forwarded arguments when present. For scripted configured launches, call `$HOME/.local/bin/agent-launch --preset NAME --yes HOST -- ...` or add `$HOME/.local/bin` to `PATH`. The summary goes to stderr so backend stdout stays machine-consumable.

## Review routing

Review runs cross-family by default (`review_family`, default `cross`; `same` selects same-family projection): because the main's tiers are one model family, every dispatchable review route — native and the deep route — runs on the opposite family. The exception is `slash-review`, the host's own built-in review command (`/code-review` on Claude, with `ultra` for its deep multi-agent pass; `/review` on Codex): it needs no dependency and always resolves, but being the main's own command it cannot be dispatched cross-family, so under `cross` it runs as the same-family floor and its verdicts are labeled PROPOSED. A Claude main dispatches gpt/codex review (native via the `codex-run` reviewer wrapper resolved under `$CODEX_HOME/bin`, deep via plain `codex exec -m <frontier model> -c model_reasoning_effort="ultra"` with a self-contained packet on stdin — `-c service_tier="fast"` is the explicit faster, shallower opt-in); a Codex main dispatches Anthropic/Claude review (native via `claude -p --permission-mode plan`, deep via the `claude` CLI headless with the keyword `ultracode` in the prompt, which is what opens Claude Code's dynamic workflow for that turn). The concrete reviewer command, resolved absolute path, and opposite-family tier bindings are named in the injected session-start contract; cross-family reviewers are dispatched as read-only subprocesses, not CLI-native subagents, since neither CLI hosts the other family as a native subagent. When a cross-family route is unavailable at launch or unauthenticated at use time it degrades to same-family native subagent review labeled PROPOSED (family collapse) rather than blocking; a requested non-none review with no cross-family route and no same-family fallback (delegation off) stays fail-closed. A reviewer this launcher has never seen is yours to add: **Register another reviewer…** in the review editor asks for the descriptor a method needs, proves the candidate by running it through the real config reader before a byte is written, and appends it to `review-methods.local.toml` beside your config — a file the installer never deploys, verifies, or overwrites, whose entries face exactly the validation a shipped one does and whose name may not shadow a shipped method. A refusal shows the reader's own message and leaves that file byte-identical. Review setup means configured/requested; this launcher does not claim that review completed, and unavailable runtimes such as Ultrawork are not offered until integrated.

## Internal adapters and permission boundaries

When the internal Codex wrappers are available to a configured route, `codex-helm` follows the local CLI default and launches the HELM main with `--dangerously-bypass-approvals-and-sandbox`; an explicit `--sandbox MODE` disables bypass for that run regardless of flag order. `AGENTS.md` gives root/main local Codex sessions standing ordinary-subagent authorization when the delegation gates fire. A non-Ultra HELM main sets native multi-agent off by default and instructs HELM to send tiered dispatch through the internal `codex-run` adapter, where the selected model, effort, and sandbox are pinned; native multi-agent defaults on only when the HELM main itself is explicitly Ultra. FRONTIER is instructed to run as a separate `gpt-6-astra` root that is always read-only, at max by default, Ultra for genuinely divisible complex work, or a lower supported effort when cost or latency dominates. Because the HELM main has bypass authority and arbitrary expert `-c` by design, this dispatch route is an instruction-backed, live-E2E-verified default rather than a security boundary. Keep `codex-run` as the low-level internal adapter, not as a user-facing policy boundary. Both wrappers accept `-c key=value` as an expert override, and that override may intentionally change wrapper defaults for a single run. The private installer keeps wrapper files in its immutable release rather than populating `$CODEX_HOME/bin`; a route that still names a native-home wrapper is unavailable until its adapter path is resolved.

`claude-run` is the Claude-side review adapter carried by the release, and it takes `--model` and `--effort` to pin the seat. Omitting either warns and dispatches anyway, matching `codex-run`: refusing outright turned "the review ran unpinned" into "the review did not run", which is the worse of the two. The honest signal is downstream instead — an unpinned dispatch can name no seat, so it emits no receipt and the method adjudicates to UNKNOWN rather than to a clean pass. Its default denies the mutating tools, which is not the OS-level sandbox its Codex twin gets — do not read the two defaults as equivalent guarantees.

## Review receipts

**Review receipts.** A launch reports what it *projected*, because at launch no review has run — so a clean verdict without a receipt is PROPOSED, never ACHIEVED. Given `REVIEW_RECEIPT_DIR`, both adapters record what they observed of the dispatch they just performed: exit status, a hash of the packet fed in, a hash of the bytes returned, and the seat actually sent. Unset, they behave exactly as they would otherwise and write nothing. `agent-launch --fold-receipts DIR PACKET MAIN_DISPATCH_ID` folds a run into a `ReviewReceipts/v1` bundle — several passes of one method become the one record it is judged on — and `agent-launch --verify-receipts PLAN BUNDLE` adjudicates it, exiting non-zero unless every selected method verified. Adapting another tool needs no change here: call `agent-launch --emit-receipt` from your adapter and prove it conforms with `agent-launch --check-adapter SEAT -- CMD`, which is adjudicated by the same code that credits a real review. A receipt is still written by whoever ran the review, so this buys drift rather than honesty: what it stops is a reviewer that quietly never ran, returned nothing, or exited non-zero reading as a clean pass.

See [verification and limits](session-model.md#verification-and-limits) for the evidence boundary, authenticated resume, and unsupported native named profiles.
