"""WLF loader utilities."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .analyzer import Waveform, parse_vcd


class WLFConversionError(RuntimeError):
    """Raised when WLF-to-VCD conversion fails."""


def load_wlf(path: str | Path, *, converter: str = "wlf2vcd") -> Waveform:
    wlf_path = Path(path)
    if not wlf_path.exists():
        raise FileNotFoundError(f"WLF file not found: {wlf_path}")

    if shutil.which(converter) is None:
        raise WLFConversionError(
            f"'{converter}' command is required to parse WLF files. "
            "Install Questa/ModelSim tools or provide a converter available in PATH."
        )

    with tempfile.NamedTemporaryFile(suffix=".vcd", delete=False) as temp_file:
        vcd_path = Path(temp_file.name)

    conversion_commands = [
        [converter, str(wlf_path), str(vcd_path)],
        [converter, "-o", str(vcd_path), str(wlf_path)],
    ]

    try:
        last_error: Exception | None = None
        for command in conversion_commands:
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                return parse_vcd(vcd_path)
            except subprocess.CalledProcessError as error:
                last_error = error

        raise WLFConversionError(
            f"Unable to convert WLF file '{wlf_path}' to VCD with '{converter}'."
        ) from last_error
    finally:
        vcd_path.unlink(missing_ok=True)
