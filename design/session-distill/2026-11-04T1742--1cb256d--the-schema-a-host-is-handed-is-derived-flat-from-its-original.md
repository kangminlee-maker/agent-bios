---
created_at: 2026-11-04T17:42:00+09:00
head: 1cb256d
kind: design
supersedes: null
---

# The schema a host is handed is derived flat from its original

WP-08 commit 7. This follows `2026-11-04T1716--b2dc7c2--a-schema-handed-to-a-host-carries-no-schema-key-…`, whose fix
dropped `$schema` only. The lead then decided, on 2026-11-04 (D-20261104-cf3871), on two things:
- confirm the cause on the pinned binary, under three conditions that make a model call and any network traffic
  impossible;
- derive the handed schema by code from the original: no `$schema`, every `$ref` inlined from `$defs`, no `$defs`.

The original `read.schema.json` and `stitch.schema.json` stay the one owner of every value. The handed form changes
the shape the model sees, so the lead puts this transformation in ⑦'s X review.

## The cause, confirmed on the binary

`work/impl/wp08/c7/host-probe.sh` ran the pinned 2.1.317 binary with the hermetic flags and `--json-schema`, under the
lead's conditions:
1. `CLAUDE_CODE_OAUTH_TOKEN` was a wrong placeholder. So the CLI had no credential and did not read the keychain; the
   real token file was not used.
2. The binary ran inside `sandbox-exec` with `(deny network*)`. The sandbox was first shown to refuse a local
   connection.
3. HOME and the configuration directory were a new cell (mode 700), removed afterwards. Only stderr's first line and
   the stdout events' types were kept.

| Schema handed | Exit | stderr, first line | stdout events |
| --- | --- | --- | --- |
| the re-pin's judge schema (no `$schema`) | 142, stopped at 90 s | none | `system/init`, then `system/api_retry` |
| dw2-live1's `schema.json` (draft 2020-12, with references) | 1 | `Error: --json-schema is not a valid JSON Schema: no schema with key or ref "https://json-schema.org/draft/2020-12/schema"` | none |
| read, without `$schema` (1cb256d) | 142 | none | `system/init`, `system/api_retry` |
| stitch, without `$schema` (1cb256d) | 142 | none | `system/init`, `system/api_retry` |
| read, flattened (this change) | 142 | none | `system/init`, `system/api_retry` |
| stitch, flattened (this change) | 142 | none | `system/init`, `system/api_retry` |

- **How to read the table.** `system/init` means the startup check passed and a session began. `api_retry` is the
  CLI retrying a request that the sandbox would not let out. Exit 142 is the probe's own 90-second alarm.
- **The real roots.** agent-bios, checkout-run and checkout-main were equal before and after both probes.
  - `~/.claude` changed only by `.claude.json` backup rotation and other sessions' transcripts. The rotation ran on the
    same one-minute cadence before the probes started, and no changed name carries a probe cell's name.
  - `~/.codex` changed only by another session's worktree in the first probe.

## The change

- **`packet.host_schema(schema)`.** It derives the handed form:
  - `$schema` and `$defs` are dropped;
  - every `$ref` is replaced, recursively, by a copy of the `$defs` entry it names.

  Two references have no inlined form and are refused (`HOST_SCHEMA`): one beside other keywords, and one that reaches
  itself. The policy already allows a `$ref` only to an entry of the schema's own `$defs`.
- **`packet.schema_bytes`.** It compiles both the original and its handed form through the policy, and returns the
  handed form's canonical bytes. Those bytes are still:
  - what `schema.json` holds;
  - what the packet's `SCHEMA` hash names;
  - what `claude-run` hands the host;
  - what the receipt hashes.

  So the gate's single binding, from the driver to the host, is kept.
- **Sizes.** The handed read schema is 2,695 bytes. It was 2,932 as dw2-live1 sent it and 2,875 without `$schema`. The
  handed stitch schema is 920 bytes, against 949 without `$schema`.

## The controls

**`packet`:**
- `host-schema-names-no-meta-schema-and-no-reference`: both originals name the meta-schema and hold references, and
  their handed bytes hold no `$schema`, `$defs` or `$ref`. The policy still compiles those bytes.
- `host-schema-follows-a-change-to-its-defs`: every `$defs` entry of each original is marked. The marker then appears in
  the handed form exactly as many times as references reach that entry from the root, counted independently.
- `host-schema-refuses-a-reference-it-cannot-inline` and `host-schema-refuses-a-reference-that-reaches-itself`.

**`stage_read`:**
- "the schema a host is handed accepts and refuses the answers the schema does". It takes every answer the three
  live-leg fixtures' golden runs gave: 11 read answers and 3 stitch answers.
  - Each is also broken in one place: a required key gone, a key added, a claim id off its pattern, a quote with a key
    added, a resolution's outcome off its list.
  - The original and the handed form must agree on every one. The accepted ones must be accepted, and the broken ones
    refused.
- "every schema S3 hands a host names no meta-schema", from 1cb256d, still holds.

**The pretrial.** Each row is one mutation in a fresh copy. The unmutated suites passed first.

| Mutation | Caught by name |
| --- | --- |
| `$schema` kept | `host-schema-names-no-meta-schema-and-no-reference`; stage_read's "names no meta-schema" |
| nothing inlined, `$defs` kept | `host-schema-names-no-meta-schema-and-no-reference`; `host-schema-follows-a-change-to-its-defs` (and both refusal controls, whose refusals the mutation also disabled) |
| `pattern` lost when inlining | stage_read's "accepts and refuses the answers the schema does" |

**The other suites.** `gate` and `dispatch` pass unchanged. Their schemas hold no references, so their handed form is
the schema without `$schema`.

**The runner's preflight.** `run-leg.sh` puts the handed read and stitch schemas through the binary's check offline
before every leg. Both are now accepted, as they are on the binary itself (the table above).

## What is still open

The provider's side is first exercised by DW2's rerun (`live2`). Two things are tested there:
- Claude Code derives a strict schema for the provider, falling back when it cannot.
- The gate's binding check requires the request's recorded `StructuredOutput` tool definition to equal `schema.json`.
  The handed form holds no references, so it is the form least likely to be rewritten on the way.
