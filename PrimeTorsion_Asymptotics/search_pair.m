// Search for strange characters, one pair (prime p, character order n) per
// Magma process:
//   magma -b p:=100003 n:=3 search_pair.m
// screens the even character of order n mod p (n > 1 must divide (p-1)/2)
// with screen_character_lean (as screen_order_lean does) and verifies a
// candidate, if there is one, with verify_candidate (see strange_primes.magma).
// Output:
//   CANDIDATE <p, n, q, z, d, l, coeffs>      only if there is a candidate,
//                                             printed before the verification
//   RESULT <p, n, candidates, verified>       one line; "RESULT <p, n, [], []>"
//                                             says that the character is not strange
//   p = ..., n = ...: ... (... s, ... MB)     final line (CPU time, peak memory)
// If the verification did not finish (e.g. the process was killed), it can be
// redone without the screening from the CANDIDATE line:
//   magma -b 'cand:=<p, n, q, z, d, l, coeffs>' search_pair.m
// With verify:=no a screening that finds a candidate stops after the CANDIDATE
// line and prints "SCREENED <p, n>" instead of the RESULT and final lines, so
// that the verification can run as a process of its own (e.g. with Magma's
// "large" binary, which the verification needs from about p = 4.2e5 on).
// The process fails (exit code 1) if a candidate is not confirmed.
SetQuitOnError(true);
SetColumns(0);
load "strange_primes.magma";
SetVerbose("User1", 1);
t0 := Cputime();
oneline := func<x | &cat[s cat " " : s in Split(Sprint(x), "\n")]>;
// (Magma needs every identifier in a select expression to be assigned.)
if not assigned cand then cand := ""; end if;
if not assigned p then p := "0"; n := "0"; end if;
if not assigned verify then verify := "yes"; end if;
screen := cand eq "";
p := screen select StringToInteger(p) else (eval cand)[1];
n := screen select StringToInteger(n) else (eval cand)[2];
chi := order_character(p, n);
// The setup of the screening (it builds the modular symbols space) is a
// top-level statement of its own, and not inside an if-block: Magma frees the
// memory of the space only when the top-level statement has finished, and the
// long first trial of the screening does not need it (see lean_setup).
setup := screen select lean_setup(chi) else false;
cands := screen select candidate_list(chi, screen_character_lean(chi : setup := setup)) else [eval cand];
delete setup;
if screen then
  for c in cands do printf "CANDIDATE %o\n", oneline(c); end for;
  if verify eq "no" and not IsEmpty(cands) then
    printf "SCREENED <%o, %o>\n", p, n;
    quit;
  end if;
end if;
verified := [verify_candidate(c) : c in cands];
printf "RESULT %o\n", oneline(<p, n, cands, verified>);
assert forall{v : v in verified | v[4]};
printf "p = %o, n = %o: %o (%o s, %o MB)\n", p, n,
       IsEmpty(verified) select "not strange" else Sprintf("STRANGE, strdim %o", verified[1,2]),
       Cputime(t0), GetMaximumMemoryUsage() div 2^20;
quit;
