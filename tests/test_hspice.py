import unittest
from netlist_parser.parser.spice import SpiceParser

class TestHspice(unittest.TestCase):
    def test_quoted_expressions(self):
        # M1 w='1u + 2u'
        content = "M1 d g s b nmos w='1u + 2u'"
        parser = SpiceParser()
        circuit = parser.parse(content)
        m1 = circuit.components[0]
        self.assertEqual(m1.parameters['w'], "'1u + 2u'")

    def test_param_parsing(self):
        content = """
        .PARAM width=1u length='0.18u * 2'
        R1 1 0 1k
        """
        parser = SpiceParser()
        circuit = parser.parse(content)
        self.assertEqual(circuit.parameters['width'], '1u')
        self.assertEqual(circuit.parameters['length'], '0.18u * 2') # Quotes stripped by parser logic if outer

    def test_multipliers(self):
        content = "M1 d g s b nmos m=4"
        parser = SpiceParser()
        circuit = parser.parse(content)
        m1 = circuit.components[0]
        self.assertEqual(m1.parameters['m'], '4')

if __name__ == '__main__':
    unittest.main()
