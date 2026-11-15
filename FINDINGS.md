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

## F-35 — two branches that close a run over one base ledger allocate the same entry id

Found by the S12 review of 2026-11-13 (round 2). `stage_close.next_ids` numbers new entries in the series after the
highest `S<n>` the base ledger holds. Two runs closed on two branches from one base both allocate `S<n+1>-01`, for
different lessons, and each result passes `ledger.check_pair` against that base. Freezing the allocation inside a
run (`close/allocation.json`) makes one run repeatable; it says nothing across branches.

Reach: two checkouts or branches each closing a run before either is merged. The merge then meets two appended
entries of one id in one JSON array - a textual conflict where git sees one, and a duplicate id `validate_ledger`
refuses where it does not. It is not silent, and it is not prevented.

Alternatives:

1. **A run-specific id.** Derive the series from the run (its id or the confirmation's digest) instead of a
   counter, as `decisions/record-decision.py` moved from positional to content ids for the same reason. Changes
   the id form §12 and every reader of `S<n>-<m>` hold.
2. **Renumber at merge.** A merge-time tool that reallocates the later branch's ids and rewrites its `resolves`
   references. Keeps the id form; adds a step someone must run.
3. **Accept it.** One owner, one checkout, one close at a time is release 1's actual use; the collision is caught
   by the ledger's own validation at merge.

## F-36 — a read packet's call id and due list are outside the measure a window is cut against

Found by the first three-day run of 2026-11-14 (S3's dry measure). S2 holds a window to the bound by
`views.make_window`'s measure: the packet's fixed overhead, the window's text, and the omission list at its
longest. Two parts of the packet S3 really builds are still not in it: the call id, whose length follows the run
id and the view's file name, and the list of expected observations due (`stage_read.expected_text`), which S2
cannot know. Both fit only in what the fixed overhead leaves over (`packet.py --self-test` prints the room; 449
bytes for a read packet with a 13-character call id).

Reach: a window cut to within that room of the bound, in a run with long view names or with observations due.
S3 measures the packet before any call and refuses it by name (`WINDOW_OVER_BOUND`), so nothing is sent and
nothing is spent; the run stops until S2 is run again. On the run that found this, the due list was empty and the
longest view name was 144 characters.

Alternatives:

- S2 measures the call id it can derive (the run id and the view's name are known when the window is cut), and
  the declaration states a reserve for the due list that S3 holds its list to.
- S3 splits a window that its own additions push over the bound, instead of refusing it.

## F-37 — a window cut to the bound cannot be retried: the retry's correction is outside the measure

Found by the first three-hour live run of 2026-11-14 (S3). When the gate or the stage's check fails a window's
answer, the dispatcher sends the window once more with the failure's lines appended (`gate.correction`, which the
dispatcher's own docstring calls unbounded). The second packet is measured against the same bound as the first,
and S2 cut the window against the first. A window within the correction's size of the bound is therefore refused
on its retry (`WINDOW_OVER_BOUND`, the `-a2` call id): on that run one window of 116,205 allowed bytes came to
116,549 with its correction.

Reach: any window near the bound whose first answer is refused; most windows of a dense session are near the
bound, since S2 fills them. Nothing is sent and nothing is spent for the refused attempt. Under the production
posture the unit is quarantined by name and its session is handed back as failed, so the run goes on without that
session's reading; under the other postures the stage stops.

Alternatives:

- S2 reserves a declared number of bytes for a correction, and `gate.correction` holds its text to that number
  (the first lines that fit, and a line saying how many were left out).
- The retry is measured against its own bound: the first attempt's bound plus the declared correction reserve.

## F-38 — a Codex usage limit is read as an unrecognised stop, and no command ends that stop

Found by the first three-hour live run of 2026-11-14 (S6's Judge B). The Codex host answered a call with an error
frame whose detail is `{"error": {"type": "usage_limit_reached"}}` and no reset time. `breaker.codex_signals`
reads that frame as `unrecognised`, so the provider's breaker opens with `resets_at: null`, and an unrecognised stop
"stays stopped until the operator resets it" (`Breaker.reset`). Nothing in `distill.py` calls that reset: the run's
operator has to import the module and call it. Until then every Codex call of the run is deferred without being
sent, including after the limit has lifted - the first resume on that run made no call at all.

Reach: any run with a Codex seat that meets the account's limit. Nothing is sent and nothing is spent while the
breaker is open; the stage ends `partial`, and the next stage refuses it by name.

Alternatives:

- Read `error.type == "usage_limit_reached"` as a limit (a structured field, not message text), and give the
  breaker's reset a driver command that names the provider and records who reset it.
- Keep the frame unrecognised, and add only the command.

## F-39 — the review states a non-proposal row's candidate in English, and a group row states none of its members

Found by the first three-hour live run of 2026-11-14, when the owner opened the review (54 rows, 656 KB) and could
not review it. The page now prints what each row's candidate says (a row whose candidate has no text of its own
says that; an obsolete hint names its unit by id, without the unit's text) and each judge's reason for a disputed
or rejected requirement, and keeps the rest of what the judges wrote in its appendix. S7b's per-item reasons are
not in S7b's document, so the page names where they are instead of printing them. Two things remain:

- The candidate's words are its source's, which are English (S4's candidates, the ledger's lessons); only a
  proposal's reasons are written in Korean, by S7. A Korean reader gets the subject of 49 of that run's 54 rows in
  English.
- A group row (the legacy groups, the left-out hints) names its members by id in the appendix and says nothing of
  what any member is, so a decision on the group is a decision on ids.

Reach: every review a run renders. Decisions are parsed correctly either way.

Alternatives:

- Give the subject a Korean rendering made by a model seat (S9b's, which already judges Korean), with the English
  kept beside it, and print each group member's lesson in the appendix.
- Keep the subject in English and say so on the page; print the members' lessons only.

## F-40 — an approved `none` on a candidate with no entry leaves no ledger row

Found by the first three-hour live run of 2026-11-14 at S12. The owner approved five formed candidates whose
disposition is `none`. `closed_ledger` gives such an item no entry (`target_of` is `new`, and a `none` allocates
none), so the decision exists in the run's `close.json` and nowhere in the checkout. The close's report says so,
and S9's and S10b's pages now say that a `none` changes no file and that one on a new candidate is kept in the
run's record alone. Two things remain: the Korean reason S7's model writes for such a proposal may still tell the
owner the item "is recorded in the ledger", since S7's packet does not say otherwise, and a later window has no
ledger row telling it this lesson was already seen and left alone.

Reach: every approved `none` on a candidate that has no ledger entry - in RR-1, every approval of a formed
candidate. Nothing wrong is written.

Alternatives:

- Give an approved `none` on a new candidate a ledger entry in a state that names it as seen and left alone.
- Keep it out of the ledger, and have S7's packet say that a `none` on a new candidate is kept in the run's record.

## F-41 — the coverage state is keyed by session ids, and its default home is still a tracked, shipped file

Found by the first three-hour live run of 2026-11-14 at S12: `promote_coverage` wrote 3.2 MB, 7,398 transcript
keys, into the tracked `session-distill/coverage.json` of the checkout, and the close printed a `git add` of it.
The close now leaves the coverage state out of the commit command and names it local state, the repository
ignores `session-distill/local/`, and the driver's help names that path (owner, 2026-11-15: keep it inside the
checkout, untracked). What remains: `census --coverage` still defaults to the tracked, shipped
`session-distill/coverage.json`, S0 pins whatever path the caller hashed, and nothing refuses a
`--checkout-coverage` that names a tracked path, so a caller who keeps the defaults still dirties a tracked file
(uncommitted by the printed command). The state also stays on one machine.

Reach: every periodic run that closes with `--checkout-coverage`.

Alternatives:

- Move the coverage state out of the checkout to the state root, with S0, S1 and S12 reading one declared place,
  and drop the tracked empty file from the package.
- Keep it in the checkout, make the ignored path the default of S0, S1 and S12, and drop the tracked empty file.
