// project FREE POLY OUT: the functional phi = m(T_2*) u on all generators, for crt_verify.py.
// FREE is the plan of prepare_free.py (Najman's format: the gauged random functional u, which
// vanishes on all relations, the dual step of T_2 on the k + 2 free coordinates, and the
// propagation to the other coordinates); POLY is "L c_0 ... c_L", and m(x) = x^L C(1/x). For
// crt_verify.py, C is the polynomial of finish_L (x^L C(1/x) is the minimal polynomial of the
// sequence u(T_2^i e')) times (1 - c_1 x)(1 - c_2 x), c_1 = 1 + 2 chi(2), c_2 = 2 + chi(2) (the
// Eisenstein eigenvalues of T_2). Then phi vanishes on Q[T_2] e' and on the Eisenstein part,
// i.e. it lies in the part of the dual of S that annihilates Q[T_2] e' (dimension k - L when
// T_2 is cyclic on S). The parser and the step are those of Najman's krylov_packed.cpp (MIT, see
// LICENSE-Najman). OUT: "q ns a" (a: eigenvalue of T_2* on phi, or -1 if phi is not an
// eigenvector) and the values of phi on the ns generators (not gauged).
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
using namespace std;
struct Entry { uint32_t j, a; };
struct Column { uint32_t r, s, rho, root; };
struct Pivot { uint32_t root, j, r, s, rho, iv; };
struct Tree { uint32_t r, p, j; };
int main(int argc, char** argv) {
  assert(argc == 4);
  ifstream in(argv[1]); assert(in);
  uint64_t q; size_t p, ord, n, k, nr, nf, ne, nt, np, nroot;
  in >> q >> p >> ord >> n >> k >> nr >> nf >> ne >> nt >> np >> nroot;
  assert(q > 3 && q <= UINT32_MAX && nf == k + 2 && nf + nt + np == n);
  vector<uint32_t> mu(nr), scale(n), w(n), check(64), free(nf);
  for (auto& x : mu) { in >> x; assert(x && x < q); }
  for (auto& x : scale) { in >> x; assert(x && x < q); }
  for (auto& x : w) { in >> x; assert(x < q); }
  for (auto& x : check) { in >> x; assert(x < q); }
  for (auto& x : free) { in >> x; assert(x < n); }
  vector<Entry> wind(ne); for (auto& e : wind) { in >> e.j >> e.a; assert(e.j < n && e.a && e.a < q); }
  vector<vector<Entry>> R(nf);
  for (auto& row : R) { size_t z; in >> z; assert(z <= n); row.resize(z); for (auto& e : row) { in >> e.j >> e.a; assert(e.j < n && e.a && e.a < q); } }
  vector<Column> cols(nf); for (auto& c : cols) { in >> c.r >> c.s >> c.rho >> c.root; assert(c.r <= nr && c.s <= nr && c.rho < q && c.root <= nr); }
  vector<Pivot> pivs(np);
  for (auto& a : pivs) { in >> a.root >> a.j >> a.r >> a.s >> a.rho >> a.iv; assert(a.root < nr && a.j < n && a.r < nr && a.s < nr && a.rho < q && ((uint64_t(1) + a.rho) * a.iv) % q == 1); }
  vector<Tree> tree(nt); for (auto& a : tree) { in >> a.r >> a.p >> a.j; assert(a.r < nr && a.p <= nr && a.j < n); }
  vector<uint32_t> roots(nroot); for (auto& r : roots) { in >> r; assert(r < nr); }
  assert(in); string extra; assert(!(in >> extra));
  ifstream pin(argv[2]); assert(pin); long L; pin >> L; assert(L >= 0 && size_t(L) <= k + 2);
  vector<uint64_t> C(L + 1); for (auto& c : C) { pin >> c; assert(c < q); } assert(pin && C[0] == 1);

  // (Barrett reduction as in krylov_packed.cpp)
  const uint64_t reciprocal = uint64_t(((__uint128_t)1 << 64) / q);
  auto reduce = [&](uint64_t z) -> uint64_t { uint64_t h = uint64_t(((__uint128_t)z * reciprocal) >> 64); uint64_t r = z - h * q; return r >= q ? r - q : r; };
  auto add = [&](uint64_t a, uint64_t b) -> uint64_t { uint64_t z = a + b; return z >= q ? z - q : z; };
  auto neg = [&](uint64_t a) -> uint64_t { return a ? q - a : 0; };
  auto mul = [&](uint64_t a, uint64_t b) -> uint64_t { return reduce(a * b); };
  size_t maxrow = 0; for (auto& row : R) maxrow = max(maxrow, row.size());
  const bool safe_rows = maxrow * ((__uint128_t)(q - 1) * (q - 1)) <= UINT64_MAX;
  auto pw = [&](uint64_t a, uint64_t e) { uint64_t z = 1; while (e) { if (e & 1) z = mul(z, a); a = mul(a, a); e >>= 1; } return z; };
  auto inv = [&](uint64_t a) { assert(a); return pw(a, q - 2); };
  // the free coordinates of x o T_2 for a gauged functional x (all coordinates)
  auto dual = [&](const vector<uint32_t>& x, vector<uint32_t>& vals) {
    for (size_t i = 0; i < nf; i++) {
      if (safe_rows) { uint64_t z = 0; for (auto& e : R[i]) z += uint64_t(x[e.j]) * e.a; vals[i] = reduce(z); }
      else { uint64_t z = 0; for (auto& e : R[i]) z = add(z, mul(x[e.j], e.a)); vals[i] = z; }
    }
  };
  // all coordinates of the functional with the given free coordinates (propagation along the
  // relations, as in krylov_packed.cpp)
  vector<uint32_t> b(nr), res(nr + 1);
  auto reconstruct = [&](const vector<uint32_t>& vals, vector<uint32_t>& x) {
    fill(b.begin(), b.end(), 0); fill(res.begin(), res.end(), 0);
    for (size_t i = 0; i < nf; i++) {
      auto v = vals[i]; x[free[i]] = v; auto& c = cols[i]; if (c.r == nr) continue;
      b[c.r] = add(b[c.r], v); uint64_t y = 0;
      if (c.s != nr) { y = mul(c.rho, v); b[c.s] = add(b[c.s], y); }
      if (c.root != nr) res[c.root] = add(res[c.root], add(v, y));
    }
    for (auto& a : pivs) { auto v = mul(neg(res[a.root]), a.iv); x[a.j] = v; b[a.r] = add(b[a.r], v); b[a.s] = add(b[a.s], mul(a.rho, v)); }
    for (auto& a : tree) { x[a.j] = neg(b[a.r]); if (a.p != nr) b[a.p] = add(b[a.p], b[a.r]); }
    for (auto r : roots) assert(b[r] == 0);
  };
  // phi = sum_t m_t (T*)^t u with m_t = c_(L-t)
  vector<uint32_t> vals(nf), acc(nf, 0);
  for (long t = 0; t <= L; t++) {
    uint64_t m = C[L - t];
    if (m) for (size_t i = 0; i < nf; i++) acc[i] = add(acc[i], mul(m, w[free[i]]));
    if (t < L) { dual(w, vals); reconstruct(vals, w); }
  }
  vector<uint32_t> phi(n); reconstruct(acc, phi);
  uint64_t at_e = 0; for (auto& e : wind) at_e = (at_e + uint64_t(phi[e.j]) * e.a) % q;
  // eigenvector? (compare phi o T_2 with a phi on the free coordinates)
  dual(phi, vals);
  long a = -1; size_t i0 = 0; while (i0 < nf && phi[free[i0]] == 0) i0++;
  if (i0 < nf) {
    uint64_t c = mul(vals[i0], inv(phi[free[i0]])); bool eig = true;
    for (size_t i = 0; i < nf && eig; i++) eig = vals[i] == mul(c, phi[free[i]]);
    if (eig) a = c;
  }
  ofstream out(argv[3]); assert(out);
  out << q << ' ' << n << ' ' << a << '\n';
  for (size_t j = 0; j < n; j++) out << mul(phi[j], inv(scale[j])) << (j + 1 < n ? ' ' : '\n');
  assert(out);
  cout << "S23_PROJECTION q=" << q << " generators=" << n << " L=" << L << " zero=" << (i0 == nf ? 1 : 0)
       << " at_e=" << at_e << " eigenvalue=" << a << endl;
}
