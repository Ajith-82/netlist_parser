import unittest
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer

class TestTransistorClassification(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()

    def test_classification(self):
        netlist = """
        .subckt nfet d g s b
        .ends
        
        .subckt pmos_hvt d g s b
        .ends

        .subckt my_bjt c b e
        .ends
        
        .subckt esd_diode n p
        .ends
        
        .subckt simple_block a b
        R1 a b 100
        .ends
        
        .subckt top
        * Valid Mosfet (Leaf + name + W/L params)
        X1 1 2 3 0 nfet W=1u L=0.1u
        
        * Valid Mosfet (Case insensitive name + params)
        X2 1 2 3 0 pmos_hvt w=2u l=0.2u
        
        * Invalid Mosfet (Name ok, missing params) -> Should stay SubcktInstance
        X3 1 2 3 0 nfet M=2
        
        * Valid BJT (Name heuristic)
        X4 1 2 3 my_bjt
        
        * Valid Diode (Name heuristic)
        X5 1 2 esd_diode
        
        * Structural Block -> SubcktInstance
        X6 1 2 simple_block
        
        * Real Primitive
        M1 1 2 3 0 nfet_model
        .ends
        """
        circuit = self.parser.parse(netlist, circuit_name="top")
        analyzer = NetlistAnalyzer(circuit)
        
        stats = analyzer.get_hierarchical_stats()
        
        # MOSFETs: X1, X2, M1 (Primitive) = 3
        self.assertEqual(stats.get("Mosfet", 0), 3)
        
        # BJTs: X4 = 1
        self.assertEqual(stats.get("Bjt", 0), 1)
        
        # Diodes: X5 = 1
        self.assertEqual(stats.get("Diode", 0), 1)
        
        # SubcktInstances: X3 (failed MOS check), X6 (structural) = 2
        # Note: X6 contains R1, so R1 is counted as Resistor: 1.
        # But X6 itself is not a primitive, so it shouldn't be in hierarchical primitve stats?
        # WAIT. get_hierarchical_stats flatten() decomposes structural blocks.
        # X6 is replaced by R1. So X6 classification is never even called for stats!
        # X3 is distinct because 'nfet' is empty, so it's a leaf. It persists in flatten().
        # So X3 is classified. It fails MOS check. So it returns "SubcktInstance".
        # So expected "SubcktInstance" = 1 (X3).
        self.assertEqual(stats.get("SubcktInstance", 0), 1)
        self.assertEqual(stats.get("Resistor", 0), 1) # Inside X6

if __name__ == '__main__':
    unittest.main()
