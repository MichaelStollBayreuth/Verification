"""Shared queue for the strange-prime search on a cluster (see README.md).

The queue lives in a directory Q on a file system shared by all nodes:

  Q/pairs.txt      tasks "p n", one per line, append-only (enqueue.py)
  Q/pairs.pos      byte offset in pairs.txt of the next task to hand out
  Q/requeue.txt    tasks to be redone, served before pairs.txt; lines
                   "S p n attempts" (screening) or "V p n attempts <candidate>"
                   (verification only), append-only
  Q/requeue.pos    byte offset in requeue.txt of the next task to hand out
  Q/lock/          lock directory (mkdir is atomic, also on PanFS and NFS)
  Q/running/NAME   one file per running task: "jobid host pid start kind attempts"
                   (NAME = "p-n"); touched regularly by the worker (heartbeat)
  Q/out/NAME.out   Magma output of a running task
  Q/done/SHARD/NAME.out   Magma output of a finished task (SHARD = p div 1000)
  Q/failed/NAME.out       Magma output of a task that ended with an error
  Q/logs/JOBID.log        worker log; Q/logs/JOBID.tsv one line per finished task

All updates of pairs.pos, requeue.pos and requeue.txt happen under the lock;
everything else is written by the one worker that owns the task.
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
    are "p n"; lines of requeue.txt are "S p n a" or "V p n a <candidate>"."""
    w = line.split(None, 4)
    if w[0] in ("S", "V"):
        t = dict(kind=w[0], p=int(w[1]), n=int(w[2]), attempts=int(w[3]), cand=None)
        if t["kind"] == "V":
            t["cand"] = w[4].strip()
        return t
    return dict(kind="S", p=int(w[0]), n=int(w[1]), attempts=0, cand=None)


def task_line(t):
    if t["kind"] == "V":
        return "V %d %d %d %s" % (t["p"], t["n"], t["attempts"], t["cand"])
    return "S %d %d %d" % (t["p"], t["n"], t["attempts"])


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


def claim(Q, log=None):
    """The next task (requeued tasks first), or None if the queue is empty."""
    with Lock(Q, log=log):
        for fname, posname in (("requeue.txt", "requeue.pos"), ("pairs.txt", "pairs.pos")):
            while True:
                line = _take(Q, fname, posname)
                if line is None:
                    break
                if line.strip() and not line.startswith("#"):
                    return parse_task(line)
    return None


def requeue(Q, tasks, log=None):
    if not tasks:
        return
    with Lock(Q, log=log):
        with open(qpath(Q, "requeue.txt"), "a") as f:
            for t in tasks:
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
    for d in ("running", "out", "done", "failed", "logs", "slurm"):
        os.makedirs(qpath(Q, d), exist_ok=True)
