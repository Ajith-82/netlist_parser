# SPICE Netlist Parser and Analyzer

A Python-based utility for parsing, analyzing, and manipulating SPICE netlists. This tool supports various SPICE dialects (Generic, CDL, etc.) and provides capabilities for hierarchical analysis, flattening, model usage extraction, and connectivity inspection.

## Features

-   **Multi-Dialect Parsing**: Supports generic SPICE syntax and CDL (Circuit Description Language) specifics (e.g., `/` separators in instances, `$` comments).
-   **Hierarchical Analysis**: parses nested `.SUBCKT` definitions and builds an internal AST (Abstract Syntax Tree).
-   **Flattening**: Recursively flattens the hierarchy to provide a component-level view of the entire circuit.
-   **Automatic Top Cell Detection**: Heuristically identifies the top-level subcircuit if the global scope is empty.
-   **Component Counting**: Counts primitives (MOSFETs, BJTs, Resistors, etc.) and specific transistor types.
-   **Model Usage**: Extracts all referenced device models and counts their occurrences in the flattened design.
-   **Search Capabilities**: Find which subcircuits use a specific model.
-   **Robustness**: Handles missing includes (reporting them as unresolved warnings) and various comment styles.

## Installation

No external dependencies are required. The tool uses standard Python 3 libraries.

```bash
# Clone the repository
git clone <repository_url>
cd netlist_parser

# Set up PYTHONPATH
export PYTHONPATH=$PYTHONPATH:.
```

## Usage

The main entry point is `main.py`.

```bash
python3 main.py [file] [options]
```

### Arguments

| Argument | Description |
| :--- | :--- |
| `file` | Path to the SPICE/CDL netlist file. |
| `--stats` | Print component statistics (counts of each component type) for the top level. |
| `--flatten` | Flatten the hierarchy and print the simplified list of components. |
| `--count-transistors` | Count the total number of transistors (MOSFET + BJT) in the flattened circuit. |
| `--model-usage` | Count unique usage of each device model name in the flattened circuit. |
| `--find-model <NAME>` | Find and list all subcircuits that directly instantiate the specified model. |
| `--list-top-cells` | List all potential top-level subcircuits (defined but not instantiated by others). |
| `--top-cell <NAME>` | Manually specify the name of the top-level subcircuit to analyze. Helpful for partial netlists or testing specific blocks. |

## Examples

**1. Basic Statistics**
Get a count of components in the top-level circuit:
```bash
python3 main.py examples/my_design.sp --stats
```

**2. Analyze Model Usage**
See which models are used and how often in the entire flattened design:
```bash
python3 main.py examples/processor.cdl --model-usage
```

**3. Find Model Users**
Find which subcircuits use a specific high-voltage transistor model:
```bash
python3 main.py examples/mixed_signal.sp --find-model nch_hvt_dnw
```

**4. Analyze a Specific Block**
If your file contains many definitions but you only want to analyze the `ALU` block:
```bash
python3 main.py examples/cpu.cdl --top-cell ALU --count-transistors
```

**5. Debugging Hierarchy**
List the apparent roots of the hierarchy (top cells):
```bash
python3 main.py examples/complex_soc.cdl --list-top-cells
```

## Parsing Details

-   **CDL Support**: Handles `XX` instances with `/` separators correctly (e.g., `XXinst / subckt_name`).
-   **Comments**: 
    -   `*` at the start of a line is a comment.
    -   `$` is treated as an inline comment (everything after is ignored), compatible with CDL parameter syntax.
-   **Missing Definitions**: If a subcircuit is instantiated but not defined (e.g., inside an unparsed `.INCLUDE`), it is treated as a black box and reported as a warning during analysis.
