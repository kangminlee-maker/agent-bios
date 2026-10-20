---
created_at: 2026-10-20T21:19:00+09:00
head: cc0498f
kind: design
supersedes: null
---

# Session distill: implementation plan (redesign step 3)

This record is the implementation-process plan (staged workflow, stage 2) for
`2026-10-20T1942--9684f05--mechanism-design.md` (below: the design), which stays the authority; its
§2 owner decisions and its contracts are fixed. Nothing here is implemented yet.

**How it was made.** Two planners drafted it independently from one blind packet that carried the
design, the purpose record, the probe record, `AGENTS.md`, and the owner's working principles
(concept economy, LLM/capability boundary, staged workflow, verification discipline, mock/realization
boundary): gpt-6-astra/xhigh through the hermetic Codex profile at `12b2769` (receipted), and
claude-fable-5-1/max. This record takes the Claude draft's structure — its finer work packages,
exact files, and plant table — and carries the Codex draft's distinct findings into it: the
review/decision file conflict, the static-check allowlist, the frozen evaluator, commit
sequencing, the reservation bootstrap, frozen-copy inventory, and its full-scale rehearsal costing.
Where the drafts disagreed, §6 says which reading this plan takes and why. Code facts were read
from `feat/distill-redesign` at `cc0498f` and `fix/hermetic-isolation` at `12b2769`; the synthesizer
re-checked the load-bearing ones (the §9/§10.1 file conflict, `AUXILIARY_MODELS` in
`benchmarks/dispatch.py`, the prompting guides on `feat/prompting-rederive` `5846e4a`).
**Review round 1** (2026-10-20, a fresh hermetic gpt-6-astra/xhigh pass over this record, 38
findings and 17 open items, verdict `fix_then_implement`) found one cause behind most findings: the
plan had restated design contracts in its own words and drifted from them. This revision removes
the restatements (the rule below), applies every finding in the work package it names, and
records in §6.3 the findings whose wording the code corrected. It was then reviewed by six fresh runs of gpt-6-astra/xhigh through the fixed hermetic
Codex profile, each receipted: rounds 1–5 returned "fix then implement" (38, 20, 13, 7 and 6
findings), and the plan was revised after each; round 6 returned "implement from it" with four
minor findings, which this record settles. Between rounds 4 and 6 the owner decided D-1 and D-2 and
amended design §5.4 (`2026-10-21T0026--cc0498f--input-bound-amendment.md`).

**Review round 2** (2026-10-20, the same reviewer kind over the round-1 revision, 20 findings —
13 major, 7 minor — verdict `fix_then_implement`) found the remaining defects localized: four
round-1 fixes had overshot (a blanket rejection of inherited child context, the author-side
success path dropped from RH-1, a textual runner scan, cap enforcement moved only halfway) and
three instructions contradicted the design (A/B packet-hash equality against unique call headers,
a scratch branch read as confinement, §18's window read as elapsed time). This revision applies
all twenty in place (each marked `N#n` where it lands), recomputes §8.2 from one manifest, and
records in §6.4 the readings it settled while applying them.

**Review round 3** (2026-10-20, the same reviewer kind over the round-2 revision, 13 findings — 4
major, 9 minor — verdict `fix_then_implement`) found two instructions still contradicting the
design (a sampled token ratio offered as the §5.4 input bound; a rehearsal plant writing an
owner's file) and eleven localized corrections. This revision applies all thirteen (`N#n` marks
of this round are suffixed `r3`), recomputes §8 from the one manifest, and records in §6.5 the
readings it settled.

**Review round 4 and the owner's decisions** (2026-10-21). Round 4 (7 findings — 2 major, 5
minor — verdict `fix_then_implement`) showed that no pre-send bound over the complete request can
be established from measurements; the owner answered by **amending design §5.4** in the record
`2026-10-21T0026--cc0498f--input-bound-amendment.md` (the driver's part bounded in bytes, the host's part a declared
allowance verified per call), and decided **D-1: option 1** and **D-2: one real core item**. This
revision implements the amendment where the bound is cited (WP-06 done-when 3, WP-03 done-when
5, WP-23 done-when 3, §5, §6.5), marks D-1 and D-2 decided in §6.2, applies the other six
findings (`N#nr4`), and records in §6.6 the readings it settled. Implementation starts once the
final review confirms the plan.

**Review round 5** (2026-10-21, 6 findings — 1 major, 5 minor — verdict `fix_then_implement`): the
major finding was the amendment's own overreach — a blanket 120k stop would have rejected §8.6's
whole-library reconstruction (probe 7: ≈136k input) — and the owner corrected the amendment record
to **view-window calls only**. This revision scopes the plan to it and applies the five local
corrections (`N#nr5`); §6.7 records the readings it settled.

Conventions used throughout:

- **The design's field lists and predicates are the contract; this plan never restates them.**
  Where a work package implements a design contract — claim records (§3.3), evidence records
  (§5.5), census statuses (§5.1), coverage state (§5.2), the model-call acceptance predicates
  (§3.2), the judgment-reuse key (§6.2), the planted-control population (§6.5), the review
  population (§9), approvals and adjudications (§10.1), the confirmation record (§10.3), the
  side-effect journal (§10.5), recovery (§10.6), the exposure predicate (§11), ledger schema 2
  (§12.1), its migration (§12.2), transitions (§12.3) — the plan says "as design §X" and names
  only what it **adds**. Each implementing schema or predicate carries `$comment: "design §X"`,
  and the module's self-test asserts that the implemented required field set (or the predicate's
  branch set) equals §X's list; that expected list is copied exactly once, into the self-test,
  cited to §X, and the cross-provider reviewer of that work package checks the copy against the
  design. A second authority for a contract — a table in this plan, a docstring, a guide
  paragraph — is a defect.
- **shipped** = packed by `package.json` `files[]` and judged by `gates/check-package.sh` (prose scan,
  hygiene, endpoints, `author_only` withholding); **author-side** = under `gates/`, `decisions/`,
  `design/`, `benchmarks/`, `session-distill/`, `.githooks/` (`AUTHOR_SIDE_DIRS` in
  `gates/check-package.sh`) or declared in `AUTHOR_SIDE_FILES` (e.g. `compose/test_*.py`,
  `learn/build-promotions.py`). The direction is fixed: author-side code may import shipped modules,
  never the reverse. `package.json` `files[]` names wrapper **files** individually
  (`wrappers/codex-run.sh`, `wrappers/codex-helm.sh`, `wrappers/claude-run.sh`), not the directory,
  so every new shipped helper needs its own `files[]` entry, its deploy line in `install.sh` (and
  the `SURFACES.md` claim `gates/check-surfaces.py` demands), and a **packed-install test**: `npm
  pack`, install from the tarball into a scratch HOME with the checkout made unreachable, and run
  the helper's route from there.
- **One dispatch path.** Every live model call of the pipeline — producing, independent-judgment,
  authoring, scoring, actor episodes, calibration, development probes — goes through
  `session-distill/runlib/dispatch.py` (WP-02), which allocates the `call_id`, requires a
  reservation and both caps, runs the live monitor and the stop at either cap, consults the
  provider breaker, and hands the result to the gate. The rule is about **executable dispatch
  edges in the new pipeline's closure** (the evaluator closure of WP-19: `distill.py`, `runlib/`,
  the `benchmarks/` modules the driver imports), checked by import tracing and call-site analysis,
  not about textual mentions (N#5): the retained legacy entrypoints (`session-distill/screen-codex.py`
  names `~/.codex/bin/codex-run` until the WP-22 cutover) and the tier experiments
  (`benchmarks/tier/live.py` resolves `/opt/homebrew/bin/codex`) are inventoried as out-of-scope
  executors that the new pipeline must neither import nor call; the legacy entries of that
  inventory are retired at the cutover. The plan's own **review dispatches** (the X reviews of §2)
  are not pipeline calls: they run through the P1 hermetic profile with the launcher's receipt
  (the review bootstrap, §2), outside the supervisor. Development live calls made before WP-18
  lands run under the supervisor's provisional calibration tranche (§6.1 S-15), never outside it.
- Every new Python module carries `--self-test` with positive and negative controls, in the shape
  `gates/control-audit.py` grades (failures appended to a sink it recognises), **and is registered
  by name in that tool's `SUBJECTS` list** — the audit's automatic inventory recognises only
  checker-named files (`CHECKER_NAME`), so an unregistered `runlib/*.py` is not graded, and the
  audit exits 0 whatever it finds; a done-when that says "covered" reads the module's own line in
  the audit output. Every new umbrella leg is a real `if [ -f … ]` line in `gates/check-parity.sh`
  that runs the module's self-test command, so the hook's self-test loop executes it.
- Schema validation uses the repository's existing dependency: `jsonschema` 4.26.0, Draft 2020-12,
  exactly as `learn/check-learning.py` loads it (`Draft202012Validator.check_schema` at load, then
  validation; a missing package is a named failure, never a silent skip), through the managed
  interpreter `launch/provision-venv.sh` provisions (`JSONSCHEMA_PIN`). Stage schemas declare
  `additionalProperties: false`, and `validate.py` enforces that and the supported-keyword set as a
  **schema-policy lint** after `check_schema`, because jsonschema itself accepts unknown keywords
  and open objects (N#3r4). Instance validation stays jsonschema's; no second validator is written
  (review round 1, F32).
- "fails by name" means the failure output carries the named code or the planted path, asserted
  by the control, never by eyeballing.
- Realization of a fixture is declared: **golden** (synthetic artifacts, fault injectors, fake
  hosts), **replay** (a retained real capture from the probes or an earlier live run, with its
  provenance hash), **live** (the real `claude`/`codex` binary), or **smoke** (a live run below the
  contract scale, made during development to exercise machinery; it is never evidence). All run
  through the same production validators. A golden, replay, or smoke check never stands in for a
  live one in the rehearsal's authorization evidence, and the harness refuses a fake binary unless
  the run is declared golden (mock/realization boundary).
- Ports from the probe prototypes under `distill-probes-20261020/` are named in the porting
  commit's message with the source path and its hash, and every difference the design requires is
  listed there; nothing imports a prototype by an absolute path.
- Legacy entrypoints (`session-distill/digest.py`, `batch.py`, `screen-claude.js`,
  `screen-codex.py`, `collect.py`, `consolidate.js`, `bundle.py`, `bundle_final.py`,
  `out/BUNDLE.*`) stay in place and working until WP-22's **atomic cutover**, which deletes them in
  the same commit that replaces the runbook sections naming them (the delivered
  `claude/guides/session-distill-workflow.md` names all seven commands today) and re-emits the
  mirrors. The same commit migrates `design/session-distill/ledger.json` to schema 2 and replaces
  `merge-ledger.py`'s body, because the runbook's documented `merge-ledger.py --window-end` and
  `update-state.py --window-end` invocations must keep working on the data they find until then
  (N#14); "working" is checked by running the documented invocation, never by a file's existence.
  No earlier work package deletes a file the active runbook names or changes what a documented
  invocation does.
- Run directory: `session-distill/out/<run-id>/` (per-run, untracked). Stage records at
  `stages/<stage>/record.json`; every model call at `calls/<call_id>/` holding `packet.md`,
  `schema.json`, `result.json`, `receipt.json`, `usage.json`, `capture/`.

---

## 1. Prerequisites and environment

| # | Prerequisite | How it is checked (and its negative control) |
|---|---|---|
| P1 | **Land `12b2769` on `feat/distill-redesign`** (cherry-pick from `fix/hermetic-isolation`, worktree `/Users/kangmin/.local/share/agent-bios-workbench/hermetic-fix/source`). It carries: `wrappers/codex-run.sh` hermetic profile (`run_env+=(HOME="$root/user-home")`, `-c project_doc_max_bytes=0`, `env … CODEX_HOME=… codex`), the `gates/check_parity.py::codex_run` fixture-home assertions (child HOME empty, CODEX_HOME holds only `auth.json`, flag set `--ignore-user-config --ephemeral project_doc_max_bytes=0`, inherit lacks it), the cli-multi-model-workflow guide in four trees, and decision `D-20261020-7b89dc`. `git merge-base --is-ancestor 12b2769 HEAD` returns **no** on `cc0498f`; `main` is at `af40b03`. | After landing: `python3 gates/check_parity.py --only codex_run` exits 0; `python3 gates/emit-mirrors.py --check` exits 0 (four guide trees); `python3 decisions/record-decision.py --check` exits 0 (content-derived id merges by concatenation). **Control:** run the landed `check_parity.py --only codex_run` against a **throwaway copy of the tracked tree** carrying the `cc0498f` `wrappers/codex-run.sh` (never an in-place swap in the worktree) — it must fail naming the fixture-home assertion, and the unchanged worktree passes. Until P1 lands, no cross-provider review in this plan is receipted as hermetic, and WP-04 cannot start. After P1 (and P6), run the umbrella once and record every failure by name as the baseline; a WP is not complete while a failure it touches is unexplained. |
| P2 | **Host binaries pinned**: Claude Code 2.1.304 (`/Users/kangmin/.local/bin/claude` → `~/.local/share/claude/versions/2.1.304`; 2.1.302/303 also present, so the symlink moves on auto-update), codex-cli 0.163.0 (`/opt/homebrew/bin/codex`). Cells and runners invoke the **versioned path**, never the symlink, with `DISABLE_AUTOUPDATER=1` in the child env. | `claude --version` and `codex --version` equal the pins in `session-distill/seats.json` and in `run.json`; the §14 seven checks (`distill.py preflight`, WP-23) run at rehearsal start and after any version change. **Control:** `preflight` with a pin edited to `2.1.303` fails naming `HOST_VERSION_MISMATCH`. |
| P3 | **Account settings declared**: Claude Max with extra usage **currently on** (measured 2026-10-20) — the owner turns it off before the first dispatching development test, else S0 records that charges are accepted; Codex via ChatGPT login (`~/.codex/auth.json` present; never read by any plan step). | `run.json.account.extra_usage ∈ {off, on-accepted}` with the owner's date is required by `distill.py declare`; `rate_limit_event.utilization` from the first Claude call is logged as headroom. **Control:** `declare` without the field fails `ACCOUNT_UNDECLARED`. The harness cannot read the account setting; this is a declared value, by design (§13.2). |
| P4 | **Credential handling**: token slot `~/.local/share/agent-bios-workbench/secrets/claude-oauth.env` (mode 600, 133 bytes measured by `ls` only). Loaded only into a child process environment by the runner (WP-03), reaching `claude` as `CLAUDE_CODE_OAUTH_TOKEN`; never written, printed, or hashed into any artifact. | `distill.py preflight --secrets`: `test -s`, mode is `600`, value matches the subscription token's documented prefix and length class (the pattern lives in `preflight.py`, not in this record), checked without reading the value into any output, nothing echoed. After every development test and rehearsal session: the token-prefix sweep (`preflight.py --sweep <run-dir> <cell-root>`, a fixed-string search for the prefix) lists **0** files (the BRIEF rule). **Control:** plant a file containing the prefix in a scratch run dir → the sweep names it and exits non-zero. Token validity is proven by WP-03's first live call (one minimal call), not by this check. |
| P5 | **Clean-ancestry cell root**: `/Users/Shared/agent-bios-cells/` (production), mode 700, owner the operator; `/Users/Shared` is `drwxrwxrwt root` (sticky, world-writable), so sibling protection rests on our root's mode and the sandbox profile. The probe root `/Users/Shared/agent-bios-probe-cells/` (700) stays for fixtures. The runner's `hermetic_call.py` rule stands: a cell root under `/Users/kangmin` is refused. | Ported static check (`p2_static_check`, WP-16): no `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.codex/`, `.mcp.json`, or settings file in any ancestor of the root; mode 700. **Control:** a plant at `<root>/plant/CLAUDE.md` with a cell beneath it fails by the planted path (never plant in `/Users/Shared` itself). |
| P6 | **Seats declared where gates can see them** (S-2): `launch/agent-launch.toml` `hosts.claude.models` lacks `claude-sonnet-5-5` and `claude-opus-5-5`; `hosts.codex.models` lacks `gpt-6-luna` (it lists `gpt-6-astra`, `gpt-5.6-sol/terra/luna`); `claude/guides/claude-prompting.md` `targets:` and `gpt-prompting.md` `targets:` do not name them; `session-cost.py` `PRICES` has no 5-5 rows (its rows already carry input, output, cache-read and both cache-write tiers, so only the two rows are added). The re-derivation of both guides for the 5.5 and 6.x generations is committed on `feat/prompting-rederive` (`5846e4a`, not yet on this branch or `main`); landing it here is part of this prerequisite, and the owner decides whether it also goes to `main`. `launch/check-prompting-targets.sh` reads only the launch config's `hosts.*.models` and tier models, so a seat chosen at S0 from observed usage (§8.4) is outside its reach. | `launch/check-prompting-targets.sh` and `python3 gates/check-prompting-sources.py` exit 0 after the models are added to the launch config and the guides' `targets:` (re-derived, `derived_at` ≥ `pinned_at`). **Control:** add a model to `hosts.*.models` without a `targets:` entry → the targets gate fails naming it. **Runtime half (design §8.4):** `distill.py declare` runs the same coverage check over every seat in `run.json` — stage seats and the four actor strata, observed or fallback — against the guides' `targets:`, by calling the gate's own target reader, and refuses the declaration on a seat no guide covers (`SEAT_UNCOVERED`); control: a `run.json` whose Codex-subagent stratum names an uncovered model is refused by name. |
| P7 | **Tools present**: `zstd` 1.5.7 CLI at `/opt/homebrew/bin/zstd` (no Python `zstandard` in `/usr/bin/python3` 3.14.7 or `/opt/homebrew/bin/python3`); `/usr/bin/sandbox-exec`; `/usr/bin/log` (the unified-log executable — in this zsh tool a bare `log` resolves to zsh's builtin, so every call names the absolute path); Python ≥ 3.11 (`tomllib`); `jsonschema` 4.26.0 in the managed interpreter. Each recorded in `DEPENDENCIES.md` with the verified version. | `distill.py preflight --tools` resolves each by the absolute path declared in `run.json.sources`/`seats.json` and checks its version string. **Control:** a declared `zstd` path that does not exist (`/nonexistent/zstd` in a scratch `run.json`) fails naming `zstd` — a `PATH` manipulation is not a control here, since the tools are resolved by absolute path. |
| P8 | **Worktrees and hooks**: the integration checkout is `/Users/kangmin/.local/share/agent-bios-workbench/distill-redesign/source` (branch `feat/distill-redesign`), never the shared `/Users/kangmin/Documents/agent-bios-personal` tree (several sessions share it; `main` lags). **Each implementer works in their own `git worktree`** added from that checkout (the hook refuses a commit whose index moved while the gates ran, and two lanes in one worktree share one index); integration into the integration checkout is serialized — one lane rebases and commits at a time. `git config core.hooksPath .githooks` in every worktree; the umbrella costs minutes (AGENTS.md §3) and runs on an index snapshot. | `git config --get core.hooksPath` prints `.githooks` in every worktree; `git status --porcelain` empty at each WP start; `git worktree list` shows one worktree per active lane. **Control:** a commit attempted while another process stages a file in the same worktree is refused by the hook (the AGENTS.md §3 property); the per-lane worktrees are what keeps that from happening in normal work. |
| P9 | **Prompting-principles injection for external drafts/reviews**: every packet dispatched to a hermetic reviewer carries the concept-economy, LLM/capability-boundary, staged-workflow, verification-discipline, and mock-boundary summaries (the reviewer loads no instructions). | A packet linter in WP-02 (`packet.check`) requires the principles block hash; **control:** a packet without it is refused before dispatch. |

Removed in review round 1: the former P9 ("benchmark guard re-approval") and S-16. `benchmarks/run.py`
`GUARDS_APPROVED = "2026-08-26"` records the owner's approval of the per-item `guards`
classifications (`manifest.py` `GUARDS = irreversible | authority | security | none`) and nothing
compares an isolation-guard hash against it; the plan had invented a refusal that does not exist.
Harness changes are gated by this plan's own isolation controls (WP-16, WP-17) and owner review.

---

## 2. Work packages

Size legend: S ≈ ≤150 lines, one implementer session; M ≈ 150–500 lines, 1–2 sessions; L ≈
500–1,200 lines, 2–4 sessions; XL ≈ >1,200 lines or ≥4 sessions. A session is one context window of
one implementing agent plus its review. Reviewer kinds: **X** = cross-provider hermetic reviewer
(gpt-6-astra/xhigh through `codex-run.sh --profile hermetic`, receipted; requires P1); **W** =
same-provider fresh-context reviewer (claude-sonnet-5-5/xhigh in a fresh process, receipted);
**O** = owner. Per the independence ladder, every contract-bearing WP gets X; mechanical ports get
W; anything that changes a decision, a shipped surface, or the preset gets O in addition. Every X
packet includes the design sections the WP implements, and the reviewer is asked to compare the
implemented schemas with those sections' field lists (the contract-fidelity rule above).

**Review bootstrap (N#6).** The gate and the supervisor cannot review their own creation: WP-01's
and WP-02's X reviews, and every X review until WP-04 lands, are dispatched through the fixed
`codex-run.sh --profile hermetic` of P1 with `REVIEW_RECEIPT_DIR` set, which gives a fresh
`CODEX_HOME`, an empty HOME and no project documents (the isolation a review needs) and a
`ReviewReceipt/v1` per review. From WP-04 on, X reviews run through the capture mode. This is the
one place a model call in this plan runs outside `runlib/dispatch.py`; it is a review of the work,
never evidence the pipeline produces. Review dependencies are the third edge kind of §3.

### WP-01 Driver skeleton, run declaration, stage records, record schemas (S0, O0)

- **Goal.** `session-distill/distill.py` with one subcommand per stage (S0–S12 names fixed in §4),
  the run directory layout, `run.json` and `--amend`, stage records that pin the declaration they
  read, the record schemas every later stage shares (claim, evidence, expected observation), the
  set-accounting primitive, and the failure posture (quarantine with dependants in production;
  stop by name in development/rehearsal).
- **Design.** §3, §3.3 (claim records), §5.5 (evidence records), §7.3 (expected observation), §4,
  §4.1, §13.2 (declared budget fields), §13.4 (record shape).
- **Files.** author-side: `session-distill/distill.py` (new; entry point), `session-distill/runlib/`
  (new package: `declare.py`, `records.py`, `claims.py`, `stagelock.py`, `validate.py` — the
  `jsonschema` wrapper of the conventions), `session-distill/schemas/{claim,evidence,expected_observation}.schema.json`,
  `.gitignore` (add `session-distill/out/*/` — per-run directories hold redacted transcript views and
  must never be tracked), `gates/control-audit.py` `SUBJECTS` (register the new modules). No
  deletions (atomic cutover, WP-22).
- **Dependencies.** P8. None on other WPs. WP-08 and WP-21 consume the record schemas defined here
  (an interface dependency, not a live one — F34).
- **Artifacts and interfaces.**
  - `run.json` fields: `question`, `kind ∈ {periodic, targeted}`, `window {start, end, tz}` (half-open),
    `sources[]` (paths, with the absolute `zstd` path), `checks{}` with thresholds (§13), `budget{per_stage{},
    per_episode{tokens, compactions, max_budget_usd, max_turns}, reserve}`, `seats{}` (stage → `provider:model/effort`),
    `actor_seats[]` with provenance (§8.4), `config_manifest_B`, `starting_hashes{ledger, coverage, layers{}}`,
    `account{extra_usage, declared_on}`, `hosts{claude, codex}` versions, `declaration_seq` (0) —
    these are the §4.1 contents, with the plan adding `declaration_seq`, `host_allowance{}` (per seat:
    the measured allowance in tokens, host version, flag-set hash — the declaration the amendment
    record `2026-10-21T0026--cc0498f--input-bound-amendment.md` requires; N#0r4) and `destinations{}` — the
    declared root per destination class (checkout, install roots, personal layers, launcher and
    shell integration, runtime state, nudge, recovery) that every writer of S11 and S12 must
    resolve into (WP-21 done-when 14; filled with fixture roots by the rehearsal, WP-23 done-when
    7; N#4).
  - `amendments.jsonl`: `{seq, at, reason, scope[], invalidates[], diff}`; `distill.py declare --amend --reason …`.
    `scope[]` names the stages the amendment licenses to read it; `invalidates[]` names the stages
    whose results it makes stale (an amendment that changes `checks{}` after S3 invalidates S3 and
    everything downstream).
  - `stages/<stage>/record.json`: `{stage, run_json_sha256, declaration_seq, started, ended, status,
    inputs[{artifact, sha256, producer_stage, producer_seq}], outputs[], calls[], usage{measured,
    provisional, unresolved, complete}}`. A stage refuses to start when any input is partial, stale,
    or invalid (`INPUT_PARTIAL`, `INPUT_STALE`, `INPUT_INVALID`) except the recovery close.
  - Claim record **as design §3.3**; evidence record **as design §5.5**; expected observation **as
    design §7.3** (occasion criteria, exposure rule, expected behavior, retrieval terms, expiry,
    counter and threshold where a counter can resolve it). The plan adds nothing to these three.
    A stage that revises a claim writes a new claim referencing the old one (§3.3); records are
    append-only.
  - Set accounting helper: `expect_set(ids) / observe_set(ids) → SET_MISMATCH` listing missing and extra
    ids; the §3.2 item-5 categories (retained, merged with explicit membership, rejected with reason,
    quarantined) are the only accepted outcomes.
  - `distill.py close --recovery` is reserved here and implemented in WP-21.
- **Done when (each with its control).**
  1. `python3 session-distill/distill.py declare --self-test` exits 0 with ≥ 12 controls listed by name. Control: the self-test's own positive control (a valid declaration) is run first; removing one required field (`account`) fails `ACCOUNT_UNDECLARED`; a seat no prompting guide covers fails `SEAT_UNCOVERED` (P6).
  2. Declaration order (§4.1; F38): `records.check_declaration_order` accepts a consumer whose `declaration_seq` **equals** its producer's, or where an amendment with `seq` in `(producer_seq, consumer_seq]` lists the consuming stage in `scope[]` and does not list the producer in `invalidates[]`. Three independent controls: equal → pass; legitimately amended (scope covers, producer not invalidated) → pass; silently advanced (no amendment between) → `DECLARATION_DRIFT` naming the stage (O0 plant); amendment present but the producer is in `invalidates[]` → `INPUT_STALE` naming the producer.
  3. Criteria (`checks{}`) changed after S3 without an amendment: `declare --set checks.…` after a S3 record exists is refused with `AMEND_REQUIRED`. Control: the same change through `--amend` is accepted, logged, and marks S3 in `invalidates[]`.
  4. Set accounting: `observe_set` missing one id or carrying an extra id fails `SET_MISMATCH` naming both; equal sets pass.
  5. Contract fidelity: the `required` sets of `claim.schema.json`, `evidence.schema.json`, and `expected_observation.schema.json` equal the field lists of §3.3, §5.5, and §7.3 (asserted in `claims.py --self-test` against the lists copied there and cited); control: add one field to a schema's `required` → the self-test names the schema and the section. The schemas are loaded through `validate.py`: `Draft202012Validator.check_schema` first, then the project's **schema-policy lint** (every object schema closed with `additionalProperties: false`; keywords from a declared supported set) — jsonschema accepts unknown keywords and open objects as valid under its own policy, so the lint is a separate, explicit check (N#3r4); controls: an actually invalid schema (`"required": "x"`, not an array) is refused by `check_schema` with `SchemaError`; a schema with an unknown keyword and one without `additionalProperties: false` are each refused by the lint naming the keyword or the open object. Field presence is this check; the **preservation** of one revision's fact, interpretation, uncertainty and quotation through render and ledger is WP-21 done-when 13 (N#13).
  6. `git check-ignore session-distill/out/r1/x` matches; `gates/check-lexicon.py` (after `git add -N` of the new files) and `gates/check-package.sh` exit 0 (concept home: all new paths under `session-distill/`); `gates/control-audit.py` output carries a line for each registered module.
- **Verification point.** Self-test plus a golden end-to-end: `declare` → a stub stage → `--amend` → stub → `check_declaration_order` on real files under a scratch run dir.
- **Review gate.** X on the record schemas and the declaration-order predicate (they are the contracts every stage keeps; the reviewer compares the schemas with §3.3, §5.5, §7.3); W on the CLI.
- **Size.** M (≈450 lines).
- **Main risk.** Over-general schema. Mitigation: fields appear only when a later WP consumes them (the inert-field rule); the self-test lists each field's consumer.

### WP-02 Model-call gate and dispatch supervisor (§3.2, §13.2 reservations and breaker, §13.3 per-call usage)

- **Goal.** One code path that every live model call goes through: the **dispatch supervisor**
  (`call_id` allocation; reservation of the episode's calibrated cost against the stage budget;
  both caps on every agent-backed dispatch; the **live monitor** over the stream events and
  transcript records of every call — main, child, compaction markers — with the compaction
  estimate per marker; the **stop** at either cap — freeze the process tree, rescan it, sweep its
  process groups, kill, verify by pid and start time — recorded `budget_stopped`; the provider
  circuit breaker; per-call usage capture in the three states) and the **gate** (completion and
  binding, receipt, seat attestation by role, schema, cross-record integrity, set accounting, the
  corrective retry). It is the only path that turns a call directory into an accepted result;
  stages read `result.json` only through `gate.accepted(call_dir)`. Review round 1 (F09, S-15)
  moved the supervisor here from WP-18 so that every live call from WP-03 on — including
  development probes and calibration — is already reserved, capped, and breaker-protected; review
  round 2 (N#0) moved the monitor and the stop here too, so a non-actor call is stopped by the
  same mechanism as an actor episode.
- **Design.** §3.2 (all five steps and the control list, verbatim), §13.2 (every agent-backed
  dispatch is an episode; reservation; both caps; breaker signals; no retry against a live limit),
  §13.3 (per-call usage states), §6.5 (the gate controls as planted controls), §8.4 (seat
  coverage), P9.
- **Files.** author-side: `session-distill/runlib/gate.py` (new; ports `claude-runner/proto/accept.py`,
  `codex-runner/proto/accept.py`, `context_evidence.py` logic), `session-distill/runlib/dispatch.py`
  (new; the supervisor — the only module in the closure that dispatches a runner or host binary),
  `session-distill/runlib/monitor.py` (new; the live monitor — ports `claude-accounting/proto/acct.py`'s
  Ledger with its 0.25 s `FLUSH_WINDOW_S` for transcript records and `codex-accounting/proto/acct.py`'s
  `SentDecoder`), `session-distill/runlib/stop.py` (new; ports `ep.py` `stop_tree`),
  `session-distill/runlib/breaker.py` (new; moved from WP-18), `session-distill/runlib/receipts.py`
  (reads `ReviewReceipt/v1` as `launch/agent-launch.py::emit_receipt_command` writes it:
  `{schema, method_id, dispatch_id, packet_sha256, result_sha256, provider, model, effort,
  exit_status, evidence{}}`), `session-distill/runlib/packet.py` (packet + schema builder and
  linter), `session-distill/runlib/usage.py` (per-call usage states; the §13.3 estimate rule),
  `session-distill/seats.json` (new; pinned seats per stage, host versions, flag-set hashes, the
  **declared auxiliary roles per host version** — S-7 — and the **host allowance** measured per host
  version and flag set in preflight, which `run.json.host_allowance{}` declares per run (the
  amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`; N#0r4)), `gates/control-audit.py` `SUBJECTS`. No
  shipped file changes: `--emit-receipt … --evidence KEY=VALUE` already exists and `parse_seat`
  already defines `provider:model/effort`.
- **Dependencies.** WP-01. Live attestation inputs come from WP-03 (Claude) and WP-04 (Codex); the
  gate is developed against the probes' recorded captures (replay) first.
- **Artifacts and interfaces.**
  - `dispatch.call(stage, seat, packet, schema, *, reservation, caps, view_window) → call_dir`: refuses
    without a reservation (`RESERVATION_MISSING`), without both caps (`CAP_MISSING`), while the
    provider's breaker is open (`PROVIDER_DEFERRED`, the item recorded `deferred`), or on a packet
    the linter rejects; writes `calls/<call_id>/` and the receipt through the runner; the usage
    record is captured before any temporary home is deleted (§13.3). `view_window` marks the calls
    the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md` governs — S3 reading and its expansion
    windows — and only those: after such a call returns, its observed input is compared with 120k
    and an excess is `INPUT_BOUND_EXCEEDED` (a host change, the run stops); a call without a view
    window — R authoring (§8.6, ≈136k input measured in probe 7), judging, scoring, actor episodes —
    keeps its own section's contract and is bounded only by its seat's context capacity (N#0r5).
    **Reservation allocation is atomic** (N#3r5): check-and-reserve runs in one critical section
    under the supervisor's lock, so two concurrent requests can never both be admitted against one
    remaining balance.
  - **Packet identity (N#1).** A dispatched packet = the per-call **envelope** (the §3.2 header with
    the `call_id`, the stage and seat lines, the principles block) + the **judgment payload** (the
    §6.2 contents for a judge call; the view and schema for a read call). `packet_sha256` in the
    receipt is the hash of the complete dispatched packet and is unique per call; the plan adds
    `payload_sha256` as an evidence key — the hash of the payload alone — which is what two calls
    of one judgment share. The §6.2 reuse key is computed over the payload fields plus seat and
    prompt/schema versions, never over the envelope.
  - **Live monitor and stop (N#0).** During every call the supervisor evaluates both caps at every
    stream event and every transcript record (§13.2), counts a provisional estimate at each
    `compact_boundary` marker, and at either cap freezes, rescans, sweeps and kills the process
    tree, verifying by pid and start time; the guarantee is §13.2's — no request is sent after the
    stop takes effect — and the request in flight is counted as provisional.
  - `gate.accept(call_dir) → Verdict{ok, codes[], seat_sent, seat_observed, effort_provenance, usage,
    context_evidence}`. `codes[]` is the **complete** failure set: every predicate is evaluated and
    none short-circuits, so a control asserts the presence of its named code beside whatever else
    the same capture fails (N#8). Acceptance **as design §3.2, steps 1–5, host-specific** (F07) — in particular:
    Claude completion is read from `is_error`, `terminal_reason` **equal to `completed`**, every
    assistant `stop_reason` within `end_turn`/`stop_sequence`/`tool_use`, `safety_stops` zero, and a
    present `structured_output` **where a schema was given**; the three Claude host-level bindings
    (recorded request text equals the packet; the request's StructuredOutput tool definition
    equals the schema; `structured_output` equals the last recorded tool call) are asserted on the
    recorded bytes, not on copied hashes; Codex: an aborted stream (`response.created` without
    `response.completed`) is failure; a stale receipt (another `call_id`), an inherited profile, a
    working directory outside the declared manifest, or effective-context evidence naming an
    undeclared instruction, skill, agent, hook or memory source is rejected. Codes (plan names
    except `MODEL_UNATTESTED` and `frames_blind`, which the design names): `COMPLETION_INCOMPLETE`,
    `BINDING_MISMATCH`, `MODEL_UNATTESTED`, `frames_blind`, `SCHEMA_INVALID`, `RECORD_INTEGRITY`,
    `SET_MISMATCH`, `CONTEXT_UNDECLARED`, `CONTEXT_HASH_MISMATCH`, `RECEIPT_STALE`, `RECEIPT_MISSING`,
    `RECEIPT_KEY_MISSING`, `PROFILE_INHERITED`, `CWD_OUTSIDE_MANIFEST`, `RETRY_EXHAUSTED`.
  - Required receipt `evidence` keys: the §3.2 list (`call_id`, packet/result/schema hashes, seat sent
    and observed, profile and flag-set hash, working directory, context-manifest and
    observed-context hashes, usage state and totals, capture hash, session or thread id); each must
    **equal** what the contract requires, which the gate recomputes from the call directory rather
    than trusting the receipt's copy. `method_id` = `distill/<stage>/<call_id>`.
  - **Seat attestation by role (S-7, F08).** Every main response and every child response must be on
    its exact declared seat: Claude — each main and subagent request's `params.model` and each
    assistant `message.model` equal the seat declared for that role; Codex — each joined
    `response.model` equals the seat declared for that response's role (main, child, compaction,
    warm-up), joined and failed as §3.2 describes (`frames_blind` as §13.3). Auxiliary models are
    accepted **only as separately declared auxiliary roles** in `seats.json` (measured per host
    version by `preflight`, with the request kind they serve), and only in the aggregate: every
    `result.modelUsage` key must be the main seat, a declared child seat, or a declared auxiliary
    role, and the compaction residual must sit under those keys (§3.2's aggregate attestation).
    `benchmarks/dispatch.py` `AUXILIARY_MODELS` is replaced by this declaration (WP-17).
  - Effort: recorded as requested; `effort_provenance ∈ {unverified, host-reported}` —
    `host-reported` only when Codex frames carry `reasoning.effort` equal to the request; Claude is
    always `unverified` (§3.2; S-6).
  - Corrective retry **as §3.2**: a failing output is rejected, retried once with the validation
    message, then recorded as failed with every attempt kept; the driver never extracts JSON from
    prose, repairs values, or treats a failed call as empty; a usage-limit signal is never retried
    (the breaker).
  - Supervisor accounting: reservation = the 95th percentile of measured cost for the call's class
    (stage, seat, case type) from the rehearsal, updated per run; **bootstrap (S-15)**: a class with
    no measured sample runs a declared calibration tranche at concurrency one, reserving a seed
    taken from the nearest probe measurement times the §13.3 safety factor, its records marked
    `calibration: provisional`; broad dispatch of a class whose estimate is still provisional is
    refused (`CALIBRATION_PROVISIONAL`). Breaker **as §13.2**: Claude `result.api_error ==
    "usage_limit_reached"` with status 429 and `terminal_reason: api_error`, a `rate_limit_event`
    with `status: rejected` (`resetsAt`, `rateLimitType`); Codex a `usage_limit_reached` 429 error
    frame, an otel `codex.api_request` with status 429, or `codex.rate_limits.limit_reached`; an
    unrecognised provider error also stops that provider and is reported; message text is never
    matched; `breaker.state.json` per provider `{open, since, signal, resets_at, deferred_items[]}`.
- **Done when.**
  1. `gate.py --self-test` ≥ 40 controls over recorded captures from `distill-probes-20261020/` (replay, declared) mutated one field at a time, each failing by its code with the unmutated capture passing, and **every §3.2 control present with its realization**: truncated output (Claude live through a small `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, WP-03; Codex a real aborted stream, live in WP-04, and a planted `response.incomplete` frame, golden); refusal (the known Claude `stop_reason: refusal` shape as replay; planted refusal frames for both runners); nonzero exit (live); stale receipt (golden); mismatched result hash (golden); inherited profile (live: `--profile inherit` → `PROFILE_INHERITED`); contaminated working directory — an undeclared working-directory instruction file, an ancestor file, a configuration-home instruction file, a skill, and a memory file, each returning a valid canary-free answer (live, WP-03 done-when 3: under the **loading** flag set — the `inherit` profile with the cell homes — so each source demonstrably loads and `CONTEXT_UNDECLARED` is in the complete failure set; the same plants under the production hermetic profile are the isolation positives — N#8); unattested model (Codex frames silent, live in WP-04; Claude undeclared `modelUsage` key, golden); `terminal_reason` present but not `completed` → `COMPLETION_INCOMPLETE`; a schema-less actor call with no `structured_output` → accepted (the predicate is conditional); the three Claude bindings each broken one at a time → `BINDING_MISMATCH`; one child response without a frame while root and warm-up have frames → `MODEL_UNATTESTED` with usage still recorded; otel completion without a joined frame → `frames_blind`.
  2. Role attestation (S-7): every main request on a declared auxiliary model (the all-auxiliary main response) → `MODEL_UNATTESTED`; main on the seat with the auxiliary role's usage present in `modelUsage` → accepted (the mixed valid counterpart); a child request on the main seat where the stratum declares a different child seat → `MODEL_UNATTESTED`; an undeclared key → `MODEL_UNATTESTED`. Live counterparts come from WP-17/WP-18's episodes (F-O10-14b, F-O10-16).
  3. Effective-context evidence: a Claude capture whose transcript shows an appended system prompt whose hash is not in the declared list → `CONTEXT_UNDECLARED`; declared and matching → accepted; declared but hash differs → `CONTEXT_HASH_MISMATCH` (O4 plants).
  4. Corrective retry: a schema-invalid first result followed by a valid second → accepted with both attempts kept; two invalid → `RETRY_EXHAUSTED` with both kept; a prose-wrapped JSON result is `SCHEMA_INVALID`, never parsed (control: the brace-extraction path of `benchmarks/absence.py` is shown to accept what the gate refuses — this is the F22 boundary).
  5. Supervisor: a call without a reservation or without both caps is refused by name **on a non-actor call** (a judge call); a breaker signal of each §13.2 kind (fault injector, golden) opens that provider, records outstanding work per item as `deferred`, makes no retry, leaves the other provider dispatching, and resumes after `resets_at`; an unrecognised error opens and reports; message-text matching is proven absent (an error whose text says "usage limit" with no structured field is treated as unrecognised); a provisional class refused broad dispatch; a stage budget below one reservation → `not_done`, nothing dispatched; a budget amendment recorded before spend; **reservation race** (N#3r5, deterministic through a barrier and a fake clock): two simultaneous requests, each affordable alone and unaffordable together (balance = 1.5 reservations) → exactly one admitted, the other refused `BUDGET_EXHAUSTED`, and the remaining balance equals the budget minus one reservation (control: the check-then-reserve variant admits both, asserted to fail); **window scope** (N#0r5): probe 7's retained R-authoring capture (≈136k input) through the dispatcher with `view_window=false` → accepted, no `INPUT_BOUND_EXCEEDED`; the same capture with `view_window=true` → `INPUT_BOUND_EXCEEDED`. **Both caps stop a non-actor call** (N#0): a judge call with a token cap set below its first request's size is stopped mid-stream, its tree killed and verified by pid and start time, recorded `budget_stopped` with provisional usage (live, after WP-03); a judge call whose golden stream carries planted `compact_boundary` markers past the compaction cap is stopped (golden); the §13.2 guarantee ("no request is sent after the stop takes effect") is checked on **outgoing** evidence, not on response starts (N#9r3): no Codex client (sent) frame and no Claude transcript `api-request` record whose send instant is after the **verified freeze instant** — every pid of the tree in stopped state before the kill; the freeze verification is the boundary, not the stop decision — and the check keeps `uncertain` where a host record cannot establish sending (an attempt record written late, inside the measured observation latency, is reported as uncertain, never counted clean; the request whose send trips the cap is counted as provisional). Control: a fault-injected post-boundary send that produces no response start → `STOP_BOUNDARY_VIOLATED` by request id, and the `message_start`-only reading is shown to miss it.
  6. Dispatch edges (N#5): `dispatch.py --self-test` traces the import closure of `session-distill/distill.py` and `runlib/` (plus the `benchmarks/` modules the driver imports) and inspects every `subprocess`/`os.exec*`/`os.system` call site by AST; a site that resolves to a runner (`claude-run`, `codex-run`), a host binary, or a pinned binary path outside `dispatch.py` fails by file and line (controls: a planted direct dispatch in a closure module is named; a planted `import` of `screen-codex` into the driver is named). The out-of-scope executor inventory — `session-distill/screen-codex.py` (legacy, retired at the WP-22 cutover) and `benchmarks/tier/live.py` (tier experiments, outside the redesign) — is data in `dispatch.py` with each entry's reason and retirement condition, and the self-test asserts the closure imports none of them. Textual mentions outside the closure are not failures.
  7. Packet linter: a packet lacking the principles block (P9) or the schema reference is refused before dispatch; a conforming packet passes.
  8. Contract fidelity: the gate's predicate branch set equals §3.2's list (self-test), and `usage.py`'s states equal §13.3's three; `gates/control-audit.py` output carries covered lines for `gate.py`, `dispatch.py`, `breaker.py`, `usage.py`.
- **Verification point.** Replay self-test; then the first live calls of WP-03/WP-04 pass the gate unchanged (a live-path green through the real dispatch).
- **Review gate.** X — the gate is what makes every other green trustworthy; the reviewer gets the probe captures, §3.2, §13.2–13.3, and the implemented predicates, and is asked for the branch of §3.2 the code does not implement.
- **Size.** XL (≈1,700 lines incl. controls; the supervisor, monitor and stop live here).
- **Main risk.** A control that passes because the mutation hit a field the gate never reads (vacuous mutation). Mitigation: `mutation_audit.py` (probe prototype) ported — each mutation must change the verdict.

### WP-03 Hermetic Claude profile for `claude-run` (shipped adapter) + parity leg

- **Goal.** A shipped adapter profile that runs one Claude call in a per-call cell under a clean
  root with a fresh `HOME` and `CLAUDE_CONFIG_DIR`, the token in the child environment only, the
  measured flag set, `--json-schema` output, session persistence on, a per-stage output-token cap,
  declared appended instructions hash-pinned, an optional tool-enabled producing profile confined
  to a manifest directory (N#9), transcript-based effective-context evidence, and receipt evidence keys through
  `agent-launch --emit-receipt --evidence`.
- **Design.** §3.1 (producing / independent-judgment / authoring calls), §3.2, §8.1 (cell rules),
  §13.3 (Claude channels), D-20261020-bcba5e (no Workflow subagents).
- **Files.** shipped: `wrappers/claude-run.sh` (change: a `--profile inherit|hermetic` vocabulary
  like `codex-run.sh`'s; `inherit` is today's behaviour byte-for-byte in argv, proven by the existing
  `claude_run` leg; settled S-1, §6), `wrappers/claude_hermetic_evidence.py` (new; transcript →
  effective-context rendering + hash; ports `claude-runner/proto/ctxrec.py`; **its own `package.json`
  `files[]` entry**, resolved by the adapter relative to its own resolved path), `install.sh` (a
  `deploy_file` line for the helper beside line 821's `claude-run`, and its `verify_present` line —
  the compatibility route copies the adapter into `$CLAUDE_DIR/bin`, so the helper must travel with
  it), `SURFACES.md` (claim the new deploy source — `gates/check-surfaces.py` fails an unclaimed
  `deploy_file`), `DEPENDENCIES.md` (profile row and the `bash -n` line at 282),
  `docs/advanced-launch.md` and `claude/guides/cli-multi-model-workflow.md` + `ko/` + mirrors (one
  paragraph: `claude-run`'s hermetic profile exists and what it denies). author-side:
  `gates/check_parity.py::claude_run` extended with hermetic-profile assertions (modelled on the
  existing leg and the landed `codex_run` fixture-home assertions), `ontology/emit-map.py` re-run
  (any `install.sh` edit shifts the `verify_*` line numbers the map embeds — AGENTS.md trap).
- **Dependencies.** WP-02 (dispatch and gate consume its output), P2, P4, P5. P1 for its X review.
- **Artifacts and interfaces.**
  - `claude-run --profile hermetic --model M --effort E --cell-root R --call-id ID [--use judge|producing|authoring]
    [--schema FILE] [--append-system-prompt-file F --declared-sha256 H]… [--tools "Read" --manifest DIR]
    [--max-output-tokens N] [--cd DIR] [-- extra claude args]`; packet on stdin, final JSON on stdout,
    exit status mirrored; `REVIEW_RECEIPT_DIR` and `REVIEW_CAPTURE_DIR` honoured as `codex-run` does.
  - Flag set (measured, probe 4): `claude -p --output-format stream-json --verbose
    --include-partial-messages --safe-mode --setting-sources "" --strict-mcp-config
    --disable-slash-commands --tools ""` (judge profile) or, for the producing profile, `--tools "Read"
    --allowedTools "Read(//<manifest>/**)" --permission-mode default` (the tool boundary below),
    `--json-schema`,
    `--session-id <uuid>`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=N`, `DISABLE_AUTOUPDATER=1`; `--bare` is not
    used (probe: unusable). Cell: `<root>/<call_id>/{home,config,cwd}`; the transcript under
    `config/projects/` is copied into `capture/` before the cell is deleted.
  - Receipt: `agent-launch --emit-receipt distill/<stage>/<id> anthropic:<M>/<E> <status> <packet> <result>
    --evidence …` with the WP-02 key set; `seat_observed` per role from `params.model` and
    `message.model`; `effort_provenance: unverified`.
  - **Tool boundary of the producing profile (N#9).** The profile grants exactly one tool and
    declares how it is mediated: `Read`, through the path-scoped allow rule `Read(//<manifest>/**)`;
    under `-p` a tool request no allow rule covers is refused by the host without a prompt, so a
    read outside the manifest is denied before any content returns, and the denial is a `tool_result`
    error in the transcript, copied to `capture/actions.jsonl`. `Grep`, `Glob` and `Bash` are not
    granted: the host does not path-scope them, so search is code's job before dispatch (the packet
    carries WP-06's search results) and a request for any of them is refused as an ungranted tool.
    Inside a harness cell (WP-16 on) the cell's `sandbox-exec` profile is a second, kernel-level
    boundary; the shipped profile's guarantee rests on the host's rule evaluation, which
    done-when 4 measures live rather than assumes.
- **Done when.**
  1. `python3 gates/check_parity.py --only claude_run` (extended with hermetic-profile assertions) exits 0 using a fake `claude` (golden, as the `claude_run` leg does): asserts child `HOME` is the cell home and empty, `CLAUDE_CONFIG_DIR` is the cell config, the flag set hash equals the one in `seats.json`, the token reaches the child env and appears in **no** argv, no file, and no log (control: the fake dumps its env and argv; a `grep` for the token value across the cell and capture finds only the env dump the fake wrote on purpose, which the leg then deletes), `--max-output-tokens` is exported, receipt seat equals the seat the fake ran on with and without `--` overrides (the `claude_run` control pattern), a missing `--cd` root is refused, exit status mirrored, and the helper is resolved relative to the adapter (control: the helper removed from beside the adapter → the adapter fails naming it, never falls back to the checkout).
  2. Declared instructions: with `--append-system-prompt-file F --declared-sha256 H` the evidence rendering records H and the gate accepts; with the file edited after declaration → `CONTEXT_HASH_MISMATCH`; with an undeclared `--append-system-prompt` passed after `--` → `CONTEXT_UNDECLARED` (O4 plants, golden here, live in WP-23).
  3. Contamination, two halves per source (N#8): **isolation positives** — each of the five §3.2 sources (a working-directory instruction file, an ancestor file, a configuration-home instruction file, a skill, a memory file) planted under the hermetic profile is **not** loaded: the rendering records nothing and the gate accepts (the profile's flags remove these sources — `claude-runner/RESULTS.md` §2.2 — so this half proves isolation, not detection). **Detection controls** — the same five plants run live under a **loading** flag set: the adapter's `inherit` profile with the cell's `HOME` and `CLAUDE_CONFIG_DIR` exported by the harness and the token in the child environment as P4 allows, which loads working-directory, ancestor, configuration-home, skill and memory sources as the probe's non-isolating controls did, through the same evidence renderer (the capture is profile-independent); the gate's complete failure set must contain `CONTEXT_UNDECLARED` naming the source — `PROFILE_INHERITED` is present as well and does not satisfy the control — and the loading set's clean counterpart (nothing planted) fails `PROFILE_INHERITED` only, which proves the detector reads the loaded set and not the profile. The ancestor pair keeps its second half under an activated cell (WP-17; O4, §14 check 3). Both halves of every source must run.
  4. Tool boundary (N#9), **live** on the real host — the rule evaluation under `-p` is a host behaviour this plan asserts, so a fake cannot stand in: a producing call reading a file inside the manifest directory is accepted with the read recorded; a `Read` of a path outside the manifest (an absolute path to a planted file beside the cell, and a `..` path) is refused by the host before content returns — the transcript shows the `tool_use` and a denial `tool_result`, and no byte of the planted file (its canary) appears in any transcript, capture or output; a `Grep`, `Glob` and `Bash` request are each refused as ungranted and recorded; a symlink inside the manifest pointing outside it → refused (control: the same symlink resolved inside → accepted). Golden with the fake for the recording path; live here and live again in WP-23 (O4).
  5. Live (through `dispatch.py` under the calibration tranche): one minimal judge-profile call on claude-sonnet-5-5/medium passes `gate.accept` with `seat_observed == seat_sent`, usage measured (`message_start`/`message_delta` + `result.modelUsage`); the **host-allowance measurement** of WP-06 done-when 3 is made here first (minimal calls under the flag set; the observed input minus the driver's bytes, the maximum over the calls, recorded into `seats.json` and declared in `run.json` — the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`, N#0r4; the probe's ≈3.2k floor is the expected class; a measurement, never a maximum); a second with `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16` ends `stop_reason: max_tokens` and is rejected `COMPLETION_INCOMPLETE` (§14 check 4); a third with `--profile inherit` is rejected `PROFILE_INHERITED`. Token sweep (P4) finds 0 files.
  6. Packaging, in a scratch home (`HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `ZDOTDIR` exported to a fixture root — never the owner's homes; N#1r3): `bash install.sh install --non-interactive` deploys `claude-run` with the helper; `install.sh verify` sees both; the packed-install test (conventions) runs a hermetic call with the fake host from the tarball install with the checkout unreachable and produces a complete capture and receipt; `gates/check-surfaces.py`, `check-hygiene.py`, `check-endpoints.py`, `check-package.sh` exit 0; `ontology/check-ontology.py` projection freshness exits 0 after `emit-map.py`.
- **Verification point.** Parity leg (golden) + the three live calls + install/verify round trip + packed-install test.
- **Review gate.** X with the packet = the runner, the leg, §3.1/§3.2, and the prototype `hermetic-call.sh`; O on the shipped-surface prose (docs, SURFACES, DEPENDENCIES).
- **Size.** L (≈350 lines bash + ≈250 Python + ≈220 leg).
- **Main risk.** Claude Code flag semantics are version-bound (`--setting-sources ""`, `--safe-mode`, ancestor walk). Mitigation: the flag-set hash is pinned per host version in `seats.json`; §14 check 3 and 4 re-run on every version change; a mismatch is a redesign trigger (§5).

### WP-04 Codex capture mode in `codex-run.sh` (shipped) + parity leg extension

- **Goal.** Add a capture mode to the landed hermetic profile: websocket trace frames
  (`RUST_LOG='tungstenite::protocol=trace'`), otel `codex.sse_event`/`codex.api_request` log-only
  rows, the effective-context rendering (`codex debug prompt-input` with the same homes and
  overrides, plus app-server `instructionSources`), frame whitelisting before storage, and the
  WP-02 receipt evidence keys — no receipt-schema change.
- **Design.** §3.1, §3.2 (Codex attestation: `response.model` frames, per-response join,
  `frames_blind`, the usage-bearing completion ledger and the HTTPS attempt rules), §13.3 (warm-up
  request, retries as `codex_core::responses_retry`), §14 checks 1–2, D-20261020-8166e7
  (trace-frame channel + canary, fail-closed `MODEL_UNATTESTED`).
- **Files.** shipped: `wrappers/codex-run.sh` (change: `--capture DIR` / `REVIEW_CAPTURE_DIR`,
  `REVIEW_CALL_ID`, evidence keys; ports `codex-runner/proto/codex-run-capture.sh`),
  `wrappers/codex_frame_filter.py` (new; whitelist from `frame_filter.py` — every non-content field
  the gate and accounting read is kept: frame type, `response.model`, usage, ids, `status`,
  `generate` (warm-up), `incomplete_details`, `error`, `reasoning.effort`, refusal markers, and the
  sent frame's turn metadata (`request_kind`, thread and agent ids); prompt and output bodies are
  dropped — a filter test asserts each kept field survives and no body text does; **its own `package.json` `files[]` entry**,
  resolved relative to the adapter's resolved path), `install.sh` (a `deploy_file` line for the
  helper beside line 816's `codex-run` and its `verify_present` line), `SURFACES.md` (claim the deploy
  source), `DEPENDENCIES.md` (capture row; `bash -n` line). author-side: `gates/check_parity.py::codex_run`
  extended (capture-mode assertions), `docs/advanced-launch.md` paragraph (shipped prose; no repo
  paths), `ontology/emit-map.py` re-run after the `install.sh` edit.
- **Dependencies.** P1 (hard), WP-02.
- **Artifacts and interfaces.** `capture/` holds `frames.jsonl` (filtered), `otel.jsonl`,
  `prompt-input.txt` (rendering), `instruction-sources.json`, `rollout.jsonl` copy, `usage.json`
  (per request: kind ∈ {warm-up, main, child, compaction}, in/out/cache, attempts, and the §3.2
  completion-ledger join: usage-bearing `response.completed` rows joined to frames; a usage-less
  row without a usage-bearing one recorded as an interrupted attempt with provisional usage;
  HTTPS attempt coverage reported complete only when `responses_retry` warnings reconcile, else
  unknown); receipt `evidence.capture_sha256` = hash of the capture manifest;
  `effort_provenance: host-reported` when the frames' `reasoning.effort` equals the request.
- **Done when.**
  1. `check_parity.py --only codex_run` (extended) exits 0 with a fake `codex` that emits canned frames/otel: capture files present and whitelisted (control: a frame carrying a prompt body is dropped and the leg asserts its absence), evidence keys complete (`RECEIPT_KEY_MISSING` when one is removed from the fake's path), inherit profile unchanged byte-for-byte in argv (control: diff against the P1 leg's expected argv), the helper resolved relative to the adapter (control: helper removed → named failure, no checkout fallback).
  2. Rendering: with `--cd` inside a scratch repository carrying `AGENTS.md`, `prompt-input.txt` contains no AGENTS.md message and only built-in skills (§14 check 2; O4 plant). Control: the inherit profile at the same `--cd` shows the AGENTS.md message — proving the rendering can see one.
  3. Live canary (`distill.py preflight --codex-canary`, one `codex exec` on gpt-6-luna/medium through capture and `dispatch.py`): `response.model` frames seen, one warm-up request recorded (11.6–16.4k input, no output), otel rows join every frame; gate accepts with `seat_observed == seat_sent` and `effort_provenance: host-reported`. Control: run with `RUST_LOG` unset → `frames_seen == 0` → `MODEL_UNATTESTED` (fail-closed proven on the real binary). A second live call terminated mid-stream (SIGTERM to the host after `response.created`) → a real aborted stream → rejected (§3.2 control).
  4. Transport fallback and attempt fixtures (replay, from probe 5 and probe 9 recordings: the retained fallback, HTTP drop, HTTP retry and mixed-coverage recordings): otel completion with no joined frame → `frames_blind`, usage taken from otel, request kind `unknown`, call rejected (O10 plant); the HTTP-drop recording yields an interrupted attempt with provisional usage; the HTTP-retry recording reconciles two posts to one stream through the `responses_retry` warning.
  5. Packaging, in a scratch home as WP-03 done-when 6 (never the owner's homes; N#1r3): `bash install.sh install --non-interactive` deploys `codex-run` with the helper; `install.sh verify` sees both; the packed-install test runs a capture with the fake host from the tarball install with the checkout unreachable; `gates/check-surfaces.py`, `check-hygiene.py`, `check-endpoints.py`, `check-package.sh` exit 0; `ontology/check-ontology.py` exits 0 after `emit-map.py`.
- **Verification point.** Extended leg + live canary and aborted stream + replay fixtures + packed-install test.
- **Review gate.** X (another Claude-family reviewer cannot stand in: this is the Codex seat's own attestation — the reviewer is dispatched through the pre-capture hermetic profile, and the review packet notes it); O on the DEPENDENCIES/advanced-launch prose.
- **Size.** M (≈350 lines).
- **Main risk.** `tungstenite` trace output format changes with codex-cli; the canary catches it, so the first symptom is `MODEL_UNATTESTED` on every Codex call — by design (owner decision).

### WP-05 Census (S1, O1)

- **Goal.** Rewrite `session-distill/census.py` transcript-first over four sources (Claude Code
  `~/.claude/projects/**/*.jsonl`, Claude Desktop `claude-code-sessions/**/local_*.json` index +
  transcripts, Codex `~/.codex/sessions/**` incl. `.jsonl.zst`, `~/.codex/archived_sessions/**`),
  first-entry-point classification, the originator table (defaults: `Codex Desktop`/`codex_work_desktop`
  → desktop; `Claude Code` originator in `vscode` → excluded; `codex_vscode`/`sidepanel` → unknown),
  child linking (linked, not counted), the disjoint statuses **as §5.1**, transcript versions and
  ranges **as §5.2** (`session-distill/coverage.json`), lineage (roots, affirmed lineage, unique-root
  rule), provenance verdicts from host indexes (`~/.codex/state_5.sqlite` `threads`,
  `~/.claude/history.jsonl`, Desktop index) → `indexed | not_indexed | index_missing`, `known_absent`
  per class, `unknown_provenance` listed with counts, pin join (`instructions_session` pins), the
  reconciliation of S3's results back into the statuses, and the per-source coverage measures.
- **Design.** §5.1, §5.2, §5.3, §13.4 (coverage), §14 checks 5 and 7, D-20261020-bcba5e (lineage
  counting rule; census over compressed/archived rollouts).
- **Files.** author-side: `session-distill/census.py` (rewrite; today 195 lines driven by
  `history.jsonl` with dispositions `eligible_main/excluded_dispatched/unknown_quarantine/known_absent_source`;
  the runbook invokes `census.py --end YYYY-MM-DD` and `digest.py` consumes its `disposition`,
  `transcript`, `provider`, `session_id` and `goals` fields, so by the cutover rule the legacy
  invocation and output stay as they are until WP-22 and the new census is a separate entrypoint,
  `distill.py census`; control: the documented census-to-digest handoff runs on fixtures through
  WP-21), `session-distill/runlib/sources.py` (readers;
  `zstd -dc` via subprocess with the absolute path from `run.json.sources`, output into the immutable
  copy of WP-06), `session-distill/runlib/lineage.py` (ports `claude-records/scripts/classify.py`,
  `features.py`, `codex-records/scripts/classify.py`), `session-distill/runlib/provenance.py` (ports
  `provenance-index/scripts/measure.py`, `path-mismatch.py`), `session-distill/runlib/coverage.py`
  (the §5.2 state: versions, read and processed-for-window ranges, pending events, backlog, windows),
  `session-distill/coverage.json` (new, tracked state), `session-distill/originators.json` (the
  table; owner-editable), `gates/control-audit.py` `SUBJECTS`.
- **Dependencies.** WP-01. Independent of WP-02–04.
- **Artifacts and interfaces.** `census.json`: per transcript `{id, source, path, sha256, status,
  originator, entrypoint, lineage{component, root, unique_root, affirmed[]}, provenance ∈ {indexed,
  not_indexed, index_missing}, counted (bool), window_overlap ∈ {inside, straddles_start, straddles_end,
  context_only}, pin{content_ref|null}, versions[]}` with `status` **as §5.1** (`excluded(reason)`,
  `child_of(parent)`, `unknown_provenance`, `unreadable`, `known_absent`, or eligible ending as
  `read_complete`, `read_partial`, `failed`, `deferred`, `nothing_new`) plus totals per source;
  `coverage.json` **as §5.2** — per transcript the versions `{sha, record_count, prefix_sha}`, per
  version the **read** ranges and the **processed for window w** ranges, pending events with their
  ids, the backlog of unread ranges for `read_partial`, `failed` and `deferred` sessions, windows with
  accounted and fully-read flags; targeted runs read but never advance periodic coverage.
- **Done when.**
  1. `census.py --self-test` builds a synthetic corpus per O1 plant (one fixture each; every fixture is a declared golden) and asserts the classification named in §18 for every one: named Desktop sessions (Claude and Codex) → desktop; resumed session with appended records → one transcript, continuity holds, a new range; rewritten transcript → continuity fails, a new version read in full, prior evidence ids still pointing at the prior version's copy; missing source directory → source reported unknown with no total (never zero); all sources empty → run succeeds with zero eligible; deferred and partial carried into the backlog; child transcript → `child_of`, linked, not counted; records straddling window start → earlier records context, not counted; event at a window's end whose outcome falls in the next → read as context, stitched by the next run (fixture shared with WP-08); interactive Claude root later resumed headlessly → stays `claude-cli`; a copy of a root beside its original → not unique root, in S1's unknown-independence share; activated Codex `vscode` session with originator `agent-bios` + pin → `codex-cli`, same without pin → `unknown_provenance`; Claude fork with inherited head and copied record ids, no pointer → affirmed with source; Codex compaction → classified only once §14 check 5 has measured it (fixture flagged `measurement_pending` until WP-23 records it); rollout compressed in place after indexing → `indexed`; moved to `archived_sessions/` → same transcript id, continuity; compressed rollout in window → read; lone copy with new id, no original → `not_indexed`, in the share; Desktop session absent from every index → `not_indexed`; unreadable index → `index_missing` (read, not counted); `vscode` rollout with originator `Claude Code` → excluded; unnamed originator → `unknown_provenance` with count; index-only identities (Codex, Desktop) → `known_absent`; a transcript with no new records since the last window → `nothing_new`. Control per fixture: the fixture's expected status flipped to any other value fails by fixture name.
  2. Statuses are disjoint and the union equals the discovered set: `sum(counts by status) == discovered` asserted in the self-test and at every live run (`SET_MISMATCH` otherwise); after S3, the eligible statuses are reconciled from S3's records (`read_complete`/`read_partial`/`failed`/`deferred`/`nothing_new`) and the per-source counts add up again (control: an S3 record deleted → the reconciliation fails naming the session).
  3. Range ownership (F04): a record read as context for window w+1 appears in the **read** ranges and not in the **processed** ranges of its own window; the run that owns that window processes it (two scratch runs); a window is **accounted** when every eligible session has a terminal status with its unread ranges in the backlog, and the run record reports accounted and fully-read counts separately (control: one session left non-terminal → not accounted); a **targeted** run after a periodic one leaves the periodic coverage byte-identical (control: a targeted run that advanced a processed range fails `TARGETED_ADVANCED_COVERAGE`); pending events survive a run boundary with their ids.
  4. Live, read-only over the owner's real homes: counts reproduce the probe measurement classes (1,653/1,682 Codex indexed, 79/82 Claude history, 9/12 Desktop as of 2026-10-20 — re-measured, not asserted as equal; a drop below the recorded class with no host change is reported); every `.jsonl.zst` under `~/.codex/sessions` and `archived_sessions` is read (control: `run.json.sources.zstd` set to a nonexistent path → those files `unreadable` by name, not silently skipped).
  5. `coverage.json` writes are atomic (lock, base-hash check, temp + fsync + rename); control: a stale base hash is refused.
  6. Host indexes are read without writing: `state_5.sqlite` through a read-only connection that still sees its write-ahead log (never `immutable=1`, which ignores the WAL and can miss recent threads); control: a thread written to a fixture database's WAL and not yet checkpointed is found.
  7. Contract fidelity: the status vocabulary and the coverage schema's required sets equal §5.1 and §5.2 (self-test against the copied, cited lists).
- **Verification point.** Self-test corpus + one live read-only census compared against the probe's provenance-index figures.
- **Review gate.** W on readers; X on the counting rule (unique root + indexed) and on the coverage state (it decides whether absence can be claimed).
- **Size.** L (≈1,000 lines incl. fixtures).
- **Main risk.** Host index shapes are undocumented (`state_5.sqlite`, Desktop `local_*.json`); a change turns a source `index_missing` and recurrence silently drops — surfaced by §14 check 7 and the per-source provenance counts in every run record.

### WP-06 Views, immutable sources, redaction projection, evidence store, search, expansion (S2, O2)

- **Goal.** `distill.py views`: immutable hash-named copies of every eligible transcript version
  (decompressed `.zst` included), a **versioned redaction projection** of each version
  (`learn/redact.py::redact` plus local-path masking, `redaction_version` recorded), token-bounded
  windows cut from the projection **as §5.4** (input at most 120k with output capacity reserved, a
  five-turn overlap, oversized messages split into mapped spans, tool results as head, tail and
  every error line, an omission manifest naming each clipped record, its size and omitted span), the
  evidence store with records **as §5.5**, BM25 search over the **full redacted text of every version
  including clipped spans**, and the expansion API S3 calls (`expand(locator) → additional windows
  under the same token bound and span mapping`, logged with reason).
- **Design.** §5.4, §5.5, §13.4 (view complete vs source complete), §5.2 (`window_role` on
  evidence records).
- **Files.** author-side: `session-distill/runlib/views.py`, `redaction.py`, `evidence.py`,
  `search.py` (new). `learn/redact.py` unchanged (shipped; imported by author-side code — allowed
  direction). `session-distill/digest.py` stays until WP-22 (its counters move to `views.py` as
  hints; digests are not evidence).
- **Dependencies.** WP-05 (census.json, coverage state), WP-01 (evidence record schema).
- **Artifacts and interfaces.** `sources/<version_sha>.jsonl` (raw, immutable, never read by a model;
  the owner's openable locator in the review points here); `redacted/<version_sha>.<redaction_version>.jsonl`
  (the deterministic projection; the only text windows, search, and quotes are built from);
  `views/<transcript>/<n>.json` with `{window_n, driver_bytes, host_allowance, bound_ok, span_map[], records[{record_id,
  text|clipped{head, tail, error_lines[], omitted_span}}], omission_manifest[], overlap{prev, next}}`;
  `evidence/*.jsonl` records as §5.5 plus `window_role` (§5.2); `index/bm25/` (pure-Python inverted
  index over the projection, rebuilt per run); `expansions.jsonl` `{call_id, locator, reason,
  decision ∈ {expand, skip}, forced_by ∈ {pending_event, search_match, none}}`.
- **Done when.**
  1. Immutability and projection: an evidence locator resolves to bytes whose hash equals the recorded `version_sha`, and its `redacted_text` equals the projection of that content block at its `redaction_version` (control: edit a source copy → `SOURCE_TAMPERED`; change the projection's version → the old quote fails `REDACTION_VERSION_MISMATCH` and a re-projection passes); the O2 "altered quote" shares this fixture.
  2. Redaction: every `SECRET_RE` match and every absolute path under the owner's home is masked in the projection; control: a planted token and a planted `/Users/<name>/…` path in a synthetic transcript appear in no projection, window, index entry, or evidence record (grep returns 0) while the raw copy keeps them; a correctly masked quote validates (control: the F02 case — a quote carrying the masked form passes; one carrying the raw bytes fails, so raw text cannot reach a claim).
  3. Windows (F03): each record is **owned** by exactly one window (processed-for-window accounting, set-complete), and appears additionally in the five-turn overlap of its neighbours (control: an overlap removed → `OVERLAP_MISSING`; a record owned twice → `SET_MISMATCH`); a message larger than a window is split into mapped spans whose union is the message; every error line of a clipped tool result is kept whole (control: an error line dropped → named); the input bound is implemented **exactly as the owner's amendment of §5.4** (the record `2026-10-21T0026--cc0498f--input-bound-amendment.md`, 2026-10-21, corrected 2026-10-21 to its scope; N#0r4, N#0r5), which replaces the earlier guaranteed-bound instruction and governs **view-window calls only** — S3 reading and its expansion windows, the calls whose packet carries a window of a transcript view; every other call keeps its own section's contract and is bounded only by its seat's context capacity (R authoring, §8.6, ≈136k input): (a) **the driver's part is bounded before dispatch** — for a view-window call, the UTF-8 byte count of everything the driver supplies (the view window, the packet template, the schema, any declared instructions) is at most 120k minus the seat's **declared host allowance**; a token covers at least one byte, so this bounds the driver's part in tokens without a tokenizer; (b) **the host's part is a declared allowance, verified per call** — measured per host version and flag set in preflight (WP-23 done-when 3: minimal calls under the flag set, observed input minus the driver's bytes, the maximum over the calls), declared in `run.json.host_allowance{}`, re-measured on every host upgrade (§14 checks); a seat without a declared allowance is refused at S0 (`ALLOWANCE_UNDECLARED`); every view-window call's observed input (input + cache creation + cache read) is compared with 120k after it returns; (c) **an observed input above 120k on a view-window call is a host change** — recorded against the call as `INPUT_BOUND_EXCEEDED`, and the run stops, in rehearsal and in production, until the allowance is re-measured and the declaration amended (`declare --amend`); a single request may exceed 120k by the host's unforeseen addition once, and the run does not continue on that basis; (d) **output capacity stays reserved** — driver bytes + allowance + the output reservation ≤ the seat's context capacity, checked before dispatch; a window failing (a) or (d) is split. No complete-request guarantee is claimed; the bytes-per-token ratio per script class is a packing diagnostic only. Controls: a window whose driver bytes exceed 120k − allowance → split before dispatch; one passing (a) but failing (d) → split; a replayed capture whose observed input exceeds 120k → `INPUT_BOUND_EXCEEDED`, the run refuses every further dispatch until `run.json` declares a re-measured allowance through `--amend` (asserted); a run with a seat lacking an allowance → `ALLOWANCE_UNDECLARED` at S0; a retained R-authoring capture above 120k through the dispatcher as a non-window call → accepted, the window rule untouched (WP-02 done-when 5, N#0r5).
  4. Omission and completeness: a clipped record's manifest names it, its size and its omitted span; a session is **view complete** when every window has a gate-passing result and every clipped record has an executed expansion or a recorded skip, **source complete** when in addition no span was skipped (O2 plant); skipped spans are listed per session.
  5. Mandatory expansion predicate **as §5.4**, by code: every clipped record between a pending event and the next human turn, and every clipped record the full-source search matches, is `forced` (control: a clipped record after the next human turn is not forced; one before it is); expansions are additional windows under the same bound and span mapping (control: an expansion exceeding the bound is itself split).
  6. The F-O9-04 pair (F28): two clipped results with identical visible head and tail, one hiding a paraphrased occasion that carries none of the retrieval terms — the search **misses** it, no expansion is forced, S3's skip leaves the session at basis view, and the absence claim is refused → `pending` (control: the same hidden occasion written with a retrieval term → search match → forced expansion → found). The hidden occasion's `omitted_span` hash differs between the pair (the manifest distinguishes them even when the visible bytes do not).
  7. Contract fidelity: `evidence.schema.json`'s required set equals §5.5 plus `window_role`; the window invariants above are the self-test's branch list.
- **Verification point.** Self-test on synthetic transcripts + a live run over the real census (read-only) measuring window counts and token totals for §16.
- **Review gate.** W; X on the omission/expansion predicate and the redaction projection (they decide what a model can see and what a quote can be).
- **Size.** L (≈800 lines).
- **Main risk.** Byte-bounded views hold roughly a quarter to a third of the tokens a 120k-token view would (≈3–4 bytes per token on this corpus), so S3 makes three to four times as many calls; the cost is the overlaps and per-call overhead (§8.2). The host's part is never bounded in advance — it is a declared allowance verified per call, and an overrun stops the run as the amendment record provides.

### WP-07 Inventory of units per layer and reference point (S2, O3)

- **Goal.** `distill.py inventory`: numbered units `{unit_id, layer, path, heading, n, text, sha,
  operative|reference}` **as §6.1** for every layer of the effective library at each reference point
  (*current*, *release*, *selection*), with the completeness flag per reference point and the
  operative-context map (a unit's enclosing exceptions and cross-guide context) the §6.3/§6.4
  derivations need.
- **Design.** §6.1 (layers and reference points), §6.3 (operative context, version-bound exposure),
  §6.4 inputs, §8.6 (R uses the same units).
- **Files.** author-side: `session-distill/runlib/inventory.py` (ports
  `reconstruction/scripts/inventory.py`: 1,938 units / 1,553 operative measured), `gates/control-audit.py`
  `SUBJECTS`. `session-distill/batch.py` and the `out/baseline.txt` pattern stay until WP-22.
- **Dependencies.** WP-01; WP-13 (schema 2 for the ledger layer — an interface edge, golden until it lands); reads `compose/instructions_store.py` snapshot inventories (shipped, unchanged).
- **Layers and producers (F06).** Every §6.1 layer has a named producer, and a layer without one is
  reported `unsupported`, which makes the reference point incomplete:
  catalog content — rules, guides, skills, hooks, agents from the checkout, plus adopted packages
  (`compose/instructions_catalog.py` origins, read from frozen copies); the owner's overlays — as
  `compose/instructions_store.py` resolves its effective items (frozen copies, done-when 5); native
  layers — native global instruction files, project instruction files, settings, memory entries,
  session-level injection (captured from the host homes at S0 into the run); incubating ledger
  principles and active `keep` records (the ledger, WP-13's schema 2). Reference points: *current*
  (all layers now); *release* (from a pin's `inputs.baseline_ref` to `runtime/baselines/<ref>/inventory.json`,
  104 items measured; for an unpinned session, unknown unless an install record maps the session's
  time to a baseline); *selection* (the pin's snapshot items). Historical overlays and native
  layers are unknown unless recorded; an unknown layer or an unsupported structure makes the
  reference point incomplete.
- **Artifacts and interfaces.** `inventory/<reference>.json` `{reference{kind, ref|commit|content_ref,
  complete, incomplete_reasons[]}, layers[{layer, producer, status ∈ {complete, incomplete, unsupported,
  unknown}}], units[{…as §6.1…, operative_context[unit_id], version_sha256}]}`; stable `unit_id`
  across references by content hash + carrier, with a rename map.
- **Done when.**
  1. Live: the release reference maps every one of the 104 baseline items to ≥1 unit, judged against an **independent expected set** (the baseline file's own item list, read separately from the produced mapping); control: remove one produced mapping while keeping the expected set → `BASELINE_UNMAPPED` naming the item (a control that shrinks the expected set is rejected by the self-test — F06); the current checkout yields a unit count within the measured class (≈1.9k; reported, not asserted equal).
  2. Every §6.1 layer is present in `layers[]` with a producer; fixtures: an unsupported layer (a structure the producer cannot split) → `unsupported`, reference point incomplete; an unavailable layer (a historical native layer with no record) → `unknown`, incomplete; a layer whose carrier failed to parse → `incomplete`, never silently empty (`leg()`-style non-empty assertion per layer). Control: the fixture's expected completeness flipped fails by layer name.
  3. A unit whose operative context spans two guides lists both carriers; control: remove the cross-reference from the fixture guide → the context shrinks and the O3 fixture "second guide unread → exposed_not_read" (WP-10) flips to `delivered` — proving the context map is load-bearing.
  4. Identical fragment across two versions with different operative contexts yields two units with one shared `fragment_sha256` (O3 plant input).
  5. Read-only over the owner's state: the store's public methods lock and may recover pending transactions, so inventory resolves overlays and snapshots from **frozen copies** of the state it reads, never through a call that can write; every file under the owner's state root hashes the same before and after a live inventory. Control: the same inventory pointed at a fixture state with a pending transaction through the store's recovering entry point shows the write the frozen-copy route avoids.
  6. Contract fidelity: the unit record's required set equals §6.1's list plus the plan's `operative_context` and `version_sha256`.
- **Verification point.** Self-test + live inventory of `cc0498f` and of the deployed release.
- **Review gate.** W; X on the layer/producer table (it decides what "complete reference point" means for every absence claim).
- **Size.** M (≈450 lines).
- **Main risk.** Unit identity drift across versions; mitigated by the rename map and the fragment hash, both consumed by WP-10's version-binding rule.

### WP-08 S3 Read and stitch (model, claude-sonnet-5-5/xhigh)

- **Goal.** `distill.py read`: per window, a packet (view + schema + the principles block) dispatched
  through `dispatch.py` to the hermetic Claude profile; claim records **as §3.3** and evidence
  records **as §5.5**; per clipped record an `expand`/`skip` decision with reason (set accounting
  over the omission manifest; mandatory expansions enforced by code, WP-06); observation judgments
  for due expected observations **as §11**; **one stitch call per session** after all its windows;
  twelve concurrent calls; reconciliation of each session's reading status back into the census.
- **Design.** §4 (S3), §5.4, §5.5, §11 (occasions, exposure, resolutions), §3.3, S-3 (no `read.js`).
- **Files.** author-side: `session-distill/runlib/stage_read.py`, `schemas/read.schema.json`,
  `schemas/stitch.schema.json`, `packets/read.md`, `packets/stitch.md` (templates). The legacy
  screeners stay until WP-22.
- **Dependencies.** WP-02, WP-03, WP-06, WP-07 (unit ids for observation judgments), WP-01's
  expected-observation schema (interface); the seeds themselves come from WP-21 at run time and
  from golden fixtures in development (F34: the interface is fixed in WP-01, not deferred).
- **Artifacts and interfaces.** `claims/<transcript>.jsonl` (as §3.3), `events/<transcript>.jsonl`
  `{event_id, kind, at_record, claim_ids[], outcome ∈ {resolved, pending, unresolved}, description,
  stitched_from}` (`pending` only before the session's stitch call; after it, `resolved` or
  `unresolved` as §5.4 — the carry-forward to the next run is `coverage.json`'s pending-events
  entry, a separate record; N#10r3), `observations/<window>.jsonl` `{expected_id,
  occasion_locator, exposure ∈ {eligible, exposure_unknown}, verdict ∈ {observed, not_observed}, basis
  ∈ {incomplete, view, source}, evidence_ids[]}` (per instance; the window **resolution** — not
  observed / observed / no occasion / pending — is derived by code as §11 and stored by WP-21),
  `expansions.jsonl`.
- **Done when.**
  1. Quote fidelity is code-checked after every call: each claim's evidence records resolve and their `redacted_text` equals the projection (WP-06); control (O2): a model output that retypes a quote (fixture result with one character changed) → `QUOTE_MISMATCH`, the claim dropped and the call's set accounting reports it. No stage retypes a claim; a revision is a new claim referencing the old (control: an in-place edit of a claim file → `CLAIM_IMMUTABLE`).
  2. Mandatory expansion: a window whose manifest carries a forced record must have a matching `expand` decision before the window's record is accepted; control: a result that skips it → `EXPANSION_SKIPPED`; the decisive outcome in the omitted middle of a successful tool result after a pending event is found after expansion and not found without (O2, live through the real seat once).
  3. Stitching **as §5.4**: after all windows of a session, one stitch call per session receives its pending events and later claim records and resolves each with evidence ids or leaves it `unresolved`; the O2 plant "cause and outcome four windows apart" runs **live through the production reader and the stitch path** (its four windows and the stitch call on the real seat, receipts retained — N#11) and resolves (event `resolved`, `stitched_from` set, the evidence ids naming the outcome window's records); its counterpart with the outcome window withheld, also live, ends its stitch call **`unresolved`** in the event record (§5.4), the run record counts it, and `coverage.json` carries the carry-forward pending-events entry with its id (WP-05) for the next run's stitch — both records asserted, as two states, never one (N#10r3; the golden twin of both checks accounting and persistence only); a session with pending events and no stitch call is `read_partial`, not `read_complete` (control: stitch call suppressed → status named).
  4. Cross-window/run: the O1/O9 fixture "event at end of window N, outcome in N+1" is read as context in run N and processed and stitched in run N+1 (two scratch runs in the self-test).
  5. Observation instances: for each due expected observation, every occasion found (by reading, with the search forcing expansions) is judged `observed`/`not_observed` with evidence ids, its exposure judged **as §11** (eligible or `exposure_unknown`), and its coverage basis set **by code** over the claim's scope (incomplete / view / source, §5.4); the §11 resolution fixtures (O9) run through `measures.derive_resolution` (WP-21) with each expected verdict flipped failing by name; basis `incomplete` is produced for a scope with a `read_partial`, `failed`, `deferred`, unreadable, unknown-provenance, or known-absent session, or an unaccounted source (F04 control: one source left unaccounted → every absence resolution in scope is `pending`). **Live seeded follow-up path** (N#3r3; RH-1, WP-23 done-when 4): expected observations seeded into the seeded corpus's windows — one with an observed occasion, one with a not-observed occasion, the hidden-occasion pair of F-O9-04 (the search-missed twin and its retrieval-term counterpart), the skipped-span occasion of F-O9-03, and a request → guide read → action sequence (F-O9-07) — are **recognized by the production reader** on the real seat, with forced expansions where the search matches, judged with evidence ids, resolved by code (WP-21), rendered and closed into the ledger; receipts retained; each instance's verdict, exposure and basis asserted. Precedence and persistence stay golden.
  6. Live: S3 over three real windows plus their stitch call passes the gate with `seat_observed == claude-sonnet-5-5`; concurrency 12 honoured (control: a semaphore probe counts ≤ 12 in flight); the per-view observed `input_tokens` and envelope bytes are reported as the bytes-per-token packing diagnostic per script class (WP-06; never a bound — N#0r3).
  7. Resumability: the stage is idempotent per window (call ids derived from window identity); a kill-and-resume control re-dispatches only the unfinished windows.
  8. Contract fidelity: `read.schema.json`'s claim object equals §3.3's list; the observation instance's basis vocabulary equals §5.4's three.
- **Verification point.** Golden self-test (fake runner returning canned results) + live three-window run with stitch; the per-window measured usage seeds §16.
- **Review gate.** X on the packets and schemas (what the model is asked and allowed to answer); W on the code.
- **Size.** L (≈800 lines + templates).
- **Main risk.** Usage: views are byte-bounded at 120k (≈30–40k tokens each at the measured packing), so S3's call count, not its per-call size, is what can exhaust a usage window. The supervisor's breaker defers and resumes; done-when 7 is the proof.

### WP-09 S4 Form candidates and lifecycle intake (model, claude-opus-5-5/high)

- **Goal.** `distill.py form`: cross-session candidate formation — situation / action / exception,
  the eight admission fields, type A–G — with the **exact partition of every event** required by §9
  (member of a candidate; a **non-finding** with one reason from the fixed list — no consequence,
  routine step, duplicate of another event; or a **rejected finding** — a claim about what to do
  differently that fails an admission requirement at formation), and the **lifecycle inputs of §7.1
  produced before formation**: every unresolved incubate decision whose expiry is on or before the
  window end (incubating entries and pending interventions on placed entries) with the window's
  occasions for its observation; the legacy incubation intake (every migrated `incubating` entry,
  142 measured, as a lifecycle candidate `legacy, observation unavailable`, in every run until it
  receives an applied decision); obsolete-review hints (from the occasion index S12 writes, WP-21);
  redundancy hints (code: BM25 similarity over current operative units above a fixed threshold);
  and the G inputs of §7.4 (correction clusters by tension across sessions; ledger clusters of at
  least three placed learnings sharing retrieved principle text; arc retrospectives only when the
  declared question names an arc).
- **Design.** §4 (S4), §7.1, §7.4 (type G), §9 (population), D-20261020-71699d (eight admission
  requirements), §3.3.
- **Files.** author-side: `session-distill/runlib/stage_form.py`, `runlib/lifecycle_intake.py` (new;
  code-produced inputs), `schemas/form.schema.json`, `packets/form.md`. `consolidate.js` stays until
  WP-22 (its cluster schema is kept in the new schema).
- **Dependencies.** WP-08 (all sessions read — a barrier), WP-02, WP-03, WP-13 (ledger schema 2 for
  the intake; golden ledgers until it lands), WP-21's occasion index (interface fixed here; golden
  until it lands).
- **Artifacts and interfaces.** `candidates.json` `{candidate_id, type, situation, action, exception,
  admission{eight fields}, events[], sessions[], lifecycle{kind, target_entry|unit, resolves|null}}`;
  `partition.jsonl` `{event_id, class ∈ {candidate, non_finding, rejected_finding}, candidate_id|reason}`;
  `intake.json` (the lifecycle candidates with their source: due decision, legacy, obsolete hint,
  redundancy hint, G cluster); `population.json` `{candidate_ids[] (intake included, each with
  `event_ids[]`, empty for a legacy or due-decision candidate), rejected_finding_ids[],
  non_finding_ids[], event_membership{event_id → candidate_id | class}}` — the §9 render population
  as an explicit set, consumed by WP-20 done-when 1 (N#12).
- **Done when.**
  1. Partition (F12): every event is assigned exactly once to one of the three classes; a non-finding carries a reason from the fixed list only; control: a result that drops one event → `SET_MISMATCH`; one assigned to two candidates → `SET_MISMATCH`; a non-finding reason outside the list → `SCHEMA_INVALID`. `population.json` (N#12) lists every candidate id including the lifecycle intake, every rejected finding and every non-finding, with the event membership; control: a lifecycle candidate present in `intake.json` and absent from `population.json` → `SET_MISMATCH` naming it; an event whose membership names a candidate not in the list → `SET_MISMATCH`.
  2. Admission fields are all present and typed per schema; control: a result with seven → `SCHEMA_INVALID`; a rejected finding names the failed requirement (control: none named → invalid).
  3. Intake completeness (F05): the intake set equals, by id, the union of (a) every ledger decision with `expiry ≤ window.end` and no `resolves` pointer, (b) every migrated `incubating` entry without an applied decision, (c) every obsolete-review hint S12 derived (WP-21 done-when 8: three chronologically consecutive source-basis windows with no match — N#17) and (d) every redundancy pair of operative units, (e) every G cluster meeting the §7.4 input rule; control: one due decision removed from the produced intake → `INTAKE_INCOMPLETE` naming it; a pending intervention on a placed entry enters (not only incubating entries); an entry that received an applied decision in the previous run does not re-enter (two scratch runs).
  4. Type G (F05): a G candidate without both sides of the tension, the preference ordering, what it now forbids, and ≥3 claim ids as instances is refused (`G_ANTI_ABSTRACTION`); the evidence bar (≥3 independent lineages resolving the same tension the same way, or an owner-confirmed arc) is checked by code from S5's lineage counts and the proposal is held below the bar otherwise.
  5. Barrier: `form` refuses to run while any eligible session's S3 record is missing or partial (`INPUT_PARTIAL`), except sessions the census marked `deferred` (they are listed, not blocking).
  6. Live: one run over the WP-08 live claims passes the gate on claude-opus-5-5.
  7. Contract fidelity: the partition classes and non-finding reasons equal §9's; the intake sources equal §7.1's list.
- **Verification point.** Golden + live.
- **Review gate.** X on packet/schema and the intake rule; W on code.
- **Size.** L (≈600 lines).
- **Main risk.** Candidate granularity (too coarse merges unrelated lessons). The S5 recurrence counts and the two judges are the correction; the overturn rate (§13.4) is the measure that tells.

### WP-10 S5 Retrieve, check, planted controls, and the §6.4 derivations (code)

- **Goal.** Deterministic checks and derivations: retrieval **as §6.2** (BM25 over units, query =
  situation + action + exception + named hints; top 20 per layer plus every named unit; top ledger
  entries), quote checks re-run over the formed set, lineage independence and recurrence counts
  (unique root ∧ indexed), the **planted controls as §6.5** inserted under ordinary ids, and the
  code that turns judgments into unit diagnosis, candidate diagnosis, unit outcome, kind, admission
  and promotion eligibility **as §6.4**, generated from the §6.4 unit-outcome table held as data so
  an untested row is visible.
- **Design.** §5.3 (counting), §6.2 (retrieval), §6.3 (delivery evidence table incl. installation
  receipt, `selected_unavailable`, `exposed_not_read`), §6.4, §6.5, §7.1.
- **Files.** author-side: `session-distill/runlib/stage_retrieve.py`, `derive.py`, `controls.py`,
  `tables/unit_outcome.json` (the §6.4 table as data — the single source the code and the fixture
  generator both read), `tables/delivery_evidence.json` (the §6.3 levels as data), `gates/control-audit.py`
  `SUBJECTS`.
- **Dependencies.** WP-05, WP-07, WP-09; WP-15 for the installation-receipt row (golden until it lands).
- **Artifacts and interfaces.** `checks.json` `{candidate_id, recurrence{count, independent_sessions[],
  excluded{unknown_independence, not_indexed}}, retrieved_units[], ledger_entries[], quote_ok}`;
  `controls.json` — the planted population **as §6.5** (two paraphrases of covered units, two
  admission failures: temporal-order cause and a task-specific requirement, one altered quote, one
  fabricated session id, plus the gate controls of §3.2), each with its expected verdict, held
  **outside every packet**: the ids are ordinary and no judge-visible byte marks a control (F27);
  `derive.unit_outcome(judgment, delivery) → {unit_diagnosis, candidate_diagnosis, unit_outcomes[],
  kind, admission, eligible}`.
- **Done when.**
  1. Fixture generator (N#18): the generator writes one fixture per row of `tables/unit_outcome.json` **once**, and the fixtures are committed (frozen) with the row id each names; the self-test never regenerates — it compares three sets, the table's rows, the frozen fixtures' row ids, and the case ids the run actually executed, and fails on any difference (`check_bijection` pattern from `benchmarks/manifest.py`). Controls: a row added to a scratch copy of the table with the frozen fixtures unchanged → an uncovered row by id; a frozen fixture deleted → an unfixtured row; an executed case removed from the run's recorded set → the coverage check fails by case id. The same rule governs every table-generated fixture set (WP-13 done-when 4).
  2. O3 verdicts (each with its control = expected flipped): pinned session violating a delivered rule → misfire; guide pointer exposed, never read → misfire (trigger); `selected_unavailable` → not delivered; unpinned session → unclassified; one helpful + one violated covering unit → misfire, both shown; guide read spanning the unit but content truncated before it → `exposed_not_read`; unpinned session that read the unit before violating → misfire, selection unknown; helpful + unknown-contribution → unclassified, both shown; helpful + unknown-following → unclassified; read returns unit and heading but not the enclosing exception → `exposed_not_read`; operative context across two guides read completely → delivered, second guide unread → `exposed_not_read`, second guide from a different version than the requirement names → `exposed_not_read`; identical fragment in two versions with different contexts → binds by pin or release, else unknown. The kind precedence (misfire > not delivered > unclassified > confirmed > all-neutral unclassified) is asserted on a mixed fixture.
  3. Recurrence: the O4 "session pair whose replay hides its ancestry" (same root, copied ids) counts as one; control: two genuinely distinct roots count as two.
  4. Planted controls **as §6.5**: the full population is inserted every run (control: a run with fewer than the six listed plus the gate controls → `CONTROLS_INCOMPLETE`); controls are reported apart from the natural rejection share; a planted control accepted as natural stops the run before S7 (`CONTROL_FAILED`); **more than twenty natural candidates with no rejection fails O4** (`REJECTION_SHARE_ZERO`; control: 21 natural candidates all admitted → fails; 20 → passes); structural: a byte-diff of a control's judge packets against a natural candidate's of the same shape shows no marker field (F27).
  5. Contract fidelity: the table rows equal §6.4's table (self-test against the copied, cited rows); the delivery levels equal §6.3's.
- **Verification point.** Generated fixtures; live over WP-09 output; the planted population through the real judges in the rehearsal (F-O4-01, live).
- **Review gate.** X — the derivations are the delivery/coverage judgment the owner reads; the reviewer gets the tables and the code, not this plan.
- **Size.** L (≈850 lines incl. generator).
- **Main risk.** The table and the code disagreeing silently; the generator makes every row a test, and the code reads the table rather than restating it.

### WP-11 S6 Judge A ‖ B and absence sweeps (models)

- **Goal.** `distill.py judge`: for each candidate, Judge A (claude-opus-5-5/high via WP-03) and
  Judge B (gpt-6-astra/xhigh via WP-04 hermetic capture) from one judgment payload built **as §6.2**,
  each in its own call envelope (N#1)
  (candidate, claims and evidence projected by code, retrieved units, retrieved ledger entries;
  per-unit and per-candidate fields as §6.2); absence sweeps **as §6.2** (shards of remaining units at
  a complete reference point, several candidates per shard, once by claude-sonnet-5-5 as a
  producing call and once by gpt-6-luna under the independent-judgment contract, bound to the
  inventory hash); **Judge B's cross-review** per absence claim of every unit either sweep marked a
  partial match plus a code-drawn sample of fifty negatives seeded by run id, with both reasons;
  any unit flagged by either sweep or by Judge B **returned to both judges**; disagreement →
  disputed; an incomplete reference point → absence `unknown`; judgment reuse keyed **as §6.2**.
- **Design.** §4 (S6), §6.2, §6.4 (derivations consumed from WP-10), §3.1, §3.2.
- **Files.** author-side: `session-distill/runlib/stage_judge.py`, `schemas/judge.schema.json`,
  `schemas/sweep.schema.json`, `schemas/cross_review.schema.json`, `packets/judge.md`,
  `packets/sweep.md`, `packets/cross_review.md`.
- **Dependencies.** WP-02, WP-03, WP-04, WP-10.
- **Artifacts and interfaces.** `judgments/<candidate>/A.json|B.json` (§6.2 fields),
  `sweeps/<group>/<shard>/<provider>.json`, `cross_review/<candidate>.json` `{partial_flags[],
  seeded_negatives[50], verdicts[]}`, `reconsiderations/<candidate>/{A,B}.json`,
  `judgments/reuse.json` `{judgment_key → judgment_ref}` where `judgment_key` is the §6.2 key — the
  hash of the judgment **payload** (candidate version with claim and evidence versions, unit
  text, heading path, the enclosing trigger, enclosing exceptions, referenced operative units,
  layer, scope, prompt and schema versions, **and seat**), never of the per-call envelope; dispatch
  receipts stay per call and are never part of the key (F11, N#1).
- **Done when.**
  1. A and B receive the same judgment payload (N#1): `payload_sha256` (WP-02) equal in both receipts while each `packet_sha256` is unique to its call, since the envelope carries the `call_id` (§3.2); controls: a seat-specific line injected into one payload → `PACKET_DIVERGENCE`; two receipts carrying one `packet_sha256` → `RECEIPT_STALE` (a receipt serves one call).
  2. Both judges uncertain → `disputed`, not admitted (O4); control: both confident-agree → admitted; the disputed path is exercised live once with a planted ambiguous candidate (its verdict recorded; the golden fixture proves the aggregation).
  3. Cross-review (F10): for every absence claim, Judge B's packet carries every partial flag from either sweep and exactly fifty seeded negatives with both sweeps' reasons (control: one partial flag removed → `CROSS_REVIEW_INCOMPLETE`; the seed changed → a different sample, asserted; one sampled reason corrupted → detected by the packet hash against the sweep results); a unit flagged by either sweep or by B returns to both judges (control: a reconsideration missing from one judge → `RECONSIDERATION_MISSING`); a gap claim contradicted by a unit only one sweep flags → both judges reconsider it; if they disagree → `disputed` (O4).
  4. Reuse **as §6.2** (F11): within a run, a judgment at the *release* reference point is reused at *current* only when the full key is identical (no call made; asserted); A's judgment can never satisfy B (seat in the key; control: a B request with A's key present → a new call); one byte of unit text changed → a new call; **no cross-run reuse** (a new run with an identical key makes a fresh dispatch; control: the previous run's `reuse.json` present → ignored and a call made).
  5. Context evidence: a judgment call whose capture shows an undeclared instruction loaded is rejected even though its answer is schema-valid (O4; replay fixture from the WP-03 plant; live in WP-23).
  6. Sharding: every unit of each reference point is covered by exactly one shard per group (set accounting), each shard bound to the inventory hash (control: inventory changed → shard results refused); the reuse rate between *release* and *current* is reported (the §16 80% assumption is measured, not assumed); an incomplete reference point yields absence `unknown` (control: a reference point marked incomplete → no gap diagnosis).
  7. Live: one candidate through A and B, one sweep shard per provider, and one cross-review pass the gate with observed seats.
  8. Contract fidelity: the judgment schema's per-unit and per-candidate fields equal §6.2's; the reuse key's component list equals §6.2's.
- **Verification point.** Golden + live five calls.
- **Review gate.** X on packets/schemas (the reviewer is the same family as Judge B; the packet says so and asks for the Claude-side blind spots explicitly); W on code.
- **Size.** L (≈800 lines).
- **Main risk.** Sweep volume (≈380 calls per run); batching is the lever, and the shard size is a `run.json` field, not a constant.

### WP-12 S7 Propose, S7b review, placement contract, commit sequencing (models + code)

- **Goal.** `distill.py propose` (claude-opus-5-5/high) producing proposals **as §7.3** (typed
  operations with before-state hashes, complete artifact set, behavior contract, expected
  observation as WP-01's schema, cost and the Korean review fields) with the §7.2 vocabularies;
  `distill.py review-proposals` (gpt-6-astra/xhigh) returning disposition and destination review and
  the faithful-merge judgment; code enforcing the **allowed pairs of §7.2** and the **structural rules
  of §7.3** from tables held as data, the §7.4 placement contract, ranking **as §7.5**, and the
  **commit-sequencing check** (S-14): before the core freeze, S7b verifies that the operations of
  every core item set admit an ordered sequence of intermediate trees each passing the hook (run
  in a scratch worktree); a set with no such sequence — a route and its carrier proposed as
  separate items — is re-formed into one item or deferred before the freeze. Legacy lifecycle
  candidates arrive from WP-09's intake and are proposed under the legacy-maintenance row.
- **Design.** §7.2–§7.5, §12.2 (legacy rows), §13.1 (global ops), §10.5 (order of operations), O5.
- **Files.** author-side: `session-distill/runlib/stage_propose.py`, `stage_review_proposals.py`,
  `placement.py` (the operative contract as code over `tables/allowed_pairs.json` — the §7.2 table
  — `tables/structural_rules.json` — the §7.3 list — and `tables/placement_rules.json` — the
  decidable restrictions of §7.4: the destination order behind "cheapest that still fires on time",
  consumer escalation, the decidable conditions of the enforcement, gate and hook bars, the
  new-guide count, the C-principle routes, and the global-file revision; N#10), `packets/placement_contract.md`
  (the one canonical reviewed text of §7.4's semantic bars — leftward reformulation, retirement
  reasons, verbatim facts — carried into the S7 and S7b packets and judged by S7b), `sequencing.py` (the ordered-tree check,
  reused by WP-20/WP-21 for the approved F order), `schemas/propose.schema.json`,
  `schemas/s7b.schema.json`, `packets/propose.md`, `packets/s7b.md`; `design/session-distill/PLACEMENT-FRAMEWORK.md`
  untouched (dated rationale). The three tables and `packets/placement_contract.md` are together the
  **single authority** for the full §7.4 contract: the runbook's contract section (WP-22) is generated
  from them, never hand-written (F32, N#10).
- **Dependencies.** WP-11, WP-09 (intake), WP-13 (ledger schema 2 for lifecycle targets; golden until it lands).
- **Artifacts and interfaces.** `proposals.json` `{item_id, candidate_id, kind, diagnosis, disposition,
  operations[] (as §7.3, typed, each with the expected before-state hash), artifact_set, behavior_contract,
  expected_observation, cost, review_fields{…}, destination{layer, carrier}, rank, requires_R (core),
  sequence_group}`; `review-s7b.json` `{item_id, verdict, faithful_merge ∈ {yes, no, n/a}, alternative|null,
  notes}`; `sequencing.json` `{set_hash, order[], tree_hashes[], hook_results[]}`.
- **Done when.**
  1. Allowed pairs: every (kind/diagnosis, disposition) is in `tables/allowed_pairs.json`; control (O5): a disallowed pair → `PAIR_DISALLOWED`; the table's rows equal §7.2's (self-test against the copied, cited table).
  2. Structural rules **as §7.3**: a global-file operation other than delete or merge → rejected; incubate without observation and expiry → `EXPIRY_REQUIRED`; keep or drop without reason → rejected; a reduce or merge touching a unit with an active keep record not named in the proposal → `KEEP_GUARDED` (eligible only after the owner's `keep 해제`); each with its clean counterpart.
  3. Placement **as §7.4** (N#10), decidable rules from `tables/placement_rules.json`, each with its clean counterpart: a guide proposed where fewer than five promoted items share a situation no guide covers → `GUIDE_PREMATURE`; an instruction aimed at a consumer that reads only code (a script, a hermetic dispatch) → `CONSUMER_MISMATCH`; a blocking gate proposed for a semantic criterion → `GATE_ON_JUDGMENT`; an addition to the global file → `GLOBAL_ADDITION`; a C principle routed anywhere but the router trigger of the guide whose situation it names or session-level injection → `C_ROUTE`; a hook that blocks or judges → `HOOK_CHARTER`. The semantic bars reach S7 and S7b only through `packets/placement_contract.md` (golden: the packet carries the text and its hash; live: S7b's verdict on one planted leftward-reformulation case in the rehearsal). Contract fidelity: the table's rule ids plus the text's bars equal §7.4's list (self-test against the copied, cited list).
  4. Lifecycle fixtures: evidence supporting keep, re-deliver, reduce each yields that disposition; a redundant pair of working units → reduce-by-merge allowed; a core item admitted by adjudication → `awaiting_R`, never applied (O5); these run live through S4–S7 on the rehearsal's fixture corpus (F27), golden for the aggregation.
  5. Legacy row: S3-03 (status `incubating`, `decision1 = user-approved-default 2026-07-19`, `decision2 = recommendation-confirmed 2026-07-19`, no mapped decision in schema 2) is proposed as unclassified with incubate-with-prospective-observation-and-expiry or drop under the legacy-maintenance row; an entry with a mapped incubate decision is proposed with it; control: the two fixtures swapped fail by entry id. Items at `none` stay in the intake; a retired counterpart does not re-enter (O5).
  6. Keep/incubate/drop proposals carry no library operations and `requires_test == false` (ledger-only dispositions, §10.4).
  7. Sequencing (S-14, F17): the route-and-carrier pair proposed as two items is caught before the freeze; a set with a valid order records it; the same checker is exported for WP-20/WP-21 to re-run on the exact approved subset (control fixture: a full set with a valid order whose approved subset has none → the subset is returned, not applied).
  8. Live: one proposal and its S7b review pass the gate.
  9. The ranking is a total order with the §7.5 keys (control: two rows differing only in candidate id order deterministically).
- **Verification point.** Golden + live two calls + the sequencing check in a scratch worktree.
- **Review gate.** X on the placement code, the tables, and the packets; O on the legacy-maintenance row wording (it decides what happens to 142 entries).
- **Size.** L (≈800 lines).
- **Main risk.** Two authorities for the placement contract; closed by generating the runbook section from the tables (WP-22) and comparing structurally in the umbrella.

### WP-13 Ledger schema 2, migration, transitions, state file, launcher nudge (§12)

- **Goal.** Schema 2 for `design/session-distill/ledger.json` **exactly as §12.1** (the new entry
  fields and `decisions[]` with its per-run element shape: disposition, approval and adjudication
  ids, confirmation, applied operations and delivery, tests, expected observation with its
  resolutions); the deterministic migration **exactly as §12.2** (its field table, prefix table,
  expected records for G-8, G-5, S2-17, S2-19, S3-06, S4-03, S4-07, S3-16, and its self-test
  rules); transitions **as §12.3** from the table held as data; the id-set check as an umbrella leg
  — `runlib/ledger.py --check` with its own `--self-test` in this WP, renamed to `merge-ledger.py
  --check` at the cutover (N#7r3) — windows at the ledger top level and the atomic
  journaled writes of §12.4; the external state file and the launcher nudge; and a **derived
  compatibility projection** for the old consumers (S-4).
- **Design.** §12.1–§12.4, §13.4 (library size), O10 plants.
- **Files.** author-side: `session-distill/runlib/ledger.py` (new; schema-2 validation, the id-set
  check, transitions and the atomic writes — the body `merge-ledger.py` takes over at the cutover),
  `session-distill/merge-ledger.py` (today 100 lines allocating `S<strength>-<nn>` ids and refusing
  a double window; **unchanged until the WP-22 cutover commit**, where it becomes the thin CLI over
  `runlib/ledger.py` that §12 names — N#14), `session-distill/migrate-ledger.py` (new, idempotent;
  `--check` compares a dry migration of the committed ledger to the expected records; the committed
  `design/session-distill/ledger.json` is **migrated in the WP-22 cutover commit**, together with the
  runbook that names the old commands, never earlier; the dated migration record §12.2 names for the
  removed `verdict`/`strength`/`criteria` values is written then),
  `session-distill/runlib/ledger_compat.py` (new; the projection, reading **both** schema versions —
  schema 1 passes through — so the readers switch in this WP while the data moves at the cutover),
  `session-distill/tables/ledger_readers.json` (new; the explicit reader inventory, N#15),
  `session-distill/tables/transitions.json`
  (the §12.3 table), `session-distill/update-state.py` (change: add `transcript_files_total` beside
  the existing `window_end`, `history_lines_total`, `updated`), `learn/build-promotions.py` (change:
  reads placed entries through `ledger_compat` instead of `placed_anchor` on the entry — it is
  author-side, so the import direction holds), `gates/check-parity.sh` (new `if [ -f
  session-distill/runlib/ledger.py ]` leg running its `--check` and `--self-test`; WP-22 switches the
  leg to `merge-ledger.py --check` — today's `merge-ledger.py` requires `--window-end` and supports
  neither flag, so no leg invokes it before the cutover, N#7r3),
  `gates/control-audit.py` `SUBJECTS`, `design/session-distill/versions.json` (kept; written at
  close). shipped:
  `launch/agent-launch.py::session_distill_nudge` (change: nudge when `days_since(window_end) ≥
  cadence_days` or `transcript_files_total` grew by `transcript_growth`; a file without the new field
  keeps today's `history_lines_total` behaviour; no file → no nudge), `launch/agent-launch.toml`
  `[session_distill]` (add `cadence_days`, `transcript_growth` beside `nudge_after = 250`).
  `compose/instructions-state.py::ledger_summary` (shipped) reads `entries[].status` and
  `classification.layer`, both **kept** by §12.2, so it needs no change — asserted, not assumed
  (done-when 6). `learn/ingest-learnings-export.py` reads `learning_id` (kept).
- **Dependencies.** WP-01. Independent of the model stages; the WP-09/WP-12/WP-21 consumers use
  golden ledgers until this lands.
- **Artifacts and interfaces.** Schema 2 **as §12.1** with windows **as §12.4** at the top level;
  the plan adds nothing to the entry or to `decisions[]` elements. `ledger_compat.placed_entries()`
  → `{id, status, learning_id, placed_anchor, placed_package_id, classification}` **derived** from
  `destination` and the latest place decision's `applied` (or the `legacy_application` element) —
  a read-only projection, never stored. `runlib/ledger.py --check [--base <sha>]` (the same
  command as `merge-ledger.py --check` from the cutover);
  `migrate-ledger.py --check`; state file `~/.local/share/agent-bios/session-distill-state.json`
  `{window_end, history_lines_total, transcript_files_total, updated}` (env override
  `AGENT_BIOS_SESSION_DISTILL_STATE` kept).
- **Consumer inventory (F36, N#15).** The code readers of the ledger are **explicit data**
  (`tables/ledger_readers.json`: path, the fields read, how the path is built): `learn/build-promotions.py`
  (`status == "placed"`, `learning_id`, `placed_anchor`, `placed_package_id`),
  `compose/instructions-state.py::ledger_summary` (`status`, `classification.layer`),
  `learn/ingest-learnings-export.py` (`learning_id`), `session-distill/merge-ledger.py` (until the
  cutover) and `runlib/ledger.py`; `SURFACES.md` names the file as an authority. Discovery is
  broader than a literal search and is a disclosure checked against the inventory: `git grep -n
  'ledger.json'` over tracked code **plus** an AST pass over tracked Python for path constructions
  whose string components include both `session-distill` and `ledger.json` in any order — the
  literal search does find `learn/build-promotions.py` and `learn/ingest-learnings-export.py` (each
  carries the `ledger.json` component), and the AST pass is what identifies them as readers of this
  ledger and catches a path built from components that carry no such literal. `migrate-ledger.py --self-test` fails when discovery finds a reader the inventory
  does not list (controls: the two component-built readers are found on the real tree, asserted; a
  planted reader that constructs the path from components in a scratch copy → named). A literal hit
  count is never reported as reader completeness.
- **Done when.**
  1. Migration (dry, against a scratch copy until the cutover — N#14): `migrate-ledger.py` over the real ledger maps every one of the 310 legacy decision values through the §12.2 prefix table (control: an unmapped value planted in a scratch copy → `DECISION_UNMAPPED` naming the entry); every legacy field value is found in the migrated record (§12.2's own self-test rule; control: a value dropped → fails naming field and entry); the eight named rows equal their expected migrated records (fixtures copied from §12.2's table; control: one expected record edited → fails by row id); `placed`/`placed_anchor`/`implementation` land in `destination` and the latest place decision's `applied` (or a `legacy_application` element for G-5 and G-8), never as entry fields (control: an entry-level `placed_anchor` after migration → `FIELD_NOT_MIGRATED`); the migration is idempotent (second run is a no-op).
  2. Compatibility projection (S-4): `learn/build-promotions.py` through `ledger_compat` reproduces `learn/promotions.json` byte-identical on the unmigrated ledger (schema 1 passthrough) and on the dry-migrated copy (control: a placed learning whose `destination` is removed → the F3 guard fails, as it does today); `--check` in the umbrella stays green. The old CLI keeps working as the delivered runbook says until the cutover (N#14): the self-test runs the **documented invocation** `merge-ledger.py --window-end <date>` on a scratch copy of the unmigrated ledger with a fixture `consolidated.json` and asserts the merged result (control: the invocation's exit status is checked, not the file's existence).
  3. History test (F14): a placed entry with an earlier applied expected observation and a later pending intervention, each resolved independently, carries two `decisions[]` elements with their own `expected_observation.resolutions[]`, and the status is unchanged (control: a resolution appended to the wrong element → named).
  4. Transitions: one frozen fixture per non-"—" cell of `tables/transitions.json` (frozen fixtures and the three-set comparison as WP-10 done-when 1, N#18); control: a disallowed transition → `TRANSITION_DISALLOWED`; the table equals §12.3's (self-test against the copied, cited table).
  5. The id-set check (`runlib/ledger.py --check` in the umbrella now, `merge-ledger.py --check` from the cutover as §12 names it): equal-count deletion plus insertion → fails naming the lost id (O10); duplicate id → fails; new id not in the allocation → fails; a changed row without a validated decision → fails; the committed ledger passes (schema 1 now, schema 2 after the cutover — the check reads both). `--self-test` runs these four as negative controls; its line in `gates/control-audit.py`'s output reads covered.
  6. Atomic writes: lock + base-hash + temp + fsync + rename; a concurrent writer with a stale base is refused; a crash injected between temp write and rename leaves the old file intact (fault injected by the self-test). `compose/instructions-state.py ledger_summary` on the migrated ledger returns counts whose sum equals `len(entries)` and lists no status outside §12's vocabulary.
  7. Nudge: `launch/agent-launch.py` with a state file carrying the new fields nudges at the cadence or the growth threshold; without them it behaves exactly as today (control: golden state files from before and after; the existing launcher receipts/golden legs in `check_parity.py --list` stay green); with no file, no nudge. The launcher reads no checkout file and not `coverage.json` (control: run with the checkout removed from reach).
  8. Contract fidelity: the entry schema's required set and the `decisions[]` element's required set equal §12.1's lists (self-test against the copied, cited lists).
- **Verification point.** Self-tests + the dry migration diffed against the expected records + the documented old invocation on a scratch copy + `./gates/check-parity.sh` green with the new leg listed.
- **Review gate.** X on the migration mapping, the projection, and the id-set invariants (the reviewer compares the schema with §12.1–§12.2); O on the cutover commit that migrates the ledger (WP-22; it rewrites the ledger the owner reads) and on the nudge thresholds.
- **Size.** L (≈1,100 lines incl. migration fixtures).
- **Main risk.** A consumer that reads a field §12.2 moves. Mitigation: the reader inventory above is a self-test subject, and the projection is the only read path for `placed_anchor`.

### WP-14 Global-file gate leg (§13.1, O10)

- **Goal.** A gate that compares `claude/CLAUDE.md` in the index with `HEAD`, blocks when the line
  count or the byte count grows, discloses every index line absent from `HEAD`, and discloses —
  never blocks — the before/after line and byte counts of `ko/claude/CLAUDE.md` (S-10, N#12r3);
  runs in the pre-commit hook on the index snapshot and in the umbrella.
- **Design.** §13.1, §2 (owner decision: commit gate), AGENTS.md §8 (frozen to reductions).
- **Files.** author-side: `gates/check-global-file.py` (new; `--self-test`), `gates/check-parity.sh`
  (leg line running the gate and its `--self-test`), `.githooks/pre-commit` (already runs the
  umbrella; no change unless the leg must read `GIT_INDEX_FILE` — it does, via `git show
  :claude/CLAUDE.md` under the hook's exported env), `gates/control-audit.py` `SUBJECTS` (F31: the
  file is checker-named, so the inventory finds it, but the registration makes the intent
  explicit), `AGENTS.md` §8 (one sentence: now ENFORCED by `gates/check-global-file.py`),
  `IMPLEMENTATION_MAP.html`.
- **Dependencies.** None (can land first).
- **Artifacts and interfaces.** `check-global-file.py [--index|--worktree] [--base HEAD]`: exit 1 on
  growth with `GLOBAL_LINES_GREW a→b` / `GLOBAL_BYTES_GREW a→b`; stdout disclosure block `NEW LINES:`
  listing each index line absent from the base, and `KO SIZE: lines a→b, bytes a→b` for
  `ko/claude/CLAUDE.md` whenever it changed (disclosure only).
- **Done when.**
  1. `--self-test` (scratch repo built with the hook's `GIT_DIR`/`GIT_WORK_TREE` scrubbed — the `own_repo_env` trap in AGENTS.md): added line → blocks `GLOBAL_LINES_GREW`; added word → blocks `GLOBAL_BYTES_GREW`; deleted line → passes with empty disclosure; deletion plus a shorter unrelated line → passes the count check and the disclosure names the new line (O10 plant and §13.1's fourth control); unchanged → passes; a grown `ko/claude/CLAUDE.md` with the English file unchanged → **passes** (exit 0) and the `KO SIZE` block reports the growth (N#12r3; controls: the block absent on Korean growth → self-test fails; Korean growth blocking the commit → self-test fails); control of the control: the positive case is run first and the self-test asserts the `NEW LINES` disclosure is non-empty exactly in the fourth case.
  2. Hook path: staging a grown `claude/CLAUDE.md` in a scratch clone with `core.hooksPath` set is refused by the commit; restoring the file on disk while the index keeps the growth is still refused (index, not worktree — the AGENTS.md §3 property).
  3. `gates/control-audit.py`'s output carries a covered line for the gate (read, not inferred from the exit status); `check-parity.sh` lists the leg.
- **Verification point.** Self-test + scratch-clone commit attempt.
- **Review gate.** W (small, decidable); O for the AGENTS.md sentence.
- **Size.** S (≈150 lines).
- **Main risk.** Reads the worktree instead of the index; the hook-path control is the proof.

### WP-15 Installation receipt and snapshot binding (§6.3; shipped)

- **Goal.** `compose/instructions_install.py` writes an installation receipt after verification and
  before `COMMITTED` (the declared installer source digest at import and at receipt, the transaction
  id and result, the installed release digest, the resulting artifact hashes, and — for a recovered
  transaction — the digest of the installer that **began** it); the journal carries
  `installer_digest` and `receipt_id`; `compose/instructions_store.py` records the receipt id in the
  snapshot's `inputs` before `content_ref` is derived and exposes `installation_binding`.
- **Design.** §6.3 (the installation-receipt row of the delivery evidence table), §11 (the single
  installer-exposure predicate), probe 10 (`distill-probes-20261020/installer/patch-v1.diff`, 223
  lines; `run_all.sh` 11 scenarios / 139 assertions).
- **Files.** shipped: `compose/instructions_install.py` (`INSTALLER_CODE` tuple incl.
  `launch/shell_integration.py`, `_installer_code()`, `_CODE_AT_START`, `transaction_id` in the record,
  `_write_receipt` → `runtime/receipts/<sha256>.json`, `receipt_id` in the `COMMITTED` journal
  written by `_finish_install_transaction` (~line 866–894), recovery in `_recover_pending_transactions`
  (~909) carrying the beginning installer's digest forward), `compose/instructions_store.py`
  (`RECEIPT_ARTIFACTS`, `read_installation_receipt`, `installation_binding`,
  `_current_installation_receipt_id`, `inputs["installation_receipt_id"]` inserted before
  `content_ref = _digest(inputs)` (~line 1526), `snapshot_inventory` returns `installation_binding`),
  `SURFACES.md` (the receipt as an artifact of the installer surface — `check-surfaces.py` holds
  authority blocks against the installer). author-side: `compose/test_instructions_install.py` /
  `test_instructions_store.py` (existing test files extended; they are `AUTHOR_SIDE_FILES`),
  `gates/check-receipt-chain.py` (extend if it walks installer artifacts), `gates/check_parity.py`
  installer legs (`--list` to find the exact names before editing), `ontology/extract.py` +
  `check-ontology.py` (evidence literals may move; re-measure, never edit numbers to match).
- **Dependencies.** None on other WPs; WP-10, WP-17 and WP-21 consume it.
- **Artifacts and interfaces.** `runtime/receipts/<receipt_id>.json` whose canonical body `{schema:
  "InstallationReceipt/v1", transaction_id, result, installer{digest_at_import, digest, build, package_modules_run},
  begun_by_installer_digest|null, release_digest, baseline_ref, selection, artifacts[{path, sha256}], at}`
  — `installer.digest` is the installer that **executed** the receipt-writing step;
  `begun_by_installer_digest` is the `installer_digest` the original journal recorded, kept only when
  it differs from the executing digest (as the probe patch does: `begun_by if begun_by !=
  now["digest"] else None`); `store.installation_binding() → {bound, receipt_id, transaction_id,
  installer_digest, release_digest, begun_by_installer_digest}`; `content_ref` changes whenever the
  receipt id changes (the binding WP-21 verifies delivery with).
- **Done when.**
  1. Ported scenarios: the 11 `run_all.sh` scenarios pass as `compose/test_*` cases (139 assertions, the count asserted non-zero and listed); control: remove the receipt write → the "receipt before COMMITTED" scenario fails by name.
  2. Ordering and recovery identity (F18): the receipt file exists before the journal reaches `COMMITTED` (fault injection between the two leaves a receipt and a non-committed journal); a transaction **begun by installer X** and **recovered by installer Y** yields `installer.digest == Y` and `begun_by_installer_digest == X`, with X ≠ Y asserted (control: the two values swapped → fails by field; a transaction begun and finished by the same installer carries `null`); the F-O9-15 fixture consumes exactly this receipt and must come out `exposure_unknown` under §11's single predicate.
  3. A transaction begun before receipts existed recovers as `unbound` (`exposure_unknown` downstream — O9 plant); control: a receipt-bearing transaction recovers bound.
  4. `content_ref` differs between two snapshots that differ only in `installation_receipt_id` (control: identical receipt ids → identical `content_ref`); `compose/instructions_session.py` needs no change (the pin keeps `content_ref`; asserted by `verify_snapshot` on a pin written before and after).
  5. In a scratch home (as WP-03 done-when 6; never the owner's homes — N#1r3): `bash install.sh install --non-interactive` then `install.sh verify` exit 0; `./gates/check-parity.sh` green incl. `check-receipt-chain.py`, `check-surfaces.py`, `check-ontology.py`.
  6. Receipt identity (N#5r5): `receipt_id` is the sha256 of the canonical body and lives **outside** it — in the filename and in returned metadata (`installation_binding()`), as the prototype's `_write_receipt`/`read_installation_receipt` do; `read_installation_receipt` verifies that the file's bytes hash to the id (controls: a body carrying a `receipt_id` field → refused at write by the schema; a file whose bytes do not hash to its filename → `ValidationError`; a receipt re-serialized with reordered keys → the canonical form hashes the same).
- **Verification point.** Test files + install/verify round trip + umbrella.
- **Review gate.** X (shipped installer path; the reviewer gets the diff, the probe patch, and §6.3/§11); O acknowledges the shipped change.
- **Size.** M (≈300 lines incl. tests).
- **Main risk.** Ontology evidence literals drift (`check-ontology.py` fails on numbers that moved) — handled by re-extracting, which is the rule.

### WP-16 Harness: cells, fresh install per episode, isolation (§8.1)

- **Goal.** Change `benchmarks/run.py` and `benchmarks/dispatch.py` so every episode runs in a cell
  under the clean-ancestry root with a fresh private install (≈0.5 s measured), the token on a pipe
  fd into the child only (`benchmarks/instructions.py::auth_channel` pattern,
  `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`), **every protected root of §8.1** write-protected for
  the host's whole process tree (the state root `AGENT_BIOS_STATE_DIR`, the instructions root, the
  release tree, the snapshot, the pin, the journal, and the install, launcher and bin destinations
  of `compose/instructions_install.py`) via a `sandbox-exec` profile plus
  `--disallowedTools "Edit(//<roots>/**),Write(//<roots>/**)"` on Claude, and the three isolation
  checks of §8.1: static, host report, OS sandbox with unified-log denials joined by requesting
  pid and start time.
- **Design.** §8.1, §8.4 (actor seats), §13.2 (both caps on every dispatch — enforced by WP-02's
  supervisor, which every episode goes through).
- **Files.** author-side: `benchmarks/run.py`, `benchmarks/dispatch.py` (change), `benchmarks/cells.py`
  (new; ports `claude-runner/proto/cell.py`, `claude-activation/clean/scripts/p2_static_check`,
  `p2_profile`, `p2_sbx_denials`), `benchmarks/instructions.py` (change: `HOST_HOMES` per cell),
  `benchmarks/selftest.py` (control groups extended), `benchmarks/fixtures/` (cell fixtures).
  (`gates/check-lexicon.py` lists `benchmarks/` in `NOT_A_HOME`, so no naming constraint applies
  there — the earlier claim was wrong, F36.)
- **Dependencies.** P5, WP-01 (run ids), WP-02 (the supervisor every episode is dispatched through),
  WP-15 (the fresh install writes a receipt; golden until it lands).
- **Static-check contract (settled S-12, §6; F20).** The probe's `p2_static_check` skips credentials,
  binaries, SQLite files, host-generated directories and symlinks, and allows toolchain prefixes, so
  by itself it does not show that "no file names a path outside the cell". The ported check has a
  **closed inspection scope** held as data: the file classes it inspects (settings JSON/TOML, hook
  commands, MCP configurations, launcher scripts, native instruction files, Python and shell
  imports in the cell, symlink targets), the **allowlist** of required outside paths with a reason
  each (the pinned host binary and its install directory, OS libraries, the Python, `zstd` and
  `/usr/bin/log` executables), and the classes it does not inspect, listed in its result. An
  **effective configuration reference that could not be inspected** — an unreadable settings file,
  an unresolvable hook command, a dangling symlink, a path outside the allowlist — makes the
  episode `invalid`, never green with a disclosure; only inert literals in prose are disclosure.
  Owner-data, sibling-cell and run-output paths are never allowlisted; the sandbox of check 3
  enforces access independently.
- **Denial attribution (F20).** The unified log's sandbox-denial latency is **measured
  independently** in `cells.py --measure-denial-latency` (a probe process denied a write at a known
  instant; the delay until `/usr/bin/log show --predicate` returns it, sampled n ≥ 20; the p99 is
  the wait), not taken from any accounting constant (`claude-accounting/proto/acct.py`'s
  `FLUSH_WINDOW_S` = 0.25 s is the transcript-record flush window and unrelated). A denial is
  attributed only by a requesting pid with its start time recorded in the episode's process tree;
  the path corroborates. An episode closes `isolation: uncertain` until its denial window has
  elapsed, and a denial whose requester is unidentified invalidates every episode whose window
  overlaps it.
- **Artifacts and interfaces.** Cell: `<root>/<run>/<cell_id>/{home, config, state, release, snapshot,
  pin, journal, cwd}`; `cells.prepare(cell, host, seat, variant) → CellRecord{paths, install_receipt_id,
  static_check, sandbox_profile_sha256}`; `cells.verify(cell) → {static, host_report, denials[],
  isolation ∈ {valid, invalid, uncertain}}`; episode result gains `isolation{…}` and `valid`.
- **Done when.**
  1. Static check: a cell under the owner's `HOME` fails by name (O7); a copied setting pointing into the owner's real roots fails naming the setting path (O7); an uninspectable effective reference (a dangling symlink in `config/`) → `invalid` by path (F20); the clean cell passes; the scope and allowlist are data files whose every entry carries a reason (control: an allowlist entry without a reason → refused at load).
  2. Host report: an instruction file planted in an ancestor of the cell is listed by the host report and the episode is invalid (O4 counterpart to WP-03's runner half); clean counterpart passes; names are judged against the per-host-version baseline measured at a clean root plus the configuration manifest (control: an undeclared hook *name* in `system/init` → invalid).
  3. Sandbox, every protected root exercised: an actor's shell write (not an editing tool) to its own snapshot is denied by the profile, appears in the unified log by the actor's pid, is recorded as an action, and the episode stays **valid** (O7); an editing-tool attempt on the snapshot is denied by `--disallowedTools`, recorded, snapshot still verifies (O7); writes to the pin, the journal, the state root, the release tree, and each install/launcher/bin destination are denied and recorded (O7 and §8.1 — one control per root); an actor reading, and one writing, a sibling cell → denied, episode **invalid** (O7); two concurrent episodes with a denial on one's cell whose requesting pid neither recorded → both invalid and the denial is attributed to neither (O7); a denial arriving after the episode's close but inside the measured window is still joined (control: an episode closed before the window elapsed reads `uncertain`, never `valid`).
  4. Native state: an episode whose cell's instruction-surface hashes (release tree and snapshot included) changed mid-run (fault injected) is invalid (O7).
  5. Fresh install: every episode's cell carries a distinct installation receipt id (control: two episodes sharing one → `CELL_REUSED`); the install takes < 2 s measured per cell (reported).
  6. Token: `grep` for the token across every cell and output after a run finds 0 files (P4).
  7. Realization: `dispatch.real_bin` refuses a `claude`/`codex` that is not the pinned versioned path unless `--realization golden` is passed and recorded in the manifest; every episode is dispatched through `runlib/dispatch.py` (WP-02's closure check covers the `benchmarks/` modules the driver imports — N#5).
- **Verification point.** `benchmarks/selftest.py` control groups (golden with a fake host) + the denial-latency measurement + one live episode per host with each denial plant (the denials need the real host and the real sandbox).
- **Review gate.** X — isolation is the property that makes S8 results evidence; the reviewer gets the profile, the scope and allowlist data, the checks, §8.1, and the probe's `RESULTS.md`; O reviews the harness change (the former "guard re-approval" is this review).
- **Size.** XL (≈1,400 lines).
- **Main risk.** `sandbox-exec` profile semantics. Mitigation: every rule has a live plant, and `uncertain` is a terminal state the matrix counts as not scorable rather than as a pass.

### WP-17 Harness: headless activation, child actors, wrapper route (§8.2, §8.3)

- **Goal.** Headless activated actors on both hosts **as §8.2** — one invocation per host serving
  activation, the isolation report, the §3.2 completion fields and the §13.3 accounting: Claude via
  `claude -p --output-format stream-json --verbose --include-partial-messages --include-hook-events`
  with the `--session-id` `launch()` chose and the pin written by
  `compose/instructions_session.py::launch` (`observe_and_pin`, `claude_evidence`); Codex via the
  module's app-server `thread/start` + `inject_items` snapshot reference, then `codex exec resume
  --json` under the capture mode in place of the TTY step; the adapter records the snapshot's
  `unavailable` list, classifies the episode by the §3.2 completion fields (a pin can exist when the
  host failed), reaches the interactive path's outcomes for valid, invalid, disabled and unavailable
  native routes, and checks hook execution by host (Claude `hook_started` against the expected
  events; Codex executor-side markers with the hook-trust setting recorded in the episode manifest);
  child actors **as §8.3**; the sandboxing host wrapper route for activation.
- **Design.** §8.2, §8.3, §8.4, §6.3 (child session row; hook row), probes 1 and 3.
- **Files.** author-side: `benchmarks/activate.py` (new; ports `claude-activation/clean/scripts/p1lib`
  `headless_launch` and `codex-activation/scripts/`), `benchmarks/children.py` (new),
  `benchmarks/dispatch.py::command_for` (change: today `--output-format json` /
  `--permission-mode acceptEdits|plan`; the activated route uses the stream-json flag set and the
  cell's permission settings; `AUXILIARY_MODELS` removed in favour of `seats.json`'s declared
  auxiliary roles, S-7), `benchmarks/dispatch.py::_parse_claude` (stream-json parsing with partial
  messages), `benchmarks/receipt.py` (`BenchResponseReceipt/v1` gains `activation{pin, content_ref,
  unavailable[], native_routes{}, hooks{expected[], observed[], trust}}` and `children[]`;
  `effort_provenance` becomes `∈ {unverified, host-reported}`, `host-reported` only with Codex frame
  evidence — S-6/F30, replacing the validator's `must be unverified` rule).
- **Dependencies.** WP-16, WP-15 (pin carries the receipt-bound `content_ref`), WP-03 (shared flag
  knowledge), WP-04 (Codex capture for the child echo and frames), WP-02 (dispatch).
- **Artifacts and interfaces.** `activate.launch(cell, host, snapshot) → {session_id|thread_id, pin_path,
  content_ref, unavailable[], native_routes{claude_plugins|codex_hooks: valid|invalid|disabled|unavailable},
  hooks{expected[], observed[], trust}, completion{…§3.2 fields…}}`; `children.verify(episode) →
  [{child_id, host, brief_sha256, delivered_sha256, relay ∈ {plaintext, ciphertext_equal, none},
  inheritance{declared ∈ {none, controlled_fork}, markers{…}, inherited_context_sha256,
  declared_context_sha256}, ok, reason}]`; episode `actions.jsonl` (tool calls,
  denials, child spawns, compaction markers).
- **Done when.**
  1. Activation through the sandboxing host wrapper completes and pins (O7 clean plant); control: activation with the pin directory write-denied fails `PIN_UNWRITTEN` and the episode is invalid.
  2. Route and hook evidence (F21): the `unavailable` list is recorded from the snapshot (control: a snapshot with one unavailable item → listed, and the episode's delivery states for that unit read `selected_unavailable`); each native-route case (valid, invalid, disabled, unavailable; probe 1) reaches the interactive path's outcome and is classified as such (control: a disabled route read as clean → named); Claude: an expected hook with no `hook_started` → `route_failed` (control: `disableAllHooks` planted → named, pin still present); Codex: an expected executor-side marker missing → `route_failed`, and the episode manifest records the hook-trust setting (control: a session-flag hook under `codex exec` with trust not bypassed → `route_failed` by design, not clean).
  3. Claude child **as §8.3** (F19): exactly one `Agent` call, exactly one child transcript, and the child's first user record carrying the same bytes as the fixed brief (a `fork` child compared by suffix); controls: two Agent calls → invalid; a child transcript whose first user record differs by a paraphrase → invalid (O7); zero child transcripts → invalid.
  4. Codex child **as §8.3**: the child's echo equals the fixed brief byte for byte **and** the parent's and child's `spawn_agent` ciphertexts are equal (relay evidence); exact → accepted; paraphrased, edited by one character, with appended context → each invalid; a refusal to echo → invalid (O7); ciphertexts unequal with an exact echo → invalid (control).
  5. Inheritance **as §8.3** (F19, N#2): each stratum's route declares its permitted inheritance — `none` (a plain `Agent` child; Codex `spawn_agent` with `fork_turns: "none"`) or `controlled_fork` (Claude `subagent_type: fork`; Codex `fork_turns: "all"`) together with the **exact parent context** it may carry, **frozen before the parent is launched** as a construction rule over the episode's fixed inputs — never read from the parent at spawn time (N#2r3): the activation's system context (hash-pinned), exactly one user record whose bytes are the fixed brief, and the parent's own first-turn assistant records up to the spawning call; nothing older than the session start, no second user record, no record from another turn. `children.verify` reads the **actual fork markers** — Claude: `fork-context-ref {parentSessionId, parentLastUuid, contextLength}` and `meta.isFork`, and the child's `prompt_snapshot.systemPrompt` against the parent's; Codex: `forked_from_id`, `history_base` and the replayed records — and the child's effective-context evidence (§6.3 child row); generic child identity (`agentId`/`isSidechain`; `parent_thread_id`/`source.subagent`) identifies a child and never establishes inheritance. It reconstructs the inherited context from the markers and compares it with the declared one. Verdicts: declared `none` with any fork marker → `CHILD_CONTEXT_INHERITED`; declared `controlled_fork` whose inherited context equals the declared parent context and whose echo is exact → **valid** (the controlled-fork counterpart, F-O7-21f); declared `controlled_fork` with records beyond the frozen allowance — the extra-history plant scripts a second user turn before the spawn, so `contextLength`/the replayed records carry a second user record the rule forbids — with a replayed record outside the allowed prefix, with a different `parentSessionId`/`forked_from_id`, or with `parentLastUuid`/`history_base` not at the allowed prefix's last record → `CHILD_CONTEXT_INHERITED`, episode invalid (O7 "inherited parent context controlled"); the clean and the extra-history cases are judged against the **same** frozen rule, which is what makes the negative distinguishable (N#2r3). The parent canary's absence from the echo is recorded and is never the acceptance criterion (control: canary absent, undeclared history present → still invalid).
  6. Pin evidence: `claude_evidence` resolves the native session log for the cell's `--session-id` and cwd; control: a cell whose cwd differs from the record → no evidence → episode invalid.
  7. `benchmarks/receipt.py`: a Codex receipt with frame-reported effort equal to the request validates as `host-reported`; a Claude receipt claiming `host-reported` is refused; `unverified` validates on both (F30).
  8. Live: one activated episode per host with one child each passes isolation (WP-16) and the gate (WP-02) with observed seats by role; the Codex child's warm-up request is visible in the capture (it is a separate billed request — §16 row).
- **Verification point.** Golden (fake hosts emitting recorded streams) + the two live episodes.
- **Review gate.** X; the reviewer gets the activation code, the probe 1/3 `RESULTS.md`, and §8.2–8.3; O reviews the harness change.
- **Size.** L (≈1,000 lines).
- **Main risk.** Codex app-server protocol drift (`thread/start`, `inject_items`); the live episode is the canary and a failure is a redesign trigger only if the protocol has no equivalent.

### WP-18 Episode accounting: actor channels, cap values, compaction reconciliation (§13.3; the stop is WP-02's)

- **Goal.** The actor-episode integration of WP-02's supervisor, monitor and stop (N#0): the
  actor-specific channels registered with the monitor **as the §13.3 channel table** (Claude main
  from `message_start`/`message_delta`, subagent requests from the subagent transcript, closing
  `result.modelUsage`; Codex frames and otel per request kind — main, child, compaction, warm-up),
  the three usage states, the §13.3 estimate rule, closing reconciliation with compaction as the
  residual only after every other request and failed attempt reconciles, the per-episode cap
  **values** handed to the supervisor (tokens, compaction count, with `--max-budget-usd` and
  `--max-turns` as secondary bounds), overshoot reporting (measured vs estimated), attempts, and
  the per-class p95 that feeds the supervisor's reservation. The monitor, the caps' evaluation and
  the process-tree stop are WP-02's and run on every call; this WP adds no second copy.
- **Design.** §13.2 (the stop guarantee, both caps, overshoot), §13.3 (channels, states, estimate,
  attempts, cost by cache tier), §8.7 (re-run once after `budget_stopped`), §16 (what is measured),
  O10 plants. Reservation, caps-before-dispatch and the breaker are WP-02's (F09).
- **Files.** author-side: `benchmarks/accounting.py` (new; registers the subagent-transcript and
  Codex child-thread channels with `runlib/monitor.py`, ports `finalize_after_exit` and
  `reconcile.py` from the probe prototypes, overshoot; the Ledger, `FLUSH_WINDOW_S`, `SentDecoder`
  and `stop_tree` ports live in WP-02's `monitor.py`/`stop.py`), `benchmarks/fixtures/faults/` (ports
  `codex-accounting/proto/fakeserver.py` injector and the Claude fault injector; declared golden),
  `session-distill/runlib/usage.py` (from WP-02; the shared states). shipped: `session-cost.py`
  `PRICES` (the two 5-5 rows only — its tuples already carry input, output, cache-read and the
  5-minute and 1-hour cache-write rates, so cost by cache tier needs no new key; Claude main
  requests use the one-hour tier, subagents the five-minute one, §13.3).
- **Dependencies.** WP-16, WP-17, WP-02 (supervisor and call-level usage), WP-04 (Codex frames/otel).
- **Artifacts and interfaces.** `usage.json` per episode `{requests[{request_id, kind, agent, role,
  in, out, cache{tier, read, write}, state ∈ {measured, provisional, unresolved}, attempt}],
  totals{measured, provisional, unresolved_count, complete}, compaction{markers, estimate,
  residual|unexplained}, overshoot{tokens, kind ∈ {measured, estimated}}, stopped ∈ {none,
  budget_stopped, compaction_cap, breaker}}`; `classes.json` (per class: n, p95, provisional flag) read
  by the supervisor.
- **Done when.**
  1. Claude channels (replay from probe 9 recordings, then live): main requests from `message_start`/`message_delta`, subagent requests from the subagent transcript (0.06–5.8 s late — the flush window waits), closing `result.modelUsage`; `result.usage` is never used as a total (control: a fixture where `result.usage` ≠ sum → totals come from `modelUsage`).
  2. Compaction residual: attributed only when every other request and failed attempt reconciles; a closing-aggregate residual beside an unreconciled failed attempt stays `unexplained` (O10); control: with the attempt reconciled → attributed; the residual must sit under declared keys (S-7; an undeclared key → `MODEL_UNATTESTED`, a declared auxiliary role's usage → accepted and attested by aggregate — F-O10-14a/b, F-O10-15/16).
  3. Estimate rule **as §13.3**: provisional = the same agent's previous request + new content chars/3 × ≥2 for tool results; control: a fixture where the "class's highest observed" rule would under-estimate (probe 9: 16 of 39 Codex main requests) shows the plan rule above actual; late usage replaces the provisional figure; a killed-in-flight request stays provisional.
  4. Caps and stop on actor episodes (the mechanism is WP-02's, proven there on a non-actor call; here its actor integration): an episode exceeding its token cap is stopped by the supervisor's stop, its process tree frozen, rescanned, swept, killed and verified by pid+start time, overshoot recorded (O7); a capped Claude episode that compacts carries an estimate per `compact_boundary` marker, is stopped by the compaction cap, overshoot reported as estimated (O7); a Codex episode looping on compaction (fault injector) is stopped by the compaction cap; `--max-budget-usd` and `--max-turns` are set as secondary bounds (control: an episode stopped by the host's own budget stop is recorded as such, with the 35% overshoot class re-measured).
  5. Attempts **as §13.3**: one Claude transcript `api-request` record per HTTP attempt, retries and silent fallbacks included; Codex retries from `codex_core::responses_retry` warnings and otel `attempt`; a Codex warm-up request per thread (root and child) recorded with no output (control: a thread without a warm-up record → attempt coverage `unknown`, never silently complete).
  6. A stage with no wall time is rejected at close; an **accepted** result without an observed model is rejected (attestation is for accepted results); a failed or interrupted attempt keeps an explicit `failed`/`unknown` status with its accounting retained (provisional or unresolved, §13.3) and never blocks the close (O10; N#1r4).
  7. Classes: after the rehearsal, `classes.json` carries n and p95 per class with the provisional flag cleared only when n ≥ the declared minimum (control: a class below the minimum stays provisional and the supervisor refuses its broad dispatch).
  8. Live: one capped episode per host with a child and a forced compaction reconciles its channels (§14 check 6); the Claude overshoot class (72,086 under 48,000 in the probe) is re-measured and reported.
- **Verification point.** 27 ported controls + 15 mutants from the probe prototypes (golden/replay), then the two live capped episodes.
- **Review gate.** X; the reviewer gets §13.2–13.3, the probe 9 `RESULTS.md`, and the code; the packet states that the limit shapes were never observed live.
- **Size.** M (≈600 lines; the supervisor, breaker, monitor and stop are WP-02's).
- **Main risk.** The stop guarantee is "no request sent after the stop takes effect", not a ceiling (§13.2); detached daemons escape a tree kill and are outside it — reported, never claimed.

### WP-19 S8 cases, calibration, configurations (B/A/R/A−i/R−i), scoring, acceptance, artifact validation (§8.4–§8.8)

- **Goal.** Case authoring **as §8.5** (gpt-6-astra authors six cases per change from the behavior
  contract and evidence, never the proposed wording; calibration responses per failure dimension;
  claude-opus-5-5 labels blind; a leakage review), four strata seats from observed usage (S1) else
  `seats.json`, the configurations **as §8.6** with R built once per run by the reconstruction route
  (ports `materialize.py`, `r_schema.json`, `build_rminus.py`, `hc_validate.py`) and A/A−i per item,
  a **versioned manifest** whose cell is `(configuration, case, stratum)` and whose episodes are its
  repetitions (`BenchManifest/v2`; v1 artifacts readable, unable to satisfy v2 acceptance — F24),
  scoring through the model-call gate with per-case validated calibration and per-dimension scores
  **as §8.7**, the acceptance rules **as §8.7** with adaptive and retry slots bound into the manifest,
  and artifact validation **as §8.8** of every proposed artifact set in a scratch worktree.
- **Design.** §8.4–§8.8, §2 (six cases × two reps × four strata × five configurations for core), §16
  (ratios measured), O7 plants.
- **Files.** author-side: `benchmarks/cases.py` (new), `benchmarks/configs.py` (new; R, R−i, A, A−i),
  `benchmarks/reconstruct.py` (new; ports the reconstruction scripts), `benchmarks/judge.py` (change:
  gate-routed scoring through `runlib/dispatch.py`, per-case calibration validity, per-dimension
  scores, `collapse` PARTIAL→MISS kept; the **calibration barrier** kept — today `calibrate` runs
  every calibration case and `score_run` returns without scores unless `calibration_valid` holds
  for the whole batch — and adapted to per case, N#5r3, N#6r4), `benchmarks/manifest.py` (change: `BenchManifest/v2` — cell
  key `configuration|case|stratum`, episode key `cell|rep|slot ∈ {base, adaptive, retry}`, strata
  `claude-main|claude-subagent|codex-main|codex-subagent`, a mapping function from v1 keys for
  reading old artifacts; `ROLES`/`GUARDS` kept for the shared regression battery's own
  classification), `benchmarks/calibration.toml` (per-case, generated per run into the run dir — the
  committed file stays the fixture), `benchmarks/absence.py` (change: the semantic `ask` routed
  through `runlib/dispatch.py` with `--json-schema`, parsing **only** the gate-validated
  `structured_output`; `parse_verdict`'s brace extraction and `dispatch_problem`'s old receipt check
  removed; the lexical layer and the positive control kept — F22), `benchmarks/compare.py` (reused:
  denominator rule), `benchmarks/artifacts.py` (new; scratch worktree + the full §8.8 command set,
  `GIT_DIR` scrubbed), `benchmarks/evaluator.py` (new; the frozen closure).
- **Frozen evaluator (settled S-13, §6; F23).** The evaluator is the **closure** of everything that
  decides whether an episode is valid evidence: `benchmarks/` dispatch, scoring, manifest and
  validation code; `session-distill/distill.py` and `runlib/` (the driver, the gate, the supervisor);
  the hermetic runners (`wrappers/claude-run.sh` and `wrappers/codex-run.sh` with their helpers);
  the scorers' packets and schemas; the item identities. `evaluator.py` hashes that closure, copies
  it into `test/evaluator/` once per run, and every episode, score and validation runs **from the
  frozen copy**, never from a treatment tree. A proposed change to any closure member is exercised
  only as the subject executor against the frozen oracle and fixtures; a change whose intended
  behaviour alters the experiment's own acceptance semantics cannot be judged in the run that
  proposes it — it is recorded as deferred to a new evaluator revision and its own rehearsal.
  Control: a treatment tree that edits `benchmarks/judge.py`, and one that edits
  `wrappers/claude-run.sh`, each run with the frozen closure (its hash asserted unchanged before and
  after), never its own.
- **Kept interfaces.** The pure parsers that `benchmarks/tier/live.py` and `benchmarks/tier/usage.py`
  import stay importable with their signatures; old benchmark artifacts stay readable through the v1
  mapping but cannot satisfy the new acceptance contract. The tier experiments are not redesigned here.
- **Dependencies.** WP-16, WP-17, WP-18, WP-07 (units for R), WP-12 (proposals and the sequencing
  checker), WP-02/03/04 (seats).
- **Artifacts and interfaces.** `test/manifest.json` (v2), `test/cases/<item>/<case>.json` `{kind ∈
  {positive, positive_keyword_stripped, non_trigger, non_trigger_competing_value, regression}, fixture,
  completion_mode, postcondition|null, hit_criterion, naive_miss, key_terms[], diagnosis}`,
  `test/calibration/<item>.json` `{case → {responses[], labels{author, blind}, valid}}`,
  `test/results.json` `{cell → {episodes[], passes, denominator, per_dimension{}, comparable, verdict}}`,
  `test/attribution.json` `{item → {accepted_on_A, shows_improvement, A_vs_Ai, R_vs_Ri,
  unresolved_attribution}}`, `test/artifact-gate.json` (per item, per §8.8 command, exit status and
  output hash), `configs/R/{library, obligation_map, requirement_map, distance_report}`,
  `test/evaluator/{closure.json, …}`.
- **Done when.**
  1. Case rules **as §8.5**: the six case kinds are present per item (control: a missing keyword-stripped positive → `CASE_SET_INCOMPLETE`); a wording-only test is refused (`CASE_WORDING_ONLY`); an action case without a postcondition where an artifact could show the action is refused; a leaked diagnosis without its key terms fails the leakage review by name (the review is a model judgment — live in the rehearsal, F27); a mislabelled calibration response invalidates the case's calibration, the author reworks it once, and a still-invalid slot leaves its cells `invalid` and the item incompletely tested (O7; the blind labeller must catch a planted mislabel live).
  2. Withholding arms: a contaminated A−i/R−i (the removed behaviour still instructed in other words) is caught by `absence.py`'s semantic layer **through the gate**, whose positive control (a section known to carry the behaviour in other words) must fire or the whole absence verdict is void (O7); controls (F22): a prose-wrapped JSON verdict cannot establish absence (`SCHEMA_INVALID`), a context-invalid receipt cannot (`CONTEXT_UNDECLARED`), and a stub answering ABSENT without a dispatch cannot (no accepted call → no verdict).
  3. R **as §8.6**: built once per run after the core freeze (control: `configs.build_R` refuses while any core item lacks its S7b record); its authoring call is not a view-window call — ≈152k input by budget, ≈136k measured in probe 7 — and is bounded only by its seat's context capacity, never by the 120k window rule (the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`; N#0r5); returned as a composition over unit ids, gated by code (call id, every referenced unit exists, each edit applies exactly once, set accounting over operative units); its two maps present; validation split by kind (code for verbatim-kept units on unchanged routes; claude-opus-5-5 for changed, moved, dropped rows, the requirement map, and a sample of kept rows, in shards; a failing map reworked once, a still-failing R invalid → every core item `untested`, not eligible); its distance from B reported (units kept/dropped, 1,551/1,553 measured class); an R−i that does not isolate the item (entanglement, probe 7's case) is marked `unresolved_attribution` and the validator receives R's requirement-map row (control: without the row the validator's verdict differs — asserted on the probe fixture); claude-opus-5-5 confirms A−i and R−i differ from A and R only in item i and code confirms the changed-file set.
  4. Acceptance **as §8.7**: an episode passes by the dimensions its case type requires; a cell starts with two episodes: 2/2 → pass, 0/2 → fail, 1/2 → two more from its pre-bound adaptive slots then 3/4 or 4/4 → pass else fail; an unscored, budget-stopped, or invalid episode is re-run once, still not scorable → `invalid`; an item is accepted on A per the stratum rule, shows improvement when B fails a positive cell, and any invalid cell makes it `incompletely tested`; failures in B, A−i, R−i are outcomes. Controls: each branch flipped fails by name; a reserve of zero → `not_done` rather than a verdict; a cell with one repetition is **incomplete**, never a verdict (F26).
  5. Denominators and identity (F24): a cell short of its declared reps is `not comparable` and never counts as a regression (`compare.py` rule); control: a cell that lost one response to `defect:seat` is excluded from the regression count; two otherwise-identical episodes in the `claude-main` and `claude-subagent` strata have distinct cell keys (control: the stratum removed from the key → `KEY_COLLISION`); a v1 artifact reads through the mapping and is refused by v2 acceptance (control).
  6. Item kinds carried through their arms: one personal, one reduce, one re-deliver, one route-carried, one executable-carried core item, and **two** author-side gate changes (one completes confirmation, application and executor verification — F-O8-10e; one fails F and returns — F-O8-11; N#3) each produce a full v2 matrix (every cell at the contract scale) and an artifact-gate result (O7 and O8 share these seven fixtures; golden matrix here, **live at the contract scale in the rehearsal**, WP-23).
  7. Artifact validation **as §8.8**: every proposed artifact set is built into a scratch worktree and `gates/emit-mirrors.py`, `./gates/check-parity.sh`, `gates/check-lexicon.py`, `gates/check-package.sh`, the translation-presence check, and the author-side negative controls run there, each result bound into the item's results; negative controls (F25): a missing Korean artifact for user-facing text, a stale mirror (`codex/` not re-emitted), a shipped helper omitted from `files[]`, an author-side gate change whose own control cannot fire, and a repo path added to shipped prose — each caught in the scratch tree by name; the scratch worktree never touches the real index (asserted by `git status --porcelain` on the checkout before/after).
  8. Calibration barrier **as §8.7** (N#5r3): before any score of a case is accepted, the scoring seat classifies that case's calibration responses correctly through the gate (`calibrate` per case, `calibration_valid`; a calibration call that fails the gate is `unproven`, never a label — kept from today's `calibrate`); negative: the author's and the blind labeller's labels agree, but the scoring seat misclassifies one of the case's calibration responses → no score of that case is accepted and the case is `unscored`; the case's unscored episodes are **re-run once through their pre-bound retry slots** (done-when 4; §8.7 — no scoring-only retry exists), and calibration and scoring run again on the re-run episodes; success → scored; failure persisting through the retry → the case's cells `invalid`, the item incompletely tested (N#2r4, N#1r5; controls: failure then success → scored, each re-run episode recorded under its retry slot in the manifest; failure persisting → `invalid`, no third episode; the same responses with the scoring seat correct → scored on the first pass; a batch with one failing case still scores the other cases, which is the per-case adaptation).
  9. Development smoke (**not evidence**, realization `smoke`): one core item, one case per kind, four strata, two reps, five configurations plus the 13 regression scenarios on one stratum at two reps and three configurations — `(6·4·2·5 + 13·1·2·3) = 318` episodes — to exercise authoring, calibration, R, scoring, acceptance and artifact validation live; its usage and durations seed the supervisor's calibration tranche; it is excluded from every rehearsal and production figure (F26).
- **Verification point.** Golden matrix with fake hosts (bijection, acceptance, denominators, evaluator closure), then the smoke.
- **Review gate.** X on the scoring/acceptance/attribution code, the evaluator closure, and the case-authoring packets; O on the six case kinds (they define what "tested" means for the owner).
- **Size.** XL (≈2,000 lines).
- **Main risk.** Volume: the contract scale is the rehearsal's largest spend (§8.2) and the production run's; adaptive slots and the breaker keep it resumable, and the first measured run decides whether the scale fits the usage windows (§5).

### WP-20 S9 render, S9b Korean review, S10 decision parsing, adjudication, S10b confirmation (§9, §10.1–10.4)

- **Goal.** `distill.py render` → `review.ko.v<n>.md` from the **complete accounted population as
  §9** (every candidate including lifecycle candidates, every rejected finding, every quarantined
  or failed item; non-findings counted by reason in the coverage section and listed with locators
  in an appendix; every O6 field per row plus kind, diagnosis, units with delivery evidence, both
  judges, S7b, the test table, and a `결정:` line; the §7.5 total order grouped by status; the §9
  header; counts reconciled with the census and S4); `distill.py review-korean` (gpt-6-astra/high,
  per row: faithful to its English payload and plain) with **S7's one permitted regeneration** of a
  failing row and the persistent visible "번역 검토 실패" mark on a row still failing;
  `distill.py parse-decisions` reading the owner's `결정:` lines into `approvals.jsonl` and
  `adjudications.jsonl` **exactly as §10.1**; `distill.py adjudicate` (§10.2: recompute the §6.4
  derivations with the adjudicated values, run the newly admitted candidates through S7, S7b and
  S8 in a second pass of the same run, and render a new review version); eligibility **as §10.4**;
  `distill.py confirm` **as §10.3**.
- **Design.** §9, §10.1–§10.4, §13.4 (owner overturn rate, review time), §7.5, O6, O8.
- **Files.** author-side: `session-distill/runlib/stage_render.py`, `stage_review_korean.py`,
  `stage_decisions.py`, `stage_adjudicate.py`, `stage_confirm.py`, `schemas/s9b.schema.json`,
  `packets/s9b.md`, `grammar/decisions.py` (the decision grammar as one parser with `--self-test`),
  `gates/control-audit.py` `SUBJECTS`. `bundle.py` and `bundle_final.py` stay until WP-22.
- **Dependencies.** WP-12 (proposals, S7b, the sequencing checker), WP-19, WP-02, WP-04, WP-09
  (the partition), WP-10 (derivations for adjudication).
- **Review and decision files (settled S-11, §6).** The design makes each `review.ko.v<n>.md` an
  immutable render (§9) yet has the owner write `결정:` lines per row (§10.1). The render stays
  immutable; beside it the renderer writes `decisions.ko.v<n>.md`, a copy that carries the render's
  hash in its header and whose only editable parts are the `결정:` lines, their notes, `판정` values
  and `keep 해제:` lines. The parser requires every other byte to equal the render and refuses the
  file by line number otherwise; approvals carry §10.1's `review_version_sha` (the render) and the
  plan adds `decision_input_sha` (the edited copy). The owner still reads and decides in one Korean
  file.
- **Artifacts and interfaces.** `review.ko.v<n>.md` (every row carries its `item_id`, its `item_sha`,
  and a `payload_sha256` of its English source); `decisions.ko.v<n>.md`; `review-s9b.v<n>.json`
  `{row → {verdict, regenerated: bool, mark: bool}}`; `approvals.jsonl` **as §10.1** (`approval_id`
  code-generated, `item_id`, `item_sha`, `review_version_sha`, `configuration_sha`, `manifest_sha`,
  `results_sha`, `decision`, `superseded_keeps`, `note`, `at`) plus the plan's `decision_input_sha`;
  `adjudications.jsonl` **as §10.1**; `confirm/<pass>/{manifest, results, confirmation.json}` with the
  confirmation record **as §10.3** (approval ids bound to F's `configuration_sha` and the confirmation
  manifest and results hashes).
- **Done when.**
  1. Population (F12, N#12): the render population is WP-09's `population.json` — every candidate id including the lifecycle intake (legacy entries, due decisions and pending interventions on placed entries, which have no event row), every rejected finding, every quarantined or failed item, and every located non-finding — each appearing exactly once, with the event-to-candidate membership printed per row (set accounting; O6 "a candidate missing from the review" → `RENDER_INCOMPLETE`); controls: a missing rejected finding, a missing failed item, a missing quarantined item, a missing non-finding appendix row, a missing proposal, **a missing eventless legacy candidate**, and **a missing pending intervention on a placed entry** each → `RENDER_INCOMPLETE` naming the id; an item that disappeared before proposal generation is caught (the population is `population.json`, never `proposals.json`); the counts line reconciles with the census and S4 (O6; control: a count edited by one → `COUNTS_DIVERGE`); the order is total and stable across re-renders (byte-identical for identical inputs); every row carries every O6 field (control: a row without a falsifier → structural refusal).
  2. S9b (F13): a row whose Korean drops a fact (fixture: the English payload names an exception the Korean omits) is flagged by the reviewer (O6 — live); a flagged row is regenerated once by S7's seat and re-reviewed; a row failing twice carries the visible "번역 검토 실패" mark in the next render and is never withheld or vetoed (control: the mark absent on a twice-failing row → `MARK_MISSING`; a row withheld → `RENDER_INCOMPLETE`); the golden counterpart asserts the packet carries both texts and the hash.
  3. Decision copy and grammar: an edit outside the editable parts (a changed payload word) is refused by line number; an unedited copy parses as every row `undecided`; control: the same edit inside a note is accepted. Each of the five verbs and `keep 해제:` parses with its arguments; an item without an approval row is `undecided` and never applied (O8); an ambiguous line is refused by line number, never guessed (the LLM/capability rule); an item whose `item_sha` changed after rendering is refused until decided again (`DECISION_STALE`; F15); `--self-test` covers every grammar branch and a malformed line.
  4. Approval bindings (F15): `approvals.jsonl` rows carry every §10.1 field (control: a row missing `configuration_sha` → `SCHEMA_INVALID`); a `수정` naming S7b's alternative adopts it (control); a `reduce`/`merge` over a `keep` record without `keep 해제: <record id>` → `KEEP_GUARDED`.
  5. Adjudication **as §10.2** (F13): `adjudicate` recomputes the §6.4 derivations with the adjudicated values; a candidate that becomes admitted goes through S7, S7b and S8 in a second pass of the same run and appears in a new review version; fixtures: a newly admitted core item (tested on B, A and A−i in this run; `incubating` with reason "awaiting R"; not eligible) and a newly admitted personal item (proceeds to F) — each verified by the new review version's rows and the ledger's reason.
  6. S10b **as §10.3** (F15, F17): F = B plus every approved core, personal and author intervention; the confirmation manifest covers, in all four strata, each approved item's six cases and interaction cases, the shared regressions, and the §8.8 artifact validation (control: a stratum or an interaction case missing → `SET_MISMATCH`); B's results are reused from S8 **only when** B's configuration manifest and the cases are unchanged (control: one case byte changed → B reruns; the manifest changed → B reruns); the confirmation record binds the approval ids to F's `configuration_sha` and the confirmation manifest and results hashes (controls: stale `item_sha`, stale case bytes, stale `configuration_sha`, stale `results_sha` → `CONFIRMATION_UNBOUND` by field); the exact approved operation order is re-validated with WP-12's sequencing checker before confirmation (control: full set valid, approved subset invalid → the subset returned, not confirmed); an item that fails returns to the owner in a new review version with the new results, F is rebuilt without it, and confirmation repeats at most once per approved item (O8; the planted author-side failure, F-O8-11).
  7. Eligibility **as §10.4**: each condition is a named check and an ineligible item is returned with the failing condition named (control: each condition broken one at a time → named); ledger-only dispositions skip S8 and are not part of F.
  8. Owner overturn rate and review time are computed from frozen first-render proposals (control: a wording-only change is reported apart, not as an overturn).
  9. Contract fidelity: the approval, adjudication and confirmation schemas' required sets equal §10.1 and §10.3's lists (self-test against the copied, cited lists); the render's row fields equal §9's.
- **Verification point.** Golden (rendering, grammar, adjudication, S10b set logic) + live S9b over three rows incl. one regeneration.
- **Review gate.** X on the grammar, the bindings and the S10b logic; O reads one rendered `review.ko.v1.md` from the rehearsal and confirms the decision lines are usable (this is the owner's own interface).
- **Size.** XL (≈1,300 lines).
- **Main risk.** The Korean file drifting from its English payload; the per-row payload hash and S9b are the two checks, and S9b has a live plant.

### WP-21 S11 apply, delivery verification, recovery, S12 close and follow-up seeding (§10.5–§10.6, §11, §12.4, §13.4)

- **Goal.** `distill.py apply` **as §10.5**: the live configuration manifest (every §6.1 layer,
  dependencies, author-side tree hashes) recomputed and compared with F's manifest minus the
  approved interventions — any difference is drift and stops the affected items; F's order of
  operations, with operations sharing a target chained (each expecting the previous operation's
  after-hash as its before-hash) and each re-checking its target; the write-ahead side-effect
  journal (a `planned` record with durable operation id, target, expected before-hash and intended
  after-hash, fsynced before each effect; `done` after; commits carrying the operation id;
  installation idempotent and always verified); every writer's destination resolved from
  `run.json.destinations` and asserted inside its declared root before the first `planned` record
  (`DESTINATION_OUTSIDE_ROOT`; N#4); core: one commit per item on a branch naming item
  and approval ids, then `gates/emit-mirrors.py` and the parity umbrella; personal: the approved
  patch with an application receipt; author: the gate change with its negative control; delivery
  verification **as §10.5** at every surface's levels of §6.3; recovery **as §10.6**; `distill.py
  close`: ledger (schema 2), coverage state, version registry and nudge projection in one journaled
  close (nudge last), `run-record.json` with the §13.4 measures, dated records, the **occasion index
  of §7.1**, the expected-observation resolutions **as §11** appended to the ledger's
  `decisions[].expected_observation.resolutions[]`, and the `No change` path.
- **Design.** §10.5, §10.6, §11, §7.1 (occasion index), §12.3–§12.4, §13.1, §13.4, O8, O9, O10, "No change".
- **Files.** author-side: `session-distill/runlib/stage_apply.py`, `journal.py`, `delivery.py`,
  `recovery.py`, `stage_close.py`, `measures.py`, `exposure.py` (the §11 predicate as a table-driven
  function with a generated fixture per rule), `occasion_index.py`, `session-distill/plain-asks.py`
  (change: counting function behind the §11 adapter; Codex sources reported unsupported),
  `gates/control-audit.py` `SUBJECTS`. Writes it performs at runtime: `design/session-distill/ledger.json`,
  `versions.json`, `session-distill/coverage.json`, `~/.local/share/agent-bios/session-distill-state.json`
  (through `update-state.py`), one git commit per applied item (the hook runs the umbrella — minutes
  per commit, budgeted in §8), dated records `design/session-distill/<YYYY-MM-DD>T<HHMM>--<sha>--run-<id>.md`.
- **Dependencies.** WP-13, WP-14, WP-15, WP-20 (approvals, confirmation record, the sequencing
  checker from WP-12), WP-05 (next-run intake), WP-08 (observation instances), WP-06 (search for the
  occasion index).
- **Artifacts and interfaces.** `journal.jsonl` **as §10.5** (`planned` and `done` records with the
  durable operation id, target, expected before-hash, intended after-hash; the plan adds `item_id`,
  `approval_id` and `commit|null` on `done`); `applied.jsonl`; `destinations.resolved.json` `[{class, writer, path, root, inside}]` (N#4);
  `delivery.json` `{item_id, unit →
  {level_reached, verified ∈ {yes, failed, unverified}, evidence}}`; `run-record.json` (§13.4 measures
  with denominators; usage totals in three states; coverage per source, accounted and fully read
  apart; S1's unknown-independence share; R distance); `occasion_index.json` (per unit: whether the
  full-source search with the unit's trigger terms matched any in-window record, and the window's
  coverage basis); `expected_observations.jsonl` (seeds for the next run's S3, WP-01's schema).
- **Done when.**
  1. Global ops: a delete passes with its approval row; a merge without `faithful_merge: yes` and without an override is refused; the O10 "deletion plus an unrelated shorter line" passes WP-14's gate but is refused by S11 without a merge judgment (`GLOBAL_OP_UNJUDGED`); an added global line is refused before the gate is even reached.
  2. Order and drift (F16, F17): the exact approved F operation order is re-validated with the sequencing checker before application (control: a route-and-carrier pair approved as two items with no valid order → returned); drift compares the recomputed live manifest with F's manifest minus the approved interventions over every §6.1 layer, dependencies and author-side tree hashes (control: a dependency hash changed → the affected items stop for rebuild, retest and re-confirmation; a layer outside any target changed → likewise; O8 target drift and untargeted drift each refused by name); two operations on one target chain by hash (control: the second operation's before-hash equals the first's after-hash; a run where the first did not apply → the second refuses `TARGET_MISMATCH`).
  3. Journal durability (F16, N#16): no effect precedes a **successful fsync** of its `planned` record (control: a fault injected after the write and before fsync — the target's before-hash shows no effect, whatever the record's fate); recovery handles the pre-fsync record in every state it can be found in — absent, complete, or torn (records are length-framed with a trailing hash, so a torn record is detected, logged and ignored) — and decides by the target's before/after hashes, never by the record's presence; loss of an unsynced record is exercised only through an explicit storage-failure injector (a filesystem fake that drops unsynced writes), never assumed from a process crash; commits carry the operation id in the message (control: a commit without it → `COMMIT_UNBOUND`); a crash **after the commit and before `done`** recovers by finding the operation id in the branch log and records `done` without a second effect (control: the replay makes no second commit); installation re-runs install and verify idempotently.
  4. Delivery **as §10.5** at every surface's levels (§6.3), under the fixture environment of done-when 11 (never the owner's homes — N#1r3): `bash install.sh install --non-interactive`, `bash install.sh verify`, then fresh activated sessions through the §8.2 adapter; a rule exposed; a guide's pointer exposed, router read and guide read in a fixture where its trigger applies; a skill listed and invoked; a hook registered and fired on a probe event; a native layer identified and loaded; an executable's effective path pointing at the applied artifact's hash with the route-specific executor check rerun from the installed path; create/edit traced from canonical source through the catalog's origin mapping into the compiled output; delete/merge verified by absence (and the merged unit present); route verified by the route entry and reach; author-side changes verified in the checkout by the §8.3 executor contract against the approved tree hash with the gate's violation and clean controls rerun; **controls as §10.5**: a selected-but-unused unit, an emitted-but-unavailable unit, and a fresh pin paired with an invocation of the old executable version must each fail (O8); claimed child reach verified by §8.3's controlled delegation with the item's operation-specific contrast against its B state and the child's version-bound context record naming the applied artifact — a failed check sets delivery `failed` and returns the item (O8), never narrowing the claim.
  5. Recovery **as §10.6**: crashes injected before an effect, after an effect but before `done`, and during installation each recover (after-hash → `done`; before-hash → not done; else drift, stop the item; commits by operation id in the branch log; installation by re-running install and verify), every completed operation is recorded in the ledger with its delivery state, replay skips `done`, and the next review lists every `applied` item without verified delivery (O8); the installation case carries `begun_by_installer_digest` as WP-15 defines it.
  6. Close: ledger, coverage, versions, and nudge update in one journaled close with the nudge last (control: a crash injected before the nudge write leaves the previous nudge file and a recoverable journal); every stage has wall time and every **accepted** call an observed model, else the close fails; failed and interrupted attempts close with explicit `failed`/`unknown` status and retained accounting (`unresolved_count` in the run record), and the **recovery close is never blocked** by an unattested failed delivery call — completed effects are recorded as §10.6 requires (O10; N#1r4). Mixed-run control: one unattested failed attempt (killed before any response), a successful attested retry, and an applied effect whose delivery call failed unattested → the close succeeds, the run record lists the failed attempt with model `unknown` and provisional usage, the retry attested, the effect recorded `applied` with delivery `failed` and the item returned (O8); the run record's measures carry denominators or `unknown` (control: a measure with a zero denominator prints `unknown`, never 0.0); a targeted run's close leaves periodic coverage unchanged (F04).
  7. Follow-up **as §11**: the window resolution per item (not observed / observed / no occasion / pending) is derived by code from WP-08's instances with the §11 precedence — the O9 fixtures of WP-08 run here end to end — and appended to `decisions[].expected_observation.resolutions[]` (§12.1); exposure by the table-driven §11 predicate with a generated fixture per rule (O9): installer change with the old installer on the receipt → not exposed; removed wrapper resolving to an older carrier → not exposed; no resolution recorded → `exposure_unknown`; compiler change with the old compiler digest → not exposed; personal change without a loading record → `exposure_unknown`; recovery begun by the old installer → `exposure_unknown`; pre-receipt transaction → `exposure_unknown`; a pending intervention on a placed entry carried into the next run's intake and resolved there (two scratch runs). Each expected verdict flipped fails by fixture name; the predicate's branch set equals §11's. The **seeded follow-up path runs live end to end in RH-1** (N#3r3; WP-08 done-when 5): the live instances' resolutions and exposure are asserted on the rendered rows and on the ledger's `resolutions[]`, with the golden fixtures keeping precedence and persistence.
  8. Occasion index (F05, N#17): per unit, the search match and basis are recorded at close; the hint arises **as §7.1** from three **chronologically consecutive** windows each of basis `source` and without a match — a window of basis `view` or `incomplete` in the sequence is neither counted nor skipped: it breaks the sequence and the count restarts at the next source-basis window (the design licenses no filtering; the plan's earlier "resets nothing" reading is withdrawn). Controls (scratch runs): source/source/source without a match → hint; source/source/view/source → no hint; source/view/source/source/source → hint after the last three; a match in the third window → no hint.
  9. Legacy carry: S3-03's owner-approved incubation is carried through S12 (unavailable provenance preserved, observation and expiry stored) and re-enters a later run's intake at its expiry (O5; two scratch runs).
  10. `No change` (F28): a **nonempty, source-complete** clean window whose correct result is no proposals runs S0–S12, applies nothing, and the run record reports it — live on a real window in the rehearsal (control: the same window with one planted candidate produces one proposal); the credit requires both predicates and **no proposal of any kind** — a window whose only proposal is personal is not credited (F-NC-02, N#4r5); the empty-source case stays F-O1-06.
  11. Live, under the destination manifest (N#4): one applied item end-to-end in a **fixture-owned clone** of the checkout (`git clone` of HEAD under the fixture root — never the owner's checkout, and never a worktree sharing its `.git`) with every class of `run.json.destinations` resolved into fixture roots: `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `ZDOTDIR`, `AGENT_BIOS_STATE_DIR`, `AGENT_BIOS_SESSION_DISTILL_STATE` and the other `compose/instructions_install.py` overrides, exported to every writer (`install.sh`, `compose/instructions_install.py`, `launch/shell_integration.py`, `update-state.py`, the git operations, the close); a deletion in a test guide, its commit passing the hook, delivery verified by a fresh pin from the fixture install; the owner's real destination set hashed before and after and equal (the guard of WP-23 done-when 7).
  12. Contract fidelity: the journal record's required set equals §10.5's; the recovery branch set equals §10.6's; the exposure predicate's branches equal §11's.
  13. Preservation end to end (N#13): one claim revision with a deliberately distinct fact, interpretation, uncertainty and redacted quotation, referenced by a proposal, is carried through S9's render and S12's close (schema 2 `decisions[]` with the claim and evidence ids); the rendered row's values and the ledger's referenced revision and evidence resolve to the same four components as the stored claim (equality, not field presence); controls: each component mutated independently in the stored claim after rendering → the render's `payload_sha256` check fails naming the row and the ledger's reference still resolves to the unmutated revision (immutability), per component.
  14. Destinations (N#4, N#4r3): `apply` writes `destinations.resolved.json` from the environment it hands each writer, before any effect, and refuses on any `inside == false`. Two controls, kept apart: a **missing required override** (`CODEX_HOME` or `AGENT_BIOS_SESSION_DISTILL_STATE` unset) → `OVERRIDE_MISSING` before any `planned` record, because an unset override resolves through a fallback the run did not declare — even though `install.sh`'s and `update-state.py`'s fallbacks land inside the fixture `HOME`; an **actual escape** (`AGENT_BIOS_SESSION_DISTILL_STATE` set to a path under a second fixture root outside the declared one; a resolver fixture whose fallback is out of root) → `DESTINATION_OUTSIDE_ROOT` before any effect, the escape target's hash equal before and after (it is a fixture path, never an owner path). The resolved set covers every writer named in done-when 11 (control: a writer added without a destination class → `DESTINATION_UNDECLARED` in the self-test).
- **Verification point.** Generated fixtures + two- and three-run scratch sequences + the live applied item.
- **Review gate.** X on apply/recovery/close (irreversible effects; the reviewer compares the journal and drift code with §10.5–§10.6); O on the first real application (the owner's library).
- **Size.** XL (≈1,900 lines).
- **Main risk.** Commit-per-item cost (the umbrella is ≈4.5 min per commit): ten applied items ≈ 45 min; recorded as S11 duration, not optimised away (the hook is the author-side gate).

### WP-22 Preset, runbook guide, docs, mirrors, decisions, map, atomic cutover (§15 tail)

- **Goal.** `[presets.session-distill]` points at the new runbook and its review method moves to
  Judge B's seat; `claude/guides/session-distill-workflow.md` Goal replaced by the purpose record,
  runbook S0–S12, and the §7.4 placement contract **generated from WP-12's tables** (a marked block
  emitted by `session-distill/emit-placement.py`, whose `--check` leg fails a hand edit — the
  `emit-lexicon.py` pattern; F32); `ko/` translation; mirrors re-emitted; the **atomic cutover**:
  the legacy entrypoints and `out/BUNDLE.*` deleted in the same commit as the runbook sections
  naming them are replaced (F35); `DEPENDENCIES.md`, `CONTRIBUTING.md` layout row,
  `docs/instructions.md` guide inventory, `IMPLEMENTATION_MAP.html`, ontology re-extraction,
  decision records for every alternative this plan closes.
- **Design.** §15 (reuse map rows for the preset, the guide, `PLACEMENT-FRAMEWORK.md`, `out/BUNDLE.*`), §7.4.
- **Files.** shipped: `launch/agent-launch.toml` (`[presets.session-distill]`: mission text, `review`
  → `gpt-6-astra/xhigh` via `codex-run --profile hermetic`; `audience = "author"` kept so the prose
  scan tolerates author paths), `claude/guides/session-distill-workflow.md` (+ `ko/claude/guides/`,
  `codex/`, `ko/codex/` via `gates/emit-mirrors.py`; frontmatter keeps `audience: author` and the
  sentence `Requires an agent-bios checkout` so `compose/assemble.py::author_only` withholds it),
  `DEPENDENCIES.md`, `docs/instructions.md`, `CONTRIBUTING.md`. author-side: `benchmarks/README.md`
  (N#4r4: the v2 manifest cell `(configuration, case, stratum)` and its episodes replace the
  (item, obligation, scenario role, arm, host, repetition) identity its "What a run evidences"
  section documents; the per-case calibration barrier replaces the batch-wide one its judge
  paragraph describes; the scope of retained legacy benchmark behaviour — the tier experiments and
  the v1 reader — stated; historical measurements kept as dated evidence), `benchmarks/EXTENDING.md`
  (N#4r4: "Promoting a finding" no longer says "extend or add a global rule" — the global file takes
  deletions and merges only (WP-14, §7.4) — and routes a promotion to a guide trigger, skill, hook
  or session-level injection through the placement contract), `session-distill/emit-placement.py`
  (new; `--check` in the umbrella), `gates/check-parity.sh` (the leg line), the review-routing golden
  (regenerated deliberately; the diff is the review subject), `IMPLEMENTATION_MAP.html`,
  `learn/redact.py` (docstring only, N#8r3), `gates/check-parity.sh` (the redaction-leg comment,
  and the ledger leg switched from `runlib/ledger.py` to `merge-ledger.py --check`, N#7r3),
  `ontology/instances/graph.json` + `extract.py` + `check-ontology.py`, `decisions/decisions.jsonl`
  via `record-decision.py` (one record per closed alternative: the S-n readings once the owner
  settles them, `.js` stage scripts dropped, `BUNDLE.*` replaced, per-run out directories, the
  supervisor's placement), `compose/domains.json` unchanged (tier `infra`); deletions:
  `session-distill/digest.py`, `batch.py`, `screen-claude.js`, `screen-codex.py`, `collect.py`,
  `consolidate.js`, `bundle.py`, `bundle_final.py`, `out/BUNDLE.json`, `out/BUNDLE.md`, and the
  `.gitignore` legacy patterns.
- **Dependencies.** Every other WP's interfaces frozen (last in order); P6 for the seats named in the preset.
- **Done when.**
  1. `python3 gates/emit-mirrors.py --check`, `./gates/check-parity.sh` (incl. the review-routing golden after regeneration, `check_parity.py --only distill_hub` — re-read the leg before editing the preset, and the new `emit-placement.py --check` leg), `gates/check-package.sh` (prose scan: no author path outside `audience: author` files), `gates/check-lexicon.py` (no deprecated token; no count restated in prose that `check-ontology.py` would hold — numbers go to the run record, not the guide), `ontology/check-ontology.py`, `launch/check-prompting-targets.sh` all exit 0.
  2. `compose/assemble.py` withholds the runbook from a packaged user (control: build a variant for a non-author audience and assert the guide is absent) while the preset still resolves it for the author (control: `agent-launch --config launch/agent-launch.toml` renders the distill contract naming Judge B's seat and the hermetic adapter path — options before the positional host, per the AGENTS.md trap).
  3. Placement authority (F32, N#10): the runbook's contract block equals `emit-placement.py`'s output over the three tables and `packets/placement_contract.md` (control: a hand edit inside the block → `--check` fails; a change to any table or to the canonical text without re-emitting → fails; an operative rule changed in a table and re-emitted → the block changes, which the W reviewer reads). Semantic prose around the block stays owner-reviewed; no anchor phrase is relied on.
  4. Atomic cutover (F35, N#14): the commit that deletes the legacy entrypoints is the commit that replaces every runbook section naming them, **migrates `design/session-distill/ledger.json` to schema 2** (`migrate-ledger.py`, with the dated migration record) and replaces `merge-ledger.py`'s body with the thin CLI over `runlib/ledger.py` (control — N#8r3: a scan of **current** references for the seven command names — tracked code, the runbook, `docs/`, `SURFACES.md`, `DEPENDENCIES.md`, `IMPLEMENTATION_MAP.html` — finds none at that commit, while historical records keep their text and are excluded by path: `decisions/decisions.jsonl` (D-20260825-79eed9 names `screen-codex.py`) and dated files under `design/`; the scan's self-test plants a name in a current file → named, and in `decisions.jsonl` → not a failure); the stale current references are **named edits of this WP**: `learn/redact.py`'s docstring (the heavy flow becomes `session-distill/runlib/redaction.py`, not `digest.py`) and the comment at `gates/check-parity.sh`'s redaction leg; no earlier commit on the branch leaves the delivered runbook naming an absent or incompatible command — the control runs **each documented invocation** of the runbook at every commit on the branch against a scratch copy of that commit's data (the old runbook's `merge-ledger.py --window-end <date>` and `update-state.py --window-end <date>` before the cutover, the new runbook's commands from it), exit status asserted; filename existence is not the check.
  5. `git ls-files session-distill/out` is empty and `check-lexicon.py`'s `ARCHIVE` allowlist entry for `session-distill/out` is removed or re-justified (an allowlist entry matching no file is a stale declaration — the gate's own rule for homes; apply the same bar).
  6. `IMPLEMENTATION_MAP.html` names the driver, the supervisor, the runner profiles, the capture mode, and the commands that derive live state, with no dated measurements.
  7. Benchmark docs (N#4r4): `benchmarks/README.md` and `benchmarks/EXTENDING.md` describe the v2 interfaces, the per-case calibration barrier, the retained legacy scope and the promotion route under the global-file restriction; control: the cutover scan of done-when 4 also fails on a current doc that still documents the v1 cell identity, batch-wide calibration or "add a global rule" (a planted sentence in a scratch copy → named).
  8. `AGENTS.md` §10 says distill "is a feature of the deployed package that its users run against their own sessions", while `package.json` `files[]` and `gates/check-package.sh` keep `session-distill/` author-side and the runbook is `audience: author`. Both drafts found this; the sentence, and any lexicon entry that says the same (edited in `ontology/instances/graph.json`, then re-emitted), is corrected to the payload boundary. O reviews the wording.
- **Verification point.** The umbrella, run twice: once before the golden regeneration (expected red on the golden only, by name) and once after.
- **Review gate.** O on the guide, the preset, and the decision records (these are the owner's surfaces); W on the mechanical edits and the generated block.
- **Size.** M (≈550 lines of prose, config and the emitter).
- **Main risk.** Touching the preset changes the rendered review contract golden for every setup/host/family combination; the regeneration diff must show only the distill preset's rows.

### WP-23 Rehearsal harness: plant generator, §14 preflight, the two rehearsal runs, authorization record

- **Goal.** `distill.py rehearse`: the §18 plant table as data (`tables/plants.json`: one row per
  plant with `outcome`, `wp`, `fixture_id`, `realization ∈ {golden, replay, live}`, `expect` — the
  fail-by-name code or path — and `counterpart`), a runner that executes every plant and its clean
  counterpart, `distill.py preflight` (the §14 seven checks + P2/P4/P7 checks and the auxiliary-role
  measurement of S-7), the rehearsal **destination manifest and owner-destination guard** (N#4), the
  two rehearsal runs of §4.2 **at the contract scale** (D-1, option 1), the measurements of §16, and
  the rehearsal record that authorizes the first production run.
- **Design.** §14, §18, §16 (every parameter measured), §13.2 (budget set from measurements), §8.7
  (acceptance at the contract scale), §10.3 (F passes).
- **Files.** author-side: `session-distill/rehearse.py` (new), `session-distill/preflight.py` (new),
  `session-distill/tables/plants.json` (new), `session-distill/fixtures/` (synthetic transcripts,
  recorded captures, fault scripts, the seeded fixture corpus of RH-1 — each with a `REALIZATION`
  marker file), `gates/control-audit.py` `SUBJECTS`, rehearsal record written as a dated file
  `design/session-distill/<date>T<time>--<sha>--rehearsal.md` with the measured parameters.
- **Dependencies.** All WPs (it exercises them); runs after WP-22.
- **Done when.**
  1. Bijection: every row of §18 (as transcribed into `plants.json`, plus the §3.2 gate controls and the review's added rows of §4.1) names an existing fixture and a WP; every fixture is named by a row; the generator fails on an orphan either way (control: delete a fixture → fails by fixture id; add a row without a fixture → fails by row); a `smoke` realization is refused in `plants.json` (control).
  2. Each plant fails by its named code/path and each clean counterpart passes; the rehearsal record lists plant → verdict with the realization and, for live plants, the receipt ids. The design's rule: any plant passing unnoticed or any counterpart failing fails the rehearsal. **Semantic plants run through the production model path** (F27): the §6.5 control population through the real judges; the O5 keep/re-deliver/reduce/redundancy evidence through S4–S7; the calibration mislabel and the leakage plant through the real labeller and reviewer; the O6 Korean plant through S9b — each recorded with its live verdict, with the deterministic aggregation tested golden beside it.
  3. `preflight` runs the seven §14 checks live and, with them, the **host-allowance measurement** per host version and flag set (the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`; WP-06 done-when 3: minimal calls under each flag set, observed input minus the driver's bytes, the maximum recorded into `seats.json` and declared in `run.json.host_allowance{}`; re-run on every host upgrade, and a changed value re-bases every view bound before any dispatch — N#0r4) (frames canary; Codex isolation rendering; Claude ancestor plant in runner vs activated cell; `max_tokens` rejection; planted resume/fork/compaction per host incl. the first Codex compaction file-behaviour measurement, recorded into WP-05's `measurement_pending` fixture; capped episode per host with child and forced compaction reconciling; provenance indexes found with a fresh session `indexed` and a planted copy `not_indexed`), measures the auxiliary roles per host version into `seats.json` (S-7), and refuses the production run on any failure.
  4. **RH-1 (plant run, contract scale):** from the seeded fixture corpus, **seven** intervention items of the six kinds (four core — reduce, re-deliver, route-carried, executable-carried; one personal; two author-side gate changes — N#3) proposed, tested on their arms at the §2 scale (six cases × two repetitions × four strata × five configurations for core, two configurations for personal and author-side, the 13 shared regressions, interaction cases), carried through approval and S10b: pass 1 over all seven approved items; the planted author-side failure (F-O8-11) returns to the owner, F is rebuilt, pass 2 over the six — the two passes are **that fixture's schedule**, while §10.3's bound (confirmation repeats at most once per approved item) is asserted on its own (control: the same item failing again → returned, not re-confirmed); the other author-side item (F-O8-10e) completes confirmation, application in the fixture clone and executor verification by the §8.3 contract with its violation and clean controls rerun; application and delivery verification run under the destination manifest (done-when 7); the **seeded follow-up path** (O9's live rows: WP-08 done-when 5, WP-21 done-when 7) runs through S3's production reading and expansion, S12's resolution and exposure, the render and the close (N#3r3). The episode and token figures are the manifest-derived calculation of §8.2 (≈1,980 S8 actor episodes, ≈1,030 confirmation episodes, one scoring call per episode). Every cell carries its full denominator (control: a cell at one repetition is `incomplete` and the rehearsal does not authorize).
  5. **RH-2 (real-transcript path, contract scale):** over §18's **source scope** — a window of about three days, about ten sessions (≈20 views), a scope and not a duration (N#19) — S1–S2 over the owner's real homes (read-only), S3 and the stitch calls over the window's sessions, S4 with the full lifecycle intake (142 legacy entries), S5–S7b, R build and validation, S8 for the run's own core proposals at the contract scale (one real core item in the budget, D-2 as decided; a further item in the same run adds ≈331 episodes plus its interaction cases, §8.2; a window with no eligible core proposal keeps its actual result — F-NC-01 credited only when no proposal of any kind was produced on a nonempty, source-complete window, a personal-only window being the negative (F-NC-02) — and the path continues on a second declared window or a labelled historical subject with its own R and matrix — D-2, N#5r4, N#4r5), S9 and S9b, the owner's decisions for the rehearsal only, S10b, and S11–S12 in the fixture clone under the destination manifest (done-when 7), discarded after the record; every **consumed** result accepted by the gate, every rejected or interrupted attempt retained, classified and accounted; the token sweep clean. The **authorization predicate** of §4.3 is code in `rehearse.py` and the mixed-attempt control of WP-21 done-when 6 runs through it as well as through the close (N#2r5): a full-denominator rehearsal containing a failed attempt followed by a valid retry → authorized; a consumed result without an accepted gate verdict → not authorized, naming the call.
  6. Measured parameters recorded with denominators: per-stage usage and wall time, per-class p95 episode cost with n, Codex warm-up share, cache-hit share, sweep reuse rate (the §16 80% assumption), usage-window consumption per provider, R distance, S1 unknown-independence share, the Claude compaction overshoot class, the denial-log latency, S9b regeneration rate, owner review time.
  7. Confinement (N#4, N#1r3): `rehearse.py` builds the fixture root (`<root>/rehearsal/<run>/{home, claude-config, codex-home, state, clone}`), fills `run.json.destinations` with it for every class — the clone, install roots, personal layers, launcher and shell integration, runtime state, nudge, recovery — exports the overrides every writer reads, and asserts the resolved set (WP-21 done-when 14) before RH-1's and RH-2's S11. The **owner-destination guard** is **read-only**: it hashes the owner's real destination set — derived by running the same resolver against the owner's real environment: the install roots and the paths their deployed manifest lists, the personal layers, `~/.config/agent-launch`, the shell startup file, the `~/.local/bin` entries the installer owns, `~/.local/share/agent-bios`, the nudge state file, and the owner's checkout (`HEAD`, the index hash, `git status --porcelain`) — before the rehearsal, after RH-1, after every crash injection (F-O8-09a–c, F-O8-13), and after RH-2; any difference fails the rehearsal naming the path (`OWNER_DESTINATION_CHANGED`). Transcript directories are sources (read-only, WP-05), not destinations, and are outside the set. **No plant writes an owner path.** The guard's change detection is tested against a **fixture-owned stand-in**: a second fixture root posing as the owner's destination set, hashed by the same guard, into which a crash-injection run plants a write → `OWNER_DESTINATION_CHANGED` naming the stand-in path (F-O8-21); an escape attempt is tested by proving **refusal before any write** (WP-21 done-when 14's escape control, F-O8-20), with the attempted target's hash equal before and after. A scratch branch, a scratch ledger or a worktree is not confinement; only the resolved set inside the fixture root and the unchanged owner hashes are.
- **Verification point.** The rehearsal itself; its record is the evidence.
- **Review gate.** X over the rehearsal record (packet = record + plants table + receipts; the reviewer is asked which plant could have passed vacuously and which live row is missing); O authorizes the first production run.
- **Size.** L (≈800 lines + fixtures authored across WPs + the seeded corpus).
- **Main risk.** Fixture debt — a plant left golden where the contract is host-bound. The `realization` column makes that a visible row, and §4 names which rows must be live.

---

## 3. Ordering

The graph is derived from the **Dependencies** lines of §2 by one rule: an edge X → Y for every
work package X that Y's line names, of the kind the line states (N#6). Three kinds (F34): an
**interface** edge (the consumer needs a schema or table the producer defines — satisfied by
landing the definition, with golden fixtures until the producer's live path exists), a **live**
edge (the consumer's live done-when needs the producer's live path), and a **review** edge (the
seat a work package's X review runs on). Where a line separates landing from live verification
(WP-02: its gate lands against replayed captures; its verification point waits for WP-03/WP-04's
first live calls), the live edge runs from the producer's **live-verified** milestone, which is
what dissolves the WP-02 ⇄ WP-03/04 cycle. The longest path is taken over live and review edges.

```
interface edges (schemas, tables, declarations)
  WP-01 → {WP-02, WP-05, WP-08 (record schemas), WP-21 (expected-observation seeds)}
  WP-09 (partition, population) → WP-20;  WP-12 (sequencing checker) → {WP-20, WP-21}
  WP-13 (schema 2) → {WP-07 (ledger layer), WP-09, WP-12, WP-21};  WP-21 (occasion index) → WP-09
  WP-15 (installation receipt) → {WP-10, WP-16}

live edges (→ = must precede the consumer's live done-when; WP-02 has two milestones — N#6r3:
  WP-02i = gate and supervisor landed against replayed captures, reviewed; WP-02v = live-verified
  by WP-03's and WP-04's first live calls, a zero-length milestone)
  WP-01 → WP-02i → WP-03 ‖ WP-04;  P1 → WP-04;  {WP-03, WP-04} → WP-02v
  WP-01 → WP-05 → WP-06;  WP-01 → WP-07;  WP-01 → WP-13;  WP-02i → WP-16;  WP-01 → WP-16
  {WP-02v, WP-03, WP-06, WP-07} → WP-08 → WP-09 → WP-10 → WP-11 → WP-12;  WP-03 → WP-09
  {WP-05, WP-07} → WP-10;  {WP-03, WP-04} → WP-11;  WP-09 → WP-12
  WP-16 → WP-17 → WP-18 → WP-19;  {WP-02v, WP-03, WP-04, WP-15} → WP-17;  {WP-16, WP-04} → WP-18
  {WP-16, WP-17, WP-07, WP-12} → WP-19        (WP-12 → WP-19: the live matrices need real proposals)
  {WP-12, WP-19, WP-09, WP-10, WP-04} → WP-20 → WP-21;  {WP-13, WP-14, WP-15, WP-05, WP-06, WP-08} → WP-21
  {WP-01 … WP-21} → WP-22 → WP-23          (the cutover's predecessors are the twenty-one packages before it; acyclic)

review edges
  P1 → every X review: through the fixed hermetic profile until WP-04 lands, through the capture
  mode after (the bootstrap of §2, stated once there; WP-04's own review runs on the pre-capture profile)
```

**Longest path (provisional — F34; sizes as §8.3, S 1 / M 1.5 / L 3 / XL 5 sessions; re-based
when WP-01, WP-14 and WP-02 are timed): 44 sessions** — WP-01 → WP-02i → WP-03 → WP-02v → WP-08 →
WP-09 → WP-10 → WP-11 → WP-12 → WP-19 → WP-20 → WP-21 → WP-22 → WP-23 → first production run,
computed over the acyclic graph above (WP-02v adds no length; WP-16 starts from WP-02i). The
**evidence lane** is the critical path, not the harness lane: WP-19's live done-when needs WP-12's
real proposals, and WP-12 finishes at session ≈24.5 while the harness lane's WP-18 finishes at ≈16
(WP-16 starts right after WP-02 — it needs no runner profile — and WP-17 waits for WP-03/WP-04 and
WP-15). Earliest finish per WP, in sessions from P1: WP-01 1.5, WP-02i 6.5, WP-04 8, WP-03 9.5, WP-02v 9.5,
WP-16 11.5, WP-08 12.5, WP-17 14.5, WP-09 15.5, WP-18 16, WP-10 18.5, WP-11 21.5, WP-12 24.5,
WP-19 29.5, WP-20 34.5, WP-21 39.5, WP-22 41, WP-23 44; Lane L's three land whenever a slot is
free.

**Parallel lanes** (after WP-01/WP-02), one `git worktree` per lane (P8):

- Lane E (evidence): WP-05 → WP-06 → WP-08 → WP-09 → WP-10 → WP-11 → WP-12, with WP-07 beside WP-06.
  Needs WP-03/WP-04 only from WP-08 on. It is the critical path; a third implementer shortens the
  calendar only by splitting it (WP-05/WP-06/WP-07 beside WP-02's tail).
- Lane H (harness): WP-16 → WP-17 → WP-18 → WP-19. Needs WP-03/WP-04 and WP-15 from WP-17 on; has
  ≈8 sessions of slack before WP-19.
- Lane L (state and gates): WP-13, WP-14, WP-15 — independent of each other and of the lanes above;
  WP-14 can land first of all (it is also the gate that protects the global file while WP-21 is
  being written). WP-13's schema is an interface edge into Lane E (WP-07, WP-09, WP-12), so it lands
  before those start their ledger-reading done-whens; its data migration waits for the cutover
  (N#14).
- Lane R (reviews): the bootstrap of §2 — until WP-04 lands, every X review runs through P1's fixed
  hermetic profile with a receipt; from WP-04 on, through the capture mode. Schedule WP-03's and
  WP-04's reviews back-to-back.

Integration is serialized: a lane rebases onto the integration checkout and commits there one WP at
a time (the hook refuses an index that moved during the gates, and the umbrella takes minutes).
Two implementers suffice: one on Lane E, one on Lane H, with Lane L interleaved by whichever is
blocked on a review. Three shorten the calendar only until WP-19, where live matrices serialise on
the usage windows.

---

## 4. Rehearsal

### 4.1 Plant map (§18 → work package, fixture, realization)

Every row below becomes one row of `session-distill/tables/plants.json` (WP-23), which the
rehearsal runner executes together with its clean counterpart. `golden` = synthetic artifact,
fault injector, or fake host (declared); `replay` = a retained real capture with its provenance
hash; `live` = the real pinned binary. A host-bound contract (isolation, attestation, activation,
accounting, compaction, provenance indexes) and every **semantic** plant (a judge, labeller,
reviewer or author must recognise the planted meaning — F27) must have a live row; a golden or
replay row for such a contract is a development convenience, never authorization evidence.
Fixture ids are stable names the WP self-tests use. Rows marked "added" come from review round 1
or from the §3.2 control list, which §6.5 folds into the planted population.

**O0** (WP-01)

| Plant | Fixture | Realization | Fails as |
|---|---|---|---|
| criteria changed after S3 without an amendment | F-O0-01 | golden | `AMEND_REQUIRED` |
| a stage that read a newer `run.json` than its results | F-O0-02 | golden | `DECLARATION_DRIFT <stage>` |
| added: an amendment present whose `invalidates[]` names the producer | F-O0-03 | golden | `INPUT_STALE <producer>`; counterpart: scope covers, producer not invalidated → pass |

**O1** (WP-05 unless noted)

| Plant | Fixture | Realization | Expected classification |
|---|---|---|---|
| one named Claude Desktop session | F-O1-01 | golden | desktop, counted per provenance |
| one named Codex Desktop session | F-O1-02 | golden | desktop |
| resumed session with appended records | F-O1-03 | golden | one transcript, continuity holds, new range in `coverage.json` |
| rewritten transcript | F-O1-04 | golden | continuity fails, new version read in full, prior evidence ids kept on the prior copy |
| missing source directory | F-O1-05 | golden | source `unknown`, no total |
| all sources empty | F-O1-06 | golden | zero eligible; run succeeds (empty-source handling only; the no-change path is F-NC-01) |
| deferred session carried to the next run | F-O1-07 | golden (two runs) | in the backlog, read first next run |
| partial session carried to the next run | F-O1-08 | golden (two runs) | `read_partial`, unread ranges in the backlog |
| child transcript | F-O1-09 | golden | `child_of(parent)`, linked, not counted |
| records straddling the window start | F-O1-10 | golden | earlier records context, not counted |
| event at the end of one window whose outcome falls in the next | F-O1-11 | golden (two runs; WP-05 + WP-08) | read as context (read range, not processed); next run processes and stitches |
| interactive Claude root later resumed headlessly | F-O1-12 | golden | stays `claude-cli` |
| copy of a root beside its original | F-O1-13 | golden | unknown independence; in S1's share |
| activated Codex `vscode` session, originator `agent-bios`, with pin | F-O1-14 | golden | `codex-cli` |
| same shape without a pin | F-O1-15 | golden | `unknown_provenance` |
| Claude fork with inherited head, copied record ids, no pointer | F-O1-16 | golden | affirmed with its source |
| Codex compaction | F-O1-17 | **live** (§14 check 5, WP-23) | classified only after its file behaviour is measured; fixture flagged `measurement_pending` until then |
| rollout compressed in place after indexing | F-O1-18 | golden | `indexed` |
| rollout moved to `archived_sessions/` | F-O1-19 | golden | same transcript; continuity holds |
| compressed rollout in the window | F-O1-20 | golden | read |
| lone copy of a root with a new id and no original | F-O1-21 | golden | `not_indexed`; unknown independence; in the share |
| Desktop session absent from every index | F-O1-22 | golden | `not_indexed` |
| unreadable index | F-O1-23 | golden | `index_missing`: read, not counted |
| `vscode` rollout with originator `Claude Code` | F-O1-24 | golden | excluded |
| rollout with an originator the table does not name | F-O1-25 | golden | `unknown_provenance`, listed with count |
| index-only identity with no transcript, Codex | F-O1-26 | golden | `known_absent` (codex class) |
| index-only identity with no transcript, Desktop index | F-O1-27 | golden | `known_absent` (desktop class) |
| provenance readers on the real indexes; fresh session `indexed`; planted copy `not_indexed` | F-O1-28 | **live** (§14 check 7) | as named |
| added: a targeted run after a periodic one | F-O1-29 | golden (two runs) | periodic coverage byte-identical; `TARGETED_ADVANCED_COVERAGE` if not |
| added: a transcript with no new records since the last window | F-O1-30 | golden | `nothing_new` |
| added: an S3 record deleted before reconciliation | F-O1-31 | golden | per-source counts fail naming the session |

**O2** (WP-06, WP-08)

| Plant | Fixture | Realization | Fails as / expected |
|---|---|---|---|
| an altered quote | F-O2-01 | golden | `SOURCE_TAMPERED` on resolve / `QUOTE_MISMATCH` on the claim |
| decisive outcome in the omitted middle of a successful tool result after a pending event | F-O2-02 | golden (forcing + enforcement) and **live** (one S3 call must find it; counterpart: not found without expansion) | forced; `EXPANSION_SKIPPED` if skipped |
| a skipped span | F-O2-03 | golden | session `view complete`, not `source complete` |
| a model output that retypes a quote | F-O2-04 | golden (canned result) | `QUOTE_MISMATCH`, claim dropped, set accounting reports it |
| a cause and its outcome four windows apart | F-O2-05 | golden + **live** (the four windows and the stitch call through the production reader on the real seat; receipts retained — N#11) | stitch call resolves the event with evidence ids naming the outcome window's records; withheld outcome window (live counterpart) → event `unresolved` after the stitch; `coverage.json` pending-events entry with its id (N#10r3) |
| added: a window overlap removed | F-O2-06 | golden | `OVERLAP_MISSING`; a record owned twice → `SET_MISMATCH` |
| added: a session's stitch call suppressed | F-O2-07 | golden | `read_partial`, not `read_complete` |
| added: a quote carrying raw (unmasked) bytes vs the masked form | F-O2-08 | golden | raw → fails; masked → validates against the redaction projection |
| added: a view window whose driver bytes exceed 120k − the declared allowance; one under that but over the context capacity with its output reservation; a replayed view-window capture whose observed input exceeds 120k; a seat without a declared allowance; probe 7's retained R-authoring capture (≈136k) as a non-window call | F-O2-09 (×5) | golden (+ the live allowance measurement in preflight) | split before dispatch; split; `INPUT_BOUND_EXCEEDED` (host change — the run stops until re-measured and amended); `ALLOWANCE_UNDECLARED`; accepted, the window rule untouched (the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`; N#0r4, N#0r5) |
| added: one claim revision with distinct fact, interpretation, uncertainty and quotation through render and ledger | F-O2-10 | golden (WP-21 done-when 13) | all four resolve unchanged; each mutated independently → named by component (N#13) |

**O3** (WP-10; inputs from WP-07)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| pinned session that violated a delivered rule | F-O3-01 | golden | misfire |
| guide pointer exposed but never read | F-O3-02 | golden | misfire (trigger) |
| unit selected but unavailable on the route | F-O3-03 | golden | `selected_unavailable` → not delivered |
| unpinned session | F-O3-04 | golden | unclassified |
| one helpful and one violated covering unit | F-O3-05 | golden | misfire, both shown |
| guide read spanning the unit, content truncated before it | F-O3-06 | golden | `exposed_not_read` |
| unpinned session that read the unit before violating it | F-O3-07 | golden | misfire, selection unknown |
| one fixture per row of the §6.4 unit-outcome table | F-O3-T-<row> | golden, generated | per row; an untested row fails the bijection |
| helpful unit + unit of unknown contribution | F-O3-08 | golden | unclassified, both outcomes shown |
| helpful unit + unit of unknown following | F-O3-09 | golden | unclassified, both shown |
| guide read returns unit and heading, not the enclosing exception | F-O3-10 | golden | `exposed_not_read` |
| operative context across two guides, read completely | F-O3-11a | golden | delivered |
| … second guide unread | F-O3-11b | golden | `exposed_not_read` |
| … second guide from a different version than the requirement names | F-O3-11c | golden | `exposed_not_read` |
| returned fragment identical in two versions with different operative contexts | F-O3-12 | golden | binds by pin or release, else unknown |
| added: an unsupported layer; an unavailable historical layer | F-O3-13a/b | golden (WP-07) | reference point incomplete; a gap at it → `unknown` |

**O4** (WP-02, WP-03, WP-04, WP-10, WP-11, WP-16)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| the planted controls — the whole §6.5 population: two paraphrases of covered units, two admission failures (temporal-order cause; task-specific requirement), one altered quote, one fabricated session id | F-O4-01 | golden (aggregation) + **live** (every control through the real judges, under ordinary ids) | each recognised; one accepted as natural → `CONTROL_FAILED`, run stops before S7 |
| a candidate both judges mark uncertain | F-O4-02 | golden + **live** (a planted ambiguous candidate; its verdict recorded) | `disputed`, not admitted |
| a gap claim contradicted by a unit only one sweep flags | F-O4-03 | golden + **live** | reconsidered by both judges; disagreement → `disputed` |
| a session pair whose replay hides its ancestry | F-O4-04 | golden | counted once |
| a judgment call that silently loads an undeclared instruction yet returns a valid answer | F-O4-05 | **live** (WP-03 profile with a planted `--append-system-prompt` after `--`) | `CONTEXT_UNDECLARED` |
| instruction file in an ancestor of the hermetic runner's cwd | F-O4-06a | **live** | not loaded; accepted |
| the same plant under an activated cell | F-O4-06b | **live** (WP-16/17) | loaded; rejected by the planted path |
| hermetic Codex call with `--cd` inside a repository carrying `AGENTS.md` | F-O4-07 | **live** (§14 check 2) | no AGENTS.md in the rendering; accepted; inherit counterpart shows it |
| hermetic Claude call with declared appended instructions | F-O4-08a | **live** | accepted; recorded content matches the declared hash |
| … undeclared | F-O4-08b | **live** | `CONTEXT_UNDECLARED` |
| … hash-mismatched | F-O4-08c | **live** | `CONTEXT_HASH_MISMATCH` |
| tool-enabled producing call using its declared tools | F-O4-09a | **live** | accepted |
| … attempting an undeclared tool | F-O4-09b | **live** | refused; recorded in `actions.jsonl` |
| … a path outside its manifest directory | F-O4-09c | **live** | refused; recorded |
| added (§3.2 controls): truncated output on Claude | F-O4-10a | **live** (`CLAUDE_CODE_MAX_OUTPUT_TOKENS` small) | `COMPLETION_INCOMPLETE` |
| added: a real aborted Codex stream | F-O4-10b | **live** (host terminated after `response.created`) | failure |
| added: a planted `response.incomplete` frame | F-O4-10c | golden | failure |
| added: a refusal (Claude `stop_reason: refusal` shape; planted refusal frames both runners) | F-O4-10d | replay + golden | failure |
| added: a nonzero exit | F-O4-10e | **live** | failure |
| added: a stale receipt (another `call_id`) | F-O4-10f | golden | `RECEIPT_STALE` |
| added: a mismatched result hash | F-O4-10g | golden | `RECORD_INTEGRITY` |
| added: an inherited profile | F-O4-10h | **live** (`--profile inherit`) | `PROFILE_INHERITED` |
| added: a contaminated working directory — an undeclared working-directory instruction file, an ancestor file, a configuration-home instruction file, a skill, a memory file, each returning a valid canary-free answer; two halves per source (N#8) | F-O4-10i (×5, ×2 halves) | **live** (both runners) | hermetic half: source not loaded, accepted (isolation); loading half (`inherit` profile with the cell homes): `CONTEXT_UNDECLARED` in the complete failure set (detection); loading clean counterpart: `PROFILE_INHERITED` only |
| added: `terminal_reason` present but not `completed`; a schema-less actor call without `structured_output`; each Claude binding broken | F-O4-10j | golden | `COMPLETION_INCOMPLETE`; accepted; `BINDING_MISMATCH` |
| added: more than twenty natural candidates with no rejection | F-O4-11 | golden | `REJECTION_SHARE_ZERO` (O4 fails); counterpart: twenty → passes |
| added: cross-review — a partial flag removed; a sampled reason corrupted; a reconsideration missing | F-O4-12a/b/c | golden | `CROSS_REVIEW_INCOMPLETE`; hash mismatch; `RECONSIDERATION_MISSING` |
| added: a control's judge packet carrying a marker byte | F-O4-13 | golden (structural diff) | refused — controls enter under ordinary ids |
| added: Judge A and B payloads equal while each packet carries its own `call_id` | F-O4-14 | golden | `payload_sha256` equal, `packet_sha256` distinct; a seat-specific line in one payload → `PACKET_DIVERGENCE`; one `packet_sha256` on two receipts → `RECEIPT_STALE` (N#1) |

**O5** (WP-09, WP-12; carry rows WP-21)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| evidence supporting keep | F-O5-01 | golden (aggregation) + **live** (S4–S7 on the RH-1 corpus) | keep proposal |
| evidence supporting re-deliver | F-O5-02 | golden + **live** | re-deliver |
| evidence supporting reduce | F-O5-03 | golden + **live** | reduce |
| redundant pair of working units | F-O5-04 | golden + **live** | reduce by merge allowed |
| reduce over a keep record without `keep 해제` | F-O5-05 | golden | `KEEP_GUARDED` |
| incubate without expiry | F-O5-06 | golden | `EXPIRY_REQUIRED` |
| disallowed kind–disposition pair | F-O5-07 | golden | `PAIR_DISALLOWED` |
| core item admitted by adjudication | F-O5-08 | golden (WP-20 adjudication second pass) | `awaiting_R`, not applied; a personal item admitted the same way proceeds |
| legacy S3-03 (no mapped decision, unavailable history, no new occasion) | F-O5-09 | golden over the real entry + **live** (RH-2 intake) | unclassified; offered incubate with prospective observation and expiry, or drop, under the legacy-maintenance row |
| legacy entry with a mapped incubate decision | F-O5-10 | golden | enters with it |
| S3-03's approved incubation carried through S12 into a later run's intake at expiry | F-O5-11 | golden (two runs; WP-21) | provenance preserved; observation and expiry stored; re-enters at expiry |
| counterpart S3-03 the owner retires | F-O5-12 | golden (WP-21) | does not re-enter |
| one left at `none` | F-O5-13 | golden | stays in the legacy intake |
| approved keep, incubate, drop | F-O5-14 | golden (WP-12 + WP-21) | ledger only; no library change; no S8 matrix |
| added: a G candidate without both sides, ordering, prohibition, or three claim ids; one below the lineage bar | F-O5-15 | golden | `G_ANTI_ABSTRACTION`; held below the bar |
| added: a due decision removed from the produced intake; a pending intervention on a placed entry | F-O5-16 | golden | `INTAKE_INCOMPLETE`; enters |
| added: a guide proposed below the five-item criterion; an instruction aimed at a code-only consumer; a blocking gate on a semantic criterion; a global-file addition; a C principle routed elsewhere; a judging hook | F-O5-17 (×6) | golden (+ one S7b live case in RH-1) | `GUIDE_PREMATURE`, `CONSUMER_MISMATCH`, `GATE_ON_JUDGMENT`, `GLOBAL_ADDITION`, `C_ROUTE`, `HOOK_CHARTER` (N#10) |

**O6** (WP-20)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| a candidate missing from the review | F-O6-01 | golden | `RENDER_INCOMPLETE` |
| counts that do not reconcile | F-O6-02 | golden | `COUNTS_DIVERGE` |
| a row whose Korean drops a fact | F-O6-03 | **live** (S9b on gpt-6-astra/high; regeneration once by S7's seat) | flagged; regenerated; counterpart row passes |
| added: a row still failing after regeneration | F-O6-04 | golden + **live** | visible "번역 검토 실패" mark persists; never withheld |
| added: a missing rejected finding, failed item, quarantined item, non-finding appendix row | F-O6-05 (×4) | golden | `RENDER_INCOMPLETE` naming the id |
| added: a missing eventless legacy candidate; a missing pending intervention on a placed entry | F-O6-06 (×2) | golden | `RENDER_INCOMPLETE` naming the id (N#12) |

**O7** (WP-16, WP-17, WP-18, WP-19)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| wording-only test | F-O7-01 | golden (WP-19) | `CASE_WORDING_ONLY` |
| action case without a postcondition | F-O7-02 | golden | refused |
| leaked diagnosis without its key terms | F-O7-03 | golden + **live** leakage review | fails by name |
| mislabelled calibration response | F-O7-04 | golden + **live** (the blind labeller must catch it) | calibration invalid; reworked once; still invalid → cells `invalid`, item incompletely tested |
| contaminated withholding arm | F-O7-05 | golden lexical + **live** semantic through the gate with its positive control | caught; void if the positive control does not fire |
| child brief differing by a paraphrase | F-O7-06 | golden (WP-17) | episode invalid |
| copied setting pointing into the owner's real roots | F-O7-07 | golden (WP-16 static check) | fails naming the setting |
| episode whose native state changed mid-run | F-O7-08 | golden (fault) | invalid |
| episode that exceeds its cap | F-O7-09 | **live** (WP-18) | stopped; tree killed; overshoot recorded |
| case slot whose calibration stays invalid | F-O7-10 | golden | item incompletely tested |
| personal / reduce / re-deliver / route-carried / executable-carried core item / author-side gate change through their arms | F-O7-11a–f | golden matrix + **live at the contract scale** (RH-1, WP-23) | full v2 matrix with every denominator and an artifact-gate result each |
| Codex child that refuses to echo its brief | F-O7-12 | **live** (WP-17) | episode invalid |
| actor that tries to edit its compiled snapshot | F-O7-13 | **live** (WP-16) | denied; recorded as an action; snapshot still verifies |
| cell placed under the owner's HOME | F-O7-14 | golden (static) + **live** host report | both fail by name |
| capped Claude episode that compacts | F-O7-15 | **live** (WP-18) | estimate per marker; stopped by compaction cap; overshoot reported as estimated |
| actor reading a sibling cell | F-O7-16a | **live** | denied; episode invalid |
| actor writing a sibling cell | F-O7-16b | **live** | denied; episode invalid |
| shell write (not an editing tool) to the episode's own snapshot | F-O7-17 | **live** | denied by the sandbox; recorded; episode valid |
| two concurrent episodes, a denial on one's cell whose requesting pid neither recorded | F-O7-18 | **live** | both invalid; attributed to neither |
| activation through the sandboxing host wrapper | F-O7-19 | **live** (WP-17) | completes and pins; clean |
| actor's shell write to its own pin | F-O7-20a | **live** | denied; recorded |
| actor's shell write to its journal | F-O7-20b | **live** | denied; recorded |
| Codex child brief exact | F-O7-21a | **live** | accepted (echo equal, ciphertexts equal) |
| … paraphrased | F-O7-21b | **live** | invalid |
| … edited by one character | F-O7-21c | **live** | invalid |
| … with appended context | F-O7-21d | **live** | invalid |
| … inherited parent context controlled: declared `none` with a fork marker; declared `controlled_fork` whose parent took a scripted second turn before the spawn (records beyond the allowance frozen before launch); a different parent id | F-O7-21e (×3) | **live** (actual fork markers + child effective-context evidence; the allowance is a construction rule frozen before launch — N#2, N#2r3) | `CHILD_CONTEXT_INHERITED` even with an exact echo; canary absence alone is not acceptance |
| … controlled fork counterpart: declared `controlled_fork` carrying exactly the prefix the frozen rule allows, echo exact (Claude `subagent_type: fork`; Codex `fork_turns: "all"`), judged by the same rule as F-O7-21e | F-O7-21f | **live** (per host) | **valid** (N#2, N#2r3) |
| added: Claude child with two Agent calls; with zero child transcripts; first user record differing | F-O7-22 (×3) | golden + **live** | invalid |
| added: pin succeeds but an expected hook does not execute (Claude `hook_started` absent; Codex marker absent / trust not bypassed) | F-O7-23 | **live** (per host) | `route_failed`, not clean |
| added: a treatment tree that edits `benchmarks/judge.py`; one that edits `wrappers/claude-run.sh` | F-O7-24a/b | golden | the frozen evaluator closure is used (hash asserted unchanged) |
| added: artifact validation — missing Korean artifact; stale mirror; shipped helper not in `files[]`; author-gate control that cannot fire; repo path in shipped prose | F-O7-25 (×5) | golden (scratch worktree) | each caught by name |
| added: a prose-wrapped JSON absence verdict; a context-invalid receipt; a stub with no dispatch | F-O7-26 (×3) | golden | cannot establish absence |
| added: an uninspectable effective reference (dangling symlink in `config/`) | F-O7-27 | golden | `invalid` by path |
| added: denied writes to the state root, the release tree, and each install/launcher/bin destination | F-O7-28 | **live** | denied; recorded; episode valid |
| added: a cell at one repetition | F-O7-29 | golden | `incomplete`, never a verdict |
| added: `claude-main` and `claude-subagent` episodes otherwise identical | F-O7-30 | golden | distinct cell keys; a v1 artifact refused by v2 acceptance |
| added: an episode closed before its denial window elapsed | F-O7-31 | golden | `isolation: uncertain`, never `valid` |
| added: a producing call's `Read` outside the manifest (absolute path, `..` path, symlink out); `Grep`/`Glob`/`Bash` requests | F-O7-32 | **live** (real host; WP-03 done-when 4) | refused before content returns; denial recorded; no canary byte anywhere (N#9) |

**O8** (WP-20, WP-21, WP-15)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| item without an approval row | F-O8-01 | golden | `undecided`, never applied |
| approved subset whose confirmation fails one item | F-O8-02 | golden + **live** (RH-1) | item returns in a new review version; F rebuilt; the rest re-confirm |
| target drift before application | F-O8-03a | golden | refused by name |
| untargeted configuration drift (a layer, a dependency, an author-side tree hash) | F-O8-03b | golden | refused by name |
| deletion verified by absence | F-O8-04 | golden + **live** (WP-21 applied item) | verified |
| route-only change verified by route | F-O8-05 | golden | verified |
| emitted-but-unavailable unit | F-O8-06 | golden | not delivered |
| failed child reach | F-O8-07 | **live** actor | delivery failed; item returned |
| applied wrapper change whose fresh pin pairs with an invocation of the old wrapper version | F-O8-08 | golden | not verified |
| crash before an effect | F-O8-09a | golden (fault) | recovery close reconciles |
| crash after an effect, before its `done` record | F-O8-09b | golden (fault) | reconciles |
| crash during installation | F-O8-09c | golden (fault; WP-15) | reconciles; `installer.digest` = the recovering installer, `begun_by_installer_digest` = the beginning one |
| personal, reduce, re-deliver items and the author-side gate change through approval, F confirmation, application, delivery verification | F-O8-10a–d | golden + **live at the contract scale** (RH-1, fixture clone under the destination manifest) | each carried end to end; F-O8-10d's item is the one F-O8-11 fails |
| added: a second author-side gate change that **succeeds** — confirmation, application in the fixture clone, executor verification by the §8.3 contract with its violation and clean controls rerun, complete denominators | F-O8-10e | golden + **live at the contract scale** (RH-1) | carried end to end (N#3) |
| one F confirmation in which the author-side change fails and returns to the owner while the rest re-confirm | F-O8-11 | golden + **live** (RH-1: pass 1 fails it, pass 2 re-confirms the rest — this fixture's schedule, not §10.3's bound) | as named; the same item failing again → returned, not re-confirmed (§10.3) |
| added: two operations sharing a target | F-O8-12 | golden | chained by hash; the second refuses `TARGET_MISMATCH` when the first did not apply |
| added: crash after the commit and before `done` | F-O8-13 | golden (fault) | recovery finds the operation id in the branch log; no second commit |
| added: a full set with a valid order whose approved subset has none | F-O8-14 | golden | subset returned, not confirmed or applied |
| added: stale `item_sha`, stale case bytes, stale `configuration_sha`, stale `results_sha` | F-O8-15 (×4) | golden | `CONFIRMATION_UNBOUND` by field |
| added: a case byte changed after S8 | F-O8-16 | golden | B reruns (reuse precondition) |
| added: an item whose sha changed after rendering | F-O8-17 | golden | `DECISION_STALE` until decided again |
| added: a selected-but-unused unit | F-O8-18 | golden | delivery check fails (§10.5 control) |
| added: a pre-fsync `planned` record found absent, complete, or torn | F-O8-19 (×3) | golden (fault) | no effect before fsync (before-hash); recovery decides by hashes; a torn record logged and ignored (N#16) |
| added: a required override missing (`CODEX_HOME`; the nudge state path); an actual escape (nudge state path under a second fixture root; a resolver fixture with an out-of-root fallback); a writer without a destination class | F-O8-20 (×5) | golden | `OVERRIDE_MISSING`; `DESTINATION_OUTSIDE_ROOT` before any effect, target hash unchanged; `DESTINATION_UNDECLARED` (N#4, N#4r3) |
| added: a write planted into the fixture-owned **stand-in** destination set inside a crash-injection run (never an owner path) | F-O8-21 | **live** (rehearsal guard on the stand-in; the real-owner guard is read-only hashing) | `OWNER_DESTINATION_CHANGED` naming the stand-in path (N#4, N#1r3) |

**O9** (WP-08 instances; WP-21 resolution and exposure; WP-15 receipts; WP-13 history)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| seeded expected observation: one observed, one not observed, one pre-application, one `exposure_unknown` occasion | F-O9-01 | golden (precedence) + **live** (RH-1 seeded follow-up path: the observed and the not-observed occasion recognized by the production reader — N#3r3) | not observed wins |
| only observed and `exposure_unknown` occasions | F-O9-02 | golden | pending |
| only match lies in a skipped span | F-O9-03 | golden + **live** (RH-1: pending until the forced expansion, then found — N#3r3) | pending until expanded |
| two clipped results with identical visible head and tail, one hiding a paraphrased occasion **the search misses** | F-O9-04 | golden (WP-06/08) + **live** (RH-1, both twins — N#3r3) | no forced expansion; skip leaves basis view; "no occasion" refused → pending; counterpart with a retrieval term → forced expansion, found |
| observed occasions in a window with one skipped span | F-O9-05 | golden | observed, basis view, out of the effect ratio |
| observed occasions in a window with a missing transcript | F-O9-06 | golden | pending |
| request → guide read → correct action | F-O9-07 | golden + **live** (RH-1 seeded follow-up path — N#3r3) | exposed, observed |
| source-complete window with no occasion | F-O9-08 | golden | `no_occasion` |
| observed occasions in a window with a deferred session | F-O9-09a | golden | pending |
| … a failed session | F-O9-09b | golden | pending |
| … a partially read session | F-O9-09c | golden | pending |
| installer change whose occasion's installation receipt names the old installer | F-O9-10 | golden (WP-15 receipts) | not exposed |
| removed wrapper whose command still resolves to an older carrier | F-O9-11a | golden | not exposed |
| … whose occasion recorded no resolution | F-O9-11b | golden | `exposure_unknown` |
| pending intervention on a placed entry carried into the next run's intake | F-O9-12 | golden (two runs) | resolved there |
| compiler change whose occasion consumed an artifact with the old compiler digest | F-O9-13 | golden | not exposed |
| personal change whose layer has the applied hash but no loading record | F-O9-14 | golden | `exposure_unknown` |
| installer recovery begun by the old installer, finished by the applied one | F-O9-15 | golden (WP-15 fault) | distinct `installer.digest` and `begun_by_installer_digest`; `exposure_unknown` |
| recovery of a transaction begun before receipts existed | F-O9-16 | golden (WP-15) | unbound, `exposure_unknown` |
| added: three consecutive source-basis windows without a match for a unit; a view-basis window in the sequence | F-O9-17 | golden (three runs) | obsolete-review hint in the next intake; the view window counts nothing |
| added: an unaccounted source in a claim's scope | F-O9-18 | golden | basis incomplete; every absence resolution pending |
| added: a placed entry with an earlier applied observation and a later pending intervention, resolved independently | F-O9-19 | golden (WP-13) | two `decisions[]` elements with their own resolutions; status unchanged |
| added: occasion-index hint sequences — source/source/source; source/source/view/source; source/view/source/source/source; a match in the third window | F-O9-20 (×4) | golden (scratch runs) | hint; no hint; hint after the last three; no hint (N#17) |

**O10** (WP-02, WP-04, WP-13, WP-14, WP-18, WP-21)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| an added global line | F-O10-01 | golden (WP-14 scratch repo) | `GLOBAL_LINES_GREW` |
| a deletion plus an unrelated shorter line | F-O10-02 | golden (WP-14 + WP-21) | passes the gate; disclosed; S11 refuses `GLOBAL_OP_UNJUDGED` |
| equal-count ledger deletion plus insertion | F-O10-03 | golden (WP-13) | fails naming the lost id |
| the migration over the real ledger | F-O10-04 | deterministic over real data (WP-13) | every legacy value mapped; every legacy value found in the migrated record; eight named rows match |
| one fixture per non-"—" cell of the §12.3 table | F-O10-T-<cell> | golden, generated | per cell; bijection enforced |
| a stage with no wall time | F-O10-05 | golden (WP-21 close) | close fails |
| an accepted result with no observed model; a mixed run — an unattested failed attempt, an attested retry, an applied effect whose delivery call failed unattested | F-O10-06 (×2) | golden (WP-02/21) | rejected; the close succeeds with explicit `failed`/`unknown` status and retained accounting, the effect recorded, delivery `failed`, item returned (N#1r4) |
| provider usage-limit signal mid-stage | F-O10-07 | golden (injector; WP-02 breaker) | dispatch stops, no retries, items deferred, resumed after reset, other provider continues |
| Codex call whose frames are silent | F-O10-08 | **live** (`RUST_LOG` unset; WP-04) | `MODEL_UNATTESTED` |
| Codex transport fallback | F-O10-09 | replay (probe 5 recording) | `frames_blind`; usage from otel; request kind unknown |
| Claude result reading `success` with `is_error` true | F-O10-10 | golden | failure |
| closing-aggregate residual beside an unreconciled failed attempt | F-O10-11 | golden (WP-18) | unexplained, not compaction |
| Codex episode whose warm-up and root carry frames while one child response does not | F-O10-12 | golden | `MODEL_UNATTESTED`; usage still recorded |
| provider error the breaker does not recognise | F-O10-13 | golden | dispatch stopped and reported |
| Claude episode with compaction whose `modelUsage` carries an undeclared model key | F-O10-14a | golden + replay | `MODEL_UNATTESTED` |
| … clean counterpart with declared keys only | F-O10-14b | golden + **live** (F-O7-15's episode) | accepted; attested by aggregate |
| added: every main request on a declared auxiliary model (the all-auxiliary main response) | F-O10-15 | golden | `MODEL_UNATTESTED` |
| added: main on the seat with a declared auxiliary role's usage in the aggregate (mixed valid) | F-O10-16 | golden + **live** | accepted |
| added: `placed_anchor` left at entry level after migration | F-O10-17 | golden | `FIELD_NOT_MIGRATED` |
| added: an unlisted ledger reader planted in tracked code, building the path from components | F-O10-18 | golden | discovery finds it and the inventory check fails naming it (N#15) |
| added: a non-actor call without a reservation or without both caps | F-O10-19 | golden | `RESERVATION_MISSING` / `CAP_MISSING` |
| added: an HTTP-drop recording; an HTTP-retry recording | F-O10-20a/b | replay (probe 9) | interrupted attempt with provisional usage; two posts reconciled to one stream |
| added: a non-actor (judge) call stopped by the token cap mid-stream; one stopped by the compaction cap; a fault-injected send after the freeze boundary with no response start | F-O10-21 (×3) | **live** + golden (WP-02 done-when 5) | `budget_stopped`, tree frozen (verified) then killed and verified by pid and start time, no outgoing request after the freeze instant; the planted post-boundary send → `STOP_BOUNDARY_VIOLATED` (N#0, N#9r3) |
| added: `ko/claude/CLAUDE.md` grows while `claude/CLAUDE.md` is unchanged | F-O10-22 | golden (WP-14) | passes; `KO SIZE` disclosure emitted (N#12r3) |

**No change** (WP-21)

| Plant | Fixture | Realization | Expected |
|---|---|---|---|
| a clean window whose correct result is no proposals | F-NC-01 | golden + **live** (a **nonempty, source-complete** real window) | run succeeds S0–S12 and reports it; credited only when both predicates hold and no proposal of any kind was produced; counterpart with one planted candidate yields one proposal |
| added: a window whose only proposal is personal (no core proposal) | F-NC-02 | golden + **live** when RH-2 meets one | **not** credited as no-change; the result preserved; the core path continues elsewhere (N#4r5) |

Coverage of the design's own list: every plant sentence of §18 appears above exactly once (O0 2,
O1 27 + the §14-7 live row, O2 5, O3 15 + generated, O4 14, O5 14, O6 3, O7 27, O8 14, O9 19, O10 16
+ generated, No change 1), the §3.2 control list appears as F-O4-10a–j, and the rows review rounds
1 and 2 added are marked "added" (round 2's carry their `N#`: F-O2-09/10, F-O4-14, F-O5-17,
F-O6-06, F-O7-21f, F-O7-32, F-O8-10e, F-O8-19–21, F-O9-20, F-O10-21; round 3's F-O10-22 carries `N#12r3`). WP-23's bijection check holds
`plants.json` to this list; a plant the implementer cannot realize is a redesign trigger (§5), not
a deleted row.

### 4.2 How the rehearsal runs

1. **Preflight** (`distill.py preflight`): P2 pins, P4 secret-slot check, P7 tools, P5 root, the
   auxiliary-role measurement per host version (S-7), then the seven §14 checks live with receipts.
   Any failure stops here.
2. **Golden and replay sweep** (`distill.py rehearse --realization golden,replay`): every such row
   and its counterpart, in one process, with the fake hosts declared. Zero model cost. Output: the
   plant verdict table.
3. **Live plant set** (`--realization live`): the rows marked live above that stand alone (O4 runner
   and capture rows, O7 isolation and accounting rows, O10 frames-silent canary, O1 compaction and
   provenance rows), grouped by host and WP so each group fits one usage window.
4. **RH-1, the plant run at the contract scale** (WP-23 done-when 4): the seeded fixture corpus
   yields the six intervention kinds; S4–S7b run live over it (the O5 semantic rows and the §6.5
   control population through the real judges); R is built and validated; S8 runs every cell at
   six cases × two repetitions × four strata × the configurations each kind needs, with the shared
   regressions and interaction cases; the owner decides the rehearsal review; S10b runs pass 1 over
   the seven approved items, the planted author-side failure (F-O8-11) returns and pass 2
   re-confirms the six (that fixture's schedule; §10.3's bound is at most one repeat per item);
   the second author-side item (F-O8-10e) completes application and executor verification; S11
   applies in the fixture clone under the destination manifest and verifies delivery through fresh
   activated sessions from the fixture install; S12 closes on the clone's ledger; the
   owner-destination guard is equal before and after. Episode and token figures: §8.2.
5. **RH-2, the real-transcript path at the contract scale** (WP-23 done-when 5): the window is
   §18's source scope — about three days, about ten sessions — S1–S2 over the owner's real homes
   (read-only), S3 with stitch calls, S4 with the full lifecycle intake (142 legacy entries),
   S5–S7b, R, S8 for the run's own core proposals at the contract scale (one real core item in the
   budget, D-2 as decided; no eligible core proposal → the window's actual result stands, F-NC-01 is
   credited only on its own predicates, and the path continues on a second declared window or a
   labelled historical subject, N#5r4, N#4r5), S9 render, S9b, the owner's decision lines for the rehearsal only, S10b, S11–S12 in
   the fixture clone under the destination manifest, discarded after the record (nothing applied
   to the owner's library in rehearsal; the guard proves it). The nonempty clean window of
   F-NC-01 is a second RH-2 window chosen for having no eligible candidates.
6. **Measurement**: every §16 parameter recorded with denominators (per-stage usage and wall time;
   per-class p95 episode cost with n; Codex warm-up share; cache share; sweep reuse rate;
   usage-window consumption per provider; R distance; S1 unknown-independence share; Claude
   compaction overshoot class; denial-log latency; S9b regeneration rate; owner review time).
7. **Record**: a dated file `design/session-distill/<date>T<time>--<sha>--rehearsal.md` with the
   plant table verdicts (fixture, realization, verdict, receipt ids for live rows), the §14 results,
   RH-1's and RH-2's manifests, results and confirmation records (every cell with its full
   denominator), the measurements, the token-sweep result (0 files), host versions, and the budget
   S0 will adopt.
8. **Cross-provider review** of the record (X): packet = the record, `plants.json`, the receipts
   folder, §18; the question asked is which plant could have passed vacuously, which live row is
   missing, and which cell is below its denominator. Receipted; `plan_from_it`-style verdict required.
9. **Owner authorization**: the owner's line in the record, with the S0 budget (tokens per stage,
   windows, `account.extra_usage`) derived from the measurements.

### 4.3 Evidence that authorizes the first production run

All of: (a) preflight green with receipts on the pinned host versions; (b) every golden, replay
and live plant failed by name and every counterpart passed — no row skipped, no row left golden or
replay where §4.1 marks it live, no `smoke` row counted; (c) RH-1 and RH-2 completed at the contract
scale with every cell at its full §8.7 denominator, RH-1's two F passes (F-O8-11's schedule) and
the successful author-side application (F-O8-10e) recorded, every **consumed** result passed by
the gate and every rejected or interrupted attempt retained, classified (`failed`/`unknown`) and
accounted (N#2r5), and the token sweep at 0; (d) measurements present with denominators, including at
least one measured usage-window consumption per provider and per-class p95 with n above the
declared minimum; (e) the X review receipt showing a fresh dispatch of the declared packet on
gpt-6-astra/xhigh through the hermetic capture profile; (f) the owner's authorization line and the
S0 budget; (g) `git status --porcelain` empty on the checkout and the umbrella green at the HEAD
the record names; (h) the owner-destination guard equal before and after both runs and every crash
injection, with both runs' `destinations.resolved.json` inside the fixture root. A missing item is a
missing authorization, not a caveat.

---

## 5. Redesign triggers and stop conditions

**Back to the design** (the owner decides; the plan does not improvise a contract):

| Trigger | Design section reopened |
|---|---|
| A §14 check fails on the pinned hosts in a way no WP can fix without changing a contract: Claude `--setting-sources ""`/ancestor behaviour differs from probe 4, `response.model` frames absent on 0.163.0, `codex debug prompt-input` rendering unavailable | §3.1, §3.2, §13.3 |
| The contract-scale rehearsal (§8.2) or the measured usage-window consumption cannot carry the §2 scale within a cadence the owner accepts | §2, §8.6, §16, §18 (D-20261020-457ea5 closed the lighter scale; option 2 of D-1 is the design change) |
| R−i fails to isolate more than a stated share of core items (entanglement) or R's distance from B exceeds what the owner accepts | §8.6, D-20261020-8166e7 |
| A ledger consumer (S-4) cannot be served by the derived compatibility projection without changing its own contract | §12.1–§12.2 |
| Codex compaction's file behaviour (first measured in preflight) breaks the lineage rule's assumptions | §5.3 |
| A host version's auxiliary requests cannot be measured as declared auxiliary roles (S-7) — the main or child seat cannot be attested per response | §3.2 |
| The hermetic Claude profile cannot be shipped under the repository's gates (hygiene, endpoints, surfaces) and must become author-side | §3.1, §15, `SURFACES.md` |
| Codex app-server lacks `thread/start`/`inject_items`/`resume` equivalents on the pinned version | §8.2 |
| Fresh install per episode or the installation receipt breaks a `content_ref` consumer | §6.3 |
| The first real usage-limit signal carries no structured field the breaker can key on | §13.2 |
| The unified log's denial latency, measured in WP-16, is so long that concurrent episodes cannot be attributed within a run's elapsed time | §8.1 |
| A §18 plant cannot be realized by any fixture (not merely not yet) | the outcome's section |

**Stop conditions** (work halts until the owner is told; no implementer judgment call):

- any plant passes unnoticed or any clean counterpart fails in the rehearsal (§18's own rule);
- the token sweep finds a file, or a secret reaches argv, a log, or an artifact;
- a cell is created under the owner's `HOME`, or a static check is bypassed to make a run proceed;
- the breaker fails to stop a provider on a recognised signal, or a retry is observed against a limit;
- a live model call is made outside `runlib/dispatch.py`, or without a reservation and both caps;
- a **view-window call's** observed input exceeds 120k (`INPUT_BOUND_EXCEEDED`): a host change — the run stops, in rehearsal and in production, until the host allowance is re-measured and the declaration amended (the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md`; N#0r4, N#0r5); calls without a view window — R authoring above 120k by contract (§8.6) — are outside this rule;
- an application touches the owner's library outside S11's journal, or a global line is added;
- `git status` on the checkout shows a change no WP's journal accounts for;
- two consecutive attempts at the same WP fail its done-when for the same cause.

**Settled in the plan** (not design questions): module and file names; failure-code names other
than `MODEL_UNATTESTED` and `frames_blind`; Python subcommands instead of `.js` stage scripts
(S-3 records the reasoning, but the design's §3 already names one subcommand per stage); `zstd`
by subprocess with a pinned absolute path; `jsonschema` as the validator; the production cell root
path; `.gitignore` for `session-distill/out/*/`; the plants table format; the p95-per-class
definition (stage, seat, case type); the reviewer seat per WP; two implementer lanes in separate
worktrees; the development smoke scale (WP-19) as a non-evidence run; the supervisor's placement in
WP-02.

---

## 6. Design questions

The two drafts raised seventeen questions between them (Claude S-1–S-16, Codex Q1–Q5). Review
round 1 re-read each against the code and the design; the synthesizer then corrected S-4, S-7 and
S-16 on the reviewer's findings (2026-10-20, not owner decisions; the owner may reverse any of them).
Fifteen are settled below with the reading this plan takes; S-16 is deleted; D-1 and D-2 were the
owner's and were **decided on 2026-10-21** (§6.2 keeps the options as the record of what was chosen
between); the input bound was settled by the owner's amendment of design §5.4 on the same day
(`2026-10-21T0026--cc0498f--input-bound-amendment.md`).

### 6.1 Settled in this plan

| # | Source | Question | Reading this plan takes, and why |
|---|---|---|---|
| S-1 | DQ-1 | Design §15 names a new hermetic Claude runner and keeps `claude-run.sh` "not hermetic" | `claude-run.sh` gains a `--profile inherit\|hermetic` vocabulary like `codex-run.sh`'s, with `inherit` byte-identical to today. The §3.1 contract is unchanged; one adapter per host with one profile vocabulary is fewer concepts and one resolution path (`review_wrapper_command`). Its helper ships with its own `files[]` entry and deploy line (F33). |
| S-2 | DQ-2 | The distill seats (claude-sonnet-5-5, claude-opus-5-5, gpt-6-luna) are in neither `hosts.*.models` nor the prompting guides' `targets:`, so no gate covers them | P6: land `feat/prompting-rederive` (`5846e4a`), add the seats to `launch/agent-launch.toml` and the guides' `targets:`, add the two price rows. **And** the runtime half the design already requires (§8.4): `distill.py declare` checks every `run.json` seat — stage seats and the observed or fallback actor strata — against the guides' `targets:` through the gate's own reader and refuses an uncovered seat (`SEAT_UNCOVERED`), because `launch/check-prompting-targets.sh` reads only the launch config (F30). |
| S-3 | DQ-3 | §15 names `read.js`, `form.js`, `judge.js` | Python subcommands with packet templates (§3: one subcommand per stage; D-20261020-bcba5e: no Workflow). The `.js` names are the reuse rows' legacy labels. |
| S-4 | DQ-4 | Schema 2's consumers | **Corrected in review round 1 (F14):** schema 2 follows §12.1–§12.2 exactly — `placed`, `placed_anchor`, `implementation` migrate into `destination` and the latest place decision's `applied` (or a `legacy_application` element), and the per-run `decisions[]` elements carry the design's full shape. The old consumers read a **derived compatibility projection** (`runlib/ledger_compat.py`, author-side; `learn/build-promotions.py` is author-side and imports it); `compose/instructions-state.py::ledger_summary` and `learn/ingest-learnings-export.py` read only fields §12.2 keeps. No field is duplicated as a second authority (F14). |
| S-5 | DQ-5 | Nudge fields | Keep `window_end` and `history_lines_total`; add `transcript_files_total`, `cadence_days`, `transcript_growth`; the cadence value is the purpose record's. |
| S-6 | DQ-6 | "Seat observed" | The model is attested per response and role; effort is recorded as requested and marked `host-reported` only where the host reports it (Codex frames carry `reasoning.effort`; Claude does not echo it). `benchmarks/receipt.py`'s validator changes from "must be `unverified`" to `∈ {unverified, host-reported}` with the Codex-only condition, so WP-17 and this reading agree (F30). |
| S-7 | DQ-7 | Claude Code makes auxiliary requests on a small model (`benchmarks/dispatch.py` `AUXILIARY_MODELS`), so `modelUsage ⊆ {seat}` would fail every call | **Corrected in review round 1 (F08):** attest **by role** — every main and child response must be on its exact declared seat (Claude per request and message; Codex per joined response); auxiliary models are allowed only as separately declared auxiliary roles whose usage appears in the aggregate, measured per host version in preflight and declared in `seats.json`; the all-auxiliary main response is a negative control and the mixed valid counterpart its pair (F08; WP-02 done-when 2; F-O10-15/16). The earlier "seat ∪ auxiliaries" predicate is withdrawn. |
| S-8 | DQ-8 | Distill receipts and the launch-plan receipt fold | `method_id = distill/<stage>/<call_id>`, stored under the run directory, adjudicated by WP-02's gate, never folded into a launch plan; `check-receipt-chain.py` is read before WP-02 to confirm it does not scan the run directory. |
| S-9 | DQ-9 | State homes | The design's four homes stand; `session-distill/out/*/` is ignored entirely; dated run summaries without transcript content go to `design/session-distill/`; `run-record.json` is not tracked. |
| S-10 | DQ-10 | Does the global gate cover `ko/claude/CLAUDE.md`? | English file only (the design's literal); Korean growth is disclosed, never blocked — the `KO SIZE` disclosure of WP-14 done-when 1 (N#12r3). |
| S-11 | Codex Q1 | §9 makes each review render immutable; §10.1 has the owner write decision lines | An immutable render plus `decisions.ko.v<n>.md`, an editable copy whose non-decision bytes must equal the render; approvals carry §10.1's `review_version_sha` and add `decision_input_sha` (WP-20). |
| S-12 | Codex Q2 | The probe's static check skips file classes and allows toolchain paths | A **closed inspection scope** and allowlist as data with a reason per entry; an effective configuration reference that cannot be inspected makes the episode `invalid`, never green with a disclosure; only inert literals in prose are disclosure; owner, sibling and output paths never allowlisted (WP-16; F20). |
| S-13 | Codex Q3 | An intervention in `benchmarks/` could change its own judge | The evaluator is the **closure** — benchmark dispatch/scoring/manifest/validation, the driver and `runlib/`, the hermetic runners and helpers, the scorers' packets and schemas, item identities — hashed and copied once per run, with every episode run from the frozen copy; a change that alters acceptance semantics is deferred to a new evaluator revision (WP-19; F23). |
| S-14 | Codex Q4 | One commit per item vs items that are only valid together | The ordered-tree check is defined in WP-12 and run in S7b before the core freeze; it is **re-run on the exact approved F operation order** before confirmation (WP-20) and before application (WP-21); a full set valid whose approved subset is not → the subset is returned; never squashed, never past the hook (F17). |
| S-15 | Codex Q5 | The first p95 reservation of a class has no measurement | A declared calibration tranche at concurrency one with probe-derived seeds, replaced by measured p95s before broad dispatch — enforced in the **dispatch supervisor of WP-02**, which every live call from WP-03 on goes through, so no development call precedes it (F09). |
| S-16 | DQ-12 | `benchmarks/run.py` ties its guard set to an owner approval date | **Deleted in review round 1 (F29).** `GUARDS_APPROVED` records the owner's approval of per-item `guards` classifications; no isolation-guard hash or refusal exists in the code. Harness changes get the plan's own isolation controls and owner review (WP-16, WP-17). |

### 6.2 For the owner

**D-1 — the scale of the rehearsal's test stage.** The design fixes the broad scale (§2: six cases
× two repetitions × four strata × five configurations for core items), the acceptance rule (§8.7:
a cell starts with two episodes and a one-repetition cell has no verdict), the confirmation rule
(§10.3: a failing item returns and confirmation repeats at most once per approved item), and requires the rehearsal to carry six intervention kinds "through their
arms" and through "approval, F confirmation, application, and delivery verification", plus "one
complete evidence-to-test path on real transcripts" (§18). Read together, these fix the rehearsal's
scale: an intervention carried through approval and application has to be **accepted**, and
acceptance needs every cell at its full denominator. The earlier draft's "reduced" default — one
repetition, the intervention kinds in a golden matrix — could not satisfy that contract and was
withdrawn in review round 1 (F26). The plan is written for option 1.

**Decided by the owner on 2026-10-21: option 1.** The options below stay as the record of what was
chosen between.

- **Option 1 — run the rehearsal as designed (default).** RH-1 carries the six intervention kinds
  live at the contract scale and RH-2 runs the real path at the contract scale (§4.2, WP-23). From
  the one manifest of §8.2: about **1,980** S8 actor episodes and **1,030** confirmation episodes
  in RH-1 (seven items — four core, one personal, two author-side, of which one completes
  application and one fails F and returns; N#3), about **810** actor and confirmation episodes in
  RH-2 (one real core item at §18's source scope), one scoring call per episode, about **5,350**
  Codex warm-up requests, S3 on byte-bounded views (≈25 + ≈72 calls); in all about **165–298
  million input tokens and 12–22 million output tokens**, roughly 1.0–1.5 times one production run (§16), over several usage windows (estimated
  5–8 calendar days, provisional until the first window is measured; §18's "about three days, about
  ten sessions" is the source scope RH-2 reads, not this duration — N#19). What it buys: before the first production run, the acceptance rule, the F passes, S11
  and delivery verification have each run at scale on a corpus whose correct answers are known,
  and the usage-window fit of the broad scale is measured rather than assumed.
- **Option 2 — amend design §18** so that some intervention kinds are exercised only through
  golden or replay matrices (the deterministic aggregation, the F-pass logic and S11 on synthetic
  results), with one kind live at the contract scale. This is a **design change**, recorded as a
  decision that supersedes §18's wording. Its loss, stated plainly: the first production run
  becomes the first full-scale run — the first time the §8.7 acceptance, the F passes, S11 and
  delivery verification execute at scale is on the owner's real library, with no rehearsal result
  at that scale to compare against. Its saving: roughly 60–70% of the rehearsal's model spend and
  3–5 calendar days.

**D-2 — how many real core items RH-2 tests.** RH-2's budget counts one real core item at the
contract scale (≈635 S8 and ≈175 confirmation episodes, the shared regressions included). A
further real core proposal **in the same run** shares those regressions and adds about **331**
episodes ((240 + 48)·1.15: its own cells on five configurations plus its F cells) plus ≈55 per
interaction case it introduces, ≈66 calibration labels, 6 leakage reviews and its R−i build —
about 12–23M input and 0.7–1.6M output tokens with scoring and warm-ups (§8.2, from the same
manifest; the earlier "about 810" counted the shared regressions twice — N#19). An item admitted
by adjudication in the second pass is `awaiting_R`, enters no F this run, and is tested on three
configurations: 6·4·2·3 = 144 base episodes, ≈**166** with the adaptive share (N#11r3); its F
confirmation (≈55) is priced in the later run where it becomes eligible. A separate run is a new
RH-2 (its full subtotal) and is never implied by one more item. Default: test one — the one ranked first by §7.5 — and carry the window's other real proposals to the first production run untested, listed in the rehearsal record; the alternative is to test every real core proposal the window produces, with the budget opened per item before S8. **If the window yields no eligible core proposal** (N#5r4, N#4r5): the first window's actual result is preserved whatever it is (personal or author-side proposals included); F-NC-01 is credited **only when its own predicates hold** — a nonempty, source-complete window with no proposal of any kind — and a window that produced a personal proposal only is its negative counterpart (F-NC-02, not credited); RH-2's complete evidence-to-test path then continues on **another genuine transcript window**, declared in the record (its S1–S7b rows added, ≈13M input), or — if the owner prefers — on an explicitly labelled **historical, already-evidenced intervention** (a ledger proposal whose evidence exists, marked `historical` in the record) with its own R and full matrix; a proposal is never manufactured and the no-change run never counts as the complete path.

**Decided by the owner on 2026-10-21: test one real core item (the default).** The alternative above stays as the record of what was chosen between.

The plant table (§4.1), §4.2, WP-19, WP-23 and §8 are consistent with option 1, the owner's choice.
The option-2 rewrite list — §18 amended first, then F-O7-11, F-O8-02, F-O8-10a–e, F-O8-11, §4.2
step 4, WP-23 done-when 4 and §8.2 — stays as the record of what the other choice would have
changed.

### 6.3 Review round 1: findings not applied

None. All 38 findings (F01–F38) and the 17 open items were applied in the work package or section
they name. Two findings were applied with a correction to their own wording, recorded here so the
next reviewer does not re-raise them:

- **F36 (`log`).** The finding says macOS `log` is an executable, not a shell builtin. Both are
  true at once: `/usr/bin/log` is the unified-log executable, and in this repository's zsh tool a
  bare `log` resolves to zsh's builtin (`which log` prints "shell built-in command"), which is how
  the plan's earlier sentence arose. The plan now names `/usr/bin/log` wherever the unified log is
  read (P7, WP-16).
- **F11 (judgment reuse).** The finding asks that reuse be scoped "to the allowed
  run/reference-point boundary". Design §6.2 licenses reuse **across reference points** on the full
  packet key including seat and says nothing about reuse across runs; the plan keeps the
  within-run cross-reference-point reuse the design names and removes the cross-run reuse the
  earlier draft had added (WP-11 done-when 4), rather than removing reuse altogether.

### 6.4 Review round 2: findings not applied

None. All 20 findings (N#0–N#19) and the 27 partial open items were applied in the work package or
section they name (each marked `N#n`). Five were applied with a reading settled here, recorded so
the next reviewer does not re-raise them:

- **N#9 (tool boundary).** The finding asks to confine `Read`/`Grep` to the manifest directory.
  The host path-scopes `Read` rules but not `Grep` or `Glob`, so the producing profile grants
  `Read` alone and leaves search to code (WP-06's index, carried in the packet) — a smaller tool
  surface rather than a second mediation mechanism; inside harness cells the WP-16 sandbox stays
  the kernel-level second boundary. The host's refusal of an uncovered tool request under `-p` is
  measured live (WP-03 done-when 4), not assumed.
- **N#14 (cutover).** The finding offers a compatibility adapter for the old CLI or moving the
  incompatible rewrite into the cutover commit. The plan takes the second: the old `merge-ledger.py`
  **writes** schema-1 rows, so an adapter would be a second producer of ledger entries; instead
  `ledger_compat` reads both schemas (readers switch early), the old documented invocation is
  exercised until the cutover, and the data moves once, in the commit that replaces the runbook.
- **N#17 (hint sequence).** The finding leaves open whether §7.1 licenses filtering view-basis
  windows out of the sequence. No such clause exists in §7.1, so the plan reads "three consecutive
  windows of basis source" chronologically (WP-21 done-when 8); the owner may license filtering by
  amending §7.1.
- **N#19 (RH-2 scope).** The earlier 40-session / 80-window assumption was the plan's own
  inflation; RH-2 is now sized at §18's scope (about ten sessions, ≈20 views), which lowers its S3
  and per-candidate rows, and the calendar estimate is stated apart from it.
- **N#6 (review bootstrap).** The finding asks to define the initial review executor or to separate
  landing from completion; the plan does both — §2's bootstrap paragraph and §3's live-verified
  milestone for WP-02 — and derives §3's graph and longest path from the Dependencies lines by a
  stated rule.

### 6.5 Review round 3: findings not applied

None. All 13 findings (N#0r3–N#12r3) and the 11 partial open items were applied where they land.
Readings settled while applying them:

- **N#0r3 (input bound).** Superseded on 2026-10-21 by the owner's amendment of design §5.4 (the
  record `2026-10-21T0026--cc0498f--input-bound-amendment.md`): the driver's part is bounded in bytes, the host's part is a
  declared allowance verified per call, and no complete-request guarantee is claimed; the
  two-measurement determinism check this bullet described is withdrawn (round 4, N#0r4). The
  bytes-per-token ratio survives only as a packing diagnostic. Byte-bounded views hold a third to a
  quarter of a 120k-token view, so S3 makes three to four times as many calls; §8 carries the added
  overlaps and per-call overhead, with total read tokens unchanged.
- **N#1r3 (owner files).** Every plant that wrote to an owner path is gone: the guard's detection
  runs on a fixture-owned stand-in, the real-owner guard only hashes, escapes are proven refused
  before any write, and the packaging and delivery installs name a scratch home. A grep of this
  plan for owner-path writes now finds read-only accesses only (census, inventory frozen copies,
  the P2–P4 checks, the guard's hashing).
- **N#3r3 (follow-up path).** Its live rows share the seeded corpus's views; the added cost is the
  forced expansions and the instances' judgments (§8.2's S3 row), not a second corpus.
- **N#8r3 (historical records).** The cutover scan excludes `decisions/decisions.jsonl` and dated
  `design/` files by path and fixes the two stale current references as named edits; rewriting a
  decision record would be the wrong repair.

### 6.6 Review round 4: findings not applied

None. All 7 findings (N#0r4–N#6r4) and the three partial open items were applied where they land.
Readings settled while applying them:

- **N#0r4 (input bound).** Applied as the owner's amendment of design §5.4 (the record
  `2026-10-21T0026--cc0498f--input-bound-amendment.md`), not as the finding's own fix: the finding asked for a defensible
  pre-send bound over the complete request; the owner closed that route and declared the host's
  part an allowance verified per call. The plan cites the amendment wherever the bound appears and
  claims no complete-request guarantee anywhere.
- **N#3r4 (schema policy).** The closed-object and supported-keyword rules are a lint in
  `validate.py`, run after `check_schema`; this is not a second validator — instance validation is
  still jsonschema's — so the round-1 rule (F32) stands.
- **N#5r4 (zero-proposal branch).** The default continuation is a second genuine transcript window;
  the labelled historical subject the Codex draft allowed is kept as the owner's alternative, never
  as something the run selects on its own.

### 6.7 Review round 5: findings not applied

None. All 6 findings (N#0r5–N#5r5) and the four partial open items were applied where they land.
Readings settled while applying them:

- **N#0r5 (window scope).** Applied as the owner's corrected amendment (the record
  `2026-10-21T0026--cc0498f--input-bound-amendment.md`): `view_window` is a dispatcher argument, so the scope is a
  structural property of each call rather than a convention; the R-authoring counterpart uses
  probe 7's retained capture (≈136k input).
- **N#1r5 (retry).** The scoring-only retry of round 4 is withdrawn; the unscored episodes consume
  their pre-bound retry slots and the manifest records them there.
- **N#4r5 (no-change credit).** "No eligible core proposal" and "no proposal" are different
  predicates; only the second, with source completeness, credits F-NC-01.

---

## 7. Deferred

| Item | Reason | Returns when |
|---|---|---|
| Windows hosts (the native installer workflow in `.github/workflows/windows.yml`) | The design, probes, cells, and sandbox are macOS-bound (`sandbox-exec`, unified log, `/Users/Shared`) | a Windows transcript corpus is in scope |
| Growth gate on `ko/claude/CLAUDE.md` | translation length is not the design's rule (S-10) | the owner asks for it |
| Codex compaction lineage beyond the first measurement | the design classifies it only after preflight measures it | preflight records the behaviour; WP-05's fixture then pins it |
| A user-runnable distill in the shipped package | `session-distill/` is author-side by `check-package.sh`, the guide is `audience: author`, and the design keeps the driver there; WP-22 corrects the `AGENTS.md` §10 sentence that says otherwise | the owner decides to ship the driver (then WP-03's profile and the hermetic contracts are already shipped) |
| Reuse of `benchmarks/tier/` (`usage.py` pricing, `budget.py` reserve, `pin.py`) | not named by the design; WP-18 ports the probe prototypes, which were measured on the actual channels; their pure parsers stay importable | WP-18 finds a cheaper port there (then record the reuse decision) |
| Sweep batching beyond the shard/group sizes in `run.json` | §16 names batching as the lever but the rehearsal measures the reuse rate first | the measured sweep share exceeds the actor-episode share |
| Multi-machine or multi-user census | product scope (team sharing) is a separate initiative, stopped 2026-10-20 (D-20261020-05c243) | a second machine's transcripts are in scope |
| Selection evidence for desktop-app sessions | the design accepts "unclassified" for sessions without a pin (§17) | a desktop pin route exists |
| Merging `decisions/` into distill | AGENTS.md §10 leaves it open; the ledger is author-side and distill's product is the ledger, not the decision log | the owner reopens it |
| The real usage-limit shape | cannot be scheduled; the breaker records the first one as evidence | the first real limit occurs |
| A second rehearsal corpus (RH-1 with a different seeded ledger) | one seeded corpus is what §18 asks; a second would measure variance the design does not require | the first rehearsal's p95 classes show a spread the owner wants bounded |

Closed, not deferred (owner decisions already recorded): a metering proxy, a hard spending
ceiling, Workflow subagents for Claude-side calls, the lighter test scale, skip judgments as
evidence of absence, the reduced rehearsal default (withdrawn, F26), the guard re-approval
prerequisite (deleted, F29).

---

## 8. Cost and time

Model spend counts only live and smoke rows; golden and replay rows cost nothing. Both providers
are reached by subscription login (no API keys), so the binding quantity is usage-window
consumption, which the repository cannot tell: the first live S3 window (WP-08) measures
`rate_limit_event.utilization` per input token on Claude, and the Codex canary measures its limit
headroom; every later estimate is `tokens × measured utilization per token`. The placeholder rate
of §16 (10 USD / M input, 50 USD / M output) is used below only to express volume on one scale.
These are **estimates of volume with the assumptions stated**, not upper bounds: retries,
adaptive repetitions beyond the assumed share, and measured overshoot are outside them (F37).

### 8.1 Development tests (live and smoke rows during WPs)

| WP | Live calls | Input tokens | Output tokens | Provider | Note |
|---|---|---|---|---|---|
| WP-03 | ≈15 hermetic calls (sonnet-5-5) incl. `max_tokens`, inherit-profile and contamination plants | ≈100k | ≈12k | Claude | ≈3.2k floor per call |
| WP-04 | ≈10 canaries (gpt-6-luna) + 4 (gpt-6-astra) incl. the aborted stream and contamination plants | ≈280k (warm-ups 11.6–16.4k each) | ≈12k | Codex | frames-silent control included |
| WP-08 | 3 byte-bounded views + 1 stitch call + kill/resume control | ≈150k | ≈15k | Claude | ≈30–40k tokens per view (N#0r3) |
| WP-09 | 1 | ≈60k | ≈8k | Claude | |
| WP-11 | A 1, B 1, sweeps 1 + 1, cross-review 1 | ≈130k | ≈18k | both | |
| WP-12 | 1 + 1 | ≈60k | ≈8k | both | |
| WP-16 | ≈8 denial-plant episodes + the latency measurement (no model) | ≈180k | ≈15k | both | incl. 4 Codex warm-ups |
| WP-17 | 2 activated episodes + 2 children + the route cases (≈8 short episodes) | ≈220k | ≈20k | both | |
| WP-18 | 2 capped episodes with forced compaction | ≈150k | ≈15k | both | overshoot class re-measured |
| WP-19 smoke | 318 episodes (`6·4·2·5 + 13·1·2·3`), scoring, 6 cases authored, 190 calibration labels, leakage | ≈16.6M (episodes 8.0M, scoring 2.5M, warm-ups ≈5.0M, authoring/labels 1.1M) | ≈1.1M | both (≈55% Claude) | **not evidence**; seeds the calibration tranche |
| WP-20 | S9b 3 rows + 1 regeneration | ≈45k | ≈8k | both | |
| WP-21 | 1 applied item + 1 actor for delivery | ≈30k | ≈3k | Claude | |
| **Development total** | | **≈18.0M** | **≈1.25M** | | ≈ 250 USD-equivalent at placeholder rates |

### 8.2 Rehearsal (WP-23), at the contract scale — one manifest-derived calculation

Symbols as §16: k = 6 cases, s = 4 strata, r = 2 repetitions, a = 0.15 adaptive share, 13 shared
regression scenarios in three configurations (B, A, R), five configurations for core, two for
personal and author-side. Assumed sizes per §16: actor episode 12k–40k input / 1.5k–4k output;
scoring 8k / 0.5k; calibration and leakage 6k / 1k; Codex warm-up 11.6–16.4k input, no output; R
authoring 152k / 26k (gpt-6-astra, Codex); R−i 40–52k / 0.5–7k; validation shards 7–29k /
0.8–3.5k (claude-opus-5-5, Claude). WP-19, WP-23, §4.2, §6.2 and this table cite these figures and
no others. The 120k rule of the amendment record `2026-10-21T0026--cc0498f--input-bound-amendment.md` applies to the S3
view-window rows only; R authoring exceeds 120k by contract (§8.6) and is bounded by its seat's
context capacity (N#0r5).

**RH-1 (seven intervention items of six kinds on the seeded corpus):** c = 4 core (reduce,
re-deliver, route-carried, executable-carried), p = 1 personal, u = 2 author-side (one completes
application, one fails F and returns — N#3), m = 4 interaction cases (authored between core items;
an author-side item adds none). Every count below is one calculation from these symbols (N#19); a
changed symbol changes every row, and §4.2, WP-19, WP-23, D-1 and D-2 quote these rows and no
others.

| Component | Calls | Formula → count | Input tokens | Output tokens |
|---|---|---|---|---|
| S8 actor episodes | E1 | (c·k·s·r·5 + (p+u)·k·s·r·2 + 13·s·r·3 + m·s·r·5)·(1+a) = (960 + 288 + 312 + 160)·1.15 ≈ **1,978** | 23.7M–79.1M | 3.0M–7.9M |
| S10b confirmation, F-O8-11's two passes | E2 | pass 1 (n = 7, m' = 4): (n·k·s·r + 13·s·r + m'·s·r)·(1+a) = (336 + 104 + 32)·1.15 ≈ 543; pass 2 (n = 6, the failing author-side item removed): (288 + 104 + 32)·1.15 ≈ 488 → **≈ 1,030** (B reused from S8) | 12.4M–41.2M | 1.5M–4.1M |
| Scoring | E1 + E2 ≈ 3,008 | one per episode | 24.1M | 1.5M |
| Calibration | 5·(c+p+u)·k + 5·13 = 275 responses, labelled twice, +10% rework | ≈ 605 | 3.6M | 0.6M |
| Leakage review | (c+p+u)·k + 13 | 55 | 0.3M | 0.06M |
| R, R−i, validation | 1 build (+1 rework), 4 R−i, ≈30 shards, ≈10 diff confirmations | | ≈ 1.1M | ≈ 0.2M |
| S3 over the seeded corpus incl. the seeded follow-up path (N#0r3, N#3r3) | ≈10 synthetic sessions ≈ 0.8M content tokens → ≈25 byte-bounded views + ≈6 forced expansions + 10 stitch calls | ≈ 41 | ≈ 1.3M | ≈ 0.18M |
| S4–S7b, S9b on the seeded corpus (≈10 candidates) | judges, sweeps, proposals, reviews | ≈ 120 | ≈ 1.7M | ≈ 0.3M |
| Codex warm-ups | Codex-stratum roots (E1+E2)/2 ≈ 1,504 + their children ≈ 752 + Codex scoring of Claude actors ≈ 1,504 + authoring/review threads ≈ 40 | ≈ **3,800** | 44M–62M | — |
| **RH-1 subtotal** | | | **≈ 112M–215M** | **≈ 7.4M–14.9M** |

**RH-2 (real-transcript path, at §18's source scope):** a window of about three days, about ten
sessions — ≈20 views (two per session, as the probe views ran), ≈5 natural candidates plus the
**142-entry legacy intake** (F37) ≈ 147 candidates, ≈10 gap claims, one real core item (D-2). The
scope is what S1–S3 read; it is not a duration (N#19).

| Component | Formula → count | Input tokens | Output tokens |
|---|---|---|---|
| S3 views + stitch calls | ≈2.4M content tokens in ≈72 byte-bounded views (≈116k driver bytes each — 120k minus the declared allowance, ≈3.2k class — at ≈3.5 bytes/token, measured in RH-2, assumed here) + 10 stitch × 20k; the 52 extra calls add ≈7k each (five-turn overlap ≈2k + allowance and template ≈5k) and ≈0.5k output (N#0r3, N#0r4) | 3.0M | 0.18M |
| S4 (incl. the intake) | 1 formation pass | 0.6M | 0.08M |
| S6 judges A and B | 147 × 2 × 12k | 3.5M | 0.7M |
| Absence sweeps + cross-review | 2 groups × 24 shards × 2 providers = 96 × 25k; 10 × 15k | 2.6M | 0.6M |
| S7, S7b | 147 × 15k each | 4.4M | 1.2M |
| S9b (+10% regenerations) | 147 × 10k | 1.6M | 0.3M |
| R, R−i, validation | 1 build, 1 R−i, ≈30 shards | 0.9M | 0.15M |
| S8 for one real core item | E3 = (1·k·s·r·5 + 13·s·r·3)·(1+a) = (240 + 312)·1.15 ≈ **635** | 7.6M–25.4M | 1.0M–2.5M |
| S10b, one pass (n = 1, m' = 0) | (48 + 104)·1.15 ≈ **175** | 2.1M–7.0M | 0.3M–0.7M |
| Scoring | 810 | 6.5M | 0.4M |
| Calibration + leakage | 5·(k + 13) × 2 = 190; 19 | 1.3M | 0.2M |
| Codex warm-ups | Codex strata ≈ 405 + children ≈ 203 + Codex scoring ≈ 405 + B/S7b/S9b/sweep threads ≈ 537 | ≈ **1,550** → 18M–25M | — |
| **RH-2 subtotal** | | **≈ 53M–83M** | **≈ 5.0M–7.2M** |

**Marginal costs from the same manifest (D-2, N#19).** A further real core item **in the same RH-2
run** shares the 312 + 104 regression episodes and adds (240 + 48)·1.15 ≈ **331** episodes (its own
cells on five configurations plus its F cells), plus ≈55 per interaction case it introduces
((40 + 8)·1.15), ≈66 calibration labels, 6 leakage reviews, one R−i build and ≈10 diff
confirmations; with its scoring and Codex warm-ups ≈ 12M–23M input and 0.7M–1.6M output tokens.
An item admitted by adjudication in the second pass is `awaiting_R`, enters no F this run, and is
tested on three configurations (B, A, A−i): 144 base episodes, ≈**166** with the adaptive share
(N#11r3); its F confirmation (≈55) is priced in the later run where it becomes eligible. A separate
run is a new RH-2 at its full subtotal and is never implied by one more item. The earlier "about 810 per further item" counted the shared regressions twice.

**Rehearsal total:** ≈ **165M–298M input, 12M–22M output tokens** (≈ 2,250–4,000 USD-equivalent at
placeholder rates; about 1.0–1.5 × one production run's §16 range before contingency). Provider
split by input: Claude ≈ 55% (S3, the Claude strata, Judge A, opus validation and labelling), Codex
≈ 45% (warm-ups, Judge B, astra authoring, R authoring, astra scoring of Claude actors). The
rehearsal measures the cached share of Codex thread requests, which this table does not discount.

**Combined (development + rehearsal):** ≈ 183M–316M input, 13.7M–23.3M output. Usage windows: S3 and
the S8 matrices are the steps that can exhaust a window; the breaker defers and resumes, so the
cost of a limit is elapsed time, not loss. Extra usage stays **off** on the Claude account for every
step above (P3); if the owner leaves it on, S0 records accepted charges, and the placeholder volume
is not a price — vendor pricing, retries and overshoot are unknown to this plan.

### 8.3 Elapsed time

| Phase | Estimate | Basis |
|---|---|---|
| Implementation (23 WPs: 1 S, 6 M, 11 L, 5 XL) | ≈68 implementer sessions (S 1, M 1.5, L 3, XL 5 each); the longest dependency path is 44 sessions (§3), so two lanes finish in ≈44–48 session-slots; ≈15–18 working days at ≈3 sessions a day | sizes in §2; a session ≈ one context window |
| Reviews (X per WP ≈ 20–40 min, O on the owner surfaces) | ≈2 working days spread across the lanes | reviews require P1 first |
| Commit overhead | ≈4.5 min per commit (umbrella) × ≈68 commits ≈ 5.1 h | AGENTS.md §3 measurement, re-measure |
| Rehearsal, machine time | RH-1 ≈ 3,008 episodes × ≈4 min / 12 concurrent ≈ 16.7 h; RH-2 ≈ 810 × 4 / 12 ≈ 4.5 h plus S3 ≈ 15 min (≈72 byte-bounded views at 12 concurrent) and S4–S7b ≈ 1.5 h | §16 rates; provisional until the smoke is timed |
| Rehearsal, calendar | ≈ 5–8 days, bounded by usage windows, not machine time. §18's "a window of about three days, about ten sessions" is the **source scope** RH-2 reads (N#19), not an elapsed-time estimate; the two figures are separate | §8.2; the first measured window re-bases it |
| Owner review of `review.ko.v1.md` (RH-1 and RH-2) | separate; measured as "owner review time" | §13.4 |
| **Calendar** | **≈ 5–6 weeks** from P1 to an authorized first production run, usage windows permitting | |

The Codex draft sized the same work in engineer-days, not agent sessions: about 49–69 days plus 5–8
reviewer-days, or 5–8 calendar weeks with three coordinated workstreams. The two figures measure
different implementers; the first measured work packages (WP-01, WP-14, WP-02) re-base both.

**Owner time.** The first production run's review carries the legacy intake — the 142 incubating
entries that have no applied decision — besides the run's own proposals, and RH-2's review carries
it first; the Codex draft put that review at 5–10 hours. That figure is an estimate; RH-2's
render-to-decision time is the first measurement.

The production run itself is outside this plan's spend (§16: 17–19 h machine time plus owner
review, over the windows the rehearsal measures).
