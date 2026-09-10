

===== FILE srizzon/git-city::CLAUDE.md | stars=5741 followers=None lang=TypeScript bytes=5498 =====

# Git City

3D pixel art city built from real GitHub data. Buildings represent developers: height = contributions, width = repos, lit windows = recent activity.

## Tech stack

- **Frontend:** Next.js App Router, Three.js (instanced rendering), TypeScript
- **Backend:** Supabase (Postgres + Auth + Realtime)
- **Payments:** Stripe (USD), AbacatePay (BRL/PIX), NOWPayments (crypto)
- **Deployment:** Vercel

## Project structure

```
src/
  app/              Next.js pages and API routes
  components/       React + Three.js components
  lib/              Core game logic (raids, dailies, XP, items, etc.)
supabase/
  migrations/       Sequential SQL migrations (001_, 002_, ...)
```

## Code conventions

- TypeScript everywhere, no `any`
- `getSupabaseAdmin()` for server-side writes (bypasses RLS)
- `createServerSupabase()` for auth in API routes (cookie-based)
- API routes validate auth, then use admin client for DB operations
- Items use a zone system: crown, roof, aura, faces
- Loadout stored in `developer_customizations` table with `item_id = "loadout"`

## Database

- Migrations in `supabase/migrations/`, numbered sequentially
- Never modify existing migrations, always create new ones
- Run locally with `npx supabase db push`
- **NEVER run UPDATE or DELETE on production data without explicit user approval**
- **NEVER NULL out, drop, or modify columns that contain user data (emails, API keys, etc)**
- When fixing security/permissions issues, ONLY change grants/policies — never touch the data itself
- Always propose SQL as code for the user to review, never execute destructive SQL directly

## Environments

- Three environments, one-directional flow: local → staging → prod (see `ENVIRONMENTS.md`)
- `main` = production. Any other pushed branch = Vercel preview + staging Supabase
- Pushing a branch with migration changes triggers `deploy-staging-migrations.yml` (validate + `db push` to staging)
- Merging into `main` triggers `deploy-migrations.yml` (validate + `db push` to prod) — migrations deploy automatically, never push them to prod by hand
- Vercel Preview-scoped env vars point at the staging Supabase project; Production-scoped at prod
- Staging is disposable: reset with `supabase db reset --linked` while linked to staging. Never copy prod data into it

## Git

- Preserve full commit history on merge — NEVER squash PRs (use a merge commit or rebase, keep every commit)
- Commit message format (ALWAYS follow):
  - emoji + conventional commit: `✨ feat(scope): ...`, `🐛 fix(scope): ...`, `✏️ docs: ...`, `♻️ refactor: ...`
  - single line only — no body, no bullet points
  - all lowercase, written in english
  - split work into separate commits by logical part / group of changes (never one giant commit)
- Never skip hooks or force push to main

## Third-party Assets (IMPORTANT)

- **Arcade character sprites (char_0-5)** and Lumon furniture: from [pixel-agents](https://github.com/pablodelucca/pixel-agents) by Pablo De Lucca (MIT) / [MetroCity](https://jik-a-4.itch.io/metrocity-free-topdown-character-pack) (CC0). These ARE in the repo under `public/sprites/arcade/`.
- **Cozy People Asset Pack** by shubibubi: purchased under commercial license ($3.99+). Used for the layered avatar (body, hair, clothing, accessories) and pet sprites.
- **Cozy Interior Asset Pack** by shubibubi: purchased under commercial license. Used for arcade room furniture and tilesets.
- **License terms**: "Can be used in any commercial or non commercial project, may modify. Can't be resold or redistributed even if modified."
- **NEVER commit Cozy assets to the repo** — they are NOT covered by AGPL. They live in Supabase Storage and are loaded at runtime via `NEXT_PUBLIC_COZY_BASE_URL`.
- **NEVER include Cozy PNGs in git add** — the `public/cozy/` folder is gitignored.
- Forkers must buy their own license from shubibubi on itch.io and place files in `public/cozy/`, then seed the `arcade-assets` Supabase bucket from those files. (The maintainer's upload script lives under the gitignored `scripts/` folder and is not shipped — write a small one-off uploader against the `arcade-assets` bucket.)
- Original purchase links: https://shubibubi.itch.io/cozy-people and https://shubibubi.itch.io/cozy-interior
- **Kenney models** (`public/models/trees/*.glb`, `public/models/props/*.glb`): from [Kenney](https://kenney.nl) Nature Kit / City Kit (CC0 — public domain). Free to use, modify, and redistribute; attribution appreciated but not required. These ARE in the repo. Raw unpacked kit folders stay local (`kenney/` is gitignored).
- **San Francisco map** (`public/maps/sf.json`): baked from [OpenStreetMap](https://www.openstreetmap.org/copyright) data. OSM data is **ODbL** — the "© OpenStreetMap contributors" credit MUST stay visible on the SF map (rendered in `home-client.tsx`). The committed `public/maps/sf.json` is what ships; the bake script lives under the gitignored `scripts/` folder and is not in the repo.

## Key files

| File | What it does |
|------|-------------|
| `src/components/InstancedBuildings.tsx` | WebGL instanced rendering for thousands of buildings |
| `src/components/CityCanvas.tsx` | Main Three.js scene setup |
| `src/lib/raid.ts` | Raid system (PvP, scoring, limits) |
| `src/lib/items.ts` | Shop items, equipping, zones |
| `src/lib/xp.ts` | XP leveling (25 levels, 6 tiers) |
| `src/lib/stripe.ts` | Stripe checkout sessions |
| `src/app/api/webhooks/stripe/route.ts` | Stripe webhook handler |


===== FILE go-pay/gopay::CLAUDE.md | stars=5689 followers=None lang=Go bytes=3218 =====

# GoPay 项目说明

## 代码探索约定

探索/索引本项目代码时，**默认优先使用 `codebase-memory` MCP**，未安装则降级到默认工具：

1. **首选**：`mcp__codebase-memory-mcp__*` 工具（若可用）
   - `search_graph` — 按名称/标签/限定名查找函数、类型、路由
   - `trace_path` — 调用链、数据流、跨服务追踪
   - `get_code_snippet` — 按限定名获取精确源码片段
   - `query_graph` — 复杂 Cypher 查询
   - `get_architecture` — 项目结构总览
   - `search_code` — 图增强的文本搜索
   - 项目未索引时，先运行 `index_repository` 建立索引
2. **降级（MCP 未安装/不可用时）**：使用默认工具 `Grep` / `Glob` / `Read` / `Bash`（find、grep）进行文本与文件检索
3. 不管哪种方式，**编辑前必须先 `Read` 目标文件**

## 项目概述

GoPay 是一个 Go 语言的支付 SDK 项目，提供微信、支付宝、QQ、通联支付、拉卡拉、PayPal、扫呗、Apple 支付的统一接口。

- **仓库**: https://github.com/go-pay/gopay
- **Go 版本**: 1.24.0
- **许可证**: Apache 2.0

## 项目结构

```
gopay/
├── alipay/          # 支付宝支付 SDK
├── wechat/          # 微信支付 SDK
├── apple/           # Apple 支付校验
├── paypal/          # PayPal 支付 SDK
├── qq/              # QQ 支付 SDK
├── allinpay/        # 通联支付 SDK
├── lakala/          # 拉卡拉支付 SDK
├── saobei/          # 扫呗支付 SDK
├── pkg/             # 公共包
├── doc/             # 各支付方式文档
└── examples/        # 示例代码
```

## 开发约定

### 代码风格

1. **遵循 Go 标准规范**
   - 使用 `gofmt` 格式化代码
   - 遵循 Go 命名约定（驼峰命名）
   - 导出的函数、类型、常量首字母大写

2. **测试文件**
   - 每个模块都有对应的 `*_test.go` 文件
   - 测试文件包含实际使用示例
   - 建议使用正式环境 1 分钱测试法

3. **日志处理**
   - 使用项目依赖的 `github.com/go-pay/xlog` 包
   - 支持自定义 Logger（实现 `xlog.XLogger` interface）

### 支付平台版本

- **支付宝**: 优先使用 V3 版本
- **微信**: 优先使用 V3 版本（V2 版本不推荐）
- 其他平台参考 `doc/` 目录下的文档

### 重要注意事项

1. **安全性优先**
   - 处理支付相关代码时特别注意安全性
   - 不要在代码中硬编码敏感信息（密钥、证书等）
   - 注意参数验证和签名校验

2. **向后兼容**
   - 这是一个公开的 SDK，修改时注意 API 兼容性
   - 重大变更需要在 `release_note.md` 中记录

3. **文档同步**
   - 新增功能需要更新对应的 `doc/*.md` 文档
   - 保持代码示例和文档的一致性

## 依赖管理

项目使用 Go Modules，主要依赖：
- `github.com/go-pay/crypto` - 加密工具
- `github.com/go-pay/xlog` - 日志工具
- `github.com/go-pay/util` - 通用工具
- `golang.org/x/crypto` - Go 官方加密库

## 参考资源

- 各支付方式文档: `doc/` 目录
- 测试用例: 各模块的 `*_test.go` 文件
- 示例项目: https://github.com/go-pay/gopay-platform


===== FILE alexzhang13/rlm::AGENTS.md | stars=5318 followers=None lang=Python bytes=15638 =====

# AGENTS.md

This guide covers best practices for contributing to the core Recursive Language Models `rlm` library and developing new environments (in `rlm/environments/`) and LM clients (in `rlm/clients/`).

## Setup

We use `uv` for developing `rlm`.
```bash
# Install uv (first time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup blank project if needed
uv init && uv venv --python 3.12
source .venv/bin/activate

# Install in editable mode
uv pip install -e .

# For Modal sandbox support
uv pip install -e ".[modal]"

# For Prime sandbox support
uv pip install -e ".[prime]"
```

## General Guidelines

### Code Style & Typing
- **Formatting**: Strict `ruff` enforcement. All PRs must pass `ruff check --fix .`
- **Typing**: Explicit types preferred
  - **OK**: `cast(...)`, `assert ...` for type narrowing
  - **SOMETIMES OK**: Untyped args for simple cases (e.g., prompt handlers)
  - **NOT OK**: `# type: ignore` without strong justification

### Naming Conventions
- **Methods**: snake_case
- **Classes**: PascalCase (e.g., `LocalREPL`, `PortkeyClient`)
- **Variables**: snake_case
- **Constants**: UPPER_CASE (e.g., `_SAFE_BUILTINS`, `RLM_SYSTEM_PROMPT`)

Do NOT use `_` prefix for private methods unless explicitly requested.

### Error Handling Philosophy
- **Fail fast, fail loud** - No defensive programming or silent fallbacks
- **Minimize branching** - Prefer single code paths; every `if`/`try` needs justification
- **Example**: Missing API key → immediate `ValueError`, not graceful fallback

## Core Repository Development

For PRs to `rlm` core:
```bash
git clone https://github.com/alexzhang13/rlm.git
cd rlm

# Standard development:
uv sync

# Install dev + test dependencies:
uv sync --group dev --group test

# Install pre-commit hooks:
uv run pre-commit install
```

### Dependencies
- Avoid new core dependencies
- Use optional extras for non-essential features (e.g., `modal` extra)
- Exception: tiny deps that simplify widely-used code

### Testing
- `uv run pytest` with discovery under `tests/`
- Write simple, deterministic unit tests
- Update tests when changing functionality
- For isolated environments, mock external services

### Documentation
- Keep concise and actionable
- Update README when behavior changes
- Avoid content duplication

### Scope
- Small, focused diffs
- One change per PR
- Backward compatibility is only desirable if it can be done without introducing excessive maintenance burden
- Delete dead code (don't guard it)

### Checklist

Before a PR:

```bash
# Run style + lint checks:
uv run ruff check --fix .
uv run ruff format .
uv run pre-commit run --all-files

# Run tests:
uv run pytest
```

Ensure docs and tests are updated if necessary, and dead code is deleted. Strive for minimal, surgical diffs.

## Developing LM Clients

LM client implementations live in `rlm/clients/`. All clients must inherit from `BaseLM`.

### Client Pattern

| Base Class | When to Use | Key Methods |
|------------|-------------|-------------|
| `BaseLM` | All LM integrations | `completion`, `acompletion`, `get_usage_summary`, `get_last_usage` |

### Requirements
- Inherit from `BaseLM` in `rlm/clients/base_lm.py`
- Implement all abstract methods: `completion`, `acompletion`, `get_usage_summary`, `get_last_usage`
- Track per-model usage (calls, input/output tokens)
- Handle both string and message list prompts
- Register client in `rlm/clients/__init__.py`

### Example Structure
```python
from rlm.clients.base_lm import BaseLM
from rlm.core.types import ModelUsageSummary, UsageSummary

class MyClient(BaseLM):
    def __init__(self, api_key: str, model_name: str, **kwargs):
        super().__init__(model_name=model_name, **kwargs)
        # Initialize your client
        
    def completion(self, prompt: str | list[dict[str, Any]], model: str | None = None) -> str:
        # Handle both str and message list formats
        # Track usage with _track_cost()
        # Return response string
        
    def get_usage_summary(self) -> UsageSummary:
        # Return aggregated usage across all calls
```

### Configuration Guidelines
- **Environment variables**: ONLY for API keys (document in README)
- **Hardcode**: Default base URLs, reasonable defaults
- **Arguments**: Essential customization via `__init__()`

## Developing Environments

Environment implementations live in `rlm/environments/`. Choose the appropriate base class.

### Environment Pattern

| Pattern | Base Class | When to Use | Key Methods |
|---------|------------|-------------|-------------|
| **Non-isolated** | `NonIsolatedEnv` | Local execution, same machine | `setup`, `load_context`, `execute_code` |
| **Isolated** | `IsolatedEnv` | Cloud sandboxes (Modal, Prime) | `setup`, `load_context`, `execute_code` |

### Requirements
- Inherit from `NonIsolatedEnv` or `IsolatedEnv` in `rlm/environments/base_env.py`
- Implement all abstract methods: `setup`, `load_context`, `execute_code`
- Return `REPLResult` from `execute_code`
- Handle `lm_handler_address` for LM calls via `llm_query()` and `rlm_query()`
- Implement `cleanup()` for resource management
- Register environment in `rlm/environments/__init__.py`

### Key Implementation Details
- `setup()`: Initialize globals, locals, and helper functions
- `load_context()`: Make context available as `context` variable
- `execute_code()`: Execute code, capture stdout/stderr, return `REPLResult`
- Always provide `llm_query`, `llm_query_batched`, `rlm_query`, and `rlm_query_batched` functions in environment globals

### State Management
Environments must provide these globals to executed code:
- `context`: The loaded context payload
- `llm_query(prompt, model=None)`: Plain single LM completion (no REPL, no iteration)
- `llm_query_batched(prompts, model=None)`: Batched plain LM completions
- `rlm_query(prompt, model=None)`: Recursive child RLM call (own REPL + iteration). Falls back to `llm_query` at max depth.
- `rlm_query_batched(prompts, model=None)`: Batched recursive child RLM calls
- `answer`: A dict (`{"content": "", "ready": False}`); the model sets `answer["content"]` and `answer["ready"] = True` to return a final answer. The env surfaces the content on `REPLResult.final_answer` once `ready` flips truthy.
- `SHOW_VARS()`: For listing available variables

### Example Structure
```python
from rlm.environments.base_env import NonIsolatedEnv
from rlm.core.types import REPLResult

class MyEnvironment(NonIsolatedEnv):
    def __init__(self, lm_handler_address: tuple[str, int] | None = None, 
                 context_payload: dict | list | str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.lm_handler_address = lm_handler_address
        self.setup()
        if context_payload:
            self.load_context(context_payload)
            
    def setup(self):
        # Initialize execution namespace
        
    def load_context(self, context_payload: dict | list | str):
        # Make context available to executed code
        
    def execute_code(self, code: str) -> REPLResult:
        # Execute code and return REPLResult
        
    def cleanup(self):
        # Clean up resources
```

### Checklist
- Guidelines here are followed
- Environment works with basic RLM completion calls
- `cleanup()` properly releases all resources
- Sub-LM calls work via `llm_query()` and `rlm_query()`
- Reserved names (`llm_query`, `rlm_query`, `context`, `history`, `answer`, `SHOW_VARS`) are restored after each execution

## Architecture: Environment ↔ LM Handler Communication

Understanding how environments communicate with the LM Handler is essential for developing new environments.

### Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Host Machine                                                       │
│  ┌─────────────┐       Socket (TCP)        ┌──────────────────────┐ │
│  │   RLM       │◄──────────────────────────►  LMHandler           │ │
│  │  (main)     │                           │  (ThreadingTCPServer)│ │
│  └─────────────┘                           └──────────────────────┘ │
│        │                                            ▲               │
│        ▼                                            │               │
│  ┌─────────────┐       Socket (TCP)                 │               │
│  │ LocalREPL   │────────────────────────────────────┘               │
│  │ (exec code) │  llm_query() / rlm_query() → LM calls               │
│  └─────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Socket Protocol (Non-Isolated Environments)

Non-isolated environments like `LocalREPL` communicate directly with the `LMHandler` via TCP sockets using a length-prefixed JSON protocol:

**Protocol Format**: `4-byte big-endian length prefix + UTF-8 JSON payload`

```python
# Sending a message (from rlm/core/comms_utils.py)
def socket_send(sock: socket.socket, data: dict) -> None:
    payload = json.dumps(data).encode("utf-8")
    sock.sendall(struct.pack(">I", len(payload)) + payload)
```

**Request Flow**:
1. Environment's `llm_query(prompt)` or `rlm_query(prompt)` is called during code execution
2. For `llm_query`: creates `LMRequest` and calls `send_lm_request(address, request)`. For `rlm_query`: invokes `subcall_fn` to spawn a child RLM (or falls back to `llm_query` at max depth).
3. Opens TCP connection to `LMHandler` at `(host, port)`
4. Sends length-prefixed JSON request
5. `LMHandler` processes via `LMRequestHandler.handle()`
6. Returns `LMResponse` with `RLMChatCompletion` or error

**Key Components**:
- `LMHandler` (`rlm/core/lm_handler.py`): Multi-threaded TCP server wrapping LM clients
- `LMRequest` / `LMResponse` (`rlm/core/comms_utils.py`): Typed request/response dataclasses
- `send_lm_request()` / `send_lm_request_batched()`: Helper functions for socket communication

### HTTP Broker Pattern (Isolated Environments)

Isolated environments (Modal, Prime) cannot directly connect to the host's socket server. They use an HTTP broker pattern:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Host Machine                                                               │
│  ┌─────────┐    Socket    ┌────────────┐    HTTP Poll    ┌────────────────┐ │
│  │   RLM   │◄────────────►│  LMHandler │◄────────────────│   ModalREPL    │ │
│  └─────────┘              └────────────┘                 │  (poller)      │ │
│                                                          └────────────────┘ │
│                                                                  │          │
│                                                          HTTP (tunnel)      │
│                                                                  │          │
└──────────────────────────────────────────────────────────────────┼──────────┘
                                                                   │
┌──────────────────────────────────────────────────────────────────┼──────────┐
│  Cloud Sandbox (Modal/Prime)                                     ▼          │
│  ┌─────────────┐     HTTP (localhost)     ┌─────────────────────────────┐   │
│  │ Exec Script │◄────────────────────────►│   Broker Server (Flask)     │   │
│  │ (exec code) │     /enqueue, etc.       │   - /enqueue (submit req)   │   │
│  └─────────────┘                          │   - /pending (poll reqs)    │   │
│                                           │   - /respond (return resp)  │   │
│                                           └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How It Works**:

1. **Sandbox Setup**: Environment creates a cloud sandbox with an HTTP broker server running inside
2. **Tunnel Exposure**: Broker server is exposed via encrypted tunnel (e.g., Modal's `encrypted_ports`)
3. **Code Execution**: When `llm_query()` is called inside sandbox, it POSTs to `http://localhost:8080/enqueue`
4. **Request Queuing**: Broker queues the request and blocks waiting for response
5. **Host Polling**: `ModalREPL` on host polls `{tunnel_url}/pending` for new requests
6. **LM Forwarding**: Host forwards requests to `LMHandler` via socket, gets response
7. **Response Delivery**: Host POSTs response to `{tunnel_url}/respond`
8. **Unblocking**: Broker unblocks the original `/enqueue` call with the response

**Broker Endpoints**:
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/enqueue` | POST | Submit LLM request from sandbox code (blocks until response) |
| `/pending` | GET | Get list of pending requests (called by host poller) |
| `/respond` | POST | Submit response for a request ID (called by host poller) |
| `/health` | GET | Health check |

**Key Implementation Details**:
- Broker runs as a Flask server inside the sandbox
- Uses `threading.Event` for request/response synchronization
- Poller thread on host runs in background with 100ms polling interval
- State persistence via `dill` serialization to `/tmp/rlm_state.dill`

### Implementing a New Isolated Environment

When building a new isolated environment (e.g., for a new cloud provider):

1. **Create broker server** - Flask/HTTP server with `/enqueue`, `/pending`, `/respond` endpoints
2. **Expose tunnel** - Use provider's tunnel/port forwarding to expose broker to host
3. **Implement poller** - Background thread on host to poll and forward requests
4. **Build exec script** - Script that runs inside sandbox with `llm_query()` calling broker
5. **Handle state** - Serialize/deserialize execution state between code blocks

See `rlm/environments/modal_repl.py` as the canonical reference implementation.



===== FILE openkruise/kruise::AGENTS.md | stars=5298 followers=None lang=Go bytes=9020 =====

# AGENTS.md

Guidance for AI agents working on the OpenKruise project.

## Project Overview

OpenKruise is a CNCF incubating project that extends Kubernetes with advanced workload management. It runs as a set of custom controllers and CRDs on top of Kubernetes, providing five functional domains:

- **Advanced Workloads**: CloneSet, AdvancedStatefulSet, BroadcastJob, AdvancedCronJob, DaemonSet, EphemeralJob
- **Sidecar Container Management**: SidecarSet, Container Launch Priority, SidecarTerminator
- **Multi-domain Management**: WorkloadSpread, UnitedDeployment
- **Enhanced Operations**: ContainerRecreateRequest, ImagePullJob, ImageListPullJob, ResourceDistribution, PodProbeMarker, NodeImage
- **Application Protection**: DeletionProtection, PodUnavailableBudget, PersistentPodState

| Key | Value                                                                        |
|-----|------------------------------------------------------------------------------|
| Module | `github.com/openkruise/kruise`                                               |
| Language | Go 1.23+                                                                     |
| K8s Libraries | v0.32.10                                                                     |
| controller-runtime | v0.20.2                                                                      |
| controller-tools | v0.17.3                                                                      |
| API Groups | `apps.kruise.io` (workloads and operations), `policy.kruise.io` (protection) |
| K8s Compatibility | v1.18+ (v1.28+ recommended)                                                  |
| License | Apache 2.0                                                                   |

## Project Structure

```
.
├── main.go                  # kruise-manager entry point
├── apis/                    # API type definitions (CRD specs)
│   ├── apps/
│   │   ├── pub/             # Shared types (lifecycle, launch_priority, etc.)
│   │   ├── v1alpha1/        # v1alpha1 API types
│   │   └── v1beta1/         # v1beta1 API types (StatefulSet)
│   └── policy/v1alpha1/     # Policy API types (DeletionProtection)
├── pkg/
│   ├── controller/          # Controller implementations per workload type
│   ├── webhook/             # Admission webhook handlers (validating/mutating)
│   ├── daemon/              # Kruise-daemon (node agent, gRPC + CRI)
│   ├── control/             # Shared control logic (pubcontrol, sidecarcontrol)
│   ├── util/                # Utilities (expectations, feature gates, cache, etc.)
│   ├── client/              # Generated clientset, informer, lister [DO NOT EDIT]
│   └── features/            # Feature gate definitions
├── cmd/
│   ├── daemon/              # Kruise-daemon entry point
│   └── helm_hook/           # Helm hook binary
├── config/                  # Kustomize overlays (CRD, RBAC, webhook, manager)
├── test/
│   ├── e2e/                 # End-to-end tests (ginkgo/gomega)
│   └── fuzz/                # Fuzz tests
├── scripts/                 # Build and code generation scripts
├── hack/                    # Dev scripts (fmt-imports, boilerplate)
└── docs/                    # Documentation, proposals, contributing guides
```

## Commands

### Build & Generate

| Command | Description |
|---------|-------------|
| `make build` | Build `bin/manager` (runs generate + fmt + vet + manifests first) |
| `make generate` | Regenerate DeepCopy, clientset, informer, lister, OpenAPI |
| `make manifests` | Regenerate CRD YAML and RBAC manifests |
| `make generate_helm_crds` | Regenerate CRDs for Helm charts into `bin/` |
| `make docker-build` | Build Docker image `openkruise/kruise-manager:test` |
| `make docker-multiarch` | Build multi-arch image (amd64/arm64/ppc64le) |

### Test

| Command | Description |
|---------|-------------|
| `make test` | Unit tests with race detector + coverage (envtest K8s 1.32.0) |
| `make atest` | Same as `test` but skips generate/fmt/vet/manifests |
| `make kruise-e2e-test` | Full e2e: kind cluster + build + install + test + cleanup |
| `make coverage-report` | Generate `cover.html` from `cover.out` |

### Lint & Format

| Command | Description |
|---------|-------------|
| `make lint` | golangci-lint (v1.51.2, config: `.golangci.yml`) |
| `make vet` | `go vet` |
| `make fmt` | `go fmt` |
| `make fmt-imports` | goimports with local prefix grouping |
| `typos --config typos.toml` | Spell check |

## Code Style and Conventions

### Error Handling
- **Forbidden**: `github.com/pkg/errors` (enforced by depguard linter)
- **Use instead**: `fmt.Errorf("context: %w", err)` for wrapping

### Import Ordering
Use `goimports` with local prefix `github.com/openkruise/kruise`. Groups in order:
1. Standard library (`fmt`, `os`, `context`, ...)
2. Third-party (`github.com/...`)
3. Kubernetes (`k8s.io/...`, `sigs.k8s.io/...`)
4. OpenKruise (`github.com/openkruise/kruise/...`)

Blank imports must have a comment explaining the side effect.

### Boilerplate
All `.go` files must include the Apache 2.0 license header from `hack/boilerplate.go.txt`.

### Spelling
US English locale (enforced by misspell linter).

### Generated Code (DO NOT EDIT)
- `pkg/client/` — generated clientset, informer, lister
- `apis/*/zz_generated.deepcopy.go` — generated DeepCopy methods
- `apis/*/openapi_generated.go` — generated OpenAPI specs
- `config/crd/bases/` — generated CRD YAML files

Regenerate with `make generate && make manifests`.

## Architecture Patterns

### Controller
- Each workload has its own package under `pkg/controller/<workload>/` with an `Add(mgr manager.Manager) error` entry point, registered in `pkg/controller/controllers.go`
- **Reconcile loops must be idempotent**: reprocessing the same event must produce the same result. Do not assume single execution
- Use expectation tracking (`pkg/util/expectations/`) to coordinate resource creation/deletion and avoid race conditions
- Use `Status().Update()` / `Status().Patch()` for status updates, not full resource updates
- Do not perform heavy operations (locking, blocking I/O) in event handlers; move them into the reconcile loop
- Check `deletionTimestamp` and handle finalizer cleanup before applying business logic
- Use `observedGeneration` in status to track whether the controller has processed the latest spec

### Webhook
- Each workload has handlers under `pkg/webhook/<workload>/`, registered via `pkg/webhook/add_<workload>.go`
- Webhooks should only do simple mutation and validation — move heavy operations into the controller reconcile loop
- Mutating webhooks: handle CREATE and UPDATE separately
- Validating webhooks: return clear, informative error messages on rejection
- Never panic in webhook handlers; recover and return `Allowed: false`

### Daemon (Kruise-Daemon)
- Runs as a node agent (`pkg/daemon/`), handling image pulling, container recreation, and pod probes via gRPC
- Communicates with the container runtime through CRI interface only — do not talk directly to Kubelet, Docker, or Containerd
- Should only access node-local Kubernetes resources or resources in the system namespace
- Entry point: `cmd/daemon/main.go`

### Feature Gates
- New features must be gated via `pkg/features/kruise_features.go` using `utilfeature.DefaultMutableFeatureGate`
- Feature gates must have unit tests behind the gate

## Code Generation Workflow

When modifying API types under `apis/`:

```
1. Edit types in apis/apps/v1alpha1/ or apis/apps/v1beta1/
2. make generate        # DeepCopy, clientset, informer, lister, OpenAPI
3. make manifests       # CRD YAML, RBAC
```

When adding a new API type or controller:

```
1. Define types in apis/apps/v1alpha1/<type>_types.go
2. Register scheme in apis/addtoscheme_apps_v1alpha1.go (or v1beta1)
3. Register controller in pkg/controller/controllers.go
4. Register webhook in pkg/webhook/add_<type>.go
5. make generate && make manifests
```

## Behavioral Rules

- Import order need matching goimports local prefix convention
- Don't perform blocking or locking operations in controller event handlers instead of the reconcile loop
- Don't Access cluster-scoped resources from daemon code
- Read related files before modifying code
- Don't edit `client/`, `proto/`, `config/crd/` — run `make generate` or `make manifests` instead
- After modifying `api/`, run `make generate manifests`
- Don't delete comments unless outdated
- New `.go` files need Apache 2.0 license header from `hack/boilerplate.go.txt`
- Use `Expectations` (`pkg/utils/expectations/`) for slow informer cache issues
- New APIs/architectural changes need proposal in `docs/proposals/`
- Ask user when unsure about business logic
- Always edit the files on your own, never use automation tools or scripts
- All comments must be in English
- Always commit with sign-off (e.g. `git commit -s`)


===== FILE Hufe921/canvas-editor::AGENTS.md | stars=5011 followers=None lang=TypeScript bytes=6708 =====

# Canvas Editor - Agent Development Guide

This guide provides essential information for agentic coding agents working on the canvas-editor repository.

## Project Overview

Canvas Editor is a TypeScript-based rich text editor library that renders content using HTML5 Canvas/SVG. It's built as an ES module with comprehensive TypeScript support and follows modern development practices.

## Development Commands

### Essential Commands
```bash
# Development
npm run dev                    # Start Vite dev server
npm run serve                  # Preview production build

# Building (includes lint + type check)
npm run lib                    # Build library for distribution
npm run build                  # Build application

# Code Quality
npm run lint                   # Run ESLint
npm run type:check            # TypeScript type checking

# Testing
npm run cypress:open          # Open Cypress test runner interactively
npm run cypress:run           # Run Cypress tests headless
```

### Pre-commit Hooks
- Automatically runs `npm run lint && npm run type:check` before commits
- Commit messages must follow conventional commit format (feat:, fix:, docs:, etc.)

## Code Style Guidelines

### Formatting Rules
- **No semicolons** - `semi: [1, "never"]`
- **Single quotes** - `quotes: [1, "single"]`
- **2-space indentation** - No tabs
- **80 character line limit** - `printWidth: 80`
- **No trailing commas** - `trailingComma: "none"`
- **Arrow function parentheses avoided** - `arrowParens: "avoid"`
- **LF line endings** - `endOfLine: "lf"`

### TypeScript Configuration
- **Strict mode enabled** - All type checking enforced
- **Target**: ESNext with modern features
- **Module system**: ESNext modules
- **Source maps**: Enabled for debugging
- **Unused locals/parameters**: Checked and reported

### ESLint Rules
- `any` type allowed (`@typescript-eslint/no-explicit-any: 0`)
- Console statements permitted
- Debugger statements allowed
- No explicit function return type required when inferred

## Project Structure

### Main Directories
```
src/
├── editor/                    # Core editor library
│   ├── index.ts              # Main entry point - exports Editor class
│   ├── core/                 # Core functionality
│   │   ├── draw/             # Canvas rendering engine
│   │   ├── command/         # Command pattern implementation
│   │   ├── listener/        # Event handling system
│   │   └── ...
│   ├── interface/            # TypeScript type definitions
│   ├── dataset/             # Constants and enums
│   │   ├── constant/        # Magic numbers and strings
│   │   └── enum/           # TypeScript enums
│   ├── utils/              # Editor-specific utilities
│   └── assets/             # CSS-in-JS and images
├── plugins/                 # Optional editor plugins
├── components/              # Reusable UI components
├── utils/                   # Shared utility functions
└── assets/                  # Static assets
```

### Key Files
- **Main entry**: `src/editor/index.ts` - Exports Editor class and utilities
- **Package exports**: ES module and UMD builds with TypeScript definitions
- **Node requirement**: `>=16.9.1`

## Import Conventions

### Module Imports
- Use ES module imports: `import { Editor } from './editor'`
- TypeScript interfaces: `import type { EditorInterface } from './interface'`
- Relative imports with explicit extensions for non-TypeScript files

### Import Organization
1. External libraries (Node.js built-ins, npm packages)
2. Internal modules (absolute imports from src/)
3. Relative imports (sibling/parent directory imports)
4. Type-only imports (use `import type` when possible)

## Naming Conventions

### Files and Directories
- **PascalCase** for components and classes: `EditorManager.ts`
- **camelCase** for utilities and functions: `formatText.ts`
- **kebab-case** for directories when containing multiple words: `rich-text/`

### Code Elements
- **PascalCase** for classes and interfaces: `class Editor`, `interface EditorConfig`
- **camelCase** for functions and variables: `formatText`, `currentSelection`
- **UPPER_SNAKE_CASE** for constants: `MAX_CANVAS_WIDTH`, `DEFAULT_FONT_SIZE`
- **PascalCase** for enums: `enum TextAlignment`

## Error Handling

### TypeScript Errors
- Use strict TypeScript checking - prefer explicit types over `any`
- Handle nullable types with optional chaining and nullish coalescing
- Use union types for variant error states

### Runtime Errors
- Throw descriptive Error objects with context
- Use try-catch blocks for external API calls
- Validate user input in public API methods

## Testing Guidelines

### Cypress E2E Tests
- Tests located in `cypress/` directory
- Use `npm run cypress:open` for interactive test development
- Use `npm run cypress:run` for CI/CD automated testing
- Viewport set to 1366x720 for consistency

### Test Organization
- Group related tests in describe blocks
- Use beforeEach for common setup
- Write descriptive test names that explain the behavior
- Test both happy path and error conditions

## Build Process

### Library Build
- TypeScript compilation with strict checking
- Vite bundling for ES module and UMD outputs
- Automatic CSS-in-JS injection via plugin
- Source maps generated for debugging

### Quality Gates
- Linting must pass before build completion
- Type checking must pass before build completion
- Pre-commit hooks enforce quality standards

## API Design

### Public API
- Main Editor class exported from `src/editor/index.ts`
- Fluent method chaining where appropriate
- Consistent parameter ordering (required, then optional)
- Comprehensive TypeScript definitions

### Plugin System
- Plugins in `src/plugins/` directory
- Extend Editor functionality without modifying core
- Follow established plugin patterns in codebase

## Development Workflow

1. **Start development**: `npm run dev`
2. **Make changes**: Follow code style guidelines
3. **Test changes**: Use Cypress for E2E testing
4. **Quality check**: `npm run lint && npm run type:check`
5. **Commit**: Pre-commit hooks will validate automatically
6. **Build**: `npm run lib` for distribution build

## Performance Considerations

- Canvas rendering optimized for frequent updates
- Minimal DOM manipulation - primarily Canvas-based
- Efficient event handling with delegation patterns
- Memory-conscious object pooling where appropriate

## Security Notes

- No external network requests in core library
- Sanitize all user input before rendering
- Avoid eval() and Function constructor usage
- Validate configuration options in public API

===== FILE triwinds/ns-emu-tools::CLAUDE.md | stars=4929 followers=None lang=Rust bytes=480 =====

# Repository Instructions

- Commit messages must follow Conventional Commits, for example: `fix(eden): switch release source to Forgejo`.
- Unless the user explicitly requests otherwise, make changes only on the Rust side under `src-tauri`. Do not modify Python or other non-Rust parts by default.
- After modifying Rust code, run `cargo fmt` and `cargo check` before handing off the work.
- If `cargo check` reports any errors or warnings, fix them before handing off the work.


===== FILE kimai/kimai::AGENTS.md | stars=4841 followers=None lang=PHP bytes=4952 =====

# Kimai Core Agent Guide

Use this file when working in the Kimai core repository.

## Stack

- Kimai is a professional open source time-tracking application
- PHP versions: 8.2, 8.3, 8.4, 8.5
- Main framework: Symfony 6.4
- Core libraries: Doctrine, Twig
- API libraries: FOSRestBundle, NelmioApiDocBundle
- Frontend: Bootstrap with Tabler.io
- Frontend build: Webpack Encore via `symfony/webpack-encore`
- Package managers: Composer and Yarn
- Tests: PHPUnit
- Code styles: PhpCsFixer
- Static analysis: PHPStan
- Project information in README.md
- Translations managed with Weblate online service

## Scope

- This guide applies to Kimai core only
- Work in `var/plugins/` is out of scope unless explicitly requested
- Each subdirectory in `var/plugins/` is a separate Kimai plugin and its own Git repository
- In fresh installations, `var/data/` and `var/plugins/` are empty

## Repository Map

- `.docker/` Docker image build files
- `.github/` GitHub Actions and repository metadata
- `assets/` JavaScript and Sass sources
- `bin/` executable entry points, especially `bin/console`
- `config/` Symfony configuration and bundle setup
- `migrations/` Doctrine migrations for installs and upgrades
- `public/` web root with `index.php`
- `public/build/` generated frontend assets
- `public/bundles/` generated public bundle assets
- `src/` core PHP source code
- `src/API/` the JSON API
- `templates/` Twig templates
- `tests/` PHPUnit tests
- `translations/` XLIFF files named `<component>.<locale>.xlf`
- `var/` runtime storage and generated content
- `vendor/` Composer dependencies

## Never Touch

- Do not read from or write to `var/cache/`, it is Symfony-managed internal state
- Do not modify `vendor/`
- Do not modify `var/data/`
- Do not modify `var/log/`
- Do not modify `public/build/`, generated frontend assets
- Do not modify `public/bundles/`, frintend assets from plugins
- Do not modify plugins in `var/plugins/` unless explicitly asked

## Agent Workflow

- Read the surrounding code before editing
- Follow existing local patterns before introducing new abstractions
- Keep changes small and targeted
- Keep code, identifiers, comments, branches, commit text, and documentation in English
- Ask before touching security-sensitive areas such as authentication, authorization, or permissions

## Architecture Rules

- Do not introduce new composer packages without prior discussion
- Prefer services over static helper classes
- Keep business logic out of controllers
- Use Twig templates for HTML output
- Preserve backward compatibility for upgrades

## Database Rules

- Doctrine entity changes affecting the schema require a migration file
- Generate migration with `bin/console doctrine:migrations:diff`
- Prefer `Doctrine\DBAL\Schema` in migrations over inline SQL

## Frontend and Translation Rules

- Build on existing Bootstrap and Tabler patterns
- Do not introduce new frontend frameworks without prior discussion
- Keep English translations updated whenever translations change
- English is the Weblate default language and Kimai fallback language
- Use Twig `|trans` for user-facing text instead of hardcoded strings
- Use FontAwesome 6 names for icons

## Testing Rules

- Every PHP class in `src/`, except interfaces, should have a matching PHPUnit test
- Map `src/<directory>/<ClassName>.php` to `tests/<directory>/<ClassName>Test.php`
- Cover all public methods with tests
- Follow the existing test style in the target area such as controller, event, voter, or service tests

## Validation

- Always run `./php-cs-fixer.sh core`
- Run `./phpstan.sh core` for changes in `src/`
- Run `./phpstan.sh test` for changes in `tests/`
- For focused checks, run `vendor/bin/phpunit tests/<directory>/<TestClassName>.php`
- Use `composer tests-unit` for broader validation without expensive end-to-end coverage
- Use `composer tests` when the change justifies running the full suite
- If tests fail, remove stale cache with `rm -r ./var/cache/test/` to cause a rebuild 

## Git Rules

- Avoid working directly on `main`
- Small fixes should target the active `release-x.y.z` branch
- Larger changes should go to descriptive `snake_case` feature branches
- Agents may create branches when needed
- Agents must not create commits unless explicitly asked
- Commits are normally created by the maintainer

## Coding Conventions

- Use strict comparisons such as `===` and `!==`
- Prefer constructor promotion for dependency injection
- Use PHP attributes for routing, mapping, and configuration where established
- Use `camelCase` for variables and methods
- Use 4-space indentation
- Use single quotes for strings in PHP, JavaScript, and CSS unless the local code style requires otherwise
- Use modern HTML5, Twig, and ES6+ syntax

## Security Focus

- Prevent XSS
- Prevent CSRF issues
- Prevent SQL or command injection patterns
- Prevent auth bypasses
- Prevent open redirects
- Apply Rate-Limiting in authentication flows


===== FILE sebastienros/jint::CLAUDE.md | stars=4685 followers=1936 lang=C# bytes=15656 =====

# CLAUDE.md

**Current development**: Target against main branch and compare changes against it.

## Build & Test Commands

### Building
```bash
# Build entire solution
dotnet build --configuration Release

# Build specific project
dotnet build --configuration Release Jint/Jint.csproj
```

Important: Never use --no-build - always ensure you are working with the latest compiled code.

### Testing
```bash
# Run all tests
dotnet test --configuration Release

# Run specific test project
dotnet test --configuration Release Jint.Tests/Jint.Tests.csproj

# Run specific test class
dotnet test --configuration Release --filter "FullyQualifiedName~Jint.Tests.Runtime.EngineTests"

# Run specific test method
dotnet test --configuration Release --filter "FullyQualifiedName~Jint.Tests.Runtime.EngineTests.CanEvaluateScripts"

# Run Test262 conformance tests
dotnet test --configuration Release Jint.Tests.Test262/Jint.Tests.Test262.csproj
```

Important: Run tests in Release mode for faster feedback loop.

## Requirements

- The project uses central package management via Directory.Packages.props

## Architecture

Jint follows a layered interpreter architecture:

```
Acornima Parser (external) → AST → Interpreter → Runtime → Interop
```

### Core Components

**Engine (`Jint/Engine.cs`)**
- Main API entry point split across multiple partial files (Engine.cs, Engine.Advanced.cs, Engine.Modules.cs, etc.)
- Manages execution context stack, intrinsics (built-in objects), and realms
- Configuration via `Options` class (constraints, CLR interop, modules, debugging)

**JsValue Type System (`Jint/Native/`)**
- `JsValue` is the abstract base class for all JavaScript values
- Primitive types: JsUndefined, JsNull, JsBoolean, JsNumber, JsString, JsBigInt, JsSymbol
- Object types: ObjectInstance and derived classes (JsArray, JsDate, JsMap, JsSet, JsPromise, etc.)
- All built-in JavaScript objects are in `Jint/Native/` organized by type (Array/, Date/, Error/, Function/, etc.)

**Runtime (`Jint/Runtime/`)**
- **TypeConverter.cs** (1,048 lines): All JavaScript type coercion (ToPrimitive, ToNumber, ToString, ToObject, etc.)
- **Intrinsics.cs**: Singleton containing all built-in object constructors and prototypes (lazily initialized)
- **Realm.cs**: ECMAScript Realm encapsulating global environment and intrinsics
- **Environments/**: Scope chain implementation (GlobalEnvironment, FunctionEnvironment, DeclarativeEnvironment, etc.)

**Interpreter (`Jint/Runtime/Interpreter/`)**
- **Statements/**: One handler class per statement type (JintIfStatement, JintForStatement, JintTryStatement, etc.)
- **Expressions/**: One handler class per expression type (JintBinaryExpression, JintCallExpression, JintMemberExpression, etc.)
- AST nodes are evaluated via specialized Jint* handler classes
- Caching: JintFunctionDefinition caches compiled function metadata for reuse

**Interop (`Jint/Runtime/Interop/`)**
- **ObjectWrapper.cs**: Wraps .NET objects for JavaScript access
- **TypeReference.cs**: Exposes CLR types to JavaScript (e.g., `System.String`)
- **ClrFunction.cs**: Wraps .NET methods/delegates as JavaScript functions
- **DefaultTypeConverter.cs**: Bidirectional conversion between JS values and CLR types
- **Reflection/**: Type discovery and method binding with caching

**Modules (`Jint/Runtime/Modules/`)**
- ES6 module system with import/export support
- ModuleLoader handles module resolution and loading
- Supports cyclic dependencies via CyclicModule
- Modules can be defined from JavaScript source or programmatically via ModuleBuilder

### Important Patterns

**Lazy Initialization**
- Built-in objects (Intrinsics) are lazily initialized to reduce startup time
- Properties are typically null until first access

**Object Pooling (`Jint/Pooling/`)**
- Reference, Arguments, and JsValue arrays are pooled to reduce GC pressure
- Use `ReferencePool`, `ArgumentsInstancePool`, `JsValueArrayPool`

**Property Key Optimization**
- `KnownKeys.cs` contains pre-computed common property names
- `HybridDictionary` switches between list and hash based on property count
- `StringDictionarySlim` for string-only dictionary keys

**Partial Classes**
- Large classes are split: Engine.*.cs, Intrinsics.*.cs, ObjectInstance.*.cs, etc.
- Keep related functionality together when editing

**ECMAScript Spec References**
- Code includes TC39 spec section references in comments (e.g., `// https://tc39.es/ecma262/#sec-...`)
- Maintain these references when implementing new features
- The to follow TC 39 spec when possible
- The test files are located in ..\test262\test when source code needed

**Type Flags**
- `InternalTypes` enum enables fast type checking without casting
- Many hot paths use type flags for performance

## ECMAScript Compliance
- Follow ECMAScript specification behavior as closely as practical
- Do not introduce non-standard language extensions
- Support both strict and sloppy mode with spec-defined differences

## Code Conventions

- **Namespaces**: Global usings for Acornima and Acornima.Ast defined in Directory.Build.props
- **Nullable**: Enabled across the codebase (NRT)
- **Unsafe Code**: Allowed (used for performance-critical paths)
- **Warnings as Errors**: Enabled - all warnings must be fixed
- **Analysis**: Latest analyzers enabled with EnforceCodeStyleInBuild
- **Performance**: Try to make code as perfomant as possible.

### Data Structures

**Prefer readonly record structs over tuples** for returning multiple values. Record structs provide better readability, named properties, and IDE support. Pass them into methods with 'in' modifier.

```csharp
// ❌ Avoid: Tuples with unnamed or poorly named fields
public (JsPlainDate?, JsZonedDateTime?) GetRelativeTo(ObjectInstance options)
{
    // Item1 and Item2 are unclear at call site
    return (plainDate, zonedDateTime);
}

// ✅ Prefer: readonly record struct with descriptive names
[System.Runtime.InteropServices.StructLayout(LayoutKind.Auto)]
public readonly record struct RelativeToResult(
    JsPlainDate? PlainRelativeTo,
    JsZonedDateTime? ZonedRelativeTo);

public RelativeToResult GetRelativeTo(ObjectInstance options)
{
    // Clear, self-documenting at call site
    return new RelativeToResult(plainDate, zonedDateTime);
}

// Usage is clear and type-safe
var result = GetRelativeTo(options);
if (result.PlainRelativeTo != null)
{
    // Use result.PlainRelativeTo
}
```

**When to use each:**
- **readonly record struct**: Multiple related return values (2+), especially when used across multiple methods
- **Class/struct**: Complex data with behavior, validation, or many fields (5+)

### Visibility: internal-first

Default new types, members, fields, and parameters to the **narrowest visibility that compiles**. Climb up only when a real consumer requires it.

1. **`private`** → single-class / single-file implementation detail
2. **`internal`** → shared within the Jint assembly (the default for most new runtime types)
3. **`protected internal`** → extension points on public abstract classes that derived classes in user code might legitimately need (e.g. `Module._engine`, `_realm`)
4. **`public`** → only when the type appears in a **public** signature (parameter, return, property) of an already-public API, or when end users must construct/consume it directly

**Rule of thumb:** if a type is only referenced by `internal` members, it must be `internal`. Only promote to `public` when a genuine public surface forces your hand — and if that happens, first consider whether the public surface itself can be split so the implementation-detail type stays internal. Example from this repo: `ModuleImportPhase` is only used by `internal` consumers plus one `public` static method; splitting that method into `public GetModuleNamespace(Module)` + `internal GetModuleNamespace(Module, ModuleImportPhase)` kept the enum internal.

Adding `public` API surface is a durable commitment — once shipped, breaking changes are costly. `internal` costs nothing to widen later.

### Type co-location: same file if same concept

Keep small supporting types (enums, record structs, private helpers) **in the same file** as the class they primarily exist to serve, provided they share a namespace and the combined file stays readable. Benefits: the relationship is obvious at a glance, renames/refactors touch one file, and reviewers don't have to jump between files.

Good candidates for co-location:
- Enums used by exactly one public type (e.g. `ModuleImportPhase` lives in `ModuleRequest.cs`)
- Record structs used as the return type of a single method
- Tiny helper classes with a one-way dependency on a single enclosing type

Split into a separate file when:
- The type has multiple independent consumers across the assembly
- It's a `public` type that needs independent XML-doc discoverability
- The enclosing file would exceed ~500 lines or mix unrelated concepts

## Testing

- **Jint.Tests/**: Main test suite using xUnit v3
  - Organized by topic (Runtime/, Parser/, Debugger/, etc.)
  - Uses AwesomeAssertions for readable assertions
  - Embedded test scripts in Runtime/Scripts/ and Parser/Scripts/
  - Use timeout of 30 seconds when invoking test runner

- **Jint.Tests.Test262/**: ECMAScript conformance suite using NUnit
  - Official TC39 Test262 integration
  - Validates spec compliance
  - The test files are located in ..\test262\test when source code needed, you are always allowed to read from this directory and its sub-directories
  - The error output contains the failing script, you just need to remove line numbers from the JavaScript
  - Never try to fix these tests
  - No need to use timeout, engine has default timeout of 30 seconds

- **Jint.Tests.CommonScripts/**: Real-world benchmark scripts using NUnit
  - Performance validation (crypto, 3D rendering, etc.)

- **Jint.Tests.PublicInterface/**: API contract tests using xUnit v3
  - Ensures public API stability

## Performance Considerations

- Jint uses Acornima for parsing (external, optimized)
- Cache `Script` or `Module` instances when executing the same script repeatedly
- Prefer strict mode execution (improves performance)
- Object pooling reduces GC pressure
- Expression and function definition caching reduces re-evaluation cost
- AggressiveInlining attributes mark hot paths

### Unsigned-cast bounds check (`(uint)i < (uint)length`)

Prefer `(uint) index < (uint) array.Length` over `index >= 0 && index < array.Length` when guarding an array/Span/list access where the index could be negative. This is an established pattern in this codebase (already used in `DictionarySlim`, `StringDictionarySlim`, `ValueStringBuilder`, `Arguments`, `TypeConverter`, `JsNumber`, `JintIdentifierExpression`, etc.) and across the .NET BCL.

**How it works:** `int.MinValue..-1` cast to `uint` produces values `0x80000000..0xFFFFFFFF` — all greater than any non-negative `int`. So the single unsigned comparison `(uint)i < (uint)length` is true iff `i` is in `[0, length)`. RyuJIT recognizes this idiom and lowers it to a single `cmp` + `jae` instruction; furthermore, the JIT can use the post-comparison range fact to elide the bounds check on the subsequent `array[i]` access (the index is already proven in range).

**When to use:**
- Manual bounds checks before a direct `array[i]` / `span[i]` / `list[i]` access where `i` could be negative or oversized — typical in pool/cache code, parser fast paths, and `for`-loop chains where the index isn't a fresh loop variable.
- Defensive validation of an `int` field/argument before indexing.
- `for (var i = ...; (uint)i < (uint)arr.Length; ...)` loops where the body indexes `arr[i]`.

**When not to use:**
- Ordinary `for (var i = 0; i < arr.Length; i++)` loops — the JIT already eliminates the bounds check there; the cast is noise.
- When the index is known non-negative by construction and you just want a single upper-bound check — plain `i < arr.Length` is clearer and equivalent.
- When the type is already unsigned (`uint`/`nuint`) — the cast is redundant.

**Caveats:**
- The pattern relies on `length` fitting in `int` (always true for `Array.Length` / `Span<T>.Length`). For `long` lengths (rare), use `(ulong)i < (ulong)length`.
- Different phrasings can affect the JIT's ability to elide subsequent bounds checks; prefer `(uint)i < (uint)arr.Length` over `(uint)i <= (uint)(arr.Length - 1)` and similar variants.

## Working with ES Features

When implementing new ECMAScript features:

1. **Read the TC39 spec section** for the feature
2. **Check Native/ directory** for where the built-in should live (e.g., Array/ for Array methods)
3. **Add to Intrinsics.cs** if it's a new global constructor or well-known symbol
4. **Update TypeConverter.cs** if new type coercion rules apply
5. **Add Statement/Expression handler** in Runtime/Interpreter/ if it's new syntax
6. **Reference spec sections** in code comments
7. Jint.Tests.Test262\Test262Harness.settings.json contains exclusions and inclusions for test cases

## Testing with Jint.Repl

The Jint REPL (Read-Eval-Print Loop) is useful for quickly testing JavaScript code during development.

### Running the REPL
```bash
# Build the REPL
dotnet build Jint.Repl --configuration Release

# Run the REPL
dotnet run --project Jint.Repl --configuration Release
```

### Command Line Options
```
-f, --file <path>     Execute JavaScript file
-t, --timeout <secs>  Set execution timeout in seconds
-h, --help            Show help message
```

### Testing Scripts

**Always use a timeout when testing scripts using Jint.Repl** to prevent infinite loops from hanging your session:

```bash
# Execute a file with 10 second timeout (recommended default)
dotnet run --project Jint.Repl --configuration Release -- -f script.js -t 10

# Execute from stdin with timeout
echo "1 + 2" | dotnet run --project Jint.Repl --configuration Release -- -t 10

# Execute multiline script from stdin
cat << 'EOF' | dotnet run --project Jint.Repl --configuration Release -- -t 10
var result = [];
for (var i = 0; i < 5; i++) {
    result.push(i * 2);
}
JSON.stringify(result);
EOF
```

### Quick Testing Patterns

```bash
# Test a simple expression
echo "Math.sqrt(16)" | dotnet run --project Jint.Repl --configuration Release -- -t 10

# Test JSON parsing
echo 'JSON.parse("[1,2,3]")' | dotnet run --project Jint.Repl --configuration Release -- -t 10

# Test with a temporary file
echo 'var x = 5; x * 2' > /tmp/test.js
dotnet run --project Jint.Repl --configuration Release -- -f /tmp/test.js -t 10
```

### When to Use REPL vs Jint.Tryouts

- **REPL**: Quick one-off tests, verifying behavior, testing from command line
- **Jint.Tryouts**: Complex debugging scenarios, stepping through code, testing with C# interop

## Module System

Modules are enabled via:
```csharp
var engine = new Engine(options => options.EnableModules(@"C:\Scripts"));
var ns = engine.Modules.Import("./my-module.js");
```

Or define modules programmatically:
```csharp
engine.Modules.Add("lib", builder => builder
    .ExportType<MyClass>()
    .ExportValue("version", 1)
);
```

## Constraints & Security

Execution constraints prevent resource abuse:
- Memory limits: `options.LimitMemory(4_000_000)`
- Timeout: `options.TimeoutInterval(TimeSpan.FromSeconds(4))`
- Statement limits: `options.MaxStatements(1000)`
- Custom constraints: Derive from `Constraint` base class

CLR access is disabled by default. Enable via:
```csharp
var engine = new Engine(cfg => cfg.AllowClr());
```

## AOT Compatibility

- Jint is AOT-compatible for .NET 7.0+ targets
- See Jint.AotExample/ for AOT usage patterns
- IsAotCompatible flag set for net7.0+ in Jint.csproj


===== FILE gptme/gptme::AGENTS.md | stars=4369 followers=None lang=Python bytes=3442 =====

# Agent Instructions for gptme

This file provides agent-specific guidance for working on gptme.
For general project information, see [README.md](README.md) and [docs](https://gptme.org/docs/).

## Git Workflow

- **Never push directly to master** - always use branches and PRs
- **Branch naming**: `feat/`, `fix/`, `docs/`, `refactor/` prefixes
- **Commit format**: Use [Conventional Commits](https://www.conventionalcommits.org/)
  - `feat:` for new features (not just docs)
  - `fix:` for bug fixes
  - `docs:` for documentation only
  - `refactor:`, `test:`, `chore:` as appropriate
- **Stage files explicitly**: Never use `git add .` or `git commit -a`
- **Create PRs**: Use `gh pr create` after pushing branch

## Code Style

- **Type hints**: All functions must have type annotations
- **Formatting**: `ruff format` and `ruff check` (run via pre-commit)
- **Type checking**: `mypy` must pass
- **KISS**: Keep it simple - avoid over-engineering
- **Small functions**: Refactor deeply nested code into smaller units
- **Minimal mocking**: Prefer integration tests over heavy mocking

## Testing

Run tests before submitting PRs:
```bash
make test           # Fast tests (excludes slow/eval)
make test SLOW=1    # Include slow tests
make typecheck      # mypy
make lint           # ruff + other checks
```

## Project Structure

Key directories:
- `gptme/` - Core library code
  - `gptme/cli/` - CLI entry points
  - `gptme/tools/` - Tool implementations
  - `gptme/llm/` - LLM provider integrations
  - `gptme/server/` - REST API server
- `tests/` - Test suite
- `docs/` - Sphinx documentation (RST + MD)
- `scripts/` - Build and utility scripts

## Core vs gptme-contrib

We aim to keep gptme core small and focused. See [docs/arewetiny.rst](docs/arewetiny.rst).

**Belongs in core (`gptme`):**
- Essential tools (shell, save, patch, browser, vision)
- Core infrastructure (chat loop, message handling, LLM providers)
- Features needed by most users

**Belongs in [gptme-contrib](https://github.com/gptme/gptme-contrib):**
- Specialized tools (Twitter/X, Discord, email)
- Experimental features
- Integrations with specific services
- Multi-agent patterns (consortium)

When in doubt, start in gptme-contrib. If widely adopted, consider upstreaming.

## Performance

We track startup time and code size. See [docs/arewetiny.rst](docs/arewetiny.rst).

CI benchmarks enforce startup thresholds.

## Key Concepts

- **Tool**: A function the assistant can execute (shell, save, patch, etc.)
- **ToolUse**: Parsed representation of a tool invocation in a message
- **Message**: A single message in the conversation
- **LogManager**: Manages conversation history persistence
- **Step**: One LLM generation + tool execution cycle
- **Turn**: Complete user→assistant exchange (may include multiple steps)

See [docs/glossary.md](docs/glossary.md) for full terminology.

## Subsystem Guides

- [webui/AGENTS.md](webui/AGENTS.md) - Web UI architecture and gotchas

## Common Tasks

### Adding a new tool
1. Create `gptme/tools/toolname.py`
2. Implement `ToolSpec` with `execute()` function
3. Tools are auto-discovered - no manual registration needed
4. Add tests in `tests/test_tools_toolname.py`

### Running the server
```bash
uv run gptme-server --port 5000
```

### Working on the web UI
See [webui/AGENTS.md](webui/AGENTS.md) for full setup including dev servers, testing, and architecture notes.

### Building docs
```bash
make docs
```


===== FILE ericc-ch/copilot-api::AGENTS.md | stars=4081 followers=None lang=TypeScript bytes=1599 =====

# AGENTS.md

## Build, Lint, and Test Commands

- **Build:**  
  `bun run build` (uses tsup)
- **Dev:**  
  `bun run dev`
- **Lint:**  
  `bun run lint` (uses @echristian/eslint-config)
- **Lint & Fix staged files:**  
  `bunx lint-staged`
- **Test all:**  
   `bun test`
- **Test single file:**  
   `bun test tests/claude-request.test.ts`
- **Start (prod):**  
  `bun run start`

## Code Style Guidelines

- **Imports:**  
  Use ESNext syntax. Prefer absolute imports via `~/*` for `src/*` (see `tsconfig.json`).
- **Formatting:**  
  Follows Prettier (with `prettier-plugin-packagejson`). Run `bun run lint` to auto-fix.
- **Types:**  
  Strict TypeScript (`strict: true`). Avoid `any`; use explicit types and interfaces.
- **Naming:**  
  Use `camelCase` for variables/functions, `PascalCase` for types/classes.
- **Error Handling:**  
  Use explicit error classes (see `src/lib/error.ts`). Avoid silent failures.
- **Unused:**  
  Unused imports/variables are errors (`noUnusedLocals`, `noUnusedParameters`).
- **Switches:**  
  No fallthrough in switch statements.
- **Modules:**  
  Use ESNext modules, no CommonJS.
- **Testing:**  
   Use Bun's built-in test runner. Place tests in `tests/`, name as `*.test.ts`.
- **Linting:**  
  Uses `@echristian/eslint-config` (see npm for details). Includes stylistic, unused imports, regex, and package.json rules.
- **Paths:**  
  Use path aliases (`~/*`) for imports from `src/`.

---

This file is tailored for agentic coding agents. For more details, see the configs in `eslint.config.js` and `tsconfig.json`. No Cursor or Copilot rules detected.


===== FILE portfolio-performance/portfolio::CLAUDE.md | stars=3981 followers=None lang=Java bytes=2448 =====

# CLAUDE.md

## Project Overview

Portfolio Performance is an Eclipse RCP (Rich Client Platform) application for tracking and analyzing investment portfolios. The codebase uses Java 21, Maven with Tycho for Eclipse-specific builds, and follows a modular OSGi plugin-based architecture.

## Build Commands

### Prerequisites
- `JAVA_HOME` must point to Java 21 JDK
- Use Maven Tycho for builds
- All commands use `-f portfolio-app/pom.xml`
- Use `-Plocal-dev` profile for faster local development (skips coverage, checkstyle, babel translations)

### Full Build
```bash
export MAVEN_OPTS="-Xmx4g"
mvn -f portfolio-app/pom.xml clean verify -Plocal-dev
```

### Build Core Module Only
```bash
mvn -f portfolio-app/pom.xml clean compile -Plocal-dev \
  -pl :portfolio-target-definition,:name.abuchen.portfolio.pdfbox1,:name.abuchen.portfolio.pdfbox3,:name.abuchen.portfolio -am -amd
```

### Build Core and UI Modules
```bash
mvn -f portfolio-app/pom.xml clean compile -Plocal-dev \
  -pl :portfolio-target-definition,:name.abuchen.portfolio.pdfbox1,:name.abuchen.portfolio.pdfbox3,:name.abuchen.portfolio,:name.abuchen.portfolio.bootstrap,:name.abuchen.portfolio.ui -am -amd
```

## Test Commands

### Run Core Tests
```bash
mvn -f portfolio-app/pom.xml verify -Plocal-dev -o \
  -pl :portfolio-target-definition,:name.abuchen.portfolio.pdfbox1,:name.abuchen.portfolio.pdfbox3,:name.abuchen.portfolio,:name.abuchen.portfolio.junit,:name.abuchen.portfolio.tests -am -amd
```

### Run Single Test Class
```bash
mvn -f portfolio-app/pom.xml verify -Plocal-dev -o \
  -pl :portfolio-target-definition,:name.abuchen.portfolio.pdfbox1,:name.abuchen.portfolio.pdfbox3,:name.abuchen.portfolio,:name.abuchen.portfolio.junit,:name.abuchen.portfolio.tests -am -amd \
  -Dtest=<fully.qualified.TestClassName>
```

### Run UI Tests
```bash
mvn -f portfolio-app/pom.xml verify -Plocal-dev \
  -pl :portfolio-target-definition,:name.abuchen.portfolio.pdfbox1,:name.abuchen.portfolio.pdfbox3,:name.abuchen.portfolio,:name.abuchen.portfolio.ui,:name.abuchen.portfolio.bootstrap,:name.abuchen.portfolio.junit,:name.abuchen.portfolio.ui.tests -am -amd
```

## Code Style

- Use `var` keyword for local variables where type is obvious
- Do NOT auto-format PDF extractor files — use `@formatter:off` / `@formatter:on` where formatting is intentional; otherwise carefully insert code manually preserving existing alignment
- Do not reformat code unrelated to your change


===== FILE verilator/verilator::docs/AGENTS.md | stars=3773 followers=None lang=SystemVerilog bytes=1999 =====

<!-- DESCRIPTION: Verilator: docs/ guidelines for AI coding agents
     SPDX-FileCopyrightText: 2026-2026 Wilson Snyder
     SPDX-License-Identifier: LGPL-3.0-only OR Artistic-2.0 -->

# docs/ Guidelines -- Verilator documentation (\*.rst)

When to check: before editing anything under `docs/`.
Read the repository-root [AGENTS.md](../AGENTS.md) first for process and cross-cutting rules.

## Writing rules

- Rewrap paragraphs after editing -- keep consistent line length in `*.rst` files.

- Document only stable, implemented features -- never planned or in-development capabilities; prevents user confusion and support burden.

- Explain WHAT and WHEN, not HOW -- conceptual purpose and practical use cases over implementation mechanics; describe behavior ("optimized as pure", not "treated as pure") and clarify ambiguous referents ("in the internals of Verilator").

- Keep terminology consistent -- one term per concept; update docs when renaming code constructs; spell out full terms, avoiding abbreviations like "sim"/"sims".

- Use "how many" for countable nouns (threads, tasks, workers) and "how much" for uncountable quantities.

- Mark internal or experimental features "for internal use only" -- prevents user dependence and forced deprecation cycles later.

- Use specific IEEE references: `IEEE {number}-{year}` plus the section (e.g. `Annex I`) -- a vague "IEEE spec requires" is unverifiable.

- Document all flags with descriptions, not just syntax.

## reStructuredText mechanics

- Use the `:vlopt:` role for Verilator option references -- makes cross-references clickable and consistent.

- Escape angle brackets (`\<`, `\>`) in link targets -- prevents broken links to command-line options.

- Generate documentation examples with `test.extract` from `test_regress` test files -- examples stay synced with actually tested behavior.

## Hard constraint

- Never edit `docs/CONTRIBUTORS` -- only humans may, after reading and agreeing to its statement; remind the user instead.


===== FILE home-assistant/android::AGENTS.md | stars=3765 followers=None lang=Kotlin bytes=5386 =====

# Home Assistant Companion for Android Agent Guide

You are helping develop the Home Assistant Companion for Android, the official Android app for the Home Assistant home automation platform. The app centers around a WebView for Home Assistant's frontend, enhanced with native features like background sensors, notifications, widgets, Wear OS, and Android Automotive. The project is entirely written in Kotlin and must stay that way.

Detailed developer documentation lives at https://developers.home-assistant.io/docs/android (sources at https://github.com/home-assistant/developers.home-assistant).

## Essential Commands

```bash
./gradlew assembleDebug                                    # Debug build (full and minimal flavors)
./gradlew test                                             # Unit tests (:common:test for one module)
./gradlew :build-logic:convention:ktlintFormat ktlintFormat  # Format code, run before committing
./gradlew ktlintCheck :build-logic:convention:ktlintCheck --continue  # Check code style
./gradlew lint --continue                                  # Android linter
./gradlew validateDebugScreenshotTest                      # Screenshot tests
./gradlew alldependencies --write-locks                    # Update dependency locks after any dependency change
```

## Architecture

- Gradle modules: `:app` (mobile), `:automotive` (reuses `:app` sources), `:wear`, `:common` (shared data layer, sensors, WebSocket, REST API), `:testing-unit` (shared test utilities, independent from `:common`), `:lint` (custom lint rules), and `build-logic` (convention plugins via `includeBuild`).
- `:app` and `:automotive` have two flavors: `full` (Google Play Services) and `minimal` (FOSS). Keep code in the `main` source set flavor-agnostic whenever possible.
- Key technologies: Jetpack Compose (all new UI), Hilt (DI), Kotlin Coroutines and Flow (all concurrency), Room, Retrofit + OkHttp, Kotlinx.serialization, Timber (logging).
- Source lives under `src/main/kotlin/io/homeassistant/companion/android/`, packaged by feature (`sensors/`, `notifications/`, `settings/`, `onboarding/`, `widgets/`, `frontend/`, ...). `frontend/` hosts the frontend screen (the WebView rendering the Home Assistant frontend) and the external bus that communicates with it; `webview/` is the legacy implementation being removed.
- Min SDK versions are defined in `gradle/libs.versions.toml` (`androidSdk-min`, `androidSdk-automotive-min`, `androidSdk-wear-min`).

## Development Standards

- Kotlin only, all code and comments in English.
- Use named constants instead of magic numbers or strings, and sealed classes/interfaces instead of strings or enums for logic control.
- Use immutable data classes; produce changes through `copy()` or functions returning new instances.
- Keep functions small (under 50 lines) with meaningful names; default to `private`/`internal` visibility.
- Document every public function, focusing on functionality rather than implementation details.
- All displayed strings go in the value files in `:common`, English only, accessed via `stringResource`.
- Gate new features on the server version, for example `serverManager.getServer()?.version?.isAtLeast(2025, 6, 0) == true`.
- Never use `System.currentTimeMillis`; inject `kotlin.time.Clock` through Hilt.
- When JetBrains IDE (Android Studio) capabilities are available to you, prefer them over raw text edits and grep: use Rename refactoring for renames, Find Usages for impact analysis, Safe Delete, and Change Signature. They understand Kotlin semantics across all Gradle modules, where plain text search misses generated code, XML references, and overloads.

## Project Skills

Detailed guidance lives in project skills under `.agents/skills/`. Load the matching skill before detailed implementation or review:

- `ha-android-architecture`: modules, flavors, layers, repositories, use cases, Hilt, storage and encryption, and networking.
- `ha-android-ui`: Compose screens, ViewModels, state/events, HATheme design system, navigation, and widgets.
- `ha-android-kotlin-style`: constants, strong types, immutability, time types, naming, and documentation.
- `ha-android-concurrency`: coroutines, dispatchers, thread safety, and lifecycle scoping.
- `ha-android-logging-errors`: Timber, sensitive data, FailFast, and exception handling.
- `ha-android-testing`: JUnit, MockK, Robolectric, Turbine, screenshot tests, and test naming.
- `ha-android-review`: reviewing a diff for correctness, style, convention adherence, and security.
- `ha-android-committing`: finalizing a change — format, tests, changelog, branch naming, and pull requests.
- `ha-android-skill-maintenance`: updating AGENTS.md or the skills when guidance is missing, stale, or corrected.

## Pull Requests

When creating a pull request, use `.github/pull_request_template.md` as the PR body. Keep PRs small and focused. If the change is visible to end users, add it to the changelog in `app/src/main/res/xml/changelog_master.xml`. Before committing, format with ktlint and run the tests.

## AI policy

This project follows the [Open Home Foundation AI Policy](AI_POLICY.md).
Autonomous contributions are not accepted: a human must review, understand,
and be able to explain every change before it is submitted. Do not open
issues or pull requests autonomously, and do not post comments on behalf of
a user without their review.


===== FILE standardagents/arrow-js::docs/AGENTS.md | stars=3709 followers=None lang=TypeScript bytes=19383 =====

# Arrow.js Docs — Agent Guide

This is the Arrow.js documentation site, built with Arrow's own meta-framework
on Vite 8. It must be a model citizen of Arrow.js usage: proper components, SSR,
hydration, and reactive patterns throughout.

## Project structure

```
docs/
  server.mjs              Vite 8 custom app server (dev + prod)
  index.html              HTML shell with <!--app-head/html/payload--> slots
  vite.config.ts          Vite 8 config with SSR environment
  src/
    entry-server.ts       SSR entry: renderToString → HTML + payload
    entry-client.ts       Client entry: readPayload → hydrate
    app.ts                Route dispatch: URL → page factory
    layout.ts             Shared layout shell
    styles/main.css       Tailwind 4 + custom theme tokens
    components/           Shared UI components (Header, Footer, etc.)
    pages/
      home/               Landing page sections
      docs/               Documentation page + content sections
```

## Package imports

Always import from the published package names, never from relative source paths:

```ts
// Core runtime (~3KB) — always available on client AND server
import { html, reactive, watch, component, pick, props } from '@arrow-js/core'
import type { ArrowTemplate, Props, Reactive, Computed } from '@arrow-js/core'

// Framework layer — async components, boundaries, render context
import { boundary, render, toTemplate, renderDocument } from '@arrow-js/framework'

// SSR — server only
import { renderToString, serializePayload } from '@arrow-js/ssr'

// Hydration — client only
import { hydrate, readPayload } from '@arrow-js/hydrate'
```

Short aliases exist but prefer the full names for readability:
- `html` / `t` — template tag
- `reactive` / `r` — reactive proxy
- `watch` / `w` — watcher
- `component` / `c` — component wrapper

## Code Example Architecture

The docs site no longer runs Shiki/Twoslash in the browser on page load.
Highlighting is now SSR/build-time only for the HTML docs pages, while the
Markdown endpoints render plain code blocks.

Current source of truth:

- `docs/src/server-code-highlight.ts`
  Server-only Shiki/Twoslash loader and DOM post-processor.
- `docs/src/components/highlighted-section.ts`
  Wraps static docs/API sections in async components that resolve highlighted
  HTML on the server and serialize the result into hydration snapshots.
- `docs/src/components/CodeBlock.ts`
  Used for code blocks inside otherwise interactive sections like `Quickstart`
  and `Hero`.
- `docs/src/components/TsCodeBlock.ts`
  Still used for partial Twoslash examples. It preserves the full hidden source
  in `data-code-source` and shows a trimmed preview.
- `docs/src/entry-client.ts`
  Only hydrates, imports Twoslash CSS, and repositions popups. It must not
  eagerly import Shiki/Twoslash runtime code.
- `docs/src/entry-server.ts`
  Renders normal HTML pages with highlighted code, but renders `/docs.md` and
  `/api.md` with `highlightCode: false`.

Implications:

1. Do not reintroduce browser-side startup highlighting.
   `docs/src/highlight.ts` is legacy. Do not wire it back into
   `entry-client.ts` unless you are intentionally undoing the bundle-size work.

2. Static sections should use `highlightedSection(...)`.
   This is the preferred path for docs/API sections that contain code blocks but
   no interactive state that must hydrate inside the section body.

3. Interactive sections should use `CodeBlock(...)`.
   Use this for places like the hero card or `Quickstart`, where the surrounding
   section contains live UI and cannot be collapsed into a raw HTML snapshot.

4. Markdown pages must stay on the plain path.
   `/docs.md` and `/api.md` are generated from `createPage(url, { highlightCode: false })`.
   If you add new highlighted rendering paths, make sure the plain path still
   works and still produces clean markdown-compatible markup.

5. Keep the highlighter server-only.
   Any import of `shiki`, `@shikijs/twoslash`, or `twoslash-cdn` should stay
   behind SSR-only code paths so those chunks do not appear in the client build.

## TypeScript Example Authoring

The Twoslash sandbox still exists, but it now runs during SSR/build instead of
in the browser. The docs sandbox is configured in:

- `docs/src/server-code-highlight.ts`
- `docs/play/arrow-types.d.ts`
- `docs/src/components/TsCodeBlock.ts`

Follow these rules when adding or editing TypeScript examples:

1. Prefer real exported package types.
   Use actual public exports from `@arrow-js/core`, `@arrow-js/framework`,
   `@arrow-js/ssr`, and `@arrow-js/hydrate` whenever possible. Do not show
   placeholder aliases like `type Foo = unknown` in visible docs code.

2. Use `TsCodeBlock()` for partial examples.
   If the visible snippet omits setup, imports, or helper declarations, wrap the
   example with `TsCodeBlock()` and hide the extra context with:
   - `// ---cut-start---`
   - `// ---cut-end---`
   - `// ---cut-before---`
   - `// ---cut-after---`

3. Keep hidden context minimal.
   Hide only the scaffolding required to make the snippet a valid standalone
   Twoslash program. Do not hide the actual API being documented.

4. Do not hand-write public package types in docs examples.
   If a docs example needs a type, import the official exported type directly.
   If the package does not export the type cleanly enough for docs usage, export
   it from the package first instead of recreating it in the docs.

5. For type reference sections, show official declaration excerpts instead of
   import-only lists.
   If readers need to understand the shape of a type, render the declaration
   excerpt sourced from the package code or emitted type declarations, not just
   `import type { ... }` lines.

6. Keep `arrow-types.d.ts` thin.
   That file should primarily mirror real package exports plus a small amount of
   docs-only support code, such as local fake modules like `./App` or helper
   assertion utilities. Do not turn it into a second source of truth for public
   API types.

7. If a snippet imports a local example module, wire it into the Twoslash fsMap.
   Add the file content to the `fsMap` in `docs/src/server-code-highlight.ts`
   so imports like `./App` resolve inside the docs sandbox.

---

## Core API reference

### `html` — Tagged template literal

Creates an `ArrowTemplate` — a function that mounts DOM to a parent node.

```ts
import { html } from '@arrow-js/core'

// Static template — renders once, no reactivity overhead
const greeting = html`<h1>Hello, world</h1>`

// Mount to DOM:
greeting(document.getElementById('app'))

// Or get a DocumentFragment (no parent):
const fragment = greeting()
```

**Expressions in templates:**

- **Static** (render once): any non-function value
  ```ts
  html`<p>${someString}</p>`
  ```
- **Reactive** (live updates): wrap in an arrow function
  ```ts
  html`<p>${() => data.count}</p>`
  ```
- **Templates/components**: nest directly
  ```ts
  html`<div>${otherTemplate}</div>`
  html`<div>${MyComponent({ label: 'hi' })}</div>`
  ```
- **Lists**: return an array of templates
  ```ts
  html`<ul>${() => items.map(i => html`<li>${i.name}</li>`)}</ul>`
  ```
- **Events**: `@eventName` attribute
  ```ts
  html`<button @click="${(e) => handleClick(e)}">Click</button>`
  ```
- **Attributes**: static or reactive
  ```ts
  html`<div class="${staticClass}"></div>`
  html`<div class="${() => data.active ? 'on' : 'off'}"></div>`
  ```
  Returning `false` from an attribute expression removes the attribute.
- **IDL properties**: prefix with `.`
  ```ts
  html`<input .value="${() => data.text}" />`
  ```

**Key rule**: expressions are *static by default*. Only function expressions
(`() => ...`) create reactive bindings. This keeps the static path cheap.

### `reactive` — Observable state

```ts
import { reactive } from '@arrow-js/core'

// Plain object → reactive proxy
const data = reactive({ count: 0, items: [] })

data.count++               // triggers observers
data.items.push('hello')   // array mutations trigger parent observers

// Computed value → reactive(() => expression)
const totals = reactive({
  total: reactive(() => data.count * 10)
})
totals.total  // reads like a normal value, auto-updates

// Manual subscription (prefer watch() or template expressions instead)
data.$on('count', (newVal, oldVal) => { ... })
data.$off('count', callback)
```

**Rules:**
- Only objects and arrays can be reactive. Primitives cannot.
- Nested objects are lazily made reactive on first access.
- `reactive()` on an already-reactive object returns the same proxy.
- Computed values are created with `reactive(() => expr)` and auto-update.

### `watch` — Side effects

```ts
import { reactive, watch } from '@arrow-js/core'

const data = reactive({ price: 25, quantity: 10 })

// Single-effect form: runs immediately, re-runs when tracked reads change
watch(() => {
  console.log(`Total: ${data.price * data.quantity}`)
})

// Getter + effect form: getter tracks, effect receives result
watch(
  () => data.price * data.quantity,
  (total) => console.log(`Total: ${total}`)
)
```

**Rules:**
- Dependencies are auto-discovered from reactive reads inside the watcher.
- Dependencies that are no longer read on subsequent runs are dropped.
- Returns `[returnValue, stop]` — call `stop()` to unsubscribe.

### `component` — Stable component instances

This is the key abstraction. Components wrap a factory function to provide
**stable local state** across parent re-renders.

```ts
import { component, html, reactive } from '@arrow-js/core'
import type { Props } from '@arrow-js/core'

// Define a component:
const Counter = component((props: Props<{ count: number }>) => {
  // This factory runs ONCE per render slot.
  // Local state survives parent re-renders.
  const local = reactive({ clicks: 0 })

  return html`<button @click="${() => local.clicks++}">
    Root count ${() => props.count} | Local clicks ${() => local.clicks}
  </button>`
})

// Use in a template:
const state = reactive({ count: 1 })
html`${Counter(state)}`
```

**Critical rules:**
1. The factory function runs **once per slot**, not on every update.
2. **Never destructure props** at the top of the factory — read them lazily
   inside reactive expressions so updates flow through:
   ```ts
   // WRONG — captures value once, never updates:
   const Counter = component(({ count }) => {
     return html`<p>${count}</p>`
   })

   // RIGHT — reads lazily, stays reactive:
   const Counter = component((props) => {
     return html`<p>${() => props.count}</p>`
   })
   ```
3. Use `pick(source, ...keys)` or `props(source, ...keys)` to narrow a large
   reactive object down to the keys a component needs:
   ```ts
   import { pick } from '@arrow-js/core'

   const state = reactive({ count: 1, theme: 'dark', locale: 'en' })
   html`${Counter(pick(state, 'count'))}`
   ```
4. Use `.key()` when rendering components in keyed lists:
   ```ts
   html`${() => items.map(item =>
     ItemCard(item).key(item.id)
   )}`
   ```
5. Factory must return an `ArrowTemplate` (the result of `html\`...\``).

### Async components

When the Arrow framework runtime is loaded (`@arrow-js/framework`,
`@arrow-js/ssr`, or `@arrow-js/hydrate`), `component()` also accepts async
factories:

```ts
import { component, html } from '@arrow-js/core'
import { boundary } from '@arrow-js/framework'

const UserName = component(async ({ id }: { id: string }) => {
  const user = await fetch(`/api/users/${id}`).then(r => r.json())
  return user.name  // resolved value rendered directly by default
})

// Always wrap async components in a boundary for SSR/hydration recovery:
html`${boundary(UserName({ id: '42' }), { idPrefix: 'user' })}`
```

**Options bag (all optional):**
```ts
component(asyncFactory, {
  fallback: html`<span>Loading...</span>`,         // shown while pending
  render: (value, props) => html`<p>${value}</p>`,  // custom render
  onError: (error, props) => html`<p>Error</p>`,    // error handler
  serialize: (value, props) => value.id,             // custom SSR snapshot
  deserialize: (snapshot, props) => ({ id: snapshot }), // restore on client
  idPrefix: 'user',                                  // readable SSR ids
})
```

**Rules:**
- SSR waits for all async components to resolve before returning HTML.
- JSON-safe results are auto-serialized into the hydration payload.
- On hydration, matching components resume from serialized data (no refetch).
- Always use `boundary()` around async component output.

---

## SSR + Hydration architecture

This site uses a standard Arrow SSR flow:

### Server (`entry-server.ts`)

```ts
import { renderToString, serializePayload } from '@arrow-js/ssr'
import { routeToPage } from './app'

export async function renderPage(url: string) {
  const page = routeToPage(url)
  const result = await renderToString(page.view)

  return {
    html: result.html,
    head: `<title>${page.title}</title>`,
    payloadScript: serializePayload({
      ...result.payload,
      path: url,
    }),
    status: 200,
  }
}
```

### Client (`entry-client.ts`)

```ts
import { hydrate, readPayload } from '@arrow-js/hydrate'
import { routeToPage } from './app'

const payload = readPayload()
const root = document.getElementById('app')!

await hydrate(root, routeToPage(window.location.pathname).view, payload)
```

### How it works

1. Server calls `renderToString(view)` → returns `{ html, payload }`.
2. Payload is serialized as a `<script type="application/json">` tag.
3. Server injects HTML + payload into `index.html` template slots.
4. Client reads payload with `readPayload()`, then calls `hydrate()`.
5. Hydration reconciles the existing DOM with the client template.
6. If a subtree mismatches, `boundary()` markers enable targeted recovery.

### `boundary(view, options)` — Hydration boundaries

Wrap subtrees that need independent recovery during hydration:

```ts
import { boundary } from '@arrow-js/framework'

html`
  <main>
    ${boundary(SomeComponent(), { idPrefix: 'sidebar' })}
    ${boundary(OtherComponent(), { idPrefix: 'content' })}
  </main>
`
```

This inserts `<template data-arrow-boundary-start/end>` markers so the
hydrator can repair individual regions instead of replacing the entire root.

---

## When to use `component()` vs plain functions

| Pattern | Use when |
|---------|----------|
| Plain function returning `html\`...\`` | Static or compositional content with no local state. Pages, sections, layout wrappers. |
| `component(factory)` | The UI has **local state** that must survive parent re-renders, or receives **reactive props** that update over time. Interactive widgets, toggles, forms. |
| `component(async factory)` | The UI needs to **fetch data** or perform async work. Combined with `boundary()` for SSR. |

### Plain function example (static content)

```ts
// This is fine for content sections — no local state needed
export function Introduction() {
  return html`
    <section>
      <h2>What is Arrow?</h2>
      <p>Arrow is a small reactive UI runtime...</p>
    </section>
  `
}
```

### Component example (interactive widget)

```ts
// This needs component() because it has local state
const ThemeToggle = component(() => {
  const state = reactive({ theme: 'dark' })

  return html`
    <button @click="${() => {
      state.theme = state.theme === 'dark' ? 'light' : 'dark'
      document.documentElement.setAttribute('data-theme', state.theme)
    }}">
      ${() => state.theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </button>
  `
})
```

---

## Template patterns for this project

### Tailwind classes in templates

Arrow templates are HTML strings — Tailwind utility classes work directly:

```ts
html`<div class="flex items-center gap-4 px-6 py-3 bg-white dark:bg-zinc-950">
  <span class="text-sm font-medium text-zinc-600 dark:text-zinc-400">
    ${() => props.label}
  </span>
</div>`
```

### Conditional rendering

```ts
// Reactive conditional — use a function expression
html`${() => data.isOpen
  ? html`<div class="dropdown">...</div>`
  : ''
}`

// Static conditional — no function wrapper needed
html`${isDocsPage ? Navigation() : ''}`
```

### List rendering

```ts
html`<ul>
  ${() => data.items.map(item =>
    html`<li>${item.name}</li>`.key(item.id)
  )}
</ul>`
```

### Nesting components

```ts
html`
  <div>
    ${Header()}
    <main>${content}</main>
    ${Footer()}
  </div>
`
```

Components and templates compose by nesting — no special slot or children API.

---

## File conventions

- **TypeScript** throughout (`*.ts`). The project uses strict mode.
- Components that hold local state: use `component()`, name as `PascalCase` const.
- Static view functions: plain functions, `PascalCase` export name.
- One component/function per file when it's substantial; group small related ones.
- Import `html`, `reactive`, `watch`, `component` from `@arrow-js/core`.
- Import `boundary` from `@arrow-js/framework` when wrapping async components.

## Styling

- **Tailwind CSS 4** via `@tailwindcss/vite` plugin.
- CSS lives in `src/styles/main.css` — imports Tailwind, defines theme tokens.
- Dark mode: `@custom-variant dark` keyed to `data-theme="dark"` on `<html>`.
- Brand color: `arrow-500` (#ffb000) and its scale (`arrow-50` through `arrow-950`).
- Fonts: Inter (sans), JetBrains Mono (mono) — loaded from Google Fonts.
- Use Tailwind utilities in templates. Avoid custom CSS unless truly shared
  (code blocks, callouts, nav links).

## Development

```sh
pnpm dev               # Start dev server on http://127.0.0.1:4174
pnpm build             # Build client + SSR bundles
pnpm preview           # Preview production build
```

## Common mistakes to avoid

1. **Passing HTML strings as template expressions:**
   ```ts
   // Bug — renders as escaped text, not DOM:
   const icon = `<svg>...</svg>`
   html`<div>${icon}</div>`

   // Fix — use an html template so Arrow renders it as DOM:
   function Icon() {
     return html`<svg>...</svg>`
   }
   html`<div>${Icon()}</div>`
   ```

2. **Forgetting the function wrapper for reactive expressions:**
   ```ts
   // Bug — renders once, never updates:
   html`<p>${data.count}</p>`
   // Fix:
   html`<p>${() => data.count}</p>`
   ```

3. **Destructuring component props:**
   ```ts
   // Bug — captures values once:
   const Foo = component(({ x, y }) => html`<p>${x}, ${y}</p>`)
   // Fix — read props lazily:
   const Foo = component((props) => html`<p>${() => props.x}, ${() => props.y}</p>`)
   ```

4. **Using `component()` when a plain function suffices:**
   Static content sections don't need component wrappers. Only use `component()`
   when local state or stable instance identity matters.

5. **Forgetting `boundary()` around async components:**
   Without a boundary, hydration mismatches in async regions force a full
   root replacement instead of targeted repair.

6. **Using browser APIs during SSR:**
   `localStorage`, `window`, `document.querySelector` etc. don't exist during
   `renderToString()`. Guard with runtime checks or move to client-only code
   paths (e.g., inside `entry-client.ts` or behind `typeof window !== 'undefined'`).

7. **Not calling `.key()` on list-rendered components:**
   Without keys, list patches reuse slots by position. If items reorder,
   local component state will attach to the wrong item.


===== FILE Osmantic/ODS::CLAUDE.md | stars=3640 followers=None lang=Python bytes=9187 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ODS is a fully local AI stack (LLM inference, chat, voice, agents, workflows, RAG, image generation, privacy tools) deployed on user hardware with a single command. It supports Linux (NVIDIA + AMD), Windows (WSL2), and macOS (Apple Silicon). The project is primarily Bash (installer/CLI), Python (dashboard-api, services), and React/Vite (dashboard UI).

## Repository Structure

The repo has two layers:

- **Root level** — outer wrapper with top-level README, install scripts (`install.sh`, `install.ps1`), and CI workflows (`.github/workflows/`)
- **`ods/`** — the core product containing all deployable code

Within `ods/`:

- **`install-core.sh`** — thin orchestrator that sources libs then runs phases in order
- **`installers/lib/`** — pure function libraries (constants, logging, UI, GPU detection, tier mapping, packaging, compose selection)
- **`installers/phases/`** — 13 sequential install steps (`01-preflight` through `13-summary`), each sourced by install-core
- **`installers/macos/`**, **`installers/windows/`** — platform-specific installer variants
- **`extensions/services/`** — 24 bundled service manifests, each a directory with `manifest.yaml` + optional `compose.yaml` and GPU overlays
- **`extensions/library/`** — optional extension catalog, templates, workflows, and manifest schema used by the dashboard Extensions page
- **`docker-compose.base.yml`** — core service definitions; `docker-compose.{amd,nvidia,apple}.yml` are GPU overlays
- **`ods-cli`** — main Bash CLI for managing the stack; keep changes narrow and follow `docs/ODS_CLI_DECOMPOSITION.md` for behavior-preserving split work
- **`config/`** — backend configs (`backends/amd.json`, `nvidia.json`, etc.), GPU database, LiteLLM config, hardware classes
- **`extensions/services/dashboard-api/`** — Python FastAPI backend (with `routers/`, `tests/`)
- **`extensions/services/dashboard/`** — React + Vite + Tailwind frontend (`src/`)
- **`scripts/`** — operational scripts (health checks, model management, compose stack resolution, doctor, preflight)
- **`tests/`** — shell-based tests (tier map, contracts, smoke tests, integration)
- **`lib/`** — shared Bash utilities (safe-env, service-registry, progress, QR code)

## Build & Development Commands

All commands run from `ods/` directory unless noted.

### Linting and Validation

```bash
make lint          # Shell syntax check (bash -n) + Python compile check
make test          # Unit/contract tests: tier map, installer, AMD/Lemonade, overlays, secrets, etc.
make smoke         # Platform smoke tests (linux-amd, linux-nvidia, wsl, macos)
make simulate      # Installer simulation harness
make gate          # Full pre-release: lint + test + BATS + smoke + simulate
make doctor        # Run diagnostic report
```

### Running a Single Test

```bash
bash tests/test-tier-map.sh                      # Tier mapping tests
bash tests/contracts/test-installer-contracts.sh  # Installer contracts
bash tests/contracts/test-preflight-fixtures.sh   # Preflight fixtures
bash tests/smoke/linux-nvidia.sh                  # Single smoke test
```

### Dashboard API (Python/FastAPI)

```bash
cd extensions/services/dashboard-api
pytest tests/                    # Run all dashboard-api tests
pytest tests/test_routers.py     # Run a specific test file
```

### Dashboard UI (React/Vite)

```bash
cd extensions/services/dashboard
npm install
npm run dev      # Dev server
npm run build    # Production build
npm run lint     # ESLint
```

### Pre-commit Hooks

The root `.pre-commit-config.yaml` runs gitleaks (secret scanning), private key detection, and large file checks. Install with:
```bash
pip install pre-commit && pre-commit install
```

## CI Workflows

GitHub Actions in `.github/workflows/`:
- **lint-shell.yml** — ShellCheck on all `.sh` files
- **lint-python.yml** — Python linting
- **type-check-python.yml** — Python type checking
- **dashboard.yml** — Dashboard build/lint
- **test-linux.yml** — Linux test suite + installer simulation (uploads artifacts)
- **matrix-smoke.yml** — Multi-distro smoke tests (6 distros)
- **validate-compose.yml** — Docker Compose validation
- **secret-scan.yml** — Secret scanning
- **lint-powershell.yml** — PowerShell linting for Windows installer

## Architecture Key Concepts

### Installer Architecture

The installer is modular with a strict separation: `installers/lib/` contains pure functions (no side effects), `installers/phases/` contain sequential steps that execute on `source`. Every module has a standardized header (Purpose, Expects, Provides, Modder notes). The orchestrator (`install-core.sh`) sets `INSTALL_PHASE` before each phase for error reporting.

### Extension System

Every service is an extension under `extensions/services/<name>/`. Each has a `manifest.yaml` defining metadata (id, port, health endpoint, container name, aliases, category, GPU backends, feature flags). Extensions with `compose.yaml` get auto-merged into the Docker Compose stack by `scripts/resolve-compose-stack.sh`. Core services (llama-server, open-webui, dashboard, dashboard-api) only have manifests — their compose lives in `docker-compose.base.yml`.

### GPU Backend / Tier System

GPU detection (`installers/lib/detection.sh`) identifies hardware and maps it to a tier via `installers/lib/tier-map.sh`. Backend configs in `config/backends/{amd,nvidia,apple,cpu}.json` define per-tier model selections. The compose stack is layered: `docker-compose.base.yml` + `docker-compose.{amd,nvidia,apple}.yml`.

### Docker Compose Layering

The stack uses compose file merging. `scripts/resolve-compose-stack.sh` dynamically discovers enabled extension compose files and merges them with base + GPU overlay. Services bind to `127.0.0.1` by default for security.

### Dashboard API

FastAPI app in `extensions/services/dashboard-api/` with modular routers (`routers/agents.py`, `features.py`, `privacy.py`, `setup.py`, `updates.py`, `workflows.py`). Uses API key auth (`security.py`), GPU detection (`gpu.py`), and service health monitoring (`helpers.py`).

## Code Style

- **Shell**: Bash with `set -euo pipefail`. Use `shellcheck` for linting. POSIX-compatible constructs preferred for macOS portability (avoid GNU-only date/grep).
- **Python**: Standard formatting, consistent with existing file style. FastAPI for APIs. Pytest for tests.
- **JavaScript/React**: ESLint with flat config. Vite for bundling. Tailwind CSS for styling.

## Design Philosophy

Priority order when principles conflict: **Let It Crash > KISS > Pure Functions > SOLID**.

### Error Handling Rules

1. **No broad or silent catches.** Never `except Exception: pass` or `except Exception: return None`. No retry/backoff loops. No fallback chains.
2. **Narrow exceptions at I/O boundaries are fine.** Health checks, network calls, and file I/O may catch *specific* exception types (e.g., `asyncio.TimeoutError`, `aiohttp.ClientConnectorError`) when each maps to a distinct, meaningful status.
3. **Internal functions: let exceptions propagate.** The default is zero error handling — errors crash visibly with a full stack trace.
4. **Bash: `set -euo pipefail` everywhere.** Errors kill the process. Use `trap` handlers for context (see `install-core.sh`). If you must tolerate a failure, log it: `some_command || warn "failed (non-fatal)"`. Never `|| true` or `2>/dev/null`.
5. **Python boundaries: raise, don't swallow.** FastAPI routers validate input and `raise HTTPException`. Never return `None` to signal an error.
6. **Tests: let assertions fail visibly.** Never catch exceptions in tests to avoid failure. A crash in a test is a signal, not a problem.

### KISS

- Readable over clever. Explicit over implicit.
- One function, one job. Flatten deep nesting with early returns.
- No premature abstraction — wait for 3+ use cases.
- Thresholds: functions > 30 lines, nesting > 3 levels, files > 500 lines → consider splitting.

### Pure Functions

- Default to pure for business logic, validation, data mapping (same inputs → same output, no side effects).
- Push I/O to boundaries. Follow **functional core, imperative shell** — `installers/lib/` is the pure core, `installers/phases/` is the imperative shell.
- If purity adds excessive wiring, prefer a simple impure function with a comment.

### SOLID (apply pragmatically)

- **SRP**: Each module/function has one reason to change (installer phases, FastAPI routers).
- **OCP**: Extend via config/data (extension manifests, backend JSON files), not code modification.
- **DIP**: Inject dependencies via env vars (Bash) and `Depends()` (FastAPI). Don't hardcode.
- Don't over-engineer. For simple utilities, pragmatism > purity.

## Key File Paths

- Tier mapping logic: `ods/installers/lib/tier-map.sh`
- GPU detection: `ods/installers/lib/detection.sh`
- Service manifests: `ods/extensions/services/*/manifest.yaml`
- Compose stack resolver: `ods/scripts/resolve-compose-stack.sh`
- Environment schema: `ods/.env.schema.json`
- Environment example: `ods/.env.example`


===== FILE huggingface/blog::agents.md | stars=3477 followers=None lang=Jupyter Notebook bytes=25252 =====

---
title: "License to Call: Introducing Transformers Agents 2.0"
thumbnail: /blog/assets/agents/thumbnail.png
authors:
  - user: m-ric
  - user: lysandre
  - user: pcuenq
---

# License to Call: Introducing Transformers Agents 2.0

## TL;DR

We are releasing Transformers Agents 2.0!

⇒ 🎁 On top of our existing agent type, we introduce two new agents that **can iterate based on past observations to solve complex tasks**.

⇒ 💡 We aim for the code to be **clear and modular, and for common attributes like the final prompt and tools to be transparent**.

⇒ 🤝 We add **sharing options** to boost community agents.

⇒ 💪 **Extremely performant new agent framework**, allowing a Llama-3-70B-Instruct agent to outperform GPT-4 based agents in the GAIA Leaderboard!

🚀 Go try it out and climb ever higher on the GAIA leaderboard!

> [!WARNING]
> `transformers.agents` has now been upgraded to the stand-alone library [smolagents](https://github.com/huggingface/smolagents)! The two libraries have very similar APIs, so switching is easy.
> Go checkout the `smolagents` introduction blog [here](https://huggingface.co/blog/smolagents).

## Table of Contents

- [What is an agent?](#what-is-an-agent)
- [The Transformers Agents approach](#the-transformers-agents-approach)
    - [Main elements](#main-elements)
- [Example use-cases](#example-use-cases)
    - [Self-correcting Retrieval-Augmented-Generation](#self-correcting-retrieval-augmented-generation)
    - [Using a simple multi-agent setup 🤝 for efficient web browsing](#using-a-simple-multi-agent-setup-for-efficient-web-browsing)
- [Testing our agents](#testing-our-agents)
    - [Benchmarking LLM engines](#benchmarking-llm-engines)
    - [Climbing up the GAIA Leaderboard with a multi-modal agent](#climbing-up-the-gaia-leaderboard-with-a-multi-modal-agent)
- [Conclusion](#conclusion)

## What is an agent?

Large Language Models (LLMs) can tackle a wide range of tasks, but they often struggle with specific tasks like logic, calculation, and search. When prompted in these domains in which they do not perform well, they frequently fail to generate a correct answer.

One approach to overcome this weakness is to create an **agent**, which is just a program driven by an LLM. The agent is empowered by **tools** to help it perform actions. When the agent needs a specific skill to solve a particular problem, it relies on an appropriate tool from its toolbox.

Thus when during problem-solving the agent needs a specific skill, it can just rely on an appropriate tool from its toolbox.

Experimentally, agent frameworks generally work very well, achieving state-of-the-art performance on several benchmarks. For instance, have a look at [the top submissions for HumanEval](https://paperswithcode.com/sota/code-generation-on-humaneval): they are agent systems.

## The Transformers Agents approach

Building agent workflows is complex, and we feel these systems need a lot of clarity and modularity. We launched Transformers Agents one year ago, and we’re doubling down on our core design goals.

Our framework strives for:

- **Clarity through simplicity:** we reduce abstractions to the minimum. Simple error logs and accessible attributes let you easily inspect what’s happening and give you more clarity.
- **Modularity:** We prefer to propose building blocks rather than full, complex feature sets. You are free to choose whatever building blocks are best for your project.
    - For instance, since any agent system is just a vehicle powered by an LLM engine, we decided to conceptually separate the two, which lets you create any agent type from any underlying LLM.

On top of that, we have **sharing features** that let you build on the shoulders of giants!

### Main elements

- `Tool`: this is the class that lets you use a tool or implement a new one. It is composed mainly of a callable forward `method` that executes the tool action, and a set of a few essential attributes: `name`, `descriptions`, `inputs` and `output_type`. These attributes are used to dynamically generate a usage manual for the tool and insert it into the LLM’s prompt.
- `Toolbox`: It's a set of tools that are provided to an agent as resources to solve a particular task. For performance reasons, tools in a toolbox are already instantiated and ready to go. This is because some tools take time to initialize, so it’s usually better to re-use an existing toolbox and just swap one tool, rather than re-building a set of tools from scratch at each agent initialization.
- `CodeAgent`: a very simple agent that generates its actions as one single blob of Python code. It will not be able to iterate on previous observations.
- `ReactAgent`: ReAct agents follow a cycle of Thought ⇒ Action ⇒ Observation until they’ve solve the task. We propose two classes of ReactAgent:
    - `ReactCodeAgent` generates its actions as python blobs.
    - `ReactJsonAgent` generates its actions as JSON blobs.

Check out [the documentation](https://huggingface.co/docs/transformers/en/main_classes/agent) to learn how to use each component!

How do agents work under the hood?

In essence, what an agent does is “allowing an LLM to use tools”. Agents have a key `agent.run()` method that:

- Provides information about tool usage to your LLM in a **specific prompt**. This way, the LLM can select tools to run to solve the task.
- **Parses** the tool calls from the LLM output (can be via code, JSON format, or any other format).
- **Executes** the calls.
- If the agent is designed to iterate on previous outputs, it **keeps a memory** with previous tool calls and observations. This memory can be more or less fine-grained depending on how long-term you want it to be.

<p align="center">
    <img src="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/agents/agent_single_multistep.png" alt="graph of agent workflows" width=90%>
</p>


For more general context about agents, you could read [this excellent blog post](https://lilianweng.github.io/posts/2023-06-23-agent/) by Lilian Weng or [our earlier blog post](https://huggingface.co/blog/open-source-llms-as-agents) about building agents with LangChain.


To take a deeper dive in our package, go take a look at the [agents documentation](https://huggingface.co/docs/transformers/en/transformers_agents).


## Example use cases

In order to get access to the early access of this feature, please first install `transformers` from its `main` branch:
```
pip install "git+https://github.com/huggingface/transformers.git#egg=transformers[agents]"
```
Agents 2.0 will be released in the v4.41.0 version, landing mid-May.


### Self-correcting Retrieval-Augmented-Generation

Quick definition: Retrieval-Augmented-Generation (RAG) is “using an LLM to answer a user query, but basing the answer on information retrieved from a knowledge base”. It has many advantages over using a vanilla or fine-tuned LLM: to name a few, it allows to ground the answer on true facts and reduce confabulations, it allows to provide the LLM with domain-specific knowledge, and it allows fine-grained control of access to information from the knowledge base.

Let’s say we want to perform RAG, and some parameters must be dynamically generated. For example, depending on the user query we could want to restrict the search to specific subsets of the knowledge base, or we could want to adjust the number of documents retrieved. The difficulty is: how to dynamically adjust these parameters based on the user query?

Well, we can do this by giving our agent an access to these parameters!

Let's setup this system. 

Run the line below to install the required dependencies:
```
pip install langchain sentence-transformers faiss-cpu
```

We first load a knowledge base on which we want to perform RAG: this dataset is a compilation of the documentation pages for many `huggingface` packages, stored as markdown.

```python
import datasets
knowledge_base = datasets.load_dataset("m-ric/huggingface_doc", split="train")
```

Now we prepare the knowledge base by processing the dataset and storing it into a vector database to be used by the retriever. We are going to use LangChain, since it features excellent utilities for vector databases:

```python
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

source_docs = [
    Document(
        page_content=doc["text"], metadata={"source": doc["source"].split("/")[1]}
    ) for doc in knowledge_base
]

docs_processed = RecursiveCharacterTextSplitter(chunk_size=500).split_documents(source_docs)[:1000]

embedding_model = HuggingFaceEmbeddings("thenlper/gte-small")
vectordb = FAISS.from_documents(
    documents=docs_processed,
    embedding=embedding_model
)
```

Now that we have the database ready, let’s build a RAG system that answers user queries based on it!

We want our system to select only from the most relevant sources of information, depending on the query.

Our documentation pages come from the following sources:

```python
>>> all_sources = list(set([doc.metadata["source"] for doc in docs_processed]))
>>> print(all_sources)

['blog', 'optimum', 'datasets-server', 'datasets', 'transformers', 'course',
'gradio', 'diffusers', 'evaluate', 'deep-rl-class', 'peft',
'hf-endpoints-documentation', 'pytorch-image-models', 'hub-docs']
```

How can we select the relevant sources based on the user query?

👉 Let us build our RAG system as an agent that will be free to choose its sources!

We create a retriever tool that the agent can call with the parameters of its choice:

```python
import json
from transformers.agents import Tool
from langchain_core.vectorstores import VectorStore

class RetrieverTool(Tool):
    name = "retriever"
    description = "Retrieves some documents from the knowledge base that have the closest embeddings to the input query."
    inputs = {
        "query": {
            "type": "text",
            "description": "The query to perform. This should be semantically close to your target documents. Use the affirmative form rather than a question.",
        },
        "source": {
            "type": "text", 
            "description": ""
        },
    }
    output_type = "text"
    
    def __init__(self, vectordb: VectorStore, all_sources: str, **kwargs):
        super().__init__(**kwargs)
        self.vectordb = vectordb
        self.inputs["source"]["description"] = (
	        f"The source of the documents to search, as a str representation of a list. Possible values in the list are: {all_sources}. If this argument is not provided, all sources will be searched."
	      )

    def forward(self, query: str, source: str = None) -> str:
        assert isinstance(query, str), "Your search query must be a string"

        if source:
            if isinstance(source, str) and "[" not in str(source): # if the source is not representing a list
                source = [source]
            source = json.loads(str(source).replace("'", '"'))

        docs = self.vectordb.similarity_search(query, filter=({"source": source} if source else None), k=3)

        if len(docs) == 0:
            return "No documents found with this filtering. Try removing the source filter."
        return "Retrieved documents:\n\n" + "\n===Document===\n".join(
            [doc.page_content for doc in docs]
        )
```

Now it’s straightforward to create an agent that leverages this tool!

The agent will need these arguments upon initialization:
- *`tools`*: a list of tools that the agent will be able to call.
- *`llm_engine`*: the LLM that powers the agent.

Our `llm_engine` must be a callable that takes as input a list of [messages](https://huggingface.co/docs/transformers/main/chat_templating) and returns text. It also needs to accept a `stop_sequences` argument that indicates when to stop its generation. For convenience, we directly use the `HfEngine` class provided in the package to get a LLM engine that calls our [Inference API](https://huggingface.co/docs/api-inference/en/index).

```python
from transformers.agents import HfEngine, ReactJsonAgent

llm_engine = HfEngine("meta-llama/Meta-Llama-3-70B-Instruct")

agent = ReactJsonAgent(
    tools=[RetrieverTool(vectordb, all_sources)],
    llm_engine=llm_engine
)

agent_output = agent.run("Please show me a LORA finetuning script")

print("Final output:")
print(agent_output)
```

Since we initialized the agent as a `ReactJsonAgent`, it has been automatically given a default system prompt that tells the LLM engine to process step-by-step and generate tool calls as JSON blobs (you could replace this prompt template with your own as needed).

Then when its `.run()` method is launched, the agent takes care of calling the LLM engine, parsing the tool call JSON blobs and executing these tool calls, all in a loop that ends only when the final answer is provided.

And we get the following output:

```
Calling tool: retriever with arguments: {'query': 'LORA finetuning script', 'source': "['transformers', 'datasets-server', 'datasets']"}
Calling tool: retriever with arguments: {'query': 'LORA finetuning script'}
Calling tool: retriever with arguments: {'query': 'LORA finetuning script example', 'source': "['transformers', 'datasets-server', 'datasets']"}
Calling tool: retriever with arguments: {'query': 'LORA finetuning script example'}
Calling tool: final_answer with arguments: {'answer': 'Here is an example of a LORA finetuning script: https://github.com/huggingface/diffusers/blob/dd9a5caf61f04d11c0fa9f3947b69ab0010c9a0f/examples/text_to_image/train_text_to_image_lora.py#L371'}

Final output:
Here is an example of a LORA finetuning script: https://github.com/huggingface/diffusers/blob/dd9a5caf61f04d11c0fa9f3947b69ab0010c9a0f/examples/text_to_image/train_text_to_image_lora.py#L371
```

We can see the self-correction in action: the agent first tried to restrict sources, but due to the lack of corresponding documents it ended up not restricting sources at all.

We can verify that by inspecting the llm output at the logs for step 2: `print(agent.logs[2]['llm_output'])`

```
Thought: I'll try to retrieve some documents related to LORA finetuning scripts from the entire knowledge base, without any source filtering.

Action:
{
  "action": "retriever",
  "action_input": {"query": "LORA finetuning script"}
}
```

### Using a simple multi-agent setup 🤝 for efficient web browsing

In this example, we want to build an agent and test it on the GAIA benchmark ([Mialon et al. 2023](https://huggingface.co/papers/2311.12983)). GAIA is an extremely difficult benchmark, with most questions requiring several steps of reasoning using different tools. A specifically difficult requirement is to have a powerful web browser, able to navigate to pages with specific constraints: discovering pages using the website’s inner navigation, selecting specific articles in time...

Web browsing requires diving deeper into subpages and scrolling through lots of text tokens that will not be necessary for the higher-level task-solving. We assign the web-browsing sub-tasks to a specialized web surfer agent. We provide it with some tools to browse the web and a specific prompt (check the repo to find specific implementations).

Defining these tools is outside the scope of this post: but you can check [the repository](https://github.com/aymeric-roucher/agent_reasoning_benchmark) to find specific implementations.

```python
from transformers.agents import ReactJsonAgent, HfEngine

WEB_TOOLS = [
    SearchInformationTool(),
    NavigationalSearchTool(),
    VisitTool(),
    DownloadTool(),
    PageUpTool(),
    PageDownTool(),
    FinderTool(),
    FindNextTool(),
]

websurfer_llm_engine = HfEngine(
    model="CohereForAI/c4ai-command-r-plus"
)  # We choose Command-R+ for its high context length

websurfer_agent = ReactJsonAgent(
    tools=WEB_TOOLS,
    llm_engine=websurfer_llm_engine,
)
```

To allow this agent to be called by a higher-level task solving agent, we can simply encapsulate it in another tool:

```python
class SearchTool(Tool):
    name = "ask_search_agent"
    description = "A search agent that will browse the internet to answer a question. Use it to gather informations, not for problem-solving."

    inputs = {
        "question": {
            "description": "Your question, as a natural language sentence. You are talking to an agent, so provide them with as much context as possible.",
            "type": "text",
        }
    }
    output_type = "text"

    def forward(self, question: str) -> str:
        return websurfer_agent.run(question)
```

Then we initialize the task-solving agent with this search tool:

```python
from transformers.agents import ReactCodeAgent

llm_engine = HfEngine(model="meta-llama/Meta-Llama-3-70B-Instruct")
react_agent_hf = ReactCodeAgent(
    tools=[SearchTool()],
    llm_engine=llm_engine,
)
```

Let's run the agent with the following task:

> *Use density measures from the chemistry materials licensed by Marisa Alviar-Agnew & Henry Agnew under the CK-12 license in LibreText's Introductory Chemistry materials as compiled 08/21/2023.*
> *I have a gallon of honey and a gallon of mayonnaise at 25C. I remove one cup of honey at a time from the gallon of honey. How many times will I need to remove a cup to have the honey weigh less than the mayonaise? Assume the containers themselves weigh the same.*
> 

```
Thought: I will use the 'ask_search_agent' tool to find the density of honey and mayonnaise at 25C.
==== Agent is executing the code below:
density_honey = ask_search_agent(question="What is the density of honey at 25C?")
print("Density of honey:", density_honey)
density_mayo = ask_search_agent(question="What is the density of mayonnaise at 25C?")
print("Density of mayo:", density_mayo)
===
Observation:
Density of honey: The density of honey is around 1.38-1.45kg/L at 20C. Although I couldn't find information specific to 25C, minor temperature differences are unlikely to affect the density that much, so it's likely to remain within this range.
Density of mayo: The density of mayonnaise at 25°C is 0.910 g/cm³.

===== New step =====
Thought: I will convert the density of mayonnaise from g/cm³ to kg/L and then calculate the initial weights of the honey and mayonnaise in a gallon. After that, I will calculate the weight of honey after removing one cup at a time until it weighs less than the mayonnaise.
==== Agent is executing the code below:
density_honey = 1.42 # taking the average of the range
density_mayo = 0.910 # converting g/cm³ to kg/L
density_mayo = density_mayo * 1000 / 1000 # conversion

gallon_to_liters = 3.785 # conversion factor
initial_honey_weight = density_honey * gallon_to_liters
initial_mayo_weight = density_mayo * gallon_to_liters

cup_to_liters = 0.236 # conversion factor
removed_honey_weight = cup_to_liters * density_honey
===
Observation:

===== New step =====
Thought: Now that I have the initial weights of honey and mayonnaise, I'll try to calculate the number of cups to remove from the honey to make it weigh less than the mayonnaise using a simple arithmetic operation.
==== Agent is executing the code below:
cups_removed = int((initial_honey_weight - initial_mayo_weight) / removed_honey_weight) + 1
print("Cups removed:", cups_removed)
final_answer(cups_removed)
===
>>> Final answer: 6
```

✅ And the answer is **correct**!

## Testing our agents

Let’s take our agent framework for a spin and benchmark different models with it!

All the code for the experiments below can be found [here](https://github.com/aymeric-roucher/agent_reasoning_benchmark).

### Benchmarking LLM engines

The `agents_reasoning_benchmark` is a small - but mighty- reasoning test for evaluating agent performance. This benchmark was already used and explained in more detail in [our earlier blog post](https://huggingface.co/blog/open-source-llms-as-agents). 

The idea is that the choice of tools you use with your agents can radically alter performance for certain tasks. So this benchmark restricts the set of tools used to a calculator and a basic search tool. We picked questions from several datasets that could be solved using only these two tools:

- **30 questions from [HotpotQA](https://huggingface.co/datasets/hotpot_qa)** ([Yang et al., 2018](https://huggingface.co/papers/1809.09600)) to test search tool usage.
- **40 questions from [GSM8K](https://huggingface.co/datasets/gsm8k)** ([Cobbe et al., 2021](https://huggingface.co/papers/2110.14168)) to test calculator usage.
- **20 questions from [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA)** ([Mialon et al., 2023](https://huggingface.co/papers/2311.12983)) to test the usage of both tools for solving difficult questions.

Here we try 3 different engines: [Mixtral-8x7B](https://huggingface.co/mistralai/Mixtral-8x7B-Instruct-v0.1), [Llama-3-70B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-70B-Instruct), and [GPT-4 Turbo](https://platform.openai.com/docs/models).

<p align="center">
    <img src="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/agents/aggregate_score.png" alt="benchmark of agent performances" width=90%>
</p>

The results are shown above - as the average of two complete runs for more precision. We also tested [Command-R+](https://huggingface.co/CohereForAI/c4ai-command-r-plus) and [Mixtral-8x22B](https://huggingface.co/mistralai/Mixtral-8x22B-Instruct-v0.1), but do not show them for clarity.

⇒ **Llama-3-70B-Instruct leads the Open-Source models: it is on par with GPT-4**, and it’s especially strong in a `ReactCodeAgent`  thanks to Llama 3’s strong coding performance!

💡 It's interesting to compare JSON- and Code-based React agents: with less powerful LLM engines like Mixtral-8x7B, Code-based agents do not perform as well as JSON, since the LLM engine frequently fails to generate good code. But the Code version really shines with more powerful models as engines: in our experience, the Code version even outperforms the JSON with Llama-3-70B-Instruct. As a result, we use the Code version for our next challenge: testing on the complete GAIA benchmark.

### Climbing up the GAIA Leaderboard with a multi-modal agent

[GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) ([Mialon et al., 2023](https://huggingface.co/papers/2311.12983)) is an extremely difficult benchmark: you can see in the `agent_reasoning_benchmark` above that models do not perform above 50% even though we cherry-picked tasks that could be solved with 2 basic tools.

Now we want to get a score on the complete set, we do not cherry-pick questions anymore. Thus we have to cover all modalities, which leads us to use these specific tools:
- `SearchTool`: the web browser defined above.
- `TextInspectorTool`: open documents as text files and return their content.
- `SpeechToTextTool`: transcribe audio files to text. We use the default tool based on [distil-whisper](https://huggingface.co/distil-whisper/distil-large-v3).
- `VisualQATool`: analyze images visually. For these we use the shiny new [Idefics2-8b-chatty](https://huggingface.co/HuggingFaceM4/idefics2-8b-chatty)!

We first initialize these toole (for more detail, inspect the code in the [repository](https://github.com/aymeric-roucher/agent_reasoning_benchmark)).

Then we initialize our agent:

```python
from transformers.agents import ReactCodeAgent, HfEngine

TASK_SOLVING_TOOLBOX = [
    SearchTool(),
    VisualQATool(),
    SpeechToTextTool(),
    TextInspectorTool(),
]

react_agent_hf = ReactCodeAgent(
    tools=TASK_SOLVING_TOOLBOX,
    llm_engine=HfEngine(model="meta-llama/Meta-Llama-3-70B-Instruct"),
    memory_verbose=True,
)
```

And after some time needed to complete the 165 questions, we submit our result to the [GAIA Leaderboard](https://huggingface.co/spaces/gaia-benchmark/leaderboard), and… 🥁🥁🥁

<p align="center">
    <img src="https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/agents/leaderboard.png" alt="GAIA leaderboard" width=90%>
</p>

⇒ Our agent ranks 4th: it beats many GPT-4-based agents, and is now the reigning contender for the Open-Source category!


## Conclusion

We will keep improving this package in the coming months. We have already identified several exciting paths in our development roadmap:
- More agent sharing options: for now you can push or load tools from the Hub, we will implement pushing/loading agents too.
- Better tools, especially for image processing.
- Long-term memory management.
- Multi-agent collaboration.

👉 **Go try out transformers agents!** We’re looking forward to receiving your feedback and your ideas.

Let’s fill the top of the leaderboard with more open-source models! 🚀

> [!WARNING]
> `transformers.agents` has now been upgraded to the stand-alone library [smolagents](https://github.com/huggingface/smolagents)! The two libraries have very similar APIs, so switching is easy.
> Go checkout the `smolagents` introduction blog [here](https://huggingface.co/blog/smolagents).

===== FILE momo5502/sogen::AGENTS.md | stars=3432 followers=1880 lang=C++ bytes=2600 =====

# Repository Guidelines

## Project Overview

Sogen is a C++20 Windows user-space emulator.
It produces an `analyzer` binary that analyzes and emulates windows binaries.
Details and commandline options can be found in `src/analyzer/main.cpp`

## Build

For fast iterations during development, build the release preset:

`cmake --build --preset=release`

When fully done implementing a feature, make sure to build the tidy configuration, which includes clang-tidy.
It's very slow, so only use it at the end:

`cmake --build --preset=tidy`

## Smoke tests

Execute `analyzer.exe -s test-sample.exe` for smoke tests using the cmd in the directory of the built preset.
E.g.: `cmd /c "cd build\release\artifacts\ && analyzer.exe -s test-sample.exe"`

Other applications can also be executed in the emulator:
`cmd /c "cd build\release\artifacts\ && analyzer.exe -s path/to/binary.exe arg1 arg2 ..."`

## Code comments

The default is **no comment**. Write code that explains itself through naming and structure instead.

A comment is only justified when it carries information that is *not recoverable from the code*, and that a
competent developer reading this file would otherwise get wrong. In practice that means:

- A non-obvious external constraint: a Windows/NT behaviour, an undocumented structure layout, a hardware or
  emulator quirk that forces the code into a shape that otherwise looks wrong.
- A deliberate deviation: why the obvious approach was *not* taken, when the code alone would make a reader
  want to "fix" it.
- A reference that saves someone a research session: a spec section, an MSDN structure, a known-bug link.

Never write:

- Restatements of the code (`// increment the counter`, `// call the handler`, `// loop over the modules`).
- Section headers or banners inside a function (`// --- setup ---`, `// Step 3: cleanup`).
- Narration of your own edit or reasoning (`// changed to fix X`, `// this is safe because ...`, `// now uses Y`).
  This is talking to the reviewer, not to the next reader, and it is noise the moment the change is merged.
- Docstring-style headers that just spell out the signature in prose.
- Obvious type or scope information (`// pointer to the process`).

If you are unsure whether a comment qualifies, it does not. Leave it out. A change that adds zero comments is a
perfectly good change; a change that sprinkles comments over otherwise readable code will be rejected.

## Development notes

- Run clang-format on changed files to ensure consistent formatting
- Do not use shortcuts or workarounds. Always prefer clean and idiomatic solutions.


===== FILE conversejs/converse.js::AGENTS.md | stars=3281 followers=None lang=JavaScript bytes=17710 =====

# Converse.js Agent Guidelines

**Converse.js** is an XMPP chat client built with JavaScript and web tech.
It has a plugin-based architecture, uses JSDoc TypeScript type definitions,
Bootstrap 5 and Lit UI components.

## Project Overview

- **Type**: XMPP/Jabber web-based chat client
- **Build Tool**: Rspack (Webpack-compatible)
- **UI Framework**: Lit (Web Components)
- **Testing**: Vitest (browser mode, Playwright/Chromium) with a Jasmine-compat shim
- **Styling**: SCSS with Bootstrap 5
- **Language**: JavaScript
- **Type System**: TypeScript via JSDoc annotations

## Monorepo

Three npm workspaces:

- **Root** (`/`): Main package with UI plugins (`src/plugins/`)
- **Headless** (`src/headless/`): Core XMPP logic and state management, separate package `@converse/headless`
  The `@converse/headless` package resolves to the built bundle (`dist/converse-headless.js`),
  **not** to individual source files. Importing from relative paths pointing to `src/headless/`
  back into the main package like `src/plugins` is forbidden since they cross the package boundary.

    Read: src/headless/AGENTS.md

- **Log** (`src/log/`): Logging utility, separate package `@converse/log`

### Key Entry Points

- `src/index.js` — Main entry
- `src/headless/index.js` — Headless entry
- `rspack/` — Build configs

### Directory Structure

```
src/
├── headless/             # Core XMPP logic (separate package @converse/headless)
│   ├── plugins/          # Headless plugins (chat, muc, roster, etc.)
│   ├── shared/           # Shared headless utilities
│   ├── types/            # Generated TypeScript definitions
│   └── dist/             # Built headless package
├── plugins/              # UI plugins
│   ├── chatview/         # Chat UI
│   ├── muc-views/        # Multi-user chat UI
│   ├── rosterview/       # Contact list UI
│   └── controlbox/       # Main control panel
├── shared/               # Shared UI components
│   ├── components/       # Reusable Lit components
│   ├── chat/             # Chat-related shared components
│   ├── modals/           # Modal dialogs
│   └── styles/           # Shared SCSS files
├── templates/            # Lit template functions
├── i18n/                 # Internationalization
│   └── locales/          # Translation files (.po)
├── types/                # Generated TypeScript definitions
└── utils/                # Utility functions
media/                    # Sponsor logos (separate repo: conversejs/media)
```

#### Media Repository

Sponsor logos are stored in a separate repository at `https://github.com/conversejs/media`.
This repo should be checked out to the `media/` directory and is git-ignored in the main repo.
Without this repo, sponsor logos in `index.html` and the fullscreen footer will show as broken images.

## Essential Commands

### Development

```bash
# Development build (unminified, with debugger statements)
npm run dev                   # Build everything in dev mode
npm run dev:headless          # Build only headless package

# Watch mode (auto-rebuild on changes)
npm run watch                 # Watch both headless and main
npm run watch:headless        # Watch only headless
npm run watch:main            # Watch only main package

# Dev server with live reload
npm run devserver             # Starts on http://localhost:8080

# Serve static files
npm run serve                 # Serves on http://localhost:8000 (default)
npm run serve -- -p 8008      # Serve on custom port
npm run serve-tls             # HTTPS server (requires certs/)
```

### Building

```bash
# Production build (minified)
npm run build                 # Full build: headless + ESM + CJS + CSS
npm run build:headless        # Build headless package only
npm run build:esm             # Build ESM bundle
npm run build:cjs             # Build CommonJS bundle
npm run build:website-css     # Build website CSS
npm run build:website-min-css # Build and minify website CSS

# Special builds
npm run nodeps                # Build without dependencies
npm run cdn                   # Build for CDN deployment
```

### Testing

- **Framework**: Vitest browser mode (Playwright/Chromium) with a Jasmine-compat shim (`vitest/setup.jasmine-shim.js`)
- **Test files**: Located in `tests/` subdirectory of each plugin (auto-discovered by glob — no manual registration)
- **Naming**: `*.js` (e.g., `chatbox.js`, `actions.js`, `corrections.js`)
- **Mock data**: `src/headless/tests/mock.js` and `src/shared/tests/mock.js`

**`npm test` is single-run by default** (it maps to `vitest run`); no `--single-run` flag is needed. Use
`npm run test:browser` for a headed/watch session.

**Always run `npm run dev` before running tests.** Vitest runs against the pre-built `dist/converse.js` bundle,
not source files directly. If you skip the build, you will be testing against a stale bundle and changes to source
files will have no effect.

**The full test suite takes over a minute to run.** Avoid running it unless you need to verify that nothing has
regressed across the entire codebase. When working on a specific feature, pass a file path or use `fdescribe`/`fit`
(see below).

```bash
# Always build first, then test
npm run dev && npm test

npm test                                    # Run main UI tests (headless Chromium)
npm run test:all                            # Run both headless and main tests
npm run test:headless                       # Run headless (core XMPP) tests only
cd src/headless && npm test                 # Alternative way to run headless tests

# Run only specific files (fastest turnaround) — pass a path/substring to vitest
npx vitest run --project main src/plugins/chatview/tests/messages.js
```

> **Which suite to run?** Tests for plugins under `src/headless/` (e.g. smacks, roster,
> status, presence) live in the **headless** suite and will not be picked up by `npm test`.
> Use `npm run test:headless` (or `npm run dev:headless` before it) when
> working in that area. `npm test` only covers the UI plugins under `src/plugins/`.

```bash
# Full test suite (as used in CI) — slow, use sparingly
make check                    # Runs lint + types + all tests
```

#### Creating new test files

Just drop the `*.js` file in a plugin's `tests/` directory — Vitest discovers it via the
`include` globs in `vitest.config.js`. No manual registration is required (unlike the old
Karma `files` array). Non-spec helpers in a `tests/` dir must be added to `commonExclude`
in `vitest.config.js` so they aren't collected as empty test files.

#### Focusing tests with `fdescribe` / `fit`

**Prefer scoping a run to a file (`npx vitest run --project main path/to/test.js`), or
`fdescribe`/`fit`, over `-t`/`--testNamePattern`.** To focus within a file, temporarily
change `describe` → `fdescribe` or `it` → `fit`, then revert before committing. (The shim
aliases `fdescribe`/`fit` to Vitest's `.only`; note a focused test only narrows within its
own file, so combine it with a file path when running the whole suite.)

```javascript
// Focus an entire suite:
fdescribe('Message Reactions (XEP-0444)', function () { ... });

// Focus a single test:
fit('sends a correct XEP-0444 stanza when a reaction is added', ...);
```

**Always revert `fdescribe`/`fit` back to `describe`/`it` before committing.**

#### Jasmine shim vs. native Vitest APIs

`vitest/setup.jasmine-shim.js` is a thin, **additive** compatibility layer (`spyOn`,
`jasmine.*`, `fdescribe`/`fit`, `toEqualStanza`, matchers like `toBeTrue`/`toHaveSize`) that
lets the existing Jasmine-era specs run unchanged. It does **not** shadow Vitest.

**Write new tests with native Vitest APIs** (`vi.fn`, `vi.spyOn().mockReturnValue()`,
`vi.useFakeTimers`, native matchers). Both styles work and can be mixed in one file:
`globals: true` injects `vi`/`expect`/`describe`/`it` (no imports), `expect` is *extended*
(native + Jasmine matchers coexist), and `spyOn()` returns the underlying Vitest mock (so
`spy.and.returnValue(x)`/`spy.calls.count()` and `spy.mockReturnValue(x)`/
`expect(spy).toHaveBeenCalledOnce()` both work on the same spy).

Two caveats, independent of style:
- **`vi.mock()` can't stub Converse internals** — specs import the prebuilt `dist/converse.js`
  bundle (modules are inlined, no path to intercept). Stub at runtime: `vi.spyOn(converse.env.X, …)`,
  `vi.spyOn(SomeClass.prototype, …)`, `vi.stubGlobal('Notification', …)`.
- **No `.concurrent`** — the suite needs serial execution + shared browser state
  (`fileParallelism: false`, `isolate: false`); concurrent tests break cumulative storage state.

### Code Quality

```bash
# Linting
npm run lint                  # Run ESLint on all source files

# Type checking
npm run types:check           # TypeScript type checking (no emit)
npm run types                 # Generate type definitions
```

## Code Style and Conventions

### Formatting (Prettier)

- **Files**: `kebab-case.js`
- **Variables**: `snake_case` (`camelCase` for variables referring to functions)
- **Classes**: `PascalCase`
- **Constants**: `UPPER_CASE`
- **Private methods**: `#privateMethod()`
- **Templates**: `tplPlaceholder`
- **Unused vars**: prefix with `_`
- **Logging**: use `log.debug/info/warn/error` from `@converse/log`, not `console`
- **Prettier**: single quotes, 120 line width, 4-space indent, `spaceBeforeFunctionParen`
- **Line endings**: LF

## Architecture

### Plugin System

Converse.js uses a **plugin-based architecture** powered by `pluggable.js`:

- **Headless plugins** (`src/headless/plugins/`): Core XMPP logic, no UI
    - Examples: `chat`, `muc`, `disco`, `roster`, `ping`, `bookmarks`
- **UI plugins** (`src/plugins/`): Visual components that depend on headless
    - Examples: `chatview`, `muc-views`, `rosterview`, `controlbox`

### Plugin Structure

Every plugin follows this pattern:

```javascript
import { _converse, api, converse } from '@converse/headless';

converse.plugins.add('plugin-name', {
    dependencies: ['other-plugin-1', 'other-plugin-2'], // Other plugins that should be loaded first

    initialize() {
        // Extend Converse's settings with new plugin-specific ones.
        api.settings.extend({
            some_setting: 'default_value',
        });

        // Export models/views for other plugins
        const exports = { MyClass, myFunction };
        Object.assign(_converse.exports, exports);

        // Extend API
        Object.assign(api, my_api_methods);

        // Register event listeners
        api.listen.on('connected', () => {
            /* ... */
        });
    },
});
```

### Plugin Design Philosophy

Converse.js mirrors the XMPP philosophy: a minimal core with features implemented as
plugins corresponding to individual XEPs.

**Avoiding leaky abstractions:** Shared core code (`src/headless/shared/`, e.g.
`model-with-messages.js`) must not contain logic specific to a particular plugin.
Plugin-specific logic belongs in the plugin itself.

**Use hooks and events:** When you need to allow other plugins to participate in a processing flow.

- **Hooks** (`api.hook(name, context, data)`) are chainable async pipelines — each
  listener receives the output of the previous one and can modify the data before passing
  it along. Use hooks when the caller needs a return value or when the data should be
  transformed by plugins.
- **Events** (`api.trigger(name, data)`) are fire-and-forget notifications. Use events
  when plugins need to be informed of something but the caller does not need a response.

**Example:**

```javascript
// In the foundational chat plugin (chat/model.js):
const { handled } = await api.hook('beforeMessageCreated', this, attrs, { handled: false });
if (handled) return;

// In a higher-level plugin (e.g. reactions):
api.listen.on('beforeMessageCreated', (chatbox, attrs, data) => {
    if (attrs.reaction_to_id && !targetExists(chatbox, attrs)) {
        storeDanglingReaction(chatbox, attrs);
        return { ...data, handled: true };
    }
    return data;
});
```

### Import Patterns

```javascript
// Headless core imports
import { _converse, api, converse } from '@converse/headless';

// Logging
import { log } from '@converse/log';

// Lit framework
import { html, css } from 'lit';

// Relative imports for local files
import ChatView from './chat.js';
import './styles/index.scss';

// Utilities
import { u } from '@converse/headless'; // Utility functions
const { dayjs, Strophe, sizzle } = converse.env; // Common libraries
```

#### Using utility functions from @converse/headless

Headless utility methods are exposed via the `u` object from `@converse/headless`/

```javascript
import { converse } from '@converse/headless';
const { u } = converse.env;
```

**Wrong approach:**

```javascript
// DON'T cross the package boundary with relative paths or unexported subpaths:
import { getOwnReactionJID } from '../../headless/plugins/reactions/utils.js'; // ❌ relative path
import { getOwnReactionJID } from '@converse/headless/plugins/reactions/utils.js'; // ❌ unexported subpath
```

### Component Patterns

**Lit Components** extend `CustomElement`:

```javascript
import { html } from 'lit';
import { CustomElement } from 'shared/components/element.js';

export default class MyComponent extends CustomElement {
    static get properties() {
        return {
            model: { type: Object },
            some_state: { state: true }, // Internal state
        };
    }

    async initialize() {
        await this.model.initialized;
        // Listen to model changes to trigger re-render
        this.listenTo(this.model, 'change', () => this.requestUpdate());
        this.requestUpdate();
    }

    render() {
        return html`<div>...</div>`;
    }
}
customElements.define('my-component', MyComponent);
```

**Templates** are functions returning `html` tagged templates:

```javascript
import { html } from 'lit';

export default (model) => html`
    <div class="chat-message">
        <span>${model.get('from')}</span>
        <p>${model.get('body')}</p>
    </div>
`;
```

### API Usage Patterns

```javascript
// Settings
api.settings.extend({ 'my_setting': 'default' });
api.settings.get('my_setting');

// Events (fire-and-forget notifications)
api.listen.on('connected', callback);
api.trigger('customEvent', data);

// Hooks (chainable async pipelines — each listener receives and can modify the data)
// Use hooks when a caller needs plugins to intercept or transform data.
const result = await api.hook('hookName', context, data);
api.listen.on('hookName', (context, data) => {
    return { ...data, modified: true }; // Return modified data to pass along the chain
});

// Promises
await api.waitUntil('connected');

// User interaction
const confirmed = await api.confirm('Are you sure?');
await api.alert('Something happened');
```

## TypeScript and Type Definitions

See `tsconfig.json`

### JSDoc for Types

Add JSDoc comments to document types in `.js` files:

### Type Checking

```bash
npm run types:check  # Check types without generating files
npm run types        # Generate type definitions
```

## Styling

### SCSS Organization

- **Framework**: Bootstrap 5 (imported from node_modules)
- **Location**: Component-specific styles in plugin directories
- **Shared styles**: `src/shared/styles/` (alerts, badges, buttons, forms, etc.)
- **Import paths**: Rspack configured with `node_modules/` and `src/` as includePaths

### CSS Loading

Styles are imported directly in JavaScript:

```javascript
import './styles/chat-content.scss';
```

Rspack uses `style-loader` + `css-loader` + `postcss-loader` + `sass-loader` to process and inject styles.

## Internationalization (i18n)

### Translation System

- **Library**: Jed (Gettext for JavaScript)
- **Format**: PO files in `src/i18n/locales/*/LC_MESSAGES/converse.po`

### Using Translations

```javascript
import { __ } from '@converse/headless';

const message = __('Hello, %1$s!', username);
```

## Common Patterns and Gotchas

### 1. Async Initialization

Models and collections are initialized asynchronously:

```javascript
await this.model.initialized; // Wait for model
await this.model.messages.fetched; // Wait for data fetch
```

### 2. Event Listening

Use Backbone-style event listeners (automatically cleaned up):

```javascript
this.listenTo(this.model, 'change', () => this.requestUpdate());
this.listenTo(this.model.messages, 'add', this.onMessageAdded);
```

### 3. Waiting for Conditions

Use utility functions to wait:

```javascript
await u.waitUntil(() => sizzle('.chat-msg', view).length > 0);
await api.waitUntil('connected');
```

### 4. Accessing Converse Internals

```javascript
import { _converse, api, converse } from '@converse/headless';

// Access global state via `_converse.state` (use sparingly, prefer api)
const { chatboxes } = _converse.state;
const chatbox = chatboxes.get(jid);

// Access 3rd party libraries
const { Strophe, $msg, $iq, $pres, $build, stx } = converse.env;
```

### 5. Memory Leaks Prevention

- Always use `listenTo` instead of `on` (auto-cleanup on disconnect)
- Call `stopListening()` in `disconnectedCallback()`

## Release Process

Read: RELEASE.md

## Documentation

- **Source**: `docs/src/content/docs/` (Markdown)
- **Framework**: Starlight (Astro)
- **Build**: `make doc` or `npm run docs:build`
- **Dev server**: `npm run docs:dev`
- **Output**: `docs/dist/`
- **Online**: https://conversejs.org/docs/

Generate docs:

```bash
make doc           # Build HTML documentation
npm run docs:dev   # Start dev server with live reload
npm run docs:build # Build for production
```


===== FILE power721/alist-tvbox::CLAUDE.md | stars=3049 followers=None lang=Java bytes=3471 =====

# AGENTS.md

This is the single source of truth for AI agents (Codex / Claude Code).

---

# 1. Project Overview

AList-TvBox is a Spring Boot 4 (Java 21) + Vue 3 system:

- TVBox VOD API backend
- Cloud storage aggregation (AList)
- Telegram media search engine
- Live streaming aggregator
- Plugin + filter system
- Embedded AList runtime

Base package: cn.har01d.alist_tvbox

---

# 2. Architecture Overview

Controller → Service → Repository → Database

---

## Core Modules

### Storage (storage/)
- 30+ cloud drive adapters
- Strategy pattern
- AList-compatible config generator

### Live (live/)
Multi-platform streaming:
Huya / Douyu / Bilibili / CC / Kuaishou / Douyin

### Telegram Search
- Jsoup scraping
- Caffeine cache
- Media extraction

APIs:
- /tg-search
- /tgsc
- /tgs

### Plugin System
- Spider plugins (.txt)
- Filter plugins (.py)

### Offline Download
- 115 / Guangya / Thunder handlers

### Embedded AList
- subprocess runtime
- WebDAV proxy (/dav/)

---

# 3. Security Model

- X-API-KEY → CLIENT
- Basic Auth → legacy APIs
- Authorization → session tokens

Roles:
- ADMIN
- USER
- CLIENT

---

# 4. Scheduling Jobs

- Index build (22:00 + hourly)
- Douban sync (20:00 / 22:00)
- Share validation (:00 / :30)
- Proxy cleanup (:45)
- Daily cleanup (06:00)

---

# 5. Development Guide

Backend:
mvn clean package
mvn spring-boot:run
mvn test

Frontend:
cd web-ui
npm install
npm run dev
npm run build
npm run lint

---

# 6. Code Rules

## Java
- 4-space indent
- Lombok required
- Service-first design

## DTO Rules
- Must be top-level class
- Must be in dto/

## Frontend
- Vue 3 + TypeScript
- PascalCase components

## Database
- use Flyway migration

## Runtime Packaging
- JVM jar builds are the primary supported deployment target.
- Native Image configuration is retained as an optional build path.
- Native Image support must be validated separately with `mvn clean package -Pnative`.

## Native Image
- All resource files MUST be registered in `META-INF/native-image/resource-config.json`
  - GraalVM only includes explicitly declared resources
  - Missing resources cause runtime "unsupported protocol: resource" errors
- Common patterns:
  - Text/config files: `{"pattern": "filename.txt"}`
  - Directories: `{"pattern": "path/to/dir/.*"}`
  - SQL migrations: `{"pattern": "db/migration/.*"}`, `{"pattern": "db/migration/current/.*\\.sql"}`
- Reflection configuration:
  - **New DTO/entity packages MUST be added to Main.java scan list first**
  - After adding packages or classes, regenerate `reflect-config.json`:
    ```bash
    mvn compile
    java -cp target/classes cn.har01d.alist_tvbox.Main
    ```
  - Main.java scans configured packages (dto/entity/model/domain/storage/etc)
  - Individual classes can be added to `CUSTOM_REFLECTION_CLASSES` list
- Flyway Java migration file must add to src/main/resources/META-INF/services/org.flywaydb.core.api.migration.JavaMigration

---

# 7. Git Workflow

1. worktree per task
2. feature branch
3. no direct main commits
4. PR-based merge
5. cleanup after merge

---

# 8. AI CODING RULES

## Codex Mode
- Minimal patch only
- No refactor unless requested
- Must compile
- No API breaking changes

## Claude Mode
- Analyze before changes
- Prefer simple solutions
- Avoid over-engineering

## Shared Rules
- No cross-layer logic
- No API break
- Keep diffs small

## Documents
- Save all documents to folder docs/
- Save security related documents to folder docs/security/


===== FILE 10miaomiao/bilimiao2::AGENTS.md | stars=2877 followers=None lang=Kotlin bytes=12843 =====

# AGENTS.md - Agent Guidelines for Bilimiao

本文件为在此代码仓库中工作的 AI 代理（agent）提供指导。

**重要：请全程使用中文回答用户问题。**

## 项目概述

bilimiao（哔哩喵~）是哔哩哔哩的第三方安卓客户端，使用 Kotlin 开发。项目正在积极迁移至 Kotlin 多平台（KMP），通过 Compose Multiplatform 支持桌面端（JVM）。技术栈：Jetpack Compose UI、Kodein 依赖注入、OkHttp 网络请求、kotlinx.serialization JSON 序列化。

## 构建命令

```bash
# 调试构建
./gradlew assembleFullDebug          # 完整版（含百度统计、极验验证）
./gradlew assembleFossDebug          # 开源版

# 发布构建
./gradlew assembleFullRelease
./gradlew assembleFossRelease
./gradlew -Pchannel=Github assembleFullRelease  # 指定渠道

# 桌面端
./gradlew :desktop-app:run           # 运行桌面应用

# 测试
./gradlew test
./gradlew testFullDebugUnitTest
./gradlew test --tests "com.a10miaomiao.bilimiao.ExampleUnitTest.addition_isCorrect"

# 代码检查
./gradlew lint
./gradlew app:lintFullDebug

# 清理
./gradlew clean
```

## 模块架构

```
app/                    - 安卓应用入口（MainActivity、Service）
desktop-app/            - 桌面端应用入口（Main.kt）
bilimiao-comm/          - KMP：核心共享库（API、实体、Store、网络、平台抽象）
bilimiao-compose/       - KMP：所有 Compose UI（页面、组件、导航、主题）
bilimiao-download/      - 安卓：下载功能
bilimiao-cover/         - 安卓：封面图片处理
bilimiao-appwidget/     - 安卓：桌面小组件
DanmakuFlameMaster/     - 安卓：弹幕引擎
danmaku-engine/         - KMP：跨平台弹幕引擎
benchmark/              - 安卓：性能基准测试
grpc-generator/         - Protobuf/gRPC 代码生成
```

### KMP 源集结构

`bilimiao-comm` 和 `bilimiao-compose` 均使用 KMP，包含三个源集：
- **commonMain** - 平台无关代码（无 Android 依赖）
- **androidMain** - Android 平台实现
- **desktopMain** - JVM 桌面端实现

**迁移状态**：全部约 150 个 Compose 页面已迁移至 commonMain。

## 核心架构模式

### 依赖注入（Kodein）

DI 容器在入口点创建（`app/MainActivity`、`desktop-app/Main.kt`），Store 注册为单例：

```kotlin
val di = DI.lazy {
    bindSingleton { AppStore(di) }
    bindSingleton { PlayerStore(di) }
    bindSingleton { UserStore(di) }
}
```

在 Composable 中使用 `localDI()` 和 `rememberInstance()`：
```kotlin
val store: AppStore by rememberInstance()
```

ViewModel 使用 `diViewModel` 辅助函数（`bilimiao-compose/common/DiViewModel.kt`）：
```kotlin
val viewModel = diViewModel { di -> MyViewModel(di) }
```

### 平台抽象

通过两种模式抽象平台特定功能：

1. **expect/actual**（用于简单函数、Composable、属性）：
   - `BackHandler`、`WebViewContainer`、`HapticFeedback`、`ImageCacheHelper`、`ImageSaveHelper`、`navigateDeepLink`、`appDataStore`、`MiaoLogger` 等
   - commonMain 中声明 expect，androidMain/desktopMain 中提供 actual 实现

2. **接口 + DI 绑定**（用于复杂服务）：
   - `PlatformContext`、`PlatformProviders`（bilimiao-comm 层）
   - `GeetestVerifier`、`ProxyRepository`、`AppInfo`、`FileStorage`、`DownloadManager`、`VideoPlayerSource` 工厂（bilimiao-compose 层）
   - commonMain 定义接口，androidMain/desktopMain 提供实现，在入口点通过 Kodein 绑定

### 导航系统

使用 Jetpack Compose Navigation 类型化路由。每个页面是 `ComposePage` 的子类（data class 或 object）：

```kotlin
// 页面定义
@Serializable
data class VideoDetailPage(val id: String) : ComposePage() {
    @Composable
    override fun Content() { /* ... */ }
}

// 在 BilimiaoPageRoute.kt 中注册路由
composable<VideoDetailPage>()

// 导航调用
pageNavigation.navigate(VideoDetailPage(id = "BV1xx411c7mu"))
pageNavigation.navigateByUri("bilimiao://video/BV1xx411c7mu")
```

关键文件：
- `BilimiaoPageRoute.kt` - 所有页面的路由注册
- `PageNavigation.kt` - 导航控制器封装
- `PageNavigator.kt` - 导航接口定义
- `BilibiliNavigation.kt` - URL/深链接路由解析

### 状态管理（Store 模式）

Store 继承 `ViewModel` 并实现 `BaseStore<T>`，状态通过 `MutableStateFlow<T>` 持有：

```kotlin
class AppStore(override val di: DI) : ViewModel(), BaseStore<AppStore.State> {
    data class State(var theme: ThemeSettingState? = null, ...)
    override val stateFlow = MutableStateFlow(State())
    override fun copyState() = state.copy()
    fun updateSomething() = setState { /* 修改副本 */ }
}
```

主要 Store：`AppStore`、`PlayerStore`、`UserStore`、`FilterStore`、`MessageStore`、`PlayListStore`、`TimeSettingStore`、`UserLibraryStore`

### 网络层

`MiaoHttp` 封装 OkHttp 进行 HTTP 请求，`BiliApiService` 提供 B站 API URL 构建：

```kotlin
class ArchiveApi {
    fun relation(aid: String) = MiaoHttp.request {
        url = BiliApiService.biliApi("x/web-interface/archive/relation", "aid" to aid)
    }
}
```

- `MiaoHttp`（commonMain）- HTTP 客户端，自动携带 Cookie、buvid 请求头
- `BiliGRPCHttp`（commonMain）- 基于 HTTP 的 gRPC protobuf 调用
- `BiliApiService`（commonMain）- API URL 构建器，聚合所有 API 类实例

### 数据序列化

- 使用 `kotlinx.serialization` 的 `@Serializable` 注解
- `MiaoJson` 提供配置好的 `Json` 实例（ignoreUnknownKeys、isLenient）
- 实体类位于 `bilimiao-comm/src/commonMain/kotlin/com/a10miaomiao/bilimiao/comm/entity/`

### DataStore 偏好设置

`SettingPreferences`（commonMain）定义所有偏好设置键。平台特定的 `appDataStore` 通过 expect/actual 提供。

## 代码风格指南

### Kotlin 约定

1. **命名**
   - 类/对象/接口：`PascalCase`（如 `ArchiveApi`、`ResultInfo`）
   - 函数/属性：`camelCase`（如 `getCookie`、`isSuccess`）
   - 常量：`UPPER_SNAKE_CASE`（如 `GET`、`POST`）
   - 包名：全小写（如 `com.a10miaomiao.bilimiao.comm.apis`）

2. **导入**
   - 使用显式导入（同包除外，不使用通配符导入）
   - 分组：标准库、Android、第三方、项目内，组内按字母序

3. **格式化**
   - 4 空格缩进（Kotlin 默认）
   - 行宽上限 120 字符（Android Studio 默认）
   - 类/函数左花括号不换行
   - 简单函数酌情使用表达式体

4. **类型**
   - 使用 Kotlin 类型系统（无需原生包装类型）
   - 合理使用可空类型（`?`）
   - 优先 `val`，确需可变才用 `var`
   - 数据载体用 `data class`（自带 `equals`/`hashCode`/`toString`）
   - JSON 可序列化类使用 kotlinx.serialization 的 `@Serializable`

5. **空安全**
   - 使用安全调用（`?.`）和 elvis（`?:`）
   - 初始化有保证时优先 `lateinit var` 而非可空
   - 空检查用 `?.let`

6. **协程**
   - 异步操作使用 `suspend` 函数
   - 使用结构化并发（viewModelScope、lifecycleScope）
   - 用 `try-catch` 或 `CoroutineExceptionHandler` 处理异常

### Android/KMP 特定指南

1. **入口点**
   - 遵循 Android 生命周期
   - 使用 Compose，不使用 findViewById
   - 正确处理运行时权限

2. **ViewModel**
   - 使用 AndroidX ViewModel + Kodein 注入
   - 通过 `StateFlow` 暴露状态
   - 自动处理配置变更

3. **网络**
   - 使用 OkHttp 进行 HTTP 请求
   - 用 kotlinx.serialization 解析响应
   - 用自定义异常优雅处理错误
   - 使用 `MiaoLogger` 记录日志

4. **依赖注入**
   - 用 Kodein 模块组织依赖
   - 尽量使用构造函数注入
   - 昂贵依赖使用 lazy delegate

5. **错误处理**
   - 为领域错误创建自定义异常
   - 预期错误用 Result 类型或 try-catch
   - 适当记录日志

### 数据类

```kotlin
@Serializable
data class ResultInfo<T>(
    val code: Int,
    val `data`: T,
    val message: String,
    val ttl: Int,
) {
    val isSuccess get() = code == 0
}
```

### API 类

```kotlin
class ArchiveApi {
    fun relation(aid: String) = MiaoHttp.request {
        url = BiliApiService.biliApi(
            "x/web-interface/archive/relation",
            "aid" to aid
        )
    }
}
```

## 开发约定

- **语言**：全程 Kotlin，代码注释和文档使用中文
- **Java 目标**：JVM 1.8 字节码，JDK 17 编译
- **SDK 版本**：Min SDK 24（app）/ 21（库），Compile SDK 36，Target SDK 35
- **包名**：`com.a10miaomiao.bilimiao.*`（bilimiao-comm），`cn.a10miaomiao.bilimiao.compose.*`（bilimiao-compose）
- **构建变体**：`full`（百度统计、极验验证、AV1 解码器）和 `foss`（开源版）
- **构建类型**：`debug`、`release`、`benchmark`
- **无 ktlint/detekt**，使用 Android Studio 格式化工具
- **Kotlin 代码风格**：gradle.properties 中设为 "official"
- **版本目录**：`gradle/libs.versions.toml` 管理所有依赖版本
- **签名配置**：`app/signing.properties`（已 gitignore）存放发布签名信息

## 目录结构参考

```
bilimiao-comm/src/commonMain/kotlin/com/a10miaomiao/bilimiao/comm/
├── apis/            # B站 API 定义
├── datastore/       # DataStore 偏好设置键
├── db/              # Room 数据库（FilterDatabase、SearchHistoryDatabase）
├── delegate/player/ # 播放器源抽象（BasePlayerSource、VideoPlayerSource、BangumiPlayerSource）
├── entity/          # API 响应数据类
├── miao/            # MiaoJson（序列化）、MiaoLogger
├── network/         # MiaoHttp、BiliApiService、BiliGRPCHttp
├── platform/        # 平台抽象（PlatformContext、CookieProvider 等）
├── store/           # 状态 Store（AppStore、PlayerStore、UserStore 等）
├── toast/           # GlobalToaster（基于 sonner）
└── utils/           # AES/RSA 加密、数字工具

bilimiao-compose/src/commonMain/kotlin/cn/a10miaomiao/bilimiao/compose/
├── base/            # ComposePage、BottomSheetState、PageSearchMethod
├── common/          # 共享工具、平台抽象、DI 辅助、导航
│   ├── auth/        # GeetestVerifier
│   ├── download/    # DownloadManager、LocalPlayerSource
│   ├── emitter/     # SharedFlowEmitter（事件总线）
│   ├── navigation/  # PageNavigation、BilibiliNavigation
│   ├── platform/    # AppInfo、FileStorage、BrowserCookie、PlatformInfo
│   ├── preference/  # DataStore Compose 集成
│   ├── proxy/       # ProxyRepository
│   └── webview/     # WebViewContainer（expect/actual）
├── components/      # 可复用 UI 组件
│   ├── appbar/      # 顶部应用栏
│   ├── dialogs/     # AnyPopDialog、AutoSheetDialog、MessageDialog
│   ├── image/       # ImagePreviewer、ImagePager
│   ├── layout/      # ComposeScaffold、AutoTwoPaneLayout
│   ├── list/        # 列表状态管理
│   ├── start/       # 首页卡片组件
│   └── zoomable/    # 可缩放图片查看器
├── pages/           # 所有应用页面（commonMain 中约 150 个文件）
│   ├── auth/        # 登录页面（二维码、短信、H5、手机验证）
│   ├── bangumi/     # 番剧详情/剧集
│   ├── community/   # 评论/回复页面
│   ├── download/    # 下载管理
│   ├── dynamic/     # 动态流
│   ├── filter/      # 内容过滤设置
│   ├── home/        # 首页
│   ├── lyric/       # 歌词显示
│   ├── message/     # 消息中心
│   ├── mine/        # 用户库（历史、收藏、关注）
│   ├── player/      # 播放器控制（发送弹幕）
│   ├── playlist/    # 播放列表管理
│   ├── rank/        # 排行榜
│   ├── search/      # 搜索结果
│   ├── setting/     # 设置页面（主题、代理、弹幕等）
│   ├── time/        # 时光机功能
│   ├── user/        # 用户空间、关注、收藏
│   ├── video/       # 视频详情和播放
│   └── web/         # 应用内浏览器
└── platform/        # PlatformContext（Compose 层）
```

### 测试结构

```
app/src/test/java/     # 单元测试（JUnit 4）
app/src/androidTest/   # 插桩测试
```

### 重要配置文件

- `gradle/libs.versions.toml` - 版本目录，管理所有依赖版本
- `app/build.gradle.kts` - app 模块构建配置
- `bilimiao-comm/build.gradle.kts` - KMP 核心库构建配置（含 protobuf/gRPC 生成）
- `bilimiao-compose/build.gradle.kts` - KMP Compose UI 构建配置（含 SVG→Compose 图标生成）
- `build.gradle.kts` - 根构建配置
- `settings.gradle.kts` - 模块注册与仓库配置


===== FILE rainbow-me/rainbowkit::CLAUDE.md | stars=2831 followers=None lang=MDX bytes=6596 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Monorepo Structure

RainbowKit is a pnpm monorepo containing multiple packages:

- **`packages/rainbowkit`** - Core library: React components and hooks for wallet connection UI
- **`packages/rainbow-button`** - Standalone rainbow button component
- **`packages/rainbowkit-siwe-next-auth`** - Sign-In with Ethereum integration with NextAuth.js
- **`packages/create-rainbowkit`** - CLI tool for scaffolding new RainbowKit projects
- **`packages/example`** - Development example app (runs on localhost:3000)
- **`site`** - Documentation site (runs on localhost:3001)
- **`examples/`** - Additional example integrations (Next.js, Vite, Remix, etc.)

## Development Commands

### Setup
```bash
pnpm install  # Install dependencies and generate type definitions from root
```

### Development
```bash
pnpm dev                      # Run example app + site (localhost:3000 and :3001)
pnpm dev:lib                  # Watch and rebuild library packages only
pnpm dev:example              # Run lib + example app only
pnpm dev:site                 # Run lib + docs site only
pnpm dev:cli                  # Watch mode for create-rainbowkit CLI
pnpm dev:template:next-app    # Run Next.js app template directly
```

### Building
```bash
pnpm build                    # Build all packages (excludes template apps)
```

### Testing
```bash
pnpm test                     # Run all unit tests (uses Vitest)
pnpm test:unit run -t "<name>"  # Run specific test by name
pnpm test:update              # Update test snapshots
pnpm test:watch               # Watch mode for tests
pnpm test:cli                 # Test CLI scaffolding (builds template)
pnpm test:cli:dev             # Scaffold template + start dev server
pnpm test:cli:clean           # Remove generated test app
```

### Linting & Formatting
```bash
pnpm lint                     # Check formatting + typecheck all packages
pnpm lint:fix                 # Auto-fix formatting issues
pnpm format:check             # Check Biome formatting only
pnpm format:fix               # Auto-fix Biome formatting (run before commits)
```

## Architecture

### Core Library (`packages/rainbowkit`)

Built with:
- **Styling**: Vanilla Extract for type-safe CSS-in-JS with CSS modules
- **Build**: Custom esbuild setup (`build.js`) with watch mode
- **Bundling**: ESM format with code splitting for tree shaking

Key directories:
- `src/components/` - UI components (ConnectButton, modals, etc.)
- `src/wallets/` - Wallet connector definitions and registry
- `src/themes/` - Theme system (light, dark, midnight)
- `src/locales/` - Internationalization files
- `src/hooks/` - React hooks for wallet interactions
- `src/css/` - Vanilla Extract styles

Build process:
1. TypeScript type generation runs first (`typegen`)
2. esbuild compiles main entry + wallets separately
3. Vanilla Extract processes CSS with autoprefixer and selector prefixing (`[data-rk]`)
4. SVGs are inlined as data URLs, PNGs as base64

Environment variables required (`.env.local`):
- `RAINBOW_PROVIDER_API_KEY` - For enhanced provider features
- `WALLETCONNECT_PROJECT_ID` - For WalletConnect integration

### Testing

- Framework: Vitest with jsdom environment
- Setup: `packages/rainbowkit/test/setup.ts`
- Config: Root `vitest.config.ts` with Vanilla Extract plugin
- Tests located alongside source files (`.test.ts` / `.test.tsx`)

## Commit & Release Workflow

### Commit Format
Follow conventional commits as defined in `commitlint.config.js`:
- Types: `fix`, `feat`, `test`, `tooling`, `refactor`, `revert`, `example`, `docs`, `format`, `chore`
- Example: `fix: resolve wallet disconnect issue`

### Changesets
Always create a changeset for user-facing changes:
```bash
pnpm changeset  # Creates markdown file in .changeset/
```
- Prefer patch versions unless change warrants minor/major
- Never edit CHANGELOG.md files directly (auto-generated)
- Update existing changesets in same area rather than creating duplicates
- Patch bump `@rainbow-me/create-rainbowkit` when template dependencies change

### Git Workflow Tools
Use the following tools for git operations:
- **Graphite (`gt`)** - Preferred tool for all git interactions:
  - **Creating commits**: `gt create @username/precise-branch-name -m "commit message"`
    - **Stylize gt branch names like the following**: `@username/fix-feature` or `@username/upgrade-package-v10`
  - **Modifying existing commits**: `gt modify`
    - **Prefer this over adding new commits unless explicitly asked**
    - **Need to stage changes with git add or use --all to stage all changes**
  - **Creating branches**: `gt branch create <branch-name>`
  - **Tracking branches**: `gt track` - Always track branches if they aren't already tracked
  - **Moving branches in stack**: `gt move --onto <target-branch>` - Use when repositioning commits/branches
  - **Submitting/updating pull requests**: `gt submit --stack`
  - **Checking out PRs**: `gt checkout <pr-number>`
  - **Always ask before committing changes or manipulating/resubmitting branches or opening PRs**
  - **Always use gt modify by default when asked to make a commit**
- **GitHub CLI (`gh`)** - For viewing CI/CD status:
  - Use `gh run list` to view workflow runs
  - Use `gh run view` to investigate specific CI failures

### Locale Files
Only modify `en-US.json` locale files. Other language files are managed separately.

## CI Pipeline

See `.github/workflows/ci.yml` for full test plan:
1. Install dependencies
2. Build all packages
3. Run linting and formatting checks
4. Run unit tests (`pnpm test`)
5. Run CLI tests (`pnpm test:cli`)

All checks must pass before merging.

## Working with create-rainbowkit CLI

Template location: `packages/create-rainbowkit/templates/next-app/`

After template changes:
```bash
pnpm test:cli:dev  # Scaffold and test template (updates lockfile)
```
Commit the generated lockfile to keep monorepo in sync.

Link CLI globally for testing:
```bash
pnpm link:cli  # Makes `create-rainbowkit` available system-wide
```

## Local Environment

- **Node.js**: v24+ required. If using nvm, source it and select v24 before running any commands in this repo:
  ```bash
  export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh"
  nvm use 24
  ```
- **pnpm**: managed via Corepack. Activate the lockfile-pinned version once: `corepack enable pnpm`.

## Additional Notes

- Uses Biome for formatting/linting (replaces ESLint + Prettier)
- React 19 and Next.js 16 compatible
- Built on wagmi v2 and viem 2.x
- Node.js >= 24 required


===== FILE Dailin521/codex-provider-sync::AGENTS.md | stars=2797 followers=None lang=C# bytes=6648 =====

# AI Operator Guide

This file is for AI assistants, coding agents, and automation tools.

## Goal

Help the user make historical Codex sessions visible again after switching `model_provider`.

For normal Windows users, prefer the GUI app when it is available. Use the CLI when:

- the user explicitly wants commands
- the task is automated
- the GUI EXE is unavailable

The tool works by updating both:

- rollout metadata under `~/.codex/sessions` and `~/.codex/archived_sessions`
- SQLite thread metadata in the detected Codex state database, normally
  `~/.codex/sqlite/state_5.sqlite` with legacy fallback to
  `~/.codex/state_5.sqlite`

Do not solve this by manually editing rollout files only unless the user explicitly asks for manual intervention.

## Preferred Flow

Use this order by default:

1. If the GUI is available and the user is not asking for terminal commands, open `CodexProviderSync.exe`
2. Refresh and inspect the current provider plus rollout/SQLite distribution
3. Decide whether the user needs sync, switch-like behavior, or restore
4. Execute the action
5. Report whether the result is complete or partially skipped due to locked files

CLI fallback flow:

1. Run `codex-provider status`
2. Read `Current provider`, the displayed SQLite database path, and compare rollout/SQLite distribution
3. Decide whether the user needs `sync`, `switch`, or `restore`
4. Run the command
5. Report whether the result is complete or partially skipped due to locked files

## Command Selection

Use `codex-provider sync` when:

- the user already switched auth/provider using another tool
- the current `config.toml` root `model_provider` is already correct
- the user says things like:
  - "make my old sessions visible again"
  - "resync my Codex history"
  - "I already switched provider"

Use `codex-provider switch <provider-id>` when:

- the user wants to change the root `model_provider`
- the user wants one command to both switch provider and resync history

By default `switch` also aligns the root-level `model` with the new
provider section's `model`. Use `switch <provider-id> --keep-root-model`
to leave the root-level `model` untouched, or
`switch <provider-id> --model <name>` to set it explicitly (e.g. when
the new provider section has no `model` field of its own, or when the
user wants to call a non-default model through a relay provider).

Use `codex-provider restore <backup-dir>` when:

- the user wants to roll back a previous sync
- the user synced to the wrong provider

Use `codex-provider status` only when:

- the user asks for inspection only
- you need a safe first step before deciding what to do

## GUI Selection

Use the GUI app when:

- the user wants a double-click tool
- the user does not want to install Node/npm
- the user wants to visually inspect providers and backups

GUI mapping:

- `Refresh` = inspect current status
- `Execute` without config checkbox = `sync --provider <selected>`
- `Execute` with config checkbox = switch-like behavior
- `Restore Backup` = restore a previous backup
- backup retention defaults to 5 and can be customized in the GUI
- `Clean Old Backups` = prune managed backups down to the selected retention count

## Important Behavior

- `sync` uses the current root `model_provider` from `~/.codex/config.toml`
- if root `model_provider` is missing, `sync` falls back to `openai`
- `switch` changes root `model_provider`, then runs a sync
- built-in `openai` is always valid
- custom providers must already exist in `config.toml`
- the tool does not log the user in and does not manage `auth.json`
- sync and switch create a backup first, then automatically prune older managed backups
- backup pruning only touches backups created by this tool under `backups_state/provider-sync`

## Error Handling

If the output says `state_5.sqlite is currently in use`:

- tell the user to close Codex, Codex App, and app-server
- then rerun the same command

If sync reports `Skipped locked rollout files`:

- treat the sync as mostly successful
- explain that the active session still holds one or more rollout files open
- tell the user to rerun `codex-provider sync` after that session ends if they want a full rewrite

If `switch <provider-id>` fails because the provider is missing:

- tell the user to define it in `config.toml` or switch via their existing provider tool first
- then run `codex-provider sync`

## Safe Defaults

- default Codex home: `~/.codex`
- detect the SQLite DB before reasoning about SQLite counts; recent Codex uses
  `~/.codex/sqlite/state_5.sqlite`, while older layouts may use
  `~/.codex/state_5.sqlite`
- prefer `status` before destructive-looking operations, even though this tool only edits metadata
- by default the tool keeps the most recent 5 managed backups
- use GUI retention settings or CLI `--keep <n>` when the user wants a different retention count
- do not edit `state_5.sqlite` or rollout files manually if the tool can do it
- GUI settings live in `%AppData%\codex-provider-sync\settings.json`

## Recommended Commands

```bash
codex-provider status
codex-provider sync
codex-provider sync --keep 5
codex-provider sync --provider openai
codex-provider switch apigather
codex-provider switch apigather --model "MiniMax-M3"
codex-provider switch apigather --keep-root-model
codex-provider prune-backups --keep 5
codex-provider restore C:\Users\you\.codex\backups_state\provider-sync\20260319T042708906Z
```

With an explicit Codex home:

```bash
codex-provider status --codex-home C:\Users\you\.codex
codex-provider sync --codex-home C:\Users\you\.codex
codex-provider switch openai --codex-home C:\Users\you\.codex
```

## One-Shot Prompt Template

Use this prompt in another AI tool if the user wants one-step handling:

```text
I use codex-provider-sync. Please help me fix Codex session visibility under my current provider.

Steps:
1. Run `codex-provider status`.
2. If my current provider is already correct, run `codex-provider sync`.
3. If I explicitly tell you to switch provider, run `codex-provider switch <provider-id>` instead.
4. If SQLite is locked, tell me to close Codex / Codex App / app-server and retry.
5. If rollout files are skipped because they are locked, tell me which ones were skipped and remind me to rerun sync later.
6. Summarize the final state of rollout files and SQLite after the command finishes.
```

## User-Facing Summary Style

When reporting results back to the user:

- state the current provider
- state whether rollout files and SQLite are aligned
- mention backup location if a sync or switch was executed
- call out partial success clearly if locked rollout files were skipped


===== FILE freenet/freenet-core::AGENTS.md | stars=2797 followers=None lang=Rust bytes=11494 =====

# Freenet Core – Agent Guide

@~/.claude/freenet-local.md

## Contribution Scope (read before opening a PR)

[CONTRIBUTING.md](CONTRIBUTING.md) is the authoritative policy. In short:

- **Bug fixes** and **non-overreaching performance improvements** (no behavior
  change) — accepted without prior discussion.
- **Feature changes, new features, behavior changes, API reshaping** — require
  an issue approved by a maintainer *before* writing code. Feature PRs without
  an approved issue are auto-closed.
- **One logical change per PR.** Don't smuggle a feature into a bug fix or let a
  focused change accrete unrelated cleanup — that's scope creep and grounds for
  closing the PR.

When unsure which bucket a change is in, open an issue first.

## Behavioral Rules

### BEFORE modifying any file

```
1. Is this in crates/core/?
   → Check .claude/rules/testing.md for DST requirements
   → Verify: TimeSource for time, GlobalRng for randomness

2. Which module are you modifying?
   → ring/router/     → Check .claude/rules/ring.md
   → operations/      → Check .claude/rules/operations.md
   → transport/       → Check .claude/rules/transport.md
   → contract/wasm_runtime/ → Check .claude/rules/contracts.md

3. Is this Rust code?
   → Check .claude/rules/code-style.md
```

### BEFORE committing

```
1. Run: cargo fmt && cargo clippy -- -D warnings && cargo test
2. Check: Does commit message follow conventional commits?
3. Check .claude/rules/git-workflow.md for PR requirements
```

### WHEN fixing a bug (fix: PRs)

```
EVERY bug fix MUST include a regression test.

1. Write a test that reproduces the bug FIRST
2. Verify it FAILS without the fix
3. Apply the fix
4. Verify the test PASSES

CI enforces this: fix: PRs without new test functions are rejected.

Also: don't just test the happy path. Test edge cases and boundary
conditions. See .claude/rules/testing.md for specifics.
```

### WHEN a test fails

```
DO NOT delete or comment out the test.

Is the test broken/flaky?
  → Add #[ignore] with a comment explaining why
  → Create GitHub issue immediately
  → Reference the issue in the comment: // Ignored: [reason] #[issue]

Is the test superseded by new semantics?
  → Add #[ignore] with a comment explaining the semantic change
  → Reference the PR that changed the behavior
  → Keep the test as historical documentation
```

### WHEN writing cleanup/GC logic

```
Cleanup exemptions MUST be time-bounded.

Any condition that exempts an entry from garbage collection
(is_transient, has_pending, etc.) MUST either:
  1. Expire via TTL, OR
  2. Be overridden by an absolute age threshold

WHY: Unbounded exemptions create permanent GC blind spots.
This is a recurring meta-pattern where a fix introduces cleanup with
exemptions, then a follow-up discovers the exemptions themselves are
buggy (permanently refreshable, missing TTL enforcement).
Exemptions in GC deserve the same scrutiny as the original bug.

See: docs/weekly-fix-review-2025-02.md (befb0bd → 0b88945 cycle)
```

### WHEN you discover outdated or missing documentation

```
1. Is information in AGENTS.md, .claude/rules/, or CLAUDE.md incorrect?
   → Fix it immediately in the same commit or PR

2. Did you learn something important that would help future work?
   → Add it to the appropriate file:
     - Project-wide patterns → AGENTS.md
     - Code conventions → .claude/rules/code-style.md
     - Testing patterns → .claude/rules/testing.md
     - Git/PR workflow → .claude/rules/git-workflow.md
     - Crate-specific → crates/*/CLAUDE.md

3. Is a file reference (line number, path) stale?
   → Update or remove it
```

## Quick Reference

### Commands

```bash
cargo build                    # Build
cargo test -p freenet          # Test all
cargo fmt && cargo clippy -- -D warnings  # Lint (must match CI)
```

### Repository Structure

```
crates/
├── core/             # Runtime (node, transport, contracts, operations)
├── fdev/             # Developer CLI
├── freenet-macros/   # Test macros
└── release-agent/    # HTTP service on each gateway for triggering
                      # auto-updates from the release workflow (#4073)
apps/                 # Example applications
docs/architecture/    # Design docs
```

### Core Modules (`crates/core/src/`)

| Module | Purpose |
|--------|---------|
| `node/` | Event loop, coordination |
| `operations/` | State machines (GET, PUT, UPDATE, SUBSCRIBE, CONNECT) |
| `contract/` | WASM execution |
| `transport/` | UDP networking, encryption |
| `ring/` | DHT topology |
| `simulation/` | DST framework |

### Key Abstractions

| Need | Use | Location |
|------|-----|----------|
| Time | `TimeSource` | `crates/core/src/simulation/` |
| RNG | `GlobalRng` | `crates/core/src/config.rs` |
| Sockets | `Socket` trait | `crates/core/src/transport/` |

## Documentation

### Architecture Docs

| Topic | Location |
|-------|----------|
| Architecture | `docs/architecture/README.md` |
| Ring/DHT | `docs/architecture/ring/README.md` |
| Operations | `docs/architecture/operations/README.md` |
| Transport | `docs/architecture/transport/README.md` |
| Testing | `docs/architecture/testing/README.md` |

### Module Rules (path-scoped)

| Module | Rules |
|--------|-------|
| Ring/Router | `.claude/rules/ring.md` |
| Operations | `.claude/rules/operations.md` |
| Transport | `.claude/rules/transport.md` |
| Contracts | `.claude/rules/contracts.md` |

### General Rules

| Topic | Location |
|-------|----------|
| Code style | `.claude/rules/code-style.md` |
| Git workflow | `.claude/rules/git-workflow.md` |
| DST testing | `.claude/rules/testing.md` |
| Deployment | `.claude/rules/deployment.md` |

## Release Workflow & RELEASE_PAT

The release pipeline (`.github/workflows/release.yml` →
`.github/workflows/cross-compile.yml` → downstream `gateway-update.yml` /
`release-announce.yml`) relies on a `RELEASE_PAT` repo secret to fire
all the workflow events that make releases zero-touch.

### Why a PAT is required

GitHub's `GITHUB_TOKEN` deliberately suppresses workflow-triggering
events as an anti-recursion safeguard:

> When you use the repository's `GITHUB_TOKEN` to perform tasks,
> events triggered by the `GITHUB_TOKEN` will not create a new
> workflow run.

That means any `gh` call inside a workflow that *should* wake up
another workflow has to authenticate with a personal access token
(PAT) instead. Two concrete failure modes hit the v0.2.57 release:

1. **Bump PR has 0 check-runs.** `release.yml` opens the
   `release/vX.Y.Z` PR via `gh pr create`. With `GITHUB_TOKEN`, no
   `pull_request` event fires, so `ci.yml` never runs and the PR's
   required checks never go green. Workaround was
   `gh pr close && gh pr reopen`, which broke `wait_for_pr` polling.

2. **`release.published` doesn't fire downstream workflows.**
   `cross-compile.yml`'s `attach-to-release` job ends with
   `gh release edit --draft=false`. With `GITHUB_TOKEN`, the
   `release.published` event is suppressed, so `gateway-update.yml`
   and `release-announce.yml` don't auto-fire. v0.2.57 had to trigger
   them manually via `workflow_dispatch`.

### Configuring the secret

`RELEASE_PAT` must be a fine-grained (or classic) personal access
token with at minimum:

- **`repo`** (Contents: read/write, Pull requests: read/write,
  Metadata: read) for `gh pr create`, `gh release edit`, and push of
  release branches.
- **`workflow`** required for any token that lands on
  `.github/workflows/`-adjacent code paths.

Add it under
**Settings → Secrets and variables → Actions → Repository secrets**
as `RELEASE_PAT`. Both `release.yml` and `cross-compile.yml`
coalesce on it. The coalesce appears in two forms:

```yaml
# for actions/checkout (controls what `git push` uses later):
- uses: actions/checkout@v6
  with:
    token: ${{ secrets.RELEASE_PAT || secrets.GITHUB_TOKEN }}

# for `gh` CLI steps:
env:
  GH_TOKEN: ${{ secrets.RELEASE_PAT || secrets.GITHUB_TOKEN }}
```

When the secret is missing the workflows degrade gracefully: they
still complete, but the bump-PR CI, the tag-push → cross-compile
trigger, and the release-published cascade won't auto-fire and a
human has to intervene. `release.yml` emits a GitHub `::warning::`
on every run that's missing the secret, so the gap is visible
early.

`.github/workflows/check-token-coalesce.yml` runs on every PR and
fails if any new event-emitting step regresses to bare
`GITHUB_TOKEN` / `github.token` — see issue #4118 for the regression
class this guard prevents.

### Maintenance

The PAT belongs to a maintainer's account (currently @sanity). Rotate
it on the GitHub PAT expiry schedule, and update the `RELEASE_PAT`
secret in the freenet-core repo when you do. If `release.yml` prints
the "RELEASE_PAT not set" warning unexpectedly, the secret has
expired and the same rotation procedure applies.

### Cutting a release

End-to-end procedure for any maintainer is in
[`docs/RELEASING.md`](docs/RELEASING.md). One-line summary:
`gh workflow run release.yml --field version=X.Y.Z`. The `RELEASE_PAT`
section above is the prerequisite for the cascade to fire automatically.

## Release artifact signing (`FREENET_RELEASE_SIGNING_KEY`)

`cross-compile.yml` signs the release `SHA256SUMS.txt` with an ed25519 key
(`FREENET_RELEASE_SIGNING_KEY` repo secret) and uploads `SHA256SUMS.txt.sig`.
The auto-updater (`crates/core/src/bin/commands/update.rs`) verifies that
signature against the public key baked into the binary (`FREENET_RELEASE_PUBKEY`)
before trusting the checksum manifest. Rotating the key means updating BOTH the
secret AND the baked-in `FREENET_RELEASE_PUBKEY` (a mismatch would make every
client refuse the release). To verify the secret matches the baked-in key
without cutting a release, run `cross-compile.yml` via `workflow_dispatch` and
check the `verify-signing-key` job. The full prerequisites table (including the
two-release `REQUIRE_RELEASE_SIGNATURE` transition) is in `docs/RELEASING.md`.

### Reserved offline revocation key (`FREENET_REVOCATION_PUBKEY`)

A second ed25519 public key, `FREENET_REVOCATION_PUBKEY`, is baked into the
binary alongside `FREENET_RELEASE_PUBKEY` but serves a different purpose: it is
the OFFLINE backup / key-revocation key. Its private half is kept strictly
offline (never in CI or GitHub secrets, unlike `FREENET_RELEASE_SIGNING_KEY`),
so it can authorize a key-revocation message even if the online release-signing
key is compromised. It is RESERVED — the mechanism to fetch and verify a
revocation message signed by it is deferred to the future signed-policy-over-
Freenet delivery layer (auto-update epic #4073). It must nevertheless be shipped
now: a revocation can only be honored by peers whose binary already carries the
key, so it cannot be retrofitted into already-released builds. The value is
pinned by the `revocation_pubkey_matches_published_hex` test in `update.rs`.
It is declared as a `#[used] static` (NOT a `const`) on purpose: a `const`
with no runtime reader is inlined to nothing and would be absent from the
shipped binary, defeating the bake-in. Do not "simplify" it to a `const`
until a runtime path actually reads it.

## Delegate secrets-at-rest

Operator-facing documentation (encryption model, migration matrix,
`freenet secrets` CLI) lives in [`docs/secrets-at-rest.md`](docs/secrets-at-rest.md).

## External Resources

- API docs: https://docs.rs/freenet
- Manual: https://freenet.org/resources/manual/


===== FILE paritytech/polkadot-sdk::CLAUDE.md | stars=2788 followers=None lang=Rust bytes=4452 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

The Polkadot SDK is a monorepo containing all components needed to build on the Polkadot network. It was formed by
merging three previously separate repositories:

- **Substrate** (`substrate/`): Core blockchain framework providing consensus, networking, storage, and runtime
  execution
- **Polkadot** (`polkadot/`): Relay chain implementation including the validator node
- **Cumulus** (`cumulus/`): SDK for building parachains that connect to Polkadot
- **Bridges** (`bridges/`): Cross-chain bridge infrastructure including Snowbridge (Ethereum bridge)

## Rust Toolchain

This repository is meant to be compiled with a stable Rust toolchain. A nightly toolchain is only required
to run `cargo +nightly fmt`. It should always compile with the latest Rust version. However, the CI will
use the version referenced in `.github/env`. Using features not available in that version will not pass CI.
Additionally, newer versions will likely result in warnings when compiling the repository.

The toolchain requires the `rust-src` component to build for the PolkaVM target.
We also need the `wasm32v1-none` target to compile the WASM runtimes.

## Build Commands

```bash
# Check or clippy the entire workspace
# This skips the time-intensive building of the WASM runtimes
SKIP_WASM_BUILD=1 cargo check --workspace --all-targets --all-features
SKIP_WASM_BUILD=1 cargo clippy --workspace --all-targets --all-features

# Build specific binary
cargo build -p polkadot --release
cargo build -p polkadot-parachain-bin --release

# Build specific runtime
cargo build -p kitchensink-runtime --release --features runtime-benchmarks
```

## Testing

```bash
# Run all tests (testnet is a release profile with debugging)
cargo test --workspace --profile testnet
```

## Formatting and Linting

```bash
# Format Rust code (requires nightly)
cargo +nightly fmt

# Format TOML files
taplo format --config .config/taplo.toml
```

## Architecture

### Runtime vs Node

The SDK separates **runtime** (on-chain logic, compiled to WASM) from **node** (off-chain client):
- Runtime code lives in `*/runtime/` directories and must be `no_std` compatible
- Node/client code lives in `*/client/` and `*/node/` directories

### FRAME Pallets

Pallets are modular runtime components in `substrate/frame/`. Each pallet:
- Has a `Config` trait for configuration
- May have storage items, dispatchables (extrinsics), events, and errors
- Uses macros from `frame_support` (`#[pallet::*]`)

### XCM (Cross-Consensus Messaging)

Located in `polkadot/xcm/`. XCM is the messaging format for cross-chain communication:
- `xcm/` - Core XCM types and versioning
- `xcm-builder/` - Configurable components for XCM execution
- `xcm-executor/` - XCM instruction executor
- `pallet-xcm/` - Runtime pallet for XCM

### Key Directories

- `substrate/primitives/` - Core types shared across the codebase
- `substrate/frame/support/` - FRAME macros and support code
- `polkadot/node/` - Polkadot validator node subsystems
- `cumulus/pallets/parachain-system/` - Core parachain runtime support
- `cumulus/parachains/runtimes/` - System parachain runtimes (Asset Hub, Bridge Hub, etc.)
- `substrate/client/statement-store/` - Statement store (off-chain signed-statement gossip store);

## Code Style

- **Indentation**: Tabs (not spaces)
- **Line width**: 100 characters max
- **Panickers**: Avoid `unwrap()`; if used, add proof comment ending with `; qed`
- **Unsafe code**: Requires explicit safety justification

## PR Requirements

1. All PRs need a `prdoc` file unless labeled `R0-no-crate-publish-required`
2. Use `/cmd prdoc` in PR comments to generate prdoc (paritytech org members)
3. Use `/cmd fmt` to format code
4. Use `/cmd bench` for weight generation
5. Tag PRs with at least one `T*` label indicating the component changed

## Running Local Networks

```bash
# Using zombienet (recommended)
zombienet --provider native spawn ./zombienet/examples/small_network.toml

# Manual: Start relay chain
./target/release/polkadot --chain rococo-local --alice --tmp

# Manual: Start parachain collator
./target/release/polkadot-parachain --collator --alice --force-authoring --tmp
```

## UI Tests

UI tests verify macro output. Update them with:
```bash
./scripts/update-ui-tests.sh
# Or for a specific Rust version:
./scripts/update-ui-tests.sh 1.70
```


===== FILE kylecorry31/Trail-Sense::AGENTS.md | stars=2738 followers=None lang=Kotlin bytes=670 =====

Use the following scripts to work with the app, but do not modify them:
- `scripts/build.sh`: build the debug APK
- `scripts/run-unit-tests.sh [test-filter]`: run unit tests. The optional filter is forwarded to Gradle with `--tests`.
- `scripts/run-emulator-integration-tests.sh [test-class-or-method-filter] [timeout-seconds]`: run connected Android tests on the emulator with an optional timeout, defaulting to 1800 seconds. Fails if no emulator is connected. Most individual integration tests should finish in 60 to 180 seconds; use the timeout argument for focused runs when practical.
- `scripts/lint.sh`: run Detekt linting

Use the test filters whenever possible.

===== FILE ClassIsland/ClassIsland::AGENTS.md | stars=2646 followers=None lang=C# bytes=4480 =====

# AGENTS.md

## Repo Shape
- Main solution: `ClassIsland.sln`; platform-filtered solutions exist as `ClassIsland.Filter.Linux.slnf` and `ClassIsland.Filter.MacOs.slnf`.
- Runtime app entrypoint is `ClassIsland.Desktop/Program.cs`; the Avalonia app/library code lives in `ClassIsland/`, and shared UI/services live mostly in `ClassIsland.Core/`.
- Platform services are split under `platforms/ClassIsland.Platforms.{Windows,Linux,MacOs}` and wired by compile constants from `CrossPlatformProps.props`.
- `ClassIsland.Shared` and `ClassIsland.Shared.IPC` multi-target `net8.0;net472`; avoid APIs unavailable on `net472` there.
- `ClassIsland.Launcher` targets `net9.0`; most app projects target `net8.0`.

## SDK And Restore
- `global.json` requests .NET SDK `9.0.0` with `rollForward: latestFeature`; launcher/native-AOT work needs .NET 9 SDK, not just .NET 8.
- CI checks out submodules recursively; this repo depends on `vendors/EdgeTtsSharp` (`classisland-v2` branch). If restore/build complains about missing vendor code, run `git submodule update --init --recursive`.
- CI adds the GitHub Package Registry source `https://nuget.pkg.github.com/ClassIsland/index.json`; local restores may need equivalent credentials if a package is unavailable from public NuGet.

## Build Commands
- Fast focused compile for the desktop app: `dotnet build ClassIsland.Desktop/ClassIsland.Desktop.csproj -c Debug`.
- Build a single library/package project directly, for example: `dotnet build ClassIsland.Core/ClassIsland.Core.csproj -c Debug`.
- Use NUKE only for release/publish builds; do not use the wrapper default target for normal verification.
- Release-style app packaging must call `PublishApp` explicitly: on Windows use `./build.ps1 PublishApp --OsName windows --Arch x64 --Package folder --BuildType full --BuildName appBase --AppVersion 0.0.0.0`; on Unix use `./build.sh PublishApp` with the same arguments.
- `PublishApp` requires metadata: `--OsName windows|linux|macos`, `--Arch x64|x86|arm64`, `--Package folder|deb|pkg`, `--BuildType full|selfContained`, `--BuildName appBase|app`, `--AppVersion <version>`.
- Launcher packaging uses `PublishLauncher` and publishes native AOT self-contained output from `ClassIsland.Launcher`.
- Plugin dev environment target `InitPluginDevEnv` writes user environment variables/profile blocks pointing at `out/ClassIsland_Dev`; do not run it casually during verification.

## Platform Targeting
- `CrossPlatformProps.props` auto-selects platform constants from the host OS for normal builds; release builds override this with `PublishBuilding=true` and `PublishPlatform=<os>`.
- `ClassIsland.Desktop` conditionally references exactly one platform implementation based on `Platforms_Windows`, `Platforms_Linux`, or `Platforms_MacOs`.
- Linux install/runtime docs require X11; Wayland/XWayland is not considered supported.

## Generated And Output Files
- NUKE writes release artifacts to `out/`; plugin builds may write `.cipx` files under a plugin project's `cipx/` directory.
- `ClassIsland/secrets.g.cs` is generated by NUKE `GenerateSecrets` and deleted by `PostCleanup`; never commit generated secret files.
- Ignore and do not edit transient `*_wpftmp.csproj` files such as those under `ClassIsland.Core/`.
- CsWin32 inputs live in `NativeMethods.txt`/`NativeMethods.json` under platform projects; generated interop code comes from the package.

## Tests And Verification
- No test projects are present in the solution; prefer focused `dotnet build <project>` verification for code changes.
- After every code change, run at least one compile check; for app changes, use `dotnet build ClassIsland.Desktop/ClassIsland.Desktop.csproj -c Debug` rather than NUKE.
- If automated tests become available or the touched area has an executable test path, run the relevant automated tests too.
- If automated testing is not available or cannot cover the changed feature, tell the user what related behavior still needs manual verification.
- For platform-specific changes, build the affected entry project with the intended host/platform settings; a Windows-host debug build will not compile Linux/macOS-specific code unless invoked through the publish properties/filter.

## Contribution Conventions
- `CONTRIBUTING.md` asks for Conventional Commits with scopes from `doc/Contributing/Scopes.md` when committing.
- Feature work should target `master`; fixes for currently maintained stable versions may target the matching maintenance branch.


===== FILE pjsip/pjproject::CLAUDE.md | stars=2644 followers=None lang=C bytes=7063 =====

# PJSIP/PJPROJECT

Open-source multimedia communication library in C (SIP, SDP, RTP, STUN, TURN, ICE).

## Build & Test

- **Build**: `./configure && make -j3` (timeout 120s+, NEVER CANCEL)
- **Skip `make dep`** — it often produces corrupt `.depend` files. `make` generates deps automatically. If build fails with "missing separator" in `.depend`, run `find . -name "*.depend" -delete` and retry.
- **Targeted build**: `cd pjlib/build && make` (or `pjsip/build`, etc.)
- **Full clean**: `make clean` (required when switching SSL backends or configure options)
- Get target arch: `make infotarget` (e.g., `x86_64-pc-linux-gnu`)
- **Three build systems** — when adding/removing source files, update all three:
  1. GNU Makefile (e.g., `pjlib/build/Makefile`)
  2. MSVC project (e.g., `pjlib/build/pjlib.vcxproj`)
  3. CMake (`CMakeLists.txt`)

### Running Tests

Run via Makefile (NEVER CANCEL, 5+ min each, timeout 600s):
```
make pjlib-test        # core library
make pjsip-test        # SIP stack
make pjsua-test        # high-level API (Python)
```

Run specific test directly — **must run from the bin/ directory**:
```
cd pjlib/bin && ./pjlib-test-x86_64-pc-linux-gnu timer_test
cd pjlib/bin && ./pjlib-test-x86_64-pc-linux-gnu --list
```
Options: `-w N` (worker threads), `--shuffle`, `--ci-mode`, `--stop-err`

Quick smoke test: `cd tests/pjsua && python3 run.py mod_run.py scripts-run/100_simple.py`

### Minimum Validation (mandatory after every change)

- **Always run `make -j3`** — zero errors, zero warnings (`-Wall` enabled).
- For targeted builds: `cd pjlib/build && make` or `cd pjsip/build && make`.
- **Known warning**: `PJ_TODO(id)` macro triggers `-Wunused-label` intentionally. Suppress with `#define PJ_TODO(x)` in `config_site.h`.

### Configure Options

- `--with-gnutls=/usr/` — GnuTLS instead of OpenSSL (requires `make clean` first)
- `--disable-ssl` — disable SSL/TLS
- `--enable-shared` — shared libraries
- Feature toggles: `#define` in `pjlib/include/pj/config_site.h`

### Config Site

- `pjlib/include/pj/config_site.h` — local configuration overrides, NOT tracked by git
- CI uses `config_site_test.h` (copied to `config_site.h` in workflows)
- SSL tests will fail with timeouts in sandboxed environments — expected

## Repository Structure

```
pjlib/           # Base framework (OS abstraction, data structures, pool allocator)
pjlib-util/      # Utilities (DNS, STUN, XML, JSON, WebSocket)
pjnath/          # NAT traversal (STUN, TURN, ICE)
pjmedia/         # Media framework (codecs, transport, audio/video)
pjsip/           # SIP stack (transactions, dialogs, UA layer)
pjsip-apps/      # Applications and samples
third_party/     # Bundled third-party libs (srtp, resample, etc.)
tests/pjsua/     # Python-based PJSUA tests
.github/         # CI workflows
```

### Architecture Layers (top → bottom)

1. **PJSUA2** (C++) / **PJSUA** (C high-level) — `pjsip/include/pjsua-lib/`
2. **PJSIP UA** — dialogs, calls, presence — `pjsip/include/pjsip-ua/`
3. **PJSIP Core** — transactions, transport, parsing — `pjsip/include/pjsip/`
4. **PJMEDIA** — media sessions, codecs, RTP — `pjmedia/include/pjmedia/`
5. **PJNATH** — ICE, STUN, TURN — `pjnath/include/pjnath/`
6. **PJLIB** — pool allocator, OS abstraction — `pjlib/include/pj/`

### Key Files

- `pjlib/include/pj/config_site.h` — main configuration overrides
- `pjlib/include/pj/config.h` — default configuration values
- `build.mak` — generated build configuration
- ICE/NAT: `pjnath/include/pjnath/ice_strmtp.h`
- Call handling: `pjsip/src/pjsua-lib/pjsua_call.c`
- Transport: `pjsip/include/pjsip/sip_transport.h`

## Coding Conventions

Follow: https://docs.pjsip.org/en/latest/get-started/coding-style.html

Documentation source (for when the docs site is not directly accessible):
https://github.com/pjsip/pjproject_docs

### Essentials
- **ANSI C (C89/C90)** for core modules. No declarations after statements.
- **4 spaces** indentation (no tabs). ~80 char lines.
- **K&R braces**: same line for control statements, next line for functions/structs.
- **`/* */` comments** for C code, `/** */` for Doxygen on public APIs.
- **Module prefixes**: `pj_` (pjlib), `pjsip_` (sip), `pjmedia_` (media), `pjnath_` (nat)
- **Constants**: ALL_CAPS with prefix (`PJSIP_MAX_URL_SIZE`, `PJ_TRUE`)

### Memory Management
- Core C modules use **pool-based allocation** (`pj_pool_t`).
- Use `PJ_POOL_ALLOC_T()`, `PJ_POOL_ZALLOC_T()`, `pj_pool_alloc()`.
- Pools freed as a whole — no individual deallocation.
- **No `malloc()`/`free()`** in core C code.

### String Handling
- `pj_str_t` (pointer + length), NOT null-terminated.
- Never assume null-termination. Use `pj_strcmp()`, `pj_stricmp()`.

### Error Handling
- Functions return `pj_status_t`. `PJ_SUCCESS` (0) = success.
- Always check return values. Use `PJ_ASSERT_RETURN()` for preconditions.

### Logging
- `PJ_LOG(level, (sender, format, ...))` — note double parentheses.
- Each file defines `THIS_FILE`. Levels: 0 (fatal) to 6 (trace).

## Architecture Notes

### Threading Model
- Single-threaded (polling) or multi-threaded.
- Use `pj_mutex_t` / `pj_lock_t` — NOT pthread directly.
- Callbacks may fire from worker threads — be thread-safe.
- **Avoid invoking user callbacks while holding a mutex** — release lock first to prevent deadlock.

### Group Lock (`pj_grp_lock_t`)
- Mutual exclusion + reference counting + lock ordering in one primitive.
- `add_ref()` before scheduling timer/callback, `dec_ref()` in the callback.
- Never destroy a lock that other threads may reference — use ref counting.
- Lock ordering: PJSUA_LOCK > dialog grp_lock > transaction grp_lock.
- Debug: enable `PJ_GRP_LOCK_DEBUG` in `config_site.h`.

### Platform Differences
- **I/O Queue backends**: epoll (Linux), kqueue (macOS/BSD), select (portable), IOCP (Windows)
- IOCP backend has different threading semantics than epoll/select.

## Do's and Don'ts

### DO:
- Reference existing patterns before writing new code
- Follow module prefix naming strictly
- Check `pj_status_t` return values everywhere
- Declare all variables at top of block (C89)
- Add Doxygen `/** */` for new public APIs
- Prefer param structs over many positional arguments for extensibility

### DON'T:
- Don't use malloc/free in core C modules
- Don't assume null-terminated strings with `pj_str_t`
- Don't add C++ in core C modules
- Don't modify public headers without understanding downstream impact
- Don't destroy objects with pending timers/async callbacks
- Don't declare variables after statements (C89)

## CI Integration

- GitHub Actions: `.github/workflows/` (Linux, Mac, Windows)
- Uses `cirunner` tool for test execution with timeouts
- Tests multiple configurations (SSL/no-SSL, GnuTLS, video codecs, etc.)
- `--ci-mode` widens timing tolerances for slow CI runners

### Writing Robust Tests
- **No precise timing** — use generous tolerances or event-driven sync. CI runners can be 5-10x slower.
- Verify ASan compatibility for platform-specific features (sigaltstack, thread stacks).


===== FILE SummerSec/ShiroAttack2::CLAUDE.md | stars=2606 followers=1790 lang=Java bytes=3629 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# 前置步骤：安装本地 JAR 到 Maven（仅首次需要）
mvn install:install-file -Dfile=libs/jEG-Core-1.0.0.jar -DgroupId=jeg -DartifactId=jeg-core -Dversion=1.0.0 -Dpackaging=jar
mvn install:install-file -Dfile=libs/jmg-sdk-1.0.9.jar -DgroupId=jmg -DartifactId=jmg-sdk -Dversion=1.0.9 -Dpackaging=jar

# 打包为可执行 fat JAR（含所有依赖）
mvn clean package -DskipTests

# 产物路径: target/shiro_attack-5.1.1-all.jar

# 运行 CLI（命令行模式，无需 GUI）
java -cp target/shiro_attack-5.1.1-all.jar com.summersec.attack.CLI.MainCLI <command> [options]

# CLI 可用命令: detect | crack | exec | memshell | changekey | gui
# 详见 .claude/skills/shiro-attack-cli/SKILL.md

# 运行（需要 JavaFX 运行时，Java 8）
java -jar target/shiro_attack-5.1.1-all.jar
```

本项目无测试套件；仅有 GitHub Release CI（推送 tag 触发）。

## 插件市场

本项目同时也是 Claude Code 插件市场，通过 `.claude-plugin/marketplace.json` 注册了 `shiro-attack-cli` 技能。

```bash
# 安装（来源为 GitHub）
claude plugins add github:SummerSec/ShiroAttack2
```

支持平台：Claude Code (`.claude-plugin/`)、Codex CLI (`.codex-plugin/`)、Cursor (`.cursor-plugin/`)。skill 源文件在 `skills/shiro-attack-cli/SKILL.md`。

## 架构概述

ShiroAttack2 是一个利用 Apache Shiro rememberMe AES 反序列化漏洞（Shiro-550）的 JavaFX GUI 工具。

### 攻击流程

1. **密钥爆破** — `deser/plugins/keytest/KeyEcho.java` 将 `SimplePrincipalCollection` 序列化后用候选密钥（`resources/data/shiro_key.txt`）逐一加密，通过响应判断有效密钥
2. **Gadget 链选择** — 用户在 UI 中选择适合目标 classpath 的 `CommonsBeanutils` 变体（1.8.3 / 1.9.2 / AttrCompare）
3. **回显类型选择** — Tomcat / Spring / DFS-AllEcho / NoEcho / 反弹 Shell
4. **Payload 构造** — `deser/util/Gadgets.java` 用 Javassist 将回显类嵌入 `TemplatesImpl` translet，Gadget 链包装后序列化
5. **加密发送** — `Encrypt/CbcEncrypt.java`（AES-CBC）或 `Encrypt/GcmEncrypt.java`（AES-GCM）加密后 Base64 编码，写入 rememberMe cookie 发送

### 主要包职责

| 包 | 职责 |
|---|---|
| `attack.UI` | JavaFX 入口 (`Main`) 和主窗口控制器 |
| `attack.core` | `AttackService` — 串联爆破、Gadget、加密、发送的编排层 |
| `attack.Encrypt` | AES-CBC / AES-GCM 加密；`KeyGenerator` 生成新密钥 |
| `attack.deser.payloads` | CommonsBeanutils gadget 链实现 |
| `attack.deser.echo` | 各平台回显 Payload 生成（Tomcat/Spring/DFS/Reverse/NoEcho） |
| `attack.deser.plugins` | 内存马注入（`InjectMemTool`）、密钥探测（`KeyEcho`）|
| `attack.deser.frame` | Shiro cookie 序列化/加密封装 |
| `attack.deser.util` | `Gadgets`（TemplatesImpl 构造）、反射工具、JavaVersion |
| `attack.utils` | HTTP 请求（Hutool）、AES 工具、控制台输出 |
| `attack.entity` | `ControllersFactory`（JavaFX 控制器注册表）、`RequestInfo` |
| `org.apache.shiro.*` | 内嵌 Shiro 加密源码（`AesCipherService` 等），便于定制 |

### 关键依赖说明

- `lib/` 目录下的本地 JAR（`commons-beanutils-1.8.3.jar` 等）通过 `pom.xml` 中 `systemPath` 引入，是 Gadget 链的实际攻击依赖，与常规 Maven 依赖分开管理
- `assembly.xml` 配置将 test-scope 依赖也解包进 fat JAR
- Allatori 混淆配置已存在但在 `pom.xml` 中被注释，发布时可按需启用


===== FILE Vexa-ai/vexa::CLAUDE.md | stars=2601 followers=None lang=Python bytes=430 =====

@AGENTS.md

## Claude Code specifics

Layout: pnpm + turbo monorepo — `core/` (gateway, agent, runtime, identity, meetings),
`clients/terminal` (Next.js 15, port 3000, `npm run dev`), `docs/docs` (Mintlify site — the
published law), `calm/` (FINOS CALM model). Licensing is FINOS-gated: new deps must be
Category A (MIT/BSD/Apache); weak-copyleft needs an entry in `license-exceptions.json`
(ADR-0004) — never add GPL/AGPL.


===== FILE FreeRADIUS/freeradius-server::AGENTS.md | stars=2558 followers=None lang=C bytes=1884 =====

# Policy on AI Agents

> [!IMPORTANT]
> This project does **not** accept pull requests that are fully or
> predominantly AI-generated. AI tools may be utilized solely to
> assist individual development.
>
> If we receive an AI PR that _clearly has had zero testing_, then we
> will **ban the person who submitted the PR**.
>
> Submitting a garbage PR isn't just AI slop, it's abuse.

AI assistance is fine.  But when someone submits a PR, we assume that
they understand the submission, and that they accept full
responsibility for it.

---

## Recommendations for Using AI

AI can be useful in some situations.  However, our experience has been
that when people ask AI questions about FreeRADIUS, the answers are
pretty bad.  The advice is either unclear, or is simply wrong.  This
means that AI should be used to point you in a direction, but you
should read the documentation to get the _truthful_ answers:

> READ THE DOCS!
>
> https://www.freeradius.org/documentation/freeradius-server/

AI can help in the following use cases:

- Code completion in an editor,
- Asking about the structure of the code,
- Learning about specific techniques used in the project,
- Finding documents, links, and parts of the code that are worth your time
- Reviewing human-written code and providing suggestions on things you hadn't thought of,
- Creating rough outlines for documentation,

Anything AI generated _must_ be reviewed, edited, and approved by a person.

## Disclosure

**All AI contributions must be disclosed.**

If you use AI in an editor for API suggestions, searching the code,
etc., that doesn't need to be disclosed.  You are the person writing
the code, not the AI.

If you use AI to _generate_ code, it **must** be disclosed.  The code
that AI generates is pretty much always wrong.  We need to know if the
PR is AI slop, or if it has been reviewed and understood by a person.
