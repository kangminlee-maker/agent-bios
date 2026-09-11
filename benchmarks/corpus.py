#!/usr/bin/env python3
"""Corpus variants for the benchmark's `--corpus` arm.

An arm is a *variant home*: a config home the host CLI loads instead of the
deployed one, holding the corpus under test plus whatever the host needs to
reach its seat from there. Building one is four separable steps, separable
because each failed on its own during the probes that produced this file:

  materialize  copy the deployed corpus into a scratch home, plus the auth files
               the host reads out of that home
  edit         apply the arm's text edits — ablate a child clause, restore one
  rebind       point the global's router references at THIS home's guides
  canary       inject a load marker into the entry file and into every guide, so
               a response can evidence which corpus it read instead of asserting it

**Two hashes, because they answer different questions.** `experiment_hash` is taken
after the edits and BEFORE rebinding and canary injection: it identifies the corpus
under test, so two builds of the same arm produce the same value and two different
arms produce different ones. `realized_hash` is taken at the end and identifies the
bytes the agent actually read, which necessarily include this home's absolute paths
and this build's random canary token. A single hash taken at the end — the first
revision here — differs on every build, which makes "the arms' hashes differ" true
even when the arms are identical, and that is a control that cannot fail. Auth and
host state are excluded from both: two arms differing only in a refreshed token are
the same corpus.

Measured 2026-08-26 (codex-cli 0.149.1, Claude Code 2.1.246), each against a
control arm whose expected answers were inverted — an arm that merely agrees
with the hypothesis does not show the probe can tell the arms apart:

  - CODEX_HOME redirects the global load and stays authenticated once `auth.json`
    is copied in.
  - CLAUDE_CONFIG_DIR redirects the global load but the redirected home is not
    authenticated: the live credential is in the macOS keychain, and a redirected
    home reads only its own (stale) `.credentials.json`. Redirecting HOME instead
    fails identically. It authenticates when the seat is handed over through
    `CLAUDE_CODE_OAUTH_TOKEN` — the channel `claude setup-token` mints for.
  - Neither host exports its home variable into the agent's tool shell, so a
    router written `${CODEX_HOME:-$HOME/.codex}/guides/x.md` resolves to the
    DEPLOYED guide from inside a variant home. The first live canary run caught
    exactly this: the global canary returned while every guide canary reported
    NOT_FOUND. Hence `rebind`.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import subprocess
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent
OWNED_HOOK_NAMES = tuple(json.loads((ROOT.parent / 'compose/domains.json').read_text())['hooks'])

# Per host: the deployed home, the corpus paths inside it (a set, not one file —
# the Claude entry file is a shim whose rules live in an imported bundle), the
# entry file the canary instruction is appended to, the guide directory, the
# router prefix to rebind, and the auth files a redirected home must carry.
HOST_HOMES = {
    "codex": {
        "env": "CODEX_HOME",
        "home": pathlib.Path.home() / ".codex",
        "corpus_paths": ("AGENTS.md", "guides", "agents") + tuple(f"hooks/{name}" for name in OWNED_HOOK_NAMES),
        "entry": "AGENTS.md",
        "guides_dir": "guides",
        "hooks_dir": "hooks",
        "settings": "hooks.json",
        "router_prefix": "${CODEX_HOME:-$HOME/.codex}",
        "auth": ("auth.json", "config.toml"),
    },
    "claude": {
        "env": "CLAUDE_CONFIG_DIR",
        "home": pathlib.Path.home() / ".claude",
        "corpus_paths": ("CLAUDE.md", "central", "personal"),
        "entry": "CLAUDE.md",
        "guides_dir": "central/guides",
        "hooks_dir": "central/hooks",
        "settings": "settings.json",
        "router_prefix": "${CLAUDE_CONFIG_DIR:-$HOME/.claude}",
        "auth": (),
    },
}

# Output meaning the dispatch never reached a seat. Such a response is a defect,
# not a MISS: scored as data it would read as the strongest possible ablation effect.
AUTH_FAILURE_MARKERS = (
    "Not logged in", "Please run /login", "OAuth session expired",
    "Failed to authenticate", "API key is invalid", "Invalid bearer token",
)


class CorpusError(RuntimeError):
    """A variant that cannot be built, named by what is missing."""


def _refuse_repo_destination(dest: pathlib.Path) -> None:
    """A variant home may not be built inside a git work tree.

    It holds a copy of the operator's live host credential, and the dispatched
    agent is told this directory's absolute path (router rebinding writes it into
    the instructions the agent reads). Inside a repository that is a reusable
    secret sitting one directory from a guide the agent opens, in a tree that
    `git add -f`, a packaging step, or another agent's sweep can pick up — and
    the run reports `ok` either way, which is what makes it worth a mechanism
    rather than a warning. Outside a repository the same copy is scratch state
    the run deletes.

    It does not widen what the agent can reach: it already runs as the operator
    and could read `~/.codex/auth.json` directly. What this removes is the second
    copy, its durability, and its committable location."""
    for parent in [dest, *dest.parents]:
        if (parent / ".git").exists():
            raise CorpusError(
                f"{dest}: variant homes carry a copy of the host credential and may not be "
                f"built inside the git work tree at {parent}. Use a scratch directory the run "
                f"deletes (run.py does this); the corpus_hash in each receipt is what makes a "
                f"run auditable afterwards, not the directory.")


def is_auth_failure(text: str) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in AUTH_FAILURE_MARKERS)


def _keychain_oauth_token() -> str:
    """The live Claude seat, read from the keychain into memory.

    Never logged, never written to disk. A redirected CLAUDE_CONFIG_DIR does not
    consult the keychain itself, so the token has to be handed to the child."""
    proc = subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise CorpusError(
            "claude: no keychain credential to hand the variant home. Log in once, "
            "or mint a long-lived token with `claude setup-token` and export "
            "CLAUDE_CODE_OAUTH_TOKEN.")
    try:
        return json.loads(proc.stdout.strip())["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CorpusError(f"claude: keychain payload is not the expected shape ({exc})") from exc


@contextlib.contextmanager
def auth_channel(host: str):
    """Yield `(env_additions, pass_fds)` that let a dispatch reach the seat.

    codex carries its auth in the copied home. claude cannot, so its seat has to
    be handed over — and it travels on a **file descriptor**, not in the
    environment: the process this authenticates is an agent under test that
    spawns its own tool subprocesses, and an environment variable is inherited by
    every one of them, so the operator's own token would be readable by the thing
    being measured. `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` is not inherited
    that way, because the fd is closed as soon as the child has it.

    Proven 2026-08-26 with the control that matters: a garbage token written to
    the fd fails authentication (rc=1) while the real one succeeds, so the fd is
    what authenticates rather than something else quietly doing it.

    A caller-set CLAUDE_CODE_OAUTH_TOKEN still wins as the token's SOURCE — a
    long-lived `setup-token` value outlives a batch, while a keychain access token
    can expire partway through one — but it is never passed on to the child."""
    if host != "claude":
        yield {}, ()
        return
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or _keychain_oauth_token()
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, token.encode())
    finally:
        os.close(write_fd)
    try:
        yield {"CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR": str(read_fd)}, (read_fd,)
    finally:
        os.close(read_fd)


def _corpus_files(home: pathlib.Path, host: str) -> list[pathlib.Path]:
    out = []
    for rel in HOST_HOMES[host]["corpus_paths"]:
        p = home / rel
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += [q for q in p.rglob("*") if q.is_file()]
    return sorted(out)


def corpus_hash(home: pathlib.Path, host: str) -> str:
    """sha256 over the corpus files' (relpath, bytes), sorted — auth excluded."""
    files = _corpus_files(home, host)
    entry = home / HOST_HOMES[host]["entry"]
    if not entry.exists():
        raise CorpusError(f"{entry}: no entry instruction file to hash")
    digest = hashlib.sha256()
    for p in files:
        digest.update(str(p.relative_to(home)).encode())
        digest.update(b"\0")
        digest.update(p.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def canary_line(slug: str, nonce: str) -> str:
    """A guide's marker carries an INDEPENDENT nonce, not a value derived from the
    global canary's token.

    The first version wrote `{token}-{slug}-GUIDE`, and the global instruction hands
    the agent that token — so an agent that read only the global could synthesise a
    guide canary for a guide it never opened, and the check accepted it. A carrier
    proof whose value is derivable from another carrier proves nothing about its own
    carrier."""
    return f"<!-- load-canary --> CANARY_GUIDE: {slug}={nonce}"


def _canary_instruction(token: str) -> str:
    return (
        "\n\n## Load canary\n\n"
        f"- This instruction file carries the load canary `{token}-GLOBAL`. In every "
        "report you produce, add a final line `CANARY_GLOBAL: <token>` quoting it.\n"
        "- Every guide file ends with its own canary line, carrying a value stated "
        "nowhere but in that guide. Whenever you read a guide, copy its "
        "`CANARY_GUIDE: <slug>=<value>` line verbatim into the same report.\n"
        "- If any injected context carries a `CANARY_HOOK:` line, copy that line into "
        "the report too.\n"
    )


INSTALL_MANIFEST = pathlib.Path.home() / ".local/share/agent-bios/manifest.txt"


def manifested_paths(host: str, src: pathlib.Path) -> list[str]:
    """Corpus-deployed paths under this host's home, per the installer's own record.

    `corpus_paths` is a hand-written list and it was wrong: it carried the guides and
    the bundle but not the skills, so the variant reproduced part of the corpus and
    the run measured the rest as absent. The installer already writes down exactly
    what it deployed, so ask it rather than maintain a second list — and it is right
    about what is NOT corpus too: `~/.claude/agents/` predates the current layout and
    is not manifested, so copying it would put stale text in every arm.

    The manifest records DEPLOYED absolute paths, so the home it is relative to is
    this host's deployed home — never `src`. With `--corpus` pointing at a candidate
    tree those are different directories, every entry raised ValueError, and each was
    skipped in silence: the arm then measured a candidate with its manifested skills
    omitted while reporting normal hashes. An absent or unmappable manifest is now an
    error rather than an empty footprint, because "the corpus deployed nothing here"
    and "we could not find out" are not the same answer."""
    home = pathlib.Path(HOST_HOMES[host]["home"]).resolve()
    if not INSTALL_MANIFEST.exists():
        raise CorpusError(
            f"{INSTALL_MANIFEST}: no installer manifest, so the corpus footprint for "
            f"{host} cannot be established — an arm built on a guessed footprint is not "
            f"the arm it claims to be")
    rels = set()
    for line in INSTALL_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rel = pathlib.Path(line).resolve().relative_to(home)
        except ValueError:
            continue
        # FILE granularity, not the containing tree. Collapsing `skills/repo-charter/
        # SKILL.md` to `skills` copied the operator's own thirty-odd skills into every
        # arm — variables the experiment never declared, and the exact mistake the hook
        # rule exists to avoid. The manifest lists every file the corpus deployed, so
        # the files it names ARE the corpus.
        rels.add(str(rel))
    if not rels:
        raise CorpusError(
            f"{INSTALL_MANIFEST}: no entry maps under {home}, so this host's manifested "
            f"footprint would be empty — the manifest is present but says nothing about "
            f"{host}, which is a stale or foreign manifest rather than a hookless corpus")
    return sorted(rels)


def _rebind_hook_command(command: str, spec: dict, src: pathlib.Path,
                         dest: pathlib.Path, marker: str) -> str:
    """Point a registered hook command at THIS arm's copy, or refuse the arm.

    The old form was `command.replace(str(src), str(dest))`. Under `--corpus` the
    settings file is the candidate's copy but the command inside it still names the
    DEPLOYED hook, so `str(src)` occurs nowhere and the replacement was a no-op: the
    arm reported itself rebound and ran the deployed hook, which is precisely the text
    an ablated arm is supposed to be missing. Resolution is structural — take the path
    apart against the deployed home or the source, rebuild it under `dest` — and every
    way of not succeeding raises, because a silently unrebound hook is indistinguishable
    from a rebound one in the receipt."""
    homes = [pathlib.Path(spec["home"]).resolve(), pathlib.Path(src).resolve()]
    out, rebound = [], 0
    for tok in command.split():
        if marker not in tok:
            out.append(tok)
            continue
        bare = tok.strip("\"'")
        rel = None
        for home in homes:
            try:
                rel = pathlib.Path(bare).resolve().relative_to(home)
                break
            except ValueError:
                continue
        if rel is None:
            raise CorpusError(
                f"hook command {command!r}: {bare} is under neither the deployed home "
                f"nor {src}, so it cannot be rebound into this arm")
        target = dest / rel
        if not target.exists():
            raise CorpusError(
                f"hook command {command!r}: {rel} is registered but absent from the "
                f"variant, so the arm would run a hook it does not contain")
        out.append(tok.replace(bare, str(target)))
        rebound += 1
    if not rebound:
        raise CorpusError(
            f"hook command {command!r}: nothing in it resolved to a hook path, so the "
            f"registration would still target whatever it targeted before")
    rewritten = " ".join(out)
    if str(dest) not in rewritten:
        raise CorpusError(f"hook command {command!r}: rebinding produced {rewritten!r}, "
                          f"which does not point into {dest}")
    return rewritten


def corpus_hook_entries(host: str, src: pathlib.Path, dest: pathlib.Path) -> dict:
    """The deployed hook registrations the CORPUS owns, rebound into this arm.

    A hook is a delivery surface for this corpus — one of them injects the
    tooling-gotchas rules at tool-call time — so a variant home with no hook
    registration measures the corpus with part of its delivery removed. Only
    entries whose command points into the corpus's own hook directory are taken:
    session collectors, notifiers and plugin hooks belong to this machine, not to
    the corpus, and copying them would add variables the experiment did not
    declare.

    Every path is rewritten to this home for the same reason the routers are: a
    registration left pointing at the deployed tree runs the DEPLOYED hook, so an
    ablated arm would keep receiving the very text it is supposed to be missing —
    and unlike a guide, nothing in the response names the file it came from."""
    spec = HOST_HOMES[host]
    settings = src / spec["settings"]
    marker = f"/{spec['hooks_dir']}/"
    try:
        sources = [json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})] if settings.exists() else []
        if host == "codex" and (src / 'config.toml').exists():
            inline = tomllib.loads((src / 'config.toml').read_text()).get('hooks', {})
            sources.append({event: groups for event, groups in inline.items()
                            if event not in {'state', 'managed_dir', 'windows_managed_dir'}})
    except (ValueError, OSError, AttributeError) as exc:
        # An unreadable settings file is not evidence that the corpus registers no
        # hooks. Returning {} here is the same value a legitimately hookless corpus
        # returns, so the variant would drop the whole hook delivery surface and every
        # later receipt would still read ok.
        raise CorpusError(f"{settings}: hook registrations unreadable ({exc}) — this is "
                          f"not the same answer as a corpus with no hooks") from exc
    kept = {}
    registered = {}
    for source in sources:
        if not isinstance(source, dict):
            raise CorpusError(f'{settings}: hook registrations unreadable (expected event mapping)')
        for event, groups in source.items():
            if not isinstance(groups, list):
                raise CorpusError(f'{settings}: hook registrations unreadable ({event} must be a list)')
            registered.setdefault(event, []).extend(groups)
    def owned(handler):
        command = str(handler.get('command', ''))
        if marker not in command:
            return False
        if host == 'claude':
            return True  # central/hooks is the legacy corpus-owned tree.
        # Codex hooks/ is shared with other tools; its directory alone grants no ownership.
        try:
            return any(token.endswith('/hooks/' + name) for token in shlex.split(command)
                       for name in OWNED_HOOK_NAMES)
        except ValueError as exc:
            raise CorpusError(f'{settings}: hook command cannot be parsed') from exc
    for event, entries in registered.items():
        for entry in entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get('hooks'), list)
                    or not all(isinstance(handler, dict) for handler in entry['hooks'])):
                raise CorpusError(f'{settings}: hook registrations unreadable ({event} has malformed handlers)')
            mine = [h for h in entry.get("hooks", [])
                    if owned(h)]
            if not mine:
                continue
            kept.setdefault(event, []).append({
                **{k: v for k, v in entry.items() if k != "hooks"},
                "hooks": [{**h, "command": _rebind_hook_command(
                    str(h["command"]), spec, src, dest, marker)} for h in mine],
            })
    return kept


def _codex_config_without_hooks(text: str) -> str:
    """Keep auth/runtime config, excluding ambient inline hooks and trust state.

    The semantic comparison makes unusual TOML fail explicitly instead of
    silently carrying an uninstrumented hook into the benchmark.
    """
    original = tomllib.loads(text)
    expected = {key: value for key, value in original.items() if key != 'hooks'}
    kept, skip = [], False
    for line in text.splitlines(keepends=True):
        if re.match(r'^\s*\[', line):
            try:
                table = tomllib.loads(line + '\n__benchmark_probe__ = true\n')
            except ValueError:
                pass  # A line in a multiline value; the comparison below is authoritative.
            else:
                skip = 'hooks' in table
        if not skip:
            kept.append(line)
    result = ''.join(kept)
    try:
        valid = tomllib.loads(result) == expected
    except ValueError:
        valid = False
    if not valid:
        raise CorpusError('Codex inline hook config cannot be isolated without changing unrelated settings; use [hooks] tables')
    return result


def build_variant(host: str, dest: pathlib.Path, token: str, edits=(),
                  source: pathlib.Path | None = None) -> dict:
    """Materialize a variant home and return its record.

    `edits` is a sequence of (relpath, old_text, new_text). `old_text` must occur
    EXACTLY ONCE in the file: an edit matching nothing yields an arm identical to
    the one it was meant to differ from, and the two would then be compared as if
    they differed."""
    if host not in HOST_HOMES:
        raise CorpusError(f"unknown host {host!r}")
    spec = HOST_HOMES[host]
    src = pathlib.Path(source) if source else spec["home"]
    if not (src / spec["entry"]).exists():
        raise CorpusError(f"{src / spec['entry']}: deployed entry file not found")

    dest = pathlib.Path(dest).resolve()
    _refuse_repo_destination(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    dest.chmod(0o700)

    # Declared trees plus the exact files the installer says it deployed here; the
    # union is the corpus's real footprint, and the manifest is the half that cannot
    # go stale.
    for rel in sorted(set(spec["corpus_paths"]) | set(manifested_paths(host, src))):
        s = src / rel
        if s.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dest / rel)
        elif s.is_dir():
            shutil.copytree(s, dest / rel)
    for name in spec["auth"]:
        if (src / name).exists():
            if host == 'codex' and name == 'config.toml':
                (dest / name).write_text(_codex_config_without_hooks((src / name).read_text()))
            else:
                shutil.copy2(src / name, dest / name)
            (dest / name).chmod(0o600)

    pre_edit_hash = corpus_hash(dest, host)
    applied = []
    for rel, old, new in edits:
        if old == new:
            raise CorpusError(f"{rel}: edit replaces text with itself")
        target = dest / rel
        if not target.exists():
            raise CorpusError(f"edit target {rel} absent from the variant")
        text = target.read_text(encoding="utf-8")
        hits = text.count(old)
        if hits != 1:
            raise CorpusError(
                f"{rel}: edit anchor occurs {hits} times, not once — an arm built on "
                f"an ambiguous anchor is not the arm it claims to be")
        target.write_text(text.replace(old, new), encoding="utf-8")
        applied.append(rel)

    # Before instrumentation: this is the corpus the experiment is about.
    experiment_hash = corpus_hash(dest, host)
    if edits and experiment_hash == pre_edit_hash:
        raise CorpusError(
            "the edit set changed no corpus byte (an identity replacement, or edits that "
            "cancel), so this arm is the control wearing another name — and its realized "
            "hash would still differ, because paths and canaries differ on every build")

    # Rebind routers across every markdown file in the variant, then assert the
    # rebinding happened: a variant whose routers still resolve to the deployed
    # home reads the deployed guides and is not an arm at all.
    prefix = spec["router_prefix"]
    routed = 0
    for p in sorted(dest.rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        n = text.count(prefix)
        if n:
            p.write_text(text.replace(prefix, str(dest)), encoding="utf-8")
            routed += n
    if routed == 0:
        raise CorpusError(
            f"{host}: no router reference {prefix!r} found to rebind — a variant whose "
            f"routers resolve to the deployed home is not an arm")

    entry = dest / spec["entry"]
    entry.write_text(entry.read_text(encoding="utf-8") + _canary_instruction(token),
                     encoding="utf-8")
    guide_canaries = {}
    gdir = dest / spec["guides_dir"]
    if gdir.is_dir():
        for p in sorted(gdir.rglob("*.md")):
            slug = p.stem
            nonce = secrets.token_hex(6)
            p.write_text(p.read_text(encoding="utf-8") + "\n\n"
                         + canary_line(slug, nonce) + "\n", encoding="utf-8")
            guide_canaries[slug] = nonce
    if not guide_canaries:
        raise CorpusError(f"{host}: no guides under {spec['guides_dir']} to canary")

    # Register the corpus's own hooks against this home, and give each one a nonce
    # so a response evidences that it fired rather than us assuming it did.
    hook_entries = corpus_hook_entries(host, src, dest)
    hook_canary = None
    if hook_entries:
        hook_canary = secrets.token_hex(6)
        hdir = dest / spec["hooks_dir"]
        injected = 0
        for hp in sorted(hdir.rglob("*.py")):
            text = hp.read_text(encoding="utf-8")
            anchor = '"additionalContext": context,'
            if anchor in text:
                hp.write_text(text.replace(
                    anchor,
                    '"additionalContext": context + '
                    f'"\\n<!-- hook-canary --> CANARY_HOOK: {hook_canary}",'),
                    encoding="utf-8")
                injected += 1
        if not injected:
            raise CorpusError(
                f"{host}: {len(hook_entries)} corpus hook event(s) are registered but no hook "
                f"under {spec['hooks_dir']} exposes the context anchor, so nothing would "
                f"evidence that a hook ran")
        (dest / spec["settings"]).write_text(
            json.dumps({"hooks": hook_entries}, indent=2), encoding="utf-8")

    return {
        "host": host,
        "home": str(dest),
        "env": spec["env"],
        "experiment_hash": experiment_hash,
        "realized_hash": corpus_hash(dest, host),
        "token": token,
        "source": str(src),
        "edits_applied": applied,
        "routers_rebound": routed,
        "guide_canaries": guide_canaries,
        "hook_events": sorted(hook_entries),
        "hook_canary": hook_canary,
    }


def verify_unchanged(variant: dict) -> str | None:
    """Re-hash the realized corpus; return a problem string if it moved.

    Called after every dispatch. The hash a receipt carries is taken once at build
    time, so without this a response that ran against mutated bytes still carries
    the pristine digest — the receipt would be true about a corpus that no longer
    existed when the response was produced."""
    now = corpus_hash(pathlib.Path(variant["home"]), variant["host"])
    if now != variant["realized_hash"]:
        return (f"corpus under {variant['home']} changed during the run: "
                f"{variant['realized_hash'][:12]} -> {now[:12]}")
    return None
