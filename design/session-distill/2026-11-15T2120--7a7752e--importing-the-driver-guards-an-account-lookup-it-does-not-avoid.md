---
created_at: 2026-11-15T21:20:00+09:00
head: 7a7752e          # the commit the content was true at
kind: review
supersedes: none (it corrects one sentence of 2026-11-12T1418--8e6c4c4--the-cli-test-paragraph-of-t1201-is-withdrawn-and-what-the-ast-assertion-actually-holds.md, which stays as written)
---

# Importing the driver guards an account lookup; it does not avoid one

`…T1418--8e6c4c4--…-what-the-ast-assertion-actually-holds.md` ends its list of what the AST
assertion holds with: the property it protects is "importing this module does not ask the operating
system who the user is", and "that property holds for this module's own top level". Review Z (WP-22a
round 2, F7) showed that the second half is false, and it was false at 8e6c4c4 as well.

`session-distill/distill.py`'s top level runs `HOME = _diagnostic_home()`. That function calls
`pathlib.Path.home()` inside a `try` that catches `RuntimeError`, `OSError` and `KeyError` and returns
`None`. With `$HOME` set, `Path.home()` reads the variable. With `$HOME` unset, it asks the account
database (`pwd`), which is asking the operating system who the user is. So importing the driver can
perform that lookup; what the guard gives is that the import never **fails** for want of a home.

The AST assertion does not see this, and T1418's own description says why: it excludes every
`FunctionDef` whole, so the call to `Path.home` inside `_diagnostic_home` is outside it, and at the
top level the statement is a call to a bare name, not an attribute named `home` or `expanduser`. The
assertion holds what T1418 says it holds about its own scope. The sentence that rounded it up to the
property was wider than the assertion.

What stands:

- T1418's withdrawal of T1201's two-CLI-process paragraph.
- T1418's description of the assertion's scope: top-level statements only, two attribute names, and
  nothing about another module's import.

What is corrected: a guarded lookup is not the absence of a lookup. The accurate statement is
"importing `distill.py` does not fail when the home cannot be resolved; with `$HOME` unset it may
consult the account database once, through `_diagnostic_home`". Re-derive from
`grep -n "^HOME = \|def _diagnostic_home" session-distill/distill.py` before relying on either.
