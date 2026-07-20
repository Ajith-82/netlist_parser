#!/usr/bin/env bash
# Batch-parse a directory of netlists on Slurm.
#
# Usage:
#   ./submit_parse.sh <netlist-dir> <out-dir> [tool args...]
#
# Examples:
#   ./submit_parse.sh /projects/chipA/cdl results/                 # default --model-usage
#   ./submit_parse.sh /projects/chipA/cdl results/ --list-models
#   FILES_PER_TASK=10 MAX_CONCURRENT=20 ./submit_parse.sh cdl/ out/ --stats
#
# Tunables (environment variables):
#   FILES_PER_TASK  netlists per array task (default 1; raise for many
#                   small files so tasks aren't scheduler-bound)
#   MAX_CONCURRENT  array throttle, the %N in --array (default 50)
set -euo pipefail

DIR="${1:?usage: submit_parse.sh <netlist-dir> <out-dir> [tool args...]}"
OUT="${2:?usage: submit_parse.sh <netlist-dir> <out-dir> [tool args...]}"
shift 2

FILES_PER_TASK="${FILES_PER_TASK:-1}"
MAX_CONCURRENT="${MAX_CONCURRENT:-50}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$OUT" logs

MANIFEST="$OUT/manifest.txt"
find "$DIR" -type f \( -name '*.cdl' -o -name '*.sp' -o -name '*.spi' \
    -o -name '*.spice' -o -name '*.cir' \) | sort > "$MANIFEST"

N=$(wc -l < "$MANIFEST")
if [ "$N" -eq 0 ]; then
    echo "No netlist files found under $DIR" >&2
    exit 1
fi

TASKS=$(( (N + FILES_PER_TASK - 1) / FILES_PER_TASK ))
echo "Found $N netlists -> $TASKS array tasks" \
     "($FILES_PER_TASK file(s)/task, max $MAX_CONCURRENT concurrent)"

sbatch --array="1-${TASKS}%${MAX_CONCURRENT}" \
       --export=ALL,FILES_PER_TASK="$FILES_PER_TASK" \
       "$SCRIPT_DIR/parse_netlists.sbatch" "$MANIFEST" "$OUT" "$@"
