---
created_at: 2026-10-28T05:49:10+09:00
head: aa80bb1
kind: design
supersedes:
  - 2026-10-28T0034--e011005--a-control-read-out-of-the-source-is-a-claim-about-the-source.md
---

# A parser's message is the carrier's own text, and a judge that normalizes a name admits a different program

Hermetic round 5 — the last — reviewed `git diff e011005 aa80bb1` and returned **fix_then_accept**
with six findings: one blocking, four major and all five reachable, plus one impossible-condition.
By the owner's rule there is no further review round: the reachable five are fixed in S11 and the
lead verifies them, and the sixth becomes a named residual. The lead checked every finding against
`aa80bb1`, reproducing three of them in memory.

This record names the statements of the 0034 record that round 5 showed false or too strong, states
what is true after S11, and carries the residual. The 0034 record is not edited.

The title is the shape of the blocking one and of the two beside it. A carrier the floor withholds
whole does not stop being that carrier when a PARSER describes it: tomllib names the duplicated
table, a `SyntaxError` names the identifier it tripped on, and those words became a layer row's
reason, which the floor then projects on its own, without the carrier's context — so the withheld
carrier published itself through its own error. And a judge that normalizes a name before ADMITTING
it admits a different program than the one written: `git.sh` is not `git`, and `/fixture/echo` is a
file the shell runs, not the builtin the comparison matched.

## 1. Statements of the 0034 record that round 5 showed false or too strong

### 1.1 §2's "Every command of a shell line is found however it is written"

False as written. `shlex` with `punctuation_chars` returns a RUN of punctuation as ONE token, so
`git status;(python3 x.py)` yields `';('`, `git status&&(codex exec -)` yields `'&&('`, and
`(git status);python3 x.py` yields `');'`. None of those is a separator, so the command after it was
never judged — three lines, all admitted, none of them exotic.

As it holds now: a token of punctuation alone is decomposed into the operators it is made of,
longest match first, and the decomposer takes its operator table as a PARAMETER. A run that does
not decompose is refused by name (`DISPATCH_SHELL_UNPARSED`).

That refusal is **unreachable with the real table**, and this is asserted rather than claimed in a
comment: `punctuation_characters()` reads the set from a configured `shlex` instance rather than
from a copy of the string, `punctuation_covered()` returns the characters no single-character
operator covers, and a control holds it empty. Every run is a string of those characters, so when
each of them matches alone, every run decomposes. The day `shlex` gains a punctuation character this
table does not hold, that control fails — and a second control builds its own table without `&` and
drives a `&&` run through it, so the refusal itself is shown to fire.

### 1.2 §2's "A literal program is admitted only by declaration"

Too strong, in two places, both because an ADMITTING comparison normalized the name first:
`_judge_literal` stripped `.sh`, so `git.sh` matched the `git` declaration and was admitted at a
site that declares `git`; and `_judge_words` compared a path's BASENAME against the builtins, so
`/fixture/echo x` passed as the harmless builtin `echo` although the shell runs that file.

As it holds now: a declaration matches the program's exact basename with no suffix stripping, and a
builtin, a word that runs the next one and a shell are recognized in a shell line only as the exact
bare word. Normalization stays where it leads to a REFUSAL — a host written `claude.sh` is still the
host. Instrumented before the change: no call in the real tree stops being admitted.

### 1.3 §2's "A watched module is never a value", and the loaders

Too strong. The callable-as-value check asked only `spelled in EXEC_CALLS`, so
`run_file = runpy.run_path` and `load = importlib.import_module` passed while the direct call is
`DYNAMIC_LOAD_UNDECLARED`; and the module check admitted any watched Name that is the base of an
attribute access, which is exactly what `loader = importlib.util` is.

As it holds now: the direct-callee rule covers every `LOAD_CALLS` spelling, and an attribute chain
spelled as a watched module path (`importlib.util`, `concurrent.futures`, …) used anywhere but as
the base of a further attribute access is refused. An attribute of a watched module that is NOT a
module — `subprocess.PIPE`, `subprocess.TimeoutExpired`, `os.environ` — stays admitted, with a
positive control each. Instrumented before the change: zero real sites newly refused.

### 1.4 §2's R6 row

The row stood on a control whose decoy could not be admitted. The flagless plant put a BARE
`copied_member(...)` at outer element 5, and `_copy_member` admits only `str(copied_member(...))`,
so the decoy was refused under the new arithmetic AND under the whole old meaning; the revert
"failed" on the message's wording (`sys.argv[2]` against `[5]`), not on an admitted bad call. The
lead accepted that row in S9 without seeing it.

As it holds now: the decoy is the admitted form, a check asserts that the same element at the
position the program really loads from is admitted — so the refusal is about the INDEX, not the
form — and the control requires the refusal at the planted call's own line. Under the whole old
meaning the plant is admitted with no refusal at all, which is the defect the row is for.

### 1.5 §2's "A failing control keeps its own name … a string from anywhere else cannot leave unprojected"

The first half holds. The second is too strong and is now a named residual: `FailureLine` is a
MARKER, and `emit(FailureLine("…"))` prints whatever a caller deliberately wraps. What the type
rules out is a string reaching `emit` by accident; it is not proof of projection. The docstrings say
that now, and a check holds the one thing a check can hold — that nothing outside `runlib/entry.py`
constructs one — read as a tree, over sources a caller may supply so the check itself is shown to
fire.

### 1.6 §1.3's differential coverage

Too strong as a general claim. The differential compares withheld LINES, so a message that echoes a
FRAGMENT of a line — a table name without its brackets — passed it. The leak the round found was
invisible to every control in the package for that reason.

As it holds now: four malformed-carrier fixtures drive `emitted_document` and `write_document` and
are searched by SUBSTRING for a per-fixture canary. Two of them are real leak cases, with the
premise asserted — `carrier_decision` withholds the carrier whole, and the parser's own message
would have carried the canary: a TOML duplicate table, and a python carrier whose `SyntaxError`
names an identifier. The other two are regression carriers and say so: measured, neither `json` nor
tomllib echoes carrier text for a plain syntax error, so "the old message would have carried the
canary" is false for them and the fixtures do not pretend otherwise.

## 2. The blocking finding, and the sweep it came with

A reason derived from a carrier now carries no text taken from the carrier: a fixed category per
kind, plus the position where the parser exposes it as NUMBERS, read with `getattr` from
`lineno`/`colno` and omitted when absent — never parsed out of the message. The declared floor is
Python 3.11, where `TOMLDecodeError` has no such attributes at all, so the position is absent as
often as it is present. The path stays, as metadata, as before.

Every place a carrier's bytes or a parser's message can become an emitted string in package A was
read, seventeen sites in all:

| Site | What it carried | What was done |
| --- | --- | --- |
| `structured()` JSON, `structured()` TOML, `blocks_of()`'s splitter handler | the parser's message | category + numeric position |
| `layer_rows`' three handlers, `produce`'s two | those messages, transitively | fixed at the source; what remains is `Unsupported`'s fixed sentence and `Unacquired`'s own message, which names paths |
| `source_digests`, `checkout_copy` (three sites) | a `Refused` message, which names a masked path | left as is |
| `transcript_events` | an `Unacquired` message about a transcript: a path and a reason | left as is; the one place worth re-reading if transcript reading ever parses |
| `inventory_schema` (two sites) | a message about this repository's own schema file | left as is |
| three suite-internal sites | a control's detail, never an artifact | left as is |

## 3. The residual this record carries

**`forged_failure_line`.** `entry.emit` publishes without projecting and refuses anything that is
not a `FailureLine`, which keeps a string from reaching it by accident. It cannot keep a caller from
wrapping unprojected text in `FailureLine` deliberately. Reason: the type is a marker for this
module's own callers, and proving projection would mean re-projecting, which is the thing the
fallback exists to avoid — re-judging a withheld line in pieces publishes what the whole-line
judgement refused. **Reopens if** a `FailureLine` is constructed anywhere outside `runlib/entry.py`
(a check holds that today and fails by name when a construction is planted), or if `emit` gains a
caller outside the two report functions and this module.

## 4. The `head:` this record carries, and what its present tense describes

`head:` is `aa80bb1`: the base this record was written against, the tree round 5 reviewed and the
tree every finding was reproduced at, before S11 was committed. It is not the tree the statements
here hold at. Each present-tense sentence above describes the S11 code, which was checked in the
worktree and is committed as `171bf00` — a commit that did not exist when this record was written,
which is why the frontmatter cannot name it. Read the base from `head:` and the behaviour from
`171bf00`.

## 5. What this record does not establish

Round 5 was the last review; there is no round 6, so nothing here was re-reviewed. The five
reachable findings are the lead's rulings, each checked against the source and then reproduced or
re-measured before being changed — the TOML leak, the three punctuation runs, `git.sh` and
`/fixture/echo`, the loader and submodule aliases, and the R6 decoy's admissibility. The counts,
the sweep and the revert table are in the implementer's work notes outside this repository. No
control-audit was run for this step.
