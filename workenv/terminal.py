"""The terminal an entry is drawn in: the entry model's frames drawn as lines, and the bytes a
person types read as the model's inputs (`workenv.tui`). It adds no rule of its own.

Drawing. Each element is one line: the two-cell focus gutter, then its marks, its label and its
effects as the model words them (`tui.drawn`), clipped at `columns - 2` cells. A field's value
follows on up to three lines. An element the model places below the last row is not drawn. A
control character is drawn as its caret notation (`^[`, `^J`), two cells, as the model counts it,
so nothing typed or pasted acts on the terminal.

Reading (`Decoder`):

  - the arrows, Tab and Shift-Tab, Enter, Esc, Space, Backspace, Home, Page Up and Page Down are
    read by their escape sequences, as the model's keys;
  - a bracketed paste arrives as one paste input, cut where the model's input holds no more;
  - any other printable text is a text input, however the reads split it;
  - Ctrl-C and Ctrl-D leave, and nothing is sent. No letter is a shortcut;
  - an escape sequence nothing here names is dropped whole, and Esc alone is Esc once no more
    bytes follow it.

A resize (`SIGWINCH`) is a resize input.
"""
from __future__ import annotations

import codecs
import os
import select
import signal
import termios
import tty

from workenv import tui

QUIT = "quit"
PASTE_START, PASTE_END = b"\x1b[200~", b"\x1b[201~"
KEYS = {b"\x1b[A": "up", b"\x1b[B": "down", b"\x1b[C": "right", b"\x1b[D": "left",
        b"\x1bOA": "up", b"\x1bOB": "down", b"\x1bOC": "right", b"\x1bOD": "left",
        b"\x1b[Z": "back_tab", b"\x1b[H": "home", b"\x1bOH": "home", b"\x1b[1~": "home",
        b"\x1b[7~": "home", b"\x1b[5~": "page_up", b"\x1b[6~": "page_down",
        b"\t": "tab", b"\r": "enter", b"\n": "enter", b" ": "space", b"\x7f": "backspace",
        b"\x08": "backspace"}
LEAVE = (b"\x03", b"\x04")
# The most characters one text or paste input holds (C12 `surface_script`).
HOLDS = 2000
# How long a lone Esc waits for the rest of a sequence, in seconds.
ESCAPE_WAIT = 0.05
ENTER = "\x1b[?1049h\x1b[?25l\x1b[?2004h"
LEAVE_SCREEN = "\x1b[?2004l\x1b[?25h\x1b[?1049l"


def texts(kind: str, text: str) -> list[dict]:
    return [{"input": kind, "text": text[at:at + HOLDS]} for at in range(0, len(text), HOLDS)]


class Decoder:
    """Bytes as the model's inputs, fed as they arrive."""

    def __init__(self):
        self.pending = b""
        self.pasting: bytes | None = None
        self.text = codecs.getincrementaldecoder("utf-8")("replace")

    def feed(self, data: bytes) -> list:
        self.pending += data
        found: list = []
        while self.pending:
            step = self.step()
            if step is None:
                break
            found += step
        return found

    def flush(self) -> list:
        """What is waiting once no more bytes came: a lone Esc, and the rest read after it."""
        if self.pasting is not None or not self.pending.startswith(b"\x1b"):
            return []
        self.pending = self.pending[1:]
        return [{"input": "key", "key": "escape"}] + self.feed(b"")

    def step(self) -> list | None:
        """The inputs the front of the pending bytes makes, having consumed them, or None where
        they are the start of something not complete yet."""
        data = self.pending
        if self.pasting is not None:
            held = self.pasting + data
            end = held.find(PASTE_END)
            if end < 0:
                self.pasting, self.pending = held, b""
                return None
            self.pasting, self.pending = None, held[end + len(PASTE_END):]
            return texts("paste", held[:end].decode("utf-8", "replace"))
        if data.startswith(PASTE_START):
            self.pasting, self.pending = b"", data[len(PASTE_START):]
            return []
        if data[:1] in LEAVE:
            self.pending = data[1:]
            return [QUIT]
        if data[:1] == b"\x1b":
            return self.escape(data)
        for sequence, key in KEYS.items():
            if data.startswith(sequence):
                self.pending = data[len(sequence):]
                return [{"input": "key", "key": key}]
        if data[0] < 0x20:
            self.pending = data[1:]
            return []
        end = next((at for at, byte in enumerate(data) if byte < 0x20 or byte in (0x20, 0x7F)),
                   len(data))
        self.pending = data[end:]
        text = self.text.decode(data[:end])
        return texts("text", text)

    def escape(self, data: bytes) -> list | None:
        for sequence, key in KEYS.items():
            if data.startswith(sequence):
                self.pending = data[len(sequence):]
                return [{"input": "key", "key": key}]
        if len(data) == 1 or any(sequence.startswith(data) for sequence in
                                 (*KEYS, PASTE_START)):
            return None
        if data[1:2] == b"[":
            final = next((at for at in range(2, len(data)) if 0x40 <= data[at] <= 0x7E), None)
            if final is None:
                return None
            self.pending = data[final + 1:]
            return []
        if data[1:2] == b"O":
            self.pending = data[3:]
            return []
        self.pending = data[1:]
        return [{"input": "key", "key": "escape"}]


# Drawing.

def visible(text: str) -> str:
    """The text with each control character as its caret notation."""
    return "".join(f"^{chr(ord(char) ^ 0x40)}" if ord(char) < 0x20 or ord(char) == 0x7F
                   else char for char in text)


def clipped(text: str, room: int) -> str:
    kept, used = [], 0
    for char in text:
        width = tui.cells(char)
        if used + width > room:
            break
        kept.append(char)
        used += width
    return "".join(kept)


def wrapped(text: str, room: int) -> list[str]:
    lines, line, used = [], [], 0
    for char in text:
        width = tui.cells(char)
        if used + width > room and line:
            lines.append("".join(line))
            line, used = [], 0
        line.append(char)
        used += width
    lines.append("".join(line))
    return lines


def lines(frame: dict) -> list[str]:
    """What one frame draws, row by row."""
    columns, rows = frame["terminal"]["columns"], frame["terminal"]["rows"]
    room, gutter = max(columns - tui.GUTTER, 1), " " * tui.GUTTER
    found = []
    for element in frame["elements"]:
        if element["shown"] == "off_screen":
            continue
        line = visible(tui.drawn(element, frame["locale"]))
        found.append(gutter + clipped(line, room))
        if element["role"] == "field":
            found += [gutter + part for part in
                      wrapped(visible(element.get("value", "")), room)[:tui.VALUE_LINES]]
    return found[:rows]


class Terminal:
    """The person's terminal, held raw for the length of an entry."""

    def __init__(self, fd_in: int = 0, fd_out: int = 1):
        self.fd_in, self.fd_out = fd_in, fd_out
        self.resized = False
        self.decoder = Decoder()

    def __enter__(self) -> Terminal:
        self.saved = termios.tcgetattr(self.fd_in)
        self.previous = signal.signal(signal.SIGWINCH, self.on_resize)
        tty.setraw(self.fd_in)
        self.write(ENTER)
        return self

    def __exit__(self, *_) -> None:
        self.write(LEAVE_SCREEN)
        termios.tcsetattr(self.fd_in, termios.TCSAFLUSH, self.saved)
        signal.signal(signal.SIGWINCH, self.previous)

    def on_resize(self, *_) -> None:
        self.resized = True

    def write(self, text: str) -> None:
        data = text.encode("utf-8")
        while data:
            data = data[os.write(self.fd_out, data):]

    def size(self) -> tuple[int, int]:
        found = os.get_terminal_size(self.fd_out)
        return found.columns, found.lines

    def draw(self, frame: dict) -> None:
        self.write("\x1b[H" + "".join(f"{line}\x1b[K\r\n" for line in lines(frame)) + "\x1b[J")

    def inputs(self):
        """The person's inputs, as they come: a resize, a key, text or a paste, or QUIT."""
        while True:
            if self.resized:
                self.resized = False
                columns, rows = self.size()
                yield {"input": "resize", "columns": columns, "rows": rows}
            waiting = self.decoder.pending.startswith(b"\x1b") and self.decoder.pasting is None
            ready, _, _ = select.select([self.fd_in], [], [], ESCAPE_WAIT if waiting else 0.2)
            if not ready:
                yield from self.decoder.flush() if waiting else ()
                continue
            data = os.read(self.fd_in, 4096)
            if not data:
                yield QUIT
                return
            yield from self.decoder.feed(data)
