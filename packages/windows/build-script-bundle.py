"""Build signed script-distribution test/release assets on Windows; never publish."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def shell_environment():
    # A pwsh 7 parent exports its own PSModulePath; Windows PowerShell 5.1 then cannot
    # auto-load Microsoft.PowerShell.Security (Cert: drive, Authenticode cmdlets).
    return {key: value for key, value in os.environ.items() if key.upper() != 'PSMODULEPATH'}


def powershell(script):
    p = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference='Stop';" + script],
                       capture_output=True, text=True, encoding='utf-8', env=shell_environment())
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return p.stdout.strip()


def sign(path, thumbprint, timestamp_server=None):
    code = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
    code += '$cert=Get-Item ' + ps_quote('Cert:\\CurrentUser\\My\\'+thumbprint) + ';'
    code += '$r=Set-AuthenticodeSignature -FilePath '+ps_quote(path)+' -Certificate $cert -HashAlgorithm SHA256'
    # An RFC 3161 counter-signature keeps a stable signature valid after the certificate expires.
    code += (' -TimestampServer '+ps_quote(timestamp_server) if timestamp_server else '')+';'
    code += "if($r.Status -ne 'Valid'){throw ('Signing failed: '+$r.Status)}"
    powershell(code)


def signature(path):
    code = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$s=Get-AuthenticodeSignature -LiteralPath "+ps_quote(path)+";"
    code += '@{status=[string]$s.Status;thumbprint=$s.SignerCertificate.Thumbprint;subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress'
    return json.loads(powershell(code))


def archive(source, destination):
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(source.rglob('*')):
            if p.is_file():
                z.write(p,p.relative_to(source).as_posix())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--signer-thumbprint',help='required for test and stable; forbidden for preview')
    parser.add_argument('--channel',choices=['test','stable','preview'],default='test')
    parser.add_argument('--public-base-url',help='release-pinned asset base URL (required for stable and preview)')
    parser.add_argument('--command-base-url',help='base URL shown in the one-line command; defaults to the public base')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/windows-script')
    parser.add_argument('--timestamp-server',help='RFC 3161 timestamp server URL; required for stable')
    args=parser.parse_args()
    if os.name!='nt' or sys.version_info[:2]!=(3,13):
        parser.error('Windows CPython 3.13 is required to build the qualified dependency ABI')
    if args.channel in ('stable','preview') and not args.public_base_url:
        parser.error(args.channel+' requires an explicit release-pinned public base URL')
    if args.public_base_url and not args.public_base_url.startswith('https://'):
        parser.error('the public base URL must use https')
    signed=args.channel!='preview'
    if signed and not args.signer_thumbprint:
        parser.error(args.channel+' assets must be signed; pass --signer-thumbprint')
    if not signed and args.signer_thumbprint:
        parser.error('preview assets are unsigned by definition; do not pass --signer-thumbprint')
    if args.channel=='stable' and not args.timestamp_server:
        parser.error('stable signatures must be timestamped; pass --timestamp-server')
    if signed:
        cert=json.loads(powershell("$c=Get-Item "+ps_quote('Cert:\\CurrentUser\\My\\'+args.signer_thumbprint)+";@{subject=$c.Subject;thumbprint=$c.Thumbprint}|ConvertTo-Json -Compress"))
        if args.channel=='stable' and 'TEST ONLY' in cert['subject']:
            raise RuntimeError('test signing identities cannot build stable assets')
    out=args.output.resolve()
    if out.exists(): shutil.rmtree(out)
    staged=out/'staged';package=staged/'package';deps=staged/'dependencies';commands=staged/'commands'
    package.mkdir(parents=True);deps.mkdir();commands.mkdir()
    meta=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    for name in [*meta['files'],'package.json','LICENSE']:
        if name=='provenance.json':continue
        source,target=ROOT/name,package/name
        if source.is_dir():shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-compile','--target',str(deps),'jsonschema==4.25.1','colorama==0.4.6'],check=True)
    # pip --target also emits console-script launchers (jsonschema.exe); the
    # application imports these packages and never runs their commands.
    for launchers in (deps/'bin',deps/'Scripts'):
        if launchers.is_dir():shutil.rmtree(launchers)
    for source in (ROOT/'packages/windows/commands').glob('*.ps1'):
        target=commands/source.name;shutil.copy2(source,target)
        if signed:sign(target,args.signer_thumbprint,args.timestamp_server)
    # Application payload must carry no custom or interpreter EXE.
    if list(staged.rglob('*.exe')):raise RuntimeError('unexpected executable in script application archive')
    appzip=out/'application.zip';archive(staged,appzip)
    runtime=json.loads((ROOT/'packages/windows/python-runtime.json').read_text())
    runtimezip=out/'runtime.zip'
    with urllib.request.urlopen(runtime['url'],timeout=90) as r:runtimezip.write_bytes(r.read())
    if runtimezip.stat().st_size!=runtime['size'] or digest(runtimezip)!=runtime['sha256']:
        raise RuntimeError('official Python runtime differs from pinned descriptor')
    expanded=out/'runtime-inspection';expanded.mkdir()
    with zipfile.ZipFile(runtimezip) as z:z.extractall(expanded)
    signers=set()
    for binary in [*expanded.glob('*.exe'),*expanded.glob('*.dll'),*expanded.glob('*.pyd'),Path(sys.executable)]:
        info=signature(binary)
        if info['status']!='Valid' or not any(name in info['subject'] for name in ['Python Software Foundation','Microsoft Corporation']):
            raise RuntimeError('unapproved runtime signature: '+str(binary)+' '+str(info))
        signers.add(info['thumbprint'])
    def url(name):return args.public_base_url.rstrip('/')+'/'+name if args.public_base_url else name
    manifest={'schema_version':1,'channel':args.channel,'version':meta['version'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'platform':'windows-x64','archive':{'url':url('application.zip'),'size':appzip.stat().st_size,'sha256':digest(appzip)},
        'runtime':{**runtime,'source_url':runtime['url'],'architecture':'x64','url':url('runtime.zip'),'python_sha256':digest(expanded/'python.exe'),'publisher_thumbprints':sorted(signers)},
        'script_signer_thumbprints':[args.signer_thumbprint.upper()] if signed else []}
    manifestpath=out/'release.json';manifestpath.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    template=(ROOT/'packages/windows/script-install.ps1').read_text(encoding='utf-8')
    content=template.replace('__AGENT_BIOS_MANIFEST_URL__',url('release.json')).replace('__AGENT_BIOS_MANIFEST_SHA256__',digest(manifestpath)).replace('__AGENT_BIOS_SCRIPT_SIGNERS__',json.dumps(manifest['script_signer_thumbprints'],separators=(',',':')))
    install=out/'install.ps1';install.write_text(content,encoding='utf-8-sig',newline='\r\n')
    if signed:sign(install,args.signer_thumbprint,args.timestamp_server)
    checksums={p.name:digest(p) for p in [appzip,runtimezip,manifestpath,install]}
    (out/'checksums.json').write_text(json.dumps(checksums,indent=2),encoding='utf-8')
    if args.public_base_url:
        (out/'release-notes.md').write_text(release_notes(args.channel,meta['version'],manifest['source_commit'],args.command_base_url or args.public_base_url,checksums,runtime,manifest['script_signer_thumbprints']),encoding='utf-8')
    print(json.dumps({'channel':args.channel,'manifest':str(manifestpath),'manifest_sha256':digest(manifestpath),'script':str(install)}))


def one_line_command(base,unsigned,*,bootstrap_sha256,signer_thumbprints=()):
    # These pins come from the builder after the bootstrap's final signing pass.
    # They must be checked by the caller, before any downloaded script can run.
    if not isinstance(bootstrap_sha256,str) or not re.fullmatch(r'[a-fA-F0-9]{64}',bootstrap_sha256):
        raise ValueError('the public command requires the final bootstrap SHA256')
    signers=tuple(signer_thumbprints)
    if any(not isinstance(signer,str) or not re.fullmatch(r'[a-fA-F0-9]{40}',signer) for signer in signers):
        raise ValueError('the public command requires valid signer thumbprints')
    if unsigned and signers:
        raise ValueError('an unsigned preview command cannot carry signing identities')
    if not unsigned and not signers:
        raise ValueError('a signed command requires pinned signing identities')
    flag=' -AcceptUnsignedPreview' if unsigned else ''
    script=base.rstrip('/')+'/install.ps1'
    command=("$d = Join-Path $env:TEMP ('agent-bios-' + [guid]::NewGuid().ToString('N')); "
            "New-Item -ItemType Directory -Path $d | Out-Null; "
            "curl.exe -fsSL --proto '=https' --proto-redir '=https' -o \"$d\\install.ps1\" \""+script+"\"; "
            "if ($LASTEXITCODE -ne 0) { throw 'download failed' }; "
            "if ((Get-FileHash -LiteralPath \"$d\\install.ps1\" -Algorithm SHA256 -ErrorAction Stop).Hash -ine "+ps_quote(bootstrap_sha256.lower())+") { throw 'bootstrap SHA256 mismatch' }; ")
    if not unsigned:
        approved='@('+', '.join(ps_quote(signer.upper()) for signer in sorted(set(signers)))+')'
        command+=("$s = Get-AuthenticodeSignature -LiteralPath \"$d\\install.ps1\" -ErrorAction Stop; "
                  "if ($s.Status -ne 'Valid' -or $null -eq $s.SignerCertificate -or "+approved+
                  " -inotcontains $s.SignerCertificate.Thumbprint) { throw 'bootstrap signer approval failed' }; ")
    return command+"& \"$d\\install.ps1\""+flag


def release_notes(channel,version,commit,command_base,checksums,runtime,signer_thumbprints=()):
    unsigned=channel=='preview'
    lines=['# agent-bios '+version+' for Windows ('+channel+' script distribution)','',
           'Source commit `'+commit+'`. Windows 10/11 x64, Windows PowerShell 5.1 or PowerShell 7.',
           'No custom EXE, npm, WSL or manual Python installation is required: the bootstrap reuses an',
           'approved CPython 3.13 x64 when one is installed and otherwise provisions the pinned official',
           'embeddable runtime '+runtime['version']+' into an application-private folder.','',
           '## Install (one line, PowerShell)','','```powershell',
           one_line_command(command_base,unsigned,bootstrap_sha256=checksums['install.ps1'],signer_thumbprints=signer_thumbprints),'```','',
           'The command verifies the bootstrap SHA256 printed in this release before invoking the saved script.',
           'Trust in this initial pin comes from the release page and command you choose to use.','']
    if unsigned:
        lines+=['**This preview is unsigned.** The release had no code-signing identity, so the bootstrap runs',
                'only with `-AcceptUnsignedPreview`. Use it where your organization accepts unsigned scripts from',
                'this source; the stable channel will be signed and needs no flag. Hashes pinned inside the',
                'script still guard the manifest, the application archive and the runtime archive.','']
    else:
        lines+=['The bootstrap and the installed commands are Authenticode-signed. Before invoking the bootstrap,',
                'the command also requires a valid signature from the pinned release signing identity.',
                'The bootstrap then verifies the pinned manifest and asset hashes before running the application.','']
    lines+=['## Verify','','| File | SHA256 |','|---|---|']
    lines+=['| `'+name+'` | `'+value+'` |' for name,value in checksums.items()]
    lines+=['','The command checks `install.ps1` against its pinned digest; the manifest hash is pinned inside the script.','',
            '## Not established by this release','',
            '- Approval by an organization policy or endpoint-protection product; a green workflow proves the',
            '  route on a hosted runner where PowerShell and Python are permitted.',
            '- Migration of an existing EXE installation: the bootstrap refuses an Inno-managed root.',
            '- `agent-bios uninstall` keeps retained release and runtime folders that older app bridges or',
            '  session snapshots may still reference.','',
            '## 한국어 요약','',
            '위 명령 한 줄을 PowerShell에 붙여 넣으면 됩니다. 별도 EXE·npm·WSL·Python 설치가 필요 없고,',
            '설치 후 같은 창에서 `agent-bios`를 바로 실행할 수 있습니다.'+
            (' 이 미리보기 빌드는 서명되지 않아 `-AcceptUnsignedPreview` 플래그가 필요합니다.' if unsigned else ' 스크립트는 서명되어 있습니다.'),'']
    return '\n'.join(lines)

if __name__=='__main__':main()
