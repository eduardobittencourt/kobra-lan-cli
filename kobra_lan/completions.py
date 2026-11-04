"""Offline completion scripts derived from the canonical argparse metadata."""
import argparse
from pathlib import Path
import shlex


def metadata(parser):
    nodes = {}

    def visit(current, path):
        node = {"options": {}, "commands": [], "files": False}
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                node["commands"] = list(action.choices)
                for name, child in action.choices.items():
                    visit(child, " ".join(filter(None, [path, name])))
            else:
                add_action(node, action)
        nodes[path] = node
    visit(parser, "")
    return nodes


def add_action(node, action):
    if action.option_strings:
        for flag in action.option_strings:
            node["options"][flag] = {
                "value": action.nargs != 0,
                "choices": [str(c) for c in action.choices or []],
                "files": action.type is Path,
            }
    elif action.choices:
        node["commands"] += [str(c) for c in action.choices]
    elif action.type is Path:
        node["files"] = True


def command_transitions(nodes):
    for path, node in nodes.items():
        for command in node["commands"]:
            dest = " ".join(filter(None, [path, command]))
            if dest in nodes:
                yield path, command, dest


def value_options(nodes):
    for path, node in nodes.items():
        for flag, option in node["options"].items():
            if option["value"]:
                yield path, flag, option


def generate(parser, shell):
    nodes = metadata(parser)
    if shell == "fish":
        return fish(nodes)
    return bourne(nodes, shell)


def bourne(nodes, shell):
    zsh = shell == "zsh"
    lines = ["# Offline kobra-lan completion; no configuration or printer queries."]
    if zsh:
        lines += ["#compdef kobra-lan"]
    lines += ["_kobra_lan() {", "  local context='' word prev cur candidates='' skip=0 i"]
    if zsh:
        lines += ['  cur="${words[CURRENT]}"; prev="${words[CURRENT-1]}"',
                  '  for ((i=2; i<CURRENT; i++)); do', '    word="${words[i]}"']
    else:
        lines += ['  COMPREPLY=()', '  cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"',
                  '  for ((i=1; i<COMP_CWORD; i++)); do', '    word="${COMP_WORDS[i]}"']
    lines += ['    if ((skip)); then skip=0; continue; fi', '    case "$context:$word" in']
    for path, command, dest in command_transitions(nodes):
        lines += [f"      {shlex.quote(path + ':' + command)}) context={shlex.quote(dest)} ;; "]
    for path, flag, _ in value_options(nodes):
        lines += [f"      {shlex.quote(path + ':' + flag)}) skip=1 ;; "]
    lines += ['    esac', '  done', '  case "$context:$prev" in']
    lines += bourne_values(nodes, zsh)
    lines += ['  esac', '  case "$context" in']
    for path, node in nodes.items():
        choices = " ".join(node["commands"] + list(node["options"]))
        lines += [f"    {shlex.quote(path)}) candidates={shlex.quote(choices)} ;; "]
    lines += ['  esac']
    if zsh:
        lines += ['  compadd -- ${=candidates}']
    else:
        lines += ['  mapfile -t COMPREPLY < <(compgen -W "$candidates" -- "$cur")']
    paths = [shlex.quote(path) for path, node in nodes.items() if node["files"]]
    lines += ['  if [[ "$cur" != -* ]]; then', '    case "$context" in',
              '      ' + '|'.join(paths) + ')' + (' _files ;;' if zsh else ' compopt -o filenames; local -a files; mapfile -t files < <(compgen -f -- "$cur"); COMPREPLY+=("${files[@]}") ;;'),
              '    esac', '  fi', '}']
    lines += ['compdef _kobra_lan kobra-lan' if zsh else 'complete -F _kobra_lan kobra-lan']
    return '\n'.join(lines) + '\n'


def bourne_values(nodes, zsh):
    lines = []
    file_return = ' _files; return ;;' if zsh else ' compopt -o filenames; mapfile -t COMPREPLY < <(compgen -f -- "$cur"); return ;;'
    choices_return = ' compadd -- ${=candidates}; return ;;' if zsh else ' mapfile -t COMPREPLY < <(compgen -W "$candidates" -- "$cur"); return ;;'
    for path, flag, option in value_options(nodes):
        key = shlex.quote(path + ':' + flag)
        if option["choices"]:
            lines += [f"    {key}) candidates={shlex.quote(' '.join(option['choices']))};" + choices_return]
        elif option["files"]:
            lines += [f"    {key})" + file_return]
        else:
            lines += [f"    {key}) return ;; "]
    return lines


def fish(nodes):
    lines = ['# Offline kobra-lan completion; no configuration or printer queries.',
             'function __kobra_lan_context', "    set -l context ''", '    set -l skip 0',
             '    set -l words (commandline -opc)', '    for word in $words[2..-1]',
             '        if test $skip = 1', '            set skip 0', '            continue', '        end',
             '        switch "$context:$word"']
    for path, command, dest in command_transitions(nodes):
        lines += [f"            case {shlex.quote(path + ':' + command)}", f"                set context {shlex.quote(dest)}"]
    for path, flag, _ in value_options(nodes):
        lines += [f"            case {shlex.quote(path + ':' + flag)}", '                set skip 1']
    lines += ['        end', '    end', '    echo x$context', 'end', 'complete -c kobra-lan -f']
    for path, node in nodes.items():
        condition = shlex.quote('test (__kobra_lan_context) = ' + shlex.quote('x' + path))
        base = 'complete -c kobra-lan -n ' + condition
        if node['commands']:
            lines += [base + ' -a ' + shlex.quote(' '.join(node['commands']))]
        if node['files']:
            lines += [base + ' -F']
        lines += fish_options(base, node)
    return '\n'.join(lines) + '\n'


def fish_options(base, node):
    lines = []
    for flag, option in node['options'].items():
        line = base + (' -l ' + flag[2:] if flag.startswith('--') else ' -s ' + flag[1:])
        if option['value']:
            line += ' -r'
        if option['choices']:
            line += ' -a ' + shlex.quote(' '.join(option['choices']))
        if option['files']:
            line += ' -F'
        lines += [line]
    return lines
