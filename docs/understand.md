# Understand why the instructions work this way

[← Overview](../README.md) · [Setup](setup.md) · [Instructions](instructions.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

Understand! is learning for the person using the instructions, not model training. It explores reasons and limits through a conversation rather than asking you to memorize files.

## Start a learning session

Choose **Understand!** in the root TUI, or run:

```bash
agent-bios understand list
agent-bios understand show core-purpose
agent-launch --understand core-purpose claude   # or codex
```

The selection is a coherent bundle, not an individual file: core groups cover goals
and scope, decision support, adaptation, evidence/safety, and retained learning;
domain and personal bundles come from the effective instructions. A session freezes its
selected source references and edited content. The tutor explains the purpose,
background, mechanisms, tradeoffs, and limits, distinguishing documented rationale
from inference. The tutor chooses a small finite set of core points and tracks their
coverage and question counts. It uses fewer questions when understanding is sufficient,
with at most 10 tutor questions per source bullet including all followups and
clarifications. Ten is a ceiling, not a target. At the limit it explains remaining
gaps instead of extending the quiz. Supporting guides supply context, not a list of
implementation details to examine one by one.

Questions are optional when explaining, answering or summarizing. Once the core
points are covered, the tutor summarizes and ends without a compulsory followup.
If it asks a useful question, it waits for your answer. Pause and stop requests end
the questioning immediately. This is the tutoring contract; the runtime does not
claim to measure understanding or independently count semantic questions.
`understand!` also works through the shared skill in
an activated session. Learning excerpts are data, not permission to run their commands.

## Read pinned material in bounded pages

Startup contains a small tutoring prompt, not the full source bundle. `show` gives
bundle metadata, and `start`/`session` return a compact entry with the pinned source
reference. The full source stays in private session storage. Read it on demand:

```bash
agent-bios understand read SESSION
agent-bios understand read SESSION --ref '@agent-bios/core:rule-004'
agent-bios understand read SESSION --ref REF --member MEMBER --offset NEXT --expected-sha256 DIGEST
```

Without `--ref`, the reader pages a manifest of items and member names without their
bodies. With a reference it reads the exact effective body, or the named member.
Each response includes `text`, `source_ref`, `resource_sha256`, `total_bytes`,
`next_offset` and `eof`. Follow offsets until the needed resource is complete;
partial output is never a complete-source claim. Offsets count UTF-8 bytes and stay
on character boundaries, including for a large guide written on one line.

`--limit-bytes` accepts 256–16384 bytes, default 8192. The entire JSON response,
including escaping and metadata, is capped at 32768 bytes. Transcript inspection
through `turns SESSION` uses the same page format; later transcript pages require
the preceding digest and restart if the transcript changed. All prior assistant
turns must still be reviewed before proposing a discovery.

Existing pinned sessions and older full-bundle prompt files are not rewritten.
Use `session SESSION` for the current compact entry and the reader for their exact
retained source. This does not erase earlier instructions from an already running
conversation. A resumed old host still needs the current reader and tutoring skill
to follow this workflow.

## Personal discoveries

A meaningful flaw or alternative first introduced by the user can unlock a persistent
pixel trophy. Tutor-originated ideas, leading hints, and echoes do not qualify. The
discovery flow binds the native human session, checks recorded turn provenance and
ordering, and asks for a later exact save confirmation. Unsupported provenance leaves
the award pending, without blocking learning. Significance and semantic originality
remain explicit tutor/user judgments; transcript validation does not prove them or
authenticate against an owner who can edit local files. Only a successfully saved
requested-only personal instructions note can unlock the trophy. The CLI prints it, and the
TUI shows it when there is room. Retries do not duplicate the note; updates and note
deletion retain the trophy. Full reset archives the active unlock generation and clears
the display; older discovery records cannot reactivate it. Native global files and
instructions source rules are not rewritten by learning.

The runtime checks a new proposal's complete review-response size before storing
its candidate. An oversized proposal can be shortened and retried without leaving
an unreachable candidate; required provenance IDs must remain complete. Award
responses contain a compact receipt, so the saved note body is not echoed in full.

Turning an item off for ordinary activated sessions does not remove it from the learning library. On/off preferences and the inventory read revision are not learning content, so they do not repin otherwise unchanged learning bundles.
