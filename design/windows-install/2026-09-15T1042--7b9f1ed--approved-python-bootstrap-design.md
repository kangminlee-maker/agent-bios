---
created_at: 2026-09-15T10:42:55+09:00
head: 7b9f1ed
kind: design
status: proposed-not-implemented
supersedes: 2026-09-15T1032--7b9f1ed--powershell-bootstrap-design.md
---

# Windows script distribution with approved Python — proposed design

This is the successor design for PowerShell one-line installation. The user states
that Python is allowed, but some workers do not have it installed, and asks for a
curl-like installation path without the custom EXE installer. This document replaces
the EXE-dependent default of the earlier bootstrap design; the existing tested EXE
build remains an optional route. Nothing here implements or publishes a new route.
It changes Windows acquisition/deployment, not the separate Team environment design.

## Outcome and policy boundary

A worker runs one PowerShell command. The bootstrap obtains verified release assets,
finds a usable approved interpreter or provisions an approved application-private
Python runtime, deploys agent-bios scripts and dependencies, and opens product setup.
No agent-bios-setup.exe, agent-bios.exe, agent-launch.exe, npm, GitHub CLI, WSL or manual
Python installation is required by this default route.

This does NOT mean no executable code runs. Existing PowerShell/curl and Python are
executables. Provisioned Python includes python.exe and DLLs, and some dependencies
include native .pyd files. The constraint is to avoid custom compiled agent-bios
executables and an EXE installer, not to disguise or evade application control.
Python being allowed does not prove every downloaded Python build, path or child
script is allowed. Use the organization's approved distribution/version/location;
a policy rejection stops with its real reason. Never rename/encode a blocked binary,
disable endpoint protection or weaken execution policy to make installation work.

This supports the product purpose by making the same selected environment reachable
on Windows while retaining personal sources, native files and pinned task context.
Software installation does not activate instructions in an existing agent task.

## What curl contributes

curl.exe transfers files; PowerShell coordinates installation; Python runs the
existing application. curl cannot replace the interpreter or make blocked code
permitted. Use curl.exe explicitly when that transport is selected, not an ambiguous
curl alias. A built-in PowerShell downloader is an equivalent transport when curl
is absent; its absence must not start another dependency-installation chain.

The public one-line command is generated only after public assets exist. The default
corporate path downloads a version-bound install.ps1 into a unique temporary folder,
checks download success and its approved signature/trust information, then invokes
that saved script in the current PowerShell process. A failed transfer never runs
an old or partial script. The exact public URL and initial trust anchor must be
published with the command; no working URL is claimed by this design.

Use curl --fail --location with bounded redirect/time/retry behavior and check its
exit status before execution. Prefer HTTPS-only transfers and normal certificate
validation. Do not forward credentials to unrelated redirect hosts. A compact
curl-to-Invoke-Expression variant is not the corporate default: it executes fetched
code before file-signature checking and does not provide the same signed-script
policy path. No -ExecutionPolicy Bypass, Unblock-File workaround or profile edit.

A child powershell.exe cannot update its parent's environment. The coordinating
script therefore runs in the invoking session, with local variables/preferences
scoped and restored; only its intentional process PATH update persists. It never
uses exit to close an interactive caller's shell.

## Runtime selection

1. Discover supported, approved existing Python installations without modifying them.
   Do not trigger Microsoft Store installation aliases or execute arbitrary PATH
   candidates just because they are named python. Validate the candidate against the
   configured distribution policy, then probe version, architecture and capabilities.
2. Reuse an interpreter only when its version/ABI/platform match a tested dependency
   bundle. Record its absolute resolved identity; never depend on future PATH order.
3. If none is usable, download the approved, version-pinned Windows embeddable Python
   distribution from the official source or organization-controlled mirror. Check
   archive digest, contents and expected publisher signatures before execution.
4. Extract to an owned versioned runtime directory. No system Python replacement,
   Python file-association change, global Python PATH registration or administrator
   installer is needed. Policy requiring a centrally installed runtime takes precedence:
   give the approved deployment action instead of installing a private copy anyway.

V1 runtime qualification starts with Python 3.13 x64, matching the Windows build
already exercised. The exact patch release and hashes are release-generated data,
not a floating 3.13 download. Other installed versions are reusable only after their
ABI and child-process paths pass the same tests; unsupported existing Python is not
uninstalled. Windows 10/11 x64, PowerShell 5.1/7 are targets. ARM64/x86 remain outside
v1 until a matching runtime/dependency bundle and runner evidence exist.

The official embeddable distribution has isolated _pth behavior and is not a normal
pip-managed installation. Do not assume script-directory imports, PYTHONPATH,
ensurepip, venv or a developer's site-packages are available. Ship dependencies as
verified, ABI-specific application assets. Do not pip install into an existing
user/system interpreter. Native dependency inventory must include .dll/.pyd files
so deployment approval is based on actual contents, not only extensions of launchers.

## Application and launch structure

Deploy code, instruction assets and application dependencies as a verified ZIP.
Keep runtime versions, application versions and user authoring in separate homes.
The stable command directory contains signed static agent-bios.ps1 and
agent-launch.ps1 wrappers. They read a validated local binding record for the
interpreter and active application; they do not contain user-specific generated
code that would need a signing key on the client. No C# EXE launcher is used.

Reuse compose/native_cli.py and the shared Python store/setup/session machinery.
Add one application-owned bootstrap entry for import paths and dependency activation;
all child interpreter calls, app bridge helpers, learning probes and runtime-command
receipts must use that same binding. Audit sys.executable, python3 and implicit
site-packages assumptions. An embeddable runtime executing one trivial file is not
proof that the complete application or its children work.

The default persisted command is a .ps1 script, so command lookup and signed-script
execution must be tested in PowerShell 5.1 and 7. No persistent user-profile functions
or aliases are required. A verified absolute script path remains the recovery route.
Other shells are not silently claimed supported.

## Ownership and reuse of existing machinery

| Layer | Owns | Must not do |
| --- | --- | --- |
| PowerShell bootstrap | Acquisition, approved-runtime resolution/provisioning, invocation, current-process PATH and stage reporting | Rewrite private instruction state, duplicate setup choices, remove another Python |
| Common Windows deployment module in Python | Owned application/runtime version directories, command bindings, persistent PATH/shortcut receipts, repair and removal | Depend on Inno running first or overwrite foreign directories |
| Existing private installer/setup | Library updates, saved selection, personal edits, native-file preservation and recovery | Treat installation as current-task instruction activation |
| Optional existing EXE route | A convenience client of the common deployment contract after integration | Become a second source of PATH, ownership or uninstall rules |

The common Windows deployment module is NEW work: current persistent PATH, Start
menu and program-removal behavior resides in Inno Pascal code. It must be extracted
and tested, not described as already reusable Python behavior. Reuse its validated
ownership semantics, including 8.3 path equivalence without rewriting saved roots.
The PowerShell stage before Python exists only acquires a runtime; it does not grow
into another application installer.

An occupied unowned destination is rejected. An existing Inno-managed installation
is not overwritten or silently relabelled as ZIP-managed. Design and validate an
explicit handoff of its owned entrypoints/receipts, or use approved removal followed
by deployment into a distinct owned root while preserving private sources. Do not
leave two writers claiming the same installation. This migration requires its own
tests and can be deferred while the source route targets fresh installations.

## Release assets and trust

Publish a complete versioned GitHub Release or organization mirror, not expiring
Actions artifacts. One release provides the signed bootstrap/wrappers, application
ZIP, ABI-specific dependency assets, installed-file inventory and runtime descriptor
with pinned source/version/architecture/size/digests/publisher policy.
Generate metadata from actual build inputs and final signed bytes. Build a dependency
chain without self-hash cycles. The initial bootstrap pins the release manifest;
that manifest pins each dependent asset. Resolve latest only once. A pinned version
never fetches a later latest asset mid-run.

Prefer immutable releases, draft-first asset assembly and promotion only after all
required assets and anonymous download checks pass. Stable metadata must not silently
fall back to unsigned previews, unknown mirrors or a different interpreter. Published
trust policy and key rotation are explicit. Initial bootstrap trust comes from the
published command/source/signature policy; a hash downloaded from the same untrusted
place is not an independent trust anchor.

Runtime acquisition performs no user authentication automatically. Use the approved
proxy/certificate environment. An offline deployment can supply the same approved
verified assets through internal distribution. No security-product configuration is
changed by the bootstrap.

## First install, update and removal

New installation deploys verified files, establishes the approved interpreter
binding, validates the native command path and opens product setup once. Language,
environment selection, app registration, optional model tools and source capture
stay in the existing setup UI. NoLaunch installs the software but leaves first-time
configuration pending rather than inventing choices.

Existing installations preserve custom roots, selections, personal edits and session
pins. Stage a new application/runtime version, check it through the exact selected
interpreter, then switch owned command bindings through the deployment owner. Never
replace a running runtime in place or kill user agents. Shared native transaction
locks and schema checks govern private-state writes; versioned directories alone do
not make mixed-version writers safe. Refuse an unqualified downgrade.

A same-version rerun verifies/repairs owned files. Missing or changed externally owned
Python is a broken binding, not permission to delete or modify it. Re-probe and select
an approved compatible interpreter/runtime through the same documented policy.

Persisted PATH is owned by the deployment module; the bootstrap adds only the command
directory to its current process PATH, preserving unrelated process-only entries.
Do not delete a user's shadowing alias/function. Verify bare command resolution,
report conflicts and use the verified absolute path for the current operation.
Other already-open terminals/apps are unaffected.

Provide an application removal command that uses the same deployment owner, removes
only its scripts, shortcuts, PATH entry and unreferenced application-private runtime
versions, and retains personal instructions/session records by default. An existing
external Python is never removed. Startup confirmation is read-only; actual mutation
follows the user's removal action. No Inno uninstaller EXE is needed for this route.

## Failure handling

Before execution, wrong hashes/signatures, incomplete archives, unsafe extraction
paths or blocked runtime execution stop without switching active code. Retain a
small operation receipt and useful logs; do not log credentials or all environment
variables. Clean only owned temporary files after child processes finish.

Separate software acquired, runtime usable, application deployed, private environment
updated and configuration complete. A canceled setup leaves software present with
configuration pending. A failed private update uses the native recovery path rather
than resetting user data. A pointer switch can be undone only while compatible with
observed user-state writes; never restore stale user data as a generic rollback.
No power-loss durability, approved-policy status or model activation is inferred
from a successful download or version printout.

## Required qualification

Keep the existing direct-Windows evidence as baseline, not proof of this new route.
Test the actual downloaded script/application/runtime assets under PowerShell 5.1/7:

- No Python installed: approved private runtime is acquired and real setup/library
  operations work without Node/npm/GitHub CLI/WSL or a custom agent-bios EXE.
- Approved supported Python present: reused by absolute identity; no runtime download,
  global package mutation or interpreter replacement. Incompatible Python and Store
  aliases are distinguished from a usable runtime.
- Embeddable _pth isolation and ABI-correct native modules: Studio, source import,
  learning, app helper, snapshot generation and child processes use the real binding.
- Restricted/missing signature, denied runtime location and security-product rejection:
  stop and identify the approval/deployment need; no disguised fallback or bypass.
  A generic Windows CI runner is not evidence of an Exosphere-managed policy outcome.
- Download/redirect failures, wrong metadata/digests and concurrent latest changes:
  never execute stale/partial/wrong-release content.
- New install, signed-wrapper execution, same-shell command lookup, Unicode/spaces/8.3
  paths, ordinary unelevated user, owned-only PATH and alias conflict handling.
- Update/repair/cancel/removal preserve actual personal edits, native files and pins;
  external Python survives removal; active old runtime and ownership conflicts are
  handled explicitly. Existing-Inno handoff is qualified separately before enabled.

User/IT validation on an Exosphere-managed machine remains required for a policy
compatibility claim. This does not block designing or testing the permitted Python
route; it prevents claiming that curl or packaging format establishes approval.

## Implementation order and exclusions

1. Define approved runtime/ABI assets and the shared Python application entry.
2. Extract common Windows deployment/ownership from the EXE-specific route.
3. Implement the signed static command wrappers and bootstrap with both runtime branches.
4. Qualify clean-machine/existing-Python tests, failure controls and update/removal.
5. Validate the actual enterprise policy, publish a complete approved release, then
   advertise its one-line command. Publication and policy administration are separate.

Deferred: custom EXE as the corporate default; global Python installation/modification;
WinGet as a prerequisite; package-manager rewrites; ARM64 without evidence; automatic
security exceptions; arbitrary pip installation; unqualified Inno migration and
background auto-update. Revisit each only when its concrete capability or deployment
need is established. The existing EXE build remains available where policy permits it.

## Sources

- Python Windows embedding and isolated module paths:
  https://docs.python.org/3/using/windows.html#the-embeddable-package
- Python script/module entry:
  https://github.com/python/cpython/blob/main/Doc/library/__main__.rst
- curl HTTP failure and redirects:
  https://github.com/curl/curl/blob/master/docs/cmdline-opts/fail.md
  https://github.com/curl/curl/blob/master/docs/cmdline-opts/location.md
- Exosphere program execution control:
  https://exosp.com/function/control/
