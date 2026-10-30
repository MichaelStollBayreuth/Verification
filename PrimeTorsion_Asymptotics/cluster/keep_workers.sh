#!/bin/bash
# Keep N worker jobs (pending or running) of the strange-prime search, as long
# as the queue has tasks that are not handed out yet (see README.md).
#   cluster/keep_workers.sh [N]     (N defaults to the number in queue/workers_target, else 10)
# Run in ~/strange-search, by hand or from scrontab (cluster/scrontab.txt).
cd ~/strange-search || exit 1
N=${1:-$(cat queue/workers_target 2>/dev/null || echo 10)}
size() { stat -c %s "$1" 2>/dev/null || echo 0; }
pos() { cat "$1" 2>/dev/null || echo 0; }
if [ "$(size queue/pairs.txt)" -le "$(pos queue/pairs.pos)" ] &&
   [ "$(size queue/requeue.txt)" -le "$(pos queue/requeue.pos)" ]; then
  exit 0  # nothing left to hand out
fi
# (a worker calling this at its end does not count itself)
have=$(squeue --me -h -n strange-worker -t PENDING,RUNNING -o %i | grep -v -x "${SLURM_JOB_ID:-none}" | wc -l)
for ((i = have; i < N; i++)); do
  echo "$(date '+%F %T') $have of $N workers; submitted job $(sbatch --parsable cluster/worker.sbatch)"
done
