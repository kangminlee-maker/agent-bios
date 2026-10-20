---
created_at: 2026-10-21T00:26:00+09:00
head: cc0498f
kind: design
supersedes: null
---

# Session distill: amendment to the window input bound (design §5.4)

This record amends one sentence of `2026-10-20T1942--9684f05--mechanism-design.md` (below: the
design), §5.4, by owner decision of 2026-10-21. Every other contract of the design stands.

## The sentence amended

The design reads: "Views are cut into windows bounded in tokens (input at most 120k, output
capacity reserved)". Four rounds of hermetic review of the implementation plan
(`2026-10-20T2119--cc0498f--implementation-plan.md`) found that this cannot be guaranteed before a
request is sent: neither host exposes a tokenizer, and the host adds content of its own to every
request — its system and environment text, request framing, retries — that the driver cannot count
in advance. A bound from sampled character ratios, and one from repeated minimal-call measurements,
were each shown not to cover that part.

## The amended contract

The sentence bounds **view windows**: the calls whose packet carries a window of a transcript view —
S3 reading and its expansion windows — and nothing else. Calls without a view window keep the
contracts of their own sections; the whole-library reconstruction of §8.6, for one, is bounded only
by its seat's context capacity (probe 7: about 136k input tokens, plus the host's warm-up request).

- **The driver's part is bounded before dispatch.** For a view-window call, the UTF-8 byte count of
  everything the driver supplies — the view window, the packet template, the schema, and any
  declared instructions — is at most 120k minus the seat's declared **host allowance**. Every token
  covers at least one byte, so this bounds the driver's part in tokens without a tokenizer.
- **The host's part is covered by a declared allowance and verified per call.** The allowance is
  measured per host version and flag set in preflight, declared in `run.json`, and re-measured on
  every host upgrade (the design's §14 checks). Every view-window call's observed input is compared
  with 120k after it returns.
- **An observed input above 120k on a view-window call is a host change.** It is recorded against
  the call, and the run stops — in rehearsal and in production — until the allowance is re-measured
  and the declaration amended. A single request may therefore exceed 120k by the host's unforeseen
  addition once; the run does not continue on that basis.
- **Output capacity stays reserved.** The driver's bound plus the allowance plus the output
  reservation must fit the seat's context capacity, checked before dispatch; a window failing
  either check is split.

## What this closes

A guaranteed pre-send bound over the complete request, which would need a capture of the host's
own request content in preflight and a re-capture on every host upgrade, is not pursued. The
harm of a request slightly above 120k is a single over-long read, not a wrong result; the stop on
observation keeps it from recurring.
