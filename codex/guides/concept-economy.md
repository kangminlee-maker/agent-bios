---
guide_id: concept-economy
language: en
status: active
use_when:
  - naming anything lasting or shared — a feature, entity, type, field, flag, enum value, failure kind, artifact, or documentation term
  - a review finding or test failure tempts you to add a name to make it go away
  - deciding whether a value is its own concept or a property of an existing one
  - deciding what a public surface exposes versus where the truth actually lives
  - laying out a repository, or judging whether its shape still matches its concept graph
core_rules:
  - name the nearest existing concept before adding one, then choose reuse / extend / rename / split out loud
  - every fix has a concept-surface sign — reducing, preserving, or increasing; say which before making it
  - one value has one owner, and every other surface is generated from it rather than restated
---

# Concept Economy

A scoped extension of the global Concept Economy section. Use it when you are about to introduce
or change a name that will outlive the change that created it.

The cost this guide manages is not disk or tokens. It is the reader's working set: every distinct
name in a system is something a person or a model must hold, disambiguate, and keep aligned with
its siblings. Two names for one behavior is not redundancy — it is a standing invitation to edit
one and not the other, and that divergence is silent until something breaks in production.

## What Counts As A Concept

Anything **lasting or shared**. The list is deliberately long because the expensive additions are
rarely the ones that feel like architecture:

features, entities, variables, types, helper modules, artifacts, config keys, CLI flags, MCP/tool
fields, public response fields, artifact fields, enum values, failure kinds, retry/recovery
tokens, process names, documentation terms.

What is *not* a concept: transient locals, generic containers (`items`, `result`, `tmp`), and
layout a framework or tool imposes on you. The binding test is whether a second person has to
learn the name to work here. A loop variable never crosses that line; a new failure kind always
does, even when it is one string in one enum.

The trap is scale-blindness. A field added to a response is one line of diff and a permanent
addition to every consumer's mental model — including consumers you have not met.

## The Four Paths

Before adding or changing a concept, find the nearest existing one and choose a path **explicitly**.
Choosing silently is how near-duplicates arrive: nobody decided to add a second name, they just
did not look for the first.

| Path | Choose it when | What you owe |
| --- | --- | --- |
| **Reuse** | an existing concept already covers this behavior | nothing — this is the default and needs no justification |
| **Extend** | the existing concept covers it once you add a property | the property, and a check that existing readers tolerate its absence |
| **Rename** | the behavior is right and the name has drifted from it | every site, in one change — a half-rename is strictly worse than either name |
| **Split** | one of the split triggers below actually fired | the parent named, the reason stated, aliases mapped back |

Prefer broad, stable concepts with precise properties over narrow near-duplicates. `Job` with a
`kind` property beats `ImportJob` / `ExportJob` / `CleanupJob` as long as they share a lifecycle;
the moment they stop sharing one, that is a split trigger, not a naming preference.

### Finding the nearest concept

The instruction to "find the nearest existing concept" fails when you search for the name you
already have in mind — the name you invented will not be there, and its absence reads as
permission. Search for the **behavior** instead:

- Grep the vocabulary the concept would produce, not the concept: the enum values, the failure
  strings, the field names, the log messages.
- Read the nearest sibling's full definition, not its name. Names understate coverage; a type
  called `Session` often already carries the lifecycle you were about to name separately.
- Ask what would have to be true for the existing concept to be wrong here. If you cannot state
  it as a behavioral difference, you are adding a synonym.
- Check the terminology surface the repo already operates — a lexicon, a glossary, a domain
  manifest — before the code. It is shorter and it is where the deliberate decisions live.

If that search returns nothing, the addition is probably real. Record what you searched, because
the next person will otherwise repeat it.

## When To Split

A split is warranted when the two things differ in something a caller can observe or must handle.
These are the triggers; anything else is a preference:

runtime behavior · ownership · lifecycle · validation · failure mode · user-visible behavior ·
audit/replay requirements · authority · persistence · user control · failure handling

Not triggers: a different call site, a different caller, a longer function, or a reviewer's
discomfort. Those are reasons to add a property, a parameter, or a comment.

When a split is necessary, three things ship with it or the split leaves debt:

1. **Name the parent.** The concept being split from, explicitly, in the change.
2. **State the reason.** Which trigger fired, in one sentence, where a maintainer will find it.
3. **Map the variants back.** Aliases, deprecated spellings, and old values resolve to the
   canonical concept — otherwise the old name lives on as a second concept nobody declared.

## Derived Values Stay Derived

A value that tools or code can compute from its source is a **property or projection** of that
source, not a concept of its own. Persisting it creates a second authority that can disagree with
the first, and it will: the source moves and the copy does not.

The test is whether anything reads the stored value that could not have derived it. If the answer
is no, the value is a cache at best and a contradiction at worst.

**Authority is not visibility.** These are separate questions and conflating them produces both
failure modes at once:

| | Question | Wrong answer looks like |
| --- | --- | --- |
| Authority | where does the truth live, and who may change it | two writers, or a derived copy that outranks its source |
| Visibility | what may a given surface see | an internal projection leaked into a public contract, now unchangeable |

A public response may expose a bounded view — fewer fields, coarser precision, a rendered form —
while the source concept or artifact remains the one truth location. That is a projection, and it
is correct. What is not correct is treating the projection as the place to fix a wrong value.

Keep internal projections and helper outputs internal unless public exposure is genuinely required
by user behavior, a product contract, or artifact truth. An exposed field cannot be withdrawn on
your schedule.

## Reuse The Vocabulary Before Adding To It

Enum values, failure kinds, retry/recovery tokens, and result/failure surfaces are concepts with
unusually high blast radius: every consumer's branch coverage depends on the set being stable.
Adding a value obliges every exhaustive reader to handle it; adding a near-synonym obliges them to
handle it *and* to guess which one they will actually receive.

Check the existing set first, and prefer an existing value whose meaning genuinely covers the case
over a new one that describes it more precisely. Precision that fragments the set costs more than
it buys.

## Classifying A Fix

Before fixing a review finding or a test failure, say which way the fix moves the active concept
surface:

- **Reducing** — the fix removes a name, merges a duplicate, or deletes a branch. Cheapest, and
  usually available when the finding is "these two do the same thing".
- **Preserving** — the fix changes behavior inside existing names. The normal case.
- **Increasing** — the fix adds a name. Legitimate, but it must survive the four-paths question,
  and a review finding is not by itself a reason to add a concept.

This matters because review findings create pressure toward the increasing path: adding a flag, a
kind, or a special case makes a finding disappear locally while widening the surface everyone else
carries. Naming the direction before making the change is what keeps that trade deliberate.

## Migration Compatibility

**Use** fallback paths, compatibility shims, and deprecated alias normalization **when explicit
migration compatibility is required** — the obligation runs both ways: required compatibility gets
a shim, and nothing gets one as a default hedge. Each one is a second
concept surface that must be maintained and eventually removed.

When you add one, the removal condition ships with it: what has to be true for the shim to go, and
where that is recorded. A compatibility path with no stated end becomes permanent architecture by
attrition.

## Keeping The Shape Navigable

Let the repository's shape mirror its concept graph. A shared, lasting concept's canonical name
should be traceable across every layer it appears in — path, module, type/interface, field, public
API — so the structure is guessable from the concept name instead of from a translation table you
have to already know.

The working test: someone who knows the concept's name but not this repo should be able to guess
the path, or find it with one grep. If finding it requires knowing that the concept is called one
thing in the schema, another in the module, and a third in the URL, the layout has stopped being
navigable and the names are doing damage rather than work.

This binds shared concepts only. Transient locals, generic containers, and framework- or
tooling-imposed layout may diverge, and forcing them to conform is its own kind of waste.

## Domain Notes

- **Ontology work.** Check existing entities and relations first — before adding, modifying,
  removing, or relinking either; the graph is the
  artifact whose value degrades fastest under duplication, because every added node multiplies the
  edges a reader must consider.
- **Code work.** Follow the naming patterns the repository already uses — the file first, then
  its neighbors — and consolidate the variations
  your own change introduced before calling it done. A change that leaves three spellings of one
  idea has added two concepts regardless of intent.
- **Comments and active docs.** Keep them aligned with current runtime behavior, failure
  semantics, retry policy, ownership, and authority. A comment describing a superseded contract is
  not stale documentation — it is a second, false authority, and it reads as current to anyone who
  finds it first.
