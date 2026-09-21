"""B02 the unlock binding: the gaps an unlock or a protected use answers with.

Record kind: `unlock_binding`.

The person unlocks at OpenSSH's own prompt into an agent this runtime owns; agent-bios never
holds the passphrase. Two observations from the spike are consts in the schema rather than
advice: the public half used for signing is stored apart from the private key, because a signing
call falls back to a private key sitting beside it and asks the person again outside the unlock;
and `-U` is not relied on, because two of the five observed OpenSSH versions ignore it.

A system with no agent the runtime can start and own has no key store for the device key: an
unlock there is `keystore_missing`, protected use is unsupported, and no plaintext or mocked key
stands in.
"""
CONTRACT = "B02"
RECORD_KINDS = ("unlock_binding",)
IN_RESULTS = True

PRIVATE_KEY_BESIDE_PUBLIC = "private_key_beside_public"
AGENT_NOT_OWNED_HERE = "agent_not_owned_here"
KEYSTORE_MISSING = "keystore_missing"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    PRIVATE_KEY_BESIDE_PUBLIC: "a signing key whose private half sits beside the public one, so "
                               "the call can prompt the person outside the unlock and sign with "
                               "an empty agent",
    AGENT_NOT_OWNED_HERE: "a signing agent this runtime does not own, such as the login agent",
    KEYSTORE_MISSING: "a system with no agent this runtime can start and own, so no device key can "
                      "be held unlocked; protected use is unsupported there, never a plaintext or "
                      "mocked key in its place",
}
