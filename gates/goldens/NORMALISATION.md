# Review-matrix goldens — what is captured, and what was normalised away

Produced by `gates/capture-review-goldens.py`. Stage 1 of
`design/reviewer-registry/DESIGN.md` §5: the characterisation every later stage is
checked against.

`review-matrix.json` is a **control, not a report.** Stage 2's exit condition is
byte-identity against it after path normalisation, so the normalisation rules below
are part of the control: loosening one silently weakens every later stage. Change
them only with a stated reason, and re-state why the loosened rule still fails when
the launcher's behaviour changes.

## The matrix

64 legacy cells = 4 review setups × 2 hosts × 2 review families × 2 opposite-CLI
states × delegation on/off. Cell id:

```
<host>/<setup>/<family>/cli-<present|absent>/deleg-<on|off>
```

Axis order is fixed in the script; it determines the id, which is the golden's key.

**The absence axis removes the OPPOSITE host's CLI, not a tool.** Both shipped
review capabilities are `${backend}`, so a reviewer is absent exactly when a host
CLI is — and the only CLI a cell can lose without making the MAIN unlaunchable
(which would break the two-route agreement control) is the opposite host's. A main
missing its own CLI is a different assertion, pinned by the composable
`backend-absent`/`codex-exec-absent` scenarios.

**Absence is produced by pointing the backend command at a name that cannot
resolve — never by uninstalling anything.** The authoring machine has every host
CLI installed and is therefore not representative of a general user; a matrix
without absent cells would characterise one machine rather than the launcher.

## The fixture

The capture must not encode the author's install, and must not fake away the very
thing under test:

- **One backend per host** (`backend-codex`, `backend-claude`), never a shared fake.
  Aliasing them made "dispatched the opposite family" and "dispatched my own family
  again" the same recorded argv — so a cross-family regression, the single property
  this design exists to guarantee, stayed byte-identical across every cell.
- **A fixture `CODEX_HOME`**, set on the process so *both* observation routes see it
  (the module route reads `os.environ` directly; passing it only to the subprocess
  left half the capture reading the real install). It contains what `install.sh`
  deploys: `bin/codex-run`, `bin/codex-helm`, and
  `agents/{frontier,workhorse,sweep}.toml`.
- **Agent templates copied from `codex/agents/`**, not invented. The launcher rejects
  a template without a `description`, and empty ones turned 48 cells into error
  records. Sourcing them from the repository also means a template edit moves the
  golden, which is coverage rather than fragility.
- `XDG_CACHE_HOME` is redirected into the temp directory and
  `AGENT_LAUNCH_VERSION_FILE` points at a fixture pinned to `9.9.9` / `2026-01-02`,
  so a real release never moves the golden.

## Two observation routes per cell

| Route | What it proves | Source |
|---|---|---|
| `module` | the resolver's decision — `effective_review()` → effective / dropped / floor, or the `LaunchError` | direct import of `launch/agent-launch.py` |
| `projection` | what the backend would actually receive — normalised argv plus the injected contract | real dispatch stopped at `--dry-run` |

Both run against the same synthetic `[presets.golden]` preset, so the two routes
describe one configuration rather than two.

`module` also records `resolved_family`. `build_plan` silently forces
`review_family = "same"` when the opposite host or backend is missing; recording the
resolved value keeps that downgrade visible instead of letting it hide inside a cell
that merely looks same-family.

The contract is located **by its `LaunchPlan:` prefix, never by argv index** — codex
receives it inside a `-c developer_instructions=…` assignment and claude as the value
after `--append-system-prompt`, and the index moves whenever argv changes. It is
replaced **in place** by a `<CONTRACT>` token that **keeps whatever prefix preceded
it**, and stored separately. Removing the element discarded its position and
multiplicity; replacing the whole element additionally erased codex's
`developer_instructions="…"` envelope, so changing that config key left the golden
identical.

## Normalisation rules

Applied to every argv element, contract, and stderr string, longest literal first
(so a path nested inside another is not half-substituted):

| Literal | Token |
|---|---|
| the per-run temp directory (and its `resolve()`d form) | `<TMP>` |
| the repository root | `<REPO>` |
| `$AGENT_LAUNCH_VENV`, else `~/.local/share/agent-launch/venv` | `<VENV>` |
| the user's home directory | `<HOME>` |

Everything else is captured verbatim. In particular model ids, efforts, policy
flags, and route names are **not** normalised — those are the behaviour under test.

## Controls (all run on every capture; the capture fails if any fails)

1. **Real subject count.** 192 cells, non-zero. An empty or short matrix passes
   vacuously, so it is rejected rather than reported.
2. **Every axis is load-bearing.** For each axis there must exist a pair of cells
   differing only along it whose goldens differ. An axis that changes nothing means
   the harness is wrong — not that the launcher is consistent.
3. **The two routes agree per cell** on whether the plan resolves. They agreed on all
   96 cells before the `CODEX_HOME` fixture existed; a broken fixture then made 48
   cells fail in the dispatch while the resolver still said they were fine, and
   controls 1–2 stayed green because both only look at shape, never at health.
4. **The contract keeps its invocation envelope.** At least one cell must retain a
   prefix before the token. The token once replaced the whole argv element, which
   erased codex's `developer_instructions="…"` wrapper.

11. **No environment-state notice in any stderr.** The launcher's session-distill
   nudge fires on how many sessions the *operator* has accumulated, read through
   `Path.home()` rather than the pinned homes, so on 2026-08-27 — after a benchmark's
   few hundred `claude -p` dispatches crossed the 250 threshold — every cell's stderr
   gained a line and the golden diverged with no routing change at all. The capture now
   pins `AGENT_BIOS_SESSION_DISTILL_STATE` into the fixture (a missing file is "no
   nudge"), and this control fails the capture if the nudge text reaches any cell on
   either route. Its self-test mutation plants the nudge into one cell.

Each was checked against a deliberately broken capture and observed to fail:
disabling the `family` axis fails control 2 and names it; emptying the agent
templates fails control 3 with 48 disagreeing cells; replacing the whole argv element
fails control 4. A control that has never been seen to fail is not evidence.

The matrix's discrimination was also proven end to end: mutating `build_plan` to take
`review_backend` from the launching host instead of the opposite one makes `--check`
exit 1, and restoring it returns to 0.

## Known limits

Stated rather than fixed, so a later reader does not mistake a passing control for a
stronger claim than it makes:

- Controls 1–4 check the matrix's **shape and health**, not that every assertion
  inside a cell is maximally strong. A cross-family review round found further
  mutations that individual controls still admit — for example control 1 checks the
  cell count but not that the ids are exactly the Cartesian product, and control 4
  needs only one enveloped cell rather than all of them. Closing that class is
  unbounded (every control can be made stronger), so it was deliberately stopped
  here rather than chased.
- 22 of the 192 cells record a failure rather than argv. Those are real launcher
  rejections — control 3 confirms both routes agree on them — not harness breakage.

## Module route (added 2026-07-27)

The module route records `LaunchError` text, and a composable error may quote the profile or
the user-registry path. Those strings go through the same rules as the projection route.
Until a composable error first carried a path, only the projection route normalised — and the
golden differed from itself between runs, which `--check` caught immediately after a capture.

## Composable cells (added 2026-07-27)

Composable scenarios are enumerated, not a product: their failure branches are not axes, and a
cartesian product over them would be mostly unreachable combinations. Each scenario declares its
`outcome`, and control 6 asserts the observed result matches — so a failure branch that quietly
starts succeeding is a gate failure rather than a re-baselined golden.
