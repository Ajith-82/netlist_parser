#!/usr/bin/env bash
# Slurm job-array worker: parse a slice of netlists from a manifest.
#
# Normally submitted via submit_parse.sh, which builds the manifest and
# sizes the array. Manual submission:
#
#   sbatch --array=1-<N>%50 parse_netlists.sbatch <manifest> <out-dir> [tool args...]
#
# Each array task processes FILES_PER_TASK consecutive manifest lines
# (default 1). Per-netlist stdout goes to <out-dir>/<name>.txt and
# stderr to <out-dir>/<name>.err.
#
#SBATCH --job-name=netlist-parse
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x_%A_%a.out
set -euo pipefail

MANIFEST="${1:?usage: parse_netlists.sbatch <manifest> <out-dir> [tool args...]}"
OUTDIR="${2:?usage: parse_netlists.sbatch <manifest> <out-dir> [tool args...]}"
shift 2
# Default analysis if no tool args were given
ARGS=("${@:---model-usage}")

# Provide netlist-parser: prefer an already-available binary, else the module
if ! command -v netlist-parser >/dev/null 2>&1; then
    module load netlist-parser
fi

FILES_PER_TASK="${FILES_PER_TASK:-1}"
start=$(( (SLURM_ARRAY_TASK_ID - 1) * FILES_PER_TASK + 1 ))
end=$(( start + FILES_PER_TASK - 1 ))
mapfile -t files < <(sed -n "${start},${end}p" "$MANIFEST")

mkdir -p "$OUTDIR"
rc=0
for f in "${files[@]}"; do
    [ -n "$f" ] || continue
    base=$(basename "$f")
    name="${base%.*}"
    echo "[$(date +%T)] parsing $f"
    if ! netlist-parser "$f" -j "${SLURM_CPUS_PER_TASK:-2}" "${ARGS[@]}" \
            > "$OUTDIR/$name.txt" 2> "$OUTDIR/$name.err"; then
        echo "FAILED: $f (see $OUTDIR/$name.err)" >&2
        rc=1
    fi
done
exit $rc
