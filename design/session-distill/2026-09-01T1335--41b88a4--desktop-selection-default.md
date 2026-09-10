---
created_at: 2026-09-01T13:35:54+09:00
head: 41b88a4
kind: design
supersedes: 2026-09-01T1330--41b88a4--desktop-preflight-boundary.md
---

# Desktop corpus selection: revised minimum

## Finding that changes the default

The prior design correctly separated three mechanisms:

1. agent-bios assembles and deploys a selected corpus;
2. Codex reads the resulting global `AGENTS.md` artifact when a task starts; and
3. the terminal-only `agent-launch` preflight configures one CLI invocation.

It then made a plugin plus `SessionStart` status hook the default desktop configuration
surface. That is more machinery than the required behavior needs. A user-scoped standalone
skill is already cross-project in the ChatGPT desktop app. The explicit selection action can
show current state itself, so a hook on every session adds lifecycle, trust-review, and failure
states without enabling selection before instruction discovery.

## Revised default

Ship one **user-scoped, explicitly selected agent-bios onboarding skill**. Do not require a
plugin or lifecycle hook for the first version.

The skill performs this bounded flow:

1. Read the installer-owned `~/.local/share/agent-bios/corpus-status.json` and require a
   non-empty `domains.available` list.
2. Show `domains.applied` separately from the available set. `null` means no selection was
   recorded; an empty list means the deliberate core-and-infra-only selection.
3. Ask the user which closed set to apply and state the consequence: `agent-bios onboard`
   runs the full existing installer path, not only an `AGENTS.md` edit. It can redeploy the
   selected corpus, skills, launcher files, wrappers, config additions, and status projection,
   then run its activation canary.
4. After explicit confirmation, pass the validated set unchanged to
   `agent-bios onboard --domains <comma-separated-set>`; use `none` for the empty set. The
   skill never writes `selection.json`, `corpus-status.json`, or `AGENTS.md` itself.
5. Report the installer outcome and state plainly: **the current task retains the instruction
   chain loaded at its start; create a new Codex task to use the new selection.**

Do not prescribe one mention character in the product contract. OpenAI documents different
explicit skill selectors for ChatGPT and Codex surfaces, and this exact desktop surface has not
been probed. User-facing text should say “select the agent-bios onboarding skill” and use the
selector the active UI exposes.

## Authority boundary

| Decision or artifact | Owner |
| --- | --- |
| desired domains | user, from the runtime-enumerated allowed set |
| allowed domain ids | installer-owned status projection |
| validation and canonical selection state | `agent-bios onboard` / assembler |
| global managed region write | assembler only |
| current task's effective instruction chain | Codex task start; immutable for this purpose |
| next task's observation | new desktop Codex task |

The existing command remains the one accepted write channel. Unknown domains must fail in the
installer, and the skill must not construct an unvalidated free-form shell fragment from model
text.

## Immediate zero-change path

Until the skill ships, open the desktop integrated terminal, run:

```bash
agent-bios onboard
```

Choose the domains, let the existing apply finish, then create a new Codex task. This is the
same authority path the skill will call; it is manual rather than a separate implementation.

## Deferred enhancement

Add a plugin-bundled status hook only if users demonstrate a need to see corpus status at every
task start. If added, it must:

- match `SessionStart` source `startup` only;
- return a JSON `systemMessage` only, never plaintext or `additionalContext`;
- remain read-only and advisory;
- state the selection recorded when this task started, not a later selection after resume or
  compaction; and
- include the non-managed hook trust/review step in onboarding.

This hook is not a preloader and must not claim to update the current task.

## Out of scope until the desktop exposes authority

The model, effort, permission, review, and developer-instruction `LaunchPlan` portion of the
terminal TUI cannot be transferred by this skill. The desktop starts its bundled Codex
app-server without the shell wrapper, and no supported pre-thread creation input for that plan
was found. App-bundle replacement, PATH interception, and file watchers remain rejected.

## Done when

The first version is complete when:

1. the standalone skill is discoverable from a Codex task in the ChatGPT desktop app;
2. its allowed set is derived from a non-empty installer-owned status projection;
3. the chosen set is confirmed and reaches the existing `onboard --domains` validator unchanged;
4. only the installer/assembler writes canonical state and the managed global region;
5. the skill reports that the current task is unchanged; and
6. a new desktop Codex task observes the newly selected managed content.

The sixth item is a live-surface observation. The existing activation canary is Claude-only,
and the existing Codex verify path proves marker presence rather than desktop consumption; neither
is desktop proof.
