---
created_at: 2026-09-15T13:43:00+09:00
head: 35c75ca
kind: review
status: p00-accepted-coordinator-mode-no-product-implementation
plan: 2026-09-15T1026--35c75ca--development-plan.json
node: P00
run_id: p00-baseline-20260915T1321
decision: D-20260915-6ccd60
---

# P00 — brownfield baseline captured and present-state tests classified

This record continues Codex thread `01a09937-3670-7370-becd-d93c80ed2126`, whose last
turn completed at 2026-09-15 10:51 KST with the 10:26 design bundle and then stopped
on the weekly usage limit. Nothing was mid-flight; the first executable node of the
plan, P00, had not been started. This is that node, run under coordinator control by
a Claude Code session. No product node is implemented, no unattended runner is
qualified, and main's index was not written.

## Input and attribution

`main` sits at `35c75ca` with 147 modified, 27 deleted and 3,209 untracked paths in
its working tree. The tree is shared by three sessions (ledger `session` ids):

| Session | Work in the shared tree |
| --- | --- |
| Codex `01a09937` | corpus→Instructions rename integration, Team work-environment design bundles, purpose and development-plan gates |
| Codex `01a09abe` | FDE-UI research: `research/fde-ui/` (2,960 files), `output/` (29 files), ui-design guide |
| `01a09b87` | korean-writing guide |

The newest commit whose content the working tree already contains is
`a264457` (`feat/ui-design-instructions-20260914`, 2026-09-14 20:01 KST). It carries the
rename, `v0.19.1`, `v0.19.2` and the ui-design guide; `main` was never fast-forwarded.
Against `a264457` the working tree's residual is 11 modified files and 134 new files,
all from `01a09937`, plus the two foreign untracked trees. `package.json` in the working
tree still reads `0.19.0` while `a264457` reads `0.19.2`; the baseline carries the
working-tree value and records the drift rather than resolving it.

The session's reported "full umbrella fails on file tracking state" was an index
artifact, not a code defect: gates derive their subject set from `git ls-files`, so
the still-tracked deleted `test_corpus_*` files and the untracked `instructions_*`
modules made `fixture_support.copy_tracked_tree` and `check-package.sh --self-test`
fail by name. On a consistent index the umbrella passes (B05 below).

## Baseline

| Item | Value |
| --- | --- |
| Worktree | `/Users/kangmin/.local/share/agent-bios-workbench/p00-baseline-20260915/source` (detached) |
| Substrate | `a264457514d0a60153d8e77ded19636513e66e38` |
| Overlay | 11 modified + 134 new paths copied from main's working tree, staged by name in the worktree's own index |
| Excluded | `research/`, `output/` (2,989 untracked files of another session; not runtime, not tests) |
| Baseline tree | `7f3c1c29f1e71f805d14704ccf658068a2cff9ff` (`git write-tree`, 846 paths) |
| Verification | every overlaid path sha256-equal to main's copy; every other path blob-equal to the substrate; 0 mismatches |
| Manifest | `../baseline-manifest.json` (path, sha256, bytes, mode, origin) beside the worktree; summary in [p00-baseline-summary.json](2026-09-15T1343--35c75ca--p00-baseline-summary.json) |

Four paths untracked in main but tracked on the substrate differed; main's newer
copy won (two team-CRUD design notes, `docs/instructions.md`,
`docs/instructions-compatibility.md`). No symlinks were encountered.

## Present-state tests (B01–B05) in the baseline

Interpreter: the prepared venv `~/.local/share/agent-launch/venv` (Python 3.14.5,
Textual 8.2.8), the same one `gates/check-parity.sh` uses.

| Case | Command | Result |
| --- | --- | --- |
| B01 | `compose/test_instructions_compatibility.py` | 12 tests, OK, 0.3 s |
| B02 | `compose/test_instructions_app.py` | 23 tests, OK, 20.8 s |
| B03 | `compose/test_instructions_transactions.py` | 3 tests, OK, 6.3 s |
| B04 | `unittest discover -s compose -p 'test_instructions*.py'` | 523 tests, OK, 0 skips, 315 s |
| B05 | `bash gates/check-parity.sh` | exit 0, `PARITY OK`, 0 `FAIL` lines, 793 s |
| P00-contract-positive | `gates/check-development-plan.py` | 12 positive / 118 negative controls |
| P00-contract-negative | `gates/check-development-plan.py --self-test` | 3 positive / 53 negative controls |

Classification: these are the existing Instructions suites and the author umbrella.
They document starting behavior on the captured baseline; per the catalog's
`baseline_semantics` they are not target acceptance and no backward-compatibility
promise follows from them. The umbrella's wall time was 793 s on this machine, well
above the 267 s quoted in AGENTS.md; re-measure before quoting either figure.

## Run evidence

`/Users/kangmin/.local/share/agent-bios-workbench/p00-baseline-20260915/evidence/run.json`
binds profile P00 (digest of the catalog profile, seven bound cases across B01–B05,
adapter and fixture fingerprints) and one record for P00 (plan/node digests, coordinator
mode, `product_changes: []`, subject fingerprint of the baseline tree and manifest,
artifact `P00/result-evidence.json`, sha256 `41b5b345…0bd96cc`). Evaluated with the
dated checker:

```bash
python3 design/knowledge-and-history/2026-09-15T1026--35c75ca--check-development-plan.py \
  --run ~/.local/share/agent-bios-workbench/p00-baseline-20260915/evidence/run.json
```

Result: `accepted_nodes: ["P00"]`; every other node `missing result`; `terminal_accepted:
false` (exit 2, the expected nonterminal outcome). No node is dispatch-ready until P01
freezes case bindings; R0 then qualifies a runner before any unattended claim.

## Explicit gaps and owner decisions

- `main` was three commits behind `a264457` when the baseline was captured. On the owner's
  instruction later the same day, local `main` was moved to `origin/main` (`bb7b212`, the
  PR #1 merge whose tree equals `a264457`) with `git reset --mixed`, which touches no
  working-tree file; four committed files the tree lacked were restored from that commit.
  The baseline substrate and tree are unchanged, and the residual now shows as the 11
  modified files plus the new design files. Committing the residual remains the owner's call.
- `package.json` version drift (`0.19.0` in the tree, `0.19.2` on the substrate) is
  recorded, not resolved.
- The foreign FDE-UI trees are excluded by attribution, not by inspection of their contents.
- No runner is qualified; this evidence is coordinator-mode only and cannot support
  unattended dispatch.
