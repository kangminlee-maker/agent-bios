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

The preview flag remains explicit. The Windows command relaxes the execution policy
for the one process it starts and names the interpreter, so it runs on an
unconfigured machine and from cmd.exe or the Run box; the machine's saved policy is
not edited and a domain-imposed policy still refuses. Neither command evaluates a
downloaded string, and neither treats a script's self-check as verification before
its execution. Moving this address from preview to stable also changes the displayed
command to omit the preview-only flag.

## macOS and Linux

The same address serves `install.sh`, which is `packages/posix/install.sh` byte for
byte. It installs the published latest npm release and stops: deployment is
`agent-bios install`, whose chooser needs a terminal that `curl | bash` does not
provide. The bootstrap edits no shell profile and installs no package manager, and
it reports the case npm leaves behind -- a successful global install whose command
the caller's PATH does not carry.

**This route pins nothing, and that is the difference between the two.** The Windows
bootstrap carries the release assets' own digests, so which release it installs is
part of what it verifies, and promotion is a deliberate step. This one carries no
digests: npm resolves the version and checks the tarball. A version pinned here
would add a promotion step to every publish whose omission serves an old release
silently, so the script prints the version it installed instead -- which is also
where a stale registry packument becomes visible.

Publishing to npm therefore needs no action on this site. The workflow derives the
expected bytes from the checkout, downloads the public script anonymously, compares
the digest, parses it, and requires its refusal path to refuse.
