#!/usr/bin/env python3
"""Reading one side of a commit, once.

The driver's ledger check compares the ledger in the index with the ledger at a base revision, and
`gates/check-global-file.py` compares the global instruction file the same way. Both need the same
three answers from git — the bytes of a blob, the bytes at a revision, the bytes the index or the
working tree holds — and both need the same distinction, which is the reason this is one module and
not two copies:

* **absent** is a measurement. A revision that does not hold the path, or an index that does not,
  measures as empty, because a deletion is a reduction rather than an unknown.
* **None** is no measurement at all. Git could not resolve the revision, could not read the tree, or
  the disk refused the file. A caller may not treat it as empty.

It lives in the driver, which ships, and the author-side gate imports it from here. The direction is
fixed by AGENTS.md: author-side imports shipped, never the reverse. Before this module the driver
loaded the gate's file by path (`importlib` over `gates/check-global-file.py`), which made shipped
code depend on a tree a packaged user does not have.

Nothing here reads a path of its own choosing: every call names its repository and its relative path,
so one function serves a ledger under a state root and a file inside a checkout alike.
"""
import pathlib
import subprocess


def git_blob(repo, spec):
    """The bytes of `REV:path` (or `:path`, the index), or None when git cannot read it."""
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", spec],
                          capture_output=True)
    return done.stdout if done.returncode == 0 else None


def base_blob(repo, base, rel):
    """(bytes, absent) for `rel` at `base`. A revision that lacks the path is absent and
    measures as empty. Bytes are None only when git cannot resolve the revision or read the
    tree, which is no measurement at all."""
    resolved = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                               f"{base}^{{commit}}"], capture_output=True)
    if resolved.returncode != 0:
        return None, False
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "--full-tree", "-z",
                              resolved.stdout.strip().decode(), "--", rel], capture_output=True)
    if listing.returncode != 0:
        return None, False
    entries = [e for e in listing.stdout.split(b"\0") if e]
    if not entries:
        return b"", True
    mode, kind, oid = entries[0].split(b"\t", 1)[0].split(b" ")
    return (git_blob(repo, oid.decode()) if kind == b"blob" else None), False


def current_blob(repo, rel, worktree):
    """(bytes, absent). A path the index (or disk) lacks is absent and measures as empty — a
    deletion is a reduction. Bytes are None only when git or the disk cannot answer, which
    is no measurement at all."""
    if worktree:
        try:
            return (pathlib.Path(repo) / rel).read_bytes(), False
        except FileNotFoundError:
            return b"", True
        except OSError:
            return None, False
    listing = subprocess.run(["git", "-C", str(repo), "ls-files", "--stage", "-z", "--", rel],
                             capture_output=True)
    if listing.returncode != 0:
        return None, False
    entries = [e for e in listing.stdout.split(b"\0") if e]
    if not entries:
        return b"", True
    if any(e.split(b"\t", 1)[0].split(b" ")[2] != b"0" for e in entries):
        return None, False
    return git_blob(repo, f":{rel}"), False


def lines_of(raw):
    """The lines of `raw`, without a trailing empty line for a file ending in a newline."""
    text = raw.decode("utf-8", "replace").split("\n")
    return text[:-1] if text[-1] == "" else text
