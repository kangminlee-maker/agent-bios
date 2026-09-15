# Release builder fills these trust anchors before signing this saved script.
# Invoke the verified file with &, never by evaluating downloaded text.
[CmdletBinding(DefaultParameterSetName = 'Online')]
param(
    [Parameter(ParameterSetName = 'Online')]
    [string]$ManifestUrl = '__AGENT_BIOS_MANIFEST_URL__',
    [Parameter(Mandatory = $true, ParameterSetName = 'Local')]
    [string]$ManifestPath,
    [string]$ManifestSha256 = '__AGENT_BIOS_MANIFEST_SHA256__',
    [string]$InstallRoot,
    [string]$PythonPath,
    [switch]$PrivateRuntime,
    [switch]$NoRuntimeDownload,
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$approvedScriptSigners = @('__AGENT_BIOS_SCRIPT_SIGNERS__' | ConvertFrom-Json)
$stage = 'preflight'
$temporaryRoot = $null
$previousTls = [Net.ServicePointManager]::SecurityProtocol
$previousConsoleEncoding = [Console]::OutputEncoding
$previousOutputEncoding = $OutputEncoding

function Assert-Signature([string]$Path, [object[]]$Signers) {
    if (@($Signers).Count -eq 0) { throw 'No approved signing identity was supplied.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        @($Signers) -inotcontains $signature.SignerCertificate.Thumbprint) {
        throw "Signature approval failed for '$Path' ($($signature.Status)). Use the approved distribution or ask your administrator to approve its publisher."
    }
}

function Assert-Asset([string]$Path, [string]$Sha256, [long]$Size = -1) {
    if ($Sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'The expected SHA256 is missing or malformed.' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Asset is missing: $Path" }
    if ($Size -ge 0 -and (Get-Item -LiteralPath $Path).Length -ne $Size) {
        throw "Asset size does not match approved metadata: $Path"
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ine $Sha256) {
        throw "Asset SHA256 does not match approved metadata: $Path"
    }
}

function Receive-Asset([string]$Source, [string]$Destination, [string]$LocalBase = '') {
    if ($LocalBase -and -not [Uri]::IsWellFormedUriString($Source, [UriKind]::Absolute)) {
        $base = [IO.Path]::GetFullPath($LocalBase).TrimEnd('\') + '\'
        $path = [IO.Path]::GetFullPath((Join-Path $LocalBase $Source))
        if (-not $path.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Local asset paths must remain inside the explicit manifest directory.'
        }
        Copy-Item -LiteralPath $path -Destination $Destination
        return
    }
    $uri = $null
    if (-not [Uri]::TryCreate($Source, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo) { throw 'Asset downloads require an HTTPS URL without embedded credentials.' }
    $curl = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $curl) {
        & $curl.Source --fail --location --proto '=https' --proto-redir '=https' `
            --max-redirs 5 --connect-timeout 20 --max-time 600 --retry 2 `
            --silent --show-error --output $Destination --url $uri.AbsoluteUri
        if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit $LASTEXITCODE). No downloaded code was executed." }
    } else {
        # Handle redirects ourselves so Windows PowerShell cannot follow HTTPS to HTTP.
        for ($redirect = 0; $redirect -le 5; $redirect++) {
            $response = $null
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $uri.AbsoluteUri -OutFile $Destination `
                    -PassThru -MaximumRedirection 0 -TimeoutSec 600 -ErrorAction Ignore
            } catch {
                if ($null -eq $_.Exception.Response) { throw }
                $response = $_.Exception.Response
                if ([int]$response.StatusCode -lt 300 -or [int]$response.StatusCode -ge 400) { throw }
            }
            if ($null -eq $response) { throw 'Download returned no HTTP response.' }
            if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300) { return }
            if ([int]$response.StatusCode -lt 300 -or [int]$response.StatusCode -ge 400 -or $redirect -eq 5) {
                throw 'Download failed or exceeded the redirect limit.'
            }
            if ($response.GetType().FullName -eq 'System.Net.Http.HttpResponseMessage') {
                $location = [string]$response.Headers.Location
            } else { $location = [string]$response.Headers['Location'] }
            if (-not $location) { throw 'Download redirect omitted its destination.' }
            $uri = [Uri]::new($uri, $location)
            if ($uri.Scheme -ne 'https' -or $uri.UserInfo) { throw 'Download redirect violates the HTTPS-only policy.' }
        }
    }
}

function Expand-ApprovedZip([string]$Archive, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [void][IO.Directory]::CreateDirectory($Destination)
    $prefix = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    $total = [long]0
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    try {
        if ($zip.Entries.Count -gt 30000) { throw 'Archive contains too many entries.' }
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('/', '\')
            $segments = @($name.TrimEnd('\').Split('\'))
            if ([string]::IsNullOrWhiteSpace($name) -or [IO.Path]::IsPathRooted($name) -or
                $name.Contains(':') -or $name.Contains([char]0) -or
                (($entry.ExternalAttributes -shr 16) -band 0xf000) -eq 0xa000) {
                throw 'Archive contains an unsafe or linked path.'
            }
            foreach ($segment in $segments) {
                if ($segment -in @('', '.', '..') -or $segment.EndsWith('.') -or $segment.EndsWith(' ') -or
                    $segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)' -or
                    $segment.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
                    throw 'Archive contains an unsafe Windows filename.'
                }
            }
            $target = [IO.Path]::GetFullPath((Join-Path $Destination $name))
            if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or -not $seen.Add($target)) {
                throw 'Archive contains an escaping or duplicate path.'
            }
            $total += $entry.Length
            if ($total -gt 1073741824) { throw 'Expanded archive exceeds the one GiB limit.' }
            if ($name.EndsWith('\')) { [void][IO.Directory]::CreateDirectory($target); continue }
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
        }
    } finally { $zip.Dispose() }
}

function Get-ApprovedPython([string]$Candidate, [object[]]$Signers, [switch]$Required) {
    if (-not $Candidate) { return $null }
    $executionFailure = $false
    try {
        $full = [IO.Path]::GetFullPath($Candidate)
        if ($full -match '(?i)\\Microsoft\\WindowsApps\\' -or -not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw 'Microsoft Store aliases and missing interpreter paths are not usable Python installations.'
        }
        Assert-Signature $full $Signers
        $executionFailure = $true
        $probe = & $full -I -X utf8 -c "import json,sys,struct,platform; print(json.dumps(dict(version=list(sys.version_info[:3]),bits=struct.calcsize('P')*8,machine=platform.machine(),executable=sys.executable,implementation=sys.implementation.name)))"
        if ($LASTEXITCODE -ne 0) { throw "Python execution was denied or failed (exit $LASTEXITCODE)." }
        $info = ($probe -join "`n") | ConvertFrom-Json
        $executionFailure = $false
        if ($info.version[0] -ne 3 -or $info.version[1] -ne 13 -or $info.bits -ne 64 -or
            $info.machine -notin @('AMD64', 'x86_64') -or $info.implementation -ne 'cpython') {
            throw 'This release requires approved CPython 3.13 x64.'
        }
        if (-not [string]::Equals([IO.Path]::GetFullPath([string]$info.executable), $full, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Python resolved to a different executable than the approved candidate.'
        }
        return $full
    } catch {
        if ($Required -or $executionFailure) { throw }
        Write-Verbose "Python candidate not selected: $($_.Exception.Message)"
        return $null
    }
}

function Find-ApprovedPython([object[]]$Signers) {
    $candidates = [Collections.Generic.List[string]]::new()
    foreach ($name in @('python.exe', 'python3.exe')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            $candidates.Add($command.Source)
        }
    }
    foreach ($key in @('HKCU:\Software\Python\PythonCore\3.13\InstallPath',
                        'HKLM:\Software\Python\PythonCore\3.13\InstallPath')) {
        if (Test-Path -LiteralPath $key) {
            $item = Get-Item -LiteralPath $key
            $executable = [string]$item.GetValue('ExecutablePath')
            if (-not $executable) { $executable = Join-Path ([string]$item.GetValue('')) 'python.exe' }
            $candidates.Add($executable)
        }
    }
    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        $selected = Get-ApprovedPython $candidate $Signers
        if ($selected) { return $selected }
    }
    return $null
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
        -not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or
        $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'This release supports Windows x64 in 64-bit PowerShell only.' }
    if ($PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'PowerShell 5.1 or newer is required.' }
    if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage') {
        throw 'This installation requires an approved PowerShell FullLanguage session. Ask your administrator for an approved deployment; execution policy will not be changed.'
    }
    Assert-Signature $PSCommandPath $approvedScriptSigners
    if ($PrivateRuntime -and ($PythonPath -or $NoRuntimeDownload)) {
        throw '-PrivateRuntime cannot be combined with -PythonPath or -NoRuntimeDownload.'
    }
    if ($ManifestSha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'This bootstrap has no approved release manifest SHA256.' }
    if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\agent-bios-script' }
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('agent-bios-bootstrap-' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($temporaryRoot)
    [Net.ServicePointManager]::SecurityProtocol = $previousTls -bor [Net.SecurityProtocolType]::Tls12
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
    $stage = 'release metadata'
    $manifestFile = Join-Path $temporaryRoot 'release.json'
    $localBase = ''
    if ($PSCmdlet.ParameterSetName -eq 'Local') {
        if (-not $PSBoundParameters.ContainsKey('ManifestSha256')) { throw 'Local manifests require an explicit expected SHA256.' }
        $localBase = Split-Path -Parent ([IO.Path]::GetFullPath($ManifestPath))
        Copy-Item -LiteralPath $ManifestPath -Destination $manifestFile
    } else { Receive-Asset $ManifestUrl $manifestFile }
    Assert-Asset $manifestFile $ManifestSha256
    $manifest = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.platform -cne 'windows-x64' -or
        $manifest.version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$' -or
        $manifest.runtime.version -notmatch '^3\.13\.\d+$' -or $manifest.runtime.architecture -cne 'x64' -or
        @($manifest.script_signer_thumbprints).Count -eq 0 -or @($manifest.runtime.publisher_thumbprints).Count -eq 0) {
        throw 'Release metadata has an unsupported schema, version, platform or trust policy.'
    }
    foreach ($signer in @($manifest.script_signer_thumbprints)) {
        if ($approvedScriptSigners -inotcontains $signer) { throw 'Release metadata requests an unapproved script signer.' }
    }
    foreach ($asset in @($manifest.archive, $manifest.runtime)) {
        if ($asset.size -le 0 -or $asset.size -gt 536870912 -or $asset.sha256 -notmatch '^[a-fA-F0-9]{64}$') {
            throw 'Release metadata contains an invalid asset size or SHA256.'
        }
    }
    Write-Host "Installing agent-bios $($manifest.version) (Windows x64)."
    $stage = 'application acquisition'
    $archivePath = Join-Path $temporaryRoot 'application.zip'
    Receive-Asset $manifest.archive.url $archivePath $localBase
    Assert-Asset $archivePath $manifest.archive.sha256 $manifest.archive.size
    $source = Join-Path $temporaryRoot 'application'
    Expand-ApprovedZip $archivePath $source
    if (@(Get-ChildItem -LiteralPath $source -Filter '*.exe' -Recurse -File).Count -ne 0) {
        throw 'The script application archive must not contain custom executable launchers.'
    }
    foreach ($command in @('agent-bios.ps1', 'agent-launch.ps1')) {
        Assert-Signature (Join-Path $source "commands/$command") @($manifest.script_signer_thumbprints)
    }
    $package = Join-Path $source 'package'
    $dependencies = Join-Path $source 'dependencies'
    $packageMetadata = Get-Content -LiteralPath (Join-Path $package 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($packageMetadata.name -cne 'agent-bios' -or $packageMetadata.version -cne $manifest.version) {
        throw 'Application identity does not match the pinned release.'
    }
    $stage = 'approved Python resolution'
    $managedRuntime = $null
    if ($PythonPath) { $python = Get-ApprovedPython $PythonPath @($manifest.runtime.publisher_thumbprints) -Required }
    elseif ($PrivateRuntime) { $python = $null }
    else { $python = Find-ApprovedPython @($manifest.runtime.publisher_thumbprints) }
    if (-not $python) {
        if ($NoRuntimeDownload) { throw 'No approved CPython 3.13 x64 is available. Use your approved Python deployment or specify -PythonPath.' }
        Write-Host 'No compatible approved Python found. Preparing the pinned application-private Python runtime.'
        $stage = 'approved Python acquisition'
        $runtimeArchive = Join-Path $temporaryRoot 'python.zip'
        Receive-Asset $manifest.runtime.url $runtimeArchive $localBase
        Assert-Asset $runtimeArchive $manifest.runtime.sha256 $manifest.runtime.size
        $managedRuntime = Join-Path $temporaryRoot 'python'
        Expand-ApprovedZip $runtimeArchive $managedRuntime
        $python = Join-Path $managedRuntime 'python.exe'
        Assert-Asset $python $manifest.runtime.python_sha256
        $nativeFiles = @(Get-ChildItem -LiteralPath $managedRuntime -Recurse -File | Where-Object { $_.Extension -in @('.exe', '.dll', '.pyd') })
        if ($nativeFiles.Count -eq 0) { throw 'The Python archive contains no native runtime files.' }
        foreach ($file in $nativeFiles) { Assert-Signature $file.FullName @($manifest.runtime.publisher_thumbprints) }
        $python = Get-ApprovedPython $python @($manifest.runtime.publisher_thumbprints) -Required
    } else { Write-Host "Using approved Python: $python" }
    $stage = 'application deployment'
    $deployArguments = @('-I', '-X', 'utf8', (Join-Path $package 'compose/runtime_entry.py'), '--dependencies', $dependencies,
        '--script', (Join-Path $package 'compose/windows_deploy.py'), 'install', '--source', $source,
        '--root', $InstallRoot, '--python', $python)
    if ($managedRuntime) { $deployArguments += @('--managed-runtime', $managedRuntime) }
    $deploymentOutput = & $python @deployArguments
    if ($LASTEXITCODE -ne 0) { throw "Application deployment failed (exit $LASTEXITCODE)." }
    $deployment = ($deploymentOutput -join "`n") | ConvertFrom-Json
    $commandPath = Join-Path ([string]$deployment.commands_root) 'agent-bios.ps1'
    if (-not (Test-Path -LiteralPath $commandPath -PathType Leaf)) { throw 'Deployment did not return an installed command path.' }
    Assert-Signature $commandPath @($manifest.script_signer_thumbprints)
    $stage = 'current PowerShell command registration'
    $commandsRoot = [IO.Path]::GetFullPath([string]$deployment.commands_root).TrimEnd('\')
    $present = @($env:Path -split ';' | Where-Object { $_.TrimEnd('\') -ieq $commandsRoot }).Count -gt 0
    if (-not $present) { $env:Path = $commandsRoot + ';' + $env:Path }
    $resolved = Get-Command agent-bios -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $resolved -or $resolved.CommandType -ne 'ExternalScript' -or
        -not [string]::Equals($resolved.Source, $commandPath, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "Another command shadows agent-bios. It was preserved. Use: & '$($commandPath.Replace("'", "''"))'"
    }
    Write-Host "Application deployed: $($deployment.root)"
    if ($NoLaunch) {
        if ($deployment.configuration_pending) { Write-Host 'Configuration pending. Run agent-bios install when ready.' }
        else { Write-Host 'The saved environment has been retained and updated.' }
    } elseif ($deployment.configuration_pending) {
        $stage = 'first-time configuration'
        & $commandPath install
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Application remains installed; configuration did not complete (exit $LASTEXITCODE). Run agent-bios install to resume."
        }
    } else { Write-Host 'The saved environment has been retained and updated.' }
} catch {
    throw "agent-bios installation stopped during $stage. $($_.Exception.Message)"
} finally {
    [Net.ServicePointManager]::SecurityProtocol = $previousTls
    [Console]::OutputEncoding = $previousConsoleEncoding
    $OutputEncoding = $previousOutputEncoding
    if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
