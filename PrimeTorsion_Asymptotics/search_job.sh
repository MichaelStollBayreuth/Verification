#!/bin/bash
# One job of run_search.sh: run search_prime.m for the prime $1 and exit with
# status 0 only if Magma reported success (Magma's own exit status is 0 even
# after some errors, e.g. an undefined identifier).
MAGMA=${MAGMA:-magma}
out=$("$MAGMA" -b p:="$1" search_prime.m < /dev/null 2>&1)
status=$?
printf '%s\n' "$out"
[ "$status" -eq 0 ] && printf '%s\n' "$out" | grep -q '^RESULT ' && printf '%s\n' "$out" | grep -q ' strange character(s) ('
