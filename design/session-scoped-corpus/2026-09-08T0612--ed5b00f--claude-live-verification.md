---
created_at: 2026-09-08T06:12:00+09:00
head: ed5b00f
kind: review
---

# Claude live verification

Scope: verify the existing dirty working tree, not implement new adapters or
repair runtime behavior. Product runtime files were not changed by this pass.
The opt-in author-side `claude-live-probe.py` exercises the real store,
`build_plan` / `project_args`, `corpus_session.launch`, and installed Claude Code
2.1.263. The controlled plan uses Claude Sonnet 5 at low effort, no review route,
and per-invocation settings/MCP isolation. Authentication uses the existing Claude
Max login; credentials were neither copied nor printed.

## Results

| Subject | Verdict | Actual evidence |
| --- | --- | --- |
| Plain Claude control | PASS | Session `d3c5b57f-09cc-4b1a-8429-20602eeea1b5` returned `ABSENT` for the undefined corpus value. |
| First-turn corpus delivery | PASS | Session `4abaf096-8374-4572-a58b-bd5521d3a36c` returned the exact value present only in the installed private item; real model usage, valid pin, unchanged native instruction/settings hashes. |
| Managed resume after authoring edit | FAIL | The same session id and snapshot pin were selected, but authentication failed before a model request; every input/output/cache token counter was zero. |
| Launcher-generated native child | PASS | Session `4a724f77-3d28-41c9-9fd2-dbc2ff60676a` spawned and completed exactly one workhorse. Its native child transcript contains a real Sonnet 5 answer with the value, while its user task does not contain the value. |
| Explicit native hook capability | PASS, bounded | Session `0a905b03-65b6-4ce6-924b-e779bc23a56f` triggered the unmodified shipped hook through temporary `--settings`. One matching PreToolUse record contains the actual pipeline-exit reminder. |
| Hook registration removed | PASS control | Same Bash request in session `275db944-63f1-4a44-b0c7-c65f97601ee2` produced zero hook records and no reported reminder. |
| Automatic corpus event/delegated adapters | NOT IMPLEMENTED | The compiler lists these surfaces as unavailable; their catalog items do not become private native registrations. Launcher tier definitions are a different producer. |

The native hook ran **before** the requested Bash command's permission check.
Bash execution was denied in both hook arms; this is hook-delivery evidence, not
successful shell execution. Permission settings were not widened to obtain a
passing result. The hook logging wrapper's `fixture: true` denotes authored
probe instrumentation, not a mocked Claude host. Its structural fixture log was
cleared before the native run; the live record's session id and command match
the real Claude tool request. No corpus hook adapter was added to make this work.

The evidence collector validates nonempty parent/child subjects and produces
`2026-09-08T0612--ed5b00f--claude-live-evidence/evidence.json`. It includes exact
session/content refs, model usage, child input/output evidence, hook contrasts,
native-file hash comparisons, and runtime source hashes. The actually used hook
wrapper and settings are preserved beside it. Native transcripts remain in their
original host location; they were not relocated for resume.

## Confirmed resume defect

`corpus_session.launch` reconstructs a config-home environment variable from the
pin's resolved filesystem path. This loses the distinction between an unset
`CLAUDE_CONFIG_DIR` and an explicitly assigned default path.

Read-only auth probes outside the sandbox, differing only in that variable:

| Environment | loggedIn | authMethod | subscription |
| --- | --- | --- | --- |
| Original environment | true | claude.ai | max |
| Explicit `/Users/kangmin/.claude` | false | none | absent |

The actual resume error claims the OAuth session expired; the controlled
contrast localizes the cause to environment reconstruction, not expired user
login or corpus content. An initial sandbox-only auth status was also false;
the native Keychain-accessible status resolved that environmental ambiguity
before model testing. There was no auth retry storm or credential mutation.

Correction, 2026-09-08: the previous implementation record's real Codex recovery
proof and fixture-based Claude trace proof did not establish authenticated
Claude resume. First-turn delivery is now verified; managed resume is an open
product defect, recorded as F-18. Runtime repair requires the next implementation
request. Preserve set/unset environment provenance rather than deriving
credential identity from path equality; older pins need explicit handling.

## Probe limits and independent check

- The probe's first active attempt lacked a positional prompt because the
  variadic `--tools` flag consumed it; a delimiter flag fixed the harness.
- Its first authoring-edit attempt omitted the required item digest; the store
  rejected it before any host call. The corrected probe used the actual digest.
- These harness failures are not counted as product failures. The later
  authenticated resume failure is separately captured with native evidence.
- No automatic corpus native-skill discovery, event adapter, delegated-item
  adapter, model-behavior reliability rate, release, or live installation is claimed.
- `/root/private_runtime_review` independently checked the failure attribution,
  child transcript, and hook contrast; it accepted the split above and explicitly
  excluded shell execution and automatic corpus wiring from the hook claim.
- SpawnGate: Independence REVIEWER spawn — bounded evidence adjudication ran on
  an independent seat while the main exercised native cases.
- SpawnGate: Parallelism WORKHORSE spawn — the wiring census and hook evidence
  wrapper were delegated alongside the main's session verification.

Post-report checks passed for runtime source-hash equality, evidence assertions,
Python syntax, surface contracts, ontology agreement, payload boundaries,
terminology, content hygiene, the launcher documentation contract, and map
HTML/SVG structure. The ordinary working diff is whitespace-clean. A temporary
index exposing all earlier untracked designs additionally found trailing blank
lines in four September 4–5 records; those pre-existing dated records were left
unchanged. This is not a fresh full-umbrella or all-green repository claim.

## Codex named profile clarification

A native Codex named profile is a saved configuration layer selected with
`codex --profile NAME`: the verified CLI overlays `NAME.config.toml` on the base
`config.toml`. It is separate from the launcher's Balanced/Solo presets and from
named permission profiles. Official reference:
[Profiles](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles).
The current private adapter rejects native named profiles because its
`app-server config/read` route does not support them; this verification pass did
not change that limitation.
