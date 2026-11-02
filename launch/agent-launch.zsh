# Alias expansion is OFF while this file is parsed and restored to what it was at the
# end: zsh expands aliases at parse time, inside function bodies too, so an alias named
# `builtin`, `command`, or `claude` that exists when this file is sourced would be baked
# into the functions below and the real binary never reached.
[[ -o aliases ]] && _agent_launch_aliases_were=1 || _agent_launch_aliases_were=0
setopt no_aliases

# Interactive zero-argument entrypoints use agent-launch. Every argument-bearing
# or non-TTY call skips profile projection; Claude retains its direct-path
# permission-bypass default.
_agent_launch_direct() {
  local host="$1"
  shift
  # `builtin command`, not bare `command`. The point of this line is to reach the real
  # binary without re-entering a shell function, and zsh lets a user define `command()`
  # — at which point the bare form calls THAT, and the direct path this wrapper exists to
  # provide is handed to whatever the user's function does. `builtin` cannot be shadowed,
  # so the resolution is the one the comment above already promised.
  if [[ "$host" == "claude" && -z "${_agent_launch_private_connection:-}" ]]; then
    # The permission default goes in front of a prompt or an option, never in front of a
    # subcommand: some subcommands are dispatched only from the first argument, so with a
    # flag in front `claude attach <id>` is a new session whose prompt is "attach <id>",
    # and which ones is the installed version's to say. The subcommands are what that
    # version's `claude --help` lists (_agent_launch_claude_subcommands); a first argument
    # that starts with `-` is no subcommand and needs no probe. When the list cannot be
    # read, the flag stays off.
    if [[ $# -eq 0 || "$1" == -* ]]; then
      builtin command claude --dangerously-skip-permissions "$@"
    elif _agent_launch_claude_subcommands && (( ! ${_agent_launch_claude_verbs[(Ie)$1]} )); then
      builtin command claude --dangerously-skip-permissions "$@"
    else
      builtin command claude "$@"
    fi
  else
    builtin command "$host" "$@"
  fi
}

# The subcommand spellings (`stop|kill` is two) the installed `claude --help` lists under
# `Commands:`, in `_agent_launch_claude_verbs`. Read once per installed binary: the key is the
# binary's resolved path, modification time and size, held in this shell and in
# ~/.local/share/agent-bios/claude-subcommands (the state dir the shadow log below uses, never
# created here), so an update, which installs a new versioned path or rewrites the file, is
# probed again. Returns nonzero when no list can be read: no `claude` on PATH, no zstat, a help
# that fails or lists nothing. A failed probe is not cached.
typeset -ga _agent_launch_claude_verbs
typeset -g _agent_launch_claude_verbs_key=""
_agent_launch_claude_subcommands() {
  setopt localoptions noksharrays no_err_return no_err_exit no_bash_rematch no_rematch_pcre
  local bin real key help line cache="$HOME/.local/share/agent-bios/claude-subcommands"
  local -a words cached
  local -A meta
  bin="$(whence -p claude)" || return 1
  [[ -n "$bin" ]] || return 1
  real="${bin:A}"
  zmodload -F zsh/stat b:zstat 2>/dev/null || return 1
  zstat -H meta -- "$real" 2>/dev/null || return 1
  key="${real}"$'\t'"${meta[mtime]}"$'\t'"${meta[size]}"
  [[ "$key" == "$_agent_launch_claude_verbs_key" ]] && return 0
  if [[ -f "$cache" && ! -L "$cache" ]]; then
    cached=("${(@f)$(<"$cache")}")
    if [[ "${cached[1]-}" == "$key" && ${#cached} -gt 1 ]]; then
      _agent_launch_claude_verbs=("${(@)cached[2,-1]}")
      _agent_launch_claude_verbs_key="$key"
      return 0
    fi
  fi
  help="$("$bin" --help </dev/null 2>/dev/null)" || return 1
  local in_commands=0
  for line in "${(@f)help}"; do
    if [[ "$line" == Commands:* ]]; then
      in_commands=1
    elif (( in_commands )); then
      if [[ "$line" =~ '^  ([a-z][a-z0-9-]*([|][a-z][a-z0-9-]*)*)( |$)' ]]; then
        words+=("${(@s:|:)match[1]}")
      elif [[ -n "$line" && "$line" != ' '* ]]; then
        break
      fi
    fi
  done
  (( ${#words} )) || return 1
  _agent_launch_claude_verbs=("${words[@]}")
  _agent_launch_claude_verbs_key="$key"
  if [[ -d "${cache:h}" && ( ! -e "$cache" || ( -f "$cache" && ! -L "$cache" ) ) ]]; then
    builtin print -rl -- "$key" "${words[@]}" >| "$cache.$$" 2>/dev/null \
      && builtin command mv -f -- "$cache.$$" "$cache" 2>/dev/null \
      || builtin command rm -f -- "$cache.$$" 2>/dev/null
  fi
  return 0
}

_agent_launch_dispatch() {
  local host="$1"
  shift
  local launcher="${AGENT_LAUNCH_BIN:-$HOME/.local/bin/agent-launch}"

  if [[ $# -gt 0 && "$1" == "--no-tui" ]]; then
    shift
    _agent_launch_direct "$host" "$@"
  elif [[ -n "${_agent_launch_private_connection:-}" && ( ! -r "$_agent_launch_private_connection" || ! -f "$launcher" || ! -x "$launcher" ) ]]; then
    _agent_launch_direct "$host" "$@"
  elif [[ $# -eq 0 && -t 0 && -t 1 && "${AGENT_LAUNCH_TUI:-1}" != "0" ]]; then
    "$launcher" "$host"
  else
    _agent_launch_direct "$host" "$@"
  fi
}

# The entrypoints are (re)defined from one place so the reassert below installs the
# same thing the initial source did. The top-level unalias stays: zsh expands aliases
# while PARSING the function below, so an alias named `claude` that exists when this
# file is sourced would turn its `claude() {` into a parse error and leave the alias in
# control. The inner unalias handles an alias that arrives later, at reassert time.
# `no_err_return`: a missing alias makes `unalias` return 1, and under ERR_RETURN that
# would end the function before either entrypoint is defined.
unalias codex 2>/dev/null || :
unalias claude 2>/dev/null || :
_agent_launch_define() {
  setopt localoptions no_err_return no_err_exit
  unalias codex 2>/dev/null
  unalias claude 2>/dev/null
  codex() { _agent_launch_dispatch codex "$@"; }
  claude() { _agent_launch_dispatch claude "$@"; }
  return 0
}
_agent_launch_define

# Reassert the entrypoints right before each command runs. "Last definer wins" is
# the shell's rule, and a terminal or tool that defines `claude` after the rc files
# (cmux does, on its first precmd — deliberately, "in case user startup replaced
# them") would otherwise win in silence: bare `claude` skips the preflight while
# `codex` keeps working. preexec runs after every precmd, whatever the registration
# order, so for a prompt-hook shadower the check is the last word at the only moment
# that matters. Two things it does not do, on purpose: it does not fight a hook that
# runs after it in preexec (that tool wins; the shadow log names it), and it cannot
# repair the command already parsed when the shadow is an alias — aliases expand at
# parse time, so an alias shadow is repaired from the next command on. The downstream
# stays `builtin command <host>`, so a tool that also owns a PATH shim (cmux) keeps its
# own injection.
#
# Ownership is byte-equality with the body captured at source time, never a marker
# string: a foreign function that quotes the marker would otherwise pass as ours.
zmodload -i zsh/parameter 2>/dev/null
typeset -gA _agent_launch_body _agent_launch_shadow_noted
_agent_launch_body[claude]="${functions[claude]}"
_agent_launch_body[codex]="${functions[codex]}"

# Evidence, not repair: one line per host per shell, into the state dir agent-bios
# already owns — what `agent-bios status`/`verify` read. Never creates the dir (no
# install, no log). The "noted" flag is set only after the append succeeded, so a
# directory that cannot be written is retried on the next command instead of being
# recorded as "no shadowing observed". Tabs and newlines are stripped from every field
# so a hostile TERM_PROGRAM or function body cannot forge a second row.
_agent_launch_note_shadow() {
  setopt localoptions extendedglob noksharrays no_err_return no_err_exit
  local host="$1" foreign="$2" state="$HOME/.local/share/agent-bios" first prog stamp
  [[ -n "${_agent_launch_shadow_noted[$host]-}" || ! -d "$state" ]] && return 0
  # Only a regular, non-symlinked file is evidence: a log pointing at /dev/null would
  # take the write, set the flag, and keep nothing.
  [[ -e "$state/shell-shadow.log" && ( -L "$state/shell-shadow.log" || ! -f "$state/shell-shadow.log" ) ]] && return 0
  first="${foreign%%$'\n'*}"
  first="${first##[[:space:]]#}"
  first="${first//[[:cntrl:]]/ }"
  prog="${TERM_PROGRAM:-unknown}"
  prog="${prog//[[:cntrl:]]/ }"
  # `builtin command`: a shell function named `date` must not write this field.
  stamp="$(builtin command date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
  stamp="${stamp//[[:cntrl:]]/ }"
  # `builtin printf`: a shell function named printf could report success and write nothing.
  if builtin printf '%s\t%s\t%s\t%s\n' "${stamp:-<unknown>}" "$host" "$prog" \
       "${first:-<undefined>}" >> "$state/shell-shadow.log" 2>/dev/null; then
    _agent_launch_shadow_noted[$host]=1
  fi
  return 0
}

_agent_launch_reassert() {
  setopt localoptions noksharrays no_err_return no_err_exit
  local host foreign entry
  local -a shadowed
  # Removing an opted-in connection takes effect in already-open shells too.
  # Only our own entrypoints are withdrawn; later user/tool definitions survive.
  if [[ -n "${_agent_launch_private_connection:-}" && ! -r "$_agent_launch_private_connection" ]]; then
    for host in claude codex; do
      if [[ "${functions[$host]-}" == "${_agent_launch_body[$host]}" ]]; then
        unfunction "$host"
      fi
    done
    add-zsh-hook -d preexec _agent_launch_reassert
    add-zsh-hook -d precmd _agent_launch_reassert
    return 0
  fi
  for host in claude codex; do
    foreign=""
    # Existence, not non-emptiness: `alias claude=''` is a shadow that erases the command
    # word. Global aliases live in $galiases, not $aliases; `unalias` removes either.
    if (( ${+aliases[$host]} )); then
      foreign="alias $host=${aliases[$host]}"
    elif (( ${+galiases[$host]} )); then
      foreign="alias -g $host=${galiases[$host]}"
    elif [[ "${functions[$host]-}" != "${_agent_launch_body[$host]}" ]]; then
      foreign="${functions[$host]-<undefined>}"
    fi
    [[ -n "$foreign" ]] && shadowed+=("${host}"$'\t'"${foreign}")
  done
  (( $#shadowed )) || return 0
  # Repair first, then record: a failure to write evidence must never leave the
  # foreign definition in place for the command about to run.
  _agent_launch_define
  for entry in "${shadowed[@]}"; do
    _agent_launch_note_shadow "${entry%%$'\t'*}" "${entry#*$'\t'}"
  done
  return 0
}
# Registered on precmd as well: a tool that redefines the names in a preexec that runs
# after ours wins for that command, but its definition is still in place when the next
# prompt is drawn — precmd is where that shadow is observed and logged, so "recorded, not
# fought" holds for the case the preexec pass cannot see.
autoload -Uz add-zsh-hook
add-zsh-hook -d preexec _agent_launch_reassert 2>/dev/null
add-zsh-hook -d precmd _agent_launch_reassert 2>/dev/null
add-zsh-hook preexec _agent_launch_reassert
add-zsh-hook precmd _agent_launch_reassert

(( _agent_launch_aliases_were )) && setopt aliases
unset _agent_launch_aliases_were
