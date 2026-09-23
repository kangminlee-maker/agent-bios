---
created_at: 2026-09-23T09:50:00+09:00
head: 1ba4dcd
kind: review
supersedes: 2026-09-23T0606--ab6818a--design-validity-review.md
---

# R1 was a misreading: the recipient pair is withdrawn

The 06:06 review recorded R1 — that C06's "a later use or a child recipient is admitted on
its own" was stated three times and enforced nowhere — as a real gap, after a cross-family
check overturned the rebuttal that had dismissed it. Work then went into closing it: an
optional `recipient` on `admitted_use`, an optional `recipient_kind` beside C03's existing
`recipient_digest`, a runtime rule comparing them, and thirty of the thirty-one admissions in
the scenario set filled in. All of it is reverted at this head. R1 itself was the misreading.

## What the sentence means

"Admitted on its own" says the admission record covers one use id and nothing else, so a
later use, or a session started under this one, gets a record of its own. It does not say the
person is asked again. Those are separate: whether admitting asks follows the mode the person
chose with their answer — C11's `keep_until_change` or `ask_each_use` — not the session the
request comes from.

The module's doctrine sentence now says this. The schema description
(`c06_reader_result` `admitted_use`) was left as it stands; "this one covers nothing else"
already carries the record-scope reading, and the module is where the doctrine lives.

## Why the fix could not work

Three findings, each from the artifacts:

- **It cannot tell apart what it was built to tell apart.** The pair was
  `(recipient link digest, host_session | child_session)`. Two sibling sessions started under
  one session share the link and both spell `child_session`, so both carry the identical pair.
  Demonstrated by running the oracle on a constructed example (cross-provider check,
  gpt-6-astra/max, which reached this independently and chose neither offered alternative).
- **C11 forbids the anchor.** "A destination says where to ask and nothing more: no
  preference, use or choice is keyed by one."
- **A frozen case says the opposite.** DC-KEEP: "a new session is not a reason to ask again"
  and "a new link is no more a reason to bypass the source's current rights than it is a
  reason to ask again." The rule would have refused an admission whenever the link differed.

What the product already does instead: a child reader holds its own access handle derived
from its parent's (C02, with `child_handle_carries_its_parents_generation` checking it);
N15-C11-POS shows a child session receiving a preparation under its own use; and a child a
route cannot deliver to is `child_route_unsupported`.

## The question that was raised and closed

Under `keep_until_change`, a session started for isolation inherits the kept application as
readily as one started to continue the work. Whether the contracts should distinguish the two
was put to the owner and closed: inheriting a decision is a consequence of inheriting context,
which the caller settles when it composes that context. A session given no context holds no
decision to apply; one given the context holds it. The contracts gain no spelling for it.

Both rulings are in the ledger: `D-20260923-72ff7b` (the pair is withdrawn) and
`D-20260923-8c69ac` (the product will not model why a session was started).

## What this leaves of the 06:06 review

The other findings of that review stand as written. R1 is the only one withdrawn. The two
instruments it added — the generator's `delivered()` check and the entry-point identifier
gate — and the `extend_supplied` removal were separate changes and are unaffected; they are
committed at `ab6818a` and `c03993a`.

Two things found while the fix was in flight are worth keeping, though nothing in the tree
holds them now:

- An audit over the generated scenarios (every `reader_result` that admits a use, against the
  link record its recipient named) found one scenario naming a link that routes to a different
  person than the one who asked. It was in the reverted work only. The shape of that audit —
  resolve a digest to the record it is of, then ask whether the two agree about who — is worth
  rebuilding if a later change puts an identity on a record.
- CAP-08 holds the one admission with no C11 record anywhere in its scenario. Any future rule
  that requires an admission to name something delivery-side has to answer for it first.
