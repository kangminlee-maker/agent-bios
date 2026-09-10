---
created_at: 2026-09-07T21:09:33+09:00
head: ed5b00f
kind: review
supersedes: null
---

# Astra cross-validation: corpus management under session-scoped activation

## Goal

Decide whether the user-managed corpus architecture remains sound after the
newer “install privately; activate per session” direction, and state the exact
design corrections needed before implementation. This is a pre-implementation
review; do not edit files.

## Required user outcomes

- Every agent-bios-managed corpus item is reviewable, editable, and removable.
- The TUI reviews corpus as wiki-like documents; an activated agent session can
  inspect and manage it through a skill.
- Users can create corpus content.
- Editing covers content and consumption surface.
- Every installed item can be restored individually.
- One command resets agent-bios settings to the installed state.

The newer direction adds these constraints:

- A clean installation stores corpus privately and leaves native global
  `AGENTS.md`, `CLAUDE.md`, skill discovery, hooks, and shell commands inactive.
- Plain CLI and Software Engineer / Vanilla carry no automatic agent-bios corpus.
- Only an explicitly activated launch receives the selected corpus and session
  registrations.
- Resume retains the session's pinned immutable corpus.

## Review target

Read both documents in full as one design bundle:

1. `design/corpus-management/2026-09-04T2321--17862b3--proposed-design.md`
   (`sha256 a84293da85e584752dd0845f32dc5c4fcce3dadf3d8977f3734c61a55cd2718b`)
2. `design/session-scoped-corpus/2026-09-07T1818--ed5b00f--proposed-design.md`
   (`sha256 d51e16b24ff7871502976bb0bd7f60f4642ca9606f6078f89828ad233e903561`)

The second explicitly supersedes the first document's always-installed
management-skill and global-realization assumptions, while retaining the
baseline/personal-overlay direction. Treat that statement as a hypothesis to
verify, not the answer. Treat the session-scoped document as the current primary
direction and the corpus-management document as the historical comparator whose
surviving contracts must be identified.

Review against the current working tree at `main@ed5b00f`, including its dirty
changes. Prioritize the real consumers and writers:

- `compose/domains.json`, `compose/assemble.py`, `compose/check-domains.py`,
  `compose/corpus-state.py`, `compose/pkgid.py`
- `install.sh`
- `launch/agent-launch.py`, `launch/agent-launch.toml`
- `launch/agent-launch.zsh`
- `learn/collect-learning.py`, `learn/migrate-learnings.py`,
  `learn/learning.schema.json`
- `SURFACES.md`, `ENDPOINTS.md`, `README.md`
- `design/session-scoped-corpus/2026-09-07T1818--ed5b00f--blind-packet.md`
- `design/session-scoped-corpus/2026-09-07T1818--ed5b00f--loader-probe.json`
- the `D-20260907-fe9379` row in `decisions/decisions.jsonl`

The current dirty launcher changes improve help text and bind Astra; they do not
implement the session-scoped proposal. Do not treat missing implementation as a
design defect.

For independence, do not read earlier review reports or model drafts under
`design/corpus-management/` or `design/session-scoped-corpus/`; only the two
target designs, the session-scoped blind packet and deterministic loader probe,
the named decision row, and actual source/evidence files above are in the review
boundary.

## Criterion

- **Observer:** the user operating Corpus Studio, an activated session skill,
  Vanilla, update/restore/reset, and resume; plus the maintainer who must
  implement the contract without inventing policy.
- **Defect:** a design choice or omission that makes a required workflow
  impossible, ambiguous, lossy, or inconsistent with an actual writer/consumer.
- **Classes:** `behavioral_design_defect` (stop-relevant), `verification_gap`,
  `non_defect`.
- **Evidence:** each material finding states starting state, proposed branch,
  observable wrong result, tight anchors in a target design, and source anchors
  when the cause depends on current behavior.
- **Non-defects:** implementation is absent; exact module/class names; explicit
  non-goals such as remote registry/signing; a host mechanism that is labeled
  unverified and kept disabled until probed.
- **Stop:** zero material design defects across the scenarios below.
- **Misclassification cost:** false negatives dominate because identity,
  recovery, session pinning, and ownership are retrofit-hard. Do not inflate
  verification gaps into defects.

Boundary goldens:

- An always-discovered management skill under a clean install violates the new
  Vanilla/no-global-corpus contract.
- A standalone CLI/TUI management entry can remain installed without violating
  that contract when it injects no content into ordinary sessions.
- Lack of a universal atomic host pointer is not itself a defect if publication
  cannot report success over a split state and recovery is journaled.
- Native skill registration being unproven is a verification gap only if the
  required in-session skill workflow has another explicitly valid realization;
  otherwise it is a design defect.

## Scenarios

1. Fresh install → plain CLI/Vanilla → no agent-bios content or registration.
2. Open Corpus Studio before any activated session; inspect/create/edit safely.
3. Start an activated session; its selected wiki/skill procedures are reachable,
   including the management skill promised by the user outcome.
4. Run active and Vanilla sessions concurrently; neither mutates shared global
   files to switch modes.
5. Edit/move/remove/restore global rules, shared guide/router edges, multi-file
   skills, hook prose, agent bodies, and personal learnings without orphaning a
   carrier or changing stable identity.
6. Update with user overlays: upstream-only, user-only, disjoint, same-field,
   upstream deletion, invalidated surface.
7. Learning capture/edit/upload/promotion/reset across the separate Claude and
   Codex authorities and any shared reader files.
8. Package create identity, per-session package/domain selection, immutable
   baseline defaults, rollback, and resume pinning.
9. Crash/concurrency around install, activate, learn, edit, remove, reset,
   rollback, and resume; no success over split state.
10. Uninstall/reinstall, permanent local purge versus remote retention, manual
    user text, secrets, and foreign files.
11. Feature-off migration: existing globally installed corpus is cleaned only by
    an explicit recoverable migration, while a new install never creates it.
12. TUI, non-TTY CLI, and session skill use one canonical manager/validator,
    without making the management skill a self-removable bootstrap dependency.

## Output

Return a bounded report:

1. `verdict: pass | revise | reject` and material defect count.
2. Material findings ordered by severity with class, confidence, target/source
   anchors, failure path, and smallest design correction.
3. A compatibility table: which first-design components survive unchanged,
   survive only after adaptation, or are superseded by session scoping.
4. A decision on the management experience: how standalone TUI/CLI and the
   activated-session skill coexist without violating Vanilla.
5. A premise table (`confirmed | falsified | proposed`) and explicit coverage of
   all 12 scenarios.
6. Rejected/non-defect observations and the exact conditions that must be proved
   before implementation starts.

Stop after the review. Do not write a replacement design and do not modify the
repository.
