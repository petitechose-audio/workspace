_ms_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    local commands="doctor verify update setup bridge run web build upload monitor clean list completion icons changes status help r w b core bitwig"
    local codebases="core bitwig"
    local build_targets="teensy native wasm"

    case "$prev" in
        ms)
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
            ;;
        run|web|build|upload|monitor|clean|icons)
            COMPREPLY=( $(compgen -W "$codebases" -- "$cur") )
            ;;
        build)
            COMPREPLY=( $(compgen -W "$codebases" -- "$cur") )
            ;;
        *)
            # Special case: second arg of `ms build <codebase> <target>`
            if [[ ${COMP_WORDS[1]} == "build" && ${COMP_CWORD} -eq 3 ]]; then
                COMPREPLY=( $(compgen -W "$build_targets" -- "$cur") )
            fi
            ;;
    esac
}

complete -F _ms_completions ms
