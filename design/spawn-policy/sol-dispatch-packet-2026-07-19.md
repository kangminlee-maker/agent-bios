# Role

You are an independent frontier-tier design consultant working read-only and hermetic: no repo access, no network. Everything you need is in this packet.

# Goal

Define "spawn points" for a multi-tier CLI agent system, and propose the metric set that proves and governs them.

# Background (system under design)

- Two CLI agent hosts (Claude Code, Codex CLI) launch with a 4-tier model hierarchy injected at session start:
  - FRONTIER — strongest model, max effort. Intended for the hardest bounded judgments, verdicts, deep review.
  - HELM — standing main/orchestrator (xhigh effort). Owns architecture, scope, tradeoffs, user-facing decisions.
  - WORKHORSE — mid-tier model, high effort. Implementation volume, per-item judgments.
  - SWEEP — small model, low effort. Mechanical scans, wide cheap reads, closed rule-driven passes.
- The main session (usually HELM) can spawn subagents at any tier. Design intent: decisions stay in the main; volume work delegates down; hardest bounded judgments and independent review delegate up to FRONTIER.
- Measured reality (from ~2 weeks of session logs on both hosts since the feature landed): only 2.6% of Claude sessions and under 0.3% of Codex sessions ever spawn a subagent; tier-named spawns concentrate in 18 sessions; SWEEP was never used once. Root causes already diagnosed: (a) the launch wrapper injects tier agents only on a narrow entry path, so most sessions never have them; (b) the always-loaded session contract states tier bindings but contains no decision rules for WHEN to spawn — those gates live in a guide that loads only for explicitly multi-model work, which ordinary sessions never trigger.
- Agreed fix direction: inline a compact spawn policy into the always-loaded contract, and make the spawn-point definitions adjustable from measured data. This packet asks you to design that policy's core: the spawn-point definitions and their governing metrics.

# The question

1. Define the spawn points. Where should the main delegate DOWN (WORKHORSE/SWEEP) with no quality loss, and where should it delegate UP to FRONTIER such that quality strictly increases? Give operational, in-session-detectable definitions — conditions an agent can check while working — not aspirational descriptions.
2. Propose the metric set that (a) proves down-delegation is quality-neutral, (b) proves frontier delegation adds quality, (c) adjusts the spawn-point definitions over time. For each metric: what it measures, which failure mode it detects (prefer falsifiable signals that drop when the mechanism is wrong), an interpretation rule (what value range triggers what adjustment), and whether it is computable from existing session transcripts (JSONL tool-call logs, subagent sidechain transcripts, token counts, file-edit history) or needs new instrumentation.

# Success criteria

- Definitions are checkable conditions; each gate names the concrete signal that fires it.
- Every metric is paired with the failure it detects and an interpretation rule. Cut any metric whose absence would not change a decision — the set must be minimal.
- Leading (decision-time) metrics are distinguished from lagging (outcome) metrics.
- Anchoring is addressed: how to keep FRONTIER review packets from leaking the main's tentative conclusion, and how to detect vacuous spawns (spawns whose output never changes anything).

# Constraints

- Read-only; answer from this packet only. Design level only — no implementation.

# Output

A bounded Markdown report in English with exactly these sections:

1. Spawn-point definitions (down-delegation and frontier up-delegation).
2. Decision gates — a compact checkable list suitable for inlining into an always-loaded system contract, 10 lines or fewer.
3. Metric tables: metric | measures | failure detected | interpretation rule | computable from logs today (yes/no).
4. Top 3 risks or blind spots of this entire approach.

Stop when these four sections are complete.
