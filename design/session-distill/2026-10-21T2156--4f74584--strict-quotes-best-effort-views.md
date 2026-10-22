---
created_at: 2026-10-21T21:56:00+09:00
head: 4f74584
kind: design
supersedes: 2026-10-21T2127--27f72ed--keyed-rule-is-a-line.md
---

# The requirement splits by where the text goes: strict for what is stored and shared, best effort for a view

Owner decision of 2026-10-21, about 22:00 KST, after ten review rounds in which every round found a
new shape at the view level. It keeps everything the superseded record states about the projection
and the verifier, and adds a second, stricter rule for one surface.

## The decision

**Strict and blocking - anything persisted for sharing.** That is evidence quotes.
`projection.evidence_quote_admissible(quote)` is wired into the evidence store's admission path, at
both boundaries: `evidence.make`, where every record is built, and `evidence.append`, where text
becomes persisted. A quote that in any spelling - raw and at every decode depth the verifier reaches -
holds a secret-named token, a floor match or an owner path is refused by name,
`EVIDENCE_QUOTE_SENSITIVE`. There is no masking and no partial acceptance: the quote cannot be stored,
and the caller quotes a span that does not name a secret.

**Best effort - model-bound views and the local index.** The r15 projection and its verifier as they
stand. A new keyed-fragment shape found at the view level is a tracked residual from now on, not a
blocker.

## Why it splits

The two surfaces differ in what a mistake costs. A window is bound to the session it was made from:
its content already went to the same providers when that session ran, so a shape the verifier misses
in a window discloses to a reader who could already read it. A quote is different in kind - it is
lifted out of its block and carried into a report, where the context that made `"password":
"<REDACTED>"` a correct and useful thing to READ does not travel with it. Quotes are also short and
few, which is what makes a strict rule closable at all: it can refuse outright, where a projection
must still produce something readable.

Ten rounds of view-level findings is the other half of the reason. Each was real and each was local;
none of them was the last one. A rule that blocks on every one of them does not converge, and the
evidence of ten rounds is that it would not have.

## What this closed

- **Blocking acceptance on every view-level keyed shape.** Ten rounds of evidence that the list does
  not end, against a disclosure that reaches a reader who already had the session.
- **Blanking every block that carries a secret-named token.** Measured at the time of this decision:
  it would have replaced a large share of ordinary tool output with a placeholder, and a window
  nobody can read is a stage nobody runs.

## Tracked residuals

Shapes found at the view level and their status. A fixed one carries its own control; an open one is
a residual, not a blocker.

| Shape | Round found | Status |
| --- | --- | --- |
| A readable structured value in a fragment keeps its key association, every leaf checked | 14 (V#0) | fixed, controlled |
| What follows a quoted scalar is not the scalar's; nothing stripped from inside one | 14 (V#1) | fixed, controlled |
| A quoted key whose separator stands after a newline | 14 (V#2) | fixed, controlled |
| A structure whose extent genuinely cannot be read, under a secret-named key | 9 onward | open - the owner-pending structural class, unchanged by design |
| A value region whose remainder begins a further member of the same object | 14 | deferred to the member rule, which reads those members as members |
| Any further keyed-fragment spelling | - | residual: tracked here, not blocking |

## What it costs

The projection, measured on a local sample of 60 session files and 142,551 projected blocks:
**114 blanked blocks, 0.080%** - 112 for the keyed fragment and 2 for the floor.

The strict quote rule, measured over the 25 projected blocks of this branch's downstream fixture
transcript, each offered whole as a quote: **5 refused, 20 admitted** - three for naming `password`,
one `api_key`, one `secret`. The mask itself is admissible, which is what the existing controls quote.
Re-measure both before quoting them.
