# Dependencies

What agent-bios' scripts and rules depend on, with required capabilities and verified versions. Role-slot→model bindings are owned by each guide's `Environment Binding`; numeric defaults by each guide's `Evidence Base`. This file does not restate them — it inventories dependency *kinds* and points to their owners, so a version lives in exactly one place.

Korean: [`ko/DEPENDENCIES.md`](ko/DEPENDENCIES.md). Dates = verification time; update a date when the version is re-checked.

## Runtime tools (scripts) — owned here

| Tool | Required by | Required capability | Verified |
| --- | --- | --- | --- |
| `codex` (codex-cli) | `compose/corpus_session.py`, `launch/agent-launch.py`, `wrappers/codex-run.sh`, `wrappers/codex-helm.sh`; guide "Codex direct-drive" + "Session relocation" bindings | per-call `-c`; cwd-aware `app-server --stdio` `config/read`; durable `thread/start`, `thread/inject_items`, and `thread/read`; `codex resume`; existing `codex exec` and agent-config projection. The corpus session tests exercise config preservation and durable thread identity without a model turn | 0.153.4 · 2026-09-07 |
| `bash` | `install.sh`, `*/*.sh` | POSIX + arrays; runs on macOS system bash | 3.2.57 · 2026-07 |
| `python3` | `compose/corpus.py`, `compose/corpus_install.py`, `compose/corpus_session.py`, `compose/corpus_store.py`, `session-cost.py`, `launch/agent-launch.py` | Python 3.11+ stdlib (`tomllib`) owns every machine/non-TTY path, private file transaction, catalog/store operation, session journal, and numbered fallback. Textual is imported only for the interactive clients | 3.14.5 · 2026-09-07 |
| `textual` (managed venv) | `launch/agent-launch.py` preflight and `compose/corpus_ui.py` Corpus Studio; provisioner is `launch/provision-venv.sh` | Textual runtime in `~/.local/share/agent-launch/venv` (override `AGENT_LAUNCH_VENV`); each interactive client re-execs into it only on its TTY path. The private installer does not currently run the provisioner, so a fresh machine without that runtime uses numbered UI. Corpus Studio uses `Tree`, `MarkdownViewer(open_links=False)`, `TextArea(language="markdown")`, and `Select`; its numbered editor uses `$VISUAL`/`$EDITOR` when set | 8.2.8 · py 3.14.5 · 2026-09-07 |
| `jsonschema` (system python) | `learn/check-learning.py` (learning record gate; chained from `gates/check-parity.sh`) | JSON Schema Draft 2020-12 validator executing `learn/learning.schema.json` as the SSOT | 4.26.0 · 2026-07-20 |
| `zsh` | `launch/agent-launch.zsh` | legacy compatibility/regression path only: shell functions, TTY tests, argument-preserving dispatch. The private default does not install shell interception | 5.9 · 2026-07-13 |
| `git` | scripts, workflow (`origin/<base>..HEAD`, worktrees) | modern git; worktree support | 2.50.1 · 2026-07 |
| coreutils (`mktemp`, `cp`) | `codex-run.sh` hermetic home; `codex-helm.sh` managed home | BSD or GNU | 2026-07 |

## Host agent CLIs

| CLI | Role | Required capability | Version owner |
| --- | --- | --- | --- |
| Claude Code | primary host and `agent-launch` backend; native global/project loading remains native | `--model`; effort `low/medium/high/xhigh/max`; `--agents`; per-call `--append-system-prompt`; `--session-id` and `--resume`; `--mcp-config`; `--plugin-dir`; permission modes `acceptEdits/auto/bypassPermissions/manual/dontAsk/plan`. Default-off `--corpus-native` validates and supplies per-item plugin roots for installed corpus carriers; automatic SessionStart execution is observed. Authenticated corpus-agent execution and post-fix authenticated resume remain unverified | Environment Binding; installed CLI 2.1.263 checked 2026-09-08 |
| Codex CLI | mirror host and worker/reviewer runtime; native global/project loading remains native | private corpus composition preserves cwd-aware effective developer instructions, injects the selected snapshot per call, and pins the host id after `thread/start` + `thread/inject_items` + `thread/read`; see codex row above | Environment Binding + this file |

Optional user-global instruction exclusion in `compose/corpus_session.py` requires
Claude Code 2.1.263 or newer. Its native `claudeMdExcludes` setting is supplied once
through `--settings`; native configuration arrays union/deduplicate, but repeated
CLI `--settings` options replace one another, so the adapter refuses that collision.
Actual include/exclude/resume startup preserved project instruction sources and
omitted the global root/imports/user rules on 2026-09-08. Codex 0.153.4 has no
equivalent supported native control; exclusion is refused without changing its
execution sandbox or configuration home.

Claude Haiku 4.5 calls omit `--effort` and the native agent `effort` field.
The SWEEP-main route requires `--restricted`, `--tools`, `--strict-mcp-config`
and `--mcp-config`; installed Claude Code 2.1.263 accepts these parser options.
Its projection uses Read/Glob/Grep and an empty MCP configuration, with no child
delegation. This is a parser/projection check, not a new model-generation receipt.

## LLM models & providers — owned by `Environment Binding`

Concrete role-slot→model bindings live only in each guide's `Environment Binding`, dated, expiring ~8 weeks or on a newer model. Not restated here.

- Providers: **Anthropic** (Claude — Fable/Opus/Sonnet/Haiku), **OpenAI** (GPT / Codex).
- Auth: Anthropic via Claude Code login; OpenAI via ChatGPT subscription or API key (`$CODEX_HOME/auth.json`).

## Private corpus assets

- **Native corpus hooks** — `--corpus-native` uses one shared installed Python carrier and typed event/matcher on both hosts. Claude Code 2.1.268 validates per-item plugins and receives them by `--plugin-dir`; Codex CLI 0.153.4 receives inline session hook config and exposes it through `hooks/list`. Existing native hooks remain, global config is unchanged, and Codex's native enablement/trust review still applies. The installed Codex runtime has a local-transport positive/negative test for execution and context injection; discovery alone is not execution.
- **Claude native corpus agents** — selected agent carriers use the same per-item plugin packaging and retain their authored frontmatter, including tool restrictions. Routes are plugin-qualified rather than launcher tier names. A Codex agent projection is separate work on agent semantics, not a hook restriction.
- **Codex custom agents** (`codex/agents/*.toml`) — role-template sources stored in the immutable private release. The default installer does not register templates in the native host home.
- **Corpus management bootstrap** (`compose/bootstrap/SKILL.md`) — copied into every activated immutable snapshot and named by exact private path in startup text. This is private procedure access, not a claim of native skill registration.

## Referenced / optional — not required by the core repo

- **Slide-writing static HTML/PDF companion** — the primary slide-writing guide needs no renderer. Its explicit static HTML/PDF job path uses Python 3.11+ standard libraries for preparation, binding checks, and result acceptance. Rendering additionally requires an explicit Node executable, Playwright module file, `pdf-lib` resolvable beside that module, and a Chromium-family browser executable. These are job-side dependencies, not installed by corpus delivery. Verified on 2026-09-09: Node 24.19.0, Playwright 1.62.1, pdf-lib 1.17.1, Chromium-family browser 152.0.7977.83. The companion runbook owns invocation and supported-format limits.

- **Deep review** — no separate tool on either side. The Codex-seat deep reviewer (`codex-exec`) is the `codex` CLI's own non-interactive exec mode: `codex exec -s read-only -m gpt-5.6-sol -c model_reasoning_effort="ultra"`, self-contained packet on stdin (`-s read-only`, `-c model_reasoning_effort` and `-c service_tier` verified against installed codex-cli 0.146.0; `-c service_tier="fast"` is the explicit faster, shallower opt-in; `-s read-only` enforces the promised sandbox — ambient `~/.codex` config stays inherited, so the route is read-only but not hermetic). The Claude-seat deep reviewer (**ultracode**) is the `claude` backend itself run headless with the keyword `ultracode` in the prompt — that keyword is what opens the Workflow tool for the turn (`workflowKeywordTriggerEnabled`, default true, read in the installed 2.1.220 bundle). Personal or third-party reviewers register in the user-owned `review-methods.local.toml`, never in the shipped config.
- **Cross-family review reviewers** — with `review_family=cross` (default), each main routes review to the opposite family. A Claude main dispatches gpt review via `$CODEX_HOME/bin/codex-run --profile hermetic` (and `codex-helm --mode review` for review fan-out) plus the deep `codex exec` pass above; a Codex main dispatches Claude review via the `claude` CLI (`claude -p --permission-mode plan` for native, and, for the workflow-orchestration route, the same `claude` CLI headless with the keyword `ultracode` in the prompt — the keyword trigger is what the injected contract names, so this is the mechanism to follow). The reviewer command, resolved path, and opposite-family tier bindings are named in the launch contract; an absent or unauthenticated route degrades to same-family native (PROPOSED). `review_family=same` restores same-family review.
- **codex-plugin-cc** (1.0.6; re-evaluated 2026-07-16) — spawns `codex app-server` with inherited env and no `--ignore-user-config`/`--profile`, so every run reads the real `~/.codex` (config.toml, auth, its MCP servers); it has no per-invocation hermetic reach, which is what makes it unfit as a **review** route: the reviewer would inherit the same config and AGENTS.md as the main, undercutting the independent lens `review_family=cross` exists to provide. The model *is* selectable (`--model`/`--effort`); what is dated is the bundled `gpt-5-4-prompting` skill, so passing a current model does not resolve it. **Not adopted**; `wrappers/codex-run.sh` is preferred for controlled reach. It does not touch Claude Code's `/code-review` (no `code-review.md`; it adds namespaced `/codex:*`), so it never made that route cross-family. Capability we lack and may still want independently: its opt-in `Stop` hook review gate.
- **MCP servers** (clickhouse, node_repl, …) — environment-specific; referenced by Environment Binding, not a core dependency. The launcher registers a stdio MCP server only for a user-registered capability whose offer declares the `mcp-stdio-v1` adapter; no shipped review method is MCP-backed.
- **spreadsheet-processing** (skill) — referenced by the always-surface spreadsheet rule in an activated selection; present in the author's Claude Code and Codex environments. If absent, the rule's inline fallback (plain tools/code + real Excel-engine validation) applies.

## Untracked — dependencies, but excluded by design

Host `config.toml`, `settings.json`, and `hooks.json` — machine-specific trust lists, hook paths, and MCP secrets. The tracked `launch/agent-launch.toml` contains launch bindings but no secrets. See README Scope.

## Re-verify

```bash
codex --version
codex_help="$(codex exec --help)"
for flag in --output-schema --ignore-user-config --ephemeral --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox --cd --sandbox --model --profile; do
  printf '%s\n' "$codex_help" | grep -q -- "$flag" || { echo "missing codex flag: $flag"; exit 1; }
done
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-c([,[:space:]]|$)' || { echo "missing codex flag: -c"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-C([,[:space:]]|$)' || { echo "missing codex flag: -C"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-p([,[:space:]]|$)' || { echo "missing codex flag: -p"; exit 1; }
printf '%s\n' "$codex_help" | grep -Eq '(^|[[:space:]])-s([,[:space:]]|$)' || { echo "missing codex flag: -s"; exit 1; }
claude --version; claude --help | grep -E -- '--model|--effort|--agents|--append-system-prompt|--session-id|--resume|--mcp-config'
bash --version | head -1; zsh --version; python3 --version; git --version
AGENT_LAUNCH_VENV="${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}" bash launch/provision-venv.sh
"${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}/bin/python" -c 'import textual, sys; print("textual", textual.__version__, "py", sys.version.split()[0])'
python3 -m py_compile compose/corpus.py compose/corpus_catalog.py compose/corpus_install.py compose/corpus_session.py compose/corpus_store.py
"${AGENT_LAUNCH_VENV:-$HOME/.local/share/agent-launch/venv}/bin/python" -m unittest discover -s compose -p 'test_corpus*.py'
bash -n wrappers/codex-run.sh wrappers/codex-helm.sh gates/check-parity.sh launch/check-prompting-targets.sh launch/provision-venv.sh install.sh
zsh -n launch/agent-launch.zsh
python3 -c 'compile(open("launch/agent-launch.py").read(), "launch/agent-launch.py", "exec")'
./gates/check-parity.sh
./launch/check-prompting-targets.sh
python3 - <<'PY'
import pathlib, tomllib
roots = [pathlib.Path("codex/agents")]
required = {"frontier.toml", "workhorse.toml", "sweep.toml", "reviewer.toml"}
for root in roots:
    missing = required - {path.name for path in root.glob("*.toml")}
    assert not missing, f"missing required agent TOML files in {root}: {sorted(missing)}"
    for path in sorted(root.glob("*.toml")):
        tomllib.loads(path.read_text())
    print(f"agent TOML ok: {root}")
PY
wrappers/codex-helm.sh --dry-run --mode review "probe"
agent-bios verify
agent-bios corpus status --json
```

## Ownership

| Owner | Owns |
| --- | --- |
| this file (`DEPENDENCIES.md`) | script runtime tools + required capabilities; the dependency inventory |
| each guide `Environment Binding` | role-slot→model bindings, host-CLI verified versions |
| each guide `Evidence Base` | numeric defaults / measurements |
