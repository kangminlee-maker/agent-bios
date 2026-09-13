# Set up agent-bios through conversation

This guide uses the same installation controller as the terminal wizard. The
conversation collects choices and presents effects; `setup` validates and executes
them. It needs local command and file access on the intended machine, Bash, and
Python 3.11 or newer. Codex CLI, an additional model login, and Textual are not
requirements for this route.

## Start without an installed skill

The user can request installation using the public repository link. Follow the
repository's root `INSTALL.md` to obtain and verify the source, select the language
and run `setup start`. The agent resolves paths; the user does not need a checkout,
an installed skill or a long installation prompt. An explicitly selected trusted
local source remains valid. Preserve the acquisition's exact revision and location
for the review and any resume. If the selected public revision lacks conversation
setup, report that limitation instead of invoking an older installation route.

## Choose the entrypoint and language

For an already registered app bridge, run `python3 "$BRIDGE" setup start`, where
`BRIDGE` is the absolute helper path beside the loaded skill. Read the returned
`guide_path`. For an acquired source, use the verified `setup_argv` from its start
response. Keep using that entrypoint and the reported private roots throughout
the review. Shell variables from one app tool call do not persist to the next;
pass absolute arguments or set the variable in the same call.

`start` returns language choices, a suggested language and execution context without
probing dependencies or creating private setup state. Confirm English, 한국어 or
日本語, honoring an explicit language already chosen by the user, before `inspect`.
Use the selected language for questions and explanations; retain identifiers,
paths, versions, raw diagnostics and command arguments exactly. Use a native
question control when the current host exposes one for this interaction, or ask
ordinary concise questions. The conversation does not require custom widgets.

The commands below use `agent-bios` as shorthand for that verified entrypoint. In
an app bridge call, replace `agent-bios setup` with `python3 "$BRIDGE" setup`.

```bash
agent-bios setup inspect --language ko
agent-bios setup discover --project-root /absolute/project
```

## Collect and review the choices

Use `inspect`'s `default_plan`, inventory and choices. Present all dependency
capabilities with readiness, purpose and installation destination. Ready dependencies
are observations, not requested actions: include only chosen missing dependencies
with returned recipes in `dependencies`. Do not create shell recipes from model
memory. A dependency's presence does not authorize installing another one.

`retained_corpus` reports local personal instructions and host learning records
already stored on this device as `{target, label, item_count}`; localized labels are
in `display.retained_corpus`. Present this separately as a read-only storage view,
not as extra installation choices or evidence of active use. Counts cover stored,
nonremoved items regardless of enable overrides or current host/project eligibility,
and reveal no bodies. Do not copy these rows into `targets`; use the source `choices`
and the user's activation-policy decision.

Collect the six plan fields without asking the user to author JSON:

- `selection_mode` and `targets`: keep saved policy, no active corpus, all available
  corpus, or specific returned package/domain/item targets. Start from the returned
  default. No active corpus retains private library assets but delivers no corpus.
- `dependencies`: chosen installable inventory IDs; an empty list installs none.
- `app_bridge`: the explicit **Connect to the Codex app** choice, adding `$agent-bios`
  for setup and personal instruction management. Registration enables discovery only;
  each task still requires its own explicit corpus use.
- `project_roots` and `import_paths`: absolute project folders and explicitly
  selected files from discovery. Capture is independent of corpus selection.

Keep saved policy uses `selection_mode: null` and `targets: null`. No active corpus
uses `"none"` and `[]`. Explicit choices use `"selected"` and their target list;
all available corpus uses `"selected"` and `["all"]`.

Discovery checks known global instruction locations and the specified project
roots. Show detected sources before selecting them. Capture preserves originals
and prepares private evidence for later model review; it is not an automatically
optimized personal corpus. Read the import procedure only when the user requests
that subsequent review.

Save choices to a new caller-owned artifact. Run `plan` and save its complete
stdout bytes to another new caller-owned artifact:

```bash
agent-bios setup plan --language ko --input /absolute/choices.json > /absolute/review.json
```

The returned review envelope contains `review_id`, `context`, `language`,
`preview` and `summary`. Keep the entire envelope; do not reconstruct it from the
summary, copy only `preview`, change its IDs, or accept truncated output. Show the
concrete private paths, selected dependency commands/destinations, corpus policy,
app discovery change and selected capture sources. Keep the exact artifact
available for inspection. Preparing these caller-owned files is separate from
applying installation effects.

Apply the saved envelope only when its concrete choices are authorized. Existing
authorization for those exact choices does not require another confirmation.

```bash
agent-bios setup apply --input /absolute/review.json --review-id REVIEW_ID --yes
```

The engine checks the reviewed context, source bytes, private state and package
before its effects. If the review is stale, show a fresh plan and explain the
changed effects; do not bypass checks. Report completed dependencies, private
installation, bridge registration and pending import separately. A partial failure
or cancellation does not roll back completed external package installations.

## Continue or resume

```bash
agent-bios setup status --review-id REVIEW_ID
agent-bios setup resume --review-id REVIEW_ID
```

These commands do not execute the remaining installation. `status` reports the
recorded attempt in `receipt`, `result` and `state`; a past `complete` result does
not establish the current runtime's health. Inspect `handoff` for current readiness
and any `needs_action`. Package verification, full runtime verification and helper
verification are independent observations; one does not prove the others.
`replayed: true` means the existing attempt was returned without executing it again.
If `handoff.verification` is `"deferred"`, its readiness fields are null: they are
unverified, not false. Status can return recorded progress while setup holds the
private-state lock. Follow `needs_action` and retry status when that operation has
settled; require checked readiness before using a handoff to continue.

`resume` adds `remaining_plan`, `review` and `needs_action`. When `review` is
non-null, save that entire nested review object to a new caller-owned JSON artifact
using deterministic JSON extraction. Do not pass the enclosing status response or
`remaining_plan` to Apply. Preserve every review field, including `continuation`,
and use the nested review's own `review_id`. Review its remaining effects before
applying within the user's authorization. If `review` is null, inspect the stated
reason; unknown prior effects are not permission to replay package installation.
When `resumed_from` is present, the response has followed a receipt's `continued_by`
link to an existing continuation. Report the returned child `review_id` rather than
assuming the original ID is current.

After an explicit app registration succeeds, use `handoff.helper_argv` only when
`helper_usable` is true, appending `setup` and the desired operation.
`helper_verified` confirms helper bytes, while `helper_usable` also requires a
verified package and no pending work blocking it. Otherwise inspect `needs_action`
and current readiness before continuing. A usable helper can continue in this task
even if native skill discovery has not refreshed. Without a
verified helper, a verified runtime's `setup_argv` already includes `setup`;
`cli_argv` does not. Supply the returned `environment` with each call. These arrays
are command arguments, not shell snippets. Finish applying an existing review
through its reviewed entrypoint/context; changing entrypoints requires a fresh
review. Status and subsequent setup can use the verified handoff.
Do not create a duplicate personal skill or edit host discovery settings to force
refresh. Once discovered, `$agent-bios` is the ordinary entrypoint. Registration
on disk is not proof of discovery or corpus loading.

If capture completed, report its actual capture ID and returned next action. Its
semantic review, proposed consumption placement and revision-checked import are
separate from installation. Setup enables no hooks, native agent registration,
permissions or edits to global/project instruction files. Each app task requires
its own explicit corpus use; neither setup nor opening the app performs it.
