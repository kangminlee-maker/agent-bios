---
created_at: 2026-08-19T08:55:00+09:00
head: 12914d0
kind: design
---

# Design — the criterion stage: discipline enters the contract, the criterion stays in the packet

**Status: working draft for the build in the same PR.** The stage was deferred by
`2026-08-18T2237--0390b81--design.md` §7 step 6 pending separate approval; the user granted
that approval on 2026-08-19, sequencing it before the v0.13.0 release. Synthesized from two
independent frontier drafts off one blind packet — Claude (fable-5, fresh-context subagent)
and GPT (gpt-5.6-sol, max, `codex exec -s read-only`) — per the dual-provider design rule.
The packet (with the full code-seam evidence, gathered read-only at 471ff43) and both raw
drafts are in the session scratchpad. Two probes anchored the packet: codex-cli 0.146.0
registers `codex exec --output-schema <FILE>`, Claude Code 2.1.235 registers
`--json-schema <schema>`; neither is passed by the launcher today, and whether each flag
*refuses* non-conforming output was left unprobed by design (the build probes behavior, not
registration alone).

**Where the providers converged** — treated as settled: alternative C (schema where
possible), both A (full contract stack) and D (no launcher change) rejected; prose routes
stay first-class with an honest disclosure, never demoted or grade-penalized; no machine
catalog this stage (a task-local criterion document is the only machine form; the shipped
guide stays the human catalog); strict deterministic validation of the criterion document —
the guide's eight fields, exactly one stop-relevant class, ≥2/≥2/≥1 goldens each with
`measured`/`constructed` provenance and date, class labels under the existing name rules —
refusing by field name with no fallback; the structural refusal of findings is a local
deterministic check, with the host's schema flag credited as steering generation, never as
the sole authority; user-registered methods and the wizard untouched, the resolver
identity-blind; the existing 121 review-matrix entries stay byte-identical, new coverage is
additive cells only; runtime never reasons — no class guessing, no prose-to-JSON salvage,
no same-run fallback after a structured failure.

**Where they split, and what was taken:**

1. **Input channel** — GPT: a `--criterion PATH` launch flag whose document renders through
   a new `{criterion}` INSTRUCTION_SLOT (virtually appended per method). Claude: a preset
   boolean; the criterion text never enters the launcher. **Claude's taken.** The rendered
   contract stays f(config, plan) — the review-matrix golden's byte-for-byte pinning
   survives with no normalization holes for per-invocation free text, and the criterion
   text keeps exactly one home: the packet, which rank 2 of the shipped guide already
   requires to carry it verbatim and which `packet_sha256` already binds. GPT's own
   load-bearing ASSUMPTION (one launch ≡ one criterion) dissolves with the flag.
2. **Validation point** — GPT required a core-owned mandatory point before result
   publication and flagged it MISSING FACT: "if no such point exists, return to design."
   **The point exists: `emit_receipt_command`** (launch/agent-launch.py:3060-3092), the
   only path to a receipt. Taken as the fusion of both drafts: the findings check runs
   inside receipt emission when the dispatch declares a compiled schema (a new
   `REVIEW_CRITERION_SCHEMA` env var beside the existing `REVIEW_*` family), so a bypassed
   check means no receipt, and an unproven dispatch is already counted false by the
   AI-harness stop class. A standalone `--check-findings` exposes the same pure check to
   the dispatching agent's fold.
3. **Result grammar** — GPT's closed shape taken verbatim as what the compiler emits:
   `{"findings": [{"class": "<enum>", "finding": "<non-empty prose>"}]}`, empty list
   allowed, unknown fields rejected at both levels.
4. **Offer grammar** — GPT extended OFFER_KEYS with `output_contract = "json-schema"`;
   Claude kept the offer grammar closed and probed instead. **Claude's taken**: a declared
   capability is docs, and the corpus rule is probe-over-docs; the host→flag knowledge
   (`codex exec --output-schema`, `claude --json-schema`) is a core table verified by a
   conformance probe extending the existing `--check-adapter` family. OFFER_KEYS stays
   frozen at four keys.
5. **Receipts** — GPT added nothing, arguing a digest with no verifier decision is inert;
   Claude added one optional key with three verify bars. **Claude's taken, because the
   reader is real**: `criterion_schema_sha256` (present only on schema-route dispatches) is
   read by `--verify-receipts --packet`, which recompiles the packet's machine-readable
   criterion — compilation is canonical by construction, proven byte-identical on
   double-compile — and refuses a mismatch. That proves the schema the host was handed was
   compiled from *this* packet's criterion. GPT's caution survives as ordering: the receipt
   touch is the last build step and independently revertible.

## Decisions at a glance

| # | Decision | Nearest neighbor and why it does not cover |
|---|---|---|
| 1 | Criterion text enters via the **packet** (guide rank 2, machine-readable section); the launcher gains only a preset boolean `criterion = true` | mission/trigger — preset fields that reach the contract (:4820-4831, :8278-8283) carry per-preset intent, and this one carries only discipline intent, never content |
| 2 | Render: core-owned **criterion clause + marker**, appended to each method row when the plan toggles it — no INSTRUCTION_SLOTS or METHOD_KEYS change | severity_translation / controls_clause (:1626-1642, :1605-1614) — same core-appended, method-blind, marker-guarded pattern, but unconditional; this one is plan-conditional |
| 3 | `--compile-criterion FILE OUT`: deterministic strict subset of the guide schema → canonical findings JSON Schema + digest | `--fold-receipts` / `--emit-receipt` — the existing per-review file subcommands; none reads criterion text |
| 4 | Host schema transport: core host→flag table, **probed** against the resolved binary (registration + refusal behavior); probe-negative ⇒ that route renders prose discipline | the adapter conformance probe (:3385-3393) — same empirical pattern, different property |
| 5 | `--check-findings RESULT SCHEMA`: pure deterministic check, refuses class-less / out-of-enum rows by name; also runs inside `--emit-receipt` when `REVIEW_CRITERION_SCHEMA` is set — **emission refused on invalid results** | fold_receipts (:3300-3310) — folds receipt metadata, explicitly not finding classification |
| 6 | Receipts: one optional key `criterion_schema_sha256`; verify bars — marker in any plan row ⇒ packet must carry a compilable criterion; key present ⇒ recompile-and-match; key absent on a criterion review ⇒ **disclosed** as prose-level, never refused | packet_sha256/result_sha256 (:2373-2378) bind packet and result bytes, not the schema artifact handed to the host |
| 7 | Enforcement level (schema / prose / none) is **derived** at verdict render, never stored | render_receipt_verdicts (:2910); a stored label restates derivable state |
| 8 | No catalog; task-local criterion only; the criterion name is display identity, not a lookup key | the shipped guide is the human catalog; a machine catalog's only reader today would be the composing agent — inert |
| 9 | Goldens: existing cells byte-identical (proven by `--check` before capture); **additive** scenario cells — criterion-toggled per host family + one prose case | broad re-baseline — avoided because no unconditional render path changes |

## Build order — seven steps, one PR, a negative control each

1. **Preset field `criterion`** — parse/store beside mission/trigger. Control: a planted
   non-boolean refused by name; revert the refusal → self-test fails.
2. **Clause + marker, core-appended when toggled.** Controls: golden `--check` byte-green
   with the toggle absent; a scratch toggled preset must produce a diff (instrument test —
   prove the check can see the change); a spoofed marker in author instructions refused
   (refuse_plan_marker pattern :1580); revert → launcher_review_methods self-test fails.
3. **`--compile-criterion` + `--self-test`** — planted zero-stop-class, two-stop-class,
   short-goldens, missing-provenance documents each refused by name; canonical output
   proven by double-compile byte-compare; break canonicalization → self-test fails.
4. **Schema-flag probe** extending the `--check-adapter` family. Controls: a stub binary
   lacking the flag reports *absent*, not error; the probe decides file-vs-inline transport
   empirically for both installed binaries.
5. **`--check-findings` + `--self-test`** — planted class-less and out-of-enum findings
   refused by name; no salvage path exists to gut; remove the refusal → control-audit or
   self-test notices.
6. **Receipt key + emission validation + verify bars** (last receipt touch, independently
   revertible). Controls per refusal: plant the violation, watch it fail by name, revert
   the fix, watch the control fail — including an E2E where a planted invalid result
   reaches the real `--emit-receipt` and no receipt is emitted.
7. **Golden capture** — additive scenario cells; extend `launcher_review_methods` (clause
   iff toggled, core-constant subtraction, canary method proves method-blindness);
   reconcile the stale "192 projections" comment at gates/check-parity.sh:288 against the
   measured 121 entries. Control: mutate the clause constant → only the new cells diff.

**Done-when (falsifiable):** untoggled capture `--check` green over the unchanged 121
cells; a toggled dry-run renders the clause exactly once per method row and a golden cell
pins it; a planted class-less finding through the real `--emit-receipt` yields refusal and
no receipt; `--verify-receipts --packet` refuses a mismatched `criterion_schema_sha256` and
a marker-bearing plan whose packet carries no compilable criterion; the parity umbrella
green from the clone; every new control seen to fail before its green, and each fix
reverted once to prove its control notices.

## Not built, with reopeners

- A `{criterion}` INSTRUCTION_SLOT or METHOD_KEYS key — reopen if per-method criterion
  variation inside one launch becomes real.
- Any per-invocation text channel into the rendered contract (`--criterion` flag, env,
  packet parsing at launch) — reopen if packet bytes ever start passing through the
  launcher before rendering.
- An offer `output_contract` key — reopen for a schema transport that is not a CLI flag
  (an MCP/API adapter property the probe cannot reach).
- A machine-readable catalog — reopen on measured cross-packet digest drift of a reused
  named criterion (the verify recompile digests make that drift measurable for free).
- An enforcement-strength probe beyond refusal behavior — moot while emission validates.
- Launcher-side semantic fold or re-send; prose→JSON conversion; same-run fallback after a
  structured failure; wizard prompts for output contracts; ReviewPlan grade changes keyed
  on schema capability; cryptographic receipt claims.

## Open questions carried forward

1. Whether the guide's rank-3 paragraph (the slot "deliberately not part of this guide")
   is rewritten in this PR or the next corpus release — the channel now exists, so the
   sentence becomes stale the moment step 6 lands. Default: rewrite in this PR, since
   active docs describe the present.
2. Per-repo criterion extension (user-owned file vs AGENTS.md) — unchanged from the prior
   design; the first real second-repo criterion decides.
