#!/usr/bin/env python3
"""Secret-redaction floor — the ONE canonical secret scrubber for the repo.

Both flows that egress session-derived text redact through here, so the floor
is single-sourced (concept economy) rather than duplicated per call site:
  * heavy flow  — session-distill/digest.py (per-session digests);
  * light flow  — learn/collect-learning.py (`learn!` prose + upload + the
    curator export downstream, since the server stores what it receives —
    redaction that does not happen HERE cannot be undone there).

`design/corpus-domain-packaging.md` declares this floor as an inherited
constraint ("the digest pipeline's secret-redaction carries over to harvest").
The patterns are deliberately conservative: kill obvious secrets/identifiers in
the `key: value` / `key=value` form and well-known token shapes, keep prose. A
`token`/`secret`/`bearer` word standing alone (no `:`/`=` + value) is NOT
touched, so lessons ABOUT tokens (e.g. "trust the X-Hook-Token header") survive.

This module has no side effects on import and is safe to load by path.
learn/redact.py is shipped in the npm package (package.json `files`) because
the shipped learn/collect-learning.py imports it at runtime.
"""
import re
import sys

# Conservative: kill obvious secrets/identifiers, keep prose.
SECRET_RE = [
    # The optional scheme word is what makes the HEADER form work. `\S+` alone stopped at
    # `Bearer` and published the credential after it: `Authorization: Bearer <token>`
    # redacted to `<REDACTED> <token>`, which is the single most common way a secret
    # appears in a developer's terminal, and this floor is what stands between a captured
    # learning and an upload. The `=` form was always fully covered — the two spellings
    # of one header disagreeing is the defect, not the strictness.
    re.compile(r'(?i)(api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*'
               r'(?:(?:bearer|basic|digest|token)\s+)?\S+'),
    re.compile(r'sk-[A-Za-z0-9_-]{16,}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'eyJ[A-Za-z0-9_-]{20,}\.'),                       # JWT-ish
    re.compile(r'AKIA[0-9A-Z]{12,}'),                             # AWS key id
    re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),  # email
]
PLACEHOLDER = '<REDACTED>'


def redact(s):
    """Return `s` with obvious secrets/identifiers replaced by <REDACTED>.
    Falsy/non-str input is returned unchanged (callers may pass None)."""
    if not s or not isinstance(s, str):
        return s
    for r in SECRET_RE:
        s = r.sub(PLACEHOLDER, s)
    return s


def _self_test():
    """Prove each pattern fires and that clean prose survives; exits non-zero on
    any miss so the umbrella gate catches a regression in the floor."""
    must_redact = [
        ("api_key value", "my api_key=sk_live_ABCDEF0123456789 leaked", "sk_live_"),
        ("authorization value", "set authorization=topsecretvalue123 here", "topsecretvalue123"),
        # Both spellings of the SAME header, because only one of them used to work: the
        # `=` form was fully redacted while the wire form published its credential.
        ("authorization header form", "Authorization: Bearer opaque0123456789abcdef", "opaque0123456789abcdef"),
        ("authorization header lowercase", "authorization: bearer abcdef0123456789xyz", "abcdef0123456789xyz"),
        ("authorization header inside a command",
         "curl -H 'Authorization: Bearer wire9876543210value'", "wire9876543210value"),
        ("openai key", "used sk-abcdefghij0123456789 here", "sk-abcdefghij"),
        ("github token", "token ghp_abcdefghij0123456789klmn committed", "ghp_"),
        ("aws key id", "key AKIA0123456789ABCD in env", "AKIA0123456789"),
        ("jwt", "cookie eyJhbGciOiJIUzI1NiIsInR5cCI6.rest here", "eyJ"),
        ("email", "ping alice.dev@example.com about it", "alice.dev@example.com"),
    ]
    must_keep = [
        # a lesson ABOUT tokens/secrets, no `key: value` → untouched.
        "trust the X-Hook-Token header; the server derives identity from it",
        "the secret sauce is verifying the real dispatch path",
        "password rotation policy matters but state no value",
    ]
    checks = []
    for name, src, needle in must_redact:
        out = redact(src)
        checks.append((f"redacts {name}", PLACEHOLDER in out and needle not in out))
    for src in must_keep:
        out = redact(src)
        checks.append((f"keeps: {src[:32]}…", out == src))
    checks.append(("None passthrough", redact(None) is None))
    checks.append(("empty passthrough", redact("") == ""))

    failed = [name for name, ok in checks if not ok]
    if failed:
        for name in failed:
            print(f"redact --self-test: FAIL: {name}", file=sys.stderr)
        sys.exit(1)
    print(f"redact --self-test: OK ({len(checks)} redaction-floor checks)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        _self_test()
    else:
        # Filter mode: redact stdin → stdout (handy for ad-hoc use).
        sys.stdout.write(redact(sys.stdin.read()))
