"""Command-line interface for netlist-parser."""

import argparse
import sys
import os
import logging

from .parser.spice import SpiceParser
from .analyzer import NetlistAnalyzer
from .dedupe import remove_duplicate_subckts, verify_dedupe


def _print_duplicates(duplicates):
    """Print each duplicated subcircuit name with its definition sites."""
    for dup in duplicates:
        status = ("identical" if dup.identical
                  else "CONFLICTING - last one is used")
        print(f"{dup.name} ({len(dup.definitions)} definitions, {status})")
        for d in dup.definitions:
            written = f" (as '{d.name}')" if d.name != dup.name else ""
            print(f"  - {d.source_file or '<unknown>'}:{d.source_line or '?'}"
                  f"{written}")


def _where(subckt):
    return f"{subckt.source_file or '<unknown>'}:{subckt.source_line or '?'}"


def _remove_duplicates(args, circuit, analyzer):
    """Write a copy of the netlist without duplicated subcircuits."""
    print("\n--- Remove Duplicate Subcircuits ---")
    try:
        # newline="" keeps the file's own line endings
        with open(args.file, 'r', newline="") as f:
            content = f.read()
        result = remove_duplicate_subckts(analyzer, args.file, content,
                                          keep=args.keep)
        if result.removed:
            verify_dedupe(circuit, result, args.file,
                          case_sensitive=args.case_sensitive)
            with open(args.remove_duplicates, 'x', newline="") as f:
                f.write(result.text)
    except (OSError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if result.removed:
        n = len(result.removed)
        print(f"Removed {n} duplicate definition{'s' if n != 1 else ''}:")
        for subckt in sorted(result.removed,
                             key=lambda s: (s.name, s.source_line or 0)):
            print(f"  - {subckt.name} ({_where(subckt)})")
        print(f"Wrote '{args.remove_duplicates}' (verified by re-parsing).")
        out_dir = os.path.dirname(os.path.abspath(args.remove_duplicates))
        if (circuit.includes
                and out_dir != os.path.dirname(os.path.abspath(args.file))):
            print("  Note: the output is in a different directory, so "
                  "relative .INCLUDE/.LIB paths may no longer resolve.")
    else:
        print("No removable duplicates; nothing written.")

    if result.unresolved:
        print("\nConflicting duplicates were NOT removed "
              "(use --keep first|last to choose):")
        _print_duplicates(result.unresolved)

    if result.in_includes:
        print("\nRedundant definitions in included files were NOT removed "
              "(only the main file is rewritten):")
        for subckt in result.in_includes:
            print(f"  - {subckt.name} ({_where(subckt)})")


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
        "--check-duplicates", action="store_true",
        help="Report subcircuits that are defined more than once"
    )
    parser.add_argument(
        "--remove-duplicates", metavar="OUTPUT",
        help="Write a copy of the netlist to OUTPUT with duplicated "
             "subcircuit definitions removed. Identical duplicates are "
             "removed; conflicting ones only with --keep"
    )
    parser.add_argument(
        "--keep", choices=["first", "last"],
        help="With --remove-duplicates: also remove conflicting duplicates, "
             "keeping the first or last definition"
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
        help="Use case-sensitive model and subcircuit names "
             "(default: case-insensitive)"
    )

    args = parser.parse_args()

    if args.keep and not args.remove_duplicates:
        parser.error("--keep requires --remove-duplicates")

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

    if args.remove_duplicates:
        # Check before the (possibly long) parse
        if os.path.exists(args.remove_duplicates):
            same = os.path.samefile(args.remove_duplicates, args.file)
            print(f"Error: Output file '{args.remove_duplicates}' "
                  + ("is the input file." if same else "already exists."))
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

    if circuit.skipped_elements:
        total = sum(circuit.skipped_elements.values())
        detail = ", ".join(f"{letter}: {count}" for letter, count
                           in sorted(circuit.skipped_elements.items()))
        print(f"\n[WARNING] {total} device line(s) of unsupported element "
              f"types were skipped ({detail}).")

    try:
        analyzer = NetlistAnalyzer(circuit, top_cell_name=args.top_cell,
                                   case_sensitive=args.case_sensitive)
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

    uses_hierarchy = (args.stats or args.count_transistors or args.model_usage
                      or args.flatten or args.tree)
    if uses_hierarchy:
        recursive = analyzer.find_recursive_subckts()
        if recursive:
            print("\n[WARNING] The following subcircuits instantiate "
                  "themselves, directly or indirectly:")
            for name in recursive:
                print(f"  - {name}")
            print("  (The repeated instance is treated as a black box, so "
                  "counts are incomplete.)")

    duplicates = analyzer.get_duplicate_subckts()
    if args.check_duplicates:
        print("\n--- Duplicate Subcircuits ---")
        if duplicates:
            _print_duplicates(duplicates)
            print(f"\nTotal: {len(duplicates)} duplicated subcircuit "
                  f"name{'s' if len(duplicates) != 1 else ''}")
        else:
            print("No duplicate subcircuits found.")
    elif duplicates and uses_hierarchy:
        print("\n[WARNING] The following subcircuits are defined more than "
              "once:")
        _print_duplicates(duplicates)
        print("  (Results use the last definition of each. Run "
              "--check-duplicates for this report on its own.)")

    if args.remove_duplicates:
        _remove_duplicates(args, circuit, analyzer)

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
