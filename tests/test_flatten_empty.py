import unittest
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer

class TestFlattenEmpty(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()

    def test_flatten_empty_subckt(self):
        # Scenario: Transistor defined as an empty subcircuit (common in CDL/LVS)
        netlist = """
        .subckt nfet d g s b
        * Empty leaf cell
        .ends

        .subckt top
        X1 1 2 3 0 nfet
        .ends
        """
        circuit = self.parser.parse(netlist, circuit_name="top")
        analyzer = NetlistAnalyzer(circuit)
        
        # Flatten
        flat = analyzer.flatten()
        
        # After fix, flat.components should contain 1 SubcktInstance (X1)
        self.assertEqual(len(flat.components), 1)
        self.assertEqual(flat.components[0].subckt_name, "nfet")
        
        # Verify stats
        stats = analyzer.get_hierarchical_stats()
        self.assertEqual(stats["SubcktInstance"], 1)
        
        # Verify usage
        usage = analyzer.get_model_usage()
        self.assertEqual(usage["nfet"], 1)

if __name__ == '__main__':
    unittest.main()
