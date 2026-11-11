---
created_at: 2026-11-11T11:40:00+09:00
head: 304724e
kind: design
supersedes: null
---

# A unit is delivered by the bytes a session read back, and a miss is never claimed from an unread call

WP-10, commit W2: design §6.3's delivery evidence as code over `session-distill/tables/delivery_evidence.json`, in
`runlib/delivery.py` (a module the plan's file list does not name; §6.4's derivations stay in `derive.py`, which
reads the states this module answers). Decisions D-20261111-6ff311 (this commit) and D-20261111-eaa2a8 (the lead's
absence rule, recorded with it). S5's assembly of these inputs from the inventory and the transcripts is W3.

## What the table holds

The eight surfaces of §6.3 in the design's words, each with its ordered levels, the level it delivers at, the level
it exposes at, the catalog item surfaces it answers for, and whether a producer reads its evidence; the five
delivery states; and one licensed level, `library_selected` (D-20261110-9c60bc, the lead's direction for WP-10):
the selection history says what the owner's library held, its state is `unknown`, and it ranks below every
delivered level. Four surfaces have no producer in release 1 and say why (`producer: absent`): an executable
invoked directly, a skill, a hook, a child session. A unit on one of them is `unknown` naming
`producer_absent:<surface>`. The code reads the ladder: a level at or above `delivered_at` delivers, one at or
above `exposed_at` exposes.

## The rules

- **A guide's unit read.** The requirement set is the inventory's `operative_context` (the unit, its frontmatter,
  the enclosing conditions, every operative unit it names, in any guide; a `k-` entry it could not resolve is a
  requirement that stays `unknown`). A requirement is met by a read before the decision whose returned lines -
  with the line-number prefix of a reading tool removed when every line carries one - hold its text as one
  contiguous run, and whose bytes are of the requirement's version: the versions of the source whose lines hold the
  read's lines (lines the tool added at either edge, which no version holds, are not the file). One version, the
  requirement's: met. Several, the requirement's among them: the version the pin or release names binds it
  (`bound_versions`), and with none it is `unknown` (`version_unbound`). Another version: unmet
  (`version_mismatch`).
- **Which reads are of a carrier.** The path the compiled output emitted for the unit's item, or a path ending in
  the part of the carrier's catalog path a deployed copy keeps (`claude/guides/x.md` read as `.../guides/x.md`).
  The bytes, not the path, decide the version: two packages deliver one path.
- **Exposure.** A selected guide's pointer is exposed when the injection recorded at or before the decision holds
  the router path (relevant) or its own emitted path (requested); a read of the router whose returned line ends in
  the guide's item ref is the router read. A partial read of the guide is exposure too, with or without a pin. A
  tool call before the decision that names the guide and whose returned bytes this code could not read leaves the
  state `unknown` (`read_unparsed`): `exposed_not_read` feeds a misfire (trigger), a claim about the session, so it
  rests only on evidence that was read.
- **The always surface.** Delivered when the pin selected the item, its lines are in the compiled instruction text,
  its route is not unavailable, and the injection was recorded at or before the decision.
- **Native layers.** Delivered when the most recent recorded injection at or before the decision loaded the unit.
- **Absences.** `not_delivered` (the release holds the item, the selection lacks it; or a native unit the latest
  injection did not load) is an absence: under the literal policy it is `unknown` and the reason names the layers
  whose completeness is unknown (`absence_withheld: completeness unknown for native_settings`).
- **Sessions without a pin.** A unit read delivers, a partial read exposes, nothing else is claimed, and the
  selection stays `unknown`. A Codex pin that names no rollout is `unknown` with the inventory's reason (F-22); a
  joined Codex pin is a pin (golden; the live case waits for the early release).
- **The installer.** `installer_exposure(binding, receipt, snapshot_artifacts)` reads the store's
  `installation_binding()` and the receipt in the plan's WP-15 shape with the lead's flat `artifacts[{path,
  sha256, role}]`: consumed when bound, a success receipt of the binding's transaction, and every artifact the
  snapshot records among the receipt's `release` rows; exposure is judged against the executing installer and the
  one that began a recovered transaction. Golden; the live case waits by name (`receipt_live_waiting_wp15`).

## The O3 verdicts this commit holds (done-when 2)

Each with the control that flips it: an operative context across two guides read completely is delivered; the
second guide unread, or read at another version, is `exposed_not_read`; a read with the unit and its heading but
not the enclosing exception, or truncated before the unit, is `exposed_not_read`; a pointer exposed and never read
is `exposed_not_read` and, through `derive`, a misfire (trigger); a selected item whose route is unavailable is
`selected_unavailable` and not delivered; an unpinned session is `unknown` and unclassified; an unpinned session
that read the unit before violating it is delivered with its selection unknown and a misfire; an identical fragment
in two versions binds by the pin and is `unknown` when nothing binds it. Beside them: reads and injections after the
decision count for nothing, the router read is its own level, the selection history is `library_selected`, and an
absence is withheld under the literal policy and shown at a complete release.

## Frozen fixtures and the design's rows

`delivery.py --generate-fixtures` wrote `tables/delivery_evidence_fixtures.json` once: one fixture per row (eight
surfaces and the licensed level), each case reaching exactly one level and expecting the state the table's own
fields give it. The self-test runs them through the production functions and compares the three sets with
`derive.coverage_problems`; §6.3's surfaces, levels and states are copied once into the module and held against the
table (`CONTRACT_DRIFT`); every implemented surface has its handler and every handler its surface
(`SURFACE_UNHANDLED`, `HANDLER_ORPHAN`).

## Measured on this tree

| What | Result |
| --- | --- |
| The table | 9 rows; 9 frozen fixtures |
| delivery self-test | 55 controls, OK |
| Revert rows (`rows-w2.py`) | the baseline passes; 16 revert rows caught, none missed |
| Self-tests | every session-distill module with a self-test: 36, 0 not rc=0 |
