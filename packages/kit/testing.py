from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import select
import struct
import termios
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass
class PtyRun:
    result: object
    screen: str
    code: int


def run_in_pty(target: Callable[[], object], keys: Sequence[bytes], lines: int = 24, columns: int = 100) -> PtyRun:
    read_result, write_result = os.pipe()
    pid, master = pty.fork()
    if pid == 0:
        os.close(read_result)
        code = 0
        try:
            os.write(write_result, json.dumps(target()).encode())
        except SystemExit as exit:
            code = exit.code if isinstance(exit.code, int) else 1
        except BaseException:
            traceback.print_exc()
            code = 99
        os._exit(code)
    os.close(write_result)
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", lines, columns, 0, 0))
    screen = b""

    def drain(timeout: float) -> bool:
        nonlocal screen
        ready, _, _ = select.select([master], [], [], timeout)
        if not ready:
            return True
        try:
            chunk = os.read(master, 65536)
        except OSError:
            return False
        screen += chunk
        return bool(chunk)

    for key in keys:
        end = time.time() + 0.15
        while time.time() < end and drain(0.02):
            pass
        os.write(master, key)
    status: int | None = None
    end = time.time() + 5
    while time.time() < end:
        alive = drain(0.05)
        done, waited = os.waitpid(pid, os.WNOHANG)
        if done:
            status = waited
            while alive and select.select([master], [], [], 0.05)[0] and drain(0):
                pass
            break
        if not alive:
            time.sleep(0.01)
    if status is None:
        os.kill(pid, 9)
        _, status = os.waitpid(pid, 0)
    data = b""
    while chunk := os.read(read_result, 65536):
        data += chunk
    os.close(read_result)
    os.close(master)
    code = os.waitstatus_to_exitcode(status)
    text = ANSI.sub("", screen.decode(errors="replace")).replace("\r", "")
    return PtyRun(json.loads(data) if data else None, text, code)
