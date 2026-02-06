#!/usr/bin/env python3
"""
Standalone entry point for running netlist-parser without installation.

For installed usage, use: poetry run netlist-parser
"""

from netlist_parser.cli import main

if __name__ == "__main__":
    main()
