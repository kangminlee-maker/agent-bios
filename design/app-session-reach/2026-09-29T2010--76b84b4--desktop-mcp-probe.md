---
created_at: 2026-09-29T20:10:00+09:00
head: 76b84b4
kind: review
---

# What Claude Desktop 2.9939.4 actually speaks, measured rather than read

Evidence, not design. It records what one Claude Desktop sent to a minimal MCP
server on 2026-09-29, so the design that follows rests on observation. Every
figure is a dated claim about **Claude Desktop 2.9939.4 on one macOS machine**;
re-probe after a Desktop update, and compare that version string first.

Sections are separated on purpose: **Measured** holds what the probe observed,
**Asserted** holds claims from other sources that this probe did not test, and
**Not measured** holds what a reader might otherwise assume was covered.

The question it serves: agent-launch projects a work environment at launch, and a
desktop app has no launch to project into.

## Method

A stdio MCP server that answers `initialize`, `tools/list` and `tools/call`, and
appends every received message to a log.

**Registration path: `~/Library/Application Support/Claude/claude_desktop_config.json`,
as `{"command": "python3", "args": ["<probe path>"]}`, followed by a Desktop
restart.** Everything below was observed under that path. A `.mcpb` bundle was
never installed or exercised, so nothing here establishes that a `.mcpb`-installed
server sees the same client, capabilities or limits.

**The probe declared `capabilities: {"tools": {}}` and nothing else.** This is a
confound to keep in mind wherever absence is reported: a client will not call
`resources/*` or `prompts/*` on a server that never offered them.

**It reads both protocol shapes.** MCP 2025-11-25 declares the client once, in
`initialize`. MCP 2026-07-28 removed that handshake; each request instead carries
`_meta` with protocol version, client info and capabilities. A probe reading only
one shape learns nothing from a host speaking the other.

**Positive control.** Before registering it, the probe was fed synthetic messages
in *both* shapes and required to report each correctly — an `initialize` carrying
`capabilities` with no elicitation, and a `tools/call` whose `_meta` carried
`io.modelcontextprotocol/clientCapabilities: {"elicitation": {"form": {}, "url": {}}}`.
It reported `REVISION SEEN: initialize handshake` for the first and
`REVISION SEEN: per-request _meta` plus the elicitation object for the second.
So the zero-observation result below is "it did not arrive", not "the probe could
not see it".

**It measures arrival, not departure.** A payload's size on the wire is not its
size in the model's context. Each payload is wrapped in `BEGIN <n>KB <nonce>` and
`END <n>KB <nonce>` lines, and a second tool, `probe_report`, lets the receiving
model post back the END line it saw, plus whether the result arrived inline or as
a file. Filler between the markers is `("agent-bios probe payload. " * 40)[:1024]`
repeated to length — plain ASCII, which matters for the token limit below.

## Measured — what Desktop declares

Seven `initialize` handshakes, two distinct clients:

| clientInfo | handshakes | roots | elicitation | sampling | extensions |
| --- | --- | --- | --- | --- | --- |
| `claude-ai / 0.1.0` | 3 | absent | absent | absent | `io.modelcontextprotocol/ui` |
| `local-agent-mode-<server name> / 1.0.0` | 4 | `listChanged` | absent | absent | same |

The second embeds the server's own name and corresponds to Desktop's
`local-agent-mode-sessions` directory: one registered server is started once per
client. Nine server processes started against seven handshakes — two started and
were replaced without completing one, both around the 32 MiB failure below.

`protocolVersion` was `2025-11-25` on all seven, and the per-request `_meta` shape
was observed **zero** times (see the positive control above). The current
published standard is 2026-07-28, so this Desktop is one revision behind.

**No `elicitation` on either client.** A server cannot ask the user a question
through MCP on this host.

`roots.listChanged` is **declared by the local-agent-mode client and never
exercised**: the probe never issued `roots/list`, so no root was ever retrieved.
The declaration is evidence of intent, not of a working exchange.

`io.modelcontextprotocol/ui` (`text/html;profile=mcp-app`) is likewise declared by
both clients and never exercised — no server on this machine has returned such a
resource in any retained log.

## Measured — what Desktop called

50 `tools/call`, reconciling exactly: 35 payload requests (29 to the round-trip
probe, 6 to an earlier version) and 15 `probe_report` calls.

| Method | Calls |
| --- | --- |
| `tools/call` | 50 |
| `initialize` | 7 |
| `notifications/initialized` | 7 |
| `tools/list` | 7 |

Nothing else was received. **This does not establish that Desktop ignores
`resources/*` or `prompts/*`** — the probe declared neither, so their absence is
expected and uninformative. What it does establish is that tool calls and the
handshake are sufficient for a server that offers only tools.

## Measured — the inline limit, 48 KiB

| Payload | Bytes | Trials | Delivery |
| --- | --- | --- | --- |
| 32 KiB | 32,768 | 1 | inline |
| **48 KiB** | **49,152** | **2** | **inline** |
| **49 KiB** | **50,176** | **2** | **saved to a file** |
| 64 KiB | 65,536 | 1 | saved to a file |
| 256 KiB | 262,144 | 1 | saved to a file |
| 1 MiB, 8 MiB, 16 MiB | — | 1 each | saved to a file |

The boundary lies between 49,152 and 50,176 bytes. Above it Desktop writes the
tool result to a file and the model reads it from disk; both markers survived, so
nothing was truncated.

**Desktop tells the model.** Its report reads "Result exceeded the inline token
limit and was saved to a file". The delivery change is therefore visible to the
model in the moment — but not to agent-bios, which would still label the result
`returned-as-context`
(`compose/instructions_app.py:414`). The risk is a false receipt, not a silent
model.

**It is a token limit expressed here in bytes of one particular text.** Desktop's
own words are "inline token limit"; the probe sent repeated ASCII. Real
instruction text tokenizes differently and may cross the same boundary at a
different byte count.

## Measured — the transport ceiling, and how it fails

| Payload | Bytes | Trials | Result |
| --- | --- | --- | --- |
| 16 MiB | 16,777,216 | 2 | arrived (as a file) |
| 16,400 KiB | 16,793,600 | 1 | arrived (as a file) |
| 17 MiB | 17,825,792 | 6 | failed |
| 18,440 KiB | 18,882,560 | 4 | failed |
| 24,580 KiB | 25,169,920 | 4 | failed |
| 32 MiB | 33,554,432 | 1 | connection closed, server process replaced |

16 MiB was re-sent as a control **in the session where 17 MiB had just failed**,
and it arrived. That control is what makes the 17 MiB failure attributable to
size. The ceiling lies between 16,793,600 and 17,825,792 bytes — roughly 650×
above the largest instruction body measured below, which is why it is recorded
for its failure behaviour rather than its value.

**A session can be lost, and recovers only on a Desktop restart.** After the
24,580 KiB attempts, every later call in that session failed regardless of size,
including 18,440 KiB and 17 MiB; a Desktop restart cleared it. This is **not** a
property of every oversized call: in the fresh session, 17 MiB failed four times
and the session still served 16 MiB afterwards. So an oversized call *may* lose
the session, and the loss persists until restart.

**Failures near the ceiling misname their cause.** Every one reported
`MCP server "remote-devices" session expired`, naming a server that was not this
one.

## Measured — Desktop retries without telling the model

One clean observation: 17 MiB in the session later proven healthy by the 16 MiB
control. The server received **four** `tools/call` requests; the model reported
"failed twice".

The same 4-against-2 split appeared at 24,580 KiB and 18,440 KiB, but those were
in the lost session and are **not counted** — a lost session's retry behaviour is
not known to match a healthy one's. One clean observation is enough to establish
that the split happens; it is not enough to establish its rate, and nothing here
observed a retry of a *successful* call.

## Measured — the instruction body this would carry

Measured 2026-09-29 on this machine:

```
wc -c ~/.local/share/agent-bios/sessions/snapshots/*/launch-content/instructions.md
```

27 snapshots carried that file: 23,240 bytes minimum, 25,771 maximum.

**These are native-session snapshots.** The app path returns
`catalog.compile_items(..., native=False)` output plus an appended bootstrap
invocation line (`compose/instructions_store.py:1548,1568`), so the body an app
`use` would return is compiled separately and is not known to equal these files.
Sizing the app path requires measuring the app path.

## Asserted — not tested by this probe

- **MCP 2026-07-28 is the current standard**, and it removes the
  `initialize`/`initialized` handshake in favour of per-request `_meta`, moves
  elicitation into an `input_required` tool result carrying `elicitation/create`
  (modes `form` and `url`), adds `-32021` (missing required client capability,
  carrying `requiredCapabilities`) and `-32022` (unsupported protocol version),
  replaces per-transport subscription mechanisms with one `subscriptions/listen`,
  and admits no batching. Source: the `modelcontextprotocol/modelcontextprotocol`
  repository — `schema/2026-07-28/schema.ts`,
  `docs/docs/2026-07-28/learn/versioning.mdx`,
  `docs/specification/2026-07-28/client/elicitation.mdx`,
  `docs/specification/2026-07-28/schema.mdx`, `docs/seps/2322-MRTR.mdx`, read
  2026-09-29. No content hash was taken, so this is a dated reading, not a pin.
- **Desktop has no hook system.** Hooks are a Claude Code feature. This probe
  tested nothing about hooks.
- **`.mcpb` packaging.** Read from an already-installed bundle on this machine
  (`Claude Extensions/local.mcpb.kangminlee-maker.onto/manifest.json`):
  `manifest_version 0.3`, a `server.mcp_config` carrying command/args/env with
  `${__dirname}` and `${user_config.*}` substitution, a declared `tools` list, and
  a `user_config` block. That a `user_config` form is actually rendered at install
  time, and that a `.mcpb`-installed server behaves as measured above, were not
  tested.

## Not measured

- The inline limit against real instruction text rather than repeated ASCII.
- The app path's returned body size.
- Whether a `.mcpb`-installed server sees the same clients and limits.
- `roots/list` — declared, never exercised.
- `io.modelcontextprotocol/ui` — declared, never exercised.
- Whether Desktop retries successful calls.
- Whether the Codex app's MCP client differs; only its skill path was examined.
- Whether a skill written into a live per-session config home is honoured, and
  whether any pre-session seeding point exists.

## Other surfaces on this machine

**Desktop does have a skills tree**, at
`~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/<session uuid>/<uuid>/skills/`.
Nine of them exist here, holding 8 to 17 skill directories each across four
distinct sets (`docx`, `pdf`, `pptx`, `xlsx`, `skill-creator`, `deep-research`,
`computer-use`, `google-workspace`, …). Each sits beside a `manifest.json` whose
entries are all `"creatorType": "anthropic"` and `"enabled": true`, under a
`.claude-plugin/plugin.json` describing "Anthropic-managed skills for Claude
Desktop".

All 88 skill entries across all nine manifests carry `"creatorType": "anthropic"`
and `"enabled": true` — the full set, not a sample. The trees are separate copies,
not links: the same skill in two trees has different inodes.

**Desktop's local agent mode is bundled Claude Code 2.1.284 running against a
per-session configuration home**, at
`local-agent-mode-sessions/<A>/<B>/local_<session>/.claude/` — 70 of them, with
the standard `.claude.json` / `projects` / `sessions` layout. `claude-code/2.1.284/`
holds the app, and the session ids under `claude-code-sessions/` are the same
UUIDs that key the skills trees.

**That home is not the user's `~/.claude/`.** Checked from both directions: of 480
project entries under `~/.claude/projects`, zero come from Desktop local agent
mode, while 69 exist inside the session homes.

The standard `.claude/skills/` path is live inside those homes — one of the 70
holds `create-shortcut`, an Anthropic skill for Desktop's shortcut feature, dated
2026-02-13. So the mechanism works; what is absent is a **stable root a third
party controls**. Every skill location observed is either Anthropic-provisioned
into the managed tree or inside a per-session home that does not exist until the
session starts.

Not established: whether a skill written into a live session home is honoured, and
whether any pre-session seeding point exists. Not found is not proven absent.

`Claude Extensions` holds ten unpacked extension directories, not ten `.mcpb`
bundles: eight named `ant.dir.*` (directory-sourced) and two named `local.mcpb.*`
(`.mcpb`-sourced). It is the local extension surface that was confirmed working;
it is not exclusively a `.mcpb` surface.

## What this probe got wrong first

Both mistakes were the same mistake, and re-running a known-good value exposed
both.

**A clamp read as a host limit.** The first probe carried `min(size, 4096)`.
Asking for 8192 KiB returned exactly 4096 KiB, which looked like Desktop's ceiling
and was the probe measuring itself. The probe now records every clamp as
`CLAMPED BY THE PROBE, NOT THE HOST`.

**A lost session read as a size limit.** After 24,580 KiB lost the session,
18,440 KiB and 17 MiB also failed, and the falling sequence looked like a boundary
being bisected. It was not. Only after 16 MiB succeeded again did 17 MiB's failure
mean anything.

A third, found in review rather than in the probe: an earlier draft of this record
quoted `tools/call` as 27, a count taken before the final rounds and never
recomputed. Numbers in a record must be derived from the artifact at the moment
the record is written, not carried forward from a working note.

**A fourth, and the same error class as the first two: an absence reported from a
search that could not have found the thing.** An earlier draft stated that nothing
named `skill` exists under `~/Library/Application Support/Claude/`. The search was
a listing of that directory; the skills tree is two levels below it, and a listing
cannot report what it never descended into. The same draft called every
`Claude Extensions` entry a `.mcpb` bundle when eight of the ten are
directory-sourced — a classification asserted over a listing that had already been
read and not looked at. **An absence is only as strong as the search that looked
for it, and neither of these searches was stated alongside its conclusion.** Both
claims were load-bearing: one of them was a reason for excluding an alternative.

## Re-deriving this

Register a stdio MCP server in `claude_desktop_config.json`, restart Desktop, and
have it return payloads wrapped in BEGIN/END markers around the boundary,
each followed by a report of the END line seen and whether delivery was inline or
a file. Confirm session health with a known-good size before believing any
failure, and record the Desktop version. The probe used here was author-side
scratch and is not retained in the tree; its behaviour and filler string are
described above in enough detail to rebuild.
