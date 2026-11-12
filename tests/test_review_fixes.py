import os
import tempfile
import unittest

from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer


def parse(content):
    return SpiceParser(num_threads=1).parse(content)


class TestTitleLine(unittest.TestCase):
    def test_prose_title_is_not_a_device(self):
        circuit = parse(
            "CMOS inverter testbench\n"
            ".subckt top a b\nM1 a b a a nch\n.ends\n"
        )
        self.assertEqual(circuit.components, [])
        stats = NetlistAnalyzer(circuit).get_hierarchical_stats()
        self.assertEqual(stats, {"Mosfet": 1})

    def test_valid_first_line_device_is_kept(self):
        circuit = parse("R1 a b 1k\nC1 a 0 1p\n")
        self.assertEqual([c.name for c in circuit.components], ["R1", "C1"])

    def test_first_line_directive_is_kept(self):
        circuit = parse(".subckt top a b\nR1 a b 1k\n.ends\n")
        self.assertEqual(len(circuit.subcircuits), 1)

    def test_title_only_applies_to_top_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "inc.sp"), "w") as f:
                f.write("M1 d g s b nch\n")
            top = os.path.join(tmp, "top.sp")
            with open(top, "w") as f:
                f.write("* top\n.include 'inc.sp'\n")
            circuit = SpiceParser(num_threads=1).parse_file(top)
            self.assertEqual(len(circuit.components), 1)


class TestLibSections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, content):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    LIB = (
        "* corner library\n"
        ".lib tt\n"
        ".model nch nmos level=1\n"
        ".subckt cell a b\nR1 a b 1k\n.ends\n"
        ".endl tt\n"
        ".lib ff\n"
        ".model nch nmos level=2\n"
        ".subckt cell a b\nR1 a b 2k\n.ends\n"
        ".endl ff\n"
    )

    def test_only_requested_section_is_included(self):
        self._write("models.lib", self.LIB)
        top = self._write("top.sp", "* top\n.lib 'models.lib' TT\nX1 1 2 cell\n")
        for threads in (1, 4):
            circuit = SpiceParser(num_threads=threads).parse_file(top)
            self.assertEqual(len(circuit.subcircuits), 1)
            self.assertEqual(circuit.subcircuits[0].components[0].value, "1k")
            self.assertEqual(len(circuit.models), 1)
            self.assertEqual(circuit.failed_includes, [])

    def test_section_marker_is_not_a_missing_include(self):
        top = self._write("top.sp", self.LIB)
        circuit = SpiceParser(num_threads=1).parse_file(top)
        self.assertEqual(circuit.failed_includes, [])
        self.assertEqual(len(circuit.subcircuits), 2)

    def test_same_file_two_sections_and_self_reference(self):
        self._write(
            "models.lib",
            ".lib tt\n.lib 'models.lib' mos\n.endl\n"
            ".lib mos\n.subckt m a b\nR1 a b 1k\n.ends\n.endl\n"
            ".lib res\n.subckt r a b\nR1 a b 1k\n.ends\n.endl\n"
            ".lib unused\n.subckt u a b\nR1 a b 1k\n.ends\n.endl\n",
        )
        top = self._write(
            "top.sp", "* top\n.lib 'models.lib' tt\n.lib 'models.lib' res\n")
        circuit = SpiceParser(num_threads=1).parse_file(top)
        self.assertEqual(sorted(s.name for s in circuit.subcircuits), ["m", "r"])

    def test_missing_section_is_reported(self):
        self._write("models.lib", self.LIB)
        top = self._write("top.sp", "* top\n.lib 'models.lib' ss\n")
        circuit = SpiceParser(num_threads=1).parse_file(top)
        self.assertEqual(len(circuit.subcircuits), 0)
        self.assertEqual(len(circuit.failed_includes), 1)
        self.assertIn("ss", circuit.failed_includes[0])

    def test_lib_with_only_a_file_includes_whole_file(self):
        self._write("cells.sp", ".subckt cell a b\nR1 a b 1k\n.ends\n")
        top = self._write("top.sp", "* top\n.lib 'cells.sp'\n")
        circuit = SpiceParser(num_threads=1).parse_file(top)
        self.assertEqual(len(circuit.subcircuits), 1)


class TestRecursiveSubckts(unittest.TestCase):
    SELF = ".subckt a 1 2\nX1 1 2 a\nR1 1 2 1k\n.ends\n\nX0 1 2 a\n"
    CYCLE = (
        ".subckt a 1 2\nX1 1 2 b\n.ends\n"
        ".subckt b 1 2\nX1 1 2 a\nR1 1 2 1k\n.ends\n"
        ".subckt ok 1 2\nR1 1 2 1k\n.ends\n"
        "\nX0 1 2 a\nX9 1 2 ok\n"
    )

    def test_flatten_terminates(self):
        for content in (self.SELF, self.CYCLE):
            analyzer = NetlistAnalyzer(parse(content))
            flat = analyzer.flatten()
            self.assertTrue(flat.components)
            self.assertTrue(analyzer.get_hierarchical_stats())

    def test_recursive_subckts_are_reported(self):
        self.assertEqual(
            NetlistAnalyzer(parse(self.SELF)).find_recursive_subckts(), ["a"])
        self.assertEqual(
            NetlistAnalyzer(parse(self.CYCLE)).find_recursive_subckts(),
            ["a", "b"])
        self.assertEqual(
            NetlistAnalyzer(parse(".subckt a 1 2\nR1 1 2 1k\n.ends\n"))
            .find_recursive_subckts(), [])

    def test_tree_terminates(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            NetlistAnalyzer(parse(self.CYCLE)).print_hierarchy()
        self.assertIn("[recursive]", buf.getvalue())


class TestCaseInsensitiveSubcktNames(unittest.TestCase):
    NETLIST = (
        ".subckt INV a y\nM1 y a 0 0 nch\n.ends\n"
        ".subckt Top a y\nX1 a y inv\n.ends\n"
    )

    def test_instance_resolves_regardless_of_case(self):
        analyzer = NetlistAnalyzer(parse(self.NETLIST))
        self.assertEqual(analyzer.get_top_cells(), ["Top"])
        self.assertEqual(analyzer.get_transistor_count(), 1)
        self.assertEqual(analyzer.unresolved_subckts, set())

    def test_top_cell_name_regardless_of_case(self):
        analyzer = NetlistAnalyzer(parse(self.NETLIST), top_cell_name="TOP")
        self.assertEqual(analyzer.get_transistor_count(), 1)

    def test_case_sensitive_mode(self):
        analyzer = NetlistAnalyzer(parse(self.NETLIST), case_sensitive=True)
        self.assertEqual(analyzer.get_top_cells(), ["INV", "Top"])
        analyzer = NetlistAnalyzer(parse(self.NETLIST), top_cell_name="Top",
                                   case_sensitive=True)
        self.assertEqual(analyzer.get_transistor_count(), 0)
        self.assertEqual(analyzer.unresolved_subckts, {"inv"})
        with self.assertRaises(ValueError):
            NetlistAnalyzer(parse(self.NETLIST), top_cell_name="TOP",
                            case_sensitive=True)


if __name__ == "__main__":
    unittest.main()
