#!/bin/bash
#SBATCH --job-name=netlist_parser
#SBATCH --account=analog_ip
#SBATCH --partition=r8bs
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:01:30
#SBATCH -o output.%j
#SBATCH -e error.%j

cd /projects/af02_analog_ip/cmos55nvm_sos/work/avenugopalan/python/netlist_parser
python3 main.py ./examples/DUK001B_02.cdl --model-usage -v -j ${SLURM_CPUS_PER_TASK} > out.txt