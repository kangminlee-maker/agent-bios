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

## F-23 — `install.sh` uses a temp-file form GNU `mktemp` refuses, and the abort restores the wrong manifest

`install.sh` creates three logs with `mktemp -t <word>` (in `cmd_install`, `cmd_verify` and
`cmd_onboard`), as does `gates/check-parity.sh`. The macOS `mktemp(1)` builds a template from
the prefix. The GNU manual requires "at least three consecutive 'X's in the last component" and
marks `-t` deprecated. `package.json` declares `linux`, and under `set -euo pipefail`
`cmd_install` aborts at that line. By then every file is deployed, but the status projection has
not run and `INSTALL_COMPLETED=1` has not been set. The EXIT trap then copies the previous
manifest back over the new install, which is the reading its own comment calls the worst one:
`uninstall` later removes the wrong set. No CI job runs `install.sh` on Linux; the ubuntu jobs
only run `bash -n` and a PATH probe on `packages/posix/install.sh`. The form is on `main` and
absent from the published 0.19.3. The hook and the wrappers already use the portable
`mktemp "${TMPDIR:-/tmp}/name.XXXXXX"` form. Not reproduced on Linux; the code was read and the
GNU contract quoted (`design/dependency-contracts/`, row C-3).

Alternatives:

1. **Use the portable template form at all four sites, and add a Linux job that runs
   `install.sh install --non-interactive` in a sandbox HOME.** Risk: the job is new CI surface
   to keep green.
2. **Drop `linux` from `package.json` `os` until such a job exists.** Risk: it withdraws a
   declared platform from users who may already depend on it.

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

## F-25 — `agent-bios cost` reports `$0.00` without a word when a transcript usage key moves

`session-cost.py` sums `message.usage.{input_tokens, output_tokens, cache_read_input_tokens,
cache_creation_input_tokens, …}` from Claude transcript records. The vendor's sessions
documentation says the entry format "is internal to Claude Code and changes between versions".
A renamed key reads as zero, and a bad JSON line is skipped uncounted, so the user-facing report
prints a cost of nothing and names no cause (row B-2). AGENTS.md §12 puts validating a
no-contract input, and refusing a drift by name, on our side.

Alternatives:

1. **Count the records that carry a `usage` object but no recognised key, and report them by
   name with the host version.** Risk: a host that adds keys without removing any raises a
   false alarm unless the check is about missing keys, not extra ones.
2. **Refuse to print a total when any assistant record has an unreadable usage shape.**
   Risk: one odd record withholds a report that was otherwise right.

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

## F-27 — the zsh wrapper's subcommand exceptions are a measurement of one Claude version

`launch/agent-launch.zsh` prepends `--dangerously-skip-permissions` to a bare `claude <verb>`.
It skips this only for six verbs measured on 2.1.280 (`logs attach stop kill respawn rm`),
because a leading flag turns those subcommands into a new session whose prompt is the verb. No
document states which subcommands stop parsing after a flag. A verb added later, typed bare,
starts a permission-skipping session with the verb as its prompt, silently (row A-11).

Alternatives:

1. **Invert the rule: prepend the flag only when the first argument is not a subcommand
   `claude --help` lists, probed once per installed version and cached.** Risk: one probe of
   help text per version; help prose is not a contract either, so a failed probe must leave
   the flag off.
2. **Prepend the flag only for a bare `claude` and for the documented prompt flags.** Risk:
   users lose the bypass for forms the current list allows.

---

## F-28 — `codex-helm.sh` reads a non-terminal stdin to EOF, so an idle inherited stdin hangs it

`codex-helm.sh` takes a piped prompt with `if [ ! -t 0 ]; then stdin_prompt="$(cat)"`, its
`--dry-run` included. A caller that runs it with an open, idle stdin hangs it at 0% CPU.
Python's `subprocess` passes the parent's stdin by default. The gate (`invoke`, `stdin=DEVNULL`)
and `install.sh` (`exec </dev/null`) fixed their own calls after it hung the gate for ten
minutes. Nothing checks the other callers (row C-5).

Alternatives:

1. **Read stdin only when the caller asks for it (an explicit `-`), and never in
   `--dry-run`.** Risk: a documented pipe usage changes and needs the flag.
2. **Bound the read with a deadline and name the timeout.** Risk: a slow but real producer is
   cut off.

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
