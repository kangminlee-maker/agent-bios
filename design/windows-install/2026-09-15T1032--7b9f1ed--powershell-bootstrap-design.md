---
created_at: 2026-09-15T10:32:51+09:00
head: 7b9f1ed
kind: design
status: proposed-not-implemented
---

# PowerShell one-line installation — proposed design

This document designs acquisition and entry into the existing Windows installer.
It does not implement the bootstrap, publish a release, enable repository settings,
register a WinGet package, or certify new operating-system behavior.
It is separate from the Team work-environment expansion specification: no Team
selection, source rights, environment composition or context-activation rule changes.

## 1. Purpose and starting evidence

Make agent-bios available from an ordinary Windows PowerShell without asking the
worker to install Node.js, npm, GitHub CLI, Python or WSL. Preserve chosen work
environments, private authoring and existing task pins across software updates.
Installation is not authorization to use instructions in an existing agent task.

The starting implementation is the Windows branch at 7b9f1eda1ed7faec37d4c5c8e4cfe02b4ac1110f.
Its Windows workflow 34913904276 passed packaged installation, native entrypoints,
PATH/Start-menu registration, both host snapshots, setup inspection, bridge
registration/status/removal, UI imports, process locking, reinstall preservation,
invalid-ownership refusal, and owned PATH removal. Its installer is unsigned.
This is Windows Server 2022 runner evidence, not desktop Windows 10/11 user or IME
qualification. It proves no PowerShell bootstrap yet. The distribution is currently
an Actions artifact, not an anonymous, durable GitHub Release download.

Current owners:

| Responsibility | Existing owner |
| --- | --- |
| Build bundled Python and native executable entrypoints | packages/windows/build.py and Launcher.cs |
| Program installation, user PATH, Start menu and program removal | packages/windows/installer.iss |
| Private library update, saved choices, receipts and recovery | compose/instructions_install.py and shared setup controller |
| Product settings and explicit app registration/source capture | agent-bios install/setup and their existing UI |
| Task context delivery | existing launch/app session adapters; no change in this design |

The bootstrap owns only release acquisition, verification, invoking these owners,
current-process PATH convenience, and reporting the observed stages.

## 2. User entry

Proposed public command, NOT AVAILABLE until the release assets are published:

```powershell
irm -UseBasicParsing https://github.com/kangminlee-maker/agent-bios/releases/latest/download/install.ps1 | iex
```

A specific version uses the same asset on its version-tagged release URL:
`https://github.com/kangminlee-maker/agent-bios/releases/download/vX.Y.Z/install.ps1`.
`vX.Y.Z` is a placeholder, not a release to execute. Pinning the script URL pins
its target installer too; the pinned script never asks for latest again.

Default new-install journey:

1. Show the resolved version and per-user destination.
2. Download and verify the release assets.
3. Run the existing installer without its separate wizard or automatic TUI launch.
4. Verify the installed application and make its directory available to THIS shell.
5. Open the product's own setup once, using its absolute executable path.
6. Report program installation and environment configuration separately.

One line starts the process; language, instruction selection and optional account or
host setup remain meaningful choices in the product UI. No duplicate generic
"continue?" question is added before routine authorized installation. Missing
permissions, a conflicting destination, or a policy block are real stop conditions.

A script parameter `-NoLaunch` suppresses opening the product UI. On a fresh machine
this leaves configuration pending rather than silently choosing an environment.
Parameters use an in-process ScriptBlock invocation when needed; do not spawn a
second powershell.exe and claim it updated its parent. Version selection is by the
pinned URL; no separate version resolver or custom short domain is needed in v1.
An optional `-InstallDir` may choose a fresh destination, but must not relocate an
existing installation implicitly.

## 3. Platforms and shell behavior

Initial target: Windows 10/11 x64, Windows PowerShell 5.1 and PowerShell 7.
Test 32-bit PowerShell on a 64-bit OS explicitly; determine OS architecture, not
only the bitness of the current process. Reject x86 and ARM64 before installer
execution in v1. ARM64 emulation in an installer declaration is not qualification.
Add native ARM64 or emulated support only with a corresponding built/tested asset.

Use built-in PowerShell/.NET facilities. Include basic parsing for 5.1; do not
assume the PowerShell 7 web-request parameter set. Honor configured Windows proxy
and certificate trust. No TLS-certificate bypass, global execution-policy change,
profile edit, alias removal or forced elevation. If enterprise policy blocks script
execution, explain the actual failure and offer the ordinary EXE or later WinGet
route; do not route around that policy.

Run bootstrap implementation in its own local script/function scope. Restore any
changed preference/TLS settings in finally; never use exit to close the caller's
interactive PowerShell. The intended persistent process change is the PATH entry.

## 4. Release binding and distribution

Use public GitHub Releases as the first distribution channel. No runtime GitHub API
query or GitHub login is needed for normal installation. Actions artifacts remain
build evidence and development downloads, not the default install URL.

Each complete release carries:

| Asset | Meaning |
| --- | --- |
| install.ps1 | Shared bootstrap template plus generated, release-pinned metadata |
| release.json | Version, source commit, platform, exact asset names/URLs, sizes and SHA-256 values, approved signer policy, installed-file manifest reference |
| Windows setup EXE | Existing installer format containing program/runtime/assets |
| windows-x64-build.json | File inventory and hashes for the installed application, derived from the actual payload |

Generate these from package metadata, the exact build and signing outputs. Do not
hand-maintain separate version, URL or digest constants in several files. The
bootstrap embeds the exact URL and SHA-256 of release.json. That manifest points
only to version-specific assets from the same repository/release. A moving latest
link is used once to obtain the bootstrap, never again for its dependent assets.

Avoid hash cycles: build/sign application payload -> installed-file manifest ->
installer -> sign installer -> release.json -> generated install.ps1. The manifest
does not contain its own digest or the bootstrap's digest. GitHub immutable release
attestation can bind all final assets after publication.

Enable immutable releases before the first stable Windows publication, then use
create draft -> attach ALL assets -> verify candidate -> publish. Setting the
repository's latest release is a promotion step: do it only when required Windows
assets exist and post-publication checks pass. A later npm-only or partial release
must not replace latest and break the one-line URL. Prereleases are explicit,
version-pinned entries and never the default stable target.

Anonymous redirect/download probes must confirm the documented public URLs after
publication. The verifier must not rely on the publisher's GitHub credentials.
No release setting or publication is performed by this design task.

## 5. Trust and integrity

The first trust decision is executing the bootstrap from the project's official
GitHub release over HTTPS. The short irm/iex form executes remote code before its
installer checks run. A checksum downloaded by that same script is not independent
proof that the script itself is trustworthy. Explain this plainly in documentation;
keep direct EXE download and an inspectable saved-script path available.

After that trust decision, verify the pinned metadata hash, exact expected size and
SHA-256 of the EXE, platform/version identity and the installed payload manifest.
The stable channel requires a Valid Authenticode signature matching the approved
publisher key/certificate policy, including a recorded rotation policy. Merely
being signed by any publisher or comparing only a display name is insufficient.
Signing must precede final hashes, and the exact signed installer must be tested.

The existing unsigned EXE is eligible only for an explicitly labelled development
preview release. Preview trust policy is fixed in its pinned generated metadata;
the stable bootstrap cannot silently fall back to unsigned assets. No generic
skip-verification switch is included. Signing credentials and stable publication
remain external prerequisites, not capabilities already present in the repo.

## 6. Execution and update contract

Preflight reads the known native installation registration and validates ownership
before selecting its destination. Do not run an arbitrary agent-bios found first
on PATH or overwrite an occupied, unowned destination. Put destination/ownership
checks in the installer so direct EXE and bootstrap installation use the same rule.
Retain existing custom installation and private storage roots on update.

Download into an operation-specific user temporary directory using a .partial
file. Only a verified complete download becomes executable input. Bound transfer
size/time; retry transient download failures a small fixed number of times. Never
retry an installer automatically on an ambiguous or partially applied outcome.
Use a validated local cache only after rechecking its exact expected digest.

Invoke the EXE directly with correctly quoted literal arguments, using
/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /RESTARTEXITCODE=3010 and an exact log path.
These are program-install choices, not consent to install optional model tools or
capture user sources. Suppress the installer's postinstall setup launch so the
bootstrap opens it only once after verification. Do not kill running agents or
product processes to make an update succeed. The installer owns concurrency and
in-use-file handling; a bootstrap must not hold a mutex the child needs to acquire.

Wait for the installer and its child process tree. Interpret exit 0 as permission
to VERIFY, not proof of readiness; code 3010 is reboot-required because this design
explicitly sets that exit code. Other nonzero and unknown codes are not success.
Never reboot automatically. Validate product version and installed file hashes
against the release's payload inventory before invoking the installed executable.

For a new installation, open absolute-path agent-bios install once. If the user
cancels product configuration, retain the program and report configuration pending.
For an existing configured installation, run absolute-path agent-bios install
--non-interactive to preserve saved selection and personal authoring, then verify.
A repeat of the same version follows this verified repair path; v1 deliberately
avoids a version-only fast path that could overlook broken files. Do not silently
downgrade when the installed version is newer. An explicit downgrade/recovery
workflow is separate future work, not inferred from visiting an old release URL.

Native configuration files, imported source originals, private authoring and running
session pins retain their existing boundaries. No direct bootstrap writes to those
files, no automatic source capture, and no installation-as-context-use claim.

## 7. PATH ownership and immediate use

Inno remains the sole persistent PATH owner, including its uninstall receipt.
After verifying the install, the bootstrap adds only the actual installed directory
to the current process PATH if needed. Preserve all other entries and their order,
including process-only virtual-environment/tool paths. Never replace the current
PATH wholesale with Machine PATH plus User PATH.

Deduplicate by Windows directory equivalence while preserving stored path spelling;
include case, trailing separators and 8.3 aliases in the tests. Reuse the lessons
from the Windows bridge and uninstaller instead of rewriting old ownership records.

Get-Command checks whether the bare name resolves to the new executable. If a user
function/alias or another installation shadows it, do not remove that definition.
Report the conflict and use the verified absolute executable path for this run.
Current-process PATH repair does not change other open terminals, IDEs or apps.
A child shell cannot change its parent's environment; only the invoking shell gets
the immediate-use guarantee. A script launched by another agent tool may therefore
update that tool's process only, not the user's already-open terminal.

## 8. Failure and resume states

| Observed state | Result and next action |
| --- | --- |
| Unsupported OS/architecture or occupied foreign destination | Stop before install; preserve existing application/data |
| Download timeout, missing asset, wrong hash/size/signature | Do not execute; retain concise diagnostics and retry only acquisition |
| Installer busy or in-use files | Ask the user to close the named product process and retry; no forced termination |
| Installer cancellation or failure during file replacement | Report exact stage/code/log; application files may be partial; no claim that the previous program was automatically restored |
| Reboot-required result | Mark pending reboot and do not claim runnable/fully verified |
| Program succeeds, private environment update fails | Program-installed/environment-pending; use the native recovery path, never reset the user's data to make the status green |
| Configuration canceled | Program remains installed; show the absolute command to resume setup |
| PATH registration or name-resolution conflict | Use absolute entrypoint, state limited command availability; no repeated reinstallation |
| All required verifications complete | Ready; report version, installed path and observed configuration status |

Store stage, version, source commit, digests, installer exit code and log location
in a user-local operation receipt. Exclude tokens, full environment dumps and source
contents. Preserve useful failure logs; clean only the operation's owned temporary
files after child processes are finished. Re-running the same pinned command is the
normal retry. Check current state again; never replay an old success receipt as a
fresh validation. The current in-place installer does not establish atomic rollback
on power loss; this bootstrap must not promise it.

## 9. Acceptance evidence

Before stable publication, run the exact generated bootstrap and exact signed EXE
through the Windows workflow. Existing direct-installer smoke is retained.

Required cases:

- PowerShell 5.1 and 7; no Node/npm/system Python/GitHub CLI/WSL dependency.
- HTTP acquisition with real redirects, truncated downloads, wrong hashes and
  mismatched platform/metadata. Verify that rejected EXEs were never started.
- The latest pointer changes mid-run; all dependent assets still come from the
  bootstrap's initially pinned release. Missing Windows assets do not fall back.
- Signature valid/invalid/wrong publisher; stable refuses unsigned preview assets.
- New install and same-version repair; upgrade from a real earlier build with saved
  selection, personal edits and a current session pin; newer-version refusal.
- Unicode/spaces/8.3 paths, existing custom root, foreign directory refusal and
  ordinary unelevated account. An admin runner using per-user mode alone is not
  evidence of running without an elevated token.
- Same invoking PowerShell can run the command; retain unrelated process-only PATH
  entries. Other-process inheritance and alias/function shadowing are reported honestly.
- UI setup opens exactly once; cancel and NoLaunch produce configuration-pending.
  The noninteractive update path preserves actual saved selections and authoring.
- Installer busy, failure, reboot code, partial state and failed private update;
  logs/receipts name the actual outcome, no reset/forced kill or invented rollback.
- Concurrent direct EXE/bootstrap attempts share installer ownership controls.
- End-to-end uninstall preserves user content and removes only its owned PATH.

Use bounded HTTP fixtures for negative controls, then verify the published stable
URLs anonymously. Separate automated runtime evidence from actual Windows desktop,
interactive terminal/IME and live model/app discovery qualification.

## 10. Implementation sequence and exclusions

A. Add the release metadata generator and installed-file verification inventory.
B. Implement the shared bootstrap and current-process PATH handling.
C. Add missing installer ownership/concurrency checks and structured completion data;
   reuse existing private update/recovery semantics.
D. Qualify the generated script under PowerShell 5.1/7 and an unelevated account.
E. Obtain/verify signing setup; test signed bytes; publish all assets as one immutable
   release and only then promote latest. Publishing is a separate authorized action.
F. Register that same installer with WinGet after the public asset/version contract
   is stable. WinGet consumes the installer; it is not another setup implementation.

Deferred: WinGet registration until a durable public installer exists; custom short
URL/domain until GitHub URL usability actually warrants it; ARM64 until target-runner
qualification; automatic downgrade until data compatibility and recovery are defined;
background auto-update and a custom package manager because user-invoked reruns suffice.
Retain direct EXE installation as the offline/restricted-script path. No npm removal
is proposed for macOS/Linux, and no WSL installation is added to the Windows default.

## References consulted

- PowerShell process environment and new-process scope:
  https://github.com/microsoftdocs/powershell-docs/blob/main/reference/5.1/Microsoft.PowerShell.Core/About/about_Environment_Variables.md
  https://github.com/microsoftdocs/powershell-docs/blob/main/reference/5.1/Microsoft.PowerShell.Core/About/about_PowerShell_exe.md
- PowerShell process wait and return object:
  https://github.com/microsoftdocs/powershell-docs/blob/main/reference/7.7/Microsoft.PowerShell.Management/Start-Process.md
- GitHub latest asset URLs:
  https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases
- GitHub immutable releases and draft-first publication:
  https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases
- Inno parameters and exit codes:
  https://jrsoftware.org/ishelp/topic_setupcmdline.htm
  https://jrsoftware.org/ishelp/topic_setupexitcodes.htm
