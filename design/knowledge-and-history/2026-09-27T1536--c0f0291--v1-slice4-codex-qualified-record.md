---
created_at: 2026-09-27T15:36:08+09:00
head: c0f0291
kind: design
supersedes: 2026-09-27T1408--365a6f2--v1-slice4-probing-record.md
plan: 2026-09-26T1404--f065835--development-plan.json
decisions: D-20260927-f05a86
---

# V1, fourth slice, second increment: Codex's routes qualified after the person's review

[The 14:08 record](2026-09-27T1408--365a6f2--v1-slice4-probing-record.md) left Codex's new and
current routes refused until the person reviewed the probe's hook in Codex's `/hooks`. The person
reviewed and trusted both hooks. This record is what probing found after that, and the change it
forced in how a probe asks. Everything else in the 14:08 record stands.

## What the probes found

1. **The installed Codex had moved to 0.157.1** (installed 15:28 KST, when the person opened
   Codex to review the hooks). Probing 0.156.1 answered `unreachable`, "The installed codex is
   0.157.1, not 0.156.1", on each of its declared routes, and qualified nothing. The version rule
   held on a real update.
2. **On 0.157.1 the hook ran and the recipient still did not answer.** Codex listed the probe's
   hook as trusted and enabled, both `UserPromptSubmit` hooks ran (the person's and the probe's),
   and Codex added the hook's text to the session as a developer message. Asked to repeat the
   line, the model answered "I can't disclose hidden instructions." The route worked; the way of
   observing it did not.
3. **A probe now asks the recipient to act on what it was handed** (`D-20260927-f05a86`). The
   hook hands a random code with the instruction to give it when asked, and the recipient is asked
   for the code. By hand on Codex 0.157.1, the new and current routes answered the code, and each
   answered NONE when the hook handed nothing. The method is the same on every host.

## Used on this machine

The same direct use as the 14:08 record, on a fresh state root, with the new method:

| Host | new | current | child | rehydrated |
| --- | --- | --- | --- | --- |
| Claude Code 2.1.283 | worked | worked | worked | worked |
| Codex 0.157.1 | worked | worked | unsupported | unsupported |

- Each Codex probe recorded seven hooks, the probe's among them, enabled.
- After probing, a delivery to the current Codex conversation was received, and a delivery to a
  Codex child was refused `child_route_unsupported`, because no child route is declared.
- The Claude Code deliveries, the observations and the activation behaved as in the 14:08 record.
  The whole run took 50 seconds.
- As before, the delivery attempts were submitted by the script, standing in for the hook. The
  hook answering a host event with bodies is the third increment.

## How it was checked

The unit tests use the new method: the fake host gives a code only when the hook handed one, and
its stale mode gives a code it made up. 48 probe and adapter tests pass. The sweep gained two
reverts (the code handed without its instruction, and the instruction replaced by a line to
repeat), and all 58 reverts are caught.

## Next

The third increment: the hook answering a host event with the bodies an activation returns, and
a real delivery to a Claude Code and a Codex session. Then slice five, the P01 re-freeze and V1's
acceptance.
