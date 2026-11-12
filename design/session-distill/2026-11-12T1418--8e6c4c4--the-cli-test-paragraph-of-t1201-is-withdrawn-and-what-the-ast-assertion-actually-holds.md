---
created_at: 2026-11-12T14:18:00+09:00
head: 8e6c4c4          # the commit the content was true at
kind: review
supersedes: 2026-11-11T1252--8cdc56e--two-self-test-runs-wrote-into-the-owners-real-home-and-what-each-one-proved.md
---

# The CLI-test paragraph of T1201 is withdrawn, and what the AST assertion actually holds

`…T1252--8cdc56e--…-and-what-each-one-proved.md` ended its opening with "Everything else in T1201
stands." That sentence was too wide, and review Z (WP-22a round 1) was right to say so. T1201
describes an approach that did not ship, and T1252's own description of the control that replaced it
is narrower than its wording suggests. Both are corrected here; neither earlier record is edited,
because a dated record is written once (`AGENTS.md` §2).

## What is withdrawn from T1201

T1201's paragraph on the unresolvable home says:

> Two controls run the real CLI in a real process with no `$HOME` and a `pwd` whose lookup raises:
> told a destination it runs, and not told one it refuses `DEFAULT_OUT_UNRESOLVED` by name rather
> than printing a traceback.

**Those two controls are not what shipped.** T1252 records why: a real CLI process cannot have
`pwd`'s lookup raise, because `pwd` is a built-in module and nothing on the filesystem can shadow
it — the stub has to be installed into `sys.modules`, which means in-process, which means there is
no second process to run. The control that replaced them stubs `pwd` in process and resolves no
destination at all. T1252 said this about the SECOND run's lesson and left T1201's paragraph
standing beside it, so a reader of the two together could still believe two real CLI processes
exercise the no-account case. They do not, and that paragraph is withdrawn.

What remains true in that paragraph: the value is resolved through a function that cannot fail and
answers `None`; every consumer already takes `None` as its default; an unresolvable home therefore
masks exactly what the redaction floor's own default masks. Only the sentence about two real CLI
processes is withdrawn.

## What the AST assertion actually holds

T1252 says the AST assertion holds that "no statement of the module's top level asks for a home at
all". Read against the code, that is wider than the assertion. What it holds is narrower and worth
stating exactly, because the next person to rely on it will rely on the words:

- It is an assertion about the module's **top-level statements only**, and it excludes every
  `FunctionDef`, `AsyncFunctionDef` and `ClassDef` node whole. A default argument in a function
  signature is evaluated at import and sits inside a `FunctionDef`, so it is outside this
  assertion; so is anything in a class body.
- It matches **two attribute names**, `home` and `expanduser`, anywhere inside an admitted
  statement. It is an attribute test, so a home asked for in another shape is not matched:
  `os.environ["HOME"]` is a subscript, a bare `expandvars` is a different name, and another
  library's home helper is whatever that library calls it. Each of those would have to be added to
  the two names before this assertion sees it.
- It cannot see a home resolved during the import of another module. The property it protects is
  "importing this module does not ask the operating system who the user is", and that property
  holds for this module's own top level.

The guarded wrapper around the suite is likewise narrower than "the suite cannot write outside its
scratch": it names the control that was in flight when an exception escaped, so a crash reports a
control rather than a traceback. It does not confine writes. The confinement is the fixture seam and
the before/after comparison of exactly `<real home>/.local/state/agent-bios`, both of which T1252
describes correctly.

## Why this is a separate record rather than an edit

Two earlier records are claims about earlier trees, and each is right about the tree it names. The
defect was a forward-looking sentence — "everything else stands" — that kept a superseded paragraph
alive, and a description that rounded an assertion up to the property it protects. A correction
that rewrote them would leave no trace of either mistake, and the mistake is the part worth keeping:
a record that blesses a neighbouring record wholesale is making a claim it did not check.
