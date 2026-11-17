---
created_at: 2026-10-22T19:38:03+09:00
head: 2c1235a
kind: design
supersedes: null
---

# A JSONL record ends at a newline and nowhere else

The WP-06 real-data view build (run on `05e409a`, 2026-10-22) had `projection.py --sweep` refuse a
valid record, `UNSWEPT_RECORD …r22.jsonl:8: Unterminated string`. The sweep's reader cut the file with
`str.splitlines()`, which breaks at U+2028, U+2029, \x0b, \x0c, \x1c–\x1e and \x85 as well as at
"\n". JSON allows U+2028 and U+2029 raw inside a string, Claude Code writes them raw, and every
`json.dumps(..., ensure_ascii=False)` writer here keeps them raw. That record held two U+2028. Every
one of the run's 145,031 redacted lines parsed once the files were split on "\n" alone.

## Decided

**One splitter, `learn/jsonl_lines.py` `split`, cuts JSONL at "\n" only.** Every JSONL reader that used
`str.splitlines()` now calls it:

- `session-distill/runlib/records.py` `read_log` (the amendments log),
- `session-distill/runlib/evidence.py` `load` (the evidence store),
- `session-distill/runlib/gate.py` `Call._jsonl` (host-written capture rows),
- `session-distill/runlib/projection.py` `documents_in` (the sweep),
- `learn/migrate-learnings.py` `prune_jsonl` and `migrate` (the user's `learnings.jsonl`, written raw
  by `learn/collect-learning.py`). The prune is the one that damaged data: it keeps lines it cannot
  parse and joins what it keeps with "\n". A record holding U+2028 came back as malformed pieces, with
  "\n" written where the character had been.

The owner sits in `learn/` because the direction rule decides it. Shipped code (`learn/`) reads JSONL
too and may not import author-side code. `session-distill/runlib` is author-side and may import
shipped code. So the one owner is shipped, listed in `package.json` `files[]`. `runlib/records.py`
loads it by its literal path and re-exports it as `records.jsonl_lines`. `dispatch.py` `DYNAMIC_LOADS`
declares that load, so the closure trace follows it. `learn/migrate-learnings.py` loads it the same
way it loads its other siblings.

Each of the six reader sites has a control, `jsonl-line-separators-inside-a-string-read-whole`. The
control writes one record holding raw U+2028 and U+2029 inside a string and requires it read back
whole. Reverting any one site to `str.splitlines()` fails that site's control by name.

Readers left as they are, and why:

- File iteration (`for line in handle`, e.g. `collect-learning.py`'s drain) breaks text at "\n", "\r"
  and "\r\n" only.
- `bytes.splitlines()` (`census.py`) breaks at "\n", "\r" and "\r\n" only.
- `views.py`'s clipper and error-line reader (`clip_parts`, `error_lines_of`) split tool-result text into
  display lines, not JSONL.
- `packet.py`, `stop.py` (ps output), `migrate-ledger.py` (source code), `collect-learning.py` and
  `migrate-learnings.py`'s prose and bundle readers split Markdown or command output, not JSONL.
- The remaining `str.splitlines()` JSONL reads sit inside self-tests (`views.py`, `gate.py`,
  `monitor.py`, `breaker.py`, `distill.py`, `migrate-learnings.py`'s `local_ids`). They read fixtures
  and golden outputs that this repo writes without those characters, so the defect cannot reach a
  verdict through them.

## Closed

**Escape U+2028 and U+2029 at every writer instead.** This is ruled out because the captures and
transcripts that matter are written by the hosts (Claude Code, codex), not by this repo. Escaping at
our writers would cover only our own files. The host-written files reach the same readers, so the
reader is the one place a fix covers both.
