"""SignalSample class."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalSample:
    time: int
    value: str
