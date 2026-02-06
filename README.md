# SPICE Netlist Parser and Analyzer

A Python-based utility for parsing, analyzing, and manipulating SPICE netlists. This tool supports various SPICE dialects (Generic, CDL, HSPICE) and provides capabilities for hierarchical analysis, flattening, model usage extraction, and connectivity inspection.

## Features

-   **Multi-Dialect Parsing**: Supports generic SPICE syntax, CDL (Circuit Description Language), and HSPICE specifics.
-   **Hierarchical Analysis**: Parses nested `.SUBCKT` definitions and builds an internal AST (Abstract Syntax Tree).
-   **Flattening**: Recursively flattens the hierarchy to provide a component-level view of the entire circuit.
-   **Automatic Top Cell Detection**: Heuristically identifies the top-level subcircuit based on hierarchy depth.
-   **Component Counting**: Counts primitives (MOSFETs, BJTs, Resistors, etc.) and specific transistor types.
-   **Model Extraction**: List all unique models or count their occurrences in the flattened design.
-   **Search Capabilities**: Find which subcircuits use a specific model.
-   **Multi-threading**: Parallel I/O for faster parsing of large netlists with many include files.
-   **Case-insensitive Matching**: SPICE-compliant case-insensitive model name handling.
-   **3-Terminal Passives**: Supports resistors and capacitors with substrate connections.
-   **Robustness**: Handles missing includes (reporting them as unresolved warnings) and various comment styles.

## Installation

### Using Poetry (Recommended)

```bash
# Clone the repository
git clone <repository_url>
cd netlist_parser

# Install with Poetry
poetry install

# Run the tool
poetry run netlist-parser <file> [options]
```

### Manual Installation

No external dependencies are required. The tool uses standard Python 3.9+ libraries.

```bash
# Clone the repository
git clone <repository_url>
cd netlist_parser

# Run directly
python3 main.py <file> [options]
```

## Usage

```bash
# Via Poetry
poetry run netlist-parser [file] [options]

# Or directly
python3 main.py [file] [options]
```

### Arguments

| Argument | Description |
| :--- | :--- |
| `file` | Path to the SPICE/CDL netlist file. |
| `--stats` | Print component statistics (counts of each component type). |
| `--flatten` | Flatten the hierarchy and print the simplified list of components. |
| `--count-transistors` | Count the total number of transistors (MOSFET + BJT) in the flattened circuit. |
| `--model-usage` | Count usage of each device model in the flattened circuit. |
| `--list-models` | List all unique models in the netlist (fast, no flattening required). |
| `--find-model <NAME>` | Find and list all subcircuits that directly instantiate the specified model. |
| `--list-top-cells` | List all potential top-level subcircuits (defined but not instantiated by others). |
| `--top-cell <NAME>` | Manually specify the name of the top-level subcircuit to analyze. |
| `--tree` | Print the hierarchy tree (subcircuit instances only). |
| `-v, --verbose` | Enable verbose output (INFO level logging). |
| `--debug` | Enable debug logging (DEBUG level). |
| `-j, --threads <N>` | Number of threads for parallel I/O (0=auto, 1=disabled). |
| `--case-sensitive` | Use case-sensitive model names (default: case-insensitive). |

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

**3. List All Models (Fast)**
Extract all unique model names without flattening:
```bash
python3 main.py examples/large_design.cdl --list-models
```

**4. Find Model Users**
Find which subcircuits use a specific high-voltage transistor model:
```bash
python3 main.py examples/mixed_signal.sp --find-model nch_hvt_dnw
```

**5. Analyze a Specific Block**
If your file contains many definitions but you only want to analyze the `ALU` block:
```bash
python3 main.py examples/cpu.cdl --top-cell ALU --count-transistors
```

**6. Verbose Output with Multi-threading**
Parse a large netlist with verbose logging and 4 threads:
```bash
python3 main.py examples/large_soc.cdl --model-usage -v -j 4
```

**7. Debugging Hierarchy**
List the apparent roots of the hierarchy (top cells):
```bash
python3 main.py examples/complex_soc.cdl --list-top-cells
```

## Parsing Details

-   **CDL Support**: Handles `XX` instances with `/` separators correctly (e.g., `XXinst / subckt_name`).
-   **HSPICE Support**: Parses `.PARAM`, quoted expressions, and multiplier parameters.
-   **3-Terminal Passives**: Supports R/C/L with substrate connections (e.g., `R1 N1 N2 SUB model`).
-   **Model-based Passives**: Detects resistor/capacitor models (e.g., `R1 N1 N2 opppcres l=2u w=2u`).
-   **Comments**:
    -   `*` at the start of a line is a comment.
    -   `$` is treated as an inline comment (everything after is ignored).
-   **Include Files**: Processes `.INCLUDE` and `.LIB` directives with parallel file loading.
-   **Missing Definitions**: If a subcircuit is instantiated but not defined, it is treated as a black box and reported as a warning.

## Library Usage

```python
from netlist_parser import SpiceParser, NetlistAnalyzer

# Parse a netlist
parser = SpiceParser(num_threads=4)
circuit = parser.parse_file("design.cdl")

# Analyze
analyzer = NetlistAnalyzer(circuit)

# Get all unique models
models = analyzer.get_all_models()

# Get model usage counts
usage = analyzer.get_model_usage()

# Find subcircuits using a specific model
subckts = analyzer.get_subckts_using_model("nmos_hvt")

# Flatten and count transistors
count = analyzer.get_transistor_count()
```
