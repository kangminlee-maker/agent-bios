"""Signing: the driver's own keys make what a scenario's keys and signatures stand for.

A scenario's key bindings carry an example public key, and its signature envelopes an example
`sshsig`. Signing is the person's side and the driver acts for the person, so before the first
step this generates one ed25519 key for each distinct public key the scenario states (a
`public_key` field anywhere in its records) and puts the generated one in its place everywhere.

Whenever the run builds a signature envelope, whether for a step to submit or as a given answer
to place, it signs the canonical bytes of the record its `signed_digest` names under the
envelope's `namespace`, with the key of the principal binding whose `binding_id` is the
envelope's `signer_binding_id`, through `ssh-keygen -Y sign`. `sshsig` is the armored signature's
body without its header lines (B01). So a signature verifies exactly when the bytes it names are
the bytes it was made over. An envelope whose `signed_digest` the scenario does not join to a
record keeps its example signature, which verifies against nothing. An envelope naming a binding
no record of the scenario states is `failed`: the driver has no key to sign it with.
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess

import executor

ENVELOPE = "signature_envelope"
BINDING = "principal_binding"
KEY_FIELD = "public_key"


def install(run) -> None:
    keys = Keys(run.workdir / "keys")
    run.prepare_hooks.append(keys.replace)
    run.record_hooks.append(keys.seal)
    run.reply_hooks.append(keys.intact)


def stated_keys(value, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == KEY_FIELD and isinstance(item, str):
                if item not in found:
                    found.append(item)
            else:
                stated_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            stated_keys(item, found)


def swapped(value, keys: dict[str, str]):
    if isinstance(value, dict):
        return {k: (keys.get(v, v) if k == KEY_FIELD and isinstance(v, str) else swapped(v, keys))
                for k, v in value.items()}
    if isinstance(value, list):
        return [swapped(item, keys) for item in value]
    return value


class Keys:
    def __init__(self, directory: pathlib.Path):
        self.directory = directory
        self.files: dict[str, pathlib.Path] = {}   # generated public key -> private key file
        self.made: dict[str, bytes] = {}            # generated public key -> its private key
        self.signed: dict[tuple[str, str, str], str] = {}

    def replace(self, run) -> None:
        """One generated key for each public key the scenario states, in its place everywhere."""
        stated: list[str] = []
        for record in run.templates.values():
            stated_keys(record, stated)
        self.directory.mkdir(parents=True, exist_ok=True)
        made = {}
        for index, example in enumerate(stated):
            path = self.directory / f"key{index}"
            ssh_keygen(["-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(path)])
            public = " ".join(path.with_suffix(".pub").read_text().split()[:2])
            made[example] = public
            self.files[public] = path
            self.made[public] = path.read_bytes()
        for name, record in run.templates.items():
            run.templates[name] = swapped(record, made)
        run.forget()

    def intact(self, run, step: dict, message: dict, reply: dict):
        """After each reply, the driver's private keys as it made them: code under test that
        wrote over them wrote outside its state root."""
        for public, path in self.files.items():
            if not path.is_file() or path.read_bytes() != self.made[public]:
                raise executor.Stop(executor.FAILED, f"the private key the driver made for "
                                    f"{path.name} was changed while the code under test ran, "
                                    "outside its state root", step=step["name"])
        return reply

    def signer(self, run, binding_id: str) -> str | None:
        """The public key of the principal binding the run knows under this binding id."""
        for name, record in run.templates.items():
            if not isinstance(record, dict) or record.get("kind") != BINDING:
                continue
            value = record.get("binding_id")
            for join in run.joins.get(name, []):
                if join["pointer"] == "/binding_id" and "minted" in join:
                    value = run.learned.get(join["minted"], value)
            if value == binding_id:
                return record.get("credential", {}).get(KEY_FIELD)
        return None

    def seal(self, run, name: str, value):
        if not isinstance(value, dict) or value.get("kind") != ENVELOPE:
            return value
        named = next((join["digest_of"] for join in run.joins.get(name, [])
                      if join["pointer"] == "/signed_digest" and "digest_of" in join), None)
        if named is None:
            return value
        public = self.signer(run, value.get("signer_binding_id"))
        if public not in self.files:
            raise executor.Stop(executor.FAILED, f"{name} is signed by the binding "
                                f"{value.get('signer_binding_id')}, and no principal binding of "
                                "the scenario states a key under that id to sign it with")
        data = run.bytes_of(named)
        key = (public, value["namespace"], hashlib.sha256(data).hexdigest())
        if key not in self.signed:
            armored = ssh_keygen(["-Y", "sign", "-f", str(self.files[public]),
                                  "-n", value["namespace"]], data)
            self.signed[key] = "".join(line for line in armored.decode("ascii").splitlines()
                                       if line and not line.startswith("-----"))
        return {**value, "sshsig": self.signed[key]}


def ssh_keygen(arguments: list[str], data: bytes | None = None) -> bytes:
    try:
        done = subprocess.run(["ssh-keygen", *arguments], input=data, capture_output=True,
                              timeout=30)
    except FileNotFoundError as error:
        raise executor.Stop(executor.BLOCKED, "ssh-keygen is not on PATH, so the driver cannot "
                                              "sign for the person") from error
    if done.returncode != 0:
        raise executor.Stop(executor.BLOCKED, f"ssh-keygen {arguments[0]} {arguments[1]} exited "
                            f"{done.returncode}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout
