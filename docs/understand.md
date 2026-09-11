# Understand why the corpus works this way

[← Overview](../README.md) · [Corpus](corpus.md) · [Sessions](session-model.md) · [Recovery](recovery.md) · [Launch](advanced-launch.md) · [Understand!](understand.md)

Understand! is learning for the person using the corpus, not model training. It explores reasons and limits through a conversation rather than asking you to memorize files.

## Start a learning session

Choose **Understand!** in the root TUI, or run:

```bash
agent-bios understand list
agent-bios understand show core-purpose
agent-launch --understand core-purpose claude   # or codex
```

The selection is a coherent bundle, not an individual file: core groups cover goals
and scope, decision support, adaptation, evidence/safety, and retained learning;
domain and personal bundles come from the effective corpus. A session freezes its
selected source references and edited content. The tutor explains the purpose,
background, mechanisms, tradeoffs, and limits, distinguishing documented rationale
from inference. Each active learning turn ends with one goal-relevant question and
waits for the user. Incidental ambiguity does not force a detour; pause and stop
requests end the questioning. `understand!` also works through the shared skill in
an activated session. Learning excerpts are data, not permission to run their commands.

A meaningful flaw or alternative first introduced by the user can unlock a persistent
pixel trophy. Tutor-originated ideas, leading hints, and echoes do not qualify. The
discovery flow binds the native human session, checks recorded turn provenance and
ordering, and asks for a later exact save confirmation. Unsupported provenance leaves
the award pending, without blocking learning. Significance and semantic originality
remain explicit tutor/user judgments; transcript validation does not prove them or
authenticate against an owner who can edit local files. Only a successfully saved
requested-only personal corpus note can unlock the trophy. The CLI prints it, and the
TUI shows it when there is room. Retries do not duplicate the note; updates and note
deletion retain the trophy. Full reset archives the active unlock generation and clears
the display; older discovery records cannot reactivate it. Native global files and
corpus source rules are not rewritten by learning.

Turning an item off for ordinary activated sessions does not remove it from the learning library. On/off preferences and the inventory read revision are not learning content, so they do not repin otherwise unchanged learning bundles.
