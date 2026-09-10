# agent-bios — Domain-Package Ecosystem (architecture + analysis)

Status: **DECIDED + PARTLY IMPLEMENTED 2026-07-26.** The architecture and its
analysis are from 2026-07-24/25; the two master levers were settled in the 2026-07-26
decision session (see *Decisions*), and the five open ecosystem questions resolved against
them. The four adapter-split questions were decided the same day in `DESIGN.md`. The
foundational contract those decisions call for is at the end of this file, now at **v2**:
v1 was rejected by cross-family review the same day, and v2 was drafted independently by
two providers from one blind packet and synthesized. **Identity, the manifest field, and
the prune authorization are implemented and shipped; the multi-package composer (§3) is
specified and deliberately deferred** — see its status note.
Diagram: `architecture-draft.html` (this folder). Supersedes-by-absorption the narrower
`DESIGN.md` framing (adapter-split is now one facet of this).

## The unified architecture

Three prior threads — **adapter-split** (make agent-bios a general product),
**finer domains** (the technical space is under-differentiated), and **multi-author
versioned packages** — are ONE architecture:

> **agent-bios core (a general instruction engine) + a composable "authored, versioned
> domain-package" ecosystem, with a learning feedback loop.**

Flow (see the diagram): authors (day1 / individual / third-party) publish **author-scoped**
packages (`@scope/name` = a manifest {`package_id`, the domains it declares} + contents
{bullets, guides}) → a distribution channel → the **core composer** selects the user's
chosen packages and domains within them, and composes a **per-user bundle** → deployed to
Claude / Codex (later opencode / Cursor). A **teal feedback loop**: `learn!`/`distill!`
classifies learnings by domain and grows the matching author's package (the collection-loop
we built plugs in here).

*(The identity unit was `@author/domain@version` in the 2026-07-24 draft. The contract at
the end of this file replaced it: a package is unversioned `@scope/name`, and a domain is
package-local. Read that section, not this sketch, for the binding form.)*

## Assessment (is the structure right?)

**Bones are right.** This is the classic **platform + plugins / kernel + modules** pattern
(VS Code extensions, npm, browser extensions, Terraform providers): a stable core +
pluralistic, independently-evolving content. The feedback loop closes the value cycle, and
the multi-author-composition requirement **auto-eliminates the fork** (a fork can't be a
multi-author ecosystem — reconfirms the review's "npm-composition, not fork").

**Two honest concerns:**
1. **Over-build risk (timing).** agent-bios is un-deployed, ~1 user, ~90 domain bullets. A
   full registry/trust/composition ecosystem is infrastructure for a scale that does not
   exist yet. Resolution = the user's instinct is right ("design the foundation in now"),
   but the discipline is **"cheap-but-retrofit-hard FOUNDATIONS now (identity · manifest ·
   namespace); heavy MACHINERY (registry · signing · conflict engine) only on proven
   demand."**
2. **The hard part is content, not plumbing.** Value = well-classified good learnings.
   Packaging/versioning/distribution is the easy 20%; the hard 80% is good content + a
   classification scheme that actually helps. Guard against empty packages.

Recommendation: prove the loop with **day1's own single-author packages** first; open
authorship only when there is demand **and** a trust model. Put **content + trust before
plumbing.**

## Decisions — 2026-07-26

The open decisions were never independent; they all hung off two switches, and both are
now settled. Recorded with rationale so the next reader inherits the decision rather than
the debate.

### Lever 1 — how OPEN, how SOON → **single/org author, retrofit-hard foundations fixed now**

Packages are authored by us (the author / day1) only. No registry, no trust model, no
signing, no precedence engine — those wait for demand that does not exist (~1 real user;
87 domain-tier bullets across 5 domains, 113 in the manifest all told, counted
2026-07-26). What *is* fixed now is only the part that gets expensive
once content accumulates: the package identity unit, the manifest shape, and the
composition contract (see *Foundational contract*).

Rationale: opening later costs one distribution decision. Changing identity or manifest
shape later costs a migration of every package **and** of the `learn!`/`distill!` placement
pipeline that writes into them. Pay only the second cost now.

### Lever 2 — PROSE-only vs CODE-carrying → **prose only**

An authored domain package may contribute instruction bullets and guide documents. It may
not contribute hooks, agents, or scripts.

Note the asymmetry: **core** still ships hooks and agents per domain (`domains.json`
already carries `hooks` and `agents` alongside `bullets` and `guides`), because core is
the engine, not a package. Prose-only binds the *authored package* unit.

**Rationale corrected 2026-07-26 after cross-family review — do not inherit the original
argument.** This section first claimed that prose-only is what drops the trust,
sandboxing, and signing bars to zero, because a bad package is merely bad advice,
recoverable by deselecting. **That is false.** Package prose is instruction text loaded
straight into the agent's corpus — `assemble.py:297` into Claude's central tree, `:305`
into Codex's — and acted on by an agent that holds shell access. A guide can direct an
exfiltration or a destructive command, and deselecting afterwards recovers nothing that
was already disclosed or destroyed. What actually holds the trust bar at zero is **Lever 1
— every author is us.** Prose-only genuinely lowers the blast radius (nothing executes
unread; the content is reviewable by reading) but does not remove it. The consequence is
the important part: **reopening Lever 1 requires a trust model whether or not packages
stay prose-only**, which makes that dependency the most retrofit-hard thing the ecosystem
currently defers.

## The five ecosystem questions — each as a KIND of problem (all resolved below)

| # | Decision | Kind of problem (analogy) | What shifts it | How it changes |
|---|---|---|---|---|
| 1 | **Distribution/composition** (a npm scoped / b own registry·git / c local convention) | **Logistics** — "how do plugins ship/get installed?" (app store vs sideload vs copy-a-file) | who publishes/consumes (Lever 1); discovery need; infra appetite | **(c) now** → (a) npm when public sharing needed → (b) only if npm's model doesn't fit (private gating / custom trust) |
| 2 | **Conflict/precedence** (order / layered / exclusive-owner / namespaced) | **Merge/authority** — "when two plugins disagree, who wins?" (CSS specificity; config layering) | **do packages OVERLAP by design?** (ties to #4) | disjoint domains ⇒ namespace solves it, problem ~vanishes; same-domain override ⇒ need a real precedence engine |
| 3 | **Trust/signing** (closed / org-gated / signed+attributed / open) | **Security/trust** — "will this plugin harm me?" (app permissions + code signing) | **who authors** (Lever 1) × **prose-vs-code** (Lever 2) — instructions are *executed by the agent* | single/org ⇒ non-issue (defer); open ⇒ foundational, retrofit-impossible; hooks amplify it hugely → key sub-decision: **prose-first** |
| 4 | **Domain granularity** (coarse / by-discipline / by-specialty) | **Taxonomy** — "how finely to categorize?" (bookstore sections; folder depth) | content volume; user differentiation; where new learnings naturally fall (discover inductively from the ledger) | little content now ⇒ stay coarse + allow splitting; **split on evidence** when a domain gets fat; do NOT pre-fragment (sparse empty packages) |
| 5 | **Absorb adapter-split** | **Scope/framing** — "are these one thing?" | — | **Yes** — the ecosystem IS the extension mechanism adapter-split was reaching for; unify to avoid designing twice (low-risk) |

**Resolved against the levers (2026-07-26):**

1. **Distribution** → **(c) local convention now.** The domain set stays in the repo-owned
   `config/domains.json`; scoped npm publishing waits for an actual second consumer.
2. **Conflict/precedence** → **namespacing only.** Packages are disjoint by construction
   (one author owns a domain id within their scope); there is no override semantics and no
   precedence engine to build.
3. **Trust/signing** → **deferred entirely**, and prose-only (Lever 2) is what makes that
   deferral safe rather than reckless.
4. **Domain granularity** → **stay coarse, split on evidence** from the incubator ledger.
   Do not pre-fragment; sparse empty packages are the failure mode.
5. **Absorb adapter-split** → **yes.** `DESIGN.md`'s four questions were decided the same
   day and are recorded there.

## Bottom line

- Every decision was downstream of **"how/when open + prose vs code,"** and both are now
  fixed: **single/org · prose-only.** That collapses distribution to local convention,
  conflict to exclusive namespacing, trust to a non-issue, and granularity to
  coarse-then-split.
- The one thing being paid for now is the **foundational contract** — the identity unit,
  the manifest shape, and the composition interface — because those are cheap today and
  require a full content migration later. v1 was rejected on review; **v2 is specified
  below** and its root fix is that a package and a domain are different concepts.
- Everything else (registry, signing, precedence, distribution channel) is deferred to
  proven demand — with one correction: **a trust model is a hard prerequisite of reopening
  Lever 1**, and prose-only does not substitute for it (see Lever 2's corrected rationale).

## Foundational contract (v2, 2026-07-26)

Supersedes the v1 draft, which was rejected on the day it was written. How v2 was produced,
and why that matters for trusting it: v1 was reviewed cross-family (gpt-5.6-sol at max
effort, read-only against this repo; every consumer file was actually opened), returned
eight findings and a reject verdict, and **every finding was re-verified against real code
before being accepted.** None of them overturned a *decision* — the six decisions above
stand unchanged — but all six contract defects were real. v2 was then drafted twice
independently from one blind packet, once per provider (Claude and gpt-5.6-sol), neither
shown the rejected draft, and synthesized below.

> **The six defects v1 had. Each is answered in v2; keep them here so the failure is not
> re-introduced.**
>
> 1. **The identity unit cannot represent core's universal content.** `audience()` returns
>    `UNIVERSAL` for the `core` and `infra` tiers (`assemble.py:72-76`), and those bullets
>    carry `domains: []` — 25 of the 113 in the manifest. A core-only onboarding (empty
>    selection) still retains them, so the required per-bullet provenance has no
>    `@author/domain@version` to name. `@author/domain@version` conflates *package* with
>    *domain*; a package must be able to declare several domains and none.
> 2. **A persisted exact version has nowhere to resolve from.** The contract records
>    `@author/domain@version` in the selection while distribution stays a local convention
>    with a single manifest at the current release. After an update, a recorded `@1` either
>    fails to resolve or silently composes `@2` — an undefined update semantics for the
>    only path that exists.
> 3. **Two of the contract's own clauses are mutually unsatisfiable.** It requires
>    `check-domains.py` to pass "for every package" while also forbidding packages from
>    carrying hooks and agents — but the gate's non-vacuity rule errors when a manifest
>    section is empty (`check-domains.py:130-133`), and its `MANIFEST`/`MONOLITH` roots are
>    hardcoded to core. A conforming prose-only package fails the gate by construction.
> 4. **Bundle-recorded provenance never reaches the prune path, and that path deletes user
>    data.** `build-promotions.py:44` resolves a `placed_anchor` against the single
>    `config/domains.json`, and `promotions.json` persists bare ids
>    (`{"tier":"domain","domains":["builder-base"]}`). `migrate-learnings.py:83` then
>    intersects those bare ids with the user's selection and `:210-223` removes both the
>    JSONL record and the prose. Version-blind: a learning promoted only into `@2` is
>    deleted from a user still on `@1`.
> 5. **Namespacing gives identity-disjointness, not semantic disjointness.** The contract
>    claims one-owner-per-`@author/domain` is what makes "namespacing is sufficient" true.
>    It is not: `@alice/builder-base` and `@bob/builder-base` are distinct keys, so both can
>    be selected, and their contradictory instructions land in one prompt with no defined
>    authority. Under single/org authorship this is inert — but it is exactly what the
>    contract is supposed to survive.
> 6. **Guide filenames are package-local in the manifest and global on disk.** `filtered_files`
>    keys by filename and `copy_filtered` writes to one `central/guides/` tree
>    (`assemble.py:142`, `:298`), so two packages contributing `setup.md` silently
>    overwrite each other. *(Medium.)*
>
> The review found **no contradiction** between decisions 2 and 3 in `DESIGN.md`, with a
> stated rationale: configurability does not make the day1 protocol generic.
>
> The reviewer also confirmed a defect in **today's shipped product**, not this contract —
> see `DESIGN.md` decision 4, which grew as a result.

### The root cause v1 got wrong

All six defects trace to one conflation: v1 made the identity unit `@author/domain@version`,
so **the package and the domain were the same concept.** Separate them and the defects
dissolve rather than needing individual patches.

- A **domain** is a classification facet that content carries. It already exists, already
  works, and `audience()`/`kept()` (`assemble.py:72-84`) already handle domainless universal
  content correctly. Do not touch it.
- A **package** is the authored unit that content ships in.

Content's *audience* stays `(tier, domains[])`. Content's *origin* is the package whose
manifest declares it. The two are orthogonal, and neither carries a version.

### 1. Identity — `package_id := @scope/name`, unversioned

- Both segments match `[a-z0-9]+(?:-[a-z0-9]+)*`. The built-in source is
  **`@agent-bios/core`**.
- **`package_id` carries no version and no domain.** A package may declare many domains.
- **Domains are package-local.** A domain's canonical identity is the pair
  `(package_id, domain)` — never a bare string compared globally. This is what makes
  namespacing real: two authors may both use `builder-base` without contention, so a domain
  id never becomes a globally squattable name.
- Content locators are **derived projections**, not stored strings: a bullet is
  `(package_id, "bullet", anchor)`, a guide `(package_id, "guide", filename)`. No new
  per-item id is introduced.
- `package_id` is immutable; a rename is a new identity requiring an explicit migration.
  Two manifests presenting the same `package_id` are fatal.
- A scope prevents accidental collision. It does **not** prove the author owns that scope —
  that would need an allocation authority, which C1 defers.

### 2. Manifest shape

An authored package manifest holds exactly `version`, `package_id`, `tiers`, `domains`,
`bullets`, `guides`.

- `version` is the **manifest-format** version, never a content release.
- `domains` keys and guide filenames are local to `package_id`.
- **Authored packages declare `domain`-tier content only.** `core`/`infra` — the tiers that
  land unconditionally — stay with the core manifest, because core is the engine and
  unconditional injection is an engine privilege. This is the reversible direction: allowing
  universal content in packages later is additive, while withdrawing it later is a migration.
- `hooks`, `agents`, and `scripts` are **invalid manifest fields for a package, and the
  composer has no code path that reads them.** Prose-only is enforced by absence of
  capability, not by a rule a reader must obey.
- Non-vacuity for a package is `len(bullets) + len(guides) > 0`. Individual sections and the
  domain registry may be empty — today's rule that no section may be empty
  (`check-domains.py:130-133`) is core-shaped and is precisely what made a conforming
  prose-only package unjudgeable.
- **Core's manifest is a distinct profile.** `config/domains.json` gains `package_id`
  and keeps its `hooks`/`agents`. It is the engine manifest, not a conforming package.

### 3. Composition contract

> **Status 2026-07-26 — specified, deliberately NOT built.** Identity (§1), the manifest
> field (§2), and the prune authorization (§4) are implemented and shipped, because those
> are the parts that would have forced a content migration later. The rules below are not,
> and building them now would mean **inventing an on-disk package format for packages that
> do not exist** — a per-package prose root, its guide tree, and its codex projection.
> C4 says include only what omitting would force a migration later, and the levers deferred
> heavy machinery to proven demand; a composer with no package to compose is exactly the
> inert code this repo treats as unbuilt. Build this when the first real second package
> exists, and let that package's actual shape decide the format rather than guessing it now.

- **Discovery is local (C3):** the composer takes the built-in core plus zero or more
  explicit local package roots. No registry is implied.
- **No version is ever persisted as a resolution input.** A selection names packages and
  domains; each `package_id` resolves to whatever manifest is currently supplied. A missing
  package is fatal rather than silently resolving to older content — there is no historical
  store, so a recorded version would be a promise the system cannot keep.
- **Selection state** grows a v2 form, `{"version":2,"packages":[{package_id, domains[]}]}`,
  where presence activates a package. **v1 stays valid and is normalized**: a bare-domain
  `{"version":1,"domains":[…]}` means those domains of `@agent-bios/core`
  (`assemble.py:310`), and the existing `--domains` path keeps writing v1 exactly. v2 is
  emitted only when an authored package participates.
- **Deterministic order:** core first, then ascending `package_id`, source order preserved
  within a package. This buys reproducible serialization for the parity gate — it is
  explicitly **not** semantic precedence.
- **Deploy paths are derived, not chosen.** Core output stays flat and unchanged; a
  package's guides deploy beneath a path the composer derives from the validated
  `package_id` and a basename-only key. An author cannot express a global path, so the
  filename collision is unreachable rather than forbidden. (Note: `copy_filtered`'s existing
  `rewrite` hook is a single `body.replace(*rewrite)` (`assemble.py:142-152`) and must be
  generalized for per-package reference rewriting.)
- **Fails closed, as today:** the gate must pass, the extracted-anchor post-condition must
  hold per package (`assemble.py:131-134`), and unknown domains die (`:274-276`). Structural
  failure leaves the previous deployed tree and selection authoritative.
- **The gate is parameterized,** taking an explicit manifest path and content root. The
  core-only rules (monolith bijection, whole-tree file coverage, router co-package, hook
  `source_guide`) stay core-only; package rules judge a package against its own root.

### 4. Prune authorization — the irreversible path

`migrate-learnings.py` deletes a user's personal learning, prose and JSONL both
(`:83`, `:210-223`). Promotion metadata is a *projection* of where a bullet landed; the
authoritative fact is whether the promoted content is actually in the user's deployed
corpus.

- **Metadata selects candidates. Presence in the user's composed corpus authorizes the
  deletion.** This removes the whole failure class, including the version skew v1 could not
  see, because the check is against reality rather than against a record that can drift.
- Promotions gain `package_id`, sourced from a `placed_package_id` on the placement record;
  `tier`/`domains` remain derived projections. **v1 records without `package_id` mean
  `@agent-bios/core`**, so today's single entry keeps deciding exactly as it does now.
- **Correction, 2026-07-26 (found while implementing):** promotions must also carry the
  **`anchor`**. The spec above named the authorizing check but not the locator it needs —
  `build-promotions` resolved `placed_anchor` and then discarded it, keeping only the
  derived audience, so the consumer had nothing to look for. Shipping the anchor keeps the
  locator alongside its projection instead of only the projection. A record without one
  cannot be verified and is therefore KEEP.
- **Any uncertainty is KEEP.** Unknown package, unsupported artifact version, malformed
  record, or missing selection evidence must never delete.

### Explicitly NOT in the contract

Registry, discovery, signing, trust scoring, permissions; precedence, override, exclusivity,
and semantic-conflict detection; package/content versions, ranges, lockfiles, rollback, and
`core_compat`; transitive dependencies and cross-package guide imports; per-package
distribution; separate author metadata; per-item ids and content hashes. Each is additive
later, keyed on a stable `package_id`, and none requires relocating prose.

`hooks`/`agents`/`scripts` in packages are **excluded, not deferred** (Lever 2).

### What the two independent drafts disagreed on, and how it resolved

Recorded because the disagreements are where the design was actually decided.

| Question | Claude draft | gpt-5.6-sol draft | Adopted |
|---|---|---|---|
| Domain scoping | global ids, duplicate declaration fatal | package-local `(package_id, domain)` | **gpt** — the fatal-duplicate rule made domain ids a globally contended resource, defeating the point of namespacing; it also gave a false sense that semantic conflict was solved |
| Prune authority | presence in the deployed corpus authorizes deletion | package-aware metadata match, KEEP on uncertainty | **both** — presence as the authority, gpt's normalization and KEEP-on-uncertainty around it, because the failure is irreversible |
| Universal content in packages | core-only | allowed, activated by package presence | **Claude** — restricting now is the reversible direction under C4; gpt's model is the natural relaxation |
| Composition order | unspecified | core first, then ascending `package_id` | **gpt** — determinism is needed by the parity gate |
| Forced changes | 7 files | 10, including the ledger row and the negative-control list | **gpt** — it caught `design/session-distill/ledger.json`'s single `placed_anchor` row (`L-01`, the only one of 83 entries), which the Claude draft missed |

Both drafts independently re-derived the `package.json` `files[]` packaging defect without
being told about it — see `DESIGN.md` decision 4.

### Implementation status

Stages 1, 2, and 4 landed on 2026-07-26 (`cc7f768`, `7af9a30`). The composition machinery
(§3) is deferred to the first real second package — see the status note there.

| File | Change | State |
|---|---|---|
| `config/domains.json` | add `package_id: "@agent-bios/core"`; `version` is the format version; content unchanged | **done** `cc7f768` |
| `scripts/check-domains.py:35` | take explicit manifest/content-root inputs; keep the no-arg core gate; package profile drops per-section and router non-vacuity (`:130-133`) for total-prose non-vacuity and omits hook/agent rules | validates `package_id`; parameterized profile deferred with §3 |
| `scripts/assemble.py:261`, `:298`, `:310` | gate and compose N package roots; reject duplicate/missing `package_id`; derive namespaced deploy paths for package guides; generalize the `rewrite` hook; keep the v1 selection writer when no package is active | deferred with §3 |
| `scripts/build-promotions.py:44` | resolve `(placed_package_id, placed_anchor)`; fail on zero or multiple matches; emit promotions v2 with `package_id`; legacy rows fall back to core | **done** `7af9a30` |
| `scripts/migrate-learnings.py:70`, `:205-223` | authorize deletion by presence in the composed corpus; package-aware candidate matching; every uncertainty is KEEP | **done** `7af9a30` |
| `design/session-distill/ledger.json` | add `placed_package_id: "@agent-bios/core"` to `L-01` — the only one of 83 entries carrying a `placed_anchor` | not needed — absent `placed_package_id` already means core |
| `config/promotions.json` | regenerate as v2; v1 stays accepted | **done** — v2 `7af9a30` |
| `scripts/install.sh:113` | forward package roots; pass v2 state to migration; leave the no-package branch (`:443`) unchanged | deferred with §3 |
| `scripts/gates/test-assemble.sh`, `scripts/gates/check-parity.sh` | negative controls: universal-only, guide-only, duplicate id, unknown package, same filename in different packages, unsupported version, package-aware promotion, fail-safe prune | prune + identity controls **done**; package controls deferred with §3 |
| `package.json` | ship the assembler and gate — see `DESIGN.md` decision 4(iii) | **done** `5db4ab9` |

## Related
`architecture-draft.html` (diagram) · `DESIGN.md` (adapter-split origin + dual-provider
review, absorbed) · memory `[[adapter-split]]`, `[[collection-loop]]`, `[[corpus-domain-packaging]]`.
