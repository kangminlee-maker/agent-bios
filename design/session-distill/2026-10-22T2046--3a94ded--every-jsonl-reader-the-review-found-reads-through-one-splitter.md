---
created_at: 2026-10-22T20:46:09+09:00
head: 3a94ded
kind: review
supersedes: 2026-10-22T1938--2c1235a--a-jsonl-record-ends-at-a-newline-and-nowhere-else.md
---

# Every JSONL reader the review found reads through one splitter, from the file's bytes

The 1938 record listed six readers and said every JSONL reader that used `str.splitlines()` now
used the one splitter. It was wrong on three counts. Round 1 of the F-21 review (`3a94ded`, FA#0 to
FA#4) found seven more readers in `compose/` and `wrappers/` with the same defect. It found that
text-mode reading turns a bare CR, which JSON allows as whitespace, into a line break before any
splitter runs. And it found that the package gate could not see the splitter. This record replaces
the 1938 one and says what is true now. Its reason, U+2028 and U+2029 raw inside JSON strings,
still stands.

## What is true now

**The owner is `wrappers/jsonl_lines.py`: `split(text)` cuts at "\n" only, and `read(path)` decodes
the file's bytes as UTF-8 and then splits.** It moved out of `learn/` because the compatibility
install copies `wrappers/claude_hermetic_evidence.py` into `$CLAUDE_DIR/bin` on its own. That helper
finds the splitter beside itself, the same rule `claude-run.sh` applies to the helper, so
`install.sh` deploys `jsonl_lines.py` beside it, verifies it, and removes it with the helper. Every
other consumer loads it by path inside its own package root, with no `sys.path` search and no
fallback, and fails naming the path when it is missing:

- `compose/host_platform.py` `jsonl_read` / `jsonl_split`, for `compose/` (`../wrappers/jsonl_lines.py`);
- `learn/migrate-learnings.py` `load_jsonl_read` (`../wrappers/jsonl_lines.py`);
- `session-distill/runlib/records.py` (`records.jsonl_lines`, `records.jsonl_read`), declared in
  `dispatch.py` `DYNAMIC_LOADS`.

Layouts checked: the checkout and the npm package hold the same tree. The private release copies every
`files[]` path at its relative path (`instructions_install._copy_release`), and the launcher and
the collector load `compose/` from that package root. The Windows bundle stages the whole package
tree as `release/package`. The compatibility install's helper copy has the splitter beside it.
`gates/check_parity.py` `claude_run` copies the adapter alone, then adds the helper, then adds the
splitter. The helper without the splitter fails naming `jsonl_lines.py`, and the full copy runs.

**Thirteen readers use it, each from bytes, each with its own controls.** For each reader,
`jsonl-line-separators-inside-a-string-read-whole` reads raw U+2028 and U+2029 inside a string
back whole. A bare-CR control reads a record with a bare CR between tokens and a CRLF line ending
back whole. In the session-distill, learn and wrappers modules it is
`jsonl-bare-cr-whitespace-and-crlf-read-whole`; in the compose tests one test per site carries
both cases. Reverting any one site to `str.splitlines()` fails its own control by name. Reverting
it to text-mode reading fails the bare-CR control.

| Reader | Site |
|---|---|
| amendments log | `session-distill/runlib/records.py` `read_log` |
| evidence store | `session-distill/runlib/evidence.py` `load` |
| capture rows | `session-distill/runlib/gate.py` `Call._jsonl` (it already decoded bytes) |
| sweep | `session-distill/runlib/projection.py` `documents_in` |
| learnings prune | `learn/migrate-learnings.py` `prune_jsonl` |
| learnings ids | `learn/migrate-learnings.py` `migrate` |
| private learning events | `compose/instructions_store.py` `_learning_events` |
| legacy migration, source | `compose/instructions_install.py` `_legacy_events` |
| legacy migration, destination | `compose/instructions_install.py` `_event_destination_conflicts` |
| legacy migration, byte check | `compose/instructions_install.py` `_verify_transferred_events` |
| legacy migration, apply | `compose/instructions_install.py` `migrate` apply path |
| init row | `wrappers/claude_hermetic_evidence.py` `stream_mcp_servers` |
| result row | `wrappers/claude_hermetic_evidence.py` `result_object` |

Each site keeps its comparison and rewrite behaviour. Lines are compared and rewritten as the
splitter returns them, so a CRLF record keeps its CR when it is written back.

**The package gate sees a module loaded by path.** `gates/check-package.sh` walks every chain of
string segments joined with `/` that names a python file of the repo (`REPO / "learn" / "redact.py"`,
`… / "wrappers" / "jsonl_lines.py"`) in each walked file, as it walks imports. Its negative control
drops `wrappers/jsonl_lines.py` from `files[]` and requires a failure naming it.

## Left as they are, and why

- Text-mode iteration and `bytes.splitlines()` readers keep their current shape. They are
  `learn/collect-learning.py` `read_jsonl_records`,
  `wrappers/claude_hermetic_evidence.py` `read_records`, `wrappers/codex_frame_filter.py`
  `read_jsonl`, `compose/instructions_session.py` `claude_evidence`,
  `compose/instructions_understand.py` `_transcript` (`bytes.splitlines()`), and the legacy
  `session-distill/census.py`, `digest.py` and `plain-asks.py`. They split at "\n", "\r" and "\r\n",
  never at U+2028 or U+2029. They differ from the splitter only on a bare CR between tokens. No
  writer we know of emits one, and a JSON string cannot hold a raw CR.
  **Revisit when** a host or one of our writers is seen emitting a bare CR as whitespace in JSONL.
- `views.py` `clip_parts` and `error_lines_of` split tool-result text into display lines, not JSONL.
- `packet.py`, `stop.py`, `migrate-ledger.py`, and `collect-learning.py` and `migrate-learnings.py`'s
  prose and bundle readers split Markdown, source code or command output, not JSONL.
- The JSONL `splitlines()` reads inside self-tests and unit tests (`views.py`, `gate.py`, `monitor.py`,
  `breaker.py`, `distill.py`, `migrate-learnings.py` `local_ids`, `claude_hermetic_evidence.py`'s
  transcript fixture, the compose tests' readers) read fixtures written without those characters.
  The defect cannot reach a verdict through them.

## Closed

**Escape U+2028 and U+2029 at every writer instead.** This is ruled out because the captures, streams
and transcripts that matter are written by the hosts, not by this repo. Escaping at our writers would
cover only our own files.

**Keep the owner in `learn/` and also copy it into the compatibility install's bin.** This is ruled
out because the helper would then need two locations, beside itself in that install and `../learn`
in a checkout, which is a fallback. With the owner in `wrappers/`, each consumer has one location.
