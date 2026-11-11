---
created_at: 2026-11-11T12:52:00+09:00
head: 8cdc56e          # the commit the content was true at
kind: review
supersedes: 2026-11-11T1201--a290437--a-control-wrote-into-the-owners-home-and-a-negation-hid-a-file-npm-still-ships.md
---

# Two self-test runs wrote into the owner's real home, and what each one proved

`…T1201--a290437--a-control-wrote-into-the-owners-home-and-a-negation-hid-a-file-npm-still-ships.md`
is the account of review Y's two rounds on WP-24. It names one run left in the owner's real home. A
second was found after it landed, and this record supersedes that one paragraph's subject only:
**there were two, by two different controls, and the second was written while fixing the first.**
Everything else in T1201 stands.

| when | run id | written by | why it reached the real home |
| --- | --- | --- | --- |
| 11:00:14 | `y2-relative-home` | the pre-commit hook of `a290437` | the relative-HOME control, with `$HOME` relative and `XDG_STATE_HOME` unset, took its destination from the password database — the one home a fixture environment cannot redirect |
| 11:55:29 | `y2-no-account` | a standalone `session-distill/distill.py --self-test`, run by hand in the WP-24 worktree | the FIRST draft of the round-2 no-account control put a `pwd.py` stub on the child's `PYTHONPATH`. `pwd` is a **built-in** module, so a file can never shadow it: the stub never applied, the child read the real password database, and with `$HOME` removed it declared there |

Each run left `run.json`, `amendments.jsonl` and `locks/declaration.lock` under
`~/.local/state/agent-bios/distill/runs/<run id>/`. The lead moved both aside as evidence; the paths
are absent again. Neither run was reading anything of the owner's — a declaration is written from a
fixture — but a suite that writes outside its scratch is a suite that can overwrite, and the first
one did it inside a commit hook, which is as unattended as this repo gets.

## What the second one taught that the first did not

The first says: a fixture `$HOME` does not redirect the password database. The second says something
narrower and easier to miss: **a built-in module cannot be stubbed from the filesystem.** `pwd`,
`posix`, `time` and the rest are compiled into the interpreter and resolved before `sys.path` is
consulted, so `PYTHONPATH=<dir with pwd.py>` changes nothing and reports nothing. The control looked
like it isolated the lookup and did not, and what it actually exercised was the real account.

The draft that followed stubbed `sys.modules["pwd"]` in a child that then ran the driver as
`__main__`. That works, and it is not what shipped either: `session-distill/runlib/dispatch.py`'s
closure check refuses a self-test that restarts the driver — `DISPATCH_UNRESOLVED` for a child
running a script written into scratch at runtime, `DYNAMIC_LOAD_UNDECLARED` for
`runpy.run_path` of a path the trace cannot resolve. Both refusals are right, and together they
closed this damage route by removing it.

## What the committed controls do instead

- The import-time property is asserted where it lives: `_diagnostic_home()` answers `None` rather
  than raising when `pwd`'s lookup fails (stubbed in `sys.modules`, in process), and an AST
  assertion holds that **no statement of the module's top level asks for a home at all**, so the
  next edit that puts such a call back fails in the suite. Neither control resolves a destination,
  so neither can write anywhere.
- The one control that still exercises the account-home fallback states the home it means through
  the production seam (`_password_home`), asserts the declaration landed at exactly that path inside
  its own scratch, and compares the names under exactly `<real home>/.local/state/agent-bios` before
  and after — never a walk of the home, never its contents.

## The rule this is evidence for

A control is a write. Before trusting one that exercises a fallback, ask which input the fallback
takes and whether a fixture can reach it: an environment variable can, a password database cannot, a
built-in module cannot. Where it cannot, the production code owes a seam, and the control owes an
assertion about **where the write landed** — the two controls that let the first residue through
both passed while it happened, because one checked a message and the other checked a path that was
never involved.
