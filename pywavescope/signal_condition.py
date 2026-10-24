"""SignalCondition class."""

from __future__ import annotations

from collections.abc import Callable

from .waveform import Waveform


class SignalCondition:
    """Composable logic condition over one or more signals.

    Conditions are combined with ``&`` (and), ``|`` (or) and ``~`` (not)
    and evaluated against a waveform at a given point in time, e.g.::

        condition = SignalCondition.signal("clk") & ~SignalCondition.signal("rst")
    """

    def __init__(self, evaluator: Callable[[Waveform, int], bool]) -> None:
        self._evaluator = evaluator

    def evaluate(self, waveform: Waveform, time: int) -> bool:
        """Return whether the condition holds at ``time``."""
        return self._evaluator(waveform, time)

    def __and__(self, other: SignalCondition) -> SignalCondition:
        return SignalCondition(
            lambda waveform, time: self.evaluate(waveform, time) and other.evaluate(waveform, time)
        )

    def __or__(self, other: SignalCondition) -> SignalCondition:
        return SignalCondition(
            lambda waveform, time: self.evaluate(waveform, time) or other.evaluate(waveform, time)
        )

    def __invert__(self) -> SignalCondition:
        return SignalCondition(lambda waveform, time: not self.evaluate(waveform, time))

    @classmethod
    def signal(cls, name: str, value: str = "1") -> SignalCondition:
        """Condition that holds while the signal ``name`` equals ``value``."""
        return cls(lambda waveform, time: waveform.value_at(name, time) == value)
