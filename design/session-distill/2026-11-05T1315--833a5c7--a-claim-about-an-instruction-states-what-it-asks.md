---
created_at: 2026-11-05T13:15:00+09:00
head: 833a5c7
kind: design
supersedes: null
---

# A claim about an instruction states what it asks, not only that it was given

WP-08, before merge. C1's S3 answer was judged by models of other families (D-20261104-9524bf, D-20261105-42188a).
Two items the first judge listed as missed were the owner's instructions and findings in unit 0. The S3 claims quoted
the same records (distance 0) but stated only that an instruction or a finding had been given: not what it asked,
under which conditions and steps, or how far it reached. The owner decided that this recall is fixed before WP-08
merges (D-20261105-385651). The other disputes in that judgement were settled in S3's favour and change no code.

## The change

`packets/read.md`, in the `claims` bullet, one sentence after the `call_id` instruction:

> A claim about an instruction, request, finding or decision states in `fact` or `interpretation` what it asks or
> decides, under which conditions and steps, and how far it reaches, as its quotes show; that it was given is not
> enough.

- It asks for fuller claims, not more of them: "one observation each" stands.
- "as its quotes show" keeps the sentence inside the packet's rule that what cannot be quoted is not claimed.
- No schema, check or field changes. The template grows by 236 bytes. S2 cuts windows against a fixed overhead
  (`bound.PACKET_OVERHEAD`, 12,288 bytes), not against the template, so no window moves. The read packet's fixed part
  is now 11,010 bytes, 1,278 under that overhead, which `packet`'s self-test holds.

## The control

`stage_read` self-test, "WP-08 C1 recall": every read packet a live leg sends (window and expansion calls of the dw2,
apart and twin fixtures) carries the sentence's five parts in its claims bullet. The bullet is taken from the task
part of the packet, after the payload marker and the last `# Your task` heading, so a transcript cannot supply it. The
control also requires that the packets it judges are exactly the calls the legs recorded, and more than none.

**The pretrial** (`c7/pt7-pretrial.py`, on a copy of the tracked tree):
- Unmutated, six suites passed: stage_read, packet, records, views, claims, evidence.
- With the sentence removed from `read.md`, the control failed by name. There were no other failures and no traceback.

## What the control cannot show

The control proves only that the sentence reaches every read packet. Whether a reader then writes fuller claims is
model behaviour, which no offline test can decide: the fake runner returns answers the fixture wrote, whatever the
packet says. The check is a live one: unit 0 of the C1 window is read again in a new run with this packet, and the
new answer is judged by GPT and Opus (D-20261105-385651). It is accepted when both judges find the two missed items
covered, and no new claim is found unsupported by both. Its result is recorded separately, after the run.
