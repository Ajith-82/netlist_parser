import os
import subprocess
import sys
import tempfile
import unittest

from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer
from netlist_parser.dedupe import remove_duplicate_subckts, verify_dedupe

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NETLIST = (
    "* header comment\n"                              # 1
    ".subckt NAND2 a b y\n"                           # 2
    "M1 y a b b nch\n"                                # 3
    "+ W=1u L=1u\n"                                   # 4
    ".ends NAND2\n"                                   # 5
    "* banner for INV\n"                              # 6
    ".subckt INV a y\n"                               # 7
    "R1 a y 1k\n"                                     # 8
    ".ends\n"                                         # 9
    "\n"                                              # 10
    ".SUBCKT nand2 a b y\n"                           # 11  identical to line 2
    "M1 y a b b nch W=1u L=1u\n"                      # 12
    ".ENDS\n"                                         # 13
    ".subckt INV a y\n"                               # 14  conflicts with line 7
    "R1 a y 2k   $ different value\n"                 # 15
    ".ends\n"                                         # 16
    "X1 1 2 3 NAND2\n"                                # 17
    "X2 3 4 INV\n"                                    # 18
)


def run(content, keep=None, filename="top.sp"):
    circuit = SpiceParser(num_threads=1).parse(content, filename=filename)
    analyzer = NetlistAnalyzer(circuit)
    result = remove_duplicate_subckts(analyzer, filename, content, keep=keep)
    cleaned = verify_dedupe(circuit, result, filename)
    return result, cleaned


class TestRemoveDuplicates(unittest.TestCase):
    def test_default_removes_identical_only(self):
        result, cleaned = run(NETLIST)
        self.assertEqual([(s.name, s.source_line) for s in result.removed],
                         [("NAND2", 2)])
        self.assertEqual([d.name for d in result.unresolved], ["INV"])
        lines = NETLIST.splitlines(keepends=True)
        self.assertEqual(result.text, "".join(lines[:1] + lines[5:]))
        dups = NetlistAnalyzer(cleaned).get_duplicate_subckts()
        self.assertEqual([d.name for d in dups], ["INV"])

    def test_keep_last(self):
        result, cleaned = run(NETLIST, keep="last")
        self.assertEqual(sorted((s.name, s.source_line) for s in result.removed),
                         [("INV", 7), ("NAND2", 2)])
        self.assertEqual(result.unresolved, [])
        self.assertEqual(NetlistAnalyzer(cleaned).get_duplicate_subckts(), [])
        inv = [s for s in cleaned.subcircuits if s.name == "INV"][0]
        self.assertEqual(inv.components[0].value, "2k")
        self.assertIn("* banner for INV\n", result.text)
        self.assertIn("$ different value", result.text)

    def test_keep_first(self):
        result, cleaned = run(NETLIST, keep="first")
        self.assertEqual(sorted((s.name, s.source_line) for s in result.removed),
                         [("INV", 14), ("nand2", 11)])
        inv = [s for s in cleaned.subcircuits if s.name == "INV"][0]
        self.assertEqual(inv.components[0].value, "1k")

    def test_no_duplicates_leaves_text_untouched(self):
        content = ".subckt A 1 2\nR1 1 2 1k\n.ends\nX1 1 2 A\n"
        result, _ = run(content)
        self.assertEqual(result.removed, [])
        self.assertEqual(result.text, content)

    def test_crlf_line_endings_are_preserved(self):
        content = NETLIST.replace("\n", "\r\n")
        result, _ = run(content, keep="last")
        self.assertNotIn("\n", result.text.replace("\r\n", ""))

    def test_three_copies(self):
        block = ".subckt A 1 2\nR1 1 2 1k\n.ends\n"
        result, cleaned = run("* t\n" + block * 3 + "X1 1 2 A\n")
        self.assertEqual(len(result.removed), 2)
        self.assertEqual(result.text, "* t\n" + block + "X1 1 2 A\n")


class TestRemoveDuplicatesCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", newline="") as f:
            f.write(content)
        return path

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "netlist_parser.cli", *args],
            capture_output=True, text=True, cwd=REPO)

    def test_writes_cleaned_file(self):
        top = self._write("top.sp", NETLIST)
        out = os.path.join(self.tmp.name, "clean.sp")
        result = self._run(top, "--remove-duplicates", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Removed 1 duplicate definition", result.stdout)
        self.assertIn(f"NAND2 ({top}:2)", result.stdout)
        self.assertIn("INV", result.stdout)
        self.assertIn("--keep", result.stdout)
        with open(top, newline="") as f:
            self.assertEqual(f.read(), NETLIST)  # input untouched
        check = self._run(out, "--check-duplicates")
        self.assertNotIn("NAND2", check.stdout)
        self.assertIn("INV (2 definitions, CONFLICTING", check.stdout)

    def test_keep_resolves_conflicts(self):
        top = self._write("top.sp", NETLIST)
        out = os.path.join(self.tmp.name, "clean.sp")
        result = self._run(top, "--remove-duplicates", out, "--keep", "last")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        check = self._run(out, "--check-duplicates")
        self.assertIn("No duplicate subcircuits found.", check.stdout)

    def test_refuses_to_overwrite(self):
        top = self._write("top.sp", NETLIST)
        existing = self._write("exists.sp", "keep me\n")
        for target in (top, existing):
            result = self._run(top, "--remove-duplicates", target)
            self.assertEqual(result.returncode, 1)
        with open(existing) as f:
            self.assertEqual(f.read(), "keep me\n")
        with open(top, newline="") as f:
            self.assertEqual(f.read(), NETLIST)

    def test_nothing_to_remove_writes_nothing(self):
        top = self._write("top.sp", ".subckt A 1 2\nR1 1 2 1k\n.ends\n")
        out = os.path.join(self.tmp.name, "clean.sp")
        result = self._run(top, "--remove-duplicates", out)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(out))
        self.assertIn("nothing written", result.stdout)

    def test_copy_in_include_is_kept_and_main_copy_removed(self):
        block = ".subckt cell a b\nR1 a b 1k\n.ends\n"
        self._write("lib.sp", block)
        top = self._write("top.sp", "* top\n.include 'lib.sp'\n" + block
                          + "X1 1 2 cell\n")
        out = os.path.join(self.tmp.name, "clean.sp")
        result = self._run(top, "--remove-duplicates", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(out) as f:
            self.assertEqual(f.read(), "* top\n.include 'lib.sp'\nX1 1 2 cell\n")

    def test_duplicates_only_in_includes_are_reported(self):
        self._write("a.sp", ".subckt cell a b\nR1 a b 1k\n.ends\n")
        self._write("b.sp", ".subckt cell a b\nR1 a b 2k\n.ends\n")
        top = self._write("top.sp", "* top\n.include 'a.sp'\n.include 'b.sp'\n")
        out = os.path.join(self.tmp.name, "clean.sp")
        result = self._run(top, "--remove-duplicates", out, "--keep", "last")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(out))
        self.assertIn("included files", result.stdout)
        self.assertIn("a.sp:1", result.stdout)


if __name__ == "__main__":
    unittest.main()
