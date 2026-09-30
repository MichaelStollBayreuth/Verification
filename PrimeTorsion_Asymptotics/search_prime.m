// Search for strange primes, one prime per Magma process:
//   magma -b p:=100003 search_prime.m
// prints one line "RESULT <p, candidates, verified>" (see strange_primes.magma:
// candidates as returned by screen_prime_lean, verified as returned by
// verify_candidate) and fails (exit code 1) if a candidate is not confirmed.
// run_search.sh runs this for all primes in a range with GNU parallel.
SetQuitOnError(true);
SetColumns(0);
load "strange_primes.magma";
p := StringToInteger(p);
SetVerbose("User1", 1);
t0 := Cputime();
cands := screen_prime_lean(p);
verified := [verify_candidate(c) : c in cands];
printf "RESULT %o\n", &cat[x cat " " : x in Split(Sprint(<p, cands, verified>), "\n")]; // one line
assert forall{v : v in verified | v[4]};
printf "p = %o: %o strange character(s) (%o s)\n", p, #verified, Cputime(t0);
quit;
