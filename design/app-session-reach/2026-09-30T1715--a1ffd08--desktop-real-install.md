---
created_at: 2026-09-30T17:15:00+09:00
head: a1ffd08
kind: review
---

# The Desktop route on the user's real installation, and what Desktop's Code tab loads

Evidence, not design. The first end-to-end run
(`2026-09-30T1250--20084c8--desktop-end-to-end.md`) used a sandbox installation.
This one used the real one, on Claude Desktop 2.16120.0, after the working tree at
`a1ffd08` (plus the uncommitted help line for `app desktop`) was installed with
`bash install.sh install --non-interactive`: release `238cf9cf…`, saved selection
`all` unchanged, `install.sh verify` passing. `bash install.sh app desktop` wrote
`runtime/desktop-bundles/2aae4ad1…/agent-bios.mcpb` naming
`/opt/homebrew/opt/python@3.14/bin/python3.14`. Run from the unpacked bundle under
`env -i`, its `preview` reported the real body at **25,965 bytes** and wrote nothing.

The user replaced the sandbox extension with this bundle and ran two checks: a
second load request inside one chat conversation, and a load request from
**Desktop's Code tab**. Cowork (local agent mode) was not run: the user reports that
Anthropic has removed the Cowork tab from Desktop, so this route no longer considers it.
That is the user's statement, not a measurement; Desktop 2.16120.0 still opened a
`local-agent-mode-<server>` client handshake during the qualification that morning.

## Measured

### Chat: a second request in the same conversation

Desktop's log shows one server process answering four `tools/call` requests:
08:00:00, 08:00:09, 08:00:36, 08:00:38 (UTC). The conversation's receipt,
`desktop-9862…`, holds **one** delivery (08:00:00, marker `…459c17`) confirmed at
08:00:09, and the receipt file was last written at 08:00:38. No other receipt was
created in that window.

That is what the repeat path produces: a second `use` carrying the session id
returns the same text and marker without appending a delivery, and the model's
following `status` rewrites the receipt while keeping the first confirmation. A
second `use` without the id would have minted another receipt; none exists. The
tool arguments themselves are not observable — Desktop's log omits parameters and
the chat transcript is not stored locally — so the call kinds are inferred from
their effects, not read.

### Desktop's Code tab

The Code tab session (Claude Code **2.1.284**, `entrypoint: "claude-desktop"`,
working directory `/Users/kangmin/Documents/workbench-TA`, model
`claude-opus-5-5`) wrote its transcript to the user's own
`~/.claude/projects/-Users-kangmin-Documents-workbench-TA/`. It shows:

- `mcp__agent-bios__use {}` at 08:01:40, returning **26,987 bytes** whose last line
  is the delivery's end marker — the full text sits in the transcript's tool result;
- `mcp__agent-bios__status` with that marker and the minted `session_id` at 08:01:45,
  answered "read to its end: yes";
- receipt `desktop-ae57…`: one delivery, confirmed, working directory `/`.

None of these calls appears in Desktop's `mcp.log`, so the Code tab runs its own
server process through Claude Code's MCP client. Which client name and
capabilities it declared was not recorded; the server does not log them.

### The Code tab uses the user's `~/.claude`

This contradicts the first record's finding that Desktop's Claude Code runs against
a per-session home and never the user's `~/.claude/`
(`2026-09-29T2010--76b84b4--desktop-mcp-probe.md`, "That home is not the user's
`~/.claude/`"). That finding holds for **local agent mode** (Cowork), which is what
it examined. It does not hold for the Code tab:

- 11 transcript files under `~/.claude/projects/` carry `entrypoint:
  "claude-desktop"`, first at 2026-09-15T02:15Z — they existed when the first
  record said zero, which searched for local-agent-mode transcripts only;
- versions 2.1.270, 2.1.271 and 2.1.284;
- this session's transcript carries text from the user's global
  `~/.claude/CLAUDE.md`, a `skill_listing` attachment, and a `hook_success`
  attachment.

So the Code tab loads the user's global instructions, skills and hooks.

## What this changes, and what it does not

- The extension reaches both chat and the Code tab, the two surfaces this route
  now serves.
- The skill-route closure (`D-20260929-b275d6`) rested on "every root Desktop uses
  is Anthropic-provisioned or created after a session starts". For the Code tab that
  ground is false: `~/.claude/skills/` is a stable root the tab reads. The closure's
  ground stands for chat and Cowork only.
- In the Code tab a project exists — the session's working directory — but the
  extension's server starts in `/` and Desktop delivery resolves no project scope,
  so project-scoped imported instructions are excluded there too. A route that runs
  inside the session (a skill invoking agent-bios through the shell, as the Codex app
  bridge does) would see that directory; the MCP server does not. Whether to add one
  is a direction question, not settled here.

## Not measured

- The MCP client name and capabilities the Code tab declares, and whether it
  answers `roots/list`.
- The chat tool arguments (inferred above).
- Whether a skill placed in `~/.claude/skills/` is offered in the Code tab's skill
  listing. The listing exists; its contents were not compared.

## Got wrong first

The first record's "not the user's `~/.claude/`" generalised from local agent mode
to Desktop as a whole. The search behind it looked for one kind of transcript and
could not have found the other; no control asked whether Desktop wrote
`~/.claude/projects` by any other route. The `entrypoint` field that settles it was
in those files the whole time.
