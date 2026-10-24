#!/usr/bin/env python3
"""Stand-in for ``wlf2vcd`` for demos: writes data/example.vcd to the output path.

Usage (same argument order load_wlf tries first): fake_wlf2vcd.py <in.wlf> <out.vcd>
"""

import shutil
import sys
from pathlib import Path

if len(sys.argv) != 3:
    sys.exit("usage: fake_wlf2vcd.py <in.wlf> <out.vcd>")

shutil.copyfile(Path(__file__).parent / "data" / "example.vcd", sys.argv[2])
