import unittest
import os
from netlist_parser.parser.spice import SpiceParser

class TestFailedInclude(unittest.TestCase):
    def setUp(self):
        self.parser = SpiceParser()
        self.test_file = "test_missing_include.sp"
        
        content = """
        * Test circuit with missing include
        .include ./non_existent_file.sp
        X1 1 2 0 mysub
        """
        with open(self.test_file, "w") as f:
            f.write(content)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_failed_include_tracking(self):
        circuit = self.parser.parse_file(self.test_file)
        
        # Check if failed include is recorded
        self.assertTrue(len(circuit.failed_includes) > 0)
        self.assertTrue(any("non_existent_file.sp" in f for f in circuit.failed_includes))

if __name__ == '__main__':
    unittest.main()
