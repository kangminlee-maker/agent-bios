# Findings — open implementation defects

Live queue, kept current. **Only open items live here.** Closing one means deleting its entry,
not annotating it — the reasoning belongs in that round's dated record, where it stops needing
maintenance.

A per-entry status field is the thing that goes stale, because closure often arrives as a side
effect of a decision taken under another name and nobody walks back to mark it. A file with no
status field cannot drift that way, so `gates/check-lexicon.py` fails if resolution markers
appear here.

These are defects in the **product**, not in the ontology. Judgements about the ontology's own
claims live in `ontology/instances/graph.json` (`verdicts`, `decisions`), which is a deliberate
split: a decision about a golden relationship and a decision about the CLI surface answer to
different authorities.

Every entry names its alternatives. An item with one path is not a finding, it is a task.

---

## F-17 — conditional prohibitions in the selected startup instructions need evaluation

`claude/CLAUDE.md` embeds prohibitions inside longer conditional bullets, including
runtime enforcement, lifecycle ownership, destructive operations, and spawn policy.
The private compiler preserves the selected rule text in startup snapshots. Moving
its delivery out of native global files does not establish that a model recognizes
and follows those clauses under context pressure; child reach is a separate question.

The structural observation is supported by the current canonical text. A comparative
behavior result for the current private delivery path is not established here. Review
must preserve each prohibition's intended scope and use a relevant activated snapshot;
a count of clauses or a shorter rewrite alone does not demonstrate better behavior.

Alternatives:

1. **Extract standalone boundaries within a reduction.** Remove the clauses being
   replaced and show their scoped meaning at the new location. Risk: a standalone
   prohibition may lose the condition that made it correct.
2. **Keep the current wording.** Accept the unresolved recognition risk if an
   appropriately scoped comparison does not justify the change.
3. **Enforce decidable boundaries in the owning tool.** Use capability, validation,
   or ownership checks where the action can be controlled; retain prose for judgments
   and surfaces without that authority. Each change needs its own negative control.
4. **Evaluate another current delivery surface.** Compare guide, requested procedure,
   or session-specific delivery against startup placement using `SURFACES.md`.
   Stay within the canonical always surface's 20 KiB ceiling and test main/child reach
   separately before adopting a placement.

These alternatives remain open; enforcement and prose placement can be combined
for different clauses. Any behavior experiment needs a bounded question and scope.

---

## F-18 — an activation whose host never wrote a transcript stays pending with no way out

`claude_evidence` in `compose/instructions_session.py` accepts exactly one proof that a
requested session became real: a native transcript at
`<config home>/projects/<slug>/<session id>.jsonl`. Claude does not create that file until
the user submits a first turn, so closing the window without typing anything leaves the
intent in `PREPARED` permanently — the file it waits for will never arrive.

Nothing retires such an intent. `recover_activations` re-reads every journal on each launch
and applies no age test; the journal's `created` field is written by `prepare` and read
nowhere else; no code path removes an activation directory. The intent therefore prints
"activation(s) lack host evidence" on every later launch, and `_active_intents` in
`compose/instructions_install.py` makes `uninstall` preserve the release directory instead
of removing it. Starting a session and closing it untouched is ordinary use, so the cost
falls on a correct action.

Observed 2026-09-29 on the author's machine: one intent from 2026-09-16T07:14 had held this
state for thirteen days. Its `SessionEnd` hook snapshot recorded `duration_sec: 0`, zero
tokens, and zero transcript entries scanned, so the transcript was never written rather than
deleted. A retry 34 minutes later reached `PINNED` only because a single `/exit` command
made Claude write a 3 KB transcript. Removing the journal directory by hand cleared the
warning, and that is currently the only route.

Alternatives:

1. **Widen the evidence set.** Accept a host artifact that exists from session start, such
   as the per-session environment directory. Risk: those paths answer to the host and to
   hook configuration rather than to a contract agent-bios holds, so the check would pass
   where they exist for unrelated reasons and fail where a user has pruned them.
2. **Retire an intent by age.** Read `created` and drop an evidence-less intent past a
   threshold. Risk: the threshold is a judgement, and a host that writes its transcript
   late would have a real session discarded without notice.
3. **Decide at launch rather than at recovery.** When the child exits having produced no
   transcript and no tokens, discard the intent in place instead of retaining it. Risk:
   `launch` would be inferring host-internal state, and a crash that loses a real session's
   first turn becomes indistinguishable from an empty one.
4. **Expose an explicit cleanup path.** Add a command that lists evidence-less intents and
   forgets a named one. Risk: it resolves nothing on its own — the operator must know the
   command exists and that the warning is actionable.

---

## F-19 — an observed input excess can still end without a stop

Round 5 of the seam06 review (hermetic, 2026-10-22, on 0292cdf; findings BE#0 and BE#1) reproduced two
paths on which a view-window call's observed input is above 120k and the supervisor ledger records no
`stopped` entry, so later admission stays open. (1) `_stop_run` handles only `stagelock.Locked` from the
declaration lock; a mode-000 `declaration.lock` (PermissionError) or a lock symlink leaving the run
(`Escaped`) escapes before the ledger write. (2) The excess is established in settlement before
call.json, the receipt and `charge` run; a failure in any of them (`RECEIPT_MISSING`, calibration.json
unreadable) ends the call before `_stop_run`. The review ended at round 5 by the owner's decision; this
must be closed before WP-08, the first stage that dispatches view-window calls. No stage before WP-08
dispatches one.

Alternatives:

1. **Persist first.** Write the strongest stop as soon as the excess is established, before any fallible
   settlement work, and turn every declaration-lock acquisition failure into an unstamped stop written
   under the supervisor lock. Risk: the stop is written before the call's own record, so the record must
   still be completed or its absence reported.
2. **Finalisation path.** Keep the order and guarantee the stop write in a `finally` that runs whatever
   fails after the excess. Risk: an exception inside the finaliser itself, and two code paths that must
   agree on the stop.

---

## F-20 — a stop's own diagnostic and the stop-ordering control are weaker than the record says

Round 5 findings BE#2 and BE#3 (minor). The stop path's broad handler labels a programming error after a
successful declaration read (e.g. inside `bound.committed`) as `declaration-unreadable`; when an earlier
terminal stop is kept, that error survives only in the returned object and is neither persisted nor in
the refusal detail. `STOP_ACQUIRING` is set before the real lock attempt, so the BD#2 control can pass
on a favourable schedule. The dated record T1840 claims each call records its own stop and that the
control forces acquisition order; neither holds.

Alternatives:

1. **Record per call.** Persist each call's stop diagnostic in its call record (or an append-only stop
   log) independent of which ledger stop wins, distinguish read failures from stamping bugs, and signal
   from an instrumented acquisition after observed contention; supersede T1840.
2. **Report only.** Carry the diagnostic in the refusal detail and accept that the ledger keeps only the
   strongest stop. Risk: a stamping bug stays invisible once a terminal stop exists.

---

## F-21 — JSONL readers split a record on characters JSON allows inside strings

Found by the WP-06 real-data view build (2026-10-22, run on 05e409a). `projection.py --sweep` refused a
valid record (`UNSWEPT_RECORD`) because `documents_in` uses `str.splitlines()`, which also splits on
U+2028/U+2029 (and \x0b, \x0c, \x1c–\x1e, \x85); Claude Code writes U+2028/U+2029 raw inside strings and
`json.dumps(..., ensure_ascii=False)` keeps them raw. The same reader shape is in `evidence.py` (its
writer uses `ensure_ascii=False`), `gate.py` `_jsonl` (host-written capture rows) and `records.py`
(the amendments log). With a `\n`-only split that run's sweep reported 7 residual members in shapes the
owner judged no-secret on 2026-10-22.

Alternatives:

1. **One `\n`-only JSONL reader** used by every site, with a U+2028/U+2029 control per site.
2. **Escape at every writer.** Ruled out for host-written captures and transcripts, which are not ours to
   write; it would cover only our own files.
