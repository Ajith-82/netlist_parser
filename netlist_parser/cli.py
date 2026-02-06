"""Command-line interface for netlist-parser."""

import argparse
import sys
import os
import logging

from .parser.spice import SpiceParser
from .analyzer import NetlistAnalyzer


def main():
    """Main entry point for the netlist-parser CLI."""
    parser = argparse.ArgumentParser(
        description="SPICE Netlist Parser and Analyzer"
    )
    parser.add_argument("file", help="Path to SPICE netlist file")
    parser.add_argument(
        "--stats", action="store_true",
        help="Print component statistics"
    )
    parser.add_argument(
        "--flatten", action="store_true",
        help="Flatten hierarchy and print simplified netlist"
    )
    parser.add_argument(
        "--count-transistors", action="store_true",
        help="Count total transistors (MOS+BJT) in flattened circuit"
    )
    parser.add_argument(
        "--model-usage", action="store_true",
        help="Count usage of each device model in flattened circuit"
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="List all unique models in the netlist (no flattening)"
    )
    parser.add_argument(
        "--find-model", metavar="MODEL_NAME",
        help="Find all subcircuits that use the specified model name"
    )
    parser.add_argument(
        "--tree", action="store_true",
        help="Print hierarchy tree (subcircuit instances only)"
    )
    parser.add_argument(
        "--list-top-cells", action="store_true",
        help="List all potential top-level subcircuits (not instantiated)"
    )
    parser.add_argument(
        "--top-cell", metavar="TOP_CELL_NAME",
        help="Manually specify the name of the top-level subcircuit"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose output (INFO level)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging (DEBUG level)"
    )
    parser.add_argument(
        "-j", "--threads", type=int, default=0,
        help="Number of threads for parallel I/O (0=auto, 1=disabled)"
    )
    parser.add_argument(
        "--case-sensitive", action="store_true",
        help="Use case-sensitive model names (default: case-insensitive)"
    )

    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(levelname)s: %(message)s'
        )
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format='%(message)s')
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format='%(levelname)s: %(message)s'
        )

    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found.")
        sys.exit(1)

    # Determine thread count (0=auto, uses CPU count)
    if args.threads == 0:
        num_threads = min(8, (os.cpu_count() or 4))
    else:
        num_threads = args.threads

    print(f"Parsing '{args.file}'...")
    try:
        parser_obj = SpiceParser(num_threads=num_threads)
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
        print(f"\nTotal Transistors (Flattened): {count}")

    if args.model_usage:
        print("\n--- Model Usage (Flattened) ---")
        usage = analyzer.get_model_usage(
            case_insensitive=not args.case_sensitive
        )
        for model in sorted(usage.keys()):
            print(f"{model}: {usage[model]}")

        if analyzer.unresolved_subckts:
            print("\n[WARNING] The following subcircuits were instantiated "
                  "but not defined (treated as black boxes):")
            for miss in sorted(list(analyzer.unresolved_subckts)):
                print(f"  - {miss}")
            print("  (This may result in incomplete statistics if they "
                  "contain devices.)")

    if hasattr(circuit, 'failed_includes') and circuit.failed_includes:
        print("\n[WARNING] The following include files were not found:")
        for fail in sorted(circuit.failed_includes):
            print(f"  - {fail}")
        print("  (Missing includes explain why subcircuits are undefined "
              "and treated as black boxes.)")

    if args.list_models:
        print("\n--- All Models in Netlist ---")
        models = analyzer.get_all_models(
            case_insensitive=not args.case_sensitive
        )
        if models:
            for model in models:
                print(model)
            print(f"\nTotal: {len(models)} unique models")
        else:
            print("No models found.")

    if args.find_model:
        print(f"\n--- Subcircuits using model '{args.find_model}' ---")
        subckts = analyzer.get_subckts_using_model(
            args.find_model,
            case_insensitive=not args.case_sensitive
        )
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
            print(f"{comp.name} {' '.join(comp.nodes)}")


if __name__ == "__main__":
    main()
