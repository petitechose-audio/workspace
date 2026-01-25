_ms_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"

    local commands="check setup repos tools"
    local repos_subcommands="sync"
    local tools_subcommands="sync"

    case "$prev" in
        ms)
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
            ;;
        repos)
            COMPREPLY=( $(compgen -W "$repos_subcommands" -- "$cur") )
            ;;
        tools)
            COMPREPLY=( $(compgen -W "$tools_subcommands" -- "$cur") )
            ;;
        *)
            ;;
    esac
}

complete -F _ms_completions ms
