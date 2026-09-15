"""Small OS boundary shared by the native entrypoint, installer and launcher."""
from __future__ import annotations
import errno
import os
from pathlib import Path
import subprocess
import sys
import time

WINDOWS = os.name == 'nt'

if not WINDOWS:
    import fcntl as file_locks
else:
    import msvcrt

    class file_locks:
        LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

        @staticmethod
        def flock(file, operation):
            fd = file if isinstance(file, int) else file.fileno()
            position = os.lseek(fd, 0, os.SEEK_CUR)
            try:
                while True:
                    os.lseek(fd, 0, os.SEEK_SET)
                    try:
                        msvcrt.locking(fd, msvcrt.LK_UNLCK if operation & 8 else msvcrt.LK_NBLCK, 1)
                        return
                    except OSError as exc:
                        if operation & 8 or exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        if operation & 4:
                            raise BlockingIOError(exc.errno, str(exc)) from exc
                        time.sleep(.05)
            finally:
                os.lseek(fd, position, os.SEEK_SET)


def cli_argv(root: Path, *args: str) -> list[str]:
    if WINDOWS:
        return python_argv(root / 'compose/native_cli.py', *args)
    return ['/bin/bash', str(root / 'install.sh'), *args]


def runtime_environment(environ=None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    entry, deps = env.get('AGENT_BIOS_PYTHON_ENTRY'), env.get('AGENT_BIOS_PYTHON_DEPS')
    if bool(entry) != bool(deps):
        raise RuntimeError('application Python entry and dependencies must be bound together')
    if not entry:
        return {}
    if not Path(entry).is_absolute() or not Path(entry).is_file() or not Path(deps).is_absolute() or not Path(deps).is_dir():
        raise RuntimeError('application Python binding is unavailable; repair the script installation')
    executable = env.get('AGENT_BIOS_PYTHON_EXECUTABLE', sys.executable)
    if not Path(executable).is_absolute() or not Path(executable).is_file():
        raise RuntimeError('bound Python interpreter is unavailable')
    return {'AGENT_BIOS_PYTHON_ENTRY': str(entry), 'AGENT_BIOS_PYTHON_DEPS': str(deps), 'AGENT_BIOS_PYTHON_EXECUTABLE': str(executable)}


def python_argv(script: Path, *args: str, interpreter=None, environ=None) -> list[str]:
    binding = runtime_environment(environ)
    executable = str(interpreter or binding.get("AGENT_BIOS_PYTHON_EXECUTABLE") or sys.executable)
    if binding:
        return [executable, '-I', '-X', 'utf8', binding['AGENT_BIOS_PYTHON_ENTRY'],
                '--dependencies', binding['AGENT_BIOS_PYTHON_DEPS'], '--script', str(script), *args]
    return [executable, str(script), *args]


def sync_directory(path: Path) -> None:
    # Windows CRT cannot open directory descriptors. File bytes are flushed by
    # the writer; replace/restart tests establish process recovery, not power-loss durability.
    if WINDOWS:
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def create_junction(link: Path, target: Path) -> None:
    """Create a directory junction without shell expansion or symlink privileges."""
    if not WINDOWS:
        raise OSError('junction creation is Windows-only')
    import ctypes
    from ctypes import wintypes
    import struct
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    target = target.resolve(strict=True)
    substitute = ('\\??\\' + str(target)).encode('utf-16-le')
    display = str(target).encode('utf-16-le')
    names = substitute + b'\0\0' + display + b'\0\0'
    payload = struct.pack('<HHHH', 0, len(substitute), len(substitute)+2, len(display)) + names
    data = struct.pack('<IHH', 0xA0000003, len(payload), 0) + payload
    link.mkdir()
    handle = kernel.CreateFileW(str(link), 0x40000000, 0, None, 3, 0x02200000, None)
    try:
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        returned = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(data)
        if not kernel.DeviceIoControl(handle, 0x000900A4, buffer, len(data), None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        if handle != ctypes.c_void_p(-1).value:
            kernel.CloseHandle(handle)
            handle = ctypes.c_void_p(-1).value
        link.rmdir()
        raise
    finally:
        if handle != ctypes.c_void_p(-1).value:
            kernel.CloseHandle(handle)
