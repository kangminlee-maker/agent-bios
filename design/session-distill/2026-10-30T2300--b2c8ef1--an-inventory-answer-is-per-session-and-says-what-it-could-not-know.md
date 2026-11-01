---
created_at: 2026-10-30T23:00:22+09:00
head: b2c8ef1
kind: design
supersedes:
  - 2026-10-28T0549--aa80bb1--a-parser-s-message-is-the-carrier-s-own-text.md
---

# An inventory answer is per session, and says what it could not know

This record closes phase 2 of WP-07 package B: `session-distill/runlib/inventory.py`, its schema
`session-distill/schemas/inventory.schema.json`, and the parts of `projection.py`, `distill.py`, `dispatch.py` and
`gates/control-audit.py` they needed. Package A's chain of records ends at the 0549 record this one supersedes, so
the WP-07 line stays one line. It amends four inventory records, each of which stays as written:
`2026-10-22T1949--2c1235a--inventory-layers-and-producers.md`,
`2026-10-23T1200--2a61d6b--release-completeness-and-the-capture-a-run-reads.md`,
`2026-10-23T1330--2a61d6b--what-an-incomplete-reference-point-actually-blocks.md` and
`2026-10-23T1548--2a61d6b--plan-amendment-a-past-reference-point-is-what-the-transcript-records.md`. Where they
describe the inventory as one reference point per run, or a release inventory as the installed state, this record
states what is true at `b2c8ef1`.

The title is the change in one line. At the base, `98fb8fb`, the inventory answered once per run: one current
reference point, one selection, one release, each a set of units. Now every session of the census answers for
itself: its events, its segments, its own pin's selection, the release its own snapshot names, and a delivery
that names the first link of that chain that broke. Where an answer cannot be given, the document carries a row
that says which input was missing and why, never an empty set standing in for it.

## 1. What it records

Base `98fb8fb` (2026-10-28 06:50). Phase 1 is `163cf48` and `0ce6a0a`. Phase 2 is the 23 commits after them, up
to `b2c8ef1` (2026-10-30 20:47):

| step | commits | what it made |
| --- | --- | --- |
| P2.1 | `f4ef63c`, `f006b9a` | events as published records, owners, intervals, the session record |
| P2.2 | `952d4bd`, `7292db8` | the current reference point scope by scope |
| P2.3a | `89dd81b`, `2deec7f` | identities from raw values, duplicate members, the shared unit store |
| P2.3b | `376944f` | occurrences, recorded versions, deliveries, a Codex block's git |
| P2.4a | `a36c728` | every session's own pin and snapshot, and its delivery chain |
| P2.4b | `b0abfef`, `f097f2c`, `5e9f687`, `22bb796`, `7f75bda` | shared inventories, the deferred release, and a self-test that names a refused run and a raising block instead of ending |
| P2.5 | `b3e2ef3`, `520b010` | segments per owner, the instant-only placement, `release.json` as a segment index |
| P2.6 | `24ea3f5`, `fdc1965`, `f506ef0` | one closure rule over published edges, the heading-nesting fix, context sets and override sets |
| cache | `68b148c` | the disclosure verifier's answers remembered |
| P2.7 | `6ac58f5`, `03bb349`, `1d6d2be`, `b2c8ef1` | S-19 and S-20, the survivors and the sinks, the reason vocabulary control, one owner for why a session is unknown, and a refused run that cuts no self-test section |

Six files, +13,265/-3,303 against the base (`git diff --stat 98fb8fb b2c8ef1`).

The contract is "step 0 final", a design file of the implementer's that is not in the repository. Every clause
this record relies on is restated where it is used, with its number (S-1 to S-27). It was built from the brief's
items (#1 to #16) through three design passes, cross-checked before any phase-2 code.

Every commit was judged by its dev pass, its revert rows and the commit hook, and its claims were checked against
the commit by the lead. The suites' results on `b2c8ef1` are in section 7.

## 2. The published shape

Everything is under the run's `inventory/` directory. Each file is a registered output of the inventory stage, and
`manifest.json` lists every other file with its document kind, its opaque id (or null) and the sha256 of the
bytes written. The manifest is not in its own list; its sha256 lives in the stage's output record, like every
stage output's.

| file | document | holds |
| --- | --- | --- |
| `current.json` | `current` | `units`, `layers`, `scopes` (one row per scope answer), `scope_universe`, `unknown_entries`, `closure_rule` |
| `selection.json` | `selection` | the `--pin` session's selection: `units`, `layers`, `unknown_entries`, `closure_rule` |
| `release.json` | `release` | a segment index: per session and segment, the release inventory it names and the source of each layer row |
| `sessions.json` | `sessions` | `sessions`, `events`, `segments`, `occurrences`, `context_sets`, `override_sets`, `unknown_entries`, `span_unit` |
| `shared/store.json` | `shared_store` | every carrier version the run names, once (`versions`), and its context-free units (`units`), each by its `r-` reference |
| `shared/release-<i>.json`, `shared/selection-<i>.json` | `shared_inventory` | one per distinct release baseline and per distinct snapshot: layer rows, carrier-version references into the store, unit references, `edges`, `unknown_entries` |
| `manifest.json` | (none) | the artifact list, the session and store counts, `references.release` `{sessions, segments, complete_segments}` |

A session record (S-14) holds `session_ref`, its display names, `kind` (main or subagent), its transcript, parent,
owners and ownership intervals, `binding`, `read` (`bound`, `appended`, `changed`, `unbound`, `binding_invalid`,
`no_path` or `unreadable`), `lines_read`, the inherited `session_meta` counts, `own_meta_unidentified`,
`limitations`, `pin`, `selection`, `delivery`, its event and segment references, and `unknown` entries. Nothing in
it is truncated.

Joins across documents use opaque ids only: `p-` session, `o-` owner, `e-` event, `s-` scope, `q-` occurrence,
`g-` segment, `x-` context set, `v-` override set, `k-` unknown requirement, `i-` shared inventory, `r-` unit
reference, `c-` carrier. Each is a fixed prefix and the first 24 hex of the sha256 of a canonical JSON array
(`separators=(",", ":")`, `ensure_ascii=False`) over raw values. Display fields are projected metadata and never a
join key.

A reader who wants a unit's operative context computes it from published edges with `published_closures`, under
the document's `closure_rule` (section 3.8). `current.json` alone keeps closures on its units (section 3.9).

## 3. The contract's decisions, item by item

### 3.1 The Codex layer value (S-19)

A Codex rollout records one undivided block of instructions, not separate global, project and memory files. It
is published as its own layer, `native_undivided`, in the schema's enum and in `LAYERS`. Its current answer is
chosen per `(codex, cwd)` by S-8, its release answer is the native event in force in the segment, and selection
declares it absent (`unknown: per_event`). At a Codex scope or event the three divided layers are
`unknown: codex_undivided`; at a Claude event the block is complete and empty. A Codex event's `payload.git` is
published as provenance `git {commit_hash, branch, repository_url}`, the URL's userinfo removed before the floor.

P2.7's audit found every clause held by a control except one: at the current reference point, a run whose
transcripts are all Claude publishes `native_undivided` complete and empty. That control is new in `6ac58f5`; the
product code did not change.

### 3.2 The memory rule (S-9)

A memory directory D answers from the last eligible event that named it (S-8's order). A later event at another
host or project says nothing about D, and D stays `answered`, with the design §8 freshness sentence. A later
eligible event at the same host and project that names no member under D makes D `unknown: memory_unconfirmed`,
the earlier set kept as evidence and the later event's id in the reason. A later event whose AutoMem membership is
itself unknown gives D that reason (`member_unmapped`, `container_unusable`) or `incomplete`, never
`memory_unconfirmed`.

The reason: the host loads a project's memory with that project's session, so an injection elsewhere is no
statement about it, while an injection in the same project that leaves it out is.

"Same project" is the host's own test, applied lexically. The host names a project's memory directory
`~/.claude/projects/<slug>/memory`, the slug being the project path with every non-alphanumeric character a dash.
The inventory applies that character rule to the recorded cwd string, without resolving anything on disk, and
compares it with the `<slug>` segment of D's recorded path. Plain cwd equality is the fall-back only when D's path
has no `projects/<slug>/` segment. Two missing cwds are never one project.

### 3.3 Codex pins and rollouts are never joined (#7, S-16)

`unknown: id_space` covers exactly the producers that need a Codex session's pin or snapshot: selection catalog,
adopted packages, overlays and injection; release overlays and release session injection; and `current`'s
injection for a Codex `--pin`. No pin is associated with a rollout by any means, an equal id included. The Codex
session's release catalog and adopted packages follow S-24 like any unpinned session's, and `native_undivided`
answers from its events. A `--pin codex:<id>` snapshot is evidence about that pin only.

The reason and its revisit condition are the 1548 record's §12: activation pins the app-server thread id, the
host writes rollouts under its own uuid, and on 2026-10-23 none of 15 pins joined any of 2,631 rollouts. An equal
id would be a coincidence of two stores, not a join. Section 9 carries the condition.

### 3.4 Usable units of an incomplete layer (S-20; rulings R19, R20, R21)

At the base `produce` split a whole layer at once, and an empty-text carrier made the row `incomplete`. Now
(`6ac58f5`):
- each carrier is split alone; a carrier that raises `Malformed` or `Unsupported` adds `"{layer}: {message}"` to
  the row's reasons and drops only its own units; a complete row becomes `incomplete`, a row that was not complete
  keeps its status, and the other carriers' units are published;
- a row whose every carrier's text is exactly `""` is `complete`, `empty`, with no unit and no reason; the version
  stays in the store with length 0 (R20: exactly empty; whitespace splits into blocks and yields units);
- a row with content that yields no unit stays `incomplete` with "a layer is never silently empty"; today's
  splitter yields a unit for any non-empty text, so only a planted splitter reaches this branch;
- R19: an unsupported carrier among others makes the row `incomplete`, not `unsupported`. `unsupported` stays the
  status of a producer that raises `Unsupported`. A row whose every carrier is unsupported read `unsupported` at
  the base and reads `incomplete` now (section 4);
- R21: a row mixing empty and non-empty carriers is `complete` and not empty, as before.

### 3.5 The naive instant (S-3)

An event's `at` is UTC from `timestamp` (Codex also `payload.timestamp`): an ISO string with `Z` or an offset, or
a finite epoch number of seconds. An ISO string with no zone is refused as `undated_naive`; absent or other shapes
are `undated`. This diverges from `census.parse`, which reads a naive string as UTC. Inside one transcript the raw
line already gives the order; across transcripts a guessed zone decides which session's answer is `current`, and
a wrong guess hands one session's answer to another. Cost on 2026-10-28 (lead, counts-only): 1,492 of 1,492 Claude
and 1,345 of 1,345 Codex instants carry a zone.

### 3.6 `provenance.record` means the raw line

A transcript native unit's `provenance.record` was a decoded record's index; it is now its event's raw line, the
record's 1-based number among the transcript's complete lines (S-2). The same number is the event's `line` in
`sessions.json` and the `line` views publish for a turn, which is how a turn is joined to its owner and segment.

### 3.7 Inherited `session_meta` (S-23)

Every Codex `session_meta` is tested for the rollout's own id, because a later one can carry the id census took
from the file name. One with another session's id, or with none, is inherited, never an event, and is counted in
two categories that stay apart because their grounds differ: `another_session_id` and `no_session_id`. A first
`session_meta` with no id and no later qualifying one gives `own_meta_unidentified` with its line on the session
record, beside the `no_session_id` count, and distinct from a rollout with no `session_meta` at all.

### 3.8 Universe-specific edges, the override key, and the reader rule (S-12, S-11)

Why edges and not closures. `operative_context` resolves a mention by exact path or by BASENAME over the whole
universe of carriers it is given, and says when a name is ambiguous. So a segment whose events carry a native
`CLAUDE.md`, `AGENTS.md` or `MEMORY.md` changes the `reached` list of every catalog unit that mentions that name.
One closure per shared inventory would be wrong for every segment that adds such a file; one closure per segment
would copy every inventory into every segment.

The published form:
- A shared inventory publishes, per unit, `direct` (its own frontmatter, enclosing headings and condition spans,
  intrinsic to its carrier version) and `reached` (its mentions resolved in the inventory's own universe).
- A segment's universe publishes a context set `x-`: the event units' own edges, plus OVERRIDE `reached` lists for
  the shared-inventory units whose `reached` differs in that universe. `direct` is never overridden. A context
  set's id is over every carrier version of its universe and the `i-` ids of the inventories its segment names.
  Context sets are deduplicated by that id.
- An override set `v-` is keyed per shared inventory: the `i-` id of the inventory whose units it overrides, and
  the sorted `[resolution path, carrier_id, version_sha256]` triples of THAT inventory's matched mentions. Each
  component is needed:
  - the inventory: the triples name the mentions' targets, not their origin; two inventories that resolve against
    the same native versions have different units and need different overrides (a guide nothing mentions, that
    itself mentions `CLAUDE.md`, still needs one);
  - the version: a `reached` entry is version-qualified, and a heading mention resolves to the units of the
    version at that path whose heading matches, so one path set with two native versions gives two override sets;
  - matched carriers only: a unit's `reached` reads only the carriers its mentions match, so a carrier no mention
    matches (a `MEMORY.md` the catalog never names) is not in the key and makes no new set. Measured: eight
    universes gave 8 context sets and 4 override sets, the two `MEMORY.md` versions changing none (`f506ef0`);
  - the path is the resolution path, the carrier's `path` as `carriers_at_path` holds it (R15 (a): the raw path,
    as written; the id is therefore not recomputable from published files, section 6).
- Every unit whose `reached` differs gets its override, whether or not anything in the segment reaches it.

The reader rule. `inventory.py` exports one function, `published_closures`, that closes from published edges only
(shared edges, then the context set's overrides), never from a source tree or a state root; `operative_context`
runs the same loop (`closure_of`), so there is one rule. Every document carries `closure_rule`
(`operative-context/1`) and every context set its `closure_digest`, the sha256 of the canonical closure map it
yields. The function refuses an unknown rule (`CLOSURE_RULE_UNSUPPORTED`) and a digest it does not reproduce
(`CLOSURE_DIGEST_MISMATCH`), each by name. Edges and closures are sorted before they are published, digested or
compared.

Unresolved mentions are typed entries: each is a terminal requirement `k-` over its origin carrier and version,
the named span, the heading span and its kind, with a display text projected once, at production, under its
origin's floor decision, and never rebuilt at read time. Several origins of one string are several entries
(section 4).

### 3.9 The context asymmetry

`current.json` keeps closures on its units; the shared inventories and `sessions.json` publish edges. A closure is
per document and grows with every universe it is closed over; edges are shared once. Sizes, measured on this
repository's own trees and synthetic files under a fake home:
- one release document per baseline WITH closures: about 15 MB (the contract's size section, three release trees);
- the checkout's own catalog (108 carriers, 1,983 units) as one shared release inventory with edges: edges
  636,918 B, the whole document 739,318 B (`f506ef0`);
- per distinct universe: a context set of 15,948 B, override sets of 28,302 B (13 units, 493 `reached` entries),
  unknown entries of 2,344 B. The contract's estimate was 13 units, 493 entries and 14.7 KB; units and entries
  match, and the bytes are larger by the published row form;
- the number of distinct override sets is the number of distinct combinations of matched `CLAUDE.md`, `AGENTS.md`
  and `MEMORY.md` versions in force per inventory, not the number of segments.

`current.json` is one document per run, so its closures cost one document's size, and it keeps them. Its closures
are now emitted sorted and its unresolved strings are typed entries: a change of order and of form, with closure
membership otherwise unchanged (measured over the X11 fixture, two arms, as sets: section 6).

### 3.10 The launch exclusion and what cannot be seen of it (S-8 (b))

agent-bios launches a Claude session with `claudeMdExcludes` when its pin records
`include_global_instructions: false`. Such a session's events are no outcome at the global scope
(`global_excluded_by_launch`): its global set is an exclusion, not a deletion. For an unpinned session the
exclusion cannot be seen, so every global answer it gives, empty or not, carries the limitation
`exclusion_unobservable` (a user's own `claudeMdExcludes` can remove some members). When a census row names a pin
that is absent or unreadable, the exclusion is not known, and the global scope its chosen event answers is
`unknown: exclusion_unreadable`, its native evidence still published.

### 3.11 The cwd split (S-7)

A project scope is `(host, the event record's cwd)`, the cwd read as data, never resolved. No `cwd` key: the
project scope is `no_scope`, the global scope still answers. A `cwd` that is not a string or not absolute
(lexically POSIX `/…`, a drive `X:\` or `X:/`, or UNC `\\`): `cwd_unreadable`; the host's global scope is
`unknown`, and only the project scopes whose chosen outcome precedes the record become `uncertain`, naming its
event. Each case is counted per host in `scope_universe`, and a layer row is complete only when every scope
answers and those counts are zero.

### 3.12 Unpinned release: option 1 (S-24, owner's decision)

An unpinned session's release catalog and adopted packages, every Codex session's included, are
`unknown: release_history_deferred`. No journal is read for them; the installed-now inventory stays separately
identified. A pinned session keeps its own snapshot's baseline through the chain `pin` -> snapshot's
`inputs.baseline_ref` -> `baseline@<ref>`, and a break gives those rows the broken link's reason (for instance
`pin_absent`, `pin_mismatch`, `snapshot_absent`, `baseline_unnamed`, `baseline_absent`, `input_failed`). Option
2's sketch is in section 9.

### 3.13 Duplicate members (S-12)

One event can record one path twice with equal bytes. Members are collapsed by `(carrier_id, version_sha256)`
before they are split, one copy per version, consistent with `r-`, and each dropped copy is the limitation
`member_duplicate` at its line with its ordinal. Two byte strings at one path stay two versions.

### 3.14 Basename resolution is POSIX-only

A mention resolves by basename through `path.rsplit("/", 1)`. A recorded Windows path (`C:\…\CLAUDE.md`) is its
own basename under that split, so a mention of `CLAUDE.md` does not reach it. Override keys and closures follow
the same rule.

### 3.15 S-8's corrections

- An undated head stays unknown. When a transcript's greatest-line outcome at a scope is undated, that transcript's
  candidate is `unknown: undated`, and an older dated event of the same transcript is never taken instead. A prefix
  of dated records gives a lower bound only. The only upper bound admitted is the instant of the first later
  record of the same transcript with a supported instant, when its instants are non-decreasing up to it.
- Undecodable lines elsewhere. An undecodable or non-object line in another main transcript of the same host,
  after that transcript's last dated event and not bracketed below the chosen instant, makes every scope it could
  follow `uncertain: undecodable_elsewhere`, naming the transcript and line. On 2026-10-29 (lead, counts-only,
  30 days) 1,132 Claude transcripts held 630,686 complete lines and none was undecodable, so this costs nothing
  today.

### 3.16 `~/` memory paths are relative

A recorded memory path that is not absolute makes that memory scope `memory_path_relative`, a `~/` path included:
nothing expands or resolves it. On 2026-10-29 (lead, counts-only, 30 days) every member path of a Claude
instructions attachment was absolute (AutoMem 1,448, Project 722, User 1,400), so the rule loses no answer today;
if the host ever records `~/` paths, every memory scope becomes `memory_path_relative`.

### 3.17 One root per document, not a `oneOf`; one closed limitation row

The contract asked for a root `oneOf` keyed by `document`. The repository's schema policy refuses `oneOf` and
`anyOf` (`runlib/validate.py` `SUPPORTED_KEYWORDS`), so that a closed object cannot hide under them. Each document
has its own `$defs` root with a `document` const; the code's `DOCUMENT_ROOTS` picks it, an undeclared kind is
refused by name (`DOCUMENT_KIND_UNDECLARED`), and a control compares `DOCUMENT_ROOTS` with the consts read from
the schema. For the same reason the `limitation` row is one closed object in the schema; the code's
`LIMITATION_TABLE` holds each kind to its own fields on the publication path, and a control compares its kinds
with the schema's enum.

## 4. What changed for a reader

Phase-1 behaviour the contract changed (S-26), each at its commit:
- a Claude record belongs to a sidechain when `isSidechain` is true or `agentId` is a non-empty string (the
  census's test); an empty or non-string `agentId` leaves it the main owner's, counted `agent_id_unusable`; a
  sidechain with no usable `agentId` has no owner (`ownership_unknown`) where phase 1 named it
  `#sidechain:unnamed` (`f4ef63c`);
- an own Codex record with an unusable block is a damaged event, no longer a damage row only (`f4ef63c`);
- inherited `session_meta` findings live on the session record (`f4ef63c`);
- a valid `files: []` and an empty Codex block are kept as events, so a deletion shows (`952d4bd`);
- duplicate members collapse before splitting (`89dd81b`);
- `current.json`'s closures are sorted, and its unresolved strings are typed entries (`24ea3f5`);
- `produce` splits per carrier and an empty-text layer is complete and empty (`6ac58f5`).

Changes beyond the contract's list:
- `release.json` was a reference point; it is a segment index (`520b010`). It never picks one segment and never
  unions versions.
- A `--pin` the census has no session for gets no release base: its `renames_base` is
  `{inventory_ref: null, reason: no_census_session}`, it adds no release inventory of its own, its renames are
  empty and the manifest maps no baseline (`520b010`).
- `_emit_context` keeps every origin of one string. It used to collapse them to one entry, the withheld rendering
  winning; each origin is now its own typed entry under its own floor decision (`24ea3f5`).
- Two reason keys beyond the contract's list: `baseline_unnamed`, a snapshot that names no usable baseline (where
  `baseline_absent` is a named baseline the state does not hold), and `injection_body_empty`, a session whose own
  snapshot body is empty, so nobody could look for its injection (where `no_record` means no recorded occurrence).
- A row whose every carrier is unsupported reads `incomplete`, not `unsupported` (R19, `6ac58f5`).
- Unit ids are counted once per row. Two versions of one carrier can sit in one row (two byte strings at one
  path, or one file recorded in two scopes at two versions). `units_of` keys a unit by sha256 of the carrier id
  and the block text, so a block both versions hold took `u-<key>` and `u-<key>-2` in a whole-row split, and
  would have taken `u-<key>` twice once split per carrier. `produce` keeps one occurrence count per row, and a
  carrier that fails never moves it. `UNIT_DUPLICATE` now refuses a run in which one unit id names two units of
  one reference document; the closure check after it had assumed this without checking (`6ac58f5`).
- Why a session is unknown is decided once (`1d6d2be`). Its record in `sessions.json` and its entry in the
  manifest's per-session list had each decided alone, and they disagreed in two cases: a Codex rollout whose first
  `session_meta` names no session and no later one is its own (`own_meta_unidentified` in one, `no_record` in the
  other), and a session whose every injection is damaged (`no_record` in one, not listed in the other).
  `session_unknown` now decides, and both documents publish its key; failure texts are byte-equal to before.
- `gates/control-audit.py`'s `DATA_SINKS` for `inventory.py` gains `unknown` (the per-session unknown list) and
  `failed` (`produce`'s per-carrier splitting failures), each published as data (`6ac58f5`). R22 closed with no
  residual: a broader scan had listed `found` in `self_test` as a second unclassified sink, but the audit tool's
  own finder does not report it, and after the two entries it reports none.

## 5. The heading defect

`da8ac2b` (2026-10-22, on this integration branch only, never on `main`, so nothing shipped) built a unit's
`heading`, its enclosing headings and its heading spans by slicing a list by the heading's absolute level
(`[:level - 1]`). A carrier whose first heading is `##` therefore nested its next `##` under it, and a skipped
level (`# A`, `### C`, `### D`) nested D under its sibling C. Three sites re-split the joined heading string on
" > ", so a title that itself contains " > " became two levels.

K6, a control written for P2.6's context edges, found it: its fixture's sibling `## Other` came out nested under
`## Details`. `fdc1965` builds all three from one stack of open headings: a heading closes every open heading at
its level or deeper, then opens. The chain travels on the unit as a tuple (`heading_chain`, never emitted), and
the three sites read the tuple, so a title containing " > " is one level.

What changes, for a carrier that starts below level 1, skips a level, or carries " > " in a title: the unit's
`heading`, `class`, enclosing headings, condition spans and closure. Measured with the real splitter: the 53
markdown files git tracks under `claude/` and `ko/claude/`, closed together, 3,701 units, change in nothing; over
the self-test's own 333 carrier groups, 4,525 units, 13 units change (10 in heading, 1 in class, 10 in enclosing
headings, 13 in closure), each in a fixture of one of those shapes.

## 6. Residuals

None of these contradicts the contract; each is a property a reader or a later package should know.

- A5: a carrier the floor withholds WHOLE publishes `named` and `heading` as null on its `k-` entries, but the `k-`
  id is still over the offsets, as S-12 defines it, and the carrier id and version are published. A reader could
  recover the offsets by searching a small space; the content stays withheld.
- R15 and the other ids: `k-`, `v-` and `carrier_id` each commit to values they do not state (`v-` to the raw
  resolution path under the owner's home, R15 (a)). They are checked where they are built, and `matches` and the
  cross checks hold their targets, but a reader cannot recompute them from the published files.
- R8, R14: a context set is computed over the KNOWN universe. An uncertain event or an unknown inventory is said
  by the segment's `in_force` and the index rows, not by the context set; the empty context set means an empty
  known universe, not "no context".
- The store's units carry no `unit_id`. `units_of`'s occurrence count runs across one call, so one `r-` reference
  can have different `unit_id`s in two reference documents; each document keeps its own.
- Unit order: `current.json` and `selection.json` publish units in one canonical order (layer position, carrier id,
  version, position, unit id) since `24ea3f5`. Measured over the X11 fixture's two arms against `520b010`, as sets:
  the same units, the same records and renames, only the order and `produced_by.state_root` differ. The only
  reader of those units outside `inventory.py` is `distill.py` (`any(...)` at :939-943), which does not depend on
  order.
- One key, three statements: `no_record` ("the transcript records no injection") is the reason at the current
  reference point when no main transcript records a layer, on a session record when no undamaged event exists
  (none at all, or every one damaged, the damage listed before it), and on a delivery with no recorded
  occurrence. Where it sits says which.
- The reason vocabulary control counts a key as driven only when a document the suite wrote carries it. Eighteen
  keys are carried by full `run()` documents and 22 only by documents of two self-test helpers, which run the
  product steps in `run`'s order over fixture inputs and write through `write_document`; those count (lead's
  ruling). The control cannot tell a document someone assembles by hand later. The evidence today is a probe: the
  five hand-assembled documents in the suite carry none of the keys.
- A second class of cut self-test sections, not fixed in phase 2. A product refusal raised by a direct call outside
  `run` or `judged_run` ends its section, and a later section that reads a name the cut one never bound ends too
  (`UnboundLocalError`). Seen only under reverts: P1R1 (8 sections), Y73 and Y78 (one each, the P2.6 context-set
  section). Each of those rows still fails by its own control's name. The first class, reads that assumed a
  refused run's document, is fixed in `b2c8ef1`. Candidate follow-up.
- The disclosure cache's residuals are in section 8.

## 7. The verification process

The owner's decision of 2026-10-30, taken after the owner asked why a commit took about three hours and the lead
measured where the time went, applies from P2.6's last commit on. Each part, with what it saves and what it gives
up. Times are wall times read from the logs' creation and last-write instants, not instrumented, and the rows per
trial differ by commit:

| part | before (P2.6 commit 1, `24ea3f5`) | after (P2.7) | given up |
| --- | --- | --- | --- |
| no post-commit revert when the committed blobs hash-equal the pre-commit trial's bytes | revert 2,371 s | none; the trial's table is authoritative, the hash equality stated | a run in the committed checkout rather than in clones with the file copied over `HEAD`; the bytes are proven equal |
| no prehook | 864 s | none; a state-root snapshot before and after the hook | an earlier failure; the hook runs the same suites, so no coverage |
| the pre-commit trial runs new and retargeted rows and BASE only | 2,316 s | 336-451 s | an existing row in a changed function is not re-run per commit; a regression it would catch shows only at the final sweep, possibly commits later |
| 6 workers instead of 3 | | | nothing seen: no harness timeout or broken pipe in any trial since |
| the disclosure cache | inventory suite 304 s | 142 s | section 8's residuals |

The hook itself ran 1,517 s on `24ea3f5` and 1,115-1,198 s on the four P2.7 commits.

Deferred to the final sweep at this record's head, each row with the function it sits in: `self_test` W29, W30,
G1-G7; `closure_cross_problems` Y63, Y64, Y65, Y91; `units_of` Y68; `session_record` 14c, T7, V28, V29;
`transcript_events` 11a, 11b, V16, V17 (22 rows; V17 already ran on this head's exact bytes, in `b2c8ef1`'s
pre-commit trial, whose `inventory.py` equals the committed blob: reverted, it failed its own control by name,
with no section cut). Three rows whose old strings no longer occur once (X1, X4, 14d) are re-derived there. The
final sweep runs every live row after this record; its result is not here.

Final suites on `b2c8ef1`, clean tree, under the fake home (`final-suites-1.log`, `final-stop-1.log`, 2026-10-30
22:55-23:04): fourteen self-tests (thirteen `runlib/` modules and `distill.py`) and the lexicon gate, `fail=0` in
502 s (inventory 1,072 controls in 154 s, dispatch 520 in 319 s, views 535, gate 196, census 172, distill 130,
declare 110, the rest OK); `runlib/stop.py --self-test` OK, 36 controls, 13 s. The state root was unchanged around
both.

A fact of the date, not a gate this package ran: on 2026-10-30 the owner merged the Python 3.12 floor into `main`
(PR #11, `1d92878`). The lead parsed every tracked `.py` file of this branch's tree outside `design/`, 211 files,
with Python 3.12.12, and none failed.

## 8. The disclosure cache (`68b148c`)

`projection.discloses(text, home)` decides whether a string discloses a secret, a floor pattern or a home path.
The inventory suite asked it 10,769,881 times for 21,291 distinct inputs: 99.8% of the calls repeated an answer
already computed.

What it keys on, and why. A remembered answer is valid only while three things are unchanged: the text, the home it
was judged against, and the rules in force. The key is the sha256 of the text (UTF-8, surrogates passed through;
the text itself is not kept), the resolved home (`~` resolved once per call when None, and the verifier asked with
exactly that home), and a generation. The rules in force are the current values of every module name the verifier
reaches (39, derived from its code objects at import and followed into the module's own functions and classes)
and every public member of `FLOOR`, a list read as the tuple of its items because the floor's patterns are changed
in place as well as rebound. They are compared with `!=`, never hashed; when they differ the generation moves on
and the cache is emptied. Only the answer is kept, never an exception. Inputs that are not exactly `str` bypass
the cache. At most 65,536 entries, oldest forgotten first; a lock holds the compare, lookup and insert, and the
verifier runs outside it.

Measured, one tool for both runs (the inventory self-test in process under the fake home, `discloses` wrapped by
a counter):

| | before (`f506ef0`) | after |
| --- | --- | --- |
| calls of `discloses` | 10,769,881 | 10,838,989 |
| distinct (text, home) | 21,291 | 35,759 |
| time inside `discloses` | 192.64 s | 39.99 s |
| inventory suite, clean run | 304 s | 142 s |

The after run carries the new control's own calls (34,554 direct calls of the uncached verifier and 69,108 more
cached ones, exactly the difference). The wrapper's own cost, corrected: the tool's printed figure (17.26 s)
subtracted every uncached call, including the control's direct ones, and was wrong; recomputed from the hits
alone, the 10,803,230 hits took 28.35 s raw, about 23.3 s with the timers' own cost removed, 15.3% to 18.7% of the
152.65 s saved. Its parts: the rules snapshot 13.95 s, the sha256 1.33 s, the lock 4.77 s. Memory at the end of
the suite: 35,759 entries, about 6.2 MB.

Controls: the remembered answers equal the uncached verifier's over every string and key of every document and
every transcript line the inventory suite wrote, for the fixture home and for None, every second ask a hit; and,
in the projection self-test, a warm cache sees a floor pattern planted in place, a replaced `secret_key`, a helper
replaced two calls below the verifier, each home and a changed `HOME`, its bound, and that every rule value it
compares is immutable and reached by name (`pathlib.PurePath` allowed: a path has no public mutator).

Residuals:
- the names are fixed at import; a function replaced at run time that calls some other name, itself replaced
  afterwards, is not seen (the replaced function itself is in the key);
- attributes of other modules (`os`, `re`, `json`) replaced at run time are not seen, and neither are builtins; a
  home given as None is resolved at every call, so a changed `HOME` is seen;
- a sha256 collision would return a wrong answer.

## 9. Revisit conditions

- #7, Codex pins and rollouts (1548 record, §12): revisit when activation records the rollout the host actually
  writes, or the transcript carries the pin's own identifier, so the two join without guessing. Until then every
  Codex session's selection and delivery are `unknown: id_space`.
- S-24 option 2, the unpinned release history: a follow-up package, after B and before WP-10, builds the
  baseline-selection history from the store's transaction journals. The sketch, corrected to the journals' real
  fields:
  - input `store_transactions` (optional; absent means no transition record):
    `runtime/transactions/*/journal.json`, with `plan.before.runtime.selected_baseline_ref` and
    `plan.after.runtime.selected_baseline_ref`, which record every switch, `reset` and `rollback` included; the
    installer journals become a cross-check, and `baseline@<ref>` an input per mapped ref;
  - the switch instant: `recovered_at` for `RECOVERED_COMMITTED`, `committed_at` for `COMMITTED`;
  - install journals carry no `created_at` and a `PLANNED` journal moves no state, so an install's interval is
    `[the previous switch, this switch)` under its `before` ref; a plan journal's `[plan.created_at,
    committed_at)` is `uncertain: switch_in_flight`;
  - `PREPARED`, `NEEDS_RECOVERY` and malformed journals give uncertain intervals from the last switch before them
    to the next after them;
  - before the first switch: its `before` ref when that is null (nothing installed), else
    `unknown: before_first_switch`;
  - a gap where one journal's `after` does not chain to the next one's `before` is unknown; an equal-second tie is
    `uncertain`; a segment whose first and last supported instants fall in two intervals is `uncertain`;
  - controls: rollback then reset, a hidden (malformed) journal, an interior instant, the switch boundary, a
    recovered install, the `PLANNED` journal, the period before the first switch.
  On this machine (lead, counts-only): 17 store journals, all `install`, 16 `RECOVERED_COMMITTED` and 1 `PLANNED`,
  10 baseline changes, no `reset` or `rollback`.
- D1 option 1, the subagent binding (owner, 2026-10-28): in this package a subagent transcript has no census hash
  and is `unbound`, an honest named unknown. A separate small package records each child's version on its census
  row in the shape an eligible row has (`sha256`, and `versions[-1]` with `sha`, `record_count`, `prefix_sha`),
  makes `views.py` use that binding, and adds an integration check that bound children gain past events while
  staying out of `current`. Until it lands every real subagent's past reference point is `unbound`, which blocks
  WP-10's child-reach diagnosis, so it must be scheduled.
