---
created_at: 2026-10-21T17:52:00+09:00
head: 4ca7c8a
kind: design
supersedes: null
---

# Session distill implementation plan: addendum for WP-04

This record settles four readings raised while implementing WP-04 (the Codex capture mode) of
`2026-10-20T2119--cc0498f--implementation-plan.md` against
`2026-10-20T1942--9684f05--mechanism-design.md`: the HTTPS attempt rule of design §3.2, the
usage of an interrupted attempt, the mixed-coverage fixture, and the capture's file inventory. The plan and the design stand
otherwise.

## A warning-free HTTP call is never complete

Design §3.2 says an HTTPS attempt that failed before streaming is seen only in
`codex_core::responses_retry` warnings, and that HTTPS attempt coverage is complete only when
those warnings reconcile. Probe 9 (`distill-probes-20261020/codex-accounting/RESULTS.md` §2.5)
measured that an HTTP 500 is retried silently: two posts and one stream, with no `--json` event
and no warning at the levels the probe opened. In that case the absence of a warning would read
as "no attempt failed", and a call with an invisible failed post would be reported complete.

The reading this record takes:

- On the HTTP transport nothing records the posts themselves, so no count of warnings can show
  that every post was seen: one warning for one retry says nothing about a second post that
  failed silently beside it. A thread with any request over the HTTP transport, that is, any
  request not seen as a websocket frame (the fallback, or an HTTP post), reports attempt coverage
  `unknown`, with or without warnings. Warnings are still counted, each as the failed post it
  names.
- Only a thread made entirely of observed websocket frames can be `complete`.
- (Review round 2 of WP-04 corrected this rule, 2026-10-21: an earlier wording accepted a thread
  whose warnings were at least one and at least its interrupted streams.)
- Such calls therefore fail `USAGE_ATTRIBUTION_UNKNOWN` at the gate. This is fail-closed, and
  the transport fallback is rare.

Implemented in `wrappers/codex_frame_filter.py` (`attempts`) with a golden control (an HTTP
call with the retry channel captured and no warning, and one with a warning beside a silent
failure, both read `unknown`). The replay of probe 9's `f-http-500-once`, with the retry channel
declared and with a planted warning, is held in `gates/check_parity.py` `codex_run`.

**Closed:** treating a warning-free HTTP call as complete; treating an HTTP call as complete
because its warnings cover its interrupted streams.

## An interrupted attempt is unresolved in the capture

Plan WP-04 (Artifacts, and done-when 4 at line 482) says the HTTP-drop recording yields an
interrupted attempt with provisional usage. Design §13.3's estimate is the same agent's previous
request plus the content added since it. The capture keeps no content (its allow-list drops
every body), so that estimate cannot be formed there, and the earlier prototype's figure — the
thread's later completion — is not the previous request. The reading this record takes: the
capture records such an attempt `unresolved`, with no estimate; the supervisor, which reads
the content live (`runlib/monitor.py` on WP-02), remains the place a provisional estimate is
made.

**Closed:** estimating an interrupted attempt from another request's usage in the capture.

## The mixed-coverage fixture is golden

Plan WP-04 done-when 4 (line 482) and design §3.2 name a retained mixed-coverage recording. No
such recording exists among the probes (`distill-probes-20261020/codex-accounting`, the probe 9
recordings). The mixed-coverage control in `gates/check_parity.py` `codex_run` is therefore a
golden variant of the retained `f-normal-ws` recording (one otel completion moved to a second
thread), declared as golden in that fixture's PROVENANCE. A retained recording replaces it
when WP-04v or the rehearsal produces one. The HTTP-retry reconciliation through a warning is
golden for the same reason: the retained `f-http-500-once` recording carries no warning.

**Closed:** describing the mixed-coverage and warning-reconciled fixtures as replays.

## frames.jsonl holds the frames and the otel rows

Plan WP-04 (Artifacts) lists `frames.jsonl` and `otel.jsonl` as separate capture files. The
capture writes one file, `frames.jsonl`, holding the reduced frames, the otel rows and the
retry warnings in the order the trace printed them, because the completion ledger's join and
the attempt reconstruction read their relative order, and because WP-02's gate reads that one
file (`capture/frames.jsonl`). No `otel.jsonl` is written. The capture's file inventory is
`frames.jsonl`, `events.jsonl`, `host.json`, `usage.json`, `prompt-input.txt` and
`instruction-sources.json`; there is no rollout copy, since the hermetic profile runs
`--ephemeral` and writes none.

**Closed:** a separate `otel.jsonl` beside `frames.jsonl`.
