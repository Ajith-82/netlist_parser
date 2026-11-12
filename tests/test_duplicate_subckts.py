import os
import subprocess
import sys
import tempfile
import unittest

from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer


class TestDuplicateSubckts(unittest.TestCase):
    def _analyze(self, content, filename="top.sp"):
        circuit = SpiceParser().parse(content, filename=filename)
        return NetlistAnalyzer(circuit)

    def test_no_duplicates(self):
        analyzer = self._analyze(
            ".subckt A 1 2\nR1 1 2 1k\n.ends\n"
            ".subckt B 1 2\nR1 1 2 1k\n.ends\n"
        )
        self.assertEqual(analyzer.get_duplicate_subckts(), [])

    def test_conflicting_duplicate(self):
        analyzer = self._analyze(
            ".subckt INV in out\n"      # line 1
            "R1 in out 1k\n"
            ".ends\n"
            ".subckt INV in out\n"      # line 4
            "R1 in out 2k\n"
            ".ends\n"
        )
        dups = analyzer.get_duplicate_subckts()
        self.assertEqual(len(dups), 1)
        dup = dups[0]
        self.assertEqual(dup.name, "INV")
        self.assertFalse(dup.identical)
        self.assertEqual(
            [(d.source_file, d.source_line) for d in dup.definitions],
            [("top.sp", 1), ("top.sp", 4)],
        )

    def test_identical_duplicate(self):
        analyzer = self._analyze(
            ".subckt NAND2 a b y\nM1 y a b b nch W=1u L=1u\n.ends\n"
            "\n* a comment shifts the line numbers\n"
            ".subckt NAND2 a b y\nM1 y a b b nch W=1u L=1u\n.ends\n"
        )
        dups = analyzer.get_duplicate_subckts()
        self.assertEqual(len(dups), 1)
        self.assertTrue(dups[0].identical)

    def test_different_ports_conflict(self):
        analyzer = self._analyze(
            ".subckt BUF a y\nR1 a y 1k\n.ends\n"
            ".subckt BUF y a\nR1 a y 1k\n.ends\n"
        )
        self.assertFalse(analyzer.get_duplicate_subckts()[0].identical)

    def test_names_differing_only_in_case_are_duplicates(self):
        content = (
            ".subckt INV a y\nR1 a y 1k\n.ends\n"
            ".subckt inv a y\nR1 a y 2k\n.ends\n"
        )
        dups = self._analyze(content).get_duplicate_subckts()
        self.assertEqual([d.name for d in dups], ["INV"])
        self.assertEqual([d.name for d in dups[0].definitions], ["INV", "inv"])

        circuit = SpiceParser().parse(content)
        analyzer = NetlistAnalyzer(circuit, case_sensitive=True)
        self.assertEqual(analyzer.get_duplicate_subckts(), [])

    def test_three_definitions_sorted_by_name(self):
        analyzer = self._analyze(
            ".subckt Z a y\nR1 a y 1k\n.ends\n"
            ".subckt A a y\nR1 a y 1k\n.ends\n"
            ".subckt Z a y\nR1 a y 1k\n.ends\n"
            ".subckt A a y\nR1 a y 1k\n.ends\n"
            ".subckt Z a y\nR1 a y 3k\n.ends\n"
        )
        dups = analyzer.get_duplicate_subckts()
        self.assertEqual([d.name for d in dups], ["A", "Z"])
        self.assertTrue(dups[0].identical)
        self.assertEqual(len(dups[1].definitions), 3)
        self.assertFalse(dups[1].identical)


class TestDuplicateSubcktsCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def _run(self, path, *flags):
        return subprocess.run(
            [sys.executable, "-m", "netlist_parser.cli", path, *flags],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

    def test_duplicate_across_include(self):
        lib = self._write("lib.sp", ".subckt INV a y\nR1 a y 2k\n.ends\n")
        top = self._write(
            "top.sp",
            ".include 'lib.sp'\n"
            ".subckt INV a y\nR1 a y 1k\n.ends\n"
            "X1 1 2 INV\n",
        )
        result = self._run(top, "--check-duplicates")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--- Duplicate Subcircuits ---", result.stdout)
        self.assertIn("INV (2 definitions, CONFLICTING - last one is used)",
                      result.stdout)
        self.assertIn(f"  - {lib}:1", result.stdout)
        self.assertIn(f"  - {top}:2", result.stdout)
        self.assertIn("Total: 1 duplicated subcircuit name", result.stdout)

    def test_check_reports_none(self):
        top = self._write("top.sp", ".subckt INV a y\nR1 a y 1k\n.ends\n")
        result = self._run(top, "--check-duplicates")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No duplicate subcircuits found.", result.stdout)

    def test_automatic_warning(self):
        top = self._write(
            "top.sp",
            ".subckt INV a y\nR1 a y 1k\n.ends\n"
            ".subckt INV a y\nR1 a y 2k\n.ends\n"
            "X1 1 2 INV\n",
        )
        result = self._run(top, "--stats")
        self.assertEqual(result.returncode, 0)
        self.assertIn("[WARNING] The following subcircuits are defined more "
                      "than once", result.stdout)
        self.assertIn("INV", result.stdout)

        # No warning for options that do not depend on the definition used
        result = self._run(top, "--list-top-cells")
        self.assertNotIn("defined more than once", result.stdout)


if __name__ == "__main__":
    unittest.main()
