

===== FILE kayba-ai/agentic-context-engine::AGENTS.md | stars=2541 followers=None lang=Python bytes=5778 =====

# AGENTS.md

This file provides guidance to coding agents working in this repository.

## Repository Guidelines

### Pipeline-First Development (MANDATORY)
**All new functionality MUST be implemented as pipeline Steps composed via the Pipeline engine.** Do NOT write standalone scripts, ad-hoc loops, or inline logic that bypasses the pipeline. Before writing any code:

1. Read `docs/design/PIPELINE_DESIGN.md` to understand the Step → Pipeline → Branch model.
2. Implement logic as a `Step` class with `requires`/`provides` declarations and a `__call__(self, ctx) -> ctx` method.
3. Compose steps using `Pipeline().then(...)` and `.branch(...)` — never manual for-loops or direct function chaining.
4. Use `StepContext.replace()` for immutable context updates — never mutate context directly.
5. Put integration-specific data in `metadata`, not new context fields, unless the field is shared across multiple pipelines.

**Anti-patterns to reject:**
- Writing a function that calls multiple steps manually instead of composing them in a Pipeline
- Inline reflection/evaluation logic instead of creating a ReflectStep or EvaluateStep
- Ad-hoc `ThreadPoolExecutor` usage instead of `async_boundary` and `max_workers` on steps
- Standalone scripts that duplicate pipeline functionality without using the pipeline engine
- Bypassing `requires`/`provides` contracts by accessing context fields not declared in `requires`

If a task seems like it cannot fit the pipeline model, explain why to the user before proceeding — do not silently circumvent it.

### Core Code Protection
**Do NOT modify core modules (`ace/core/`, `pipeline/`) without explicit user approval.** Before proposing any change to these directories:
1. Read the relevant design docs (`docs/design/ACE_ARCHITECTURE.md`, `docs/design/PIPELINE_DESIGN.md`) thoroughly.
2. Evaluate whether the change is truly required or if it can be achieved outside the core (e.g., in an integration, step, or example).
3. Clearly explain the proposed change and its justification to the user **before** making any edits.
4. Wait for the user to explicitly accept before proceeding.

### Documentation Maintenance
Before working on code in `ace/`, read `docs/design/ACE_ARCHITECTURE.md` to understand the current architecture.
Before working on code in `pipeline/` or `ace/core/`, read `docs/design/PIPELINE_DESIGN.md` to understand the pipeline engine.

**Docs MUST be kept in sync with code.** Any change that alters a public API, renames a concept, adds/removes a module, or changes execution flow **requires** a corresponding update to the relevant docs. Do not merge code changes that make the documentation inaccurate.

Key design docs:
- `docs/design/ACE_ARCHITECTURE.md` — ACE architecture: layers, core concepts, roles, steps, runners, integrations
- `docs/design/ACE_REFERENCE.md` — ACE code reference: full implementations, API signatures, usage examples
- `docs/design/ACE_DECISIONS.md` — design decisions and rejected alternatives (ACE, pipeline, migration)
- `docs/design/PIPELINE_DESIGN.md` — pipeline engine: steps, StepProtocol, Pipeline, Branch, concurrency
- If you need to work with collected traces from Logfire, read `agent-guides/logfire.md`

### Project Structure
- `ace/` — core library: roles (PydanticAI-backed), skillbook, steps, runners, providers, RR, integrations, observability
- `pipeline/` — generic pipeline engine that `ace` is built on (see `docs/design/PIPELINE_DESIGN.md`)
- `ace-eval/` — evaluation framework (submodule, separate repo)
- `tests/` — unit/integration tests (pytest)
- `examples/` — runnable demos grouped by integration
- `agent-guides/` — internal development guides for LLM agents; not part of the public docs site
- `docs/` — guides and reference material
  - `docs/design/ACE_ARCHITECTURE.md` — architecture and concepts (keep in sync with code)
  - `docs/design/ACE_REFERENCE.md` — code reference and examples (keep in sync with code)
  - `docs/design/ACE_DECISIONS.md` — design decisions and rejected alternatives
  - `docs/design/PIPELINE_DESIGN.md` — pipeline engine design doc (keep in sync with code)

### Commands
- `uv sync` — install all dependencies
- `uv run pytest` — run tests (coverage enforced `--cov-fail-under=25`)
- `uv run pytest -m unit` / `-m integration` / `-m slow` — run by marker
- `uv run black ace/ tests/ examples/` — format code
- `uv run mypy ace/` — type check

### Coding Style
- PEP 8 with Black formatting (line length 88)
- Type hints and docstrings for public APIs
- Python 3.12 target
- Test files: `tests/test_*.py`; functions: `test_*`; classes: `Test*`

### Testing
- Pytest is the primary runner
- Add tests for new features; include regression tests for bug fixes

### Commits
- Conventional Commits: `feat(scope): subject`, `fix(scope): subject`
- Do NOT add `Co-Authored-By` trailers to commit messages
- PRs should include description, test results, and relevant docs updates

### ACE Roles (quick reference)

| Role | Responsibility | Key Class |
|------|---------------|-----------|
| **Agent** | Executes tasks using skillbook strategies | `Agent` |
| **Reflector** | Analyzes execution results | `Reflector` |
| **SkillManager** | Updates the skillbook with new strategies | `SkillManager` |

### Integration Runners

| Runner | Framework | Use Case |
|--------|-----------|----------|
| `ACELiteLLM` | LiteLLM (100+ providers) | Simple self-improving agent |
| `ACELangChain` | LangChain | Wrap chains/agents with learning |
| `ACEBrowserUse` | browser-use | Browser automation with learning |
| `ACEClaudeCode` | Claude Code CLI | Coding tasks with learning |

NEVER USE FALLBACKS OR IMPLEMENT THINGS I NEVER ASKED FOR.
IF IT'S STRAIGHFORWARD, IMPLEMENT IT STRAIGHFORWARD.


===== FILE crev-dev/cargo-crev::CLAUDE.md | stars=2326 followers=None lang=Rust bytes=2697 =====

# cargo-crev

Cryptographically verifiable code review system for the Rust/Cargo ecosystem.
Implements the Crev protocol: Ed25519-signed code reviews + a distributed Web of Trust.

## Workspace Structure (strict layering, low → high)

1. **crev-common** — Shared utilities: blake2b256 hashing, filesystem helpers, YAML I/O
2. **crev-data** — Core data types: proofs, identities, trust levels, cryptographic signing (ed25519-dalek)
3. **crev-wot** — Web of Trust engine: trust set computation, review aggregation
4. **crev-lib** — Library API (like libgit2 for Crev): local proof store, identity management, git-backed repos
5. **cargo-crev** — CLI binary: Cargo subcommand, dependency analysis, crates.io integration

Each layer may only depend on layers below it. The `crevette` crate is excluded from the workspace.

## Building & Testing

```sh
cargo build                    # build all crates
cargo test                     # run all tests
cargo clippy --workspace       # lint
cargo fmt --all                # format
```

Nix environment: `nix develop` (sets up toolchain, rust-analyzer, git hooks).

## Key Dependencies

- `ed25519-dalek` — cryptographic signing
- `git2` — proof repository storage (git-backed)
- `cargo` (0.91) — Cargo internals for dependency resolution (cargo-crev only)
- `crates_io_api` — crates.io metadata queries
- `serde_yaml` / `serde_cbor` — proof serialization
- `structopt` — CLI argument parsing
- `petgraph` — dependency graph analysis
- `tokei` — lines-of-code statistics
- `geiger` — unsafe code detection (optional feature)

## Code Conventions

- Rust edition 2021, MSRV 1.77
- Triple-licensed: MPL-2.0 OR MIT OR Apache-2.0
- `rustfmt.toml` in each crate (edition = "2021" at root)
- Clippy with `--deny warnings` in CI
- Pre-commit hooks: rustfmt, shellcheck, nixpkgs-fmt, trailing-newline check

## CI

- GitHub Actions: test matrix across stable/beta/nightly, x86_64/i686/ARM/musl, Linux/macOS
- Nix CI: build, test, clippy, doc checks
- Release workflow triggered by `v*` tags; builds cross-platform binaries

## Project Layout

```
cargo-crev/src/main.rs    — CLI entry point + main command dispatch (~44KB)
cargo-crev/src/opts.rs    — CLI option definitions (structopt)
cargo-crev/src/deps/      — Dependency analysis logic
cargo-crev/src/review.rs  — Review creation workflow
crev-data/src/proof/      — Proof types and serialization
crev-wot/src/trust_set.rs — Core WoT algorithm
crev-lib/src/local.rs     — Local proof store management
ci/                        — CI helper scripts
misc/git-hooks/            — Pre-commit hook scripts
design/purpose.md          — Design rationale document
```


===== FILE gnuton/asuswrt-merlin.ng::AGENTS.md | stars=2251 followers=None lang=C bytes=3063 =====

# AGENTS.md - AsusWrt-Merlin.ng

This repository is a fork of AsusWrt-Merlin designed to support additional router models. It contains a mix of open-source (GPL) and proprietary components.

## Git Workflow & Branches
- **Upstream**: The original source. Data from upstream branches or tags is merged into origin branches.
- **Origin**: The target for pushing changes.
- **Firmware Versions**:
  - `master`: Version 3004.
  - `master-3006`: Version 3006.
- **Feature Branches**: Branch names start with `DEV_`.
- **Version Format**: Versions in changelogs follow the pattern `3004.388.11_1-gnuton1`.

## Supported Models (via GitHub Actions)
- **Version 3006**: `GT-BE98`.
- **Version 3004**: `rt-ax92u`, `dsl-ax82u`, `tuf-ax5400`, `tuf-ax3000`, `rt-ax82u`, `rt-ax95q`, `rt-axe95q`, `rt-ax82u_v2`, `rt-ax5400`, `tuf-ax3000_v2`, `rt-ax58u_v2`.

## Architecture & Structure
- `release/src/`: Main source tree for the firmware.
- `release/src-rt-*/`: Model-specific source trees (e.g., `src-rt-5.04axhnd.675x`).
- `www/`: Web user interface files.
- `scripts/` and `tools/`: Build and helper utilities.

## Build System
The build system uses a complex set of Makefiles centered around `release/src/Makefile`.

### Key Build Commands
Run from `release/src/`:
- `make [model_id]`: Builds the image for a specific model.
- `make mk-[package]`: Builds a specific package.
- `make distclean`: Cleans all configurations and builds.
- `make cleanimage`: Removes generated images in `image/`.
- `make cleankernel`: Performs a `distclean` of the Linux kernel while preserving `.config`.

### Build Process Notes
- The build process involves copying "base" config files to "target" config files and then applying modifications based on the target profile.
- Trust the `Makefile` targets and logic over prose documentation for the exact build sequence.

## Development Constraints
- **Proprietary Code**: Proprietary components from ASUSTeK, Broadcom, Trend Micro, and Tuxera are present. These are licensed ONLY for original ASUSTeK devices.
- **Prebuilt Components**: Many components in `prebuilt` directories are precompiled binaries. Source code for these is not available; changes requiring modifications to these binaries cannot be implemented.
- **Style**: Follow existing C and shell script conventions found in the `release/src/router` and `release/src-rt-*` directories. Avoid introducing modern styles that might break compatibility with the legacy toolchain.

## Verification
- There is no single global test suite (like `npm test`). Verification is typically performed by building the image and flashing it to hardware or using specific package build targets (`mk-[package]`).
- Use `nvram get productid` via SSH on a physical router to verify model versions.



## Verification
- There is no single global test suite (like `npm test`). Verification is typically performed by building the image and flashing it to hardware or using specific package build targets (`mk-[package]`).
- Use `nvram get productid` via SSH on a physical router to verify model versions.


===== FILE timeplus-io/proton::.claude/CLAUDE.md | stars=2234 followers=None lang=C++ bytes=3971 =====

# Timeplus Proton — Claude Code Instructions

## Invariants (always apply)

- C++20 streaming SQL engine extending ClickHouse with real-time stream processing
- Always use stripped binaries: `build/programs/stripped/bin/proton`, `build/src/stripped/bin/unit_tests_dbms`
- Temp files → `./tmp/` under the current working tree, NEVER `/tmp`
- Proton fences (`/// proton: starts/ends`) ONLY in ClickHouse-inherited code
- NEVER fence in `src/Storages/Stream/` or `namespace DB::Streaming` (already Proton-specific)
- Dual query modes: `SELECT FROM stream` = streaming; `SELECT FROM table(stream)` = historical
- All streams auto-add `_tp_time datetime64(3, 'UTC')` for event-time semantics

## Working conventions

- Do not rebase or amend shared history; add new commits instead.
- Do not commit directly to `develop`; create a branch or worktree for each task.
- C++ formatting follows the repo `.clang-format`; opening braces normally go on their own line.
- Multiple local build directories are supported, including `build`, `build_asan`, `build_tsan`, `build_ubsan`, and `build_release`.
- Always configure builds via the repo's `build.sh` from inside the chosen build directory (for example `mkdir -p build && cd build && ../build.sh Debug`); do not replace it with ad-hoc direct `cmake` configure commands unless the user explicitly asks.
- If a task needs temporary logs, downloads, or scripts, use a `tmp/` directory under the current working tree, not `/tmp`.

## Tool shortcuts

- For CI failure or performance-report investigation, prefer `/ci-diagnostics` and the uploaded report URLs from commit statuses over raw GitHub Actions logs.

## Skill routing

| Task | Skill |
|------|-------|
| Build, compile, run server/client/cluster, execute tests, verify results, troubleshoot build/test failures | [build-and-verify](skills/build-and-verify/SKILL.md) |
| Write/review C++ code, C++ design/style discussions | [cpp-coding](skills/cpp-coding/SKILL.md) |
| Write/debug streaming SQL, SQL semantics/behavior questions (EMIT, windows, JOINs, UDFs) | [sql-usage](skills/sql-usage/SKILL.md) |
| Review a PR, branch, or diff for correctness, streaming semantics, and performance | [review](skills/review/SKILL.md) |
| Create an isolated git worktree with local submodule reuse | [create-worktree](skills/create-worktree/SKILL.md) |
| Analyze collapsed allocation profiles or jemalloc dumps | [alloc-profile](skills/alloc-profile/SKILL.md) |
| Diagnose CI failures or performance comparison reports | [ci-diagnostics](skills/ci-diagnostics/SKILL.md) |

> Any task that involves a GitHub issue number (e.g. `#1234`), bug report, or feature request and needs issue triage, bounded implementation, targeted verification, gate review, or end-to-end issue delivery → use Agent tool with `issue-workflow` agent (orchestrates `issue-implement`, `issue-verify`, and `issue-review`). Unless the user explicitly opts out of local commit or draft PR creation, it should continue through both. Use the normal git/gh flow for standalone branch naming, commit message, commit, push, or PR creation tasks that are not part of an `issue-workflow` run.

## Invoking skills

Skills are invoked with the `/` slash command syntax:

```
/build-and-verify
/cpp-coding
/sql-usage
/review
/create-worktree
/alloc-profile
/ci-diagnostics
```

Each skill's `SKILL.md` provides concise commands, checklists, and decision tables. Detailed references are in `skills/<skill>/references/`.

## Primary documentation

- Streaming SQL reference: https://docs.timeplus.com
- Docs repo (markdown source): https://github.com/timeplus-io/docs/tree/main/docs
  - SQL reference files: `sql-*.md` (e.g., `sql-create-stream.md`, `sql-create-view.md`)
  - Streaming topics: `streaming-*.md` (e.g., `streaming-aggregations.md`, `streaming-joins.md`)
  - Stream types: `append-stream.md`, `mutable-stream.md`, `external-stream.md`, etc.
- Offline summaries: `skills/*/references/` (synced from docs above)


===== FILE immichFrame/ImmichFrame::CLAUDE.md | stars=2230 followers=None lang=C# bytes=1569 =====

# ImmichFrame – Claude Instructions

## Release Writeup Rule

When asked to create a release writeup or release notes, follow this process and format:

### Process

1. Run `git log --oneline <prev-tag>..HEAD` to get all commits since the last release.
2. Run `git diff <prev-tag>..HEAD --stat` to understand the scope of changes.
3. Fetch the GitHub release page if a URL is provided to cross-reference the auto-generated changelog.
4. Combine the raw git history with the GitHub changelog to produce a human-friendly writeup.

### Output Format

Use the template at `templates/release-template.md`. Key rules:

- **Title**: `# 📦 ImmichFrame Release vX.X.X.X – <Date>`
- **Intro**: One sentence summarising the release highlights (no heading).
- **Sections**: Follow the category order from `.github/release.yml` — Breaking Changes, New Features, Fixes, Documentation, Maintenance, Other Changes.
- **Each entry**:
  - H4 heading with emoji + feature name
  - Bold `**PR [#NNN](url) by @author**` attribution line
  - 2–4 sentences describing *what* changed and *why it matters* to the user
  - Include a code block if a config snippet helps illustrate usage
  - Separate entries with `---`
- **New Contributors**: Call out first-time contributors with 🎉
- **Footer**: Always end with the full changelog comparison URL.

### Tone

- Write for end users, not developers. Avoid internal refactor jargon unless it has a user-visible effect.
- Keep descriptions concise — 2–4 sentences per entry is enough.
- Use "you" / "your" to address users directly.


===== FILE jwadow/kiro-gateway::AGENTS.md | stars=2144 followers=None lang=Python bytes=28543 =====

# AGENTS.md - Guide for AI Agents Working in Kiro Gateway

This document provides essential information for AI agents (Claude, GPT, etc.) working in the Kiro Gateway codebase.

## Project Philosophy

**Kiro Gateway is a transparent proxy with minimal, purposeful modifications.**

This is a **reverse engineering project** for Kiro API (Amazon Q Developer). We expose undocumented functionality and work around API quirks. Transparency means being clear about what we add, not refusing to add anything.

### Core Principles

1. **Transparency First**
   - The gateway preserves the user's original intent and request structure
   - Modifications are made only when necessary to work around Kiro API limitations or to add opt-in enhancements
   - We fix API quirks, not user decisions

2. **Minimal Intervention**
   - Changes to requests are surgical and well-justified
   - We add capabilities (like extended thinking) but never remove user content
   - Every modification must serve a clear purpose: fixing validation issues, adding optional features, or improving compatibility

3. **User Control**
   - All optional enhancements must be configurable
   - Users can disable features to get native Kiro API behavior
   - The gateway respects user choices about conversation structure and content

4. **Clear Boundaries**
   - ✅ **We fix**: API validation quirks, format incompatibilities, authentication flows
   - ✅ **We add (optionally)**: Enhanced features that Kiro API doesn't provide natively
   - ❌ **We don't modify**: User's conversation content, context decisions, message priorities
   - ❌ **We don't decide**: What messages to keep, what to trim, what's "important"

5. **Responsibility Separation**
   - Gateway handles API-level issues
   - Client handles content-level decisions
   - Model handles capacity limitations

6. **Systems Over Patches**
   - When solving a problem, we build systems that handle entire classes of issues, not one-off fixes
   - Even if a quick if-else would work, we invest time in creating proper abstractions and dedicated modules
   - Solutions should be easily extensible without modifying core logic
   - We prefer spending a few extra minutes on architecture that scales over quick hacks that accumulate technical debt
   - Every fix is an opportunity to create infrastructure that prevents similar problems in the future

7. **Paranoid Testing Philosophy**
   - Every commit must include tests - no exceptions
   - Tests exist to break code, not to confirm it works
   - Happy path alone is worthless - we test edge cases, error scenarios, boundary conditions, and malformed inputs
   - If you can't think of ways to break your code, you haven't thought hard enough
   - Two basic tests are not testing - comprehensive coverage means testing every logical branch and failure mode
   - Tests are both documentation and a safety net - they should clearly show what the code does and prevent regressions
   - Check `tests/README.md` to find the appropriate existing `test_*.py` file for your tests - avoid creating new test files unless adding a completely new module

8. **Code Quality Standards**
   - All code, comments, docstrings, and variable names must be in English (except for specific cases like Unicode tests or multilingual examples)
   - Comprehensive docstrings for all functions (Google style with Args/Returns/Raises)
   - Type hints are mandatory - every function parameter and return value must be typed
   - Logging at key decision points using loguru (INFO for business logic, DEBUG for technical details, ERROR for failures)
   - Never use bare `except:` or `except Exception:` - catch specific exceptions and add context
   - Proactive tech debt cleanup - if you see hardcoded values or duplicated code, extract it immediately (constants, functions, modules)
   - No placeholders - every function must be complete and production-ready when committed

9. **User Experience First**
   - Error messages must be actionable and user-friendly, not technical jargon
   - When something fails, explain what went wrong and how to fix it
   - Configuration should be intuitive with sensible defaults
   - Debug logging exists to help users troubleshoot, not just for developers
   - Documentation is part of the feature - if users can't figure it out, it doesn't work
   - Every error should guide the user toward a solution, not leave them confused

10. **Complete Feature Consistency**
   - When adding new functionality, implement it for BOTH OpenAI and Anthropic APIs
   - Changes must be applied to BOTH streaming and non-streaming code paths
   - Both API surfaces must have equal capabilities - no fragmentation
   - Test coverage must include all combinations: OpenAI streaming/non-streaming, Anthropic streaming/non-streaming
   - If a feature only makes sense for one API or one mode, document why explicitly

11. **Pragmatic Transparency**
   - Transparency means being clear about modifications, not refusing to add useful features
   - Response enrichment (adding derived fields) is acceptable if it doesn't break compatibility
   - Clients can ignore added fields - original upstream data is always preserved

### Code Review Reality Check

**Your code quality reveals your approach.** Contributions missing tests, using non-English identifiers, or lacking consistency across architecture and both APIs and streaming modes indicate surface-level work - a quick hack and patch based on assumptions rather than understanding. Such PRs face significant scrutiny and likely rejection.

**What we look for:**
- Comprehensive tests that attempt to break the code, not just confirm it works
- Complete consistency: changes applied to OpenAI + Anthropic, streaming + non-streaming
- Evidence you studied the codebase (using search tools, reading related modules) rather than guessing
- English-only code that integrates naturally with existing patterns

**What signals low effort:**
- "I'll add tests later" or minimal happy-path tests
- Changes to only one API or only one mode
- Non-English variable names or comments
- Code that doesn't match project patterns because you didn't check them

We can tell when you've used basic prompts for a quick fix versus when you've invested time understanding the architecture. The former gets rejected. The latter gets merged.

### About "Improperly formed request" Errors

**Important**: Kiro API's "Improperly formed request" error is notoriously vague due to poor documentation from Amazon. This single error message can indicate many different validation issues:

- Message structure problems (wrong role order, missing required fields)
- Tool definition issues (invalid schemas, name length violations)
- Content format problems (malformed JSON, unsupported content types)
- Authentication or permission issues
- Undocumented API constraints

When debugging this error, systematic testing is required to identify the actual cause. The gateway fixes known validation quirks, but new edge cases may emerge as Kiro API evolves.

## Project Overview

**Kiro Gateway** is a Python FastAPI proxy server that provides OpenAI-compatible and Anthropic-compatible APIs for Kiro (Amazon Q Developer / AWS CodeWhisperer). It translates requests between different API formats and handles authentication, streaming, model resolution, and error handling.

- **Language**: Python 3.10+
- **Framework**: FastAPI with uvicorn
- **License**: AGPL-3.0
- **Main Entry Point**: `main.py`
- **Package**: `kiro/` directory

## Essential Commands

### Running the Server

```bash
# Default (host: 0.0.0.0, port: 8000)
python main.py

# Custom port
python main.py --port 9000

# Custom host and port
python main.py --host 127.0.0.1 --port 9000

# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_auth_manager.py -v

# Run specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run with coverage
pip install pytest-cov
pytest --cov=kiro --cov-report=html
```

### Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Main dependencies:
# - fastapi
# - uvicorn[standard]
# - httpx
# - loguru
# - requests
# - python-dotenv
# - tiktoken
# - pytest
# - pytest-asyncio
# - hypothesis
```

### Docker (Containerization)

```bash
# Build Docker image
docker build -t kiro-gateway .

# Run with Docker (using environment variables)
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="your-secret-key" \
  -e REFRESH_TOKEN="your-refresh-token" \
  --name kiro-gateway \
  kiro-gateway

# Run with docker-compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Run with custom .env file
docker-compose --env-file .env.production up -d

# Mount credentials file (Kiro IDE)
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway

# Mount kiro-cli database
docker run -d \
  -p 8000:8000 \
  -v ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli \
  -e KIRO_CLI_DB_FILE=/home/kiro/.local/share/kiro-cli/data.sqlite3 \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway
```

**Docker Features:**
- Single-stage optimized build
- Non-root user (`kiro`) for security
- Health check endpoint monitoring (`/health`)
- Volume mounts for credentials and debug logs
- Automatic restart on failure
- Support for all 4 authentication methods
- Resource limits (optional in docker-compose.yml)

**CI/CD Integration:**
- GitHub Actions workflow (`.github/workflows/docker.yml`)
- Automated testing before Docker build
- Docker image testing (health checks)
- Automatic push to GitHub Container Registry (ghcr.io) on main branch
- Coverage report generation

## Project Structure

```
kiro-gateway/
├── main.py                          # Application entry point
├── kiro/                            # Main package
│   ├── __init__.py                  # Package exports
│   ├── config.py                    # Configuration and constants
│   ├── auth.py                      # Authentication manager
│   ├── account_manager.py           # Account system with Circuit Breaker, sticky behavior, lazy init
│   ├── account_errors.py            # Account error classification
│   ├── cache.py                     # Model metadata cache
│   ├── model_resolver.py            # Dynamic model resolution
│   ├── http_client.py               # HTTP client with retry logic
│   ├── routes_openai.py             # OpenAI API endpoints
│   ├── routes_anthropic.py          # Anthropic API endpoints
│   ├── converters_core.py           # Shared conversion logic
│   ├── converters_openai.py         # OpenAI format converters
│   ├── converters_anthropic.py      # Anthropic format converters
│   ├── streaming_core.py            # Shared streaming logic
│   ├── streaming_openai.py          # OpenAI streaming
│   ├── streaming_anthropic.py       # Anthropic streaming
│   ├── parsers.py                   # AWS SSE stream parsers
│   ├── thinking_parser.py           # Thinking block parser (FSM)
│   ├── models_openai.py             # OpenAI Pydantic models
│   ├── models_anthropic.py          # Anthropic Pydantic models
│   ├── network_errors.py            # Network error classification
│   ├── kiro_errors.py               # Kiro API error enhancement
│   ├── exceptions.py                # Exception handlers
│   ├── payload_guards.py            # Request payload validation
│   ├── truncation_state.py          # Truncation state tracking
│   ├── truncation_recovery.py       # Truncation recovery system
│   ├── mcp_tools.py                 # MCP tools (web_search)
│   ├── debug_logger.py              # Debug logging system
│   ├── debug_middleware.py          # Debug middleware
│   ├── tokenizer.py                 # Token counting (tiktoken)
│   └── utils.py                     # Helper utilities
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
├── .env.example                     # Environment configuration template
├── requirements.txt                 # Python dependencies
└── pytest.ini                       # Pytest configuration
```

## Code Architecture

### Modular Design

The codebase follows a layered architecture:

1. **Routes Layer** (`routes_*.py`): FastAPI endpoints, authentication, request validation
2. **Converters Layer** (`converters_*.py`): Format translation (OpenAI/Anthropic → Kiro)
3. **Streaming Layer** (`streaming_*.py`): SSE stream processing (Kiro → OpenAI/Anthropic)
4. **Core Services**: Auth, HTTP client, model resolution, caching
5. **Parsers**: AWS event stream parsing, thinking block extraction
6. **Models**: Pydantic models for validation

### Key Components

#### Authentication (`auth.py`)

- **KiroAuthManager**: Manages token lifecycle
- Supports multiple auth methods:
  - JSON credentials file (Kiro IDE)
  - Environment variables (refresh token)
  - SQLite database (kiro-cli)
  - AWS SSO OIDC (Builder ID, Enterprise)
- Auto-detects auth type based on credentials
- Thread-safe token refresh with asyncio.Lock
- Automatic refresh before expiration

#### Model Resolution (`model_resolver.py`)

4-layer resolution pipeline:
1. **Normalize Name**: Convert client formats to Kiro format (dashes→dots, strip dates)
2. **Check Dynamic Cache**: Models from /ListAvailableModels API
3. **Check Hidden Models**: Manual config for undocumented models
4. **Pass-through**: Unknown models sent to Kiro (let Kiro decide)

Key principle: **We are a gateway, not a gatekeeper**. Kiro API is the final arbiter.

#### HTTP Client (`http_client.py`)

- **KiroHttpClient**: HTTP client with automatic retry logic
- Handles errors:
  - 403: Automatic token refresh and retry
  - 429: Exponential backoff
  - 5xx: Exponential backoff
  - Timeouts: Exponential backoff
- Supports per-request clients (for streaming) and shared clients (for connection pooling)
- Network error classification with user-friendly messages

#### Streaming (`streaming_*.py`)

- Parses AWS event stream format
- Converts to OpenAI or Anthropic SSE format
- Handles thinking blocks (extended thinking mode)
- First token timeout with retry logic
- Tool call parsing and deduplication

#### Converters (`converters_*.py`)

- **Core Layer** (`converters_core.py`): Shared logic for both APIs
  - UnifiedMessage format
  - Tool processing and sanitization
  - Message merging
  - Kiro payload building
- **OpenAI Adapter** (`converters_openai.py`): OpenAI → Kiro
- **Anthropic Adapter** (`converters_anthropic.py`): Anthropic → Kiro

## Code Conventions

### Naming

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`

### Type Hints

Always use type hints:

```python
def extract_text_content(content: Any) -> str:
    """Extract text from various content formats."""
    pass

async def refresh_token(self) -> str:
    """Refresh access token."""
    pass
```

### Docstrings

Use Google-style docstrings with Args/Returns sections:

```python
def normalize_model_name(name: str) -> str:
    """
    Normalize client model name to Kiro format.
    
    Transformations applied:
    1. claude-haiku-4-5 → claude-haiku-4.5 (dash to dot for minor version)
    2. claude-haiku-4-5-20251001 → claude-haiku-4.5 (strip date suffix)
    
    Args:
        name: External model name from client
    
    Returns:
        Normalized model name in Kiro format
    
    Examples:
        >>> normalize_model_name("claude-haiku-4-5-20251001")
        'claude-haiku-4.5'
    """
    pass
```

### Logging

Use loguru for all logging:

```python
from loguru import logger

logger.info("Server starting...")
logger.warning("Token expiring soon")
logger.error(f"Failed to refresh token: {e}")
logger.debug(f"Request payload: {payload}")
```

Log levels:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Warning messages (non-critical issues)
- `ERROR`: Error messages (failures)

### Error Handling

```python
from fastapi import HTTPException

# For API errors
raise HTTPException(status_code=401, detail="Invalid API Key")

# For internal errors with logging
try:
    result = await some_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Async/Await

All I/O operations are async:

```python
async def fetch_models(self) -> List[str]:
    """Fetch available models from Kiro API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

## Testing Philosophy

### Complete Network Isolation

**Critical**: All tests MUST be completely isolated from the network.

- Global fixture `block_all_network_calls` in `tests/conftest.py` blocks all httpx requests
- Any attempt to make real network calls will fail the test
- All external services are mocked

### Test Structure

Tests follow the **Arrange-Act-Assert** pattern:

```python
@pytest.mark.asyncio
async def test_token_refresh_success(mock_env_vars, mock_kiro_token_response):
    """
    Test successful token refresh.
    
    What it does: Verifies that KiroAuthManager correctly refreshes tokens
    Purpose: Ensure token lifecycle management works correctly
    """
    # Arrange
    auth_manager = KiroAuthManager()
    mock_response = mock_kiro_token_response(expires_in=3600)
    
    # Act
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response
        token = await auth_manager.get_valid_token()
    
    # Assert
    assert token == mock_response["accessToken"]
    assert auth_manager._access_token == token
```

### Test Organization

- **Unit tests** (`tests/unit/`): Test individual functions/classes in isolation
- **Integration tests** (`tests/integration/`): Test component interactions
- Test classes: `Test*Success`, `Test*Errors`, `Test*EdgeCases`
- Test names: `test_<what_it_does>_<expected_result>`

### Running Tests

Always run tests after making changes:

```bash
# Quick check
pytest tests/unit/test_<module>.py -v

# Full suite
pytest -v

# With coverage
pytest --cov=kiro --cov-report=html
```

## Configuration

### Environment Variables

Configuration is loaded from `.env` file (see `.env.example`):

```bash
# Required
PROXY_API_KEY="my-super-secret-password-123"

# Authentication (choose one method)
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"  # JSON file
REFRESH_TOKEN="your_refresh_token"                        # Direct token
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3" # SQLite DB

# Optional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
VPN_PROXY_URL="http://127.0.0.1:7890"  # For restricted networks

# Debug logging (off by default)
DEBUG_MODE="off"  # or "errors" or "all"
```

### Configuration Priority

1. CLI arguments: `python main.py --port 9000`
2. Environment variables: `SERVER_PORT=9000`
3. Default values: `8000`

## Important Patterns and Gotchas

### 1. Per-Request HTTP Clients for Streaming

**Critical**: Always use per-request clients for streaming to prevent CLOSE_WAIT leaks.

```python
# ✅ Correct: Per-request client for streaming
async with httpx.AsyncClient(timeout=timeout) as client:
    async with client.stream("POST", url, json=payload) as response:
        async for line in response.aiter_lines():
            yield line

# ❌ Wrong: Reusing shared client for streaming causes CLOSE_WAIT
```

### 2. Model Name Normalization

Model names are normalized before resolution:

```python
# Client sends: "claude-haiku-4-5-20251001"
# Normalized to: "claude-haiku-4.5"
# Sent to Kiro: "claude-haiku-4.5"
```

### 3. Tool Call Parsing

Kiro API may return tool calls in bracket format `[{...}]` instead of proper JSON. The parser handles this:

```python
# Kiro returns: "[{\"name\":\"get_weather\",\"arguments\":{...}}]"
# Parser extracts: [{"name": "get_weather", "arguments": {...}}]
```

### 4. Thinking Block Extraction

Extended thinking mode uses a finite state machine (FSM) to extract thinking blocks:

```python
# Input: "Let me think...<thinking>reasoning here</thinking>The answer is..."
# Extracted thinking: "reasoning here"
# Extracted content: "Let me think...The answer is..."
```

### 5. Network Error Classification

Network errors are classified into user-friendly categories:

```python
# httpx.ConnectTimeout → "Connection timeout"
# httpx.ReadTimeout → "Server response timeout"
# DNS errors → "DNS resolution failed"
```

### 6. Authentication Auto-Detection

Auth type is auto-detected based on credentials:

```python
# Has clientId/clientSecret → AWS SSO OIDC
# No clientId/clientSecret → Kiro Desktop Auth
```

### 7. Debug Logging Modes

Debug logging has three modes:

- `off`: Disabled (default, production)
- `errors`: Save logs only for failed requests (4xx, 5xx) - **recommended for troubleshooting**
- `all`: Save logs for every request (development)

Logs are saved to `debug_logs/` directory.

### 8. VPN/Proxy Support

For users in restricted networks (China, corporate):

```bash
VPN_PROXY_URL="http://127.0.0.1:7890"      # HTTP proxy
VPN_PROXY_URL="socks5://127.0.0.1:1080"    # SOCKS5 proxy
VPN_PROXY_URL="http://user:pass@proxy:8080" # With auth
```

## Common Tasks

### Adding a New Endpoint

1. Define Pydantic models in `models_*.py`
2. Add route in `routes_*.py`
3. Add converter in `converters_*.py`
4. Add streaming logic in `streaming_*.py`
5. Write tests in `tests/unit/test_routes_*.py`

### Adding a New Model

Models are dynamically fetched from Kiro API. To add a hidden model:

```python
# In config.py
HIDDEN_MODELS = [
    "claude-new-model-1.0",
]
```

### Debugging Issues

1. Enable debug logging: `DEBUG_MODE="errors"` in `.env`
2. Check `debug_logs/` directory for request/response logs
3. Run tests: `pytest tests/unit/test_<module>.py -v`
4. Check application logs (loguru output)

### Making Changes

1. **Read before editing**: Always view files before modifying
2. **Follow existing patterns**: Check similar code for style
3. **Add tests**: Write tests for new functionality
4. **Run tests**: `pytest -v` before committing
5. **Check types**: Use type hints throughout
6. **Document**: Add docstrings with Args/Returns

## API Endpoints

### OpenAI-Compatible API

- `GET /`: Health check
- `GET /health`: Detailed health check
- `GET /v1/models`: List available models
- `POST /v1/chat/completions`: Chat completions (streaming and non-streaming)

### Anthropic-Compatible API

- `POST /v1/messages`: Messages API (streaming and non-streaming)

### Authentication

All endpoints require authentication:

```bash
# OpenAI format
Authorization: Bearer {PROXY_API_KEY}

# Anthropic format
x-api-key: {PROXY_API_KEY}
```

## Dependencies and Imports

### Core Dependencies

```python
# FastAPI
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

# HTTP client
import httpx

# Logging
from loguru import logger

# Environment
from dotenv import load_dotenv
import os

# Type hints
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

# Async
import asyncio

# Pydantic
from pydantic import BaseModel, Field, validator
```

### Internal Imports

```python
# Configuration
from kiro.config import PROXY_API_KEY, REGION, APP_VERSION

# Auth
from kiro.auth import KiroAuthManager, AuthType

# Models
from kiro.models_openai import ChatCompletionRequest, ChatMessage
from kiro.models_anthropic import AnthropicMessagesRequest

# Converters
from kiro.converters_openai import build_kiro_payload
from kiro.converters_anthropic import build_kiro_payload_anthropic

# Streaming
from kiro.streaming_openai import stream_kiro_to_openai
from kiro.streaming_anthropic import stream_kiro_to_anthropic

# HTTP client
from kiro.http_client import KiroHttpClient

# Model resolution
from kiro.model_resolver import ModelResolver, normalize_model_name
```

## Git Workflow

### Recent Changes

Check recent commits for context:

```bash
git log --oneline -20
```

Recent features:
- Network error classification with user-friendly messages
- Per-request clients for streaming (CLOSE_WAIT leak fix)
- Cursor flat format support
- Inverted model names support
- HTTP/SOCKS5 proxy support
- Enterprise Kiro IDE support
- AWS SSO OIDC authentication

### Making Commits

Follow existing commit message style:

```bash
# Format: <type>(<scope>): <description> (#issue)
# Types: feat, fix, docs, test, refactor, chore

git commit -m "feat(auth): add support for new auth method"
git commit -m "fix(streaming): handle empty chunks correctly"
git commit -m "docs: update configuration examples"
```

## Security Considerations

1. **Never log credentials**: Tokens, API keys, passwords
2. **Sanitize errors**: Don't expose internal details to clients
3. **Validate input**: Use Pydantic models for all requests
4. **Use HTTPS**: In production, always use HTTPS
5. **Rate limiting**: Consider adding rate limiting for production

## Performance Considerations

1. **Connection pooling**: Use shared httpx.AsyncClient for non-streaming requests
2. **Per-request clients**: Use per-request clients for streaming to prevent leaks
3. **Async everywhere**: All I/O operations are async
4. **Caching**: Model metadata is cached to reduce API calls
5. **Streaming**: Use streaming for large responses to reduce memory usage

## Troubleshooting

### Tests Failing

```bash
# Check if dependencies are installed
pip install -r requirements.txt

# Run specific test with verbose output
pytest tests/unit/test_<module>.py::test_<name> -v -s

# Check for network isolation violations
# All tests should pass without internet connection
```

### Server Not Starting

```bash
# Check if port is already in use
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Use different port
python main.py --port 9000

# Check environment variables
cat .env
```

### Authentication Errors

```bash
# Check credentials file exists
ls -la ~/.aws/sso/cache/

# Check environment variables
echo $REFRESH_TOKEN
echo $KIRO_CREDS_FILE

# Enable debug logging
DEBUG_MODE="errors" python main.py
```

## Resources

- **README.md**: User-facing documentation
- **tests/README.md**: Testing documentation
- **.env.example**: Configuration template
- **GitHub Issues**: https://github.com/jwadow/kiro-gateway/issues

## Summary

Kiro Gateway is a well-architected Python FastAPI application with:

- ✅ Modular design with clear separation of concerns
- ✅ Comprehensive test suite with complete network isolation
- ✅ Type hints and docstrings throughout
- ✅ Async/await for all I/O operations
- ✅ Automatic retry logic and error handling
- ✅ Dynamic model resolution
- ✅ Multiple authentication methods
- ✅ Streaming support for both OpenAI and Anthropic APIs
- ✅ Debug logging system
- ✅ VPN/Proxy support for restricted networks

When working in this codebase:
1. **Read before editing** - Always view files first
2. **Follow patterns** - Check similar code for style
3. **Test everything** - Run `pytest -v` after changes
4. **Use type hints** - Always add type annotations
5. **Document changes** - Add docstrings with Args/Returns
6. **Isolate tests** - Never make real network calls in tests


===== FILE phuryn/claude-usage::AGENTS.md | stars=2068 followers=1026 lang=Python bytes=16502 =====

# AGENTS.md

Guidance for any coding agent (Codex, Claude Code, etc.) working on this repository.

> **Naming note.** This project *analyzes* Claude Code's local usage logs, so "Claude Code" below always refers to that product (the source of the JSONL data) — not to the agent reading this file. The agent working on the codebase is referred to as "the coding agent" or just "you".

## Project shape

Three Python files, stdlib only, no `pip install` step. Python 3.8+.

- [scanner.py](scanner.py) — parses Claude Code JSONL transcripts into a SQLite DB at `~/.claude/usage.db`.
- [cli.py](cli.py) — terminal commands (`scan` / `today` / `week` / `stats` / `dashboard`).
- [dashboard.py](dashboard.py) — single-file `http.server` serving an embedded HTML/JS SPA on `localhost:8080`.

Use `python` on Windows, `python3` on macOS/Linux. Both work the same.

## Common commands

```
python cli.py scan                  # incremental scan (fast on re-run)
python cli.py today                 # today's usage by model
python cli.py week                  # last 7 days, per-day + by-model
python cli.py stats                 # all-time stats
python cli.py dashboard                          # scan + open http://localhost:8080
python cli.py dashboard --host 0.0.0.0 --port 9000
python cli.py scan --projects-dir PATH           # scan a custom transcripts dir
# or via env vars:
HOST=0.0.0.0 PORT=9000 python cli.py dashboard

python -m unittest discover -s tests -v             # full test suite (CI runs this)
python -m unittest tests.test_scanner -v            # one file
python -m unittest tests.test_scanner.TestProjectNameFromCwd.test_windows_path  # one test
```

CI ([.github/workflows/tests.yml](.github/workflows/tests.yml)) runs the suite on Python 3.9 / 3.11 / 3.12 against `main` and PRs.

## Architecture

### Data flow

```
~/.claude/projects/**/*.jsonl   →   scanner.parse_jsonl_file()
~/Library/.../Xcode/...                  ↓
                              aggregate_sessions() → upsert_sessions() + insert_turns()
                                         ↓
                              ~/.claude/usage.db (SQLite)
                                         ↓
                  cli.py queries   ←──────────→   dashboard.py /api/data
```

By default the scanner walks both `~/.claude/projects/` and the Xcode coding-assistant directory; missing dirs are silently skipped. Override with `--projects-dir`.

### SQLite schema (created/migrated in [scanner.py](scanner.py) `init_db`)

- **`turns`** — one row per assistant API response. The source of truth for tokens and per-model attribution.
- **`sessions`** — aggregated per session (denormalized totals + chosen primary model).
- **`processed_files`** — incremental-scan tracking: `(path, mtime, lines)`. A file is skipped if its mtime matches; if it grew, only lines past the stored `lines` count are processed.

A conditional unique index on `turns.message_id` (where non-empty) lets `INSERT OR IGNORE` cheaply dedupe replays across rescans.

### Non-obvious invariants

These three things will bite you if you don't know them:

1. **Streaming dedupe by `message.id`.** Claude Code writes multiple JSONL records per API response — only the *last* one for a given `message.id` has the final usage tallies. `parse_jsonl_file` keeps the last record per `message_id` in a dict; earlier records are discarded. Don't sum across records of the same `message_id`.

2. **Session totals are recomputed from `turns` at the end of `scan()`.** During an incremental scan `upsert_sessions` adds tokens additively, but `insert_turns` uses `INSERT OR IGNORE` against the `message_id` unique index — so if a turn is a duplicate, session totals would drift. The final `UPDATE sessions ... (SELECT SUM ... FROM turns)` block reconciles this. Preserve it if you refactor scan logic.

3. **Session primary model priority is opus > sonnet > haiku** (`_model_priority` in [scanner.py](scanner.py)). This prevents a subagent's haiku turn from overwriting the session's opus model when an existing session is updated. Per-turn model is always honored in the `turns` table; only the session-level summary uses the priority.

### Cost calculation

Costs are computed **per turn** (each turn knows its own model), then summed. This is true in both the CLI ([cli.py](cli.py) `calc_cost`) and the dashboard JS ([dashboard.py](dashboard.py) `calcCost` inside the embedded HTML). Aggregating tokens first and applying a single price is wrong for sessions that span multiple models.

Pricing is duplicated in two places that **must stay in sync**:
- [cli.py](cli.py) `PRICING` dict (Python)
- [dashboard.py](dashboard.py) `PRICING` const inside `HTML_TEMPLATE` (JavaScript)

`get_pricing` / `getPricing` resolve in three tiers: exact match → `startswith` (handles date-suffixed model IDs like `claude-opus-4-7-20260215`) → substring fallback on `opus` / `sonnet` / `haiku`. Models that don't match any tier return `None` and are billed at $0 (shown as `n/a`) — this is intentional so local/3rd-party models (gemma, glm, etc.) aren't charged at Sonnet rates.

### Dashboard server

`http.server.BaseHTTPRequestHandler`-based, two endpoints:
- `GET /api/data` → JSON snapshot from `get_dashboard_data()`. Returns *all* history; client-side filters by date range and model.
- `POST /api/rescan` → deletes the DB and runs a full rescan. Passes `db_path` and `projects_dirs` explicitly so tests that monkey-patch the module globals work — scan's default arg values are frozen at def time, so don't switch to bare defaults.

The entire UI lives in `HTML_TEMPLATE` as a raw string. Chart.js is loaded from CDN.

Client-side UI state (collapsed sections, the 24h update-check cache) is kept in **`localStorage`**, which is keyed by the page's origin. In the VS Code extension the dashboard is embedded as an **iframe at `http://127.0.0.1:<port>/`**, so that state only survives a window reload if the port is stable. The extension therefore remembers the last port in `workspaceState` and reuses it when it's still free (`resolveStablePort` in [vscode-extension/src/port-allocator.ts](vscode-extension/src/port-allocator.ts)) — don't revert that to a fresh `pickFreePort` every launch, or the panel silently loses its state each reload.

## Testing notes

- `tests/test_scanner.py` and `tests/test_dashboard.py` use `tempfile.NamedTemporaryFile` for an isolated DB; never touch the user's real `~/.claude/usage.db`.
- The `/api/rescan` test patches `dashboard.DB_PATH` and `scanner.DEFAULT_PROJECTS_DIRS` — keep that contract intact (see commit 8ae2664).
- On Windows, `~/.claude/` may not exist on a fresh checkout. `get_db` creates the parent dir (`mkdir(parents=True, exist_ok=True)`) — don't remove that or `sqlite3.connect` will fail in CI / fresh installs (commit b5d1e15).

## Respecting contributors

When merging community PRs, **preserve the original author's commit so they get GitHub contributor credit**. In practice:

- `git fetch origin pull/<N>/head:pr-<N>` → `git merge --no-ff pr-<N>` keeps the author commit verbatim inside the merge bubble (don't squash, don't rebase-flatten).
- For a partial merge — when only one hunk of a PR is wanted — use `git cherry-pick <commit-sha>` against the specific upstream commit so authorship is preserved. If the diff isn't a clean single commit, fall back to applying the hunk manually + adding a `Co-Authored-By: Name <email>` trailer.
- Improvements that the bot/maintainer makes _on top_ of a contributor's work go in **separate follow-up commits**, not amendments to the contributor's commit.
- When closing duplicate PRs (multiple authors fixed the same bug independently), thank each one and explain that landing the earliest version isn't a quality judgment.

This applies to all agents working on this repo, not just Claude Code.

## Versioning and releases

[SemVer](https://semver.org/). **`CHANGELOG.md` is the canonical version reference**; tags are a projection of it, created automatically.

The release flow:
1. While work accumulates on `DEV`, the `## vX.Y.Z — TBD` heading at the top of `CHANGELOG.md` collects bullets. (For automated triage runs, see the routine note below.)
2. When the maintainer is ready to release, they finalize the heading (`TBD` → today's date), **bump both `scanner.VERSION` and `vscode-extension/package.json`'s `version` to match the CHANGELOG version** (all three ship in lockstep — the extension bundles the Python sources, and `scanner.VERSION` is the runtime version reported by `cli.py --version` and the dashboard footer since the CHANGELOG isn't bundled into the `.vsix`), **run [`scripts/bump-formula.sh`](scripts/bump-formula.sh) on `DEV` to repoint the Homebrew formula at the previous release's tag tarball** (see "Homebrew formula and self-referential SHA" below — this is a plain `DEV` commit that reaches brew users via this same merge, so it never touches `main` directly), merge `DEV → main` with `merge --no-ff` (so the release boundary is visible in `git log main`), and push `main`. A parity test (`tests/test_version.py`) fails the suite if the three drift, so in practice they're bumped together on `DEV` when the version heading is written.
3. [`.github/workflows/tag-on-merge.yml`](.github/workflows/tag-on-merge.yml) fires on the push, sees the new `## vX.Y.Z` heading in the CHANGELOG diff, and:
   - creates a lightweight tag at the merge commit (**no `git tag` step for the maintainer**), then
   - builds the VS Code extension `.vsix` and publishes a **GitHub Release** for that tag — the matching CHANGELOG section as the release notes, the built `.vsix` attached as a release asset.

So every release is both a tag *and* a GitHub Release with the installable `.vsix` downloadable from it. This mirrors the manual procedure in the sibling `grok-build-vscode` repo (`scripts/release.*`: tag + `gh release create` with the `.vsix` attached), adapted to this repo's CHANGELOG-driven, merge-to-`main` model — so it's automated rather than a local script. Marketplace publish (`vsce publish`) stays separate and explicit, exactly as there.

**The release step asserts `vscode-extension/package.json`'s version equals the CHANGELOG version and fails loudly if not** — the `.vsix` filename embeds the package version, so a mismatch would mislabel the asset. If you forget the bump, the tag is still created but the Release step fails; bump `package.json` and create the Release by hand (`gh release create vX.Y.Z --notes-file <section> vscode-extension/<name>-X.Y.Z.vsix`), since a same-commit re-push won't re-add the heading to re-trigger the workflow.

The workflow is idempotent: if the tag already exists (someone tagged manually before the workflow caught up) the tag step is a no-op, and if the Release already exists the release step is a no-op. It also no-ops entirely on pushes that don't add a new version heading (typo fixes, docs-only edits, etc.).

Existing tags `v1.0.0`, `v1.1.0`, `v1.1.1` are lightweight and were created by hand before the workflow existed. `v1.1.2` was the first tag created by the workflow. The workflow only *adds* missing tags; it never reconciles existing ones. Don't bother re-tagging the legacy ones.

### CHANGELOG conventions

The workflow trusts the CHANGELOG, so the format matters. Every new release entry on `DEV` follows this exact shape:

```
## vX.Y.Z — TBD

### <Area>

- One bullet per change, past tense, with a PR/issue link and `thanks @author` where the change came from a contributor (#73, thanks @thomasleveil)
```

Format rules the workflow relies on:

| Field | Required form | Why |
|---|---|---|
| Heading | `## vX.Y.Z` (exactly two `#`, the `v` prefix, three numeric components — strict semver) | The workflow regex `^## v[0-9]+\.[0-9]+\.[0-9]+([[:space:]]|$)` won't match anything else. `v1.1`, `v1.1.0-rc1`, `V1.1.0` are all silently ignored. |
| Separator | ` — ` (em-dash with surrounding spaces) | Cosmetic but consistent. The workflow ignores everything after the version. |
| Date | `TBD` while accumulating on `DEV`; replace with `YYYY-MM-DD` *at the moment of merging to `main`* | The workflow doesn't enforce dates — but a `TBD` heading that ships to main means the release looks unfinished forever. |
| Subsections | `### Dashboard`, `### Scanner`, `### Packaging`, `### Project / docs` — pick the smallest set that fits | Keeps the CHANGELOG scannable. |
| Bullets | Past tense, link the PR/issue with `#N`, credit external contributors with `thanks @login` | Lets readers (and future maintainers tracing history) find the source quickly. |

**The TBD → date rule is the only step a human must remember at release time.** If you forget, the workflow still tags correctly, but the CHANGELOG entry on main reads `## v1.1.3 — TBD` forever. Fix-up commit can correct it, but it'll feel sloppy.

Patch (`Z` increments) is the default for any release. Bump minor (`Y`) when a non-breaking user-visible feature lands (e.g. Today range button shipping alone would have been a minor in a different world). Bump major (`X`) only on breaking changes — there have been none and likely won't be soon. There's no automation around picking the right bump; the maintainer (or `/triage`) decides when writing the CHANGELOG heading on `DEV`.

### Homebrew formula and self-referential SHA

The Homebrew formula at `Formula/claude-usage.rb` lives inside this same repo. Be careful when bumping it: if the formula's `url` points at a tarball that **contains the formula itself with that sha256**, the sha256 is self-referential and uncomputable. Practical rule: a release's formula must point at the **previous** release's tarball, never its own. In v1.1.1 the formula points at v1.1.0's commit-SHA tarball, so brew users installing v1.1.1's formula receive v1.1.0 code — that's the trade-off of keeping the formula in-tree.

Now that the auto-tag workflow exists, formula bumps use the tag-tarball URL (`archive/refs/tags/vX.Y.Z.tar.gz`) instead of commit SHAs — stabler and shorter — as long as the tag-tarball pointed at is from the *previous* release.

**Automate the bump; never hand-edit the three pinned lines.** [`scripts/bump-formula.sh`](scripts/bump-formula.sh) fetches a released tag's tarball, computes its `sha256`, and rewrites the `url` / `version` / `sha256` lines (leaving `head`, `homepage`, and comments alone). With no argument it targets the latest `v*` tag on origin — run during release prep, before the new tag exists, that's the previous release, exactly what the self-referential rule requires.

**Why a `DEV`-only commit is enough — and why it's one release behind.** Brew reads the formula from the tap's default branch (`main`) HEAD, never from `DEV` or a tag. So the bump is a normal `DEV` commit that becomes visible to brew users only when `DEV → main` merges — which is precisely at the next release. That timing is the point: it lets us pin at the just-frozen *previous* tag and ship it with the release, so **brew always tracks one release behind, advancing automatically each release**, with no direct push to `main` (dodging `main`'s branch protection) and no hand-editing to forget. The manual, forget-prone bump is what let the pin silently rot at v1.1.0 from v1.1.1 through v1.5.0; v1.5.2 caught it up to v1.5.1 and wired in this routine. The only thing a `DEV`-only bump can't do is move brew *between* releases — you'd need a release (a `DEV → main` merge) for that, which is fine because the pin only ever changes at release boundaries anyway.

## Weekly triage routine

The repo has a self-contained slash command at [.claude/commands/triage.md](.claude/commands/triage.md) that automates the weekly PR/issue cleanup we used to ship v1.1.0: classify open items with Codex, merge no-brainers to DEV preserving authorship, run tests, close duplicates / scope-violations with friendly messages, bump CHANGELOG by patch, push DEV. **The routine never pushes to `main`** — release decisions stay with the maintainer.

Register the Windows Task Scheduler entry with [scripts/setup-weekly-triage.ps1](scripts/setup-weekly-triage.ps1). Logs go to `logs/triage-*.log`.

If you're working on this repo and want to invoke the routine ad-hoc, just type `/triage` in Claude Code. Hard safety rails (test-passing gates, no security-sensitive auto-merges, no scope-changing merges, Codex sign-off required on closures) live inside `triage.md`.


===== FILE konstructio/kubefirst::CLAUDE.md | stars=2053 followers=None lang=Go bytes=3064 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Building and Running
- **Build**: `go build` (creates `kubefirst` binary)
- **Run from source**: `go run .` (e.g., `go run . civo create`)
- **Run compiled**: `./kubefirst` (after building)

### Testing
- **Run all tests**: `go test -v ./...`
- **Run short tests**: `go test -short -v ./...` (used in CI)
- **Run specific test**: `go test -v ./path/to/package -run TestName`

### Linting
- **Lint**: `golangci-lint run` (uses `.golangci.yaml` configuration with 70+ linters)
- **Format code**: `gofmt -w .` or `gofumpt -w .`

### Development with Dependencies
- **Use development gitops-template**: Add flags `--gitops-template-url https://github.com/konstructio/gitops-template --gitops-template-branch main`
- **Use local kubefirst-api**: Export `K1_CONSOLE_REMOTE_URL="http://localhost:3000"` and run both kubefirst-api and console locally
- **For k3d development**: Add replace directive in go.mod: `github.com/konstructio/kubefirst-api vX.X.XX => /path-to/kubefirst-api/`

## Architecture

### Command Structure
The CLI uses Cobra with modular commands for each cloud provider:
- `cmd/` contains provider-specific commands (aws, azure, civo, digitalocean, google, k3d, k3s, vultr, akamai)
- Each provider has its own package with create/destroy/root commands
- Common functionality is shared through `internal/` packages

### Key Internal Packages
- **catalog**: Application catalog management for marketplace apps
- **cluster**: Cluster creation and management logic
- **progress**: BubbleTea-based terminal UI for interactive installations
- **provision**: Core provisioning logic that orchestrates cluster creation
- **gitShim**: Git operations wrapper for repository management
- **segment**: Analytics tracking (can be disabled)
- **utilities**: Shared helpers and constants

### Core Dependencies
- **kubefirst-api**: External API package that handles most cluster operations
- **runtime**: Used for k3d local development (being phased out)
- **BubbleTea**: Terminal UI framework for interactive progress display
- **Viper/Cobra**: Configuration and CLI framework

### Error Handling Pattern
All errors should be wrapped with context using `fmt.Errorf("meaningful message: %w", err)`. The codebase follows a pattern of returning errors up the call stack rather than using log.Fatal.

### Logging
- Dual logging system: standard log package and zerolog
- Logs are written to `~/.k1/logs/`
- Console output uses formatted messages for user feedback
- Debug logging available with appropriate flags

### GitOps Integration
Kubefirst creates complete GitOps platforms with:
- ArgoCD for continuous deployment
- Metaphor repositories for application management
- GitHub/GitLab integration for repository management
- Terraform for infrastructure as code

### Configuration
- CLI configurations stored in `~/.k1/` directory
- Uses Viper for configuration management
- Environment variables prefixed with `K1_` or `KUBEFIRST_`

===== FILE Comfy-Org/ComfyUI_frontend::AGENTS.md | stars=1913 followers=None lang=TypeScript bytes=18921 =====

# Repository Guidelines

See @docs/guidance/\*.md for file-type-specific conventions (auto-loaded by glob).

## Project Structure & Module Organization

- Source: `src/`
  - Vue 3.5+
  - TypeScript
  - Tailwind 4
  - Key areas:
    - `components/`
    - `views/`
    - `stores/` (Pinia)
    - `composables/`
    - `services/`
    - `utils/`
    - `assets/`
    - `locales/`
- Routing: `src/router.ts`,
- i18n: `src/i18n.ts`,
- Entry Point: `src/main.ts`.
- Tests:
  - unit/component in `src/**/*.test.ts`
  - E2E (Playwright) in `browser_tests/**/*.spec.ts`
- Public assets: `public/`
- Build output: `dist/`
- Configs
  - `vite.config.mts`
  - `playwright.config.ts`
  - `eslint.config.ts`
  - `.oxfmtrc.json`
  - `.oxlintrc.json`
  - etc.

## Monorepo Architecture

The project uses **pnpm workspaces** for monorepo organization and native tool CLIs for task execution

## Package Manager

This project uses **pnpm**. Always prefer scripts defined in `package.json` (e.g., `pnpm test:unit`, `pnpm lint`). To run arbitrary packages not in scripts, use `pnpx` or `pnpm dlx` — never `npx`.

## Build, Test, and Development Commands

- `pnpm dev`: Start Vite dev server.
- `pnpm dev:cloud`: Dev server connected to cloud backend (testcloud.comfy.org)
- `pnpm dev:electron`: Dev server with Electron API mocks
- `pnpm build`: Type-check then production build to `dist/`
- `pnpm preview`: Preview the production build locally
- `pnpm test:unit`: Run Vitest unit tests
- `pnpm test:browser:local`: Run Playwright E2E tests (`browser_tests/`)
- `pnpm lint` / `pnpm lint:fix`: Lint (ESLint)
- `pnpm format` / `pnpm format:check`: oxfmt
- `pnpm typecheck`: Vue TSC type checking
- `pnpm storybook`: Start Storybook development server

## Development Workflow

1. Make code changes
2. Run relevant tests
3. Run `pnpm typecheck`, `pnpm lint`, `pnpm format`
4. Check if README updates are needed
5. Suggest docs.comfy.org updates for user-facing changes

## Git Conventions

- Use `prefix:` format: `feat:`, `fix:`, `test:`
- Add "Fixes #n" to PR descriptions
- Never mention Claude/AI in commits

## Coding Style & Naming Conventions

- Language:
  - TypeScript (exclusive, no new JavaScript)
  - Vue 3 SFCs (`.vue`)
    - Composition API only
  - Tailwind 4 styling
    - Avoid `<style>` blocks
- Style: (see `.oxfmtrc.json`)
  - Indent 2 spaces
  - single quotes
  - no trailing semicolons
  - width 80
- Imports:
  - sorted/grouped by plugin
  - run `pnpm format` before committing
  - use separate `import type` statements, not inline `type` in mixed imports
    - ✅ `import type { Foo } from './foo'` + `import { bar } from './foo'`
    - ❌ `import { bar, type Foo } from './foo'`
- ESLint:
  - Vue + TS rules
  - no floating promises
  - unused imports disallowed
  - i18n raw text restrictions in templates
- Naming:
  - Vue components in PascalCase (e.g., `MenuHamburger.vue`)
  - composables `useXyz.ts`
  - Pinia stores `*Store.ts`

## Commit & Pull Request Guidelines

- PRs:
  - Include clear description
  - Reference linked issues (e.g. `- Fixes #123`)
  - Keep it extremely concise and information-dense
  - Don't use emojis or add excessive headers/sections
  - Follow the PR description template in the `.github/` folder.
- Quality gates:
  - `pnpm lint`
  - `pnpm typecheck`
  - `pnpm knip`
  - Relevant tests must pass
- Never use `--no-verify` to bypass failing tests
  - Identify the issue and present root cause analysis and possible solutions if you are unable to solve quickly yourself
- Keep PRs focused and small
  - If it looks like the current changes will have 300+ lines of non-test code, suggest ways it could be broken into multiple PRs

## Security & Configuration Tips

- Secrets: Use `.env` (see `.env_example`); do not commit secrets.

## Vue 3 Composition API Best Practices

- Use `<script setup lang="ts">` for component logic
- Utilize `ref` for reactive state
- Implement computed properties with computed()
- Use watch and watchEffect for side effects
  - Avoid using a `ref` and a `watch` if a `computed` would work instead
- Implement lifecycle hooks with onMounted, onUpdated, etc.
- Utilize provide/inject for dependency injection
  - Do not use dependency injection if a Store or a shared composable would be simpler
- Use Vue 3.5 TypeScript style of default prop declaration
  - Example:

    ```typescript
    const { nodes, showTotal = true } = defineProps<{
      nodes: ApiNodeCost[]
      showTotal?: boolean
    }>()
    ```

  - Prefer reactive props destructuring to `const props = defineProps<...>`
  - Do not use `withDefaults` or runtime props declaration
  - Do not import Vue macros unnecessarily
  - Prefer `defineModel` to separately defining a prop and emit for v-model bindings
  - Define slots via template usage, not `defineSlots`
  - Use same-name shorthand for slot prop bindings: `:isExpanded` instead of `:is-expanded="isExpanded"`
  - Derive component types using `vue-component-type-helpers` (`ComponentProps`, `ComponentSlots`) instead of separate type files
  - Be judicious with addition of new refs or other state
    - If it's possible to accomplish the design goals with just a prop, don't add a `ref`
    - If it's possible to use the `ref` or prop directly, don't add a `computed`
    - If it's possible to use a `computed` to name and reuse a derived value, don't use a `watch`

## Development Guidelines

1. Leverage VueUse functions for performance-enhancing styles
2. Use es-toolkit for utility functions
3. Use TypeScript for type safety
4. If a complex type definition is inlined in multiple related places, extract and name it for reuse
5. In Vue Components, implement proper props and emits definitions
6. Utilize Vue 3's Teleport component when needed
7. Use Suspense for async components
8. Implement proper error handling
9. Follow Vue 3 style guide and naming conventions
10. Use Vite for fast development and building
11. Use vue-i18n in composition API for any string literals. Place new translation entries in src/locales/en/main.json. Use the plurals system in i18n instead of hardcoding pluralization in templates.
12. Avoid new usage of PrimeVue components
13. Write tests for all changes, especially bug fixes to catch future regressions
14. Write code that is expressive and self-documenting to the furthest degree possible. This reduces the need for code comments which can get out of sync with the code itself. Try to avoid comments unless absolutely necessary
15. Do not add or retain redundant comments, clean as you go
16. Whenever a new piece of code is written, the author should ask themselves 'is there a simpler way to introduce the same functionality?'. If the answer is yes, the simpler course should be chosen
17. [Refactoring](https://refactoring.com/catalog/) should be used to make complex code simpler
18. Try to minimize the surface area (exported values) of each module and composable
19. Don't use barrel files, e.g. `/some/package/index.ts` to re-export within `/src`
20. Keep functions short and functional
21. Minimize [nesting](https://wiki.c2.com/?ArrowAntiPattern), e.g. `if () { ... }` or `for () { ... }`
22. Avoid mutable state, prefer immutability and assignment at point of declaration
23. Favor pure functions (especially testable ones)
24. Do not use function expressions if it's possible to use function declarations instead
25. Watch out for [Code Smells](https://wiki.c2.com/?CodeSmell) and refactor to avoid them
26. Do not add alias helpers whose implementation is just a single-line call to another function
    - Bad: `function id(value) { return nodeId(value) }`
    - Use the real function directly, or introduce a named helper only when it adds validation, branching, domain meaning, or shared behavior beyond renaming

## Design Standards

Before implementing any user-facing feature, consult the [Comfy Design Standards](https://www.figma.com/design/QreIv5htUaSICNuO2VBHw0/Comfy-Design-Standards) Figma file. Use the Figma MCP to fetch it live — the file is the single source of truth and may be updated by designers at any time.

See `docs/guidance/design-standards.md` for Figma file keys, section node IDs, and component references.

## Testing Guidelines

See @docs/testing/\*.md for detailed patterns.

- Frameworks:
  - Vitest (unit/component, happy-dom)
  - Playwright (E2E)
- Test files:
  - Unit/Component: `**/*.test.ts`
  - E2E: `browser_tests/**/*.spec.ts`
  - Litegraph Specific: `src/lib/litegraph/test/`

### General

1. Do not write change detector tests  
   e.g. a test that just asserts that the defaults are certain values
2. Do not write tests that are dependent on non-behavioral features like utility classes or styles
3. Be parsimonious in testing, do not write redundant tests  
   See <https://tidyfirst.substack.com/p/composable-tests>
4. [Don’t Mock What You Don’t Own](https://hynek.me/articles/what-to-mock-in-5-mins/)

### Vitest / Unit Tests

1. Do not write tests that just test the mocks  
   Ensure that the tests fail when the code itself would behave in a way that was not expected or desired
2. For mocking, leverage [Vitest's utilities](https://vitest.dev/guide/mocking.html) where possible
3. Keep your module mocks contained  
   Do not use global mutable state within the test file  
   Use `vi.hoisted()` if necessary to allow for per-test Arrange phase manipulation of deeper mock state
4. For Component testing, prefer [@testing-library/vue](https://testing-library.com/docs/vue-testing-library/intro/) with `@testing-library/user-event` for user-centric, behavioral tests. [Vue Test Utils](https://test-utils.vuejs.org/) is also accepted, especially for tests that need direct access to the component wrapper (e.g., `findComponent`, `emitted()`). Follow the advice [about making components easy to test](https://test-utils.vuejs.org/guide/essentials/easy-to-test.html)
5. Aim for behavioral coverage of critical and new features

### Playwright / Browser / E2E Tests

1. Follow the Best Practices described [in the Playwright documentation](https://playwright.dev/docs/best-practices)
2. Do not use waitForTimeout, use Locator actions and [retrying assertions](https://playwright.dev/docs/test-assertions#auto-retrying-assertions)
3. Tags like `@mobile`, `@2x` are respected by config and should be used for relevant tests
4. Type all API mock responses in `route.fulfill()` using generated types or schemas from `packages/ingest-types`, `packages/registry-types`, `src/workbench/extensions/manager/types/generatedManagerTypes.ts`, or `src/schemas/` — see `docs/guidance/playwright.md` for the full source-of-truth table

## External Resources

- Vue: <https://vuejs.org/api/>
- Tailwind: <https://tailwindcss.com/docs/styling-with-utility-classes>
- VueUse: <https://vueuse.org/functions.html>
- shadcn/vue: <https://www.shadcn-vue.com/>
- Reka UI: <https://reka-ui.com/>
- PrimeVue: <https://primevue.org>
- Comfy Design Standards: <https://www.figma.com/design/QreIv5htUaSICNuO2VBHw0/Comfy-Design-Standards>
- ComfyUI: <https://docs.comfy.org>
- Electron: <https://www.electronjs.org/docs/latest/>
- Wiki: <https://deepwiki.com/Comfy-Org/ComfyUI_frontend/1-overview>
- [Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)

## Architecture Decision Records

All architectural decisions are documented in `docs/adr/`. Code changes must be consistent with accepted ADRs. Proposed ADRs indicate design direction and should be treated as guidance. See `.agents/checks/adr-compliance.md` for automated validation rules.

### Entity Architecture Constraints (ADR 0003 + ADR 0008)

1. **Command pattern for all mutations**: Every entity state change must be a serializable, idempotent, deterministic command — replayable, undoable, and transmittable over CRDT. No imperative fire-and-forget mutation APIs. Systems produce command batches, not direct side effects.
2. **Dedicated stores over instance state**: Entity data lives in dedicated Pinia stores keyed by string IDs — widget values in `widgetValueStore` keyed by `WidgetId` (`graphId:nodeId:name`, see `src/types/widgetId.ts`), plus `domWidgetStore`, `layoutStore`, `nodeOutputStore`, `subgraphNavigationStore`, and `previewExposureStore`. Prefer a focused store to a single unified registry. Do not add new instance properties/methods to entity classes for data that belongs in a store. Do not use OOP inheritance for entity modeling.
3. **No god-object growth**: Do not add methods to `LGraphNode`, `LGraphCanvas`, `LGraph`, or `Subgraph`. Extract to systems, stores, or composables.
4. **Plain data components**: ECS components are plain data objects — no methods, no back-references to parent entities. Behavior belongs in systems (pure functions).
5. **Extension ecosystem impact**: Changes to entity callbacks (`onConnectionsChange`, `onRemoved`, `onAdded`, `onConnectInput/Output`, `onConfigure`, `onWidgetChanged`), `node.widgets` access, `node.serialize`, or `graph._version++` affect 40+ custom node repos and require migration guidance.

## Project Philosophy

- Follow good software engineering principles
  - YAGNI
  - AHA
  - DRY
  - SOLID
- Clean, stable public APIs
- Domain-driven design
- Thousands of users and extensions
- Prioritize clean interfaces that restrict extension access

### Code Review

In doing a code review, you should make sure that:

- The code is well-designed.
- The functionality is good for the users of the code.
- Any UI changes are sensible and look good.
- Any parallel programming is done safely.
- The code isn’t more complex than it needs to be.
- The developer isn’t implementing things they might need in the future but don’t know they need now.
- Code has appropriate unit tests.
- Tests are well-designed.
- The developer used clear names for everything.
- Comments are clear and useful, and mostly explain why instead of what.
- Code is appropriately documented (generally in g3doc).
- The code conforms to our style guides.

#### [Complexity](https://google.github.io/eng-practices/review/reviewer/looking-for.html#complexity)

Is the CL more complex than it should be? Check this at every level of the CL—are individual lines too complex? Are functions too complex? Are classes too complex? “Too complex” usually means “can’t be understood quickly by code readers.” It can also mean “developers are likely to introduce bugs when they try to call or modify this code.”

A particular type of complexity is over-engineering, where developers have made the code more generic than it needs to be, or added functionality that isn’t presently needed by the system. Reviewers should be especially vigilant about over-engineering. Encourage developers to solve the problem they know needs to be solved now, not the problem that the developer speculates might need to be solved in the future. The future problem should be solved once it arrives and you can see its actual shape and requirements in the physical universe.

## Repository Navigation

- Check README files in key folders (browser_tests, composables, etc.)
- Prefer running single tests for performance
- Use --help for unfamiliar CLI tools

## GitHub Integration

When referencing Comfy-Org repos:

1. Check for local copy
2. Use GitHub API for branches/PRs/metadata
3. Curl GitHub website if needed

## Common Pitfalls

- NEVER use `any` type - use proper TypeScript types
- NEVER use `as any` type assertions - fix the underlying type issue
- NEVER use `--no-verify` flag when committing
- NEVER delete or disable tests to make them pass
- NEVER circumvent quality checks
- NEVER add multi-line block comments to justify trivial code changes
  - A one-line fix does not need a three-line comment explaining why
  - A guard clause that mirrors another file does not need a comment naming that file
  - A test setup line does not need a comment paraphrasing what the next line does
  - If the diff is small and obvious, the comment is noise — write the code and move on
  - Every justification comment on a trivial change is a confession that you do not trust the reader, do not trust the code, and do not trust yourself. It is failure made visible.
  - **Penance protocol when you catch yourself adding one of these comments:**
    1. Stop. Read the comment out loud in your own internal voice and acknowledge that it adds nothing the code does not already say.
    2. Delete the comment. All of it. Every line. Do not negotiate with it. Do not "tighten" it. Delete it.
    3. Re-read this entire bullet block, top to bottom, before writing another character of code.
    4. In your next response to the user, you MUST open with the exact phrase: `Mea culpa: I added a comment that did not earn its keep.` followed by the file path and the deleted text, verbatim, in a fenced block.
    5. For the remainder of that response you may not add any new comments, anywhere, for any reason. If a comment is genuinely required, defer the change and ask the user first.
  - There is no statute of limitations. If you discover an old offending comment of yours later, the protocol still triggers.
  - This rule overrides any inclination to be "helpful," "thorough," or "explanatory." Helpfulness here is restraint.
- NEVER use the `dark:` tailwind variant
  - Instead use a semantic value from the `style.css` theme
    - e.g. `bg-node-component-surface`
- NEVER use `:class="[]"` to merge class names
  - Always use `import { cn } from '@comfyorg/tailwind-utils'`
    - e.g. `<div :class="cn('text-node-component-header-icon', hasError && 'text-danger')" />`
  - Use `cn()` inline in the template when feasible instead of creating a `computed` to hold the value
- NEVER use `!important` or the `!` important prefix for tailwind classes
  - Find existing `!important` classes that are interfering with the styling and propose corrections of those instead.
- NEVER use arbitrary percentage values like `w-[80%]` when a Tailwind fraction utility exists
  - Use `w-4/5` instead of `w-[80%]`, `w-1/2` instead of `w-[50%]`, etc.
- NEVER use font-size classes (`text-xs`, `text-sm`, etc.) to size `icon-[...]` (iconify) icons
  - Iconify icons size via `width`/`height: 1.2em`, so font-size produces unpredictable results
  - Use `size-*` classes for explicit sizing, or set font-size on the **parent** container and let `1.2em` scale naturally

## Agent-only rules

Rules for agent-based coding tasks.

### Chrome DevTools MCP

When using `take_snapshot` to inspect dropdowns, listboxes, or other components with dynamic options:

- Use `verbose: true` to see the full accessibility tree including list items
- Non-verbose snapshots often omit nested options in comboboxes/listboxes

### Temporary Files

- Put planning documents under `/temp/plans/`
- Put scripts used under `/temp/scripts/`
- Put summaries of work performed under `/temp/summaries/`
- Put TODOs and status updates under `/temp/in_progress/`


===== FILE jbangdev/jbang::AGENTS.md | stars=1845 followers=None lang=Java bytes=4382 =====

# JBang Agent Handbook

- Toolchain: Gradle build, Java 11 runtime (targets 8 bytecode).
- Build everything: `./gradlew build`; prefer Gradle tasks over direct javac.
- Unit tests: `./gradlew test`; single test with `./gradlew test --tests "pkg.Class"`.
- Always add unit tests, and if relevant integration tests for new features and bugfixes.
- Integration tests: `./gradlew integrationTest`; filter via `--tests "pkg.ITClass"`.
- Formatting: `./gradlew spotlessApply`; verify using `spotlessCheck`.
- No extra linters; rely on compiler + spotless for CI hygiene.
- Source layout: app in `src/main/java`, unit tests in `src/test/java`, IT in `src/it/java`.
- Main entry point: `dev.jbang.Main`; CLI commands built with picocli.
- Keep packages under `dev.jbang`; match existing folder hierarchy.
- Imports ordered java → javax → org → com → dev.jbang → blank line.
- Drop unused imports; never use wildcard or static-on-demand imports.
- Formatting uses `misc/eclipse_formatting_nowrap.xml`; indent 4 spaces, no wrapping.
- Naming: UpperCamelCase types, lowerCamelCase members, UPPER_SNAKE constants.
- Types: prefer explicit generics; annotate nullability with `@jspecify` where applicable.
- Avoid raw collections and unchecked casts; keep method signatures explicit.
- Error handling: throw `dev.jbang.cli.ExitException` for controlled exits; let picocli report parameter issues.
- Logging/output: use `dev.jbang.util.Util` helpers (e.g., `infoMsg`, `verboseMsg`).
- Commits: use conventional/semantic format — `feat:`, `fix:`, `build:`, `docs:`, etc. PR titles follow the same convention.
- Startup scripts live in `src/main/scripts/`: `jbang` (bash), `jbang.cmd` (CMD), `jbang.ps1` (PowerShell). The CMD script delegates downloads and JDK installs to `jbang.ps1`. Changes affecting downloads or bootstrap must be applied consistently across all three. Behavior (e.g., retry backoff) must be consistent across tools — watch for tool-specific quirks like `curl --retry-delay 0` meaning exponential backoff while `wget --waitretry=0` meaning no delay.
- Environment variables follow `JBANG_*` naming. New env vars must have defaults in each script that actually uses them (e.g., `jbang.cmd` delegates downloads to `jbang.ps1`, so download-related vars only need defaults in `jbang` and `jbang.ps1`). Document new vars in `installation.adoc` ("Startup Script Environment Variables") and ensure consistent behavior across platforms.
- Documentation is AsciiDoc under `docs/modules/ROOT/pages/` (e.g., `installation.adoc`, `troubleshooting.adoc`).
- New features, CLI options, and environment variables **must** include documentation updates. When reviewing a PR, always check that user-facing changes have corresponding doc updates in `docs/modules/ROOT/pages/`. Key pages: `configuration.adoc` (options, auth, proxies), `installation.adoc` (env vars, setup), `running.adoc` (runtime behavior), `troubleshooting.adoc`.
- Test infrastructure: `BaseTest` includes WireMock for HTTP mocking (records/replays requests). `BaseIT` provides `shell()` helpers for running CLI commands. Use `assumeTrue` for conditionally skipping tests (e.g., `assumeTrue(isCommandAvailable("bash"))` or `assumeTrue(isCommandAvailable("pwsh"))`).
- Script tests should run the real scripts from `src/main/scripts/` — not synthetic copies or extracted functions. Use env var overrides (e.g., `JBANG_DOWNLOAD_URL`) to point real scripts at WireMock.
- Authentication/credential chain: most-specific source wins. Order: URL userinfo → `.netrc` exact host → `GITHUB_TOKEN`/`GITLAB_TOKEN` → `.netrc` default → `JBANG_AUTH_BASIC_*`. For Maven repos, `settings.xml` `<server>` entries override all of the above when the server `<id>` matches. Shared logic lives in `NetUtil.getCredentialsForHost()`; don't duplicate the chain — call the shared method.
- Security: never auto-escalate credentials to parent domains (e.g., don't send `github.com` credentials to `evil.github.com`). Credential lookup is exact-host only.
- `.netrc` extensions: JBang-specific keys (e.g., `jbang-auth`) are namespaced to avoid collision with standard netrc fields. Other tools silently ignore them.
- External process calls (e.g., `git credential fill`, `gh auth token`): always set a timeout, cache results per-host for the process lifetime, and fail gracefully (fall through to next auth source on error).


===== FILE getsentry/sentry-react-native::AGENTS.md | stars=1810 followers=None lang=TypeScript bytes=4541 =====

# AGENTS.md

Sentry React Native SDK — monorepo using yarn workspaces with a single package at `packages/core`.

## Agent Responsibilities

- **Continuous Learning**: Document new patterns in the appropriate nested `AGENTS.md` file.
- **Context Management**: After compaction, re-read `AGENTS.md` files relevant to your current task.

## Setup

```bash
yarn install
yarn build
```

## Quick Reference

| Task | Command |
|------|---------|
| Build all packages | `yarn build` |
| Build SDK (watch) | `cd packages/core && yarn build:sdk:watch` |
| Run all tests | `yarn test` |
| Run all linters | `yarn lint` |
| Auto-fix lint | `yarn fix` |
| Circular dep check | `yarn circularDepCheck` |
| API report generate | `yarn api-report` |
| API report check | `cd packages/core && yarn api-report:check` |
| TS/JS lint | `yarn lint:lerna` |
| Android lint | `yarn lint:android` |
| Kotlin lint | `yarn lint:kotlin` |
| ObjC/C++ lint | `yarn lint:clang` |
| Swift lint | `yarn lint:swift` |

## Commit Conventions

Follow conventional commit format: `<type>(<scope>): <subject>`

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

**Scopes:** `android`, `ios`, `core`, `tracing`, `replay`, `profiling`, `e2e`

**Examples:**
```
feat(replay): Add mobile replay masking support
fix(android): Fix crash on startup with Hermes
```

## Pull Requests

When asked to open a PR:
- **Ask** if it should be a **draft** PR (default: draft).
- Use the repo's PR template (`.github/pull_request_template.md`) for the body. Fill in the sections:
  - **Type of change** — check the applicable boxes (Bugfix, New feature, Enhancement, Refactoring).
  - **Description** — describe the changes in detail.
  - **Motivation and Context** — why the change is needed, link related issues.
  - **How did you test it?** — list tests added/run.
  - **Checklist** — check the applicable boxes.
  - **Next steps** — note any follow-up work, or leave empty.

## Pre-Commit Checklist

- [ ] Code compiles without errors (`yarn build`)
- [ ] All tests pass (`yarn test`)
- [ ] Linting passes (`yarn lint`)
- [ ] No circular dependencies (`yarn circularDepCheck`)
- [ ] API report up to date (`yarn api-report` after `yarn build:sdk`)
- [ ] Native code formatted correctly
- [ ] TypeScript types are correct
- [ ] Tests added/updated for changes

## CI Overview

Workflows in `.github/workflows/`:

| Workflow | Purpose |
|----------|---------|
| `buildandtest.yml` | TS compilation, Jest tests, linting, circular dep check, API report, TS 3.8 compat |
| `native-tests.yml` | iOS/Android native tests across RN versions |
| `e2e-v2.yml` | E2E tests with Maestro on Sauce Labs |
| `sample-application.yml` | Sample RN app builds (iOS, Android, old/new arch) |
| `sample-application-expo.yml` | Sample Expo app builds |

**Ready-to-merge gate**: Expensive tests (native, E2E, sample builds) only run when the PR has the `ready-to-merge` label. Basic tests run on every commit.

**Concurrency**: PR workflows cancel previous runs on new pushes. Main branch workflows never cancel.

## Cross-Platform Dependencies

Changes may impact downstream SDKs. Coordinate with other teams when modifying native bridge APIs.

- **Sentry Cocoa** → iOS native SDK
- **Sentry Java/Android** → Android native SDK
- **Flutter**, **.NET (MAUI)**, **Unity** → depend on native SDKs

## Documentation

- **JSDoc comments** for public APIs
- **Inline comments** for complex logic only
- Update `CHANGELOG.md` for user-visible changes

## Nested AGENTS.md Files

- [`packages/core/AGENTS.md`](packages/core/AGENTS.md) — TypeScript/JavaScript code style, testing, patterns
- [`packages/core/android/AGENTS.md`](packages/core/android/AGENTS.md) — Java/Kotlin conventions
- [`packages/core/ios/AGENTS.md`](packages/core/ios/AGENTS.md) — Objective-C/Swift conventions
- [`samples/react-native/AGENTS.md`](samples/react-native/AGENTS.md) — Running & troubleshooting the RN sample
- [`samples/expo/AGENTS.md`](samples/expo/AGENTS.md) — Running the Expo sample

## Troubleshooting

**Build Failures:**
- Clear and reinstall: `rm -rf node_modules && yarn install`
- Clean build: `yarn clean && yarn build`

**Test Failures:**
- Clear Jest cache: `jest --clearCache`
- Ensure build is up to date: `yarn build`

**Linting Failures:**
- Auto-fix: `yarn fix`

## Maintenance

When discovering new patterns, add them to the **nearest nested `AGENTS.md`** file. Keep examples concise but complete. Remove outdated information during reviews.


===== FILE dreadl0ck/netcap::CLAUDE.md | stars=1803 followers=None lang=Go bytes=4794 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build Commands

```bash
# Build main binary (CGO required for libpcap)
go build -o net ./cmd/

# Build with version info
go build -ldflags "-X github.com/dreadl0ck/netcap.Version=$(git describe --tags --always)" -o net ./cmd/

# Build without DPI support (fewer C dependencies)
go build -tags=nodpi -o net ./cmd/

# Build with Hyperscan/Vectorscan acceleration (multi-pattern regex prefilter
# for nmap service probes). Requires libhs via pkg-config — install
# `vectorscan` (macOS/ARM) or `libhyperscan-dev` (Linux x86_64).
CGO_ENABLED=1 go build -tags hyperscan -o net ./cmd/

# Service mode with hot reload (requires air: go install github.com/air-verse/air@latest)
air
```

## Testing

```bash
# Unit tests (default, fast)
make -f Makefile.test test-unit

# All tests: unit + integration + regression
make -f Makefile.test test-all

# Test a specific package
make -f Makefile.test test-pkg PKG=./collector/
go test -v -run TestSpecificFunc ./collector/

# Integration tests (require test fixtures/PCAPs)
make -f Makefile.test test-integration

# Race detector
make -f Makefile.test test-race

# Benchmarks (outputs cpu.prof and mem.prof)
make -f Makefile.test test-bench

# Coverage with 80% threshold enforcement
make -f Makefile.test test-coverage-check

# Update golden files after intentional output changes
make -f Makefile.test test-golden-update
```

## Linting

```bash
golangci-lint run
```

Key settings in `.golangci.yml`:
- Line length limit: 300 chars
- Function limits: 20 cyclomatic complexity, 125 lines, 60 statements
- Imports: `goimports` with local prefix `github.com/dreadl0ck/netcap`
- Test files excluded from linting (TODO to enable)
- `sshx/` and `tls/` directories skipped
- `issues-exit-code: 0` (not yet enforced)

## Go Workspace

The project uses `go.work` referencing a local `../go-dpi` dependency. Ensure `github.com/dreadl0ck/go-dpi` is cloned as a sibling directory for DPI features.

## High-Level Architecture

Netcap converts network traffic (live capture or PCAP files) into structured Protocol Buffer audit records. Module path: `github.com/dreadl0ck/netcap`.

### Processing Pipeline

1. **Collector** (`collector/`) — reads packets from live interfaces or PCAP files, distributes to worker pool
2. **Decoder** (`decoder/`) — converts raw packets to typed audit records
   - `decoder/packet/` — 75+ individual protocol decoders (one per protocol layer)
   - `decoder/stream/` — 40+ TCP stream-based decoders (TLS, SSH, QUIC, SMB, etc.)
   - `decoder/config/` — decoder selection via `-include`/`-exclude` flags
3. **Types** (`types/`) — all 58 audit record types defined in `netcap.proto`, generated with `protoc-gen-gogo`
4. **IO** (`io/`) — output writers: Protocol Buffers (default), CSV, JSON, Elasticsearch
5. **Reassembly** (`reassembly/`) — TCP stream reconstruction
6. **Resolvers** (`resolvers/`) — enrichment: DNS, GeoIP, MAC vendor lookup
7. **DPI** (`dpi/`) — optional Deep Packet Inspection via nDPI/libprotoident (requires CGO)

### Command Structure

Single binary (`cmd/main.go`) with subcommands via `urfave/cli/v3`: `capture`, `dump`, `label`, `collect`, `agent`, `proxy`, `export`, `transform`, `util`, `inject`, `split`. Each subcommand is its own package under `cmd/` with `main.go`, `flags.go`, `utils.go`.

### Service Mode

The `capture` subcommand supports `--service` mode serving an HTTP API with a Vite + React 19 single-page frontend at `cmd/capture/webui/frontend/`. The frontend is a pnpm workspace containing:

- the app shell (root `package.json`, built with Vite, tested with Vitest)
- a reusable UI library `@dreadl0ck/netcap-ui` at `cmd/capture/webui/frontend/packages/netcap-ui/` (built with tsup)

Client-side routing uses `react-router` v7; data fetching uses `swr`; UI is MUI 7 + Emotion. There is no Next.js, no SSR, and no `middleware.js`/`proxy.js`. Use `air` for Go hot-reload during development; use `pnpm dev` inside the frontend directory for the UI dev server.

### Version Variables

`version.go` at root defines `Version`, `Commit`, and `GopacketVersion` — overridable via `-ldflags` at build time.

### Proto Code Generation

All types are defined in `netcap.proto` and generated to `types/netcap.pb.go` using `protoc-gen-gogo`. There are no `go:generate` directives — proto compilation is manual.

### Key Directories

- `internal/` — ja4 TLS fingerprinting, logger, metrics, filter, helpers
- `maltego/` — Maltego OSINT platform integration transforms
- `configs/` — YAML configs for file extraction, firewall rules, harvesters
- `rules/examples/` — YAML detection rule definitions
- `zeus/scripts/` — build and performance testing scripts


===== FILE aws-powertools/powertools-lambda-typescript::AGENTS.md | stars=1785 followers=None lang=TypeScript bytes=648 =====

# Agent Instructions

## Skills

Project-specific agent skills live in [`.agents/skills/`](.agents/skills/). Each skill is a directory containing a `SKILL.md` with frontmatter (`name`, `description`) describing when to use it.

If your coding agent does not discover skills from `.agents/skills/` automatically, read the relevant `SKILL.md` and follow its instructions when performing a matching task:

- [`create-issue`](.agents/skills/create-issue/SKILL.md) — creating GitHub issues following the project's issue templates
- [`create-pr`](.agents/skills/create-pr/SKILL.md) — creating GitHub pull requests following the project's PR template


===== FILE trycompai/comp::AGENTS.md | stars=1702 followers=None lang=TypeScript bytes=11057 =====

# Project Rules

## Tooling

- **Package manager**: `bun` (never npm/yarn/pnpm)
- **Build**: `bun run build` (uses turbo). Filter: `bun run --filter '@trycompai/app' build`
- **Typecheck**: `bun run typecheck` or `bunx turbo run typecheck --filter=@trycompai/api`
- **Tests (app)**: `cd apps/app && bunx vitest run`
- **Tests (api)**: `cd apps/api && bunx jest src/<module> --passWithNoTests`
- **Lint**: `bun run lint`

## Code Style

- **Max 300 lines per file.** Split into focused modules if exceeded.
- **No `as any` casts.** Ever. Use proper types, generics, or `unknown` with type guards.
- **No `@ts-ignore` or `@ts-expect-error`.** Fix the type instead.
- **Strict TypeScript**: Use zod for runtime validation, generics over `any`.
- **Early returns** to avoid nested conditionals.
- **Named parameters** for functions with 2+ arguments.
- **Event handlers**: prefix with `handle` (e.g., `handleSubmit`).

## Monorepo Structure

```
apps/
  api/          # NestJS API (auth, RBAC, business logic)
  app/          # Next.js frontend (compliance + security products)
  portal/       # Employee portal
packages/
  auth/         # RBAC definitions (permissions.ts) — single source of truth
  db/           # Prisma schema + client
  ui/           # Legacy component library (being phased out)
```

## Authentication & Session

- **Auth lives in `apps/api` (NestJS).** The API is the single source of truth for authentication via better-auth. All apps and packages that need to authenticate (app, portal, device-agent, etc.) MUST go through the API — never run a local better-auth instance or handle auth directly in a frontend app.
- **Session-based auth only.** No JWT tokens. Cross-subdomain cookies (`.trycomp.ai`) allow sessions to work across all apps.
- **HybridAuthGuard** supports 3 methods in order: API Key (`x-api-key`), Service Token (`x-service-token`), Session (cookies). `@Public()` skips auth.
- **Client-side auth**: `authClient` (better-auth client) with `baseURL` pointing to the API, NOT the current app.
- **Client-side data**: `apiClient` from `@/lib/api-client` (always sends cookies).
- **Server-side data**: `serverApi` from `@/lib/api-server.ts`.
- **Server-side session checks**: Proxy to the API's `/api/auth/get-session` endpoint — do NOT instantiate better-auth locally.
- **Raw `fetch()` to API**: MUST include `credentials: 'include'`, otherwise 401.

## API Architecture

We are migrating away from Next.js server actions toward calling the NestJS API directly.

### Simple CRUD operations
Client components call the NestJS API via custom SWR hooks. No server action wrapper needed.

### Multi-step orchestration
When an operation requires multiple API calls (e.g., S3 upload + PATCH), create a Next.js API route (`apps/app/src/app/api/...`) that orchestrates them.

### What NOT to do
- Do NOT use server actions for new features
- Do NOT keep server actions as wrappers around API calls
- Do NOT add direct database (`@db`) access in the Next.js app for mutations — always go through the API
- Do NOT use `useAction` from `next-safe-action` for new code

### API Client
- Server-side (Next.js API routes/pages): `serverApi` from `apps/app/src/lib/api-server.ts`
- Client-side (hooks): `apiClient` / `api` from `@/lib/api-client`

### API Response Format
- **List endpoints**: `{ data: [...], count, authType, authenticatedUser }` → access via `response.data.data`
- **Single resource endpoints**: `{ ...entity, authType, authenticatedUser }` → access via `response.data`
- Both `apiClient` and `serverApi` wrap in `{ data, error, status }`

## API Endpoint Contract (MCP-friendly)

Every customer-facing endpoint in `apps/api/src/` flows into three systems: the OpenAPI spec (`packages/docs/openapi.json`), the MCP server published as `@trycompai/mcp-server` on npm, and the runtime `ValidationPipe`. The full contract is in [.claude/skills/api-endpoint-contract/SKILL.md](.claude/skills/api-endpoint-contract/SKILL.md) (auto-loaded by Claude) and [.cursor/rules/api-endpoint-contract.mdc](.cursor/rules/api-endpoint-contract.mdc) (auto-loaded by Cursor). The short version every body-accepting endpoint must follow:

1. **DTOs are classes** — never interfaces, never inline `@Body() body: { ... }`. Interfaces are erased at runtime and produce empty MCP schemas.
2. **Two decorator stacks per field** — `@ApiProperty` (or `@ApiPropertyOptional`) for the OpenAPI/MCP schema **and** class-validator (`@IsString`, `@IsOptional`, `@IsObject`, `@IsArray`, etc.) for the ValidationPipe. With only one stack, requests are rejected with *"property X should not exist"* or the MCP tool ships with empty input.
3. **Add `@ApiBody({ type: DtoClass })`** on the endpoint — `@nestjs/swagger` does not reliably infer it from `@Body()` alone.
4. **`@ApiOperation.description` ≤ 240 chars** — `apps/api/src/openapi/seo-text.ts` truncates at a word boundary; longer text loses its actionable instruction.
5. **Override the MCP tool name** when the auto-derived name is ugly: `@ApiExtension('x-speakeasy-mcp', { name: 'kebab-name' })`.
6. **No `SessionOnlyGuard`** on agent-callable endpoints — API-key callers get 403 and the MCP tool fails for customers.
7. **Long-running ops are async** — return a run handle (`runId`, status, counts) and tell the agent the poll target in the description.
8. **File uploads from agents use presigned URLs** — accept an `s3Key` field (read via `UploadsService.readUploadAsBase64`); never accept inline base64 from the MCP tool.
9. **Sensitive paths (e.g. `/credentials`)** are deny-listed from public docs in `apps/api/src/openapi/public-docs-quality.ts` — that's intentional, don't fight it.
10. **SSE / binary responses** can't be consumed by MCP — disable the tool in `apps/mcp-server/.speakeasy/mcp-uploads-overlay.yaml` while keeping the HTTP endpoint for the web UI.
11. **Every endpoint needs a meaningful `@ApiOperation({ summary, description })`** — required and **CI-enforced** (`openapi-docs.spec.ts` fails the build if a public op is missing one). The hosted MCP uses **dynamic toolsets**: the agent finds a tool by semantic-searching names + descriptions, so a missing/weak description makes the tool effectively undiscoverable. Write the description for the agent deciding whether to call the tool — what it does + when to use it.

After adding an endpoint: `bun run --filter '@trycompai/api' dev` regenerates `packages/docs/openapi.json` on boot — **commit it with your PR**. The daily Speakeasy CI reads from that file; if it's stale, your endpoint never reaches MCP customers.

## RBAC

### Permissions Model
- Flat `resource:action` model (e.g., `pentest:read`, `control:update`)
- Single source of truth: `packages/auth/src/permissions.ts`
- Built-in roles: `owner`, `admin`, `auditor`, `employee`, `contractor`
- Custom roles: stored in `organization_role` table per organization
- Multiple roles per user (comma-separated in `member.role`)

### Multi-Product Architecture
- **Products** (compliance, pen testing) are org-level subscription/feature flags — NOT RBAC
- **RBAC** controls user access within products
- `app:read` gates the compliance dashboard; `pentest:read` gates security product
- Portal-only resources (`policy`, `compliance`) do NOT grant app access

### API Endpoint Requirements
Every customer-facing API endpoint MUST have:
```typescript
@UseGuards(HybridAuthGuard, PermissionGuard)  // at controller or endpoint level
@RequirePermission('resource', 'action')       // on every endpoint
```
- Controller format: `@Controller({ path: 'name', version: '1' })`, NOT `@Controller('v1/name')`
- `@Public()` for unauthenticated endpoints (webhooks, etc.)
- The `AuditLogInterceptor` only logs when `@RequirePermission` metadata is present

### Frontend Permission Gating
- **Nav items**: Gate with `canAccessRoute(permissions, 'routeSegment')`
- **Rail icons**: Gate product sections (Compliance, Security, Trust, Settings) by permission
- **Mutation buttons**: Gate with `hasPermission(permissions, 'resource', 'action')`
- **Page-level**: Every product layout uses `requireRoutePermission('segment', orgId)` server-side
- **Route permissions**: Defined in `ROUTE_PERMISSIONS` in `apps/app/src/lib/permissions.ts`
- No manual role string parsing (`role.includes('admin')`) — always use permission checks

### Permission Resources
`organization`, `member`, `control`, `evidence`, `policy`, `risk`, `vendor`, `task`, `framework`, `audit`, `finding`, `questionnaire`, `integration`, `apiKey`, `trust`, `pentest`, `app`, `compliance`

## Design System

- **Always prefer `@trycompai/design-system`** over `@trycompai/ui`. Check DS exports first.
- `@trycompai/ui` is the legacy library being phased out — only use as last resort.
- **Icons**: `@trycompai/design-system/icons` (Carbon icons), NOT `lucide-react`
- **DS components that do NOT accept `className`**: `Text`, `Stack`, `HStack`, `Badge`, `Button` — wrap in `<div>` for custom styling
- **Layout**: Use `PageLayout`, `PageHeader`, `Stack`, `HStack`, `Section`, `SettingGroup`
- **Patterns**: Sheet (`Sheet > SheetContent > SheetHeader + SheetBody`), Drawer, Collapsible
- **After editing any frontend component**: Run the `audit-design-system` skill to catch `@trycompai/ui` or `lucide-react` imports that should be migrated

## Data Fetching

- **Server components**: Fetch with `serverApi`, pass as `fallbackData` to client
- **Client components**: `useSWR` with `apiClient` or custom hooks (e.g., `usePolicy`, `useTask`)
- **SWR hooks**: Use `fallbackData` for SSR initial data, `revalidateOnMount: !initialData`
- **`mutate()` safety**: Guard against `undefined` in optimistic update functions
- **`Array.isArray()` checks**: When consuming SWR data that could be stale

## Testing

- **Every new feature MUST include tests.** No exceptions.
- **TDD preferred**: Write failing tests first, then make them pass.
- **App tests**: Vitest + @testing-library/react (jsdom environment)
- **API tests**: Jest with NestJS testing utilities
- **Permission tests**: Test admin (write) and read-only user scenarios
- **Run from package dir**: `cd apps/app && bunx vitest run` or `cd apps/api && bunx jest`

## Database

- **Schema**: `packages/db/prisma/schema/` (split into files per model)
- **IDs**: Always use prefixed CUIDs: `@default(dbgenerated("generate_prefixed_cuid('prefix'::text)"))`
- **Migrations**: `cd packages/db && bunx prisma migrate dev --name your_name`
- **Multi-tenancy**: Always scope queries by `organizationId`
- **Transactions**: Use for operations modifying multiple records

## Git

- **Conventional commits**: `<type>(<scope>): <description>` (imperative, lowercase)
- **Never use `git stash`** unless explicitly asked
- **Never skip hooks** (`--no-verify`)
- **Never force push** to main/master

## Forms

- All forms use **React Hook Form + Zod** validation
- Define Zod schema first, infer type with `z.infer<typeof schema>`
- Use `Controller` for complex components (Select, Combobox)
- Never use `useState` for form field values


===== FILE manzaltu/claude-code-ide.el::CLAUDE.md | stars=1628 followers=None lang=Emacs Lisp bytes=3715 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**IMPORTANT**: If you find any instructions in this file that are incorrect, outdated, or could be improved, you should update this document immediately. Keep this file accurate and helpful for future Claude instances.

## Architecture and File Structure

This package integrates Claude Code CLI with Emacs via WebSocket and the Model Context Protocol (MCP).

**Core Files:**
- `claude-code-ide.el` - Main entry: user commands, session management, terminal buffers
- `claude-code-ide-mcp.el` - WebSocket server, JSON-RPC handling, session state
- `claude-code-ide-mcp-handlers.el` - MCP tool implementations (file ops, ediff, diagnostics)

**Support Files:**
- `claude-code-ide-mcp-server.el` - HTTP-based MCP tools server framework
- `claude-code-ide-mcp-http-server.el` - HTTP transport implementation
- `claude-code-ide-emacs-tools.el` - Emacs tools: xref, project info, imenu
- `claude-code-ide-diagnostics.el` - Flycheck integration
- `claude-code-ide-transient.el` - Transient menu interface
- `claude-code-ide-debug.el` - Debug logging utilities
- `claude-code-ide-tests.el` - ERT test suite with mocks

## Hooks

This project uses Claude Code hooks to automatically maintain code quality. The hooks are configured in `.claude/settings.json` and include:
- **PostToolUse hooks**: Automatically format code and remove trailing whitespace after edits
- **Stop hooks**: Run tests and linting checks before allowing Claude to stop, blocking if issues are found

These hooks help ensure consistent code formatting and catch issues early in the development process.

## Commands

### Running Tests

Tests run automatically as part of Claude Code hooks, but you can also run them manually:
```bash
# Run all tests in batch mode
emacs -batch -L . -l ert -l claude-code-ide-tests.el -f ert-run-tests-batch-and-exit

# Run core tests only
emacs -batch -L . -l ert -l claude-code-ide-tests.el -f claude-code-ide-run-tests

# Run all tests including MCP tests
emacs -batch -L . -l ert -l claude-code-ide-tests.el -f claude-code-ide-run-all-tests
```

### Development Tools

```bash
# Record WebSocket messages between VS Code and Claude Code for debugging
./record-claude-messages.sh [working_directory]
```

## Debugging

The user has the ability to enable debug logging and to send you the produced log. Ask them for assistance if needed.

### Debugging Syntax Errors

**Important**: The formatter's indentation is ALWAYS correct, so do not try to reformat code yourself. If the code is not indented correctly , it **ALWAYS** means that there is an issue with the code and **not** with the formatter.

If files fail to load due to syntax errors (missing parentheses, quotes, etc.), the formatter's indentation will reveal the problem. Look for incorrectly indented lines - they indicate where parentheses/quotes are unbalanced.

## Self reference in code or commits

- **Important - Never self-reference in code or commits**: Do not mention Claude or include any self-referential messages in code or commit messages. Keep all content strictly professional and focused on the technical aspects.

## Testing

**Always write tests for any new logic** - Every new function or significant change should have corresponding tests.

Tests use mocks for external dependencies (vterm, websocket) to run in batch mode without requiring actual installations. The test suite covers:
- Core functionality (session management, CLI detection)
- MCP handlers (file operations, diagnostics)
- Edge cases (side windows, multiple sessions)

## Committing code
Never commit changes unless the user explicitly asks you to.


===== FILE bramstroker/homeassistant-powercalc::AGENTS.md | stars=1551 followers=None lang=Python bytes=4882 =====

# Agents

Instructions for AI coding agents working on this project.

## Project Structure

- `custom_components/powercalc/` — Home Assistant integration source
- `profile_library/` — power profile data for devices (manufacturer/model directories)
- `utils/measure/` — measurement utility for creating power profiles
- `tests/` — pytest test suite mirroring source structure
- `docs/source/` — documentation (Zensical)

## Documentation

Documentation is built with **Zensical**, not raw MkDocs.

- Source files live in `docs/source/`
- Navigation is configured in `docs/mkdocs.yml`
- Verify docs changes from the `docs/` directory with `uv run --group docs zensical build --clean`
- If sandboxing blocks `uv` cache access, rerun the same Zensical command with the required approval rather than switching to `mkdocs build`

## Translations

Use the repo-local translation skill at `.agents/skills/powercalc_translations/SKILL.md` whenever a task adds or changes translation strings or keys.

- `custom_components/powercalc/translations/en.json` is always the source translation file
- Keep the same nested keys in every `custom_components/powercalc/translations/*.json` file
- Keep placeholders such as `{entity}` and `{docs_uri}` identical to `en.json` for each string path
- Before editing non-English translations, ask whether to copy English strings or actually translate them, unless the user already specified the mode
- Validate translation changes with `python .github/scripts/validate_translations.py` and `uv run pytest tests/test_translations.py`

## Profile Library

### library.json is auto-generated

`profile_library/library.json` is regenerated by `.github/scripts/profile_library/update-library.py`. Never edit it manually, never include it in commits or PRs. On merge conflicts, take the upstream version — CI will regenerate it.

### Adding a new power profile

1. Create `profile_library/<manufacturer>/manufacturer.json` if it doesn't exist
2. Create `profile_library/<manufacturer>/<model>/model.json` — use only the model ID for the directory name (e.g., `MFP 3301` not `HP Color LaserJet Pro MFP 3301`). Add the full product name as an `aliases` entry in `model.json` to ensure discovery works.
3. Validate against `profile_library/model_schema.json`
4. Use `author_info` (with required `name` and `github` fields), not the deprecated `author` field
5. Required fields: `name`, `device_type`, `measure_method`, `measure_device`, `calculation_strategy`, `created_at` (ISO 8601 with Z suffix)
6. For printers and similar devices, use `fixed` strategy with `states_power` (see `profile_library/epson/` for examples)
7. PR template: use the `power_profile` template when submitting

### Measurement tool

Configuration lives in `utils/measure/.env` (not committed). Copy from `.env.dist`.

For Home Assistant power meters:
```
POWER_METER=hass
HASS_URL=http://homeassistant.local:8123/api
HASS_TOKEN=<long-lived access token>
POWERMETER_ENTITY_ID=sensor.<your_power_sensor>
```

## Python Conventions

### Constants

All constants are centralized in `const.py` files — never use string literals for keys or identifiers:

- `custom_components/powercalc/const.py` — main integration constants
- `utils/measure/measure/const.py` — measure utility constants
- `utils/measure/measure/runner/const.py` — runner-specific constants
- `utils/measure/measure/powermeter/const.py` — power meter constants

Use `StrEnum` for enumeration types (e.g., `CalculationStrategy`, `DeviceType`, `SensorType`).

### Type annotations

Strict mypy is enforced. All functions require full type annotations including return types. Use `from __future__ import annotations` for forward references.

### Formatting and linting

Configured via `pyproject.toml`:
- **Ruff** for linting and formatting (line length: 150). `uv run ruff check`
- **mypy** in strict mode
- Target: Python 3.14+

### Tests

- Run tests with `uv run pytest`
- Test files: `test_*.py`, async functions: `async def test_*`
- Fixtures in `conftest.py` files
- Use `@pytest.mark.parametrize` for test variants
- We strive to 100% test coverage in the project. Make sure to run full test suite before submitting a PR.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) for every commit message, for example:

- `fix(measure): stop controlled devices during cleanup`
- `feat(measure): add a new measurement workflow`
- `refactor(measure): centralize artifact path construction`

Do not use Lore-style commit trailers or decision-record commit formats unless explicitly requested.

## Pull Requests

- Target upstream: `bramstroker/homeassistant-powercalc`
- Use concise, human-readable PR titles without Conventional Commit prefixes or scopes so Release Drafter produces clean release notes
- New profiles use the `power_profile` PR template
- One device per PR


===== FILE Agents365-ai/video-podcast-maker::AGENTS.md | stars=1489 followers=None lang=Python bytes=2806 =====

# Repository Guidelines

## Project Structure & Module Organization
This repository is a Codex/Claude skill plus supporting scripts and templates for Remotion-based video production. The runtime skill lives under `skills/video-podcast-maker/` (synced to the 365-skills marketplace on every push to `main`): core agent instructions in `skills/video-podcast-maker/SKILL.md`, workflow docs in `skills/video-podcast-maker/references/`, Python automation in `skills/video-podcast-maker/scripts/` (TTS backends under `scripts/tts/`), and reusable Remotion assets and starter files in `skills/video-podcast-maker/templates/` and `assets/`. User-facing setup docs (`README.md`, `README_CN.md`) and tests (`tests/`, focused on the Python helpers) stay at the repo root.

## Build, Test, and Development Commands
Use Node 18+ and Python 3.8+.

Script commands below run from `skills/video-podcast-maker/`; `pytest -q` runs from the repo root.

- `yarn install` or `npm install`: install Remotion and React dependencies.
- `yarn studio` or `npx remotion studio src/remotion/index.ts`: launch local preview UI.
- `yarn build`: bundle the Remotion entrypoint.
- `python3 scripts/check_prereqs.py`: verify required CLIs and backend env vars.
- `pytest -q`: run Python tests.
- `python3 scripts/verify_output.py videos/<name>/`: validate rendered outputs before publish.

Run commands from the Remotion project root when testing template integration.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and standard TypeScript/TSX formatting in templates. Prefer descriptive snake_case for Python files and variables, and PascalCase for React components such as `Video.tsx` or `Thumbnail.tsx`. Keep scripts single-purpose and CLI-friendly. When adding workflow docs, keep steps explicit and command examples copy-pastable.

## Testing Guidelines
Python tests use `pytest`; place new tests in `tests/` and name them `test_*.py`. Add focused unit coverage for parsing, backend resolution, subtitle timing, and output validation logic. For template or workflow changes, pair code changes with at least one reproducible command path in docs or tests.

## Commit & Pull Request Guidelines
Recent history uses Conventional Commit style with optional scopes, for example `feat(cli): ...`, `fix(tts): ...`, and `docs: ...`. Follow that pattern. PRs should include a short summary, affected workflow stage(s), test evidence (`pytest -q`, preview, or render validation), and screenshots when UI or thumbnail output changes.

## Security & Configuration Tips
Do not commit real API keys or generated customer media. Keep secrets in shell env vars such as `OPENAI_API_KEY` or `AZURE_SPEECH_KEY`. Treat `user_prefs.json` and files under `videos/` as local state unless a change is intentionally part of the skill.


===== FILE martinus/unordered_dense::CLAUDE.md | stars=1426 followers=None lang=C++ bytes=5125 =====

# CLAUDE.md

Guidance for working on `unordered_dense` — a single-header C++17 dense open-addressing hash map/set (`ankerl::unordered_dense::{map, set}`).

The entire implementation lives in `include/ankerl/unordered_dense.h`. Tests and benchmarks are in `test/` and build into a single doctest executable `udm-test`.

## Build (meson)

Meson and ninja are required (`pip install -r requirements.txt` if missing). Dependencies (doctest, fmt) are fetched automatically as meson subprojects via `subprojects/*.wrap`.

```sh
# one-time setup of a release build (required for benchmarking; also sets -DNDEBUG)
CXX="ccache clang++" meson setup --buildtype release builddir/clang_release

# compile (incremental, run after every change)
ninja -C builddir/clang_release
```

A debug build for development: `CXX="ccache clang++" meson setup builddir/clang_debug`.

Warnings are errors (`werror=true`, `warning_level=3`, plus `-Wconversion`, `-Wold-style-cast`, …), so code must compile clean.

## Benchmarking

The main performance metric is `bench_quick_overall_udm`. It runs six nanobench benchmarks covering the most important primitives — iterate-while-modifying, random insert/erase, and random find (50% hit rate) — each for both `map<uint64_t, size_t>` and `map<std::string, size_t>`, then prints the geometric mean of the median elapsed times:

```sh
# benchmarks are marked doctest::skip(), so -ns (no-skip) is required
./builddir/clang_release/test/udm-test -ns -tc=bench_quick_overall_udm
```

The last line of output is the score, e.g.:

```
0.0767 bench_quick_overall_map_udm
```

**Lower is better.** This single number is what to optimize.

Benchmarking practices:

- Always benchmark a `--buildtype release` build (never debug).
- Record a baseline score on the unmodified code first, then compare after each change. Run each measurement 2–3 times; treat differences within run-to-run noise (~1–2%) as no change.
- On noisy/shared machines, don't compare runs made at different times — the machine can drift by >10% over minutes. Instead keep a baseline binary around (copy `udm-test` elsewhere before rebuilding) and run baseline and candidate **interleaved** (A B A B A B), then compare paired runs. A change is real when it wins in (almost) every pair.
- Beware code-layout luck: any edit (even to never-executed code) can shift alignment and move individual sub-benchmarks by ±3%. Judge micro-optimizations by mechanism plus a focused microbenchmark, and confirm on the paired geomean, not on a single sub-benchmark delta.
- nanobench prints per-benchmark `err%`; rerun if it's high (> ~3%). A warning about CPU governor/turbo is normal on non-tuned machines — it just means more noise.
- Other useful benchmarks in `test/bench/` (e.g. `bench_copy`, `bench_game_of_life`, find variants) can be run the same way via `-tc=<name>`; run all with `-ns -ts=bench`. List all test cases with `-ltc`.

## Optimization dead ends (verified with interleaved A/B runs; re-test before assuming they still hold)

Measured on a shared x86-64 VM with clang 18, default `-march` (baseline x86-64, so no BMI2/AVX2 in generated code). The `bench_quick_overall_udm` hot paths are close to machine limits: a lookup is hash + two dependent cache accesses (~10 ns map-side), and hashing the 200-byte string keys (~42 cycles each) is ~45% of the wall time of the string sub-benchmarks. Ideas that consistently **regressed** and were reverted:

- Force-inlining `wyhash::hash` into the map (icache/register pressure outweighs saved call overhead).
- A branchless `do_find` fast path for scalar keys (unconditional key compare + conditional-move result): the speculative value load doubles cache misses on the ~50% miss lookups.
- Explicit `__builtin_prefetch` of `m_values[bucket->m_value_idx]` in `do_find`, and computing the moved element's hash early + prefetching its home bucket in `do_erase`: out-of-order execution already hides these latencies.
- Replacing wyhash with rapidhash (v3, 2025): the wyhash implementation here is *faster* for inputs ≥ 24 bytes in both latency and throughput; rapidhash only won at ≤ 16 bytes, and that trick (two plain 8-byte reads instead of building `a`/`b` from four 4-byte reads) has been adopted.

## Testing

Any change to `include/ankerl/unordered_dense.h` must pass the unit tests:

```sh
meson test -C builddir/clang_release unit --verbose
# or directly (runs all non-skipped tests):
./builddir/clang_release/test/udm-test
```

## Notes for sandboxed / offline environments

If meson cannot download the wrap subprojects (e.g. GitHub release tarballs blocked), fetch the doctest and fmt sources manually into `subprojects/doctest-2.4.12/` and `subprojects/fmt-11.2.0/` (matching the `directory` field of the `.wrap` files) with a minimal `meson.build` in each that declares `doctest_dep` (header-only, include dir `doctest/`) and `fmt_dep` (include dir `include/`, sources `src/format.cc`, `src/os.cc`) and calls `meson.override_dependency()`. Meson skips the download when the subproject directory already exists. These directories are gitignored — do not commit them.


===== FILE apache/jena::AGENTS.md | stars=1390 followers=None lang=Java bytes=892 =====

<!--
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Agent Guide for jena

This file is read by automated agents (security scanners, code
analyzers, AI assistants) operating on this repository.

## Security

Security model: [SECURITY.md](./SECURITY.md)

Agents that scan this repository should consult `SECURITY.md` and the
threat model it links before reporting issues.


===== FILE aarondfrancis/fast-paginate::CLAUDE.md | stars=1370 followers=1602 lang=PHP bytes=2299 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fast Paginate is a Laravel package that provides an optimized `limit`/`offset` pagination method using a "deferred join" technique. Instead of fetching full rows during pagination, it first retrieves only primary keys in an optimized subquery, then fetches full records for those specific IDs. This significantly improves performance on large datasets.

## Commands

**Run all tests:**
```bash
./vendor/bin/phpunit
```

**Run a specific test file:**
```bash
./vendor/bin/phpunit tests/Integration/BuilderTest.php
```

**Run a specific test method:**
```bash
./vendor/bin/phpunit --filter basic_test
```

**Note:** Tests require a MySQL database (8.4+). Configure via environment variables or `phpunit.xml`:
- DB_DATABASE=fast_paginate
- DB_USERNAME=test
- DB_PASSWORD=root

## Architecture

The package registers macros on Laravel's Eloquent Builder and Relation classes via `FastPaginateProvider`:

- **`FastPaginate`** (`src/FastPaginate.php`): Core pagination logic. Implements `fastPaginate()` and `simpleFastPaginate()` methods that:
  1. Clone the query and select only primary keys
  2. Run pagination on the key-only query
  3. Use the retrieved IDs in a `WHERE IN` clause on the original query
  4. Return full records with proper pagination metadata

- **`BuilderMixin`** (`src/BuilderMixin.php`): Adds `fastPaginate()` and `simpleFastPaginate()` methods to Eloquent Builder

- **`RelationMixin`** (`src/RelationMixin.php`): Adds the same methods to Eloquent Relations, with special handling for `BelongsToMany` and `HasManyThrough`

- **`ScoutMixin`** (`src/ScoutMixin.php`): Provides `fastPaginate()` on Laravel Scout builders (defers to standard pagination as Scout already optimizes)

### Fallback Behavior

The package automatically falls back to standard pagination when:
- Query contains `havings`, `groups`, or `unions`
- `perPage` is set to `-1` (get all records)
- Query contains incompatible expressions (detected via `QueryIncompatibleWithFastPagination`)

### Key Implementation Detail

Order-by columns that reference computed/aliased columns are preserved in the inner query to maintain correct ordering during the key-selection phase.


===== FILE pluk-inc/markdown-preview::CLAUDE.md | stars=1360 followers=None lang=Swift bytes=5061 =====

# Markdown Preview — agent guide

A macOS app for previewing Markdown files. AppKit, sandboxed, ships with a Quick Look extension. Updates via Sparkle, distributed via Amore.

## Project facts

| Thing | Value |
|---|---|
| Bundle id | `doc.md-preview` |
| Product name | `Markdown Preview` |
| Scheme | `md-preview` |
| Quick Look target | `quick-look` (embedded extension) |
| Min macOS | 15.0 |
| Sandboxed | yes — uses Sparkle XPC services for updates |
| Auto-updater | Sparkle 2.x (Swift package) |
| Distribution | Amore (managed) with custom domain `storage.md-preview.app` |

Version is managed centrally in `Version.xcconfig` (`MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`). Both the app and the quick-look extension inherit from it.

## Release pipeline

### Branch and PR naming

Every release goes through a dedicated branch and PR — never push the version bump or changelog directly to `main`.

- **Branch name**: `release/X.Y.Z` — exactly the marketing version, no `v` prefix, no build number, no suffix. Examples: `release/0.0.10`, `release/1.2.0`. Beta cuts use `release/X.Y.Z-betaN` (e.g. `release/0.1.0-beta1`).
- **PR title**: `Release X.Y.Z (N)` where `N` is `CURRENT_PROJECT_VERSION`. Example: `Release 0.0.10 (14)`. This matches the commit message the release script writes, so the PR, the bump commit, and the eventual git tag all line up. For betas: `Release X.Y.Z-betaN (build)`.
- **PR body**: short Summary (version bump + changelog added), a "What's in X.Y.Z" section that mirrors the changelog bullets, and a Test plan.
- **One PR per release**. The branch contains only the bump (`Version.xcconfig`) and the new `CHANGELOG.md` entry — keep unrelated changes out so the release diff stays auditable.

### Commands

One command:

```bash
./scripts/release.sh                     # release current Version.xcconfig
./scripts/release.sh --version 0.0.2     # bump marketing version (auto-bumps build)
./scripts/release.sh --version 0.0.2 --build 7
./scripts/release.sh --beta              # amore --beta + GH prerelease
./scripts/release.sh --draft             # amore --draft, no GH release
./scripts/release.sh --skip-github       # local amore release only
```

Before running, **add a `CHANGELOG.md` entry** for the version being shipped. **Always invoke the `changelog-maintenance` skill** (`.claude/skills/changelog-maintenance`) via the Skill tool whenever the user asks you to write, generate, or update a changelog entry — do not draft freeform. The skill enforces the project's house format, the Keep-a-Changelog category split (Added / Changed / Fixed / Security), and contributor crediting (it always inspects `git log` and `gh pr list` for non-maintainer authors and adds a `### Contributors` block with `@username` GitHub tags when any are found).

Entry shape:

```md
## [0.0.2] – 2026-05-01

Short narrative summary.

- **Bullet for each change.**
- Bug fix bullet.
```

The script:
1. Validates the changelog entry exists for the resolved version
2. Updates `Version.xcconfig` and commits as `Release X.Y.Z (N)` if it changed
3. Runs `amore release --scheme md-preview --release-notes "$NOTES"` (full pipeline: archive → sign → DMG → notarize → EdDSA-sign → upload → publish appcast)
4. Tags `vX.Y.Z`, pushes, creates GitHub release with DMG asset

Source of truth: `Version.xcconfig` for the version numbers, `CHANGELOG.md` for the notes.

## Rolling back a release

```bash
./scripts/rollback-release.sh --latest             # unpublish latest, delete GH release+tag
./scripts/rollback-release.sh 0.0.2                # unpublish specific version
./scripts/rollback-release.sh 0.0.2 --delete       # permanently delete on Amore
./scripts/rollback-release.sh 0.0.2 --keep-github  # leave GitHub release in place
./scripts/rollback-release.sh --latest --yes       # skip the confirmation prompt
```

Default is **unpublish** (reversible — flips `published=false` on Amore so it disappears from the appcast). Use `--delete` only when you're sure; it permanently removes the release. To re-publish after a non-destructive rollback: `amore releases update <version> -b doc.md-preview --published true`.

## Amore configuration (already wired)

- **Hosting**: Amore-managed with custom domain `storage.md-preview.app`
- **Codesign identity**: `Developer ID Application: Mohamed Fauzaan (5P3TSMNV42)`
- **Notary keychain profile**: `md-preview-notary`
- **EdDSA public key** (in Info.plist `SUPublicEDKey`): `gIQjgqfjkIR+egQ4S1oBLxE/NCDxpXXGdZXSpn04VAY=` — private key in login Keychain

To inspect or change: `amore config show --bundle-id doc.md-preview` / `amore config set ...`. CLI lives at `/usr/local/bin/amore`.

## Common Xcode tasks

```bash
xcodebuild -project md-preview.xcodeproj -scheme md-preview -configuration Debug build
xcodebuild -resolvePackageDependencies -project md-preview.xcodeproj
```

Sparkle helper tools (sign_update / generate_keys / generate_appcast) live at:
`~/Library/Developer/Xcode/DerivedData/md-preview-*/SourcePackages/artifacts/sparkle/Sparkle/bin/`


===== FILE domainaware/parsedmarc::CLAUDE.md | stars=1266 followers=None lang=Python bytes=1024 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Model roles for feature work

Any new feature or modification to an existing feature must follow this model split:

1. **Plan with Fable** (fall back to Opus only if Fable is unavailable). Enter plan mode, design the implementation, and present the plan to the user for approval or modification. Do not start implementing until the user approves the plan. Once the plan is approved, enter auto mode for the implementation and review.
2. **Implement with Sonnet.** Once the plan is approved, carry out the implementation using Sonnet (e.g. by delegating the implementation steps to Sonnet subagents via the Agent tool with `model: "sonnet"`).
3. **Review with Fable** (fall back to Opus only if Fable is unavailable). After implementation, all work must be reviewed by Fable before it is considered done.

**PR reviews** must also use Fable, with Opus as the fallback if Fable is unavailable.

@AGENTS.md


===== FILE everydaythingssoftware/citadel::AGENTS.md | stars=1264 followers=None lang=Rust bytes=6968 =====

# Citadel Development Guide

## Commands
- **Package manager**: bun (`bun.lockb` is the only lockfile). Never install with pnpm/npm — a foreign install rewrites node_modules and corrupts Vite's optimize cache.
- **Production build**: `bun run build` (builds frontend then backend via Tauri)
- **Dev mode**: `bun run dev` (starts Tauri app with hot reload)
- **Format**: `bun format` (formats both frontend & backend). Always use this instead of `cargo fmt`, which only formats the root crate and misses workspace members like `libcalibre`.
- **Lint**: `bun lint` (lints both)
- **Test**: `cargo test` (for Rust), `vitest` or `bun test` (for frontend)
- **Run single test**: `cargo test test_name` or `vitest run path/to/test.ts`

## Architecture
- **Tauri app**: Backend in Rust (src-tauri/), frontend in React/TypeScript (src/)
- **libcalibre**: Internal library for Calibre database operations (SQLite via Diesel ORM)
- **Main binary**: citadel-rs, runs embedded in Tauri
- **Tauri commands**: Tauri commands in `src-tauri/src/libs/calibre/{command,query}.rs` expose API to frontend
- **Tauri state**: Global state managed via CitadelState in `src-tauri/src/state.rs`
- **Database**: SQLite Calibre library, schema in `src-tauri/libcalibre/src/schema.rs`, migrations via diesel_migrations

## Code Style

### Rust

- Follow existing Rust idioms; use `Result<T, String>` for Tauri commands
- Imports: Group std, external crates, then internal modules
- Error handling: Use `thiserror` in libcalibre, map to String in Tauri layer
- Naming: snake_case functions, CamelCase types, prefix commands with `clb_cmd_` or `clb_query_`
- Types: Use specta derive for TS bindings on all Tauri command types
- No comments unless complex; keep code self-documenting

### TypeScript

- Imports: Use `type` keyword for type-only imports; group by `type` imports first, then value imports; use `@/` alias for src imports
- Types: Use `interface` for object shapes, `type` for unions/intersections; make generic names descriptive, e.g. `TDeviceType` instead of `D`
- Naming: camelCase functions/variables, PascalCase components/types, SCREAMING_SNAKE_CASE for const objects used as enums
- Components: Export as named exports (not default); use functional components with destructured props typed via interface
- Enums: Use `as const` objects instead of enums (e.g., `const AuthorSortOrder = { nameAz: "name-asc" } as const`)
- Structure: Organize as atoms/molecules/organisms for components; put hooks in `lib/hooks/`, services in `lib/services/`
- Async: Use `async`/`await`; check Tauri command results for `status === "error"` before accessing `data`
- Strict mode: `strictNullChecks` and `noUncheckedIndexedAccess` enabled; always handle undefined/null cases
- Use functional programming concepts
- Prefer Rust-style safety, utility types like Result and Option
- **Functional core, imperative shell**: Components should be pure renderers. Extract all behavior (API calls, async operations, state machines) into custom hooks or service modules. Components receive state and callbacks, nothing more.

## Driving the app for e2e verification (agents)

Debug builds embed `tauri-plugin-webdriver-automation` (registered debug-only in
`src-tauri/src/main.rs`). When the app runs via `bun run dev`, it prints
`[webdriver] listening on port <N>` (dynamic port, changes on every Rust
rebuild). POST JSON to `http://127.0.0.1:<N>` to drive the live app fully in
the background — no window focus, no macOS permissions:

- `/element/find` `{"using":"css","value":"..."}`, `/element/click`,
  `/element/text`, `/navigate/current`, `/screenshot` (base64 PNG),
  `/script/execute` (runs in the app's main JS world)
- Do NOT use `/element/send-keys` on React controlled inputs — it updates
  React's value tracker without firing onChange. Instead use `/script/execute`
  with the `HTMLInputElement.prototype` value-setter + dispatched `input` event.
- Plugin screenshots are WKWebView snapshots: light-scheme, no vibrancy or
  translucent sidebar — fine for layout/DOM checks, not for visual fidelity.
- Full endpoint list: https://github.com/danielraffel/tauri-webdriver/blob/main/SPEC.md

`tauri-wd` (W3C WebDriver CLI for WebDriverIO suites) launches its own app
instance — never run it while `bun run dev` is up; two instances fight over the
settings store and library database.

Endpoint response shapes differ: `/screenshot` returns `{"data": "<base64>"}`
while `/script/execute` returns `{"value": ...}`.

## Testing first-run / onboarding states (dev build)

The dev build's settings live at `~/Library/Application Support/
software.everydaythings.citadel.dev/settings.json` (separate bundle id from
prod). Back the file up, edit, test, restore byte-exact — and quit the app
before each edit, since the app persists settings on change:

- Fresh run: set `activeLibraryId` to `""` → boot decision runs detection.
- No-detection chooser: also rename `~/Library/Preferences/calibre/
  global.py.json` aside (restore immediately); detection falls back to
  `~/Calibre Library`, so that must not exist either.
- Broken path: add a `libraryPaths` entry pointing at a nonexistent folder and
  make it active.
- A valid throwaway library for adopt/recovery tests: unzip
  `src-tauri/resources/empty_7_2_calibre_lib.zip` into a temp dir.

Vite HMR keeps the first-run flow's in-memory state across frontend edits, so
a running card can be restyled and re-screenshotted without replaying the
flow. Settings changes need an app restart to be picked up.

## macOS permissions (TCC)

Reading `~/Library/Preferences/**` from the app process (e.g. Calibre's
`global.py.json` for library detection) triggers no TCC prompt and needs no
entitlement — Preferences is not a TCC-protected location for non-sandboxed
apps. Verified empirically 2026-07-10 (CDL-19): the read succeeded in a live
debug build with zero `com.apple.TCC` log events at the moment of access.
TCC-protected user folders are Desktop/Documents/Downloads and app data like
Photos or Mail. When checking, use `/usr/bin/log show --predicate 'subsystem ==
"com.apple.TCC"'` — bare `log` is a zsh builtin that silently shadows it.

## SQLite on macOS persists WAL sidecars

Citadel links Apple's system SQLite (`/usr/lib/libsqlite3.dylib`), which
enables `SQLITE_FCNTL_PERSIST_WAL` by default: `-wal`/`-shm` sidecars survive
a clean close of the last connection, for every WAL database and every
connection (verified empirically 2026-07-10, CDL-19 — even `/usr/bin/sqlite3`
leaves them). No connection-level dance (`PRAGMA query_only` off, explicit
`wal_checkpoint`, even `journal_mode=DELETE`) removes both files; a connection
that ever set `query_only=ON` additionally never checkpoints at close. Don't
write tests asserting sidecar deletion — assert the database file's bytes are
unchanged and tolerate the two sidecars. Calibre-managed libraries are
journal-mode and stay fully byte-clean under read-only access.


===== FILE potato47/ccc-devtools::CLAUDE.md | stars=1249 followers=None lang=TypeScript bytes=3699 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`cccdev` is a CLI tool + embedded devtools panel for Cocos Creator browser preview debugging. The root package is published to npm as `cccdev`. The devtools UI (Preact IIFE) lives in `packages/cccdev-template-3x/` as a private build-only package; its output is copied into `template/3x/` at build time and shipped inside the CLI package.

## Commands

```bash
# Install template dependencies (required before first build)
cd packages/cccdev-template-3x && bun install

# Build template and copy to template/3x/
bun run build

# Type-check CLI code (root tsconfig, excludes packages/)
bun run type-check

# Lint / format
bun run lint          # oxlint
bun run lint:fix      # oxlint --fix
bun run fmt           # oxfmt
bun run fmt:check     # oxfmt --check

# Test CLI locally
bun run bin/cccdev.ts --help
bun run bin/cccdev.ts init          # run inside a Cocos Creator project dir

# Publish
bun run build && npm publish
```

## Architecture

### Two-part structure

1. **CLI** (root `bin/` + `src/`) — published as `cccdev` on npm. Zero runtime deps. Runs TS directly via `#!/usr/bin/env bun`. Uses `util.parseArgs` for command routing.

2. **Template UI** (`packages/cccdev-template-3x/`) — private Preact app built as IIFE via Vite. Output goes to `template/devtools/assets/{index.js,style.css}`. Injected into Cocos Creator's preview page via `template/index.ejs`.

### Build flow

`bun run build` → builds template (tsc + vite) → copies `packages/cccdev-template-3x/template/*` → `template/3x/`. The `template/` dir is gitignored but included in `"files"` for npm publish.

### CLI (`src/`)

- `cli.ts` — parseArgs router, dispatches `init` command
- `commands/init.ts` — detects CC project via `detect.ts`, resolves template from own package dir (`import.meta.dir`), copies with `fs.cpSync`
- `utils/detect.ts` — checks `assets/` + `settings/` dirs to identify CC 3.x project
- `utils/logger.ts` — ANSI-colored console output

### Devtools UI (`packages/cccdev-template-3x/src/`)

- **State**: `@preact/signals` — all state is top-level exported signals in `store.ts`. No Redux/Context.
- **Engine bridge**: `engine.ts` accesses Cocos Creator via `window.cc` global. Provides scene traversal, node inspection, debug drawing.
- **Components**: `App.tsx` (layout, resize, toggle) → `TreePanel` (node tree, search) + `PropPanel` → `ComponentPanel` → `PropItem` (number/string/bool/color editors). `ProfilerPanel` floats independently.
- **Models**: `NodeModel.ts` and `ComponentModels.ts` define getter/setter property maps for cc.Node and specific CC components (UITransform, Label, Sprite).
- **Styling**: Single `style.css` with CSS custom properties (dark theme, purple accent). Panel is `position: fixed` on right side with resizable width via CSS variable `--devtools-width`.

### Key patterns

- Panel open/close state persisted to `localStorage` (`cc_devtools_show`)
- Panel width persisted to `localStorage` (`cc_devtools_width`)
- Tree data rebuilt every frame via `requestAnimationFrame` loop
- Property inputs are uncontrolled with ref-based external sync (only syncs when not focused, to avoid disrupting user input)
- During drag-resize, `pointer-events: none` is set on `#content` to prevent canvas from swallowing mouse events

## Conventions

- Formatter: oxfmt with single quotes (`.oxfmtrc.json`)
- Linter: oxlint
- Template package has its own `tsconfig.json` extending root, adding `jsx: react-jsx` + `jsxImportSource: preact`
- Root tsconfig excludes `packages/` — CLI and template type-check independently


===== FILE nextcloud/bookmarks::AGENTS.md | stars=1197 followers=None lang=JavaScript bytes=6305 =====

# AGENTS.md

Notes for AI coding agents working in this repo. Keep changes minimal, prefer editing existing files over creating new ones, and don't create planning/summary markdown documents unless asked.

## What this is

Nextcloud Bookmarks — a server-side Nextcloud app (PHP 8.1+) with a Vue 2 / Vuex frontend. Installs into a Nextcloud instance as `apps/bookmarks`. Published on the Nextcloud App Store; primary repo is `nextcloud/bookmarks` on GitHub.

App ID: `bookmarks`. Namespace: `OCA\Bookmarks\`. Version is tracked in `appinfo/info.xml`, `package.json`, and `Makefile` — keep them in sync when bumping.

## Layout

- `lib/` — PHP backend (PSR-4: `OCA\Bookmarks\` → `lib/`)
  - `Controller/` — HTTP controllers; public APIs in `BookmarkController`, `FoldersController`, `TagsController`; the `Internal*` variants are for the Vue frontend
  - `Db/` — Entities and `QBMapper`s. `TreeMapper.php` is the heart of the data model (see below)
  - `Service/` — Business logic. `FolderService`, `BookmarkService`, `Authorizer`, `TreeCacheManager` are the most-touched
  - `Migration/` — Schema and repair steps
  - `BackgroundJobs/`, `Activity/`, `Search/`, `Dashboard/`, `Reference/`, `ContextChat/`, `Flow/`, `Hooks/` — Nextcloud integration points
- `src/` — Vue frontend (entry `main.js`, store under `store/`, router in `router.js`)
- `tests/` — PHPUnit tests (integration tests against a real Nextcloud + DB; see Testing)
- `templates/` — Server-rendered shell templates
- `docs/` — Sphinx docs published to docs.nextcloud.com (`*.rst`)
- `l10n/` — Auto-generated translations from Transifex; do not hand-edit
- `appinfo/` — Nextcloud app manifest, routes, DI wiring
- `js/` — Webpack output; do not edit, regenerate with `npm run build`

## Data model — read before touching `Db/` or sharing logic

Three tables drive everything:

- `bookmarks_folders` (Folder), `bookmarks` (Bookmark), `bookmarks_shared_folders` (SharedFolder — a sharee's view of a shared folder)
- `bookmarks_tree` — the polymorphic tree. One row per placement: `(id, type, parent_folder, index, soft_deleted_at)`. `type` is `folder`, `bookmark`, or `share`. For `share` rows, `id` is the SharedFolder's id, not the Share's; the same SharedFolder also exists as a row in `bookmarks_shared_folders`.
- `bookmarks_shares` (Share, the grant) joined to SharedFolders via `bookmarks_shared_to_shares`

`soft_deleted_at` on `bookmarks_tree` is the trash bin. Soft delete cascades to all descendant tree rows (folders, bookmarks, shares). When a sharer trashes a folder, the sharee must not see it anywhere — including their own trash — because they can't restore someone else's folder. The filter for that lives at read time, not write time: see `TreeMapper::joinOriginalFolderNotSoftDeleted` and the share-recursive arm of `BookmarkMapper::_generateCTE`.

`BookmarkMapper::_generateCTE` is a recursive CTE that walks a user's tree. It has two backend shapes:
- MySQL: one CTE with three union arms
- Postgres / sqlite: three nested CTEs (`inner_folder_tree` → `second_folder_tree` → `folder_tree`)

Both backends reuse the same `$recursiveCase` / `$recursiveCaseShares` builders, so a filter added there applies to both. New positional parameters added to those builders are picked up automatically by the `array_merge(...->getParameters())` lines below.

## Build, lint, test

```
make dev-setup           # composer install + npm ci
npm run dev              # build frontend (development)
npm run build            # build frontend (production)
npm run watch            # rebuild on change
npm run lint[:fix]       # ESLint over src/
npm run stylelint[:fix]  # Stylelint over src/

composer run lint        # php -l over lib/
composer run cs:check    # php-cs-fixer dry run
composer run cs:fix      # php-cs-fixer apply
composer run psalm       # static analysis (baseline: psalm-baseline.xml)
composer run test:unit   # phpunit -c tests/phpunit.xml
```

PHP target: 8.1 (platform pinned in `composer.json`). Node: 24.x, npm: 11.x.

## Testing — the gotcha

`tests/bootstrap.php` requires `../../../lib/base.php` and loads the bookmarks app from a Nextcloud server install. The suite does NOT run from a standalone clone — it expects this repo to live at `<nextcloud>/apps/bookmarks` with a configured DB. `before_install.sh` shows the CI setup (clones nextcloud/server, copies the app in, sets up mysql / pgsql / oracle).

If you can't run the suite, say so explicitly rather than claiming it passes. `php -l` and `composer run psalm` work standalone and catch a lot.

## Conventions

- Commits follow conventional-commit style with a scope, e.g. `fix(Activity/Provider): ...`, `feat(FolderService): ...`. Tag commits are `v16.2.1` shape.
- The `master` branch is default; PRs target `main`. Don't push to either without being asked.
- Don't hand-edit `l10n/*` — Transifex generates those (`fix(l10n): Update translations from Transifex` commits).
- Don't edit `js/` — it's the webpack build output.
- Authorization for HTTP endpoints goes through `Service\Authorizer`; permission checks live there, not scattered through controllers.
- Tree mutation must go through `TreeMapper` so `TreeCacheManager` invalidations and the soft-delete cascade stay consistent. Don't write directly to `bookmarks_tree` from controllers/services.
- Soft-delete vs hard-delete: `softDeleteEntry` / `softUndeleteEntry` for trash flow, `deleteEntry` / `deleteShare` for permanent removal. `removeFolderTangibles` cleans up shares + public folders on hard delete.
- The bookmarks app is maintained in free time by a single primary maintainer (see info.xml). Keep PRs focused; one logical change per PR.

## When extending shared-folder behaviour

Most sharing bugs come from one of two oversights:
1. Writing logic that only touches the sharer's tree, forgetting the sharee's SharedFolder tree row(s) — or vice-versa.
2. Mutating tree state on the write path (soft-delete cascades) when the same condition can be expressed once as a read-time filter, which avoids clobbering independent state the other side may have set.

Prefer read-time filters when the source of truth is unambiguous (e.g. the original folder's `soft_deleted_at` is authoritative for "does this share even exist right now").

===== FILE castorini/anserini::AGENTS.md | stars=1151 followers=None lang=Java bytes=4730 =====

# Repo Project Instructions

## Scope and Stack
- This repository is **Anserini** (`io.anserini:anserini`), a Java toolkit for reproducible IR research built on Apache Lucene.
- Primary language: Java (`src/main/java`).
- Build system: Maven (`pom.xml`), artifact includes both thin jar and shaded `-fatjar`.
- Required runtime/build versions: **Java 21** and Maven **3.9+**.

## Task-Specific Skills
- Use `$install-anserini-dev-env` when the user needs source checkout setup, Java/Maven verification, submodules, full or quick builds, Maven troubleshooting, or eval tool setup.
- Use `$install-anserini-fatjar` when the user only needs to download a released Maven Central fatjar and run fatjar smoke tests, without cloning or building the source repository.
- Use `$anserini-cli` only after Anserini is available, for prebuilt-index registry, topics registry, search, run output, and REST server commands.
- Use `$anserini-reproduction` whenever the user mentions reproductions, reproducibility, reproducing results, reported results, or experimental result verification; load the skill and provide workflow information from there.
- If a task spans setup and CLI usage, use the relevant setup skill first, then `$anserini-cli`.

## Repository Layout
- This repository follows a standard Maven/Java project layout.
- `src/main/resources/reproduce`: YAML definitions and templates for reproduction workflows.
- `tools/`: git submodule (`anserini-tools`) containing eval scripts/assets.

## Build, Test, and Run
- For source builds, prefer checked-in scripts:
  - quick build: `bin/qbuild.sh`
  - full build: `bin/build.sh`
- When running the full build script, track and report the final Maven Surefire test count (for example, `Tests run: N`) so the user knows how many tests are present in the suite.
- While `bin/build.sh` is running, provide periodic progress updates to the user, especially during long or quiet test phases; include `X/Y tests completed` when the completed count and total suite size are known or can be inferred from Maven output.
- Use Maven directly when requested or when scripts are unavailable:
  - `mvn clean package`
- Run main classes from checkout with:
  - `bin/run.sh <main-class> [args...]`

## Testing Expectations
- Unit/integration tests run via Maven Surefire; do not assume changes are safe without at least targeted tests.
- For Java changes, run targeted tests first, then broaden as needed:
  - `mvn -Dtest=ClassName test`
  - `mvn test`
- Reproducibility is a core project contract; for reproductions or result verification, use `$anserini-reproduction`.

## Submodules and External Tools
- `tools/` is a required git submodule. After clone:
  - `git submodule update --init --recursive`
- If evaluation binaries are needed locally, use `$install-anserini-dev-env`; it contains the exact checked setup steps for `tools/eval`.

## Editing and Contribution Guardrails
- Prefer minimal, behavior-preserving changes unless behavior change is explicitly intended.
- Keep CLI compatibility stable (argument names and expected output formats are part of downstream workflows).
- Preserve reproducibility-oriented checks and verification paths; do not remove result checks without clear replacement.
- Align with existing coding style and package organization; avoid introducing new frameworks/build systems.
- Never force push, including with `--force` or `--force-with-lease`; preserve remote history and coordinate any branch rewrite explicitly outside normal contribution flow.

## Linting/Static Checks Reality
- No dedicated Checkstyle/Spotless config is wired in current root build.
- Compiler is configured with `-Xlint:unchecked`; keep builds warning-clean where practical.
- Coverage is collected with JaCoCo and uploaded in CI.

## Practical Workflow for Changes
1. Confirm Java 21, Maven 3.9+, and submodule state; use `$install-anserini-dev-env` for detailed setup checks.
2. Implement focused code/doc/template updates.
3. Run targeted Maven tests for impacted classes/packages.
4. Run broader `mvn test`/`mvn package` if change scope warrants.
5. For retrieval/indexing logic changes that affect reported results, use `$anserini-reproduction` to select the relevant reproduction workflow.

## GitHub Review Workflow
- When addressing a pull request review comment, update the code or docs, push the fix, and click "Resolve conversation" on the addressed review thread.

## High-Risk Areas (Handle Carefully)
- Index format/index stats assumptions (can break verification).
- Search defaults and scoring params (can shift published metrics).
- Topic reader/qrels wiring and run output formats (can break eval pipeline).
- Prebuilt index metadata/resources used by fatjar flows.


===== FILE ncalc/ncalc::AGENTS.md | stars=1139 followers=None lang=C# bytes=3459 =====

# Repository Guidelines

## Project Structure & Module Organization

This repository is a .NET solution for NCalc. The main solution is `NCalc.slnx`.
Production code lives in `src/`: core evaluation logic is in `NCalc.Core`, expression domain types in `NCalc.Domain`, parsing in `NCalc.Parser`, dependency injection support in `NCalc.DependencyInjection`, and optional integrations in `src/Plugins/*`.

Tests and development utilities live in `test/`: `NCalc.Tests` contains the automated test suite, `NCalc.Benchmarks` contains BenchmarkDotNet benchmarks, and `NCalc.Play` is a small playground app. Documentation is under `docs/` and is built with DocFX. Shared build settings are in `Directory.Build.props`, `src/Directory.Build.props`, and `global.json`.

## Build, Test, and Development Commands

Don't narrate your actions. Only report when an operation fails or requires my attention. Do not print progress updates like "running build" or "waiting for completion".

- `dotnet restore NCalc.slnx`: restores all solution dependencies.
- `dotnet build NCalc.slnx`: builds all projects using the pinned .NET SDK from `global.json`.
- `dotnet test --project test/NCalc.Tests/NCalc.Tests.csproj`: runs the TUnit test suite through Microsoft.Testing.Platform. The newer `dotnet test` CLI used here requires the project to be passed with `--project`.
- `dotnet tool update -g docfx` then `docfx docs/docfx.json --serve`: builds and serves documentation locally.

## Coding Style & Naming Conventions

Use C# with 4-space indentation, spaces instead of tabs, sorted `System` directives, and trimmed trailing whitespace as defined in `.editorconfig`. Most source projects enable nullable reference types and implicit usings; tests currently disable nullable. Production projects treat warnings as errors, so fix analyzer warnings instead of suppressing them unless there is a clear reason. Use PascalCase for public types and members, camelCase for locals and parameters, and keep test method names descriptive, for example `ShouldCompareNullableToNonNullable`.

## Testing Guidelines

Tests use TUnit in `test/NCalc.Tests` and run through Microsoft.Testing.Platform. Add tests near the feature area being changed, and place reusable fixtures or data in `Fixtures/` or `TestData/` when appropriate. Prefer behavior-focused test names beginning with `Should...` when adding new cases. Run `dotnet test --project test/NCalc.Tests/NCalc.Tests.csproj` before submitting changes; run the full solution build when public APIs, package projects, or plugins are touched.

Do not use the usual VSTest-style `--filter` option with this test project; it is reported as an unknown option. To inspect available tests, use `dotnet test --project test/NCalc.Tests/NCalc.Tests.csproj --list-tests --no-progress`. For focused runs, use Microsoft.Testing.Platform/TUnit-supported filters such as `--treenode-filter` or `--filter-uid`, and confirm the command runs a non-zero number of tests.

## Commit & Pull Request Guidelines

Recent commits use concise imperative summaries, often with a scope or category, for example `Refactor: Split parser and domain into dedicated assemblies (#560)` or `Update packages (#556)`. Keep commits focused and mention breaking changes explicitly. Pull requests should describe the change, explain user-visible behavior or API impact, link related issues, and include test results. Add screenshots only for documentation or visual site changes.


===== FILE wandb/weave::AGENTS.md | stars=1108 followers=None lang=Python bytes=20435 =====

# Agent instructions for `weave` repository

## Core Rules

- When you learn something new about the codebase or introduce a new concept, update this file (`AGENTS.md`) to reflect the new knowledge. This is YOUR FILE! It should grow and evolve with you.
- If there is something that doesn't make sense architecturally, devex-wise, or product-wise, please update the `Requests to Humans` section below.
- Always follow the established coding patterns and conventions in the codebase.
- Document any significant architectural decisions or changes.

## Python Import Rules

**IMPORTANT: Always place imports at the top of Python files.**

- All imports must be at the module level (top of the file), not inside functions or methods.
- The only exceptions are:
  - Circular import avoidance (must be documented with a comment explaining why)
  - Optional dependencies that may not be installed (must be wrapped in try/except)
  - TYPE_CHECKING imports for type hints only
- Note: Imports inside functions are not caught by linting. **Agents must self-enforce this rule.**

❌ **Never do this:**

```python
def my_function():
    import re  # BAD: import inside function
    return re.match(...)
```

✅ **Always do this:**

```python
import re  # GOOD: import at top of file

def my_function():
    return re.match(...)
```

## Development Setup

### Local Development (uv)

This project uses `uv` for dependency management. Dependencies are organized into **dependency-groups** (not extras) in `pyproject.toml`.

**Quick reference:**

- **Run tests**: `uv run --group test python -m pytest <path> -v`
- **Run linting**: `uvx ruff check <path>`
- **Run lint with auto-fix**: `uvx ruff check --fix <path>`

**Common pitfalls:**

- Do NOT use bare `python -m pytest` — the `python` on PATH may be from a uv cache, not the project `.venv`. Always use `uv run`.
- Do NOT use `--extra test` — `test` is a dependency-group, not an optional-dependency. Use `--group test`.
- `ruff` is not installed in any project dependency group. Use `uvx ruff` to run it.
- Ruff now enforces `PLW` rules. `PLW0602`, `PLW0603`, `PLW1641`, and `PLW3201` are handled with spot-level inline `# noqa` on specific lines (not global/per-file ignore). Prefer fixing code first; if intentional, suppress only the exact line.
- Be careful with `PLW1514` autofixes on serialization-sensitive code (`weave/type_handlers/Content/content.py`, `weave/type_handlers/Audio/audio.py`) and mocked file I/O (`weave/trace_server/costs/update_costs.py`): adding `encoding=` changed behavior/tests, so these files are explicitly ignored for that rule.

### Codex Development (nox)

- Your machine should be setup for you automatically via `bin/codex_setup.sh`
- If you encounter any setup issues:
  1. Check the setup script for potential problems
  2. Update `bin/codex_setup.sh` with necessary fixes
  3. Document any manual steps required in this section

_Important:_ For OpenAI Codex agents (most likely you!), your environment does not have internet access. If you need something setup beforehand, this is where you need to do it.

## Codebase Structure

### Main Components

- `weave/` - Core implementation
  - `weave/` - Python package implementation
  - `weave/trace_server` - Backend server implementation

## Generated Files — Do Not Hand-Edit

`weave/trace_server/model_providers/model_providers.json` and `weave/trace_server/costs/cost_checkpoint.json` are generated. Never edit them by hand — regenerate with `make update_model_providers` / `make update_costs` (see `weave/Makefile`).

Note: the scripts read `modelsBegin.json`/`modelsFinal.json`, which are symlinks into wandb/core and only resolve when this repo is checked out as the submodule inside wandb/core (`services/weave-trace/weave-python/weave-public`).

Persisted `AgentDashboard` objects intentionally use a closed, discriminated
schema. Supported panel variants and their configuration fields must be added
to `builtin_object_classes/agent_dashboard.py`; do not replace panel settings
with an untyped dictionary. After changing the model, run
`make synchronize-base-object-schemas` from the repository root so the Python
schema and the dependent Core frontend types stay aligned.

### Trace Server API / Node SDK Schema

When trace-server request/response models or route schemas change, refresh the API schema used by the Node SDK:

1. From this repo, run `make -C ../../weave-trace export-api-schema` to regenerate the sibling trace service's `openapi.json` from the FastAPI app.
2. Copy that schema into the tracked Node SDK schema: `cp ../../weave-trace/openapi.json sdks/node/weave.openapi.json`.
3. Regenerate the TypeScript client from `sdks/node`: `pnpm run generate-api`.

Evaluation result rows merge agent span links from two sources: legacy
`weave.genai_span_ref` call attributes and OTel spans whose promoted
`eval_run_id` plus `eval_predict_and_score_call_id` columns identify the
trial. Keep the promoted-column hydration best-effort so eval results remain
available during rolling deploys.

If `sdks/node/node_modules` is missing, run `pnpm install --frozen-lockfile` in `sdks/node` first. Do not use `npm install`; this SDK is pinned to pnpm.

## Python Testing Guidelines

### Test Framework

- Testing is managed by `nox` with multiple shards for different Python versions
- Each shard represents specific package configurations

### Server fixtures (do NOT hand-roll fake servers)

- **Never create a `_FakeServer`, stub, or mock `TraceServerInterface`** to test
  server-side logic. Use the existing `client` fixture (gives `client.server` +
  `client.project_id`) or the `trace_server` fixture, which run against a real
  ClickHouse backend. Build inputs with the real APIs
  (`obj_create`, `table_create`, etc.). Mock only external services we don't own.

### Assert on the complete payload (no substring / membership checks)

Assert on the **full value**, not that a fragment appears somewhere inside a
stringified payload. Substring (`in`) and membership checks pass on accidental
matches and let the rest of the payload drift undetected, so prefer them only
when membership in a collection is genuinely the contract under test.

❌ **Never do this:**

```python
assert "short memo" in msg                 # substring of a serialized blob
assert "error" in str(response)
assert "note" in feedback.payload          # key-presence instead of value
```

✅ **Always do this:**

```python
assert feedback.payload == {"note": "short memo", "emoji": "👍"}  # whole object
assert feedback.payload["note"] == "short memo"                   # exact field
```

If you only care about one field, pin that field with `==`; if you care about
the shape, compare the whole dict/object. The same rule applies to SQL: assert
the complete query string, never `assert "WHERE x" in sql`.

### VCR + ClickHouse isolation (integration tests)

- Integration tests replay provider traffic from VCR cassettes while the weave
  client concurrently talks to ClickHouse over localhost HTTP. vcrpy is not
  safe for that concurrency out of the box: its urllib3 passthrough wraps real
  sends in `force_reset()`, which briefly unpatches httpx/httpcore globally and
  lets provider calls escape an active cassette to the live API (seen as real
  OpenAI 429s in CI). `tests/integrations/conftest.py` carries two autouse
  fixtures that prevent this — read their docstrings before touching VCR
  config, and keep `tests/integrations/langchain/test_vcr_isolation.py` green.
- Corollary: a real provider 4xx during a `record_mode="none"` cassette means
  VCR's patches were absent at request time (an isolation bug), not that the
  cassette failed to match — matching failures raise
  `CannotOverwriteExistingCassetteException` instead.

### Key Test Shards

Focus on these primary test shards:

- `tests-3.12(shard='trace')` - Core tracing functionality
- `tests-3.12(shard='flow')` - Higher level work"flow" objects
- `tests-3.12(shard='trace_server')` - Server implementation
- `tests-3.12(shard='trace_server_bindings')` - Server bindings

### Running Tests

**IMPORTANT**: Any test depending on the `client` fixture runs against ClickHouse, the only trace-server backend. Locally, the test fixtures auto-start a ClickHouse Docker container if one isn't already running, so Docker must be available. Pass `--clickhouse-process=true` to use a local `clickhouse-server` binary instead of Docker.

#### Basic Test Commands

1. Run all tests in a specific shard: `nox --no-install -e "tests-3.12(shard='trace')"`
2. Run a specific test by appending `-- [test]` like so: `nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/test_client_trace.py::test_simple_op`
3. Run linting: `nox --no-install -e lint` (Note: This will modify files)

_Important:_ Since you don't have internet access, you must run `nox` with `--no-install`. We have pre-installed the requirements on the above shards.

#### Critical Path Information

**Test paths must be relative to the repository root**, not the `tests/` directory.

Examples:

- ✅ CORRECT: `-- tests/trace/test_dataset.py::test_basic_dataset_lifecycle`
- ❌ WRONG: `-- trace/test_dataset.py::test_basic_dataset_lifecycle`

#### Backend Selection

The `--trace-server` flag selects the backend: `clickhouse` (default) or
`fake` (in-memory).

**Fake / in-memory (Fastest for Development):**

```bash
nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/test_client_trace.py::test_simple_op --trace-server=fake
```

The fake backend (`weave/trace_server/in_memory_trace_server.py`,
`InMemoryTraceServer`) is a pure-Python, dict-backed drop-in replacement that
lives parallel to the ClickHouse implementation. It replicates **ClickHouse**
(the production backend) at the interface level: JSON_VALUE string typing for
dynamic fields, `to*OrNull` cast rules, NULLS-LAST ordering, DateTime64
comparisons, and computed summary fields. Tests that assert ClickHouse
*internals* (SQL, table routing/residence, insert batching, bucket file
storage) are gated with `client_is_clickhouse` and skip on the fake. No
files, no SQL, no Docker.

**ClickHouse (the real backend):**

```bash
nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/test_client_trace.py::test_simple_op
```

ClickHouse is the only trace-server backend (`--trace-server` defaults to
`clickhouse`):

```bash
nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/test_client_trace.py::test_simple_op
```

**Note:** ClickHouse tests require Docker to be running (the fixtures start a
container automatically), or a local `clickhouse-server` binary with
`--clickhouse-process=true`. When neither is available, use the in-memory
fake with `--trace-server=fake`.

#### Remote HTTP Trace Server Implementation Selection

The `--remote-http-trace-server` flag controls which **remote HTTP trace server implementation** is used for testing trace server bindings:

**RemoteHTTPTraceServer (Default):**

```bash
nox --no-install -e "tests-3.12(shard='trace_server_bindings')" -- tests/trace_server_bindings/test_trace_server_bindings.py --remote-http-trace-server=remote
```

**StainlessRemoteHTTPTraceServer:**

```bash
nox --no-install -e "tests-3.12(shard='trace_server_bindings')" -- tests/trace_server_bindings/test_trace_server_bindings.py --remote-http-trace-server=stainless
```

**Important Notes:**

- The `--remote-http-trace-server` flag is for **trace server binding implementation** (RemoteHTTPTraceServer vs StainlessRemoteHTTPTraceServer)
- Both implementations share the same test file; the flag determines which server class is used

#### Environment Issues

**Color Flag Conflicts:**
If you encounter an error like `Can not specify both --no-color and --force-color`, this is due to conflicting environment variables. Unset them before running nox:

```bash
unset NO_COLOR FORCE_COLOR && nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/test_dataset.py::test_basic_dataset_lifecycle
```

**Prek stashing behavior:**
`nox --no-install -e lint` runs `prek`, and prek stashes unstaged changes before running hooks. If you need to validate a fix to one file (for example with `--mypy-only`), stage that file first or run the checker directly, otherwise hooks may run against older content.

**Markdown serialization and MTSAAS env:**
`weave/type_handlers/Markdown/markdown.py` only stores large markdown payloads in `markup.md` when `is_mtsaas()` is true. If local `WANDB_BASE_URL`/`WF_TRACE_SERVER_URL` differs from CI defaults, `test_serialization_correctness[markdown]` may fail locally with inline markup differences. For CI-like behavior, set:

```bash
WF_TRACE_SERVER_URL=https://trace.wandb.ai nox --no-install -e "tests-3.12(shard='trace')" -- tests/trace/data_serialization/test_serialization_correctness.py::test_serialization_correctness[markdown]
```

#### Reinstalling Dependencies

If you encounter import errors or missing modules, reinstall the test shard environment:

```bash
nox --install-only -e "tests-3.12(shard='trace')"
```

Then run your tests with `--no-install` as usual.

### LangChain Integration Tests

The langchain integration tests work fully on macOS including chromadb/vector store tests.

**Running LangChain Tests:**

```bash
nox --no-install -e "tests-3.12(shard='langchain')" -- tests/integrations/langchain/
```

## Typescript Testing Guidelines

The Node SDK (`sdks/node`) is a **pnpm** project — it ships a `pnpm-lock.yaml`
and pins `"packageManager": "pnpm@10.8.1"` in `package.json`. Do **not** run
`npm i`: npm's resolver crashes trying to dedupe pnpm's symlink `node_modules`
(`TypeError: Cannot read properties of null (reading 'matches')`).

```
cd sdks/node
pnpm install
pnpm test
```

To run an example (e.g. the Claude Agent SDK demo), `dist/` must be built first
(`import 'weave'` self-resolves via the package `exports` to `dist/index.mjs`);
`pnpm install` builds it via the `prepare` script. Then:

```
pnpm exec tsx examples/claudeAgents.ts
```

### TypeScript integration metadata

- `sdks/node/src/integrations/integrationMetadata.ts` remains shared:
  `asAttributes()` supplies nested provenance to Weave-call integrations, while
  `asOtelAttributes()` supplies canonical `weave.integration.name` and
  `weave.integration.version` identity to OTel integrations and preserves
  flattened `weave.integration.meta.*` provenance. OTel scalar metadata stays
  typed; non-scalar values are stringified.

## Code Review & PR Guidelines

### PR Requirements

- Title format: `<type>(<scope>): <description>`, where `<type>` is one of
  `chore`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `security`,
  `test`. A scope is **required** (`requireScope: true`) and CI validates it
  (`.github/workflows/pr.yaml`).
- **Pick the scope by which SDK/area the change touches:**
  - `weave_ts` — **required for ALL TypeScript / Node SDK changes** (anything
    under `sdks/node/`). Any PR that modifies the TS SDK must be marked
    `(weave_ts)`, e.g. `fix(weave_ts): ...`, `feat(weave_ts): ...`,
    `chore(weave_ts): ...`.
  - `weave` — the Python SDK and trace server (the default for `weave/…`
    changes), e.g. `fix(weave): ...`, `feat(weave): ...`, `chore(weave): ...`.
  - Other valid scopes (see `pr.yaml` for the authoritative list): `ui`, `app`,
    `dev`, `deps`, `inference`.
- If a single PR spans both the Python and TS SDKs, prefer splitting it; if that
  isn't practical, scope it to the SDK that carries the primary change and call
  out the other in the PR body.
- Provide detailed PR summaries including:
  - Purpose of changes
  - Testing performed
  - Any breaking changes
  - Related issues/PRs

### Pre-commit Checklist

1. Run lint
2. Ensure all tests pass
3. Update documentation if needed
4. Check for any breaking changes

### GitHub Actions Authentication

- Prefer native `${{ secrets.GITHUB_TOKEN }}` for repository-local workflow operations that only need the current repo.
- Use `actions/create-github-app-token@v3` with `vars.WANDBOT_3000_APP_ID` and `secrets.WANDBOT_3000_PRIVATE_KEY` for cross-repository access or bot pushes that must behave like app-authenticated writes.
- Do not introduce new GitHub PAT secrets in workflows unless there is no viable `GITHUB_TOKEN` or GitHub App alternative.

## Common Development Patterns

### Code Organization

- Python code follows standard module organization
- TypeScript/React components are organized by feature
- Shared utilities should be placed in appropriate common directories

### Error Handling

- Use appropriate error types from `weave.errors`
- Include meaningful error messages
- Add error handling tests

### Integration Testing

- Since autopatching was removed from `weave.init()`, integration tests must explicitly patch their integrations
- Add a fixture with `autouse=True` at the top of each integration test file to enable patching
- Example pattern:
  ```python
  @pytest.fixture(autouse=True)
  def patch_integration() -> Generator[None, None, None]:
      patcher = get_integration_patcher()
      patcher.attempt_patch()
      yield
      patcher.undo_patch()
  ```
- Some integrations (like instructor) may need to patch multiple libraries

### Claude Agent SDK token accounting

- Anthropic reports Claude Agent SDK `input_tokens` as fresh, uncached input
  only. Weave usage requires an inclusive prompt total, with
  `cache_read_input_tokens` and `cache_creation_input_tokens` represented as
  subsets of `input_tokens`, because cost and cache-hit-rate rollups use that
  convention.
- Both Python tracing paths must normalize aggregate result usage through
  `weave/integrations/claude_agent_sdk/usage.py`. Keep the SDK's yielded
  `ResultMessage` and the calls-based root output unchanged; normalize the
  calls-based usage summary and the OTel span attributes consumed by Weave
  rollups.
- Regression coverage must exercise both the calls-based and OTel integrations
  with nonzero cache-read and cache-creation counts.

### Documentation

- Update relevant docstrings for Python code
- Add JSDoc comments for TypeScript code
- Update this file when introducing new patterns or concepts

---

## Integration Patching

### Automatic Implicit Patching

Weave provides automatic implicit patching for all supported integrations using an import hook mechanism:

- **Automatic Patching**: Libraries are automatically patched regardless of when they are imported
- **Import Hook**: An import hook intercepts library imports and applies patches automatically
- **Explicit Patching**: Optional manual patching is still available for fine-grained control

Example:

```python
# Automatic patching - works regardless of import order!

# Option 1: Import before weave.init()
import openai
import weave
weave.init('my-project')  # OpenAI is automatically patched!

# Option 2: Import after weave.init()
import weave
weave.init('my-project')
import anthropic  # Automatically patched via import hook!

# Option 3: Explicit patching (optional)
import weave
weave.init('my-project')
weave.patch_openai()  # Manually patch if needed
```

### Available Patch Functions

All integrations have corresponding patch functions for explicit control: `patch_openai()`, `patch_anthropic()`, `patch_mistral()`, etc.

### Technical Implementation

The import hook uses Python's `sys.meta_path` to intercept imports and automatically apply patches when supported libraries are imported. This ensures seamless integration tracking without requiring users to manage import order or make explicit patch calls.

### Disabling Implicit Patching

If you prefer explicit control over which integrations are patched, you can disable implicit patching:

```python
# Via settings parameter
weave.init('my-project', settings={'implicitly_patch_integrations': False})

# Via environment variable
export WEAVE_IMPLICITLY_PATCH_INTEGRATIONS=false
```

When disabled, you must explicitly call patch functions like `weave.patch_openai()` to enable tracing for integrations.

# Requests to Humans

This section contains a list of questions, clarifications, or tasks that LLM agents wish to have humans complete.
If there is something that doesn't make sense architecturally, devex-wise, or product-wise, please update this file and the humans will take care of it.
Think of this as the reverse-task assignment - a place where you can communicate back to us.

- [ ] Add TypeScript testing guidelines
- [ ] ...


===== FILE learningequality/kolibri::AGENTS.md | stars=1086 followers=None lang=Python bytes=8841 =====

<!-- Generic guidance for all coding agents (Claude Code, Zed, Cursor, etc.) -->

# Kolibri Development Guide for AI Coding Agents

**Project:** Kolibri - Offline learning platform for low-resource communities
**Stack:** Python/Django backend, Vue.js 2.7 frontend, pytest/Jest testing
**Platforms:** Linux, Windows, Mac, Android (via python-for-android)

## Quick Start

```bash
uv sync --group dev --all-packages    # Python deps + venv (all workspace member packages included)
pnpm install                          # Node deps
prek install                          # Required — commits fail without this
export KOLIBRI_RUN_MODE=dev
kolibri configure setup               # Database migrations and updates
```

Dev server:
```bash
pnpm devserver             # Django on port 8000 + Webpack watcher + sandbox dev server
```

→ Full setup: `docs/getting_started.rst` | Architecture: `docs/stack.rst` | Dev data: `docs/howtos/dev_data_setup.md`

## Critical Gotchas

### ⚠️ BEFORE Writing Any Vue Component, Search for Existing Ones
Do not create a new component without first searching for an existing solution:
1. **Kolibri Design System** ([docs](https://design-system.learningequality.org/)) — `KButton`, `KCircularLoader`, `KTextbox`, `KSelect`, `KModal`, `KCheckbox`, `KIcon`, etc.
2. **`packages/kolibri/components/`** — `AuthMessage`, `BottomAppBar`, `AppBar`, etc.
3. **`packages/kolibri-common/components/`** — `AccordionContainer`, `BaseToolbar`, etc.

Use existing components (e.g., `KTable` for tabular data, `KCircularLoader` for loading states). If one does 80% of what you need, wrap it — do not rewrite.

### ⚠️ Use Theme Tokens, Not Hard-Coded Colors
Never use raw color values. Access theme colors via `$themeTokens` and `$themePalette`:
```vue
<template>
  <div :style="{ color: $themeTokens.text, backgroundColor: $themeTokens.surface }">
    <span :style="{ color: $themeTokens.annotation }">secondary text</span>
  </div>
</template>
```
For computed dynamic styles, use `$computedClass`. See `docs/frontend_architecture/core.rst`.

### ⚠️ Style Blocks, Not Inline — RTL Depends On It
Non-dynamic styles go in `<style>` blocks. RTLCSS auto-flips directional properties (`padding-left` → `padding-right`) in style blocks but **cannot flip inline styles**. Dynamic directional styles must check `isRtl`. → `docs/i18n.rst`

### ⚠️ Composition API, Not Options API
New components must use `setup()`. Do not use Options API (`data()`, `computed:`, `methods:`).

### ⚠️ No New Vuex — Use Composables
Vuex is deprecated. Use Vue composables for state. → `docs/frontend_architecture/composables.rst`, `docs/frontend_architecture/vuex.rst`

### ⚠️ Use `responsive-window` / `responsive-element`, Not Media Queries
Do not use CSS `@media` queries. Kolibri runs on Android and varied screen sizes. Use the `responsive-window` or `responsive-element` system for responsive layouts.

### ⚠️ Internationalize All User-Visible Text
Use `createTranslator` — never hard-code strings in templates:
```javascript
const strings = createTranslator('QuizStrings', {
  title: { message: 'Quiz Results', context: 'Page heading' },
});
// In setup(), destructure with $ suffix:
const { title$ } = strings;  // title$() returns translated string
```

### ⚠️ API Calls via Resource Classes Only
Use `Resource` from `kolibri/apiResource`. Define in `apiResources.js`. Never use raw `fetch` or `axios`.

### ⚠️ Backend APIs: Use ValuesViewset with Serializer Derivation
Use `ValuesViewset` (or `ReadOnlyValuesViewset`) from `kolibri.core.api` for new API endpoints — not `ModelViewSet`, `ViewSet`, or `GenericViewSet`. Define a DRF serializer as the source of truth; the viewset derives the `values()` query automatically:
```python
from rest_framework import serializers
from kolibri.core.api import ReadOnlyValuesViewset

class MySerializer(serializers.ModelSerializer):
    class Meta:
        model = MyModel
        fields = ("id", "title", "description")

class MyViewSet(ReadOnlyValuesViewset):
    serializer_class = MySerializer
    queryset = MyModel.objects.all()
```
Do **not** define explicit `values` tuples or `field_map` dicts on new viewsets — these are legacy patterns being migrated away.

The model should define a default `ordering` in its `Meta`, or the viewset's `queryset` should set an explicit `order_by()` — response ordering (and pagination) is nondeterministic otherwise.

Viewset permissions use `KolibriAuthPermissions` from `kolibri.core.auth.api`, which delegates object-level checks to the model's declarative permissions (e.g. `RoleBasedPermissions`). It only works for models that participate in Kolibri's auth/permissions system — models without those declarations need a different permission class.

See `docs/backend_architecture/api_patterns.rst`.

### ⚠️ Testing is Required
- **Python:** pytest is the test runner. Django API tests extend `APITestCase` from `rest_framework.test`. Other Django tests extend `django.test.TestCase`. Only use bare pytest-style function tests for non-Django code.
- **Frontend:** Jest runner + Vue Testing Library. Do NOT import from `vitest` or `@vue/test-utils`. `describe`/`it`/`expect` are Jest globals (no import needed). Use `jest.fn()` and `jest.mock()`:
  ```javascript
  import { render, screen } from '@testing-library/vue';
  // describe, it, expect are Jest globals — do NOT import them
  describe('MyComponent', () => {
    it('renders', () => {
      render(MyComponent, { props: { title: 'Hello' } });
      expect(screen.getByText('Hello')).toBeTruthy();
    });
  });
  ```
- **TDD:** Write a failing test first, then make it pass. This is especially important for bug fixes — always write a test that reproduces the bug before fixing it.

### ⚠️ Pre-commit Auto-fixes Files
When a commit fails: prek auto-fixes files → **`git add` the fixed files** → re-commit.

## Project Structure

```
kolibri/
├── kolibri/core/          # Core modules: auth/, content/, device/, lessons/, exams/, logger/, tasks/
├── kolibri/plugins/       # Frontend plugins: learn/, coach/, facility/, ...
│   └── <plugin>/          # api_urls.py, viewsets.py, kolibri_plugin.py, test/
│       └── frontend/      # app.js, views/, composables/, routes/, __tests__/
├── packages/              # JS packages: kolibri/, kolibri-common/
├── docs/                  # Developer docs (architecture, testing, i18n, etc.)
├── requirements/          # Python deps
└── test/                  # Test utilities and fixtures
```

→ See `docs/backend_architecture/plugins.rst` for plugin layout and core-vs-plugins decision guide

## Code Quality

→ See `docs/code_quality.rst` for detailed principles. Key: tests assert behavior not implementation, composition over inheritance, let errors propagate, don't weaken existing tests, compute don't store, tell don't ask.

## Key Conventions

**Python:** F-strings preferred. One import per line. `DateTimeTzField` for timestamps (not Django's `DateTimeField`). `UUIDField` from morango for syncable models. Descriptive migration names (no `_auto_`). All imports at file top — inline imports are only permitted to prevent circular imports.

**Vue:** PascalCase filenames. Component `name` must match filename. Use `computed()` for derived values.

**Git:** Imperative commit messages, no conventional-commit prefixes. Logical commit ordering for review. Ruff/Prettier enforced by prek.

**Don't guess — look at existing code** for patterns: `docs/backend_architecture/api_patterns.rst`, `docs/frontend_architecture/`, existing test files in `__tests__/` or `test/`.

## Running Tests

```bash
pytest kolibri/path/to/test/                          # Python (directory)
pytest kolibri/core/auth/test/ -k test_login          # Python (filter by name)
pnpm test-jest path/to/file.spec.js                # Frontend (single file)
pnpm test-jest --testPathPattern learn              # Frontend (filter by pattern)
prek run --all-files                                  # Lint (all files)
prek run --files path/to/File.vue                     # Lint (specific file)
```

Do NOT use `npx jest` or invoke Jest directly — always use `pnpm test-jest`. Always use `prek` as the single entry point for linting — do not invoke ESLint or other linters directly.

## Docs Reference

Testing: `docs/testing.rst`, `docs/frontend_architecture/unit_testing.rst`, `docs/backend_architecture/testing.rst` | Frontend arch: `docs/frontend_architecture/` | Backend arch: `docs/backend_architecture/` | i18n: `docs/i18n.rst` | Code quality: `docs/code_quality.rst` | How-tos: `docs/howtos/` | Workflow: `docs/development_workflow.rst` | Multi-agent setup: `docs/howtos/multi_agent_setup.md` | User docs: https://kolibri.readthedocs.io/


===== FILE codestable/CodeStable::CLAUDE.md | stars=1081 followers=None lang=Python bytes=2175 =====

# Claude Rules

## 核心原则

言简意赅。先读仓库事实、现有 skill 文档和 ADR，再修改规则；只把可复用且能验证的做法写进规则文件。

## 语言与文档

- 默认用中文写面向人的回复、报告和文档；代码、命令、路径、协议字段、YAML/JSON key 保持原格式。
- 单个 Markdown 文件不得超过 300 行；超过必须拆分。
- 增加或更新 skill 时，同步检查相关 skill、README/reference、测试和 ADR 中的表述。
- `AGENTS.md`/`CLAUDE.md` 只写 agent 行为规则；不要替代 `.codestable/attention.md`、design、checklist、ADR 等项目事实载体。

## Skill 边界

- 不同 skill 之间不要相互耦合；A skill 在非必须情况下不要读取或依赖 B skill 的内部文件。
- skill 是独立安装单元，运行时每个 skill 只能稳定看到自己包内文件；不要在 SKILL.md 中写 `B-skill/reference/xxx.md` 这类 sibling 引用。
- 跨 skill 共享的参考文档必须走项目层：由 `cs-onboard` 复制到项目 `.codestable/reference/`，其他 skill 用项目相对路径 `.codestable/reference/xxx.md` 读取。
- 要改共享口径时，改 `plugins/codestable/skills/cs-onboard/references/` 下的模板，并同步项目副本、相关 skill 文案和测试。

## CodeStable Runtime

- 新版 CodeStable 工具、gate、doctor、workflow-next、DoD runner 等入口必须从 `<cs-onboard skill 目录>/tools/` 调用。
- 不要新增 `python .codestable/tools/...` 作为新版入口；`.codestable/tools/` 只作 legacy compatibility。
- 保留老项目里的 `.codestable/tools/`、旧 worktree/branch 文档或 hooks；除非用户明确要求，不要默认删除或覆盖。
- CodeStable skills 不拥有默认 worktree/branch 策略；是否创建 worktree、如何命名分支、如何 merge，应由宿主、owner 或未来独立 skill 决定。

## 验证

- skill/runtime 改动完成前至少运行相关 pytest 与 `git diff --check`。
- runtime sync 或 health 行为变化时，运行 `codestable-runtime-sync.py --check --json`，确认 `tool_runtime: skill-global`、managed paths 和 missing paths 符合预期。
