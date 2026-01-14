import argparse
import sys
import os
from netlist_parser.parser.spice import SpiceParser
from netlist_parser.analyzer import NetlistAnalyzer

def main():
    parser = argparse.ArgumentParser(description="SPICE Netlist Parser and Analyzer")
    parser.add_argument("file", help="Path to SPICE netlist file")
    parser.add_argument("--stats", action="store_true", help="Print component statistics")
    parser.add_argument("--flatten", action="store_true", help="Flatten hierarchy and print simplified netlist")
    parser.add_argument("--count-transistors", action="store_true", help="Count total transistors (MOS+BJT) in flattened circuit")
    parser.add_argument("--model-usage", action="store_true", help="Count usage of each device model in flattened circuit")
    parser.add_argument("--find-model", help="Find all subcircuits that use the specified model name", metavar="MODEL_NAME")
    parser.add_argument("--tree", action="store_true", help="Print hierarchy tree (subcircuit instances only)")
    parser.add_argument("--list-top-cells", action="store_true", help="List all potential top-level subcircuits (not instantiated by others)")
    parser.add_argument("--top-cell", help="Manually specify the name of the top-level subcircuit to analyze", metavar="TOP_CELL_NAME")

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    print(f"Parsing '{args.file}'...")
    try:
        parser_obj = SpiceParser()
        circuit = parser_obj.parse_file(args.file)
    except Exception as e:
        print(f"Error parsing file: {e}")
        sys.exit(1)

    print(f"Successfully parsed circuit: {circuit.name}")

    try:
        analyzer = NetlistAnalyzer(circuit, top_cell_name=args.top_cell)
    except Exception as e:
        print(f"Error initializing analyzer: {e}")
        sys.exit(1)

    if args.stats:
        print("\n--- Component Statistics (Top Level) ---")
        stats = analyzer.get_stats()
        for comp, count in stats.items():
            print(f"{comp}: {count}")

        print("\n--- Component Statistics (Hierarchical/Flattened) ---")
        h_stats = analyzer.get_hierarchical_stats()
        for comp, count in h_stats.items():
            print(f"{comp}: {count}")

    if args.count_transistors:
        count = analyzer.get_transistor_count()
        print(f"\nTotal Transistors (Flattend): {count}")

    if args.model_usage:
        print("\n--- Model Usage (Flattened) ---")
        usage = analyzer.get_model_usage()
        for model in sorted(usage.keys()):
            print(f"{model}: {usage[model]}")
            
        if analyzer.unresolved_subckts:
            print("\n[WARNING] The following subcircuits were instantiated but not defined (treated as black boxes):")
            for miss in sorted(list(analyzer.unresolved_subckts)):
                print(f"  - {miss}")
            print("  (This may result in incomplete statistics if they contain devices.)")

    if args.find_model:
        print(f"\n--- Subcircuits using model '{args.find_model}' ---")
        subckts = analyzer.get_subckts_using_model(args.find_model)
        if subckts:
            for s in subckts:
                print(s)
        else:
             print("No subcircuits found using this model.")

    if args.tree:
        print("\n--- Circuit Hierarchy ---")
        analyzer.print_hierarchy()

    if args.list_top_cells:
        print("\n--- Top Cells (Roots of Hierarchy) ---")
        roots = analyzer.get_top_cells()
        if roots:
            for r in roots:
                print(r)
        else:
            print("No subcircuits found (flat design).")

    if args.flatten:
        print("\n--- Flattened Netlist Components ---")
        flat = analyzer.flatten()
        for comp in flat.components:
            # Basic print of name and nodes
            print(f"{comp.name} {' '.join(comp.nodes)}")

if __name__ == "__main__":
    main()
