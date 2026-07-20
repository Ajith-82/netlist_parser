import unittest
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.ast import Resistor, Mosfet, SubcktInstance, Subckt

class TestSpiceParser(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()

    def test_basic_components(self):
        netlist = """
        * Basic Test
        R1 1 0 1k
        M1 d g s b nmos l=1u w=2u
        V1 1 0 5
        """
        circuit = self.parser.parse(netlist)
        
        self.assertEqual(len(circuit.components), 3)
        
        r1 = circuit.components[0]
        self.assertIsInstance(r1, Resistor)
        self.assertEqual(r1.name, "R1")
        self.assertEqual(r1.nodes, ["1", "0"])
        self.assertEqual(r1.value, "1k")
        
        m1 = circuit.components[1]
        self.assertIsInstance(m1, Mosfet)
        self.assertEqual(m1.name, "M1")
        self.assertEqual(m1.nodes, ["d", "g", "s", "b"])
        self.assertEqual(m1.model, "nmos")
        self.assertEqual(m1.parameters["l"], "1u")
        self.assertEqual(m1.parameters["w"], "2u")

    def test_subckt_hierarchy(self):
        netlist = """
        .subckt inv in out vdd gnd
        M1 out in vdd vdd pmos
        M2 out in gnd gnd nmos
        .ends
        
        X1 a b vdd 0 inv
        X2 b c vdd 0 inv
        """
        circuit = self.parser.parse(netlist)
        
        self.assertEqual(len(circuit.subcircuits), 1)
        subckt = circuit.subcircuits[0]
        self.assertEqual(subckt.name, "inv")
        self.assertEqual(len(subckt.components), 2)
        
        self.assertEqual(len(circuit.components), 2)
        x1 = circuit.components[0]
        self.assertIsInstance(x1, SubcktInstance)
        self.assertEqual(x1.subckt_name, "inv")
        self.assertEqual(x1.nodes, ["a", "b", "vdd", "0"])

    def test_cdl_comment_coded_params(self):
        # CDL style: $SUB= substrate, $[model] device model, params continue
        # on the next line. None of these may be mistaken for a model name.
        netlist = """
        RR1 N075 VDD $SUB=VSS $[opppcres] m=1 w=5E-07 s=5 pbar=1
        + bp=3
        """
        circuit = self.parser.parse(netlist)
        r1 = circuit.components[0]
        self.assertIsInstance(r1, Resistor)
        self.assertEqual(r1.nodes, ["N075", "VDD"])
        self.assertEqual(r1.model, "opppcres")
        self.assertEqual(r1.parameters["SUB"], "VSS")
        self.assertEqual(r1.parameters["bp"], "3")
        self.assertEqual(r1.parameters["pbar"], "1")

    def test_dollar_comment_stripped(self):
        # A bare '$ ' still starts an inline comment
        netlist = "R1 1 0 1k $ this is a comment r=99\n"
        circuit = self.parser.parse(netlist)
        r1 = circuit.components[0]
        self.assertEqual(r1.value, "1k")
        self.assertNotIn("r", r1.parameters)

    def test_continuation_line(self):
        netlist = """
        M1 d g s b nmos 
        + l=1u 
        + w=2u
        """
        circuit = self.parser.parse(netlist)
        m1 = circuit.components[0]
        self.assertEqual(m1.parameters["l"], "1u")
        self.assertEqual(m1.parameters["w"], "2u")

if __name__ == '__main__':
    unittest.main()
