# Strange-prime search on a SLURM cluster

Scripts for continuing the search for strange primes (see `strange_primes.magma`)
on the cluster lipwig of the University of Bayreuth, one task per pair (prime
`p`, character order `n`), with a shared queue that can grow while the search
runs. Written by Claude Code (Opus 5.5), October 2026.

## Layout on the cluster

Everything lives in `~/strange-search` on the shared file system:

| path | contents |
|---|---|
| `strange_primes.magma`, `search_pair.m` | the Magma code (one pair per process) |
| `cluster/` | these scripts |
| `queue/` | the queue and all results (created by `enqueue.py`) |
| `queue/config.json` | parameters of the workers (re-read every minute) |

One **task** is `search_pair.m` for one pair: screening the even character of
order `n` mod `p` and, if it is a candidate, verifying it. Each **worker** is a
SLURM job on a whole node (`--exclusive`: lipwig schedules cores only, not
memory, so jobs sharing a node could run it out of memory). It runs as many
tasks at a time as the memory of the node allows, takes the next task from the
queue whenever one finishes, and stops taking tasks when its time limit is
near.

## Usage

```bash
cd ~/strange-search
python3 cluster/enqueue.py --queue queue 200001 300000   # all pairs for these primes
sbatch cluster/worker.sbatch                             # one worker (repeat for more)
cluster/keep_workers.sh 10                               # keep 10 workers queued or running
python3 cluster/status.py --queue queue --strange        # progress, strange pairs found
python3 cluster/audit.py --queue queue --results results.txt   # completeness check, all results
```

`scrontab cluster/scrontab.txt` runs `keep_workers.sh` every 30 minutes, with the
number of workers taken from `queue/workers_target`; since such a job can wait
long on a full cluster, each worker also runs `keep_workers.sh` when it ends
regularly.

The queue can be extended at any time with `enqueue.py` (a new range of primes,
or `--pairs FILE` with lines `p n`); workers that are running pick up the new
tasks. To stop all workers from taking new tasks, set `"stop": true` in
`queue/config.json`; they finish their running tasks and exit.

## The queue

| file | meaning |
|---|---|
| `pairs.txt`, `pairs.pos` | the tasks `p n` (append-only) and the offset of the next one to hand out |
| `requeue.txt`, `requeue.pos` | tasks to be redone (served first): `S p n attempts` or `V p n attempts candidate` |
| `running/p-n` | one file per running task: job id, host, pid, start time; touched every 5 minutes |
| `out/p-n.out` | Magma output of a running task |
| `done/SHARD/p-n.out` | Magma output of a finished task, with its `RESULT` line (`SHARD` = `p` div 1000) |
| `failed/p-n.out` | output of a task that ended with an error (not retried automatically) |
| `logs/JOBID.log`, `logs/JOBID.tsv` | log of each worker; one line per finished task (time, memory, result) |
| `slurm/JOBID.out` | SLURM output of each worker |

The pointers and `requeue.txt` are only changed under a lock (the directory
`queue/lock`, created with `mkdir`, which is atomic on the shared file system).

## Tasks that do not finish regularly

- A task killed by a signal (e.g. by the kernel when the node runs out of
  memory) is requeued by its worker; this counts as an attempt.
- If the free memory of a node falls below `kill_below_gb`, the worker kills
  its youngest task and requeues it (also an attempt).
- If a task had already printed its `CANDIDATE` line, it is requeued as a
  verification-only task (`V`), so the screening is not repeated.
- If a worker disappears (time limit, `scancel`, node failure), its entries in
  `running/` belong to a job that is no longer running, or are no longer
  touched; every worker checks for such entries every 10 minutes (with
  `squeue`) and requeues their tasks.
- On `SIGTERM` (cancellation) a worker kills its tasks and requeues them without
  counting an attempt; 30 minutes before its time limit (`SIGUSR1`) it stops
  taking tasks and requeues those that cannot finish in time.
- A task with `max_attempts` (4) irregular ends goes to `failed/` (it may need a
  node with more memory); so does a task whose Magma run fails (error, or an
  unconfirmed candidate). After three failures in a row a worker stops taking
  tasks, so that a systematic problem cannot empty the queue.
- `audit.py` checks that every pair in `pairs.txt` has a result in `done/`, and
  lists pairs that are neither done, running, waiting nor failed (`--requeue`
  puts them back).

## Parameters (`queue/config.json`)

Defaults are in `worker.py` (`DEFAULTS`); the file only needs the values that
differ. A task needs much memory only while it builds the modular symbols
space, during its first `peak_s (p/200000)^peak_exp` seconds (up to
`peak_a (p/200000)^mem_exp` GiB), and `steady_a (p/200000)^mem_exp` GiB
afterwards (measured on lipwig at p = 2.1·10^5: about 45 s with a peak of
14 GiB, then 1.1–2.2 GiB). A worker starts a task only if the memory of its
running tasks (young ones counted with `young_frac` times their peak, the
others with their steady-state memory) plus the peak of the new one stays below
the node's memory minus `reserve_gb`; at most `max_procs` tasks (default: one
per CPU), at most one start per `delay_s` seconds, and only if `time_safety`
times the predicted time `time_a (p/200000)^time_exp` seconds fits before the
end of the job. Verification tasks count with `verify_mem_factor` and
`verify_time_factor`. A task whose predicted peak exceeds the memory of the node
(from about p = 4.9·10^5 on for verifications on a node with 128 GB) is run alone:
the worker starts no other task until all its running tasks have ended. Capacity of a node with 128 GB: about 30 tasks at
p = 2.1·10^5, 18 at 2.5·10^5, 12 at 3·10^5 (memory, not the 32 cores, is the
limit beyond about 2.2·10^5).

## Calibration

`calib.sbatch` measured time and memory of single characters on one node
(October 2026, Magma V2.30-1, AMD EPYC 7302): at p = 2, 3, 4·10^5 one character
takes 234, 484, 761 s with a peak of 12.9, 28.9, 51.4 GB; up to 8 processes per
node do not slow each other down.
