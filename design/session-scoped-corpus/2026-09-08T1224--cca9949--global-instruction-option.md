---
created_at: 2026-09-08T12:24:00+09:00
head: cca9949
kind: handoff
---

# User-global instruction choice

Implemented in the working tree, not committed, published, or installed into the
user's live launcher. The default remains inclusion through the native loader.
Claude exclusion is implemented and exercised. Codex exclusion is explicitly
unavailable; this is a disclosed host boundary, not full cross-host completion.

## User-visible contract

Custom exposes **My global instruction files → Include / Exclude**, localized in
English, Korean, and Japanese. `--exclude-global-instructions` seeds the visible
choice for that invocation; the final Custom choice is what is saved and run.
The existing preset/plan/pin carries one boolean, `include_global_instructions`.
Missing fields mean true; default serialization adds no field. Excluded managed
sessions retain their choice on resume. A resume-time flag override is refused.

| Launch | agent-bios session content | Existing user-global documents | Project instructions |
| --- | --- | --- | --- |
| Native CLI / Software Engineer Vanilla | None added | Native loading rules | Native loading rules |
| Activated, Include (default) | Selected snapshot | Native loading rules | Native loading rules |
| Activated Claude, Exclude | Selected snapshot | Global CLAUDE.md/imports and user rules omitted | Native loading rules, excluding ambiguous shared-file paths |
| Activated Codex, Exclude | No launch | Explicit unsupported error | No launch |

The private installer does not rewrite global documents. Existing files are not
silently cleaned up: a legacy global deployment needs the separate, explicit
migration flow. Vanilla's zero injection does not remove content a native CLI
already reads from such legacy files.

This choice controls automatic instruction loading, not tool file permissions,
project memory erasure, enterprise policy, or removal of text already present in
a conversation. Native configuration, authentication, tool registrations, and
permissions are retained. Language catalogs describe the choice for people and
do not alter model-consumed corpus text.

## Runtime mechanism and rejected route

Claude 2.1.263 receives one per-call `--settings` JSON with `claudeMdExcludes`
covering its native global `CLAUDE.md` and user `rules/**`. Native configuration
arrays union across settings sources; repeating CLI `--settings` is last-wins.
The adapter therefore refuses an existing CLI settings argument rather than
overwriting or interpreting arbitrary user settings. Relative/empty homes,
symlink ambiguity, glob metacharacters, and detected project/global aliases
are refused. Default inclusion adds neither this setting nor a version probe.

Codex 0.153.4 exposes no selective user-global document switch in the inspected
CLI/schema. A controlled macOS deny-read prototype removed the global canary
from real `debug prompt-input` while keeping project/config canaries. But native
`codex sandbox -- /usr/bin/true` changed from exit 0 to exit 71 under that outer
sandbox (`sandbox_apply: Operation not permitted`). The FRONTIER review's
preserve-native-permissions condition therefore rejected the route. No OS
wrapper, native CLI patch, redirected authentication home, or weaker execution
policy was shipped.

User decision `D-20260908-e9a718` closes always-including globals and default
exclusion. SpawnGate: Independence FRONTIER spawn — bounded native-route judgment
before changing an execution boundary; disposition: reject the OS workaround
after the real native sandbox failure. SpawnGate: Parallelism WORKHORSE spawn —
independent launcher integration, native-source inspection, and runtime work.

## Real execution evidence

The companion `2026-09-08T1224--cca9949--global-instruction-evidence.json` retains
path-redacted native loader lines, pin identities, source hashes, bounded review
results, receipt checks, and the exact supplied review packets. Raw native debug
logs and their unrelated private metadata are not copied into the checkout.

Real `corpus_session.launch` against installed Claude, using the native logged-in
home and a separate temporary agent-bios store, showed:

- Include: **7** sources — global CLAUDE.md, two imports, user context7 rule,
  project CLAUDE.md and its AGENTS.md import, and project memory.
- Exclude: **3** sources — the two project files and project memory only.
- Managed resume of the excluded pin: the same **3** sources, same recorded
  exclusion choice and native environment.
- Before/after SHA-256 comparisons reported all four protected files unchanged:
  native CLAUDE.md/settings.json and project CLAUDE.md/AGENTS.md.
- Native login and permission-mode banners remained. Sessions exited cleanly.
  Only local `/context` or `/exit` operations were used; no model-generation
  prompt was sent. This verifies native loading and managed resume startup, not
  model obedience, corpus-agent execution, or all earlier native-plugin work.

Correction dated 2026-09-08: the earlier 07:25 record reported Claude unauthenticated
at that time. The current original environment reports logged in, and these
authenticated startup/resume probes succeeded. That does not retroactively turn
the earlier zero-token native-plugin attempt into model acceptance.

## Review adjudication

Three fresh Claude Fable 5 / max source passes and one focused final pass completed
on the cross-provider seat. Receipts bind the supplied packet and raw result
digests; distinct native session ids and model usage confirm real fresh dispatch.
The evidence does not claim that the additional ultracode workflow ran or that
file labels alone prove distinct perspective-control coverage.

Confirmed causes, fixed without additional persistent concepts:

1. Module resume accepted an explicit False argument but replayed the pin instead.
   It now refuses the override before recovery or host access.
2. Exact global/project path overlap could remove project instructions. Fresh
   preparation and resume now refuse that overlap.
3. Pinning re-ran mutable symlink checks and could terminate a healthy child after
   filesystem drift. Pin/read/recovery validation now checks recorded arguments
   and provenance only; live path checks remain before preparation and resume.

Rejected findings were checked against actual consumers rather than majority:

- Bare/Vanilla silently ignoring the flag: the initial packet omitted the bare
  guard. Real CLI calls exit 2 before activation; persistent dispatch tests now
  cover both, Codex, and resume refusals.
- NFC changing the native lookup: the installed native config getter itself
  normalizes NFC, so the adapter matches it.
- `link/..` being traversed by the kernel before native normalization: the exact
  installed import is `join as Ve` from `path`; both User CLAUDE.md and user rules
  are built with `Ve`. A direct Node probe confirms lexical normalization before
  filesystem access. A regression preserves this supported behavior. No runtime
  restriction was added for this false finding.

## Verification and remaining boundary

Final corpus suite: **92 tests PASS**, no skips. Added launcher option regression
passes through real main → selection → Custom → save/read → composition dispatch,
covering final Include overriding initial CLI Exclude and saved False/default
roundtrip. Catalog key parity, real Textual picker, numbered fallback, and
language-invariant launch contracts pass in named partial runs. Earlier native
Textual Pilot checks covered English/Korean/Japanese and both host choices.

Python compile checks, `git diff --check`, package boundary, surfaces, terminology,
and decision ledger checks passed. No fresh full-umbrella green is claimed; the
earlier unrelated launcher/binding failures remain separately documented.
Untracked new files are not implicitly covered by tracked-file gates.

The remaining product limitation is Codex selective exclusion. Revisit when a
native selective source control exists, or with explicit scope for a separately
maintained host adapter; do not infer permission to modify the vendor CLI or
weaken its sandbox. No deployment or global-file migration was performed here.
