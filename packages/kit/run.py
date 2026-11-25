from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from collections.abc import Sequence

from kit import ui


def _has_tty() -> bool:
    try:
        os.close(os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY))
        return True
    except OSError:
        return False


def _args(args: Sequence[str], sudo: bool) -> list[str]:
    if not sudo:
        return list(args)
    return ["sudo"] + ([] if _has_tty() else ["-n"]) + list(args)


def _feed(process: subprocess.Popen[str], text: str) -> None:
    assert process.stdin is not None
    try:
        process.stdin.write(text)
        process.stdin.close()
    except BrokenPipeError:
        pass


def cmd(
    args: Sequence[str],
    sudo: bool = False,
    input: str | None = None,
    quiet: bool = False,
    timeout: float | None = None,
) -> None:
    full = _args(args, sudo)
    try:
        process = subprocess.Popen(
            full,
            stdin=subprocess.PIPE if input is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        ui.fail(f"comando não encontrado: {full[0]}")
    if input is not None:
        threading.Thread(target=_feed, args=(process, input), daemon=True).start()
    expired = threading.Event()

    def expire() -> None:
        expired.set()
        process.kill()

    timer = threading.Timer(timeout, expire) if timeout else None
    if timer:
        timer.start()
    kept: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        if quiet:
            kept.append(line)
        else:
            ui.prefixed(line.rstrip("\n"))
    code = process.wait()
    if timer:
        timer.cancel()
    if expired.is_set():
        ui.fail(f"o comando passou de {timeout:g} s: {shlex.join(full)}")
    if code:
        if kept:
            ui.prefixed("".join(kept).rstrip("\n"), sys.stderr)
        ui.fail(f"comando falhou (código {code}): {shlex.join(full)}")


def capture(args: Sequence[str], sudo: bool = False, input: str | None = None, timeout: float | None = None) -> str:
    full = _args(args, sudo)
    try:
        done = subprocess.run(full, input=input, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        ui.fail(f"comando não encontrado: {full[0]}")
    except subprocess.TimeoutExpired:
        ui.fail(f"o comando passou de {timeout:g} s: {shlex.join(full)}")
    if done.returncode:
        if done.stderr.strip():
            ui.prefixed(done.stderr.rstrip("\n"), sys.stderr)
        ui.fail(f"comando falhou (código {done.returncode}): {shlex.join(full)}")
    return done.stdout.rstrip("\n")


def output(
    args: Sequence[str], timeout: float | None = None, env: dict[str, str] | None = None, input: str | bytes | None = None
) -> tuple[int, str]:
    code, data = output_raw(args, timeout, env, input)
    return code, data.decode(errors="replace")


def output_raw(
    args: Sequence[str], timeout: float | None = None, env: dict[str, str] | None = None, input: str | bytes | None = None
) -> tuple[int, bytes]:
    data = input.encode() if isinstance(input, str) else input
    try:
        done = subprocess.run(
            list(args), input=data, stdin=None if data is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout, env={**os.environ, **(env or {})},
        )
    except FileNotFoundError:
        return 127, f"comando não encontrado: {args[0]}".encode()
    except subprocess.TimeoutExpired as problem:
        partial = problem.output if isinstance(problem.output, bytes) else (problem.output or "").encode()
        return 124, partial + f"\no comando passou de {timeout:g} s".encode()
    return done.returncode, done.stdout


def succeeds(args: Sequence[str], sudo: bool = False, timeout: float | None = None) -> bool:
    try:
        done = subprocess.run(
            _args(args, sudo), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def sudo_prepare(reason: str) -> None:
    if succeeds(["sudo", "-n", "true"]):
        return
    if not _has_tty():
        ui.fail(f"precisa de permissão de administrador ({reason}): rode num terminal")
    ui.info(f"permissão de administrador necessária: {reason}")
    if subprocess.run(["sudo", "-v"]).returncode:
        ui.fail("a senha do sudo não foi aceita")
