// Driver for the tables of [Sto19], Section 4: runs SelChab (../SelChabDyn.magma) and the point
// search on one slice of a population of polynomials h and writes one record per curve
//   y^2 = x^(2g+1) + h(x)^2.
//
// Run from this directory (the loads and the genus-7 list are relative paths):
//   magma -b g:=2 k:=0 n:=113 out:=raw/g2-k0-n113.txt run_table.m < /dev/null
// Parameters (all given as strings on the command line):
//   g     genus, 2..7 (required)
//   k, n  process the curves with index i = k mod n of the population (default k = 0, n = 1)
//   out   output file (required); records are appended; an interrupted run is resumed
//         (indices already in the file are skipped)
//   B     coefficient bound of the population hlist(g, B) (default 25, 9, 5, 3, 3 for
//         g = 2, ..., 6)
//   hfile a file with one h per line (coefficients from the constant term up, separated by
//         commas; lines starting with # are comments) instead of the population; for g = 7
//         the default is genus7_h.txt
//   mem   memory limit in GB (default 5)
//   ifile a file with indices of the population, one per line: only these are processed
// The record format is described in README.md.

SetColumns(0);
if not assigned mem then mem := "5"; end if;
SetMemoryLimit(StringToInteger(mem)*2^30);
load "../SelChabDyn.magma";
SetClassGroupBounds("GRH");

P<x> := PolynomialRing(Rationals());

// The population of [Sto19] for g = 2, ..., 6 (as in makedata.magma of 2019): all h with
// deg h <= g, coefficients in [-b, b], h(0) odd, h(1) even, positive leading coefficient.
function hlist(g, b)
  list := [P!n : n in [-b..b] | IsOdd(n)];
  for d := 1 to g do
    list := [n*x^d + p : n in [-b..b], p in list];
  end for;
  return [p : p in list | IsEven(Integers()!&+Coefficients(p))
                           and LeadingCoefficient(p) gt 0];
end function;

// Read a list of h, one per line: coefficients from the constant term up, comma-separated.
function readhfile(file)
  pols := [P|];
  for line in Split(Read(file), "\n") do
    if #line gt 0 and line[1] ne "#" then
      Append(~pols, P![StringToInteger(c) : c in Split(line, ", ")]);
    end if;
  end for;
  return pols;
end function;

// One-line string without tabs and newlines.
function oneline(s)
  return Join(Split(s, "\t\n"), " ");
end function;

// Comma-separated list without spaces.
function commalist(seq)
  return Join([Strings()| Sprint(c) : c in seq], ",");
end function;

error if not assigned g, "parameter g missing";
error if not assigned out, "parameter out missing";
g := StringToInteger(g);
k := assigned k select StringToInteger(k) else 0;
n := assigned n select StringToInteger(n) else 1;
error if not (n ge 1 and k ge 0 and k lt n), "need 0 <= k < n";

if not assigned hfile and g eq 7 then hfile := "genus7_h.txt"; end if;
if assigned hfile then
  pols := readhfile(hfile);
  pop := "file:" cat hfile;
else
  error if g notin [2..6], "no default population for this genus; give hfile";
  b := assigned B select StringToInteger(B) else [25, 9, 5, 3, 3][g-1];
  pols := hlist(g, b);
  pop := Sprintf("hlist(%o,%o)", g, b);
end if;
NN := #pols;
error if exists{h : h in pols | Degree(h) gt g}, "deg h > g in the population";

// Resume: indices already recorded in the output file.
done := {Integers()|};
if System("test -f " cat out) eq 0 then
  for line in Split(Read(out), "\n") do
    if #line ge 4 and Substring(line, 1, 4) eq "REC\t" then
      fields := Split(line, "\t");
      Include(~done, StringToInteger(Substring(fields[4], 3, #fields[4] - 2))); // "i=..."
    end if;
  end for;
end if;

idx := [i : i in [1..NN] | i mod n eq k and i notin done];
if assigned ifile then
  // only the indices listed in ifile (one per line), among those of the slice
  wanted := {StringToInteger(s) : s in Split(Read(ifile), "\n") | #s gt 0 and s[1] ne "#"};
  error if not wanted subset {1..NN}, "ifile: index out of range";
  idx := [i : i in idx | i in wanted];
end if;
mv1, mv2, mv3 := GetVersion();
F := Open(out, "a");
fprintf F, "POP\tpop=%o\tg=%o\tN=%o\tk=%o\tn=%o\tskipped=%o\ttodo=%o\tmagma=%o\n",
        pop, g, NN, k, n, #done, #idx, Sprintf("%o.%o-%o", mv1, mv2, mv3);
Flush(F);

for i in idx do
  h := pols[i];
  f := x^(2*g+1) + h^2;
  err := "";
  t0 := Cputime();
  SetSeed(i);  // the 2019 random local-image search: reproducible per curve, also on resume
  try
    flag, d, info := SelChab(g, h);
  catch e
    flag := false; d := 0; info := <"ERROR", #Factorization(f) - 1, -1, true>;
    err := oneline(Sprint(e`Object));
  end try;
  tsel := Cputime(t0);
  t0 := Cputime();
  C := HyperellipticCurve(f);
  pts := Points(C : Bound := 10^4);
  xs := Sort(SetToSequence({pt[1]/pt[3] : pt in pts | pt[1] ne 0 and pt[3] ne 0}));
  tpts := Cputime(t0);
  code, jq2, img, inj := Explode(info);
  sel := code in {"LOCIMG", "ERROR"} select "NA" else Sprint(d);
  a3 := img ge 0 select (d - img eq jq2 select "T" else "F") else "NA";
  // The 2019 code stopped with "false" when Sel_2(J) --> H_2 was not injective.
  v2019 := code eq "LOCIMG" select "U" else code eq "ERROR" select "E"
             else inj and code in {"SEL0", "OK", "A3FAIL"} select "T" else "F";
  verdict := flag select "success"
               else code eq "A3FAIL" select "A3fail"
               else code eq "LOCIMG" select "undet"
               else code eq "ERROR" select "error" else "fail";
  if code eq "LOCIMG" then err := Sprintf("local image at p = %o not determined", -d); end if;
  fprintf F, "REC\tpop=%o\tg=%o\ti=%o\th=%o\tsel=%o\tjq2=%o\timg=%o\ta3=%o\tinj=%o\tv2019=%o"
             cat "\tcode=%o\tv=%o\txs=%o\tnxs=%o\ttsel=%o\ttpts=%o\terr=%o\n",
          pop, g, i, commalist(Coefficients(h)), sel, jq2, img lt 0 select "NA" else Sprint(img),
          a3, inj select "T" else "F", v2019, code, verdict, commalist(xs), #xs, tsel, tpts, err;
  Flush(F);
end for;
fprintf F, "END\tk=%o\tn=%o\tdone=%o\n", k, n, #idx;
Flush(F);
delete F;
quit;
