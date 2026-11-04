"""Completion is static metadata, never a dynamic device inventory."""
import contextlib
import io
import os
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from kobra_lan.cli import build_parser, main
from kobra_lan.completions import generate, metadata


def read_terminal(master):
    output = b''
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not select.select([master], [], [], max(0, deadline - time.monotonic()))[0]:
            break
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    return output


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
compopt() { printf 'filename-mode:%s\\n' "$*"; }
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
        self.assertIn('filename-mode:-o filenames', process.stdout.splitlines())

    def test_bash_readline_inserts_spaced_paths_as_single_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            root = Path(directory)
            script = root / 'completion.bash'
            script.write_text(generate(build_parser(), 'bash'))
            (root / 'model with spaces.gcode').write_text('synthetic')
            (root / 'config with spaces.json').write_text('{}')
            master, slave = pty.openpty()
            process = subprocess.Popen(['bash', '--noprofile', '--norc', '-i'], cwd=root,
                                       stdin=slave, stdout=slave, stderr=slave,
                                       env={**os.environ, 'TERM': 'dumb', 'PS1': ''})
            os.close(slave)
            try:
                commands = ("source completion.bash\n"
                            "kobra-lan() { printf 'OPERAND:<%s>\\n' \"$@\"; }\n"
                            "kobra-lan gcode inspect model\t\n"
                            "kobra-lan --config config\t\nexit\n")
                os.write(master, commands.encode())
                output = read_terminal(master)
                self.assertEqual(process.wait(timeout=1), 0, output)
                self.assertIn(b'OPERAND:<model with spaces.gcode>\r\n', output)
                self.assertIn(b'OPERAND:<config with spaces.json>\r\n', output)
            finally:
                os.close(master)
                if process.poll() is None:
                    process.kill()
                    process.wait()

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
