"""Waveform parsing and signal analysis utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SignalSample:
    time: int
    value: str


@dataclass
class Waveform:
    signals: dict[str, list[SignalSample]]

    def samples(self, signal: str) -> list[SignalSample]:
        if signal not in self.signals:
            available = ", ".join(sorted(self.signals))
            raise KeyError(f"Unknown signal '{signal}'. Available signals: {available}")
        return self.signals[signal]


def parse_vcd(path: str | Path) -> Waveform:
    symbol_to_signal: dict[str, str] = {}
    scope_stack: list[str] = []
    signal_values: dict[str, list[SignalSample]] = {}

    with Path(path).open("r", encoding="utf-8") as vcd:
        in_definitions = True
        current_time = 0

        for raw_line in vcd:
            line = raw_line.strip()
            if not line:
                continue

            if in_definitions:
                parts = line.split()
                if line.startswith("$scope"):
                    if len(parts) >= 3:
                        scope_stack.append(parts[2])
                elif line.startswith("$upscope"):
                    if scope_stack:
                        scope_stack.pop()
                elif line.startswith("$var"):
                    if len(parts) >= 5:
                        symbol = parts[3]
                        signal_name = parts[4]
                        full_name = ".".join(scope_stack + [signal_name]) if scope_stack else signal_name
                        symbol_to_signal[symbol] = full_name
                        signal_values.setdefault(full_name, [])
                elif line.startswith("$enddefinitions"):
                    in_definitions = False
                continue

            if line.startswith("#"):
                current_time = int(line[1:])
                continue

            if line[0] in {"0", "1", "x", "z"} and len(line) >= 2:
                value = line[0]
                symbol = line[1:]
            elif line.startswith("b"):
                parts = line.split()
                if len(parts) != 2:
                    continue
                value = parts[0][1:]
                symbol = parts[1]
            else:
                continue

            signal = symbol_to_signal.get(symbol)
            if signal is None:
                continue
            signal_values[signal].append(SignalSample(time=current_time, value=value))

    return Waveform(signal_values)


def count_rising_edges(waveform: Waveform, signal: str, *, start_time: int = 0) -> int:
    count = 0
    previous: str | None = None

    for sample in waveform.samples(signal):
        if sample.time < start_time:
            previous = sample.value
            continue

        if previous is not None and previous != "1" and sample.value == "1":
            count += 1
        previous = sample.value

    return count


def first_assertion_time(
    waveform: Waveform,
    signal: str,
    *,
    asserted_value: str = "1",
    start_time: int = 0,
) -> int | None:
    for sample in waveform.samples(signal):
        if sample.time >= start_time and sample.value == asserted_value:
            return sample.time
    return None
