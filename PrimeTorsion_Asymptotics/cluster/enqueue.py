#!/usr/bin/env python3
"""Append tasks to the queue of the strange-prime search (see README.md).

  python3 enqueue.py --queue Q LO HI       all pairs (p, n): primes LO <= p <= HI,
                                           orders n > 1 dividing (p-1)/2
  python3 enqueue.py --queue Q --pairs F   the lines "p n" of the file F

Pairs are appended in increasing order of p (and n). The ranges enqueued are
recorded in Q/ranges.txt; a range overlapping an earlier one is refused
(--force to override).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sq  # noqa: E402


def primes_between(lo, hi):
    sieve = bytearray([1]) * (hi + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(hi ** 0.5) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(range(i * i, hi + 1, i)))
    return [p for p in range(max(lo, 2), hi + 1) if sieve[p]]


def divisors(m):
    small, large = [], []
    d = 1
    while d * d <= m:
        if m % d == 0:
            small.append(d)
            if d * d != m:
                large.append(m // d)
        d += 1
    return small + large[::-1]


def pairs_for(lo, hi):
    for p in primes_between(lo, hi):
        if p <= 3:
            continue
        for n in divisors((p - 1) // 2):
            if n > 1:
                yield p, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--pairs")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("range", nargs="*", type=int)
    a = ap.parse_args()
    Q = os.path.abspath(a.queue)
    os.makedirs(Q, exist_ok=True)
    sq.ensure_dirs(Q)
    if a.pairs:
        with open(a.pairs) as f:
            lines = [" ".join(l.split()[:2]) for l in f if l.strip() and not l.startswith("#")]
        what = "pairs from %s" % a.pairs
    else:
        if len(a.range) != 2:
            ap.error("give LO HI or --pairs FILE")
        lo, hi = a.range
        rpath = sq.qpath(Q, "ranges.txt")
        if os.path.exists(rpath) and not a.force:
            with open(rpath) as f:
                for line in f:
                    w = line.split()
                    if len(w) >= 2 and not (hi < int(w[0]) or lo > int(w[1])):
                        sys.exit("range %d..%d overlaps %s..%s, enqueued earlier (--force to override)"
                                 % (lo, hi, w[0], w[1]))
        lines = ["%d %d" % pn for pn in pairs_for(lo, hi)]
        what = "range %d..%d" % (lo, hi)
    with sq.Lock(Q):
        with open(sq.qpath(Q, "pairs.txt"), "a") as f:
            for line in lines:
                f.write(line + "\n")
        if not a.pairs:
            with open(sq.qpath(Q, "ranges.txt"), "a") as f:
                f.write("%d %d %d %s\n" % (lo, hi, len(lines), time.strftime("%Y-%m-%d %H:%M:%S")))
    print("enqueued %d pairs (%s)" % (len(lines), what))


if __name__ == "__main__":
    main()
