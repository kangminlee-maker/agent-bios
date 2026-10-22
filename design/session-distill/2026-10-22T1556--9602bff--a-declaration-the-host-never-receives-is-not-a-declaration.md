---
created_at: 2026-10-22T15:56:45+09:00
head: 9602bff
kind: review
supersedes: 2026-10-22T1121--ec51ee9--the-capacity-is-reported-not-invented-and-recovery-is-measured-from-the-stop.md
---

# A declaration the host never receives is not a declaration

Round 2 of the dispatcher-seam review (`wp/06-dispatch-seam`, subject `git diff ec51ee9 9602bff`)
returned six findings, BB#0–BB#5. This records what they closed and what they ruled out. It
supersedes the 1121 record only where it changes something; everything that record says about the
bound's one owner, the declared capacity and the recovery sequence still holds.

The sentence in the title is the round's one finding, said three ways. Round 1 made the dispatcher
declare things: the output cap check (d) reserves, the appended system prompt the driver sends, the
seat's capacity. Round 2 asked who receives each declaration, and in three places the answer was
nobody. A reserved cap that `codex-run` never passes reserves nothing at the host. A prompt recorded
as a hash and never sent fails the call's own effective-context check, after the call is paid for. A
capacity a caller hands the window builder is a number no declaration carries.

## What was wrong, and what it is now

**BB#0 — the stop and the amendments were not serialized.** The stop stamped itself with the latest
declaration sequence, but read that sequence outside the lock `declare --amend` commits under. An
amendment committed a moment before the read would stamp the stop with a sequence that amendment then
lifts; an amendment caught between its log line and its run.json made the read fail
`DECLARATION_DRIFT` instead of waiting. **The lock order in `dispatch.py` is now the declaration lock,
then the supervisor's**, stated in `_stop_run`'s own docstring. A bound stop is the one place that
takes both; every other site only reads the declaration, under the supervisor's lock alone, and a read
that lands mid-commit is refused by name rather than believed - so no site takes the two in the other
order and the new order cannot deadlock against them.

**BB#1 — a part could be hashed once and counted twice.** `part_bytes` preferred an asserted `bytes`
while `part_evidence` hashed the content independently, so `{"text": "P" * 130000, "bytes": 1}` was
admitted as one byte and recorded with the hash of 130 KB. Each declared part is now read exactly once
(`bound.part_body` → `part_snapshot`), and the count, the evidence and the bytes the adapter is handed
are three views of that one snapshot (`bound.admitted_parts`, the dispatcher's single entry point). An
asserted length can now only disagree, and a disagreement is `DRIVER_PART_LENGTH_CONFLICT`.

**BB#2 — the appended prompt was recorded and never sent.** The runner specification carried neither
content nor path and `runner_argv` emitted no `--append-system-prompt-file`, although `claude-run`
takes one. The snapshot's bytes are now written into `calls/<id>/appended/` and handed to the adapter
with the sha256 they were declared at; the fake host reads the delivered file and reports its hash, so
the gate's effective-context leg is a delivery check. A call carrying a prompt is now accepted by the
gate outright, where BA#2 could only show that every other leg passed.

**BB#3 — the path form is gone.** `part_evidence` kept `path` for appended prompts, which produced a
record `CALL_SCHEMA` rejects, and nothing ever read it back. An appended prompt is declared by content;
the path form is the instruction file's and stays there. A path-shaped prompt is
`APPENDED_PROMPT_PATH_FORM` at declaration.

**BB#4 — check (d) reserved a cap the host was never told.** `codex-run` deliberately does not pass
`--max-output-tokens` (Codex has none, design §3.2). `ADAPTER_CONVEYS` now declares what each adapter
can deliver and the flag that carries it; a view-window call on a host that cannot convey the cap is
`CAP_UNDELIVERABLE`, before the allowance and the capacity are even looked at, and a declared prompt on
a host that cannot send it is `APPENDED_PROMPT_UNDELIVERABLE`. Both are kept twice - at admission and
in `runner_argv` - so a specification cannot be launched with a declaration stripped out of it. The
declaration is held against the wrapper scripts themselves by a control, so a flag `claude-run.sh`
stops taking fails here rather than at a launch.

Because of this, **every view-window control in `dispatch.py`'s self-test now runs on the Claude seat**
`claude:claude-sonnet-5-5/xhigh`, whose capacity `seats.json` declares and whose allowance it measures;
the retained 136k R-authoring observation is replayed through the Claude side of the fake host. The
Codex seat keeps the non-window half of that pair, where it was captured, and one control of its own:
the view-window call refused `CAP_UNDELIVERABLE`.

**BB#5 — the window builder had a public capacity override.** `views.limits_of` and `views.run` took a
`capacity` argument and only consulted the shared reader when it was None. Both now resolve it through
`gate.seat_capacity` on every path; a test that needs another capacity declares one in a `seats.json`
fixture (`views.fx_seats`) and names it with `seats_path`, so the reader - and what it requires of a
declaration - is the same one production uses.

## Closed alternatives

- **An appended prompt declared by a path.** Ruled out. It produced a record the call schema rejects,
  no reader consumed it, and the delivered bytes would then be whatever the file held at send time
  rather than what admission counted. Instruction files keep paths, because a path is what the host
  loads for them.
- **Reserving an output cap the host never receives.** Ruled out. Check (d) exists to keep the answer's
  tokens inside the seat's context; a cap enforced only on the driver's side reserves nothing, so the
  call is refused instead of admitted against a reservation nobody made. The consequence is accepted:
  no view-window call runs on Codex until an adapter can convey a cap.
- **A second lock order.** Ruled out. The stop could have taken the supervisor's lock and then the
  declaration's, which reads naturally from the dispatcher's side and deadlocks against any site that
  takes them the other way. One order, declaration first, stated in the code.

## What the controls are

Every fix has a control that fails when the fix is reverted, and each was watched failing by name:
`bound.py`'s conflicting-length and path-form controls, `dispatch.py`'s
`BB#0-the-stop-waited-for-the-amendment-s-commit-instead-of-reading-across-it` (an amendment that holds
the declaration lock, writes its log line, pauses, then commits),
`BB#2-the-counted-snapshot-is-what-the-adapter-is-handed` with the host's reported hash beside it,
`a-view-window-call-on-a-host-whose-adapter-cannot-convey-the-cap-is-refused`, and `views.py`'s
signature control for the capacity that is no longer an argument. The refusal inventory reads
`bound.PART_CODES` rather than a literal, because the dispatcher computes the part refusal's code from
the problem the rule reports; `a-removed-driver-part-refusal-is-detected` is what keeps that scan from
going quiet.
