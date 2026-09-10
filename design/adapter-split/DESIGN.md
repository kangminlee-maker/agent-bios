# agent-bios ⁄ day1-agent-bios split — adapter design (BACKLOG)

Status: **DECIDED 2026-07-26. NOT implemented.** The initial draft's two load-bearing
choices (git-fork overlay; "day1 coupling is just two endpoints") were **overturned** by
cross-family review (Opus + codex/gpt-5.6-sol, both re-derived from code, strongly
convergent) on 2026-07-24; the four questions that review left open were settled in the
2026-07-26 decision session — see **Decisions** below. Ecosystem-level context and the
foundational contract these sit inside: `ECOSYSTEM-ARCHITECTURE.md`. This file is the
record: goal → verified facts → what the review overturned → the direction → the
decisions.

## Goal (user-decided 2026-07-23, unchanged)

Make **`agent-bios`** a general, self-contained instruction-layer product usable by
**individuals and third-party companies**, not coupled to day1's dashboard; put day1's
collection wiring in a thin overlay so:
- individual → `agent-bios`, corpus + launcher + `learn!` **local** capture, no org dep;
- third party → point the sink at their own endpoint;
- day1 → one turnkey package (`day1-agent-bios`), pre-configured for the day1 dashboard.

## Verified facts (2026-07-23/24)

- **agent-bios is NOT company-deployed** — only the author uses it; "~500" = the dashboard
  `collect-session` fleet + the agent-bios deploy TARGET. **⇒ no fleet to migrate; the
  author just re-installs. Splitting now is zero-legacy, ideal timing.** (unchanged)
- Capture is genuinely general: no token ⇒ upload cleanly `skipped`
  (`collect-learning.py:391-395`); the hook dir is dashboard-owned/read-only to us
  (`:289-290`). Launcher/corpus have no day1 *transport* coupling.
- **CORRECTED (was "two endpoints + one token"):** the shared upload transport encodes a
  **day1 protocol**, not a couple of config values — see Review §finding-6.

## Review outcome — dual-provider adversarial review (2026-07-23/24)

> Line numbers in this section are **as-of 2026-07-24** and some have since drifted; the
> findings themselves were re-verified on 2026-07-26 (see **Decisions**). Re-locate by
> symbol, not by line, before acting on any citation here.

Two independent frontier reviewers (Opus max, Claude family; gpt-5.6-sol xhigh, gpt
family) re-derived every load-bearing claim from code. **Both verdicts: needs rethink.**
Cross-family convergence ⇒ high confidence. Findings (union, evidence-anchored):

### Fork is the wrong mechanism (both, decisive)
- **F-a (reproduced):** `package.json` `name` must diverge (fork) while core bumps
  `version`+`releaseDate` **every release** in the *same 3-line hunk* → `git merge`
  conflicts on **every** upstream release. Proven with `git merge-file` (exit 1). The
  "conflict-free by construction" claim (old §Seam) is **false**. (`package.json:2-4`)
- **F-b (decisive, codex):** the shared installer's `update` for an npm install always
  prints `npm install -g **agent-bios**@latest && agent-bios install`
  (`install.sh:673`). A day1 **fork** user who runs `update` is swapped to **core** →
  upload silently disabled. The fork actively breaks day1's own update path. status/help/
  onboarding/README are also `agent-bios`-hardcoded.
- `git filter-repo` rewrites commit IDs ⇒ defeats "preserve history to merge upstream."
- **Both recommend an npm-dependency wrapper, not a fork:** `day1-agent-bios` = one day1
  preset file + a thin forwarding wrapper that `dependsOn` core and runs the core CLI with
  the day1 preset's absolute path (one user command preserved); bin stays `agent-bios`;
  core updates via one dependency-version bump, no merges.

### The sink is a day1 PROTOCOL, not "a few endpoints" (codex §6 — deepest)
Hardcoded in the *shared* transport: `X-Hook-Token` auth (`collect-learning.py:372/377`),
`learning_id` server-dedup assumption, 400/413 permanent-drop policy (`:362`), the exact
JSON schema/request shape, and a **single sink-agnostic upload watermark** (`:338`). So:
a third-party sink using Bearer auth or treating 400 as transient → learnings permanently
dropped; switching sink A→B never resends A's already-`uploaded` records; a non-dedup sink
gets duplicates on retry. "Generic sink by config" is a mirage. Opus M1 (the `X-Hook-Token`
header name is not even in the proposed config surface) is the tip of this.
**Two honest options:** (a) keep the sink day1-shaped, just **default-off + endpoint
configurable** (simple; matches reality — day1 is the only org); (b) define a real **sink
adapter contract** (`sink_id` + per-sink watermark, auth mode/header, idempotency,
retry/permanent-status policy, endpoint, backlog-resend-on-config-change) if arbitrary
third-party sinks are truly wanted (much bigger).

### Other converged fixes
- **`export_source` is inert / mis-models auth (drop it).** `ingest-learnings-export.py`
  reads file/stdin, does **zero HTTP** (`:230`); the dashboard export **rejects
  X-Hook-Token, allows only a session cookie** (`PHASE3-CURATION-DESIGN.md:209`); real
  export = admin downloads a file in the browser (`CURATION-INTAKE.md:10`). Keep intake as
  file/stdin; the overlay just documents "admin exports → hand the file to intake."
- **Config authority/lifecycle (Opus M4 + codex §7):** the deployment config must be
  **user-owned, never deployed, never `verify_match`'d** (like `presets.local.toml`,
  `install.sh:47`) — NOT shipped+verified like `profiles.toml` (`:460/:540`), which an
  update would clobber and then fail verify. Precedence: explicit `--deployment-config` >
  `~/.config/agent-bios/deployment.toml` (user-owned) > vendor preset (overlay-provided) >
  built-in disabled default.
- **Security — credential exfil footgun (Opus M3 + codex §3):** `urllib` default follows
  redirects and forwards custom headers cross-origin (301/302/303) → a redirected day1 URL
  leaks `X-Hook-Token`; an arbitrary `token_source` can read arbitrary local files; a
  typo/malicious second package widens supply-chain surface. This is an **authority-posture
  decision**. Fixes: HTTPS-only for any token-bearing POST; forbid or same-origin-only
  redirects; restrict token source to a named provider/user-config path (no project-local
  config); explicit `expanduser`; confirm endpoint scheme/host at install.
- **Redaction gap (codex §2):** `redact.py` doesn't fully handle `Authorization: Bearer …`
  (probe: partially unredacted, `redact.py:51`). Generalizing the sink widens the floor's
  blast radius. Handle bearer/basic/cookie/CLI-cred forms + per-pattern upload negative
  controls before treating redaction as a security guarantee.
- **Corpus/schema still carry day1 prose (Opus L1 + codex §9):** the `## Session Learning`
  global says learnings reach "**the org**" (`claude/CLAUDE.md:151`, mirrors); learning-flow
  frames org curation as the purpose (`:17`); the schema hardcodes dashboard + `X-Hook-Token`
  (`learning.schema.json:5`); fixtures carry day1 email. Contradicts "corpus zero day1
  coupling." Neutralize to "optional configured org sink"; move server contract + provenance
  fixtures to the overlay/private.

### Scope surprises that threaten the goal itself (codex, pre-existing — verify+address)
- **learn! capture may not run after an npm install (codex §1):** the guide runs
  `python3 scripts/collect-learning.py` (`learning-flow.md:78`) but the installer never
  deploys it to a PATH location (`install.sh:447`). Works from a clone (cwd=repo), **breaks
  for npm-only individuals/third parties.** Fix: add an `agent-bios learn` subcommand the
  corpus calls; test capture after an npm tarball install from an arbitrary cwd.
- **Curator pipeline is org-DATA-coupled, not just mechanism (codex §8):** `build-promotions`
  emits *this repo's* manifest and the installer deletes personal learnings using the
  package's `config/promotions.json`; a third party's curated learning isn't in core's
  manifest, and editing the package-internal manifest is overwritten on update. "Change the
  sink → own org loop" is incomplete. Separate generic engine from org-owned data
  (ledger/promotions/corpus-additions overlay-owned, or a `promotion_manifest_source` trust
  boundary), or restrict the third-party promise to one-way ingest.
- **Verification is clone/author-side only (Opus L3 + codex §10, L2):** self-tests inject a
  fake `post_fn` (skip real URL/header/`urlopen`/redirect/config-parser, `collect-learning.py:449`);
  `check-parity` skips conditionally; npm `files[]` omits `ingest-learnings-export.py` /
  `build-promotions.py` (`package.json:9-37`) so "curator pipeline ships in core" is false on
  npm. Needs real loopback + npm-tarball tests (see the reviewers' test lists).

## Revised direction (adopted 2026-07-26)

Single core `agent-bios` package; **no fork.**
1. **Parameterize the sink honestly** — default **off/local-only**; endpoint + token-source
   + `token_header` configurable; keep it day1-shaped (option (a)). Withdraw the
   "arbitrary third-party sink" promise rather than promoting the full protocol contract.
2. **Config = user-owned, never-deployed** (`~/.config/agent-bios/deployment.toml`) with the
   precedence above; ship only a disabled built-in default.
3. **Security**: HTTPS-only, no cross-origin redirect, restricted token source, expanduser.
4. **`agent-bios learn` subcommand** so capture works after an npm install from any cwd.
5. **Neutralize corpus prose**; move day1 server contract/fixtures to overlay/private.
6. **day1 turnkey = npm-dependency wrapper** (`day1-agent-bios` = day1 preset + thin
   wrapper depending on core; bin stays `agent-bios`; record the two distributions are
   mutually exclusive in installer state), **not a fork**.
7. **Real verification** per the reviewers' test lists.

## Decisions (2026-07-26)

Settled in the C-1/C-2 decision session, downstream of the two master levers recorded in
`ECOSYSTEM-ARCHITECTURE.md` (**single/org authorship · prose-only packages**).

1. **Distribution shape → npm-dependency wrapper.** `day1-agent-bios` = one day1 preset +
   a thin wrapper depending on core; bin stays `agent-bios`; core updates are a dependency
   bump, never a merge. **The fork is dead** — and note the reason is independent of the
   openness lever: `package.json` conflicts on every release were *reproduced*
   (`git merge-file`, exit 1, `package.json:2-4`), and the shared installer's `update`
   sends a fork user to core (`install.sh:680`, re-verified 2026-07-26), silently
   disabling their upload. Even a
   single-author world would hit both. Accepted cost: two distribution paths to keep in
   sync, and installer state must record that they are mutually exclusive.
2. **Sink scope → (a) day1-shaped, default-off, endpoint configurable.** The transport
   keeps day1's protocol (`X-Hook-Token`, `learning_id` dedup, the 400/413 permanent-drop
   policy, one sink-agnostic watermark) and the docs say so plainly instead of promising a
   generic sink. day1 remains the only org, so the adapter contract (b) would be machinery
   with no consumer. If a second sink ever appears, (b) is still open — but the honest
   documentation is what prevents someone from pointing a Bearer-auth server at it and
   silently losing learnings.
3. **Third-party scope → promise nothing for now.** Drop the "a third party can run their
   own curation loop" claim from the docs; the product goal narrows to *a general
   instruction-layer product an individual can run locally*. Rationale: the curator
   pipeline is org-**data**-coupled (`build-promotions` emits this repo's manifest; the
   installer prunes using the package's `promotions.json`), so the claim is not true today
   and writing an unkeepable promise costs more than dropping it. Neither the one-way
   ingest promise nor the full loop is being built.
4. **Pre-existing packaging gaps → fix both, as the next work item.** Re-verified against
   real files 2026-07-26 (the review's line numbers had drifted; the findings hold).
   - (i) **`learn!` capture is unreachable after an npm-only install.** The guide invokes
     `python3 scripts/collect-learning.py` as a **cwd-relative path**
     (`claude/guides/learning-flow.md:86`). The script *is* shipped (`package.json`
     `files[]` includes `scripts/collect-learning.py`) — the defect is reachability: the
     installer's deploy block puts `codex-run`, `codex-helm`, and `agent-launch` on
     `$BIN_DIR` (`install.sh:457-462`) and never deploys `collect-learning.py`. So capture
     works from a clone (cwd = repo) and silently fails from anywhere else. Fix with an
     `agent-bios learn` subcommand — `bin.agent-bios` already points at `scripts/install.sh`
     — with `agent-launch` as the proven deploy pattern; verify by capturing from an
     arbitrary cwd after a real tarball install.
   - (ii) **"The curator pipeline ships in core" is not a claim worth making true.**
     First read: `ingest-learnings-export.py` and `build-promotions.py` were absent from
     `package.json` `files[]`, so the claim was false on npm — and they were duly shipped
     in v0.9.5/v0.9.6. **Reversed 2026-07-26 after verifying the deployed artifact:**
     shipping them fixed the wrong end. Both read
     `design/session-distill/ledger.json` — *this repo's curation data*, which is not
     shipped and should not be — so on an npm install they die with `FileNotFoundError`
     on first use (reproduced against the installed package). The claim could only be made
     true by shipping the ledger itself. This is the 2026-07-24 review's
     "curator pipeline is org-DATA-coupled" finding reaching its conclusion, and it is
     what decision 3 already implies. **Resolution: the curator pipeline is an author-side
     tool that operates on a repo checkout.** The scripts are unshipped again and the
     claim is withdrawn rather than propped up.
     Note the gate boundary this exposed: `check-package.sh` asserts that everything the
     runtime *needs* is shipped, not that everything shipped *works* — these two are on no
     runtime path, so no gate was ever going to catch them.
   - (iii) **★ ENLARGED 2026-07-26 by cross-family review — packaged install is broken on
     npm, not merely incomplete.** `files[]` also omits **`scripts/assemble.py`**,
     **`scripts/check-domains.py`**, **`scripts/canary.sh`**, and **`claude/settings.json`**
     (all four verified absent from the array; all four present in the repo). Consequence
     on the real path: `packaged_mode()` is entered whenever `--domains` is passed or a
     `selection.json` exists (`install.sh:111`), and it runs
     `python3 "$REPO/scripts/assemble.py"` (`:117`, dispatched at `:443-445`) where
     `$REPO` is the *installed package directory* — a file that was never shipped. The
     assembler in turn shells out to the equally-missing `check-domains.py`
     (`assemble.py:261`), `install.sh:648` runs the missing `canary.sh`, and
     `merge_settings` reads the missing `claude/settings.json` (`assemble.py:302`) — that
     last one fails *soft*, defaulting to `{}` (`assemble.py:160`) and silently deploying
     without the central hook entries.
     **So `agent-bios onboard` — documented as "interactive domain selection + packaged
     install + activation canary" (`install.sh:689`) — cannot work for an npm user at
     all.** The entire corpus-domain-packaging feature is clone-only in practice. It was
     never caught because plain `agent-bios install` with no selection does not enter
     packaged mode, and all prior verification ran from the repo clone.

   All of these block the general-product goal regardless of every lever above. (i) and
   (ii) are small; (iii) is the one that makes a shipped feature non-functional, and it
   deserves a real tarball-install test rather than another clone-side check.

**Sequencing.** Decisions 1–3 are recorded direction, not queued work. The next
implementation item is decision 4, followed by the foundational contract in
`ECOSYSTEM-ARCHITECTURE.md`.

## Non-goals (unchanged)

- Web-serving / self-updating the collector from a server (rejected 2026-07-23 — re-introduces
  the server dependency a general product must shed; web-issuance stays each org's concern).
- Any change to the dashboard's own collector / provisioning.

## Superseded initial draft (2026-07-23, for history)

The first draft proposed: (Y) light parameterization of "two endpoints + one token" +
a **git-fork** `day1-agent-bios` whose only diff was a `config/deployment.toml` +
`package.json`, claimed **conflict-free by construction**. Both claims were overturned
(fork §F-a/F-b; sink-is-a-protocol §6; export_source inert; config authority; security).
Kept here only as the decision trail.
