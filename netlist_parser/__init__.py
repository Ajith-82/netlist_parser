"""SPICE Netlist Parser and Analyzer.

A Python utility for parsing, analyzing, and manipulating SPICE netlists
with support for CDL and hierarchical analysis.
"""

from .parser.spice import SpiceParser
from .analyzer import NetlistAnalyzer
from .ast import (
    Circuit,
    Subckt,
    Component,
    Resistor,
    Capacitor,
    Inductor,
    Mosfet,
    Bjt,
    Diode,
    SubcktInstance,
)

__version__ = "0.2.0"
__all__ = [
    "SpiceParser",
    "NetlistAnalyzer",
    "Circuit",
    "Subckt",
    "Component",
    "Resistor",
    "Capacitor",
    "Inductor",
    "Mosfet",
    "Bjt",
    "Diode",
    "SubcktInstance",
]
