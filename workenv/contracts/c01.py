"""C01 Identity and reference: the gaps its operations answer with.

Record kinds: `principal_binding`, `repository_binding`, `source_ref`, `source_home`,
`source_manifest`, `source_request`, `behaviour_capture`, `knowledge_capture`,
`memory_capture`, `source_provenance`, `source_selection`, `source_observation`,
`extraction_run`.

An id is an opaque string this installation made; it proves nothing about who holds it. A
display name, an e-mail address, a locator and a key are labels or credentials that change,
so no C01 record has a field for one in the place of an id, and the closed schemas refuse the
attempt as an unknown field. What is left for an operation to answer is below.

A source is held apart from its bytes the same way. Where it is authored and which authority
accepts its revisions are two fields, not one; what one revision holds is a manifest of members
and hashes, with the companion sources its members are read with; where the bytes came from,
when this installation acquired them and whether anything here accepted them are three facts in a
provenance record, none of which confers priority. A managed source is kept by its scope's
namespace in the collection of its role, so its home names no collection of its own.
A capture is three record kinds because it carries the material itself, and material of
different roles is different in kind: a knowledge or memory capture has no property for a
behavioural unit, so promoting either into behavioural text cannot be written down. The
operation that admits any of these is C03's; what they are is C01's.

A source's head moves with each owner commit on its id. The first — a registration
(`source.home.register`) or an admission (`source.revision.admit`) — expects no head, and every
later one names the head it expects: a revision commit, a publication, or a registration of the
same home again. The home holds the source's conditions — applicability, disclosure, retention —
so registering it again changes them and moves the head while every revision's bytes stay what
they were; a registration that changes the home, scope, role or accepting authority instead is a
second home (`source_home_conflict`). Unchanged bytes do not cancel a changed condition:
`reference.resolve` answers an exact revision with the home at the head it read.

What is read comes from an explicit selection. `source_selection` names the places — transcript
records, revision members, working-tree paths of a named checkout, a supplied file — and what
each place's owner permits for text read there; `source_observation` is what one acquisition
actually read: for a working tree, committed, modified and untracked files alike as one
snapshot, and each required place whose content was absent. Observing writes nothing, and
binding a checkout to a repository id is its own operation, apart from any Team's exchange
carrier. A capture names the observation its inputs were read in, where each input was read, and
what its source permits for processing, prompt logs and destinations, which is no more than the
selection root it was read under states; one proposed for a wider scope than its inputs came from
states the widening and its authority. It names the destination's revision it was made against
when the destination has one. A model's capture comes with the `extraction_run` of the packaged
adapter that made it: every file the run loaded and what it wrote inside its own directory.

A source's own statements about its history — author, decision time, status, approval — are
claims in its provenance, each verified or stated only; none is an acceptance.

Two rules relate one record to another, which a schema cannot state; the runtime owner keeps
them and P01's cases check them: an observation reads only under the roots of the selection it
answers, and reports missing only a root the selection requires; and each capture input lies
under a root of the selection its observation answers and restates no more than that root
permits.
"""
CONTRACT = "C01"
RECORD_KINDS = ("principal_binding", "repository_binding", "source_ref", "source_home",
                "source_manifest", "source_request", "behaviour_capture", "knowledge_capture",
                "memory_capture", "source_provenance", "source_selection", "source_observation",
                "extraction_run")
IN_RESULTS = True

# The operations of this contract that travel in a C03 sealed request. `takes` is the
# record kinds its payload may be, and none means the request names no payload;
# `returns` is the kinds its result may name in `outputs`. The union across the
# contract modules is the closed list a request may name. `effect`, `action` and `targets`
# are what every request for it states: its effect class, the one grant action it needs, and
# the id prefixes its target may carry.
OPERATIONS = {
    "identity.binding.add": {"takes": ("principal_binding",), "returns": ("principal_binding",),
                             "effect": "owner_commit", "action": "local_profile",
                             "targets": ("prn",)},
    "identity.binding.revoke": {"takes": (), "returns": (),
                                "effect": "owner_commit", "action": "local_profile",
                                "targets": ("bnd",)},
    "reference.resolve": {"takes": ("source_ref",),
                          "returns": ("source_manifest", "source_provenance", "source_home"),
                          "effect": "pure_preview", "action": "read", "targets": ("src",)},
    "source.home.register": {"takes": ("source_home",), "returns": ("source_home",),
                             "effect": "owner_commit", "action": "contribute",
                             "targets": ("src",)},
    "source.capture.record": {
        "takes": ("behaviour_capture", "knowledge_capture", "memory_capture"),
        "returns": ("behaviour_capture", "knowledge_capture", "memory_capture", "extraction_run"),
        "effect": "durable_candidate", "action": "contribute", "targets": ("src",),
    },
    "source.observe": {"takes": ("source_selection",), "returns": ("source_observation",),
                       "effect": "pure_preview", "action": "read", "targets": ("rep", "prn")},
    "repository.bind": {"takes": ("repository_binding",), "returns": ("repository_binding",),
                        "effect": "owner_commit", "action": "local_profile",
                        "targets": ("rep",)},
    "source.revision.admit": {"takes": ("source_request",),
                              "returns": ("source_manifest", "source_provenance"),
                              "effect": "owner_commit", "action": "contribute",
                              "targets": ("src",)},
    "source.revision.commit": {"takes": ("source_manifest",), "returns": ("source_manifest",),
                               "effect": "owner_commit", "action": "publish",
                               "targets": ("src",)},
    "source.revision.publish": {"takes": (), "returns": (),
                                "effect": "owner_commit", "action": "publish",
                                "targets": ("src",)},
}

ID_BOUND_TO_OTHER_BYTES = "id_bound_to_other_bytes"
BINDING_UNVERIFIED = "binding_unverified"
BINDING_CONFLICT = "binding_conflict"
REPOSITORY_BINDING_REQUIRED = "repository_binding_required"
REF_UNAVAILABLE = "ref_unavailable"
SOURCE_HOME_CONFLICT = "source_home_conflict"
PUBLISHER_BYTES_MODIFIED = "publisher_bytes_modified"
MANIFEST_MEMBER_UNLISTED = "manifest_member_unlisted"
INPUT_NOT_PERMITTED = "input_not_permitted"
INPUT_NOT_OBSERVED = "input_not_observed"
WIDENING_UNSTATED = "widening_unstated"
ADAPTER_UNAVAILABLE = "adapter_unavailable"

# Rules that relate one element of a record to another, which a schema cannot state. The
# runtime owner keeps each; a case in the registry (gates/workenv/case-index.json) checks it.
RUNTIME_RULES = {
    "read_within_selection": "a source_observation reads only under the roots of the selection "
                             "it answers, and reports missing only a root that selection "
                             "requires",
    "input_within_its_root": "each input of a capture lies under a root of the selection its "
                             "observation answers and restates no more than that root permits "
                             "for processing, prompt logs and destinations; a root that states "
                             "no permission permits no capture",
}

# This module's rows of the contract error table (workenv.contracts.errors joins them).
ERRORS = {
    ID_BOUND_TO_OTHER_BYTES: "an id or digest already bound here to bytes that differ",
    BINDING_UNVERIFIED: "a binding whose evidence is absent or does not verify",
    BINDING_CONFLICT: "a credential already bound to another principal; kept, never merged",
    REPOSITORY_BINDING_REQUIRED: "a fork used as its original without an explicit binding",
    REF_UNAVAILABLE: "an exact reference whose bytes this installation does not hold",
    SOURCE_HOME_CONFLICT: "a second home claiming one source's accepted state: a repository "
                          "document and a managed twin cannot both own it, nor can a "
                          "registration changing its home, scope, role or authority",
    PUBLISHER_BYTES_MODIFIED: "installed publisher bytes changed in place, where an addition "
                              "is a derived source with a home of its own",
    MANIFEST_MEMBER_UNLISTED: "a revision holding a member its manifest does not list",
    INPUT_NOT_PERMITTED: "a capture input stating more than its selection root permits, or a "
                         "capture that processes, logs or commits more than its inputs permit; "
                         "read permission or redaction is not that permission",
    INPUT_NOT_OBSERVED: "a capture input whose bytes the observation it names did not read from "
                        "an explicit selection",
    WIDENING_UNSTATED: "a capture committed to a wider scope than its inputs came from without "
                       "stating the widening and the authority for it",
    ADAPTER_UNAVAILABLE: "no supported packaged adapter can run here; the capture is not made, "
                         "and nothing stands in for it",
}
