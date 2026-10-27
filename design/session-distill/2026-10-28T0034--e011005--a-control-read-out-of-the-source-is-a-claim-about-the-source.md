---
created_at: 2026-10-28T00:34:00+09:00
head: e011005
kind: design
supersedes:
  - 2026-10-27T1405--fdba6f4--a-guarantee-is-the-mechanism-the-control-and-the-row-that-watched-it.md
---

# A control read out of the source is a claim about the source, not about the run

Hermetic round 4 reviewed `git diff ae36970 e011005` and returned rework with eight findings; the
lead checked every one against the source and ruled seven of them code defects and one a defect in
the 1405 record. This record names the statements of the 1405 record that this step makes false and
states what is true at `e011005` plus the S9 commits. It supersedes 1405 only where it says so;
every other row of that record stands as written.

The sentence in the title is the shape three of the eight findings share. A control that reads a
file's source and asks "does some handler of it reach the publication" is a claim about the source,
satisfied by the handler that does while the handler that does not goes unseen. A control that asks
`group_alive` about a process that leads no group is a claim about a group that never existed. A
control that matches a refusal by a prefix two refusals share is a claim about the prefix.

None of them was watching the mechanism it was written for, and each was green through every round
it existed in — which is days, not years, and is the point: the source-reading one (X3) was written
on 2026-10-27 in S8c and reported PASS in the r9 revert round the same day; the descendant one dates
from r3's child-bound work and was green in the r7, r8 and r9 revert rounds and in hermetic rounds 1
to 4; the two prefix-matching ones were green in the ae36970 control-audit and in r9, and S8i
narrowed them only after reverting the refusal and printing the rows showed which row had been
answering.

## 1. Statements of the 1405 record that are no longer true

### 1.1 "…and every abort path reaches that publication" (§1.1, the X3 row)

1405 §1.1 carries this row:

| Guarantee | Weakest mechanism | Control | Row |
| --- | --- | --- | --- |
| …and every abort path reaches that publication | the call in each handler | `every abort path of this package publishes what the suite collected` | X3 |

Two things in it were false at `fdba6f4` and at `e011005`.

The CONTROL did not ask about the abort paths. It parsed each runner's source and required that SOME
`except` handler of the file — or, for `entry.py`, `failed` — reach `publish_collected`. Both files
whose handlers did not publish also held handlers that did, so the control was green over them:

* `distill.main`'s `except (Refused, stagelock.Locked, stagelock.Escaped)` said the refusal and
  returned. The suite runs INSIDE that boundary, so a refusal raised from inside it took every
  collected failure line with it; only the later `except Exception` published.
* `entry.guarded`'s three `SystemExit` branches returned without publishing, and `guarded` is the
  boundary the inventory's own suite aborts through.

And the GUARANTEE was not reachable for two of the four runners at all: `dispatch.py`'s and
`stop.py`'s handlers were a `try` inside `if __name__ == "__main__"`, which no control can enter —
which is why the claim had been read out of the source in the first place.

As it holds now: each runner's own handler publishes, and each is DRIVEN by a control in its own
suite.

| Guarantee | Weakest mechanism | Control |
| --- | --- | --- |
| A handled refusal publishes what the suite collected | `entry.publish_collected` in `distill.main`'s refusal handler | `main publishes the failures the suite collected when the command raises a refusal` (and one row each for `stagelock.Locked`, `stagelock.Escaped` and an unexpected failure) |
| A `SystemExit` through the guarded boundary publishes too | the call before the code is decided in `guarded` | `the guarded boundary publishes the collected failures on SystemExit carrying an int` (and one row each for a message, for None, for a refusal and for an unexpected failure) |
| `dispatch.py`'s `__main__` boundary publishes | `main_boundary`'s `except BaseException` | `the main boundary publishes what the suite collected before an abort leaves` |
| `stop.py`'s `__main__` boundary publishes | the same, in that file | `the main boundary publishes what the suite collected before an abort leaves` |
| …and a normal path publishes nothing | the empty `SELF_TEST_COLLECTED` on a reported suite | `and a normal return through the same boundary publishes nothing`; `and a run that returns normally through it publishes nothing and keeps its code` |

The `__main__` blocks are now one line each (`sys.exit(main_boundary())`). A handler inside an
`if __name__` block is unreachable by every control in the process, so it is not a place a
guarantee can live.

### 1.2 "and neither the fixture git nor the sleep it started outlived the bound" and the descendant row (§1.4, W6)

1405 §1.4's W6 row reports the group-is-the-tree guarantee as watched. The row itself stands, but
the control beside it in `distill.py` — "and the descendant that outlived its leader is gone
afterwards" — was asking nothing: it passed the descendant's PID to `entry.group_alive`, which calls
`os.killpg(pid, 0)`. The descendant leads no group of its own, so that raises `ProcessLookupError`
and the control read "gone" whether the descendant lived or not. Its fixture made the same mistake
twice over: a natural lifetime of three seconds, shorter than `GROUP_DRAIN` (10s) plus the SIGKILL
rounds (5s), so even a judgement that worked could have been reading a process that simply ran out.

As it holds now: the descendant is judged as a PROCESS (`os.kill(pid, 0)`; it is reparented and
reaped by init, so a vanished pid raises), and both sleeps in the `IGNORES_TERM` fixture are 90
seconds — longer than the whole bound, finite all the same. Its declared `sha256` in
`INLINE_PROGRAMS` moved with the text.

What the reverts establish about this one, exactly, because less than was planned: the control is no
longer vacuous, and it is fail-closed. With every kill the bound sends after a timeout removed —
`end_group`'s SIGKILL and `finish_group`'s rounds, which is what actually reaches a TERM-ignoring
descendant — the control fails by name. It fails through its `len(descendant) == 1` guard rather
than on a live process, because the descendant then holds the leader's pipe, `bounded` gives up
without that output, and the fixture's `DESCENDANT <pid>` line never reaches the control at all.
The 90-second lifetime is what removed the natural-death mask: at three seconds the descendant was
gone before the control looked, whatever any kill did.

Judging by process rather than by group is correct by construction — `killpg` on a pid that leads no
group raises `ProcessLookupError`, which the old control read as "gone" — but no revert row proves
that judgement load-bearing with this fixture, because the only state in which a pid reaches the
control is one in which the descendant is already dead. Reverting the judgement alone leaves the
control green (the kill still works), and reverting it together with the kills leaves it failing on
the empty list, so neither row isolates it. A second fixture whose descendant reports its own pid on
its own stream would isolate it; that is a proposal, not a claim, and the current fixture's premise
— "a bound reached with a descendant holding the pipe is a named failure, not a wait" — is why it
was not changed here.

Beside it, two controls now ask `end_group` itself, with a recording `os.killpg` and no process at
all: that it sends SIGTERM and then SIGKILL when the leader reports itself exited right after the
SIGTERM, and that it sends both to a leader that never exits. The unconditional SIGKILL is the
mechanism r3 #1 added, and nothing was watching it independently of `finish_group` and of a
fixture's own lifetime.

### 1.3 The differential's reach (§1.1, the E8 row)

1405 §1.1's E8 row — "every carrier-derived field leaves through one path", watched by `every
carrier fixture, differentially` — understated what the control reached and overstated what it
covered. `emitted_document`'s own docstring said "called by `reference_of` and by the differential
control alike"; nothing but `reference_of` called it. The differential called `units_of` + `shed`
itself, so it never drove `operative_context`, the reference, layer and produced-by rows, or the
disclosure judgement `write_document` makes before an artifact exists. Its schema check compounded
this: it collected only properties whose own `type` is string, so `operative_context` — an array of
strings, and the one field a context leak travels in — was not in the set it held the walk against,
and neither was any string leaf under a `$ref` or a nested object.

As it holds now: the differential drives `emitted_document` and then `write_document` into the
suite's own scratch, per fixture and then with every fixture in ONE document, and reads the strings
back from the published file. The schema's string leaves are resolved recursively through `items`,
`properties`, `$ref` and the `anyOf`/`oneOf`/`allOf` branches, with a cycle guard, and the
requirement is held LEAF BY LEAF: each leaf is named by its path from the unit (`provenance.transcript`,
`operative_context[]`, an array index normalized to `[]`), and the walked set is built the same way
from the document's own locations. Judged per top-level field instead — which is where the recursive
resolution first landed — `provenance` counted as covered the moment any one of its five strings was
walked, and a sub-field no fixture fills, or one added later, passed unseen.

Six leaves were unwalked when the requirement first held leaf by leaf: `provenance.hosts[]`,
`.identity`, `.keep_reason`, `.keep_units[]`, `.reference` and `.status`. None of them is
unfillable and none is exempted: the native fixture now carries the `reference`, `record` and
`identity` its producer sets, and a ledger fixture carries the `status`, `keep_units` and
`keep_reason` `_ledger` sets plus the `hosts` list the deduplication appends.

Two statements that went with it, also false:

* A comment in the mention-fixture block said no valid JSON carrier can be withheld whole, so JSON
  was the one carrier kind with no whole-withheld fixture. `projection.carrier_decision` returns the
  whole-carrier withholding (`([], True)`, the same answer the escaped markdown fixture gets) for a
  VALID JSON object whose string value holds an escaped credential key over two lines, and
  `units_of` splits it into a unit. The comment is deleted and that fixture is in the set.
* `reference_of`'s caller appended `mapping_problems(...)` to `document["reference"]
  ["incomplete_reasons"]` after the row had been emitted, so those strings passed no rule of the
  reference table — and a baseline item ref is a path often enough. Such a reason now reaches the
  row through the table, as a `more_reasons(units)` the production path calls before the row is
  emitted.

### 1.4 Residual 1's reopening condition (§3.1)

1405 §3.1 gives the reason for writing `census.reconciled.json` outside the emission tables and then
says it **reopens if** "a reconciliation output is read by a model-facing surface, or if a credential
or a home path is found in one". The second half is met by design, so the residual as written was
already reopened and said nothing: `census.json` (`census.py:533`) and `census.reconciled.json`
(`distill.py:198`) are written through `census.dump` alike, and both carry each transcript's `path`
because that is the census contract —
`design/session-distill/2026-10-20T2119--cc0498f--implementation-plan.md` (~519) defines
`census.json` per transcript as `{id, source, path, sha256, …}`, and later stages re-read
transcripts by it. Applying the floor to it would break the locator.

As it holds now, replacing §3.1's residual: census outputs carry raw transcript locators BY
CONTRACT. They are written into the run directory (`session-distill/out/<run-id>/` by default, which
`.gitignore` excludes) and are not an inventory artifact. **Reopens if** a census output is read by a
model-facing surface, if one is copied outside the run directory, or if one carries a credential.
A home path in a census output is the contract, not a defect. No code changed for this item.

## 2. What else S9 changed, which 1405 did not state either way

The dispatch judge's two default-deny gaps and the floor decision's cache key are new ground rather
than corrections of 1405, and they are here so one record carries the round.

| Guarantee | Weakest mechanism | Control |
| --- | --- | --- |
| A floor decision answers for the carrier VERSION it was taken from | `_decision_key`'s digest of the carrier text | `two versions of one carrier identity, harmless first: the withheld version's secret in no published string` (and the same with the withheld version first) |
| Two versions of one identity are two carriers everywhere, not only there | `_carrier_key` in the context structures | `two versions of one identity are two carriers at one path, so the context states the ambiguity` |
| A literal program is admitted only by declaration | `_judge_literal`'s default deny | `planted-a-literal-program-no-declaration-admits`, `planted-a-declared-program-written-at-another-site` |
| A literal interpreter is refused wherever it is written | `INTERPRETER_NAME` | `planted-a-literal-interpreter-as-the-program` |
| Every command of a shell line is judged, not only the first | the separator split in `_judge_words` | `planted-a-shell-lines-second-command-starting-a-host`, `planted-a-shell-lines-second-command-running-an-interpreter` |
| A suite flag in a shell line is refused | the `--self-test` test in `_judge_words` | `planted-a-shell-line-carrying-the-suite-flag` |
| A watched module is never a value | the `ast.Name` test against `WATCHED_MODULES` | `planted-the-scratch-module-taken-as-a-value`, `planted-an-executors-module-taken-as-a-value`, `planted-a-watched-module-handed-to-a-function` |
| An inline program's declared index is the index the PROGRAM reads | `at_c + 1 + row["loads"]` | `an-inline-program-whose-flagless-argv-moves-the-element-it-loads` |
| A suite's own shell text quotes the paths it interpolates | `slow_git_script`'s environment variable | `the fixture git writes its marker inside scratch when its parent's name is shell`, `and the file an unquoted redirect would have truncated is untouched` |
| Every command of a shell line is found however it is written | `_shell_tokens`' `punctuation_chars` and its newline separator | `planted-shell-a-separator-glued-to-the-command-before-it`, `-a-glued-pipe-into-a-host`, `-a-second-command-on-the-next-line` |
| A builtin that runs the next word does not hide it | `SHELL_RUNS_NEXT` | `planted-shell-a-program-run-by-exec`, `-a-program-run-by-command` |
| A line built at run time is refused rather than read | `SHELL_EVALS` | `planted-shell-a-line-run-by-eval` |
| A command substitution is refused rather than read | `SHELL_SUBSTITUTIONS`, checked in a word and across a token pair | `planted-shell-a-command-substitution-in-dollar-parens`, `-in-backticks`, `-a-process-substitution` |
| A failing control keeps its own name | `failure_text`'s whole-line-first judgement with a detail-free fallback | `a failure whose name and detail trip the floor together still publishes its name`, `a detail the floor admits alone is still not published when the pair is withheld` |
| A line that skipped the floor cannot leave through the unprojecting printer | `emit`'s `FailureLine` type check | `the unprojecting printer refuses a line that did not come from the floor` |
| A shell builtin that runs a line of its own is refused | `trap` sitting in `SHELL_EVALS` | `planted-shell-a-line-deferred-by-trap`, `-a-trap-after-an-admitted-command` |

The eight literal programs the old fallthrough admitted in silence were instrumented over the real
tree before the rule was closed, and exactly those eight are declared in
`LITERAL_PROGRAMS_DECLARED`: `git` at four sites, `zstd` at two, `cp` and `ps`. The declaration is
per site and matches the program's basename, because the trace resolves `zstd` and `ps` to wherever
this machine holds them.

**The shell line's commands.** Closing the tail left the commonest spelling of a second command
still admitted: the words reached the judge pre-split by `shlex.split`, which leaves `status;` whole,
so a separator glued to the command before it was no separator and everything after it went
unjudged. `git status; python3 x.py`, `git status|codex exec -`, a second command on the next line,
`exec python3 x.py`, `eval '…'` and a command substitution were all admitted at the point the tail
was closed. One tokenizer now answers for every shell line — `shlex.shlex(..., posix=True,
punctuation_chars=True)` with `whitespace_split`, per physical line, a newline becoming its own
separator token — and both call sites use it; the SHELLS site tokenizes as a LINE only the argv
element after a `-c`-style flag, because re-splitting the others would change the shape of a quoted
argument. There is no real shell line anywhere in `session-distill/` for these rules to judge today:
every match for `os.system`, `os.popen`, `shell=True`, `getoutput` and `sh -c` outside the judge's
own planted source strings is absent, so the positive control is the real tree staying clean.

**Two more of the same two shapes, found after the first S9 commit.** `trap '<line>' SIG` runs its
argument as a line when the signal arrives — `eval` deferred — and `trap` was in the list of
builtins that start no program, so `trap 'python3 x.py' EXIT` and a `trap` after an admitted command
were both admitted. It is refused by name now, with the refusal's wording covering a deferred line
as well as one built at run time. And `emit`, the one printer that publishes without projecting,
rested on a docstring naming its callers: `failure_text` now returns a marked `FailureLine` and
`emit` refuses anything else by name, so a string from anywhere else cannot leave through it
unprojected. A convention is not a guard.

**A failing control's own name.** The `[FAIL]` lines of this package's two floor-bearing runners
were projected as ONE string, so a line whose name and detail read as a credential key and its value
together came back as the placeholder alone — no name, no tag, no suite label. The r4 R0 revert did
exactly that, and the harness reading it recorded a named failure as unnamed. `entry.failure_text`
now projects the whole line first, because a whole-line judgement is the strongest the floor makes,
and when that withholds the line it publishes the label, the tag and the name with the DETAIL
REPLACED BY THE PLACEHOLDER. The detail is never re-judged on its own: the floor withheld the line
because of the pair, and a detail projected alone loses the context it was refused for — publishing
it would undo the judgement that had just refused it. The label and the name are published only as
the floor returns them, and the line says which part was withheld. `entry.emit` is the one printer
that does not project what it is given, with its callers named in its docstring, because projecting
the rebuilt line again would hand the floor the joined string and take the name back out.

The controls for it carry BOOLEANS as their detail, never the planted text or the published line: a
control for this defect must report through a line the defect cannot eat, and the first version of
these two reported through one it could.

## 3. The `head:` this record carries, and what its present tense describes

`head:` is `e011005`: the base this record was written against, before S9 was committed. It is not
the tree every statement here was checked at, and the first version of this section said it was.
Each "as it holds now" above describes the S9 code, which was checked in the worktree and is
committed as `a4dadb6` — a commit that did not exist when this record was written, which is why the
frontmatter cannot name it. Read the base from `head:` and the behaviour from `a4dadb6`.

The revert table, the per-row verdicts and the control counts are in the implementer's work notes,
which live outside this repository, and are summarized in the round-5 review packet. They are not
referenced by path here: a path to a file no reader of this repository has is not a reference.

## 4. What this record does not establish

Round 5 has not run. The eight findings are the lead's rulings on round 4, checked against the
source by the lead and then by the implementation; the reproduction of R0 and of the JSON
whole-withheld decision was re-run here before either was changed, and the 2119 prefix hypothesis
was confirmed by reverting that refusal and printing the rows. No control-audit was run for this
step; the control counts and the revert table are in the implementer's work notes outside this
repository, summarized in the round-5 review packet.
