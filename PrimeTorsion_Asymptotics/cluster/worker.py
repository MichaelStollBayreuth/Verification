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
    # time (measured on lipwig for 2.0e5 < p < 2.8e5), and its peak is about 1.25 times
    # the predicted screening peak.
    verify_mem_factor=1.6, verify_time_factor=20.0,
    time_safety=1.5,      # start a task only if time_safety * predicted time fits
    end_margin_s=300,     # ... before the end of the job minus this margin
    max_attempts=4,       # irregular ends of a task before it is given up (failed/)
    stale_s=1800,         # a running/ entry not touched for this long is dead
    heartbeat_s=300, janitor_s=600, config_s=60, memlog_s=300, loop_s=5,
    stop=False,           # true: no worker starts new tasks
)

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
        self.t_heartbeat = self.t_janitor = self.t_memlog = time.time()
        signal.signal(signal.SIGUSR1, self.on_usr1)
        signal.signal(signal.SIGTERM, self.on_term)
        signal.signal(signal.SIGINT, self.on_term)
        cpus = len(os.sched_getaffinity(0))
        total, avail = meminfo()
        self.log("worker %s on %s: %d CPUs, %.1f GB total, %.1f GB available, end in %.1f h, code %s"
                 % (self.jobid, sq.HOST, cpus, total, avail, (self.end - time.time()) / 3600, self.code))

    # ---------------------------------------------------------------- utilities
    def log(self, msg):
        self.logf.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
        self.logf.flush()

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
        c = self.cfg
        a = c["peak_a"] if peak else c["steady_a"]
        m = a * (t["p"] / 2e5) ** c["mem_exp"] + c["mem_b"]
        return m * (c["verify_mem_factor"] if t["kind"] == "V" else 1)

    def peak_window(self, t):
        return self.cfg["peak_s"] * (t["p"] / 2e5) ** self.cfg["peak_exp"]

    def pred_time(self, t):
        c = self.cfg
        s = c["time_a"] * (t["p"] / 2e5) ** c["time_exp"]
        return s * (c["verify_time_factor"] if t["kind"] == "V" else 1)

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
        cmd = [self.magma, "-b"]
        if t["kind"] == "V":
            cmd.append("cand:=" + t["cand"])
        else:
            cmd += ["p:=%d" % t["p"], "n:=%d" % t["n"]]
        cmd.append("search_pair.m")
        out = open(self.out_path(t), "w")
        proc = subprocess.Popen(cmd, cwd=self.code, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT)
        out.close()
        self.mark_running(t, proc.pid)
        self.children.append(dict(task=t, name=sq.name_of(t["p"], t["n"]), proc=proc, start=time.time(),
                                  pmem=self.pred_mem(t), ptime=self.pred_time(t), killed=None, hwm=0))
        self.last_start = time.time()
        self.log("start %s (%s, attempt %d) pid %d, predicted %.1f GB, %.0f s"
                 % (sq.name_of(t["p"], t["n"]), t["kind"], t["attempts"], proc.pid,
                    self.children[-1]["pmem"], self.children[-1]["ptime"]))

    def give_back(self, t, why, irregular):
        """Requeue task t (after an irregular end if irregular is true: then
        its attempts are counted, and a screening task whose candidate was
        already printed becomes a verification task)."""
        t = dict(t)
        outp = self.out_path(t)
        if irregular:
            t["attempts"] += 1
            if t["kind"] == "S":
                cand = sq.candidate_from_output(outp)
                if cand:
                    t["kind"], t["cand"] = "V", cand
            if t["attempts"] >= self.cfg["max_attempts"]:
                self.fail(t, "gave up after %d irregular ends (last: %s)" % (t["attempts"], why))
                return
        sq.requeue(self.Q, [t], log=self.log)
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
        try:
            c["proc"].terminate()
        except ProcessLookupError:
            pass
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
                c["proc"].kill()

    def admissible(self, t):
        # Young tasks (still building the modular symbols space) count with
        # young_frac times their peak memory, the others with their steady-state
        # memory; the new task needs its peak.
        total, avail = meminfo()
        now = time.time()
        committed = sum(self.cfg["young_frac"] * self.pred_mem(c["task"], True)
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

    def maybe_start(self):
        c = self.cfg
        if self.draining or c["stop"] or self.breaker():
            if self.held:
                self.give_back(self.held, "worker stops taking tasks", irregular=False)
                self.held = None
            return
        if len(self.children) >= self.max_procs() or time.time() - self.last_start < c["delay_s"]:
            return
        if self.held is None:
            if self.empty and time.time() - self.last_claim_try < 120:
                return
            self.last_claim_try = time.time()
            t = sq.claim(self.Q, log=self.log)
            self.empty = t is None
            if t is None:
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
            except (FileNotFoundError, ValueError):
                continue
            if jobid == self.jobid:
                continue
            dead = not self.job_alive(jobid, host, pid, slurm_jobs)
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
        finish in time."""
        left = self.end - time.time()
        for c in self.children:
            if not c["killed"] and c["ptime"] * 1.2 - (time.time() - c["start"]) > left - 60:
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
            c["proc"].kill()
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
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keep_workers.sh")
        try:
            r = subprocess.run([script], capture_output=True, text=True, timeout=120)
            with open(sq.qpath(self.Q, "logs", "keeper.log"), "a") as f:
                f.write(r.stdout)
            self.log("keep_workers.sh: %s" % (r.stdout.strip().replace("\n", "; ") or "nothing submitted"))
        except Exception as e:
            self.log("keep_workers.sh failed: %s" % e)

    # ---------------------------------------------------------------- main loop
    def run(self):
        self.janitor()
        while True:
            now = time.time()
            if now - self.cfg_time > self.cfg["config_s"]:
                self.read_config()
            self.reap()
            if self.terminate:
                self.shutdown("terminated by a signal")
                break
            if self.end - now < self.cfg["end_margin_s"] / 2 and not self.draining:
                self.log("end of the job is near; draining")
                self.draining = True
            if self.draining:
                self.drain()
            if now - self.t_heartbeat > self.cfg["heartbeat_s"]:
                self.heartbeat()
                self.t_heartbeat = now
            if now - self.t_janitor > self.cfg["janitor_s"]:
                self.janitor()
                self.t_janitor = now
            if now - self.t_memlog > self.cfg["memlog_s"]:
                self.memlog()
                self.t_memlog = now
            self.memory_guard()
            self.maybe_start()
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
