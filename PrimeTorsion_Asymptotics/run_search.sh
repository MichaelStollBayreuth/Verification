#!/bin/bash
# Search for strange primes p with LO <= p <= HI (default: 10^5 < p < 2*10^5),
# one Magma process per prime, at most NJ processes at a time, a new one only
# when MEMFREE memory is available (GNU parallel; --memfree also suspends the
# youngest job when memory runs low). Restartable: rerun the same command,
# finished primes are skipped (search.joblog). Results: res/1/<p>/stdout, one
# line "RESULT <p, candidates, verified>" each; collect them with
#   grep -h '^RESULT' res/1/*/stdout | sort -t'<' -k2 -n
# Failed jobs: exit code != 0 in search.joblog (search_job.sh checks Magma's output).
# Usage: ./run_search.sh [LO] [HI] [NJ] [MEMFREE]      (MAGMA=... to set the command)
LO=${1:-100001}; HI=${2:-200000}; NJ=${3:-12}; MEMFREE=${4:-30G}
MAGMA=${MAGMA:-magma}
cd "$(dirname "$0")" || exit 1
parallel --version 2>/dev/null | grep -q "GNU parallel" || { echo "GNU parallel is required (https://www.gnu.org/software/parallel/)"; exit 1; }
printf 'for p in PrimesInInterval(%s, %s) do print p; end for; quit;\n' "$LO" "$HI" | "$MAGMA" -b | grep -E '^[0-9]+$' > primes_${LO}_${HI}.txt
echo "$(wc -l < primes_${LO}_${HI}.txt) primes, $NJ processes, memfree $MEMFREE"
export MAGMA
parallel -j "$NJ" --memfree "$MEMFREE" --joblog search.joblog --resume-failed --results res/ \
  ./search_job.sh {} :::: primes_${LO}_${HI}.txt
ok=0; failed=""
for p in $(cat primes_${LO}_${HI}.txt); do
  if grep -q ' strange character(s) (' res/1/$p/stdout 2>/dev/null; then ok=$((ok + 1)); else failed="$failed $p"; fi
done
echo "done: $ok primes finished; not finished:${failed:- none}"
