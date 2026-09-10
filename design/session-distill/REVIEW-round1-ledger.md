# Design Review Ledger — Session-Learning Pipeline

Reviewed: 2026-07-16. Target: `/tmp/agent-bios-session-distill-plan.md`
`design_body_hash` = `89fe740412821d6f05d227d8e8ace798c895fc297d5f7d749b6007802d4c42fa` (raw sha256 `4804e222…`)

Two independent multi-lens reviews of the same packet (design + context + consumer sample), same six lenses (goal-fit, proportionality, missing-critical, operability, consistency, statistics), finder → adversarial-verify → synthesis in both:

| Track | Models | Participation | Raw → verified kept | Verdict |
|---|---|---|---|---|
| Codex (gpt-5.6 sol/terra) | find xhigh ×6, verify high ×46, synth max | 6/6 lenses | 47 → 37 kept, 9 refuted, 1 unverified (F28) | **fit_with_material_changes** |
| Claude (opus-4.8/sonnet-5) | find xhigh ×6, verify high ×29, synth max | 6/6 lenses | 48 → 22 kept, 7 refuted, 5 low filtered | **fit_with_material_changes** |

Both tracks independently reached the same verdict: the semantic skeleton (freeze → census → dual-lane screen → current-gap comparison → human admission → promotion bundle) fits the goal; the contract as written should not enter implementation unchanged.

User dispositions recorded 2026-07-16:
- **Business-case findings (Codex F19/F03/F18/F20; Claude C03/C10/C11) — out of scope by user decision.** Cost/schedule/yield justification is not a question this review decides. They remain listed for the record only.
- **Over-engineering findings — accepted for deep examination** (below, with main-context re-derivation).

---

## Part 1 — Over-engineering examination (user-requested focus)

Each cluster: what both tracks found, what the main-context re-derivation against the design text confirms, and the resulting disposition. "Keep" = load-bearing as written; "Simplify" = replace with the named alternative; every simplification names its accepted residual risk.

### OE-1. OS containment / process-supervision choreography — **Simplify (split: keep evidenced core, drop proof-demanding layer)**
- Sources: Codex F01/F12/F23/F25 (map #1) ↔ Claude C02, map #2. Convergent.
- Design demands (§Privacy ¶205–212): per-attempt **non-joinable, takeover-safe kernel job/container handles** with live proofs ("prove on the live host that outsiders cannot join it and members cannot escape undetected"), barrier trampoline with single identity-preserving exec, **exec-generation kernel monitor receipt**, crash-GC that terminates only through handle operations; absence of any proof ⇒ semantic route unavailable.
- Re-derivation: the *threats* are real and the design's own empirical basis proves some (19 vendor-orphaned temp dirs, 0644 marker modes, one live 0600 auth file; `sandbox=read-only` reading an outside marker when shell was enabled). **But the demanded guarantee level exceeds what macOS natively provides.** macOS has no non-joinable job object; process groups are joinable by design; an "exec-generation receipt" needs kernel-level monitoring authority the design never names. Under its own fail-closed rule, the likeliest outcome on this host is: **every semantic route is permanently unavailable** (Codex F25's core, Claude synthesis concurs). Meanwhile the design itself already contains the sufficient race-free mechanism for direct children: "the supervisor does not reap an attempt's direct leader until all work … is terminal, preventing PID/SID/PGID reuse" — an unreaped direct child's PID cannot be reused, so handle-free supervision of *direct children* is already identity-safe.
- **Simplification**: keep — leased 0700 run roots, 0600 credential modes, leased-`TMPDIR` ancestry for Codex isolation, exact-realpath-only deletion, unreaped-direct-child termination, minimal generated config, `--bare` + pinned argv, self-marking of pipeline jobs. Replace — kernel-handle/takeover/exec-generation proofs with: kqueue `NOTE_EXIT`-tracked descendant bookkeeping, best-effort group termination *after* direct-leader death proof, and `sandbox-exec` file/process profile (already validated by the design's own canary).
- **Accepted residual risk**: a detached grandchild that escapes supervision is contained by the file profile and leased ancestry but may require manual cleanup; post-crash accounting is coarser. The refuted-candidate record supports keeping the cleanup/lease core: Claude verify **refuted C19** ("cleanup machinery answers an audited real defect") — the lease/state-machine core is load-bearing; only the proof-demanding handle layer is excess.

### OE-2. Zero-miss certification + blinded redesign + provider-wide replay — **Simplify (confirmed internal contradiction)**
- Sources: Codex F10/F30/F46 (map #2) ↔ Claude C08 (high), C13 (high), C04, C15, map #1. Strongly convergent; both tracks' highest-confidence over-engineering cluster.
- Re-derivation confirms an outright **contradiction with the declared authority**: "The exact finite-population hypergeometric one-sided upper bound is authority" vs "Any observed material miss in the probability sample or a cell minimum fails and invalidates the provider audit." In a *full census* with, e.g., 5/200 misses (2.5% < ε=0.10) the bound passes while the zero-miss veto still invalidates — the stricter rule silently overrides the rule the user is told they chose (Decision 2 presents ε=0.10). Operating characteristics at n=29, c=0: P(fail | true miss rate 1%) ≈ 25%, 2% ≈ 44%, 3% ≈ 59%, 5% ≈ 77% — a compliant screen fails near a coin flip, consuming the **single non-renewable** redesign allowance (C13), after which any later confirmed miss (expected, since ~70% of L is never audited while up to 10% miss rate is tolerated) leaves the run permanently incomplete after full P4–P6 spend.
- Single-person blinding (C04): the capability-revocation choreography cannot manufacture real independence when one human fills labeler and redesign roles; the certificate's independence assumption is unattainable regardless of ceremony.
- **Simplification**: (a) acceptance rule = the already-declared hypergeometric bound with a user-frozen (n, c) pair — e.g. n≈46, c=1 preserves the ε=0.10/95% guarantee while tolerating one observed miss; (b) observed misses are repaired and disclosed, not epoch-invalidating; (c) P4Q scoped to the confirmed miss's stratum/class (re-screen affected stratum + add the miss class as a regression control) instead of whole-provider replay; (d) redesign allowance renewable by explicit user gate; (e) replace role-revocation choreography with time-separated precommitment and a disclosed single-operator-independence limitation.
- **Accepted residual risk**: a bounded nonzero false-negative rate — which is exactly the tolerance the design already states — and weaker anti-overfitting protection after redesign (keep the sealed disjoint holdout for the redesign path only; that part is principled and cheap).

### OE-3. Overlap guard scope (4-token/24-scalar over the full closure incl. own outbound packet) — **Simplify (confirmed self-defeating at the deliverable)**
- Sources: Codex F08 (map #5) ↔ Claude C06 (**high**). Convergent, Claude sharper.
- Re-derivation confirms the self-collision: the guard's source set explicitly includes "the outbound packet" and the transitive raw-card closure; it re-runs "over deterministic views, promotion bundles, and the exact P6 bytes"; a failing span gets only a human rewrite **"that must pass the same guard."** But the pipeline's core deliverable class is exact operational vocabulary: `--no-session-persistence` is exactly 24 scalars; `--dangerously-skip-permissions` is 30; any real path/env name ≥8 scalars trips the identifier detector; the consumer document (canonical CLAUDE.md) is itself full of exact flags, env names, and file paths. As scoped, the guard structurally forbids the promotion bundle from containing the very content the goal requires ("extend the nearest guide for procedures, thresholds, tables, examples"), and no rewrite can save an exact flag. It also collides with quoting current-rule text for covered/partial comparison display, since injected AGENTS payloads sit in the raw-card inventories (Codex F08).
- **Simplification**: two-tier guard. Provider-bound/cross-family bytes: keep the conservative verbatim n-gram + identifier guard as written. Local canonical store / views / promotion bundle / P6 projections that stay local: replace verbatim n-gram rejection with secret/credential/identifier detectors (keys, tokens, emails, home-path prefixes) plus an allowlist for operational vocabulary (CLI flags, env names, documented commands) — exact flags/paths are first-class lesson content, not leakage.
- **Accepted residual risk**: non-secret private source prose may persist in local artifacts for the retention period — the user's own data on the user's own machine, disclosed.

### OE-4. Dedicated `goal_only` semantic lane — **Drop (replace with local disclosure note)**
- Source: Claude C16. Codex did not flag it (divergence — noted and adopted on re-derivation).
- Re-derivation: the claim-authority matrix caps the lane's entire possible output at `topic_only`, which "cannot increase causal, behavioral, impact, novelty, or admission strength" — i.e., **no admission decision can ever change based on this lane's result**. For that decision-inert output the design builds: a versioned projection contract, a full-census provider lane, its own P2 N=1 receipt, forbidden-claim negative fixtures, and mandatory P3.5 binding. Population: 4 cards in the frozen audit (~1.5% of ids; production census likely similar).
- **Simplification**: record goal-only ids as `known_absent_source` with locally redacted goal text in the census store and a disclosure note in the bundle; delete the provider lane, its receipt, and its fixtures. **Accepted residual risk**: loss of a weak topic-recurrence footnote on candidates grounded elsewhere — decision-inert by construction.

### OE-5. Quarantine exhaustion before any useful output — **Keep, with one addition**
- Source: Codex F05 (map #3). Claude verify refuted the adjacent C01 (fail-closed gates deliberate, fallback disclosed).
- Re-derivation: the design already contains nearly the proposed alternative — a signed exact count/reason exclusion yields `bounded_exclusion_coverage`; quarantine is "a visible decision queue, not an exclusion sink." The gap is only that exclusion signatures are per-stratum ad hoc. **Disposition: keep the blocking rule; add a P0-preauthorizable standing exclusion policy** (user pre-signs: "strata matching reason R up to count N are excluded into bounded coverage") so ambiguity throughput cannot hold the proven corpus hostage to synchronous availability. Residual: a genuinely direct-main session may sit in an excluded stratum; corpus-wide recall is then correctly not claimed.

### OE-6. Mandatory live cross-family P6 finality (even zero-candidate) — **Keep requirement, add provisional state**
- Sources: Codex F31 (map #4) ↔ Claude C09/C14-adjacent; also interacts with Codex **F34 (high)**: the Method-B fallback is invoked exactly when one family's route died, yet P6 still demands that family live — completion unreachable in the fallback's own trigger scenario.
- **Disposition**: keep live cross-family P6 as the requirement for *reviewed* status; add a durable, hash-bound `review_pending` P5 export the user may inspect (never promotion-ready), and define mode-specific P6/completion rules for Method B (fix F34). Residual: the provisional artifact may lack what an independent reviewer would have found — it is labeled, not promotion-ready.

### OE-7. Per-incident human authorization after ambiguous dispatch — **Simplify**
- Source: Codex F29. Claude C25 adjacent (recovery path unspecified for either pinned route).
- Re-derivation: the design already reserves worst-case duplicate exposure on a signed resend; making one recover-first + exact-hash linked resend a **standing P3.5-approved policy** within a separately reserved duplicate-exposure ceiling removes the synchronous sole-human dependency without adding any new judgment authority (a resend is transport, not semantics). Residual: one duplicate billed execution / duplicate same-provider exposure when the original was in fact accepted — bounded and pre-reserved. Also adopt Claude C25: specify and probe the content-free recovery route per provider at P0, or delete "recovery-preferred" language.

### OE-8. Recurrence/high-impact-only drafting bar — **Simplify (goal misfit at the modal case)**
- Sources: Codex F07 ↔ Claude C29. Convergent across different categories.
- Re-derivation: hard eligibility admits "generalizable beyond the incident" with no recurrence requirement, but the §6 drafting gate accepts only recurrent clusters or high/blocker-impact singletons — so a fully-evidenced, generalizable, **single-occurrence moderate-impact** lesson passes eligibility and then has no drafting route. In a 21-day single-user corpus that is the modal lesson shape; the repo's own recent instruction additions (used by the design as calibration controls) largely originated from single incidents.
- **Simplification**: add a medium-impact singleton route gated by novelty check, counterexample search, over-trigger control, token-budget delta, and explicit user sign-off. Residual: possible overgeneralization from one-offs — mitigated by the human gate the design already requires for every promotion.

### Looks-overengineered but load-bearing — **explicitly kept** (adversarial verification defended these)
- Write-ahead/duplicate-exposure ceremony (Claude C18 refuted: the design correctly refuses to assume provider idempotency).
- Cleanup/lease state machine core (Claude C19 refuted: answers the audited real vendor temp/auth defect).
- Vector budget caps not derived from history (Claude C20 refuted: design explicitly excludes historical usage as authorization).
- Fail-closed route gates with named user-gate fallback (Claude C01 refuted: deliberate, disclosed).
- Read-scope discipline independent of `sandbox=read-only` (both tracks: the design's own live contrast probe proved the sandbox flag is not read authority).

---

## Part 2 — Remaining verified findings (union, deduplicated across tracks)

High-severity (excluding user-descoped business-case items):

| # | Sources | Finding | Status after re-derivation |
|---|---|---|---|
| R1 | Claude C05 ↔ Codex F26 | **No corpus preservation step**: census reads byte-prefix pointers into live provider files; retention decay is already proven (4/265 irrecoverable); an open gate at hard expiry deletes run content; nothing archives the ~1.4 GB. | Confirmed. Cheapest, most urgent fix of the whole review: archive in-window files + both history.jsonl now, run census against the archive, exempt archive from hard expiry. |
| R2 | Codex F34 ↔ Claude C07-rec | **Method-B fallback cannot complete**: B triggers when one family's route is unavailable, but P6/`extraction_complete` still require that family's live receipt. | Confirmed internal contradiction (re-derived §Method ↔ §P6/§307). Add mode-specific completion rules. |
| R3 | Claude C07 ↔ Codex F21/F27 | **Containment welded to already-drifted pins** (0.5.0 clauses vs installed 0.6.0; Claude 2.1.211 unverified); any re-pin is a body change forcing fresh full review. | Confirmed empirically (this session observed 0.6.0). Move version-bound empirics to a re-pinnable attested appendix + per-release re-derivation checklist. |
| R4 | Claude C14/C09 ↔ Codex map#3-adjacent | **Whole-body hash attestation welded to readiness**: any one-line fix revokes pilot/production readiness and forces full conformance + cross-family re-review; no tiered change classes. | Confirmed. Define change classes (containment/privacy vs semantic vs mechanical) with class-scoped re-validation; class label auditable, defaulting stricter. |
| R5 | Claude C28 ↔ Codex missing-critical #5 | **H-stratum has zero quality control**: all statistical audit lands on L; deep-extraction dismissals on the densest lesson stratum (rollbacks, failing builds) are invisible to every receipt. | Confirmed. Add a small human-reference audit over H deep-extraction dismissals (same (n,c) logic). |
| R6 | Claude C12 ↔ Codex F02/missing #1,#6 | **No independent validity check on admitted lessons; P6 reviewer is evidence-blind; bundle lacks implementer-ready patch content + aggregate token gate.** | Confirmed (bundle carries sanitized projections only; drafts forbid exact context; consumer has a hard token budget). Rebalance §6: give lesson-drafting/validation the specification depth containment gets today (Claude C02). |
| R7 | Claude C15/C04 ↔ Codex F40/F44/F45 | **Screen-quality certificate lacks a fixed semantic estimand** (what a "material miss" is, operationally) and assumes unattainable single-person independence; card-rate bound cannot certify material-lesson recall in the rare-material regime. | Confirmed. Freeze a written materiality rubric at P0; report the bound as card-rate, not lesson-recall. |
| R8 | Claude C24 ↔ Codex F33/F35/F38/F39, F36, F31 | **State-machine completeness gaps**: late provenance reclassification forces full P1.5→P3.5 redo; P2 recovery/P6 overflow/reviewer-materiality/rejection/cleanup-store reconciliation each have undefined or asymmetric transitions. | Confirmed as a cluster. One authoritative transition spec covering these five paths. |
| R9 | Claude C22 ↔ Codex missing #11, F22 | **No partial-value delivery and no repeat-run reuse contract**: any single P4 shortfall yields zero user-consumable output; overlapping windows re-incur full census + human floors. | Confirmed. Define labeled partial-bundle states; add cross-census carry rules for unchanged episodes. |

Out-of-scope by user decision (recorded only): Codex F19/F03/F18/F20; Claude C03/C10/C11 (business case / workload / yield envelopes).

Unverified (treat as open question only): Codex F28 — human-label wait states vs unattended progress within preapproved caps.

## Part 3 — Refuted findings (both tracks, for the record)

Codex refuted 9 of 47 (incl. severity-downgrades); Claude refuted 7 of 29 — full texts in `codex-result.json` / `claude-result.json` (session scratchpad `design-review/`). Notable: every "the fail-closed gate is itself a defect" candidate died under adversarial verification in both tracks; the gates' *scope* (what they demand proof of) is the confirmed problem, not their fail-closed nature.

## Part 4 — Questions only the user can decide (union)

1. Screen quality: govern by the declared ε/α bound with an (n,c) acceptance rule, or intentionally keep zero-observed-miss with its redesign/replay cost? (Both tracks' top statistical question.)
2. Overlap guard: accept the two-tier scoping (verbatim guard for provider-bound bytes; secret-detectors + operational-vocabulary allowlist locally)?
3. Containment: accept unreaped-direct-child + kqueue supervision + `sandbox-exec` profile as the macOS-realizable containment floor, dropping the non-joinable-handle/exec-generation proofs?
4. Ambiguous dispatch: preauthorize one recover-first exact-hash linked resend within a reserved duplicate ceiling?
5. Provisional delivery: allow durable `review_pending` P5 export (never promotion-ready) when the cross-family route is down?
6. Singleton route: allow medium-impact singletons under the tightened controls above?
7. Retention: authorize the readiness-independent corpus archive now (R1), and its retention length?
8. Rerun cadence: is this a recurring rolling-window pipeline (drives R9)?
