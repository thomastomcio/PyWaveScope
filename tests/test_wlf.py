import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pywavescope.wlf import WLFConversionError, load_wlf


class WLFTests(unittest.TestCase):
    def test_missing_wlf_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_wlf("/does/not/exist.wlf")

    @patch("pywavescope.wlf.shutil.which", return_value=None)
    def test_missing_converter_raises(self, _):
        with tempfile.NamedTemporaryFile(suffix=".wlf") as temp:
            with self.assertRaises(WLFConversionError):
                load_wlf(Path(temp.name))


if __name__ == "__main__":
    unittest.main()
