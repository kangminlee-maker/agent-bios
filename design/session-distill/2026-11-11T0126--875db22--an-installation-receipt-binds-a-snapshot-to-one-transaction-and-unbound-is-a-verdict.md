---
created_at: 2026-11-11T01:26:00+09:00
head: 875db22          # the commit the content was true at
kind: design
supersedes: none
---

# WP-15 landed: an installation receipt binds a snapshot to one transaction, and unbound is a verdict

Implements the plan's WP-15 (`2026-10-20T2119--cc0498f--implementation-plan.md`) against design §6.3
and §11 of `2026-10-20T1942--9684f05--mechanism-design.md`, porting probe 10
(`distill-probes-20261020/installer`, 11 scenarios). Owner decision D-20261111-818391 ships this in
an early patch release so receipts accumulate in the owner's state from that installation on.

## What exists now

`compose/instructions_install.py` hashes a **declared** set of installer source files
(`INSTALLER_CODE`, including `launch/shell_integration.py`, which executes but never enters
`sys.modules`) from the tree it executes from, at import and again at receipt time. After a
transaction verifies and before its journal reaches `COMMITTED`, it writes
`InstallationReceipt/v1` into the state root's receipt directory under the sha256 of its own
canonical bytes. The COMMITTED journal carries that id; the install record carries the transaction
id that reaches it.

`compose/instructions_store.py` records the receipt id in a snapshot's `inputs` **before**
`content_ref` is derived, and only when the receipt covers the catalog, store and bootstrap bytes
the snapshot just hashed. `installation_binding()` is a pure verdict, returned by
`snapshot_inventory` and so by `instructions snapshot --content-ref`.

Three properties worth stating because they are easy to assume the other way:

- The digest names the installer that **executed**, never the package it installed. An old
  installer installing a package that carries a newer one still names its own digest; the package's
  store and catalog ran inside that process and are named separately in `package_modules_run`.
- A difference between the two hashes refuses the **receipt**, not the install. The install is
  sound; only the claim about which code ran is not, and the sessions it serves stay unbound.
- Unbound is a verdict, not a refusal. A development override at an older tree legitimately
  produces snapshots no current receipt covers.

## Measured on this branch (2026-11-11)

- A real `bash install.sh install --non-interactive` into a scratch home writes one receipt of
  24,479 bytes (169 artifact rows: 164 release, 5 owned), `install` and `verify` both exit 0.
- The ported suite: 30 new cases (17 installer-side, 12 store-side, 1 coverage), 84 assertions in
  the 20 cases the probe-scenario map names; `test_instructions_install` 34 tests, the `store`
  group 131.
- 13 controls were pretried (the fix reverted alone, the named case required to fail, restored):
  13/13 fired by name.

## Not ported, and why

- The probe's `sc_c6_git_update` route (`install.sh update` pulling a newer installer and then
  writing the receipt) needs a git remote fixture. The property it showed — the digest follows the
  tree that executes, not the script that started the update — is held by running the installer
  from a copied tree. The git route itself is unexercised here.
- `exposure_unknown` and the F-O9-15 row are WP-21's: no §11 predicate exists in this tree, and
  `session-distill/runlib/measures.py`'s `o9_fixtures` docstring assigns every exposure row to it.
  WP-15 asserts the inputs that predicate consumes (D-20261111-c97b35).

## Residuals carried forward from the probe

Bytecode caches can execute code that differs from source with equal mtime and size, and a file
replaced and restored between the two hashes is not seen. The receipt does not prove every executed
byte, and §6.3 says so. `_CODE_AT_START` is now taken before the sibling imports
(D-20261111-969332), which closes the one residual that was ours to close.
