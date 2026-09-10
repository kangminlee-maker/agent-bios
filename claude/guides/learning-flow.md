---
guide_id: learning-flow
language: en
status: active
use_when:
  - the user entered `learn!` in any session (this is the light capture flow)
  - capturing a durable lesson from the current session for reuse + org curation
  - deciding whether a candidate lesson is worth recording, and how it should apply
core_rules:
  - three gates BEFORE asking the user — admission bar, type, consumption layer
  - the user approves every recorded learning; nothing is written without it
  - submit ONLY through `agent-bios learn`; never hand-write the record
---

# Session learning flow (`learn!`)

The **light**, per-user, single-session capture flow: turn a lesson from the
current session into a **learning** (prose + a JSON record) that (a) applies to
the user's own next session and (b) reaches the org for curation. This is the
counterpart of the **heavy** session-distill pipeline (`distill!`), which mines
many sessions and is curator/power-user only. Terminology and the full routing
framework are maintained in the agent-bios repo; the criteria this flow applies
are stated below.

Defer to the preset mission: if this session runs the **Session distill** preset
(trigger `distill!`), that mission owns capture — do not also run this flow.

## When it fires

Only on the user's `learn!`. Runs in-conversation on the CURRENT session (no
Workflow fleets, no subagent mining). **Multiple learnings per invocation are
allowed** — walk each candidate through the gates independently.

## Rigor: three gates BEFORE surfacing anything

Establish all three for each candidate; drop candidates that fail. Only
still-valid candidates are surfaced for the user's approval.

1. **Admission bar** (promotion criteria — PLACEMENT-FRAMEWORK): the lesson
   recurred across **≥2 independent sessions**, OR it is a **single event with
   high materiality** (irreversible / verification-corrupting / security). A
   one-off low-stakes observation does not meet the bar — say so and skip it.

2. **Type** (typology A–G; classify by root cause, first match wins):
   - **A. Own-tooling defect** — a flaw in a script/tool we own (a repair).
   - **B. Tool gotcha** — counterintuitive external-tool behavior with a
     machine-detectable trigger (command pattern).
   - **C. Recognition principle** — a cross-domain semantic signal → suspicion/action.
   - **D. Domain procedure** — a multi-step method within an already-routed kind of work.
   - **E. Environment fact** — a non-generalizable, decaying specific fact.
   - **F. Unproven** — evidence still below the bar (usually already dropped at gate 1).
   - **G. Principle/direction** — a value ordering shaping many decisions.
     **Not manufactured user-side in v1** (curator-only); record a principle-ish
     observation as an ordinary learning and let curation promote it.
   Prefer *leftward reformulation* when it holds (E→C generalize a fact into a
   principle; B/C/D→A mechanize knowledge into structure) — cheaper and more reliable.

3. **Intended consumption layer** (cheapest-that-still-fires wins):
   **enforcement > gate > hook > guide > global > memory** (`incubator` = park
   for later triage). This is recorded as **metadata only** — do NOT build the
   hook/gate/enforcement here; mechanization is deferred to curation.

## Domain tagging (the curation join key)

Suggest a `domain` from the registered vocabulary in `compose/domains.json`
(domain keys for domain-specific lessons, or a tier name like `core`/`infra`
for a genuinely cross-cutting lesson); the user **confirms**. If unsure, use
`unclassified` (never blocks capture — the curator assigns later). If no
registered domain fits, keep `domain: "unclassified"` and put the model's
suggested new name in `proposed_domain` (domain creation stays curator authority).

## User approval, then submit

Surface each surviving candidate compactly — lesson, type, intended layer,
admission-bar verdict, domain (+ proposed_domain) — and record ONLY what the
user explicitly approves.

Submit each approved learning through the deterministic submit tool. Pass your
session's `--host` and pipe the **semantic payload only** as one JSON object on
stdin (set the `supporting_sessions` tool prefix — `claude:` or `codex:` — to
match your host):

    echo '{"lesson":"…","domain":"builder-base","supporting_sessions":["<tool>:<session-short-id>"],
           "criteria":["recurrent_error"],
           "classification":{"type":"B","layer":"hook","meets_bar":true}}' \
      | agent-bios learn --host <claude|codex>

The script (capability boundary) owns `learning_id` / `created` / `schema_version`,
validates against `learn/learning.schema.json`, logs the JSON record, and writes
the lesson prose where THIS host loads it next session:
- **Claude**: appended to the automation-owned personal learnings file, pulled in
  by the entry file's `@personal/learnings.md` import.
- **Codex**: appended into a managed `agent-bios:personal-learnings` region of
  `AGENTS.md` (Codex has no import; AGENTS.md is always loaded), kept outside the
  central markers so re-assembly preserves it.

**Never** hand-author `learning_id` / `created` / `schema_version`, and never
write those files directly. If the script REJECTS a record, fix the semantic
payload — do not work around the validation.

## Scope (v1)

- Single-session capture only; cross-session mining is `distill!` (curator).
- Mechanization (hook/gate/enforcement) is deferred to curation — record intent, don't build it.
- Type-G principle manufacture is curator-only.
- Transport (upload to the org) is best-effort after the local write: it runs only
  when the `~/.config/agent-bios/{ingest-url,token}` slot is set, which is the
  only source there is. A default install sets nothing, so nothing leaves the
  machine; an org fills the slot through its own wrapper.
