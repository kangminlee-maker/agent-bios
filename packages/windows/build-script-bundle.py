"""Build signed script-distribution test/release assets on Windows; never publish."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
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


def sign(path, thumbprint):
    code = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
    code += '$cert=Get-Item ' + ps_quote('Cert:\\CurrentUser\\My\\'+thumbprint) + ';'
    code += '$r=Set-AuthenticodeSignature -FilePath '+ps_quote(path)+' -Certificate $cert -HashAlgorithm SHA256;'
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
    parser.add_argument('--signer-thumbprint',required=True)
    parser.add_argument('--channel',choices=['test','stable'],default='test')
    parser.add_argument('--public-base-url')
    args=parser.parse_args()
    if os.name!='nt' or sys.version_info[:2]!=(3,13):
        parser.error('Windows CPython 3.13 is required to build the qualified dependency ABI')
    if args.channel=='stable' and not args.public_base_url:
        parser.error('stable requires an explicit release-pinned public base URL')
    cert=json.loads(powershell("$c=Get-Item "+ps_quote('Cert:\\CurrentUser\\My\\'+args.signer_thumbprint)+";@{subject=$c.Subject;thumbprint=$c.Thumbprint}|ConvertTo-Json -Compress"))
    if args.channel=='stable' and 'TEST ONLY' in cert['subject']:
        raise RuntimeError('test signing identities cannot build stable assets')
    out=ROOT/'dist/windows-script'
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
    for source in (ROOT/'packages/windows/commands').glob('*.ps1'):
        target=commands/source.name;shutil.copy2(source,target);sign(target,args.signer_thumbprint)
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
    for binary in [*expanded.glob('*.exe'),*expanded.glob('*.dll'),Path(sys.executable)]:
        info=signature(binary)
        if info['status']!='Valid' or not any(name in info['subject'] for name in ['Python Software Foundation','Microsoft Corporation']):
            raise RuntimeError('unapproved runtime signature: '+str(binary)+' '+str(info))
        signers.add(info['thumbprint'])
    def url(name):return args.public_base_url.rstrip('/')+'/'+name if args.public_base_url else name
    manifest={'schema_version':1,'channel':args.channel,'version':meta['version'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'platform':'windows-x64','archive':{'url':url('application.zip'),'size':appzip.stat().st_size,'sha256':digest(appzip)},
        'runtime':{**runtime,'source_url':runtime['url'],'architecture':'x64','url':url('runtime.zip'),'python_sha256':digest(expanded/'python.exe'),'publisher_thumbprints':sorted(signers)},
        'script_signer_thumbprints':[args.signer_thumbprint.upper()]}
    manifestpath=out/'release.json';manifestpath.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    template=(ROOT/'packages/windows/script-install.ps1').read_text(encoding='utf-8')
    content=template.replace('__AGENT_BIOS_MANIFEST_URL__',url('release.json')).replace('__AGENT_BIOS_MANIFEST_SHA256__',digest(manifestpath)).replace('__AGENT_BIOS_SCRIPT_SIGNERS__',json.dumps(manifest['script_signer_thumbprints'],separators=(',',':')))
    install=out/'install.ps1';install.write_text(content,encoding='utf-8-sig',newline='\r\n');sign(install,args.signer_thumbprint)
    (out/'checksums.json').write_text(json.dumps({p.name:digest(p) for p in [appzip,runtimezip,manifestpath,install]},indent=2),encoding='utf-8')
    print(json.dumps({'channel':args.channel,'manifest':str(manifestpath),'manifest_sha256':digest(manifestpath),'script':str(install)}))

if __name__=='__main__':main()
