"""Public-command construction contracts; Windows CI exercises actual PowerShell rejection."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import unittest


BUILDER_PATH = Path(__file__).resolve().parents[1] / "packages/windows/build-script-bundle.py"
SPEC = importlib.util.spec_from_file_location("windows_script_release_builder", BUILDER_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


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


if __name__ == "__main__":
    unittest.main()
