---
created_at: 2026-11-04T17:16:00+09:00
head: b2dc7c2
kind: design
supersedes: null
---

# A schema handed to a host carries no $schema key, because Claude refuses the 2020-12 meta-schema at startup

WP-08 commit 7. The first live leg, `dw2-live1` (17:00, on b2dc7c2), stopped before any model request. This record
covers four things:
- what the failure was;
- what was compared to find it;
- the fix (D-20261104-eed107);
- why the dry run did not catch it.

## What happened

- Window 1 was dispatched twice: the call and its retry.
- Each attempt's host exited 1 after 1.6 s:
  - `capture/stream.jsonl` was empty, without even the session's init event;
  - the host recorded no transcript and no request;
  - usage was zero.
- The gate's codes (`BINDING_MISMATCH`, `COMPLETION_INCOMPLETE`, `CONTEXT_UNDECLARED`, `CWD_OUTSIDE_MANIFEST`,
  `MODEL_UNATTESTED`) all follow from that empty capture. `CWD_OUTSIDE_MANIFEST` reads the host's recorded working
  directory, which is null because no session started.
- `LEG_ENDED` ended the leg at that failed item.
- The pinned version was 2.1.317 before and after, and the real roots were unchanged.
- The lead counts the two attempts as no calls of the owner's budget, since no request was made.

## What was compared

The re-pin's judge calls (`view_window` false) passed. The S3 window call (`view_window` true) did not. What reaches
`claude-run` for each was compared from their call directories.

**The same in both:**
- the profile flags and their hash;
- the environment names the host is given;
- the manifest's shape (no files, the cell's own working directory);
- the pinned binary.

**Different:**

| What | Re-pin judge | S3 window |
| --- | --- | --- |
| Schema | Plain object, no `$schema` | Draft 2020-12: `$schema`, 7 `$defs`, 10 `$ref` |
| Output cap | 4,096 | 32,000 |
| Packet bytes | 4.7k | 10.4k |
| Cell path | 53 bytes | 92 bytes (a longer call id) |

## The cause

Claude Code 2.1.317 checks `--json-schema` at startup, after loading its commands and agents and before any request.
The check was read from the binary's embedded source, without running it:
- it builds Ajv's default class, the draft-07 one;
- its options are `allErrors`, `validateFormats: false` and `multipleOfPrecision: 6`;
- it calls `validateSchema`;
- on any error it prints "Error: --json-schema is not a valid JSON Schema: …" and exits.

Ajv's `validateSchema` looks the `$schema` URI up among the meta-schemas it holds. The draft-07 class holds no 2020-12
meta-schema, so it throws `no schema with key or ref "https://json-schema.org/draft/2020-12/schema"`. Every distill
schema names that URI.

Reproduced offline with Ajv 8.20.0 under the same options, by `work/impl/wp08/c7/ajv-probe.js`:

| Schema | As sent | Without `$schema` |
| --- | --- | --- |
| `schema.json` of the failed window call | refused, `no schema with key or ref …/draft/2020-12/schema` | accepted |
| `read.schema.json` | refused, same error | accepted |
| `stitch.schema.json` | refused, same error | accepted |
| The re-pin's judge `schema.json` | accepted (has no key) | accepted |

The host's error message itself was not kept. The dispatcher stores no runner stderr, because it carries bodies
(design §3.2). The cause therefore rests on the binary's code and this reproduction.

## The fix

`packet.schema_bytes` drops `$schema` from the bytes `schema.json` holds.
- **Why there.** Those bytes are:
  - the bytes the packet's `SCHEMA` hash names;
  - the file `claude-run` hands the host;
  - what the receipt's `schema_sha256` hashes.

  The gate binds all of these to `call.json`'s `schema_sha256`. A second, host-only file would break that binding.
- **Why it is safe.** Our validation pins draft 2020-12 in code (`validate.compile_schema` builds
  `Draft202012Validator`), so the key decided nothing on our side. Codex is handed the same file. The key declares
  which draft applies and constrains no instance. No WP-08 call hands Codex a schema, so Codex's validator was not
  checked.

Two controls hold the fix:
- `packet`: `host-schema-carries-no-$schema`. The read and stitch schemas each name the 2020-12 meta-schema. The bytes
  S3 hands a host for them carry no `$schema` and are otherwise the same schema, which the policy still compiles.
- `stage_read`: "every schema S3 hands a host names no meta-schema". It checks every `schema.json` the three live-leg
  fixtures' golden runs dispatched.

The pretrial ran each suite unmutated first, and both passed. With the fix alone reverted, both failed, each by its
control's name.

## Why the dry run passed

The dry runner replaces `claude-run` with a process that prints the argv and exits 0. So neither `claude-run`'s own
checks nor the host's startup ran in it. A dry run proves the dispatcher's side only:
- the declaration's amendment;
- the reservation and the seat's admission;
- the argv.

`work/impl/wp08/c7/run-leg.sh` now runs the host's schema check offline before every leg, dry or live:
- it writes the bytes S3 hands the host for its two schemas;
- it puts them through `ajv-probe.js`, the same Ajv class and options as the binary;
- the leg stops (exit 97) unless both are accepted.

Against b2dc7c2 it stops with 0 of 2 accepted, and against the fix it passes 2 of 2.

## What this does not show

- **The binary's Ajv version.** It is not known; the reproduction used 8.20.0, whose draft-07 class behaves as the
  binary's code reads.
- **The API side.** Claude Code derives a strict schema for the provider and falls back when it cannot. Whether the
  provider takes `$defs` and `$ref` in the tool's schema is first exercised by the next live call. A refusal there would
  be a request with an error, not an empty stream.
- **Schemas no WP-08 call hands a host.** `event`, `expected_observation` and `ledger` use `dependentRequired`. The same
  check refuses that keyword under Ajv's strict mode, as an unknown keyword, with or without `$schema`. A later stage
  that hands one of them to Claude would fail in the same way.
