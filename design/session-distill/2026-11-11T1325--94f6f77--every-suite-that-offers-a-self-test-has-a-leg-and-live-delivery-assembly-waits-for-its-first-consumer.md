---
created_at: 2026-11-11T13:25:00+09:00
head: 94f6f77
kind: design
supersedes: null
---

# Every suite that offers a self-test has a leg, and live delivery assembly waits for its first consumer

WP-10, commit W5: the lead's four points before X round 1. Decisions D-20261111-a58533 (the exclusion) and
D-20261111-2506f9 (the rename and the coverage gate).

## Named exclusion: live delivery assembly (lead, 2026-11-11)

What is excluded: assembling design §6.3's delivery evidence from live records. That means building, for each
formed candidate's events and each retrieved unit, the session evidence that `runlib/delivery_evidence.py`'s
`delivery()` takes. Its sources are the inventory's pins, selections, session-injection and native events, and the
bytes that a session's tool calls read back from the immutable copies.

| Field | Value |
| --- | --- |
| Excluded from | WP-10 |
| Owner | the package that first applies `derive.unit_outcome` to live records: WP-12 by the plan's §6.4 placement, confirmed or moved at the WP-11 brief |
| Why | WP-10's five done-whens need the §6.3 code and its O3 verdicts over golden fixtures, and S5 live over WP-09's output; none needs live assembly. The first live consumer of a delivery state is the derivation over the judges' answers, after S6 |
| What WP-10 holds | the §6.3 evidence code and its table, fixtures and O3 verdicts (W2); S5 over C2 (W3, W4), which writes no delivery state |
| What the owner finds | WP-07's inventory already records pins, selections, events, occurrences and the events in force per segment. A guide's unit read still needs the bytes returned before the decision, read from transcript tool calls and results on both hosts |
| Revisit when | the WP-11 brief places the first live application of `derive.unit_outcome` in WP-11 or earlier, or a WP-10 review finds that S5 must carry delivery states for S6's packets |

## The rename

`runlib/delivery.py` is now `runlib/delivery_evidence.py`, so the plan's WP-21 `runlib/delivery.py` and
`delivery.json` (S11 delivery verification) keep their names. The rename moves with it: the module's own usage lines
and suite prefix, the comment of `tables/delivery_evidence.json`, the comment of the frozen fixtures, the umbrella
leg, and control-audit's subject. No module imports it. Dated records written before today keep the old name, because
they describe the tree they were true at.

## The coverage gate

`gates/check-self-test-legs.py` decides which files are subjects from the syntax tree: every Python file under
`session-distill/` whose argv handling accepts `--self-test`. That is either an argparse registration, or a comparison
holding the flag (`sys.argv[1:] == ["--self-test"]`, `"--self-test" not in sys.argv[1:]`,
`sys.argv[1] == "--self-test"`). Each subject must have a `python3 [flags] <path> --self-test` leg in
`gates/check-parity.sh`. The failures are named:

- SELF_TEST_UNLEGGED: a subject with no leg;
- SELF_TEST_UNPARSED: a file the syntax tree cannot be read from;
- SUBJECTS_EMPTY: no subject at all.

`session-distill/out/` is excluded, with its reason: it holds pipeline snapshots. The umbrella runs the gate and its
self-test. The self-test plants trees, positive control first. Its negative controls cover:

- a self-testing module without a leg;
- an argparse route whose leg is gone;
- a prose-only mention, which is no subject;
- a snapshot that only the exclusion keeps out;
- an empty subject set;
- an unparsable file.

Two points about how the subjects are decided:

- **control-audit's pattern was not reused.** `gates/control-audit.py` has its own pattern, `SELF_TEST_DECL`. Over
  this tree it finds 9 files where the syntax tree finds 37, because it misses the `not in sys.argv[1:]` form. That
  tool belongs to the lead, so the defect is reported, not fixed.
- **Legs added.** `runlib/declare.py` now has a direct leg. The driver's `declare --self-test` leg already ran the
  same suite; the direct leg costs under a second and keeps the rule a single comparison. `plain-asks.py` has a leg.
  `runlib/entry.py` gets none: it names the flag only in prose, offers no such route, and a leg would pass about
  nothing. That correction is to 012ca20's report, whose text search named it.

## The S5 self-test's child run

dispatch's SCRIPT_RUNS row added in W3, verbatim:

```
{"site": "session-distill/runlib/stage_retrieve.py", "path": "session-distill/distill.py",
 "reason": "S5's self-test runs the driver's `retrieve` command as a child over a golden run through S4 it made, so the "
           "command a person runs is held as a process runs it (WP-10 commit W3); S5 makes no call and starts no model"},
```

What actually runs: `subprocess.run([sys.executable, "-I", str(HERE / "distill.py"), "retrieve", "--run-id", <name>,
"--out", <parent>])`. Here `HERE` is `pathlib.Path(__file__).resolve().parents[1]`, the module's own `session-distill/`.
So the child is the repository-path driver. `--self-test` is never handed to it. Only its inputs, a golden run made by
the self-test, live in a temporary directory. Nothing runs from a scratch copy, and nothing is re-entered through
`runpy`.

## Measured

| What | Result |
| --- | --- |
| check-self-test-legs | 37 subjects, each with a leg; its self-test 7 controls, OK |
| Its revert rows (`work/impl/wp10/pt-w5-gate.py`) | the baseline passes; 7 rows caught, none missed |
| A copy of the tree with plain-asks' leg removed | `SELF_TEST_UNLEGGED session-distill/plain-asks.py`, exit 1 |
| delivery_evidence self-test | 55 controls, OK (the renamed module, its bytes unchanged but for its name) |
| Self-tests | every session-distill module with a self-test: 38, 0 not rc=0 |
