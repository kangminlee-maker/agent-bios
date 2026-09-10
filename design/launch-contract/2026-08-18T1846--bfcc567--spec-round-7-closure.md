---
created_at: 2026-08-18T18:46:00+09:00
head: bfcc567
kind: review
supersedes: 2026-08-18T0504--0008590--spec-round-7-findings.md
---

# Spec round 7 — closure, and the loop's conclusion

Three code violations and two specification defects, from
`…T0504--0008590--spec-round-7-findings.md` against the fourth revision of the spec
instrument (`…T0235--3328cb8--review-evidence-invariants.md`). Each code finding is closed
at the authority with a named, revert-proven control; both spec defects get exact
replacement sentences below — the spec is a dated record and is not edited here.

**This closure concludes the launcher review loop** (`D-20260818-76bea7`, stop): rounds
20–24 and spec rounds 1–7 closed every malfunction-grade finding, the violation trend under
the instrument ran 13→6→6→3→1→2→3 with severity falling below the product-malfunction bar,
and round 7's residue was one letter-level recomputation observable only under a mid-launch
config mutation plus two save-path over-refusals. The spec remains the instrument for any
future round; no round 8 is dispatched.

## 1. L7 (High) — the projections were computed once and CALLED twice

**The finding.** Rounds 5 and 6 gave the MCP and child registrations one producer each —
and `project_args` still called each producer twice: `run_contract` computed the value for
the contract text, then the argv builders computed it again. Both producers reread their
sources (`child_agent_registrations` the template files and `XDG_CACHE_HOME`,
`review_mcp_servers` PATH through `resolve_command`), so a change landing between the two
calls put one value in the contract and another in argv, under a tail that promises what is
described is what runs.

**Reproduced before the fix**, with the reviewer's own child probe (`sweep_template_reads=2`;
contract carrying the old description while argv registered `CHANGED … at …/9195…/sweep.toml`)
and its stable-read control, plus the MCP twin reconstructed from the record's outputs
(`resolver_calls=2 contract_first=True contract_second=False`, argv registering
`/resolved/second`). The reviewer's runpy-based resolver patch was re-seated on an
importlib-loaded module — `runpy.run_path` returns a copy of the namespace, so rebinding in
the returned dict reaches nothing, which the probe's own `resolver_calls=0` exposed before
it graded anything.

**Fixed at** `launch/agent-launch.py`, as the finding proposed: `project_args` computes
`review_mcp_servers(plan)` and (for a delegating codex launch)
`child_agent_registrations(plan)` ONCE at the start, and threads those exact values into
`run_contract`, the materializer (`codex_agent_configs` gained an optional
`registrations` parameter), and both backend argv builders. `run_contract` accepts both
projections as parameters and computes them only for contract-only callers, where no argv
exists beside the text to diverge from (`D-20260818-f0a2f7` closes making them required
everywhere).

After the fix both probes read one producer call (`sweep_template_reads=1`,
`resolver_calls=1`) and contract and argv agree on the same value under the very mutation
that split them; the controls are unchanged.

**Contract text did not move.** Same values, same call: `capture-review-goldens.py --check`
is green against the pre-change golden — 121 cells, zero movement, so no re-capture and no
inverse transformation were needed.

**Control** added to the check the finding names, `launcher_review_contract` — the temporal
twins its static cases could not be: every existing mutation edits the config between two
whole projections and holds the sources fixed within one. The new cases make the source
answer differently on every call *inside* one `project_args` and require the contract read
off argv to still reconcile with the registrations beside it:

| Assertion | What it catches |
| --- | --- |
| needle armed: two direct producer calls under the patch disagree | a patch that missed its seam, passing over nothing |
| child half (codex): every registered `(tier, description, config file)` is stated in the same call's contract while the sweep template's bytes shift per read | **L7's temporal letter**, child projection |
| MCP half (both hosts): every registered `(name, command)` is stated in the same call's contract while `resolve_command` shifts per call | **L7's temporal letter**, MCP projection — the two argv shapes are built separately |
| the contract is read off argv, not re-rendered | a reader handing the recomputation a fresh chance to agree with itself |
| `temporal_cases == 3` | any half going quiet |

`contract_cases` floor raised 9 → 12 to match.

**Revert-proven, per half.** With only the child threading reverted (contract and
materializer recomputing), the child case fails by name — the sweep row on its description
AND config file, and every sibling tier on its config file, because the directory digest
moves for the whole set — while both MCP cases stay quiet. With only the MCP threading
reverted, both hosts fail by name on the registered command while the child case stays
quiet. Restored, all green.

## 2. S1/S4 (High) — a TOML-writable whole arm was falsely refused at save

**The finding.** `hosts.codex = [1, 2]` is a profile the launcher accepts — only the
launching arm is parsed — and TOML spells it perfectly well as a value in the parent
`review.hosts` table, yet `render_preset_block` refused it: "the review arm at
'review.hosts.codex' is list, not a table". Reproduced with the reviewer's mutation
(`source_build=accepted`, `toml_writable=[1, 2]`, `save=LaunchError`) and table-arm control.

**Fixed at** `launch/agent-launch.py` `render_preset_block`: non-table arms are emitted as
values in an explicit `[presets.<name>.review.hosts]` parent table, before the table arms,
through the shared `_arm_scalar` serializer; table arms take the unchanged recursive path,
and active-arm validation is untouched (launching the value arm's own host still refuses at
load by name). A whole arm with no TOML spelling at all — reachable only by assembling the
config in memory — is refused naming `review.hosts.<host>`. The old whole-arm refusal is
deleted rather than kept dead: its message had become false.

After the fix the mutation reads `save=accepted reloaded=[1, 2]`, through the real
`save_preset` as well (lock, parse-before-replace, projection comparator; the codex arm is
skipped by S5's existing source-doesn't-build conditional). The control is unchanged.

**Control** added to `launcher_review_save` (control 1b3): an inactive whole arm authored
as a TOML value — array and scalar shapes, authored as real TOML text — saves through the
real writer and reloads verbatim, with a vacuity check that the authored value landed where
the case reads it; plus the complement, an unserializable whole arm refused naming
`review.hosts.codex` with the serializer's own "no form this writes back" needle.

**Revert-proven.** With the old refusal restored and the value emission removed, all three
cases fail by name: both writable shapes as "did not save … refusing it at Save makes an
accepted profile unsaveable", and the complement as "refused … without naming the entry",
because the old message is not the door this control asserts. Restored, green.

## 3. S4 (High) — a TOML-writable nested tier override was falsely refused

**The finding.** `tier_overrides.codex.workhorse = [1, 2]` — accepted at build (only the
active host's blocks are validated), spelled by TOML as a value in the parent host table,
refused at save. Reproduced with the reviewer's mutation and table-override control.

**Fixed at** `launch/agent-launch.py` `render_preset_block`: the whole `tier_overrides`
tree goes through the SAME recursive emitter the review arms use (`_emit_arm_table` from
the root), so a non-table node at any depth — a tier entry, or a whole host block — is
written as a value in its parent table, and an authored-empty host block survives as an
explicit empty table instead of vanishing. The active host's blocks arrive normalized from
`preset_from_plan`, so for them the emitter writes byte-identical output to the old loop;
a genuinely unwritable value is refused naming its full `tier_overrides.…` path.

**The interaction the fix exposed.** The FRONTIER normalizer's skip branches (`continue`
on a non-dict host block or `frontier` entry) were safe only because the renderer refused
those shapes — the comment said so in as many words. With the refusal gone, skipping would
have written the occupied node verbatim and silently dropped a non-default authored
`frontier_effort`: a NEW S4 violation manufactured by the fix. `preset_from_plan` now
refuses that combination by name — "authors frontier_effort=…, whose saved home is
tier_overrides.<host>.frontier.effort, and <entry> holds a non-table value the save carries
verbatim — it cannot write both" — and only AFTER default elision, because a default-valued
authoring writes no line and reloads faithfully (`D-20260818-7c02da`; the one case
`D-20260817-105da4` keeps a named refusal for: two authored values, one home).

**Controls**, in `preset_save`, the check the finding names. The two cases that asserted
the refusal — the finding's "control encoding the opposite of S4" — are now round-trip
checks, alongside new complements:

| Case | Asserts |
| --- | --- |
| scalar host block / array tier block | saves and reloads verbatim; the active host's rebuilt override survives beside it |
| empty host block | reloads as the authored `{}`, not dropped |
| unwritable host / tier block (`object()`) | refused naming `tier_overrides.claude` / `…claude.workhorse` with the serializer's "holds object" needle |
| occupied FRONTIER home, both spellings | refused naming both values, "cannot write both" |
| the door's two edges (default-valued / absent `frontier_effort`) | still save, carrying the non-table node verbatim |

**Revert-proven, per half.** With the per-tier `_table` loop restored, seven cases fail by
name — both writable depths, the empty-block drop, both unwritable needles (the old message
is not the new door's), and both frontier edges — while the occupied cases stay quiet,
because that door lives in `preset_from_plan`. With only the occupied door reverted to
skips, exactly the two occupied-spelling cases fail as silent drops while every edge stays
green. Restored, all green.

## Decisions

- `D-20260818-76bea7` (stop) — the loop concludes with this closure; no spec round 8.
- `D-20260818-f0a2f7` (design) — once-per-projection binds the pipeline `project_args`
  owns; contract-only callers keep a compute-when-absent default.
- `D-20260818-7c02da` (design) — non-table override nodes save verbatim; the occupied
  FRONTIER home is the refusal kept, placed after default elision.

## Spec amendments proposed

The spec file is a dated record and was not edited. Both defects are in the specification;
after this round's fixes the runtime is internally consistent on each.

### 1. S1/S4 vs S5 — buildability owed on a host the source never built

S1 requires raw inactive material to survive verbatim and S4 keeps every accepted
non-routed profile saveable, while S5's "every other launchable host is owed that the
preset still BUILDS there" is unsatisfiable for an arm like `hosts.codex = [1, 2]`: no
implementation can both preserve it verbatim and make the saved preset build on codex. The
runtime already scopes the owe (`save_preset` skips a host the SOURCE preset does not build
on), so this is a wording repair adopting the reviewer's minimal fix. Exact replacement for
the S5 sentence:

> Every other launchable host **on which the source preset builds** is owed that the saved
> preset still BUILDS there, plus S1's verbatim carry and S2's source-not-destination rule
> for the material written for it — a host arm the source never built is owed the carry
> alone, since a refusal the source already earns there is not the save's to repair; there
> is no second projection to hold any inactive host to, because a host-independent
> customization is supposed to move every host's projection (D-20260817-57c57c; spec
> round 1; spec round 7).

### 2. D8/S5 — "no temporary remains" cannot survive a failing cleanup

D8's "temp removed on failure" and S5's "a failure at or before the atomic replace leaves
… no temporary behind" state an unconditional guarantee the mechanism cannot give: deletion
cannot be guaranteed when the deletion operation itself persistently fails, as the
reviewer's bounded injection showed (`events=['write','replace','unlink']
temporary_exists=True` with the initiating `OSError` preserved). The recommended reading is
the reviewer's minimal fix — best-effort cleanup, preservation of the initiating failure,
disclosure of an unremovable leftover. Exact replacement for the D8 parenthetical:

> (dotted same-directory temp + `os.replace`; cleanup of the temporary on failure is
> best-effort — it may not mask the initiating failure, and a temporary the cleanup could
> not remove is disclosed by path rather than guaranteed absent; spec round 1; spec
> round 7)

Exact replacement for the §2 preamble's residue sentence:

> Their artifact-decidable residue is the POST-FAILURE state — no partial file, and no
> leftover temporary that a later run or reader would mistake for live state; when the
> cleanup itself fails, the residue is a disclosed temporary path, never a silent one —
> and that is what a control asserts.

Exact replacement for the S5 clause:

> a failure at or before the atomic replace leaves the old file intact and, when cleanup
> succeeds, no temporary behind — cleanup is best-effort, may not mask the initiating
> failure, and discloses a temporary it could not remove —

Adopting this is not free on the code side: today's `publish_atomically` preserves the
initiating failure against an `Exception`-class cleanup failure but discloses nothing, and
a `KeyboardInterrupt`/`SystemExit` raised DURING the cleanup still masks the initiating
failure. Under the amended sentences both become obligations with controls to write
(`launcher_receipt_adapters` and `preset_save_round_trips` currently inject replacement
failure only while cleanup succeeds). That work belongs to whoever adopts the amendment;
it is disclosed here so the proposal is priced, not smuggled.

## What the reverts taught

- **The temporal needle must prove itself armed.** Under the fix the mid-call mutation can
  never fire — the second read simply does not happen — so a broken patch and a correct fix
  look identical from the assertion alone. Two direct producer calls under the patch,
  required to disagree, are what tell them apart; the probe's own `resolver_calls=0` on the
  runpy seam is the instrument-bug this guard catches.
- **A fix can manufacture the violation one door over.** The renderer's refusal was the
  only thing making the frontier normalizer's skips safe; removing it faithfully per the
  finding would have converted an over-refusal into a silent drop. The revert of the
  occupied door alone — everything else fixed — fails exactly the two occupied cases as
  drops, which is the proof the door is load-bearing rather than defensive.
- **A shared digest fails a whole family by name.** The child-half revert fails not only
  the mutated sweep row but every sibling tier's config file, because the directory is a
  digest of the whole rendered set — the same mechanism `D-20260818-18a8be` recorded as the
  reason paths belong in the contract.

## Verification

| Check | Result |
| --- | --- |
| `check_parity.py` (62 checks, full, venv python) | exit 0 — `LAUNCH/BINDINGS OK` |
| `launcher_review_contract` with the fix | pass |
| …child threading reverted | FAIL by name (sweep description + all three config files); MCP cases quiet |
| …MCP threading reverted | FAIL by name ×2 (command, both hosts); child case quiet |
| `launcher_review_save` with the fix | pass |
| …whole-arm refusal restored | FAIL by name ×3 (array, scalar, unserializable-complement) |
| `preset_save` with the fix | pass |
| …per-tier table doors restored | FAIL by name ×7; occupied cases quiet |
| …occupied door reverted to skips | FAIL by name ×2 (both spellings); edges quiet |
| all reverts restored | pass |
| `capture-review-goldens.py --check` | 121 cells, 0 movement — contract text unchanged, no re-capture |
| `capture-review-goldens.py --self-test` | 10 controls each proven to fire |
| `check-surfaces.py` | 14 surfaces, 39 authority paths live |
| `check-ontology.py` | 38 entities, 49 edges, 9 kinds |
| `check-lexicon.py` | 342 files scanned, 14 tokens enforced, 9 concept homes held |
| `record-decision.py --check` | 106 records, ids content-bound |
| dry-run `--config launch/agent-launch.toml`, codex / claude | exit 0 / exit 0 |
| reviewer's four probes, mutation + control each | mutation behaves, control unchanged (§1–§3) |
