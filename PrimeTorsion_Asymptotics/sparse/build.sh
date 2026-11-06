#!/bin/bash
# build.sh [NTL_PREFIX]: compile the C++ steps (also those of crt_verify.py) into bin/ (on a node of the CPU type that runs
# them: -march=native). finish_L needs NTL (default prefix ~/sw/ntl; NTL 11.5.1 built with
# ./configure PREFIX=$HOME/sw/ntl NTL_GMP_LIP=off TUNE=x86 NATIVE=on on lipwig, which has no
# GMP headers), then runs finish_L on random recurrences of known length.
set -e
cd "$(dirname "$0")"
NTL=${1:-$HOME/sw/ntl}
mkdir -p bin
g++ -O3 -march=native -std=c++17 -o bin/prepare_graph prepare_graph.cpp
g++ -O3 -march=native -std=c++17 -o bin/krylov_packed krylov_packed.cpp
g++ -O3 -march=native -std=c++17 -o bin/project project.cpp
g++ -O3 -march=native -std=c++17 -I"$NTL/include" -o bin/finish_L finish_L.cpp -L"$NTL/lib" -lntl -pthread
t=$(mktemp -d)
for kl in "1000 1000" "1000 500" "1000 999" "1000 1" "1000 0" "3000 3000" "3000 1500"; do
  set -- $kl
  python3 gen_test.py "$t/raw.m" 4263001 "$1" "$2" "$1$2"
  bin/finish_L "$t/raw.m" | grep -q "dimension=$1 complexity=$2 certificate=ok" || { echo "finish_L test k=$1 L=$2 FAILED"; exit 1; }
done
rm -rf "$t"
echo "built in $PWD/bin; finish_L tests passed"
