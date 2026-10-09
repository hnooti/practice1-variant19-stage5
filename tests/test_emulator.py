import tempfile
import unittest
import zipfile
from pathlib import Path

from emulator.shell import ShellCommandError, ShellEmulator
from emulator.vfs import VirtualFileSystem


class EmulatorTests(unittest.TestCase):
    def setUp(self):
        self.vfs = VirtualFileSystem.empty()
        self.vfs.directories.update({"/home", "/home/user", "/empty"})
        self.vfs.files["/home/user/a.txt"] = b"hello"
        self.shell = ShellEmulator(self.vfs)

    def test_quoted_argument_parser(self):
        self.shell.execute('touch "/home/user/file with spaces.txt"')
        self.assertIn("/home/user/file with spaces.txt", self.vfs.files)

    def test_cd_and_ls_state(self):
        self.shell.execute("cd /home/user")
        self.assertEqual(self.shell.cwd, "/home/user")

    def test_rmdir_nonempty_fails(self):
        with self.assertRaises(ShellCommandError):
            self.shell.execute("rmdir /home")

    def test_rmdir_empty(self):
        self.shell.execute("rmdir /empty")
        self.assertNotIn("/empty", self.vfs.directories)

    def test_unknown_command(self):
        with self.assertRaises(ShellCommandError):
            self.shell.execute("definitely-not-a-command")

    def test_vfs_zip_load(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "v.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("x/y/z.txt", "ok")
            vfs = VirtualFileSystem.from_zip(str(p))
            self.assertEqual(vfs.files["/x/y/z.txt"], b"ok")
            self.assertIn("/x/y", vfs.directories)


if __name__ == "__main__":
    unittest.main()
