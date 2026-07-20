-- Lmod modulefile for netlist-parser.
--
-- Install into your modules tree as:
--   <modules-root>/netlist-parser/0.1.0.lua
-- so users can:  module load netlist-parser
--
-- Adjust `root` to match the prefix given to install.sh.

local root = "/apps/tools/netlist-parser"
local version = myModuleVersion()
local prefix = pathJoin(root, version)

whatis("Name        : netlist-parser")
whatis("Version     : " .. version)
whatis("Description : SPICE/CDL netlist parser and analyzer")

help([[
SPICE/CDL netlist parser and analyzer.

Usage:  netlist-parser <file.cdl> [--stats|--list-models|--model-usage|...]

For batch processing many netlists, see the Slurm job-array scripts in
the repository's deploy/ directory (submit_parse.sh).
]])

-- If the venv was built with a python module instead of the system
-- python3, make it load automatically:
-- depends_on("python/3.11")

prepend_path("PATH", pathJoin(prefix, "bin"))
