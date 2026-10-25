"""PyQt6 GUI for PyWaveScope."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Qt's bundled GTK3 theme plugin aborts on GNOME versions whose xsettings schema
# lacks the 'antialiasing' key; the generic theme avoids it.
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPalette,
    QPainter,
    QPen,
    QPolygonF,
    QShortcut,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .signal_analysis import SignalAnalysis
from .signal_condition import SignalCondition
from .signal_sample import SignalSample
from .vcd_parser import parse_vcd
from .waveform import Waveform
from .wlf import WLFConversionError, load_wlf

THEME = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "panel_alt": "#1c2230",
    "border": "#30363d",
    "text": "#e6edf3",
    "dim": "#8b949e",
    "accent": "#58a6ff",
    "grid": "#1f2630",
    "trace": "#3fb950",
    "bus": "#58a6ff",
    "bus_text": "#a5d6ff",
    "match": "#f0883e",
    "event": "#ff7b72",
    "marker": "#d2a8ff",
    "band_selected": "#16243a",
    "band_match": "#2a1f14",
    "field_active": "#3b2f17",
}


def apply_dark_theme(app: QApplication) -> None:
    """Fusion style with a dark palette and a matching stylesheet."""
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "panel"),
        (QPalette.ColorRole.AlternateBase, "panel_alt"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "panel"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "panel_alt"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "bg"),
        (QPalette.ColorRole.PlaceholderText, "dim"),
    ):
        palette.setColor(role, QColor(THEME[key]))
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QWidget {{ font-size: 10pt; }}
        QLabel {{ color: {THEME['text']}; }}
        QPlainTextEdit {{
            background: {THEME['panel']}; color: {THEME['text']};
            border: 1px solid {THEME['border']}; border-radius: 6px; padding: 4px 8px;
            selection-background-color: {THEME['accent']};
        }}
        QPlainTextEdit:focus {{ border: 1px solid {THEME['accent']}; }}
        QScrollArea {{ border: 1px solid {THEME['border']}; border-radius: 6px; background: {THEME['bg']}; }}
        QScrollBar:vertical {{ background: {THEME['bg']}; width: 12px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {THEME['border']}; border-radius: 5px; min-height: 24px; }}
        QScrollBar::handle:vertical:hover {{ background: {THEME['dim']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
        QToolTip {{
            background: {THEME['panel_alt']}; color: {THEME['text']};
            border: 1px solid {THEME['border']}; padding: 4px;
        }}
        """
    )


ANALYSES = (
    "Count rising edges",
    "Count falling edges",
    "Nth assertion time",
    "Nth deassertion time",
    "Edges between times",
    "Condition matching",
)

MATCH_SIGNAL = "condition match"


class Overlay:
    """Markers (time, label), highlighted event times and an optional derived signal."""

    def __init__(self) -> None:
        self.markers: list[tuple[int, str]] = []
        self.events: list[int] = []
        self.derived: list[SignalSample] | None = None
        self.target: str | None = None


def compute_overlay(
    waveform: Waveform,
    analysis: str,
    signal: str,
    *,
    start_time: int = 0,
    end_time: int | None = None,
    value: str = "",
    n: int = 1,
    condition: str = "",
) -> Overlay:
    """Compute markers, events and derived signal to display for an analysis."""
    overlay = Overlay()
    overlay.target = signal

    def in_range(time: int) -> bool:
        return time >= start_time and (end_time is None or time <= end_time)

    def edge_times(target: str) -> list[int]:
        times: list[int] = []
        previous: str | None = None
        for sample in waveform.samples(signal):
            if previous is not None and in_range(sample.time):
                if previous != target and sample.value == target:
                    times.append(sample.time)
            previous = sample.value
        return times

    if analysis == "Count rising edges":
        overlay.events = edge_times("1")
    elif analysis == "Count falling edges":
        overlay.events = edge_times("0")
    elif analysis == "Edges between times":
        overlay.events = edge_times(value or "1")
    elif analysis == "Nth assertion time":
        t = SignalAnalysis.nth_assertion_time(
            waveform, signal, asserted_value=value or "1", start_time=start_time, n=n
        )
        if t is not None and in_range(t):
            overlay.markers.append((t, f"assert #{n}"))
            overlay.events.append(t)
    elif analysis == "Nth deassertion time":
        t = SignalAnalysis.nth_deassertion_time(
            waveform, signal, deasserted_value=value or "0", start_time=start_time, n=n
        )
        if t is not None and in_range(t):
            overlay.markers.append((t, f"deassert #{n}"))
            overlay.events.append(t)
    elif analysis == "Condition matching":
        parsed, names = SignalCondition.parse(condition)
        times = sorted({s.time for name in names for s in waveform.samples(name)})
        derived: list[SignalSample] = []
        for t in times:
            matched = "1" if parsed.evaluate(waveform, t) else "0"
            if not derived or derived[-1].value != matched:
                derived.append(SignalSample(t, matched))
        overlay.derived = derived
        overlay.target = None
        overlay.events = [s.time for s in derived if s.value == "1" and in_range(s.time)]
    return overlay


def load_waveform(path: str | Path) -> Waveform:
    """Load a waveform from a .vcd or .wlf file."""
    if Path(path).suffix.lower() == ".wlf":
        return load_wlf(path)
    return parse_vcd(path)


def run_analysis(
    waveform: Waveform,
    analysis: str,
    signal: str,
    *,
    start_time: int = 0,
    end_time: int | None = None,
    value: str = "",
    n: int = 1,
    condition: str = "",
) -> str:
    """Run the named analysis and return a human-readable result."""
    if analysis == "Condition matching":
        overlay = compute_overlay(
            waveform, analysis, signal, start_time=start_time, end_time=end_time, condition=condition
        )
        shown = ", ".join(map(str, overlay.events[:10])) + (" ..." if len(overlay.events) > 10 else "")
        return f"{len(overlay.events)} match(es) at [{shown}]"
    if analysis == "Count rising edges":
        if end_time is not None:
            return str(len(compute_overlay(waveform, analysis, signal, start_time=start_time, end_time=end_time).events))
        return str(SignalAnalysis.count_rising_edges(waveform, signal, start_time=start_time))
    if analysis == "Count falling edges":
        if end_time is not None:
            return str(len(compute_overlay(waveform, analysis, signal, start_time=start_time, end_time=end_time).events))
        return str(SignalAnalysis.count_falling_edges(waveform, signal, start_time=start_time))
    if analysis == "Nth assertion time":
        result = SignalAnalysis.nth_assertion_time(
            waveform, signal, asserted_value=value or "1", start_time=start_time, n=n
        )
    elif analysis == "Nth deassertion time":
        result = SignalAnalysis.nth_deassertion_time(
            waveform, signal, deasserted_value=value or "0", start_time=start_time, n=n
        )
    elif analysis == "Edges between times":
        return str(
            SignalAnalysis.count_signal_edges_between(
                waveform,
                signal,
                start_time=start_time,
                end_time=end_time,
                asserted_value=value or "1",
            )
        )
    else:
        raise ValueError(f"Unknown analysis '{analysis}'")
    if result is not None and end_time is not None and result > end_time:
        result = None
    return "not found" if result is None else str(result)


def nice_step(span: float, target_ticks: int) -> int:
    """Return a 1/2/5 x 10^k tick step giving roughly ``target_ticks`` ticks over ``span``."""
    raw = max(span / max(target_ticks, 1), 1)
    magnitude = 10 ** (len(str(int(raw))) - 1)
    for factor in (1, 2, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


class WaveformView(QWidget):
    """Draws all signals as digital traces with a time ruler, zoomable range, cursor and markers."""

    ROW_HEIGHT = 40
    RULER_HEIGHT = 28
    LABEL_WIDTH = 140
    MARGIN = 10

    def __init__(self) -> None:
        super().__init__()
        self.waveform: Waveform | None = None
        self.signals: list[str] = []
        self.selected: set[str] = set()
        self.markers: list[tuple[int, str]] = []
        self.overlay = Overlay()
        self.view_start: int | None = None
        self.view_end: int | None = None
        self.cursor_time: int | None = None
        self.cursor_signal: str | None = None
        self.setMinimumHeight(200)

    def set_data(
        self, waveform: Waveform | None, signals: list[str], selected: list[str] | None = None
    ) -> None:
        changed = waveform is not self.waveform
        self.waveform = waveform
        self.signals = signals
        self.selected = set(selected or [])
        if changed:
            self.cursor_signal = None
            self.reset_range()
        self._resize_to_rows()

    def set_overlay(self, overlay: Overlay) -> None:
        self.overlay = overlay
        self._resize_to_rows()

    def _resize_to_rows(self) -> None:
        self.setMinimumHeight(max(200, (len(self._rows()) + 1) * self.ROW_HEIGHT + self.RULER_HEIGHT + 20))
        self.update()

    def _rows(self) -> list[tuple[str, list[SignalSample]]]:
        if self.waveform is None:
            return []
        rows = [(name, self.waveform.samples(name)) for name in self.signals]
        if self.overlay.derived is not None:
            rows.append((MATCH_SIGNAL, self.overlay.derived))
        return rows

    def full_range(self) -> tuple[int, int]:
        times = [s.time for _, samples in self._rows() for s in samples]
        times += [t for t, _ in self.markers] + [t for t, _ in self.overlay.markers]
        return 0, max(times, default=0) or 1

    def view_range(self) -> tuple[int, int]:
        start, end = self.full_range()
        if self.view_start is not None:
            start = self.view_start
        if self.view_end is not None:
            end = self.view_end
        return start, end

    def reset_range(self) -> None:
        self.view_start = self.view_end = None
        self.center_cursor()
        self.update()

    def center_cursor(self) -> None:
        if self.waveform is None:
            self.cursor_time = None
            return
        start, end = self.view_range()
        self.cursor_time = (start + end) // 2

    def narrow(self, side: str) -> bool:
        """Keep the part of the visible range left or right of the main cursor, then re-centre the cursor."""
        start, end = self.view_range()
        if end - start < 2:
            return False
        middle = self.cursor_time
        if middle is None or not start < middle < end:
            middle = (start + end) // 2
        self.view_start, self.view_end = (start, middle) if side == "left" else (middle, end)
        self.center_cursor()
        self.update()
        return True

    def change_times(self) -> list[int]:
        """Times at which the cursor signal (or any signal) changes value."""
        if self.waveform is None:
            return []
        names = [self.cursor_signal] if self.cursor_signal else self.signals
        times: set[int] = set()
        for name in names:
            previous: str | None = None
            for sample in self.waveform.samples(name):
                if previous is not None and sample.value != previous:
                    times.add(sample.time)
                previous = sample.value
        return sorted(times)

    def move_cursor(self, direction: int) -> int | None:
        """Move the cursor to the next (+1) / previous (-1) signal change; returns new time."""
        changes = self.change_times()
        start, end = self.view_range()
        if self.cursor_time is None:
            candidates = [t for t in changes if start <= t <= end]
            target = (candidates[0] if direction > 0 else candidates[-1]) if candidates else None
        elif direction > 0:
            target = next((t for t in changes if self.cursor_time < t <= end), None)
        else:
            target = next((t for t in reversed(changes) if start <= t < self.cursor_time), None)
        if target is not None:
            self.cursor_time = target
            self.update()
        return target

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(THEME["bg"]))
        rows = self._rows()
        if not rows:
            return

        view_start, view_end = self.view_range()
        span = max(view_end - view_start, 1)
        plot_left = self.LABEL_WIDTH + self.MARGIN
        plot_width = max(self.width() - plot_left - self.MARGIN, 1)
        scale = plot_width / span

        def x_at(time: float) -> float:
            return plot_left + (time - view_start) * scale

        trace_pen = QPen(QColor(THEME["trace"]), 2)
        match_pen = QPen(QColor(THEME["match"]), 2)
        box_pen = QPen(QColor(THEME["bus"]), 1)
        text_color = QColor(THEME["text"])
        top = self.RULER_HEIGHT
        total_height = top + len(rows) * self.ROW_HEIGHT + 12

        # Time ruler
        painter.setPen(QPen(QColor(THEME["dim"])))
        painter.drawText(4, 16, f"time  [{view_start}..{view_end}]")
        painter.drawLine(plot_left, top - 2, plot_left + plot_width, top - 2)
        step = nice_step(span, plot_width // 80)
        tick = -(-view_start // step) * step
        while tick <= view_end:
            x = int(x_at(tick))
            painter.setPen(QPen(QColor(THEME["dim"])))
            painter.drawLine(x, top - 7, x, top - 2)
            painter.drawText(x - 20, 0, 40, top - 9, Qt.AlignmentFlag.AlignCenter, str(tick))
            painter.setPen(QPen(QColor(THEME["grid"]), 1))
            painter.drawLine(x, top, x, total_height)
            tick += step

        for row, (name, samples) in enumerate(rows):
            high = top + row * self.ROW_HEIGHT + 12
            low = high + self.ROW_HEIGHT - 16
            is_match = name == MATCH_SIGNAL
            band = QRectF(0, high - 6, self.width(), self.ROW_HEIGHT - 4)
            if is_match:
                painter.fillRect(band, QColor(THEME["band_match"]))
            elif name in self.selected or name == self.cursor_signal:
                painter.fillRect(band, QColor(THEME["band_selected"]))
            painter.setPen(QPen(QColor(THEME["match"]) if is_match else text_color))
            painter.drawText(
                QRectF(4, high, self.LABEL_WIDTH - 8, low - high),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name,
            )
            painter.save()
            painter.setClipRect(QRectF(plot_left, top, plot_width + 1, total_height))
            for index, sample in enumerate(samples):
                following = samples[index + 1] if index + 1 < len(samples) else None
                end_time = following.time if following else view_end
                if end_time < view_start or sample.time > view_end:
                    continue
                x_start, x_end = x_at(sample.time), x_at(end_time)
                if sample.value in ("0", "1"):
                    painter.setPen(match_pen if is_match else trace_pen)
                    y = high if sample.value == "1" else low
                    painter.drawLine(int(x_start), int(y), int(x_end), int(y))
                    if following and following.value in ("0", "1") and following.value != sample.value:
                        painter.drawLine(int(x_end), int(high), int(x_end), int(low))
                else:
                    painter.setPen(box_pen)
                    painter.drawRect(QRectF(x_start, high, x_end - x_start, low - high))
                    painter.setPen(QPen(QColor(THEME["bus_text"])))
                    painter.drawText(
                        QRectF(x_start, high, x_end - x_start, low - high),
                        Qt.AlignmentFlag.AlignCenter,
                        sample.value,
                    )
            painter.restore()

        painter.save()
        painter.setClipRect(QRectF(plot_left - 30, 0, plot_width + 60, total_height + 20))
        # Events: red dashed lines with a dot at the top.
        painter.setBrush(QColor(THEME["event"]))
        for time in self.overlay.events:
            if view_start <= time <= view_end:
                x = int(x_at(time))
                painter.setPen(QPen(QColor(THEME["event"]), 1, Qt.PenStyle.DashLine))
                painter.drawLine(x, top, x, total_height)
                painter.drawEllipse(x - 4, top - 2, 8, 8)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Markers: user markers (purple) and analysis markers (red), labelled.
        for color, markers in ((QColor(THEME["marker"]), self.markers), (QColor(THEME["event"]), self.overlay.markers)):
            painter.setPen(QPen(color, 2))
            for time, label in markers:
                if view_start <= time <= view_end:
                    x = int(x_at(time))
                    painter.drawLine(x, top, x, total_height)
                    painter.drawText(x + 3, total_height + 12, f"{label} @{time}")

        # Cursor: thick line with white halo, ruler flag and per-row value tags.
        if self.cursor_time is not None and view_start <= self.cursor_time <= view_end:
            x = int(x_at(self.cursor_time))
            cursor_color = QColor(THEME["accent"])
            painter.setPen(QPen(QColor(THEME["bg"]), 6))
            painter.drawLine(x, top - 2, x, total_height)
            painter.setPen(QPen(cursor_color, 3))
            painter.drawLine(x, top - 2, x, total_height)
            painter.setBrush(cursor_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([QPointF(x - 7, 2), QPointF(x + 7, 2), QPointF(x, top - 3)]))
            for row, (name, samples) in enumerate(rows):
                value = None
                for sample in samples:
                    if sample.time > self.cursor_time:
                        break
                    value = sample.value
                tag = f"{value if value is not None else '-'}"
                width = painter.fontMetrics().horizontalAdvance(tag) + 10
                y = top + row * self.ROW_HEIGHT + 12 + (self.ROW_HEIGHT - 16) // 2 - 9
                rect = QRectF(min(x + 6, plot_left + plot_width - width), y, width, 18)
                painter.setBrush(cursor_color)
                painter.drawRoundedRect(rect, 4, 4)
                painter.setPen(QPen(QColor(THEME["bg"])))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, tag)
                painter.setPen(Qt.PenStyle.NoPen)
            label = f"cursor @{self.cursor_time}"
            label_rect = QRectF(x - 45, total_height + 4, 90, 18)
            painter.drawRoundedRect(label_rect, 4, 4)
            painter.setPen(QPen(QColor(THEME["bg"])))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.restore()


COMMANDS = {
    "rising": ("Count rising edges", "<signal> [start= end=]"),
    "falling": ("Count falling edges", "<signal> [start= end=]"),
    "edges": ("Edges between times", "<signal> [value= start= end=]"),
    "assert": ("Nth assertion time", "<signal> [n= value= start=]"),
    "deassert": ("Nth deassertion time", "<signal> [n= value= start=]"),
    "match": ("Condition matching", "<expression, e.g. clk & ~rst | bus=0101> [start= end=]"),
    "left": (None, "- narrow search area to its left half (Ctrl+Left)"),
    "right": (None, "- narrow search area to its right half (Ctrl+Right)"),
    "reset": (None, "- show the whole time range (Ctrl+Up)"),
    "cursor": (None, "<time|signal|any>  - set cursor time or the signal it follows"),
    "next": (None, "- cursor to next signal change (Right on empty line)"),
    "prev": (None, "- cursor to previous signal change (Left on empty line)"),
    "marker": (None, "<time>  - add a marker"),
    "clear": (None, "- remove markers and results"),
    "open": (None, "<path>  - load a VCD/WLF file"),
}
PARAMS = {
    "rising": ("start=", "end="),
    "falling": ("start=", "end="),
    "edges": ("value=", "start=", "end="),
    "assert": ("n=", "value=", "start="),
    "deassert": ("n=", "value=", "start="),
    "match": ("start=", "end="),
}
COLORS = {
    "command": "#79c0ff",
    "signal": "#56d4c4",
    "param": "#ffa657",
    "number": "#d2a8ff",
    "operator": "#ff7b72",
    "error": "#ff6b6b",
    "dim": THEME["dim"],
}
PLAIN_HELP = "Commands: " + ", ".join(COMMANDS)


def _html_usage(usage: str) -> str:
    """Colour a usage string: <placeholders> as signals, key= as params, rest dim."""
    from html import escape

    def colour(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith("<"):
            kind = "signal"
        elif token.endswith("=") or token.startswith("["):
            kind = "param"
        else:
            kind = "dim"
        return f'<span style="color:{COLORS[kind]}">{escape(token)}</span>'

    parts = re.sub(r"<[^>]*>|\[[^\]]*\]|[^<\[]+", colour, usage)
    return parts


def help_html() -> str:
    rows = []
    for name, (_, usage) in COMMANDS.items():
        rows.append(
            f'<b style="color:{COLORS["command"]}">{name}</b> {_html_usage(usage)}'
        )
    keys = (
        f'<span style="color:{COLORS["dim"]}">Keys: Ctrl+Left/Right narrow area, Ctrl+Up reset, '
        "empty line: Left/Right cursor to prev/next change, Up/Down choose followed signal, Ctrl+O open<br>"
        "Command line: Tab = accept suggestion and go to next parameter, Shift+Tab = previous parameter, "
        "in a time field (start=, end=, time=) Left/Right pick the previous/next signal change with the cursor, "
        "Up/Down choose the followed signal, "
        "Backspace on an empty value = clear whole command, Enter = run, Esc = close suggestions</span>"
    )
    return "<br>".join(rows + [keys])


# Field layout per command: (label, kind, positional). Kinds: signal, int, value, expr, path, target.
FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "rising": [("signal=", "signal", True), ("start=", "time", False), ("end=", "time", False)],
    "falling": [("signal=", "signal", True), ("start=", "time", False), ("end=", "time", False)],
    "edges": [
        ("signal=", "signal", True),
        ("value=", "value", False),
        ("start=", "time", False),
        ("end=", "time", False),
    ],
    "assert": [
        ("signal=", "signal", True),
        ("n=", "int", False),
        ("value=", "value", False),
        ("start=", "time", False),
    ],
    "deassert": [
        ("signal=", "signal", True),
        ("n=", "int", False),
        ("value=", "value", False),
        ("start=", "time", False),
    ],
    "match": [("expr=", "expr", True), ("start=", "time", False), ("end=", "time", False)],
    "marker": [("time=", "time", True)],
    "cursor": [("target=", "target", True)],
    "open": [("path=", "path", True)],
}
HINTS = {
    "signal": "signal",
    "int": "number",
    "time": "time: type or use ←/→",
    "value": "value",
    "expr": "clk & ~rst | bus=0101",
    "path": "file",
    "target": "time | signal | any",
}


def field_suggestions(kind: str, value: str, signals: list[str]) -> list[str]:
    """Full replacement values for a field being edited."""
    if kind in ("signal", "target"):
        names = [*signals, "any"] if kind == "target" else signals
        return [name for name in names if name.lower().startswith(value.lower())]
    if kind == "expr":
        cut = max(value.rfind(ch) for ch in "&|~( ") + 1
        head, word = value[:cut], value[cut:]
        if "=" in word:
            return []
        if head.rstrip().endswith(("&", "|")) and not head.endswith(" "):
            head += " "
        return [head + name for name in signals if name.lower().startswith(word.lower())]
    if kind == "value":
        return [v for v in ("0", "1", "x", "z") if v.startswith(value)]
    return []


class SuggestionList(QListWidget):
    """Non-focusable popup list shown above the command line."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            f"QListWidget {{ border: 1px solid {THEME['accent']}; border-radius: 4px; "
            f"background: {THEME['panel_alt']}; color: {THEME['text']}; padding: 2px; }}"
            f"QListWidget::item {{ padding: 2px 6px; }}"
            f"QListWidget::item:selected {{ background: {THEME['accent']}; color: {THEME['bg']}; }}"
        )


class CommandEdit(QPlainTextEdit):
    """Structured, keyboard-only command line.

    The command name is typed/completed first; the parameter names are then
    inserted automatically and only their values are edited.  Tab confirms a
    value (accepting a suggestion if one was typed or selected) and moves to the
    next parameter, Shift+Tab goes back, Backspace on an empty value clears the
    whole command, Enter runs it.
    """

    returnPressed = pyqtSignal()
    timePick = pyqtSignal(str)  # 'next' | 'prev' | 'signal-next' | 'signal-prev'

    def __init__(self) -> None:
        super().__init__()
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.setFont(font)
        self.setFixedHeight(self.fontMetrics().height() + 16)
        self.signals: set[str] = set()
        self.command = ""  # command-name buffer (confirmed once ``fields`` is non-empty / complete)
        self.confirmed = False
        self.values: list[str] = []
        self.active = 0
        self.suggestions: list[str] = []
        self.navigated = False
        self.popup = SuggestionList(self)
        self.popup.hide()
        self.render()

    # --- state helpers -------------------------------------------------
    @property
    def layout_fields(self) -> list[tuple[str, str, bool]]:
        return FIELDS.get(self.command, []) if self.confirmed else []

    def text(self) -> str:
        """Canonical command text understood by the executor ('' when nothing typed)."""
        if not self.confirmed:
            return self.command.strip()
        parts = [self.command]
        for (label, _kind, positional), value in zip(self.layout_fields, self.values):
            value = value.strip()
            if not value:
                continue
            parts.append(value if positional else f"{label}{value}")
        return " ".join(parts)

    def setText(self, text: str) -> None:
        """Load a canonical command line (used by tests / history)."""
        self.clear_command()
        command, _, rest = text.partition(" ")
        self.command = command
        if command not in COMMANDS:
            self.render()
            return
        self.confirmed = True
        fields = FIELDS.get(command, [])
        self.values = [""] * len(fields)
        rest = rest.strip()
        if fields and fields[0][2]:
            tokens = rest.split()
            trailing: list[str] = []
            while tokens and "=" in tokens[-1] and tokens[-1].partition("=")[0] + "=" in [f[0] for f in fields[1:]]:
                trailing.insert(0, tokens.pop())
            self.values[0] = " ".join(tokens)
            for token in trailing:
                key, _, value = token.partition("=")
                for index, (label, _k, _p) in enumerate(fields):
                    if label == key + "=":
                        self.values[index] = value
        self.active = len(fields) - 1 if fields else 0
        self.render()

    def clear_command(self) -> None:
        self.command = ""
        self.confirmed = False
        self.values = []
        self.active = 0
        self.hide_suggestions()
        self.render()

    def popup_visible(self) -> bool:
        return self.popup.isVisible()

    # --- rendering -----------------------------------------------------
    @staticmethod
    def _fmt(color: str, *, bold: bool = False, italic: bool = False, wavy: bool = False,
             background: str | None = None) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(COLORS[color] if color in COLORS else color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontItalic(italic)
        if wavy:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor(COLORS["error"]))
        if background:
            fmt.setBackground(QColor(background))
        return fmt

    def _value_segments(self, kind: str, value: str) -> list[tuple[str, QTextCharFormat]]:
        if kind in ("signal", "target"):
            ok = value in self.signals or (kind == "target" and (value == "any" or value.lstrip("-").isdigit()))
            return [(value, self._fmt("signal" if ok else "error", wavy=not ok and bool(value)))]
        if kind in ("int", "time"):
            bad = bool(value) and not value.lstrip("-").isdigit()
            return [(value, self._fmt("error" if bad else "number", wavy=bad))]
        if kind == "expr":
            segments = []
            for token in re.finditer(r"[&|~()]|\s+|[^\s&|~()]+", value):
                word = token.group(0)
                if word in "&|~()":
                    segments.append((word, self._fmt("operator", bold=True)))
                elif word.isspace():
                    segments.append((word, self._fmt("dim")))
                else:
                    name, sep, val = word.partition("=")
                    ok = name in self.signals
                    segments.append((name, self._fmt("signal" if ok else "error", wavy=not ok)))
                    if sep:
                        segments.append(("=", self._fmt("dim")))
                        segments.append((val, self._fmt("number")))
            return segments
        return [(value, self._fmt("number" if kind == "value" else "dim" if kind == "path" else "number"))]

    def render(self) -> None:
        self.blockSignals(True)
        self.clear()
        cursor = self.textCursor()
        caret_position = 0

        def put(text: str, fmt: QTextCharFormat) -> None:
            cursor.insertText(text, fmt)

        if not self.confirmed:
            valid = self.command in COMMANDS
            put(self.command, self._fmt("command" if valid else "error", bold=valid,
                                        wavy=not valid and bool(self.command)))
            caret_position = cursor.position()
            if not self.command:
                put("command (Tab = list)", self._fmt("dim", italic=True))
        else:
            put(self.command, self._fmt("command", bold=True))
            for index, ((label, kind, _pos), value) in enumerate(zip(self.layout_fields, self.values)):
                put(" ", self._fmt("dim"))
                active = index == self.active
                put(label, self._fmt("param", bold=active, background=THEME["field_active"] if active else None))
                for segment, fmt in self._value_segments(kind, value):
                    if active:
                        fmt.setBackground(QColor(THEME["field_active"]))
                    put(segment, fmt)
                if active:
                    caret_position = cursor.position()
                if active and not value:
                    put(f"<{HINTS.get(kind, '')}>", self._fmt("dim", italic=True, background=THEME["field_active"]))
        cursor.setPosition(caret_position)
        self.setTextCursor(cursor)
        self.blockSignals(False)

    # --- suggestions ---------------------------------------------------
    def current_value(self) -> str:
        if not self.confirmed:
            return self.command
        return self.values[self.active] if self.values else ""

    def refresh_suggestions(self, *, force: bool = False) -> None:
        value = self.current_value()
        if not self.confirmed:
            items = [name for name in COMMANDS if name.startswith(value)] if (value or force) else []
        else:
            items = field_suggestions(self.layout_fields[self.active][1], value, sorted(self.signals))
        self.navigated = False
        if not items or (len(items) == 1 and items[0] == value and self.confirmed):
            self.hide_suggestions()
            return
        self.suggestions = items
        self.popup.clear()
        self.popup.addItems(items)
        self.popup.setCurrentRow(0)
        self.popup.setFixedSize(
            max(self.popup.sizeHintForColumn(0) + 24, 120),
            min(len(items), 8) * (self.popup.sizeHintForRow(0) + 2) + 6,
        )
        origin = self.mapToGlobal(self.rect().topLeft())
        self.popup.move(origin.x(), origin.y() - self.popup.height() - 2)
        self.popup.show()

    def hide_suggestions(self) -> None:
        self.suggestions = []
        self.navigated = False
        if hasattr(self, "popup"):
            self.popup.hide()

    def selected_suggestion(self) -> str | None:
        row = self.popup.currentRow()
        return self.suggestions[row] if self.popup_visible() and 0 <= row < len(self.suggestions) else None

    def _apply_value(self, value: str) -> None:
        if not self.confirmed:
            self.command = value
        else:
            self.values[self.active] = value

    def confirm_command(self) -> None:
        self.confirmed = True
        self.values = [""] * len(self.layout_fields)
        self.active = 0
        self.hide_suggestions()
        self.render()
        if self.layout_fields:
            self.refresh_suggestions()

    def move_field(self, step: int) -> None:
        fields = self.layout_fields
        if not fields:
            return
        self.active = (self.active + step) % len(fields)
        self.hide_suggestions()
        self.render()
        self.refresh_suggestions()

    # --- keyboard ------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.popup_visible() and self.navigated and self.selected_suggestion() is not None:
                self._accept_and_advance()
            else:
                self.hide_suggestions()
                self.returnPressed.emit()
            return
        if key == Qt.Key.Key_Escape:
            self.hide_suggestions()
            return
        if key == Qt.Key.Key_Tab:
            self.on_tab()
            return
        if key == Qt.Key.Key_Backtab or (key == Qt.Key.Key_Tab and modifiers & Qt.KeyboardModifier.ShiftModifier):
            if self.confirmed:
                self.move_field(-1)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.popup_visible():
            step = -1 if key == Qt.Key.Key_Up else 1
            row = max(0, min(self.popup.currentRow() + step, len(self.suggestions) - 1))
            self.popup.setCurrentRow(row)
            self.navigated = True
            return
        if self.confirmed and self.layout_fields[self.active][1] == "time":
            pick = {
                Qt.Key.Key_Right: "next",
                Qt.Key.Key_Left: "prev",
                Qt.Key.Key_Down: "signal-next",
                Qt.Key.Key_Up: "signal-prev",
            }.get(key)
            if pick and not modifiers & Qt.KeyboardModifier.ControlModifier:
                self.timePick.emit(pick)
                return
        if key == Qt.Key.Key_Backspace:
            if self.confirmed and not self.current_value():
                self.clear_command()
            elif self.current_value():
                self._apply_value(self.current_value()[:-1])
                self.render()
                self.refresh_suggestions()
            return
        if key == Qt.Key.Key_Delete:
            self.clear_command()
            return
        text = event.text()
        if text and text.isprintable() and not modifiers & Qt.KeyboardModifier.ControlModifier:
            if not self.confirmed and text.isspace():
                if self.command in COMMANDS:
                    self.confirm_command()
                return
            self._apply_value(self.current_value() + text)
            self.render()
            self.refresh_suggestions()
            if not self.confirmed and self.command in COMMANDS and not FIELDS.get(self.command):
                self.hide_suggestions()

    def expression_complete(self) -> bool:
        """True when the match expression parses, uses known signals and has no dangling operator."""
        try:
            _condition, names = SignalCondition.parse(self.current_value())
        except ValueError:
            return False
        return all(name in self.signals for name in names)

    def _in_expression(self) -> bool:
        return self.confirmed and self.layout_fields[self.active][1] == "expr"

    def on_tab(self) -> None:
        if not self.confirmed:
            if self.popup_visible():
                self._accept_and_advance()
            else:
                self.refresh_suggestions(force=True)
                if len(self.suggestions) == 1:
                    self._accept_and_advance()
            return
        if self._in_expression():
            picked = self.popup_visible() and self.navigated
            if self.expression_complete() and not picked:
                self.move_field(1)
            elif self.popup_visible():
                self._accept_and_advance()
            return
        if self.popup_visible() and (self.navigated or self.current_value()):
            self._accept_and_advance()
        else:
            self.move_field(1)

    def _accept_and_advance(self) -> None:
        choice = self.selected_suggestion()
        if choice is not None:
            self._apply_value(choice)
        self.hide_suggestions()
        if not self.confirmed:
            if self.command in COMMANDS:
                self.confirm_command()
            self.render()
        elif self._in_expression() and not self.expression_complete():
            self.render()
            self.refresh_suggestions()
        else:
            self.move_field(1)

    def set_current_value(self, value: str) -> None:
        if self.confirmed and self.values:
            self.values[self.active] = value
            self.render()

    def focusOutEvent(self, event) -> None:
        self.hide_suggestions()
        super().focusOutEvent(event)

    def insertFromMimeData(self, source) -> None:
        pass

    def focusNextPrevChild(self, _next: bool) -> bool:
        return False


def parse_params(tokens: list[str], allowed: tuple[str, ...]) -> dict:
    params: dict = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or key + "=" not in allowed:
            raise ValueError(f"Unknown parameter '{token}' (allowed: {', '.join(allowed)})")
        if key == "value":
            params["value"] = value
        else:
            try:
                params[{"start": "start_time", "end": "end_time", "n": "n"}[key]] = int(value)
            except ValueError:
                raise ValueError(f"{key}= needs a whole number, got '{value}'") from None
    return params


class ResultLabel(QLabel):
    """Result box shown right of the command line: coloured status badge plus message."""

    STYLES = {
        "Result": ("OK", "#3fb950", "#12261a"),
        "Error": ("ERROR", "#ff6b6b", "#2d1517"),
        "Info": ("INFO", "#58a6ff", "#111d2e"),
    }

    def __init__(self) -> None:
        super().__init__()
        self._plain = ""
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setText("Info: ")

    def text(self) -> str:
        return self._plain

    def setText(self, text: str) -> None:
        from html import escape

        self._plain = text
        kind = "Info"
        message = text
        for prefix in ("Result", "Error"):
            if text.startswith(prefix + ":"):
                kind, message = prefix, text[len(prefix) + 1 :].strip()
                break
        else:
            if text.startswith("Failed"):
                kind = "Error"
        color = "#ff6b6b" if kind == "Error" else THEME["text"]
        shown = message if len(message) <= 220 else message[:217] + "..."
        super().setText(f'<span style="color:{color}">{escape(shown)}</span>')
        self.setToolTip(message)
        self.setStyleSheet(
            f"QLabel {{ background: {THEME['panel']}; border: 1px solid {THEME['border']}; "
            "border-radius: 6px; padding: 3px 10px; }"
        )


class WaveScopeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PyWaveScope")
        self.resize(1000, 600)
        self.waveform: Waveform | None = None
        self._build_widgets()

    def _build_widgets(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        self.file_label = QLabel("No file loaded - type: open <path>  (or press Ctrl+O)")
        self.file_label.setStyleSheet(
            f"QLabel {{ color: {THEME['accent']}; font-weight: bold; padding: 2px 4px; }}"
        )
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.file_label)

        self.view = WaveformView()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.view)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(scroll, 1)

        self.result_label = ResultLabel()
        self.hint_label = QLabel(help_html())
        self.hint_label.setTextFormat(Qt.TextFormat.RichText)
        self.hint_label.setStyleSheet(
            f"QLabel {{ background: {THEME['panel']}; border: 1px solid {THEME['border']}; "
            "border-radius: 6px; padding: 8px 12px; }"
        )
        self.hint_label.setVisible(False)
        layout.addWidget(self.hint_label)

        self.command_edit = CommandEdit()
        self.command_edit.returnPressed.connect(self.run_command)
        self.command_edit.timePick.connect(self.pick_time)
        self.command_edit.installEventFilter(self)
        self.history: list[tuple[str, str]] = []
        self.history_pos: int | None = None
        self.history_label = QLabel("")
        self.history_label.setTextFormat(Qt.TextFormat.RichText)
        self.history_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.history_label.setStyleSheet(
            f"QLabel {{ background: {THEME['panel']}; border: 1px solid {THEME['border']}; "
            "border-radius: 6px; padding: 3px 10px; font-family: monospace; }"
        )
        box_height = self.fontMetrics().lineSpacing() * 3 + 16
        self.history_label.setFixedHeight(box_height)
        self.result_label.setFixedHeight(box_height)
        caption_style = f"QLabel {{ color: {THEME['dim']}; font-weight: bold; padding-left: 4px; }}"
        panels = QHBoxLayout()
        for caption, widget, stretch in (
            ("Previous commands", self.history_label, 3),
            ("Result", self.result_label, 2),
        ):
            column = QVBoxLayout()
            column.setSpacing(3)
            title = QLabel(caption)
            title.setStyleSheet(caption_style)
            column.addWidget(title)
            column.addWidget(widget)
            panels.addLayout(column, stretch)
        layout.addLayout(panels)
        self.render_history()
        layout.addWidget(self.command_edit)

        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_dialog)
        QShortcut(
            QKeySequence("F1"), self, activated=lambda: self.hint_label.setVisible(not self.hint_label.isVisible())
        )
        self.setCentralWidget(central)
        self.command_edit.setFocus()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.command_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            action = None
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and key in (
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
            ):
                self.recall_history(-1 if key == Qt.Key.Key_Up else 1)
                return True
            if ctrl and key == Qt.Key.Key_Left:
                action = "left"
            elif ctrl and key == Qt.Key.Key_Right:
                action = "right"
            elif ctrl and key == Qt.Key.Key_Up:
                action = "reset"
            elif not self.command_edit.text() and not self.command_edit.popup_visible():
                action = {
                    Qt.Key.Key_Left: "prev",
                    Qt.Key.Key_Right: "next",
                    Qt.Key.Key_Up: "cursor-signal-prev",
                    Qt.Key.Key_Down: "cursor-signal-next",
                }.get(key)
            if action:
                self.run_action(action)
                return True
        return super().eventFilter(watched, event)

    def pick_time(self, action: str) -> None:
        """Arrow-key time picking: move the cursor and copy its time into the active field."""
        if self.waveform is None:
            return
        if action.startswith("signal"):
            self.run_action("cursor-signal-" + action.split("-")[1])
            return
        value = self.command_edit.current_value().strip()
        if value.lstrip("-").isdigit() and self.view.cursor_time != int(value):
            self.view.cursor_time = int(value)
        time = self.view.move_cursor(1 if action == "next" else -1)
        if time is not None:
            self.command_edit.set_current_value(str(time))
        self.view.update()

    def run_action(self, action: str) -> None:
        try:
            self.execute(action)
        except (ValueError, KeyError):
            pass

    def signal_names(self) -> list[str]:
        return sorted(self.waveform.signals) if self.waveform else []


    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open waveform", "", "Waveform files (*.vcd *.wlf);;All files (*)"
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        try:
            self.waveform = load_waveform(path)
        except (OSError, WLFConversionError, ValueError) as error:
            self.result_label.setText(f"Failed to load file: {error}")
            return
        self.file_label.setText(Path(path).name)
        self.command_edit.signals = set(self.waveform.signals)
        self.command_edit.render()
        self.view.markers = []
        self.view.set_overlay(Overlay())
        self.view.set_data(self.waveform, self.signal_names())
        self.result_label.setText(f"Loaded {len(self.waveform.signals)} signals")

    def run_command(self) -> None:
        text = self.command_edit.text().strip()
        if not text:
            return
        try:
            result = self.execute(text)
        except (ValueError, KeyError) as error:
            self.result_label.setText(f"Error: {error}")
            self.record_history(text, f"Error: {error}")
            return
        self.result_label.setText(f"Result: {result}")
        self.record_history(text, f"Result: {result}")
        self.command_edit.clear_command()

    def record_history(self, command: str, outcome: str) -> None:
        self.history.append((command, outcome))
        self.history_pos = None
        self.render_history()

    def render_history(self) -> None:
        from html import escape

        lines = []
        for command, outcome in self.history[-3:]:
            failed = outcome.startswith("Error")
            message = outcome.split(":", 1)[1].strip()
            message = message if len(message) <= 60 else message[:57] + "..."
            color = "#ff6b6b" if failed else THEME["dim"]
            lines.append(
                f'<span style="color:{THEME["accent"]}">▸ {escape(command)}</span> '
                f'<span style="color:{color}">→ {escape(message)}</span>'
            )
        self.history_label.setText("<br>".join(lines))

    def recall_history(self, step: int) -> None:
        """Shift+Up/Down: put an older/newer command from the history into the command line."""
        if not self.history:
            return
        if self.history_pos is None:
            if step > 0:
                return
            position = len(self.history) - 1
        else:
            position = self.history_pos + step
        if position >= len(self.history):
            self.history_pos = None
            self.command_edit.clear_command()
            return
        self.history_pos = max(position, 0)
        self.command_edit.setText(self.history[self.history_pos][0])

    def execute(self, text: str) -> str:
        return self._execute(text)

    def _execute(self, text: str) -> str:
        command, _, rest = text.partition(" ")
        rest = rest.strip()
        if command in ("cursor-signal-prev", "cursor-signal-next"):
            names = self.signal_names()
            options = [None, *names]
            current = options.index(self.view.cursor_signal) if self.view.cursor_signal in options else 0
            step = -1 if command.endswith("prev") else 1
            self.view.cursor_signal = options[(current + step) % len(options)]
            self.view.update()
            return f"cursor follows {self.view.cursor_signal or 'any signal'}"
        if command not in COMMANDS:
            raise ValueError(f"Unknown command '{command}'. {PLAIN_HELP}")
        if command == "open":
            self.open_file(os.path.expanduser(rest))
            message = self.result_label.text()
            if message.startswith("Failed"):
                raise ValueError(message)
            return message
        if command == "clear":
            self.view.markers = []
            self.view.set_overlay(Overlay())
            self.view.set_data(self.waveform, self.signal_names())
            return "cleared"
        if command in ("left", "right"):
            if not self.view.narrow(command):
                raise ValueError("Search area cannot be narrowed further")
            start, end = self.view.view_range()
            return f"search area {start}..{end}"
        if command == "reset":
            self.view.reset_range()
            start, end = self.view.view_range()
            return f"search area {start}..{end}"
        if command in ("next", "prev"):
            time = self.view.move_cursor(1 if command == "next" else -1)
            if time is None:
                raise ValueError("No further signal change in the search area")
            return f"cursor at {time}"
        if command == "cursor":
            if rest.lstrip("-").isdigit():
                self.view.cursor_time = int(rest)
            elif rest == "any":
                self.view.cursor_signal = None
            else:
                if self.waveform is None:
                    raise ValueError("Load a file first")
                self.waveform.samples(rest)
                self.view.cursor_signal = rest
            self.view.update()
            return f"cursor {rest}"
        if command == "marker":
            if not rest:
                raise ValueError("Missing time")
            time = int(rest)
            self.view.markers.append((time, f"M{len(self.view.markers) + 1}"))
            self.view.set_overlay(self.view.overlay)
            return f"marker at {time}"
        if self.waveform is None:
            raise ValueError("Load a file first (open <path> or Ctrl+O)")

        analysis = COMMANDS[command][0]
        view_start, view_end = self.view.view_range()
        if command == "match":
            # Trailing start=/end= tokens are split off; the remainder is the expression.
            tokens = rest.split()
            trailing = []
            while tokens and tokens[-1].partition("=")[0] in ("start", "end") and "=" in tokens[-1]:
                trailing.insert(0, tokens.pop())
            expression = " ".join(tokens)
            signal, kwargs = "", parse_params(trailing, PARAMS[command])
            kwargs["condition"] = expression
        else:
            tokens = rest.split()
            if not tokens:
                raise ValueError("Missing signal name")
            signal, kwargs = tokens[0], parse_params(tokens[1:], PARAMS[command])
            self.waveform.samples(signal)  # validates the signal name
        kwargs.setdefault("start_time", view_start)
        kwargs.setdefault("end_time", view_end)
        result = run_analysis(self.waveform, analysis, signal, **kwargs)
        overlay = compute_overlay(self.waveform, analysis, signal, **kwargs)
        self.view.set_data(self.waveform, self.signal_names(), [signal] if signal else [])
        self.view.set_overlay(overlay)
        return f"{command} {signal or kwargs['condition']}: {result}"


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = WaveScopeWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
