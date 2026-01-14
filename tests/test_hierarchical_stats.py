import unittest
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer

class TestHierarchicalStats(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()

    def test_hierarchical_stats_simple(self):
        # 3-level hierarchy
        # Top -> Sub (1 Res) -> Leaf (1 Res)
        # Total Resistors = 1 (in Sub) + 1 (in Leaf) = 2.
        netlist = """
        .subckt leaf a b
        R1 a b 100
        .ends

        .subckt sub x y
        X1 x mid leaf
        R2 mid y 200
        .ends

        Xtop 1 0 sub
        """
        circuit = self.parser.parse(netlist)
        analyzer = NetlistAnalyzer(circuit)
        
        # Top level stats (should be just Xtop instance)
        stats = analyzer.get_stats()
        self.assertEqual(stats.get("SubcktInstance", 0), 1)
        self.assertEqual(stats.get("Resistor", 0), 0)

        # Hierarchical stats
        h_stats = analyzer.get_hierarchical_stats()
        # Expect 2 resistors total
        self.assertEqual(h_stats.get("Resistor", 0), 2)
        # Expect 2 subckt instances (Xtop, X1 inside Sub) - Wait, Xtop in stats?
        # flatten() returns mostly primitives usually, unless unresolved.
        # But wait, flatten() keeps subckt instances if they are unresolved.
        # If resolved, it replaces them with content.
        # Let's check logic:
        # _flatten_instance recurses content. 
        # So Xtop is replaced by content of 'sub'.
        # content of 'sub' is X1 and R2.
        # X1 is replaced by content of 'leaf'.
        # content of leaf is R1.
        # So final list should have R1 and R2. No SubcktInstances left.
        self.assertEqual(h_stats.get("SubcktInstance", 0), 0)

if __name__ == '__main__':
    unittest.main()
