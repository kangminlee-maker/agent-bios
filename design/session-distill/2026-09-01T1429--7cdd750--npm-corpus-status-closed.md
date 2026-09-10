---
created_at: 2026-09-01T14:29:52+09:00
head: 7cdd750
branch: main
kind: review
supersedes: 2026-09-01T1352--41b88a4--npm-corpus-status-final-boundary.md
---

# The npm corpus-status blocker is closed, verified on a packed tarball rather than a tree

Implements the design in the superseded record. Every claim below was re-derived from the
artifact; the design's own premises were checked against the code first, and one of them
would have introduced a worse defect than the one it fixed.

## Done-when, all six, against `npm pack --ignore-scripts` output

Run from the extracted package root into a HOME that began with no corpus status:

| # | Condition | Result |
| --- | --- | --- |
| 1 | installed corpus matches the requested selection | deployed, rc 0 |
| 2 | `selection.json` holds the requested closed set | `["office-work"]` |
| 3 | `corpus-status.json` newly generated, same available/applied | available 5, applied `["office-work"]` |
| 4 | `last_apply` records `applied` for that set | `{requested: ["office-work"], outcome: "applied"}` |
| 5 | author-only version/ledger labelled unavailable | `versions: null`, `summary: null` |
| 6 | non-zero when a required status write fails | rc 1, `Done.` withheld |

`compose/corpus-state.py` is in the tarball; `gates/`, `ontology/` and
`design/session-distill/` are not.

## The correction the design needed

The design required `install`/`onboard` to fail without a readable status. Returning at the
projection would have done that and been worse: the projection runs AFTER the corpus is
deployed, and a non-zero return there fires the EXIT trap, which restores the PREVIOUS
manifest — new corpus on disk, record naming the old one. `install.sh:96` already carried
that lesson from a different cause.

So the failure is deferred. The manifest is completed first, then the command exits
non-zero, and `Done.` is withheld — the files, the record, and the exit code each say
something true. `PROJECTION_FAILED` carries it across.

## Why two fixtures and not one

The two silences were independent, so one failure case cannot prove both. Reverting each
was measured:

| Reverted | I17 (10 checks) | I18 (4 checks) |
| --- | --- | --- |
| `project` stderr/status suppression | **3 fail** | all pass |
| `record-apply` success-path `\|\| true` | all pass | **2 fail** |

I18 also asserts its own fixture reached `record-apply` through a PASSING canary. Without
that, both of its behavioural assertions would pass equally well if the canary had failed
first — which is I9's case and says nothing about the apply record.

Suite 104 -> 118.

## Two instrument errors caught before they became claims

- `record-apply` appeared to return 0 with no status file, which would have made the new
  strict check vacuous. The 0 was the exit status of `head` at the end of a pipe. Unpiped
  it returns 1, so the check is live. A hole was nearly reported that did not exist.
- A first draft of I18 asserted the absence of `ONBOARDING COMPLETE`, a string `install.sh`
  does not contain. It would have passed forever while testing nothing.

## What this does not cover

The success-path canary in both the suite and the tarball run is a stub echoing the
bundle's real rev marker. It exercises the canary's pass branch; it does not prove a live
model loads the bundle. That verification stays where `compose/canary.sh` puts it, against
an authenticated session, and the desktop plan must keep its own live-surface check
separate — Codex CLI and a ChatGPT desktop task are not covered by the Claude probe.
