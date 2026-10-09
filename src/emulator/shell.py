from __future__ import annotations

import calendar
import getpass
import platform
import shlex
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from .vfs import VirtualFileSystem, VFSError, VFSLoadError


class ShellCommandError(Exception):
    pass


@dataclass
class ShellResult:
    should_exit: bool = False


class ShellEmulator:
    def __init__(self, vfs: VirtualFileSystem | None = None):
        self.vfs = vfs if vfs is not None else VirtualFileSystem.empty()
        self.cwd = "/"
        self.started_at = time.monotonic()
        self.username = getpass.getuser() or "user"
        self.hostname = socket.gethostname() or "host"

    def prompt(self) -> str:
        display = "~" if self.cwd == "/" else self.cwd
        return f"{self.username}@{self.hostname}:{display}$ "

    def parse(self, line: str) -> list[str]:
        try:
            return shlex.split(line, posix=True)
        except ValueError as exc:
            raise ShellCommandError(
                f"ошибка разбора аргументов: {exc}"
            ) from exc

    def execute(self, line: str) -> ShellResult:
        tokens = self.parse(line)
        if not tokens:
            return ShellResult()

        command, *args = tokens
        handlers = {
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "uname": self.cmd_uname,
            "cal": self.cmd_cal,
            "uptime": self.cmd_uptime,
            "rmdir": self.cmd_rmdir,
            "touch": self.cmd_touch,
            "vfs-load": self.cmd_vfs_load,
            "exit": self.cmd_exit,
        }

        handler = handlers.get(command)
        if handler is None:
            raise ShellCommandError(f"{command}: неизвестная команда")

        try:
            return handler(args)
        except VFSError as exc:
            raise ShellCommandError(str(exc)) from exc

    @staticmethod
    def _require_arg_count(
        command: str, args: list[str], minimum: int,
        maximum: int | None = None,
    ):
        if len(args) < minimum or (maximum is not None and len(args) > maximum):
            if minimum == maximum:
                raise ShellCommandError(
                    f"{command}: ожидается аргументов: {minimum}"
                )
            raise ShellCommandError(
                f"{command}: неверное количество аргументов"
            )

    def cmd_ls(self, args: list[str]) -> ShellResult:
        self._require_arg_count("ls", args, 0, 1)
        target = self.vfs.resolve(self.cwd, args[0] if args else self.cwd)
        entries = self.vfs.list_dir(target)
        if entries:
            print("  ".join(entries))
        return ShellResult()

    def cmd_cd(self, args: list[str]) -> ShellResult:
        self._require_arg_count("cd", args, 0, 1)
        target = self.vfs.resolve(self.cwd, args[0] if args else "/")
        if not self.vfs.is_dir(target):
            raise ShellCommandError(
                f"cd: нет такого каталога: {args[0] if args else target}"
            )
        self.cwd = target
        return ShellResult()

    def cmd_uname(self, args: list[str]) -> ShellResult:
        self._require_arg_count("uname", args, 0, 1)
        info = platform.uname()
        if not args:
            print(info.system or "EmuOS")
        elif args[0] == "-a":
            print(" ".join(str(x) for x in info))
        else:
            raise ShellCommandError("uname: поддерживается только опция -a")
        return ShellResult()

    def cmd_cal(self, args: list[str]) -> ShellResult:
        if len(args) == 0:
            now = time.localtime()
            print(calendar.month(now.tm_year, now.tm_mon), end="")
        elif len(args) == 1:
            try:
                year = int(args[0])
            except ValueError as exc:
                raise ShellCommandError(
                    "cal: год должен быть целым числом"
                ) from exc
            print(calendar.calendar(year), end="")
        elif len(args) == 2:
            try:
                month = int(args[0])
                year = int(args[1])
            except ValueError as exc:
                raise ShellCommandError(
                    "cal: месяц и год должны быть целыми числами"
                ) from exc
            if month < 1 or month > 12:
                raise ShellCommandError("cal: месяц должен быть от 1 до 12")
            print(calendar.month(year, month), end="")
        else:
            raise ShellCommandError(
                "cal: использование: cal [год] | cal [месяц год]"
            )
        return ShellResult()

    def cmd_uptime(self, args: list[str]) -> ShellResult:
        self._require_arg_count("uptime", args, 0, 0)
        seconds = int(time.monotonic() - self.started_at)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        prefix = f"{days} day(s), " if days else ""
        print(f"up {prefix}{hours:02d}:{minutes:02d}:{secs:02d}")
        return ShellResult()

    def cmd_rmdir(self, args: list[str]) -> ShellResult:
        self._require_arg_count("rmdir", args, 1, 1)
        target = self.vfs.resolve(self.cwd, args[0])
        if self.cwd == target or self.cwd.startswith(target.rstrip("/") + "/"):
            raise ShellCommandError("rmdir: каталог используется оболочкой")
        self.vfs.remove_dir(target)
        return ShellResult()

    def cmd_touch(self, args: list[str]) -> ShellResult:
        self._require_arg_count("touch", args, 1, 1)
        target = self.vfs.resolve(self.cwd, args[0])
        self.vfs.make_file(target)
        return ShellResult()

    def cmd_vfs_load(self, args: list[str]) -> ShellResult:
        self._require_arg_count("vfs-load", args, 1, 1)
        try:
            self.vfs.load_zip(args[0])
        except VFSLoadError as exc:
            raise ShellCommandError(f"vfs-load: {exc}") from exc
        self.cwd = "/"
        print(f"VFS загружена: {args[0]}")
        return ShellResult()

    def cmd_exit(self, args: list[str]) -> ShellResult:
        self._require_arg_count("exit", args, 0, 0)
        return ShellResult(should_exit=True)

    def run_script(self, script_path: str) -> bool:
        try:
            lines = Path(script_path).read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise ShellCommandError(
                f"стартовый скрипт не найден: {script_path}"
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise ShellCommandError(
                f"ошибка чтения стартового скрипта: {exc}"
            ) from exc

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            print(self.prompt() + line)
            try:
                result = self.execute(line)
            except ShellCommandError as exc:
                print(f"error: {exc}")
                continue

            if result.should_exit:
                return True
        return False

    def repl(self) -> None:
        while True:
            try:
                line = input(self.prompt())
            except (EOFError, KeyboardInterrupt):
                print()
                break

            try:
                result = self.execute(line)
            except ShellCommandError as exc:
                print(f"error: {exc}")
                continue

            if result.should_exit:
                break
