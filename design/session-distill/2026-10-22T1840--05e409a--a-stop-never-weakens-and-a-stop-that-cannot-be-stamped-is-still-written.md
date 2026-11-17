---
created_at: 2026-10-22T18:40:21+09:00
head: 05e409a
kind: review
supersedes: 2026-10-22T1725--2ebe9f9--a-check-that-reads-one-form-and-compares-another-is-not-a-check.md
---

# A stop never weakens, and a stop that cannot be stamped is still written

Round 4 of the dispatcher-seam review (`wp/06-dispatch-seam`, subject `05e409a`) returned two major
and three minor findings, BD#0–BD#4. This record supersedes the 1725 one because three of its
sentences were claims the code did not keep, and it says what is true now.

**The 1725 record said "an observed excess is never discarded", "an unstamped stop lifts for nothing,
so recovery is a new run", and that the amendment controls no longer depended on scheduling. All three
were overstatements.** The excess could still be discarded by any failure to read the declaration that
was not a named refusal - a file the process could not read, a declaration linked out of the run - and
once the file was readable again, nothing stopped the next dispatch. The unstamped stop did stop the
run, but only until another call, already running when the timeout happened, settled its own excess:
`_stop_run` wrote its entry over the unstamped one, and a `host_allowance` amendment then lifted a run
that should have ended. And the amendment control released its amender before the stop was even
called, so a schedule existed in which the intermediate state never appeared.

## What is true now

**BD#0 — a stop never weakens.** `bound.strongest(kept, offered)` decides what the ledger's one
`stopped` entry says, and `bound.terminal` says which stops nothing can lift: a code this rule does not
own, and a bound stop with no `declaration_seq`. A terminal stop already recorded is never replaced;
between two stamped stops the higher sequence stays, so recovery must pass the latest excess; an equal
sequence keeps what is already there. Each call still reports its own stop in its own call record -
`_stop_run` returns the entry it offered - and the run keeps the stronger one.

**BD#1 — any failure to read the declaration inside the stop path is an unstamped stop.** The handler
took `Refused` alone, which is what the reader raises for a drifted declaration; a `PermissionError`,
an `Escaped` confinement violation or a decode error escaped the stop with the excess already observed
and nothing written. It now catches every exception there, records the stop with
`stamp: declaration-unreadable: <the error>`, and the call is refused by name. Restoring readability
does not reopen admission, and no amendment lifts such a stop.

**BD#2 — the amendment control waits for the stop's own acquisition attempt.** `dispatch.STOP_ACQUIRING`
is set by the self-test to an event, and the stop signals it where it really asks for the declaration
lock. The amender holds the lock until that signal arrives and releases it only after writing its
run.json, so the stop cannot avoid finding the declaration mid-commit. In production the module
variable is None and nothing reads it.

**BD#3 — the adapter control is the production invocation.** The argv is `runner_argv` over the spec the
Supervisor builds, the environment is `Supervisor.runner_env` for that call - now the one owner of the
launch environment, used by `call` itself - and the cell, the working directory and the delivered
prompt file are the ones the dispatcher made. The fixtures are the host binary, which starts no model
and records what it received, and the homes, which are inside the scratch directory. Both forwarding
mutations stay, now applied to a copy the launcher is pointed at.

**BD#4 — a reverted producer reports its control instead of killing the suite.** The subject's presence
and key set are checked before the two hashes are compared.

## Closed alternatives

- **The last stop wins.** Ruled out. It is the rule that let a stamped stop replace the unstamped one a
  lock timeout had written, and with it a sequence a later amendment could pass. The kept entry is the
  stronger one, never the newer one.
- **Handling only the named refusal in the stop path.** Ruled out. The reader has one named failure and
  several unnamed ones, and the unnamed ones arrive precisely when the filesystem is against us - which
  is not a reason to forget an overrun that has already been observed.

## A known residual

The instruction comparison is made in the observer's form (BC#2), and that form is a normalization: it
strips HTML comments and collapses whitespace. So a change between the count and the send that the
normalization ignores - whitespace, a stripped comment - changes the raw length the bound counted
without producing any refusal: the observer-form hashes still agree. **This is not protected.** It is
recorded here as a residual, not as a property: the raw `sha256` and `bytes` in the record are the
bytes that were counted, and nothing compares them against what the host later read. Closing it would
mean either a second comparison on the raw form, which the host's own evidence cannot support, or
counting the normalized form, which would make the bound's arithmetic depend on one host's rendering
rule.
