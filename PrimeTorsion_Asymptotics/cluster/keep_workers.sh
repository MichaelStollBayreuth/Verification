#!/bin/bash
# Keep N worker jobs (pending or running) of the strange-prime search, as long
# as the queue has tasks that are not handed out yet (see README.md).
#   cluster/keep_workers.sh [N]     (N defaults to the number in queue/workers_target, else 10)
# Run in ~/strange-search, by hand or from scrontab (cluster/scrontab.txt).
# Then fill idle nodes with one-off extra workers (job name strange-extra, not
# replaced when they end), up to queue/max_jobs worker jobs in all (default 0:
# no extra workers), leaving queue/idle_reserve idle nodes (default 10) for
# others; only while none of our worker jobs is pending and our keeper job is
# not pending with reason Priority (other users' jobs are invisible on lipwig).
# DRY=1 only prints what would be submitted; MAX_JOBS and IDLE_RESERVE override the files.
# KEEPER_MIN_AGE=s (set by the workers' periodic call): do nothing if the script
# has run in the last s seconds (queue/keeper.last).
cd ~/strange-search || exit 1
# one run at a time (the extra workers end at about the same time); a lock older
# than 10 minutes is stale
lock=queue/keeper.lock
if ! mkdir "$lock" 2>/dev/null; then
  [ -n "$(find "$lock" -maxdepth 0 -mmin +10 2>/dev/null)" ] && rmdir "$lock" 2>/dev/null && mkdir "$lock" 2>/dev/null || exit 0
fi
trap 'rmdir "$lock" 2>/dev/null' EXIT
if [ -n "$KEEPER_MIN_AGE" ] && [ -f queue/keeper.last ] &&
   [ $(($(date +%s) - $(stat -c %Y queue/keeper.last))) -lt "$KEEPER_MIN_AGE" ]; then
  exit 0
fi
[ -n "$DRY" ] || touch queue/keeper.last
# pairs that workers with older code left in open/: proofs in characteristic 0 (kind C)
[ -n "$DRY" ] || python3 cluster/sweep_open.py --queue queue >> queue/sweep.log 2>&1
N=${1:-$(cat queue/workers_target 2>/dev/null || echo 10)}
M=${MAX_JOBS:-$(cat queue/max_jobs 2>/dev/null || echo 0)}
R=${IDLE_RESERVE:-$(cat queue/idle_reserve 2>/dev/null || echo 10)}
size() { stat -c %s "$1" 2>/dev/null || echo 0; }
pos() { cat "$1" 2>/dev/null || echo 0; }
submit() {  # submit [sbatch options]: print the job id (or what would be done)
  if [ -n "$DRY" ]; then echo "(dry run: sbatch $*)"; else sbatch --parsable "$@" cluster/worker.sbatch; fi
}
if [ "$(size queue/pairs.txt)" -le "$(pos queue/pairs.pos)" ] &&
   [ "$(size queue/requeue.txt)" -le "$(pos queue/requeue.pos)" ]; then
  exit 0  # nothing left to hand out
fi
# Our jobs, one squeue call: "id name state reason". If squeue fails (it did, briefly,
# on 2026-11-02: DNS), stop: an empty list would mean "no workers" and 20 new ones.
jobs=$(squeue --me -h -t PENDING,CONFIGURING,RUNNING -o "%i %j %T %r") || exit 1
# (a worker calling this at its end does not count itself; its periodic call does)
self=${SLURM_JOB_ID:-none}; [ -n "$KEEPER_MIN_AGE" ] && self=none
count() { awk -v names=",$1," -v self="$self" 'index(names, "," $2 ",") && $1 != self' <<< "$jobs" | wc -l; }
have=$(count strange-worker)
for ((i = have; i < N; i++)); do
  echo "$(date '+%F %T') $have of $N workers; submitted job $(submit)"
done

# extra workers on idle nodes
ours=$(count strange-worker,strange-extra)
[ "$ours" -lt "$M" ] || exit 0
[ "$(awk '($2 == "strange-worker" || $2 == "strange-extra") && $3 == "PENDING"' <<< "$jobs" | wc -l)" -eq 0 ] || exit 0
# squeue shows only our own jobs (PrivateData=jobs); our keeper job pending with
# reason Priority means that jobs of higher priority are waiting
[ "$(awk '$2 == "strange-keeper" && $3 == "PENDING" && $4 == "Priority"' <<< "$jobs" | wc -l)" -eq 0 ] || exit 0
ni=$(sinfo -h -p normal -N -o "%n %f %T") || exit 1
nodes=$(sort -u <<< "$ni" | grep -v '^r12g' | awk '$3 == "idle" || $3 == "idle~"')
big=$(grep -c 'EPYC-7352' <<< "$nodes")
std=$(grep -c 'EPYC-7302' <<< "$nodes")
n=$((M - ours)); [ $((big + std - R)) -lt $n ] && n=$((big + std - R))
[ "$n" -gt 0 ] || exit 0
nb=$((n < big ? n : big))
ids=""
for ((i = 0; i < n; i++)); do
  if [ "$i" -lt "$nb" ]; then f=EPYC-7352; else f=EPYC-7302; fi
  ids="$ids $(submit -J strange-extra --constraint=$f)"
done
echo "$(date '+%F %T') $ours of $M jobs, idle nodes: $big EPYC-7352, $std EPYC-7302 (keeping $R); extra workers ($nb on EPYC-7352):$ids"
