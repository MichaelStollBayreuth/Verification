#!/bin/bash
#SBATCH --job-name=strange-calib
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --cpus-per-task=32
#SBATCH --mem=0
#SBATCH --constraint=EPYC-7302
#SBATCH --time=03:00:00
#SBATCH --output=calib/slurm-%j.out
#
# Calibration of the per-pair search (search_pair.m) on one standard lipwig
# node: time and memory per character at p ~ 2, 3, 4 * 10^5 alone, for a
# strange character (199873, order 3), and the slowdown with 4 and 8
# simultaneous processes at 2 * 10^5 and 3 at 3 * 10^5.
# Results in calib/<jobid>/: summary.txt (one line per pair), memlog.txt
# (every 5 s: epoch, MemAvailable in kB, then "rss p:= n:=;" per process),
# node.txt, and the Magma output of each pair.
MAGMA=/opt/hpc-lipwig/public/group_software/math/vivaorg_10150005/magma/magma
cd ~/strange-search || exit 1
D=calib/$SLURM_JOB_ID
mkdir -p $D
{ hostname; lscpu | grep -E 'Model name|^CPU\(s\)|Thread|NUMA node\(s\)'; free -g; nproc
  echo "SLURM_CPUS_ON_NODE=$SLURM_CPUS_ON_NODE SLURM_JOB_ACCOUNT=$SLURM_JOB_ACCOUNT"; } > $D/node.txt
md5sum strange_primes.magma search_pair.m >> $D/node.txt

( while true; do
    echo "$(date +%s) $(awk '/MemAvailable/ {print $2}' /proc/meminfo) $(ps -C magma.avx2.exe -o rss=,args= |
      awk '{s = $1; for (i = 2; i <= NF; i++) if ($i ~ /^[pn]:=/) s = s " " $i; printf "%s; ", s}')"
    sleep 5
  done ) > $D/memlog.txt &
LOGGER=$!

run() { # run TAG p n
  local tag=$1 p=$2 n=$3 t0
  t0=$(date +%s)
  "$MAGMA" -b p:=$p n:=$n search_pair.m < /dev/null > $D/$tag-$p-$n.out 2>&1
  local st=$?
  echo "$tag $p $n exit=$st wall=$(( $(date +%s) - t0 )) | $(tail -1 $D/$tag-$p-$n.out)" >> $D/summary.txt
}
phase() { echo "# $(date '+%F %T') phase $1" >> $D/summary.txt; }
parallel_runs() { # parallel_runs TAG n p1 p2 ...: simultaneous runs (wait only for these, not for the logger)
  local tag=$1 n=$2 pids=() p; shift 2
  for p in "$@"; do run $tag $p $n & pids+=($!); done
  wait "${pids[@]}"
}

phase "A: one process at a time"
run A 200023 3
run A 300007 3
run A 400051 3
run A 199873 3

phase "B4: 4 processes at 2e5"
parallel_runs B4 3 200131 200191 200227 200323

phase "B8: 8 processes at 2e5"
parallel_runs B8 3 200023 200371 200383 200407 200443 200467 200587 200671

phase "C3: 3 processes at 3e5"
parallel_runs C3 3 300007 300043 300151

phase "end"
kill $LOGGER
