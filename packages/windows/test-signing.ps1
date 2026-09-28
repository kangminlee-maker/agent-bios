# This trust configuration exists ONLY in the ephemeral Windows CI runner.
# The machine stores are used because adding to the current user's Root store
# raises an interactive confirmation dialog; the hosted runner is administrative.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Test certificate generation is limited to GitHub Actions.' }
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=agent-bios CI TEST ONLY' -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddDays(2)
$public = Join-Path $env:RUNNER_TEMP 'agent-bios-test-signing.cer'
Export-Certificate -Cert $cert -FilePath $public | Out-Null
Import-Certificate -FilePath $public -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Import-Certificate -FilePath $public -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null
"AGENT_BIOS_TEST_SIGNER=$($cert.Thumbprint)" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
