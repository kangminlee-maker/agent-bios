---
created_at: 2026-10-23T12:00:12+09:00
head: 2a61d6b
kind: design
supersedes: 2026-10-22T1949--2c1235a--inventory-layers-and-producers.md
---

# The literal completeness rule stands, and a run reads the capture it made rather than the owner's home

This record supersedes `2026-10-22T1949--2c1235a--inventory-layers-and-producers.md` where the two
differ. The earlier record's layer table, its four statuses, its unit identity and its rename rule
still hold except where this one restates them; its §6.1/§6.4 tension is settled here, in the sense
that the tension is **not** resolved by this package and the earlier record's own preference is
withdrawn.

It covers what review round 1 of WP-07 changed: the completeness rule (GA#12), the native capture a
run reads (GA#4), the one place a document is asked what it still discloses (GA#0), carrier identity
(GA#2), the context a unit carries (GA#1), and the producers for adopted packages, overlays, the
baselines and the ledger's keep records (GA#6-GA#9).

## §6.1's literal completeness rule stands, and the earlier record's preference is withdrawn

§6.1 makes a reference point complete only when **every** layer of it is complete. §6.4 turns an
incomplete reference point's gap into `unknown`. The earlier record named three ways to live with
that and leaned toward the first — scoping completeness to the layers a judgement actually reads.
**That preference is withdrawn.** The literal rule is what the code implements, and the choice
belongs to WP-10 with the evidence below, not to the package that built the inventory.

**What the literal rule blocks.** One thing: a `not_delivered` judged against *release*. A
judgement that a unit was not delivered in the release the session ran from rests on the release
reference point being complete; it is not, so §6.4 turns that gap into `unknown`.

**What it does not block.**

- Gaps at *current*. The current reference point is complete whenever its producers run, so a
  diagnosis against the library as it stands now is unaffected.
- Any positive diagnosis. "This unit was delivered", "this unit changed between the pin and now",
  "this fragment moved from one carrier to another" are all claims about units the inventory holds.
  An incomplete reference point weakens what can be said about **absence**, never about presence.
- The *selection* reference point's own answers, which rest on the pin's snapshot rather than on
  the layers the snapshot does not record.

**What release completeness would need.** Eight layers have no producer at the release reference
point, and each would need a historical record that does not exist today:

| Layer | What a release producer would have to read |
| --- | --- |
| `overlays` | the owner's overlay state as it stood at the session's time — the store keeps the current state only |
| `native_global` | the host's global instruction file as it stood then |
| `native_project` | the project instruction files as they stood then |
| `native_settings` | the host's settings as they stood then |
| `native_memory` | the project's memory entries as they stood then |
| `session_injection` | the compiled instruction text of a session with no pin |
| `ledger_incubating` | the ledger's incubating entries as they stood then |
| `ledger_keep` | the ledger's keep records as they stood then, with the lifecycle state they had then |

The *selection* reference point is short six of these: the four native layers and the two ledger
layers. `adopted_packages` is no longer among them at either point — the baseline's own item list
and the pin's snapshot both record which package each item came from, which is what GA#6 now reads.

The five that are native or session-level would be answered by an S0 capture that records them at
the session's time; the two ledger layers would be answered by reading the ledger at the session's
commit; `overlays` would need an overlay history the store does not keep. None of this is WP-07's
work. WP-10 decides whether to build it, to scope completeness, or to accept `unknown` for
`not_delivered` against *release*.

## A run reads the capture it made, and an inspection says it is one

The native layers are the owner's own files, so when they are read decides what a run means.

- A **run** reads `<run>/capture/native/`: a copy this run made, with its scope (the configured host
  homes, the projects by canonical path), a sha256 per file, a digest per layer, and every source it
  did not carry — an absent home, a symlink, an unreadable file, a scope that was read and holds
  nothing. The copy is written once; a second capture into the same run is refused. It is read back
  only after each file's bytes are checked against the hash it was captured with, and after each
  layer's digest is checked against the declaration's `starting_hashes.layers` when the run declares
  one.
- An **inspection** (`--native-live`) reads the owner's live homes. Every artifact it writes carries
  `mode: inspection` and `not_a_pipeline_result: true`, and the CLI says so. It is a way to look at
  the current state, not a result any later stage may consume.

A project is its canonical path. Keyed by directory name, two checkouts both called `source` were
one project and one's memory entries were read as the other's.

The host homes `~/.claude` and `~/.codex` are protected from being written into whether or not a run
reads them. Deriving the protected set from the run's inputs alone stopped protecting them the
moment the capture replaced them as the input.

## One place asks the document what it still discloses

Every unit's text passes the one floor (`session-distill/runlib/projection.py` over
`learn/redact.py`) and carries the floor's version, while `sha` and `version_sha256` stay on the raw
fragment and the raw carrier, so a masked unit still binds to the version it came from. The raw
bytes live only in the run's frozen copy, which is discarded.

Field-by-field masking is the shape that leaks: `text` went through the floor while `heading`,
`path`, the carriers' provenance, the manifest's own roots and an exception's message were copied
raw. So the fields that come from carrier text are projected **and** every document the inventory
writes is asked, as a whole, what it still discloses before it is written — every string in it, keys
included. A hit refuses the write by name, says where the string sits and which detector found it,
and never repeats the string. The manifest's paths are written with the projection's own home mask
rather than a second spelling of it.

## A carrier's identity is its package, its item and its path

`item_carriers` rewrites every package's member into the position it is delivered at, so two
packages' `guides/review.md` both arrive as `claude/guides/review.md`. A unit keyed on layer and
path alone made one package's fragment the other's. Identity is
`layer\0package_id\0item_ref\0path`, and the rename map reconciles a layer change as well as a path
change: the same sentence delivered from the owner's overlay rather than from the package moved,
even though its path did not.

## A unit's context carries the spans that condition it

A heading is not its own condition. A rule under `## Delivery` is bound by the `### Exceptions`
under it, and recording only the enclosing heading units left the rule's context identical when the
exception's body changed — which is exactly the delivery state WP-10 has to tell apart. The context
carries the condition spans at or above the unit's own chain, the carrier's frontmatter, and the
units a mention names together with those units' own context. A mention this reference point cannot
resolve is kept as `unknown:<path>`: a context that silently omits what it could not reach claims a
completeness it does not have.

## The remaining producers

- **Adopted packages** come from the owner's installed state. `load_catalog` returns one root's
  catalog and every item in it carries that root's package id, so filtering it for "not the core
  package" reported complete and empty without ever consulting an adoption. With no state root to
  read, the layer says so rather than reporting nothing.
- **Overlays** resolve for every host the store keeps a journal for. The store reads a journal only
  when it is told which host, so the hostless call dropped every rule the owner's sessions had
  learned. The host scope for overlays is not the native capture's scope.
- **Both baselines** are frozen with their own provenance: the installed one the current reference
  point resolves against, and the one the pin's session was activated from.
- **A keep record is not a keep.** Eligibility is the ledger's lifecycle state; the ledger retires,
  absorbs and reverts entries while the `keep` field stays on the row as history. The units a keep
  protects travel with the carrier as provenance, and every entry held back is named.

## The refusals and statuses this package owns

Each is a name an artifact or a message carries, so that a failure is attributable without reading
the code that produced it.

- `unsupported` — a layer whose carrier has a structure the splitter cannot divide. Separate from
  `incomplete`, which is a supported carrier that is malformed, missing or unreadable, and from
  `unknown`, which is a layer with no record at this reference point.
- `operative_context` — the field on every unit that carries the requirement set a read must cover,
  including `unknown:<path>` for a mention this reference point could not resolve.
- `BASELINE_UNMAPPED` — an item the baseline's own list names and the release reference point
  produced no unit for. The expected set is read from the baseline file, never from the mapping.
- `STATE_WRITTEN` — the owner's state or a captured native file changed while the inventory read
  it. Checked before and after, and on the error paths too.
- `DISCLOSED_IN_ARTIFACT` — a document reached the write boundary with a string the floor still
  objects to. Nothing is written, and the refusal names the place, not the string.
- `CAPTURE_EXISTS`, `CAPTURE_ABSENT`, `CAPTURE_CHANGED`, `CAPTURE_DRIFT` — the native capture is
  written once, is required by a run, must still hold the bytes it recorded, and must match the
  layer digests the declaration pinned.
- `PROTECTED_OVERLAP` — an output or temporary destination overlapping a root this inventory reads
  or must not write into, refused before any write.

## The S2 stage record

`records.run_stage` wrote one record per stage and `views` already owned S2's, so a second caller
would have overwritten it. The owner ruled on 2026-10-23: the record holds one part per producer.
`2026-10-23T1210--2a61d6b--one-stage-record-holds-one-part-per-producer.md` is that decision and
its alternatives; the inventory writes the `inventory` part of S2 when it runs inside a run
directory, and writes no stage record at all in inspection mode.
