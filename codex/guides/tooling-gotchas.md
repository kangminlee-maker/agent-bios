---
guide_id: tooling-gotchas
language: en
status: active
use_when:
  - a shell command's exit code or output will gate a pass/fail or verification decision
  - a tool returns empty / no-match / not-found output that contradicts other evidence
  - running git diff over ranges, or pulling into a worktree with local changes
  - passing dynamic or untrusted strings through a shell command line
  - operating cloud/managed-service CLIs, update APIs, or secrets-bearing config
  - spawning subprocesses or long-lived handles
core_rules:
  - pin ambient state (interpreter, CLI context, command resolution) where an outcome depends on it
  - a piped command's exit code reflects only the last stage — capture the stage under test
  - treat surprising empty output as a tool artifact hypothesis before a world fact
  - git two-dot diff is a snapshot comparison, not a range exclusion; protect dirty worktrees before pulling
  - own the full lifecycle of anything you spawn
---

# Tooling Gotchas

Concrete, tool-level traps behind the global principles. Shared Claude/Codex hook
injections derive their text from this file — edit here, never in the hook
data (single source of truth).

## Ambient state drifts — pin it

Instances of the global rule: ambient state silently drifts; where an outcome
depends on it, pin it explicitly instead of trusting the environment.

- **Interpreter**: the default shell differs across machines (zsh/bash/dash)
  and bash-only idioms misbehave silently elsewhere (unquoted-variable word
  splitting, `read -r -d ''` hangs). Don't probe the shell per command — make
  shell identity irrelevant: keep inline one-liners POSIX-portable; when a
  bash-specific feature (arrays, `read -d`, `PIPESTATUS`) is needed, pin the
  interpreter with a `#!/bin/bash` script file or `bash -c '…'`. The session
  environment block already declares the shell — read it for free; probe only
  when diagnosing a misbehavior.
- **Command resolution**: a command name is not a fixed binary — interactive
  shells resolve functions/aliases first, programmatic spawns resolve raw
  PATH, and a same-named package can shadow a system tool with silent empty
  output. Before trusting a result across execution contexts, confirm the
  resolved target (`type -a`, absolute path). A missing prefix wrapper fails
  the same silent way — GNU `timeout` is routinely absent on BSD-derived
  systems — so confirm the wrapper too.
- **Cloud CLI context**: gcloud/aws/kubectl/terraform carry mutable ambient
  context (active project, profile, cluster) that drifts between sessions.
  Before the first environment-affecting command — or right after a resume —
  verify it against intent, then pin the target explicitly on every command
  (`--project`, `--profile`, `--context`) rather than fixing the global
  default once. A forge CLI (`gh`/`glab`) reads its repository from the
  checkout's remotes too: with a fork plus an upstream it can answer for the
  wrong repo, so pass `--repo` wherever the answer feeds a decision.
- **Installed is not running**: a live process keeps its old code until
  restarted or reloaded. When confirming an update, config change, or
  dependency bump took effect, don't stop at the on-disk artifact — confirm
  the running process's actual version/behavior or force a restart.
- **Producer newer than consumer**: when a deployed binary validates an
  artifact you produce (a signed config or manifest), produce and verify it
  with the producer tooling checked out at the exact commit that binary was
  built from — a local verify with current-tree tooling proves only that
  newer tooling accepts it. Confirm the consumer's build commit from image
  provenance, not the current branch; any version mismatch is a release
  blocker. A consumer rebuilt from the same commit needs only ordinary
  verification.
- **A dev-labelled datastore target is a claim**: a localhost URL or
  exported override is no evidence of a non-production target — a local port
  can proxy into the only real instance, and a tool's config loader can
  re-load a dotenv over your exported value. Before the first writing
  command (migration, seeder), print what the connection reaches from inside
  the tool's own path and assert it is the intended target; where the loader
  is untrustworthy, extract the DDL and apply it yourself.

## Shell execution traps

- **Pipe exit masking**: `$?` after a pipeline reflects only the last stage;
  a real failure upstream is masked by a successful `tail`/`grep`/`jq`,
  reading green. Capture the tested stage's own status: run it unpiped,
  store `$?` immediately, or use `set -o pipefail`/`PIPESTATUS` — a
  per-command choice, since pipefail breaks early-exit consumers (`cmd |
  head -1`, `grep -q` on a long producer → SIGPIPE 141). The
  final-stage-assertion exemption (`cmd | grep -q pattern`) holds only
  without pipefail; under it, capture output and check its status first.
- **Passthrough arguments in a CLI you author**: an option meant to carry
  another command's own flags cannot use a greedy-but-dash-stopping arity —
  Python's `nargs="+"` ends at the first token starting with `-`, so the
  wrapped command's `--model x` lands on the next positional and the error
  names a parameter the caller never mentioned. Use the parser's
  everything-after form (`argparse.REMAINDER`). A bare `--` separator is a
  second, separate trap: argparse consumes it as its own positional marker
  before the remainder sees it, so the form every caller reaches for first is
  the one that breaks — normalize it out of `argv` before parsing.
- **CLI flag probes that execute**: probe a CLI only with invocations that
  cannot do real work — a help form, or the candidate flag paired with a
  control flag that forbids execution (dry-run, an invalid required
  argument). Never run a subcommand bare, and assume a value after a flag
  may be read as positional input: a boolean flag does not consume it, so it
  falls through and runs. Tell a boolean from an unregistered flag by the
  parser's error, not by the run succeeding.
- **Reserved parameter names**: assigning to reserved shell names (`UID`,
  `EUID`, `GID`, `PPID`) can invoke the bound system behavior instead of
  storing a value — silently changing process credentials mid-script. Use
  unreserved names; if such an assignment already ran alongside a
  side-effecting command, verify the resulting system state directly instead
  of assuming the mistake inhibited the command.
- **Metacharacter-bearing values**: prompts, filenames, or content strings
  that may contain `$`, backticks, quotes, or globs must not be inlined as
  raw CLI arguments — the shell expands or mangles them before the target
  process sees them. Pass via stdin, heredoc, or a temp file. (Our dispatch
  scripts codex-run/codex-helm already accept stdin — use that path.)
- **Multi-line pasted commands**: a command pasted across lines without
  continuation markers can be re-wrapped into two invocations, silently
  dropping trailing flags (a real incident: `--scopes` lost during an auth
  flow → wrong-scope credential). After running one, verify the target's
  actual state (granted scopes, applied settings); on re-run, join to one
  line or use explicit continuations.

## Tool output is a rendering, not the bytes

- **grep binary heuristic**: grep silently treats heavy non-ASCII or
  NUL-containing text files as binary and returns a false no-match without
  error. When a no-match contradicts other evidence (git diff, an earlier
  read), re-check with the harness Grep tool (ripgrep) or `grep -a`, or read
  the file directly.
- **Viewer normalization**: file-read tools can render non-printable bytes
  (NUL) as visually indistinguishable blanks. When correctness rides on
  byte-exact content (delimiters, encodings), verify with `hexdump`/`od` or a
  byte-comparing script, not the rendered view.
- **Stale caches in rapid loops**: mtime/size-keyed compile or rewrite caches
  can re-serve a previous file's result when mutate→test cycles run within
  timestamp resolution (mutation testing). Clear the cache or run no-cache
  per iteration, and re-confirm the unmutated baseline still passes after a
  cache clear.
- **Transport limits are measured on the wire payload, in the provider's
  unit**: take the unit and value from the provider's rejection or a live
  probe, never from docs or a variable's name, and measure the serialized
  payload the consumer receives — after encoding and wrappers — not the
  object you assembled. A character count against a byte limit undercounts
  multibyte text, hiding while inputs are ASCII; an item count bounds no
  size. Enforce at one dispatch chokepoint, deriving every budget from that
  constant.

## Git operations

- **A stale local base inflates the range**: before reasoning about what a branch
  contains or opening a PR, `git fetch`, then ask against the remote rather than the
  local tracking ref — `git log origin/<base>..HEAD` for which commits are yours, and
  the merge-base form below for the diff. On a shared repo the local base lags until
  you pull, so `<base>..HEAD` quietly folds in work that already merged. When a range
  looks surprisingly large, suspect the base before the branch.
- **"Mergeable" is measured against the base, not against siblings**: the platform
  flag says each PR merges into the base, and two PRs can both be clean while
  conflicting with each other. Before choosing a merge order, diff their changed-file
  sets and simulate the sequence.
- **Two-dot diff semantics**: `git diff A..B` is a direct snapshot
  comparison — unlike `git log A..B` it excludes nothing, so a lagging
  merge-base injects unrelated upstream changes into the diff. For PR/review
  diffs use `git diff origin/base...HEAD` (merge-base form); suspect this
  mechanism first when a diff looks too large or shows deletions in untouched
  files.
- **Reverting a path is not undoing your edit**: `git checkout <path>` and
  `git restore <path>` discard *every* uncommitted change in that file. Used
  to remove a planted probe it also removes whatever else was in flight there,
  and the loss is silent. Check `git diff <path>` first, or plant in a copy and
  restore from that. The same asymmetry makes the restore step fragile: if the
  probe can time out or abort, the restore must not be the next command in the
  same invocation — put it where a failure cannot skip it.
- **An ignore rule can swallow a durable record**: before treating a path as
  durable — a new ledger, a cited authority — run `git check-ignore -v
  <path>` and `git ls-files --error-unmatch <path>`. Broad runtime-state
  patterns (`*.jsonl`, `runs/`, `out/`) absorb a new file, and a tracked
  file pointing at an ignored path is an authority that exists in one
  checkout only. Fix with a negation rule proven by a sibling that stays
  ignored; genuinely ephemeral output stays ignored.
- **Dirty-worktree pulls**: before pulling into a worktree with
  staged/unstaged/untracked changes, fetch first and compare incoming paths
  against every dirty path; on overlap or a non-fast-forward, stop and clear
  the conflict risk (stash, commit, ask). Otherwise pull `--ff-only`, confirm
  dirty changes survived, and regenerate any local derived artifacts whose
  inputs were updated.
- **A split series is proven commit by commit**: order them by dependency
  and check each out into a throwaway worktree to run the build, tests, and
  gates before pushing. Green only at the tip hides a broken bisect point
  and a commit that cannot be reverted alone — usually a rename or shared
  hunk in the wrong commit. If a handoff cites the branch's hashes, merge
  with a merge commit: squash and rebase rewrite every hash.
- **A shared tree holds other operators' work**: a commit you did not make, a file the
  editor reports changed on disk, a staged path you never added, one more field than
  your predicted post-state — treat an unexplained delta as someone else's work, not
  noise. Before a sweeping write (`git add -A`/`.`, `commit -a`, `stash`, `clean`,
  `reset --hard`), attribute it (`git status`, reflog timestamps, other live sessions)
  and then act only on what you can prove is yours — add by name.

## Config, secrets, and managed services

- **Verbatim slicing over parse-reserialize**: when provisioning part of a
  user's structured config (TOML/YAML/INI) that may carry secrets and
  comments, extract the section's raw text instead of parsing and
  re-serializing — rewrites silently drop comments, formatting, or secret
  values. Use a parser only for real structural change, and test the slicer
  against actual shapes first.
- **Merge-not-replace update APIs**: managed-service update calls (secret
  rotation, mount changes) often merge new definitions into the existing set,
  leaving stale, unreferenced definitions live. After updating, re-read the
  resource, check definitions and active references separately, and remove
  the orphans explicitly.
- **Derive a new revision from the live one, not from a template**: a
  replace-semantics update drops every field the command does not restate,
  and wrappers commonly default mounted secrets to off. Render the exact set
  the command will send, derived from the live resource, and diff it field
  by field; a field that disappears, or an operational value that moves
  backward, is a blocker to explain, not a default to accept. Re-read the
  resource afterwards, since a command rarely labels its semantics.
- **A new revision is not live traffic**: on a runtime that pins traffic to a
  named revision (e.g. Cloud Run with a fixed split), `gcloud run deploy` (or
  the equivalent) creates the new revision but shifts no traffic to it — the
  previous revision keeps serving until an explicit `gcloud run services
  update-traffic`. Read the "deploy succeeded" message as "a revision exists",
  not "the new code is serving"; verify the live traffic split before
  concluding the deploy took effect.
- **Job logs outlive the execution**: a managed job that has run more than
  once under one name — including one deleted and recreated with the same
  name — returns the earlier incarnations' output when its logs are read by
  job name. Scope every read to the execution id you received at launch and
  confirm the timestamp window covers that run. An unscoped read merges
  prior runs into the present and yields confident false diagnoses that a
  scoped read reverses.
- **Dispatch status is not execution**: a CLI `--wait` returning or timing
  out, a scheduler reporting success, a trigger accepted without error —
  each reports what the dispatcher saw, not whether the target ran or what
  state it reached. Before retrying or declaring done, re-derive the state
  from the target's own record (its execution describe, the handler's logs),
  matched to the run by id, and keep a manual probe distinguishable from the
  scheduled one. A blind re-launch is a duplicate execution with side
  effects.
- **An apply cut off before confirmation is unconfirmed** — neither done nor
  un-run: when a multi-statement side-effecting apply (migration, batch
  write) loses its confirmation channel, enumerate which target objects
  already exist in the store, and plan the rerun from that partial state; a
  naive rerun half-fails on "already exists" and leaves a second partial
  state. Where the runner surfaces only exit status, route the object list
  out through a deliberate failure. A transactional or provably idempotent
  apply needs only the confirmation.
- **A traffic rollback is not a config rollback**: on a revision-pinned
  runtime, sending traffic back to the previous revision restores behavior
  but leaves the added env var or secret binding in the service template,
  where the next deploy re-enables it silently. Count a rollback complete
  only when the traffic split and the service spec are both back to the
  prior state — re-read the spec and remove the change explicitly. Runtimes
  that redeploy the prior spec itself (immutable-artifact, GitOps) have no
  such gap.
- **Perimeter controls need the enforcement point's own logs**: an
  agent-side fetch is not an independent observer — its egress IP and
  caching path are opaque, and it may share the protected network or serve a
  stale cached response. Verify allow AND deny directions from those logs,
  and check for a front-side cache/CDN separately. Aim the probe at an
  in-unit sentinel the app answers without credentials: a denial the app
  produces anyway passes with the control off, and a redirect into it is a
  bypass.
- **Tightening exposure is a behavior change for external clients**: switching
  ingress mode, adding an allowlist, or requiring auth is not safe when
  callers live outside your redeploy. Enumerate which clients reach the
  endpoint and by which hostname, verify from a client's vantage, and
  confirm inbound volume did not fall to zero — clients you cut off raise no
  error on your side, so enforcement-point logs alone can sever ingestion
  silently. Callers you redeploy in the same change need only the ordinary
  deploy check.
- **Smoke limits outlive the smoke test**: item caps, sample sizes, and row
  limits left in env vars/flags/config make a later "full-scale" run silently
  succeed on a slice. Clearing or explicitly verifying their absence is a
  precondition of declaring a full run.
- **A remote handle is valid only when it was read**: a row index in a sheet
  that auto-sorts, a downloaded copy of a hosted file — each moves between
  your read and your write. Before writing, re-establish the target from the
  live source: re-locate the row by its key column, not a remembered
  position, and assert the key matches after the write; compare the remote's
  version against the copy you edited, re-downloading and reapplying on a
  move. Local single-writer files need none of this.
- **Packaging and ignore rules are judged against paths and environments, not your tree**: before
  a release, pack the real tarball, install it clean with lifecycle scripts
  ON, and smoke it — a postinstall hook fine in the repo can delete the
  shipped runtime where the build toolchain is absent. After moving or
  renaming a directory, every ignore rule is void for the new paths:
  re-check there and read the staged diff's file count, since old-path
  patterns stop matching and excluded data enters the stage.
- **Shared live config has concurrent writers**: before concluding your edit
  to a shared state/config file was lost or corrupting, rule out concurrent
  writers with a short live observation (mtime plus the fields you changed),
  and scope merge/union operations to the intended fields only.
- **Uniform failure is structural — read the persisted reason, then check the built artifact**: when
  every item in a batch fails and the per-item error is persisted outside
  the log (a status column, a result record), read it before blaming keys,
  quota, or model availability. And when code reads sibling files from its
  working directory, prove they exist inside the built image by listing or
  hashing them there: a selective copy passes every repo-side check and
  fails only at runtime.
- **Production probes expose data**: default diagnostic queries against
  production stores to read-only server-side aggregation (counts, types,
  presence, hashes) — never pull raw payloads into logs, prompts, or
  transcripts — and delete scratch probe resources after the decision.
- **Build-context ignore patterns anchor at the root**: in a `.dockerignore`
  or any root-anchored filter, a bare filename matches only at the context
  root and never in a subdirectory, and an extension glob misses the
  same-purpose credential file carrying another extension. Never conclude a
  shipped image is secret-free from the patterns — list the built artifact's
  own filesystem for credential-shaped files (env files, keys,
  service-account JSON) as a named negative control, repeated whenever the
  build context or ignore file changes.
- **A revoke is grant-wide, not token-wide**: revoking anything issued under
  a client id the user's live sessions share invalidates those sessions too,
  and the failure surfaces later, elsewhere, with no re-auth prompt. A probe
  may clean up only what it alone owns — use minimum scopes and a dedicated
  client id, and let a probe token expire rather than revoking it. Where a
  revoke on a shared grant is unavoidable, state the blast radius and time
  it with the user.

## Own what you spawn

Instance of the global rule: own the full lifecycle of what you create.

- **Subprocess/handle lifecycle**: creating a subprocess means owning spawn
  (set up a process group), result acquisition, and teardown — close owned
  stdio handles, kill exactly that group (not just a wrapper PID, which
  orphans the real child), and await exit. An unref'd child handle or open
  stdin pipe keeps the parent's event loop alive and hangs otherwise-complete
  commands.
- **A handle issued to a human is a commitment**: once a consent URL is
  handed over, the listener behind it must not be restarted, re-ported, or
  replaced while the person may still act — keep it alive until the callback
  lands, or say plainly that the link is dead. The handler captures the
  credential write-once and ignores later hits, since a browser's favicon
  request clears a naive one. Before asking a human to click again, drive
  the handler with a simulated callback.
- **A stop is confirmed at the sink, not in the process list**: a kill that
  misses one descendant lets that stage finish and publish, and the process
  list looks clean either way. After stopping a multi-stage run, list the
  output sink for anything written after the stop instant and roll it back
  as contaminated. Read the rollback path's retention — noncurrent-version
  expiry is a recovery window, not a backup — and snapshot before a risky
  run, choosing the restore point by timestamp.
- **Detach what must outlive the call**: a process started inside a harness
  tool call belongs to that call's process group: a trailing `&` is reaped
  when the call returns, and the harness may signal the group when another
  background task finishes. Launch anything meant to outlive one call
  through the harness's background facility or fully detached
  (nohup/setsid), writing progress to durable files a resume can read. A
  zero-byte output file means it never survived. Detached still means owned
  — PID file and stop path.
- **Name-substring lookup is not a liveness check**: `pgrep -f <name>` and
  `ps | grep <name>` match the argv of the shell running the query itself,
  and match unrelated processes carrying the same name — another session, a
  sibling dispatch, the launcher's own plan text. To decide whether a
  dispatched job is alive, use the PID or handle captured at launch, its
  process-group state, or growth of its own output artifact. Substring
  lookup is for discovery only, confirmed against one of those first.
