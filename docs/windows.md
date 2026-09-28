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

The repository's GitHub Pages installation page also provides a shorter command
at a fixed address. It names `powershell` and relaxes that process's execution
policy, so it runs from the Command Prompt and the Run box as well as from an open
PowerShell, and on a machine whose policy nobody changed. It saves the script to a
unique temporary path and executes it. This convenience command trusts the HTTPS
site for the initial script; it does not check that script's hash before execution.
Dependent downloads still undergo the installer's checks. The fixed address
serves an explicitly promoted release, so publishing another release does not
silently change it. Preview commands retain `-AcceptUnsignedPreview`.

The same page carries a `curl` one-liner for macOS and Linux. That route is not
this Windows distribution: it installs the published npm package, which needs
Node.js and python3 already present, and then names the command that deploys the
work environment rather than opening its chooser over a pipe.

Releases come in two channels. A stable release is Authenticode-signed with the
project's release signing identity. Copy the version-specific command from its
release page: the command carries the SHA-256 of that final bootstrap and the
approved signer thumbprint, and checks both before invoking the saved script.
The generic latest URL is not an execution command: a moving asset cannot match
a fixed digest indefinitely. Release publication generates the command only after
all script signing is complete.

A preview release is published as a prerelease without a signing identity. Its
bootstrap refuses to run unless the caller adds `-AcceptUnsignedPreview`, and
it prints a warning when accepted; the manifest and asset hashes pinned inside
the script are still enforced. New preview release pages carry a tag-pinned command with that flag and a
bootstrap digest check before execution. Older preview pages may require the user
to compare the published bootstrap digest separately; their assets are not rewritten. Each published
command relaxes the execution policy for the process it starts, because a machine
nobody configured refuses scripts under the default Restricted policy. Neither
that relaxation nor anything installed edits the machine's saved policy, and a
policy imposed by a domain still refuses: the invocation's own error names it.

After caller-side verification, the bootstrap verifies the pinned release manifest
and dependent archives before running downloaded application or runtime code. It reuses an approved
CPython 3.13 x64 installation found on the machine, or provisions the pinned
official embeddable runtime into an application-private folder. Neither an
existing Python nor its packages are modified. The bootstrap adds the command
directory to the current PowerShell session, so `agent-bios` and `agent-launch`
work without reopening the terminal; other open terminals are unaffected.

The installed commands are static signed wrappers, `agent-bios.ps1` and
`agent-launch.ps1`, that read a local deployment binding and run the bundled
application through the bound interpreter. Beside each one the installer writes a
generated `.cmd` shim, because Windows does not treat `.ps1` as executable: without
the shim the PATH entry serves PowerShell alone and `agent-bios` is unavailable in
the Command Prompt, the Run box, and to any program that spawns a command. The
shim is generated rather than shipped since Authenticode cannot sign a `.cmd`; its
bytes are fixed and recorded in the deployment's ownership inventory, so a modified
shim is refused exactly like a modified command. `agent-bios uninstall` removes owned
commands, shims, shortcuts and the owned PATH entry; private instructions, session
records and any preexisting Python are retained.

This route is qualified on the Windows workflow runner in PowerShell 5.1 and 7
with runner-only test signing, and the release workflow re-runs that
qualification on the exact assets before it publishes them and then verifies
the published command anonymously. Validation on a policy-managed machine is a
separate step that no workflow establishes. Executable code still runs:
PowerShell, curl and Python, plus native modules inside the dependency bundle.
Migration of an existing EXE installation into this route is refused rather
than attempted.
