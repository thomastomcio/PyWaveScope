"""Waveform class."""

from __future__ import annotations

from dataclasses import dataclass

from .signal_sample import SignalSample


@dataclass
class Waveform:
    signals: dict[str, list[SignalSample]]

    def samples(self, signal: str) -> list[SignalSample]:
        if signal not in self.signals:
            available = ", ".join(sorted(self.signals))
            raise KeyError(f"Unknown signal '{signal}'. Available signals: {available}")
        return self.signals[signal]

    def value_at(self, signal: str, time: int) -> str | None:
        """Return the value of ``signal`` at ``time`` (None before the first sample)."""
        value: str | None = None
        for sample in self.samples(signal):
            if sample.time > time:
                break
            value = sample.value
        return value
