"""Regression checks for configuration, scripts and VFS invariants."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from emulator.config import ConfigError, resolve_settings
from emulator.shell import ShellCommandError, ShellEmulator
from emulator.vfs import VFSLoadError, VirtualFileSystem


class EdgeCases(unittest.TestCase):
    def test_cli_overrides_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps({'vfs_path': 'a.zip'}))
            settings = resolve_settings([
                '--config', str(config), '--vfs', 'b.zip',
            ])
            self.assertEqual(settings.vfs_path, 'b.zip')

    def test_invalid_config_type(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text('{"vfs_path": 42}')
            with self.assertRaises(ConfigError):
                resolve_settings(['--config', str(config)])

    def test_touch_requires_parent(self):
        shell = ShellEmulator()
        with self.assertRaises(ShellCommandError):
            shell.execute('touch /missing/file')
        self.assertEqual(shell.vfs.directories, {'/'})

    def test_touch_preserves_contents(self):
        shell = ShellEmulator()
        shell.vfs.files['/a'] = b'original'
        shell.execute('touch /a')
        self.assertEqual(shell.vfs.files['/a'], b'original')

    def test_cannot_remove_current_directory(self):
        shell = ShellEmulator()
        shell.vfs.directories.add('/empty')
        shell.execute('cd /empty')
        with self.assertRaises(ShellCommandError):
            shell.execute('rmdir /empty')

    def test_script_continues_after_error(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'commands.txt'
            script.write_text('unknown\ntouch /ok\nexit\ntouch /late\n')
            shell = ShellEmulator()
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertTrue(shell.run_script(str(script)))
            self.assertIn('error:', output.getvalue())
            self.assertIn('/ok', shell.vfs.files)
            self.assertNotIn('/late', shell.vfs.files)

    def test_invalid_zip_preserves_vfs(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'bad.zip'
            archive.write_text('not a zip')
            vfs = VirtualFileSystem.empty()
            vfs.files['/old'] = b'old'
            with self.assertRaises(VFSLoadError):
                vfs.load_zip(str(archive))
            self.assertEqual(vfs.files, {'/old': b'old'})

    def test_implicit_directory_parents_and_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'data.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('a/b/c/', b'')
                output.writestr('binary', bytes(range(256)))
            before = archive.read_bytes()
            vfs = VirtualFileSystem.from_zip(str(archive))
            expected = {'/', '/a', '/a/b', '/a/b/c'}
            self.assertTrue(expected <= vfs.directories)
            self.assertEqual(vfs.files['/binary'], bytes(range(256)))
            vfs.make_file('/new')
            vfs.remove_dir('/a/b/c')
            self.assertEqual(archive.read_bytes(), before)

    def test_invalid_quotes_and_arguments(self):
        shell = ShellEmulator()
        for command in ['touch "', 'exit extra', 'cal 13 2026']:
            with self.subTest(command=command):
                with self.assertRaises(ShellCommandError):
                    shell.execute(command)


if __name__ == '__main__':
    unittest.main()
