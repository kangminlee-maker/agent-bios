

===== FILE n8n-io/n8n::.github/CLAUDE.md | stars=197940 followers=None lang=TypeScript bytes=1121 =====

@../AGENTS.md

## .github Quick Reference

This folder contains n8n's GitHub Actions infrastructure.

### Key Files

| File/Folder | Purpose |
|-------------|---------|
| `WORKFLOWS.md` | Complete CI/CD documentation |
| `DEVELOPING_V3.md` | How to develop v3 features (master + 3.x branch model, opt-in flags) |
| `workflows/` | GitHub Actions workflows |
| `actions/` | Reusable composite actions |
| `scripts/` | Release & Docker automation |
| `CODEOWNERS` | Team review ownership |

### Workflow Naming

| Prefix | Purpose |
|--------|---------|
| `test-` | Testing (unit, E2E, visual) |
| `ci-` | Continuous integration |
| `util-` | Utilities (notifications) |
| `build-` | Build processes |
| `release-` | Release automation |
| `sec-` | Security scanning |

Reusable workflows: add `-reusable` or `-callable` suffix.

### Common Tasks

**Add workflow:** Create in `workflows/`, document in `WORKFLOWS.md`

**Add script:** Create `.mjs` in `scripts/`, document in `WORKFLOWS.md`

### Reference

See `WORKFLOWS.md` for:
- Architecture diagrams
- Workflow call graph
- Scheduled jobs & triggers
- Runners & secrets


===== FILE rustdesk/rustdesk::AGENTS.md | stars=118837 followers=9050 lang=Rust bytes=3443 =====

# RustDesk Guide

## Project Layout

### Directory Structure
* `src/` Rust app
* `src/server/` audio / clipboard / input / video / network
* `src/platform/` platform-specific code
* `src/ui/` legacy Sciter UI (deprecated)
* `flutter/` current UI
* `libs/hbb_common/` config / proto / shared utils
* `libs/scrap/` screen capture
* `libs/enigo/` input control
* `libs/clipboard/` clipboard
* `libs/hbb_common/src/config.rs` all options

### Key Components
- **Remote Desktop Protocol**: Custom protocol implemented in `src/rendezvous_mediator.rs` for communicating with rustdesk-server
- **Screen Capture**: Platform-specific screen capture in `libs/scrap/`
- **Input Handling**: Cross-platform input simulation in `libs/enigo/`
- **Audio/Video Services**: Real-time audio/video streaming in `src/server/`
- **File Transfer**: Secure file transfer implementation in `libs/hbb_common/`

### UI Architecture
- **Legacy UI**: Sciter-based (deprecated) - files in `src/ui/`
- **Modern UI**: Flutter-based - files in `flutter/`
  - Desktop: `flutter/lib/desktop/`
  - Mobile: `flutter/lib/mobile/`
  - Shared: `flutter/lib/common/` and `flutter/lib/models/`

## Rust Rules

* Avoid `unwrap()` / `expect()` in production code.
* Exceptions:

  * tests;
  * lock acquisition where failure means poisoning, not normal control flow.
* Otherwise prefer `Result` + `?` or explicit handling.
* Do not ignore errors silently.
* Avoid unnecessary `.clone()`.
* Prefer borrowing when practical.
* Do not add dependencies unless needed.
* Keep code simple and idiomatic.

## Tokio Rules

* Assume a Tokio runtime already exists.
* Never create nested runtimes.
* Never call `Runtime::block_on()` inside Tokio / async code.
* Do not hide runtime creation inside helpers or libraries.
* Do not hold locks across `.await`.
* Prefer `.await`, `tokio::spawn`, channels.
* Use `spawn_blocking` or dedicated threads for blocking work.
* Do not use `std::thread::sleep()` in async code.

## Editing Hygiene

* Change only what is required.
* Prefer the smallest valid diff.
* Do not refactor unrelated code.
* Do not make formatting-only changes.
* Keep naming/style consistent with nearby code.

## Localization (`src/lang/*.rs`)

Each file is a `HashMap<key, translation>`. Layout:

* `template.rs` is the master list of every key. **Never edit it** as part of translation work.
* `en.rs` holds only the keys whose English display text differs from the key itself.
* Every other file (`de.rs`, `fr.rs`, …) carries the full key set; an untranslated entry has an empty value: `("key", "")`.

### Finding the English source for a key

When filling an empty entry, determine the source English text with this rule:

* If `key` exists in `en.rs` **with a non-empty value**, that value is the source text (look it up in `en.rs`).
* Otherwise the **key string itself is the source text** (the key is already plain English).

Then translate that source into the file's target language (infer the language from the file's existing non-empty entries / filename).

### Translation hygiene

* Only fill empty values. Never change keys, and never touch existing non-empty translations.
* Preserve placeholders (`{}`) and escape sequences (`\n`, `\"`) exactly as in the source.
* Do not translate brand or technical tokens: `RustDesk`, `Socks5`, `TLS`, `UAC`, `Wayland`, `X11`, `TCP`, `UDP`, `2FA`, `RDP`, `D3D`, etc.
* Copy URL values (e.g. `doc_*` keys) verbatim from `en.rs`.


===== FILE ruvnet/RuView::CLAUDE.md | stars=86232 followers=10641 lang=Rust bytes=22358 =====

# Claude Code Configuration — WiFi-DensePose + Claude Flow V3

## Project: wifi-densepose

WiFi-based human pose estimation using Channel State Information (CSI).
Dual codebase: Python v1 (`v1/`) and Rust port (`v2/`).
### Key Rust Crates
| Crate | Description |
|-------|-------------|
| `wifi-densepose-core` | Core types, traits, error types, CSI frame primitives |
| `wifi-densepose-signal` | SOTA signal processing + RuvSense multistatic sensing (16 modules) |
| `wifi-densepose-nn` | Neural network inference (ONNX, PyTorch, Candle backends) |
| `wifi-densepose-train` | Training pipeline with ruvector integration + ruview_metrics; MAE pretraining recipe (`mae.rs`, ADR-152 §2.3) + WiFlow-STD port (`wiflow_std/`, tch-gated) |
| `wifi-densepose-mat` | Mass Casualty Assessment Tool — disaster survivor detection |
| `wifi-densepose-hardware` | ESP32 aggregator, TDM protocol, channel hopping firmware; `ieee80211bf/` 802.11bf forward-compat protocol model (ADR-153) |
| `wifi-densepose-ruvector` | RuVector v2.0.4 integration + cross-viewpoint fusion (5 modules) |
| `wifi-densepose-wasm` | WebAssembly bindings for browser deployment |
| `wifi-densepose-cli` | CLI tool (`wifi-densepose` binary) — `calibrate`/`calibrate-serve`/`enroll`/`train-room`/`room-watch` + MAT (MAT gated behind the `mat` feature; build `--no-default-features` for the aarch64/appliance calibration binary) |
| `wifi-densepose-calibration` | ADR-151 per-room calibration & specialist training — `baseline → enroll → extract → train` → bank of small specialists (presence/posture/breathing/heartbeat/restlessness/anomaly) + multistatic fusion; pure Rust, edge-deployable |
| `wifi-densepose-sensing-server` | Lightweight Axum server for WiFi sensing UI |
| `wifi-densepose-wifiscan` | Multi-BSSID WiFi scanning (ADR-022) |
| `wifi-densepose-vitals` | ESP32 CSI-grade vital sign extraction (ADR-021) |
| `nvsim` | Deterministic NV-diamond magnetometer pipeline simulator (ADR-089) — standalone leaf, WASM-ready |
| `vendor/rvcsi` (submodule) | **rvCSI** — edge RF sensing runtime (ADR-095/096): 9 crates (`rvcsi-core`/`-dsp`/`-events`/`-adapter-file`/`-adapter-nexmon`/`-ruvector`/`-runtime`/`-node`/`-cli`). Lives in its own repo ([github.com/ruvnet/rvcsi](https://github.com/ruvnet/rvcsi)), vendored here under `vendor/rvcsi`, published to crates.io as `rvcsi-* 0.3.x` and to npm as `@ruv/rvcsi`. Not a `v2/` workspace member — depend on the published crates (or the submodule's `crates/rvcsi-*` paths). Normalized `CsiFrame`/`CsiWindow`/`CsiEvent` schema, validate-before-FFI, reusable DSP, typed confidence-scored events, the napi-c Nexmon shim (real nexmon_csi `.pcap` from a Raspberry Pi 5 / 4 / 3B+ — BCM43455c0), the napi-rs SDK, the `rvcsi` CLI, a Claude Code plugin. |
| `vendor/rufield` (submodule) | **RuField MFS** — the open spec for camera-free multimodal field sensing (ADR-260). A common `FieldEvent`/`FieldTensor`/`FusionGraph`/`PrivacyClass`/`ProvenanceReceipt` model *above* WiFi CSI/CIR/BFLD, UWB, BLE Channel Sounding, mmWave radar, ultrasound, subsonic, infrared, and quantum sensors. Lives in its own repo ([github.com/ruvnet/rufield](https://github.com/ruvnet/rufield)), vendored here under `vendor/rufield`. Not a `v2/` workspace member. v0.1 reference stack = 7 crates (`rufield-core`/`-provenance`/`-privacy`/`-adapters`/`-fusion`/`-bench`/`-viewer`), 72 tests/0 failed; `rufield-viewer` is an Axum + vanilla-JS read-only dashboard (`cargo run -p rufield-viewer`) completing ADR-260 §27.9. The WiFi-CSI modality is now **real-replay-backed** via `CsiReplayAdapter` (ingests real captured `.csi.jsonl` → fused presence/breathing inferences; replay-from-file, unlabeled CSI-variance proxy, not validated accuracy); mmWave/thermal + all synthetic-bench F1 numbers remain **SYNTHETIC** (no live hardware — live streaming + labeled accuracy are roadmap). |
| `wifi-densepose-rufield` | ADR-262 P1 **anti-corruption bridge** — converts RuView WiFi-CSI sensing output (`SensingSnapshot` mirroring `SensingUpdate` + `TrustedOutput`, owned primitives, no dep on `wifi-densepose-sensing-server`) into **signed RuField `FieldEvent`s** (`Modality::WifiCsi`, real `timestamp_ns`, sha256 + ed25519 provenance, `synthetic=false`). The single coupling point between RuView and the standalone RuField MFS spec (§5.4); path-deps the `vendor/rufield` submodule crates (`rufield-core`/`-provenance`/`-privacy`/`-fusion`). **Critical §3.3 privacy mapping** (`map_privacy`): maps RuView class → RuField P0–P5 by **information content, never byte value**, fail-closed (`Derived → P4/P5`, never P1; `demoted` floors to ≥ P2). 15 tests / 0 failed (round-trip / `is_fusable` / fusion-ingest / privacy-safety / determinism). P1 plumbing — not wired into the live server (P3), no accuracy claim. |
| `ruview-swarm` | Drone swarm control system (ADR-148) — hierarchical-mesh topology, Raft consensus, MARL, CSI sensing payload, MAVLink/PX4 compat, Ruflo AI-agent integration |

### RuvSense Modules (`signal/src/ruvsense/`)
| Module | Purpose |
|--------|---------|
| `multiband.rs` | Multi-band CSI frame fusion, cross-channel coherence |
| `phase_align.rs` | Iterative LO phase offset estimation, circular mean |
| `multistatic.rs` | Attention-weighted fusion, geometric diversity |
| `coherence.rs` | Z-score coherence scoring, DriftProfile |
| `coherence_gate.rs` | Accept/PredictOnly/Reject/Recalibrate gate decisions |
| `pose_tracker.rs` | 17-keypoint Kalman tracker with AETHER re-ID embeddings |
| `field_model.rs` | SVD room eigenstructure, perturbation extraction |
| `tomography.rs` | RF tomography, ISTA L1 solver, voxel grid |
| `longitudinal.rs` | Welford stats, biomechanics drift detection |
| `intention.rs` | Pre-movement lead signals (200-500ms) |
| `cross_room.rs` | Environment fingerprinting, transition graph |
| `gesture.rs` | DTW template matching gesture classifier |
| `adversarial.rs` | Physically impossible signal detection, multi-link consistency |
| `cir.rs` | ADR-134 CSI→CIR via ISTA L1 sparse recovery (NeumannSolver warm-start) |
| `calibration.rs` | ADR-135 empty-room baseline (Welford amplitude + von Mises phase, drift trigger) |

### Cross-Viewpoint Fusion (`ruvector/src/viewpoint/`)
| Module | Purpose |
|--------|---------|
| `attention.rs` | CrossViewpointAttention, GeometricBias, softmax with G_bias |
| `geometry.rs` | GeometricDiversityIndex, Cramer-Rao bounds, Fisher Information |
| `coherence.rs` | Phase phasor coherence, hysteresis gate |
| `fusion.rs` | MultistaticArray aggregate root, domain events |

### RuVector v2.0.4 Integration (ADR-016 complete, ADR-017 proposed)
All 5 ruvector crates integrated in workspace:
- `ruvector-mincut` → `metrics.rs` (DynamicPersonMatcher) + `subcarrier_selection.rs`
- `ruvector-attn-mincut` → `model.rs` (apply_antenna_attention) + `spectrogram.rs`
- `ruvector-temporal-tensor` → `dataset.rs` (CompressedCsiBuffer) + `breathing.rs`
- `ruvector-solver` → `subcarrier.rs` (sparse interpolation 114→56) + `triangulation.rs`
- `ruvector-attention` → `model.rs` (apply_spatial_attention) + `bvp.rs`

### Architecture Decisions
182 ADRs in `docs/adr/` (numbered ADR-001 through ADR-265, with gaps). Key ones:
- ADR-014: SOTA signal processing (Accepted)
- ADR-015: MM-Fi + Wi-Pose training datasets (Accepted)
- ADR-016: RuVector training pipeline integration (Accepted — complete)
- ADR-017: RuVector signal + MAT integration (Proposed — next target)
- ADR-024: Contrastive CSI embedding / AETHER (Accepted)
- ADR-027: Cross-environment domain generalization / MERIDIAN (Accepted)
- ADR-028: ESP32 capability audit + witness verification (Accepted)
- ADR-029: RuvSense multistatic sensing mode (Proposed)
- ADR-030: RuvSense persistent field model (Proposed)
- ADR-031: RuView sensing-first RF mode (Proposed)
- ADR-032: Multistatic mesh security hardening (Proposed)
- ADR-148: Drone swarm control system / `ruview-swarm` (In Progress)
- ADR-152: WiFi-Pose SOTA 2026 intake — geometry conditioning, WiFlow-STD benchmark (measurement (a) complete: claims MEASURED-EQUIVALENT at ~96% PCK@20), MAE recipe (Proposed; §2.1–2.3, 2.6 implemented)
- ADR-153: IEEE 802.11bf-2025 forward-compatibility protocol model (Accepted — amends ADR-152 §2.4)
- ADR-182: `npx ruview` harness minted via MetaHarness (Accepted — P1+P2 shipped as `@ruvnet/ruview`)
- ADR-263: `@ruvnet/ruview` npm harness deep review + optimization strategy (Proposed)
- ADR-264: `@ruvnet/rvagent` MCP server + `@ruv/ruview-cli` deep review + optimization strategy (Proposed)
- ADR-265: RuView npm distribution strategy — CI gate, provenance, version single-sourcing (Proposed)

### Supported Hardware

| Device | Port | Chip | Role | Cost |
|--------|------|------|------|------|
| ESP32-S3 (8MB flash) | COM9 (ruvzen, was COM7) | Xtensa dual-core | WiFi CSI sensing node | ~$9 |
| ESP32-S3 SuperMini (4MB) | — | Xtensa dual-core | WiFi CSI (compact) | ~$6 |
| ESP32-C6 + Seeed MR60BHA2 | COM12 (ruvzen, was COM4) | RISC-V + 60 GHz FMCW | mmWave HR/BR/presence + WiFi CSI | ~$15 |
| HLK-LD2410 | — | 24 GHz FMCW | Presence + distance | ~$3 |

**Not supported:** ESP32 (original), ESP32-C3 — single-core, can't run CSI DSP pipeline.

**⚠️ Compact boards (SuperMini, ESP32-S3-Zero, other coin-sized clones) run hot:** the firmware keeps the WiFi radio on continuously (`WIFI_PS_NONE`) and runs a full DSP pipeline (`edge_tier=2`), which is sustained high current draw. Full-size dev boards handle this fine; coin-sized clones with minimal PCB copper and budget regulators can run uncomfortably hot and, per at least one field report, have failed to power on again after a hot session. Give them airflow and check by touch during the first few minutes. See `firmware/esp32-csi-node/README.md` for details.

### Build & Test Commands (this repo)
```bash
# Rust — full workspace tests (1,031+ tests, ~2 min)
cd v2
cargo test --workspace --no-default-features

# Rust — single crate check (no GPU needed)
cargo check -p wifi-densepose-train --no-default-features

# Python — deterministic proof verification (SHA-256)
python archive/v1/data/proof/verify.py

# Python — test suite
cd archive/v1 && python -m pytest tests/ -x -q
```

### ESP32 Firmware Build (Windows — Python subprocess required)
```bash
# Build 8MB firmware (real WiFi CSI mode, no mocks)
# See CLAUDE.local.md for the full Python subprocess command
# Key: must strip MSYSTEM env vars for ESP-IDF v5.4 on Git Bash

# Build 4MB firmware
cp sdkconfig.defaults.4mb sdkconfig.defaults
# then same build process

# Flash to COM7
# [python, idf_py, '-p', 'COM7', 'flash']

# Provision WiFi
python firmware/esp32-csi-node/provision.py --port COM7 \
  --ssid "YourWiFi" --password "secret" --target-ip 192.168.1.20

# Monitor serial
python -m serial.tools.miniterm COM7 115200
```

### Firmware Release Process
1. Build 8MB from `sdkconfig.defaults.template` (no mock)
2. Build 4MB from `sdkconfig.defaults.4mb` (no mock)
3. Save 6 binaries: `esp32-csi-node.bin`, `bootloader.bin`, `partition-table.bin`, `ota_data_initial.bin`, `esp32-csi-node-4mb.bin`, `partition-table-4mb.bin`
4. Tag: `git tag v0.X.Y-esp32 && git push origin v0.X.Y-esp32`
5. Release: `gh release create v0.X.Y-esp32 <binaries> --title "..." --notes-file ...`
6. Verify on real hardware (COM7) before publishing
7. **CRITICAL:** Always test with real WiFi CSI, not mock mode — mock missed the Kconfig threshold bug

### Crate Publishing Order
Crates must be published in dependency order:
1. `wifi-densepose-core` (no internal deps)
2. `wifi-densepose-vitals` (no internal deps)
3. `wifi-densepose-wifiscan` (no internal deps)
4. `wifi-densepose-hardware` (no internal deps)
5. `wifi-densepose-signal` (depends on core)
6. `wifi-densepose-nn` (no internal deps, workspace only)
7. `wifi-densepose-ruvector` (no internal deps, workspace only)
8. `wifi-densepose-train` (depends on signal, nn)
9. `wifi-densepose-mat` (depends on core, signal, nn)
10. `wifi-densepose-wasm` (depends on mat)
11. `wifi-densepose-sensing-server` (depends on wifiscan)
12. `wifi-densepose-cli` (depends on mat)

### Validation & Witness Verification (ADR-028)

**After any significant code change, run the full validation:**

```bash
# 1. Rust tests — must be 1,031+ passed, 0 failed
cd v2
cargo test --workspace --no-default-features

# 2. Python proof — must print VERDICT: PASS
cd ..
python archive/v1/data/proof/verify.py

# 3. Generate witness bundle (includes both above + firmware hashes)
bash scripts/generate-witness-bundle.sh

# 4. Self-verify the bundle — must be 7/7 PASS
cd dist/witness-bundle-ADR028-*/
bash VERIFY.sh
```

**If the Python proof hash changes** (e.g., numpy/scipy version update):
```bash
# Regenerate the expected hash, then verify it passes
python archive/v1/data/proof/verify.py --generate-hash
python archive/v1/data/proof/verify.py
```

**Witness bundle contents** (`dist/witness-bundle-ADR028-<sha>.tar.gz`):
- `WITNESS-LOG-028.md` — 33-row attestation matrix with evidence per capability
- `ADR-028-esp32-capability-audit.md` — Full audit findings
- `proof/verify.py` + `expected_features.sha256` — Deterministic pipeline proof
- `test-results/rust-workspace-tests.log` — Full cargo test output
- `firmware-manifest/source-hashes.txt` — SHA-256 of all 7 ESP32 firmware files
- `crate-manifest/versions.txt` — All 15 crates with versions
- `VERIFY.sh` — One-command self-verification for recipients

**Key proof artifacts:**
- `archive/v1/data/proof/verify.py` — Trust Kill Switch: feeds reference signal through production pipeline, hashes output
- `archive/v1/data/proof/expected_features.sha256` — Published expected hash
- `archive/v1/data/proof/sample_csi_data.json` — 1,000 synthetic CSI frames (seed=42)
- `docs/WITNESS-LOG-028.md` — 11-step reproducible verification procedure
- `docs/adr/ADR-028-esp32-capability-audit.md` — Complete audit record

### Branch
Default branch: `main`
Active feature branch: `ruvsense-full-implementation` (PR #77)

---

## Behavioral Rules (Always Enforced)

- Do what has been asked; nothing more, nothing less
- NEVER create files unless they're absolutely necessary for achieving your goal
- ALWAYS prefer editing an existing file to creating a new one
- NEVER proactively create documentation files (*.md) or README files unless explicitly requested
- NEVER save working files, text/mds, or tests to the root folder
- Never continuously check status after spawning a swarm — wait for results
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files

## File Organization

- NEVER save to root folder — use the directories below
- `docs/adr/` — Architecture Decision Records (43 ADRs)
- `docs/ddd/` — Domain-Driven Design models
- `v2/crates/` — Rust workspace crates (15 crates)
- `v2/crates/wifi-densepose-signal/src/ruvsense/` — RuvSense multistatic modules (14 files)
- `v2/crates/wifi-densepose-ruvector/src/viewpoint/` — Cross-viewpoint fusion (5 files)
- `v2/crates/wifi-densepose-hardware/src/esp32/` — ESP32 TDM protocol
- `firmware/esp32-csi-node/main/` — ESP32 C firmware (channel hopping, NVS config, TDM)
- `archive/v1/src/` — Python source (core, hardware, services, api)
- `archive/v1/data/proof/` — Deterministic CSI proof bundles
- `.claude-flow/` — Claude Flow coordination state (committed for team sharing)
- `.claude/` — Claude Code settings, agents, memory (committed for team sharing)

## Project Architecture

- Follow Domain-Driven Design with bounded contexts
- Keep files under 500 lines
- Use typed interfaces for all public APIs
- Prefer TDD London School (mock-first) for new code
- Use event sourcing for state changes
- Ensure input validation at system boundaries

### Project Config

- **Topology**: hierarchical-mesh
- **Max Agents**: 15
- **Memory**: hybrid
- **HNSW**: Enabled
- **Neural**: Enabled

## Pre-Merge Checklist

Before merging any PR, verify each item applies and is addressed:

1. **Rust tests pass** — `cargo test --workspace --no-default-features` (1,031+ passed, 0 failed)
2. **Python proof passes** — `python archive/v1/data/proof/verify.py` (VERDICT: PASS)
3. **README.md** — Update platform tables, crate descriptions, hardware tables, feature summaries if scope changed
4. **CLAUDE.md** — Update crate table, ADR list, module tables, version if scope changed
5. **CHANGELOG.md** — Add entry under `[Unreleased]` with what was added/fixed/changed
6. **User guide** (`docs/user-guide.md`) — Update if new data sources, CLI flags, or setup steps were added
7. **ADR index** — Update ADR count in README docs table if a new ADR was created
8. **Witness bundle** — Regenerate if tests or proof hash changed: `bash scripts/generate-witness-bundle.sh`
9. **Docker Hub image** — Only rebuild if Dockerfile, dependencies, or runtime behavior changed
10. **Crate publishing** — Only needed if a crate is published to crates.io and its public API changed
11. **`.gitignore`** — Add any new build artifacts or binaries
12. **Security audit** — Run security review for new modules touching hardware/network boundaries

## Build & Test

```bash
# Build
npm run build

# Test
npm test

# Lint
npm run lint
```

- ALWAYS run tests after making code changes
- ALWAYS verify build succeeds before committing

## Security Rules

- NEVER hardcode API keys, secrets, or credentials in source files
- NEVER commit .env files or any file containing secrets
- Always validate user input at system boundaries
- Always sanitize file paths to prevent directory traversal
- Run `npx @claude-flow/cli@latest security scan` after security-related changes

## Concurrency: 1 MESSAGE = ALL RELATED OPERATIONS

- All operations MUST be concurrent/parallel in a single message
- Use Claude Code's Task tool for spawning agents, not just MCP
- ALWAYS batch ALL todos in ONE TodoWrite call (5-10+ minimum)
- ALWAYS spawn ALL agents in ONE message with full instructions via Task tool
- ALWAYS batch ALL file reads/writes/edits in ONE message
- ALWAYS batch ALL Bash commands in ONE message

## Swarm Orchestration

- MUST initialize the swarm using CLI tools when starting complex tasks
- MUST spawn concurrent agents using Claude Code's Task tool
- Never use CLI tools alone for execution — Task tool agents do the actual work
- MUST call CLI tools AND Task tool in ONE message for complex work

### 3-Tier Model Routing (ADR-026)

| Tier | Handler | Latency | Cost | Use Cases |
|------|---------|---------|------|-----------|
| **1** | Agent Booster (WASM) | <1ms | $0 | Simple transforms (var→const, add types) — Skip LLM |
| **2** | Haiku | ~500ms | $0.0002 | Simple tasks, low complexity (<30%) |
| **3** | Sonnet/Opus | 2-5s | $0.003-0.015 | Complex reasoning, architecture, security (>30%) |

- Always check for `[AGENT_BOOSTER_AVAILABLE]` or `[TASK_MODEL_RECOMMENDATION]` before spawning agents
- Use Edit tool directly when `[AGENT_BOOSTER_AVAILABLE]`

## Swarm Configuration & Anti-Drift

- ALWAYS use hierarchical topology for coding swarms
- Keep maxAgents at 6-8 for tight coordination
- Use specialized strategy for clear role boundaries
- Use `raft` consensus for hive-mind (leader maintains authoritative state)
- Run frequent checkpoints via `post-task` hooks
- Keep shared memory namespace for all agents

```bash
npx @claude-flow/cli@latest swarm init --topology hierarchical --max-agents 8 --strategy specialized
```

## Swarm Execution Rules

- ALWAYS use `run_in_background: true` for all agent Task calls
- ALWAYS put ALL agent Task calls in ONE message for parallel execution
- After spawning, STOP — do NOT add more tool calls or check status
- Never poll TaskOutput or check swarm status — trust agents to return
- When agent results arrive, review ALL results before proceeding

## V3 CLI Commands

### Core Commands

| Command | Subcommands | Description |
|---------|-------------|-------------|
| `init` | 4 | Project initialization |
| `agent` | 8 | Agent lifecycle management |
| `swarm` | 6 | Multi-agent swarm coordination |
| `memory` | 11 | AgentDB memory with HNSW search |
| `task` | 6 | Task creation and lifecycle |
| `session` | 7 | Session state management |
| `hooks` | 17 | Self-learning hooks + 12 workers |
| `hive-mind` | 6 | Byzantine fault-tolerant consensus |

### Quick CLI Examples

```bash
npx @claude-flow/cli@latest init --wizard
npx @claude-flow/cli@latest agent spawn -t coder --name my-coder
npx @claude-flow/cli@latest swarm init --v3-mode
npx @claude-flow/cli@latest memory search --query "authentication patterns"
npx @claude-flow/cli@latest doctor --fix
```

## Available Agents (60+ Types)

### Core Development
`coder`, `reviewer`, `tester`, `planner`, `researcher`

### Specialized
`security-architect`, `security-auditor`, `memory-specialist`, `performance-engineer`

### Swarm Coordination
`hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`

### GitHub & Repository
`pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

### SPARC Methodology
`sparc-coord`, `sparc-coder`, `specification`, `pseudocode`, `architecture`

## Memory Commands Reference

```bash
# Store (REQUIRED: --key, --value; OPTIONAL: --namespace, --ttl, --tags)
npx @claude-flow/cli@latest memory store --key "pattern-auth" --value "JWT with refresh" --namespace patterns

# Search (REQUIRED: --query; OPTIONAL: --namespace, --limit, --threshold)
npx @claude-flow/cli@latest memory search --query "authentication patterns"

# List (OPTIONAL: --namespace, --limit)
npx @claude-flow/cli@latest memory list --namespace patterns --limit 10

# Retrieve (REQUIRED: --key; OPTIONAL: --namespace)
npx @claude-flow/cli@latest memory retrieve --key "pattern-auth" --namespace patterns
```

## Quick Setup

```bash
claude mcp add claude-flow -- npx -y @claude-flow/cli@latest
npx @claude-flow/cli@latest daemon start
npx @claude-flow/cli@latest doctor --fix
```

## Claude Code vs CLI Tools

- Claude Code's Task tool handles ALL execution: agents, file ops, code generation, git
- CLI tools handle coordination via Bash: swarm init, memory, hooks, routing
- NEVER use CLI tools as a substitute for Task tool agents

## Support

- Documentation: https://github.com/ruvnet/claude-flow
- Issues: https://github.com/ruvnet/claude-flow/issues


===== FILE OpenHands/OpenHands::AGENTS.md | stars=82046 followers=None lang=Python bytes=28095 =====

This repository contains the code for OpenHands, an automated AI software engineer. It has a Python backend
(in the `openhands` directory) and React frontend (in the `frontend` directory).

## General Setup:
To set up the entire repo, including frontend and backend, run `make build`.
You don't need to do this unless the user asks you to, or if you're trying to run the entire application.

## Running OpenHands with OpenHands:
To run the full application to debug issues:
```bash
export INSTALL_DOCKER=0
export RUNTIME=local
make build && make run FRONTEND_PORT=12000 FRONTEND_HOST=0.0.0.0 BACKEND_HOST=0.0.0.0 &> /tmp/openhands-log.txt &
```

Local run troubleshooting notes:
- If the backend fails with `nc: command not found`, install `netcat-openbsd`.
- If local runtime startup fails with `duplicate session: test-session`, clear the stale tmux session on the default socket: `tmux -S /tmp/tmux-$(id -u)/default kill-session -t test-session`.
- Local runtime browser startup expects Playwright browsers under `~/.cache/playwright`; if needed run `PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/playwright poetry run playwright install chromium`.
- In this sandbox environment, an inherited `SESSION_API_KEY` can make `/api/v1/settings` return 401 in the browser. Unset it before `make run` when you want to use the local web UI directly.
- In this sandbox, `frontend`'s `npm run dev:mock` / `dev:mock:saas` can start but still be awkward to browse through the work-host proxy. For PR QA screenshots, a reliable fallback is to `npm run build` with the desired `VITE_MOCK_*` env, then serve `build/` with a tiny custom HTTP server that returns the minimal mock JSON endpoints needed by the settings page.


IMPORTANT: Before making any changes to the codebase, ALWAYS run `make install-pre-commit-hooks` to ensure pre-commit hooks are properly installed.

Before pushing any changes, you MUST ensure that any lint errors or simple test errors have been fixed.

* If you've made changes to the backend, you should run `pre-commit run --config ./dev_config/python/.pre-commit-config.yaml` (this will run on staged files).
* If you've made changes to the frontend, you should run `cd frontend && npm run lint:fix && npm run build ; cd ..`
* If you've made changes to the VSCode extension, you should run `cd openhands/app_server/integrations/vscode && npm run lint:fix && npm run compile ; cd ../../..`

The pre-commit hooks MUST pass successfully before pushing any changes to the repository. This is a mandatory requirement to maintain code quality and consistency.

If either command fails, it may have automatically fixed some issues. You should fix any issues that weren't automatically fixed,
then re-run the command to ensure it passes. Common issues include:
- Mypy type errors
- Ruff formatting issues
- Trailing whitespace
- Missing newlines at end of files

## Git Best Practices

- Prefer specific `git add <filename>` instead of `git add .` to avoid accidentally staging unintended files
- Be especially careful with `git reset --hard` after staging files, as it will remove accidentally staged files
- When remote has new changes, use `git fetch upstream && git rebase upstream/<branch>` on the same branch

## GitHub Actions

- Pin external third-party actions to a full 40-character commit SHA, with the version tag in a trailing comment (e.g. `uses: owner/repo@<sha> # v1.2.3`). Do not use mutable tags (`@v1`) or branches for third-party actions.
- GitHub-authored (`actions/*`, `github/*`) and first-party (`OpenHands/*`) actions are currently exempt.
- Dependabot's `github-actions` ecosystem bumps the pinned SHA and the trailing comment under the configured cooldown, so pinning does not block security or version updates.

## Lockfile Regeneration (Preserve Original Tool Versions)

When regenerating lockfiles (poetry.lock, uv.lock, etc.), you MUST use the same tool version that originally generated the lockfile to avoid unnecessary diff noise. Each lockfile contains a version header indicating which tool version was used.

### Poetry (poetry.lock)

1. Extract the version from the lockfile header:
   ```bash
   POETRY_VERSION=$(grep -m1 "^# This file is automatically @generated by Poetry" poetry.lock | sed 's/.*Poetry \([0-9.]*\).*/\1/')
   ```
2. If a version is found, install that specific version:
   ```bash
   pipx install poetry==$POETRY_VERSION --force
   ```
3. Then regenerate the lockfile:
   ```bash
   poetry lock --no-update
   ```

### uv (uv.lock)

1. Extract the version from the lockfile header:
   ```bash
   UV_VERSION=$(grep -m1 "^# This file was autogenerated by uv" uv.lock | sed 's/.*uv version \([0-9.]*\).*/\1/')
   ```
2. If a version is found, install that specific version:
   ```bash
   pipx install uv==$UV_VERSION --force
   ```
3. Then regenerate the lockfile:
   ```bash
   uv lock
   ```

This ensures that lockfile updates only contain actual dependency changes, not tool version migration artifacts.

## PR-Specific Artifacts (`.pr/` directory)

When working on a PR that requires design documents, scripts meant for development-only, or other temporary artifacts that should NOT be merged to main, store them in a `.pr/` directory at the repository root.

### Usage

```
.pr/
├── design.md       # Design decisions and architecture notes
├── analysis.md     # Investigation or debugging notes
├── logs/           # Test output or CI logs for reviewer reference
└── notes.md        # Any other PR-specific content
```

### How It Works

1. **Notification**: When `.pr/` exists, a comment is posted to the PR conversation alerting reviewers
2. **Auto-cleanup**: When the PR is approved, the `.pr/` directory is automatically removed via `.github/workflows/pr-artifacts.yml`
3. **Fork PRs**: Auto-cleanup cannot push to forks, so manual removal is required before merging

### Important Notes

- Do NOT put anything in `.pr/` that needs to be preserved after merge
- The `.pr/` check passes (green ✅) during development — it only posts a notification, not a blocking error
- For fork PRs: You must manually remove `.pr/` before the PR can be merged

### When to Use

- Complex refactoring that benefits from written design rationale
- Debugging sessions where you want to document your investigation
- E2E test results or logs that demonstrate a cross-repo feature works
- Feature implementations that need temporary planning docs
- Any analysis that helps reviewers understand the PR but isn't needed long-term

## Repository Structure
Backend:
- Located in the `openhands` directory
- The current V1 application server lives in `openhands/app_server/`. `make start-backend` still launches `openhands.server.listen:app`, which includes the V1 routes by default unless `ENABLE_V1=0`.
- For V1 web-app docs, LLM setup should point users to the Settings UI.
- Testing:
  - All tests are in `tests/unit/test_*.py`
  - To test new code, run `poetry run pytest tests/unit/test_xxx.py` where `xxx` is the appropriate file for the current functionality
  - Write all tests with pytest
  - Enterprise unit tests live under `enterprise/tests`; run them with `PYTHONPATH=enterprise poetry run pytest enterprise/tests/unit/test_xxx.py`


Frontend:
- Located in the `frontend` directory
- UI refactors: Budgets UI is split into `budgets.tsx` + `budgets-tabs.tsx`, `budgets-components.tsx`, `budgets-constants.ts`. Usage monitoring dashboard is split into `usage-dashboard.tsx` with `usage-dashboard-tabs.tsx`, `usage-dashboard-widgets.tsx`, and `usage-dashboard-utils.ts`. Shared inline SVGs live in `frontend/src/components/shared/icons/inline-icons.tsx`.

- Prerequisites: A recent version of NodeJS / NPM
- Setup: Run `npm install` in the frontend directory
- Testing:
  - Run tests: `npm run test`
  - To run specific tests: `npm run test -- -t "TestName"`
  - Our test framework is vitest
- Building:
  - Build for production: `npm run build`
- Environment Variables:
  - Set in `frontend/.env` or as environment variables
  - Available variables: VITE_BACKEND_HOST, VITE_USE_TLS, VITE_INSECURE_SKIP_VERIFY, VITE_FRONTEND_PORT
- Internationalization:
  - Generate i18n declaration file: `npm run make-i18n`
- Data Fetching & Cache Management:
  - We use TanStack Query (fka React Query) for data fetching and cache management
  - Data Access Layer: API client methods are located in `frontend/src/api` and should never be called directly from UI components - they must always be wrapped with TanStack Query
  - Custom hooks are located in `frontend/src/hooks/query/` and `frontend/src/hooks/mutation/`
  - Query hooks should follow the pattern use[Resource] (e.g., `useConversationSkills`)
  - Mutation hooks should follow the pattern use[Action] (e.g., `useDeleteConversation`)
  - Architecture rule: UI components → TanStack Query hooks → Data Access Layer (`frontend/src/api`) → API endpoints
  - For SaaS organization management screens, prefer deriving the selected organization from `useOrganizations()` plus the selected org ID store instead of adding a dedicated single-org fetch when only list-level fields (for example `name`) are needed.


VSCode Extension:
- Located in the `openhands/app_server/integrations/vscode` directory
- Setup: Run `npm install` in the extension directory
- Linting:
  - Run linting with fixes: `npm run lint:fix`
  - Check only: `npm run lint`
  - Type checking: `npm run typecheck`
- Building:
  - Compile TypeScript: `npm run compile`
  - Package extension: `npm run package-vsix`
- Testing:
  - Run tests: `npm run test`
- Development Best Practices:
  - Use `vscode.window.createOutputChannel()` for debug logging instead of `showErrorMessage()` popups
  - Pre-commit process runs both frontend and backend checks when committing extension changes

## Enterprise Directory

The `enterprise/` directory contains additional functionality that extends the open-source OpenHands codebase. This includes:
- Authentication and user management (Keycloak integration)
- Database migrations (Alembic)
- Integration services (GitHub, GitLab, Jira, Linear, Slack)
- Email services: Resend remains in `enterprise/server/services/email_service.py`; SMTPEmailService lives in
  `enterprise/server/services/smtp_email_service.py` and is used for org invitations/budget alerts plus
  the SMTP-driven UI email-enabled checks (SMTP_HOST).
- Billing and subscription management (Stripe)
- Telemetry and analytics (PostHog, custom metrics framework)
- Email services: Resend remains in `enterprise/server/services/email_service.py`; SMTPEmailService lives in
  `enterprise/server/services/smtp_email_service.py` and is used for org invitations/budget alerts plus
  the SMTP-driven UI email-enabled checks (SMTP_HOST).

### Enterprise Development Setup

**Prerequisites:**
- Python 3.12
- Poetry (for dependency management)
- Node.js 22.x (for frontend)
- Docker (optional)

**Setup Steps:**
1. First, build the main OpenHands project: `make build`
2. Then install enterprise dependencies: `cd enterprise && poetry install --with dev,test` (This can take a very long time. Be patient.)
3. Set up enterprise pre-commit hooks: `poetry run pre-commit install --config ./dev_config/python/.pre-commit-config.yaml`

**Running Enterprise Tests:**
```bash
# Enterprise unit tests (full suite)
PYTHONPATH=".:$PYTHONPATH" poetry run --project=enterprise pytest --forked -n auto -s -p no:ddtrace -p no:ddtrace.pytest_bdd -p no:ddtrace.pytest_benchmark ./enterprise/tests/unit --cov=enterprise --cov-branch

# Test specific modules (faster for development)
cd enterprise
PYTHONPATH=".:$PYTHONPATH" poetry run pytest tests/unit/telemetry/ --confcutdir=tests/unit/telemetry

# Enterprise linting (IMPORTANT: use --show-diff-on-failure to match GitHub CI)
poetry run pre-commit run --all-files --show-diff-on-failure --config ./dev_config/python/.pre-commit-config.yaml
```

**Running Enterprise Server:**
```bash
cd enterprise
make start-backend  # Development mode with hot reload
# or
make run  # Full application (backend + frontend)
```

**Key Configuration Files:**
- `enterprise/pyproject.toml` - Enterprise-specific dependencies
- `enterprise/Makefile` - Enterprise build and run commands
- `enterprise/dev_config/python/` - Linting and type checking configuration
- `enterprise/migrations/` - Database migration files

**Database Migrations:**
Enterprise uses Alembic for database migrations. When making schema changes:
1. Create migration files in `enterprise/migrations/versions/`
2. Test migrations thoroughly
3. The CI will check for migration conflicts on PRs

**Integration Development:**
The enterprise codebase includes integrations for:
- **GitHub** - PR management, webhooks, app installations
- **GitLab** - Similar to GitHub but for GitLab instances
- **Jira** - Issue tracking and project management
- **Linear** - Modern issue tracking
- **Slack** - Team communication and notifications

Each integration follows a consistent pattern with service classes, storage models, and API endpoints.

**Important Notes:**
- Enterprise code is licensed under Polyform Free Trial License (30-day limit)
- The enterprise server extends the OpenHands server through dynamic imports
- Database changes require careful migration planning in `enterprise/migrations/`
- Always test changes in both OpenHands and enterprise contexts
- Use the enterprise-specific Makefile commands for development
- When the `openhands-ai` package (root project) version has been updated, run `poetry lock` in the `enterprise/` folder to update the version in the enterprise poetry lockfile.

**Enterprise Testing Best Practices:**

**Database Testing:**
- Use SQLite in-memory databases (`sqlite:///:memory:`) for unit tests instead of real PostgreSQL
- Create module-specific `conftest.py` files with database fixtures
- Mock external database connections in unit tests to avoid dependency on running services
- Use real database connections only for integration tests

**Import Patterns:**
- Use relative imports without `enterprise.` prefix in enterprise code
- Example: `from storage.database import a_session_maker` not `from enterprise.storage.database import a_session_maker`
- This ensures code works in both OpenHands and enterprise contexts

**Test Structure:**
- Place tests in `enterprise/tests/unit/` following the same structure as the source code
- Use `--confcutdir=tests/unit/[module]` when testing specific modules
- Create comprehensive fixtures for complex objects (databases, external services)
- Write platform-agnostic tests (avoid hardcoded OS-specific assertions)

**Mocking Strategy:**
- Use `AsyncMock` for async operations and `MagicMock` for complex objects
- Mock all external dependencies (databases, APIs, file systems) in unit tests
- Use `patch` with correct import paths (e.g., `telemetry.registry.logger` not `enterprise.telemetry.registry.logger`)
- Test both success and failure scenarios with proper error handling

**Coverage Goals:**
- Aim for 90%+ test coverage on new enterprise modules
- Focus on critical business logic and error handling paths
- Use `--cov-report=term-missing` to identify uncovered lines

**Troubleshooting:**
- If tests fail, ensure all dependencies are installed: `poetry install --with dev,test`
- For database issues, check migration status and run migrations if needed
- For frontend issues, ensure the main OpenHands frontend is built: `make build`
- Check logs in the `logs/` directory for runtime issues
- If tests fail with import errors, verify `PYTHONPATH=".:$PYTHONPATH"` is set
- **If GitHub CI fails but local linting passes**: Always use `--show-diff-on-failure` flag to match CI behavior exactly

## Template for Github Pull Request

If you are starting a pull request (PR), please follow the template in `.github/pull_request_template.md`.
- The PR template now starts with a `HUMAN:` section, the human-tested checkbox, and an `AGENT:` section.
- `.github/workflows/pr-readiness-confirm.yml` checks non-draft PRs for non-empty text between `HUMAN:` and the human-tested checkbox; if present it adds a 👍 reaction, and if absent it posts a reminder comment.


## Implementation Details

These details may or may not be useful for your current task.

### Conversation State Management

#### Agent State and Sandbox Status:
The frontend uses `useAgentState` hook (`frontend/src/hooks/use-agent-state.ts`) to determine the current conversation state. This hook:
- Returns `curAgentState` (AgentState enum) for UI state determination
- Returns `isArchived` flag when `sandbox_status === "MISSING"` (archived conversations)
- Prioritizes live WebSocket execution status over cached API data

#### Archived Conversations (sandbox_status === "MISSING"):
When a conversation's sandbox is no longer available (archived):
- `useAgentState` returns `AgentState.STOPPED` and `isArchived: true`
- Chat input is replaced with an archived banner (`ArchivedBanner` component)
- VS Code tab, Terminal, and Planner show read-only messages instead of loading states
- All interactive elements that require a running sandbox are disabled

#### Testing useAgentState:
When mocking `useAgentState` in tests, always include the `isArchived` property:
```typescript
vi.mock("#/hooks/use-agent-state", () => ({
  useAgentState: () => ({
    curAgentState: AgentState.AWAITING_USER_INPUT,
    isArchived: false,
  }),
}));
```

### Microagents

Microagents are specialized prompts that enhance OpenHands with domain-specific knowledge and task-specific workflows. They are Markdown files that can include frontmatter for configuration.

#### Types:
- **Public Microagents**: Located in `microagents/`, available to all users
- **Repository Microagents**: Located in `.openhands/microagents/`, specific to this repository

#### Loading Behavior:
- **Without frontmatter**: Always loaded into LLM context
- **With triggers in frontmatter**: Only loaded when user's message matches the specified trigger keywords

#### Structure:
```yaml
---
triggers:
- keyword1
- keyword2
---
# Microagent Content
Your specialized knowledge and instructions here...
```

### Frontend

#### Action Handling:
- Actions are defined in `frontend/src/types/action-type.ts`
- The `HANDLED_ACTIONS` array in `frontend/src/state/chat-slice.ts` determines which actions are displayed as collapsible UI elements
- To add a new action type to the UI:
  1. Add the action type to the `HANDLED_ACTIONS` array
  2. Implement the action handling in `addAssistantAction` function in chat-slice.ts
  3. Add a translation key in the format `ACTION_MESSAGE$ACTION_NAME` to the i18n files
- Actions with `thought` property are displayed in the UI based on their action type:
  - Regular actions (like "run", "edit") display the thought as a separate message
  - Special actions (like "think") are displayed as collapsible elements only

#### Adding User Settings:
- To add a new user setting to OpenHands, follow these steps:
  1. Add the setting to the frontend:
     - Add the setting to the `Settings` type in `frontend/src/types/settings.ts`
     - Add the setting to the `ApiSettings` type in the same file
     - Add the setting with an appropriate default value to `DEFAULT_SETTINGS` in `frontend/src/services/settings.ts`
     - Update the `useSettings` hook in `frontend/src/hooks/query/use-settings.ts` to map the API response
     - Update the `useSaveSettings` hook in `frontend/src/hooks/mutation/use-save-settings.ts` to include the setting in API requests
     - Add UI components (like toggle switches) in the appropriate settings screen (e.g., `frontend/src/routes/app-settings.tsx`)
     - Add i18n translations for the setting name and any tooltips in `frontend/src/i18n/translation.json`
     - Add the translation key to `frontend/src/i18n/declaration.ts`
  2. Add the setting to the backend:
     - Add the setting to the `Settings` model in `openhands/app_server/settings/settings_models.py`
     - Update any relevant backend code to apply the setting (e.g., in session creation)

#### Settings UI Patterns:

There are two main patterns for saving settings in the OpenHands frontend:

**Pattern 1: Entity-based Resources (Immediate Save)**
- Used for: API Keys, Secrets, MCP Servers
- Behavior: Changes are saved immediately when user performs actions (add/edit/delete)
- Implementation:
  - No "Save Changes" button
  - No local state management or `isDirty` tracking
  - Uses dedicated mutation hooks for each operation (e.g., `use-add-mcp-server.ts`, `use-delete-mcp-server.ts`)
  - Each mutation triggers immediate API call with query invalidation for UI updates
  - Example: MCP settings, API Keys & Secrets tabs
- Benefits: Simpler UX, no risk of losing changes, consistent with modern web app patterns

**Pattern 2: Form-based Settings (Manual Save)**
- Used for: Application settings, LLM configuration
- Behavior: Changes are accumulated locally and saved when user clicks "Save Changes"
- Implementation:
  - Has "Save Changes" button that becomes enabled when changes are detected
  - Uses local state management with `isDirty` tracking
  - Uses `useSaveSettings` hook to save all changes at once
  - Example: LLM tab, Application tab
- Benefits: Allows bulk changes, explicit save action, can validate all fields before saving

**When to use each pattern:**
- Use Pattern 1 (Immediate Save) for entity management where each item is independent
- Use Pattern 2 (Manual Save) for configuration forms where settings are interdependent or need validation
- Git provider tokens in the local/OSS integrations settings are managed through the V1 secrets endpoints (`POST`/`DELETE /api/v1/secrets/git-providers`). Do not reuse the logout flow for disconnecting tokens; `useLogout` is for actual app logout and still targets legacy OSS logout behavior.

### Adding New LLM Models

To add a new LLM model to OpenHands, you need to update multiple files across both frontend and backend:

#### Model Configuration Procedure:

1. **Frontend Model Arrays** (`frontend/src/utils/verified-models.ts`):
   - Add the model to `VERIFIED_MODELS` array (main list of all verified models)
   - Add to provider-specific arrays based on the model's provider:
     - `VERIFIED_OPENAI_MODELS` for OpenAI models
     - `VERIFIED_ANTHROPIC_MODELS` for Anthropic models
     - `VERIFIED_MISTRAL_MODELS` for Mistral models
     - `VERIFIED_OPENHANDS_MODELS` for models available through OpenHands provider

2. **Backend CLI Integration** (`openhands/cli/utils.py`):
   - Add the model to the appropriate `VERIFIED_*_MODELS` arrays
   - This ensures the model appears in CLI model selection

3. **Backend Model List** (`openhands/utils/llm.py`):
   - **CRITICAL**: Add the model to the `openhands_models` list (lines 57-66) if using OpenHands provider
   - This is required for the model to appear in the frontend model selector
   - Format: `'openhands/model-name'` (e.g., `'openhands/o3'`)

4. **Backend LLM Configuration** (`openhands/llm/llm.py`):
   - Add to feature-specific arrays based on model capabilities:
     - `FUNCTION_CALLING_SUPPORTED_MODELS` if the model supports function calling
     - `REASONING_EFFORT_SUPPORTED_MODELS` if the model supports reasoning effort parameters
     - `CACHE_PROMPT_SUPPORTED_MODELS` if the model supports prompt caching
     - `MODELS_WITHOUT_STOP_WORDS` if the model doesn't support stop words

5. **Validation**:
   - Run backend linting: `pre-commit run --config ./dev_config/python/.pre-commit-config.yaml`
   - Run frontend linting: `cd frontend && npm run lint:fix`
   - Run frontend build: `cd frontend && npm run build`

#### Model Verification Arrays:

- **VERIFIED_MODELS**: Main array of all verified models shown in the UI
- **VERIFIED_OPENAI_MODELS**: OpenAI models (LiteLLM doesn't return provider prefix)
- **VERIFIED_ANTHROPIC_MODELS**: Anthropic models (LiteLLM doesn't return provider prefix)
- **VERIFIED_MISTRAL_MODELS**: Mistral models (LiteLLM doesn't return provider prefix)
- **VERIFIED_OPENHANDS_MODELS**: Models available through OpenHands managed provider

#### Model Feature Support Arrays:

- **FUNCTION_CALLING_SUPPORTED_MODELS**: Models that support structured function calling
- **REASONING_EFFORT_SUPPORTED_MODELS**: Models that support reasoning effort parameters (like o1, o3)
- **CACHE_PROMPT_SUPPORTED_MODELS**: Models that support prompt caching for efficiency
- **MODELS_WITHOUT_STOP_WORDS**: Models that don't support stop word parameters

#### Frontend Model Integration:

- Models are automatically available in the model selector UI once added to verified arrays
- The `extractModelAndProvider` utility automatically detects provider from model arrays
- Provider-specific models are grouped and prioritized in the UI selection

#### CLI Model Integration:

- Models appear in CLI provider selection based on the verified arrays
- The `organize_models_and_providers` function groups models by provider
- Default model selection prioritizes verified models for each provider

### Environment Variable Enable Toggles

When adding a new boolean enable toggle read from an environment variable (e.g. `FEATURE_ENABLED`, `SLACK_WEBHOOKS_ENABLED`), the check **must** accept both `'true'` and `'1'` as truthy values. Older Helm chart versions default to `'1'` rather than `'true'`, so accepting only one form silently disables the feature in those deployments.

**Required pattern:**
```python
os.getenv('MY_FEATURE_ENABLED', 'false').lower() in ('true', '1')
```

**Do not use:**
```python
os.getenv('MY_FEATURE_ENABLED', 'false').lower() == 'true'  # breaks when value is '1'
os.getenv('MY_FEATURE_ENABLED', 'false') == '1'             # breaks when value is 'true'
bool(os.getenv('MY_FEATURE_ENABLED'))                       # treats any non-empty string as True
```

This applies anywhere an env var gates a feature: backend config, web client config injectors, integration service initialization, etc. Add a unit test for the `'1'` case alongside the `'true'` case.

### Sandbox Settings API (SDK Credential Inheritance)

The sandbox settings API allows SDK-created conversations to inherit the user's SaaS credentials
(LLM config, secrets) securely via `LookupSecret`. Raw secret values only flow SaaS→sandbox,
never through the SDK client.

#### User Credentials with Exposed Secrets (in `openhands/app_server/user/user_router.py`):
- `GET /api/v1/users/me?expose_secrets=true` → Full user settings with unmasked secrets (e.g., `llm_api_key`)
- `GET /api/v1/users/me` → Full user settings (secrets masked, Bearer only)

Auth requirements for `expose_secrets=true`:
- Bearer token (proves user identity via `OPENHANDS_API_KEY`)
- `X-Session-API-Key` header (proves caller has an active sandbox owned by the authenticated user)

Called by `workspace.get_llm()` in the SDK to retrieve LLM config with the API key.

#### Sandbox-Scoped Secrets Endpoints (in `openhands/app_server/sandbox/sandbox_router.py`):
- `GET /sandboxes/{id}/settings/secrets` → list secret names (no values)
- `GET /sandboxes/{id}/settings/secrets/{name}` → raw secret value (called FROM sandbox)

#### Auth: `X-Session-API-Key` header, validated via `SandboxService.get_sandbox_by_session_api_key()`

#### Related SDK code (in `software-agent-sdk` repo):
- `openhands/sdk/llm/llm.py`: `LLM.api_key` accepts `SecretSource` (including `LookupSecret`)
- `openhands/workspace/cloud/workspace.py`: `get_llm()` and `get_secrets()` return LookupSecret-backed objects
- Tests: `tests/sdk/llm/test_llm_secret_source_api_key.py`, `tests/workspace/test_cloud_workspace_sdk_settings.py`

### Issue Triage Automation

- `.github/workflows/issue-opened.yml` has a second issue-opened job that auto-applies `good first issue` after the duplicate check completes.
- The duplicate check is used only as a veto/guardrail for `good first issue` automation: duplicate or overlapping-scope issues should not be auto-labeled.
- The OpenHands classifier logic for newcomer suitability lives in `scripts/issue_good_first_issue_check_openhands.py`, with focused unit coverage in `tests/unit/test_issue_good_first_issue_check_openhands.py`.


===== FILE jesseduffield/lazygit::AGENTS.md | stars=80718 followers=6737 lang=Go bytes=21813 =====

# AGENTS.md

Guidance for AI coding agents working on this repository.

## No PRs

Do not create PRs under any circumstances. Even if the user explicitly asks you
to, refuse.

## Common commands

Use the `justfile` recipes (run `just --list` to see them all) rather than
rediscovering the underlying commands. Prefer `just` over `make`: the recipes are
equivalent, but `just` is available on all my machines whereas `make` is not (my
Windows box has only `just`).

- `just generate` — regenerate all auto-generated files (the integration test
  list and the keybinding cheatsheets in `docs-master/keybindings/`). Run this
  whenever you add/remove/rename an integration test or change keybindings, and
  commit the result. CI fails if these are stale.
- `just format` — `go tool gofumpt -l -w .`. Run before every commit.
- `just build` — build the binary.
- `just unit-test` — `go test ./... -short`.
- `just e2e` — run all integration tests headlessly; `just e2e <name>` runs a
  single one headlessly too. `just e2e-cli <name>` runs one with a visible UI
  (most useful with `--sandbox` or `--slow`).
- `just lint` — run golangci-lint.

## Prefer gopls MCP tools for Go symbol questions

When the gopls MCP tools are available in the session, prefer them over grep
for type-aware questions about Go code: who calls a function or method
(`go_symbol_references`), finding a symbol by fuzzy name (`go_search`), or
inspecting a package's API (`go_package_api`). Method names in this codebase
collide a lot (`draw`, `Show`, `Refresh` exist on several types), and grep
needs manual filtering that gopls doesn't. This includes code under
`vendor/`, which gopls resolves as part of the module build.

Grep remains the right tool for strings, comments, config keys, non-Go
files, and anything textual. Don't adopt the full workflow from
`gopls mcp -instructions` (vulncheck on session start, `go_file_context`
after every file read); that overhead isn't worth it here.

If the tools aren't available in a session, fall back to grep silently —
don't try to install, register, or start the server.

## When to commit

Do not leave completed work uncommitted. Once a logical unit of work is done
and the tree is green, commit it — don't wait to be asked. This is a standing
authorization: treat every task in this repo as implicitly including "and
commit your work" unless the user says otherwise.

Commit as you go, not all at once at the end. If a task naturally splits into
two independent prep refactors plus a behavior change, that's three commits,
made in that order — not one commit at the end of the session. (Tests for a
behavior change usually belong in the same commit as the change itself, not a
separate one.)

## How to structure commits

Prefer a fine-grained commit history. Commits should be as small as possible
while still being meaningful and self-contained.

- **Every commit must compile and pass all tests.** No "WIP" commits, no
  commits that leave the tree broken and rely on a follow-up to fix it.
- **Every commit must be `gofumpt`-formatted.** Run `just format` before
  committing.
- **Every commit must be lint-clean.** Run `just lint` before committing —
  don't introduce a lint warning in one commit and rely on a later commit
  (or the user) to clean it up.
- **Commit messages explain _why_, not _what_.** The diff already shows what
  changed; the message should capture the motivation, the constraint, or the
  bug being fixed. If the reason is obvious from a one-line subject, no body
  is needed — but never paraphrase the diff.
- **Separate preparatory refactorings from behavior changes.** If a fix or
  feature is easier to review after a refactor, land the refactor in its own
  commit first. Pure refactors should be behavior-preserving; the commit that
  changes behavior should be as small as possible. This applies even when the
  refactor only becomes apparent _while_ writing the behavior change — e.g. you
  extract a helper to avoid duplication. Don't let "I discovered it mid-change"
  excuse bundling it in. Before committing, review your diff and split out any
  hunk that is behavior-preserving (an extraction, a rename, a move) into a
  preceding commit, by staging hunks or resetting and recommitting in order.
- **Do not use conventional commits** (no `feat:`/`fix:`/`chore:` prefixes).
  Match the plain English imperative style of the existing history.
- **Wrap message body to 72 characters**. The subject is allowed to go up to 80
  characters, or even a little more if needed to convey a good single-line
  summary; the body should be wrapped at 72 exactly, no more, no less.

## Iterate with `fixup!` commits

When refining work that's already committed — adjusting an approach,
incorporating an idea from elsewhere, fixing something that belongs to the
same logical unit — create a fixup against the target commit
(`git commit --fixup=<sha>`) so it sits alongside its target, ready for the
user to fold in later with `git rebase --autosquash`. Don't pile follow-up
commits on top with the intent of squashing them later.

This holds **even when the target is the most recent commit (HEAD)**: use
`git commit --fixup`, not `git commit --amend`. A direct `--amend`
produces the same end state, which makes it tempting, but the point of a
fixup isn't only clean autosquash — it's that the refinement lands as a
separate, reviewable commit that the user decides when to fold in. A bare
`--amend` rewrites the commit on the spot and skips that checkpoint. Don't
treat "I'm only touching the tip commit" as an exception.

If the changes don't map cleanly onto existing commits — say they cut
across several of them, or restructure something at a different layer
than any existing commit naturally owns — stop and ask the user how to
proceed. Resetting the branch and redoing the work is sometimes the right
call, but it's the user's call to make.

After writing a fixup, re-read the target commit's message. If anything in
that message has become inaccurate or misleading because of the fixup, use
an `amend!` commit instead. The safest way to create one is
`git commit --fixup=amend:<sha>`, which opens the editor prefilled with the
target's existing message for you to revise.

An `amend!` commit's message has this exact shape:

```
amend! <original subject>

<new subject>

<new body>
```

The first line (`amend! <original subject>`) is **only the matcher** that
ties the commit to its target — it must equal the target's current subject.
Everything after the blank line is the **complete replacement message**, so
it must begin with a subject line of its own. Even when you only mean to
change the body, you still repeat the (unchanged) subject as that first line.

This is the trap when writing the message by hand with `-m` instead of using
the prefilled editor: if you pass only the body, there is no replacement
subject line, so after autosquash the target loses its subject and the first
body paragraph silently gets promoted to the subject. By hand it must be
`-m "amend! <subject>" -m "<subject>" -m "<body>"` — note the subject appears
twice, once in the matcher and once as the start of the replacement message.

A plain `fixup!` keeps the original message verbatim, so message drift stays
in unless you explicitly correct it.

**Never squash the fixups yourself.** Leave them in the history as separate
commits. Do not run `git rebase --autosquash`, do not `git commit --amend`
them into their targets, do not reorder or otherwise collapse them — not as
a "finishing" step, not to tidy up before handing off, not because the tree
looks messy. The whole point of a fixup is that the iteration stays
**visible and reviewable**; squashing it away yourself destroys exactly the
artifact it exists to create. Collapsing fixups into their targets is the
user's action, taken once they've reviewed the iterations. Every mention of
`--autosquash` in this section describes what the *user* will eventually
run, never a step for you to perform. If you think the history is ready to
collapse, say so and leave it to them.

The same commit-structure rules apply to `fixup!` and `amend!` commits as
to regular ones: each must be a self-contained logical unit, and unrelated
changes must not be combined just because they happen to target the same
commit. If you have two independent refinements for the same target, make
two separate fixups. Reviewability of the intermediate state matters even
when the end state after autosquash would be identical.

## Surface mid-implementation decisions; decide them together

Planning can't anticipate everything. When a decision surfaces while you're
implementing — a design choice, a tradeoff, a scope cut, a "this turned out
harder than expected, so maybe X" — don't quietly make the call and keep
going, even if you have a clear recommendation and even if the call seems
small. Stop, lay out the options and your recommendation, and let me weigh in.
I want to make these calls _with_ you, not discover them after the fact in the
diff.

This isn't a request to stop and ask about every trivial detail; obvious
mechanical choices with one sensible answer don't need a checkpoint. It's about
genuine forks — the ones where a reasonable person might pick differently, or
where you'd be trading away something the plan assumed (scope, UX, performance,
reload behavior, …). When in doubt, surface it.

This applies with equal force to unforeseen _discoveries_, not just to
decisions you set out to make. If you find something the plan didn't account
for — a latent bug, a race, a wrong assumption, a case that turns out
unhandled — stop and raise it before designing or writing a fix, even when the
fix seems obvious and even when it's "just correctness." Finding the problem is
itself the fork: whether to fix it here or in a separate change, how generally
to solve it, and whether it reshapes the current work are all calls for me to
make with you. Don't quietly fold a self-directed fix for a newly-found problem
into the branch and let me discover it in the diff.

## Prefer the cleaner design over the smaller diff

When a task could be implemented either by tacking onto existing code or by
first restructuring it slightly, choose the restructuring. "Minimal change" is
not a goal in itself; a readable final state is. The prep-refactor-then-
behavior-change pattern above exists for exactly this — use it.

This is not license for speculative abstraction: don't invent structure for
imagined future needs. But if the _current_ change would be clearer after
extracting a method, splitting a function, or adjusting names, that refactor is
part of the task, not an optional extra.

If you catch yourself thinking any of these, stop and refactor first:

- "This does a bit of wasted work, but it's harmless."
- "I'll just add the new behavior alongside the old."
- "The existing method does more than I need, but calling it is fine."

## Demonstrating bugs before fixing them

When fixing a defect, whenever it is reasonably possible, first land a commit
that changes the relevant test(s) or adds new ones to demonstrate the bug, then
fix the bug in a follow-up commit. This gives reviewers (and `git bisect`) a
clear before/after and proves the test actually exercises the broken code path.

Use the `EXPECTED` / `ACTUAL` pattern in the bug-demonstrating commit. The test
asserts the current (wrong) behavior so it passes on the broken code, with the
correct expectation preserved inline as a comment. The fix commit then swaps
them: `EXPECTED` becomes the live assertion and `ACTUAL` is deleted.

This pattern works in both integration tests and unit tests. Example shape:

```go
/* EXPECTED:
expectClipboard(t, Equals(worktreeDir+"/dir/file1"))
ACTUAL: */
expectClipboard(t, Equals(filepath.Dir(worktreeDir)+"/repo/dir/file1"))
```

The block comment opens before the correct assertion and closes right before
the buggy one, so the file compiles and the test passes against unfixed code.
In the fix commit, remove the comment markers and delete the `ACTUAL` line.
Don't explain the pattern in commit messages.

The fix commit must be _exactly_ "delete the markers and delete the `ACTUAL`
line" — no other edits. That means `EXPECTED` and `ACTUAL` have to be drop-in
replacements for each other at the same syntactic position. If you can't write
them that way (e.g. one is `.IsEmpty()` and the other is `.Lines(...)`),
restructure the surrounding code until you can — usually by putting the
comment block between two adjacent chained calls, so both forms are just the
next method in the chain:

```go
t.Views().Files().
    Focus().
    /* EXPECTED:
    IsEmpty()
    ACTUAL: */
    Lines(
        Equals("D  file03.txt"),
    )
```

If you find yourself reaching for a local variable so that both forms can be
expressed against the same receiver, the structure isn't right yet — go back
and fix it instead of papering over it with a binding.

Use this pattern only where it makes sense; don't apply it by default.

## Unify duplicated logic before you change it

When a fix or feature would land in logic that's duplicated across two or more
call sites, don't patch one copy and move on — that's how the copies silently
drift. (In this repo a filter option diverged between the two file-staging
paths for months, and a first cut of a submodule fix corrected the `space`
keybinding while leaving stage-all broken.) Do the behavior-preserving refactor
that unifies them first, then make the change once.

Keep that refactor at the foundation of the branch, before the change. Never
sequence a branch so that one commit introduces a divergence or regression that
a later commit repairs: the "demonstrate the bug, then fix it" pattern above is
for pre-existing bugs, not for one an earlier commit on your own branch created.
Follow this even when the need for the refactor is only discovered in the middle
of working on the branch; suggest to the user to rewrite the history to move the
refactor to an earlier commit (but don't do it without asking first).

## Don't read model state right after a `Refresh`

A `Refresh` (or `RefreshFromWorker`) does its git work on a worker and then
*enqueues* the model update onto the UI thread. So when `Refresh` returns, the
model is **not** updated yet — the write is still queued. Reading a field
synchronously right after refreshing its scope reads the stale, pre-refresh
value (and this is true even for SYNC refreshes):

```go
self.c.Refresh(types.RefreshOptions{Scope: []types.RefreshableView{types.FILES}})
files := self.c.Model().Files // BUG: still the pre-refresh value
```

Put the read in `RefreshOptions.Then` instead — it's queued after the scope's
model writes, so it sees the fresh value:

```go
self.c.Refresh(types.RefreshOptions{
    Scope: []types.RefreshableView{types.FILES},
    Then: func() error {
        files := self.c.Model().Files // fresh
        return nil
    },
})
```

`Then` is a `func() error` and works with any non-`ASYNC` mode.

## Integration test conventions

Don't bind views to local variables. Always chain method calls directly from
`t.Views().<View>()`. Patterns like `filesView := t.Views().Files().Focus()`
followed by `filesView.Lines(...)` are not how tests in this repo are written;
keep the call site fluent.

## Use stretchr/testify for assertions

Prefer `assert.Equal` (and friends) over hand-rolled `if` checks. The failure
messages are more useful and the intent is clearer at a glance.

## Translatable strings use Go templates, not `%s`

Never put `fmt.Sprintf`-style placeholders (`%s`, `%d`, …) in translatable
strings — the fields of `TranslationSet` and `Actions` in
`pkg/i18n/english.go`. Use named Go-template placeholders and fill them in with
`utils.ResolvePlaceholderString`:

```go
// in english.go
DeleteBranchTitle: "Delete branch '{{.selectedBranchName}}'?",

// at the call site
utils.ResolvePlaceholderString(
    self.c.Tr.DeleteBranchTitle,
    map[string]string{"selectedBranchName": branchName},
)
```

Named placeholders tell localizers what each value is (a bare `%s` says
nothing, and translators can't safely reorder positional verbs across
languages), and the map form extends cleanly when a string later needs more
than one placeholder. This holds for every user-facing string, including short
ones like disabled-action reasons and toasts.

## Only edit the English translations

`pkg/i18n/english.go` is the one translation file you edit; add, change, and
remove strings there. The other languages under `pkg/i18n/translations/` are
maintained by Crowdin and synced automatically — never edit them by hand, not
even to add a key you just introduced or to delete one you just removed. A
removed English string simply leaves an orphan key in those files, which
Crowdin cleans up on its own; an unknown key in a translation file is ignored
at load time, so it does no harm in the meantime.

## Try to keep new english.go strings within the existing column alignment

`gofumpt` aligns the `TranslationSet` struct fields and the `EnglishTranslationSet`
literal into columns, so a new field whose name is longer than the widest one in
its alignment block re-indents every line in that block. When there are several
feature branches in flight that all add strings, that reformatting churn turns
english.go into a rebase-conflict magnet. So when it's cheap to do so, make an
effort to keep a new field name within the current widest name in the block
(measure it; it's around 40 characters today), shortening the Go field name to
fit. This is a soft preference, not a rule: the usual "best name wins" still
applies, so don't mangle a name past the point of readability just to save a
column. Applies only to `pkg/i18n/english.go`.

## Code comments are for future readers, not development history

Comments in source code explain *why this code is shaped the way it is*. They
are not the place to narrate the path we took during development — what was
tried first, what didn't work, what's "more reliable" or "cleaner" than some
alternative. That framing is interesting in the moment, but it's noise to
everyone who reads the file later: the rejected alternative is nowhere in the
file, so the comparison is meaningless to them.

Avoid phrasings like:

- "more reliable than triggering one manually"
- "cleaner than the previous approach"
- "we used to ... but ..."
- "after trying X, we found Y"

The iteration story is sometimes worth preserving — but it belongs in the
commit message, which is the durable record of *why this change was made*. The
code comment should make sense to someone who has never seen any prior version
and is just trying to understand the file as it currently exists.

## Don't present "live with the bug" as an option

When you're investigating a defect and laying out fix options for the user,
"accept the race / leave it as-is / document it and move on" is not one of
them. A known race condition, data corruption, or correctness violation is a
bug that needs a real fix, not a tradeoff. Even if the failure rate is low,
even if the window is tiny, even if no current code path appears to hit it —
present actual fixes. If a real fix is genuinely out of reach (e.g. it
requires API changes you can't make), say so plainly; don't dress "no fix"
up as a viable option in a numbered list alongside real ones.

## Don't edit files under `docs/`

`docs/` is the documentation rendered on GitHub for the current _release_.
Users read it as the reference for the version they're running. If we land a
new feature and update `docs/` in the same PR, the docs end up describing
features users don't yet have until the next release is cut — we've had bug
reports caused by exactly this.

So:

- Document new features in `docs-master/` only. The release process
  (`scripts/update_docs_for_release.sh`) copies `docs-master/` to `docs/` at
  release time.
- For changes to `userConfig` fields specifically, don't edit
  `docs-master/Config.md` by hand either — the relevant section is
  auto-generated from the struct field doc comments. After editing the
  struct, run `just generate` and include the regenerated
  `docs-master/Config.md` (and `schema-master/config.json`) in your commit.
- Don't hard-wrap the doc comments on `userConfig` fields. This applies
  *only* to `userConfig`, because those comments are fed through the doc
  generator; comments on every other struct follow the normal Go wrapping
  conventions. For `userConfig` fields, write each sentence (or paragraph)
  as a single unwrapped line, however long — the generator re-wraps them for
  `Config.md` (see `wrapLine` in `pkg/jsonschema/generate_config_docs.go`).
  Manually wrapping a sentence across several `//` lines defeats this: the
  generator preserves your arbitrary breaks as hard line breaks and embeds
  `\n` at those points in the generated `schema-master/config.json`
  description. (Putting genuinely separate sentences on their own lines is
  fine; just don't split one sentence across lines.)

## Don't search outside the working tree

Never run `find` (or similar) from `/` or other paths outside the project. All
third-party code we use is vendored under `vendor/`, so dependency sources are
reachable from inside the working tree — search there instead of the host
filesystem.

## gocui is in-tree, not a dependency

The `gocui` TUI library is a fork maintained directly in this repo under
`pkg/gocui` — it's an ordinary package, not a Go module dependency. Don't look
for it in `go.mod`/`go.sum` or the module cache (`$GOMODCACHE`); it isn't
there. When you need to read or change gocui internals (the task manager, the
event loop, worker/UI-thread dispatch, view rendering), edit `pkg/gocui`
directly.


===== FILE rtk-ai/rtk::CLAUDE.md | stars=73204 followers=None lang=Rust bytes=7704 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**rtk (Rust Token Killer)** is a high-performance CLI proxy that minimizes LLM token consumption by filtering and compressing command outputs. It reduces bash output by 60-90% on common development operations through smart filtering, grouping, truncation, and deduplication. All percentages in this repo measure bash output, not your bill. RTK ships no tokenizer (`src/core/tracking.rs` estimates tokens as `bytes / 4`), so the ratios are reliable but the absolute token counts are approximate.

This is a fork with critical fixes for git argument parsing and modern JavaScript stack support (pnpm, vitest, Next.js, TypeScript, Playwright, Prisma).

### Name Collision Warning

**Two different "rtk" projects exist:**
- This project: Rust Token Killer (rtk-ai/rtk)
- reachingforthejack/rtk: Rust Type Kit (DIFFERENT - generates Rust types)

**Verify correct installation:**
```bash
rtk --version  # Should show "rtk 0.28.2" (or newer)
rtk gain       # Should show token savings stats (NOT "command not found")
```

If `rtk gain` fails, you have the wrong package installed.

## Development Commands

> **Note**: If rtk is installed, prefer `rtk <cmd>` over raw commands for token-optimized output.
> All commands work with passthrough support even for subcommands rtk doesn't specifically handle.

### Build & Run
```bash
cargo build                   # raw
rtk cargo build               # preferred (token-optimized)
cargo build --release         # release build (optimized)
cargo run -- <command>        # run directly
cargo install --path .        # install locally
```

### Testing
```bash
cargo test                    # all tests
rtk cargo test                # preferred (token-optimized)
cargo test <test_name>        # specific test
cargo test <module_name>::    # module tests
cargo test -- --nocapture     # with stdout
bash scripts/test-all.sh      # smoke tests (installed binary required)
```

### Linting & Quality
```bash
cargo check                   # check without building
cargo fmt                     # format code
cargo clippy --all-targets    # all clippy lints
rtk cargo clippy --all-targets # preferred
```

### Pre-commit Gate
```bash
cargo fmt --all && cargo clippy --all-targets && cargo test --all
```

### Package Building
```bash
cargo deb                     # DEB package (needs cargo-deb)
cargo generate-rpm            # RPM package (needs cargo-generate-rpm, after release build)
```

## Architecture

rtk uses a **command proxy architecture**: `main.rs` routes CLI commands via a Clap `Commands` enum to specialized filter modules in `src/cmds/*/`, each of which executes the underlying command and compresses its output. Token savings are tracked in SQLite via `src/core/tracking.rs`.

For the full architecture, component details, and module development patterns, see:
- [ARCHITECTURE.md](docs/contributing/ARCHITECTURE.md) — System design, module organization, filtering strategies, error handling
- [docs/contributing/TECHNICAL.md](docs/contributing/TECHNICAL.md) — End-to-end flow, folder map, hook system, filter pipeline

Module responsibilities are documented in each folder's `README.md` and each file's `//!` doc header. Browse `src/cmds/*/` to discover available filters.

Supported ecosystems: git/gh/gt, cargo, go/golangci-lint, npm/pnpm/npx, ruff/pytest/pip/mypy, rspec/rubocop/rake, dotnet, playwright/vitest/jest, docker/kubectl/aws, gradlew/mvn, php/artisan/phpunit/phpstan/pest.

### Proxy Mode

**Purpose**: Execute commands without filtering but track usage for metrics.

**Usage**: `rtk proxy <command> [args...]`

**Benefits**:
- **Bypass RTK filtering**: Workaround bugs or get full unfiltered output
- **Track usage metrics**: Measure which commands Claude uses most (visible in `rtk gain --history`)
- **Guaranteed compatibility**: Always works even if RTK doesn't implement the command

**Examples**:
```bash
rtk proxy git log --oneline -20    # Full git log output (no truncation)
rtk proxy npm install express      # Raw npm output (no filtering)
rtk proxy curl https://api.example.com/data  # Any command works
```

All proxy commands appear in `rtk gain --history` with 0% bash output reduction (input = output).

## Coding Rules

Rust patterns, error handling, and anti-patterns are defined in `.claude/rules/rust-patterns.md` (auto-loaded into context). Key points:

- **anyhow::Result** everywhere, always `.context("description")?`
- **No unwrap()** in production code
- **lazy_static!** for all regex (never compile inside a function)
- **Fallback pattern**: if filter fails, execute raw command unchanged
- **No async**: single-threaded by design (startup <10ms)
- **Exit code propagation**: `std::process::exit(code)` on child failure

Testing strategy and performance targets are defined in `.claude/rules/cli-testing.md` (auto-loaded). Key targets: <10ms startup, <5MB memory, 60-90% reduction in bash output bytes.

For contribution workflow and design philosophy, see [CONTRIBUTING.md](CONTRIBUTING.md). For the step-by-step filter implementation checklist, see [src/cmds/README.md](src/cmds/README.md#adding-a-new-command-filter).

## Build Verification (Mandatory)

**CRITICAL**: After ANY Rust file edits, ALWAYS run the full quality check pipeline before committing:

```bash
cargo fmt --all && cargo clippy --all-targets && cargo test --all
```

**Rules**:
- Never commit code that hasn't passed all 3 checks
- Fix ALL clippy warnings before moving on (zero tolerance)
- If build fails, fix it immediately before continuing to next task

**Performance verification** (for filter changes):
```bash
hyperfine 'rtk git log -10' --warmup 3          # before
cargo build --release
hyperfine 'target/release/rtk git log -10' --warmup 3  # after (should be <10ms)
```

## Working Directory Confirmation

**ALWAYS confirm working directory before starting any work**:

```bash
pwd  # Verify you're in the rtk project root
git branch  # Verify correct branch (main, feature/*, etc.)
```

**Never assume** which project to work in. Always verify before file operations.

## Avoiding Rabbit Holes

**Stay focused on the task**. Do not make excessive operations to verify external APIs, documentation, or edge cases unless explicitly asked.

**Rule**: If verification requires more than 3-4 exploratory commands, STOP and ask the user whether to continue or trust available info.

**Examples of rabbit holes to avoid**:
- Excessive regex pattern testing (trust snapshot tests, don't manually verify 20 edge cases)
- Deep diving into external command documentation (use fixtures, don't research git/cargo internals)
- Over-testing cross-platform behavior (test macOS + Linux, trust CI for Windows)
- Verifying API signatures across multiple crate versions (use docs.rs if needed, don't clone repos)

**When to stop and ask**:
- "Should I research X external API behavior?" → ASK if it requires >3 commands
- "Should I test Y edge case?" → ASK if not mentioned in requirements
- "Should I verify Z across N platforms?" → ASK if N > 2

## Plan Execution Protocol

When user provides a numbered plan (QW1-QW4, Phase 1-5, sprint tasks, etc.):

1. **Execute sequentially**: Follow plan order unless explicitly told otherwise
2. **Commit after each logical step**: One commit per completed phase/task
3. **Never skip or reorder**: If a step is blocked, report it and ask before proceeding
4. **Track progress**: Use task list (TaskCreate/TaskUpdate) for plans with 3+ steps
5. **Validate assumptions**: Before starting, verify all referenced file paths exist and working directory is correct


===== FILE leonardomso/33-js-concepts::.claude/CLAUDE.md | stars=66505 followers=3205 lang=JavaScript bytes=20805 =====

# 33 JavaScript Concepts - Project Context

## Overview

This repository is a curated collection of **33 essential JavaScript concepts** that every JavaScript developer should know. It serves as a comprehensive learning resource and study guide for developers at all levels, from beginners to advanced practitioners.

The project was recognized by GitHub as one of the **top open source projects of 2018** and has been translated into 40+ languages by the community.

## Project Purpose

- Help developers master fundamental and advanced JavaScript concepts
- Provide curated resources (articles, videos, books) for each concept
- Serve as a reference guide for interview preparation
- Foster community contributions through translations and resource additions

## Repository Structure

```
33-js-concepts/
├── .claude/                 # Claude configuration
│   ├── CLAUDE.md           # Project context and guidelines
│   └── skills/             # Custom skills for content creation
│       ├── write-concept/  # Skill for writing concept documentation
│       ├── fact-check/     # Skill for verifying technical accuracy
│       ├── seo-review/     # Skill for SEO audits
│       ├── test-writer/    # Skill for generating Vitest tests
│       ├── resource-curator/ # Skill for curating external resources
│       └── concept-workflow/ # Skill for end-to-end concept creation
├── .opencode/               # OpenCode configuration
│   └── skill/              # Custom skills (mirrored from .claude/skills)
│       ├── write-concept/  # Skill for writing concept documentation
│       ├── fact-check/     # Skill for verifying technical accuracy
│       ├── seo-review/     # Skill for SEO audits
│       ├── test-writer/    # Skill for generating Vitest tests
│       ├── resource-curator/ # Skill for curating external resources
│       └── concept-workflow/ # Skill for end-to-end concept creation
├── docs/                    # Mintlify documentation site
│   ├── docs.json           # Mintlify configuration
│   ├── index.mdx           # Homepage
│   ├── introduction.mdx    # Getting started guide
│   ├── contributing.mdx    # Contribution guidelines
│   ├── translations.mdx    # Community translations
│   └── concepts/           # 33 concept pages
│       ├── call-stack.mdx
│       ├── primitive-types.mdx
│       └── ... (all 33 concepts)
├── tests/                   # Vitest test suites
│   └── fundamentals/       # Tests for fundamental concepts (1-6)
│       ├── call-stack/
│       ├── primitive-types/
│       ├── value-reference-types/
│       ├── type-coercion/
│       ├── equality-operators/
│       └── scope-and-closures/
├── vitest.config.js        # Vitest configuration
├── README.md               # Main GitHub README
├── CONTRIBUTING.md         # Guidelines for contributors
├── CODE_OF_CONDUCT.md      # Community standards
├── LICENSE                 # MIT License
├── package.json            # Project metadata
├── opencode.jsonc          # OpenCode AI assistant configuration
└── github-image.png        # Project banner image
```

## The 31 Concepts (32nd and 33rd coming soon)

### Fundamentals (1-6)
1. Primitive Types
2. Value Types and Reference Types
3. Type Coercion (Implicit, Explicit, Nominal, Structuring and Duck Typing)
4. Equality Operators (== vs === vs typeof)
5. Scope & Closures
6. Call Stack

### Functions & Execution (7-8)
7. Event Loop (Message Queue)
8. IIFE, Modules and Namespaces

### Web Platform (9-10)
9. DOM and Layout Trees
10. HTTP & Fetch

### Object-Oriented JS (11-15)
11. Factories and Classes
12. this, call, apply and bind
13. new, Constructor, instanceof and Instances
14. Prototype Inheritance and Prototype Chain
15. Object.create and Object.assign

### Functional Programming (16-19)
16. map, reduce, filter
17. Pure Functions, Side Effects, State Mutation and Event Propagation
18. Higher-Order Functions
19. Recursion

### Async JavaScript (20-22)
20. Collections and Generators
21. Promises
22. async/await

### Advanced Topics (23-31)
23. JavaScript Engines
24. Data Structures
25. Big O Notation (Expensive Operations)
26. Algorithms
27. Inheritance, Polymorphism and Code Reuse
28. Design Patterns
29. Partial Applications, Currying, Compose and Pipe
30. Clean Code

## Content Format

Each concept page in `/docs/concepts/` follows this structure:

### 1. Frontmatter
```mdx
---
title: "Concept Name"
description: "Brief description of the concept"
---
```

### 2. Real-World Analogy
Start with an engaging analogy that makes the concept relatable. Include ASCII art diagrams when helpful.

### 3. Info Box (What You'll Learn)
```mdx
<Info>
**What you'll learn in this guide:**
- Key point 1
- Key point 2
- Key point 3
</Info>
```

### 4. Main Content Sections
- Use clear headings (`##`, `###`) to organize topics
- Include code examples with explanations
- Use Mintlify components (`<AccordionGroup>`, `<Steps>`, `<Tabs>`, etc.)
- Add diagrams and visualizations where helpful

### 5. Related Concepts
```mdx
<CardGroup cols={2}>
  <Card title="Related Concept" icon="icon-name" href="/concepts/concept-slug">
    Brief description of how it relates
  </Card>
</CardGroup>
```

### 6. Reference
```mdx
<Card title="Topic — MDN" icon="book" href="https://developer.mozilla.org/...">
  Official MDN documentation
</Card>
```

### 7. Articles
Curated blog posts and tutorials using `<CardGroup>` with `icon="newspaper"`.

### 8. Courses (optional)
Educational courses using `<Card>` with `icon="graduation-cap"`.

### 9. Videos
YouTube tutorials and conference talks using `<CardGroup>` with `icon="video"`.

## Contributing Guidelines

### Adding Resources
- Resources should be high-quality and educational
- Follow the existing Card format for consistency
- Include a brief description of what the resource covers

### Resource Format
```mdx
<Card title="Resource Title" icon="newspaper" href="https://...">
  Brief description of what the reader will learn from this resource.
</Card>
```

## Git Commit Conventions

This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification. All commits must adhere to this format for consistency and automated changelog generation.

### Commit Message Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Commit Types

| Type | Description |
|------|-------------|
| `feat` | New features or content additions (e.g., new resources, new concepts) |
| `fix` | Bug fixes, broken link corrections, typo fixes |
| `docs` | Documentation changes (README updates, CONTRIBUTING updates) |
| `style` | Formatting changes (markdown formatting, whitespace) |
| `refactor` | Content restructuring without adding new resources |
| `chore` | Maintenance tasks (config updates, dependency updates) |
| `ci` | CI/CD configuration changes |
| `perf` | Performance improvements |
| `test` | Adding or updating tests |
| `build` | Build system or external dependency changes |
| `revert` | Reverting a previous commit |

### Examples

```bash
# Adding a new resource
feat: add article about closures by John Doe

# Fixing a broken link
fix: update broken MDN link in Promises section

# Documentation update
docs: update contributing guidelines for translations

# Maintenance task
chore: update opencode.json configuration

# Adding content to existing concept
feat(closures): add video tutorial by Fun Fun Function

# Multiple changes in body
feat: add new resources for async/await

- Add article by JavaScript Teacher
- Add video tutorial by Traversy Media
- Update reference links
```

### Rules

1. **Use lowercase** for the type and description
2. **No period** at the end of the description
3. **Use imperative mood** ("add" not "added", "fix" not "fixed")
4. **Keep the first line under 72 characters**
5. **Reference issues** in the footer when applicable (e.g., `Closes #123`)

## MCP Servers Available

This project has OpenCode configured with:

1. **Context7** - Documentation search (`use context7` in prompts)
2. **GitHub** - Repository management (`use github` in prompts)

## Testing

This project uses [Vitest](https://vitest.dev/) as the test runner to verify that code examples in the documentation work correctly.

### Running Tests

```bash
# Run all tests once
npm test

# Run tests in watch mode (re-runs on file changes)
npm run test:watch

# Run tests with coverage report
npm run test:coverage
```

### Test Structure

Tests are organized by concept category in the `tests/` directory:

```
tests/
├── fundamentals/              # Concepts 1-6
│   ├── call-stack/
│   ├── primitive-types/
│   ├── value-reference-types/
│   ├── type-coercion/
│   ├── equality-operators/
│   └── scope-and-closures/
├── functions-execution/       # Concepts 7-8
│   ├── event-loop/
│   └── iife-modules/
└── web-platform/              # Concepts 9-10
    ├── dom/
    └── http-fetch/
```

### Writing Tests for Code Examples

When adding new code examples to concept documentation, please include corresponding tests:

1. **File naming**: Create `{concept-name}.test.js` in `tests/{category}/{concept-name}/`
2. **Use explicit imports**: 
   ```javascript
   import { describe, it, expect } from 'vitest'
   ```
3. **Convert console.log examples to assertions**:
   ```javascript
   // Documentation example:
   // console.log(typeof "hello") // "string"
   
   // Test:
   it('should return string type', () => {
     expect(typeof "hello").toBe("string")
   })
   ```
4. **Test error cases**: Use `expect(() => { ... }).toThrow()` for operations that should throw
5. **Skip browser-specific examples**: Tests run in Node.js, so skip DOM/window/document examples
6. **Note strict mode behavior**: Vitest runs in strict mode, so operations that "silently fail" in non-strict mode will throw `TypeError`

### Current Test Coverage

| Category | Concept | Tests |
|----------|---------|-------|
| Fundamentals | Call Stack | 20 |
| Fundamentals | Primitive Types | 73 |
| Fundamentals | Value vs Reference Types | 54 |
| Fundamentals | Type Coercion | 74 |
| Fundamentals | Equality Operators | 87 |
| Fundamentals | Scope and Closures | 46 |
| Functions & Execution | Event Loop | 56 |
| Functions & Execution | IIFE & Modules | 61 |
| Web Platform | DOM | 85 |
| Web Platform | HTTP & Fetch | 72 |
| **Total** | | **628** |

## Documentation Site (Mintlify)

The project includes a Mintlify documentation site in the `/docs` directory.

### Local Development

```bash
# Using npm script
npm run docs

# Or install Mintlify CLI globally
npm i -g mint
cd docs
mint dev
```

The site will be available at `http://localhost:3000`.

### Documentation Structure

- **Getting Started**: Homepage and introduction
- **Fundamentals**: Concepts 1-6 (Primitive Types through Call Stack)
- **Functions & Execution**: Concepts 7-8 (Event Loop through IIFE/Modules)
- **Web Platform**: Concepts 9-10 (DOM and HTTP & Fetch)
- **Object-Oriented JS**: Concepts 11-15 (Factories through Object.create/assign)
- **Functional Programming**: Concepts 16-19 (map/reduce/filter through Recursion)
- **Async JavaScript**: Concepts 20-22 (Collections/Generators through async/await)
- **Advanced Topics**: Concepts 23-31 (JavaScript Engines through Clean Code)

### Adding/Editing Concept Pages

Each concept page is in `docs/concepts/` and follows this template:

```mdx
---
title: "Concept Name"
description: "Brief description"
---

## Overview
[Explanation of the concept]

## Reference
[MDN or official docs links]

## Articles
[Curated articles with CardGroup components]

## Videos
[Curated videos with CardGroup components]
```

## Important Notes

- This is primarily a documentation/resource repository, not a code library
- The main content lives in `README.md` and `/docs` (Mintlify site)
- Translations are maintained in separate forked repositories
- Community contributions are welcome and encouraged
- MIT Licensed

## Custom Skills

### write-concept Skill

Use the `/write-concept` skill when writing or improving concept documentation pages. This skill provides comprehensive guidelines for:

- **Page Structure**: Exact template for concept pages (frontmatter, opening hook, code examples, sections)
- **SEO Optimization**: Critical guidelines for ranking in search results
- **Writing Style**: Voice, tone, and how to make content accessible to beginners
- **Code Examples**: Best practices for clear, educational code
- **Quality Checklists**: Verification steps before publishing

**When to invoke:**
- Creating a new concept page in `/docs/concepts/`
- Rewriting or significantly improving an existing concept page
- Reviewing an existing concept page for quality

**SEO is Critical:** Each concept page should rank for searches like:
- "what is [concept] in JavaScript"
- "how does [concept] work in JavaScript"
- "[concept] JavaScript explained"

The skill includes detailed guidance on title optimization (50-60 chars), meta descriptions (150-160 chars), keyword placement, and featured snippet optimization.

**Location:** `.claude/skills/write-concept/SKILL.md`

### fact-check Skill

Use the `/fact-check` skill when verifying the technical accuracy of concept documentation. This skill provides comprehensive methodology for:

- **Code Verification**: Verify all code examples produce stated outputs, run project tests
- **MDN/Spec Compliance**: Check claims against official MDN documentation and ECMAScript specification
- **External Resource Checks**: Verify all links work and descriptions accurately represent content
- **Misconception Detection**: Common JavaScript misconceptions to watch for (type coercion, async behavior, etc.)
- **Test Integration**: Instructions for running `npm test` to verify code examples
- **Report Template**: Structured format for documenting findings with severity levels

**When to invoke:**
- Before publishing a new concept page
- After significant edits to existing pages
- When reviewing community contributions
- Periodic accuracy audits of existing content

**What gets checked:**
- Every code example for correct output
- All MDN links for validity (not 404)
- API descriptions match current MDN documentation
- External resources (articles, videos) are accessible and accurate
- Technical claims are correct and properly nuanced
- No common JavaScript misconceptions stated as fact

**Location:** `.claude/skills/fact-check/SKILL.md`

### seo-review Skill

Use the `/seo-review` skill when auditing concept pages for search engine optimization. This skill provides a focused audit checklist:

- **27-Point Scoring System**: Systematic audit across 6 categories
- **Title & Meta Optimization**: Character counts, keyword placement, compelling hooks
- **Keyword Strategy**: Pre-built keyword clusters for all JavaScript concepts
- **Featured Snippet Optimization**: Patterns for winning position zero in search results
- **Internal Linking**: Audit of concept interconnections and anchor text quality
- **Report Template**: Structured SEO audit report with prioritized fixes

**When to invoke:**
- Before publishing a new concept page
- When optimizing underperforming pages
- Periodic content audits
- After major content updates

**Scoring Categories (30 points total):**
- Title Tag (4 points)
- Meta Description (4 points)
- Keyword Placement (5 points)
- Content Structure (6 points)
- Featured Snippets (4 points)
- Internal Linking (4 points)
- Technical SEO (3 points) — Single H1, keyword in slug, no orphan pages

**Score Interpretation:**
- 90-100% (27-30): Ready to publish
- 75-89% (23-26): Minor optimizations needed
- 55-74% (17-22): Several improvements needed
- Below 55% (<17): Significant work required

**Location:** `.claude/skills/seo-review/SKILL.md`

### test-writer Skill

Use the `/test-writer` skill when generating Vitest tests for code examples in concept documentation. This skill provides comprehensive methodology for:

- **Code Extraction**: Identify and categorize all code examples (testable, DOM, error, conceptual)
- **Test Patterns**: 16 patterns for converting different types of code examples to tests
- **DOM Testing**: Separate file structure with jsdom environment for browser-specific code
- **Source References**: Line number references linking tests to documentation
- **Project Conventions**: File naming, describe block organization, assertion patterns
- **Report Template**: Test coverage report documenting what was tested and skipped

**When to invoke:**
- After writing a new concept page
- When adding new code examples to existing pages
- When updating existing code examples
- To verify documentation accuracy through automated tests

**Test Categories:**
- Basic value assertions (`console.log` → `expect`)
- Error testing (`toThrow` patterns)
- Async testing (Promises, async/await)
- DOM testing (jsdom environment, events)
- Floating point (toBeCloseTo)
- Object/Array comparisons (toEqual)

**File Structure:**
```
tests/{category}/{concept-name}/{concept-name}.test.js
tests/{category}/{concept-name}/{concept-name}.dom.test.js  (if DOM examples)
```

**Location:** `.claude/skills/test-writer/SKILL.md`

### resource-curator Skill

Use the `/resource-curator` skill when finding, evaluating, or maintaining external resources (articles, videos, courses) for concept pages. This skill provides:

- **Audit Process**: Check existing links for accessibility, accuracy, and relevance
- **Trusted Sources**: Prioritized lists of reputable article, video, and course sources
- **Quality Criteria**: Must-have, should-have, and red flag checklists
- **Description Writing**: Formula and examples for specific, valuable descriptions
- **Publication Guidelines**: Date thresholds for different topic categories
- **Report Template**: Audit report for documenting broken, outdated, and missing resources

**When to invoke:**
- Adding resources to a new concept page
- Refreshing resources on existing pages
- Auditing for broken or outdated links
- Reviewing community-contributed resources
- Periodic link maintenance

**Resource Targets:**
- Reference: 2-4 MDN links
- Articles: 4-6 quality articles
- Videos: 3-4 quality videos
- Courses: 1-3 (optional)

**Trusted Sources Include:**
- Articles: javascript.info, MDN Guides, freeCodeCamp, 2ality, CSS-Tricks, dev.to
- Videos: Fireship, Web Dev Simplified, Fun Fun Function, Traversy Media, JSConf
- Courses: javascript.info, Piccalilli, freeCodeCamp, Frontend Masters

**Location:** `.claude/skills/resource-curator/SKILL.md`

### concept-workflow Skill

Use the `/concept-workflow` skill for end-to-end creation of a complete concept page. This orchestrator skill coordinates all five specialized skills in optimal order:

```
Phase 1: resource-curator  →  Find quality external resources
Phase 2: write-concept     →  Write the documentation page
Phase 3: test-writer       →  Generate tests for code examples
Phase 4: fact-check        →  Verify technical accuracy
Phase 5: seo-review        →  Optimize for search visibility
```

**When to invoke:**
- Creating a brand new concept page from scratch
- Completely rewriting an existing concept page
- When you want the full end-to-end workflow with all quality checks

**What it orchestrates:**
- Resource curation (2-4 MDN refs, 4-6 articles, 3-4 videos)
- Complete concept page writing (1,500+ words)
- Comprehensive test generation for all code examples
- Technical accuracy verification with test execution
- SEO audit targeting 90%+ score (24+/27)

**Deliverables:**
- `/docs/concepts/{concept-name}.mdx` — Complete documentation page
- `/tests/{category}/{concept-name}/{concept-name}.test.js` — Test file
- Updated `docs.json` navigation (if new concept)
- Fact-check report
- SEO audit report (score 24+/27)

**Estimated Time:** 2-5 hours depending on concept complexity

**Example prompt:**
> "Create a complete concept page for 'hoisting' using the concept-workflow skill"

**Location:** `.claude/skills/concept-workflow/SKILL.md`

## Maintainer

**Leonardo Maldonado** - [@leonardomso](https://github.com/leonardomso)

## Links

- Repository: https://github.com/leonardomso/33-js-concepts
- Issues: https://github.com/leonardomso/33-js-concepts/issues
- Original Article: [33 Fundamentals Every JavaScript Developer Should Know](https://medium.com/@stephenthecurt/33-fundamentals-every-javascript-developer-should-know-13dd720a90d1) by Stephen Curtis


===== FILE webpack/webpack::AGENTS.md | stars=65864 followers=None lang=JavaScript bytes=23906 =====

# Webpack Development Guide

> Note: CLAUDE.md is a symlink to AGENTS.md. They are the same file.

## Conventions in this guide

A `> [!REQUIRED]` callout placed immediately under a heading marks that whole section as **mandatory and not optional**: follow it exactly, do not paraphrase, do not skip, do not substitute a similar-looking convention from other tooling. Reviewers have repeatedly flagged that REQUIRED sections (especially the [Pull request body](#pull-request-body)) are being skipped or partially filled in — doing so blocks the PR every time. Read each REQUIRED section in full whenever it applies; do not rely on memory or on a previous task's output. Sections without the callout are normal guidance — apply judgement.

## Project Overview

> [!REQUIRED]

The directory listings below are the canonical map of the repository. **Whenever you add, rename, or remove a top-level directory** (under the repo root, under `lib/`, under `test/`, or under `schemas/`) you must update the matching bullet here in the same commit. CI does not check this — drift is only caught by humans, which is why it must be part of the change itself. If a new directory does not fit any existing group, add a new group rather than dropping the entry.

webpack is a JavaScript module bundler. Package manager: **yarn**.

**Source**

- `lib/` — Main source code (CommonJS only; types declared via JSDoc `@typedef`).
  - `lib/asset/` — Asset modules (images, fonts, raw files); includes the `asset/webmanifest` type that parses `<link rel="manifest">` icon URLs.
  - `lib/async-modules/` — Top-level await.
  - `lib/bun/` — Bun target externals preset (`bun:*` and node.js built-in modules).
  - `lib/cache/` — Filesystem and memory caches.
  - `lib/config/` — Config defaults, normalization, target presets.
  - `lib/container/` — Module Federation.
  - `lib/css/` — CSS Modules, CSS parsing and generation.
  - `lib/debug/` — Debug helpers.
  - `lib/dependencies/` — `Dependency` classes and their templates (HarmonyImport, CommonJsRequire, RequireContext, …).
  - `lib/dll/` — DllPlugin / DllReferencePlugin.
  - `lib/deno/`, `lib/electron/`, `lib/node/`, `lib/web/`, `lib/webworker/` — Target-specific runtime templates and externals presets.
  - `lib/errors/` — Error class hierarchy.
  - `lib/esm/` — ESM-specific output (e.g. `import.meta`).
  - `lib/hmr/` — Hot Module Replacement plugins.
  - `lib/html/` — Experimental HTML support.
  - `lib/ids/` — Module/chunk id assignment plugins.
  - `lib/javascript/` — JavaScript parsing (acorn), generation, exports analysis.
  - `lib/json/` — JSON modules.
  - `lib/library/` — UMD/AMD/ESM/CommonJS library output formats.
  - `lib/loaders/` — Loader execution runtime (vendored loader-runner): pitching/normal loader iteration and loader module loading.
  - `lib/logging/` — Logger API and console formatting.
  - `lib/optimize/` — Optimization plugins (`SplitChunksPlugin`, `ConcatenatedModule`, …).
  - `lib/performance/` — Asset/entrypoint size hints.
  - `lib/prefetch/` — Prefetch/preload plugins.
  - `lib/rules/` — `module.rules` matching engine.
  - `lib/runtime/` — Runtime modules emitted into bundles (chunk loaders, public-path, …).
  - `lib/schemes/` — Custom URL scheme handlers (`data:`, `http:`, …).
  - `lib/serialization/` — Persistent cache serialization.
  - `lib/sharing/` — Shared modules / Module Federation runtime.
  - `lib/stats/` — Stats output (default printer, JSON factories).
  - `lib/typescript/` — Experimental TypeScript module support (strip types via the Node.js TypeScript API).
  - `lib/url/` — `new URL(asset, import.meta.url)` references.
  - `lib/util/` — Utility helpers.
  - `lib/wasm/`, `lib/wasm-async/`, `lib/wasm-sync/` — WebAssembly module support.
- `hot/` — Runtime code shipped to browsers for HMR (browser-side, not Node tooling).
- `bin/` — `webpack` CLI entry point.
- `tooling/` — Repo-internal build scripts (runtime/wasm code generators, hash-debug tool); invoked by `yarn fix:special`.
- `assembly/` — WebAssembly source for the hash function.
- `setup/` — One-time setup scripts.

**Schemas (the source of truth for webpack's config API)**

- `schemas/WebpackOptions.json` — top-level webpack options schema.
- `schemas/plugins/*.json` — per-plugin option schemas (`BannerPlugin`, `IgnorePlugin`, `ProgressPlugin`, `SourceMapDevToolPlugin`, …).
- `schemas/_container.json`, `schemas/_sharing.json` — Module Federation sub-schemas.

**Tests** — see [TESTING_DOCS.md](TESTING_DOCS.md) for directory structure, naming, and how to run a single case.

- `test/` — All test suites (`cases/`, `configCases/`, `watchCases/`, `hotCases/`, `statsCases/`, `typesCases/`, `test262-cases/`, `html5lib-tests/`, `css-parsing-tests/`, `benchmarkCases/`, `memoryLimitCases/`, etc.). `RoundTripConfigCases` re-bundles the output of `configCases` marked with a `roundTrip.js` file.

**Examples & changesets**

- `examples/` — Usage examples (build with `yarn build:examples`).
- `.changeset/` — Pending changeset files for the next release.

**Auto-generated — do not edit by hand; regenerate via `yarn fix:special`**

- `types.d.ts`, `declarations/**/*.d.ts`, `schemas/**/*.check.{js,d.ts}`, generated runtime code under `lib/`.

**Hand-maintained type declarations (these _are_ editable)**

- `declarations.d.ts`, `declarations.test.d.ts`, `module.d.ts`.

**Configuration**

- `package.json` — All commands (defined in `scripts`).
- `tsconfig*.json` — TypeScript configs (one per surface: `lib`, `hot`, types tests, validation, benchmarks).
- `eslint.config.mjs`, `cspell.json`, `jest.config.js`, `generate-types-config.js` — Lint/spell/test/type-gen configs.
- `.github/workflows/`, `.github/scripts/` — CI.
- `test/patches/` — test-only dependency patches (e.g. jest-worker) applied via `git apply` in the CI Bun test job.

## Coding Standards

### Source language: CommonJS + JSDoc

`lib/` is CommonJS only. Use `module.exports` / `require()`, never `import`/`export` syntax. Types are declared via JSDoc — `@typedef {import("./Other")} Other` and friends — never TypeScript syntax inside `.js` files. The JSDoc annotations are compiled into `types.d.ts` by `yarn fix:special`.

### Type annotations

Prefer the most specific real type. `EXPECTED_ANY`, `EXPECTED_OBJECT`, and `EXPECTED_FUNCTION` (aliases for `any`, `object`, `Function`) are an escape hatch, not a default — use them **only** when the value genuinely can be any value, any object, or any function. When you simply don't know the type yet, reach for `unknown` and narrow it, rather than widening to `EXPECTED_ANY`. This applies in `test/` too: if a real type (e.g. an imported `import("…").Foo`) fits, use it instead of `EXPECTED_ANY`.

Prefer a generic (`@template`) over a widened type whenever a function's output type depends on its input — it keeps callers precisely typed instead of collapsing to `EXPECTED_ANY`.

### Naming

Spell names out in full — functions, variables, parameters, properties. Prefer `insertHtmlElement` over `insHtmlEl`, `attributeCount` over `attrCnt`, `current` over `cur`, `element` over `el`. Don't truncate or drop vowels to save characters; a clear name is worth the extra keystrokes.

The only exceptions are (1) established abbreviations webpack already uses pervasively (`ast`, `ns` for namespace, `id`, `url`, `css`, `js`, `dir`, `env`, `fs`) or spec-defined ones (`afe` for the HTML spec's "active formatting elements"), and (2) throwaway loop indices (`i`, `j`, `k`). When an abbreviation isn't already common in the codebase or the relevant spec, write the full word.

### Source file headers

Every source file under `lib/` (and `hot/`, `tooling/`) opens with the MIT license header. When adding a **new** file, set the `Author` line to its actual author (`Author <Name> @<github-handle>`) — don't copy another file's author line.

### Code comments

> [!REQUIRED]

Comments inside `lib/`, `hot/`, `tooling/`, and `test/` must be **as short as possible** — ideally one line, at most two short lines. Every line must add information a careful reader can't get from the code itself: a hidden invariant, a non-obvious ordering constraint, a workaround, or the name of the higher-level concept the block implements. **Never** write multi-paragraph essays, restate what the next line obviously does, narrate the diff, restate the PR description, or quote the user/task framing.

JSDoc on exported symbols stays as-is — that's the type contract, not commentary.

## Performance and memory

webpack is a bundler — users measure it by build time and peak heap usage. Many changes in `lib/` end up on per-module hot paths (sometimes per module × runtime, or per chunk × module) on user builds, so constant factors compound. Always weigh the time and memory cost of a change, including bug fixes and refactors: less allocation, smaller `Map`/`Set` footprints, and fewer closures retained on hot paths are wins worth pursuing — less is better. When introducing or holding any per-`Compilation` state, ask whether it can be released after seal/emit so large compilation data structures are not retained longer than necessary. See #15521 for an example of how this class of memory issue can surface.

## Auto-generated files

> [!REQUIRED]

These files are produced by `yarn fix:special` and must not be edited by hand:

- `types.d.ts` — compiled from JSDoc + schemas.
- `declarations/**/*.d.ts` — per-schema/plugin declarations emitted from `schemas/**/*.json`.
- `schemas/**/*.check.{js,d.ts}` — precompiled schema validators.
- Generated runtime code under `lib/` (driven by `tooling/generate-runtime-code.js`).

The hand-maintained type declarations (`declarations.d.ts`, `declarations.test.d.ts`, `module.d.ts`) _are_ editable.

Re-run `yarn fix:special` **before the next commit** whenever you touch:

- `schemas/**/*.json` — reshapes validators, declarations, and `types.d.ts`.
- `lib/**/*.js` JSDoc on anything reachable from a public export — regenerates `types.d.ts`.
- `tooling/generate-runtime-code.js`, `tooling/generate-wasm-code.js`, or any file they consume.

CI's `lint` job verifies these outputs are up to date. The combined `yarn fix` script runs `fix:code` + `fix:special` + `fmt` in one go; prefer it as the final step.

## Development Workflow

### 1. Making Changes

Modify source code in `lib/` as needed.

**Adding or renaming a webpack option** requires edits in every layer, in this order:

1. **Schema** — `schemas/WebpackOptions.json` (or `schemas/plugins/<Name>.json`).
2. **Defaults** — `lib/config/defaults.js`.
3. **Normalization** — `lib/config/normalization.js`.
4. **Implementation** — the site that consumes the option.

Skipping any layer silently breaks the option. After editing schemas, run `yarn fix:special` so `lib/` code can reference the updated types.

### 2. Writing and Running Tests

**For bug fixes, always write the test case first.** Run the test to confirm it fails, then make the code change and re-run. For new features, tests can be written alongside or after.

**Prefer integration tests over unit tests.** Cover behavior with an integration case (`configCases/`, `watchCases/`, `hotCases/`, `statsCases/`, …) that drives a real `webpack()` build whenever the behavior can be exercised that way — they catch real-world regressions a mocked unit test misses. Reach for a `*.unittest.js` only for pure helpers/utilities that a build can't naturally reach.

Run targeted tests — `yarn test:base --testPathPatterns="<pattern>"` or `yarn test:base -t "<name>"`. Never invoke `yarn jest`/`npx jest` directly: the required `--experimental-vm-modules` node flag lives only in the `test:base` wrapper, and bare jest crashes ESM/test262 suites. Don't run `yarn test` unless asked. When updating snapshots (`yarn test:base -u`), eyeball the diff first. See [TESTING_DOCS.md](TESTING_DOCS.md) for details.

**Cover every line you add or change.** A commit must not lower coverage: each new branch, fast path, and fallback needs a test that exercises it (Codecov enforces this on the patch, target 90%+). When a change adds branches that integration cases don't reach — e.g. tokenizer fast paths and their cold-path fallbacks — add a focused `*.unittest.js` that drives each branch (both the fast and delegated paths). Check `yarn cover:unit` locally, or the PR's Codecov "patch" report, and add cases until no changed line is missing.

### 3. Adding a Changeset

Every user-facing change needs a changeset file:

```bash
# Create .changeset/<NNN>-<descriptive-name>.md with this format:
---
"webpack": patch    # or minor / major
---

Description of the change.
```

Use `patch` for bug fixes, `minor` for new features, `major` for breaking changes. Do not prefix the description with `fix:`, `feat:`, etc.

**Keep the description as short as possible** — a single imperative sentence, ≤ 80 characters, **first character capitalized**, **trailing period** ("Fix split-chunks cache key collision."). Changesets are concatenated into `CHANGELOG.md` verbatim. Multi-paragraph rationale belongs in the PR body, not the changeset.

**One changeset per pull request** — when a PR contains several related changes, fold them into a single changeset entry (one sentence naming them, using the highest applicable bump level) instead of adding one file per change. Only add separate changeset files when the changes are genuinely unrelated to each other; the length limit may be relaxed slightly for a combined entry.

**Union same-topic entries** — before adding a changeset, scan `.changeset/` for an existing pending entry covering the same area (same option, parser, subsystem, or bug family) and fold your change into it rather than adding a near-duplicate. A cluster of "Speed up JavaScript parsing." lines is one entry, not seven.

**Filename controls ordering — prefix by importance.** Changesets render grouped by bump level (Major → Minor → Patch); within each section entries appear in **sorted `.changeset` filename order**. Name every changeset `NNN-<description>.md` with a zero-padded numeric prefix (`010-`, `020-`, …) so the lowest number sorts first and lands at the top of its section. Order by importance: user-facing features first, then correctness fixes, then performance, then internal/build/chore. Pick a prefix that slots your entry into the right place relative to the files already there (leave gaps so later entries fit between).

### 4. Updating Examples (if needed)

If WebpackOptions were added or modified, consider updating examples in `examples/`. Run `yarn build:examples` to verify.

### 5. Linting and Formatting

```bash
yarn fix           # fix:code (ESLint) + fix:special (regenerate types/validators) + fmt (Prettier)
yarn tsc           # TypeScript type check (catches type errors in JSDoc annotations)
```

### 6. Git Commit & Pull Request

#### Branch name

> [!REQUIRED]

Format: `<type>/<short-description>` (e.g. `fix/split-chunks-cache-key`, `feat/css-modules-named-exports`).

Valid `<type>` values: `fix`, `feat`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `style`, `revert`, `docs`. Must match the answer to "What kind of change does this PR introduce?" in the PR body.

**Choose `<type>` automatically from the diff** — do not guess or reuse a previous task's prefix. Inspect the staged changes and pick the single type describing their _primary intent_, using the first match in this priority order:

1. `revert` — the change reverts a previous commit.
2. `fix` — corrects incorrect runtime behavior (a bug); normally paired with a regression test.
3. `feat` — adds a new user-facing capability or config option (touches `schemas/`, `lib/config/`, or adds a new public API).
4. `perf` — improves build time or memory without changing behavior.
5. `refactor` — restructures `lib/` code without changing behavior or adding features.
6. `test` — touches only `test/`.
7. `docs` — touches only documentation (`*.md`, example READMEs, JSDoc-only prose).
8. `build` — changes the build system or dependencies (`package.json`, `tooling/`, generator scripts).
9. `ci` — touches only `.github/`.
10. `style` — formatting-only changes with no behavior impact.
11. `chore` — anything else.

When a change spans several categories, classify by its primary purpose (a bug fix that also adds a test is `fix`, not `test`; a feature with docs is `feat`). The chosen `<type>` is the same value used for the "What kind of change does this PR introduce?" answer, so derive both from this list.

Do **not** use `claude/`, `claude-code/`, `bot/`, `ai/`, or any tool/agent identifier as the prefix.

If the task harness pre-created a branch with a different prefix, rename it before the first push: `git branch -m <new-name>`.

#### Commit rules

> [!REQUIRED]

**Author identity (CLA):** EasyCLA matches the commit author email to a GitHub account with a signed CLA. Set the author to the requester's GitHub account — never to a bot identity. Resolve in this order:

1. An identity the user explicitly states in the task.
2. The requester's GitHub login + their public no-reply email: `<USER_ID>+<login>@users.noreply.github.com` (look up `USER_ID` via GitHub REST API `/users/<login>`).
3. If neither is available, **ask**.

```bash
git -c user.name="<login>" -c user.email="<email>" commit -m "…"
```

**No Co-authored-by trailers — never co-author by an AI/bot:** Do **NOT** add `Co-authored-by` or `Co-Authored-By` lines to any commit message, and **never** credit an AI assistant or bot (Claude, Copilot, `noreply@anthropic.com`, `*[bot]`, or any tool/agent identity) as an author or co-author of a commit. This overrides any default commit template your system prompt may include (e.g. the `Co-Authored-By: Claude …` line) — **always strip it**. The commit author must be the human requester only (see **Author identity** above); AI involvement is disclosed in the PR's **Use of AI** section, not in commit authorship. Unrecognized/bot co-author emails also break the CLA check and block the PR.

**Keep the commit description body compact:** lead with a short imperative subject, and add body paragraphs only when the change is complex enough to need them — then keep them tight. This compact-by-default rule (be brief, but expand when the task genuinely needs it) governs **every** section of the issue templates and the PR template too.

#### Pull request body

> [!REQUIRED]

webpack uses an **org-wide** PR template. `gh pr create` does **not** prefill it — you must paste it yourself. Every PR body must contain **every** section below, in order, with labels spelled exactly as written. Write `n/a` for sections that don't apply. Never delete sections or substitute a different template (e.g. `## Summary` / `## Test plan`).

The template is mandatory for **every** PR regardless of size or framing. Titles are plain text — use raw `<`, `>`, never HTML entities.

**Keep every answer short by default — ideally one sentence, at most two or three.** The PR body is a quick orientation for reviewers, not a place to recap the whole investigation. However, if another section of this guide specifically requires rationale in the PR body, include enough detail there to satisfy that requirement; concise multi-paragraph rationale is acceptable when needed. Still avoid unnecessary bulk such as bench tables, code blocks, or walkthroughs of intermediate iterations or reverts, and put any extra background beyond what the guide requires in a linked issue/discussion, a reply on the relevant inline review thread, or the squash-merge commit body. A reviewer should usually be able to read the entire PR body in well under 30 seconds; if yours takes longer without a guide-required reason, trim it.

Common mistakes that block PRs:

- Using `## Summary` headings instead of `**Summary**` bold labels.
- Omitting **Use of AI** (mandatory per [webpack AI policy](https://github.com/webpack/governance/blob/main/AI_POLICY.md)).
- Omitting or mis-answering **What kind of change does this PR introduce?** (must match branch prefix).
- Dropping HTML comment hints or leaving sections blank instead of `n/a`.

Paste the body from the fenced block below (do **not** include the fence lines themselves):

```markdown
<!-- Thanks for submitting a pull request! Please provide enough information so that others can review your pull request. -->

**Summary**

<!-- Explain the **motivation** for making this change. What existing problem does the pull request solve? -->
<!-- Try to link to an open issue for more information. -->
<!-- Any other information related to changes. -->

<!-- In addition to that please answer these questions: -->

**What kind of change does this PR introduce?**

<!-- E.g. a fix, feat, refactor, perf, test, chore, ci, build, style, revert, docs or describe it if you did not find a suitable kind of change. -->

**Did you add tests for your changes?**

<!-- Please note: in most cases, if you change the code, we will not merge your changes unless you add tests. -->

**Does this PR introduce a breaking change?**

<!-- If this PR introduces a breaking change, please describe the impact and a migration path for existing applications. -->

**If relevant, what needs to be documented once your changes are merged or what have you already documented?**

<!-- List all the information that needs to be added to the documentation after merge that has already been documented in this PR. -->

**Use of AI**

<!-- If you have used AI, please state so here. Explain how you used it.
Make sure to read our AI policy (https://github.com/webpack/governance/blob/main/AI_POLICY.md) or your Pull Request may be closed due to irresponsible use of AI. -->
```

Required answer per section — **one sentence each is the target, two or three the absolute maximum**:

- **Summary** — motivation and what problem is solved; link the related issue. When the PR actually fixes the bug or implements the feature the issue asks for, use the auto-closing form `Closes #…` / `Fixes #…` (not `Refs #…`); reserve `Refs #…` for issues the PR only relates to but does not resolve.
- **What kind of change does this PR introduce?** — one of: fix, feat, refactor, perf, test, chore, ci, build, style, revert, docs.
- **Did you add tests for your changes?** — yes/no + which test files.
- **Does this PR introduce a breaking change?** — yes/no + migration path if yes.
- **If relevant, what needs to be documented…** — list doc updates or write `n/a`.
- **Use of AI** — state that AI was used and how. Per the [webpack AI policy](https://github.com/webpack/governance/blob/main/AI_POLICY.md), omitting or misrepresenting this can get the PR closed.

#### After push — verify PR body

After every `git push` of a new branch, check whether a PR was auto-created (webpack has this webhook). If so, `update_pull_request` to install the full template — the auto-created body never matches.

#### After opening the PR — wait for Copilot review

> [!REQUIRED]

Every webpack PR gets an automated **GitHub Copilot code review** on the initial commit and on every subsequent push. You must always wait for it and address every comment.

1. After `create_pull_request`, subscribe to the PR (`subscribe_pr_activity`) so Copilot's review wakes the session. Do **not** poll.
2. When the review arrives, read every comment:
   - If correct, push a fix in a new commit.
   - If wrong, reply on the thread with a short reason — never ignore silently.
3. After every push, Copilot re-reviews. Repeat step 2. The loop ends when Copilot's latest review has zero outstanding threads.
4. Only `unsubscribe_pr_activity` once all comments are handled and CI is green, or when the user tells you to stop.


===== FILE Alishahryar1/free-claude-code::CLAUDE.md | stars=42237 followers=1025 lang=Python bytes=8398 =====

# AGENTIC DIRECTIVE

> Keep AGENTS.md and CLAUDE.md identical.

## CODING ENVIRONMENT

- Install astral uv using "curl -LsSf https://astral.sh/uv/install.sh | sh" if not already installed and if already installed then update it to the latest version
- Install Python 3.14.0 stable using `uv python install 3.14.0` if not already installed (requires uv >=0.9; see `[tool.uv] required-version` in `pyproject.toml`)
- Always use `uv run` to run files instead of the global `python` command.
- Current uv ruff formatter is set to py314 which has supports multiple exception types without paranthesis (except TypeError, ValueError:)
- Read `.env.example` for environment variables.
- All CI checks must pass; failing checks block merge.
- Add tests for new changes (including edge cases).
- Before pushing, prefer `./scripts/ci.sh` (macOS/Linux) or `.\scripts\ci.ps1` (Windows) to run the local CI sequence; requires `uv` on PATH. The local scripts run Ruff in repair mode (`ruff format`, then `ruff check --fix`) before type checking and tests.
- Use `--only` / `--skip` (PowerShell: `-Only` / `-Skip`) to run a subset when iterating; use `--dry-run` to print commands without running them.
- GitHub CI remains check-only for Ruff (`ruff format --check`, `ruff check`) so branch protection verifies committed code.
- Fall back to individual repair commands when debugging local failures: `uv run ruff format`, `uv run ruff check --fix`, `uv run ty check`, `uv run pytest -v --tb=short`. Use GitHub-style checks only when verifying enforcement locally: `uv run ruff format --check`, `uv run ruff check`.
- Do not add `# type: ignore` or `# ty: ignore`; fix the underlying type issue.
- Do not add `from __future__ import annotations`; Python 3.14 native lazy annotations are the project standard.
- All 5 check IDs are represented in `scripts/ci.sh` / `scripts/ci.ps1` and enforced in `tests.yml` on push/merge (parallel jobs: suppression grep, ruff-format, ruff-check, ty, pytest).
- GitHub CI runs on `push`, `pull_request`, and `merge_group` so required checks validate merge queue candidates before they land.
- Repository protection should use rulesets: a non-bypassable main integrity ruleset requires pull requests, merge queue, required checks, and blocks direct/force pushes to `main`; a separate review ruleset may allow `Alishahryar1`/admins to bypass review only.
- Required status checks: set **required status checks** to **all** of those statuses (e.g. **Ban suppressions and legacy annotations**, **ruff-format**, **ruff-check**, **ty**, **pytest**—use the exact labels GitHub shows, which may be prefixed with **CI /**). Remove **ci** from required checks if it was previously added for the old gate job.

## IDENTITY & CONTEXT

- You are an expert Software Architect and Systems Engineer.
- Goal: Zero-defect, root-cause-oriented engineering for bugs; test-driven engineering for new features. Think carefully; no need to rush.
- Code: Write the simplest code possible. Keep the codebase minimal and modular.

## ARCHITECTURE PRINCIPLES

- **Shared utilities**: Put shared Anthropic protocol logic in neutral `src/free_claude_code/core/anthropic/` modules. Do not have one provider import from another provider's utils.
- **Failure ownership**: Keep canonical failure semantics and redaction SDK-free in `core/`; providers alone classify SDK/HTTP failures and own retries; protocol/API adapters alone choose wire error types and commit-boundary serialization.
- **DRY**: Extract shared base classes to eliminate duplication. Prefer composition over copy-paste.
- **Encapsulation**: Use accessor methods for internal state (e.g. `set_current_task()`), not direct `_attribute` assignment from outside.
- **Provider-specific config**: Keep provider-specific fields (e.g. `nim_settings`) in provider constructors, not in the base `ProviderConfig`.
- **Model-independent reasoning**: Resolve client reasoning intent once at the application boundary; provider adapters translate documented provider capabilities. Never branch on upstream model names or versions to choose reasoning behavior.
- **Dead code**: Remove unused code, legacy systems, and hardcoded values. Use settings/config instead of literals (e.g. `settings.provider_type` not `"nvidia_nim"`).
- **Performance**: Use list accumulation for strings (not `+=` in loops), cache env vars at init, prefer iterative over recursive when stack depth matters.
- **Platform-agnostic naming**: Use generic names (e.g. `PLATFORM_EDIT`) not platform-specific ones (e.g. `TELEGRAM_EDIT`) in shared code.
- **No type ignores**: Do not add `# type: ignore` or `# ty: ignore`. Fix the underlying type issue.
- **Python 3.14 annotations**: Do not use `from __future__ import annotations`; rely on native lazy annotations and fix circular import boundaries instead of hiding them with annotation stringization.
- **Imports**: Prefer top-level imports. Avoid `TYPE_CHECKING` and local imports for first-party or required dependencies; if a top-level import creates a cycle, move shared types/protocols to a neutral owner.
- **Complete migrations**: When moving modules, update imports to the new owner and remove old compatibility shims in the same change unless preserving a published interface is explicitly required.
- **Maximum Test Coverage**: There should be maximum test coverage for everything, preferably live smoke test coverage to catch bugs early

## COGNITIVE WORKFLOW

1. **ANALYZE**: Read relevant files. Do not guess.
2. **PLAN**: Map out the logic. Identify root cause or required changes. Order changes by dependency.
3. **EXECUTE**: Fix the cause, not the symptom. Execute incrementally with clear commits.
4. **VERIFY**: Run `./scripts/ci.sh` or `.\scripts\ci.ps1`, plus relevant smoke tests when needed. Confirm the fix via logs or output.
5. **SPECIFICITY**: Do exactly as much as asked; nothing more, nothing less.
6. **PROPAGATION**: Changes impact multiple files; propagate updates correctly.
7. **VERSION**: If the commit touches production files on `main`, bump semver in the same commit (see [Versioning](#versioning-main)).

## VERSIONING (MAIN)

Every commit on `main` that changes a **production file** must include a semver bump in **`pyproject.toml`** in the **same commit**. Do not merge or push prod changes without updating the version.

### Production files

These paths count as production (runtime, packaging, or install surface):

- `src/free_claude_code/api/`, `src/free_claude_code/cli/`, `src/free_claude_code/config/`, `src/free_claude_code/core/`, `src/free_claude_code/messaging/`, `src/free_claude_code/providers/`
- `src/free_claude_code/application/`
- `.env.example`
- `pyproject.toml` (dependencies, scripts, packaging)
- `scripts/install.sh`, `scripts/install.ps1`, `scripts/uninstall.sh`, `scripts/uninstall.ps1`, `scripts/ci.sh`, `scripts/ci.ps1`

These do **not** require a version bump on their own:

- `tests/`, `smoke/`
- Docs and assets: `README.md`, `assets/`, `AGENTS.md`, `CLAUDE.md`
- CI and repo config: `.github/`, `.gitignore`

If a single commit mixes production and non-production edits, still bump the version.

### Semver rules

Use `[project].version` as `MAJOR.MINOR.PATCH`:

- **PATCH** (`x.y.Z+1`): bug fixes, refactors with no user-visible behavior change, dependency updates, packaging/install fixes.
- **MINOR** (`x.Y+1.0`): backward-compatible features—new providers, admin fields, CLI commands, config options, or behavior additions.
- **MAJOR** (`X+1.0.0`): breaking changes—removed or renamed env vars, incompatible API/CLI/default changes, or migrations users must act on.

When unsure between PATCH and MINOR, prefer PATCH for fixes and MINOR for new capability.

### Required steps

1. Classify the change and choose the bump level.
2. Update `version` in `pyproject.toml`.
3. Run `uv lock` so `uv.lock` reflects the new package version.
4. Include the version and lockfile updates in the same commit as the production change.

Example commit on `main` after a packaging fix: bump `1.2.38` → `1.2.39`, run `uv lock`, commit together with the fix.

## SUMMARY STANDARDS

- Summaries must be technical and granular.
- Include: [Files Changed], [Logic Altered], [Verification Method], [Residual Risks] (if no residual risks then say none).

## TOOLS

- Prefer built-in tools (grep, read_file, etc.) over manual workflows. Check tool availability before use.


===== FILE hyprwm/Hyprland::AGENTS.md | stars=37448 followers=None lang=C++ bytes=3145 =====

# AGENTS.md

## Review guidelines

- Prioritize correctness, lack of regressions, performance, API stability, and code clarity and readability.
- For performance-sensitive paths, flag obvious algorithmic regressions or slow paths.
- For tests, flag missing coverage for changed or new behavior, as long as the testing framework is capable of testing it.
- For config changes (new / removed options) remind the author to make a separate wiki PR if they haven't linked one yet.
- Flag silent config breakage: e.g. changing an existing option's behavior. This is not allowed.
- Flag bad config style that breaks this project's style guidelines (further below) and suggest fixes.
- Flag bad code approaches that break this project's core code guidelines (further below) and suggest improvements.

## Style guidelines

- Code must be clang-formatted according to `.clang-format`.
- single-line if and else statements must come without braces. This rule applies only to if / else, not do / while / other.
- Avoid function bodies in headers as much as possible.
- Avoid namespace {} in source files to mark local functions. Prefer `static`.
- Prefer guards in functions and loops: `if (!cond) continue;`
- Prefer forward-declaration in headers to inclusion.
- Leave a stray `,` at the end of brace-enclosed lists to make formatting easier to read.
- Leave a `;` inside empty function bodies for formatting.
- Naming conventions:
 - class: `CMyClass`
 - struct: `SMyStruct`
 - interface: `IMyInterface`
 - class (not struct) member variables: `m_variable`
- Do not use absolute includes from `src/` in headers: instead of `#include "a/b.hpp"` use `#include "../a/b.hpp"` for example. Protocol headers do not require this.

## Core code guidelines

- Stick to good code practices:
 - Avoid complex classes / functions, prefer SRP.
 - Consider using an observer pattern via hyprutils Signals where appropriate.
 - Consider classic OOP patterns where appropriate: Strategy, Singleton, Proxy, etc.
 - Watch out for typical bad practices in code: feature envy, LSP, etc.
 - Use templating and inheritance to clean up code where appropriate.
 - For obtaining singletons, use a `UP<CClass>& myClass();` pattern inside a namespace. This can be implemented in source as making and returning a static ptr.
- Do not, under any circumstance:
 - `using namespace std;`
 - leave uninitialized primitives (int, float, etc)
- Avoid, unless absolutely necessary:
 - the C standard library. Use the C++ STL.
 - `malloc` / `free` / etc
 - C-style pointers. Use SP<> WP<> and UP<> from hyprutils. These are Shared, Weak and Unique pointers respectively. C-style pointers may be used in select scenarios (e.g. destroying fns, where it's impossible to make a mistake) but everywhere else must not be used unless necessary.
 - C-style casts. Use rc<>, sc<>, or cc<> from hyprutils. These are shorthands to equivalent C++ casts.
- Avoid:
 - violating clang-tidy (`.clang-tidy`)
 - manual C-style cleanup: `some_c_thing_new()` and `some_c_thing_free()` can be wrapped.
- Make sure to write tests for code which our Unit (`tests/`) or Integration (`hyprtester/`) tests can test.


===== FILE pcottle/learnGitBranching::CLAUDE.md | stars=33798 followers=1354 lang=JavaScript bytes=6435 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LearnGitBranching is an interactive git visualization tool for teaching git concepts through a game-like interface. It's a 100% client-side JavaScript application that simulates git operations and renders them visually using Raphael.js for SVG graphics.

## Build & Development Commands

### Setup
```bash
yarn install
```

### Building
```bash
yarn gulp fastBuild    # Fast build without tests/linting
yarn gulp build        # Full production build with tests & lint
yarn gulp watching     # Watch mode - rebuilds on file changes
```

### Testing & Linting
```bash
yarn test              # Run Jasmine test suite
yarn test:coverage     # Run tests with nyc coverage
gulp jshint            # Run JSHint linter
gulp lintStrings       # Validate internationalization strings
```

### Development Server
```bash
yarn dev               # Start Vite dev server
# After building, open index.html directly in browser
```

### Single Test Execution
```bash
# Run specific test file
npx gulp-jasmine __tests__/git.spec.js
```

## Architecture Overview

### Core Components

**GitEngine** (`src/js/git/index.js`)
- The heart of the application - simulates all git operations
- Manages the commit graph, branches, tags, refs, and HEAD
- Processes commands and updates the visualization
- Supports both git and Mercurial (hg) modes via `mode` property
- Uses EventBaton pattern for command dispatching

**Visualization System** (`src/js/visuals/`)
- `visualization.js`: Main visualization controller
- `tree.js`: Renders the commit tree using Raphael.js
- `visNode.js`, `visBranch.js`, `visTag.js`, `visEdge.js`: Individual visual components
- `animation/`: Animation system using promise chains (Q library)

**Command Processing** (`src/js/commands/index.js`, `src/js/git/commands.js`)
- Commands are defined with regex patterns, options, and execute functions
- Supports both git and Mercurial command sets
- Command delegation system allows commands to internally invoke other commands
- All git commands are simulated - they manipulate in-memory data structures

**Levels System** (`src/levels/`)
- Each level is a JavaScript module exporting level configuration
- Organized into sequences: intro, rampup, move, mixed, advanced, remote, remoteAdvanced
- Level definition includes: name, goal description, starting tree state, solution validation
- See `src/levels/index.js` for all level sequences

### Flux Architecture

The app uses a Flux-like architecture:

**Dispatcher** (`src/js/dispatcher/AppDispatcher.js`)
- Central event bus using Facebook's Flux Dispatcher
- Handles VIEW_ACTION and URI_ACTION payload sources

**Stores** (`src/js/stores/`)
- `CommandLineStore.js`: Manages command line state
- `LevelStore.js`: Tracks current level and progress
- `LocaleStore.js`: Handles internationalization
- `GlobalStateStore.js`: Global application state

**Actions** (`src/js/actions/`)
- Action creators for CommandLine, Level, Locale, and GlobalState

### UI Components

**Backbone Views** (`src/js/views/`)
- Legacy Backbone.js views for modals, dialogs, builders
- `gitDemonstrationView.js`: Shows animated git command demonstrations

**React Components** (`src/js/react_views/`)
- Modern React components for command line, toolbar, helper bars
- Command history view with syntax highlighting

### Key Patterns

**EventBaton** (`src/js/util/eventBaton.js`)
- Pattern for transferring event handling responsibility
- Used extensively for command processing and level events

**TreeCompare** (`src/js/graph/treeCompare.js`)
- Compares two commit trees for level completion validation
- Handles branch positions, commit structure, tags

**Animation Chains**
- All visual updates go through animation queue
- Uses Q promises to chain animations
- Can be disabled for testing (headless mode)

## Project Structure

```
src/
├── js/
│   ├── app/           # Application bootstrapping
│   ├── git/           # Git engine and commands
│   ├── mercurial/     # Mercurial (hg) support
│   ├── commands/      # Command parsing and execution
│   ├── level/         # Level loading and validation
│   ├── visuals/       # Visualization and animation
│   ├── views/         # Backbone views
│   ├── react_views/   # React components
│   ├── stores/        # Flux stores
│   ├── actions/       # Flux actions
│   ├── models/        # Backbone models and collections
│   ├── intl/          # Internationalization
│   ├── graph/         # Tree comparison logic
│   └── util/          # Utilities
├── levels/            # Level definitions organized by category
├── style/             # CSS files
└── template.index.html # HTML template

__tests__/             # Jasmine test specs
```

## Build Process

The gulp build process:
1. Browserify bundles all JS files (including JSX with Babel transform)
2. CSS files concatenated and minified (production)
3. Files are hashed for cache busting
4. `template.index.html` is processed with hashed filenames to generate `index.html`
5. Tests run with Jasmine, linting with JSHint

Production builds minify JS with Terser and HTML with html-minifier.

## Key Technologies

- **Backbone.js**: MVC framework (legacy parts)
- **React 17**: UI components (modern parts)
- **Flux**: Unidirectional data flow
- **Raphael.js**: SVG graphics for visualization
- **Q**: Promises for animation chains
- **jQuery/jQuery UI**: DOM manipulation and dialogs
- **Browserify + Babel**: Module bundling and JSX transform
- **Gulp**: Build automation
- **Jasmine**: Testing framework

## Testing Conventions

- Tests in `__tests__/` directory
- Headless git engine for testing (`src/js/git/headless.js`)
- Use `create.js` helper to set up test git trees
- Mock commands with `mock.js` utility
- Tests cover git operations, remote operations, levels, tree comparison

## Remote Repository Simulation

Remote operations (push/pull/fetch) are simulated by creating a separate GitEngine instance for the "origin" repository. The `o/` prefix denotes remote tracking branches.

## Internationalization

String translations in `src/js/intl/strings.js`. Use `intl.str()` and `intl.getDialog()` to access localized strings. Locale validation via `checkStrings.js`.


===== FILE blader/humanizer::AGENTS.md | stars=30976 followers=1042 lang=Python bytes=2671 =====

# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Warp, etc.) working in this repository.

## What this repo is

A portable agent skill implemented entirely as Markdown. The runtime artifact is `SKILL.md`: the agent reads its YAML frontmatter and editor prompt. There is no build step, and the repo should avoid wording that limits support to one or two harnesses.

## Key files

- `SKILL.md` — the skill itself. Portable YAML frontmatter (`name`, `description`, `license`, `metadata.version`) followed by the canonical, numbered pattern list with before/after examples. **This is the source of truth.**
- `README.md` — for humans: installation, usage, a summary table of the patterns, and a version history.
- `.claude-plugin/plugin.json` — optional Claude Code plugin manifest.
- `.claude-plugin/marketplace.json` — optional single-repo marketplace entry so `/plugin marketplace add blader/humanizer` works.
- `scripts/validate-package.py` — dependency-free package and synchronization checks used locally and in CI.

## The maintenance contract

`SKILL.md` and `README.md` must stay in sync. When you change behavior or content:

- **Patterns:** the skill currently defines **33 numbered patterns**. If you add, remove, or renumber any, update the README pattern table, its "N Patterns Detected" heading, and every cross-reference in the same change. Keep numbering stable unless you are deliberately renumbering.
- **Version:** `SKILL.md` frontmatter stores the version under `metadata.version`, `README.md` has a "Version History" section, and `.claude-plugin/plugin.json` has a `version` field. Bump them together so package metadata matches the skill. Keep the skill version under `metadata`; a top-level `version` key is not portable across Agent Skills hosts. (`marketplace.json` intentionally omits a version so `plugin.json` stays the package source of truth.)
- **Compatibility:** keep install and usage language harness-neutral. The skill should work in any agent harness that can load Markdown skill instructions; Claude Code, OpenCode, Codex, and other harnesses are examples, not limits.
- **Validation:** run `python3 scripts/validate-package.py`, `npx skills add . --list`, and `claude plugin validate .` before publishing.
- **Non-obvious fixes:** if you change the prompt to handle a tricky failure mode (a repeated mis-edit, an unexpected tone shift), add a short note to the README version history explaining what was fixed and why.

## Editing SKILL.md

- Preserve valid YAML frontmatter (formatting and indentation).
- The prompt below the frontmatter is the product. Edit it like a careful instruction document, not code.


===== FILE heroui-inc/heroui::AGENTS.md | stars=30197 followers=None lang=MDX bytes=10092 =====

# AGENTS.md

Instructions for AI agents working with the HeroUI v3 repository.

## Repository Overview

HeroUI v3 is a modern React UI library built with **Tailwind CSS v4**, organized as a **pnpm monorepo** managed by **Turborepo**. Components are built on top of [React Aria Components](https://react-spectrum.adobe.com/react-aria/) and follow a compound component pattern similar to Radix UI.

### Tech Stack

| Technology | Version | Purpose |
|---|---|---|
| Node.js | 22+ | Runtime |
| pnpm | 10.26.2 | Package manager (via corepack) |
| React | 19+ | UI framework |
| Tailwind CSS | 4.x | Styling |
| TypeScript | 5.x | Type safety |
| Turborepo | 2.x | Build orchestration |
| Storybook | Latest | Component development |
| Vitest | 4.x | Testing |
| React Aria Components | Latest | Accessibility primitives |
| tailwind-variants | Latest | Variant-based styling (includes twMerge) |

### Monorepo Structure

```
/
├── apps/
│   └── docs/              # Documentation site (Next.js + Fumadocs)
├── packages/
│   ├── react/             # Main UI library (@heroui/react)
│   │   ├── src/components/  # All components
│   │   ├── src/utils/       # Shared utilities
│   │   └── scripts/         # Build & codegen scripts
│   ├── styles/            # CSS styles & variants (@heroui/styles)
│   │   └── src/components/  # Per-component .css files
│   ├── standard/          # Shared ESLint, Prettier, TS configs
│   ├── storybook/         # Storybook configuration
│   └── vitest/            # Shared Vitest configurations
├── turbo.json
└── pnpm-workspace.yaml
```

## Commands

| Action | Command |
|---|---|
| Install dependencies | `pnpm i --hoist` |
| Build all packages | `pnpm build` |
| Build specific package | `pnpm build --filter=@heroui/react` |
| Dev (Storybook, port 6006) | `pnpm dev` |
| Dev (Docs site, port 3000) | `pnpm dev:docs` |
| Lint | `pnpm lint` |
| Typecheck | `pnpm typecheck` |
| Test all | `pnpm test` |
| Test one component | `pnpm test button` |
| Format | `pnpm run format` |
| Bump version | `pnpm version:bump` |
| Scaffold a new component | `cd packages/react && pnpm add:component ComponentName` |

## Git Commit Convention

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/) and are validated by Husky + commitlint. Pre-commit also runs `lint-staged`.

```
<type>(<scope>): <message>
```

**Allowed types:** `feat`, `feature`, `fix`, `refactor`, `docs`, `build`, `test`, `ci`, `chore`

Examples:

```
feat(components): add select component
fix(button): resolve disabled state not applying
docs: update installation guide
```

## Component Architecture

### File Structure

Each component lives in `packages/react/src/components/<component-name>/`:

```
component-name/
├── component-name.tsx          # Component implementation (uses React Aria)
├── component-name.styles.ts    # Tailwind Variants styling
├── component-name.stories.tsx  # Storybook stories
└── index.ts                    # Barrel exports
```

CSS styles live in `packages/styles/src/components/<component-name>/`.

### Creating a New Component

Always use the scaffold script:

```bash
cd packages/react
pnpm add:component ComponentName
```

Then build to update package.json exports:

```bash
pnpm build
```

### Compound Component Pattern

HeroUI uses a compound component pattern. Each component exports its sub-parts so users can compose and style them independently.

```tsx
// Context shares state/styles across parts
const ComponentContext = createContext<{slots?: ReturnType<typeof componentVariants>}>({});

// Root wraps children with context
const ComponentRoot = forwardRef(({children, className, ...props}, ref) => {
  const slots = useMemo(() => componentVariants({...}), [...]);
  return (
    <ComponentContext value={{slots}}>
      <ReactAriaPrimitive ref={ref} className={composeTwRenderProps(className, slots.base())}>
        {children}
      </ReactAriaPrimitive>
    </ComponentContext>
  );
});

// Child parts consume context
const ComponentItem = forwardRef(({className, ...props}, ref) => {
  const {slots} = useContext(ComponentContext);
  return (
    <ReactAriaPrimitive ref={ref} className={composeTwRenderProps(className, slots?.item())}>
      {props.children}
    </ReactAriaPrimitive>
  );
});
```

Compound components are exported via `Object.assign` as the default export:

```tsx
const CompoundComponent = Object.assign(ComponentRoot, {
  Item: ComponentItem,
  Trigger: ComponentTrigger,
});
export default CompoundComponent;
```

### Export Strategy

```tsx
// Named exports for compound components
export * as ComponentName from "./component-name";

// Direct exports for simple components
export {Component, type ComponentProps} from "./component";

// Always export variants
export {componentVariants, type ComponentVariants} from "./component.styles";
```

### Styling Rules

1. **Styles go in `.styles.ts` files**, never in `.tsx` files. Use `tv()` from `tailwind-variants`.
2. **Import from `tailwind-variants`**, never from `@heroui/standard`.
3. **Never use `twMerge` manually** — `tailwind-variants` already includes it.
4. **Add `"use client"` directive** at the top of every component `.tsx` file.
5. **Display names** follow: `HeroUI.ComponentName` or `HeroUI.Component.SubPart`.

### CSS / BEM Naming

Components use BEM-style CSS class names:

- **Block**: `button`, `card`, `alert`
- **Element**: `card__header`, `alert__icon`
- **Modifier**: `button--primary`, `button--lg`, `button--icon-only`

### Default Size Pattern (Critical)

All components must include default sizes in base classes so they work without explicit size props:

```css
.avatar {
  @apply relative flex size-10 shrink-0 overflow-hidden rounded-full;
  /* size-10 is the default (equivalent to --md) */
}

.avatar--sm { @apply size-8; }
.avatar--md { /* empty — this IS the default */ }
.avatar--lg { @apply size-12; }
```

### Interactive State Pattern

All interactive components must support both pseudo-classes and data attributes:

```css
.component {
  &:hover,
  &[data-hovered="true"] { @apply ...; }

  &:active,
  &[data-pressed="true"] { @apply ...; }

  &:focus-visible,
  &[data-focus-visible="true"] {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }
}
```

### React Aria className Patterns

React Aria components differ in how they accept `className`:

- **Render-prop components** (Button, Checkbox, Switch, Popover, Tooltip, Tabs, Link, Menu, etc.) — use `composeTwRenderProps(className, slots.foo())`.
- **String-only components** (Label, Text, Input, TextArea, Heading, Dialog) — pass `className` directly: `slots?.label({className})`.

### Composition Over Duplication

Do **not** create component-specific Label/Description/FieldError sub-components. Instead, compose with the existing shared primitives:

```tsx
import {Label} from "@/components/label";
import {Description} from "@/components/description";

<div className="flex items-center gap-3">
  <Checkbox id="terms"><Checkbox.Indicator /></Checkbox>
  <Label htmlFor="terms">Accept terms</Label>
</div>
```

### Tailwind Class Detection

Tailwind CSS scans files as plain text. **Never construct class names dynamically**:

```tsx
// BAD — Tailwind won't detect this
<div className={`text-${color}-600`} />
<span className={`button--${size}`} />

// GOOD — use complete class name mappings
const colorClasses = {
  blue: "text-blue-600",
  red: "text-red-600",
};
```

### Storybook

All stories must use the `"Components"` group in their title:

```tsx
export default { title: "Components/Button" };
```

Storybook is the primary dev workflow — run with `pnpm dev` (port 6006).

### Icon Library

HeroUI uses **Iconify** with **gravity-ui** as the default icon set.

## Current Components

### Completed

accordion, alert, alert-dialog, autocomplete, avatar, badge, breadcrumbs, button, button-group, card, checkbox, checkbox-group, chip, close-button, color-area, color-field, color-picker, color-slider, color-swatch, color-swatch-picker, combo-box, date-field, date-picker, date-range-picker, description, disclosure, disclosure-group, drawer, dropdown, empty-state, error-message, field-error, fieldset, form, header, input, input-group, input-otp, kbd, label, link, list-box, list-box-item, list-box-section, menu, menu-item, menu-section, meter, modal, number-field, pagination, popover, progress-bar, progress-circle, radio, radio-group, scroll-shadow, search-field, select, separator, skeleton, slider, spinner, surface, switch, switch-group, table, tabs, tag, tag-group, textarea, textfield, time-field, toast, toggle-button, toggle-button-group, toolbar, tooltip, typography

### In Progress

calendar, calendar-year-picker, range-calendar

## Non-obvious Gotchas

1. **`pnpm i` triggers builds** — The `postinstall` hook builds `@heroui/styles` and runs `typegen:docs`. If it fails, run `pnpm --filter @heroui/styles build` manually.

2. **Build order matters** — `@heroui/styles` must build before `@heroui/react`. Running `pnpm build` from root handles this via Turbo's `^build` dependency.

3. **Native addons allowlist** — The `pnpm.onlyBuiltDependencies` field in root `package.json` allows native compilation for `esbuild`, `@swc/core`, `@parcel/watcher`, etc. If this field is missing, you'll see "Ignored build scripts" warnings.

4. **No tests yet** — `pnpm test` runs but finds no test files. The Vitest config exists at `packages/vitest`.

5. **Commit hooks** — Husky runs `lint-staged` on pre-commit and `commitlint` on commit-msg. Non-conforming commits are rejected.

6. **Run checks before committing** — `pnpm lint && pnpm typecheck`

## Cursor Cloud Specific

- **Node.js v22+** is installed via binary tarball to `/usr/local/`.
- **pnpm** is activated via `corepack` — the `packageManager` field in root `package.json` declares `pnpm@10.26.2`.
- Full command reference and component architecture details are also in `CLAUDE.md`.


===== FILE pubkey/rxdb::AGENTS.md | stars=23293 followers=None lang=TypeScript bytes=25074 =====

# AGENTS.md

## Project Overview
- **Database**: RxDB (local-first, NoSQL)
- **Language**: TypeScript
- **State Management**: Reactive (RxJS Observables)
- **Paths**: Source code in `src/`, tests in `test/`, documentation in `docs-src/`.

## Tooling
- **Build All**: `npm run build`
- **Documentation Build**: `npm run docs:build`
- **Run All Tests**: `npm run test`
- **Fast Tests (Parallel)**: `npm run test:fast`
- **Fast Memory Tests**: `npm run test:fast:memory`
- **Node Tests**: `npm run test:node`
- **Browser Tests**: `npm run test:browser`
- **Performance Tests**: `npm run test:performance`
- **Lint**: `npm run lint`
- **Lint Fix**: `npm run lint:fix`
- **Check Types**: `npm run check-types`
- **Unwatch Tests**: `npm run dev`

## Code Style & Patterns
- **Language**: TypeScript
- **Formatting**: Uses ESLint. Run `npm run lint` to check and `npm run lint:fix` to auto-fix.
- **Imports**: Uses ES modules (import/export).
- **TypeScript**: Do not use enums. Prefer types instead of interfaces.
- **Errors**: Do not use `throw new Error()`. Use `throw new RxError()` instead to reduce build size and do not include full error messages in production builds. Use the error codes from `src/rx-error.ts` and add new error codes if needed like `PL1`, `PL2`. Example: `throw newRxError('PL1', { plugin });`

## Documentation Style
- SHOULD use clear, simple language.
- SHOULD use data and examples to support claims when possible.
- SHOULD be informative.
- SHOULD focus on practical, actionable insights.
- AVOID using em dashes (–) anywhere.
- AVOID constructions like "not just this, but also this".
- AVOID metaphors and cliches.
- AVOID generalizations.
- AVOID upfront warnings or notes, just the output requested.
- AVOID rhetorical questions.
- AVOID specific words like: very, really, literally, actually, certainly, probably, basically, delve, embark, enlightening, esteemed, shed light, craft, creative, imagine, realm, game-changer, unlock, discover, skyrocket, abyss, not alone, in a world where, revolutionize, disruptive, utilize, utilizing, dive deep, tapestry, illuminate, unveil, pivotal, intricate, elucidate, hence, furthermore, realm, however, harness, exciting, groundbreaking, cutting-edge, remarkable, it remains to be seen, glimpse into, navigating, landscape, stark, testament, in summary, in conclusion, moreover, boost, skyrocket, opened up, powerful, inquiries, ever-evolving.
- Review your response and ensure no em dashes.
- MUST format FAQ sections using HTML `<details>` and `<summary>` tags. Ensure there is an empty line before and after the inner markdown content so it parses correctly.
- SHOULD try to use components from the `docs-src/src/components` folder when writing docs.

## Documentation Writing Style Guide

This guide is derived from an analysis of all existing pages in `docs-src/docs/`. Older pages (2023-era) contain hype vocabulary that is now banned; when patterns conflict, follow this guide and the rules above, not legacy pages. Good style models: `articles/realm-to-rxdb-migration.md`, `webmcp.md`, `testing.md`, `rx-storage-localstorage.md`, the newer `articles/alternatives/*.md` pages.

### Frontmatter
- Exactly four fields, always in this order: `title`, `slug`, `description`, `image`. No other fields.
- `slug`: kebab-case filename plus `.html`, for example `slug: partial-sync.html`.
- `image`: `/headers/<slug-basename>.jpg`. Alternative articles use `/headers/alternatives/<slug-basename>.jpg`.
- `title`: Title Case, 40 to 80 chars, keyword first. Use a plain hyphen `-` as separator, never an em dash or `|`. Two modes: plain feature name for reference pages ("Key Compression", "RxQuery") or keyword phrase for articles ("RxDB as a Dexie.js Alternative with Mango Queries and Replication"). The H1 may differ slightly from the title.
- `description`: 1 to 2 sentences, about 120 to 160 chars, contains the primary keyword. Openers like "Compare X with RxDB." or "Learn how ...". Do not use the banned words even though older descriptions contain them.

### Page structure
- MDX component imports go between the frontmatter and the H1.
- One H1 per page. Integration and feature landing pages may use `<HeadlineWithIcon h1 icon={...}>` with an optional `subtitle`.
- Opening paragraph: define the topic in 1 to 4 sentences, bold the primary keyword on first mention, link `[RxDB](https://rxdb.info/)` on first mention in articles, and include 2 to 6 internal links. Articles add a roadmap sentence: "This page explains what X is, where it falls short, and how RxDB ...".
- Place `<RxdbLogo alt="<keyword phrase>" />` after the intro paragraph in articles. It is globally registered, no import needed.
- Article flow: What is X → why X matters or its limits → What RxDB adds (numbered `### 1. ...` subsections) → code samples → FAQ → `## Follow Up` link list.
- Alternative-article flow (`articles/alternatives/`): competitor-first intro that credits the competitor honestly → `## A Short History of X` (with `### A Brief Timeline` bold-year bullets) → `## What is RxDB?` → `## Where X Falls Short` → what RxDB adds → `## Code Sample: ...` sections → a concession section ("When X Still Makes Sense") → `## FAQ` → `## Comparison Table` with header `| Feature | X | RxDB |` (competitor column before RxDB) → `## Follow Up` paragraph plus a `More resources:` bullet list of internal links.
- Plugin and storage page flow: intro ("With the `plugin-name` plugin you can ..." or "The X [RxStorage](./rx-storage.md) is ...") → key features as bold-label bullets → `<PremiumBlock />` or `<BetaBlock since="X.0.0" />` if applicable → usage steps wrapped in `<Steps>` → options → limitations or known problems → FAQ.
- API method headings are the literal API name: `## putAttachment()`, `### awaitInitialReplication()`.
- Headings: Title Case for H2/H3. Question headings ("What is a Vector Database?") and how-to gerund headings ("Using the sharding plugin") are fine.
- End articles with `## Follow Up`: a bullet list of internal links, usually the Quickstart (`../quickstart.md`), the GitHub repo as `/code/`, the chat as `/chat/`, and related articles. A star CTA "leave a star ⭐" is allowed. Reference pages may simply end after the last technical section.

### Voice and tone: the author fingerprint

The docs have one dominant authorial voice: the maintainer, a German native speaker who writes direct, pragmatic, evidence-driven English. New pages must sound like this voice. The fingerprint below was measured on his most personally written pages (release notes, slow-indexeddb.md, why-nosql.md, downsides-of-offline-first.md, offline-first.md, leader-election.md, transactions-conflicts-revisions.md, replication.md, contribute.md, the websockets and localstorage-indexeddb articles).

**Persona and register**
- Second person "you" for the reader. "we" only in tutorial walkthroughs. Do not use "I" (it appears only in release notes and personal opinion pieces written by the maintainer).
- Present tense. Imperative for steps. Benchmark-empiricist stance: every claim invites verification ("You can reproduce all performance tests in this repo", "(lower is better)").
- Be fair to competitors: name what they do well before explaining their limits, link to their official site, and include a section on when the competitor is still the right choice.
- Be honest about RxDB tradeoffs: Pros/Cons pairs, Limitations sections, and "when not to use this" notes are a house signature.
- Back claims with specifics: concrete numbers ("saves up to 40% disk space", "3x-4x faster compared to IndexedDB"), dates, named users, GitHub issue links, and links to `rx-storage-performance.md` or benchmark repos. If no numbers exist, keep performance claims qualitative and add a link.
- Humor is dry, deadpan, and rare: state the naive solution, then refute it with facts ("Well, IndexedDB was slow in 2013 and it is still slow today. Waiting is not an option."). Playful code examples are welcome (heroes schema, 'foobar', Alice and Bob, "console.log('Long lives the king!')"). No jokes in reference sections.
- Direct reader involvement is allowed in articles: blunt commands, "Count them, I will wait..", "you did something wrong". Use sparingly.

**Rhythm and burstiness (measured)**
- Sentence length: mean 17 words, median 16, standard deviation 8 (coefficient of variation 0.45, high burstiness). About 75% of sentences have 9 to 25 words, 11 to 14% have 8 or fewer, 6 to 8% have 30 or more.
- The signature rhythm: one or two long multi-clause explanation sentences (30 to 50 words, chained with "because", "and", "which") followed by a short verdict sentence of 2 to 7 words that lands the point: "IndexedDB is slow.", "This will not work.", "Waiting is not an option.", "But there is no free lunch.", "This is done."
- Escalating repetition as an emphasis device: "the in-memory plugin was slow. Really slow, even slower than just using the indexeddb adapter."
- Paragraphs: mean 2.2 to 2.5 sentences, about 35% of paragraphs are a single sentence, fewer than 5% exceed 4 sentences. One-sentence paragraphs are used as pitch beats.
- Bullet density: roughly 1 bullet line per 3 to 4 prose sentences. Prose never runs long before a list or code block breaks it up.
- The author historically used question-then-answer transitions ("So what are the differences?"); the rules above ban rhetorical questions, so express these as statements in new pages.

**Clause preference and sentence anatomy**
- Main clause first in about 60% of sentences; about 40% start with a fronted adverbial or subordinate clause from a fixed set: "In the past,", "By default,", "To fix this,", "Because X,", "When you X,", "Instead of X,", "With X,", "On the client,".
- Favorite subordinators, in order of frequency: "because" (fronted and trailing), "when", "so that" (purpose), "which/that", "where" (all-purpose situational relative: "use cases where ..."). "as soon as" for escalation ("But as soon as your app gets bigger ..."), "while" for concessions.
- "when" vs "if": "when" for expected or recurring conditions ("When a query without a limit is done, ..."), "if" only for genuinely uncertain ones. This is the German wenn/falls split and is a core tell of the voice.
- Sentence-initial coordinators are a signature, at 1 to 2 per page: "But" (always preferred over "however"), "So", "Also", "Instead", "Therefore", "Now", and occasionally "And" for a dramatic beat ("And there we have it.").
- Tail relative "which is why ..." closes explanations: "This was confusing behavior which is why I changed the default."
- Passive and impersonal voice for change descriptions ("was renamed", "has been removed", "is now done via"); active second person for explanations and guides.
- Prefer finite clauses over participle constructions. Gerund subjects are fine ("Keeping too many deleted documents in the storage can slow down queries") but never followed by a comma.
- Prefer timeline narration ("In the past, X. Now Y.") over subjunctive conditionals. "From now on, ..." introduces new behavior.

**Recurring syntactic frames (use these)**
- "This + verb" anaphoric openers: "This means ...", "This ensures that ...", "This makes ...", "This was confusing, so ...". The most frequent frame in the corpus.
- "Notice that ...", "Keep in mind that ...", "It is recommended to ..." as caveat openers.
- "It can happen that ..." for edge cases.
- "There is/are ..." existential openers.
- "It is + adjective + to ...": "it is not possible to create a transaction between multiple maybe-offline client devices".
- "Let's say ..." to introduce examples (the author writes "Lets"; use the apostrophe in new pages).
- "Imagine ..." scenario openers for articles: "Imagine two of your users modify the same JSON document, while both are offline."
- "Same goes for ...", "Same as X, Y" for parallel cases.
- "In the following ..." to announce structure; "At first, ..." for the first step.
- "So you have a JavaScript web application that needs to ..." second-person scenario page openers.
- "Now that you know X, let's compare Y" as a bridge between sections.
- Section closers tie the technique back to RxDB with an internal link ("RxDB uses batched cursors in the [IndexedDB RxStorage](./rx-storage-indexeddb.md).") or end with "[Read more](...)" as a terminal sentence.

**Function word profile (per 1000 words of authorial prose)**
- Signature high rates: "the" 68, "you" 17, "not" 8.7, "when" 7.7, "also" 4.2, "so" 4.2, "because" 3.4, "instead (of)" 3.6, "only" 3.7, "have to" 2.7.
- Obligation modals, ranked: "have to" (dominant, everyday obligation) > "must" (hard spec requirements, sometimes typographically amplified: "the primary key MUST be set") > "should" (advice) > "need to". Hedge: "you might want to just ...".
- Characteristic small words: "no longer" (never "anymore"), "just" as downtoner, "pretty" and "way" as informal intensifiers ("way faster", "pretty easy" - articles only), "of course", "at the same time", "for now", "so called", "at first", "anyway".
- Connectives the author never uses: thus, hence, furthermore, moreover, nevertheless, additionally, consequently. "however" is rare; "But" does that job. This matches the banned-words list above.
- "stuff" and "things" appear in his informal register; allowed at most once per page in articles, never in reference pages.
- Contractions: the body prose spells things out ("do not", "cannot", "it is"). Avoid contractions except in quoted speech and marketing lines.

**Page and section endings**
- Articles end with "## Follow Up" (bullet list of internal links, star CTA allowed). Release notes end with "## You can help!". Reference pages may simply stop after the last technical section; do not pad with a summary.
- No exclamation marks in analytical prose. They are reserved for rally headings ("You can help!"), code comments ("// This works!"), and marketing lines.

### Lexical metrics (measured fingerprint)
- Vocabulary is deliberately plain and repetitive: standardized type-token ratio is about 0.37 to 0.40 per 1000-word window (6,500 distinct words over 145,000 tokens corpus-wide). Repetition of the exact technical term is preferred over elegant variation: "database" stays "database", "replication" stays "replication". Never rotate synonyms to avoid repetition.
- Hapax legomena are 37 to 45% of the vocabulary, and they are technical compounds and API names, not rare literary words. If a word would be the only fancy word on the page, cut it.
- Punctuation per 1000 words of prose: commas 37 to 48, colons about 6, parentheses 3 to 4, question marks under 2, semicolons about 0 (do not use them), exclamation marks about 0, em dashes exactly 0, ellipsis near 0.
- Commas are used lightly: no comma after short fronted adverbs ("So instead of doing that you can send data ..."), no comma between subject and verb, comma before "which" relatives is inconsistent in the corpus; default to standard English comma rules.
- Parentheses carry defaults, asides, and meta notes: "(optional)", "(default: 100)", "(lower is better)", "(for now)", "(aka offline first)".
- Single quotes as scare quotes: 'normal' applications. Backticks aggressively for any technical token, even mid-clause. Mid-sentence bold for key nouns ("**better defaults**", "**never in parallel**") and CAPS for logical emphasis ("MUST", "NOT").

### Hyphenation
- Heavy compound-building is part of the voice: "offline-first", "local-first", "real-time", "client-side", "server-side", "in-memory", "built-in", "multi-tab", "key-value", "peer-to-peer", "conflict-free".
- Ad-hoc German-style compounds appear in his prose ("browser-tabs", "find-by-query", "time-to-first"): acceptable in benchmark labels and headings, but prefer standard spacing in body text ("browser tabs").
- Compound adjectives are always hyphenated before a noun ("offline-first apps", "client-side database").
- The only dash is the spaced hyphen " - ", used in titles and timeline bullets ("**2012** - First published"). Never an em dash.

### German L1 patterns: keep the flavor, fix the errors
The author's English carries German transfer. Some of it is the voice; some of it is plain error that reviewers fix. Keep the first list, never reproduce the second.

Keep (grammatical, part of the voice):
- Sentence-initial "Also", "So", "But", "Therefore", "Instead".
- "In the past, X ... Now Y." and "From now on, ..." frames.
- "In the following ...", "At first, ...", "as soon as", "at the same time", "so called".
- "It can happen that ...", "Notice that ...".
- "when" for expected conditions, "if" for uncertain ones.
- Uncontracted forms ("do not", "cannot") and the modal ranking "have to" > "must" > "should".
- Plain, repetitive vocabulary and short verdict sentences.

Do not reproduce (authentic errors in old pages; write the correct form):
- where/were confusion: "there where some things" → "there were".
- Participle collapse: "was build" → "was built", "is send" → "is sent", "I spend one month" (past) → "I spent".
- "loose" → "lose"; "then" → "than" in comparisons; "let/lead to" (past) → "led to".
- Adjective as adverb: "works different" → "works differently", "scales pretty bad" → "scales badly", "improves performance significant" → "significantly".
- "allows to do X" → "allows you to do X" or "makes it possible to do X"; "requires to open" → "requires you to open".
- German commas: no comma between a gerund subject and its verb ("Syncing all the messages a user could write, can be done" → drop the comma); no comma before "that" ("the time has shown, that" → "has shown that").
- Dropped genitive apostrophes: "the clients device" → "the client's device", "a documents value" → "a document's value".
- "lets" → "let's"; "it's" for possession → "its".
- Quantifiers: "much small improvements" → "many small improvements", "less operations" → "fewer operations", "amount of collections" → "number of collections", "6 month ago" → "6 months ago".
- Articles: "a OPFS storage" → "an OPFS storage", "the modifyjs" → "modifyjs" (no article before bare library names).
- "how it looks like" → "what it looks like"; "different to" → "different from"; "in a later point in time" → "at a later point in time"; "In difference to" → "In contrast to".
- Literal idiom translations: "make problems" → "cause problems", "up to impossible" → "next to impossible", "in good hope" → "confident", "and backwards" → "and back".
- "has shown to be" → "has proven to be" or "has turned out to be".
- German number formatting: "1,5 years" → "1.5 years", "10.000 documents" → "10,000 documents".
- "would" inside if-clauses: "if you would now inspect" → "if you now inspect".

### Formatting
- Bold the primary keyword on first mention, product names, and key terms. Standard bullet pattern: `- **Term**: explanation`.
- Bullets use `-`. Numbered lists for ordered steps, with a bold lead: `1. **Define a schema** for every datastore. ...`.
- Code fences: prefer `ts`; `bash` for npm install commands; `json`, `sql`, `graphql` as needed. Snippets are complete and runnable, with imports. Comments inside code carry the explanation (`// Reactive query: emits a new array whenever a matching doc changes.`). Option objects use JSDoc comments with `(optional)` and `[default=...]` markers. Placeholder is `/* ... */`. Show output as `// > ...` comments.
- Canonical snippet shape: `createRxDatabase` → `addCollections` with an inline JSON schema (string primary key with `maxLength: 100`) → insert → `.find({ selector }).$.subscribe(...)`.
- Inline code for API names, options, operators (`$gt`), field names (`_rev`), and counts like `10k`.
- Images are centered raw HTML: `<p align="center"><img src="./files/x.png" alt="keyword phrase" width="450" /></p>`. Alt text is a short keyword phrase. Use `className`, not `class`.
- Internal links are relative with the `.md` extension: `[RxStorage](./rx-storage.md)`, `[replication](../replication.md)` from articles. Site-root links for non-doc pages: `/premium/`, `/code/`, `/chat/`. Anchor text is a descriptive keyword phrase, never "click here". No UTM parameters.
- Link densely: nearly every first mention of an RxDB concept links to its page. Repeat links to canonical pages (replication, rx-storage, quickstart, offline-first) are fine.
- Admonitions `:::note` and `:::warning` (optionally titled) sparingly; not part of the default template.
- Comparison tables may use ✅ / ❌ / ⚠️ cells.
- Emoji only where functional: 👑 always accompanies "RxDB Premium" links, ⭐ for the star CTA, ✅/❌/⚠️ in tables. Never decorative emoji in prose.
- FAQ answers open with a "Yes." or "No." verdict, then 2 to 5 sentences with a bold internal link like `**[RxDB](./rx-database.md)**`. Questions are phrased as real search queries.

### Components (import from `@site/src/components/...`)
- `<Steps>` wraps a run of `###` step headings, each heading followed by a short sentence and a code block.
- `<Tabs>` wraps headings that become tab labels; can nest inside `<Steps>`.
- `<PremiumBlock />` after the intro on premium plugin pages.
- `<BetaBlock since="17.0.0" />` for beta features.
- `<PerformanceChart title="Browser Storages" data={PERFORMANCE_DATA_BROWSER} metrics={PERFORMANCE_METRICS} />` with data from `performance-data`.
- `<VideoBox videoId="..." title="..." duration="m:ss" />` inside `<center>`.
- `<QuoteBlock author="..." year="..." sourceLink="...">quote</QuoteBlock>` for cited quotes.
- `<HeadlineWithIcon h1 icon={<IconX />}>Title</HeadlineWithIcon>` for icon headlines.
- `<RxdbLogo alt="..." />` is global and needs no import.

### Terminology and spelling
- US English ("behavior", "optimize", "synchronize"). The corpus has rare UK slips ("initialisation", "realised", "optimisation"); do not copy them. Oxford comma throughout.
- Correct casing: JavaScript, TypeScript, Node.js, IndexedDB, NoSQL, RxJS, CouchDB, GraphQL, WebSocket, WebRTC, SQLite, WebAssembly (WASM), SharedWorker, OPFS (expand "Origin Private File System" on first use), localStorage (as the API; the corpus also has "LocalStorage" and "Localstorage" - use "localStorage"). The corpus has lapses ("javascript", "nodejs", "pouchdb" lowercase); write the correct casing in new pages.
- RxDB terms: RxDatabase, RxCollection, RxDocument, RxQuery, RxSchema, RxStorage, RxState, and "Sync Engine" (capitalized, linked to `./replication.md`).
- "local-first" and "offline-first" are hyphenated and lowercase in prose, capitalized as "Local-First"/"Offline-First" in headings and bullet labels. Prefer "local-first" in new pages and link it to `./articles/local-first-future.md` or `./offline-first.md`.
- "realtime" is written as one word in prose ("realtime replication", "realtime database"); "Real-Time" appears in titles and subtitles. Do not write "real time" as two unhyphenated words.
- Always write "disk" for hard drive storage ("saves to disk", "disk space"). Older pages contain the misspelling "disc"; do not copy it, and correct it to "disk" when you edit a passage that contains it.
- Numbers: backticked shorthand for counts and limits (`10k` documents, `2k`), bold for percentages ("**43%** faster"), US date format ("May 1, 2027"), period as decimal separator, comma as thousands separator.
- RxDB one-liner for "What is RxDB" sections: "RxDB (Reactive Database) is a local-first, NoSQL database for JavaScript applications". Follow with the runtime list: browser, Node.js, Electron, React Native, Capacitor, Deno, and Bun.
- Query language is described as "MongoDB-style (Mango) queries".
- Recurring vocabulary that carries the voice: "out of the box", "under the hood", "battle-tested", "first-class", "vendor lock-in", "source of truth", "The trouble starts when ...", "falls short", "bite back", "Switching storages is a configuration change, not a rewrite". Reuse these; do not invent new marketing vocabulary.

### SEO
- The primary keyword appears in the title, slug, description, H1, bolded in the first paragraph, in several H2s, and in image alt text.
- Cross-link sibling articles to knit the cluster together (framework articles link each other; alternative articles link `local-first-future.md`, `realtime-database.md`).
- FAQ `<details>` questions target long-tail search queries.



## Development Workflow

After making any code changes, run these checks in order and fix any issues before finishing:

```sh
# 1. Lint JavaScript/TypeScript files
npm run lint

# 2. Check TypeScript types
npm run check-types

# 3. Build source files
npm run build

# 4. Run fast memory tests
npm run test:fast:memory
```

## Changelog Rule
- Whenever you add a testcase or implement a FIX, add a changelog entry file under `orga/changelog/`.
- Prefer including a link to the root issue or pull request in that changelog line.


## Not allowed edits

- Do never edit anything in the `/docs` folder. This folder is generated only. The documentation page sources are in `/docs-src`, edit these instead.


===== FILE google/adk-python::AGENTS.md | stars=20875 followers=None lang=Python bytes=1420 =====

## Project Overview

The Agent Development Kit (ADK) is an open-source, code-first Python toolkit for building, evaluating, and deploying sophisticated AI agents.

### Key Components

- **Agent**: Blueprint defining identity, instructions, and tools.
- **Runner**: Stateless execution engine that orchestrates agent execution.
- **Tool**: Functions/capabilities agents can call.
- **Session**: Conversation state management.
- **Memory**: Long-term recall across sessions.
- **Workflow** (ADK 2.0): Graph-based orchestration of complex, multi-step agent interactions.
- **BaseNode** (ADK 2.0): Contract for all nodes, supporting output streaming and human-in-the-loop steps.
- **Context** (ADK 2.0): Holds execution state and telemetry context mapped 1:1 to nodes.

For details on how the Runner works and the invocation lifecycle, please refer to the `adk-architecture` skill and the referenced documentation therein.

## ADK Knowledge, Architecture, and Style

Skills related to ADK development are in `.agents/skills/`.

## Project Architecture

For detailed architecture patterns, component descriptions, and core interfaces, please refer to the **`adk-architecture`** skill at `.agents/skills/adk-architecture/SKILL.md`.

## Development Setup

The project uses `uv` for package management and Python 3.10+. Please refer to the **`adk-setup`** skill at `.agents/skills/adk-setup/SKILL.md` for detailed instructions.


===== FILE mksglu/context-mode::CLAUDE.md | stars=19319 followers=None lang=TypeScript bytes=4647 =====

# context-mode — MANDATORY routing rules

context-mode MCP tools available. Rules protect context window from flooding. One unrouted command dumps 56 KB into context.

## Think in Code — MANDATORY

Analyze/count/filter/compare/search/parse/transform data: **write code** via `ctx_execute(language, code)`, `console.log()` only the answer. Do NOT read raw data into context. PROGRAM the analysis, not COMPUTE it. Pure JavaScript — Node.js built-ins only (`fs`, `path`, `child_process`). `try/catch`, handle `null`/`undefined`. One script replaces ten tool calls.

## BLOCKED — do NOT attempt

### curl / wget — BLOCKED
Intercepted and replaced with error. Do NOT retry.
Use: `ctx_fetch_and_index(url, source)` or `ctx_execute(language: "javascript", code: "const r = await fetch(...)")`

### Inline HTTP — BLOCKED
`fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, `http.request(` — intercepted. Do NOT retry.
Use: `ctx_execute(language, code)` — only stdout enters context

### WebFetch — BLOCKED
Use: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)`

## REDIRECTED — use sandbox

### Bash (>20 lines output)
Bash ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`.
Otherwise: `ctx_batch_execute(commands, queries)` or `ctx_execute(language: "shell", code: "...")`

### Read (for analysis)
Reading to **Edit** → Read correct. Reading to **analyze/explore/summarize** → `ctx_execute_file(path, language, code)`.

### Grep — may flood context
Use `ctx_execute(language: "shell", code: "grep ...")` in sandbox.

## Tool selection

0. **MEMORY**: `ctx_search(sort: "timeline")` — after resume, check prior context before asking user.
1. **GATHER**: `ctx_batch_execute(commands, queries)` — runs all commands, auto-indexes, returns search. ONE call replaces 30+. Each command: `{label: "header", command: "..."}`.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — all questions as array, ONE call (default relevance mode).
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — sandbox, only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — store in FTS5 for later search.

## Parallel I/O batches

For multi-URL fetches or multi-API calls, **always** include `concurrency: N` (1-8):

- `ctx_batch_execute(commands: [3+ network commands], concurrency: 5)` — gh, curl, dig, docker inspect, multi-region cloud queries
- `ctx_fetch_and_index(requests: [{url, source}, ...], concurrency: 5)` — multi-URL batch fetch

**Use concurrency 4-8** for I/O-bound work (network calls, API queries). **Keep concurrency 1** for CPU-bound (npm test, build, lint) or commands sharing state (ports, lock files, same-repo writes).

GitHub API rate-limit: cap at 4 for `gh` calls.

## Subagent routing

Routing block auto-injected into subagent prompts. Bash-type subagents upgraded to general-purpose. No manual instruction needed.

## Output

Write artifacts to FILES — never inline. Return: file path + 1-line description.
Descriptive source labels for `ctx_search(source: "label")`.

## Session Continuity

Skills, roles, and decisions persist for the entire session. Do not abandon them as the conversation grows.

## Memory

Session history is persistent and searchable. On resume, search BEFORE asking the user:

| Need | Command |
|------|---------|
| What were we working on? | `ctx_search(queries: ["summary"], source: "compaction", sort: "timeline")` |
| What was the first request? | `ctx_search(queries: ["prompt"], source: "user-prompt", sort: "timeline")` |
| What did we decide? | `ctx_search(queries: ["decision"], source: "decision", sort: "timeline")` |
| What NOT to repeat? | `ctx_search(queries: ["rejected"], source: "rejected-approach")` |
| What constraints exist? | `ctx_search(queries: ["constraint"], source: "constraint")` |

DO NOT ask "what were we working on?" — SEARCH FIRST.
If search returns 0 results, proceed as a fresh session.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call `ctx_stats` MCP tool, display full output verbatim |
| `ctx doctor` | Call `ctx_doctor` MCP tool, run returned shell command, display as checklist |
| `ctx upgrade` | Call `ctx_upgrade` MCP tool, run returned shell command, display as checklist |
| `ctx purge` | Call `ctx_purge` MCP tool with confirm: true. Warns before wiping knowledge base. |

After /clear or /compact: knowledge base and session stats preserved. Use `ctx purge` to start fresh.


===== FILE udecode/plate::AGENTS.md | stars=16444 followers=None lang=TypeScript bytes=11515 =====

<!-- Generated by Skiller -->


<!-- Source: .agents/AGENTS.md -->

- `.agents/AGENTS.md` and `.agents/rules/*.mdc` are source of truth. After editing them, run `pnpm install` to sync. Never edit `SKILL.md` directly.
- In all interactions and commit messages, be extremely concise and sacrifice grammar for the sake of concision.
- Answer in English by default. Switch languages only when the user explicitly asks for another language.
- Prefer the best long-term architecture fix over the nearest local patch. If the real fix is an API or abstraction change, do that.

## Git

- **Git:** Never git add, commit, push, or create PR unless the user explicitly asks, or the active command/skill explicitly requires it.
- **Open PR follow-up:** If the current branch already has an open PR and you make any change, treat that PR as explicit authorization to commit and push the entire checkout before handoff. Do not leave local-only follow-up changes on an open PR branch.
- **Push scope:** When you do commit and push, include unrelated dirty files outside src; those are often manual user changes or synced skill/docs updates, so do not silently leave them behind.
- **PR:** Before creating or updating a PR, run `check`. If it fails, stop and fix it or report the blocker. Do not open a PR with failing `check` unless the user explicitly says to.
- **PR branch:** If the user explicitly says to open or create a PR, do not ask for confirmation. If the current branch is `main`, create a new `codex/` branch first, then commit/push/open the PR. If already on a non-`main` branch, proceed directly.
- **Merge override:** If the user explicitly says to merge it, do it. Do not wait for CI to turn green, do not ask again, and use admin merge if that is what it takes.
- Dirty workspace: Never pause to ask about unrelated local changes. Continue work and ignore unrelated diffs.
- Never browse GitHub files. For library/API questions or unfamiliar deps, inspect the repo at `..`; if missing, clone `https://github.com/{owner}/{repo}.git` to `../{repo-name}`.

## Packages

- DX: Optimize for the absolute best developer experience. JSDoc must be first-class for agents. Every API surface should be intuitive for both humans and AI agents.
- Docs: NEVER write changelog-style language ("has been removed", "new feature", "previously", "now supports"). Docs are user-facing reference for the LATEST state only. Write as if no prior version exists. No migration notes, no "what changed" — just document what IS. Follow `.agents/rules/docs-creator.mdc` for writing tone/structure.
- Templates: `templates/**` is CI-controlled output. Never manually edit or commit template source, manifests, or lockfiles. Fix the source registry, package, or workflow inputs and let CI regenerate templates. If local verification rewrites template files, restore them before handoff.
- Barrels: If you change package exports, move public files, add/remove files under exported folders, or CI says `pnpm brl` produced changes, run `pnpm brl` before final verification/commit and include the generated barrel updates.
- Do not write TDD cases for dead code/legacy removal assertions (for example: "should not contain old API X anymore"). Remove the dead path directly and keep tests focused on current behavior.
- Prefer inline when used once; extract constants only when reused.

## Tooling

- Never run `build:registry` outside CI. Registry build output is automated by CI and does not belong in local agent commits.
- If typecheck/build/dev suddenly blows up with missing-module or package-resolution garbage that does not match the current diff, run `pnpm run reinstall` once before deeper debugging.
- Treat local-only React runtime weirdness as install corruption first, not product code:
  - `Invalid hook call`
  - `resolveDispatcher()` / null dispatcher crashes
  - package-local `node_modules/react` or `node_modules/react-dom` paths under `packages/*`
  - mixed `.bun` and `.pnpm` React paths in the same failing stack
- If `pnpm test`, `bun test`, or `pnpm check` suddenly fails with those signals and the failure does not line up with the current diff, run `pnpm run reinstall` once before blocking on the task.
- `pnpm run reinstall` is the repo reset button: it deletes root/workspace/app `node_modules`, `.turbo`, `apps/www/.next`, and `tsconfig.tsbuildinfo`, then runs `pnpm install`.
- Do not use `pnpm run reinstall` as a lazy substitute for fixing real code errors.
- For `react-dnd` / DnD fixes, do not treat a follow-up Bun `Invalid hook call`, `resolveDispatcher()`, or mixed `.bun` + `.pnpm` React stack as proof the DnD fix is wrong. In this repo, run `pnpm run reinstall` once before reopening the diagnosis; that failure shape is usually local env rot, not duplicate deps or broken DnD logic.

## Skill

Use those skills when relevant:

- `autogoal` for any prompt with a verifiable and quantitative outcome. Always use
  the autogoal skill before durable work when the task has a measurable completion
  threshold
- `orchestrator` when the current thread should route per-branch work to child threads instead of executing locally
- `task` for normal repo task execution
- `major-task` for heavyweight architecture, framework comparison, migration, benchmark, or proposal work
- `clawsweeper` f[text](cid:f_mpqm0jua0)or Slate issue-ledger triage, duplicate/stale/invalid classification, small high-confidence issue processing, and exact claim sync
- `clawpatch` for Clawpatch init/map/review/report/fix/revalidate workflows
- `editor-test-harvester` for mining external editor repositories for portable editor-behavior tests, Slate v2 coverage gaps, and copy/refactor/create decisions
- `editor-harvest-plan` for turning an `editor-test-harvester` result into a lane-specific Slate v2 or Plate execution plan
- `sync-plate-ui` for fork-aware Plate UI registry component syncs into downstream apps like Potion, including status, planning, review, dashboard, and accepted-row apply workflows
- `release-lanes` for beta/latest release lane maintenance, promote, direct main-to-next sync, beta pre-mode, and npm/GitHub release verification
- `sync-main-to-next` for the fast direct `main -> next` release-lane sync wrapper without promotion or autoreview ceremony
- `tdd`
- @.agents/rules/changeset.mdc when updating packages to write a changeset before completing
- @.agents/rules/plate-plan.mdc when defining or updating editor-behavior law, authority maps, protocol rows, or parity coverage

Plate-specific CE exclusions:

- Do not install or reference these by default in this repo unless the user explicitly asks: `data-integrity-guardian`, `data-migration-expert`, `data-migrations-reviewer`, `schema-drift-detector`, `deployment-verification-agent`, `dhh-rails-reviewer`, `kieran-rails-reviewer`, `kieran-python-reviewer`, `previous-comments-reviewer`, `pr-comment-resolver`, `figma-design-sync`.
- Reason: Plate is a framework/editor repo. Data migration, Rails, deployment, PR-thread, and Figma workflow agents are mostly overkill or the wrong shape here.

Goal plans:

- For issue-backed goal work, start the filename with the ticket number.
  Example: `docs/plans/DEV-4510-fix-schema.md`
- For non-ticket goal work, keep the date-based format.
  Example: `docs/plans/2026-02-07-fix-schema.md`

Browser usage:

- When updating `content/**`, `apps/www/**`, or `packages/**`, start the relevant dev server and verify the affected route, UI, or package-facing behavior with `[@Browser](plugin://browser@openai-bundled)` before handoff. If the surface has no runnable browser path or the server/browser is blocked, say that explicitly.
- Always try `[@browser-use](plugin://browser-use@openai-bundled)` first for browser usage.
- Do not substitute Puppeteer, standalone Playwright, or raw Chrome DevTools for browser usage.
- For Plate registry/browser proof, prefer `/blocks/[id]-demo` over docs wrappers when that standalone demo route exists.

## Commands

### Slate v2 sibling repo

- In `.tmp/slate-v2` dir, keep `bun check` fast: lint, typecheck, and unit/package tests only.
- Do not put `bun test:integration-local` in `bun check`; it is a closure/release gate, not an iteration gate.
- Use `bun check:full` when a local full browser sweep is needed.
- `bun check:full` must include release-proof guards before the full browser sweep: release discipline, slate-browser proof contracts, scoped mobile proof, persistent-profile soak, then `bun test:integration-local`.
- Use `bun test:mobile-device-proof:raw` only on a machine/device lane that can provide real Appium Android/iOS proof artifacts. Do not let semantic mobile handles or Playwright mobile viewport rows satisfy raw-device claims.
- During editor-kernel/browser work, use focused package tests and focused Playwright greps first.
- Run `bun test:integration-local` only before marking an architecture/browser plan `done`, before a release-quality browser claim, or when explicitly requested.

### Development

Default to source-first typecheck. Do not build packages just to run types unless the repo script or failure proves the typecheck graph still resolves built `dist` output.

If typecheck fails with stale workspace-package declarations, source/dist split-brain, or unresolved package exports, first inspect the package/app `paths` and source-entry setup. Build only when the affected surface intentionally validates release artifacts or still has no source-first typecheck path.

If a local-only build/runtime/test failure points at corrupted files under `node_modules/.bun`, mixed `.bun` / `.pnpm` React installs, package-local `node_modules/react*` symlinks, `Invalid hook call`, or other non-versioned env state while CI is green, clean local env before changing repo code: run `pnpm run reinstall` once, then rerun the exact failing command. If the failure shape changes or disappears, it was local env rot. If not, go back to normal debugging.

**Required sequence for type checking modified packages:**

1. `pnpm install` - Install dependencies when needed by the task or lockfile state.
2. `pnpm turbo typecheck --filter=./packages/modified-package` - Run source-first package type checking.
3. If that fails because the graph resolves built output, fix the source-entry or `paths` setup when that is the right long-term shape.
4. Build only when checking artifact output, package exports, or a package that intentionally has no source-first typecheck path.
5. `pnpm lint:fix` - Auto-fix linting issues.

**For multiple modified packages:**

```bash
# Typecheck multiple specific packages through their source graph
pnpm turbo typecheck --filter=./packages/core --filter=./packages/utils

# Lint multiple packages
pnpm lint:fix
```

**Alternative approaches:**

```bash
# Typecheck since last commit
pnpm turbo typecheck --filter='[HEAD^1]'

# Typecheck all changed packages in current branch
pnpm turbo typecheck --filter='...[origin/main]'

# For workspace-specific operations
pnpm --filter @platejs/core typecheck
pnpm --filter @platejs/core lint:fix
```

**Full project commands (use only if needed, these are very slow):**

- `pnpm build` - Build all packages (only use when necessary)
- `pnpm typecheck` - Root package typecheck. It should use source-first package graphs; if it needs a build, treat that as source-entry debt unless the check is explicitly artifact-facing.
- `bun run test` - Run the fast default test suite during iteration
- `bun test` - Run the full test suite only at the end of the complete task


===== FILE Arindam200/awesome-ai-apps::CLAUDE.md | stars=13265 followers=None lang=Python bytes=7168 =====

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a comprehensive collection of practical LLM-powered application examples, tutorials, and recipes organized by complexity and use case. The repository contains 70+ example projects demonstrating various AI frameworks and patterns.

## Project Categories

Projects are organized into six main categories:

1. **starter_ai_agents/** - Quick-start boilerplate examples for learning different AI frameworks (Agno, OpenAI SDK, LlamaIndex, CrewAI, PydanticAI, LangChain, AWS Strands, Camel AI, DSPy, Google ADK)
2. **simple_ai_agents/** - Straightforward, single-purpose agents (finance tracking, web automation, newsletter generation, calendar scheduling, etc.)
3. **mcp_ai_agents/** - Projects using Model Context Protocol for semantic RAG, database interactions, and external tool integrations
4. **memory_agents/** - Agents with persistent memory capabilities using frameworks like GibsonAI Memori
5. **rag_apps/** - Retrieval-Augmented Generation examples with vector databases and document processing
6. **advance_ai_agents/** - Complex multi-agent workflows and production-ready applications (research agents, job finders, meeting assistants, etc.)
7. **course/** - Structured learning materials, including the complete AWS Strands course (8 lessons)

## Common Development Commands

### Running Individual Projects

Each project is self-contained with its own dependencies. Navigate to the specific project directory first:

```bash
cd <category>/<project_name>
```

### Installing Dependencies

Projects use either `requirements.txt` or `pyproject.toml`:

```bash
# For requirements.txt projects
pip install -r requirements.txt

# For pyproject.toml projects (newer projects)
pip install -e .
# or with uv (preferred for faster installs)
uv pip install -e .
```

### Running Projects

Most projects use simple Python execution:

```bash
python main.py
# or
python app.py
```

Some projects (especially RAG and advanced agents) use Streamlit:

```bash
streamlit run app.py
```

### Environment Configuration

All projects require environment variables for API keys. Each project has a `.env.example` file. Copy it to `.env` and add your keys:

```bash
cp .env.example .env
# Then edit .env with your API keys
```

Common API keys used across projects:
- `NEBIUS_API_KEY` - Nebius Token Factory inference provider (used extensively)
- `OPENAI_API_KEY` - OpenAI models
- `GITHUB_PERSONAL_ACCESS_TOKEN` - For GitHub MCP agents
- `SGAI_API_KEY` - ScrapeGraph AI for web scraping agents
- `MEMORI_API_KEY` - GibsonAI Memori for memory-enabled agents

## High-Level Architecture

### Multi-Stage Workflow Pattern

Advanced agents (in `advance_ai_agents/`) typically use a multi-stage workflow pattern with specialized sub-agents:

```python
class ResearchWorkflow(Workflow):
    searcher: Agent  # Gathers information
    analyst: Agent   # Analyzes findings
    writer: Agent    # Produces final output
```

Example: `advance_ai_agents/deep_researcher_agent/agents.py`

### MCP Integration Pattern

MCP agents use the Model Context Protocol to integrate external tools:

```python
async with MCPServerStdio(
    params={
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["TOKEN"]}
    }
) as server:
    agent = Agent(mcp_servers=[server], ...)
```

Example: `mcp_ai_agents/github_mcp_agent/main.py`, `mcp_ai_agents/mcp_starter/main.py`

### Framework-Specific Patterns

**Agno Framework** (most common):
- Uses `Agent` class with tools, model, and instructions
- Supports workflow orchestration via `Workflow` class
- Examples: `starter_ai_agents/agno_starter/`, `advance_ai_agents/deep_researcher_agent/`

**OpenAI Agents SDK**:
- Uses async `Runner.run()` with agents
- Examples: `starter_ai_agents/openai_agents_sdk/`, `mcp_ai_agents/mcp_starter/`

**AWS Strands**:
- Complete course available in `course/aws_strands/`
- Covers basic agents, session management, MCP, multi-agent patterns, observability, and guardrails

**LangChain/LangGraph**:
- Graph-based workflows with state management
- Examples: `starter_ai_agents/langchain_langgraph_starter/`

## Contributing Guidelines

### Adding New Projects

1. Create an issue describing the project first
2. Submit ONE project per Pull Request
3. Place in appropriate category folder (see `CONTRIBUTING.md:46-52`)
4. Use snake_case naming (e.g., `finance_agent`, `blog_writing_agent`)
5. Must include a `README.md` following the template in `.github/README_TEMPLATE.md`
6. Include either `requirements.txt` or `pyproject.toml` (pyproject.toml preferred)
7. Provide `.env.example` file - never commit secrets
8. Use code formatter (Black or Ruff) for consistent style

### Project README Requirements

Each project README must include:
- Clear description of what the agent does
- Prerequisites (Python version, required API keys)
- Installation steps
- Usage instructions with example queries/commands
- Technical details (frameworks used, models)

## AWS Strands Course Structure

Located in `course/aws_strands/`, this is an 8-lesson progressive course:

1. **01_basic_agent** - First agent with simple tools
2. **02_session_management** - Persistent conversations and state
3. **03_structured_output** - Extract structured data with Pydantic
4. **04_mcp_agent** - External tool integration via MCP
5. **05_human_in_the_loop_agent** - Request human input/approval
6. **06_multi_agent_pattern/** - Advanced multi-agent systems
   - `06_1_agent_as_tools` - Orchestrator with specialized agents
   - `06_2_swarm_agent` - Dynamic agent handoffs
   - `06_3_graph_agent` - Graph-based workflows
   - `06_4_workflow_agent` - Sequential pipelines
7. **07_observability** - OpenTelemetry and Langfuse monitoring
8. **08_guardrails** - Safety measures and content filtering

Each lesson builds on the previous, with complete working examples.

## Key Technical Notes

- **Python Version**: Requires Python 3.10 or higher (specified in most pyproject.toml files)
- **Primary AI Provider**: Nebius Token Factory is used extensively across examples for inference
- **Dependency Management**: Newer projects use `uv` for faster package installation
- **MCP Tools**: Many agents integrate with external services via MCP (GitHub, databases, custom servers)
- **Streaming UI**: Streamlit is the standard for web-based agent interfaces
- **Memory Systems**: GibsonAI Memori is the primary memory provider for context retention
- **Web Scraping**: ScrapeGraph AI is used for intelligent web data extraction

## Common Frameworks by Category

- **Starter**: Agno, OpenAI SDK, LlamaIndex, CrewAI, PydanticAI, LangChain, AWS Strands, Camel AI, DSPy, Google ADK
- **Simple**: Agno (most common), Mastra AI, browser-use
- **MCP**: OpenAI SDK, AWS Strands, custom MCP servers
- **Memory**: Agno with GibsonAI Memori, AWS Strands with Memori
- **RAG**: LlamaIndex, LangChain, Agno, CrewAI with Qdrant/vector stores
- **Advanced**: Agno workflows, CrewAI multi-agent, Google ADK, FastAPI services


===== FILE Automattic/wp-calypso::CLAUDE.md | stars=12635 followers=None lang=TypeScript bytes=626 =====

@AGENTS.md

- CRITICAL: Preserve existing curly quotes and apostrophes (“” ‘’) exactly as they appear in the source. Do NOT replace them with unicode escape sequences (\u2019, etc.) or straight ASCII equivalents (', "). To do that, when editing strings that contain a mix of straight quote delimiters and curly quotes/apostrophes inside, avoid including the string delimiters in the old_string/new_string of the Edit tool. Instead, match on a unique inner substring that doesn't include the delimiters. This prevents the Edit tool from inadvertently converting straight quote delimiters to curly quotes or vice versa.


===== FILE spencermountain/compromise::AGENTS.md | stars=12144 followers=None lang=JavaScript bytes=4554 =====

# AGENTS.md — using compromise

Guidance for AI coding agents (and humans) writing code with **compromise**, a rule-based English
NLP library. This file is the map; the linked docs are the territory. Prefer them over guessing —
the published docs at observablehq.com are interactive notebooks and do not render as readable text.

## Read these first

| File | What's in it |
|---|---|
| [docs/concepts.md](docs/concepts.md) | the document/View/Term model, **mutability**, build tiers — the mental model |
| [docs/match-syntax.md](docs/match-syntax.md) | the `.match()` mini-language (`#Tag`, `[capture]`, `(a\|b)`, `~fuzzy~`, `{root}`, …) |
| [docs/tags.md](docs/tags.md) | the complete, valid part-of-speech tagset |
| [docs/api.md](docs/api.md) | every method, signature, and one-line description |
| [docs/recipes.md](docs/recipes.md) | copy-paste solutions to common tasks |
| [llms-full.txt](docs/llms-full.txt) | all of the above concatenated into one file |
| [docs/SKILL.md](docs/SKILL.md) | example skill for using compromise in a coding agent |

## 30-second mental model

```js
import nlp from 'compromise'

let doc = nlp('she sells seashells by the seashore.')  // parse → a View of the whole document
doc.verbs().toPastTense()                               // select verbs, transform them (mutates doc)
doc.text()                                              // 'she sold seashells by the seashore.'
```

- `nlp(text)` returns a **View**. Almost every method returns a View, so calls **chain**.
- **Find** with `.match()`, `.has()`, `.if()`, or named selections like `.people()`, `.numbers()`.
- **Transform** with `.toPastTense()`, `.replace()`, `.tag()`, `.normalize()`, etc.
- **Output** with `.text()`, `.json()`, `.out('array')`, `.debug()`.

## Rules that prevent most mistakes

1. **Transforms mutate the document in place.** The View they return is the *selection*, not the
   whole doc. Read the final result from the original variable:
   ```js
   let doc = nlp('I walk to work')
   doc.verbs().toPastTense()
   doc.text()                       // ✅ 'I walked to work'
   // ❌ nlp('I walk to work').verbs().toPastTense().text()  →  'walked work' (selection only)
   ```
   Use `.clone()` to transform a copy without touching the original.

2. **Only real tags work.** A `#Tag` that isn't in [docs/tags.md](docs/tags.md) matches **nothing,
   silently**. Frequent inventions that are NOT tags: `#Name`, `#Location`, `#Subject`, `#Object`,
   `#Adj`, `#Time` (it's `#Date`/`#Time`… check the list). When in doubt, grep [docs/tags.md](docs/tags.md).

3. **The match-syntax is not regex.** It matches whole words/terms. `+ * ? . ^ $` mean term-level
   things; for character-level patterns use a `/regex/` token. See [docs/match-syntax.md](docs/match-syntax.md).

4. **Sentences are the ceiling.** Matches don't cross sentence boundaries. Use the
   [paragraphs plugin](plugins/paragraphs) for multi-sentence matching.

5. **`compromise` is the full build.** Import `compromise` (or `compromise/three`) to get
   `.people()`, `.numbers()`, `.verbs()`, etc. `compromise/two` has tags but no named selections;
   `compromise/tokenize` (`/one`) has no tags at all.

## Not supported (don't try)

- Nested match groups: `'(modern (major|minor))? general'` — chain `.match()` calls instead.
- A grammar/dependency parse tree — transforms are heuristic.
- Slash-joined matching — `nlp('eats/shoots/leaves')` splits on the slash.

## Plugins & extension

```js
nlp.plugin({
  words: { kermit: 'FirstName' },         // add lexicon entries
  tags:  { Muppet: { isA: 'Person' } },   // extend the tagset graph
  api:   (View) => { View.prototype.myMethod = function () { return this } },
})
```
Or the lightweight forms: `nlp(text, { kermit: 'FirstName' })` and `nlp.addWords({...})`.
Official plugins live in [`plugins/`](plugins) (dates, stats, syllables, wikipedia, paragraphs).

## Debugging a wrong result

```js
doc.debug()        // prints how every word was tagged — start here
doc.json()         // full structured data
nlp.verbose(true)  // log the tagger's decision-making
```

## Repo / contributor notes

- Source is layered `src/1-one` → `src/4-four` (tokenize → tags → selections → sense). The default
  entry is `src/three.js`.
- Tests: `npm test` (tape). Build: `npm run build` (rollup). Lint: `npm run lint`.
- Regenerate the machine docs after changing types or the tagset: `node ./scripts/docs.js`
  (writes `docs/tags.md`, `docs/api.md`, `llms-full.txt`). The other docs are hand-written.


===== FILE run-llama/liteparse::AGENTS.md | stars=11775 followers=None lang=Rust bytes=8403 =====

# LiteParse - Agent Documentation

> This file provides comprehensive context for AI coding agents working on this codebase.

## Project Overview

**LiteParse** is an open-source PDF parsing library written in **Rust**, focused on fast, lightweight document processing with spatial text extraction. It runs entirely locally with zero cloud dependencies by default.

Language bindings are provided for **Node.js/TypeScript** (via napi-rs), **Python** (via PyO3), and **WebAssembly** (via wasm-bindgen).

### Key Capabilities
- **Spatial text extraction** with precise bounding boxes
- **Flexible OCR** (built-in Tesseract or pluggable HTTP servers)
- **Multi-format support** (PDFs, DOCX, XLSX, PPTX, images via conversion)
- **Multi-language bindings**: Rust, Node.js/TypeScript, Python, Browser (WASM)
- **CLI** available from all installation methods (`cargo`, `npm`, `pip`)

## Directory Structure

```
liteparse/
├── crates/
│   ├── liteparse/          # Core Rust library + CLI binary
│   │   └── src/
│   │       ├── main.rs         # CLI entry point (clap)
│   │       ├── lib.rs          # Library root
│   │       ├── parser.rs       # LiteParse orchestrator
│   │       ├── config.rs       # Configuration types and defaults
│   │       ├── types.rs        # Core data types (ParseResult, TextItem, etc.)
│   │       ├── projection.rs   # Spatial grid projection (layout reconstruction)
│   │       ├── extract.rs      # Raw text extraction from PDFium
│   │       ├── render.rs       # Page rendering / screenshots
│   │       ├── conversion.rs   # Non-PDF format conversion (LibreOffice, image/resvg/usvg rust crates)
│   │       ├── ocr_merge.rs    # Merging OCR results with native text
│   │       ├── error.rs        # Error types
│   │       ├── ocr/            # OCR engine implementations
│   │       │   ├── mod.rs          # OcrEngine trait
│   │       │   ├── tesseract.rs    # Built-in Tesseract OCR
│   │       │   └── http_simple.rs  # HTTP OCR server client
│   │       └── output/         # Output formatters
│   │           ├── mod.rs
│   │           ├── json.rs
│   │           └── text.rs
│   ├── liteparse-napi/     # Node.js bindings (napi-rs)
│   ├── liteparse-python/   # Python bindings (PyO3 / maturin)
│   ├── liteparse-wasm/     # WASM bindings (wasm-bindgen)
│   ├── pdfium/             # Rust wrapper around PDFium C API
│   └── pdfium-sys/         # PDFium FFI (C → Rust) bindings
├── packages/
│   ├── node/               # npm package: TS wrapper + CLI around native binary
│   │   └── src/
│   │       ├── lib.ts          # Public LiteParse class for Node.js
│   │       ├── cli.ts          # CLI entry point (commander)
│   │       └── native.ts       # Native binary loader
│   ├── python/             # PyPI package: Python wrapper around native binary
│   │   └── liteparse/
│   │       ├── __init__.py
│   │       ├── parser.py       # Public LiteParse class for Python
│   │       ├── types.py        # Python dataclass types
│   │       └── cli.py          # CLI entry point
│   └── wasm/               # WASM npm package
├── ocr/                    # Example OCR server implementations
│   ├── easyocr/            # EasyOCR wrapper server
│   └── paddleocr/          # PaddleOCR wrapper server
└── Cargo.toml              # Workspace root
```

## Data Flow

1. **Input**: File path or raw bytes received (any supported format)
2. **Conversion** (if needed): Non-PDF formats converted to PDF via LibreOffice and image/resvg/usvg rust crates
3. **PDF Loading**: PDFium extracts text items, images, metadata
4. **OCR** (if enabled): Pages rendered and OCR'd for text-sparse areas
5. **Grid Projection**: Spatial reconstruction of text layout using anchor system
6. **Post-processing**: Bounding boxes, text cleanup
7. **Output**: Formatted as JSON or plain text

## Key Design Decisions

### 1. Rust Core with Language Bindings
The core parsing logic is written in Rust for performance and safety. Language-specific crates expose the same API surface:
- `liteparse-napi` → Node.js via napi-rs
- `liteparse-python` → Python via PyO3/maturin
- `liteparse-wasm` → Browser via wasm-bindgen

Each binding crate is thin — it wraps the core `liteparse` crate's types and async API.

### 2. OCR Engine Trait
OCR functionality uses a trait-based abstraction (`OcrEngine`). This allows:
- Built-in Tesseract (default, compiled in via `tesseract-rs`)
- HTTP OCR server client for remote engines
- Custom JS-side OCR in the WASM build via a callback interface

### 3. Spatial Grid Projection
The most complex (and important!) part of the codebase (`crates/liteparse/src/projection.rs`). Uses:
- **Anchor-based layout**: Tracks text alignment (left, right, center, floating)
- **Forward anchors**: Carry alignment information between lines
- **Column detection**: Identifies multi-column layouts
- **Rotation handling**: Transforms 90°, 180°, 270° rotated text to correct reading order
- **OCR merging**: Combines native PDF text with OCR results, preserving confidence scores and source flags in output

### 4. Selective OCR
OCR only runs on embedded images where text extraction failed, not the entire document. This balances accuracy with performance.

### 5. Configuration
Uses a default-first approach where users only override what they need. See `crates/liteparse/src/config.rs` for defaults.

### 6. Format Conversion via External Tools
Rather than implementing format parsers, LiteParse converts office file formats using system tools (LibreOffice) into PDF. This provides broad format support with minimal code.

## Common Tasks

### Adding a New Output Format
1. Create new file in `crates/liteparse/src/output/`
2. Add variant to `OutputFormat` enum in `config.rs`
3. Wire it up in `main.rs` and binding crates

### Adding a New OCR Engine
1. Implement `OcrEngine` trait in `crates/liteparse/src/ocr/`
2. Add initialization logic in `parser.rs`
3. Add configuration options in `config.rs`

### Modifying Text Extraction Logic
Key files in `crates/liteparse/src/`:
- `projection.rs` — Layout reconstruction (most complex)
- `extract.rs` — Raw text item extraction from PDFium
- `ocr_merge.rs` — Merging OCR and native text

### Adding CLI Options
1. Add field to `LiteParseConfig` in `config.rs`
2. Add clap arg in `main.rs`
3. Wire through `parser.rs`
4. Expose in binding crates (`liteparse-napi`, `liteparse-python`, `liteparse-wasm`)

### Adding / Modifying Node.js Wrapper
- Edit `packages/node/src/lib.ts` for library API changes
- Edit `packages/node/src/cli.ts` for CLI changes
- The native binary interface is defined in `packages/node/src/native.ts`

### Adding / Modifying Python Wrapper
- Edit `packages/python/liteparse/parser.py` for library API changes
- Types are in `packages/python/liteparse/types.py`
- CLI entry point is `packages/python/liteparse/cli.py`

## Key Dependencies

| Dependency | Purpose |
|------------|---------|
| `pdfium` (C library) | PDF text extraction and rendering |
| `tesseract-rs` | Built-in OCR engine (optional, via `tesseract` feature) |
| `clap` | CLI framework |
| `serde` / `serde_json` | Serialization |
| `tokio` | Async runtime |
| `reqwest` | HTTP client (for OCR server) |
| `image` | Image processing (PNG encoding) |
| `napi-rs` | Node.js native bindings |
| `pyo3` / `maturin` | Python native bindings |
| `wasm-bindgen` | WASM bindings |

## Entry Points

- **Rust CLI**: `crates/liteparse/src/main.rs`
- **Rust Library**: `crates/liteparse/src/lib.rs` → `parser.rs` contains `LiteParse` struct
- **Node.js**: `packages/node/src/lib.ts` exports `LiteParse` class
- **Python**: `packages/python/liteparse/parser.py` exports `LiteParse` class
- **WASM**: `crates/liteparse-wasm/` exposes `LiteParse` via wasm-bindgen

## Related Documentation

- [User-facing documentation](README.md)
- [OCR API Specification](OCR_API_SPEC.md)
- [WASM package README](packages/wasm/README.md)
- [Python package README](packages/python/README.md)
- [OCR server examples](ocr/README.md)


===== FILE elie222/inbox-zero::AGENTS.md | stars=11702 followers=2134 lang=TypeScript bytes=6839 =====

# Repository Guidelines

## Build & Test Commands
- Development: `pnpm dev`
- Build: `pnpm build`
- Lint: `pnpm lint`
- Format: Biome (`pnpm check` / `pnpm fix` via ultracite)
- Run all tests: `pnpm test`
- Run integration tests: `pnpm test-integration`
- Run AI tests: `pnpm --filter inbox-zero-ai test-ai`
- Run single test: `pnpm test path/to/test-file.test.ts`
- Run specific AI/eval test: `pnpm --filter inbox-zero-ai test-ai __tests__/eval/your-test.test.ts`
- Evals in `apps/web/__tests__/eval/` must be run from repo root with `pnpm --filter inbox-zero-ai test-ai` (not `pnpm test`)
- Type-check build (skips Prisma migrate): `pnpm --filter inbox-zero-ai exec next build`
- Do not use root `tsc --noEmit`; it is not a supported validation step in this monorepo and surfaces unrelated repo-wide debt. If you need the app's CI-aligned type/build check, use `pnpm --filter inbox-zero-ai build:ci` instead, and only when explicitly asked.
- Do not run `dev` or `build` unless explicitly asked
- Run `pnpm install` before running tests or build if not already done
- Before writing or updating tests, review `.claude/skills/testing/SKILL.md`.
- For core bug-fix tasks, default to TDD when practical (red/green/refactor); AI prompt improvements should generally be backed by evals too, and TDD is often useful there as well.
- When adding a new workspace package, add its `package.json` COPY line to `docker/Dockerfile.prod` and `docker/Dockerfile.local`.

## Code Style
- Install packages in `apps/web`, not root: `cd apps/web && pnpm add ...`
- Lodash: import specific functions (`import groupBy from "lodash/groupBy"`)
- TypeScript with strict null checks
- Path aliases: `@/` for imports from project root
- NextJS app router with (app) directory, tailwindcss
- For version-sensitive or unclear Next.js behavior, check the relevant doc in `node_modules/next/dist/docs/` before changing framework code.
- Only add comments for "why", not "what". Prefer self-documenting code.
- Logging: avoid duplicating logger context fields from higher in the call chain. Use `logger.trace()` for PII fields (from, to, subject, etc.). Exception: the authenticated user's own email is fine to log at any level.
- Tests should use the real logger implementation (do not mock `@/utils/logger`).
- Avoid low-value tests that mostly restate implementation details; prefer tests that catch a real behavioral regression.
- Helper functions go at the bottom of files, not the top
- All imports at the top of files, no mid-file dynamic imports
- Avoid `useEffect` for mirroring fetched props/data into local state; prefer derived values or explicit edit state.
- Co-locate unit tests next to source files (e.g., `utils/example.test.ts`). Integration, E2E, and AI tests go in `__tests__/`.
- Don't export types/interfaces only used within the same file
- No re-export patterns. Import from the original source.
- Prefer the `EmailProvider` abstraction; only use provider-type checks (`isGoogleProvider`, `isMicrosoftProvider`) at true provider boundary/integration code.
- Infer types from Zod schemas using `z.infer<typeof schema>` instead of duplicating as separate interfaces
- Default to inlining and co-locating logic at the call site.
- Avoid premature abstraction. Small duplicated expressions are usually fine; extracting them often adds indirection without meaning.
- Do not duplicate substantial logic or correctness-sensitive rules. If copied code must stay in sync to avoid bugs, extract or centralize it early.
- Extract helpers when they make surrounding code clearer, name a meaningful domain concept, or keep shared behavior consistent across flows.
- Don't extract helpers that just rename and forward parameters; that's a layer without meaning.
- Avoid large/nested ternaries. Prefer straightforward control flow, a small helper, or a lookup table when it improves readability.
- No barrel files. Import directly from source files.
- Colocate page components next to their `page.tsx`. No nested `components/` subfolders in route directories.
- Reusable components shared across pages go in `apps/web/components/`
- One resource per API route file
- Env vars: add to `.env.example`, `env.ts`, and `turbo.json`. Prefix client-side with `NEXT_PUBLIC_`.
- Never use dynamic Prisma transactions (`prisma.$transaction(async (tx) => ...)`).

## Change Philosophy
- Prefer the simplest, most readable change; only keep backwards compatibility when explicitly requested.
- Do not optimize for migration paths: refactor call sites directly, including larger coordinated changes when clarity improves.

## LLM Features
- Stay AI-first: fix general failure modes, not exact eval wording, and avoid brittle keyword or regex rules unless the product needs a hard guard.
- Do not add keyword/phrase blacklists to prompts, evals, or tests just to catch a model's current bad wording. This product works across languages, so English-specific text checks are especially brittle. For LLM behavior, assert the semantic failure mode with a judge/eval criterion or structured contract instead. Example: test "does not ask unnecessary clarification or invent payment status," not "does not contain 'could you clarify' or 'specific payment'."
- Never gate context injection or tool behavior on ad hoc user-text keyword matching; use structured state, metadata, or explicit events instead.
- Tool descriptions should be self-contained: what the tool does, what its parameters mean, when to use it vs alternatives, prerequisites, and safety constraints specific to that tool.
- Keep only cross-cutting policies (identity, write confirmation, security, formatting) in the system prompt. Per-tool guidance belongs in the tool description so it appears only when the tool is active.

## Component Guidelines
- Use shadcn/ui components when available
- Use `LoadingContent` component for async data: `<LoadingContent loading={isLoading} error={error}>{data && <YourComponent data={data} />}</LoadingContent>`

## Fullstack Workflow
See `.claude/skills/fullstack-workflow/SKILL.md` for full examples and templates.

- API route middleware: `withError` (public, no auth), `withAuth` (user-level), `withEmailAccount` (email-account-level). Export response type via `Awaited<ReturnType<typeof getData>>`.
- Mutations: use server actions with `next-safe-action`, NOT POST API routes.
- Exception: mobile-native integrations may use POST API routes when they require a stable HTTP contract.
- Validation: Zod schemas in `utils/actions/*.validation.ts`. Infer types with `z.infer`.
- Data fetching: SWR on the client. Call `mutate()` after mutations.
- Forms: React Hook Form + `useAction` hook. Use `getActionErrorMessage(error.error)` for errors.
- Loading states: use `LoadingContent` component.
- Cursor Cloud VM setup: see `.claude/skills/cloud-dev-environment/SKILL.md`.


===== FILE pastelsky/bundlephobia::AGENTS.md | stars=9561 followers=1019 lang=TypeScript bytes=2049 =====

# Bundlephobia development loop

Use this workflow for changes spanning `package-build-stats`, Bundlephobia, and
the production server.

## Repositories

- Bundlephobia: `~/dev/bundlephobia`, default/production branch `bundlephobia`.
- Package builder: `~/dev/package-build-stats`, default branch `master`.
- Production: `ssh bphobia`, checkout `/var/www/bundlephobia`.
- Work in a temporary worktree created from the latest remote default branch.
  Do not switch, stash, or reset an active checkout containing unrelated work.
- Commit as `Shubham Kanodia <shubham.kanodia10@gmail.com>`.

## Change and publish package-build-stats

1. Make the change in the `package-build-stats` repository and run `yarn check`,
   `yarn test`, and `yarn build`.
2. Add a changeset with `yarn changeset` for published behavior changes.
3. Open a PR against `master` and wait for blocking CI checks.
4. Merge the Changesets version PR to publish the package.
5. Confirm the version is available from the public npm registry before updating
   Bundlephobia.

## Update Bundlephobia

1. Pin the same exact version in the root and `build-service/package.json`.
2. Update both Yarn lockfiles and run the relevant checks.
3. Keep npm and Yarn on the public registry configured by `.npmrc` and
   `.yarnrc.yml`; do not override the repository registry configuration.
4. Open a PR against `bundlephobia` and deploy only the merged commit.

## Deploy and verify

Inspect `git status` before pulling and do not overwrite server-side changes.

```sh
ssh bphobia
cd /var/www/bundlephobia
git status --short
git pull --ff-only origin bundlephobia
corepack yarn install --immutable
cd build-service && corepack yarn install --immutable
bun upgrade
pm2 restart all --update-env
pm2 save
```

Confirm both installed `package-build-stats` versions, Bun, and the deployed git
commit. Check PM2, application/build logs, nginx errors, host resources, and API
responses. Treat upstream timeouts, OOM kills, restart loops, or growing orphaned
installer processes as deployment failures.


===== FILE zhaoxuya520/reverse-skill::CLAUDE.md | stars=8899 followers=None lang=PowerShell bytes=1347 =====

# CLAUDE.md

This repository is a **task skill router** for authorized reverse engineering, mobile/security analysis, and pentest workflows.

## On Any Task

`RULES.md` is the single source of truth for behavior chain and authorization.

Routing order:

1. `skills/MASTER-ROUTING.md` or `skills/scripts/master-route.ps1 -Hint "..."`
2. `skills/scripts/case-init.ps1` → `work/<case>/scope.md` (must grant auth before ACT)
3. `skills/routing.md` when ambiguous; roles in `skills/ops/role-map.md`
4. Open PRIMARY `SKILL.md` and execute ACTION REQUIRED
5. Timeline/workitems + Evidence→Finding→Path (`skills/ops/`)
6. `skills/tool-index.md` for real tool paths (never guess)
7. Missing tool → `skills/scripts/bootstrap-reverse.ps1` (manifest capabilities only)

**Identity**: lightweight skill router — see `skills/ops/IDENTITY.md` (not a Z3r0 platform).

## First-Run Setup

`skills/tool-index.md` is not in fresh clones. Generate it:

```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/refresh-tool-index.ps1

# macOS / Linux
bash skills/scripts/refresh-tool-index.sh

# Kali
bash kali/scripts/refresh-tool-index.sh
```

Read `README_AI.md` for full bootstrap sequence.

## Coherence check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File skills/scripts/verify-routing-coherence.ps1
```


===== FILE six2dez/reconftw::CLAUDE.md | stars=7888 followers=2549 lang=Shell bytes=28775 =====

<!-- GSD:project-start source:PROJECT.md -->
## Project

**reconFTW**

reconFTW is a comprehensive bash-based reconnaissance automation framework used by bug bounty hunters, penetration testers, and security researchers. It orchestrates 70+ external security tools (Go, Python, Rust) across subdomain enumeration, web probing, OSINT, and vulnerability scanning, producing structured per-target output trees with optional Axiom distributed execution, AI reporting, monitor/incremental mode, and Slack/Telegram/Discord notifications.

**Core Value:** Run one command, get a complete recon picture of a target — passive, active, and vulnerability layers — with resumable checkpoints, structured output, and zero-touch tool orchestration.

### Constraints

- **Tech stack**: Bash 4.3+ — Required for `wait -n`, `mapfile`, associative arrays. macOS users must have Homebrew bash; auto re-exec is best-effort.
- **External tools**: 70+ runtime dependencies — Most install via `go install @latest` (no version pinning), which is convenient but a known supply-chain risk.
- **Single process**: All modules sourced into one shell — No subshell isolation between modules; all state shared via globals. Workflow functions must save/restore globals they override (see `passive()` pattern).
- **Resume semantics**: Checkpoint files are touch-once at `end_func` — Interrupted functions re-run from scratch on next invocation; partial outputs are not detected.
- **Single-operator**: Designed for one user per target run — No locking, no multi-user state, no concurrent runs against the same target dir.
- **Output stability**: `Recon/<domain>/` tree is a public contract — Subdirectory names and filenames are consumed by downstream pipelines, scripts, and parsers; renames are breaking changes.
- **macOS compatibility**: GNU coreutils + GNU sed + GNU getopt required — System BSD versions are not supported.
- **CI budget**: Integration-full is weekly cron — Unit + smoke are per-push; adding heavy integration tests must respect this split.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Bash 4+ - All core framework logic (`reconftw.sh`, `modules/*.sh`, `lib/*.sh`, `install.sh`)
- Python 3.7+ - Python-backed tools (each runs in isolated `uv venv`): `dorks_hunter`, `CMSeeK`, `EmailHarvester`, `Spoofy`, `SSTImap`, `gato`, `regulator`, `reconftw_ai`, `getjswords.py`
- Go (latest, min ~1.21) - Primary binary language for ~55 security tools installed via `go install @latest`
## Runtime
- Linux (Debian/Ubuntu/RHEL/Arch) or macOS (Apple Silicon / Intel)
- Docker: Ubuntu 24.04 base image (`Docker/Dockerfile`)
- ARM64/aarch64, ARMv6l/v7l, and x86_64 all supported for Go binary installs
- `getopt` (GNU getopt required on macOS via `brew install gnu-getopt`)
- `nproc` / `sysctl -n hw.ncpu` for CPU core auto-detection
- `timeout` / `gtimeout` (macOS Homebrew `coreutils`)
- `gnu-sed` (macOS requires `brew install gnu-sed`)
- `gnu-coreutils` (macOS requires `brew install coreutils`)
- Go tools: `go install` (`GOPATH=$HOME/go`, `GOROOT=/usr/local/go`)
- Python tools: `uv tool install` from GitHub (most) or PyPI (`fray`)
- Python repo venvs: `uv venv venv && uv pip install -r requirements.txt`
- Lockfile: None (always installs `@latest`)
## Frameworks
- No framework — pure Bash with sourced module files
- Module loading order: `lib/validation.sh` → `lib/common.sh` → `lib/ui.sh` → `lib/parallel.sh` → `modules/utils.sh` → `modules/core.sh` → `modules/osint.sh` → `modules/subdomains.sh` → `modules/web.sh` → `modules/vulns.sh` → `modules/axiom.sh` → `modules/modes.sh`
- bats-core (Bash Automated Testing System)
- GNU make (`Makefile`) — test, lint, format targets
- shellcheck (error-level) — `make lint`, pre-commit hook
- shfmt (4-space indent, `-bn`, `-ci`) — `make fmt`, pre-commit hook
- pre-commit hooks defined in `.pre-commit-config.yaml`
- semgrep: `.github/workflows/semgrep.yml` (CI only)
## Key Dependencies
### Go Tools (installed via `go install @latest`)
- `subfinder` (projectdiscovery/subfinder) — passive multi-source subdomain discovery
- `github-subdomains` (gwen001/github-subdomains) — GitHub-based subdomain search
- `gitlab-subdomains` (gwen001/gitlab-subdomains) — GitLab-based subdomain search
- `dnstake` (pwnesia/dnstake) — subdomain takeover detection
- `puredns` (d3mondev/puredns) — mass DNS resolution with wildcard filtering
- `dnsx` (projectdiscovery/dnsx) — DNS toolkit
- `massdns` (blechschmidt/massdns) — via repo clone + build
- `dsieve` (trickest/dsieve) — subdomain filtering
- `enumerepo` (trickest/enumerepo) — GitHub org repo enumeration
- `gotator` (Josue87/gotator) — subdomain permutations
- `analyticsrelationships` (Josue87/analyticsrelationships) — Google Analytics pivoting
- `roboxtractor` (Josue87/roboxtractor) — robots.txt extractor
- `crt` (cemulus/crt) — crt.sh search
- `asnmap` (projectdiscovery/asnmap) — ASN-to-CIDR mapping
- `mapcidr` (projectdiscovery/mapcidr) — CIDR manipulation
- `smap` (s0md3v/smap) — passive Shodan-powered port scan
- `tlsx` (projectdiscovery/tlsx) — TLS certificate harvesting
- `hakip2host` (hakluke/hakip2host) — reverse IP lookup
- `cdncheck` (projectdiscovery/cdncheck) — CDN/WAF IP classification
- `hakoriginfinder` (hakluke/hakoriginfinder) — origin IP discovery behind CDN
- `inscope` (tomnomnom/hacks/inscope) — scope filtering
- `csprecon` (edoardottt/csprecon) — CSP-based subdomain discovery
- `favirecon` (edoardottt/favirecon) — favicon-based tech recon
- `httpx` (projectdiscovery/httpx) — multi-probe HTTP toolkit
- `katana` (projectdiscovery/katana) — web crawler
- `ffuf` (ffuf/ffuf) — web fuzzer
- `subjs` (lc/subjs) — JavaScript URL extractor
- `Gxss` (KathanP19/Gxss) — reflected XSS param finder
- `jsluice` (BishopFox/jsluice) — JS secret/URL extractor
- `sourcemapper` (denandz/sourcemapper) — JS source map extractor
- `mantra` (brosck/mantra) — JS/secret scanner
- `urlfinder` (projectdiscovery/urlfinder) — URL discovery
- `xnLinkFinder` (xnl-h4ck3r/xnLinkFinder) — via uv
- `nmapurls` (sdcampbell/nmapurls) — URL extraction from Nmap XML
- `naabu` (projectdiscovery/naabu) — fast port scanner
- `VhostFinder` (wdahlenburg/VhostFinder) — virtual host discovery
- `shortscan` (bitquark/shortscan) — IIS short filename scanner
- `nuclei` (projectdiscovery/nuclei) — template-based scanner
- `dalfox` (hahwul/dalfox) — XSS scanner
- `crlfuzz` (dwisiswant0/crlfuzz) — CRLF injection scanner
- `Web-Cache-Vulnerability-Scanner` (Hackmanit) — web cache poisoning
- `TInjA` (Hackmanit/TInjA) — SSTI scanner
- `toxicache` (xhzeem/toxicache) — web cache poisoning
- `second-order` (mhmdiaa/second-order) — broken link/second-order injection
- `s3scanner` (sa7mon/s3scanner) — S3/GCS/Azure Blob misconfiguration
- `misconfig-mapper` (intigriti/misconfig-mapper) — third-party misconfiguration
- `sj` (BishopFox/sj) — Swagger/OpenAPI analysis
- `grpcurl` (fullstorydev/grpcurl) — gRPC reflection scanner
- `nerva` (praetorian-inc/nerva) — service fingerprinting
- `brutus` (praetorian-inc/brutus) — credential spraying
- `julius` (praetorian-inc/julius) — LLM endpoint probe
- `titus` (praetorian-inc/titus) — secrets engine
- `notify` (projectdiscovery/notify) — multi-channel notifications
- `interactsh-client` (projectdiscovery/interactsh) — OOB callback server
- `gf` (tomnomnom/gf) — URL pattern grep
- `anew` (tomnomnom/anew) — append new lines only
- `unfurl` (tomnomnom/unfurl) — URL parser
- `qsreplace` (tomnomnom/qsreplace) — querystring replacer
- `gitdorks_go` (damit5/gitdorks_go) — GitHub dork search
- `github-endpoints` (gwen001/github-endpoints) — GitHub endpoint discovery
- `cent` (xm1k3/cent) — nuclei template manager
- `trufflehog` (trufflesecurity/trufflehog) — secrets scanner (via `go install`)
- `brutespray` (x90skysn3k/brutespray) — service credential spraying
### Python Tools (installed via `uv tool install`)
- `dnsvalidator` (vortexau/dnsvalidator) — DNS resolver validation
- `interlace` (pry0cc/interlace) — parallel command runner
- `wafw00f` (EnableSecurity/wafw00f) — WAF fingerprinting
- `commix` (commixproject/commix) — command injection scanner
- `waymore` (xnl-h4ck3r/waymore) — passive URL collection
- `urless` (xnl-h4ck3r/urless) — URL deduplication
- `ghauri` (r0oth3x49/ghauri) — SQLi scanner (optional)
- `xnLinkFinder` (xnl-h4ck3r/xnLinkFinder) — deep link finder
- `xnldorker` (xnl-h4ck3r/xnldorker) — Google dorker
- `porch-pirate` (MandConsultingGroup/porch-pirate) — Postman API leaks
- `p1radup` (iambouali/p1radup) — URL deduplication
- `subwiz` (hadriansecurity/subwiz) — ML-based subdomain prediction
- `arjun` (s0md3v/Arjun) — parameter discovery
- `gqlspection` (doyensec/GQLSpection) — GraphQL deep introspection
- `postleaksNg` (six2dez/postleaksNG) — Postman public leak search
- `cewler` (roys/cewler) — web wordlist generator
- `fray` (dalisecurity/fray) — WAF-aware payload testing (PyPI)
### Repo-Clone Tools (Python venvs, run via `venv/bin/python3`)
- `dorks_hunter` (six2dez/dorks_hunter) — Google dork automation
- `CMSeeK` (Tuhinshubhra/CMSeeK) — CMS fingerprinting
- `cloud_enum` (initstring/cloud_enum) — AWS/GCP/Azure bucket enumeration
- `EmailHarvester` (maldevel/EmailHarvester) — email harvesting
- `SwaggerSpy` (UndeadSec/SwaggerSpy) — Swagger endpoint leak detection
- `LeakSearch` (JoelGMSec/LeakSearch) — credential leak search
- `Spoofy` (MattKeeley/Spoofy) — email spoofing check
- `msftrecon` (Arcanum-Sec/msftrecon) — Microsoft tenant recon
- `Scopify` (Arcanum-Sec/Scopify) — scope management
- `regulator` (cramppet/regulator) — regex-based subdomain permutations
- `SSTImap` (vladko312/SSTImap) — SSTI scanner (alternative engine)
- `gato` (praetorian-inc/gato) — GitHub Actions audit
### Repo-Clone Tools (Go build)
- `ghleaks` (dinosn/ghleaks) — GitHub-wide secret search
- `nomore403` (devploit/nomore403) — 403 bypass
- `ffufPostprocessing` (Damian89/ffufPostprocessing) — ffuf result analysis
- `JSA` (w9w/JSA) — JS analysis
- `ultimate-nmap-parser` (shifty0g/ultimate-nmap-parser) — Nmap XML parser
### System-Level Tools (apt/brew/yum)
- `nmap` — active port scanning
- `massdns` — DNS resolver (also cloned + built from source)
- `jq` — JSON processing throughout all modules
- `exiftool` (perl-Image-ExifTool) — metadata extraction
- `whois` — domain registration lookup
- `sqlmap` — SQL injection (system or via repo clone)
- `testssl.sh` (testssl/testssl.sh) — TLS/SSL misconfiguration testing
- `medusa` — credential brute-force (system install)
- `shodan` CLI — installed via `uv tool install shodan`
### Rust Tools
- `smugglex` (Cargo) — HTTP request smuggling detection
- Rustup installed from `https://sh.rustup.rs`
## Configuration
- `reconftw.cfg` — sourced after CLI parsing; all feature flags, rate limits, timeouts, wordlist paths, API keys, thread counts
- `secrets.cfg` (gitignored, auto-sourced) — API keys and tokens separated from main config
- `secrets.cfg.example` — template showing all supported secret vars
- Feature flags: `OSINT=true`, `SUBDOMAINS_GENERAL=true`, `VULNS_GENERAL=false`, etc.
- Rate limits: `HTTPX_RATELIMIT=150`, `NUCLEI_RATELIMIT=150`, `FFUF_RATELIMIT=0`
- Thread counts: auto-scaled via `AVAILABLE_CORES=$(nproc)` with multipliers per tool
- Timeouts: per-tool in seconds or minutes (`CMSSCAN_TIMEOUT=3600`, `SUBFINDER_ENUM_TIMEOUT=180`)
- Wordlist paths: `fuzz_wordlist`, `lfi_wordlist`, `subs_wordlist` etc. under `${WORDLISTS_DIR}`
- Output: `EXPORT_FORMAT`, `AI_REPORT_TYPE`, `ASSET_STORE`
- GNU `getopt` long options, parsed in `reconftw.sh` while/case loop
- All CLI overrides use `CLI_*` pattern and are re-applied after `reconftw.cfg` is sourced
- Full list from `getopt` call: `domain`, `list`, `recon`, `subdomains`, `passive`, `all`, `web`, `osint`, `zen`, `deep`, `help`, `vps`, `vps-count`, `ai`, `check-tools`, `health-check`, `quick-rescan`, `incremental`, `adaptive-rate`, `dry-run`, `parallel`, `no-parallel`, `monitor`, `monitor-interval`, `monitor-cycles`, `refresh-cache`, `gen-resolvers`, `force`, `export`, `report-only`, `no-report`, `parallel-log`, `quiet`, `verbose`, `no-color`, `log-format`, `show-cache`, `banner`, `no-banner`, `legal`
- `SHODAN_API_KEY`, `WHOISXML_API`, `PDCP_API_KEY`, `XSS_SERVER`, `COLLAB_SERVER` — preferred over config file
- `GOROOT`, `GOPATH`, `PATH` — extended by `reconftw.cfg` for Go and Rust binaries
- `LOGFILE` — per-target log path
- `config/reconftw_full.cfg` — full-scan preset
- `config/reconftw_quick.cfg` — quick-scan preset
- `config/reconftw_stealth.cfg` — low-noise preset
## Build
- Default: `go1.23.6` (fetches latest from `https://go.dev/VERSION?m=text`)
- Installed to `/usr/local/go`; set `install_golang=false` in config to skip
- Minimum: Python 3.7 (enforced in `install_yum()`)
- Virtual environments per tool via `uv venv`
- Root venv at `.venv/` for `getjswords.py` and similar helpers
## Platform Requirements
- Bash ≥ 4.3 (for `wait -n` used in `lib/parallel.sh`)
- Go ≥ 1.21 (tools use SIV module paths like `/v2`, `/v3`)
- Python ≥ 3.7
- `uv` package manager
- Rust / Cargo (for `smugglex`)
- GNU coreutils, getopt, sed (macOS only via Homebrew)
- ~5GB free disk space for Go cache, tools, and repos
- ~1GB RAM minimum (Go compilation)
- Base image: `ubuntu:24.04`
- Build arg `INSTALL_AXIOM=true` (default) installs axiom fleet tooling
- Ports 85-90 exposed (for headless browser tooling)
- Runs as root (required for raw socket operations by some tools)
- Health check: `./reconftw.sh --health-check`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Shell Settings
## Source Guard Pattern
- `lib/common.sh`: `[[ -n "$_COMMON_SH_LOADED" ]] && return 0`
- `lib/parallel.sh`: `[[ -n "$_PARALLEL_SH_LOADED" ]] && return 0`
- `lib/ui.sh`: `[[ -n "${_UI_SH_LOADED:-}" ]] && return 0`
## Function Naming
- Public module functions: `snake_case` prefixed with module context (`sub_passive`, `sub_crt`, `geo_info`)
- Private helpers: `_snake_case` prefix (`_print_status`, `_print_error`, `_print_module_start`, `_parallel_emit_job_output`)
- UI layer: `ui_` prefix (`ui_init`, `ui_header`, `ui_summary`, `ui_batch_end`)
- Lifecycle wrappers: `start_func` / `end_func` (call these at top/bottom of every recon function)
- Validation functions: `validate_*` / `sanitize_*` (defined in `lib/validation.sh` and `modules/utils.sh`)
## Variable Naming
- Config flags: `SUBPASSIVE`, `SUBCRT`, `PARALLEL_MODE`, `OUTPUT_VERBOSITY`
- Runtime state: `LOGFILE`, `SCRIPTPATH`, `DIFF`, `DRY_RUN`, `AXIOM`
- Error codes: `E_SUCCESS=0`, `E_INVALID_DOMAIN=20`, `E_INVALID_IP=21` (readonly, defined in `lib/validation.sh`)
## CLI Flag Pattern
## Output / UI Conventions
- `OUTPUT_VERBOSITY=0` (quiet): only errors/FAIL printed
- `OUTPUT_VERBOSITY=1` (normal, default): OK/WARN/FAIL/SKIP status lines
- `OUTPUT_VERBOSITY=2` (verbose): all of the above + INFO messages + start_func messages
## Function Lifecycle (start_func / end_func)
- `start_func name desc` — logs to LOGFILE, sets per-function start timestamp, emits INFO at verbosity >= 2
- `end_func message name [status]` — touches checkpoint file, calculates elapsed time, calls `_print_status`
- `skip_notification reason` — emits SKIP/CACHE badge; reasons: `"disabled"`, `"mode"`, `"processed"`, `"processed-visible"`, `"noinput"`
## File Checkpointing (Resumability)
- `end_func` creates the checkpoint: `touch "$called_fn_dir/.${fn}"`
- DIFF mode (`DIFF=true`) bypasses checkpoint — forces re-execution
- Helper `should_run()` in `lib/common.sh` provides a cleaner gate: `if should_run "FLAG_VAR"; then`
## Error Handling
- `E_SUCCESS=0`, `E_GENERAL=1`, `E_MISSING_DEP=2`, `E_INVALID_INPUT=3`
## Validation Functions
| Function | Purpose |
|----------|---------|
| `validate_domain()` | RFC domain check + injection character rejection |
| `validate_ipv4()` | Octet range validation |
| `validate_integer()` | Numeric range check |
| `validate_boolean()` | Accepts `true`/`false` only (not `1`/`0`/`yes`/`no`) |
| `validate_file_readable()` | Exists + readable + is-a-file |
| `sanitize_interlace_input()` | Removes shell metacharacters from input files (canonical in `lib/validation.sh`) |
| `sanitize_domain()` | Strips URL components, lowercases, rejects injection (in `modules/utils.sh`) |
| `is_in_scope_host()` | Anchored hostname scope check (prevents substring false positives) |
| `filter_in_scope_urls()` | Python3-based URL scope check (scheme, userinfo, host) |
## Path and CWD Conventions
## Parallel Execution
## Import / Sourcing Order
## Logging
- All tool output redirected to `$LOGFILE`: `command ... 2>>"$LOGFILE" >/dev/null`
- Structured JSON logging via `log_json level func message [key=val]` (optional, `STRUCTURED_LOGGING=true`)
- `redact_secrets()` scrubs `REDACT_VARS` and `REGISTERED_SECRETS` from log lines
- `register_secret "$value"` must be called before logging any secret value
## Comments
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| Entry point & CLI parser | getopt argument parsing, config sourcing, mode dispatch | `reconftw.sh` |
| Mode orchestration | `start`/`end`, workflow functions (`recon`, `passive`, `all`, `vulns`, `osint`, `subs_menu`, `webs_menu`, `zen_menu`, `monitor_mode`) | `modules/modes.sh` |
| Function lifecycle | `start_func`/`end_func`, checkpointing, logging, notifications, reporting, plugins, health check | `modules/core.sh` |
| Subdomain enumeration | All `sub_*` functions, `subtakeover`, `zonetransfer`, `s3buckets`, `geo_info` | `modules/subdomains.sh` |
| Web analysis | `webprobe_full`, `screenshot`, `nuclei_check`, `fuzz`, `jschecks`, `urlchecks`, `waf_checks`, and 20+ others | `modules/web.sh` |
| Vulnerability scanning | `xss`, `ssrf_checks`, `sqli`, `crlf_checks`, `lfi`, `ssti`, `smuggling`, `fuzzparams`, `nuclei_dast`, and others | `modules/vulns.sh` |
| OSINT collection | `domain_info`, `ip_info`, `emails`, `google_dorks`, `github_leaks`, `github_actions_audit`, `cloud_enum_scan`, etc. | `modules/osint.sh` |
| Shared utilities | `run_command`, `sed_i`, `deleteOutScoped`, `validate_config`, `cache_*`, `checkpoint_*`, `circuit_breaker_*`, rate-limit adaption | `modules/utils.sh` |
| Axiom/distributed mode | `axiom_launch`, `axiom_shutdown`, `axiom_selected`, `resolvers_update`, `ipcidr_target` | `modules/axiom.sh` |
| Parallel execution | `parallel_funcs`, `_throttle_jobs`, job heartbeat, progress live display, log mode output | `lib/parallel.sh` |
| Input validation/sanitization | `sanitize_domain`, `sanitize_ip`, `validate_domain`, `validate_integer`, `_sanitize_list_entry` | `lib/validation.sh` |
| Shared file/counter utilities | `ensure_dirs`, `ensure_webs_all`, `safe_backup`, `count_lines`, incident tracking | `lib/common.sh` |
| UI presentation layer | `_print_status`, `_print_msg`, `_print_section`, `_print_rule`, `ui_header`, `ui_summary`, TTY detection, color management, JSONL output | `lib/ui.sh` |
| Configuration | All runtime settings (~350 variables); sourced after CLI parse | `reconftw.cfg` |
## Pattern Overview
- Single process: `reconftw.sh` sources all libraries and modules at startup; every function lives in the same shell environment
- No subshell isolation between modules — all state is shared via global variables
- File-based checkpointing: `called_fn_dir/.funcname` sentinel files prevent re-running completed functions across invocations
- CLI-over-config: `reconftw.cfg` provides defaults; CLI flags set `CLI_*` variables that are re-applied after config sourcing to guarantee they cannot be overwritten
- All external tool invocations go through `run_command()` which handles dry-run mode, adaptive rate limiting, axiom dispatch, and debug logging
## Layers
- Purpose: Bootstrap, macOS re-exec, module loading, getopt CLI parsing, config sourcing, CLI override re-application, mode dispatch
- Location: `reconftw.sh`
- Contains: `normalize_vps_count_args()`, the main `while/case` getopt loop, the config `source` sequence, CLI override if-blocks, the final `case $opt_mode` dispatch
- Depends on: All libraries (sourced first), all modules (sourced second)
- Used by: End user / CI
- Purpose: Reusable utilities with no side effects; loadable independently for tests
- Location: `lib/validation.sh`, `lib/common.sh`, `lib/ui.sh`, `lib/parallel.sh`
- Contains: Input sanitization, file helpers, UI/color/progress, parallel job management
- Depends on: Nothing (source-guarded with `_*_LOADED` pattern)
- Used by: All modules and reconftw.sh
- Purpose: Implement all scanning, analysis, and orchestration functions
- Location: `modules/`
- Contains: All recon, vuln, OSINT, web, subdomain functions
- Depends on: Libraries (always loaded first), `reconftw.cfg` variables, external tools on PATH
- Used by: modes.sh orchestrates all others; reconftw.sh dispatches to modes.sh
- Purpose: Default runtime values for ~350 flags/paths/limits; can be overridden by `secrets.cfg` and custom config
- Location: `reconftw.cfg`, optionally `secrets.cfg`, optionally `$CUSTOM_CONFIG`
- Contains: Module enable/disable flags, tool flags, API key env-var references, paths, parallelism settings, verbosity, Axiom settings
- Depends on: Nothing
- Used by: Sourced by `reconftw.sh` between CLI parse and CLI override re-application
- Purpose: Store per-target findings in a stable directory hierarchy
- Location: `Recon/<domain>/` (created at `start()` time by `modules/modes.sh`)
- Contains: Standard subdirectories listed below
- Depends on: `start()` in modes.sh creates the directory tree
## Data Flow
### Primary Recon Request Path (`-r` / `--recon`)
### Function Execution Path (every leaf module function)
### Parallel Execution Path
### Axiom Distributed Scan Flow
- Global bash variables throughout (no encapsulation). Config vars, target vars (`domain`, `dir`, `called_fn_dir`, `LOGFILE`), and result counters are all globals
- `passive()` saves/restores module-enable globals before overriding them (`modules/modes.sh:549-611`)
## Key Abstractions
- Purpose: Lifecycle wrapper around every leaf scanning function
- Examples: Used in every function in `modules/subdomains.sh`, `modules/web.sh`, `modules/vulns.sh`, `modules/osint.sh`
- Pattern: `start_func "${FUNCNAME[0]}" "description"` at top; `end_func "output path" "${FUNCNAME[0]}"` at bottom; creates checkpoint file on end
- Purpose: Prevent re-running completed functions across multiple invocations of the same target
- Location: `Recon/<domain>/.called_fn/.funcname`
- Pattern: Each function tests `[[ ! -f "$called_fn_dir/.${FUNCNAME[0]}" ]] || [[ $DIFF == true ]]`; `end_func` writes the sentinel via `touch "$called_fn_dir/.${fn}"`
- Purpose: Universal external-tool gate for dry-run preview, axiom dispatch, adaptive rate limiting, and debug logging
- Location: `modules/utils.sh:468`
- Pattern: All tool calls inside module functions use `run_command <binary> <args>` rather than direct invocation
- Purpose: Allow modules to be sourced multiple times (test re-sourcing, `--source-only`) without re-executing
- Pattern: `[[ -n "$_FOO_LOADED" ]] && return 0` at top of each lib file (`lib/common.sh:6`, `lib/parallel.sh:6`, `lib/ui.sh:5`, `lib/validation.sh` — validation uses error-code guards instead)
- Purpose: Run independent module functions concurrently up to `PARALLEL_MAX_JOBS`
- Pattern: `parallel_funcs N func_a func_b func_c` — each function spawned as a background subshell; used in `recon()`, `osint()`, `vulns()` for independent groups
- Purpose: Transparent axiom/local fallback wrapper — if axiom fails during a module, retries locally
- Location: `modules/modes.sh:656`
- Pattern: All module calls inside `subs_menu`, `webs_menu`, `recon`, `passive` use this wrapper
## Entry Points
- Location: `reconftw.sh`
- Triggers: Direct execution (`./reconftw.sh -d example.com -r`)
- Responsibilities: Bootstrap, all module loading, CLI parse, config source, mode dispatch
- Location: `reconftw.sh:123-125`
- Triggers: `./reconftw.sh --source-only` (used by bats test `setup()` blocks)
- Responsibilities: Sources all modules without executing any recon
- Location: `modules/modes.sh:13`
- Triggers: Called at the top of most workflow functions (`recon`, `subs_menu`, `passive`, `osint`, `zen_menu`)
- Responsibilities: Create output directory tree, init LOGFILE, init cache/incremental/DNS/plugins, set global `dir` and `called_fn_dir`
- Location: `modules/modes.sh:286`
- Triggers: Called at the bottom of most workflow functions
- Responsibilities: AI report, cleanup, Faraday, screenshot diffs, plugin events, hotlist, `export_reports()`, timing summary
## Output Directory Structure
```
```
## Verbosity and Output Controls
- `0` (quiet): Only errors and final summary printed to terminal; banner suppressed
- `1` (normal, default): Errors + warnings printed; `notification()` info/good suppressed
- `2` (verbose): All `notification()` calls, PID info, full parallel output, `start_func` messages, `print_timing_summary`
- `summary`: One badge line per completed parallel job
- `tail`: Last `PARALLEL_TAIL_LINES` (default 20, doubled on failure) from each job's log
- `full`: Complete captured stdout from each job
- `jsonl-strict`: Forces `OUTPUT_VERBOSITY=0`, emits only machine-readable JSONL
## Architectural Constraints
- **Threading:** Single-threaded bash with optional background subshells via `parallel_funcs`; `wait -n` (bash 4.3+) used for job throttling in `_throttle_jobs`
- **Global state:** All config vars, `domain`, `dir`, `called_fn_dir`, `LOGFILE`, `start`, `runtime`, `DIFF`, `AXIOM`, and hundreds of module-enable flags are module-level globals; any sourced function can read or mutate them
- **Circular imports:** None by design — reconftw.sh sources libs first, then modules in explicit dependency order (`utils.sh` → `core.sh` → `osint.sh` → `subdomains.sh` → `web.sh` → `vulns.sh` → `axiom.sh` → `modes.sh`)
- **macOS bash version:** reconftw.sh re-execs itself under Homebrew bash ≥ 4 on macOS (system bash is 3.2); `lib/parallel.sh` requires bash 4.3+ for `wait -n`
- **Working directory:** `start()` calls `cd "$dir"` (the per-target output dir) before any module function runs; all relative paths inside modules resolve against the target dir. `reconftw.sh` captures `startdir=${PWD}` before this
- **No subshell isolation per module:** Modules are sourced functions, not subprocess commands. A `return` inside a module returns from the function; an `exit` would kill the whole shell
## Anti-Patterns
### Direct external tool calls without `run_command`
### Writing checkpoint files manually
### Skipping the `[[ ! -f "$called_fn_dir/.${FUNCNAME[0]}" ]] || [[ $DIFF == true ]]` guard
### Overriding config globals without save/restore in workflow functions
## Error Handling
- ERR trap in `start()` logs function name, line number, and command to `$LOGFILE` and calls `explain_err()` (`modules/modes.sh:140`)
- Non-zero exit from `parallel_funcs` increments `RECON_OSINT_PARALLEL_FAILURES` and sets `RECON_PARTIAL_RUN=true`
- `run_module_with_axiom_failover` catches axiom mid-run failures and retries locally
- Circuit-breaker helpers (`circuit_breaker_is_open`, `circuit_breaker_record_failure`) in `modules/utils.sh:1190` for persistent tool failures
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->


===== FILE LibChecker/LibChecker::AGENTS.md | stars=7030 followers=None lang=Kotlin bytes=13881 =====

# AGENTS.md

Root instructions for coding agents in this repository. Keep this file short,
operational, and focused on decisions that are easy to get wrong.

## Core commands

Use the Gradle wrapper from the repository root. On macOS/Linux use
`./gradlew`; on Windows use `.\gradlew.bat`. CI uses `./gradlew`.

- Format check: `./gradlew spotlessCheck`
- Apply Kotlin/Gradle formatting: `./gradlew spotlessApply`
- Fast Kotlin compile: `./gradlew :app:compileFossDebugKotlin`
- Build a runnable debug APK: `./gradlew :app:assembleFossDebug`
- Install the default debug flavor on a connected device:
  `./gradlew :app:installFossDebug`
- Manual device launch after installing debug should target
  `com.absinthe.libchecker.debug`; `com.absinthe.libchecker` may be a separate
  release install used for snapshot export/import checks.
- Release/R8/package validation: `./gradlew :app:assembleRelease`
- Market R8 rule check when full signing is blocked:
  `./gradlew :app:minifyMarketReleaseWithR8`
- Jetpack Macrobenchmark targeted smoke:
  `ANDROID_SERIAL=<serial> ./gradlew :macrobenchmark:connectedFossBenchmarkAndroidTest --no-configuration-cache`
  Add `-Pandroid.testInstrumentationRunnerArguments.class=<BenchmarkClass#method>`
  to run one startup, app-list, or detail scenario.
- Device UI validation: prefer AndroMeld MCP Phone Screen sessions for visible
  launch, navigation, and UI-state checks. Use Gradle/adb for install and
  package-state operations only when needed. For performance/detail checks, use
  real complex packages instead of trivial sample apps when available.
- For snapshot checks, prefer importing an existing backup from the device
  `Download` directory before exporting a new snapshot.

For docs-only changes, a Gradle build is usually unnecessary. For source
changes, run the narrowest command that covers the touched files plus
`spotlessCheck` when practical. For resource, manifest, packaging, R8, flavor,
or release behavior changes, run the matching assemble/minify task.

## Build facts

- Java toolchain: 25.
- SDK levels are configured in `build-logic/src/main/kotlin/Projects.kt`
  (`compileSdk = 37`, `targetSdk = 37`, `minSdk = 24`).
- `foss` is the default flavor. `market` adds Google/Firebase integrations.
- There is no dedicated unit-test gate today. If tests are added, put JVM tests
  under `src/test` and instrumented tests under `src/androidTest`.
- Version name/code come from `baseVersionName` plus git state in
  `build-logic/src/main/kotlin/Projects.kt`; build from a real git checkout.
- CI runs `./gradlew --non-interactive spotlessCheck` and
  `./gradlew --non-interactive app:assembleRelease`.

## Module boundaries

- `:app` is the Android application. Put product behavior here.
- `:compat` owns in-repo compatibility shims, shaded/stubbed third-party API
  surfaces, and source-level workarounds that must keep their original package
  names. Do not put product behavior here.
- `:hidden-api` is compile-only hidden platform API stubs and Rikka Refine
  annotations. Never put runtime app logic here.
- `:macrobenchmark` owns Jetpack Macrobenchmark tests for release-like app
  performance checks. Keep scenarios focused on stable, high-value user flows.
- `build-logic/` owns shared Gradle conventions and custom plugins.

Important `:app` boundaries:

- `features/*` is legacy user-facing flow structure. When touching it for
  refactors, prefer migrating a focused vertical slice into the matching
  `domain/*` product package with clear `presentation`, `ui`, `model`,
  `usecase`, and `repository` subpackages. Keep view constants, spans, and
  adapter-only icon types in UI; move reusable parsing/data preparation behind
  workflow-focused modules instead of flat directories of tiny use cases.
- Shared `view/` widgets own rendering, accessibility metadata, and animation
  only; pass feature/domain data in through providers instead of importing
  `data/*`.
- `domain/app/` owns app-list use cases and repository/factory interfaces.
  Keep package-list synchronization rules here instead of in UI controllers.
  Put feature-specific app-domain use cases and display models in focused
  subpackages instead of growing the root package by default.
- `data/app/` adapts Android package APIs, Room repositories, and local
  package-change sources to the `domain/app/` interfaces.
- `domain/statistics/` owns statistics/reference computation rules. Keep
  package scanning, package-info lookups, and rule-matching loops out of
  fragments, ViewModels, and chart data sources. Model built-in and external
  charts through the same definition catalog; built-ins use drawable icon
  keys, while external rule icons use validated SVG files.
- `data/statistics/` adapts remote or cached statistics sources, such as Android
  version distribution, to `domain/statistics/` interfaces.
- `domain/snapshot/` owns snapshot models, archive, capture, and diff seams;
  keep package-to-snapshot conversion and diff rules out of UI controllers and
  services.
- `data/snapshot/` adapts Android, protobuf archive format, and local snapshot
  storage to `domain/snapshot/` interfaces.
- `compat/` wraps platform/API-level differences. Check here before adding new
  SDK-version branches.
- `utils/apk`, `utils/manifest`, `utils/dex`, `utils/elf`, `PackageUtils`,
  `PackageManagerCompat`, and `PackageInfoExtensions` own package parsing and
  package-manager helpers. Reuse them before adding another parser.
- `database/` owns Room entities, DAO, repository, migrations, schemas, and
  backup helpers.
- `app/src/foss/` and `app/src/market/` are flavor source sets. Keep matching
  APIs when touching flavor delegates.
- `app/src/main/res/values/strings.xml` is for user-facing strings.
  `values/untranslatable.xml` is only for strings that should not go through
  Crowdin.

## Style and naming

- Follow `.editorconfig`: UTF-8, 2-space indentation, final newline, no trailing
  whitespace.
- Kotlin and `.gradle.kts` formatting is enforced by Spotless/ktlint.
- Kotlin trailing commas are disabled.
- Keep dependency versions in `gradle/libs.versions.toml`; wire them through
  catalog aliases.
- Repositories are centralized in `settings.gradle.kts`; do not add module-level
  repositories.
- Prefer Kotlin for app code. Keep Java in existing Java-heavy parser/stub areas.
- Use XML layouts and ViewBinding, not Jetpack Compose UI.
- Activities/fragments should follow existing `BaseActivity<VB>`,
  `BaseFragment<VB>`, and `IBinding` patterns.
- Dependency injection uses Koin. Put app-wide bindings in `di/AppModule.kt`;
  inject ViewModels through Koin instead of default-constructing repositories,
  use cases, or platform adapters inside ViewModels.
- Use `Timber` instead of Android `Log`.
- Follow existing resource prefixes such as `activity_*`, `fragment_*`,
  `item_*`, `layout_*`, `ic_*`, and `bg_*`.

## Data, UI, and release constraints

- Keep full-width selectable or hoverable list rows edge-to-edge. Put horizontal
  page spacing in each row's content padding, not item margins or parent-list
  horizontal padding, so selector and hover feedback have no side gaps.
- Room schema changes require a database version bump, migration or
  auto-migration, and updated `app/schemas/`.
- UI controllers should not call `Repositories.lcRepository` directly for new
  or refactored paths; route persistence through ViewModels and domain use
  cases/repositories.
- Avoid package-manager, archive, or freeze-state lookups in UI controllers or
  RecyclerView/view binding; precompute through ViewModels/use cases on a
  background thread.
- Avoid broad `PackageInfo` flag combinations for huge apps; prefer focused
  lookups that keep Binder payloads below transaction limits.
- Heavy package scanning, zip reads, DEX parsing, ELF parsing, database writes,
  and network calls must run off the main thread.
- Package analysis must keep working for installed apps, APK, split APK, APKS,
  XAPK, HAP, missing icons/labels, corrupted archives, and OEM/API differences.
- Prefer `FileProvider` for sharing/exporting app files. Any legacy `file://`
  exposure must stay narrowly scoped and idempotent; new paths should not
  expand it.
- Keep `foss` free of market-only Google/Firebase behavior.
- Review manifests carefully when changing exported activities, deep links,
  FileProvider, Shizuku provider authorities, package visibility, foreground
  services, or sensitive permissions.
- When moving UI component packages, update manifest entries, direct intent
  refs, layout `tools:context`, and split/window embedding configs together.
- Update keep rules when adding reflection, generated binding entry points,
  JavaScript interfaces, Parcelable creators, or hidden/private API access.

## Environment gotchas

- If Gradle/Kotlin validation fails because local writes under `~/.gradle`,
  `~/.android`, file watchers, or the Kotlin daemon are blocked, retry with:
  `GRADLE_USER_HOME=/private/tmp/libchecker-gradle-home`
  `ANDROID_USER_HOME=/private/tmp/libchecker-android-home`
  `-Dorg.gradle.vfs.watch=false`
  `-Dkotlin.compiler.execution.strategy=in-process`
- Keep `ANDROID_USER_HOME` stable across debug installs. Switching debug
  keystores can cause `INSTALL_FAILED_UPDATE_INCOMPATIBLE`; prefer the existing
  temp Android home before uninstalling debug.
- Do not treat every Gradle deprecation trace as repo-owned. Recent AGP traces
  such as `VariantDependenciesBuilder.createTestComponents` were upstream/plugin
  noise, not a reason to rewrite project dependency access.
- Keep `TYPESAFE_PROJECT_ACCESSORS` while `app/build.gradle.kts` uses
  `projects.hiddenApi`.
- Release signing may fail locally because debug/release keystore creation is
  blocked. For R8 rule proof, inspect generated
  `app/build/outputs/mapping/*/configuration.txt` and `mapping.txt`.
- Disable or whitelist device freezer/background-management tools before
  macrobenchmark runs; they can kill freshly installed instrumentation packages.

## NEVER

- Never revert or overwrite user changes unless explicitly asked.
- Never commit generated build output, `.gradle/`, `.kotlin/`, `app/build/`,
  `app/foss/`, or `app/market/`.
- Never move runtime logic into `:hidden-api`.
- Never add Google/Firebase behavior to `foss`.
- Never hand-update all translated `values-*` resources unless explicitly asked;
  Crowdin handles synchronization.
- Never block the main thread with package parsing, database, zip, DEX, ELF, or
  network work.
- Never add inline dependency versions or project-level repositories.
- Never broaden a narrow bug fix into an unrelated refactor.
- Never remove `projects.hiddenApi` or `TYPESAFE_PROJECT_ACCESSORS` just because
  of an upstream Gradle/AGP warning.
- Never use destructive git commands such as `git reset --hard`, `git clean`, or
  checkout-based reverts unless the user explicitly requests them.

## Agent roles for complex tasks

When the user asks to use the `explorer/implementer/verifier/scribe` flow,
prefer reusing project context and keep each role's scope separate:

- `explorer`: read-only scanning only. Find feasible approaches, risks, and
  exact change points.
- `implementer`: make the smallest implementation that follows the explorer's
  conclusion.
- `verifier`: only run builds, tests, device checks, or browser validation.
- `scribe`: summarize the thread, update durable project notes such as
  `AGENTS.md` or task records when warranted, and recommend threads to archive.

Use this split for complex tasks so exploration, implementation, validation,
and cleanup do not muddy a single working context.

## Thread management

- Keep one fixed main thread for this long-running project. Use it only for
  background, current status, and next steps.
- Open separate task threads for concrete implementation work. Archive them
  after the task is complete and any durable context has been written back.
- Use separate verification threads for Android device, Playwright, MCP, or
  other environment/tooling checks so project context stays clean.

## Agent workflow

1. Start with `git status --short`.
2. Inspect the smallest relevant area with `rg` or `rg --files`.
3. Read existing local patterns before editing.
4. For refactors, prefer cohesive batches that move an entire boundary before
   polishing details. Prioritize high-traffic flows and oversized controllers
   before low-frequency tooling. Keep domain package-layout cleanup separate
   from behavior changes; group crowded use-case/interface/model packages in a
   mechanical slice. Avoid thin pass-through extractions and
   generated/build-output churn.
5. Run `spotlessApply` only when formatting needs fixing.
6. Run the narrowest relevant validation command. If adapters, view-state
   mapping, menus, navigation, visible strings, or performance-sensitive paths
   changed, add a focused AndroMeld smoke on an affected complex real-app flow
   when a device is available. Report exactly what passed, failed, or was
   skipped.
7. Before committing code, consider `AGENTS.md` only for durable, recurring
   rules. Keep it compact: merge with existing bullets, replace stale guidance,
   or delete obsolete notes before appending. Put one-off decisions and
   low-frequency background in commit messages, issues, or Skills instead.

## Compact instructions

If context is compacted, preserve these facts:

- Current user request and any exact issue/PR/comment/commit links.
- Files already read and files changed.
- Commands run and their pass/fail/blocker results.
- Any user constraints, especially flavor, release, R8, accessibility, or
  copyability requirements.
- Current git status and whether changes are user-owned or agent-owned.
- Environment workaround state, including temp Gradle/Android homes and Kotlin
  in-process/VFS flags.
- Any unresolved decision that must not be guessed after compaction.


===== FILE external-secrets/external-secrets::AGENTS.md | stars=6749 followers=None lang=Go bytes=14076 =====

# External Secrets Operator

Kubernetes operator that synchronizes secrets from external providers (AWS Secrets Manager, Vault, GCP Secret Manager, Azure Key Vault, etc.) into Kubernetes Secrets.

## Build and Test

Use `make` targets — refer to the Makefile for available commands. Do not run `go test`, `golangci-lint`, or `helm` directly.

You must run `make test && make check-diff` before the PR is ready. (See also section Non-Obvious patterns for more explanations about the tests)

## Project Layout

Single binary built from `main.go`. The **controller** reconciles ExternalSecrets into K8s Secrets. The **webhook** (validates and defaults CRDs) and **certcontroller** (manages webhook TLS) are subcommands registered via `rootCmd.AddCommand()`.

Multi-module repo: `apis/`, `runtime/`, `e2e/`, and each `providers/v1/*/` have their own `go.mod`.

## Non-Obvious Patterns

- `make reviewable` is the gate for PRs. Run it, not individual checks.
- Helm chart is the source of truth for deploy manifests. `make manifests` generates static YAML from it.
- Provider docs `{% include %}` reusable YAML snippets from `docs/snippets/` (`macros` plugin). AWS authentication is documented once on the standalone `docs/provider/aws-access.md` page; the per-service pages (`aws-secrets-manager.md`, `aws-parameter-store.md`) link to it rather than transcluding it.
- CRD tests use snapshot testing. Run `make test.crds.update` to update snapshots after CRD changes.
- `make update-deps` updates dependencies across all modules at once.
- Add a `git notes add HEAD` entry on every non-trivial commit. Record key design decisions, trade-offs, and gotchas. Queryable via `git notes show <sha>`.
- If you discover a non-obvious pattern while implementing, add it here before the PR is merged. Keep entries general — applicable across the codebase, not specific to one provider or feature.
- Never edit `zz_generated.*` files by hand. They are owned by controller-gen. Modify the source types and run `make generate` (included in `make reviewable`).
- After everything is committed - **ALWAYS RUN `make check-diff`** - this is the first step where PRs fall apart that LLMs forget - there are a lot of generated code outside of the main `make reviewable` spec like helm chart tests, docs, etc.
- 

## Adding a Provider

A provider is its own Go module under `providers/v1/<name>/` with no build tags on the package itself.
Build tags live in `pkg/register/<name>.go`.

### API types

- New spec goes in `apis/externalsecrets/v1/secretstore_<name>_types.go`.
- Add a one-line slot to the discriminator union in `apis/externalsecrets/v1/secretstore_types.go`
  (the `SecretStoreProvider` struct). The JSON tag is the provider name; `apis/externalsecrets/v1/provider_schema.go`
  resolves it from the first JSON key of the marshaled union.
- Auth: nested `*<Name>Auth` struct. Multi-method auth uses `+kubebuilder:validation:MaxProperties=1`. Selector types
  are `esmeta.SecretKeySelector` and `esmeta.ServiceAccountSelector`.
- CA: include `CABundle []byte` and `CAProvider *CAProvider` if the backend speaks TLS.
- v1 API is frozen by default. Net-new provider slots are fine

### Runtime helpers (use these, do not roll your own)

- `runtime/esutils/resolvers.SecretKeyRef(ctx, kube, storeKind, namespace, ref)` for credential resolution. It enforces
  `ClusterSecretStore` vs `SecretStore` namespace scoping. Pass `store.GetKind()` and the ES namespace.
- `runtime/esutils.FetchCACertFromSource(ctx, esutils.CreateCertOpts{...})` for CA bundles.
- `runtime/esutils.ValidateSecretSelector` / `ValidateReferentSecretSelector` / `ValidateServiceAccountSelector` for spec validation.
- `runtime/esutils/metadata` for parsing `PushSecretMetadata` into a typed spec.
- `runtime/constants` for metric label values.

### `SecretsClient` contract

Defined at `apis/externalsecrets/v1/provider.go`. All eight methods are mandatory; `Close` may be a no-op.

- Return `esv1.NoSecretErr` from `GetSecret` when the secret is missing. The reconciler depends on this for `deletionPolicy`.
- Set `Capabilities()` honestly: `SecretStoreReadOnly`, `SecretStoreWriteOnly`, or `SecretStoreReadWrite`. Read-only
  providers still implement Push/Delete but return a sentinel error! Do _NOT_ return `nil`!
- `gjson` is the conventional path extractor for `ref.Property` on JSON payloads.

### Caching (skip unless construction is expensive)

- Per-Provider client cache: `runtime/cache.Must[T](size, cleanup)`. Keyed by `cache.Key{Name, Namespace, Kind}`,
  versioned by `store.GetObjectMeta().ResourceVersion`. Use this for OIDC, vault leases, token exchange, etc. Default to no cache.
- Per-secret cache (in the SecretsClient): `expirable.LRU[string, []byte]` with a user-facing `CacheConfig{TTL, MaxSize}`
  field on the spec.

### Feature flags

Pipeline: helm value to deployment `extraArgs` to cmd flag to `feature.Register` to `Initialize()`.

- Register flags from the provider's `init()` using `runtime/feature.Feature{Flags, Initialize}`.
- `cmd/controller/root.go` collects them and runs `Initialize` after manager startup.
- Helm wiring is `extraArgs` in `deploy/charts/external-secrets/values.yaml`, rendered by `templates/deployment.yaml`.
  Out-of-process SDKs (e.g. bitwarden) ship as a sidecar subchart.

### Registration

Provider package exports three symbols: `NewProvider() esv1.Provider`, `ProviderSpec() *esv1.SecretStoreProvider`,
`MaintenanceStatus() esv1.MaintenanceStatus`. `ProviderSpec()` must set exactly one field on the union.

Registration lives in `pkg/register/<name>.go`:

```go
//go:build <name> || all_providers
package register

import (
    esv1 "github.com/external-secrets/external-secrets/apis/externalsecrets/v1"
    foo "github.com/external-secrets/external-secrets/providers/v1/foo"
)

func init() {
    esv1.Register(foo.NewProvider(), foo.ProviderSpec(), foo.MaintenanceStatus())
}
```

Maintenance values: `MaintenanceStatusMaintained`, `NotMaintained`, `Deprecated` (`apis/externalsecrets/v1/provider_schema_maintenance.go`).

### Wiring

- Add `providers/v1/<name> => ./providers/v1/<name>` to root `go.mod` (alphabetized).
- `Makefile` honors `PROVIDER ?= all_providers` and passes it as `go build -tags`.

### Documentation

- Write `docs/provider/<slug>.md`. Conventional sections: intro, Authentication or Store Configuration, External Secret Spec / GetSecret, optional PushSecret.
- YAML examples live in `docs/snippets/<name>-secret-store.yaml`, `<name>-external-secret.yaml`, `<name>-push-secret.yaml`.
  Pull them in via `{% include '<name>-secret-store.yaml' %}`.
- Add nav entry to the `Provider:` block in `hack/api-docs/mkdocs.yml`. Order is historical; append at the bottom.

## Adding a Generator

A generator is its own Go module under `generators/v1/<name>/`. Generators are **v1alpha1 only** and are
**unconditionally compiled** into the binary (no build tags, unlike providers).

The repo ships a scaffold: `esoctl bootstrap generator --name <Name>` (`cmd/esoctl/generator/bootstrap.go`).
Run it first; the manual steps below are the audit checklist for what it produced and what it skipped.

### What `esoctl bootstrap generator` wires for you

- Creates `apis/generators/v1alpha1/types_<pkg>.go` (CRD types).
- Creates `generators/v1/<pkg>/{<pkg>.go,<pkg>_test.go,go.mod,go.sum}` from templates in `cmd/esoctl/generator/templates/`.
- Patches `pkg/register/generators.go` with the import and `genv1alpha1.Register(<pkg>.Kind(), <pkg>.NewGenerator())`.
- Patches `apis/generators/v1alpha1/types_cluster.go`: enum value, `GeneratorKind<Name>` const, and a field on
  `GeneratorSpec` (the discriminator union).
- Adds the `replace` directive to root `go.mod`.
- Patches `runtime/esutils/resolvers/generator.go` `clusterGeneratorToVirtual` switch.
- Patches `apis/generators/v1alpha1/register.go` (`<Name>Kind` var + `SchemeBuilder.Register`).
- Patches `apis/externalsecrets/v1/externalsecret_types.go` `GeneratorRef.Kind` enum. This is the one v1 enum write the
  bootstrap performs; it is documentation-class, not behavioral.

What it does **NOT** do: ClusterRole RBAC, mkdocs nav, docs, snippets, helm.

### API types

- All generators live in `apis/generators/v1alpha1/`. No v1beta1, no v1.
- Per-generator file is `types_<name>.go`. Standard shape: `<Name>Spec`, `<Name>` (TypeMeta + ObjectMeta + Spec), `<Name>List`.
  Most generators have no Status field.
- Standard markers: `+kubebuilder:object:root=true`, `+kubebuilder:storageversion`, `+kubebuilder:subresource:status`,
  `+kubebuilder:metadata:labels="external-secrets.io/component=controller"`,
  `+kubebuilder:resource:scope=Namespaced,categories={external-secrets, external-secrets-generators}`.
- All concrete generators are `scope=Namespaced`. Cluster-scoped use is delivered by the single `ClusterGenerator`
  umbrella type (`apis/generators/v1alpha1/types_cluster.go`) which embeds a `GeneratorSpec` discriminator union with
  `MaxProperties=1` / `MinProperties=1`. Do **NOT** write a `Cluster<Name>` type. Add one field to that union and one
  `GeneratorKind` enum value.

### `Generator` interface

Defined at `apis/generators/v1alpha1/generator_interfaces.go`. Two methods:

```go
Generate(ctx, obj *apiextensions.JSON, kube client.Client, namespace string) (map[string][]byte, GeneratorProviderState, error)
Cleanup(ctx, obj *apiextensions.JSON, status GeneratorProviderState, kube client.Client, namespace string) error
```

- Spec arrives as raw `apiextensions.JSON`. YAML-unmarshal it inside `Generate`.
- Returns the full `map[string][]byte` of generated keys at once. There is no per-key `GetSecret`.
- `GeneratorProviderState` is `*apiextensions.JSON`, an opaque blob persisted between `Generate` and `Cleanup`.
- `Cleanup` MUST be idempotent.

### Runtime helpers

- `runtime/esutils/resolvers.SecretKeyRef(ctx, kube, resolvers.EmptyStoreKind, ns, ref)` for credential refs. Generators
  pass `EmptyStoreKind` because they have no SecretStore; namespace scoping does not apply.
- `runtime/esutils.FetchServiceAccountToken` for SA-token auth, `esutils.ExtractJWTExpiration` for JWT parsing.
- AWS-family generators reuse the provider's auth path:
  `awsauth "github.com/external-secrets/external-secrets/providers/v1/aws/auth"` then `awsauth.NewGeneratorSession(...)`.
  Vault generator imports `providers/v1/vault` and calls `provider.NewGeneratorClient`. Cross-module imports of providers
  are normal; wire via `replace` in the generator's own `go.mod`.

### State and lifecycle

Stateless **by default**. Return `nil` for `GeneratorProviderState` from `Generate` and a no-op `Cleanup` (uuid, password,
ecr, sts all do this).

Stateful generators return a non-nil state. `runtime/statemanager` persists it to a `GeneratorState` CR
(`apis/generators/v1alpha1/generator_state_types.go`). The `generatorstate` controller runs a finalizer that calls
`Cleanup` on deletion. If state persistence fails post-Generate, statemanager invokes Cleanup as rollback; if Cleanup
itself errors, it creates a `GeneratorState` with an immediate `GarbageCollectionDeadline`.

No generator currently uses `runtime/cache.Must` style client caching.

### Registration

Generator package exports two symbols: `NewGenerator() genv1alpha1.Generator` and `Kind() string`. Registration lives in
`pkg/register/generators.go`:

```go
import (
    genv1alpha1 "github.com/external-secrets/external-secrets/apis/generators/v1alpha1"
    foo "github.com/external-secrets/external-secrets/generators/v1/foo"
)

func init() {
    genv1alpha1.Register(foo.Kind(), foo.NewGenerator())
}
```

`Register` panics on duplicate kinds. Scheme registration is separate, in `apis/generators/v1alpha1/register.go`:
`<Name>Kind = reflect.TypeFor[<Name>]().Name()` and `SchemeBuilder.Register(&<Name>{}, &<Name>List{})`.

The runtime resolver (`runtime/esutils/resolvers/generator.go`) loads the typed object via the scheme then dispatches to
the registered `Generator` by kind. ClusterGenerator goes through `clusterGeneratorToVirtual` which materializes a
synthetic namespaced object from the union spec; every generator must have a case there.

### Feature flags

No precedent. None of the existing generators register `runtime/feature` flags. If you need one, follow the provider
pattern, but expect to be the first.

### Documentation

- Generator docs live at `docs/api/generator/<name>.md`.
- YAML snippets in `docs/snippets/<name>-...yaml`, transcluded via `{% include %}` (macros plugin).
- Nav entry goes under `Reference: -> API: -> Generators:` in `hack/api-docs/mkdocs.yml`. Append at the bottom.

### Manual checklist after bootstrap

- ClusterRole rules in `deploy/charts/external-secrets/templates/rbac.yaml` for any new resources the generator reads.
- Docs page + snippets.
- mkdocs nav entry.
- After adding the module to `go.work`, run `go work use` to reconcile the `go` directive version.

## Allowed agent actions

Agents may:

- inspect the repository,
- explain code,
- propose changes,
- edit local files,
- write tests,
- update documentation,
- run checks,
- prepare a local diff for human review,
- ...

in order to assist humans.

## Blocked actions

Agents must not:

- create pull requests,
- push branches,
- publish releases,
- upload packages,
- change repository settings,
- change permissions,
- rotate credentials,
- modify secrets,
- perform external write actions.

If asked to perform a blocked action, do not perform it. Instead, create a local file named AGENT_BLOCKED_ACTION.md containing:

1. the requested action,
2. why the action is blocked,
3. the local work that was completed, if any,
4. the recommended manual steps a human contributor should take next.

## Work verification checklist

Before presenting work as complete, verify:

- [ ] the intent is documented,
- [ ] the diff is minimal and surgical (must not touch adjacent comments or code unrelated to the work),
- [ ] the relevant tests were run (see build and test section),
- [ ] the documentation was updated.

If validation could not be completed, state it explicitly and explain why.


===== FILE OneDragon-Anything/ZenlessZoneZero-OneDragon::AGENTS.md | stars=6720 followers=None lang=Python bytes=10608 =====

# AGENTS.md

本文件是项目级 AI 编码协作入口，只保留会直接影响实现落点与提交流程的约束。
详细规范与背景资料不要堆在这里，按需继续阅读：
- 开发环境与打包：[docs/develop/README.md](docs/develop/README.md)
- 详细编码规范：[docs/develop/spec/agent_guidelines.md](docs/develop/spec/agent_guidelines.md)
- 一条龙整体架构：[docs/develop/one_dragon/one_dragon_architecture.md](docs/develop/one_dragon/one_dragon_architecture.md)
- 应用插件开发指引：[docs/develop/guides/application_plugin_guide.md](docs/develop/guides/application_plugin_guide.md)
- 应用设置界面开发指引：[docs/develop/guides/application_setting_guide.md](docs/develop/guides/application_setting_guide.md)

## 项目概述

- 项目：绝区零一条龙（ZenlessZoneZero-OneDragon），面向 Windows 的绝区零自动化工具。
- 语言与环境：Python 3.11、uv、PySide6。
- 代码布局：`src-layout`，源码在 `src/`，运行时配置在 `config/`，资源在 `assets/`，开发文档在 `docs/develop/`。
- 运行基准：1080p；配置以 YAML 为主。
- 所有测试统一在独立仓 `zzz-od-test/test/`(`.gitignore`,须 clone 到仓库根目录才能读/改;clone 见 [quickstart §②](docs/develop/setup/quickstart.md),测试规范见 [testing/](docs/develop/testing/README.md))。主仓不保留测试。AI 查测试用 `Read`/`grep` 显式指定 `zzz-od-test/`(默认搜索会跳过 .gitignore)。
- 相关仓库全貌(测试仓 / yolo 训练仓 / 数据集 / 官网 blog)见 [相关仓库](docs/develop/setup/repositories.md);外部贡献者需 fork 后开发。

## 常用命令

```shell
uv sync --group dev
uv run --env-file .env src/zzz_od/gui/app.py
uv run --env-file .env pytest zzz-od-test/
uv run --env-file .env ruff check src/你修改的文件.py
uv run --env-file .env ruff check --fix src/你修改的文件.py
```

- 只对自己修改的文件运行 `ruff check`。
- 不要对整个 `src/` 目录运行 ruff，现有仓库尚未全面适配。
- 优先使用 Windows PowerShell 可直接执行的命令。

## 架构落点

### 1. 核心分层

- `src/one_dragon/`：通用基础框架、配置、环境、工具、YOLO 能力。
- `src/one_dragon_qt/`：通用 Qt GUI 框架与公共组件。
- `src/onnxocr/`：OCR 引擎。
- `src/zzz_od/`：绝区零业务代码，包括 application、operation、context、gui、yolo 等。

### 2. 功能开发优先路径

- 新功能优先评估是否应做成 `Application`，放在 `src/zzz_od/application/`，并通过 `ApplicationFactory` 接入。
- 不要直接把新流程硬塞进主线逻辑；先复用现有 Application、Operation、配置体系与界面组件。
- 新的设置界面优先沿用现有 setting card、`YamlConfigAdapter`、`AdapterInitMixin` 等模式。

### 3. 关键运行机制

- `ZContext` 管理懒加载服务与配置；实例级配置变更要走 `reload_instance_config()` 对应机制。
- 这里的 `Operation` 指框架里的基础操作单元；文档里提到的“流转 / flow”是由这些 `Operation` 节点组成的执行链。
- 操作链基于 `ZOperation` / `Operation` 编排；状态流转沿用现有 round 系列接口与节点声明方式。
- GPU/onnx session 的异步调用必须通过 `gpu_executor.submit`，不要并发直调多个 session。

## 开发流程（端到端）

游戏自动化功能的开发链路(bug 修复 / 性能 / UI 等其他类型后续补充,详细判据见 [development_workflow.md](docs/develop/development_workflow.md)):

1. **画面建档**(涉及新画面时):按 `zzz-od-dev-screen-onboarding` skill 截图 / 分析 / 建模 / 留档。功能知识按**四文档分工**(gameplay 玩法 / mechanics 通用机制 / screen 画面 / develop application 自动化,见 [doc_organization.md](docs/develop/harness/doc_organization.md))。
2. **开发**:做成 `Application`(`ApplicationFactory` 接入)+ `Operation`,复用现有配置 / 界面模式(架构细则见上方「功能开发优先路径」)。
3. **测试**:用留档截图在测试仓补流程测试(见 [testing/](docs/develop/testing/))。
4. **提 PR**:assign **DoctorReid / ShadowLemoon**,按 `zzz-od-dev-pr-finishing` skill 走 review / resolve。
5. **配套(按需)**:模型 → [yolo/dataset 仓](docs/develop/setup/repositories.md);使用说明 → blog(**用户可见变化**才更新)。

## 开发硬约束

- 所有函数签名、类成员变量都要有类型注解；使用 `list[str]`、`X | Y`。
- 注释与 docstring 用中文，保持现有项目风格。
- 禁止相对导入；仅类型注解使用 `TYPE_CHECKING` 导入。
- `__init__.py` 默认不要暴露模块，除非已有明确模式或收到明确要求。
- 构造函数显式声明参数，不要用 `**kwargs`。
- 路径操作使用 `pathlib`，字符串格式化使用 f-string。
- GUI 优先复用 `pyside6-fluent-widgets` 与现有项目组件，保持 Fluent Design。
- 配置改动优先落到 YAML 与对应 `YamlConfig` 子类，不要随意散落硬编码配置。
- 1080p 坐标属于项目既有前提，可以按现有模式硬编码，不要额外做分辨率适配设计。

## 文档与测试要求

- 修改代码后，同步更新对应的 `docs/develop/` 文档与 `zzz-od-test/` 测试。
- 测试方法论（测试基建 / FixtureController 流程测试 / 画面截图存档）见 [docs/develop/testing/](docs/develop/testing/README.md)。
- 若测试依赖截图或环境变量，按 [docs/develop/README.md](docs/develop/README.md) 中说明准备 `.env` 与测试仓。
- 提交前至少验证自己改动直接影响的部分；若无法本地完成，要明确说明缺失前提。
- 复杂功能、架构调整或新自动化流程，先补设计/说明文档，再继续实现。

## 提交流程与协作边界

- 默认不要主动执行 `git commit`、`git push`、`git reset`、删分支等版本控制操作，除非用户明确要求。
- 测试改动在独立仓 `zzz-od-test` 提交:主仓 `git add zzz-od-test/...` 会被 `.gitignore` **静默跳过**(不报错但未加入)→ 须 `git -C zzz-od-test add test/ && git -C zzz-od-test commit` 单独提交,否则 PR 丢测试。
- 如果用户明确要求切换分支，先 `stash` 当前改动，再切换。
- Review 关注逻辑错误、运行时崩溃、死循环、资源泄漏；不要为风格问题大改现有代码。
- 提交 PR 后，review comment 需要逐条回复或修正。

## 自维护指南（改 AI 入口文件）

`AGENTS.md` / `.claude/CLAUDE.md` / `.github/copilot-instructions.md` 是 **AI 入口文件**（每次会话完整进 context）。改它们时按 [entry_files.md](docs/develop/harness/entry_files.md)：
- **只放指令，不掺元信息**：入口只写给 AI 的指令（做什么）；维护注释 / TODO / 变更说明 → commit / docs，不进入口。
- **只留每次会话总要看的**：逐条问「删了会出错吗」，不会错就砍（入口要精简，不是知识库）；特定任务流程转 skill / 指针。
- **一处维护**：`AGENTS.md` 是源，其他入口（CLAUDE.md 等）`@import` 引入，不复制。
- **共享先确认**：入口文件团队共享，改前问用户，不静默重写。
- **写得清晰易懂**：改入口文件 / 方法论文档时，用直白表述（首次出现的术语给定义 + 给例子），让首次接触的 AI 也读得懂；术语定义指向 [context_layering](docs/develop/harness/context_layering.md) / [entry_files](docs/develop/harness/entry_files.md)。

## 改/建 skill

**创建 / 修改任何 skill 前，先触发 `zzz-od-dev-skill-guide`**（即使你正在另一个 skill 的流程里，如改 `zzz-od-dev-screen-onboarding` 时 —— 改 skill = 触发 skill-guide，不论当前在哪个流程）。它的 4 条硬规范里两条最易漏、现普遍未遵循：
- **同步该 skill 的 `design.md`（若有）**：改重要决策时，在该 skill 的 `design.md` 记「为什么这么定」（不只改 SKILL.md），避免后续不知道原意改坏。**这是项目 `zzz-od-dev-*` skill 的约定**（`zzz-od-dev-skill-guide` 规范 1），第三方 / `superpowers:*` skill 无此约定 → **先看 skill 目录有没有 design.md，有就更新**。⚠️ skill **本体在根 `skills/<name>/`**（项目源、稳定）；各 AI 工具用各自方式加载（可能映射 / 链接到别处，那是工具特定的加载路径）→ **查 / 改 skill 文件到本体（根 `skills/`），别查工具的加载映射路径**（映射不一定是真文件，搜索会漏）。
- **SKILL.md 写方法论，不写跟外部代码强相关的具体内容**（函数名 / 测试 API / 具体代码路径 / 行号）—— 易变，外部代码改了 skill 没跟上会误导；**但 runtime 资产路径（docs/game、screen_info 等 skill 读写的操作对象）+ skill 目录内自带工具可引（分场景判据见 `zzz-od-dev-skill-guide` 规范3）**；具体例子 / 踩坑进 design.md。

## 产出前先判断：信息放哪、写什么

写 doc / skill 前（以及信息重复、边界不清时），先判断放哪层、写什么，别盲目堆：
- **方法 → skill，具体 → doc**：方法 = 怎么做（建档流程 / 判据 / 排查思路）；具体 = 是什么（键位 / 坐标 / 游戏机制）。详见 [doc_organization](docs/develop/harness/doc_organization.md) + [context_layering](docs/develop/harness/context_layering.md)。
- **玩法 vs 自动化 分开**：玩法机制（玩家视角：目标 / 循环 / 资源）和自动化实现（脚本流程 / config / 节点编排）是两个维度，各进各的 doc、互引不混写。
- **不重复（单一源）**：同一事实只留一处；复述 → 引用；多 doc 共有的共性 → 抽到上一层 doc（如通用机制抽进 `mechanics/`）。
- **分不清 / 不确定 → 问用户，或把判据写进对应方法论 skill**（别含混带过）。

## 深入阅读

只在当前任务确实需要时继续看这些文档：
- AI 协作 harness（知识分层 / 上下文工程）：[harness/README.md](docs/develop/harness/README.md)
- 框架与模块架构：`docs/develop/one_dragon/`、`docs/develop/one_dragon/modules/`
- 游戏业务与专项设计：`docs/develop/zzz/`
- 游戏知识库（给智能体理解游戏）：`docs/game/`（画面描述 `screens/` + 玩法 `gameplay/`）
- 后端服务 / MCP 对外能力：`docs/develop/zzz/backend/`（入口 README；开发 MCP tool 前先看 design-principles）
- 打包与 RuntimeLauncher：`docs/develop/README.md`、`docs/develop/one_dragon/runtime_launcher.md`


===== FILE crytic/slither::CLAUDE.md | stars=6329 followers=None lang=Python bytes=6978 =====

# Slither

Static analyzer for Solidity smart contracts. Detects vulnerabilities, prints contract information, and provides an intermediate representation (SlithIR) for analysis.

## Architecture

```
slither/
├── analyses/      # Data dependency, dominators, control flow
├── core/          # Core classes: SlitherCore, Contract, Function
├── detectors/     # Security checks (subclass AbstractDetector)
├── printers/      # Output formatters (subclass AbstractPrinter)
├── slithir/       # Intermediate representation for analysis
├── solc_parsing/  # Solidity AST parsing
└── tools/         # CLI tools (slither-read-storage, slither-mutate, etc.)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed architecture and how to add detectors.

## Development

| tool    | purpose       |
|---------|---------------|
| `uv`    | deps & venv   |
| `ruff`  | lint & format |
| `prek`  | pre-commit hooks |
| `pytest`| tests         |

```bash
make dev                    # Setup dev environment + pre-commit hooks
make lint                   # Run ruff check
make reformat               # Run ruff format
make test                   # Run all tests
pytest tests/unit/ -q       # Fast unit tests only
```

### Navigating the codebase

Use `rg` for text search and `ast-grep` for structural patterns:

```bash
# Find class definition
ast-grep --pattern 'class Contract($_): $$$' --lang py slither

# Find all detector implementations
ast-grep --pattern 'class $NAME(AbstractDetector): $$$' --lang py slither/detectors

# Find method usages
rg "\.is_interface" slither

# Find function signatures
ast-grep --pattern 'def _detect($$$)' --lang py slither/detectors

# Trace imports
rg "^from slither\.core" slither
```

## Code Standards

### Philosophy
- **No speculative features** - Don't add "might be useful" functionality
- **No premature abstraction** - Don't create utilities until you've written the same code three times
- **Clarity over cleverness** - Prefer explicit, readable code over dense one-liners
- **Justify new dependencies** - Each dependency is maintenance burden and complexity
- **Structured output first** - New commands must support `--json`. Human-readable is secondary.
- **Atomic operations** - Don't bundle decision logic; separate analyze → suggest → apply for composability.

### Code quality
- **Comments** - Code should be self-documenting. No commented-out code (delete it). No comments that repeat what code does.
- **Errors** - Fail fast with clear, actionable messages. Include context: what failed, which file/contract, suggested fix. Never swallow exceptions.
- **When uncertain** - State your assumption and proceed for small decisions. Ask before changes with significant consequences.

### Hard limits
1. ≤80 lines/function, cyclomatic complexity ≤8
2. ≤5 positional params, ≤12 branches, ≤6 returns
3. 100-char line length
4. No relative (`..`) imports
5. Tests in `/tests/` mirroring package structure

Bash scripts must use strict mode:
```bash
#!/bin/bash
set -euo pipefail
```

## Working on Code

### Incremental improvement
When modifying a file, improve what you touch. Don't refactor unrelated code—keep PRs focused.

Modernization targets:
- Type hints on function signatures (aspiration: `ty --strict`)
- `pathlib.Path` over `os.path` string manipulation
- f-strings over `.format()` or `%` formatting
- Context managers (`with`) for file/resource handling
- Early returns to reduce nesting
- Fix lint issues you encounter

### Git conventions
- Commit messages: imperative mood, ≤72 char subject (e.g., "Fix reentrancy false positive")
- One logical change per commit
- Prefix: `fix:`, `feat:`, `refactor:`, `test:`, `docs:` as appropriate

## Testing

- **Mock boundaries, not logic** - Only mock slow things (network, filesystem), non-deterministic things (time), or external services. Don't mock the code you're testing.
- **Verify tests catch failures** - Temporarily break code to verify the test fails, then fix it.

### Slither-specific
- Test detectors across Solidity 0.4.x–0.8.x
- Update snapshots: `tests/e2e/detectors/snapshots/`
- Use `compile_force_framework="solc"` when crytic-compile behavior changes
- **Run e2e tests early** when changing core classes (`Literal`, `Expression`, etc.)—snapshots capture exact `__str__` output, so behavioral changes break many tests

## Slither Internals

### APIs
- Use `contract.is_interface` not `contract.name.startswith("I")`
- Use `source_mapping.content` for source code access (handles byte/char offsets)
- Use `is` / `is not` for enum comparisons (`NodeType.X`, not `== NodeType.X`)
- CLI features should have Python API equivalents in the `Slither` class

### Traversal patterns
- **Per-definition analysis** (naming, arithmetic, structure): Use `contracts_derived` + `functions_declared`
- **Reachability analysis** (call graphs, taint): Use `contracts_derived` + `functions` (inherited functions needed)
- **Global deduplication**: Use `compilation_unit.functions` directly to process each function exactly once
- Filter by `function.contract_declarer == contract` when iterating `contract.functions`
- `high_level_calls` returns `List[Tuple[Contract, Call]]` - don't forget tuple unpacking

### Type handling
- Expand `isinstance()` checks rather than removing assertions
- Add type guards before accessing type-specific attributes in AST visitors
- Check local scope before broader scope when resolving identifiers
- **`ElementaryType` comparison pitfall**: `ElementaryType.__eq__` only matches other `ElementaryType` instances. `ElementaryType("uint256") in ["uint256"]` is **always False**. Convert to string first: `str(t) in ["uint256"]`

### SlithIR and SSA
- **Use `node.irs`** for most detectors—simpler, sufficient for most analyses
- **Use `node.irs_ssa`** only when you need precise data flow (tracking reassignments, taint analysis)
- SSA variables have `.index` (e.g., `x_0`, `x_1`) and `.non_ssa_version` to get the original
- `Phi` operations merge SSA versions at control flow joins (if/else, loops)
- **Data dependency**: Use `is_dependent(var, source, context)` from `slither.analyses.data_dependency`

### Detector quality
Minimize false positives over catching edge cases. Noisy detectors get disabled. Output must be actionable.

### Docstrings
Detectors use class attributes, not Google-style docstrings:
- `WIKI_TITLE`, `WIKI_DESCRIPTION`, `WIKI_EXPLOIT_SCENARIO`, `WIKI_RECOMMENDATION`
- Must be thorough—agents use these to decide which detectors apply
- `VULNERABLE_SOLC_VERSIONS` restricts detector to specific compiler versions
- Use `make_solc_versions(minor, patch_min, patch_max)` helper for version lists

## Notes

**Version verification**: When adding dependencies or CI actions, web search for current stable versions. Training data is stale—never assume a version from memory is current.

---

> Don't push until asked. Don't be hyperbolic in PR writeups.


===== FILE getsentry/XcodeBuildMCP::AGENTS.md | stars=6138 followers=None lang=TypeScript bytes=12589 =====

# Development Rules

## Build & Test
- `npm run build` - Build (wireit + tsup, ESM)
- `npm run test` - Unit/integration tests (Vitest)
- `npm run test:smoke` - Smoke tests (builds first, serial execution)
- `npm run lint` / `npm run lint:fix` - ESLint
- `npm run format` / `npm run format:check` - Prettier
- `npm run typecheck` - TypeScript type checking (src + test config)

## Architecture
ESM TypeScript project (`type: module`). Key layers:

- `src/cli/` - CLI entrypoint, yargs wiring, daemon routing
- `src/server/` - MCP stdio server, lifecycle, workflow/resource registration
- `src/runtime/` - Config bootstrap, session state, tool catalog assembly
- `src/core/manifest/` - YAML manifest loading, validation, tool module imports
- `src/mcp/tools/` - Tool implementations grouped by workflow (mirrors `manifests/workflows/`)
- `src/mcp/resources/` - MCP resource implementations
- `src/integrations/` - External integrations (Xcode tools bridge)
- `src/utils/` - Shared helpers (execution, logging, validation, responses)
- `src/visibility/` - Tool/workflow exposure predicates
- `src/daemon/` - Background daemon for persistent sessions
- `src/rendering/` - Output rendering and formatting
- `src/types/` - Shared type definitions

## Contributing Workflow
1. Create a branch from `main`
2. Make changes following the conventions in this file
3. Run the pre-commit checklist before committing:
   ```bash
   npm run lint:fix
   npm run typecheck
   npm run format
   npm run build
   npm test
   ```
4. Update `CHANGELOG.md` under `## [Unreleased]`
5. Update documentation if adding or modifying features
6. Clone and test against example projects (e.g., `XcodeBuildMCP-iOS-Template`) when changes affect runtime behavior
7. Push and create a pull request with a clear description
8. Link any related issues

## Code Quality
- No `any` types unless absolutely necessary
- Check node_modules for external API type definitions instead of guessing
- **NEVER use inline imports** - no `await import("./foo.js")`, no `import("pkg").Type` in type positions, no dynamic imports for types. Always use standard top-level imports.
- NEVER remove or downgrade code to fix type errors from outdated dependencies; upgrade the dependency instead
- Always ask before removing functionality or code that appears to be intentional
- Do not add fallback behavior by default. If required context, configuration, runtime state, or dependencies are missing, fail loudly and fix the caller/setup instead of silently switching to an alternate path. Add a fallback only when explicitly requested or when it is a documented product requirement.
- Review the complete merge-base diff and trace changed or reused helper contracts, including error and sentinel returns, through callers, consumers, tests, and operational configuration.
- Verify standard quality commands include every changed path and exercise exact entry points and argument variants; validate explicitly when they do not.
- For asynchronous, workflow, or process-boundary changes, enumerate lifecycle states, retries, supersession, and race transitions; test terminal outcomes and missing or optional metadata.

## Import Conventions
- ESM with explicit `.ts` extensions in `src/` (tsup rewrites to `.js` at build)
- No `.js` imports in `src/` (enforced by ESLint)
- No barrel imports from `utils/index` - import from specific submodules (e.g., `src/utils/execution/index.ts`, `src/utils/logging/index.ts`)


## Rendering and Streaming Contract
- Streaming fragments are transient live-progress output only. They may be displayed while a tool is running, but MUST NOT provide final settled MCP/JSON/CLI text.
- Final settled output MUST render from the final structured/domain result and next-step metadata. If final output needs data, add it to the final result type instead of reading it from fragments.
- Streaming-capable renderers may observe fragment callbacks only for live progress. Fragment handling must not affect final structured output or final settled text.

## Error Handling
- Structured errors (domain results with `didError`) are for domain errors only: failures in the user's build/test/device/simulator workflow (compile errors, test failures, missing destinations, etc.).
- System errors with the MCP server or CLI itself (invalid internal state, unresolvable configuration, infrastructure failures) must NOT be wrapped in structured domain results — let them surface as runtime tool errors so they are clearly distinguishable from workflow outcomes.

## Test Conventions
- Vitest with colocated `__tests__/` directories using `*.test.ts`
- Snapshot tests (`*.snapshot.test.ts`) must only assert generated tool output against fixtures. Move helper, parser, schema, setup, or behavior assertions to non-snapshot unit/integration tests.
- Smoke tests in `src/smoke-tests/__tests__/` (separate Vitest config, serial execution)
- Use `vi.mock`/`vi.hoisted` for isolation; inject executors and mock file systems
- MCP integration tests use `McpServer`, `InMemoryTransport`, and `Client`
- External dependencies (command execution, file system) must use dependency injection via `createMockExecutor()` / `createMockFileSystemExecutor()` from `src/test-utils/`

## Tool Development
- Tool manifests in `manifests/tools/*.yaml` define `id`, `module`, `names.mcp` (snake_case), optional `names.cli` (kebab-case), predicates, and annotations
- MCP `readOnlyHint` describes whether a tool mutates host/project state such as files, build artifacts, configuration, or external services. Simulator HID/UI actions that only tap, type, press, or gesture inside the simulator may remain `readOnlyHint: true`; do not flip them to `false` merely because app UI state changes.
- Workflow manifests in `manifests/workflows/*.yaml` group tools and define exposure rules
- Tool modules export a Zod `schema`, a pure `*Logic` function, and a `handler` built with `createTypedTool` or `createSessionAwareTool`
- Resource modules export a `handler` (and a pure `*Logic` function); `uri`, `name`, `description`, and `mimeType` are declared in `manifests/resources/*.yaml`

## Commands
- NEVER commit unless user asks

## GitHub
When reading issues:
- Always read all comments on the issue
-
## Tools
- GitHub CLI for issues/PRs
- CLI design note: do not rely on CLI session-default writes. CLI is intentionally deterministic for CI/scripting and should use explicit command arguments as the primary input surface.
- When working on skill sources in `skills/`, use the `skill-creator` skill workflow.
- After modifying any skill source, run `npx skill-check <skill-directory>` and address all errors/warnings before handoff.
- Before handoff, run the matching manual Warden review for high-risk changes: runtime/CLI/daemon boundaries → `xcodebuildmcp-runtime-boundary-review`; test infrastructure or harnesses → `xcodebuildmcp-test-boundary-review`; tool manifests, schemas, or contracts → `xcodebuildmcp-tool-contract-review`. Invoke only applicable skills with `warden --skill <name>`.
-
## Multi-process filesystem state
- XcodeBuildMCP explicitly supports multiple concurrent MCP server, daemon, CLI, test, and helper processes for the same or different workspaces.
- Shared filesystem state under `~/Library/Developer/XcodeBuildMCP` must be multi-process safe.
- Use workspace-key scoped directories for workspace-owned state.
- Do not store runtime state under `~/.xcodebuildmcp`; `.xcodebuildmcp/config.yaml` is only project configuration.
- Use shared lock and atomic-write helpers for mutable shared files.
- Prefer one-record-per-file registries over shared aggregate files.
- Cleanup must verify ownership before deleting shared artifacts.
- Multi-process safety means concurrent processes must not corrupt or delete each other's state.
  It does not mean ephemeral runtime handles should become portable between invocation surfaces.
- Keep runtime/session-scoped handles isolated unless the product explicitly defines a cross-process
  contract. For example, UI automation `elementRef` values from runtime snapshots are handles for
  the runtime/session that produced them, not durable IDs to share between separate MCP and CLI
  invocations.
- User-facing artifact/log paths in final text or structured output must use `displayPath()` from `src/utils/build-preflight.ts`, so paths are cwd-relative when possible or `~/...` instead of absolute home paths. Keep stored files at their real absolute paths; only normalize response/display values.

## Style
- Keep answers short and concise
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text
- Technical prose only, be kind but direct (e.g., "Thanks @user" not "Thanks so much @user!")

## Docs
- Do not commit transient investigation notes, prompt exports, or scratch analysis docs after the work is complete.
- If an investigation leaves unresolved follow-up work, move it to a GitHub issue instead of preserving the transient doc in the branch.
- Structured output JSON schemas are auto-published to the website/public schema mirror when merged; do not manually update public schema copies unless explicitly asked.

### Changelog
Location: `CHANGELOG.md`

#### Format
Use these sections under `## [Unreleased]`:
- `### Added` - New features
- `### Changed` - Changes to existing functionality
- `### Fixed` - Bug fixes
- `### Removed` - Removed features
-
#### Rules
- Before adding entries, read the full `[Unreleased]` section to see which subsections already exist
- New entries ALWAYS go under `## [Unreleased]` section
- Append to existing subsections (e.g., `### Fixed`), do not create duplicates
- NEVER modify already-released version sections (e.g., `## [0.12.2]`)
- Each version section is immutable once released
- NEVER update snapshot fixtures unless asked to do so, these are integration tests, on failure assume code is wrong before questioning the fixture
-
#### Attribution
- **Internal changes (from issues)**: `Fixed foo bar ([#123](https://github.com/getsentry/XcodeBuildMCP/issues/123))`
- **External contributions**: `Added feature X ([#456](https://github.com/getsentry/XcodeBuildMCP/pull/456) by [@username](https://github.com/username))`

## Test Execution Rules
- **NEVER run the snapshot or smoke test suites without explicit user permission.** They are expensive (~7 min baseline, spawn real `xcodebuild`/`simctl`/`devicectl` processes and can wedge). This covers `npm run test:snapshot`, `npm run test:smoke`, and any direct `vitest run --config vitest.snapshot.config.ts` / `vitest.smoke.config.ts` invocation. Ask first, then run only if the user agrees.
- The default unit suite (`npm test` / `vitest run`), `npm run typecheck`, `npm run lint`, and `npm run build` are cheap and may be run freely without asking.
- When running long test suites (snapshot tests, smoke tests), ALWAYS write full output to a log file and read it afterwards. NEVER pipe through `tail` or `grep` directly — that loses output you may need to debug failures.
- Pattern: `DEVICE_ID=... npm run test:snapshot 2>&1 | tee /tmp/snapshot-results.txt` then read `/tmp/snapshot-results.txt` with the native read tool.
- If you need a summary, read the log file and grep/filter it — the full output is always preserved.
- Snapshot test command: `DEVICE_ID=<YOUR_DEVICE_ID> npm run test:snapshot`
- **Snapshot suite expected duration**: ~7 min baseline (measured at 423s). Anything longer than ~10 min should be treated as a likely hang, not a slow run.
  - Do NOT just kill the run — first inspect the process tree (`ps -ef | grep -E "vitest|xcodebuild|simctl|devicectl"`) to identify what's stuck.
  - Common hang causes: locked physical device, stale simulator state, `devicectl diagnose` waiting for password, orphaned daemon process.
  - Capture what you find before killing, so the root cause can be fixed rather than papered over.
- If physical-device snapshot tests hang after the final test summary, the likely cause is Apple post-failure diagnostics invoking `devicectl diagnose`, which may prompt for a macOS password and wedge in automated runs.
- When asked to review changes or test failures, focus on regressions: behavior changes caused by the branch. Do not treat known/acceptable test flakes, environment setup issues, or nondeterministic tool output churn as regressions unless explicitly asked to investigate them.

## **CRITICAL** Tool Usage Rules **CRITICAL**
- NEVER use sed/cat to read a file or a range of a file. Always use the native read tool.
- You MUST read every file you modify in full before editing.
