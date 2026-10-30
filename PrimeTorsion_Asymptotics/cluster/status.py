#!/usr/bin/env python3
"""State of the queue of the strange-prime search (see README.md).

  python3 status.py --queue Q [--strange] [--failed] [--running]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sq  # noqa: E402
from worker import DEFAULTS  # noqa: E402


def lines_after(path, pos):
    """(lines before the offset pos, the lines from pos on)"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return [], []
    before = [l for l in data[:pos].decode().split("\n") if l.strip() and not l.startswith("#")]
    after = [l for l in data[pos:].decode().split("\n") if l.strip() and not l.startswith("#")]
    return before, after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--strange", action="store_true", help="list the strange pairs found")
    ap.add_argument("--failed", action="store_true", help="list the failed tasks")
    ap.add_argument("--running", action="store_true", help="list the running tasks")
    a = ap.parse_args()
    Q = os.path.abspath(a.queue)
    cfg = dict(DEFAULTS)
    try:
        with open(sq.qpath(Q, "config.json")) as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    handed, pending = lines_after(sq.qpath(Q, "pairs.txt"), sq.read_pos(sq.qpath(Q, "pairs.pos")))
    rq_done, rq_pending = lines_after(sq.qpath(Q, "requeue.txt"), sq.read_pos(sq.qpath(Q, "requeue.pos")))
    ndone = sum(len(os.listdir(d)) for d in glob.glob(sq.qpath(Q, "done", "*")))
    failed = sorted(os.listdir(sq.qpath(Q, "failed")))
    running = []
    for e in os.scandir(sq.qpath(Q, "running")):
        if e.name.startswith(".") or ".tmp." in e.name:
            continue
        try:
            with open(e.path) as f:
                head = f.readline().split()
            running.append((e.name, head, time.time() - e.stat().st_mtime))
        except (FileNotFoundError, ValueError):
            pass
    rows, strange = [], {}
    for path in glob.glob(sq.qpath(Q, "logs", "*.tsv")):
        with open(path) as f:
            for line in f:
                w = line.rstrip("\n").split("\t")
                if len(w) >= 10:
                    rows.append(w)
                    if w[9].startswith("STRANGE"):
                        strange[w[1]] = w[9]
    total = len(handed) + len(pending)
    print("pairs: %d enqueued, %d handed out, %d not yet; requeued: %d (%d pending)"
          % (total, len(handed), len(pending), len(rq_done) + len(rq_pending), len(rq_pending)))
    started = sum(1 for r in running if r[1][2] != "0")
    print("done: %d, running: %d (+%d claimed, waiting for memory), failed: %d, strange pairs: %d"
          % (ndone, started, len(running) - started, len(failed), len(strange)))
    hour = [r for r in rows if time.time() - float(r[0]) < 3600 and r[9] != "FAILED"]
    if hour:
        print("last hour: %d tasks done, mean wall %.0f s, max peak %s MB"
              % (len(hour), sum(float(r[5]) for r in hour) / len(hour), max(int(r[7]) for r in hour)))
    if pending and started:
        ps = [int(l.split()[0]) for l in pending]
        pred = sum(cfg["time_a"] * (p / 2e5) ** cfg["time_exp"] for p in ps)
        print("pending work (model): %.0f core-hours, i.e. %.1f days at the current %d tasks in parallel"
              % (pred / 3600, pred / 86400 / started, started))
    try:
        r = subprocess.run(["squeue", "--me", "-h", "-n", "strange-worker", "-o", "%i %T %M %l %N"],
                           capture_output=True, text=True, timeout=60)
        jobs = [l for l in r.stdout.split("\n") if l.strip()]
        print("worker jobs: %d (%d running)" % (len(jobs), sum(" RUNNING " in " %s " % l for l in jobs)))
    except Exception:
        pass
    if a.running:
        for name, head, age in sorted(running):
            print("  running %s: job %s on %s, pid %s, started %s, heartbeat %d s ago"
                  % (name, head[0], head[1], head[2], time.strftime("%m-%d %H:%M", time.localtime(int(head[3]))), age))
    if a.failed:
        for name in failed:
            print("  failed %s" % name)
    if a.strange:
        for name in sorted(strange, key=lambda s: tuple(map(int, s.split("-")))):
            print("  strange %s: %s" % (name, strange[name]))


if __name__ == "__main__":
    main()
