#!/usr/bin/env python3
"""Table of [Sto19], Section 4, from the raw records written by run_table.m.

Usage: python3 maketable.py [--partial] [--merged] [--points=PTS] FILE...

All FILEs must belong to one population (one genus). The rows are exclusive; a curve goes into
the first of these that applies (the table prints success first, as in the paper):
  more pts.     extra points found (x != 0, finite, naive height of x <= 10^4, or in PTS), whatever
                the verdict
  success       the method with the check of (A3) proves C(Q) = {oo, P_0, -P_0}
  failure (A3)  the checks of the residue disks pass, but (A3) fails (code A3FAIL; when
                Sel_2(J) --> H_2 is injective, the 2019 algorithm succeeds on these curves)
  failure       one of the checks fails (codes ODDX, DISC0, DISCINF)
  undetermined  the local image at an odd bad prime was not determined
  error         a runtime error in SelChab
The columns are dim Sel_2(J) = 0, ..., max, and "?" for curves with dim Sel unknown.
With --merged the row "failure (A3)" is merged into "failure" (the summary below the table
still lists the curves of failure (A3)).
With --points=PTS the points of a further search (ratpoints/run.py: lines g, i, h, H, number of
points, x-coordinates, seconds) are added to the records of the curves of this genus in PTS; it
must cover exactly the curves without extra points whose verdict is not "success".

Checks (each violation is reported as an ERROR, and the exit status is 1):
  - every index 1..N of the population occurs exactly once (with --partial: at most once;
    for test slices);
  - all records belong to the same population, and the POP headers agree on N;
  - no curve with verdict "success" has extra points;
  - the fields are consistent (success => (A3) and 2019 verdict true; code A3FAIL => (A3) false);
  - no runtime errors;
  - with --points: the lines of PTS for this genus are the curves without extra points and with
    verdict failure, failure (A3) or undetermined, each exactly once and with the same h.
"""

import sys
from collections import Counter, defaultdict

# display order of the rows (as in the paper); the bucket of a curve is decided by bucket()
ROWS = ["success", "more pts.", "failure (A3)", "failure", "undetermined", "error"]


def parse(files):
    pops, recs, errors = [], [], []
    for fn in files:
        with open(fn) as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                kind, *fields = line.split("\t")
                if kind not in ("POP", "REC", "END"):
                    errors.append(f"{fn}:{lineno}: unknown line {line[:60]!r}")
                    continue
                d = {}
                for fld in fields:
                    key, sep, val = fld.partition("=")
                    if not sep:
                        errors.append(f"{fn}:{lineno}: malformed field {fld!r}")
                    d[key] = val
                d["_where"] = f"{fn}:{lineno}"
                if kind == "POP":
                    pops.append(d)
                elif kind == "REC":
                    recs.append(legacy(d))
    return pops, recs, errors


def legacy(d):
    """Records written before the switch to the numbering of the revised paper (2026-11-17)
    call the condition (A4) and have no field inj; the 2019 code stopped with the code NONINJ
    when Sel_2(J) --> H_2 was not injective."""
    if "a4" in d:
        d["a3"] = d.pop("a4")
    d["code"] = {"A4FAIL": "A3FAIL"}.get(d["code"], d["code"])
    d["v"] = {"A4fail": "A3fail"}.get(d["v"], d["v"])
    d.setdefault("inj", "F" if d["code"] == "NONINJ" else "T")
    return d


def add_points(recs, fn, errors):
    """Add the points of the search in `fn` to the records of their genus; return the bounds H
    used, the number of curves searched and the records with new points."""
    g = recs[0]["g"]
    byidx = {r["i"]: r for r in recs}
    seen, bounds, found = set(), set(), []
    with open(fn) as fh:
        for lineno, line in enumerate(fh, 1):
            fg, i, h, bound, n, xs, _ = line.rstrip("\n").split("\t")
            if fg != g:
                continue
            w = f"{fn}:{lineno} (i={i}, h={h})"
            r = byidx.get(i)
            if r is None or r["h"] != h:
                errors.append(f"{w}: no record with this index and h")
                continue
            if i in seen:
                errors.append(f"{w}: searched twice")
            if r["v"] == "success" and r["nxs"] == "0":
                # proved after the search (the curves that were undetermined in genus 6)
                if int(n) > 0:
                    errors.append(f"{w}: points found on a curve with a proof")
            elif r["nxs"] != "0" or r["v"] not in ("fail", "A3fail", "undet"):
                errors.append(f"{w}: not a curve to search (nxs={r['nxs']}, v={r['v']})")
            seen.add(i)
            bounds.add(bound)
            if int(n) > 0:
                r["xs"], r["nxs"] = xs, n
                found.append(r)
    todo = [r["i"] for r in recs if r["i"] not in seen and r["nxs"] == "0"
            and r["v"] in ("fail", "A3fail", "undet")]
    if todo:
        errors.append(f"{fn}: {len(todo)} curves to search are missing: {todo[:20]}")
    return sorted(bounds), len(seen), found


def bucket(r):
    if int(r["nxs"]) > 0:
        return "more pts."
    return {"success": "success", "A3fail": "failure (A3)", "fail": "failure",
            "undet": "undetermined", "error": "error"}[r["v"]]


def check(pops, recs, partial, errors):
    if not pops:
        errors.append("no POP header")
        return None
    popids = {p["pop"] for p in pops} | {r["pop"] for r in recs}
    if len(popids) != 1:
        errors.append(f"several populations: {sorted(popids)}")
    sizes = {int(p["N"]) for p in pops}
    if len(sizes) != 1:
        errors.append(f"POP headers disagree on N: {sorted(sizes)}")
    N = max(sizes)
    count = Counter(int(r["i"]) for r in recs)
    dup = sorted(i for i, c in count.items() if c > 1)
    if dup:
        errors.append(f"{len(dup)} indices occur more than once: {dup[:20]}")
    bad = sorted(i for i in count if not 1 <= i <= N)
    if bad:
        errors.append(f"indices outside 1..{N}: {bad[:20]}")
    missing = N - len(set(count) - set(bad))
    if missing and not partial:
        errors.append(f"{missing} of {N} curves missing")
    for r in recs:
        w = f"{r['_where']} (i={r['i']}, h={r['h']})"
        if r["v"] == "success" and int(r["nxs"]) > 0:
            errors.append(f"{w}: success with extra points x = {r['xs']}")
        if r["v"] == "success" and (r["a3"] != "T"
                                    or r["v2019"] != ("T" if r["inj"] == "T" else "F")):
            errors.append(f"{w}: success, but a3={r['a3']}, inj={r['inj']}, "
                          f"v2019={r['v2019']}")
        if r["code"] == "A3FAIL" and (r["a3"] != "F" or r["v"] != "A3fail"):
            errors.append(f"{w}: code A3FAIL, but a3={r['a3']}, v={r['v']}")
        if r["v"] == "error":
            errors.append(f"{w}: runtime error: {r['err']}")
    return N


def table(recs, N, partial, merged=False):
    known = [int(r["sel"]) for r in recs if r["sel"] != "NA"]
    maxsel = max(known, default=0)
    cols = list(range(maxsel + 1))
    cnt = {row: Counter() for row in ROWS}
    for r in recs:
        b = bucket(r)
        if merged and b == "failure (A3)":
            b = "failure"
        cnt[b][int(r["sel"]) if r["sel"] != "NA" else "?"] += 1
    unknown = any(cnt[row]["?"] for row in ROWS)
    if unknown:
        cols.append("?")
    total = len(recs) if partial else N

    def stats(c):
        n = sum(c.values())
        nk = sum(v for k, v in c.items() if k != "?")
        avg = f"{sum(v * 2 ** k for k, v in c.items() if k != '?') / nk:.3f}" if nk else "-"
        return n, avg, f"{100.0 * n / total:.1f}%" if total else "-"

    shown = [row for row in ROWS if not (merged and row == "failure (A3)")]
    rows = [row for row in shown if sum(cnt[row].values()) or row in ROWS[:4]]
    tot = sum((cnt[row] for row in ROWS), Counter())
    out = []
    head = ["dim Sel"] + [str(c) for c in cols] + ["avg. #Sel", "total", "perc."]
    lines = []
    for row in rows + ["total"]:
        c = tot if row == "total" else cnt[row]
        n, avg, perc = stats(c)
        lines.append([row] + [str(c[k]) for k in cols] + [avg, str(n), perc])
    widths = [max(len(x[j]) for x in [head] + lines) for j in range(len(head))]
    fmt = lambda x: "  ".join(s.rjust(w) for s, w in zip(x, widths))
    out.append(fmt(head))
    out.append("-" * len(fmt(head)))
    out.extend(fmt(x) for x in lines)
    # LaTeX, in the layout of the paper
    tex = ["\\[ \\renewcommand{\\arraystretch}{1.2}",
           f"  \\begin{{array}}{{|r||*{{{len(cols)}}}{{c|}}|c||c|c|}} \\hline",
           "           \\dim \\Sel & " + " & ".join(str(c) for c in cols)
           + " & \\text{avg.~$\\#\\Sel$} & \\text{total} & \\text{perc.} \\\\ \\hline \\hline"]
    for x in lines:
        name = "\\text{%s}" % x[0]
        sep = " \\\\ \\hline\\hline" if x[0] == rows[-1] else " \\\\ \\hline"
        tex.append(f"  {name:>26} & " + " & ".join(x[1:-1]) + " & "
                   + x[-1].replace("%", "\\%") + sep)
    tex += ["  \\end{array}", "\\]"]
    return out, tex, cnt


def summary(recs):
    out = []
    codes = Counter(r["code"] for r in recs)
    out.append("codes: " + ", ".join(f"{k} {v}" for k, v in sorted(codes.items())))
    succ = [r for r in recs if bucket(r) == "success"]
    out.append(f"successes with J(Q)[2] != 0: {sum(1 for r in succ if r['jq2'] != '0')}"
               f" (of {len(succ)}; with dim Sel >= 1: "
               f"{sum(1 for r in succ if r['sel'] != '0')})")
    a3 = Counter((r["sel"], r["img"], r["jq2"]) for r in recs if r["code"] == "A3FAIL")
    if a3:
        out.append("failure (A3) by (dim Sel, dim image, dim J(Q)[2]): "
                   + ", ".join(f"{k} {v}" for k, v in sorted(a3.items())))
    a3pts = [r for r in recs
             if r["code"] == "A3FAIL" and r["inj"] == "T" and int(r["nxs"]) > 0]
    if a3pts:
        out.append(f"2019 successes refuted by points (code A3FAIL, in 'more pts.'): {len(a3pts)}")
        for r in a3pts[:10]:
            out.append(f"   i={r['i']} h={r['h']} x={r['xs']}")
    a3nf = Counter(r["a3"] for r in recs if r["img"] != "NA")
    out.append("(A3) where the image was computed: "
               + ", ".join(f"{k} {v}" for k, v in sorted(a3nf.items())))
    und = [r for r in recs if r["v"] == "undet"]
    for r in und:
        out.append(f"undetermined: i={r['i']} h={r['h']}: {r['err']}")
    ts = [float(r["tsel"]) for r in recs]
    tp = [float(r["tpts"]) for r in recs]
    if recs:
        out.append(f"CPU: SelChab {sum(ts):.1f} s (mean {sum(ts) / len(ts):.3f} s, max "
                   f"{max(ts):.2f} s), point search {sum(tp):.1f} s (mean "
                   f"{sum(tp) / len(tp):.3f} s, max {max(tp):.2f} s); "
                   f"total {(sum(ts) + sum(tp)) / 3600:.2f} h for {len(recs)} curves")
    return out


def main(argv):
    partial = "--partial" in argv
    merged = "--merged" in argv
    points = [a.partition("=")[2] for a in argv if a.startswith("--points=")]
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        print(__doc__)
        return 2
    pops, recs, errors = parse(files)
    pts = [add_points(recs, fn, errors) for fn in points] if recs else []
    N = check(pops, recs, partial, errors)
    if N is None:
        print("\n".join("ERROR: " + e for e in errors))
        return 1
    g = recs[0]["g"] if recs else "?"
    print(f"population {pops[0]['pop']}, genus {g}: {len(recs)} records, N = {N}"
          + (" (partial)" if partial else ""))
    out, tex, _ = table(recs, N, partial, merged)
    print("\n".join(out))
    print()
    print("\n".join(summary(recs)))
    for fn, (bounds, n, found) in zip(points, pts):
        print(f"further search {fn} (H = {', '.join(bounds)}): {n} curves, "
              f"{len(found)} with new points")
        for r in found:
            print(f"   i={r['i']} h={r['h']} sel={r['sel']} v={r['v']} x={r['xs']}")
    print()
    print("\n".join(tex))
    if errors:
        print()
        print("\n".join("ERROR: " + e for e in errors))
        return 1
    print("\nchecks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
