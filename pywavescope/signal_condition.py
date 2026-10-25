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

    @classmethod
    def parse(cls, expression: str) -> tuple[SignalCondition, list[str]]:
        """Parse e.g. ``clk & ~rst | (bus=0101)``; return the condition and its signal names.

        ``name`` means ``name=1``; ``&``, ``|``, ``~`` and parentheses are supported.
        """
        tokens: list[str] = []
        word = ""
        for char in expression:
            if char in "&|~()" or char.isspace():
                if word:
                    tokens.append(word)
                    word = ""
                if not char.isspace():
                    tokens.append(char)
            else:
                word += char
        if word:
            tokens.append(word)
        if not tokens:
            raise ValueError("Empty condition")

        names: list[str] = []
        position = 0

        def peek() -> str | None:
            return tokens[position] if position < len(tokens) else None

        def take() -> str:
            nonlocal position
            token = peek()
            if token is None:
                raise ValueError("Unexpected end of condition")
            position += 1
            return token

        def parse_or() -> SignalCondition:
            result = parse_and()
            while peek() == "|":
                take()
                result = result | parse_and()
            return result

        def parse_and() -> SignalCondition:
            result = parse_unary()
            while peek() == "&":
                take()
                result = result & parse_unary()
            return result

        def parse_unary() -> SignalCondition:
            token = take()
            if token == "~":
                return ~parse_unary()
            if token == "(":
                result = parse_or()
                if take() != ")":
                    raise ValueError("Expected ')'")
                return result
            if token in ("&", "|", ")"):
                raise ValueError(f"Unexpected '{token}'")
            name, _, value = token.partition("=")
            names.append(name)
            return cls.signal(name, value or "1")

        condition = parse_or()
        if position != len(tokens):
            raise ValueError(f"Unexpected '{tokens[position]}'")
        return condition, names
