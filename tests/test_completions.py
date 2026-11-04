"""Completion is static metadata, never a dynamic device inventory."""
import contextlib
import io
import shutil
import subprocess
import unittest
from unittest.mock import patch

from kobra_lan.cli import build_parser, main
from kobra_lan.completions import generate, metadata


class CompletionTests(unittest.TestCase):
    def test_offline_generation_covers_parser_metadata(self):
        parser = build_parser()
        nodes = metadata(parser)
        for shell in ('bash', 'zsh', 'fish'):
            out = io.StringIO()
            with patch('kobra_lan.cli.Registry') as registry, \
                    patch('socket.create_connection', side_effect=AssertionError('network forbidden')), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(main(['--json', 'completion', shell]), 0)
            registry.assert_not_called()
            script = out.getvalue()
            for node in nodes.values():
                for name in node['commands']:
                    self.assertIn(name, script)
                for flag, option in node['options'].items():
                    self.assertIn(flag.lstrip('-') if shell == 'fish' else flag, script)
                    for choice in option['choices']:
                        self.assertIn(choice, script)
            self.assertNotIn('schema_version', script)
            self.assertNotIn('$(kobra-lan', script)
            self.assertNotIn('(kobra-lan ', script)

    def test_bash_sources_and_completes_root_nested_choices_and_files(self):
        script = generate(build_parser(), 'bash')
        script += '''
COMP_WORDS=(kobra-lan --json --printer bench files ''); COMP_CWORD=5
_kobra_lan; printf '%s\\n' "${COMPREPLY[@]}"
COMP_WORDS=(kobra-lan print plan test.gcode --auto-leveling o); COMP_CWORD=5
_kobra_lan; printf '%s\\n' "${COMPREPLY[@]}"
COMP_WORDS=(kobra-lan --j); COMP_CWORD=1
_kobra_lan; printf '%s\\n' "${COMPREPLY[@]}"
COMP_WORDS=(kobra-lan gcode inspect pypro); COMP_CWORD=3
_kobra_lan; printf '%s\\n' "${COMPREPLY[@]}"
'''
        process = subprocess.run(['bash', '--noprofile', '--norc'], input=script, text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, '')
        for expected in ('list', 'info', 'upload', 'on', 'off', '--json', 'pyproject.toml'):
            self.assertIn(expected, process.stdout.splitlines())

    def test_fish_sources_and_completes_offline(self):
        if not shutil.which('fish'):
            self.skipTest('fish unavailable: native smoke test not performed')
        script = generate(build_parser(), 'fish')
        script += '''
complete -C 'kobra-lan --json --printer bench files '
complete -C 'kobra-lan print plan a.gcode --auto-leveling o'
complete -C 'kobra-lan --j'
'''
        process = subprocess.run(['fish', '--no-config'], input=script, text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, '')
        for expected in ('list', 'info', 'upload', 'on', 'off', '--json'):
            self.assertIn(expected, [line.split('\t')[0] for line in process.stdout.splitlines()])

    def test_zsh_sources_and_calls_completion_without_device_commands(self):
        if not shutil.which('zsh'):
            self.skipTest('zsh unavailable: native smoke test not performed')
        script = 'autoload -Uz compinit; compinit -D\n' + generate(build_parser(), 'zsh')
        # Capture candidates while calling the actual generated function.
        script += '''
compadd() { print -l -- "$@"; }
_files() { print local-files; }
words=(kobra-lan --json files ''); CURRENT=4
_kobra_lan
words=(kobra-lan print plan a.gcode --auto-leveling o); CURRENT=6
_kobra_lan
words=(kobra-lan --j); CURRENT=2
_kobra_lan
'''
        process = subprocess.run(['zsh', '-f'], input=script, text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, '')
        for expected in ('list', 'info', 'upload', 'on', 'off', '--json'):
            self.assertIn(expected, process.stdout.splitlines())
