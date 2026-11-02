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

## F-22 — a Codex activation pins an id no transcript on disk carries

Found by the WP-07 match check (2026-10-23, run against the owner's own state, counts only). Every
pinned Codex session is unjoinable to a transcript, so its selection and delivery can only ever be
reported `unknown`, however complete the rollout beside it is.

What agent-bios records: `create_codex_session` (`compose/instructions_session.py`) starts a thread
over the app-server, validates `thread['id']`, and pins that id — `requested_session_id`, then
`session_id` through `observe_and_pin` — with `evidence = {'method':
'thread/start+inject_items+read', 'thread_path': thread.get('path')}`. All 15 pins on this machine
carry that method and a `thread_path`, and in all 15 the pinned id is the uuid in that path.

What the CLI's transcripts use: `~/.codex/sessions/**/rollout-<date>T<time>-<uuid>.jsonl`, the uuid
being the rollout's own session id (24 of the 2,631 files carry a second uuid appended, the fork
shape). `runlib/sources.py` discovers exactly these.

Why no join is possible today, measured 2026-10-23: 15 pins, 2,631 rollouts, 2,614 distinct rollout
uuids; 0 of 15 pin ids occur in any rollout file name, 0 occur in any rollout's opening records, and
0 of the 15 recorded `thread_path` files still exist — none matches a rollout by name or by uuid
either. Rollouts covering the same 23–34 day span are present in quantity, so this is not retention.
The app-server thread store and the CLI rollout store are two stores, and the pin names the first.

Alternatives:

1. **Record the rollout the host actually writes.** At activation, resolve the thread to its rollout
   (the app-server's own path, or the CLI's store) and pin that path and its id beside the thread
   id. Risk: it depends on an app-server field whose shape is the host's to change, and the same
   `thread_path` it already records has proved to be a path that stops resolving.
2. **Join after the fact, from the transcript's own side.** The activation injects a developer item
   carrying `agent-bios session snapshot: <content_ref>`; a reader could find the rollout that
   carries that `content_ref` and bind the pin to it. Risk: it is evidence inside the model's
   context rather than an identifier, so a compaction or a fork can carry or lose it, and two
   sessions activated from one snapshot share the string.
3. **Leave it unknown and say so.** Keep reporting Codex selection and delivery `unknown` with the
   id-space reason. Risk: Codex coverage stays at zero for every past-session diagnosis, and the
   gap is invisible to anyone reading only a Claude-shaped result.

Not in scope here: a time-window or `cwd` match. A wrong join attributes one session's delivered
bytes to another, which is worse than `unknown`, and nothing in the data tells a right guess from a
wrong one.

---

## F-24 — the Codex context-evidence probe waits on `select()` for a line Python already buffered

`wrappers/codex_frame_filter.py` `app_server_sources` starts `codex app-server` with
`text=True, bufsize=1`, then loops `select.select([proc.stdout], …, 1)` and `readline()`.
`select()` judges the descriptor. If a notification and the response arrive in one read, the
response stays in Python's buffer and the descriptor never becomes ready again. After the
60-second timeout the probe returns "no answer", and `codex-run.sh` exits 3 with
"effective-context evidence failed; refusing to dispatch", blamed on Codex. The Python
documentation says nothing about data buffered above the descriptor, so no contract covers the
assumption. `compose/instructions_session.py` `AppServer` already does the same job with a
reader thread and a `queue.Queue`, which has no such hazard (row C-4).

Alternatives:

1. **Read with a thread and a queue, as `AppServer` does.** Risk: one more thread to shut down
   on every exit path.
2. **Read the descriptor unbuffered (`os.read`) and split lines in the probe.** Risk: the probe
   then owns partial-line and decoding handling that the text layer did before.

---

## F-26 — hermetic evidence is rebuilt from record kinds the vendor calls internal, and a rename is misnamed

`wrappers/claude_hermetic_evidence.py` reconstructs the requests a review call sent, and the
context it loaded, from transcript records: `api-request`, `api-request-shape`,
`api-request-blob`, and `attachment` of several types. None of these appear in a published
page, and the vendor says the format "can break on any release". When a kind is renamed the
helper returns an empty context, and the gate refuses every dispatch for a context mismatch.
That fails closed, but the refusal names the call, not the drift, so an operator looks for a
packet error first (rows B-4, A-3). `DEPENDENCIES.md` pins the reliance to 2.1.304, and 2.1.310
is installed.

Alternatives:

1. **Validate the record kinds seen against the expected set, and refuse naming the drift and
   the host version.** Risk: the expected set becomes one more host restatement to re-measure
   per release.
2. **Stop using the transcript as evidence, and prove hermeticity from inputs we control.**
   Inputs we control are the flag set, the empty homes and the stream's `system/init`.
   Risk: the stream is also undocumented in part (row B-5), and the proof of what was loaded
   weakens to a proof of what was offered. This is the owner decision named in the dated
   record.

---

## F-29 — blocking `flock` writers have no deadline, so a wedged holder hangs them without a message

`compose/instructions_transaction.py` `_transaction_lock`, `compose/instructions-state.py`
`_deploy_lock`, `launch/agent-launch.py`, `learn/collect-learning.py` and
`decisions/record-decision.py` take `LOCK_EX` and wait forever. The Windows emulation in
`compose/host_platform.py` retries forever. `flock` is inside its contract, but AGENTS.md §12
makes not hanging on an environment fault our part, and a holder stuck in I/O or stopped in a
debugger makes the installer, the launcher and the decision recorder wait with nothing on the
screen. `session-distill/runlib/stagelock.py` already shows the named shape: `STAGE_LOCKED
<name>` at a deadline (rows C-16, C-17, C-35).

Alternatives:

1. **Wait with a deadline, then refuse naming the lock and, where readable, its holder.**
   Risk: a long legitimate hold, a slow install for instance, is refused.
2. **Print a "waiting for <lock> held since …" line after a short delay and keep waiting.**
   Risk: it still hangs; it only stops hanging silently.

---

## F-30 — the Codex app-server, labelled experimental by its vendor, carries private activation and context evidence

`compose/instructions_session.py` drives `codex app-server` over stdio for private Codex
activation: `initialize`, `config/read`, `hooks/list`, `thread/start`, `thread/inject_items`
and `thread/read`. `wrappers/codex_frame_filter.py` uses it for context evidence. The vendor's
app-server page says the command "and WebSocket transport are experimental and aren't supported
for production workloads"; the developer-commands page says it "may change without notice". Six
names the code depends on are not in the documentation read: `developerInstructions`,
`experimentalRawEvents`, `thread.path`, `config/read`'s `includeLayers`/`layers`, `hooks/list`'s
`cwds`, and the `sessionFlags` label. A removed method fails loudly. A field that merely comes
back empty (`developer_instructions`) silently drops the user's own developer instructions from
the composed session (rows A-2, B-13).

Alternatives:

1. **Accept the surface explicitly: pin the Codex version the shapes were measured on, and
   refuse by name on an unknown shape, empty fields included, as `codex-run.sh` does for its
   capture.** Risk: every Codex release needs a re-measure before private activation works.
2. **Move each use to a documented surface where one exists.** Examples: `codex debug
   prompt-input` for what the model sees, and config files read directly for layers. Risk:
   some uses (thread injection) may have no documented equivalent.

---

## F-31 — two gaps in what "hermetic" claims for a Claude review call

`wrappers/claude-run.sh` builds the hermetic call with `--setting-sources ""` and `--safe-mode`.
The CLI reference documents `--setting-sources` as a comma-separated list of `user`,
`project`, `local`; an empty value is not described. `--safe-mode` is documented to keep
"Managed settings policy … including policy-configured hooks, status line, and file-suggestion
commands". Managed settings live in a system directory outside every path the evidence check
(`claude_hermetic_evidence.py` `SURFACES`) inspects. On the owner's single-user machine both are
dormant. As a property of the receipt's claim, they are the gap between measured clean on
2.1.304 and guaranteed clean (rows A-8, A-9).

Alternatives:

1. **Probe both on each pinned version: a planted user setting must not load under `""`, and
   the presence of a managed-settings file is recorded and refused.** Risk: the probe needs a
   real host call per version, which costs a call and its tokens.
2. **Record both as named residuals in every hermetic receipt.** Risk: the receipt then
   promises less than "loaded nothing of the owner's", and readers must notice the residual.
