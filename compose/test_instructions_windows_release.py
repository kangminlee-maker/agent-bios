"""Public-command construction contracts; Windows CI exercises actual PowerShell rejection."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


BUILDER_PATH = Path(__file__).resolve().parents[1] / "packages/windows/build-script-bundle.py"
SPEC = importlib.util.spec_from_file_location("windows_script_release_builder", BUILDER_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

SITE_SPEC = importlib.util.spec_from_file_location(
    "windows_install_site", BUILDER_PATH.with_name("build-install-site.py"))
site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(site)


class WindowsReleaseCommandTests(unittest.TestCase):
    base = "https://releases.example.invalid/windows-script-v1.2.3"
    bootstrap = b"# approved bootstrap fixture\r\nWrite-Output 'approved'\r\n"
    digest = hashlib.sha256(bootstrap).hexdigest()
    signer = "A1" * 20

    def command(self, *, unsigned=True, digest=None, signers=None):
        return builder.one_line_command(
            self.base, unsigned, bootstrap_sha256=self.digest if digest is None else digest,
            signer_thumbprints=(() if unsigned else (self.signer,)) if signers is None else signers,
        )

    def test_preview_rejects_transfer_or_hash_failure_before_invocation(self):
        command = self.command()
        steps = ("curl.exe ", "if ($LASTEXITCODE -ne 0)", "Get-FileHash -LiteralPath",
                 "throw 'bootstrap SHA256 mismatch'", '& "$d\\install.ps1" -AcceptUnsignedPreview')
        positions = [command.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("-Algorithm SHA256 -ErrorAction Stop", command)
        self.assertIn("-ine '" + self.digest + "'", command)
        self.assertNotIn("Get-AuthenticodeSignature", command)
        self.assertNotIn("Invoke-Expression", command)
        self.assertEqual(len(command.splitlines()), 1)

    def test_signed_command_requires_hash_and_approved_signature_before_invocation(self):
        command = self.command(unsigned=False)
        steps = ("Get-FileHash -LiteralPath", "Get-AuthenticodeSignature -LiteralPath",
                 "throw 'bootstrap signer approval failed'", '& "$d\\install.ps1"')
        positions = [command.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("$s.Status -ne 'Valid'", command)
        self.assertIn("$null -eq $s.SignerCertificate", command)
        self.assertIn("@('" + self.signer + "') -inotcontains $s.SignerCertificate.Thumbprint", command)
        self.assertIn('Get-AuthenticodeSignature -LiteralPath "$d\\install.ps1" -ErrorAction Stop', command)
        self.assertNotIn("-AcceptUnsignedPreview", command)

    def test_release_page_command_relaxes_only_this_process_before_it_invokes(self):
        # Pasted into an open PowerShell, so it cannot name the interpreter; the
        # policy is relaxed for the process and the machine is left as it was.
        command = self.command()
        relax = "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force"
        self.assertIn(relax, command)
        self.assertLess(command.index(relax), command.index("curl.exe "))
        for scope in ("-Scope CurrentUser", "-Scope LocalMachine", "-Scope MachinePolicy", "-Scope UserPolicy"):
            self.assertNotIn(scope, command)

    def test_full_replacement_has_different_digest_from_caller_pin(self):
        # This verifies the emitted guard's input, not PowerShell execution. The
        # Windows workflow checks that the real command rejects a replacement
        # before its marker-writing body runs.
        replacement = b"# no self-verification remains\r\nWrite-Output 'replacement'\r\n"
        for unsigned in (True, False):
            with self.subTest(unsigned=unsigned):
                command = self.command(unsigned=unsigned)
                guard = re.search(
                    r"Get-FileHash .*?\)\.Hash -ine '([0-9a-f]{64})'\) "
                    r"\{ throw 'bootstrap SHA256 mismatch' \}", command,
                )
                self.assertIsNotNone(guard)
                pinned = guard.group(1)
                self.assertEqual(hashlib.sha256(self.bootstrap).hexdigest(), pinned)
                self.assertNotEqual(hashlib.sha256(replacement).hexdigest(), pinned)
                self.assertLess(guard.end(), command.index('& "$d\\install.ps1"'))

    def test_empty_malformed_or_injected_digest_is_refused(self):
        for digest in ("", "a" * 63, "g" * 64, "a" * 64 + "'; Write-Output injected; '", 42):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "SHA256"):
                builder.one_line_command(self.base, True, bootstrap_sha256=digest)

    def test_signed_command_cannot_omit_or_inject_its_signing_identity(self):
        for signers in ((), ("",), ("G" * 40,), ("A" * 40 + "'; Write-Output injected; '",)):
            with self.subTest(signers=signers), self.assertRaisesRegex(ValueError, "sign"):
                self.command(unsigned=False, signers=signers)

    def test_preview_cannot_claim_a_signing_identity(self):
        with self.assertRaisesRegex(ValueError, "unsigned preview"):
            self.command(signers=(self.signer,))

    def test_release_notes_pin_final_bootstrap_bytes_instead_of_unsigned_predecessor(self):
        # A signature changes the bytes. Release notes receive the final digest
        # already computed by the builder after signing, not a template digest.
        final_digest = hashlib.sha256(self.bootstrap + b"# signature fixture\r\n").hexdigest()
        notes = builder.release_notes(
            "stable", "1.2.3", "source-commit", self.base,
            {"install.ps1": final_digest}, {"version": "3.13.15"}, (self.signer,),
        )
        command = notes.split("```powershell\n", 1)[1].split("\n```", 1)[0]
        self.assertIn("-ine '" + final_digest + "'", command)
        self.assertNotIn(self.digest, command)
        self.assertIn(self.signer, command)
        self.assertNotIn("before executing anything", notes)

    def test_preview_notes_disclose_the_source_of_initial_trust(self):
        notes = builder.release_notes(
            "preview", "1.2.3", "source-commit", self.base,
            {"install.ps1": self.digest}, {"version": "3.13.15"},
        )
        self.assertIn("Trust in this initial pin comes from the release page and command", notes)
        self.assertIn("**This preview is unsigned.**", notes)
        self.assertIn("-AcceptUnsignedPreview", notes)


class WindowsInstallSiteTests(unittest.TestCase):
    repository = "https://github.com/example/project"
    site_url = "https://example.github.io/project"
    bootstrap = b"# signature-sensitive fixture\r\nWrite-Output 'approved'\r\n"

    def config(self, preview=True):
        return {"tag": "windows-script-v1.2.3" + ("-preview.1" if preview else ""),
                "bootstrap_sha256": hashlib.sha256(self.bootstrap).hexdigest()}

    def test_corrupt_public_download_cannot_produce_a_site(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                site.build(self.config(), self.repository, self.site_url, b"replacement", output)
            self.assertFalse(output.exists())

    def test_promotion_preserves_exact_script_bytes_and_explicit_channel(self):
        for preview in (True, False):
            with self.subTest(preview=preview), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                config = self.config(preview)
                metadata = site.build(config, self.repository, self.site_url, self.bootstrap, output)
                self.assertEqual((output / "install.ps1").read_bytes(), self.bootstrap)
                self.assertEqual(metadata["bootstrap_sha256"], config["bootstrap_sha256"])
                self.assertIn("/releases/download/" + config["tag"] + "/", metadata["asset_url"])
                command = site.install_command(self.site_url, metadata["channel"])
                self.assertEqual("-AcceptUnsignedPreview" in command, preview)
                # Saved to a file, then invoked from it: a transfer that failed
                # halfway must not reach the invocation, and the file is what the
                # bootstrap authenticates itself from.
                self.assertIn("-ErrorAction Stop; & ", command)
                self.assertIn("[IO.Path]::GetTempPath()", command)
                self.assertNotIn("Invoke-Expression", command)
                self.assertEqual({p.name for p in output.iterdir()},
                                 {"install.ps1", "install.sh", "bootstrap.json", "index.html", ".nojekyll"})

    def test_fixed_address_command_starts_outside_powershell_under_the_default_policy(self):
        # A machine nobody configured refuses `& $p` under Restricted, and cmd.exe
        # or Win+R cannot enter a bare PowerShell program at all. Both are why the
        # command names the interpreter and relaxes the policy for that process.
        for channel in ("preview", "stable"):
            with self.subTest(channel=channel):
                command = site.install_command(self.site_url, channel)
                prefix = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
                self.assertTrue(command.startswith(prefix), command)
                self.assertTrue(command.endswith('"'), command)
                program = command[len(prefix):-1]
                # cmd.exe ends the argument at the first inner double quote, so the
                # quoted program must carry none; the URL regex alone does not say so.
                self.assertNotIn('"', program)
                # Pasted into PowerShell -- the commonest case -- the program sits
                # inside that shell's quotes and is expanded before the child starts.
                # A reported failure showed `$p = Join-Path $env:TEMP ...` arriving
                # as `= Join-Path C:\Users\...\Temp ...`: the variable was consumed
                # by the pasting shell, and nothing downstream could see it.
                self.assertNotIn("$", program)
                # The bootstrap authenticates itself through $PSCommandPath, which a
                # scriptblock built from downloaded text does not have, so the script
                # is saved and invoked as a file rather than evaluated.
                self.assertIn("-OutFile", program)
                self.assertNotIn("iex", program)
                self.assertNotIn("Invoke-Expression", program)
                self.assertEqual(len(command.splitlines()), 1)
                # Relaxing this process is not editing the machine's policy.
                self.assertNotIn("Set-ExecutionPolicy", command)

    def test_posix_bootstrap_installs_the_published_latest_and_reports_what_it_got(self):
        body = site.posix_bootstrap().decode("utf-8")
        # A version pinned here would need re-promoting after every publish, and a
        # forgotten promotion serves an old release with nothing to show for it.
        self.assertIn("npm install --global agent-bios@latest", body)
        self.assertNotIn("agent-bios@0.", body)
        # Which release 'latest' resolved to is then the only thing that says so --
        # a stale registry packument is visible exactly here and nowhere else.
        self.assertIn('note "installed agent-bios ${version', body)
        self.assertEqual(body, site.POSIX_BOOTSTRAP.read_text(encoding="utf-8"),
                         "the served script must be the authored one, byte for byte")

    @unittest.skipIf(os.name == "nt", "the POSIX bootstrap runs under bash")
    def test_posix_bootstrap_reports_the_installed_version_in_one_line(self):
        # A text check passed while the line was broken: agent-bios has no --version
        # command, so asking it printed "unknown command" and the whole help text where
        # the version belonged. Run the script against stubs and read what it says.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "global/agent-bios").mkdir(parents=True)
            (root / "global/agent-bios/package.json").write_text('{"name": "agent-bios", "version": "9.9.9"}')
            stubs = root / "bin"
            stubs.mkdir()
            (stubs / "npm").write_text(f'#!/bin/sh\ncase "$1" in root) echo "{root}/global";; esac\nexit 0\n')
            (stubs / "agent-bios").write_text('#!/bin/sh\necho "unknown command: $1"; echo "help text"; exit 2\n')
            (stubs / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
            for stub in stubs.iterdir():
                stub.chmod(0o755)
            done = subprocess.run(["bash", str(site.POSIX_BOOTSTRAP)], capture_output=True, text=True, timeout=60,
                                  env={**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}"})
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("agent-bios: installed agent-bios 9.9.9\n", done.stdout)
        self.assertNotIn("unknown command", done.stdout)
        self.assertNotIn("help text", done.stdout)

    def test_posix_command_installs_and_stops_before_the_interactive_step(self):
        command = site.posix_install_command(self.site_url)
        self.assertEqual(command, "curl -fsSL " + self.site_url + "/install.sh | bash")
        body = site.posix_bootstrap().decode("utf-8")
        # `curl | bash` hands the shell a pipe, so the chooser cannot be opened here;
        # saying which command opens it is what keeps the install from looking finished.
        self.assertIn("agent-bios install", body)
        self.assertNotIn("&& agent-bios install", body)
        # npm exits 0 having written a command the caller's PATH may not carry.
        self.assertIn("is not on PATH", body)
        for url in ("http://example.test", "https://example.test/';exit", "https://u:p@example.test"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                site.posix_install_command(url)

    def test_mutable_or_injected_source_and_install_urls_are_refused(self):
        for tag in ("latest", "windows-script-v1.2.3/../../main", "windows-script-v1.2.3';exit"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                site.release_identity({**self.config(), "tag": tag}, self.repository)
        for url in ("http://example.test", "https://example.test/';exit", "https://u:p@example.test",
                    "https://example.test/?q=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                site.install_command(url, "preview")


if __name__ == "__main__":
    unittest.main()
