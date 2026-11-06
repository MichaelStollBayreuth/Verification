"""Shared queue for the strange-prime search on a cluster (see README.md).

The queue lives in a directory Q on a file system shared by all nodes:

  Q/pairs.txt      tasks "p n", one per line, append-only (enqueue.py)
  Q/pairs.pos      byte offset in pairs.txt of the next task to hand out
  Q/requeue.txt    tasks to be redone, served before pairs.txt; lines
                   "S p n attempts" (screening) or "V p n attempts <candidate>"
                   (verification only), append-only
  Q/requeue.pos    byte offset in requeue.txt of the next task to hand out
  Q/crt.txt, Q/crt.pos   the same for tasks "C p n attempts [<candidate>]"
                   (proof in characteristic 0, sparse/crt_verify.py)
  Q/lock/          lock directory (mkdir is atomic, also on PanFS and NFS)
  Q/running/NAME   one file per running task: "jobid host pid start kind attempts"
                   (NAME = "p-n"); touched regularly by the worker (heartbeat)
  Q/out/NAME.out   Magma output of a running task
  Q/done/SHARD/NAME.out   Magma output of a finished task (SHARD = p div 1000)
  Q/failed/NAME.out       Magma output of a task that ended with an error
  Q/open/NAME.out         output of a sparse screening (N) that did not certify the pair
  Q/logs/JOBID.log        worker log; Q/logs/JOBID.tsv one line per finished task

All updates of pairs.pos, requeue.pos, requeue.txt, crt.pos and crt.txt happen
under the lock; everything else is written by the one worker that owns the task.
"""

import os
import random
import shutil
import socket
import time

HOST = socket.gethostname().split('.')[0]


def qpath(Q, *parts):
    return os.path.join(Q, *parts)


def name_of(p, n):
    return "%d-%d" % (p, n)


def shard_of(p):
    return "%04d" % (p // 1000)


def done_path(Q, p, n):
    return qpath(Q, "done", shard_of(p), name_of(p, n) + ".out")


class Lock:
    """Mutual exclusion via mkdir. A lock older than `stale` seconds is
    assumed to belong to a dead process and is broken.

    The PanFS client of a node can keep a directory entry that no longer
    exists on the server (2026-11-01: r12n11 for 2.6 hours, r12n02): stat
    finds the old lock, mkdir fails with EEXIST and rmdir with ENOENT, while
    the other nodes see no lock. A rename onto the entry fails with ENOENT as
    well, but makes the client drop it (tested on r12n02). So when a broken
    lock is still there with the same inode and mtime, drop_stale_entry
    renames a directory onto it, at most every 10 seconds."""

    def __init__(self, Q, stale=120, log=None):
        self.path = qpath(Q, "lock")
        self.stale = stale
        self.log = log

    def owner_line(self):
        return "%s %d %d\n" % (HOST, os.getpid(), int(time.time()))

    def drop_stale_entry(self):
        """Rename a directory with an owner file onto the lock path. A lock
        held by a live process has its owner file (from right after its
        mkdir), so the rename does not replace it (rename onto a non-empty
        directory fails); if the rename succeeds, the lock is ours."""
        tmp = "%s.tmp.%s.%d" % (self.path, HOST, os.getpid())
        try:
            os.mkdir(tmp)
            with open(os.path.join(tmp, "owner"), "w") as f:
                f.write(self.owner_line())
            os.rename(tmp, self.path)
            return True
        except OSError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            if self.log:
                self.log("lock entry not removable; rename onto it: %s" % e.strerror)
            return False

    def __enter__(self):
        broken = None     # (inode, mtime) of the last lock broken
        logged = None     # the last lock reported in the log
        tried = 0         # time of the last drop_stale_entry
        while True:
            try:
                os.mkdir(self.path)
                with open(os.path.join(self.path, "owner"), "w") as f:
                    f.write(self.owner_line())
                return self
            except FileExistsError:
                try:
                    st = os.stat(self.path)
                except FileNotFoundError:
                    continue
                age = time.time() - st.st_mtime
                if age > self.stale:
                    key = (st.st_ino, st.st_mtime)
                    if key == broken and time.time() - tried >= 10:
                        tried = time.time()
                        if self.drop_stale_entry():
                            return self
                    shutil.rmtree(self.path, ignore_errors=True)
                    broken = key
                    if self.log and key != logged:
                        logged = key
                        self.log("broke a stale lock (age %d s)" % age)
                time.sleep(0.05 + 0.1 * random.random())

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def write_atomic(path, text):
    tmp = "%s.tmp.%s.%d" % (path, HOST, os.getpid())
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def read_pos(path):
    try:
        with open(path) as f:
            return int(f.read().strip() or 0)
    except FileNotFoundError:
        return 0


def parse_task(line):
    """A task line -> dict(kind, p, n, attempts, cand). Lines of pairs.txt
    are "p n"; lines of requeue.txt are "S p n a", "V p n a <candidate>" or
    "C p n a [<candidate>]". (A worker may run a task of kind S as kind N,
    with the sparse method, and one of kind V as kind C; see claim. In the
    files an N task remains S.)"""
    w = line.split(None, 4)
    if w[0] in ("S", "V", "C"):
        t = dict(kind=w[0], p=int(w[1]), n=int(w[2]), attempts=int(w[3]), cand=None)
        if t["kind"] == "V" or (t["kind"] == "C" and len(w) > 4):
            t["cand"] = w[4].strip()
        return t
    return dict(kind="S", p=int(w[0]), n=int(w[1]), attempts=0, cand=None)


def task_line(t):
    if t["kind"] in ("V", "C"):
        return ("%s %d %d %d %s" % (t["kind"], t["p"], t["n"], t["attempts"], t["cand"] or "")).rstrip()
    return "S %d %d %d" % (t["p"], t["n"], t["attempts"])  # (also for kind N)


def _take(Q, fname, posname):
    """Under the lock: the next complete line of Q/fname after the stored
    offset, advancing the offset; None if there is none."""
    path = qpath(Q, fname)
    pos = read_pos(qpath(Q, posname))
    try:
        with open(path, "rb") as f:
            f.seek(pos)
            line = f.readline()
    except FileNotFoundError:
        return None
    if not line.endswith(b"\n"):
        return None  # nothing new (or an incomplete last line)
    write_atomic(qpath(Q, posname), "%d\n" % (pos + len(line)))
    return line.decode()


def _scan(Q, fname, posname, accept, convert):
    """Under the lock: the next task of a requeue file (requeue.txt, crt.txt) that
    accept takes; the lines it does not take are moved to the end of the file (for
    another worker). Only the lines present at the start are scanned."""
    try:
        end = os.path.getsize(qpath(Q, fname))
    except FileNotFoundError:
        return None
    skipped, t = [], None
    while t is None and read_pos(qpath(Q, posname)) < end:
        line = _take(Q, fname, posname)
        if line is None:
            break
        if line.strip() and not line.startswith("#"):
            t = parse_task(line)
            if convert is not None:
                t = convert(t)
            if accept is not None and not accept(t):
                skipped.append(line)
                t = None
    if skipped:
        with open(qpath(Q, fname), "a") as f:
            f.writelines(skipped)
    return t


def claim(Q, log=None, accept=None, convert=None):
    """The next task (requeued tasks first, then proofs in characteristic 0), or
    None if the queue is empty. A requeued task for which accept(task) is false
    (e.g. a long verification that cannot finish before the end of the job) is
    moved to the end of requeue.txt (crt.txt) for another worker; only the lines
    present at the start are scanned. convert(task), if given, is applied to
    every task read (it may change its kind from S to N or from V to C), before
    accept."""
    with Lock(Q, log=log):
        t = _scan(Q, "requeue.txt", "requeue.pos", accept, convert)
        if t is None:
            t = _scan(Q, "crt.txt", "crt.pos", accept, convert)
        while t is None:
            line = _take(Q, "pairs.txt", "pairs.pos")
            if line is None:
                break
            if line.strip() and not line.startswith("#"):
                t = parse_task(line)
                if convert is not None:
                    t = convert(t)
        return t


def requeue(Q, tasks, log=None):
    """Append tasks to requeue.txt, those of kind C to crt.txt (which workers with
    older code, which do not know that kind, do not read)."""
    if not tasks:
        return
    with Lock(Q, log=log):
        for fname, ts in (("requeue.txt", [t for t in tasks if t["kind"] != "C"]),
                          ("crt.txt", [t for t in tasks if t["kind"] == "C"])):
            if ts:
                with open(qpath(Q, fname), "a") as f:
                    for t in ts:
                        f.write(task_line(t) + "\n")


def candidate_from_output(path):
    """The candidate tuple printed by search_pair.m before the verification,
    or None."""
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("CANDIDATE "):
                    return line[len("CANDIDATE "):].strip()
    except FileNotFoundError:
        pass
    return None


def ensure_dirs(Q):
    for d in ("running", "out", "done", "failed", "open", "logs", "slurm"):
        os.makedirs(qpath(Q, d), exist_ok=True)
