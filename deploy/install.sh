#!/usr/bin/env bash
# Install a netlist-parser wheel into a versioned venv on the cluster
# tools area (run this ON the cluster; no internet access required).
#
# Build the wheel first on any machine:   poetry build
# Then copy dist/netlist_parser-<ver>-py3-none-any.whl to the cluster.
#
# Usage:
#   ./install.sh <wheel-file> <install-prefix> [python]
#
# Example:
#   module load python/3.11   # if the system python3 is < 3.9
#   ./install.sh netlist_parser-0.1.0-py3-none-any.whl /apps/tools/netlist-parser
#
# Result: /apps/tools/netlist-parser/<version>/bin/netlist-parser
set -euo pipefail

WHEEL="${1:?usage: install.sh <wheel-file> <install-prefix> [python]}"
PREFIX="${2:?usage: install.sh <wheel-file> <install-prefix> [python]}"
PYTHON="${3:-python3}"

# netlist_parser-0.1.0-py3-none-any.whl -> 0.1.0
VERSION=$(basename "$WHEEL" | cut -d- -f2)
VENV="$PREFIX/$VERSION"

"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 9), \
    f"Python >= 3.9 required, found {sys.version.split()[0]}"'

if [ -e "$VENV" ]; then
    echo "Error: $VENV already exists (remove it to reinstall)." >&2
    exit 1
fi

echo "Installing netlist-parser $VERSION -> $VENV"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --no-index "$WHEEL"

echo "Done. Verify with: $VENV/bin/netlist-parser --help"
echo "Now install the modulefile as netlist-parser/$VERSION.lua (see modulefile.lua)."
