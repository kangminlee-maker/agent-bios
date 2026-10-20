---
created_at: 2026-10-20T19:10:00+09:00
head: a0ce9fe
kind: review
supersedes: none (companion to 2026-10-20T1312--20948d2--mechanism-design.md)
---

# Session distill — feasibility probes (2026-10-20)

## 0. What this record is

The mechanism design (`2026-10-20T1312--20948d2--mechanism-design.md`, §14) requires its probes to
pass before the implementation plan. This record states what each probe showed on the hosts as
installed on 2026-10-20 — Claude Code 2.1.304 (`/Users/kangmin/.local/bin/claude`), codex-cli
0.163.0 (`/opt/homebrew/bin/codex`), macOS — the design changes they force, the corrections they
make to earlier claims, and the decisions left to the owner. It is a dated record: the numbers are
claims about that day's hosts, to be re-measured after any host upgrade.

Evidence lives outside the repository, because it holds session transcripts that carry the owner's
instructions: `~/.local/share/agent-bios-workbench/distill-probes-20261020/<probe>/`, each with
`RESULTS.md`, `raw/`, its scripts, and `SHA256SUMS` (every group verified after the last re-run,
2026-10-20 about 19:40; `codex-records` lists paths relative to `raw/`). Paths below are relative to that directory. Every probe ran its
model calls in cells whose HOME, CLAUDE_CONFIG_DIR, CODEX_HOME and agent-bios roots it created, and
checked the owner's real roots before and after.

Probes ran in thirteen groups: twelve subagents (claude-sonnet-5-5; `reconstruction` on
claude-opus-5-5) and one Workflow run from the coordinating session (`workflow/`). The common brief
is `BRIEF.md`.

## 1. Verdicts

| Probe | Claude | Codex |
|---|---|---|
| 1 Headless activated actor | met (`claude-activation/` run 2) | met (`codex-activation/`) |
| 2 Isolated episode | met only with clean ancestry and a new static rule (F14) | met, with content-hash reports and an outer sandbox that excludes Codex's own (F10, F16) |
| 3 Child route | met; `--append-system-prompt` reaches only fork children, not ordinary ones (F11) | brief capture not met as written: the spawn message is ciphertext; an echo substitute works (F20) |
| 4 Runner acceptance | Workflow channel: attested, not isolated (F3). Hermetic Claude runner: did not exist; a prototype met the tested cases, with structural refusals planted and the declared-instruction route not yet in its gate (F2) | `codex-run.sh`: a prototype gate met the tested cases; the hermetic profile leaked and is fixed (F1); observed model only through a debug channel (F4) |
| 5 Codex capture under the real profile | — | met by a prototype capture wrapper, not by the shipped receipt (which holds only packet and result hashes, seat and exit status); a warm-up request per thread, observed model trace-only (F4, F22) |
| 6 Workflow persistence | met; a truncated subagent was not produced (unknown) | — |
| 7 Reconstruction | met for the whole library; R was conservative and entanglement appeared (F21) | (R author) |
| 8 Lineage markers | met on 57 planted sessions; no positive fresh marker (F8) | met on 30 planted sessions (F7, F9) |
| 9 Episode accounting | main requests per-request; children delayed; compaction aggregate only (F22) | met on the websocket transport; two channels undercount (F22) |
| 10 Installation receipt | met by prototype, 2 files, about 113 lines (F12) | |

## 2. Findings that change the design

### Contracts and the model-call gate (§3.1, §3.2)

- **F1 — the hermetic Codex profile was not hermetic.** `codex-run.sh --profile hermetic` gave
  Codex only a fresh CODEX_HOME. Codex also reads project AGENTS.md from the git root down to
  `--cd`, and user skills from HOME: with `--cd` at this repository the model input carried one
  AGENTS.md message of 34,645 characters and 19 skills, 15 of them the owner's
  (`codex-runner/` §2.2; `hermetic-fix/raw/`). Fixed on branch `fix/hermetic-isolation`, commit
  `12b2769` (decision D-20261020-7b89dc): an empty temporary HOME and `project_doc_max_bytes=0`;
  the parity gate's `codex_run` check now asserts both. Replayed on the commit's tree with the
  shipped wrapper put back, it fails by name four times; on the fix it passes
  (`hermetic-fix/raw/gate-shipped.txt`, `gate-fixed.txt`).
  The independent-judgment contract additionally requires effective-context evidence per call,
  which Codex provides model-free: `codex debug prompt-input` with the call's own homes and `-c`
  overrides renders the model input byte-equal to the real call's context messages, and `codex
  app-server thread/start` returns `instructionSources` (`codex-runner/` §2.3).
- **F2 — the hermetic Claude runner, specified.** It did not exist (`wrappers/claude-run.sh` is not
  hermetic and says so). Measured specification (`claude-runner/`): a fresh HOME and
  CLAUDE_CONFIG_DIR per call under clean ancestry (F14); the owner's subscription token in the
  child environment only; a driver-created empty working directory or one holding exactly a
  declared manifest; `--safe-mode --setting-sources "" --strict-mcp-config --disable-slash-commands
  --tools ""`; `--json-schema` for structured output; session persistence on, because the
  effective-context evidence exists only in the transcript (`instructions`, skill, agent, MCP and
  hook attachments, and the full sent request); `CLAUDE_CODE_MAX_OUTPUT_TOKENS` per stage. `--bare`
  cannot be used: it never reads OAuth. Under `--safe-mode` CLAUDE.md files do not load. A
  zero-cost probe showed `--append-system-prompt-file` text arriving as a sent system block, so the
  proposed route for declared instructions is that flag with the file pinned by hash in the
  manifest; it is not yet in the prototype gate, whose declared counterparts used separate
  profiles that load project files. Five real undeclared
  controls (working-directory CLAUDE.md, ancestor CLAUDE.md, cell CLAUDE.md plus rules, a skill,
  auto-memory) returned valid, canary-free answers and were rejected by that evidence; their
  declared counterparts were accepted. A one-line call costs about 3.2k input tokens.
- **F3 — the Workflow channel is a producing channel only.** Its transcripts give the result, call
  binding, observed model, and per-request usage, but every subagent receives the owner's user,
  project and memory instruction files (5) and 119 skills (`workflow/`). A gate reading the
  `instructions` attachment rejects it for independent judgments. Its floor is about 58k input
  tokens per call.
- **F4 — observed-model attestation.** Claude: the response's `message.model`, the `modelUsage`
  keys and each request's `params.model` must all equal the seat (shown on haiku and opus; a
  `--fallback-model` and an alias control were rejected). Codex: no supported output carries the
  server's model; the rollout holds the configured model only. The server's `response.model` and
  `reasoning.effort` appear only in websocket frames under `RUST_LOG='tungstenite::protocol=trace'`,
  version-bound and unsupported; with the channel silent the prototype fails closed
  (`MODEL_UNATTESTED`). Owner decision O1.
- **F5 — completion and failure.** Claude's `result.subtype` reads `success` on errors; failure is
  `is_error`, `terminal_reason` other than completed, an assistant `stop_reason` outside
  `end_turn`/`stop_sequence`/`tool_use`, `safety_stops > 0`, or a missing `structured_output`. A real
  Claude truncation can be forced (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`); Codex 0.163.0 has no output cap,
  so its truncation control is a real aborted stream plus a planted `response.incomplete` frame.
  Real Claude refusals occurred in the accounting probe — two responses with `stop_reason: refusal`
  and an automatic continuation (`claude-accounting/raw/ep-q-refusal-continuation/`) — so that
  shape is known; the runners' refusal controls are still planted, and a real Codex refusal is
  unknown.
- **F6 — receipts.** The launcher's closed receipt grammar already carries arbitrary evidence through
  `--evidence key=value`; the required keys (call id, profile and flag-set hash, cwd, manifest and
  observed-context hashes, schema hash, observed models and effort, usage state and totals, capture
  hash, session or thread id) need no launcher change. Claude adds three host-level bindings: the
  recorded request text equals the packet, the request's StructuredOutput tool definition equals
  the schema, and `structured_output` equals the last recorded tool call.

### Census and lineage (§5.1, §5.3)

- **F7 — resume is not a lineage edge on either host.** Resume appends to the same file under the
  same id (Codex: no new `session_meta`; Claude: a `cost-state` record then more activity), and
  compaction is in place (Claude `system/compact_boundary`). Forks and children are separate files
  linked by pointers: Codex `forked_from_id`, `history_base`, `parent_thread_id`,
  `source.subagent.thread_spawn`; Claude copies record uuids under a new `sessionId`. "Never
  resumed" must not be a condition of being a root: activated Codex sessions are created by the
  app-server and resumed before their first turn. Keep `root` (counts toward recurrence) apart
  from `fresh` (never resumed or compacted).
- **F8 — Claude has no positive fresh marker.** An in-file root is negative space: no
  inherited-head marker and not the target of a `continued-in` pointer. Record-uuid sharing
  survives timestamp rewriting and joins (timestamp, human text) as a link criterion: it links a
  root to its forks and disqualifies *strict freshness*, but does not by itself take the original
  root out of recurrence (`claude-records/scripts/classify.py`, `raw/p8-eval.txt`). On the owner's
  real corpus, 4 of 9 multi-member components have no unique root and stay of unknown
  independence (`claude-records/raw/real-classify.txt`). Owner decision O4.
- **F9 — a lone copy cannot be told from its original.** A copy of a never-resumed fresh session
  with a new id classifies fresh when alone on both hosts; it is caught only through shared
  host-minted record ids when the original is present. S1 records file hashes and checks record-id
  sharing corpus-wide; a session whose file provenance is not established keeps unknown
  independence.
- **F10 — harness sessions are labelled by the host.** Claude `-p` sessions record entrypoint
  `sdk-cli` (590 of the owner's 693 top-level files are `sdk-*`), so S1 excludes harness episodes by
  cell path together with the **first** recorded entrypoint: an interactive root later resumed
  headlessly records both `cli` and `sdk-cli` and stays an interactive session (3 of the owner's
  files, reproduced in `claude-records/raw/p8-eval.txt`). Codex takes `--thread-source` and the
  app-server client name as
  caller-written labels — a courtesy for the census, never authority.

### Delivery evidence (§6.3)

- **F11 — what each host records about delivered instructions.** Codex's rollout and model input
  record the loaded instruction *text* (`world_state.agents_md`, developer messages), not paths;
  the pre-run `codex app-server thread/start` does list `instructionSources` by path
  (`codex-runner/raw/appserver-thread-start-repo1-sub.json`), but nothing records paths for a
  child. So child delivery is shown by content hash against the cell's declared files, and where a
  name is wanted the delivered text carries an artifact id line. Claude records instruction files
  by path and kind and skills and agents by name; settings hooks appear by event name only, while
  plugin hooks leave transcript attachments with the (unexpanded) command and its exit code
  (`claude-records/raw/p3-plugin-records.txt`). On Claude, the
  activation's `--append-system-prompt` reaches only `fork` children; child reach needs a carrier
  the child's record shows (plugin agent, plugin `SubagentStart` hook, or a CLAUDE.md), each
  embedding the artifact id line.
- **F12 — the installation receipt.** On every shipped POSIX route the installer runs from the same
  tree as the package (`install.sh:41`, `:1741`, `:1876`); they differ only through `--repo`, the
  Windows deploy tool, and direct invocation, which is where the receipt adds information, together
  with transaction identity. An installer process also runs the *package's* store, catalog and
  assembler (`_private_module`), so exposure to a store or catalog change reads the snapshot's
  `store_schema_digest` / `compiler_digest`, not the installer digest. The receipt is written after
  verification and before COMMITTED; the snapshot binds the receipt id before `content_ref` is
  derived, so `compose/instructions_session.py` needs no change (reuse map: keep). "Rejected as
  unbound" is a consumer verdict that makes installer exposure unknown, not a launch refusal. Each
  installation transaction costs one extra 1.6 MB snapshot per (cwd, selection).
  The `installer_digest` is the digest of a **declared** installer source-file set — it must
  include `launch/shell_integration.py`, which executes but never appears in `sys.modules` — hashed
  at import and again at receipt time; a difference refuses the receipt, not the install
  (`installer/raw/c1b-controls.log`). It is not proof of every executed byte (bytecode caches and a
  file replaced and restored between the two hashes are not seen). A transaction begun by one
  installer and recovered by another carries both `installer_digest` and
  `begun_by_installer_digest`, and exposure is judged against both; recovering a transaction begun
  by a pre-receipt installer completes without a bound receipt (`installer/raw/c3-failure.log`,
  `c3b-upgrade-pending.log`).
- **F13 — hooks.** A Codex session-flag hook is `untrusted` and does not run under `codex exec`
  unless `--dangerously-bypass-hook-trust`; a Claude plugin hook runs under `-p` with no trust
  review. Codex's stream and rollout showed no trace of a hook's execution. Claude shows it with
  `--include-hook-events` (`hook_started`, `hook_response` with exit code and outcome), and a
  `disableAllHooks` setting — invisible to the activation module — shows up as the missing start
  (`claude-activation/clean/raw/p1-valid-hook.stdout` against `p1-disabled-b-hook.stdout`). Hook
  reach needs its executor check: on Claude, compare expected with started hook events and read
  the responses; on Codex, an executor-side marker.

### Cells and isolation (§8.1)

- **F14 — Claude walks up from its working directory.** It loads `CLAUDE.md`, `CLAUDE.local.md` and
  `.claude/{CLAUDE.md,rules,skills,agents,commands}` from every ancestor to the filesystem root. A
  cell anywhere under `/Users/kangmin` therefore loaded the owner's `~/.claude/CLAUDE.md`,
  `rules/context7.md`, 5 skills and 7 agents as *Project* sources despite its own HOME and
  CLAUDE_CONFIG_DIR, and they reached subagents too (found independently by three probes). The walk
  differs by surface: instruction files are found across a git root, while ancestor skills and
  agents are not found above one (`claude-runner/raw/x/g-git/meta.json` against `g-nogit/`);
  `--safe-mode` suppresses all of it, which suits the hermetic runner (F2) but not an activated
  cell, whose own instructions must load normally. Activated cells therefore live wholly under
  clean ancestry (measured: `/Users/Shared/agent-bios-probe-cells/`); the static check gains an
  ancestor rule, which fired by name for a planted ancestor file and stayed silent at the clean
  location. `--setting-sources user` (drops the fixture's own project file) and
  `claudeMdExcludes` (skills and agents still leak) are not acceptable mitigations. Codex searches
  only from the git root down and is unaffected.
- **F15 — cells are installed, not cloned.** A copy-on-write clone of an installed cell keeps 35
  references to the original's paths; installing a private release into a fresh root takes about
  0.5 s. Snapshot `content_ref` depends on the path, so it is not comparable across cells.
- **F16 — the operating-system sandbox.** A read-denying macOS profile wraps both hosts, but neither
  host's own sandbox nests inside it (`sandbox_apply: Operation not permitted`), so inner sandboxes
  are off inside the outer one. Some denials are reported by the host (Codex named a denied model
  instructions file; a denied Claude hook reported an execution error), but others are silent — a
  denied Claude import was simply not loaded — so the harness collects the macOS unified log's
  denials by time window (a pid filter misses shell children). Claude needs its working directory
  inside the cell and its install directory allowed.
- **F17 — actors can damage their own configuration.** Under `acceptEdits` an actor edited the
  compiled snapshot outside its working directory (`reconstruction/`; `verify_snapshot` then fails),
  and an in-process import of the release wrote `__pycache__` into it (`claude-activation/`). On the
  re-run a permission rule denying writes there (`--disallowedTools "Edit(//Users/kangmin/**),Write(//Users/kangmin/**)"`)
  refused the same edit and every snapshot still verified (`reconstruction/raw/snapshot-integrity.json`).
  Actor episodes deny writes to the state, release and snapshot roots, so an attempted edit is a
  recorded action and the surface-hash check — which covers the release tree and snapshot — stays a
  pure integrity check; in-process imports set `PYTHONDONTWRITEBYTECODE`.
- **F18 — cells are not network-silent.** Codex contacted its public plugin catalogue and populated
  plugin caches even in credential-free cells (the probe author reports about 335 MB, removed; no
  size measurement was kept); Claude cells fetch `remote-settings.json` and policy limits.

### Headless activation and children (§8.2, §8.3)

- **F19 — activation runs headless.** Claude: the unmodified `launch()` already runs headless with
  `-p` in its argv and stdin closed; the pin's session id is the one the module chose
  (`--session-id`) and confirmed from the transcript. Codex: the adapter replaces only the TTY step
  with `codex exec resume --json`; resume mode carries the `agent-bios session snapshot:
  <content_ref>` marker. On both, the adapter classifies the episode by the failure fields of F5 —
  a pin exists even when the host failed — and records `snapshot["unavailable"]` itself, since the
  session module never reports it.
- **F20 — the child brief on Codex.** The `spawn_agent` message is ciphertext to the harness and
  `codex exec --json` does not emit the spawn. The fixed brief carries an echo instruction and the
  harness compares the child's echo byte for byte; a missing or different echo invalidates the
  episode (a full paraphrase made the child refuse, the safe direction). Claude keeps the pass
  condition as written: the brief is plaintext in the parent's `Agent` tool input.

### Reconstruction (§8.6)

- **F21 — one call, conservative.** The whole library (104 items, 1,553 operative units, 418 kB) was
  reconstructed in one `gpt-6-astra`/xhigh call: 135,796 input tokens plus a 16,372-token warm-up,
  25,966 output, 671 s, about 53% of the context. R kept 1,551 units verbatim and changed only the
  three requirements' carriers. The entanglement risk of §17 appeared: R routed a second guide for
  the route requirement, and R−ROUTE was rejected until the validator received R's requirement-map
  row. Validation splits by kind: code verifies kept, same-route rows (text present byte for byte);
  the model judges changed and moved rows and a sample of kept ones. Owner decision O3.

### Budget and usage (§13.2, §13.3)

- **F22 — usage channels.** Codex: `--json` usage was 32–72% of the frame total in three runs; the
  rollout includes children and compaction but omits the billed warm-up request each thread sends
  (root and every child), and came to about 72–95% of the frames
  (`codex-accounting/raw/{e-child2,e-compact1,ep-e-long-out-big-tool}/reconcile.json`). Warm-ups are
  seen only in the frames and in INFO `codex_otel.log_only` events (which matched the frames 40 of
  40). A transport fallback to HTTPS is announced in the `--json` events but blinds the frames, so
  `frames_seen == 0` with otel completions stays a named `frames_blind` completeness condition.
  Claude: the stream's `message_delta` is exact for main requests (87 of 88 in the final set; the
  exception is the request cut by a budget stop); subagents emit no stream events and their
  transcripts are exact but 0.06–5.8 s late; compaction requests are visible on no host channel
  until the run ends; `result.usage` covers only the last main segment, and `result.modelUsage` is
  the closing aggregate (29 of 30 exact). A residual of `result.modelUsage` over the other channels
  is attributed to compaction only after every other request and failed attempt reconciles —
  otherwise it stays unexplained or unresolved (`claude-accounting/raw/f4-drop-mid-stream/`,
  `f5-drop-before-first-event/`); aggregate agreement alone does not establish completeness.
  Claude's transcript writes one `api-request` record per HTTP attempt, retries included.
- **F23 — the stop.** Freeze, rescan, sweep the tree's process groups, kill, verify by pid and start
  time. The guarantee is "no request is sent after the stop took effect": the request whose sending
  trips the cap is already in flight and is counted, as are requests within the observation latency
  (sub-millisecond for stream triggers; 65–111 ms for Claude transcript triggers, with a request in
  flight in all three measured). Detached daemons escape a tree kill; they are out of scope unless
  the episode runs in a sandbox that enumerates them. Because Claude compaction usage is invisible
  until the run ends, a cap evaluated on visible usage was overrun — one episode reached 72,086
  tokens under a 48,000 cap (`claude-accounting/raw/nl4-compaction/`) — so the stop policy adds an
  estimate at every `compact_boundary` marker and caps compactions per episode. Nested Claude
  subagents run two levels deep at the default limit.
- **F24 — the provisional estimate.** "The class's highest observed request" was exceeded by 16 of
  39 Codex main requests (up to 21%) and by every following Claude main request (50 of 50). Estimate from the
  same agent's previous request plus the new content (tool-result characters / 3), keep a safety
  factor of at least 2 for tool results, calibrate per request kind, and report estimate against
  actual per class.
- **F25 — retries and limits.** Both hosts retry on their own (Codex up to 5 sampling retries, then
  websocket to HTTPS; Claude 10 with doubling delay, visible as `system/api_retry`); neither retries a
  usage-limit error. The circuit breaker keys on structured fields: Codex `usage_limit_reached` 429
  frames, otel `codex.api_request` status 429, `codex.rate_limits.limit_reached`; Claude
  `result.api_error == "usage_limit_reached"` with status 429, and `rate_limit_event` with status
  `rejected`, `resetsAt`, `rateLimitType` (emitted on every run, with `utilization` per window as
  headroom). Real-backend retry and rejection shapes were seen only through local fault injectors.
- **F26 — host-side limits.** Claude's `--max-budget-usd` computes list-price cost under
  subscription login, counts subagents and compaction, and is checked between requests (one stop came
  35% over, cutting a streaming request): a usable secondary bound. `--max-turns` bounds main-thread
  turns per segment only. Codex has neither.
- **F27 — an uncapped episode runs away.** One Codex episode started without a cap looped on
  compaction and `wait_agent` for 41 requests and 547,910 tokens in 150 s; Claude stops a compaction
  loop itself after three. The design's cap on every episode is necessary, not cautious.

### Measured costs for §16

| Call | Input | Output | Wall time |
|---|---|---|---|
| Whole-library R authoring (gpt-6-astra/xhigh) | 135.8k + 16.4k warm-up | 26.0k | 671 s |
| R−i rewrite (gpt-6-astra/xhigh) | 40–52k (16.4k warm-up included) | 0.5–7k | 20–193 s |
| Map and requirement validation shard (claude-opus-5-5/high, hermetic) | 7–29k cache write + about 2k cache read | 0.8–3.5k | 10–32 s |
| One-line hermetic Claude call | about 3.2k | — | — |
| One-line Workflow subagent | about 58k | 19–484 | — |
| Codex warm-up request, per thread (root and each child) | gpt-6-astra about 16.4k; gpt-6-luna about 11.8k root, 11.6k child | — | — |

## 3. Corrections to earlier claims

- **C1 — earlier "hermetic" Codex reviews were not shown to be context-isolated.** On the measured
  version (the wrapper at `af40b03`, codex-cli 0.163.0), a `--profile hermetic` dispatch with `--cd`
  inside a repository loads that repository's AGENTS.md and the owner's HOME skills. The adapter
  log holds 999 hermetic dispatches since 2026-07-19 and records no working directory, so which of
  them were exposed, and under which earlier Codex versions, is not established. The nine review
  rounds of the mechanism design and the two rounds of the prompting-guide re-derivation on
  2026-10-20 were dispatched with `--cd` at a worktree (this session's commands), so they ran with
  that exposure on today's version. They remain provider-different reviews; what else reached them
  beyond their packets was not captured, so their isolation stays unverified. The mechanism
  design's provenance line ("hermetic") is corrected here.
- **C2** — §3.1 named "the hermetic Claude runner" as the Claude route for independent judgments;
  none existed. F2 specifies it.
- **C3** — §8.1 said cell credentials are "linked read-only". Claude's login is bound to the macOS
  keychain for the default configuration directory; cells use the owner's long-lived subscription
  token (`claude setup-token`, stored 2026-10-20 in
  `~/.local/share/agent-bios-workbench/secrets/claude-oauth.env`, mode 600), loaded only into the
  child environment. Codex cells copy `auth.json`.
- **C4** — the §15 reuse-map row for `compose/instructions_session.py` changes from "change" to
  "keep" (F12).

## 4. Owner decisions (2026-10-20)

Each was put to the owner with its alternatives; the owner chose the first option in all four.

- **O1 — Codex observed-model attestation: the trace-frame channel.** A canary call in the rehearsal
  and after every Codex upgrade must see frames; a Codex call whose frames are silent fails closed
  (`MODEL_UNATTESTED`). Not chosen: requested-or-configured attestation with a visible mark; moving
  attested judgments off Codex.
- **O2 — usage accounting: host channels as in F22.** Compaction is aggregate-measured, child usage
  arrives late, the completeness flag stays false until the closing reconciliation, and the stop
  policy adds an estimate per compaction marker and caps compactions per episode (F23). Not chosen:
  a local metering proxy (`ANTHROPIC_BASE_URL` to a forwarder), the only per-request, immediate and
  complete channel, which would see the authorization header and need its own probe.
- **O3 — a conservative R is accepted.** R is an independent author's choice of carriers; each run
  reports R's distance from B (units kept verbatim, rewritten, moved, dropped), so a near-copy is
  visible. Not chosen: requiring R's author to restate every item in its own arrangement.
- **O4 — sessions of unknown independence are not counted.** The negative-space root rule stands;
  components with no unique root or unestablished file provenance do not count toward recurrence,
  and S1 reports their share each run. Not chosen: taking the earliest session of a component as
  its root.

## 5. Not done or unknown

Billing of a request killed in flight (both hosts); a real Codex refusal and a real Codex
`response.incomplete`; real-backend retries and the real rejected usage-limit shape (both hosts,
seen only through local injectors); Codex compaction lineage; Claude Desktop sessions and the
`continued-in` trigger; Claude auto-compaction at its natural threshold (it was forced through
environment overrides); nesting beyond two subagent levels; interactive sessions beyond one
real-TUI comparison; Windows. Small samples: child echo runs and child behavior arms are n=1–2 per
variant; the Codex resume pattern rests on five planted resumes. The raw files of two early
accounting runs that exposed an instrument defect were deleted before the fix was recorded; the
probe states this and counts their 3,140 tokens.

## 6. Cross-check

One pass by `gpt-6-astra`/xhigh through the fixed wrapper (`12b2769`, `--profile hermetic`), working
directory the probe evidence directory, read-only. A model-free rendering of the same dispatch
showed no AGENTS.md message and only the four built-in skills (`xcheck/precheck.*`). The receipt's
result hash equals the retained result (`xcheck/receipt.json`, `xcheck/review.json`). Verdict
`fix_then_use`: of 45 items, 25 supported, 19 partly supported, 1 contradicted (the unknowns list,
which named real Claude refusals and Claude auto-compaction as unknown); 25 findings, 14 major.
None overturned a probe verdict; they corrected overstated passes, stale counts, and missing
qualifications. Every finding was applied after the load-bearing ones were re-checked against the
raw files (the refusals, the git-root walk, the replayed gate). Its finding that 30 files of
`claude-accounting/` failed their manifest was a mid-regeneration state: that probe re-ran and
regenerated its manifest during the check, and all 1,403 entries verify afterwards. The corrected
record was not re-reviewed.

## 7. What the probes used

Codex (`gpt-6-luna`/low unless noted): codex-activation 16 episodes; codex-records 56 requests,
772k tokens (550k cached); codex-runner 20 `codex exec` calls (two requests each); codex-accounting
88 requests, 1,131k tokens (852k cached; over its 800k guideline because of the runaway in F27);
reconstruction 3 `gpt-6-luna`/medium and 4 `gpt-6-astra`/xhigh calls. Claude (`claude-haiku-5-5`/low
unless noted): claude-activation 55 sessions; claude-records about 110 requests; claude-runner 76
calls (5 on claude-opus-5-5); claude-accounting 169 usage-bearing requests, about 764k tokens;
reconstruction 24 claude-opus-5-5/high validator calls and 16 haiku calls (first run and the
clean-location re-run); workflow 4 requests, 231k tokens. Cross-check: one gpt-6-astra/xhigh call.
No usage limit was hit. The probe subagents' own sessions are not counted here.
