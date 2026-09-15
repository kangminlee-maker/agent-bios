# Static release-signed command. Keep user-specific values in deployment.json.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$bindingFile = Join-Path (Split-Path -Parent $PSScriptRoot) 'deployment.json'
$binding = Get-Content -LiteralPath $bindingFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($binding.schema_version -ne 1 -or $binding.owner -cne 'agent-bios-windows-script') {
    throw 'agent-launch: unsupported or foreign deployment binding. Run the approved installer to repair it.'
}
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\') + '\'
foreach ($field in @('application_root', 'dependencies_root', 'commands_root')) {
    $value = [IO.Path]::GetFullPath([string]$binding.$field)
    if (-not $value.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "agent-launch: deployment $field escapes the installation root."
    }
}
if (-not [string]::Equals([IO.Path]::GetFullPath([string]$binding.commands_root).TrimEnd('\'),
        [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'agent-launch: this command belongs to a different deployment.'
}
$python = [string]$binding.python.path
if (-not [IO.Path]::IsPathRooted($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf) -or
    $binding.python.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
    (Get-FileHash -LiteralPath $python -Algorithm SHA256).Hash -ine $binding.python.sha256) {
    throw 'agent-launch: the bound Python is missing or changed. Run the approved installer to repair the binding.'
}
$privateNames = @('HOME', 'AGENT_BIOS_STATE_DIR', 'AGENT_BIOS_INSTRUCTIONS_DIR', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME')
$previousEnvironment = @{}
$selectedEnvironment = @{}
foreach ($property in @($binding.private_environment.PSObject.Properties)) {
    if ($privateNames -cnotcontains $property.Name -or $property.Value -isnot [string] -or
        -not [IO.Path]::IsPathRooted($property.Value)) {
        throw 'agent-launch: invalid saved private environment binding.'
    }
    $name = $property.Name
    $savedPath = [IO.Path]::GetFullPath($property.Value).TrimEnd('\')
    $currentPath = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ($null -ne $currentPath) {
        $expanded = [Environment]::ExpandEnvironmentVariables($currentPath.Trim('"'))
        if (-not [IO.Path]::IsPathRooted($expanded)) { throw "agent-launch: $name is not an absolute path." }
        $currentIdentity = [IO.Path]::GetFullPath($expanded).TrimEnd('\')
        $savedIdentity = $savedPath
        $currentResolved = Resolve-Path -LiteralPath $currentIdentity -ErrorAction SilentlyContinue
        $savedResolved = Resolve-Path -LiteralPath $savedIdentity -ErrorAction SilentlyContinue
        if ($currentResolved) { $currentIdentity = $currentResolved.ProviderPath.TrimEnd('\') }
        if ($savedResolved) { $savedIdentity = $savedResolved.ProviderPath.TrimEnd('\') }
        if (-not [string]::Equals($currentIdentity, $savedIdentity, [StringComparison]::OrdinalIgnoreCase)) {
            throw "agent-launch: $name differs from the saved deployment root; explicit root relocation is not supported."
        }
    }
    $previousEnvironment[$name] = $currentPath
    $selectedEnvironment[$name] = $savedPath
}
if ($selectedEnvironment.Count -ne $privateNames.Count) {
    throw 'agent-launch: the saved private environment binding is incomplete.'
}
$previousBinding = [Environment]::GetEnvironmentVariable('AGENT_BIOS_WINDOWS_BINDING', 'Process')
$previousConsoleEncoding = [Console]::OutputEncoding
$previousOutputEncoding = $OutputEncoding
try {
    $env:AGENT_BIOS_WINDOWS_BINDING = $bindingFile
    foreach ($name in $selectedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $selectedEnvironment[$name], 'Process')
    }
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
    $pythonArguments = @('-I', '-X', 'utf8', (Join-Path $binding.application_root 'compose/runtime_entry.py'),
        '--dependencies', $binding.dependencies_root, '--script')
    $pythonArguments += @((Join-Path $binding.application_root 'compose/native_cli.py'), 'launch') + @($args)
    if ($MyInvocation.ExpectingInput) { $input | & $python @pythonArguments }
    else { & $python @pythonArguments }
    $global:LASTEXITCODE = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('AGENT_BIOS_WINDOWS_BINDING', $previousBinding, 'Process')
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
    [Console]::OutputEncoding = $previousConsoleEncoding
    $OutputEncoding = $previousOutputEncoding
}
