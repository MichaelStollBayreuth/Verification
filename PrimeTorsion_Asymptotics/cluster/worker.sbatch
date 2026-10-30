#!/bin/bash
#SBATCH --job-name=strange-worker
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --constraint=EPYC-7302|EPYC-7352
#SBATCH --exclude=r12g[01-03]
#SBATCH --time=1-00:00:00
#SBATCH --signal=B:USR1@1800
#SBATCH --output=queue/slurm/%j.out
#
# One worker of the strange-prime search on a whole node (see README.md).
# Submit from ~/strange-search (which contains strange_primes.magma,
# search_pair.m, cluster/ and queue/):  sbatch cluster/worker.sbatch
# 30 minutes before the time limit the worker stops taking tasks and requeues
# those that cannot finish in time.
cd ~/strange-search || exit 1
exec python3 cluster/worker.py --queue queue --code . \
  --magma /opt/hpc-lipwig/public/group_software/math/vivaorg_10150005/magma/magma
