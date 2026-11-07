#!/usr/bin/env python3
"""Proof of strangeness of a pair (p, n) by a multimodular computation in characteristic 0
(see README.md), for pairs that sparse_pair.py did not certify:

  python3 crt_verify.py P N [--magma MAGMA] [--jobs J] [--tmp DIR] [--out DIR] [--ops OPS]

1. An operator A in the Hecke algebra that is cyclic on S: the Krylov sequence of a random
   element of S has linear complexity k = dim S (then A is cyclic on S over Q(zeta_n) as well,
   and the Hecke algebra acts on S through Q(zeta_n)[A]). A = T_2 if T_2 is cyclic mod q (or
   mod the first prime l of 2.), otherwise the first operator of OPS below that is cyclic mod l
   (A = c_1 T_l1 + c_2 T_l2 + ..., written "l1:c1,l2:c2,..."; --ops: only this operator).
2. For primes l = 1 mod n below 2^23.5 and each embedding zeta_n -> z of Q(zeta_n) into F_l
   (chi(PrimitiveRoot(p)) = z), with d random functionals u: the minimal polynomial m of the
   sequence u(A^i e') (linear complexity L; d = k - L), and phi = m(A*) u, which lies in
   the annihilator W of F_l[A] e' (dimension d). The d functionals are brought into reduced
   echelon form mod l.
3. Chinese remaindering over the primes l (all embeddings of each l give the coefficients in
   the power basis of zeta_n mod l) and rational reconstruction of the echelon basis of W over
   Q(zeta_n), until the reconstruction is stable.
4. verify_char0.m checks the result exactly over Q(zeta_n): W is a space of functionals on the
   modular symbols, stable under T_l* for the primes l of A (and T_2*), cuspidal, and vanishing
   on {0, oo}. With 1. this proves strdim >= d phi(n); each l gives L <= dim Q(zeta_n)[A] e',
   so strdim <= k - L, and the strange dimension is d phi(n).
Runs in the directory of strange_primes.magma (like sparse_pair.py).
"""

import argparse
import concurrent.futures
import math
import os
import re
import resource
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
B = lambda name: os.path.join(HERE, "bin", name)
S = lambda name: os.path.join(HERE, name)
LIMIT = int(2 ** 23.5)  # (F_l arithmetic in Magma is fast for l^2 < 2^47)
# operators tried in turn if T_2 is not cyclic on S (see 1. above)
OPS = ["2:1", "2:1,3:1", "2:1,3:-1", "2:1,3:2", "3:1", "2:1,3:1,5:1", "2:1,3:-1,5:2", "2:1,5:1,7:1"]


def op_name(ops):
    """"2:1,3:-1" -> "T_2 - T_3"."""
    out = ""
    for o in ops.split(","):
        l, c = map(int, o.split(":"))
        out += ((" - " if out else "-") if c < 0 else " + " if out else "") + ("" if abs(c) == 1 else "%d " % abs(c)) + "T_%d" % l
    return out


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def is_prime(m):
    if m < 2:
        return False
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if m % a == 0:
            return m == a
    d, s = m - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, m)
        if x in (1, m - 1):
            continue
        for _ in range(s - 1):
            x = x * x % m
            if x == m - 1:
                break
        else:
            return False
    return True


def primes_1_mod(n, below):
    """Primes l = 1 mod n (and l = 1 mod 2), downwards from below."""
    m = 2 * n // math.gcd(2, n)
    l = (below - 1) // m * m + 1
    while l > 10 ** 6:
        if is_prime(l):
            yield l
        l -= m


def prim_roots_of_unity(n, l):
    """The primitive n-th roots of unity mod l (l = 1 mod n)."""
    fac = [r for r in range(2, n + 1) if n % r == 0 and all(r % s for s in range(2, r))]
    g = 2
    while True:
        z = pow(g, (l - 1) // n, l)
        if all(pow(z, n // r, l) != 1 for r in fac):
            break
        g += 1
    return [pow(z, e, l) for e in range(1, n + 1) if math.gcd(e, n) == 1]


def run(cmd, logf, env=None):
    with open(logf, "a") as f:
        f.write("$ %s\n" % " ".join(cmd))
        f.flush()
        rc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                            env=env).returncode
    if rc != 0:
        raise RuntimeError("%s: exit code %d (see %s)" % (os.path.basename(cmd[0]), rc, logf))
    with open(logf) as f:
        return f.read()


def field(out, key):
    m = re.findall(r"\b%s=(-?\d+)" % key, out)
    assert m, key
    return int(m[-1])


def one_run(a, W, l, z, seeds, random_start=False, ops="2:1"):
    """One prime l and embedding z, operator ops: (k, [(L, a, phi) for each seed])."""
    os.makedirs(W, exist_ok=True)
    lg = os.path.join(W, "log")
    f = lambda name: os.path.join(W, name)
    args = [a.magma, "-b", "P:=%d" % a.p, "OrderToTest:=%d" % a.n, "GraphOut:=" + f("graph.txt"),
            "Ops:=" + ops]
    if l:
        args += ["Q:=%d" % l, "Z:=%d" % z]
    out = run(args + [S("export_graph_crt.m")], lg)
    eis = (field(out, "eis1"), field(out, "eis2"))  # the eigenvalues of A on the Eisenstein series
    res, k = [], None
    for s in seeds:
        env = dict(os.environ, STRANGE_SEED=str(s), STRANGE_EIS="%d %d" % eis)
        if random_start:
            env["STRANGE_RANDOM_START"] = "1"
        out = run([B("prepare_graph"), f("graph.txt"), f("prepared.txt"), f("rank.json")], lg, env)
        k = field(out, "cuspidal_dimension")
        run([sys.executable, S("prepare_free.py"), f("graph.txt"), f("prepared.txt"), f("rank.json"), f("free.txt")], lg)
        run([B("krylov_packed"), f("free.txt"), f("raw.m")], lg)
        out = run([B("finish_L"), f("raw.m"), f("poly.txt")], lg)
        L = field(out, "complexity")
        if random_start or L == k:  # (L = k: m(A*) u = 0, and the pair is not strange)
            res.append((L, None, None))
            continue
        # m(x) (x - c_1)(x - c_2): phi also vanishes on the Eisenstein part
        with open(f("graph.txt")) as g:
            q = int(g.readline().split()[0])
        with open(f("poly.txt")) as g:
            w = list(map(int, g.read().split()))
        C = w[1:]
        for c in eis:
            C = [(x - c * y) % q for x, y in zip(C + [0], [0] + C)]
        with open(f("poly2.txt"), "w") as g:
            g.write("%d %s\n" % (len(C) - 1, " ".join(map(str, C))))
        out = run([B("project"), f("free.txt"), f("poly2.txt"), f("phi.txt")], lg)
        if field(out, "at_e") != 0 or field(out, "zero") != 0:
            raise RuntimeError("l = %d, z = %d, seed %d: projection zero or not in the annihilator" % (l, z, s))
        with open(f("phi.txt")) as g:
            qq, ns, ev = map(int, g.readline().split())
            phi = list(map(int, g.readline().split()))
        assert qq == (l or qq) and len(phi) == ns
        res.append((L, ev, phi))
    shutil.rmtree(W, ignore_errors=True)
    return k, res


def echelon(rows, l):
    """Reduced row echelon form mod l (rows of equal length): (pivots, rows), or None if the
    rows are dependent."""
    rows = [r[:] for r in rows]
    piv = []
    for t in range(len(rows)):
        j = next((j for j in range(len(rows[t])) if rows[t][j]), None)
        if j is None:
            return None
        c = pow(rows[t][j], -1, l)
        rows[t] = [x * c % l for x in rows[t]]
        for s in range(len(rows)):
            if s != t and rows[s][j]:
                c = rows[s][j]
                rows[s] = [(x - c * y) % l for x, y in zip(rows[s], rows[t])]
        piv.append(j)
    order = sorted(range(len(rows)), key=lambda t: piv[t])
    return [piv[t] for t in order], [rows[t] for t in order]


def ratrec(x, M):
    """A rational a/b = x mod M with |a|, b <= sqrt(M/2) (and a margin), or None."""
    bound = math.isqrt(M // 2) >> 16
    r0, r1, s0, s1 = M, x % M, 0, 1
    while r1 > bound:
        qq = r0 // r1
        r0, r1, s0, s1 = r1, r0 - qq * r1, s1, s0 - qq * s1
    if s1 == 0 or abs(s1) > bound or math.gcd(r1, abs(s1)) != 1:
        return None
    return (r1, s1) if s1 > 0 else (-r1, -s1)


def reconstruct(data, n, dK):
    """data: {l: {z: (pivots, rows)}} with all dK embeddings for each l. The echelon basis
    over Q(zeta_n) as rows of lists of dK-tuples of rationals, or None."""
    M, coef = 1, None  # coef[t][j][i]: coefficient of zeta^i mod M
    for l, byz in data.items():
        zs = sorted(byz)
        V = [[pow(z, i, l) for i in range(dK)] for z in zs]
        Vi = mat_inv(V, l)
        rows = [byz[z][1] for z in zs]  # rows[e][t][j]
        d, ns = len(rows[0]), len(rows[0][0])
        cl = [[[sum(Vi[i][e] * rows[e][t][j] for e in range(dK)) % l for i in range(dK)]
               for j in range(ns)] for t in range(d)]
        if coef is None:
            coef = cl
        else:
            for t in range(d):
                for j in range(ns):
                    for i in range(dK):
                        x, y = coef[t][j][i], cl[t][j][i]
                        coef[t][j][i] = x + M * ((y - x) * pow(M, -1, l) % l)
        M *= l
    out = []
    for t in range(len(coef)):
        row = []
        for j in range(len(coef[t])):
            tup = []
            for i in range(dK):
                r = ratrec(coef[t][j][i], M)
                if r is None:
                    return None, M
                tup.append(r)
            row.append(tup)
        out.append(row)
    return out, M


def mat_inv(V, l):
    m = len(V)
    A = [V[i][:] + [int(i == j) for j in range(m)] for i in range(m)]
    for c in range(m):
        r = next(r for r in range(c, m) if A[r][c])
        A[c], A[r] = A[r], A[c]
        x = pow(A[c][c], -1, l)
        A[c] = [y * x % l for y in A[c]]
        for r in range(m):
            if r != c and A[r][c]:
                y = A[r][c]
                A[r] = [(u - y * v) % l for u, v in zip(A[r], A[c])]
    return [row[m:] for row in A]


def final(p, n, verified):
    """The RESULT and final lines of search_pair.m (for the worker; verified: the tuple of
    verify_candidate, or None: not strange)."""
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    print("RESULT <%d, %d, [], [%s]>" % (p, n, " %s " % verified if verified else ""))
    print("p = %d, n = %d: %s (%.1f s, %d MB)" % (
        p, n, "STRANGE, strdim %s" % verified.split(",")[1].strip() if verified else "not strange",
        r.ru_utime + r.ru_stime, r.ru_maxrss // 1024))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("p", type=int)
    ap.add_argument("n", type=int)
    ap.add_argument("--magma", default="magma")
    ap.add_argument("--jobs", type=int, default=len(os.sched_getaffinity(0)))
    ap.add_argument("--tmp", default=os.environ.get("TMPDIR") or "/tmp")
    ap.add_argument("--out", default=".")
    ap.add_argument("--max-primes", type=int, default=200)
    ap.add_argument("--ops", help="the operator A (default: T_2, otherwise the first cyclic one of OPS)")
    a = ap.parse_args()
    p, n = a.p, a.n
    dK = sum(1 for e in range(1, n + 1) if math.gcd(e, n) == 1)
    T = os.path.join(a.tmp, "strange-crt-%s" % os.environ.get("USER", "x"), "%d-%d-%d" % (p, n, os.getpid()))
    os.makedirs(T)
    t0 = time.time()
    pool = concurrent.futures.ThreadPoolExecutor(a.jobs)
    try:
        # 1. an operator A that is cyclic on S (random start vector): T_2 mod q = aux_prime(p)
        ops = a.ops or OPS[0]
        k, res = one_run(a, os.path.join(T, "cyc"), None, None, [0], random_start=True, ops=ops)
        Lv = res[0][0]
        log("p = %d, n = %d: k = %d; A = %s, random element of S: linear complexity %d%s"
            % (p, n, k, op_name(ops), Lv, "" if Lv == k else " -- A is not cyclic on S (mod q)"))
        if Lv != k:
            # a repeated eigenvalue mod q may be an accident of q: cyclicity mod one prime
            # l = 1 mod n (one embedding; the others are Galois conjugate) suffices as well;
            # if T_2 is not cyclic mod l either, the operators of OPS in turn
            l = next(primes_1_mod(n, LIMIT))
            z = prim_roots_of_unity(n, l)[0]
            for ops in ([a.ops] if a.ops else OPS):
                _, res = one_run(a, os.path.join(T, "cyc-%d-%d" % (l, OPS.index(ops) if ops in OPS else 99)),
                                 l, z, [0], random_start=True, ops=ops)
                log("l = %d, z = %d: A = %s, random element of S: linear complexity %d"
                    % (l, z, op_name(ops), res[0][0]))
                if res[0][0] == k:
                    Lv = k
                    break
        if Lv != k:
            print("CRT_NOT_APPLICABLE <%d, %d>: %s not cyclic on S mod q and mod %d"
                  % (p, n, op_name(a.ops) if a.ops else "no operator of %s" % OPS, l))
            return
        A = op_name(ops)
        if ops != OPS[0]:
            log("A = %s is cyclic on S" % A)
        # 2. a first prime: L and d
        primes = primes_1_mod(n, LIMIT)
        data, Lmax, d, piv0, last = {}, -1, None, None, None
        batch = max(1, min(4, a.jobs // dK))  # (the heights are small: a few primes suffice)
        while len(data) < a.max_primes:
            ls = [next(primes) for _ in range(batch if d is not None else 1)]
            futs = {(l, z): pool.submit(one_run, a, os.path.join(T, "%d-%d" % (l, z)), l, z,
                                        list(range(d if d else 1)), ops=ops)
                    for l in ls for z in prim_roots_of_unity(n, l)}
            for (l, z), fu in futs.items():
                try:
                    kk, res = fu.result()
                except Exception as ex:
                    log("l = %d, z = %d: %s; skipped" % (l, z, ex))
                    data.pop(l, None)
                    continue
                assert kk == k
                Ls = [r[0] for r in res]
                if d is None:
                    Lmax, d = Ls[0], k - Ls[0]
                    log("L = %d, d = k - L = %d" % (Lmax, d))
                    if d == 0:
                        print("CRT_NOT_STRANGE <%d, %d>: L = k mod %d" % (p, n, l))
                        final(p, n, None)
                        return
                    if d > 1:  # (the first run had only one functional)
                        data = {}
                        break
                if max(Ls) > Lmax:
                    log("l = %d: L = %d > %d; starting again" % (l, max(Ls), Lmax))
                    Lmax, d, data = max(Ls), k - max(Ls), {}
                    break
                if min(Ls) < Lmax:
                    log("l = %d, z = %d: L = %d < %d, skipped" % (l, z, min(Ls), Lmax))
                    data.pop(l, None)
                    continue
                e = echelon([r[2] for r in res], l)
                if e is None:
                    log("l = %d, z = %d: functionals dependent, skipped" % (l, z))
                    data.pop(l, None)
                    continue
                if piv0 is None:
                    piv0 = e[0]
                if e[0] != piv0:
                    log("l = %d, z = %d: pivots %s differ from %s, skipped" % (l, z, e[0], piv0))
                    data.pop(l, None)
                    continue
                data.setdefault(l, {})[z] = e
            data = {l: v for l, v in data.items() if len(v) == dK}
            if not data:
                continue
            rec, M = reconstruct(data, n, dK)
            log("%d primes (%d bits): %s" % (len(data), M.bit_length(),
                                              "reconstructed" if rec else "not yet"))
            if rec is None:
                continue
            # 4. exact check
            den = [math.lcm(*[b for tup in row for _, b in tup]) for row in rec]
            fn = os.path.join(a.out, "crt-%d-%d.txt" % (p, n))
            with open(fn, "w") as f:
                f.write("%d %d %d %d\n" % (p, n, d, len(rec[0])))
                for row, D in zip(rec, den):
                    for tup in row:
                        f.write(" ".join(str(x * (D // y)) for x, y in tup) + "\n")
            height = max(abs(x * (D // y)).bit_length() for row, D in zip(rec, den) for tup in row for x, y in tup)
            log("candidate written to %s (max %d bits); exact check" % (fn, height))
            out = run([a.magma, "-b", "P:=%d" % p, "N:=%d" % n, "Phi:=" + fn, "Ops:=" + ops,
                       S("verify_char0.m")], os.path.join(a.out, "crt-%d-%d.log" % (p, n)))
            m = re.findall(r"^CHAR0_VERIFIED .*$", out, re.M)  # (the log may have earlier runs)
            if m:
                print("STRANGE <%d, %d>: strdim %d (k = %d, L = %d, %s cyclic; %d primes, %d bits, "
                      "max height %d bits; %.0f s)" % (p, n, d * dK, k, Lmax, A, len(data), M.bit_length(),
                                                       height, time.time() - t0))
                print(m[-1])
                final(p, n, re.findall(r"^CHAR0_RESULT (<.*>)$", out, re.M)[-1])
                return
            if rec == last:
                print("CRT_FAILED <%d, %d>: the exact check fails for a stable reconstruction" % (p, n))
                return
            last = rec
            log("exact check failed; more primes")
        print("CRT_FAILED <%d, %d>: no verified reconstruction with %d primes" % (p, n, len(data)))
    finally:
        pool.shutdown(wait=False)
        shutil.rmtree(T, ignore_errors=True)


if __name__ == "__main__":
    main()
