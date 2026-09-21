"""C02 Access session: the gaps its operations answer with.

Record kinds: `access_state`, `access_transition`, `access_admission`, `local_profile`,
`profile_label`, `provider_connection`, `sign_in_attempt`, `provider_callback`, `sign_in_evidence`,
`control_evidence`.

The local access owner keeps one state per profile on one installation: `active`, `locked` or
`signed_out`, with a generation that moves on every restrictive transition. A protected
operation is admitted only under the current generation, and a late result is checked against
it again before anything is shown. Each reason an operation is not admitted has its own name,
because each has a different way back.

The device key signs through an agent this runtime owns, and the signing call names a public
key file that has no private key beside it. Under that layout a signature asked for after a
lock is `access_locked`; with the private key beside the public one OpenSSH would ask the
person for the passphrase again, outside the unlock operation.

A profile is written by the runtime at first use, with no account, Team or network; its display
name is a label a rename changes and nothing names.

A provider sign-in is identity evidence, never access. A Team's `provider_connection` names the
issuer, audience and claims it trusts and where its exchange runs, and has no field for a secret.
An attempt is begun for one connection and one purpose; the callback binds to it by the state and
nonce the runtime minted, once, and is held to the connection's issuer, audience and claims.
What it establishes is `sign_in_evidence`, which unlocks nothing: re-entry is an explicit
`access.transition` sign-in naming that evidence among its proofs, and a callback, a refresh or a
provider logout arriving while a profile is locked or signed out changes nothing.

Offline use rests on `control_evidence` a Team's authority issued to one holder: a permit with its
validity and offline limit, or the revocation of one. A request names the evidence it relies on in
`control_digests`.

A browser reaches the operations only through the loopback bridge (B04). `access.bridge.serve`
takes the `bridge_request` as received and answers with the `bridge_response`, whose written body
has one generation, read on arrival and again before writing.
"""
CONTRACT = "C02"
RECORD_KINDS = ("access_state", "access_transition", "access_admission", "local_profile",
                "profile_label", "provider_connection", "sign_in_attempt", "provider_callback",
                "sign_in_evidence", "control_evidence")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name.
OPERATIONS = {
    "access.transition": {"takes": ("access_transition",), "returns": ("access_state",)},
    "access.admission.decide": {"takes": ("operation_request",), "returns": ("access_admission",)},
    "access.profile.rename": {"takes": ("profile_label",), "returns": ("local_profile",)},
    "access.connection.configure": {"takes": ("provider_connection",),
                                    "returns": ("provider_connection",)},
    "access.sign_in.begin": {"takes": ("sign_in_attempt",), "returns": ("sign_in_attempt",)},
    "access.sign_in.complete": {"takes": ("provider_callback",),
                                "returns": ("sign_in_evidence", "principal_binding")},
    "access.control.record": {"takes": ("control_evidence",), "returns": ("control_evidence",)},
    "access.bridge.serve": {"takes": ("bridge_request",), "returns": ("bridge_response",)},
}

ACCESS_LOCKED = "access_locked"
ACCESS_SIGNED_OUT = "access_signed_out"
ACCESS_GENERATION_MOVED = "access_generation_moved"
ACCESS_STATE_NOT_DURABLE = "access_state_not_durable"
RECIPIENT_MISMATCH = "recipient_mismatch"
CREDENTIAL_MISSING = "credential_missing"
CREDENTIAL_REVOKED = "credential_revoked"
CREDENTIAL_EXPIRED = "credential_expired"
CONTROL_EVIDENCE_INSUFFICIENT = "control_evidence_insufficient"
FRESH_AUTH_REQUIRED = "fresh_auth_required"
UNLOCK_NEEDS_A_TERMINAL = "unlock_needs_a_terminal"
CARRIER_UNREACHABLE = "carrier_unreachable"
CLAIM_NOT_EXPECTED = "claim_not_expected"
CALLBACK_NOT_BOUND = "callback_not_bound"
PROVIDER_UNREACHABLE = "provider_unreachable"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    ACCESS_LOCKED: "the profile is locked; protected use waits for an explicit unlock",
    ACCESS_SIGNED_OUT: "the profile is signed out; protected use waits for an explicit sign-in",
    ACCESS_GENERATION_MOVED: "a handle issued under an access generation that has since moved",
    ACCESS_STATE_NOT_DURABLE: "an access transition whose record could not be made durable",
    RECIPIENT_MISMATCH: "a result or body asked for by a recipient it was not prepared for",
    CREDENTIAL_MISSING: "no credential this operation accepts is enrolled on this device",
    CREDENTIAL_REVOKED: "a credential a known control has revoked",
    CREDENTIAL_EXPIRED: "a credential or its permitted offline evidence past its validity",
    CONTROL_EVIDENCE_INSUFFICIENT: "control evidence too old or too incomplete for this use",
    FRESH_AUTH_REQUIRED: "a policy that requires a fresh provider check this session lacks",
    UNLOCK_NEEDS_A_TERMINAL: "an unlock asked for where no person can be prompted",
    CARRIER_UNREACHABLE: "the carrier an operation needs cannot be reached; access, credentials, "
                         "controls and bodies were in place, and nothing was dispatched",
    CLAIM_NOT_EXPECTED: "a returned identity whose issuer, audience or required workspace or "
                        "tenant claim is not what its connection expects; nothing is linked",
    CALLBACK_NOT_BOUND: "a callback whose state or nonce is not its attempt's, that arrives after "
                        "the attempt expired, or for an attempt already completed",
    PROVIDER_UNREACHABLE: "the provider or the connection's exchange could not be reached; nothing "
                          "was verified or linked, and work that needs no provider continues",
}
