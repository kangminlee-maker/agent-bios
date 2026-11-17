---
created_at: 2026-10-22T08:53:00+09:00
head: d1ca7bb
kind: design
supersedes: 2026-10-22T0831--9c24824--the-spelling-set-is-a-closure-not-a-pipeline.md
---

# A fixture that passes either way tests nothing

Fixture-only round. `projection.CURRENT` stays `r22`; no projection behaviour changed, so no stored
evidence is invalidated and no version is bumped.

## AE#0: the credential fixture did not test case preservation

AD#0's point was that the invisible characters were stripped only inside the **casefolded** skeleton,
so a case-sensitive detector never saw a stripped, case-preserved spelling. The fixture written for
it used `sk-abcdefghij<ZWSP>klmnopqrst`, and `sk-[A-Za-z0-9_-]{16,}` matches its casefold just as
well. The row therefore passed with or without the case-preserving step: it asserted a refusal that
was happening for a different reason.

The floor has a pattern whose required prefix does not survive casefolding — `AKIA[0-9A-Z]{12,}`.
The new row is `the key AKI<ZWSP>A0123456789ABCDEF was used`: only a spelling that is
invisible-stripped **and** case-preserved reaches the floor with it.

The property is asserted of the floor itself, before any boundary is asked, rather than assumed of a
pattern that could gain an `IGNORECASE` flag later:

* the floor claims `AKIA0123456789ABCDEF`;
* the floor does **not** claim its casefold.

Both assertions fail by name if either stops holding, so the day the floor's pattern changes, this
fixture says it has stopped testing what it claims instead of passing quietly.

## Proof, as asked

On a copy, the case-preserving strip step was removed from `vf_transforms` and the casefolded one
left in place:

```
evidence --self-test [FAIL] an invisible character inside a case-SENSITIVE credential:
    make built a record for a quote that names a secret
... an independently built record was stored into new30.jsonl / populated.jsonl
```

Under the same mutation the old `sk-` row stays **silent**, which is AE#0 restated as an experiment.
The floor-property assertion was proven the same way, by giving the `AKIA` pattern an `IGNORECASE`
flag on a copy:

```
evidence --self-test [FAIL] the floor claims the casefold of 'AKIA0123456789ABCDEF' too,
    so that fixture passes without case preservation and tests nothing
```

## A trap this round paid for: a stale `.pyc` can shadow a restored file

Reverting by file copy and re-running within the same second leaves a `__pycache__` entry that
Python still considers valid — timestamp invalidation records the source mtime at one-second
granularity, so mutate → import → restore inside one second produces a byte-code cache for code that
is no longer on disk. It cost a confusing minute here: `learn/redact.py` was restored, `git diff` was
empty, and the compiled pattern still carried the mutation's `IGNORECASE` flag.

It matters for *any* revert of an imported module, which is every file but the one run as
`__main__`. The rule to follow:

```bash
find session-distill learn -name __pycache__ -type d -exec rm -rf {} +
```

before each run of a revert experiment, and again after restoring. The reverts in this record were
re-run that way, so their attribution is clean. Worth considering for AGENTS.md's trap list — the
lead's call, since that file is not this lane's to edit.

## Residuals

| Shape | Found | Status |
| --- | --- | --- |
| a comma-prefixed remainder carrying a separator but not a validated member (X#6) | round 12 | open by instruction |
| an unreadable structure class, 63 cases | round 15 | pending the owner |
| a secret name written with cross-script lookalike letters | round 19 (anticipated) | out of scope by owner decision, 2026-10-22 |
