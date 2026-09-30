---
created_at: 2026-09-30T06:45:00+09:00
head: 20084c8
kind: review
---

# A `.mcpb`-installed Python server in Claude Desktop 2.16120.0, measured

Evidence, not design. It is the first implementation step the design
(`2026-09-29T2015--76b84b4--design.md`) required before building anything:
qualify the `.mcpb` installation route that the first probe never used, and
measure the real app-path instruction body against the inline limit.

Every figure is a dated claim about **Claude Desktop 2.16120.0 on one macOS
machine**, measured on 2026-09-30. The first record
(`2026-09-29T2010--76b84b4--desktop-mcp-probe.md`) is about **2.9939.4**. Desktop
updated between the two, and one of that record's findings did not survive the
update; it stands as a claim about the older version, not as a current fact.

## Method

A scratch bundle, not a repo file: `manifest_version` 0.3, `server.type`
`python`, `mcp_config.command` `python3` with `${__dirname}/server/probe.py`, two
members, 3.4 kB. `mcpb validate` (CLI 2.1.2) passed it, and before that verdict
was trusted the same validator was shown to reject three planted invalid
manifests (an unknown server type, a missing entry point, a missing name).

The server is standard-library Python. It logs each process start with its
interpreter, arguments, working directory, `HOME` and `PATH`; each message's
method and parameter keys; and any `_meta` under the 2026-07-28 key names. It
offers three tools:

- `probe_payload` — repeated ASCII of exactly *n* × 1024 bytes, built the way the
  first probe built it, so its sizes are a control against that record's table.
- `probe_real_body` — the real app-path body, repeated *n* times and joined by a
  blank line. The body is `AppSessions._snapshot(..., dry_run=True)` from the
  checkout's code against the confirmed private release (0.19.2, commit
  `172928b`), with no selection argument: **23,434 bytes**, ContentRef
  `b0ad0b62…`.
- `probe_report` — the receiving model posts back the END line it saw and whether
  the result arrived in the message body or as a file.

Before installation it was run locally over stdio with synthetic messages in both
protocol shapes, including a `tools/call` carrying 2026-07-28 `_meta`, and under
`/usr/bin/python3` 3.9.6, where `probe_real_body` returns the version it found
instead of crashing.

Three runs, each started by the user installing the bundle and sending prompts in
a new Desktop conversation:

| Run | Bundle | Log placement | Result |
| --- | --- | --- | --- |
| 1 | 0.1.0 | inside the extension directory | **lost**: uninstalling deleted the directory and the log with it |
| 2 | 0.1.0 | inside the extension directory | kept; copied out before uninstall |
| 3 | 0.1.2 | outside the extension directory, every line tagged with process id and client name | kept |

Desktop's own `~/Library/Logs/Claude/mcp.log` survived run 1 and supplies what
that run can still say.

## Measured

### Launch

Desktop resolves the manifest's bare `python3` through the user's login-shell
`PATH`. Its log reads `Using MCP server command: /opt/homebrew/bin/python3 with
path: {…}` followed by 25 entries; the server recorded `sys.executable`
`/opt/homebrew/opt/python@3.14/bin/python3.14`, version **3.14.7**, working
directory **`/`**, and `HOME` set to the user's home. Node-type extensions on the
same start are logged as `Using built-in Node.js for MCP server`; no Python
counterpart appears.

So the interpreter is whatever `python3` comes first on that user's `PATH`. On
this machine `/usr/bin/python3` is 3.9.6, and agent-bios requires 3.11 or later.
A bundle that names bare `python3` works here because Homebrew is earlier on
`PATH`, and that is a property of this machine, not of Desktop.

Desktop also logs `Era probe verdict: legacy (exec lane pinned — no sibling
probe)` for every stdio server, ours included. What it decides is not known; it
is recorded verbatim.

### Clients and protocol

| Run | Server processes | `claude-ai` 0.1.0 handshakes | `local-agent-mode-<server>` 1.0.0 handshakes |
| --- | --- | --- | --- |
| 2 | 9 | 3 | 2 |
| 3 | 4 | 2 | 1 |

Every handshake is `initialize` with protocolVersion **2025-11-25**. The
capabilities match the first record exactly: `claude-ai` declares only the
`io.modelcontextprotocol/ui` extension (`text/html;profile=mcp-app`);
`local-agent-mode` adds `roots` (`listChanged: true`). Neither declares
elicitation or sampling. No 2026-07-28 `_meta` arrived. Methods received:
`initialize`, `notifications/initialized`, `tools/list`, `tools/call` — nothing
else, `roots/list` included.

### Call shape: no conversation identity

All 16 `tools/call` requests in runs 2 and 3 carried exactly two parameter keys,
`arguments` and `name`. There is no `_meta`, no conversation or task identifier,
and no request field that distinguishes one Desktop conversation from another.
The first record saw the same on 2.9939.4, so this held across the update.

### Delivery size

The model reported every END line correctly, matching the nonce the server sent.

| Payload | Bytes | Run | Client | Delivery, as the model reported it |
| --- | --- | --- | --- | --- |
| real × 1 | 23,486 | 2 | not attributable | in the message body |
| real × 2 | 46,922 | 2 | not attributable | in the message body |
| real × 3 | 70,358 | 2 | not attributable | in the message body |
| ASCII 48 KiB | 49,152 | 3 | `claude-ai` | in the message body |
| **ASCII 49 KiB** | **50,176** | 3 | `claude-ai` | **in the message body** |
| **ASCII 64 KiB** | **65,536** | 3 | `claude-ai` | **in the message body** |
| real × 4 | 93,794 | 3 | `claude-ai` | in the message body |
| real × 6 | 140,666 | 3 | `claude-ai` | in the message body |

Run 3's calls all went through one process (pid 21271) whose handshake named
`claude-ai`. Run 2's log carried no process ids, so its calls cannot be tied to a
client from the log.

**The 48 KiB boundary the first record measured does not hold on 2.16120.0.** The
same ASCII bytes that 2.9939.4 saved to a file — 50,176 and 65,536 — now arrive in
the message body, and no payload up to 140,666 bytes was turned into a file.

## What the comparison does and does not separate

Two things changed between the first record and this one: the Desktop version
(2.9939.4 → 2.16120.0) and the registration route (the host configuration file →
a `.mcpb` bundle). **Which of them moved the boundary is not separated.**
Separating them would mean registering through the configuration file again, the
route the design rejects; no design decision depends on the answer, so it was not
done.

The client is a third candidate that this evidence cannot rule out. The first
record did not tie calls to clients. Its calls would have left a local agent mode
transcript if they had gone through that client, but the check for one is weak:
`local-agent-mode-sessions/` holds 206 `.jsonl` files, the newest modified
2026-07-12, and none since 2026-09-29. That means either local agent mode has not
run since July, or current versions write transcripts somewhere else. It does not
show which client carried the first record's calls.

**An END marker proves the model saw the end, not that it arrived inline.** In the
first record, payloads Desktop saved to a file came back with their END lines
correct too — the model read them from the end of the saved file. Only the
model's own report distinguishes body from file. The design's end-marker
mechanism claimed the marker proves inline delivery; that claim is wrong and has
to change.

## Not measured

- The new boundary. 140,666 bytes is the largest delivery seen, and nothing in
  runs 2–3 became a file.
- A tool call through the `local-agent-mode` client. Run 3 made none.
- `roots/list`. Declared by `local-agent-mode`, never requested by a server.
- A machine where the first `python3` on `PATH` is older than 3.11, inside
  Desktop. The 3.9.6 behaviour above is a local stdio test.
- Windows.
- Whether the model's report of body versus file is accurate. It is a
  self-report; the first record's file deliveries were reported as files, which
  is the only check it has had.

## Got wrong first

1. **The log lived where uninstall deletes.** Run 1 wrote inside the extension
   directory, and the instructions said to uninstall when done. Desktop removes
   the directory on uninstall, so the run's own record went with it.
2. **Two searches never ran and read as "not found".** This macOS has no
   `timeout` command. `timeout 100 grep … | head` exited 127 inside the pipeline
   and printed nothing, which looked like an empty result. It surfaced only when
   the exit status was printed; the search was rerun with a working time limit
   and a positive control.
3. **Run 2 was not tagged per process**, so three of its rows cannot name a
   client. Run 3 adds the tag; run 2 was not repeated because run 3's
   `claude-ai` rows cover larger payloads than run 2's.
