

===== FILE NVIDIA-NeMo/Gym::CLAUDE.md | stars=1066 followers=None lang=Python bytes=8267 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

NeMo Gym is a library for evaluating and improving models and agents using environments. It provides infrastructure to develop environments, scalably run evaluation and training, and a collection of popular benchmarks and training environments. All components are composable and modular — bring your own agent, model, or environment and integrate with Gym where you need it.

An environment is the complete system an agent interacts with to complete a task. It consists of a dataset (tasks to solve), an agent harness (how the model interacts with the world), a verifier (task completion scoring), and state (per-task execution context).

## Architecture

Environments decompose into four concepts:

| Concept | NeMo Gym Component |
|---------|-------------------|
| Dataset | JSONL: one row per task |
| Agent Harness | FastAPI Agent Server (`responses_api_agents/`) |
| Verifier + State | FastAPI Resources Server (`resources_servers/`) |
| Model | FastAPI Model Server (`responses_api_models/`) or your own |

Base class hierarchy:
```
BaseServer (Pydantic model with config + server_client)
└── SimpleServer (FastAPI app setup, middleware stack)
    ├── SimpleResourcesServer  →  implement verify()
    ├── SimpleResponsesAPIModel  →  implement chat_completions(), responses()
    └── SimpleResponsesAPIAgent  →  implement responses(), run()
```

For full architecture and concepts (environments, training approaches, verification), see `fern/versions/latest/pages/about/`.

## Creating Environments

The typical workflow is to create your own environments tailored to your evaluation or training task. An environment consists of:

1. **Dataset** — JSONL with one task per row. NeMo Gym uses the OpenAI Responses API as its native format because it natively represents multi-turn, tool-calling agentic trajectories without custom serialization. Each row has `responses_create_params.input` (the input messages in Responses API format) and `verifier_metadata` (task-specific data passed to the verifier)
2. **Resources Server** — implements verification logic, environment-specific tools, and per-task state isolation
3. **Agent Harness** — reuse a built-in agent harness (e.g. OpenHands) or bring your own
4. **Model** — use any LLM endpoint via the Model Server (supports inference providers like OpenAI, and vLLM for local/open models), or manage inference in your own agent harness
5. **YAML config** — wires the resources server, agent, and model server together

For guidance on how to build environments, see `fern/versions/latest/pages/environment-tutorials/`. For evaluation, see `fern/versions/latest/pages/get-started/quickstart.mdx`. For training framework integrations, see `fern/versions/latest/pages/training-tutorials/`.

## Environment Design Recommendations

- **Use NeMo Gym's Model Server for inference** — standardizes different model providers behind a common format and manages token IDs needed for training.
- **Hydra YAML for configuration** — pass configuration through Gym's Hydra config system so it's composable and reproducible across runs.
- **Graceful error handling** — environments must handle tool failures and bad model outputs with meaningful error responses, not crash the server.
- **Async endpoints** — the `/run` endpoint must be async. Use `asyncio.Semaphore` for concurrency control if shelling out to external processes.
- **Test skip guards** — tests should skip gracefully if external tools aren't installed (e.g. `pytest.mark.skipif(shutil.which("tool") is None, ...)`).

## Communication & Async Patterns

Servers communicate via `ServerClient`, which wraps aiohttp with retry logic (3 tries, exponential backoff) and connection pooling via a singleton aiohttp client.

- **Use aiohttp, not httpx, for async HTTP.** All async HTTP calls must go through NeMo Gym's global aiohttp client (`nemo_gym.server_utils.request()`). Do not use `httpx.AsyncClient` — httpx/httpcore has O(n^2) connection pooling that causes hangs at high concurrency (16k+ requests). When wrapping external libraries that use httpx internally, replace their HTTP transport with an aiohttp adapter. See `resources_servers/tavily_search/app.py` (`TavilySearchAIOHTTPClient`) for the adapter pattern.
- **Propagate session cookies** through all downstream calls (`cookies=request.cookies`) for stateful environments.
- Use `asyncio.Semaphore` to bound concurrent subprocess/external calls
- For Ray remote tasks in async code: `result = await future` (Ray futures are directly awaitable). Never call `ray.get()` directly in async context.
- Decode all subprocess output with `errors="replace"` to handle non-UTF8
- Guard optional nested fields: `(body.field or {}).get("key", default)`

## External Tool Auto-Install

When an environment requires an external tool (compiler, runtime, etc.), auto-install it on server startup so users don't need manual setup:

1. Create a `setup_<tool>.py` module with an `ensure_<tool>()` function that:
   - Checks `shutil.which("tool")` — returns early if already on PATH
   - Forks on `sys.platform`: macOS (brew), Linux (build from source via bash script)
   - Updates `os.environ["PATH"]` and `os.environ["LD_LIBRARY_PATH"]` for the current process
   - Verifies the tool runs successfully after install
2. Call `ensure_<tool>()` in the server's `model_post_init()` (runs once at startup)
3. For tests: add a `pytest_configure` hook in `conftest.py` that calls `ensure_<tool>()` before collection, so `skipif(shutil.which("tool") is None)` markers see the installed tool
4. Build-from-source scripts should be idempotent (skip if artifacts exist) and install into a local prefix (e.g. `.<tool_name>/` in the server dir, gitignored)

## Common Commands for Building & Testing Environments

```bash
# Setup
uv venv && uv sync --extra dev --group docs
pre-commit install

# Run servers
gym env start \
    --resources-server example_single_tool_call \
    --model-type vllm_model

# Run tests for a specific server (creates .venv per server, installs deps, runs pytest)
# First run is slow. Use skip_venv_if_present config or place a .venv to skip venv creation.
gym env test --resources-server example_single_tool_call

# Run all server tests
gym env test

# Run core library unit tests
pytest tests/unit_tests/ -x

# Run a single test file
pytest tests/unit_tests/test_openai_utils.py -x

# Lint and format
ruff check --fix .
ruff format .

# Pre-commit (runs ruff, formatting, custom hooks)
pre-commit run --all-files

# Check server health
gym env status

# Dev test (runs the core unit tests with coverage: pytest --cov)
gym dev test

# Dump merged config
gym env resolve --config ...
```

## Code Style

- Line length: 119
- Python 3.12+, async-first
- Ruff for linting and formatting (double quotes, isort)
- Test coverage must be >= 96%
- All commits require DCO sign-off (`-s`) and cryptographic signature (`-S`)

## Pre-commit Hooks

Notable custom hooks that auto-modify files:
- `add-verified-flag`: Adds `verified: false` to new resources server YAML configs (`verified: true` means the benchmark has been baselined and reviewed; new servers start as `false`)
- `update-readme-table`: Updates the resources server table in root README.md
- `ruff-format`: Auto-formats code

First run may fail as hooks modify files. Stage the changes and commit again.

To avoid committing unrelated auto-fixes from other servers, scope pre-commit to your files:
```bash
pre-commit run --files resources_servers/my_benchmark/**/*
```
If hooks modify files in other directories, discard those changes:
```bash
git checkout -- resources_servers/other_server/
```

## Cluster / HPC Gotchas

- **Ray socket path length**: On systems with long working directory paths (e.g. Lustre mounts), Ray's AF_UNIX socket paths can exceed the 107-byte Linux limit. Fix: `RAY_TMPDIR=/tmp` before running tests or `ray.init()`.
- **`gym env test` venv isolation**: `gym env test` creates isolated venvs per resources server. `os.environ` changes in Python don't propagate — set env vars externally (e.g. `RAY_TMPDIR=/tmp gym env test ...`).


===== FILE TencentCloudBase/CloudBase-AI-Toolkit::AGENTS.md | stars=1066 followers=None lang=TypeScript bytes=14356 =====

---
alwaysApply: true
---

<workflow>
1. 每当我输入新的需求的时候，为了规范需求质量和验收标准，你首先会搞清楚问题和需求
2. 需求评估：先根据需求大小、影响范围、复杂度和风险判断是否需要走完整 spec 流程。对于跨模块、中大型、高风险、涉及较多协作或验收边界不清晰的需求，必须先补齐 spec；对于小型、低风险、边界清晰的改动，不强制要求产出 spec，但仍需先明确目标、范围和验收标准。
3. 需求文档和验收标准设计：如果判断需要 spec，则先完成需求设计，按照 EARS 简易需求语法方法来描述，保存在 `specs/spec_name/requirements.md` 中，跟我进行确认，最终确认清楚后，需求定稿，参考格式如下

```markdown
# 需求文档

## 介绍

需求描述

## 需求

### 需求 1 - 需求名称

**用户故事：** 用户故事内容

#### 验收标准

1. 采用 ERAS 描述的子句 While <可选前置条件>, when <可选触发器>, the <系统名称> shall <系统响应>，例如 When 选择"静音"时，笔记本电脑应当抑制所有音频输出。
2. ...
...
```
4. 技术方案设计：对于需要 spec 的需求，在完成需求设计之后，你会根据当前的技术架构和前面确认好的需求，进行技术方案设计，保存在 `specs/spec_name/design.md` 中，精简但是能够准确描述技术架构（例如架构、技术栈、技术选型、数据库/接口设计、测试策略、安全性），必要时可以用 mermaid 来绘图，跟我确认清楚后，才进入下阶段。对于不需要 spec 的小需求，可以直接在对话中给出精简方案并继续执行。
5. 任务拆分：对于需要 spec 的需求，在完成技术方案设计后，你会根据需求文档和技术方案，细化具体要做的事情，保存在 `specs/spec_name/tasks.md` 中，跟我确认清楚后，才开始正式执行任务，同时更新任务状态。对于不需要 spec 的小需求，可以直接给出精简任务说明或直接执行。

格式如下

``` markdown
# 实施计划

- [ ] 1. 任务信息
  - 具体要做的事情
  - ...
  - _需求: 相关的需求点的编号

```
</workflow>


<project_rules>
1. 项目结构
   - doc 存放对外的文档
   - mcp 核心的 mcp package
   - config 用来给 AI IDE 提供的规则和 mcp 预设配置
   - tests 自动化测试
   - skills 项目级 skills 源目录
   - specs 需求/设计/任务文档

2. AGENTS 文件约定
   - `AGENTS.md` 为项目及子目录的唯一可信源
   - `CLAUDE.md`、`CODEBUDDY.md` 均为指向 `AGENTS.md` 的软链
   - 新增子目录时，只需创建 `AGENTS.md`，用软链补齐 `CLAUDE.md`

3. Skills & Rules 目录约定
   - `.agents/skills` 为 skills 的唯一可信源，`.codebuddy/skills`、`.claude/skills` 软链至此
   - `.agents/rules` 为 rules 的唯一可信源（尚未创建时以 `.agents/rules` 为目标）
   - 新增 skills 请直接添加到 `skills/` 目录，`.agents/skills/` 下的软链会自动关联
   - 如果使用 `npx skills` 命令添加 skills 时保留 `Universal` 选项，不用重复添加 `claude` 和 `codebuddy` 选项
   - 某个目录中只要有 `AGENTS.md`、`CLAUDE.md` 和 `.agents/skills`、`.claude/skills` 中的任意一个，就需要自动补齐

4. 项目子目录规则
   - `mcp/` 子目录同样适用本约定：`mcp/AGENTS.md` 为源，`mcp/CLAUDE.md`、`mcp/CODEBUDDY.md` 为软链
</project_rules>

<attribution_evaluation_guardrails>
当任务来源于 failing eval、attribution issue、grader、benchmark、trace、result artifact 或其他评测证据时，必须额外遵守以下规则：
1. 评测证据只用于定位问题，不等于产品公开契约；先判断是否存在真实用户可见的产品缺陷，再决定是否修改产品代码。
2. 不要为了通过评测而新增 benchmark-only / grader-only 的兼容分支、提示词、注释、文案或行为。
3. 不要新增同一语义字段的多套命名变体（例如大小写/下划线别名）来"兼容评测"，除非该别名已经是文档化的公开契约。
4. 不要在代码、注释、文档、提交说明或 PR 描述中泄漏内部评测文件名或上下文路径（例如 `run-result.json`、`run-trace.json`、`evaluation-trace.json`、`.codebuddy/attribution-context`）；如必须提及，统一改写为"internal evaluation evidence"。
5. 如果证据更像 grader / task contract 问题、仓库路由错误、或外部系统限制，而不是当前仓库里的真实产品缺陷，应停止产品表面改动，并在总结里明确说明原因与后续建议。
6. 提交前必须自查 staged diff：确认没有评测专用措辞、没有内部 artifact 泄漏、没有为同一字段临时补多个别名。
</attribution_evaluation_guardrails>

<cloud_api_backend_rules>
1. 如果需求涉及通过调用腾讯云 API 来实现后端功能，开始设计或编码前必须先查阅相关文档：
   - 云 API 文档：https://cloud.tencent.com/document/product/876/34809
   - 依赖 API 文档：https://cloud.tencent.com/document/product/876/34808
2. 同时必须检查 CloudBase Manager SDK 文档：https://docs.cloudbase.net/api-reference/manager/node/introduction
3. 如果 Manager SDK 有对应方法，优先使用 Manager SDK；只有在 SDK 没有对应能力或无法满足需求时，才直接调用腾讯云 API。
4. 在实现前，需要根据文档确认接口能力、参数、鉴权方式、返回结构和限制条件，避免凭记忆实现。
</cloud_api_backend_rules>

<mcp_tool_schema_rules>
1. 当新增或修改 MCP 工具入参 schema 时，如果某个字符串字段在 description 中描述了固定可选值、取值范围、模式枚举或协议类型（例如 `MYSQL/FLEXDB`、`on/off`、`blacklist/whitelist`、`OAUTH/OIDC/EMAIL`），必须在 Zod / JSON Schema 中定义为 `z.enum([...])` 或等价枚举 schema，而不是只用 `z.string()` 加说明文字。
2. 仅当字段确实是用户自定义标识、路径、命令、搜索关键词、动态模板名或后端返回的开放值时，才保留 `z.string()`；不要把"例如"中的示例值误收窄成枚举。
3. 枚举值必须来自公开文档、Manager SDK 类型/文档、已有公开契约或当前代码中已稳定使用的常量；如果契约不清楚，先保留开放类型并在总结中说明，不要凭直觉收窄。
4. 修改枚举入参后必须同步补充或更新 schema 测试，并更新生成产物（如 `scripts/tools.json`、`doc/mcp-tools.md`）。
5. 提交前应扫描生成后的工具 schema，确认不存在"description 里列固定取值，但 schema 没有 enum"的字段。
</mcp_tool_schema_rules>

<add_aiide>
# CloudBase AI Toolkit - 新增 AI IDE 支持工作流

1. 在 `config/source/editor-config/` 中补充该 IDE 所需的机器配置文件或兼容说明文件
2. 如需新增 rules / instructions 兼容产物，更新 `scripts/build-compat-config.mjs` 的生成目标
3. 更新 `mcp/src/tools/setup.ts` 中该 IDE 的文件映射和描述
4. 如新增 skill 级兼容要求，确认是否需要保留到 `config/.claude/skills/` 镜像
5. 创建 `doc/ide-setup/{ide-name}.md` 配置文档
6. 更新 `README.md`、`doc/index.md`、`doc/faq.md` 中的 AI IDE 支持列表，README 中注意 detail 中的内容也要填写
7. **更新 IDE 文件映射**：
   - 在 `mcp/src/tools/setup.ts` 的 `ALL_IDE_FILES` 数组中添加新 IDE 的配置文件路径
   - 在 `IDE_FILE_MAPPINGS` 对象中添加新 IDE 的文件映射关系
   - 在 `IDE_DESCRIPTIONS` 对象中添加新 IDE 的描述
   - 在 `IDE_TYPES` 数组中添加新 IDE 的类型
8. 执行 `node scripts/build-compat-config.mjs` 验证兼容产物生成
9. 如需本地检查 Claude skills 镜像，执行 `node scripts/sync-claude-skills-mirror.mjs --check`
10. 执行 `node scripts/diff-compat-config.mjs` 验证外部兼容面无回退
11. 测试 IDE 特定下载功能是否正常工作
</add_aiide>

<add_example>
# CloudBase AI Toolkit - 新增用户案例/视频/文章工作流
0. 注意标题尽量用原标题，然后适当增加一些描述
1. 更新 README.md
2. 更新 doc/tutorials.md

例如 艺术展览预约系统 - 一个完全通过 AI 编程开发的艺术展览预约系统，包含预约功能、管理后台等功能。
</add_example>

<sync_doc>
cp -r doc/* {cloudbase-docs dir}/docs/ai/cloudbase-ai-toolkit/
</sync_doc>


<fix_config_hardlinks>
兼容文件不再通过硬链接维护。
日常维护时，直接修改 `config/source/skills/`、`config/source/guideline/`、`config/source/editor-config/` 并提交即可。
`config/.claude/skills/` 是从 `config/source/skills/` 自动同步的兼容镜像，不要手改。
兼容产物的生成和对外发布主要由 CI / workflow 负责，不需要像以前一样手动跑同步脚本。
只有在需要本地验证或手动同步外部模板仓库时，才执行：
1. `node scripts/sync-claude-skills-mirror.mjs`
2. `node scripts/build-compat-config.mjs`
3. `node scripts/sync-config.mjs`
</fix_config_hardlinks>

<git_push>
1. 提交代码注意 commit 采用 conventional-changelog 风格，在 `feat(xxx):` 后面加一个 emoji，提交信息使用英文描述。
2. 提交代码不要直接推到 `main`，使用 feature 分支，并且默认只推送 GitHub 远端，不要执行 `cnb` 推送，也不要使用 `--force`：
   - `git push origin HEAD`
3. 然后自动创建 PR。
4. 创建 PR 后先等待几分钟，再检查 review 评论和 CI；如果有可执行的问题，继续在同一分支修复并更新 PR。
5. **每次推送代码到 PR 分支后，必须立即检查 PR 状态**：包括是否有冲突（`This branch has conflicts that must be resolved`）、CI 是否通过、机器人评论是否已解决。不要假设推送后万事大吉，冲突和 CI 失败往往只在远程才暴露。
6. **CI 主动监控（强制）**：git push 后必须主动监控 CI Pipeline，不能等用户提醒。使用 `gh pr view --json statusCheckRollup` 等待 CI 完成；如果 CI 失败，自动分析日志并修复；CI 全绿后主动告知用户。
</git_push>

<skills_and_rules_maintenance>
对外暴露的 skills 和规则文件采用「单一语义源 + 自动生成兼容层」的方式维护，具体约定如下：

1. skills 源（对外 Skill 能力定义）
   - 修改 / 新增任何对外 Skill 时，只编辑 `config/source/skills/` 目录下的模块化 `SKILL.md`
   - 如果需要拆模块，可以按功能拆分子目录，例如 `config/source/skills/database/`、`config/source/skills/web/`

2. guideline / rules 总入口
   - 所有对外公开阅读的总入口规则（如 CloudBase 总指南）统一维护在 `config/source/guideline/` 下
   - 例如 CloudBase 主入口为 `config/source/guideline/cloudbase/SKILL.md`

3. IDE / MCP 机器配置
   - 与 IDE / 插件 / MCP 相关的机器配置放在 `config/source/editor-config/`
   - 新增 IDE 或修改 IDE 行为时，只需要更新这里和 `mcp/src/tools/setup.ts` 中的映射

4. 兼容镜像与生成产物（禁止直接修改）
   - `config/.claude/skills/`：从 `config/source/skills/` 自动同步的 Claude skills 兼容镜像，不要手动编辑
   - `.generated/compat-config/`：各 IDE / 外部模板使用的兼容配置生成目录，不要手动编辑
   - `.skills-repo-output/`：对外 skills 仓库发布产物目录，不要手动编辑

5. 本地验证与对外发布
   - 日常只需要修改 `config/source/skills/`、`config/source/guideline/`、`config/source/editor-config/`，其余交给 CI
   - 如果 Skill 变更会影响对外公开的 prompts 文档（例如修改 `config/source/skills/cloudbase-platform/SKILL.md` 需要同步更新 `doc/prompts/cloudbase-platform.mdx`），在提交前必须本地运行：
     - `node scripts/generate-prompts-data.mjs && node scripts/generate-prompts.mjs`
   - 只有在需要本地验证兼容面或同步外部模板仓库时，才运行：
     - `node scripts/sync-claude-skills-mirror.mjs`
     - `node scripts/build-compat-config.mjs`
     - `node scripts/diff-compat-config.mjs`
     - `node scripts/sync-config.mjs`
</skills_and_rules_maintenance>

<doc_freshness_rules>
插件系统与接入说明相关文档的维护遵循以下规则：

1. 插件清单单一真源
   - `mcp/src/server.ts` 中的 `DEFAULT_PLUGINS`、`AVAILABLE_PLUGINS`、`PLUGIN_ALIASES` 是插件名、默认启用集合与兼容别名的唯一真源
   - 修改插件名、默认集合或别名时，必须同步检查 `doc/connection-modes.mdx`、`README.md`、`mcp/README.md`

2. URL 参数与环境变量成对校验
   - 同一能力如果同时暴露环境变量与 URL 参数（例如 `CLOUDBASE_MCP_PLUGINS_ENABLED` / `CLOUDBASE_MCP_PLUGINS_DISABLED` 与 `enable_plugins` / `disable_plugins`），标题、说明、示例和多值格式必须保持一致
   - 多值默认统一使用逗号分隔，不要再写重复 query key 的示例

3. canonical 名称与文档链接校验
   - 文档中的插件 canonical 名必须能在 `AVAILABLE_PLUGINS` 中解析；旧名称只允许出现在"兼容别名"说明中，不应继续作为主名称书写
   - 文档链接必须指向真实存在的仓库文件或站点路由；涉及工具数量时，优先使用不易过期的描述，避免写死数字
</doc_freshness_rules>

<supply_chain_security>
# npm 供应链安全（必须遵守）

本项目因 MCP Server + 大规模 AI IDE 技能分发特性，是 npm 供应链攻击的高价值目标。

**强制规则：**
- 安全敏感依赖（`@cloudbase/*`、`@modelcontextprotocol/sdk`、express、ws、zod 等 runtime 核心）**必须使用精确版本**（禁止 `^` / `~`）。
- 所有 GitHub Actions 引用**必须 pin 到完整 40 字符 commit SHA**（禁止浮动 tag 如 `@v4`、`@beta`）。
- 修改 `package.json`、`pnpm-workspace.yaml`、`.npmrc` 或 workflow 时，必须参考内部详细指南。
- 优先使用 `corepack + pnpm` 进行依赖管理（已配置 `packageManager` 字段）。

**详细内部文档（含当前状态、AI Agent 审计 Prompt、防护措施）：**
`specs/npm-supply-chain-security-hardening/npm-security.md`

任何涉及依赖或 CI 的变更，在开始前都应先阅读该文档。
</supply_chain_security>


===== FILE hookdeck/outpost::docs/AGENTS.md | stars=1027 followers=None lang=Go bytes=1229 =====

# Outpost Documentation Agent Guide

How to contribute to the docs in this folder now lives as a repo-local **Agent Skill**:
[`.agents/skills/hookdeck-outpost-docs-format/SKILL.md`](../.agents/skills/hookdeck-outpost-docs-format/SKILL.md).

It covers everything that used to be in this file — directory map, frontmatter, the
managed-vs-self-hosted tab pattern, template variables, Markdoc components, navigation and
redirects, the contribution workflow and review checklist — plus the voice rules Outpost
docs follow. The skill is self-contained: no external dependencies.

## Loading the skill

- **Cursor, Codex, and other agents** load `.agents/skills/` automatically — nothing to do.
- **Claude Code:** from the repo root, run `npx skills add . --skill hookdeck-outpost-docs-format`
  and choose **symlink** at the prompt (see [vercel-labs/skills](https://github.com/vercel-labs/skills)).

## Context

- Docs content is authored in this repository under `docs/content`.
- Rendering is done by a separate (private) Astro application that loads docs from `docs/content`.
- Treat `docs/content`, `docs/content/nav.json`, and `docs/content/redirects.json` as the
  source of truth for structure, navigation, and redirects.


===== FILE fluttercommunity/flutter_workmanager::CLAUDE.md | stars=1018 followers=None lang=Dart bytes=3343 =====

## Version Management
- **DO NOT manually edit CHANGELOG.md files** - Melos handles changelog generation automatically
- **Use semantic commit messages** for proper versioning:
  - `fix:` for bug fixes (patch version bump)
  - `feat:` for new features (minor version bump) 
  - `BREAKING CHANGE:` or `!` for breaking changes (major version bump)
  - Example: `fix: prevent iOS build errors with Logger availability`
- Melos will generate changelog entries from commit messages during release

## Pre-Commit Requirements
**CRITICAL**: Always run from project root before ANY commit:
1. `dart analyze` (check for code errors)
2. `ktlint -F .` (format Kotlin code)
3. `swiftlint --fix` (format Swift code)
4. `find . -name "*.dart" ! -name "*.g.dart" ! -path "*/.*" -print0 | xargs -0 dart format --set-exit-if-changed`
5. `flutter test` (all Dart tests)
6. `cd example/android && ./gradlew :workmanager_android:test` (Android native tests)
7. `cd example && flutter build apk --debug` (build Android example app)
8. `cd example && flutter build ios --debug --no-codesign` (build iOS example app)

## Code Generation
- Regenerate Pigeon files: `melos run generate:pigeon`
- Regenerate Dart files (including mocks): `melos run generate:dart`
- Do not manually edit *.g.* files
- Never manually modify mocks or generated files. Always modify the source, then run the generator tasks via melos.

## Running Tests
- Use melos to run all tests: `melos run test`
- Or run tests in individual packages:
  - `cd workmanager_android && flutter test`
  - `cd workmanager_apple && flutter test` 
  - `cd workmanager && flutter test`
- Before running tests in workmanager package, ensure mocks are up-to-date: `melos run generate:dart`

## Test Quality Requirements
- **NEVER create useless tests**: No `assert(true)`, `expect(true, true)`, or compilation-only tests
- **Test real logic**: Exercise actual methods with real inputs and verify meaningful outputs
- **Test edge cases**: null inputs, error conditions, boundary values

## Complex Component Testing
- **BackgroundWorker**: Cannot be unit tested due to Flutter engine dependencies - use integration tests

## Changelog Guidelines
- **User-focused content only**: Write from end user perspective, not internal implementation details
- **No AI agent progress**: Don't document debugging steps, build fixes, or internal development process
- **What matters to users**: Breaking changes, new features, bug fixes that affect their code
- **Example of bad changelog entry**: "Fixed Kotlin null safety issues with androidx.work 2.10.2 type system improvements"
- **Example of good changelog entry**: "Fixed periodic tasks not respecting frequency changes"

## Documentation Components (docs.page)
- **Component reference**: https://use.docs.page/ contains the full reference for available components
- **Tabs component syntax**:
  ```jsx
  <Tabs>
    <TabItem label="Tab Name" value="unique-value">
      Content here
    </TabItem>
  </Tabs>
  ```
- Use `<TabItem>` not `<Tab>` - this is a common mistake that causes JavaScript errors
- Always include both `label` and `value` props on TabItem components

## Pull Request Description Guidelines

Template:
```markdown
## Summary
- Brief change description

Fixes #123

## Breaking Changes (if applicable)
**Before:** `old code`
**After:** `new code`
```

===== FILE hahwul/jwt-hack::AGENTS.md | stars=1013 followers=3014 lang=Rust bytes=9780 =====

# JWT-HACK Development Instructions

JWT-HACK is a high-performance Rust-based JSON Web Token security testing toolkit. It provides JWT encoding, decoding, verification, cracking, and attack payload generation capabilities.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Prerequisites and Setup
- Install Rust and Cargo (latest stable version recommended):
  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  source ~/.cargo/env
  ```
- Install Just task runner:
  ```bash
  cargo install just
  ```

### Build Commands
- **CRITICAL**: Set timeouts to 120+ seconds for all build commands. NEVER CANCEL builds.
- Development build: `just dev` or `cargo build` -- takes 75 seconds on first build with dependencies, 18 seconds on subsequent builds. NEVER CANCEL. Set timeout to 120+ seconds.
- Release build: `just build` or `cargo build --release` -- takes 47 seconds. NEVER CANCEL. Set timeout to 90+ seconds.
- Quick check (no build): `cargo check` -- takes 15 seconds. Good for fast compilation verification.
- Clean build: `cargo clean` followed by build commands.
- Quick recompile after changes: `cargo build` -- takes 3-5 seconds for incremental builds.

### Testing
- Run full test suite: `just test` -- takes 17 seconds. NEVER CANCEL. Set timeout to 60+ seconds.
- This runs: `cargo test`, `cargo clippy`, `cargo fmt --check`, and `cargo doc`
- Unit tests only: `cargo test` -- takes 3-5 seconds.
- Lint only: `cargo clippy -- --deny warnings`
- Format check: `cargo fmt --check`
- Format code: `just fix` or `cargo fmt`

### Benchmarks and Fuzzing
- Run performance benchmarks (criterion): `just bench` or `cargo bench`
  - Covers encode, decode, verify, and cracking (dictionary + brute force).
  - CI tracks results against a baseline via `.github/workflows/benchmarks.yml`.
- Run a fuzz target (requires nightly + `cargo install cargo-fuzz`):
  - `just fuzz jwt_decode` (or `jwe_decode`, `header_parsing`)
  - `cargo +nightly fuzz run <target> -- -max_total_time=60`
  - Fuzz targets live in `fuzz/fuzz_targets/`; scheduled/manual CI is in `.github/workflows/fuzz.yml`.

### Development Tasks
- List available Just commands: `just --list`
- Format and fix linting: `just fix`
- Build documentation: `cargo doc --workspace --all-features --no-deps --document-private-items`

## Validation Scenarios

### CRITICAL: Always run these validation steps after making changes:

1. **Build and Test Validation**:
   ```bash
   just dev && just test
   ```

2. **Core Functionality Testing**:
   ```bash
   # Test decoding (should display header/payload breakdown with algorithm and timestamps)
   ./target/debug/jwt-hack decode eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.5mhBHqs5_DTLdINd9p5m7ZJ6XD0Xc55kIaCRY5r6HRA
   
   # Test encoding (should create valid JWT with spinner animation)
   ./target/debug/jwt-hack encode '{"sub":"1234", "name":"test"}' --secret=mysecret
   
   # Test verification (should show validation result)
   ./target/debug/jwt-hack verify eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.5mhBHqs5_DTLdINd9p5m7ZJ6XD0Xc55kIaCRY5r6HRA --secret=test
   
   # Test dictionary cracking (should process 16 words with progress bar)
   ./target/debug/jwt-hack crack -w samples/wordlist.txt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.CHANGED
   
   # Test brute force cracking (should generate combinations with progress)
   ./target/debug/jwt-hack crack -m brute eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.CHANGED --max=2
   
   # Test payload generation (should create none algorithm attack payloads)
   ./target/debug/jwt-hack payload eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.CHANGED --target none
   
   # Test all payload types (should generate multiple attack vectors)
   ./target/debug/jwt-hack payload eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.CHANGED --jwk-attack example.com
   ```

3. **Help System Validation**:
   ```bash
   # Verify help displays correctly with banner
   ./target/debug/jwt-hack --help
   ./target/debug/jwt-hack decode --help
   ./target/debug/jwt-hack encode --help
   ```

### Pre-commit Validation
Always run these before committing changes or the CI (.github/workflows/ci.yml) will fail:
```bash
cargo fmt
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

## Project Structure

### Key Directories and Files
```
├── src/
│   ├── main.rs              # Application entry point
│   ├── cmd/                 # Command implementations
│   │   ├── decode.rs        # JWT decoding functionality
│   │   ├── encode.rs        # JWT encoding functionality
│   │   ├── verify.rs        # JWT verification functionality
│   │   ├── crack.rs         # JWT cracking (dict/brute force)
│   │   ├── payload.rs       # Attack payload generation
│   │   └── version.rs       # Version display
│   ├── jwt/                 # Core JWT operations
│   ├── crack/               # Cracking algorithms and utilities
│   ├── payload/             # Payload generation logic
│   ├── printing/            # Output formatting and logging
│   └── utils/               # Shared utilities
├── samples/                 # Test data
│   ├── jwt.txt             # Sample JWT token
│   └── wordlist.txt        # Sample wordlist for cracking
├── Cargo.toml              # Rust project configuration
├── justfile                # Task automation scripts
├── Dockerfile              # Container build definition
└── .github/workflows/      # CI/CD pipelines
```

### Configuration Files
- `Cargo.toml`: Dependencies, build configuration, binary definition
- `justfile`: Task automation (build, test, dev, fix commands)
- `.github/workflows/ci.yml`: CI pipeline (builds on Ubuntu/macOS/Windows)

## Common Development Patterns

### Adding New Commands
1. Create new module in `src/cmd/`
2. Add command struct with `clap` derives
3. Implement execute function
4. Add to `src/cmd/mod.rs` and main command enum
5. Add comprehensive unit tests
6. Update help documentation

### Modifying JWT Operations
- Core JWT logic is in `src/jwt/`
- Uses `jsonwebtoken` crate for cryptographic operations
- Always add tests for new algorithms or validation logic
- Test with various JWT formats and edge cases

### Performance Considerations
- Uses `rayon` for parallel processing in cracking operations
- Uses `indicatif` for progress bars on long-running operations
- Built with release optimizations: LTO, single codegen unit, stripped binaries

## Troubleshooting

### Build Issues
- **"cargo command not found"**: Install Rust toolchain with rustup
- **"just command not found"**: Install with `cargo install just`
- **Dependency resolution errors**: Delete `Cargo.lock` and rebuild
- **Compilation errors**: Ensure using latest stable Rust version

### Test Failures
- **Clippy warnings**: Run `cargo clippy --fix --allow-dirty` then manually review changes
- **Format failures**: Run `cargo fmt` to auto-fix formatting
- **Unit test failures**: Check if tests depend on specific sample data in `samples/`

### Runtime Issues
- **JWT parsing errors**: Verify JWT format (header.payload.signature structure)
- **Missing wordlist files**: Use relative paths from project root or absolute paths
- **Performance issues**: Use release build for large-scale operations

### Docker Build (Note: May fail in restricted environments)
```bash
# Docker build may fail due to network restrictions in sandboxed environments
docker build -t jwt-hack .
# If build fails, use local cargo builds instead
```

## CI/CD Information

The project uses GitHub Actions with the following jobs:
- **Build & Test**: Runs on Ubuntu, macOS, Windows with stable Rust
- **Lint**: Runs `cargo fmt --check` and `cargo clippy` with strict warnings
- **Coverage**: Generates code coverage reports using `cargo-llvm-cov`

All CI checks must pass before merging. The pipeline takes approximately 5-10 minutes to complete.

## Quick Reference

### Most Common Commands
```bash
# Development workflow
just dev                    # Build for development (75s first build, 18s subsequent, timeout 120s)
just test                   # Run all tests (17s, timeout 60s)
just fix                    # Format and fix linting

# Manual commands
cargo check                 # Fast compilation check (15s, timeout 30s)
cargo build                 # Development build
cargo build --release      # Production build (47s, timeout 90s)
cargo test                  # Unit tests only
cargo clippy               # Linting
cargo fmt                  # Code formatting

# Application testing
./target/debug/jwt-hack --help                    # Show help with banner
./target/debug/jwt-hack decode TOKEN              # Decode JWT (shows header/payload)
./target/debug/jwt-hack encode JSON --secret=KEY  # Encode JWT (creates new token)
./target/debug/jwt-hack verify TOKEN --secret=KEY # Verify JWT signature
./target/debug/jwt-hack crack -w FILE TOKEN       # Crack JWT with wordlist
./target/debug/jwt-hack crack -m brute TOKEN --max=N  # Brute force crack
./target/debug/jwt-hack payload TOKEN --target=TYPE   # Generate attack payloads
```

### File Patterns to Know
- Test files: `src/**/*test*.rs` or `#[cfg(test)]` modules
- Sample data: `samples/*.txt`
- Build artifacts: `target/` (excluded from git)
- Binary location: `target/debug/jwt-hack` or `target/release/jwt-hack`

===== FILE akitaonrails/ai-jail::CLAUDE.md | stars=970 followers=18999 lang=Rust bytes=7302 =====

# ai-jail — Development Guidelines

## What This Project Is

A Rust CLI tool that wraps bubblewrap (`bwrap`) to sandbox AI coding agents (Claude Code, GPT Codex, OpenCode, Crush). It replaces a bash script with config persistence (`.ai-jail` TOML), proper signal handling, and a developer-friendly CLI.

## Project Structure

```
src/
  main.rs         -- entry point, orchestration, TempFile RAII guard
  cli.rs          -- argument parsing with lexopt
  config.rs       -- .ai-jail TOML config load/save/merge (project + global)
  sandbox/
    mod.rs        -- shared sandbox logic, mount lists, launch wrapper
    bwrap.rs      -- bwrap command builder + mount discovery (Linux)
    landlock.rs   -- Landlock LSM path + network rules (Linux)
    seccomp.rs    -- seccomp-bpf syscall filter (Linux)
    rlimits.rs    -- resource limits (NPROC, NOFILE, CORE)
    seatbelt.rs   -- sandbox-exec SBPL profile generation (macOS)
  pty.rs          -- PTY proxy with vt100 virtual terminal (raw mode, IO loop, diff rendering)
  statusbar.rs    -- persistent terminal status bar overlay (redraw, update check)
  signals.rs      -- signal forwarding + child process reaping
  output.rs       -- colored terminal output helpers (raw ANSI, no deps)
  bootstrap.rs    -- AI tool config generation (Claude, Codex, OpenCode)
```

## Critical Rule: Backward Compatibility

**Every new version MUST work with previously generated `.ai-jail` config files.**

This is the single most important invariant of the project. Users generate `.ai-jail` files in their project directories and expect them to keep working after upgrading the binary.

### Config file rules

- **Never remove a config field.** If a field becomes obsolete, keep deserializing it but ignore its value. Use `#[serde(default)]` on all fields so missing fields get defaults.
- **Never rename a config field.** If a better name is needed, add the new name and keep the old one as an alias (`#[serde(alias = "old_name")]`).
- **Never change a field's type.** A `Vec<String>` must stay a `Vec<String>`. If richer types are needed, add a new field.
- **New fields must have defaults.** Always use `#[serde(default)]` so old config files without the field still parse.
- **Unknown fields must be silently ignored.** Never use `#[serde(deny_unknown_fields)]`. This allows old configs with removed fields to still load.
- When writing config files, only serialize fields that differ from defaults (keeps files clean for users who edit them by hand).

### CLI option rules

- **Never remove a CLI flag.** If a flag becomes obsolete, keep accepting it silently (with an optional deprecation warning to stderr).
- **Never change the meaning of an existing flag.** `--no-gpu` must always mean "disable GPU passthrough".
- **New flags must not break existing invocations.** Defaults for new flags must preserve the prior behavior.
- **Positional command behavior is sacred.** `ai-jail claude` must always mean "run claude inside the sandbox".

### Testing backward compatibility

There are regression tests in `src/config.rs` that parse old config file formats. **When changing config.rs, always add a new regression test with the old format before making changes.** Never delete existing regression tests.

## Coding Conventions

- **No async, no tokio.** This is a synchronous CLI tool.
- **Minimal dependencies.** Current deps: `lexopt`, `serde`, `toml`, `serde_json`, `vt100`, `nix`, `landlock`, `seccompiler` (Linux). Do not add new crates without a strong justification.
- **No clap.** We use `lexopt` for argument parsing to keep the binary small.
- **Raw ANSI for colors.** No color crate — `output.rs` handles this with raw escape codes.
- **Warn and skip, never crash.** Missing paths, unreadable dirs, and non-critical errors produce a warning and continue. Existing `.ai-jail` files that cannot be read or parsed are fatal because silently dropping sandbox policy would fail open. Other fatal errors include no bwrap and an unavailable current directory.
- **Signal safety.** The signal handler (`signals.rs`) must only use async-signal-safe operations. The current handler just calls `libc::kill` on the stored child PID.
- **RAII for cleanup.** Temp files use a `Drop` guard, not manual cleanup.

## Mount Order Matters

The bwrap command mounts are order-dependent. The sequence in `sandbox/bwrap.rs` must be:

1. Base mounts (`/usr`, `/etc`, `/opt`, `/sys`, `/dev`, `/proc`, `/tmp`, `/run`)
2. Sensitive /sys masks (tmpfs over `/sys/firmware`, `/sys/kernel/security`, etc.)
3. GPU devices
4. Docker socket
5. Tailscale socket
6. Shared memory (`/dev/shm`)
7. Display mounts (X11, Wayland, XDG_RUNTIME_DIR)
8. systemd user bus mounts (`--systemd-user`, narrow XDG runtime sockets)
9. Home directory (tmpfs `$HOME` first, then dotfiles on top)
10. Config hide (tmpfs over sensitive `~/.config/*` subdirs)
11. Cache hide (tmpfs over sensitive `~/.cache/*` subdirs)
12. Local overrides (`~/.local/state`, `~/.local/share/*` rw subdirs)
13. Command binary exemption (private-home only: ro-binds of the invoked command's `$HOME` install paths, so `--private-home claude` can exec an agent installed under the home directory)
14. Linked Git worktree metadata
15. SSH agent socket and `~/.ssh` exemption mounts
16. Pictures mount
17. Browser profile state mount
18. Extra user mounts (`--map`, `--rw-map`)
19. Overlay maps (`--overlay-map` — copy-on-write `--overlay-src`/`--overlay`)
20. Project directory (pwd, rw or ro depending on mode)
21. In-project user mounts (`--map`/`--rw-map` paths inside the project dir, after the project bind so it cannot shadow them)
22. In-project overlay maps (`--overlay-map` paths inside the project dir, same shadowing rule)
23. Mask overlays (`--mask` and hidden project `.ai-jail`)
24. Deny overlays (`--deny-path`, mode-000 file/dir placeholders)
25. Overlay storage hide (tmpfs over `<project>/.ai-jail-overlays`, last so it sits on top of the project mount that contains the upper/work layers)

Changing this order can break the sandbox. The tmpfs for `$HOME` must come before the individual dotfile bind mounts. Overlay maps come after the home/dotfile mounts (so an overlay on a home path sits on top). User mounts and overlay maps whose destination sits **inside** the project directory are emitted after the project mount — bwrap gives the later mount precedence, so emitting them earlier lets the project bind silently shadow them (issue #83: `--map .git` stayed writable and in-project overlay writes hit the real files). Mask and deny overlays come after those so they still win. Overlay storage hide comes last, after the project mount, so it masks the upper/work layers the project mount would otherwise expose.

## Before Committing

Always run `cargo fmt` before committing. CI enforces `cargo fmt --check` and will fail on unformatted code. The project uses `max_width = 80` via `rustfmt.toml`.

```
cargo fmt
cargo clippy -- -D warnings
cargo test
```

## Running Tests

```
cargo test
```

Tests are in `#[cfg(test)]` modules at the bottom of each source file. Config tests use `tempfile`-style patterns with `std::env::temp_dir()`.

## Building

```
cargo build --release    # 881K stripped binary
```

Install by copying `target/release/ai-jail` to `~/.local/bin/` or `/usr/local/bin/`.


===== FILE ArisGuimera/MobiAI-Core::CLAUDE.md | stars=427 followers=5226 lang=Go bytes=739 =====

# MobiAI — Mobile Development AI Ecosystem

MobiAI is an AI ecosystem for mobile development: skills, specialized agents, and automated pipelines for Android, iOS, KMP, Flutter, and React Native.

## Bootstrap

The full skill catalog is at `skills/core/skills/using-mobiai/SKILL.md`. It loads automatically on session start and lists all available skills with a decision guide for when to use each one.

## Principles

- **Minimal fixes**: Change only what's necessary. Don't refactor, don't add unrelated improvements.
- **Evidence-based**: Always verify your work compiles and tests pass before declaring success.
- **Platform-native**: Follow each platform's conventions and idioms. Don't apply Android patterns to iOS or vice versa.


===== FILE tangxiaofeng7/cscan::CLAUDE.md | stars=394 followers=1307 lang=Go bytes=28240 =====

# CLAUDE.md

## 一、项目架构

### 1.1 项目概述

**cscan** — 企业级分布式网络资产扫描平台

### 1.2 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端框架 | Go + go-zero 微服务框架 | Go 1.25+ / go-zero v1.7.3 |
| 前端框架 | Vue 3 + Vite + Element Plus | Vue 3.4 / Vite 5 / Element Plus 2.4 |
| 数据库 | MongoDB + Redis | MongoDB 6 / Redis 7 |
| RPC 通信 | gRPC + Protobuf | grpc v1.76 |
| 扫描引擎 | ProjectDiscovery + Nmap/Masscan | nuclei v3.6 / httpx v1.7 / naabu v2.3 / subfinder v2.11 |
| 截图引擎 | Chromedp (Chrome 无头浏览器) | chromedp v0.14 |
| 任务调度 | robfig/cron + Redis Sorted Set | cron/v3 |
| 认证 | JWT (golang-jwt/v4) | jwt/v4 v4.5 |
| 前端状态管理 | Pinia | v2.1 |
| 国际化 | vue-i18n | v11 |
| 图表 | ECharts | v5.4 |
| CSS 预处理 | SCSS (modern-compiler API) | sass v1.97 |
| 测试 (Go) | testify + gopter (属性测试) | testify v1.11 / gopter v0.2 |
| 测试 (前端) | Vitest + happy-dom + fast-check | vitest v4 |

### 1.3 系统架构图

```
[Browser] → [Vue 3 Frontend (web/) :3000]
                  │
            [Vite Proxy /api → :8888]
                  │
           [HTTP API (api/) - go-zero REST :8888]
                  │
      ┌───────────┼────────────┐
      │           │            │
[gRPC RPC     [MongoDB]    [Redis]
 (rpc/) :9000]    │            │
                  │      ┌─────┴──────────┐
                  │  [Sorted Set     [Pub/Sub
                  │   任务队列]     cscan:cron:execute]
                  │      │               │
              [Scheduler (scheduler/)]───┘
                  │
         [Worker nodes (worker/)]  ← 通过 Install Key 认证，WebSocket 长连接
                  │
         [Scanner modules (scanner/)]
                  │
    ┌─────┬──────┼──────┬────────┬──────┐
  Naabu  Nmap  Httpx  Subfinder Nuclei Chromedp
```

### 1.4 核心架构模式

- **多租户隔离**: 所有数据按 `workspace_id` 过滤；MongoDB 集合命名 `{workspaceId}_{entity}`（如 `default_asset`、`ws1_tasks`）
- **任务流**: MainTask → 按目标数量分批 (batchSize=50) → SubTasks → 推入 Redis Sorted Set 队列 → Worker 拉取执行
- **孤儿恢复**: 后台协程每 5 分钟检查 STARTED 状态超过 30 分钟未更新的任务，重置为 PENDING 并重新入队
- **定时调度**: Redis Pub/Sub 频道 `cscan:cron:execute` 触发定时扫描，基于 `robfig/cron/v3`
- **Worker 通信**: Install Key 认证注册 → WebSocket (`/api/v1/worker/ws`) 保持长连接 → 心跳上报 → REST 接口回传结果

---

## 二、项目模块划分

### 2.1 文件与文件夹布局

```
cscan/
├── api/                          # HTTP API 服务（主入口）
│   ├── cscan.go                  # API 服务入口点
│   ├── etc/cscan.yaml            # API 配置（端口8888, JWT, MongoDB, Redis, RPC）
│   └── internal/
│       ├── config/config.go      # 配置结构体定义
│       ├── handler/              # 路由处理器（按资源域分子包）
│       │   ├── routes.go         # 统一路由注册（4 层认证级别）
│       │   ├── asset/            # 资产管理 Handler
│       │   ├── task/             # 任务管理 Handler
│       │   ├── vul/              # 漏洞管理 Handler
│       │   ├── worker/           # Worker 管理 Handler
│       │   ├── fingerprint/      # 指纹管理 Handler
│       │   ├── poc/              # POC 管理 Handler
│       │   ├── onlineapi/        # 在线 API 搜索 Handler
│       │   ├── user/             # 用户管理 Handler
│       │   ├── workspace/        # 工作空间 Handler
│       │   ├── organization/     # 组织管理 Handler
│       │   ├── blacklist/        # 黑名单 Handler
│       │   ├── dirscan/          # 目录扫描 Handler
│       │   ├── subdomain/        # 子域名字典 Handler
│       │   ├── subfinder/        # Subfinder 配置 Handler
│       │   ├── notify/           # 通知配置 Handler
│       │   ├── report/           # 报告 Handler
│       │   └── ai/               # AI POC 生成 Handler
│       ├── logic/                # 业务逻辑层（平铺，{动作}{实体}logic.go）
│       ├── middleware/           # 中间件（JWT/WorkerAuth/ConsoleAuth）
│       ├── svc/                  # 服务上下文（DI 容器 + 服务实现）
│       │   ├── servicecontext.go # ServiceContext 核心结构体
│       │   ├── scanresult_service.go
│       │   ├── history_service.go
│       │   └── sync/             # 同步服务（模板/指纹/POC 同步）
│       └── types/                # 请求/响应类型定义
├── rpc/                          # gRPC 内部服务
│   └── task/
│       ├── task.go               # RPC 服务入口（端口 9000）
│       ├── task.proto            # Protobuf 定义
│       ├── pb/                   # 生成的 pb 代码
│       ├── taskservice/          # 服务实现
│       ├── client/               # 客户端封装
│       └── etc/task.yaml         # RPC 配置
├── model/                        # MongoDB 数据模型（30+ 模型文件）
│   ├── asset.go                  # 资产模型（按 workspace 分集合）
│   ├── task.go                   # 主任务/子任务模型
│   ├── vul.go                    # 漏洞模型
│   ├── user.go                   # 用户模型（全局集合）
│   ├── workspace.go              # 工作空间模型
│   ├── fingerprint.go            # 指纹模型
│   ├── scantemplate.go           # 扫描模板
│   ├── indexes.go                # MongoDB 索引定义
│   ├── base.go                   # 基础类型
│   └── errors.go                 # 模型层错误定义
├── pkg/                          # 共享工具包
│   ├── xerr/                     # 业务错误码体系
│   │   ├── errcode.go            # 错误码常量 + 消息映射
│   │   ├── errors.go             # CodeError 结构体 + 工厂函数
│   │   └── scan_errors.go        # 扫描相关错误
│   ├── response/response.go      # 统一 HTTP 响应封装
│   ├── cache/                    # 缓存工具
│   ├── circuitbreaker/           # 熔断器
│   ├── httpclient/               # HTTP 客户端封装
│   ├── notify/                   # 多渠道通知发送
│   ├── retry/                    # 重试机制
│   ├── risk/                     # 风险等级计算
│   └── utils/                    # 通用工具函数
├── scheduler/                    # 任务调度器（Redis 队列 + Cron）
├── scanner/                      # 扫描模块（Naabu/Nmap/Httpx/Subfinder/Nuclei/Dnsx）
├── worker/                       # 分布式 Worker 进程
├── cmd/
│   └── worker/main.go            # Worker 命令行入口
├── onlineapi/                    # 在线资产搜索（FOFA/Hunter/Quake）
├── screenshot/                   # Web 截图服务（Chromedp）
├── tools/                        # 辅助工具脚本
├── poc/                          # POC 定义文件
├── docker/                       # Docker 配置
│   ├── Dockerfile.api            # API 镜像
│   ├── Dockerfile.rpc            # RPC 镜像
│   ├── Dockerfile.worker         # Worker 镜像
│   ├── mongo-init.js             # MongoDB 初始化脚本
│   └── entrypoint.sh             # 容器启动脚本
├── web/                          # Vue.js 前端
│   ├── src/
│   │   ├── main.js               # 应用入口
│   │   ├── App.vue               # 根组件
│   │   ├── router/index.js       # 路由配置（History 模式 + 懒加载）
│   │   ├── stores/               # Pinia 状态管理
│   │   │   ├── user.js           # 用户信息、token、登录/登出
│   │   │   ├── workspace.js      # 当前工作空间 ID、列表
│   │   │   ├── theme.js          # 主题模式（light/dark/system）
│   │   │   ├── locale.js         # 语言设置
│   │   │   └── onlineSearch.js   # 在线搜索状态
│   │   ├── api/                  # HTTP 请求封装
│   │   │   ├── request.js        # axios 实例（baseURL=/api/v1, 自动注入 Token + WorkspaceId）
│   │   │   └── {domain}.js       # 按业务域分文件（asset/task/worker/poc 等）
│   │   ├── views/                # 页面视图（PascalCase.vue）
│   │   ├── components/           # 可复用组件
│   │   │   └── asset/            # 资产相关子组件
│   │   ├── layouts/MainLayout.vue # 主框架布局
│   │   ├── i18n/                 # 国际化（zh-CN / en-US）
│   │   ├── utils/                # 工具函数
│   │   └── styles/index.css      # 全局样式
│   ├── vite.config.js            # Vite 配置（代理、分包、SCSS）
│   └── package.json
├── docker-compose.yaml           # 生产环境全栈部署
├── docker-compose.dev.yaml       # 本地开发依赖（仅 MongoDB + Redis）
├── docker-compose-worker.yaml    # 独立 Worker 部署
├── .github/workflows/            # CI/CD（Docker 镜像构建推送）
├── go.mod / go.sum               # Go 模块定义
├── VERSION                       # 版本号文件
├── cscan.sh / cscan.bat          # 一键启动脚本
└── README.md / README_EN.md      # 项目文档
```

### 2.2 业务模块清单

| 模块 | 后端 Handler | 前端视图 | 说明 |
|------|-------------|---------|------|
| 资产管理 | `handler/asset/` | `AssetManagement.vue` + `components/asset/` | 端口/站点/域名/IP/截图/历史/标签 |
| 任务管理 | `handler/task/` | `Task.vue`, `TaskCreate.vue`, `CronTask.vue` | 创建/分批/暂停/恢复/停止/重试/定时 |
| 漏洞管理 | `handler/vul/` | `VulnerabilityManagement.vue` | 漏洞列表/详情/统计 |
| Worker 管理 | `handler/worker/` | `Worker.vue`, `WorkerLogs.vue`, `WorkerConsole.vue` | 注册/心跳/WebSocket/日志流/控制台 |
| 指纹管理 | `handler/fingerprint/` | `Fingerprint.vue` | 指纹 CRUD/分类/同步/主动指纹 |
| POC 管理 | `handler/poc/` | `Poc.vue` | 自定义 POC/Nuclei 模板/AI 生成 |
| 在线搜索 | `handler/onlineapi/` | `OnlineSearch.vue` | FOFA/Hunter/Quake API 聚合 |
| 目录扫描 | `handler/dirscan/` | `DirectoryManagement.vue` | 字典管理/扫描结果 |
| 用户管理 | `handler/user/` | `Settings.vue (tab=user)` | CRUD/登录/密码重置 |
| 工作空间 | `handler/workspace/` | `Settings.vue (tab=workspace)` | 工作空间 CRUD |
| 组织管理 | `handler/organization/` | `Settings.vue (tab=organization)` | 组织 CRUD/状态切换 |
| 黑名单 | `handler/blacklist/` | `Blacklist.vue` | 黑名单规则配置 |
| 通知 | `handler/notify/` | Settings 页面内 | 通知配置/主题/高危过滤器 |
| 报告 | `handler/report/` | `Report.vue` | 报告详情/导出 |
| 扫描模板 | `handler/task/` | `ScanTemplate.vue` | 扫描配置模板管理 |

---

## 三、代码风格与规范

### 3.1 Go 命名约定

| 元素 | 规范 | 示例 |
|------|------|------|
| 文件名 | lowercase_underscore | `scanresult_service.go`, `asset_history.go` |
| 包名 | 小写单词 | `model`, `svc`, `handler`, `xerr` |
| 结构体/类型 | PascalCase | `AssetModel`, `ScanResultService`, `CodeError` |
| 导出函数 | PascalCase | `GetAsset()`, `NewAssetModel()` |
| 未导出函数 | camelCase | `parseResult()`, `unauthorized()` |
| 常量 | PascalCase | `ServerError`, `UserNotFound` |
| Context Key | 具名类型 `ContextKey` | `UserIdKey`, `WorkspaceIdKey` |
| Handler 函数 | `{Entity}{Action}Handler` | `AssetListHandler`, `WorkerHeartbeatHandler` |
| Logic 文件 | `{动作}{实体}logic.go` | `loginlogic.go`, `tasklogic.go` |

### 3.2 Vue 前端命名约定

| 元素 | 规范 | 示例 |
|------|------|------|
| 视图页面 | PascalCase.vue | `AssetManagement.vue`, `TaskCreate.vue` |
| 通用组件 | PascalCase.vue | `ScanWorkflow.vue`, `LanguageSwitcher.vue` |
| 内容视图组件 | PascalCase + `View` 后缀 | `SiteView.vue`, `VulView.vue` |
| 标签页组件 | PascalCase + `Tab` 后缀 | `AssetInventoryTab.vue` |
| 布局组件 | PascalCase + `Layout` 后缀 | `MainLayout.vue` |
| API 文件 | camelCase.js | `asset.js`, `crontask.js` |
| Store 文件 | camelCase.js | `workspace.js`, `onlineSearch.js` |
| 工具函数文件 | camelCase.js | `screenshot.js`, `performance.js` |

### 3.3 Import 规则

**Go — 三组空行分隔**：
```go
import (
    // 1. 标准库
    "context"
    "time"

    // 2. 内部包
    "cscan/model"
    "cscan/pkg/xerr"
    "cscan/api/internal/middleware"

    // 3. 第三方包
    "go.mongodb.org/mongo-driver/bson"
    "github.com/zeromicro/go-zero/core/logx"
)
```

**Vue — 使用 `@/` 别名**：
```js
import request from '@/api/request'
import { useUserStore } from '@/stores/user'
import { useWorkspaceStore } from '@/stores/workspace'
```

### 3.4 依赖注入

**ServiceContext 作为根 DI 容器**（`api/internal/svc/servicecontext.go`）：

```go
// 工厂函数创建，所有依赖通过构造函数注入
svcCtx := svc.NewServiceContext(config)

// 多租户工厂方法 — 按 workspaceId 动态获取模型
assetModel := svcCtx.GetAssetModel(workspaceId)    // 集合: {workspaceId}_asset
taskModel := svcCtx.GetMainTaskModel(workspaceId)  // 集合: {workspaceId}_tasks
vulModel := svcCtx.GetVulModel(workspaceId)        // 集合: {workspaceId}_vul

// 全局模型 — 不分 workspace
userModel := svcCtx.UserModel
workspaceModel := svcCtx.WorkspaceModel
```

**服务构造器模式**：
```go
type ScanResultService struct {
    db *mongo.Database
}

func NewScanResultService(db *mongo.Database) *ScanResultService {
    return &ScanResultService{db: db}
}
```

**MongoDB 模型构造器模式**：
```go
// 多租户模型
func NewAssetModel(db *mongo.Database, workspaceId string) *AssetModel {
    coll := db.Collection(workspaceId + "_asset")
    return &AssetModel{coll: coll}
}

// 全局模型
func NewUserModel(db *mongo.Database) *UserModel {
    return &UserModel{db: db}
}
```

### 3.5 日志规范

- **必须**使用 go-zero 的 `logx`（`logx.Infof / logx.Errorf / logx.Info`）
- **禁止**在业务逻辑中使用 `fmt.Println`
- 日志前缀标签约定：`[模块名]` 格式，如 `[OrphanedTaskRecovery]`
- 配置中 Log Level 通过 `api/etc/cscan.yaml` 的 `Log.Level` 控制

### 3.6 异常处理

**错误码体系**（`pkg/xerr/errcode.go`）：

| 范围 | 类型 | 示例 |
|------|------|------|
| 0 | 成功 | `OK = 0` |
| 400-500 | HTTP 标准码 | `ParamError=400`, `Unauthorized=401`, `Forbidden=403`, `NotFound=404`, `ServerError=500` |
| 10001-10099 | 用户错误 | `UserNotFound=10001`, `UserPasswordError=10002`, `UserDisabled=10003` |
| 10101-10199 | 任务错误 | `TaskNotFound=10101`, `TaskStatusError=10103` |
| 10201-10299 | 工作空间错误 | `WorkspaceNotFound=10201` |
| 10301-10399 | 资产错误 | `AssetNotFound=10301` |
| 10401-10699 | 其他业务错误 | `VulNotFound=10401`, `FingerprintNotFound=10501`, `PocNotFound=10601` |

**错误使用方式**：
```go
// 创建业务错误
xerr.NewCodeError(xerr.UserNotFound)          // 使用预定义消息
xerr.NewCodeErrorMsg(xerr.ParamError, "自定义消息") // 自定义消息
xerr.NewParamError("字段不能为空")               // 参数错误快捷函数
xerr.NewServerError("")                        // 服务器错误快捷函数
xerr.NewNotFoundError("")                      // 资源不存在快捷函数
```

**统一响应封装**（`pkg/response/response.go`）：
```go
// 统一响应结构: { "code": 0, "msg": "success", "data": {...} }
response.Success(w, data)                     // 成功
response.Error(w, err)                        // 自动识别 CodeError 或普通 error
response.ErrorWithCode(w, xerr.NotFound, "")  // 指定错误码
response.ParamError(w, "参数校验失败")          // 参数错误
```

### 3.7 参数校验

- 前端请求拦截器自动注入 `Authorization: Bearer <token>` 和 `X-Workspace-Id` Header
- 后端通过 `middleware.GetWorkspaceId(ctx)` 从 Context 获取 workspaceId
- 后端通过 `middleware.GetUserId(ctx)` / `GetUsername(ctx)` / `GetRole(ctx)` 获取用户信息
- 管理员权限检查：`middleware.RequireAdmin(next)` 中间件，校验 `role == "admin"`

### 3.8 Struct Tag 规范

所有 MongoDB 模型**必须同时包含 `bson` 和 `json` 标签**：
```go
type Asset struct {
    Id         primitive.ObjectID `bson:"_id,omitempty" json:"id"`
    Host       string             `bson:"host" json:"host"`
    Port       int                `bson:"port" json:"port"`
    Labels     []string           `bson:"labels,omitempty" json:"labels"`
    CreateTime time.Time          `bson:"create_time" json:"createTime"`
    UpdateTime time.Time          `bson:"update_time" json:"updateTime"`
    RiskScore  float64            `bson:"risk_score,omitempty" json:"riskScore,omitempty"`
}
```

注意 bson 使用 `snake_case`，json 使用 `camelCase`。

### 3.9 API 路由规范

- 所有端点前缀：`/api/v1/*`
- HTTP 方法：除健康检查 (`GET /health`) 和 Worker WebSocket (`GET /api/v1/worker/ws`) 外，**所有业务接口均为 POST**
- 四层认证级别：
  1. **无认证**：`/health`、`/api/v1/login`、Worker 下载/验证/WebSocket
  2. **Worker Key 认证**（`WorkerAuthMiddleware`）：Worker 任务上报、心跳、配置拉取
  3. **JWT 认证**（`AuthMiddleware`）：所有用户操作路由（60+ 个端点）
  4. **JWT + Console 认证**（`ConsoleAuthMiddleware`）：Worker 控制台文件/终端/审计

### 3.10 Redis 使用规范

| 用途 | Key 模式 | 数据结构 |
|------|---------|---------|
| 任务队列 | `cscan:task:queue` | Sorted Set（score = 时间戳，优先级调度） |
| 任务状态 | `cscan:task:status:{taskId}` | String |
| 任务信息 | `cscan:task:info:{taskId}` | String (JSON) |
| 处理中集合 | `cscan:task:processing` | Set |
| 定时触发 | `cscan:cron:execute` | Pub/Sub Channel |
| Worker Install Key | 自定义 Key | String |
| Worker 心跳 | 自定义 Key | String |

### 3.11 前端其他规范

- **组件风格**：始终使用 `<script setup>` Composition API
- **UI 组件**：Element Plus 全量引入，图标全局注册（可直接在模板中使用 `<Edit />`）
- **样式**：SCSS，使用 Element Plus CSS 变量实现暗色模式
- **国际化**：模板中使用 `$t('key')`，语言文件位于 `web/src/i18n/locales/`（zh-CN / en-US）
- **状态管理**：Pinia stores 位于 `web/src/stores/`
- **路由懒加载**：所有组件通过 `lazyLoad()` 包装，chunk 加载失败自动刷新
- **路由 meta 字段**：`requiresAuth`（默认 true）、`title`（中文标题）、`icon`（Element Plus 图标名）、`hidden`（隐藏菜单）
- **纯 JavaScript 项目**：无 TypeScript，所有文件为 `.js` / `.vue`

---

## 四、测试与质量

### 4.1 Go 单元测试

测试文件位于 `api/internal/svc/` 和 `api/internal/handler/` 目录。

**表格驱动测试模式**：
```go
testCases := []struct {
    name     string
    input    string
    expected int
}{
    {"empty", "", 0},
    {"valid", "test", 4},
}
for _, tc := range testCases {
    t.Run(tc.name, func(t *testing.T) { /* 断言 */ })
}
```

**属性测试模式（gopter）**：
```go
parameters := gopter.DefaultTestParameters()
parameters.MinSuccessfulTests = 100
properties := gopter.NewProperties(parameters)

properties.Property("属性描述", prop.ForAll(
    func(workspaceId string, port int) bool {
        if workspaceId == "" || port <= 0 || port > 65535 {
            return true  // guard clause 跳过无效输入
        }
        return someInvariant(workspaceId, port)
    },
    gen.AlphaString().SuchThat(func(s string) bool { return len(s) > 0 }),
    gen.IntRange(1, 65535),
))
properties.TestingRun(t)
```

已实现的属性测试覆盖：资产-结果关联、目录扫描计数、分页正确性、排序默认值、合并时字段保留（labels/memo/color_tag）、跨视图一致性等。

### 4.2 Go 集成测试

- `handler/worker/security_test.go` — 使用 `httptest` + `miniredis` 的中间件安全测试
- `handler/asset/scanresult_integration_test.go` — 扫描结果集成测试
- `handler/api_compatibility_test.go` — API 兼容性测试

### 4.3 前端测试

框架已配置（Vitest + happy-dom + fast-check），配置在 `web/vite.config.js` 中：
```js
test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./src/tests/setup.js'],
    coverage: { provider: 'v8', reporter: ['text', 'json', 'html'] }
}
```

---

## 五、项目构建、测试与运行

### 5.1 环境与配置

**本地开发依赖启动**：
```bash
docker-compose -f docker-compose.dev.yaml up -d   # 启动 MongoDB(:27017) + Redis(:6379)
```

**后端服务启动（按顺序）**：
```bash
go run rpc/task/task.go -f rpc/task/etc/task.yaml     # 1. 启动 gRPC 服务 (:9000)
go run api/cscan.go -f api/etc/cscan.yaml              # 2. 启动 HTTP API (:8888)
go run cmd/worker/main.go -k <install_key> -s http://localhost:8888  # 3. 启动 Worker
```

**前端启动**：
```bash
cd web && npm install && npm run dev    # 开发服务器 (:3000)，代理 /api → :8888
```

**关键配置文件**：
| 文件 | 说明 |
|------|------|
| `api/etc/cscan.yaml` | API 配置：端口 8888，超时 300s，MaxBytes 100MB，JWT 24h |
| `rpc/task/etc/task.yaml` | RPC 配置：端口 9000 |
| `docker/cscan-api.yaml` | 容器内 API 配置 |
| `docker/task.yaml` | 容器内 RPC 配置 |
| `docker/mongo-init.js` | MongoDB 初始化脚本 |

**MongoDB 连接池**：MaxPoolSize=100, MinPoolSize=10, ConnectTimeout=10s

**Redis 连接池**：PoolSize=100, MinIdleConns=10, MaxRetries=3

### 5.2 构建命令

```bash
# Protobuf 代码生成（修改 .proto 文件后必须执行）
protoc -I rpc/task --go_out=rpc/task/pb --go_opt=paths=source_relative --go-grpc_out=rpc/task/pb --go-grpc_opt=paths=source_relative task.proto

# Go 后端
go build -o cscan ./api/cscan.go       # 构建 API 服务
go build -o worker ./worker/            # 构建 Worker
go mod download && go mod tidy          # 依赖管理

# Vue 前端
cd web
npm install                             # 安装依赖
npm run build                           # 生产构建（terser 压缩，移除 console）
npm run dev                             # 开发服务器
```

### 5.3 测试命令

```bash
# Go 测试
go test ./...                                        # 运行所有测试
go test -v ./api/internal/svc/ -run TestFunctionName # 指定测试函数
go test -v -run TestProperty1 ./api/internal/svc/    # 属性测试
go test -cover ./...                                  # 覆盖率
go test -race ./...                                   # 竞态检测

# Vue 前端测试
cd web
npm run test                                          # vitest
npx vitest run src/tests/MyComponent.test.js          # 单个测试文件
npm run test:coverage                                 # 覆盖率
```

### 5.4 生产部署

```bash
# 全栈部署
docker-compose up -d

# 独立 Worker 部署
docker-compose -f docker-compose-worker.yaml up -d

# 一键启动脚本
./cscan.sh        # Linux/macOS
.\cscan.bat       # Windows
```

访问 `https://ip:7777`，默认账号 `admin / 123456`

---

## 六、Git 工作流程

### 6.1 分支策略

- 主分支：`main`
- CI/CD 触发：push 到 `main` 或 `master`（忽略 `*.md`、`LICENSE`、`.gitignore` 变更）

### 6.2 CI/CD

`.github/workflows/build-images.yml` — 4 个并行 Job：

| Job | 镜像 | Dockerfile |
|-----|------|-----------|
| `build-api` | `cscan-api` | `docker/Dockerfile.api` |
| `build-rpc` | `cscan-rpc` | `docker/Dockerfile.rpc` |
| `build-web` | `cscan-web` | `web/Dockerfile` |
| `build-worker` | `cscan-worker` | `docker/Dockerfile.worker` |

所有镜像推送至阿里云容器镜像服务（`registry.cn-hangzhou.aliyuncs.com/txf7`），平台 `linux/amd64`，使用 GitHub Actions cache。

### 6.3 .gitignore 要点

```
web/node_modules/    # 前端依赖
web/dist/            # 前端构建产物
*.exe                # 编译产物
.idea/ .vscode/      # IDE 配置
output/              # 输出目录
screenshot/          # 截图缓存
.env                 # 环境变量
```

---

## 七、文档目录

### 7.1 文档存储规范

| 文件 | 位置 | 说明 |
|------|------|------|
| `README.md` | 根目录 | 中文项目说明、功能特性、快速开始 |
| `README_EN.md` | 根目录 | 英文项目说明 |
| `CLAUDE.md` | 根目录 | AI 编码助手指导文件（已 .gitignore） |
| `VERSION` | 根目录 | 当前版本号（V2.19） |
| `LICENSE` | 根目录 | MIT 许可证 |

项目无独立 `docs/` 目录，无 lint 配置文件（ESLint/Prettier/golangci-lint），无 Makefile。

---

## 八、关键规则

1. **工作空间隔离**: 所有数据查询**必须**按 `workspace_id` 过滤，通过 `svcCtx.GetXxxModel(workspaceId)` 获取对应集合
2. **保留用户数据**: 更新资产时**必须**保留 `labels`、`memo`、`color_tag`、布尔标志（`isNew`/`isUpdated`）、风险字段、任务追踪字段
3. **API 稳定性**: 禁止修改已有端点路径或 HTTP 方法
4. **错误码**: 使用 `pkg/xerr/errcode.go` 中的错误码常量
5. **日志**: 使用 go-zero `logx` — 禁止业务逻辑中使用 `fmt.Println`
6. **旧数据兼容**: 优雅处理缺少新字段的旧数据（fallback 逻辑，如 `Version==0` 自动赋值 `1`，`ScanTime` 零值回退 `CreateTime`）
7. **类型安全**: 禁止使用 `as any`、`@ts-ignore` 等类型抑制
8. **MongoDB**: 始终使用 `primitive.ObjectID` 作为 `_id`；必须包含 `create_time` 和 `update_time` 字段
9. **Struct Tag**: 所有模型必须同时声明 `bson` + `json` 标签（bson 用 snake_case，json 用 camelCase）
10. **响应格式**: 统一使用 `pkg/response` 封装，返回 `{ "code": 0, "msg": "success", "data": {...} }` 结构
11. **交互语言**：工具与模型交互强制使用 **English**；用户输出强制使用 **中文**。
12. **代码主权**：外部模型生成的代码仅作为逻辑参考（Prototype），最终交付代码**必须经过重构**，确保无冗余、企业级标准。
13. **风格定义**：整体代码风格**始终定位**为，精简高效、毫无冗余。该要求同样适用于注释与文档，且对于这两者，严格遵循**非必要不形成**的核心原则。
14. **仅对需求做针对性改动**：严禁影响用户现有的其他功能。
15. **判断依据**：始终以项目代码、grok的搜索结果作为判断依据，严禁使用一般知识进行猜测，允许向用户表明自己的不确定性。在调用编程语言的非内置库时，必须启用grok搜索，以文档作为判断依据进行编码。例如，在调用fastapi库对api接口进行封装时，必须使用联网搜索的最新结果作为依据、阅读官方文档说明编写代码，严禁使用已知的一般知识进行直接编码，这样会直接造成用户项目的崩坏。
16. **禁用临时脚本**：更新任何文件时，不得使用临时脚本、批量代码工具或程序自动改写内容；应使用直接、逐文件、便于人工审阅的修改方式完成更新。
17. **MUST** ultrathink in English.

===== FILE ayush-that/jiang-clips::AGENTS.md | stars=313 followers=1150 lang=TypeScript bytes=4475 =====

# AGENTS.md - jiang-clips

Automated short-form clip extraction pipeline for YouTube videos using AI.

## Project Overview

- **Runtime**: Bun (not Node.js)
- **Language**: TypeScript with strict mode
- **Module System**: ESNext with bundler module resolution
- **Package Manager**: Bun (uses bun.lock)

## Commands

```bash
# Run the pipeline
bun run src/index.ts pipeline <youtube-url>
bun run src/index.ts batch <channel-url>
bun run src/index.ts resume <run-id>
bun run src/index.ts status [run-id]
bun run src/index.ts clean <run-id>

# Testing
bun test                     # All tests
bun test tests/utils         # Single test directory
bun test tests/utils/fs.test.ts  # Single test file
bun test --reporter=verbose tests/  # Verbose output

# Linting & Formatting
oxlint                       # Lint src/ and tests/
oxfmt --write src tests      # Format and write changes
oxfmt --check src tests      # Check formatting without writing
```

## Code Style

### TypeScript
- Use `type` for simple type aliases, `interface` for complex types
- Prefer `export class` for public classes
- Use `enum` for related constants (e.g., `PipelineStage`, `StageStatus`)
- All functions must have explicit return types
- Use `unknown` instead of `any` for generic error handling

### Imports
Order imports separated by blank lines:
1. External packages (e.g., `chalk`, `commander`, `zod`)
2. Internal modules (e.g., `../utils/logger`, `./config`)
3. Type imports use `import type`

```typescript
import chalk from "chalk";
import { join } from "path";
import { createLogger } from "../utils/logger";
import type { VideoMetadata } from "../pipeline/types";
```

### Naming Conventions
- **Files**: kebab-case (e.g., `video-processor.ts`, `clip-identifier.ts`)
- **Classes**: PascalCase (e.g., `PipelineOrchestrator`, `CheckpointManager`)
- **Functions/variables**: camelCase (e.g., `extractVideoId`, `runId`)
- **Enums**: PascalCase with UPPER_SNAKE values (e.g., `PipelineStage.DOWNLOAD`)
- **Types/Interfaces**: PascalCase (e.g., `VideoMetadata`, `ClipCandidate`)
- **Constants**: camelCase or UPPER_SNAKE (logger instances use camelCase module names)

### Error Handling
- Throw `Error` objects with descriptive messages
- Wrap async operations in try/catch with proper cleanup in `finally` blocks
- Log errors before re-throwing: `log.error(\`Failed: ${err}\`); throw err;`
- Handle subprocess failures with exit code checks

```typescript
try {
  const result = await someAsyncOperation();
  log.info(`Success: ${result}`);
} catch (err) {
  log.error(`Operation failed: ${err}`);
  throw err;
} finally {
  cleanup();
}
```

### Path Aliases
Configured in `tsconfig.json`:
```typescript
import { createLogger } from "@/utils/logger";  // resolves to ./src/utils/logger
```

### Logging
Use the `createLogger` utility with module name:
```typescript
const log = createLogger("module-name");
log.info("message");
log.error("failed: ${err}");
```

Log levels: `debug`, `info`, `warn`, `error`

## Project Structure

```
src/
├── index.ts          # CLI entry point (commander)
├── config.ts        # Zod schema & config loader
├── pipeline/        # Pipeline orchestration
│   ├── orchestrator.ts
│   ├── checkpoint.ts
│   └── types.ts
├── modules/         # Processing modules
│   ├── downloader.ts
│   ├── transcriber.ts
│   ├── clip-identifier.ts
│   ├── video-processor.ts
│   └── caption-generator.ts
├── utils/           # Utilities
│   ├── logger.ts
│   ├── fs.ts
│   └── ffmpeg.ts
└── remotion/        # Video rendering
    └── types.ts

tests/
├── pipeline/
├── modules/
└── utils/
```

## Testing

Uses `bun:test` with `describe`/`test`/`expect`:
```typescript
import { describe, test, expect } from "bun:test";

describe("FeatureName", () => {
  test("does something", () => {
    expect(result).toBe(expected);
  });
});
```

## Configuration

Environment variables validated via Zod in `src/config.ts`:
- `GEMINI_API_KEY` (required)
- `WHISPER_MODEL` (tiny|base|small|medium|large, default: base)
- `MAX_PARALLEL_CLIPS` (1-10, default: 3)
- `SILENCE_THRESHOLD_DB` (default: -35)
- `OUTPUT_WIDTH`/`OUTPUT_HEIGHT` (default: 1080x1920)

## Dependencies

- **@google/genai**: AI content generation
- **@remotion/***: Video rendering
- **chalk**: Terminal colors
- **commander**: CLI framework
- **zod**: Schema validation


===== FILE EvanBacon/chat-template::AGENTS.md | stars=298 followers=6183 lang=TypeScript bytes=1359 =====

Use `bunx expo install` to add dependencies.

When searching Apple docs, replace https://developer.apple.com with https://sosumi.ai to read as markdown. e.g. https://sosumi.ai/documentation/Xcode/configuring-app-groups instead of https://developer.apple.com/documentation/xcode/configuring-app-groups

## Pressable Style Functions

Do NOT use the function form of `style` on `Pressable` (e.g. `style={({ pressed }) => ({ ... })}`). This is not supported when using Uniwind. Instead, use `className` with the `active:` modifier for pressed states (e.g. `className="bg-transparent active:bg-muted"`).

## CSS Variables

Do NOT use CSS variables (e.g. `var(--app-muted)`) directly in inline `style` props. Instead, use Tailwind classes. The design tokens in `global.css` are mapped to Tailwind colors via the `@theme` block, so use classes like `bg-muted`, `bg-accent`, `border-border`, `text-foreground`, etc. For pressed/active states, use `active:bg-muted` on Pressable components via `className`.

## Verification

This app requires a custom Expo development build and will not work in Expo Go. To verify the app:

- Use `npx serve-sim` to verify iOS and Apple platforms.
- Use `npx agent-browser` to verify on web.

## Metadata

Manage Apple App Store metadata and screenshots with `npx eas-cli@latest metadata:pull` and `npx eas-cli@latest metadata:push`.


===== FILE kitlangton/neotype::AGENTS.md | stars=257 followers=1407 lang=Scala bytes=602 =====

# Repository Agent Notes

- Prefer `sbt` for build and test tasks (e.g. `sbt test`, `sbt "coreJVM/compile"`).
- Prefer `bun` for JS tooling when needed, unless a module explicitly uses something else.
- The compile‑time evaluator lives in `modules/comptime`; avoid re‑introducing the old `eval`/`eval2` codepaths.
- Update `modules/comptime/SUPPORTED.md` when adding or removing comptime features.
- Keep rule changes test‑backed; add/adjust tests under `modules/comptime/shared/src/test/scala/comptime`.
- Performance changes should be gated by measurement; see `modules/comptime/PERF_PLAN.md`.


===== FILE feiskyer/codex-settings::AGENTS.md | stars=222 followers=2760 lang=Python bytes=4352 =====

# Repository Guidelines

## Repository Structure

- `config.toml` is the shared Codex CLI configuration and points to the local `copilot-gateway` provider at `localhost:4141`.
- Root-level `*.config.toml` files are optional Codex Profiles (`chatgpt`, `azure`, `github-copilot`, and `openrouter`). Keep the `<name>.config.toml` naming required by `codex --profile <name>`.
- `skills/<name>/SKILL.md` contains reusable workflows. Put deterministic helpers in `scripts/`, detailed references in `references/`, UI metadata in `agents/openai.yaml`, and offline regression tests in `tests/`.
- `prompts/` contains historical Custom Prompts retained for migration reference. Do not add new workflows there; use a Skill instead.
- `litellm_config.yaml` is only for the optional GitHub Copilot through LiteLLM profile. It is not the backend used by the default `config.toml`.

## Validation Commands

Run checks that match the files you changed. The standard offline suite is:

```bash
# TOML syntax
python3 -c 'import pathlib, tomllib; [tomllib.loads(p.read_text()) for p in pathlib.Path(".").glob("**/*.toml")]'

# Skill structure
for skill in skills/*; do
  test ! -f "$skill/SKILL.md" || \
    python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$skill"
done

# Python scripts and offline tests
python3 -m compileall -q skills
ruff check skills
for test_dir in skills/*/tests; do
  test ! -d "$test_dir" || python3 -m unittest discover -s "$test_dir" -v
done

# Bundled shell and JavaScript helpers
bash -n skills/brainstorming/scripts/start-server.sh \
  skills/brainstorming/scripts/stop-server.sh
node --check skills/brainstorming/scripts/server.cjs
node --check skills/brainstorming/scripts/helper.js
```

Run provider integration checks only when the related provider files change:

- Strict Codex config: with the relevant provider available, run `CODEX_HOME="$PWD" codex --strict-config exec --ephemeral --sandbox read-only --skip-git-repo-check -c mcp_servers.chrome.enabled=false -c web_search="disabled" "Reply exactly OK"`.
- Default gateway: start `copilot-gateway`, then run `codex` or `codex doctor --summary`.
- LiteLLM profile: start `litellm --config ~/.codex/litellm_config.yaml`, then run `codex --profile github-copilot`.
- ChatGPT profile: authenticate with `codex login`, then run `codex --profile chatgpt`.
- External API Skills: prefer mocked/offline tests. Use real credentials only for an explicitly requested integration test.

## Style and Skill Conventions

- TOML uses two-space indentation where indentation applies, aligned `=` signs within related blocks, double-quoted strings, and grouped tables.
- Name Profiles, Skills, prompts, and scripts with lowercase kebab-case unless the platform requires another filename.
- Skill frontmatter contains only `name` and `description`. Put requirements and compatibility notes in the body.
- Write Skill instructions in imperative form. Keep the core workflow concise and move repeatable or fragile behavior into bundled scripts.
- Add or refresh `agents/openai.yaml` when a Skill is created or materially renamed. Its `default_prompt` must mention `$skill-name`.
- Scripts must expose `--help`, validate local inputs before network/API calls, return non-zero on failure, and create output parent directories when appropriate.
- Tests must not require paid API calls, browser cookies, interactive approval, or live third-party services unless the user explicitly requests an integration run.

## Commit and Pull Request Guidelines

- Use concise title-case imperative commit subjects, consistent with repository history.
- Keep commits scoped; do not include local Codex runtime state, credentials, generated logs, or unrelated working-tree changes.
- In pull requests, list affected configs or Skills, validation commands run, intentionally skipped integration checks, and any compatibility assumptions.
- Use redacted placeholders such as `sk-dummy` in examples.

## Security

- Never commit API keys, access tokens, cookies, real authorization headers, or private logs.
- Review `shell_environment_policy`, sandbox, network, MCP, and browser-cookie behavior when changing integrations.
- Do not silently broaden permissions or enable browser-cookie access. Explain the need and obtain user approval first.
- Follow `SECURITY.md` for vulnerability reporting.


===== FILE samaaron/tau5::CLAUDE.md | stars=204 followers=2017 lang=C++ bytes=7582 =====

# Claude.md — Tau5 Development Guidelines

## Project Overview
- Tau5 is a collaborative creative coding platform for music, visuals, and live interactive art.
- Built on the **BEAM VM** with Elixir/Phoenix for the server and **Qt/C++** hosting a full Chromium browser for the GUI.

## Tau5 has two build modes
1. Dev - Development mode - contains built-in dev tools and runs Phoenix in dev mode from source with auto-compile and asset-building enabled by deafult.
2. Release - No dev tools, Phoenix running in production mode from a mix release.

## Deployment Modes (TAU5_MODE)
Tau5 has three deployment modes that control routing and features:
1. **`:gui`** - Desktop app mode. The full app - Qt Chromium Browser + Elixir Phoenix Server + NIFs. Routes `/` to `/app` (MainLive LiveView)
2. **`:node`** - Headless server mode (default). Qt CLI + Elixir Phoenix Server + NIFs. Routes `/` to `/app` (MainLive LiveView)
3. **`:central`** - Live web mode. Elixir Phoenix Server only. Routes `/` to a special WebGL shader landing page (CentralController). Used for central/hosted deployments (e.g., tau5.live)

## Environment
- **Default assumption**: development mode (`MIX_ENV=dev`).
- **Release mode** is explicit and uses `bin/*/build-release*` scripts.

## Build & Run (bin scripts)
- Scripts are the **canonical way** to build/run Tau5. There are script dirs for Windows (win), macOS (mac) and Linux (linux).
- Examples:
  - `bin/linux/dev-tau5-spectra.sh --devtools` — run GUI + Spectra MCP integration.
  - `bin/mac/dev-tau5-gui.sh` — run standalone GUI.
  - `bin\win\dev-tau5-node.bat` — run headless server node.
  - `bin/linux/dev-build-server.sh` — build the Phoenix server only.
  - `bin/mac/build-release.sh` — build production desktop release.

## Server Development
- Phoenix LiveView app is in `server/`:
  - `lib/tau5/` — business logic.
  - `lib/tau5_web/` — web UI + LiveView.
  - `lib/tau5/mcp/` — MCP/AI integration.
- Asset pipeline:
  - **esbuild** bundles JavaScript (see `config/config.exs`).
  - **Tailwind CSS** compiles styles (see `assets/tailwind.config.js`).
  - All dependencies are **vendored**; **no npm** in production.
  - Tailwind config must include LiveView templates in `content` and safelist `phx-*` classes.

## GUI Development
- GUI is a Qt/C++ desktop app (`gui/`).
- Uses Chromium-based rendering to display Phoenix frontend.
- Considered stable infrastructure; changes here are less frequent but may be required.
- Claude should reason about C++/Qt code when work explicitly involves the GUI.

## Rules & Constraints
- ✅ Use provided **bin scripts** for running, building, and testing.
- ✅ Assume we're building and working with dev mode unless explicitly told otherwise.
- ✅ Keep builds **self-contained** — use vendored JS/CSS, esbuild, Tailwind.
- ✅ Safelist `phx-*` classes in Tailwind to preserve LiveView behavior.
- ❌ Do not introduce **npm**, yarn, webpack, or Vite.
- ❌ Do not fetch remote dependencies at build time.
- ❌ Do not suggest restarting the Phoenix server automatically — that is a user action.

## Development Workflow

A common workflow leverages the MCP servers for rapid experimentation:

1. Use **Tidewave** (Elixir MCP) to experiment with server-side changes and observe dynamic behavior
2. Use **Spectra** (Chrome DevTools MCP) to inspect DOM changes and verify UI updates
3. Solidify changes by editing files, which triggers Phoenix auto-reload
4. Verify the reloaded changes using Spectra tools

The Phoenix server auto-reloads on file save:
- Elixir files trigger recompilation
- Assets (CSS/JS) trigger esbuild/Tailwind rebuilds
- LiveView automatically pushes updates to the browser

## MCP / AI Integration

Tau5 provides three MCP servers for development:

1. **Spectra** - Bridge server providing Chrome DevTools access, Tidewave integration, and log viewing
   - Built with `dev-build-spectra.sh` or as part of the GUI build
   - Connects to Chrome DevTools Protocol (port 9220-9225 depending on channel)
   - Access to DOM manipulation, JavaScript execution, and browser inspection

2. **Tidewave** - Elixir runtime introspection and manipulation
   - Available at `http://localhost:555X/tidewave` where X is the channel (0-5)
   - Module introspection, code evaluation, database access
   - Live server state inspection

3. **Tau5 MCP** - End-user functionality (Lua interpreter)
   - Sandboxed code execution environment
   - Available when running with MCP enabled

## MCP Development Techniques

### State Inspection Pattern
Inspect LiveView process state and verify UI synchronization:

```elixir
# Tidewave: Get LiveView state
:sys.get_state({:via, Registry, {Tau5.PubSub, "phx-SESSION_ID"}})
```

```javascript
// Spectra: Verify DOM reflects state
document.querySelector('[data-phx-component]')
```

### Error Debugging Flow
Check errors across server and client:
- Use Tidewave's `get_logs` to check server logs
- Use Spectra's `getConsoleMessages` for browser console
- Cross-reference to identify root causes

### LiveView Hook Debugging
```javascript
// Check registered hooks
window.liveSocket.hooks;

// Verify hook is attached
document.getElementById("element-id").__view;

// Check LiveSocket connection
window.liveSocket.isConnected();

// Enable debug logging
window.liveSocket.enableDebug();
```

### Asset Pipeline Debugging
When CSS/JS changes don't appear:

```javascript
// Check loaded stylesheets
Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map(l => l.href);

// Check loaded scripts
Array.from(document.querySelectorAll('script[src]')).map(s => s.src);

// Verify asset fingerprinting
document.querySelector('[phx-track-static]');
```

## DOM Manipulation Best Practices

⚠️ **CRITICAL: Phoenix LiveView manages the DOM and may re-render at any time**

### Approach (in order of preference)

1. ✅ **FIRST**: Direct text node update
   ```javascript
   document.querySelector('selector').textContent = 'new value';
   // For preserving whitespace:
   document.querySelector('selector').firstChild.nodeValue = 'new value';
   ```

2. ✅ **FOR MULTIPLE**: Use querySelectorAll
   ```javascript
   document.querySelectorAll('selector').forEach(elem => {
     if (elem.textContent.includes('target')) {
       elem.textContent = elem.textContent.replace('target', 'replacement');
     }
   });
   ```

3. ⚠️ **AVOID**: Complex selection range manipulation (often fails in LiveView)
4. ❌ **NEVER**: Make multiple tool calls to find the same element

### JavaScript Execution Guidelines

The `evaluateJavaScript` tool expects valid expressions for console execution:

❌ **DON'T** write:
```javascript
if (condition) {
    'Success';  // Syntax error - loose string literal
}
```

✅ **DO** write:
```javascript
// Option 1: Variable assignment
let result = condition ? 'Success' : 'Error';
result;  // Last line is returned

// Option 2: Direct expression
document.querySelector('.element').textContent = 'new value';
'Updated';  // Simple return confirmation
```

## Key Takeaways
1. **Server development is primary** — focus on Elixir/Phoenix + LiveView + asset pipeline.
2. **GUI is secondary** — Qt/C++ is stable but may require changes.
3. **Always use bin scripts for building and launching** — they set up the environment correctly.
4. **Strict vendoring** — no npm, no external fetches, no alternative build tools.
5. **Dev mode is default** — release is explicit.
6. **Use Spectra** - Spectra provides an extensive suite of MCP tools to help Agents colloaborate with the development of Tau5.


===== FILE kunchenguid/gh-axi::AGENTS.md | stars=192 followers=3537 lang=TypeScript bytes=7814 =====

# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Dependency bumps and the lockfile

The committed `pnpm-lock.yaml` is Prettier-formatted (multi-line `resolution:` and `engines:` blocks), which is not pnpm's native output format.
A plain `pnpm install` rewrites those blocks inline and produces a ~1000-line cosmetic churn even when only one dependency actually changed.
After bumping a dependency, run `pnpm exec prettier --write pnpm-lock.yaml` so the diff collapses to just the real change.
CI uses `pnpm install --frozen-lockfile`, which parses the YAML structurally and accepts the Prettier-formatted lockfile, so the formatting does not break the frozen-install check.

## The SDK-provided `update` command

`gh-axi` runs its CLI through `runAxiCli` from `axi-sdk-js` (`src/cli.ts`) and registers no `update` command of its own.
Since `axi-sdk-js@0.1.8` ships `update` as a `RESERVED_COMMANDS` built-in, `gh-axi` inherits `gh-axi update` for free, and the SDK auto-resolves the npm package name (`gh-axi`) by walking up to the nearest `package.json`.
The SDK also appends a `"built-in":` section to the top-level `--help` output at runtime, so `src/cli.ts`'s `TOP_HELP` constant is a prefix of the rendered help rather than the whole thing.

## Release process

Releases are cut by release-please from conventional commit messages on `main`; merging the bot's release PR triggers `npm publish` via `.github/workflows/release-please.yml`.
Do not hand-edit `CHANGELOG.md` or `.release-please-manifest.json` (a guard workflow blocks PRs that touch them), and regenerate `skills/gh-axi/SKILL.md` with `pnpm run build:skill` instead of editing it directly.

## GitHub Enterprise host support (`src/host.ts`, `src/cli.ts`)

`gh-axi` targets a custom GitHub host (e.g. a GHE server like `ghe.example.com`) via a global `--hostname <host>` flag or the `GH_HOST` env var; explicit `--hostname` wins.
Like `-R`/`--repo`, `--hostname` must come _after_ the command (the SDK rejects leading flags), and it is stripped from the args before they reach the underlying `gh` (it is never a subcommand flag).
`src/cli.ts`'s `resolveContext` sets `process.env.GH_HOST` only when `--hostname` is present; the child `gh` process inherits `process.env`, so no explicit env is threaded through `gh.ts`. When no `--hostname` is given, `GH_HOST` is left untouched, keeping the default (github.com) behavior byte-for-byte identical.
`src/host.ts#resolveHost()` (flag > `GH_HOST` > `github.com`) is the single source of truth for the effective host used when _building or parsing_ URLs — `parseRemoteUrl` in `src/context.ts` matches the configured host in `git remote` URLs, and `issue transfer`'s fallback URL is built as `https://<host>/...`. The `gh pr create` output regex (`/pull/(\d+)/`) is already host-agnostic.

## Secret/variable value input (`src/secretValue.ts`, `src/stdin.ts`, `gh.ts#ghExecWithStdin`)

`gh secret list`/`gh variable list` do not support `--limit` or any pagination flag (unlike `issue`/`pr`/`release` list), so `secret.ts`/`variable.ts` list all results in one call with no `--limit` flag of their own.

Secret values must never appear in argv (visible via `ps`) or stdout.
`secretCommand`'s `set` subcommand is stdin-only: it rejects `--body`/`-b`, calls `resolveValue(undefined, "secret")`, and pipes the resolved value to `gh.ts#ghExecWithStdin` so the wrapped `gh secret set` child also never receives the value in argv.
Variable values are not treated as secrets: `variableCommand`'s `set` subcommand may resolve the value from `--body`/`-b` or piped stdin (`resolveValue` in `src/secretValue.ts`, backed by `src/stdin.ts`), and `gh-axi variable list` intentionally prints variable values.
`variable set --body` values are visible in the `gh-axi` process argv, but `ghExecWithStdin` still keeps them out of the child `gh variable set` argv.
`resolveValue` throws immediately instead of blocking when stdin is an interactive TTY and no usable value source was provided, since AXI commands must never hang waiting for interactive input.

`secretCommand`'s `list`/`set`/`delete` forward `--env`/`-e <environment>` to `gh secret ... --env` via `resolveScope` in `src/commands/secret.ts`; the repo/host context flags are already stripped in `cli.ts` before the command sees its args, so `-R`/`--hostname` compose with `--env` for free. `resolveScope` is deliberately strict: a malformed `--env` (missing/empty value), conflicting `--env` flags, gh's other scopes (`--org`/`--user`/`--app`, plus the value-channel `--env-file`), and any unknown flag all throw loudly rather than silently falling back to repo scope. Unknown flags are echoed by name only (the `=value` is stripped) so a secret value can never leak into an error message.

## GitHub Projects (`gh project`) support (`src/commands/project.ts`)

Unlike every other command family, `gh project` is owner-scoped (`--owner <login>`), not repo-scoped — it has no `--repo` flag at all.
`project.ts`'s subfunctions therefore never pass `RepoContext` as the second arg to `ghJson` (matching `search.ts`'s existing pattern), since `gh.ts#buildArgs` auto-appends `--repo` for flag/env-sourced contexts and `gh project` would reject that flag.
Instead, `resolveOwner()` defaults `--owner` to the current repo's owner (`ctx?.owner`) when the flag is omitted and a repo context is available, falling back to explicit `@me` otherwise because `gh project` requires an owner in non-interactive shells.
`gh project` subcommands use `--format json` (whole-object dump), not the `--json field,field` selection style used by `issue`/`pr`/`release`; list-shaped responses come back wrapped (e.g. `{ projects: [...], totalCount }`), not as a bare array.
Since Projects v2 items carry per-project custom fields (Status, Priority, ...) with no fixed schema, `item-list`/`field-list` render through bespoke functions (`renderProjectItems`/`renderProjectFields`) that flatten any unknown scalar top-level key into its own column, rather than a fixed `FieldDef` schema.
Requires the `project` (or `read:project`) OAuth scope on the `gh` token; `src/errors.ts` matches gh's literal `"authentication token is missing required scopes [...]"` stderr (verified against a live token missing the scope) and maps it to `FORBIDDEN` with a `gh auth refresh -s <scope>` suggestion — this pattern is generic, not project-specific, so it also covers other gh features gated by OAuth scopes.

## Repeatable flags (`src/args.ts`)

`gh` accepts `--label`, `--assignee`, `--reviewer`, `--project`, and the `--add-*`/`--remove-*` variants once per value, so gh-axi must collect _every_ occurrence.
Use `getAllFlags`/`takeAllFlags` plus `pushRepeated`; `getFlag`/`takeFlag` keep only the first occurrence and silently discard the rest, which is the bug that recurred as #55, #57, and #75.
Both collectors reject a dangling (`--label` with nothing after it) or blank (`--label=`) value with a `VALIDATION_ERROR` instead of dropping it.
Pick the collector that matches the surrounding file: `issue.ts` reads args non-destructively (`getAllFlags`), `pr.ts` consumes them (`takeAllFlags`).
When a flag becomes repeatable, mark it `(repeatable)` in that command's `*_HELP` string.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.


===== FILE ascorbic/astro-loaders::CLAUDE.md | stars=178 followers=1373 lang=TypeScript bytes=1965 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a monorepo for Astro loaders using pnpm workspaces. The main packages are:

- `packages/` - Individual loader packages (`@ascorbic/*`)
- `packages/utils/` - Shared utilities (`@ascorbic/loader-utils`)
- `demos/` - Demo applications using the loaders

Each loader package follows the same structure:

- `src/` - TypeScript source code with main loader implementation
- `dist/` - Built output (generated)
- `test/` - Vitest test files

## Common Commands

All commands should be run from the repository root.

### Development

- `pnpm build` - Build all packages
- `pnpm test` - Run tests for all packages
- `pnpm check` - Run type checking and linting for all packages

### Package-specific commands

- `pnpm run --filter @ascorbic/csv-loader build` - Build specific package
- `pnpm run --filter @ascorbic/csv-loader test` - Test specific package
- `pnpm run --filter @ascorbic/csv-loader check` - Check specific package

### Demo development (from demos/loaders/)

- `pnpm run dev` - Start Astro dev server
- `pnpm run build` - Build demo site

## Architecture

### Loader Pattern

All loaders implement the Astro `Loader` interface:

- `name` - Identifier for the loader
- `load(options: LoaderContext)` - Main loading function that syncs data to Astro's store

### Shared Utilities

`@ascorbic/loader-utils` provides common functionality:

- `getConditionalHeaders()` - HTTP conditional request headers
- `storeConditionalHeaders()` - Store HTTP cache headers in meta

### Build System

- Uses `tsup` for TypeScript compilation to ESM
- `publint` and `@arethetypeswrong/cli` for package validation
- Workspace dependencies use `workspace:^` protocol

### Testing

- Vitest for unit testing
- Tests in `test/` directories within each package

### SCM

- Uses conventional commits
- Changes tracked using `changesets`


===== FILE jkitchin/vasp::CLAUDE.md | stars=155 followers=1368 lang=Python bytes=5067 =====

# VASP-ASE Interface

A modern Python interface for VASP (Vienna Ab initio Simulation Package) through ASE (Atomic Simulation Environment).

## Project Structure

```
vasp/
├── vasp/                    # Main package
│   ├── __init__.py          # Vasp calculator class
│   ├── parameters.py        # Parameter presets (VdW, DFT+U, HSE06, etc.)
│   ├── runners/             # Execution backends
│   │   ├── local.py         # LocalRunner for direct execution
│   │   ├── interactive.py   # InteractiveRunner for persistent VASP
│   │   ├── socket_io.py     # Socket server/client (i-PI protocol)
│   │   ├── slurm.py         # SLURM cluster runner
│   │   └── kubernetes.py    # Kubernetes runner
│   ├── recipes/             # Workflow recipes (quacc-style)
│   │   ├── core.py          # static_job, relax_job, double_relax_flow
│   │   ├── slabs.py         # Surface calculation recipes
│   │   ├── phonons.py       # Phonon calculation recipes
│   │   └── decorators.py    # @job, @flow, @subflow decorators
│   ├── database/            # Vector database for embeddings
│   └── tests/               # Test suite
├── docs/                    # Jupyter Book documentation
│   └── tutorials/           # 21 progressive tutorial notebooks
└── .claude/                 # Claude Code configuration
```

## Key Files

- `vasp/__init__.py` - Main `Vasp` calculator class
- `vasp/parameters.py` - Preset functions: `get_vdw_params()`, `get_ldau_params()`, `get_hybrid_params()`
- `vasp/runners/` - Execution backends: `LocalRunner`, `InteractiveRunner`, `SocketServer`, `SlurmRunner`
- `vasp/recipes/core.py` - `static_job`, `relax_job`, `double_relax_flow`
- `vasp/database/` - Vector database with per-atom embeddings

## Development Commands

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=vasp

# Build documentation
jupyter-book build docs

# Lint code
ruff check .
```

## VASP Parameter Quick Reference

### Common Parameters
- `xc` - Exchange-correlation: 'PBE', 'LDA', 'PW91'
- `encut` - Plane-wave cutoff (eV)
- `kpts` - K-point mesh: (8, 8, 8) or path for bands
- `ismear` - Smearing: -5 (tetrahedron), 0 (Gaussian), 1 (MP)
- `sigma` - Smearing width (eV)

### Relaxation
- `ibrion` - Optimizer: 1 (quasi-Newton), 2 (CG)
- `isif` - What to relax: 2 (ions), 3 (ions+cell)
- `nsw` - Max ionic steps
- `ediffg` - Force convergence (negative = forces in eV/Å)

### Spin/Magnetism
- `ispin` - 1 (non-spin), 2 (spin-polarized)
- `magmom` - Initial magnetic moments

### DFT+U
- Use `get_ldau_params(['Fe', 'O'], {'Fe': HubbardU(u=4.0)})`

### Hybrid Functionals
- Use `get_hybrid_params('hse06')`

### Van der Waals
- Use `get_vdw_params('d3bj')` for D3-BJ correction

## Tutorial Progression

1. **Beginner (01-05)**: Energy, convergence, relaxation, EOS, DOS
2. **Intermediate (06-10)**: Bands, magnetism, surfaces, adsorption, reactions
3. **Advanced (11-20)**: Phonons, DFT+U, HSE06, vdW, workflows, NEB, vibrations, visualization, pseudopotentials, interactive mode

## Code Style

- Use type hints
- Follow existing patterns in the codebase
- Add tests for new features
- Update documentation for user-facing changes

## Testing

Tests use `MockRunner` to run without VASP:

```python
from vasp.runners import MockRunner, MockResults

mock = MockResults(energy=-10.5, forces=np.zeros((2, 3)))
runner = MockRunner(results=mock)
calc = Vasp(atoms=atoms, runner=runner, ...)
```

## Claude Code Integration

### Global Installation

Install Claude Code skills globally (works from any project):

```bash
vasp-claude install    # Install skills
vasp-claude status     # Check installation
vasp-claude uninstall  # Remove skills
```

### Project Commands

Use these slash commands when working in this repository:

| Command | Description |
|---------|-------------|
| `/docs` | Open documentation |
| `/examples` | List all examples |
| `/tutorial <n>` | View tutorial n (1-16) |
| `/test` | Run test suite |
| `/new-example` | Create new example |
| `/architecture` | Review codebase |
| `/lint` | Run code quality checks |
| `/build-docs` | Build Jupyter Book |
| `/status` | Project status |

### Job Monitoring Commands

| Command | Description |
|---------|-------------|
| `/watch-job <dir>` | Monitor VASP job status |
| `/fix-job <dir>` | Diagnose and fix failed job |
| `/vasp-help <topic>` | Parameter reference |

### Global Commands (after `vasp-claude install`)

These work from any project:

| Command | Description |
|---------|-------------|
| `/vasp-help <topic>` | VASP parameter help |
| `/vasp-watch-job <dir>` | Monitor running job |
| `/vasp-fix-job <dir>` | Auto-fix failed job |
| `/vasp-examples` | List tutorials |
| `/vasp-tutorial <n>` | View tutorial |

### Skills

Claude automatically uses these skills:
- **vasp** - General VASP calculation help
- **job-watcher** - Job monitoring and troubleshooting
- **troubleshoot** - Error diagnosis and fixes


===== FILE ZhangHanDong/pi-book::CLAUDE.md | stars=125 followers=1928 lang=JavaScript bytes=4406 =====

# pi-book 写作指南

## 项目概述

本目录是《pi 的设计艺术：构建生产级 Coding Agent 的架构决策》一书的写作空间。

全书以 pi-mono 项目的**设计决策**为骨架，源码为佐证，面向有工程经验、想真正理解 agent 系统设计的开发者。

## 大纲

完整大纲见 [outline.md](outline.md)。Codex v1 大纲见 [outline-v1.md](outline-v1.md) 供参考。

## 章节 Spec（任务合约）

每篇/每组章节有一个 agent-spec 任务合约，定义了写作要求、验收标准和取舍约束。
**写任何章节前，必须先读对应的 spec。**

| Spec 文件 | 覆盖章节 | 预估工时 | 依赖 |
|-----------|---------|---------|------|
| [project.spec.md](specs/project.spec.md) | 全书约束 | - | - |
| [ch01-prologue.spec.md](specs/ch01-prologue.spec.md) | 第 1 章：序章 | 0.5d | - |
| [ch02-03-layering.spec.md](specs/ch02-03-layering.spec.md) | 第 2-3 章：分层的纪律 | 1d | - |
| [ch04-07-pi-ai.spec.md](specs/ch04-07-pi-ai.spec.md) | 第 4-7 章：pi-ai 设计 | 2d | ch02-03 |
| [ch08-10-runtime.spec.md](specs/ch08-10-runtime.spec.md) | 第 8-10 章：Agent Runtime | 2d | ch04-07 |
| [ch11-14-product.spec.md](specs/ch11-14-product.spec.md) | 第 11-14 章：产品化 | 2d | ch08-10 |
| [ch15-18-extensibility.spec.md](specs/ch15-18-extensibility.spec.md) | 第 15-18 章：能力外置 | 1.5d | ch11-14 |
| [ch19-23-tools.spec.md](specs/ch19-23-tools.spec.md) | 第 19-23 章：工具设计 | 2d | ch08-10 |
| [ch24-27-ui.spec.md](specs/ch24-27-ui.spec.md) | 第 24-27 章：UI 层 | 1.5d | ch11-14 |
| [ch28-29-products.spec.md](specs/ch28-29-products.spec.md) | 第 28-29 章：产品化实证 | 1d | ch11-14 |
| [ch30-32-philosophy.spec.md](specs/ch30-32-philosophy.spec.md) | 第 30-32 章：设计哲学 | 1.5d | ch15-18, ch19-23 |
| [appendix.spec.md](specs/appendix.spec.md) | 附录 A-D | 0.5d | ch08-10, ch19-23 |

### 依赖关系（关键路径用粗线标注）

```
ch01-prologue (0.5d)
ch02-03-layering (1d) ═══> ch04-07-pi-ai (2d) ═══> ch08-10-runtime (2d) ═══> ch11-14-product (2d) ═══> ch15-18-extensibility (1.5d) ═══> ch30-32-philosophy (1.5d)
                                                          │                         │
                                                          ├──> ch19-23-tools (2d) ──┤──> appendix (0.5d)
                                                          │                         │
                                                          │                         ├──> ch30-32-philosophy
                                                          │
                                                          ├──> ch24-27-ui (1.5d)
                                                          └──> ch28-29-products (1d)
```

**关键路径**: ch02-03 → ch04-07 → ch08-10 → ch11-14 → ch15-18 → ch30-32（总计 10d）

## 写作规则

1. **每章以设计问题开头** — 不是"这个模块有什么"，而是"为什么要这样设计"
2. **每个关键决策标注取舍** — 得到什么、放弃什么
3. **源码只在需要时出场** — 引用格式：`packages/ai/src/api-registry.ts:66-78`
4. **中文写作，术语保留英文** — 如 provider, stream, tool call, compaction
5. **每章 3000-6000 字** — 不超过 8000 字
6. **代码块不超过 40 行** — 只展示设计核心，不贴完整实现
7. **图示使用 Mermaid** — 放在章节内，不创建单独图片文件
8. **章节文件命名** — `src/ch{NN}-{slug}.md`（mdbook 结构）
9. **目录结构由 `src/SUMMARY.md` 控制** — 修改章节顺序或添加新章节时同步更新

## 构建与预览

```bash
# 构建 HTML 书籍
cd pi-book && mdbook build

# 本地预览（自动刷新）
cd pi-book && mdbook serve --open
```

## 写作前的检查

```bash
# 读取对应 spec
agent-spec contract specs/ch04-07-pi-ai.spec.md

# 写完后验证 spec
agent-spec verify specs/ch04-07-pi-ai.spec.md
```

## 源码参考

写作时需要参考的 pi-mono 源码在上级目录：

- `../packages/ai/` — pi-ai 层
- `../packages/agent/` — pi-agent-core 层
- `../packages/coding-agent/` — pi-coding-agent 层
- `../packages/tui/` — pi-tui 层
- `../packages/mom/` — mom (Slack bot)
- `../packages/pods/` — pods (GPU 编排)
- `../packages/web-ui/` — Web UI


===== FILE tom-doerr/simpledspy::CLAUDE.md | stars=114 followers=1368 lang=Python bytes=3282 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
SimpleDSPy is a lightweight wrapper around DSPy that simplifies the creation of LLM pipelines through a reflection-based API. It allows users to build complex LLM workflows with minimal boilerplate code.

## Architecture

### Core Components
- **BaseCaller** (`base_caller.py`): Foundation class for all modules, handles DSPy module initialization and invocation
- **module_caller.py**: Creates specialized callers (ChainOfThoughtCaller, ProgrammaticCaller) with automatic signature generation
- **module_factory.py**: Factory pattern for creating different types of modules
- **pipeline_manager.py**: Manages multi-step LLM pipelines with sequential module execution
- **optimization_manager.py**: Handles optimization of pipelines using DSPy teleprompters
- **evaluator.py**: Evaluation system with 1-10 scoring for optimization
- **settings.py**: Global configuration management
- **logger.py**: Optional logging system that saves training data to `.simpledspy/` directory

### Key Design Patterns
- Reflection-based API that infers variable names from calling context
- Automatic signature generation from type hints
- Factory pattern for module creation
- Pipeline pattern for chaining operations

## Development Commands

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_module_caller.py

# Run tests matching pattern
pytest -k "test_chain"

# Run with coverage
pytest --cov=simpledspy
```

### Linting & Formatting
```bash
# Format code
black .

# Check formatting
black --check .

# Type checking (optional)
mypy simpledspy
```

### Building & Publishing
```bash
# Build package
poetry build

# Publish to PyPI
poetry publish
```

### Environment Setup
```bash
# Create virtual environment and install dependencies
./setup_env.sh
```

## Testing Approach
- Unit tests for all major components using pytest
- Mock DSPy objects to test SimpleDSPy logic in isolation
- CI/CD runs tests on Python 3.9, 3.10, and 3.11
- Black formatting is enforced in CI

## Important Implementation Details

### Logging System
- When `settings.enable_logging = True`, creates `.simpledspy/` directory
- Logs are stored in `.simpledspy/logs/`
- Training data saved to `.simpledspy/training_data/`
- Each module call generates a timestamped JSON file with inputs/outputs

### Module Creation Pattern
```python
# SimpleDSPy uses reflection to infer variable names
question = "What is the capital of France?"
answer = module_caller.call_chain_of_thought()  # Automatically uses 'question' as input
```

### Pipeline Usage
```python
# Pipelines chain multiple modules
pipeline = PipelineManager()
pipeline.add_step("step1", module1)
pipeline.add_step("step2", module2)
result = pipeline.run(initial_input)
```

### Type Hints for Signatures
- When provided, type hints automatically generate DSPy signatures
- Example: `def process(text: str) -> summary: str` creates signature "text -> summary"

## CI/CD Configuration
- GitHub Actions workflow in `.github/workflows/python-package.yml`
- Runs on push to main/master and pull requests
- Tests multiple Python versions
- Enforces black formatting
- Publishes to PyPI on version tags

===== FILE mizchi/markdown.mbt::CLAUDE.md | stars=98 followers=1842 lang=MoonBit bytes=6445 =====

# MoonBit Markdown Parser

CST-based incremental Markdown parser implemented in MoonBit.

## Project Structure

```
src/
├── types.mbt                       # CST type definitions (Span, Block, Inline)
├── scanner.mbt                     # O(1) character access (Array[Char])
├── unicode.mbt                     # Shared Unicode classification helpers
├── block_parser.mbt                # Block parser dispatcher / paragraph / blockquote / thematic break
├── block_parser_heading.mbt        # ATX & setext heading parsing
├── block_parser_code.mbt           # Fenced & indented code-block parsing
├── block_parser_link_def.mbt       # Link reference & GFM footnote definitions
├── block_parser_list.mbt           # Bullet & ordered list parsing
├── block_parser_table.mbt          # GFM table parsing
├── block_parser_html.mbt           # HTML block parsing
├── block_parser_frontmatter.mbt    # YAML frontmatter parsing
├── inline_parser.mbt               # Inline parser dispatcher (single-pass)
├── inline_parser_emphasis.mbt      # `*` / `_` emphasis + strong (single-pass)
├── inline_parser_link.mbt          # Links, images, wikilinks, footnote refs
├── inline_parser_strict.mbt        # CommonMark delimiter-stack emphasis
├── incremental.mbt                 # Incremental parsing (EditInfo)
├── serializer.mbt                  # Lossless block serializer + md_parse_and_render
├── serializer_inline.mbt           # Inline serialization (text, emphasis, links, ...)
├── renderer.mbt                    # HTML renderer + md_to_html
├── renderer_autolink.mbt           # Bare-URL autolink boundary helpers
├── renderer_literal.mbt            # Source-preserving HTML renderer (block dispatch + helpers)
├── renderer_literal_inline.mbt     # Inline rendering for the literal renderer
├── plugin.mbt                      # CodeBlockInfo + RenderOptions + parse_code_block_info
├── api/                            # FFI exports for JS/WASM consumers
├── experimental/
│   ├── crdt/                       # CRDT experimental code (isolated)
│   ├── multipass/                  # Experimental multi-pass inline parser
│   ├── notebook/                   # Notebook cells / executable code blocks
│   ├── mdx/                        # MDX (JSX-in-Markdown) extraction
│   ├── slide/                      # Slide-deck splitting
│   ├── tui/                        # Terminal renderer
│   └── purify/                     # HTML sanitization
├── bench.mbt                       # Document parse/serialize/roundtrip benches
├── bench_inline.mbt                # Inline parser benches
├── bench_table.mbt                 # GFM table benches
├── bench_scanner.mbt               # Scanner / block-only benches
└── bench_incremental.mbt           # Incremental parser benches
```

## Design Philosophy

- **CST is the source of truth**: Markdown text is the serialization of CST
- **Lossless**: Preserves trivia (whitespace, newlines) and markers (`*` vs `_`)
- **Incremental**: Re-parses only changed blocks, reuses before/after

## Development Commands

```bash
moon check           # Type check
moon test            # Run all tests
moon test --target js    # Test with JS target
moon test --target wasm-gc  # Test with WASM-GC target
moon bench           # Run benchmarks
moon fmt             # Format code
```

## Development Workflow

### Test / Benchmark / Iteration Cycle

When fixing features, follow this cycle:

```bash
# 1. Verify basic behavior with main tests
moon test --target js src

# 2. Check progress with CommonMark compatibility tests
moon test --target js src/cmark_tests

# 3. Run specific category tests (e.g., code spans)
moon test --target js src/cmark_tests/code_spans_test.mbt

# 4. Run benchmarks and compare with baseline
moon bench
# Compare visually with .bench-baseline

# 5. If performance issues exist, re-test after optimization
moon test --target js src  # Verify optimization didn't break anything
moon bench                  # Confirm improvement

# 6. Update baseline (when optimization is complete)
just bench-accept
```

### CommonMark Compatibility Tests (cmark_tests)

`src/cmark_tests/` is auto-generated, **do not edit directly**.

- To add/remove test skips: Edit `SKIP_TESTS` in `scripts/gen-tests.js`
- To regenerate: `node scripts/gen-tests.js`
- Details: [CONTRIBUTING.md](./CONTRIBUTING.md)

### Performance Optimization Tips

- Use `peek_at(n)` instead of `count_char` (O(n) → O(1))
- Use bitmasks instead of arrays (avoid allocations)
- Avoid String creation inside loops

## Key Types

### Block (Block Elements)

```moonbit
pub(all) enum Block {
  Paragraph(span~, children~)           # Paragraph
  Heading(span~, level~, children~)     # Heading (h1-h6)
  FencedCode(span~, fence_char~, fence_length~, info~, code~)
  ThematicBreak(span~, marker_char~)    # ---
  BlockQuote(span~, children~)          # > Quote
  List(span~, ordered~, start~, tight~, marker_char~, items~)
  HtmlBlock(span~, content~)
  LinkRefDef(span~, label~, dest~, title~)
}
```

### Inline (Inline Elements)

```moonbit
pub(all) enum Inline {
  Text(span~, content~)                 # Text
  Code(span~, content~)                 # `code`
  Emphasis(span~, marker~, children~)   # *em* or _em_
  Strong(span~, marker~, children~)     # **strong** or __strong__
  Link(span~, children~, dest~, title~)
  Image(span~, alt~, dest~, title~)
  SoftBreak(span~)                      # Line break
  HardBreak(span~)                      # Two trailing spaces
  HtmlInline(span~, content~)
}
```

## API

```moonbit
// Parse
let doc = @markdown.parse(markdown_string)

// Serialize (lossless)
let output = @markdown.serialize(doc)
assert_eq(output, markdown_string)

// Incremental parse
let edit = EditInfo::new(change_start, change_end, new_length)
let new_doc = @markdown.parse_incremental(old_doc, new_text, edit)
```

## Performance Characteristics

| Document | Full Parse | Incremental | Speedup |
|----------|-----------|-------------|---------|
| 10 paragraphs | 68.89µs | 7.36µs | 9.4x |
| 50 paragraphs | 327.99µs | 8.67µs | 37.8x |
| 100 paragraphs | 651.14µs | 15.25µs | 42.7x |

## Reference Documentation

- [Architecture](./docs/markdown.md) - Detailed design document


===== FILE AgriciDaniel/claude-email::CLAUDE.md | stars=97 followers=2164 lang=Python bytes=4087 =====

# Claude Email — Comprehensive Email Management & Marketing

## Project Overview

This repository contains **Claude Email**, a Tier 4 Claude Code skill for inbox
management, email composition, quality review, deliverability auditing, automation
sequences, and email marketing strategy. It follows the Agent Skills open standard
and the 3-layer architecture (directive, orchestration, execution).

## Architecture

```
claude-email/
  CLAUDE.md                          # This file (project instructions)
  email/                             # Main orchestrator skill (Tier 4)
    SKILL.md                         # Entry point, routing table, user profile, quality gates
    references/                      # On-demand knowledge files (6 files)
      deliverability-rules.md       # SPF/DKIM/DMARC thresholds, bulk sender requirements
      benchmarks.md                 # KPI benchmarks by industry, scoring tables
      compliance.md                 # CAN-SPAM, GDPR, CCPA, RFC 8058
      copy-frameworks.md           # PAS, AIDA, BAB, FAB, 4Ps frameworks
      technical-standards.md        # HTML email rendering, dark mode, responsive
      mcp-integration.md           # Setup guides for Gmail, Outlook, SendGrid, etc.
  skills/                            # Sub-skills
    email-check/SKILL.md            # Inbox triage, categorization, reply suggestions
    email-write/SKILL.md            # Email composition with frameworks and templates
    email-review/SKILL.md           # Pre-send quality scoring (0-100)
    email-audit/SKILL.md            # Domain deliverability audit (SPF/DKIM/DMARC)
    email-sequence/SKILL.md         # Automation sequence designer
    email-plan/SKILL.md             # Email marketing strategy with industry templates
      assets/                       # Industry templates (local-business, saas, ecommerce, etc.)
  agents/                            # Subagent definitions
    email-deliverability.md         # Deliverability analysis agent
    email-compliance.md             # Compliance checking agent
    email-content.md                # Copy quality scoring agent
    email-inbox.md                  # Inbox categorization agent
  scripts/                           # Python execution scripts
    check_deliverability.py         # SPF/DKIM/DMARC checks via checkdmarc + dig
    analyze_email_html.py           # HTML email validation
    score_subject_line.py           # Subject line scoring algorithm
  hooks/                             # Quality gate hooks
    pre-send-check.sh              # Pre-send quality gate
    validate-email-html.py         # Post-edit HTML validation
  install.sh                         # Installation script
```

## Key Principles

1. **User Profile System**: First-run onboarding generates email-profile.md for personalized behavior
2. **MCP-First**: Integrates with Gmail/Outlook MCP for live inbox access
3. **Progressive Disclosure**: Metadata always loaded, instructions on activation, references on demand
4. **Quality Gates**: Score emails 0-100 before sending, audit domains before campaigns
5. **Industry Adaptation**: Templates and recommendations adapt to business type

## Development Rules

- Test with `python scripts/check_deliverability.py <domain> --json` after changes
- Keep SKILL.md files under 500 lines / 5000 tokens
- Reference files should be focused and under 200 lines
- Scripts must have docstrings, CLI interface, JSON output
- Follow kebab-case naming for all skill directories

## Commands

| Command | Purpose |
|---------|---------|
| `/email` | Interactive mode with inbox summary or menu |
| `/email check` | Inbox triage and reply suggestions |
| `/email write` | Compose emails with frameworks |
| `/email review` | Pre-send quality scoring |
| `/email audit <domain>` | Deliverability and compliance audit |
| `/email sequence <type>` | Design automation sequences |
| `/email plan <business>` | Email marketing strategy |

## MCP Dependencies

- **Required**: Gmail MCP (taylorwilsdon/google_workspace_mcp)
- **Optional**: Microsoft 365, SendGrid, Mailchimp, Kit.com


===== FILE captainsafia/grove::AGENTS.md | stars=82 followers=2890 lang=Rust bytes=7243 =====

Instructions for coding agents working on the Grove repository.

## Project Overview

Grove is a CLI tool written in Rust that manages Git worktrees. It targets Linux, macOS, and Windows platforms.

**Key technologies:**
- Language: Rust (2021 edition)
- CLI Framework: clap (derive macros)
- Git Operations: git CLI shell-outs via `std::process::Command`
- Terminal UI: dialoguer (fuzzy-select), colored
- Serialization: serde, serde_json
- Testing: Rust's built-in test framework (`cargo test`)

## Repository Structure

```
src/
├── main.rs               # CLI entry point, clap command registration
├── models.rs             # Worktree struct, option types
├── utils.rs              # Helper functions (discovery, formatting, config)
├── commands/             # One file per CLI command
│   ├── mod.rs
│   ├── add.rs
│   ├── go.rs
│   ├── init.rs
│   ├── list.rs
│   ├── pr.rs
│   ├── prune.rs
│   ├── remove.rs
│   ├── self_update.rs
│   ├── shell_init.rs
│   └── sync.rs
└── git/
    ├── mod.rs
    └── worktree_manager.rs  # Core Git worktree operations

test/
└── integration/          # Hone integration tests

site/                     # GitHub Pages website
├── index.html            # Landing page
└── install.sh            # Installation script
```

## Development Commands

```bash
# Build debug binary
cargo build

# Build optimized release binary
cargo build --release

# Run directly in development
cargo run -- <command>

# Type check without building
cargo check

# Run all tests
cargo test

# Clean build artifacts
cargo clean
```

Always run `cargo check` and `cargo test` before committing changes.

## Updating Documentation

### README.md

The README at the repository root is the primary documentation. When updating:

1. Keep the existing section structure:
   - Features
   - Installation
   - Quick Start
   - Commands (with examples)
   - Development

2. When adding a new command:
   - Add it to the Commands section with usage syntax and examples
   - Include all flags/options with descriptions
   - Show realistic example output if helpful

3. When changing command behavior:
   - Update the corresponding command documentation
   - Update any affected examples

### Site Documentation (site/)

The `site/` directory contains the GitHub Pages website. The `site/index.html` file is a standalone HTML page with embedded CSS.

When updating site documentation:

1. **Keep README and site in sync** - The site mirrors the README content. If you update README command documentation, update `site/index.html` to match.

2. **Maintain the HTML structure** - The site uses semantic HTML sections:
   - Hero section with tagline
   - Installation section
   - Commands/usage section

3. **Test locally** - Open `site/index.html` in a browser to verify changes render correctly.

4. **Deployment** - The site auto-deploys via GitHub Actions when changes to `site/` are pushed to main.

### install.sh

The `site/install.sh` script is the curl-pipe-bash installer. When modifying:

- Test the script thoroughly on both Linux and macOS
- Maintain support for both x64 and arm64 architectures
- Keep error handling and user feedback intact

## Commit Message and PR Title Format

This repository uses [Conventional Commits](https://www.conventionalcommits.org/). All commit messages and PR titles must follow this format:

```
<type>: <subject>
```

### Types

| Type    | Use For                                           |
|---------|---------------------------------------------------|
| `feat`  | New features or functionality                     |
| `fix`   | Bug fixes                                         |
| `chore` | Build, CI/CD, dependencies, maintenance           |
| `test`  | Adding or updating tests                          |
| `doc`   | Documentation only changes                        |

### Rules

1. **Use lowercase** for type and subject
2. **No period** at the end of the subject
3. **Use imperative mood** ("add" not "added" or "adds")
4. **Keep subject under 72 characters**
5. **Reference PR number** when applicable: `(#123)`
6. **Use the same Conventional Commit format for PR titles**

### Examples

```
feat: add support for branch tracking in add command
fix: handle missing git config gracefully
chore: update dependencies to latest versions
test: add edge case tests for prune command
doc: update readme with new installation method
fix: address edge cases in worktree detection (#17)
chore: add notarization for macos binaries (#15)
```

### Multi-line Commits

For complex changes, add a body separated by a blank line:

```
feat: add self-update command

Allows users to update grove to the latest version or a specific
version directly from the CLI. Supports installing PR preview builds
with the --pr flag.
```

## Code Conventions

### Command Files

Each command in `src/commands/` is implemented as a public function that takes parsed arguments and executes the command logic. Commands are registered in `src/main.rs` using clap's derive macros:

```rust
// In src/main.rs
#[derive(Subcommand)]
enum Commands {
    /// Short description of command
    Example {
        /// Argument description
        name: String,
        /// Flag description
        #[arg(short, long)]
        flag: bool,
    },
}
```

Command implementations live in their respective files under `src/commands/`:

```rust
// In src/commands/example.rs
pub fn execute(name: &str, flag: bool) -> Result<(), Box<dyn std::error::Error>> {
    // Implementation
    Ok(())
}
```

### WorktreeManager

Git operations go through `src/git/worktree_manager.rs`. This module uses `std::process::Command` to shell out to the `git` CLI. Extend this module when adding new Git functionality rather than calling git directly in commands.

### Error Handling

Use the utility functions from `src/utils.rs`:

```rust
use crate::utils::{format_error, format_warning};

println!("{}", format_error("Something went wrong"));
println!("{}", format_warning("Proceed with caution"));
```

### Rust

- Edition 2021
- Define shared types in `src/models.rs`
- Use explicit return types for public functions
- Use `#[cfg(test)]` modules for inline unit tests

### Testing

- Unit tests are inline `#[cfg(test)]` modules in the source files they test
- Integration tests are in `test/integration/` (Hone test files)
- Run all tests with `cargo test`

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_something() {
        assert_eq!(result, expected);
    }
}
```

## CI/CD

- **CI runs on all PRs**: Type check (`cargo check`), tests (`cargo test`), and build verification (`cargo build --release`)
- **Releases trigger on tags**: Version tags like `v1.0.0` create releases with cross-compiled binaries
- **PR builds**: Each PR gets preview builds for Linux (x64, arm64) and macOS (x64, arm64) with download links posted as comments

## Platform Support

Grove supports:
- Linux (x64, arm64)
- macOS (x64, arm64)
- Windows (x64)

Prefer cross-platform implementations when adding features, and avoid Unix-only command assumptions in user-facing workflows.


===== FILE sergiodxa/remix-v3-demo::AGENTS.md | stars=64 followers=2207 lang=TypeScript bytes=2454 =====

Default to using Bun instead of Node.js.

- Use `bun <file>` instead of `node <file>` or `ts-node <file>`
- Use `bun test` instead of `jest` or `vitest`
- Use `bun build <file.html|file.ts|file.css>` instead of `webpack` or `esbuild`
- Use `bun install` instead of `npm install` or `yarn install` or `pnpm install`
- Use `bun run <script>` instead of `npm run <script>` or `yarn run <script>` or `pnpm run <script>`
- Bun automatically loads .env, so don't use dotenv.

## APIs

- `Bun.serve()` supports WebSockets, HTTPS, and routes. Don't use `express`.
- `bun:sqlite` for SQLite. Don't use `better-sqlite3`.
- `Bun.redis` for Redis. Don't use `ioredis`.
- `Bun.sql` for Postgres. Don't use `pg` or `postgres.js`.
- `WebSocket` is built-in. Don't use `ws`.
- Prefer `Bun.file` over `node:fs`'s readFile/writeFile
- Bun.$`ls` instead of execa.

## Testing

Use `bun test` to run tests.

```ts#index.test.ts
import { test, expect } from "bun:test";

test("hello world", () => {
  expect(1).toBe(1);
});
```

## Frontend

Use HTML imports with `Bun.serve()`. Don't use `vite`. HTML imports fully support React, CSS, Tailwind.

Server:

```ts#index.ts
import index from "./index.html"

Bun.serve({
  routes: {
    "/": index,
    "/api/users/:id": {
      GET: (req) => {
        return new Response(JSON.stringify({ id: req.params.id }));
      },
    },
  },
  // optional websocket support
  websocket: {
    open: (ws) => {
      ws.send("Hello, world!");
    },
    message: (ws, message) => {
      ws.send(message);
    },
    close: (ws) => {
      // handle close
    }
  },
  development: {
    hmr: true,
    console: true,
  }
})
```

HTML files can import .tsx, .jsx or .js files directly and Bun's bundler will transpile & bundle automatically. `<link>` tags can point to stylesheets and Bun's CSS bundler will bundle.

```html#index.html
<html>
  <body>
    <h1>Hello, world!</h1>
    <script type="module" src="./frontend.tsx"></script>
  </body>
</html>
```

With the following `frontend.tsx`:

```tsx#frontend.tsx
import React from "react";

// import .css files directly and it works
import './index.css';

import { createRoot } from "react-dom/client";

const root = createRoot(document.body);

export default function Frontend() {
  return <h1>Hello, world!</h1>;
}

root.render(<Frontend />);
```

Then, run index.ts

```sh
bun --hot ./index.ts
```

For more information, read the Bun API docs in `node_modules/bun-types/docs/**.md`.


===== FILE doggy8088/Paste-to-Markdown::AGENTS.md | stars=64 followers=4519 lang=JavaScript bytes=8092 =====

# Agent Guide: Paste-to-Markdown

This repository contains a simple, client-side web application for converting clipboard content (HTML/RTF/Text) to Markdown. It is built using vanilla JavaScript, HTML, and CSS.

## Project Structure

- `index.html`: The main entry point and UI structure.
- `assets/`:
  - `clipboard2markdown.js`: Main application logic, handles paste events and UI updates.
  - `to-markdown.js`: Custom conversion logic and utilities.
  - `bootstrap.css`: Styling (Bootstrap 3 based).
- `vendor/`: Third-party libraries (Turndown, Marked, GFM plugin).
- `assets/background.svg`: Background image for the application.

## Build, Lint, and Test Commands

Currently, this project does **not** use a package manager (npm/yarn) or a build system.

- **Build**: No build step is required. Changes to JS/CSS/HTML are reflected immediately upon browser refresh.
- **Lint**: No automated linter is configured. Adhere to existing styles.
- **Test**: No automated tests exist.
  - **Manual Testing**: Open `index.html` in a browser and test different clipboard sources (Web, VS Code, Word, Excel, Plain Text).
  - **Single Test**: To test a specific conversion rule, you can use the browser console to call `turndownService.turndown(html)` or `convert(html)`.

## Code Style Guidelines

### General
- Use `'use strict';` inside all JS files.
- Wrap scripts in an Immediately Invoked Function Expression (IIFE) to avoid global namespace pollution.
- Indentation: **2 spaces**.
- Semicolons: **Always use semicolons**.
- Line length: Aim for a reasonable line length (under 100-120 characters).

### Imports and Dependencies
- Dependencies are managed manually in the `vendor/` directory.
- Add new scripts to `index.html` before the application scripts.
- Order of scripts:
  1. Vendor libraries (Turndown, Marked, etc.)
  2. Custom utilities (`to-markdown.js`)
  3. Main application logic (`clipboard2markdown.js`)
- Prefer vanilla JS over adding new libraries.

### Variables and Types
- Prefer `const` for constants and `let` for variables.
- Avoid using `var` for new code to prevent hoisting issues and ensure block scoping.
- This is a non-TypeScript project; use JSDoc comments for complex function signatures or object structures.
- Use descriptive variable names that reflect the data they hold.

### Naming Conventions
- Variables and functions: `camelCase` (e.g., `updatePreview`, `isSafeUrl`).
- Global constants: `SCREAMING_SNAKE_CASE` (though few are currently used).
- DOM elements: Use descriptive names (e.g., `pastebin`, `output`, `preview`).
- CSS classes: Kebab-case (e.g., `tab-button`, `tab-content`).
- Event handlers: Inline functions or clearly named functions like `handlePaste`.

### DOM Manipulation
- Use `document.querySelector` and `document.querySelectorAll` for selecting elements.
- Use `addEventListener` for event handling instead of `onEvent` properties.
- Use `classList.add`, `classList.remove`, and `classList.toggle` for managing CSS classes.
- Avoid inline event handlers in HTML.

### Error Handling
- Use `try...catch` blocks for operations that might fail (e.g., parsing HTML or complex regex operations).
- Provide fallback values or silent failures for non-critical features.
- Log errors to the console for debugging during development.

### Security
- **XSS Prevention**: When rendering Markdown to the preview, use the `sanitizeHtml` function.
- The `sanitizeHtml` function uses `DOMParser` to parse HTML safely and removes `<script>` tags.
- It also validates URLs in `<a>` and `<img>` tags using `isSafeUrl`.
- **URL Validation**: `isSafeUrl` blocks `javascript:`, `data:`, and other dangerous protocols.
- **Bootstrap Integration**: The sanitizer also adds Bootstrap classes (`table-striped`, `img-responsive`, etc.) to the rendered HTML to ensure consistent styling.
- Never use `innerHTML` with unsanitized user input.

## Key Implementation Details

### Paste Handling
The application listens for `paste` events on a hidden `contenteditable` div (`#pastebin`). It prioritizes clipboard types in this order:
1. `vscode-editor-data`: Handles VS Code code snippets. It extracts `text/plain` and removes the minimum common leading indentation from all lines to keep the code clean.
2. `text/rtf` + `text/html`: Used for content from Microsoft Word, Outlook, or Rich Text editors. Includes specific fixes for common RTF-to-HTML conversion artifacts like bullet point characters (e.g., `ü`).
3. `text/plain` (only if `text/html` is missing): Applies custom `plainTextRules` to identify and format specific text patterns (like Copilot CLI output).
4. `text/html`: Standard web content conversion. It pre-processes the HTML to remove unnecessary tags (like `<p>` inside `<li>`) and normalize line breaks from sources like Excel.

### Markdown Conversion Logic
Conversion is primarily handled by `TurndownService` with the GFM tables plugin.
- **Custom Rules**: Added via `turndownService.addRule` in `assets/clipboard2markdown.js`.
  - `brInTableCell`: Preserves `<br>` inside table cells, as many Markdown flavors (like GFM) support them for multi-line cells.
  - `pandoc`: A collection of rules for Pandoc-style Markdown features:
    - `^sup^` for superscripts.
    - `~sub~` for subscripts.
    - `atx` style headings (`# H1`, `## H2`).
    - Smart punctuation conversion.
- **Smart Punctuation**: The custom `escape` function handles:
  - Converting curly quotes (`“”`, `‘’`) to straight quotes.
  - Normalizing various dash types (`–`, `—`) to Markdown dashes.
  - Converting ellipses (`…`) to triple dots.
  - Cleaning up trailing whitespace and excessive newlines.

### Preview and Theming
- **Marked**: Used to render the Markdown back to HTML in the "Preview" tab.
- **Sanitization**: All output from `marked.parse()` MUST pass through `sanitizeHtml()`.
- **Theming**:
  - UI components use Bootstrap 3 classes.
  - Dark Mode: Supports `prefers-color-scheme: dark` via CSS media queries. The background image changes to `background-dark.svg`, and colors are adjusted for readability.

## Workflow for Agents

### Adding a New Conversion Rule
1. Open `assets/clipboard2markdown.js`.
2. Locate the `turndownService.addRule` calls or the `pandoc` array.
3. Define a new rule with:
   - `filter`: A string (tag name), array of strings, or a function that returns true for matching nodes.
   - `replacement`: A function that returns the Markdown string for that node.
4. If it's a plain text rule (for when no HTML is available), add it to the `plainTextRules` object with a detection function and a transformation function.

### Modifying the UI
1. Edit `index.html` for HTML structure changes.
2. Update the `<style>` block in `index.html` for CSS changes.
3. For theme-specific changes, ensure you update the `@media (prefers-color-scheme: dark)` section.
4. If adding new tabs, update the tab switching logic in `assets/clipboard2markdown.js`.

### Common Tasks and Troubleshooting
- **Fixing Table Alignment**: Check `turndown-plugin-gfm.js` and the `tr` rule in `clipboard2markdown.js`.
- **Handling New Clipboard Sources**: Log `event.clipboardData.types` in the `paste` event handler to see what formats the new source provides.
- **Regex Debugging**: When adding regex-based cleanup in `escape()` or `plainTextRules`, use non-greedy matches where appropriate and test with varied input.

### Verification and Testing
Since there are no automated tests:
1. Open `index.html` in a local browser (Chrome/Edge/Firefox).
2. Copy content from various sources:
   - Web pages (tables, lists, headings).
   - VS Code (code blocks).
   - Microsoft Word (formatted text, lists).
   - Excel (tables).
   - Copilot CLI or other terminal outputs.
3. Paste into the app and verify the Markdown output in the "Edit" tab.
4. Switch to the "Preview" tab to ensure it renders correctly, follows Bootstrap styling, and is properly sanitized.
5. Check the browser console for any errors or "Matched" logs from `plainTextRules`.

---
*Note: This file is intended for agentic consumption. Keep it updated as the project evolves.*


===== FILE Eldergenix/Durable-agent-harness::AGENTS.md | stars=55 followers=1281 lang=Python bytes=9480 =====

# AGENTS.md — Operating manual for agents in this repo

You are working on **durable-agent-harness (`dah`)**: a research harness for long-horizon
agents (verification loops, checkpoint/rollback, budget-aware planning, failure recovery)
plus an **ablatable memory system** evaluated on multi-session tasks. The deliverable is
reproducible evidence, judged by agent engineers at labs. Honest negative results are wins.

## Read order (once per session)

1. `GOAL.md` — mission, pre-declared hypotheses H1–H5, frozen metric definitions, Definition of Done.
2. `RULES.md` — non-negotiables R1–R15 and which machine enforces each.
3. `FEATURES.md` — what exists vs. what's planned (includes tracked known gaps).
4. `TASKS.md` — the ordered plan; find the first unblocked `[ ]` task in the active milestone.
5. `docs/JOURNAL.md` — what the last session did and what it left for you.

## Ground truth commands

```bash
source .venv/bin/activate                     # Python 3.11 venv at repo root
python scripts/quality_gate.py --fast         # lint + compile + governance tests (~seconds)
python scripts/quality_gate.py --strict       # + full pytest, import checks, results integrity
python scripts/rules_lint.py                  # just the rule checks, verbose per-rule output
pytest -q                                     # full test suite
dah-baseline / dah-ablation / dah-analyze     # experiment CLIs (M3+; console scripts from pyproject)
```

The **fast gate green** is the precondition for saying "done" on anything (R15) — the
`stop` hook runs it and will bounce you back if it's red. The **strict gate** closes
milestones.

## Repo map

```
src/dah/
  types.py            # Fact/Turn/Task/ContextItem/AssembledContext — shared data model
  budget.py           # Budget: hard charge + soft pressure() in [0,1]; no refunds ever
  checkpoint.py       # Checkpointer over Snapshotable components; deep, total snapshots
  telemetry.py        # Trace.emit — the ONLY way library code reports what happened
  verifier.py         # oracle-free ConsistencyVerifier -> Verdict (empty-recall, low-relevance)
  recovery.py         # RecoveryPolicy: ingestion retries + rollback-before-retry
  planner.py          # StaticPlanner vs BudgetAwarePlanner (allocation, focused retries)
  faults.py           # seeded FaultInjector — own RNG stream, rate 0 == no injector
  agents.py           # one toggleable Agent loop; BaselineAgent vs HarnessAgent configs
  memory/
    stores.py         # WorkingMemory / Compactor / EpisodicStore / SemanticStore
    manager.py        # MemoryConfig + MemoryManager + 10 PRESETS — the ablation surface
  env/
    tasks.py          # synthetic multi-session task generator (owns ground truth)
    multisession.py   # MultiSessionEnv — sole grader; frozen metrics on EpisodeResult
  providers/
    base.py           # Provider protocol + ModelResponse
    simulated.py      # deterministic context-degradation model (length decay × middle loss)
    openai_compat.py  # optional live-LLM adapter; sole sanctioned network egress (R2)
  experiments/
    config.py         # single source of truth for every number in RESULTS.md
    runner.py         # config -> tidy DataFrame studies; paired bootstrap (R4)
    run_ablation.py   # dah-ablation: memory matrix + noise/fill sweeps
    run_baseline.py   # dah-baseline: harness ladder + budget/tau/recovery studies
    analyze.py        # dah-analyze: figures + hypotheses.csv verdicts + summary.md
    gallery.py        # results/traces.md — three annotated, seed-reproducible episodes
    live_check.py     # manual live-endpoint smoke test (needs OPENAI_API_KEY)
scripts/              # rules_lint.py, quality_gate.py (governance machinery)
tests/                # pytest; test_governance.py enforces R5/R6/R7/R1 + hook behavior
results/              # GENERATED ONLY — never hand-edit (R3); `make reproduce` rebuilds all
docs/                 # DESIGN.md (methodology), RESULTS.md (findings), JOURNAL.md (log)
.cursor/hooks*        # guardrails — do not weaken without user approval (R13)
```

## Architecture invariants (violating these invalidates the science)

1. **The env owns truth.** Only `env/` and `experiments/` may read `required_fact_ids` or
   grade. Memory/planner/verifier/recovery must never see the answer key (R5 — the linter
   greps for the tokens; don't alias them to sneak past it, the test suite also checks
   behaviorally).
2. **The provider is blind.** `SimulatedProvider` rolls recall for every fact in context;
   it cannot favor required facts. A fact absent from assembled context has recall
   probability 0 — that asymmetry is what makes memory load-bearing.
3. **Same degradation model for every arm.** Memory policies win by *placing the right
   facts at accessible positions under a token budget*, never by changing accessibility
   parameters. If an experiment varies `AccessibilityParams`, it's a sweep axis, applied
   identically to all arms.
4. **Determinism end to end (R1).** Seeds in, identical bytes out. Every RNG is an
   explicitly seeded `np.random.default_rng`; RNG state goes into snapshots (copy the
   `Compactor` pattern: `self.rng.bit_generator.state` in `snapshot()`/`restore()`).
5. **Rollback restores state, not budget (R7).** Retries are paid for. This is the tension
   that makes budget-aware planning a real subject, so never "fix" it.
6. **Paired everything (R4).** Seed `i` = same task for every arm. Deltas get paired
   bootstrap CIs (≥ 10k resamples, seeded). ≥ 20 seeds/arm, default 30.

## Working style

- **One task at a time**, from `TASKS.md`, respecting milestone order. Mark it `[~]` when
  you start, `[x]` when the acceptance criteria hold and the fast gate is green.
- **Tests land with code (R11).** New module ⇒ new tests in the same change. The linter
  only checks a reference exists; you are responsible for the tests being real.
- **Sync the docs you touched (R12).** Feature reality changed ⇒ FEATURES.md row updated
  (status + evidence). New scope discovered ⇒ new task ID in TASKS.md.
- **Journal before you stop (R14).** Append to `docs/JOURNAL.md`: date, task IDs, what
  changed, evidence (gate/test output, result files), next step. Record dead ends — a
  failed approach is data the next session needs.
- **Experiments are code.** Change an experiment ⇒ regenerate its `results/` artifacts via
  the CLI; never edit CSVs (the results hook denies it) and never cherry-pick seeds
  (R3 — that's falsification).
- Python ≥ 3.10, 4-space indent, type hints on public APIs, `from __future__ import
  annotations` everywhere, docstrings that explain *why* (R10). No `print` in library code
  — `Trace.emit` (R9). No `pickle`/`eval`/`exec` (R8). No network in `src/dah/` except
  `providers/openai_compat.py` (R2).
- Dependencies: numpy/matplotlib/pandas (+pytest dev). Adding anything else needs a
  written rationale in the PR/journal and user approval.

## Guardrails you will encounter (don't fight them, don't weaken them)

| Trigger | Hook | What happens |
|---------|------|--------------|
| Editing GOAL.md / RULES.md / hooks / linter / gate / .githooks | `protect-governance.sh` (preToolUse) | **Denied** — propose the change to the user; they apply it or lift the guard (R13) |
| Editing `results/*` with any editor tool | `protect-governance.sh` (preToolUse) | **Denied** — regenerate via `make reproduce` (R3) |
| `git commit --no-verify`, force-push, `rm -rf` at dangerous paths | `shell-guard.sh` (beforeShellExecution) | **Denied** outright (R15) |
| `git config` writes, shell redirection into `results/`, sed -i on governance files | `shell-guard.sh` | **Approval card** shown to the user |
| Any Python edit under `src/`, `scripts/`, `tests/` | `lint-context.sh` (postToolUse) | Runs the rules linter; violations injected back as context |
| Declaring completion with a dirty tree | `stop-quality.sh` (stop, loop_limit 3) | Runs the fast gate; red gate bounces the completion; green-but-unjournaled code bounces once for R14 |

If a guardrail seems wrong, propose an amendment (RULES.md § Amendment protocol) — never
route around it. Weakening enforcement silently is the one unforgivable move in this repo.

## Current state & first moves (as of M4 complete)

- M0–M4 closed (incl. the T4.2 robustness re-run); the strict gate is green; all studies
  are generated and `docs/RESULTS.md` carries machine-computed H1–H5 verdicts (H1
  directional, H4 refuted-opposite — reported honestly in "What didn't work"). See
  `docs/JOURNAL.md` for session history, including discarded designs.
- Open items in order: stretch **T5.2** (live-LLM spot check, needs `OPENAI_API_KEY`),
  **T5.3** (`gap_triggered` policy: measure it or delete it), **T5.4** (`v0.1.0` tag —
  needs explicit user approval; no commits without it).
- If you change *any* experiment or provider/memory behavior, regenerate all of
  `results/` via `make reproduce` before touching RESULTS.md — numbers in docs must
  never drift from artifacts (R3/R12). FEATURES.md "Known gaps" lists the three
  tracked gaps; never re-litigate closed hypotheses without new runs.

## Definition of Done (summary — full version in GOAL.md)

Strict gate green; one-command regeneration of all results; RESULTS.md with H1–H5 verdicts
+ CIs + "What didn't work"; every FEATURES.md row `verified` with live evidence; a stranger
reproduces the headline number from README alone.


===== FILE luizomf/vps_deploy_template::AGENTS.md | stars=53 followers=9183 lang=Shell bytes=4264 =====

# AGENTS

This document keeps future collaborators aligned on the goals, guardrails, and
deployment story of this repo.

## Mission

- This project serves as a **production-ready template** for students deploying
  Python applications on a VPS (specifically Hostinger KVM 2).
- It is the core artifact for a video tutorial series. The goal is to provide a
  "win-win-win" scenario: students get a robust starting point, the sponsor gets
  visibility, and the author provides supported, high-quality content.
- The repository is designed to be forked. It provides a full CI/CD pipeline
  bridging a local development environment with a hardened production server.

## Infrastructure Snapshot

- **Provider:** Hostinger KVM 2 VPS.
- **OS:** Ubuntu 24.04 LTS (with Docker pre-installed).
- **Network:** Ports 22 (SSH), 80 (HTTP), 443 (HTTPS) open.
- **User:** `<deploy-user>` (primary administrative user, used for deployment).
- **Directories:**
  - Project root: `/dockerlabs`
  - Persistent data: Managed via `data_vol` container and bind mounts.

## Architecture & Services

The stack is composed of Docker containers orchestrated via `compose.yaml`:

1.  **`dockerlabs` (App):**
    - Python/FastAPI application.
    - Serves the main application logic.
    - **Crucial:** Exposes `/webhook/github` endpoint to trigger deployments.
2.  **`nginx`:**
    - Reverse proxy handling SSL termination and routing.
    - Serves static assets and forwards traffic to `dockerlabs`.
3.  **`certbot`:**
    - Obtains and renews Let’s Encrypt certificates.
    - Shares volumes with NGINX for challenge response and cert storage.
4.  **`data_vol`:**
    - A lightweight container used solely for initializing and sharing volumes
      between containers and the host.

## Deployment Workflow

The deployment model has shifted from a "Push via SSH" model to a **"Signal &
Pull"** model to improve security and decoupling.

1.  **Trigger (GitHub):**
    - Developer pushes to `main`.
    - GitHub Actions builds the image and pushes it to GHCR.
    - GitHub Actions sends a POST request to the production URL
      `/webhook/github`.

2.  **Signal (App):**
    - `dockerlabs` app receives the webhook.
    - Verifies the `X-Hub-Signature-256` using `GITHUB_WEBHOOK_SECRET`.
    - If valid, it creates a timestamped file in the shared volume
      `/data/webhook_jobs`.

3.  **Execution (Watcher):**
    - A systemd service (`webhook-watcher`) running on the host checks for files
      in `/dockerlabs/data/webhook_jobs` (via `data_vol`).
    - Upon detection, it triggers `data/scripts/deploy`.

4.  **Update (Script):**
    - `data/scripts/deploy`:
      1.  Backs up volumes.
      2.  `git fetch/reset` to match `origin/main` (if in production).
      3.  `docker compose pull` & `up -d`.
      4.  Prunes old images.

## Server & Security Ground Rules

- **Access:** SSH Keys only. Password authentication is disabled.
- **Firewall:** `ufw` enabled, allowing only SSH, HTTP, and HTTPS.
- **Fail2Ban:** Configured to jail repeated failed SSH login attempts.
- **Permissions:**
  - Project directory `/dockerlabs` is owned by `<deploy-user>:<deploy-user>` with
    setgid (`chmod g+s`).
  - `webhook-watcher` runs as `<deploy-user>`.
- **Secrets:**
  - Managed via `.env` file (not committed).
  - `GITHUB_WEBHOOK_SECRET` must match between `.env` and GitHub Repository
    Secrets.

## Contribution Guidelines

- **Educational Value First:** Changes should be intelligible to students. Avoid
  over-engineering if a simpler solution exists.
- **Idempotency:** Scripts like `bootstrap` and `deploy` must be safe to run
  multiple times without breaking the state.
- **Configuration:**
  - `CURRENT_ENV` variable in `.env` controls behavior (e.g., generating dummy
    certs in `development` vs. real certs in `production`).
  - Always update `.env.example` if adding new environment variables.
- **Documentation:** Infra changes must be reflected in `README.md`. It serves
  as the script for the video tutorial.

## Quick Reference

- **Main Command:** `docker compose up -d --build` (Local dev).
- **Deploy Script:** `/dockerlabs/data/scripts/deploy`.
- **Watcher Service:** `sudo systemctl status webhook-watcher`.
- **Logs:** `sudo journalctl -u webhook-watcher -f`.



===== FILE schacon/slidetty::CLAUDE.md | stars=45 followers=14216 lang=Go bytes=2677 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Slidetty is a TUI (Terminal User Interface) slideshow application built in Go using the Bubble Tea framework. It renders markdown slides with beautiful styling via Glamour and provides an intuitive presentation interface.

## Architecture

### Core Components
- **Single File Architecture**: The entire application is contained in `main.go` (~255 lines)
- **Bubble Tea Model**: Uses the Model-View-Update (MVU) pattern via `github.com/charmbracelet/bubbletea`
- **Markdown Rendering**: Powered by `github.com/charmbracelet/glamour` with auto-styling
- **Progress Bar**: Animated gradient progress bar using `github.com/charmbracelet/bubbles/progress`
- **Styling**: UI styling via `github.com/charmbracelet/lipgloss`

### Key Data Structures
- `model` struct contains slides array, current slide index, glamour renderer, progress bar, window dimensions, and title
- Slide loading is asynchronous using Tea's command pattern (`loadSlides()` function)
- Window size changes trigger renderer updates with dynamic word wrapping

## Development Commands

### Build
```bash
go build -o slidetty main.go
```

### Run
```bash
./slidetty
```

### Install Dependencies
```bash
go mod download
```

### Clean Build
```bash
rm -f slidetty && go build -o slidetty main.go
```

## Slide Management

### Slide Directory Structure
- All slides live in `slides/` directory
- Regular slides: `##-name.md` (e.g., `01-welcome.md`, `02-navigation.md`)
- Special files:
  - `_title.md`: Contains presentation title (appears in status bar)
  - `_author.md`: Author information (not currently used by app)
  - Files starting with `_` are excluded from slide sequence

### Slide Loading Logic
- Slides are loaded alphabetically by filename
- Only `.md` files are processed
- Files beginning with underscore are skipped in main sequence
- Content is read into memory at startup

## Key Navigation
- `→` or `l`: Next slide
- `←` or `h`: Previous slide
- `q` or `Ctrl+C`: Quit application

## UI Layout
- **Content Area**: Dynamically sized based on terminal dimensions
- **Status Bar**: Shows "Slide X/Y" and presentation title with blue background
- **Progress Bar**: Animated gradient bar at bottom showing presentation progress
- **Responsive**: Word wrapping and layout adjust to terminal size changes

## Dependencies
The application uses several Charm libraries:
- `bubbletea`: TUI framework and MVU architecture
- `glamour`: Markdown rendering with syntax highlighting
- `lipgloss`: Styling and layout
- `bubbles/progress`: Animated progress bar component

===== FILE DanWahlin/ai-agent-board::AGENTS.md | stars=42 followers=5186 lang=TypeScript bytes=10952 =====

# AGENTS.md

## Project Overview

Agentic AI Kanban Board — a drag-and-drop Kanban board that delegates coding tasks to AI coding agents (GitHub Copilot, Claude Code, OpenAI Codex, OpenCode, Hermes, OpenClaw). Monorepo with npm workspaces.

## Architecture

```
ai-agent-board/
├── packages/
│   ├── client/          # React 19 + Vite + Tailwind 4 + Framer Motion + xterm.js
│   │   └── src/
│   │       ├── components/  # Board, Column, TaskCard, TaskGroupCard, GroupPanel, AgentPanel, TerminalView, FilterChips, Header, dialogs
│   │       ├── hooks/       # useTasks, useTaskGroups, useTheme, useDebounce, useKeyboardShortcuts
│   │       ├── lib/         # api.ts (REST + WebSocket), agent-config.ts, priority-config.ts, columns.ts, utils
│   │       └── types/       # Client-side type re-exports
│   ├── server/          # Express + @codewithdan/agent-sdk-core + better-sqlite3/pg + ws
│   │   └── src/
│   │       ├── middleware/  # auth.ts (Bearer token auth)
│   │       ├── routes/      # tasks.ts, agent.ts, git.ts, templates.ts, groups.ts, helpers.ts
│   │       ├── services/    # agent-manager.ts (session orchestration, event caching)
│   │       ├── repositories/# sqlite.ts, postgres.ts, sqlite-templates.ts, postgres-templates.ts, sqlite-groups.ts, postgres-groups.ts, types.ts, template-types.ts, group-types.ts
│   │       ├── db.ts        # SQLite + PostgreSQL init + migrations
│   │       ├── websocket.ts # WebSocket broadcast
│   │       └── index.ts     # Express app setup + graceful shutdown
│   └── e2e/             # Playwright tests
├── shared/              # Shared types (Task, TaskGroup, TaskTemplate, AgentEvent, ColumnId, AgentType, etc.) + validation constants
├── scripts/             # required gate, hook install, and E2E process helpers
└── k8s/                 # Kubernetes manifests (namespace, deployments, services, ingress)
```

## Key Technical Decisions

- **Multi-agent support** — pluggable `AgentProvider`/`AgentSession` interfaces from `@codewithdan/agent-sdk-core`. Six providers: `copilot` (`@github/copilot-sdk`), `claude` (`@anthropic-ai/claude-agent-sdk`), `codex` (`@openai/codex-sdk`), `opencode` (`@opencode-ai/sdk`), `hermes`, and `openclaw`. Auto-detected at startup via `detectAgents()`.
- **Agent SDK abstraction** — all provider implementations live in the external `@codewithdan/agent-sdk-core` package. The server imports providers and the detection function from this package.
- **Dual database backends** — SQLite via `better-sqlite3` (default, zero config) or PostgreSQL via `pg` (set `DATABASE_URL`). Both implement the `TaskRepository` and `TemplateRepository` interfaces.
- **Route splitting** — REST API is split across `tasks.ts` (CRUD), `agent.ts` (start/stop/events/follow-up), `git.ts` (merge-local, create-pr, worktree cleanup, git-info), `templates.ts` (task template CRUD), and `groups.ts` (group CRUD + run/stop/archive).
- **API key auth** — optional Bearer token via `API_KEY` env var. When set, all API and WebSocket requests require `Authorization: Bearer <key>`. Middleware in `middleware/auth.ts`.
- **Task Groups** — parent entity with N child tasks, concurrency-controlled execution via `GroupQueue` in agent-manager. Groups move as a single card on the board; auto-advance to review when all children complete. Parallelism slider locked once running.
- **Event streaming** — SDK events mapped to `AgentEvent`s, persisted to database, broadcast via WebSocket. In-memory LRU cache (200 tasks max, 100 events per task).
- **Git worktrees** — optional per-task branch isolation. Agent works in worktree directory, path rewriting via `onPreToolUse` hook. Worktrees auto-cleaned after successful merge or PR creation.
- **Local merge** — `mergeLocal()` merges worktree branch into base branch locally with per-repo mutex to prevent concurrent checkout races. Auto-aborts on conflict.
- **Smart PR/merge buttons** — `GET /api/tasks/:id/git-info` checks for remote; UI shows "Create PR" only when remote exists, "Merge to main" always available.
- **Vite proxy** — client proxies `/api` and `/ws` to the server.
- **Shared validation** — `shared/constants.ts` exports validators (`isValidPriority`, `isValidColumnId`, etc.) and limits (`MAX_TITLE_LENGTH`, `MAX_DESCRIPTION_LENGTH`) used by both client and server.

## Running Locally

```bash
npm install
npm run dev:server   # Terminal 1 — port 3001
npm run dev:client   # Terminal 2 — port 4175
```

## Production (systemd)

The production server (`kanban.codewithdan.com`) runs via two systemd services:

| Service | Unit File | Port | Description |
|---------|-----------|------|-------------|
| `ai-agent-board-server` | `/etc/systemd/system/ai-agent-board-server.service` | 3001 | Express API + WebSocket + agent SDKs |
| `ai-agent-board-client` | `/etc/systemd/system/ai-agent-board-client.service` | 4175 | Vite dev server (proxied by nginx/reverse proxy) |

```bash
# Check status
systemctl status ai-agent-board-server ai-agent-board-client

# Restart after code changes
systemctl restart ai-agent-board-server ai-agent-board-client

# View logs
journalctl -u ai-agent-board-server -f
journalctl -u ai-agent-board-client -f

# Restart just one
systemctl restart ai-agent-board-server
systemctl restart ai-agent-board-client
```

**Important:** The server reads `packages/server/.env` via dotenv. Production uses PostgreSQL via the `ai-agent-board-db` Docker container (postgres:16-alpine on port 5433). DB credentials: `user=agentboard, db=agentboard`. If the password needs resetting: `docker exec ai-agent-board-db psql -U agentboard -c "ALTER USER agentboard WITH PASSWORD '<pass>'"`. Do **not** fall back to SQLite in production.

## Build

```bash
npm run gate:required  # required gate: client build, server build, E2E
npm run build:client   # tsc + vite build
npm run build:server   # tsc -b tsconfig.build.json
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | _(none)_ | Bearer token for API + WebSocket auth; unset = open access |
| `VITE_API_KEY` | _(none)_ | Client-side API key (must match `API_KEY`) |
| `PORT` | `3001` | Server port |
| `DATABASE_URL` | _(none)_ | PostgreSQL connection string; when unset, uses SQLite |
| `DB_PATH` | `./data/agentboard.db` | SQLite database file path |
| `COPILOT_MODEL` | `claude-opus-4-20250514` | Model for Copilot SDK sessions |
| `CLAUDE_MODEL` | `claude-opus-4-20250514` | Model for Claude Code sessions |
| `CODEX_MODEL` | `gpt-5.2-codex` | Model for OpenAI Codex sessions |
| `HERMES_COMMAND` | `hermes` | Hermes CLI command or absolute path used to start the ACP server |
| `OPENCLAW_COMMAND` | `openclaw` | OpenClaw CLI command or absolute path used to start the ACP bridge |
| `OPENCLAW_GATEWAY_URL` | _(none)_ | Optional OpenClaw Gateway WebSocket URL forwarded to `openclaw acp` |
| `COPILOT_DENIED_TOOLS` | _(none)_ | Comma-separated tool names to deny in Copilot sessions |
| `ALLOWED_REPO_ROOTS` | `$HOME`, temp, current workspace | Comma-separated allowed repo root paths (security whitelist) |
| `ALLOWED_ORIGINS` | `http://localhost:4175,http://localhost:4176` | CORS origins |
| `AGENT_TIMEOUT_MS` | `600000` (10 min) | Max agent execution time |
| `API_URL` | `http://localhost:3001` | Vite proxy target |
| `PROJECTS_DIR` | `~/projects` | Host projects path |

## Tests

```bash
# Deterministic required gate (client build, server build, E2E)
npm run gate:required

# Required E2E only; Playwright starts isolated test app processes on ports 3002/4176
npm run test:e2e:required

# Enable the committed pre-push hook for this clone
npm run hooks:install
```

The committed `.githooks/pre-push` hook runs `npm run gate:required` and must not silently skip E2E. 7 test files, 81 tests (79 active, 2 skipped integration): board (CRUD, drag, theme, priority, sort, filter, retry), API improvements (auto-run, batch, status, events), agent selector, task groups (CRUD, validation, edge cases, UI), git operations (merge, PR, worktree), group integration (real agent execution), agent SDK. Portability/setup problems are blockers to fix, not reasons to skip affected e2e coverage.

## Code Patterns

- **Task lifecycle**: backlog → in-progress → review → done (validated transitions in `VALID_TRANSITIONS` from `shared/constants.ts`)
- **Agent lifecycle**: idle → planning → executing → complete/failed (set via `agentStatus`)
- **Agent types**: `copilot | claude | codex | opencode | hermes | openclaw` — each task can specify which agent to use via `agentType`
- **Provider pattern**: `AgentProvider` creates `AgentSession`s (from `@codewithdan/agent-sdk-core`). `AgentManager` orchestrates sessions with timeouts, event caching, and graceful cleanup.
- **Repository pattern**: `TaskRepository`, `TemplateRepository`, and `TaskGroupRepository` interfaces with SQLite and PostgreSQL implementations.
- **Event coalescing**: AgentPanel merges consecutive thinking/output events for readability
- **Graceful shutdown**: 5s force-exit timeout after `SIGINT`/`SIGTERM`, all SDK sessions cleaned up
- **Copilot permission request**: SDK uses `req.kind` (shell/read/write/mcp/url/memory), NOT `req.toolName`
- **Group queue**: `GroupQueue` in agent-manager tracks pending/running/completed/failed per group. `drainQueue()` fills slots up to `maxConcurrency` as children complete.
- **Per-repo mutex**: `withRepoLock()` serializes git operations (merge, checkout) on the same repository to prevent concurrent modification races.
- **Startup recovery**: Orphaned tasks (`executing`/`planning` without live session) reset to `failed` on server restart. Groups reconstruct queue from DB state.

## Squad Operating Mode

- **Roster/routing**: Use `.squad/team.md` and `.squad/routing.md` for domain ownership before non-trivial work.
- **Critical behaviors**: Use `.squad/coverage-matrix.md` to classify risk for agent runtime, git/worktrees, auth/path safety, event streaming, task groups, repositories, and board workflows. Browser workflow/client-server changes must produce deterministic e2e evidence or fail the gate.
- **Skills**: Check `.copilot/skills/` for general process skills and `.squad/skills/` for project-specific patterns before starting work.
- **Completion summaries**: After significant agent batches, report `Asked:`, `Completed:`, and `Open issues:` so blockers are not hidden in logs.

## Known Issues (LOW priority)

- Search input missing `aria-label` (Header.tsx)
- No WebSocket re-sync after reconnection (api.ts)
- `db.close()` not in try/catch during shutdown (index.ts)
- Keyboard shortcuts don't check `contenteditable` elements (useKeyboardShortcuts.ts)
- Timer leak in CopyButton if component unmounts within 2s (AgentPanel.tsx)


===== FILE nikomatsakis/babysteps::CLAUDE.md | stars=38 followers=4531 lang=HTML bytes=3725 =====

# Babysteps Blog

This is Niko Matsakis' technical blog "baby steps" where he posts various thoughts and ideas about Rust, programming language design, and software development.

## About the Blog

- **URL**: https://smallcultfollowing.com/babysteps/
- **Description**: This blog is where Niko posts up various half-baked ideas that he has
- **Built with**: Hugo static site generator
- **Key Topics**: Rust language design, async/await, traits, lifetimes, borrow checking, type systems, programming language theory
- **Started**: 2011

## Key Context

Niko is one of the lead designers of the Rust programming language and has been writing on this blog since 2011. The blog contains deep technical discussions about:
- Rust language features and design decisions
- Memory management and ownership
- Type inference and trait systems
- Async programming in Rust
- Developer tooling and ergonomics

## Working with the Blog

### Structure
- Blog posts are in `content/blog/` with date-prefixed filenames (e.g., `2024-03-04-borrow-checking-without-lifetimes.markdown`)
- Public drafts go in `drafts/` directory
- Private drafts go in `drafts-private/` (git submodule pointing to private repository)
- Uses Markdown with Hugo frontmatter
- Images and assets go in `static/assets/`

### Private Drafts Setup
- `drafts-private/` is a git submodule pointing to `git@github.com:nikomatsakis/babysteps-drafts.git`
- People with SSH access can `git submodule update --init` to access private drafts
- People without access will see an empty directory without errors
- Use private drafts for sensitive ideas or work-in-progress thoughts not ready for public consumption

### Important Conventions
- **Deployment**: Automatic via GitHub push
- **URLs**: Preserved by keeping filenames unchanged - NEVER change the date in a filename as it determines the URL
- **Cross-referencing**: Use the `{{< baseurl >}}` shortcode when linking to other posts on this blog
  - Use "out of line" link definitions for readability
  - In the text: `[link text][ref]`
  - Define links at the bottom of the paragraph where they're first used: `[ref]: {{< baseurl >}}/blog/YYYY/MM/DD/slug/`
  - Example: `[soul of Rust][sor]` with `[sor]: {{< baseurl >}}/blog/2022/09/18/dyn-async-traits-part-8-the-soul-of-rust/` after the paragraph
  - Avoid absolute URLs as they make local testing harder
- **Updates**: If updating an existing post, add an "Updated: YYYY-MM-DD" note but keep the original date

### Post Format Example
```markdown
---
title: "Your Title Here"
date: 2024-03-04T10:00:00-05:00
series:
- "Series Name Here"
- "Another Series If Applicable"
---

Post content here...
```

### Series
Posts can belong to one or more series using the `series:` frontmatter field. This helps connect related posts together. Common series include:
- "Dyn async traits" - exploring dynamic async traits
- "Polonius" - the new borrow checker formulation
- "Async interviews" - conversations about async Rust
- Posts can belong to multiple series simultaneously

### Writing Style
- Technical but accessible
- Often uses examples to illustrate concepts
- Includes code snippets to demonstrate ideas
- Personal and conversational tone while discussing complex topics
- Often explores "half-baked ideas" and thinking out loud
- Target audience: Rust developers (intermediate to expert), language designers, systems programmers

### When Helping with Blog Posts
- Maintain the existing conversational yet technical tone
- Use concrete examples to illustrate abstract concepts
- Feel free to include Rust code examples where relevant
- Blog posts often explore ideas in progress, not just finished thoughts
- For code blocks, use language tags: ```rust, ```bash, etc.

===== FILE anonrig/yagiz.co::AGENTS.md | stars=36 followers=2183 lang=MDX bytes=4889 =====

# AGENTS.md

Project-specific rules and notes for AI agents working in this codebase.

## Commands

```sh
node --run build          # wrangler types && astro check && astro build
node --run dev            # wrangler types && astro dev --port 3000
node --run preview        # wrangler dev (Cloudflare Workers local preview)
node --run deploy         # build && wrangler deploy
node --run lint           # biome check .
node --run lint-fix       # biome check . --write
node --run cli            # interactive CLI for blog/newsletter tasks
```

Always run `node --run build` before marking a task complete. It runs type generation,
type checking, and the full Astro build in one step.

## Stack

- **Framework**: Astro 7 — static output, deployed to Cloudflare Workers via `@astrojs/cloudflare` v14
- **Styling**: Tailwind CSS v4 via `@tailwindcss/vite` (no `tailwind.config` file needed for basic use)
- **Fonts**: Mulish variable font via `fontProviders.local()` — file lives at `src/assets/fonts/mulish-variable.woff2`
- **Linter/formatter**: Biome v2
- **Package manager**: pnpm

## Git

- Branch names must use the `yagiz/` prefix (e.g. `yagiz/fix-something`)
- Do not add Claude/AI as a git commit author
- Keep commits small and focused

## TypeScript

- Use TypeScript 6 (`^6.0.0`). TypeScript 7 is available but breaks `@astrojs/check`
  (language-server incompatibility). Stay on TS 6 until Astro check supports TS 7.
  Peer warnings about `typescript@^5` are cosmetic.

## Astro-specific

- **Content config**: lives at `src/content.config.ts` (NOT `src/content/config.ts` —
  that was the Astro v4 location). All collections must use loaders (e.g. `glob()`).
- **`z` (Zod)**: import from `astro/zod`, not from `astro:content`.
- **Rust compiler**: default in Astro 7 — do not set `experimental.rustCompiler`.
- **Markdown/MDX plugins**: use `markdown.processor: unified({...})` from
  `@astrojs/markdown-remark`. Plugins on `mdx({ remarkPlugins, rehypePlugins })` are
  deprecated. This project stays on unified (not Sätteri) for rehype-pretty-code, etc.
- **`compressHTML`**: Astro 7 defaults to `'jsx'` whitespace rules; this project sets
  `compressHTML: true` to keep previous HTML-aware spacing.

## Cloudflare adapter (v14)

These APIs were **removed** in `@astrojs/cloudflare` v13+ / Astro 6+. Do not use them:

| Old (v4/v5) | New (v13+ / Astro 6+) |
|---|---|
| `Astro.locals.runtime.env` | `import { env } from "cloudflare:workers"` |
| `Astro.locals.runtime.cf` | `Astro.request.cf` |
| `Astro.locals.runtime.caches` | global `caches` |
| `Astro.locals.runtime.ctx` | `Astro.locals.cfContext` |

Cloudflare bindings (D1, KV, etc.) are accessed like this in API routes:

```ts
import { env } from 'cloudflare:workers'

export const POST: APIRoute = async ({ request }) => {
  const result = await env.MY_BINDING.prepare('SELECT 1').run()
}
```

`App.Locals` only has `cfContext: ExecutionContext` — there is no `runtime` property.

- Cloudflare Pages support was **removed** in adapter v13. The project deploys to
  **Cloudflare Workers**. Do not add `pages_build_output_dir` to `wrangler.toml`.
- Pages prerendering now uses Cloudflare's `workerd` runtime by default. If a
  prerendered page uses Node.js-only packages (e.g. `sharp`, `satori`), set
  `prerenderEnvironment: 'node'` in the adapter config in `astro.config.ts`.

## D1 — newsletter database

- **Binding**: `newsletter` (lowercase)
- **Database name**: `newsletter`
- **Database ID**: `33ad2d37-f48c-4033-86fd-81c7ade04178`
- **Schema**: `migrations/0001_create_subscribers.sql`

Apply migrations:
```sh
wrangler d1 migrations apply newsletter --remote   # production
wrangler d1 migrations apply newsletter --local    # local dev
```

Add new schema changes as `migrations/0002_*.sql`, `migrations/0003_*.sql`, etc.
Never edit existing migration files.

## Fonts

The site uses the Mulish variable font. It is self-hosted via Astro's built-in fonts API
(`fontProviders.local()`), configured in `astro.config.ts`. The WOFF2 file is at
`src/assets/fonts/mulish-variable.woff2`. The CSS variable `--font-mulish` is injected
automatically by the `<Font cssVariable="--font-mulish" preload />` component in
`src/layouts/Layout.astro`. `display: 'optional'` is set in the font config to prevent
layout shift on reload — do not change this to `'swap'`.

Do **not** use `fontProviders.fontsource()` — it requires outbound HTTPS to
`api.fontsource.org` which may be blocked in restricted build environments.

## Removed dependencies (do not re-add)

| Package | Replaced by |
|---|---|
| `@fontsource-variable/mulish` | Astro fonts API + local WOFF2 |
| `astro-seo` | Inline meta tags in `Layout.astro` |
| `date-fns` | Native `Date.getTime()` / `toISOString().split('T')[0]` |
| `reading-time` | Inline word-count: `Math.max(1, Math.round(words / 200)) + " min read"` |
| `open` | Was unused |


===== FILE zzzgydi/verge-browser::CLAUDE.md | stars=28 followers=1254 lang=Python bytes=2296 =====

# CLAUDE.md

## Overview

Verge Browser is a browser sandbox system for agent workflows. The current repository contains a functional MVP path:

- build the runtime image
- create a sandbox through the API
- take real window and page screenshots
- execute GUI actions
- open a ticketed VNC entry
- run file APIs inside the same workspace

## Repository Conventions

- API code lives in `apps/api-server/app`.
- Runtime scripts live in `apps/runtime-xvfb/scripts` and `apps/runtime-xpra/scripts`.
- Supervisor wiring lives in `apps/runtime-xvfb/supervisor` and `apps/runtime-xpra/supervisor`.
- Integration tests that require Docker live under `tests/integration`.
- Use **Conventional Commits** for all `git commit` messages.
- Do not leak local developer information in generated code or `git commit` messages, including machine-specific paths, usernames, home directories, or other local environment details.

## Development Workflow

### Local Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the API server

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

### Build the runtime image

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
```

### Run tests

```bash
PYTHONPATH=apps/api-server pytest tests/unit
PYTHONPATH=apps/api-server pytest -m integration tests/integration/test_runtime_api.py
```

## Implementation Notes

- The runtime currently assumes Docker is the sandbox backend.
- `BrowserService` contains the real screenshot, viewport discovery, and CDP screenshot logic.
- `SandboxLifecycleService` owns startup readiness and container cleanup.
- `DockerAdapter` is the boundary for Docker interactions. Prefer extending it instead of scattering `docker` shell calls.

## When Updating This Repo

- Keep README in sync with what is actually validated.
- Add or extend integration tests whenever runtime behavior changes.
- If you change runtime ports, update both the Docker image and the API-side runtime metadata.
- If you change screenshot or session behavior, validate against a real built runtime image before considering the change done.
