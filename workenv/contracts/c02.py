"""C02 Access session: the gaps its operations answer with.

Record kinds: `access_state`, `access_transition`, `access_admission`.

The local access owner keeps one state per profile on one installation: `active`, `locked` or
`signed_out`, with a generation that moves on every restrictive transition. A protected
operation is admitted only under the current generation, and a late result is checked against
it again before anything is shown. Each reason an operation is not admitted has its own name,
because each has a different way back.

The device key signs through an agent this runtime owns, and the signing call names a public
key file that has no private key beside it. Under that layout a signature asked for after a
lock is `access_locked`; with the private key beside the public one OpenSSH would ask the
person for the passphrase again, outside the unlock operation.
"""
CONTRACT = "C02"
RECORD_KINDS = ("access_state", "access_transition", "access_admission")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request.
# The union across the contract modules is the closed list a request may name.
OPERATIONS = (
    "access.transition",
    "access.admission.decide",
)

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
}
