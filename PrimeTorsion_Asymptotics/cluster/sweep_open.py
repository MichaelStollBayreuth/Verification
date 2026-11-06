#!/usr/bin/env python3
"""Requeue the pairs in open/ that nobody takes care of as tasks of kind C (proof in
characteristic 0, see README.md): those that are not done, not running, not waiting in
requeue.txt or crt.txt, without crt/p-n.na, and whose open/ entry is older than --min-age
seconds (so that a worker that has just put a pair into open/ has requeued it already).
Workers whose code does not know kind C leave such pairs in open/ (for p > magma_max_p).
keep_workers.sh runs it.

  python3 sweep_open.py --queue Q [--min-age S] [--dry]
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sq  # noqa: E402
from status import lines_after  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--min-age", type=float, default=600)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    Q = os.path.abspath(a.queue)
    odir = sq.qpath(Q, "open")
    if not os.path.isdir(odir):
        return
    with sq.Lock(Q):
        waiting = set()
        for fname, posname in (("requeue.txt", "requeue.pos"), ("crt.txt", "crt.pos")):
            for line in lines_after(sq.qpath(Q, fname), sq.read_pos(sq.qpath(Q, posname)))[1]:
                t = sq.parse_task(line)
                waiting.add(sq.name_of(t["p"], t["n"]))
        new = []
        for e in os.scandir(odir):
            if not e.name.endswith(".out"):
                continue
            name = e.name[:-4]
            p, n = map(int, name.split("-"))
            if (name in waiting or time.time() - e.stat().st_mtime < a.min_age
                    or os.path.exists(sq.done_path(Q, p, n))
                    or os.path.exists(sq.qpath(Q, "running", name))
                    or os.path.exists(sq.qpath(Q, "crt", name + ".na"))):
                continue
            new.append(dict(kind="C", p=p, n=n, attempts=0, cand=None))
        if new and not a.dry:
            with open(sq.qpath(Q, "crt.txt"), "a") as f:
                for t in new:
                    f.write(sq.task_line(t) + "\n")
    if new:
        print("%s %srequeued as C: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), "(dry run) " if a.dry else "",
                                          " ".join(sq.name_of(t["p"], t["n"]) for t in new)))


if __name__ == "__main__":
    main()
