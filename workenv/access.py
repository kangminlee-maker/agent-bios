"""The local profile and its access state (C02), as far as a profile is read and named.

A profile is written by the runtime the first time a request comes from it, with no account,
Team or network: `first_use` writes the `local_profile` naming the actor's principal and an
active `access_state` at generation 1, both at that instant, in the unit of work of that first
request. No request creates a profile, and none but the first writes one.

`access.profile.read` returns the profile and its current access state, whatever the state is,
because reading where access stands is not protected use. `access.profile.rename` changes only
the display name: the profile's id, principal and creation time stay what first use wrote, so
nothing that names the profile moves with its label. Both act on the actor's own profile, so a
request whose target is another profile is `request_mismatch`.
"""
from __future__ import annotations

from workenv import journal, storage
from workenv.contracts import c03


def first_use(store: storage.Store, actor: dict, at: str) -> None:
    """Write the actor's profile and its first access state, unless it has one."""
    if store.read("SELECT 1 FROM profiles WHERE profile_id = ?", (actor["profile_id"],)):
        return
    profile = {"kind": "local_profile", "schema": 1, "profile_id": actor["profile_id"],
               "principal_id": actor["principal_id"], "created_at": at}
    state = {"kind": "access_state", "schema": 1, "profile_id": actor["profile_id"],
             "state": {"is": "active", "because": "first_use"}, "access_generation": 1,
             "changed_at": at}
    store.write("INSERT INTO profiles (profile_id, principal_id, profile_digest, state_digest) "
                "VALUES (?, ?, ?, ?)",
                (actor["profile_id"], actor["principal_id"], store.put(profile),
                 store.put(state)))


def profile_of(store: storage.Store, profile_id: str) -> tuple[dict, dict]:
    """The profile's record and its current access state."""
    profile, state = store.read("SELECT profile_digest, state_digest FROM profiles "
                                "WHERE profile_id = ?", (profile_id,))[0]
    return store.get(profile), store.get(state)


def not_own(call) -> dict | None:
    """The answer to a request whose target is not the actor's own profile, or None."""
    if call.request["target"]["resource_id"] == call.request["actor"]["profile_id"]:
        return None
    return journal.answered(call, "refused", gaps=[{"code": c03.REQUEST_MISMATCH,
                                                    "pointer": "/target/resource_id"}],
                            recovery=["new_governed_request"])


def access_profile_read(call) -> dict:
    refused = not_own(call)
    if refused:
        return refused
    profile, state = profile_of(storage.of(call.state), call.request["target"]["resource_id"])
    return journal.answered(call, "previewed", [profile, state])


def access_profile_rename(call) -> dict:
    refused = not_own(call)
    if refused:
        return refused
    store = storage.of(call.state)
    profile_id = call.request["target"]["resource_id"]
    profile, _ = profile_of(store, profile_id)
    renamed = {**profile, "display_name": journal.payload(call)["display_name"]}
    store.write("UPDATE profiles SET profile_digest = ? WHERE profile_id = ?",
                (store.put(renamed), profile_id))
    return journal.committed(call, [renamed])
