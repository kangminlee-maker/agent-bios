# ENDPOINTS.md — the core-owned endpoint contract

The network operations agent-bios speaks, extracted from the operating code so the
contract is declared in one place instead of implied by an implementation
(D-20260819-b515a0: one core-owned contract; org/private endpoints arrive on it;
the default install configures none of it). **Gate-bound**: every wire literal
below is held against the code by `gates/check-endpoints.py`, so this file cannot
drift from what actually runs. Facts about the operating server are dated claims
against `day1co-ai-usage-dashboard` `5ab04de` and marked as such — re-derive
before relying on them.

Author-side (not in `package.json` `files[]`), like `SURFACES.md`: it names
author-side paths. The shipped form of this contract is step 6's (SDK packaging)
decision, not this file.

## The five operations

| Operation | State | Realized by |
| --- | --- | --- |
| `ingest-learning` | **extracted** — operating, contract below | `learn/collect-learning.py` upload drain |
| `publish-corpus` | **defined** — name and subject reserved; no network implementation, deliberately | `npm publish` (gated by `gates/check-publish.sh`) |
| `fetch-corpus` | **defined** — same | `npm install` / `git pull` (`install.sh` `cmd_update`) |
| `check-version` | **extracted** — operating, no endpoint of ours | `install.sh` `refresh_update_cache` via `npm view <name> version` |
| `ingest-session` | **not in the extracted contract** — vocabulary reserved, home undecided | dashboard-owned collectors, entirely outside this repo |

`check-version` reads a public version number and sends the package name — nothing
derived from this machine. Selected dependency installation in `compose/corpus_setup.py`
and `launch/provision-venv.sh` likewise uses the user's package-manager configuration;
neither configures corpus ingestion. Three properties
make that true rather than merely intended, and each is worth stating because losing
any one of them turns it into a different operation:

- **It names no registry.** The lookup delegates to `npm view`, so it resolves through
  whatever registry, proxy, and credentials the user already configured — a private
  registry keeps working. `gates/check-endpoints.py` rejects shipped URLs outside
  its declared namespace, documentation and source-repository exceptions.
- **The launcher never performs it.** The TUI reads a local cache
  (`~/.local/share/agent-bios/update-check.json`) and at most spawns the installer
  detached to refresh it, at most once every 24h. A launch is never blocked on the
  network, and an offline machine records the attempt rather than retrying every launch.
- **`AGENT_BIOS_UPDATE_CHECK=0` turns it off**, and the gates' launcher fixture sets
  exactly that — a gate that reaches the network is not a gate.

`ingest-session`'s home — base operation vs separately governed extension — is an
open design question (roadmap step 4). Default-off does not remove a capability
from the product's identity, so nothing here defines it; this table only records
that the name is taken.

## ingest-learning — the wire contract (operating)

- **Request**: `POST {base}/api/ingest/learnings` — the path is the constant
  `INGEST_PATH` in `learn/collect-learning.py`. Header
  `X-Hook-Token: <opaque per-user token>`; `Content-Type: application/json`.
- **Identity is out of band.** The server derives the user from the token; the
  payload must not carry an email or user field. This is a body property, not a
  storage property — the operating server stores the derived identity alongside
  the payload it received (see the server facts below for what it changes).
- **Payload**: one learning record, authority `learn/learning.schema.json`
  (`$id` `urn:agent-bios:schema:learning:v1`, `additionalProperties: false`).
  `schema_version` (integer, currently `1`) is the only version marker: the
  operating server applies v1 shape checks only when `schema_version == 1` and
  stores newer versions tolerantly, so a newer client is not rejected by an
  older server. There is no URL or content-type versioning.
- **Response**: the HTTP status is the entire contract — no response body is
  parsed. `2xx` settles a record (server dedups by learning id); `400` and
  `413` settle it as permanently rejected; every other status (or a network
  error) is transient and **stops the drain** — no retry inside an invocation,
  retry on the next `learn!`. Redirects are **not followed** (urllib would
  re-send a redirected POST as a bodyless GET), so a `3xx` is transient: fix
  the configured URL. A record or token the client cannot turn into a request
  at all — a value urllib rejects, text that is not UTF-8 encodable — settles
  like a `400` rather than counting as transient: retrying cannot help, and
  classing it transient wedged every later record behind it while reporting
  the wedge as a server outage.
- **Client budget**: at most 25 POSTs per invocation (a hard cap), a 5.0 s wall
  clock **checked before each send**, and a 3.0 s socket timeout per request
  (`learn/collect-learning.py` constants). The wall figure is a stop condition,
  not a ceiling: a send that starts inside the budget runs to completion, so an
  invocation can exceed 5.0 s by up to one request. The socket timeout bounds each blocking socket operation, not the
  whole request: a server that drips one header per interval, or a slow DNS
  resolution (which the timeout does not cover at all), extends a single POST
  past both numbers. These are budgets against a cooperating endpoint, not
  guarantees against a hostile one.
- **Operating server facts** (dated, dashboard `5ab04de`): 32 KiB body cap
  (413), 100 distinct learnings per rolling 24 h per user (429 — counted and
  inserted in separate statements, so the limit is approximate under
  concurrency), stored keyed `(user, learning_id)` with the payload kept as
  sent except for NUL stripping (`stripNullChars`). Re-derive before relying
  on any of these: they are claims about another repo at one commit.

## Transport configuration — who supplies `{base}` and the token

`transport_config()` (`learn/collect-learning.py`) reads one source and one only:

1. **The agent-bios-owned slot**: `~/.config/agent-bios/ingest-url` +
   `~/.config/agent-bios/token` (0600 recommended). If either file exists the
   slot is claimed and must be complete, non-empty, and a usable http(s)
   endpoint — a half-configured, empty, unreadable, or unparseable slot fails
   loud with the file named, and never falls through. The slot is rooted at
   `$HOME`, deliberately host-independent. Private learning records and upload
   state live under `$AGENT_BIOS_CORPUS_DIR`, defaulting to
   `~/.config/agent-bios/corpus`, with a separate `learnings/<host>/` directory
   for each host. Changing that private root does not move the transport slot.
   `--config-dir` is accepted only with `AGENT_BIOS_LEGACY_INSTALL=1`, where
   it overrides the native host home; `$CLAUDE_CONFIG_DIR` / `$CODEX_HOME` do
   not relocate private records. Use `--no-upload` for local-only capture or
   `--dry-run` for validation without writes or uploads. An isolated test home
   must also isolate any explicitly configured private roots.
2. **Nothing else.** There is no second source and no fallback: an unset slot
   means upload is skipped with a notice, which is the default install.

**Filling the slot is the adopter's side of the contract, not the core's.** An
organization supplies its own endpoint and token through a wrapper that writes
these two files and then forwards the CLI — `day1-agent-bios` is that wrapper
for day1co, and the shape is repeatable: the ingest URL is an organization
constant carried in the wrapper's own config, the token is a per-user secret
the organization already issues, and neither ever appears here. A wrapper is
also the only thing that may write the slot: no host-home directory, hook
file, or ambient machine state configures transport, so an install cannot
inherit an endpoint it was never given.

No environment variable, config key, or shipped file holds an endpoint value.

`AGENT_BIOS_LEGACY_INSTALL=1` is a compatibility selector for legacy local
storage/projection behavior. It is not a transport configuration source: it
cannot supply an endpoint, token, auth scope, request header, or client budget.
`gates/check-endpoints.py` names this one nontransport environment read and
requires the collector to keep exercising it; any additional environment read
remains a gate failure until it is classified with the same scope.

## Zero egress by default

A default install configures no ingestion endpoint and registers no collection hook.
The scope of this claim is **agent-bios collection egress**. Explicitly selected
dependency installation can fetch packages through Homebrew, npm or pip; host CLI
execution and app model requests use the user's host/provider configuration. These
are distinct from sending captured data to an agent-bios ingestion endpoint.
`gates/check-endpoints.py` checks the ingestion default: a default home resolves
no transport — and still none with a dashboard-shaped hook directory planted in
the host home, since no such provider exists in the core (the probe proven
against a planted slot before its answer counts) —
`install.sh` never touches the slot or those hook files, every
registered hook command is the bare canonical `python3 central/hooks/<file>.py`
shape resolving to a shipped source, and no shipped file hardcodes an endpoint
URL — each with a negative control. The hook sources are additionally
tripwire-scanned for network primitives; the scan is a tripwire, and the proof
of no-egress is review of those shipped files. The ingest-learning wire
contract itself is exercised live against a loopback server (path, method,
token header, content type, settle statuses, client budget defaults), so a
dead-code evasion of the static anchors still fails on the wire. The
compatibility installed-artifact half — the transport slot directory absent and no
transport resolving on scenario homes, with the installed hook registration equal to
the template — is asserted by `gates/test-install-guides.sh` on its explicit legacy
installation route.

## Local setup, instruction import, and app context

The repository-link request in `README.md` and `ko/README.md` names the public
source declared by `package.json` repository metadata. `INSTALL.md` guides the
host agent through an explicit source download when needed, pinned to one commit
in a caller-owned directory. This acquisition precedes the local setup plan and
uses host tools; it is not an automatic installer request or a corpus transport.
The URL exception is limited to each exact request line and its declared repository.

`compose/corpus_setup.py` probes local commands and previews fixed dependency
installation argv. Only selected dependency actions run after Apply; no package
manager is a source for an ingest URL or token. `--corpus none`, selected packages,
app registration, and instruction capture are separate setup choices.

`agent-bios setup start|inspect|discover|plan|apply|status|resume` exposes the same
controller through local JSON commands in `compose/corpus_setup_cli.py`. It requires
no TTY, Textual, MCP/HTTP server or model SDK. `start` returns the local
`compose/setup/START.md` guide path and language choices before dependency probes.
The conversation uses normal host file/command tools and receives review data through
their output. This is part of the user's ordinary model context, not an ingest upload.
Only explicit Apply runs selected dependency recipes and installation actions; package
acquisition and package-manager downloads retain their separate scopes.

The complete review envelope binds its source, current private state, execution
context and dependency recipes. Durable local receipts distinguish outcomes and
prevent a completed review from repeating effects. Status and resume do not execute
remaining installation work; a fresh review is required for safely resumable actions.
Status describes the recorded attempt; handoff separately reports current package,
runtime and helper verification. If safe local synchronization is unavailable, status
still returns recorded progress and handoff defers checks with null readiness fields.
These checks stay local. Resume follows recorded continuations and returns a
nested review when the remaining work can be reviewed safely.
Neither the protocol nor the app helper's `setup` forwarding fills a transport slot,
enables hooks, registers a server or activates corpus context.

`install` and `onboard` use interactive setup unless `--non-interactive` is explicit;
non-TTY callers without it fail before writes. The package UI's Textual wheels are
shipped in `compose/ui_runtime/`. Installation, package/current-checkout Corpus Studio,
and private/current-checkout launcher rich entrypoints use that bundle.
`compose/corpus_ui_runtime.py` verifies their
manifest, hashes and metadata and extracts them into a process-owned temporary
directory. The UI makes no runtime download or pip installation and requires no
preinstalled system/managed Textual. Normal process exit cleans the extraction; the
launcher also releases it before backend `execve`. It is not a persistent package
installation. A damaged bundle produces repair guidance, not a network fallback.
`gates/build-ui-runtime.py --check` and `--self-test` run offline; only its explicit
author-side `--build` fetches packages, deriving the root version from the provisioner's
`TEXTUAL_PIN`. Optional dependency actions such as learning-validator
installation remain separately selected and may use the configured package index.

`compose/corpus_import.py` reads only selected discovered instruction paths and
stores redacted evidence in the private user root. It neither uploads those sources
nor follows references in their text. Supplying that evidence to a host agent for
semantic classification makes it part of the user's normal model context; it is
not an `ingest-learning` or `ingest-session` operation. The import transaction
preserves original files and records provenance for the new private items.

`compose/corpus_app.py` registers no network service. Optional app registration
creates a local discovery link with implicit invocation disabled. Explicit per-task
use returns selected corpus text through the app's tool/context path, governed by
the host's normal data handling. Its local receipt states `returned-as-context`,
not native startup activation or proof of model reading. Off and unregister do not
retract context already returned. The app helper's explicit `learn` command uses
the same collector and transport slot defined above; app registration and use do
not fill that slot or enable collection hooks.

## publish-corpus / fetch-corpus — defined, not implemented

The subject is the **corpus**: the assembler input set — the `claude/` tree plus
a `compose/domains.json` manifest under a `@scope/name` package identity
(`compose/pkgid.py`). Private baselines and snapshots are local artifacts; these
operation names do not define a network distribution protocol for them.
`publish-corpus` is whatever moves that set to a distribution point;
`fetch-corpus` is whatever brings it to a machine `install.sh` can assemble
from. Today both are realized by the npm package (and, in a clone, `git pull`)
— the table above. The names are reserved here so the
public corpus-sharing service (roadmap step 7, demand-gated) and the SDK
(step 6) implement this contract instead of minting a second vocabulary — until
then, adding network machinery for them would be capability nobody consumes.
