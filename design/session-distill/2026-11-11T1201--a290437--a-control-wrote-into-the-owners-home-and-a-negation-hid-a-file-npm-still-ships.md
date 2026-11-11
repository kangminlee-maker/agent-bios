---
created_at: 2026-11-11T12:01:00+09:00
head: a290437          # the commit the content was true at
kind: review
supersedes: none
---

# A control wrote into the owner's home, and a `files[]` negation hid a file npm still ships

Review Y's two rounds on WP-24 (the driver ships). Round 1 returned `fix_then_accept` with three
major and five minor findings; round 2, on the three commits that answered them, confirmed all eight
present and returned `fix_then_accept` again with two major and two minor. This record is the
account of both rounds' fixes. The package record
`2026-11-11T0903--f236df6--the-driver-ships-and-three-refusals-that-could-not-fire.md` is dated and
unchanged; the figures it was missing are stated here, not inserted there.

## Round 2's two major findings

**A control of mine wrote into the owner's real home directory.** The relative-HOME control sets
`HOME=relative-home` with no `XDG_STATE_HOME`, so the destination comes from the password database —
the one home the suite could not state. It resolved the owner's actual account home, and a run
directory with `run.json`, `amendments.jsonl` and a declaration lock appeared under
`~/.local/state/agent-bios/distill/runs/y2-relative-home/` while a commit hook was running. Both of
the control's assertions passed anyway, because neither looked at where the declaration landed: one
asserted the "ignored" notice, the other that nothing appeared relative to the working directory.
The lead reproduced it and moved the residue aside.

The lookup is now a named seam, `_password_home()`, which `_account_home()` is the only caller of.
The control states the account home it means by replacing that function with one naming a directory
inside its own scratch, then asserts the declaration landed at exactly that path — the assertion the
control did not have. A canary reads the real account home's structure (names only, never contents)
before and after, and fails if anything arrived. The production resolver is still exercised for real
by a control of its own, and that production reaches the seam at all is asserted on
`_account_home`'s source text, so an edit that inlines the lookup again fails in the suite.

That last assertion has no revert row, and the reason is worth stating: reverting it has exactly one
observable, a run written into the owner's home, which is the defect the fix exists to prevent.
Provoking the harm to prove the guard against it is not a trade this record will make. The
assertion's subject is decidable text, which is why it can stand without one.

**A `files[]` negation hid a packed file from the content scans.** With `files[]` present, npm nulls
the root `.npmignore` and a negated entry is the only exclusion it honours — which is why the
payload carries three, all naming bytecode. But npm force-includes `README.md`, `LICENSE`, and the
`bin` and `main` targets whatever `files[]` says. Adding `!README.md` therefore removed README from
`gates/check-hygiene.py`'s subject set and from the endpoint scan that imports it, while npm and the
installer both still carried the file: the reviewer planted a forbidden organisation identifier and a
live collector endpoint in it and neither gate said anything, and the packlist comparison agreed
because the tarball did contain README.

A negation can only be safe where every path it can exclude is bytecode, and whether an arbitrary
pattern has that property is not decidable by inspection. So the supported negations are enumerated
instead, in `compose/instructions_install.py` (`SUPPORTED_NEGATIONS`, `negation_supported`), the
payload being the owner of what the payload implements. `gates/check-package.sh` imports that
predicate and refuses any other negation by name, `FILES_NEGATION_UNSUPPORTED <entry>`. The hygiene
derivation imports it too: an unsupported negation is reported and **not applied**, so its paths stay
scanned, and a supported one that ever matched something other than compiled Python keeps that
subject and reports the mismatch. A subject too many is a false finding a person reads; a subject too
few is a leak nobody sees.

The reviewer's second note on the same line is closed with it: the exclusion regex read an
unqualified pattern as gitignore does, matching a basename at any depth, while npm 12 expands a
`files[]` glob root-relative. `*.pyc` now names a compiled file beside `package.json` and the
any-depth form is `**/*.pyc`, with controls on all three readings.

## Round 2's two minor findings

**The driver could not start on a machine with no home.** `HOME = str(pathlib.Path.home())` ran at
import, before either startup boundary, and `Path.home()` raises when `$HOME` is unset and the
account has no password-database entry. On such a machine nothing ran — not `--out DIR`, not
`--help`. The value is now resolved through a function that cannot fail and answers `None`, which is
what every consumer of it already takes as its default, so an unresolvable home masks exactly what
the redaction floor's own default masks. Two controls run the real CLI in a real process with no
`$HOME` and a `pwd` whose lookup raises: told a destination it runs, and not told one it refuses
`DEFAULT_OUT_UNRESOLVED` by name rather than printing a traceback. The stub is installed into
`sys.modules` rather than onto `PYTHONPATH`, because `pwd` is a built-in module and a file can never
shadow it.

**An absolute `XDG_STATE_HOME` was refused over a home it did not need.** `default_out` resolved the
home first, so an unreadable account entry raised `DEFAULT_OUT_UNRESOLVED` even where
`/xdg/agent-bios/distill/runs` was already fully determined. XDG is selected first now, and the home
or the password-database fallback is resolved only when XDG gives no absolute base.

## The figures round 2 asked for

| | |
| --- | --- |
| receipt `installed_files` before the driver shipped | 165 |
| files under the state root at that point | 175 |
| receipt `installed_files` after | 224 |
| driver files in that historical install | 59 |
| installer inventory today (`_package_files`) | 222 |
| driver files today | 57 |

**165 and 175 count different things, and the receipt does not establish 175.** The receipt lists
the files the installation *wrote* as payload; the state root also holds what the installation keeps
about itself — the receipt, the status, the release digest's own bookkeeping — which no payload entry
names. Reading 175 as a payload count, or 165 as a file count, is wrong in both directions, and the
earlier record stated neither.

Today's 222 and 57 are smaller than the historical 224 and 59 for one reason: two driver files were
removed after that install, not because the payload boundary moved. The npm row count is 223, which
is the installer's 222 plus `LICENSE`, force-included by npm and not an entry of `files[]`.

## What the suites report now

| suite | controls |
| --- | --- |
| `session-distill/distill.py --self-test` | 161 |
| `gates/check-package.sh --self-test` | 50 planted violations, each named |
| `gates/check-hygiene.py` | 279 shipped subjects |
| `gates/check-endpoints.py` | 279 shipped files url-scanned |

Re-measure before quoting any of them. Round 2's own verdict is in
`work/lead/wp24-y-r2-findings.txt`, outside the repository; the revert trial of these four fixes is
`pretrial-wp24-r2.py` beside it, and the one fix it deliberately does not revert is named in its
own docstring.
