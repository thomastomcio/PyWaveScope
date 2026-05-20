# PyWaveScope

HDL simulation waveform analysis library.

## Features

- Load WLF files (via `wlf2vcd` converter available in Questa/ModelSim tools)
- Count clock rising edges
- Find first assertion time of a signal
- Example CLI for quick waveform inspection

## Example

```bash
python examples/analyze_wlf.py path/to/sim.wlf --clock tb.clk --signal tb.valid
```
