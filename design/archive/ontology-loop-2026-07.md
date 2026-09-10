# Ontology loop — round record, 2026-07-29 → 2026-07-31

Dated record. True as of 2026-07-31 and not revised since; read it as history.

The loop's **method** — the two loops, the three gap kinds, the stage order, the five verdict
states, the question admission bar, site-agreement support, the ratchet, the output unit and the
judge — was durable rather than round-specific, so it moved to this repo's `AGENTS.md`, where it
is loaded and can be acted on. What remains here is what those rules produced on the days they
ran: which stage stopped for what reason, which claims did not survive being measured, and which
framings had to be narrowed. The reasoning is the point; the state it describes is not current.

Counts that once appeared here have been dropped rather than carried forward. The graph owns
them, `python3 ontology/check-ontology.py` prints them, and a number copied into prose is the
exact failure this loop was built to remove.

---


## Stage A items, and what closed each one

| | Item | State |
| --- | --- | --- |
| **A0** | Purpose extraction — separate stated from inferred clauses; inferred ones await user confirmation | **complete 2026-07-31.** Declared complete 2026-07-30, reopened the same day by its own review, and closed once the demotion landed: `inferred` is empty and `purpose.extraction_status` is `settled`, which the gate judges rather than the prose asserting. The contradiction the demotion left is stage-C work, not A0's |
| **A1** | Purpose clauses vs existing golden relationships, both directions, producing the first question set | **complete 2026-07-30** — the mapping is data (`golden_relationships[].serves`), both directions are checked, and `check-ontology.py --coverage` prints the standing report |
| **A2** | Extractors return a **site set**, not an answer | **complete 2026-07-31** — every multi-authored value now has a site-set extractor (tier binding, user-owned regions, domain classification, plus the subcommands and GR-4 comparisons that already were). What remains single-site genuinely has one author or is a filesystem observation |
| **A3** | Unrun sweeps — nested config keys, call sites, consumers | **complete 2026-07-31** — config keys clean, consumers forced GR-6 to name its reader and became a check, call sites yielded one finding and deliberately no check |
| **A4** | Declare each licensed asymmetry **naming the implementation site** (undeclared ones are demoted to contradictions) | **complete 2026-07-31** — `verdicts.licensed_asymmetry` holds the declared ones and a gate proves each declaration names its site; the undeclared candidates were demoted |
| **A5** | Retroactive audit of authored fields — re-record as decisions what were decisions | **complete 2026-07-31** — the gate's own copy of the edge vocabulary is gone, `GR-4`'s silent verdict is an open decision, and two inherited audit items were unfounded |
| **A6** | Apply the question admission bar; retire questions that fail it | **complete 2026-07-31** — every question names the purpose it serves, two were retired with reasons, and the bar is a gate |

**A stops when**: for every purpose clause, the dependency set of the decisions that clause
requires is settled. Purpose clauses are finite and come from source, so completion is provable.
The earlier candidate ("no questions left to verify") was circular — writing no questions
satisfies it. A0 is what closes that circle.


## Findings carried into B (from A0)

Product observations surfaced while extracting purpose clauses. Neither is a purpose violation —
they are a lifetime problem and a surface problem — so they are held here rather than in the
graph's `open_violations`, and triaged in stage B.

- **Install backups accumulate without bound.** Every `install` writes
  `$STATE_DIR/backups/<timestamp>/`, nothing prunes, and `uninstall` deliberately keeps them
  (it prints the `rm -rf` line instead). Growth is unbounded in the user's home.
- **`rollback` is not on the CLI surface.** `compose/corpus-state.py rollback` exists and is
  reached from the launcher, but `agent-bios` advertises only install / verify / status / update /
  uninstall / help. A CLI-only user has no way to learn recovery exists.

- **The install backups have no declared restore consumer.** They were first classified here as
  a **licensed asymmetry** on the grounds that the consumer is a human and `README.md` says
  where to look. That classification is **withdrawn**: §5 requires a declaration that names the
  differing implementation site, and `README.md:79` states a storage location, not a restore
  contract. Unclassified until someone either declares the contract or records the gap.

- **`PU-14` was demoted, and what it described is now undecided.** The clause claimed every span
  written into a user-owned file is identifiable as ours and carries matching merge/check/remove,
  and that the entry files are never manifested. Both halves are false in real code:
  - Full mode — the default — deploys the entry `CLAUDE.md`/`AGENTS.md` through `deploy_file`
    (`install.sh:481,488`), which manifests unconditionally (`:97`), and `uninstall` replays the
    manifest with `rm -f` and no backup (`:661`). The packaged-mode comment at `:112` that said
    otherwise is scoped to `assemble_packaged`.
  - Of the four spans the clause named, only the Codex config block and the zsh hook line carry
    the full triad. The settings hook registrations and the `AGENTS.md` central region have a
    merge path and no check or remove path in `uninstall`.

  Sites disagree and no declaration names them, so under §5 this is a **contradiction**: a
  stage-C decision, not something A0 may admit. The options are to narrow the rule to packaged
  mode and record full mode as licensed, or to keep the rule and record three code sites as
  violations. Do not settle it before A is exhausted.


## Round log

§8 requires every round to record why it stopped, or "a round was run" is unfalsifiable.

### A0 — 2026-07-30, stopped by its round-end review reversing the completion claim

Judge: three isolated `gpt-5.6-sol`/`max` passes, hermetic profile, read-only, working directory
outside the repo so the repo's own `AGENTS.md` could not load as instructions (it is a subject
document). Perspectives were **evidence / inflation / escape-hatch**, substituted for the default
correctness / security / reproduction because the subject is a set of judgements, not code, and
§ "choose perspectives that can bite" applies. Participation: 37 / 25 / 38 checked spans; all
three ran the gates themselves.

All three returned *"A0 does not stand as claimed"* and all three named `PU-14` the weakest
claim. Re-verified against real code before acting; every item below was confirmed, none were
taken on the reviewer's word:

- `PU-14` false on both halves → demoted, now a stage-C contradiction (above).
- `PV-3` was a **false debt**: it condemned `shell-deployed-as-target` for being two halves of
  one mechanism, which `ontology/dependency_rules.md:91-99` gives as that kind's own worked
  example. Removed; the id was not reused.
- `PV-1` undercounted the restating surfaces — `codex/agents/*.toml` pin model and effort too —
  and `dependency_rules.md` had already named the gate-holds-a-constant case, so it was recorded
  as a discovery when it was an unacted-on known. Row widened, framing corrected.
- Two gate holes, both reproduced: a blanked quote passed because every file contains the empty
  string, and nothing asserted the inferred set was empty at stage end. Both now judged, with
  negative controls; the empty-inferred claim is judged against `purpose.extraction_status`
  rather than asserted in prose.
- New debt `PV-4`: `extract.py::subcommands` computes advertised-vs-implemented disagreement and
  `check_derived_agreement` reads only the implemented count — a produced value with no consumer.

Both carried-forward items were then closed by measurement, and both reviewer framings needed
narrowing — the pattern the review-request guide predicts, where the defect survives and the
causal story does not:

- **The prune is guarded, and the guard is weaker than the clause.** `migrate()` takes a
  `corpus_loaded` argument and `claude_corpus_loaded` implements it, with three self-test checks
  — so the passes' framing that presence alone authorises the delete is wrong. What the guard
  cannot see is a *declined* import approval, because it tests whether the entry file contains
  the import string; probing it shows it also passes on the string inside a fenced block or a
  prose mention. That is `PU-13`'s exact statement, so it is recorded as `PV-5` against `PU-13`,
  not `PU-16`, and at the severity the residue deserves: the lesson survives on disk in the
  bundle, it stops being loaded.
- **`PT-T1` stays transitional, with a sharper finding.** The escape pass was right that the old
  wording ("nothing declares") is false — `compose/canary.sh` calls the full-mode no-bundle shape
  "by design". It was wrong that the classification fails: what is undeclared is whether the two
  modes coexisting is a transition, which is the half that decides ownership. The row now says
  which half is declared and carries the user's 2026-07-30 decision as its support.

**Caveat on the convergence.** All three passes are the same provider and model. Under the
multi-model guide that makes their agreement high-confidence but blind-spot-sharing: their shared
finding that `PU-13`, `PU-16` and `PU-17` are genuinely distinct is **not** verification of that
point, only an absence of objection from one reviewer kind.

### A1 — 2026-07-30, stopped on its own completion criterion

The mapping between obligations and purpose is recorded as data, not prose:
`golden_relationships[].serves` names the clauses each obligation exists for, and every unserved
clause carries an `enforcement` decision. The two directions are deliberately asymmetric.

- **Obligation → purpose fails structurally.** A named clause either exists or it does not, so
  a `serves` naming nothing real, a missing `serves`, or an empty one with no `orphan_reason`
  turns the suite red.
- **Purpose → obligation only discloses.** `--coverage` prints it and never fails. Some clauses
  are judgements no gate can decide, and failing on them would push the loop to invent checks to
  clear a counter — §11's Goodhart case. `accepted` is therefore a real closure, and what the
  gate refuses is silence: an unserved clause with no decision recorded.

Result: 8 of 16 clauses are served. Of the 8 that are not, two are `accepted` (`PU-9`, `PU-10` —
both judgements about text that no inspection decides), one is enforced `elsewhere` (`PU-8`, by
`gates/test-assemble.sh` scenario S1, never lifted into the golden set), and five need an
obligation built. Two of those five are the clauses promoted this same day — `PU-16` and `PU-17`
went in with no obligation serving them, and `PV-5` shows `PU-16`'s gap was already live.

`PU-3` was not left unserved: derived closure does enforce its content half, so `GR-2` was
widened to name it. The behavioural half is `PL-1`'s declared non-guarantee, not a gap.

**`GR-12` is rootless and stays that way for now.** `PU-14` was its purpose root; demoting
`PU-14` left a real obligation — a deploy target is never a span of a file the user owns — with
nothing requiring it. It waits on the stage-C decision that replaces `PU-14`, and the reason is
recorded on the row rather than left to be rediscovered.

### A2 — 2026-07-30, first conversion, deliberately not the last

The pattern the design asked for already existed in one place: `subcommands()` returns the three
sites a command is authored at and the disagreements between them, written that way because an
extractor keyed on the `case` block alone had reported `learn` as nonexistent. A2 generalises it,
starting with the value this round found restated most widely.

`tier_binding_sites()` reads `launch/agent-launch.toml` and `codex/agents/*.toml` and reports
both their values and where they conflict. Two rules keep it honest:

- **Absence is not disagreement.** A template that names a model and no effort is saying less,
  not saying otherwise — FRONTIER's effort varies per dispatch, so pinning it in the template
  would be the wrong fix. Only a value declared on both sides and differing fails.
- **A site it cannot compare is named, not guessed at.** The guides' Environment Binding tables
  restate the same bindings in display names with no declared id-to-display map, and
  `check_parity.py` holds its own literals. Both are listed as uncomparable sites, which is what
  `PV-1` is now scoped to.

The consumer matters as much as the extractor. `subcommands()` had computed
`advertised_but_absent` since it was written and **nothing read it** — a produced value with no
reader, which is the repo's own definition of inert. `check_site_agreement` reads it, so a
command added to the dispatch and not to `usage()` now fails. That closes `PV-4`, which was
recorded a few hours earlier in this same round.

Two more conversions followed, and the second one settled what the consumer is *for*.

`user_owned_regions()` had read `install.sh` alone, so it saw the zsh hook and the Codex config
block and never saw the two spans `assemble.py` writes — which are exactly the two with a merge
path and no remover. The defect that broke a promoted purpose clause was invisible to the
machinery whose job is finding it. It now reads both authors and reports lifecycle ops per span,
because the question is never "does this repo remove things" but "does THIS span have a remover".

`domain_manifest()` had read `compose/domains.json` alone, which made the manifest true by
construction: an anchor matching no bullet, or a guide on disk nobody claimed, still looked like
a well-formed manifest. It now reads the manifest, the corpus text and the filesystem, reusing
`compose/check-domains.py`'s own matching rules so the two cannot drift into different
definitions of one disagreement.

**What the consumer asserts differs by who owns the enforcement.** For the domain classification
the answer is `check-domains.py`, which `check-parity.sh` already runs with its own self-test —
so re-failing on the same disagreement here would make this a second author of one rule, which
is what `PU-15` forbids. What is asserted instead is extractor health: all three sites still
read, over a non-empty subject. The ontology's job there is seeing the comparison, not repeating
it. Where no one else enforces — the tier binding across profile and templates — the consumer
does fail.

### A3 — 2026-07-31, the sweep's yield was a concept, not a list

**Config keys: clean, and the empty result cites itself.** Every leaf key name in
`launch/agent-launch.toml` was checked for an access site — subscript, `.get`, attribute or
shell variable read, not a bare mention — across `launch`, `compose`, `learn`, `gates`,
`wrappers` and `install.sh`, with the ontology tree excluded because it reports keys rather
than consuming them. All 43 have consumers. Five `severity_map` entries looked unread and are
not: the map is consumed whole and its keys are looked up dynamically, which a name search
cannot see.

**Consumers: the rule had to be sharpened before it could find anything.** Applied literally,
GR-6 — "each declared value has a reader on the live path" — condemned 23 of 60 extractor
fields, of which one was real. The rule measures "reader" as "code reader", so every value made
for a person to read fails it. That is the same question the install backups raised earlier the
same round, and a question that arrives twice is a missing concept.

The fix keeps the default dangerous-side-up: **a produced value is gate-facing unless it is
registered otherwise.** Forgetting to register fails; registering is a decision with a reason
attached, and a reason can be argued with. The alternative — marking every field with its
audience — fails silently when someone forgets, which is the wrong direction for a default.
`extract.py` carries the registry, because the producer is the one who knows who it is for.

Three ways to fail, all controlled: unread and unregistered, registered with no reason, and
registered while something actually reads it — the last is what stops the list rotting into a
permanent excuse.

One field was deleted rather than registered. `gr4_deploy_verify.violation` was
`bool(uncovered)` with no reader: a second statement of a fact that already had an owner, so
`PU-15` says remove it, not document it.

**The control caught the check being permissive.** The first negative control could not fail,
because planting a field named it in the self-test source — and this file is one of the sources
the reader search reads. Test scaffolding was counting as a consumer. The self-test body is now
excluded from reader detection.

**Call sites: one real finding in 361, and no gate.** All 31 shell functions in `install.sh` are
called. Of 361 Python definitions across the runtime and gate trees, 30 had no reference by name
— and 29 of them are `gates/check_parity.py` checks dispatched through a decorator registry,
which reports 33 entries at import. A name search cannot see registry dispatch, so those are the
sweep's error, not the code's.

The one real hit is `compose/pkgid.py::segments()`, written for deploy-path derivation that the
multi-package composer needs and nothing calls today (`FINDINGS.md` F-12).

**This sweep deliberately does not become a check.** One true positive against twenty-nine false
ones is a gate that would be silenced within a week, and silencing it is worse than not having
it — §8's point that an unenforced obligation recorded as accepted beats a check people learn to
ignore. It stays a sweep to re-run, not a rule.

### A4 — 2026-07-31, two licensed, two demoted, and a home for the verdicts

The rule this stage exists to enforce is that a declared exception must **name the site it
excuses**. A rule that names no site would excuse every site, which is how "it's declared
somewhere" becomes cover for a real disagreement. That is now mechanical: `names` must appear
inside the quoted declaration, and the quote must still be in the file it is attributed to.

**Licensed, with the declaration naming the site:**

- `LA-1` — `helm` has no Codex agent template. The config fragment must be exactly the spawnable
  tiers `(no helm)`, which names helm and says why: helm is the main seat, not a spawnable
  subagent.
- `LA-2` — `frontier.toml` pins a model and no effort. The gate fails if the field is *present*
  — "must omit `model_reasoning_effort` so HELM can pin task-fit effort per dispatch". The
  absence is enforced, not tolerated.

**Demoted, because nothing names them:**

- `reviewer.toml` is a template that is not a launch tier. It is excluded from the fragment only
  by an enumeration that happens not to contain it, and an enumeration is not a naming
  (`FINDINGS.md` F-11).
- The install backups' missing restore consumer, already withdrawn earlier this round for the
  same reason: `README.md` states a location, not a contract.

**One candidate turned out not to be an asymmetry at all.** A prior session recorded that
`claude-prompting`'s `targets` list was broader than the launch profile and licensed only by a
note in gate output. Measured today the two are identical, four models each. It is `admitted`,
not licensed — the fifth inherited claim this round that did not survive being checked.

**The verdicts got a home.** `transitional` had been living under `purpose`, which holds
extracted clauses; a judgement about a claim is not a purpose clause. Both now sit under
`verdicts`, named for the vocabulary in section 5, so the data's shape matches the design's.

**The gate caught its author.** `LA-1`'s first quote was truncated just before `(no helm)`,
because the declaration spans two adjacent string literals — so the recorded licence did not
contain the name it claimed to. The check failed on exactly that, which is the behaviour it was
written for.

### A5 — 2026-07-31, the audit's biggest hit was the auditor

The candidate set is every graph field an extractor does not produce: `guard` values, kind
assignments, obligation directions, `pos` sets, family assignments, `desc`. The inherited list of
suspects was four items; two survived contact with the code.

**The ontology was breaking `PU-15` inside its own machinery.** The nine edge kinds and their
obligation directions were authored in `dependency_rules.md` **and** restated as a
`DECLARED_KINDS` dict in `check-ontology.py`, with nothing comparing them. `check_edge_integrity`
reads the dict, so the gate was the real authority while the document looked like it — flip a
direction in the prose and the gate keeps enforcing the old one, silently. The dict is gone; the
vocabulary is parsed from its documented home, and a parse yielding nothing raises rather than
returning an empty mapping. Proven by renaming a kind in the prose and watching the gate fail on
the edges that use it.

**`GR-4`'s `violated` was a judgement wearing an observation's clothes.** Three of twelve deploy
targets carry no verify assertion — that part is computed. Calling it a *defect* rather than a
licensed exemption is a choice, and the second reading is real: a wrapper is re-deployed on every
install, so drift is self-healing and byte-checking it buys little. Recorded as `D-1`, status
open, with the alternatives it ruled out. A golden relationship claiming `violated` must now be
named by a decision, and an open decision must list at least two options — a decision with one
path is a conclusion wearing a decision's shape.

**Two inherited items were unfounded.** The claim that the F5 assurance entities were declared
"legitimately outside the path" matches no text in the ontology prose, and the count given for
them was wrong (eight, not five). The claim that the nine obligation directions were undocumented
judgements is also wrong — `dependency_rules.md` states each direction *with its reasoning*,
including the one that was reversed after a traversal silently answered nothing. They were
documented; what they lacked was being the only copy.

### A6 — 2026-07-31, the bar became a field, and stage A closed

Section 6's first condition — a question must name the decision it serves — is now data: every
competency question carries `serves`, naming the stated purpose clauses whose decisions change
with its answer. Naming *the purpose* rather than a free-text justification is the whole point;
a decision consumer invented for the occasion legitimises the question that invented it.

Fourteen of sixteen questions pass. Two were retired, and the reason is kept rather than the
question deleted — a silent delete leaves no trace of having been judged, so the next reader
re-adds it.

- `CQ-N-01` "why does this entity exist, and which decision does it support" is not a question
  about the target; it **is** the admission bar. It survives as the `serves` requirement every
  question now carries.
- `CQ-N-02` "what rule governs adding a new entity or edge" asks about the ontology's own
  authoring process, not about the service the ontology describes — meaning reproduction with no
  decision about the target behind it. Its content already lives in `dependency_rules.md`.

Three failure modes are controlled: a question serving nothing, a question serving a clause that
does not exist, and a retirement with no reason.

**Stage A is closed.** A0 extracted purpose and had its completion reversed by its own review;
A1 traced every obligation to a purpose and found half of them habitual; A2 made every
multi-authored value report its sites; A3 swept config keys, consumers and call sites and turned
one of them into a concept; A4 made a licence prove it names its site; A5 caught the gate holding
its own copy of the vocabulary; A6 bounded the question set by the purpose it serves.

What A produced for B: the contradictions it refused to settle — `PU-14`'s demotion, `reviewer`
as a template that is not a tier, `PT-T1`'s undeclared half — plus twelve implementation defects
in `FINDINGS.md` and one open decision, `D-1`.

### B — 2026-07-31, two contradictions surfaced, one candidate dissolved

Stage B surfaces and does not settle. Its output is `verdicts.contradiction` and
`verdicts.unlinked`, with a gate that keeps both honest.

**`UL-1` dissolved a contradiction A4 had recorded.** The launch profile's
`[hosts.codex.agent_templates]` declares which tiers have a template — three of them — and
`reviewer.toml` is a review role that was never in that mapping. Comparing the whole
`codex/agents/` directory against the tier list compared two different sets, so "a template with
no tier" was a link the ontology drew, not a disagreement in the code. Fixed where the fault was:
`tier_binding_sites` compares against the declared map now. This is exactly the case the
`unlinked` verdict exists for, and without it the fix would have gone into the code.

**Two contradictions stand, both refused rather than settled.**

- `CT-1` — the ownership rule. Full mode manifests the entry files and packaged mode does not;
  two of the four user-owned spans have a merge path and no remover. Nothing declares the rule as
  packaged-mode-only, and nothing exempts those two spans. This is what `PU-14`'s demotion left,
  and it is what leaves `GR-12` rootless.
- `CT-2` — whether the two install modes coexisting is a transition or the design. The *shape* is
  declared (`canary.sh` calls full mode's missing bundle "by design"); which of the two it is, is
  not — and that is the half deciding who owns the loading obligation.

The gate's floor is two sites per contradiction. A contradiction recorded with one site reads as
a defect at that site and gets "fixed" there, which is the move stage B exists to prevent.

### C — 2026-07-31, first batch

`CT-1` decided, and the implementation refined the decision. "Keep the rule and fix the code" was
approved; building it showed the entry-file half does not survive contact. In full mode the entry
file IS the corpus, so refusing to manifest it would leave the whole corpus behind after
uninstall — trading data loss for junk the user cannot identify as ours. The actual defect was
narrower and worse: uninstall deleted with **no backup** while install backs up before
overwriting. That asymmetry is closed, the two merge-only spans have removers, and full mode's
entry file is licensed as `LA-3` rather than pretended away.

`D-1` decided: the three uncovered deploy targets are exempt, because a wrapper and the agents
directory are re-deployed whole on every install, so drift is self-healing. `GR-4` stops being
`violated`; the exemption is the answer rather than the absence of a check.

`CT-2` stays open by choice — it splits naturally once the ownership question is settled, and it
now is, so the next round can take it.

The five obligations landed, so `obligation-needed` is empty. The heaviest, `PU-16`, changed what
authorizes an irreversible act: the canary now records WHICH bundle rev it proved loading, and
the prune reads that proof instead of re-deriving a weaker answer from file contents. A plain
`install` runs no canary and therefore prunes nothing; `onboard` prunes after the canary passes.

`PU-18` re-promotes the ownership rule in its corrected form, which gives `GR-12` a root again.


## Corrections

- **Support ranking** (§7) — "source extraction is strongest" was rejected: it treats the
  implementation as truth. Replaced by site agreement.
- **`unlinked` and `transitional`** (§5) — the first four-verdict draft had neither. `unlinked`
  was added after false contradictions were predicted; `transitional` after a full/packaged
  coexistence turned out to be in-flight work rather than a contradiction.
- **R3 "P5 absent means inert" was NOT weakened.** A proposal to qualify it with the packaging
  tier was withdrawn: the corpus case is work in process, which is what the `transitional` verdict
  is for.
- **Stage-A stop condition** (§4) — "no questions left to verify" was circular; replaced by
  per-purpose-clause dependency closure once A0 existed.


## Appendix — borrowed from onto, and not

**Borrowed** — the question frontier, declaring support kinds, the 7-dimension x 3-actionability-
surface coordinate system, the convergence ledger.

**Not borrowed** — artifact and validation machinery (our gates already do this) and the promotion
registry (no runtime entry point exists for it). onto's maturation runtime cannot be run, so the
frame is imported and our gates execute it.



---

# Appendix — the implementation-defect queue as it stood on 2026-07-31

Dated record of what the round found in the product. Twelve entries; the ones marked RESOLVED
were closed during the round, and F-1/F-2 (by `CT-1`'s decision) and F-4/F-5/F-6 (by enforcement
sites in `gates/check_parity.py`) were closed by decisions taken under other names and never
marked here — which is what retired the status field from the live queue.

The items still open on that date moved to the repo-root `FINDINGS.md`, restated.

# Implementation defects found while building the ontology — deferred queue

These are changes to the **product**, not to the ontology. They were found while extracting
purpose and tracing obligations (see `DESIGN.md`), and are parked here on purpose: the ontology
round continues, and these get worked as their own batch.

Every row was re-derived from real code by the author before being written down — where a
reviewer supplied the finding, its causal story was checked separately from its defect, and the
narrowed version is what appears here. `Status` says what is proven, not what is suspected.

Anchors name symbols and files. Line numbers appear only where the line itself is the evidence.

---

## Blocking a decision (stage C owns these)

### F-1 · Full mode manifests the entry files, so `uninstall` deletes them whole

`cmd_install`'s non-packaged branch deploys `claude/CLAUDE.md` and `codex/AGENTS.md` through
`deploy_file`, which appends every destination to the manifest unconditionally. `cmd_uninstall`
replays that manifest with `rm -f` and no backup. Full mode is the default — `usage()` says
"Default (no flag, no saved selection) keeps today's full-corpus deploy."

A user who adds personal rules to `~/.claude/CLAUDE.md` after a default install loses the whole
file on `uninstall`. The comment above `assemble_packaged` that says entry files are never
manifested is scoped to packaged mode only.

**Status:** proven. **Related:** demoted `PU-14`; `GR-12` is rootless until this is decided.

### F-2 · Two user-owned spans have a merge path and no check or remove path

`compose/assemble.py::merge_settings` writes hook registrations into the user's `settings.json`,
and the same file writes the `AGENTS.md` central region between markers. `cmd_uninstall` calls
neither. After uninstall, Claude still invokes hook commands whose files were deleted, and Codex
still loads a central region whose guides were removed.

Of the four spans this repo writes into files it does not own, only the Codex config block and
the zsh hook line carry the full merge / check / remove triad.

**Status:** proven — no settings or central-region removal call exists in the uninstall path.
**Related:** demoted `PU-14`.

---

## Gaps behind a promoted purpose clause

### F-3 · The prune's loading test cannot see a declined import approval

`learn/migrate-learnings.py::claude_corpus_loaded` decides whether the corpus is loaded by
testing whether the entry file *contains* the import string. That blocks the missing-line case,
but probing shows it also passes on the string inside a fenced code block or in a prose mention,
and it structurally cannot detect an import the harness was told not to load — which is exactly
what `PU-13` says file presence cannot detect. The probe that can see it, `compose/canary.sh`,
runs in `cmd_onboard`, after `cmd_install` has already pruned.

The lesson is not destroyed — it survives in the deployed bundle — but it stops being loaded
while the personal copy that was loading is gone.

**Status:** proven, including the probe. **Related:** `PV-5` against `PU-13`.

### F-4 · Nothing keeps the npm `postinstall` script a no-op

`package.json` carries a `postinstall` script. It only prints a hint today, and `install.sh`'s
header states the deployment is "never a postinstall side effect" — but no check asserts that.
The claim rests on nobody having edited that line.

**Status:** proven. **Related:** `PU-6`, classified `obligation-needed`.

### F-5 · The Korean tree's exclusion is permitted, not required

`PU-11` and `PL-2` say Korean is reference-only and never installed. The installer deploys
English only, so the positive half holds. The prohibition half does not exist: `check-package.sh`
exempts `ko` **by name** from the must-ship rule, which permits its absence rather than
forbidding its presence. Nothing fails if `ko/` enters the payload.

**Status:** proven. **Related:** `PU-11`, classified `obligation-needed`.

### F-6 · Capture's directory independence is asserted in prose only

`learn/collect-learning.py` resolves its home from the environment and documents that it works
regardless of the working directory. No check runs it from a foreign directory.

**Status:** proven (no such test exists). **Related:** `PU-12`, classified `obligation-needed`.

---

## Restatements that should be generated

### F-7 · RESOLVED 2026-07-31 — the gate stopped being one of the authors

The model identity in the guides' Environment Binding tables is now read from
`launch/agent-launch.toml` through a declared `[model_display]` map, so
`check_parity.environment_bindings` compares two real surfaces instead of names it
held itself. The tables are not generatable — their cells mix profile data with
policy the profile does not carry, and three rows are not tiers — which is the case
`PU-15` says stays a gated restatement. What was wrong was the third author.

*Superseded text below.*

### F-7 (original) · The tier binding's remaining two authors

`tier_binding_sites()` now compares `launch/agent-launch.toml` against `codex/agents/*.toml`, and
a drift between them fails. Two authors remain outside that comparison: the guides'
`Environment Binding` tables restate the binding in display names with no declared
id-to-display map, and `gates/check_parity.py` compares each surface to its own literals rather
than to the canonical file.

**Status:** proven. **Related:** `PV-1` against `PU-15`.

### F-8 · RESOLVED 2026-07-31 — the fragment is generated now

`gates/emit-mirrors.py` emits the `[agents.*]` block from the launch profile's
declared template map and each template's own description; the authored header and
`features.multi_agent` are preserved because they project from nothing. The first
generated output matched the hand-written file byte for byte, which is the evidence
that the rule is the one a human had been following. Controls cover a hand-edited
fragment and a declared template going missing.

*Superseded text below.*

### F-8 (original) · The Codex config fragment is compared, not generated

`codex/config-additions.toml`'s agent entries restate `description` and `config_file` from
`codex/agents/*.toml`. `check_parity.py::config_fragment` compares them instead of the fragment
being emitted from the templates the way `emit-mirrors.py` emits the Codex trees.

**Status:** proven. **Related:** `PV-2` against `PU-15`.

---

## Lifetime and surface

### F-9 · RESOLVED 2026-07-31 — retention, and a second backup shape nobody had counted

`compose/prune-backups.py` runs after every install and uninstall. A copy is deleted only when it
is **both** older than 30 days **and** outside the newest 10 — either condition alone would delete
something someone still wants, since a busy week ages out yesterday's work and a quiet quarter
trims a set small enough to keep whole.

Measuring for this also found a shape the original finding missed: backups exist in **two**
places. Timestamped directories under the state dir (23 of them, 2.4 MB, on the first machine
measured) and loose `.bak-*` files sitting beside the file they copy in the user's own config
dirs (15 more). The second group is the worse one — it accumulates directly in `~/.claude`. Both
groups are pruned, independently, so one group's churn cannot age out the other's history.

Still open from the original finding: the backups have **no automated restore consumer**, and
`README.md` states their location rather than a restore contract.

*Superseded text below.*

### F-9 (original) · Install backups accumulate without bound

Every `install` writes `$STATE_DIR/backups/<timestamp>/`, nothing prunes, and `uninstall`
deliberately keeps them (it prints the `rm -rf` line instead). Growth is unbounded in the user's
home. Separately, the backups have **no automated restore consumer** and `README.md` states only
their location, not a restore contract — so the "reversible" half of the install promise is a
directory, not a mechanism.

**Status:** proven.

### F-10 · `rollback` is not on the CLI surface

`compose/corpus-state.py rollback` exists and is reached from the launcher, but `agent-bios`
advertises only install / verify / status / update / uninstall / help. A CLI-only user has no way
to learn recovery exists.

**Status:** proven.

---

## Surfaced, not yet classified

### F-12 · `pkgid.segments()` is defined for a feature that was deferred

`compose/pkgid.py::segments()` returns `('scope', 'name')` and its docstring says it is "for
deriving deploy paths". Nothing in the repository calls it — not the two modules that import
`pkgid`, not the installer, not a gate. Derived deploy paths belong to the multi-package composer
that `design/adapter-split/ECOSYSTEM-ARCHITECTURE.md` defers "to the first real second package",
which is the deferral `PT-T2` already quotes.

So it is not dead by accident: it is code written ahead of a deferred feature. That makes the
choice explicit rather than automatic — delete it and rewrite when the composer lands, or keep it
and say in the code that it is waiting on that deferral. Right now it says neither.

**Status:** proven — swept 361 definitions, this is the only one with no reference.

### F-11 · RESOLVED 2026-07-31 — the comparison was wrong, not the code

**Both halves closed.** `helm` having no template is licensed (`LA-1`). And `reviewer.toml` was
never a contradiction: `[hosts.codex.agent_templates]` in the launch profile declares which tiers
have a template — three of them — and `reviewer` is not in that mapping because it is a review
role. Comparing the whole `codex/agents/` directory against the tier list compared two different
sets, so the finding was produced by a link the ontology drew, not by anything in the code.

Recorded as `UL-1` (unlinked) and fixed in `tier_binding_sites`, which now compares against the
declared map and reports files outside it as a list to read.

*Superseded text below, kept because the reasoning was wrong in an instructive way.*

### F-11 (original) · `reviewer.toml` is a template that is not a tier, and nothing says so

**Half of this resolved.** The `helm` tier having no agent template IS declared — the config
fragment must be "the spawnable tiers `(no helm)`", which names helm and gives the reason. That
is now `LA-1` in the graph's `verdicts.licensed_asymmetry`.

`reviewer.toml` did not resolve. It is a required deploy target (`install.sh` requires it,
`check_parity.py::codex_agent_templates` pins its model and effort), and it is deliberately
absent from the config fragment because the fragment is checked as *exactly*
`{frontier, workhorse, sweep}`. But an enumeration that happens to exclude something does not
name it: nothing states that `reviewer` is a review role rather than a launch tier, so nothing
tells the next person whether adding a tier named `reviewer` would be right or wrong.

Under the A4 rule — a licence must name the site it excuses — this stays a contradiction. The
fix is one declared sentence, not code.

**Status:** proven; `helm` half closed as `LA-1`.

---

## Appendix — verdicts that stopped having a subject

Both were live judgements until the install modes converged on 2026-07-31; converging
removed the asymmetry each described. They carried no reader once resolved, so they were
lifted out of the graph on 2026-08-01 rather than left sitting in runtime authority.

### PT-T1 (was transitional)

The transition finished on 2026-07-31. Full and packaged no longer coexist: an install with no selection selects every domain and goes down the same assembly path as any other, so the question of whether the dual path was a transition or the design has no subject left. Resolved 2026-07-31.

### LA-3 (was licensed_asymmetry)

Licensed the entry file being ours in one mode and the user's in the other. With one mode the entry file is always the user's, so there is no asymmetry to license. Resolved 2026-07-31.

