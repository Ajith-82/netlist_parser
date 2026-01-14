import unittest
import os
from netlist_parser.parser.spice import SpiceParser

class TestInclude(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()
        self.test_files = []

    def tearDown(self):
        for f in self.test_files:
            if os.path.exists(f):
                os.remove(f)

    def test_recursive_include(self):
        # Create dummy files
        # top.sp -> includes sub.sp
        # sub.sp -> defines subckt 'mysub'
        
        sub_content = """
        .subckt mysub A B
        R1 A B 1k
        .ends
        """
        
        top_content = """
        .include './sub.sp'
        X1 1 0 mysub
        """
        
        with open("sub.sp", "w") as f:
            f.write(sub_content)
        self.test_files.append("sub.sp")
        
        with open("top.sp", "w") as f:
            f.write(top_content)
        self.test_files.append("top.sp")
        
        # Parse top
        circuit = self.parser.parse_file("top.sp")
        
        # Check if subckt is loaded
        sub_names = [s.name for s in circuit.subcircuits]
        self.assertIn("mysub", sub_names)
        
        # Check if X1 is resolved (not strictly checked by parser, but we can check if model usage finds it later)
        # But for parser unit test, just checking subcircuit existence is enough.
        
        # Also check circuit.includes list
        # Path will be absolute
        self.assertTrue(any("sub.sp" in p for p in circuit.includes))

if __name__ == '__main__':
    unittest.main()
