# Install agent-bios

This is the agent's runbook for an installation request naming this repository.
The user supplies the repository link; the agent handles paths and commands.

Ask the user to choose English, 한국어 or 日本語 before running prerequisite or
dependency probes. Honor a language already selected in the request. Use a native
question control when available, or an ordinary short question. Run on the intended
local machine; a remote executor's home is a different installation target.

## Obtain the source

If the user explicitly selected an existing trusted source directory, use it
without pulling, switching branches or modifying it. Record its location and any
available commit/dirty-state information. Otherwise obtain the repository named in
the request. Do not substitute an old global CLI or require a global npm install.

With Git available, use the sequence below. The agent fills `BIOS_SETUP_REPO` from
the request using a structured argument or a properly quoted shell literal; the
user does not type a path. Run this in a dedicated Bash tool call and stop on any
failure. Keep these variables in that call or retain their values as caller-owned
data.

Before acquisition, tell the user which repository and cache/workdir destination
will be used. Explain that this downloads source and retains private cache/artifact
files now, separately from the installation effects reviewed at Apply.

```bash
set -eu
BIOS_SETUP_REPO='<repository URL from the installation request>'
umask 077
BIOS_SETUP_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/agent-bios-acquisition"
mkdir -p "$BIOS_SETUP_CACHE"
BIOS_SETUP_SOURCE="$(mktemp -d "$BIOS_SETUP_CACHE/source.XXXXXX")"
git -c core.hooksPath=/dev/null clone --quiet --depth 1 --single-branch \
  --branch main --no-checkout "$BIOS_SETUP_REPO" "$BIOS_SETUP_SOURCE"
BIOS_SETUP_COMMIT="$(git -C "$BIOS_SETUP_SOURCE" rev-parse --verify HEAD)"
git -C "$BIOS_SETUP_SOURCE" -c core.hooksPath=/dev/null \
  checkout --quiet --detach "$BIOS_SETUP_COMMIT"
git -C "$BIOS_SETUP_SOURCE" rev-parse --verify HEAD
```

Confirm the final full commit equals `BIOS_SETUP_COMMIT`. The clone resolves
`main` once; keep that exact checkout through planning and Apply. Record the
repository, full commit and source location in a caller-owned acquisition artifact
and retain them for resume. An explicitly requested revision takes precedence over
`main`; resolve and retain that revision instead. Do not refresh a moving branch
between review and Apply.

If Git is unavailable, use the host's download capability to obtain the official
repository archive for one resolved full commit. Follow the repository host's
actual commit/archive link rather than inventing a download endpoint. Record the
commit and archive digest, inspect its members, and extract into a new private
directory without allowing paths or links outside it. If that capability is also
unavailable, explain the missing prerequisite and use documented platform Git
installation instructions within the user's authorization.

Acquisition downloads and these cache/artifact files exist before setup Apply.
Report them separately from installation effects and keep the source while setup
or a reviewed continuation may need it. A failed acquisition does not authorize
switching to a different package or installation mode.

## Check this revision before running it

Reread `INSTALL.md` from the acquired revision so its runbook and executable source
come from the same commit. Inspect any difference from the guide that led here;
do not mix their instructions or recursively acquire the repository again.

Read `package.json` as data. Its package name must be `agent-bios`, its repository
identity must match the trusted source, and its `agent-bios` binary must be
`install.sh`. Normalize the package's `git+` prefix and trailing `.git` when
comparing repository URLs. Confirm these required files are regular files whose
resolved paths remain inside the source; do not follow links to outside files:

- `INSTALL.md`
- `install.sh`
- `compose/corpus_setup_cli.py`
- `compose/corpus_setup.py`
- `compose/setup/START.md`

If they are missing, explain that the selected public revision/package does not
provide conversational setup. Stop this installation route and report the checked
revision. Do not run an older `install`, enable compatibility mode, or claim that
unpublished checkout features are available from the public repository.

Bash and Python 3.11 or newer are required. Check them after the language choice.
If missing, explain the prerequisite and help resolve it through documented
platform instructions within the user's authorization. This route does not need
Codex CLI, another model login, Node/npm or Textual. Do not borrow an undocumented
app runtime or install a package manager solely to present the questions.

## Continue in the conversation

Run the acquired source's entrypoint with the chosen language; `ko` below is an
example. These paths are internal command arguments, not information the user must
supply.

```bash
bash "$BIOS_SETUP_SOURCE/install.sh" setup start --language ko
```

Require a successful JSON response with `kind: "agent-bios-setup-start"`,
`schema_version: 1`, an existing `guide_path` inside that source, and matching
`context.package_root`. Read that guide and continue through its returned
`setup_argv`, keeping the same source, working directory and reviewed execution
context. Do not fall back to a PATH command if validation fails.

The detailed guide collects corpus, optional dependencies, app connection and
instruction-source choices, then prepares the exact review for authorized Apply.
Use the existing authorization for concrete effects already accepted by the user.
Preserve global/project `AGENTS.md` and `CLAUDE.md`. Installation and app connection
do not authorize corpus content in this task; that remains a separate explicit use.
