#compdef ms

_ms() {
  local -a commands
  local -a codebases
  local -a build_targets

  commands=(doctor verify update setup bridge run web build upload monitor clean list completion icons changes status help r w b core bitwig)
  codebases=(core bitwig)
  build_targets=(teensy native wasm)

  if (( CURRENT == 2 )); then
    _describe -t commands 'ms command' commands
    return
  fi

  local cmd=${words[2]}
  case $cmd in
    run|web|upload|monitor|clean|icons)
      _describe -t codebases 'codebase' codebases
      return
      ;;
    build)
      if (( CURRENT == 3 )); then
        _describe -t codebases 'codebase' codebases
        return
      fi
      if (( CURRENT == 4 )); then
        _describe -t build_targets 'target' build_targets
        return
      fi
      ;;
    completion)
      _values 'shell' bash zsh
      return
      ;;
  esac
}

_ms "$@"
