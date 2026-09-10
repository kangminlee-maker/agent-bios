---
created_at: 2026-08-20T09:27:00+09:00
head: 788d0bf
kind: design
supersedes: (none — the build record for roadmap step 2)
---

# Step 2 landed: the endpoint contract is extracted, and zero egress is a gate

Roadmap step 2 (`design/open-sourcing/2026-08-19T1713`): endpoint contract
extraction, corpus operations only, plus the zero-egress config surface. Preceded
by the dual inventory (`2026-08-19T2042--788d0bf--endpoint-inventory.md`), built in
one session, held to nine criterion-declared review rounds.

## What shipped

- **`ENDPOINTS.md`** — the core-owned contract: `ingest-learning` extracted from
  the operating wire; `publish-corpus` / `fetch-corpus` defined over the assembler
  input set with npm as today's only realization, deliberately no new network
  machinery; `ingest-session` name reserved, home left to step 4. Gate-bound.
- **The agent-bios-owned transport slot** — `~/.config/agent-bios/{ingest-url,token}`,
  host-independent, same file-pair shape as the operating day1 hook dir (the wrapper
  carries that provider in step 3), winning over the legacy hook dir; a claimed but
  incomplete, empty, or untraversable slot fails loud and never falls back
  (D-20260819-e46585). Default: neither source exists — upload skipped, zero egress
  (D-20260819-5d1f15 scoped the claim to DATA egress; the venv pip fetch stays).
- **Two shipped-client defects found by the loop and fixed**: a followed `302`
  re-sent the POST as a bodyless GET and settled the record while delivering
  nothing (now: redirects refused, `3xx` = transient); a malformed gateway status
  line (`BadStatusLine`) crashed `learn!` instead of leaving the record pending
  (now: `http.client.HTTPException` joins the transient set).
- **`gates/check-endpoints.py`** — five legs: doc anchors (12, consumption-checked
  on comment-stripped code, field-bound to the Request/Response/Client budget/
  Payload bullet blocks of a fence-, comment-, and unclosed-marker-stripped doc);
  default-transport probe through the real resolver (instrument proven on a planted
  slot first) plus install.sh statics; hook registration refused unless the bare
  canonical `python3 central/hooks/<file>.py` shape, sources tripwire-scanned; URL
  scan over the full shipped set incl. npm force-includes (case-insensitive,
  extensioned, entry points, bin arrays), host-allowlisted and URL-capped
  exemptions each exercised; and the **wire leg** — 15 live assertions on a
  loopback server: request line/method/token/content-type, whole-record payloads
  per index, the settle matrix (413/400 permanent, 201/204 ok, 302 not followed,
  429 transient-stop over two records), per-status dispatch snapshots, budget
  defaults via `inspect.signature`, a stall probe proving the socket timeout
  reaches the wire, a raw-socket garbage probe, and the **real CLI dispatch**
  (`install.sh learn` on stdin — the fd-3 plumbing included). Self-test: positive
  control + **59 planted violations failing by name**. Wired into `check-parity.sh`.
- **Umbrella guard hardened** — leg subjects tested with each leg's OWN predicate;
  the COUNT grammar accepts bracket/double-bracket/`test` forms, any-case
  predicates, and quoted paths while the PARSE stays strict, so an unknown guard
  form diverges loudly (directory-squat, test-form, and quoted-path probes).
- **Install-scenario assertions** (`gates/test-install-guides.sh` I1): after a real
  default install, the slot directory is absent outright, both host homes resolve
  the exact no-transport reason, and the installed hook registration equals the
  template structurally.
- `learn/collect-learning.py` self-test grew 16 → 26 checks, the load-bearing ones
  splice-proven against the exact reverted defect (9 manual proofs: the 5-check
  old-resolver splice, empty-token, tuple-reversal, limit flip, or-branch drop,
  budget reorder, plus the three umbrella-guard probes).
- Lexicon: 12th concept **endpoint contract**; learning-flow guide's stale
  "Transport lands in Phase 2" corrected in all four trees; module docstring
  updated to the slot-first resolution; AGENTS.md and IMPLEMENTATION_MAP rows.

## The review loop (criterion: AI harness, gpt-5.6-sol @ max, schema route)

86 findings over nine rounds — 80 fixed, 5 declared non-defects, 1 disclosed.

| Round | Subject | Findings | Disposition |
| --- | --- | --- | --- |
| 1 | full staged diff | 11 | all confirmed real, all fixed |
| 2 | fix delta | 14 | all fixed — incl. a real always-FAIL bug in the new scenario probe (detected_miss) |
| 3 | second fix delta | 13 | one recurring root cause (static substring checks are evadable) **class-killed** by the wire leg + canonical-shape refusal; 4 mechanical fixes; 1 regression |
| 4 | third fix delta | 15 | counts refusing to converge → the criterion-guide diagnosis: the defect lived in the UNDECLARED THREAT MODEL. 11 accident-plausible fixed; 4 adversarial in-repo constructions declared non-defects (D-20260819-67c00a) |
| 5 | fourth, threat model declared | 7 | converging; all fixed (whole-record payload, transient-stop, stall probe, backreferenced fences, case-insensitive force-includes, guard-form divergence, zero-send budget) |
| 6 | fifth | 8 | all fixed (content-type/2xx anchors, column-0 bullet, entry-point subjects, env-var tripwire, both legacy-url needles, per-index payloads, live 400, any-case predicates) |
| 7 | sixth | 7 | **shipped defect #1** (302 settle-without-delivery) + field-bound anchors, unclosed comments, bin control, 0.45 s stall bar, quoted guards |
| 8 | seventh (planned close) | 7 | **shipped defect #2** (BadStatusLine crash) + the REAL CLI dispatch probe, unclosed fences, bin arrays; 1 declared (prose negation semantics is review's, not a decidable gate's), 1 disclosed (DNS sits outside the socket timeout — doc) |
| 9 | eighth (user-requested final sweep) | 4 | all fixed: the CLI probe now runs `install.sh learn` itself (fd-3 plumbing, m59), untraversable slot dir fails loud, `[[` guard form diverges, module docstring de-staled |

Every round: `--compile-criterion` record line in the packet, `codex exec -s
read-only --ephemeral --output-schema`, `--check-findings` fold, fresh context per
round. The recipe's claim held again: the round-on-the-fix-delta caught
control-quality defects every time it ran, including two crashes of the gate
itself by its own mutations.

## Deliberately accepted residuals (disclosed, not defects)

- Deliberate in-repo adversarial evasion is out of the gate's threat model
  (D-20260819-67c00a): an author with commit access can disable the gate itself.
- The egress token scan on hook sources and the install.sh static needles are
  tripwires; the enforcement is the canonical-shape refusal, the scenario's
  directory-absence assertion, and review of the one shipped hook.
- Prose negation next to an anchored token is review's territory — a naive
  detector false-fires on the Response field's own "Redirects are not followed".
- The venv pip fetch on install is dependency provisioning, outside the
  data-egress scope (D-20260819-5d1f15). DNS resolution sits outside the socket
  timeout (documented in the Client budget field).

## Verification inventory at close

check-endpoints + self-test (59 controls), collect-learning self-test (26),
lexicon, ontology, package, hygiene, surfaces, domains all green; install
scenarios and the full parity umbrella run at commit. Stale docs found en route
are queued in the inventory record §6 (register-hooks.py callerless-shipped,
SURFACES/IMPLEMENTATION register-hooks claims, AGENTS.md "five files", dashboard
comment paths) — out of step-2 scope.
