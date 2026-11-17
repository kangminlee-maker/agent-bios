---
created_at: 2026-10-22T21:27:37+09:00
head: 08ac30e
kind: review
supersedes:
  - 2026-10-22T2046--3a94ded--every-jsonl-reader-the-review-found-reads-through-one-splitter.md
  - 2026-10-22T2104--6d351b5--the-splitter-sits-beside-the-one-reader-that-travels-alone.md
---

# A line terminator is LF or CRLF, and each package root reads with its own splitter

Round 2 of the F-21 review (`6d351b5`, FB#0 to FB#4) found that two claims of the 2046 and 2104
records were not true. This record replaces both and says what is true now. Their inventory of
thirteen readers, the owner `wrappers/jsonl_lines.py`, the helper's sibling load, the compatibility
install's deploy, verify and remove, and the closed alternatives (escaping at every writer; B, C and
D of the 2104 record) all stand. The two corrections follow.

**The 2104 record said every consumer loads the splitter inside its own package root. A private
release's store did not.** `compose/host_platform.py` found the splitter from its own `__file__`. A
private release's `instructions_store.py`, loaded by path from the installer
(`instructions_install._private_module`), imports `host_platform` by absolute name and gets the
installer's cached module. So it read with the installer's root's splitter. A release missing its
own splitter still worked.

**The 2046 record said each site keeps its comparison and rewrite behaviour. The migration's did
not.** The splitter kept the CR of a CRLF terminator on the line. One record written with CRLF in a
legacy source and LF in the private destination stopped being the same record: "same learning_id has
different source/private bytes".

## What is true now

**A terminator is "\n" or "\r\n", and lines compare the same whichever ended them** (FB#1).
`split` takes the terminator off. A CR anywhere else in a line stays part of it, since JSON allows it
as whitespace. `split_terminated` and `read_terminated` return each line with its own terminator,
for a writer that keeps it. This is the one rule, in the owner. The migration's identity is
terminator-insensitive again, as it was before this branch: legacy duplicates, the destination
comparison and the transfer verification. The apply path rejoins prior lines with "\n", as it did
before.

**Each consuming module reads with its own package root's splitter** (FB#0).
`host_platform.jsonl_lines_for(anchor)` takes the consuming module's own `__file__`. It loads
`<that root>/wrappers/jsonl_lines.py` under a name derived from the path, keeps it out of
`sys.modules`, and fails naming that path when it is missing. So a release store that imported
another root's `host_platform` still binds to its own root. `instructions_store.py` and
`instructions_install.py` call it with `__file__`. The two installer test fixtures, which build a
package from a file list, now ship the splitter in that package.

**`learn/migrate-learnings.py` `prune_jsonl` rewrites bytes, each kept line with its own
terminator** (FB#2). `compose/assemble.py` `replace_atomically` writes bytes as given. So Windows
text-mode writing, which turns every "\n" written as text into "\r\n", cannot turn a kept "\r\n" into
"\r\r\n".

**The package gate reads by-path loads from the parsed module** (FB#3, FB#4). A CHAIN is an outermost
`/` expression of two or more string segments naming a repo python file. A SIBLING is one segment
after `.parent`, resolved in the loader's directory. A comment or a docstring that shows such a path
is not a load.

## Controls

| Finding | Control | Fails when only this is reverted |
|---|---|---|
| FB#0 | `compose/test_instructions_store.py` `test_a_release_store_reads_with_its_own_roots_splitter`: the checkout's `host_platform` cached, a release store loaded by path, the release lacking its splitter -> FileNotFoundError naming the release's path; with it -> reads | the loader bound to `host_platform`'s own root |
| FB#1 | `test_instructions_migration.py` `test_jsonl_legacy_duplicate_across_lf_and_crlf_is_one_record`, `test_jsonl_destination_comparison_ignores_lf_or_crlf`, `test_jsonl_transfer_verification_ignores_lf_or_crlf` | the splitter keeping a CRLF's CR on the line (all three, each by name) |
| FB#2 | `migrate-learnings --self-test` `jsonl-rewrite-keeps-each-terminator-under-windows-newline-translation (prune_jsonl)`, with `Path.write_text` translating "\n" to "\r\n" | the rewrite passed as text |
| FB#3 | `check-package --self-test` "a module loaded by a path chain that files[] does not ship" (only `host_platform`'s chain left) and "a module loaded from beside its loader that files[] does not ship" (only the helper's sibling load left); both drop the installer's reference and the other loaders | the CHAIN walk, or the SIBLING walk, each failing only its own control |
| FB#4 | "a path shown in a comment or a docstring is no runtime reference" (the gate stays green) | the regex scan of raw source |

## Left

The readers the 2046 record left are still left, for its reasons and with its revisit condition:
text-mode iteration and `bytes.splitlines()` readers, display-line splitting, and Markdown, source
or command output. Under the terminator rule above, the only difference left between them and the
splitter is a bare CR between tokens.
