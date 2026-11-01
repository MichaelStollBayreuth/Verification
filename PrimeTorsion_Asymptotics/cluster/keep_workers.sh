#!/bin/bash
# Keep N worker jobs (pending or running) of the strange-prime search, as long
# as the queue has tasks that are not handed out yet (see README.md).
#   cluster/keep_workers.sh [N]     (N defaults to the number in queue/workers_target, else 10)
# Run in ~/strange-search, by hand or from scrontab (cluster/scrontab.txt).
# Then fill idle nodes with one-off extra workers (job name strange-extra, not
# replaced when they end), up to queue/max_jobs worker jobs in all (default 0:
# no extra workers), leaving queue/idle_reserve idle nodes (default 10) for
# others; only while no job of another user and none of ours is pending.
# DRY=1 only prints what would be submitted; MAX_JOBS and IDLE_RESERVE override the files.
cd ~/strange-search || exit 1
# one run at a time (the extra workers end at about the same time); a lock older
# than 10 minutes is stale
lock=queue/keeper.lock
if ! mkdir "$lock" 2>/dev/null; then
  [ -n "$(find "$lock" -maxdepth 0 -mmin +10 2>/dev/null)" ] && rmdir "$lock" 2>/dev/null && mkdir "$lock" 2>/dev/null || exit 0
fi
trap 'rmdir "$lock" 2>/dev/null' EXIT
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
# (a worker calling this at its end does not count itself)
count() { squeue --me -h -n "$1" -t PENDING,CONFIGURING,RUNNING -o %i | grep -v -x "${SLURM_JOB_ID:-none}" | wc -l; }
have=$(count strange-worker)
for ((i = have; i < N; i++)); do
  echo "$(date '+%F %T') $have of $N workers; submitted job $(submit)"
done

# extra workers on idle nodes
ours=$(count strange-worker,strange-extra)
[ "$ours" -lt "$M" ] || exit 0
[ "$(squeue -h -p normal -t PENDING -o %u | grep -v -x "$USER" | wc -l)" -eq 0 ] || exit 0
[ "$(squeue --me -h -n strange-worker,strange-extra -t PENDING -o %i | wc -l)" -eq 0 ] || exit 0
nodes=$(sinfo -h -p normal -N -o "%n %f %T" | sort -u | grep -v '^r12g' | awk '$3 == "idle" || $3 == "idle~"')
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
