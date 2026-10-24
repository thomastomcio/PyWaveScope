"""SignalAnalysis class wrapping all signal analysis operations."""

from __future__ import annotations

from collections.abc import Callable

from .waveform import Waveform


class SignalAnalysis:
    """Signal analysis operations over a :class:`Waveform`."""

    @staticmethod
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

    @staticmethod
    def count_falling_edges(waveform: Waveform, signal: str, *, start_time: int = 0) -> int:
        count = 0
        previous: str | None = None

        for sample in waveform.samples(signal):
            if sample.time < start_time:
                previous = sample.value
                continue

            if previous is not None and previous != "0" and sample.value == "0":
                count += 1
            previous = sample.value

        return count

    @staticmethod
    def nth_assertion_time(
        waveform: Waveform,
        signal: str,
        *,
        asserted_value: str = "1",
        start_time: int = 0,
        n: int = 1,
    ) -> int | None:
        count = 0
        for sample in waveform.samples(signal):
            if sample.time < start_time:
                continue
            if sample.value == asserted_value:
                count += 1
                if count == n:
                    return sample.time
        return None

    @staticmethod
    def first_assertion_time(
        waveform: Waveform,
        signal: str,
        *,
        asserted_value: str = "1",
        start_time: int = 0,
    ) -> int | None:
        return SignalAnalysis.nth_assertion_time(
            waveform, signal, asserted_value=asserted_value, start_time=start_time, n=1
        )

    @staticmethod
    def nth_deassertion_time(
        waveform: Waveform,
        signal: str,
        *,
        deasserted_value: str = "0",
        start_time: int = 0,
        n: int = 1,
    ) -> int | None:
        count = 0
        for sample in waveform.samples(signal):
            if sample.time < start_time:
                continue
            if sample.value == deasserted_value:
                count += 1
                if count == n:
                    return sample.time
        return None

    @staticmethod
    def count_signal_edges_between(
        waveform: Waveform,
        signal: str,
        *,
        start_time: int = 0,
        end_time: int | None = None,
        asserted_value: str = "1",
    ) -> int:
        count = 0
        previous: str | None = None

        for sample in waveform.samples(signal):
            if sample.time < start_time:
                previous = sample.value
                continue
            if end_time is not None and sample.time > end_time:
                break

            if previous is not None and previous != asserted_value and sample.value == asserted_value:
                count += 1
            previous = sample.value

        return count

    @staticmethod
    def find_events_that_match_condition(
        waveform: Waveform,
        signal: str,
        *,
        start_time: int = 0,
        end_time: int | None = None,
        condition: Callable[[str], bool],
    ) -> list[int]:
        events: list[int] = []
        for sample in waveform.samples(signal):
            if sample.time < start_time:
                continue
            if end_time is not None and sample.time > end_time:
                break
            if condition(sample.value):
                events.append(sample.time)
        return events
