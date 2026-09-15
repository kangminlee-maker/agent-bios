---
created_at: 2026-09-15T16:42:00+09:00
head: 95fa287
kind: design
supersedes: 2026-09-15T1604--37f7a90--script-route-implementation-handoff.md
---

# Windows script distribution — release channels and the public one-line command

The handoff at 37f7a90 listed a published GitHub release and a public one-line
command among the items the tree did not establish, and the user confirmed that no
release code-signing certificate exists yet. This record states how the route is
published without one, and what that publication does and does not prove. It is
written against `head`; the implementation lands in the commit after it.

## Channels

| Channel | Signing | Bootstrap behaviour | Release form |
| --- | --- | --- | --- |
| `test` | runner-only self-signed identity | verifies signatures | never published; CI qualification only |
| `preview` | none; `script_signer_thumbprints` is empty | refuses to run without `-AcceptUnsignedPreview`, warns when accepted, skips only the three signature checks | GitHub prerelease, tag `windows-script-v<version>-preview.<n>` |
| `stable` | release identity from repository secrets, RFC 3161 timestamped | verifies signatures; refuses the preview flag | GitHub release marked latest, tag `windows-script-v<version>` |

The two trust policies cannot cross. A signed bootstrap rejects a manifest whose
signer list is empty; an unsigned bootstrap rejects a manifest that names a signer
or a channel other than `preview`. Both are negative controls in the smoke suite.

What the preview channel gives up is exactly one link: the bootstrap file itself
is not verified before it runs. Everything after it stays pinned — the manifest
hash is embedded in the script, the manifest pins the application and runtime
archives, the runtime's Python must carry an approved publisher signature, and
the caller-side `-ManifestSha256` pin used by the qualification suite is still
honoured. A user who pastes the preview command is told this in the release
notes and by the warning.

## Where the public command lives

The release workflow (`.github/workflows/release-windows.yml`, `workflow_dispatch`
with `channel` and `tag`) builds the bundle with its asset URLs pinned to the tag,
re-runs the full qualification on the exact assets it will publish — the smoke
driver serves a release bundle's assets locally because the tag is not published
while it is being judged — creates the immutable release with generated notes,
downloads every asset anonymously and compares digests, and then runs the
published one-line command in Windows PowerShell 5.1 with `-NoLaunch` and a
scratch root, followed by `agent-bios verify` and `uninstall`.

The one-line command's shape has one owner, `one_line_command()` in
`packages/windows/build-script-bundle.py`. The release notes carry the tag-pinned
form; `docs/windows.md` carries the metadata-derived `releases/latest/download`
form, admitted by `gates/check-hygiene.py` as a public install request so that
both the author identifier and the URL are excused only on that exact line.
GitHub resolves `latest` among stable releases only, so the documented command
downloads nothing until a stable release exists, and the docs say so.

## Not established by this design

- Approval by an organization's application-control or execution policy. The
  route needs a policy that permits scripts (RemoteSigned, or AllSigned with the
  stable signer trusted); nothing here changes a policy.
- A stable release. The workflow's stable path is implemented and refuses to run
  without the `WINDOWS_CODESIGN_PFX_BASE64` and `WINDOWS_CODESIGN_PFX_PASSWORD`
  secrets; it has not been exercised, because no identity exists.
- Migration of an Inno-managed installation, and collection of retained
  `releases/<digest>` and `runtimes/<digest>` trees after uninstall
  (D-20260915-371664) — unchanged from the handoff.

Decision: D-20260915-5dc4cd, "Windows script releases publish an
unsigned preview channel …" in `decisions/decisions.jsonl`.
