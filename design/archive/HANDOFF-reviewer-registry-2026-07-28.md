# Handoff — pluggable review methods, post-migration hardening

Written 2026-07-27. All eight stages and the corpus half are done and pushed. The one decision this
handoff was written to hand over (§4.1) has since been taken, implemented, reversed when the fix
moved upstream, and merged (PRs #10, #11, #12). Nothing is half-built and nothing is in flight.

**§4.9 is done** (C20–C23): a user whose only reachable reviewer is their own model can now use
every shipped preset, degraded loudly rather than refused. Its review loop was closed by
**enumerating** the consumer set rather than sampling it — 13 functions touch the representation,
only 6 consume a `ReviewPlan`, and all 6 were fixed (C23).

**Next is §4.6 — an adversarial review of the DESIGN.** It is the largest unexamined risk and this
work is the evidence: both contradictions found here (§1 vs C7; the base/method role split) were
design-level and survived ten implementation review rounds. Implementation review cannot close it.

## 1. Current state

Stages 1–8 landed and the shipped defaults migrated: `balanced`, `fast-batch`, `deep-review` and
`session-distill` review **on the other family from either host** via per-host arms. `solo` and
`vanilla` stay legacy on purpose. The 192-cell legacy matrix has not moved by a byte.

After the migration, walking the launcher **as a user** — not reading it — turned up two real
defects that every green gate had missed. Both are fixed and gated (design `Corrections` C8, C9).
A third is recorded and deliberately **not** fixed (§4.1).

## 2. Pinned state

| | |
|---|---|
| Worktree | `/Users/kangmin/Documents/agent-bios` |
| Branch | **`main`.** PR **#10** (the onto override, 11 commits), **#11** (its follow-up review's gate fixes) and **#12** (the single-provider base fallback, §4.9) are all MERGED and their branches deleted. Nothing is in flight. |
| Settled HEAD | **`git rev-parse origin/main`** — deliberately not a literal hash. A pinned hash here went stale three times in one day as the direction changed, each time naming a commit whose behaviour the rest of this document contradicted. |
| Upstream | `origin/main`, in sync, tracked tree clean. |
| Tracked tree | clean |
| Author tier | HELM (`claude-opus-5` / xhigh) |
| Active fallback / family collapse | None |
| Untracked, NOT mine | `AGENTS.md`, `CLAUDE.md`, `research/`, `design/review-process-learnings/` — other sessions' work. Leave them; never `git add -A`. |
| Cross-repo | `~/Documents/ultracode-for-codex` PR **#23** (two evidence-gate docs) is OPEN, and that repo has already moved on to implementing fixes. Do not assume its `main` still matches what those docs describe. · `~/Documents/onto-mcp` has an **uncommitted, untracked** `docs/llm-override-consumer-findings.md` (four measured `llmOverride` findings, filed 2026-07-27) on branch `feat/observation-grant-stage2`. Nothing else there was touched; it is not ours to commit. |

**This machine is not representative.** `onto` and `ultracode-for-codex` are installed here; a
general user has neither. Capability-absent cells come from pointing `[capabilities.*].command` at
a non-existent name, never from uninstalling.

## 3. CONFIRMED this session (re-derived from real artifacts; anchors are grep-able symbols)

- **The migration is live and its A/B lives in the golden.** 253 cells: 192 legacy
  (byte-identical throughout), 49 composable scenarios, 12 `shipped/*`. The shipped cells are the
  only place a default-policy change is visible.
- **C8 — a Codex-only tool was bound to an Anthropic seat.** `[capabilities.ultracode].offers`
  claimed `hosts = ["codex", "claude"]`; that list is the set of hosts a reviewer can be **seated
  on**, and `ultracode-for-codex` takes its model catalog from the Codex app-server (no model id is
  hardcoded; `claude`/`anthropic` appear nowhere in its catalog module). Narrowed to `["codex"]`,
  and the two codex arms stopped binding the method.
- **C9 — the onto override was billing per token.** onto's per-call `llmOverride` REPLACES the
  seat, so omitted fields are lost. Measured through onto's own `normalizeLlmModelSwitcher`:
  `{provider:anthropic, model}` → `billing_mode: per_token`; adding `auth:"oauth"` →
  `subscription`; adding `effort` → preserved. openai already defaulted to subscription, so the
  asymmetry was the whole defect. The template sends both now, verified end to end by extracting
  the override string from the rendered contract and feeding it back through the switcher.
- **The binding screens no longer land on self-review.** `review_provider_options` orders
  cross-family first, then `REVIEW_HOST_PREFERENCE` (codex, claude), own family last;
  `choose_review_binding` defaults to the first family the main is not. Verified with a third
  provider present: from a Claude main the order is openai, the new vendor, anthropic.
- **An uninstalled method no longer looks installed.** `method_availability` marks it and carries
  the install command; it stays selectable on purpose.
- **`Register another reviewer…`** names the user-owned file and what a descriptor needs. The
  launcher selects and installs; it does not author (decided Q2).
- **Both reviewer descriptions were researched from the installed packages**, adversarially
  re-verified, and one was corrected after the tool's own doc refuted it — "requires a git repo" is
  the wrong diagnosis; no such check exists in that runtime.
- **C10 — the legacy path's exposure is permanent, and C9's openai row was wrong.** Measured
  through the real caller's input (`resolveSettingsChain` → `applyReviewLlmOverride` →
  `normalizeLlmModelSwitcher`), with a negative control proving the unfixed shape reproduces
  `per_token`: an openai override is an OVERLAY, not a REPLACE, so it never dropped effort — the
  whole defect lives on the anthropic REPLACE path, where an omitted auth defaults to `api_key`.
  A user-owned preset never migrates when the shipped defaults do, so `_cross_review_route` stays
  live for anyone who authored one.
- **C11 — the launcher now sends no `auth` at all, on either path, because onto fixed the default
  upstream.** Measured on a seat that states its auth explicitly, so the result holds under both
  the old and the new rule: omitting `auth` OVERLAYs and preserves a deliberate `api_key` seat;
  stating it forces oauth and drops `api_key_env`. `effort` is the opposite case and stays on the
  composable path. The 192-cell legacy matrix is byte-identical to `origin/main` again.
- **The upstream rule SHIPPED as onto 0.4.18 and was verified by behaviour, not by version.**
  12 checks against the installed build, no billed call: an omitted `auth` resolves
  `subscription/oauth` for both providers; metered stays reachable when the seat states it, by
  `auth = "api_key"` **or** by `api_key_env` alone; `defaultAuthForProvider` is now block-aware
  (`{}` → `oauth`, `{api_key_env}` → `api_key`), which closes the `effectiveRoute` concern raised
  during this work; a deliberate `api_key` seat keeps its auth, its `api_key_env` and its tuned
  effort under the override this launcher emits, and loses all three under the one it removed; and
  a zero-seat override throws `llm_override_reached_no_seat` while a one-seat contrast passes.
  End to end: the strings the launcher actually emits, fed back through onto's own parser, give
  `subscription/oauth` with `effort=max` on both hosts.

## 4. OPEN

1. ~~**DECISION PENDING — the legacy `llmOverride` prose carries C9's defect too.**~~ **CLOSED
   2026-07-27** (design `Corrections` C10 → **C11**, which reversed C10's fix; read C11, not C10).
   The exposure was live, not hypothetical — the deployed `profiles.toml` is pre-migration, and the
   user-owned `presets.local.toml`, which `install.sh` never overwrites, carries two `hybrid`
   presets that reach `_cross_review_route` permanently. **Settled state: `_cross_review_route`
   emits exactly `{provider, model}` — no `auth`, no `effort`.** onto now resolves an omitted auth
   to the subscription, so stating it would only override a user who deliberately chose metered.
   There is no `ONTO_OAUTH_PROVIDERS` and no `launcher_review_legacy_onto_auth`; the gate is
   `launcher_review_legacy_onto_override`, which pins the exact key set, the exact prose, and
   fail-closed rejection of a seat whose provider the review host does not speak for. The 192-cell
   legacy golden is byte-identical to `origin/main`.
2. **The `ultracode` instruction does not name a workflow.** `run {command} against a self-contained
   review packet` — the built-in `code-review` reviews the working tree, not a packet, and `task`
   has no review harness. Upstream is actively changing that tool, so **wait for it to settle**
   rather than rewriting against a moving target.
3. **Backlog — `grok`/`lmstudio`.** `ONTO_PROVIDERS` admits them; onto's `supported-models.yaml`
   has no model for either. The follow-on claim that they therefore "fail at review time, every
   time" was **corrected 2026-07-27** — onto's review-side support gate is scoped to runs carrying
   an override, so that does not follow and was never measured. Design `Open evidence` #7.
4. **No adapter emits receipts — but a producer now exists to consume.** `--verify-receipts` is a
   real verifier with no automatic producer, so achievement is still asserted by hand. **Changed
   2026-07-27:** onto's override now returns a `reached`/`dropped` seat report and discloses it
   with the resolved `billing_mode`, the effective auth, and whether that auth was defaulted, as
   `environmentWarnings` on both `onto_review_read` and `onto_prepare_review`. That is call-time
   evidence of the exact seat — the thing §4's `achieved_grade` needs. Wiring the `onto` method's
   adapter to consume it is now cheaper than building the panel producer, so **start there**.
   Motive, no longer hypothetical: onto measured that a dropped override resolves to
   `codex/codex` with `model = null` rather than failing, so the family collapse was real.
5. **`HOST_EFFORTS` is per-host; the authority is per-model.** Values verified correct against the
   providers — do not re-litigate — but the shape is an approximation.
6. **The design has never been reviewed as a design.** Two blind frontier drafts plus a synthesis;
   the synthesis itself was never adversarially checked. Every review since reviewed the
   implementation.
7. **ACCEPTED, not closed — the launcher requires onto ≥ 0.4.18.** Below that version an omitted
   `auth` resolves Anthropic to `api_key`, so the shipped `deep-review` / `session-distill` arms
   bill a metered key on a codex main. Not a fringe case: `install.sh:340` reports a capability
   *present* and skips it whenever the command resolves, with no version probe and no upgrade, so
   an existing install keeps 0.4.17 indefinitely. **Owner decided to ignore 0.4.17 compatibility**
   (design `Corrections` C15) — no floor, no degrade, no signal. First thing to revisit if the
   multi-user target ever becomes real.
8. **Smaller:** the editor has no discard path, and `build_plan` raising is unguarded where the
   mode default preset is built for the picker — unreachable while no shipped preset is
   composable-and-unresolvable, reachable the day a user's composable preset becomes a mode default.
9. ~~**A single-provider user cannot use any shipped preset that carries review.**~~ **DONE
   2026-07-27** (design `Corrections` C20). All four review-carrying presets launch on a
   claude-only profile now: the base falls back to the main seat as `DEGRADED` /
   `perspective_floor`, and optional methods `DROP` naming the missing host. The §1/C7
   contradiction resolved in §1's favour — C7 was protecting against a *silent* degrade, and this
   one is loud. Two-provider behaviour is byte-identical (golden: one renamed scenario, zero
   changed cells).

## 5. The machinery

| Concern | Where |
|---|---|
| Readers, both schemas | `read_review`, `read_review_arms`, `parse_review_block`, `parse_review_arms`, `parse_review_binding`, `legacy_review_plan` |
| Per-host arms | `[presets.<n>.review.hosts.<host>]`, exclusive with a flat block; arms resolve lazily |
| Descriptors / offers | `[review_methods.*]`, `[capabilities.*].offers` in `launch/agent-launch.toml` |
| User registry | `merge_user_review_methods`, `user_methods_path` (`review-methods.local.toml`) |
| Mechanism + renderer | `derive_review_mechanism`, `host_dispatch_command`, `render_review_method` |
| Resolution (one owner) | `resolve_review_for_plan`, `resolve_composable_review`, `independence_grade` |
| Contract record | `review_plan_v1`, `review_plan_from_v1`, `extract_review_plan_v1` |
| Args | `review_mcp_servers` |
| Editor | `review_editor`, `choose_review_binding`, `review_provider_options`, `method_availability`, `register_reviewer_info`, `apply_review_plan` |
| Save | `review_block_from_plan`, `review_binding_fields`, `render_preset_block` |
| Receipts | `verify_review_receipts`, `render_receipt_verdicts`, `verify_receipts_command` (`--verify-receipts`) |
| Gate checks | `launcher_review_{schema,methods,report,contract,editor,save}`, `launcher_receipts` (30 parity checks) |
| E2E | `gates/capture-review-goldens.py` → 253 cells, 10 controls each proven to fire |

**Run everything:**

```bash
./gates/check-parity.sh            # ~30s; includes the golden --check and --self-test
python3 gates/check-lexicon.py
bash gates/check-package.sh
bash gates/test-assemble.sh
```

**Import smoke — after EVERY launcher edit, before believing any other green.** `compile()` does
not catch an undefined name:

```python
spec = importlib.util.spec_from_file_location("probe", "launch/agent-launch.py")
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m   # required
spec.loader.exec_module(m)
cfg = m.load_config(pathlib.Path("launch/agent-launch.toml"))
for host in ("codex", "claude"):
    for preset in sorted(cfg["presets"]):
        plan = m.build_plan(cfg, host, preset)
        m.run_contract(plan); m.project_args(plan, materialize_agents=False)
```

**Driving the TUI headlessly** — stub `read_input` only and let `choose_lines` run, or drive the
real Textual app under `run_test()` and `export_screenshot()` for SVGs (venv python at
`~/.local/share/agent-launch/venv/bin/python`). Menu indices shift as rows appear.

## 6. Ordered next actions

1. **§4.6** — an adversarial review of the design itself is the largest unexamined risk left, and
   §4.9 is evidence for it: a contradiction between §1 and C7 survived because the synthesis was
   never reviewed as a design.
2. **§4.4 receipts producer**, if achievement should stop being hand-asserted.
3. **§4.2** once `ultracode-for-codex` settles.
4. **Redeploy — now unblocked, and worth doing.** The installed launcher and `profiles.toml`
   predate the migration, so this machine still launches pre-migration defaults. The reason to
   wait is gone: onto 0.4.18 resolves an omitted `auth` to the subscription, so the merged launcher
   is correct against it (verified end to end, §3). Repo-tree deploy is `bash install.sh install`
   from the repo root; `agent-bios install` would deploy the published npm package instead.
   **Precondition:** correct only on onto ≥ 0.4.18, so check `npm ls -g onto-mcp` first — on
   0.4.17 the same launcher restores per-token billing for the two user-owned `hybrid` presets.

**Literal first command** (T1, HELM, delegation authorised, cross-family review live):

```
load claude/guides/coding-staged-workflow.md and claude/guides/cli-multi-model-workflow.md,
read design/reviewer-registry/DESIGN.md Corrections C4–C9, then run ./gates/check-parity.sh
```

## 7. Traps that cost time this session

- **Read a function's input from its real caller, not from the file it seems to come from.** A
  probe fed `applyReviewLlmOverride` the raw `~/.onto/settings.json` and concluded the override
  changed nothing. Seats there live under `review.execution.actors.*`; the function reads the flat
  `review.execution.{teamlead,lens,synthesize}`; the real call site passes
  `resolveSettingsChain(...)`, which normalises between them. Confident, reproducible, wrong.
- **A derived invariant cannot catch a lie in the data it derives from.** The first gate for C8
  asserted no shipped preset is DROPPED for "offers no operation for host" — it never fired,
  because a false `hosts` claim makes the mechanism resolve *successfully*. The check that works
  pins the declaration itself.
- **An A/B can be true and blind at once.** The migration's A/B correctly reported four presets
  moving and every one grading `provider_difference` — and was structurally incapable of seeing a
  reviewer told to run a model its command cannot load.
- **A gate that borrows a shipped preset dies the moment defaults move.** Six checks built their
  legacy scenario by string-replacing `review_setup` in a shipped preset. After the migration those
  replacements silently no-op'd and the checks passed while testing nothing. They own synthetic
  subjects now (`legacy_preset_toml`).
- **Renaming a preset must take its sub-tables.** A probe renamed `[presets.balanced]` only, and
  the arms under `[presets.balanced.review.hosts.*]` re-created the preset implicitly.
- **Count what you mean.** A control counting a capability endpoint across all of argv conflated
  instruction text with the server registration — the contract travels in argv too.
- **Edit the launcher in one all-or-nothing patch**, and keep the patch script in the scratchpad.
- **A backgrounded `&` inside a tool call does not survive the call.** A dispatched frontier draft
  died silently and left a 0-byte output file.
- **A subagent may never report.** Two did not. Never let a claim rest on a pending spawn.
- **`claude` and `codex` are zsh functions**; non-interactively use `~/.superset/bin/claude` and
  `/opt/homebrew/bin/codex`. `timeout` is `gtimeout` on macOS. `codex -c` accepts arbitrary keys,
  so a config-key probe needs a bogus-key negative control.

## 8. Credentials

None needed. Every route here is `--dry-run` against a fake backend, a read-only review dispatch
over an existing OAuth session, or a pure-function probe. The onto billing finding was established
**without a billed call** — keep it that way; if a live check is ever wanted, use a gitignored env
slot and never a literal.
