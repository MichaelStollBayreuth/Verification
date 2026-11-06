#!/usr/bin/env python3
"""gen_test.py FILE q k L seed: a raw.m (q, dimension k, 2k terms) of a random linear recurrence
of length L (L <= k), i.e. linear complexity L (up to a negligible chance), for testing finish_L.
(Time O(k L) in Python: k up to a few thousand.)"""
import random, sys
fn, q, k, L, seed = sys.argv[1], *map(int, sys.argv[2:])
r = random.Random(seed)
c = [r.randrange(1, q)] + [r.randrange(q) for _ in range(L - 1)] if L else []   # s_i = sum c_j s_(i-1-j)
s = [r.randrange(q) for _ in range(L)]
while len(s) < 2*k:
    s.append(sum(cj * s[-1 - j] for j, cj in enumerate(c)) % q)
with open(fn, "w") as f:
    f.write("q:=%d;dimension:=%d;sequence:=[%s];\n" % (q, k, ",".join(map(str, s))))
