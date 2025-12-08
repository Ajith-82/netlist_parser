import unittest
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer

class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()

    def test_stats(self):
        netlist = """
        M1 d g s b nmos
        R1 1 0 1k
        """
        circuit = self.parser.parse(netlist)
        analyzer = NetlistAnalyzer(circuit)
        stats = analyzer.get_stats()
        self.assertEqual(stats["Mosfet"], 1)
        self.assertEqual(stats["Resistor"], 1)

    def test_flatten_simple(self):
        netlist = """
        .subckt inv in out
        M1 out in 0 0 nmos
        .ends
        
        X1 a b inv
        """
        circuit = self.parser.parse(netlist)
        analyzer = NetlistAnalyzer(circuit)
        flat = analyzer.flatten()
        
        self.assertEqual(len(flat.components), 1)
        m1 = flat.components[0]
        self.assertEqual(m1.name, "X1.M1")
        # Nodes: out->b, in->a, 0->0, 0->0
        self.assertEqual(m1.nodes, ["b", "a", "0", "0"])

    def test_flatten_nested(self):
        netlist = """
        .subckt leaf p1 p2
        R1 p1 p2 100
        .ends
        
        .subckt branch a b
        X1 a mid leaf
        X2 mid b leaf
        .ends
        
        Xtop in out branch
        """
        circuit = self.parser.parse(netlist)
        analyzer = NetlistAnalyzer(circuit)
        flat = analyzer.flatten()
        
        # Should have 2 resistors:
        # Xtop.X1.R1 (a -> Xtop.mid)
        # Xtop.X2.R1 (Xtop.mid -> out)
        
        self.assertEqual(len(flat.components), 2)
        r_names = sorted([c.name for c in flat.components])
        self.assertEqual(r_names, ["Xtop.X1.R1", "Xtop.X2.R1"])
        
        # Check connectivity
        # Xtop.X1 connects 'a' (in) and 'mid' (Xtop.mid)
        # Xtop.X2 connects 'mid' (Xtop.mid) and 'b' (out)
        
        # Wait, my logic for top level node renaming in recurse:
        # Xtop maps 'in' 'out' to 'a' 'b' of branch.
        # Inside branch:
        # X1 'a' 'mid' -> leaf 'p1' 'p2'.
        # 'a' maps to 'in'. 'mid' is internal, so becomes 'Xtop.mid'.
        
        # Let's verify
        comp1 = [c for c in flat.components if c.name == "Xtop.X1.R1"][0]
        # R1 in leaf connects p1 p2.
        # X1 connects a(in) mid(Xtop.mid).
        # So Xtop.X1.R1 nodes should be ['in', 'Xtop.mid']
        self.assertEqual(comp1.nodes, ['in', 'Xtop.mid'])

    def test_model_usage(self):
        netlist = """
        .model nmos_vtg nmos
        .model pmos_vtg pmos
        
        .subckt inv in out
        M1 out in 0 0 nmos_vtg
        M2 out in 1 1 pmos_vtg
        .ends
        
        X1 a b inv
        X2 b c inv
        """
        circuit = self.parser.parse(netlist)
        analyzer = NetlistAnalyzer(circuit)
        usage = analyzer.get_model_usage()
        
        self.assertEqual(usage["nmos_vtg"], 2) # X1.M1, X2.M1
        self.assertEqual(usage["pmos_vtg"], 2) # X1.M2, X2.M2

if __name__ == '__main__':
    unittest.main()
