---
created_at: 2026-08-21T13:30:00+09:00
head: fa03c7b
kind: design
supersedes: none — the fix-delta portion of 2026-08-21T1117--07ff218--wrapper-review-round1.md
---

# The findings were symptoms; this is the mechanism that produced them

User direction, 2026-08-21: *a finding is a phenomenon, not a result.* Patch the
phenomenon and the fix delta produces the next one — which had already happened
twice in this initiative before the instruction was given.

Round 1 produced nine findings and a tenth defect from its own fixes. This record
is not about those ten. It is about why they were possible, and what changed so
that class stops being available.

## Phenomenon A — assertions that could not fail

Four in one session: the gate's decoy fixture the resolver cannot read (#6); an
E2E grep for a word the command never prints; a wrapper E2E that passed because
`node_modules/agent-bios` symlinked the working clone instead of the declared
pin (#1); an isolation probe that passed a path to a gate which ignores its
arguments and re-measured the real repo.

**The mechanism already existed.** `gates/control-audit.py` removes one failure
statement at a time and asks whether the gate's own `--self-test` notices — the
exact question. It never ran here, and not by oversight:

```
gates/check-endpoints.py: 47 failure statements
control-audit SUBJECTS:   7 gates, this one absent
check-endpoints --self-test: 133.61s real, 10.23s user, 7.34s sys
```

47 × 134s ≈ **105 minutes** to audit one gate. So it was left out of `SUBJECTS`,
so the gate was never audited, so an assertion that could not fire survived into
a merged branch. The chain closes on cost, not on discipline.

And the cost had one source. Per gate run: `leg_wire` 1.74s, every other leg
0.09s **together** — the wire leg stalls a handler 1.2s on purpose, to prove the
client's socket timeout reaches the wire. A real assertion, worth paying once.
The self-test paid it 70 times by re-running the whole gate for every planted
mutation.

### The response

Legs became addressable (`collect(root, legs)`, `run(root, legs=…)`), and each
planted mutation now **declares the legs that must catch it**. The cheap four
always run; `wire` runs only where declared.

```
before: 133.61s   after: 46.62s   (and 73 controls now, up from 69)
```

The same change carries the property review asked for, which is the point:
declaring reach means a control states which assertions it pins, and
`_expect` fails when the caught set differs from the declared one — naming the
leg that went quiet. Demonstrated by neutering one paired assertion in a copy:

```
FAIL: [live method flipped] declares ('anchors', 'wire') but was caught by
('wire',); ['anchors'] went quiet — its assertion no longer has a control
```

Then `gates/check-endpoints.py` went into `control-audit.py`'s `SUBJECTS`, and
the audit ran for the first time:

```
control-audit: 29 check(s) covered by a control, 19 uncovered
```

Nineteen checks in this gate had nothing that would notice their removal. Most
are non-vacuity guards, which no ordinary mutation reaches by design — the tool
says so itself. Four were substantive contract claims and now have controls: the
drain's live budget and socket timeout drifting from their declared constants,
a default skip that gives no reason, and the doc dropping a settle status the
code enforces.

**What is now impossible rather than discouraged:** adding a check to this gate
without a control still passes, but the count moves and the audit names the line.
A control that silently covers two assertions does not pass at all.

## Phenomenon B — fail-open at a trust boundary

The wrapper's provisioning failure was `|| true` in the shell and `return 0` in
Python: not a decision to continue, but the absence of one. Every failure mode
added later would have inherited it — and one already had, since a crash from a
mismatched core pin took the same path as a missing token.

### The response

`Refusal.blocking`, defaulting to **True**. Exactly one condition is benign and
it is named in the code: no token available AND no slot naming another endpoint.
The forwarder stops on any non-zero. A new failure mode inherits "stop" without
anyone deciding it should.

## Phenomenon C — a restatement with no generating relationship

`ontology/instances/graph.json` §lexicon — the *declared authority* for the
endpoint concept — still said the slot "wins over the legacy dashboard-owned hook
dir" after the fallback was deleted, with every gate green.

Asking the repo's own tool why:

```
$ python3 ontology/impact.py learn/collect-learning.py
nothing in the ontology anchors to 'learn/collect-learning.py'
```

The resolver is anchored to no entity, so changing it obliges nothing. The
disclosure was already printing `unmapped` on every `--diff`.

### The response

The concept text no longer restates the resolution rules; it names the slot and
points at `ENDPOINTS.md` for behavior. A surface that cannot drift beats a gate
holding a copy — `AGENTS.md` §Where authority lives says a gate with its own copy
of a value is a third restatement, not a guard.

The missing anchor stays open **deliberately**: adding an ontology entity is the
deepening loop's work (settle → classify → decide), and `AGENTS.md` is explicit
that a commit must never wait on a round of semantic judgement. It is recorded
here as a G1 coverage gap, not fixed in passing.

## What this round did not do

- The 15 remaining uncovered checks are disclosed, not closed. Under the
  ratchet, each needs a control or an `unguarded-accepted` decision with its
  reason; neither has been recorded yet.
- `gates/check-hygiene.py` and `gates/check_parity.py` are still unaudited — they
  ship no `--self-test` for the tool to consult. Named here because an audit that
  covers two thirds of the gates reads like one that covers all of them.
- The umbrella's own runtime is untouched at the structural level. It should drop
  substantially — every nested `install.sh verify` runs this self-test — but the
  next commit's hook is the measurement, and no figure is claimed here.
