# Windows native installation

The Windows build provides a per-user installer and `agent-bios.exe` with its own
Python runtime. Node.js, npm, a system Python installation and WSL are not required
for the Instructions library and setup. Model host CLIs remain separate dependencies.

Run the Windows x64 setup executable, then open setup from the final page or the
Start menu. A newly opened PowerShell can run `agent-bios install` or
`agent-bios instructions`. Existing terminal processes need restarting to pick up
user PATH changes. The installer does not change PowerShell execution policy or
intercept bare model commands.

Re-running the installer updates program files. `agent-bios install` refreshes the
private library while retaining saved selection and personal authoring. Removing
the application removes its owned PATH entry; private instructions and session
records remain in the user's home. Windows and WSL have separate homes and stores.

The native build is experimental until the Windows workflow's artifact and lifecycle
checks pass for the exact candidate. Fixture tests do not establish live host login,
model execution, app skill discovery or interactive Korean IME behavior. Native
hooks and the shell-based multi-model worker adapters require separate Windows
qualification. File contents are flushed; process-recovery tests are not proof of
power-loss durability on Windows.

## Script distribution with an approved Python

A second Windows route installs agent-bios as scripts and data without a custom
EXE launcher or an EXE installer. It targets organizations whose application
control permits PowerShell and CPython but blocks unrecognized executables. The
Windows workflow builds and exercises this route on every change; the Windows
script release workflow publishes it as a GitHub release whose page carries the
one-line PowerShell command for that exact release.

Releases come in two channels. A stable release is Authenticode-signed with the
project's release signing identity and installs with the line below. Until a
stable release exists, this line downloads nothing, because GitHub resolves the
latest release only among stable releases.

```text
$d = Join-Path $env:TEMP ('agent-bios-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $d | Out-Null; curl.exe -fsSL --proto '=https' --proto-redir '=https' -o "$d\install.ps1" "https://github.com/kangminlee-maker/agent-bios/releases/latest/download/install.ps1"; if ($LASTEXITCODE -ne 0) { throw 'download failed' }; & "$d\install.ps1"
```

A preview release is published as a prerelease without a signing identity. Its
bootstrap refuses to run unless the caller adds `-AcceptUnsignedPreview`, and
it prints a warning when accepted; the manifest and asset hashes pinned inside
the script are still enforced. Each preview release page carries its own
tag-pinned command with that flag. Both channels require an execution policy
that permits scripts, such as RemoteSigned; neither the bootstrap nor the
installed commands change the policy.

A signed PowerShell bootstrap verifies a pinned release manifest, the application
archive and its hashes before any downloaded code runs. It reuses an approved
CPython 3.13 x64 installation found on the machine, or provisions the pinned
official embeddable runtime into an application-private folder. Neither an
existing Python nor its packages are modified. The bootstrap adds the command
directory to the current PowerShell session, so `agent-bios` and `agent-launch`
work without reopening the terminal; other open terminals are unaffected.

The installed commands are static signed wrappers, `agent-bios.ps1` and
`agent-launch.ps1`, that read a local deployment binding and run the bundled
application through the bound interpreter. `agent-bios uninstall` removes owned
commands, shortcuts and the owned PATH entry; private instructions, session
records and any preexisting Python are retained.

This route is qualified on the Windows workflow runner in PowerShell 5.1 and 7
with runner-only test signing, and the release workflow re-runs that
qualification on the exact assets before it publishes them and then verifies
the published command anonymously. Validation on a policy-managed machine is a
separate step that no workflow establishes. Executable code still runs:
PowerShell, curl and Python, plus native modules inside the dependency bundle.
Migration of an existing EXE installation into this route is refused rather
than attempted.
