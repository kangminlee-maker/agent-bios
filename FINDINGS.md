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

## F-33 — a forked Codex thread's activation pins no transcript until a fork's naming is measured

A Codex activation resolves the rollout the host wrote in two steps, and since review X round 2
both steps go through one test (`_rollout_of_thread` in `compose/instructions_session.py`): the
candidate must lie inside the resolved configured home's sessions tree, have one link, and carry
exactly one id in its name, that id being this thread's. The host's index row is an association
by itself, but it carries only a path, so it is held to the same test — and a rollout the host
names with two ids, which is how a fork is written (`rollout-<when>-<parent>-fork-<child>.jsonl`),
is refused by the single-id rule.

The effect is a class of sessions, not an edge case: every activation of a thread the host forked
records `rollout_path: null`, `rollout_id: null`, `rollout_method: "rollout_unresolved"`, with both
attempts named on stderr. To the inventory that pin reads `rollout_unresolved` on its own
`--pin` evidence path, and the rollout itself, which no pin then names, reads `unpinned` or
`rollout_unmatched` depending on the state's other pins. Nothing is wrongly attributed; a forked
session's selection and delivery are simply unknown.

This follows D-20261111-18c350 deliberately — a path is not an association, and a wrong join
attributes one session's delivered bytes to another — and the refusal is the safe direction. What
is not established is the premise the rule rests on for forks: which of a fork name's two ids is
the thread the row answers for. Evidence (the lead's independent reproduction over
`062b76d..49477a0`, 2026-11-11): the probe `index_row_fork_named_file` resolves `index` on
6bdb4db, where the index step took the last id of the name, and resolves nothing on acc301c and
49477a0. No measurement of a real fork exists; the 2026-11-11 measurement under a temporary
`CODEX_HOME` covered a new unforked thread only.

Closing it needs that measurement on the installed host: what the host names a fork's rollout,
whether the file's `session_meta.id` is the fork's own thread id or the parent's, and whether the
index row for a forked thread points at the fork's file or the parent's. Then one of these:

1. **Admit the fork shape in the index step only.** The row is the association, so take the path
   it names and read the id from the fork position of the name. Risk: it rests entirely on the
   naming convention being stable and on the fork position being the thread the row answers for;
   if either is wrong the join is silent and wrong, which is the failure this rule exists to
   prevent.
2. **Admit it in both steps.** A fork-named path from `thread.path` is this thread's by the same
   reading. Risk: the same, plus `thread.path` carries no association at all, so a stale path to
   a fork of another thread would be accepted on its name alone.
3. **Carry the row's claim as a weaker evidence kind.** Resolve the fork's path but record it as
   its own `rollout_method`, so a reader can tell a name-agreed join from a row-only one. Risk: a
   new evidence grade that no current reader distinguishes, which reads as a join until every
   consumer is taught the difference.
4. **Leave it refused and say so to the user.** Keep the rule and name the fork case in the
   activation's message, so a forked session's owner knows why its pin records no transcript.
   Risk: a whole class of sessions stays unknown for as long as nobody measures the naming.
---

## F-32 — two of C2's thirteen calls had their structured output refused inside the host

Found by WP-08e's reading of C2 (2026-11-10, the run's usage and call records, counts only). S3's window 8 of the
Codex child and S4's formation call each made two main requests in one call: the host refused the first structured
output and asked again, so the second request carried the first answer and the refusal on top of the packet. The
two second requests added 1,118 and 584 tokens beyond the first request and its answer, and read 61,030 and 26,794
input tokens. Neither call failed: the stage accepted each second answer.

WP-08e budgets the retry (`dispatch.RETRY_ERROR_TOKENS`, the retry line of S3's estimate, S4's claim) and does not
reduce it. At C2's rate a retry is about one call in seven, and each one costs a second request of the whole packet
and a first answer.

Alternatives:

1. **Name the constraint the refused answers broke, and state it in the packet.** The refusal is in each call's
   capture; reading it is reading the run's text, which WP-08e did not. Risk: a rule written for one refusal adds
   packet bytes to every call and may not be the next refusal's.
2. **Hand the constraint to the stage's own check.** Where the stage re-checks what the schema states, the schema
   could state less, so the host refuses less and the stage's one corrective retry carries the message. Risk: the
   dispatcher's retry is a new call with the whole packet, dearer than the host's in-call retry.
3. **Accept the rate and keep budgeting it.** Risk: the retry stays about one call in seven and each costs a packet.

## F-34 — the proposal schema cannot be sent to a strict-schema provider

Found by the S11 review of 2026-11-13 (round 1, question on the proposal's wire form). `packet.schema_bytes`
accepts `session-distill/schemas/propose.schema.json`, but `provider_schema(host_schema(schema), 'codex')` returns
four `STRICT_OPTIONAL_PROPERTY` errors and `provider_schema_bytes` raises `SCHEMA_UNPROJECTABLE` before dispatch.
The schema has optional properties on the operation (`anchor`, `content`, `entry`, `units`, `unit_states` among
them), which a strict provider does not admit. It predates `unit_states`: removing that property leaves the same
four locations.

Reach: S7's seat. A run whose `seats.S7` is a Claude seat is not affected, and that is the only configuration
release 1 has run. A run that declares a strict-schema provider for S7 is refused before its first call, by name,
with nothing spent.

Alternatives:

1. **A provider wire schema beside the validation schema.** Every operation field required and nullable on the
   wire; the code-enriched proposal still validated by the present schema. `unit_states` leaves the wire, since
   code owns it. Needs an offline control over the real `provider_schema_bytes` path.
2. **Refuse the seat at declaration.** State in the seat table that S7 takes no strict-schema provider, so the
   refusal comes at S0 and names the reason. Cheaper, and closes a seat choice.
