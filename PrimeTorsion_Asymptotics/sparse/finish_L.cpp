// finish_L RAW [POLY]: the linear complexity L of the Krylov sequence in RAW (krylov_packed output:
// q, dimension k, 2k terms), with Najman's Pade certificate (degree22/finish_fast.cpp):
// C S = A mod x^(2k), C(0) = 1, gcd(C, A) = 1 and L = max(deg C, deg A + 1) <= k; then no
// recurrence of length < L exists (it would give C | C' with deg C' < L). Unlike finish_fast
// it does not require L = k: for the quadratic character with chi(2) = 1 the certificate is
// L = k/2, and otherwise L is the defect information for the fallback. A failed check is
// reported (certificate=FAILED), not asserted. With POLY it writes "L c_0 c_1 ... c_L", the
// coefficients of C (c_0 = 1, padded to length L + 1): s_i + c_1 s_(i-1) + ... + c_L s_(i-L) = 0
// for L <= i < 2k, so x^L C(1/x) is the minimal polynomial of the sequence (crt_verify.py).
#include <NTL/lzz_pX.h>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace NTL; using namespace std;
int main(int argc, char** argv) {
  assert(argc == 2 || argc == 3); ifstream in(argv[1]); assert(in);
  string s((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());
  auto scalar = [&](const string& name) {
    size_t j = s.find(name + ":="); assert(j != string::npos); j += name.size() + 2; assert(isdigit(s[j]));
    uint64_t v = 0; while (isdigit(s[j])) v = 10*v + s[j++] - '0'; assert(s[j] == ';'); return v; };
  uint64_t q = scalar("q"); long k = scalar("dimension"); assert(q > 3 && q < UINT32_MAX && k > 0);
  zz_p::init(q);
  size_t j = s.find("sequence:=["); assert(j != string::npos); j += 11; vector<long> seq;
  while (true) {
    while (isspace(s[j])) j++; assert(isdigit(s[j]));
    uint64_t a = 0; while (isdigit(s[j])) a = 10*a + s[j++] - '0'; assert(a < q); seq.push_back(a);
    while (isspace(s[j])) j++; if (s[j] == ']') break; assert(s[j++] == ',');
  }
  assert(seq.size() == size_t(2*k));
  zz_pX S, U, V, C, A;
  for (long i = 0; i < 2*k; i++) SetCoeff(S, i, seq[i]);
  SetCoeff(U, 2*k); V = S;
  if (deg(V) >= k) { zz_pXMatrix M; XHalfGCD(M, U, V, k + 1); C = M(1, 1); A = V; }
  else { SetCoeff(C, 0); A = S; }
  bool ok = !IsZero(coeff(C, 0)); long L = -1;
  if (ok) {
    zz_p c = inv(coeff(C, 0)); C *= c; A *= c;
    L = max(deg(C), deg(A) + 1);
    zz_pX error = C*S - A; trunc(error, error, 2*k);
    ok = L <= k && IsZero(error) && IsOne(GCD(C, A));
  }
  if (ok && argc == 3) {
    ofstream f(argv[2]); assert(f); f << L;
    for (long i = 0; i <= L; i++) f << ' ' << rep(coeff(C, i));
    f << '\n'; assert(f);
  }
  cout << "S21_LINEAR_COMPLEXITY q=" << q << " dimension=" << k << " complexity=" << L
       << " certificate=" << (ok ? "ok" : "FAILED") << endl;
  return ok ? 0 : 2;
}
