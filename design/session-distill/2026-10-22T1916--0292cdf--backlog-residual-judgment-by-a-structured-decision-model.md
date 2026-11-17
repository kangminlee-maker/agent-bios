---
created_at: 2026-10-22T19:16:28+09:00
head: 0292cdf
kind: backlog
---

# Backlog: judging sweep residuals with a structured-decision model

## What it is
Jev is TypeSafe AI's first "System One" model (https://typesafe.ai/blog/introducing-system-one-models-and-jev,
read 2026-10-22). Per that page: a hosted model in early access through TypeSafe's API; it returns values
from a type declared in advance (classify, route, score, extract, verify), never free text, with calibrated
probabilities; 70-500 ms end to end; input $0.042 per million tokens, output free; choices above 255 values
unsupported. The page claims no secret, credential or PII detection, publishes no public-benchmark results,
and names no weights, size or licence.

## Where it could help
The residual sweep (`projection.py --sweep`) reports members whose key the floor calls a secret and whose
value the projection did not mask. Today the owner judges each one by hand (63 on 2026-10-22, all "no
secret"). A structured yes/no with a probability per member could triage that list.

## What must hold before it is tried
- No value leaves the machine. The question is asked of a shape only: key name, value length, character
  classes, and the surrounding text with the value replaced. Whether a shape-only question can be answered
  at all is the first thing to measure.
- A new network operation needs its contract in ENDPOINTS.md; the zero-egress default stays the default.
- Its verdicts are scored against owner verdicts before any is trusted. The 2026-10-22 set (63, all
  negative) was deleted with its values and is too one-sided to score a classifier on.

## Revisit when
The redesign has landed (after the WP-23 rehearsals), or a sweep leaves more residuals than the owner can
judge in one sitting.
