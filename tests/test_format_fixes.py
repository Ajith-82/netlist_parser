import unittest

from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer


def parse(content):
    # Leading comment keeps the first real line from being a title candidate
    return SpiceParser(num_threads=1).parse("* test\n" + content)


class TestPassiveModelThenValue(unittest.TestCase):
    def test_model_then_value(self):
        r = parse("R1 n1 n2 rmod 1k\n").components[0]
        self.assertEqual((r.nodes, r.model, r.value), (["n1", "n2"], "rmod", "1k"))

    def test_three_terminal_model_then_value(self):
        r = parse("R1 n1 n2 sub rmod 1k w=1u\n").components[0]
        self.assertEqual((r.nodes, r.model, r.value),
                         (["n1", "n2", "sub"], "rmod", "1k"))
        self.assertEqual(r.parameters, {"w": "1u"})

    def test_existing_forms_unchanged(self):
        r = parse("R1 n1 n2 1k\n").components[0]
        self.assertEqual((r.nodes, r.model, r.value), (["n1", "n2"], None, "1k"))
        r = parse("R1 n1 n2 sub rmod l=2u\n").components[0]
        self.assertEqual((r.nodes, r.model), (["n1", "n2", "sub"], "rmod"))
        r = parse("C1 n1 n2 cmod l=2u\n").components[0]
        self.assertEqual((r.nodes, r.model), (["n1", "n2"], "cmod"))


class TestGlobals(unittest.TestCase):
    BODY = ".subckt s a b\nR1 a VDD 1k\nR2 b local 1k\n.ends\nX1 1 2 s\n"

    def _flat_nodes(self, content, **kwargs):
        analyzer = NetlistAnalyzer(parse(content), **kwargs)
        return [c.nodes for c in analyzer.flatten().components]

    def test_spice_global(self):
        circuit = parse(".global VDD VSS\n" + self.BODY)
        self.assertEqual(circuit.globals, ["VDD", "VSS"])
        self.assertEqual(self._flat_nodes(".global VDD VSS\n" + self.BODY),
                         [["1", "VDD"], ["2", "X1.local"]])

    def test_cdl_global_with_types_and_commas(self):
        circuit = parse("*.GLOBAL VDD:P, gnd!:G\n" + self.BODY)
        self.assertEqual(circuit.globals, ["VDD", "gnd!"])
        self.assertEqual(self._flat_nodes("*.GLOBAL VDD:P\n" + self.BODY)[0],
                         ["1", "VDD"])

    def test_without_global_net_is_local(self):
        self.assertEqual(self._flat_nodes(self.BODY)[0], ["1", "X1.VDD"])

    def test_port_overrides_global(self):
        nodes = self._flat_nodes(
            ".global VDD\n.subckt s a VDD\nR1 a VDD 1k\n.ends\nX1 1 pwr s\n")
        self.assertEqual(nodes, [["1", "pwr"]])

    def test_global_case(self):
        content = ".global vdd\n" + self.BODY
        self.assertEqual(self._flat_nodes(content)[0], ["1", "vdd"])
        self.assertEqual(self._flat_nodes(content, case_sensitive=True)[0],
                         ["1", "X1.VDD"])

    def test_other_cdl_directives_stay_comments(self):
        circuit = parse("*.PININFO a:I b:O\n*.SCALE METER\nR1 a b 1k\n")
        self.assertEqual(len(circuit.components), 1)


class TestSpacedEquals(unittest.TestCase):
    def test_instance(self):
        x = parse(".subckt s a b\nR1 a b 1k\n.ends\nX1 1 2 s w = 1u l= 2u m =3\n"
                  ).components[0]
        self.assertEqual(x.subckt_name, "s")
        self.assertEqual(x.nodes, ["1", "2"])
        self.assertEqual(x.parameters, {"w": "1u", "l": "2u", "m": "3"})

    def test_param_and_quotes(self):
        circuit = parse(".param w = '1u + 2u'\nM1 d g s b nch W = w\n")
        self.assertEqual(circuit.parameters, {"w": "1u + 2u"})
        self.assertEqual(circuit.components[0].parameters, {"W": "w"})


class TestFindModel(unittest.TestCase):
    def test_leaf_instances_are_found(self):
        analyzer = NetlistAnalyzer(parse(
            ".subckt top a b\nXM1 a b a a pmos_1p5 W=1u L=1u\n"
            "M2 a b a a nch\nX3 a b inner\n.ends\n"
            ".subckt inner a b\nR1 a b 1k\n.ends\n"))
        self.assertEqual(analyzer.get_all_models(), ["nch", "pmos_1p5"])
        self.assertEqual(analyzer.get_subckts_using_model("PMOS_1P5"), ["top"])
        self.assertEqual(analyzer.get_subckts_using_model("nch"), ["top"])
        self.assertEqual(analyzer.get_subckts_using_model("inner"), [])


class TestExtraTokens(unittest.TestCase):
    def test_all_extra_tokens_are_kept(self):
        m = parse("M1 d g s b nch W=1 a b c\n").components[0]
        self.assertEqual(m.parameters, {"W": "1", "extra": ["a", "b", "c"]})


class TestBjtTerminals(unittest.TestCase):
    def _q(self, line):
        q = parse(line + "\n").components[0]
        return q.nodes, q.model

    def test_three_and_four_terminals(self):
        self.assertEqual(self._q("Q1 c b e npn"), (["c", "b", "e"], "npn"))
        self.assertEqual(self._q("Q1 c b e npn 2"), (["c", "b", "e"], "npn"))
        self.assertEqual(self._q("Q1 c b e npn M=2 $EA=1"),
                         (["c", "b", "e"], "npn"))
        self.assertEqual(self._q("Q1 c b e sub npn"),
                         (["c", "b", "e", "sub"], "npn"))
        self.assertEqual(self._q("Q1 c b e sub npn 2 m=1"),
                         (["c", "b", "e", "sub"], "npn"))


class TestModelParens(unittest.TestCase):
    def test_parenthesised_parameters(self):
        for line in (".model nch nmos (level=1 vto=0.7)",
                     ".model nch nmos(level=1 vto=0.7)",
                     ".model nch nmos ( level = 1 vto=0.7 )",
                     ".model nch nmos level=1 vto=0.7"):
            model = parse(line + "\n").models[0]
            self.assertEqual(model.model_type, "nmos", line)
            self.assertEqual(model.parameters, {"level": "1", "vto": "0.7"}, line)


class TestSkippedElements(unittest.TestCase):
    def test_unsupported_elements_are_counted(self):
        circuit = parse("E1 1 2 3 4 10\nE2 1 2 3 4 10\nK1 L1 L2 0.9\nR1 1 2 1k\n")
        self.assertEqual(circuit.skipped_elements, {"E": 2, "K": 1})
        self.assertEqual(len(circuit.components), 1)


class TestMacro(unittest.TestCase):
    def test_macro_and_eom(self):
        circuit = parse(".MACRO inv a y\nM1 y a 0 0 nch\n.EOM\nX1 1 2 inv\n")
        self.assertEqual([s.name for s in circuit.subcircuits], ["inv"])
        self.assertEqual(len(circuit.subcircuits[0].components), 1)
        self.assertEqual(len(circuit.components), 1)


if __name__ == "__main__":
    unittest.main()
