"""The terminal an entry is drawn in (`workenv.terminal`): the bytes a person types read as the
entry model's inputs, however the reads split them, and a frame drawn as the model measured it."""
from __future__ import annotations

import fcntl
import os
import select
import signal
import struct
import termios
import threading
import types
import unittest

import bench  # noqa: F401  (puts the checkout on the path)

from workenv import terminal, tui


def key(name: str) -> dict:
    return {"input": "key", "key": name}


def fed(*chunks: bytes) -> list:
    decoder = terminal.Decoder()
    found = []
    for chunk in chunks:
        found += decoder.feed(chunk)
    return found + decoder.flush()


class Reading(unittest.TestCase):
    def test_each_key_is_read_by_its_sequence(self):
        for data, name in terminal.KEYS.items():
            with self.subTest(name=name, data=data):
                self.assertEqual(fed(data), [key(name)])

    def test_a_sequence_split_across_reads_is_one_key(self):
        self.assertEqual(fed(b"\x1b", b"[", b"B"), [key("down")])
        self.assertEqual(fed(b"\x1bO", b"A"), [key("up")])
        self.assertEqual(fed(b"\x1b[5", b"~\t"), [key("page_up"), key("tab")])

    def test_esc_alone_is_esc_once_nothing_follows_and_before_what_does(self):
        self.assertEqual(fed(b"\x1b"), [key("escape")])
        self.assertEqual(fed(b"\x1bq"), [key("escape"), {"input": "text", "text": "q"}])
        decoder = terminal.Decoder()
        self.assertEqual(decoder.feed(b"\x1b"), [])
        self.assertEqual(decoder.flush(), [key("escape")])

    def test_a_sequence_nothing_here_names_is_dropped_whole(self):
        self.assertEqual(fed(b"\x1b[1;5A", b"\x1bOP", b"\x1b[15~x"),
                         [{"input": "text", "text": "x"}])

    def test_text_is_text_however_the_reads_split_it_and_space_is_the_key(self):
        word = "q 종료".encode()
        self.assertEqual(fed(word[:3], word[3:5], word[5:]),
                         [{"input": "text", "text": "q"}, key("space"),
                          {"input": "text", "text": "종"}, {"input": "text", "text": "료"}])

    def test_a_paste_is_one_input_with_its_controls_as_data(self):
        pasted = "첫 줄\n\x1b[31m".encode()
        self.assertEqual(fed(terminal.PASTE_START + pasted[:4], pasted[4:] + b"\x1b[20",
                             b"1~\t"),
                         [{"input": "paste", "text": "첫 줄\n\x1b[31m"}, key("tab")])

    def test_a_paste_longer_than_an_input_holds_is_cut_into_inputs(self):
        found = fed(terminal.PASTE_START + b"a" * (terminal.HOLDS + 1) + terminal.PASTE_END)
        self.assertEqual([len(given["text"]) for given in found], [terminal.HOLDS, 1])

    def test_ctrl_c_and_ctrl_d_leave_and_other_controls_are_nothing(self):
        self.assertEqual(fed(b"\x03"), [terminal.QUIT])
        self.assertEqual(fed(b"\x04"), [terminal.QUIT])
        self.assertEqual(fed(b"\x01\x02\x05q"), [{"input": "text", "text": "q"}])


def frame(*elements: dict, columns: int = 20, rows: int = 24, locale: str = "ko") -> dict:
    found = [{"marks": [], "shown": "whole", "role": "action", **element}
             for element in elements]
    return {"terminal": {"columns": columns, "rows": rows}, "locale": locale,
            "elements": found}


class Drawing(unittest.TestCase):
    def test_an_element_s_effects_are_drawn_on_its_line_in_the_frame_s_words(self):
        start = {"label": "시작", "effects": ["file_changes", "model_calls"]}
        self.assertEqual(terminal.lines(frame(start, columns=40)),
                         ["  시작 · 파일 변경 · 모델 호출"])
        self.assertEqual(terminal.lines(frame(start, columns=40, locale="en")),
                         ["  시작 · file changes · model calls"])

    def test_each_element_is_one_line_after_the_gutter_with_its_marks(self):
        self.assertEqual(terminal.lines(frame({"label": "시작", "marks": ["›", "[x]"]})),
                         ["  › [x] 시작"])

    def test_a_line_is_clipped_at_its_cells_and_a_wide_character_is_never_split(self):
        self.assertEqual(terminal.lines(frame({"label": "가" * 10}, columns=12)),
                         ["  " + "가" * 5])
        self.assertEqual(terminal.lines(frame({"label": "a" + "가" * 10}, columns=12)),
                         ["  a" + "가" * 4])

    def test_controls_are_drawn_as_caret_notation(self):
        self.assertEqual(terminal.visible("a\x1b[1m\n\x7f"), "a^[[1m^J^?")
        self.assertEqual(tui.cells("\x1b\n\x7f"), len(terminal.visible("\x1b\n\x7f")))

    def test_a_field_s_value_takes_up_to_three_lines(self):
        drawn = terminal.lines(frame({"label": "메모", "role": "field", "value": "a" * 50},
                                     columns=12))
        self.assertEqual(drawn, ["  메모", "  " + "a" * 10, "  " + "a" * 10, "  " + "a" * 10])
        self.assertEqual(terminal.lines(frame({"label": "메모", "role": "field", "value": ""})),
                         ["  메모", "  "])

    def test_an_element_off_screen_is_not_drawn_and_nothing_passes_the_last_row(self):
        drawn = terminal.lines(frame({"label": "a"}, {"label": "b", "shown": "off_screen"},
                                     {"label": "c", "role": "field", "value": "x" * 90},
                                     rows=3))
        self.assertEqual(drawn, ["  a", "  c", "  " + "x" * 18])

    def test_what_the_model_measures_whole_is_drawn_whole_and_clipped_is_cut(self):
        # The model measures the line the terminal draws, effects included.
        elements = [{"element_id": f"{width}{effects}", "role": "action", "label": "가" * width,
                     "marks": ["›"], **({"effects": ["model_calls"]} if effects else {})}
                    for width in range(1, 12) for effects in (False, True)]
        tui.Entry.fit(types.SimpleNamespace(terminal={"columns": 20, "rows": 24}, locale="ko"),
                      elements)
        for element, line in zip(elements, terminal.lines(
                {"terminal": {"columns": 20, "rows": 40}, "locale": "ko", "elements": elements}),
                strict=True):
            whole = "  › " + element["label"] + (" · 모델 호출" if "effects" in element else "")
            with self.subTest(shown=element["shown"], width=len(element["label"])):
                self.assertEqual(line == whole, element["shown"] == "whole")
                self.assertTrue(whole.startswith(line))


class Held(unittest.TestCase):
    """A real pseudo-terminal: raw while the entry is drawn, as it was after. Its other side is
    read as a person's terminal reads it, so what is drawn drains."""

    def setUp(self):
        self.master, self.slave = os.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        self.shown, self.reading = bytearray(), True
        reader = threading.Thread(target=self.read, daemon=True)
        reader.start()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        self.addCleanup(reader.join)
        self.addCleanup(setattr, self, "reading", False)

    def read(self) -> None:
        while self.reading:
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    self.shown += os.read(self.master, 65536)
                except OSError:
                    return

    def output(self) -> bytes:
        select.select([], [], [], 0.2)
        return bytes(self.shown)

    def test_the_terminal_is_raw_while_held_and_restored_after(self):
        before = termios.tcgetattr(self.slave)
        held = terminal.Terminal(self.slave, self.slave)
        self.assertEqual(held.size(), (100, 30))
        with held:
            self.assertEqual(termios.tcgetattr(self.slave)[3] & termios.ICANON, 0)
            held.draw(frame({"label": "시작"}))
            # A byte after each awaited input, so a missing one fails rather than waits.
            os.write(self.master, b"\x1b[B\x03\t")
            inputs = held.inputs()
            self.assertEqual([next(inputs), next(inputs)], [key("down"), terminal.QUIT])
        self.assertEqual(termios.tcgetattr(self.slave), before)
        shown = self.output()
        self.assertIn(terminal.ENTER.encode(), shown)
        self.assertIn("  시작".encode(), shown)
        self.assertTrue(shown.endswith(terminal.LEAVE_SCREEN.encode()))

    def test_the_end_of_input_leaves(self):
        read, write = os.pipe()
        self.addCleanup(os.close, read)
        os.write(write, b"\x1b[A")
        os.close(write)
        self.assertEqual(list(terminal.Terminal(read, self.slave).inputs()),
                         [key("up"), terminal.QUIT])

    def test_a_resize_is_an_input_with_the_new_size(self):
        previous = signal.getsignal(signal.SIGWINCH)
        with terminal.Terminal(self.slave, self.slave) as held:
            fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            os.kill(os.getpid(), signal.SIGWINCH)
            os.write(self.master, b"\t\x1b[A")
            inputs = held.inputs()
            self.assertEqual([next(inputs), next(inputs)],
                             [{"input": "resize", "columns": 80, "rows": 24}, key("tab")])
        self.assertEqual(signal.getsignal(signal.SIGWINCH), previous)


if __name__ == "__main__":
    unittest.main()
