---
created_at: 2026-09-15T16:04:17+09:00
head: 37f7a90
kind: handoff
supersedes: 2026-09-15T1042--7b9f1ed--approved-python-bootstrap-design.md
---

# Windows script distribution — implementation handoff

This record states what the approved-Python script route is at `head`, which of
the design's qualification items the Windows workflow now exercises, and what
remains outside the tree. The superseded design stays the rationale; its
`status: proposed-not-implemented` no longer describes the tree.

## Implemented at head

- `compose/windows_deploy.py` owns the script installation: ownership marker and
  binding records, immutable `releases/<digest>` and `runtimes/<digest>` staging,
  the Python binding with its hash, HKCU PATH and Start menu receipts, `install`,
  `verify` and `uninstall`. It refuses an unowned nonempty root, an Inno-managed
  root and an unqualified downgrade.
- `compose/runtime_entry.py` is the one dependency entry for ordinary and
  `_pth`-isolated interpreters; `host_platform.python_argv` routes every child
  call (bridge, setup probes, launcher, Studio) through the recorded binding, and
  private install receipts record the launcher runtime so an interpreter move no
  longer invalidates ownership.
- `packages/windows/script-install.ps1` (bootstrap), `packages/windows/commands/*.ps1`
  (static wrappers), `packages/windows/build-script-bundle.py` (test/stable asset
  builder), `packages/windows/python-runtime.json` (pinned CPython 3.13.15 x64
  embeddable descriptor) and `packages/windows/script-smoke.py` (runner-only
  qualification) are author-side; only the two compose modules ship.

## Qualification evidence

Windows workflow run 34939569862 at 37f7a90 (2026-09-15) passed both jobs. The
`windows-script` job built test-signed assets on the runner and ran the
qualification in Windows PowerShell 5.1 and PowerShell 7 (33 checks, 22 distinct,
106 s). Per shell: bootstrap install into a Korean, spaced profile and return to the
same session with a preserved user alias; real private install, version, verify and
setup through the bound interpreter; source capture and revision-checked import;
both host snapshots, app bridge children and learning capture through the runtime
binding; Studio and jsonschema imports under the isolated embeddable runtime; fresh
shell restoring saved roots without changing the caller environment; same-version
repair; interpreter A to B update preserving ownership, bridge and private state;
uninstall retaining authoring, session pins, the external Python and referenced old
runtimes. Once: preinstalled approved Python reuse without download or package
mutation; real HTTPS acquisition of the pinned official runtime; and nine negative
controls (wrong manifest, archive and runtime hashes, unknown script signer, ZIP
traversal, tampered bootstrap, tampered wrapper, occupied unowned root, unapproved
Python, existing Inno root). The EXE job stayed green.

Read a green run as "these contracts held on a hosted runner where PowerShell and
Python are permitted", not as a claim about any managed machine.

## Not established by this tree

- A release code-signing identity: the workflow signs with a runner-only test
  certificate imported into the runner's machine stores; stable assets refuse it.
- A published release and its public one-line command; `install.ps1` still
  carries placeholder trust anchors until a builder fills them.
- Policy validation on an Exosphere-managed machine; a hosted runner proves the
  route works where Python and PowerShell are permitted, not that the policy
  permits it.
- Migration of an existing Inno installation (refused, decision-recorded in the
  design) and garbage collection of retained release/runtime trees on uninstall
  (D-20260915-371664).

## Traps met while landing this

- Windows PowerShell 5.1 started from a pwsh 7 step inherits pwsh's PSModulePath
  and cannot load its Security module; the harnesses scrub the variable.
- 5.1 returns a top-level JSON array from ConvertFrom-Json as one object; the
  bootstrap casts its signer list to `[string[]]`.
- With stderr redirected, 5.1 turns native stderr lines into terminating errors
  under Stop; native invocations in the wrappers and bootstrap run under Continue.
- `pip --target` emits console launchers (`jsonschema.exe`); the builder removes
  them so the no-custom-EXE check stays meaningful.
- The WScript.Shell shortcut object cannot save into a path with characters outside
  the system ANSI code page; shortcuts are written through IShellLinkW instead.
- Read back from the Console with stdout redirected, 5.1 returns a BOM-emitting
  UTF-8; the scripts name a preamble-free encoding and the Python entry decodes
  stdin as utf-8-sig.
- PowerShell 7 kept a private root variable after the wrapper restored it through
  the process block alone; the wrappers now also remove it through the Env: drive.
