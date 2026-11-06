#!/bin/bash
#SBATCH --job-name=strange-crt
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --constraint=EPYC-7302|EPYC-7352
#SBATCH --exclude=r12g[01-03],r04n27,r05n20,r11n24
#SBATCH --time=0-06:00:00
#SBATCH --output=queue/slurm/crt-%j.out
#
# Proofs of strangeness in characteristic 0 (sparse/crt_verify.py) for the pairs that the
# sparse screening did not certify (queue/open/), or for the pairs "p n" given as arguments:
#   sbatch cluster/crt.sbatch [p n ...]
# Results in queue/crt/: p-n.txt (output, with the line "STRANGE <p, n>: strdim ..."),
# crt-p-n.txt (the functionals) and crt-p-n.log (the exact check). Pairs with a result are skipped.
cd ~/strange-search || exit 1
M=/opt/hpc-lipwig/public/group_software/math/vivaorg_10150005/magma/magma
mkdir -p queue/crt
if [ $# -gt 0 ]; then pairs="$*"; else
  pairs=$(ls queue/open | sed -n 's/^\([0-9]*\)-\([0-9]*\)\.out$/\1 \2/p' | sort -n)
fi
set -- $pairs
while [ $# -ge 2 ]; do
  p=$1; n=$2; shift 2
  [ -s queue/crt/$p-$n.txt ] && grep -q -e '^STRANGE' -e '^CRT_' queue/crt/$p-$n.txt && continue
  echo "$(date '+%F %T') $p $n"
  python3 sparse/crt_verify.py $p $n --magma $M --jobs 32 --out queue/crt > queue/crt/$p-$n.txt 2>&1
  grep -h -e '^STRANGE' -e '^CHAR0' -e '^CRT_' queue/crt/$p-$n.txt
done
echo "$(date '+%F %T') done"
