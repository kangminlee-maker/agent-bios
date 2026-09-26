"""The person's checkout (C01): binding it to a repository id, and reading what a selection names.

`repository.bind` binds the git checkout the process runs in to the repository id its payload
names, and states what it observed there in the runtime-owned `observed`: the remote the checkout
calls `origin` (the checkout's own directory when it has none), its branch, its HEAD, and its
selected working bytes. Those are the digest of the last observation this installation answered
for a selection of that repository reading this checkout with no required root missing, when
reading the same selection now reads the same files with the same bytes; bytes that moved since,
or a checkout never so observed, state none, because the whole project is never snapshotted in
their place. Binding the same repository again binds it anew.

`source.observe` reads what a selection names and changes nothing: it keeps only the selection
it read, by digest beside the observation the journal holds, so a binding can read it again. A
working-tree root reads the file or every file under the directory it names, in the checkout it
names, as the working tree holds it now: committed, modified since HEAD, or untracked, by git's
reading, and never a file git ignores. A symbolic link is read as the path it holds, as git keeps
it, so nothing outside a root is read through one. Reads are ordered as git lists them: by root,
then the files git tracks before those it does not, each by path. A root with no file is missing,
and a missing root the selection requires is `ref_unavailable` at that root; a missing optional
root is not reported. Places other than a working tree are not read here yet.

Git is asked about the checkout a call names and no other: the variables that point git at
another repository, index or object store (`GIT_DIR`, `GIT_INDEX_FILE` and the rest of
`REPOSITORY_ENV`) are removed from the environment of every git process this module starts, so a
runtime started from inside a git hook still reads the person's checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess

from workenv import journal, storage
from workenv.contracts import c01, c03, canonical

WORKING_TREE = "working_tree"
REPOSITORY_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_INDEX_FILE",
                  "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                  "GIT_PREFIX", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES")
OBSERVE = "source.observe"


class NotAGitCheckout(Exception):
    """A directory git does not read as a working tree."""


def git(checkout: pathlib.Path, *arguments: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(checkout), *arguments], capture_output=True,
                              timeout=60, env={name: value for name, value in os.environ.items()
                                               if name not in REPOSITORY_ENV})
    except FileNotFoundError as error:
        raise NotAGitCheckout("git is not on PATH") from error
    if done.returncode != 0:
        raise NotAGitCheckout(done.stderr.decode("utf-8", "replace").strip())
    return done.stdout.decode("utf-8", "surrogateescape")


def top(directory: pathlib.Path) -> pathlib.Path | None:
    """The working tree the directory lies in, or None."""
    try:
        return pathlib.Path(git(directory, "rev-parse", "--show-toplevel").strip())
    except NotAGitCheckout:
        return None


def states(checkout: pathlib.Path) -> dict[str, str]:
    """Every file git sees in the working tree, by path: committed, modified or untracked."""
    listed = [path for path in git(checkout, "ls-files", "-z", "--cached", "--others",
                                   "--exclude-standard").split("\0") if path]
    changed: dict[str, str] = {}
    fields = git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        changed[path] = "untracked" if code == "??" else "modified"
        if "R" in code or "C" in code:
            index += 1   # the path it was renamed or copied from
    found = {}
    for path in listed:
        target = checkout / path
        if target.is_symlink() or target.is_file():   # not a deleted file, nor a submodule
            found[path] = changed.get(path, "committed")
    return found


def read(checkout: pathlib.Path, path: str) -> bytes:
    """A working-tree file's bytes as git keeps them: a symbolic link is the path it holds."""
    target = checkout / path
    if target.is_symlink():
        return os.fsencode(os.readlink(target))
    return target.read_bytes()


def under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def reading(selection: dict) -> tuple[list[dict], list[int]]:
    """What the working tree holds now under a selection's roots: the reads, in the order the
    module states, and the required roots with no file."""
    reads, missing = [], []
    for index, root in enumerate(selection["roots"]):
        place = root["place"]
        if place["from"] != WORKING_TREE:
            raise journal.JournalError(f"reading a {place['from']} place is not served yet")
        checkout = pathlib.Path(place["checkout"])
        try:
            found = {path: state for path, state in states(checkout).items()
                     if under(path, place["path"])} if checkout.is_dir() else {}
        except NotAGitCheckout:
            found = {}
        if not found and root["need"] == "required":
            missing.append(index)
        for path, state in sorted(found.items(), key=lambda item: (item[1] == "untracked",
                                                                     item[0])):
            data = read(checkout, path)
            reads.append({"read": "tree", "root": index, "path": path, "state": state,
                          "digest": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return reads, missing


def same_place(one: str, other: pathlib.Path) -> bool:
    return pathlib.Path(one).resolve() == other.resolve()


def selected_bytes(store: storage.Store, repository_id: str,
                   checkout: pathlib.Path) -> str | None:
    """The digest of the last complete observation answered for this repository's checkout,
    while the working tree still reads as it read; else None."""
    rows = store.read("SELECT target, payload_digest, returned FROM requests WHERE operation = ? "
                      "AND stage = 'previewed' ORDER BY position DESC", (OBSERVE,))
    for target, named, returned in rows:
        if canonical.load(target.encode("utf-8"))["resource_id"] != repository_id:
            continue
        selection = store.get(named)
        if selection is None or not all(
                root["place"]["from"] == WORKING_TREE
                and same_place(root["place"]["checkout"], checkout) for root in selection["roots"]):
            continue
        digest = json.loads(returned)[0]
        observation = store.get(digest)
        if observation["missing"]:
            continue
        reads, missing = reading(selection)
        return digest if (reads, missing) == (observation["read"],
                                              observation["missing"]) else None
    return None


def repository_bind(call) -> dict:
    store = storage.of(call.state)
    binding = journal.payload(call)
    if binding["repository_id"] != call.request["target"]["resource_id"]:
        return journal.answered(call, "refused", gaps=[{"code": c03.REQUEST_MISMATCH,
                                                        "pointer": "/target/resource_id"}],
                                recovery=["new_governed_request"])
    checkout = top(pathlib.Path.cwd())
    if checkout is None:
        return journal.answered(call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE}],
                                recovery=["new_governed_request"])
    observed = {"locator": str(checkout)}
    try:
        observed["locator"] = git(checkout, "remote", "get-url", "origin").strip()
    except NotAGitCheckout:
        pass
    try:
        branch = git(checkout, "symbolic-ref", "-q", "--short", "HEAD").strip()
        if branch:
            observed["branch"] = branch
    except NotAGitCheckout:
        pass   # a detached HEAD is on no branch
    try:
        observed["commit"] = git(checkout, "rev-parse", "--verify", "-q", "HEAD").strip()
    except NotAGitCheckout:
        pass   # a checkout with no commit yet
    selected = selected_bytes(store, binding["repository_id"], checkout)
    if selected is not None:
        observed["working_bytes_digest"] = selected
    stored = {**binding, "observed": observed}
    store.write("INSERT OR REPLACE INTO repositories (repository_id, binding_digest, checkout) "
                "VALUES (?, ?, ?)", (binding["repository_id"], store.put(stored), str(checkout)))
    return journal.committed(call, [stored])


def source_observe(call) -> dict:
    selection = journal.payload(call)
    storage.of(call.state).put(selection)
    reads, missing = reading(selection)
    gaps = [{"code": c01.REF_UNAVAILABLE, "pointer": f"/roots/{index}"} for index in missing]
    observation = {"kind": "source_observation", "schema": 1,
                   "selection_digest": canonical.digest_of(selection), "read": reads,
                   "missing": missing, "observed_at": journal.now(call)}
    return journal.answered(call, "previewed", [observation], gaps=gaps)
