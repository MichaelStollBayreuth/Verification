// verify_char0.m: exact check of a CRT certificate of strangeness (crt_verify.py).
//   magma -b P:=p N:=n Phi:=FILE [Ops:="l1:c1,l2:c2,..."] verify_char0.m
// FILE: "p n d ns" and then, for each of d functionals, ns lines with the phi(n) integer
// coefficients (power basis of zeta_n) of its values on the generators of the 2-term quotient
// of the Manin symbols (in the order of Sparse2Quotient, as in export_graph_fast.m), for the
// even character chi of order n with chi(PrimitiveRoot(p)) = zeta_n.
// Checks, over K = Q(zeta_n): the functionals vanish on all 3-term relations (so they are
// functionals on the space M of modular symbols, plus quotient), they are linearly independent,
// their span W is stable under the dual of T_2 (Heilbronn matrices of determinant 2, as in
// export_graph_fast.m), its characteristic polynomial g is coprime to the Eisenstein factor
// (x - 1 - 2 chi(2))(x - 2 - chi(2)), so W lies in the dual of the cuspidal subspace S, and
// every functional in W vanishes on the winding element {0, oo}. Then W lies in the annihilator
// of K[T_2] {0, oo}; if T_2 is cyclic on S (checked by crt_verify.py mod q), the newforms
// whose T_2-eigenvalues are the roots of g are strange, so strdim >= d phi(n).
// With Ops (default "2:1"), the same for the operator A = c1 T_l1 + c2 T_l2 + ... in place of
// T_2 (A cyclic on S, checked by crt_verify.py): W is stable under T_l* for all l in Ops (and
// under T_2*), the characteristic polynomial of A* on W is coprime to the Eisenstein factor of
// A, and W vanishes on {0, oo}; the T_l are given by the Heilbronn matrices of Merel.
// The import path of core.m must point to the local Magma installation.
SetQuitOnError(true); SetColumns(0);
import "/opt/hpc-lipwig/public/group_software/math/vivaorg_10150005/magma/V2.30-1/package/Geometry/ModSym/core.m":
  ManinSymbolList, Sparse2Quotient;
t0 := Cputime();
p := StringToInteger(P); n := StringToInteger(N);
K<z> := CyclotomicField(n); dK := Degree(K);
G := DirichletGroup(p, K); chi := G.1^ExactQuotient(#G, n);
g0 := PrimitiveRoot(p);
ee := [e : e in [1..n] | Gcd(e, n) eq 1 and chi(g0)^e eq z]; assert #ee eq 1;
chi := chi^ee[1];
assert Order(chi) eq n and IsEven(chi) and chi(g0) eq z;
// the 2-term quotient (as in export_graph_fast.m, over K)
ml := ManinSymbolList(2, p, K); eps := ValueList(chi); pp := ml`p1list;
A := MatrixAlgebra(Integers(p), 2);
function Apply(h, j)
  ind, scalar := P1Reduce(pp[j]*h, pp); assert ind gt 0;
  return <eps[Integers()!scalar], ind>;
end function;
xS := [Apply(A![0,-1,1,0], j) : j in [1..p+1]]; xI := [Apply(A![-1,0,0,1], j) : j in [1..p+1]];
rel := [[j, xS[j][2]] : j in [1..p+1]] cat [[j, xI[j][2]] : j in [1..p+1]];
rc := [[K!1, xS[j][1]] : j in [1..p+1]] cat [[K!1, -xI[j][1]] : j in [1..p+1]];
sg, sq, sc := Sparse2Quotient(rel, rc, p+1, K);
delete rel, rc, xS, xI;
ns := #sg;
printf "quotient: %o generators (%o s)\n", ns, Cputime(t0);
// the functionals
ls := Split(Read(Phi), "\n");
h := [StringToInteger(x) : x in Split(ls[1], " ")];
assert h[1] eq p and h[2] eq n and h[4] eq ns;
d := h[3]; assert #ls eq 1 + d*ns;
Phis := [[K | Eltseq([StringToInteger(x) : x in Split(ls[1 + (t-1)*ns + i], " ")]) : i in [1..ns]] : t in [1..d]];
delete ls;
printf "read %o functional(s) (%o s)\n", d, Cputime(t0);
val := func<phi, c, j | sq[j] eq 0 select K!0 else c*sc[j]*phi[sq[j]]>;
// 3-term relations
T := A![0,-1,1,-1]; TT := A![-1,1,-1,0];
mask := [false : i in [1..p+1]]; nrel := 0;
for j in [1..p+1] do
  if not mask[j] then
    t := Apply(T, j); u := Apply(TT, j); mask[t[2]] := true; mask[u[2]] := true; nrel +:= 1;
    for phi in Phis do
      assert val(phi, K!1, j) + val(phi, t[1], t[2]) + val(phi, u[1], u[2]) eq 0;
    end for;
  end if;
end for;
printf "all %o 3-term relations hold (%o s)\n", nrel, Cputime(t0);
// the operator A = sum of c_l T_l
ops := [[StringToInteger(x) : x in Split(o, ":")] : o in Split(assigned Ops select Ops else "2:1", ",")];
assert forall{o : o in ops | #o eq 2 and IsPrime(o[1]) and p mod o[1] ne 0};
ells := Sort(SetToSequence({2} join {o[1] : o in ops}));
// independence (on the pivot columns of an echelon form)
B := Matrix(K, d, ns, &cat Phis);
E := EchelonForm(B);
assert Rank(E) eq d; // the functionals are linearly independent
piv := [Min([i : i in [1..ns] | E[t, i] ne 0]) : t in [1..d]];
Bp := HorizontalJoin([ColumnSubmatrixRange(B, j, j) : j in piv]);
// T_l: (phi o T_l)(g_i) = sum over the Heilbronn matrices h of phi(g_i h)
Mats := AssociativeArray();
for l in ells do
  HH := l eq 2 select [A![1,0,0,2], A![2,0,0,1], A![2,1,0,1], A![1,0,1,2]] else [A!h : h in HeilbronnMerel(l)];
  tval := function(phi, i)
    s := K!0;
    for hh in HH do a := Apply(hh, sg[i]); s +:= val(phi, a[1], a[2]); end for;
    return s;
  end function;
  TB := Matrix(K, d, ns, &cat[[tval(phi, i) : i in [1..ns]] : phi in Phis]);
  TBp := HorizontalJoin([ColumnSubmatrixRange(TB, j, j) : j in piv]);
  Mat := Solution(Bp, TBp); // Mat * B = TB on the pivot columns
  assert Mat*B eq TB; // W is stable under T_l*, and Mat is its matrix
  Mats[l] := Mat;
  delete TB;
  printf "T_%o applied, W is stable (%o s)\n", l, Cputime(t0);
end for;
PK<x> := PolynomialRing(K);
g := PK!CharacteristicPolynomial(Mats[2]);
MA := &+[o[2]*Mats[o[1]] : o in ops];
gA := PK!CharacteristicPolynomial(MA);
EisA := (x - &+[o[2]*(1 + o[1]*chi(o[1])) : o in ops])*(x - &+[o[2]*(o[1] + chi(o[1])) : o in ops]);
assert Gcd(gA, EisA) eq 1;
// the winding element {0, oo} = Manin symbol (0:1)
ind := Position(pp, Parent(pp[1])![0,1]); assert ind gt 0;
for phi in Phis do assert val(phi, K!1, ind) eq 0; end for;
printf "W is stable under T_l* for l in %o, cuspidal, and vanishes on {0, oo} (%o s)\n", ells, Cputime(t0);
// (one line each: the characteristic polynomial of T_2 on W over K = Q(z), z = zeta_n, and the
// minimal polynomials over Q of the eigenvalues a_2 of the strange newforms)
fg := Factorization(gA);
mq := {AbsoluteMinimalPolynomial(r[1]) : r in Roots(g, SplittingField(g))};
printf "CHAR0_VERIFIED <%o, %o, %o> T_2 on W: %o;%o a_2 over Q: %o\n", p, n, d*dK, Sprint(g),
       ops eq [[2, 1]] select "" else " A = " cat Ops cat " on W: " cat Sprint(gA) cat ";",
       Join([Sprint(f) : f in mq], ", ");
// (as verify_candidate in strange_primes.magma: <n, strdim, sizes of the Galois orbits of
// strange newforms, true>; A is cyclic, so the factors of gA belong to the Galois orbits)
printf "CHAR0_RESULT <%o, %o, %o, true>\n", n, d*dK, Sort([dK*Degree(f[1]) : f in fg]);
quit;
