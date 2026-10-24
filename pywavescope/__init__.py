"""PyWaveScope public API."""

from .analyzer import (
    count_falling_edges,
    count_rising_edges,
    count_signal_edges_between,
    find_events_that_match_condition,
    first_assertion_time,
    nth_assertion_time,
    nth_deassertion_time,
)
from .signal_analysis import SignalAnalysis
from .signal_condition import SignalCondition
from .signal_sample import SignalSample
from .vcd_parser import parse_vcd
from .waveform import Waveform
from .wlf import load_wlf

__all__ = [
    "SignalAnalysis",
    "SignalCondition",
    "SignalSample",
    "Waveform",
    "count_falling_edges",
    "count_rising_edges",
    "count_signal_edges_between",
    "find_events_that_match_condition",
    "first_assertion_time",
    "nth_assertion_time",
    "nth_deassertion_time",
    "parse_vcd",
    "load_wlf",
]
