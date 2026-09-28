---
created_at: 2026-09-14T20:44:35+09:00
head: 35c75ca
kind: review
status: source-inspection-not-runtime-observation
---

# Current TUI entry audit for the zero-base first-screen design

Read-only code/test audit against the 19:33 target SSOT. No real installed state, account or network settings were changed; no terminal UI or installer was launched for this audit. Existing test code was inspected, not rerun. The findings below are information-architecture risks derived from code, not observed participant usability results.

Repository root: `/Users/kangmin/Documents/agent-bios-personal`. All source paths below are relative to this root.

## 1. There is no single current product first screen

| Invocation / arrival | Actual current destination and effect | Evidence |
| --- | --- | --- |
| Bare `agent-bios` | Help text. It is not a generic Studio home and does not open a TUI. | `install.sh:1832` defaults CMD to help; `:1746` owns usage. |
| `agent-bios install` / `onboard` in default private mode | Both enter the same Instructions installation flow. Interactive is the default; non-TTY callers must explicitly choose non-interactive. The first screen is language selection, then Instructions/dependencies/import/app-link choices. | `install.sh:1861–1869`; `compose/instructions_install.py:1766–1781`, `:1799–1827`. |
| `agent-bios setup start/inspect/plan/apply/status/resume` | Conversation/machine setup API, not the launch mode picker or the Instructions editor. The read/plan and exact apply/receipt operations are separate. | `install.sh:1853–1859`; `compose/instructions_setup_cli.py:192`, `:201`, `:230`, `:375`, `:450`. |
| `agent-bios instructions` with a TTY | Instructions Studio: private source library/editor. Without a TTY and no subcommand, it lists items. | `install.sh:1838–1839`; `compose/instructions.py:381–400`. |
| `agent-launch --instructions` | Opens the same Instructions Studio before launch configuration flow. | `launch/agent-launch.py:11065–11067`; `:4209–4213`. |
| `agent-launch claude` / `codex` in an interactive supported terminal | Host is already selected; root launcher menu asks for a mode, then preset/configuration. Bare `agent-launch` without a host is an argument error except explicitly hostless operations. | `launch/agent-launch.py:10813–10824`; `:11168–11220`; `:9301–9398`. |
| Bare `claude` / `codex` through an explicitly restored shell connection | The optional zsh wrapper routes bare interactive calls to the launcher. Argument/noninteractive calls preserve native dispatch behavior. This is not a new shell process or a Team selection. | `install.sh:1768–1770`, `:1794–1796`; `compose/test_instructions_shell.py:432`, `:483`. |
| `agent-bios shell` | Shell connection status/restore/remove management, not the main application hub. | `install.sh:1841–1842`; `:1768–1770`; `launch/i18n/ko.toml:24–39`. |

The legacy `cmd_onboard` under `install.sh:1407` is not the default private installation route; the earlier dispatch transfers default install/onboard to `instructions_install.py`. A zero-base design must not accidentally treat that historical checklist as the current default.

## 2. What the actual launcher first screen asks

The root menu is implemented by `pick_mode_and_preset` at `launch/agent-launch.py:9301`.

1. It reads Instructions status (`:9325`) and assembles three mode rows: Software Engineer, Builder and Session distill (`:9328–9341`).
2. It adds Instructions Studio; private installations also add Understand and Shell connection; when a config path exists, Language is another peer row (`:9342–9359`).
3. Before a choice is committed, it previews the Builder default and sets that as the setup panel (`:9388–9397`). Builder is the default highlighted mode (`:82`, `:9394`).
4. The rendered order is title → setup/Instructions reference panels plus any durable trophy → selected-item description → options → key footer (`:5149–5192`).
5. Moving the option highlight changes the description and the setup preview (`:5215–5232`). Enter/Space choose a menu value according to the menu contract (`:5236–5255`). The mode selection then opens a preset submenu (`:9432–9452`), rather than inherently starting work.
6. Actual Instructions snapshot projection happens later (`:11255–11269`) and rechecks the captured configuration generation (`:4200–4206`). A preview is therefore neither an active session nor a committed source selection.

The Korean catalog intentionally retains English mode names: `launch/i18n/ko.toml:3–9`. It describes Software Engineer through native CLI loading and Vanilla/Custom; Builder through installed Instructions plus Balanced/Deep review/Fast batch/Solo/Custom. Both describe ordinary development work, while their important distinction is how tooling and instructions are projected.

## 3. The state sources are different, despite sharing the first screen

| Displayed fact | Actual source | Qualification for the redesign |
| --- | --- | --- |
| Host | Explicit launcher argument, resolved backend/config | Known launch target type; not proof a new session exists or that this terminal is an active recipient. |
| Highlighted mode/preset | Menu-local selection; default Builder preview | Focus, selected draft and active runtime must have separate meanings. |
| “Current setup” panel | `setup_summary_lines(plan)` from the highlighted/default proposed plan | Despite `현재 설정`, this is often a prospective launch preview. `launch/agent-launch.py:4794–4833`, `:5059–5065`, `:5226–5232`; label at `launch/i18n/ko.toml:267`. |
| Models, tiers, review/delegation/execution policy | Loaded launch configuration and user presets | Execution arrangement, not professional role, Team work standards, source ownership or resource grants. `launch/agent-launch.py:4280–4295`, `:4794–4871`. |
| Private Instructions selection/baseline | `InstructionsStore.status()` via `load_instructions_status` | Stored selection and baseline; not observed delivery to the pending host. `launch/agent-launch.py:8327–8347`, `:8557–8569`. |
| Whether private Instructions mode is enabled | Explicit environment setting or `runtime/private-install.json` existence | Installation mode, not person authentication, Team membership, or selected environment readiness. `launch/agent-launch.py:4137–4142`. |
| Package version/update badge | `version.json` and cached update state | Distribution status, not a source edition or current work context. `launch/agent-launch.py:8231–8243`, `:8350–8368`. |
| Understand trophy | Durable Instructions-understanding manager state | Optional learning decoration; not work readiness or approval evidence. `launch/agent-launch.py:4224–4235`. |
| Launcher language | Explicit override, saved preference, then English | Screen language only; not the language/authority of source material. `launch/agent-launch.py:213–229`; `launch/i18n/ko.toml:20–21`. |
| Setup wizard defaults | Fresh install selects no active Instructions; installed state keeps saved selection | This is a future-delivery default, independent of a current app task's use. `compose/instructions_setup.py:363–369`. |
| Actual Codex app task delivery | Separate `AppSessions` receipts | Returned-as-context is not native activation or model reading. It is not the launch menu's state source. `compose/instructions_app.py:262`, `:297–304`, `:367–400`. |

The package-version renderer can schedule an update-cache refresh when due (`launch/agent-launch.py:8297–8318`, `:8364–8366`). For any later isolated screen probe, explicitly disable update checking and replace host/provider execution with fixture backends. This audit did not launch the UI or trigger that path.

## 4. Root information-architecture causes

### A. The first choice classifies implementation modes rather than the user's intended outcome

Software Engineer and Builder overlap as ordinary development jobs; their actual difference depends on understanding native loading, private Instructions, presets, delegation and review. Session distill is another job, while Studio, shell connection and language are management/settings. They appear as peers under “Mode.” The user must discover which level each row operates at before knowing whether it opens another menu, changes stored settings or starts work.

Evidence: `launch/agent-launch.py:9328–9359`; `launch/i18n/ko.toml:3–9`, `:24–48`.

### B. Focus preview is presented with the language of current applied state

The panel titled “현재 설정” is initialized from the Builder default and changes when an option is merely highlighted. That is useful preview behavior, but the heading does not distinguish “what would be used” from stored selection or actual use. The installed Instructions status is separately displayed, increasing the need for that distinction.

Evidence: `launch/agent-launch.py:9388–9397`, `:5218–5232`, `:8557–8569`; `launch/i18n/ko.toml:267`.

### C. Source/work environment and execution arrangement are mixed

The initial setup panel leads with host/preset, main tier, review, delegation, execution policy and model bindings. The separate Instructions panel then explains another state. There is no joined target work scope, I/K/M support or source/recipient limitation assessment. The current launcher is doing its existing job; it is not an implementation of the broader W01 contract.

Evidence: `launch/agent-launch.py:4794–4871`, `:5155–5168`; target `19:33 SSOT:1107–1127`, `:1215–1229`.

### D. Detailed configuration appears before the ordinary next action

In the real screen composition, technical reference panels and selected-item prose precede the option list. The UI has scrolling and sensible focus behavior, but those protections do not make the first decision easier to recognize. The first screen asks for a mode, then a preset, even when the host and launch intent were already provided by invoking `agent-launch codex` or a bare host wrapper.

Evidence: `launch/agent-launch.py:5149–5192`, `:10813–10824`, `:9309–9317`, `:9432–9452`.

### E. The three “setup/Studio” routes describe different effects

Installation first asks for a language and future Instructions delivery policy, includes optional app registration and capture, and changes installed runtime only on Apply. Instructions Studio opens a source library with Create/Edit/Remove/Restore/Recover/Reset and Effective/Installed/Change/Diff/History views. The launcher opens tool configuration. Similar entry words do not supply a common product-level expectation about the resulting change.

Evidence: `compose/instructions_setup_ui.py:95–107`, `:113–136`; `compose/instructions_ui.py:213–214`, `:277–337`; `install.sh:1750–1769`.

### F. Missing interpretation cannot be fixed with more counts or status labels

The code already distinguishes many necessary facts and protects against unavailable/malformed status. The issue is their primary ordering and meaning, not simply missing backend data. More setup rows would not explain whether the next action opens configuration, creates a candidate, changes a future default, or starts a new host. Package version, stored baseline and prospective preset must not be collapsed into a universal current/ready state.

Evidence: `load_instructions_status`/`instructions_summary_lines` (`launch/agent-launch.py:8327–8407`), `setup_summary_lines` (`:4794–4871`), and SSOT S05/S11's independent selection/support/eligibility dimensions.

## 5. Existing tests: useful protections, not evidence of comprehension

- `compose/test_instructions_ui_entrypoints.py:89–120` exercises clean-process and installed-private Instructions/launcher Textual entry, using temporary installs/stub hosts; corruption cases at `:133–150` require actionable failure rather than silent fallback.
- `compose/test_instructions_setup_ui.py:396–420` proves the first setup screen is language selection before controller construction and before side effects. The language/back flow at `:422` preserves input; these are intentional current behaviors, not evidence that a language gate is the optimal generic entry.
- `compose/test_instructions_setup.py:805–845` tests interactive versus machine dispatch; `:882–896` checks non-TTY and legacy flag boundaries.
- `compose/test_instructions_shell.py:432` and `:483` distinguish argument/noninteractive native calls from bare interactive interception. The shell connection is explicit, not a universal new application entry.
- `compose/test_instructions_ui.py:549` checks that highlight changes cannot retarget an editor or prepared plan. Preserve that distinction in any replacement first screen.
- `gates/check_parity.py:9154` drives the real MenuScreen stylesheet; `:10876` tests the TTY mode picker; `:11618` checks picker navigation; `:12168` and `:12227` check degraded status and rendered language/cell alignment.

These tests establish specified transitions, source derivation and layout/focus properties for the current UI. They do not establish that users understand the mode taxonomy, which state is applied, or what their next action changes. New comprehension claims require observation of actual/likely users.

## 6. Alignment with the current target design and recommended constraint

`CURRENT.md` selects the 19:33 SSOT and explicitly labels the old 15:04 map incomplete. Its S10 allows personal preparation without Team/project/predecessor/session; S11 distinguishes generic arrivals from exact work/source/review links and existing host work (`SSOT:1107–1116`, `:1175–1205`). Existing runtime remains evidence of present behavior, not the required information architecture for the new target.

The proposed direction is consistent with that purpose:

- **Generic Studio arrival:** show an outcome-oriented hub for someone who has not expressed an intent. Personal work remains a first-class route; Team creation/login is optional.
- **Host launcher arrival:** host and launch intent are already known. Go directly to W01 work preparation using the same information grammar, not through a redundant generic hub or SWE/Builder classification.
- **Separate two axes:** work scope and environment (Instructions/K/M with source conditions) versus execution tool/configuration (host/model/delegation/review/execution settings). A launch preset is not a profession, Team role, or work standard.
- **Keep three states distinct:** focused option; selected draft/preparation; actual adopted/used state. Merely opening menus, reading material or editing draft choices changes no prior work, active session, membership or source.
- **Show the result of the next action:** prepare/check first, then inspect exact expected target/effects before an explicitly named start/change action. Internal checks may be combined under one authorized intent; do not reinstate a universal Preview→Check→Use ceremony.
- **Do not infer missing facts:** CWD is a candidate work location, not proof of Team, task goal, allowed source range or historical decisions. A chosen host is a planned recipient type until a supported target/receipt exists.
- **Keep material effects visible:** delegated work, execution privilege changes, cost-relevant model/review choices, missing required evidence and recipient restrictions cannot disappear inside optional technical detail.
- **Use truthful unsupported/missing states:** no current Team/K/M provider, absent project data, unknown prior delivery and locked access have different remedies. Do not populate first use with the old mock task/history.

This is a fundamental entry-model change, not a demand to preserve old command/preset compatibility. The user's explicit compatibility waiver permits a cleaner target. Installation/bootstrap and shell connection still retain their separate side effects and should not be performed implicitly by opening the new home.

## 7. Narrow acceptance probes for the successor first screen

1. From a bare host launcher, the initial screen identifies the known host and planned action without requiring a second hub; no session/Team/history is invented.
2. From generic Studio with no Team, the user can reach personal preparation without signup, Team creation, source import or repository creation.
3. Moving keyboard focus reveals an option's explanation without changing selected draft or active state. Explicit selection changes only the draft, invalidating any older preview.
4. The user can explain which source environment and which execution configuration will be used, which prior state will stay unchanged, and whether the next action only prepares or actually executes.
5. Missing required bodies remain missing through recovery navigation; offline sufficient bodies can support only the declared permitted action. Denied metadata is not displayed as a helpful source preview.
6. After lock/signout or source/target/policy change, stale preview/late result cannot enable the action; unknown execution uses the same request/result identity rather than a fresh success screen.
7. Keyboard editing of a path/goal/text field retains native caret and input behavior; navigation keys must not silently submit or replace the current work.
8. The actual installed target and real terminal must eventually be tested separately. A compact HTML TUI-like prototype cannot certify IME, terminal cell widths, SSH, accessibility or host delivery.

Only this memo was written for the audit; a subsequently requested prototype is a separate explicitly simulated design artifact.
