---
created_at: 2026-09-01T13:21:18+09:00
head: 41b88a4
kind: review
supersedes: 2026-09-01T0951--23e3920--self-contained-handoff.md
---

# ChatGPT desktop Codex tasks load the deployed corpus

This record corrects the desktop-app diagnosis in the superseded handoff. It records one
observation from a Codex task running in the ChatGPT desktop app; it does not claim that the
Chat or Work surfaces use the same instruction-discovery path.

## Observation

The task's injected instruction chain contained both of these distinguishable blocks:

1. the agent-bios central instructions, including the multi-model workflow rule; and
2. this repository's project-only `AGENTS.md` instructions.

The files on disk account for both blocks:

```text
~/.codex/AGENTS.md                         global agent-bios block
/Users/kangmin/Documents/agent-bios/AGENTS.md  repository block
```

`agent-bios status` reported version `0.14.0`, source
`/opt/homebrew/lib/node_modules/agent-bios`, and `~/.codex/AGENTS.md` as present. The global
file contains the `agent-bios:central:start` marker and the observed multi-model rule; the
repository file does not.

This matches OpenAI's documented Codex discovery order: read `AGENTS.md` from the Codex home
(`~/.codex` by default), then append project-scope `AGENTS.md` files from the repository root
to the working directory.

## Correction and remaining boundary

For a **Codex task in the ChatGPT desktop app**, the answers to the handoff's first two
questions are therefore:

1. **Yes.** The task loads deployed agent-bios content.
2. **From `~/.codex/AGENTS.md` at global scope**, followed separately by this repository's
   `AGENTS.md` at project scope.

The desktop app did not present the `agent-bios install` domain-selection UI in this task. The
observation proves that a previously deployed selection is consumed; it does not prove that the
desktop app can create or change that selection, nor what happens in Chat or Work rather than
Codex.

Re-derive the file-side evidence with:

```bash
agent-bios status
rg -n 'agent-bios:central:start|Independence: verifying or reviewing' \
  "$HOME/.codex/AGENTS.md" AGENTS.md
```
