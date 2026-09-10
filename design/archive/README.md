# Archive — dated records, never runtime authority

Everything under this directory is **true as of its date and never updated afterwards**.

That is the whole point. A dated record says "as of 2026-07-31, X"; that claim never becomes
false, it becomes historical. A living document says "currently, X" and silently becomes false
the moment X changes — with no date on it to warn the reader. This repo has already paid for the
second shape: `design/session-distill/HANDOFF.md` is titled `Current state (DONE)`, was last
touched 2026-07-26, and states entry counts the ledger has since moved past.

So the rule here is not "write carefully." It is that nothing in this directory is ever edited to
stay current, and nothing that must stay current is ever stored here.

## What lives here

- **Round records** — what a round found, why it stopped, which framings were narrowed. The
  reasoning is worth keeping; the state it describes is not current by the time it lands.
- **Superseded design documents** — a feature design, once implemented, describes a shape the
  code now owns. It archives whole rather than drifting in place.
- **Handoffs** — one dated file per handoff, accumulated, never revised.

Durable *method* does not live here. If a rule governs how the next round runs, it belongs in the
repo's `AGENTS.md`, where it is loaded and can be acted on.

## Two properties, both enforced

**Deprecated terminology is tolerated.** Historical prose keeps the words it was written with, so
`gates/check-lexicon.py` exempts this prefix. Without that exemption, the archive would break the
terminology gate every time it recorded a rename — which is exactly what happened on 2026-08-01,
when a handoff naming two deprecated tokens turned `check-parity.sh` red.

**No runtime file may point at a record in here.** The corpus, the installer, the composer, the
launcher, the gates, and this repo's `AGENTS.md` are all forbidden from naming a file under this
directory, and `gates/check-lexicon.py` fails if one does. A live pointer would make a dated
record authoritative again, which is the property the archive exists to remove. `AGENTS.md` is
inside that prohibition on purpose: the method it carries has to be self-contained rather than a
stub deferring to history.

Naming the *directory* is allowed, because declaring the rule is not the same as depending on
what the rule protects — a runtime file has to be able to state the boundary it is bound by. The
gate draws that line where it actually falls: a filename character after the slash is a
dependency, a bare directory mention is a declaration.

The two files that operate these rules — `gates/check-lexicon.py` and
`ontology/instances/graph.json`, plus the `LEXICON.md` they project — must name the path in order
to enforce and author it, and are exempt for that reason alone.

## Finding things

Archived files are dated in their names and are not indexed here; an index would be a living
document, which is the shape this directory exists to avoid. Search by date or by content
(`rg`), or follow a pointer from wherever the work is currently tracked.
