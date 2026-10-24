"""PyQt6 GUI for PyWaveScope."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Qt's bundled GTK3 theme plugin aborts on GNOME versions whose xsettings schema
# lacks the 'antialiasing' key; the generic theme avoids it.
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)

from .signal_analysis import SignalAnalysis
from .vcd_parser import parse_vcd
from .waveform import Waveform
from .wlf import WLFConversionError, load_wlf

ANALYSES = (
    "Count rising edges",
    "Count falling edges",
    "Nth assertion time",
    "Nth deassertion time",
    "Edges between times",
)


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
) -> str:
    """Run the named analysis and return a human-readable result."""
    if analysis == "Count rising edges":
        return str(SignalAnalysis.count_rising_edges(waveform, signal, start_time=start_time))
    if analysis == "Count falling edges":
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
    return "not found" if result is None else str(result)


class WaveformView(QWidget):
    """Widget that draws selected signals as digital traces."""

    ROW_HEIGHT = 40
    LABEL_WIDTH = 140
    MARGIN = 10

    def __init__(self) -> None:
        super().__init__()
        self.waveform: Waveform | None = None
        self.signals: list[str] = []
        self.setMinimumHeight(200)

    def set_data(self, waveform: Waveform | None, signals: list[str]) -> None:
        self.waveform = waveform
        self.signals = signals
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        if self.waveform is None or not self.signals:
            return

        max_time = (
            max((s.time for name in self.signals for s in self.waveform.samples(name)), default=0) or 1
        )
        scale = (self.width() - self.LABEL_WIDTH - 2 * self.MARGIN) / max_time

        def x_at(time: int) -> float:
            return self.LABEL_WIDTH + self.MARGIN + time * scale

        trace_pen = QPen(QColor("green"), 2)
        box_pen = QPen(QColor("blue"), 1)

        for row, name in enumerate(self.signals):
            high = row * self.ROW_HEIGHT + 12
            low = high + self.ROW_HEIGHT - 16
            painter.setPen(QPen(QColor("black")))
            painter.drawText(
                QRectF(4, high, self.LABEL_WIDTH - 8, low - high),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name,
            )
            samples = self.waveform.samples(name)
            for index, sample in enumerate(samples):
                x_start = x_at(sample.time)
                following = samples[index + 1] if index + 1 < len(samples) else None
                x_end = x_at(following.time) if following else x_at(max_time)
                if sample.value in ("0", "1"):
                    painter.setPen(trace_pen)
                    y = high if sample.value == "1" else low
                    painter.drawLine(int(x_start), int(y), int(x_end), int(y))
                    if following and following.value in ("0", "1") and following.value != sample.value:
                        painter.drawLine(int(x_end), int(high), int(x_end), int(low))
                else:
                    painter.setPen(box_pen)
                    painter.drawRect(QRectF(x_start, high, x_end - x_start, low - high))
                    painter.drawText(
                        QRectF(x_start, high, x_end - x_start, low - high),
                        Qt.AlignmentFlag.AlignCenter,
                        sample.value,
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

        toolbar = QHBoxLayout()
        open_button = QPushButton("Open VCD/WLF...")
        open_button.clicked.connect(self.open_file)
        self.file_label = QLabel("No file loaded")
        toolbar.addWidget(open_button)
        toolbar.addWidget(self.file_label, 1)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Signals (multi-select to plot)"))
        self.signal_list = QListWidget()
        self.signal_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.signal_list.itemSelectionChanged.connect(self.update_view)
        left_layout.addWidget(self.signal_list)
        splitter.addWidget(left)

        self.view = WaveformView()
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

        panel = QGroupBox("Analysis")
        panel_layout = QHBoxLayout(panel)
        self.analysis_box = QComboBox()
        self.analysis_box.addItems(ANALYSES)
        panel_layout.addWidget(self.analysis_box)

        self.start_edit = QLineEdit("0")
        self.end_edit = QLineEdit()
        self.value_edit = QLineEdit()
        self.n_edit = QLineEdit("1")
        for label, edit in (
            ("Start", self.start_edit),
            ("End", self.end_edit),
            ("Value", self.value_edit),
            ("N", self.n_edit),
        ):
            edit.setMaximumWidth(80)
            panel_layout.addWidget(QLabel(label))
            panel_layout.addWidget(edit)

        run_button = QPushButton("Run")
        run_button.clicked.connect(self.run_selected_analysis)
        panel_layout.addWidget(run_button)
        self.result_label = QLabel("Result: -")
        panel_layout.addWidget(self.result_label, 1)
        layout.addWidget(panel)

        self.setCentralWidget(central)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open waveform", "", "Waveform files (*.vcd *.wlf);;All files (*)"
        )
        if not path:
            return
        try:
            self.waveform = load_waveform(path)
        except (OSError, WLFConversionError, ValueError) as error:
            QMessageBox.critical(self, "PyWaveScope", f"Failed to load file:\n{error}")
            return
        self.file_label.setText(Path(path).name)
        self.signal_list.clear()
        self.signal_list.addItems(sorted(self.waveform.signals))
        self.update_view()

    def selected_signals(self) -> list[str]:
        return [item.text() for item in self.signal_list.selectedItems()]

    def update_view(self) -> None:
        self.view.set_data(self.waveform, self.selected_signals())

    def run_selected_analysis(self) -> None:
        signals = self.selected_signals()
        if self.waveform is None or not signals:
            QMessageBox.information(self, "PyWaveScope", "Load a file and select a signal first.")
            return
        try:
            end_text = self.end_edit.text().strip()
            result = run_analysis(
                self.waveform,
                self.analysis_box.currentText(),
                signals[0],
                start_time=int(self.start_edit.text() or 0),
                end_time=int(end_text) if end_text else None,
                value=self.value_edit.text().strip(),
                n=int(self.n_edit.text() or 1),
            )
        except ValueError as error:
            QMessageBox.critical(self, "PyWaveScope", f"Invalid input: {error}")
            return
        self.result_label.setText(f"Result ({signals[0]}): {result}")


def main() -> int:
    app = QApplication(sys.argv)
    window = WaveScopeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
