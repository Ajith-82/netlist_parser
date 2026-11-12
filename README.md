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
-   **Case-insensitive Matching**: SPICE-compliant case-insensitive model name handling (device names keep their source case).
-   **3-Terminal Passives**: Supports resistors and capacitors with substrate connections.
-   **CDL Comment-Coded Parameters**: Parses `$SUB=`, `$[model]`, and `$KEY=value` tokens instead of discarding them as comments.
-   **Scales to Large Netlists**: Dict-based subcircuit lookup and copy-light flattening handle multi-million-line netlists in seconds.
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
| `--list-models` | List all unique device models in the netlist, hierarchy-wide (fast, no flattening required). Includes CDL-style X-instance leaf devices. |
| `--find-model <NAME>` | Find and list all subcircuits that directly instantiate the specified model. |
| `--list-top-cells` | List all potential top-level subcircuits (defined but not instantiated by others). |
| `--check-duplicates` | Report subcircuit names defined more than once (case-insensitive unless `--case-sensitive`), with the file and line of each definition, labelled identical or conflicting. The last definition is the one used. A short warning is also shown automatically with `--stats`, `--count-transistors`, `--model-usage`, `--flatten` and `--tree`. |
| `--remove-duplicates <OUTPUT>` | Write a copy of the netlist to `OUTPUT` with duplicated subcircuit definitions cut out; the rest of the text is left exactly as it was. Identical duplicates are removed. Conflicting ones are left in place unless `--keep` is given. The input is never modified, an existing `OUTPUT` is never overwritten, and only the main file is rewritten (not included files). |
| `--keep first\|last` | With `--remove-duplicates`: also remove conflicting duplicates, keeping the first or last definition (`last` is the one the analysis uses). |
| `--top-cell <NAME>` | Manually specify the name of the top-level subcircuit to analyze. |
| `--tree` | Print the hierarchy tree (subcircuit instances only). |
| `-v, --verbose` | Enable verbose output (INFO level logging). |
| `--debug` | Enable debug logging (DEBUG level). |
| `-j, --threads <N>` | Number of threads for parallel I/O (0=auto, 1=disabled). |
| `--case-sensitive` | Use case-sensitive model and subcircuit names (default: case-insensitive, as in SPICE). |

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
-   **Comments and CDL Comment-Coded Parameters**:
    -   `*` at the start of a line is a comment.
    -   A bare `$` followed by whitespace starts an inline comment.
    -   CDL comment-coded parameters are parsed, not discarded: `$[model]`
        sets the device model (e.g. `RR1 N1 N2 $SUB=VSS $[opppcres] w=1u`),
        and `$KEY=value` (e.g. `$SUB=VSS`, `$W=1u`) becomes a parameter.
        Any other `$token` is treated as the start of a comment.
-   **Include Files**: Processes `.INCLUDE` and `.LIB` directives with parallel file loading.
-   **Library Sections**: `.LIB 'file' section` reads only that section (between `.LIB section` and `.ENDL`) of the file. `.LIB 'file'` with no section reads the whole file.
-   **Global Nets**: `.GLOBAL` and CDL `*.GLOBAL` (including `:P`/`:G` suffixes) are recorded; flattening keeps these nets unscoped unless a subcircuit port of the same name overrides them.
-   **Macros**: `.MACRO`/`.EOM` are accepted as synonyms for `.SUBCKT`/`.ENDS`.
-   **Unsupported Elements**: Device lines of other element types (E, F, G, H, K, J, ...) are skipped and reported as a count per type.
-   **Title Line**: The first line of the top file is ignored as a SPICE title unless it is a comment, a dot command, or a plausible device statement.
-   **Recursive Subcircuits**: A subcircuit that instantiates itself, directly or indirectly, is reported and the repeated instance is treated as a black box.
-   **Missing Definitions**: If a subcircuit is instantiated but not defined, it is treated as a black box and reported as a warning.

## Deployment on HPC Clusters (Slurm)

The tool is pure Python 3.9+ with no runtime dependencies, so cluster
deployment needs no internet access on the nodes. Ready-made scripts live in
[`deploy/`](deploy/).

### One-time installation

```bash
# 1. On any machine: build the wheel (pure-Python, works on any node)
poetry build

# 2. On the cluster: install into a versioned venv on the shared tools area
#    (module load python/3.11 first if the system python3 is older than 3.9)
./deploy/install.sh dist/netlist_parser-0.2.0-py3-none-any.whl /apps/tools/netlist-parser

# 3. Install the Lmod modulefile (edit the `root` path inside first)
cp deploy/modulefile.lua <modules-root>/netlist-parser/0.2.0.lua
```

Users then get the CLI with `module load netlist-parser`.

### Batch processing with job arrays

Parsing is single-node and mostly single-core (`-j` only parallelizes include
file I/O), so parallelism across many netlists comes from Slurm job arrays:

```bash
# Parse every netlist under a directory, one array task per file
./deploy/submit_parse.sh /projects/chipA/cdl results/ --model-usage

# Bundle 10 small netlists per task, at most 20 tasks running at once
FILES_PER_TASK=10 MAX_CONCURRENT=20 ./deploy/submit_parse.sh cdl/ out/ --list-models
```

`submit_parse.sh` builds a manifest of `*.cdl/*.sp/*.spi/*.spice/*.cir` files,
sizes the array, and submits `parse_netlists.sbatch`. Each netlist's output
lands in `<out-dir>/<name>.txt` (stderr in `<name>.err`).

Notes:

-   Add `--partition=`/`--account=` to the `#SBATCH` headers if your site
    requires them; defaults are 2 CPUs, 8 GB, 1 hour per task.
-   `MAX_CONCURRENT` throttles the array — tune it down if the netlists live
    on a heavily shared filesystem.
-   No scheduler? The single-file alternative is a zipapp:
    `python3 -m zipapp netlist_parser -m "netlist_parser.cli:main" -o netlist-parser.pyz -p "/usr/bin/env python3"`
    produces one file runnable anywhere Python 3.9+ exists.

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
