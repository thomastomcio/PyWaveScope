#!/usr/bin/env python3
"""Example CLI for WLF waveform analysis."""

from __future__ import annotations

import argparse

from pywavescope import count_rising_edges, first_assertion_time, load_wlf


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze HDL waveforms from WLF files")
    parser.add_argument("wlf_path", help="Path to WLF file")
    parser.add_argument("--clock", required=True, help="Clock signal name")
    parser.add_argument("--signal", required=True, help="Signal to check first assertion")
    parser.add_argument("--asserted-value", default="1", help="Value considered as assertion (default: 1)")
    parser.add_argument("--start-time", type=int, default=0, help="Start analysis from this simulation time")
    args = parser.parse_args()

    waveform = load_wlf(args.wlf_path)
    clock_count = count_rising_edges(waveform, args.clock, start_time=args.start_time)
    first_assert = first_assertion_time(
        waveform,
        args.signal,
        asserted_value=args.asserted_value,
        start_time=args.start_time,
    )

    print(f"Clock rising edges ({args.clock}): {clock_count}")
    if first_assert is None:
        print(f"First assertion ({args.signal} == {args.asserted_value}): not found")
    else:
        print(f"First assertion ({args.signal} == {args.asserted_value}): t={first_assert}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
