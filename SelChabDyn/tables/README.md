# The tables of Section 4

These files compute the tables at the end of Section 4 of *An application of "Selmer group
Chabauty" to arithmetic dynamics* (revised version, 2026). For `g = 2, ..., 7` the tables sort the
curves

```math
C_h \colon y^2 = x^{2g+1} + h(x)^2, \qquad h \in \mathbb{Z}[x],\ \deg h \le g,\ h(0) \text{ odd},\ h(1) \text{ even}
```

by the dimension of the 2-Selmer group of the Jacobian and by the outcome of the algorithm of
Section 2, which tries to prove that `∞` and `(0, ±h(0))` are the only rational points.

| File | Content |
|---|---|
| `run_table.m` | runs `SelChab` (from `../SelChabDyn.magma`) and a point search on a slice of a population; one record per curve |
| `maketable.py` | the table of one genus from the records of all its slices, with consistency checks |
| `make_genus7.m` | the sampler of the genus-7 population |
| `genus7_h.txt` | the 1000 genus-7 polynomials `h` it produced, in the order drawn |
| `ratpoints/` | the further point search on the curves that the algorithm does not settle |
| `raw/` | the records of our runs, compressed with `xz` |

## Populations

- Genus 2 to 6: all `h` with `deg h <= g`, coefficients in `[-B, B]`, `h(0)` odd, `h(1)` even and
  positive leading coefficient (`h` and `-h` give the same curve), with `B = 25, 9, 5, 3, 3`; these
  are 16900, 17150, 21960, 16808 and 117648 curves. The index `i` of a curve is its position in
  this list, from 1.
- Genus 7: 1000 distinct `h` with `deg h <= 7`, coefficients in `[-10, 10]` and the same
  conditions, drawn uniformly by rejection sampling (`make_genus7.m` with `SetSeed(20261115)` in
  Magma V2.30-1). The run reads them from `genus7_h.txt`, so the sampler is not needed to
  reproduce the table.
- As stated in the paper, the class and unit groups are computed assuming GRH
  (`SetClassGroupBounds("GRH")`).
- Points: Magma's `Points(C : Bound := 10^4)`, i.e., naive height of `x` at most `10^4`. The extra
  points are those with `x != 0` finite.

## Running

From this directory:

```sh
mkdir -p new
magma -b g:=6 k:=0 n:=16 out:=new/g6-k0-n16.txt run_table.m < /dev/null > new/g6-k0-n16.log 2>&1
```

runs the curves with index `i ≡ k mod n` of the genus-6 population. The other parameters are
described at the top of `run_table.m`. The output is appended and flushed after each curve, and a
run with the same `out` skips the indices already there, so an interrupted slice is resumed by
starting it again. When all slices of a genus are done,

```sh
python3 maketable.py --merged --points=ratpoints/out-1e7.tsv new/g6-*.txt
```

prints the table, as plain text and as LaTeX. The rows are exclusive; a curve goes into the first
that applies:

1. *more pts.*: extra points found;
2. *success*: the algorithm proves that there are no other rational points;
3. *failure (A3)*: all checks of Section 2 pass, but Assumption (A3) fails;
4. *failure*: one of the checks fails.

With `--merged` the rows *failure (A3)* and *failure* are merged, as in the paper. Below the
table, `maketable.py` lists the codes returned by `SelChab`, the CPU time and some special cases.
It checks that every index occurs exactly once, that no curve with a proof has extra points, and
that the fields of each record are consistent; a violation is reported as `ERROR` (exit status 1).

The CPU time of our runs (Magma V2.30-1): 0.9, 1.3, 2.3 and 2.6 hours for genus 2 to 5, 56 hours
for genus 6 and 1.6 hours for genus 7. Magma's memory use stays near 100 MB.

## Our records

`raw/` holds the records of our runs: one file for each genus, except genus 6, which was run in
16 slices (`g6-k<k>-n16.txt`). Unpack them with `xz -dk raw/*.xz`; then, for example,

```sh
python3 maketable.py --merged --points=ratpoints/out-1e7.tsv raw/g6-*.txt
```

prints the table of genus 6 in the paper.

The first run (2026-11-14/15) used an earlier version of `SelChabDyn.magma`, which stopped with
the code `NONINJ` when `Sel_2(J) → H_2` is not injective (Assumption (A3) of the 2019 version of
the paper). The 8873 curves where this happened were run again with the present version
(2026-11-17), and their new records replaced the old ones. None of them is a success, so the
tables did not change. The other records keep the earlier format: the field `a4` instead of `a3`
(the earlier code called the present (A3) Assumption (A4)), no field `inj` (it would be `T`), and
the code `A4FAIL` and verdict `A4fail` instead of `A3FAIL` and `A3fail`. `maketable.py` reads both
formats.

## Record format

One line per curve, tab-separated `key=value` fields after `REC`:

| key | content |
|---|---|
| `pop`, `g`, `i` | population, genus, index of the curve in the population |
| `h` | coefficients of `h`, from the constant term up |
| `sel` | dim `Sel_2(J)` |
| `jq2` | dim `J(Q)[2]`, i.e., the number of irreducible factors of `x^(2g+1) + h^2` over `Q`, minus 1 |
| `img` | dim of the image of `Sel_2(J)` in `F_2^g` (`NA` if the algorithm stopped before) |
| `a3` | whether (A3) holds: `T`, `F`, or `NA` (image not computed) |
| `inj` | whether `Sel_2(J) → H_2` is injective: `T`, `F` |
| `v2019` | the verdict of the code of 2019, which did not check (A3) and stopped when `inj` is `F` |
| `code` | the code returned by `SelChab` (see `../SelChabDyn.magma`) |
| `v` | the verdict: `success`, `A3fail`, `fail`, `undet`, `error` |
| `xs`, `nxs` | the extra `x`-coordinates (comma-separated) and their number |
| `tsel`, `tpts` | CPU seconds of `SelChab` and of the point search |
| `err` | an error message, if any |

## Further point search

The curves without extra points that the algorithm does not settle were searched again with
`ratpoints` (version 3.1.1) up to naive height `10^7` of `x`:

```sh
cd ratpoints
python3 mklist.py > curves.txt
python3 run.py 10000000 4 out-1e7.tsv
```

`mklist.py` takes the curves from the unpacked records in `../raw/`. `run.py H JOBS OUT` runs
`ratpoints` on each curve of `curves.txt` with `JOBS` processes and writes one line per curve: `g`,
`i`, `h`, `H`, the number and the list of the extra `x`, and the seconds taken; it skips the curves
already in `OUT`. The result is `out-1e7.tsv` (36895 curves; about 13.5 CPU hours). Two curves of
genus 2 have further points, `h = 13x^2 - 2x - 13` with `x = 50125/246^2` and `h = 21x^2 + 24x + 21`
with `x = 3010/107^2`; there are no others. The option `--points=ratpoints/out-1e7.tsv` of
`maketable.py` adds these points to the records before the curves are sorted into rows. The file
also contains the genus-6 curve `h = x^6 + 3x^5 + 2x^2 + 3x + 3`, for which the algorithm proves the
result.
