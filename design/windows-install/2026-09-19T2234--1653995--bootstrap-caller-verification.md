---
created_at: 2026-09-19T22:34:48+09:00
head: 1653995
kind: review
---

# Verify the downloaded Windows bootstrap before invoking it

The resumed implementation already has a passing Windows script route and a public
preview release, windows-script-v0.19.2-preview.1. Anonymous downloads on this date
matched the published asset digests and the tested source commit 1653995.

Independent review found one remaining contract error in the signed public-command
path: a downloaded script verified itself only after invocation. That cannot reject
a replacement bootstrap that omits its own verification. The preview channel already
disclosed its initial unsigned-source trust; that disclosure does not establish the
stronger signed-channel promise.

The generator now embeds the digest of the final signed bootstrap in the caller's
command. The caller checks transfer success, that digest, and (for signed channels)
Valid Authenticode status plus the pinned release signer before invoking the script.
The preview command also pins a digest, while retaining explicit unsigned acceptance.
Initial trust remains in the release page/command the user elects to use.

A generic moving latest execution command cannot retain one fixed digest indefinitely.
Documentation directs users to the version-specific generated command. Stable latest
asset discovery may still be checked without executing its downloaded contents.
Existing release assets and notes are not changed by this source revision.

The Windows driver exercises the generated validation and invocation, substituting
only the download transport with controlled local fixture bytes. Positive signed and
preview controls write a marker. Full replacement, invalid signature, wrong signer
and preview digest mismatch must fail before any marker is written. Local tests check
construction only and are not reported as Windows execution evidence.

No production signing certificate is available. This change neither publishes a new
release nor establishes permission under any organization's endpoint policy.
