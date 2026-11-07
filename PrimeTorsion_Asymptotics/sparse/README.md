# Sparse screening (Najman's method)

Screening of a pair (prime `p`, order `n`) for strangeness with memory `O(p)`, for
the search beyond `p = 5·10^5`, where the modular symbols spaces of
`strange_primes.magma` no longer fit into the memory of a node (about 300 GB at
`p = 10^6`). The method and most of the programs are Filip Najman's, from
<https://github.com/F-Najman/Sd> (MIT license, see `LICENSE-Najman`; directory
`degree22/` at commit 67e28e0, 2026-11-05), written for his paper on the sets
`S(d)` (degrees 9 to 22).

## What it computes

The even character `chi` of order `n` mod `p` with values in `F_q`, `q =
aux_prime(p)` (from `strange_primes.magma`), the space of modular symbols for
`chi` (weight 2, plus quotient) over `F_q`, described only by its Manin symbols
and their 2- and 3-term relations (the "Manin graph"), and `T_2` by the four
Merel–Heilbronn matrices of determinant 2. With `e' = (T_2 - 1 - 2chi(2))(T_2 -
2 - chi(2)) {0, oo}` and a random functional `u` on the quotient, the sequence
`u(T_2^i e')`, `i < 2k`, `k = dim S` (cuspidal part, `k = dim M - 2`), is
computed by a dual iteration on `k + 2` free coordinates; the others follow
from the relations along a spanning forest. Its linear complexity `L` is
determined exactly, with a Padé certificate (`C S = A mod x^(2k)`, `C(0) = 1`,
`gcd(C, A) = 1`, `L = max(deg C, deg A + 1) <= k`; then no shorter recurrence
exists).

The pair is **certified not strange** if `L = k`, or if `n = 2`, `chi(2) = 1`
and `L = k/2` (then every eigenvalue of `T_2` is double, see the comments on
"doubled" in `strange_primes.magma`). This is exactly trial 1 of
`screen_character_lean` in `strange_primes.magma` (Najman's Lemma 4.12). Every
other pair is reported as **uncertified** (`UNCERTIFIED <p, n, k, L, chi(2) =
1>`): it is strange, or `T_2` alone does not separate (rare); it needs the
further trials of `strange_primes.magma` and, if strange, a proof.

## Steps (`sparse_pair.py P N`)

1. `export_graph_fast.m` (Magma): the Manin graph, `T_2`, `e'` (Najman's script,
   with our `aux_prime` and the path of `core.m` of the local Magma installation:
   **adjust the `import` line** to another installation).
2. `bin/prepare_graph`: the exact rank of the relations (forest and left null
   vectors), hence `k`, a functional `u` vanishing on all relations, and the
   first 64 terms of the sequence.
3. `verify_graph.py`, `check_graph_prefix.m`: independent checks of the rank
   certificate, of `e'` and of the first 64 terms (Python, Magma).
4. `prepare_free.py`, `verify_free.py`: the plan of the dual iteration on the
   free coordinates, and its independent check.
5. `bin/krylov_packed`: the `2k` terms (Najman's scalar version; his
   `krylov_simd.cpp` needs AVX-512, which lipwig's EPYC 7302/7352 lack).
6. `bin/finish_L`: the linear complexity with its Padé certificate (NTL half-gcd;
   ours, after Najman's `finish_fast.cpp`, which only accepts `L = k`).

The large files (about 55 MB at `p = 10^6`) go to the node-local `/tmp` (or
`$TMPDIR`) and are removed at the end, also when the script is terminated.
Changes to Najman's files: the two paths in `export_graph_fast.m` (and its
variant `export_graph_crt.m`), three environment variables in `prepare_graph.cpp`
(`STRANGE_SEED`, `STRANGE_RANDOM_START`, `STRANGE_EIS`; default behavior
unchanged), and in
`verify_graph.py` and `verify_free.py` `hashlib.file_digest` (Python 3.11)
replaced by `hashlib.sha256` (lipwig has Python 3.9).

## Proof of strangeness (`crt_verify.py P N`)

For an uncertified pair, a multimodular computation in characteristic 0 that
needs no modular symbols space either (memory `O(p)`):

1. Cyclicity: an operator `A` in the Hecke algebra whose Krylov sequence of a
   random element of `S` (`STRANGE_RANDOM_START`) has linear complexity `k`; then
   `A` is cyclic on `S`, mod `q` and over `K = Q(zeta_n)`, and the Hecke algebra
   acts on `S` through `K[A]`. `A = T_2` if this holds mod `q` or mod the first
   prime `l` of 2.; otherwise the first operator of the list `OPS` (`T_2 + T_3`,
   `T_2 - T_3`, `T_2 + 2T_3`, `T_3`, `T_2 + T_3 + T_5`, ...) that is cyclic mod `l`
   (`--ops "2:1,3:1"`: only this one). `export_graph_crt.m` builds `A` from the
   Merel–Heilbronn matrices (`Ops:=...`; Magma's `HeilbronnMerel`, checked against
   `HeckeOperator` for `T_2`, `T_3`, `T_5`) and prints its eigenvalues `c_1, c_2` on
   the Eisenstein series, `sum c_l (1 + l chi(l))` and `sum c_l (l + chi(l))`;
   `prepare_graph` takes them from `STRANGE_EIS` (default: those of `T_2`).
2. For primes `l = 1 mod n` below `2^23.5` and each embedding `zeta_n -> z` of `K`
   into `F_l` (`export_graph_crt.m`, `chi(PrimitiveRoot(p)) = z`), and `d = k - L`
   random functionals `u`: `m` the minimal polynomial of `u(A^i e')` (from
   `finish_L`), and `phi = m(A*) (A* - c_1)(A* - c_2) u` (`project`): it vanishes on
   `F_l[A] e'` and on the Eisenstein part. These span the part `W` of the dual of
   `S` that annihilates `F_l[A] e'` (dimension `d`); its reduced echelon basis is
   canonical. If `L = k` for the first prime, the pair is not strange
   (`CRT_NOT_STRANGE`).
3. Chinese remaindering (all embeddings of each `l` give the coefficients in the
   power basis of `zeta_n`) and rational reconstruction over `K`.
4. `verify_char0.m` checks the result exactly over `K` (all in time `O(p)`): the
   functionals vanish on all 3-term relations (so they are functionals on the
   modular symbols), are linearly independent, span a space `W` stable under the
   duals of `T_l` for the primes `l` of `A` and of `T_2`, on which the
   characteristic polynomial of `A*` is coprime to the Eisenstein factor of `A` (so
   `W` lies in the dual of `S`), and vanish on `{0, oo}`.

With 1., every newform whose `A`-eigenvalue is a root of the characteristic
polynomial of `A` on `W` is strange, so `strdim >= d phi(n)`; each prime gives
`L <= dim K[A] e'`, so `strdim <= (k - L) phi(n)`. The output is
`STRANGE <p, n>: strdim ...` and the line `CHAR0_VERIFIED <p, n, strdim> ...` of
`verify_char0.m`, with the minimal polynomials over `Q` of the `a_2` of the
strange newforms (from `T_2` on `W`). If no operator of `OPS` is cyclic, the
output is `CRT_NOT_APPLICABLE`. Example: for 746497/3, `T_2` has a repeated
eigenvalue on `S` (so the sparse screening gives `L = k - 1`), `T_2 + T_3` is
cyclic, and `L = k`: not strange; 8713/4 (two strange newforms with `a_2 = -1`)
is proved strange with `T_2 + T_3`.

The entries of the reconstructed functionals are tiny (at most 4 bits for all
pairs tested), so a handful of primes suffices. Tested on xh (November 2026):
181/6, 853/6, 1777/3, 97/12, 101/10, 201493/6 (52 s) and 426301/6 (196 s; the
verification with Magma's modular symbols needed 96.5 GB and hours); strange
dimensions as found by `strange_primes.magma`. On lipwig, `cluster/crt.sbatch`
runs it for the pairs in `queue/open/`.

## Build

`build.sh [NTL_PREFIX]` compiles the four programs into `bin/` with
`-march=native` (run it on a node of the type that runs them) and tests
`finish_L` on random recurrences of known length (`gen_test.py`). `finish_L`
needs NTL; on lipwig it is NTL 11.5.1 in `~/sw/ntl`, built without GMP (no GMP
headers there):

```bash
cd ~/sw/src/ntl-11.5.1/src
./configure PREFIX=$HOME/sw/ntl NTL_GMP_LIP=off TUNE=x86 NATIVE=on && make -j32 && make install
```

## In the cluster search

With `sparse_from` > 0 in `config.json`, a worker runs the tasks with `p >=
sparse_from` as tasks of kind `N`, with `sparse_pair.py` (memory and time model
`sparse_mem_*`, `sparse_time_*` in `worker.py`). A certified pair ends in `done/` like a
screening with Magma (`RESULT <p, n, [], []>`); an uncertified one in `open/`,
and if `p <= magma_max_p` it is also requeued as an ordinary task (kind `S`,
`search_pair.m`). See `../cluster/README.md`.

## Measurements (November 2026, one character, five in parallel)

At `p ≈ 10^6` (`k ≈ 83000`), on lipwig (AMD EPYC 7302): export 60–72 s, checks
about 22 s, Krylov 233–248 s, Magma's `BerlekampMassey` in place of `finish_L`
114–117 s; peak memory 1.4 GB (in the export). On xh (Intel i7-13700K) about
half the time. With 32 pairs in parallel on one lipwig node at `p ≈ 7·10^5`
(`k ≈ 58300`): export 46 s, Krylov 112 s (no slowdown against five in
parallel), `finish_L` 1 s (Magma's `BerlekampMassey` 57 s, same results), peak
0.9 GB; all 32 certified, as in Najman's data. Model: `85 x + 245 x^2` seconds,
`x = p/10^6`; about 34000 core-hours for all 594414 pairs with `5·10^5 < p <
10^6`. Najman's own times (AMD EPYC 9175F with AVX-512): 0.3 min below
`5·10^5`, 1.8 min up to `10^6`, 18.8 min at `2.1·10^6`.
