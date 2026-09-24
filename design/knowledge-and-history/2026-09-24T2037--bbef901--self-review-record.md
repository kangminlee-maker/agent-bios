---
created_at: 2026-09-24T20:37:49+09:00
head: bbef901
kind: review
plan: 2026-09-24T0740--a0e289e--development-plan.json
corrects: 2026-09-24T0616--9b26d79--successor-bundle-record.md, 2026-09-24T0920--65b3057--refreeze-record.md
decisions: D-20260924-f63e31, D-20260924-b5fdb5, D-20260924-f8da36
---

# Self-review: the driver's verdict sat outside the freeze it was frozen with

The owner asked for every judgment since the 05:53 successor bundle to be re-read for mistakes.
Each was checked again against the code, the plan and the decision ledger rather than against
the records that reported it. The one design question that decides the next stage — where a
family case's verdict is computed — went to a blind judge given the files and three neutral
alternatives, with no conclusion attached. That judge was **same-provider**: the cross-provider
seat refused on a usage limit until 2026-09-29 and returned nothing. Its agreement is an absence
of objection from one model family, not independent verification. Its full answer is kept with
the run evidence, `review-driver-design-20260924/judge-result.md`, and each of its factual claims
used below was re-checked against the files.

## Three judgments were wrong

**The driver's verdict route (`a0e289e`, `D-20260924-fef65b`).** The driver took a family case's
verdict from a test named in a `CASES` map inside the module the catalog gives for that family,
such as `gates/workenv/test_identity.py`. That module is in no part of any binding.
`gates/workenv/cases.py` says so in as many words: "An implementation, a host version or a unit
test is in neither" fingerprint. It is also in no subject, and in no node's `owned_paths`. So the
bytes that decide a verdict could change and no frozen value would move. The freeze exists to
prevent exactly that. No code executes any `scenario.json` either: the scenario bytes are hashed
into the fixture fingerprint and never run. Three decisions from 2026-09-22 already give scenario
execution to the driver:

- `D-20260922-e5fdae`: the world section.
- `D-20260922-e48992`: given answers for steps outside the profile.
- `D-20260922-61e94c`: signing with the driver's own keys at run time.

`scenarios.py` states all three in the present tense. `fef65b` was designed without reading them.
The judge rated the route a blocker. Superseded by `D-20260924-f63e31`.

**The 09:20 re-freeze (`bbef901`) was premature.** It took the shared work to be finished while the
driver still owed everything above. The driver has to change again, which moves 23 of the 25
bindings again, so a further P01 re-run and bound review were certain from the start.
`D-20260924-f8da36` makes the next re-freeze the only one before the driver executes scenarios.

**The drift detector was not automatic.** The owner chose automatic detection
(`D-20260924-d53e9f`). The tool shipped with nothing running it: neither its comparison nor its
self-test. The 09:20 record and `CURRENT.md` said the drift "now" discloses. Its controls now run in
the parity umbrella, and the comparison moves to where a node is recorded (`D-20260924-b5fdb5`).

## Three statements were stronger than their evidence

- **The 06:16 record overstates independence.** It says the blind SSOT reader "reached the same
  reading of the *Complete operation contracts* header independently". It did not. The packet that
  reader was given (`successor-bundle-20260924/blind-review-packet.md`) told it that "a table whose
  own header declares its rows in design scope regardless of implementation, is NOT stale". The
  reader applied a reading it was handed. The rest of that review — S13 carrying all ten removals,
  and no stale scheduled work for the four features named there — is unaffected. The same claim
  was made to the owner in conversation and is withdrawn there too.
- **The 07:40 spec narrows the S11 header.** The header asks for two things from a backend not yet
  implemented: "a truthful unsupported state and implementation acceptance". The spec (lines
  31–33) keeps the first, drops the second, and adds "not an implementation". This will be
  corrected in the successor spec published at the next re-freeze. A spec successor moves the plan
  digest, and that re-freeze re-records P00 and P01 anyway, so both happen in one step.
- **`CURRENT.md` labelled the SSOT "2026-09-15 10:26 KST"** while linking the 05:53 file. The label
  is corrected with this record.

## Smaller defects, kept for the next change that touches each

- **Attempt ids.** `run-3` and `run-5` both record P01 as `team-env-20260923:attempt-1`, though
  they are different attempts a day apart.
- **`cases.py` docstring.** It says the adapter fingerprint moves with "the driver path". The code
  hashes the driver's bytes, which is stronger than the text says.
- **`binding-drift.py` docstring.** It hardcodes "23 of the 25" as if it were a property rather than
  one measurement.
- **Review packet builder.** It still names the evaluator from the plan's stamp. The 09:20 record
  already noted this.
- **Unbound code in the verdict process.** The driver runs (`exec_module`) a module that is not in
  any fingerprint, inside the process that produces the verdict. This goes with the route that
  replaces it.
- **Joined cases.** A joined case's verified member map reaches only the driver's report, never the
  thing that judges the case.

## What held

The reasoning behind each of these was re-checked and stands:

- The successor SSOT was published before P02.
- P00's minimal three-field re-record.
- `0740` was published instead of editing the committed `0553` spec.
- The rejection of the `N15` misreading.
- Asking the second spec read about omissions as well as additions.
- The re-freeze mechanics. Only the decision to re-freeze at that time was wrong.

## Where this leaves the graph

The evaluator's answer is unchanged: accepted `["P00", "P01"]`, ready `["P02", "P03", "R0"]`.
`ready` is not a reason to start P02. Its cases cannot pass until the driver executes scenarios.
An implementation node recorded against the present freeze would carry a binding the tree no
longer emits. The next stage is the adapter contract, which is how the driver reaches an
implementation and what P01 freezes as its "adapter selectors". Then the driver's scenario
execution. Then one re-freeze, together with the spec successor.
