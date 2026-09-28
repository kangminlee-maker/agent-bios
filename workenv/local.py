"""Where this installation keeps the work environment, and whose requests it makes.

The state root is `workenv/state` under the local state base: `AGENT_BIOS_STATE_DIR` where the
caller sets it, and `~/.local/share/agent-bios` otherwise. A root set that way is the caller's,
so an entrance that honours it states `root_origin: caller`.

The actor is minted at first use: a principal, a device and a profile id, kept in
`workenv/actor.json` beside the state root, readable by its owner alone. The profile itself is
written by the journal with the first request (`workenv.access`). Nothing is signed at first use,
so no device key is made; a key is made when a sharing or recovery operation needs one.

The locale an entry draws in is the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that is set,
read as Korean, Japanese or English; anything else is English.
"""
from __future__ import annotations

import json
import os
import pathlib

from workenv import journal

BASE = "AGENT_BIOS_STATE_DIR"
ACTOR = "actor.json"
IDS = (("principal_id", "prn"), ("device_id", "dev"), ("profile_id", "prf"))
LOCALES = ("ko", "ja", "en")


class LocalError(Exception):
    """This installation's own files are not what they must be, named."""


def base(environ) -> pathlib.Path:
    """The local state base."""
    return pathlib.Path(environ.get(BASE) or pathlib.Path(environ["HOME"]) / ".local" / "share" /
                        "agent-bios")


def home(environ) -> pathlib.Path:
    """What the work environment keeps under the base: the state root and the actor."""
    return base(environ) / "workenv"


def state_root(environ) -> pathlib.Path:
    return home(environ) / "state"


def root_origin(environ) -> str:
    return "caller" if environ.get(BASE) else "owner"


def held_actor(environ) -> dict | None:
    """The actor first use minted here, or None where there has been no first use."""
    path = home(environ) / ACTOR
    try:
        actor = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise LocalError(f"{path} cannot be read: {error}") from error
    if not isinstance(actor, dict) or sorted(actor) != sorted(name for name, _ in IDS) or \
            not all(isinstance(actor[name], str) and actor[name].startswith(f"{prefix}_")
                    for name, prefix in IDS):
        raise LocalError(f"{path} does not name a principal, a device and a profile")
    return actor


def actor(environ) -> dict:
    """The actor this installation makes requests as, minted at first use."""
    found = held_actor(environ)
    if found is not None:
        return found
    directory = home(environ)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    minted = {name: journal.mint(prefix) for name, prefix in IDS}
    try:
        written = os.open(directory / ACTOR, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process minted it first: its actor is this installation's.
        return held_actor(environ)
    with os.fdopen(written, "w", encoding="utf-8") as out:
        json.dump(minted, out)
        out.flush()
        os.fsync(out.fileno())
    return minted


def locale(environ) -> str:
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = environ.get(name)
        if value:
            language = value.split("_")[0].split(".")[0].lower()
            return language if language in LOCALES else "en"
    return "en"
