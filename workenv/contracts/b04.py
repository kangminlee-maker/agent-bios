"""B04 the bridge binding: the gaps a local bridge request answers with.

Record kind: `bridge_binding`.

Loopback HTTP for a browser only; the TUI and the CLI call the operations in process. The token
identifies a client instance and grants nothing, and it rides in the URL fragment rather than a
cookie because cookies are not isolated by port. Host and Origin are compared exactly, and the
access generation is read again before any protected body is written, so a lock landing between
computing a result and writing it refuses the write.
"""
CONTRACT = "B04"
RECORD_KINDS = ("bridge_binding",)
IN_RESULTS = True

HOST_NOT_EXACT = "host_not_exact"
ORIGIN_NOT_EXACT = "origin_not_exact"
ORIGIN_REQUIRED = "origin_required"
CLIENT_TOKEN_MISSING = "client_token_missing"
CLIENT_TOKEN_UNKNOWN = "client_token_unknown"
PREFLIGHT_REFUSED = "preflight_refused"

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    HOST_NOT_EXACT: "a Host header that is not the exact value this bridge serves",
    ORIGIN_NOT_EXACT: "an Origin that is not the exact value this bridge serves",
    ORIGIN_REQUIRED: "a request that carries no Origin where one is required",
    CLIENT_TOKEN_MISSING: "a request with no per-launch client token",
    CLIENT_TOKEN_UNKNOWN: "a client token this launch did not issue",
    PREFLIGHT_REFUSED: "a preflight this bridge does not answer; it grants nothing to refuse "
                       "later",
}
