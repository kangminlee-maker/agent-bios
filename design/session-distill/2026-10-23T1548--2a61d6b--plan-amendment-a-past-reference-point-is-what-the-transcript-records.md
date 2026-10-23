---
created_at: 2026-10-23T15:48:00+09:00
head: 2a61d6b
kind: design
supersedes: 2026-10-23T1336--2a61d6b--plan-amendment-s0-native-capture-is-its-own-package.md
---

# Plan amendment: a past session's reference point is the bytes its own transcript records

This supersedes the 1336 amendment, which created an S0 native-capture package and left WP-07
waiting on it. That package is **withdrawn**. A past session's reference point is not reconstructed
from the owner's current files, nor from git history: it is what the session's own transcript
records as delivered. WP-07 consumes that record, and no host instruction, settings or memory file is read in any mode.

The owner decided this on 2026-10-23 after a match check run against real pinned sessions. The
check measured, for every pin whose transcript was on disk, whether the transcript reproduces the
bytes agent-bios says it delivered. Its numbers are quoted below as measurements of that date, not
as rules.

## 1. What a reference point is, per layer the host distinguishes

A reference point is per **injection event**, not per session. One session can be injected more than
once, and the re-injected bytes are not always the same bytes.

- **Claude, native layers** — the `instructions` attachment's `files[]` entries, each carrying its
  own `path` and `type` (`User`, `Project`, `AutoMem`). The type is the layer the host itself
  distinguishes; the inventory does not infer a layer from a path shape.
- **Claude, the agent-bios injection** — located by the pin's snapshot hash inside
  `attachment.systemPrompt[]`, or inside the request-shape record's system text, which carries the
  same body. The located body is the delivered bytes; the surrounding field is not.
- **Codex** — `session_meta.payload.base_instructions` as **one undivided block**, together with
  `payload.git`. Its split into a global and a project part is **unknown**. No estimated split is
  recorded, and no layer-level claim is derived from a block that was delivered merged.

A layer the host does not distinguish in its own record stays one carrier. Splitting it would
invent an identity the delivery never had.

## 2. What pins, snapshots and transcripts each establish

Pins and snapshots say what agent-bios **selected and delivered**. A transcript **confirms**
delivery. The two are different claims and neither substitutes for the other.

A pin present with no record in the transcript is **delivery unknown**, with the reason named. It
is never `not_delivered`. An absence of evidence about an injection is not evidence that the
injection did not happen. The governing rule is §6.3's delivery state `unknown` — "any needed
evidence missing" — not §6.4's, which decides what happens to a candidate `gap` at an incomplete
reference point.

§6.3's **Native layer** row already says where the loaded text comes from: on Claude, the
transcript's `instructions` attachment by path and kind, which is what §1 reads. The same row asks
that on Codex the loaded text's hash equal the declared file's — a test no mode can meet, because
meeting it means reading the declared file. So on Codex the native layer's **identity is unknown**
and only its **loaded text** is known, and no identity claim is derived from the loaded text alone.

## 3. Git history is not a source of delivered bytes

Measured 2026-10-23 over the 33 pins whose transcripts were on disk, for the Claude `instructions`
attachment's 84 file entries compared against the nearest commit before the session started:

| class | count |
| --- | --- |
| exact | 0 |
| exact after line-ending and trailing-whitespace normalisation | 0 |
| mismatch | 14 |
| not tracked by any git repository | 70 |
| no commit before the session | 0 |

The 70 untracked entries are `User` and `AutoMem` files, which live outside any repository, so no
prior revision of them exists to compare. The 14 mismatches are `Project` files that do have a
prior commit and differ from it — the simplest explanation being an uncommitted working tree at
delivery time. Either way, zero of 84 were recovered from history, so history is not consulted for
delivered bytes.

This says nothing about the **release** reference point. The package payload at a release commit is
committed by definition, and that reference point stays exactly as it is.

## 4. What stays unknown, and with which named reason

`unknown` is only admissible with a reason that names the missing record:

| unknown | reason |
| --- | --- |
| host settings | `settings.json` / `config.toml` are not carried in the transcript |
| a session's selection when it was never pinned | no pin, so nothing says what was selected |
| a past state of the ledger | the ledger records the present, with no per-session history |
| an injection in a transcript with no attachment record | `unknown: transcript records no injection` |
| the agent-bios selection and delivery for a Codex session | `unknown: the pin and the rollout use different id spaces` (§4.2) |

### 4.1 A missing record is never inferred from a neighbour

Measured 2026-10-23, an `instructions` attachment is present in 88.4% of the last 30 days' 1,763
Claude transcripts and a `systemPrompt` attachment in 98.9% — a measurement of that day, not a
rule. The gap does not follow version order, so neither a host version nor another session of the
same version predicts whether this transcript carries the record. A transcript without the record
is `unknown: transcript records no injection`, and that answer is never filled in from a
neighbouring session, from the same version's other transcripts, or from the share itself.

### 4.2 Codex: two id spaces, and no invented join

A Codex pin records the id agent-bios requested (`session_id`, `requested_session_id`); the rollout
file names the thread uuid the host generated. Measured 2026-10-23: 15 pins, 2,631 rollouts, 2,614
rollout uuids, and 0 of 15 pins joinable — no pin id appears in a rollout name, and none appears in
any rollout's opening records. Rollouts from the same period are present in quantity, so this is
not retention.

Therefore, for a Codex session the agent-bios **selection and delivery are unknown**, with that
reason named. The Codex **native** block is still read, from the rollout itself
(`session_meta.payload.base_instructions` plus `payload.git`), without a pin.

No join is invented. Matching by time window, by `cwd`, by `argv` or by any other coincidence is
refused: a wrong join attributes one session's delivered bytes to another, which is worse than
`unknown`, and nothing in the data distinguishes a correct guess from a wrong one.

## 5. What is read, and what is never read

WP-07 opens no host home itself. It reads transcript bytes **only through the S1 census readers**
(`runlib/sources.py`), which read the host transcript stores — `claude_projects`, `codex_sessions`,
`codex_archived_sessions` — read-only and in place. Every read is bound to that session's census
record, which carries the transcript's `sha` and, for a file the host is still writing, the
`prefix_sha` of its complete lines with `record_count`.

A transcript whose bytes no longer match its census record gives that session's reference points
`unknown`, with that reason named. It is never silently re-read: a re-read answers about a different
file than the run's other stages judged, and the disagreement is the finding, not a thing to repair.

Host **instruction files, settings files and memory files are never read** — not in any mode, not on
any path. What the inventory knows about them is what a transcript records as delivered.

Inspection mode (`--native-root`, `--native-live`) is **removed**. Its only purpose was to supply a
reference point that the transcript now supplies, and three of review round 3's findings (GC#0's
project-root destinations, GC#2, GC#3) were inside it. A mode whose reason is gone is removed
rather than guarded: a guarded mode still has to be proven safe on every path, and its reason no
longer pays for that proof.

With the capture withdrawn, **WP-10 no longer waits on a new package.**

## 6. Applicability: which turn a reference point judges

A turn is judged against the **most recent injection event at or before it** in the same
transcript. Re-injection changes bytes (22 of 84 file entries, §11), so an earlier event's bytes do
not answer for a later turn, and a later event's bytes do not answer for an earlier one.

A turn that precedes every recorded injection event has an **unknown** reference point, with that
reason named. The same holds for a whole transcript with no recorded event.

A **subagent transcript is judged by its own records**, never by its parent's. A parent's delivered
bytes are evidence about the parent, and §6.3's child-session row already requires a child's own
record for child reach.

## 7. The release side: what the transcript now produces

§6.1 lists eight layers that release completeness needs and that had no historical producer (the
1330 record). For a pinned session whose injection **is** recorded, the transcript now produces:

| layer | produced from |
| --- | --- |
| native global | the `instructions` attachment's `User` entry |
| native project | its `Project` entry |
| native memory | its `AutoMem` entry |
| session injection | the body located in `attachment.systemPrompt[]` or the request-shape system text, by the pin's snapshot hash |

These stay **unknown**, with the reasons §4 names:

| layer | reason |
| --- | --- |
| native settings | settings files are not carried in the transcript, and none is read |
| overlays of unpinned sessions | no pin, so nothing says what was selected |
| `ledger_incubating` | the ledger records the present, with no per-session history |
| `ledger_keep` | the same |

§6.1's completeness rule is kept literally: a release reference point that lacks any of these is
incomplete, and the **policy** about what an incomplete release reference point may still diagnose
stays with WP-10, exactly as the 1330 record left it.

## 8. The current reference point's native layers are the most recent recorded injection

Owner decision 2026-10-23. §6.1's *current* reference point asks for all layers as they are now,
and the 1336 amendment's withdrawn S0 capture was their only producer. The ruling:

- Resolution is per layer **and per scope**, never per path: the global layer, each project root
  (the scope a transcript's own `cwd` or project identifies), each memory directory, and each Codex
  `cwd`. For one scope, the current set is the **whole `files[]` set** (or the whole Codex block) of
  that scope's most recent recorded injection event among the transcripts this run acquired through
  the census (§5). Scopes are resolved independently, so two scopes may come from two sessions.
- Per-path resolution is refused: taking the newest event for each path separately would keep a
  file alive forever after it was deleted, because no later event mentions a file that is gone. A
  whole-set answer lets a deletion show as a deletion.
- Only **main transcripts** feed the *current* reference point. A subagent's injection can omit
  layers by agent type — some built-in agent types load no `CLAUDE.md` — so a subagent event would
  make a present layer look absent. Subagent transcripts still carry their own *past* reference
  points (§6); they are simply not evidence about the current state.
- Each answer carries `as_of` the event's instant and **names the session** it came from. An
  undated or unattributed current native layer is not admissible.
- **No native file is read live**, in this or any other mode.
- **Settings are unknown at every reference point** — current, past and release alike — because no
  transcript carries them and none is read.
- An edit made after that event is **unknown until a later transcript records it**, and the record
  says so in those terms. "Current" here means the newest delivery on record, not the file on disk,
  and the answer must not be read as the latter.

Under §6.1's literal completeness rule this leaves the *current* reference point **incomplete**,
for the same reason the release one already is: settings have no producer. That is stated, not
worked around. Whether a diagnosis may proceed on a scoped reference point instead of a literally
complete one stays with **WP-10**, unchanged by this amendment.

The *past* and *release* reference points are unaffected: they are what the transcript and the
release commit record.

## 9. Review round 3, finding by finding

| finding | disposition | note |
| --- | --- | --- |
| GC#0 (blocking) frozen-copy destinations escape into protected roots | **changed** | The native and project-root copy destinations are gone with inspection. The frozen copy of the authoritative state remains, so destination confinement before any `mkdir` or copy, identifier validation, and write-observing controls all stay — for that copy. |
| GC#1 (major) the temp-directory preflight writes before refusing a protected destination | **carried** | Any run still writes output. Choose and validate the location without a write-probing resolver; test attempted writes, not final hashes. |
| GC#2 (major) run mode still acquires native project inputs | **moot** | Run mode acquires no native source at all. Project paths are retained only as protected write targets. |
| GC#3 (major) inspection can overwrite a run's inventory through `--to` | **moot** | The mode is removed. Destination confinement for run output is GC#0/GC#1. |
| GC#4 (major) splitting carriers before projection loses credential context | **carried** | It applies unchanged to transcript-derived unit text: project the span with the intact carrier's context, keep identity hashes on the raw carrier. |
| GC#5 (major) the document disclosure check weakens the floor's structural policy | **carried** | Floor predicates over every value type; refusal locations from trusted schema fields or ordinals. |
| GC#6 (major) stage records and CLI diagnostics bypass the disclosure boundary | **carried** | Enforced before publication, including preserved parts and failure records, and on diagnostics and argument errors. |
| GC#7 (major) sources are read before the walker and ancestor links are not rejected | **changed** | Transcripts are read through `sources.py` (§5), so WP-07's own walker covers the frozen state copy and nothing else; within that scope the rule is unchanged — one selection mechanism, links rejected before bytes are read, leaf and ancestor controls. |
| GC#8 (major) operative context is not a closure over the starting unit's requirements | **carried** | Including the initial requirement set, with cycle protection, and the O3 control where the second guide is reached only through an enclosing condition. |
| GC#9 (major) legacy recovery and part-less S2 writes violate GB#11 | **carried** | A part is required for every new write to a stage in `STAGE_PARTS`; ambiguous legacy records are preserved or refused before mutation; legacy fixtures are built directly. |
| GC#10 (major) the bytecode control does not test the command | **carried, and narrowed** | The control now runs the real driver in a child process, observes attempted writes through an audit hook (a `.pyc` is written through `os.open`, whose audit arguments carry no mode string — a mode-only test saw nothing and called it proof), clears the caches it asks about so it cannot pass on a cache that was already valid, and keeps the positive control. Its claim is scoped to the modules the command loads **by path**; §9.1 says why, and what that leaves. |
| GC#11 (minor) the rename-ambiguity control misses the same-path, different-package case | **carried** | Identical fragments at one delivered path in two package-qualified carriers, under reversed order and changed membership. |
| GC#12 (minor) the self-test depends on dated prose | **carried, and ruled** | See §10. |
| GC#13 (minor) the 1330 record wrongly blocks `selected_unavailable` | **carried** | Positive selection membership is distinguished from absence in selection, and any broader policy stays with WP-10. |
| GC#14 (major) the capture handoff underspecifies identity and stage information | **moot** | There is no capture to hand off. §1 is the contract that replaces it. |

The round-3 rework that stays in WP-07, unchanged by this amendment: S2 stage parts, the disclosure
boundary over every written document and diagnostic, the bytecode guard before the command's module
graph is imported, the operative-context closure, package-qualified carrier identity, the preserved
legacy S2 producer, and the malformed-but-supported carrier class.

### 9.1 The bytecode guard, measured

Measured 2026-10-23 on this tree, not inferred. Every `__pycache__` under `session-distill/`,
`learn/` and `compose/` was removed, and the driver was run as a real invocation with no bytecode
environment variable set:

```
python3 session-distill/distill.py inventory --to <tmp>/out --no-state
```

It exited 0 with four artifacts, and **zero `.pyc` files appeared** anywhere under those three
trees. The reason is in the code: `distill.py` sets `sys.dont_write_bytecode = True` before the line
that imports `runlib`, and importlib reads that flag at the moment it would write the cache — so
`runlib` is not cached, the modules the floor and the store load by path are not cached, and the
driver itself is `__main__`, which is never cached at all.

So GB#7's claim holds for the real invocation, whole. The one shape that would cache the driver is
**importing** it as a module, and nothing in production does: `session-distill/` is author-side
(`package.json` `files[]` carries no path under it, held by `gates/check-package.sh`), there is no
shipped launcher, and a real invocation runs the file as a script. That import was the control's own
probe, and the `session-distill/__pycache__/distill.*.pyc` seen during one revert came from it.

The control now runs the driver the way production does — `runpy.run_path(..., run_name="__main__")`
inside a child, from a cleared cache — and asserts that no `.pyc` appears anywhere under the
checkout, by observing the attempted writes and by looking at the disk afterwards. Its positive
control still loads a copy of `learn/redact.py` by path with the guard off, so the observation is
known to be able to see such a write. Clearing the caches first is part of the control: without it,
a run that found a valid cache already there writes nothing and the control passes on that.

### 9.2 One floor entry point for a decoded document

Measured 2026-10-23. The floor's helpers read different representations, and each is consistent
inside `projection.py`'s own walk: `all_mask` reads an object as `Members`, `holds_secret` reads
plain decoded objects, and `discloses` reads a string. Asked from outside with the wrong shape they
answer wrongly in BOTH directions — `all_mask` calls a plain `dict` unmasked whatever it holds (a
refusal, so safe), while `discloses` on a plain object returns None for a credential-named member
and `holds_secret` on `Members` misses the same member (a pass, so not safe).

The inventory had been choosing a helper per value, which is the fragile shape: it got one wrong in
each direction within a single round. The rule now: `projection.document_disclosures` is the one
entry point for "does this decoded document disclose anything". It takes either representation,
converts internally, applies the floor's own three rules (a credential-named member whose value is
not the mask, at any depth and with duplicates kept; a key that discloses; a string that
`discloses` objects to), and returns locations built from schema-safe names or ordinals — never the
value, a path, or a hash of either. Its contract is a table in `projection.py`'s own self-test over
every shape measured above. The inventory's write boundary and diagnostics call only that entry
point and own nothing but their refusal code.

## 10. The self-test reads what the code owns

No control depends on a dated design record by path. Dated records are claims about a past tree, so
a test that asserts one of them exists tests provenance rather than behaviour, and it breaks when
the record is superseded — which is the normal fate of these files. Controls read the schemas,
interfaces and serialized fixture results the code itself owns, and keep record links as
provenance only, outside executable acceptance criteria.

## 11. Expected coverage, measured 2026-10-23

These are measurements of one day on one machine. They are not a rule, and they are not a
guarantee for any other tree.

Whole-body match for the 33 pins with a transcript on disk, all of them Claude main sessions:

| class | sessions |
| --- | --- |
| the delivered body present intact inside one field | 23 |
| no record of the injection at all | 10 |
| present only split across records | 0 |
| field-exact | 0 |

Field-exact is zero by structure: the transcript's `systemPrompt` field is a larger string that
contains the delivered body, so the body matches as a part of it, not as the whole field.

Re-injection: of 84 attachment file entries seen, 22 were re-injected with different bytes. This is
why a reference point is per injection event.

Coverage across the last 30 days of Claude transcripts (1,763 files): 1,558 (88.4%) carry an
`instructions` attachment and 1,743 (98.9%) carry a `systemPrompt` attachment; 694 of 794 main and
864 of 969 subagent transcripts carry the attachment. The share does not improve monotonically with
host version — one version records it in 445 of 445 transcripts while two later versions record it
in 108 of 179 and 37 of 65 — and the 10 pinned sessions with no record are spread across five
versions that also appear among the 23 with a record. The gap is therefore structural rather than
historical: some launch path leaves no record. Those 10 carry no `systemPrompt` attachment either.

Codex pins resolve to no transcript at all, for the reason §4.2 states, so pinned Codex coverage is
zero until the identifier is reconciled (§12). The Codex native block is unaffected: it is read from
the rollout without a pin.

## 12. Open item for the findings queue: the Codex id-space mismatch

This is an activation defect in agent-bios, **outside WP-07**. It is written here so the queue entry
can be drafted from measured facts; the owner decides its wording and placement in `FINDINGS.md`.

- **What is recorded.** `create_codex_session` (`compose/instructions_session.py`) starts a thread
  over the app-server and pins `thread['id']` as `requested_session_id` and then `session_id`, with
  `evidence = {'method': 'thread/start+inject_items+read', 'thread_path': thread.get('path')}`. All
  15 pins on this machine carry that method and a `thread_path`, and the pinned id is the uuid in
  that path.
- **What the rollout uses.** The host writes `rollout-<date>T<time>-<thread uuid>.jsonl`, with the
  thread uuid it generated itself; 24 of the files carry a second uuid appended, the fork shape.
- **Why no join is possible today.** Measured 2026-10-23: 2,631 rollouts, 2,614 distinct rollout
  uuids, 15 pins, and 0 of 15 pins joinable — no pin id occurs in any rollout name or in any
  rollout's opening records, and none of the 15 recorded `thread_path` files still exists, matches a
  rollout name, or carries a rollout's uuid. The app-server thread store and the CLI rollout store
  are two stores, and the pin names the first. Rollouts covering the same 23–34 day span are present
  in quantity, so retention is not the cause. The consequence is that every Codex pinned session's
  selection and delivery is `unknown`, however complete the rollout beside it is.
- **What would close it.** Activation must record the rollout the host actually writes, or the
  transcript must carry the pin's own identifier, so the two can be joined without guessing. The
  alternatives and their risks are in `FINDINGS.md` F-22; the change is in the activation path, not
  in the inventory.

## 13. Transcript text passes the same floor

Transcript text read for a reference point is unit text like any other: it crosses into an artifact
only through `runlib/projection.py` over `learn/redact.py`, stamped with `redaction_version`, with
hashes kept on the raw fragment and raw carrier. The delivered bodies measured above are the
owner's own instruction text and host memory, so nothing about their origin relaxes the boundary.
