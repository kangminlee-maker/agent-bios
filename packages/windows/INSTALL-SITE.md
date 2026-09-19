# Fixed Windows installation address

The installation site makes the same work environment easier to acquire on a
new Windows machine. It preserves the existing environment selection, personal
state and installation authority boundaries.

The public entry point is `https://kangminlee-maker.github.io/agent-bios/`.
Its `install.ps1` path serves the exact bytes of one published release asset.
`bootstrap.json` records the promoted release and bootstrap SHA256. The index
provides the corresponding short PowerShell command.

## Promote a release

1. Publish and qualify the Windows script release through the existing release
   workflow. This site does not create a new application release.
2. Set the release tag and final bootstrap digest in `install-site.json`. Take
   the digest from the verified release artifacts, not a mutable latest URL.
3. Run `python3 packages/windows/build-install-site.py`. The builder downloads
   the immutable asset over HTTPS and refuses a digest mismatch. Review
   `dist/install-site/` and commit through the normal repository gates.
4. Push to `feat/windows-native` (or `main` after integration). The installation
   address workflow deploys only the generated distribution files. It then
   downloads the public script anonymously on Windows, verifies the digest and
   parses it with Windows PowerShell 5.1.

Pages uses the GitHub Actions build type and the `github-pages` environment.
Only the designated publishing branches should be admitted by that environment.
The workflow needs `pages: write` and `id-token: write` for its deployment job;
it has no release-publication permission. No custom domain is configured.

A failed public check requires inspecting the deployment; it does not roll back
automatically. To roll back deliberately, restore the previous pointer and
redeploy. CDN caches can briefly retain the previous complete, pinned script.

## Initial trust

The short command trusts the HTTPS Pages origin for its initial downloaded
script. A deployment-time digest check proves that the promoted asset matched
the recorded release, not that each caller independently verified it. Keep the
version-specific, caller-verified command available on the release page for
people who need that contract. Older release pages may require a separate hash
comparison; the site does not rewrite their immutable assets or release notes.

The preview flag remains explicit. Neither the site nor its command changes
execution policy, evaluates downloaded strings, or treats a script's self-check
as verification before its execution. Moving this address from preview to stable
also changes the displayed command to omit the preview-only flag.
