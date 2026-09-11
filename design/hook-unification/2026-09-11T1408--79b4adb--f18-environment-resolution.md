---
created_at: 2026-09-11T14:08:58.551542+09:00
head: 79b4adb
kind: review
supersedes: 2026-09-11T1213--79b4adb--resolution.md
---

# F-18: author verification owns its environment

F-18 is addressed and removed from the live FINDINGS queue. The earlier hook
interoperability changes remain in the working tree. Author verification now
prepares its own legacy host environment and copies only its tracked subject.

## Changes

- `gates/fixture_support.py` supplies a scoped legacy environment: explicit
  installation mode, temporary Claude/Codex homes containing repository wrappers
  and Codex agent templates, private state/status paths, cache, source profile and
  language. Values and their original absence/empty state are restored when the
  context exits, including on exceptions. Temporary assets are removed.
- The review-golden capture, runtime-projection gate and tier-effort test enter
  that context before importing the launcher. In-process observations and child
  processes receive the same settings. This is applied at those entrypoints,
  rather than disabling private corpus throughout the umbrella. Existing private
  tests continue to activate their own private path.
- `copy_tracked_tree` enumerates the effective Git index and copies the current
  bytes for those paths. A pre-commit materialized tree retains its supplied
  GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE identity. A mismatched tree, empty subject,
  or missing tracked member fails explicitly. Symlinks remain symlinks.
- The two assembler package-copy scenarios use that function instead of walking
  the working directory. Ignored benchmark outputs and untracked files cannot
  enter the fixture.
- The umbrella runs the helper's self-test. Four tests cover hostile ambient
  private mode, absent native assets, both observation routes, entrypoint wiring,
  exception cleanup, untracked/ignored broken links, executable modes, current
  bytes, preserved tracked links and a borrowed snapshot index after the live
  index moves.

## Verification

The ordinary command was run directly in this working directory, without a
separate checkout or caller-prepared environment:

```bash
bash gates/check-parity.sh
```

It exited **0** and printed **PARITY OK**, taking **637.17 seconds** in this run.
The following ambient conditions were present before and after it:

```json
{
  "ambient_private_override": null,
  "private_install_marker": true,
  "native_frontier_template_exists": false,
  "ignored_broken_link_present": true
}
```

Thus the acceptance run retained the real private-install marker, absent native
agent template and ignored broken executable link that exposed F-18. The gate
itself supplied the required fixture boundaries.

Additional results:

| Check | Result |
| --- | --- |
| Shared fixture self-test | 4 passed |
| Assembler scenarios in the original working directory | Passed |
| Existing review golden | 126 cells, zero control failures |
| Full runtime-projection and tier checks | Passed |
| Corpus/Studio regression suite | 170 passed |
| Slide-writing regression suite | 24 passed |
| Package boundary and lexicon | Passed |
| Faithful-regression controls | Mode override omission, template-copy omission and restored whole-directory traversal each fail their named tests |

The existing golden and UI row assertions were retained. Repository instruction
payload and the two hosts' runtime behavior receive no additional change from
this follow-up. The implementation is author-side; the new helper is excluded
from the npm payload by the existing gates/ boundary.

The dated 12:13 report records F-18 as open at that earlier point in time. This
record closes that remaining item; the earlier document is preserved as history.
