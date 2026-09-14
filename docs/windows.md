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
