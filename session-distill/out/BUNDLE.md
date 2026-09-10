# Session-Distill promotion bundle — verified shortlist

From **251** directly-handled main-context sessions (247 Claude + 4 Codex, 38-day window ending 2026-08-25) → 189 raw candidates → **147 consolidated clusters** → **147 survive** independent novelty verification against the current baseline (9 novel, 138 extend existing). 0 dropped as already-covered/too-specific/weak.

`strength` = recurrence (independent sessions) × materiality (1–5). `novel` = new rule; `partial` = extend an existing rule. Placement respects the repo rule that **only situation-recognition failures belong in global CLAUDE.md; procedures/thresholds/examples belong in scoped guides.** Nothing is written to the corpus yet — this is for your selection.

---

## Strength 4  (17)

### Detach long-running processes from the harness session/process group

`novel` · strength 4 · 3 sessions `claude:6e493fd5 claude:dd433796 claude:3a106d99` · ④recur-err ②rollback ⑤rare-hi-cost ③re-explore

**Rule:** A process started inside an agent-harness tool call belongs to that call's process group and session: a trailing `&` is reaped when the call returns, a background job dies with the session it was launched from, and the harness may signal the whole group when any other background task it manages completes. Anything meant to outlive one tool call or turn boundary — a multi-hour batch or collection chain, a frontier dispatch, a dev server or app stack run for the user — must be launched either through the harness's own background-run facility or fully detached (nohup/setsid/disown-equivalent, its own session or an explicitly owned group), writing progress and output to durable files so a resumed session re-attaches by reading state rather than restarting from zero. Read the signs correctly: a zero-byte output file right after such a launch means the process never survived, not that it produced nothing; a service that dies seconds after an unrelated background task finishes points to shared-group teardown before it points to the app; and check for a completion record before assuming a background job finished. This is the complement of owning teardown for children you create, not an exception to it — a detached process still needs an explicit owner, PID file, and stop path.

**vs baseline:** claude/guides/tooling-gotchas.md §Own what you spawn — covers spawn/teardown of children you create (process group, kill the group, await exit) and global §Tooling and Operational Safety 'idle CPU is not a hang'; neither states that a harness tool call/session reaps or signals its group, nor that an outliving job must be detached and resumed from durable state. Omits.

**Placement:** guides/tooling-gotchas.md §Own what you spawn (new bullet: "Detach what must outlive the call")

**Why (strength):** Three independent sessions (claude:6e493fd5, claude:dd433796, claude:3a106d99) hit the same mechanism from three angles — `&` reaped at call return, background chain dead after session resume (twice), harness cleanup of one task killing a sibling stack (twice) — each costing a real rerun (a multi-hour chain, a frontier draft dispatch, a user-facing app going down and being misattributed to the user). Clearly general to any harness-run shell; the baseline's only lifecycle rule is the inverse direction. Not 5 because same provider across all three and the exact reaping semantics are harness-specific in detail.


### Filter managed-job logs by the execution id you launched

`partial` · strength 4 · 2 sessions `claude:7dcaa4b8 claude:e28780e2` · ④recur-err ②rollback ⑤rare-hi-cost ⑥quality

**Rule:** Job-level logs outlive the execution: a managed job that has run more than once under one name — including a job deleted and recreated with the same name — returns the earlier incarnations' output when read by job name. Before interpreting any probe or run result, scope the log read to the execution id you received at launch and confirm the timestamp window covers that run; an unscoped read merges prior runs into the present and yields confident false diagnoses (stale last-seen, zero counts, phantom regressions) that a scoped read reverses. Applies to any managed job/run system whose log store is keyed by resource name rather than by execution; a job that has only ever run once is exempt but still benefits from the timestamp check.

**vs baseline:** Global §Tooling and Operational Safety ("Ambient state ... 'latest'-style pointers ... pin it explicitly (exact handles)") and cli-multi-model-workflow ("When polling concurrent async jobs, pin the exact id/handle received at dispatch — a 'latest' selector can point at a sibling job") — partial: both are dispatch/polling-side handle pinning; neither names the read-side trap that name-keyed logs retain prior executions (and survive deletion) so an unscoped log read contaminates the current result. tooling-gotchas §Config, secrets, and managed services has no log-scoping entry.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet "Job logs outlive the execution", placed after "A new revision is not live traffic"

**Why (strength):** Two independent sessions (claude:7dcaa4b8 — recreated same-name probe jobs read a deleted predecessor's logs; claude:e28780e2 — job-level log read produced a declared 1.5-day outage and regression that an execution-scoped re-read fully reversed, forcing a rollback of the diagnosis and a memory correction). Materiality is high: the failure mode is a confident wrong load-bearing conclusion, not a slow path. The general form (name-keyed log stores retaining prior executions) is clear and provider-independent. Not 5 because recurrence is two sessions and the mechanism is adjacent to an existing handle-pinning rule, so it extends rather than opens a new class.


### A mutant counts only if it compiled and lies on a reachable path; runners must report build failure distinctly

`partial` · strength 4 · 3 sessions `claude:d2b97c15 claude:e72c64c6 claude:8d164081` · ④recur-err ⑥quality

**Rule:** Before reading any mutation verdict, confirm the mutant is a valid probe: it compiled, it sits on a path the exercised test actually traverses, and it changes the guarded behavior rather than being healed downstream or coinciding with a default. A mutation runner must emit build failure, unreachable/anchor-mismatch, and equivalent as outcomes distinct from KILLED and SURVIVED — never fold them into either — and stop when the anchor it mutates has moved. Read the signals accordingly: more tests going red than the mutation should touch means suspect the mutant, not the code; a survivor is classified (build failed → re-mutate with a compiling change; equivalent → discard, no test can kill it; genuine gap → add a test on the real path) before any test is written. Applies to any mutate→test loop, hand-rolled or tooled; it does not apply to ordinary test failures where no mutant was planted.

**vs baseline:** guides/verification-discipline.md §When a green means nothing (revert-the-fix, empty subject, crashed-harness shapes) and review-defect-criteria AI-harness goldens (equivalent mutant "survived = gap" rule defect; runner that never ran its subject) — partially covers: equivalent mutants and vacuous runners are named as goldens, but the precondition that a mutant must compile and be reachable, the runner's distinct build-failure/unreachable outcomes, and survivor triage are absent as a rule.

**Placement:** guides/verification-discipline.md §When a green means nothing — new bullet "The mutant that never ran" following "The suspiciously fast or empty run", before the revert-the-fix closing paragraph

**Why (strength):** Three independent sessions (claude:d2b97c15, claude:e72c64c6, claude:8d164081) each hit the same shape — a non-compiling or unreachable mutant read as KILLED or SURVIVED, requiring rework of the runner or the mutant — so recurrence is real and cross-session, and the cost is a false verification signal that looks true (the harness class the baseline itself flags as dominant). The baseline only carries the equivalent-mutant golden and generic vacuous-run shapes; the compile/reachability precondition and the runner's distinct outcome classes are new. Not 5 because materiality is a wasted round rather than an irreversible loss, and all three sessions are single-provider.


### Run one probe item through the whole batch machinery before an unattended metered batch

`partial` · strength 4 · 2 sessions `claude:3ff21035 claude:7832145a` · ⑤rare-hi-cost ⑥quality

**Rule:** Before letting an unattended metered or long-running batch run past its first item, use that first item as a probe of the batch machinery itself, not just the item logic: run it end to end through the runner to its terminal side effect (the persisted record, publish, or write), then read the persisted evidence and confirm every value the later analysis depends on — treatment knob, run identity, witness fields, cost — was actually recorded with the expected value through the expected channel, and that any zero-cost path (a skip) really cost nothing. Only then release the remaining items. A batch whose outputs cannot be attributed is spend with no result; the check costs one item instead of all of them. When first failures appear, read the raw run logs rather than trusting the runner's status classifier, which infers causes from missing outputs. Applies to batches whose items are metered or take minutes each; a cheap, idempotent rerunnable batch does not need the gate.

**vs baseline:** guides/cli-multi-model-workflow.md §Unattended Batch Safety — partially covers: circuit breaker, poison-item dead-lettering, per-item outcome/cost records; verification-discipline.md "Probe at N=1 with the inputs precondition-checked" and tooling-gotchas "Smoke limits outlive the smoke test" are adjacent. None states gating batch launch on a first-item pass through the full runner with a persisted-instrumentation check to the terminal side effect.

**Placement:** guides/cli-multi-model-workflow.md §Unattended Batch Safety

**Why (strength):** Two independent sessions (a multi-arm pilot at ~26 min/invocation, and a 4.5-hour 31-item paid publish run) each reached the same practice on their own, and both involve rare-high-cost exposure where a missed instrumentation defect wastes the whole batch. The baseline's batch section covers failure handling during the run but not a pre-launch proof that the runner persists what the analysis will need, so this is a genuine extension rather than a restatement. Not 5 because recurrence is two sessions and neither reported an actual loss, only an averted one.


### Resolve the actual datastore target before any write from a scratch/dev context

`partial` · strength 4 · 2 sessions `claude:b8bdbf6d claude:9c08f554` · ⑤rare-hi-cost

**Rule:** A datastore target labelled dev, local, or scratch — a localhost URL in an env file, an exported override variable, a profile name — is a claim, not evidence of a non-production target: a localhost port can be a proxy into the only real instance, and a tool's own config loader can re-load a dotenv over the shell environment so an exported scratch URL never reaches it. Before the first command that can write (migration, schema push, seeder, real-payload run), resolve and print what the connection actually reaches (instance, project, host behind any proxy) from inside the same execution path the tool uses, and assert it is the intended target; when the loader cannot be trusted, extract the DDL or plan and apply it to the scratch target yourself, loading only non-datastore variables. Record the resolution so the next session does not re-assume. Read-only diagnostics still follow the production-probe rule; this applies to anything that writes.

**vs baseline:** guides/tooling-gotchas.md §Ambient state drifts — pin it (cloud CLI context) and §Config, secrets, and managed services (production probes expose data); guides/verification-discipline.md branch/version test bullet ("separate every state sink … OS-level stores that ignore env overrides, confirm the launch path propagates the isolation"). Partially covers: pinning ambient targets and isolating state sinks in general, but never states that a dev/local label or an exported env override is not proof of the target, nor that a tool's config loader can override the shell env, nor to assert the resolved target before the first write.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Two independent sessions (different repos, different mechanisms: proxy-to-prod behind a localhost dev URL; ORM config loading dotenv with override on top of the shell) converged on the same near-miss — a scratch write that would have landed on the only production database. Materiality is high (irreversible data loss on prod, criterion ⑤), and the failure mode is silent under the existing rules: the agent did pin/export as the baseline advises and was still pointed at prod. Not too specific — the general form (label ≠ target; resolve from inside the tool's own path; assert before write) applies to any datastore CLI. Strength 4 rather than 5 because recurrence is two sessions and both are near-misses, not realized losses.


### Dispatch/client status is not execution; confirm on the target's own record

`partial` · strength 4 · 2 sessions `claude:3f0354fb claude:c05b151d` · ④recur-err ③re-explore ⑤rare-hi-cost ⑥quality

**Rule:** A client-side status for a managed or triggered job — a CLI `--wait` returning or timing out, a scheduler/queue/webhook reporting success, a trigger accepted with no error — reports what the dispatcher saw, not whether the target ran or what state it reached. Before retrying, declaring done, or attributing a failure, re-derive the job's state from the target's own record (the service's job/execution describe, or the handler's logs), matched to the specific run by id or timestamp; treat a re-launch without that check as a duplicate execution with side effects, and keep any manual probe distinguishable from the scheduled one so the two cannot be confused. Applies to remote or asynchronous execution the dispatcher does not itself observe; a local synchronous command's exit code already is the target's record.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — "A new revision is not live traffic" and "Perimeter controls need the enforcement point's own logs" are instances of the same family; cli-multi-model-workflow "idle notification is not the report / pin the exact handle" and review-request "no receipt = PROPOSED" are the subagent/review instances. None states the general rule for managed jobs and triggers (client wait/timeout return, scheduler success), nor the duplicate-launch consequence of retrying blind. Partially covers.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet "Dispatch status is not execution", placed beside "A new revision is not live traffic"

**Why (strength):** Two independent sessions (a cloud CLI wait/timeout on builds and job executions, recovered via describe rather than re-launch; a scheduler forced run returning empty status, verified only on handler logs by timestamp). Materiality is high: the failure mode on one side is a duplicate launch with side effects, on the other an unverified retention cron treated as live. The baseline holds three sibling instances but not the generalization, so the addition compresses rather than dilutes. Not 5 because recurrence is two sessions and the two cases are adjacent instances rather than the same trap twice.


### Text matches in logs are hypotheses; inspect hits and prefer structured status

`partial` · strength 4 · 3 sessions `claude:cbf074b3 claude:19a169b2 claude:4c706feb` · ④recur-err ②rollback ⑥quality

**Rule:** A grep or substring match over a log, transcript, or process output is a hypothesis, never a finding — the text is a rendering that also carries quoted input, prior incidents, and review/deliberation prose. Failure vocabulary ("fail", "error", "halt") appears routinely in healthy reviewer and test logs; a transcript echoes its own prompt, so any earlier incident quoted there matches the same string; and short or numeric codes (a rate-limit status, an exit number) match substrings of token counts, ids, and timestamps. Before reporting a nonzero count, raising a failure event, or attributing a stall to a matched string: anchor the pattern to the field or message shape that carries the code, scope it to the output stream and the time window in question, print the matched lines and read them. Prefer the mechanism's own structured status — exit code, assertion throw, a status or event-kind field, or the terminal artifact it writes on completion — and never key a waiter or monitor you author on failure words alone. This governs signals read from text; it does not replace reading the raw provider payload for the cause once a real failure is confirmed.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety ("Treat a coarse runtime signal — a failure label ... — as a hypothesis, and confirm ... against the authoritative low-level evidence") and guides/tooling-gotchas.md §Tool output is a rendering, not the bytes (grep binary heuristic = false NO-match). Both cover coarse labels and false negatives/empty output; neither names the false-POSITIVE direction — substring/vocabulary matches over logs that quote failure words, echo the prompt, or collide with numeric fields — nor the rule to inspect matched lines and key on structured status/terminal artifacts. Partially covered.

**Placement:** guides/tooling-gotchas.md §Tool output is a rendering, not the bytes — new bullet "Text matches over logs are hypotheses", sibling of the grep-binary bullet (the false-negative counterpart)

**Why (strength):** Three independent sessions (cbf074b3, 19a169b2, 4c706feb; a fourth, c05b151d, is cited as a similar count-then-inspect correction) each hit a different concrete face of the same trap: failure vocabulary in a deliberation log fired a monitor, a prompt-echo match produced a retracted spend-cap diagnosis (rollback), and a bare numeric code matched token counts to report 2 errors where there were 0. Materiality is real — false failure attribution leads to re-arming, retracted diagnoses, and the risk of aborting healthy long-running work, which the global rule already treats as costly. The general form is clear and machine-checkable (anchor the pattern, scope to output stream, read hits, prefer structured status), and the baseline covers only the inverse direction (false no-match) and the coarse-label case, so this is a genuine gap rather than a restatement. Not 5 because no single instance was rare-high-cost; each was caught within the session.


### Another operator may be editing the shared tree/state; attribute foreign deltas before acting

`partial` · strength 4 · 5 sessions `claude:20169348 claude:fb236519 claude:87fb0d9c claude:66209c8c claude:65d4d30c` · ⑤rare-hi-cost ②rollback ④recur-err

**Rule:** A working tree, index, or shared service configuration can be changed by another session or operator while you work — a commit you did not make, a file the editor says changed on disk, paths in the index you never staged, a config surface one field larger than your predicted after-state. Treat any delta you cannot account for as another operator's work, not noise: stop before the next write, attribute it (reflog timestamps, process list filtered by working directory, revision history or audit log), and confirm whether it is meant to land. Then act only on what you can prove is yours — commit by explicit pathspec rather than the whole index, revert only paths whose every hunk or whose creation is yours, and never promote or ship a state that carries the unattributed delta without the operator's decision. After any long gap (background work, resume), re-read the untruncated status and re-diff against your last known state before writing. This is a precondition of shared-checkout and shared-service work; a private clone or an isolated worktree with no other writers needs only the ordinary pre-commit diff.

**vs baseline:** Partially covers. cli-multi-model-workflow §Sessions, Branches, Worktrees: "Attribute a parallel session's action by execution evidence in that session's own transcript" and "forbid destructive git ops on any tree with uncommitted work; re-verify tree integrity before trusting results produced mid-edit"; global §Tooling: "Scope destructive actions to targets you own"; tooling-gotchas §Git: "Reverting a path is not undoing your edit", "Dirty-worktree pulls"; §Config: "Shared live config has concurrent writers". None states the trigger (an unexplained delta in tree/index/config as the signal of a foreign operator), the attribute-before-write step, commit-by-pathspec / revert-by-provenance, or the predicted-delta check before promoting a shared service revision.

**Placement:** guides/tooling-gotchas.md §Git (new entry after "Dirty-worktree pulls"), with one cross-reference sentence in §Config, secrets, and managed services next to "Shared live config has concurrent writers"

**Why (strength):** Five independent sessions (five distinct session ids), four of them tagged rare_high_cost and two rollback: a phantom merge commit plus on-disk file mutation, 25 foreign staged files nearly swept into a commit, a concurrent refactor nearly wiped by a whole-tree discard, an unreviewed flag that would have shipped with a promotion, and a NameError left by another process mid-edit. The general form (foreign delta → attribute → act only on provenance-proven paths) is invariant across git tree, index, and managed-service config. Not 5 because the baseline already holds the destructive-ops prohibition and the attribution-by-evidence rule; the addition is the trigger and the constructive procedure.


### Every input shaping a cached/generated artifact must be in its cache key

`partial` · strength 4 · 2 sessions `claude:e1b285d7 claude:7832145a` · ⑤rare-hi-cost ②rollback

**Rule:** When an artifact is generated, cached, or resumed from a stage output, its cache-hit or fingerprint predicate must cover every value that shapes its content — the upstream input's content identity, budgets and caps, templates, model ids, and config — never artifact existence, mtime, or size alone. When introducing any new value that shapes such an output, inspect the key's pre-image in the same change and add a check that the key moves when the value moves. Before re-running a multi-stage pipeline because an upstream input changed, read each stage's hit predicate first; if it omits the input's identity, invalidate the downstream intermediates explicitly, because a "regenerate" over existence-keyed caches re-derives from the old input and can publish output worse than what it replaces. Applies to any keyed reuse on a product or verification path; ephemeral tool-managed caches cleared per run are out of scope.

**vs baseline:** cli-multi-model-workflow.md §Halt And Resume ("Resume-first from artifacts that ... match their recorded source/config/HEAD fingerprint") covers the consumer side of checking a fingerprint but not the authoring rule that the key must include every output-shaping input; tooling-gotchas.md "Stale caches in rapid loops" covers only mtime/size-keyed compile caches in mutation loops. Partially covers.

**Placement:** guides/cli-multi-model-workflow.md §Halt And Resume (extend the fingerprint bullet with the key-completeness rule and the invalidate-before-regenerate step)

**Why (strength):** Two independent sessions (different session ids, different systems — an LLM prompt fingerprint missing a new char cap, and a translation pipeline whose stage caches were keyed on file existence rather than transcript fingerprint). Both were rare-high-cost: one shipped worse output (76.9% repetition) than what it replaced until caches were invalidated, requiring rollback; the other was caught only by cross-verification. The rule generalizes cleanly beyond either case, and the baseline states only the consumer-side check, so it is a genuine extension rather than a restatement.


### Enforce transport limits in the provider's unit on the serialized wire payload

`partial` · strength 4 · 3 sessions `claude:0b29a54a claude:2fa2565f claude:491e8fad` · ②rollback ①hi-tok ⑤rare-hi-cost ④recur-err

**Rule:** When a transport, provider, or context limit bounds what you send, take the unit (bytes, characters, tokens) and the value from the provider's own rejection payload or a live probe — never from documentation, a comment, or a variable's name — and measure the serialized wire payload exactly as the consumer receives it (after encoding, escaping, wrappers, and any duplicated representations), not the object you assembled. A character count against a byte limit undercounts multibyte text and stays hidden while inputs are ASCII; a cap on the number of items bounds nothing about size; a budget whose name says one unit and whose value means another recreates the defect on the next edit. Enforce at the single dispatch chokepoint, derive every local budget, reservation, and charge from that one adapter constant in that one unit, and add a boundary test showing the guard admits exactly what the provider admits. Applies to any locally enforced external size limit; it does not cover semantic token budgeting for prompt quality, which is a judgment rather than a measurement.

**vs baseline:** Partially covers: global CLAUDE.md §Verification Discipline "fix a common basis — units, denominators, population, measurement surface"; §Tooling and Operational Safety "confirm [a] runtime constraint empirically against the live or installed artifact"; guides/llm-capability-boundary.md "provider schema limits are known and probed before relying on them" and envelope/serialization as runtime-owned; guides/tooling-gotchas.md §"Tool output is a rendering, not the bytes" (byte-exactness, but only for reading, not for enforcing a limit). None names the bytes/chars/tokens unit trap, the count-cap vs size-cap confusion, measuring on the serialized envelope as received, or single-sourcing the limit constant at the dispatch chokepoint.

**Placement:** guides/tooling-gotchas.md §Tool output is a rendering, not the bytes — add a bullet "Transport limits: measure the wire payload in the provider's unit"; cross-reference from guides/llm-capability-boundary.md verification_focus line "provider schema limits are known and probed before relying on them".

**Why (strength):** Three independent sessions (three distinct session ids, different codebases/mechanisms) each paid a real cost: one shipped a guard that undercounted multibyte payloads against a 1MB byte limit and misread an item-count cap as a size cap (rollback); one misdiagnosed clipping as page merging until re-measurement showed the envelope rendered at 2.1-2.3x the payload, with a ~2x overfill of worker context (high_token, rollback); one had the limit recorded in the wrong unit and only the provider's rejection payload exposed it (rare_high_cost). The general form is clear and invariant-shaped, and the baseline only has adjacent generic rules, so this is a genuine gap. Not 5 because the trigger is recognition-dependent and belongs behind a guide pointer, not in the global.


### A small or single sample says nothing about a stochastic property; establish noise floor and re-sample

`partial` · strength 4 · 3 sessions `claude:0e84f213 claude:19a169b2 claude:04d26700` · ②rollback ⑥quality ①hi-tok

**Rule:** A single case, or a handful that all agree, settles whether a path is reachable — never how often a stochastic behavior holds. Before quoting any rate-shaped property as a fact (determinism, reproducibility, flake rate, a judge or reviewer panel's unanimity, an A/B effect): first confirm the mechanism honors the controls you think you set (a seat may accept temperature or seed and reproduce nothing); establish the noise floor from already-existing repeated runs of the same input before spending new calls; then run enough trials to bound the rate, with a no-treatment control so the effect is attributable, on the real pipeline path rather than a differently-prompted raw probe. If the floor exceeds the effect you planned to detect, the premise is broken — record that before redesigning. Report a panel tally as a sample with its split and margin, and re-sample before a decision rides on "unanimous"; in resumable workflows, key caches on stable inputs, or every resume silently re-rolls the judges. The N=1 probe stays the default for deterministic reachability questions; this rule binds only claims about frequency or agreement.

**vs baseline:** guides/verification-discipline.md §Proportion the depth before you spend — partial: endorses "Probe at N=1 ... a single well-chosen case that reaches the real path" without bounding it to reachability, and §Independent review covers same-kind agreement as blind-spot-sharing but treats a panel verdict as a verdict, not a sample; §Keeping E2E honest names flakiness but not how to measure it. Global "confirm capability empirically" and "fix a common basis before comparing" are adjacent but do not name noise floor, sample size, or a no-treatment control.

**Placement:** guides/verification-discipline.md §Proportion the depth before you spend (extend the N=1 probe bullet with its boundary and the rate-estimate procedure; one cross-pointer from cli-multi-model-workflow.md §Cross-Verification Economy on panel tallies as samples)

**Why (strength):** Three independent sessions (three distinct session ids) each hit the same failure from a different angle: a 3/3 seed-reproducibility claim retracted at N=6 with a control (rollback), a 3:0 judge panel that became 2:1 on re-run (quality lever, resumed workflow re-rolled the judges), and a judge-determinism redesign whose premise broke once existing four-roll repeats showed the noise floor (high token, rollback). Materiality is high — two retracted claims and one abandoned design — and the baseline's own N=1 endorsement actively invites the error, so the boundary is load-bearing. Not 5 because all three sessions are same-provider and the general form is a known statistical principle, so the corpus-specific value is the boundary against the N=1 rule rather than a new idea.


### Localize a metric change in time against deploy history before blaming code

`partial` · strength 4 · 2 sessions `claude:53b3e2eb claude:925a97c9` · ①hi-tok ②rollback ④recur-err

**Rule:** When a live metric collapses, reads zero, or steps across a pre-declared threshold, localize the change in time before diagnosing the feature or code you were asked about: first confirm the whole inbound pipeline is alive (every source, a per-period series, distinct producers), then compare only contemporaneous cohorts (items produced and judged in the same window, never re-processed rows), bracket the transition to the finest time unit the data supports, and read the deploy or audit log around that instant — a change landing within seconds of the last-good point is the prime suspect, and a step in a window with no deploys is an input-population shift whose fix is in scoping the measured population, not in the model, prompt, or code. Declare the pass/fail threshold before looking at the data, and never treat a failure seen from your own vantage (a 404 from your machine, your own access restriction) as the fleet's failure until confirmed from theirs. Applies to any measurement whose producers and consumers change on different clocks; it does not replace fixing the comparison basis, which comes first.

**vs baseline:** Global CLAUDE.md §Verification Discipline ("fix a common basis — units, denominators, population ... exclude or flag non-representative data") and §Tooling and Operational Safety ("treat a coarse runtime signal as a hypothesis ... confirm against the authoritative low-level evidence before attributing blame") cover the comparison basis and the signal-as-hypothesis stance. Neither the global nor guides/verification-discipline.md ("When a green means nothing") gives the temporal-localization order — pipeline liveness, contemporaneous cohorts, bracketing the transition, correlating the last-good instant with the deploy/audit log, or reading a no-deploy window as a population shift. Partial coverage.

**Placement:** guides/verification-discipline.md §When a green means nothing — new sibling section "Before blaming code for a metric change" (after the empty-subject/quiet-control list, before Keeping E2E honest)

**Why (strength):** Two independent sessions (different systems: a self-update event pipeline that went to zero, and a classification quality metric that stepped past a FAIL threshold) each burned a probe/build cycle on a code-side theory before a time-series plus change-log correlation found the real cause; in one, a handoff's causal claim was disproved and two downstream tasks lost their basis (rollback), in the other cause was briefly mis-attributed to the agent's own vantage-point 404. Both are high_token and both retract a prior conclusion, so materiality is high; the failure mode is recognition-independent (the agent already knows it is diagnosing), so it belongs behind the guide pointer rather than in the global. Not 5 because n=2 and the two member principles disagree on emphasis (liveness-first vs cohort/threshold-first), which the merged form reconciles.


### Test state must be what the real producer emits, not hand-built fixtures

`partial` · strength 4 · 3 sessions `claude:7cb9f6f4 claude:e00e9bf4 claude:78287a0a` · ②rollback ④recur-err ⑥quality

**Rule:** The input state of a test is only evidence when the thing that produces it in production produced it. Before trusting a fixture, seeded document, pre-configured gate, or state-machine head, ask where it came from: a wire fixture must be a raw response captured through the same client code that will parse it — never a CLI's rendered listing, a doc example, or a hand-rewritten payload; an E2E for a gated or staged feature must run with the gate in its production setting and receive the intermediate state its real upstream stage leaves behind, not a pre-seeded final state; and a reducer or state-machine test head must be a state that some real prior transition could reach, with its expected next state derived from an oracle independent of the code under test and asserted, not merely "event accepted". A fixture that is schema-valid but could never arise from the real producer, or that already contains the outcome the test exists to verify, passes without the mechanism running — it validates the fixture, not the code. Before declaring a decoder, payload builder, or gated path done, replay the code's own output against the live producer once (read-only or zero-cost), and treat a missing-field or unreachable-state defect as a class: probe every sibling built the same way. Boundary: this governs the provenance of test inputs and expected outputs; it does not require live services on every commit — a cheap stand-in may run per commit provided it was captured from, and is periodically re-captured from, the real producer.

**vs baseline:** guides/verification-discipline.md §"Deriving the case space" ("record the verdict, do not type it") and §"When a green means nothing" ("the fixture that misses the guard") partially cover: they govern the VERDICT's provenance and one guard-routing trap, but not the provenance of the test's INPUT state. Global §Verification Discipline ("real dispatch and real calls, not a mock") and guides/mock-realization-boundary.md ("who owns semantics" table; real service owns semantics) cover the execution path, not where fixture content comes from. Nothing names hand-seeded outcomes, rendered-output-derived fixtures, unreachable state heads, or the circular oracle.

**Placement:** guides/verification-discipline.md §When a green means nothing — new bullet "The fixture the producer never emits" beside "The fixture that misses the guard", with a one-line cross-reference from guides/mock-realization-boundary.md §Central Fixture Boundary (fixture provenance)

**Why (strength):** Three independent sessions (7cb9f6f4, e00e9bf4, 78287a0a), and member 17 cites two further sibling sessions with the same pattern (lease-flow-seeded takeover bug, catalog payload replayed live). Every member carries rollback — tests were rewritten after a green suite (2,871 passing tests in one case, all mutations killed in another) was shown to have tested the fixture rather than the code — and one carries recurrent_error. Materiality is high: the false green survived until a frontier review or a live probe, exactly the false-pass selection effect. The general form is clear and spans three shapes (wire fixture, gated E2E, reducer head), so it is neither too_specific nor weak; it is partial rather than novel because the baseline already governs verdict provenance and the execution path, leaving only input-state provenance unstated.


### Blind-packet reviewer agreement is about the packet; one seat needs real grounding

`partial` · strength 4 · 3 sessions `claude:4a86412d claude:e368f4a2 claude:145a37cb` · ②rollback ⑥quality ⑤rare-hi-cost ④recur-err

**Rule:** When every reviewer or drafter was fed the same blind packet with no access to the code or environment, their convergence — across providers or families — is evidence about the packet's framing only, and it inherits every omission and mismeasurement the packet carries. Before adopting a converged verdict or mechanism that rests on a concrete code seat, a measured environment fact, or a constraint list, route at least one independent seat with live read access whose brief is to re-derive those load-bearing facts and falsify them; a lone dissent that cites a real constraint outweighs a blind majority, and the missing fact is folded back into the packet. This adds an evidence-access axis to the independence ladder; it does not replace provider or model difference, and a packet-only review still counts for internal consistency.

**vs baseline:** guides/cli-multi-model-workflow.md §Default Frame and §Review Independence, plus verification-discipline.md §Independent review: cover same-kind blind-spot sharing, the provider/model/effort independence ladder, and "re-verify each finding against real code" — partial. Nothing states that a blind packet makes cross-provider convergence share the packet's blind spot, nor that one seat must hold live grounding access to falsify measured facts.

**Placement:** guides/cli-multi-model-workflow.md §Review Independence (new bullet: evidence access as a distinct axis, cross-referenced from §Dual-Provider Design Drafts adjudication)

**Why (strength):** Three independent sessions each hit the same failure shape from different angles: cross-family blind drafts converged on a nonexistent code seat and the design had to be rolled back; four hermetic review rounds closed clean while a repo-access reviewer found a blocking environment fact; a two-of-three cross-family majority chose an already-recorded rejection and only the grounded dissent caught it. Materiality is high (design rollback, blocker missed until late) and the general form is clear: the existing ladder grades provider/model/effort but never asks what evidence the seat could see. Not 5 because the corpus already covers half the idea (blind-spot sharing, re-verify against real code), so this is an extension rather than a new rule.


### A found instance is a sample of a class; enumerate the class deterministically

`partial` · strength 4 · 3 sessions `claude:d77c4de3 claude:4cc04644 claude:184862c3` · ⑥quality ①hi-tok ③re-explore ②rollback

**Rule:** When a defect turns out to be an instance of a repeatable assumption — a hard-coded literal (URI scheme, provider name, path prefix, version), a reused plan or template, a call-site pattern — treat the first instance as a sample, not the defect: before scoping the fix, enumerate every occurrence of the same shape deterministically from the artifact (grep, call-site list, route table), confirm which sit on the live path, and fix the set once with a check derived from that enumeration. Do not rely on further review rounds or on a residual list to surface the siblings — an adversarial reviewer returns the cheapest single counterexample per round and so samples the class rather than exhausts it, and a batch of leftovers labeled "needs human judgment" must be opened and compared by signature first, since residuals sharing one signature are one mechanical defect, not N judgment calls. Boundary: applies once the found defect has an identifiable structural shape; a genuinely one-off logic error has no class to enumerate and is fixed as itself.

**vs baseline:** coding-staged-workflow.md "Fix the cause at its authority" (instances are a class, single-source and fix the class — reactive: triggered only after fixes keep revealing instances) and §Stop Conditions (recurring instances across rounds = refilling queue). Partially covers: the baseline recognizes the class only after repeated rounds reveal it; it omits the proactive enumeration on the first instance, the mechanism (a reviewer yields one cheapest counterexample per round, so rounds cannot converge on a class), and the residual-classification trigger (compare signatures before declaring leftovers human-only).

**Placement:** guides/coding-staged-workflow.md §Stop Conditions — extend the "recurring instances ... refilling queue" bullet with the first-instance enumeration rule and the residual-signature check; cross-reference from review-defect-criteria.md (round non-convergence)

**Why (strength):** Three independent sessions (a migration bug whose s3:// sibling was found only by grepping the literal; a month-long retrospective formalizing that adversarial review returns one cheapest counterexample per round and a material count oscillating 9→7→10 that closed only by re-scoping; eleven "human-judgment" residuals that proved to be one mechanical defect on inspection). Materiality is real: wasted review rounds (high_token, re_exploration) and a flipped completion verdict (rollback). The baseline states the class idea reactively; the missing part is the trigger moving from "after rounds refill" to "at the first instance", which is a clearly general, cheap rule. Not 5 because none of the evidence is rare-high-cost catastrophic.


### Derive a new config revision from the live one and diff before applying

`partial` · strength 4 · 2 sessions `claude:e53c5874 claude:63a3202f` · ⑤rare-hi-cost ③re-explore ⑥quality

**Rule:** Live-config revisions regress from the wrong base, not from the edit: when a deployed config, env set, or secret mount is re-authored from a template, an example file, or a command line that replaces the whole set rather than merging, every field or entry not restated silently reverts to its default or disappears — and wrapper scripts commonly default the sensitive half (secrets) to off. Before signing or applying any such revision, render the exact set the command will send, derive it from the last live artifact rather than from a template, and diff it field by field against what the live resource currently carries; treat any entry that disappears or any operational value that moves backward (a version floor, a recovery flag, a mounted secret) as a blocker to explain, never a default to accept. After applying, re-read the live resource instead of trusting the command's success message. Applies to any replace-semantics config path (deploy env flags, signed release configs, generated manifests); the merge-semantics case is the neighbouring orphan rule, and both directions must be checked because a command's semantics are rarely labelled.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — 'Merge-not-replace update APIs' covers only the merge direction (stale orphans left live), 'Verbatim slicing over parse-reserialize' covers content loss when rewriting a config file; global §Tooling and Operational Safety 'snapshot the last good state before any in-place resume or overwrite' is a generic precaution with no render-and-diff-against-live behavior. Partially covers; the replace-all direction and the derive-from-live/diff-before-apply discipline are absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet placed directly after 'Merge-not-replace update APIs' so both directions are named together

**Why (strength):** Two independent sessions (different session ids, different systems: a signed release config re-authored from a template that reset a version floor; a Cloud Run deploy script whose --set-env-vars would have wiped ten mounted secrets and a live recovery flag). Both are rare-high-cost — a silent security-floor regression and a near-miss production secret wipe — and the general form (replace-semantics revision derived from the wrong base) is clearly invariant across tools. Baseline names the exact opposite failure mode in the same section, which confirms the gap is real rather than a restatement. Not 5 because one instance was a caught near-miss rather than an incurred loss and recurrence is two sessions.


### A checker must call the real implementation, not reimplement the rule

`partial` · strength 4 · 2 sessions `claude:7014c92d claude:7aad389d` · ②rollback ⑤rare-hi-cost ⑥quality

**Rule:** When a gate, probe, or measurement must agree with a judgment the product already implements, do not recompute that judgment inside the checker — a checker that re-derives the rule is a second implementation that must agree with the first, and it stays green when the production wiring is reverted (a dropped argument, a skipped call) because it never looked at the wiring. Have the checker call the shipped code path on real inputs; if that path sits behind a boundary the checker cannot import, split it into a collector that only records the real inputs and a replay that runs inside the boundary and calls the real function, rather than copying the rule out. Extend the negative-control set accordingly: mutate the call-site plumbing, not only the function the checker invokes directly. Boundary: a check that deliberately holds an independent oracle (a second, differently-derived answer for a specific value) is a contrast control, not a restatement, and is exempt as long as it is declared as such.

**vs baseline:** verification-discipline.md §When a green means nothing ("revert the fix it guards and watch the check fail") and §Deriving the case space ("Record the verdict, do not type it. Run the real path"); global Verification Discipline bullet on green only through real dispatch; concept-economy core rule "one value has one owner, generated not restated". Partially covers: the real-dispatch and revert disciplines exist, but none says a checker that re-derives the rule is a restatement blind to call-site reverts, nor gives the collector/replay split when the real function is unreachable.

**Placement:** guides/verification-discipline.md §When a green means nothing — new bullet "The checker that re-derives the rule", immediately before the closing "revert the fix" sentence, with the collector/replay split as its second clause

**Why (strength):** Two independent sessions (claude:7014c92d, claude:7aad389d) reached the same design rule from different angles — one a gate that recomputed a landing seat and stayed green with seven controls while the original defect was restored at the call site (rollback + rare-high-cost: found only by a cross-family reviewer), the other a drift probe deliberately split into collector + in-boundary replay to avoid two implementations that must agree (quality lever, then positive-controlled). Materiality is high — the failure is a false PASS about the gate itself, which the corpus already names as its worst defect class — and the form is general across gates, probes, and measurements. Not 5 because the second session is a prevention rather than a paid failure, and the rule is an extension of an existing bullet rather than a wholly new section.


---

## Strength 3  (66)

### Split commits: prove each green alone in a scratch worktree

`novel` · strength 3 · 2 sessions `claude:8cef67ae claude:e3a47ef7` · ⑥quality ②rollback

**Rule:** When one change is divided into several commits, order them by dependency and prove each commit green on its own — check it out into a throwaway worktree and run the build, tests, and gates there — before pushing; a series that is only green at the tip hides a broken bisect point and a commit that cannot be reverted independently, and a staged rename or shared hunk leaking into the wrong commit is the usual cause. Before merging such a series, check whether any handoff, decision record, or doc cites the branch's commit hashes; if so, merge with a merge commit rather than squash or rebase, which rewrite every cited hash. Applies to deliberate multi-commit splits, not to a single-commit change.

**vs baseline:** guides/tooling-gotchas.md §Git operations covers stale base ranges, two-dot diff, path reverts, and dirty-worktree pulls; guides/cli-multi-model-workflow.md handoff rules cover "never record the hash of the commit that will contain the record itself". Neither covers per-commit standalone verification of a split series, bisectability, or choosing a SHA-preserving merge when records cite branch hashes — omits.

**Placement:** guides/tooling-gotchas.md §Git operations

**Why (strength):** Two independent sessions (claude:8cef67ae, claude:e3a47ef7) practiced the same per-commit worktree check, and one hit a concrete rollback-class defect (a staged git mv leaked into the first of seven commits, making it non-buildable alone) that forced re-cutting the series. Materiality is moderate — a broken bisect point or non-revertable commit costs a real investigation later, but it is not rare-high-cost. The rule is general (any repo, any multi-commit split) and mechanically actionable, and the SHA-preservation corollary extends the existing hash-stability handoff rule without restating it.


### Tag material with its subject and cross-check siblings for content bleed

`novel` · strength 3 · 2 sessions `claude:cb10169f claude:80385459` · ②rollback ④recur-err

**Rule:** When writing about more than one distinct subject (people, companies, cases, accounts) from one context — whether several sibling deliverables or one document that draws on mixed source material — bind every captured item to its subject and confirmation status at capture, refuse to narrate an item under any subject until that binding is confirmed, and before delivery run a deterministic cross-check of subject-specific proper nouns and figures across all outputs: a term or fact belonging to subject A appearing under subject B is the signature of context bleed. Keep a figure in the same sentence as its composition wherever it is stored, since a detached number is read in its worst plausible sense. This applies to prose deliverables authored from user-supplied or interview material; it does not add a step to single-subject writing.

**vs baseline:** verification-discipline.md §Verification Menus "Docs" bullet (links, terminology, current-behavior alignment, historical-note references) — omits subject attribution and cross-output contamination; global §Multi-Model Workflow bullet on attributing a parallel session's action by execution evidence not token mention is the nearest analogue but is about sessions/commits, not written subjects; the co-authoritative-section propagation rule covers replication completeness, not bleed. Omits.

**Placement:** guides/verification-discipline.md §Verification Menus — extend the "Docs" bullet (or add a "Multi-subject prose" bullet beside it)

**Why (strength):** Two independent sessions (different session ids, different tasks: a report narrating a third-party case as in-house; six per-interviewee documents with one person's content bled into another's), both surfaced as a user-caught rollback and one recurring within its session ("same check skipped for C5"). Materiality is real — misattributing facts to the wrong company or person is a reputational/factual error that no existing gate or menu entry catches — but the evidence is only two sessions and the check is cheap, so mid strength rather than 4–5. The general form (subject binding + deterministic proper-noun cross-check) is clearly not a one-off.


### CLI-printed access tokens are cached; a long-running observer must force a fresh mint

`novel` · strength 3 · 1 session `claude:98c3d959` · ④recur-err ⑤rare-hi-cost

**Rule:** A cloud CLI's "print access token" command usually returns the token it already holds in its own cache, so a scripted "refresh" that re-runs it re-issues nothing and the process still dies at the original token's expiry. For any observer, watcher, or loop whose runtime exceeds a short-lived credential's lifetime, make the refresh path force a genuine re-mint (an explicit re-auth or refresh-token exchange, or the client library's own refresh) rather than re-reading the CLI, and verify the fix only by watching the process cross the previous failure point without a 401 — a refresh that has not yet outlived the old token has proven nothing. Does not apply to one-shot commands that finish inside a single token lifetime.

**vs baseline:** guides/tooling-gotchas.md §Ambient state drifts — pin it ("Installed is not running") and §Config, secrets, and managed services: nearest analogues (a live process keeps stale state; stale definitions stay live after an update), but neither mentions credential caching, token lifetime, or refresh paths. Omits.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** One independent session (claude:98c3d959), but the error recurred twice within it (first watcher at ~7 min, replacement with a "refresh" again at <10 min with 401) and cost a canary observation window each time before the third, force-re-minted watcher survived — rare-high-cost plus repeated error inside one session. The mechanism (CLI token caches, e.g. gcloud/aws/az) is well-known and general across cloud CLIs, so a general form clearly exists; strength capped at 3 for single-session recurrence. Verified absent from the baseline text: no bullet covers token caching, credential lifetime, or long-lived-process refresh.


### Browser-automation tabs do not share the user's login and stall when backgrounded

`novel` · strength 3 · 1 session `claude:c717c714` · ③re-explore ④recur-err

**Rule:** Before driving a web page through a browser-automation tool, assume two properties of the automation context and plan around them rather than discovering them turn by turn: (1) the automation tab has its own session state — the user's existing login is not shared with it, so when a login screen appears, have the user authenticate inside the automation window itself instead of moving or regrouping tabs to borrow the session; (2) the tab being driven must stay in the foreground — browsers throttle timers, layout, and rendering in background tabs, so an interaction sequence that depends on element positions or timing silently stalls part-way through when the tab is backgrounded. Ask the user to foreground the tab (or drive one tab at a time) before concluding the page or the tool is broken. Applies to any tab- or profile-based browser automation (extension-driven tabs, headed Playwright/Puppeteer, remote-debugging sessions); it does not apply to headless contexts, where neither the shared-login expectation nor foreground throttling arises.

**vs baseline:** guides/tooling-gotchas.md — closest is "Ambient state drifts — pin it" (session/context drift generally) and the global rule "never auto-open a browser for a non-default identity"; neither mentions browser-automation session isolation or background-tab throttling. Browsers otherwise appear only as render targets. Omits.

**Placement:** guides/tooling-gotchas.md §Browser automation (new subsection, after "Own what you spawn"), two bullets: "Automation tab has its own session" and "A backgrounded tab is throttled"

**Why (strength):** Genuinely absent from the baseline (verified by grep for browser/tab/login/headless/backgrounded terms — only render-target and identity-gating mentions exist). Evidence is a single session (one independent tag), so recurrence is thin, which caps strength. Materiality is moderate: several turns of re-exploration (tab regrouping, re-login) plus a stalled run at 3/8 items that needed user intervention. The two mechanisms are stable, documented browser invariants (isolated automation cookie jar; background-tab throttling), so the rule generalizes cleanly beyond the one tool used and is not too_specific. Guide placement, not global: the failure mode is recognition of a browser trap, which belongs behind the tooling-gotchas pointer.


### dockerignore patterns anchor at the context root; verify a built image holds no secrets by listing inside it

`novel` · strength 3 · 1 session `claude:6de415d0` · ⑤rare-hi-cost ⑥quality

**Rule:** When a build packages a directory into an image or archive that will leave the machine (container image, bundle, tarball), treat the ignore file as a filter whose semantics must be measured, not read: a bare filename pattern matches only at the context root, not in subdirectories, and an extension glob misses same-purpose credential files carrying another extension. Never conclude the artifact is secret-free from the ignore patterns or from a clean sibling that used selective copying; list the built artifact's own filesystem for credential-shaped files (env files, keys, tokens, service-account JSON) as a named negative control, and repeat that listing whenever the build context, copy steps, or ignore file change. Applies to any root-anchored ignore/include filter feeding a shipped artifact; plain source-control ignores that never ship are out of scope.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — omits: it covers verbatim config slicing, merge-not-replace update APIs, revision-vs-traffic, and perimeter logs, but nothing on build-context ignore semantics or verifying packaged artifact contents. Global CLAUDE.md §Tooling and Operational Safety secrets bullets cover accepting/echoing secrets, not packaging them. §Verification Discipline's generic "verify against the artifact, not a document about it" is the nearest principle but names no build-context trigger.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Single independent session (1 tag), so recurrence is weak, but materiality is high: a service-account key and an infra .env were confirmed inside a built CI image, found only by cross-family review, and the fix was proven with a negative control that named both files inside the tainted image — a rare, high-cost credential-exposure class with a mechanism (root-anchored ignore patterns, extension-literal globs) that generalizes to any packaging filter. The baseline states nothing about build-context ignore semantics or listing a built artifact's contents, so it is genuinely novel; strength capped at 3 for one-session evidence.


### Run git check-ignore on any path cited as authority or created as a durable record

`novel` · strength 3 · 1 session `claude:6de415d0` · ④recur-err ⑤rare-hi-cost

**Rule:** Before treating a path as durable — a newly created ledger or record that must survive a clone, or a file that code or docs cite as their authority — ask the VCS whether it is ignored (`git check-ignore -v <path>`) and confirm it is tracked (`git ls-files --error-unmatch <path>`). Broad ignore patterns written for runtime state (`*.jsonl`, `runs/`, `out/`) silently absorb a new durable file of the same shape, and a tracked file pointing at an ignored path is an authority that exists in exactly one checkout and in no build or CI context. Fix by adding a negation rule for the specific file and prove it with a sibling that stays ignored; do not fix by loosening the broad rule. Does not apply to genuinely ephemeral output, which should stay ignored.

**vs baseline:** global CLAUDE.md §Coding Guidelines ("artifacts out of tool-managed temp locations into a durable home") and guides/review-request.md (untracked files are invisible to diff-based review) are adjacent but omit this: neither says an ignore rule can swallow a durable artifact, nor that a path cited as authority must be tracked. guides/tooling-gotchas.md §Git operations covers ranges, restores, and dirty pulls only. Omits.

**Placement:** guides/tooling-gotchas.md §Git operations

**Why (strength):** Two independent incidents in two repos (one session's tracked code citing an ignored spec path that vanished in the container build; a separate session where a new decisions ledger was swallowed by a runtime-log ignore rule and needed an exception plus negative control). Materiality is real — an unverified authority path is a rare-high-cost failure discovered only at build/clone time — but the cluster carries one candidate tag and the second incident is cited rather than independently tagged, so recurrence evidence is moderate. Fully general (any repo with broad ignore patterns), cheap check, and absent from the baseline.


### Pin the reviewed revision so stale findings are recognized

`partial` · strength 3 · 2 sessions `claude:8b899a66 claude:ce655f95` · ①hi-tok ②rollback ⑥quality

**Rule:** A review packet names the exact revision it was dispatched on (commit or content hash), and the artifact under review stays frozen until every reviewer on that revision has returned. When a fix must land while a reviewer is still in flight, the returned findings are first mapped against the pinned revision versus the current one: a finding whose anchor text no longer exists is classified stale and closed by that mapping, never re-fixed or counted as open; only findings that survive on the current revision enter the round's tally. This binds parallel and sequential review rounds alike; it does not require withholding fixes, only labeling which revision each verdict judged.

**vs baseline:** cli-multi-model-workflow.md (bundle line ~324): "Give reviewers/subagents a read-only diff, snapshot, or isolated worktree — not the live tree the main is editing ... re-verify tree integrity before trusting results produced mid-edit" — covers giving reviewers a snapshot, and the review ladder requires a receipt of "the declared packet on the exact seat". Neither states that the packet carries a revision id, that the revision is frozen until all parallel lenses return, or that findings returned against a superseded revision are triaged as stale before counting. review-request.md §"Say what the target is, and what absence means" names stage context only, not revision identity. Partially covered.

**Placement:** guides/review-request.md §Say what the target is, and what absence means (extend: the target includes its revision id; findings on a moved revision are triaged stale-vs-live before entering the tally)

**Why (strength):** Two independent sessions (different session ids, same provider) hit the same failure shape: a parallel lens judged a superseded draft, returned findings already closed, and forced a reconciliation pass (high-token, rollback of a counted finding). Materiality is moderate — wasted round and a risk of re-fixing or mis-tallying, not an irreversible loss. The baseline already gives reviewers a snapshot, so this is an extension (label the revision, triage stale findings) rather than a new rule; general form is clear and applies to any multi-reviewer round.


### A negative-control mutation must be shown to have actually applied and changed behavior on the inputs used

`partial` · strength 3 · 2 sessions `claude:b25fcb8c claude:dd433796` · ④recur-err ⑥quality ②rollback

**Rule:** Before crediting a negative control, prove its mutation landed: assert that the corrupted, removed, or altered input actually differs from the original (construct the corruption deterministically, never by scanning random or generated data for a spot to hit), and that the inputs the control feeds actually traverse the mutated branch — enumerated from the artifact, not one convenient case. A control whose mutation silently became a no-op reports a rejection that was never exercised, and it can pass green intermittently; the assertion that the mutation applied is part of the control, placed before the assertion that the system rejected it. This adds to, not replaces, the revert-and-watch-it-fail check, which cannot catch a mutation that never happened on the run being read.

**vs baseline:** guides/verification-discipline.md §When a green means nothing — "The fixture that misses the guard" covers inputs routing around a branch, "The control that went quiet" covers list-indexed controls, and the closing "revert the fix and watch the check fail" covers a control that survives a revert. None states that the planted mutation itself can silently not apply (random-scan finds nothing to flip; guard removed on a path the fixture never enters) and that the control must assert the mutation took effect before asserting rejection. Partially covers.

**Placement:** guides/verification-discipline.md §When a green means nothing — new shape "The mutation that never landed", beside "The fixture that misses the guard", and extend the closing discipline sentence to name the mutation-applied assertion

**Why (strength):** Two independent sessions (one a flaky tamper test whose corruption step found nothing to corrupt ~7% of runs; one a gate negative control whose removed guard sat on a branch the legacy fixture never entered, later also missing the exact presets that drove the decision). Both are false-pass shapes in the control itself, the class the baseline already says dominates cost, and both were caught only by looking rather than by any existing check. General form is clear and fits an existing list in the guide; recurrence is only two sessions and materiality was moderate (caught before shipping), so mid strength.


### Probe a seat with a known-invalid control before trusting exit 0

`partial` · strength 3 · 2 sessions `claude:173b9f9f claude:f28794e7` · ⑥quality ⑤rare-hi-cost ④recur-err

**Rule:** Before reading a successful exit status as proof that a CLI, adapter, or API accepted a parameter value (model, effort, flag) or that a dispatch seat is live, send one deliberately invalid value through the same path first and confirm it fails; only then run the minimal valid probe. A tool that also exits 0 on garbage (warning and silently downgrading to a default) is fail-open, and its exit code certifies nothing — read acceptance from the tool's echoed effective setting or the provider's response instead, and record which tools are fail-open so the control is not rediscovered. Applies whenever the acceptance probe gates spend on a long or multi-pass dispatch or a pass/fail decision; a one-off interactive command needs no control.

**vs baseline:** Global §Tooling and Operational Safety ("confirm it empirically ... a minimal probe") and review-request.md §AI workbench/harness ("run the instrument against an input whose answer is known to be the opposite") plus the personal learning on testing the instrument on agreement — partially cover: the known-opposite check exists for instruments and PASS verdicts, but the minimal-probe rule itself is stated as a positive probe only, and nothing says a positive probe is vacuous on a fail-open CLI (exit 0 on an invalid value, silent downgrade), nor to read the echoed effective setting instead.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (new bullet "Fail-open option handling" after "Command resolution"), with the global §Tooling and Operational Safety "minimal probe" clause extended by "and disprove it with an invalid value first"

**Why (strength):** Two independent sessions (different session ids) hit the same mechanism, one from the review-dispatch side (control dispatch rc=1 then rc=0 before a 3-pass frontier review) and one from the CLI side, where the observation is concrete and material: one CLI rejected an invalid effort with rc=1 while another accepted it with rc=0 and silently used the default, so a positive-only probe would have certified a mis-tiered reviewer — a rare-high-cost false signal that the baseline's existing "minimal probe" wording actively invites. The general form (invalid control before positive probe; exit code has no discriminating power on fail-open tools) is clearly not repo-specific. Held at 3 rather than higher because recurrence is two sessions and the known-opposite idea already exists in the corpus for instruments, so this is an extension, not a new principle.


### A check's expected value must differ between the alternatives it discriminates

`partial` · strength 3 · 2 sessions `claude:b045388b claude:565c072e` · ⑥quality ②rollback ④recur-err

**Rule:** When a check exists to tell two states apart — translated vs. source text, a value read from field A vs. its sibling B, before vs. after a split or transformation — choose an expected value that is different in the two states. An expectation that happens to be identical on both sides (a proper noun that passes through translation unchanged, two fixture fields set to the same value, a default shared by both branches) passes whether or not the mechanism ran, so the check discriminates nothing. Before trusting it, point the assertion at the wrong side (the untranslated variant, the other field) and watch it fail; pair a positive assertion on the changed variant with an identity assertion on the untouched one. Applies to any test, gate, or probe whose verdict is a comparison against an authored value; it does not require distinctness where the two states genuinely share the value by contract — there the check belongs on a different observable.

**vs baseline:** verification-discipline.md §Deriving the case space ("Make the criterion falsifiable before you make it green ... a negative or contrast control") and §When a green means nothing (five vacuous-green shapes; closing rule "revert the fix and watch the check fail") — partially covers: the revert discipline would catch both incidents in principle, but no shape names the expected value itself being indistinguishable across the alternatives, and the fixture bullet only covers guard mismatch, not equal-valued fields. Personal learning on "known-opposite input" is the nearest sibling but lives outside the deployed corpus.

**Placement:** guides/verification-discipline.md §When a green means nothing — add as a sixth shape ("The indistinguishable expectation")

**Why (strength):** Two independent sessions (i18n render legs; approval-TTL split with mutation-verified swap detection) hit the same shape in unrelated domains, each requiring a rework of already-written checks (rollback in one). Materiality is moderate — a false green over a quality-critical assertion — but no rare-high-cost event. The general form is clear and the baseline's existing vacuous-green list is the natural home, so extend rather than add a new rule; not global-worthy since it needs recognition of the situation.


### Localize pipeline defects stage-by-stage: in a multi-stage (especially LLM/nondeterministic) pipeline, an end-to-end output diff cannot attribute an effect or a regression to a stage; persist per-stage artifacts, partition stages by whether they mutate the content in question, and find the first stage where the intended effect disappears or the corruption appears.

`partial` · strength 3 · 2 sessions `claude:a34aa7d2 claude:789cf3b0` · ①hi-tok ⑤rare-hi-cost ⑥quality

**Rule:** When attributing an intervention's effect or hunting a content regression in a multi-stage pipeline whose stages are nondeterministic (LLM calls, repair passes, reviewers), do not judge from a final-output diff against a baseline — it conflates the change with run-to-run variance and points at the wrong stage. Persist every intermediate stage's output, tabulate per stage what it creates, what it may edit, and what it only guards, restrict the suspect set to the stages that edit the content in question, and locate the first stage where the intended effect disappears or the defect appears; that stage is the one to fix, and the fix is a structural recheck after its edit rather than another prompt-level instruction that already failed. Applies to any pipeline with two or more content-mutating stages; a single-stage or deterministic pipeline needs only the existing A/B arm check.

**vs baseline:** verification-discipline.md §Verification Menus "A/B or on/off measurements" bullet (partially covers: checks that arms differ, not where in a pipeline the effect is lost); coding-staged-workflow.md "Fix the cause at its authority, not the symptom where it shows" (partially covers: go upstream, but gives no method to find which stage); global §LLM And Capability Boundary "enforce through the capability surface instead of repeating prohibitions" (covers the fix shape only). The stage-partition/first-divergence localization method is absent.

**Placement:** guides/verification-discipline.md §Verification Menus — new bullet directly after "A/B or on/off measurements"

**Why (strength):** Two independent sessions (different session ids, different pipelines: a glossary-constraint attribution and a semantic-loss hunt) converged on the same diagnostic — per-stage localization — and in both the end-to-end view had already misled a paid or blocking investigation (rare_high_cost, high_token). Both from the same provider family, and the recurrence count is only two, so not 4–5; but the baseline's nearest rules only say "go upstream" without a method, and the method generalizes to any multi-stage nondeterministic pipeline, so it earns a guide bullet rather than global placement.


### A shared remote moves between read and write; re-locate/diff before writing

`partial` · strength 3 · 2 sessions `claude:80385459 claude:c717c714` · ④recur-err ⑤rare-hi-cost ⑥quality

**Rule:** A handle taken from a shared or remote store — a row index in a spreadsheet other people or auto-sort can reorder, a downloaded copy of a hosted file, a fetched version of a remote object or config — is valid only at the instant it was read. Immediately before every write, re-establish the target from the live source: re-locate a row by its key column (never by a remembered position) and assert the key matches after the write; compare the remote's modification time or version against the copy you edited, and if it moved, re-download, diff what changed, reapply your edit on the fresh copy, and verify by re-reading. Never overwrite from a stale handle. This is a pre-write guard; the existing concurrent-writer check remains the post-hoc diagnosis when an edit appears lost. Local, single-writer files you own need none of this.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services "Shared live config has concurrent writers" — partial: it covers diagnosing a lost edit after the fact (mtime observation), not a pre-write re-locate/diff guard; §Git operations "Dirty-worktree pulls" (fetch-then-compare) covers the same shape only for git; global "Ambient state drifts — pin it" covers environment state, not remote data. Key-based row addressing is absent (0 hits).

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet "A remote handle is valid only when read" placed directly before "Shared live config has concurrent writers", which it should reference as the post-hoc counterpart

**Why (strength):** Two independent sessions (different session ids, different surfaces: an auto-sorting Google Sheet and a Drive-hosted xlsx round-trip) hit the same invariant — a read-time handle silently invalidated before the write — and both cost real rework (a mis-addressed row that became a runbook trap; a near-overwrite of another person's change caught only at upload). The general form (stale handle → re-locate/diff before write) is clearly not one-off, but recurrence is only two sessions and the baseline already has the post-hoc half, so this is an extension rather than a new rule; not global-worthy since its failure mode is recognition (knowing the store is shared), which belongs behind the tooling-gotchas pointer.


### Identity of what actually ran must be read back from the resolved target

`partial` · strength 3 · 2 sessions `claude:fe3f8eb4 claude:56bd378f` · ②rollback ④recur-err ⑥quality

**Rule:** Whenever a run's identity (provider, model, route, version, environment) is recorded into a result or asserted by a guard, derive it from the target as resolved at execution time and compare it to what was requested — never write it from a literal in the runner, and never let the guard pass on "some target was reached". Fallback and salvage paths satisfy existence checks by design, so an existence check is exactly the check they defeat; a label that can disagree with what ran turns every comparison built on it into a mislabeled dataset. Applies to any runner, benchmark, or dispatcher that can resolve to more than one backend; a single-backend tool with no fallback path needs only the resolved-read, not the equality assertion.

**vs baseline:** Partially covers: cli-multi-model-workflow.md §Cross-Verification Economy ("Kind labels do not guarantee distinct backends... confirm each verifier's actual backing model from live process or usage evidence") and the receipt-on-exact-seat rule cover the review-diversity case only; tooling-gotchas.md §Ambient state drifts ("Command resolution... confirm the resolved target") covers shell binaries only; verification-discipline.md §When a green means nothing ("The permissive fallback in the checker", `a || b`) covers the fail-loud shape but not the requested-vs-reached identity assertion. Omits: identity labels in result records must come from resolved runtime config, and guards against silent re-resolution must assert identity equality rather than reachability.

**Placement:** guides/verification-discipline.md §When a green means nothing — new bullet "The guard that checks reachability, not identity", adjacent to "The permissive fallback in the checker"

**Why (strength):** Two independent sessions (different session ids, both claude) hit the same failure shape: a benchmark runner hardcoded the model label so every row's provenance misidentified the model that ran (rollback of a dataset's basis), and a fail-closed guard passed when a request for one provider silently resolved to a fallback with no model pin (found by two cross-family lenses, i.e. missed inline). Materiality is high — mislabeled provenance corrupts every downstream comparison and a fallback that passes the guard is the exact collapse it exists to block — but recurrence is only two sessions and the neighbouring baseline rules already carry the review-diversity and shell-resolution instances, so this is an extension of an existing bullet family rather than a new global rule.


### Prove deny guards fire with planted violations and pass on the clean tree

`partial` · strength 3 · 2 sessions `claude:e9468069 claude:105319ce` · ④recur-err ⑥quality ②rollback

**Rule:** When you narrow or widen a lexical deny guard (a grep/regex policy check over source or docs), a passing suite is not proof the edited rule still fires: sibling rules may have caught the planted cases, and a bare-identifier pattern may self-match its own prohibition comment or miss the same capability reached through a sibling API or an aliased import. Falsify the rule on its own, in both directions — with sibling rules disabled, the clean tree (including comments that name the forbidden call) must pass, and planted violations in every shape that grants the capability (direct, sibling API, alias/receiver form) must each go red — then plant one violation into the real guarded path and watch the real check fail, not only the unit test of the pattern. Match the invocation shape rather than the bare word, and scope the scan to the tree future files will land in. Applies to any hand-written pattern that enforces a prohibition; a semantic or judgment check is not a lexical guard and is out of scope.

**vs baseline:** guides/verification-discipline.md §When a green means nothing and §Deriving the case space — covers negative controls, planting a violation to prove a control fires (and the restore trap), revert-and-watch-fail, and the empty-subject vacuous pass. Omits: isolating the edited rule from sibling rules that mask it, the clean-tree-must-pass direction (self-match on a prohibition comment), sibling-API/alias bypass coverage, and planting into the real guarded path after unit-testing the pattern.

**Placement:** guides/verification-discipline.md §When a green means nothing (new bullet: "The rule masked by its siblings", following "The control that went quiet")

**Why (strength):** Two independent sessions (different session ids, different repos/languages: a package-hygiene regex and a Go env-read guard) hit the same failure shape — a modified deny pattern whose continued firing was unproven because sibling rules or a unit test stood in for the real check, and whose clean-tree direction failed on a comment. Materiality is moderate-high: a deny guard that silently stops firing is a false-PASS about the gate itself, the class the corpus already flags as most expensive, and each session took multiple rework iterations (rollback-class). The baseline genuinely covers the generic "plant and watch it fail" discipline, so this is an extension of an existing section, not a new rule; hence partial and 3, not 4-5.


### Never hand-edit a derived artifact; fix the source/generator and regenerate

`partial` · strength 3 · 2 sessions `claude:08503f68 claude:87fb0d9c` · ②rollback ⑥quality

**Rule:** Before editing any file that may be derived — a copy in a config home or installed package, a generated mirror, or the output of a transformation tool you built — first look for what produces it (a deploy manifest, a generator, a parity gate, the tool's own run) and treat that as the only place to make the change. If the derived output is wrong or off-convention, revert it, fix the source or the generator, and regenerate every projection in the same change; a hand fix to the output is overwritten at the next deploy or run, leaves the generator unvalidated for the larger run it exists for, and lets the defect propagate into every later application. Applies to anything with a producer; a file with no generator or deploy path is simply source and is edited directly.

**vs baseline:** guides/concept-economy.md §Derived Values Stay Derived — states the design-side principle ("what is not correct is treating the projection as the place to fix a wrong value") and the global core rule "one value has one owner, every other surface is generated from it"; claude-prompting.md Environment Binding adds one narrow instance ("install overwrites deployed bindings, so edit the repo copy"). Partial: neither gives the operational trap — detect that a file is a projection BEFORE editing, and when a tool's output is wrong fix the tool and re-run instead of patching output.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Two independent sessions (a deployed config-home copy edited and lost at commit time; a refactor tool's output hand-patched and the defect propagating into later extractions), both costing a rollback and redo. The authority principle exists in the baseline but at design altitude; both failures happened because the agent did not check for a producer before editing, which is a concrete decidable check absent from the corpus. Materiality is moderate (rework, silent divergence), not rare-high-cost.


### Freeze the input before a before/after comparison

`partial` · strength 3 · 2 sessions `claude:13d39d5f claude:5df5dc5c` · ②rollback ⑤rare-hi-cost ③re-explore

**Rule:** Before any before/after or old-vs-new comparison of a tool, stage, or configuration, pin the input to an immutable copy (a snapshot file, a checkpointed or versioned artifact) and run both arms against that same copy — a live artifact (an in-progress transcript, a growing log, an upstream stage regenerated between runs) drifts between the two runs, so any diff over it, including a matching one, is evidence of nothing; when the arms are metered, restore the exact upstream inputs the baseline consumed and re-run only the changed stage so the comparison isolates it. This is about input identity between arms; unit/denominator/population equivalence is a separate, already-stated basis rule.

**vs baseline:** global CLAUDE.md §Verification Discipline "fix a common basis — units, denominators, population, measurement surface" (partially covers: basis equivalence, not that the input artifact itself may move between runs); verification-discipline.md §Verification Menus "A/B or on/off measurements" bullet (covers arm-treatment difference, not input drift); §Proportion the depth "replay the changed deterministic logic over persisted real artifacts" (adjacent — persisted artifacts, but stated for cost, not comparison validity). Omits input freezing as such.

**Placement:** guides/verification-discipline.md §Verification Menus — extend the "A/B or on/off measurements" bullet

**Why (strength):** Two independent sessions: one had to redo an invalidated regression diff of a cost tool because its transcript input grew between runs (rollback); the other burned metered LLM spend and many turns re-deriving a comparison whose upstream inputs had to be restored from bucket versioning (rare_high_cost, re_exploration). The general form is clear and small; the baseline's basis rule and A/B-arms rule each sit one step away without stating input immutability. Member 172's extra clauses (probe the sink before spend, timestamp zone normalization, record the run command) are separate lessons and are not carried by this cluster's principle.


### Before declaring work absent, recover its artifact from disk

`partial` · strength 3 · 2 sessions `claude:b5b22ba6 claude:bff266bb` · ②rollback ⑤rare-hi-cost ⑥quality

**Rule:** When a required output has not arrived through its expected channel — a delegated worker went idle with no report, or the usual route to an input is unavailable — treat that as a channel failure, not evidence the work did not happen. Before reporting the step as blocked or the review/sweep as absent, and before re-dispatching, look for the finished artifact where the mechanism persists it (the worker's own transcript file, the producing service's logs, its output/download location) and verify the recovered artifact against that record (timestamp, id, count) before using it. Report "no result ran" only when the persisted record shows no completed result; never let a missing message be reported as missing work, and keep any personal data in a recovered artifact out of the repository.

**vs baseline:** guides/cli-multi-model-workflow.md §Delegation Mechanics ("Idle/progress notifications are hypotheses; verify repo artifacts before re-dispatch ... idle-without-report is not done — request the report explicitly") and §Halt And Resume ("Resume-first from artifacts") — partially covers: says to verify artifacts and request the report, but does not say the completed output is recoverable from the seat's persisted transcript / the producer's logs, nor that a dropped report must not be reported as "no work ran".

**Placement:** guides/cli-multi-model-workflow.md §Delegation Mechanics And Teammate Persistence — extend the idle-notification bullet with the disk-recovery path and the "missing message is not missing work" boundary

**Why (strength):** Two independent sessions (claude:b5b22ba6, claude:bff266bb) with the same shape from different channels (browser export vs subagent report). Materiality is real: one session was about to discard four blocking review findings and had already told the user "no independent review ran" — a false report that required an explicit correction (rollback + rare-high-cost); the other unblocked an end-to-end round-trip without the missing channel. The baseline already has the adjacent rule (idle is not done; verify artifacts), so this is an extension, not a new bullet — hence partial and strength 3 rather than higher.


### Attribute a cause by a controlled with/without contrast: when the error channel is silent or a remedy is about to be chosen, hold every variable but the candidate cause constant and read a countable difference instead of trusting the absence of a report or a plausible first hypothesis.

`partial` · strength 3 · 2 sessions `claude:d41d6c45 claude:12070ef6` · ②rollback ⑤rare-hi-cost ①hi-tok

**Rule:** Before attributing a fault to a cause — and always before proposing a remedy that costs an admin change, a perimeter/allowlist edit, or a policy loosening — establish the cause by a controlled contrast: two observations that hold everything constant (same principal, same path, same page, same input) and differ only in the candidate variable (header present vs absent, feature on vs off, token A vs token B), and read a countable difference (element dimensions, applied-stylesheet count, request count, status-code family) rather than a narrative. A missing error report is not exoneration — reporting channels can be suppressed, unobserved, or not wired to the mechanism at fault — so "no violations logged" only rules a cause out when the contrast also shows no difference. If the evidence already contains such a contrast, read it before adding a remedy; if it does not, construct the cheapest one. Once the discriminator is identified, pin it with a check that fails if the same condition is reintroduced. This applies to diagnosis of observed behavior; it does not replace reading the enforcement point's own logs where those exist, and it is not needed when the mechanism emits authoritative evidence that names the cause directly.

**vs baseline:** Partial. Global §Tooling and Operational Safety ("treat a coarse runtime signal as a hypothesis, confirm against the authoritative low-level evidence the mechanism emits") covers reading the mechanism's own evidence but assumes such evidence exists; verification-discipline §Verification Menus (A/B arms must actually receive different treatment) and §Deriving the case space ("prefer a negative or contrast control") cover contrasts as test design, not as a diagnostic move for attributing a live fault; tooling-gotchas §Config ("Perimeter controls need the enforcement point's own logs") covers one perimeter case. None states that an absent error report does not exonerate, nor the single-variable contrast with a countable metric as the cause-attribution step before choosing a remedy class.

**Placement:** guides/verification-discipline.md §When a green means nothing

**Why (strength):** Two independent sessions (a CSP rendering fault with a clean console; an API gateway block misattributed to egress IP), both carrying ②rollback — a wrong first diagnosis was asserted and had to be withdrawn — and one ⑤rare-high-cost (a proposed admin/allowlist change that would not have fixed anything). The move generalizes cleanly beyond both domains (single-variable contrast + countable metric + "silence is not exoneration"), but recurrence is only two sessions and the adjacent baseline rules already cover much of the surrounding discipline, so this is an extension rather than a new rule.


### Log silence is not non-use; check the field that attributes the subject before declaring a resource dead

`partial` · strength 3 · 1 session `claude:bc05a404` · ②rollback ⑤rare-hi-cost ⑥quality

**Rule:** When deciding that an identity, key, flag, endpoint, or other resource is unused, treat absence of log or telemetry activity as non-evidence until two things are shown: that the queried field is the one that records the subject (delegated or impersonated actions are attributed to the caller, with the target appearing in a different field, so a query on the wrong field returns a clean silence), and that no live binding, attachment, or signed config still references it (a reference proves use without emitting traffic). Only positive activity counts as evidence of use, and only a demonstrated "the log would have recorded this use" counts as evidence of non-use. Applies to any removal or deprecation justified by inactivity; it does not apply where usage is provably counted by a consumer-side instrument you have positive-controlled.

**vs baseline:** verification-discipline.md §"When a green means nothing" — partially covers: "The empty subject" and "The suspiciously fast or empty run" state that a clean result over nothing is vacuous, and global §Tooling and Operational Safety says a coarse runtime signal is a hypothesis. Neither names inactivity-as-evidence in a usage/inventory audit, the attribution-field trap (delegated actions logged under the caller), or references that prove use without traffic.

**Placement:** guides/verification-discipline.md §When a green means nothing — add a sixth shape, "The silent log", after "The control that went quiet"

**Why (strength):** One independent session (claude:bc05a404), so recurrence is thin, but materiality is high: the false negative would have justified deleting a load-bearing identity (irreversible, rollback-class), and the mechanism — the log attributing the action to a different field than the one queried, plus references that prove use without traffic — is a general false-pass instrument shape that the baseline's existing "green means nothing" list does not enumerate. It fits that list as an extension rather than a new rule; not global, since the failure mode is recognition, which is exactly what the section pointer exists for.


### Verify a load-bearing external fact by element and by the source's own later updates before it enters prose

`partial` · strength 3 · 1 session `claude:3ce07bf6` · ②rollback ⑤rare-hi-cost

**Rule:** Research, summaries, or fact digests: before a fact from a digest or research subagent becomes load-bearing in a document, verify it against the primary source decomposed into its elements — actor, action, scope, number, date — and check whether the publisher has since corrected, widened, or retracted it; a compact digest silently merges actors and freezes a figure the source has already revised. Applies to facts that would change the document's conclusion, not to incidental color.

**vs baseline:** Partial: global Decision Framing "treat ... reviewer findings and your own earlier conclusions as hypotheses; re-derive each load-bearing claim from real code or data" (code/data only); gpt-prompting "Research and grounded work: cite only retrieved sources, label inference separately" (citation discipline, not element-level or post-publication re-verification); cli-multi-model "idle/progress notifications are hypotheses" (liveness, not content). verification-discipline.md Verification Menus has no research/prose entry.

**Placement:** guides/verification-discipline.md §Verification Menus (new "Research or grounded prose" bullet)

**Why (strength):** One independent session, but high materiality: two of six digests would have inverted the article's claims (rollback + rare-high-cost), and the failure mode (actor merge, frozen revised statistic) is general to any digest-to-prose flow. The general form fits exactly the domain-menu shape the guide already uses, which the menu currently lacks for research/prose.


### A clean automatic merge can place a feature in the wrong semantic slot

`partial` · strength 3 · 1 session `claude:74aa7f5a` · ⑤rare-hi-cost ⑥quality

**Rule:** When a merge, rebase, or cherry-pick lands your change onto a base that restructured the surrounding code (regrouped sections, split modules, introduced per-variant tabs or containers, renamed groupings), a conflict-free merge with green build and tests is evidence about text, not about placement. Before calling the merge verified, locate each merged addition in the new structure and confirm its scope still matches its container's scope — a global setting or behavior must not sit inside a variant-specific container, and no duplicate or orphaned copy remains. Applies only when the base side moved structure; a merge onto an unchanged layout needs the ordinary green-state check.

**vs baseline:** guides/coding-staged-workflow.md §Default Frame (stage 6 Merge verify: "freshly fetched merged state green") and guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees ("re-verify after each merge") — partially covers: both demand a green re-verification after merge, neither states that textual merge success plus green tests fails to establish semantic/structural placement after an upstream restructuring, nor prescribes the placement check.

**Placement:** guides/coding-staged-workflow.md §Default Frame — a bullet beneath the stage table extending stage 6 Merge verify

**Why (strength):** One independent session (claude:74aa7f5a), so no recurrence; but materiality is high — a real user-facing defect (global toggle placed inside a provider-specific tab, sibling tab falsely claiming no features) survived a trivial-conflict merge, a passing build, and 172 green tests, and was found only by manual placement inspection. The failure class (structural refactor on the base side + automatic textual merge) is general across any codebase and is invisible to every deterministic gate the baseline already prescribes, so it is a genuine gap in the merge-verify stage rather than a repo-specific anecdote. Strength capped at 3 for single-session evidence.


### A per-file non-empty guard cannot see code that left the scanned file list; pin a total-count floor

`partial` · strength 3 · 1 session `claude:3364ce2a` · ④recur-err ⑤rare-hi-cost

**Rule:** The enumerated subject that quietly shrinks. A gate scanning an explicit list of files or surfaces can only see "listed but empty"; a subject that migrates to an unlisted surface leaves the scanned population smaller yet still non-empty, so the empty-subject guard never fires and the gate stays green while its coverage erodes. Whenever code or subjects move out of a scanned surface (extraction, split, rename), retarget the gate to the new surface in the same change, and pin a lower-bound floor on the total measured count so any decrease fails loudly; prove the floor with a negative control that moves one subject out of the list. Prefer traversal of a directory or the artifact that defines the population over a hand-maintained list where the gate allows it. A floor is a ratchet against silent loss, not a target — raise it when the population legitimately grows, and never lower it to make a run pass.

**vs baseline:** guides/verification-discipline.md §When a green means nothing — "The empty subject" (cardinality > 0 before the claim) and "The control that went quiet" (control indexing a list that empties) cover the zero case; global Verification Discipline "assert the subject set is non-empty" restates it. Neither covers a scanned population that shrinks but stays non-empty because subjects moved to an unscanned surface. Partially covered.

**Placement:** guides/verification-discipline.md §When a green means nothing — add a sixth shape after "The control that went quiet", and amend the closing "discipline that covers all five" sentence accordingly

**Why (strength):** One independent session, but the same erosion recurred twice within it (16 lost in the first extraction, then 28→24 in the second) under a gate that returned rc=0 both times — a false-green on a security-relevant count (guarded catch blocks) is high materiality. The general form is clear and distinct from the existing empty-subject rule: non-empty-but-shrunk is a different failure shape with a different fix (count floor + retargeting), so it extends rather than repeats. Single-session recurrence caps strength at 3.


### Key cross-instance records on the invariant, and seed test preconditions from the independent authority

`partial` · strength 3 · 1 session `claude:fa7e7e5f` · ②rollback ⑥quality

**Rule:** A record meant to hold across many instances — an approval, qualification, registration, cache entry — must be keyed on the invariant it is about (a code-derived template or contract digest), never on a per-instance filled value, or the live consumer can never present a matching key and the record becomes a permanent veto. The test-side twin of this defect is the circular seed: a test that seeds such a record with the value the code under test itself computes proves only self-agreement and stays green through the mismatch. Seed preconditions from the independent authority the live path will actually present (the contract, the template, the registry), and treat a test helper that imports the code-under-test's own derivation to build its precondition as a green that means nothing. Boundary: this is about identity keys and seeded preconditions; it does not forbid computing expected outputs from the code under test in golden or snapshot tests where the goal is regression detection rather than correctness.

**vs baseline:** guides/verification-discipline.md §When a green means nothing — lists five shapes (empty subject, fixture that misses the guard, permissive fallback, fast/empty run, quiet control) but omits the circular-seed shape; guides/mock-realization-boundary.md covers fixture ownership of semantics but not seeding preconditions from independent authority; the invariant-vs-instance keying rule is absent everywhere. Partial.

**Placement:** guides/verification-discipline.md §When a green means nothing (new bullet "The circular seed"); the keying-on-invariant half as one sentence in the same bullet's lead, since the test trap is how it hides

**Why (strength):** One independent session (claude:fa7e7e5f), so recurrence is thin, but materiality is high: the defect was a permanent live veto invisible to a fully green unit suite and surfaced only by an external reviewer, which is exactly the "green means nothing" class the baseline already enumerates. The general form (test precondition derived from the code under test) is clearly not a one-off and slots cleanly into an existing list, so it is partial rather than novel and worth adding at guide altitude, not global.


### Replace a synthetic benchmark with an observation track when realism is the expensive part

`partial` · strength 3 · 1 session `claude:a010347c` · ①hi-tok ⑥quality

**Rule:** When a benchmark's dominant cost or its blocking defect is authoring realistic inputs, stop authoring and switch to an observation track: tag qualifying cases as they occur in real usage, and at capture time preserve the uncut original input together with the exact target/profile it ran against, so each case can be re-executed later even after the target changes or vanishes. Check first whether existing run records already hold those raw materials — collection code added to a live path is a change the observation track exists to avoid. Accept the two limits knowingly and state them in the plan: an observation track gives no controlled comparison, and its validation lags usage. This does not replace a benchmark whose inputs are cheap to construct or whose purpose is a controlled A/B.

**vs baseline:** guides/verification-discipline.md §Deriving the case space — partially covers: "Enumerate the space from the artifact that defines it" and "Split by cost, not by space" (cheap stand-in on every commit, real path on demand, same enumeration), plus global §Verification Discipline's non-representative-data rule and the pipeline note that dropping captured source fields needs explicit confirmation. None of these say to replace synthetic construction with tagging real usage when realism is the cost, nor to preserve the uncut original and target at capture for re-execution.

**Placement:** guides/verification-discipline.md §Deriving the case space

**Why (strength):** One independent session, so recurrence is thin, but materiality is real: two adversarial review rounds returned MATERIAL-BLOCKING on the synthetic design (7 then 5 confirmed defects) and the loopback rule stopped work pending spend, whereas the observation track eliminated both the hardest problem and its cost with zero live-path change. The rule has a general form (trigger = realism is the dominant cost; behavior = observe-and-preserve; boundary = no controlled comparison, lagging validation) and extends the existing case-space section rather than duplicating it. Kept at 3 rather than higher because it is single-session evidence and the criteria are high_token/quality_lever, not rare-high-cost or recurrent error.


### A sandbox probe must disarm every outbound side effect, not only guard its input path

`partial` · strength 3 · 1 session `claude:f36d4344` · ⑤rare-hi-cost ②rollback

**Rule:** When running any stage against production-derived config (a copied live env, a live credential set, a real destination binding) in what is meant to be a sandbox or dry run, enumerate every outbound channel that stage can reach — publish, upload, deliver, notify, external write — and disable or redirect each one before the run, proving each disarm fires the way a path guard is proved; a guard on the input or target path alone leaves egress armed. Fingerprint every external destination before the run and diff it after, so an escaped write is detected by the run rather than discovered by a recipient. Applies to any rehearsal, replay, re-adjudication, or test build that shares config with the live system; it does not apply to runs whose credentials cannot reach a real destination in the first place.

**vs baseline:** guides/verification-discipline.md §Verification Menus, bullet "Branch/version test builds against real data: explicitly separate every state sink the app touches (files, DB, OS-level stores...), confirm the launch path propagates the isolation to child processes, and back up live data before the first run" — partially covers: it names state sinks (persistent stores) but not outbound delivery channels (publish/upload/notify), and it does not say to prove each disarm fires or to fingerprint the external destination. Global CLAUDE.md §Tooling and Operational Safety (scope destructive actions; snapshot before overwrite) and llm-capability-boundary §Security And Side Effects (classify side effects for tool design) are adjacent but address different situations. tooling-gotchas §Config, secrets, and managed services "Smoke limits outlive the smoke test" is the nearest shape (a config carried into a run silently changes what the run does) but the reverse direction.

**Placement:** guides/verification-discipline.md §Verification Menus — extend the "Branch/version test builds against real data" bullet (or add a sibling bullet "Sandbox/replay runs on production-derived config") to cover outbound channels, proven disarms, and destination fingerprinting. Not global: the global destructive-actions bullet is already long, and the rule's trigger (running a stage on copied live config) is recognizable, so a pointer suffices.

**Why (strength):** One independent session (claude:f36d4344), so recurrence is thin, but materiality is high: an irreversible external publish to a real delivery folder despite a verified input-path guard, needing after-the-fact triage via revision history (rare_high_cost + rollback). The general form is clear and the baseline already has the adjacent "state sink" bullet, which shows this failure class recurs in different guises; the specific gap — outbound channels vs persistent stores, and proving the disarm — is genuinely unstated.


### A probe on a copied script that self-locates re-measures the original

`partial` · strength 3 · 2 sessions `claude:836ae508 claude:62097bd1` · ④recur-err ③re-explore

**Rule:** When a probe runs a copy of a script or gate (a planted-violation copy, a scratch copy of a checker), first confirm how the script locates its subject: one that derives its repo root or targets from its own location ($0, BASH_SOURCE, a cd to its own parent) ignores where the copy sits and scans the original tree, so the copy's green or red proves nothing about the mutation. Either pin the subject variable in the copy to the intended target, run the copy inside a fully copied tree, or plant in place with a snapshot-restore. The signature to distrust is a probe whose result is identical to the unmutated run; this applies only to scripts that self-locate — one that takes its subject as an argument is safe to copy.

**vs baseline:** verification-discipline.md §Deriving the case space ("Plant in a copy where the shape allows it") and tooling-gotchas.md §Git operations ("plant in a copy and restore from that") both recommend copy-probing but never warn that a self-locating script makes the copy re-measure the original; §When a green means nothing lists green-with-no-evidence shapes but omits this one; §Ambient state drifts covers pinning paths generally, not this probe trap. Partially covered — the baseline actively prescribes the copy without its failure mode.

**Placement:** guides/verification-discipline.md §When a green means nothing (new bullet "The probe that measured the original", qualifying the "plant in a copy" advice in §Deriving the case space and tooling-gotchas §Git operations)

**Why (strength):** Two independent sessions hit it (the cluster member plus the second session named in its evidence), each costing multiple wasted probe retries and one of them a planted-violation "pass" that measured nothing — a false-green on a gate control, which is materially dangerous. General form is clear and is the exact counter-case to advice the baseline already gives, so it is an extension rather than a new rule; not multi-session enough beyond two, nor high-cost enough, for 4-5.


### An apply cut off before confirmation is unconfirmed and may be partial — enumerate target objects before re-running

`partial` · strength 3 · 1 session `claude:b35039cd` · ⑤rare-hi-cost ⑥quality

**Rule:** When a multi-statement, side-effecting apply (schema migration, bulk provisioning, batch write) loses its confirmation channel before the result was read — auth dropped, session cut, runner exited without verification — treat it as unconfirmed and possibly partial, never as done and never as not-run. Before re-running, enumerate which of its target objects already exist against the real store and plan the rerun from that partial state (skip, drop-and-recreate, or resume from the first missing object), because a naive rerun of a non-idempotent apply fails halfway on "already exists" and leaves a second partial state. When the runner only surfaces exit status, route the observation you need through the channel it does surface — e.g. make a diagnostic step fail deliberately with the object list as its message — rather than trusting a green that carried no data. Boundary: an apply that is provably idempotent or transactional (all-or-nothing) needs only the confirmation, not the enumeration.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services ("A new revision is not live traffic") — partially covers: "success message ≠ effect", but only for deploys, not interrupted confirmation or partial multi-statement state. guides/llm-capability-boundary.md §Persistence, Idempotency, And Retry names "side-effect uncertainty" and "partial persistence failure" as retry classes and says retries are not automatically safe for side effects, but gives no behavior for the interrupted-confirmation case. cli-multi-model-workflow §Unattended Batch Safety says whole-batch reruns require cheap idempotence. The enumerate-before-rerun step and the exit-status-only-runner tactic are absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (new bullet after "A new revision is not live traffic")

**Why (strength):** One independent session (claude:b35039cd), so recurrence is thin, but materiality is high: the failure mode is a production schema migration whose naive rerun produces a second partial state, and the session's evidence shows the assistant explicitly avoided that by checking for partial objects and running a positive control. The rule has a clearly general form (any non-idempotent multi-step apply whose confirmation was interrupted) and a clean boundary (idempotent/transactional applies exempt). Baseline touches the neighbouring ideas (side-effect uncertainty, idempotence for reruns, success-message-is-not-effect) without stating the enumerate-before-rerun behavior, so extend rather than add a new section.


### Pre-declare a validity floor for an evaluation and re-derive size estimates from real serialized output

`partial` · strength 3 · 1 session `claude:e1b285d7` · ①hi-tok ②rollback

**Rule:** Before running an evaluation that yields a verdict (an ablation, benchmark, gate, A/B), declare the minimum sample or admission count below which the run is invalid rather than a result; a run that lands under that floor is reported as "invalid — floor not reached" with its cause, never as FAIL or PASS. When the floor is reached through a budget (characters, tokens, bytes, rows), size the budget from the measured cost of one real serialized element — every field, wrapper, and formatting included — not from the nominal size of its label or key; a design that estimated from the label can be an order of magnitude short and will produce under-floor runs indistinguishable from failures. Applies to any capacity- or sample-bounded evaluation; does not apply to N=1 probes whose purpose is reaching the real path rather than reaching a verdict.

**vs baseline:** guides/verification-discipline.md §When a green means nothing ("The empty subject", "The suspiciously fast or empty run") and global §Verification Discipline denominator/"flag non-representative data (smoke slices)" bullet — partially covers: both address a vacuous or non-representative run, but neither states a pre-declared minimum-sample floor that separates "invalid run" from "failed run", nor the trap of sizing a budget from an element's nominal size instead of its real serialized cost.

**Placement:** guides/verification-discipline.md §When a green means nothing — add a bullet "The under-floor run" (a red under the declared floor is as evidence-free as a vacuous green), with the serialized-cost sizing note attached

**Why (strength):** One session only (claude:e1b285d7), so recurrence is weak; but materiality is real — the misclassification would have recorded a FAIL and forced a rollback of the model switch on a run whose budget structurally could not reach the floor (admit 12 vs floor 30, ~81 vs ~850 chars/element, a 10x sizing error), and the fix re-pinned a design constant. The general form (validity floor precedes verdict; size from real serialized cost) is invariant across evaluation types and is genuinely absent from the guide, whose closest bullets cover empty and crashed runs but not undersized ones. Partial extension, not a new global bullet.


### A perimeter probe needs a sentinel the protected app would answer, so a pass can only come from the perimeter

`partial` · strength 3 · 1 session `claude:f2811e5c` · ⑥quality ⑤rare-hi-cost

**Rule:** When probing that a perimeter control (edge auth, WAF, identity-aware gate, firewall rule) is enforcing, do not use the protected application's own denial as evidence: aim the probe at a target the application would itself answer successfully without credentials (a sentinel route or endpoint), so a denial can only have come from the perimeter. Read a redirect or any response originating from the application as a bypass, not a deny. Keep the sentinel and the probe in the same unit so they cannot drift apart. This complements, not replaces, confirming allow and deny from the enforcement point's own logs.

**vs baseline:** tooling-gotchas.md "Perimeter controls need the enforcement point's own logs" — partially covers: it says how to observe (the enforcement point's logs, not an agent-side fetch) but nothing about probe target design, so a probe whose denial the app would produce anyway still passes with the control off. The general "run the instrument against an input whose answer is known to be the opposite" (personal learnings; verification-discipline.md AI workbench menu, Evidence line) covers the abstract principle but not this perimeter-specific shape (sentinel target; redirect-to-app = bypass).

**Placement:** guides/tooling-gotchas.md §Deploy/infra traps — extend the "Perimeter controls need the enforcement point's own logs" bullet with a sibling clause on probe target design (sentinel the app would answer; redirect = bypass)

**Why (strength):** One independent session (claude:f2811e5c), but with concrete materiality: the sentinel exposed a real false pass (an app redirect read as an edge deny) on a security-perimeter acceptance check, where a false pass is rare-high-cost. The abstract known-opposite rule already exists, so this is an extension of an existing bullet rather than a new rule; the specific failure shape (app's own rejection masquerading as the perimeter's) is general to every edge-auth/WAF/IAP verification and absent from the baseline.


### Census the whole population's current state before paying for a batch run

`partial` · strength 3 · 1 session `claude:cf311b2a` · ⑤rare-hi-cost ⑥quality

**Rule:** Before committing a costed or irreversible batch over a population of items, take a cheap deterministic census of that population's current state — status distribution, version, presence of the artifacts the plan expects — and compare it against the premise the batch rests on; halt and re-diagnose when the distribution contradicts the premise. An N=1 probe validates the path; only the census validates that the population is what the plan assumes. Applies whenever per-item cost or irreversibility makes a wrong premise expensive; a cheap idempotent batch over a few items needs no separate census.

**vs baseline:** guides/verification-discipline.md §Proportion the depth before you spend — "Probe at N=1 with the inputs precondition-checked" covers the single-path probe; global §Problem Solving "Return to understanding if a discovery breaks the user's premise" and §Decision Framing "treat inherited premises as hypotheses" cover the reaction after the fact; §Unattended Batch Safety covers in-flight failure handling. None says to enumerate the population's before-state prior to launch. Partially covered.

**Placement:** guides/verification-discipline.md §Proportion the depth before you spend — new bullet directly after the "Probe at N=1" bullet

**Why (strength):** One independent session (single member), but the materiality is high: a 52-item paid migration was about to launch on an inverted premise (49/52 already blocked), and the population scan alone stopped it — a rare-high-cost lever that no baseline rule triggers before spend. The general form (per-item cost × premise dependence → census first) is clearly domain-neutral and complements rather than duplicates the N=1 bullet. Single-session recurrence caps strength at 3.


### Expected values in tests must not depend on the wall clock or on storage-normalized byte order

`partial` · strength 3 · 1 session `claude:8cd559df` · ④recur-err ⑥quality

**Rule:** An expected value in a test must be invariant to when and where the test runs. Two traps produce a test that is green today and wrong tomorrow, or red on identical data: (1) baking the current date/time into an assertion — match the shape (a pattern) or inject a fixed clock instead; (2) asserting byte-for-byte equality on data that round-trips through a normalizing store or codec (JSON/jsonb columns reorder keys, whitespace or Unicode normalization, float formatting) — compare structurally (order-insensitive deep-equal on the parsed value), because a byte diff there is not a defect. Boundary: this governs how the expected value is written, not what is verified — where byte identity IS the contract (a signed payload, a golden file, a wire literal), the byte comparison stays and the normalizing layer is what must be removed from the path.

**vs baseline:** guides/verification-discipline.md §Keeping E2E honest — partially covers: it says "keep it deterministic with fixed data, resilient selectors, isolated external dependencies, and explicit waits", which addresses input determinism, not the expected-value side; neither the wall-clock-in-assertion trap nor the normalizing-store byte-order trap is named. Global CLAUDE.md §Verification Discipline "fix a common basis... compare on equivalent output" is about cost/quality comparisons, not test assertions.

**Placement:** guides/verification-discipline.md §Keeping E2E honest

**Why (strength):** One independent session (claude:8cd559df), but two distinct corrections within it exhibiting the same failure class (date baked into a filename assertion; jsonb key-order breaking a verbatim round-trip assertion), and both are classic, general test-authoring traps that any real-DB or date-bearing test will reproduce. Materiality is moderate: the date case yields a latent false-pass that breaks later (survives green, per the personal false-pass lesson), the store case yields a false-fail that burns a debugging loop. Existing E2E section covers input determinism only, so an extension is warranted; single-session evidence and no rare-high-cost event keep it below 4.


### Do not re-audit authority the upstream system already granted; guard only the non-human failure modes

`partial` · strength 3 · 1 session `claude:e96a2851` · ②rollback ⑥quality

**Rule:** When an agent or wrapper acts through a credential that the upstream system already authorized, do not rebuild that system's authorization, spend cap, or second-party approval inside the wrapper — the upstream access grant is the authority, and a duplicated gate adds a second authority that can disagree with it. Scope the wrapper's safeguard to the failure modes the upstream cannot see: an automated caller malfunctioning or compromised. Detect those by thresholding changes that are unusual in magnitude against real historical scale (never a guessed number), stage such changes without activating them, and route activation to a human acting inside the upstream system with a notification to the responsible owner. The general rule 'require preview, approval, or downstream authorization for high-impact actions' still holds where no upstream grant exists; this boundary applies only when the actor's authority is already established by the system being driven.

**vs baseline:** Closest: global §Decision Framing 'Do not default to a restrictive lens ... restrict only on concrete, named risk' (partial — says not to over-restrict, not how to split authority between upstream ACL and wrapper), and guides/llm-capability-boundary.md §Security And Side Effects 'Classify side effects ... financial/legal action' + 'Require preview, diff, approval, or downstream authorization for high-impact actions' (partial and in tension — read literally it endorses exactly the duplicated approval gate the session rolled back; it lacks the boundary that an existing upstream grant is the authority and the wrapper guards anomaly, not authorization).

**Placement:** guides/llm-capability-boundary.md §Security And Side Effects — extend the 'Require preview, diff, approval, or downstream authorization for high-impact actions' bullet with the upstream-grant boundary and the anomaly-guard shape (historical-scale threshold, stage-not-activate, human activation upstream, owner notification)

**Why (strength):** One independent session only (claude:e96a2851), so recurrence is thin. Materiality is real: three CRITICAL reviewer findings were rolled back on the user's reframing, and the correction shapes where authority lives in an agent-to-external-system design — the exact question the capability-boundary guide owns. The baseline's side-effect bullet currently points the other way (approval for any high-impact action), which means the corpus would reproduce the same rejected design; that tension makes it worth extending despite single-session evidence. General form is clear (wrapper vs upstream authority), so not too_specific; concrete thresholds and channels in the evidence are stripped from the principle.


### Tightening network exposure is a behavior change for external clients

`partial` · strength 3 · 1 session `claude:53b3e2eb` · ⑤rare-hi-cost

**Rule:** Tightening exposure on an endpoint that external clients call — switching ingress mode, adding an allowlist or VPC-only restriction, requiring auth — is a behavior change for those clients, not a safe hardening: before applying it, enumerate which clients reach the endpoint and by which hostname or URL, and after applying it, verify from a client's vantage point and confirm inbound volume did not drop to zero. A posture change verified only from the enforcement point's own logs can silently sever ingestion for days, because the clients that were cut off produce no error on your side. Boundary: applies to endpoints with callers outside the deploying team's control; an endpoint whose only callers you own and redeploy in the same change needs only the normal deploy verification.

**vs baseline:** Partially covered. Global CLAUDE.md §Coding Guidelines treats only *loosening* a security posture as a decision. guides/tooling-gotchas.md §Config, secrets, and managed services has "Perimeter controls need the enforcement point's own logs" (verify allow/deny from LB/firewall logs) and llm-capability-boundary.md §Security And Side Effects has "Resolve every authorization/allowlist entry against the live runtime key space ... can pass every deploy check while silently denying its whole route class" (a mis-formatted entry) plus "A new revision is not live traffic". None of these states that a *correctly applied* tightening must be checked from the external clients' side and via inbound volume, nor that clients must be enumerated first.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet immediately after "Perimeter controls need the enforcement point's own logs"

**Why (strength):** Single independent session (claude:53b3e2eb), so recurrence is weak, but materiality is high (⑤ rare-high-cost: four days of silently lost inbound events, no alarm, found only by correlating the last event timestamp with the deploy audit log). The form is clearly general — any ingress/allowlist/auth tightening on an externally-called endpoint — and it fills a real asymmetry in the baseline, which guards loosening and enforcement-side verification but not client-side severance. Guide placement, not global: the failure mode is recognition of the situation, which the global's loosening bullet does not trigger on, so it belongs beside the perimeter bullet it extends.


### An LLM-generated artifact is accepted only if it beats a deterministic baseline under a blind judge

`partial` · strength 3 · 1 session `claude:432cfef2` · ⑥quality ②rollback

**Rule:** LLM-produced comprehension artifacts (summaries, semantic maps, digests, generated docs): structural presence — the sidecar exists, counts match, schema validates — is not acceptance. Before shipping or keeping such an artifact, pre-register the questions it is supposed to answer, build a cheap deterministic control from the same inputs (a concatenation or listing of what the artifact was derived from), and have a context-blind judge with no tools answer the questions from each arm alone. Keep the artifact only if it beats the control; a tie or loss means it costs tokens and adds nothing, and the generating step is removed or reworked rather than kept for its presence. This applies to any artifact whose only claimed value is that a downstream reader understands more with it than without it; it does not replace structural or contract checks, which still run first.

**vs baseline:** guides/verification-discipline.md §Verification Menus (rows "A/B or on/off measurements" and "Model-behavior guardrails") plus §Deriving the case space ("make the criterion falsifiable... a negative or contrast control") and global §Verification Discipline ("'it ran' is not 'quality met'"). Partially covers: the baseline demands contrast controls and that A/B arms genuinely differ, but has no row for the acceptance shape of an LLM-produced comprehension artifact — pre-registered questions, a deterministic same-input control arm, a context-blind tool-less judge, and beat-the-baseline as the ship condition.

**Placement:** guides/verification-discipline.md §Verification Menus (new row: "LLM-produced comprehension artifacts")

**Why (strength):** Single independent session (one provider tag), though the evidence records the failure twice within that track — a structurally green artifact that added no comprehension — and the experiment result (gate failed 1/5) is measured rather than asserted. Materiality is real: without this gate a token-costing generation step ships on presence alone, and a reviewer recommended it as the live acceptance gate for the next tier (quality_lever, rollback). Clearly general — any summary/map/digest artifact has the same failure shape — but with only one session's recurrence and no rare-high-cost criterion it does not reach 4–5.


### Derive signals from the concept's authority, never redefine the concept to fit available data

`partial` · strength 3 · 1 session `claude:733491a0` · ②rollback ①hi-tok

**Rule:** When a classification, role, or metric you are operationalizing comes from an external definition (a taxonomy, a spec, a policy document), the definition is the authority and the signal is a projection of it: re-read the source definition before choosing a signal, derive candidate signals from what the concept actually says, and only then check which are observable in the data at hand. If no candidate is observable, report the measurement gap and carry it as an explicit limitation; never replace the concept with the signal the data makes convenient, because a design built on that proxy measures something else while still bearing the concept's name. Applies whenever a concept's meaning is owned outside the artifact being built; it does not apply to concepts the design itself introduces and owns.

**vs baseline:** Global CLAUDE.md §Decision Framing, "Treat user suggestions, inherited premises ... as hypotheses; re-derive each load-bearing claim from real code or data" (partial: covers re-deriving facts, not re-deriving a concept's definition from its source before operationalizing it); §Verification Discipline "fix a common basis before comparing" (adjacent, about comparison bases); guides/concept-economy.md §Derived Values Stay Derived (covers one-authority for values, not for externally defined concepts operationalized into proxies). The proxy-vs-definition drift is not stated anywhere.

**Placement:** guides/concept-economy.md §Derived Values Stay Derived

**Why (strength):** Single independent session (claude:733491a0), so recurrence is weak; materiality is high — a full design plus a two-family adversarial review was built on a role definition ("builder = merges to main") that the source taxonomy did not support, forcing invalidation of the signal definition, a design banner, and a memory correction (rollback + high token cost), and the drift was only caught when the user asked. The form is clearly general (construct-validity drift: proxy becomes definition) and the baseline's closest rules address facts, comparison bases, and value authority but not concept authority, so it extends rather than duplicates.


### If a clean reinstall does not fix it, the defect is identity-bound host state; bisect with a minimal stand-in

`partial` · strength 3 · 1 session `claude:20b950db` · ①hi-tok ⑤rare-hi-cost ⑥quality

**Rule:** When a component fails identically after a clean reinstall of the same version, stop debugging the artifact and its version: the state lives outside it, keyed to the artifact's identity (identifier, signing/publisher identity, registration records) and a reinstall does not clear it. Ask first what changed about the identity (signing, publisher, channel) — that fact reorders the search. Then bisect with a minimal stand-in that shares only the identity: if the stand-in fails and the same stand-in under a fresh identity survives, the cause is identity-bound host state and a renamed identity is an immediate workaround. Treat any experiment whose removed treatment the system silently restores as never having run. Applies to installed/registered components on a host (apps, services, extensions, daemons); does not apply when the reinstall itself was not shown to be clean.

**vs baseline:** guides/tooling-gotchas.md §Ambient state drifts — pin it, bullet "Installed is not running" (adjacent: it covers the forward direction — on-disk artifact updated but old process still running — not the reverse, where the artifact is fresh and host state keyed to its identity persists). guides/verification-discipline.md §Deriving the case space A/B bullet partially covers "arms received different treatment" (the auto-restored removal). The identity-keyed-state diagnosis and minimal-stand-in bisection are absent.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (new bullet directly after "Installed is not running": "Reinstalled is not reset")

**Why (strength):** Single independent session (claude:20b950db) — no recurrence, so not 4–5. Materiality is high: ~20 diagnostic turns, several invalidated experiments, and a live app that was unusable until an identity-renamed copy was produced; a one-line trap would have collapsed the search to one bisection step. The form is general (host state keyed to bundle/signing/registration identity is a common OS pattern, not tied to this app), and the baseline's nearest bullet states the opposite direction only, so this is a genuine extension rather than a restatement.


### Before rewriting an instruction that is not being followed, prove it reached the sessions being measured

`partial` · strength 3 · 1 session `claude:69d760ac` · ①hi-tok ②rollback

**Rule:** When an instruction, rule, or contract is not producing the behavior it asks for, treat non-compliance as a delivery hypothesis before a wording hypothesis. Diagnose in this order: (1) confirm the injection path actually delivered the text to the sessions being measured — wrapper entry conditions, launcher branches, host differences, install path — by checking a concrete receipt in those sessions, not the source file; (2) check whether the rule's trigger depends on the agent first recognizing the situation — a rule whose trigger lives only inside a guide it points to fires only when the situation is already recognized, so carry the trigger on an always-loaded surface or enforce it mechanically; (3) only then measure adoption, and only over sessions after the mechanism landed and shown to have received it. Rewording is the last lever, never the first. Boundary: applies to instruction text and prompt contracts; for code-level flags the existing inert-until-consumed rule already governs.

**vs baseline:** Partially covered: global LLM/Capability Boundary "treat a produced field, flag, signal, or code branch as inert until a downstream consumer reads it" (producer-side, code flags — not instruction text); Tooling "confirm a config/env toggle reached a subprocess via a cheap artifact" (config, not prompt delivery); Verification Discipline "exclude non-representative data" (covers the measurement window only); guides/verification-discipline.md preamble and repo AGENTS.md §8 state the recognition-failure placement rule but only as a placement criterion, not as a diagnostic step. The ordered diagnosis — delivery path, then trigger recognition-dependence, then wording — is absent.

**Placement:** guides/llm-capability-boundary.md §Capability Surface — add a bullet under "Accessible context" (or a short "Instruction delivery" paragraph) stating that instruction text is part of the surface and non-compliance is diagnosed structurally first; the global bullet on inert fields already carries the pointer.

**Why (strength):** One independent session (claude:69d760ac), so recurrence is thin, but materiality is high: the session spent a large measurement effort over the wrong population and would have rewritten wording while the actual cause was a wrapper condition that never delivered the contract (high_token + rollback). The form is clearly general — any deployed instruction corpus faces the same "did it reach the reader" question — and the baseline only covers adjacent cases (code flags, env toggles, measurement windows), so it extends rather than duplicates. Not too_specific once names and paths are removed; not weak given the concrete rollback cost.


### Controls that fail by crashing, and gates that can reach a prompt, read as coverage they lack

`partial` · strength 3 · 1 session `claude:7014c92d` · ④recur-err ⑤rare-hi-cost

**Rule:** A negative control is evidence only when it fails through the assertion it names. A control that fails by an uncaught exception has proven nothing about the rule — a crash and a caught violation share an exit code — and an early crash can pre-empt every control after it so their assertions never run; treat each traceback in a control run as a defect in the control and chase it until the run reports one named failure per planted violation. Separately, any gate or check that runs unattended must be structurally unable to wait on a person: run it with standard input closed or a non-interactive flag so a code path that reaches a prompt fails immediately instead of hanging the suite. Applies to self-tests, negative controls, and gate suites run by hooks or background sweeps; it does not require converting interactive tools themselves, only the invocation the gate uses.

**vs baseline:** claude/guides/verification-discipline.md §When a green means nothing — partially covers: "a harness that crashed early and one that found nothing produce the same exit code" (crash-as-false-pass) and "revert the fix and watch the check fail". It omits the inverse: a control that fails by crashing counts as a false negative control and can pre-empt later controls. tooling-gotchas.md §Own what you spawn mentions an open stdin pipe keeping a parent alive, but nothing says to run gates with stdin closed / non-interactive so a prompt fails instead of hangs.

**Placement:** guides/verification-discipline.md §When a green means nothing (new bullet: "The control that failed by crashing"); stdin-closure trap cross-listed in guides/tooling-gotchas.md §Shell execution traps

**Why (strength):** One independent session (claude:7014c92d) but with two concrete recurrences inside it (three controls crashed instead of asserting, one pre-empted; then a gate froze a background sweep on stdin). Materiality is real: a crashing control reads as a firing control and silently removes coverage, and a hanging gate stalls an unattended commit path. The baseline states the mirror-image trap (crash-as-pass) and the revert discipline, so this is an extension of an existing bullet rather than a new section — hence partial, not novel, and strength capped by single-session recurrence.


### A test of degenerate-input handling must confirm the layer under test actually receives the input degenerate

`partial` · strength 3 · 1 session `claude:306853c0` · ②rollback ④recur-err

**Rule:** When a test targets how code handles an empty, missing, or malformed input, first prove the input arrives at the code under test still in that state: servers, parsers, frameworks, and shells routinely fill, default, or normalize it upstream, so the fallback branch is never traversed and the test is green about nothing. Deliver the degenerate input below the normalizing layer (raw bytes, raw socket, direct call past the framework) or assert the input's state at the boundary of the layer under test before asserting the outcome. Applies to any test whose value is the degenerate branch; ordinary happy-path tests need no such probe.

**vs baseline:** verification-discipline.md §When a green means nothing — "The fixture that misses the guard" (input silently routes into another branch) and tooling-gotchas' A/B rule ("an unconditional upstream step can silently apply the treatment to both arms") cover adjacent shapes; review-request.md's evidence base records a surviving mutation that "proved equivalent — the platform already normalized what the mutated guard checked" but frames it as a harness-reading rule, not as a test-authoring rule. The specific mechanism — an upstream layer repairing the degenerate input before the branch under test sees it, and the remedy of delivering below that layer — is not stated. Partial.

**Placement:** guides/verification-discipline.md §When a green means nothing (new bullet after "The fixture that misses the guard")

**Why (strength):** Single supporting session (one independent source), but the baseline itself already carries a second measured instance of the same mechanism (the equivalent-mutation note) framed differently, so recurrence is two shapes across sessions. Materiality is moderate-high: it produced a vacuous test that passed a mutation-survival check and required a rollback of the test's approach; the failure mode is silent (green with no evidence), which is the class this guide section exists for. Clearly general — applies to HTTP headers, CLI args, env vars, parsers. Not a global bullet: the trigger (writing a degenerate-input test) is recognizable, so a guide pointer suffices.


### `cmd | grep -q` under pipefail turns a match into a failure (SIGPIPE)

`partial` · strength 3 · 1 session `claude:8d164081` · ④recur-err ⑤rare-hi-cost

**Rule:** `grep -q`, `grep -m N`, and `head` are early-exit consumers: on the first hit they close the pipe, and a producer still writing dies with SIGPIPE — so under `set -o pipefail` the pipeline reports a successful match as a failure. The "final stage is the assertion" form (`cmd | grep -q pattern`) is safe only without pipefail; it is not exempt from the SIGPIPE trap. When both the producer's own status and a match assertion matter, capture the producer's output to a variable or file, check that command's status on its own, then run the assertion on the captured text. A producer that exits before or at the first match (short, buffered output) will not show the failure, which is why the trap surfaces only on long-running producers such as test runners or build logs.

**vs baseline:** guides/tooling-gotchas.md §Shell execution traps, "Pipe exit masking" bullet — partially covers: it names pipefail + `head -1` → SIGPIPE 141, but its closing sentence exempts `cmd | grep -q pattern` as the assertion-as-final-stage case without saying that `grep -q` is itself an early-exit consumer, so a reader combining the two recommendations (pipefail + grep -q) walks into the exact failure the session hit.

**Placement:** guides/tooling-gotchas.md §Shell execution traps — amend the "Pipe exit masking" bullet: replace the unqualified `grep -q` exemption with the boundary above (safe without pipefail; under pipefail treat `grep -q`/`-m` like `head` and capture first).

**Why (strength):** One independent session, but the mechanism is deterministic and verifiable (grep -q closes on first match; SIGPIPE to a still-writing producer; pipefail propagates 141), and the materiality was high — without the guard a mutation checker would have reported 8/8 mutants killed vacuously, a false-green in a verification instrument (rare-high-cost). The baseline is not merely silent; its existing exemption actively points at the failing form, so extending it removes a misleading rule rather than adding a new one. Single-session recurrence keeps it below 4.


### Reconcile a review harness's item list against its own totals before disposing findings

`partial` · strength 3 · 1 session `claude:8c9a5b01` · ⑤rare-hi-cost ⑥quality

**Rule:** When a review or verification harness emits both an item list and any summary of its own (a findings count, a verdict tally, a per-item decision log), count the list against every such total before triaging. Zero findings is only the extreme case: any shortfall means items were dropped in aggregation, and the dropped set is not random — an aggregation step tends to lose a whole class (one action kind, one lens, one severity band), so it can hold the most severe items. Recover the missing items from the raw per-item record and triage the union; if no raw record exists, treat the deliverable as incomplete rather than clean. Applies to any multi-stage harness whose output passes through a merge, filter, or projection; a single-pass reviewer with no self-reported total has nothing to reconcile and is judged on participation alone.

**vs baseline:** guides/review-request.md §Read participation before believing a verdict — covers the zero-findings/participation tell and "a crashed harness renders as a perfect score" (partial); guides/verification-discipline.md AI workbench goldens name "a wrong denominator" and "nothing tied the inventory's denominator to the source's own count", and a line says "a coverage count that hides its own truncation reads as more than it is" (partial). None states the concrete step: compare the emitted list to the harness's own totals/decision log and recover the difference when nonzero findings are returned.

**Placement:** guides/review-request.md §Read participation before believing a verdict

**Why (strength):** One independent session (claude:8c9a5b01), but high materiality: 6 of 15 verdicts including two P1s were silently dropped by the merge step and only recovered because the agent counted against the summary. The baseline handles the zero-findings case and the denominator idea abstractly; the nonzero-but-short case is an unstated extension of an existing section, so it earns a sentence there, not a new rule. Single-session recurrence caps strength at 3.


### Audit an MCP tool surface from the live wire, then reconcile it against every declaration layer

`partial` · strength 3 · 1 session `claude:4b1239af` · ③re-explore ⑥quality

**Rule:** When you must know what a tool server (MCP or similar) actually exposes, take the catalogue from the wire in a fresh process — protocol handshake plus list-tools against the live endpoint — not from the host's cached connection, the source tree, or a config file, and stop at the read-only handshake whenever invoking a tool would trigger a consent or login flow. Treat the audit as a reconciliation across every layer that claims to describe the surface (live list, code catalogue, routing table, config allowlist): an entry present in one layer and absent in another is the finding — a dark action, a stale alias, or a protective value (version floor, upgrade-guidance message) that a later config re-publish silently dropped. When diffing consecutive published config revisions, look for removed protective fields, not only added ones. Boundary: this is an inventory/audit procedure; it does not replace the schema-shape rules for designing the tools themselves.

**vs baseline:** Global §Tooling and Operational Safety ("confirm it empirically against the live or installed artifact") and llm-capability-boundary.md ("Resolve every authorization/allowlist entry against the live runtime key space at boot or deploy") partially cover it: both say to check one declaration against the live runtime, but neither frames a tool-surface audit as an N-way reconciliation whose cross-layer diff is the finding, neither gives the fresh-process wire enumeration route when the host connection is gone, and neither names the read-only-handshake vs consent-triggering-call boundary or the removed-protective-field regression on config re-publish.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (new bullet: tool-server surface audit)

**Why (strength):** One session carries the full procedure and the material payoff (52 failed host-side tool calls before the recovery; the reconciliation surfaced a dark tool and a silently lowered client-version floor). The candidate names two sibling sessions in the same batch that re-explored the same tool-surface discovery from scratch, which supports the re_exploration criterion but is not fully independent evidence I could verify here, so recurrence is weak-to-moderate. Materiality is real (a dropped protective floor is a regression no other check caught) and the form generalizes to any tool server with layered declarations, so it earns a guide bullet, not a global line.


### Sign and verify artifacts with tooling at the commit the deployed consumer was built from

`partial` · strength 3 · 1 session `claude:e53c5874` · ⑤rare-hi-cost ②rollback

**Rule:** When a deployed binary will validate an artifact you produce (a signed config, manifest, schema, or migration), produce and locally verify it with the producer tooling checked out at the exact source commit that binary was built from — a local verify run with newer tooling proves only that the newer tooling accepts it, not that the deployed consumer will. Before deploying, confirm the consumer's build commit (from the image/binary provenance, not the current branch) and treat any producer/consumer scheme or version mismatch as a release blocker. This applies whenever validation happens inside a deployed consumer that is older than the working tree; when the consumer is rebuilt from the same commit in the same release, ordinary verification suffices.

**vs baseline:** Partially covers: global CLAUDE.md §Tooling and Operational Safety ("confirm [a capability] empirically against the live or installed artifact ... rather than docs, memory, or a version string") and guides/tooling-gotchas.md §Environment ("Installed is not running") cover the consumer being older than expected and verifying against the installed artifact, and guides/verification-discipline.md §Verification Menus "Release or distribution" covers running the real installer through its default path — but none states the inverse trap: the producer/verifier tooling being NEWER than the deployed consumer, so a local verify with current-tree tooling is not evidence the deployed validator accepts the artifact. That specific direction is absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (new bullet beside "A new revision is not live traffic"); cross-reference from guides/verification-discipline.md §Verification Menus "Release or distribution" bullet

**Why (strength):** One independent session (claude:e53c5874), so recurrence is thin, but materiality is high: a production revision refused at boot, a full pipeline re-run from a worktree at the image's commit, and orphaned secrets and a release id to clean up (rare_high_cost + rollback). The general form is clear and invariant — a deployed validator is pinned to its build commit while the working tree moves — and the baseline only covers the mirror-image case (consumer older than believed, verify against installed artifact), so the lesson genuinely extends an existing rule rather than restating it. Strength capped at 3 for single-session evidence.


### Row-capped or paginated list reads silently undercount aggregates; measure cap exceedance before trusting a sum

`partial` · strength 3 · 1 session `claude:0a7986ef` · ①hi-tok ⑥quality

**Rule:** An aggregate computed over a bounded list read — a row cap, page size, or max-results limit, whether set by you or inherent to the API — is a lower bound until you show no subject exceeds the bound. Before a decision or gate relies on such a sum, measure each subject's cardinality against the cap on real data; where any subject exceeds it, narrow the query server-side to exactly what the rule needs (never client-side after the truncation), then verify the narrowing excludes nothing the rule depends on. A sum that happens to look plausible is not evidence the cap was not hit.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services, bullet "Smoke limits outlive the smoke test" — partially covers: it addresses leftover caps in env/config making a full run succeed on a slice, but not an API's inherent page/row bound truncating a production aggregate, nor the remedy (measure per-subject cardinality vs cap, narrow server-side, verify the narrowing). verification-discipline §Deriving the case space ("a coverage count that hides its own truncation") is about test coverage counts, not data reads. Global Verification Discipline "fix a common basis — denominators" is adjacent but does not name read-path truncation.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — extend the "Smoke limits outlive the smoke test" bullet (or add an adjacent bullet) to cover API-inherent read bounds on aggregates and the measure-then-narrow-server-side remedy

**Why (strength):** One independent session (claude:0a7986ef) supports it, so recurrence is thin, but materiality is high: a spend gate would have silently undercounted budgets (33 of 104 subjects over the cap, up to ~7x the limit) with no error, and the fix was only found by a deliberate probe. The general form is clearly invariant across any paginated/capped API, and the baseline covers only the config-leftover variant of the trap, so it earns a partial extension rather than a new rule or a global bullet.


### Operational tunables: one committed modification point, a real-loader boot test, synthetic fixture values

`partial` · strength 3 · 1 session `claude:0a7986ef` · ①hi-tok ⑥quality

**Rule:** When a value is an operational tunable that operators are expected to change (a cap, threshold, floor, limit), its authority is the committed file the runtime actually loads — if that file is not in the repo, the repo has no authority for it, only copies. Keep the value in exactly that one place, add a test that boots the file through the real loader (not a parser or a schema check), and have contracts and docs state the rule and point at the location rather than restate the number. Keep test vectors and fixtures on deliberately synthetic values that do not track the deployed number, so a retune never requires re-deriving test oracles by hand; if the value is measured from live data, ship the measurement as a repeatable tool so the next retune is one command. Boundary: applies to values meant to be changed in operation, not to constants that are part of the algorithm's definition (those remain code, and their tests may assert them directly).

**vs baseline:** guides/concept-economy.md §Derived Values Stay Derived (and core rule 'one value has one owner, every other surface generated from it') — partially covers: states single ownership and that derived copies become contradictions, and documentation-hygiene says 'give the command that re-derives instead of a typed number'. It omits (1) that the owning location must be the file the runtime actually loads and committed, with a real-loader boot test as the gate, and (2) decoupling test oracles/fixtures from tunables via synthetic values so retunes never touch tests. mock-realization-boundary.md covers mock vs live realization but not fixture-value coupling to deployed numbers.

**Placement:** guides/concept-economy.md §Derived Values Stay Derived (append an 'Operational tunables' paragraph); the recompute-as-tool clause is already implied by documentation-hygiene's re-derive-command rule and need not be duplicated.

**Why (strength):** Single independent session (claude:0a7986ef), so no recurrence. Materiality is real: seven replicated value sites, the true runtime authority absent from the repo entirely, and a prior cap change that cost hand re-derivation of 17 test expectations (high_token). The general form is clear and non-repo-specific — tunables vs. test oracles is a standard coupling failure — and the baseline's existing single-owner rule does not tell an agent that the owner must be the loaded file or that fixtures must not track the tuned value. Extend rather than add a new rule.


### When review confirms a defect that green tests missed, look for tests and fakes that encode the bug

`partial` · strength 3 · 1 session `claude:27e082c3` · ②rollback ⑥quality ④recur-err

**Rule:** When a defect is confirmed in code whose test suite is green, treat the suite as part of the defect rather than as an innocent bystander: before or alongside the source fix, search for (a) a test that asserts the buggy behavior as expected output, (b) fixtures that share state or references the real system keeps distinct, and (c) fakes of storage or concurrency primitives that do not implement the contract they stand in for (compare-and-set, versioning/etags, ordering) and so cannot express the race or interleaving the bug depends on. Rewrite those tests, fixtures, and fakes in the same change as the source fix, because a suite that encodes the bug keeps every later review round from seeing it. Applies to any confirmed defect under a green suite, not to a review finding that has not yet been re-verified against real code.

**vs baseline:** verification-discipline.md §When a green means nothing — partially covers: lists five shapes of a hollow green (empty subject, fixture missing the guard, permissive fallback, fast/empty run, quiet control) and the revert-the-fix discipline, but none is "the test asserts the wrong behavior" or "the fake cannot express the failure it should simulate", and none names a confirmed defect as the trigger to audit the suite. mock-realization-boundary.md §Core Distinction/Appropriate Mock Uses says mocks prove wiring not semantics but says nothing about a fake that skips its primitive's contract. review-defect-criteria.md's "check the assertion, not the name" covers vacuous tests only.

**Placement:** guides/verification-discipline.md §When a green means nothing

**Why (strength):** Single independent session (claude:27e082c3), so recurrence is thin, but materiality is high: four same-family review rounds had declared the module converged while the suite asserted the buggy behavior, and a cross-family round then produced 8 material findings — a rollback of a "converged" verdict with a general mechanism (test/fake encodes the defect) that the baseline's five hollow-green shapes do not name. Extends an existing section as a sixth and seventh shape rather than a new rule, so the concept surface cost is low.


### A self-authored wait loop needs a deadline and an exit predicate tested against a real completed artifact

`partial` · strength 3 · 1 session `claude:82b2e5bf` · ⑤rare-hi-cost ⑥quality

**Rule:** When you write a wait or poll loop for an asynchronous job, bound it and prove its exit before trusting it: give it a hard deadline or iteration cap derived from the job's expected duration, after which it stops and reports the outcome as undetermined instead of spinning; make it also exit when the job's process or handle is gone; and check its completion predicate once against a real completed artifact — or the producer code that writes it — because the output's shape at completion is frequently not the shape it had while running. This applies to any loop you author that blocks on a file, status field, or process; it does not license aborting a healthy long-running call whose only signal is silence.

**vs baseline:** tooling-gotchas.md §Own what you spawn (subprocess spawn/teardown lifecycle) and cli-multi-model-workflow.md §polling (pin the exact job handle; idle is not done) — partially cover: lifecycle ownership and handle pinning are stated, but neither requires a deadline on a self-authored poll loop nor validation of the exit predicate against a known-complete artifact; the global I/O-wait rule only guards the opposite failure (aborting healthy work).

**Placement:** guides/tooling-gotchas.md §Own what you spawn

**Why (strength):** Single session (one independent source), so recurrence is weak, but materiality is high: 2h26m of wall-clock spent spinning after completion, only discovered when the user asked, and the loop had to be killed by hand — a rare-high-cost failure. The rule is clearly general (any poll loop on a status field/file) and has a concrete mechanism absent from the baseline, so it extends the existing lifecycle bullet rather than duplicating it. Kept at 3 rather than higher because the evidence is one anecdote.


### A merge-dropped brace nests later shell functions legally, so bash -n passes and calls fail at runtime

`partial` · strength 3 · 1 session `claude:1a9f5736` · ⑤rare-hi-cost ④recur-err

**Rule:** Merged or conflict-resolved shell scripts: a passing syntax check proves only that braces balance. A lost closing brace turns every later top-level function into a legal nested definition that stays undefined until its enclosing function runs, so the script parses clean and fails at runtime with "command not found" for a function visibly defined above. After a merge touches a shell script, confirm each expected function is declared at top level (source it and list declared functions, or run the real entry point) before trusting the syntax result; when a function "defined above" is reported not found, suspect this mechanism first. Applies to bash/zsh/sh scripts with function bodies; a brace-balanced file is not evidence of correct nesting.

**vs baseline:** guides/verification-discipline.md §The static floor covers the general point (static checks prove well-formedness, never behavior) but the specific pass-that-means-nothing mechanism is absent; guides/tooling-gotchas.md §Shell execution traps lists pipe masking, passthrough args, reserved names, metacharacters, multi-line pastes — none touches merge-induced brace loss or nested-function swallowing; §Git operations has no merge-content trap. Partial.

**Placement:** guides/tooling-gotchas.md §Shell execution traps

**Why (strength):** Single independent session, so recurrence is thin, but materiality is high (rare_high_cost): a clean merge with a green syntax check broke every install scenario (8/27 -> 27/27 after one brace), and the design doc had misattributed the failure to one scenario, so the trap cost diagnosis time and would recur on any merge of a function-heavy shell script. The mechanism is general (bash nested function semantics) and has a concrete detectable trigger and a cheap check, fitting the tooling-gotchas trap format; it does not merit global placement.


### A check's authority source must exist in every environment the check runs in

`partial` · strength 3 · 1 session `claude:6de415d0` · ②rollback ⑥quality

**Rule:** Before choosing what a gate or check treats as its source of truth, enumerate every runtime it will execute in (developer shell, commit hook, container, CI, packaged install) and confirm that source is present in each; where it is absent the check is vacuous there and reports green about nothing. Prefer an authority materialized into every runtime (tracked files, a shipped manifest) over one only the developer checkout carries (the VCS index, untracked scratch dirs), and where a runtime cannot carry it, make the check fail loud or declare that leg skipped rather than pass. This is design-time; the existing empty-subject and suspiciously-empty-run rules are its detection-time counterpart.

**vs baseline:** guides/verification-discipline.md §When a green means nothing ("The empty subject", "The suspiciously fast or empty run") — partially covers: it tells you to detect a vacuous run after the fact and to make the gate refuse to report clean when it judged nothing, but says nothing about enumerating a check's runtimes at design time or about the authority source being missing in one of them. Global §Tooling ("Ambient state drifts silently; pin it") is adjacent but about ambient drift, not about an authority that structurally does not exist in a runtime.

**Placement:** guides/verification-discipline.md §When a green means nothing — add a sixth shape, "The authority missing in one runtime", before the closing revert-and-watch paragraph

**Why (strength):** One independent session (claude:6de415d0), so recurrence is thin, but materiality is real: a post-review prescription was withdrawn and redesigned once the CI container (no .git) was enumerated — a rollback of design work, and a class of defect (green gate over a missing authority) that every other rule in the section only catches after the fact. The general form is clear and cheap to state as one more bullet in the existing list, so it extends rather than dilutes.


### A probe's credential revoke hits the whole grant, not its own token; never revoke against a shared client id

`partial` · strength 3 · 1 session `claude:0a953fe5` · ⑤rare-hi-cost ②rollback

**Rule:** A credential revoke is grant-wide, not token-wide: revoking anything issued under a client id or grant that the user's live sessions share invalidates those sessions too, and the failure surfaces later, elsewhere, with no re-auth prompt. A probe or test may clean up only what it alone owns — use minimum scopes and a dedicated client id or test account where one exists, and let a probe token expire rather than revoking it. When a revoke on a shared grant is unavoidable, state the blast radius (which sessions die and how they recover) and time it with the user. Applies to any shared-authority teardown (OAuth grants, API keys, service-account tokens); token-scoped revokes on a credential only the probe holds need no gate.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety, destructive-actions bullet ("gate irreversible identity-tied actions (revoke, delete, grant, consent) on a live identity check") — partially covers: it gates the wrong-identity case, not the blast radius of a correct-identity revoke on a shared grant; "scope destructive actions to targets you own" names kill/rm/git only. guides/tooling-gotchas.md "Config, secrets, and managed services" has the nearest concrete trap (lost --scopes → wrong-scope credential) but nothing on revoke scope.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Single session (one independent source), but high materiality: a self-cleaning probe silently broke the user's live tool sessions 90 minutes later and required cache eviction plus re-consent to recover (rare_high_cost + rollback). The general form is real and not repo-specific — "own only what you tear down" for shared authority — and the existing global bullet's identity-check gate does not catch it, since the probe acted on the correct identity. Not global-worthy on one session; it belongs as a named trap in the gotchas guide next to the existing auth-flow trap, which the global bullet already points to.


### An empty read from a configured data source is a key-binding mismatch hypothesis before a 'no data' fact

`partial` · strength 3 · 1 session `claude:3be4ddbf` · ②rollback ⑥quality

**Rule:** When a consumer reports a configured data source as empty or sparse (zero rows, missing field, no tab), diff the consumer's expected keys — column headers, field names, tab or table names — against the source's actual keys before planning to populate anything: a name mismatch produces exactly the same zero as absent data, and it turns a content-creation task into a wiring fix. Once one mismatch is found, check the whole sibling class (every tab, locale, or field bound by the same convention) rather than the one that surfaced. This applies to declared bindings between a reader and a store; it does not apply when the source has been independently confirmed empty by a read that bypasses the consumer's key.

**vs baseline:** claude/guides/tooling-gotchas.md §Tool output is a rendering, not the bytes (core rule "treat surprising empty output as a tool artifact hypothesis before a world fact") — partially covers: it names rendering-level causes (grep binary heuristic, NUL, stale caches) but not the data-binding cause (consumer key vs source header). Global §Decision Framing ("treat inherited premises as hypotheses; re-derive from real data") covers the attitude, not the specific check.

**Placement:** guides/tooling-gotchas.md §Tool output is a rendering, not the bytes — add a bullet "Empty read from a bound source: diff keys before populating"

**Why (strength):** One independent session (single member), so no recurrence evidence; but the failure is a common, general class (schema/key drift silently reading as empty), it flipped the task's premise (a data-fill decision became a rename across 8 tabs) which is high-materiality relative to the cost of the check, and the baseline's existing empty-output rule stops at tool rendering. Extension rather than new rule keeps concept surface flat.


### Local OAuth loopback: keep the issued listener alive and accept the code only from the request carrying it

`partial` · strength 3 · 1 session `claude:b033d806` · ④recur-err ⑤rare-hi-cost

**Rule:** A local-callback auth flow (loopback OAuth, device/consent links) hands a human a URL bound to a listener you own: once issued, that listener is a commitment — never restart, re-port, or replace it while the human may still act on the URL; keep it alive until the callback lands or you explicitly tell the user the earlier link expired. The callback handler captures the credential/code write-once from the one request that carries it and ignores every other request (favicon, health probes, reloads) rather than overwriting captured state on each hit. Before asking a human to click, drive the handler with a simulated callback followed by a trailing empty request and assert the poll loop completes — a human-in-the-loop retry is the expensive test, so exhaust the deterministic one first. Boundary: applies to any one-shot human-handoff channel (a link, code, or token you asked a person to use); ordinary subprocess teardown is covered by the lifecycle rule and is not the point here.

**vs baseline:** guides/tooling-gotchas.md §Own what you spawn (subprocess/handle lifecycle: spawn, result, teardown) and global §Tooling and Operational Safety (own the full lifecycle; hand the operator the URL for non-default identity) — partially covers: lifecycle ownership and handing a URL to the user are stated, but nothing says an issued URL freezes the listener it points at, nothing about write-once capture in a callback handler, and nothing about simulating the callback before asking a human to click again.

**Placement:** guides/tooling-gotchas.md §Own what you spawn — new bullet "Issued-to-a-human handles are commitments" after the Subprocess/handle lifecycle bullet

**Why (strength):** One independent session (claude:b033d806) only, so recurrence across sessions is unproven; but within it the same class of error recurred twice via two distinct mechanisms (listener replaced under a live URL; handler overwrote the captured code on a trailing favicon GET), each costing a human consent round-trip (four clicks total) with a false 'authentication finished' screen — the cost falls on the user, not the agent, which is the rare-high-cost shape. The fix was proven with a regression test whose negative control fails without the fix, so the evidence is concrete. General form (any one-shot human-handoff channel; write-once capture; simulate before re-asking a human) is clearly extractable, and the baseline's lifecycle rule covers teardown only, not the inverse 'do not tear down what a person holds'. Guide placement, not global: its failure mode is recognition of the situation, so a pointer-backed gotcha entry is the right altitude.


### Before adding a validator, measure how often the existing ones actually fire on the real corpus

`partial` · strength 3 · 1 session `claude:cbf1879f` · ⑥quality ①hi-tok

**Rule:** Before adding, removing, or blaming a check (validator, detector, gate, blocking producer), measure each existing one's firing rate on the real corpus it has processed and map which rejection sites actually block: a check that has never fired in production is either dead weight or broken, and either way is not evidence about where blockers come from. Extend the same census to the mechanism you are about to build — search stored artifacts and existing computations for it before writing it. This is a census of production behavior, distinct from the negative control that proves a check can fire on a planted input; run it when the question is "too many checks" or "which check is the source", not on every change.

**vs baseline:** guides/verification-discipline.md §When a green means nothing — partially covers: negative controls and "revert the fix and watch it fail" prove a check CAN fire, and §Reuse The Vocabulary Before Adding To It covers reusing concepts, but nothing tells the agent to measure whether existing checks HAVE fired on real data before adding, removing, or blaming them, nor to search for an already-computed artifact before building a matcher.

**Placement:** guides/verification-discipline.md §When a green means nothing (add a sixth shape: "The check that has never fired" — with the census-before-add/remove/blame rule and the search-stored-artifacts corollary)

**Why (strength):** One independent session, so recurrence is thin, but materiality is real: the census flipped the user's premise (7 of 9 detectors had never fired on the delivered corpus, so validator count was not the blocker source) and avoided rebuilding a matcher already stored thousands of times. The rule has an invariant trigger and a clean general form; the baseline's adjacent rules address a different question (can it fire vs. has it fired), so it extends rather than duplicates.


### Source confidentiality belongs to model/provider selection, not to degrading the task input

`partial` · strength 3 · 1 session `claude:e4c1c5ea` · ⑥quality ②rollback

**Rule:** When an input is confidential and an LLM must reason over it, do not protect it by redacting, trimming, or projecting the input into an identifier-only envelope before the model sees it — a model reasoning over a degraded input produces a degraded result, often no better than a deterministic baseline, so the redaction buys no value while still spending the call. Place the confidentiality boundary on the execution route instead: choose a model, provider, or deployment that meets the data's security bar, and give that route the full input. Reduce accessible context only for relevance, budget, or a concrete named leakage risk that route selection cannot address (e.g. the data may never leave a host at all, in which case the LLM route is unavailable rather than crippled).

**vs baseline:** Global CLAUDE.md §Decision Framing "Do not default to a restrictive lens (security, masking, capability limits) when the system's purpose is sharing or utilization" — partially covers (general anti-masking stance). guides/llm-capability-boundary.md §Capability Surface lists "Accessible context" and "Execution routes" as levers but never states that confidentiality is a route/provider-selection constraint rather than a context-reduction one; the guide's only privacy note is about keeping sensitive data out of schema text. Omits the specific failure mode.

**Placement:** guides/llm-capability-boundary.md §Capability Surface (under the "Accessible context" / "Execution routes" levers)

**Why (strength):** Single independent session (claude:e4c1c5ea), so recurrence is thin, but materiality is real: a whole redaction-envelope design was built, measured 0/5 by a blind judge against a deterministic outline, and rolled back by owner decision — a rollback of a design branch, not a one-line fix. The form is clearly general (any confidential-input LLM task) and the baseline has only the abstract anti-restrictive-lens bullet plus unlinked "accessible context" and "execution route" levers, so an explicit sentence tying confidentiality to route selection adds a decision rule the corpus currently lacks. Not global-worthy: the failure mode is recognizable at design time and belongs behind the existing guide pointer.


### CLI flag probes must not be able to run the CLI; a boolean flag swallows the probe value as a prompt

`partial` · strength 3 · 1 session `claude:d107b796` · ⑤rare-hi-cost

**Rule:** When probing a CLI empirically to learn which subcommands or flags it accepts, use only invocations that cannot perform the tool's real work: help forms, or a candidate flag paired with a control flag that makes execution impossible (dry-run, version, an invalid required argument). Never invoke a subcommand bare, and assume a value placed after a flag may be consumed as the command's positional input — a boolean flag does not take the value, so it falls through to the prompt or target and executes for real (a live session, a metered call, a write). Distinguish 'boolean flag' from 'unregistered flag' by the parser's error, not by whether the run succeeded. Applies to any CLI whose positional is an input to a real action; a pure read-only tool is out of scope.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety — "confirm it empirically against the live or installed artifact (a minimal probe, the binary's registered options)" mandates the probe but says nothing about the probe itself executing the command; guides/tooling-gotchas.md "Production probes expose data" covers data leakage from probes, not side effects from flag probes. Partially covers.

**Placement:** guides/tooling-gotchas.md §Shell execution traps (new bullet "CLI flag probes that execute", adjacent to "Passthrough arguments in a CLI you author")

**Why (strength):** One independent session (claude:d107b796), but materiality is high: the probe opened a live vendor remote-control session and made a real metered model call, and the agent's own probe script carried the same defect. The trigger is general — any CLI whose positional is an input — and the baseline actively instructs probing without a safety boundary, so the gap is created by an existing rule rather than incidental. Single-session recurrence caps it at 3.


### Before publishing a package, install the actual packed tarball into a clean directory with lifecycle scripts enabled and smoke it there, because repo-side hooks (prepare/postinstall) run in the consumer's environment where build inputs are absent and can destroy the shipped runtime; and after moving a directory, re-derive the ignore result on the new paths and inspect the staged diff size, because ignore patterns are path-bound and do not follow moved files.

`partial` · strength 3 · 2 sessions `claude:d279f333 claude:6de415d0` · ⑤rare-hi-cost ⑥quality

**Rule:** Packaging and ignore contracts are evaluated against paths and environments, not against the source tree you are looking at. Before a release, pack the real tarball, install it into a clean directory with lifecycle scripts ON (not --ignore-scripts), and smoke the installed copy — a prepare/postinstall hook that works in the repo can delete or rebuild the shipped runtime in a consumer environment where the build toolchain and inputs are absent. After moving or renaming any directory, treat every ignore rule (.gitignore, .npmignore, .dockerignore) as void for the new paths: re-run the ignore check on the new locations and read the staged diff's file count and size before committing, since patterns anchored to the old path silently stop matching and previously excluded derived data or secrets enter the stage. Boundary: this is for artifacts that leave the checkout (published packages, images, commits to a shared branch); a purely local move with no commit or publish ahead needs only the diff-size glance.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety ("confirm it empirically against the live or installed artifact") — partially covers the 'installed artifact' stance for versions/flags/capabilities, but says nothing about lifecycle scripts at consumer install time or about ignore patterns being path-bound after a move; guides/tooling-gotchas.md §Git operations and §Config, secrets, and managed services have no npm-publish or ignore-after-move entry.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (publish-smoke bullet) and §Git operations (ignore-rules-after-move bullet)

**Why (strength):** Materiality is high (a prepare script that deletes dist in the consumer's install would ship a broken package; 179 never-commit source-derived sidecars nearly entered a commit). The publish-smoke half rests on one session; the 'ignore patterns are path-anchored and must be verified against the produced artifact' half is independently corroborated by a second session (claude:6de415d0, .dockerignore anchored at context root leaking a key into an image), giving two independent sessions for the general mechanism. Baseline covers the 'installed artifact' stance only for versions and flags, so this extends rather than duplicates. Not too specific: npm prepare, git moves, and dockerignore are three instances of the same invariant.


### Unattended API collectors: assert completeness against the API's own totals and reconcile lost batches

`partial` · strength 3 · 1 session `claude:6e493fd5` · ⑤rare-hi-cost ⑥quality

**Rule:** When an unattended collector enumerates a population through a paginated or bucketed source, classify retriable failures by class (any server-side transient: 5xx, gateway timeouts, connection resets) rather than by an enumerated list of status codes, since an omitted code drops items silently; persist which batches failed and run a reconciliation pass that re-fetches them before the run is declared done; and treat completion as a falsifiable assertion — the collected count per population must equal the source's own reported total for the same filter, and any mismatch or a total taken from a differently scoped population is a defect, not a footnote. Applies to enumeration runs whose completeness matters downstream; a sampled or best-effort crawl with a declared partial scope is outside it.

**vs baseline:** cli-multi-model-workflow.md §Unattended Batch Safety (per-item completion, circuit breaker, poison items dead-lettered, resume only unfinished items) and global §Verification Discipline "fix a common basis — units, denominators, population" plus the review-request evidence line "nothing tied the inventory's denominator to the source's own count". Partially covers: per-item tracking and resume exist, but nothing says (a) retriable set is a failure class not a code list, or (b) a collection run is done only when its count is asserted against the source's authoritative total for the same filter.

**Placement:** guides/cli-multi-model-workflow.md §Unattended Batch Safety — one bullet after the poison-item/dead-letter bullet

**Why (strength):** Single session (claude:6e493fd5) but concrete and high-materiality: a retry list missing one status code silently lost 16 users' batches, recovered only by an added reconciliation pass, and a wrong-population total (orgs included) was nearly accepted as the denominator. The general form (class-based retriability + completeness asserted against source totals) is a clean extension of the existing batch-safety bullets rather than a new concept, so it earns a guide bullet, not a global one. No independent recurrence caps strength at 3.


### Rolling traffic back does not roll back the service spec; the next deploy inherits the flag

`partial` · strength 3 · 1 session `claude:6c9836d1` · ②rollback ⑤rare-hi-cost

**Rule:** On a runtime where a config change creates a new revision and traffic is pinned separately (revision-pinned serving), reverting traffic to the previous revision restores behavior but not configuration: the added env var, flag, or secret binding stays in the service template and the next routine deploy re-enables it silently. Treat a rollback as complete only when both the live traffic split and the service spec are back to the prior state — after any traffic rollback, re-read the spec and remove the change explicitly. Not applicable to runtimes where rollback redeploys the prior spec itself (immutable-artifact or GitOps-driven deploys).

**vs baseline:** guides/tooling-gotchas.md §managed-service traps: "A new revision is not live traffic" covers the forward direction (deploy ≠ serving) and "Merge-not-replace update APIs" covers stale definitions surviving an update; neither states that a traffic rollback leaves the spec change in place for the next deploy to inherit. Partially covers.

**Placement:** guides/tooling-gotchas.md §managed-service traps, as a sibling bullet directly after "A new revision is not live traffic"

**Why (strength):** Single independent session (one provider tag), so recurrence is thin; but materiality is high — the failure is silent, delayed, and surfaces as an unexplained flag flip on an unrelated future deploy (rare-high-cost + rollback criteria), and the rule is clearly general across revision-pinned runtimes (Cloud Run, Knative, similar). The baseline already frames the same runtime and the same traffic/revision split, so this is a natural inverse extension rather than a new topic.


### Read the persisted failure reason before hypothesizing about credentials; verify runtime files inside the built image

`partial` · strength 3 · 1 session `claude:6c9836d1` · ①hi-tok ②rollback ⑤rare-hi-cost

**Rule:** When a batch reports uniform failure (every attempt failed) and the per-item error is persisted somewhere other than the log — a status or reason column, a result record — read that persisted reason before forming any hypothesis about keys, quota, credits, or model availability: uniform failure is usually structural (a missing file, a wrong path, a build omission), not a limit. And when code reads sibling files from its working directory at runtime, prove those files exist inside the built deployment artifact (list or hash them inside the serving image or container), not in the repo: a selective copy pattern in the build passes every repo-side check and only fails at runtime, so "the file is in the repo" is not evidence it is deployed. Boundary: applies to any packaged/containerized runtime with a build step that selects files; a plain source checkout run in place needs only the first half.

**vs baseline:** Global CLAUDE.md §Tooling and Operational Safety ("Treat a coarse runtime signal ... as a hypothesis, and confirm the cause against the authoritative low-level evidence the mechanism emits ... read the raw provider/skill log payload") partially covers the first half but assumes the evidence is a log payload, not a persisted-but-unlogged column; tooling-gotchas §Config, secrets, and managed services "A new revision is not live traffic" is the adjacent deploy-truth entry but says nothing about file inclusion in the built artifact. The built-artifact half is absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (new bullet beside "A new revision is not live traffic"), with the persisted-failure-reason clause folded into the existing global "coarse runtime signal" bullet only if it fits without lengthening it; otherwise both halves in the guide.

**Why (strength):** One independent session (the later verifying session is the same initiative, not independent recurrence), so recurrence is weak. Materiality is high: the root cause flipped three times, a production feature had been silently failing while a handoff claimed success, and the fix required a rollback-class correction — rare-high-cost. The general form (persisted-not-logged errors; build-selected files verified in the artifact) is clearly transferable beyond this repo, and the baseline covers only the "signal is a hypothesis" framing, not either concrete trap.


### Wiring a shared missing dependency re-enables every consumer at once

`partial` · strength 3 · 1 session `claude:6c9836d1` · ⑤rare-hi-cost

**Rule:** When a fix supplies a shared dependency that has been silently absent — a secret, credential, packaged file, or switch read by many code paths — the repair does not fix one feature; it wakes every consumer that was failing quietly behind it. Before applying it, enumerate the consumer set and state what each will begin doing once the value resolves (metered calls, external writes, sends, user-visible output). If that onset exceeds the feature under repair, present the wiring as an owner decision with the consumer list and expected spend or side effects, rather than landing it inside the narrower fix; the one-line change is the smallest part of its blast radius. Does not apply when the dependency has a single consumer or every consumer is read-only and free.

**vs baseline:** Global Coding Guidelines default-off/security-weakening bullet (a one-line change treated as a decision, but scoped to loosening security/authority, not to activating dormant consumers); llm-capability-boundary §Security And Side Effects (classify side effects, approval for high-impact actions — generic, not about shared-dependency repair); "treat a produced field as inert until a consumer reads it" covers the inverse direction (value present, consumer absent). Blast radius appears only as a model-allocation dial. Partially covered: the decision-shape exists, the trigger (shared dependency repair as multi-consumer activation) is absent.

**Placement:** guides/coding-staged-workflow.md §Default Frame — Stage 0 Triage (blast-radius call), as a named trigger; optionally a clause on the global Coding Guidelines default-off bullet pointing to it

**Why (strength):** One independent session (claude:6c9836d1), so recurrence is thin, but materiality is high and concrete: a single secret wiring would have simultaneously resumed five metered LLM paths, a rare-high-cost onset the agent correctly escalated instead of landing inside an interpretation fix. The pattern is clearly general (any many-consumer dependency: secrets, feature flags, packaged files) and the baseline has the decision shape without the trigger, so an extension is cheap and non-duplicative. Strength capped at 3 by single-session evidence.


### Never read the field you are about to overwrite as the model's input

`partial` · strength 3 · 1 session `claude:925a97c9` · ⑤rare-hi-cost ⑥quality

**Rule:** When an LLM stage can run more than once against the same record (reclassification, re-summarization, backfill, retry), its input must come from a field the stage never writes. If the stage reads a column and then writes that same column, every re-run feeds the model its own previous answer and the stored value drifts away from the source with no error raised. Keep the originally captured value immutable and write every derived value to a separate field; a fallback such as "original if present, else current" is acceptable only while the original is guaranteed captured going forward. When one such read-then-overwrite shape is found, audit sibling stages for the same pattern — one that is harmless today only because its selection rule skips already-overwritten rows is a latent instance, not a clean one.

**vs baseline:** guides/llm-capability-boundary.md §Persistence, Idempotency, And Retry (retries "safe for pure generation", idempotency keys — covers side-effect safety, not input/output aliasing) and guides/concept-economy.md §Derived Values Stay Derived (derived copy becomes a second authority) plus the pipeline-simplification note that dropping captured source fields is a separate, riskier decision. Together they partially cover: the immutability of captured source and the danger of persisted derived values are stated, but the specific failure — a re-runnable model stage whose input field is its own output field, converging to noise silently — is absent.

**Placement:** guides/llm-capability-boundary.md §Persistence, Idempotency, And Retry

**Why (strength):** One independent session (claude:925a97c9), so recurrence is weak, but materiality is high: the defect is silent (no validator can catch a model re-summarizing its own summary), degrades data on every re-run, and the same session found a second latent instance in a sibling service — evidence the shape is a class, not a one-off. The general form is clean and framework-neutral, and the baseline's retry guidance ("retries are safe for pure generation") is actively misleading for this case, which makes the gap worth closing with one sentence.


### Measure a flip's blast radius in-tree before designing activation; a level field can serve two roles

`partial` · strength 3 · 1 session `claude:de3b5e70` · ⑥quality ⑤rare-hi-cost

**Rule:** Before designing how a version, default, or severity flip will be activated, flip it in-tree, run the full suite, classify each failure by root cause (pure cascade from the flip, generation-pinned controls, designed detectors that are meant to fire, real regressions) and restore — the classified count is the blast radius the activation design must answer to. When a change re-maps or demotes an existing level in a severity/status field, enumerate every reader of that field before deciding, because one level commonly gates more than one behavior (shipping, repair, retry, display); a design that considered only the visible role silently changes the others. A defect confirmed but deferred by that measurement is pinned as a strict expected-failure — it keeps the tree green and forces re-review when the eventual fix lands — never left as a silent pass or a skipped test. Boundary: this is for changes to the meaning of an existing value; adding a new value follows the exhaustive-reader rule already in Reuse The Vocabulary.

**vs baseline:** Global CLAUDE.md §LLM And Capability Boundary ("treat a produced field ... as inert until a downstream consumer reads it") and concept-economy.md §Reuse The Vocabulary Before Adding To It (adding an enum value obliges every exhaustive reader) — partially cover. Both address adding a new field/value; neither states that re-mapping an existing level requires enumerating all readers because one field gates multiple behaviors, nor the flip-in-tree blast-radius measurement before activation design, nor pinning a deferred defect as a strict expected failure.

**Placement:** guides/concept-economy.md §Reuse The Vocabulary Before Adding To It (extend: changing an existing value's meaning enumerates every reader — one level, several roles); flip-measurement step and strict-xfail pin in guides/coding-staged-workflow.md §Making the change

**Why (strength):** Single session (claude:de3b5e70) so recurrence is 1, but the evidence is concrete and measured (90→53→39 failures classified; a real regression where demoting a severity level for the ship gate silently disabled repair, 1→0, and a broken artifact shipped). The gap in the baseline is real and general: the corpus governs adding enum values and wiring new fields, not re-mapping an existing level that serves two roles. Materiality is rare-high-cost (shipped defect), and the rule is clearly general beyond this repo. Capped at 3 for lack of independent recurrence.


### `pgrep -f` / `ps | grep <name>` matches the invoking shell itself (the pattern sits in its own argv) and any unrelated long-lived process sharing the name, so a name-substring count is not a liveness signal for a dispatched job.

`partial` · strength 3 · 2 sessions `claude:bab6550b claude:145a37cb` · ④recur-err

**Rule:** Name-substring process lookup (`pgrep -f <name>`, `ps | grep <name>`) is not a liveness check: the pattern appears in the argv of the shell that runs it, so the query matches itself, and it also matches unrelated long-lived processes that happen to carry the same name (other sessions, sibling dispatches, the launcher's own plan text). To confirm whether a dispatched job is alive or finished, use the PID or task handle captured at launch, its process-group state, or growth of its own output/log artifact — never a count of name matches. A substring lookup is acceptable only for discovery when the result is then verified against one of those owned identifiers before any conclusion or intervention.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety partially covers: it forbids command-line-substring scoping for destructive actions (kill/rm) and treats a `ps` result as a hypothesis; guides/cli-multi-model-workflow.md §Delegation Mechanics says to pin the exact handle received at dispatch when polling. None names the self-match mechanism (the pattern is in the querying shell's own argv) or the sibling-session false positive for a read-only liveness check, which is the failure that actually occurred; guides/tooling-gotchas.md §Shell execution traps has no process-inspection entry at all.

**Placement:** guides/tooling-gotchas.md §Shell execution traps

**Why (strength):** The cluster has one member, but its evidence cites two independent sessions (a self-match on the launch-plan string in one; days-old unrelated sessions matched by name in another), so recurrence is two. Materiality is moderate: a false "still running" or "already finished" reading drives wrong waits, re-dispatches, or kills. It is clearly general — the mechanism is inherent to `pgrep -f`/`ps|grep` — but the existing global rule already blocks the destructive half, so this is an extension of a guide entry (the read-only liveness case and the self-match cause), not a new global bullet.


### Measuring lossiness needs interior markers; elision keeps both ends

`partial` · strength 3 · 1 session `claude:bab6550b` · ②rollback ⑥quality

**Rule:** When probing whether a channel (tool result, context window, log, API response) delivers a payload intact, seed markers at evenly spaced interior points and count which survive alongside any truncation notice — never only head and tail, because elision is typically middle-out and end-markers pass on a gutted payload. Report the result as a fraction of markers placed (n/N), not a LOSSLESS/LOSSY label; a limit that cannot be raised past a plateau means a second cap governs, and size the payload against what is actually on the wire, since a result carried in two forms (rendered text plus structured copy) doubles its transport cost. Applies to any intactness or capacity measurement; it does not replace the known-opposite check, it fixes the probe's shape.

**vs baseline:** tooling-gotchas.md §"Tool output is a rendering, not the bytes" (partial — covers grep-binary, viewer normalization, stale caches, not middle-out elision); AI-workbench golden "run the instrument against an input whose answer is known to be the opposite" and personal learning on testing the instrument on agreement (partial — states the principle, not the marker-placement mechanism); global "coverage count that hides its own truncation" (adjacent). Marker placement, plateau-means-second-cap, and duplicated-envelope sizing are absent.

**Placement:** guides/tooling-gotchas.md §Tool output is a rendering, not the bytes

**Why (strength):** One independent session (claude:bab6550b), but materially concrete: the head/tail probe produced a false LOSSLESS at one limit while a higher limit truncated, and the corrected probe exposed a second cap and a 2.05x envelope inflation — a false-pass instrument defect of the class the baseline says dominates. The general form (interior markers, fraction reporting, plateau => other cap, wire-size vs carried-twice) is invariant across channels, so it is not a one-off; single-session recurrence caps strength at 3.


### Confirm a stopped run from the sink, not the process list; versioning with expiry is not a backup

`partial` · strength 3 · 1 session `claude:7832145a` · ②rollback ⑤rare-hi-cost

**Rule:** After stopping a multi-stage run, do not treat a clean process list as proof the stop held: a kill that misses one descendant lets the surviving stage finish and publish. Confirm at the output sink — list objects, versions, or rows whose write instant is after the stop instant — and treat anything found there as contaminated output to roll back. Before relying on storage-level versioning or "previous version" mechanisms as the rollback path, read their retention policy: noncurrent-object expiry makes versioning a short recovery window, not a backup, so take an explicit named snapshot before a risky run, name it by the event it precedes, and select the restore point by timestamp rather than by name or assumption. Applies to any pipeline writing to a durable sink (object storage, DB, published artifacts); for a single foreground process with no external sink, the process exit status suffices.

**vs baseline:** Partially covered. Global §Tooling and Operational Safety: "snapshot the last good state before any in-place resume or overwrite" and "treat a `ps`/process-inspection result as a hypothesis, confirm against the authoritative evidence the mechanism emits" (both about diagnosing before acting, not about post-stop verification). tooling-gotchas.md §Own what you spawn: kill the whole process group, not the wrapper PID (mechanism side only). verification-discipline.md Verification Menus: "back up live data before the first run" for branch builds. Absent: verifying a stop at the sink by post-stop write timestamps, and retention-limited versioning masquerading as a backup.

**Placement:** guides/tooling-gotchas.md §Own what you spawn (sink-side stop confirmation bullet) and §Config, secrets, managed services (versioning-with-expiry is not a backup bullet)

**Why (strength):** Single independent session, but high materiality: a claimed clean stop was false, contaminated output reached the production bucket, and the only recovery path was a 14-day-expiring versioning window plus a misnamed backup — a rollback plus rare-high-cost event. The general form (verify the stop at the sink; read retention before calling versioning a backup) is clearly transferable across cloud pipelines and is not stated in the baseline, which stops at killing the process group and diagnosing before acting.


### Preserve semantic force during style-only transformations

`partial` · strength 3 · 1 session `codex:019f9259` · ②rollback ⑥quality ①hi-tok

**Rule:** When a transformation is declared style-only — a rewrite, humanizing pass, translation, reformat, or tone change — treat the source's polarity, modality, causal attribution, assertion strength, and the author's stated position as invariants: never weaken, hedge, or flip a claim, and never "repair" an apparent contradiction or inconsistency in the source, since resolving it is a content decision that belongs to the author (name it as a finding instead). Surface checks (numbers, quotations, headings, links, punctuation, length) prove only surface preservation; before calling such a transformation done, verify meaning separately by comparing source and result claim by claim. This applies to prose the transformation was asked not to change in substance; it does not bind edits where content change was explicitly requested.

**vs baseline:** guides/coding-staged-workflow.md §Making the change ("Surgical means legible, not minimal" — every changed line traceable to the request) partially covers scope; guides/verification-discipline.md §Verification Menus Docs row (links, terminology, current behavior alignment) covers only surface checks. Neither names semantic invariants for style-only rewrites nor forbids silently resolving a perceived source contradiction.

**Placement:** guides/coding-staged-workflow.md §Making the change

**Why (strength):** Single independent session (one codex tag), so recurrence is thin, but materiality is concrete and general: deterministic surface checks passed while two semantic regressions (weakened assertion, reversed polarity introduced to "fix" a contextual inconsistency) reached the output and were rolled back only because an independent source-to-output review ran. The failure shape — surface checks green, meaning drifted — generalizes to every rewrite/translation/humanize task and is a genuine gap: the baseline's surgical-edit rule is code-framed and the Docs verification menu lists no semantic-preservation check. Partial rather than novel because scope traceability and "docs alignment" exist as adjacent rules.


---

## Strength 2  (64)

### Before the operator leaves a network perimeter, drain every perimeter-gated action first

`novel` · strength 2 · 1 session `claude:b35039cd` · ⑤rare-hi-cost ②rollback

**Rule:** When the user announces an imminent loss of a network or identity context that gates remote actions (VPN, IP allow-list, context-aware access, an expiring session), treat the announcement as a re-ordering trigger: pause the current task, enumerate every pending action that requires that context — remote pushes, cloud-side verification, migration steps and their confirmation — execute those first, and only then write and push the handoff. Local-only work is deferred; context-gated work cannot be finished once the context is gone, so an unconfirmed gated step becomes an open item for the next session by default. This applies only when a gated action is actually pending; it does not license skipping verification of the gated steps to beat the clock.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services ("Perimeter controls need the enforcement point's own logs") and global CLAUDE.md §Tooling and Operational Safety (pin ambient cloud CLI context) / §Multi-Model Workflow (re-verify location on resume) — omits: none of these sequence work when the perimeter is about to be lost.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet adjacent to "Perimeter controls need the enforcement point's own logs"

**Why (strength):** One independent session only (claude:b35039cd), so recurrence is unproven; materiality is real — a production migration step was left unconfirmed and the handoff could not be pushed until the next session, both gated by the perimeter the user had announced leaving. The rule is general (any VPN/allow-list/context-aware-access setting) and its trigger is an explicit user announcement, so it is recognizable and guide-placement (behind the perimeter-controls pointer) is adequate; not global-worthy on single-session evidence.


### git add exits non-zero on an ignored path after staging the rest, breaking && chains and merging commits

`novel` · strength 2 · 1 session `claude:c05b151d` · ②rollback ④recur-err

**Rule:** `git add` with several pathspecs is not atomic: it stages every addable path and still exits non-zero when any one path is ignored (or missing), so a chained `git add … && git commit` silently skips the commit while leaving the index populated, and the next commit absorbs both change sets. When staging multiple paths for a commit — especially any path under a dot-directory or tool-managed tree that may be gitignored — stage per logical unit, confirm the index with `git status --porcelain` (or `git diff --cached --stat`) before each commit rather than relying on the chain's exit status, and add an ignored path only by an explicit `-f` decision after `git check-ignore -v` shows why it is ignored. Does not apply to single-path adds, where a non-zero exit stages nothing.

**vs baseline:** guides/tooling-gotchas.md §Git operations — omits: covers stale bases, two-dot diffs, path reverts, dirty pulls; nothing on partial staging with non-zero exit. The repo-local AGENTS.md `git add -A` sweeping trap is a different mechanism (over-broad pathspec, not a chain break) and is not in the deployed baseline. Global §Tooling and Operational Safety only points to the guide.

**Placement:** guides/tooling-gotchas.md §Git operations

**Why (strength):** Genuinely absent from the baseline and a decidable command-pattern trap with a general form (non-atomic multi-path staging + && chain), so it fits the guide's existing bullets. But evidence is a single session (one provider tag), and the cost was moderate and reversible — splitting commits on an unpushed branch — not a rare-high-cost or multi-session recurrence. Adjacent single-session candidates (123: pre-staged foreign changes in the index; 130: check-ignore on cited paths) share the "inspect the index/ignore state before committing" theme and could be merged into one bullet at integration time, which would raise the effective support.


### Classify an externally labeled batch of edits by kind and disclose label mismatches before applying

`partial` · strength 2 · 1 session `claude:09ca2e76` · ⑥quality

**Rule:** When a batch of changes arrives under a descriptive label (a "formatting", "line-break", "typo", or "rename-only" revision, commit, or handed-over diff), treat the label as a claim about the batch, not a description of it: classify the diff by kind before applying, apply what the label covers, and disclose every hunk of a kind the label does not name so the user confirms it was intended. The unlabeled class is where unreviewed content changes hide. This applies to edits you did not author that you are asked to apply or merge; a diff you produced yourself is covered by stating your own scope instead.

**vs baseline:** Global CLAUDE.md §Decision Framing — "Treat user suggestions, inherited premises, handoff and design claims ... as hypotheses, not facts; re-derive each load-bearing claim from real code or data before building on it" — partially covers (a label is an inherited claim), but names no concrete behavior for an incoming batch of edits; guides/coding-staged-workflow.md §Making the change covers only the agent's own diff scope ("State the assumption", "Surgical means legible"), not a diff received under someone else's label.

**Placement:** guides/coding-staged-workflow.md §Making the change (new paragraph after "Surgical means legible, not minimal")

**Why (strength):** One independent session; the failure it guards (13 of 21 hunks in a "line-break" revision were wording/title changes) is real and general to any label-carrying batch, but the cost was disclosure-level (user confirmed the changes), not rollback or repeated error. The general "claims are hypotheses" rule already exists at global level, so this is a guide-level concrete instance, not a new global bullet.


### A failed cd in a compound command silently runs the remainder in the wrong directory

`partial` · strength 2 · 1 session `claude:fdf01c38` · ④recur-err

**Rule:** Directory-change masking: in a compound shell command, a `cd` joined with `;`, a newline, or a subshell that never checks its status lets the remaining commands run in the previous working directory when the change fails (missing dir, quoting or non-ASCII path, sandbox refusal) — and a scan, test, or grep then reports on the wrong subject with a green exit code. Never let work depend on a `cd` whose failure does not abort the chain: use absolute paths for every path-bearing command, or bind the change with `cd … && …` / `cd … || exit`, and when a verification reads unexpectedly clean, confirm `pwd` (or the resolved subject paths) before trusting it. Does not apply where the tool resets or pins the working directory per call and every path is already absolute.

**vs baseline:** guides/tooling-gotchas.md §Shell execution traps — "Pipe exit masking" covers the sibling failure (a masked non-zero status reads as green) and §Ambient state drifts covers pinning ambient state, but no entry names cd failure leaving the chain in the old directory; the global "re-verify pwd on resumed session" bullet covers session relocation only, and the absolute-path preference lives only in the Bash tool description, not the corpus. Partially covered.

**Placement:** guides/tooling-gotchas.md §Shell execution traps (new bullet beside "Pipe exit masking")

**Why (strength):** One independent session (claude:fdf01c38) with a concrete incident: a verification scan ran over the wrong files after a cd failed and the session recovered by re-running with absolute paths. Materiality is real — it produces a false-green verification, the same failure class the corpus already treats as high-cost — and the form is fully general (any shell, any tool). But recurrence is a single anecdote and the specific cause (non-ASCII path) is unverified in the transcript summary, so it earns a guide bullet, not a global rule.


### Dead imports left by a code move can mask a gate's import check

`partial` · strength 2 · 1 session `claude:3364ce2a` · ⑤rare-hi-cost ⑥quality

**Rule:** The residue that satisfies the probe. A check that reasons over presence — an import, a symbol, a reference, a string — is satisfied by leftovers as readily as by the thing it names: a move or extraction that leaves dead imports or stale references behind keeps such a check green and silences its negative control, because the guard finds what it looks for in the debris. After moving or extracting code, remove the residue the move created before trusting any presence-based gate, and re-run that gate's negative control afterward: a control that fires only once the residue is gone is the proof the cleanup was load-bearing rather than cosmetic. Applies to gates and tests keyed on presence; a check that executes the real path is not fooled this way.

**vs baseline:** guides/verification-discipline.md §When a green means nothing (five shapes + "revert the fix and watch the check fail") — partially covers: it names vacuous greens and the revert discipline, but no shape for refactor residue satisfying a presence-based check; guides/coding-staged-workflow.md §Verification "Clean up what this change introduced" frames dead imports as diff hygiene only, not as a gate-blinding mechanism.

**Placement:** guides/verification-discipline.md §When a green means nothing — add as a sixth shape ("The residue that satisfies the probe"), with a one-clause cross-reference from coding-staged-workflow.md's cleanup paragraph

**Why (strength):** One independent session (claude:3364ce2a), so recurrence is thin, but materiality is real: a parity gate's negative control silently returned rc=0 after a refactor, which is the exact "false PASS about the gate itself" class the baseline names as its highest-cost defect, and the contrast experiment (cleanup flipped rc 0→1) is strong evidence for the mechanism. The general form — presence-based checks satisfied by refactor residue — is clearly not repo-specific, and it fills a gap in an existing enumerated list rather than adding a new rule, so it is cheap to place. Kept at 2 for single-session support.


### Scope a conformance proof to the producer it verifies; do not infer the producer from a shared label

`partial` · strength 2 · 1 session `claude:bbadb63d` · ①hi-tok ②rollback

**Rule:** A check of the form "output conforms to authority X" enforces one producer's contract, so its subject set is that producer's outputs — never every artifact that happens to carry a shared label, since a provenance label several producers write does not identify which contract applies. Key the check on an explicit producer identifier stamped at emission, and leave surfaces owned by another validation regime to their own validator. Before trusting the check's verdict, run it over the real, currently-accepted artifacts: rejections of output that is known-valid diagnose an over-wide subject set (the mirror of the empty subject), not bad data — fix the scope, never the data or the expectation. Boundary: this governs which artifacts a check judges, not whether the contract itself is right; a defect the narrowed check still catches is the positive control that the narrowing did not blind it.

**vs baseline:** guides/verification-discipline.md §Deriving the case space ("derive the exemption rule from a property the artifact carries, never from a list of names") and §When a green means nothing ("The empty subject") — partially covers: it handles the under-scoped subject set and property-derived exemptions, but says nothing about the over-scoped mirror (a shared label conflating producers with different contracts) or about real-artifact false rejections as the scope diagnostic. LLM-capability-boundary §Grounding And Provenance lists provenance fields but not a producer identifier keyed by a validator.

**Placement:** guides/verification-discipline.md §Deriving the case space — as a new bullet directly after the "Derive the exemption rule too" bullet

**Why (strength):** One independent session (claude:bbadb63d) only; materiality is real but moderate — a new proof falsely rejected 23 fixtures and 4 currently-published outputs, costing a rewrite (rollback) and heavy tokens, but it was caught before shipping and no rare-high-cost or recurrent-error criterion applies. The general form is clear and fills a genuine gap (over-scoped subject set is the unstated mirror of the baseline's "empty subject"), so it survives as partial rather than novel; single-session evidence caps strength at 2.


### Auto-memory is bound to the project path; a spun-off repo needs a self-contained resume doc

`partial` · strength 2 · 1 session `claude:441424ae` · ⑤rare-hi-cost ③re-explore

**Rule:** Host auto-memory, like sessions, is keyed to the starting directory, not to the person or the work: when work spins off into a new directory or repository, nothing accumulated in the originating project's memory is present there. Before ending such a session, write a self-contained resume document inside the new repository (current state, decisions, contracts, next steps, verification commands) and leave only a pointer plus a path warning in the originating project's memory; never rely on the origin's memory being loaded in the new location. Does not apply to a relocation the host performs natively within the same project (worktree, /cd), where memory scope is unchanged.

**vs baseline:** guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees — "Sessions bind to their starting directory" and "For a new worktree, relocate natively or write a handoff and start fresh", plus §Handoff Contract "Store handoffs in the working repo's isolated dated docs path". Partially covers: it binds sessions and handoff location to the directory, but says nothing about auto-memory being directory-scoped, so an agent can write a compliant handoff and still assume the origin project's memory will be there in the new repo.

**Placement:** guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees — extend the "Sessions bind to their starting directory" bullet

**Why (strength):** One session (claude:441424ae) and the agent caught it proactively rather than paying a failure, so materiality is inferred, not observed. The delta over the baseline is real but narrow: the baseline already routes the handoff into the new repo; what it lacks is the statement that memory does not follow and that the old memory should hold only a pointer. General across hosts with directory-keyed memory, so not too_specific, but single-session evidence keeps it at a one-bullet extension rather than a new rule.


### Record a state transition in memory only after its evidence exists

`partial` · strength 2 · 1 session `claude:a2f92bb1` · ②rollback

**Rule:** When writing a memory or handoff line that states a lifecycle transition (committed, pushed, merged, released, deployed), write it only from evidence observed after the action — the ahead/behind count, the merge commit, the deployed version — and never from the plan, the intended next step, or a step still behind a user gate; an unevidenced transition is written as the pending next action, not as state. Applies to any cross-session record the next session reads before re-verifying; it does not require re-proving transitions already anchored by the handoff's CONFIRMED evidence.

**vs baseline:** guides/cli-multi-model-workflow.md §Handoff Contract — partially covers: item 3 requires CONFIRMED claims to carry re-establishing command evidence and item 4 separates PROPOSED/OPEN, and the "never record the hash of the commit that will contain the record itself" bullet is one instance of the same trap; global §Decision Framing covers re-verifying handoff claims on read. Neither names the write-time failure of recording an intended/user-gated step as done, nor extends it explicitly to memory files.

**Placement:** guides/cli-multi-model-workflow.md §Handoff Contract (add a bullet after "Never record the hash of the commit that will contain the record itself")

**Why (strength):** One independent session; materiality low (two cheap re-corrections of a memory line and handoff, rollback criterion only). The rule is general and the baseline's Handoff Contract already carries the CONFIRMED-needs-evidence mechanism, so this is a one-clause extension naming the write-time trap (intended or user-gated step written as done) and extending scope to memory files — worth a bullet, not a global rule.


### An error from an earlier layer proves nothing about the gate behind it — only full success proves access

`partial` · strength 2 · 1 session `claude:ac47d36f` · ②rollback

**Rule:** A request pipeline reports its first failing layer only: a schema, field-name, parse, or argument error says nothing about the authorization, enablement, or quota gate behind it. When probing whether a service, account, tool, or capability is reachable, do not report access on the strength of a pre-gate error being "the only thing wrong"; drive the probe until it either fully succeeds (a real response from the resource) or fails with the gate's own denial, and report anything short of that as undetermined. Bounded to reachability/capability probes; it does not require a full call for every ordinary validation error.

**vs baseline:** Global §Tooling and Operational Safety — "confirm it empirically against the live or installed artifact (a minimal probe)" (says probe, not that the probe must complete past the gate) and "treat a coarse runtime signal ... as a hypothesis, and confirm the cause against the authoritative low-level evidence" (about failure labels, not a pre-gate error misread as success); guides/tooling-gotchas.md §Config, secrets, and managed services "Production probes expose data" (probe hygiene, not probe sufficiency). Partially covers; the layered-error-order trap is absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** One session, one retraction to the user (rollback of a stated "access works" claim); low cost — caught within the same exchange, no downstream work built on it. The general form is real (any layered API/MCP validates before authorizing) and the baseline's probe rules stop at "probe empirically" without saying what a finished probe looks like, so it is a genuine extension, but single-session evidence and modest materiality cap it at 2.


### Confirm an API's unit scale per denomination empirically before writing a threshold in it

`partial` · strength 2 · 1 session `claude:a165f834` · ⑤rare-hi-cost

**Rule:** Before writing a limit, cap, or threshold in an external system's numeric units (money amounts, quotas, rates), measure that system's unit scale for each denomination it handles — read it from a known-magnitude field such as a documented minimum or an existing live value — rather than assuming one convention (minor units, whole units) applies across all denominations; a threshold written at the wrong scale does not error, it silently blocks or silently over-permits every operation it governs. Applies to any per-denomination or per-region-scaled field; it does not require re-measuring a scale the same session has already confirmed for that denomination.

**vs baseline:** global CLAUDE.md §Verification Discipline "fix a common basis — units, denominators" (covers comparison, not writing a threshold into a foreign unit system) and §Tooling and Operational Safety "confirm any API capability... empirically against the live artifact" (covers capabilities/flags generally, not per-denomination unit scale); guides/tooling-gotchas.md §Config, secrets, and managed services has no unit-scale bullet. Partially covers; the per-denomination trap and silent-total-block consequence are absent.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** One independent session; the near-miss was averted rather than paid, so materiality is argued (100x-too-small cap blocking every write on affected accounts) rather than measured. The general form is real and well-known across payment/ads APIs, so it is not too_specific, but single-session support and a partially covering baseline cap it at 2. The candidate's two extra clauses (independent recomputation of expected vectors; deriving status rules from live data) are separate lessons already covered by the baseline's "treat prior claims as hypotheses, re-derive from real data" and the known-opposite-check rule, and were dropped from the principle.


### Reproducing from a cached artifact tests only the stages that re-ran

`partial` · strength 2 · 1 session `claude:e3f7ea5b` · ①hi-tok ③re-explore

**Rule:** In an incremental or cache-keyed pipeline, an artifact re-derived from cache exhibits the behavior of whichever stages actually re-ran and the old behavior of every stage the cache skipped. Before attributing a defect observed on such an artifact to a stage, read the cache or currentness keys to establish which stages ran on it; if the suspected stage was skipped, reproduce from a run that forces that stage rather than from the cached artifact. This applies to any staged build, translation, QA, or data pipeline with skip-on-current semantics; a one-shot from-scratch run needs no such check.

**vs baseline:** Global §Verification Discipline "Trust a green check only when it traversed the actual changed code through the real dispatch" and guides/tooling-gotchas.md "Stale caches in rapid loops" partially cover it (a result is only evidence about what actually ran; mtime-keyed caches re-serve stale output). guides/verification-discipline.md §When a green means nothing lists five shapes of a vacuous result but none is "the stage that never re-ran". Neither states that a defect seen on a partially re-run artifact may belong to a skipped producer, nor the behavior of reading the currentness keys before choosing which stage to reproduce against.

**Placement:** guides/verification-discipline.md §When a green means nothing

**Why (strength):** Single independent session (one claude session), criteria high_token only per the candidate, with re_exploration implied by many turns rebuilding the reproduction against the wrong stage. The general form is real and recurs in any skip-on-current pipeline, and the baseline's nearest rules speak to green checks and mtime caches, not to attributing a defect to a producer that was skipped; so it extends an existing section as a sixth shape rather than adding a new rule. Materiality is moderate (wasted turns, no rollback or rare-high-cost event), hence 2.


### When one claim from a source is wrong, quarantine the source's other claims too

`partial` · strength 2 · 1 session `claude:a3defb19` · ②rollback ⑥quality

**Rule:** When a claim already adopted from a single source (a research subagent, a reviewer, a handoff, a document) is shown to be wrong, every other claim taken from that same source loses its standing at once: enumerate where each of its sibling claims landed in the deliverable, then either remove them or re-verify each against an independent source before they stay. Correcting only the falsified item and leaving its siblings in place is not a fix. This applies to claims of the same provenance that were adopted without their own verification; claims from that source that were independently confirmed keep their standing.

**vs baseline:** Global CLAUDE.md §Decision Framing, "Treat user suggestions, inherited premises, prior diagnoses, handoff and design claims, reviewer findings, and your own earlier conclusions as hypotheses, not facts; re-derive each load-bearing claim..." and guides/verification-discipline.md §Independent review ("re-verify each finding against real code before acting on it") — partially covers: both demand per-claim re-derivation up front, but neither states that a falsified claim retroactively demotes sibling claims of the same provenance, nor the enumerate-where-they-landed step. Omits the propagation rule.

**Placement:** guides/verification-discipline.md §Independent review, and what agreement is worth — append after the paragraph "Then re-verify each finding against real code before acting on it: a reviewer reasons from what it was shown, and what it was shown may be wrong."

**Why (strength):** One independent session (claude:a3defb19) supports it; the evidence is concrete (a wrong unit price led to reverting a sibling constraint inserted in three places, i.e. a real rollback), and the rule is clearly general — provenance-based contamination applies to any research/review/handoff source. But single-session recurrence and moderate materiality (wrong numbers in a document, not an irreversible action) cap it at 2. The baseline's hypothesis-not-fact rule covers the forward direction, so this is an extension of an existing bullet in a guide, not a new global rule.


### A path derived from code constants is not the path the user sees

`partial` · strength 2 · 1 session `claude:af41014b` · ②rollback ④recur-err

**Rule:** When telling a user where an artifact lives in an external or managed service, do not answer from the code's constants or path builder: an API path is relative to the credential's own root (app folder, bucket prefix, tenant, workspace) and may sit under a different account than the one the user is browsing. Resolve the location through the live API under the credential actually in use, then translate it into what the user's UI shows — account, namespace, and root included — before stating it. Applies to any service where the API's coordinate system and the human UI's differ; a local filesystem path the user can open directly needs no translation.

**vs baseline:** Partially covered. global CLAUDE.md §Verification Discipline / AGENTS "verify against the artifact, not a document about it", §Tooling and Operational Safety "ambient state drifts... pin resolved paths" and "gate identity-tied actions on a live identity check" all point in this direction, but none names the trap that an API-relative, credential-scoped path is wrong for a human navigating the service UI. tooling-gotchas.md §Config, secrets, and managed services lists analogous managed-service traps (new revision is not live traffic, merge-not-replace) but omits this one.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Single independent session (one supporting tag), so recurrence is weak; materiality is moderate — the wrong answer was given twice (rollback of a user-facing claim) and only live API inspection resolved it. The general form is real (any credential-scoped service: Dropbox app folders, S3/GCS prefixes, Drive shared drives, multi-tenant SaaS) and the existing baseline has only the abstract 'verify against the artifact' rule, so it earns a one-bullet extension in the managed-service gotchas, not a global rule.


### Ask which axis should vary before generating 'more options'

`partial` · strength 2 · 1 session `claude:242e5da1` · ②rollback ①hi-tok

**Rule:** When asked for more variety, alternatives, or variants of an output, name the axis that is meant to differ — the mechanism that produces the intended effect (e.g. what makes the content compelling), not the surface rendering (layout, styling, wording) — before multiplying output; if the request leaves that axis open, confirm it with one question first, because many variants along the wrong axis add no real option and the rework is a full regeneration. Applies to creative, design, and option-generation requests where the varying dimension is not fixed by the task; a single unambiguous axis needs no confirmation.

**vs baseline:** global CLAUDE.md §Problem Solving ("First identify the goal, scope, ambiguities"; "ask only when ambiguity blocks progress or creates risky outcomes") and §Decision Framing ("Ask for the user's goal or constraint when that determines the answer") — partially covers: they address ambiguity and goal-asking in general, but nothing addresses variant/option generation or choosing the axis of variation before fan-out.

**Placement:** global CLAUDE.md §Decision Framing — one-line extension appended after "Ask for the user's goal or constraint when that determines the answer"

**Why (strength):** Single session (claude:242e5da1), one incident; materiality was real (72 variants discarded, full regeneration = rollback + high token) but the criteria are the lighter ones (no rare-high-cost, no recurrent-error). The general form is clear and the baseline's ambiguity rules do not name the variation-axis case, so it earns a partial extension rather than a new bullet; strength stays low for lack of independent recurrence.


### Audit each item alone when items are consumed in isolation

`partial` · strength 2 · 1 session `claude:1aa55a55` · ②rollback ⑥quality

**Rule:** When the audience will meet a set's items one at a time (a feed card, a notification, a single page, an error message), the unit of audit is the single item, not the set: run a deterministic per-item check against the criterion and report the count that fails, because a set read as a whole borrows meaning across items and passes while most members are not self-sufficient. A statement of what an item is not does not satisfy a criterion that asks what it is. Does not apply where the audience genuinely consumes the set together (a table, a gallery, a list page).

**vs baseline:** guides/verification-discipline.md §Deriving the case space ("Enumerate the space from the artifact that defines it") and §When a green means nothing ("The empty subject"), plus global Verification Discipline ("make PASS mean concrete assertions on real output") — partially covers: they demand enumerated, tool-counted subjects, but nothing says the audit unit must match the consumption unit or that a whole-set impression masks per-item failure.

**Placement:** guides/verification-discipline.md §Deriving the case space (new bullet after "Enumerate the space from the artifact that defines it")

**Why (strength):** One independent session (claude:1aa55a55) with a concrete 19-of-36 false pass reversing a whole-set "all good" judgment — material (the deliverable would have shipped broken), and the general form (per-item consumption vs. whole-set eyeballing) transfers beyond ads. But single-session recurrence, self-reported confidence 0.4, and the "negation is not a statement" sub-lesson is a one-off editorial observation, so the extension is warranted only as a narrow guide bullet, not a global rule.


### Reconcile transcribed figures against the arithmetic in the same passage before recording them

`partial` · strength 2 · 1 session `claude:5ad09543` · ②rollback ⑥quality

**Rule:** When the source of a fact is a lossy machine transcription (speech-to-text, OCR, auto-captions), treat every number and proper noun in it as a candidate mis-hearing rather than as data: before recording a figure, reconcile it against the related figures in the same passage — stated differences, ratios, totals, and counterpart proposals — and flag or hold any value the surrounding arithmetic does not reproduce; conversely, downgrade a name or fact to "uncertain" only when the source itself is ambiguous at that point, and say what was withheld. This applies to documents derived from transcripts (minutes, summaries, decision logs); it does not apply to structured data whose parser already validates it.

**vs baseline:** Global CLAUDE.md §Decision Framing ("treat inherited premises ... as hypotheses; re-derive each load-bearing claim from real code or data") and §Verification Discipline ("fix a common basis ... before comparing") state the general re-derivation stance; the Verification Menus in verification-discipline.md list per-domain mixes (code, ontology, config/data, spreadsheets, docs, release, A/B, guardrails, branch builds, capture switches) but have no entry for transcript-derived documents, and nothing in the baseline names the specific failure mode that ASR output looks like clean data while its numbers and names are unreliable. Partially covered.

**Placement:** guides/verification-discipline.md §Verification Menus — add a "Transcript-derived documents" bullet alongside the Docs entry

**Why (strength):** Single independent session (claude:5ad09543), but it carries two user rollbacks in one deliverable (a wrong financial figure recorded as fact, and correctly stated names over-scrubbed) and the assistant itself confirmed the in-passage cross-check would have caught the error — a concrete, cheap, general check. The general form (lossy-transcription sources need intra-passage reconciliation) is clearly not a one-off, and the baseline's re-derivation rule does not tell the agent that the "data" here is itself the unreliable layer. Recurrence is thin, so it earns a guide menu entry, not a global bullet.


### Build negative controls from the wrong implementations the check must reject, not from input perturbations

`partial` · strength 2 · 1 session `claude:173b9f9f` · ②rollback ⑥quality

**Rule:** When writing a negative control for a completeness, coverage, or invariant check, first enumerate the plausible wrong implementations the check must reject (an aggregate that cannot distinguish two failure shapes, a guard satisfied by absence, a bound that is necessary but not sufficient) and construct one input each of them would wrongly accept; a control obtained by perturbing valid input only proves the check can fail on that perturbation, and a wrong implementation can pass it for the wrong reason. Treat the enumerated wrong-implementation list as the control's subject set, and count a control set complete only when every named wrong implementation is rejected by at least one input; this is the construction step, and "revert the fix and watch it fail" remains the acceptance step after it.

**vs baseline:** guides/verification-discipline.md §Deriving the case space ("Prefer a signal that fails when the mechanism is wrong — a negative or contrast control", "Derivation moves authorship... Give them a negative control") and §When a green means nothing ("revert the fix it guards and watch the check fail") — partially covers: it says controls must fail when the mechanism is wrong and gives the revert acceptance test, but never says how to construct the control, i.e. from an enumerated set of candidate wrong implementations rather than from perturbed valid input. The review-request goldens mention mutation survival only as evidence, not as a construction method.

**Placement:** guides/verification-discipline.md §Deriving the case space — extend the "Make the criterion falsifiable" bullet with the construction rule

**Why (strength):** Single independent session (one supporting tag), so recurrence is thin, but the materiality is real: a control passed vacuously, a cross-family reviewer then produced a counterexample all three controls missed, and the plan and stage order had to be revised (rollback). The idea has a general form (mutation-style control derivation) and fills a gap the baseline leaves between "controls must be falsifiable" and "revert and watch it fail" — the construction step between those two is unstated. Strength kept at 2 pending a second session showing the same failure shape.


### Normalize per-item before aggregating and inspect for clusters before generalizing a single observation

`partial` · strength 2 · 1 session `claude:13d39d5f` · ②rollback ⑥quality

**Rule:** When measurements are collected to state a threshold, rate, or "typically X" rule, express each observation relative to its own denominator (its own window, budget, capacity, or population) before summarizing, and look at the shape of the distribution before quoting a median or mean: a summary over a mixed population hides the sub-populations, and an apparent contradiction between one observation and the aggregate is more often two populations than an error. A rule generalized from a single observation stays a hypothesis until a measurement across the population agrees. This applies to measured numbers that will enter a rule or a decision; a one-off diagnostic reading that changes nothing needs no such treatment.

**vs baseline:** Global CLAUDE.md §Verification Discipline, "fix a common basis — units, denominators, population" bullet: partially covers (common basis before comparing two things) but omits the aggregation step — per-item normalization to its own denominator and checking for multimodality before quoting a summary statistic. The specific compaction finding itself (84-87%, windows cluster at 200K and 1M) is already recorded as a fact in the Context Budget section, so only the method is missing.

**Placement:** guides/verification-discipline.md §When a green means nothing (as a bullet on measured evidence), or a new short subsection "Measured numbers that become rules" directly before §Reporting

**Why (strength):** Single session (one independent source). Materiality is real but moderate: the session had to roll back two of its own claims (a per-host threshold rule and an apparent 867k-vs-169k contradiction), and the error mode — quoting a median over a bimodal population — would have shipped a wrong number into a guide. The general form exists (common-basis rule) so this extends rather than adds; strength capped at 2 for lack of recurrence.


### A self-test's failure path must not write to the real artifact — isolate and assert the artifact unchanged

`partial` · strength 2 · 1 session `claude:dc1413c3` · ⑤rare-hi-cost

**Rule:** When a self-test or negative control exercises a mechanism that appends to or rewrites a durable artifact (a ledger, manifest, config, index), run it against an isolated copy of that artifact and, after the run, assert the real artifact is byte-identical to its pre-run state — on the control's failure path as well as its pass path, because a control that only cleans up when it succeeds pollutes live state precisely when it is doing its job. Planting a violation in a copy covers the input side; this covers the output side. Applies to any gate whose subject is a write-capable tool; a read-only check needs only the input isolation.

**vs baseline:** guides/verification-discipline.md §Deriving the case space, last bullet ("Planting a violation to prove a control fires is a write into the working tree... Plant in a copy where the shape allows it, and when it must be in place, snapshot first and restore...") — partially covers: it isolates the plant (input) and the restore, but says nothing about the control's own execution writing into a live artifact, nor about asserting the real artifact unchanged after the control fails.

**Placement:** guides/verification-discipline.md §Deriving the case space — extend the existing planting/snapshot bullet with an output-side clause

**Why (strength):** Single independent session (claude:dc1413c3); no other candidate in the file carries the failure-path-side-effect point (the 15 other self-test/control candidates concern mutation validity, wiring, or crash-as-coverage). Materiality is real — a control that records a bogus entry in an append-only ledger on failure is a rare-high-cost pollution of a provenance artifact, and the baseline's planting bullet already establishes the adjacent concern, so the extension is a one-clause addition rather than a new rule. General form is clear (any write-capable gate under self-test), but with one anecdote it earns a guide extension, not a global bullet.


### A missing `timeout` binary on macOS yields empty output, not an error

`partial` · strength 2 · 1 session `claude:1e1a7cef` · ④recur-err

**Rule:** When a command is run through a prefix wrapper (a timeout/limit/env-setting command placed before the real command), the wrapper's absence on the host — GNU coreutils names are routinely missing or renamed on BSD-derived systems — means the wrapped command never ran, and the failure surfaces as empty output rather than an error you would notice. Before reading an empty result from a wrapped invocation as "no data", confirm the wrapper itself resolves (`command -v` / `type -a`), and prefer a bound the tool provides natively or a portable interpreter-level alarm over a wrapper that may not be installed. This extends the command-resolution rule from "shadowed" to "absent": a shadowed name and a missing name both produce silent emptiness, and the check is the same.

**vs baseline:** guides/tooling-gotchas.md §Ambient state drifts — pin it, "Command resolution" bullet (partially covers: it names a same-named package shadowing a system tool with silent empty output and says to confirm the resolved target; it does not name the wrapper-absent-entirely case nor the GNU-vs-BSD portability cause). The guide's core rule "treat surprising empty output as a tool artifact hypothesis before a world fact" also covers the generic stance.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (extend the "Command resolution" bullet)

**Why (strength):** One session (claude:1e1a7cef) with one misread empty probe; cost was a wasted call and a wrong interim inference, not a rollback or high-cost failure. The general principle (empty output is a tool-artifact hypothesis; confirm command resolution) is already in the baseline, so only the "prefix wrapper absent on non-GNU hosts" instance is new. Worth a clause on the existing bullet, not a new bullet or a global rule.


### Classify simultaneous gate failures as root vs derived before fixing each

`partial` · strength 2 · 1 session `claude:886c19a3` · ①hi-tok ⑥quality

**Rule:** When several checks fail in the same run, do not work them as independent items until you have mapped the dependency among the checks themselves: an umbrella or verify step that re-invokes sibling gates, a suite that shells out to another gate, a projection check that reads an artifact another failing check generates. Fix first the failure that depends on none of the others, re-run the whole set, and treat only what still fails as a separate defect. A failure that clears without being touched was a cascade, not a fix — record which check depended on which so the next simultaneous red is triaged from the map instead of rediscovered. This governs triage order only; it does not license skipping the re-run of the full set after each fix.

**vs baseline:** coding-staged-workflow.md "Fix the cause at its authority, not the symptom where it shows" and §Stop Conditions (classify review findings as regression vs fresh instance of one root cause) — partially covers: both push toward root-cause thinking, but neither addresses the mechanical case where failing checks invoke or depend on each other, so a cascade of one defect reads as N independent work items. verification-discipline.md §When a green means nothing covers vacuous greens only, not correlated reds.

**Placement:** guides/verification-discipline.md — new short subsection "When several checks fail at once", placed immediately before §When a green means nothing

**Why (strength):** One independent session (claude:886c19a3); the cascade was noticed only after the fact, so materiality is real (wasted diagnosis of two derived failures, and the dependency between gates would have stayed invisible) but it is high_token/quality_lever, not rollback or rare-high-cost. The rule is clearly general — any repo with an umbrella gate or a verify step that re-runs siblings produces this shape — and the baseline has the root-cause principle but not the check-dependency trigger, so it extends rather than duplicates. Single-session support caps strength at 2.


### State the time horizon behind any 'cheapest/fastest' recommendation

`partial` · strength 2 · 1 session `claude:175397e3` · ②rollback ⑥quality

**Rule:** A cost, speed, or effort superlative ("cheapest", "fastest", "least work") is incomplete until its horizon is named: say whether it means finishing the work in hand now or the recurring per-unit cost going forward. When the ranking differs between horizons, present both rather than one — a choice that is cheapest on one horizon and dearest on the other is a decision for the user, not a conclusion to recommend. Applies to any recommendation framed as a superlative; a comparison already scoped to a single stated horizon needs no second one.

**vs baseline:** Global CLAUDE.md §Verification Discipline, the "fix a common basis — units, denominators, population, measurement surface" bullet: partially covers. It requires a shared basis for comparisons but names no temporal axis; §Decision Framing lists "time, cost, risk, reversibility" as option dimensions without requiring the horizon of a cost claim to be stated. Nothing in the guides names finish-now vs recurring horizon.

**Placement:** global CLAUDE.md §Verification Discipline — extend the existing comparison-basis bullet by adding "time horizon (finish-now vs recurring per-unit)" to the basis list and the clause "give both when the ranking differs by horizon"; no new bullet.

**Why (strength):** Single session of evidence (one independent session, one incident), so recurrence is unproven. Materiality is real but moderate: the agent's "cheapest" recommendation was reversed once the horizon was made explicit (a rollback of a stated conclusion, and a user had to ask twice), which is exactly the failure the basis bullet exists to prevent, so the gap in the baseline is genuine and the general form is clear. Extend rather than add: it fits as a named axis in an existing bullet, costing near-zero global budget.


### A one-case exemption stays in that case's log, with the user's reason, not your inferred one

`partial` · strength 2 · 1 session `claude:425138e6` · ②rollback

**Rule:** When the user exempts a single item from a standing procedure, record the exemption in that item's own record as a this-case-only exception and leave the standing procedure unchanged — edit the procedure only when the user says the rule itself changed. Record only the reason the user actually gave; if no reason was stated, write that it was not stated rather than an inferred motive, because an inference written in the record's voice reads later as the user's decision. Boundary: this governs how an instruction is recorded, not whether to comply — a stated general rule change is applied to the procedure as usual.

**vs baseline:** Partial. Global §Decision Framing ("treat user suggestions, prior diagnoses ... as hypotheses; re-derive load-bearing claims") and guides/documentation-hygiene.md ("History has its own address", "Writing rules people follow" — "State the assumption you are proceeding under") cover re-deriving claims and where records live, and review-request.md "Claim only what the evidence proves" covers attribution of findings. None address the two specific failures: promoting a one-off user instruction into the standing procedure, and recording an agent-inferred motive as the user's stated reason.

**Placement:** guides/documentation-hygiene.md §Where change history belongs

**Why (strength):** Single independent session (claude:425138e6), criterion ② rollback only — the runbook was left untouched after clarification and the case log re-marked, so materiality is low-moderate (a misattributed reason and an over-generalized rule would have misled later sessions, but the cost paid was one correction). The general form is real and absent from the baseline (scope-of-instruction and attribution-of-motive in records), which earns a guide-level extension rather than a global bullet; recurrence is not yet demonstrated, so strength 2.


### Find the latest handoff across all worktrees by birth time, not by filename or the current tree

`partial` · strength 2 · 1 session `claude:6a88fde8` · ③re-explore ⑤rare-hi-cost

**Rule:** When resuming in a repo that has (or may have) more than one worktree, locate the newest handoff before trusting any: enumerate every worktree and scratch location, include untracked files, and rank candidates by filesystem creation time rather than by a timestamp embedded in the filename or by what the current checkout happens to contain — the checkout and the filename are both claims, and the newest record is frequently uncommitted in a sibling tree. Where a superseded handoff was marked dead, the marking wins over recency; where none was, recency across all trees decides which one to verify against.

**vs baseline:** guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees ("Mark superseded worktrees/handoffs dead"; "After resume/clear/relocation, verify pwd, branch, and HEAD against the pinned handoff") and §Handoff Contract ("If pinned state fails or no trustworthy handoff exists, rebuild from source artifacts") — partially covers: the writer-side duty (mark dead) and the verify-against-handoff duty exist, but there is no reader-side procedure for discovering which handoff is newest when several worktrees exist, nor a warning that filename-embedded timestamps and the current tree are unreliable selectors.

**Placement:** guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees

**Why (strength):** One independent session (claude:6a88fde8). The gap is real — the baseline's protection relies entirely on the previous writer having marked superseded handoffs dead, and gives the resuming agent no discovery step across worktrees or for untracked files — so this is a genuine extension, not a restatement. Materiality is moderate: the cost was three user re-prompts and resumption against a one-commit-stale handoff, not lost work. Single-session recurrence and moderate cost keep strength at 2; a guide bullet is proportionate, not a global rule.


### After renaming or splitting a styled element, verify visually — selector-keyed styles fail silently

`partial` · strength 2 · 1 session `claude:c6bca4ac` · ②rollback ⑥quality

**Rule:** Web/UI: when a change renames, splits, or moves an element that styles, tests, or behavior bind to by a string key (CSS class, selector, id, data attribute), the binding drops without any error and structural/DOM/geometry checks stay green while the element silently loses its styling; after such a change, render the affected screens and inspect them (or measure contrast/visibility programmatically) before calling it verified, and add a rendered-state assertion for that screen so the same miss cannot recur. Applies to any name-keyed binding a compiler cannot check; it does not apply where a typed reference would already fail the build.

**vs baseline:** verification-discipline.md §Verification Menus has no web/UI row at all; the only rendering-inspection advice is claude-prompting.md ("Render any visual artifact before finalizing; inspect layout, clipping, spacing, and missing content" — prompt-authoring context) and svg-visualization-guide.md (screenshot embedded SVG when layout matters). Concept-economy's Rename row ("every site, in one change") covers concept renames, not string-keyed style bindings. Partially covers the generic "render before finalizing"; omits the failure mode and the menu placement.

**Placement:** guides/verification-discipline.md §Verification Menus (new "Web/UI" row)

**Why (strength):** One independent session (claude:c6bca4ac) with concrete evidence: a full DOM/geometry suite passed while a split section rendered dark-on-dark text, caught only by the user's screenshot request — a real rollback and a user-visible quality miss. The mechanism (string-keyed bindings silently detaching on rename) is general and the menu genuinely lacks any UI row, so it earns a partial add; but single-session recurrence and moderate materiality (no rare-high-cost) keep strength low.


### Check credentials at the surface the runtime actually loads, not the interactive shell env

`partial` · strength 2 · 1 session `claude:cf311b2a` · ②rollback ③re-explore

**Rule:** Loading surface: before declaring a credential or config value "missing" or "present", identify the surface the target process actually reads it from — an env file sourced by a wrapper script, a secret mount, a config home, a launcher-injected environment — by reading the loader code or wrapper, then probe that surface and run the real command under the same composition the wrapper uses (source + export + command in one shell). The interactive shell's environment is evidence only when the process inherits it unchanged; an unset variable in your shell does not mean the runtime lacks it, and a set one does not mean the runtime sees it. Bounded to presence/absence judgments that gate a plan or a handoff claim; it does not license reading or echoing secret values.

**vs baseline:** guides/tooling-gotchas.md §Ambient state drifts — pin it (interpreter, command resolution, cloud CLI context, installed-is-not-running) — partially covers: same ambient-state class, but no bullet on config/credential loading surfaces. Global Tooling and Operational Safety line "confirm a config/env toggle reached a subprocess via a cheap artifact" and Decision Framing "handoff claims are hypotheses" are adjacent but neither says to probe the runtime's own loading path (env file / wrapper sourcing / secret mount) instead of the shell env.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (new bullet after "Installed is not running")

**Why (strength):** One independent session (claude:cf311b2a) with material cost — a handoff's top gate ("credentials missing") was wrong because the shell env was probed while a wrapper sourced a .env the code never loads itself, costing a re-exploration and a plan rollback. The general form (probe the loading surface the process uses) is clearly reusable across dotenv wrappers, secret mounts, and launcher-injected envs, and it fills a real gap in the ambient-state bullet list, but recurrence is a single session and no rare-high-cost or recurrent-error criterion applies, so it earns a guide bullet, not a global rule.


### Alternating success/failure on identical requests after enabling a feature is propagation, not a request bug

`partial` · strength 2 · 1 session `claude:fa97693e` · ④recur-err ⑥quality

**Rule:** Right after a server-side enablement (feature flag, entitlement, permission grant, traffic-split change), identical requests that flap between success and a policy/rollout error are the signature of a change still propagating across replicas or caches, not a defect in the request. Do not tune the request or loop retries: cap attempts at a handful, keep the one success as proof the path works, then wait or switch to a fallback path and re-probe later. Applies to managed services and gated APIs; it does not apply when the failures are identical and deterministic, which points at the request or the entitlement itself.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — 'A new revision is not live traffic' and 'Perimeter controls ... may serve a stale cached response' partially cover eventual consistency after a change, and global 'Never retry-storm a live rate limit' covers the retry side; no rule interprets a flapping success/error pattern as propagation or says what to do while it settles.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** Single session (one independent source), and in that session the agent already handled it correctly, so the materiality was low (three wasted calls, then a fallback). The general form is real and adjacent baseline bullets treat neighbouring cases (revision not live, stale cache) without naming the flapping signature, so it earns a one-bullet extension of that section rather than a global rule. Not too_specific: the trigger (server-side toggle) and the signal (alternating identical requests) are invariant across providers.


### A read endpoint that flips state is a write — no GET, no machine tokens on admin exports

`partial` · strength 2 · 1 session `claude:8cd559df` · ⑥quality ⑤rare-hi-cost

**Rule:** Classify a route by what it changes, not by what it is called: any request that mutates stored state — including a "read" that marks rows as consumed, exported, or seen — is a write, so it must use a non-safe HTTP method with CSRF protection rather than GET. Separate credential classes by audience: a route intended for a human operator (admin views, exports, approvals) accepts only the human session credential and rejects automation, hook, or service tokens even when those tokens are otherwise valid for the service, so a leaked machine token cannot dump or drive human-only surfaces. Applies to any HTTP service or tool endpoint that both reads and records; a pure read with no state change may stay GET.

**vs baseline:** guides/llm-capability-boundary-patterns.md §Security And Side Effects — partially covers: "Use least privilege for tools and routes" and "Classify side effects: read-only, reversible write, ..." state the intent, but neither the HTTP-method-follows-side-effect rule (a state-flipping read is not a safe method) nor the audience-bound credential rule (human-only routes reject machine tokens) is stated.

**Placement:** guides/llm-capability-boundary-patterns.md §Security And Side Effects (extend the "Use least privilege for tools and routes" and "Classify side effects" bullets with the two concrete shapes)

**Why (strength):** One independent session only (claude:8cd559df), but it carries two distinct adversarial-review findings (leaked hook token dumping data; CSRF-able GET with side effect) that were folded into implementation with route tests, so materiality is high (data exfiltration / unauthenticated state mutation). The rule has a clearly general form beyond the export feature, and the baseline states only the abstract intent, so it earns a two-clause extension of the existing bullets rather than a new section or a global bullet. Single-session recurrence and the fact that it is standard web-security practice keep strength low.


### Source-identical does not mean artifact-identical: never plan a release on assumed digest reuse

`partial` · strength 2 · 1 session `claude:3cafbf95` · ⑤rare-hi-cost ②rollback

**Rule:** Treat every rebuild as a new artifact until its digest is measured: never gate a release plan, manifest, secret binding, or rollback pointer on a rebuild reproducing a prior digest, even when the source archive is byte-identical, because build stamps and toolchain metadata change the output. Author manifests and deploy references from the digest actually built and attested, and record the previous attested digest as the explicit rollback target. Applies to any content-addressed build output (container images, signed bundles, installers); it does not apply where the pipeline has a proven reproducible-build guarantee that is itself verified on the same run.

**vs baseline:** guides/verification-discipline.md §Verification Menus, "Release or distribution" bullet — covers digest-verifying published objects against the staging original per channel, but says nothing about assuming a rebuild reuses a prior digest or about deriving manifests/rollback pointers from the attested digest. Global "Ambient state drifts silently... pin it explicitly" (Tooling and Operational Safety) is adjacent in spirit (do not trust an assumed identity) but does not name build reproducibility. Partially covers.

**Placement:** guides/verification-discipline.md §Verification Menus — extend the "Release or distribution" bullet

**Why (strength):** One independent session (claude:3cafbf95) only, so recurrence is weak; but materiality is real — the assumption failed a determinism gate and forced the whole release plan (build manifest, secrets, deploy manifest, rollback pointer) to be re-authored, and the failure mode is a classic rare-high-cost release trap with a clean general form. The baseline's release bullet verifies digests after publish but is silent on the pre-publish assumption, so an extension is warranted rather than a new rule; strength stays at 2 until a second session recurs.


### Classify an improvement request as missing capability vs undiscoverable capability before designing code

`partial` · strength 2 · 1 session `claude:e4d33070` · ⑥quality ②rollback

**Rule:** When a request reports a gap in a tool or feature ("it cannot do X", "it errors on Y"), locate the capability in the code before designing a fix and classify the gap as one of three: absent, present but undiscoverable from the description/error/examples the caller reads, or owned by another component than the one blamed. Only the first calls for new behavior; for the second the change is the tool description, error text, or example, and for the third the fix moves to the owning component. Applies to any request whose premise is that behavior is missing; it does not license skipping a real fix when inspection confirms the capability is actually absent.

**vs baseline:** global CLAUDE.md §Decision Framing ("Treat user suggestions, inherited premises, prior diagnoses ... as hypotheses; re-derive each load-bearing claim from real code") and guides/coding-staged-workflow.md §Making the change ("For a bug, reproduce before you fix") — partially cover: both demand verifying the premise, but neither names the outcome split (absent / undiscoverable / misattributed) nor that an undiscoverable capability is fixed in the prose the caller reads rather than in code.

**Placement:** guides/coding-staged-workflow.md §Making the change (new bold paragraph after "For a bug, reproduce before you fix")

**Why (strength):** One independent session (claude:e4d33070). Materiality is real but moderate: three of five requested fixes had wrong premises, and classifying them turned planned code changes into description/error-text edits, which is a quality lever and avoided rework. The general form is clear and the baseline's "verify the premise" rule stops short of telling the agent what to do with the answer, so it extends rather than duplicates. The member's trailing clause about tests that hash descriptions is repo-specific and dropped. Single-session evidence caps strength at 2.


### Provider quota counters undercount; instrument the calls yourself

`partial` · strength 2 · 1 session `claude:9c08f554` · ⑥quality ②rollback

**Rule:** A managed provider's usage or quota counter is a billing artifact, not a request count: edge caches, coalescing, and exemptions make it skip calls you actually issued. When a decision (rate budget, cost, batch sizing) depends on how many calls a run makes, count them at the call site with a thin counting wrapper around the client, and before trusting any provider-side counter at all, calibrate it with a known-N probe (issue exactly N identical calls, read the delta) — a delta below N means the counter is not the instrument. Boundary: this is about measuring call volume; it does not replace the counter for what it is authoritative on (whether the provider will refuse the next call).

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services, bullet "Perimeter controls need the enforcement point's own logs" (agent-side fetch has opaque caching path) and the AI-workbench criterion's "run the instrument against an input whose answer is known to be the opposite" in verification-discipline.md, plus the global "fix a common basis — measurement surface" rule — together they cover the general instrument-calibration stance but never state that a provider consumption counter undercounts requests or that call-site counting is the measurement of record: partially covers.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services — new bullet immediately after "Perimeter controls need the enforcement point's own logs"

**Why (strength):** One independent session (claude:9c08f554) with a clean measured control (10 calls → delta 5), so the mechanism is real and generalizes to any cached/CDN-fronted API; but single-session recurrence, moderate materiality (a wrong rate-cost estimate, reversed in-session), and the calibration stance already exists in general form, so it earns only a guide bullet extending an existing cluster, not a global rule.


### Numbers entering a design must come from a committed, re-runnable instrument

`partial` · strength 2 · 1 session `claude:437e48ce` · ③re-explore

**Rule:** When a measured figure enters a design, decision record, or handoff, produce it with an instrument that is committed alongside the record and record the exact invocation next to the number; a figure from an uncommitted ad-hoc probe cannot be reproduced, so the next reader has to rebuild the probe and calibrate it against the old figure before trusting either. This applies to figures a later decision will be compared against; a throwaway reading used once and never cited needs no instrument.

**vs baseline:** documentation-hygiene.md §History has its own address ("give the reader the command that re-derives them instead of a number someone typed") and verification-discipline.md §Deriving the case space ("Record the verdict, do not type it") partially cover this: both demand a re-derivation command / stored real output, but neither states that the instrument itself must be committed so the command still exists for the next session. Global CLAUDE.md §Documentation Hygiene / §Verification Discipline (re-derive load-bearing claims; fix a common basis) cover the reader side, not the producer side.

**Placement:** guides/documentation-hygiene.md §History has its own address — extend the "give the reader the command that re-derives them" sentence with: the command must invoke a committed instrument, not a script that lived only in one session.

**Why (strength):** Single independent session (claude:437e48ce), criterion re_exploration only — no rollback or high-cost failure, just rebuilt-probe rework plus a calibration control. The delta over baseline is narrow but real (committed instrument vs. merely "a command"), so it earns a one-clause extension of an existing bullet rather than a new rule or global placement.


### Write an operator manual from the reader's pinned identity and state

`partial` · strength 2 · 1 session `claude:e3d2db31` · ②rollback

**Rule:** When writing step-by-step operating instructions for one known person (a runbook, a setup manual, a hand-off of a task to a specific operator), first pin the reader's state — who they are, which account or environment they will act from, and what access they already hold — and write every step from that single state: drop branches for conditions the reader will not be in, pre-fill any value you can obtain yourself rather than instructing them to go ask for it, and address the reader directly in the voice the sender would use. Applies only when the addressee is a specific person whose state is knowable; instructions for an unknown or general audience keep their branches and conditions.

**vs baseline:** guides/documentation-hygiene.md §Writing rules people follow — partially covers (positive phrasing, trigger, cost) but only for rules, not procedures written for one named operator; Decision Framing (outcome terms, translate jargon) covers reader-facing explanation, not pinning the reader's state.

**Placement:** guides/documentation-hygiene.md §Writing rules people follow (extend with a short "Instructions for a named operator" subsection)

**Why (strength):** Single session (one independent tag), evidence is a series of user corrections on one deliverable (②rollback only), no high-cost consequence. The behavior is general beyond that session — any manual addressed to a known reader — and the baseline has no rule about writing from a pinned reader state, so it extends rather than duplicates; but recurrence is unproven, so strength stays low and placement is a guide subsection, never global.


### Mutation controls anchored to code text go stale silently when the code they target is replaced

`partial` · strength 2 · 1 session `claude:c946a36f` · ②rollback ⑥quality

**Rule:** A planted-mutation or negative control that locates its target by a literal code fragment stops testing the moment that fragment is refactored away, and the suite reports nothing about it. Whenever guarded code is refactored, or before counting a final green after a multi-round fix loop, re-derive each probe's anchor (by symbol or structural position, never by string match), require the harness to fail loudly when a mutation does not apply, and re-run the control before trusting the green. Applies to any hand-authored probe that edits or matches source text; a control whose subject is enumerated from the artifact is already covered by the empty-subject rule.

**vs baseline:** verification-discipline.md §When a green means nothing — lists five shapes including "the control that went quiet" (a control indexing a live list that empties) and the revert-the-fix discipline; cli-multi-model-workflow anchors handoff *citations* by symbol not line. Neither names a mutation/negative control keyed on literal code text that a refactor removed, so the stale-anchor shape is absent. The second half of the candidate (aim a reviewer at the previous round's fix delta) is largely covered by coding-staged-workflow's regression-vs-instance classification rule, so it is dropped from the principle.

**Placement:** guides/verification-discipline.md §When a green means nothing — a sixth shape, "the anchor that no longer matches", inserted after "The control that went quiet"

**Why (strength):** Single independent session (claude:c946a36f), but the failure mode is general to any text-anchored probe and was material there (two controls silently inert at final verification of a seven-round loop). The existing revert discipline does not catch it — an unapplied mutation leaves the code unmutated, so the check passes and the revert test also passes — which makes it a distinct shape rather than a restatement. Strength held to 2 for lack of recurrence.


### A third-party validator only offloads a verification burden if it checks the surface where your breakages occur

`partial` · strength 2 · 1 session `claude:250d838a` · ②rollback ⑥quality

**Rule:** Before adopting an external artifact (SDK, schema package, contract-test suite, upstream validator) on the premise that it will absorb a verification burden you carry, establish two facts empirically rather than from its README: which side of the integration boundary its checks actually exercise (your outbound output, or the upstream behavior whose changes are what break you), and whether anyone runs those checks automatically on the cadence of the change you fear (CI on upstream release, not hand-run smoke checks). A validator on the wrong side of the boundary, or one nobody runs, transfers no burden — do not adopt it for that goal. It may still earn a place as a narrower regression net; if so, name that residual purpose separately from the original goal so the unmet goal stays visible. Applies to dependency adoption motivated by verification offload; ordinary feature dependencies are out of scope.

**vs baseline:** Global CLAUDE.md §Decision Framing (user suggestions and premises are hypotheses; re-derive from real code) and §Tooling and Operational Safety (confirm dependency capability empirically against the installed artifact) partially cover it; guides/verification-discipline.md §Proportion the depth before you spend and §When a green means nothing cover instrument validity but say nothing about delegating verification to a dependency — the two specific questions (which side of the boundary, who runs it) are absent.

**Placement:** guides/verification-discipline.md §Proportion the depth before you spend

**Why (strength):** One independent session (claude:250d838a) supports it; the general shape (premise as hypothesis, empirical capability check) is already in the baseline, so the increment is the two concrete questions. Materiality is moderate: the session reversed a proposed dependency adoption and one subagent finding, avoiding a dependency added for a purpose it could not serve, but no rare-high-cost or recurrent-error evidence. Survives as partial because the failure mode (offloading verification to a validator on the wrong side of the boundary, run by hand) is general and non-obvious, but a single anecdote caps strength at 2.


### A rehearsal validates only the constraints its case exercises; pick the case that hits the hard one

`partial` · strength 2 · 1 session `claude:08503f68` · ②rollback ①hi-tok

**Rule:** When a plan for a multi-step change (a staged extraction, a migration order, a dependency-ordered rollout) is validated by rehearsing it on one instance first, choose the instance that exercises the constraint the plan could get wrong — the one with the most cross-dependencies or the tightest ordering rule — never the instance that satisfies the constraint trivially (a leaf, an isolated module, a case with no dependents). A rehearsal that passes on a trivial case has confirmed only the mechanics, not the plan; treat the constraint as unverified until a case that could have violated it has been run. This applies to pilot runs, dry runs, and "try it on one first" checks; it does not replace the per-change verification menu, which still runs on the real change.

**vs baseline:** guides/verification-discipline.md — §Verification Menus ("narrowest = the smallest test that would fail if the change were wrong") and §Deriving the case space ("prefer a signal that fails when the mechanism is wrong — a negative or contrast control") state the general falsifiability principle; neither names the pilot/rehearsal situation nor says how to select the rehearsal instance for a staged plan, so the trigger is uncovered while the underlying idea is present. Partially covers.

**Placement:** guides/verification-discipline.md §Deriving the case space (new bullet, after "Make the criterion falsifiable before you make it green")

**Why (strength):** One session only (claude:08503f68), so no recurrence; materiality is real (a wrong four-stage order passed all three verification layers and cost a rollback plus the token spend of the rehearsal), and the general form — rehearsal-case selection for ordered plans — is a recognizable, recurring situation that the baseline's falsifiability rule does not name. The candidate's second half (exclude the node that references everything when computing "shared" from usage counts) is a one-off root cause from that session's specific planner and is dropped as too specific.


### Flags shared by two pipeline stages flip as a unit; tests of protective defaults must declare their mode

`partial` · strength 2 · 1 session `claude:04d26700` · ⑤rare-hi-cost ②rollback

**Rule:** When one mode flag (a default-off/opt-in switch, a strictness level, an environment mode) is read by more than one stage of a pipeline, it is a single setting: flip it at every reading site in one change and add a cheap check that refuses a configuration where one stage assumes the flag on and a neighbour assumes it off, since a half-flipped chain fails only at the seam between stages. When raising a protective default that real scripts honour, run the suite from a non-clean working state before landing it: any test that invokes the real script must pin its mode explicitly rather than inherit the default, or the stricter default turns every ordinary development state red. This applies to flags with more than one reader and to tests that traverse the real path; a single-reader flag or a mocked path needs neither.

**vs baseline:** Global CLAUDE.md §Coding Guidelines default-off/opt-in bullet covers landing behind a flag but not multi-reader coupling or a half-flip check; §Tooling and Operational Safety 'pin ambient state explicitly' covers pinning in spirit but not test mode declaration against a raised default; concept-economy 'Rename: every site, in one change — a half-rename is strictly worse' is the nearest analogue for the unit-flip half. Partially covered.

**Placement:** guides/coding-staged-workflow.md §Making the change (adjacent to the default-off/opt-in landing guidance, as an extension of the global bullet)

**Why (strength):** One independent session (claude:04d26700) with concrete evidence: a half-flipped shared flag broke deployment and six real-script tests went red on any dirty tree until modes were pinned. Materiality is real (deployment breakage, rollback-class cost) but recurrence is single-session and two of the three ideas have near-analogues already in the baseline (default-off bullet, ambient-state pinning, half-rename rule), so it earns a guide-level extension rather than a global bullet.


### A fix that adds a new failure path must map it into the contract's closed failure vocabulary

`partial` · strength 2 · 1 session `claude:d4ed80e9` · ②rollback ⑥quality

**Rule:** When a result surface exposes a closed set of failure reasons that callers branch on, every new place a change can fail — especially an I/O, re-read, or lookup site introduced by a fix — must be classified into that set before the change is done; a raw exception or host error escaping past the closed vocabulary is a contract break for every exhaustive reader, not an implementation detail. Enumerate the diff's new throw sites and check each against the set, the same way a new value added to the set obliges every reader. This applies to closed failure/result vocabularies only; free-form error surfaces carry no such obligation.

**vs baseline:** guides/concept-economy.md §Reuse The Vocabulary Before Adding To It — partially covers: it treats failure kinds as high-blast-radius closed sets and governs ADDING a value; it says nothing about the inverse, an unclassified error escaping the set. llm-capability-boundary.md's checklist ("fail-loud checks for unknown fields", "retry/fail policy by failure kind") and global §LLM And Capability Boundary "fail clearly" are adjacent but do not name new throw sites introduced by a fix.

**Placement:** guides/concept-economy.md §Reuse The Vocabulary Before Adding To It

**Why (strength):** One independent session (claude:d4ed80e9), self-reported confidence 0.6. Materiality is real — the fix itself introduced a contract violation caught only by a main-side probe (rollback criterion) — and the form is general (closed failure vocabulary + new throw site). But recurrence is single-session, so it earns an extension of the existing failure-vocabulary paragraph, not a global bullet. The candidate's second clause (a time-keyed guard needs a backwards-clock test) is a separate, thinner anecdote already subsumed by verification-discipline §Deriving the case space ("derive from failure modes") and is dropped from the principle.


### Confirm which repository a forge CLI resolved before reading state through it

`partial` · strength 2 · 1 session `claude:01abd65f` · ②rollback

**Rule:** A forge CLI (gh/glab-style) chooses its target repository from the checkout's git remotes, and when more than one remote exists (origin plus upstream, fork plus canonical) that choice is silent and may not be the repository being worked on. Before reading workflow runs, PR state, checks, or settings through it — and before any conclusion about what merging or pushing will trigger — print which repository it resolved to, and pin the repository explicitly (`--repo`/equivalent) on every call whose answer feeds a decision. Does not apply to a single-remote checkout, but a fresh fork or an added upstream remote re-triggers it.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety "Ambient state drifts silently — pin it" covers the principle generically; guides/tooling-gotchas.md §Ambient state drifts — pin it enumerates Interpreter, Command resolution, Cloud CLI context (gcloud/aws/kubectl/terraform), Installed-is-not-running — a forge CLI's multi-remote repository resolution is not among the instances. Partially covers.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (new bullet "Forge CLI repository resolution", alongside "Cloud CLI context"); no global change

**Why (strength):** One independent session (claude:01abd65f). Materiality is moderate: the agent asserted that a merge would push a production image, then retracted after discovering the workflow status belonged to the upstream repository — a wrong load-bearing claim reaching the user, but caught before any irreversible action. The general rule already exists in the global; only the concrete instance (multi-remote forge resolution) is missing from the guide's enumeration, and it is a genuinely general trap for any fork-based workflow, so it earns a guide bullet rather than a global rule. Single-session evidence keeps strength low.


### Check the provenance and freshness of any artifact a reviewer or subagent cites as evidence

`partial` · strength 2 · 1 session `claude:5761c05e` · ②rollback ⑤rare-hi-cost

**Rule:** When a finding, rebuttal, or verifier verdict rests on a file or artifact, identify the exact instance it was read from — path, origin, and whether it is the live source or a copy in a scratch, cache, or prior-session location — before accepting or adjudicating it. Two analysts disagreeing is often two artifact instances disagreeing: when a rebuttal contradicts a finding, confirm both read the same current instance before judging either on its merits, and treat a claim derived from a stale copy as unverified rather than wrong. When composing a review packet, name the target instance (path and how it was obtained) so a reviewer cannot silently substitute an older copy. This does not require re-fetching every artifact on every read — only the instance a load-bearing claim or a contested verdict depends on.

**vs baseline:** Partial. Global CLAUDE.md §Decision Framing ("treat reviewer findings ... as hypotheses; re-derive each load-bearing claim from real code or data") covers re-derivation but not which artifact instance to re-derive from. cli-multi-model-workflow.md §Halt And Resume covers fingerprint-matching artifacts on resume and treats tool-managed temp locations as ephemeral, but only for resumption, not for evidence cited in a review. §Verification Discipline "fix a common basis before comparing" is about units/denominators, not artifact identity. review-request.md §"Say what the target is, and what absence means" names the stage but not the target instance. No baseline rule says: when a finding and its rebuttal disagree, check that both read the same current artifact instance.

**Placement:** guides/review-request.md §Say what the target is, and what absence means

**Why (strength):** Single independent session (one cluster member), so recurrence is weak. Materiality is real: a recheck agent's rebuttal was accepted on a stale scratchpad copy from a prior session and had to be withdrawn once pointed at the freshly downloaded production artifact (rollback of a verdict; rare but costly when a review verdict decides what ships). The general form is clear and the baseline addresses the surrounding pieces (hypotheses, ephemeral temp paths, resume fingerprints) without stating the artifact-identity check as a precondition for adjudicating disagreeing reviewers, so it earns a scoped extension of an existing guide section rather than a global bullet.


### Enumerate deployed fallback and regeneration switches before a live rerun on the artifact under test

`partial` · strength 2 · 1 session `claude:5761c05e` · ⑤rare-hi-cost

**Rule:** Live rerun to observe one stage: before spending a paid or unrepeatable run whose purpose is to observe a single stage or artifact, enumerate every deployed fallback, regeneration, or auto-repair switch that can fire on a failure along the path, the failure classes that trip each, and whether firing discards or rewrites the artifact under observation. Disable or scope the ones that would overwrite the subject, or snapshot it first and state up front that the run may end up testing the fallback rather than the stage. Applies to reruns against deployed pipelines with automatic recovery; a run whose purpose is to exercise the recovery path itself is exempt.

**vs baseline:** verification-discipline.md §Verification Menus — "A/B or on/off measurements … an unconditional upstream step can silently apply the treatment to both arms" and "Irreversible capture switches" (partial: covers confounding steps and pre-enable proof, not enumerating already-enabled recovery switches that can destroy the artifact under test); global CLAUDE.md §Tooling and Operational Safety "snapshot the last good state before any in-place resume or overwrite of a completed run" (partial: snapshot, but no enumeration of what triggers the overwrite); §review-request "Defect: … a silent fallback" (names the failure shape, not the pre-run step).

**Placement:** guides/verification-discipline.md §Verification Menus — new bullet adjacent to "A/B or on/off measurements" and "Irreversible capture switches"

**Why (strength):** Single session (one independent source), so recurrence is nil; materiality is real (rare_high_cost: a paid live run wasted and the artifact under test deleted, after a prior warning had named the switch). The baseline already gestures at the shape (silent fallback as defect, confounding upstream steps in A/B, snapshot before overwrite) but nowhere states the concrete pre-run step of listing enabled recovery switches and their trip conditions — hence partial, low strength pending recurrence.


### A behavior change that breaks zero existing tests is evidence the surface is uncovered

`partial` · strength 2 · 1 session `claude:144dc725` · ⑥quality

**Rule:** When you intentionally change observable behavior and the existing suite stays green, treat the green as a coverage gap rather than confirmation: no test observed that behavior at any surface. Find why the nearest tests still pass (coincidental data, tie-break, mocked or bypassed path, a comment now false), add a test at the real surface that encodes the new semantics, and prove it by restoring the old behavior and watching the new test fail. Applies to deliberate semantic changes; a pure refactor that keeps behavior is expected to stay green and is not this case.

**vs baseline:** guides/verification-discipline.md §When a green means nothing — partially covers: it lists five shapes of vacuous green and the discipline "revert the fix and watch the check fail" for a check you added, and the review-request criterion goldens classify "no test catches a one-line flip of this default" as coverage_gap. Neither names the trigger from the other direction: an intentional behavior change that no existing test notices.

**Placement:** guides/verification-discipline.md §When a green means nothing — add as a sixth shape ("The change nothing noticed") and extend the closing revert sentence to cover it

**Why (strength):** One independent session (claude:144dc725), quality_lever only, no rollback or high-cost incident; the general form is clear and fits an existing list as one bullet, but the closing revert discipline of that section already gets an agent most of the way there, so the addition is a named trigger rather than new behavior.


### Assert structural invariants of an authored graph mechanically — connectivity, edgeless nodes, and stated-count vs enumerated-member identities — because prose and visual inspection read as coherent regardless of whether the edges were ever authored.

`partial` · strength 2 · 1 session `claude:160ac08b` · ⑥quality

**Rule:** When an artifact is an authored graph or map (an ontology, dependency map, service blueprint, or similar node-and-edge structure), do not accept coherent prose or a clean visual render as evidence that the structure is sound. Compute its structural invariants mechanically — connected components, nodes with no edge to the body, and equality between every stated total and the enumerated members it summarises — and have the artifact or a gate assert them, failing on a violation. A graph that splits into islands or whose counts disagree with its enumeration is reporting edges or members that were never authored; the check is deterministic, so it belongs to tools/code, while deciding whether a found island is a defect or an intended boundary remains a judgement.

**vs baseline:** Partially covers. verification-discipline.md §The static floor names "graph validation" and §Verification Menus lists "Ontology: static graph checks" — labels only, with no statement of which invariants to compute (connectivity, orphan nodes, count identities) or that a render/prose reading is insufficient. svg-visualization-guide.md §Verification checks only layout hygiene (overlap, arrows, colours). concept-economy.md §Derived Values Stay Derived covers the count-identity half in principle (a stated total is a derived value that should be computed), but not as a graph-verification step.

**Placement:** guides/verification-discipline.md §Verification Menus — extend the "Ontology:" line (static graph checks) to name the invariants: connected components, edgeless nodes, stated-count vs enumerated-member identity, asserted by the artifact or a gate; optionally a one-line cross-reference from svg-visualization-guide.md §Verification stating that layout checks do not verify structure.

**Why (strength):** One independent session (claude:160ac08b) with a concrete measured instance: 7 of 35 entities in three disconnected components and a stated count of 9 vs an enumerated 10, both invisible to prose review and all gates and surfaced only once computed. Materiality is moderate (quality lever, a wrong dependency map misleads later decisions) but no rollback, recurrent-error, or rare-high-cost criterion is attached, and the baseline already names "static graph checks" — so this is a sharpening of an existing menu line, not a new rule. Not too_specific: connectivity and count-identity apply to any authored graph. Not weak: the evidence is concrete and computed, just single-session.


### Derived documents from auto-transcripts: re-attribute speakers by context, keep process meta out of the deliverable

`partial` · strength 2 · 1 session `claude:982ca800` · ②rollback ⑥quality

**Rule:** When producing a reader-facing document derived from a source record — an automatic meeting transcript, a chat log, a recording — treat the source's speaker labels and segment boundaries as hypotheses, not facts: automatic transcription splits sentences across speaker turns and mislabels fragments, so re-attribute each quoted or summarized statement by context against the raw source before ascribing it to anyone. Ship only the subject's content in the deliverable, shaped as the argument actually developed, with headings that state claims; put the method, attribution judgments, exclusion criteria, and source pointers in a separate execution log or provenance note rather than in the document the reader receives. Applies to prose deliverables derived from a primary source; it does not license dropping provenance — the log must exist, just at a different address.

**vs baseline:** guides/documentation-hygiene.md §The two addresses / §History has its own address — covers separating present-state prose from history and process for code/repo docs, but not reader-facing documents derived from a source; claude-prompting.md "Keep the deliverable readable: lead with the outcome; drop the working shorthand" touches the meta-out-of-deliverable half for final messages only. Speaker-label unreliability in automatic transcripts and re-attribution by context are absent.

**Placement:** guides/documentation-hygiene.md §The two addresses (new subsection: "Documents derived from a source record")

**Why (strength):** One independent session (claude:982ca800) with a real user rollback (two corrections, full second draft), so materiality is moderate; but no recurrence, and the meta-separation half already has a near neighbor in the two-addresses rule. The transcript speaker-attribution half is genuinely novel and general (any auto-transcribed source), which keeps it above weak/too_specific. Guide placement, not global — its failure mode is recognition-bound and procedural.


### A local gate failing on untracked/gitignored detritus is not a release blocker; rerun on the shipped subject set

`partial` · strength 2 · 1 session `claude:8292adf6` · ⑥quality ③re-explore

**Rule:** When a gate fails locally but passes on a clean checkout (or CI), treat the disagreement as a subject-set question before treating it as a defect: enumerate the failing subjects and check whether each is tracked and shipped. If the failures are confined to untracked or ignored working-tree residue, re-run the gate on a clean materialization of the index or a fresh worktree, and confirm the packaged artifact by inspecting its actual contents (a dry-run pack or equivalent listing) rather than the working directory. A gate that scans more than the shipped set produces false reds the same way one that scans less produces false greens; neither is fixed by editing the gate's scope to match the mood of the run — decide explicitly whether the residue is a real product risk (then fix the packaging boundary) or noise (then report the clean-subject result as the verdict and say what was excluded).

**vs baseline:** guides/verification-discipline.md §When a green means nothing — covers the inverse (false greens from an empty or unscanned subject) and demands asserting the subject set; guides/review-request.md and tooling-gotchas cover untracked files being *omitted* from diffs. Nothing states the false-red case: a local gate over-scanning untracked/ignored residue and how to attribute a local-vs-CI disagreement to subject-set mismatch. Partial.

**Placement:** guides/verification-discipline.md §When a green means nothing (add a sibling bullet "When a red means nothing: the over-scanned subject" and extend the closing discipline to "dump what it ran over, in both directions")

**Why (strength):** One supporting session (claude:8292adf6), self-rated 0.45; the fix was cheap and reversible, so materiality is moderate — the cost it avoids is a wrongly blocked release or, worse, a reflexive edit to the gate's scope. The principle is general (any gate whose file set is the working tree rather than the index/tarball) and cleanly extends an existing section, so it earns a guide bullet, not a global rule. The candidate's second clause (open a dependent PR as draft so ordering is surface-enforced) is a separate lesson with a different trigger and is dropped from this cluster's principle; it would belong in coding-staged-workflow §Review Loop if it recurs.


### When finished work is floating unlanded, landing it outranks tidy-up that adds more float

`partial` · strength 2 · 1 session `claude:7964940c` · ⑥quality ②rollback

**Rule:** When ordering next steps in a repo that already holds completed-but-unlanded work (an unmerged branch, an approved design with no implementation, a finished piece awaiting review), rank landing that work above any new cleanup or hardening item, however cheap. Count the in-flight changes a plan leaves before and after it: an item that ships no outcome while raising that count adds merge and re-verification risk to everything already floating, so prefer the plan that lowers the count. This is an ordering rule, not a ban on cleanup — a cleanup that is itself a blocker for landing (a failing gate, a broken merge) is part of landing and goes first.

**vs baseline:** guides/coding-staged-workflow.md — §Stages (step 2 "ordered work plan with dependencies") and Default Frame "7 Close: no silently parked items"; guides/verification-discipline.md "Prefer shipping" (about proportioning assurance, not ordering); cli-multi-model-workflow "Re-integrate branches serially". Each touches shipping or parked work, none states that landing floating finished work is the first-ranked item and that new tidy-up increases the float — partially covers.

**Placement:** guides/coding-staged-workflow.md §Stages (as a bullet under stage 2, implementation-process design / ordering the work plan)

**Why (strength):** Single supporting session (one independent source, self-rated confidence 0.55), and the evidence is one reversed recommendation rather than a costly failure — so materiality is modest (a wrong ranking the user caught in one turn). The rule is general (any repo with unmerged/unimplemented finished work) and genuinely absent as an ordering principle, so it earns a guide bullet, not a global line: its failure mode is recognition (not noticing the float), which per the corpus's own placement rule belongs behind a pointer, not in the per-session budget.


### Cost signals an agent can observe: model tier and elapsed LLM time, never self-counted tokens

`partial` · strength 2 · 1 session `claude:94bc8568` · ⑥quality

**Rule:** When a rule, record, triage criterion, or decision needs a cost or effort signal that must be judged in-session, use only quantities the agent can observe: the model tier and effort in use, and elapsed time derived from action timestamps (time waiting on background work counts as work). Never ask an agent to count or estimate its own tokens — billed output is mostly hidden thinking, so any in-session token figure is a guess and a criterion built on it is undecidable; token and dollar accounting belongs to after-the-fact transcript tooling run against the recorded session.

**vs baseline:** cli-multi-model-workflow.md §Context Budget And Reset — "Measure rather than estimate: `agent-bios cost --context <transcript>`" — partially covers: it says measure context/cost from the transcript rather than estimating, but only for context-window budgeting, and nothing in the deployed corpus tells an agent which cost proxies are admissible when a rule, ledger, or triage axis needs a cost judgment in-session (tier × elapsed time) or why self-counted tokens are undecidable (hidden thinking dominates billed output). The hidden-thinking fact exists only in repo-local memory/AGENTS.md, not the payload.

**Placement:** guides/cli-multi-model-workflow.md §Context Budget And Reset (extend the "Measure rather than estimate" bullet with the in-session proxy rule)

**Why (strength):** One tagged session in the cluster (the evidence text cites a second session giving the same user direction, but it is not an independent member here, so recurrence is 1–2). Materiality is a quality lever only — no rollback or high-cost failure — but it closes a real gap: the baseline directs after-the-fact measurement yet leaves in-session cost criteria (used by spawn gates, decision records, and triage axes) without an observable basis, and the "billed output is mostly hidden thinking" fact that makes token self-estimation invalid is absent from the deployed corpus. General form is clear and bounded, so it survives as a one-bullet extension rather than a new rule.


### A successful auth handshake proves identity, not reach; enumerate what the identity can see before diagnosing a 403

`partial` · strength 2 · 1 session `claude:51e5ec70` · ②rollback ④recur-err

**Rule:** **Authenticated is not authorized**: a login, token exchange, or command registration that succeeds proves only that the credential is valid — it can succeed with access to nothing, because the membership/invite/grant step that binds the identity to a resource is separate from the handshake. When a first real call returns 403/forbidden after a clean handshake, enumerate what the authenticated identity can actually list or belongs to (guilds, projects, workspaces, buckets, channels) before diagnosing scopes, intents, or config; an empty enumeration means the grant step never completed, not that the scopes are wrong. Applies to any bot, service-account, or OAuth integration where identity and resource access are provisioned in separate steps; not to systems where authentication itself implies a resource binding.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — "A new revision is not live traffic" (success message ≠ effect) and global §Tooling and Operational Safety "treat a coarse runtime signal as a hypothesis; confirm against authoritative evidence" and "gate identity-tied actions on a live identity check" partially cover the shape; none separates handshake success from resource reach or names enumerate-what-it-can-see as the first 403 triage step.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services (new bullet beside "A new revision is not live traffic")

**Why (strength):** One independent session (claude:51e5ec70), criterion rollback only; materiality is moderate (a wasted diagnosis loop over scopes/intents, not a high-cost irreversible event). The pattern generalizes cleanly across bot/service-account/OAuth integrations where identity and grant are separate steps, and the baseline's nearest rules are about deploy effects and destructive-action identity checks, so it is a genuine but narrow gap — guide-level bullet, not global.


### Pre-register the expected reading before building the instrument that produces it

`partial` · strength 2 · 1 session `claude:bff266bb` · ⑥quality

**Rule:** When a measurement or check is being built because its reading will change a decision (adopt/reject, promote/roll back, pass/fail a gate), write down the expected reading and the decision rule before the instrument exists, then compare the real output against that record and explain any gap before acting on it — an instrument authored after its output is seen gets tuned to agree with it, and no known-opposite probe catches that. This is distinct from regression goldens, where recording what the real path returned remains the rule: pre-registration protects the decision, recorded verdicts protect against drift.

**vs baseline:** guides/verification-discipline.md §Deriving the case space — "Make the criterion falsifiable before you make it green" and the negative/contrast-control bullets partially cover this (falsifiability before green, controls that fire), and the AI-workbench menu's known-opposite probe covers instrument bugs; but none states the ordering safeguard — fix the expected value before the instrument exists so the check cannot be fitted to its own output. The adjacent bullet "Record the verdict, do not type it" points the other way for goldens, so the boundary between the two must be stated explicitly.

**Placement:** guides/verification-discipline.md §Deriving the case space — a bullet immediately after "Make the criterion falsifiable before you make it green", with the boundary against "Record the verdict, do not type it"

**Why (strength):** Single session (one claude tag) and only the quality_lever criterion; the evidence is the agent stating and following the practice, not a documented failure that pre-registration prevented, so materiality is asserted rather than measured. It survives as partial because the ordering guard (expectation fixed before the instrument is written) is genuinely absent from the baseline and is a general, cheap practice that complements the known-opposite probe rather than restating it; but with one anecdote and no observed cost of omission it earns a guide bullet at most, not a global rule.


### Multi-account browser: pin the acting account before creating anything account-bound

`partial` · strength 2 · 1 session `claude:b033d806` · ②rollback ⑤rare-hi-cost

**Rule:** When creating or configuring a long-lived, account-bound resource (a project, script, token, schedule, integration) through a browser or web console where more than one identity is signed in, read which account the page is acting as — the account index in the URL, the displayed email — and pin it before the first write; and re-check that identity before reporting success, because a resource that was created, saved, and even verified under the wrong account is a verified mistake that must be recreated, not a success. The bar for irreversible identity-tied actions (revoke, delete, grant, consent) is a live identity check; for creation the bar is the same check, done up front.

**vs baseline:** global CLAUDE.md §Tooling and Operational Safety — the destructive-actions bullet gates irreversible identity-tied actions (revoke, delete, grant, consent) on a live identity check and forbids auto-opening a browser for a non-default identity; the "Ambient state drifts — pin it" bullet and guides/tooling-gotchas.md §Ambient state drifts — pin it cover cloud CLI project/context but not the browser's acting account. Partially covers: the mechanism (identity check) exists, the trigger (resource creation in a multi-account browser session) is not named.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (add the signed-in browser account as one more ambient value to pin, with the account-index/URL and shown-email read as the pin); optionally extend the global CLAUDE.md §Tooling and Operational Safety identity-check bullet by adding "create" to the gated action list rather than adding a new bullet.

**Why (strength):** Single independent session (one supporting tag), so recurrence is weak. Materiality is real: the wrong-account resource was hash-verified and reported as done, then had to be rolled back and recreated (②rollback, ⑤rare-high-cost — a scheduled mail reader bound to the wrong mailbox is silent and costly). The general form is clear and not repo-specific: the signed-in account is ambient state exactly like a cloud CLI project, which the baseline already tells the agent to pin, so this extends an existing rule rather than adding a concept. Kept as partial with low strength; it belongs in the guide's ambient-state list, and a global-bullet change should be limited to widening the existing action list.


### Before creating a home for shared data, find where existing items live and whether the human already did it

`partial` · strength 2 · 1 session `claude:b033d806` · ②rollback

**Rule:** Before creating a new container (folder, sheet, project, bucket) for items of a kind that already exist in a shared workspace, locate where the current items of that kind actually live and adopt that location, ownership, and naming convention instead of inventing one; and when a person is working on the same data in parallel, re-read the live state immediately before each write so you do not duplicate work already done. Applies to shared external stores where a human can act between your read and your write; it does not apply to scratch or tool-owned locations you alone write.

**vs baseline:** guides/concept-economy.md §The Four Paths / Finding the nearest concept (reuse existing concept by default) and guides/documentation-hygiene.md §Where change history belongs ("prefer the established homes over inventing one per change") — both cover names and documents, not the physical home/convention of shared artifacts nor checking for parallel human changes before writing. Global §Tooling and Operational Safety covers ambient-state drift and diagnosing state before irreversible ops but not this trigger. Partially covers.

**Placement:** guides/tooling-gotchas.md §Ambient state drifts — pin it (new bullet: shared workspaces are live state — locate the existing home and re-read before writing)

**Why (strength):** Single session (one independent source) with a real rollback cost (six duplicate uploads and a wrong documented naming prefix that had to be cleaned up). The general form is genuine — "established home" reasoning exists in the baseline only for concepts and docs, and the parallel-human-write check is absent — so it earns a guide bullet, but one anecdote and moderate materiality cap the strength.


### Paste long or non-ASCII text into browser editors via clipboard; hash before paste and after reload

`partial` · strength 2 · 1 session `claude:b033d806` · ⑥quality ⑤rare-hi-cost

**Rule:** When large or non-ASCII content must land in a GUI or browser editor through automation, deliver it via the clipboard rather than simulated keystrokes (keystroke entry drops or splits multi-byte characters and is slow enough to be interrupted). Treat the clipboard as shared, user-mutable state: hash its contents immediately before the paste and abort if it no longer matches the source file. Confirm persistence against the server, not the editor buffer — reload the page and hash what comes back before reporting the content saved. Applies to any automated entry into a web or desktop editor; not to file-based or API-based writes, where the file or response body is the artifact to verify.

**vs baseline:** guides/tooling-gotchas.md §"Ambient state drifts — pin it" (partially covers: clipboard is an unnamed instance of drifting shared state) and §"Tool output is a rendering, not the bytes" (partially covers: editor buffer vs. persisted bytes); no browser/GUI content-entry entry exists anywhere in the baseline.

**Placement:** guides/tooling-gotchas.md §"Ambient state drifts — pin it" (new bullet: clipboard-fed GUI/browser editor entry)

**Why (strength):** One independent session only (claude:b033d806), so recurrence is unproven. Materiality is real: the clipboard was actually overwritten by the user mid-task and wrong content landed in the editor, a silent wrong-artifact failure that the reload-and-hash step caught — a rare-high-cost shape. The mechanism (keystroke entry mangles multi-byte text; clipboard is shared state; buffer is not persistence) is general to any browser/desktop automation, so it is not too specific. Extend the existing ambient-state section rather than adding a global rule; keep it as one bullet.


### One judgment per LLM call: isolated parallel auditors, binary verdict plus reason, verified synthesis

`partial` · strength 2 · 1 session `claude:cbf1879f` · ⑥quality

**Rule:** When an automated pipeline uses an LLM as a judge or auditor, give each call one question and a structured answer no richer than verdict plus reason, and run the judges isolated from each other in parallel rather than one prompt scoring many criteria. Where several judges' findings are merged into one requirement, the merge is itself an LLM step that can drop or distort items, so check it preserved every finding before acting on it; and hand the merged requirement to a separate isolated judge of the repair, never back to the auditors that raised the issues. Boundary: this governs judge topology inside a pipeline; it does not replace the constrained submit channel for the payload or the reviewer-kind independence ladder for human-facing review.

**vs baseline:** guides/llm-capability-boundary.md §Design Procedure and §Structured Output Field Assignment (constrained channel, runtime must not re-judge) partially cover; guides/review-request.md and verification-discipline.md cover isolated multi-lens review and reviewer independence, and review-request.md notes that survival measured by presence is vacuous. None states one question per judge call, the verdict+reason answer shape, that a synthesis/merge step needs its own fidelity check, or that the repair verifier must be a different isolated judge than the auditors.

**Placement:** guides/llm-capability-boundary.md §Design Procedure

**Why (strength):** Single supporting session (claude:cbf1879f), criterion quality_lever only — no rollback or rare-high-cost evidence. The judge-topology rules (one question per call, verdict+reason shape, verified merge, separate repair judge) are genuinely absent from the baseline and generalize to any LLM-judge pipeline, but isolation/parallelism and constrained output are already covered, so the extension is partial and its evidence thin.


### Retain raw LLM responses so downstream redesigns can be re-evaluated without re-spend

`partial` · strength 2 · 1 session `claude:e4c1c5ea` · ⑥quality

**Rule:** In any pipeline where a paid model call feeds deterministic downstream stages (projection, ranking, rendering, judging), persist each raw response verbatim alongside its prompt and request parameters as a durable pipeline artifact, not only the derived per-item outcome. When a downstream stage is redesigned or a defect is suspected there, rebuild from the stored responses and re-judge instead of re-running the paid stage — so the experiment is a free ablation rather than a spend decision. Boundary: this covers stages that consume model output deterministically; a change to the prompt or model itself still requires a fresh dispatch, and stored payloads follow the same durable-path and redaction rules as any other artifact.

**vs baseline:** guides/cli-multi-model-workflow.md §Unattended Batches ("Persist per-item outcome, token, and cost records for recalibration") and §Halt And Resume (resume-first from fingerprinted artifacts) — partially covers: it persists outcomes and cost records for resume/recalibration, but never says to keep the raw prompt+response payload so later layers can be re-evaluated without new calls.

**Placement:** guides/cli-multi-model-workflow.md §Unattended Batches — extend the "Persist per-item outcome, token, and cost records" bullet

**Why (strength):** One independent session (claude:e4c1c5ea) with concrete evidence: 109 stored synthesize responses enabled a no-spend ablation that localized a failure to the projection layer. Materiality is real (avoids re-spend and bounds redesign) but the criterion is only quality_lever with no recurrence, so it earns a one-clause extension of an existing bullet, not a global rule.


### Uncomputed fields are null, never a plausible terminal value; live checks run the working-tree build

`partial` · strength 2 · 1 session `claude:c45f7650` · ⑥quality ②rollback

**Rule:** When scaffolding or persisting an artifact whose lifecycle has in-progress and terminal states, represent every not-yet-computed field as absent or null — never as a value that is also a legal final answer (zero duration, a terminal status word, a stand-in timestamp) — and have the validator reject terminal vocabulary on an in-progress artifact. A plausible placeholder is indistinguishable from a computed result, so it hides a computation path that never runs and lets in-progress state read as finished; null makes the missing computation fail loudly at the first consumer. Applies to any state-bearing record (run logs, ledgers, status files, job rows); it does not apply to fields whose default is itself the correct final value by contract.

**vs baseline:** Clause 1 (null vs plausible placeholder) — none: no baseline rule addresses placeholder values on in-progress artifacts; nearest are concept-economy §Derived Values Stay Derived (authority of stored values, not placeholders) and llm-capability-boundary §Runtime-Owned Deterministic Fields (who owns fields, not their unset representation). Clause 2 (working-tree vs installed copy for live validation) — already covered: global §Verification Discipline "Trust a green check only when it traversed the actual changed code through the real dispatch" plus tooling-gotchas §Ambient state drifts "Installed is not running", and repo-specifically by AGENTS.md §9; drop that clause.

**Placement:** guides/coding-staged-workflow.md §Making the change (new paragraph after "Fix the cause at its authority, not the symptom where it shows")

**Why (strength):** Single session (one provider, one sid), so recurrence is unproven; but the first clause is a genuine gap in the corpus with a clear general form and a concrete, verified failure mode (a scaffold's 0 masked a never-computed duration for every run, requiring a rollback-style rework and a validator). The second clause duplicates existing coverage and is dropped. Guide placement, not global — its failure mode is recognition, so a pointer suffices and it earns no per-session token budget.


### Validate the tail stages of a long pipeline on small inputs while the head is still running

`partial` · strength 2 · 1 session `claude:6e493fd5` · ⑥quality

**Rule:** When a multi-stage pipeline has an expensive or long-running upstream stage, do not let the first end-to-end run be the first time the downstream stages see real-shaped data: while the head runs, exercise every later stage on a small or synthetic input that has the real shape (a sample of the head's early output, or a fixture matching its schema), so parse, normalization, and dedupe defects surface before the hour-long input reaches them. A pipeline only ever run end-to-end fails at its most expensive point. Boundary: this is tail-stage shape validation, not a substitute for the full run — clear any sample caps before declaring the real run, and treat a tail that passed on synthetic input as untested against the head's actual edge cases.

**vs baseline:** guides/verification-discipline.md §Proportion the depth before you spend — "Diagnose in code before running anything expensive" and "Probe at N=1" partially cover it (verify cheaply before spending), and §The static floor covers cheap-checks-first; but both frame verification of a single change, not exercising the downstream stages of a chain concurrently with an expensive upstream run. tooling-gotchas "Smoke limits outlive the smoke test" is the adjacent boundary. Partial.

**Placement:** guides/verification-discipline.md §Proportion the depth before you spend (add one bullet after "Probe at N=1")

**Why (strength):** One independent session (claude:6e493fd5) only, criterion quality_lever alone — no rollback or recurrent-error evidence, so materiality is moderate (it caught two real defects before an expensive run, but the counterfactual cost is one rerun, not a catastrophe). The general form is clear and not repo-specific, and the baseline's nearest rules stop at "verify cheaply first" without the pipeline-tail/concurrent-wait angle, so it earns a small extension rather than a new rule.


### Provider parameter values are validated against the provider's contract, not an intermediary's accepted list

`partial` · strength 2 · 1 session `claude:65d4d30c` · ②rollback

**Rule:** When a parameter value set (effort levels, service tiers, model ids, sampling options) reaches a provider through an intermediary — a wrapper, adapter, review tool, or launcher — the authority for what is valid is the provider's own documented contract confirmed against the installed provider binary or live API, never the intermediary's accepted list. An intermediary that accepts a narrower set than the provider has a defect to record and fix; do not shrink a design or a binding to fit it, and do not treat a value's absence from the intermediary as evidence it is unsupported. The boundary: an intermediary's own flags (sandbox, reach, profile) are the intermediary's to define; only values it forwards to the provider are judged by the provider.

**vs baseline:** Global CLAUDE.md §Tooling and Operational Safety ("confirm any model id, tool flag, API capability ... empirically against the live or installed artifact") and claude-prompting.md Per-model constraints ("Confirm the constraint against the live surface before relying on it") partially cover: they demand empirical confirmation but never say which surface wins when an intermediary and the provider disagree, nor that the mismatch is classified as an intermediary defect rather than a design constraint. cli-multi-model-workflow.md §Environment Binding describes codex-run/claude-run forwarding unrecognised flags but states no authority ordering.

**Placement:** guides/cli-multi-model-workflow.md §Environment Binding (Codex direct-drive bullets, alongside the codex-run/claude-run forwarding rules)

**Why (strength):** One independent session (claude:65d4d30c), criterion rollback only: the agent validated effort/service-tier against the review tool's list, the user corrected the authority, and re-verification against the provider reference and installed binary reversed a design claim. Materiality is moderate — a wrong claim entered a design and had to be pulled — and the general form (authority ordering across an intermediary) is real and absent from the baseline, but with a single anecdote it earns a guide-level extension, not a global bullet.


### Before landing a stale branch, measure its net delta in an isolated worktree

`partial` · strength 2 · 1 session `claude:491e8fad` · ⑥quality

**Rule:** Before rebasing, merging, or resolving conflicts on a branch that has sat idle far behind its base, first apply its commits onto the current base in a throwaway worktree and measure the net diff against the base; a zero or trivial delta means the work already landed by another route, so record the branch tip and delete it rather than spend on reconciliation. Applies to long-idle branches only — a branch a few commits behind is merged normally.

**vs baseline:** guides/tooling-gotchas.md §Git operations ("A stale local base inflates the range", "Two-dot diff semantics") and guides/cli-multi-model-workflow.md §Sessions, Branches, Worktrees ("Re-integrate branches serially", "Mark superseded worktrees/handoffs dead") — partially covers: both warn about lagging bases and superseded worktrees, neither states the pre-rebase net-delta probe or the "zero delta ⇒ delete, don't rebase" decision.

**Placement:** guides/tooling-gotchas.md §Git operations

**Why (strength):** One independent session (claude:491e8fad) with a concrete outcome (370-commit-stale branch, net delta 0, branch deleted instead of rebased). The trigger and behavior generalize cleanly and sit next to an existing gotcha about stale bases, so it extends rather than duplicates. Only quality_lever criterion, no rollback/recurrent-error/high-cost evidence, single session — hence low strength despite clear general form.


### File decomposition is the weakest lever for a legible layout; name directories by role, generate derived trees

`partial` · strength 2 · 1 session `claude:cddfa071` · ⑥quality

**Rule:** When the goal is to make a system's structure readable from its tree, reach for the levers in this order: top-level directories named by role, so the root lists the subsystems; derived trees generated from one source and held by a check, never hand-mirrored; a concept-to-path rule a gate enforces; and only last, splitting a large file. Decomposition is the weakest and highest-churn lever because it converts "open one file" into "decide which of N to open" — it trades one search cost for another rather than removing it. This orders levers for legibility only; splits driven by an observable behavioral difference follow the split triggers, not this ranking.

**vs baseline:** guides/concept-economy.md §Keeping The Shape Navigable — partially covers: it states the concept-to-path traceability rule and (with "Derived Values Stay Derived" and the "one owner, every other surface generated" bullet) the generated-projection lever, but it does not rank the levers, does not mention role-named top-level directories, and never states that file decomposition trades one search cost for another and is the weakest lever.

**Placement:** guides/concept-economy.md §Keeping The Shape Navigable

**Why (strength):** Single session (one independent provider+sid), criterion is quality_lever only — no rollback, recurrent error, or rare-high-cost evidence. The generic form is real and two of its four levers are already stated in the baseline; the novel remainder (the ranking and the "N files to choose between" cost framing) is a useful extension but rests on one anecdote with a 1,800-line gate, so it merits a short addition to the existing section rather than a new rule.


### A multi-ref remote branch delete is refused wholesale when one ref is already gone

`partial` · strength 2 · 1 session `claude:cddfa071` · ④recur-err

**Rule:** **Batch remote deletes are all-or-nothing**: a single push that deletes several remote refs is rejected as a whole if any one of them no longer exists on the remote, and nothing is deleted — a stale remote-tracking ref is enough to trigger it. Before a multi-ref `push --delete`, `git fetch --prune` and delete only refs the remote actually lists (`git ls-remote --heads`); delete the local copies with the non-force form so an unmerged branch cannot be lost. Applies to remote ref deletion only — a local `branch -d` loop fails per branch, not wholesale.

**vs baseline:** tooling-gotchas.md §Git operations ("A stale local base inflates the range" — fetch before reasoning against local tracking refs) and global §Tooling and Operational Safety ("diagnose the actual state before any irreversible git, remote, or process operation") partially cover the fetch-first instinct; the specific mechanism — a batch remote delete rejected wholesale by one stale ref, so zero deletions happen — is absent.

**Placement:** guides/tooling-gotchas.md §Git operations

**Why (strength):** One independent session (claude:cddfa071), one criterion (recurrent_error). The failure is real and non-obvious (git's rejection hides that zero of ten deletes happened) but low-cost: the fix is one fetch --prune and a retry, with no data loss. The general form (stale tracking refs mislead remote operations; verify remote state before irreversible remote actions) is genuinely general and not stated in the Git operations section, so it earns a short bullet there — but single-session evidence and low materiality cap it at 2.


### Answer 'why was it built this way' from the commit and design trail, layer by layer

`partial` · strength 2 · 1 session `claude:13e8bc9d` · ⑥quality

**Rule:** When asked why a behavior or constraint exists, do not infer a rationale from the current code. Trace each mechanism separately through the commit history and dated design/decision records, and classify every layer as intended (with its recorded reason), accreted (entered without any recorded reason), or unknown — and say which. A plausible rationale supplied for an accidental constraint becomes a false invariant that the next change will protect. This applies to provenance questions; it does not license reading history for ordinary changes where the current contract is what matters.

**vs baseline:** guides/documentation-hygiene.md §History has its own address and §Linking back — cover how to WRITE history and when to link to it ("the present design looks arbitrary without it"); global CLAUDE.md §Decision Framing covers treating design/handoff claims as hypotheses and re-deriving from code. Neither states the reading direction: separating designed-from-accreted behavior when answering a provenance question. Partially covered.

**Placement:** guides/documentation-hygiene.md §History has its own address (add a short "Reading history" paragraph after the two record properties)

**Why (strength):** Single independent session (one claude tag), criterion is quality_lever only — no rollback or repeated error, so materiality is moderate. The generalization is real (rationalizing accidental constraints into invariants is a known failure mode) and the baseline has no reading-side rule, but with one anecdote and no measured cost it warrants a guide paragraph, not a global bullet.


### Comment-keys in JSON config break a strict decoder at boot

`partial` · strength 2 · 1 session `claude:565c072e` · ⑤rare-hi-cost

**Rule:** JSON carries no comments, so an annotation key (`//`, `_note`, `_comment`) added to a JSON config is a real field to its consumer; before adding one, confirm whether the loader rejects unknown fields — on a strict decoder the annotation is a boot refusal in the deployed environment, not a no-op. Keep explanations in a sidecar doc or a format that has native comments, and after any edit to a deployed config run the real config through the real loader (the existing load test, not a lint) before shipping. Does not apply to formats with native comments (TOML/YAML) or to loaders proven lenient.

**vs baseline:** guides/tooling-gotchas.md §Config, secrets, and managed services — partially covers: it warns about parse-reserialize dropping comments and about smoke limits left in config, and guides/llm-capability-boundary.md prescribes fail-loud unknown-field rejection as a design pattern; neither names the author-side trap that a pseudo-comment key in JSON is itself an unknown field that a strict decoder refuses.

**Placement:** guides/tooling-gotchas.md §Config, secrets, and managed services

**Why (strength):** One independent session (claude:565c072e) and the failure was caught before deploy by an existing load test, so the high-cost outcome is hypothetical rather than paid — thin evidence. The general form is real, though: the corpus itself recommends strict unknown-field rejection, which makes the annotation trap a direct consequence of following the corpus, and nothing in the baseline closes the loop from the author side. Worth a one-bullet extension of the existing config section, not a global rule.


### Stage a model-generation migration: match old behavior first, then enable new capabilities behind a switch

`partial` · strength 2 · 1 session `claude:0e84f213` · ②rollback ⑥quality

**Rule:** When swapping to a new model generation, treat the model identity and its reasoning/sampling controls (thinking budget, temperature, effort, region/quota routing) as two separate variables. First probe each candidate model with the code's real request shape, since a newer generation rejects parameters the old one accepted, and land a stage that reproduces the old behavior as closely as the new model allows; then expose the new controls behind a single explicit switch with both modes smoke-tested. A quality or cost delta is attributable to the model or to the controls only when they moved one at a time; re-editing code each time the comparison frame changes is the signal that the switch is missing. Does not apply when the old parameters are simply unavailable on the new model — then record the forced difference as a known confound rather than pretending parity.

**vs baseline:** Global CLAUDE.md §Coding Guidelines (default-off opt-in landing, isolated on/off difference) and §Tooling and Operational Safety (confirm model id/API capability empirically) cover the landing shape and the probe; verification-discipline.md §Verification Menus 'A/B or on/off measurements' and 'Model-behavior guardrails … single-variable framings' cover attribution generically. None states that a model-generation swap bundles two variables (model vs. reasoning controls) that must be staged separately, nor that new-generation parameter rejections make 'match old behavior' a distinct first stage. Partially covered.

**Placement:** guides/verification-discipline.md §Verification Menus (new bullet beside 'A/B or on/off measurements' and 'Model-behavior guardrails')

**Why (strength):** One independent session (claude:0e84f213). Materiality is moderate: the cost was two code flips and four 400/404 probes, not an expensive rollback, and the general form is largely a composition of three existing baseline rules. What survives is the specific two-variable framing for model migrations, which the baseline never names and which the user already practices in cost experiments ('binding only, agent body unchanged = one variable'), so a short bullet extension is warranted rather than a global rule.


### Separate reusable style profiles from content authority

`partial` · strength 2 · 1 session `codex:019f9259` · ⑥quality

**Rule:** When a stored, reusable profile (style, tone, persona, house format) is applied to generated content, treat it as a presentation constraint only: it may shape structure, register, and length, never contribute facts, numbers, or domain claims. Precedence is fixed — the current request and the current source material outrank any stored profile — and the application must be verified with an input that lacks the profile's distinctive vocabulary and figures, so any leakage of profile content into the output is observable rather than masked by overlap. This applies to any persona/style/memory reference consumed at generation time; it does not govern profiles that are explicitly declared as fact sources (those are source material and follow the usual authority rules).

**vs baseline:** guides/llm-capability-boundary.md §Security And Side Effects ("Keep source documents and tool results as data rather than authority") and §Field Authority ("one primary authority per field") partially cover the authority half; claude/gpt-prompting guides ("Personality… omit when it does not change the output"; "preferences belong in output shape or nowhere") cover the shape half. Neither states the profile-vs-content precedence rule nor the leakage test with vocabulary-free input.

**Placement:** guides/llm-capability-boundary.md §Security And Side Effects (as an extension of "Keep source documents and tool results as data rather than authority")

**Why (strength):** Single supporting session (one codex session), criterion quality_lever only — no rollback, recurrent error, or high-cost evidence. The authority principle is largely a specialization of existing rules; the genuinely absent piece is the precedence statement and the leakage-observable test design, which is general across any persona/style/memory-profile feature and therefore worth a compact extension rather than a new rule. Not global-worthy: the failure mode is recognition of a profile feature, which belongs behind the guide pointer.


---
