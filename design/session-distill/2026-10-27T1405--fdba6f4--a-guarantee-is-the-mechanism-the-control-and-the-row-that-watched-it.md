---
created_at: 2026-10-27T14:05:00+09:00
head: fdba6f4
kind: design
supersedes:
  - 2026-10-26T1402--b65371c--an-instrument-that-answers-for-a-guarantee-is-part-of-the-guarantee.md
  - 2026-10-24T0757--2018a38--a-control-that-passes-because-the-child-died-is-not-watching-the-fix.md
  - 2026-10-24T0308--2018a38--a-guarantee-is-the-weakest-mechanism-under-it.md
---

# A guarantee is the weakest mechanism under it, the control that fails when that alone is reverted, and the row that watched it fail

The 1402 record ended by naming the record that would have to be written: "the record that restates,
for this tree, whatever of them is still true is written after S7, at the end of the round." This is
that record. It restates the guarantees of 0308, 0757 and 1402 as they hold at `fdba6f4`, names what
in them is no longer true, and gives each residual its reason and its revive condition.

All three are listed under `supersedes` because this tree made a statement of each false — not only
1402's. 0308 §1 and 0757 §7 both state, as scope, that the other `runlib` suites "still print
directly"; S8c routed their collected-failure publication through `runlib/entry.py` and gave
`runlib/stop.py` an import of it on its suite's path. 0757 §3's account of the child bound is
carried forward here with a part it did not have. 1402 §1's "links read rather than followed" was a
control that could not fail until S8e.

**What this record is for.** A guarantee here is not a sentence about behaviour. It is the weakest
mechanism the behaviour rests on, plus the control that fails by name when that mechanism alone is
reverted, plus the revert row that observed it. Every row below is in `work/impl/r9-revert.py`, 68
rows over this tree, and every one of them was run: `R9 END pass=67 earlier-layer=1 mismatch=0
silent=0 not-applicable=0 ambiguous=0 skipped-unsafe=0 harness=0 rows=68 secs=6358`.

**What r7, r8 and r9 established, and why the definition above is the subject.** A verdict names
what the run saw, not why. r7 returned SEVEN rows as SILENT — no `[FAIL]` line at all — and those
seven had four different causes:

* **No control at all**, three rows: D1, G1, R17b. S8a wrote one for each.
* **A control that asked nothing**, two rows: D6, which a helper's signature made vacuous (class 1
  below), and G4, an empty `all()` over a subject the fixture never built (class 2).
* **An unfaithful revert whose suite then ABORTED**, one row: D3. The mutation removed the type test
  as well as the refusal, so an `ast.Name` reached a `.value` and the suite died before any control
  ran — and a collected report is lost on abort (class 3), which is what turned a broken mutation
  into silence.
* **A refusal by an earlier layer, which also aborts**, one row: R12. S1's emission table refuses the
  unhashed carrier id before the row's own control is reached. It read as silence because the harness
  had no verdict for it: EARLIER-LAYER was added in S8b, and a refusal that aborts the suite leaves no
  `[FAIL]` line for the PASS rule to see.

r7 also returned seven MISMATCH rows, and R19 was one of them rather than a silence: its revert broke
the INSTRUMENT — the probe called `os.path` without importing `os` — so the positive-control legs
failed in place of the row's control.

r8, over `96f4635`, ran 66 rows at `pass=60 earlier-layer=1 mismatch=5 silent=0 harness=0`. Its five
mismatches were a different thing again: four (D1, D6, G1, R17b) were rows whose EXPECTED NAME in the
harness was stale — S8a had added the control and the row still carried an older name, so the new
control fired by its own name and the harness called the row a mismatch — and the fifth was G4, still
asking nothing (class 5: it judged a value two other calls produce). S8e renamed the four and
repaired the one.

So neither verdict is a cause. Silence meant "no control", "a control asking nothing", "an aborted
suite" or "an earlier layer". A mismatch meant more than one thing too: of r7's seven, six were
stale expected names (F1, R0a, R3, R17a, R18a, Z1) and one was a revert that broke the INSTRUMENT
rather than the rule (R19); of r8's five, four were stale names again (D1, D6, G1, R17b) and one was
a control still asking nothing (G4). Only reverting the mechanism and reading which control fired
separates any of them. That is why a guarantee is
recorded here as the mechanism, the control, and the row — the three together — rather than as a
sentence about behaviour.

**What the run left behind, stated by its criterion rather than as a word.** The harness compares the
TOP-LEVEL names and mtimes of `~/.local/share/agent-bios` before each row, every fifth row, and at
the end; by that criterion the root was unchanged at every snapshot and at `R9 END`. A separate
full-tree watch the lead ran saw ONE change in the whole run, at 13:37:05, confined to
`sessions/snapshots/<hash>/` (a new snapshot) and `sessions/app-context/<codex thread id>` (an
mtime). The lead attributes it to the owner's own Codex app: five new rollouts appeared under the
real `~/.codex/sessions` between 13:36:37 and 13:37:09 and an existing 10-14 rollout of that same
thread was appended to. Row V2 was running at the time — the dispatch suite, with a control-helper
type guard reverted — and no code of this package writes either path. The full-tree watch saw nothing
else between 12:16 and 14:02. After the run: HEAD `fdba6f4`, tree
`d129002cafb69c0640d5abad3ff6a566cd7116fa`, working tree clean, `/var/tmp/r9-scratch` and the
harness's copy gone, no leftover Python process.

## 1. The guarantees, each with its weakest mechanism and its control

### 1.1 The emission tables (0308 §1's disclosure claims, restated)

| Guarantee | Weakest mechanism | Control that fails when it alone is reverted | Row |
| --- | --- | --- | --- |
| No record field reaches an artifact that its table does not name | the `key not in fields and key not in EMISSION_INTERNAL` test | `a record field no rule of its table names` | E1 (r9: PASS — that control failed by name) |
| A field whose kind is an enum carries only declared values | the `value not in _enum_values(spec)` test | `a value outside the declared set` | E2 (r9: PASS — that control failed by name) |
| A field whose form is its guarantee carries no owner path | the `OPAQUE_FORMS[spec["form"]].match` test | `an owner's path in a field whose form is its guarantee` | E3 (r9: PASS — that control failed by name) |
| A record's text is the carrier's bytes at the span it declares | the `unit["text"] != carrier_text[span]` test | `a record whose text is not the carrier's bytes at the span it declares` | E4 (r9: PASS — that control failed by name) |
| Two map keys that project to one string stay two facts | the `at in emitted` test | `two map keys that project to one string` | E5 (r9: PASS — that control failed by name) |
| A union field admits only what a declared kind admits | the `EMISSION_UNION_UNMATCHED` refusal | `a value no declared kind of a union field admits` | E6 (r9: PASS — that control failed by name) |
| A context entry carries carrier offsets or is unresolved | `_emit_context` | `an unresolved context entry with no carrier offsets behind it` | E7 (r9: PASS — that control failed by name) |
| Every carrier-derived field leaves through one path | `_emit_span` | `every carrier fixture, differentially` | E8 (r9: PASS — that control failed by name) |
| A layer row carries neither credential nor owner home | the metadata-text projection | `and the emitted layer row carries neither the credential nor the owner's home` | E9 (r9: PASS — that control failed by name) |
| An undeclared key is named by length and digest, never printed | the `spec is not None or key in schema_field_names()` test | `and the undeclared key is named by its length and digest, never printed` | E10 (r9: PASS — that control failed by name) |
| A carrier id is opaque | `sha256_text` in the id | `the carrier id is opaque and still distinguishes this carrier` | R12 — **EARLIER-LAYER in r8**: S1's emission table refuses the unhashed id (`Refused: EMISSION_NOT_OPAQUE rename.from_carrier_id`) before the row's own control is reached. The rule is guarded, by the layer in front of it. (r9: EARLIER-LAYER — `Refused: EMISSION_NOT_OPAQUE`, raised before the row's control is reached) |

0308 §1's "a withheld carrier withholds every span of it" holds, with the addition 0757 §6 made:
for the suite's own carriers the extent finder returns nothing, so withholding is the only defence
they have, and the controls are `a credential whose key sits more than two nonblank lines above the
value` (R0b) and `a span the floor returned with a credential still in it` (R0a).

### 1.2 The two entry points' own failure line (0308 §1's "every line the driver prints")

0308 stated this as the driver's property and 0308 §2's account of the handler was superseded by S2.
As it holds now: each of `session-distill/distill.py` and `session-distill/runlib/inventory.py`
bootstraps its own fixed, path-free line around the import of the boundary module itself.

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| The driver says one fixed line when the boundary cannot load | the bootstrap's `if __name__ != "__main__": raise` branch | `the driver, with the boundary module missing: the fixed line and nothing else` | B1 (r9: PASS — that control failed by name) |
| The inventory's entry point does the same | the same branch in that file | `this module's entry point, with the boundary module missing: the fixed line and nothing else` | B2 (r9: PASS — that control failed by name) |
| An unparsed argument is not echoed unprojected | `_print_message` through the floor | `an argument the parser did not understand is not echoed unprojected` | R2a (r9: PASS — that control failed by name) |
| A refusal naming its argument is not printed unprojected | `entry.say`'s projection | `a refusal naming the argument it refused is not printed unprojected` | R2b (r9: PASS — that control failed by name) |
| An unexpected file error is a projected diagnostic | the catch-all being `Exception` | `an unexpected file error is a projected diagnostic, not a raw traceback` | R2c (r9: PASS — that control failed by name) |
| A stage record is judged before it is published | `record_disclosures` at the publication | `a preserved part carrying a credential is refused before the record is published` | R1a (r9: PASS — that control failed by name) |
| A quarantine reason is projected where it is made | the projection in the reason | `the failure record was not published with the reason projected` | R1b (r9: PASS — that control failed by name) |
| A document key is named only when a schema declares it | the `key in schema` test | `a key no schema declares was named rather than numbered` | R3 (r9: PASS — that control failed by name) |
| A key that discloses without being credential-named is reported | the `problems.append` for that rule | `a key that discloses without being credential-named was not reported` | RS (r9: PASS — that control failed by name) |

### 1.3 The dispatch admission (0308 §3's "a copy-run is admitted by the call, not by the file")

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| A program form is the exact expression, arity included | `_exact_call`'s `len(node.args) == arity` | `planted-an-extra-argument-inside-the-own-file-form` (sibling: `planted-a-third-argument-to-the-member-owner`) | D1 (r9: PASS — that control failed by name) |
| A copy-run names only a member its site declares | the `member.value in entry["paths"]` test | `planted-a-member-this-site-does-not-declare` | D2 (r9: PASS — that control failed by name) |
| A member that is not a literal is not a member | the string-literal test | `planted-a-member-that-is-not-a-literal` | D3 (r9: PASS — that control failed by name) |
| A declared inline program's text is the declared text | the digest comparison | `a-declared-inline-program-whose-text-changed` | D4 (r9: PASS — that control failed by name) |
| An unresolved `python -c` is refused | the `DISPATCH_INLINE_UNDECLARED` append | `planted-unresolved-python-c` | D5 (r9: PASS — that control failed by name) |
| An inline program's argv is a list literal at the call | the `isinstance(argv_node, ast.List)` test | `an inline program whose argv is not a list literal at the call` | D6 (r9: PASS — that control failed by name) |
| `__file__` is the only name that is this file | the `node.id == "__file__"` test | `planted-a-rebinding-of-__file__` | D7 (r9: PASS — that control failed by name) |
| A copy-run entry names a file | the entry's own file test | `copy-run-entry-naming-no-file` | D8 (r9: PASS — that control failed by name) |
| A declared copy-run is one the site runs | the staleness test | `a-declared-copy-run-the-site-never-runs` | D9 (r9: PASS — that control failed by name) |
| An executor is a direct callee and nothing else | the parent-is-a-Call test | `planted-an-executor-referenced-as-a-value` | F1 (r9: PASS — that control failed by name) |
| No child is handed the suite argv | `_suite_argv_admitted` | `planted-a-child-handed-the-suite` | F2 (r9: PASS — that control failed by name) |
| `tempfile` is referenced only at a declared scratch site | the `(rel, where) not in declared` test | `a-second-scratch-inside-a-suite` | W1 (r9: PASS — that control failed by name) |
| No name is taken out of an executor's module | the `(module, alias.name) not in names_declared` test | `an-exec-import-form` | W2 (r9: PASS — that control failed by name) |

0757 §5 holds as written: the peel does not follow `.parent`, and the three planted controls (a
parent, a grandparent, a bare name) stand on the rule.

### 1.4 The bytecode cause and effect (1402 §1, restated)

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| The guard is a literal module-level statement, preceded only by stdlib imports | `_stdlib_only`, judged against `sys.stdlib_module_names` | `an entry file with a repository import before the guard` | G1 (r9: PASS — that control failed by name) |
| A guard nested under a condition is not the guard | the nesting test | `an entry file with the guard nested under a condition` | G2 (r9: PASS — that control failed by name) |
| Every `exec_module` is inside `with no_bytecode()` | the guarded-line-range test | `a module loaded by path outside the no-bytecode guard` | G5 (r9: PASS — that control failed by name) |
| A real invocation leaves the copy it ran from exactly as it was | the tree comparison | `the real invocation leaves the checkout it ran from exactly as it was` | R19 (r9: PASS — that control failed by name) |
| …and the comparison sees a directory | directories as entries of their own | `and it carries directories as entries of their own, so an empty one would show` | G3 (r9: PASS — that control failed by name) |
| …and reads links rather than following them | `lstat` in `tree_state` | `and it reads links without following them` | G4 — **the control could not fail until S8e**; see §2.3 (r9: PASS — that control failed by name) |

### 1.5 The protected roots and the destinations (0308 §3's host homes, S6, S7)

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| A host home is where its variable says | `host_homes` reading the shipped installer | `the driver itself refuses a run destination inside the home CLAUDE_CONFIG_DIR names` | H1, unsafe (r9: PASS — that control failed by name) |
| A checkout that does not ship the installer is refused, not defaulted | the installer-absent branch | `a checkout that does not ship the installer the host homes come from` | H2 (r9: PASS — that control failed by name) |
| The checkout is a protected root whatever `--project` declares | `checkout` in the root list | `the checkout is a protected root even when another project is the declared one` | R17a, unsafe (r9: PASS — that control failed by name) |
| The driver hands over a project set that names the checkout | `[str(repo), *(args.project or [])]` | `the project set the driver hands over names the other project AND this checkout` | R17b, unsafe (r9: PASS — that control failed by name) |
| A destination that HOLDS a protected root is refused | the `enclosing` clause of `overlap_problems` | `an output destination holding the owner's state root is refused before any write` | W5, unsafe (r9: PASS — that control failed by name) |
| A standalone `--to` over a run directory is refused | the driver's `if not args.run_id` branch | `inventory (S2) refuses a standalone --to that names a declared run` | R18a, unsafe (r9: PASS — that control failed by name) |
| …and a run directory is recognised by its markers | `all((path / name).is_file() for name in RUN_MARKERS)` | `a standalone destination that is a declared run directory` | R18b, unsafe (r9: PASS — that control failed by name) |
| One source selection stands before every read of the owner's state | `linked_above(path, boundary)` | `a read of the owner's state through a link: the runtime state itself` | R15a (r9: PASS — that control failed by name) |
| …and it walks the chain, not only the leaf | the `boundary is not None` walk | `a read of the owner's state through a link: a component above the runtime state` | R15b (r9: PASS — that control failed by name) |
| A self-test's scratch parent is judged by production's rule | `protected_roots` inside `scratch_parent` | `a self-test scratch parent inside the checkout's own .tmp` | W4, unsafe (r9: PASS — that control failed by name) |
| The manifest names every root it read and every protected root | the `masked(root, home)` projection of each root | `the input manifest names every root it read and every protected root` | T1 (r9: PASS — that control failed by name) |
| …and spells them as the projection does | the home `run` was given | `the manifest spells the roots it read as the projection does, never as raw paths` | T2 (r9: PASS — that control failed by name) |

### 1.6 The child bound and the suite's own recursion (0757 §1-§3, restated)

0757 §1's depth bound was a mark on a child's environment. That is gone: after S4 no self-test child
runs a suite, and the depth is counted in this process (`SELF_TEST_DEPTH`, limit 2).

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| A suite re-entering itself a third time is refused by name | the `SELF_TEST_DEPTH[0] >= SELF_TEST_DEPTH_LIMIT` test | `a suite starting inside a suite at the depth limit is refused by name` | Z1, depth, last and alone (r9: PASS — that control failed by name) |
| A `git` that does not finish is a refusal, never an empty listing | the bound on that one child | `a git listing that does not finish is refused by name, never read as an empty tree` | F4 (r9: PASS — that control failed by name) |
| A child whose group cannot be established is ended alone | `pgid = None` on `OSError` | `a child whose group cannot be established is ended alone, with no group signalled` | F3 (r9: PASS — that control failed by name) |
| The bound ends a TREE: the group is signalled once per round until empty | `for _ in range(rounds)` in `finish_group` | `the group-end round signals the group once per round until it is empty` | W3 — unguarded until S8c; see §2.2 (r9: PASS — that control failed by name) |
| …and the child leads its own group, so the group is the tree | `start_new_session=True` in `tracked_paths`'s `Popen` | `and neither the fixture git nor the sleep it started outlived the bound` — with S8f the revert is refused at spawn, so the control that READS it is `a git listing that does not finish is refused by name, never read as an empty tree` (measured; §2.2) | W6 (r9: PASS — that control failed by name) |
| A child that leads no group of its own is refused at spawn, not recorded | the `pgid is not None and pgid != proc.pid` test in `bounded` | `a child started without a session of its own is refused by name, and no group is signalled` | W7 (r9: PASS — that control failed by name) |

### 1.7 The suites' own honesty (S8a-S8e; no earlier record states these)

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| A boolean-style helper refuses a problem list | the `isinstance(condition, bool)` guard | `a boolean-style control given a problem list is refused by name` | V1 (distill), V2 (dispatch), V3 (stop) (r9: PASS — that control failed by name) |
| …and the inventory's `check` does too | the same guard there | `a boolean-style check given a problem list is refused by name` | V4 (r9: PASS — that control failed by name) |
| A problem-list helper refuses a non-list | the `isinstance(problems, list)` guard | `a problem-list control given something that is not a list is refused by name` | V5 (r9: PASS — that control failed by name) |
| An abort publishes what the suite had already collected | `publish_collected`'s loop | `an abort publishes the failures a suite had already collected` | X1 (r9: PASS — that control failed by name) |
| …and every abort path reaches that publication | the call in each handler | `every abort path of this package publishes what the suite collected` | X3 (r9: PASS — that control failed by name) |
| The stop machinery's module-level imports stay stdlib-only | the import living on the suite's path | `the stop machinery's module-level imports are the standard library alone` | X2 (r9: PASS — that control failed by name) |
| A control asked after the report has begun is refused | the `reporting` flag in each helper | `a control asked after the report has begun is refused by name` | X4 (r9: PASS — that control failed by name) |

## 2. Statements of 0308, 0757 and 1402 that are no longer true

### 2.1 Scope: "the other runlib modules still print directly"

0308 §1: "**Scope, stated rather than implied:** that boundary is package A's two files. The other
runlib modules each have a standalone `--self-test` that still prints directly; they are not this
package's subject". 0757 §7: "the other runlib suites still print directly and still run their
children unbounded".

**What replaces it.** Still true of each suite's own report lines. No longer true of the
collected-failure publication: S8c put `SELF_TEST_COLLECTED` and `publish_collected` in
`runlib/entry.py`, and `runlib/dispatch.py` and `runlib/stop.py` publish through it from their
`__main__` wrappers before re-raising. `runlib/stop.py` now imports that boundary — on its suite's
path only, with the `sys.path` entry it needs, so a production import of it still loads the standard
library alone, which the control `the stop machinery's module-level imports are the standard library
alone` (X2) states. "Still run their children unbounded" is still true, and is residual §3.11.

### 2.2 "A timeout ends that GROUP"

0757 §3: "The child starts in a session of its own, and a timeout ends that GROUP … Only a child
that leads its own group is ever signalled; that check is what keeps the call from signalling this
process's group."

**What replaces it.** Both sentences are true and neither was watched. The group end has two passes
— `end_group` before the leader is reaped, and `finish_group` after — and the second had no control
at all: with `for _ in range(rounds)` emptied in a copy at `6c593f8`, the driver suite was `rc=0`,
105 controls, no failure (`work/impl/w3-no-control-probe.log`). S8c gave it one, and the rule it
states is narrower than "ends the group": the group is SIGNALLED once per round until it is empty.
Returning `False` is not the rule, because a group that never empties returns `False` with no rounds
at all. W6 was the other half, and reading it is what found the next gap: with
`start_new_session=False` the child sits in this process's group, `end_group` takes its non-leader
branch and kills the shell alone, and `finish_group` is never reached.

**`bounded` used to RECORD that rather than refuse it** (`CHILD_GROUP_ENDED`), so the sleep the shell
backgrounded outlived the bound and only a control written for that one fixture noticed — every other
bounded call would have leaked the same way with nothing asking. The requirement stood in `bounded`'s
own docstring and nothing checked it. S8f makes it default-deny, decided at SPAWN: when `getpgid`
succeeded and the group is not the child's own, the child is ended alone and a named failure comes
back instead of a result (`CHILD_NOT_GROUP_LEADER`, code 98 — nonzero, so no caller reads it as a
result, and distinct from `TIMED_OUT`, so no caller reports a timeout for a child that never ran).
**Refusing is not signalling**: no `killpg` is reached, which is the point, because the group is this
process's own. `pgid is None` is a different case and is NOT refused — ownership was never
established, which an ordinary child that exits before the read produces, and F3 still answers for
it.

All ten `bounded` / `bounded_child` sites that start a real process pass `start_new_session=True`;
the eleventh is a stub with no process at all, and the twelfth is the new control's own subject,
which omits it deliberately.

W6's expected outcome was re-derived by MEASURING it rather than reading the code: with the refusal
in place the shell is ended before it backgrounds its sleep, so the marker is empty and the pid
control cannot fire at all. What fires is `a git listing that does not finish is refused by name,
never read as an empty tree`, because `tracked_paths` sees code 98, which is not `TIMED_OUT`, and
raises `TREE_UNLISTABLE … (code=98)` with no `CHILD_TIMEOUT` in it. EARLIER-LAYER does not apply
either: the suite does not abort, and the line reads `Refused: TREE_UNLISTABLE`.

### 2.3 "links read rather than followed"

1402 §1: "leaves that copy exactly as it was: entry names, content hashes, mode, size and mtime in
nanoseconds, with directories as entries of their own and **links read rather than followed**".

**What replaces it.** The same sentence, now with a control that can fail. Until S8e the control read
only the `link:<target> ` prefix, which `is_symlink()` and `os.readlink` produce — not the `lstat`
the row reverts. Shown in a disposable copy at `96f4635` with the row's revert applied: the planted
link reports `link:session-distill/distill.py mode=100644 …`, a regular file's mode, and the suite
stays green. The control now parses `mode=` out of the link's recorded state and requires
`stat.S_ISLNK`, so it judges what the reverted line decides as well as selecting its subject.

The S8a claims-table row for G4 records "with the `lstat`/`readlink` branch gone … the link reported
with a CONTENT HASH". That is a different mutation from the row's — the whole branch removed, not
`lstat` → `stat` — and both statements are true of their own mutation. Neither covered the row.

### 2.4 0757 §1's depth bound

"The depth is now bound by a mark on the child's environment (`AGENT_BIOS_SELF_TEST_NESTED`,
`entry.nest`), and a marked run skips the sections that would run it again."

Already named by 1402 §5 and restated here for completeness: after S4 no self-test child runs a
suite, the mark and the structural checker over the four sites are gone, and the depth is counted in
this process. 0757's named residual — "outside the harness, in-run recursion is bounded only by the
per-child time limit" — goes with it; what remains is Z1's in-process limit of 2.

### 2.5 0757 §1's "The guard has no revert case, deliberately"

"Reverting it IS the incident."

**What replaces it.** True of the environment mark, which no longer exists. The in-process depth
limit DOES have a revert row — Z1 — run last, alone, with a 300 s bound, because what it reverts is
a counter in this process rather than a wiring that makes children spawn children.

### 2.6 1402 §5's "the record that restates … is written after S7"

This record is later than S7 and covers S6 through S8f. The round did not end at S7.

## 3. Residuals: the reason, and what would reopen it

1. **`census.reconciled.json` is written without the emission tables' judgement.**
   `session-distill/distill.py:198` (the lead's brief says 156; the line moved) writes
   `census.reconciled.json` and `coverage.reconciled.json` through `records.write_text` /
   `write_json`. Reason: these are S3's own reconciliation outputs, not an inventory artifact, and
   the emission tables are the inventory document's contract. **Reopens if** a reconciliation output
   is read by a model-facing surface, or if a credential or a home path is found in one.

2. **Dynamic argv, the adversarial case.** The dispatch judge admits a program form only as the
   exact expression at the call, and refuses argv that is not a list literal there (D6). It does not
   decide what a program does when the argv elements are computed at run time by code the judge can
   read but not evaluate. Reason: the judge is a static reader, and evaluating would make it a
   second interpreter. **Reopens if** a site needs a computed argv, which would have to be declared
   and judged some other way.

3. **A write that was attempted and refused leaves no trace.** 1402 §2 withdrew this and the
   withdrawal stands: an audit hook fired before the operation, which is what made "attempted"
   askable; with no observer the question cannot be asked by comparing a tree, and it is not asked.
   **Reopens** on 1402 §3's condition, unchanged: a defect in which the command attempts a write
   under a tree it must not touch, the attempt fails for an unrelated reason, and the tree therefore
   looks untouched.

4. **A descendant that escapes into a session of its own.** The non-leader case is no longer a
   residual: S8f refuses it at spawn and W7 watches the refusal. The earlier wording here gave the
   reason as "refusing would mean `killpg` on this process's own group", which confused refusing with
   signalling — refusing ends the child alone and returns a named failure, and reaches no `killpg`
   at all.
   A child refused at spawn may already have started descendants of its own, between its `exec` and
   our `getpgid` read; those sit in THIS process's group and nothing here ends them, because ending
   them would mean signalling our own group — which is by design, and is the same reason the refusal
   is not a `killpg`.
   What also remains is the case a process group cannot reach by construction: a descendant that
   calls `setsid` itself and leaves the group the bound signals. Reason: the group is the only handle this
   bound has, and a process that leaves its group cannot be named by it. **No child of package A
   does this** — every bounded site starts a direct child of this package, and every program they
   start is either a `python -c` one-liner this file holds as a constant or the `/bin/sh` script the
   slow-git fixture writes; none of them re-sessions itself, and `start_new_session` is the only
   session creation in `session-distill/`. **Reopens if** a bounded call is given a program that
   re-sessions itself, or if a process is observed surviving a bound with its group already gone.

5. **Production `git` outside the bounded call.** The one `git` inside `tracked_paths` is bounded
   (F4, W6). `session-distill/distill.py:246` runs `git -C <repo> rev-parse --short HEAD` with a
   plain `subprocess.run` and no timeout, and `session-distill/migrate-ledger.py:402` does the same
   with `ls-files`. Reason: both are local reads on a repository the caller already owns, and
   neither is in the frozen-copy path the inventory's guarantee is about. **Reopens if** either is
   reached over a filesystem that can block (a network mount, a stale automount), or if a run is
   observed with no verdict at one of those calls. (0757 §7 named the unbounded production `git`
   calls as a residual and 1402 §5 said they "moved with" S4; these two sites are still unbounded,
   so the residual is restated rather than closed.)

6. **`PROCESS_MODULES` is an enumeration.** `runlib/dispatch.py:388` lists the modules that can start
   a process and that `EXEC_CALLS` does not describe. Every other rule of that judge is
   default-deny; this one is a list, so a module nobody thought of is admitted. Reason: there is no
   decidable property that separates "can start a process" from the rest of the standard library.
   **Reopens if** a new import of a process-capable module appears that the list does not hold, or
   if a decidable test is found.

7. **The `all()` sweep and the type-guard sweep are measured, not guaranteed.** The `all()` sweep
   (S8a) instrumented all 66 `all(x)` calls in six files and found 65 never empty and one safe; the
   type-guard sweep (S8b) rewrote the guards to RECORD and ran the four suites once, finding three
   calls that were asking nothing. Both are statements about the paths those runs took. Reason: "can
   this be empty / can this be the wrong type" is not decidable from the code. **Reopens** every
   time a fixture-built subject can empty, which is how the G4 leg arose; the type guards are
   permanent, so a late call fails the first time it runs, but the `all()` measurement installs no
   guard at all.

8. **That a specific abort reaches its handler was read in code, not run.** 6b's publication is
   proven to print (X1) and to be REACHED from each handler's own tree (X3, read with `ast`). That
   the handler is the one a given abort actually takes is read from the code. Reason: planting an
   abort mid-suite means running a suite inside a suite, which is the incident S4 exists for.
   **Reopens if** an abort is observed in a real run with no published report.

9. **The slow-git cause was never established.** "slow-git-ran was never created" appeared in 8 of
   61 inventory runs across r7 and r8 (r8 E7, G4, T1, X2, X3; r7 E1, E5, G2), and in X2 and X3 the
   row still counted as a PASS because its own control fired too, so the flake rode along unread.
   S8e removed the DEPENDENCE — 3 s to be seen against a 30 s sleep, with both pids asked — and
   claims no cause beyond timing. r9 is the first evidence either way: the line appears in none of
   its 68 row logs, 37 of which ran the inventory suite. **Reopens if** the check fails again with
   the wide margin, which would mean the cause is not start-up time.

10. **A refused child whose pipes do not drain is not named as such.** On the spawn-time refusal
    path, when the bounded drain times out, `out` and `err` become empty strings and no
    `CHILD_CLEANUP_UNFINISHED` line is added — which is what the TIMEOUT path does for the same
    situation. Reason: the refusal's own name (`CHILD_NOT_GROUP_LEADER`) is in the stderr either way,
    so nothing is silent; what is missing is the second line that would say the drain did not finish.
    **Reopens when** a caller needs to tell a refused child whose pipes drained from one whose pipes
    did not. Recorded by the lead's ruling rather than fixed.

11. **The other `runlib` suites still run their children unbounded.** `entry.bounded` is reached by
    `session-distill/distill.py` and `runlib/inventory.py` and by nothing else: `runlib/dispatch.py`
    (4 children), `runlib/stop.py` (6), `runlib/ledger.py` (1), `runlib/receipts.py` (1) and
    `runlib/sources.py` (1) each start processes in their own self-test with a bare `subprocess`
    call, and none of those files names `entry.bounded` or `bounded_child` at all. Reason: the
    package boundary is 0308 §1's own sentence — "that boundary is package A's two files. The other
    runlib modules each have a standalone `--self-test` that still prints directly; they are not this
    package's subject" — and 0757 §7 says the same of the children: "the other runlib suites still
    print directly and still run their children unbounded". (1402 §4 scopes the BYTECODE cause and
    effect claims to those two files; it is not the boundary sentence.) A bound is a change to a
    suite this package does not own, so the sentence is restated rather than quietly widened. **Reopens
    if** one of those suites is observed reaching no verdict, or when the contract-fix package takes
    them, which is also where `runlib/monitor.py`'s unguarded self-test helper waits.

## 4. The vacuous-control classes this package found

Each one is a shape a reviewer can look for, with the instance that taught it.

1. **Same name, different signature.** `control` is `(name, condition, detail)` in some files and
   `(name, problems, *needles)` in others. Three controls written in the second style inside a file
   holding the first passed on a truthy list whatever their needle said, and one of them was the
   control for r7's D6. **Look for:** a helper name shared across files; read the signature of the
   file you are in. **Now enforced** by each helper refusing the wrong kind of argument (V1-V5).

2. **An empty `all()`.** `all(... for x in xs if predicate(x))` is true about no subject when nothing
   satisfies the predicate. The G4 link leg ran over nothing, because the repository tracks no
   symlink and `checkout_copy` skips any it meets. **Look for:** a comprehension with a filter, over
   a set the fixture builds. **Not enforced:** measured once (§3.7).

3. **Collected failures lost on abort.** `check` and `control` append to a list the suite prints at
   the end, so an exception leaving the suite took every line with it. Three reverts read as "no
   `[FAIL]` line at all" in r7 when the cause was an abort, not a silent rule. **Look for:** a
   runner that collects and reports late. **Now enforced** by X1 and X3.

4. **Controls standing after the summary.** The summary line carries `len(ran)`, so a control after
   it is outside the number published AND the line has already said OK. Four legs of 6b stood there;
   the count read 466 before and after they were added, which is how they were found. **Look for:** a
   count in a summary, and anything after the line that prints it. **Now enforced** by X4.

5. **A control judging a value another call produced.** G4's control read the `link:<target> `
   prefix, which `is_symlink()` and `os.readlink` write — not the `lstat` the row reverts. The
   control was about a different call than the mechanism it was supposed to watch. **Look for:** the
   exact expression the revert changes, and ask which characters of the control's subject come from
   it.

6. **One control's condition coupled to another control's subject.** R17b's "and that project set was
   read from a call that really happened" judged `len(handed_projects) == 2`, which is the next
   control's subject. Both failed together under the revert, and the first said the producer was
   never reached when it had been — a true failure with a false message. **Look for:** two controls
   whose conditions share a term; each must be able to fail alone.
