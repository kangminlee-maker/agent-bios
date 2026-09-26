"""What V1's unit tests call the code with: a call as the host makes one, without a process.

`Call` carries what the adapter design fixes; its `point` raises `Killed` at the armed fault
point, which stands for the process dying there, and `restart` drops the process's open store so
the next call opens it again from disk. `request` seals a request the way a client does, stating
what the operation's row fixes, and `keys` makes real ed25519 keys and signs through ssh-keygen.
"""
from __future__ import annotations

import pathlib
import secrets
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workenv import journal, storage  # noqa: E402
from workenv.contracts import canonical  # noqa: E402

NAMESPACE = "agent-bios/principal_binding"


class Killed(Exception):
    """The process died at an armed fault point; `answer` is what it held when it did."""

    def __init__(self, point: str, answer):
        super().__init__(point)
        self.point, self.answer = point, answer


class Call:
    def __init__(self, request: dict, carried=(), state=None, now=None, given=None, arm=None):
        self.request, self.carried = request, list(carried)
        self.members: dict = {}
        self.now, self.given, self.arm = now, given, arm
        self.state = pathlib.Path(state)
        self.exchange = self.state.parent / "exchange"
        self.points: list[str] = []
        self.admissions = 0

    def point(self, name: str, answer=None) -> None:
        self.points.append(name)
        if name == self.arm:
            raise Killed(name, answer)

    def admitted(self) -> None:
        self.admissions += 1


def restart(state) -> None:
    """The process started again: its open store is gone, what it committed is on disk."""
    found = storage._OPEN.pop(pathlib.Path(state), None)
    if found is not None:
        found.connection.close()


def ident(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


class Person:
    """One actor: a principal on one device under one profile."""

    def __init__(self):
        self.principal, self.device, self.profile = ident("prn"), ident("dev"), ident("prf")

    @property
    def actor(self) -> dict:
        return {"principal_id": self.principal, "device_id": self.device,
                "profile_id": self.profile}

    @property
    def scope(self) -> dict:
        return {"layer": "personal", "principal_id": self.principal}


def request(person: Person, operation: str, target: dict | str, payload: dict | None = None,
            proofs=(), request_id: str | None = None, **changes) -> dict:
    row = journal.OPERATIONS[operation]
    sealed = {"kind": "operation_request", "schema": 1,
              "request_id": request_id or ident("req"), "operation": operation,
              "effect_class": row["effect"], "action": row["action"], "actor": person.actor,
              "local_access_generation": 1, "owner": person.scope,
              "target": target if isinstance(target, dict) else {"resource_id": target},
              "policy_digests": [], "control_digests": [],
              "proof_digests": [canonical.digest_of(proof) for proof in proofs]}
    if payload is not None:
        sealed["payload_digest"] = canonical.digest_of(payload)
    sealed.update(changes)
    return sealed


def example_key(fill: str) -> str:
    """A public key of the right shape that no private key stands behind."""
    return "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + (fill * 43)[:43]


def binding(principal: str, public_key: str, established_by: str = "local_creation") -> dict:
    return {"kind": "principal_binding", "schema": 1, "principal_id": principal,
            "credential": {"credential": "device_key", "device_id": ident("dev"),
                           "key_generation": 1, "public_key": public_key},
            "established_by": established_by, "evidence_digests": []}


class Keys:
    """Real ed25519 keys in a directory of the test's own."""

    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        self.private: dict[str, pathlib.Path] = {}

    def make(self) -> str:
        path = self.directory / f"key{len(self.private)}"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f",
                        str(path)], check=True, capture_output=True)
        public = " ".join(path.with_suffix(".pub").read_text().split()[:2])
        self.private[public] = path
        return public

    def envelope(self, public: str, signer_binding_id: str, record: dict,
                 namespace: str = NAMESPACE, data: bytes | None = None) -> dict:
        """A signature envelope over the record's bytes (or over `data` instead)."""
        armored = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(self.private[public]),
                                  "-n", namespace],
                                 input=canonical.encode(record) if data is None else data,
                                 check=True, capture_output=True).stdout.decode("ascii")
        return {"kind": "signature_envelope", "schema": 1, "namespace": namespace,
                "signed_digest": canonical.digest_of(record),
                "signer_binding_id": signer_binding_id,
                "sshsig": "".join(line for line in armored.splitlines()
                                  if line and not line.startswith("-----"))}


class Bench:
    """A state root of a test's own, and the calls made on it."""

    def __init__(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="workenv-v1-")
        self.state = pathlib.Path(self.scratch.name) / "state"
        self.keys = Keys(self.scratch.name)

    def close(self) -> None:
        restart(self.state)
        self.scratch.cleanup()

    def call(self, sealed: dict, carried=(), **options) -> Call:
        return Call(sealed, carried, self.state, **options)

    def run(self, entry, sealed: dict, carried=(), **options) -> dict:
        """The answer the journal gives, wrapping `entry`."""
        return journal.layer_journal(self.call(sealed, carried, **options), entry)

    def store(self) -> storage.Store:
        return storage.of(self.state)
