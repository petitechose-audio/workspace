#compdef ms

_ms() {
  local -a commands
  local -a repos_subcommands
  local -a tools_subcommands

  commands=(check setup repos tools)
  repos_subcommands=(sync)
  tools_subcommands=(sync)

  if (( CURRENT == 2 )); then
    _describe -t commands 'ms command' commands
    return
  fi

  local cmd=${words[2]}
  case $cmd in
    repos)
      _describe -t repos_subcommands 'repos command' repos_subcommands
      return
      ;;
    tools)
      _describe -t tools_subcommands 'tools command' tools_subcommands
      return
      ;;
  esac
}

_ms "$@"
