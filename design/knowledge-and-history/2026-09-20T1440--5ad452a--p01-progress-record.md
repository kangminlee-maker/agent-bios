---
created_at: 2026-09-20T14:40:00+09:00
head: 5ad452a
kind: design
status: p01-in-progress-u17-u7-landed-spikes-run-one-attended-probe-open-nothing-frozen
plan: 2026-09-20T0751--d76af32--development-plan.json
node: P01
run_id: team-env-20260920b
extends: 2026-09-20T0842--77020b1--p01-process-design.md
decisions: D-20260920-0ab39a, D-20260920-5da410, D-20260920-335da0
---

# P01 progress, third record — two units landed, four spikes run, and what they change

P01 is **not** accepted and nothing is frozen. This record extends the
[08:42 design](2026-09-20T0842--77020b1--p01-process-design.md) and the
[02:10 design](2026-09-20T0210--edf15c5--p01-process-design.md): it reports what closed since,
and it corrects two bindings of the 02:10 record that a probe showed to be wrong or
incomplete. Everything else in those records stands.

Spike evidence is outside the repository, under
`~/.local/share/agent-bios-workbench/team-env-20260920/p01-spikes/` and `p01-u7/`, each
directory with its script, raw runs, a `RESULTS` file and `SHA256SUMS`. Re-run a probe before
relying on a figure here; every one takes seconds.

## Landed in `5ad452a`

| Unit | What exists | Closing check |
| --- | --- | --- |
| U17 | `gates/workenv/check-workenv.py`, wired into the umbrella: every `gates/workenv/test_*.py` in its own process, and `ruff` at the exact version `RUFF_PIN` names over `workenv/` and `gates/workenv/` | each leg fails by name on an empty subject set, an absent tool and another version; the self-test builds every input (2 positive, 23 negative controls); `gates/control-audit.py` removes each of the driver's 16 failure statements and the self-test notices all 16 |
| U7, without the registry emitters | `workenv/contracts/`: `canonical.py` (canonical bytes, strict load, digests), `schema.py` (the closed JSON Schema subset, stored and submit modes), `errors.py` and the generated `errors.json` (24 codes, each owned by one module) | 34 tests; the encoder is byte-identical to an independent ECMAScript serializer on 3000 generated values in the admitted domain, and a planted difference is reported; an unsupported keyword fails at load by name |

Two things the work found that were not in any plan:

- **The umbrella's reach scan could not see a checker in a subdirectory.** Its subject set took a
  checker at any depth and its edge pattern took one directory level, so the driver read as
  unreached however it was wired. The 02:10 record listed this as not verified; it was false.
  The pattern now reads any depth under the full name, the reached set changed by that one
  file, and the new probe fails by name on revert (`D-20260920-5da410`).
- **Reverting rules one at a time found eight the tests did not notice**, in code whose tests
  had passed on the first run. Five were redundant code and were removed; three were missing
  tests and were added. A suite that is green on arrival has not been shown to test anything.

`workenv/` is not in `package.json` `files[]`. U9 adds the entries and the boundary leg before
P01 is recorded, as `D-20260920-7989fe` requires.

## Spikes

| Unit | Result | State |
| --- | --- | --- |
| U3 signature, Linux | The macOS verdicts reproduce on OpenSSH 8.2p1, 8.9p1, 10.0p2 and 10.3p1 in containers with networking disabled: positive 0, five negatives 255, `check-novalidate` 0, the two-call classification 6 of 6, Ed25519 signatures byte-identical. An image without OpenSSH gives `tool_absent`. Lowest version observed is 8.2p1; nothing proves a floor below it | **done**; fixtures are U8's |
| U4 unlock | Unattended half only — see the first correction below. With no terminal and no askpass, `ssh-add` exits 1 at once, the agent holds nothing, and signing fails: the state is the access gap `locked` | **open**: the attended run needs a person at a terminal |
| U5 crash harness | 9 of 9 named fault points hit in a child process on macOS and in a Linux container; every invariant held; the same-id retry leaves exactly one receipt and one outbox row in all seven publish cases; seven rules broken one at a time are each noticed. The first version reported `during_checkpoint` as not hit, correctly: the parent had finished the checkpoint itself | **done**; power loss is not tested by any process kill |
| U6 bridge | 13 cases against a stdlib loopback server: 3 served, 9 refused before a result is computed, and a lock landing between compute and write gives 409 with the protected body in no refused response; six rules disabled one at a time are each noticed | **done as a scripted probe**; nothing about a real browser is observed |

## Correction 1: agent-only signing depends on where the public key file is

The 02:10 binding says lock commits the new generation and then purges the agent, and U4's
closing check says a signature after lock fails. Measured on five OpenSSH versions:
`ssh-keygen -Y sign -f key.pub` asks the agent and, when the agent has no such key, **falls back
to the private key file beside the public one**. With the encrypted device key beside it, a
signing call after a lock does not fail on a terminal; OpenSSH asks the person for the
passphrase again, outside the unlock operation and outside the access generation.

`-U` does not fix this portably: OpenSSH 8.2p1 and 8.9p1 ignore it for `-Y sign` and sign with
an empty agent; 10.0p2, 10.2p1 and 10.3p1 honour it. What is agent-only on all five is a
signing call that names a public key file with **no private key beside it**.

The binding gains one clause: the device key's public half used for signing is stored apart
from the encrypted private key, signing names only that path, and `-U` is not relied on. C02's
lock example states `sign after lock` as a refusal under that layout, and P11 proves it
attended.

## Correction 2: the error table is generated, not authored

The 02:10 binding describes one `errors.json` checked both ways. Each contract module now owns
its codes and meanings, the error types refuse a code outside their module's rows, and
`errors.json` is emitted from the modules; a unit test fails a hand edit. The two-way check
against negative examples is `errors.coverage` and runs when U8 brings the examples
(`D-20260920-335da0`).

## What the spikes give U8 to freeze

- Refusal names observed in working code: `request_id_conflict`, `stale_base`,
  `object_digest_mismatch`, `backup_set_incomplete`, `backup_set_damaged`,
  `connection_profile_mismatch`; bridge: `host_not_exact`, `origin_not_exact`,
  `origin_required`, `client_token_missing`, `client_token_unknown`, `preflight_refused`,
  `access_generation_moved`; signature: `signature_invalid`, `signer_not_permitted`,
  `tool_absent`. They are candidates, not frozen codes.
- The signature tool floor a contract may state from observation is OpenSSH 8.2p1.
- A receipt is what makes an object accepted; the same-id retry returns the original receipt.

## Remaining, in order

U4 attended; U8 and U13–U16 (schemas, byte examples, and the four clauses the first design
left uncovered); U9 (lexicon, umbrella and package patches, with the `files[]` entries for
`workenv/`) and U10; U11, U18, U12, then P01's own record and its bound review. The registry
emitters of U7 land with U11, where their input exists.

## Not verified

Everything the earlier two records list that is not struck above, and: a real browser's
behaviour against the bridge rules; the attended unlock; OpenSSH below 8.2p1 or between 8.9
and 10.0; x86_64; that the closed keyword set is enough for C01–C12, which U8 finds out.
