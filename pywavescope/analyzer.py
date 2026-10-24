"""Backward-compatible facade; each class now lives in its own module."""

from __future__ import annotations

from .signal_analysis import SignalAnalysis
from .signal_condition import SignalCondition
from .signal_sample import SignalSample
from .vcd_parser import parse_vcd
from .waveform import Waveform

count_rising_edges = SignalAnalysis.count_rising_edges
count_falling_edges = SignalAnalysis.count_falling_edges
first_assertion_time = SignalAnalysis.first_assertion_time
nth_assertion_time = SignalAnalysis.nth_assertion_time
nth_deassertion_time = SignalAnalysis.nth_deassertion_time
count_signal_edges_between = SignalAnalysis.count_signal_edges_between
find_events_that_match_condition = SignalAnalysis.find_events_that_match_condition

__all__ = [
    "SignalAnalysis",
    "SignalCondition",
    "SignalSample",
    "Waveform",
    "parse_vcd",
    "count_rising_edges",
    "count_falling_edges",
    "first_assertion_time",
    "nth_assertion_time",
    "nth_deassertion_time",
    "count_signal_edges_between",
    "find_events_that_match_condition",
]
