#!/usr/bin/env python3
"""Worker of the strange-prime search: runs on one (whole) node, takes tasks
(p, n) from the shared queue (sq.py) and runs search_pair.m for each, as many
at a time as the memory of the node allows. See README.md.

  python3 worker.py --queue Q --code CODE [--magma MAGMA] [--hours H]

Inside a SLURM job the end of the job is taken from SLURM; --hours is for
runs outside SLURM (tests). The parameters in Q/config.json are re-read
every minute, so they can be changed while the workers run.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sq  # noqa: E402

DEFAULTS = dict(
    max_procs=0,          # 0: one per CPU of the node
    reserve_gb=4.0,       # memory (GiB) kept free when admitting a task
    kill_below_gb=2.5,    # below this much available memory, kill the youngest task
    delay_s=8,            # minimum time between two starts on this node
    # Memory (GiB) of a task: up to peak_a (p/2e5)^mem_exp + mem_b while it builds
    # the modular symbols space, during its first peak_s (p/2e5)^peak_exp seconds
    # (measured on lipwig: the peak is reached about 40 s after the start at
    # p = 2e5), then steady_a (p/2e5)^mem_exp + mem_b (search_pair.m frees the
    # space after the setup; with the earlier code steady_a was 9.5).
    # A young task counts with young_frac times its peak (its memory grows during
    # the setup and stays near the peak for a few seconds only; measured average
    # about 45 %), the new task with its full peak.
    peak_a=12.6, steady_a=2.0, mem_b=0.0, mem_exp=2.0, peak_s=45, peak_exp=2.0, young_frac=0.6,
    time_a=235.0, time_exp=1.75,             # predicted run time (s): time_a (p/2e5)^time_exp
    # A verification (task with a candidate) takes 12-20 times the predicted screening
    # time (measured on lipwig for 2.0e5 < p < 2.8e5); its memory stays near its peak,
    # which was 96.5 GB, 1.7 times the predicted screening peak, at p = 4.26e5 (with
    # Magma's large binary; the standard one crashes there).
    verify_mem_factor=1.8, verify_time_factor=20.0,
    split_verify=False,   # true: a screening that finds a candidate stops there, and the
                          # verification becomes a task of its own (V)
    magma_verify="",      # the Magma command for V tasks (e.g. the large binary; "": --magma)
    alone_max=1.05,       # a task predicted to need more than alone_max times the memory
                          # of the node is left for a node with more memory
    sparse_from=0,        # a task of kind S with p >= sparse_from (if > 0) is run as kind N:
                          # screening with Najman's sparse method (sparse/sparse_pair.py;
                          # see sparse/README.md), unless open/ has it already
    # Tasks of kind N need sparse_mem_a + sparse_mem_b x GiB and sparse_time_a x +
    # sparse_time_b x^2 seconds, x = p/1e6 (measured on lipwig with 32 tasks per node:
    # 0.9 GB, 2.9 min at p = 7e5; 1.4 GB at p = 1e6).
    sparse_mem_a=0.3, sparse_mem_b=1.2, sparse_time_a=85.0, sparse_time_b=245.0,
    magma_max_p=0,        # an N task that does not certify its pair goes to open/ and,
                          # if p <= magma_max_p, is requeued as an S task, which then runs
                          # search_pair.m (open/ has it); with crt_verify only if the proof
                          # in characteristic 0 is not applicable
    crt_verify=False,     # true: such a pair is requeued as a task of kind C (crt_verify.py,
                          # proof of strangeness in characteristic 0), and a task of kind V
                          # is run as kind C unless crt/p-n.na says that it is not applicable
    crt_jobs=8,           # CPUs of a task of kind C; its memory and time: crt_jobs and
    crt_time_factor=8.0,  # crt_time_factor times those of a task of kind N
    time_safety=1.5,      # start a task only if time_safety * predicted time fits
    end_margin_s=300,     # ... before the end of the job minus this margin
    max_attempts=4,       # irregular ends of a task before it is given up (failed/)
    stale_s=1800,         # a running/ entry not touched for this long is dead
    gone_s=900,           # ... and one of a job that squeue does not list after this long
                          # (squeue alone is not trusted: on 2026-11-04 it omitted running jobs)
    heartbeat_s=300, janitor_s=600, config_s=60, memlog_s=300, loop_s=5,
    keeper_s=1800,        # regular workers run keep_workers.sh if nobody has for this long (0: never)
    stop=False,           # true: no worker starts new tasks
)

def predicted_mem(c, t, peak=False):
    """Predicted memory (GiB) of task t under the parameters c: steady state, or its peak."""
    if t["kind"] in ("N", "C"):
        m = c["sparse_mem_a"] + c["sparse_mem_b"] * t["p"] / 1e6
        return m * (c["crt_jobs"] if t["kind"] == "C" else 1)
    a = c["peak_a"] if peak else c["steady_a"]
    m = a * (t["p"] / 2e5) ** c["mem_exp"] + c["mem_b"]
    return m * (c["verify_mem_factor"] if t["kind"] == "V" else 1)


def predicted_time(c, t):
    """Predicted run time (s) of task t under the parameters c."""
    if t["kind"] in ("N", "C"):
        x = t["p"] / 1e6
        s = c["sparse_time_a"] * x + c["sparse_time_b"] * x * x
        return s * (c["crt_time_factor"] if t["kind"] == "C" else 1)
    s = c["time_a"] * (t["p"] / 2e5) ** c["time_exp"]
    return s * (c["verify_time_factor"] if t["kind"] == "V" else 1)


FINAL = re.compile(r"^p = (\d+), n = (\d+): (not strange|STRANGE, strdim (\d+)) \(([\d.]+) s, (\d+) MB\)\s*$", re.M)


def meminfo():
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0])  # kB
    return m["MemTotal"] / 2**20, m["MemAvailable"] / 2**20  # GB


def vm_kb(pid, key):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith(key + ":"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        pass
    return 0


class Worker:
    def __init__(self, args):
        self.Q = os.path.abspath(args.queue)
        self.code = os.path.abspath(args.code)
        self.magma = args.magma
        sq.ensure_dirs(self.Q)
        self.slurm = "SLURM_JOB_ID" in os.environ
        self.jobid = os.environ.get("SLURM_JOB_ID") or "local-%s-%d" % (sq.HOST, os.getpid())
        self.logf = open(sq.qpath(self.Q, "logs", self.jobid + ".log"), "a")
        self.tsv = open(sq.qpath(self.Q, "logs", self.jobid + ".tsv"), "a")
        self.end = self.job_end(args.hours)
        self.cfg = dict(DEFAULTS)
        self.cfg_time = 0
        self.read_config()
        self.children = []       # dicts: task, name, proc, start, pmem, ptime, killed, hwm
        self.held = None         # claimed task waiting for memory
        self.alone_note = None   # task logged as "too big for the model: run alone"
        self.empty = False       # the queue was empty at the last claim
        self.last_claim_try = 0
        self.last_start = 0
        self.draining = False    # no new tasks (end of the job is near, or stop)
        self.terminate = False
        self.failures = []       # times of recent failures (circuit breaker)
        self.regular = os.environ.get("SLURM_JOB_NAME") == "strange-worker"
        self.keeper_proc = None  # periodic keep_workers.sh, running in the background
        self.err_logged = {}     # step -> time of the last logged exception (safely)
        self.t_heartbeat = self.t_janitor = self.t_memlog = self.t_keeper = time.time()
        signal.signal(signal.SIGUSR1, self.on_usr1)
        signal.signal(signal.SIGTERM, self.on_term)
        signal.signal(signal.SIGINT, self.on_term)
        cpus = len(os.sched_getaffinity(0))
        total, avail = meminfo()
        self.log("worker %s on %s: %d CPUs, %.1f GB total, %.1f GB available, end in %.1f h, code %s"
                 % (self.jobid, sq.HOST, cpus, total, avail, (self.end - time.time()) / 3600, self.code))

    # ---------------------------------------------------------------- utilities
    def log(self, msg):
        try:
            self.logf.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
            self.logf.flush()
        except OSError:
            pass

    def safely(self, step, *args):
        """Run one step of the main loop; an exception (e.g. a file system
        error on PanFS, which ended two workers on 2026-11-02 in the janitor)
        is logged, at most once a minute per step, instead of ending the
        worker. A task lost track of that way is requeued by a janitor once
        its running/ entry is stale."""
        try:
            return step(*args)
        except Exception:
            name = step.__name__
            if time.time() - self.err_logged.get(name, 0) > 60:
                self.err_logged[name] = time.time()
                self.log("ERROR in %s (the worker continues): %s"
                         % (name, traceback.format_exc().strip().replace("\n", " | ")))

    def job_end(self, hours):
        if self.slurm:
            e = os.environ.get("SLURM_JOB_END_TIME")
            if e and e.isdigit():
                return int(e)
            try:
                out = subprocess.run(["squeue", "-h", "-j", self.jobid, "-o", "%e"], capture_output=True,
                                     text=True, timeout=60).stdout.strip()
                return time.mktime(time.strptime(out, "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                pass
        return time.time() + 3600 * hours

    def read_config(self):
        path = sq.qpath(self.Q, "config.json")
        try:
            with open(path) as f:
                new = json.load(f)
        except FileNotFoundError:
            new = {}
        except ValueError as e:
            self.log("config.json not readable (%s); keeping the old parameters" % e)
            return
        cfg = dict(DEFAULTS)
        cfg.update(new)
        if cfg != self.cfg:
            changed = {k: cfg[k] for k in cfg if cfg[k] != self.cfg.get(k)}
            if self.cfg_time:
                self.log("config changed: %s" % changed)
        self.cfg = cfg
        self.cfg_time = time.time()

    def max_procs(self):
        return self.cfg["max_procs"] or len(os.sched_getaffinity(0))

    def pred_mem(self, t, peak=False):
        """Predicted memory (GiB) of task t: steady state, or its peak."""
        return predicted_mem(self.cfg, t, peak)

    def peak_window(self, t):
        return self.cfg["peak_s"] * (t["p"] / 2e5) ** self.cfg["peak_exp"]

    def pred_time(self, t):
        return predicted_time(self.cfg, t)

    def running_path(self, t):
        return sq.qpath(self.Q, "running", sq.name_of(t["p"], t["n"]))

    def out_path(self, t):
        return sq.qpath(self.Q, "out", sq.name_of(t["p"], t["n"]) + ".out")

    def mark_running(self, t, pid):
        sq.write_atomic(self.running_path(t), "%s %s %d %d %s %d\n%s\n"
                        % (self.jobid, sq.HOST, pid, int(time.time()), t["kind"], t["attempts"], sq.task_line(t)))

    def unmark(self, t):
        try:
            os.remove(self.running_path(t))
        except FileNotFoundError:
            pass

    # ---------------------------------------------------------------- tasks
    def start(self, t):
        if t["kind"] == "N":
            # (in a process group of its own, so that a kill reaches its steps)
            cmd = [sys.executable, os.path.join(self.code, "sparse", "sparse_pair.py"),
                   str(t["p"]), str(t["n"]), "--magma", self.magma]
            how = ", sparse"
        elif t["kind"] == "C":
            os.makedirs(sq.qpath(self.Q, "crt"), exist_ok=True)
            cmd = [sys.executable, os.path.join(self.code, "sparse", "crt_verify.py"), str(t["p"]), str(t["n"]),
                   "--magma", self.magma, "--jobs", str(self.slots(t)), "--out", sq.qpath(self.Q, "crt")]
            how = ", proof in characteristic 0 with %d CPUs" % self.slots(t)
        else:
            if t["kind"] == "V":
                cmd = [self.cfg["magma_verify"] or self.magma, "-b", "cand:=" + t["cand"]]
            else:
                cmd = [self.magma, "-b", "p:=%d" % t["p"], "n:=%d" % t["n"]]
                if self.cfg["split_verify"]:
                    cmd.append("verify:=no")
            cmd.append("search_pair.m")
            how = "" if cmd[0] == self.magma else ", with " + cmd[0]
        # (a verification appends to the output of its screening, if any)
        out = open(self.out_path(t), "a" if t["kind"] == "V" else "w")
        proc = subprocess.Popen(cmd, cwd=self.code, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=(t["kind"] in ("N", "C")))
        out.close()
        self.mark_running(t, proc.pid)
        self.children.append(dict(task=t, name=sq.name_of(t["p"], t["n"]), proc=proc, start=time.time(),
                                  pmem=self.pred_mem(t), ptime=self.pred_time(t), killed=None, hwm=0))
        self.last_start = time.time()
        self.log("start %s (%s, attempt %d) pid %d, predicted %.1f GB, %.0f s%s"
                 % (sq.name_of(t["p"], t["n"]), t["kind"], t["attempts"], proc.pid,
                    self.children[-1]["pmem"], self.children[-1]["ptime"], how))

    def give_back(self, t, why, irregular):
        """Requeue task t. A screening task whose candidate was already printed
        becomes a verification task (also at the end of the job, so that the
        screening is not repeated and the task is scheduled with the time of a
        verification); after an irregular end (irregular true) its attempts are
        counted."""
        t = dict(t)
        if t["kind"] == "S":
            cand = sq.candidate_from_output(self.out_path(t))
            if cand:
                t["kind"], t["cand"] = "V", cand
        if irregular:
            t["attempts"] += 1
            if t["attempts"] >= self.cfg["max_attempts"]:
                self.fail(t, "gave up after %d irregular ends (last: %s)" % (t["attempts"], why))
                return
        sq.requeue(self.Q, [t], log=self.log)
        self.empty = False  # (the queue has this task now)
        self.unmark(t)
        self.log("requeued %s (%s, attempts %d): %s" % (sq.name_of(t["p"], t["n"]), t["kind"], t["attempts"], why))

    def fail(self, t, why, own=True):
        name = sq.name_of(t["p"], t["n"])
        dest = sq.qpath(self.Q, "failed", name + ".out")
        try:
            os.replace(self.out_path(t), dest)
        except FileNotFoundError:
            pass
        with open(dest, "a") as f:
            f.write("# worker %s on %s: %s\n# task: %s\n" % (self.jobid, sq.HOST, why, sq.task_line(t)))
        self.unmark(t)
        self.tsv_line(t, 0, 0, 0, 0, "FAILED")
        self.log("FAILED %s: %s" % (name, why))
        if own:
            self.failures.append(time.time())

    def uncertified(self, t, out, wall):
        """An N task that did not certify its pair: its output goes to open/, and
        with p <= magma_max_p the pair is requeued as an S task (search_pair.m)."""
        name = sq.name_of(t["p"], t["n"])
        m = re.search(r"^UNCERTIFIED <(.*)>", out, re.M)
        crt = self.cfg["crt_verify"]
        magma = not crt and t["p"] <= self.cfg["magma_max_p"]
        how = "; requeued as C" if crt else "; requeued as S" if magma else ""
        dest = sq.qpath(self.Q, "open", name + ".out")
        os.replace(self.out_path(t), dest)
        with open(dest, "a") as f:
            f.write("# worker %s on %s: not certified%s\n" % (self.jobid, sq.HOST, how))
        if crt or magma:
            sq.requeue(self.Q, [dict(t, kind="C" if crt else "S", attempts=0)], log=self.log)
            self.empty = False
        self.unmark(t)
        self.tsv_line(t, wall, 0, 0, 0, "UNCERTIFIED")
        self.log("%s not certified by the sparse method (p, n, k, L, chi(2) = 1: %s)%s"
                 % (name, m.group(1) if m else "?", how or "; see open/"))

    def not_applicable(self, t, out, wall):
        """A task of kind C whose proof is not applicable (T_2 not cyclic on S): crt/p-n.na
        records it; then the candidate, if any, is verified with Magma (V), and otherwise
        the pair is screened with Magma (S) if p <= magma_max_p, or stays in open/."""
        name = sq.name_of(t["p"], t["n"])
        with open(sq.qpath(self.Q, "crt", name + ".na"), "w") as f:
            f.write(out)
        if t["cand"]:
            t2, how = dict(t, kind="V", attempts=0), "requeued as V"
        elif t["p"] <= self.cfg["magma_max_p"]:
            t2, how = dict(t, kind="S", attempts=0), "requeued as S"
        else:
            t2, how = None, "see open/"
        if t2:
            sq.requeue(self.Q, [t2], log=self.log)
            self.empty = False
        try:
            os.remove(self.out_path(t))
        except FileNotFoundError:
            pass
        self.unmark(t)
        self.tsv_line(t, wall, 0, 0, 0, "CRT_NOT_APPLICABLE")
        self.log("%s: proof in characteristic 0 not applicable (T_2 not cyclic on S); %s" % (name, how))

    def signal_task(self, c, sig):
        """Send sig to task c (to the whole process group of an N task)."""
        try:
            if c["task"]["kind"] in ("N", "C"):
                os.killpg(c["proc"].pid, sig)
            elif c["proc"].poll() is None:
                c["proc"].send_signal(sig)
        except ProcessLookupError:
            pass

    def tsv_line(self, t, wall, cpu, peak_mb, hwm_mb, result):
        self.tsv.write("%d\t%s\t%s\t%d\t%s\t%.0f\t%s\t%s\t%d\t%s\n"
                       % (time.time(), sq.name_of(t["p"], t["n"]), t["kind"], t["attempts"], sq.HOST,
                          wall, cpu, peak_mb, hwm_mb, result))
        self.tsv.flush()

    def reap(self):
        for c in list(self.children):
            rc = c["proc"].poll()
            if rc is None:
                c["hwm"] = max(c["hwm"], vm_kb(c["proc"].pid, "VmHWM"))
                continue
            self.children.remove(c)
            t, wall = c["task"], time.time() - c["start"]
            try:
                with open(self.out_path(t)) as f:
                    out = f.read()
            except FileNotFoundError:
                out = ""
            m = FINAL.search(out)
            if rc == 0 and m and "\nRESULT " in "\n" + out and int(m.group(1)) == t["p"] and int(m.group(2)) == t["n"]:
                dest = sq.done_path(self.Q, t["p"], t["n"])
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                os.replace(self.out_path(t), dest)
                self.unmark(t)
                result = "not" if m.group(3) == "not strange" else "STRANGE %s" % m.group(4)
                self.tsv_line(t, wall, m.group(5), m.group(6), c["hwm"] // 1024, result)
                self.log("done %s in %.0f s: %s (cpu %s s, peak %s MB, hwm %d MB)"
                         % (c["name"], wall, m.group(3), m.group(5), m.group(6), c["hwm"] // 1024))
                self.failures = []
            elif (rc == 0 and t["kind"] == "S" and "\nSCREENED " in "\n" + out
                  and sq.candidate_from_output(self.out_path(t))):
                # (split_verify: the candidate is verified by a task of its own)
                self.log("candidate %s after %.0f s (screening); verification as a task of its own"
                         % (c["name"], wall))
                self.give_back(t, "candidate, to be verified", irregular=False)
                self.failures = []
            elif rc == 0 and t["kind"] == "N" and "\nUNCERTIFIED " in "\n" + out:
                self.uncertified(t, out, wall)
                self.failures = []
            elif rc == 0 and t["kind"] == "C" and "\nCRT_NOT_APPLICABLE " in "\n" + out:
                self.not_applicable(t, out, wall)
                self.failures = []
            elif c["killed"]:
                self.give_back(t, c["killed"], irregular=(c["killed"] == "memory"))
            elif rc < 0:
                # (when the whole job is being cancelled, SLURM signals the tasks directly)
                self.give_back(t, "killed by signal %d after %.0f s" % (-rc, wall), irregular=not self.terminate)
            else:
                self.fail(t, "exit code %d after %.0f s" % (rc, wall))

    def kill(self, c, why):
        if c["killed"]:
            return
        c["killed"] = why
        c["kill_t"] = time.time()
        self.signal_task(c, signal.SIGTERM)
        self.log("killing %s (%s)" % (c["name"], why))

    def memory_guard(self):
        total, avail = meminfo()
        if avail < self.cfg["kill_below_gb"]:
            alive = [c for c in self.children if not c["killed"]]
            if len(alive) > 1:
                self.kill(max(alive, key=lambda c: c["start"]), "memory")
        # escalate: SIGKILL for tasks that ignore SIGTERM for 30 s
        for c in self.children:
            if c["killed"] and c["proc"].poll() is None and time.time() - c["kill_t"] > 30:
                self.signal_task(c, signal.SIGKILL)

    def admissible(self, t):
        # Young tasks (still building the modular symbols space) count with
        # young_frac times their peak memory, the others with their steady-state
        # memory, verifications with their peak all the time (their memory stays
        # near it); the new task needs its peak.
        total, avail = meminfo()
        now = time.time()
        committed = sum(self.pred_mem(c["task"], True) if c["task"]["kind"] == "V"
                        else self.cfg["young_frac"] * self.pred_mem(c["task"], True)
                        if now - c["start"] < self.peak_window(c["task"]) else self.pred_mem(c["task"])
                        for c in self.children if not c["killed"])
        need = self.pred_mem(t, True)
        cap = total - self.cfg["reserve_gb"]
        if need > cap:
            # By the model the task never fits on this node (verifications from
            # about 4.9e5 on, on a 128 GB node; the model overestimates their
            # peak by about 25 %). Run it alone: wait until no other task runs.
            name = sq.name_of(t["p"], t["n"])
            if self.alone_note != name:
                self.alone_note = name
                self.log("%s: predicted peak %.0f GiB exceeds this node (%.0f GiB); "
                         "running it alone when the other tasks have ended" % (name, need, cap))
            return not any(not c["killed"] for c in self.children)
        return committed + need <= cap and avail - need >= self.cfg["reserve_gb"] / 2

    def time_ok(self, t):
        return time.time() + self.cfg["time_safety"] * self.pred_time(t) <= self.end - self.cfg["end_margin_s"]

    def sparse_kind(self, t):
        """Kind N for a task of kind S with p >= sparse_from, unless the sparse
        method has already failed to certify it (open/p-n.out exists); kind C for
        such a task and for one of kind V if crt_verify, unless the proof in
        characteristic 0 is not applicable (crt/p-n.na exists)."""
        f, name = self.cfg["sparse_from"], sq.name_of(t["p"], t["n"])
        crt = self.cfg["crt_verify"] and not os.path.exists(sq.qpath(self.Q, "crt", name + ".na"))
        if t["kind"] == "S" and f and t["p"] >= f:
            if not os.path.exists(sq.qpath(self.Q, "open", name + ".out")):
                t = dict(t, kind="N")
            elif crt:  # (screened sparsely, not certified: e.g. requeued by a worker without kind C)
                t = dict(t, kind="C")
        if t["kind"] == "V" and crt:
            t = dict(t, kind="C")
        return t

    def slots(self, t):
        """CPUs that task t occupies."""
        return min(self.cfg["crt_jobs"], self.max_procs()) if t["kind"] == "C" else 1

    def can_take(self, t):
        """Whether this worker can run task t: it finishes in time, and it does
        not need much more memory than the node has (verifications at large p;
        a node with more memory takes them)."""
        return self.time_ok(t) and self.pred_mem(t, True) <= self.cfg["alone_max"] * meminfo()[0]

    def maybe_start(self):
        c = self.cfg
        if self.draining or c["stop"] or self.breaker():
            if self.held:
                self.give_back(self.held, "worker stops taking tasks", irregular=False)
                self.held = None
            return
        if (sum(self.slots(ch["task"]) for ch in self.children) >= self.max_procs()
                or time.time() - self.last_start < c["delay_s"]):
            return
        if self.held is None:
            if self.empty and time.time() - self.last_claim_try < 120:
                return
            self.last_claim_try = time.time()
            # (a requeued task that does not fit in the remaining time or in the
            # memory of the node is left for another worker; only a new pair
            # that does not fit in the remaining time drains)
            t = sq.claim(self.Q, log=self.log, accept=self.can_take, convert=self.sparse_kind)
            self.empty = t is None
            if t is None:
                return
            if os.path.exists(sq.done_path(self.Q, t["p"], t["n"])):
                # (e.g. a verification of a pair that was proved strange otherwise)
                self.log("%s (%s) is done already; not run" % (sq.name_of(t["p"], t["n"]), t["kind"]))
                return
            self.mark_running(t, 0)
            self.held = t
        t = self.held
        if not self.time_ok(t):
            self.log("not enough time left for %s (predicted %.0f s); draining" % (sq.name_of(t["p"], t["n"]), self.pred_time(t)))
            self.draining = True
            self.give_back(t, "not enough time left in this job", irregular=False)
            self.held = None
            return
        if sum(self.slots(ch["task"]) for ch in self.children) + self.slots(t) > self.max_procs():
            return  # (a task of kind C waits for its CPUs)
        if self.admissible(t):
            self.held = None
            self.start(t)

    def breaker(self):
        """Circuit breaker: three failures within 10 minutes without a success
        in between stop this worker from taking new tasks."""
        recent = [x for x in self.failures if time.time() - x < 600]
        if len(recent) >= 3:
            if not self.draining:
                self.log("THREE FAILURES IN A ROW: no new tasks on this worker (see failed/)")
                self.draining = True
            return True
        return False

    # ---------------------------------------------------------------- housekeeping
    def heartbeat(self):
        for c in self.children:
            try:
                os.utime(self.running_path(c["task"]))
            except FileNotFoundError:
                pass
        if self.held:
            try:
                os.utime(self.running_path(self.held))
            except FileNotFoundError:
                pass

    def alive_jobs(self):
        """Set of the job ids of our running SLURM jobs, or None if unknown."""
        if not self.slurm:
            return set()
        try:
            r = subprocess.run(["squeue", "--me", "-h", "-o", "%i", "-t", "RUNNING,COMPLETING,SUSPENDED"],
                               capture_output=True, text=True, timeout=120)
        except Exception as e:
            self.log("squeue failed (%s); janitor skipped" % e)
            return None
        if r.returncode != 0:
            self.log("squeue failed (%s); janitor skipped" % r.stderr.strip())
            return None
        return set(r.stdout.split())

    def job_alive(self, jobid, host, pid, slurm_jobs):
        if jobid.startswith("local-"):
            if host != sq.HOST:
                return True  # cannot tell; rely on the heartbeat
            try:
                os.kill(int(jobid.rsplit("-", 1)[1]), 0)
                return True
            except (ProcessLookupError, ValueError):
                return False
            except PermissionError:
                return True
        return jobid in slurm_jobs

    def janitor(self):
        """Requeue the tasks of workers that are gone (job ended or node lost)
        or whose heartbeat stopped."""
        slurm_jobs = self.alive_jobs()
        if slurm_jobs is None:
            return
        rdir = sq.qpath(self.Q, "running")
        for e in os.scandir(rdir):
            if e.name.startswith(".") or ".tmp." in e.name:
                continue
            try:
                with open(e.path) as f:
                    head, line = f.read().split("\n")[:2]
                jobid, host, pid = head.split()[:3]
                age = time.time() - e.stat().st_mtime
            except (OSError, ValueError):  # (gone meanwhile, or a file system error)
                continue
            if jobid == self.jobid:
                continue
            dead = age >= self.cfg["gone_s"] and not self.job_alive(jobid, host, pid, slurm_jobs)
            if not dead and age < self.cfg["stale_s"]:
                continue
            reap = os.path.join(rdir, ".reap-%s-%s" % (e.name, self.jobid))
            try:
                os.rename(e.path, reap)
            except FileNotFoundError:
                continue  # another janitor was faster
            t = sq.parse_task(line)
            why = "worker %s on %s %s" % (jobid, host, "is gone" if dead else "stopped its heartbeat (%d s)" % age)
            irregular = int(pid) != 0  # a task that never started does not count as an attempt
            t2 = dict(t)
            if irregular:
                t2["attempts"] += 1
                cand = sq.candidate_from_output(self.out_path(t))
                if t2["kind"] == "S" and cand:
                    t2["kind"], t2["cand"] = "V", cand
            if t2["attempts"] >= self.cfg["max_attempts"]:
                self.fail(t2, "gave up after %d irregular ends (last: %s)" % (t2["attempts"], why), own=False)
            else:
                sq.requeue(self.Q, [t2], log=self.log)
                self.log("janitor: requeued %s (%s, attempts %d): %s" % (e.name, t2["kind"], t2["attempts"], why))
            try:
                os.remove(reap)
            except FileNotFoundError:
                pass

    def memlog(self):
        total, avail = meminfo()
        parts = ["%s %d/%d MB" % (c["name"], vm_kb(c["proc"].pid, "VmRSS") // 1024, c["hwm"] // 1024)
                 for c in self.children]
        self.log("memory: %.1f GB available; %d tasks: %s" % (avail, len(self.children), ", ".join(parts)))

    # ---------------------------------------------------------------- signals
    def on_usr1(self, *a):
        self.draining = True

    def on_term(self, *a):
        self.terminate = True

    def drain(self):
        """Near the end of the job: kill (and requeue) the tasks that cannot
        finish in time. A screening task that has found a candidate is busy
        with the verification: it is predicted with screening + verification
        time (and requeued as a verification task, see give_back)."""
        left = self.end - time.time()
        for c in self.children:
            if c["killed"]:
                continue
            t = c["task"]
            if t["kind"] == "S" and not c.get("cand") and sq.candidate_from_output(self.out_path(t)):
                c["cand"] = True
                c["ptime"] = self.pred_time(t) + self.pred_time(dict(t, kind="V"))
                self.log("%s is verifying a candidate (predicted %.0f s in all)" % (c["name"], c["ptime"]))
            if c["ptime"] * 1.2 - (time.time() - c["start"]) > left - 60:
                self.kill(c, "end of the job")

    def shutdown(self, why):
        self.log("shutting down: %s" % why)
        for c in self.children:
            self.kill(c, why)
        deadline = time.time() + 30
        while self.children and time.time() < deadline:
            self.reap()
            time.sleep(1)
        for c in self.children:  # still alive: kill hard and requeue
            self.signal_task(c, signal.SIGKILL)
            self.give_back(c["task"], why, irregular=False)
        if self.held:
            self.give_back(self.held, why, irregular=False)

    def resubmit(self):
        """At the regular end of a SLURM worker: top up the worker jobs to the
        target number (keep_workers.sh, which ignores this job), unless the
        queue is empty, all workers were told to stop, or this worker stopped
        because of failures. (The scrontab keeper does the same, but as a job
        of its own it may wait long on a full cluster.)"""
        if not self.slurm or self.empty or self.cfg["stop"] or self.breaker():
            return
        self.keeper_wait()  # (its lock would make the call below do nothing)
        try:
            r = subprocess.run([self.keeper_script()], capture_output=True, text=True, timeout=120)
            self.keeper_output(r.stdout)
        except Exception as e:
            self.log("keep_workers.sh failed: %s" % e)

    def keeper_script(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "keep_workers.sh")

    def keeper_output(self, out):
        with open(sq.qpath(self.Q, "logs", "keeper.log"), "a") as f:
            f.write(out)
        self.log("keep_workers.sh: %s" % (out.strip().replace("\n", "; ") or "nothing submitted"))

    def keeper_tick(self, now):
        """Every minute: a regular worker starts keep_workers.sh in the
        background if nobody has run it for keeper_s seconds (the scrontab
        keeper may wait for a node for hours on a full cluster); the script
        checks queue/keeper.last again under its lock."""
        if self.keeper_proc is not None:
            if self.keeper_proc.poll() is not None:
                self.keeper_output(self.keeper_proc.communicate()[0])
                self.keeper_proc = None
            elif now - self.t_keeper > 120:
                self.log("keep_workers.sh still running after 120 s; killing it")
                self.keeper_proc.kill()
                self.keeper_proc.communicate()
                self.keeper_proc = None
            return
        ks = self.cfg["keeper_s"]
        if not (self.slurm and self.regular and ks) or now - self.t_keeper < 60:
            return
        if self.empty or self.draining or self.cfg["stop"]:
            return
        self.t_keeper = now
        try:
            age = now - os.stat(sq.qpath(self.Q, "keeper.last")).st_mtime
        except FileNotFoundError:
            age = ks
        if age < ks:
            return
        try:
            self.keeper_proc = subprocess.Popen([self.keeper_script()], stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                                env=dict(os.environ, KEEPER_MIN_AGE=str(int(ks - 60))))
        except Exception as e:
            self.log("keep_workers.sh failed: %s" % e)

    def keeper_wait(self):
        if self.keeper_proc is not None:
            try:
                self.keeper_output(self.keeper_proc.communicate(timeout=120)[0])
            except subprocess.TimeoutExpired:
                self.keeper_proc.kill()
                self.keeper_proc.communicate()
            self.keeper_proc = None

    # ---------------------------------------------------------------- main loop
    def run(self):
        self.safely(self.janitor)
        while True:
            now = time.time()
            if now - self.cfg_time > self.cfg["config_s"]:
                self.safely(self.read_config)
            self.safely(self.reap)
            if self.terminate:
                self.shutdown("terminated by a signal")
                break
            if self.end - now < self.cfg["end_margin_s"] / 2 and not self.draining:
                self.log("end of the job is near; draining")
                self.draining = True
            if self.draining:
                self.safely(self.drain)
            if now - self.t_heartbeat > self.cfg["heartbeat_s"]:
                self.safely(self.heartbeat)
                self.t_heartbeat = now
            if now - self.t_janitor > self.cfg["janitor_s"]:
                self.safely(self.janitor)
                self.t_janitor = now
            if now - self.t_memlog > self.cfg["memlog_s"]:
                self.safely(self.memlog)
                self.t_memlog = now
            self.safely(self.keeper_tick, now)
            self.safely(self.memory_guard)
            self.safely(self.maybe_start)
            if not self.children and self.held is None and (self.empty or self.draining or self.cfg["stop"]):
                self.log("nothing to do (%s); exiting" % ("queue empty" if self.empty else "draining"))
                self.resubmit()
                break
            time.sleep(self.cfg["loop_s"])


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--queue", default=os.path.join(here, "queue"))
    ap.add_argument("--code", default=here)
    ap.add_argument("--magma", default=os.environ.get("MAGMA", "magma"))
    ap.add_argument("--hours", type=float, default=24.0)
    Worker(ap.parse_args()).run()


if __name__ == "__main__":
    main()
