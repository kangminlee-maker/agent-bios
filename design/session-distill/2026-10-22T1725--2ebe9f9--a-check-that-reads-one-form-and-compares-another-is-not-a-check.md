---
created_at: 2026-10-22T17:25:12+09:00
head: 2ebe9f9
kind: review
supersedes: 2026-10-22T1556--9602bff--a-declaration-the-host-never-receives-is-not-a-declaration.md
---

# A check that reads one form and compares another is not a check

Round 3 of the dispatcher-seam review (`wp/06-dispatch-seam`, subject `2ebe9f9`) returned four major
and three minor findings, BC#0–BC#6. This records what they closed. It supersedes the 1556 record
only where it changes something; the one-owner bound, the declared capacity, the delivered prompt and
the adapter's declared reach all still hold as that record describes them.

Two of this round's findings are the same mistake in different places: a check that looks at one
representation of a thing and compares it with another. The declared instruction hash was the file's
raw bytes while the capture carries the file as the host renders it, so an unchanged file failed.
The adapter-capability controls looked at the wrapper's text while the claim was about what the
wrapper delivers, so deleting the parser left them passing. The third is its cousin: a control whose
fixture did not exist, comparing nothing with nothing.

## What was wrong, and what it is now

**BC#0 — a lock timeout discarded an observed excess.** `stagelock.hold` raises after its wait, and
the raise left `ledger.stopped` unwritten while the call had already been charged: the overrun was
observed, recorded nowhere, and the next dispatch was admitted. **An observed excess is now never
discarded.** The wait stays bounded - an unbounded one would hang the dispatcher behind any holder,
which is worse than an unstamped stop - and when the lock cannot be taken, or the declaration it
guards cannot be read, the stop is written under the ledger lock alone with no `declaration_seq` and
a `stamp` naming why (`lock-timeout: …`, `declaration-unreadable: …`). By the existing recovery rule
an unstamped stop lifts for nothing, so later dispatch stays refused and recovery is a new run, not
an amendment. The call still fails by name. The BB#0 controls no longer sleep for their window: the
amendment and the stop hand each other the turn through events.

**BC#1 — a path-backed part was still read twice.** `part_snapshot` called `part_body` and then
`part_bytes`, which read again; a source that answered differently the second time produced a
snapshot whose hash and length came from different bytes (it failed closed one step later, but the
single snapshot BB#1 claimed was not there). The asserted length is now judged by
`asserted_length_problem(part, body)` against the body already read, so one `part_body` call is the
whole read. A control counts the reads, and a second control answers with different bytes on a second
read that never happens.

**BC#2 — raw hashes were compared with normalized ones.** The producer recorded
`sha256(bytes)`; the Claude observer records `norm_sha256(content)`, the file as the host renders it
(trailing newline trimmed, HTML comments removed, whitespace collapsed). For an ordinary instruction
the two differ, so the gate's own `effective_context` emitted `CONTEXT_HASH_MISMATCH` for a file
nobody had touched - and the existing control had supplied two matching synthetic hashes, so it saw
none of this. The record now carries both forms: `sha256` and `bytes` of the exact bytes the payload
count counted, and `observer_sha256`, the same bytes through the observer's **own** function, loaded
from `wrappers/claude_hermetic_evidence.py` by `gate.observer_sha256` rather than copied. The gate
compares the observer form (`gate.declared_instruction_hash`), falling back to `sha256` for a record
written before this existed. The controls run the real transformation on both sides, and a third
control fails if the fixture's two forms are equal - otherwise the pair would pass without any
translation at all.

**BC#3 — content plus a path bypassed the content-only rule.** The body and text branches returned
before the path check, so `{"text": …, "path": …}` was admitted and recorded with a `path` the call
schema rejects, discovered after the launch. A `path` **field** on an appended prompt is now refused
before any content is chosen, whatever its value.

**BC#4 — the legacy-compatibility control had no subject.** It read a fixture file that does not
exist, substituted `{}`, and never called the validator (it would have raised `NameError` if it ever
had). The legacy envelope is now built from the record the dispatcher just wrote by removing what the
seam added; the control fails if its subject is missing, and a second control compiles the schema with
`bound` required and requires that same record to be rejected - so the control is known to be able to
fail.

**BC#5 — `bound.py`'s controls ran in no gate.** They had moved out of the view side's suite with the
rule and nothing invoked them. `gates/check-parity.sh` now runs `bound.py --self-test` beside the other
runlib legs.

**BC#6 — the adapter's capability was asserted from its text.** `flag in script` passes while the
parser is deleted. The wrapper is now **run**: against a fake host binary that starts no model and
records what it received, with a fixture token and no network, and the controls assert the received
`CLAUDE_CODE_MAX_OUTPUT_TOKENS` and the appended-prompt argument with its bytes. Two copies of the
wrapper, each with one forwarding behaviour removed, must lose exactly that and still reach the host.

## Closed alternatives

- **An unbounded wait on the declaration lock.** Ruled out. It would make every bound excess wait on
  whoever holds the declaration, turning a recoverable stop into a hung dispatcher. The bounded wait
  plus an unstamped stop is the trade: the run ends, and only a new run continues the work.
- **Comparing a raw hash with the observer's normalized one.** Ruled out, in both directions: the raw
  hash is kept, because it is what the payload count counted and what the delivered bytes hash to, and
  it is not what the comparison uses. Normalizing the count instead would have made the bound's
  arithmetic depend on a rendering rule that belongs to one host.
- **Asserting a capability from the adapter's source text.** Ruled out. A flag name survives in help
  text, comments and error messages after its parser is gone, which is exactly how these controls
  passed a planted deletion.
