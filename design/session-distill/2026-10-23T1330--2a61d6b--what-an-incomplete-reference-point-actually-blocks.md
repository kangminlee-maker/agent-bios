---
created_at: 2026-10-23T13:30:00+09:00
head: 2a61d6b
kind: design
supersedes: 2026-10-23T1200--2a61d6b--release-completeness-and-the-capture-a-run-reads.md
---

# An incomplete reference point blocks three different things, and the earlier record named one

This supersedes `2026-10-23T1200--2a61d6b--release-completeness-and-the-capture-a-run-reads.md`.
Everything that record says about the capture, the write boundary, carrier identity, the context and
the remaining producers still holds. What it got wrong is the completeness analysis: it said the
literal rule blocks exactly one thing, "a `not_delivered` judged against *release*". That is one of
three, and the other two matter more to WP-10.

The eight-layer evidence from that record is preserved below unchanged. The policy choice remains
WP-10's; this record only states correctly what the choice is between.

## What this record carries forward

Superseding T1200 means this record, not that one, is the current statement of WP-07's decisions.
The ones it does not revisit are carried here by name, each still implemented as that record
described it:

- **`operative_context`** — every unit carries the requirement set a read must cover: its carrier's
  frontmatter, the condition spans at or above it, the units its mentions name together with their
  own context, transitively and cycle-safe, and `unknown:<what>` for anything it could not resolve.
- **The native capture is another package's work.** A run reads the native layers from
  `capture/native` under its own run directory and from nowhere else; building that capture was
  split out of WP-07 on 2026-10-23
  (`2026-10-23T1336--2a61d6b--plan-amendment-s0-native-capture-is-its-own-package.md`), so until it
  lands a run reports every native layer `unknown` with the reason naming the missing capture, which
  makes the reference point incomplete. What stays here from that work: the destination is judged
  before anything is locked or recorded, and the host homes are protected whether or not a run reads
  them.
- **`--native-live`** — an inspection of the owner's live homes, labelled `mode: inspection` and
  `not_a_pipeline_result: true` in every artifact, consumable by no later stage.
- **The frozen copies** — the owner's state and authoring root are read through copies made by one
  walker that decides what is read, hashed and copied; a symlink is omitted rather than followed.
  `STATE_WRITTEN` refuses a run during which those roots changed, on the error paths too.
- **`DISCLOSED_IN_ARTIFACT`** — every document this run writes is asked, as a whole, what it still
  discloses, before it is written; the refusal names the place and the detector, never the string.
- **`BASELINE_UNMAPPED`** — every item the baseline's own list names carries at least one unit of
  the release reference point.
- **Carrier identity, renames, and the remaining producers** — identity is package, item and path;
  an ambiguous fragment stays ambiguous; adopted packages come from the owner's installed state;
  overlays resolve for every host the store keeps a journal for; both baselines are frozen; a keep
  record stands only while the ledger's lifecycle says it does.

## Three different claims, and which the literal rule reaches

The design uses three vocabularies that the earlier record ran together.

**1. Reference-point absence.** §6.1's completeness rule is about a reference point as a whole, and
§6.4 turns one specific derivation into `unknown` when a reference point is incomplete: a
**candidate diagnosis** of `gap`. "No unit of this reference point matches the situation" is only a
gap if the reference point held every unit; otherwise the honest answer is that nobody knows.

**2. Delivery state** (§6.3), per unit and per session: `delivered`, `exposed_not_read`,
`selected_unavailable`, `not_delivered`, `unknown`. `not_delivered` has its own condition — the
complete *release* holds the unit and the *selection* lacks it — so an incomplete *release* makes
that state unshowable for a reason of its own, independent of the candidate rule. The design already
says this for an unpinned session: "its selection and the completeness of its *release* are unknown,
so `not_delivered` cannot be shown for it."

**3. Derived candidate kind** (§6.4), over the unit outcomes: a `gap` at *release* and *current*
yields the kind **gap**; a `gap` at *release* that is covered at *current* yields **already
resolved**. Both of these read a release-side gap, so both become `unclassified` or `unknown` when
the release reference point is incomplete. The earlier record did not mention either.

So the literal rule blocks:

| Blocked | Why |
| --- | --- |
| candidate diagnosis `gap` at *release* | §6.4: an incomplete reference point turns gap into unknown |
| delivery state `not_delivered` | §6.3: its condition is a complete *release* |
| derived kind **gap** | it is read from a release-side gap |
| derived kind **already resolved** | it is read from a release-side gap plus current coverage |

And it does not block:

- any positive diagnosis — `covers`, `wrong or insufficient`, `trigger problem`, `redundant` — nor
  the outcomes built on them (`misfire`, `confirmed`, `neutral`). These are claims about units the
  inventory holds, and an incomplete reference point weakens claims about **absence** only.
- `delivered` and `exposed_not_read`, which are read from what a session returned, not from the
  release's completeness. The O3 fixture in `inventory.py --self-test` is exactly this case: the
  same rule is `delivered` when the returned span covers its whole requirement set and
  `exposed_not_read` when the second guide's requirements are missing from the span.
- the *selection* reference point's own answers, which rest on the pin's snapshot.

## Two corrections to the earlier record's reasoning

**"Current is complete whenever its producers run" is not guaranteed.** Every layer has a *current*
producer, so current can be complete — but it is complete only when each of those producers reports
`complete`, and the inventory reports `unsupported`, `incomplete` or `unknown` whenever an input is
malformed, unreadable or absent. A run with no state root, a malformed settings file or a failed
acquisition leaves *current* incomplete too, and then §6.4 turns a current-side gap into `unknown`
exactly as it does for release. The earlier record's "unaffected" was too strong: current is
*usually* answerable, not structurally answerable.

**Selection is incomplete under the same rule.** Six layers have no *selection* producer (the four
native layers and the two ledger layers), so under the literal rule the selection reference point is
incomplete as well. Any derivation that needs a complete *selection* — most directly
`selected_unavailable`, and `not_delivered`'s second half — is in the same position as the release
ones. The earlier record implied selection was unaffected.

## The evidence that does not change

Eight layers have no producer at *release*, and each needs a historical record that does not exist:

| Layer | What a release producer would have to read |
| --- | --- |
| `overlays` | the owner's overlay state as it stood at the session's time |
| `native_global` | the host's global instruction file as it stood then |
| `native_project` | the project instruction files as they stood then |
| `native_settings` | the host's settings as they stood then |
| `native_memory` | the project's memory entries as they stood then |
| `session_injection` | the compiled instruction text of a session with no pin |
| `ledger_incubating` | the ledger's incubating entries as they stood then |
| `ledger_keep` | the ledger's keep records as they stood then, with the lifecycle state they had then |

At *selection* six of these are missing: the four native layers and the two ledger layers.
`adopted_packages` is answered at both points from the baseline's own item list and the pin's
snapshot.

## The choice WP-10 makes

Not "literal rule or scoped completeness" in the abstract, but which of these it accepts:

1. **Keep the literal rule.** Absence claims against *release* and *selection* stay `unknown` until
   historical producers exist. Positive claims are unaffected. This is what the code does.
2. **Scope completeness to the layers a judgement reads.** A gap claim that reads only catalog and
   overlays could be decided from a reference point whose native layers are unknown. This needs a
   per-judgement declaration of the layers it reads, and it is a weaker guarantee that has to be
   stated wherever the claim is shown.
3. **Build the historical producers.** The eight layers above, at the cost of an S0 capture that
   records the native and session layers at the session's time, a ledger read at the session's
   commit, and an overlay history the store does not keep.

This package implements 1 and names the cost of 3. It does not choose, and it withdraws the earlier
record's preference for 2.
