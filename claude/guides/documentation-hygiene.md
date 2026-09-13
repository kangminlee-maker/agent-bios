---
guide_id: documentation-hygiene
language: en
status: active
use_when:
  - writing a comment, and deciding whether it earns its place
  - recording why something changed, an alternative that was rejected, or a migration's rationale
  - deciding whether an active document should link to a historical note
  - authoring a rule, guideline, or instruction others will follow
  - choosing where change history and implementation context belong
core_rules:
  - prose about the past and prose about the present need different addresses, not different tenses
  - a comment earns its place by carrying what the code cannot say about itself
  - phrase a rule as the behavior you want, because a prohibition describes everything except what to do
  - a continuously overwritten "current state" file claims to be now and is no particular time
---

# Documentation Hygiene

Before writing, revising, or translating Korean prose, read and apply
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/guides/korean-writing.md` in full.

A scoped extension of the global Documentation Hygiene section. The subject is placement: **prose
about the past and prose about the present need different addresses.**

The cost this manages is misreading, not tidiness. A sentence describing how something used to
work, sitting beside code that works differently now, reads as a present fact — to a person
skimming and to a model retrieving. Nothing marks it as history except a tense, and a tense is not
a signal anyone checks. Moving it is cheaper than maintaining the reader's suspicion.

## The two addresses

**Active surfaces** — runtime code, comments, the docs someone reads to operate the thing — carry
current behavior, current decisions, current contracts, current authority, current failure
handling. Nothing else.

**Isolated paths** — `docs/`, `design/`, `archive/`, `deprecated/` or whatever the repository uses
— carry backward-compatibility notes, deprecated behavior, migration rationale, historical
alternatives, change narratives, and handoff logs.

The test for any sentence: *if this stopped being true, would anyone notice?* Active surfaces are
where the answer must be yes, because something breaks. History is where the answer is no, which
is exactly why it must not sit in the first place.

## Comments carry what the code cannot

A comment earns its place by saying something the code cannot say about itself:

- Non-obvious current behavior — why this looks wrong and is right.
- An invariant a reader could break without noticing they broke it.
- A constraint that comes from outside the file: a protocol, a rate limit, an ordering another
  system depends on.
- A risk that still applies. Not one that used to.

What does not earn its place: restating the line below it, narrating the change that introduced it
("changed this to fix the bug"), or describing a contract that has since moved. That last one is
not stale documentation — it is a **second, false authority**, and to whoever reads it first it is
simply the answer.

Comments describing superseded behavior are the highest-yield deletion in most files. They are
also the hardest to find, because nothing fails when they are wrong.

## History has its own address

When you have something worth recording that is not current behavior — why an alternative was
rejected, what a migration was compensating for, what a session handed off — write it in an
isolated path rather than beside the code.

Two properties make such a record useful:

- **It is written once.** A record that is edited whenever things change stops describing any
  particular moment. If it must be updated, the honest move is a new record that supersedes the
  old one, not an overwrite.
- **It carries its own point in time.** A timestamp in the filename cannot rot, because the age is
  on the label. A file called "current state" makes a claim it cannot keep.

That second point generalizes past records. Any continuously overwritten "the state of things"
document claims to be now and is, in practice, no particular time — the last person to touch it
decided how current it is, and nobody else can tell. Where the underlying facts are derivable,
give the reader the command that re-derives them instead of a number someone typed.

## Linking back

Link from active material to a historical note only when the current task needs that history, or
when the reference genuinely helps a future maintainer — usually because the present design looks
arbitrary without it.

A link is a small permanent cost: it invites the reader to leave, and it must stay resolvable. An
active document that links to five historical notes has partly become one.

## Writing rules people follow

Phrase a rule as the behavior you want, not as the thing you are afraid of. A prohibition
describes everything except what to do, and leaves the reader to invent the positive form —
usually at the moment they have the least attention to spare.

- "Pin the interpreter when a bash-specific feature is needed" beats "don't rely on the default
  shell".
- "State the assumption you are proceeding under" beats "don't guess".

Two more properties of a rule that survives contact:

- **It says when it fires.** A rule with no trigger is advice, and advice is followed when
  convenient.
- **It says what it costs.** A rule whose expense is hidden gets quietly dropped the first time
  someone is in a hurry, and nobody records that it was dropped.

## Where change history belongs

Prefer the established homes over inventing one per change: a changelog for released behavior, a
current-state dashboard for architecture and risk, handoff notes for what a session left unfinished.

Keep their jobs distinct. A changelog that accumulates design rationale becomes unreadable as a
changelog; a dashboard that accumulates history stops being current. When a document starts
answering a question it was not built for, that is a signal to split it, not to add a section.
