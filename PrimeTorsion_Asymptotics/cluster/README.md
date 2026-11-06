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
regularly, and the regular workers (job name `strange-worker`) run it every
`keeper_s` seconds (config, default 1800) unless someone else has run it in the
meantime (`queue/keeper.last` is touched at each run).

`keep_workers.sh` also fills idle nodes with one-off extra workers (job name
`strange-extra`; they are not replaced when they end), up to `queue/max_jobs`
worker jobs in all and leaving `queue/idle_reserve` idle nodes (default 10) for
others, preferring the nodes with 250 GB. It does so only while none of our
worker jobs is pending and our keeper job is not pending with reason `Priority`.
(The jobs of other users are invisible on lipwig, `PrivateData=jobs`; a keeper
job waiting for `Priority` is the visible sign that jobs of higher priority are
waiting.) Without `queue/max_jobs` there are no extra workers.
`DRY=1 cluster/keep_workers.sh` shows what it would submit.

The queue can be extended at any time with `enqueue.py` (a new range of primes,
or `--pairs FILE` with lines `p n`); workers that are running pick up the new
tasks. To stop all workers from taking new tasks, set `"stop": true` in
`queue/config.json`; they finish their running tasks and exit.

## The queue

| file | meaning |
|---|---|
| `pairs.txt`, `pairs.pos` | the tasks `p n` (append-only) and the offset of the next one to hand out |
| `requeue.txt`, `requeue.pos` | tasks to be redone (served first): `S p n attempts` or `V p n attempts candidate` |
| `crt.txt`, `crt.pos` | proofs in characteristic 0 (served next): `C p n attempts [candidate]` |
| `running/p-n` | one file per running task: job id, host, pid, start time; touched every 5 minutes |
| `out/p-n.out` | Magma output of a running task |
| `done/SHARD/p-n.out` | Magma output of a finished task, with its `RESULT` line (`SHARD` = `p` div 1000) |
| `failed/p-n.out` | output of a task that ended with an error (not retried automatically) |
| `open/p-n.out` | output of a sparse screening (kind `N`) that did not certify its pair |
| `crt/` | results of the proofs in characteristic 0 (kind `C`): functionals, exact checks; `p-n.na`: not applicable |
| `logs/JOBID.log`, `logs/JOBID.tsv` | log of each worker; one line per finished task (time, memory, result) |
| `slurm/JOBID.out` | SLURM output of each worker |

The pointers and `requeue.txt` are only changed under a lock (the directory
`queue/lock`, created with `mkdir`, which is atomic on the shared file system).
A lock older than two minutes is broken. The PanFS client of a node can keep
an entry `queue/lock` that no longer exists on the server (`mkdir` then fails,
`rmdir` finds nothing, and the worker would wait for hours); a worker detects
this and makes the client drop the entry by renaming a directory onto it (see
`sq.Lock`).

## Tasks that do not finish regularly

- A task killed by a signal (e.g. by the kernel when the node runs out of
  memory) is requeued by its worker; this counts as an attempt.
- If the free memory of a node falls below `kill_below_gb`, the worker kills
  its youngest task and requeues it (also an attempt).
- If a task had already printed its `CANDIDATE` line, it is requeued as a
  verification-only task (`V`), so the screening is not repeated.
- If a worker disappears (time limit, `scancel`, node failure), its entries in
  `running/` are no longer touched; every worker checks for such entries every
  10 minutes and requeues their tasks once an entry has not been touched for
  `stale_s` (30 minutes), or for `gone_s` (15 minutes) if `squeue` no longer
  lists its job. (`squeue` alone is not trusted: during SLURM trouble it once
  omitted running jobs, and the tasks of two live workers were run twice.)
- On `SIGTERM` (cancellation) a worker kills its tasks and requeues them without
  counting an attempt; 30 minutes before its time limit (`SIGUSR1`) it stops
  taking tasks and requeues those that cannot finish in time.
- A worker stops taking tasks (drains) when a new pair from `pairs.txt` cannot
  finish before the end of its job. A requeued task that cannot (typically a
  verification, which takes many times as long) is moved to the end of
  `requeue.txt` for a worker with more time left, and the worker goes on with
  the next task (`sq.claim` with `accept`). (Before, every worker that met
  such a task drained.)
- A task with `max_attempts` (4) irregular ends goes to `failed/` (it may need a
  node with more memory); so does a task whose Magma run fails (error, or an
  unconfirmed candidate). After three failures in a row a worker stops taking
  tasks, so that a systematic problem cannot empty the queue.
- An exception in the worker itself (e.g. a file system error) is logged
  (`ERROR in ...`, at most once a minute per step) and the worker carries on;
  a task it loses track of is requeued by a janitor once its `running/` entry
  is stale. `keep_workers.sh` does nothing if `squeue` or `sinfo` fails (on
  lipwig's login node they sometimes fail for a while: DNS).
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

With `split_verify`, a screening task that finds a candidate stops after its
`CANDIDATE` line (`search_pair.m` with `verify:=no` then prints `SCREENED <p, n>`),
and the worker requeues the verification as a task of its own (`V`). It runs
with `magma_verify`, e.g. Magma's large binary: from about p = 4.2·10^5 on, the
standard binary crashes in the verification (a segmentation fault in
`Kernel`, a size limit), while the large one needed 96.5 GB at p = 4.26·10^5. A
verification counts with its full predicted peak for its whole run, since its
memory stays near it. A worker leaves a task that needs more than `alone_max`
times the memory of its node to a worker on a node with more memory; by the
model, a node with 128 GB takes verifications up to about p = 4.8·10^5.

## Sparse screening (tasks of kind `N`)

Beyond `p = 5·10^5` the modular symbols spaces of `search_pair.m` no longer fit
into the memory of a node. With `sparse_from` > 0 a worker runs every task of
kind `S` with `p >= sparse_from` as a task of kind `N`: screening with Najman's
method (`../sparse/`, see its README), with memory `O(p)` (0.9 GB at `p =
7·10^5`, 1.4 GB at `p = 10^6`) and about 3 and 5.5 minutes there on lipwig,
32 tasks per node. It certifies most pairs as not strange (result in `done/`,
as for `S`); a pair that it does not certify (strange, or `T_2` does not
separate) goes to `open/` (`UNCERTIFIED <p, n, k, L, chi(2) = 1>`), and if `p
<= magma_max_p` it is requeued and then runs as `S` (`search_pair.m`), since
`open/` has it. In the queue files the task remains of kind `S` (also when a
task of kind `N` is requeued), so workers with older code can run it as well.
A task of kind `N` runs in a process group of its own, so that killing it also
kills its steps. `status.py` and `audit.py` count the pairs in `open/`. The
programs in `sparse/bin` are built with `sparse/build.sh` on a node (NTL in
`~/sw/ntl`).

## Proofs in characteristic 0 (tasks of kind `C`)

With `crt_verify` set, a pair that the sparse screening did not certify is
requeued as a task of kind `C` (in `crt.txt`, which workers with older code
do not read): `sparse/crt_verify.py` proves its strangeness in characteristic
0 by Chinese remaindering (see `../sparse/README.md`), with `crt_jobs` CPUs
(memory and time: `crt_jobs` and `crt_time_factor` times those of a task of
kind `N`); about 5 minutes with 16 CPUs at `p = 4.5·10^5`. Its result goes to
`done/` like that of `search_pair.m` (`RESULT <p, n, [], [<n, strdim, orbit
sizes, true>]>`, no candidate). A task of kind `V` (verification with Magma)
is also run as kind `C`. If the proof is not applicable (`T_2` not cyclic on
`S`, e.g. for `n = 2` with `chi(2) = 1`), `crt/p-n.na` records it, and the
pair goes back to Magma: as `V` if it has a candidate, as `S` if `p <=
magma_max_p`, otherwise it stays in `open/`. A worker does not run a task
whose pair is in `done/` already. `sbatch cluster/crt.sbatch [p n ...]` runs
`crt_verify.py` by hand for the pairs in `open/` (or those given).

## Calibration

`calib.sbatch` measured time and memory of single characters on one node
(October 2026, Magma V2.30-1, AMD EPYC 7302): at p = 2, 3, 4·10^5 one character
takes 234, 484, 761 s with a peak of 12.9, 28.9, 51.4 GB; up to 8 processes per
node do not slow each other down.
