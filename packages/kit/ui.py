from __future__ import annotations

import os
import select
import shutil
import sys
import termios
import textwrap
import tty
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import NoReturn, TextIO

from kit import logo

Rgb = tuple[int, int, int]
Validator = Callable[[str], str]

LAVENDER: Rgb = (0xF1, 0xEB, 0xFA)
VIOLET: Rgb = (0x8A, 0x4D, 0xFF)
ACCENT: Rgb = (0xF0, 0x47, 0x9B)
SOFT: Rgb = (0xC4, 0xA6, 0xFF)
GREEN: Rgb = (0x4A, 0xDE, 0x80)
AMBER: Rgb = (0xFB, 0xBF, 0x24)
RED: Rgb = (0xF8, 0x71, 0x71)
GRAY: Rgb = (0x8B, 0x84, 0x99)

_BASIC: dict[Rgb, int] = {
    LAVENDER: 97, VIOLET: 35, ACCENT: 95, SOFT: 95, GREEN: 32, AMBER: 33, RED: 31, GRAY: 90,
}

_app = "astroverso"


def _depth() -> int:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return 0
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return 24
    if "256" in os.environ.get("TERM", ""):
        return 8
    return 4


def _cube(value: int) -> int:
    return 0 if value < 48 else 1 if value < 115 else (value - 35) // 40


def _color(rgb: Rgb, depth: int, background: bool = False) -> str:
    r, g, b = rgb
    if depth == 24:
        return f"{48 if background else 38};2;{r};{g};{b}"
    if depth == 8:
        return f"{48 if background else 38};5;{16 + 36 * _cube(r) + 6 * _cube(g) + _cube(b)}"
    code = _BASIC.get(rgb) or (95 if r > b else 35)
    return str(code + 10 if background else code)


def _paint(text: str, depth: int, rgb: Rgb | None = None, bold: bool = False, dim: bool = False) -> str:
    if not depth:
        return text
    codes = (["1"] if bold else []) + (["2"] if dim else []) + ([_color(rgb, depth)] if rgb else [])
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def _stream_depth(stream: TextIO) -> int:
    try:
        return _depth() if stream.isatty() else 0
    except (AttributeError, ValueError):
        return 0


def _tag(depth: int) -> str:
    return _paint(f"[{_app}]", depth, VIOLET, bold=True)


def _sudo_prompt() -> None:
    depth = _depth()
    os.environ["SUDO_PROMPT"] = f"{_tag(depth)}     {_paint('?', depth, ACCENT, bold=True)} senha do sudo: "


def set_app(name: str) -> None:
    global _app
    _app = name
    _sudo_prompt()


_sudo_prompt()


def _log(stream: TextIO, icon: str, plain: str, rgb: Rgb, text: str) -> None:
    depth = _stream_depth(stream)
    mark = _paint(icon, depth, rgb, bold=True) if depth else plain
    stream.write(f"{_tag(depth)}     {mark} {text}\n")
    stream.flush()


def step(text: str) -> None:
    depth = _stream_depth(sys.stdout)
    if depth:
        sys.stdout.write(f"\n{_tag(depth)} {_paint('==>', depth, ACCENT, bold=True)} {_paint(text, depth, bold=True)}\n")
    else:
        sys.stdout.write(f"{_tag(0)} ==> {text}\n")
    sys.stdout.flush()


def info(text: str) -> None:
    sys.stdout.write(f"{_tag(_stream_depth(sys.stdout))}     {text}\n")
    sys.stdout.flush()


def ok(text: str) -> None:
    _log(sys.stdout, "✔", "ok:", GREEN, text)


def warn(text: str) -> None:
    _log(sys.stdout, "!", "aviso:", AMBER, text)


def error(text: str) -> None:
    _log(sys.stderr, "✘", "erro:", RED, text)


def fail(text: str) -> NoReturn:
    error(text)
    raise SystemExit(1)


def prefixed(text: str, stream: TextIO | None = None) -> None:
    out = stream or sys.stdout
    depth = _stream_depth(out)
    for line in text.splitlines():
        out.write(f"{_tag(depth)}       {_paint(line, depth, GRAY)}\n")
    out.flush()


def _width(stream: TextIO) -> int:
    try:
        return os.get_terminal_size(stream.fileno()).columns or 100
    except (AttributeError, OSError, ValueError):
        return shutil.get_terminal_size((100, 24)).columns


def note(text: str) -> None:
    depth = _stream_depth(sys.stdout)
    width = max(30, min(_width(sys.stdout), 110) - len(_app) - 9)
    for paragraph in text.split("\n"):
        for line in textwrap.wrap(paragraph, width) or [""]:
            styled = f"\033[3m{line}\033[0m" if depth else line
            sys.stdout.write(f"{_tag(depth)}       {styled}\n")
    sys.stdout.flush()


def link(label: str, url: str) -> None:
    depth = _stream_depth(sys.stdout)
    arrow = _paint("→", depth, ACCENT, bold=True)
    target = f"\033[4m{_paint(url, depth, SOFT)}\033[0m" if depth else url
    sys.stdout.write(f"{_tag(depth)}     {arrow} {label}: {target}\n")
    sys.stdout.flush()


def section(title: str) -> None:
    depth = _stream_depth(sys.stdout)
    sys.stdout.write(f"{chr(10) if depth else ''}{_tag(depth)}     {_paint(title, depth, SOFT, bold=True)}\n")
    sys.stdout.flush()


@dataclass(frozen=True)
class Cell:
    text: str
    rgb: Rgb | None = None
    icon: str = ""

    @property
    def plain(self) -> str:
        return f"{self.icon} {self.text}" if self.icon else self.text


def good(text: str) -> Cell:
    return Cell(text, GREEN, "✔")


def pending(text: str) -> Cell:
    return Cell(text, AMBER, "!")


def off(text: str) -> Cell:
    return Cell(text, GRAY, "○")


def bad(text: str) -> Cell:
    return Cell(text, RED, "✘")


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)] + "…"


def table(rows: Sequence[Sequence[str | Cell]], columns: Sequence[str] | None = None) -> None:
    depth = _stream_depth(sys.stdout)
    header = [Cell(column) for column in columns or []]
    body = [[cell if isinstance(cell, Cell) else Cell(str(cell)) for cell in row] for row in rows]
    count = max([len(header)] + [len(row) for row in body])
    if not count:
        return
    lines = ([header] if header else []) + body
    lines = [line + [Cell("")] * (count - len(line)) for line in lines]
    widths = [max(len(line[i].plain) for line in lines) for i in range(count)]
    room = _width(sys.stdout) - len(_app) - 7 - (3 * count + 1 if depth else 2 * (count - 1))
    while sum(widths) > room and max(widths) > 4:
        widths[widths.index(max(widths))] -= 1
    tag = _tag(depth)
    out: list[str] = []
    if not depth:
        for line in lines:
            out.append("  ".join(_fit(cell.plain, widths[i]).ljust(widths[i]) for i, cell in enumerate(line)).rstrip())
        sys.stdout.write("".join(f"{tag}     {text}\n" for text in out))
        sys.stdout.flush()
        return

    def border(left: str, middle: str, right: str) -> str:
        return _paint(left + middle.join("─" * (width + 2) for width in widths) + right, depth, GRAY)

    def row(line: list[Cell], bold: bool = False) -> str:
        bar = _paint("│", depth, GRAY)
        cells = []
        for i, cell in enumerate(line):
            text = _fit(cell.plain, widths[i])
            cells.append(_paint(text, depth, cell.rgb, bold=bold) + " " * (widths[i] - len(text)))
        return f"{bar} " + f" {bar} ".join(cells) + f" {bar}"

    out.append(border("╭", "┬", "╮"))
    if header:
        out.append(row(lines[0], bold=True))
        out.append(border("├", "┼", "┤"))
    out.extend(row(line) for line in lines[1 if header else 0:])
    out.append(border("╰", "┴", "╯"))
    sys.stdout.write("".join(f"{tag}     {text}\n" for text in out))
    sys.stdout.flush()


def _fg(rgb: Rgb, depth: int) -> str:
    return "39" if rgb == LAVENDER else _color(rgb, depth)


def _cell(top: Rgb | None, bottom: Rgb | None, depth: int) -> str:
    if top is None and bottom is None:
        return " "
    if top == bottom and top is not None:
        return f"\033[{_fg(top, depth)}m█\033[0m"
    if bottom is None and top is not None:
        return f"\033[{_fg(top, depth)}m▀\033[0m"
    if top is None and bottom is not None:
        return f"\033[{_fg(bottom, depth)}m▄\033[0m"
    assert top is not None and bottom is not None
    return f"\033[{_color(top, depth)};{_color(bottom, depth, True)}m▀\033[0m"


def _mix(a: Rgb, b: Rgb, t: float) -> Rgb:
    return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t))


def _pixels(rows: Sequence[str]) -> list[list[Rgb | None]]:
    width = max(len(row) for row in rows)
    grid: list[list[Rgb | None]] = []
    for row in rows:
        line: list[Rgb | None] = []
        for x, char in enumerate(row.ljust(width, ".")):
            if char == "#":
                line.append(LAVENDER)
            elif char == "o":
                line.append(_mix(VIOLET, ACCENT, x / (width - 1)))
            else:
                line.append(None)
        grid.append(line)
    if len(grid) % 2:
        grid.append([None] * width)
    return grid


def _render(rows: Sequence[str], depth: int) -> list[str]:
    grid = _pixels(rows)
    return ["".join(_cell(top, bottom, depth) for top, bottom in zip(grid[y], grid[y + 1])) for y in range(0, len(grid), 2)]


def _word(text: str) -> list[str]:
    return ["..".join(logo.FONT[char][y] for char in text) for y in range(6)]


def banner() -> None:
    depth = _stream_depth(sys.stdout)
    if not depth:
        return
    columns = os.get_terminal_size(sys.stdout.fileno()).columns
    word = _word("ASTROVERSO")
    symbol_width, word_width = len(logo.SYMBOL[0]), len(word[0])
    if columns >= symbol_width + word_width + 6:
        symbol, text = _render(logo.SYMBOL, depth), _render(word, depth)
        top = (len(symbol) - len(text)) // 2 + 2
        lines = [
            f"  {line}   {text[i - top] if 0 <= i - top < len(text) else ''}".rstrip()
            for i, line in enumerate(symbol)
        ]
    elif columns >= word_width + 4:
        pad = " " * (2 + (word_width - symbol_width) // 2)
        lines = [f"{pad}{line}".rstrip() for line in _render(logo.SYMBOL, depth)]
        lines += [""] + [f"  {line}" for line in _render(word, depth)]
    else:
        lines = [f"  {_paint('ASTROVERSO', depth, bold=True)}"]
    sys.stdout.write("\n" + "\n".join(lines) + "\n\n")
    sys.stdout.flush()


class _Tty:
    def __init__(self, label: str) -> None:
        try:
            self.fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        except OSError:
            fail(f"sem terminal para perguntar: {label}")
        self.depth = _depth()
        self.pending = b""

    def close(self) -> None:
        os.close(self.fd)

    def write(self, text: str) -> None:
        os.write(self.fd, text.encode())

    def size(self) -> tuple[int, int]:
        try:
            columns, lines = os.get_terminal_size(self.fd)
            return columns or 80, lines or 24
        except OSError:
            return 80, 24

    def paint(self, text: str, rgb: Rgb | None = None, bold: bool = False, dim: bool = False) -> str:
        return _paint(text, self.depth, rgb, bold, dim)

    def question(self, text: str) -> str:
        return f"{_tag(self.depth)}     {self.paint('?', ACCENT, bold=True)} {self.paint(text, bold=True)}"

    def answered(self, label: str, answer: str, rgb: Rgb = SOFT) -> str:
        return f"{self.question(label)} {self.paint(answer, rgb)}"

    def warn(self, text: str) -> None:
        mark = self.paint("!", AMBER, bold=True) if self.depth else "aviso:"
        self.write(f"{_tag(self.depth)}       {mark} {self.paint(text, AMBER)}\n")

    def readline(self, secret: bool = False) -> str:
        old = termios.tcgetattr(self.fd)
        if secret:
            new = termios.tcgetattr(self.fd)
            new[3] &= ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, new)
        data = b""
        try:
            while not data.endswith(b"\n"):
                chunk = os.read(self.fd, 4096)
                if not chunk:
                    fail("entrada encerrada")
                data += chunk
        finally:
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, old)
        if secret:
            self.write("\n")
        return data.decode(errors="replace").rstrip("\r\n")

    @contextmanager
    def raw(self) -> Iterator[None]:
        old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self.write("\033[?25l\033[?7l")
        try:
            yield
        finally:
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, old)
            self.write("\033[?7h\033[?25h")

    def key(self) -> str:
        if not self.pending:
            self.pending = os.read(self.fd, 64)
        if self.pending == b"\x1b" and select.select([self.fd], [], [], 0.05)[0]:
            self.pending += os.read(self.fd, 64)
        if self.pending[:2] in (b"\x1b[", b"\x1bO") and not any(self.pending.startswith(k) for k, _ in _SEQUENCES):
            end = next((i for i in range(2, len(self.pending)) if 0x40 <= self.pending[i] <= 0x7E), len(self.pending) - 1)
            self.pending = self.pending[end + 1:]
            return "other"
        for sequence, name in _SEQUENCES + _KEYS:
            if self.pending.startswith(sequence):
                self.pending = self.pending[len(sequence):]
                return name
        char, self.pending = self.pending[:1], self.pending[1:]
        return char.decode(errors="replace")


_SEQUENCES: tuple[tuple[bytes, str], ...] = (
    (b"\x1b[A", "up"), (b"\x1bOA", "up"), (b"\x1b[B", "down"), (b"\x1bOB", "down"),
    (b"\x1b[H", "home"), (b"\x1bOH", "home"), (b"\x1b[1~", "home"),
    (b"\x1b[F", "end"), (b"\x1bOF", "end"), (b"\x1b[4~", "end"),
    (b"\x1b[5~", "pgup"), (b"\x1b[6~", "pgdn"),
)

_KEYS: tuple[tuple[bytes, str], ...] = (
    (b"\x1b", "esc"), (b"\r", "enter"), (b"\n", "enter"), (b" ", "space"),
    (b"k", "up"), (b"j", "down"),
)


@contextmanager
def _terminal(label: str) -> Iterator[_Tty]:
    term = _Tty(label)
    try:
        yield term
    finally:
        term.close()


def _hint(term: _Tty, text: str) -> str:
    return term.paint(f"({text})", GRAY)


def ask(label: str, default: str | None = None, validate: Validator | None = None) -> str:
    with _terminal(label) as term:
        while True:
            suffix = f" {term.paint(f'[{default}]', GRAY)}" if default else ""
            term.write(f"{term.question(label)}{suffix}{term.paint(':', bold=True)} ")
            answer = term.readline().strip() or (default or "")
            if not answer:
                term.warn("resposta obrigatória")
                continue
            if validate:
                try:
                    answer = validate(answer)
                except ValueError as problem:
                    term.warn(str(problem) or "valor inválido")
                    continue
            term.write(f"\033[1A\r\033[K{term.answered(label, answer)}\n")
            return answer


def secret(label: str, confirm: bool = True) -> str:
    with _terminal(label) as term:
        while True:
            term.write(f"{term.question(label)}{term.paint(':', bold=True)} ")
            first = term.readline(secret=True)
            if not first:
                term.warn("resposta obrigatória")
                continue
            if confirm:
                term.write(f"{term.question('confirme')}{term.paint(':', bold=True)} ")
                if term.readline(secret=True) != first:
                    term.warn("os valores não conferem")
                    continue
                term.write("\033[1A\r\033[K")
            term.write(f"\033[1A\r\033[K{term.answered(label, '••••••••')}\n")
            return first


def ask_list(label: str, validate: Validator | None = None) -> list[str]:
    items: list[str] = []
    with _terminal(label) as term:
        while True:
            term.write(f"{term.question(label)} {_hint(term, 'Enter vazio termina')}{term.paint(':', bold=True)} ")
            answer = term.readline().strip()
            if not answer:
                term.write("\033[1A\r\033[K")
                break
            if validate:
                try:
                    answer = validate(answer)
                except ValueError as problem:
                    term.warn(f"{problem or 'valor inválido'}: {answer}")
                    continue
            term.write(f"\033[1A\r\033[K{term.answered(label, answer)}\n")
            items.append(answer)
        if not items:
            term.write(f"{term.answered(label, 'nenhum', GRAY)}\n")
    return items


def confirm(question: str, default: bool = False) -> bool:
    with _terminal(question) as term:
        while True:
            hint = term.paint("[S/n]" if default else "[s/N]", GRAY)
            term.write(f"{term.question(question)} {hint} ")
            answer = term.readline().strip().lower()
            if not answer:
                result = default
            elif answer in ("s", "sim", "y", "yes"):
                result = True
            elif answer in ("n", "não", "nao", "no"):
                result = False
            else:
                term.warn("responda s ou n")
                continue
            term.write(f"\033[1A\r\033[K{term.answered(question, 'sim' if result else 'não', GREEN if result else GRAY)}\n")
            return result


class _List:
    def __init__(self, term: _Tty, title: str, hint: str, total: int) -> None:
        self.term = term
        self.title = title
        self.total = total
        self.cursor = 0
        self.top = 0
        self.drawn = 0
        self.rows = max(3, min(total, term.size()[1] - 4))
        term.write(f"{term.question(title)} {_hint(term, hint)}\n")

    def move(self, key: str) -> bool:
        moves = {
            "up": (self.cursor - 1) % self.total,
            "down": (self.cursor + 1) % self.total,
            "home": 0,
            "end": self.total - 1,
            "pgup": max(0, self.cursor - self.rows),
            "pgdn": min(self.total - 1, self.cursor + self.rows),
        }
        if key in moves:
            self.cursor = moves[key]
            return True
        return False

    def draw(self, line: Callable[[int, bool], str]) -> None:
        term = self.term
        if self.drawn:
            term.write(f"\033[{self.drawn}A")
        self.top = min(max(self.top, self.cursor - self.rows + 1), self.cursor)
        rows = min(self.rows, self.total)
        out = [f"\r\033[K{_tag(term.depth)}       {line(i, i == self.cursor)}" for i in range(self.top, self.top + rows)]
        if self.total > rows:
            out.append(f"\r\033[K{_tag(term.depth)}         {term.paint(f'{self.cursor + 1} de {self.total}', GRAY)}")
        term.write("\n".join(out) + "\n")
        self.drawn = len(out)

    def close(self, answer: str, rgb: Rgb = SOFT) -> None:
        self.term.write(f"\033[{self.drawn + 1}A\r\033[J{self.term.answered(self.title, answer, rgb)}\n")


def _labels(items: Sequence[str], details: Sequence[str], term: _Tty) -> list[tuple[str, str]]:
    width = max((len(item) for item in items), default=0)
    return [
        (item.ljust(width) if details else item, f"  {term.paint(details[i], GRAY)}" if i < len(details) and details[i] else "")
        for i, item in enumerate(items)
    ]


def menu(title: str, items: Sequence[str], details: Sequence[str] = ()) -> int:
    back = len(items) - 1 if items and items[-1] in ("Voltar", "Sair") else None
    hint = "↑/↓ e Enter" + (f", Esc {'volta' if items[-1] == 'Voltar' else 'sai'}" if back is not None else "")
    with _terminal(title) as term, term.raw():
        view = _List(term, title, hint, len(items))
        width = len(str(len(items)))
        labels = _labels(items, details, term)

        def line(i: int, current: bool) -> str:
            number = f"{i + 1:>{width}}."
            label, detail = labels[i]
            if current:
                return f"{term.paint('❯', ACCENT, bold=True)} {term.paint(number, ACCENT)} {term.paint(label, SOFT, bold=True)}{detail}"
            return f"  {term.paint(number, GRAY)} {label}{detail}"

        while True:
            view.draw(line)
            key = term.key()
            if view.move(key):
                continue
            if key == "enter":
                break
            if key == "esc" and back is not None:
                view.cursor = back
                break
            if key.isdigit() and 1 <= int(key) <= len(items):
                view.cursor = int(key) - 1
        view.close(items[view.cursor])
        return view.cursor


def checklist(
    title: str,
    items: Sequence[str],
    selected: Sequence[int] = (),
    all_option: bool = False,
    cancel: bool = False,
    details: Sequence[str] = (),
) -> list[int] | None:
    marks = [i in selected for i in range(len(items))]
    offset = 1 if all_option else 0
    hint = "↑/↓, Espaço marca, a = todos, Enter confirma" + (", Esc volta" if cancel else "")
    with _terminal(title) as term, term.raw():
        view = _List(term, title, hint, len(items) + offset)
        labels = _labels(items, details, term)

        def line(i: int, current: bool) -> str:
            (label, detail), on = (("Todos", ""), all(marks)) if i < offset else (labels[i - offset], marks[i - offset])
            box = term.paint("◉", GREEN, bold=True) if on else term.paint("○", GRAY)
            if current:
                return f"{term.paint('❯', ACCENT, bold=True)} {box} {term.paint(label, SOFT, bold=True)}{detail}"
            return f"  {box} {label}{detail}"

        while True:
            view.draw(line)
            key = term.key()
            if view.move(key):
                continue
            if key == "enter":
                break
            if key == "esc" and cancel:
                view.close("cancelado", GRAY)
                return None
            if key == "a" or (key == "space" and view.cursor < offset):
                marks = [not all(marks)] * len(items)
            elif key == "space":
                marks[view.cursor - offset] = not marks[view.cursor - offset]
        chosen = [i for i, on in enumerate(marks) if on]
        view.close(", ".join(items[i] for i in chosen) if chosen else "nenhum", SOFT if chosen else GRAY)
        return chosen
