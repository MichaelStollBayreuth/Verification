#!/usr/bin/env python3
"""Completeness check of the strange-prime search (see README.md): every pair
in pairs.txt must have a result in done/. Lists the pairs that are neither
done nor running nor pending nor failed (lost, e.g. by a crash at an
unlucky moment), and with --requeue puts them back into the queue.
With --results FILE it also writes all RESULT lines, sorted by (p, n).

  python3 audit.py --queue Q [--requeue] [--results FILE]
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sq  # noqa: E402
from status import lines_after  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--requeue", action="store_true")
    ap.add_argument("--results")
    a = ap.parse_args()
    Q = os.path.abspath(a.queue)
    handed, pending = lines_after(sq.qpath(Q, "pairs.txt"), sq.read_pos(sq.qpath(Q, "pairs.pos")))
    _, rq_pending = lines_after(sq.qpath(Q, "requeue.txt"), sq.read_pos(sq.qpath(Q, "requeue.pos")))
    names = lambda lines: {sq.name_of(t["p"], t["n"]) for t in map(sq.parse_task, lines)}
    expected = names(handed) | names(pending)
    waiting = names(pending) | names(rq_pending)
    done = {os.path.basename(f)[:-4] for f in glob.glob(sq.qpath(Q, "done", "*", "*.out"))}
    failed = {f[:-4] for f in os.listdir(sq.qpath(Q, "failed"))}
    running = {f for f in os.listdir(sq.qpath(Q, "running")) if not f.startswith(".") and ".tmp." not in f}
    lost = sorted(expected - done - waiting - failed - running, key=lambda s: tuple(map(int, s.split("-"))))
    print("%d pairs: %d done, %d running, %d waiting, %d failed, %d lost"
          % (len(expected), len(expected & done), len(running), len(waiting - done), len(failed - done), len(lost)))
    if lost:
        print("lost:", " ".join(lost[:50]), "..." if len(lost) > 50 else "")
        if a.requeue:
            tasks = [dict(kind="S", p=int(s.split("-")[0]), n=int(s.split("-")[1]), attempts=0, cand=None) for s in lost]
            sq.requeue(Q, tasks)
            print("requeued %d pairs" % len(tasks))
    if a.results:
        res = []
        for f in glob.glob(sq.qpath(Q, "done", "*", "*.out")):
            with open(f) as g:
                for line in g:
                    if line.startswith("RESULT "):
                        p, n = os.path.basename(f)[:-4].split("-")
                        res.append(((int(p), int(n)), line.rstrip()))
        res.sort()
        with open(a.results, "w") as g:
            for _, line in res:
                g.write(line + "\n")
        print("wrote %d RESULT lines to %s" % (len(res), a.results))
    if len(expected) == len(expected & done):
        print("COMPLETE: every pair has a result")


if __name__ == "__main__":
    main()
