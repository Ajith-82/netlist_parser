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
