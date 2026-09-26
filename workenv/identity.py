"""Principal bindings (C01): which credential speaks for which principal on this installation.

`identity.binding.add` binds the credential its `principal_binding` payload carries to the
principal it names, and returns the binding as stored: the submitted fields exactly, with the
`binding_id` and `created_at` the runtime owns. The request targets that principal. In order:

  - A credential already bound here to another principal is `binding_conflict`, and stays that
    principal's; nothing is merged. The same credential already bound to the same principal is
    that earlier binding: the answer names its receipt and writes no second one.
  - A principal that has held a binding here takes another only with proof of control: a
    `signature_envelope` among the request's proofs, over the payload's bytes in the
    `agent-bios/principal_binding` namespace, by one of the principal's own bindings that is not
    revoked. Without one that verifies, the answer is `binding_unverified` and nothing is bound.
    Revoking every binding does not reopen the principal to whoever asks next: a principal left
    with none takes a key only through recovery.

A principal's first binding here needs no proof, whatever established it; binding a key through
a provider's verified evidence rather than a signature, as recovery does, is not served here
yet.

`identity.binding.revoke` revokes the binding its request targets, which must be one of the
actor's principal's bindings that is not revoked; any other id is `ref_unavailable`. Its stored
result, and the result of the request that added it, stay what they were.

`verify` checks one signature envelope against the key of the binding it names, through
`ssh-keygen -Y verify` (B01): it answers None, or the B01 code that refuses it.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

from workenv import journal, storage
from workenv.contracts import b01, c01, c03, canonical

ENVELOPE = "signature_envelope"
NAMESPACE = "agent-bios/"
ARMOR = "SSH SIGNATURE"
LINE = 70   # ssh-keygen wraps an armored signature's body at this width


def credential_key(credential: dict) -> str:
    """What makes two credentials one: a device key's public key, or an identity's issuer and
    subject."""
    if credential["credential"] == "device_key":
        return "device_key " + credential["public_key"]
    return canonical.encode({"issuer": credential["issuer"],
                             "subject": credential["subject"]}).decode("utf-8")


def bindings_of(store: storage.Store, principal_id: str) -> dict[str, dict]:
    """The principal's bindings that are not revoked, by binding id."""
    return {binding_id: store.get(digest) for binding_id, digest in store.read(
        "SELECT binding_id, digest FROM bindings WHERE principal_id = ? AND revoked_by IS NULL",
        (principal_id,))}


def verify(store: storage.Store, envelope: dict, data: bytes) -> str | None:
    """None when the envelope verifies over these bytes under the key of the binding it names;
    otherwise the B01 code that refuses it."""
    found = store.read("SELECT digest FROM bindings WHERE binding_id = ? AND revoked_by IS NULL",
                       (envelope["signer_binding_id"],))
    credential = store.get(found[0][0])["credential"] if found else None
    if credential is None or credential.get("credential") != "device_key":
        return b01.SIGNER_NOT_PERMITTED
    body = envelope["sshsig"]
    armored = "\n".join([f"-----BEGIN {ARMOR}-----",
                         *(body[i:i + LINE] for i in range(0, len(body), LINE)),
                         f"-----END {ARMOR}-----", ""])
    with tempfile.TemporaryDirectory(prefix="workenv-verify-") as scratch:
        signers = pathlib.Path(scratch) / "allowed_signers"
        signers.write_text(f"signer {credential['public_key']}\n", encoding="ascii")
        signature = pathlib.Path(scratch) / "signature"
        signature.write_text(armored, encoding="ascii")
        try:
            done = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(signers),
                                   "-I", "signer", "-n", envelope["namespace"],
                                   "-s", str(signature)],
                                  input=data, capture_output=True, timeout=30)
        except FileNotFoundError:
            return b01.TOOL_ABSENT
    return None if done.returncode == 0 else b01.SIGNATURE_INVALID


def proven(call, store: storage.Store, binding: dict, holds: dict) -> bool:
    """Whether a proof among the request's carries shows control of one of `holds`."""
    data = canonical.encode(binding)
    digest = canonical.digest_of(binding)
    named = set(call.request["proof_digests"])
    for value in call.carried:
        if not (isinstance(value, dict) and value.get("kind") == ENVELOPE
                and journal.digest_of(value) in named and value["signed_digest"] == digest
                and value["namespace"] == NAMESPACE + binding["kind"]
                and value["signer_binding_id"] in holds):
            continue
        if verify(store, value, data) is None:
            return True
    return False


def identity_binding_add(call) -> dict:
    store = storage.of(call.state)
    binding = journal.payload(call)
    principal = binding["principal_id"]
    if call.request["target"]["resource_id"] != principal:
        return journal.answered(call, "refused", gaps=[{"code": c03.REQUEST_MISMATCH,
                                                        "pointer": "/target/resource_id"}],
                                recovery=["new_governed_request"])
    key = credential_key(binding["credential"])
    taken = store.read("SELECT binding_id, principal_id, digest FROM bindings "
                       "WHERE credential = ? AND revoked_by IS NULL", (key,))
    if any(owner != principal for _, owner, _ in taken):
        return journal.answered(call, "conflict", gaps=[{"code": c01.BINDING_CONFLICT}],
                                recovery=["new_governed_request"])
    if taken:
        return earlier(call, store, taken[0][2])
    held = store.read("SELECT 1 FROM bindings WHERE principal_id = ? LIMIT 1", (principal,))
    if held and not proven(call, store, binding, bindings_of(store, principal)):
        return journal.answered(call, "refused", gaps=[{"code": c01.BINDING_UNVERIFIED}],
                                recovery=["new_governed_request"])
    stored = {**binding, "binding_id": journal.mint("bnd"), "created_at": journal.now(call)}
    store.write("INSERT INTO bindings (binding_id, principal_id, credential, digest) "
                "VALUES (?, ?, ?, ?)",
                (stored["binding_id"], principal, key, store.put(stored)))
    return journal.committed(call, [stored])


def earlier(call, store: storage.Store, digest: str) -> dict:
    """The answer that settles a request as a duplicate of the commit that stored `digest`:
    its receipt and the binding it stored, and no new receipt."""
    for request_id, in store.read("SELECT request_id FROM requests WHERE stage = 'committed' "
                                  "ORDER BY position"):
        original = journal.held(store, request_id)["answer"]
        outputs = original["result"]["outputs"]
        if any(output["digest"] == digest for output in outputs):
            answer = journal.answered(call, "committed", original["returned"],
                                      local_effect="committed")
            answer["result"]["outcome"]["receipt_digest"] = \
                original["result"]["outcome"]["receipt_digest"]
            answer["receipt"] = original["receipt"]
            return answer
    raise journal.JournalError(f"no committed request stored the binding {digest}")


def identity_binding_revoke(call) -> dict:
    store = storage.of(call.state)
    binding_id = call.request["target"]["resource_id"]
    if binding_id not in bindings_of(store, call.request["actor"]["principal_id"]):
        return journal.answered(call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE,
                                                        "pointer": "/target/resource_id"}],
                                recovery=["new_governed_request"])
    store.write("UPDATE bindings SET revoked_by = ? WHERE binding_id = ?",
                (call.request["request_id"], binding_id))
    return journal.committed(call)
