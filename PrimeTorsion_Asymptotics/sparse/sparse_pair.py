#!/usr/bin/env python3
"""Screening of one pair (p, n) with Najman's sparse method (see README.md): the
linear complexity L of the Krylov sequence of T_2 on e' = (T_2 - 1 - 2 chi(2))
(T_2 - 2 - chi(2)) {0, oo}, computed mod q on the Manin symbol relations only
(memory O(p)), and compared with k = dim S. L = k, or L = k/2 for the quadratic
character with chi(2) = 1, certifies that the even character of order n mod p
is not strange (trial 1 of screen_character_lean in strange_primes.magma).

  python3 sparse_pair.py P N [--magma MAGMA] [--tmp DIR]

Run in the directory of strange_primes.magma (for aux_prime). The large
intermediate files go to DIR (default $TMPDIR or /tmp; node-local) and are
removed at the end. Output: one line per step, then either the lines
"RESULT <p, n, [], []>" and "p = P, n = N: not strange (CPU s, MB MB)" of
search_pair.m, or "UNCERTIFIED <p, n, k, L, chi(2) = 1>" (exit code 0 in both
cases); a failing step gives exit code 1.
"""

import argparse
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
child, W = None, None


def on_term(signum, frame):
    """SIGTERM: stop the running step, remove the files, and end by the signal
    (so that the worker sees a killed task, not a failed one)."""
    if child is not None and child.poll() is None:
        child.kill()
    if W:
        shutil.rmtree(W, ignore_errors=True)
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def run(name, cmd, marker):
    """Run one step, print its time and its last output lines; its output must
    contain the marker line."""
    global child
    t = time.time()
    child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, universal_newlines=True)
    out = child.communicate()[0]
    rc, child = child.returncode, None
    lines = [l for l in out.splitlines() if l.strip()]
    print("step %-7s %7.1f s, exit code %d" % (name, time.time() - t, rc))
    for l in lines[-12:]:
        print("  " + l[:300])
    sys.stdout.flush()
    if not any(l.startswith(marker) for l in lines):
        if name == "finish" and rc == 2:  # (finish_L: the certificate failed)
            return out
        print("ERROR in step %s: exit code %d, no line %s" % (name, rc, marker))
        sys.exit(1)
    return out


def field(out, key):
    m = re.search(r"\b%s=(-?\d+)" % key, out)
    assert m, key
    return int(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("p", type=int)
    ap.add_argument("n", type=int)
    ap.add_argument("--magma", default="magma")
    ap.add_argument("--tmp", default=os.environ.get("TMPDIR") or "/tmp")
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, on_term)
    global W
    p, n, M, py = a.p, a.n, a.magma, sys.executable
    W = os.path.join(a.tmp, "strange-sparse-%s" % os.environ.get("USER", "x"), "%d-%d-%d" % (p, n, os.getpid()))
    os.makedirs(W)
    f = lambda name: os.path.join(W, name)
    B = lambda name: os.path.join(HERE, "bin", name)
    S = lambda name: os.path.join(HERE, name)
    t0 = time.time()
    try:
        out = run("export", [M, "-b", "P:=%d" % p, "OrderToTest:=%d" % n, "GraphOut:=" + f("graph.txt"),
                             S("export_graph_fast.m")], "S20_MANIN_GRAPH_EXPORT_COMPLETE")
        q = field(out, "q")
        with open(f("graph.txt")) as g:
            head = g.readline().split()
        assert int(head[0]) == q and int(head[1]) == p and int(head[2]) == n
        chi2_is_1 = int(head[6]) == 1  # (chi(2) as an element of F_q)
        out = run("prepare", [B("prepare_graph"), f("graph.txt"), f("prepared.txt"), f("rank.json")],
                  "S20_MANIN_GRAPH_PREPARED")
        k = field(out, "cuspidal_dimension")
        run("vgraph", [py, S("verify_graph.py"), f("graph.txt"), f("prepared.txt"), f("rank.json"),
                       f("verified.json")], "S20_GRAPH_INDEPENDENT_CERTIFICATE_PASS")
        run("prefix", [M, "-b", "GraphIn:=" + f("graph.txt"), "Prepared:=" + f("prepared.txt"),
                       S("check_graph_prefix.m")], "S20_GRAPH_NATIVE_PREFIX_PASS")
        run("pfree", [py, S("prepare_free.py"), f("graph.txt"), f("prepared.txt"), f("rank.json"),
                      f("free.txt")], "S21_FREE_GRAPH_PREPARED")
        run("vfree", [py, S("verify_free.py"), f("graph.txt"), f("prepared.txt"), f("rank.json"),
                      f("verified.json"), f("free.txt"), f("free_verified.json")], "S21_FREE_GRAPH_INDEPENDENT_PASS")
        out = run("krylov", [B("krylov_packed"), f("free.txt"), f("raw.m")], "S22_PACKED_GRAPH_KRYLOV_COMPLETE")
        assert field(out, "dimension") == k
        out = run("finish", [B("finish_L"), f("raw.m")], "S21_LINEAR_COMPLEXITY")
        assert field(out, "dimension") == k and field(out, "q") == q
        ok = "certificate=ok" in out
        L = field(out, "complexity")
    finally:
        shutil.rmtree(W, ignore_errors=True)
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu, mb = r.ru_utime + r.ru_stime, r.ru_maxrss // 1024
    doubled = n == 2 and chi2_is_1
    print("SPARSE <%d, %d>: q = %d, k = %d, L = %s, chi(2) = 1: %s; %.0f s" % (
        p, n, q, k, L if ok else "%d (certificate failed)" % L, "true" if chi2_is_1 else "false", time.time() - t0))
    if ok and (L == k or (doubled and 2 * L == k)):
        print("RESULT <%d, %d, [], []>" % (p, n))
        print("p = %d, n = %d: not strange (%.1f s, %d MB)" % (p, n, cpu, mb))
    else:
        print("UNCERTIFIED <%d, %d, %d, %d, %s>" % (p, n, k, L if ok else -1, "true" if chi2_is_1 else "false"))


if __name__ == "__main__":
    main()
