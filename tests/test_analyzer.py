import tempfile
import unittest
from pathlib import Path

from pywavescope import Waveform, SignalSample, count_rising_edges, first_assertion_time, parse_vcd


class AnalyzerTests(unittest.TestCase):
    def test_count_rising_edges(self):
        waveform = Waveform(
            {
                "tb.clk": [
                    SignalSample(0, "0"),
                    SignalSample(5, "1"),
                    SignalSample(10, "0"),
                    SignalSample(15, "1"),
                    SignalSample(20, "0"),
                ]
            }
        )

        self.assertEqual(count_rising_edges(waveform, "tb.clk"), 2)

    def test_first_assertion_time(self):
        waveform = Waveform(
            {
                "tb.valid": [
                    SignalSample(0, "0"),
                    SignalSample(12, "1"),
                    SignalSample(20, "1"),
                ]
            }
        )

        self.assertEqual(first_assertion_time(waveform, "tb.valid"), 12)
        self.assertIsNone(first_assertion_time(waveform, "tb.valid", asserted_value="x"))

    def test_parse_vcd(self):
        content = """$timescale 1ns $end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 1 \" valid $end
$upscope $end
$enddefinitions $end
#0
0!
0\"
#5
1!
#10
1\"
#15
0!
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.vcd"
            path.write_text(content, encoding="utf-8")

            waveform = parse_vcd(path)

            self.assertIn("tb.clk", waveform.signals)
            self.assertIn("tb.valid", waveform.signals)
            self.assertEqual(first_assertion_time(waveform, "tb.valid"), 10)


if __name__ == "__main__":
    unittest.main()
